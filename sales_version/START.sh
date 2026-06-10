#!/bin/bash
# AutoPilot CreatorHub AI — Sales Version Start
# Kopiere .env.template zu .env und trage echte Werte ein, dann:
# bash START.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SCRIPT_DIR"

echo ""
echo "⚡ AutoPilot CreatorHub AI — Sales Version"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Setup .env wenn nicht vorhanden
if [ ! -f ".env" ] && [ ! -f "../.env" ]; then
  echo "⚠️  Keine .env gefunden!"
  if [ -f ".env.template" ]; then
    cp .env.template .env
    echo "   .env.template wurde zu .env kopiert."
    echo "   Bitte fülle alle Felder aus, dann nochmal starten."
    echo ""
    echo "   Öffne: $SCRIPT_DIR/.env"
    exit 1
  fi
fi

# Python venv
if [ ! -f "venv/bin/python3" ] && [ ! -f "../.venv/bin/python3" ]; then
  echo "▶ Erstelle Python venv…"
  python3 -m venv venv
  VENV="$SCRIPT_DIR/venv/bin"
else
  VENV="${ROOT_DIR}/.venv/bin"
  [ -d "$SCRIPT_DIR/venv/bin" ] && VENV="$SCRIPT_DIR/venv/bin"
fi

echo "▶ Installiere Dependencies…"
"$VENV/pip" install -q -r requirements.txt 2>&1 | tail -2

# Kill old
PORT="${SALES_PORT:-9000}"
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true

echo "▶ Starte Sales Server auf Port $PORT…"
"$VENV/python3" server.py &
SERVER_PID=$!

sleep 3

if curl -sf "http://localhost:$PORT/login" > /dev/null 2>&1; then
  echo ""
  echo "✅ AutoPilot CreatorHub AI — BEREIT"
  echo ""
  echo "┌─────────────────────────────────────────────┐"
  echo "│  🔒 Login:  http://localhost:$PORT           │"
  echo "│  ⚙️  Setup: http://localhost:$PORT/setup      │"
  echo "│                                             │"
  echo "│  Standard Passwort: autopilot2024           │"
  echo "│  (änderbar via SALES_PASSWORD in .env)      │"
  echo "└─────────────────────────────────────────────┘"
  echo ""
  if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$PORT/login" &
  fi
else
  echo "❌ Server-Start fehlgeschlagen"
  kill $SERVER_PID 2>/dev/null
  exit 1
fi

wait $SERVER_PID
