#!/usr/bin/env python3
"""
Empire Controller — Vollautonomer Master-Supervisor
====================================================
EIN Prozess der alles startet, überwacht, repariert und berichtet.

Was dieser Controller tut:
  • Startet alle 8 Agenten als Subprozesse
  • Watchdog alle 60s — stirbt ein Agent → sofortiger Neustart
  • Tägl. 00:00 Telegram-Bericht: Revenue, MRR, Leads, Fehler
  • Registriert Stripe-Webhooks automatisch wenn Server bereit
  • Exponentielles Backoff bei Crash-Schleifen (max. 5min)
  • Läuft als macOS LaunchAgent = startet bei jedem Login automatisch

Starten:
  python3 modules/empire_controller.py           # Dauerbetrieb
  python3 modules/empire_controller.py --status  # Status aller Agenten
  python3 modules/empire_controller.py --report  # Sofort-Report an Telegram
  python3 modules/empire_controller.py --stop    # Alle Agenten beenden
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EMPIRE] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("EmpireController")

BASE = Path(__file__).resolve().parent.parent  # absoluter Pfad — kein CWD-Drift

# ── Env ──────────────────────────────────────────────────────────────────────

def _load_env():
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

def _tg_token()      -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()       -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _stripe_key()    -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _dashboard_url() -> str: return os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

PYTHON = "/usr/local/bin/python3"  # Python 3.13 mit aiohttp (Xcode-Python 3.9 hat kein aiohttp)

# ── Agent-Definitionen ────────────────────────────────────────────────────────

AGENTS = [
    {
        "name":         "Dashboard Server",
        "cmd":          [PYTHON, "dashboard/server.py"],
        "pid_file":     "/tmp/empire_server.pid",
        "log_file":     "/tmp/empire_server.log",
        "health_url":   "http://localhost:8888/health",
        "critical":     True,
        "startup_wait": 8,
        "env":          {"PORT": "8888", "DASHBOARD_PORT": "8888"},
    },
    {
        "name":     "Automation Scheduler",
        "cmd":      [PYTHON, "core/automation_scheduler.py"],
        "pid_file": "/tmp/empire_scheduler.pid",
        "log_file": "/tmp/empire_scheduler.log",
        "startup_wait": 3,
    },
    {
        "name":     "Outreach Agent",
        "cmd":      [PYTHON, "modules/outreach_autonomous.py"],
        "pid_file": "/tmp/empire_outreach.pid",
        "log_file": "/tmp/empire_outreach.log",
        "startup_wait": 2,
    },
    {
        "name":     "AI Act Scanner",
        "cmd":      [PYTHON, "modules/ai_act_scanner.py"],
        "pid_file": "/tmp/empire_ai_act.pid",
        "log_file": "/tmp/empire_ai_act.log",
        "startup_wait": 2,
    },
    {
        "name":     "Handelsregister Radar",
        "cmd":      [PYTHON, "modules/handelsregister_radar.py"],
        "pid_file": "/tmp/empire_handelsregister.pid",
        "log_file": "/tmp/empire_handelsregister.log",
        "startup_wait": 2,
    },
    {
        "name":     "ZVG Radar",
        "cmd":      [PYTHON, "modules/zvg_radar.py"],
        "pid_file": "/tmp/empire_zvg.pid",
        "log_file": "/tmp/empire_zvg.log",
        "startup_wait": 2,
    },
    {
        "name":     "KI-Leasing Reports",
        "cmd":      [PYTHON, "modules/ki_leasing_engine.py"],
        "pid_file": "/tmp/empire_ki_leasing.pid",
        "log_file": "/tmp/empire_ki_leasing.log",
        "startup_wait": 2,
    },
    {
        "name":     "Insolvenz Radar",
        "cmd":      [PYTHON, "modules/insolvenz_radar.py"],
        "pid_file": "/tmp/empire_insolvenz.pid",
        "log_file": "/tmp/empire_insolvenz.log",
        "startup_wait": 2,
    },
]

# ── Prozess-State ─────────────────────────────────────────────────────────────

class AgentProcess:
    def __init__(self, cfg: Dict):
        self.cfg          = cfg
        self.proc: Optional[subprocess.Popen] = None
        self.crashes      = 0
        self.last_start   = 0.0
        self.backoff      = 5   # Sekunden
        self.started_once = False

    @property
    def name(self) -> str:
        return self.cfg["name"]

    def is_alive(self) -> bool:
        if self.proc is None:
            return False
        return self.proc.poll() is None

    def start(self) -> bool:
        env = {**os.environ, **self.cfg.get("env", {})}
        log_path = self.cfg.get("log_file", f"/tmp/empire_{self.name.lower().replace(' ','_')}.log")
        try:
            with open(log_path, "a") as lf:
                self.proc = subprocess.Popen(
                    self.cfg["cmd"],
                    cwd=str(BASE),
                    env=env,
                    stdout=lf,
                    stderr=lf,
                    start_new_session=True,
                )
            pid_file = self.cfg.get("pid_file", "")
            if pid_file:
                Path(pid_file).write_text(str(self.proc.pid))
            self.last_start   = time.time()
            self.started_once = True
            log.info("▶ %s gestartet — PID %s", self.name, self.proc.pid)
            return True
        except Exception as e:
            log.error("✗ %s Start-Fehler: %s", self.name, e)
            return False

    def stop(self):
        if self.proc and self.is_alive():
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception as e:
                    log.warning("Ignored error: %s", e)
        pid_file = self.cfg.get("pid_file", "")
        if pid_file and Path(pid_file).exists():
            Path(pid_file).unlink(missing_ok=True)

    def next_backoff(self) -> float:
        b = min(self.backoff * (2 ** min(self.crashes, 5)), 300)
        return b


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    import urllib.request
    try:
        data = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=6)
    except Exception as e:
        log.warning("Telegram-Fehler: %s", e)


def _tg_sync(text: str):
    try:
        asyncio.get_event_loop().run_until_complete(_tg(text))
    except Exception as e:
        log.warning("Ignored error: %s", e)


# ── Health Check ──────────────────────────────────────────────────────────────

async def _http_health(url: str) -> bool:
    import urllib.request
    try:
        req = urllib.request.urlopen(url, timeout=4)
        data = json.loads(req.read().decode())
        return data.get("status") in ("ok", "healthy", True)
    except Exception:
        return False


# ── Stripe Webhook Auto-Registration ─────────────────────────────────────────

async def _register_stripe_webhooks():
    key       = _stripe_key()
    base_url  = _dashboard_url()
    if not key or not base_url:
        return

    webhooks_needed = [
        {
            "url":    f"{base_url}/api/ki-leasing/webhook",
            "events": ["checkout.session.completed", "customer.subscription.deleted",
                       "customer.subscription.updated", "customer.subscription.canceled"],
            "desc":   "KI-Leasing Abo-Management",
        },
        {
            "url":    f"{base_url}/webhook/stripe",
            "events": ["payment_intent.succeeded", "invoice.paid"],
            "desc":   "Stripe Allgemein",
        },
    ]

    import urllib.request, urllib.parse
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/x-www-form-urlencoded"}

    try:
        req      = urllib.request.Request("https://api.stripe.com/v1/webhook_endpoints?limit=100",
                                           headers={"Authorization": f"Bearer {key}"})
        resp     = urllib.request.urlopen(req, timeout=8)
        existing = json.loads(resp.read())
        existing_urls = {w["url"] for w in existing.get("data", [])}
    except Exception as e:
        log.warning("Stripe Webhook-Liste: %s", e)
        existing_urls = set()

    for wh in webhooks_needed:
        if wh["url"] in existing_urls:
            log.info("✓ Stripe Webhook bereits registriert: %s", wh["url"])
            continue
        try:
            body = urllib.parse.urlencode(
                {"url": wh["url"], "description": wh["desc"]}
                | {f"enabled_events[]": e for e in wh["events"]}
            ).encode()
            req  = urllib.request.Request(
                "https://api.stripe.com/v1/webhook_endpoints",
                data=body,
                headers=headers,
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=8)
            result = json.loads(resp.read())
            if "id" in result:
                log.info("✓ Stripe Webhook registriert: %s", wh["url"])
            else:
                log.warning("Stripe Webhook Fehler: %s", result)
        except Exception as e:
            log.warning("Stripe Webhook %s: %s", wh["url"], e)


# ── Daily Revenue Report ──────────────────────────────────────────────────────

async def _daily_report(agents: List[AgentProcess]):
    alive  = [a for a in agents if a.is_alive()]
    dead   = [a for a in agents if not a.is_alive()]
    uptime = int(time.time() - _START_TIME)
    h, m   = divmod(uptime // 60, 60)

    # KI-Leasing Stats
    ki_mrr    = 0
    ki_clients = 0
    ki_leads  = 0
    try:
        from modules.ki_leasing_engine import get_stats
        s          = get_stats()
        ki_mrr     = s.get("mrr_eur", 0)
        ki_clients = s.get("active_clients", 0)
        ki_leads   = s.get("leads_today", 0)
    except Exception as e:
        log.warning("Ignored error: %s", e)

    # Outreach Stats
    outreach_today = 0
    try:
        db = BASE / "data" / "outreach_autonomous.db"
        if db.exists():
            with sqlite3.connect(str(db)) as c:
                row = c.execute("SELECT COUNT(*) FROM outreach_log WHERE date(sent_at)=date('now')").fetchone()
                outreach_today = row[0] if row else 0
    except Exception as e:
        log.warning("Ignored error: %s", e)

    status_lines = ""
    for a in agents:
        icon  = "✅" if a.is_alive() else "❌"
        crash = f" ({a.crashes}x Crash)" if a.crashes else ""
        status_lines += f"\n  {icon} {a.name}{crash}"

    msg = (
        f"🏛 <b>Empire Tages-Report — {datetime.now().strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 <b>Revenue:</b>\n"
        f"  MRR (KI-Leasing): <b>€{ki_mrr}/Monat</b>\n"
        f"  Aktive Clients: <b>{ki_clients}</b>\n"
        f"  Leads heute gesendet: <b>{ki_leads}</b>\n\n"
        f"📧 <b>Outreach:</b>\n"
        f"  Emails heute: <b>{outreach_today}</b>\n\n"
        f"⚙️ <b>Agenten ({len(alive)}/{len(agents)} aktiv):</b>{status_lines}\n\n"
        f"⏱ Uptime: {h}h {m}m\n"
        f"🔁 Auto-Restart: EIN"
    )
    await _tg(msg)
    log.info("Daily Report gesendet")


# ── Controller Hauptlogik ─────────────────────────────────────────────────────

_START_TIME = time.time()
_RUNNING    = True


def _handle_sigterm(sig, frame):
    global _RUNNING
    log.info("SIGTERM erhalten — beende alle Agenten...")
    _RUNNING = False


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT,  _handle_sigterm)


async def run_empire():
    global _RUNNING

    agents = [AgentProcess(cfg) for cfg in AGENTS]

    await _tg(
        f"🏛 <b>Empire Controller gestartet</b>\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🔧 {len(agents)} Agenten werden gestartet..."
    )

    # Agenten der Reihe nach starten (Server zuerst)
    log.info("Starte alle Agenten...")
    for agent in agents:
        ok = agent.start()
        wait = agent.cfg.get("startup_wait", 2)
        await asyncio.sleep(wait)

        # Kritischen Server auf Health prüfen
        if agent.cfg.get("critical") and agent.cfg.get("health_url"):
            for attempt in range(15):
                if await _http_health(agent.cfg["health_url"]):
                    log.info("✓ %s ist healthy", agent.name)
                    break
                await asyncio.sleep(2)
            else:
                log.warning("⚠ %s antwortet nicht auf Health-Check", agent.name)

    # Nach Server-Start: Stripe Webhooks automatisch registrieren
    await asyncio.sleep(5)
    log.info("Registriere Stripe Webhooks...")
    await _register_stripe_webhooks()

    await _tg(
        f"✅ <b>Alle {len(agents)} Agenten gestartet</b>\n"
        f"🔗 Dashboard: <code>http://localhost:8888</code>\n"
        f"🔁 Watchdog: alle 60s"
    )

    # Watchdog Loop
    last_daily_report = 0
    watchdog_tick     = 0

    while _RUNNING:
        await asyncio.sleep(60)
        watchdog_tick += 1

        for agent in agents:
            if not agent.is_alive() and agent.started_once:
                elapsed = time.time() - agent.last_start
                backoff = agent.next_backoff()

                if elapsed < backoff:
                    continue

                agent.crashes += 1
                log.warning("⚠ %s ist ausgefallen (Crash #%d) — Neustart...", agent.name, agent.crashes)

                await _tg(
                    f"⚠️ <b>{agent.name} ausgefallen</b>\n"
                    f"Crash #{agent.crashes} — Neustart in {int(backoff)}s\n"
                    f"Backoff: {int(agent.next_backoff())}s"
                )

                ok = agent.start()
                if ok:
                    log.info("✓ %s neugestartet (Crash #%d)", agent.name, agent.crashes)

        # Midnight Daily Report
        now = datetime.now()
        if now.hour == 0 and now.minute < 2:
            day_stamp = now.strftime("%Y-%m-%d")
            if last_daily_report != day_stamp:
                last_daily_report = day_stamp
                await _daily_report(agents)

        # Status-Log alle 10 Minuten
        if watchdog_tick % 10 == 0:
            alive = sum(1 for a in agents if a.is_alive())
            log.info("Watchdog: %d/%d Agenten aktiv", alive, len(agents))

    # Shutdown
    log.info("Empire Controller wird beendet...")
    for agent in agents:
        log.info("Beende %s...", agent.name)
        agent.stop()
    await _tg("🛑 <b>Empire Controller beendet.</b> Alle Agenten gestoppt.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _status():
    print("\n  Empire Controller — Agent Status")
    print("  " + "─" * 44)
    for cfg in AGENTS:
        pid_file = cfg.get("pid_file", "")
        status   = "❓"
        pid_str  = ""
        if pid_file and Path(pid_file).exists():
            try:
                pid = int(Path(pid_file).read_text().strip())
                # check if process alive
                os.kill(pid, 0)
                status  = "✅ RUNNING"
                pid_str = f"  PID {pid}"
                log_f   = cfg.get("log_file", "")
                if log_f:
                    pid_str += f"  LOG: {log_f}"
            except ProcessLookupError:
                status = "❌ DEAD (PID-File veraltet)"
            except Exception:
                status = "❓ UNKNOWN"
        else:
            status = "⚫ NICHT GESTARTET"
        print(f"  {status:<22} {cfg['name']}{pid_str}")
    print()


def _stop_all():
    print("Beende alle Empire-Agenten...")
    for cfg in AGENTS:
        pid_file = cfg.get("pid_file", "")
        if pid_file and Path(pid_file).exists():
            try:
                pid = int(Path(pid_file).read_text().strip())
                os.kill(pid, signal.SIGTERM)
                Path(pid_file).unlink(missing_ok=True)
                print(f"  ✓ {cfg['name']} (PID {pid}) beendet")
            except Exception as e:
                print(f"  ✗ {cfg['name']}: {e}")
    # Kill by port 8888 as fallback
    try:
        subprocess.run(["pkill", "-f", "dashboard/server.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "empire_controller.py"], capture_output=True)
    except Exception as e:
        log.warning("Ignored error: %s", e)
    print("Done.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--status":
        _status()
    elif arg == "--stop":
        _stop_all()
    elif arg == "--report":
        print("Sende Sofort-Report...")
        agents = [AgentProcess(cfg) for cfg in AGENTS]
        asyncio.run(_daily_report(agents))
        print("Done.")
    else:
        log.info("Empire Controller v1.0 — starting...")
        asyncio.run(run_empire())
