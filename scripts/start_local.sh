#!/bin/bash
# SuperMegaBot — Lokaler Mac-Start
# Verwendung: bash start_local.sh
# Holt immer die aktuelle Version von GitHub ohne Merge-Konflikte.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "═══════════════════════════════════════════"
echo "  SuperMegaBot — Lokaler Start"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════"

# 1. GitHub-Stand holen (ohne Merge-Konflikte)
echo ""
echo "▶ Synchronisiere mit GitHub..."
git fetch origin main
git reset --hard origin/main
echo "  ✅ Code aktuell: $(git log --oneline -1)"

# 2. .env prüfen
echo ""
echo "▶ Prüfe .env..."
if [ ! -f ".env" ]; then
    echo "  ❌ .env nicht gefunden! Bitte aus .env.example kopieren:"
    echo "     cp .env.example .env && nano .env"
    exit 1
fi

# Kritische Keys prüfen (ohne Werte anzuzeigen)
python3 - <<'PYCHECK'
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env" if False else ".env")

CRITICAL = [
    "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SUPABASE_URL", "SUPABASE_ANON_KEY",
]
OPTIONAL = [
    "ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY",
    "DIGISTORE24_API_KEY", "KLAVIYO_API_KEY",
    "OPENAI_API_KEY", "GUARDIAN_API_SECRET",
]

missing = []
for k in CRITICAL:
    v = os.getenv(k, "")
    status = f"✅ ({len(v)} Zeichen)" if v else "❌ FEHLT"
    print(f"  {k}: {status}")
    if not v:
        missing.append(k)

print("  ---")
for k in OPTIONAL:
    v = os.getenv(k, "")
    status = f"✅ ({len(v)} Zeichen)" if v else "⚠️  nicht gesetzt (optional)"
    print(f"  {k}: {status}")

if missing:
    print(f"\n  ⚠️  {len(missing)} kritische Keys fehlen — Dashboard startet trotzdem,")
    print("     aber manche Funktionen sind deaktiviert.")
else:
    print("\n  ✅ Alle kritischen Keys gesetzt")
PYCHECK

# 3. Python-Abhängigkeiten prüfen
echo ""
echo "▶ Prüfe Python-Pakete..."
python3 -c "import aiohttp, dotenv, aiosqlite" 2>/dev/null && \
    echo "  ✅ Basis-Pakete OK" || \
    (echo "  📦 Installiere fehlende Pakete..." && pip3 install -q python-dotenv aiohttp aiosqlite)

# 4. Dashboard starten
echo ""
echo "▶ Starte Dashboard auf Port 8888..."
echo "  → http://localhost:8888"
echo "  → Zum Beenden: Ctrl+C"
echo ""
echo "═══════════════════════════════════════════"

python3 dashboard/server.py 2>&1 | tee /tmp/smb_dashboard.log
