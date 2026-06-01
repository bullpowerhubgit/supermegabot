#!/bin/bash

# Railway → Vercel Migration Deploy Script
# Dieses Script deployt die shopify-automation-api auf Vercel

set -e

echo "🚀 Railway → Vercel Migration Deploy Script"
echo "=========================================="
echo ""

# Prüfe ob Vercel CLI installiert ist
if ! command -v vercel &> /dev/null; then
    echo "📦 Installiere Vercel CLI..."
    npm install -g vercel
fi

# Prüfe ob .env.local existiert
if [ ! -f .env.local ]; then
    echo "⚠️  .env.local nicht gefunden!"
    echo "📝 Erstelle .env.local aus .env.example..."
    cp .env.example .env.local
    echo "⚠️  Bitte .env.local mit deinen echten API-Keys bearbeiten!"
    echo "   WICHTIG: ANTHROPIC_API_KEY muss gesetzt sein!"
    read -p "Drücke Enter nachdem du .env.local bearbeitet hast..."
fi

# Prüfe ob ANTHROPIC_API_KEY gesetzt ist
if ! grep -q "ANTHROPIC_API_KEY=sk-ant" .env.local; then
    echo "❌ ANTHROPIC_API_KEY ist nicht in .env.local gesetzt!"
    echo "   Bitte bearbeite .env.local und füge deinen echten Key ein."
    exit 1
fi

echo "✅ Vorbereitungen abgeschlossen"
echo ""

# Deploy auf Vercel
echo "🚀 Deploy auf Vercel..."
vercel --prod

echo ""
echo "✅ Deploy erfolgreich!"
echo ""
echo "📋 Nächste Schritte:"
echo "1. Teste die API: curl -X POST https://DEINE-URL.vercel.app/api/claude ..."
echo "2. Wenn die API funktioniert: Railway kündigen"
echo "   → railway.app/account/billing"
echo ""
echo "🎉 Fertig! Deine API läuft jetzt auf Vercel (kostenlos)"
