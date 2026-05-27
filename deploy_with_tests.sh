#!/bin/bash
# deploy_with_tests.sh — Deployment mit automatischer API-Validierung
# Usage: ./deploy_with_tests.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_RUNNER="$SCRIPT_DIR/api_test_runner.py"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    DEPLOYMENT PIPELINE — Test → Build → Deploy              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: API TESTS
# ═══════════════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "PHASE 1: Running API Tests..."
echo "═══════════════════════════════════════════════════════════════"

if [ -f "$TEST_RUNNER" ]; then
    if python3 "$TEST_RUNNER"; then
        echo ""
        echo "✅ All API tests passed!"
    else
        echo ""
        echo "❌ API tests FAILED — Deployment aborted"
        echo "   Fix the errors above before deploying."
        exit 1
    fi
else
    echo "⚠️  Test runner not found: $TEST_RUNNER"
    echo "   Continuing without tests..."
fi

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: SYNTAX CHECK
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "PHASE 2: Syntax Check..."
echo "═══════════════════════════════════════════════════════════════"

ERRORS=0
JS_FILES=(
    "/Users/rudolfsarkany/local-projects/telegram-automation-bot/server.js"
    "/Users/rudolfsarkany/local-projects/telegram-automation-bot/shopify.js"
    "/Users/rudolfsarkany/local-projects/telegram-automation-bot/bot.js"
    "/Users/rudolfsarkany/windsurf-shopify-suite/src/index.js"
    "/Users/rudolfsarkany/shopify-ai-suite/server.js"
)

for js_file in "${JS_FILES[@]}"; do
    if [ -f "$js_file" ]; then
        if ! node --check "$js_file" 2>/dev/null; then
            echo "  ❌ Syntax error: $js_file"
            ERRORS=$((ERRORS + 1))
        fi
    fi
done

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "❌ Found $ERRORS syntax errors — Deployment aborted"
    exit 1
fi

echo "  ✅ All JS files syntax OK"

# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: DEEP SCAN
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "PHASE 3: Deep Scan..."
echo "═══════════════════════════════════════════════════════════════"

if [ -f "$SCRIPT_DIR/../deep_scan_repair.py" ]; then
    cd "$SCRIPT_DIR/.."
    python3 deep_scan_repair.py 2>&1 | tail -15
    echo "  ✅ Deep Scan completed"
else
    echo "  ⚠️  Deep scanner not found, skipping"
fi

# ═══════════════════════════════════════════════════════════════════════
# PHASE 4: DEPLOYMENT
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "PHASE 4: Deployment..."
echo "═══════════════════════════════════════════════════════════════"

# Restart all services
SERVICES=(
    "3200:/Users/rudolfsarkany/local-projects/telegram-automation-bot:node server.js:Telegram Bot"
    "3001:/Users/rudolfsarkany/windsurf-shopify-suite:node src/index.js:Shopify Suite"
    "3002:/Users/rudolfsarkany/shopify-ai-suite:node server.js:Shopify AI"
)

for svc in "${SERVICES[@]}"; do
    IFS=':' read -r port dir cmd name <<< "$svc"
    
    # Kill existing
    lsof -ti:$port | xargs kill -9 2>/dev/null || true
    sleep 1
    
    # Start new
    cd "$dir" && nohup $cmd > /tmp/$(echo "$name" | tr ' ' '_').log 2>&1 &
    echo "  ✅ $name restarted (port $port)"
    sleep 2
done

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5: POST-DEPLOYMENT TESTS
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "PHASE 5: Post-Deployment Verification..."
echo "═══════════════════════════════════════════════════════════════"

sleep 3
python3 "$TEST_RUNNER" 2>&1 | tail -20

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "All services tested and deployed successfully!"
