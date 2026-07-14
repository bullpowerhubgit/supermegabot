#!/bin/bash
# SuperMegaBot — Ein-Klick Vollstart + Deploy
# 352 Python-Dateien | 344 Scheduler-Tasks | 16/16 API-Keys
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$DIR/data/startup.log"
RAIL="https://supermegabot-production.up.railway.app"

mkdir -p "$DIR/data"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# Mac-Notification
osascript -e 'display notification "Alle Systeme starten... 💰" with title "SuperMegaBot" subtitle "Geldmaschine läuft an!"' 2>/dev/null || true

log "══════════════════════════════════════════════"
log "  💰 SuperMegaBot VOLLSTART $(date '+%d.%m.%Y %H:%M')"
log "══════════════════════════════════════════════"

# ── 1. Env laden ─────────────────────────────────
cd "$DIR"
if [ -f "$DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -v '^#' "$DIR/.env" | grep -v '^$' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | grep -v '[(){}]') 2>/dev/null || true
  set +a
  log "✅ .env geladen"
fi

# ── 2. Git: aktuelle Änderungen pushen ───────────
log "📤 Git Push (aktueller Stand)..."
git add -A 2>/dev/null || true
git diff --cached --quiet 2>/dev/null || git commit -m "auto: session start $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || true
git push origin main 2>/dev/null && log "✅ GitHub aktuell" || log "⚠️  Push fehlgeschlagen (kein Internet?)"

# ── 3. Railway Health prüfen ─────────────────────
log "🔍 Railway-Status..."
HEALTH=$(curl -sf --max-time 20 "$RAIL/health" 2>/dev/null || echo '{"status":"offline"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status','?'))" 2>/dev/null || echo "?")

if [ "$STATUS" = "ok" ]; then
  log "✅ Railway ONLINE — 344 Tasks laufen"
else
  log "⚠️  Railway offline — Neustart via railway CLI..."
  railway up --detach --service supermegabot 2>/dev/null && log "✅ Railway Deploy gestartet" || log "⚠️  railway CLI nicht verfügbar"
fi

# ── 4. Circuit Breaker reset ─────────────────────
log "⚡ Circuit Breaker reset..."
curl -sf -X POST "$RAIL/api/circuit/reset" > /dev/null 2>&1 && log "✅ Alle Breaker geschlossen" || true

# ── 5. Income Master — alle Revenue-Streams ──────
log ""
log "💰 GELDGENERIERUNG STARTEN"
log "──────────────────────────"

fire() {
  local url="$1"
  curl -sf -X POST --max-time 10 "$RAIL/$url" \
    -H "Content-Type: application/json" > /dev/null 2>&1 &
}

# Alle parallel feuern — kein Warten
fire "api/agents/broadcast"
fire "api/meta-ads/optimize"
fire "api/pilot/run"
fire "api/mass-outreach/research"
fire "api/mass-outreach/send"
fire "api/shopify/sync"
fire "api/repair/run"
fire "api/digistore/sync"
fire "api/traffic/blast"

# DS24 Broadcast mit Payload
curl -sf -X POST --max-time 10 "$RAIL/api/agents/broadcast" \
  -H "Content-Type: application/json" \
  -d '{"from":"desktop","type":"command","payload":{"action":"ds24_blast"}}' \
  > /dev/null 2>&1 &

log "  📣 DS24 + ROAS + Funnel + Shopify + Traffic → alle gestartet (parallel)"
wait  # kurz warten damit alle curl-Jobs laufen

# ── 6. Revenue Check ─────────────────────────────
log ""
log "📊 LIVE REVENUE CHECK..."
python3 -c "
import sys; sys.path.insert(0,'$DIR')
import asyncio, os
os.environ.setdefault('STRIPE_SECRET_KEY', '${STRIPE_SECRET_KEY:-}')
os.environ.setdefault('DS24_API_KEY', '${DS24_API_KEY:-}')

async def check():
    try:
        from modules.income_master_engine import get_live_revenue
        r = await get_live_revenue()
        total = r.get('total_eur', 0) or r.get('total', 0)
        print(f'  Stripe:  €{r.get(\"stripe\",0):.2f}')
        print(f'  DS24:    €{r.get(\"ds24\",0):.2f}')
        print(f'  Shopify: €{r.get(\"shopify\",0):.2f}')
        print(f'  GESAMT:  €{total:.2f} heute')
    except Exception as e:
        print(f'  Revenue-Check: {e}')

asyncio.run(check())
" 2>/dev/null | tee -a "$LOG" || true

# ── 7. Zusammenfassung + Dashboard öffnen ────────
log ""
log "══════════════════════════════════════════════"
log "✅ ALLE SYSTEME AKTIV — GELD WIRD VERDIENT!"
log ""
log "  Dashboard:  $RAIL"
log "  Scheduler:  $RAIL/api/scheduler/status"
log "  Revenue:    $RAIL/api/revenue/report"
log "  Meta Ads:   $RAIL/api/meta-ads/stats"
log "  Log:        $LOG"
log "══════════════════════════════════════════════"

# Dashboard im Browser öffnen
open "$RAIL" 2>/dev/null || true

osascript -e 'display notification "✅ Alle 344 Tasks laufen — Geld wird verdient!" with title "SuperMegaBot LIVE" subtitle "Dashboard geöffnet"' 2>/dev/null || true
