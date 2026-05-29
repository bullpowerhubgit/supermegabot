#!/usr/bin/env node

/**
 * RudiBot Mega Dashboard Backend
 * Einheitliches System für alle macOS Tools
 * Cloud Backup, Monitoring, DeepScan, OpenAI
 */

import http from 'http';
import fs from 'fs';
import path from 'path';
import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import os from 'os';
import gcpConfig from './lib/gcp-config.js';

const execAsync = promisify(exec);

const PORT = 8889;
const DATA_DIR = path.join(os.homedir(), 'RudiBot-Data');
const BACKUP_DIR = path.join(DATA_DIR, 'backups');

// Ensure directories exist
[DATA_DIR, BACKUP_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// System status cache
let systemStatus = {
  lastUpdate: Date.now(),
  memory: {},
  cpu: {},
  disk: {},
  processes: [],
  uptime: 0,
  alerts: []
};

// Tool status
const toolStatus = {
  deepscan: { running: false, lastRun: null, issues: [] },
  monitoring: { running: false, metrics: {} },
  watchdog: { running: false, restarts: 0 },
  openai: { running: false, requests: 0 },
  backup: { running: false, lastBackup: null },
  macoptimizer: { running: false, lastRun: null },
  telegram: { running: false, lastMessage: null },
  shopify: { running: false, lastSync: null },
  gcp: { running: false, projectId: gcpConfig.projectId, apis: gcpConfig.apiList }
};

// Tool command mapping for start/stop/restart
const TOOL_COMMANDS = {
  watchdog: { pm2Name: 'watchdog', script: 'watchdog-v2.js', type: 'pm2' },
  deepscan: { pm2Name: 'deepscan', script: 'deep-scan-fix.js', type: 'node' },
  monitoring: { pm2Name: 'monitor', script: 'professional-desktop-monitor.js', type: 'pm2' },
  backup: { pm2Name: 'backup', script: 'auto-backup-scheduler.js', type: 'pm2' },
  telegram: { pm2Name: 'telegram', script: 'test-notification.js', type: 'pm2' },
  shopify: { pm2Name: 'shopify', script: 'webhook-validator.js', type: 'pm2' },
  macoptimizer: { pm2Name: 'macoptimizer', script: 'mac-optimizer.py', type: 'python' },
  openai: { pm2Name: null, script: null, type: 'integrated' }
};

// PM2 Services Status
async function getPM2Status() {
  try {
    const { stdout } = await execAsync('pm2 jlist 2>/dev/null');
    const processes = JSON.parse(stdout);
    return processes.map(p => ({
      name: p.name,
      status: p.pm2_env.status,
      pid: p.pid,
      restarts: p.pm2_env.restart_time,
      memory: p.monit ? p.monit.memory : 0,
      cpu: p.monit ? p.monit.cpu : 0,
      uptime: p.pm2_env.pm_uptime
    }));
  } catch (error) {
    return [];
  }
}

// Mac Optimizer Status
async function getMacOptimizerStatus() {
  try {
    const { stdout } = await execAsync('ps aux | grep mac-optimizer | grep -v grep');
    return { running: stdout.length > 0, details: stdout };
  } catch {
    return { running: false };
  }
}

// Network Status
async function getNetworkStatus() {
  try {
    const { stdout: connections } = await execAsync('netstat -an | grep ESTABLISHED | wc -l').catch(() => ({ stdout: '0' }));
    const { stdout: interfaces } = await execAsync('ifconfig | grep "inet " | head -3').catch(() => ({ stdout: '' }));
    return {
      connections: parseInt(connections.trim()) || 0,
      interfaces: interfaces.split('\n').filter(l => l.trim())
    };
  } catch {
    return { connections: 0, interfaces: [] };
  }
}

async function getSystemMetrics() {
  // Memory always works via os module
  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const usedMem = totalMem - freeMem;

  const memory = {
    total: Math.round(totalMem / 1024 / 1024),
    used: Math.round(usedMem / 1024 / 1024),
    free: Math.round(freeMem / 1024 / 1024),
    percent: totalMem > 0 ? Math.round((usedMem / totalMem) * 100) : 0
  };

  // CPU
  let cpu;
  try {
    const loadAvg = os.loadavg();
    const cpus = os.cpus();
    cpu = {
      load: loadAvg.map(l => Math.round(l * 100) / 100),
      cores: cpus.length,
      model: cpus[0]?.model || 'Unknown'
    };
  } catch (e) {
    cpu = { load: [0, 0, 0], cores: 1, model: 'Unknown' };
  }

  // Disk usage - individual catch
  let disk = { size: 'N/A', used: 'N/A', available: 'N/A', percent: 'N/A' };
  try {
    const { stdout } = await execAsync('df -h /');
    const lines = stdout.trim().split('\n');
    if (lines[1]) {
      const parts = lines[1].split(/\s+/);
      disk = {
        size: parts[1] || 'N/A',
        used: parts[2] || 'N/A',
        available: parts[3] || 'N/A',
        percent: parts[4] || 'N/A'
      };
    }
  } catch (e) {
    // Keep defaults
  }

  // Top processes
  let processes = '';
  try {
    const { stdout } = await execAsync('ps -axm -o pid,comm,pmem,rss | head -6');
    processes = stdout;
  } catch (e) {
    // ignore
  }

  return {
    memory,
    cpu,
    disk,
    processes,
    uptime: Math.round(os.uptime() / 3600),
    platform: os.platform(),
    hostname: os.hostname(),
    timestamp: new Date().toISOString()
  };
}

async function runDeepScan() {
  toolStatus.deepscan.running = true;
  const scanId = Date.now().toString();
  
  try {
    const files = fs.readdirSync(process.cwd())
      .filter(f => f.endsWith('.js') || f.endsWith('.json'))
      .slice(0, 10);
    
    const issues = [];
    
    for (const file of files) {
      try {
        const content = fs.readFileSync(path.join(process.cwd(), file), 'utf8');
        
        // Check for common issues
        if (content.includes('====')) {
          issues.push({ file, type: 'syntax', message: 'Potential ==== operator', severity: 'high' });
        }
        if (content.includes('console.log') && content.length > 5000) {
          issues.push({ file, type: 'performance', message: 'Large file with console.log statements', severity: 'low' });
        }
        if (content.includes('TODO') || content.includes('FIXME')) {
          issues.push({ file, type: 'maintenance', message: 'Contains TODO/FIXME markers', severity: 'medium' });
        }
      } catch (e) {}
    }
    
    toolStatus.deepscan.lastRun = new Date().toISOString();
    toolStatus.deepscan.issues = issues;
    
    return { scanId, issues, scanned: files.length, timestamp: toolStatus.deepscan.lastRun };
  } catch (error) {
    return { scanId, error: error.message };
  } finally {
    toolStatus.deepscan.running = false;
  }
}

async function performBackup() {
  toolStatus.backup.running = true;
  
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupFile = path.join(BACKUP_DIR, `backup-${timestamp}.json`);
    
    const backupData = {
      timestamp: new Date().toISOString(),
      hostname: os.hostname(),
      system: {
        platform: os.platform(),
        release: os.release(),
        arch: os.arch()
      },
      files: [],
      toolStatus: toolStatus,
      envVars: Object.keys(process.env).filter(k => !k.includes('SECRET') && !k.includes('KEY') && !k.includes('TOKEN'))
    };
    
    // Backup important files
    const filesToBackup = ['watchdog-v2.js', 'mega-dashboard-backend.js', 'deep-scan-fix.js'];
    for (const file of filesToBackup) {
      try {
        const content = fs.readFileSync(path.join(process.cwd(), file), 'utf8');
        backupData.files.push({ name: file, size: content.length, content: content.substring(0, 1000) });
      } catch (e) {}
    }
    
    fs.writeFileSync(backupFile, JSON.stringify(backupData, null, 2));
    
    toolStatus.backup.lastBackup = new Date().toISOString();
    
    return { success: true, file: backupFile, size: fs.statSync(backupFile).size };
  } catch (error) {
    return { success: false, error: error.message };
  } finally {
    toolStatus.backup.running = false;
  }
}

async function getBackups() {
  try {
    const files = fs.readdirSync(BACKUP_DIR)
      .filter(f => f.endsWith('.json'))
      .map(f => {
        const stat = fs.statSync(path.join(BACKUP_DIR, f));
        return { name: f, size: stat.size, date: stat.mtime };
      })
      .sort((a, b) => b.date - a.date)
      .slice(0, 10);
    
    return files;
  } catch (error) {
    return [];
  }
}

// HTTP Server
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json');
  
  const url = new URL(req.url, `http://localhost:${PORT}`);
  
  try {
    switch (url.pathname) {
      case '/api/status':
        systemStatus = await getSystemMetrics();
        const pm2Status = await getPM2Status();
        const macOptimizer = await getMacOptimizerStatus();
        const network = await getNetworkStatus();
        
        // Update tool status
        toolStatus.monitoring.running = pm2Status.some(p => p.name === 'professional-desktop-monitor' && p.status === 'online');
        toolStatus.backup.running = pm2Status.some(p => p.name === 'cloud-backup-scheduler' && p.status === 'online');
        toolStatus.watchdog.running = pm2Status.some(p => p.name.includes('watchdog') && p.status === 'online');
        toolStatus.telegram.running = pm2Status.some(p => p.name.includes('telegram') && p.status === 'online');
        toolStatus.shopify.running = pm2Status.some(p => p.name.includes('shopify') && p.status === 'online');
        toolStatus.deepscan.running = pm2Status.some(p => p.name.includes('deepscan') && p.status === 'online');
        toolStatus.macoptimizer.running = macOptimizer.running;
        
        res.writeHead(200);
        res.end(JSON.stringify({ 
          status: 'ok', 
          system: systemStatus, 
          tools: toolStatus,
          pm2: pm2Status,
          network: network,
          timestamp: new Date().toISOString()
        }));
        break;
        
      case '/api/pm2':
        const pm2Data = await getPM2Status();
        res.writeHead(200);
        res.end(JSON.stringify({ processes: pm2Data }));
        break;
        
      case '/api/pm2/restart':
        const targetProcess = url.searchParams.get('name');
        try {
          await execAsync(`pm2 restart ${targetProcess}`);
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, message: `Restarted ${targetProcess}` }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        }
        break;
        
      case '/api/pm2/stop':
        const stopProcess = url.searchParams.get('name');
        try {
          await execAsync(`pm2 stop ${stopProcess}`);
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, message: `Stopped ${stopProcess}` }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        }
        break;
        
      case '/api/deepscan':
        const scanResult = await runDeepScan();
        res.writeHead(200);
        res.end(JSON.stringify(scanResult));
        break;
        
      case '/api/backup':
        const backupResult = await performBackup();
        res.writeHead(200);
        res.end(JSON.stringify(backupResult));
        break;
        
      case '/api/backups':
        const backups = await getBackups();
        res.writeHead(200);
        res.end(JSON.stringify({ backups }));
        break;
        
      case '/api/cleanup':
        try {
          await execAsync('purge').catch(() => {});
          await execAsync('dscacheutil -flushcache').catch(() => {});
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, message: 'Cleanup performed' }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        }
        break;
        
      case '/api/start-tool': {
        const tool = url.searchParams.get('tool');
        const toolConfig = TOOL_COMMANDS[tool];
        let result;
        try {
          if (!toolConfig) {
            result = { success: false, error: 'Unknown tool: ' + tool };
          } else if (toolConfig.type === 'integrated') {
            result = { success: true, message: 'OpenAI is integrated into other tools', tool };
          } else if (toolConfig.type === 'pm2') {
            try {
              await execAsync(`pm2 start ${toolConfig.script} --name ${toolConfig.pm2Name}`);
              result = { success: true, message: `Started ${tool} via PM2`, tool };
            } catch (e) {
              // Might already be running, try restart
              await execAsync(`pm2 restart ${toolConfig.pm2Name}`);
              result = { success: true, message: `Restarted ${tool} via PM2`, tool };
            }
          } else if (toolConfig.type === 'node') {
            spawn('node', [toolConfig.script], { detached: true, stdio: 'ignore' }).unref();
            result = { success: true, message: `Started ${tool}`, tool };
          } else if (toolConfig.type === 'python') {
            spawn('python3', [toolConfig.script], { detached: true, stdio: 'ignore' }).unref();
            result = { success: true, message: `Started ${tool}`, tool };
          }
        } catch (e) {
          result = { success: false, error: e.message, tool };
        }
        res.writeHead(200);
        res.end(JSON.stringify(result));
        break;
      }

      case '/api/stop-tool': {
        const stopTool = url.searchParams.get('tool');
        const stopConfig = TOOL_COMMANDS[stopTool];
        let stopResult;
        try {
          if (!stopConfig) {
            stopResult = { success: false, error: 'Unknown tool: ' + stopTool };
          } else if (stopConfig.type === 'integrated') {
            stopResult = { success: true, message: 'OpenAI cannot be stopped separately', tool: stopTool };
          } else if (stopConfig.type === 'pm2') {
            await execAsync(`pm2 stop ${stopConfig.pm2Name}`);
            stopResult = { success: true, message: `Stopped ${stopTool} via PM2`, tool: stopTool };
          } else {
            await execAsync(`pkill -f "${stopConfig.script}"`);
            stopResult = { success: true, message: `Stopped ${stopTool}`, tool: stopTool };
          }
        } catch (e) {
          stopResult = { success: false, error: e.message, tool: stopTool };
        }
        res.writeHead(200);
        res.end(JSON.stringify(stopResult));
        break;
      }
        
      default:
        // Serve static HTML
        if (url.pathname === '/' || url.pathname === '/index.html') {
          res.setHeader('Content-Type', 'text/html');
          res.writeHead(200);
          res.end(getDashboardHTML());
        } else {
          res.writeHead(404);
          res.end(JSON.stringify({ error: 'Not found' }));
        }
    }
  } catch (error) {
    res.writeHead(500);
    res.end(JSON.stringify({ error: error.message }));
  }
});

function getDashboardHTML() {
  return `<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RudiBot Mega Dashboard - macOS Control Center</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px;
            border-bottom: 2px solid #e94560;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { color: #e94560; font-size: 24px; }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #00ff88;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2d3a5c;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(233, 69, 96, 0.2);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .card-title { font-size: 18px; color: #fff; }
        .card-icon { font-size: 24px; }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #2d3a5c;
        }
        .metric:last-child { border-bottom: none; }
        .metric-value { color: #e94560; font-weight: bold; }
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #2d3a5c;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s;
        }
        .progress-fill.high { background: #ff4757; }
        .progress-fill.medium { background: #ffa502; }
        .progress-fill.low { background: #2ed573; }
        .btn {
            background: linear-gradient(135deg, #e94560 0%, #ff6b81 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            margin: 5px;
            transition: all 0.3s;
        }
        .btn:hover {
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(233, 69, 96, 0.4);
        }
        .btn-secondary {
            background: linear-gradient(135deg, #2d3a5c 0%, #3d4a6c 100%);
        }
        .btn-success {
            background: linear-gradient(135deg, #2ed573 0%, #7bed9f 100%);
        }
        .log-container {
            background: #0a0a1a;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #2d3a5c;
        }
        .log-entry {
            padding: 4px 0;
            border-bottom: 1px solid #1a1a2e;
        }
        .log-entry.info { color: #74b9ff; }
        .log-entry.warn { color: #ffa502; }
        .log-entry.error { color: #ff4757; }
        .log-entry.success { color: #2ed573; }
        .tool-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .tool-card {
            background: #1a1a2e;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid #2d3a5c;
            cursor: pointer;
            transition: all 0.3s;
        }
        .tool-card:hover {
            border-color: #e94560;
            transform: scale(1.02);
        }
        .tool-card.active {
            border-color: #2ed573;
            box-shadow: 0 0 20px rgba(46, 213, 115, 0.3);
        }
        .tool-icon { font-size: 36px; margin-bottom: 10px; }
        .tool-name { font-size: 16px; font-weight: bold; margin-bottom: 5px; }
        .tool-status { font-size: 12px; color: #888; }
        .alert-banner {
            background: linear-gradient(135deg, #ff4757 0%, #ff6348 100%);
            color: white;
            padding: 15px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: none;
        }
        .alert-banner.show { display: block; }
        .refresh-time {
            font-size: 12px;
            color: #888;
            text-align: right;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>RudiBot Mega Dashboard</h1>
            <small>macOS System Control Center</small>
        </div>
        <div>
            <span class="status-indicator"></span>
            <span>System Online</span>
        </div>
    </div>
    
    <div class="container">
        <div id="alertBanner" class="alert-banner">
            <strong>System Alert!</strong> <span id="alertMessage"></span>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Memory Usage</span>
                    <span class="card-icon">💾</span>
                </div>
                <div class="metric">
                    <span>Used</span>
                    <span class="metric-value" id="memUsed">--</span>
                </div>
                <div class="metric">
                    <span>Free</span>
                    <span class="metric-value" id="memFree">--</span>
                </div>
                <div class="metric">
                    <span>Total</span>
                    <span class="metric-value" id="memTotal">--</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill low" id="memBar" style="width: 0%"></div>
                </div>
                <div class="refresh-time" id="memPercent">--%</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">CPU Status</span>
                    <span class="card-icon">⚡</span>
                </div>
                <div class="metric">
                    <span>Load (1m)</span>
                    <span class="metric-value" id="cpuLoad1">--</span>
                </div>
                <div class="metric">
                    <span>Load (5m)</span>
                    <span class="metric-value" id="cpuLoad5">--</span>
                </div>
                <div class="metric">
                    <span>Cores</span>
                    <span class="metric-value" id="cpuCores">--</span>
                </div>
                <div class="refresh-time" id="cpuModel">--</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Disk Usage</span>
                    <span class="card-icon">💿</span>
                </div>
                <div class="metric">
                    <span>Size</span>
                    <span class="metric-value" id="diskSize">--</span>
                </div>
                <div class="metric">
                    <span>Used</span>
                    <span class="metric-value" id="diskUsed">--</span>
                </div>
                <div class="metric">
                    <span>Available</span>
                    <span class="metric-value" id="diskAvail">--</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill low" id="diskBar" style="width: 0%"></div>
                </div>
                <div class="refresh-time" id="diskPercent">--%</div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">System Info</span>
                    <span class="card-icon">🖥️</span>
                </div>
                <div class="metric">
                    <span>Uptime</span>
                    <span class="metric-value" id="uptime">--</span>
                </div>
                <div class="metric">
                    <span>Platform</span>
                    <span class="metric-value" id="platform">--</span>
                </div>
                <div class="metric">
                    <span>Hostname</span>
                    <span class="metric-value" id="hostname">--</span>
                </div>
                <div class="refresh-time" id="timestamp">--</div>
            </div>
        </div>
        
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header">
                <span class="card-title">Quick Actions</span>
                <span class="card-icon">🚀</span>
            </div>
            <div style="display: flex; flex-wrap: wrap;">
                <button class="btn" onclick="runDeepScan()">🔍 DeepScan</button>
                <button class="btn btn-secondary" onclick="runCleanup()">🧹 Memory Cleanup</button>
                <button class="btn btn-success" onclick="runBackup()">💾 Cloud Backup</button>
                <button class="btn btn-secondary" onclick="showBackups()">📁 View Backups</button>
                <button class="btn" onclick="refreshAll()">🔄 Refresh</button>
            </div>
            <div id="actionResult" class="log-container" style="margin-top: 15px; display: none;"></div>
        </div>
        
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header">
                <span class="card-title">System Tools</span>
                <span class="card-icon">🛠️</span>
            </div>
            <div class="tool-grid">
                <div class="tool-card" id="watchdogCard" onclick="toggleTool('watchdog')">
                    <div class="tool-icon">🐕</div>
                    <div class="tool-name">Watchdog</div>
                    <div class="tool-status" id="watchdogStatus">Checking...</div>
                </div>
                <div class="tool-card" id="deepscanCard" onclick="toggleTool('deepscan')">
                    <div class="tool-icon">🔍</div>
                    <div class="tool-name">DeepScan</div>
                    <div class="tool-status" id="deepscanStatus">Checking...</div>
                </div>
                <div class="tool-card" id="monitoringCard" onclick="toggleTool('monitoring')">
                    <div class="tool-icon">📊</div>
                    <div class="tool-name">Monitor</div>
                    <div class="tool-status" id="monitoringStatus">Checking...</div>
                </div>
                <div class="tool-card" id="backupCard" onclick="toggleTool('backup')">
                    <div class="tool-icon">💾</div>
                    <div class="tool-name">Cloud Backup</div>
                    <div class="tool-status" id="backupStatus">Checking...</div>
                </div>
                <div class="tool-card" id="telegramCard" onclick="toggleTool('telegram')">
                    <div class="tool-icon">📱</div>
                    <div class="tool-name">Telegram</div>
                    <div class="tool-status" id="telegramStatus">Checking...</div>
                </div>
                <div class="tool-card" id="shopifyCard" onclick="toggleTool('shopify')">
                    <div class="tool-icon">🛒</div>
                    <div class="tool-name">Shopify</div>
                    <div class="tool-status" id="shopifyStatus">Checking...</div>
                </div>
                <div class="tool-card" id="macoptimizerCard" onclick="toggleTool('macoptimizer')">
                    <div class="tool-icon">🍎</div>
                    <div class="tool-name">Mac Optimizer</div>
                    <div class="tool-status" id="macoptimizerStatus">Checking...</div>
                </div>
                <div class="tool-card" id="openaiCard" onclick="toggleTool('openai')">
                    <div class="tool-icon">🤖</div>
                    <div class="tool-name">AI Agents</div>
                    <div class="tool-status" id="openaiStatus">Checking...</div>
                </div>
            </div>
        </div>
        
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header">
                <span class="card-title">PM2 Services Management</span>
                <span class="card-icon">⚙️</span>
            </div>
            <div id="pm2Container">
                <div class="log-container" id="pm2List">
                    <div class="log-entry info">Loading PM2 services...</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">System Logs</span>
                <span class="card-icon">📋</span>
            </div>
            <div class="log-container" id="logContainer">
                <div class="log-entry info">[System] Dashboard initialized</div>
            </div>
        </div>
    </div>
    
    <script>
        const logContainer = document.getElementById('logContainer');
        
        function addLog(message, type = 'info') {
            const entry = document.createElement('div');
            entry.className = \`log-entry \${type}\`;
            entry.textContent = \`[\${new Date().toLocaleTimeString()}] \${message}\`;
            logContainer.insertBefore(entry, logContainer.firstChild);
            if (logContainer.children.length > 50) {
                logContainer.removeChild(logContainer.lastChild);
            }
        }
        
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                const data = await response.json();

                if (!data.system) {
                    addLog('No system data received', 'warn');
                    return;
                }

                const sys = data.system;

                // Memory
                if (sys.memory) {
                    document.getElementById('memUsed').textContent = sys.memory.used + ' MB';
                    document.getElementById('memFree').textContent = sys.memory.free + ' MB';
                    document.getElementById('memTotal').textContent = sys.memory.total + ' MB';
                    document.getElementById('memPercent').textContent = sys.memory.percent + '%';
                    document.getElementById('memBar').style.width = sys.memory.percent + '%';
                    document.getElementById('memBar').className = 'progress-fill ' +
                        (sys.memory.percent > 90 ? 'high' : sys.memory.percent > 70 ? 'medium' : 'low');
                }

                // CPU
                if (sys.cpu) {
                    document.getElementById('cpuLoad1').textContent = (sys.cpu.load && sys.cpu.load[0] !== undefined) ? sys.cpu.load[0] : '--';
                    document.getElementById('cpuLoad5').textContent = (sys.cpu.load && sys.cpu.load[1] !== undefined) ? sys.cpu.load[1] : '--';
                    document.getElementById('cpuCores').textContent = sys.cpu.cores || '--';
                    document.getElementById('cpuModel').textContent = (sys.cpu.model || '--').substring(0, 30);
                }

                // Disk
                if (sys.disk) {
                    document.getElementById('diskSize').textContent = sys.disk.size || '--';
                    document.getElementById('diskUsed').textContent = sys.disk.used || '--';
                    document.getElementById('diskAvail').textContent = sys.disk.available || '--';
                    document.getElementById('diskPercent').textContent = sys.disk.percent || '--';
                    const diskPct = parseInt(sys.disk.percent) || 0;
                    document.getElementById('diskBar').style.width = diskPct + '%';
                    document.getElementById('diskBar').className = 'progress-fill ' +
                        (diskPct > 90 ? 'high' : diskPct > 70 ? 'medium' : 'low');
                }

                // System Info
                document.getElementById('uptime').textContent = (sys.uptime !== undefined ? sys.uptime : '--') + 'h';
                document.getElementById('platform').textContent = sys.platform || '--';
                document.getElementById('hostname').textContent = sys.hostname || '--';
                document.getElementById('timestamp').textContent = sys.timestamp ? new Date(sys.timestamp).toLocaleString() : '--';

                // Alerts
                if (sys.memory && sys.memory.percent > 90) {
                    showAlert('Critical RAM usage: ' + sys.memory.percent + '%');
                }

                // Tool status
                if (data.tools) {
                    for (const [tool, status] of Object.entries(data.tools)) {
                        const el = document.getElementById(tool + 'Status');
                        if (el) {
                            el.textContent = status.running ? 'Running' : 'Idle';
                            const card = document.getElementById(tool + 'Card');
                            if (card) {
                                if (status.running) card.classList.add('active');
                                else card.classList.remove('active');
                            }
                        }
                    }
                }

                // PM2 Services
                if (data.pm2) {
                    updatePM2List(data.pm2);
                }

                addLog('Metrics updated', 'info');
            } catch (error) {
                addLog('Failed to fetch status: ' + error.message, 'error');
                showAlert('Dashboard connection lost: ' + error.message);
            }
        }
        
        function updatePM2List(processes) {
            const container = document.getElementById('pm2List');
            if (!processes || processes.length === 0) {
                container.innerHTML = '<div class="log-entry warn">No PM2 services running</div>';
                return;
            }
            
            let html = '';
            processes.forEach(p => {
                const statusClass = p.status === 'online' ? 'success' : p.status === 'errored' ? 'error' : 'warn';
                const memMB = Math.round(p.memory / 1024 / 1024);
                html += '<div class="log-entry ' + statusClass + '" style="display: flex; justify-content: space-between; align-items: center; padding: 8px;">' +
                    '<span><strong>' + p.name + '</strong> (PID: ' + (p.pid || 'N/A') + ')</span>' +
                    '<span style="color: #888;">CPU: ' + (p.cpu || 0) + '% | MEM: ' + memMB + 'MB | Restarts: ' + (p.restarts || 0) + '</span>' +
                    '<span style="color: ' + (p.status === 'online' ? '#2ed573' : '#ff4757') + '">' + p.status + '</span>' +
                    '<div>' +
                        '<button class="btn" style="padding: 4px 8px; font-size: 11px; margin: 2px;" onclick="restartPM2Service(\'' + p.name + '\')">🔄 Restart</button>' +
                        '<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px; margin: 2px;" onclick="stopPM2Service(\'' + p.name + '\')">⏹️ Stop</button>' +
                    '</div>' +
                '</div>';
            });
            container.innerHTML = html;
        }
        
        async function restartPM2Service(name) {
            addLog('Restarting PM2 service: ' + name, 'info');
            try {
                const response = await fetch('/api/pm2/restart?name=' + encodeURIComponent(name));
                const data = await response.json();
                if (data.success) {
                    addLog(data.message, 'success');
                } else {
                    addLog(data.error, 'error');
                }
                setTimeout(fetchStatus, 2000);
            } catch (error) {
                addLog('Failed to restart: ' + error.message, 'error');
            }
        }
        
        async function stopPM2Service(name) {
            addLog('Stopping PM2 service: ' + name, 'info');
            try {
                const response = await fetch('/api/pm2/stop?name=' + encodeURIComponent(name));
                const data = await response.json();
                if (data.success) {
                    addLog(data.message, 'success');
                } else {
                    addLog(data.error, 'error');
                }
                setTimeout(fetchStatus, 2000);
            } catch (error) {
                addLog('Failed to stop: ' + error.message, 'error');
            }
        }
        
        function showAlert(message) {
            const banner = document.getElementById('alertBanner');
            document.getElementById('alertMessage').textContent = message;
            banner.classList.add('show');
            setTimeout(() => banner.classList.remove('show'), 10000);
        }
        
        async function runDeepScan() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Scanning...';
            addLog('Starting DeepScan...', 'info');
            const resultDiv = document.getElementById('actionResult');
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="log-entry info">🔍 Scanning files...</div>';
            
            try {
                const response = await fetch('/api/deepscan');
                const data = await response.json();
                
                let html = '<div class="log-entry success">Scan completed!</div>';
                html += '<div class="log-entry info">Scanned: ' + data.scanned + ' files</div>';
                html += '<div class="log-entry ' + (data.issues.length ? 'warn' : 'success') + '">Issues found: ' + data.issues.length + '</div>';
                
                data.issues.forEach(issue => {
                    html += '<div class="log-entry warn">[' + issue.severity + '] ' + issue.file + ': ' + issue.message + '</div>';
                });
                
                resultDiv.innerHTML = html;
                addLog('DeepScan completed: ' + data.issues.length + ' issues found', data.issues.length ? 'warn' : 'success');
            } catch (error) {
                resultDiv.innerHTML = '<div class="log-entry error">Error: ' + error.message + '</div>';
                addLog('DeepScan failed: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🔍 DeepScan';
            }
        }
        
        async function runCleanup() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Cleaning...';
            addLog('Running memory cleanup...', 'info');
            const resultDiv = document.getElementById('actionResult');
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="log-entry info">🧹 Running cleanup...</div>';
            
            try {
                const response = await fetch('/api/cleanup');
                const data = await response.json();
                resultDiv.innerHTML = '<div class="log-entry ' + (data.success ? 'success' : 'error') + '">' + data.message + '</div>';
                addLog(data.message, data.success ? 'success' : 'error');
            } catch (error) {
                resultDiv.innerHTML = '<div class="log-entry error">Cleanup failed: ' + error.message + '</div>';
                addLog('Cleanup failed: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🧹 Memory Cleanup';
            }
        }
        
        async function runBackup() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Backing up...';
            addLog('Creating cloud backup...', 'info');
            const resultDiv = document.getElementById('actionResult');
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="log-entry info">💾 Creating backup...</div>';
            
            try {
                const response = await fetch('/api/backup');
                const data = await response.json();
                
                if (data.success) {
                    resultDiv.innerHTML = '<div class="log-entry success">Backup created!</div><div class="log-entry info">File: ' + data.file + '</div><div class="log-entry info">Size: ' + data.size + ' bytes</div>';
                    addLog('Backup created: ' + data.file, 'success');
                } else {
                    resultDiv.innerHTML = '<div class="log-entry error">Backup failed: ' + data.error + '</div>';
                    addLog('Backup failed: ' + data.error, 'error');
                }
            } catch (error) {
                resultDiv.innerHTML = '<div class="log-entry error">Error: ' + error.message + '</div>';
                addLog('Backup error: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '💾 Cloud Backup';
            }
        }
        
        async function showBackups() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Loading...';
            const resultDiv = document.getElementById('actionResult');
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div class="log-entry info">📁 Loading backups...</div>';
            
            try {
                const response = await fetch('/api/backups');
                const data = await response.json();
                
                if (data.backups && data.backups.length) {
                    let html = '<div class="log-entry success">Found ' + data.backups.length + ' backups</div>';
                    data.backups.forEach(b => {
                        html += '<div class="log-entry info">' + b.name + ' (' + b.size + ' bytes, ' + new Date(b.date).toLocaleString() + ')</div>';
                    });
                    resultDiv.innerHTML = html;
                    addLog('Loaded ' + data.backups.length + ' backups', 'success');
                } else {
                    resultDiv.innerHTML = '<div class="log-entry warn">No backups found</div>';
                    addLog('No backups found', 'warn');
                }
            } catch (error) {
                resultDiv.innerHTML = '<div class="log-entry error">Error: ' + error.message + '</div>';
                addLog('Failed to load backups: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '📁 View Backups';
            }
        }
        
        async function toggleTool(tool) {
            const statusEl = document.getElementById(tool + 'Status');
            const card = document.getElementById(tool + 'Card');
            const isRunning = card && card.classList.contains('active');
            
            statusEl.textContent = isRunning ? 'Stopping...' : 'Starting...';
            addLog((isRunning ? 'Stopping' : 'Starting') + ' tool: ' + tool, 'info');
            
            try {
                const endpoint = isRunning ? '/api/stop-tool?tool=' : '/api/start-tool?tool=';
                const response = await fetch(endpoint + encodeURIComponent(tool));
                const data = await response.json();
                
                if (data.success) {
                    addLog(data.message, 'success');
                    statusEl.textContent = isRunning ? 'Idle' : 'Running';
                    if (card) {
                        if (isRunning) card.classList.remove('active');
                        else card.classList.add('active');
                    }
                } else {
                    addLog(data.error || 'Failed', 'error');
                    statusEl.textContent = isRunning ? 'Running' : 'Idle';
                }
                
                setTimeout(fetchStatus, 2000);
            } catch (error) {
                addLog('Tool toggle failed: ' + error.message, 'error');
                statusEl.textContent = 'Error';
            }
        }
        
        async function refreshAll() {
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '⏳ Refreshing...';
            addLog('Refreshing all data...', 'info');
            await fetchStatus();
            btn.disabled = false;
            btn.textContent = '🔄 Refresh';
        }
        
        // Auto refresh every 10 seconds

        setInterval(fetchStatus, 10000);
        
        // Initial fetch
        fetchStatus();
        addLog('Dashboard initialized and ready', 'success');
    </script>
</body>
</html>`;
}

server.listen(PORT, () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(`RudiBot Mega Dashboard running at http://localhost:${PORT}`);
});
