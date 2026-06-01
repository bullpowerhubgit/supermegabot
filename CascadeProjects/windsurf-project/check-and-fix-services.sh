#!/bin/bash

echo "🔍 PRÜFE N8N INSTALLATION..."
if which n8n >/dev/null 2>&1; then
    echo "✅ n8n installiert"
    n8n --version 2>/dev/null || true
else
    echo "❌ n8n nicht installiert - Starte Installation..."
    npm install -g n8n 2>&1 | tail -5
fi

echo ""
echo "🚀 PRÜFE N8N SERVICE..."
if curl -s http://localhost:5678 >/dev/null 2>&1; then
    echo "✅ n8n läuft auf Port 5678!"
else
    echo "⏳ Starte n8n..."
    nohup n8n start > /tmp/n8n.log 2>&1 &
    sleep 3
    if curl -s http://localhost:5678 >/dev/null 2>&1; then
        echo "✅ n8n läuft jetzt auf Port 5678!"
    else
        echo "⚠️ n8n startet noch... Siehe /tmp/n8n.log"
    fi
fi

echo ""
echo "🔧 FIXE NETDATA..."
if curl -s http://localhost:19999 >/dev/null 2>&1; then
    echo "✅ Netdata läuft bereits!"
else
    curl -s https://get.netdata.cloud/kickstart.sh > /tmp/netdata-kickstart.sh 2>&1
    timeout 120 sh /tmp/netdata-kickstart.sh --stable-channel --disable-telemetry --non-interactive 2>&1 | tail -15 || echo "⚠️ Netdata install abgebrochen oder fehlgeschlagen"
fi

echo ""
echo "PRÜFE NETDATA:"
if curl -s http://localhost:19999 >/dev/null 2>&1; then
  echo "✅ Netdata läuft!"
else
  echo "⏳ Netdata startet noch..."
fi
