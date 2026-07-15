#!/usr/bin/env python3
"""
telegram_hub_bridge.py — Macht den Telegram-Bot zum zentralen Steuerungs-Hub.

Jede Nachricht, die der Bot empfängt, wird an den SuperMegaBot Dashboard-Server
(`/api/bot/execute`) weitergeleitet.  Die Antwort wird im selben Chat zurück-
gesendet.  Damit kann **jede** Dashboard-Funktion (107+ Commands) direkt über
Telegram aufgerufen werden — der Bot ist das Hauptzentrum für Steuerung.

Voraussetzungen:
    - SuperMegaBot Dashboard läuft (Default: http://localhost:8888)
    - TELEGRAM_BOT_TOKEN ist gesetzt

Start:
    python3 telegram_hub_bridge.py

Stoppen:
    Ctrl+C oder `pkill -f telegram_hub_bridge.py`
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Intent-to-Sale Bridge (optional — loaded lazily to avoid import errors on startup)
_intent_bridge = None

def _get_intent_bridge():
    global _intent_bridge
    if _intent_bridge is None:
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent))
            from modules.intent_to_sale_bridge import process_group_message
            _intent_bridge = process_group_message
        except Exception as e:
            log_placeholder = logging.getLogger("hub-bridge")
            log_placeholder.warning("IntentBridge not loaded: %s", e)
            _intent_bridge = False
    return _intent_bridge if _intent_bridge is not False else None

# .env laden
_THIS_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(_THIS_DIR / ".env")
except ImportError:
    _env_file = _THIS_DIR / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text(errors="ignore").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DASHBOARD_URL = os.environ.get(
    "SUPERMEGABOT_DASHBOARD_URL", "http://localhost:8888"
).rstrip("/")
POLL_TIMEOUT = int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "20"))
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("hub-bridge")

_TG_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def _http(
    method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 15
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(errors="replace"))


def telegram_call(method: str, **params: Any) -> dict[str, Any]:
    """Call a Telegram Bot API method."""
    url = f"{_TG_BASE}/{method}"
    try:
        return _http("POST", url, params, timeout=POLL_TIMEOUT + 5)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log.error("telegram %s HTTPError %s: %s", method, e.code, body[:200])
        return {"ok": False, "error": body}
    except Exception as e:
        log.error("telegram %s error: %s", method, e)
        return {"ok": False, "error": str(e)}


def dashboard_execute(command: str, session_id: str) -> str:
    """Forward a command to the dashboard CommandRouter."""
    url = f"{DASHBOARD_URL}/api/bot/execute"
    try:
        resp = _http(
            "POST",
            url,
            {"command": command, "session_id": session_id},
            timeout=60,
        )
        if not resp.get("ok"):
            return f"Fehler vom Dashboard: {resp.get('error', 'unbekannt')}"
        return str(resp.get("response", ""))
    except urllib.error.URLError as e:
        return (
            f"Dashboard nicht erreichbar ({DASHBOARD_URL}): {e}\n"
            "Starte das Dashboard mit `python3 dashboard/server.py` und versuche es erneut."
        )
    except Exception as e:
        return f"Bridge-Fehler: {e}"


def fetch_commands() -> list[str]:
    """Get the canonical list of bot commands from the dashboard."""
    url = f"{DASHBOARD_URL}/api/bot/commands"
    try:
        resp = _http("GET", url, timeout=10)
        return list(resp.get("all", []))
    except Exception as e:
        log.warning("could not fetch commands: %s", e)
        return []


def is_allowed(chat_id: int | str) -> bool:
    """Restrict access to a single chat_id if TELEGRAM_CHAT_ID is configured."""
    if not ALLOWED_CHAT_ID:
        return True
    return str(chat_id) == str(ALLOWED_CHAT_ID)


def _run_intent_bridge(text: str, chat_id: str, user: dict, message_id: int, chat_type: str) -> None:
    """Fire-and-forget: run intent analysis in background without blocking the poll loop."""
    bridge_fn = _get_intent_bridge()
    if not bridge_fn:
        return
    try:
        username = user.get("username") or user.get("first_name") or ""
        user_id  = str(user.get("id", ""))
        asyncio.run(bridge_fn(
            text=text,
            chat_id=str(chat_id),
            user_id=user_id,
            username=username,
            message_id=message_id,
            chat_type=chat_type,
        ))
    except Exception as e:
        logging.getLogger("hub-bridge").debug("IntentBridge run error: %s", e)


def handle_message(message: dict[str, Any]) -> None:
    chat      = message.get("chat", {})
    chat_id   = chat.get("id")
    chat_type = chat.get("type", "private")  # private | group | supergroup | channel
    user      = message.get("from", {})
    text      = (message.get("text") or "").strip()
    msg_id    = message.get("message_id")

    if not chat_id:
        return
    if not text:
        # Nicht-Text-Nachrichten (Foto, Sprache, Dokument, …) quittieren
        _NON_TEXT = (
            "photo", "voice", "video", "document", "sticker",
            "location", "audio", "animation", "video_note", "contact",
        )
        has_media = any(message.get(t) for t in _NON_TEXT)
        if has_media and is_allowed(chat_id):
            telegram_call(
                "sendMessage",
                chat_id=chat_id,
                text="Entschuldigung, ich verarbeite nur Text-Nachrichten.",
            )
        return

    # ── Intent Bridge: intercept all non-command group messages ──────────────
    is_group = chat_type in ("group", "supergroup")
    if is_group and not text.startswith("/"):
        _run_intent_bridge(text, chat_id, user, msg_id, chat_type)
        # Don't block or reply further — the bridge handles the response

    if not is_allowed(chat_id):
        # Non-group unauthorized chats get a rejection; groups are silently ignored
        if not is_group:
            telegram_call(
                "sendMessage",
                chat_id=chat_id,
                text="Zugriff verweigert — dieser Chat ist nicht autorisiert.",
            )
        return

    # Commands like "/army_status@MyBot" → "/army_status"
    if text.startswith("/") and "@" in text.split()[0]:
        head, *rest = text.split()
        text = head.split("@", 1)[0] + (" " + " ".join(rest) if rest else "")

    log.info("[chat=%s] %s", chat_id, text[:120])

    # /commands as a meta-command returns the catalog
    if text in ("/commands", "/befehle"):
        cmds = fetch_commands()
        if not cmds:
            reply = "Konnte Command-Liste vom Dashboard nicht laden."
        else:
            reply = "Verfügbare Bot-Commands ({}):\n{}".format(
                len(cmds), "\n".join(cmds[:80])
            )
        telegram_call("sendMessage", chat_id=chat_id, text=reply)
        return

    response = dashboard_execute(text, f"tg-{chat_id}")
    # Telegram has a 4096-char message limit
    for chunk_start in range(0, len(response), 3800):
        telegram_call(
            "sendMessage",
            chat_id=chat_id,
            text=response[chunk_start : chunk_start + 3800] or "(leere Antwort)",
            disable_web_page_preview=True,
        )


def handle_callback_query(callback: dict[str, Any]) -> None:
    """Handle an inline-keyboard button press (callback_query update)."""
    cb_id   = callback.get("id")
    message = callback.get("message", {})
    chat    = message.get("chat", {})
    chat_id = chat.get("id")
    data    = (callback.get("data") or "").strip()

    # Always acknowledge the callback so Telegram removes the loading spinner
    if cb_id:
        telegram_call("answerCallbackQuery", callback_query_id=cb_id)

    if not chat_id or not data:
        return

    if not is_allowed(chat_id):
        telegram_call(
            "sendMessage",
            chat_id=chat_id,
            text="Zugriff verweigert — dieser Chat ist nicht autorisiert.",
        )
        return

    log.info("[callback chat=%s] data=%s", chat_id, data[:120])
    response = dashboard_execute(data, f"tg-{chat_id}")
    for chunk_start in range(0, len(response), 3800):
        telegram_call(
            "sendMessage",
            chat_id=chat_id,
            text=response[chunk_start : chunk_start + 3800] or "(leere Antwort)",
            disable_web_page_preview=True,
        )


def main_loop() -> None:
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set — bridge cannot start.")
        sys.exit(2)

    log.info("Telegram Hub Bridge gestartet")
    log.info("Dashboard: %s", DASHBOARD_URL)
    log.info("Allowed chat: %s", ALLOWED_CHAT_ID or "(any)")

    offset: int | None = None
    running = True

    def _shutdown(signum, frame):
        nonlocal running
        running = False
        log.info("Stopping (signal %s)…", signum)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while running:
        params: dict[str, Any] = {
            "timeout": POLL_TIMEOUT,
            "allowed_updates": ["message", "callback_query", "edited_message", "channel_post"],
        }
        if offset is not None:
            params["offset"] = offset
        try:
            resp = _http(
                "GET",
                f"{_TG_BASE}/getUpdates?{urllib.parse.urlencode(params)}",
                timeout=POLL_TIMEOUT + 5,
            )
        except urllib.error.HTTPError as e:
            log.error("getUpdates HTTPError %s — retrying in 5s", e.code)
            time.sleep(5)
            continue
        except Exception as e:
            log.error("getUpdates error: %s — retrying in 5s", e)
            time.sleep(5)
            continue

        if not resp.get("ok"):
            log.error("getUpdates not ok: %s — retrying in 5s", resp)
            time.sleep(5)
            continue

        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            # Handle regular messages, edited messages, and channel posts uniformly
            msg = (
                update.get("message")
                or update.get("edited_message")
                or update.get("channel_post")
            )
            if msg:
                try:
                    handle_message(msg)
                except Exception as e:
                    log.exception("handle_message error: %s", e)
            # Handle inline keyboard button presses
            cb = update.get("callback_query")
            if cb:
                try:
                    handle_callback_query(cb)
                except Exception as e:
                    log.exception("handle_callback_query error: %s", e)

    log.info("Bridge stopped cleanly.")


if __name__ == "__main__":
    main_loop()
