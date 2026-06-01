#!/bin/bash
# SuperMegaBot RAM Cleanup Script
# Beendet duplizierte Bots, idle Prozesse, leert Caches

echo "========================================"
echo " SuperMegaBot RAM Cleanup"
echo "========================================"
echo ""

# 1. Speicherstatus vor Cleanup
echo "[1/5] Speicherstatus vorher:"
vm_stat | grep -E "free|inactive|used by compressor" | sed 's/^/  /'
echo ""

# 2. Duplizierte Bots finden und beenden
echo "[2/5] Pruefe auf duplizierte Bots..."
DUP_BOTS=$(ps ax | grep -E 'eternal_immortal_bot|mega_orchestrator|deep-scan-scheduler|auto-backup-scheduler|professional-desktop-monitor|cloud-backup-system' | grep -v grep | grep -v $$)
if [ -n "$DUP_BOTS" ]; then
    echo "  Gefundene Bot-Prozesse:"
    echo "$DUP_BOTS" | while read line; do
        PID=$(echo "$line" | awk '{print $1}')
        CMD=$(echo "$line" | awk '{print $5}')
        echo "    PID $PID -> ${CMD:0:60}"
    done
    
    # Nach Script-Name gruppieren und Duplikate beenden
    echo "  Beende Duplikate (aelteste Instanz bleibt)..."
    for PATTERN in eternal_immortal_bot mega_orchestrator deep-scan-scheduler auto-backup-scheduler professional-desktop-monitor cloud-backup-system; do
        PIDS=$(ps ax | grep "$PATTERN" | grep -v grep | grep -v $$ | awk '{print $1}')
        COUNT=$(echo "$PIDS" | grep -c "[0-9]")
        if [ "$COUNT" -gt 1 ]; then
            # Alle bis auf den ersten beenden
            echo "$PIDS" | tail -n +2 | while read PID; do
                if [ -n "$PID" ]; then
                    kill -15 "$PID" 2>/dev/null && echo "    Beendet PID $PID ($PATTERN)" || echo "    Konnte PID $PID nicht beenden"
                fi
            done
        fi
    done
else
    echo "  Keine duplizierten Bots gefunden."
fi
echo ""

# 3. Idle Node-Prozesse (>2% RAM, <0.1% CPU) optional beenden
echo "[3/5] Pruefe auf idle Node-Prozesse..."
IDLE_PROCS=$(ps -ax -o pid,pcpu,pmem,comm | grep node | awk '$2 < 0.1 && $3 > 2.0 {print $1}')
IDLE_COUNT=$(echo "$IDLE_PROCS" | grep -c "[0-9]" || echo 0)
if [ "$IDLE_COUNT" -gt 0 ]; then
    echo "  Gefunden: $IDLE_COUNT idle Node-Prozesse"
    echo "$IDLE_PROCS" | while read PID; do
        if [ -n "$PID" ]; then
            echo "    Beende idle Node PID $PID"
            kill -15 "$PID" 2>/dev/null
        fi
    done
else
    echo "  Keine idle Node-Prozesse gefunden."
fi
echo ""

# 4. System-Caches leeren (macOS)
echo "[4/5] Leere System-Caches..."
if command -v purge &> /dev/null; then
    purge 2>/dev/null && echo "  System-Cache geleert (purge)" || echo "  purge erfordert sudo (uebersprungen)"
fi
echo ""

# 5. Speicherstatus nach Cleanup
echo "[5/5] Speicherstatus nachher:"
vm_stat | grep -E "free|inactive|used by compressor" | sed 's/^/  /'
echo ""

echo "========================================"
echo " RAM Cleanup abgeschlossen"
echo "========================================"
