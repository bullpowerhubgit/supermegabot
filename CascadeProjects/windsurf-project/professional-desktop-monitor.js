#!/usr/bin/env node

import http from 'http';
import { execSync, spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const PORT = 9999;
const DATA_DIR = path.join(process.cwd(), 'data');
const LOGS_DIR = path.join(process.cwd(), 'logs');

// Ensure directories exist
[DATA_DIR, LOGS_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// Alert system
const alerts = [];
const ALERT_THRESHOLDS = {
  cpu: 80,
  memory: 85,
  disk: 90,
  restarts: 5
};

function getPM2Status() {
  try {
    const output = execSync('pm2 jlist 2>/dev/null', { encoding: 'utf8', timeout: 5000 });
    const processes = JSON.parse(output);
    
    // Check for alerts
    processes.forEach(p => {
      if (p.pm2_env.restart_time > ALERT_THRESHOLDS.restarts) {
        addAlert('high', `Process ${p.name} restarted ${p.pm2_env.restart_time} times`);
      }
      if (p.monit && p.monit.cpu > ALERT_THRESHOLDS.cpu) {
        addAlert('medium', `Process ${p.name} high CPU: ${p.monit.cpu.toFixed(1)}%`);
      }
      if (p.monit && p.monit.memory > (os.totalmem() * 0.5)) {
        addAlert('medium', `Process ${p.name} high memory: ${(p.monit.memory / 1024 / 1024).toFixed(0)}MB`);
      }
    });
    
    return processes.map(p => ({
      name: p.name,
      status: p.pm2_env.status,
      pid: p.pid,
      restarts: p.pm2_env.restart_time,
      memory: p.monit ? p.monit.memory : 0,
      cpu: p.monit ? p.monit.cpu : 0,
      uptime: p.pm2_env.pm_uptime,
      cpu_usage: p.monit ? p.monit.cpu : 0,
      memory_mb: p.monit ? Math.round(p.monit.memory / 1024 / 1024) : 0
    }));
  } catch { return []; }
}

function getSystemStats() {
  const totalmem = os.totalmem();
  const freemem = os.freemem();
  const usedmem = totalmem - freemem;
  const percent = Math.round((usedmem / totalmem) * 100);
  
  // Check for alerts
  if (percent > ALERT_THRESHOLDS.memory) {
    addAlert('high', `High memory usage: ${percent}%`);
  }
  
  const loadavg = os.loadavg();
  const cpuPercent = Math.round((loadavg[0] / os.cpus().length) * 100);
  
  if (cpuPercent > ALERT_THRESHOLDS.cpu) {
    addAlert('high', `High CPU usage: ${cpuPercent}%`);
  }
  
  // Disk usage
  let diskUsage = { used: 0, total: 0, percent: 0 };
  try {
    const dfOutput = execSync('df -h /', { encoding: 'utf8' });
    const lines = dfOutput.split('\n');
    if (lines.length > 1) {
      const parts = lines[1].split(/\s+/);
      diskUsage = {
        used: parts[2],
        total: parts[1],
        percent: parseInt(parts[4])
      };
    }
  } catch (e) {}
  
  if (diskUsage.percent > ALERT_THRESHOLDS.disk) {
    addAlert('high', `High disk usage: ${diskUsage.percent}%`);
  }
  
  return {
    totalmem: Math.round(totalmem / 1024 / 1024 / 1024),
    freemem: Math.round(freemem / 1024 / 1024 / 1024),
    usedmem: Math.round(usedmem / 1024 / 1024 / 1024),
    percent,
    uptime: Math.round(os.uptime()),
    loadavg,
    cpuPercent,
    cpus: os.cpus().length,
    diskUsage,
    platform: os.platform(),
    arch: os.arch(),
    hostname: os.hostname()
  };
}

function getProcessCount() {
  try {
    const output = execSync('ps aux | wc -l', { encoding: 'utf8' });
    return parseInt(output.trim());
  } catch { return 0; }
}

function getNetworkStats() {
  try {
    const output = execSync('netstat -an | grep ESTABLISHED | wc -l', { encoding: 'utf8' });
    return {
      connections: parseInt(output.trim()),
      timestamp: Date.now()
    };
  } catch { return { connections: 0, timestamp: Date.now() }; }
}

function addAlert(severity, message) {
  const existing = alerts.find(a => a.message === message);
  if (!existing) {
    alerts.unshift({
      id: Date.now(),
      severity,
      message,
      timestamp: new Date().toISOString()
    });
    // Keep only last 50 alerts
    if (alerts.length > 50) alerts.pop();
  }
}

function getLogs(service, lines = 50) {
  try {
    const logPath = `/tmp/${service}-pm2.log`;
    if (fs.existsSync(logPath)) {
      const output = execSync(`tail -n ${lines} ${logPath}`, { encoding: 'utf8' });
      return output.split('\n').filter(line => line.trim());
    }
    return [];
  } catch { return []; }
}

function startPM2Service(name) {
  try {
    execSync(`pm2 start ${name} --update-env`, { encoding: 'utf8' });
    return { success: true, message: `Started ${name}` };
  } catch (error) {
    return { success: false, message: error.message };
  }
}

function stopPM2Service(name) {
  try {
    execSync(`pm2 stop ${name}`, { encoding: 'utf8' });
    return { success: true, message: `Stopped ${name}` };
  } catch (error) {
    return { success: false, message: error.message };
  }
}

function restartPM2Service(name) {
  try {
    execSync(`pm2 restart ${name} --update-env`, { encoding: 'utf8' });
    return { success: true, message: `Restarted ${name}` };
  } catch (error) {
    return { success: false, message: error.message };
  }
}

function getPM2Logs(name, lines = 100) {
  try {
    const output = execSync(`pm2 logs ${name} --lines ${lines} --nostream`, { encoding: 'utf8' });
    return output.split('\n').filter(line => line.trim());
  } catch { return []; }
}

const HTML = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Professional Desktop Monitor</title>
  <style>
    :root {
      --bg: #0a0a0f;
      --surface: #12121a;
      --card: #1a1a26;
      --border: #2a2a40;
      --accent: #6c63ff;
      --accent2: #ff6584;
      --green: #43d98c;
      --yellow: #ffd700;
      --red: #ff4757;
      --orange: #ff6b35;
      --text: #e8e8f0;
      --muted: #7070a0;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 20px;
      min-height: 100vh;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .header h1 {
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    .header-info {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .live-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--green);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .refresh-btn {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 20px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s;
    }
    .refresh-btn:hover {
      background: var(--border);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      transition: border-color 0.2s;
    }
    .card:hover {
      border-color: var(--accent);
    }
    .card-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--muted);
      margin-bottom: 16px;
      font-weight: 600;
    }
    .metric {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 12px 0;
    }
    .metric-label {
      color: var(--muted);
      font-size: 14px;
    }
    .metric-value {
      font-size: 16px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .bar-track {
      height: 8px;
      background: var(--border);
      border-radius: 4px;
      overflow: hidden;
      margin-top: 8px;
    }
    .bar-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.5s;
    }
    .bar-green { background: linear-gradient(90deg, var(--green), #6edfa0); }
    .bar-yellow { background: linear-gradient(90deg, var(--yellow), #ffec6e); }
    .bar-red { background: linear-gradient(90deg, var(--red), #ff758c); }
    .bar-accent { background: linear-gradient(90deg, var(--accent), #9f7aea); }
    .status-online { color: var(--green); }
    .status-offline { color: var(--red); }
    .status-errored { color: var(--yellow); }
    .service-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
    }
    .service-row:last-child {
      border-bottom: none;
    }
    .service-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .service-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .service-dot.online { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .service-dot.offline { background: var(--red); }
    .service-dot.errored { background: var(--yellow); }
    .service-name {
      font-size: 14px;
      font-weight: 500;
    }
    .service-meta {
      font-size: 12px;
      color: var(--muted);
    }
    .service-actions {
      display: flex;
      gap: 6px;
    }
    .action-btn {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 11px;
      transition: all 0.2s;
    }
    .action-btn:hover {
      background: var(--border);
    }
    .action-btn.restart:hover {
      background: var(--yellow);
      color: #000;
    }
    .action-btn.stop:hover {
      background: var(--red);
    }
    .alert-item {
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 8px;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .alert-high {
      background: rgba(255, 71, 87, 0.15);
      border: 1px solid rgba(255, 71, 87, 0.3);
    }
    .alert-medium {
      background: rgba(255, 215, 0, 0.15);
      border: 1px solid rgba(255, 215, 0, 0.3);
    }
    .alert-low {
      background: rgba(108, 99, 255, 0.15);
      border: 1px solid rgba(108, 99, 255, 0.3);
    }
    .log-viewer {
      background: #050508;
      border-radius: 8px;
      padding: 12px;
      font-family: 'SF Mono', Monaco, monospace;
      font-size: 12px;
      color: var(--green);
      line-height: 1.5;
      max-height: 400px;
      overflow-y: auto;
      white-space: pre-wrap;
    }
    .log-viewer::-webkit-scrollbar {
      width: 6px;
    }
    .log-viewer::-webkit-scrollbar-track {
      background: var(--surface);
    }
    .log-viewer::-webkit-scrollbar-thumb {
      background: var(--border);
      border-radius: 3px;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    .stat-box {
      background: var(--surface);
      border-radius: 8px;
      padding: 12px;
      text-align: center;
    }
    .stat-value {
      font-size: 24px;
      font-weight: 700;
      color: var(--accent);
    }
    .stat-label {
      font-size: 11px;
      color: var(--muted);
      margin-top: 4px;
      text-transform: uppercase;
    }
    .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: var(--muted);
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🖥️ Professional Desktop Monitor</h1>
      <div style="font-size: 13px; color: var(--muted); margin-top: 4px;">
        Real-time system monitoring · PM2 management · Alert system
      </div>
    </div>
    <div class="header-info">
      <div style="display: flex; align-items: center; gap: 8px;">
        <div class="live-dot"></div>
        <span style="font-size: 14px; font-weight: 500;">Live</span>
      </div>
      <button class="refresh-btn" onclick="loadData()">🔄 Refresh</button>
    </div>
  </div>

  <div class="grid">
    <!-- System Stats -->
    <div class="card">
      <div class="card-title">System Resources</div>
      <div class="metric">
        <span class="metric-label">CPU Usage</span>
        <span class="metric-value" id="cpu-value">...</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill bar-accent" id="cpu-bar" style="width: 0%"></div>
      </div>
      <div class="metric">
        <span class="metric-label">Memory</span>
        <span class="metric-value" id="memory-value">...</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill bar-green" id="memory-bar" style="width: 0%"></div>
      </div>
      <div class="metric">
        <span class="metric-label">Disk</span>
        <span class="metric-value" id="disk-value">...</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill bar-yellow" id="disk-bar" style="width: 0%"></div>
      </div>
    </div>

    <!-- System Info -->
    <div class="card">
      <div class="card-title">System Information</div>
      <div class="stats-grid">
        <div class="stat-box">
          <div class="stat-value" id="cpu-cores">...</div>
          <div class="stat-label">CPU Cores</div>
        </div>
        <div class="stat-box">
          <div class="stat-value" id="process-count">...</div>
          <div class="stat-label">Processes</div>
        </div>
        <div class="stat-box">
          <div class="stat-value" id="connections">...</div>
          <div class="stat-label">Connections</div>
        </div>
        <div class="stat-box">
          <div class="stat-value" id="uptime">...</div>
          <div class="stat-label">Uptime</div>
        </div>
      </div>
      <div style="margin-top: 16px; font-size: 13px; color: var(--muted);">
        <div>Platform: <span id="platform">...</span></div>
        <div>Arch: <span id="arch">...</span></div>
        <div>Hostname: <span id="hostname">...</span></div>
      </div>
    </div>

    <!-- Alerts -->
    <div class="card" style="grid-column: span 2;">
      <div class="card-title">Alerts</div>
      <div id="alerts-list">
        <div class="empty-state">No alerts</div>
      </div>
    </div>
  </div>

  <!-- PM2 Services -->
  <div class="card" style="margin-bottom: 24px;">
    <div class="card-title">PM2 Services</div>
    <div id="services-list">
      <div class="empty-state">Loading services...</div>
    </div>
  </div>

  <!-- Log Viewer -->
  <div class="card">
    <div class="card-title">
      <span>Log Viewer</span>
      <select id="log-service" style="margin-left: auto; background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 12px; font-size: 13px;">
        <option value="">Select service...</option>
      </select>
    </div>
    <div class="log-viewer" id="log-viewer">
      <div style="color: var(--muted);">Select a service to view logs</div>
    </div>
  </div>

  <script>
    async function loadData() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        // System stats
        document.getElementById('cpu-value').textContent = data.system.cpuPercent + '%';
        document.getElementById('cpu-bar').style.width = data.system.cpuPercent + '%';
        document.getElementById('cpu-bar').className = 'bar-fill ' + (data.system.cpuPercent < 70 ? 'bar-green' : data.system.cpuPercent < 85 ? 'bar-yellow' : 'bar-red');
        
        document.getElementById('memory-value').textContent = data.system.usedmem + 'GB / ' + data.system.totalmem + 'GB (' + data.system.percent + '%)';
        document.getElementById('memory-bar').style.width = data.system.percent + '%';
        document.getElementById('memory-bar').className = 'bar-fill ' + (data.system.percent < 70 ? 'bar-green' : data.system.percent < 85 ? 'bar-yellow' : 'bar-red');
        
        document.getElementById('disk-value').textContent = data.system.diskUsage.used + ' / ' + data.system.diskUsage.total + ' (' + data.system.diskUsage.percent + '%)';
        document.getElementById('disk-bar').style.width = data.system.diskUsage.percent + '%';
        document.getElementById('disk-bar').className = 'bar-fill ' + (data.system.diskUsage.percent < 70 ? 'bar-green' : data.system.diskUsage.percent < 85 ? 'bar-yellow' : 'bar-red');
        
        // System info
        document.getElementById('cpu-cores').textContent = data.system.cpus;
        document.getElementById('process-count').textContent = data.processCount;
        document.getElementById('connections').textContent = data.network.connections;
        const uptime = data.system.uptime;
        document.getElementById('uptime').textContent = Math.floor(uptime / 3600) + 'h ' + Math.floor((uptime % 3600) / 60) + 'm';
        document.getElementById('platform').textContent = data.system.platform;
        document.getElementById('arch').textContent = data.system.arch;
        document.getElementById('hostname').textContent = data.system.hostname;
        
        // Alerts
        const alertsList = document.getElementById('alerts-list');
        if (data.alerts.length > 0) {
          alertsList.innerHTML = data.alerts.map(alert => {
            const severityClass = alert.severity === 'high' ? 'alert-high' : alert.severity === 'medium' ? 'alert-medium' : 'alert-low';
            return '<div class="alert-item ' + severityClass + '">' +
              '<span>' + (alert.severity === 'high' ? '🔴' : alert.severity === 'medium' ? '🟡' : '🔵') + '</span>' +
              '<span>' + alert.message + '</span>' +
              '<span style="margin-left: auto; font-size: 11px; color: var(--muted);">' + new Date(alert.timestamp).toLocaleTimeString() + '</span>' +
              '</div>';
          }).join('');
        } else {
          alertsList.innerHTML = '<div class="empty-state">No alerts</div>';
        }
        
        // Services
        const servicesList = document.getElementById('services-list');
        const logSelect = document.getElementById('log-service');
        
        if (data.pm2.length > 0) {
          servicesList.innerHTML = data.pm2.map(service => {
            const statusClass = service.status === 'online' ? 'online' : service.status === 'errored' ? 'errored' : 'offline';
            return '<div class="service-row">' +
              '<div class="service-info">' +
              '<div class="service-dot ' + statusClass + '"></div>' +
              '<div>' +
              '<div class="service-name">' + service.name + '</div>' +
              '<div class="service-meta">PID: ' + service.pid + ' · Memory: ' + service.memory_mb + 'MB · CPU: ' + service.cpu_usage.toFixed(1) + '% · Restarts: ' + service.restarts + '</div>' +
              '</div>' +
              '</div>' +
              '<div class="service-actions">' +
              '<button class="action-btn" onclick="viewLogs(\'' + service.name + '\')">📋 Logs</button>' +
              '<button class="action-btn restart" onclick="restartService(\'' + service.name + '\')">🔄 Restart</button>' +
              '<button class="action-btn stop" onclick="stopService(\'' + service.name + '\')">⏹️ Stop</button>' +
              '</div>' +
              '</div>';
          }).join('');
          
          // Update log select
          logSelect.innerHTML = '<option value="">Select service...</option>' + 
            data.pm2.map(s => '<option value="' + s.name + '">' + s.name + '</option>').join('');
        } else {
          servicesList.innerHTML = '<div class="empty-state">No PM2 services running</div>';
        }
        
      } catch (error) {
        console.error('Load failed:', error);
      }
    }
    
    async function viewLogs(service) {
      try {
        const res = await fetch('/api/logs/' + service);
        const logs = await res.json();
        const logViewer = document.getElementById('log-viewer');
        if (logs.length > 0) {
          logViewer.innerHTML = logs.join('\n');
        } else {
          logViewer.innerHTML = '<div style="color: var(--muted);">No logs available</div>';
        }
        document.getElementById('log-service').value = service;
      } catch (error) {
        console.error('Failed to load logs:', error);
      }
    }
    
    async function restartService(service) {
      try {
        const res = await fetch('/api/service/' + service + '/restart', { method: 'POST' });
        const result = await res.json();
        alert(result.message);
        loadData();
      } catch (error) {
        console.error('Failed to restart:', error);
      }
    }
    
    async function stopService(service) {
      if (confirm('Stop ' + service + '?')) {
        try {
          const res = await fetch('/api/service/' + service + '/stop', { method: 'POST' });
          const result = await res.json();
          alert(result.message);
          loadData();
        } catch (error) {
          console.error('Failed to stop:', error);
        }
      }
    }
    
    // Log select change
    document.getElementById('log-service')
.addEventListener('change', function() {
      if (this.value) {
        viewLogs(this.value);
      }
    });
    
    // Initial load
    loadData();

    setInterval(loadData, 5000);
  </script>
</body>
</html>`;

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  
  if (url.pathname === '/api/status') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({
      timestamp: new Date().toISOString(),
      system: getSystemStats(),
      pm2: getPM2Status(),
      processCount: getProcessCount(),
      network: getNetworkStats(),
      alerts: alerts
    }));
  } else if (url.pathname.startsWith('/api/logs/')) {
    const service = url.pathname.split('/').pop();
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(getPM2Logs(service, 100)));
  } else if (url.pathname.startsWith('/api/service/') && url.pathname.endsWith('/restart')) {
    const service = url.pathname.split('/')[3];
    const result = restartPM2Service(service);
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(result));
  } else if (url.pathname.startsWith('/api/service/') && url.pathname.endsWith('/stop')) {
    const service = url.pathname.split('/')[3];
    const result = stopPM2Service(service);
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(result));
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(HTML);
  }
});

server.listen(PORT, () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('🖥️ Professional Desktop Monitor: http://localhost:' + PORT);
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('📊 Real-time system monitoring active');
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('⚠️  Alert system enabled');
});
