#!/bin/bash
# ============================================
# RUDIBOT SECURITY SUITE - Supabase Setup
# ============================================

set -e

echo "🗄️  RudiBot Supabase Setup"
echo "=============================="

# Check for required environment variables
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
  echo "❌ Missing required environment variables:"
  echo "   SUPABASE_URL"
  echo "   SUPABASE_SERVICE_KEY"
  echo ""
  echo "Please set these in your .env file first."
  exit 1
fi

# Check if psql is installed
if ! command -v psql &> /dev/null; then
  echo "❌ psql is not installed. Please install PostgreSQL client."
  exit 1
fi

# Extract connection details from SUPABASE_URL
SUPABASE_HOST=$(echo $SUPABASE_URL | sed -n 's|https://||p')
SUPABASE_DB="postgres"
SUPABASE_USER="postgres"

echo "📋 Connection Details:"
echo "   Host: $SUPABASE_HOST"
echo "   Database: $SUPABASE_DB"
echo "   User: $SUPABASE_USER"
echo ""

# Ask for password
read -sp "Enter Supabase database password (from .env SUPABASE_DB_PASSWORD): " DB_PASSWORD
echo ""

# Test connection
echo "🔌 Testing connection..."
PGPASSWORD=$DB_PASSWORD psql -h $SUPABASE_HOST -U $SUPABASE_USER -d $SUPABASE_DB -c "SELECT version();" > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✅ Connection successful"
else
  echo "❌ Connection failed. Please check your credentials."
  exit 1
fi

# Run schema
echo "📝 Running database schema..."
PGPASSWORD=$DB_PASSWORD psql -h $SUPABASE_HOST -U $SUPABASE_USER -d $SUPABASE_DB -f src/db/schema.sql

if [ $? -eq 0 ]; then
  echo "✅ Schema applied successfully"
else
  echo "❌ Schema application failed"
  exit 1
fi

# Create initial admin user (optional)
echo ""
read -p "Create initial admin user? (y/n): " CREATE_ADMIN
if [ "$CREATE_ADMIN" = "y" ]; then
  read -p "Admin email: " ADMIN_EMAIL
  read -sp "Admin password: " ADMIN_PASSWORD
  echo ""
  
  # This would use Supabase Auth API - for now, just note it
  echo "ℹ️  Admin user creation requires Supabase Auth API integration"
  echo "   Email: $ADMIN_EMAIL"
  echo "   Please create via Supabase Dashboard: https://supabase.com/dashboard"
fi

echo ""
echo "✅ Supabase setup complete!"
echo ""
echo "Next steps:"
echo "1. Verify tables in Supabase Dashboard"
echo "2. Enable Row Level Security (RLS) policies"
echo "3. Configure environment variables for API"
echo ""
