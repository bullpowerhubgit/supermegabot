#!/bin/bash
set -e

echo "🚀 SuperMegaBot MCP Server Start"
echo "================================="

cd "$(dirname "$0")"

# Prüfe .env
if [ ! -f .env ]; then
    echo "❌ .env fehlt. Kopiere von .env.example:"
    echo "   cp .env.example .env"
    exit 1
fi
echo "✅ .env vorhanden"

# Prüfe mcp_server.py
if [ ! -f mcp_server.py ]; then
    echo "❌ mcp_server.py nicht gefunden"
    exit 1
fi
echo "✅ mcp_server.py vorhanden"

# Prüfe Windsurf-Config
if [ -f .windsurf/mcp_config.json ]; then
    echo "✅ Windsurf MCP-Config vorhanden"
else
    echo "⚠️  .windsurf/mcp_config.json fehlt"
fi

# Prüfe Claude Desktop-Config
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -f "$CLAUDE_CONFIG" ]; then
    if grep -q '"supermegabot"' "$CLAUDE_CONFIG" 2>/dev/null; then
        echo "✅ Claude Desktop Config enthält supermegabot"
    else
        echo "⚠️  Claude Desktop Config ohne supermegabot"
        echo "   Führe aus: python3 setup_mcp_for_claude.py"
    fi
else
    echo "⚠️  Claude Desktop nicht installiert oder Config nicht gefunden"
fi

echo ""
echo "🧪 Teste MCP-Server..."
python3 -c "
import subprocess, json, time
proc = subprocess.Popen(['python3', 'mcp_server.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'1.0'}}}) + '\n')
proc.stdin.flush()
time.sleep(0.2)
proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}) + '\n')
proc.stdin.flush()
time.sleep(0.2)
proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'}) + '\n')
proc.stdin.flush()
time.sleep(0.5)
proc.stdin.close()
out = proc.stdout.read()
proc.kill()
ok = False
for line in out.strip().split('\n'):
    if not line: continue
    try:
        msg = json.loads(line)
        if 'result' in msg and 'tools' in msg['result']:
            print(f'✅ MCP-Server OK – {len(msg[\"result\"][\"tools\"])} Tools verfügbar')
            ok = True
    except:
        pass
if not ok:
    print('❌ MCP-Server-Test fehlgeschlagen')
"

echo ""
echo "📋 Nächste Schritte:"
echo "   • Claude Desktop: Neu starten (Cmd+Q, neu öffnen)"
echo "   • Windsurf: /mcp-start Workflow ausführen"
echo "   • Testen: 'Zeige mir den Systemstatus'"
