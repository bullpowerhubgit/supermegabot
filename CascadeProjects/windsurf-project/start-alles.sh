#!/bin/zsh
# RudiBot ALLES STARTEN
# Startet alle Services und öffnet Safari mit allen Tools

echo "🚀 STARTE RUDIBOT SYSTEM..."

# 1. Ollama prüfen/starten
if ! pgrep -f "ollama" > /dev/null; then
    echo "🧠 Starte Ollama..."
    open -a Ollama
    sleep 3
else
    echo "🧠 Ollama läuft bereits"
fi

# 2. Alte Server stoppen
pkill -f "mega-server.py" 2>/dev/null
pkill -f "http.server" 2>/dev/null
sleep 1

# 3. Mega Dashboard starten
echo "📊 Starte Mega Dashboard (Port 8890)..."
cd /Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project
nohup python3 mega-server.py > /tmp/mega.log 2>&1 &
sleep 3

# 4. Watchdog prüfen
if ! pgrep -f "watchdog.js" > /dev/null; then
    echo "🐕 Starte Watchdog..."
    nohup node watchdog.js > /tmp/watchdog.log 2>&1 &
else
    echo "🐕 Watchdog läuft bereits"
fi

# 5. Warte bis Dashboard bereit
echo "⏳ Warte auf Services..."
sleep 2

# 6. Safari mit allen Tools öffnen
echo "🌐 Öffne Safari mit allen Tools..."

# Ollama
open -a Safari http://localhost:11434
sleep 1

# Dashboard
open -a Safari http://localhost:8890
sleep 1

# Andere Ports (falls verfügbar)
# n8n
open -a Safari http://localhost:5678
sleep 1

# Netdata
open -a Safari http://localhost:19999
sleep 1

# Altes Dashboard
open -a Safari http://localhost:3456

echo ""
echo "═══════════════════════════════════════"
echo "✅ ALLES GESTARTET!"
echo "═══════════════════════════════════════"
echo "Safari öffnet jetzt alle Tabs:"
echo "  🧠 Ollama:      http://localhost:11434"
echo "  📊 Dashboard:   http://localhost:8890"
echo "  ⚡ n8n:          http://localhost:5678"
echo "  📈 Netdata:      http://localhost:19999"
echo "═══════════════════════════════════════"
echo ""
echo "Du kannst jetzt alle Terminals schließen!"
