#!/bin/bash
# Stabiler Wrapper für cratorhub
# local-projects/digifabrik ist ein lokaler Pfad (kein iCloud) — sicher für cd + dotenv
DIGIFABRIK="${DIGIFABRIK_DIR:-$HOME/local-projects/digifabrik}"

if [ ! -f "$DIGIFABRIK/server.ts" ]; then
  echo "❌ server.ts nicht gefunden: $DIGIFABRIK/server.ts"
  sleep 10
  exit 1
fi

# cd ins Projektverzeichnis damit dotenv .env findet und Imports funktionieren
cd "$DIGIFABRIK" || { echo "❌ cd fehlgeschlagen: $DIGIFABRIK"; sleep 10; exit 1; }

# PORT explizit setzen — PM2 env-Übergabe an Shell-Skripte nicht immer zuverlässig
export PORT="${PORT:-3002}"

exec /opt/homebrew/bin/tsx server.ts
