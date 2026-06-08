#!/bin/bash
# ============================================
# RUDIBOT SECURITY SUITE - Vercel Deployment
# ============================================

set -e

echo "▲ RudiBot Vercel Deployment"
echo "=============================="

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
  echo "📦 Installing Vercel CLI..."
  npm install -g vercel
fi

# Build
echo "🔨 Building project..."
npm run build

# Login
echo "🔐 Logging into Vercel..."
vercel login

# Link project
echo "🔗 Linking project to rudibot..."
vercel link --yes

# Set environment variables
echo "⚙️  Setting environment variables..."
vercel env add SUPABASE_URL production
vercel env add SUPABASE_SERVICE_KEY production
vercel env add SUPABASE_ANON_KEY production
vercel env add STRIPE_SECRET_KEY production
vercel env add STRIPE_WEBHOOK_SECRET production
vercel env add OPENAI_API_KEY production
vercel env add TELEGRAM_BOT_TOKEN production

# Deploy to production
echo "🚀 Deploying to Vercel production..."
vercel --prod

echo ""
echo "✅ Vercel deployment complete!"
echo ""
echo "Your app is now live at:"
echo "https://rudibot.vercel.app"
echo ""
