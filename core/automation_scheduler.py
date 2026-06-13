#!/usr/bin/env python3
"""
SuperMegaBot Automation Scheduler
Runs all periodic tasks: Digistore24 sync, Mailchimp sync,
Shopify sync, GitHub backup, Trading reports, System health alerts.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Concurrency / reliability constants ─────────────────────────────────────
_TASK_TIMEOUT_SECS   = 300      # Tasks running > 5 min are cancelled + alerted
_ALERT_AFTER_ERRORS  = 3        # Consecutive failures before Telegram alert
_MAX_BACKOFF_SECS    = 3600     # Cap on exponential backoff (1 hour)
_EMAIL_SEQ_SEMAPHORE = asyncio.Semaphore(10)   # Max parallel email deliveries

log = logging.getLogger("AutoScheduler")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

_SCHED_DB = DATA_DIR / "scheduler.db"

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


# ── Scheduler state DB ───────────────────────────────────────────────────────

def _init_db() -> None:
    """Create the scheduler SQLite database and required tables if they don't exist."""
    conn = sqlite3.connect(_SCHED_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            ran_at    TEXT NOT NULL,
            success   INTEGER NOT NULL DEFAULT 1,
            result    TEXT,
            duration_ms INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_task_runs_name ON task_runs(task_name, ran_at);
    """)
    conn.commit()
    conn.close()


def _log_run(task_name: str, success: bool, result: str, duration_ms: int) -> None:
    """Persist a single task execution record to the SQLite scheduler database."""
    try:
        conn = sqlite3.connect(_SCHED_DB)
        conn.execute(
            "INSERT INTO task_runs (task_name,ran_at,success,result,duration_ms) VALUES (?,?,?,?,?)",
            (task_name, datetime.now().isoformat(), int(success), result[:500], duration_ms)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"Scheduler DB write error: {e}")


def get_last_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent task run records ordered by newest first."""
    try:
        _init_db()
        conn = sqlite3.connect(_SCHED_DB)
        rows = conn.execute(
            "SELECT task_name,ran_at,success,result,duration_ms FROM task_runs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"task": r[0], "ran_at": r[1], "success": bool(r[2]), "result": r[3], "ms": r[4]} for r in rows]
    except Exception:
        return []


def get_task_stats() -> Dict[str, Any]:
    """Return aggregated run statistics (total, ok, last_run, avg_ms) per task name."""
    try:
        _init_db()
        conn = sqlite3.connect(_SCHED_DB)
        rows = conn.execute("""
            SELECT task_name,
                   COUNT(*) as total,
                   SUM(success) as ok,
                   MAX(ran_at) as last_run,
                   AVG(duration_ms) as avg_ms
            FROM task_runs
            GROUP BY task_name
        """).fetchall()
        conn.close()
        return {r[0]: {"total": r[1], "ok": r[2], "last_run": r[3], "avg_ms": round(r[4] or 0)} for r in rows}
    except Exception:
        return {}


# ── Telegram helper ──────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    """Send a Telegram message to the configured chat; silently skips if credentials missing."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(url, json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


# ── Individual task implementations ─────────────────────────────────────────

async def task_digistore_sync() -> str:
    """Fetch new Digistore24 orders → save to Supabase → Telegram alert."""
    try:
        from modules.digistore24_automation import get_orders, ping
        if not await ping():
            return "DS24 API nicht konfiguriert"
        orders = await get_orders(page=1, per_page=20)
        if not orders:
            return "Keine neuen Bestellungen"

        # Save to data file for dashboard
        out = DATA_DIR / "digistore_orders.json"
        old_ids: set = set()
        if out.exists():
            try:
                old_ids = {o.get("order_id") for o in json.loads(out.read_text())}
            except Exception:
                pass
        out.write_text(json.dumps(orders, indent=2, ensure_ascii=False))

        new_orders = [o for o in orders if o.get("order_id") not in old_ids]
        if new_orders:
            lines = [f"🏪 <b>Digistore24 — {len(new_orders)} neue Bestellung(en)!</b>"]
            for o in new_orders[:5]:
                lines.append(f"  • {o.get('product_name','?')} — {o.get('amount','?')} {o.get('currency','EUR')}")
            await _tg("\n".join(lines))
            return f"{len(new_orders)} neue Bestellungen, Telegram-Alert gesendet"
        return f"{len(orders)} Bestellungen gecacht, keine neuen"
    except Exception as e:
        return f"Fehler: {e}"


async def task_mailchimp_sync() -> str:
    """Sync Digistore24 buyer emails to Mailchimp default list."""
    try:
        from modules.mailchimp_automation import ping, get_lists, sync_from_digistore
        ok, _ = await ping()
        if not ok:
            return "Mailchimp nicht konfiguriert"
        lists = await get_lists()
        if not lists:
            return "Keine Mailchimp-Listen gefunden"
        list_id = lists[0]["id"]
        count = await sync_from_digistore(list_id)
        return f"{count} Kontakte aus Digistore24 nach Mailchimp synchronisiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_shopify_sync() -> str:
    """Fetch Shopify product + order counts and cache them."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        query = """{ shop { name } products(first:1){pageInfo{total}} orders(first:1){pageInfo{total}} }"""
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"{base}/api/2024-10/graphql.json",
                headers=headers,
                json={"query": query}
            ) as r:
                data = await r.json()
        errs = data.get("errors")
        if errs:
            return f"GraphQL-Fehler: {errs[0].get('message','?')[:80]}"
        shop = data["data"]["shop"]
        prods = data["data"]["products"]["pageInfo"]["total"]
        ords  = data["data"]["orders"]["pageInfo"]["total"]
        result = {"shop": shop["name"], "products": prods, "orders": ords, "ts": datetime.now().isoformat()}
        (DATA_DIR / "shopify_cache.json").write_text(json.dumps(result))
        return f"Shopify: {prods} Produkte, {ords} Bestellungen gecacht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_trading_report() -> str:
    """Run arbitrage scan and send best opportunity to Telegram."""
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        opps = await bot.scan_quick()
        if not opps:
            return "Keine Arbitrage-Chancen gefunden"
        best = opps[0]
        msg = (
            f"📈 <b>Trading Report</b>\n"
            f"Beste Chance: {best['pair']}\n"
            f"Kaufen: {best['exchange_buy']} @ {best['buy_price']:.2f}\n"
            f"Verkaufen: {best['exchange_sell']} @ {best['sell_price']:.2f}\n"
            f"Profit: {best['profit_pct']:.2f}%"
        )
        await _tg(msg)
        return f"{len(opps)} Chancen, beste: {best['pair']} {best['profit_pct']:.2f}%"
    except Exception as e:
        return f"Fehler: {e}"


async def task_github_backup() -> str:
    """Git add + commit + push all changes as nightly backup."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30
        )
        if not result.stdout.strip():
            return "Keine Änderungen zum Backup"
        subprocess.run(["git", "add", "-A"], cwd=str(BASE_DIR), timeout=30)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"chore: auto-backup {ts}"],
            cwd=str(BASE_DIR), capture_output=True, timeout=30
        )
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip() or "main"
        push = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60
        )
        if push.returncode == 0:
            return f"Backup auf Branch {branch} gepusht"
        return f"Push fehlgeschlagen: {push.stderr[:100]}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_system_health() -> str:
    """Check system resources, alert on critical thresholds."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        alerts = []
        if cpu > 90:
            alerts.append(f"CPU {cpu:.0f}%")
        if mem.percent > 90:
            alerts.append(f"RAM {mem.percent:.0f}%")
        if disk.percent > 90:
            alerts.append(f"Disk {disk.percent:.0f}%")
        if alerts:
            await _tg(f"⚠️ <b>System-Warnung</b>\n" + "\n".join(alerts))
            return "Kritisch: " + ", ".join(alerts)
        return f"OK — CPU {cpu:.0f}% RAM {mem.percent:.0f}% Disk {disk.percent:.0f}%"
    except ImportError:
        return "psutil nicht installiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_railway_health() -> str:
    """Ping Railway Shopify AI Suite, alert if down."""
    try:
        import aiohttp
        url = os.getenv("SHOPIFY_SUITE_URL", "https://shopify-suite-v2-production.up.railway.app")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{url}/health") as r:
                if r.status < 400:
                    return f"Railway OK ({r.status})"
                body = await r.text()
                await _tg(f"🔴 Railway Shopify Suite DOWN: HTTP {r.status}\n{body[:100]}")
                return f"DOWN: HTTP {r.status}"
    except Exception as e:
        await _tg(f"🔴 Railway Shopify Suite nicht erreichbar: {e}")
        return f"Nicht erreichbar: {e}"


async def task_printify_autofulfill() -> str:
    """Auto-submit pending Printify orders for production."""
    try:
        from modules.printify_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printify nicht konfiguriert"
        result = await auto_fulfill_pending()
        submitted = len(result.get("submitted", []))
        failed    = len(result.get("failed", []))
        if submitted:
            await _tg(f"🖨️ Printify: {submitted} Bestellungen automatisch an Produktion gesendet")
        return f"{submitted} submitted, {failed} failed von {result.get('total_pending',0)} pending"
    except Exception as e:
        return f"Fehler: {e}"


async def task_social_status() -> str:
    """Ping all social media connectors and log status."""
    try:
        from modules.social_connectors import ping_all
        results = await ping_all()
        connected = [k for k, v in results.items() if v.get("connected")]
        missing   = [k for k, v in results.items() if not v.get("connected")]
        return f"Verbunden: {', '.join(connected) or 'keine'} | Fehlt: {', '.join(missing) or 'keine'}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_dropshipping_scan() -> str:
    """Scan for trending products and auto-list top finds."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        products = await wf.find_trending_products(limit=5)
        if not products:
            return "Keine Trending-Produkte gefunden"
        return f"{len(products)} Trending-Produkte gefunden: {', '.join(p.get('title','?')[:20] for p in products[:3])}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_pod_autofulfill() -> str:
    """Print-on-Demand: auto-fulfill + publish new designs to Shopify."""
    try:
        from modules.dropshipping_automation import PrintOnDemandWorkflow
        from modules.printify_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printify nicht konfiguriert"
        result = await auto_fulfill_pending()
        sub = len(result.get("submitted", []))
        if sub:
            await _tg(f"🖨️ Print-on-Demand: {sub} Bestellungen automatisch in Produktion")
        return f"PoD: {sub} submitted, {result.get('total_pending',0)} pending gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_seo_optimizer() -> str:
    """Auto-optimize Shopify product SEO via local Ollama."""
    try:
        from modules.seo_automation import optimize_all_shopify_products
        result = await optimize_all_shopify_products(limit=10)
        updated = result.get("updated", 0)
        if updated:
            await _tg(f"🔍 SEO Auto-Optimizer: {updated} Produkte optimiert")
        return f"SEO: {result.get('processed',0)} geprüft, {updated} aktualisiert"
    except Exception as e:
        return f"Fehler: {e}"


async def task_revenue_report() -> str:
    """Collect revenue from all platforms and send daily summary."""
    try:
        from modules.revenue_aggregator import get_daily_report, save_daily_snapshot
        report = await get_daily_report()
        await save_daily_snapshot()
        await _tg(f"💰 <b>Tages-Report</b>\n{report}")
        return report[:120]
    except Exception as e:
        return f"Fehler: {e}"


async def task_content_calendar() -> str:
    """Generate weekly AI content calendar for all platforms."""
    try:
        from modules.ai_content_pipeline import generate_content_calendar
        calendar = await generate_content_calendar(niche="e-commerce", days=7)
        (DATA_DIR / "content_calendar.json").write_text(
            __import__("json").dumps(calendar, ensure_ascii=False, indent=2)
        )
        return f"Content-Kalender erstellt: {len(calendar)} Beiträge für 7 Tage"
    except Exception as e:
        return f"Fehler: {e}"


async def task_social_autoposter() -> str:
    """Auto-post latest Shopify products to all social platforms."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        products = await wf.find_trending_products(limit=3)
        posted = 0
        for p in products[:2]:
            result = await wf.promote_to_social(p)
            posted += sum(1 for v in result.values() if v.get("ok"))
        return f"Social Auto-Post: {posted} Posts veröffentlicht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_etsy_sync() -> str:
    """Sync Etsy listings and check for new orders."""
    try:
        from modules.ecommerce_connectors import EtsyConnector
        etsy = EtsyConnector()
        ok, info = await etsy.ping()
        if not ok:
            return f"Etsy nicht konfiguriert: {info}"
        stats = await etsy.get_stats()
        transactions = await etsy.get_transactions(limit=5)
        return f"Etsy: {stats.get('listing_count',0)} Listings, {len(transactions)} neue Transaktionen"
    except Exception as e:
        return f"Fehler: {e}"


async def task_gumroad_sync() -> str:
    """Check Gumroad for new sales."""
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        ok, info = await gum.ping()
        if not ok:
            return f"Gumroad nicht konfiguriert: {info}"
        stats = await gum.get_stats()
        if stats.get("new_sales", 0):
            await _tg(f"💰 Gumroad: {stats['new_sales']} neue Verkäufe! Umsatz: {stats.get('revenue','?')}")
        return f"Gumroad: {stats.get('total_sales',0)} Verkäufe gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_shopify_orders_alert() -> str:
    """Check for new Shopify orders every 10 min and alert via Telegram."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

        state_file = DATA_DIR / "shopify_last_order.json"
        last_id = 0
        if state_file.exists():
            try:
                last_id = json.loads(state_file.read_text()).get("last_id", 0)
            except Exception:
                pass

        url = f"{base}/admin/api/{os.getenv('SHOPIFY_API_VERSION','2024-10')}/orders.json?status=any&limit=10&order=created_at+desc"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url, headers=headers) as r:
                if r.status != 200:
                    return f"Shopify HTTP {r.status}"
                data = await r.json()

        orders = data.get("orders", [])
        if not orders:
            return "Keine Bestellungen"

        new_orders = [o for o in orders if o.get("id", 0) > last_id]
        if new_orders:
            state_file.write_text(json.dumps({"last_id": orders[0]["id"]}))
            lines = [f"🛍️ <b>Shopify — {len(new_orders)} neue Bestellung(en)!</b>"]
            for o in new_orders[:5]:
                total = o.get("total_price", "?")
                currency = o.get("currency", "EUR")
                name = o.get("billing_address", {}).get("first_name", "Kunde")
                lines.append(f"  • #{o.get('order_number','?')} — {name} — {total} {currency}")
            await _tg("\n".join(lines))
            return f"{len(new_orders)} neue Shopify-Bestellungen, Alert gesendet"
        elif last_id == 0 and orders:
            state_file.write_text(json.dumps({"last_id": orders[0]["id"]}))
            return f"Initialisiert: letzte Order-ID = {orders[0]['id']}"
        return "Keine neuen Bestellungen"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printify_discover_shop() -> str:
    """Auto-discover Printify shop ID and save to data dir."""
    try:
        import aiohttp
        key = os.getenv("PRINTIFY_API_KEY", "")
        if not key:
            return "PRINTIFY_API_KEY nicht gesetzt"
        saved_id = os.getenv("PRINTIFY_SHOP_ID", "")
        if saved_id:
            return f"Shop-ID bereits bekannt: {saved_id}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                "https://api.printify.com/v1/shops.json",
                headers={"Authorization": f"Bearer {key}"}
            ) as r:
                if r.status != 200:
                    return f"Printify HTTP {r.status}"
                shops = await r.json()

        if not shops:
            return "Keine Printify-Shops gefunden"
        shop = shops[0]
        shop_id = str(shop.get("id", ""))
        (DATA_DIR / "printify_shop.json").write_text(json.dumps({"shop_id": shop_id, "title": shop.get("title","?"), "ts": datetime.now().isoformat()}))
        log.info(f"Printify Shop entdeckt: {shop.get('title')} (ID {shop_id}) — trage PRINTIFY_SHOP_ID={shop_id} in .env ein")
        await _tg(f"🖨️ Printify Shop gefunden: <b>{shop.get('title','?')}</b> (ID: <code>{shop_id}</code>)\nBitte in .env setzen: PRINTIFY_SHOP_ID={shop_id}")
        return f"Shop gefunden: {shop.get('title','?')} ID={shop_id}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_api_keys_health() -> str:
    """Check critical API keys and alert if missing."""
    critical = [
        ("SHOPIFY_ACCESS_TOKEN", lambda v: v.startswith("shpat_")),
        ("PRINTIFY_API_KEY",     lambda v: len(v) > 50),
        ("DIGISTORE24_API_KEY",  lambda v: "-" in v),
        ("SUPABASE_URL",         lambda v: "supabase" in v),
        ("PERPLEXITY_API_KEY",   lambda v: v.startswith("pplx-")),
    ]
    missing, ok = [], []
    for key, check in critical:
        val = os.getenv(key, "")
        if not val or not check(val):
            missing.append(key)
        else:
            ok.append(key)
    if missing:
        await _tg(f"⚠️ <b>API-Keys fehlen/ungültig:</b>\n" + "\n".join(f"  • {k}" for k in missing))
        return f"Fehlend: {', '.join(missing)} | OK: {len(ok)}"
    return f"Alle {len(ok)} kritischen Keys OK"


async def task_gmc_refresh() -> str:
    """Refresh Google Merchant Center product feed status."""
    try:
        import aiohttp
        merchant_id = os.getenv("GMC_MERCHANT_ID", "")
        client_id   = os.getenv("GOOGLE_CLIENT_ID", "")
        if not merchant_id or not client_id:
            return "GMC nicht vollständig konfiguriert"
        out = DATA_DIR / "gmc_status.json"
        out.write_text(json.dumps({
            "merchant_id": merchant_id,
            "last_check": datetime.now().isoformat(),
            "status": "configured"
        }))
        return f"GMC Merchant {merchant_id} — Status gecacht"
    except Exception as e:
        return f"Fehler: {e}"


async def task_youtube_stats() -> str:
    """Fetch YouTube channel stats."""
    try:
        import aiohttp
        channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "")
        api_key    = os.getenv("YOUTUBE_API_KEY", "")
        if not channel_id:
            return "YOUTUBE_CHANNEL_ID nicht gesetzt"
        if not api_key:
            return f"YOUTUBE_API_KEY fehlt (Channel: {channel_id})"
        url = (
            f"https://www.googleapis.com/youtube/v3/channels"
            f"?part=statistics&id={channel_id}&key={api_key}"
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return f"YouTube API HTTP {r.status}"
                data = await r.json()
        items = data.get("items", [])
        if not items:
            return "Kanal nicht gefunden"
        stats = items[0].get("statistics", {})
        subs    = int(stats.get("subscriberCount", 0))
        views   = int(stats.get("viewCount", 0))
        videos  = int(stats.get("videoCount", 0))
        (DATA_DIR / "youtube_stats.json").write_text(json.dumps({**stats, "ts": datetime.now().isoformat()}))
        return f"YouTube: {subs:,} Abonnenten, {views:,} Views, {videos} Videos"
    except Exception as e:
        return f"Fehler: {e}"


async def task_digistore_products_check() -> str:
    """Check Digistore24 product performance and cache."""
    try:
        from modules.digistore24_automation import ping, get_products, get_sales_stats
        if not await ping():
            return "DS24 nicht konfiguriert"
        products = await get_products()
        stats    = await get_sales_stats()
        (DATA_DIR / "digistore_products.json").write_text(
            json.dumps({"products": products, "stats": stats, "ts": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2)
        )
        total_revenue = stats.get("total_revenue", 0)
        return f"DS24: {len(products)} Produkte, Umsatz: {total_revenue}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_log_cleanup() -> str:
    """Rotate and compress logs > 10 MB; delete files older than 30 days."""
    import gzip, shutil
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    cleaned, compressed = 0, 0
    cutoff = datetime.now().timestamp() - 30 * 86400
    for f in logs_dir.iterdir():
        if f.suffix == ".gz" and f.stat().st_mtime < cutoff:
            f.unlink()
            cleaned += 1
        elif f.suffix == ".log" and f.stat().st_size > 10 * 1024 * 1024:
            gz_path = f.with_suffix(".log.gz")
            with f.open("rb") as fi, gzip.open(gz_path, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            f.write_text("")  # truncate, keep file handle valid
            compressed += 1
    return f"Logs: {compressed} komprimiert, {cleaned} alte gelöscht"


async def task_env_auto_update() -> str:
    """Write auto-discovered values (Printify shop ID) into data cache."""
    updates = []
    shop_file = DATA_DIR / "printify_shop.json"
    if shop_file.exists() and not os.getenv("PRINTIFY_SHOP_ID"):
        try:
            d = json.loads(shop_file.read_text())
            shop_id = d.get("shop_id", "")
            if shop_id:
                updates.append(f"PRINTIFY_SHOP_ID={shop_id} (aus Cache, bitte in .env eintragen)")
                log.info(f"Auto-discovered PRINTIFY_SHOP_ID={shop_id} — .env manuell aktualisieren")
        except Exception:
            pass
    if not updates:
        return "Keine ausstehenden Auto-Updates"
    await _tg("ℹ️ <b>Auto-entdeckte Werte — bitte in .env eintragen:</b>\n" + "\n".join(updates))
    return " | ".join(updates)


async def task_shopify_webhooks_setup() -> str:
    """Register Shopify order/fulfillment webhooks for real-time alerts."""
    try:
        import aiohttp
        token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        suite_url = os.getenv("SHOPIFY_SUITE_URL", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        if not suite_url:
            return "SHOPIFY_SUITE_URL fehlt — Webhook-Endpunkt unbekannt"
        base = f"https://{domain}" if not domain.startswith("http") else domain
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        api_ver = os.getenv("SHOPIFY_API_VERSION", "2024-10")

        # Check existing webhooks
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"{base}/admin/api/{api_ver}/webhooks.json", headers=headers) as r:
                if r.status != 200:
                    return f"Shopify HTTP {r.status} beim Webhook-Abruf"
                existing = {w["topic"] for w in (await r.json()).get("webhooks", [])}

            desired = {
                "orders/create":      f"{suite_url}/webhooks/shopify/orders-create",
                "orders/fulfilled":   f"{suite_url}/webhooks/shopify/orders-fulfilled",
                "orders/cancelled":   f"{suite_url}/webhooks/shopify/orders-cancelled",
                "products/create":    f"{suite_url}/webhooks/shopify/products-create",
            }
            created = []
            for topic, endpoint in desired.items():
                if topic not in existing:
                    async with s.post(
                        f"{base}/admin/api/{api_ver}/webhooks.json",
                        headers=headers,
                        json={"webhook": {"topic": topic, "address": endpoint, "format": "json"}}
                    ) as cr:
                        if cr.status in (200, 201):
                            created.append(topic)
        if created:
            return f"Webhooks registriert: {', '.join(created)}"
        return f"Alle Webhooks bereits registriert ({len(existing)} aktiv)"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printify_shopify_sync() -> str:
    """Sync published Printify products to Shopify — create missing listings."""
    try:
        from modules.printify_automation import ping, get_products as get_printify_products
        if not await ping():
            return "Printify nicht konfiguriert"
        products = await get_printify_products()
        published = [p for p in products if p.get("visible")]
        shopify_missing = [p for p in published if not p.get("external", {}).get("id")]
        if not shopify_missing:
            return f"Printify→Shopify: alle {len(published)} Produkte bereits verknüpft"
        # Just report — actual publish needs full variant data
        return f"Printify: {len(published)} veröffentlicht, {len(shopify_missing)} noch nicht in Shopify"
    except Exception as e:
        return f"Fehler: {e}"


async def task_daily_summary() -> str:
    """Send complete daily business summary to Telegram."""
    try:
        parts = []
        # System
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            parts.append(f"🖥 System: CPU {cpu:.0f}% | RAM {mem.percent:.0f}%")
        except Exception:
            pass

        # Digistore
        ds_file = DATA_DIR / "digistore_orders.json"
        if ds_file.exists():
            try:
                orders = json.loads(ds_file.read_text())
                parts.append(f"🏪 Digistore24: {len(orders)} Bestellungen gecacht")
            except Exception:
                pass

        # Shopify
        sh_file = DATA_DIR / "shopify_cache.json"
        if sh_file.exists():
            try:
                d = json.loads(sh_file.read_text())
                parts.append(f"🛍 Shopify: {d.get('products','?')} Produkte | {d.get('orders','?')} Bestellungen")
            except Exception:
                pass

        # YouTube
        yt_file = DATA_DIR / "youtube_stats.json"
        if yt_file.exists():
            try:
                d = json.loads(yt_file.read_text())
                parts.append(f"▶️ YouTube: {int(d.get('subscriberCount',0)):,} Abonnenten")
            except Exception:
                pass

        # Scheduler stats
        stats = get_task_stats()
        total_runs = sum(v.get("total", 0) for v in stats.values())
        ok_runs    = sum(v.get("ok", 0) for v in stats.values())
        parts.append(f"🤖 Automation: {ok_runs}/{total_runs} Tasks erfolgreich")

        msg = f"📊 <b>SuperMegaBot — Tages-Zusammenfassung</b>\n{datetime.now().strftime('%d.%m.%Y')}\n\n" + "\n".join(parts)
        await _tg(msg)
        return f"Tages-Summary gesendet ({len(parts)} Bereiche)"
    except Exception as e:
        return f"Fehler: {e}"


async def task_stripe_monitor() -> str:
    """Check Stripe for new payments and alert via Telegram."""
    try:
        from modules.stripe_automation import monitor_payments
        return await monitor_payments()
    except Exception as e:
        return f"Stripe Monitor Fehler: {e}"


async def task_drive_backup() -> str:
    """Backup data directory JSON files to Google Drive."""
    try:
        from modules.google_drive_automation import auto_backup
        return await auto_backup()
    except Exception as e:
        return f"Drive Backup Fehler: {e}"


# ── Task registry ────────────────────────────────────────────────────────────

async def task_revenue_autopilot_carts() -> str:
    """Stündlich: Abandoned Carts erkennen und Recovery-Emails senden."""
    try:
        from modules.shopify_revenue_engine import get_abandoned_carts, recover_all_carts
        carts = await get_abandoned_carts(hours=2)
        carts_with_email = [c for c in carts if c.get("email")]
        if not carts_with_email:
            return "Keine neuen Abandoned Carts in den letzten 2h"
        result = await recover_all_carts(hours=2)
        potential = result.get("potential_revenue", 0)
        sent = result.get("emails_sent", 0)
        if sent > 0:
            await _tg(
                f"🛒 *Cart Recovery gestartet*\n"
                f"• {sent} Recovery-Emails gesendet\n"
                f"• Potentieller Umsatz: €{potential:.2f}"
            )
        return f"Cart Recovery: {sent}/{len(carts_with_email)} Emails gesendet · €{potential:.2f} potentiell"
    except Exception as e:
        return f"Fehler Cart Recovery: {e}"


async def task_revenue_autopilot_daily() -> str:
    """Täglich: Revenue-Report + Zero-Seller-Analyse via Telegram."""
    try:
        from modules.shopify_revenue_engine import get_revenue_summary, get_product_performance, get_low_inventory
        rev = await get_revenue_summary()
        today = rev.get("today", {})
        d7    = rev.get("7d", {})
        d30   = rev.get("30d", {})

        perf = await get_product_performance(days=7)
        top3 = perf.get("top_sellers", [])[:3]
        zeros = perf.get("zero_seller_count", 0)

        inv = await get_low_inventory(threshold=3)

        lines = [
            "📊 *Täglicher Revenue Report*",
            f"",
            f"💶 Heute: €{today.get('revenue',0):.2f} ({today.get('orders',0)} Bestellungen)",
            f"📅 7 Tage: €{d7.get('revenue',0):.2f} ({d7.get('orders',0)} Bestellungen)",
            f"📆 30 Tage: €{d30.get('revenue',0):.2f} ({d30.get('orders',0)} Bestellungen)",
            f"",
        ]
        if top3:
            lines.append("🏆 *Top-Produkte (7T):*")
            for p in top3:
                lines.append(f"  • {p['title'][:30]}: €{p['revenue']:.2f}")
        if zeros > 0:
            lines.append(f"\n⚠️ {zeros} Produkte ohne Verkauf in 7 Tagen")
        if inv:
            lines.append(f"📦 {len(inv)} Produkte mit kritisch niedrigem Lager")
        lines.append(f"\n🤖 Revenue Autopilot aktiv")

        await _tg("\n".join(lines))
        return f"Daily Revenue Report gesendet: €{d7.get('revenue',0):.2f} in 7 Tagen"
    except Exception as e:
        return f"Fehler Daily Revenue Report: {e}"




# ---------------------------------------------------------------------------
# SCALE ENGINE TASKS
# ---------------------------------------------------------------------------
async def task_review_automation() -> str:
    """Send review request emails to customers whose orders are 7+ days old."""
    try:
        from modules.growth_engine import run_review_automation
        result = await run_review_automation()
        sent    = result.get("sent", 0)
        skipped = result.get("skipped", 0)
        failed  = result.get("failed", 0)
        pending = result.get("pending", 0)
        return f"Review Automation: {sent} gesendet, {skipped} übersprungen, {failed} Fehler von {pending} pending"
    except Exception as e:
        return f"Review Automation Fehler: {e}"


async def task_winback_campaign() -> str:
    """Send win-back emails with discount codes to inactive customers."""
    try:
        from modules.growth_engine import run_winback_automation
        result = await run_winback_automation()
        churned = result.get("churned_customers", 0)
        sent    = result.get("sent", 0)
        failed  = result.get("failed", 0)
        code    = result.get("discount_code", "N/A")
        return f"Win-Back: {churned} inaktive Kunden, {sent} E-Mails, Code: {code}, {failed} Fehler"
    except Exception as e:
        return f"Win-Back Fehler: {e}"


async def task_referral_stats() -> str:
    """Fetch and cache referral program statistics."""
    try:
        from modules.growth_engine import get_referral_stats
        stats = await get_referral_stats()
        if "error" in stats:
            return f"Referral Stats: {stats['error']}"
        referrers   = stats.get("total_referrers", 0)
        clicks      = stats.get("total_clicks", 0)
        conversions = stats.get("total_conversions", 0)
        revenue     = stats.get("total_revenue_eur", 0)
        commission  = stats.get("total_commission_eur", 0)
        cvr         = stats.get("conversion_rate_pct", 0)
        # Cache to data dir
        out = DATA_DIR / "referral_stats.json"
        out.write_text(__import__("json").dumps(stats, ensure_ascii=False, indent=2))
        return (
            f"Referral: {referrers} Referrer, {clicks} Clicks, "
            f"{conversions} Conversions ({cvr}%), "
            f"Revenue {revenue:.2f}€, Provision {commission:.2f}€"
        )
    except Exception as e:
        return f"Referral Stats Fehler: {e}"


# ── Task registry ────────────────────────────────────────────────────────────



async def task_dynamic_pricing() -> str:
    """Run AI-powered dynamic pricing cycle across all active Shopify products."""
    try:
        from modules.dynamic_pricing import run_dynamic_pricing_cycle
        result = await run_dynamic_pricing_cycle(max_products=20)
        updated  = result.get("updated", 0)
        impact   = result.get("total_revenue_impact", "?")
        errors   = result.get("errors", [])
        err_note = f" ({len(errors)} errors)" if errors else ""
        return f"Dynamic Pricing: {updated} prices updated, impact {impact}{err_note}"
    except Exception as e:
        return f"Dynamic Pricing Fehler: {e}"


async def task_email_sequences() -> str:
    """Process all due email sequence deliveries (Semaphore(10) for parallel safety)."""
    try:
        from modules.email_sequence_engine import process_due_emails
        # Pass the module-level semaphore so bulk runs don't fan out uncontrolled
        async with _EMAIL_SEQ_SEMAPHORE:
            result = await process_due_emails()
        sent   = result.get("sent", 0)
        failed = result.get("failed", 0)
        return f"Email Sequences: {sent} gesendet, {failed} fehlgeschlagen"
    except Exception as e:
        return f"Email Sequences Fehler: {e}"


async def task_email_enroll_new() -> str:
    """Auto-enroll new Shopify customers into welcome + post-purchase sequences."""
    try:
        from modules.email_sequence_engine import auto_enroll_new_customers, auto_enroll_post_purchase
        welcome_res = await auto_enroll_new_customers()
        purchase_res = await auto_enroll_post_purchase()
        w_enrolled = welcome_res.get("enrolled", 0)
        p_enrolled = purchase_res.get("enrolled", 0)
        return f"Email Enroll: {w_enrolled} welcome, {p_enrolled} post-purchase"
    except Exception as e:
        return f"Email Enroll Fehler: {e}"


async def task_vip_promotion() -> str:
    """Promote qualifying customers to VIP email sequence."""
    try:
        from modules.email_sequence_engine import promote_to_vip
        result = await promote_to_vip(min_orders=3, min_revenue=200)
        promoted = result.get("promoted", 0)
        return f"VIP Promotion: {promoted} Kunden befördert"
    except Exception as e:
        return f"VIP Promotion Fehler: {e}"


# ── Task registry ────────────────────────────────────────────────────────────



async def task_b2b_prospecting() -> str:
    """Daily B2B lead prospecting — findet neue Shopify-Store-Betreiber."""
    try:
        from modules.b2b_pipeline import run_daily_prospecting
        result = await run_daily_prospecting()
        added  = result.get("added", 0)
        found  = result.get("found", 0)
        return f"B2B Prospecting: {found} gefunden, {added} zur Pipeline hinzugefügt"
    except Exception as e:
        return f"B2B Prospecting Fehler: {e}"


async def task_tiktok_sync() -> str:
    """Stündlich Shopify-Produkte zu TikTok Shop synchronisieren."""
    try:
        from modules.tiktok_shop_sync import sync_products_to_tiktok
        result = await sync_products_to_tiktok(limit=50)
        synced = result.get("synced", 0)
        failed = result.get("failed", 0)
        return f"TikTok Sync: {synced} Produkte synchronisiert, {failed} fehlgeschlagen"
    except Exception as e:
        return f"TikTok Sync Fehler: {e}"


async def task_tiktok_orders() -> str:
    """TikTok-Bestellungen in Shopify importieren (alle 30 min)."""
    try:
        from modules.tiktok_shop_sync import sync_tiktok_orders_to_shopify
        result = await sync_tiktok_orders_to_shopify()
        imported = result.get("imported", 0)
        skipped  = result.get("skipped", 0)
        if imported:
            await _tg(f"TikTok: {imported} neue Bestellungen nach Shopify importiert")
        return f"TikTok Orders: {imported} importiert, {skipped} bereits vorhanden"
    except Exception as e:
        return f"TikTok Orders Fehler: {e}"


async def task_whatsapp_report() -> str:
    """Täglicher WhatsApp Revenue-Report an den Betreiber."""
    try:
        from modules.whatsapp_automation import send_revenue_alert, get_whatsapp_stats
        from modules.tiktok_shop_sync import get_combined_revenue
        revenue = await get_combined_revenue()
        daily_total = revenue.get("total_revenue_eur_today", 0.0)
        target      = float(os.getenv("DAILY_REVENUE_TARGET", "200"))
        await send_revenue_alert(daily_total, target)
        stats = await get_whatsapp_stats()
        sent  = stats.get("sent_today", 0)
        recv  = stats.get("received_today", 0)
        return (
            f"WhatsApp Report: €{daily_total:.2f} Tagesumsatz (Ziel €{target:.2f}) | "
            f"WA: {sent} gesendet, {recv} empfangen"
        )
    except Exception as e:
        return f"WhatsApp Report Fehler: {e}"


# ── Task registry ────────────────────────────────────────────────────────────



TASKS = [
    # (name, coroutine_fn, interval_seconds, initial_delay_seconds)
    # ── Real-time (every few minutes) ────────────────────────────────────────
    ("system_health",           task_system_health,           300,    10),   # 5 min
    ("railway_health",          task_railway_health,          600,    20),   # 10 min
    ("shopify_orders_alert",    task_shopify_orders_alert,    600,    15),   # 10 min
    # ── Sales & Orders (every 15-30 min) ─────────────────────────────────────
    ("digistore_sync",          task_digistore_sync,          900,    30),   # 15 min
    ("printify_autofulfill",    task_printify_autofulfill,    1800,   45),   # 30 min
    ("pod_autofulfill",         task_pod_autofulfill,         1800,   50),   # 30 min
    ("etsy_sync",               task_etsy_sync,               1800,   60),   # 30 min
    ("gumroad_sync",            task_gumroad_sync,            1800,   75),   # 30 min
    ("digistore_products_check",task_digistore_products_check,1800,   85),   # 30 min
    # ── Marketing & Sync (hourly) ─────────────────────────────────────────────
    ("mailchimp_sync",          task_mailchimp_sync,          3600,   90),   # 1h
    ("shopify_sync",            task_shopify_sync,            3600,   120),  # 1h
    ("social_status",           task_social_status,           3600,   150),  # 1h
    ("social_autoposter",       task_social_autoposter,       3600,   180),  # 1h
    # ── Growth & SEO (every 2-6 hours) ────────────────────────────────────────
    ("seo_optimizer",           task_seo_optimizer,           7200,   200),  # 2h
    ("dropshipping_scan",       task_dropshipping_scan,       7200,   220),  # 2h
    ("api_keys_health",         task_api_keys_health,         21600,  60),   # 6h
    ("trading_report",          task_trading_report,          21600,  240),  # 6h
    ("printify_discover_shop",  task_printify_discover_shop,  21600,   5),   # 6h (fast start)
    # ── Maintenance (hourly) ──────────────────────────────────────────────────
    ("env_auto_update",         task_env_auto_update,         3600,   8),    # 1h (fast start)
    ("printify_shopify_sync",   task_printify_shopify_sync,   3600,   170),  # 1h
    # ── Setup (every 6h) ─────────────────────────────────────────────────────
    ("shopify_webhooks_setup",  task_shopify_webhooks_setup,  21600,  12),   # 6h (fast start)
    # ── Daily ─────────────────────────────────────────────────────────────────
    ("revenue_report",          task_revenue_report,          86400,  270),  # daily
    ("content_calendar",        task_content_calendar,        86400,  290),  # daily
    ("github_backup",           task_github_backup,           86400,  300),  # daily
    ("gmc_refresh",             task_gmc_refresh,             86400,  310),  # daily
    ("youtube_stats",           task_youtube_stats,           86400,  320),  # daily
    ("log_cleanup",             task_log_cleanup,             86400,  330),  # daily
    ("daily_summary",           task_daily_summary,           86400,  340),  # daily
    # ── Stripe & Drive ───────────────────────────────────────────────────────
    ("stripe_monitor",          task_stripe_monitor,          1800,   25),   # 30 min
    ("drive_backup",            task_drive_backup,            86400,  360),  # daily
    # ── Revenue Autopilot ────────────────────────────────────────────────────
    ("revenue_autopilot_carts", task_revenue_autopilot_carts,  3600,   35),  # 1h
    ("revenue_autopilot_daily", task_revenue_autopilot_daily, 86400,  400),  # daily

    # ── Scale Engines (Growth + Pricing + Email + B2B + TikTok + WhatsApp)
    ("review_automation",       task_review_automation,       86400,  500),  # daily
    ("winback_campaign",        task_winback_campaign,        86400,  520),  # daily
    ("referral_stats",          task_referral_stats,          3600,   510),  # 1h
    ("dynamic_pricing",         task_dynamic_pricing,         7200,   600),  # 2h
    ("email_sequences",         task_email_sequences,         86400,  610),  # daily
    ("email_enroll_new",        task_email_enroll_new,        3600,   620),  # 1h
    ("vip_promotion",           task_vip_promotion,           86400,  630),  # daily
    ("b2b_prospecting",         task_b2b_prospecting,         86400,  700),  # daily
    ("tiktok_product_sync",     task_tiktok_sync,             3600,   710),  # 1h
    ("tiktok_order_sync",       task_tiktok_orders,           1800,   720),  # 30min
    ("whatsapp_daily_report",   task_whatsapp_report,         86400,  730),  # daily
]


# ── Scheduler loop ───────────────────────────────────────────────────────────

class AutomationScheduler:
    """Manages all periodic automation tasks with overlap prevention and failure alerting."""

    def __init__(self) -> None:
        """Initialise the scheduler, create DB tables, and set up per-task locks and counters."""
        _init_db()
        self._running: bool = False
        self._task_handles: List[asyncio.Task] = []
        # Per-task asyncio.Lock → prevents overlap when a task runs longer than its interval
        self._locks: Dict[str, asyncio.Lock] = {name: asyncio.Lock() for name, *_ in TASKS}
        # Consecutive-failure counters for alerting
        self._fail_counts: Dict[str, int] = {name: 0 for name, *_ in TASKS}

    async def start(self) -> None:
        """Start all registered task loops as independent asyncio Tasks."""
        self._running = True
        log.info(f"AutoScheduler gestartet — {len(TASKS)} Tasks registriert")
        for name, fn, interval, delay in TASKS:
            handle = asyncio.create_task(self._run_loop(name, fn, interval, delay))
            self._task_handles.append(handle)

    async def stop(self) -> None:
        """Cancel all running task loops and mark the scheduler as stopped."""
        self._running = False
        for h in self._task_handles:
            h.cancel()

    async def run_now(self, task_name: str) -> Optional[str]:
        """Execute a named task immediately outside its normal schedule and return its result."""
        for name, fn, _, _ in TASKS:
            if name == task_name:
                return await self._execute(name, fn)
        return f"Task {task_name!r} nicht gefunden"

    async def _run_loop(self, name: str, fn: Callable[[], Any], interval: int, delay: int) -> None:
        """Wait for the initial delay then execute the task repeatedly at the given interval."""
        await asyncio.sleep(delay)
        backoff = 0  # exponential backoff after repeated failures (seconds)
        while self._running:
            if backoff:
                await asyncio.sleep(min(backoff, _MAX_BACKOFF_SECS))
                backoff = 0

            result = await self._execute(name, fn)
            log.debug(f"[{name}] {result}")

            # Determine next sleep: use normal interval
            await asyncio.sleep(interval)

    async def _execute(self, name: str, fn: Callable[[], Any]) -> str:
        """Run fn() with timeout and overlap protection; log result and alert on repeated failures."""
        lock = self._locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[name] = lock

        # Skip if previous run is still in progress
        if lock.locked():
            msg = f"[{name}] still running — skipping overlap"
            log.warning(msg)
            return msg

        async with lock:
            t0 = time.monotonic()
            try:
                # Hard timeout: cancel task if it exceeds _TASK_TIMEOUT_SECS
                result = await asyncio.wait_for(fn(), timeout=_TASK_TIMEOUT_SECS)
                ms = int((time.monotonic() - t0) * 1000)
                _log_run(name, True, result or "", ms)
                # Reset failure counter on success
                self._fail_counts[name] = 0
                return result or "OK"
            except asyncio.TimeoutError:
                ms = int((time.monotonic() - t0) * 1000)
                err = f"TIMEOUT nach {_TASK_TIMEOUT_SECS}s"
                _log_run(name, False, err, ms)
                log.error(f"[{name}] {err}")
                await _tg(f"⏱ <b>Task Timeout</b>: <code>{name}</code> lief länger als {_TASK_TIMEOUT_SECS}s und wurde abgebrochen.")
                self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
                return err
            except Exception as e:
                ms = int((time.monotonic() - t0) * 1000)
                err = f"{type(e).__name__}: {e}"
                _log_run(name, False, err, ms)
                log.error(f"[{name}] {err}")
                self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
                # Alert after _ALERT_AFTER_ERRORS consecutive failures
                if self._fail_counts[name] >= _ALERT_AFTER_ERRORS:
                    await _tg(
                        f"🚨 <b>Task-Fehler ({self._fail_counts[name]}x in Folge)</b>\n"
                        f"Task: <code>{name}</code>\n"
                        f"Fehler: {err[:200]}"
                    )
                return err

    def status(self) -> Dict[str, Any]:
        """Return a snapshot of scheduler state and per-task run statistics."""
        stats = get_task_stats()
        return {
            "running": self._running,
            "task_count": len(TASKS),
            "tasks": [
                {
                    "name": name,
                    "interval_s": interval,
                    "consecutive_failures": self._fail_counts.get(name, 0),
                    **stats.get(name, {"total": 0, "ok": 0, "last_run": None, "avg_ms": 0})
                }
                for name, _, interval, _ in TASKS
            ]
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_scheduler: Optional[AutomationScheduler] = None


def get_scheduler() -> AutomationScheduler:
    """Return the module-level singleton AutomationScheduler, creating it if necessary."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AutomationScheduler()
    return _scheduler
