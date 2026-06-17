#!/bin/bash
# ============================================
# RUDIBOT SECURITY SUITE - Railway Deployment
# ============================================

set -e

echo "🚂 RudiBot Railway Deployment"
echo "=============================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
  echo "📦 Installing Railway CLI..."
  npm install -g @railway/cli
fi

# Login
echo "🔐 Logging into Railway..."
railway login

# Initialize project
if [ ! -f railway.json ]; then
  echo "📁 Initializing Railway project..."
  railway init
fi

# Set environment variables
echo "⚙️  Setting environment variables..."

# Required variables
railway variables set SUPABASE_URL=${SUPABASE_URL}
railway variables set SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
railway variables set SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
railway variables set STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
railway variables set STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
railway variables set OPENAI_API_KEY=${OPENAI_API_KEY}
railway variables set TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}

# Optional variables
railway variables set OPENCLAW_URL=${OPENCLAW_URL:-ws://127.0.0.1:18789}
railway variables set NODE_ENV=${NODE_ENV:-production}
railway variables set PORT=${PORT:-3001}

# Deploy
echo "🚀 Deploying to Railway..."
railway up

echo ""
echo "✅ Railway deployment complete!"
echo ""
echo "Your app is now live at:"
railway domain
echo ""
