#!/usr/bin/env python3
"""
Group Infiltrator — Pyrogram User-Client für Intent-to-Sale Bridge.

Tritt als Rudolf's Telegram-Account (nicht als Bot!) deutschen Tech/Deal-Gruppen bei
und überwacht alle Nachrichten. Kaufabsicht → IntentBridge → Bot antwortet mit Produktlink.

Setup (einmalig):
    python3 scripts/join_groups.py

Danach: läuft automatisch als Daemon, kein menschlicher Eingriff mehr nötig.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("GroupInfiltrator")

_BASE = Path(__file__).parent.parent

TELEGRAM_API_ID   = lambda: int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = lambda: os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE      = str(_BASE / "data" / "group_monitor")  # Pyrogram session path

# ─────────────────────────────────────────────────────────────────────────────
# Target groups — alle öffentlichen deutschen Tech/Deal/Shopping-Gruppen
# Werden beim Start automatisch beigetreten (public groups: direkt; private: via invite link)
# ─────────────────────────────────────────────────────────────────────────────
TARGET_GROUPS: list[str] = [
    # Tech & Deals Deutschland
    "TechDealsGermany",
    "TechDealsGermany5",
    "dealkollektiv",
    "preisalarmdeutschland",
    "hot_deals_gruppe",
    # Gadgets
    "gadgetsine",
    "gadgetboyz",
    "the_gadgets_hub",
    "china_handys",
    # Shopping & Schnäppchen
    "deutsche_gruppe",
    "GruppenVZ",
    # German communities
    "gruppen24",
    "kanalgruppenfinden",
]

# Minimum time (sec) between processing messages per group (global dedup)
_MSG_SEEN: dict[int, float] = {}  # message_id → timestamp, to avoid double-processing


def is_configured() -> bool:
    return bool(TELEGRAM_API_ID() and TELEGRAM_API_HASH())


# ─────────────────────────────────────────────────────────────────────────────
# Group joiner — runs once on startup
# ─────────────────────────────────────────────────────────────────────────────

async def join_all_groups(client) -> dict[str, str]:
    """Join all TARGET_GROUPS. Returns {username: status}."""
    results: dict[str, str] = {}
    for username in TARGET_GROUPS:
        try:
            chat = await client.join_chat(username)
            results[username] = f"✅ joined ({chat.title})"
            log.info("Joined group: %s (%s)", username, chat.title)
            await asyncio.sleep(2)  # Telegram rate limit: don't hammer
        except Exception as e:
            err = str(e)
            if "already" in err.lower() or "ALREADY" in err:
                results[username] = "✅ already member"
            elif "USERNAME_INVALID" in err or "USERNAME_NOT_OCCUPIED" in err:
                results[username] = f"⚠️ group not found"
                log.debug("Group not found: %s", username)
            elif "FLOOD_WAIT" in err:
                wait = int(err.split("FLOOD_WAIT_")[1].split(" ")[0]) if "FLOOD_WAIT_" in err else 60
                log.warning("Flood wait %ds for %s", wait, username)
                results[username] = f"⏳ flood wait {wait}s"
                await asyncio.sleep(wait + 5)
            else:
                results[username] = f"❌ {err[:60]}"
                log.debug("Could not join %s: %s", username, err)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Message handler
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_incoming(client, message) -> None:
    """Process one incoming group message through the Intent Bridge."""
    try:
        # Skip channels (only process actual group messages from real users)
        if not message.from_user:
            return

        text = message.text or message.caption or ""
        if not text or len(text) < 10:
            return

        # Skip messages older than 5 min (catch-up after restart)
        if message.date and (time.time() - message.date.timestamp()) > 300:
            return

        # Skip if we already processed this message
        if message.id in _MSG_SEEN:
            return
        _MSG_SEEN[message.id] = time.time()

        # Prune old entries (keep last 5000)
        if len(_MSG_SEEN) > 5000:
            oldest = sorted(_MSG_SEEN, key=_MSG_SEEN.get)[:1000]
            for k in oldest:
                _MSG_SEEN.pop(k, None)

        chat_id  = str(message.chat.id)
        user_id  = str(message.from_user.id)
        username = message.from_user.username or message.from_user.first_name or ""
        chat_type = message.chat.type.value if hasattr(message.chat.type, "value") else str(message.chat.type)

        log.debug("[GI] chat=%s user=%s text=%s…", chat_id, username, text[:60])

        from modules.intent_to_sale_bridge import process_group_message
        responded = await process_group_message(
            text=text,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            message_id=message.id,
            chat_type=chat_type,
        )
        if responded:
            log.info("[GI] ✅ Responded in chat=%s to: %s…", chat_id, text[:80])

    except Exception as e:
        log.debug("Message handler error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Main daemon loop
# ─────────────────────────────────────────────────────────────────────────────

async def run_monitor() -> None:
    """Start Pyrogram client and listen forever. Reconnects on errors."""
    if not is_configured():
        log.warning("GroupInfiltrator: TELEGRAM_API_ID / TELEGRAM_API_HASH not set — skipping")
        return

    # Session-Datei muss vorhanden sein — sonst kein interaktiver Login möglich (Railway)
    session_path = Path(SESSION_FILE + ".session")
    if not session_path.exists():
        log.warning("GroupInfiltrator: Session-Datei %s fehlt — lokal einmalig einloggen: python3 scripts/create_tg_session.py", session_path)
        return

    try:
        from pyrogram import Client, filters
        from pyrogram.types import Message
    except ImportError:
        log.warning("pyrogram not installed — run: pip install pyrogram TgCrypto")
        return

    log.info("GroupInfiltrator starting (session=%s.session)", SESSION_FILE)

    while True:
        try:
            async with Client(
                SESSION_FILE,
                api_id=TELEGRAM_API_ID(),
                api_hash=TELEGRAM_API_HASH(),
            ) as app:
                log.info("GroupInfiltrator connected as %s", (await app.get_me()).username)

                # Join groups on (re)start
                join_results = await join_all_groups(app)
                joined = sum(1 for v in join_results.values() if v.startswith("✅"))
                log.info("Group join results: %d/%d successful", joined, len(join_results))

                # Register message handler for all group messages
                @app.on_message(filters.group & ~filters.command(["start", "help", "commands"]))
                async def on_group_msg(client, msg: Message):
                    asyncio.create_task(_handle_incoming(client, msg))

                log.info("GroupInfiltrator listening on %d groups…", joined)
                await asyncio.Event().wait()  # run forever

        except Exception as e:
            log.error("GroupInfiltrator error (reconnecting in 30s): %s", e)
            await asyncio.sleep(30)


# ─────────────────────────────────────────────────────────────────────────────
# Called from automation_scheduler as a persistent background task
# ─────────────────────────────────────────────────────────────────────────────

async def start_background() -> None:
    """Non-blocking start — creates an asyncio task for the monitor loop."""
    if not is_configured():
        return
    if not Path(SESSION_FILE + ".session").exists():
        log.warning("GroupInfiltrator: Session fehlt — übersprungen")
        return
    asyncio.create_task(run_monitor(), name="group_infiltrator")
    log.info("GroupInfiltrator background task created")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_monitor())
