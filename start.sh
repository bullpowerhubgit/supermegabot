#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║   SuperMegaBot — Auto-Start                                  ║
# ║   Installiert Dependencies, prüft Env, startet Dashboard     ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${CYAN}→  $1${NC}"; }

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   🤖  SuperMegaBot Command Center                           ║"
echo "║   $(date +'%Y-%m-%d %H:%M:%S')                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Load .env ────────────────────────────────────────────────────────────
info "Lade .env..."
if [ -f "$DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^#' "$DIR/.env" | grep '=')
    set +a
    ok ".env geladen"
else
    warn ".env nicht gefunden — nur Systemvariablen aktiv"
fi

# ── 2. Auto-create required directories ─────────────────────────────────────
info "Erstelle Verzeichnisse..."
mkdir -p "$DIR/logs" "$DIR/data" "$DIR/dashboard"
ok "Verzeichnisse OK"

# ── 3. Python dependency check & auto-install ───────────────────────────────
info "Prüfe Python-Abhängigkeiten..."
MISSING_PKGS=""
if ! python3 -c "import aiohttp" 2>/dev/null; then MISSING_PKGS="$MISSING_PKGS aiohttp"; fi
if ! python3 -c "import psutil" 2>/dev/null; then MISSING_PKGS="$MISSING_PKGS psutil"; fi
if ! python3 -c "import dotenv" 2>/dev/null; then MISSING_PKGS="$MISSING_PKGS python-dotenv"; fi

if [ -n "$MISSING_PKGS" ]; then
    warn "Fehlende Pakete:$MISSING_PKGS — installiere..."
    pip3 install --quiet $MISSING_PKGS
    ok "Pakete installiert"
else
    ok "Alle Python-Pakete vorhanden"
fi

# ── 4. Critical env key validation ──────────────────────────────────────────
info "Prüfe kritische API-Keys..."
MISSING_KEYS=""
[ -z "${SHOPIFY_ACCESS_TOKEN:-}" ]   && MISSING_KEYS="$MISSING_KEYS SHOPIFY_ACCESS_TOKEN"
[ -z "${SHOPIFY_SHOP_DOMAIN:-}" ]    && MISSING_KEYS="$MISSING_KEYS SHOPIFY_SHOP_DOMAIN"
[ -z "${SUPABASE_URL:-}" ]           && MISSING_KEYS="$MISSING_KEYS SUPABASE_URL"
[ -z "${DIGISTORE24_API_KEY:-}" ]    && MISSING_KEYS="$MISSING_KEYS DIGISTORE24_API_KEY"
[ -z "${PRINTIFY_API_KEY:-}" ]       && MISSING_KEYS="$MISSING_KEYS PRINTIFY_API_KEY"
if [ -n "$MISSING_KEYS" ]; then
    warn "Fehlende Keys (in .env eintragen):$MISSING_KEYS"
else
    ok "Alle kritischen API-Keys gesetzt"
fi

# ── 5. Ollama auto-start ─────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        info "Starte Ollama..."
        nohup ollama serve >> "$DIR/logs/ollama.log" 2>&1 &
        sleep 3
        if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
            ok "Ollama gestartet"
        else
            warn "Ollama noch nicht bereit — läuft im Hintergrund"
        fi
    else
        ok "Ollama bereits aktiv"
    fi
else
    warn "Ollama nicht installiert"
fi

# ── 6. Guardian API notification ────────────────────────────────────────────
GUARDIAN_URL="http://localhost:3201"
if curl -sf "$GUARDIAN_URL/api/v1/health" >/dev/null 2>&1; then
    GUARDIAN_KEY=$(echo -n "${GUARDIAN_API_SECRET:-supermegabot}" | sha256sum 2>/dev/null | cut -c1-32 || echo "supermegabot")
    curl -s -X POST -H "X-API-Key: $GUARDIAN_KEY" \
         -H "Content-Type: application/json" \
         -d '{"message":"🚀 SuperMegaBot gestartet","priority":"normal"}' \
         "$GUARDIAN_URL/api/v1/notify" >/dev/null 2>&1 || true
    ok "Guardian API benachrichtigt"
fi

# ── 7. Kill any existing dashboard process on the port ──────────────────────
PORT="${DASHBOARD_PORT:-8888}"
EXISTING=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    info "Beende alten Prozess auf Port $PORT (PID: $EXISTING)..."
    kill "$EXISTING" 2>/dev/null || true
    sleep 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   🚀  Dashboard startet auf http://localhost:$PORT            ║"
echo "║   🤖  Automation: 30 Tasks aktiv                             ║"
echo "║   📊  API Keys: $([ -z "$MISSING_KEYS" ] && echo 'alle gesetzt' || echo "$(echo $MISSING_KEYS | wc -w) fehlend")                        ║"
echo "║   📋  Logs: $DIR/logs/                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 8. Start dashboard (redirect logs) ──────────────────────────────────────
exec python3 "$DIR/dashboard/server.py" 2>&1 | tee -a "$DIR/logs/dashboard.log"
