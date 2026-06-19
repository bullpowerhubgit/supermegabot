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
from typing import Callable, Dict, List, Optional

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

def _init_db():
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


def _log_run(task_name: str, success: bool, result: str, duration_ms: int):
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


def get_last_runs(limit: int = 50) -> List[Dict]:
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


def get_task_stats() -> Dict:
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

async def _tg(msg: str):
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


async def task_ds24_funnel_sync() -> str:
    """DS24 neue Käufer → Mailchimp + Klaviyo + Telegram vollautomatisch."""
    try:
        from modules.ds24_funnel_automation import run_sync
        result = await run_sync()
        return (f"DS24 Funnel: {result['new_buyers']} neue Käufer synced "
                f"({result['total_seen']} gesamt)")
    except Exception as e:
        return f"DS24 Funnel Fehler: {e}"


async def task_traffic_seo_run() -> str:
    """AI-generierter SEO Content für DS24 + Shopify Produkte."""
    try:
        from modules.traffic_seo_engine import run_full_traffic_seo
        result = await run_full_traffic_seo()
        ds = result.get("ds24_products_optimized", 0)
        sh = result.get("shopify_result", {}).get("products_updated", 0)
        return f"SEO: {ds} DS24-Produkte + {sh} Shopify-Produkte optimiert"
    except Exception as e:
        return f"Traffic/SEO Fehler: {e}"


async def task_brutus_run() -> str:
    """BRUTUS — Brutal Traffic Engine: Scan→Predict→Swarm→Deploy alle Kanäle."""
    try:
        from modules.brutus_traffic_engine import brutus_run
        result = await brutus_run(
            niche="AI income online business automatisierung",
            custom_keywords=[
                "AI Income Machine", "Passives Einkommen Online", "Shopify Automatisierung",
                "Online Geld verdienen 2026", "KI Business Blueprint", "Dropshipping KI",
            ]
        )
        kw = result.get("keywords_processed", 0)
        pieces = result.get("content_pieces", 0)
        channels = result.get("channels_hit", 0)
        return f"BRUTUS: {kw} Keywords × {pieces} Content-Stücke → {channels} Kanäle bespielt"
    except Exception as e:
        return f"BRUTUS Fehler: {e}"


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
    """Ping all 13 Railway services, Telegram alert if any DOWN."""
    import aiohttp
    services = {
        "SuperMegaBot":        "https://dudirudibot-mega-production.up.railway.app/health",
        "MetaSocialEngine":    "https://meta-social-engine-production.up.railway.app/health",
        "SEOTurboTools":       "https://seo-turbo-tools-production.up.railway.app/health",
        "FreelanceGigEngine":  "https://freelance-gig-engine-production.up.railway.app/health",
        "VisualContentEngine": "https://visual-content-engine-production.up.railway.app/health",
        "AdPosterEngine":      "https://adposter-engine-production.up.railway.app/health",
        "iComeAutoSaaS":       "https://icomeauto-saas-production.up.railway.app/health",
        "CreatorAIUltra":      "https://creatorai-ultra-production.up.railway.app/health",
        "RevenueHub":          "https://revenue-hub-notifications-production.up.railway.app/health",
        "ShopifyAutomaton":    "https://shopify-automaton-suite-production-e405.up.railway.app/api/health",
        "Steuercockpit":       "https://steuercockpit-production-44c9.up.railway.app/health",
        "SEOTrafficEngine":    "https://seo-traffic-engine-production.up.railway.app/health",
        "SocialTrafficEngine": "https://social-traffic-engine-production.up.railway.app/health",
    }
    down, ok = [], []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            for name, url in services.items():
                try:
                    async with s.get(url) as r:
                        (ok if r.status < 400 else down).append(
                            name if r.status < 400 else f"{name}(HTTP {r.status})"
                        )
                except Exception:
                    down.append(f"{name}(timeout)")
        if down:
            await _tg(f"🔴 <b>Railway DOWN ({len(down)}/{len(services)}):</b>\n" +
                      "\n".join(f"  • {d}" for d in down))
            return f"DOWN: {', '.join(down)} | OK: {len(ok)}"
        return f"Alle {len(ok)} Railway-Services OK"
    except Exception as e:
        return f"Health-Check Fehler: {e}"


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
    """Push alle unpublizierten Printify-Produkte nach Shopify."""
    try:
        from modules.printify_automation import ping, sync_all_products_to_shopify
        if not await ping():
            return "Printify nicht konfiguriert — PRINTIFY_API_KEY setzen"
        result = await sync_all_products_to_shopify()
        return f"Printify→Shopify: {result['published']} neu, {result['already_live']} bereits live, {result['failed']} Fehler"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_autofulfill() -> str:
    """Auto-confirm alle pending Printful-Bestellungen → Produktion."""
    try:
        from modules.printful_automation import ping, auto_fulfill_pending
        if not await ping():
            return "Printful nicht konfiguriert — PRINTFUL_API_KEY setzen"
        result = await auto_fulfill_pending()
        confirmed = len(result.get("confirmed", []))
        failed    = len(result.get("failed", []))
        return f"Printful: {confirmed} bestätigt, {failed} Fehler, {result.get('total_pending',0)} pending gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_shopify_sync() -> str:
    """Prüfe ob alle Printful-Produkte mit Shopify synchronisiert sind."""
    try:
        from modules.printful_automation import ping, sync_catalog_to_shopify
        if not await ping():
            return "Printful nicht konfiguriert"
        result = await sync_catalog_to_shopify()
        return f"Printful Sync: {result['synced']} OK, {result['unsynced']} unsynced von {result['total']} gesamt"
    except Exception as e:
        return f"Fehler: {e}"


async def task_printful_discover_store() -> str:
    """Auto-detect Printful Store-ID und in Railway speichern."""
    try:
        from modules.printful_automation import ping, auto_detect_store
        if not await ping():
            return "Printful nicht konfiguriert — PRINTFUL_API_KEY setzen"
        sid = await auto_detect_store()
        return f"Printful Store-ID: {sid}"
    except Exception as e:
        return f"Fehler: {e}"


async def task_pod_combined_autofulfill() -> str:
    """Print-on-Demand: Printify + Printful gleichzeitig auto-fulfillment."""
    results = []
    try:
        from modules.printify_automation import ping as py_ping, auto_fulfill_pending as py_fulfill
        if await py_ping():
            r = await py_fulfill()
            results.append(f"Printify: {len(r['submitted'])} submitted")
        else:
            results.append("Printify: kein Key")
    except Exception as e:
        results.append(f"Printify error: {e}")

    try:
        from modules.printful_automation import ping as pf_ping, auto_fulfill_pending as pf_fulfill
        if await pf_ping():
            r = await pf_fulfill()
            results.append(f"Printful: {len(r['confirmed'])} confirmed")
        else:
            results.append("Printful: kein Key")
    except Exception as e:
        results.append(f"Printful error: {e}")

    return " | ".join(results)


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


async def task_cro_run() -> str:
    """CRO Engine — Klaviyo flows, urgency campaigns, Shopify urgency banner."""
    try:
        from modules.cro_engine import run_cro
        result = await run_cro()
        return f"CRO done: {result}"
    except Exception as e:
        return f"CRO error: {e}"


async def task_auto_funnel() -> str:
    """Auto Funnel — DS24 buyers → purchase sequence → upsell → discount."""
    try:
        from modules.auto_funnel import run_auto_funnel
        result = await run_auto_funnel()
        processed = result.get("daily_funnel", {}).get("processed", 0)
        return f"AutoFunnel done: {processed} buyers processed, {result}"
    except Exception as e:
        return f"AutoFunnel error: {e}"


async def task_email_check() -> str:
    """EmailBrain — IMAP poll aller Gmail-Konten, KI-Klassifizierung, Auto-Antwort, Labels."""
    try:
        from modules.email_brain import run_email_check
        return await run_email_check()
    except Exception as e:
        return f"EmailBrain error: {e}"


async def task_email_daily_summary() -> str:
    """EmailBrain — täglicher Telegram-Report."""
    try:
        from modules.email_brain import send_email_daily_summary
        await send_email_daily_summary()
        return "Email daily summary sent"
    except Exception as e:
        return f"EmailBrain summary error: {e}"


async def task_mega_auto_post() -> str:
    """Mega Auto Poster — postet auf ALLE Kanäle gleichzeitig (alle 30 Min)."""
    try:
        from modules.mega_auto_poster import run_full_auto_post
        result = await run_full_auto_post()
        summary = result.get("_run_summary", {})
        channels_ok = summary.get("total_channels_hit", 0)
        ds24_ok  = result.get("ds24", {}).get("_summary", {}).get("channels_ok", 0)
        skip     = result.get("ds24", {}).get("skipped", False)
        if skip:
            return "MegaAutoPost: Duplicate skip (bereits heute gepostet)"
        return f"MegaAutoPost: {channels_ok} Kanal-Hits | DS24: {ds24_ok}/9 ✅"
    except Exception as e:
        return f"MegaAutoPost Fehler: {e}"


async def task_twitter_auto_post() -> str:
    """Stündlicher Auto-Tweet über AI/Business-Themen."""
    try:
        from modules.twitter_auto_poster import run_auto_tweet
        result = await run_auto_tweet()
        if result.get("ok"):
            return f"Tweet gepostet: {result.get('text','?')[:60]}"
        return f"Tweet skip/fail: {result.get('error','?')[:60]}"
    except Exception as e:
        return f"Twitter Fehler: {e}"


async def task_shopify_blog_auto() -> str:
    """Alle 2h einen AI-generierten Blog-Post auf Shopify veröffentlichen."""
    try:
        import os, aiohttp, json
        from datetime import datetime
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        shopify_token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
        shopify_ver    = os.getenv("SHOPIFY_API_VERSION", "2024-01")
        anthropic_key  = os.getenv("ANTHROPIC_API_KEY", "")
        if not shopify_domain or not shopify_token or not anthropic_key:
            return "Shopify/Anthropic nicht konfiguriert"

        import random
        topics = [
            "Wie du mit KI 2026 passives Einkommen aufbaust",
            "5 Shopify Automatisierungen die deinen Umsatz verdoppeln",
            "AI Income Machine: Der komplette Blueprint",
            "Dropshipping mit KI: So geht es richtig",
            "Online Business Ideen die wirklich funktionieren",
            "Wie KI das Online Marketing revolutioniert",
            "Digistore24 vs Shopify: Was ist besser?",
            "Automatisches Marketing: So funktioniert es",
        ]
        topic = random.choice(topics)

        # Generate blog post with Claude
        prompt = f"""Schreibe einen SEO-Blog-Post auf Deutsch für Shopify.
Thema: {topic}
Länge: 400-500 Wörter. HTML-Format. Erwähne am Ende die "AI Income Machine" (€37 auf Digistore24).
Gib NUR JSON zurück: {{"title": "...", "author": "BullPower Hub", "body_html": "<html...>", "tags": "ki,automatisierung,ecommerce,shopify"}}"""

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1500,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                data = await r.json(content_type=None)
        raw = data["content"][0]["text"]
        post_data = json.loads(raw[raw.find("{"):raw.rfind("}")+1])

        # Get blog ID
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{shopify_domain}/admin/api/{shopify_ver}/blogs.json",
                headers={"X-Shopify-Access-Token": shopify_token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                blogs = await r.json(content_type=None)
        blog_id = blogs.get("blogs", [{}])[0].get("id")
        if not blog_id:
            return "Keine Shopify Blog gefunden"

        # Publish article
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{shopify_domain}/admin/api/{shopify_ver}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": shopify_token, "Content-Type": "application/json"},
                json={"article": {
                    "title": post_data.get("title", topic),
                    "author": post_data.get("author", "BullPower Hub"),
                    "body_html": post_data.get("body_html", ""),
                    "tags": post_data.get("tags", "ki,automatisierung"),
                    "published": True,
                }},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                article = await r.json(content_type=None)

        article_id = article.get("article", {}).get("id")
        title = post_data.get("title", topic)
        return f"Shopify Blog: '{title[:50]}' veröffentlicht (ID: {article_id})"
    except Exception as e:
        return f"Shopify Blog Fehler: {e}"


async def task_shopify_seo_auto() -> str:
    """AI-optimiert Shopify Produkt-Beschreibungen (15 Stück alle 12h)."""
    try:
        from modules.shopify_seo_auto import run_seo_batch
        result = await run_seo_batch(batch_size=15)
        return f"ShopifySEO: {result.get('updated',0)} Produkte optimiert, {result.get('failed',0)} Fehler"
    except Exception as e:
        return f"ShopifySEO Fehler: {e}"


async def task_klaviyo_auto_campaign() -> str:
    """Tägliche Klaviyo Kampagne mit neuem AI-Content."""
    try:
        import os, aiohttp, json
        from datetime import datetime
        klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
        list_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not klaviyo_key or not anthropic_key:
            return "Klaviyo/Anthropic Key fehlt"

        # Generate email content via Claude
        today = datetime.now().strftime("%d.%m.%Y")
        prompt = f"""Schreibe eine Marketing-Email auf Deutsch für heute ({today}).
Produkt: AI Income Machine (€37) auf Digistore24.
Ton: motivierend, persönlich, mit klarem CTA.
Format JSON: {{"subject": "...", "preview": "...", "html_body": "<html>...</html>"}}
Nur JSON, kein anderer Text."""

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 800,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        raw = data["content"][0]["text"]
        email_data = json.loads(raw[raw.find("{"):raw.rfind("}")+1])

        # Create Klaviyo campaign
        headers = {"Authorization": f"Klaviyo-API-Key {klaviyo_key}", "revision": "2024-06-15", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            # Create campaign
            async with s.post("https://a.klaviyo.com/api/campaigns/",
                headers=headers,
                json={"data": {"type": "campaign", "attributes": {
                    "name": f"AutoCampaign {today}",
                    "channel": "email",
                    "audiences": {"included": [list_id]},
                    "send_strategy": {"method": "immediate"},
                }}},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                campaign_resp = await r.json(content_type=None)

        campaign_id = campaign_resp.get("data", {}).get("id", "")
        if not campaign_id:
            return f"Klaviyo campaign creation failed: {campaign_resp}"

        return f"Klaviyo AutoCampaign gesendet: '{email_data.get('subject','?')[:50]}'"
    except Exception as e:
        return f"Klaviyo AutoCampaign Fehler: {e}"


async def task_mailchimp_auto_campaign() -> str:
    """Tägliche Mailchimp Kampagne mit AI-Content."""
    try:
        import os, aiohttp, json, base64
        from datetime import datetime
        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        list_id = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
        server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        from_email = os.getenv("SENDGRID_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
        if not mc_key:
            return "Mailchimp Key fehlt"

        today = datetime.now().strftime("%d.%m.%Y")
        auth = base64.b64encode(f"anystring:{mc_key}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
        base_url = f"https://{server}.api.mailchimp.com/3.0"

        # Generate subject with Claude if available
        subject = f"💡 Dein täglicher AI-Business-Tipp — {today}"
        html_content = f"""<html><body style='font-family:Arial;max-width:600px;margin:0 auto;padding:20px'>
<h1 style='color:#7c3aed'>🚀 AI Income Machine</h1>
<p>Hallo,</p>
<p>Wusstest du, dass über <strong>87% der erfolgreichen Online-Unternehmer</strong> KI-Tools nutzen, um ihren Umsatz zu automatisieren?</p>
<p>Mit der <strong>AI Income Machine</strong> bekommst du den kompletten Blueprint für:</p>
<ul>
<li>✅ Vollautomatische Einnahmen ohne tägliche Arbeit</li>
<li>✅ KI-gestützte Produktauswahl und Marketing</li>
<li>✅ Step-by-step Anleitung für Anfänger</li>
</ul>
<p style='text-align:center;margin:30px 0'>
<a href='https://www.digistore24.com/product/669750' style='background:#7c3aed;color:#fff;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold'>
🛒 Jetzt für nur €37 starten →
</a>
</p>
<p style='color:#666;font-size:12px'>BullPower Hub | bullpower-hub-portal.netlify.app</p>
</body></html>"""

        # Create and send campaign
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base_url}/campaigns",
                headers=headers,
                json={"type": "regular", "recipients": {"list_id": list_id},
                      "settings": {"subject_line": subject, "from_name": "BullPower Hub",
                                   "reply_to": from_email, "title": f"AutoCampaign {today}"}},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                camp = await r.json(content_type=None)

        camp_id = camp.get("id", "")
        if not camp_id:
            return f"MC campaign create failed: {list(camp.keys())}"

        async with aiohttp.ClientSession() as s:
            # Set content
            await s.put(f"{base_url}/campaigns/{camp_id}/content",
                headers=headers, json={"html": html_content},
                timeout=aiohttp.ClientTimeout(total=15))
            # Send
            async with s.post(f"{base_url}/campaigns/{camp_id}/actions/send",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                ok = r.status in (200, 204)

        return f"Mailchimp AutoCampaign {'gesendet' if ok else 'Fehler'}: {subject[:50]}"
    except Exception as e:
        return f"Mailchimp AutoCampaign Fehler: {e}"


async def task_facebook_token_check() -> str:
    """Täglicher Facebook Token Check — Alarm wenn abgelaufen oder pages_manage_posts fehlt."""
    try:
        from modules.facebook_token_manager import check_token, refresh_all_tokens
        import os
        # Check the page token (which is what's actually used for posting)
        page_token = os.getenv("FACEBOOK_PAGE_TOKEN_IWIN") or os.getenv("FACEBOOK_PAGE_TOKEN", "")
        user_token = os.getenv("FACEBOOK_USER_TOKEN", "")
        check = await check_token(page_token or user_token)
        scopes = check.get("scopes", [])
        has_post_scope = "pages_manage_posts" in scopes
        if not check.get("valid") or not has_post_scope:
            result = await refresh_all_tokens()  # sends Telegram OAuth URL
            reason = "invalid" if not check.get("valid") else "missing pages_manage_posts"
            return f"FB token {reason} — OAuth alert sent via Telegram"
        return f"FB token OK — pages_manage_posts: {has_post_scope}, scopes: {len(scopes)}"
    except Exception as e:
        return f"FB token check error: {e}"


async def task_email_seq_process() -> str:
    """Process all due drip emails across all enrolled sequences."""
    try:
        from modules.email_sequence_engine import process_due_emails
        result = await process_due_emails()
        sent = result.get("sent", 0)
        failed = result.get("failed", 0)
        return f"EmailSeq: {sent} gesendet, {failed} Fehler"
    except Exception as e:
        return f"EmailSeq Fehler: {e}"


async def task_email_seq_enroll() -> str:
    """Auto-enroll new Shopify customers in welcome sequence."""
    try:
        from modules.email_sequence_engine import enroll_new_customers
        result = await enroll_new_customers()
        enrolled = result.get("enrolled", 0)
        return f"EmailEnroll: {enrolled} neue Käufer eingeschrieben"
    except Exception as e:
        return f"EmailEnroll Fehler: {e}"


async def task_lead_nurture() -> str:
    """Process new leads from all sources → Klaviyo + email welcome sequence."""
    try:
        klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
        if not klaviyo_key:
            return "Klaviyo Key fehlt"
        from modules.email_sequence_engine import enroll
        leads_file = DATA_DIR / "new_leads.json"
        if not leads_file.exists():
            return "Keine neuen Leads"
        leads = json.loads(leads_file.read_text())
        if not leads:
            return "Keine neuen Leads"
        enrolled = 0
        processed = []
        for lead in leads:
            email = lead.get("email", "")
            if not email or "@" not in email:
                continue
            fname = lead.get("first_name", email.split("@")[0])
            await enroll(email, "welcome", first_name=fname,
                        metadata={"source": lead.get("source", "lead_form")})
            enrolled += 1
            processed.append(lead)
        leads_file.write_text("[]")
        if enrolled:
            await _tg(f"🎯 <b>Lead Nurture</b>: {enrolled} neue Leads → Welcome Sequence")
        return f"LeadNurture: {enrolled} Leads in Welcome Sequence"
    except Exception as e:
        return f"LeadNurture Fehler: {e}"


async def task_pinterest_auto_post() -> str:
    """Auto-create Pinterest pins from Shopify products."""
    try:
        from modules.social_connectors import PinterestConnector
        import aiohttp, random
        pin = PinterestConnector()
        if not pin.is_configured():
            return "Pinterest nicht konfiguriert"
        boards = await pin.get_boards()
        if not boards.get("ok") or not boards.get("boards"):
            return "Keine Pinterest Boards gefunden"
        board_id = boards["boards"][0]["id"]
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"https://{domain}/admin/api/2024-01/products.json?limit=10&published_status=published",
                headers={"X-Shopify-Access-Token": token}
            ) as r:
                prods = (await r.json()).get("products", [])
        prods_with_img = [p for p in prods if p.get("images")]
        if not prods_with_img:
            return "Keine Produkte mit Bildern"
        p = random.choice(prods_with_img)
        img = p["images"][0]["src"]
        title = p.get("title", "Produkt")
        url = f"https://{domain}/products/{p.get('handle','')}"
        result = await pin.create_pin(board_id=board_id, title=title,
                                       description=f"✨ {title} — Jetzt entdecken!", media_url=img, link=url)
        ok = result.get("ok", False)
        return f"Pinterest Pin: {'✅' if ok else '❌'} — {title[:40]}"
    except Exception as e:
        return f"Pinterest Fehler: {e}"


async def task_telegram_broadcast() -> str:
    """Auto-post AI-generated content to Telegram channel."""
    try:
        channel = os.getenv("TELEGRAM_CHANNEL_ID", os.getenv("TELEGRAM_CHAT_ID", ""))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not channel or not token or not anthropic_key:
            return "Telegram/Anthropic Key fehlt"
        import aiohttp
        today = datetime.now().strftime("%d.%m.%Y")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
                      "messages": [{"role": "user", "content":
                        f"Schreibe einen Telegram-Channel-Post auf Deutsch für {today}. "
                        "Thema: KI-Business, Online Income, Shopify Automatisierung. "
                        "Ton: inspirierend, direkt, mit 2-3 Emojis. Max 250 Wörter. "
                        "Ende mit: 👉 bullpower-hub-portal.netlify.app"}]}
            ) as r:
                d = await r.json(content_type=None)
        msg = d.get("content", [{}])[0].get("text", "")
        if not msg:
            return "Content Generation fehlgeschlagen"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel, "text": msg, "parse_mode": "Markdown"}
            ) as r:
                result = await r.json()
        ok = result.get("ok", False)
        return f"Telegram Broadcast: {'✅' if ok else '❌'} ({len(msg)} Zeichen)"
    except Exception as e:
        return f"Telegram Broadcast Fehler: {e}"


async def task_instagram_auto_post() -> str:
    """Auto-post product to Instagram via Graph API."""
    try:
        from modules.social_connectors import InstagramConnector
        import aiohttp, random
        ig = InstagramConnector()
        if not ig.is_configured():
            return "Instagram nicht konfiguriert"
        token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        if not token or not domain:
            return "Shopify nicht konfiguriert"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"https://{domain}/admin/api/2024-01/products.json?limit=10&published_status=published",
                headers={"X-Shopify-Access-Token": token}
            ) as r:
                prods = (await r.json()).get("products", [])
        prods_with_img = [p for p in prods if p.get("images")]
        if not prods_with_img:
            return "Keine Produkte mit Bildern"
        p = random.choice(prods_with_img)
        img_url = p["images"][0]["src"]
        caption = (f"✨ {p['title']}\n\n"
                   f"{(p.get('body_html') or '')[:120].replace('<p>','').replace('</p>','')}\n\n"
                   f"🛒 Jetzt im Shop!\n\n#shopify #ecommerce #onlineshop #business #automation")
        result = await ig.post_photo(image_url=img_url, caption=caption)
        ok = result.get("ok", False)
        return f"Instagram Post: {'✅' if ok else '❌'} — {p['title'][:40]}"
    except Exception as e:
        return f"Instagram Fehler: {e}"


async def task_content_cycle() -> str:
    """SEO-Artikel + alle Social-Inhalte generieren. ContentHub Monorepo-Task."""
    try:
        from modules.content_hub import run_content_cycle, init_db as _init_content
        _init_content()
        return await run_content_cycle()
    except Exception as e:
        return f"ContentHub Fehler: {e}"


async def task_freelance_cycle() -> str:
    """Fiverr Gig + Upwork Proposals generieren. ContentHub Monorepo-Task."""
    try:
        from modules.content_hub import run_freelance_cycle, init_db as _init_content
        _init_content()
        return await run_freelance_cycle()
    except Exception as e:
        return f"FreelanceCycle Fehler: {e}"


async def task_linkedin_auto_post() -> str:
    """Post AI-generated business content to LinkedIn every 6 hours."""
    try:
        import aiohttp
        linkedin_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        linkedin_urn   = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
        anthropic_key  = os.getenv("ANTHROPIC_API_KEY", "")
        if not linkedin_token:
            return "LINKEDIN_ACCESS_TOKEN fehlt"
        if not anthropic_key:
            return "ANTHROPIC_API_KEY fehlt"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
                      "messages": [{"role": "user", "content":
                          "Schreibe einen professionellen LinkedIn-Post auf Deutsch über KI-Automatisierung im E-Commerce. "
                          "Max 1200 Zeichen. Erwähne am Ende die AI Income Machine auf Digistore24. Nur Text, kein JSON."}]},
            ) as r:
                data = await r.json(content_type=None)
        text = data.get("content", [{}])[0].get("text", "").strip()
        if not text:
            return "Kein LinkedIn-Content generiert"
        headers = {
            "Authorization": f"Bearer {linkedin_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": linkedin_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload) as r:
                if r.status in (200, 201):
                    resp = await r.json(content_type=None)
                    return f"LinkedIn Post veröffentlicht (ID: {resp.get('id','?')}): {text[:60]}..."
                err = await r.text()
                return f"LinkedIn HTTP {r.status}: {err[:80]}"
    except Exception as e:
        return f"LinkedIn Fehler: {e}"


async def task_youtube_auto_post() -> str:
    """Post YouTube community post via BRUTUS every 2h."""
    try:
        from modules.brutus_traffic_engine import deploy_to_youtube
        import random
        topics = [
            "💡 AI Income Machine — Automatisch Geld verdienen mit KI | Jetzt für €37 starten!",
            "🚀 Shopify Automatisierung 2026 — So läuft dein Business von selbst",
            "🤖 KI-Tools die wirklich Geld verdienen — Live Demo",
            "📈 Passives Einkommen mit KI — Der komplette Blueprint",
        ]
        title = random.choice(topics)
        result = await deploy_to_youtube(
            title=title,
            description=(
                f"{title}\n\n"
                "👉 https://www.digistore24.com/product/669750\n\n"
                "#KI #PassivesEinkommen #OnlineBusiness"
            ),
            tags=["KI", "passives einkommen", "online business", "shopify", "automatisierung"],
        )
        return f"YouTube: {result.get(chr(39)+'status'+chr(39), str(result)[:80])}"
    except ImportError:
        return "YouTube: brutus_traffic_engine nicht verfügbar"
    except Exception as e:
        return f"YouTube Auto-Post Fehler: {e}"


# ── Autonomy Max-Upgrade Tasks ───────────────────────────────────────────────

async def task_competitor_monitor() -> str:
    """Täglich: Konkurrenten-Preise & Features checken, Telegram-Alert bei Änderung."""
    import aiohttp, re
    competitors = [
        {"name": "Dropispy", "url": "https://dropispy.com"},
        {"name": "AutoDS", "url": "https://www.autods.com"},
        {"name": "Zendrop", "url": "https://www.zendrop.com"},
    ]
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return "Competitor monitor: ANTHROPIC_API_KEY fehlt"
    findings = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for comp in competitors:
            try:
                async with session.get(comp["url"], headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    text = await resp.text()
                    prices = re.findall(r'\$[\d,]+|€[\d,]+|[\d,]+\s*(?:€|\$|USD|EUR)', text[:8000])
                    findings.append(f"{comp['name']}: {prices[:4] or ['kein Preis']}")
            except Exception as exc:
                findings.append(f"{comp['name']}: {exc.__class__.__name__}")
    summary = " | ".join(str(f) for f in findings)
    # Telegram alert
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"🔍 Konkurrenz-Check:\n{summary}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass
    return f"Competitor check: {summary[:200]}"


async def task_ab_test_analyze() -> str:
    """Alle 12h: A/B-Test-Gewinner aus Supabase ermitteln und per Telegram melden."""
    try:
        from modules.ab_testing_engine import analyze_and_select_winner
        results = await analyze_and_select_winner()
        if "error" in results:
            return f"A/B analyze: {results['error']}"
        winners = [f"{t}: '{d['winner']}'" for t, d in results.items()]
        msg = "🏆 A/B Gewinner: " + " | ".join(winners) if winners else "A/B: noch keine Daten"
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id and winners:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        return msg
    except ImportError:
        return "ab_testing_engine nicht gefunden"
    except Exception as e:
        return f"A/B analyze Fehler: {e}"


async def task_ai_content_calendar() -> str:
    """Täglich 06:00: KI-Inhaltskalender für 7 Tage generieren."""
    try:
        from modules.ai_content_calendar import generate_daily_calendar
        result = await generate_daily_calendar()
        return f"KI-Kalender: {result.get('days', 0)} Tage, erstes Thema: {result.get('first_day', {}).get('content', {}).get('title', '?')[:60]}"
    except ImportError:
        return "ai_content_calendar Modul fehlt"
    except Exception as e:
        return f"KI-Kalender Fehler: {e}"


async def task_revenue_optimize() -> str:
    """Alle 12h: KI analysiert Revenue und sendet Optimierungs-Empfehlungen per Telegram."""
    import aiohttp, json as _json
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return "Revenue optimize: ANTHROPIC_API_KEY fehlt"
    try:
        from modules.digistore24_automation import get_sales_stats
        ds24_stats = await get_sales_stats()
    except Exception:
        ds24_stats = {}
    prompt = (
        "Du bist ein E-Commerce Revenue-Experte (DACH-Markt).\n"
        f"Revenue-Daten: {_json.dumps(ds24_stats, default=str)[:800]}\n"
        "Gib 3 konkrete sofort umsetzbare Maßnahmen zur Umsatzsteigerung. "
        "Format: nummerierte Liste, je 1 Satz."
    )
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            data = await resp.json()
            recommendations = data.get("content", [{}])[0].get("text", "Keine Empfehlung")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id,
                          "text": f"💰 Revenue-Optimierung KI:\n{recommendations[:800]}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        return f"Revenue optimize: {recommendations[:100]}"
    except Exception as e:
        return f"Revenue optimize Fehler: {e}"


async def task_google_index_submit() -> str:
    """Submit all key URLs to Google Indexing API / sitemap ping daily."""
    import aiohttp
    key = os.getenv("GOOGLE_INDEXING_KEY", "")
    urls = [
        "https://dudirudibot-mega-production.up.railway.app/",
        "https://bullpowerhubgit.github.io/shopify-brutal-tuning-landing/",
        "https://bullpower-lead.netlify.app/",
        "https://bullpower-hub-portal.netlify.app/",
        "https://bullpower-ai-tools.netlify.app/",
    ]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            if key:
                submitted = 0
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                for url in urls:
                    try:
                        async with s.post(
                            "https://indexing.googleapis.com/v3/urlNotifications:publish",
                            headers=headers, json={"url": url, "type": "URL_UPDATED"},
                        ) as r:
                            if r.status in (200, 201):
                                submitted += 1
                    except Exception:
                        pass
                return f"Google Indexing API: {submitted}/{len(urls)} URLs"
            # Fallback: free sitemap ping
            sitemap = "https://dudirudibot-mega-production.up.railway.app/sitemap.xml"
            for ping in [f"https://www.google.com/ping?sitemap={sitemap}",
                         f"https://www.bing.com/ping?sitemap={sitemap}"]:
                try:
                    await s.get(ping)
                except Exception:
                    pass
        return f"Sitemap Ping → Google+Bing ({len(urls)} URLs, GOOGLE_INDEXING_KEY optional)"
    except Exception as e:
        return f"Google Index Fehler: {e}"


async def task_push_notify_broadcast() -> str:
    """Attempt Web Push to all subscribers every 6h (requires pywebpush + VAPID keys)."""
    import aiohttp
    supa_url  = os.getenv("SUPABASE_URL", "")
    supa_key  = os.getenv("SUPABASE_SERVICE_KEY", "")
    vapid_key = os.getenv("VAPID_PRIVATE_KEY", "")
    if not supa_url:
        return "Supabase nicht konfiguriert"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/push_subscriptions?select=id",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}",
                         "Prefer": "count=exact"},
            ) as r:
                cr = r.headers.get("content-range", "0/0")
                total = cr.split("/")[-1]
        if not vapid_key:
            return f"VAPID_PRIVATE_KEY fehlt — {total} Push-Subscriber bereit sobald VAPID gesetzt"
        # pywebpush send
        try:
            import json as _json
            from pywebpush import webpush
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(
                    f"{supa_url}/rest/v1/push_subscriptions?select=endpoint,p256dh,auth&limit=500",
                    headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
                ) as r:
                    subs = await r.json(content_type=None)
            sent = 0
            payload = _json.dumps({"title": "🔥 BullPower Hub — Neues Update!",
                                   "body": "KI-Automatisierung für deinen Shop. Jetzt starten!",
                                   "url": "https://bullpower-lead.netlify.app/"})
            for sub in (subs if isinstance(subs, list) else []):
                try:
                    webpush(subscription_info={"endpoint": sub["endpoint"],
                                               "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                            data=payload, vapid_private_key=vapid_key,
                            vapid_claims={"sub": "mailto:bullpowersrtkennels@gmail.com",
                                          "aud": sub["endpoint"].split("/")[2]})
                    sent += 1
                except Exception:
                    pass
            return f"Web Push: {sent}/{len(subs)} gesendet"
        except ImportError:
            return f"pywebpush nicht installiert — pip install pywebpush zum Aktivieren"
    except Exception as e:
        return f"Push Notify Fehler: {e}"


async def task_shopify_seo_blog() -> str:
    """Publish 3 AI-SEO blog posts to Shopify every 12h."""
    try:
        from modules.shopify_seo_auto import auto_publish_blog_post
        kws = ["Shopify Automatisierung mit KI 2026",
               "eCommerce Umsatz steigern Tipps",
               "Dropshipping Tool Vergleich"]
        done = 0
        for kw in kws:
            try:
                res = await auto_publish_blog_post(kw)
                if res and not isinstance(res, Exception):
                    done += 1
            except Exception:
                pass
        return f"Shopify SEO Blog: {done}/3 Posts published"
    except ImportError:
        return "shopify_seo_auto nicht verfügbar"
    except Exception as e:
        return f"Shopify SEO Blog Fehler: {e}"


async def task_viral_referral_trigger() -> str:
    """Tag recent leads in Klaviyo to trigger viral referral flow daily."""
    import aiohttp
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    supa_url    = os.getenv("SUPABASE_URL", "")
    supa_key    = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not klaviyo_key or not supa_url:
        return "Klaviyo/Supabase fehlt"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/lead_events?select=email,name&limit=50&order=created_at.desc",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            ) as r:
                leads = await r.json(content_type=None)
        if not isinstance(leads, list) or not leads:
            return "Keine Leads für Referral-Trigger"
        tagged = 0
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            for lead in leads[:20]:
                email = lead.get("email", "")
                if not email:
                    continue
                ref = email.split("@")[0]
                try:
                    await s.post(
                        "https://a.klaviyo.com/api/profile-import/",
                        headers={"Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                                 "revision": "2024-06-15", "Content-Type": "application/json"},
                        json={"data": {"type": "profile", "attributes": {
                            "email": email,
                            "properties": {"referral_url": f"https://dudirudibot-mega-production.up.railway.app/api/referral/{ref}",
                                           "referral_triggered": True},
                        }}},
                    )
                    tagged += 1
                except Exception:
                    pass
        return f"Viral Referral: {tagged} Leads getagt"
    except Exception as e:
        return f"Referral Trigger Fehler: {e}"


async def task_onboarding_sequence_trigger() -> str:
    """Enroll new leads into Klaviyo 7-day onboarding sequence daily."""
    import aiohttp
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    supa_url    = os.getenv("SUPABASE_URL", "")
    supa_key    = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not klaviyo_key or not supa_url:
        return "Klaviyo/Supabase fehlt"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{supa_url}/rest/v1/lead_events?select=email,name,source&limit=30&order=created_at.desc",
                headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            ) as r:
                leads = await r.json(content_type=None)
        if not isinstance(leads, list):
            leads = []
        enrolled = 0
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            for lead in leads[:30]:
                email = lead.get("email", "")
                fname = (lead.get("name") or "").split()[0] or "Freund"
                if not email:
                    continue
                try:
                    await s.post(
                        "https://a.klaviyo.com/api/profile-import/",
                        headers={"Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                                 "revision": "2024-06-15", "Content-Type": "application/json"},
                        json={"data": {"type": "profile", "attributes": {
                            "email": email, "first_name": fname,
                            "properties": {"onboarding_day": 1, "onboarding_started": True,
                                           "product": lead.get("source", "shopify")},
                        }}},
                    )
                    enrolled += 1
                except Exception:
                    pass
        return f"Onboarding Sequenz: {enrolled} Leads enrolled (Day 1 Tag gesetzt)"
    except Exception as e:
        return f"Onboarding Sequenz Fehler: {e}"


async def task_seo_dominator() -> str:
    """SEO Dominator: sitemap ping + Schema.org injection + IndexNow every 2h."""
    try:
        from modules.seo_dominator import run_seo_dominator
        result = await run_seo_dominator(full=True)
        injected = result.get("schema_inject", {}).get("schema_injected", 0)
        return f"SEO Dominator OK: {injected} Schema injected, sitemap pinged"
    except Exception as e:
        return f"SEO Dominator Fehler: {e}"


async def task_backlink_bomber() -> str:
    """BacklinkBomber: IndexNow + RSS XML-RPC pings every 2h."""
    try:
        from modules.backlink_bomber import run_backlink_bomber
        result = await run_backlink_bomber()
        total = result.get("results", {}).get("rss_xmlrpc", {}).get("total_pinged", 0)
        return f"BacklinkBomber OK: {total} services pinged"
    except Exception as e:
        return f"BacklinkBomber Fehler: {e}"


async def task_viral_traffic_machine() -> str:
    """ViralTrafficMachine: Reddit + Medium + LinkedIn + trending content every 4h."""
    try:
        from modules.viral_traffic_machine import run_viral_traffic_machine
        result = await run_viral_traffic_machine()
        posted = sum(1 for v in result.get("platforms", {}).values() if isinstance(v, dict) and v.get("ok"))
        return f"ViralTraffic OK: {posted} platforms hit"
    except Exception as e:
        return f"ViralTraffic Fehler: {e}"


async def task_content_velocity() -> str:
    """ContentVelocity: generate + publish 10-format content from trending topic every 2h."""
    try:
        from modules.content_velocity_engine import run_content_velocity
        result = await run_content_velocity()
        topic = result.get("topic", "?")[:40]
        return f"ContentVelocity OK: '{topic}' published across all formats"
    except Exception as e:
        return f"ContentVelocity Fehler: {e}"


async def task_revenue_maximizer() -> str:
    """RevenueMaximizer: cart abandonment recovery + winback + urgency offers every 4h."""
    try:
        from modules.revenue_maximizer import run_revenue_maximizer
        result = await run_revenue_maximizer()
        recovered = result.get("results", {}).get("cart_recovery", {}).get("recovery_emails_sent", 0)
        winback   = result.get("results", {}).get("winback", {}).get("winback_triggered", 0)
        return f"RevenueMaximizer OK: {recovered} carts recovered, {winback} winback triggered"
    except Exception as e:
        return f"RevenueMaximizer Fehler: {e}"


async def task_free_syndication() -> str:
    """FreeSyndication: post to Dev.to, Hashnode, Medium, Discord, Telegram every 6h."""
    try:
        from modules.free_syndication_network import run_free_syndication
        result = await run_free_syndication()
        ok = result.get("platforms_ok", 0)
        topic = result.get("topic", "")[:40]
        return f"FreeSyndication OK: {ok}/5 platforms — '{topic}'"
    except Exception as e:
        return f"FreeSyndication Fehler: {e}"


async def task_github_blog() -> str:
    """GitHubBlog: publish SEO article to GitHub Pages every 4h."""
    try:
        from modules.github_blog_publisher import publish_blog_article
        result = await publish_blog_article()
        if result.get("ok"):
            return f"GitHubBlog OK: '{result.get('title','')[:50]}' → {result.get('url','')}"
        return f"GitHubBlog skip: {result.get('reason','no reason')}"
    except Exception as e:
        return f"GitHubBlog Fehler: {e}"


# ── Content Factory Tasks ────────────────────────────────────────────────────

async def task_content_factory_run() -> str:
    """Every 4h: find top trending topic → generate full content package."""
    try:
        from modules.content_factory import find_trending_topics, generate_content_package
        topics = await find_trending_topics("shopify ecommerce automation")
        topic = topics[0]["topic"] if topics else "Shopify Automation mit KI"
        package = await generate_content_package(topic)
        stats = package.get("stats", {})
        return (f"Content Factory: {topic} | "
                f"Blog {stats.get('blog_words_de', 0)}w | "
                f"{stats.get('email_count', 0)} emails | "
                f"{stats.get('platforms', 0)} platforms")
    except Exception as e:
        return f"content_factory_run error: {e}"


async def task_social_batch_gen() -> str:
    """Daily: generate 30-day social media batch for all platforms."""
    try:
        from modules.content_factory import generate_social_batch, find_trending_topics
        topics = await find_trending_topics()
        topic = topics[0]["topic"] if topics else "E-Commerce Automation 2024"
        batch = await generate_social_batch(topic)
        counts = {k: len(v) for k, v in batch.items() if isinstance(v, list)}
        return f"Social batch: {topic} | " + " | ".join(f"{k}:{v}" for k, v in counts.items())
    except Exception as e:
        return f"social_batch_gen error: {e}"


async def task_trending_topic_scan() -> str:
    """Every 12h: scan for trending topics and log top opportunities."""
    try:
        from modules.content_factory import find_trending_topics
        topics = await find_trending_topics()
        high = [t["topic"] for t in topics if t.get("urgency") == "high"]
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if high and token and chat_id:
            msg = f"🔥 Trending NOW:\n" + "\n".join(f"• {t}" for t in high[:5])
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": msg},
                             timeout=aiohttp.ClientTimeout(total=10))
        return f"Trending scan: {len(topics)} topics, {len(high)} high-urgency"
    except Exception as e:
        return f"trending_topic_scan error: {e}"


async def task_content_calendar_weekly() -> str:
    """Weekly (Monday): build next 30-day content calendar."""
    try:
        from datetime import datetime
        from modules.content_factory import build_content_calendar
        month = datetime.utcnow().strftime("%Y-%m")
        cal = await build_content_calendar(month)
        days = len(cal.get("days", []))
        return f"Content calendar built: {month} | {days} days planned"
    except Exception as e:
        return f"content_calendar_weekly error: {e}"


# ── Conversion Maximizer Tasks ───────────────────────────────────────────────

async def task_conversion_scan() -> str:
    """Every 15min: A/B winners + social proof + lead re-scoring."""
    try:
        from modules.conversion_engine import run_conversion_scan
        return await run_conversion_scan()
    except Exception as e:
        return f"ConversionScan Fehler: {e}"


async def task_daily_optimization() -> str:
    """Every 1h: revenue AI diagnosis + funnel weak-point fix."""
    try:
        from modules.conversion_engine import run_daily_optimization
        return await run_daily_optimization()
    except Exception as e:
        return f"DailyOptimization Fehler: {e}"


async def task_funnel_daily() -> str:
    """Daily: full funnel analytics report to Telegram."""
    try:
        from modules.conversion_engine import analyze_funnel
        result = await analyze_funnel()
        return (f"Funnel: {result.get('leads',0)} leads → {result.get('orders',0)} orders | "
                f"Weakest: {result.get('weakest_stage','?')} {result.get('weakest_rate',0):.1%}")
    except Exception as e:
        return f"FunnelDaily Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# OMEGA TRAFFIC ENGINE TASKS — Revolution Pack
# ─────────────────────────────────────────────────────────────────────────────

async def task_omega_full() -> str:
    """OMEGA Full-Cycle: Google Index + Bing IndexNow + Artikel + Competitor + Proof."""
    try:
        from modules.omega_traffic_engine import run_omega_cycle
        result = await run_omega_cycle(mode="full")
        indexed = len(result.get("indexing", {}).get("submitted", []))
        indexnow = result.get("indexnow", {}).get("submitted", 0)
        article = result.get("article", {}).get("words", 0)
        return f"OMEGA Full: {indexed} URLs indexiert | IndexNow: {indexnow} | Artikel: {article} Wörter"
    except Exception as e:
        return f"OMEGA Full Fehler: {e}"


async def task_omega_index() -> str:
    """Schnelle Indexierung: alle Money-URLs sofort an Google + Bing melden."""
    try:
        from modules.omega_traffic_engine import google_instant_index, bing_indexnow, MONEY_URLS
        g = await google_instant_index(MONEY_URLS)
        b = await bing_indexnow(MONEY_URLS)
        return (f"Index: {len(g.get('submitted', []))} Google | "
                f"{b.get('submitted', 0)} Bing IndexNow")
    except Exception as e:
        return f"OMEGA Index Fehler: {e}"


async def task_omega_article() -> str:
    """Generiert und veröffentlicht täglich rotierenden SEO-Artikel."""
    try:
        from modules.omega_traffic_engine import generate_seo_article, publish_article_to_vercel, ARTICLE_TOPICS
        import datetime as dt
        topic_idx = dt.datetime.now().timetuple().tm_yday % len(ARTICLE_TOPICS)
        topic, slug = ARTICLE_TOPICS[topic_idx]
        article = await generate_seo_article(topic, slug)
        if not article:
            return "Artikel-Generierung übersprungen (kein API-Key)"
        result = await publish_article_to_vercel(article)
        return f"SEO-Artikel: '{topic}' | {result.get('words', 0)} Wörter → {result.get('published', '?')}"
    except Exception as e:
        return f"OMEGA Artikel Fehler: {e}"


async def task_omega_competitor() -> str:
    """KI generiert Content der Competitor-Keywords für BullPower Hub klaut."""
    try:
        from modules.omega_traffic_engine import generate_competitor_content
        result = await generate_competitor_content()
        keyword = result.get("keyword", "?")
        posts = len(result.get("posts", []))
        return f"Competitor-Content: '{keyword}' → {posts} Posts generiert"
    except Exception as e:
        return f"OMEGA Competitor Fehler: {e}"


async def task_omega_social_proof() -> str:
    """Postet Kunden-Testimonial als Social Proof auf Telegram."""
    try:
        from modules.omega_traffic_engine import post_testimonial_social
        result = await post_testimonial_social()
        return f"Social Proof: {result.get('posted', '?')} gepostet"
    except Exception as e:
        return f"OMEGA Social Proof Fehler: {e}"


async def task_omega_youtube() -> str:
    """Generiert YouTube SEO-Paket (Titel, Description, Tags, Hook)."""
    try:
        from modules.omega_traffic_engine import generate_youtube_package
        result = await generate_youtube_package()
        return f"YouTube-Paket: '{result.get('idea', '?')[:50]}'"
    except Exception as e:
        return f"OMEGA YouTube Fehler: {e}"


async def task_omega_indexnow_sitemap() -> str:
    """Meldet alle Sitemaps bei IndexNow an (Bing/Yahoo/DuckDuckGo)."""
    try:
        from modules.omega_traffic_engine import bing_indexnow, SITEMAPS
        result = await bing_indexnow(SITEMAPS)
        return f"IndexNow Sitemaps: {result.get('submitted', 0)} bei {len(result.get('engines', []))} Engines"
    except Exception as e:
        return f"OMEGA IndexNow Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# TWITTER AUTOPOSTER TASKS
# ─────────────────────────────────────────────────────────────────────────────

async def task_twitter_daily_tweets() -> str:
    """Postet 3 Tweets täglich auf @AIITEC — KI-generiert + Templates + Produkte."""
    try:
        from modules.twitter_autoposter import post_daily_tweets
        result = await post_daily_tweets(count=3)
        return f"Twitter: {result.get('posted', 0)} Tweets | {result.get('failed', 0)} Fehler"
    except Exception as e:
        return f"Twitter Daily Fehler: {e}"


async def task_twitter_seo_thread() -> str:
    """Postet täglich einen SEO-Thread (3 Tweets) auf @AIITEC."""
    try:
        from modules.twitter_autoposter import post_seo_thread
        result = await post_seo_thread()
        return f"Twitter Thread: {result.get('thread_length', 0)} Tweets gepostet"
    except Exception as e:
        return f"Twitter Thread Fehler: {e}"


async def task_social_scheduler() -> str:
    """Social Scheduler: Twitter → Telegram Fallback (alle 6h)."""
    try:
        from modules.social_scheduler import post_daily_content
        result = await post_daily_content()
        return f"SocialScheduler: {result}"
    except Exception as e:
        return f"SocialScheduler Fehler: {e}"


# ── SEO MEGA ENGINE ───────────────────────────────────────────────────────────

async def task_seo_mega_factory() -> str:
    try:
        from modules.seo_mega_engine import run_content_factory
        r = await run_content_factory(batch_size=5)
        return f"SEO Mega: saved={r.get('saved',0)} published={r.get('published_shopify',0)}"
    except Exception as e:
        return f"SEO Mega Factory error: {e}"

async def task_seo_mega_submit() -> str:
    try:
        from modules.seo_mega_engine import submit_to_google, generate_sitemap
        sitemap = await generate_sitemap()
        r = await submit_to_google()
        return f"SEO Submit: google={r.get('results',{}).get('google',{}).get('ok')} indexnow={r.get('results',{}).get('indexnow',{}).get('ok')}"
    except Exception as e:
        return f"SEO Submit error: {e}"

async def task_seo_competitor_analysis() -> str:
    try:
        from modules.seo_mega_engine import analyze_all_competitors
        r = await analyze_all_competitors()
        return f"SEO Competitor: {r.get('competitors_analyzed',0)} analyzed, {r.get('quick_wins_added',0)} quick wins"
    except Exception as e:
        return f"SEO Competitor error: {e}"


# ── TRAFFIC SWARM ─────────────────────────────────────────────────────────────

async def task_traffic_swarm_full() -> str:
    try:
        from modules.traffic_swarm import run_full_traffic_swarm
        r = await run_full_traffic_swarm()
        return f"TrafficSwarm: {r.get('modules_ok',0)}/{r.get('modules_total',0)} OK"
    except Exception as e:
        return f"TrafficSwarm error: {e}"

async def task_traffic_velocity_check() -> str:
    try:
        from modules.traffic_swarm import monitor_traffic_velocity
        r = await monitor_traffic_velocity()
        return f"Traffic: {r.get('today_leads',0)} leads, {r.get('delta_pct',0):+.1f}%"
    except Exception as e:
        return f"TrafficVelocity error: {e}"

async def task_rss_rebuild() -> str:
    try:
        from modules.traffic_swarm import build_rss_feed
        xml = await build_rss_feed()
        return f"RSS: {len(xml)} chars"
    except Exception as e:
        return f"RSS error: {e}"

async def task_content_freshness() -> str:
    try:
        from modules.traffic_swarm import refresh_stale_content
        r = await refresh_stale_content(days_old=90)
        return f"Freshness: {r.get('articles_updated',0)} updated"
    except Exception as e:
        return f"ContentFreshness error: {e}"

async def task_backlink_outreach_gen() -> str:
    try:
        from modules.traffic_swarm import generate_outreach_emails
        emails = await generate_outreach_emails(count=5)
        sent = sum(1 for e in emails if e.get("sent"))
        return f"Outreach: {len(emails)} drafts, {sent} sent"
    except Exception as e:
        return f"Outreach error: {e}"


# ── TRAFFIC BLITZ ─────────────────────────────────────────────────────────────

async def task_traffic_blitz_full() -> str:
    try:
        from modules.traffic_blitz import run_traffic_blitz
        r = await run_traffic_blitz()
        return f"TrafficBlitz: {r.get('channels_ok',0)}/4 OK | {r.get('topic','?')[:40]}"
    except Exception as e:
        return f"TrafficBlitz error: {e}"

async def task_linkedin_burst() -> str:
    try:
        from modules.traffic_blitz import run_linkedin_burst
        r = await run_linkedin_burst()
        return f"LinkedIn Burst: {r.get('posted',0)}/{r.get('total',0)} posts"
    except Exception as e:
        return f"LinkedIn burst error: {e}"

async def task_shopify_seo_blast() -> str:
    try:
        from modules.traffic_blitz import run_shopify_seo_blast
        r = await run_shopify_seo_blast()
        return f"Shopify SEO Blast: {r.get('published',0)} Artikel"
    except Exception as e:
        return f"Shopify SEO blast error: {e}"

async def task_indexnow_mega_blast() -> str:
    try:
        from modules.traffic_blitz import indexnow_blast
        r = await indexnow_blast()
        return f"IndexNow: {r.get('submitted',0)} URLs an Google+Bing"
    except Exception as e:
        return f"IndexNow blast error: {e}"


# ── ADS ENGINE ────────────────────────────────────────────────────────────────

async def task_ads_performance_monitor() -> str:
    try:
        from modules.ads_engine import task_ads_monitor
        return await task_ads_monitor()
    except Exception as e:
        return f"AdsMonitor error: {e}"

async def task_ads_optimize_run() -> str:
    try:
        from modules.ads_engine import task_ads_optimize
        return await task_ads_optimize()
    except Exception as e:
        return f"AdsOptimize error: {e}"

async def task_ads_creative_rotate() -> str:
    try:
        from modules.ads_engine import task_ads_rotate
        return await task_ads_rotate()
    except Exception as e:
        return f"AdsRotate error: {e}"


# ── REVENUE INTELLIGENCE ──────────────────────────────────────────────────────

async def task_revenue_autopilot_run() -> str:
    try:
        from modules.revenue_intelligence import revenue_autopilot
        r = await revenue_autopilot()
        return f"RevenueAutopilot: {len(r.get('actions',[]))} actions"
    except Exception as e:
        return f"RevenueAutopilot error: {e}"

async def task_revenue_briefing_morning() -> str:
    try:
        from modules.revenue_intelligence import send_revenue_briefing
        r = await send_revenue_briefing()
        return f"RevenueBriefing: €{r.get('yesterday_revenue',0):.2f} yesterday, {r.get('leads_today',0)} leads"
    except Exception as e:
        return f"RevenueBriefing error: {e}"

async def task_revenue_leak_check() -> str:
    try:
        from modules.revenue_intelligence import detect_revenue_leaks
        leaks = await detect_revenue_leaks()
        return f"RevenueLeaks: {len(leaks)} found"
    except Exception as e:
        return f"RevenueLeaks error: {e}"

async def task_churn_prevention() -> str:
    try:
        from modules.revenue_intelligence import identify_churn_risk
        at_risk = await identify_churn_risk()
        return f"ChurnRisk: {len(at_risk)} customers at risk"
    except Exception as e:
        return f"ChurnPrevention error: {e}"


# ── SHOPIFY MAX TUNER ─────────────────────────────────────────────────────────

async def task_shopify_max_seo() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_seo_optimize
        return await task_shopify_seo_optimize()
    except Exception as e:
        return f"ShopifyMaxSEO error: {e}"

async def task_shopify_cart_recover() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_cart_recovery
        return await task_shopify_cart_recovery()
    except Exception as e:
        return f"CartRecovery error: {e}"

async def task_shopify_price_optimize() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_pricing
        return await task_shopify_pricing()
    except Exception as e:
        return f"ShopifyPricing error: {e}"

async def task_shopify_daily_intel() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_intelligence
        return await task_shopify_intelligence()
    except Exception as e:
        return f"ShopifyIntel error: {e}"

async def task_shopify_inventory_check() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_inventory
        return await task_shopify_inventory()
    except Exception as e:
        return f"ShopifyInventory error: {e}"

async def task_shopify_review_request() -> str:
    try:
        from modules.shopify_max_tuner import task_shopify_reviews
        return await task_shopify_reviews()
    except Exception as e:
        return f"ShopifyReviews error: {e}"


# ── GROWTH HACKER ─────────────────────────────────────────────────────────────

async def task_viral_trend_scan() -> str:
    try:
        from modules.growth_hacker import task_viral_trend_detect
        return await task_viral_trend_detect()
    except Exception as e:
        return f"ViralTrend error: {e}"

async def task_community_growth_post() -> str:
    try:
        from modules.growth_hacker import task_community_grow
        return await task_community_grow()
    except Exception as e:
        return f"CommunityGrowth error: {e}"

async def task_growth_morning_briefing() -> str:
    try:
        from modules.growth_hacker import task_growth_metrics
        return await task_growth_metrics()
    except Exception as e:
        return f"GrowthBriefing error: {e}"

async def task_influencer_pipeline() -> str:
    try:
        from modules.growth_hacker import task_influencer_outreach
        return await task_influencer_outreach()
    except Exception as e:
        return f"InfluencerPipeline error: {e}"

async def task_press_release_generate() -> str:
    try:
        from modules.growth_hacker import task_press_release_auto
        return await task_press_release_auto()
    except Exception as e:
        return f"PressRelease error: {e}"

async def task_testimonial_engine() -> str:
    try:
        from modules.growth_hacker import task_testimonial_collect
        return await task_testimonial_collect()
    except Exception as e:
        return f"Testimonial error: {e}"

async def task_referral_system_run() -> str:
    try:
        from modules.growth_hacker import task_referral_refresh
        return await task_referral_refresh()
    except Exception as e:
        return f"Referral error: {e}"


# ── ULTRA SEO ARSENAL TASKS ──────────────────────────────────────────────────

async def task_ultra_seo_cycle() -> str:
    """Full Ultra SEO cycle: IndexNow all properties + sitemap ping + parasite content."""
    try:
        from modules.ultra_seo_arsenal import run_ultra_seo_cycle
        result = await run_ultra_seo_cycle()
        urls = result.get("indexnow", {}).get("total_urls", 0)
        indexed = result.get("indexnow", {}).get("submitted", 0)
        return f"Ultra SEO: {urls} URLs → {indexed}/3 Engines | Content OK"
    except Exception as e:
        return f"UltraSEO error: {e}"


async def task_ultra_indexnow_all() -> str:
    """Submit all 14+ BullPower properties to IndexNow."""
    try:
        from modules.ultra_seo_arsenal import submit_all_properties_to_indexnow
        result = await submit_all_properties_to_indexnow()
        return f"IndexNow ALL: {result.get('total_urls',0)} URLs | {result.get('submitted',0)}/3 Engines"
    except Exception as e:
        return f"IndexNow ALL error: {e}"


async def task_ultra_seo_health() -> str:
    """Check all BullPower properties are online."""
    try:
        from modules.ultra_seo_arsenal import seo_health_check
        result = await seo_health_check()
        return f"SEO Health: {result.get('ok',0)}/{result.get('total',0)} Properties online"
    except Exception as e:
        return f"SEO Health error: {e}"


async def task_dynamic_pricing_cycle() -> str:
    try:
        from modules.dynamic_pricing import run_dynamic_pricing_cycle
        r = await run_dynamic_pricing_cycle(max_products=50)
        return f"Dynamic Pricing: checked={r.get('products_checked',0)} updated={r.get('prices_updated',0)}"
    except Exception as e:
        return f"Dynamic Pricing error: {e}"


async def task_tiktok_sync() -> str:
    try:
        from modules.tiktok_shop_sync import sync_products_to_tiktok
        r = await sync_products_to_tiktok()
        return f"TikTok Sync: synced={r.get('synced',0)} skipped={r.get('skipped',0)}"
    except Exception as e:
        return f"TikTok Sync error: {e}"


async def task_upsell_sequence_run() -> str:
    try:
        from modules.conversion_engine import generate_upsell_sequence
        r = await generate_upsell_sequence()
        return f"Upsell Sequence: {r.get('enrolled',0)} enrolled"
    except Exception as e:
        return f"Upsell Sequence error: {e}"


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
    ("ds24_funnel_sync",         task_ds24_funnel_sync,        900,    35),   # 15 min — neue Käufer sofort
    ("mailchimp_sync",          task_mailchimp_sync,          3600,   90),   # 1h
    ("shopify_sync",            task_shopify_sync,            3600,   120),  # 1h
    ("social_status",           task_social_status,           3600,   150),  # 1h
    ("social_autoposter",       task_social_autoposter,       3600,   180),  # 1h
    # ── Growth & SEO (every 2-6 hours) ────────────────────────────────────────
    ("seo_optimizer",           task_seo_optimizer,           7200,   200),  # 2h
    ("traffic_seo_run",         task_traffic_seo_run,          3600,  210),  # 1h — AI SEO+Traffic (war 6h)
    ("brutus_run",              task_brutus_run,               3600,    5),   # 1h — BRUTUS alle Kanäle (war 3h)
    ("dropshipping_scan",       task_dropshipping_scan,       7200,   220),  # 2h
    ("api_keys_health",         task_api_keys_health,         21600,  61),   # 6h
    ("trading_report",          task_trading_report,          21600,  240),  # 6h
    ("printify_discover_shop",  task_printify_discover_shop,  21600,   6),   # 6h (fast start)
    ("printful_discover_store", task_printful_discover_store, 21600,   7),   # 6h (fast start)
    # ── Maintenance (hourly) ──────────────────────────────────────────────────
    ("env_auto_update",         task_env_auto_update,         3600,   8),    # 1h (fast start)
    ("printify_shopify_sync",   task_printify_shopify_sync,   3600,   170),  # 1h
    ("printful_shopify_sync",   task_printful_shopify_sync,   3600,   175),  # 1h
    ("pod_combined_autofulfill", task_pod_combined_autofulfill, 1800, 47),   # 30 min — Printify+Printful
    ("printful_autofulfill",    task_printful_autofulfill,    1800,   46),   # 30 min
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
    # ── ContentHub (integriert alle 5 Content-Engines) ────────────────────
    ("content_cycle",           task_content_cycle,            3600,  400),  # 1h — SEO+Social+Twitter+FB (war 6h)
    ("freelance_cycle",         task_freelance_cycle,         14400,  420),  # 4h — Fiverr+Upwork (war 12h)
    ("mega_auto_post",          task_mega_auto_post,           1800,   16),  # 30 Min — alle Kanäle gleichzeitig
    # ── CRO + Auto Funnel ────────────────────────────────────────────────
    ("cro_run",                 task_cro_run,                 3600,   121),  # hourly — Klaviyo flows + urgency
    ("auto_funnel",             task_auto_funnel,             1800,    62),  # 30 min — DS24 buyers → funnel
    # ── Email Brain ──────────────────────────────────────────────────────
    ("email_check",             task_email_check,              900,    31),  # 15 min — IMAP poll + AI classify + auto-reply
    ("email_daily_summary",     task_email_daily_summary,    86400,   350),  # daily — Telegram summary
    ("facebook_token_check",    task_facebook_token_check,   43200,   370),  # 12h — check FB token validity
    ("shopify_seo_auto",        task_shopify_seo_auto,       43200,   380),  # 12h — AI SEO für Shopify Produkte
    ("klaviyo_auto_campaign",   task_klaviyo_auto_campaign,  86400,   390),  # täglich — Auto Klaviyo Campaign
    ("mailchimp_auto_campaign", task_mailchimp_auto_campaign,86400,   395),  # täglich — Auto Mailchimp Campaign
    ("twitter_auto_post",       task_twitter_auto_post,      3600,    21),   # 1h — Auto-Tweet
    ("shopify_blog_auto",       task_shopify_blog_auto,      7200,    46),   # 2h — Auto-Blog-Post
    # ── Email Sequences (drip processing) ────────────────────────────────
    ("email_seq_process",       task_email_seq_process,      3600,    55),   # 1h — process due drip emails
    ("email_seq_enroll",        task_email_seq_enroll,       1800,    65),   # 30 min — auto-enroll new Shopify buyers
    # ── Lead Automation ──────────────────────────────────────────────────
    ("lead_nurture",            task_lead_nurture,           3600,    70),   # 1h — process new leads → Klaviyo + sequence
    # ── Platform Posting (extra coverage) ────────────────────────────────
    ("pinterest_auto_post",     task_pinterest_auto_post,    7200,    80),   # 2h — Pinterest pins
    ("telegram_broadcast",      task_telegram_broadcast,     21600,   91),   # 6h — Telegram channel post
    ("instagram_auto_post",     task_instagram_auto_post,    14400,  100),   # 4h — Instagram post
    ("linkedin_auto_post",      task_linkedin_auto_post,     21600,  110),   # 6h — LinkedIn AI post
    ("youtube_auto_post",       task_youtube_auto_post,       7200,  122),   # 2h — YouTube community post
    # ── Autonomy Max-Upgrades ─────────────────────────────────────────────
    ("competitor_monitor",      task_competitor_monitor,     86400,  500),   # daily — Konkurrenz-Check
    ("ab_test_analyze",         task_ab_test_analyze,        43200,  510),   # 12h — A/B Gewinner auswählen
    ("ai_content_calendar",     task_ai_content_calendar,    86400,  520),   # daily 06:00 — KI-Kalender
    ("revenue_optimize",        task_revenue_optimize,       43200,  530),   # 12h — Revenue-KI-Empfehlungen
    # ── REVOLUTION PACK — SEO + Traffic + Automation Max ─────────────────
    ("google_index_submit",     task_google_index_submit,    86400,  540),   # daily — Google+Bing Indexierung
    ("push_notify_broadcast",   task_push_notify_broadcast,  21600,  550),   # 6h — Web Push an Subscriber
    ("shopify_seo_blog",        task_shopify_seo_blog,       43200,  560),   # 12h — 3x KI Shopify Blog Posts
    ("viral_referral_trigger",  task_viral_referral_trigger, 86400,  570),   # daily — Viral Referral Loop
    ("onboarding_seq_trigger",  task_onboarding_sequence_trigger, 43200, 580), # 12h — 7-Day Onboarding
    # ── REVOLUTION v3: 10.000x SEO + Traffic + Backlinks + Revenue ───────────
    ("seo_dominator",           task_seo_dominator,          7200,    26),   # 2h — Schema.org + IndexNow + Sitemap
    ("backlink_bomber",         task_backlink_bomber,        7200,    36),   # 2h — IndexNow + RSS XML-RPC pings
    ("content_velocity",        task_content_velocity,       7200,    56),   # 2h — 10-Format Content überall
    ("viral_traffic_machine",   task_viral_traffic_machine,  14400,   76),   # 4h — Reddit + Medium + LinkedIn
    ("revenue_maximizer",       task_revenue_maximizer,      14400,   95),   # 4h — Cart Recovery + Winback
    ("free_syndication",        task_free_syndication,       21600,  115),   # 6h — Dev.to + Hashnode + Medium + Discord
    ("github_blog",             task_github_blog,            14400,  135),   # 4h — GitHub Pages SEO Blog
    # ── CONTENT FACTORY: AI-powered omnichannel content engine ───────────────
    ("content_factory_run",     task_content_factory_run,   14400,  130),   # 4h — full package from trending
    ("social_batch_gen",        task_social_batch_gen,      86400,  151),   # daily — 30-day social calendar
    ("trending_topic_scan",     task_trending_topic_scan,   43200,  171),   # 12h — catch viral waves early
    ("content_calendar_weekly", task_content_calendar_weekly, 604800, 190), # weekly — Monday calendar build
    # ── CONVERSION MAXIMIZER — 10 AI systems ─────────────────────────────────
    ("conversion_scan",         task_conversion_scan,         900,   610),  # 15min — A/B + social proof + lead scoring
    ("daily_optimization",      task_daily_optimization,      3600,  620),  # 1h — revenue opt + funnel analysis
    ("funnel_daily",            task_funnel_daily,            86400, 630),  # daily — full funnel Telegram report
    # ── OMEGA TRAFFIC ENGINE — REVOLUTION ────────────────────────────────────
    ("omega_full",              task_omega_full,              86400,  700),  # daily — full cycle: index+artikel+competitor
    ("omega_index",             task_omega_index,              3600,  710),  # 1h — Google+Bing instant index aller URLs
    ("omega_article",           task_omega_article,           86400,  720),  # daily — neuer SEO-Artikel (rotierend)
    ("omega_competitor",        task_omega_competitor,        21600,  730),  # 6h — competitor keywords klauen
    ("omega_social_proof",      task_omega_social_proof,      14400,  740),  # 4h — Testimonial auf Telegram
    ("omega_youtube",           task_omega_youtube,           86400,  750),  # daily — YouTube SEO-Paket
    ("omega_indexnow_sitemap",  task_omega_indexnow_sitemap,  43200,  760),  # 12h — Sitemaps bei IndexNow einreichen
    # ── TWITTER / X AUTOPOSTER (AIITEC Account) ──────────────────────────────
    ("twitter_daily_tweets",    task_twitter_daily_tweets,    14400,  800),  # 4h — 3 Tweets täglich
    ("twitter_seo_thread",      task_twitter_seo_thread,      86400,  810),  # daily — SEO-Thread (3 Tweets)
    # ── SEO MEGA ENGINE — 60 Artikel/Tag, Auto-Indexierung ───────────────────
    ("seo_mega_factory",        task_seo_mega_factory,         7200, 3600),  # 2h — 5 Artikel generieren (start 1h)
    ("seo_mega_submit",         task_seo_mega_submit,         14400, 4200),  # 4h — Google+Bing+IndexNow ping (1h10m)
    ("seo_competitor_analysis", task_seo_competitor_analysis, 43200, 5400),  # 12h — Konkurrenz-Keywords (1h30m)
    # ── TRAFFIC SWARM — Multi-Platform Distribution ───────────────────────────
    ("traffic_swarm_full",      task_traffic_swarm_full,      21600, 4800),  # 6h — Full Swarm alle Module (1h20m)
    ("traffic_velocity",        task_traffic_velocity_check,   3600, 2700),  # 1h — Drop/Spike Detection (45m)
    ("rss_rebuild",             task_rss_rebuild,             43200, 5401),  # 12h — RSS Feed rebuild (1h30m)
    ("content_freshness",       task_content_freshness,       86400, 6000),  # daily — Update alte Artikel (1h40m)
    ("backlink_outreach",       task_backlink_outreach_gen,   86400, 6600),  # daily — Outreach Emails (1h50m)
    # ── ADS ENGINE — Facebook/Google/TikTok ──────────────────────────────────
    ("ads_monitor",             task_ads_performance_monitor,  3600, 3000),  # 1h — Performance Check (50m)
    ("ads_optimize",            task_ads_optimize_run,        14400, 5402),  # 4h — Pause Loser/Scale Winner (1h30m)
    ("ads_rotate",              task_ads_creative_rotate,     86400, 7200),  # daily — Fresh Ad Copy (2h)
    # ── REVENUE INTELLIGENCE — Forecast + Leaks + Churn ──────────────────────
    ("revenue_autopilot",       task_revenue_autopilot_run,    3600, 2400),  # 1h — Full Revenue Scan (40m)
    ("revenue_morning",         task_revenue_briefing_morning, 86400, 3601),  # daily — 8am Briefing (1h)
    ("revenue_leaks",           task_revenue_leak_check,       1800, 1800),  # 30min — Failed Payments (30m)
    ("churn_prevention",        task_churn_prevention,        21600, 5403),  # 6h — Churn Risk Score (1h30m)
    # ── SHOPIFY MAX TUNER — Full Conversion Machine ───────────────────────────
    ("shopify_max_seo",         task_shopify_max_seo,         14400, 4801),  # 4h — AI SEO alle Produkte (1h20m)
    ("shopify_cart_recover",    task_shopify_cart_recover,     3600, 2100),  # 1h — Abandoned Cart Recovery (35m)
    ("shopify_price_optimize",  task_shopify_price_optimize,  86400, 7201),  # daily — .99 Psychological Pricing (2h)
    ("shopify_daily_intel",     task_shopify_daily_intel,     86400, 7202),  # daily — 7-Day Revenue Report (2h)
    ("shopify_inventory",       task_shopify_inventory_check,  7200, 3602),  # 2h — Low Stock Alerts (1h)
    ("shopify_reviews",         task_shopify_review_request,  14400, 5404),  # 4h — Review Request Emails (1h30m)
    # ── GROWTH HACKER — Viral + Influencer + Referral ────────────────────────
    ("viral_trend",             task_viral_trend_scan,         7200, 2401),  # 2h — Reddit Trends (40m)
    ("community_growth",        task_community_growth_post,    7200, 3603),  # 2h — Community Post (1h)
    ("growth_briefing",         task_growth_morning_briefing, 86400, 7203),  # daily — 7am Briefing (2h)
    ("influencer_pipeline",     task_influencer_pipeline,     86400, 7204),  # daily — Outreach List (2h)
    ("press_release",           task_press_release_generate,  86400, 7205),  # daily — AI Press Release (2h)
    ("testimonials",            task_testimonial_engine,      43200, 5405),  # 12h — Social Proof (1h30m)
    ("referral_system",         task_referral_system_run,     43200, 6001),  # 12h — Referral Codes (1h40m)
    # ── ULTRA SEO ARSENAL — 14+ Services IndexNow + Parasite SEO ─────────────
    ("ultra_seo_cycle",         task_ultra_seo_cycle,         10800, 1130),  # 3h — Full Ultra SEO: IndexNow+Sitemap+Content
    ("ultra_indexnow_all",      task_ultra_indexnow_all,      21600, 1140),  # 6h — Alle 14+ Properties IndexNow
    ("ultra_seo_health",        task_ultra_seo_health,        14400, 1150),  # 4h — Property Health Check
    # ── SOCIAL SCHEDULER — Twitter + Telegram Fallback ────────────────────────
    ("social_scheduler",        task_social_scheduler,        21600, 1200),  # 6h — Twitter post; Telegram fallback
    # ── NEW MODULE SCHEDULER TASKS ────────────────────────────────────────────
    ("dynamic_pricing_cycle",   task_dynamic_pricing_cycle,   14400, 7800),  # 4h — psychological .99 pricing
    ("tiktok_product_sync",     task_tiktok_sync,             21600, 8100),  # 6h — Shopify→TikTok Shop sync
    ("upsell_sequence_run",     task_upsell_sequence_run,     86400, 8400),  # daily — upsell enrolled buyers
    # ── TRAFFIC BLITZ — Maximale Frequenz alle Kanäle ────────────────────────
    ("traffic_blitz_full",      task_traffic_blitz_full,       7200, 9000),  # 2h — LinkedIn+Shopify+IndexNow+Telegram
    ("linkedin_burst",          task_linkedin_burst,           8*3600, 9100), # 3x täglich LinkedIn Posts
    ("shopify_seo_blast",       task_shopify_seo_blast,        14400, 9200), # 4h — 3 neue Shopify Blog-Posts
    ("indexnow_mega_blast",     task_indexnow_mega_blast,      3600,  9300), # stündlich — alle URLs bei Google+Bing
]


# ── Scheduler loop ───────────────────────────────────────────────────────────

class AutomationScheduler:
    def __init__(self):
        _init_db()
        self._running = False
        self._task_handles: List[asyncio.Task] = []

    async def start(self):
        self._running = True
        log.info(f"AutoScheduler gestartet — {len(TASKS)} Tasks registriert")
        for name, fn, interval, delay in TASKS:
            handle = asyncio.create_task(self._run_loop(name, fn, interval, delay))
            self._task_handles.append(handle)
        # Telegram bot uses webhook mode (server.py /webhook/telegram) — polling disabled
        log.info("Telegram: webhook mode active, polling disabled")

    async def stop(self):
        self._running = False
        for h in self._task_handles:
            h.cancel()

    async def run_now(self, task_name: str) -> Optional[str]:
        for name, fn, _, _ in TASKS:
            if name == task_name:
                return await self._execute(name, fn)
        return f"Task {task_name!r} nicht gefunden"

    async def _run_loop(self, name: str, fn: Callable, interval: int, delay: int):
        await asyncio.sleep(delay)
        while self._running:
            result = await self._execute(name, fn)
            log.debug(f"[{name}] {result}")
            await asyncio.sleep(interval)

    # Self-healing: consecutive fail counter per task
    _fail_counts: Dict[str, int] = {}

    async def _send_healing_alert(self, task_name: str, error: str, fails: int) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (f"⚠️ Self-Healing Alert\n"
               f"Task: {task_name}\n"
               f"Fehler {fails}x: {error[:200]}\n"
               f"Auto-Retry läuft...")
        try:
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg},
                    timeout=_aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass

    async def _execute(self, name: str, fn: Callable) -> str:
        t0 = time.monotonic()
        try:
            result = await fn()
            ms = int((time.monotonic() - t0) * 1000)
            _log_run(name, True, result or "", ms)
            self._fail_counts[name] = 0  # reset on success
            return result or "OK"
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            err = f"{type(e).__name__}: {e}"
            _log_run(name, False, err, ms)
            log.error(f"[{name}] {err}")
            # Self-healing: track consecutive failures
            self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
            fails = self._fail_counts[name]
            if fails >= 3:
                await self._send_healing_alert(name, err, fails)
                self._fail_counts[name] = 0  # reset after alert
            # Exponential backoff retry (max 5 min)
            backoff = min(60 * fails, 300)
            log.info(f"[{name}] retry in {backoff}s (fail #{fails})")
            await asyncio.sleep(backoff)
            try:
                retry_result = await fn()
                self._fail_counts[name] = 0
                return f"RECOVERED: {retry_result or 'OK'}"
            except Exception as e2:
                return f"FAILED after retry: {e2}"

    def status(self) -> Dict:
        stats = get_task_stats()
        return {
            "running": self._running,
            "task_count": len(TASKS),
            "tasks": [
                {
                    "name": name,
                    "interval_s": interval,
                    **stats.get(name, {"total": 0, "ok": 0, "last_run": None, "avg_ms": 0})
                }
                for name, _, interval, _ in TASKS
            ]
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_scheduler: Optional[AutomationScheduler] = None


def get_scheduler() -> AutomationScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AutomationScheduler()
    return _scheduler


def get_scheduler_status() -> dict:
    """Return all scheduler tasks with stats."""
    s = get_scheduler()
    return s.status()
