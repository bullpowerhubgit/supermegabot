#!/bin/bash
# ╔═════════════════════════════════════════════════════════��╗
# ║  START ALL — RudiBot Complete System Launcher           ║
# ║  Startet alle Systeme mit einem Befehl                  ║
# ╚══════════════════════════════════════════════════════════╝

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$HOME"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; }

echo "╔══════════════════════════════════════════════════╗"
echo "║   🤖 RUDIBOT COMPLETE SYSTEM LAUNCHER           ║"
echo "║   $(date +'%Y-%m-%d %H:%M:%S')                         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Ollama (lokale KI) ─────────────────────────────────
echo "[ 1/6 ] Starte Ollama..."
if pgrep -f "ollama serve" > /dev/null 2>&1; then
  ok "Ollama läuft bereits"
else
  nohup ollama serve >> /tmp/ollama.log 2>&1 &
  sleep 2
  if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    ok "Ollama gestartet"
  else
    warn "Ollama Start — warte weitere 5s..."
    sleep 5
  fi
fi

# ── 2. Password-Sync: Dependencies prüfen ────────────────
echo ""
echo "[ 2/6 ] Password-Sync Dependencies..."
PW_DIR="$HOME_DIR/password-sync-suite/web-app"
if [ -d "$PW_DIR" ] && [ ! -d "$PW_DIR/node_modules" ]; then
  echo "  npm install für password-sync..."
  cd "$PW_DIR" && npm install --silent
  cd "$SCRIPT_DIR"
  ok "password-sync Dependencies installiert"
else
  ok "password-sync Dependencies OK"
fi

# ── 3. PM2 — alle Prozesse starten ───────────────────────
echo ""
echo "[ 3/6 ] PM2 Prozesse starten..."
ECO="$SCRIPT_DIR/ecosystem.config.js"

if ! command -v pm2 &> /dev/null; then
  warn "PM2 nicht gefunden — installiere..."
  npm install -g pm2 --silent
fi

# PM2 starten/neu laden
if pm2 list > /dev/null 2>&1; then
  echo "  PM2 bereits aktiv — reload..."
  pm2 reload "$ECO" --update-env 2>/dev/null || pm2 start "$ECO" --update-env
else
  pm2 start "$ECO" --update-env
fi

sleep 3
ok "PM2 Prozesse aktiv"

# ── 4. PM2 speichern (Autostart) ─────────────────────────
echo ""
echo "[ 4/6 ] PM2 speichern..."
pm2 save --force > /dev/null 2>&1
ok "PM2 gespeichert (Autostart bei Reboot)"

# ── 5. Status-Check ───────────────────────────────────────
echo ""
echo "[ 5/6 ] Status-Check..."
sleep 2

SERVICES=(
  "8888:SuperMegaBot Dashboard"
  "9002:Windsurf Unified Dashboard"
  "9003:Windsurf Watchdog Monitor"
  "9998:Windsurf Agenten-Hub"
  "3005:Password-Sync"
  "11434:Ollama"
  "3200:Telegram Bot"
  "9000:Windsurf Autoheal"
)

for svc in "${SERVICES[@]}"; do
  PORT="${svc%%:*}"
  NAME="${svc##*:}"
  if curl -sf "http://localhost:$PORT" > /dev/null 2>&1 || \
     curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1 || \
     curl -sf "http://localhost:$PORT/api/tags" > /dev/null 2>&1; then
    ok "$NAME (Port $PORT)"
  else
    warn "$NAME (Port $PORT) — möglicherweise noch am Starten"
  fi
done

# ── 6. Zusammenfassung ────────────────────────────────────
echo ""
echo "[ 6/6 ] Zusammenfassung"
echo ""
pm2 list --no-color 2>/dev/null | grep -E "(online|stopped|errored|name)" | head -20
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ System gestartet!                            ║"
echo "║                                                   ║"
echo "║  Dashboard:  http://localhost:8888                ║"
echo "║  Pw-Sync:    http://localhost:3005                ║"
echo "║  Telegram:   Schreibe /hub im Bot                ║"
echo "║                                                   ║"
echo "║  Logs: pm2 logs --lines 50                       ║"
echo "║  Stop: pm2 stop all                              ║"
echo "║  Neu:  ./start_all.sh                            ║"
echo "╚══════════════════════════════════════════════════╝"
