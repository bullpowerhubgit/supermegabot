#!/usr/bin/env python3
"""
Test-Skript um das aktuell funktionierende Anthropic Modell zu finden.
Alle alten Claude Modelle sind deprecated - dieses Skript testet die aktuell verfügbaren.
"""
import os
import sys
from pathlib import Path

# .env laden
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    print("❌ ANTHROPIC_API_KEY nicht in .env gefunden!")
    sys.exit(1)

# Aktuelle Anthropic Modelle (Stand: 2025)
# Die Liste enthält die wahrscheinlichsten aktuellen Modelle
MODELS_TO_TEST = [
    # Neueste Modelle (2025)
    "claude-sonnet-4-20250514",
    "claude-sonnet-4-20250514-v1:0",
    "claude-opus-4-20250514",
    
    # Claude 3.7 (2025)
    "claude-3-7-sonnet-20250219",
    
    # Claude 3.5 (2024)
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
    
    # Claude 3 (2024)
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-3-opus-latest",
    "claude-3-sonnet-latest",
    "claude-3-haiku-latest",
]

print("🔍 Suche aktuelles Anthropic Modell...")
print(f"API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
print()

working_models = []

for model in MODELS_TO_TEST:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=API_KEY)
        
        response = client.messages.create(
            model=model,
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}]
        )
        print(f"✅ ERFOLG: {model}")
        working_models.append(model)
        
    except ImportError:
        print("❌ 'anthropic' Python-Paket nicht installiert.")
        print("   Installieren mit: pip install anthropic")
        sys.exit(1)
        
    except anthropic.NotFoundError:
        print(f"❌ 404 nicht gefunden: {model}")
        
    except anthropic.AuthenticationError:
        print(f"❌ 401 Auth-Fehler: {model}")
        
    except Exception as e:
        print(f"❌ FEHLER: {model} - {type(e).__name__}: {str(e)[:50]}")

print()
print("=" * 60)
if working_models:
    print(f"✅ {len(working_models)} funktionierende Modell(e) gefunden:")
    for m in working_models:
        print(f"   - {m}")
    print()
    print("💡 Empfohlenes Modell:")
    print(f"   ANTHROPIC_MODEL={working_models[0]}")
    print()
    print("➡️  Füge diese Zeile zu deiner .env Datei hinzu:")
    print(f"   ANTHROPIC_MODEL={working_models[0]}")
else:
    print("❌ Keine funktionierenden Modelle gefunden!")
    print("   Mögliche Ursachen:")
    print("   - API Key ist ungültig oder abgelaufen")
    print("   - Account hat keine Berechtigung für diese Modelle")
    print("   - Netzwerkprobleme")
    print("   - Anthropic API ist temporär nicht verfügbar")
