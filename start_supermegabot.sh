#!/bin/bash
# SuperMegaBot — Einzel-Klick Vollstart
# Startet alle Systeme, prüft Status, öffnet Dashboard
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/data/startup.log"
RAIL="https://supermegabot-production.up.railway.app"
LOCAL="http://localhost:8888"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "═══════════════════════════════════════════"
log "  SuperMegaBot VOLLSTART"
log "═══════════════════════════════════════════"

# ── 1. Env laden ──────────────────────────────
if [ -f "$DIR/.env" ]; then
  export $(grep -v '^#' "$DIR/.env" | grep -v '^$' | xargs) 2>/dev/null || true
  log "✅ .env geladen ($(grep -c '=' "$DIR/.env") Keys)"
fi

# ── 2. Railway Health prüfen ──────────────────
log "🔍 Railway-Status prüfen..."
HEALTH=$(curl -sf "$RAIL/health" 2>/dev/null || echo '{"status":"offline"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
OPEN=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('circuits_open',[])))" 2>/dev/null || echo "")

if [ "$STATUS" = "ok" ]; then
  log "✅ Railway ONLINE"
  [ -n "$OPEN" ] && log "⚠️  Offene Breaker: $OPEN" || log "✅ Alle Circuit Breaker geschlossen"
else
  log "⚠️  Railway nicht erreichbar — starte LOKAL"
fi

# ── 3. Lokalen Server starten (falls nicht läuft) ─────────────
if ! curl -sf "$LOCAL/health" > /dev/null 2>&1; then
  log "🚀 Starte lokalen Server..."
  cd "$DIR"
  nohup python3 dashboard/server.py >> "$LOG" 2>&1 &
  SERVER_PID=$!
  echo $SERVER_PID > "$DIR/data/server.pid"
  log "   PID: $SERVER_PID — warte auf Start..."
  for i in $(seq 1 20); do
    sleep 1
    curl -sf "$LOCAL/health" > /dev/null 2>&1 && break
    [ $i -eq 20 ] && log "⚠️  Lokaler Server antwortet nicht (Railway bleibt aktiv)"
  done
  curl -sf "$LOCAL/health" > /dev/null 2>&1 && log "✅ Lokaler Server läuft auf :8888" || true
fi

# ── 4. Alle Systeme aktivieren ────────────────
BASE="${RAIL}"

log ""
log "💰 GELDGENERIERUNG — ALLE SYSTEME STARTEN"
log "─────────────────────────────────────────"

# Circuit Breaker reset (persistent)
RES=$(curl -sf -X POST "$BASE/api/circuit/reset" 2>/dev/null || echo '{}')
log "⚡ Circuit Breaker: reset → $(echo $RES | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK: '+str(d.get('reset',[]))) " 2>/dev/null || echo 'OK')"

# Mass Outreach Research (Leads sammeln)
log "🔍 Mass-Outreach Research starten..."
RES=$(curl -sf -X POST "$BASE/api/mass-outreach/research" 2>/dev/null || echo '{"started":false}')
log "   → $(echo $RES | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)" 2>/dev/null || echo $RES)"

# Mass Outreach Batch (1000 Emails)
log "📧 Mass-Outreach Batch (1000 Emails) starten..."
RES=$(curl -sf -X POST "$BASE/api/mass-outreach/send" 2>/dev/null || echo '{"started":false}')
log "   → $(echo $RES | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)" 2>/dev/null || echo $RES)"

# Shopify Sync
log "🛍️  Shopify Sync..."
curl -sf -X POST "$BASE/api/shopify/sync" > /dev/null 2>&1 && log "   → gestartet" || log "   → Route nicht verfügbar"

# Auto-Repair Cycle
log "🔧 Auto-Repair Cycle..."
curl -sf -X POST "$BASE/api/repair/run" > /dev/null 2>&1 && log "   → gestartet" || log "   → skip"

# Digistore Sync
log "💳 Digistore24 Revenue Sync..."
curl -sf -X POST "$BASE/api/digistore/sync" > /dev/null 2>&1 && log "   → gestartet" || log "   → skip"

log ""
log "═══════════════════════════════════════════"
log "✅ ALLE SYSTEME GESTARTET"
log ""
log "📊 Dashboard: $BASE"
log "📧 Outreach:  $BASE/api/mass-outreach/stats"
log "📞 Phone AI:  $BASE/api/phone/stats"
log "📝 Log:       $LOG"
log "═══════════════════════════════════════════"
log ""

# ── 5. Dashboard im Browser öffnen ───────────
open "$BASE" 2>/dev/null || true
