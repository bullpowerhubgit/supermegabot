#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  RUDIBOT ARMY COMMANDER — Verwaltet alle Agenten                   ║
║  Startet, überwacht und koordiniert die komplette Bot-Army          ║
║  6 spezialisierte Agenten + Self-Healing + Telegram Reports        ║
║  + OpenClaw AI Integration für intelligente Entscheidungen          ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, sys, time, subprocess, signal, json, datetime, re, threading
from pathlib import Path

# OpenClaw Integration
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "rudibot-eternal"))
    from openclaw_ai_provider import SyncOpenClawAIProvider
    OPENCLAW_AVAILABLE = True
except ImportError:
    OPENCLAW_AVAILABLE = False

ARMY_DIR   = Path(__file__).parent
AGENTS_DIR = ARMY_DIR / "agents"
MICRO_DIR  = ARMY_DIR / "micro"
LOGS_DIR   = ARMY_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# .env laden bevor bus importiert wird
_env_path = ARMY_DIR.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(errors='ignore').splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _, _v = _line.partition('=')
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(ARMY_DIR / "shared"))
from bus import report, notify_telegram, load_state, get_env

AGENTS = [
    {"id": "resource_manager", "file": "agent_resource_manager.py", "icon": "🌡️", "desc": "Resource Manager"},
    {"id": "monitor",   "file": "agent_monitor.py",   "icon": "🔴", "desc": "Service Monitor"},
    {"id": "shopify",   "file": "agent_shopify.py",   "icon": "🛒", "desc": "Shopify Watcher"},
    {"id": "social",    "file": "agent_social.py",    "icon": "📱", "desc": "Social Autopilot"},
    {"id": "finance",   "file": "agent_finance.py",   "icon": "💰", "desc": "Finance Tracker"},
    {"id": "monetization", "file": "agent_monetization.py", "icon": "📈", "desc": "Revenue Tracker"},
    {"id": "learner",   "file": "agent_learner.py",   "icon": "🧠", "desc": "Auto Learner"},
    {"id": "security",  "file": "agent_security.py",  "icon": "🔐", "desc": "Security Guard"},
    {"id": "optimizer", "file": "agent_optimizer.py", "icon": "⚡", "desc": "Optimizer"},
]

# ── Micro Bots ────────────────────────────────────────────────────────────────
MICRO_DIR = ARMY_DIR / "micro"
MICRO_BOTS = [
    {"id": "micro_ping",    "file": "micro_ping.py",    "icon": "🏓", "desc": "Service Ping"},
    {"id": "micro_revenue", "file": "micro_revenue.py", "icon": "💸", "desc": "Revenue Tracker"},
    {"id": "micro_backup",  "file": "micro_backup.py",  "icon": "💾", "desc": "Auto Backup"},
    {"id": "micro_clean",   "file": "micro_clean.py",   "icon": "🧹", "desc": "Log Cleaner"},
    {"id": "micro_ai",      "file": "micro_ai.py",      "icon": "🤖", "desc": "KI-Tipp Daily"},
]

running_procs = {}
crash_history = {}  # aid -> list of timestamps
central_error_log = LOGS_DIR / "central_errors.log"

def log_error(source, message):
    """Zentrale Fehlerlog-Datei — nie wieder Fehler verlieren"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{source}] {message}\n"
    with open(central_error_log, "a") as f:
        f.write(line)

def rotate_logs(max_size_mb=10):
    """Rotiert Log-Dateien wenn sie zu groß werden — verhindert Disk-Full"""
    try:
        for log_file in LOGS_DIR.glob("*.log"):
            size_mb = log_file.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                # Backup erstellen, dann auf letzte 500 Zeilen kürzen
                backup = LOGS_DIR / f"{log_file.stem}.old.log"
                log_file.rename(backup)
                with open(backup, "r") as f:
                    lines = f.readlines()
                with open(log_file, "w") as f:
                    f.writelines(lines[-500:])
                log_error("LOG_ROTATE", f"Rotiert: {log_file.name} ({size_mb:.1f}MB -> {len(lines[-500:])} Zeilen)")
    except Exception:
        pass

def kill_duplicate_processes(script_name):
    """Killt alle alten Instanzen desselben Scripts — verhindert Duplikate"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str)
                    if pid != os.getpid() and pid != os.getppid():
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.5)
                        try:
                            os.kill(pid, 0)
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
    except Exception:
        pass

def start_agent(agent, base_dir=None):
    base_dir = base_dir or AGENTS_DIR
    aid = agent["id"]
    script = base_dir / agent["file"]
    log = LOGS_DIR / f"{aid}.log"

    if not script.exists():
        log_error("START", f"Script nicht gefunden: {script}")
        return False

    # 1. Kill alte Duplikate
    kill_duplicate_processes(str(script))
    time.sleep(0.3)

    # 2. Prüfe ob schon in running_procs
    if aid in running_procs:
        p = running_procs[aid]
        if p.poll() is None:
            return True
        del running_procs[aid]

    print(f"  {agent['icon']} Starte {agent['desc']} ({aid})...")
    log_error("START", f"Starte {aid}")
    with open(log, "a") as lf:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH","")
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=lf, stderr=lf,
            start_new_session=True, env=env
        )
        running_procs[aid] = proc
        return True

def stop_all():
    print("🛑 Stoppe alle Agenten...")
    for aid, proc in running_procs.items():
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print("✅ Alle gestoppt")

def status_report():
    state = load_state()
    agents = state.get("agents", {})
    lines = []
    for a in AGENTS:
        aid = a["id"]
        info = agents.get(aid, {})
        status_icon = {"ok":"✅","warning":"⚠️","error":"❌","repaired":"🔧"}.get(info.get("status","?"),"❓")
        msg = info.get("message","Keine Daten")[:60]
        ts = info.get("ts","?")
        lines.append(f"{a['icon']} <b>{a['desc']}</b>: {status_icon} {msg}")
    return "\n".join(lines)

# ── Multi-Account Health Check ──────────────────────────────────────────────
EMAILS = [
    "dragonadnp@gmail.com",
    "nikolestimi@gmail.com",
    "bullpowersrtkennels@gmail.com",
    "looopwave@gmail.com",
    "aitecbuuss@gmail.com",
    "rudolf.sarkany@aitec.de",
    "rudolf.sarkany.aiitec@gmail.com",
]

PLATFORM_ENDPOINTS = {
    "shopify": "https://partners.shopify.com/",
    "stripe": "https://dashboard.stripe.com/apikeys",
    "hubspot": "https://developers.hubspot.com/",
    "slack": "https://api.slack.com/apps",
    "jira": "https://id.atlassian.com/manage-profile/security/api-tokens",
    "sendgrid": "https://app.sendgrid.com/settings/api_keys",
    "mailchimp": "https://us1.admin.mailchimp.com/account/api/",
    "aws": "https://console.aws.amazon.com/iam/",
    "google": "https://console.cloud.google.com/apis/credentials",
    "openai": "https://platform.openai.com/api-keys",
    "github": "https://github.com/settings/tokens",
    "notion": "https://www.notion.so/my-integrations",
    "airtable": "https://airtable.com/create/tokens",
    "heroku": "https://dashboard.heroku.com/account",
    "cloudflare": "https://dash.cloudflare.com/profile/api-tokens",
    "pipedrive": "https://app.pipedrive.com/settings/api",
    "zendesk": "https://support.zendesk.com/hc/en-us/articles/203663866",
    "intercom": "https://app.intercom.com/a/apps/",
    "klaviyo": "https://www.klaviyo.com/settings/account/api-keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
}

def health_check_all_accounts():
    """Prüft alle Konten gegen alle Plattformen — nie wieder 'API gut' für nur ein Konto"""
    results = []
    try:
        # Prüfe welche .env-Dateien welche E-Mails enthalten
        search_paths = [
            Path.home() / "windsurf",
            Path.home() / "supermegabot",
            Path.home() / "windsurf-shopify-suite",
            Path.home() / "windsurf-api-gateway",
        ]
        email_platforms = {email: set() for email in EMAILS}

        for base in search_paths:
            if not base.exists():
                continue
            for env_file in base.rglob(".env*"):
                if env_file.stat().st_size > 500000:
                    continue
                try:
                    text = env_file.read_text(errors='ignore')
                    for email in EMAILS:
                        if email in text:
                            # Finde zugehörige Plattform aus Dateiname
                            fname = env_file.name.lower()
                            for plat in PLATFORM_ENDPOINTS:
                                if plat in fname or plat in str(env_file.parent).lower():
                                    email_platforms[email].add(plat)
                            # Auch aus Inhalt
                            for plat in PLATFORM_ENDPOINTS:
                                if plat.upper() in text.upper():
                                    email_platforms[email].add(plat)
                except Exception:
                    pass

        # Baue Report
        for email in EMAILS:
            plats = sorted(email_platforms[email])
            status = "✅" if plats else "⚠️"
            results.append(f"{status} {email}\n    → {', '.join(plats) if plats else 'KEINE Plattformen gefunden'}")

        # Warnung wenn bullpowersrtkennels alle hat
        bp = email_platforms["bullpowersrtkennels@gmail.com"]
        others = {e: p for e, p in email_platforms.items() if e != "bullpowersrtkennels@gmail.com" and p}
        if len(bp) > 10 and len(others) <= 2:
            results.append("\n🔴 WARNUNG: Fast alle Plattformen nur bei bullpowersrtkennels@gmail.com!")
            results.append("   Andere Konten untergenutzt. Prüfe ob Konten auf anderen Plattformen registriert sind.")

    except Exception as e:
        log_error("HEALTH_CHECK", str(e))
        results.append(f"❌ Fehler: {e}")

    return "\n".join(results)

def check_memory_leak():
    """Erkennt Memory-Leaks durch RAM-Trend-Analyse"""
    try:
        out = subprocess.run("vm_stat", shell=True, capture_output=True, text=True, timeout=5).stdout
        vals = {}
        for line in out.splitlines():
            if ":" in line:
                k = line.split(":")[0].strip().replace('"', '')
                v = line.split(":")[1].strip().rstrip('.')
                try:
                    vals[k] = int(v)
                except ValueError:
                    pass
        page = 16384
        used = vals.get("Pages active", 0) + vals.get("Pages wired down", 0) + vals.get("Pages occupied by compressor", 0)
        total = used + vals.get("Pages free", 0) + vals.get("Pages inactive", 0) + vals.get("Pages speculative", 0)
        if total > 0:
            pct = (used / total) * 100
            if pct > 90:
                log_error("MEMORY", f"KRITISCH: RAM bei {pct:.1f}%")
                return f"🔴 KRITISCH: RAM {pct:.1f}%"
            elif pct > 75:
                return f"🟠 WARNUNG: RAM {pct:.1f}%"
        return "✅ RAM OK"
    except Exception as e:
        return f"❌ RAM-Check fehlgeschlagen: {e}"

def monetization_snapshot():
    """Sammelt Umsatz-Daten aus allen verfügbaren Quellen"""
    revenue = 0.0
    sources = []
    # Stripe prüfen
    try:
        stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if stripe_key:
            import urllib.request
            req = urllib.request.Request(
                "https://api.stripe.com/v1/charges?limit=1",
                headers={"Authorization": f"Bearer {stripe_key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("data"):
                    revenue = sum(ch.get("amount", 0) for ch in data["data"]) / 100
                    sources.append(f"Stripe: €{revenue:.2f}")
    except Exception:
        pass
    return sources, revenue

def run():
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║   🤖 RUDIBOT ARMY COMMANDER — Meta-Supervisor v2.0                 ║")
    print("║   Deduplication | Crash-Backoff | Multi-Account | Self-Healing     ║")
    print(f"║   {len(AGENTS)} Agenten + {len(MICRO_BOTS)} Micro Bots werden gestartet                    ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()

    # Cleanup: Kill alle alten rudibot-army Prozesse außer uns selbst
    print("🧹 Bereinige alte Prozesse...")
    kill_duplicate_processes("rudibot-army")
    time.sleep(1)

    # Log-Rotation vor Start (verhindert Disk-Full)
    print("🔄 Rotiere Logs...")
    rotate_logs()

    # Alle Agenten starten
    for agent in AGENTS:
        start_agent(agent, AGENTS_DIR)
        time.sleep(1)

    # Micro Bots starten
    print("\n  ── Micro Bots ──")
    for bot in MICRO_BOTS:
        start_agent(bot, MICRO_DIR)
        time.sleep(0.5)

    total = len(AGENTS) + len(MICRO_BOTS)
    print(f"\n✅ {len(AGENTS)} Agenten + {len(MICRO_BOTS)} Micro Bots = {total} gesamt\n")
    notify_telegram(
        f"🤖 <b>RudiBot Army v2.0 online!</b>\n"
        f"Meta-Supervisor aktiv: Deduplication + Crash-Backoff + Multi-Account\n"
        f"{len(AGENTS)} Agenten + {len(MICRO_BOTS)} Micro Bots gestartet."
    )

    def shutdown(sig, frame):
        stop_all()
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    last_report = time.time()
    last_health_check = 0
    last_memory_check = 0
    last_log_rotate = 0
    all_workers = AGENTS + MICRO_BOTS

    while True:
        now = time.time()

        # ── Alle 30 Min: Log-Rotation (verhindert Disk-Full) ──
        if now - last_log_rotate > 1800:
            rotate_logs()
            last_log_rotate = now

        # ── Watchdog: Agenten + Micro Bots ──
        for agent in AGENTS:
            aid = agent["id"]
            proc = running_procs.get(aid)
            if proc and proc.poll() is not None:
                # Crash-Tracking mit Backoff
                if aid not in crash_history:
                    crash_history[aid] = []
                crash_history[aid].append(now)
                # Alte Crashes (>10min) entfernen
                crash_history[aid] = [t for t in crash_history[aid] if now - t < 600]
                crash_count = len(crash_history[aid])

                if crash_count >= 10:
                    log_error("CRASH", f"{aid}: {crash_count} Crashes in 10min — BACKOFF")
                    notify_telegram(f"🛑 <b>{aid}</b> ist {crash_count}× in 10min gecrasht! Warte 60s vor Neustart.")
                    time.sleep(60)
                elif crash_count >= 5:
                    log_error("CRASH", f"{aid}: {crash_count} Crashes in 10min")
                    notify_telegram(f"⚠️ <b>{aid}</b> ist {crash_count}× in 10min gecrasht — möglicher Bug!")

                print(f"⚠️  {agent['icon']} {aid} gecrasht (#{crash_count}), neustart...")
                start_agent(agent, AGENTS_DIR)

        for bot in MICRO_BOTS:
            bid = bot["id"]
            proc = running_procs.get(bid)
            if proc and proc.poll() is not None:
                if bid not in crash_history:
                    crash_history[bid] = []
                crash_history[bid].append(now)
                crash_history[bid] = [t for t in crash_history[bid] if now - t < 600]
                crash_count = len(crash_history[bid])

                if crash_count >= 10:
                    log_error("CRASH", f"{bid}: {crash_count} Crashes in 10min — BACKOFF")
                    time.sleep(60)
                start_agent(bot, MICRO_DIR)

        # ── Alle 30 Min: Multi-Account Health Check ──
        if now - last_health_check > 1800:
            health_report = health_check_all_accounts()
            log_error("HEALTH", health_report[:200])
            # Nur bei Problemen melden
            if "WARNUNG" in health_report or "KEINE" in health_report:
                notify_telegram(f"📊 <b>Multi-Account Health Check</b>\n{health_report[:800]}")
            last_health_check = now

        # ── Alle 5 Min: Memory-Leak Check ──
        if now - last_memory_check > 300:
            mem_status = check_memory_leak()
            if "KRITISCH" in mem_status or "WARNUNG" in mem_status:
                log_error("MEMORY", mem_status)
                notify_telegram(f"🌡️ <b>System-Status</b>\n{mem_status}")
            last_memory_check = now

        # ── Stündlicher Status-Report ──
        if now - last_report > 3600:
            report_txt = status_report()
            notify_telegram(f"📊 <b>Army Status</b>\n{report_txt}")
            last_report = now

        time.sleep(15)

if __name__ == "__main__":
    run()
