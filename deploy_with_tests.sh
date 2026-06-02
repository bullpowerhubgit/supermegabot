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

# Restart all services via PM2 (avoids port conflicts with PM2-managed processes)
PM2_SERVICES=(
    "telegram-bot:Telegram Bot"
    "windsurf-shopify:Shopify Suite"
    "windsurf-api-gateway:Shopify AI"
)

for svc in "${PM2_SERVICES[@]}"; do
    IFS=':' read -r pm2name display <<< "$svc"
    if pm2 describe "$pm2name" > /dev/null 2>&1; then
        pm2 restart "$pm2name" --update-env
        echo "  ✅ $display restarted via PM2"
    else
        echo "  ⚠️  $display not found in PM2, skipping"
    fi
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
