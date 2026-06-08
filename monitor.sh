#!/bin/bash
# ============================================================
# monitor.sh — Prozess-Monitor mit Auto-Fix & Telegram-Alert
# ============================================================

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_CHAT_ID:-5088771245}"
PROJECT_DIR="/Users/rudolfsarkany/supermegabot"
LOG_FILE="/tmp/supermegabot-monitor.log"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$(dirname "$LOG_FILE")"

# ── Telegram Nachricht senden ────────────────────────────────
send_telegram() {
    local msg="$1"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "parse_mode=Markdown" \
        --data-urlencode "text=${msg}" > /dev/null 2>&1
}

# ── Log schreiben ────────────────────────────────────────────
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ── Port prüfen & PM2-Service neu starten ────────────────────
check_port() {
    local name="$1"
    local port="$2"
    local pm2_name="$3"

    if nc -z localhost "$port" 2>/dev/null; then
        log "✅ $name (:$port) läuft"
    else
        log "⚠️ $name (:$port) gestoppt — starte neu..."
        send_telegram "⚠️ *$name gestoppt!*
Starte automatisch neu via PM2..."
        /opt/homebrew/bin/pm2 restart "$pm2_name" >> "$LOG_FILE" 2>&1
        sleep 5
        if nc -z localhost "$port" 2>/dev/null; then
            log "✅ $name erfolgreich neugestartet"
            send_telegram "✅ *$name wieder online! (:$port)*"
        else
            log "❌ $name Neustart fehlgeschlagen"
            send_telegram "❌ *$name Neustart fehlgeschlagen!* Bitte manuell prüfen."
        fi
    fi
}

# ── Prozess prüfen & neu starten (für nicht-PM2 Dienste) ─────
check_process() {
    local name="$1"
    local grep_pattern="$2"
    local start_cmd="$3"

    if pgrep -f "$grep_pattern" > /dev/null 2>&1; then
        log "✅ $name läuft"
    else
        log "⚠️ $name gestoppt — starte neu..."
        send_telegram "⚠️ *$name gestoppt!*
Starte automatisch neu..."
        eval "$start_cmd" >> "$LOG_FILE" 2>&1 &
        sleep 3
        if pgrep -f "$grep_pattern" > /dev/null 2>&1; then
            log "✅ $name erfolgreich neugestartet"
            send_telegram "✅ *$name wieder online!*"
        else
            log "❌ $name Neustart fehlgeschlagen"
            send_telegram "❌ *$name Neustart fehlgeschlagen!* Bitte manuell prüfen."
        fi
    fi
}

# ── Log auf Fehler prüfen ────────────────────────────────────
check_log_errors() {
    local logfile="$1"
    local service="$2"

    if [ -f "$logfile" ]; then
        # Letzte 50 Zeilen auf Fehler prüfen
        local errors=$(tail -50 "$logfile" 2>/dev/null | grep -iE "error|exception|fatal|crash|ECONNREFUSED|ETIMEDOUT" | tail -5)
        if [ -n "$errors" ]; then
            log "⚠️ Fehler in $service Log gefunden"
            send_telegram "⚠️ *Fehler in $service:*
\`\`\`
$(echo "$errors" | head -3)
\`\`\`"
        fi
    fi
}

# ── Disk-Space prüfen (3-Stufen-Alarm) ─────────────────────
check_disk() {
    local usage=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
    local free_gb=$(df -g / | tail -1 | awk '{print $4}')
    log "💾 Disk: ${usage}% belegt | ${free_gb}GB frei"

    if [ "$usage" -gt 90 ] || [ "${free_gb:-999}" -lt 10 ]; then
        log "🚨 KRITISCH: Disk ${usage}% | nur ${free_gb}GB frei!"
        send_telegram "🚨 *KRITISCH: Mac läuft voll! ${usage}% (${free_gb}GB frei)*
Starte Notfall-Bereinigung..."
        bash "$PROJECT_DIR/cleanup.sh"
    elif [ "$usage" -gt 80 ]; then
        log "⚠️ Warnung: Disk ${usage}%"
        send_telegram "⚠️ *Festplatte ${usage}% voll (${free_gb}GB frei)*
Starte Auto-Bereinigung..."
        bash "$PROJECT_DIR/cleanup.sh"
    elif [ "$usage" -gt 70 ]; then
        log "⚠️ Hinweis: Disk ${usage}%"
        send_telegram "💾 *Hinweis: Festplatte ${usage}% (${free_gb}GB frei)*
Auto-Bereinigung läuft im Hintergrund..."
        bash "$PROJECT_DIR/cleanup.sh" &
    fi
}

# ── Kritische Verzeichnisse überwachen ──────────────────────
check_storage_dirs() {
    # Ollama Modelle (wächst bei neuen AI-Modellen)
    local ollama_gb=$(du -sg ~/.ollama/models 2>/dev/null | awk '{print $1}')
    ollama_gb="${ollama_gb:-0}"
    log "🤖 Ollama Modelle: ${ollama_gb}GB"
    if [ "$ollama_gb" -gt 25 ]; then
        send_telegram "⚠️ *Ollama Modelle sehr groß: ${ollama_gb}GB*
Nicht mehr benötigte Modelle löschen:
\`ollama list\` → \`ollama rm <name>\`"
    fi

    # npm Cache
    local npm_mb=$(du -sm ~/.npm 2>/dev/null | awk '{print $1}')
    npm_mb="${npm_mb:-0}"
    log "📦 npm Cache: ${npm_mb}MB"
    if [ "$npm_mb" -gt 3000 ]; then
        npm cache clean --force 2>/dev/null
        log "🧹 npm Cache bereinigt (war ${npm_mb}MB)"
    fi

    # Bot Logs (gegen unkontrolliertes Wachstum)
    for logfile in "$PROJECT_DIR/logs/"*.log; do
        [ -f "$logfile" ] || continue
        local lsize=$(( $(wc -c < "$logfile" 2>/dev/null || echo 0) / 1024 / 1024 ))
        if [ "$lsize" -gt 50 ]; then
            tail -2000 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
            log "✂️  $(basename "$logfile") auf 2000 Zeilen gekürzt (war ${lsize}MB)"
        fi
    done
}

# ── RAM prüfen ──────────────────────────────────────────────
check_ram() {
    # macOS-korrekt: nur wired+active zählt, inactive ist nur Cache
    local vm=$(vm_stat)
    local wired=$(echo "$vm" | awk '/wired down/{gsub(/\./,""); print $4+0}')
    local active=$(echo "$vm" | awk '/Pages active/{gsub(/\./,""); print $3+0}')
    local total_pages=$(sysctl -n hw.memsize 2>/dev/null)
    local total_mb=$(( ${total_pages:-0} / 1024 / 1024 ))
    local used_mb=$(( (wired + active) * 16 / 1024 ))  # Apple Silicon = 16KB pages
    local free_mb=$(( total_mb - used_mb ))

    log "🧠 RAM: ${used_mb}MB belegt / ${total_mb}MB gesamt (${free_mb}MB frei)"
    if [ "$free_mb" -lt 1000 ] && [ "$total_mb" -gt 0 ]; then
        log "⚠️ RAM wirklich niedrig: nur ${free_mb}MB frei"
        send_telegram "🧠 *RAM niedrig: nur ${free_mb}MB frei!*
Belegt: ${used_mb}MB / ${total_mb}MB"
    fi
}

# ── Haupt-Überwachung ────────────────────────────────────────
log "=== Monitor-Check Start ==="

# PM2-verwaltete Services (Port-basierte Prüfung)
# WICHTIG: Port muss mit dem tatsächlichen Service-Port übereinstimmen!
# CreatorHub: 3002 (nicht 3000!)
# Telegram Bot: 8000 (nicht 3200! 3200 = windsurf-monitor Dashboard)
# Windsurf Auto-Heal: optional, ggf. nicht aktiv
check_port "SuperMegaBot Dashboard" 8888 "supermegabot"
check_port "Telegram Bot"           8000 "windsurf-telegram-bot"
check_port "CreatorHub"             3002 "cratorhub"
check_port "Windsurf Shopify"       3001 "windsurf-shopify"
check_port "Password Sync"          3005 "password-sync"
check_port "Windsurf API Gateway"   8080 "windsurf-api-gateway"

# Ollama (eigener Daemon, kein PM2)
check_process \
    "Ollama LLM (Port 11434)" \
    "ollama serve" \
    "ollama serve"

# OpenClaw Gateway (LaunchAgent, kein PM2)
OPENCLAW_BIN="/opt/homebrew/bin/openclaw"
if nc -z localhost 18789 2>/dev/null; then
    log "✅ OpenClaw Gateway (:18789) läuft"
else
    if [ -x "$OPENCLAW_BIN" ]; then
        log "⚠️ OpenClaw Gateway (:18789) gestoppt — starte neu..."
        send_telegram "⚠️ *OpenClaw Gateway gestoppt!* Starte automatisch neu..."
        "$OPENCLAW_BIN" gateway start >> "$LOG_FILE" 2>&1 || {
            log "⚠️ OpenClaw start fehlgeschlagen (keine Admin-Rechte?)"
            send_telegram "⚠️ *OpenClaw Gateway:* Keine Berechtigung zum Starten. Bitte manuell prüfen."
        }
        sleep 5
        if nc -z localhost 18789 2>/dev/null; then
            log "✅ OpenClaw Gateway erfolgreich neugestartet"
            send_telegram "✅ *OpenClaw Gateway wieder online! (:18789)*"
        else
            log "❌ OpenClaw Gateway Neustart fehlgeschlagen"
            send_telegram "❌ *OpenClaw Gateway Neustart fehlgeschlagen!* Bitte manuell prüfen."
        fi
    else
        log "⚠️ OpenClaw Binary nicht gefunden ($OPENCLAW_BIN) — überspringe"
    fi
fi

# Logs auf Fehler prüfen
check_log_errors "/tmp/supermegabot-pm2.log" "SuperMegaBot"
check_log_errors "/tmp/telegram-bot-pm2.log" "Telegram-Bot"
check_log_errors "/tmp/windsurf-shopify-pm2.log" "Windsurf-Shopify"

# 5. System-Ressourcen
check_disk
check_ram

# 6. Speicher-Verzeichnisse überwachen
check_storage_dirs

log "=== Monitor-Check Ende ==="

# 7. Heartbeat Report — konsistente Datenbasis für alle Agenten
if command -v python3 >/dev/null 2>&1 && [ -f "$PROJECT_DIR/heartbeat_reporter.py" ]; then
    python3 "$PROJECT_DIR/heartbeat_reporter.py" >> "$LOG_FILE" 2>&1 || log "⚠️ Heartbeat Reporter fehlgeschlagen"
fi
