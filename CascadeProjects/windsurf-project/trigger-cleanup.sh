#!/bin/bash

# 🧹 One-Click Cleanup Trigger
# This script triggers the smart cleanup in the watchdog

echo "🧹 Triggering Smart Cleanup..."

# Find watchdog process and send SIGUSR1 signal
WATCHDOG_PID=$(pgrep -f "watchdog.js")

if [ -n "$WATCHDOG_PID" ]; then
    echo "Found watchdog process: $WATCHDOG_PID"
    kill -SIGUSR1 $WATCHDOG_PID
    echo "✅ Smart cleanup triggered successfully"
else
    echo "⚠️ Watchdog not running, starting standalone cleanup..."
    node smart-cleanup.js
fi
