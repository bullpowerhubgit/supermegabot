#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Cloud Shell Setup für SuperMegaBot Automatisierungen
# ═══════════════════════════════════════════════════════════════

echo "🚀 SuperMegaBot Cloud Setup gestartet..."

# 1. Node.js & npm prüfen
if ! command -v node &> /dev/null; then
    echo "⚠️  Node.js nicht gefunden. Installiere..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

echo "✅ Node $(node -v) | npm $(npm -v)"

# 2. Projekt klonen (falls noch nicht vorhanden)
PROJECT_DIR="$HOME/supermegabot-cloud"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📥 Klone Projekt..."
    # Option A: Von GitHub
    # git clone https://github.com/bullpowerhubgit/supermegabot.git "$PROJECT_DIR"
    
    # Option B: Lokales Verzeichnis kopieren (wenn du das Repo schon lokal hast)
    echo "   Bitte kopiere das Projekt manuell nach $PROJECT_DIR"
    echo "   z.B.: gcloud cloud-shell scp localhost:~/supermegabot-windsurf-agents/CascadeProjects/windsurf-project cloudshell:~/supermegabot-cloud --recursive"
fi

cd "$PROJECT_DIR" || exit 1

# 3. Dependencies installieren
echo "📦 Installiere Dependencies..."
npm install

# 4. Cron-Job einrichten (läuft alle 6 Stunden)
echo "⏰ Richte Cron-Job ein..."
CRON_JOB="0 */6 * * * cd $PROJECT_DIR && /usr/bin/node cloud-automation.js >> $HOME/cloud-automation.log 2>&1"
(crontab -l 2>/dev/null | grep -v "cloud-automation" ; echo "$CRON_JOB") | crontab -

echo "✅ Setup abgeschlossen!"
echo ""
echo "🔧 Nächste Schritte:"
echo "   1. .env Datei erstellen: nano $PROJECT_DIR/.env"
echo "   2. SUPABASE_URL, SUPABASE_ANON_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID eintragen"
echo "   3. Testlauf: node cloud-automation.js"
echo "   4. Logs: tail -f $HOME/cloud-automation.log"
echo ""
echo "📋 Cron-Job Übersicht:"
crontab -l | grep cloud-automation
