#!/usr/bin/env python3
"""
Telegram Control Panel — Inline-Keyboard Steuerung für den kompletten Bot.
Wird in mega_orchestrator.py eingebunden.
"""
import html
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any

BASE_DIR   = Path(__file__).parent.parent
ARMY_STATE = BASE_DIR / "rudibot-army" / "shared" / "army_state.json"
_HOME      = Path.home()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or os.getenv("TELEGRAM_BOT_TOKEN_2") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL  = os.getenv("DASHBOARD_URL", "http://localhost:8888")

# Externe Projekte — aus Env oder Standard-Pfad
_ETERNAL_DIR  = Path(os.getenv("ETERNAL_BOT_DIR",  str(_HOME / "rudibot-eternal")))

# KIVO: liegt im telegram-automation-bot Verzeichnis, startet via .command
_KIVO_BASE    = Path(os.getenv("KIVO_DIR", str(_HOME / "telegram-automation-bot")))
_KIVO_SCRIPT  = _KIVO_BASE / "kivo.py"
_KIVO_COMMAND = _KIVO_BASE / "KIVO.command"
_KIVO_LOG     = str(_KIVO_BASE / "logs" / "kivo.log")

_SHOPIFY_SUITE_URL = os.getenv("SHOPIFY_SUITE_URL",
                                "https://shopify-suite-v2-production.up.railway.app")


# ── Low-level Telegram helpers ───────────────────────────────────────────────

def _tg(method: str, payload: dict) -> dict:
    if not TELEGRAM_TOKEN:
        return {}
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            data=data, headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=8)
        return json.loads(r.read())
    except Exception:
        return {}


def send_message(chat_id: str, text: str, keyboard: list | None = None,
                 parse_mode: str = "HTML") -> dict:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _tg("sendMessage", payload)


def edit_message(chat_id: str, message_id: int, text: str,
                 keyboard: list | None = None, parse_mode: str = "HTML") -> dict:
    payload: dict = {
        "chat_id": chat_id, "message_id": message_id,
        "text": text, "parse_mode": parse_mode,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _tg("editMessageText", payload)


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    return _tg("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})


def _call_dashboard(path: str, method: str = "GET", body: dict | None = None) -> dict:
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{DASHBOARD_URL}{path}", data=data, method=method,
        )
        if data:
            req.add_header("Content-Type", "application/json")
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read())
    except Exception:
        return {}


# ── Keyboard Layouts ─────────────────────────────────────────────────────────

def kb_main() -> list:
    return [
        [{"text": "📊 System Status",    "callback_data": "menu:status"},
         {"text": "💰 Monetization",     "callback_data": "menu:monetization"}],
        [{"text": "🌐 SEO & Traffic",    "callback_data": "menu:seo"},
         {"text": "🗂 Alle Projekte",    "callback_data": "menu:projects"}],
        [{"text": "🪖 Army Control",     "callback_data": "menu:army"},
         {"text": "🔧 Services",         "callback_data": "menu:services"}],
        [{"text": "🩺 Self-Repair",      "callback_data": "menu:repair"},
         {"text": "⚡ Quick Actions",    "callback_data": "menu:actions"}],
        [{"text": "🛒 Shopify",          "callback_data": "menu:shopify"},
         {"text": "♾️ Eternal Bot",      "callback_data": "menu:eternal"}],
        [{"text": "📋 Logs",             "callback_data": "menu:logs"},
         {"text": "🎙️ KIVO Voice",       "callback_data": "menu:kivo"}],
    ]

def kb_back() -> list:
    return [[{"text": "◀️ Hauptmenü", "callback_data": "menu:main"}]]

def kb_army() -> list:
    return [
        [{"text": "▶️ Army starten",   "callback_data": "army:start"},
         {"text": "⏹ Army stoppen",   "callback_data": "army:stop"}],
        [{"text": "🔄 Status refresh", "callback_data": "army:status"},
         {"text": "📜 Events",         "callback_data": "army:events"}],
        [{"text": "◀️ Hauptmenü",      "callback_data": "menu:main"}],
    ]

def kb_repair() -> list:
    return [
        [{"text": "🔍 Deep Scan",       "callback_data": "repair:scan"},
         {"text": "🔧 Auto-Repair",     "callback_data": "repair:run"}],
        [{"text": "🧹 Logs bereinigen", "callback_data": "repair:clean"},
         {"text": "💾 Git Backup",      "callback_data": "repair:backup"}],
        [{"text": "🔄 Services restart","callback_data": "repair:restart_all"}],
        [{"text": "◀️ Hauptmenü",       "callback_data": "menu:main"}],
    ]

def kb_logs() -> list:
    return [
        [{"text": "🤖 Army Logs",       "callback_data": "logs:army"},
         {"text": "🧩 Orchestrator",    "callback_data": "logs:orchestrator"}],
        [{"text": "🧠 Ollama",          "callback_data": "logs:ollama"},
         {"text": "🩺 Self-Healer",     "callback_data": "logs:healer"}],
        [{"text": "◀️ Hauptmenü",       "callback_data": "menu:main"}],
    ]

def kb_actions() -> list:
    return [
        [{"text": "📤 Git Push",         "callback_data": "action:git_push"},
         {"text": "🔄 Dashboard restart","callback_data": "action:restart_dashboard"}],
        [{"text": "🧠 Ollama restart",   "callback_data": "action:restart_ollama"},
         {"text": "🧹 /tmp Logs löschen","callback_data": "action:clean_tmp"}],
        [{"text": "📊 PM2 Status",       "callback_data": "action:pm2_status"},
         {"text": "🏥 Health Check",     "callback_data": "action:health"}],
        [{"text": "◀️ Hauptmenü",        "callback_data": "menu:main"}],
    ]

def kb_eternal() -> list:
    return [
        [{"text": "▶️ Starten",   "callback_data": "eternal:start"},
         {"text": "⏹ Stoppen",   "callback_data": "eternal:stop"}],
        [{"text": "↺ Restart",   "callback_data": "eternal:restart"},
         {"text": "📊 Status",   "callback_data": "eternal:status"}],
        [{"text": "📋 Logs",     "callback_data": "eternal:logs"}],
        [{"text": "◀️ Hauptmenü","callback_data": "menu:main"}],
    ]

def kb_kivo() -> list:
    return [
        [{"text": "▶️ Starten",   "callback_data": "kivo:start"},
         {"text": "⏹ Stoppen",   "callback_data": "kivo:stop"}],
        [{"text": "↺ Restart",   "callback_data": "kivo:restart"},
         {"text": "📊 Status",   "callback_data": "kivo:status"}],
        [{"text": "📋 Logs",     "callback_data": "kivo:logs"}],
        [{"text": "◀️ Hauptmenü","callback_data": "menu:main"}],
    ]

def kb_railway() -> list:
    return [
        [{"text": "🌐 Status prüfen",  "callback_data": "railway:status"},
         {"text": "🔄 Health-Check",   "callback_data": "railway:health"}],
        [{"text": "📋 Logs (Railway)", "callback_data": "railway:logs"}],
        [{"text": "◀️ Hauptmenü",      "callback_data": "menu:main"}],
    ]


def kb_monetization() -> list:
    return [
        [{"text": "👥 Leads anzeigen",     "callback_data": "money:leads"},
         {"text": "💰 Revenue heute",       "callback_data": "money:revenue"}],
        [{"text": "🔍 Audit-Seite öffnen", "url": "https://bullpower-lead.netlify.app"},
         {"text": "💳 Stripe Dashboard",   "url": "https://dashboard.stripe.com"}],
        [{"text": "📈 Portal öffnen",      "url": "https://bullpower-hub-portal.netlify.app"}],
        [{"text": "◀️ Hauptmenü",          "callback_data": "menu:main"}],
    ]


def kb_seo() -> list:
    return [
        [{"text": "✍️ Artikel generieren", "callback_data": "seo:generate"},
         {"text": "🏓 Sitemaps pingen",     "callback_data": "seo:ping"}],
        [{"text": "📣 Social Drafts",       "callback_data": "seo:social"},
         {"text": "📝 Blog ansehen",        "url": "https://shopify-automaton-suite.netlify.app/blog/"}],
        [{"text": "◀️ Hauptmenü",           "callback_data": "menu:main"}],
    ]


def kb_projects() -> list:
    return [
        [{"text": "🤖 SuperMegaBot",        "callback_data": "proj:smb"},
         {"text": "🛒 Shopify Acquisition",  "callback_data": "proj:acquisition"}],
        [{"text": "🔍 SEO Turbo Tools",      "callback_data": "proj:seo"},
         {"text": "📊 SteuercockPit",        "callback_data": "proj:steuer"}],
        [{"text": "💰 iComeAuto",            "callback_data": "proj:icome"},
         {"text": "📢 AdPoster Engine",      "callback_data": "proj:adposter"}],
        [{"text": "🚗 MacOBD-Pro",           "callback_data": "proj:macobd"},
         {"text": "💻 local-coder",          "callback_data": "proj:localcoder"}],
        [{"text": "◀️ Hauptmenü",            "callback_data": "menu:main"}],
    ]


_RAILWAY_SERVICES = {
    "smb":         ("SuperMegaBot",          "https://dudirudibot-mega-production.up.railway.app"),
    "acquisition": ("Shopify Acquisition",   "https://shopify-acquisition-engine-production.up.railway.app"),
    "seo":         ("SEO Turbo Tools",       "https://seo-turbo-tools-production.up.railway.app"),
    "steuer":      ("SteuercockPit",         "https://steuercockpit-production-44c9.up.railway.app"),
    "icome":       ("iComeAuto",             "https://icomeauto-production-e4e5.up.railway.app"),
    "adposter":    ("AdPoster Engine",       "https://adposter-engine-production-2d15.up.railway.app"),
}


def _check_railway_service(key: str) -> str:
    name, url = _RAILWAY_SERVICES[key]
    try:
        r = urllib.request.urlopen(f"{url}/health", timeout=8)
        body = json.loads(r.read().decode())
        status = body.get("status", "?")
        icon = "🟢" if status == "ok" else "🟡"
        extra = ""
        if "stripe" in body:
            extra += f"\n💳 Stripe: {'✅' if body['stripe'] else '❌'}"
        if "uptime" in body:
            up = body["uptime"]
            extra += f"\n⏱ Uptime: {int(up)//3600}h {(int(up)%3600)//60}m"
        if "cycles_done" in body:
            extra += f"\n🔄 Cycles: {body['cycles_done']}"
        return f"{icon} <b>{name}</b>\n\nStatus: {status}{extra}\n🔗 <a href='{url}'>{url}</a>"
    except Exception as e:
        return f"🔴 <b>{name}</b>\n\nFehler: {str(e)[:120]}\n🔗 {url}"
# ── Content Builder ──────────────────────────────────────────────────────────

def _get_system_status() -> str:
    lines = ["<b>📊 System Status</b>", ""]
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=1)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        lines += [
            f"🖥 CPU: {cpu:.0f}%",
            f"🧠 RAM: {mem.percent:.0f}% ({mem.available//1024//1024} MB frei)",
            f"💾 Disk: {disk.percent:.0f}% ({disk.free//1024//1024//1024} GB frei)",
            "",
        ]
    except ImportError:
        lines.append("psutil nicht verfügbar")

    # Dashboard ping
    d = _call_dashboard("/health")
    if d.get("status") == "ok":
        lines.append("🟢 Dashboard (8888): Online")
    else:
        lines.append("🔴 Dashboard (8888): Offline")

    # Ollama ping
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        lines.append("🟢 Ollama (11434): Online")
    except Exception:
        lines.append("🔴 Ollama (11434): Offline")

    # Army status
    try:
        r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                           capture_output=True, text=True)
        army_on = r.returncode == 0 and bool(r.stdout.strip())
        lines.append(f"{'🟢' if army_on else '🔴'} Army Commander: {'Online' if army_on else 'Offline'}")
    except Exception:
        lines.append("❓ Army: Status unbekannt")

    lines.append(f"\n🕐 {time.strftime('%H:%M:%S')}")
    return "\n".join(lines)


def _get_army_status() -> str:
    lines = ["<b>🪖 RudiBot Army Status</b>", ""]
    try:
        if ARMY_STATE.exists():
            state = json.loads(ARMY_STATE.read_text(errors="ignore"))
            agents = state.get("agents", {})
            if agents:
                for aid, info in agents.items():
                    icon = {"ok": "✅", "warning": "⚠️", "error": "❌",
                            "repaired": "🔧"}.get(info.get("status", "?"), "❓")
                    msg = info.get("message", "")[:50]
                    lines.append(f"{icon} <b>{aid}</b>: {msg}")
            else:
                lines.append("Keine Agenten-Daten (Army noch nicht gestartet?)")
        else:
            lines.append("army_state.json nicht gefunden — Army nicht aktiv")
    except Exception as e:
        lines.append(f"Fehler: {e}")
    return "\n".join(lines)


def _get_army_events() -> str:
    lines = ["<b>📜 Army Events (letzte 10)</b>", ""]
    try:
        if ARMY_STATE.exists():
            state = json.loads(ARMY_STATE.read_text(errors="ignore"))
            for e in state.get("events", [])[-10:]:
                lines.append(f"[{e.get('ts','')}] <b>{e.get('agent','?')}</b>: {e.get('msg','')[:60]}")
    except Exception as e:
        lines.append(f"Fehler: {e}")
    return "\n".join(lines)


def _get_log_tail(log_path: str, lines: int = 20) -> str:
    try:
        p = Path(log_path)
        if not p.exists():
            return f"Log nicht gefunden: {log_path}"
        result = []
        with p.open("rb") as f:
            f.seek(0, 2)
            remaining = f.tell()
            buf = b""
            while len(result) <= lines and remaining > 0:
                chunk = min(4096, remaining)
                remaining -= chunk
                f.seek(remaining)
                buf = f.read(chunk) + buf
                result = buf.split(b"\n")
        tail = [l.decode("utf-8", errors="ignore") for l in result[-lines:]]
        return "\n".join(tail)
    except Exception as e:
        return f"Fehler: {e}"


def _run_repair_scan() -> str:
    lines = ["<b>🔍 Deep Scan Ergebnis</b>", ""]
    checks = {
        "Dashboard": lambda: _call_dashboard("/health").get("status") == "ok",
        "Ollama": lambda: bool(urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)),
        "Army State": lambda: ARMY_STATE.exists(),
        "army_commander": lambda: bool(subprocess.run(["pgrep","-f","army_commander.py"],
                                                       capture_output=True).stdout.strip()),
        "mega_orchestrator": lambda: bool(subprocess.run(["pgrep","-f","mega_orchestrator.py"],
                                                          capture_output=True).stdout.strip()),
    }
    ok_count = 0
    for name, check in checks.items():
        try:
            ok = check()
        except Exception:
            ok = False
        lines.append(f"{'✅' if ok else '❌'} {name}")
        if ok:
            ok_count += 1

    lines.append(f"\n<b>Ergebnis: {ok_count}/{len(checks)} OK</b>")
    return "\n".join(lines)


def _army_start() -> str:
    try:
        r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return "🪖 Army läuft bereits"
        with open("/tmp/rudibot-army.log", "a") as lf:
            subprocess.Popen(
                [sys.executable, str(BASE_DIR / "rudibot-army" / "army_commander.py")],
                stdout=lf, stderr=lf, start_new_session=True,
            )
        return "▶️ Army gestartet — warte 10s auf Initialisierung"
    except Exception as e:
        return f"❌ Fehler: {e}"


def _army_stop() -> str:
    try:
        r = subprocess.run(["pkill", "-f", "army_commander.py"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return "⏹ Army gestoppt"
        return "⏹ Army war nicht aktiv"
    except Exception as e:
        return f"❌ Fehler: {e}"


def _clean_logs() -> str:
    cleaned = []
    for logfile in Path("/tmp").glob("*.log"):
        try:
            size = logfile.stat().st_size
            if size > 10 * 1024 * 1024:  # > 10 MB
                keep_lines = 5000
                result = []
                with logfile.open("rb") as f:
                    f.seek(0, 2)
                    remaining = f.tell()
                    buf = b""
                    while len(result) <= keep_lines and remaining > 0:
                        chunk = min(65536, remaining)
                        remaining -= chunk
                        f.seek(remaining)
                        buf = f.read(chunk) + buf
                        result = buf.split(b"\n")
                tail_bytes = b"\n".join(result[-keep_lines:])
                logfile.write_bytes(tail_bytes)
                cleaned.append(f"{logfile.name} ({size//1024//1024}MB → 5k Zeilen)")
        except Exception:
            pass
    if cleaned:
        return "🧹 Logs bereinigt:\n" + "\n".join(cleaned)
    return "🧹 Keine Logs > 10MB gefunden"


def _git_backup() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(BASE_DIR), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if not r.stdout.strip():
            return "💾 Nichts zu committen — alles aktuell"
        ts = time.strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "-C", str(BASE_DIR), "add", "-A"],
                       capture_output=True, timeout=15)
        subprocess.run(["git", "-C", str(BASE_DIR), "commit", "-m", f"Auto-Backup {ts}"],
                       capture_output=True, timeout=15)
        branch = subprocess.run(
            ["git", "-C", str(BASE_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip() or "main"
        pr = subprocess.run(
            ["git", "-C", str(BASE_DIR), "push", "origin", branch],
            capture_output=True, text=True, timeout=60,
        )
        if pr.returncode == 0:
            return f"✅ Git Backup OK ({ts})"
        return f"⚠️ Push-Fehler: {pr.stderr[:100]}"
    except Exception as e:
        return f"❌ {e}"


def _restart_service(service_name: str) -> str:
    targets = {
        "dashboard":    ["pkill", "-f", "dashboard/server.py"],
        "ollama":       ["pkill", "-f", "ollama"],
        "army":         ["pkill", "-f", "army_commander.py"],
        "orchestrator": ["pkill", "-f", "mega_orchestrator.py"],
    }
    starts = {
        "dashboard":    [sys.executable, str(BASE_DIR / "dashboard" / "server.py")],
        "ollama":       ["ollama", "serve"],
        "army":         [sys.executable, str(BASE_DIR / "rudibot-army" / "army_commander.py")],
        "orchestrator": [sys.executable, str(BASE_DIR / "core" / "mega_orchestrator.py")],
    }
    kill_cmd = targets.get(service_name)
    start_cmd = starts.get(service_name)
    if not kill_cmd:
        return f"Unbekannter Service: {service_name}"
    try:
        subprocess.run(kill_cmd, capture_output=True)
        time.sleep(1)
        if start_cmd:
            log_path = f"/tmp/{service_name}.log"
            with open(log_path, "a") as lf:
                subprocess.Popen(start_cmd, stdout=lf, stderr=lf,
                                 start_new_session=True, cwd=str(BASE_DIR))
        return f"🔄 {service_name} neugestartet"
    except Exception as e:
        return f"❌ Fehler: {e}"


def _pm2_status() -> str:
    try:
        r = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return "PM2 nicht verfügbar oder nicht gestartet"
        procs = json.loads(r.stdout)
        lines = ["<b>📊 PM2 Prozesse</b>", ""]
        for p in procs:
            name = p.get("name", "?")
            status = p.get("pm2_env", {}).get("status", "?")
            icon = "🟢" if status == "online" else "🔴"
            pid = p.get("pid", "?")
            lines.append(f"{icon} <b>{name}</b> (PID {pid}): {status}")
        return "\n".join(lines) if len(lines) > 2 else "Keine PM2 Prozesse"
    except Exception as e:
        return f"PM2 Fehler: {e}"


def _external_service_control(name: str, script_path: Path, log_path: str,
                               action: str) -> str:
    """Generischer Start/Stop/Status für externe Python-Services."""
    pattern = script_path.name
    if action == "status":
        try:
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
            running = r.returncode == 0 and bool(r.stdout.strip())
            pid = r.stdout.strip().split("\n")[0] if running else "-"
            return (f"{'🟢' if running else '🔴'} <b>{name}</b>\n"
                    f"Status: {'Läuft' if running else 'Gestoppt'}"
                    + (f" (PID {pid})" if running else "")
                    + f"\nPfad: <code>{script_path.parent}</code>"
                    + ("" if script_path.parent.exists() else "\n⚠️ Verzeichnis nicht gefunden"))
        except Exception as e:
            return f"❌ Status-Fehler: {e}"

    elif action == "start":
        if not script_path.exists():
            return f"❌ {name}: Skript nicht gefunden\n<code>{script_path}</code>"
        try:
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True)
            if r.returncode == 0 and r.stdout.strip():
                return f"ℹ️ {name} läuft bereits"
            with open(log_path, "a") as lf:
                subprocess.Popen([sys.executable, str(script_path)],
                                 stdout=lf, stderr=lf, start_new_session=True,
                                 cwd=str(script_path.parent))
            return f"▶️ {name} gestartet"
        except Exception as e:
            return f"❌ Start-Fehler: {e}"

    elif action == "stop":
        try:
            r = subprocess.run(["pkill", "-f", pattern], capture_output=True)
            return f"⏹ {name} {'gestoppt' if r.returncode == 0 else 'war nicht aktiv'}"
        except Exception as e:
            return f"❌ Stop-Fehler: {e}"

    elif action == "restart":
        stop_msg = _external_service_control(name, script_path, log_path, "stop")
        time.sleep(1)
        start_msg = _external_service_control(name, script_path, log_path, "start")
        return f"{stop_msg}\n{start_msg}"

    elif action == "logs":
        return f"📋 {name} Logs:\n<pre>{_get_log_tail(log_path, 20)}</pre>"

    return f"Unbekannte Aktion: {action}"


def _kivo_status() -> str:
    lines = ["🎙️ <b>KIVO Voice</b>", ""]
    try:
        r = subprocess.run(["pgrep", "-f", "kivo.py"], capture_output=True, text=True)
        running = r.returncode == 0 and bool(r.stdout.strip())
        pid = r.stdout.strip().split("\n")[0] if running else "-"
        lines.append(f"{'🟢 Läuft' if running else '🔴 Gestoppt'}"
                     + (f" (PID {pid})" if running else ""))
    except Exception as e:
        lines.append(f"❓ Status-Fehler: {e}")
    lines += [
        f"📁 Basis: <code>{_KIVO_BASE}</code>",
        f"📜 Skript: {'✅' if _KIVO_SCRIPT.exists() else '❌'} kivo.py",
        f"🖱 Launcher: {'✅' if _KIVO_COMMAND.exists() else '❌'} KIVO.command",
    ]
    if not _KIVO_BASE.exists():
        lines.append("⚠️ Verzeichnis nicht gefunden — setze KIVO_DIR in .env")
    return "\n".join(lines)


def _kivo_start() -> str:
    if not _KIVO_SCRIPT.exists():
        if _KIVO_COMMAND.exists():
            return (f"🎙️ KIVO starten:\n"
                    f"Doppelklick auf:\n<code>{_KIVO_COMMAND}</code>\n\n"
                    f"(Öffnet Terminal mit Mikrofonzugriff)")
        return f"❌ KIVO nicht gefunden\n<code>{_KIVO_BASE}</code>"
    try:
        r = subprocess.run(["pgrep", "-f", "kivo.py"], capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            return "🎙️ KIVO läuft bereits"
        # Mikrofon-Zugriff braucht Terminal — Info-Meldung
        return (f"🎙️ <b>KIVO starten</b>\n\n"
                f"KIVO braucht Terminal-Mikrofonzugriff.\n"
                f"Doppelklick auf:\n<code>{_KIVO_COMMAND}</code>\n\n"
                f"Oder im Terminal:\n"
                f"<code>open '{_KIVO_COMMAND}'</code>")
    except Exception as e:
        return f"❌ Fehler: {e}"


def _railway_status() -> str:
    """Prüft Railway Shopify AI Suite Verfügbarkeit."""
    lines = [f"🛍️ <b>Shopify AI Suite (Railway)</b>", f"URL: {_SHOPIFY_SUITE_URL}", ""]
    try:
        r = urllib.request.urlopen(f"{_SHOPIFY_SUITE_URL}/health", timeout=8)
        data = json.loads(r.read())
        lines.append(f"🟢 Online — Status: {data.get('status', 'ok')}")
        if data.get("version"):
            lines.append(f"Version: {data['version']}")
    except urllib.error.HTTPError as e:
        lines.append(f"🟡 HTTP {e.code} — Service antwortet")
    except Exception as e:
        lines.append(f"🔴 Nicht erreichbar: {type(e).__name__}")
    return "\n".join(lines)


def _shopify_status() -> str:
    d = _call_dashboard("/api/shopify/status")
    if not d:
        return "🛒 Shopify: Dashboard nicht erreichbar"
    if not d.get("ok"):
        return f"🛒 Shopify: ❌ {d.get('error', 'Unbekannter Fehler')}"
    lines = [
        "<b>🛒 Shopify Status</b>", "",
        f"🟢 Shop: {d.get('store', '?')}",
    ]
    return "\n".join(lines)


# ── Main Dispatcher ──────────────────────────────────────────────────────────

def handle_callback(data: str, chat_id: str, message_id: int,
                    callback_query_id: str) -> None:
    """Verarbeitet alle Inline-Keyboard Button-Klicks."""
    if TELEGRAM_CHAT_ID and str(chat_id) != str(TELEGRAM_CHAT_ID):
        return
    answer_callback(callback_query_id)

    action, _, param = data.partition(":")

    # ── Menü-Navigation ──────────────────────────────────────────────────────
    if action == "menu":
        if param == "main":
            edit_message(chat_id, message_id,
                         "🤖 <b>SuperMegaBot Control Panel</b>\n\nWähle eine Kategorie:",
                         kb_main())
        elif param == "status":
            edit_message(chat_id, message_id, _get_system_status(),
                         [[{"text": "🔄 Refresh", "callback_data": "menu:status"}]] + kb_back())
        elif param == "army":
            edit_message(chat_id, message_id, _get_army_status(), kb_army())
        elif param == "services":
            status = _run_repair_scan()
            edit_message(chat_id, message_id, status,
                         [[{"text": "🔄 Dashboard", "callback_data": "action:restart_dashboard"},
                           {"text": "🧠 Ollama",    "callback_data": "action:restart_ollama"}],
                          [{"text": "🪖 Army",      "callback_data": "action:restart_army"},
                           {"text": "🧩 Orch.",     "callback_data": "action:restart_orchestrator"}],
                          ] + kb_back())
        elif param == "repair":
            edit_message(chat_id, message_id,
                         "🩺 <b>Repair Center</b>\n\nWähle eine Aktion:", kb_repair())
        elif param == "logs":
            edit_message(chat_id, message_id, "📋 <b>Logs</b>\n\nWelches Log?", kb_logs())
        elif param == "actions":
            edit_message(chat_id, message_id,
                         "⚡ <b>Quick Actions</b>\n\nWähle eine Aktion:", kb_actions())
        elif param == "shopify":
            edit_message(chat_id, message_id, _shopify_status(),
                         [[{"text": "🔄 Refresh", "callback_data": "menu:shopify"}]] + kb_back())
        elif param == "models":
            fast  = os.getenv("OLLAMA_FAST_MODEL",    "llama3.2:latest")
            smart = os.getenv("OLLAMA_SMART_MODEL",   "gemma2:latest")
            code  = os.getenv("OLLAMA_CODE_MODEL",    "codellama:latest")
            text = (f"🤖 <b>KI-Modelle</b>\n\n"
                    f"⚡ Fast: <code>{fast}</code>\n"
                    f"🧠 Smart: <code>{smart}</code>\n"
                    f"💻 Code: <code>{code}</code>\n\n"
                    f"Ändern: in .env setzen\n"
                    f"OLLAMA_FAST_MODEL=modell:latest")
            edit_message(chat_id, message_id, text, kb_back())
        elif param == "eternal":
            status = _external_service_control(
                "RudiBot Eternal",
                _ETERNAL_DIR / "eternal_immortal_bot.py",
                "/tmp/rudibot-eternal.log", "status")
            edit_message(chat_id, message_id, status, kb_eternal())
        elif param == "kivo":
            edit_message(chat_id, message_id, _kivo_status(), kb_kivo())
        elif param == "railway":
            edit_message(chat_id, message_id, _railway_status(), kb_railway())
        elif param == "monetization":
            txt = "<b>💰 Monetization & Leads</b>\n\nLead-Funnel, Revenue & Stripe-Dashboard:"
            edit_message(chat_id, message_id, txt, kb_monetization())
        elif param == "seo":
            txt = "<b>🌐 SEO & Traffic</b>\n\nAutomatisierte Content-Pipeline & Indexing:"
            edit_message(chat_id, message_id, txt, kb_seo())
        elif param == "projects":
            txt = "<b>🗂 Alle Projekte</b>\n\nRudolfs aktive Projekte:"
            edit_message(chat_id, message_id, txt, kb_projects())

    # ── Army Actions ─────────────────────────────────────────────────────────
    elif action == "army":
        if param == "start":
            msg = _army_start()
            send_message(chat_id, msg, kb_army())
        elif param == "stop":
            msg = _army_stop()
            send_message(chat_id, msg, kb_army())
        elif param == "status":
            edit_message(chat_id, message_id, _get_army_status(), kb_army())
        elif param == "events":
            edit_message(chat_id, message_id, _get_army_events(), kb_army())

    # ── Repair Actions ───────────────────────────────────────────────────────
    elif action == "repair":
        if param == "scan":
            edit_message(chat_id, message_id, _run_repair_scan(), kb_repair())
        elif param == "run":
            try:
                from core.self_healer import SelfHealer
                import asyncio
                healer = SelfHealer()
                fixes = asyncio.run(healer.run_auto_fixes())
                errors = asyncio.run(healer.scan_logs_for_errors())
                msg = (f"🔧 <b>Auto-Repair</b>\n\n"
                       f"Fixes: {len(fixes)}\n"
                       + ("\n".join(f"• {f}" for f in fixes[:5]) or "Keine Fixes nötig")
                       + f"\n\nLog-Fehler: {len(errors)}")
            except Exception as e:
                msg = f"❌ Repair-Fehler: {e}"
            edit_message(chat_id, message_id, msg, kb_repair())
        elif param == "clean":
            edit_message(chat_id, message_id, _clean_logs(), kb_repair())
        elif param == "backup":
            edit_message(chat_id, message_id, _git_backup(), kb_repair())
        elif param == "restart_all":
            results = []
            for svc in ["dashboard", "army", "orchestrator"]:
                results.append(_restart_service(svc))
            edit_message(chat_id, message_id,
                         "🔄 <b>Restart</b>\n\n" + "\n".join(results), kb_repair())

    # ── Log Viewer ───────────────────────────────────────────────────────────
    elif action == "logs":
        log_map = {
            "army":         "/tmp/rudibot-army.log",
            "orchestrator": "/tmp/mega-orchestrator-pm2.log",
            "ollama":       "/tmp/ollama.log",
            "healer":       str(BASE_DIR / "data" / "selfheal.log"),
        }
        log_path = log_map.get(param, "/tmp/supermegabot.log")
        tail = _get_log_tail(log_path, 25)
        if len(tail) > 3800:
            tail = "...\n" + tail[-3800:]
        edit_message(chat_id, message_id,
                     f"📋 <b>{param}</b>\n<pre>{html.escape(tail)}</pre>", kb_logs())

    # ── Quick Actions ────────────────────────────────────────────────────────
    elif action == "action":
        if param == "git_push":
            edit_message(chat_id, message_id, _git_backup(), kb_actions())
        elif param == "restart_dashboard":
            edit_message(chat_id, message_id, _restart_service("dashboard"), kb_actions())
        elif param == "restart_ollama":
            edit_message(chat_id, message_id, _restart_service("ollama"), kb_actions())
        elif param == "restart_army":
            edit_message(chat_id, message_id, _restart_service("army"), kb_actions())
        elif param == "restart_orchestrator":
            edit_message(chat_id, message_id, _restart_service("orchestrator"), kb_actions())
        elif param == "clean_tmp":
            edit_message(chat_id, message_id, _clean_logs(), kb_actions())
        elif param == "pm2_status":
            edit_message(chat_id, message_id, _pm2_status(), kb_actions())
        elif param == "health":
            edit_message(chat_id, message_id, _get_system_status(), kb_actions())

    # ── RudiBot Eternal ──────────────────────────────────────────────────────
    elif action == "eternal":
        script = _ETERNAL_DIR / "eternal_immortal_bot.py"
        msg = _external_service_control("RudiBot Eternal", script,
                                        "/tmp/rudibot-eternal.log", param)
        edit_message(chat_id, message_id, msg, kb_eternal())

    # ── KIVO Voice ───────────────────────────────────────────────────────────
    elif action == "kivo":
        if param == "status":
            edit_message(chat_id, message_id, _kivo_status(), kb_kivo())
        elif param == "start":
            edit_message(chat_id, message_id, _kivo_start(), kb_kivo())
        elif param == "stop":
            msg = _external_service_control("KIVO Voice", _KIVO_SCRIPT,
                                            _KIVO_LOG, "stop")
            edit_message(chat_id, message_id, msg, kb_kivo())
        elif param == "restart":
            _external_service_control("KIVO Voice", _KIVO_SCRIPT, _KIVO_LOG, "stop")
            time.sleep(1)
            edit_message(chat_id, message_id, _kivo_start(), kb_kivo())
        elif param == "logs":
            tail = _get_log_tail(_KIVO_LOG, 25)
            if len(tail) > 3800:
                tail = "...\n" + tail[-3800:]
            edit_message(chat_id, message_id,
                         f"📋 <b>KIVO Logs</b>\n<pre>{html.escape(tail)}</pre>", kb_kivo())

    # ── Alle Railway-Projekte ────────────────────────────────────────────────
    elif action == "proj":
        if param in _RAILWAY_SERVICES:
            txt = _check_railway_service(param)
            edit_message(chat_id, message_id, txt, kb_projects())
        elif param == "macobd":
            txt = "🚗 <b>MacOBD-Pro</b>\n\nOBD-II Diagnose App\nPort: 8765 (lokal)\nRepo: by-rudolf-sarkany-medicalculator"
            edit_message(chat_id, message_id, txt, kb_projects())
        elif param == "localcoder":
            txt = "💻 <b>local-coder</b>\n\nLokaler Ollama Code-Assistent\nPort: 7777 (lokal)\nCLI: <code>lc</code>"
            edit_message(chat_id, message_id, txt, kb_projects())
        else:
            edit_message(chat_id, message_id, f"❓ Unbekanntes Projekt: {param}", kb_projects())

    # ── Railway Shopify AI Suite ─────────────────────────────────────────────
    elif action == "railway":
        if param == "status":
            edit_message(chat_id, message_id, _railway_status(), kb_railway())
        elif param == "health":
            try:
                r = urllib.request.urlopen(
                    f"{_SHOPIFY_SUITE_URL}/health", timeout=8)
                body = r.read().decode()[:500]
                edit_message(chat_id, message_id,
                             f"🏥 <b>Railway Health</b>\n<pre>{body}</pre>",
                             kb_railway())
            except Exception as e:
                edit_message(chat_id, message_id,
                             f"❌ Health-Check fehlgeschlagen: {e}", kb_railway())
        elif param == "logs":
            edit_message(chat_id, message_id,
                         f"ℹ️ Railway Logs sind nur im Railway Dashboard verfügbar:\n"
                         f"<code>railway logs</code> (CLI)\n"
                         f"Oder: {_SHOPIFY_SUITE_URL}/logs", kb_railway())

    elif action == "money":
        if param == "leads":
            r = _call_dashboard("/api/leads")
            leads = r.get("leads", [])
            if leads:
                lines = ["👥 <b>Letzte Leads:</b>", ""]
                for lead in leads[:10]:
                    lines.append(f"• {lead.get('email','?')} — {lead.get('source','?')} ({str(lead.get('created_at','?'))[:10]})")
            else:
                lines = ["Noch keine Leads."]
            edit_message(chat_id, message_id, "\n".join(lines), kb_monetization())
        elif param == "revenue":
            r = _call_dashboard("/api/revenue/today")
            txt = f"💰 <b>Revenue heute:</b> €{r.get('revenue_eur', 0):.2f}\n📋 Bestellungen: {r.get('orders', 0)}"
            edit_message(chat_id, message_id, txt, kb_monetization())

    elif action == "seo":
        if param == "generate":
            edit_message(chat_id, message_id, "⏳ Generiere SEO-Artikel… (dauert ~30s)", kb_back())
            r = _call_dashboard("/api/seo/generate", method="POST")
            url = r.get("url", "?")
            txt = f"✅ <b>Artikel deployed!</b>\n\n🔗 <a href='{url}'>{url}</a>\n\nKeyword: {r.get('keyword','?')}"
            edit_message(chat_id, message_id, txt, kb_seo())
        elif param == "ping":
            r = _call_dashboard("/api/seo/ping-sitemaps", method="POST")
            txt = f"🏓 <b>Sitemap Pings:</b> {r.get('pinged', 0)} gesendet\nFehler: {len(r.get('errors', []))}"
            edit_message(chat_id, message_id, txt, kb_seo())
        elif param == "social":
            edit_message(chat_id, message_id, "⏳ Generiere Social Drafts… (dauert ~20s)", kb_back())
            r = _call_dashboard("/api/seo/social-drafts")
            drafts = r.get("drafts", {})
            lines = ["📣 <b>Social Drafts bereit:</b>", ""]
            for platform, d in drafts.items():
                title = d.get("title") or d.get("text", "")[:60]
                lines.append(f"• <b>{platform}</b>: {title}…")
            lines.append("\n👉 <a href='https://bullpower-hub-portal.netlify.app'>Portal</a>")
            edit_message(chat_id, message_id, "\n".join(lines), kb_seo())


def send_main_menu(chat_id: str) -> None:
    send_message(
        chat_id,
        "🤖 <b>SuperMegaBot Control Panel</b>\n\nWähle eine Kategorie:",
        kb_main(),
    )
