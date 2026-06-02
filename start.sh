#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Load env
if [ -f "$DIR/.env" ]; then
    export $(grep -v '^#' "$DIR/.env" | xargs) 2>/dev/null
fi

# ═══════════════════════════════════════════════════════════════════
# Guardian API Check & Integration
# ═══════════════════════════════════════════════════════════════════
GUARDIAN_URL="http://localhost:3201"
GUARDIAN_API_KEY=$(echo -n "$GUARDIAN_API_SECRET" | sha256sum | cut -c1-32)

echo "→ Prüfe Guardian API..."
if curl -s -H "X-API-Key: $GUARDIAN_API_KEY" "$GUARDIAN_URL/api/v1/health" >/dev/null 2>&1; then
    echo "  ✅ Guardian API erreichbar"
    # Register SuperMegaBot startup
    curl -s -X POST -H "X-API-Key: $GUARDIAN_API_KEY" \
         -H "Content-Type: application/json" \
         -d '{"agent_id":"supermegabot-startup","agent_type":"service"}' \
         "$GUARDIAN_URL/api/v1/agents/register" >/dev/null 2>&1
    curl -s -X POST -H "X-API-Key: $GUARDIAN_API_KEY" \
         -H "Content-Type: application/json" \
         -d '{"message":"🚀 SuperMegaBot gestartet (via start.sh)","priority":"normal"}' \
         "$GUARDIAN_URL/api/v1/notify" >/dev/null 2>&1
else
    echo "  ⚠️ Guardian API nicht erreichbar (Port 3201)"
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
echo "║  Guardian: http://localhost:3201 ║"
echo "╚══════════════════════════════════╝"
echo ""

python3 "$DIR/dashboard/server.py"
