#!/bin/bash
# apply_shopify_token.sh — Neuen Shopify Token in alle Projekte eintragen
# Usage: ./apply_shopify_token.sh shpat_1234567890abcdef

TOKEN="$1"
if [ -z "$TOKEN" ]; then
    echo "Usage: $0 <SHOPIFY_ACCESS_TOKEN>"
    echo "Example: $0 shpat_xxxxxxxxxxxxxxxx"
    exit 1
fi

echo "Updating all projects with new Shopify token..."

PROJECTS=(
    "/Users/rudolfsarkany/local-projects/telegram-automation-bot"
    "/Users/rudolfsarkany/windsurf-telegram-bot"
    "/Users/rudolfsarkany/windsurf-shopify-suite"
    "/Users/rudolfsarkany/shopify-ai-suite"
    "/Users/rudolfsarkany/rudibot-eternal"
    "/Users/rudolfsarkany/supermegabot"
)

for proj in "${PROJECTS[@]}"; do
    ENV_FILE="$proj/.env"
    if [ -f "$ENV_FILE" ]; then
        # Backup
        cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
        
        # Update SHOPIFY_ACCESS_TOKEN
        if grep -q "^SHOPIFY_ACCESS_TOKEN=" "$ENV_FILE"; then
            sed -i '' "s/^SHOPIFY_ACCESS_TOKEN=.*/SHOPIFY_ACCESS_TOKEN=$TOKEN/" "$ENV_FILE"
        else
            echo "" >> "$ENV_FILE"
            echo "# Updated by apply_shopify_token.sh" >> "$ENV_FILE"
            echo "SHOPIFY_ACCESS_TOKEN=$TOKEN" >> "$ENV_FILE"
        fi
        echo "  ✅ $ENV_FILE"
    else
        echo "  ⚠️  $ENV_FILE not found"
    fi
done

echo ""
echo "Testing new token..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Shopify-Access-Token: $TOKEN" \
    "https://suitenew.myshopify.com/admin/api/2024-10/shop.json")

if [ "$STATUS" = "200" ]; then
    echo "  ✅ Token valid! (HTTP 200)"
    echo ""
    echo "Restarting affected services..."
    lsof -ti:3200 | xargs kill -9 2>/dev/null
    sleep 2
    cd /Users/rudolfsarkany/local-projects/telegram-automation-bot && nohup node server.js > /tmp/telegram-bot.log 2>&1 &
    echo "  ✅ telegram-automation-bot restarted"
    echo ""
    echo "All done! Shopify 403 error should be resolved."
else
    echo "  ❌ Token invalid (HTTP $STATUS)"
    echo "  Please check your token and try again."
    exit 1
fi
