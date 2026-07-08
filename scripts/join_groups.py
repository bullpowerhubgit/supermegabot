#!/usr/bin/env python3
"""
join_groups.py — Einmaliges Setup: Telegram-Session erstellen + Gruppen beitreten.

Ausführen:
    python3 scripts/join_groups.py

Was passiert:
    1. Prüft ob TELEGRAM_API_ID und TELEGRAM_API_HASH in .env gesetzt sind
    2. Erstellt Pyrogram-Session (Phone + OTP — einmalig!)
    3. Tritt allen Ziel-Gruppen bei
    4. Zeigt Ergebnis

Danach:
    Der GroupInfiltrator startet automatisch bei jedem Server-Start.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BASE = Path(__file__).parent.parent
sys.path.insert(0, str(_BASE))

try:
    from dotenv import load_dotenv
    load_dotenv(_BASE / ".env")
except ImportError:
    _env = _BASE / ".env"
    if _env.exists():
        for line in _env.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def check_credentials() -> tuple[int, str]:
    api_id   = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    if not api_id or not api_hash:
        print("\n❌ TELEGRAM_API_ID und TELEGRAM_API_HASH fehlen!\n")
        print("So bekommst du sie (2 Minuten, einmalig):")
        print("  1. Öffne: https://my.telegram.org")
        print("  2. Login mit deiner Telefonnummer")
        print("  3. Klick auf 'API development tools'")
        print("  4. Erstelle eine neue App (Name/Kurzbeschreibung egal)")
        print("  5. Kopiere 'App api_id' und 'App api_hash'\n")
        print("Dann füge folgendes in .env ein:")
        print("  TELEGRAM_API_ID=<deine_api_id>")
        print("  TELEGRAM_API_HASH=<dein_api_hash>\n")
        sys.exit(1)
    return api_id, api_hash


async def main():
    try:
        from pyrogram import Client
    except ImportError:
        print("❌ pyrogram nicht installiert. Ausführen:")
        print("   pip install pyrogram TgCrypto")
        sys.exit(1)

    api_id, api_hash = check_credentials()
    session_file = str(_BASE / "data" / "group_monitor")

    print("\n🚀 Group Infiltrator Setup\n")
    print(f"Session wird gespeichert: {session_file}.session")
    print("Beim ersten Mal: Telefonnummer + OTP eingeben (einmalig)\n")

    async with Client(session_file, api_id=api_id, api_hash=api_hash) as app:
        me = await app.get_me()
        print(f"✅ Eingeloggt als: @{me.username} ({me.first_name})\n")

        from modules.group_infiltrator import TARGET_GROUPS, join_all_groups
        print(f"📋 Trete {len(TARGET_GROUPS)} Gruppen bei...\n")

        results = await join_all_groups(app)

        print("\n📊 Ergebnis:\n")
        ok = err = 0
        for username, status in results.items():
            print(f"  @{username:35s} {status}")
            if status.startswith("✅"):
                ok += 1
            else:
                err += 1

        print(f"\n✅ Erfolgreich: {ok} | ⚠️ Nicht verfügbar: {err}")
        print("\n🎯 GroupInfiltrator ist jetzt bereit!")
        print("Er startet automatisch mit dem Server und überwacht alle Gruppen.\n")

        # Quick self-test
        print("🧪 Selbsttest: Intent-Bridge...")
        try:
            from modules.intent_to_sale_bridge import classify_intent
            test_result = await classify_intent("Suche eine gute Powerstation um 500W, hat jemand Empfehlungen?")
            if test_result.get("is_buying"):
                print(f"   ✅ Intent erkannt! Konfidenz: {test_result['confidence']:.0%} | Kategorie: {test_result['category']}")
            else:
                print(f"   ⚠️ Kein Intent erkannt (conf={test_result.get('confidence', 0):.2f}) — AI API prüfen")
        except Exception as e:
            print(f"   ⚠️ Test fehlgeschlagen: {e}")

    print("\n✅ Setup abgeschlossen. Server kann jetzt (neu)gestartet werden.\n")


if __name__ == "__main__":
    asyncio.run(main())
