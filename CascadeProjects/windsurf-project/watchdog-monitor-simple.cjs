#!/usr/bin/env node

/**
 * Watchdog Live Monitor - Simple Version (ohne WebSocket)
 * Bietet Web-Interface mit Auto-Refresh für Watchdog-Status
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const PORT = 3456;

// HTTP Server mit Web-Interface und Auto-Refresh
const server = http.createServer((req, res) => {
  if (req.url === '/' || req.url === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(getMonitorHTML());
  } else if (req.url === '/api/status') {
    handleStatusAPI(req, res);
  } else if (req.url === '/api/log') {
    handleLogAPI(req, res);
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

// HTML Template mit Auto-Refresh
function getMonitorHTML() {
  return `<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Watchdog Live Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.1);
            -webkit-backdrop-filter: blur(10px);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .card h3 {
            font-size: 1.2em;
            margin-bottom: 15px;
            color: #00d4ff;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        .status-dot.online {
            background: #00ff88;
            box-shadow: 0 0 10px #00ff88;
        }
        
        .status-dot.offline {
            background: #ff4444;
            box-shadow: 0 0 10px #ff4444;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .info-label {
            color: #aaa;
        }
        
        .info-value {
            font-weight: bold;
        }
        
        .log-container {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 10px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .log-entry {
            padding: 5px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .log-entry.error {
            color: #ff4444;
        }
        
        .log-entry.warn {
            color: #ffaa00;
        }
        
        .log-entry.info {
            color: #00d4ff;
        }
        
        .log-entry.critical {
            color: #ff0066;
            font-weight: bold;
        }
        
        .alert-box {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 20px;
            border-radius: 10px;
            background: #ff4444;
            color: white;
            font-weight: bold;
            display: none;
            z-index: 1000;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(400px);
            }
            to {
                transform: translateX(0);
            }
        }
        
        .last-update {
            text-align: center;
            color: #666;
            margin-top: 20px;
            font-size: 0.9em;
        }
        
        .refresh-btn {
            background: #00d4ff;
            color: #1a1a2e;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            margin: 10px;
        }
        
        .refresh-btn:hover {
            background: #00a8cc;
        }
    </style>
</head>
<body>
    <div class="alert-box" id="alertBox"></div>
    
    <div class="container">
        <div class="header">
            <h1>🐕 Watchdog Live Monitor</h1>
            <p>Real-time Überwachung des System Watchdogs (Auto-Refresh alle 5 Sekunden)</p>
            <button class="refresh-btn" onclick="updateData()">🔄 Jetzt aktualisieren</button>
        </div>
        
        <div class="status-grid">
            <div class="card">
                <h3>Watchdog Status</h3>
                <div class="status-indicator">
                    <div class="status-dot" id="statusDot"></div>
                    <span id="statusText">Verbinde...</span>
                </div>
                <div class="info-row">
                    <span class="info-label">PID:</span>
                    <span class="info-value" id="pid">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Label:</span>
                    <span class="info-value" id="label">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Status:</span>
                    <span class="info-value" id="statusCode">-</span>
                </div>
            </div>
            
            <div class="card">
                <h3>System Info</h3>
                <div class="info-row">
                    <span class="info-label">Uptime:</span>
                    <span class="info-value" id="uptime">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Total RAM:</span>
                    <span class="info-value" id="totalmem">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Free RAM:</span>
                    <span class="info-value" id="freemem">-</span>
                </div>
                <div class="info-row">
                    <span class="info-label">RAM Usage:</span>
                    <span class="info-value" id="ramusage">-</span>
                </div>
            </div>
            
            <div class="card">
                <h3>Alle Watchdogs</h3>
                <div id="watchdogList">
                    <p>Lade...</p>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3>📋 Watchdog Log (letzte 20 Zeilen)</h3>
            <div class="log-container" id="logContainer">
                <p>Lade Logs...</p>
            </div>
        </div>
        
        <div class="last-update">
            Letztes Update: <span id="lastUpdate">-</span> | Auto-Refresh: <span id="refreshStatus">Aktiv</span>
        </div>
    </div>
    
    <script>
        let autoRefreshInterval;
        
        function updateData() {
            Promise.all([
                fetch('/api/status').then(r => r.json()),
                fetch('/api/log').then(r => r.text())
            ]).then(([statusData, logData]) => {
                updateStatus(statusData);
                updateLog(logData);
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
            }).catch(error => {
                console.error('Update Fehler:', error);
                document.getElementById('refreshStatus').textContent = 'Fehler';
            });
        }
        
        function updateStatus(data) {
            const statusDot = document.getElementById('statusDot');
            const statusText = document.getElementById('statusText');
            
            if (data.isRunning) {
                statusDot.className = 'status-dot online';
                statusText.textContent = '✅ Aktiv';
            } else {
                statusDot.className = 'status-dot offline';
                statusText.textContent = '❌ Inaktiv';
                showAlert('⚠️ WATCHDOG NICHT AKTIV!', 'critical');
            }
            
            if (data.ourWatchdog) {
                document.getElementById('pid').textContent = data.ourWatchdog.pid;
                document.getElementById('label').textContent = data.ourWatchdog.label;
                document.getElementById('statusCode').textContent = data.ourWatchdog.status;
            }
            
            if (data.system) {
                document.getElementById('uptime').textContent = formatUptime(data.system.uptime);
                document.getElementById('totalmem').textContent = data.system.totalmem + ' GB';
                document.getElementById('freemem').textContent = data.system.freemem + ' GB';
                
                const used = data.system.totalmem - data.system.freemem;
                const percent = Math.round((used / data.system.totalmem) * 100);
                document.getElementById('ramusage').textContent = percent + '%';
            }
            
            // Watchdog Liste
            const list = document.getElementById('watchdogList');
            list.innerHTML = '';
            
            if (data.watchdogs && data.watchdogs.length > 0) {
                data.watchdogs.forEach(w => {
                    const item = document.createElement('div');
                    item.style.cssText = 'padding: 8px; margin: 5px 0; background: rgba(255, 255, 255, 0.05); border-radius: 5px;';
                    if (w.label === 'com.supermegabot.watchdog') {
                        item.style.cssText += 'background: rgba(0, 212, 255, 0.2); border: 1px solid #00d4ff;';
                    }
                    item.innerHTML = \`
                        <strong>\${w.label}</strong><br>
                        PID: \${w.pid} | Status: \${w.status}
                    \`;
                    list.appendChild(item);
                });
            } else {
                list.innerHTML = '<p>Keine Watchdogs gefunden</p>';
            }
        }
        
        function updateLog(log) {
            const container = document.getElementById('logContainer');
            container.innerHTML = '';
            
            const lines = log.split('\\n').filter(line => line.trim());
            
            lines.forEach(line => {
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.style.cssText = 'padding: 5px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05);';
                
                if (line.includes('[ERROR]')) {
                    entry.style.color = '#ff4444';
                } else if (line.includes('[WARN]')) {
                    entry.style.color = '#ffaa00';
                } else if (line.includes('[CRITICAL]')) {
                    entry.style.color = '#ff0066';
                    entry.style.fontWeight = 'bold';
                } else if (line.includes('[INFO]')) {
                    entry.style.color = '#00d4ff';
                }
                
                entry.textContent = line;
                container.appendChild(entry);
            });
            
            container.scrollTop = container.scrollHeight;
        }
        
        function showAlert(message, severity) {
            const alertBox = document.getElementById('alertBox');
            alertBox.textContent = message;
            alertBox.style.display = 'block';
            
            if (severity === 'critical') {
                alertBox.style.background = '#ff4444';
            } else {
                alertBox.style.background = '#ffaa00';
            }
            
            setTimeout(() => {
                alertBox.style.display = 'none';
            }, 10000);
        }
        
        function formatUptime(seconds) {
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            
            if (days > 0) {
                return \`\${days}d \${hours}h \${minutes}m\`;
            } else if (hours > 0) {
                return \`\${hours}h \${minutes}m\`;
            } else {
                return \`\${minutes}m\`;
            }
        }
        
        // Auto-Refresh starten
        function startAutoRefresh() {
            updateData(); // Erster Update
            autoRefreshInterval = setInterval(updateData, 5000); // Alle 5 Sekunden
        }
        
        // Seite starten
        startAutoRefresh();
    </script>
</body>
</html>`;
}

// API Handler für Status
async function handleStatusAPI(req, res) {
  try {
    const status = await getWatchdogStatus();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(status));
  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: error.message }));
  }
}

// API Handler für Log
async function handleLogAPI(req, res) {
  try {
    const log = await getWatchdogLog();
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end(log);
  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end(`Log Fehler: ${error.message}`);
  }
}

// Watchdog Status prüfen
async function getWatchdogStatus() {
  try {
    const { stdout } = await execPromise('launchctl list | grep watchdog');
    const lines = stdout.trim().split('\\n');
    
    const watchdogs = lines.map(line => {
      const parts = line.trim().split(/\\s+/);
      if (parts.length >= 3) {
        return {
          pid: parts[0],
          status: parts[1],
          label: parts[2]
        };
      }
      return null;
    }).filter(Boolean);
    
    // Prüfe ob unser Watchdog läuft
    const ourWatchdog = watchdogs.find(w => w.label === 'com.supermegabot.watchdog');
    
    return {
      timestamp: new Date().toISOString(),
      watchdogs,
      ourWatchdog: ourWatchdog || null,
      isRunning: ourWatchdog && ourWatchdog.status === '0',
      system: {
        uptime: require('os').uptime(),
        totalmem: Math.round(require('os').totalmem() / 1024 / 1024 / 1024),
        freemem: Math.round(require('os').freemem() / 1024 / 1024 / 1024)
      }
    };
  } catch (error) {
    return {
      timestamp: new Date().toISOString(),
      error: error.message,
      isRunning: false
    };
  }
}

// Watchdog Log lesen
async function getWatchdogLog() {
  try {
    const logPath = path.join(__dirname, 'watchdog.log');
    if (fs.existsSync(logPath)) {
      const { stdout } = await execPromise(`tail -20 "${logPath}"`);
      return stdout;
    }
    return 'Kein Log gefunden';
  } catch (error) {
    return `Log Fehler: ${error.message}`;
  }
}

// Helper für exec
function execPromise(cmd) {
  return new Promise((resolve, reject) => {
    exec(cmd, (error, stdout, stderr) => {
      if (error) reject(error);
      else resolve({ stdout, stderr });
    });
  });
}

// Server starten
server.listen(PORT, () => {
  console.log(`🚀 Watchdog Monitor läuft auf http://localhost:${PORT}`);
  console.log(`📊 Öffne http://localhost:${PORT} im Browser`);
  console.log('⏰ Auto-Refresh alle 5 Sekunden aktiv');
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('🛑 Monitor Server wird gestoppt...');
  server.close();
  process.exit(0);
});
