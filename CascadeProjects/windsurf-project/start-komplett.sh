#!/bin/zsh
# RudiBot START KOMPLETT
# Backup + Fix + Start alle Services

PROJECT_DIR="/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"

echo "🚀 RUDIBOT START KOMPLETT"
echo "=========================="
echo ""

# 1. Install missing dependencies
echo "📦 Installiere fehlende Abhängigkeiten..."
pip3 install aiohttp aiohttp-cors websockets 2>/dev/null || echo "⚠️ pip3 install fehlgeschlagen"
npm install node-telegram-bot-api 2>/dev/null || echo "⚠️ npm install fehlgeschlagen"
echo "✅ Abhängigkeiten installiert"
echo ""

# 2. Stop stuck services
echo "⏹️ Stoppe stuck Services..."
pm2 stop mega-orchestrator 2>/dev/null
pm2 stop supermegabot 2>/dev/null
pm2 stop telegram-bot 2>/dev/null
pm2 stop rudiclone-agents 2>/dev/null
pm2 stop professional-desktop-monitor 2>/dev/null
pm2 stop cratorhub 2>/dev/null
pm2 stop windsurf-shopify 2>/dev/null
sleep 3
echo "✅ Stuck Services gestoppt"
echo ""

# 3. Delete stuck services
echo "🗑️ Lösche stuck Services..."
pm2 delete mega-orchestrator 2>/dev/null
pm2 delete supermegabot 2>/dev/null
pm2 delete telegram-bot 2>/dev/null
pm2 delete rudiclone-agents 2>/dev/null
pm2 delete professional-desktop-monitor 2>/dev/null
pm2 delete cratorhub 2>/dev/null
pm2 delete windsurf-shopify 2>/dev/null
sleep 2
echo "✅ Stuck Services gelöscht"
echo ""

# 4. Start Mega Dashboard
echo "🎨 Starte Mega Dashboard..."
cd "$PROJECT_DIR"
python3 mega-server.py > /tmp/mega-dashboard.log 2>&1 &
sleep 3
echo "✅ Mega Dashboard gestartet"
echo ""

# 5. Start Watchdog
echo "🐕 Starte Watchdog..."
node watchdog.js > /tmp/watchdog.log 2>&1 &
sleep 2
echo "✅ Watchdog gestartet"
echo ""

# 6. Start Agenten-Hub
echo "🤖 Starte Agenten-Hub mit externen AI Agenten..."
pkill -f agenten-hub.js 2>/dev/null
sleep 2
node agenten-hub.js > /tmp/agenten-hub.log 2>&1 &
sleep 4
echo "✅ Agenten-Hub gestartet"
echo ""

# 7. Restart PM2 services
echo "🔄 Restarte PM2 Services..."
pm2 restart all 2>/dev/null
sleep 5
echo "✅ PM2 Services neu gestartet"
echo ""

# 8. Open Safari with all dashboards
echo "🌐 Öffne Safari mit allen Dashboards..."
open http://localhost:8890  # Mega Dashboard
sleep 1
open http://localhost:9999  # Agenten-Hub
sleep 1
open http://localhost:11434  # Ollama
echo "✅ Safari geöffnet"
echo ""

# 9. Show status
echo "══════════════════════════════════"
echo "📊 FINAL STATUS"
echo "══════════════════════════════════"
echo ""
echo "🎨 Mega Dashboard: http://localhost:8890"
echo "🤖 Agenten-Hub: http://localhost:9999"
echo "🧠 Ollama: http://localhost:11434"
echo ""
echo "PM2 Status:"
pm2 list | grep -E "online|stopping|error" | head -10
echo ""
echo "RAM Status:"
vm_stat | grep "Pages free"
echo ""
echo "✅ ALLES GESTARTET!"
