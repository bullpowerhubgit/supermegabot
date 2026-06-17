#!/bin/bash
# RudiBot Server Starter mit Health-Check

echo "🚀 Starting RudiBot Server..."
echo "═══════════════════════════════════════════"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    exit 1
fi

# Load environment
export $(cat .env | grep -v '^#' | xargs)

echo "📡 Starting server on port ${PORT:-3200}..."
echo "🌐 Health-Check: http://localhost:${PORT:-3200}/api/status"
echo "🤖 Telegram Bot: @DUDIRUDIBOT or @RUDICLUDIBOT"
echo "🛒 Shopify Webhook: https://ineedit.com.co/webhooks/shopify"
echo ""
echo "📋 Available Commands:"
echo "   /status    - System Status"
echo "   /claude    - Claude AI"
echo "   /perplexity - Perplexity AI"
echo "   /github    - GitHub Repos"
echo "   /stripe    - Stripe Balance"
echo "   /shopify   - Shopify Store"
echo "   /help      - All Commands"
echo ""
echo "⏹️  Press CTRL+C to stop server"
echo "═══════════════════════════════════════════"

# Start server
node server.js
