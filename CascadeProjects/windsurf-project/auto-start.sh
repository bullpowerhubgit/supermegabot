#!/bin/bash

PROJECT_DIR="/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
ECOSYSTEM="/Users/rudolfsarkany/supermegabot-windsurf-agents/ecosystem.config.js"
PIDFILE_WD="/tmp/supermegabot-watchdog.pid"
PIDFILE_DS="/tmp/supermegabot-deepscan.pid"

sleep 5

cd "$PROJECT_DIR"

# Start Watchdog
if [ ! -f "$PIDFILE_WD" ] || ! ps -p "$(cat $PIDFILE_WD)" > /dev/null 2>&1; then
    nohup /opt/homebrew/bin/node "$PROJECT_DIR/watchdog.js" > /dev/null 2>&1 &
    echo $! > "$PIDFILE_WD"
fi

# Start DeepScan
if [ ! -f "$PIDFILE_DS" ] || ! ps -p "$(cat $PIDFILE_DS)" > /dev/null 2>&1; then
    nohup /opt/homebrew/bin/node "$PROJECT_DIR/deep-scan-scheduler.js" > /dev/null 2>&1 &
    echo $! > "$PIDFILE_DS"
fi

# Start PM2 Ecosystem
if which pm2 > /dev/null 2>&1; then
    pm2 start "$ECOSYSTEM" > /tmp/pm2-autostart.log 2>&1
fi
