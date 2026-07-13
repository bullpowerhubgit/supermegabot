#!/bin/bash
# Update .env mit neuen Keys aus .env.new

ENV_FILE="/Users/rudolfsarkany/CascadeProjects/rudibot/.env"
ENV_NEW="/Users/rudolfsarkany/CascadeProjects/rudibot/.env.new"

echo "🔄 Aktualisiere .env mit neuen Keys..."

# Backup erstellen
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo "✅ Backup erstellt: $ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"

# Shopify Admin Token (neu gefunden)
SHOPIFY_TOKEN=$(grep -o 'shpat_REDACTED' "$ENV_NEW" | head -1)
if [ ! -z "$SHOPIFY_TOKEN" ]; then
    sed -i.bak "s|SHOPIFY_ADMIN_TOKEN=.*|SHOPIFY_ADMIN_TOKEN=$SHOPIFY_TOKEN|" "$ENV_FILE"
    echo "✅ SHOPIFY_ADMIN_TOKEN aktualisiert"
fi

# Shopify Client Secret (neu gefunden)
SHOPIFY_SECRET=$(grep -o '***REDACTED_SHOPIFY_SECRET***' "$ENV_NEW" | head -1)
if [ ! -z "$SHOPIFY_SECRET" ]; then
    sed -i.bak "s|SHOPIFY_CLIENT_SECRET=.*|SHOPIFY_CLIENT_SECRET=$SHOPIFY_SECRET|" "$ENV_FILE"
    echo "✅ SHOPIFY_CLIENT_SECRET aktualisiert"
fi

# Klaviyo Key (neu gefunden)
KLAVIYO_KEY=$(grep -o 'pk_X7HUrZ_933ca50212317aed57ac767e86e4d7b1e6' "$ENV_NEW" | head -1)
if [ ! -z "$KLAVIYO_KEY" ]; then
    sed -i.bak "s|KLAVIYO_API_KEY=.*|KLAVIYO_API_KEY=$KLAVIYO_KEY|" "$ENV_FILE"
    echo "✅ KLAVIYO_API_KEY aktualisiert"
fi

# Telegram Token 2 (falls vorhanden)
TELEGRAM2=$(grep -o '8320990321:[a-zA-Z0-9_-]*' "$ENV_NEW" | head -1)
if [ ! -z "$TELEGRAM2" ]; then
    if grep -q "TELEGRAM_BOT_TOKEN_2=" "$ENV_FILE"; then
        sed -i.bak "s|TELEGRAM_BOT_TOKEN_2=.*|TELEGRAM_BOT_TOKEN_2=$TELEGRAM2|" "$ENV_FILE"
    else
        echo "TELEGRAM_BOT_TOKEN_2=$TELEGRAM2" >> "$ENV_FILE"
    fi
    echo "✅ TELEGRAM_BOT_TOKEN_2 aktualisiert"
fi

echo "🧹 Aufräumen..."
rm -f "$ENV_FILE.bak"

echo "✅ .env aktualisiert!"
echo ""
echo "📊 Zusammenfassung der Änderungen:"
echo "   • Shopify Admin Token: ${SHOPIFY_TOKEN:0:8}...${SHOPIFY_TOKEN: -8}"
echo "   • Shopify Client Secret: ${SHOPIFY_SECRET:0:8}...${SHOPIFY_SECRET: -8}"
echo "   • Klaviyo API Key: ${KLAVIYO_KEY:0:8}...${KLAVIYO_KEY: -8}"
echo "   • Telegram Bot Token 2: ${TELEGRAM2:0:8}...${TELEGRAM2: -8}"
echo ""
echo "🧪 Jetzt APIs testen mit:"
echo "   cd /Users/rudolfsarkany/CascadeProjects/rudibot && node simple-test.js"
