#!/usr/bin/env python3
"""Liest DudiRudibot + Rudiclone Chatverlauf — HEUTE komplett."""
import asyncio
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.tl.types import Message

import os
from pathlib import Path

# .env laden
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION  = "telegram_export_session"

DUDIRUDIBOT_ID = 8320990321  # ehemals TELEGRAM_BOT_TOKEN_2 (widerrufen)
RUDICLONE_ID   = 8600739487  # TELEGRAM_BOT_TOKEN

async def read_chat(client, entity_id, name, since):
    print(f"\n{'='*70}")
    print(f"  {name.upper()} (ID: {entity_id})")
    print(f"{'='*70}")
    count = 0
    try:
        async for msg in client.iter_messages(entity_id, limit=500):
            if not isinstance(msg, Message):
                continue
            if msg.date < since:
                break
            direction = ">>> BOT SENDET:" if not msg.out else "<<< DU:"
            text = msg.text or "[MEDIA/OHNE TEXT]"
            ts = msg.date.astimezone(timezone(timedelta(hours=2))).strftime("%H:%M:%S")
            print(f"\n{ts} {direction}")
            print(text[:1000])
            print("-" * 60)
            count += 1
    except Exception as e:
        print(f"  FEHLER: {e}")
    print(f"\n  → {count} Nachrichten heute von {name}")
    return count

async def main():
    today_start = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    print(f"\n{'#'*70}")
    print(f"  TELEGRAM CHATVERLAUF HEUTE — {today_start.strftime('%Y-%m-%d')}")
    print(f"  Analysiere: @DudiRudibot + @Rudiclone")
    print(f"{'#'*70}")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()

    # Dialog-Cache aufbauen (Telethon braucht das für Entity-Lookup)
    print("Lade Dialog-Liste...")
    dialogs = await client.get_dialogs(limit=50)
    entity_map = {d.entity.id: d.entity for d in dialogs if hasattr(d.entity, 'id')}
    print(f"  {len(entity_map)} Dialoge gecacht\n")

    # Rudiclone und DudiRudibot aus dem Cache holen
    targets = [
        (DUDIRUDIBOT_ID, "@DudiRudibot (widerrufen)"),
        (RUDICLONE_ID,   "@Rudiclone"),
    ]

    total = 0
    for eid, name in targets:
        entity = entity_map.get(eid)
        if entity is None:
            print(f"\n[{name}] — nicht im Dialog-Cache (kein Chat mit diesem Bot)")
            continue
        total += await read_chat(client, entity, name, today_start)

    print(f"\n{'#'*70}")
    print(f"  GESAMT HEUTE: {total} Nachrichten")
    print(f"{'#'*70}\n")
    await client.disconnect()

asyncio.run(main())
