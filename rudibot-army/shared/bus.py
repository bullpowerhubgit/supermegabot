"""Shared Message Bus — JSON State + Telegram für Bot-Army Kommunikation"""
import json, time, os, urllib.request, urllib.parse, logging
from typing import Optional
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger('bus')

STATE_FILE = Path(__file__).parent / "army_state.json"

# .env Suchreihenfolge: Umgebungsvariablen → Projekt-Root → Home-Verzeichnis
_ENV_SEARCH_PATHS = [
    Path(__file__).parent.parent.parent / ".env",  # supermegabot/.env
    Path.home() / "supermegabot" / ".env",
    Path.home() / ".env",
]

def _load_env_file() -> dict:
    """Lädt .env Datei aus dem ersten gefundenen Pfad."""
    for p in _ENV_SEARCH_PATHS:
        if p.exists():
            result = {}
            for line in p.read_text(errors='ignore').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    result[k.strip()] = v.strip().strip('"').strip("'")
            return result
    return {}

_env_cache: Optional[dict] = None

def get_env(key: str) -> Optional[str]:
    global _env_cache
    v = os.getenv(key)
    if v:
        return v
    if _env_cache is None:
        _env_cache = _load_env_file()
    return _env_cache.get(key)


def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(errors='ignore'))
    except Exception as e:
        log.error(f"Failed to load state from {STATE_FILE}: {e}")
    return {"agents": {}, "events": [], "fixes": [], "stats": {}}


def save_state(s: dict):
    try:
        STATE_FILE.write_text(json.dumps(s, indent=2, default=str))
    except Exception as e:
        log.error(f"Failed to save state to {STATE_FILE}: {e}")


def report(agent_id: str, status: str, message: str, data: Optional[dict] = None):
    try:
        s = load_state()
        s["agents"][agent_id] = {
            "status": status,
            "message": message,
            "data": data or {},
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        s["events"].append({"agent": agent_id, "msg": message, "ts": time.strftime("%H:%M:%S")})
        s["events"] = s["events"][-200:]
        save_state(s)
    except Exception as e:
        log.error(f"Failed to report agent {agent_id}: {e}")


def get_agents() -> dict:
    return load_state().get("agents", {})


def notify_telegram(msg: str):
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID") or get_env("AUTHORIZED_USER_ID")
    if not token or not chat_id:
        log.warning("Telegram notification skipped: missing TELEGRAM_BOT_TOKEN or chat_id")
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": f"🤖 Army: {msg}",
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        log.error(f"Telegram notification failed: {e}")
