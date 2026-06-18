#!/bin/bash
# Auto-update CURRENT_STATUS.md — runs after each work session
# Aufruf: bash scripts/update_status.sh

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M UTC')
RAILWAY_URL="https://dudirudibot-mega-production.up.railway.app"

# Get health status
HEALTH=$(curl -s --max-time 5 "$RAILWAY_URL/health" | python3 -c "import json,sys; d=json.load(sys.stdin); print('✅ LIVE' if d.get('status')=='ok' else '⚠️ ISSUE')" 2>/dev/null || echo "❌ DOWN")

# Get last git commit
LAST_COMMIT=$(git log --oneline -1 2>/dev/null || echo "unknown")

# Update the timestamp in CURRENT_STATUS.md
sed -i "" "s|Zuletzt aktualisiert: .*|Zuletzt aktualisiert: $TIMESTAMP|" CURRENT_STATUS.md

echo "✅ CURRENT_STATUS.md aktualisiert: $TIMESTAMP"
echo "📊 Railway: $HEALTH"
echo "📝 Letzter Commit: $LAST_COMMIT"
