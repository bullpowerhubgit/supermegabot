"""Shared Message Bus — Redis + JSON fallback für Bot-Army Kommunikation"""
import json, time, os, urllib.request, urllib.parse
from pathlib import Path

STATE_FILE = Path(__file__).parent / "army_state.json"
BOT_DIR = Path("/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot")

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(errors='ignore'))
    except (json.JSONDecodeError, OSError):
        pass
    return {"agents":{}, "events":[], "fixes":[], "stats":{}}

def save_state(s):
    try:
        STATE_FILE.write_text(json.dumps(s, indent=2, default=str))
    except OSError:
        pass

def report(agent_id, status, message, data=None):
    try:
        s = load_state()
        s["agents"][agent_id] = {
            "status": status, "message": message,
            "data": data or {}, "ts": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        s["events"].append({"agent": agent_id, "msg": message, "ts": time.strftime("%H:%M:%S")})
        s["events"] = s["events"][-200:]
        save_state(s)
    except Exception:
        import logging
        logging.getLogger('bus').warning('report failed', exc_info=True)

def get_agents():
    return load_state().get("agents", {})

def get_env(key):
    v = os.getenv(key)
    if v: return v
    try:
        for line in (BOT_DIR / ".env").read_text(errors='ignore').splitlines():
            if line.strip().startswith(key + "="):
                return line.split("=",1)[1].strip()
    except OSError:
        pass
    return None

def notify_telegram(msg):
    # urllib bereits beim Modulstart importiert — kein lazy-import mehr
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID") or get_env("AUTHORIZED_USER_ID")
    if not token or not chat_id: return
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": f"🤖 Army: {msg}",
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, method="POST"
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        import logging
        logging.getLogger('bus').warning('notify_telegram failed', exc_info=True)
