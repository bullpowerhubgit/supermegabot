#!/bin/bash
# SuperMegaBot Setup - M4 Pro macOS
# Läuft alles lokal, minimale externe Kosten

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
RESET="\033[0m"

ok() { echo -e "${GREEN}✓${RESET} $1"; }
warn() { echo -e "${YELLOW}⚠${RESET} $1"; }
info() { echo -e "${BLUE}→${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; }

echo -e "\n${BOLD}SuperMegaBot Setup${RESET}"
echo -e "M4 Pro · macOS 26.4.1 · 95% Lokal\n"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Python check
info "Checking Python..."
if ! command -v python3 &>/dev/null; then
    fail "Python3 nicht gefunden. Installiere mit: brew install python"
    exit 1
fi
PY=$(python3 --version 2>&1)
ok "Python: $PY"

# pip install dependencies
info "Installing Python dependencies (local)..."
pip3 install --quiet --upgrade \
    aiohttp \
    psutil \
    aiosqlite \
    python-dotenv \
    2>/dev/null || warn "Einige Pakete konnten nicht installiert werden"

# Optional but useful
pip3 install --quiet ccxt 2>/dev/null && ok "ccxt (Trading)" || warn "ccxt optional - Preise im Mock-Modus"
pip3 install --quiet playwright 2>/dev/null && ok "playwright (Browser)" || warn "playwright optional"

# Check Ollama
info "Checking Ollama..."
if command -v ollama &>/dev/null; then
    ok "Ollama gefunden"
    # Check if running
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        ok "Ollama läuft"
        MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; d=json.load(sys.stdin); print(', '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null)
        ok "Models: ${MODELS:-keine}"
    else
        warn "Ollama nicht gestartet. Starte: ollama serve"
    fi
else
    warn "Ollama nicht installiert. Installiere: brew install ollama"
    warn "Dann: ollama pull llama3.2 && ollama pull codellama"
fi

# Setup .env
info "Setting up .env..."
if [ ! -f "$DIR/.env" ]; then
    cat > "$DIR/.env" << 'EOF'
# SuperMegaBot Environment
# Lokal (kein Key nötig)
OLLAMA_HOST=http://localhost:11434
DASHBOARD_PORT=8888

# Telegram (optional - für Bot-Commands per Telegram)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Shopify (optional)
SHOPIFY_STORE_URL=
SHOPIFY_ACCESS_TOKEN=

# Externe APIs (optional - alles auch ohne verfügbar)
GITHUB_TOKEN=
EOF
    ok ".env erstellt (editiere bei Bedarf)"
else
    ok ".env bereits vorhanden"
fi

# Load existing .env from telegram bot
TBOT_ENV="/Users/rudolfsarkany/windsurf-telegram-bot/.env"
if [ -f "$TBOT_ENV" ]; then
    info "Übernehme Telegram-Credentials aus bestehendem Bot..."
    TG_TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" "$TBOT_ENV" 2>/dev/null | cut -d= -f2-)
    TG_CHAT=$(grep "^TELEGRAM_CHAT_ID=" "$TBOT_ENV" 2>/dev/null | cut -d= -f2-)
    if [ -n "$TG_TOKEN" ]; then
        sed -i '' "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TG_TOKEN|" "$DIR/.env"
        ok "Telegram Token übernommen"
    fi
    if [ -n "$TG_CHAT" ]; then
        sed -i '' "s|^TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=$TG_CHAT|" "$DIR/.env"
        ok "Telegram Chat-ID übernommen"
    fi
fi

# Shopify from CreatorHub
CREATORHUB_ENV="/Users/rudolfsarkany/CreatorHub Anonym & Profitabel/server/.env"
if [ -f "$CREATORHUB_ENV" ]; then
    info "Übernehme Shopify-Credentials aus CreatorHub..."
    SH_URL=$(grep "^SHOPIFY_STORE_URL=" "$CREATORHUB_ENV" 2>/dev/null | cut -d= -f2-)
    SH_TOKEN=$(grep "^SHOPIFY_ACCESS_TOKEN=" "$CREATORHUB_ENV" 2>/dev/null | cut -d= -f2-)
    if [ -n "$SH_URL" ]; then
        sed -i '' "s|^SHOPIFY_STORE_URL=.*|SHOPIFY_STORE_URL=$SH_URL|" "$DIR/.env"
        ok "Shopify URL übernommen"
    fi
    if [ -n "$SH_TOKEN" ]; then
        sed -i '' "s|^SHOPIFY_ACCESS_TOKEN=.*|SHOPIFY_ACCESS_TOKEN=$SH_TOKEN|" "$DIR/.env"
        ok "Shopify Token übernommen"
    fi
fi

# Create data dirs
mkdir -p "$DIR/data/screenshots" "$DIR/logs"
ok "Daten-Verzeichnisse erstellt"

# Create startup script
cat > "$DIR/start.sh" << 'STARTSH'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Load env
if [ -f "$DIR/.env" ]; then
    export $(grep -v '^#' "$DIR/.env" | xargs) 2>/dev/null
fi

# Start Ollama if not running
if command -v ollama &>/dev/null; then
    if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "→ Starte Ollama..."
        ollama serve &>/dev/null &
        sleep 2
    fi
fi

echo ""
echo "╔══════════════════════════════════╗"
echo "║     SuperMegaBot gestartet       ║"
echo "║  Dashboard: http://localhost:8888 ║"
echo "╚══════════════════════════════════╝"
echo ""

python3 "$DIR/dashboard/server.py"
STARTSH
chmod +x "$DIR/start.sh"
ok "start.sh erstellt"

# Create macOS .command (double-click to launch)
cat > "$DIR/SuperMegaBot.command" << 'CMDSH'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/start.sh"
CMDSH
chmod +x "$DIR/SuperMegaBot.command"
ok "SuperMegaBot.command erstellt (Doppelklick zum Starten)"

echo -e "\n${BOLD}${GREEN}Setup abgeschlossen!${RESET}"
echo -e "\nStart-Optionen:"
echo -e "  ${BOLD}Doppelklick:${RESET} SuperMegaBot.command"
echo -e "  ${BOLD}Terminal:${RESET}    ./start.sh"
echo -e "  ${BOLD}Dashboard:${RESET}   http://localhost:8888"
echo -e "\n${YELLOW}Tipp: Editiere .env für API-Keys${RESET}\n"
