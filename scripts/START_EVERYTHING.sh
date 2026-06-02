#!/usr/bin/env bash
# ================================================================
# START_EVERYTHING.sh — Vollständiger SuperMegaBot Start
# 1. Stoppt Crash-Loops  2. Scannt Credentials  3. Startet alles
#
# Ausführen: bash ~/supermegabot/scripts/START_EVERYTHING.sh
# ================================================================

set -e
MEGA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$MEGA_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "\n${BOLD}${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║      SuperMegaBot — ALLES STARTEN        ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════╝${NC}\n"

# ── Schritt 1: Crash-Loops stoppen ───────────────────────────────
echo -e "${YELLOW}► Schritt 1: PM2 Crash-Loops stoppen...${NC}"
for APP in windsurf-telegram-bot cratorhub shopify-dashboard; do
  if command -v pm2 &>/dev/null && pm2 describe "$APP" &>/dev/null 2>&1; then
    pm2 stop "$APP" 2>/dev/null && pm2 delete "$APP" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} $APP gestoppt"
  fi
done

# ── Schritt 2: Git Pull (neueste Version) ────────────────────────
echo -e "\n${YELLOW}► Schritt 2: Neueste Version von GitHub...${NC}"
git pull origin claude/practical-faraday-wl7aD --no-rebase 2>/dev/null || git pull --no-rebase 2>/dev/null || echo "  ⚠️ Git pull fehlgeschlagen"
echo -e "  ${GREEN}✓${NC} Aktuell"

# ── Schritt 3: Credentials scannen ──────────────────────────────
echo -e "\n${YELLOW}► Schritt 3: API-Keys von allen .env Dateien sammeln...${NC}"
python3 "$MEGA_DIR/scripts/scan_credentials.py" 2>/dev/null || echo "  ⚠️ scan_credentials.py fehlgeschlagen"

# ── Schritt 4: Python Dependencies ───────────────────────────────
echo -e "\n${YELLOW}► Schritt 4: Python Dependencies prüfen...${NC}"
for pkg in aiohttp python-dotenv; do
  python3 -c "import ${pkg//-/_}" 2>/dev/null \
    && echo -e "  ${GREEN}✓${NC} $pkg" \
    || { pip3 install "$pkg" -q && echo -e "  ${GREEN}✓${NC} $pkg installiert"; }
done

# ── Schritt 5: Port 8888 freimachen ──────────────────────────────
echo -e "\n${YELLOW}► Schritt 5: Port 8888 freimachen...${NC}"
lsof -ti:8888 | xargs -r kill -9 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Port 8888 frei"

# ── Schritt 6: Dashboard starten ─────────────────────────────────
echo -e "\n${YELLOW}► Schritt 6: SuperMegaBot Dashboard starten...${NC}"
nohup python3 "$MEGA_DIR/dashboard/server.py" >> /tmp/supermegabot.log 2>&1 &
DASHBOARD_PID=$!
sleep 3

if kill -0 $DASHBOARD_PID 2>/dev/null; then
  echo -e "  ${GREEN}✓${NC} Dashboard läuft (PID $DASHBOARD_PID)"
else
  echo -e "  ${RED}✗${NC} Dashboard-Start fehlgeschlagen, Log:"
  tail -20 /tmp/supermegabot.log
  exit 1
fi

# ── Schritt 7: API-Test ──────────────────────────────────────────
echo -e "\n${YELLOW}► Schritt 7: Alle APIs testen...${NC}"
python3 "$MEGA_DIR/scripts/test_all_apis.py" 2>/dev/null || echo "  ⚠️ API-Test fehlgeschlagen"

# ── Fertig ────────────────────────────────────────────────────────
echo -e "\n${BOLD}${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║         ALLES LÄUFT!  🚀                  ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${NC}"
echo -e "\n  ${BOLD}Dashboard:${NC}   http://localhost:8888"
echo -e "  ${BOLD}Logs:${NC}        tail -f /tmp/supermegabot.log"
echo -e "\n  ${YELLOW}Automation startet automatisch in 10-30 Sekunden.${NC}\n"

# Öffne Browser (macOS)
command -v open &>/dev/null && open http://localhost:8888 2>/dev/null || true
