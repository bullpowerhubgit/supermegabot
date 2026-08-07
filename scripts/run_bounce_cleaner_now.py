#!/usr/bin/env python3
"""Sofort ALLE Bounce-Mails aus allen IMAP-Postfächern löschen."""
import asyncio, sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
from modules.bounce_cleaner import run_bounce_cleaner

result = asyncio.run(run_bounce_cleaner(full_scan=True))
print("=== BOUNCE-CLEANER ERGEBNIS ===")
print(f"Gesamt gelöscht:   {result['deleted']}")
print(f"Bounced gesperrt:  {result.get('bounced_blocked', 0)}")
for acc, n in result.get("accounts", {}).items():
    s = f"{n} gelöscht" if n > 0 else ("FEHLER" if n < 0 else "keine Bounces")
    print(f"  {acc}: {s}")
