#!/bin/bash
# SuperMegaBot .env Fixer
# Bereinigt fehlerhafte Einträge und fragt sicher nach neuen Tokens

set -e
ENV_FILE="$HOME/supermegabot/.env"
BACKUP="$HOME/supermegabot/.env.backup.$(date +%s)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SuperMegaBot .env Fixer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Backup
cp "$ENV_FILE" "$BACKUP"
echo "✅ Backup: $BACKUP"

# Schritt 1: Kaputte Telegram-Zeilen entfernen
python3 - <<'PYFIX'
import re, os

env_path = os.path.expanduser("~/supermegabot/.env")
lines = open(env_path).readlines()

cleaned = []
skip_next = False
for line in lines:
    # Entferne bekannte kaputte Muster
    if re.match(r'^TELEGRAM_API_ID@', line):
        skip_next = True
        continue
    if skip_next and re.match(r'^=\d{10}:', line):
        skip_next = False
        continue
    skip_next = False
    # Entferne doppelte TELEGRAM_BOT_TOKEN Zeilen (nur erste behalten)
    if line.startswith('TELEGRAM_BOT_TOKEN=') and any(
        l.startswith('TELEGRAM_BOT_TOKEN=') for l in cleaned
    ):
        continue
    cleaned.append(line)

with open(env_path, 'w') as f:
    f.writelines(cleaned)
print("✅ Kaputte Zeilen entfernt")
PYFIX

# Schritt 2: Telegram Token eingeben
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TELEGRAM BOT TOKEN"
echo "  → @BotFather → /mybots → @DudiRudibot → API Token → Revoke"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -n "Neuen Token einfügen (unsichtbar): "
read -s TELEGRAM_TOKEN
echo ""

if [ -n "$TELEGRAM_TOKEN" ]; then
    # Teste Token sofort
    RESULT=$(python3 -c "
import urllib.request, json, sys
t = '$TELEGRAM_TOKEN'
try:
    r = urllib.request.urlopen(f'https://api.telegram.org/bot{t}/getMe', timeout=5)
    d = json.loads(r.read())
    print('OK:' + d['result']['username'])
except Exception as e:
    print('FAIL:' + str(e))
")
    if [[ "$RESULT" == OK:* ]]; then
        BOT_NAME="${RESULT#OK:}"
        echo "✅ Token gültig — Bot: @$BOT_NAME"
        # In .env schreiben
        python3 -c "
import os, re
env = open(os.path.expanduser('~/supermegabot/.env')).read()
if 'TELEGRAM_BOT_TOKEN=' in env:
    env = re.sub(r'TELEGRAM_BOT_TOKEN=.*', 'TELEGRAM_BOT_TOKEN=$TELEGRAM_TOKEN', env)
else:
    env += '\nTELEGRAM_BOT_TOKEN=$TELEGRAM_TOKEN\n'
open(os.path.expanduser('~/supermegabot/.env'), 'w').write(env)
print('✅ TELEGRAM_BOT_TOKEN gespeichert')
"
    else
        echo "❌ Token ungültig: $RESULT"
        echo "   Bitte nochmal @BotFather → /revoke → neuen Token holen"
        exit 1
    fi
else
    echo "⏭  Übersprungen"
fi

# Schritt 3: Telegram Chat ID
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TELEGRAM CHAT ID"
echo "  → Deine Chat-ID (z.B. 123456789)"
echo "  → Findest du bei @userinfobot"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
CURRENT_CHAT=$(python3 -c "
import os; from dotenv import load_dotenv; load_dotenv('$(echo $ENV_FILE)')
v = os.getenv('TELEGRAM_CHAT_ID','')
print(v[:4] + '***' if len(v)>4 else '(leer)')
" 2>/dev/null)
echo "Aktuell: $CURRENT_CHAT"
echo -n "Neue Chat-ID (Enter = überspringen): "
read CHAT_ID
if [ -n "$CHAT_ID" ]; then
    python3 -c "
import os, re
env = open(os.path.expanduser('~/supermegabot/.env')).read()
if 'TELEGRAM_CHAT_ID=' in env:
    env = re.sub(r'TELEGRAM_CHAT_ID=.*', 'TELEGRAM_CHAT_ID=$CHAT_ID', env)
else:
    env += '\nTELEGRAM_CHAT_ID=$CHAT_ID\n'
open(os.path.expanduser('~/supermegabot/.env'), 'w').write(env)
print('✅ TELEGRAM_CHAT_ID gespeichert')
"
fi

# Schritt 4: Supabase Anon Key
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SUPABASE ANON KEY"
echo "  → supabase.com → Projekt → Settings → API → anon public"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -n "Supabase Anon Key (unsichtbar, Enter = überspringen): "
read -s SUPA_KEY
echo ""
if [ -n "$SUPA_KEY" ]; then
    python3 -c "
import os, re
env = open(os.path.expanduser('~/supermegabot/.env')).read()
if 'SUPABASE_ANON_KEY=' in env:
    env = re.sub(r'SUPABASE_ANON_KEY=.*', 'SUPABASE_ANON_KEY=$SUPA_KEY', env)
else:
    env += '\nSUPABASE_ANON_KEY=$SUPA_KEY\n'
open(os.path.expanduser('~/supermegabot/.env'), 'w').write(env)
print('✅ SUPABASE_ANON_KEY gespeichert')
"
fi

# Schritt 5: Finaler Test
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  LIVE-TEST aller Verbindungen"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ~/supermegabot && python3 test_live_connections.py

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FERTIG — Dashboard starten mit:"
echo "  python3 dashboard/server.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
