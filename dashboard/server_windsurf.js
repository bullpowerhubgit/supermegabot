#!/usr/bin/env node
/**
 * SuperMegaBot Unified Dashboard Server
 * Ein Server. Ein Dashboard. Alle Daten.
 * Port: 9002
 */

import http from 'http';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PORT = 9002;

const SERVICES = [
  { name: 'Ollama AI', port: 11434, status: 'optional', checkPath: '/api/tags' },
  { name: 'n8n Workflows', port: 5678, status: 'optional' },
  { name: 'Netdata', port: 19999, status: 'optional' },
  { name: 'Mega Dashboard (alt)', port: 8889, status: 'optional' },
  { name: 'Super Server', port: 9001, status: 'running' },
  { name: 'Watchdog', port: null, status: 'running', meta: 'Memory Monitor' },
  { name: 'QuickCash Backend', port: 3001, status: 'optional' },
  { name: 'Shopify Sync', port: null, status: 'running', meta: 'API' },
  { name: 'Telegram Bot', port: null, status: 'running', meta: 'Webhook' },
  { name: 'DeepScan Scheduler', port: null, status: 'running', meta: 'Cron' },
];

class UnifiedServer {
  constructor() {
    this.history = { memory: [], cpu: [], disk: [] };
    this.maxHistory = 60;
  }

  log(msg) {
    const line = `[${new Date().toISOString()}] ${msg}`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line);
    try { fs.appendFileSync('/tmp/unified-dashboard.log', line + '\n'); } catch (e) {}
  }

  async getSystemStats() {
    try {
      const { stdout } = await execAsync('vm_stat');
      const pageSize = 16384;
      let free = 0, wired = 0, active = 0, inactive = 0, compressed = 0;
      const mFree = stdout.match(/Pages free:\s+(\d+)/);
      const mWired = stdout.match(/Pages wired down:\s+(\d+)/);
      const mActive = stdout.match(/Pages active:\s+(\d+)/);
      const mInactive = stdout.match(/Pages inactive:\s+(\d+)/);
      const mComp = stdout.match(/Pages compressed:\s+(\d+)/);
      if (mFree) free = parseInt(mFree[1]) * pageSize;
      if (mWired) wired = parseInt(mWired[1]) * pageSize;
      if (mActive) active = parseInt(mActive[1]) * pageSize;
      if (mInactive) inactive = parseInt(mInactive[1]) * pageSize;
      if (mComp) compressed = parseInt(mComp[1]) * pageSize;
      const used = active + inactive + wired + compressed;
      const total = os.totalmem();
      return {
        total: Math.round(total / 1024 / 1024),
        used: Math.round(used / 1024 / 1024),
        free: Math.round(free / 1024 / 1024),
        percent: Math.round((used / total) * 100)
      };
    } catch (e) {
      const total = os.totalmem();
      const free = os.freemem();
      return {
        total: Math.round(total / 1024 / 1024),
        used: Math.round((total - free) / 1024 / 1024),
        free: Math.round(free / 1024 / 1024),
        percent: Math.round(((total - free) / total) * 100)
      };
    }
  }

  async getCPU() {
    try {
      const { stdout } = await execAsync("ps -A -o %cpu | awk '{s+=$1} END {print s}'");
      const cores = os.cpus().length;
      const raw = parseFloat(stdout.trim()) || 0;
      // ps %cpu on macOS sums across processes; normalize by core count
      const normalized = Math.min(Math.round(raw / cores), 100);
      return { usage: normalized, cores };
    } catch (e) { return { usage: 0, cores: os.cpus().length }; }
  }

  async getDisks() {
    const disks = [];
    try {
      const { stdout } = await execAsync('df -H');
      const lines = stdout.trim().split('\n').slice(1);
      for (const line of lines) {
        const p = line.trim().split(/\s+/);
        if (p.length >= 9 && p[0].startsWith('/dev/')) {
          const mount = p[8];
          if (mount && (mount.startsWith('/Volumes/') || mount === '/')) {
            disks.push({
              filesystem: p[0], size: p[1], used: p[2], available: p[3],
              usePercent: parseInt(p[4]) || 0, mountpoint: mount,
              type: mount === '/' ? 'internal' : 'external',
              name: mount === '/' ? 'Macintosh HD' : mount.replace('/Volumes/', '')
            });
          }
        }
      }
    } catch (e) {}
    return disks;
  }

  async getProcesses() {
    try {
      const { stdout } = await execAsync('ps -axm -o comm,pmem,pcpu | head -7');
      return stdout.trim().split('\n').slice(1).map(line => {
        const parts = line.trim().split(/\s+/);
        return { name: parts[0], memPercent: parseFloat(parts[1]) || 0, cpuPercent: parseFloat(parts[2]) || 0 };
      });
    } catch (e) { return []; }
  }

  async getNetwork() {
    try {
      const { stdout } = await execAsync('netstat -an | grep ESTABLISHED | wc -l');
      return { connections: parseInt(stdout.trim()) || 0 };
    } catch (e) { return { connections: 0 }; }
  }

  async getCloud() {
    const svcs = [];
    const checks = [
      { name: 'Google Drive', cmd: 'ps aux | grep -i "google drive" | grep -v grep' },
      { name: 'Dropbox', cmd: 'ps aux | grep -i dropbox | grep -v grep' },
      { name: 'OneDrive', cmd: 'ps aux | grep -i onedrive | grep -v grep' },
      { name: 'iCloud Drive', cmd: 'ps aux | grep -i "cloudd" | grep -v grep' },
    ];
    for (const c of checks) {
      try { await execAsync(c.cmd); svcs.push({ name: c.name, status: 'running' }); }
      catch { svcs.push({ name: c.name, status: 'stopped' }); }
    }
    return svcs;
  }

  async getAlerts() {
    const alerts = [];
    const [mem, cpu, disks] = await Promise.all([this.getSystemStats(), this.getCPU(), this.getDisks()]);
    if (mem.percent > 95) alerts.push({ type: 'critical', source: 'memory', message: `RAM kritisch: ${mem.percent}%`, timestamp: new Date().toISOString() });
    else if (mem.percent > 90) alerts.push({ type: 'warning', source: 'memory', message: `RAM hoch: ${mem.percent}%`, timestamp: new Date().toISOString() });
    if (cpu.usage > 90) alerts.push({ type: 'critical', source: 'cpu', message: `CPU kritisch: ${cpu.usage}%`, timestamp: new Date().toISOString() });
    else if (cpu.usage > 70) alerts.push({ type: 'warning', source: 'cpu', message: `CPU hoch: ${cpu.usage}%`, timestamp: new Date().toISOString() });
    for (const d of disks) {
      if (d.usePercent > 90) alerts.push({ type: 'critical', source: 'disk', message: `${d.name} voll: ${d.usePercent}%`, timestamp: new Date().toISOString() });
      else if (d.usePercent > 75) alerts.push({ type: 'warning', source: 'disk', message: `${d.name} fast voll: ${d.usePercent}%`, timestamp: new Date().toISOString() });
    }
    return alerts;
  }

  async getServices() {
    const results = [];
    for (const s of SERVICES) {
      results.push({ name: s.name, port: s.port, status: s.status, meta: s.meta || (s.port ? `Port ${s.port}` : '') });
    }
    return results;
  }

  readDashboardHtml() {
    try {
      return fs.readFileSync(path.join(__dirname, 'unified-mega-dashboard.html'), 'utf8');
    } catch (e) { return '<h1>Dashboard HTML not found</h1>'; }
  }

  async handle(req, res) {
    const url = new URL(req.url, `http://${req.headers.host}`);
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Content-Type', 'application/json');

    if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

    try {
      switch (url.pathname) {
        case '/':
        case '/dashboard':
          res.setHeader('Content-Type', 'text/html');
          res.writeHead(200);
          res.end(this.readDashboardHtml());
          return;
        case '/api/system':
          const [memory, cpu, network] = await Promise.all([this.getSystemStats(), this.getCPU(), this.getNetwork()]);
          res.writeHead(200);
          res.end(JSON.stringify({ memory, cpu, network, uptime: Math.round(os.uptime() / 3600), platform: os.platform(), hostname: os.hostname() }));
          return;
        case '/api/disks':
          res.writeHead(200); res.end(JSON.stringify(await this.getDisks())); return;
        case '/api/processes':
          res.writeHead(200); res.end(JSON.stringify(await this.getProcesses())); return;
        case '/api/services':
          res.writeHead(200); res.end(JSON.stringify(await this.getServices())); return;
        case '/api/alerts':
          res.writeHead(200); res.end(JSON.stringify(await this.getAlerts())); return;
        case '/api/cloud':
          res.writeHead(200); res.end(JSON.stringify(await this.getCloud())); return;
        case '/api/health':
          res.writeHead(200); res.end(JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() })); return;
        case '/api/cleanup':
          if (req.method === 'POST') {
            try { await execAsync('pkill -f "zsh" || true'); }
            catch (e) {}
            res.writeHead(200); res.end(JSON.stringify({ message: 'Cleanup ausgeführt' })); return;
          }
          break;
        case '/api/all':
          const [sys, dsk, proc, svc, alrt, cld] = await Promise.all([
            this.getSystemStats(), this.getDisks(), this.getProcesses(),
            this.getServices(), this.getAlerts(), this.getCloud()
          ]);
          const cpu2 = await this.getCPU();
          const net2 = await this.getNetwork();
          res.writeHead(200);
          res.end(JSON.stringify({
            system: { memory: sys, cpu: cpu2, network: net2, uptime: Math.round(os.uptime() / 3600) },
            disks: dsk, processes: proc, services: svc, alerts: alrt, cloud: cld,
            timestamp: new Date().toISOString()
          }));
          return;
      }
      res.writeHead(404); res.end(JSON.stringify({ error: 'Not found' }));
    } catch (e) {
      this.log(`Error: ${e.message}`);
      res.writeHead(500); res.end(JSON.stringify({ error: e.message }));
    }
  }

  start() {
    const server = http.createServer((req, res) => this.handle(req, res));
    server.listen(PORT, () => {
      this.log(`Unified Dashboard Server running on http://localhost:${PORT}`);
      this.log(`Dashboard: http://localhost:${PORT}/dashboard`);
    });
  }
}

const srv = new UnifiedServer();
srv.start();
