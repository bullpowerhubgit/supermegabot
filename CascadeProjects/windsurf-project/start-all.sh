#!/bin/bash

# RudiBot Master Launcher
# Starts all macOS tools: Dashboard, Watchdog, DeepScan, Monitoring

PROJECT_DIR="/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
TELEGRAM_DIR="/Users/rudolfsarkany/windsurf-telegram-bot"
DASHBOARD_PORT=8888
PIDFILE_DIR="/tmp"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] $1${NC}"
}

# Check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Kill process by pattern
kill_pattern() {
    local pattern=$1
    local pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null
        sleep 1
    fi
}

# Start a service
start_service() {
    local name=$1
    local command=$2
    local log_file=$3
    
    log "Starting $name..."
    
    # Kill existing
    kill_pattern "$name"
    
    # Start in background
    cd "$PROJECT_DIR"
    nohup bash -c "$command" > "$log_file" 2>&1 &
    local pid=$!
    
    sleep 2
    
    if ps -p $pid > /dev/null 2>&1; then
        success "$name started (PID: $pid)"
        echo $pid > "$PIDFILE_DIR/rudibot-$name.pid"
        return 0
    else
        error "$name failed to start"
        return 1
    fi
}

# Stop all services
stop_all() {
    log "Stopping all RudiBot services..."
    
    kill_pattern "mega-dashboard-backend"
    kill_pattern "watchdog-v2"
    kill_pattern "deep-scan-scheduler"
    kill_pattern "main-bot-complete"
    kill_pattern "watchdog-wrapper"
    
    # Remove PID files
    rm -f $PIDFILE_DIR/rudibot-*.pid
    
    success "All services stopped"
}

# Status check
check_status() {
    log "Checking service status..."
    
    local services=("mega-dashboard-backend" "watchdog-v2" "main-bot-complete")
    local running=0
    local total=${#services[@]}
    
    for service in "${services[@]}"; do
        local pid_file="$PIDFILE_DIR/rudibot-$service.pid"
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if ps -p "$pid" > /dev/null 2>&1; then
                success "$service: Running (PID: $pid)"
                running=$((running + 1))
            else
                warn "$service: Stale PID file"
            fi
        else
            error "$service: Not running"
        fi
    done
    
    log "Status: $running/$total services running"
    
    # Check dashboard
    if check_port $DASHBOARD_PORT; then
        success "Dashboard: http://localhost:$DASHBOARD_PORT"
    else
        warn "Dashboard: Not responding"
    fi
}

# Main start function
start_all() {
    log "Starting RudiBot Mega System..."
    log "Project: $PROJECT_DIR"
    
    # Ensure directories
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p ~/RudiBot-Data/backups
    mkdir -p ~/RudiBot-Data/cloud-sync
    
    # 1. Start Watchdog (memory + process monitoring)
    start_service "watchdog" \
        "cd $PROJECT_DIR && /opt/homebrew/bin/node watchdog-v2.js" \
        "$PROJECT_DIR/logs/watchdog.log"
    
    # 2. Start Mega Dashboard
    start_service "dashboard" \
        "cd $PROJECT_DIR && /opt/homebrew/bin/node mega-dashboard-backend.js" \
        "$PROJECT_DIR/logs/dashboard.log"
    
    # 3. Start Telegram Bot (if exists)
    if [ -f "$TELEGRAM_DIR/main-bot-complete.js" ]; then
        start_service "telegram-bot" \
            "cd $TELEGRAM_DIR && /opt/homebrew/bin/node main-bot-complete.js" \
            "$TELEGRAM_DIR/logs/bot.log"
    fi
    
    # 4. Initial backup
    log "Creating initial backup..."
    cd "$PROJECT_DIR" && /opt/homebrew/bin/node cloud-backup-manager.js backup >/dev/null 2>&1 &
    
    sleep 3
    
    # Show summary
    echo ""
    success "================================"
    success "RudiBot Mega System Started!"
    success "================================"
    echo ""
    success "Dashboard: http://localhost:$DASHBOARD_PORT"
    success "Watchdog: Running (memory monitoring)"
    if [ -f "$TELEGRAM_DIR/main-bot-complete.js" ]; then
        success "Telegram Bot: Running"
    fi
    echo ""
    log "Commands:"
    log "  ./start-all.sh status  - Check status"
    log "  ./start-all.sh stop    - Stop all"
    log "  ./start-all.sh restart - Restart all"
    echo ""
}

# Auto-start via launchd
install_autostart() {
    log "Installing auto-start..."
    
    PLIST_FILE="$HOME/Library/LaunchAgents/com.rudibot.mega-system.plist"
    
    cat > "$PLIST_FILE" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rudibot.mega-system</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/start-all.sh</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>WorkingDirectory</key>
    <string>/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>/Users/rudolfsarkany</string>
    </dict>
</dict>
</plist>
EOF
    
    launchctl unload "$PLIST_FILE" 2>/dev/null
    launchctl load "$PLIST_FILE"
    
    success "Auto-start installed!"
    log "The system will start automatically on login."
}

# Menu
show_menu() {
    echo ""
    echo "================================"
    echo "  RudiBot Mega System Control"
    echo "================================"
    echo ""
    echo "1) Start all services"
    echo "2) Stop all services"
    echo "3) Restart all services"
    echo "4) Check status"
    echo "5) Install auto-start"
    echo "6) Create backup"
    echo "7) View logs"
    echo "8) Exit"
    echo ""
    echo "Or use: ./start-all.sh [start|stop|restart|status|install|backup]"
    echo ""
}

# Handle arguments
COMMAND=${1:-menu}

case $COMMAND in
    start|start_all)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    status)
        check_status
        ;;
    install|autostart)
        install_autostart
        ;;
    backup)
        log "Creating backup..."
        cd "$PROJECT_DIR" && /opt/homebrew/bin/node cloud-backup-manager.js backup
        ;;
    logs|log)
        if [ -f "$PROJECT_DIR/logs/dashboard.log" ]; then
            tail -f "$PROJECT_DIR/logs/dashboard.log"
        else
            error "No logs found"
        fi
        ;;
    menu|*)
        show_menu
        read -p "Select option [1-8]: " choice
        case $choice in
            1) start_all ;;
            2) stop_all ;;
            3) stop_all; sleep 2; start_all ;;
            4) check_status ;;
            5) install_autostart ;;
            6) cd "$PROJECT_DIR" && /opt/homebrew/bin/node cloud-backup-manager.js backup ;;
            7) tail -f "$PROJECT_DIR/logs/"*.log ;;
            8) exit 0 ;;
            *) error "Invalid option" ;;
        esac
        ;;
esac
