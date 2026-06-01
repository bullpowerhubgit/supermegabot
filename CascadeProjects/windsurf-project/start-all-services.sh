#!/bin/bash

# SuperMegaBot - Alle Services parallel starten
# Erstellt am: $(date)

echo "🚀 SuperMegaBot - Alle Services starten..."
echo "======================================"

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function zum Starten eines Service
start_service() {
    local service_name=$1
    local command=$2
    local port=$3
    local working_dir=$4
    
    echo -e "${BLUE}Starte ${service_name} (Port: ${port})${NC}"
    
    cd "$working_dir"
    nohup $command > "${service_name}.log" 2>&1 &
    local pid=$!
    
    echo -e "${GREEN}✅ ${service_name} gestartet mit PID: ${pid}${NC}"
    echo "${pid}" > "${service_name}.pid"
    
    # Warte kurz und prüfe ob Prozess läuft
    sleep 2
    if kill -0 $pid 2>/dev/null; then
        echo -e "${GREEN}✅ ${service_name} läuft erfolgreich${NC}"
    else
        echo -e "${RED}❌ ${service_name} Start fehlgeschlagen${NC}"
        return 1
    fi
    
    return 0
}

# Function für Health Check
health_check() {
    local service_name=$1
    local url=$2
    local max_attempts=$3
    
    echo -e "${YELLOW}🔍 Health Check für ${service_name}...${NC}"
    
    for attempt in $(seq 1 $max_attempts); do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ ${service_name} Health Check bestanden${NC}"
            return 0
        fi
        echo -e "${YELLOW}⏳ Versuch $attempt/$max_attempts...${NC}"
        sleep 2
    done
    
    echo -e "${RED}❌ ${service_name} Health Check fehlgeschlagen${NC}"
    return 1
}

# Function für API Validierung
check_api_keys() {
    local service_name=$1
    shift
    local required_keys=("$@")
    
    echo -e "${YELLOW}🔑 API Keys prüfen für ${service_name}...${NC}"
    
    local missing_keys=()
    for key in "${required_keys[@]}"; do
        if [ -z "${!key}" ]; then
            missing_keys+=("$key")
        fi
    done
    
    if [ ${#missing_keys[@]} -eq 0 ]; then
        echo -e "${GREEN}✅ Alle API Keys für ${service_name} vorhanden${NC}"
        return 0
    else
        echo -e "${RED}❌ Fehlende API Keys für ${service_name}: ${missing_keys[*]}${NC}"
        return 1
    fi
}

# Environment Variablen laden
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo -e "${GREEN}✅ .env Datei geladen${NC}"
else
    echo -e "${YELLOW}⚠️ Keine .env Datei gefunden${NC}"
fi

if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
    echo -e "${GREEN}✅ .env.local Datei geladen${NC}"
fi

# Function zum Stoppen aller Services
cleanup() {
    echo -e "${RED}🛑 Stoppe alle Services...${NC}"
    
    # Stoppe Services mit PID-Dateien
    for pid_file in *.pid; do
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            local service_name=$(basename "$pid_file" .pid)
            
            if kill -0 $pid 2>/dev/null; then
                echo "Stoppe $service_name (PID: $pid)"
                kill $pid
                sleep 1
                if kill -0 $pid 2>/dev/null; then
                    kill -9 $pid
                fi
                rm -f "$pid_file"
            fi
        fi
    done
    
    exit 0
}

# Signal Handler für Strg+C
trap cleanup SIGINT SIGTERM

echo ""
echo -e "${BLUE}🔑 API Validierung vor Service-Start...${NC}"
echo "======================================"

# API Keys für jeden Service prüfen
check_api_keys "Telegram-Bot" "TELEGRAM_BOT_TOKEN" "TELEGRAM_CHAT_ID"
check_api_keys "Mega-Dashboard" "ANTHROPIC_API_KEY" "OPENAI_API_KEY"
check_api_keys "Shopify-Integration" "SHOPIFY_ACCESS_TOKEN" "SHOPIFY_STORE_URL"
check_api_keys "GitHub-Integration" "GITHUB_TOKEN" "GITHUB_CLIENT_ID"
check_api_keys "Supabase" "SUPABASE_URL" "SUPABASE_ANON_KEY"

echo ""
echo -e "${BLUE}🚀 Starte Services...${NC}"
echo "======================================"

# 1. Mega Dashboard (Port 8890) - sollte bereits laufen
echo -e "${BLUE}📊 Mega Dashboard Status prüfen...${NC}"
if curl -s http://localhost:8890/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Mega Dashboard läuft bereits auf Port 8890${NC}"
else
    echo -e "${YELLOW}⚠️ Mega Dashboard nicht erreichbar, starte es...${NC}"
    start_service "Mega-Dashboard" "python3 mega-server.py" "8890" "/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
fi

# 2. Telegram Bot Server (Port 8003)
start_service "Telegram-Bot" "npm run bot:telegram" "8003" "/Users/rudolfsarkany/windsurf-telegram-bot"

# 3. Haupt-App Server (Port 8889)
start_service "Haupt-App" "npm start" "8889" "/Users/rudolfsarkany/windsurf-telegram-bot"

# 4. Professional Desktop Monitor
start_service "Desktop-Monitor" "python3 professional-desktop-monitor.py" "8888" "/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"

# 5. Watchdog Services
start_service "Watchdog" "python3 watchdog.js" "8887" "/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"

echo ""
echo -e "${BLUE}🔍 Health Checks für alle Services...${NC}"

# Health Checks durchführen
health_check "Mega-Dashboard" "http://localhost:8890/health" 5
health_check "Telegram-Bot" "http://localhost:8003/health" 5
health_check "Haupt-App" "http://localhost:8889/health" 5
health_check "Desktop-Monitor" "http://localhost:8888/health" 3
health_check "Watchdog" "http://localhost:8887/health" 3

echo ""
echo -e "${GREEN}🎉 SuperMegaBot Services gestartet!${NC}"
echo "======================================"
echo "📊 Mega Dashboard:  http://localhost:8890"
echo "🤖 Telegram Bot:   http://localhost:8003"
echo "🖥️ Haupt App:      http://localhost:8889"
echo "📱 Desktop Monitor: http://localhost:8888"
echo "🐕 Watchdog:       http://localhost:8887"
echo ""
echo "📝 Logs:"
echo "   - Mega Dashboard: mega-dashboard.log"
echo "   - Telegram Bot:   telegram-bot.log"
echo "   - Haupt App:      haupt-app.log"
echo "   - Desktop Monitor: desktop-monitor.log"
echo "   - Watchdog:       watchdog.log"
echo ""
echo "🛑 Stoppen mit: ./stop-all-services.sh oder Strg+C"
echo ""

# Warte auf Beenden
echo -e "${BLUE}⏳ Services laufen. Drücke Strg+C zum stoppen...${NC}"
while true; do
    sleep 10
    # Prüfe ob alle Services noch laufen
    running_services=0
    for pid_file in *.pid; do
        if [ -f "$pid_file" ]; then
            local pid=$(cat "$pid_file")
            if kill -0 $pid 2>/dev/null; then
                ((running_services++))
            fi
        fi
    done
    
    if [ $running_services -eq 0 ]; then
        echo -e "${RED}❌ Alle Services wurden beendet${NC}"
        break
    fi
done
