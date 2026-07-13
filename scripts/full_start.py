#!/usr/bin/env python3
"""
BullPower MEGA Command Center — Full Start (v11.0)
Vollautonomer Start mit Env-Validation, Health-Checks, Webhooks,
Scheduler, Dashboard, Self-Healer und Telegram-Bestätigung.
Ausführen: python3 scripts/full_start.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Root + Path ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── .env laden — IMMER override=True ────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(str(ROOT / ".env"), override=True)

import aiohttp

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("full_start")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Konsolen-Farben ──────────────────────────────────────────────────────
G = "\033[0;32m"; R = "\033[0;31m"; Y = "\033[1;33m"
B = "\033[0;34m"; C = "\033[0;36m"; W = "\033[1m";  N = "\033[0m"

def ok(msg: str):  log.info(f"{G}OK{N}  {msg}")
def err(msg: str): log.error(f"{R}ERR{N} {msg}")
def inf(msg: str): log.info(f"{C}INF{N} {msg}")
def hdr(msg: str): print(f"\n{W}{B}{'─'*56}{N}\n{W}{B}  {msg}{N}\n{W}{B}{'─'*56}{N}")
def warn(msg: str): log.warning(f"{Y}WRN{N} {msg}")


# ── Kritische Keys (Fail-Fast wenn fehlend) ──────────────────────────────
CRITICAL_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SHOPIFY_SHOP_DOMAIN",
    "SHOPIFY_ADMIN_API_TOKEN",
]

# Wichtige aber nicht blocklerende Keys
OPTIONAL_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "SUPABASE_ANON_KEY",
    "SHOPIFY_API_VERSION",
    "GITHUB_TOKEN",
    "GITHUB_USER",
    "DS24_API_KEY",
]


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 1 — Env-Validation
# ══════════════════════════════════════════════════════════════════════════
async def validate_env() -> tuple[bool, list[str], list[str]]:
    """Prüft alle kritischen und optionalen Keys. Gibt (ok, missing_critical, missing_optional) zurück."""
    missing_critical: list[str] = []
    missing_optional: list[str] = []

    for key in CRITICAL_KEYS:
        val = os.getenv(key, "").strip()
        if not val:
            missing_critical.append(key)
            err(f"KRITISCH fehlt: {key}")
        else:
            ok(f"{key} = {'*' * min(6, len(val))}…")

    for key in OPTIONAL_KEYS:
        val = os.getenv(key, "").strip()
        if not val:
            missing_optional.append(key)
            warn(f"Optional fehlt: {key}")
        else:
            ok(f"{key} = {'*' * min(6, len(val))}…")

    env_path = ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        filled = sum(1 for l in lines if "=" in l and not l.startswith("#") and l.split("=", 1)[1].strip())
        inf(f".env: {filled} Keys gesetzt / {len(lines)} Zeilen gesamt")
    else:
        err(".env Datei nicht gefunden!")
        missing_critical.append(".env FILE")

    success = len(missing_critical) == 0
    return success, missing_critical, missing_optional


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 2 — Platform Health-Checks
# ══════════════════════════════════════════════════════════════════════════
PLATFORM_CHECKS: list[dict] = [
    {
        "name": "Supabase",
        "url": f"{os.getenv('SUPABASE_URL', '')}/rest/v1/",
        "headers": {
            "apikey": os.getenv("SUPABASE_ANON_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_KEY', '')}",
        },
        "critical": True,
    },
    {
        "name": "Shopify",
        "url": f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', 'x.myshopify.com')}/admin/api/{os.getenv('SHOPIFY_API_VERSION', '2024-01')}/shop.json",
        "headers": {"X-Shopify-Access-Token": os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")},
        "critical": True,
    },
    {
        "name": "Telegram",
        "url": f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', 'x')}/getMe",
        "headers": {},
        "critical": True,
    },
    {
        "name": "Anthropic",
        "url": "https://api.anthropic.com/v1/models",
        "headers": {
            "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
        },
        "critical": False,
    },
    {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1/models",
        "headers": {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"},
        "critical": False,
    },
    {
        "name": "Stripe",
        "url": "https://api.stripe.com/v1/balance",
        "headers": {"Authorization": f"Bearer {os.getenv('STRIPE_SECRET_KEY', '')}"},
        "critical": False,
    },
]


async def _check_one(session: aiohttp.ClientSession, plat: dict) -> dict:
    name = plat["name"]
    url  = plat["url"]
    hdrs = {k: v for k, v in plat["headers"].items() if v}

    if not url or url.endswith("/x.myshopify.com/admin/api/"):
        return {"name": name, "ok": False, "reason": "URL/Key nicht konfiguriert", "critical": plat["critical"]}

    try:
        async with session.get(
            url,
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=10),
            ssl=True,
        ) as resp:
            status_ok = resp.status in (200, 201, 204)
            reason = f"HTTP {resp.status}"
            if status_ok:
                ok(f"{name}: {reason}")
            else:
                body = (await resp.text())[:120]
                warn(f"{name}: {reason} — {body}")
            return {"name": name, "ok": status_ok, "reason": reason, "critical": plat["critical"]}
    except asyncio.TimeoutError:
        warn(f"{name}: Timeout (>10s)")
        return {"name": name, "ok": False, "reason": "Timeout", "critical": plat["critical"]}
    except Exception as e:
        warn(f"{name}: {e}")
        return {"name": name, "ok": False, "reason": str(e)[:80], "critical": plat["critical"]}


async def run_platform_health() -> list[dict]:
    """Prüft alle Plattformen parallel mit 10s Timeout je."""
    # Reload dynamic values (Keys wurden in validate_env bereits geprüft)
    checks = [
        {
            "name": "Supabase",
            "url": f"{os.getenv('SUPABASE_URL', '')}/rest/v1/",
            "headers": {
                "apikey": os.getenv("SUPABASE_ANON_KEY", ""),
                "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_KEY', '')}",
            },
            "critical": True,
        },
        {
            "name": "Shopify",
            "url": f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', '')}/admin/api/{os.getenv('SHOPIFY_API_VERSION', '2024-01')}/shop.json",
            "headers": {"X-Shopify-Access-Token": os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")},
            "critical": True,
        },
        {
            "name": "Telegram",
            "url": f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', 'x')}/getMe",
            "headers": {},
            "critical": True,
        },
        {
            "name": "Anthropic",
            "url": "https://api.anthropic.com/v1/models",
            "headers": {
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            "critical": False,
        },
        {
            "name": "OpenAI",
            "url": "https://api.openai.com/v1/models",
            "headers": {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"},
            "critical": False,
        },
        {
            "name": "Stripe",
            "url": "https://api.stripe.com/v1/balance",
            "headers": {"Authorization": f"Bearer {os.getenv('STRIPE_SECRET_KEY', '')}"},
            "critical": False,
        },
    ]

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_check_one(session, p) for p in checks],
            return_exceptions=True,
        )

    clean: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            clean.append({"name": "?", "ok": False, "reason": str(r), "critical": False})
        else:
            clean.append(r)

    total   = len(clean)
    n_ok    = sum(1 for r in clean if r["ok"])
    n_crit  = sum(1 for r in clean if not r["ok"] and r.get("critical"))
    inf(f"Health-Gesamt: {n_ok}/{total} OK — {n_crit} kritische Fehler")
    return clean


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 3 — Shopify Webhook-Setup
# ══════════════════════════════════════════════════════════════════════════
SHOPIFY_WEBHOOKS = [
    {"topic": "carts/update",       "alias": "cart_rescue"},
    {"topic": "orders/create",      "alias": "orders_create"},
    {"topic": "orders/fulfilled",   "alias": "orders_fulfilled"},
]


async def setup_shopify_webhooks() -> int:
    """Registriert fehlende Shopify Webhooks. Gibt Anzahl registrierter zurück."""
    domain   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version  = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("PUBLIC_URL", ""))

    if not domain or not token:
        warn("Shopify Webhooks übersprungen — SHOPIFY_SHOP_DOMAIN/TOKEN fehlt")
        return 0
    if not base_url:
        warn("Shopify Webhooks übersprungen — PUBLIC_URL / RAILWAY_PUBLIC_DOMAIN fehlt")
        return 0

    base_url = base_url.rstrip("/")
    api_base = f"https://{domain}/admin/api/{version}"
    headers  = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    registered = 0

    try:
        async with aiohttp.ClientSession() as session:
            # Bestehende Webhooks laden
            async with session.get(f"{api_base}/webhooks.json", headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                existing_raw = (await resp.json()).get("webhooks", []) if resp.status == 200 else []
            existing_topics = {w["topic"] for w in existing_raw}

            for wh in SHOPIFY_WEBHOOKS:
                topic = wh["topic"]
                if topic in existing_topics:
                    inf(f"Webhook bereits vorhanden: {topic}")
                    continue
                endpoint = f"{base_url}/webhooks/shopify/{wh['alias']}"
                payload = {"webhook": {"topic": topic, "address": endpoint, "format": "json"}}
                async with session.post(f"{api_base}/webhooks.json", json=payload,
                                        headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status in (200, 201):
                        ok(f"Webhook registriert: {topic} → {endpoint}")
                        registered += 1
                    else:
                        body = (await r.text())[:120]
                        warn(f"Webhook {topic} fehlgeschlagen: HTTP {r.status} — {body}")
    except Exception as e:
        warn(f"Shopify Webhook-Setup Fehler: {e}")

    return registered


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 4 — Scheduler starten
# ══════════════════════════════════════════════════════════════════════════
def start_scheduler() -> int | None:
    sched_path = ROOT / "core" / "automation_scheduler.py"
    if not sched_path.exists():
        warn("automation_scheduler.py nicht gefunden — übersprungen")
        return None
    log_path = "/tmp/supermegabot_scheduler.log"
    proc = subprocess.Popen(
        [sys.executable, str(sched_path)],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env={**os.environ},
    )
    time.sleep(2)
    if proc.poll() is None:
        ok(f"Scheduler gestartet (PID {proc.pid}) → {log_path}")
        return proc.pid
    else:
        err(f"Scheduler-Start fehlgeschlagen → {log_path}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 5 — Dashboard starten + Health-Check
# ══════════════════════════════════════════════════════════════════════════
def free_port(port: int = 8888):
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = [p for p in result.stdout.strip().split("\n") if p]
        for pid in pids:
            subprocess.run(["kill", "-9", pid], capture_output=True)
        if pids:
            ok(f"Port {port} freigegeben (PIDs: {', '.join(pids)})")
        else:
            inf(f"Port {port} bereits frei")
    except Exception as e:
        inf(f"Port-Freigabe übersprungen: {e}")


async def start_dashboard_with_healthcheck() -> int | None:
    log_path = "/tmp/supermegabot.log"
    free_port(8888)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "dashboard" / "server.py")],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env={**os.environ},
    )

    # Warten + Health-Check (max 15s)
    deadline = time.time() + 15
    dash_ok = False
    async with aiohttp.ClientSession() as session:
        while time.time() < deadline:
            await asyncio.sleep(1)
            if proc.poll() is not None:
                err(f"Dashboard-Prozess unerwartet beendet (Code {proc.returncode})")
                err(f"Letztes Log: {log_path}")
                return None
            try:
                async with session.get(
                    "http://localhost:8888/health",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    if resp.status == 200:
                        dash_ok = True
                        break
            except Exception:
                pass  # noch nicht bereit

    if dash_ok:
        ok(f"Dashboard live auf http://localhost:8888 (PID {proc.pid})")
        return proc.pid
    else:
        err(f"Dashboard antwortet nicht nach 15s — Log: {log_path}")
        return proc.pid  # Prozess läuft evtl. noch, nicht killen


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 6 — Self-Healer starten
# ══════════════════════════════════════════════════════════════════════════
def start_self_healer() -> int | None:
    healer_candidates = [
        ROOT / "core" / "self_healer.py",
        ROOT / "modules" / "self_healer.py",
        ROOT / "scripts" / "self_healer.py",
    ]
    healer_path = next((p for p in healer_candidates if p.exists()), None)
    if healer_path is None:
        inf("self_healer.py nicht gefunden — übersprungen")
        return None
    log_path = "/tmp/supermegabot_healer.log"
    proc = subprocess.Popen(
        [sys.executable, str(healer_path)],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env={**os.environ},
    )
    time.sleep(1)
    if proc.poll() is None:
        ok(f"Self-Healer gestartet (PID {proc.pid}) → {log_path}")
        return proc.pid
    else:
        warn(f"Self-Healer-Start fehlgeschlagen → {log_path}")
        return None


# ══════════════════════════════════════════════════════════════════════════
# Revenue Snapshot (für Telegram-Nachricht)
# ══════════════════════════════════════════════════════════════════════════
async def get_revenue_snapshot() -> dict:
    try:
        from modules.revenue_tracker import get_all_revenue  # type: ignore
        rev = await get_all_revenue()
        total_eur = rev.get("total_eur", 0.0)
        ok(f"Revenue heute: €{total_eur:.2f} (Stripe + DS24 + Shopify)")
        return rev
    except ImportError:
        inf("revenue_tracker nicht verfügbar — übersprungen")
        return {}
    except Exception as e:
        warn(f"Revenue-Snapshot Fehler: {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════════
# SCHRITT 7 — Telegram-Bestätigung
# ══════════════════════════════════════════════════════════════════════════
async def tg(msg: str):
    """Sendet eine Telegram-Nachricht."""
    if not TG_TOKEN or not TG_CHAT:
        warn("Telegram nicht konfiguriert — Nachricht übersprungen")
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    ok("Telegram-Nachricht gesendet")
                else:
                    body = (await resp.text())[:120]
                    warn(f"Telegram HTTP {resp.status}: {body}")
    except Exception as e:
        warn(f"Telegram-Fehler: {e}")


async def send_start_confirmation(
    health_results: list[dict],
    revenue: dict,
    dash_pid: int | None,
    sched_pid: int | None,
    healer_pid: int | None,
    elapsed: float,
    missing_optional: list[str],
    webhooks_registered: int,
):
    n_ok    = sum(1 for r in health_results if r["ok"])
    n_total = len(health_results)

    # API-Status-Zeilen aufbauen
    api_lines = []
    for r in health_results:
        icon = "✅" if r["ok"] else "❌"
        api_lines.append(f"  {icon} {r['name']}: {r['reason'] if not r['ok'] else 'OK'}")
    api_block = "\n".join(api_lines)

    rev_total = revenue.get("total_eur", 0.0) if isinstance(revenue, dict) else 0.0

    # Tasks aktiv
    tasks: list[str] = []
    if dash_pid:  tasks.append(f"Dashboard PID {dash_pid}")
    if sched_pid: tasks.append(f"Scheduler PID {sched_pid}")
    if healer_pid: tasks.append(f"Self-Healer PID {healer_pid}")
    tasks_str = " | ".join(tasks) if tasks else "—"

    opt_warn = ""
    if missing_optional:
        opt_warn = f"\n⚠️ Optionale Keys fehlen: `{', '.join(missing_optional[:4])}`"

    msg = (
        f"✅ *BullPower MEGA Command Center GESTARTET*\n\n"
        f"🖥 *Tasks aktiv:* {tasks_str}\n\n"
        f"🌐 *APIs ({n_ok}/{n_total} OK):*\n{api_block}\n\n"
        f"💰 *Revenue heute:* €{rev_total:.2f}\n"
        f"🔗 *Webhooks registriert:* {webhooks_registered}\n"
        f"⏱ *Start-Zeit:* {elapsed:.1f}s"
        f"{opt_warn}\n\n"
        f"🔗 http://localhost:8888"
    )
    await tg(msg)


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
async def main():
    print(f"""
{W}{B}
╔══════════════════════════════════════════════════════╗
║  ⚡  BullPower MEGA Command Center — FULL START v11  ║
║      SuperMegaBot — Rudolf Sarkany                   ║
╚══════════════════════════════════════════════════════╝
{N}""")
    t0 = time.time()

    # ── SCHRITT 1: Env-Validation (Fail-Fast bei kritischen Keys) ─────────
    hdr("SCHRITT 1 / 7 — Env-Validation")
    env_ok, missing_critical, missing_optional = await validate_env()
    if not env_ok:
        crit_str = ", ".join(missing_critical)
        fatal = f"KRITISCHE Keys fehlen: {crit_str}"
        err(fatal)
        await tg(f"🚨 *FULL START ABGEBROCHEN*\n\n❌ {fatal}\n\nBitte .env prüfen!")
        sys.exit(1)

    # ── SCHRITT 2: Health-Checks aller Plattformen ─────────────────────
    hdr("SCHRITT 2 / 7 — Platform Health-Checks")
    health_results = await run_platform_health()

    # Kritische Plattform-Fehler → abbrechen
    critical_fails = [r for r in health_results if not r["ok"] and r.get("critical")]
    if critical_fails:
        names = ", ".join(r["name"] for r in critical_fails)
        err(f"Kritische Plattformen nicht erreichbar: {names}")
        warn("Fahre trotzdem fort — manuelle Prüfung empfohlen!")
        # Kein sys.exit hier — Telegram warnt, aber System startet

    # ── SCHRITT 3: Shopify Webhook-Setup ───────────────────────────────
    hdr("SCHRITT 3 / 7 — Shopify Webhook-Setup")
    webhooks_registered = await setup_shopify_webhooks()

    # ── SCHRITT 4: Scheduler starten ───────────────────────────────────
    hdr("SCHRITT 4 / 7 — Automation-Scheduler")
    sched_pid = start_scheduler()

    # ── SCHRITT 5: Dashboard starten + Health-Check ────────────────────
    hdr("SCHRITT 5 / 7 — Dashboard")
    dash_pid = await start_dashboard_with_healthcheck()
    if dash_pid is None:
        err("Dashboard konnte nicht gestartet werden!")
        await tg("🚨 *Dashboard-Start FEHLGESCHLAGEN* — Bitte Logs prüfen!\n`/tmp/supermegabot.log`")
        sys.exit(1)

    # ── SCHRITT 6: Self-Healer starten ─────────────────────────────────
    hdr("SCHRITT 6 / 7 — Self-Healer")
    healer_pid = start_self_healer()

    # ── SCHRITT 7: Revenue + Telegram-Bestätigung ──────────────────────
    hdr("SCHRITT 7 / 7 — Revenue & Telegram-Bestätigung")
    revenue = await get_revenue_snapshot()
    elapsed = time.time() - t0

    await send_start_confirmation(
        health_results=health_results,
        revenue=revenue,
        dash_pid=dash_pid,
        sched_pid=sched_pid,
        healer_pid=healer_pid,
        elapsed=elapsed,
        missing_optional=missing_optional,
        webhooks_registered=webhooks_registered,
    )

    # ── Abschluss-Banner ────────────────────────────────────────────────
    n_ok = sum(1 for r in health_results if r["ok"])
    rev_total = revenue.get("total_eur", 0.0) if isinstance(revenue, dict) else 0.0
    print(f"""
{W}{G}
╔══════════════════════════════════════════════════════╗
║  ✅  ALLE SYSTEME AKTIV — {elapsed:.1f}s                 ║
╚══════════════════════════════════════════════════════╝
{N}
  Dashboard:     {W}http://localhost:8888{N}
  APIs:          {W}{n_ok}/{len(health_results)} OK{N}
  Revenue heute: {W}€{rev_total:.2f}{N}
  Webhooks:      {W}{webhooks_registered} registriert{N}
  Scheduler PID: {W}{sched_pid}{N}
  Healer PID:    {W}{healer_pid}{N}
  Dashboard-Log: {W}/tmp/supermegabot.log{N}
  Scheduler-Log: {W}/tmp/supermegabot_scheduler.log{N}

  {Y}Revenue-Engine läuft — Status per Telegram!{N}
""")

    # Browser öffnen (macOS)
    try:
        subprocess.Popen(["open", "http://localhost:8888"])
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
