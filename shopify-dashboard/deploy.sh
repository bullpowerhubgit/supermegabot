#!/bin/bash

echo "🚀 RudiBot Dashboard Deployment"
echo "================================"

# Build erstellen
echo "📦 Erstelle Production Build..."
npm run build

# Prüfen ob Build erfolgreich
if [ ! -d "build" ]; then
    echo "❌ Build fehlgeschlagen!"
    exit 1
fi

echo "✅ Build erfolgreich!"

# Netlify CLI prüfen
if ! command -v netlify &> /dev/null; then
    echo "📥 Installiere Netlify CLI..."
    npm install -g netlify-cli
fi

# Deploy
echo "🚀 Deploye zu Netlify..."
netlify deploy --prod --dir=build

echo "✅ Deployment abgeschlossen!"
echo ""
echo "💡 Nächste Schritte:"
echo "   - Domain in Netlify Dashboard verbinden"
echo "   - DNS-Einträge anpassen"
echo "   - HTTPS aktivieren"
