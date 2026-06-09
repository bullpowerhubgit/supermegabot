#!/usr/bin/env node
import http from 'http';
import { execSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import StorageManager from './storage-manager.js';

const PORT = 8888;
const storageManager = new StorageManager();

// Professional Dashboard Configuration
const CONFIG = {
  refreshInterval: 2000, // 2 seconds
  historySize: 60, // Keep 60 data points for charts
  alertThresholds: {
    memory: { warning: 90, critical: 95 },
    disk: { warning: 85, critical: 95 },
    cpu: { warning: 80, critical: 95 }
  }
};

// Data storage for charts
const historyData = {
  memory: [],
  cpu: [],
  disk: []
};

function getSystemStats() {
  // Get accurate macOS memory stats using vm_stat
  let appMemory = 0;
  let wiredMemory = 0;
  let compressedMemory = 0;
  let freeMemory = os.freemem();
  
  try {
    const vmStat = execSync('vm_stat', { encoding: 'utf8' });
    const pageSize = 16384;
    
    const matchFree = vmStat.match(/Pages free:\s+(\d+)/);
    const matchWired = vmStat.match(/Pages wired down:\s+(\d+)/);
    const matchActive = vmStat.match(/Pages active:\s+(\d+)/);
    const matchInactive = vmStat.match(/Pages inactive:\s+(\d+)/);
    const matchCompressed = vmStat.match(/Pages compressed:\s+(\d+)/);
    
    if (matchFree) freeMemory = parseInt(matchFree[1]) * pageSize;
    if (matchWired) wiredMemory = parseInt(matchWired[1]) * pageSize;
    if (matchActive) appMemory += parseInt(matchActive[1]) * pageSize;
    if (matchInactive) appMemory += parseInt(matchInactive[1]) * pageSize;
    if (matchCompressed) compressedMemory = parseInt(matchCompressed[1]) * pageSize;
    
    const usedMemory = appMemory + wiredMemory + compressedMemory;
    const totalMemory = os.totalmem();
    const percent = Math.round((usedMemory / totalMemory) * 100);
    
    return {
      totalmem: Math.round(totalMemory / 1024 / 1024),
      freemem: Math.round(freeMemory / 1024 / 1024),
      usedmem: Math.round(usedMemory / 1024 / 1024),
      percent: percent,
      uptime: Math.round(os.uptime()),
      loadavg: os.loadavg(),
      cpus: os.cpus().length,
      compressed: Math.round(compressedMemory / 1024 / 1024)
    };
  } catch (e) {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    return {
      totalmem: Math.round(total / 1024 / 1024),
      freemem: Math.round(free / 1024 / 1024),
      usedmem: Math.round(used / 1024 / 1024),
      percent: Math.round((used / total) * 100),
      uptime: Math.round(os.uptime()),
      loadavg: os.loadavg(),
      cpus: os.cpus().length,
      compressed: 0
    };
  }
}

function getCPUUsage() {
  try {
    const output = execSync('ps -A -o %cpu | awk \'{s+=$1} END {print s}\'', { encoding: 'utf8' });
    const cpuUsage = parseFloat(output.trim()) || 0;
    return {
      usage: Math.round(cpuUsage),
      cores: os.cpus().length,
      loadavg: os.loadavg()
    };
  } catch (e) {
    return {
      usage: 0,
      cores: os.cpus().length,
      loadavg: os.loadavg()
    };
  }
}

function getDiskStats() {
  const disks = [];
  try {
    const output = execSync('df -H', { encoding: 'utf8' });
    const lines = output.trim().split('\n').slice(1);
    
    for (const line of lines) {
      const parts = line.split(/\s+/);
      if (parts.length >= 6) {
        const filesystem = parts[0];
        const size = parts[1];
        const used = parts[2];
        const available = parts[3];
        const usePercent = parseInt(parts[4]) || 0;
        const mountpoint = parts[5];
        
        disks.push({
          filesystem,
          size,
          used,
          available,
          usePercent,
          mountpoint,
          type: mountpoint === '/' ? 'internal' : 'external'
        });
      }
    }
  } catch (e) {
    console.error('Failed to get disk stats:', e);
  }
  return disks;
}

function getProcessList() {
  try {
    const output = execSync('ps -axm -o pid,comm,pmem,rss,pcpu,time | head -20', { encoding: 'utf8' });
    const lines = output.trim().split('\n').slice(1);
    const processes = [];
    
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 6) {
        processes.push({
          pid: parts[0],
          name: parts[1],
          memPercent: parseFloat(parts[2]) || 0,
          memMB: Math.round((parseInt(parts[3]) || 0) / 1024),
          cpuPercent: parseFloat(parts[4]) || 0,
          time: parts[5]
        });
      }
    }
    return processes;
  } catch (e) {
    return [];
  }
}

function getWatchdogStatus() {
  try {
    const pidfile = '/tmp/supermegabot-watchdog.pid';
    if (fs.existsSync(pidfile)) {
      const pid = fs.readFileSync(pidfile, 'utf8').trim();
      try { execSync(`ps -p ${pid}`, { stdio: 'ignore' }); return { running: true, pid }; } catch { return { running: false }; }
    }
    return { running: false };
  } catch { return { running: false }; }
}

function getStorageManagerStatus() {
  try {
    const logFile = '/tmp/storage-manager.log';
    if (fs.existsSync(logFile)) {
      const stats = fs.statSync(logFile);
      const lastModified = new Date(stats.mtime);
      const recent = (Date.now() - lastModified.getTime()) < 3600000; // Within last hour
      return { running: recent, lastModified: lastModified.toISOString() };
    }
    return { running: false, lastModified: null };
  } catch { return { running: false, lastModified: null }; }
}

function getCloudStorageStatus() {
  const cloudServices = [];
  
  try {
    const output = execSync('ps aux | grep -i "google drive" | grep -v grep', { encoding: 'utf8' });
    if (output.trim()) {
      cloudServices.push({ name: 'Google Drive', status: 'running' });
    } else {
      cloudServices.push({ name: 'Google Drive', status: 'stopped' });
    }
  } catch {
    cloudServices.push({ name: 'Google Drive', status: 'not_installed' });
  }
  
  try {
    const output = execSync('ps aux | grep -i dropbox | grep -v grep', { encoding: 'utf8' });
    if (output.trim()) {
      cloudServices.push({ name: 'Dropbox', status: 'running' });
    } else {
      cloudServices.push({ name: 'Dropbox', status: 'stopped' });
    }
  } catch {
    cloudServices.push({ name: 'Dropbox', status: 'not_installed' });
  }
  
  try {
    const output = execSync('ps aux | grep -i onedrive | grep -v grep', { encoding: 'utf8' });
    if (output.trim()) {
      cloudServices.push({ name: 'OneDrive', status: 'running' });
    } else {
      cloudServices.push({ name: 'OneDrive', status: 'stopped' });
    }
  } catch {
    cloudServices.push({ name: 'OneDrive', status: 'not_installed' });
  }
  
  try {
    const output = execSync('ps aux | grep -i "cloudd" | grep -v grep', { encoding: 'utf8' });
    if (output.trim()) {
      cloudServices.push({ name: 'iCloud Drive', status: 'running' });
    } else {
      cloudServices.push({ name: 'iCloud Drive', status: 'stopped' });
    }
  } catch {
    cloudServices.push({ name: 'iCloud Drive', status: 'not_installed' });
  }
  
  return cloudServices;
}

function getAlerts() {
  const alerts = [];
  const system = getSystemStats();
  const disks = getDiskStats();
  const cpu = getCPUUsage();
  
  if (system.percent > CONFIG.alertThresholds.memory.critical) {
    alerts.push({
      type: 'critical',
      source: 'memory',
      message: `Memory usage critical: ${system.percent}%`,
      timestamp: new Date().toISOString()
    });
  } else if (system.percent > CONFIG.alertThresholds.memory.warning) {
    alerts.push({
      type: 'warning',
      source: 'memory',
      message: `Memory usage high: ${system.percent}%`,
      timestamp: new Date().toISOString()
    });
  }
  
  if (cpu.usage > CONFIG.alertThresholds.cpu.critical) {
    alerts.push({
      type: 'critical',
      source: 'cpu',
      message: `CPU usage critical: ${cpu.usage}%`,
      timestamp: new Date().toISOString()
    });
  } else if (cpu.usage > CONFIG.alertThresholds.cpu.warning) {
    alerts.push({
      type: 'warning',
      source: 'cpu',
      message: `CPU usage high: ${cpu.usage}%`,
      timestamp: new Date().toISOString()
    });
  }
  
  for (const disk of disks) {
    if (disk.usePercent > CONFIG.alertThresholds.disk.critical) {
      alerts.push({
        type: 'critical',
        source: 'disk',
        message: `Disk ${disk.mountpoint} critical: ${disk.usePercent}%`,
        timestamp: new Date().toISOString()
      });
    } else if (disk.usePercent > CONFIG.alertThresholds.disk.warning) {
      alerts.push({
        type: 'warning',
        source: 'disk',
        message: `Disk ${disk.mountpoint} high: ${disk.usePercent}%`,
        timestamp: new Date().toISOString()
      });
    }
  }
  
  return alerts;
}

function updateHistory() {
  const system = getSystemStats();
  const cpu = getCPUUsage();
  const disks = getDiskStats();
  
  historyData.memory.push({ time: Date.now(), value: system.percent });
  historyData.cpu.push({ time: Date.now(), value: cpu.usage });
  
  const avgDiskUsage = disks.length > 0 
    ? Math.round(disks.reduce((sum, d) => sum + d.usePercent, 0) / disks.length)
    : 0;
  historyData.disk.push({ time: Date.now(), value: avgDiskUsage });
  
  // Keep only last N data points
  if (historyData.memory.length > CONFIG.historySize) {
    historyData.memory.shift();
    historyData.cpu.shift();
    historyData.disk.shift();
  }
}

function getAPIResponse() {
  updateHistory();
  
  return JSON.stringify({
    timestamp: new Date().toISOString(),
    system: getSystemStats(),
    cpu: getCPUUsage(),
    disks: getDiskStats(),
    processes: getProcessList(),
    watchdog: getWatchdogStatus(),
    storageManager: getStorageManagerStatus(),
    cloudStorage: getCloudStorageStatus(),
    alerts: getAlerts(),
    history: historyData
  });
}

const HTML = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Watchdog Pro Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
      color: #e0e0e0;
      padding: 20px;
      min-height: 100vh;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 30px;
      padding: 20px;
      background: rgba(255,255,255,0.05);
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.1);
    }
    .header h1 {
      font-size: 28px;
      font-weight: 700;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .status-badge {
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .status-online { background: rgba(0,255,136,0.2); color: #00ff88; }
    .status-offline { background: rgba(255,85,85,0.2); color: #ff5555; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
      gap: 20px;
      margin-bottom: 20px;
    }
    .card {
      background: rgba(255,255,255,0.05);
      border-radius: 16px;
      padding: 24px;
      border: 1px solid rgba(255,255,255,0.1);
      backdrop-filter: blur(10px);
    }
    .card-title {
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #888;
      margin-bottom: 16px;
      font-weight: 600;
    }
    .metric {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 12px 0;
      padding: 12px;
      background: rgba(255,255,255,0.03);
      border-radius: 8px;
    }
    .metric-label { color: #aaa; font-size: 13px; }
    .metric-value { font-size: 16px; font-weight: 600; color: #fff; }
    .progress-bar {
      height: 8px;
      border-radius: 4px;
      background: rgba(255,255,255,0.1);
      overflow: hidden;
      margin-top: 8px;
    }
    .progress-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.5s ease;
    }
    .progress-good { background: linear-gradient(90deg, #00ff88, #00cc6a); }
    .progress-warning { background: linear-gradient(90deg, #ffaa00, #ff8800); }
    .progress-critical { background: linear-gradient(90deg, #ff5555, #ff3333); }
    .chart-container {
      height: 200px;
      margin-top: 16px;
    }
    .table {
      width: 100%;
      border-collapse: collapse;
    }
    .table th, .table td {
      padding: 12px;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .table th {
      font-size: 12px;
      text-transform: uppercase;
      color: #888;
      font-weight: 600;
    }
    .table td { font-size: 13px; }
    .alert-item {
      padding: 12px;
      margin: 8px 0;
      border-radius: 8px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .alert-critical { background: rgba(255,85,85,0.2); border-left: 4px solid #ff5555; }
    .alert-warning { background: rgba(255,170,0,0.2); border-left: 4px solid #ffaa00; }
    .alert-icon { font-size: 20px; }
    .cloud-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px;
      margin: 8px 0;
      background: rgba(255,255,255,0.03);
      border-radius: 8px;
    }
    .cloud-status {
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }
    .cloud-running { background: rgba(0,255,136,0.2); color: #00ff88; }
    .cloud-stopped { background: rgba(255,85,85,0.2); color: #ff5555; }
    .cloud-not_installed { background: rgba(100,100,100,0.2); color: #888; }
    .refresh-btn {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      border: none;
      color: white;
      padding: 10px 20px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      transition: transform 0.2s;
    }
    .refresh-btn:hover { transform: scale(1.05); }
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡️ Watchdog Pro Dashboard</h1>
    <div>
      <span id="watchdog-status" class="status-badge status-offline">Watchdog: Checking...</span>
      <span id="storage-status" class="status-badge status-offline" style="margin-left: 10px;">Storage: Checking...</span>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">System Resources</div>
      <div class="metric">
        <span class="metric-label">Memory</span>
        <span class="metric-value" id="memory-value">...</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill progress-good" id="memory-bar" style="width: 0%"></div>
      </div>
      <div class="metric">
        <span class="metric-label">CPU Usage</span>
        <span class="metric-value" id="cpu-value">...</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill progress-good" id="cpu-bar" style="width: 0%"></div>
      </div>
      <div class="metric">
        <span class="metric-label">Load Average</span>
        <span class="metric-value" id="load-value">...</span>
      </div>
      <div class="metric">
        <span class="metric-label">Uptime</span>
        <span class="metric-value" id="uptime-value">...</span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Real-time Charts</div>
      <div class="chart-container">
        <canvas id="resourceChart"></canvas>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Disk Usage</div>
      <div id="disk-list"></div>
    </div>

    <div class="card">
      <div class="card-title">Top Processes</div>
      <table class="table">
        <thead>
          <tr>
            <th>Process</th>
            <th>CPU</th>
            <th>Memory</th>
          </tr>
        </thead>
        <tbody id="process-list"></tbody>
      </table>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Cloud Storage</div>
      <div id="cloud-list"></div>
    </div>

    <div class="card">
      <div class="card-title">Active Alerts</div>
      <div id="alert-list"></div>
    </div>
  </div>

  <script>
    let resourceChart;
    
    function initChart() {
      const ctx = document.getElementById('resourceChart').getContext('2d');
      resourceChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            {
              label: 'Memory %',
              data: [],
              borderColor: '#667eea',
              backgroundColor: 'rgba(102,126,234,0.1)',
              tension: 0.4,
              fill: true
            },
            {
              label: 'CPU %',
              data: [],
              borderColor: '#00ff88',
              backgroundColor: 'rgba(0,255,136,0.1)',
              tension: 0.4,
              fill: true
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: '#888' }
            }
          },
          scales: {
            x: {
              ticks: { color: '#888' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            },
            y: {
              ticks: { color: '#888' },
              grid: { color: 'rgba(255,255,255,0.05)' },
              min: 0,
              max: 100
            }
          }
        }
      });
    }
    
    function updateProgress(element, value) {
      const bar = document.getElementById(element);
      bar.style.width = value + '%';
      bar.className = 'progress-fill ' + (value < 80 ? 'progress-good' : value < 92 ? 'progress-warning' : 'progress-critical');
    }
    
    async function loadData() {
      try {
        const res = await fetch('/api/data');
        const data = await res.json();
        
        // System Resources
        document.getElementById('memory-value').textContent = data.system.usedmem + 'MB / ' + data.system.totalmem + 'MB (' + data.system.percent + '%)';
        updateProgress('memory-bar', data.system.percent);
        
        document.getElementById('cpu-value').textContent = data.cpu.usage + '%';
        updateProgress('cpu-bar', data.cpu.usage);
        
        document.getElementById('load-value').textContent = data.system.loadavg.map(x => x.toFixed(2)).join(' / ');
        const uptime = data.system.uptime;
        document.getElementById('uptime-value').textContent = Math.floor(uptime / 3600) + 'h ' + Math.floor((uptime % 3600) / 60) + 'm';
        
        // Status Badges
        const wdStatus = document.getElementById('watchdog-status');
        wdStatus.textContent = 'Watchdog: ' + (data.watchdog.running ? 'Running' : 'Stopped');
        wdStatus.className = 'status-badge ' + (data.watchdog.running ? 'status-online' : 'status-offline');
        
        const stStatus = document.getElementById('storage-status');
        stStatus.textContent = 'Storage: ' + (data.storageManager.running ? 'Active' : 'Inactive');
        stStatus.className = 'status-badge ' + (data.storageManager.running ? 'status-online' : 'status-offline');
        
        // Update Chart
        if (resourceChart) {
          const labels = data.history.memory.map((_, i) => i);
          resourceChart.data.labels = labels;
          resourceChart.data.datasets[0].data = data.history.memory.map(d => d.value);
          resourceChart.data.datasets[1].data = data.history.cpu.map(d => d.value);
          resourceChart.update('none');
        }
        
        // Disk Usage
        const diskList = document.getElementById('disk-list');
        diskList.innerHTML = '';
        data.disks.forEach(disk => {
          const div = document.createElement('div');
          div.innerHTML = \`
            <div class="metric">
              <span class="metric-label">\${disk.mountpoint}</span>
              <span class="metric-value">\${disk.used} / \${disk.size} (\${disk.usePercent}%)</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill \${disk.usePercent < 80 ? 'progress-good' : disk.usePercent < 92 ? 'progress-warning' : 'progress-critical'}" style="width: \${disk.usePercent}%"></div>
            </div>
          \`;
          diskList.appendChild(div);
        });
        
        // Top Processes
        const processList = document.getElementById('process-list');
        processList.innerHTML = '';
        data.processes.slice(0, 8).forEach(proc => {
          const row = document.createElement('tr');
          row.innerHTML = \`
            <td>\${proc.name}</td>
            <td>\${proc.cpuPercent.toFixed(1)}%</td>
            <td>\${proc.memMB}MB</td>
          \`;
          processList.appendChild(row);
        });
        
        // Cloud Storage
        const cloudList = document.getElementById('cloud-list');
        cloudList.innerHTML = '';
        data.cloudStorage.forEach(cloud => {
          const div = document.createElement('div');
          div.className = 'cloud-item';
          div.innerHTML = \`
            <span>\${cloud.name}</span>
            <span class="cloud-status cloud-\${cloud.status}">\${cloud.status}</span>
          \`;
          cloudList.appendChild(div);
        });
        
        // Alerts
        const alertList = document.getElementById('alert-list');
        alertList.innerHTML = '';
        if (data.alerts.length === 0) {
          alertList.innerHTML = '<div style="color: #00ff88; padding: 12px;">✓ No active alerts</div>';
        } else {
          data.alerts.forEach(alert => {
            const div = document.createElement('div');
            div.className = 'alert-item alert-' + alert.type;
            div.innerHTML = \`
              <span class="alert-icon">\${alert.type === 'critical' ? '⚠️' : '⚡'}</span>
              <span>\${alert.message}</span>
            \`;
            alertList.appendChild(div);
          });
        }
        
      } catch (e) {
        console.error('Load failed:', e);
      }
    }
    
    initChart();
    loadData();
    setInterval(loadData, 2000);
  </script>
</body>
</html>`;

const server = http.createServer((req, res) => {
  if (req.url === '/api/data') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(getAPIResponse());
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(HTML);
  }
});

server.listen(PORT, () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(`🛡️ Watchdog Pro Dashboard running on http://localhost:${PORT}`);
});
