/**
 * SuperMegaBot Monitor Bot - Überwachung & System-Health
 * Zuständig: RAM, CPU, API-Status, Server-Health
 */

import os from 'os';
import fs from 'fs';
import { exec } from 'child_process';
import axios from 'axios';

class MonitorBot {
  constructor() {
    this.name = 'MonitorBot';
    this.interval = 30000; // 30 Sekunden
    this.alerts = [];
    this.isRunning = false;
  }

  async start() {
    console.log(`🤖 ${this.name} starting...`);
    this.isRunning = true;
    
    // Haupt-Monitoring Loop
    this.monitoringInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      const health = await this.checkSystemHealth();
      const apiStatus = await this.checkAPIs();
      const servers = await this.checkServers();
      
      await this.processHealthData({ health, apiStatus, servers });
    }, this.interval);
    
    console.log(`✅ ${this.name} started - Monitoring every ${this.interval/1000}s`);
  }

  async checkSystemHealth() {
    const memUsage = process.memoryUsage();
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const cpuUsage = os.cpus();
    
    return {
      memory: {
        total: totalMem,
        free: freeMem,
        used: totalMem - freeMem,
        percentage: ((totalMem - freeMem) / totalMem * 100).toFixed(2)
      },
      cpu: {
        cores: cpuUsage.length,
        loadAverage: os.loadavg()
      },
      uptime: os.uptime(),
      timestamp: new Date().toISOString()
    };
  }

  async checkAPIs() {
    const apis = [
      { name: 'Claude', url: 'http://localhost:4001/api/claude' },
      { name: 'QuickCash', url: 'http://localhost:3001/health' },
      { name: 'My-Shop', url: 'http://localhost:4000/api/health' }
    ];

    const results = {};
    
    for (const api of apis) {
      try {
        const response = await axios.get(api.url, { timeout: 5000 });
        results[api.name] = {
          status: 'online',
          responseTime: response.headers['x-response-time'] || 'N/A',
          timestamp: new Date().toISOString()
        };
      } catch (error) {
        results[api.name] = {
          status: 'offline',
          error: error.message,
          timestamp: new Date().toISOString()
        };
        
        if (this.shouldAlert(api.name, 'offline')) {
          await this.sendAlert(`🚨 ${api.name} API Offline`, error.message);
        }
      }
    }
    
    return results;
  }

  async checkServers() {
    const servers = [
      { name: 'Backend 4001', port: 4001 },
      { name: 'QuickCash 3001', port: 3001 },
      { name: 'My-Shop 4000', port: 4000 }
    ];

    const results = {};
    
    for (const server of servers) {
      try {
        const isRunning = await this.checkPort(server.port);
        results[server.name] = {
          status: isRunning ? 'running' : 'stopped',
          port: server.port,
          timestamp: new Date().toISOString()
        };
        
        if (!isRunning && this.shouldAlert(server.name, 'stopped')) {
          await this.sendAlert(`🚨 ${server.name} Server Stopped`, `Port ${server.port} nicht erreichbar`);
        }
      } catch (error) {
        results[server.name] = {
          status: 'error',
          error: error.message,
          timestamp: new Date().toISOString()
        };
      }
    }
    
    return results;
  }

  async checkPort(port) {
    return new Promise((resolve) => {
      exec(`lsof -i:${port}`, (error, stdout) => {
        resolve(!error && stdout.length > 0);
      });
    });
  }

  async processHealthData(data) {
    const { health, apiStatus, servers } = data;
    
    // Memory Alert
    if (parseFloat(health.memory.percentage) > 90) {
      await this.sendAlert('🚨 High Memory Usage', `${health.memory.percentage}% RAM verwendet`);
    }
    
    // Log Health Data
    this.logHealthData(data);
    
    // Auto-cleanup bei hohem Speicherverbrauch
    if (parseFloat(health.memory.percentage) > 85) {
      await this.performCleanup();
    }
  }

  async performCleanup() {
    console.log('🧹 MonitorBot: Performing automatic cleanup...');
    
    try {
      // Temporäre Dateien aufräumen
      await exec('rm -rf /tmp/supermegabot-*');
      
      // Node.js Prozesse restarten falls nötig
      const memUsage = process.memoryUsage();
      if (memUsage.heapUsed > 500 * 1024 * 1024) { // 500MB
        console.log('🔄 MonitorBot: High memory usage detected, requesting restart...');
        // Hier könnte ein automatischer Restart implementiert werden
      }
      
    } catch (error) {
      console.error('Cleanup failed:', error.message);
    }
  }

  shouldAlert(service, status) {
    const key = `${service}_${status}`;
    const now = Date.now();
    const lastAlert = this.alerts[key];
    
    if (!lastAlert || now - lastAlert > 300000) { // 5 Minuten Cooldown
      this.alerts[key] = now;
      return true;
    }
    return false;
  }

  async sendAlert(title, message) {
    console.log(`🚨 ALERT: ${title} - ${message}`);
    
    // Hier könnten verschiedene Alert-Methoden implementiert werden:
    // - Slack/Webhook
    // - Email
    // - Telegram Bot
    // - Desktop Notification
    
    // Aktuell: Console Log + File Log
    const alertLog = {
      title,
      message,
      timestamp: new Date().toISOString(),
      bot: this.name
    };
    
    fs.appendFileSync('./logs/alerts.log', JSON.stringify(alertLog) + '\n');
  }

  logHealthData(data) {
    const logEntry = {
      ...data,
      bot: this.name,
      timestamp: new Date().toISOString()
    };
    
    fs.appendFileSync('./logs/monitoring.log', JSON.stringify(logEntry) + '\n');
  }

  async stop() {
    console.log(`🛑 ${this.name} stopping...`);
    this.isRunning = false;
    clearInterval(this.monitoringInterval);
    console.log(`✅ ${this.name} stopped`);
  }

  getStatus() {
    return {
      name: this.name,
      isRunning: this.isRunning,
      interval: this.interval,
      alertsCount: Object.keys(this.alerts).length,
      uptime: process.uptime()
    };
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new MonitorBot();
  bot.start();
  
  // Graceful shutdown
  process.on('SIGINT', async () => {
    await bot.stop();
    process.exit(0);
  });
}

export default MonitorBot;
