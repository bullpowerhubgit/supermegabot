#!/bin/zsh
# Quick Backup Script

PROJECT_DIR="/Users/rudolfsarkany/supermegabot-windsurf-agents/CascadeProjects/windsurf-project"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"

echo "📦 QUICK BACKUP STARTET..."
echo "Zeit: $TIMESTAMP"
echo ""

mkdir -p "$BACKUP_PATH"

# Backup critical files
cp "$PROJECT_DIR/watchdog.js" "$BACKUP_PATH/" 2>/dev/null && echo "✅ watchdog.js"
cp "$PROJECT_DIR/mega-server.py" "$BACKUP_PATH/" 2>/dev/null && echo "✅ mega-server.py"
cp "$PROJECT_DIR/mega-dashboard.html" "$BACKUP_PATH/" 2>/dev/null && echo "✅ mega-dashboard.html"
cp "$PROJECT_DIR/agenten-hub.js" "$BACKUP_PATH/" 2>/dev/null && echo "✅ agenten-hub.js"
cp "$PROJECT_DIR/externe-agenten.js" "$BACKUP_PATH/" 2>/dev/null && echo "✅ externe-agenten.js"
cp "$PROJECT_DIR/package.json" "$BACKUP_PATH/" 2>/dev/null && echo "✅ package.json"
cp "$PROJECT_DIR/docker-compose.yml" "$BACKUP_PATH/" 2>/dev/null && echo "✅ docker-compose.yml"
cp "$PROJECT_DIR/start-alles.sh" "$BACKUP_PATH/" 2>/dev/null && echo "✅ start-alles.sh"

# Backup services
if [ -d "$PROJECT_DIR/services" ]; then
  cp -r "$PROJECT_DIR/services" "$BACKUP_PATH/" 2>/dev/null && echo "✅ services/"
fi

# Backup templates
if [ -d "$PROJECT_DIR/templates" ]; then
  cp -r "$PROJECT_DIR/templates" "$BACKUP_PATH/" 2>/dev/null && echo "✅ templates/"
fi

# Backup to iCloud if available
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
if [ -d "$ICLOUD" ]; then
  mkdir -p "$ICLOUD/RudiBot-Backups"
  cp -r "$BACKUP_PATH" "$ICLOUD/RudiBot-Backups/" 2>/dev/null && echo "☁️  iCloud: ✅"
fi

# Backup to Dropbox if available
if [ -d "$HOME/Dropbox" ]; then
  mkdir -p "$HOME/Dropbox/RudiBot-Backups"
  cp -r "$BACKUP_PATH" "$HOME/Dropbox/RudiBot-Backups/" 2>/dev/null && echo "☁️  Dropbox: ✅"
fi

echo ""
echo "✅ BACKUP ABGESCHLOSSEN: $BACKUP_PATH"
echo "📊 Größe: $(du -sh "$BACKUP_PATH" | cut -f1)"
