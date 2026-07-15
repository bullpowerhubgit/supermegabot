#!/usr/bin/env python3
"""
TelegramThrottle — Max 1 Nachricht/3s, Batch-Queue flusht alle 30s.
Verhindert 429-Rate-Limit beim Telegram Bot.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Optional

import aiohttp

log = logging.getLogger("TGThrottle")

TG_BOT  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

_MIN_INTERVAL = 3.0      # Mindest-Abstand zwischen zwei Nachrichten (Sekunden)
_BATCH_WINDOW = 30.0     # Batch-Queue flusht spätestens alle 30s
_MAX_QUEUE    = 50       # Maximal 50 Messages in Queue (ältere werden verworfen)

_last_sent: float = 0.0
_queue: deque = deque(maxlen=_MAX_QUEUE)
_flush_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()


async def _send_raw(text: str) -> bool:
    """Sendet direkt via Telegram API."""
    if not TG_BOT or not TG_CHAT:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            r = await s.post(
                f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text[:4000], "parse_mode": "Markdown"},
            )
            data = await r.json()
            if not data.get("ok"):
                err = data.get("description", "")
                if "429" in str(r.status) or "Too Many" in err:
                    retry = data.get("parameters", {}).get("retry_after", 60)
                    log.warning("TG Rate-Limit: retry nach %ds — Message gepuffert", retry)
                    return False
            return data.get("ok", False)
    except Exception as e:
        log.debug("TG send error: %s", e)
        return False


async def send(text: str, priority: bool = False) -> None:
    """
    Throttled send. priority=True → sofort (wenn Cooldown rum), sonst Queue.
    """
    global _last_sent, _flush_task

    async with _lock:
        now = time.monotonic()
        since_last = now - _last_sent

        if since_last >= _MIN_INTERVAL:
            ok = await _send_raw(text)
            if ok:
                _last_sent = time.monotonic()
                return
            # Fehlgeschlagen → in Queue
        _queue.append(text)

    # Flush-Task sicherstellen
    if _flush_task is None or _flush_task.done():
        try:
            loop = asyncio.get_event_loop()
            _flush_task = loop.create_task(_flush_loop())
        except RuntimeError:
            pass


async def _flush_loop() -> None:
    """Leert die Queue mit _MIN_INTERVAL Pause zwischen Nachrichten."""
    global _last_sent
    while _queue:
        await asyncio.sleep(_MIN_INTERVAL)
        async with _lock:
            if not _queue:
                break
            text = _queue.popleft()
            ok = await _send_raw(text)
            if ok:
                _last_sent = time.monotonic()
            else:
                # Zurück in Queue (vorne)
                _queue.appendleft(text)
                await asyncio.sleep(10)


def send_sync(text: str) -> None:
    """Fire-and-forget aus synchronem Kontext."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(send(text))
        else:
            loop.run_until_complete(send(text))
    except Exception:
        pass
