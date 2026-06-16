---
description: Starte den SuperMegaBot MCP-Server und verbinde ihn mit Claude
---

# SuperMegaBot MCP Server Start

Dieser Workflow startet den MCP-Server und stellt sicher, dass Claude Zugriff auf alle Tools hat.

## Voraussetzungen

- `.env` Datei existiert mit allen Keys
- `mcp_server.py` ist im Projektroot
- Dashboard läuft auf Port 8888 (optional)

## Schritte

1. Umgebung prüfen
// turbo
```bash
cd /Users/rudolfsarkany/supermegabot && ls -la .env mcp_server.py
```

2. MCP-Server direkt testen
```bash
cd /Users/rudolfsarkany/supermegabot && python3 -c "
import subprocess, json, time
proc = subprocess.Popen(['python3', 'mcp_server.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'windsurf','version':'1.0'}}}) + '\n')
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
for line in out.strip().split('\n'):
    if line:
        msg = json.loads(line)
        if 'result' in msg and 'tools' in msg['result']:
            print(f'✅ MCP-Server läuft. {len(msg[\"result\"][\"tools\"])} Tools verfügbar.')
        elif 'error' in msg:
            print(f'❌ Fehler: {msg[\"error\"]}')
"
```

3. Windsurf-MCP-Config validieren
```bash
cd /Users/rudolfsarkany/supermegabot && python3 -c "
import json
with open('.windsurf/mcp_config.json') as f:
    cfg = json.load(f)
servers = cfg.get('mcpServers', {})
print('Windsurf MCP-Server:')
for name, s in servers.items():
    print(f'  • {name}: {s.get(\"command\", \"HTTP\")}')
if 'supermegabot' in servers:
    print('\n✅ supermegabot ist in Windsurf konfiguriert')
else:
    print('\n⚠️  supermegabot fehlt in der Config')
"
```

4. Dashboard-Status prüfen (optional)
```bash
curl -s http://localhost:8888/health | python3 -m json.tool 2>/dev/null || echo "Dashboard nicht erreichbar"
```

## Nach dem Start

- Der MCP-Server wird automatisch von Claude Code (Windsurf) verwendet
- Verfügbare Tools: Systemstatus, Services, Guardian, Shopify, Telegram, Trading, Mac-Actions
- Testen: "Zeige mir den Systemstatus" oder "Welche Services laufen?"
