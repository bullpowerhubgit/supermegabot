#!/bin/bash
# ╔══════════════════════════════════════════════════╗
# ║  AutoPilot CreatorHub AI — 1-Knopf-Start        ║
# ║  Startet alle Systeme und öffnet das Dashboard  ║
# ╚══════════════════════════════════════════════════╝

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "⚡ AutoPilot CreatorHub AI — Start"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Python venv ────────────────────────────────────
if [ ! -f ".venv/bin/python3" ]; then
  echo "▶ Erstelle Python venv…"
  python3 -m venv .venv
fi

echo "▶ Installiere Dependencies…"
.venv/bin/pip install -q aiohttp python-dotenv anthropic requests prometheus-client rich 2>&1 | tail -2

# ── Stop old instances ─────────────────────────────
echo "▶ Stoppe alte Prozesse…"
lsof -ti:8888 | xargs kill -9 2>/dev/null || true

# ── Start Dashboard ────────────────────────────────
echo "▶ Starte Dashboard auf Port 8888…"
nohup .venv/bin/python3 dashboard/server.py >> /tmp/autopilot.log 2>&1 &
DASHBOARD_PID=$!

# ── Wait for startup ───────────────────────────────
echo "▶ Warte auf Server…"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://localhost:8888/health > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# ── Health check ───────────────────────────────────
if curl -sf http://localhost:8888/health > /dev/null 2>&1; then
  echo "✅ Dashboard läuft! PID: $DASHBOARD_PID"
else
  echo "❌ Dashboard-Start fehlgeschlagen. Logs: tail -f /tmp/autopilot.log"
  exit 1
fi

# ── Print URLs ─────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  🤖 AutoPilot CreatorHub AI — LIVE          │"
echo "│                                             │"
echo "│  ⚡ Haupt-Dashboard:                        │"
echo "│     http://localhost:8888/autopilot         │"
echo "│                                             │"
echo "│  💰 Revenue Autopilot:                      │"
echo "│     http://localhost:8888/revenue           │"
echo "│                                             │"
echo "│  📊 System-Dashboard:                       │"
echo "│     http://localhost:8888/                  │"
echo "│                                             │"
echo "│  🔌 API Status:                             │"
echo "│     http://localhost:8888/health            │"
echo "│     http://localhost:8888/api/agents/status │"
echo "│                                             │"
echo "│  📝 Logs: tail -f /tmp/autopilot.log        │"
echo "└─────────────────────────────────────────────┘"
echo ""

# ── Open Browser ───────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  open "http://localhost:8888/autopilot" &
fi

echo "⚡ System aktiv. Strg+C zum Stoppen."
echo ""

# ── Keep alive ─────────────────────────────────────
wait $DASHBOARD_PID
