#!/bin/zsh
#
# 🔧 Fix n8n & Netdata Brew-Probleme
# Behebt: n8n NICHT in brew, netdata brew-Service Probleme
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BREW_PREFIX=""
if [ -x /opt/homebrew/bin/brew ]; then
  BREW_PREFIX=/opt/homebrew
elif [ -x /usr/local/bin/brew ]; then
  BREW_PREFIX=/usr/local
else
  echo "${RED}❌ Homebrew nicht gefunden!${NC}"
  exit 1
fi

eval "$(${BREW_PREFIX}/bin/brew shellenv)"

log_info()  { echo "${BLUE}ℹ️  $1${NC}"; }
log_ok()    { echo "${GREEN}✅ $1${NC}"; }
log_warn()  { echo "${YELLOW}⚠️  $1${NC}"; }
log_err()   { echo "${RED}❌ $1${NC}"; }

echo ""
echo "═══════════════════════════════════════════════"
echo "  🔧 N8N & NETDATA BREW-FIX"
echo "  Homebrew Prefix: ${BREW_PREFIX}"
echo "═══════════════════════════════════════════════"
echo ""

# ═══════════════════════════════════════════════
# 1. BREW REPARIEREN
# ═══════════════════════════════════════════════
log_info "Repariere Homebrew..."

timeout 60 brew update --force >/dev/null 2>&1 || true
# SKIP: brew upgrade --greedy-latest  # zu langsam, nicht nötig für Fix
timeout 30 brew cleanup -s 2>/dev/null || true
timeout 30 brew doctor 2>&1 | grep -E "(Warning|Error)" | head -5 || log_ok "brew doctor OK"

# ═══════════════════════════════════════════════
# 2. N8N FIXEN (nicht in brew! -> npm)
# ═══════════════════════════════════════════════
echo ""
log_info "Prüfe n8n..."

N8N_OK=false
if command -v n8n >/dev/null 2>&1; then
  N8N_VER=$(n8n --version 2>/dev/null || echo "unknown")
  log_ok "n8n installiert (${N8N_VER})"
  N8N_OK=true
else
  log_warn "n8n nicht gefunden (brew install n8n EXISTIERT NICHT!)"
  log_info "Installiere n8n via npm..."

  # Stelle sicher, dass npm global dir existiert und in PATH ist
  NPM_GLOBAL=$(npm config get prefix 2>/dev/null || echo "${HOME}/.npm-global")
  mkdir -p "${NPM_GLOBAL}/bin"

  if [[ ":$PATH:" != *":${NPM_GLOBAL}/bin:"* ]]; then
    log_warn "${NPM_GLOBAL}/bin nicht in PATH!"
    echo "export PATH=\"${NPM_GLOBAL}/bin:\$PATH\"" >> ~/.zshrc
    export PATH="${NPM_GLOBAL}/bin:$PATH"
    log_ok "PATH aktualisiert (bitte 'source ~/.zshrc' ausführen)"
  fi

  # Prüfe ob n8n-Installation bereits läuft
  if pgrep -f "npm install.*n8n" >/dev/null 2>&1; then
    log_warn "n8n-Installation läuft bereits, warte..."
    for i in {1..30}; do
      sleep 10
      if command -v n8n >/dev/null 2>&1; then break; fi
    done
  else
    npm install -g n8n 2>&1 | tail -n 5
  fi

  if command -v n8n >/dev/null 2>&1; then
    log_ok "n8n erfolgreich installiert"
    N8N_OK=true
  else
    log_err "n8n Installation fehlgeschlagen!"
  fi
fi

# n8n Dienst starten
if [ "$N8N_OK" = true ]; then
  if curl --max-time 2 -s http://localhost:5678 >/dev/null 2>&1; then
    log_ok "n8n läuft bereits auf http://localhost:5678"
  else
    log_info "Starte n8n..."
    pkill -f "n8n start" 2>/dev/null || true
    sleep 1
    nohup n8n start > /tmp/n8n.log 2>&1 &
    sleep 5
    if curl --max-time 2 -s http://localhost:5678 >/dev/null 2>&1; then
      log_ok "n8n gestartet: http://localhost:5678"
    else
      log_warn "n8n startet noch... Log: tail -f /tmp/n8n.log"
    fi
  fi
fi

# ═══════════════════════════════════════════════
# 3. NETDATA FIXEN (brew formel vorhanden)
# ═══════════════════════════════════════════════
echo ""
log_info "Prüfe Netdata..."

NETDATA_OK=false

if command -v netdata >/dev/null 2>&1; then
  log_ok "netdata binary gefunden"
  NETDATA_OK=true
elif brew list netdata >/dev/null 2>&1; then
  log_ok "netdata via brew installiert"
  NETDATA_OK=true
else
  log_warn "netdata nicht installiert"
  log_info "Installiere netdata via Homebrew..."

  # Sichere netdata Installation
  brew install netdata 2>&1 | tail -n 5 || {
    log_warn "brew install netdata fehlgeschlagen, versuche kickstart..."
    curl -s https://get.netdata.cloud/kickstart.sh > /tmp/netdata-kickstart.sh
    timeout 180 sh /tmp/netdata-kickstart.sh --stable-channel --disable-telemetry --non-interactive 2>&1 | tail -n 10 || true
  }

  if command -v netdata >/dev/null 2>&1 || brew list netdata >/dev/null 2>&1; then
    log_ok "netdata installiert"
    NETDATA_OK=true
  else
    log_err "netdata Installation fehlgeschlagen!"
  fi
fi

# Netdata Dienst starten
if [ "$NETDATA_OK" = true ]; then
  if curl --max-time 2 -s http://localhost:19999 >/dev/null 2>&1; then
    log_ok "Netdata läuft bereits auf http://localhost:19999"
  else
    log_info "Starte Netdata..."

    # Versuche brew services
    if brew list netdata >/dev/null 2>&1; then
      brew services restart netdata 2>&1 | tail -n 3 || true
      sleep 3
    fi

    # Fallback: direkt starten
    if ! curl --max-time 2 -s http://localhost:19999 >/dev/null 2>&1; then
      pkill -f netdata 2>/dev/null || true
      sleep 1
      nohup netdata > /tmp/netdata.log 2>&1 &
      sleep 3
    fi

    if curl --max-time 2 -s http://localhost:19999 >/dev/null 2>&1; then
      log_ok "Netdata gestartet: http://localhost:19999"
    else
      log_warn "Netdata startet noch... Log prüfen mit: tail -f /tmp/netdata.log"
    fi
  fi
fi

# ═══════════════════════════════════════════════
# 4. ZUSAMMENFASSUNG
# ═══════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════"
echo "  📋 ZUSAMMENFASSUNG"
echo "═══════════════════════════════════════════════"

if curl --max-time 2 -s http://localhost:5678 >/dev/null 2>&1; then
  log_ok "n8n:     http://localhost:5678"
else
  log_err "n8n:     NICHT ERREICHBAR"
fi

if curl --max-time 2 -s http://localhost:19999 >/dev/null 2>&1; then
  log_ok "Netdata: http://localhost:19999"
else
  log_err "Netdata: NICHT ERREICHBAR"
fi

echo "═══════════════════════════════════════════════"
echo ""
echo "💡 WICHTIG: n8n ist NICHT via brew verfügbar!"
echo "   Immer installieren mit: npm install -g n8n"
echo ""
echo "💡 Netdata via brew:"
echo "   brew install netdata"
echo "   brew services start netdata"
echo ""
echo "🎉 Fix abgeschlossen!"
echo ""
