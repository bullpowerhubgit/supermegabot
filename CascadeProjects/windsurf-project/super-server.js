#!/usr/bin/env node
import http from 'http';
import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class SuperServer {
  constructor(port = 9001) {
    this.port = port;
    this.running = false;
    this.pidFile = '/tmp/super-server.pid';
    
    // Configuration
    this.config = {
      refreshInterval: 5000, // 5 seconds
      memoryThreshold: 80,
      criticalThreshold: 92,
      diskThreshold: 85,
      cleanupInterval: 3600000, // 1 hour
      cloudCheckInterval: 300000 // 5 minutes
    };
    
    // State
    this.history = {
      memory: [],
      cpu: [],
      disk: []
    };
    this.maxHistorySize = 60;
    this.lastCleanup = 0;
    this.lastCloudCheck = 0;
    
    // Import StorageManager
    this.storageManager = null;
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line.trim());
    try {
      fs.appendFileSync('/tmp/super-server.log', line);
    } catch (e) {}
  }

  // ========== System Monitoring ==========
  
  async getSystemStats() {
    try {
      const { stdout } = await execAsync('vm_stat');
      const pageSize = 16384;
      
      let freeMemory = os.freemem();
      let appMemory = 0;
      let wiredMemory = 0;
      let compressedMemory = 0;
      
      const matchFree = stdout.match(/Pages free:\s+(\d+)/);
      const matchWired = stdout.match(/Pages wired down:\s+(\d+)/);
      const matchActive = stdout.match(/Pages active:\s+(\d+)/);
      const matchInactive = stdout.match(/Pages inactive:\s+(\d+)/);
      const matchCompressed = stdout.match(/Pages compressed:\s+(\d+)/);
      
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

  async getCPUUsage() {
    try {
      const { stdout } = await execAsync("ps -A -o %cpu | awk '{s+=$1} END {print s}'");
      const cpuUsage = parseFloat(stdout.trim()) || 0;
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

  async getDiskStats() {
    const disks = [];
    try {
      const { stdout } = await execAsync('df -H');
      const lines = stdout.trim().split('\n').slice(1);
      
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 9 && parts[0].startsWith('/dev/')) {
          const filesystem = parts[0];
          const size = parts[1];
          const used = parts[2];
          const available = parts[3];
          const usePercent = parseInt(parts[4]) || 0;
          const mountpoint = parts[8];
          
          // Filter out system volumes and only include real drives
          if (mountpoint && (mountpoint.startsWith('/Volumes/') || mountpoint === '/')) {
            disks.push({
              filesystem,
              size,
              used,
              available,
              usePercent,
              mountpoint,
              type: mountpoint === '/' ? 'internal' : 'external',
              name: mountpoint === '/' ? 'Macintosh HD' : mountpoint.replace('/Volumes/', '')
            });
          }
        }
      }
    } catch (e) {
      this.log('error', `Failed to get disk stats: ${e.message}`);
    }
    return disks;
  }

  async getProcessList() {
    try {
      const { stdout } = await execAsync('ps -axm -o pid,comm,pmem,rss,pcpu,time | head -10');
      const lines = stdout.trim().split('\n').slice(1);
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

  // ========== Cloud Storage ==========
  
  async getCloudStorageStatus() {
    const cloudServices = [];
    
    try {
      const { stdout } = await execAsync('ps aux | grep -i "google drive" | grep -v grep');
      cloudServices.push({ name: 'Google Drive', status: stdout.trim() ? 'running' : 'stopped' });
    } catch {
      cloudServices.push({ name: 'Google Drive', status: 'not_installed' });
    }
    
    try {
      const { stdout } = await execAsync('ps aux | grep -i dropbox | grep -v grep');
      cloudServices.push({ name: 'Dropbox', status: stdout.trim() ? 'running' : 'stopped' });
    } catch {
      cloudServices.push({ name: 'Dropbox', status: 'not_installed' });
    }
    
    try {
      const { stdout } = await execAsync('ps aux | grep -i onedrive | grep -v grep');
      cloudServices.push({ name: 'OneDrive', status: stdout.trim() ? 'running' : 'stopped' });
    } catch {
      cloudServices.push({ name: 'OneDrive', status: 'not_installed' });
    }
    
    try {
      const { stdout } = await execAsync('ps aux | grep -i "cloudd" | grep -v grep');
      cloudServices.push({ name: 'iCloud Drive', status: stdout.trim() ? 'running' : 'stopped' });
    } catch {
      cloudServices.push({ name: 'iCloud Drive', status: 'not_installed' });
    }
    
    return cloudServices;
  }

  // ========== Alerts ==========
  
  async getAlerts() {
    const alerts = [];
    const system = await this.getSystemStats();
    const disks = await this.getDiskStats();
    const cpu = await this.getCPUUsage();
    
    if (system.percent > this.config.criticalThreshold) {
      alerts.push({
        type: 'critical',
        source: 'memory',
        message: `Memory critical: ${system.percent}%`,
        timestamp: new Date().toISOString()
      });
    } else if (system.percent > this.config.memoryThreshold) {
      alerts.push({
        type: 'warning',
        source: 'memory',
        message: `Memory high: ${system.percent}%`,
        timestamp: new Date().toISOString()
      });
    }
    
    if (cpu.usage > 95) {
      alerts.push({
        type: 'critical',
        source: 'cpu',
        message: `CPU critical: ${cpu.usage}%`,
        timestamp: new Date().toISOString()
      });
    } else if (cpu.usage > 80) {
      alerts.push({
        type: 'warning',
        source: 'cpu',
        message: `CPU high: ${cpu.usage}%`,
        timestamp: new Date().toISOString()
      });
    }
    
    for (const disk of disks) {
      if (disk.usePercent > 95) {
        alerts.push({
          type: 'critical',
          source: disk.type === 'external' ? 'external-storage' : 'disk',
          message: `${disk.type === 'external' ? 'External Drive' : 'Disk'} ${disk.name} critical: ${disk.usePercent}%`,
          timestamp: new Date().toISOString()
        });
      } else if (disk.usePercent > this.config.diskThreshold) {
        alerts.push({
          type: 'warning',
          source: disk.type === 'external' ? 'external-storage' : 'disk',
          message: `${disk.type === 'external' ? 'External Drive' : 'Disk'} ${disk.name} high: ${disk.usePercent}%`,
          timestamp: new Date().toISOString()
        });
      }
    }
    
    return alerts;
  }

  // ========== History Management ==========
  
  async updateHistory() {
    const system = await this.getSystemStats();
    const cpu = await this.getCPUUsage();
    const disks = await this.getDiskStats();
    
    this.history.memory.push({ time: Date.now(), value: system.percent });
    this.history.cpu.push({ time: Date.now(), value: cpu.usage });
    
    const avgDiskUsage = disks.length > 0 
      ? Math.round(disks.reduce((sum, d) => sum + d.usePercent, 0) / disks.length)
      : 0;
    this.history.disk.push({ time: Date.now(), value: avgDiskUsage });
    
    if (this.history.memory.length > this.maxHistorySize) {
      this.history.memory.shift();
      this.history.cpu.shift();
      this.history.disk.shift();
    }
  }

  // ========== Storage Management ==========
  
  async runStorageCleanup() {
    const now = Date.now();
    if (now - this.lastCleanup < this.config.cleanupInterval) {
      return;
    }
    
    this.log('info', 'Running storage cleanup...');
    this.lastCleanup = now;
    
    try {
      // Run storage manager if available
      const storageManagerPath = path.join(__dirname, 'storage-manager.js');
      if (fs.existsSync(storageManagerPath)) {
        await execAsync(`/opt/homebrew/bin/node "${storageManagerPath}"`);
        this.log('info', 'Storage cleanup completed');
      }
    } catch (e) {
      this.log('error', `Storage cleanup error: ${e.message}`);
    }
  }

  // ========== Cloud Installer ==========
  
  async runCloudInstaller() {
    const now = Date.now();
    if (now - this.lastCloudCheck < this.config.cloudCheckInterval) {
      return;
    }
    
    this.log('info', 'Running cloud installer check...');
    this.lastCloudCheck = now;
    
    try {
      const cloudInstallerPath = path.join(__dirname, 'cloud-installer.js');
      if (fs.existsSync(cloudInstallerPath)) {
        await execAsync(`/opt/homebrew/bin/node "${cloudInstallerPath}"`);
        this.log('info', 'Cloud installer check completed');
      }
    } catch (e) {
      this.log('error', `Cloud installer error: ${e.message}`);
    }
  }

  // ========== API Endpoints ==========
  
  async getAPIResponse() {
    await this.updateHistory();
    
    return JSON.stringify({
      timestamp: new Date().toISOString(),
      server: {
        name: 'Super Server',
        version: '1.0.0',
        uptime: Math.round(os.uptime()),
        pid: process.pid
      },
      system: await this.getSystemStats(),
      cpu: await this.getCPUUsage(),
      disks: await this.getDiskStats(),
      processes: await this.getProcessList(),
      cloudStorage: await this.getCloudStorageStatus(),
      alerts: await this.getAlerts(),
      history: this.history
    });
  }

  // ========== HTTP Server ==========
  
  createServer() {
    this.server = http.createServer(async (req, res) => {
      // CORS headers
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      
      if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
      }
      
      if (req.url === '/api/status') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(await this.getAPIResponse());
      } else if (req.url === '/api/cleanup') {
        try {
          await this.runStorageCleanup();
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'success', message: 'Cleanup completed successfully' }));
        } catch (e) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'error', message: e.message }));
        }
      } else if (req.url === '/api/cloud') {
        try {
          await this.runCloudInstaller();
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'success', message: 'Cloud check completed successfully' }));
        } catch (e) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'error', message: e.message }));
        }
      } else if (req.url === '/api/kill-process') {
        if (req.method === 'POST') {
          let body = '';
          req.on('data', chunk => body += chunk);
          req.on('end', async () => {
            try {
              const { pid } = JSON.parse(body);
              await execAsync(`kill ${pid}`);
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ status: 'success', message: `Process ${pid} killed` }));
            } catch (e) {
              res.writeHead(500, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ status: 'error', message: e.message }));
            }
          });
        } else {
          res.writeHead(405, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'error', message: 'Method not allowed' }));
        }
      } else if (req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(this.getDashboardHTML());
      } else {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
      }
    });
  }

  getDashboardHTML() {
    return `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RudiBot Mega Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    :root {
      --bg-primary: #0a0e27;
      --bg-secondary: #1a1f3a;
      --bg-card: #16213e;
      --accent-primary: #4f46e5;
      --accent-secondary: #7c3aed;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --border: rgba(255,255,255,0.1);
    }
    
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      padding: 0;
      min-height: 100vh;
      overflow-x: hidden;
    }
    
    .sidebar {
      position: fixed;
      left: 0;
      top: 0;
      width: 250px;
      height: 100vh;
      background: var(--bg-secondary);
      border-right: 1px solid var(--border);
      padding: 24px;
      display: flex;
      flex-direction: column;
      z-index: 100;
    }
    
    .logo {
      font-size: 24px;
      font-weight: 800;
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 40px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .logo i {
      -webkit-text-fill-color: var(--accent-primary);
      background: none;
    }
    
    .nav-item {
      padding: 14px 18px;
      border-radius: 12px;
      color: var(--text-secondary);
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
      transition: all 0.3s ease;
      cursor: pointer;
    }
    
    .nav-item:hover, .nav-item.active {
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      color: white;
      transform: translateX(4px);
    }
    
    .main-content {
      margin-left: 250px;
      padding: 32px;
    }
    
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 32px;
    }
    
    .header h1 {
      font-size: 32px;
      font-weight: 700;
      color: var(--text-primary);
    }
    
    .header-actions {
      display: flex;
      gap: 12px;
    }
    
    .btn {
      padding: 12px 24px;
      border-radius: 12px;
      border: none;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s ease;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .btn-primary {
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      color: white;
    }
    
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(79, 70, 229, 0.3);
    }
    
    .btn-secondary {
      background: var(--bg-card);
      color: var(--text-primary);
      border: 1px solid var(--border);
    }
    
    .btn-secondary:hover {
      background: var(--bg-secondary);
    }
    
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 24px;
      margin-bottom: 32px;
    }
    
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      position: relative;
      overflow: hidden;
    }
    
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 4px;
      background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
    }
    
    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      font-size: 20px;
      color: white;
    }
    
    .stat-value {
      font-size: 32px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 4px;
    }
    
    .stat-label {
      font-size: 14px;
      color: var(--text-secondary);
      font-weight: 500;
    }
    
    .stat-change {
      font-size: 12px;
      margin-top: 8px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    
    .stat-change.positive { color: var(--success); }
    .stat-change.negative { color: var(--danger); }
    
    .content-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 24px;
      margin-bottom: 32px;
    }
    
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
    }
    
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }
    
    .card-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--text-primary);
    }
    
    .card-actions {
      display: flex;
      gap: 8px;
    }
    
    .card-action {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s ease;
      color: var(--text-secondary);
    }
    
    .card-action:hover {
      background: var(--accent-primary);
      color: white;
    }
    
    .chart-container {
      height: 300px;
      position: relative;
    }
    
    .table {
      width: 100%;
      border-collapse: collapse;
    }
    
    .table th {
      text-align: left;
      padding: 16px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-secondary);
      font-weight: 600;
      border-bottom: 1px solid var(--border);
    }
    
    .table td {
      padding: 16px;
      border-bottom: 1px solid var(--border);
      color: var(--text-primary);
    }
    
    .table tr:last-child td {
      border-bottom: none;
    }
    
    .status-badge {
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }
    
    .status-running { background: rgba(16, 185, 129, 0.2); color: var(--success); }
    .status-stopped { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
    .status-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
    .status-not_installed { background: rgba(148, 163, 184, 0.2); color: var(--text-secondary); }
    
    .progress-bar {
      height: 8px;
      border-radius: 4px;
      background: var(--bg-secondary);
      overflow: hidden;
      margin-top: 8px;
    }
    
    .progress-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.5s ease;
    }
    
    .progress-fill.success { background: var(--success); }
    .progress-fill.warning { background: var(--warning); }
    .progress-fill.danger { background: var(--danger); }
    
    .alert-item {
      padding: 16px;
      margin-bottom: 12px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      gap: 12px;
      border-left: 4px solid;
    }
    
    .alert-item.critical {
      background: rgba(239, 68, 68, 0.1);
      border-color: var(--danger);
    }
    
    .alert-item.warning {
      background: rgba(245, 158, 11, 0.1);
      border-color: var(--warning);
    }
    
    .alert-icon {
      font-size: 20px;
    }
    
    .alert-content {
      flex: 1;
    }
    
    .alert-title {
      font-weight: 600;
      margin-bottom: 4px;
    }
    
    .alert-time {
      font-size: 12px;
      color: var(--text-secondary);
    }
    
    .no-alerts {
      text-align: center;
      padding: 32px;
      color: var(--success);
    }
    
    @media (max-width: 1200px) {
      .stats-grid {
        grid-template-columns: repeat(2, 1fr);
      }
      .content-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="logo">
      <i class="fas fa-robot"></i>
      RudiBot Mega Dashboard
    </div>
    <div class="nav-item active">
      <i class="fas fa-chart-line"></i>
      Dashboard
    </div>
    <div class="nav-item">
      <i class="fas fa-microchip"></i>
      System
    </div>
    <div class="nav-item">
      <i class="fas fa-hdd"></i>
      Storage
    </div>
    <div class="nav-item">
      <i class="fas fa-cloud"></i>
      Cloud
    </div>
    <div class="nav-item">
      <i class="fas fa-cog"></i>
      Settings
    </div>
  </div>

  <div class="main-content">
    <div class="header">
      <div>
        <h1>Dashboard</h1>
        <p style="color: var(--text-secondary); margin-top: 8px;">Real-time system monitoring and management</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" onclick="checkCloud()">
          <i class="fas fa-cloud-download-alt"></i>
          Check Cloud
        </button>
        <button class="btn btn-primary" onclick="runCleanup()">
          <i class="fas fa-broom"></i>
          Run Cleanup
        </button>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-memory"></i>
        </div>
        <div class="stat-value" id="memory-value">...</div>
        <div class="stat-label">Memory Usage</div>
        <div class="stat-change" id="memory-change">
          <i class="fas fa-arrow-up"></i>
          <span>2.5%</span>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-microchip"></i>
        </div>
        <div class="stat-value" id="cpu-value">...</div>
        <div class="stat-label">CPU Usage</div>
        <div class="stat-change" id="cpu-change">
          <i class="fas fa-arrow-down"></i>
          <span>1.2%</span>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-hdd"></i>
        </div>
        <div class="stat-value" id="disk-value">...</div>
        <div class="stat-label">Disk Usage</div>
        <div class="stat-change" id="disk-change">
          <i class="fas fa-minus"></i>
          <span>0.0%</span>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">
          <i class="fas fa-clock"></i>
        </div>
        <div class="stat-value" id="uptime-value">...</div>
        <div class="stat-label">Uptime</div>
        <div class="stat-change">
          <i class="fas fa-check-circle"></i>
          <span>Stable</span>
        </div>
      </div>
    </div>

    <div class="content-grid">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Resource Usage</div>
          <div class="card-actions">
            <div class="card-action"><i class="fas fa-expand"></i></div>
            <div class="card-action"><i class="fas fa-download"></i></div>
          </div>
        </div>
        <div class="chart-container">
          <canvas id="resourceChart"></canvas>
        </div>
      </div>
      
      <div class="card">
        <div class="card-header">
          <div class="card-title">Active Alerts</div>
          <div class="card-actions">
            <div class="card-action"><i class="fas fa-bell"></i></div>
          </div>
        </div>
        <div id="alert-list"></div>
      </div>
    </div>

    <div class="content-grid">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Top Processes</div>
          <div class="card-actions">
            <div class="card-action"><i class="fas fa-refresh"></i></div>
          </div>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>Process</th>
              <th>CPU</th>
              <th>Memory</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="process-list"></tbody>
        </table>
      </div>
      
      <div class="card">
        <div class="card-header">
          <div class="card-title">External Storage</div>
          <div class="card-actions">
            <div class="card-action"><i class="fas fa-sync"></i></div>
          </div>
        </div>
        <div id="external-storage-list"></div>
      </div>
      
      <div class="card">
        <div class="card-header">
          <div class="card-title">Cloud Storage</div>
          <div class="card-actions">
            <div class="card-action"><i class="fas fa-sync"></i></div>
          </div>
        </div>
        <div id="cloud-list"></div>
      </div>
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
              borderColor: '#4f46e5',
              backgroundColor: 'rgba(79, 70, 229, 0.1)',
              tension: 0.4,
              fill: true,
              borderWidth: 2
            },
            {
              label: 'CPU %',
              data: [],
              borderColor: '#10b981',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              tension: 0.4,
              fill: true,
              borderWidth: 2
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: '#94a3b8', font: { size: 12 } }
            }
          },
          scales: {
            x: {
              ticks: { color: '#94a3b8' },
              grid: { color: 'rgba(255,255,255,0.05)' }
            },
            y: {
              ticks: { color: '#94a3b8' },
              grid: { color: 'rgba(255,255,255,0.05)' },
              min: 0,
              max: 100
            }
          }
        }
      });
    }
    
    async function loadData() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        // Update stats
        document.getElementById('memory-value').textContent = data.system.percent + '%';
        document.getElementById('cpu-value').textContent = data.cpu.usage + '%';
        
        const avgDisk = data.disks.length > 0 
          ? Math.round(data.disks.reduce((sum, d) => sum + d.usePercent, 0) / data.disks.length)
          : 0;
        document.getElementById('disk-value').textContent = avgDisk + '%';
        
        const uptime = data.system.uptime;
        const hours = Math.floor(uptime / 3600);
        const minutes = Math.floor((uptime % 3600) / 60);
        document.getElementById('uptime-value').textContent = hours + 'h ' + minutes + 'm';
        
        // Update chart
        if (resourceChart) {
          const labels = data.history.memory.map((_, i) => i);
          resourceChart.data.labels = labels;
          resourceChart.data.datasets[0].data = data.history.memory.map(d => d.value);
          resourceChart.data.datasets[1].data = data.history.cpu.map(d => d.value);
          resourceChart.update('none');
        }
        
        // Update processes
        const processList = document.getElementById('process-list');
        processList.textContent = '';
        data.processes.slice(0, 6).forEach(proc => {
          const row = document.createElement('tr');
          row.innerHTML = \`
            <td>\${proc.name}</td>
            <td>\${proc.cpuPercent.toFixed(1)}%</td>
            <td>\${proc.memMB}MB</td>
            <td>
              <span class="status-badge status-running">Active</span>
              <button onclick="killProcess(\${proc.pid})" style="margin-left: 8px; padding: 4px 8px; border: none; border-radius: 4px; background: rgba(239, 68, 68, 0.2); color: #ef4444; cursor: pointer; font-size: 11px;">
                <i class="fas fa-times"></i> Kill
              </button>
            </td>
          \`;
          processList.appendChild(row);
        });
        
        // Update external storage
        const externalStorageList = document.getElementById('external-storage-list');
        externalStorageList.textContent = '';
        
        // Fix: Check if data.disks exists and is an array
        let externalDisks = [];
        if (data.disks && Array.isArray(data.disks)) {
          externalDisks = data.disks.filter(disk => disk.type === 'external');
        }
        externalDisks.forEach(disk => {
          const div = document.createElement('div');
          div.style.cssText = 'padding: 16px; margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; display: flex; justify-content: space-between; align-items: center;';
          const statusColor = disk.usePercent > 90 ? 'rgba(239, 68, 68, 0.2)' : disk.usePercent > 70 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(34, 197, 94, 0.2)';
          const statusTextColor = disk.usePercent > 90 ? '#ef4444' : disk.usePercent > 70 ? '#f59e0b' : '#22c55e';
          div.innerHTML = \`
            <div>
              <div style="font-weight: 600; margin-bottom: 4px;">
                <i class="fas fa-external-drive-alt"></i> \${disk.name}
              </div>
              <div style="font-size: 12px; color: rgba(255,255,255,0.6);">
                \${disk.used} / \${disk.size} used
              </div>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 14px; font-weight: 600; margin-bottom: 4px;">
                \${disk.usePercent}%
              </div>
              <span style="padding: 4px 8px; border-radius: 12px; background: \${statusColor}; color: \${statusTextColor}; font-size: 11px;">
                \${disk.usePercent > 90 ? 'Critical' : disk.usePercent > 70 ? 'Warning' : 'OK'}
              </span>
            </div>
          \`;
          externalStorageList.appendChild(div);
        });
        
        if (externalDisks.length === 0) {
          const div = document.createElement('div');
          div.style.cssText = 'padding: 32px; text-align: center; color: rgba(255,255,255,0.5);';
          div.textContent = '<i class='fas fa-external-drive-alt" style="font-size: 24px; margin-bottom: 8px;"></i><div>No external drives connected</div>';
          externalStorageList.appendChild(div);
        }
        
        // Update cloud storage
        const cloudList = document.getElementById('cloud-list');
        cloudList.textContent = '';
        data.cloudStorage.forEach(cloud => {
          const div = document.createElement('div');
          div.style.cssText = 'padding: 16px; margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; display: flex; justify-content: space-between; align-items: center;';
          div.innerHTML = \`
            <div style="display: flex; align-items: center; gap: 12px;">
              <i class="fas fa-cloud" style="color: #4f46e5;"></i>
              <span>\${cloud.name}</span>
            </div>
            <span class="status-badge status-\${cloud.status}">\${cloud.status}</span>
          \`;
          cloudList.appendChild(div);
        });
        
        // Update alerts
        const alertList = document.getElementById('alert-list');
        alertList.textContent = '';
        if (data.alerts.length === 0) {
          alertList.textContent = '<div class='no-alerts"><i class="fas fa-check-circle" style="font-size: 32px; margin-bottom: 16px;"></i><p>No active alerts</p></div>';
        } else {
          data.alerts.forEach(alert => {
            const div = document.createElement('div');
            div.className = 'alert-item ' + alert.type;
            div.innerHTML = \`
              <div class="alert-icon">
                <i class="fas fa-\${alert.type === 'critical' ? 'exclamation-triangle' : 'exclamation-circle'}"></i>
              </div>
              <div class="alert-content">
                <div class="alert-title">\${alert.message}</div>
                <div class="alert-time">\${new Date(alert.timestamp).toLocaleString()}</div>
              </div>
            \`;
            alertList.appendChild(div);
          });
        }
      } catch (e) {
        console.error('Load failed:', e);
      }
    }
    
    async function runCleanup() {
      const btn = event.target.closest('button');
      const originalText = btn.innerHTML;
      btn.textContent = '<i class='fas fa-spinner fa-spin"></i> Running...';
      btn.disabled = true;
      
      try {
        const res = await fetch('/api/cleanup');
        const data = await res.json();
        
        if (data.status === 'success') {
          btn.textContent = '<i class='fas fa-check"></i> Success!';
          setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
          }, 2000);
        } else {
          btn.textContent = '<i class='fas fa-exclamation-triangle"></i> Error';
          setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
          }, 2000);
        }
      } catch (e) {
        btn.textContent = '<i class='fas fa-exclamation-triangle"></i> Failed';
        setTimeout(() => {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    async function checkCloud() {
      const btn = event.target.closest('button');
      const originalText = btn.innerHTML;
      btn.textContent = '<i class='fas fa-spinner fa-spin"></i> Checking...';
      btn.disabled = true;
      
      try {
        const res = await fetch('/api/cloud');
        const data = await res.json();
        
        if (data.status === 'success') {
          btn.textContent = '<i class='fas fa-check"></i> Success!';
          setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
          }, 2000);
        } else {
          btn.textContent = '<i class='fas fa-exclamation-triangle"></i> Error';
          setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
          }, 2000);
        }
      } catch (e) {
        btn.textContent = '<i class='fas fa-exclamation-triangle"></i> Failed';
        setTimeout(() => {
          btn.innerHTML = originalText;
          btn.disabled = false;
        }, 2000);
      }
    }
    
    async function killProcess(pid) {
      try {
        const res = await fetch('/api/kill-process', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
          loadData();
        } else {
          alert('Failed to kill process: ' + data.message);
        }
      } catch (e) {
        alert('Failed to kill process: ' + e.message);
      }
    }
    
    initChart();
    loadData();
    setInterval(loadData, 2000);
  </script>
</body>
</html>`;
  }

  // ========== Lifecycle ==========
  
  start() {
    if (this.running) return;
    
    this.createServer();
    this.server.listen(this.port, () => {
      this.log('info', `🚀 Super Server started on http://localhost:${this.port}`);
      this.running = true;
      
      // Write PID file
      try {
        fs.writeFileSync(this.pidFile, process.pid.toString());
      } catch (e) {
        this.log('error', `Failed to write PID file: ${e.message}`);
      }
      
      // Start periodic tasks
      this.startPeriodicTasks();
    });
    
    this.server.on('error', (error) => {
      this.log('error', `Server error: ${error.message}`);
    });
  }

  startPeriodicTasks() {
    // Run storage cleanup periodically
    setInterval(() => {
      this.runStorageCleanup();
    }, this.config.cleanupInterval);
    
    // Run cloud check periodically
    setInterval(() => {
      this.runCloudInstaller();
    }, this.config.cloudCheckInterval);
  }

  stop() {
    this.running = false;
    if (this.server) {
      this.server.close();
    }
    
    try {
      fs.unlinkSync(this.pidFile);
    } catch (e) {}
    
    this.log('info', 'Super Server stopped');
  }
}

// Start server
const server = new SuperServer(9001);
server.start();

// Handle graceful shutdown
process.on('SIGINT', () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('\nShutting down gracefully...');
  server.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('\nShutting down gracefully...');
  server.stop();
  process.exit(0);
});
