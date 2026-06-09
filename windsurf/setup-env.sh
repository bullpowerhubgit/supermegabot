#!/bin/bash
# ============================================
# RUDIBOT SECURITY SUITE - Environment Setup
# ============================================

set -e

echo "🔧 RudiBot Environment Setup"
echo "=============================="

# Check if .env exists
if [ -f .env ]; then
  echo "⚠️  .env already exists. Backup to .env.backup"
  cp .env .env.backup
fi

# Create .env from .env.example if it doesn't exist
if [ ! -f .env ]; then
  echo "📝 Creating .env from .env.example"
  cp .env.example .env
  echo "✅ .env created"
else
  echo "ℹ️  .env already exists, skipping creation"
fi

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Pre-commit hook setup
echo "🔒 Setting up pre-commit hook..."
mkdir -p .github/hooks
if [ -f .github/hooks/pre-commit ]; then
  echo "ℹ️  Pre-commit hook already exists"
else
  cp .github/hooks/pre-commit .git/hooks/pre-commit 2>/dev/null || echo "⚠️  Could not install git hook (not a git repo)"
fi

# Build TypeScript
echo "🔨 Building TypeScript..."
npm run build

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your real API keys"
echo "2. Set up Supabase project and run src/db/schema.sql"
echo "3. Run: npm run dev"
echo ""
