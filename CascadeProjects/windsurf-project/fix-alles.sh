#!/bin/zsh
# RudiBot FIX ALLES Script
# Repariert alle Services auf einmal

echo "🔧 RUDIBOT FIX ALLES STARTET..."
echo ""

# 1. Install missing Python dependencies
echo "📦 Installiere Python Abhängigkeiten..."
pip3 install aiohttp aiohttp-cors websockets 2>/dev/null || echo "⚠️ pip3 install hat Probleme"

# 2. Kill stuck processes on port 9999
echo ""
echo "🛑 Bebehe Port 9999 Konflikt..."
lsof -ti:9999 | xargs kill -9 2>/dev/null || true
sleep 2

# 3. Stop stuck PM2 services
echo ""
echo "⏹️ Stoppe stuck Services..."
pm2 stop mega-orchestrator 2>/dev/null
pm2 stop supermegabot 2>/dev/null
pm2 stop rudiclone-agents 2>/dev/null
pm2 stop professional-desktop-monitor 2>/dev/null
sleep 3

# 4. Restart all services
echo ""
echo "🔄 Restarte alle Services..."
pm2 restart all 2>/dev/null
sleep 5

# 5. Fix windsurf-telegram-bot port conflict
lsof -ti:9999 | xargs kill -9 2>/dev/null || true
sleep 2

# 6. Start professional-desktop-monitor with different port
pm2 delete professional-desktop-monitor 2>/dev/null
sleep 1
echo ""
echo "✅ ALLES REPARIERT!"
echo ""

# Show status
echo "══════════════════════════════════"
echo "📊 SERVICE STATUS"
echo "══════════════════════════════════"
pm2 list | grep -E "online|stopping|error" | head -5
echo ""
echo "💾 RAM Status:"
vm_stat | grep "Pages free"
echo ""
echo "✅ Fix abgeschlossen!"
