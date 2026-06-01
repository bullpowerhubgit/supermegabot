#!/bin/bash

# SuperMegaBot - Alle Services stoppen
# Erstellt am: $(date)

echo "🛑 SuperMegaBot - Alle Services stoppen..."
echo "======================================"

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function zum Stoppen eines Service
stop_service() {
    local service_name=$1
    local pid_file="$service_name.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        echo -e "${BLUE}Stoppe ${service_name} (PID: $pid)${NC}"
        
        if kill -0 $pid 2>/dev/null; then
            kill $pid
            sleep 2
            
            # Wenn noch läuft, hart beenden
            if kill -0 $pid 2>/dev/null; then
                echo -e "${YELLOW}⏳ Hartes Beenden von ${service_name}...${NC}"
                kill -9 $pid
                sleep 1
            fi
            
            echo -e "${GREEN}✅ ${service_name} gestoppt${NC}"
        else
            echo -e "${YELLOW}⚠️ ${service_name} läuft nicht mehr${NC}"
        fi
        
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️ Keine PID-Datei für ${service_name} gefunden${NC}"
        
        # Versuche über ps zu finden und zu beenden
        local pids=$(pgrep -f "$service_name" 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${BLUE}Gefundene PIDs für ${service_name}: $pids${NC}"
            echo "$pids" | xargs kill
            sleep 1
            echo "$pids" | xargs kill -9 2>/dev/null
            echo -e "${GREEN}✅ ${service_name} über ps beendet${NC}"
        fi
    fi
}

# Services stoppen
stop_service "Mega-Dashboard"
stop_service "Telegram-Bot"
stop_service "Haupt-App"
stop_service "Desktop-Monitor"
stop_service "Watchdog"

# Zusätzliche Prozesse suchen und beenden
echo -e "${BLUE}🔍 Zusätzliche Prozesse suchen...${NC}"

# Python Prozesse
python_pids=$(pgrep -f "mega-server.py\|professional-desktop-monitor.py\|watchdog.js" 2>/dev/null)
if [ -n "$python_pids" ]; then
    echo -e "${YELLOW}⏳ Zusätzliche Python Prozesse beenden: $python_pids${NC}"
    echo "$python_pids" | xargs kill
    sleep 1
    echo "$python_pids" | xargs kill -9 2>/dev/null
fi

# Node.js Prozesse
node_pids=$(pgrep -f "telegram-bots\|server.js\|index.js" 2>/dev/null)
if [ -n "$node_pids" ]; then
    echo -e "${YELLOW}⏳ Zusätzliche Node.js Prozesse beenden: $node_pids${NC}"
    echo "$node_pids" | xargs kill
    sleep 1
    echo "$node_pids" | xargs kill -9 2>/dev/null
fi

# Ports prüfen und beenden
echo -e "${BLUE}🔍 Ports prüfen...${NC}"
ports=(8890 8003 8889 8888 8887)

for port in "${ports[@]}"; do
    port_pid=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$port_pid" ]; then
        echo -e "${YELLOW}⏳ Prozess auf Port $port beenden (PID: $port_pid)${NC}"
        kill $port_pid 2>/dev/null
        sleep 1
        kill -9 $port_pid 2>/dev/null
    fi
done

echo ""
echo -e "${GREEN}🎉 Alle SuperMegaBot Services gestoppt!${NC}"
echo "======================================"

# Log-Dateien anzeigen (optional)
echo ""
echo -e "${BLUE}📝 Log-Dateien:${NC}"
for log_file in *.log; do
    if [ -f "$log_file" ]; then
        echo "   - $log_file ($(wc -l < "$log_file") Zeilen)"
    fi
done
