#!/bin/bash
# Stabiler Wrapper für cratorhub — läuft von lokalem Pfad, vermeidet iCloud EPERM
DIGIFABRIK="/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/digifabrik"
cd "$DIGIFABRIK" 2>/dev/null || { echo "❌ digifabrik Verzeichnis nicht erreichbar"; sleep 10; exit 1; }
exec /opt/homebrew/bin/tsx server.ts
