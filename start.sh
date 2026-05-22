#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Load env
if [ -f "$DIR/.env" ]; then
    export $(grep -v '^#' "$DIR/.env" | xargs) 2>/dev/null
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
echo "╚══════════════════════════════════╝"
echo ""

python3 "$DIR/dashboard/server.py"
