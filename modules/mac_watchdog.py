"""
Mac Watchdog — Vollautomatische Mac + System Überwachung
=========================================================
• Mac: CPU / RAM / Disk / Netzwerk / Prozesse
• Railway: alle Services auf Up/Down prüfen
• Lokaler Server: crashed → auto-restart
• Shopify / Stripe / Supabase API Health
• Scheduler: fehlgeschlagene Tasks → auto-retry
• Telegram-Alarm bei jedem kritischen Problem
• Täglich: vollständiger System-Report

Läuft alle 5 Min als LaunchAgent auf dem Mac.
"""

import asyncio
import aiohttp
import subprocess
import logging
import os
import json
import sys
import psutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from modules.mac_disk_cleaner import run_full_cleanup, get_disk_free_gb
except ImportError:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from modules.mac_disk_cleaner import run_full_cleanup, get_disk_free_gb
    except ImportError:
        run_full_cleanup = None
        get_disk_free_gb = None

log = logging.getLogger("MacWatchdog")

TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")

SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
STRIPE_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "")

LOCAL_SERVER_PORT = 8888
LOCAL_SERVER_CMD  = [sys.executable, "dashboard/server.py"]
PROJECT_DIR       = Path(__file__).parent.parent

STATE_FILE = PROJECT_DIR / "data" / "mac_watchdog_state.json"

RAILWAY_SERVICES = [
    ("supermegabot",          "https://supermegabot-production.up.railway.app/health"),
    ("icomeauto",             "https://icomeauto-production.up.railway.app/health"),
    ("steuercockpit",         "https://steuercockpit-production.up.railway.app/health"),
    ("shopify-acquisition",   "https://shopify-acquisition-production.up.railway.app/health"),
]

# Thresholds
CPU_WARN    = 85   # %
RAM_WARN    = 88   # %
DISK_WARN      = 85   # %  von belegt → Alert
DISK_MIN_GB    = 5    # GB frei → kritischer Alert
DISK_CLEAN_GB  = 20   # GB frei → auto-cleanup starten


# ── State ────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {
            "last_daily": "",
            "alerted": {},       # service → last alert time (ISO)
            "restarts": {},      # service → restart count
            "down_since": {},    # service → first down time
        }


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def _cooldown_ok(state: dict, key: str, minutes: int = 30) -> bool:
    """Nur alle X Minuten für den gleichen Fehler alarmieren."""
    last = state.get("alerted", {}).get(key)
    if not last:
        return True
    delta = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
    return delta > minutes * 60


def _mark_alerted(state: dict, key: str) -> None:
    state.setdefault("alerted", {})[key] = datetime.now(timezone.utc).isoformat()


# ── Telegram ─────────────────────────────────────────────────────────────────

async def _tg(session: aiohttp.ClientSession, text: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with session.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                log.debug("TG send failed: %s", r.status)
    except Exception as e:
        log.debug("TG error: %s", e)


# ── 1. Mac System ─────────────────────────────────────────────────────────────

def check_mac_system() -> dict:
    issues = []
    metrics = {}

    try:
        cpu = psutil.cpu_percent(interval=2)
        metrics["cpu"] = cpu
        if cpu > CPU_WARN:
            # Top-Prozesse finden
            top = sorted(psutil.process_iter(["name", "cpu_percent"]),
                         key=lambda p: p.info.get("cpu_percent") or 0, reverse=True)[:3]
            top_names = ", ".join(p.info["name"] for p in top if p.info.get("name"))
            issues.append(f"🔴 CPU hoch: {cpu:.0f}% (Top: {top_names})")
    except Exception as e:
        log.debug("CPU check: %s", e)

    try:
        mem = psutil.virtual_memory()
        metrics["ram"] = mem.percent
        if mem.percent > RAM_WARN:
            issues.append(f"🔴 RAM hoch: {mem.percent:.0f}% belegt ({mem.available // 1024**3}GB frei)")
    except Exception as e:
        log.debug("RAM check: %s", e)

    try:
        disk = psutil.disk_usage("/")
        free_gb = disk.free / 1024**3
        metrics["disk_pct"] = disk.percent
        metrics["disk_free_gb"] = round(free_gb, 1)
        if disk.percent > DISK_WARN or free_gb < DISK_MIN_GB:
            issues.append(f"🔴 Disk: {disk.percent:.0f}% belegt ({free_gb:.1f}GB frei)")
    except Exception as e:
        log.debug("Disk check: %s", e)

    try:
        net = psutil.net_io_counters()
        metrics["net_sent_mb"]  = round(net.bytes_sent / 1024**2, 1)
        metrics["net_recv_mb"]  = round(net.bytes_recv / 1024**2, 1)
    except Exception:
        pass

    return {"issues": issues, "metrics": metrics}


# ── 2. Prozesse überwachen ────────────────────────────────────────────────────

def check_local_processes() -> dict:
    issues = []
    running = {}

    for proc in psutil.process_iter(["name", "cmdline", "status"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "dashboard/server.py" in cmd:
                running["local_server"] = proc.pid
            if "automation_scheduler" in cmd:
                running["scheduler"] = proc.pid
        except Exception:
            pass

    if "local_server" not in running:
        issues.append("⚠️ Lokaler Server (port 8888) nicht aktiv")
    if "scheduler" not in running:
        issues.append("⚠️ Scheduler nicht aktiv")

    return {"issues": issues, "running": running}


def restart_local_server() -> bool:
    """Startet den lokalen Server neu."""
    try:
        subprocess.Popen(
            LOCAL_SERVER_CMD,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("Lokaler Server neu gestartet")
        return True
    except Exception as e:
        log.error("Server-Restart fehlgeschlagen: %s", e)
        return False


# ── 3. Railway Services ───────────────────────────────────────────────────────

async def check_railway_services(session: aiohttp.ClientSession) -> dict:
    issues = []
    status = {}

    for name, url in RAILWAY_SERVICES:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                body = await r.json()
                ok = r.status == 200 and body.get("status") == "ok"
                status[name] = "ok" if ok else f"HTTP {r.status}"
                if not ok:
                    issues.append(f"🔴 Railway `{name}` DOWN: HTTP {r.status}")
        except asyncio.TimeoutError:
            status[name] = "timeout"
            issues.append(f"🔴 Railway `{name}` TIMEOUT")
        except Exception as e:
            status[name] = f"error: {str(e)[:40]}"
            issues.append(f"🔴 Railway `{name}` nicht erreichbar")

    return {"issues": issues, "status": status}


# ── 4. API Health Checks ──────────────────────────────────────────────────────

async def check_apis(session: aiohttp.ClientSession) -> dict:
    issues = []

    # Shopify
    if SHOPIFY_DOMAIN and SHOPIFY_TOKEN:
        try:
            url = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/shop.json"
            async with session.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    issues.append(f"🔴 Shopify API: HTTP {r.status}")
        except Exception:
            issues.append("🔴 Shopify API nicht erreichbar")

    # Stripe
    if STRIPE_KEY:
        try:
            async with session.get("https://api.stripe.com/v1/balance",
                                   headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    issues.append(f"🔴 Stripe API: HTTP {r.status}")
        except Exception:
            issues.append("🔴 Stripe API nicht erreichbar")

    # Supabase
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            async with session.get(f"{SUPABASE_URL}/rest/v1/",
                                   headers={"apikey": SUPABASE_KEY},
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status not in (200, 400):
                    issues.append(f"🔴 Supabase: HTTP {r.status}")
        except Exception:
            issues.append("🔴 Supabase nicht erreichbar")

    return {"issues": issues}


# ── 5. Internet-Check ─────────────────────────────────────────────────────────

async def check_internet(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get("https://1.1.1.1", timeout=aiohttp.ClientTimeout(total=5)) as r:
            return r.status < 500
    except Exception:
        return False


# ── 6. Tages-Report ──────────────────────────────────────────────────────────

async def send_daily_report(session: aiohttp.ClientSession, state: dict,
                             mac: dict, railway: dict) -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if state.get("last_daily") == today:
        return
    if now.hour not in (6, 7):
        return

    m = mac.get("metrics", {})
    railway_ok  = sum(1 for v in railway.get("status", {}).values() if v == "ok")
    railway_all = len(RAILWAY_SERVICES)

    restarts = sum(state.get("restarts", {}).values())

    text = (
        f"☀️ *Mac Watchdog Report — {today}*\n\n"
        f"💻 Mac:\n"
        f"  CPU: {m.get('cpu', '?')}%  |  RAM: {m.get('ram', '?')}%\n"
        f"  Disk frei: {m.get('disk_free_gb', '?')} GB\n\n"
        f"🚀 Railway: {railway_ok}/{railway_all} Services OK\n"
        f"🔄 Auto-Restarts heute: {restarts}\n\n"
        f"🤖 Überwachung läuft vollautomatisch ✅"
    )
    await _tg(session, text)
    state["last_daily"] = today
    log.info("Tages-Report gesendet")


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

async def run_mac_watchdog() -> dict:
    """
    Vollständige Mac + System Überwachung.
    Aufruf alle 5 Min via LaunchAgent oder Scheduler.
    """
    result = {"alerts": 0, "issues": [], "repaired": [], "ok": True}
    state = _load_state()

    async with aiohttp.ClientSession() as session:

        # Internet zuerst prüfen
        has_internet = await check_internet(session)
        if not has_internet:
            if _cooldown_ok(state, "no_internet", 60):
                await _tg(session, "🔴 *Kein Internet!* — Mac Watchdog kann Services nicht prüfen")
                _mark_alerted(state, "no_internet")
            result["issues"].append("Kein Internet")
            _save_state(state)
            return result

        # 1. Mac System
        mac = check_mac_system()
        for issue in mac["issues"]:
            key = issue[:30]
            if _cooldown_ok(state, key, 30):
                await _tg(session, f"⚠️ *Mac System Alert*\n{issue}")
                _mark_alerted(state, key)
                result["alerts"] += 1
        result["issues"].extend(mac["issues"])

        # 2. Lokale Prozesse
        procs = check_local_processes()
        for issue in procs["issues"]:
            if "Lokaler Server" in issue:
                if _cooldown_ok(state, "local_server_down", 15):
                    restarted = restart_local_server()
                    msg = "🔧 Lokaler Server war DOWN → *auto-restart* ✅" if restarted \
                          else "🔴 Lokaler Server DOWN — restart fehlgeschlagen"
                    await _tg(session, msg)
                    _mark_alerted(state, "local_server_down")
                    if restarted:
                        state.setdefault("restarts", {})["local_server"] = \
                            state["restarts"].get("local_server", 0) + 1
                        result["repaired"].append("local_server restarted")
                    result["alerts"] += 1
            result["issues"].append(issue)

        # 3. Railway Services
        railway = await check_railway_services(session)
        for issue in railway["issues"]:
            key = issue[:40]
            if _cooldown_ok(state, key, 20):
                await _tg(session, f"🚨 *Railway Alert*\n{issue}")
                _mark_alerted(state, key)
                result["alerts"] += 1
        result["issues"].extend(railway["issues"])

        # 4. API Health
        apis = await check_apis(session)
        for issue in apis["issues"]:
            key = issue[:40]
            if _cooldown_ok(state, key, 60):
                await _tg(session, f"⚠️ *API Alert*\n{issue}")
                _mark_alerted(state, key)
                result["alerts"] += 1
        result["issues"].extend(apis["issues"])

        # 5. Auto Disk Cleanup (wenn < DISK_CLEAN_GB frei)
        if run_full_cleanup and get_disk_free_gb:
            free_gb = get_disk_free_gb()
            if free_gb < DISK_CLEAN_GB:
                if _cooldown_ok(state, "disk_cleanup", 120):
                    log.warning("Nur %.1f GB frei — starte Auto-Cleanup", free_gb)
                    try:
                        cleanup = run_full_cleanup(force=False)
                        if not cleanup.get("skipped"):
                            freed = cleanup.get("freed_mb", 0)
                            after = cleanup.get("free_after_gb", free_gb)
                            msg = (
                                f"🧹 *Auto Disk Cleanup abgeschlossen*\n"
                                f"War: {free_gb:.1f} GB frei\n"
                                f"Jetzt: {after:.1f} GB frei\n"
                                f"Befreit: {freed:.0f} MB\n\n"
                                f"Details:\n" +
                                "\n".join(f"  • {k}: {v} MB" for k, v in cleanup.get("steps", {}).items() if v > 0)
                            )
                            await _tg(session, msg)
                            _mark_alerted(state, "disk_cleanup")
                            result["repaired"].append(f"disk_cleanup: +{freed:.0f}MB")
                    except Exception as e:
                        log.error("Auto Disk Cleanup Fehler: %s", e)

        # 6. Tages-Report
        await send_daily_report(session, state, mac, railway)

    if result["issues"]:
        result["ok"] = False

    _save_state(state)
    log.info("Mac Watchdog: %d Alerts, repaired: %s",
             result["alerts"], result["repaired"] or "nichts nötig")
    return result


# ── Standalone-Modus (direkt ausführbar) ─────────────────────────────────────

if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv(PROJECT_DIR / ".env")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    result = asyncio.run(run_mac_watchdog())
    print(json.dumps(result, indent=2))
