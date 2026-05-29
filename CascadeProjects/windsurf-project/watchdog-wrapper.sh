#!/bin/bash

# Watchdog Wrapper - Ensures watchdog restarts on crash
# This script runs the watchdog and restarts it if it exits unexpectedly

PROJECT_DIR="/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
WATCHDOG_JS="$PROJECT_DIR/watchdog-v2.js"
PIDFILE="/tmp/supermegabot-watchdog.pid"
LOGFILE="/tmp/supermegabot-watchdog-wrapper.log"
MAX_RESTARTS=10
RESTART_COUNT=0
RESTART_WINDOW=300  # 5 minutes
FIRST_RESTART_TIME=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOGFILE"
}

# Function to check if Node.js is available
check_node() {
    if ! command -v /opt/homebrew/bin/node &> /dev/null; then
        log "ERROR: Node.js not found at /opt/homebrew/bin/node"
        return 1
    fi
    return 0
}

# Function to run watchdog with restart logic
run_watchdog() {
    log "Starting watchdog: $WATCHDOG_JS"
    
    while true; do
        # Check restart limits
        if [ $RESTART_COUNT -eq 0 ]; then
            FIRST_RESTART_TIME=$(date +%s)
        fi
        
        CURRENT_TIME=$(date +%s)
        TIME_DIFF=$((CURRENT_TIME - FIRST_RESTART_TIME))
        
        # Reset counter if window passed
        if [ $TIME_DIFF -gt $RESTART_WINDOW ]; then
            RESTART_COUNT=0
            FIRST_RESTART_TIME=$CURRENT_TIME
        fi
        
        # Check max restarts
        if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
            log "CRITICAL: Max restarts ($MAX_RESTARTS) reached in ${RESTART_WINDOW}s. Waiting 60s..."
            sleep 60
            RESTART_COUNT=0
            FIRST_RESTART_TIME=$(date +%s)
            continue
        fi
        
        # Check if already running
        if [ -f "$PIDFILE" ]; then
            EXISTING_PID=$(cat "$PIDFILE" 2>/dev/null)
            if ps -p "$EXISTING_PID" > /dev/null 2>&1; then
                log "Watchdog already running (PID: $EXISTING_PID)"
                sleep 10
                continue
            fi
        fi
        
        # Start watchdog
        RESTART_COUNT=$((RESTART_COUNT + 1))
        log "Starting watchdog (attempt $RESTART_COUNT/$MAX_RESTARTS in ${TIME_DIFF}s)..."
        
        cd "$PROJECT_DIR"
        /opt/homebrew/bin/node "$WATCHDOG_JS"
        EXIT_CODE=$?
        
        log "Watchdog exited with code: $EXIT_CODE"
        
        # Clean up PID file
        rm -f "$PIDFILE"
        
        # If clean exit, don't restart
        if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ] || [ $EXIT_CODE -eq 143 ]; then
            log "Clean exit. Stopping wrapper."
            break
        fi
        
        # Wait before restart (exponential backoff)
        WAIT_TIME=$((2 ** (RESTART_COUNT - 1)))
        [ $WAIT_TIME -gt 30 ] && WAIT_TIME=30
        log "Restarting in ${WAIT_TIME}s..."
        sleep $WAIT_TIME
    done
}

# Signal handlers for clean shutdown
cleanup() {
    log "Wrapper shutting down..."
    if [ -f "$PIDFILE" ]; then
        WDOG_PID=$(cat "$PIDFILE" 2>/dev/null)
        if [ -n "$WDOG_PID" ]; then
            kill -TERM "$WDOG_PID" 2>/dev/null
            sleep 2
        fi
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Main
log "=== Watchdog Wrapper started ==="
check_node || exit 1
run_watchdog
