#!/usr/bin/env python3
"""
modules/telegram_hub_bridge.py — Import-Shim.

Re-exportiert das Root-Modul `telegram_hub_bridge.py` (Telegram-Hub-Bridge)
und stellt zusätzlich das von mehreren Modulen erwartete asynchrone
`send_telegram_message(text)` bereit.
"""

from __future__ import annotations

import logging

log = logging.getLogger("TelegramHubBridgeShim")

try:
    # Re-Export des Root-Moduls (telegram_call, dashboard_execute, ...)
    from telegram_hub_bridge import *  # noqa: F401,F403
    from telegram_hub_bridge import telegram_call, dashboard_execute  # noqa: F401
except Exception as _exc:  # pragma: no cover — Root-Modul optional
    log.debug("telegram_hub_bridge (Root) nicht importierbar: %s", _exc)


async def send_telegram_message(text: str, chat_id: str | None = None) -> dict:
    """Async-Sender, den revenue_fast_track/mega_seo_engine u.a. erwarten."""
    from modules.telegram_notifier import send_message
    return await send_message(text, chat_id=chat_id)
