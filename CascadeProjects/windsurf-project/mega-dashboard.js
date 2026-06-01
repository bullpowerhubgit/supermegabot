#!/usr/bin/env node

/**
 * RudiBot Mega Dashboard - ALLE TOOLS IN EINER DATEI
 * Port: 8889
 * Features: Monitoring, Watchdog, DeepScan, Backup, Mac Optimizer, Memory Cleanup, PM2 Management
 */

import http from 'http';
import fs from 'fs';
import path from 'path';
import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import os from 'os';
import crypto from 'crypto';

const execAsync = promisify(exec);

const PORT = 8889;
const DATA_DIR = path.join(os.homedir(), 'RudiBot-Data');
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
const LOG_FILE = path.join(DATA_DIR, 'dashboard.log');
const PID_FILE = path.join('/tmp', 'rudibot-dashboard.pid');

[DATA_DIR, BACKUP_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

function log(level, message) {
  const ts = new Date().toISOString();
  const line = `[${ts}] [${level.toUpperCase()}] ${message}\n`;
  try { fs.appendFileSync(LOG_FILE, line); } catch (e) {}
}

// ========================================================================
// INTEGRATED TOOL CLASSES
// ========================================================================

class SystemMonitor {
  async getMetrics() {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const usedMem = totalMem - freeMem;

    const memory = {
      total: Math.round(totalMem / 1024 / 1024),
      used: Math.round(usedMem / 1024 / 1024),
      free: Math.round(freeMem / 1024 / 1024),
      percent: totalMem > 0 ? Math.round((usedMem / totalMem) * 100) : 0
    };

    let cpu;
    try {
      const loadAvg = os.loadavg();
      const cpus = os.cpus();
      cpu = { load: loadAvg.map(l => Math.round(l * 100) / 100), cores: cpus.length, model: cpus[0]?.model || 'Unknown' };
    } catch (e) { cpu = { load: [0, 0, 0], cores: 1, model: 'Unknown' }; }

    let disk = { size: 'N/A', used: 'N/A', available: 'N/A', percent: 'N/A' };
    try {
      const { stdout } = await execAsync('df -h /');
      const parts = stdout.trim().split('\n')[1]?.split(/\s+/) || [];
      if (parts.length >= 5) disk = { size: parts[1], used: parts[2], available: parts[3], percent: parts[4] };
    } catch (e) {}

    let processes = '';
    try {
      const { stdout } = await execAsync('ps -axm -o pid,comm,pmem,rss | head -6');
      processes = stdout;
    } catch (e) {}

    let network = { connections: 0, interfaces: [] };
    try {
      const { stdout: conn } = await execAsync('netstat -an | grep ESTABLISHED | wc -l').catch(() => ({ stdout: '0' }));
      const { stdout: ifaces } = await execAsync('ifconfig | grep "inet " | head -3').catch(() => ({ stdout: '' }));
      network = { connections: parseInt(conn.trim()) || 0, interfaces: ifaces.split('\n').filter(l => l.trim()) };
    } catch (e) {}

    return {
      memory, cpu, disk, processes, network,
      uptime: Math.round(os.uptime() / 3600),
      platform: os.platform(),
      hostname: os.hostname(),
      timestamp: new Date().toISOString()
    };
  }
}

class SmartWatchdog {
  constructor() {
    this.running = false;
    this.interval = 30000;
    this.memoryThreshold = 80;
    this.criticalThreshold = 92;
    this.timer = null;
    this.memoryHistory = [];
    this.maxHistory = 20;
    this.lastCleanup = 0;
    this.cleanupCooldown = 120000;
  }

  start() {
    if (this.running) return;
    this.running = true;
    log('info', 'Watchdog started');
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    log('info', 'Watchdog stopped');
  }

  async tick() {
    try {
      const total = os.totalmem();
      const free = os.freemem();
      const percent = Math.round(((total - free) / total) * 100);
      this.memoryHistory.push({ percent, timestamp: Date.now() });
      if (this.memoryHistory.length > this.maxHistory) this.memoryHistory.shift();

      if (percent >= this.criticalThreshold) {
        log('critical', `RAM CRITICAL: ${percent}% - executing emergency cleanup`);
        await this.cleanup();
      } else if (percent >= this.memoryThreshold) {
        log('warn', `RAM HIGH: ${percent}% - cleanup advised`);
      }
    } catch (e) { log('error', `Watchdog tick error: ${e.message}`); }
  }

  async cleanup() {
    const now = Date.now();
    if (now - this.lastCleanup < this.cleanupCooldown) return;
    this.lastCleanup = now;
    try {
      await execAsync('purge').catch(() => {});
      await execAsync('dscacheutil -flushcache').catch(() => {});
      log('info', 'Watchdog cleanup executed');
    } catch (e) {}
  }

  getStatus() {
    return {
      running: this.running,
      lastReading: this.memoryHistory.length > 0 ? this.memoryHistory[this.memoryHistory.length - 1] : null,
      history: this.memoryHistory
    };
  }
}

class DeepScanner {
  constructor() {
    this.issues = [];
    this.scanned = 0;
  }

  async scan(targetDir = process.cwd()) {
    this.issues = [];
    this.scanned = 0;
    const files = this.getFiles(targetDir);
    for (const file of files) {
      try {
        await this.scanFile(file);
        this.scanned++;
      } catch (e) {}
    }
    return { issues: this.issues, scanned: this.scanned };
  }

  getFiles(dir, extensions = ['.js', '.json', '.py', '.md', '.sh']) {
    const results = [];
    try {
      const items = fs.readdirSync(dir);
      for (const item of items) {
        if (item.startsWith('.') || item === 'node_modules') continue;
        const full = path.join(dir, item);
        const stat = fs.statSync(full);
        if (stat.isDirectory()) {
          results.push(...this.getFiles(full, extensions));
        } else if (extensions.some(ext => item.endsWith(ext))) {
          results.push(full);
        }
      }
    } catch (e) {}
    return results.slice(0, 100);
  }

  async scanFile(file) {
    const content = fs.readFileSync(file, 'utf8');
    const rel = path.relative(process.cwd(), file);
    const lines = content.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const lineNo = i + 1;

      if (line.includes('====') && !line.includes('//')) {
        this.issues.push({ file: rel, line: lineNo, type: 'syntax', severity: 'high', message: 'Potential invalid operator ====' });
      }
      if (/console\.log\(/.test(line) && content.length > 10000) {
        this.issues.push({ file: rel, line: lineNo, type: 'performance', severity: 'low', message: 'console.log in large file' });
      }
      if (/eval\(|new Function\(/.test(line)) {
        this.issues.push({ file: rel, line: lineNo, type: 'security', severity: 'high', message: 'Dangerous eval/Function usage' });
      }
      if (/password|secret|token|api.?key/i.test(line) && /[\"\'][^\"\']{8,}[\"\']/.test(line)) {
        this.issues.push({ file: rel, line: lineNo, type: 'security', severity: 'medium', message: 'Possible hardcoded credential' });
      }
    }

    if (content.includes('TODO') || content.includes('FIXME')) {
      this.issues.push({ file: rel, line: 0, type: 'maintenance', severity: 'low', message: 'Contains TODO/FIXME markers' });
    }
    if (content.length > 500000) {
      this.issues.push({ file: rel, line: 0, type: 'performance', severity: 'medium', message: `Very large file (${(content.length/1024).toFixed(0)}KB)` });
    }
  }
}

class MacOptimizer {
  constructor() {
    this.actions = [];
    this.homeDir = os.homedir();
  }

  async optimize() {
    this.actions = [];
    await this.clearCaches();
    await this.cleanTempFiles();
    await this.purgeMemory();
    await this.cleanupDesktopDownloads();
    return { actions: this.actions, success: true };
  }

  async clearCaches() {
    try {
      await execAsync('rm -rf ~/Library/Caches/* 2>/dev/null || true');
      this.actions.push('Cleared Library caches');
    } catch (e) {}
    try {
      await execAsync('rm -rf /tmp/* 2>/dev/null || true');
      this.actions.push('Cleared /tmp directory');
    } catch (e) {}
    try {
      await execAsync('npm cache clean --force 2>/dev/null || true');
      this.actions.push('Cleared npm cache');
    } catch (e) {}
  }

  async cleanTempFiles() {
    const dirs = ['temp', '.tmp', 'logs'].map(d => path.join(process.cwd(), d));
    for (const dir of dirs) {
      if (fs.existsSync(dir)) {
        try { fs.rmSync(dir, { recursive: true, force: true }); this.actions.push(`Removed ${dir}`); } catch (e) {}
      }
    }
  }

  async purgeMemory() {
    try {
      await execAsync('purge 2>/dev/null || true');
      this.actions.push('Executed memory purge');
    } catch (e) {}
    try {
      await execAsync('dscacheutil -flushcache 2>/dev/null || true');
      this.actions.push('Flushed DNS cache');
    } catch (e) {}
  }

  async cleanupDesktopDownloads() {
    const desktop = path.join(this.homeDir, 'Desktop');
    const downloads = path.join(this.homeDir, 'Downloads');
    for (const dir of [desktop, downloads]) {
      if (!fs.existsSync(dir)) continue;
      try {
        const items = fs.readdirSync(dir);
        let moved = 0;
        for (const item of items) {
          if (item.startsWith('.')) continue;
          const full = path.join(dir, item);
          const stat = fs.statSync(full);
          const daysOld = (Date.now() - stat.mtime) / (1000 * 60 * 60 * 24);
          if (daysOld > 30) {
            const trash = path.join(os.homedir(), '.Trash', item);
            try { fs.renameSync(full, trash); moved++; } catch (e) {}
          }
        }
        if (moved > 0) this.actions.push(`Moved ${moved} old items from ${path.basename(dir)} to Trash`);
      } catch (e) {}
    }
  }
}

class BackupManager {
  async createBackup() {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const backupDir = path.join(BACKUP_DIR, `rudibot-full-${ts}`);
    fs.mkdirSync(backupDir, { recursive: true });

    const filesToBackup = [
      'mega-dashboard.js',
      'mega-dashboard-backend.js',
      'watchdog-v2.js',
      'deep-scan-fix.js',
      'mac-optimizer.py',
      'auto-backup-scheduler.js',
      'professional-desktop-monitor.js',
      'test-notification.js',
      'webhook-validator.js',
      '.env'
    ];

    const backedUp = [];
    for (const file of filesToBackup) {
      try {
        const src = path.join(process.cwd(), file);
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, path.join(backupDir, file));
          backedUp.push(file);
        }
      } catch (e) {}
    }

    const manifest = {
      timestamp: new Date().toISOString(),
      hostname: os.hostname(),
      platform: os.platform(),
      files: backedUp,
      totalSize: this.getFolderSize(backupDir)
    };
    fs.writeFileSync(path.join(backupDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

    return { success: true, dir: backupDir, files: backedUp, manifest };
  }

  getFolderSize(dir) {
    let size = 0;
    try {
      const items = fs.readdirSync(dir);
      for (const item of items) {
        const full = path.join(dir, item);
        const stat = fs.statSync(full);
        size += stat.isDirectory() ? this.getFolderSize(full) : stat.size;
      }
    } catch (e) {}
    return size;
  }

  getBackups() {
    try {
      return fs.readdirSync(BACKUP_DIR)
        .filter(d => d.startsWith('rudibot-full-'))
        .map(d => {
          const full = path.join(BACKUP_DIR, d);
          const stat = fs.statSync(full);
          return { name: d, size: this.getFolderSize(full), date: stat.mtime };
        })
        .sort((a, b) => b.date - a.date)
        .slice(0, 20);
    } catch (e) { return []; }
  }
}

// ========================================================================
// GLOBAL INSTANCES
// ========================================================================

const systemMonitor = new SystemMonitor();
const watchdog = new SmartWatchdog();
const deepScanner = new DeepScanner();
const macOptimizer = new MacOptimizer();
const backupManager = new BackupManager();

const toolStatus = {
  deepscan: { running: false, lastRun: null, issues: [] },
  monitoring: { running: true, metrics: {} },
  watchdog: { running: false, restarts: 0 },
  openai: { running: false, requests: 0 },
  backup: { running: false, lastBackup: null },
  macoptimizer: { running: false, lastRun: null },
  telegram: { running: false, lastMessage: null },
  shopify: { running: false, lastSync: null },
  gcp: { running: false, projectId: null, apis: [] }
};

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

async function getPM2Status() {
  try {
    const { stdout } = await execAsync('pm2 jlist 2>/dev/null');
    const processes = JSON.parse(stdout);
    return processes.map(p => ({
      name: p.name, status: p.pm2_env.status, pid: p.pid,
      restarts: p.pm2_env.restart_time,
      memory: p.monit ? p.monit.memory : 0,
      cpu: p.monit ? p.monit.cpu : 0,
      uptime: p.pm2_env.pm_uptime
    }));
  } catch (error) { return []; }
}

async function getMacOptimizerStatus() {
  try {
    const { stdout } = await execAsync('ps aux | grep mac-optimizer | grep -v grep');
    return { running: stdout.length > 0, details: stdout };
  } catch { return { running: false }; }
}

// ========================================================================
// HTTP SERVER
// ========================================================================

const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  try {
    switch (url.pathname) {
      case '/':
      case '/index.html': {
        res.setHeader('Content-Type', 'text/html');
        res.writeHead(200);
        res.end(getDashboardHTML());
        break;
      }

      case '/api/status': {
        res.setHeader('Content-Type', 'application/json');
        const sys = await systemMonitor.getMetrics();
        const pm2 = await getPM2Status();
        const macOpt = await getMacOptimizerStatus();

        toolStatus.monitoring.running = true;
        toolStatus.watchdog.running = watchdog.running;
        toolStatus.macoptimizer.running = macOpt.running;
        toolStatus.backup.running = pm2.some(p => p.name === 'cloud-backup-scheduler' && p.status === 'online');
        toolStatus.telegram.running = pm2.some(p => p.name.includes('telegram') && p.status === 'online');
        toolStatus.shopify.running = pm2.some(p => p.name.includes('shopify') && p.status === 'online');
        toolStatus.deepscan.running = toolStatus.deepscan.running;

        res.writeHead(200);
        res.end(JSON.stringify({ status: 'ok', system: sys, tools: toolStatus, pm2, timestamp: new Date().toISOString() }));
        break;
      }

      case '/api/pm2': {
        res.setHeader('Content-Type', 'application/json');
        const pm2Data = await getPM2Status();
        res.writeHead(200);
        res.end(JSON.stringify({ processes: pm2Data }));
        break;
      }

      case '/api/pm2/restart': {
        res.setHeader('Content-Type', 'application/json');
        const name = url.searchParams.get('name');
        try { await execAsync(`pm2 restart ${name}`); res.end(JSON.stringify({ success: true, message: `Restarted ${name}` })); }
        catch (e) { res.writeHead(500); res.end(JSON.stringify({ success: false, error: e.message })); }
        break;
      }

      case '/api/pm2/stop': {
        res.setHeader('Content-Type', 'application/json');
        const name = url.searchParams.get('name');
        try { await execAsync(`pm2 stop ${name}`); res.end(JSON.stringify({ success: true, message: `Stopped ${name}` })); }
        catch (e) { res.writeHead(500); res.end(JSON.stringify({ success: false, error: e.message })); }
        break;
      }

      case '/api/deepscan': {
        res.setHeader('Content-Type', 'application/json');
        toolStatus.deepscan.running = true;
        try {
          const result = await deepScanner.scan();
          toolStatus.deepscan.lastRun = new Date().toISOString();
          toolStatus.deepscan.issues = result.issues;
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, ...result, timestamp: toolStatus.deepscan.lastRun }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        } finally { toolStatus.deepscan.running = false; }
        break;
      }

      case '/api/backup': {
        res.setHeader('Content-Type', 'application/json');
        toolStatus.backup.running = true;
        try {
          const result = await backupManager.createBackup();
          toolStatus.backup.lastBackup = new Date().toISOString();
          res.writeHead(200);
          res.end(JSON.stringify(result));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        } finally { toolStatus.backup.running = false; }
        break;
      }

      case '/api/backups': {
        res.setHeader('Content-Type', 'application/json');
        try {
          const backups = backupManager.getBackups();
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, backups }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        }
        break;
      }

      case '/api/cleanup': {
        res.setHeader('Content-Type', 'application/json');
        try {
          const result = await macOptimizer.optimize();
          res.writeHead(200);
          res.end(JSON.stringify({ success: true, message: `Cleanup completed: ${result.actions.length} actions`, actions: result.actions }));
        } catch (e) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: e.message }));
        }
        break;
      }

      case '/api/watchdog/start': {
        res.setHeader('Content-Type', 'application/json');
        watchdog.start();
        res.writeHead(200);
        res.end(JSON.stringify({ success: true, message: 'Watchdog started', status: watchdog.getStatus() }));
        break;
      }

      case '/api/watchdog/stop': {
        res.setHeader('Content-Type', 'application/json');
        watchdog.stop();
        res.writeHead(200);
        res.end(JSON.stringify({ success: true, message: 'Watchdog stopped', status: watchdog.getStatus() }));
        break;
      }

      case '/api/watchdog/status': {
        res.setHeader('Content-Type', 'application/json');
        res.writeHead(200);
        res.end(JSON.stringify({ success: true, status: watchdog.getStatus() }));
        break;
      }

      case '/api/start-tool': {
        res.setHeader('Content-Type', 'application/json');
        const tool = url.searchParams.get('tool');
        const cfg = TOOL_COMMANDS[tool];
        let result;
        try {
          if (!cfg) result = { success: false, error: 'Unknown tool: ' + tool };
          else if (cfg.type === 'integrated') result = { success: true, message: 'OpenAI integrated', tool };
          else if (cfg.type === 'pm2') {
            try { await execAsync(`pm2 start ${cfg.script} --name ${cfg.pm2Name}`); result = { success: true, message: `Started ${tool}`, tool }; }
            catch (e) { await execAsync(`pm2 restart ${cfg.pm2Name}`); result = { success: true, message: `Restarted ${tool}`, tool }; }
          }
          else if (cfg.type === 'node') { spawn('node', [cfg.script], { detached: true, stdio: 'ignore' }).unref(); result = { success: true, message: `Started ${tool}`, tool }; }
          else if (cfg.type === 'python') { spawn('python3', [cfg.script], { detached: true, stdio: 'ignore' }).unref(); result = { success: true, message: `Started ${tool}`, tool }; }
        } catch (e) { result = { success: false, error: e.message, tool }; }
        res.writeHead(200);
        res.end(JSON.stringify(result));
        break;
      }

      case '/api/stop-tool': {
        res.setHeader('Content-Type', 'application/json');
        const st = url.searchParams.get('tool');
        const sc = TOOL_COMMANDS[st];
        let sr;
        try {
          if (!sc) sr = { success: false, error: 'Unknown tool: ' + st };
          else if (sc.type === 'integrated') sr = { success: true, message: 'OpenAI cannot be stopped separately', tool: st };
          else if (sc.type === 'pm2') { await execAsync(`pm2 stop ${sc.pm2Name}`); sr = { success: true, message: `Stopped ${st}`, tool: st }; }
          else { await execAsync(`pkill -f "${sc.script}"`); sr = { success: true, message: `Stopped ${st}`, tool: st }; }
        } catch (e) { sr = { success: false, error: e.message, tool: st }; }
        res.writeHead(200);
        res.end(JSON.stringify(sr));
        break;
      }

      default: {
        res.setHeader('Content-Type', 'application/json');
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'Not found' }));
      }
    }
  } catch (error) {
    res.setHeader('Content-Type', 'application/json');
    res.writeHead(500);
    res.end(JSON.stringify({ error: error.message }));
  }
});

// ========================================================================
// DASHBOARD HTML (INLINE)
// ========================================================================

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
  background: #0f0f23; color: #e0e0e0; min-height: 100vh;
}
.header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  padding: 20px; border-bottom: 2px solid #e94560;
  display: flex; justify-content: space-between; align-items: center;
}
.header h1 { color: #e94560; font-size: 24px; }
.status-indicator {
  display: inline-block; width: 12px; height: 12px; border-radius: 50%;
  background: #00ff88; animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
.grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px;
}
.card {
  background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
  border-radius: 12px; padding: 20px; border: 1px solid #2d3a5c;
  transition: transform 0.3s, box-shadow 0.3s;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(233,69,96,0.2); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
.card-title { font-size: 18px; color: #fff; }
.card-icon { font-size: 24px; }
.metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #2d3a5c; }
.metric:last-child { border-bottom: none; }
.metric-value { color: #e94560; font-weight: bold; }
.progress-bar { width: 100%; height: 8px; background: #2d3a5c; border-radius: 4px; overflow: hidden; margin-top: 5px; }
.progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
.progress-fill.high { background: #ff4757; }
.progress-fill.medium { background: #ffa502; }
.progress-fill.low { background: #2ed573; }
.btn {
  background: linear-gradient(135deg, #e94560 0%, #ff6b81 100%); color: white;
  border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer;
  font-size: 14px; margin: 5px; transition: all 0.3s;
}
.btn:hover { transform: scale(1.05); box-shadow: 0 5px 15px rgba(233,69,96,0.4); }
.btn-secondary { background: linear-gradient(135deg, #2d3a5c 0%, #3d4a6c 100%); }
.btn-success { background: linear-gradient(135deg, #2ed573 0%, #7bed9f 100%); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
.log-container {
  background: #0a0a1a; border-radius: 8px; padding: 15px;
  font-family: 'Courier New', monospace; font-size: 12px;
  max-height: 300px; overflow-y: auto; border: 1px solid #2d3a5c;
}
.log-entry { padding: 4px 0; border-bottom: 1px solid #1a1a2e; }
.log-entry.info { color: #74b9ff; }
.log-entry.warn { color: #ffa502; }
.log-entry.error { color: #ff4757; }
.log-entry.success { color: #2ed573; }
.tool-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
.tool-card {
  background: #1a1a2e; border-radius: 10px; padding: 20px; text-align: center;
  border: 1px solid #2d3a5c; cursor: pointer; transition: all 0.3s;
}
.tool-card:hover { border-color: #e94560; transform: scale(1.02); }
.tool-card.active { border-color: #2ed573; box-shadow: 0 0 20px rgba(46,213,115,0.3); }
.tool-icon { font-size: 36px; margin-bottom: 10px; }
.tool-name { font-size: 16px; font-weight: bold; margin-bottom: 5px; }
.tool-status { font-size: 12px; color: #888; }
.alert-banner {
  background: linear-gradient(135deg, #ff4757 0%, #ff6348 100%); color: white;
  padding: 15px 20px; border-radius: 10px; margin-bottom: 20px; display: none;
}
.alert-banner.show { display: block; }
.refresh-time { font-size: 12px; color: #888; text-align: right; margin-top: 10px; }
.issue-item {
  background: rgba(255,71,87,0.1); border-left: 3px solid #ff4757;
  padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 12px;
}
.issue-high { border-left-color: #ff4757; }
.issue-medium { border-left-color: #ffa502; }
.issue-low { border-left-color: #74b9ff; }
</style>
</head>
<body>
<div class="header">
  <div><h1>RudiBot Mega Dashboard</h1><small>macOS System Control Center - Alle Tools in Einem</small></div>
  <div><span class="status-indicator"></span><span> System Online</span></div>
</div>

<div class="container">
  <div id="alertBanner" class="alert-banner"><strong>System Alert!</strong> <span id="alertMessage"></span></div>

  <div class="grid">
    <div class="card">
      <div class="card-header"><span class="card-title">Memory Usage</span><span class="card-icon">💾</span></div>
      <div class="metric"><span>Used</span><span class="metric-value" id="memUsed">--</span></div>
      <div class="metric"><span>Free</span><span class="metric-value" id="memFree">--</span></div>
      <div class="metric"><span>Total</span><span class="metric-value" id="memTotal">--</span></div>
      <div class="progress-bar"><div class="progress-fill low" id="memBar" style="width:0%"></div></div>
      <div class="refresh-time" id="memPercent">--%</div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">CPU Status</span><span class="card-icon">⚡</span></div>
      <div class="metric"><span>Load (1m)</span><span class="metric-value" id="cpuLoad1">--</span></div>
      <div class="metric"><span>Load (5m)</span><span class="metric-value" id="cpuLoad5">--</span></div>
      <div class="metric"><span>Cores</span><span class="metric-value" id="cpuCores">--</span></div>
      <div class="refresh-time" id="cpuModel">--</div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Disk Usage</span><span class="card-icon">💿</span></div>
      <div class="metric"><span>Size</span><span class="metric-value" id="diskSize">--</span></div>
      <div class="metric"><span>Used</span><span class="metric-value" id="diskUsed">--</span></div>
      <div class="metric"><span>Available</span><span class="metric-value" id="diskAvail">--</span></div>
      <div class="progress-bar"><div class="progress-fill low" id="diskBar" style="width:0%"></div></div>
      <div class="refresh-time" id="diskPercent">--%</div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">System Info</span><span class="card-icon">🖥️</span></div>
      <div class="metric"><span>Uptime</span><span class="metric-value" id="uptime">--</span></div>
      <div class="metric"><span>Platform</span><span class="metric-value" id="platform">--</span></div>
      <div class="metric"><span>Hostname</span><span class="metric-value" id="hostname">--</span></div>
      <div class="refresh-time" id="timestamp">--</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:20px">
    <div class="card-header"><span class="card-title">Quick Actions</span><span class="card-icon">🚀</span></div>
    <div style="display:flex;flex-wrap:wrap">
      <button class="btn" id="btnDeepScan" onclick="runDeepScan()">🔍 DeepScan</button>
      <button class="btn btn-secondary" id="btnCleanup" onclick="runCleanup()">🧹 Memory Cleanup</button>
      <button class="btn btn-success" id="btnBackup" onclick="runBackup()">💾 Cloud Backup</button>
      <button class="btn btn-secondary" id="btnBackups" onclick="showBackups()">📁 Backups</button>
      <button class="btn" id="btnWatchdog" onclick="toggleWatchdog()">🐕 Watchdog</button>
      <button class="btn" id="btnRefresh" onclick="refreshAll()">🔄 Refresh</button>
    </div>
    <div id="actionResult" class="log-container" style="margin-top:15px;display:none"></div>
  </div>

  <div class="card" style="margin-bottom:20px">
    <div class="card-header"><span class="card-title">System Tools</span><span class="card-icon">🛠️</span></div>
    <div class="tool-grid">
      <div class="tool-card" id="watchdogCard" onclick="toggleTool('watchdog')">
        <div class="tool-icon">🐕</div><div class="tool-name">Watchdog</div><div class="tool-status" id="watchdogStatus">Checking...</div>
      </div>
      <div class="tool-card" id="deepscanCard" onclick="toggleTool('deepscan')">
        <div class="tool-icon">🔍</div><div class="tool-name">DeepScan</div><div class="tool-status" id="deepscanStatus">Checking...</div>
      </div>
      <div class="tool-card" id="monitoringCard" onclick="toggleTool('monitoring')">
        <div class="tool-icon">📊</div><div class="tool-name">Monitor</div><div class="tool-status" id="monitoringStatus">Checking...</div>
      </div>
      <div class="tool-card" id="backupCard" onclick="toggleTool('backup')">
        <div class="tool-icon">💾</div><div class="tool-name">Cloud Backup</div><div class="tool-status" id="backupStatus">Checking...</div>
      </div>
      <div class="tool-card" id="telegramCard" onclick="toggleTool('telegram')">
        <div class="tool-icon">📱</div><div class="tool-name">Telegram</div><div class="tool-status" id="telegramStatus">Checking...</div>
      </div>
      <div class="tool-card" id="shopifyCard" onclick="toggleTool('shopify')">
        <div class="tool-icon">🛒</div><div class="tool-name">Shopify</div><div class="tool-status" id="shopifyStatus">Checking...</div>
      </div>
      <div class="tool-card" id="macoptimizerCard" onclick="toggleTool('macoptimizer')">
        <div class="tool-icon">🍎</div><div class="tool-name">Mac Optimizer</div><div class="tool-status" id="macoptimizerStatus">Checking...</div>
      </div>
      <div class="tool-card" id="openaiCard" onclick="toggleTool('openai')">
        <div class="tool-icon">🤖</div><div class="tool-name">AI Agents</div><div class="tool-status" id="openaiStatus">Checking...</div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-bottom:20px">
    <div class="card-header"><span class="card-title">PM2 Services</span><span class="card-icon">⚙️</span></div>
    <div class="log-container" id="pm2List"><div class="log-entry info">Loading...</div></div>
  </div>

  <div class="card">
    <div class="card-header"><span class="card-title">System Logs</span><span class="card-icon">📋</span></div>
    <div class="log-container" id="logContainer"><div class="log-entry info">[System] Dashboard initialized</div></div>
  </div>
</div>

<script>
const logContainer = document.getElementById('logContainer');
function addLog(msg, type='info') {
  const entry = document.createElement('div');
  entry.className = 'log-entry ' + type;
  entry.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  logContainer.insertBefore(entry, logContainer.firstChild);
  if (logContainer.children.length > 50) logContainer.removeChild(logContainer.lastChild);
}
function showAlert(msg) { const b=document.getElementById('alertBanner'), m=document.getElementById('alertMessage'); m.textContent=msg; b.classList.add('show'); setTimeout(()=>b.classList.remove('show'),5000); }

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (!d.system) { addLog('No system data','warn'); return; }
    const s = d.system;

    if (s.memory) {
      document.getElementById('memUsed').textContent = s.memory.used + ' MB';
      document.getElementById('memFree').textContent = s.memory.free + ' MB';
      document.getElementById('memTotal').textContent = s.memory.total + ' MB';
      document.getElementById('memPercent').textContent = s.memory.percent + '%';
      document.getElementById('memBar').style.width = s.memory.percent + '%';
      document.getElementById('memBar').className = 'progress-fill ' + (s.memory.percent>90?'high':s.memory.percent>70?'medium':'low');
    }
    if (s.cpu) {
      document.getElementById('cpuLoad1').textContent = (s.cpu.load&&s.cpu.load[0]!==undefined)?s.cpu.load[0]:'--';
      document.getElementById('cpuLoad5').textContent = (s.cpu.load&&s.cpu.load[1]!==undefined)?s.cpu.load[1]:'--';
      document.getElementById('cpuCores').textContent = s.cpu.cores || '--';
      document.getElementById('cpuModel').textContent = (s.cpu.model||'--').substring(0,30);
    }
    if (s.disk) {
      document.getElementById('diskSize').textContent = s.disk.size||'--';
      document.getElementById('diskUsed').textContent = s.disk.used||'--';
      document.getElementById('diskAvail').textContent = s.disk.available||'--';
      document.getElementById('diskPercent').textContent = s.disk.percent||'--';
      const dp = parseInt(s.disk.percent)||0;
      document.getElementById('diskBar').style.width = dp+'%';
      document.getElementById('diskBar').className = 'progress-fill ' + (dp>90?'high':dp>70?'medium':'low');
    }
    document.getElementById('uptime').textContent = (s.uptime!==undefined?s.uptime:'--')+'h';
    document.getElementById('platform').textContent = s.platform||'--';
    document.getElementById('hostname').textContent = s.hostname||'--';
    document.getElementById('timestamp').textContent = s.timestamp?new Date(s.timestamp).toLocaleString():'--';

    if (s.memory && s.memory.percent>90) showAlert('Critical RAM: ' + s.memory.percent + '%');

    if (d.tools) {
      for (const [tool,status] of Object.entries(d.tools)) {
        const el = document.getElementById(tool+'Status');
        if (el) {
          el.textContent = status.running?'Running':'Idle';
          const card = document.getElementById(tool+'Card');
          if (card) { if (status.running) card.classList.add('active'); else card.classList.remove('active'); }
        }
      }
    }
    if (d.pm2) updatePM2List(d.pm2);
    addLog('Metrics updated','info');
  } catch (e) { addLog('Status fetch failed: '+e.message,'error'); showAlert('Connection lost'); }
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function createSafeElement(tag, className, text, style) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  if (style) Object.assign(el.style, style);
  return el;
}

function updatePM2List(processes) {
  const c = document.getElementById('pm2List');
  c.textContent = '';
  if (!processes || processes.length === 0) {
    c.appendChild(createSafeElement('div', 'log-entry warn', 'No PM2 services'));
    return;
  }
  processes.forEach(p => {
    const sc = p.status === 'online' ? 'success' : p.status === 'errored' ? 'error' : 'warn';
    const mem = Math.round(p.memory / 1024 / 1024);
    const row = createSafeElement('div', 'log-entry ' + sc, '', {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '8px'
    });
    const nameSpan = createSafeElement('span', '', '');
    const strong = createSafeElement('strong', '', p.name);
    nameSpan.appendChild(strong);
    nameSpan.appendChild(document.createTextNode(' (PID:' + (p.pid || 'N/A') + ')'));
    row.appendChild(nameSpan);
    const cpuSpan = createSafeElement('span', '', 'CPU:' + (p.cpu || 0) + '% MEM:' + mem + 'MB', { color: '#888' });
    row.appendChild(cpuSpan);
    const statusSpan = createSafeElement('span', '', p.status, {
      color: p.status === 'online' ? '#2ed573' : '#ff4757'
    });
    row.appendChild(statusSpan);
    const btnDiv = createSafeElement('div');
    const restartBtn = createSafeElement('button', 'btn', '🔄', {
      padding: '4px 8px',
      fontSize: '11px',
      margin: '2px'
    });
    restartBtn.onclick = () => restartPM2(p.name);
    const stopBtn = createSafeElement('button', 'btn btn-secondary', '⏹️', {
      padding: '4px 8px',
      fontSize: '11px',
      margin: '2px'
    });
    stopBtn.onclick = () => stopPM2(p.name);
    btnDiv.appendChild(restartBtn);
    btnDiv.appendChild(stopBtn);
    row.appendChild(btnDiv);
    c.appendChild(row);
  });
}

async function restartPM2(name){ addLog('Restarting '+name,'info'); try{ const r=await fetch('/api/pm2/restart?name='+encodeURIComponent(name)); const d=await r.json(); addLog(d.message,d.success?'success':'error'); setTimeout(fetchStatus,2000); }catch(e){addLog('Failed: '+e.message,'error');} }
async function stopPM2(name){ addLog('Stopping '+name,'info'); try{ const r=await fetch('/api/pm2/stop?name='+encodeURIComponent(name)); const d=await r.json(); addLog(d.message,d.success?'success':'error'); setTimeout(fetchStatus,2000); }catch(e){addLog('Failed: '+e.message,'error');} }

async function toggleWatchdog() {
  const btn = document.getElementById('btnWatchdog');
  const resultDiv = document.getElementById('actionResult');
  resultDiv.style.display = 'block';
  resultDiv.textContent = '';
  btn.disabled = true;
  const isRunning = document.getElementById('watchdogStatus').textContent === 'Running';
  try {
    const r = await fetch(isRunning ? '/api/watchdog/stop' : '/api/watchdog/start');
    const d = await r.json();
    resultDiv.appendChild(createSafeElement('div', 'log-entry ' + (d.success ? 'success' : 'error'), d.message));
    addLog(d.message, d.success ? 'success' : 'error');
    setTimeout(fetchStatus, 1000);
  } catch (e) {
    resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Error: ' + e.message));
  }
  finally { btn.disabled = false; btn.textContent = isRunning ? '🐕 Watchdog' : '🐕 Watchdog'; }
}

async function runDeepScan() {
  const btn = document.getElementById('btnDeepScan');
  const resultDiv = document.getElementById('actionResult');
  resultDiv.style.display = 'block';
  resultDiv.textContent = '';
  resultDiv.appendChild(createSafeElement('div', 'log-entry info', '🔍 Scanning...'));
  btn.disabled = true; btn.textContent = '⏳ Scanning...';
  try {
    const r = await fetch('/api/deepscan');
    const d = await r.json();
    resultDiv.textContent = '';
    if (d.success) {
      resultDiv.appendChild(createSafeElement('div', 'log-entry success', '✅ Scanned ' + d.scanned + ' files, ' + d.issues.length + ' issues found'));
      if (d.issues.length > 0) {
        d.issues.slice(0, 20).forEach(i => {
          resultDiv.appendChild(createSafeElement('div', 'issue-item issue-' + i.severity,
            '[' + i.severity.toUpperCase() + '] ' + i.file + ' L' + i.line + ': ' + i.message));
        });
        if (d.issues.length > 20) {
          resultDiv.appendChild(createSafeElement('div', 'log-entry warn', '...and ' + (d.issues.length - 20) + ' more issues'));
        }
      }
      addLog('DeepScan: ' + d.issues.length + ' issues in ' + d.scanned + ' files', 'success');
    } else {
      resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Scan failed'));
    }
  } catch (e) {
    resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Error: ' + e.message));
    addLog('DeepScan failed: ' + e.message, 'error');
  }
  finally { btn.disabled = false; btn.textContent = '🔍 DeepScan'; }
}

async function runCleanup() {
  const btn = document.getElementById('btnCleanup');
  const resultDiv = document.getElementById('actionResult');
  resultDiv.style.display = 'block';
  resultDiv.textContent = '';
  resultDiv.appendChild(createSafeElement('div', 'log-entry info', '🧹 Cleaning...'));
  btn.disabled = true; btn.textContent = '⏳ Cleaning...';
  try {
    const r = await fetch('/api/cleanup');
    const d = await r.json();
    resultDiv.textContent = '';
    resultDiv.appendChild(createSafeElement('div', 'log-entry ' + (d.success ? 'success' : 'error'), d.message));
    if (d.actions) d.actions.forEach(a => {
      resultDiv.appendChild(createSafeElement('div', 'log-entry info', '- ' + a));
    });
    addLog(d.message, d.success ? 'success' : 'error');
  } catch (e) {
    resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Cleanup failed: ' + e.message));
    addLog('Cleanup failed', 'error');
  }
  finally { btn.disabled = false; btn.textContent = '🧹 Memory Cleanup'; }
}

async function runBackup() {
  const btn = document.getElementById('btnBackup');
  const resultDiv = document.getElementById('actionResult');
  resultDiv.style.display = 'block';
  resultDiv.textContent = '';
  resultDiv.appendChild(createSafeElement('div', 'log-entry info', '💾 Creating backup...'));
  btn.disabled = true; btn.textContent = '⏳ Backing up...';
  try {
    const r = await fetch('/api/backup');
    const d = await r.json();
    resultDiv.textContent = '';
    resultDiv.appendChild(createSafeElement('div', 'log-entry ' + (d.success ? 'success' : 'error'),
      d.success ? '✅ Backup: ' + d.dir : '❌ ' + d.error));
    addLog(d.success ? 'Backup created: ' + d.dir : 'Backup failed', 'success');
  } catch (e) {
    resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Error: ' + e.message));
    addLog('Backup error', 'error');
  }
  finally { btn.disabled = false; btn.textContent = '💾 Cloud Backup'; }
}

async function showBackups() {
  const btn = document.getElementById('btnBackups');
  const resultDiv = document.getElementById('actionResult');
  resultDiv.style.display = 'block';
  resultDiv.textContent = '';
  resultDiv.appendChild(createSafeElement('div', 'log-entry info', '📁 Loading...'));
  btn.disabled = true; btn.textContent = '⏳ Loading...';
  try {
    const r = await fetch('/api/backups');
    const d = await r.json();
    resultDiv.textContent = '';
    if (d.success && d.backups && d.backups.length > 0) {
      resultDiv.appendChild(createSafeElement('div', 'log-entry success', d.backups.length + ' backups found'));
      d.backups.forEach(b => {
        resultDiv.appendChild(createSafeElement('div', 'log-entry info',
          b.name + ' (' + Math.round(b.size / 1024) + 'KB, ' + new Date(b.date).toLocaleString() + ')'));
      });
      addLog('Loaded ' + d.backups.length + ' backups', 'success');
    } else {
      resultDiv.appendChild(createSafeElement('div', 'log-entry warn', 'No backups found'));
      addLog('No backups', 'warn');
    }
  } catch (e) {
    resultDiv.appendChild(createSafeElement('div', 'log-entry error', 'Error: ' + e.message));
    addLog('Failed to load backups', 'error');
  }
  finally { btn.disabled = false; btn.textContent = '📁 Backups'; }
}

async function toggleTool(tool) {
  const statusEl = document.getElementById(tool+'Status');
  const card = document.getElementById(tool+'Card');
  const isRunning = card && card.classList.contains('active');
  statusEl.textContent = isRunning ? 'Stopping...' : 'Starting...';
  addLog((isRunning?'Stopping':'Starting')+' tool: '+tool,'info');
  try {
    const endpoint = isRunning ? '/api/stop-tool?tool=' : '/api/start-tool?tool=';
    const r = await fetch(endpoint + encodeURIComponent(tool));
    const d = await r.json();
    if (d.success) {
      addLog(d.message,'success');
      statusEl.textContent = isRunning ? 'Idle' : 'Running';
      if (card) { if (isRunning) card.classList.remove('active'); else card.classList.add('active'); }
    } else {
      addLog(d.error||'Failed','error');
      statusEl.textContent = isRunning ? 'Running' : 'Idle';
    }
    setTimeout(fetchStatus, 2000);
  } catch (e) { addLog('Toggle failed: '+e.message,'error'); statusEl.textContent = 'Error'; }
}

async function refreshAll() {
  const btn = document.getElementById('btnRefresh');
  btn.disabled = true; btn.textContent = '⏳ Refreshing...';
  addLog('Refreshing...','info');
  await fetchStatus();
  btn.disabled = false; btn.textContent = '🔄 Refresh';
}

setInterval(fetchStatus, 10000);
fetchStatus();
</script>
</body>
</html>`;
}

// ========================================================================
// START SERVER
// ========================================================================

server.listen(PORT, () => {
  log('info', `RudiBot Mega Dashboard running at http://localhost:${PORT}`);
  log('info', 'All tools integrated: Watchdog, DeepScan, Backup, Mac Optimizer, Memory Cleanup');
  try { fs.writeFileSync(PID_FILE, process.pid.toString()); } catch (e) {}
});

process.on('SIGINT', () => {
  log('info', 'Shutting down...');
  watchdog.stop();
  try { fs.unlinkSync(PID_FILE); } catch (e) {}
  server.close(() => process.exit(0));
});
