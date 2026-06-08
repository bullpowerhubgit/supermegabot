#!/bin/bash
# Quick API Key Extraction from .env.new

echo "═══════════════════════════════════════════"
echo "  API KEY EXTRACTOR - .env.new"
echo "═══════════════════════════════════════════"
echo

echo "🔍 NEUE/VERÄNDERTE KEYS aus .env.new:"
echo

# Shopify Admin Token
SHOPIFY_TOKEN=$(grep -o 'shpat_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$SHOPIFY_TOKEN" ]; then
    echo "🔑 SHOPIFY_ADMIN_TOKEN: ${SHOPIFY_TOKEN:0:8}...${SHOPIFY_TOKEN: -8}"
fi

# Shopify Secret
SHOPIFY_SECRET=$(grep -o 'shpss_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | tail -1)
if [ ! -z "$SHOPIFY_SECRET" ]; then
    echo "🔑 SHOPIFY_CLIENT_SECRET: ${SHOPIFY_SECRET:0:8}...${SHOPIFY_SECRET: -8}"
fi

# Klaviyo Key (neu)
KLAVIYO_KEY=$(grep -o 'pk_X7HUrZ_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new)
if [ ! -z "$KLAVIYO_KEY" ]; then
    echo "🔑 KLAVIYO_API_KEY (neu): ${KLAVIYO_KEY:0:8}...${KLAVIYO_KEY: -8}"
fi

# Telegram Tokens
TELEGRAM1=$(grep -o '8600739487:[a-zA-Z0-9_-]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
TELEGRAM2=$(grep -o '8320990321:[a-zA-Z0-9_-]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)

if [ ! -z "$TELEGRAM1" ]; then
    echo "🔑 TELEGRAM_BOT_TOKEN (@DUDIRUDIBOT): ${TELEGRAM1:0:8}...${TELEGRAM1: -8}"
fi

if [ ! -z "$TELEGRAM2" ]; then
    echo "🔑 TELEGRAM_BOT_TOKEN_2 (@RUDICLUDIBOT): ${TELEGRAM2:0:8}...${TELEGRAM2: -8}"
fi

# API Keys
echo
echo "📋 WEITERE GEFUNDENE KEYS:"
echo

# Anthropic
ANTHROPIC=$(grep -o 'sk-ant-api03-[a-zA-Z0-9_-]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$ANTHROPIC" ]; then
    echo "🤖 ANTHROPIC_API_KEY: ${ANTHROPIC:0:10}...${ANTHROPIC: -10}"
fi

# OpenAI
OPENAI=$(grep -o 'sk-proj-[a-zA-Z0-9_-]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$OPENAI" ]; then
    echo "🤖 OPENAI_API_KEY: ${OPENAI:0:10}...${OPENAI: -10}"
fi

# GitHub
GITHUB=$(grep -o 'ghp_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$GITHUB" ]; then
    echo "🐙 GITHUB_TOKEN: ${GITHUB:0:8}...${GITHUB: -8}"
fi

# Printify
PRINTIFY=$(grep -o 'prtapi_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$PRINTIFY" ]; then
    echo "🖨️  PRINTIFY_ACCESS_TOKEN: ${PRINTIFY:0:8}...${PRINTIFY: -8}"
fi

# Stripe
STRIPE=$(grep -o 'sk_live_[a-zA-Z0-9]*' /Users/rudolfsarkany/CascadeProjects/rudibot/.env.new | head -1)
if [ ! -z "$STRIPE" ]; then
    echo "💳 STRIPE_API_KEY: ${STRIPE:0:8}...${STRIPE: -8}"
fi

echo
echo "═══════════════════════════════════════════"
echo "✅ Extraktion abgeschlossen"
echo "═══════════════════════════════════════════"
