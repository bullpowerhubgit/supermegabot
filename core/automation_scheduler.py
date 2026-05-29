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


# ── Task registry ────────────────────────────────────────────────────────────

TASKS = [
    # (name, coroutine_fn, interval_seconds, initial_delay_seconds)
    # ── Real-time (every few minutes) ────────────────────────────────────────
    ("system_health",       task_system_health,       300,    10),   # 5 min
    ("railway_health",      task_railway_health,      600,    20),   # 10 min
    # ── Sales & Orders (every 15-30 min) ─────────────────────────────────────
    ("digistore_sync",      task_digistore_sync,      900,    30),   # 15 min
    ("printify_autofulfill",task_printify_autofulfill,1800,   45),   # 30 min
    ("pod_autofulfill",     task_pod_autofulfill,     1800,   50),   # 30 min
    ("etsy_sync",           task_etsy_sync,           1800,   60),   # 30 min
    ("gumroad_sync",        task_gumroad_sync,        1800,   75),   # 30 min
    # ── Marketing & Sync (hourly) ─────────────────────────────────────────────
    ("mailchimp_sync",      task_mailchimp_sync,      3600,   90),   # 1h
    ("shopify_sync",        task_shopify_sync,        3600,   120),  # 1h
    ("social_status",       task_social_status,       3600,   150),  # 1h
    ("social_autoposter",   task_social_autoposter,   3600,   180),  # 1h
    # ── Growth & SEO (every 2-6 hours) ────────────────────────────────────────
    ("seo_optimizer",       task_seo_optimizer,       7200,   200),  # 2h
    ("dropshipping_scan",   task_dropshipping_scan,   7200,   220),  # 2h
    ("trading_report",      task_trading_report,      21600,  240),  # 6h
    # ── Daily ─────────────────────────────────────────────────────────────────
    ("revenue_report",      task_revenue_report,      86400,  270),  # daily
    ("content_calendar",    task_content_calendar,    86400,  290),  # daily
    ("github_backup",       task_github_backup,       86400,  300),  # daily
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

    async def _execute(self, name: str, fn: Callable) -> str:
        t0 = time.monotonic()
        try:
            result = await fn()
            ms = int((time.monotonic() - t0) * 1000)
            _log_run(name, True, result or "", ms)
            return result or "OK"
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            err = f"{type(e).__name__}: {e}"
            _log_run(name, False, err, ms)
            log.error(f"[{name}] {err}")
            return err

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
