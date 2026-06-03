#!/bin/bash
# ============================================================
# setup.sh — AutoPilot Business Bot · Vollautomatisches Setup
# Rudolf Sarkany · Production Ready
# Ausführen: chmod +x setup.sh && ./setup.sh
# ============================================================
set -e

# ── Farben ───────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; PRP='\033[0;35m'; CYN='\033[0;36m'
WHT='\033[1;37m'; NC='\033[0m' # No Color

# ── Helpers ──────────────────────────────────────────────────
ok()   { echo -e "  ${GRN}✅ $1${NC}"; }
fail() { echo -e "  ${RED}❌ $1${NC}"; }
warn() { echo -e "  ${YLW}⚠️  $1${NC}"; }
info() { echo -e "  ${CYN}ℹ️  $1${NC}"; }
step() { echo -e "\n${PRP}━━━ $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
divider() { echo -e "${BLU}────────────────────────────────────────────────${NC}"; }

# ── Banner ───────────────────────────────────────────────────
clear
echo -e "${PRP}"
cat << 'EOF'
  ██████╗ ██╗   ██╗██████╗ ██╗██████╗  ██████╗ ████████╗
  ██╔══██╗██║   ██║██╔══██╗██║██╔══██╗██╔═══██╗╚══██╔══╝
  ██████╔╝██║   ██║██║  ██║██║██████╔╝██║   ██║   ██║   
  ██╔══██╗██║   ██║██║  ██║██║██╔══██╗██║   ██║   ██║   
  ██║  ██║╚██████╔╝██████╔╝██║██████╔╝╚██████╔╝   ██║   
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝╚═════╝  ╚═════╝   ╚═╝   
  AutoPilot Business Bot — Production Setup v1.0
  Rudolf Sarkany · 2026
EOF
echo -e "${NC}"
divider

# ── 1. SYSTEM CHECK ──────────────────────────────────────────
step "1/8 System Check"

# macOS check
if [[ "$OSTYPE" == "darwin"* ]]; then
  ok "macOS erkannt"
else
  warn "Nicht macOS — einige Befehle könnten abweichen"
fi

# Node.js
if command -v node &> /dev/null; then
  NODE_VER=$(node --version | sed 's/v//')
  MAJOR=$(echo $NODE_VER | cut -d. -f1)
  if [ "$MAJOR" -ge 18 ]; then
    ok "Node.js v$NODE_VER (≥18 ✅)"
  else
    fail "Node.js v$NODE_VER zu alt — mindestens v18 benötigt"
    echo -e "  ${YLW}→ brew install node@20${NC}"
    exit 1
  fi
else
  fail "Node.js nicht gefunden"
  echo -e "  ${YLW}→ brew install node@20${NC}"
  exit 1
fi

# npm
if command -v npm &> /dev/null; then
  ok "npm $(npm --version)"
else
  fail "npm nicht gefunden"; exit 1
fi

# PM2
if command -v pm2 &> /dev/null; then
  ok "PM2 $(pm2 --version) vorhanden"
else
  warn "PM2 nicht installiert → installiere..."
  npm install -g pm2
  ok "PM2 installiert"
fi

# ── 2. .ENV SETUP ────────────────────────────────────────────
step "2/8 Environment Setup"

if [ -f ".env" ]; then
  ok ".env Datei gefunden"
else
  if [ -f ".env.example" ]; then
    cp .env.example .env
    ok ".env aus .env.example erstellt"
    warn "BITTE .env bearbeiten: nano .env"
  else
    warn ".env.example nicht gefunden — erstelle Vorlage..."
    cat > .env << 'ENVEOF'
# AutoPilot Business Bot — .env
# NIEMALS in Git committen!

TELEGRAM_BOT_TOKEN=DEIN_TOKEN_HIER
TELEGRAM_ADMIN_ID=DEINE_TELEGRAM_ID
ANTHROPIC_API_KEY=sk-ant-api03-DEIN_KEY
OPENAI_API_KEY=sk-proj-DEIN_KEY
PERPLEXITY_API_KEY=pplx-DEIN_KEY
SHOPIFY_STORE_URL=suitenew.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_NEUER_TOKEN
SHOPIFY_API_VERSION=2025-01
SHOPIFY_STORE2_URL=soolar.myshopify.com
SHOPIFY_STORE2_TOKEN=shpat_NEUER_TOKEN_STORE2
GITHUB_TOKEN=ghp_NEUER_TOKEN
GITHUB_USERNAME=bullpowerhubgit
PORT=3200
NODE_ENV=production
MONITORING_PORT=9001
ENVEOF
    ok ".env Vorlage erstellt → nano .env zum Bearbeiten"
  fi
fi

# ENV Keys prüfen
echo ""
info "Prüfe ENV Keys..."
declare -A KEYS=(
  ["ANTHROPIC_API_KEY"]="console.anthropic.com"
  ["TELEGRAM_BOT_TOKEN"]="@BotFather"
  ["SHOPIFY_ADMIN_TOKEN"]="Shopify Admin → Apps"
  ["SHOPIFY_STORE2_TOKEN"]="Soolar Shopify Admin → Apps"
  ["GITHUB_TOKEN"]="github.com/settings/tokens"
)

ALL_OK=true
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  KEY=$(echo "$line" | awk -F= '{print $1}')
  VAL=$(echo "$line" | cut -d= -f2-)
  if [[ -n "$VAL" && "$VAL" != *"DEIN"* && "$VAL" != *"TOKEN_HIER"* && "$VAL" != *"NEUER"* ]]; then
    ok "$KEY"
  elif [[ "${KEYS[$KEY]+_}" ]]; then
    fail "$KEY fehlt → ${KEYS[$KEY]}"
    ALL_OK=false
  fi
done < .env

if [ "$ALL_OK" = false ]; then
  warn "Einige Keys fehlen — bitte .env vervollständigen"
  warn "Dann Setup erneut ausführen: ./setup.sh"
fi

# ── 3. DEPENDENCIES ──────────────────────────────────────────
step "3/8 Dependencies installieren"

if [ -f "package-lock.json" ]; then
  info "package-lock.json gefunden → npm ci"
  npm ci --omit=dev
  ok "Dependencies installiert (npm ci)"
elif [ -f "package.json" ]; then
  info "npm install"
  npm install --omit=dev
  ok "Dependencies installiert (npm install)"
else
  fail "Kein package.json gefunden!"
  exit 1
fi

# ── 4. SYNTAX CHECK ──────────────────────────────────────────
step "4/8 Syntax & Qualitäts-Check"

JS_OK=true
for f in bot.js server.js; do
  if [ -f "$f" ]; then
    if node --check "$f" 2>/dev/null; then
      ok "$f — Syntax OK"
    else
      fail "$f — Syntax FEHLER!"
      node --check "$f"
      JS_OK=false
    fi
  else
    warn "$f nicht gefunden"
  fi
done

# Duplikate Check
if [ -f "scripts/check-duplicates.js" ]; then
  if node scripts/check-duplicates.js 2>/dev/null; then
    ok "Keine Command-Duplikate"
  else
    warn "Duplikate gefunden — bot.js überprüfen"
  fi
fi

if [ "$JS_OK" = false ]; then
  fail "Syntax-Fehler gefunden — bitte zuerst fixen!"; exit 1
fi

# ── 5. LOGS VERZEICHNIS ───────────────────────────────────────
step "5/8 Directories erstellen"

mkdir -p logs scripts
ok "logs/ erstellt"
ok "scripts/ erstellt"

# Lock Files aufräumen
rm -f .bot*.lock
ok "Alte Lock-Files entfernt"

# ── 6. PM2 SETUP ─────────────────────────────────────────────
step "6/8 PM2 Setup"

if [ ! -f "ecosystem.config.js" ]; then
  warn "ecosystem.config.js nicht gefunden — erstelle..."
  cat > ecosystem.config.js << 'PM2EOF'
module.exports = {
  apps: [
    {
      name: 'autopilot-server',
      script: 'server.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env_production: { NODE_ENV: 'production', PORT: 3200 },
      error_file: 'logs/server-error.log',
      out_file: 'logs/server-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '5s',
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: 'autopilot-bot',
      script: 'bot.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env_production: { NODE_ENV: 'production' },
      error_file: 'logs/bot-error.log',
      out_file: 'logs/bot-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      min_uptime: '10s',
      max_restarts: 20,
      restart_delay: 5000,
      pre_start: 'rm -f .bot*.lock',
    },
    {
      name: 'monitoring',
      script: 'windsurf-monitoring.js',
      instances: 1,
      autorestart: true,
      env_production: { NODE_ENV: 'production', MONITORING_PORT: 9001 },
      error_file: 'logs/monitor-error.log',
      out_file: 'logs/monitor-out.log',
    }
  ]
};
PM2EOF
  ok "ecosystem.config.js erstellt"
else
  ok "ecosystem.config.js vorhanden"
fi

# PM2 stoppen falls läuft
pm2 stop all 2>/dev/null && info "Alte PM2 Prozesse gestoppt" || true
pm2 delete all 2>/dev/null || true

# PM2 starten
pm2 start ecosystem.config.js --env production
ok "PM2 gestartet"

# PM2 save + startup
pm2 save
ok "PM2 Konfiguration gespeichert"

info "PM2 Startup-Befehl (als root ausführen falls nötig):"
pm2 startup 2>/dev/null | tail -1 || true

# ── 7. HEALTH CHECK ──────────────────────────────────────────
step "7/8 Health Check"

info "Warte 5s auf Server-Start..."
sleep 5

# Server Health Check
HEALTH_URL="http://localhost:3200/api/health"
if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
  ok "Server auf Port 3200 erreichbar"
  HEALTH=$(curl -s "$HEALTH_URL")
  echo -e "  ${CYN}→ $(echo $HEALTH | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"Status: {d[\"status\"]} | Uptime: {d[\"uptime\"]} | Memory: {d[\"memory\"]}")' 2>/dev/null || echo 'OK')${NC}"
else
  warn "Server noch nicht erreichbar (ggf. länger warten: curl $HEALTH_URL)"
fi

# PM2 Status
pm2 status

# ── 8. FERTIG ────────────────────────────────────────────────
step "8/8 Setup abgeschlossen"

divider
echo -e "${GRN}"
cat << 'EOF'
  🎉 SETUP ABGESCHLOSSEN!
EOF
echo -e "${NC}"

echo -e "${WHT}URLs:${NC}"
echo -e "  🌐 Server:     ${CYN}http://localhost:3200${NC}"
echo -e "  💚 Health:     ${CYN}http://localhost:3200/api/health${NC}"
echo -e "  📊 Monitoring: ${CYN}http://localhost:9001${NC}"
echo ""
echo -e "${WHT}Nützliche Befehle:${NC}"
echo -e "  pm2 status          — Alle Prozesse"
echo -e "  pm2 logs            — Live Logs"
echo -e "  pm2 restart all     — Neustart"
echo -e "  node health.js      — Vollständiger Check"
echo -e "  curl http://localhost:3200/api/health | python3 -m json.tool"
echo ""

# Warnungen ausgeben
if [ "$ALL_OK" = false ]; then
  echo -e "${YLW}⚠️  WICHTIG: Einige API-Keys fehlen noch!${NC}"
  echo -e "  → nano .env"
  echo -e "  → pm2 restart all  (nach .env Update)"
fi

divider
echo -e "${PRP}Viel Erfolg mit deinem AutoPilot Bot! 🚀${NC}\n"
