#!/usr/bin/env python3
"""
Telegram Chat-Export via Telethon (User-Login).
Exportiert den kompletten Chatverlauf als JSON + lesbares TXT.

Ausführen: python3 telegram_export_chat.py
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

import os
API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION  = "telegram_export_session"

BOT_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

async def main():
    print("\n" + "="*60)
    print("TELEGRAM CHAT EXPORT")
    print("="*60)
    print("Einmalig: Telefonnummer eingeben → SMS-Code eingeben")
    print("Danach läuft das Script automatisch.\n")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()  # Fragt Telefonnummer + Code interaktiv

    me = await client.get_me()
    print(f"\nEingeloggt als: {me.first_name} {me.last_name or ''} (+{me.phone})")

    # Alle Dialoge auflisten
    print("\n📋 Deine Chats (letzte 30):")
    print("-" * 60)
    dialogs = await client.get_dialogs(limit=30)
    for i, dialog in enumerate(dialogs):
        name = dialog.name or "Unbekannt"
        eid  = dialog.entity.id if hasattr(dialog.entity, 'id') else '?'
        print(f"  [{i:2d}] {name[:40]:40s}  ID: {eid}")

    print("\n" + "-"*60)
    print("Welchen Chat exportieren?")
    print("  [ENTER] = Rudiclone Bot-Chat (wo der Bot postet)")
    print("  alle    = ALLE Chats aus der Liste exportieren")
    print("  Oder: Nummer aus der Liste eingeben (0-29)")
    choice = input("Auswahl: ").strip().lower()

    if choice == "alle":
        entity = None  # Marker für "alle"
        chat_name = "ALLE_CHATS"
    elif choice == "":
        # Standard: Rudiclone (index 1) oder BOT_CHAT_ID
        entity = dialogs[1].entity if len(dialogs) > 1 else BOT_CHAT_ID
        chat_name = dialogs[1].name if len(dialogs) > 1 else "Rudiclone"
    else:
        idx = int(choice)
        entity = dialogs[idx].entity
        chat_name = dialogs[idx].name

    print(f"\nExportiere: {chat_name}")

    # Wie viele Tage?
    days_input = input("Wie viele Tage zurück? [ENTER = 7 Tage / 0 = ALLE]: ").strip()
    if days_input == "0":
        since = None
        days_label = "komplett"
    else:
        days = int(days_input) if days_input.isdigit() else 7
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        days_label = f"{days}d"

    print(f"\nLade Nachrichten...")

    async def fetch_messages_from(ent, ent_name):
        msgs = []
        async for msg in client.iter_messages(
            ent, reverse=True,
            offset_date=since,
            limit=None if days_input == "0" else 10000
        ):
            if not isinstance(msg, Message):
                continue
            if since and msg.date < since:
                continue
            media_type = None
            if isinstance(msg.media, MessageMediaPhoto):
                media_type = "Foto"
            elif isinstance(msg.media, MessageMediaDocument):
                media_type = "Dokument"
            sender_name = "Unbekannt"
            if msg.out:
                sender_name = f"DU ({me.first_name})"
            elif msg.sender:
                snd = msg.sender
                sender_name = getattr(snd, 'first_name', '') or getattr(snd, 'title', '') or str(msg.sender_id)
            msgs.append({
                "id": msg.id,
                "chat": ent_name,
                "date": msg.date.astimezone(timezone(timedelta(hours=2))).isoformat(),
                "sender": sender_name,
                "text": msg.text or "",
                "media": media_type,
            })
        return msgs

    messages = []
    if entity is None:
        # Alle Chats exportieren
        for dlg in dialogs:
            print(f"  Lese: {dlg.name}...")
            try:
                msgs = await fetch_messages_from(dlg.entity, dlg.name)
                messages.extend(msgs)
                print(f"    → {len(msgs)} Nachrichten")
            except Exception as e:
                print(f"    → Fehler: {e}")
    else:
        messages = await fetch_messages_from(entity, chat_name)

    # Chronologisch sortieren
    messages.sort(key=lambda m: m["date"])
    count = len(messages)
    print(f"\n✅ {count} Nachrichten geladen!")

    # Speichern
    safe_name = chat_name.replace("/", "_").replace(" ", "_")[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    output_dir = Path.home() / "supermegabot" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / f"telegram_export_{safe_name}_{ts}_{days_label}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"chat": chat_name, "exported_at": ts, "messages": messages}, f,
                  indent=2, ensure_ascii=False)

    # Lesbares TXT
    txt_path = output_dir / f"telegram_export_{safe_name}_{ts}_{days_label}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"TELEGRAM EXPORT — {chat_name}\n")
        f.write(f"Exportiert: {ts}\n")
        f.write(f"Nachrichten: {count}\n")
        f.write("=" * 70 + "\n\n")
        for m in messages:
            dt  = m["date"][11:19]  # HH:MM:SS
            day = m["date"][:10]
            sndr = m["sender"][:20]
            text = m["text"] or f"[{m['media']}]" if m["media"] else ""
            if text:
                f.write(f"{day} {dt}  [{sndr}]\n{text}\n{'-'*60}\n")

    print(f"\n📁 Export gespeichert:")
    print(f"   JSON: {json_path}")
    print(f"   TXT:  {txt_path}")

    # Letzten 50 anzeigen
    print(f"\n{'='*70}")
    print(f"LETZTE 50 NACHRICHTEN:")
    print(f"{'='*70}\n")
    for m in messages[-50:]:
        dt   = m["date"][5:19]
        sndr = m["sender"][:15]
        text = m["text"] or f"[{m['media']}]"
        if text:
            print(f"{dt}  {sndr}: {text[:300]}")
            print("-" * 50)

    await client.disconnect()
    print("\n✅ Fertig!")

asyncio.run(main())
