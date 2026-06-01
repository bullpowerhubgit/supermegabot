#!/bin/bash

# QuickCash System Deployment Script
# Team: bullpowerhubgits-projects
# Team-ID: team_xulvdt7sib2RSt4BNoqVWeSy

echo "🚀 QuickCash System Deployment Starting..."

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "📦 Installing Vercel CLI..."
    npm install -g vercel
fi

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Build project
echo "🔨 Building project..."
npm run build

# Deploy to Vercel Team
echo "🚀 Deploying to Vercel Team..."
vercel --team team_xulvdt7sib2RSt4BNoqVWeSy --prod

echo "✅ Deployment completed!"
echo "📊 Visit: https://vercel.com/bullpowerhubgits-projects/"
echo "🔧 Don't forget to set ANTHROPIC_API_KEY in Vercel Dashboard"
