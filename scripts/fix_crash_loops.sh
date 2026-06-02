#!/usr/bin/env bash
# ================================================================
# FIX CRASH LOOPS — Sofort-Fix für PM2 Crash-Schleifen
# Führe aus: bash ~/supermegabot/scripts/fix_crash_loops.sh
# ================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

echo -e "\n${BLUE}════════════════════════════════════════════${NC}"
echo -e "${BLUE}  SuperMegaBot — Crash-Loop Fix${NC}"
echo -e "${BLUE}════════════════════════════════════════════${NC}\n"

# ── 1. Zeige aktuelle PM2-Last ────────────────────────────────
echo -e "${YELLOW}[1/5] Aktuelle PM2 Status...${NC}"
pm2 list 2>/dev/null || echo "PM2 nicht verfügbar"

# ── 2. Stoppe die crash-loopenden Apps sofort ─────────────────
echo -e "\n${YELLOW}[2/5] Stoppe Crash-Loop-Apps...${NC}"
for APP in windsurf-telegram-bot cratorhub shopify-dashboard; do
  if pm2 describe "$APP" &>/dev/null; then
    echo -e "  ${RED}●${NC} Stoppe $APP..."
    pm2 stop "$APP" 2>/dev/null || true
    pm2 delete "$APP" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} $APP gestoppt + gelöscht"
  else
    echo -e "  ${YELLOW}○${NC} $APP nicht in PM2"
  fi
done

# ── 3. Zeige letzten Log-Fehler ────────────────────────────────
echo -e "\n${YELLOW}[3/5] Letzte Fehler-Logs...${NC}"
for LOGFILE in /tmp/windsurf-telegram-bot*.log /tmp/cratorhub*.log /tmp/shopify-dashboard*.log; do
  [ -f "$LOGFILE" ] && echo -e "\n  ${BLUE}$LOGFILE${NC}:" && tail -15 "$LOGFILE" 2>/dev/null | grep -i "error\|Error\|ERR\|ENOENT\|Cannot\|crash" | head -8 || true
done

# ── 4. Lade ecosystem.config.js mit Fix-Einstellungen neu ──────
echo -e "\n${YELLOW}[4/5] Lade ecosystem.config.js mit Exponential-Backoff neu...${NC}"
MEGA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$MEGA_DIR/ecosystem.config.js" ]; then
  pm2 reload "$MEGA_DIR/ecosystem.config.js" --update-env 2>/dev/null || pm2 start "$MEGA_DIR/ecosystem.config.js" 2>/dev/null || true
  echo -e "  ${GREEN}✓${NC} ecosystem.config.js geladen"
else
  echo -e "  ${RED}✗${NC} ecosystem.config.js nicht gefunden"
fi

# ── 5. Speichere PM2-Konfiguration ────────────────────────────
echo -e "\n${YELLOW}[5/5] Speichere PM2-Konfiguration...${NC}"
pm2 save 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} Gespeichert"

# ── Zusammenfassung ───────────────────────────────────────────
echo -e "\n${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Fix abgeschlossen!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "\n${YELLOW}Load Average jetzt:${NC} $(uptime | awk -F'load averages:' '{print $2}')"
echo -e "\n${YELLOW}Nächster Schritt:${NC}"
echo "  bash ~/supermegabot/scripts/scan_credentials.py"
echo -e "\n${BLUE}Dashboard:${NC} http://localhost:8888\n"
