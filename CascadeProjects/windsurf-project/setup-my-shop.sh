#!/bin/bash
# My-Shop komplettes Setup und Start

set -e

echo "🛒 SuperMegaBot My-Shop Setup"
echo "================================"

# Zum Projektordner wechseln
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "📦 1. Backend Dependencies installieren..."
cd my-shop/backend
npm install

echo ""
echo "📦 2. Frontend Dependencies installieren..."
cd ../frontend
npm install

echo ""
echo "🚀 3. Backend starten (im Hintergrund)..."
cd ../backend
node index.js &
BACKEND_PID=$!

echo ""
echo "🚀 4. Frontend starten..."
cd ../frontend
npx vite --port 3000

# Cleanup bei Strg+C
trap "echo ''; echo '🛑 Beende Backend (PID $BACKEND_PID)...'; kill $BACKEND_PID 2>/dev/null; exit 0" INT

wait $BACKEND_PID
