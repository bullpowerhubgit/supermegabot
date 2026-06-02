#!/bin/bash
set -e

echo "=== Password Sync Suite Setup ==="

# Web-App
echo "[1/2] Installiere Web-App Dependencies..."
cd "$(dirname "$0")/web-app"
npm install

echo ""
echo "[2/2] Prüfe .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env wurde aus .env.example kopiert. Bitte anpassen!"
else
  echo ".env existiert bereits."
fi

echo ""
echo "=== Fertig ==="
echo "Starte die Web-App mit:"
echo "  cd web-app && npm start"
echo ""
echo "Lade dann die Extension in chrome://extensions (Entwicklermodus -> Entpackte Erweiterung laden)"
echo "Wähle den Ordner: browser-extension/"
