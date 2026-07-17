#!/bin/bash
# SuperMegaBot — Lokaler Single-Instance Start
# Verhindert zombie-Prozesse durch PID-File-Management

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$DIR/data/server.pid"
LOG="$DIR/data/local_server.log"

mkdir -p "$DIR/data"

echo "[$(date '+%H:%M:%S')] Starte SuperMegaBot lokal..." | tee -a "$LOG"

# 1. Alle alten dashboard/server.py Prozesse beenden
OLD_PIDS=$(pgrep -f "dashboard/server.py" 2>/dev/null || true)
if [ -n "$OLD_PIDS" ]; then
    echo "[$(date '+%H:%M:%S')] Alte Server-PIDs beenden: $OLD_PIDS" | tee -a "$LOG"
    echo "$OLD_PIDS" | xargs kill -TERM 2>/dev/null || true
    sleep 2
    # Force-kill falls noch nötig
    echo "$OLD_PIDS" | xargs kill -KILL 2>/dev/null || true
fi

# 2. Warte bis Port frei
for i in $(seq 1 10); do
    if ! lsof -i :8888 -sTCP:LISTEN >/dev/null 2>&1; then
        break
    fi
    echo "[$(date '+%H:%M:%S')] Warte auf Port 8888 ($i/10)..." | tee -a "$LOG"
    sleep 1
done

# 3. Neuen Server starten
cd "$DIR"
if [ -f ".env" ]; then
    set -a
    source <(grep -v '^#' .env | grep -v '^$' | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | grep -v '[(){}]') 2>/dev/null || true
    set +a
fi

echo "[$(date '+%H:%M:%S')] Starte Server auf Port 8888..." | tee -a "$LOG"
nohup python3 dashboard/server.py >> "$LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
echo "[$(date '+%H:%M:%S')] Server gestartet (PID: $NEW_PID)" | tee -a "$LOG"
echo "Dashboard: http://localhost:8888"
