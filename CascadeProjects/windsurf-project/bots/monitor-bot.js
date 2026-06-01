#!/usr/bin/env node

/**
 * 🤖 Monitor Bot - System Health Monitoring
 * 
 * Tasks:
 * - Memory tracking
 * - Error detection  
 * - Performance metrics
 * - Service health checks
 * - API status monitoring
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment
dotenv.config();

class MonitorBot {
  constructor() {
    this.projectDir = path.join(__dirname, '..');
    this.logFile = path.join(this.projectDir, 'logs', 'monitor-bot.log');
    this.alertsFile = path.join(this.projectDir, 'data', 'alerts.json');
    this.metricsFile = path.join(this.projectDir, 'data', 'metrics.json');
    this.isRunning = false;
    this.checkInterval = 30000; // 30 seconds
    this.alerts = [];
    this.metrics = {};
    
    this.ensureDirectories();
    this.loadExistingData();
  }

  ensureDirectories() {
    const dirs = ['logs', 'data', 'pids'];
    dirs.forEach(dir => {
      const dirPath = path.join(this.projectDir, dir);
      if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
      }
    });
  }

  loadExistingData() {
    try {
      if (fs.existsSync(this.alertsFile)) {
        this.alerts = JSON.parse(fs.readFileSync(this.alertsFile, 'utf8'));
      }
      if (fs.existsSync(this.metricsFile)) {
        this.metrics = JSON.parse(fs.readFileSync(this.metricsFile, 'utf8'));
      }
    } catch (error) {
      console.log('[Monitor Bot] Starting fresh - no existing data found');
    }
  }

  log(message, level = 'info') {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
    console.log(logMessage);
    
    // Write to log file
    fs.appendFileSync(this.logFile, logMessage + '\n');
  }

  async checkMemoryUsage() {
    try {
      const stats = fs.statSync(this.logFile);
      const memoryUsage = process.memoryUsage();
      
      const memoryData = {
        timestamp: new Date().toISOString(),
        heapUsed: Math.round(memoryUsage.heapUsed / 1024 / 1024), // MB
        heapTotal: Math.round(memoryUsage.heapTotal / 1024 / 1024), // MB
        external: Math.round(memoryUsage.external / 1024 / 1024), // MB
        rss: Math.round(memoryUsage.rss / 1024 / 1024), // MB
        logFileSize: Math.round(stats.size / 1024 / 1024), // MB
      };

      // Check for memory issues
      if (memoryData.heapUsed > 1024) { // > 1GB
        this.createAlert('HIGH_MEMORY', `High memory usage: ${memoryData.heapUsed}MB`, 'critical');
      }

      if (memoryData.logFileSize > 100) { // > 100MB
        this.createAlert('LARGE_LOG_FILE', `Log file too large: ${memoryData.logFileSize}MB`, 'warning');
      }

      this.metrics.memory = memoryData;
      return memoryData;
    } catch (error) {
      this.log(`Memory check failed: ${error.message}`, 'error');
    }
  }

  async checkAPIKeys() {
    const requiredKeys = [
      'ANTHROPIC_API_KEY',
      'TELEGRAM_BOT_TOKEN',
      'SHOPIFY_ACCESS_TOKEN',
      'GITHUB_TOKEN'
    ];

    const missingKeys = [];
    const placeholderKeys = [];

    requiredKeys.forEach(key => {
      const value = process.env[key];
      if (!value) {
        missingKeys.push(key);
      } else if (value.includes('YOUR_') || value.includes('REPLACE_')) {
        placeholderKeys.push(key);
      }
    });

    if (missingKeys.length > 0) {
      this.createAlert('MISSING_API_KEYS', `Missing keys: ${missingKeys.join(', ')}`, 'critical');
    }

    if (placeholderKeys.length > 0) {
      this.createAlert('PLACEHOLDER_API_KEYS', `Placeholder keys: ${placeholderKeys.join(', ')}`, 'warning');
    }

    return { missingKeys, placeholderKeys };
  }

  async checkServices() {
    const services = [
      { name: 'Telegram Bot', url: process.env.TELEGRAM_BOT_URL, port: 8000 },
      { name: 'Shopify Service', url: process.env.SHOPIFY_SERVICE_URL, port: 3002 },
      { name: 'GitHub Service', url: process.env.GITHUB_SERVICE_URL, port: 3001 },
      { name: 'Dashboard', url: process.env.DASHBOARD_URL, port: 8888 },
    ];

    const serviceStatus = {};

    for (const service of services) {
      try {
        // Simple port check
        const isRunning = await this.checkPort(service.port);
        serviceStatus[service.name] = {
          port: service.port,
          running: isRunning,
          url: service.url,
          lastChecked: new Date().toISOString()
        };

        if (!isRunning) {
          this.createAlert('SERVICE_DOWN', `${service.name} is not running on port ${service.port}`, 'warning');
        }
      } catch (error) {
        serviceStatus[service.name] = {
          port: service.port,
          running: false,
          error: error.message,
          lastChecked: new Date().toISOString()
        };
        this.createAlert('SERVICE_ERROR', `${service.name} check failed: ${error.message}`, 'error');
      }
    }

    this.metrics.services = serviceStatus;
    return serviceStatus;
  }

  async checkPort(port) {
    return new Promise((resolve) => {
      const net = require('net');
      const server = net.createServer();

      server.listen(port, () => {
        server.once('close', () => {
          resolve(false); // Port is in use
        });
        server.close();
      });

      server.on('error', () => {
        resolve(true); // Port is available (service might be running)
      });

      setTimeout(() => {
        server.close();
        resolve(false);
      }, 1000);
    });
  }

  async checkFiles() {
    const criticalFiles = [
      'QuickCashSystem_Final.jsx',
      'my-shop/backend/index.js',
      'package.json',
      '.env'
    ];

    const fileStatus = {};

    for (const file of criticalFiles) {
      const filePath = path.join(this.projectDir, file);
      try {
        const stats = fs.statSync(filePath);
        fileStatus[file] = {
          exists: true,
          size: Math.round(stats.size / 1024), // KB
          modified: stats.mtime.toISOString(),
          lastChecked: new Date().toISOString()
        };
      } catch (error) {
        fileStatus[file] = {
          exists: false,
          error: error.message,
          lastChecked: new Date().toISOString()
        };
        this.createAlert('MISSING_FILE', `Critical file missing: ${file}`, 'critical');
      }
    }

    this.metrics.files = fileStatus;
    return fileStatus;
  }

  async checkProcesses() {
    try {
      const { exec } = require('child_process');
      const { promisify } = require('util');
      const execAsync = promisify(exec);

      // Check for Node processes
      const { stdout } = await execAsync('ps aux | grep node | grep -v grep');
      const processes = stdout.split('\n').filter(line => line.trim());

      const processStatus = {
        nodeProcesses: processes.length,
        processes: processes.map(line => ({
          raw: line,
          pid: line.split(/\s+/)[1],
          command: line.split(/\s+/).slice(10).join(' ')
        })),
        lastChecked: new Date().toISOString()
      };

      this.metrics.processes = processStatus;
      return processStatus;
    } catch (error) {
      this.log(`Process check failed: ${error.message}`, 'error');
      return { nodeProcesses: 0, processes: [], error: error.message };
    }
  }

  createAlert(type, message, severity = 'info') {
    const alert = {
      id: Date.now().toString(),
      type,
      message,
      severity,
      timestamp: new Date().toISOString(),
      resolved: false
    };

    // Avoid duplicate alerts
    const existingAlert = this.alerts.find(a => a.type === type && !a.resolved);
    if (existingAlert) {
      existingAlert.count = (existingAlert.count || 1) + 1;
      existingAlert.lastOccurrence = alert.timestamp;
    } else {
      this.alerts.push(alert);
      this.log(`🚨 ALERT [${severity.toUpperCase()}] ${type}: ${message}`, 'warn');
    }

    this.saveData();
  }

  resolveAlert(alertId) {
    const alert = this.alerts.find(a => a.id === alertId);
    if (alert) {
      alert.resolved = true;
      alert.resolvedAt = new Date().toISOString();
      this.saveData();
      this.log(`✅ Alert resolved: ${alert.type}`, 'info');
    }
  }

  saveData() {
    try {
      fs.writeFileSync(this.alertsFile, JSON.stringify(this.alerts, null, 2));
      fs.writeFileSync(this.metricsFile, JSON.stringify(this.metrics, null, 2));
    } catch (error) {
      this.log(`Failed to save data: ${error.message}`, 'error');
    }
  }

  async performHealthCheck() {
    this.log('🔍 Starting comprehensive health check...', 'info');

    const results = {
      timestamp: new Date().toISOString(),
      memory: await this.checkMemoryUsage(),
      apiKeys: await this.checkAPIKeys(),
      services: await this.checkServices(),
      files: await this.checkFiles(),
      processes: await this.checkProcesses()
    };

    // Calculate overall health score
    const score = this.calculateHealthScore(results);
    results.healthScore = score;

    this.log(`📊 Health check complete - Score: ${score}/100`, 'info');
    
    if (score < 70) {
      this.createAlert('LOW_HEALTH_SCORE', `System health score: ${score}/100`, 'warning');
    }

    this.metrics.lastHealthCheck = results;
    this.saveData();

    return results;
  }

  calculateHealthScore(results) {
    let score = 100;

    // Memory penalty
    if (results.memory?.heapUsed > 1024) score -= 20;
    if (results.memory?.heapUsed > 2048) score -= 30;

    // API keys penalty
    if (results.apiKeys?.missingKeys?.length > 0) score -= 25;
    if (results.apiKeys?.placeholderKeys?.length > 0) score -= 10;

    // Services penalty
    const runningServices = Object.values(results.services || {}).filter(s => s.running).length;
    const totalServices = Object.keys(results.services || {}).length;
    if (totalServices > 0) {
      score -= (totalServices - runningServices) * 15;
    }

    // Files penalty
    const missingFiles = Object.values(results.files || {}).filter(f => !f.exists).length;
    score -= missingFiles * 20;

    return Math.max(0, score);
  }

  async start() {
    if (this.isRunning) {
      this.log('Monitor Bot is already running', 'warn');
      return;
    }

    this.isRunning = true;
    this.log('🚀 Monitor Bot starting...', 'info');

    // Write PID file
    const pidFile = path.join(this.projectDir, 'pids', 'monitor-bot.pid');
    fs.writeFileSync(pidFile, process.pid.toString());

    // Initial health check
    await this.performHealthCheck();

    // Start monitoring loop
    this.monitorInterval = setInterval(async () => {
      try {
        await this.performHealthCheck();
      } catch (error) {
        this.log(`Monitor loop error: ${error.message}`, 'error');
      }
    }, this.checkInterval);

    this.log('✅ Monitor Bot started successfully', 'info');
  }

  async stop() {
    if (!this.isRunning) {
      this.log('Monitor Bot is not running', 'warn');
      return;
    }

    this.isRunning = false;
    
    if (this.monitorInterval) {
      clearInterval(this.monitorInterval);
    }

    // Remove PID file
    const pidFile = path.join(this.projectDir, 'pids', 'monitor-bot.pid');
    if (fs.existsSync(pidFile)) {
      fs.unlinkSync(pidFile);
    }

    this.log('🛑 Monitor Bot stopped', 'info');
  }

  async getStatus() {
    return {
      isRunning: this.isRunning,
      alerts: this.alerts.filter(a => !a.resolved),
      metrics: this.metrics,
      lastHealthCheck: this.metrics.lastHealthCheck,
      uptime: this.isRunning ? process.uptime() : 0
    };
  }
}

// CLI interface
if (import.meta.url === `file://${process.argv[1]}`) {
  const monitorBot = new MonitorBot();
  const command = process.argv[2] || 'start';

  switch (command) {
    case 'start':
      monitorBot.start();
      break;
    case 'stop':
      monitorBot.stop();
      break;
    case 'status':
      monitorBot.getStatus().then(status => {
        console.log(JSON.stringify(status, null, 2));
      });
      break;
    case 'check':
      monitorBot.performHealthCheck().then(results => {
        console.log(JSON.stringify(results, null, 2));
      });
      break;
    default:
      console.log('Usage: node monitor-bot.js [start|stop|status|check]');
  }
}

export default MonitorBot;
