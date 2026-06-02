#!/bin/bash
# pre-commit-hook.sh — Lokaler Git Hook für API-Tests vor Commit
# Install: ln -s /Users/rudolfsarkany/supermegabot/pre-commit-hook.sh .git/hooks/pre-commit

set -e

echo "═══════════════════════════════════════════════════════════════"
echo "  PRE-COMMIT: Running API Tests..."
echo "═══════════════════════════════════════════════════════════════"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_RUNNER="$SCRIPT_DIR/api_test_runner.py"

if [ -f "$TEST_RUNNER" ]; then
    if python3 "$TEST_RUNNER"; then
        echo ""
        echo "✅ All API tests passed — Commit allowed"
        exit 0
    else
        echo ""
        echo "❌ API tests FAILED — Commit blocked"
        echo ""
        echo "Fix the errors above before committing."
        echo "To bypass: git commit --no-verify"
        exit 1
    fi
else
    echo "⚠️  Test runner not found at $TEST_RUNNER"
    echo "   Commit allowed (no tests run)"
    exit 0
fi
