#!/usr/bin/env python3
"""Synchronisiert gmail_secrets.json mit den korrekten Passwords aus .env."""
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

secrets_path = Path(__file__).parent.parent / "data" / "gmail_secrets.json"

with open(secrets_path) as f:
    data = json.load(f)

# Passwörter aus .env einlesen (keine Hardcodes!)
env_pw = {
    "1": os.getenv("GMAIL_APP_PASSWORD_1", ""),
    "3": os.getenv("GMAIL_APP_PASSWORD_3", "") or os.getenv("GMAIL_APP_PASSWORD_BULLPOWER", ""),
    "5": os.getenv("GMAIL_APP_PASSWORD_5", "") or os.getenv("GMAIL_APP_PASSWORD_AIITEC", ""),
    "7": os.getenv("GMAIL_APP_PASSWORD_7", ""),
    # Index 8 (rudolfsarkany1984): Web-Login nötig → nicht in secrets
}

changed = []
for idx, pw in env_pw.items():
    pw = pw.strip()
    if pw and data["passwords"].get(idx) != pw:
        changed.append(f"  [{idx}]: Passwort aktualisiert")
        data["passwords"][idx] = pw

# Index 8 entfernen (Web-Login erforderlich, App-Passwort gesperrt)
if "8" in data["passwords"]:
    data["passwords"].pop("8")
    changed.append("  [8]: Entfernt (Web-Login erforderlich)")

with open(secrets_path, "w") as f:
    json.dump(data, f, indent=2)

if changed:
    print("Änderungen:")
    for c in changed:
        print(c)
else:
    print("Keine Änderungen nötig.")
print(f"Aktive Konten: {list(data['passwords'].keys())}")
