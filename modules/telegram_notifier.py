#!/usr/bin/env python3
"""
modules/telegram_notifier.py — Dünner Wrapper für Telegram-Benachrichtigungen.

Mehrere Module importieren `send_message` / `send_alert` von hier.
Delegiert an den spam-geschützten Sender aus modules/smart_poster.py
(send_telegram_guarded → Rate-Limit + Backoff + Link-Check).
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("TelegramNotifier")


async def send_message(text: str, chat_id: str | None = None,
                       parse_mode: str = "Markdown") -> dict:
    """Sendet eine Telegram-Nachricht an den konfigurierten Chat (spam-geschützt)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        log.debug("telegram_notifier: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID fehlt — Nachricht verworfen")
        return {"ok": False, "reason": "not_configured"}
    try:
        from modules.smart_poster import send_telegram_guarded
        return await send_telegram_guarded(token, str(chat), text, parse_mode=parse_mode)
    except Exception as exc:
        log.warning("telegram_notifier: Senden fehlgeschlagen: %s", exc)
        return {"ok": False, "reason": str(exc)[:200]}


async def send_alert(text: str, chat_id: str | None = None) -> dict:
    """Alias für send_message — für Alarm-/Report-Nachrichten."""
    return await send_message(text, chat_id=chat_id)


async def notify(text: str) -> dict:
    """Weiterer Alias (kompatibel zu _tg_notify-Aufrufmustern)."""
    return await send_message(text)
