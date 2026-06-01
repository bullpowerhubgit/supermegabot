/**
 * SuperMegaBot Monitoring Bot
 * Überwacht System Health, Performance und Fehler
 */

const EventEmitter = require('events');
const fs = require('fs').promises;
const path = require('path');

class MonitoringBot extends EventEmitter {
  constructor() {
    super();
    this.name = 'MonitoringBot';
    this.isRunning = false;
    this.checkInterval = 30000; // 30 Sekunden
    this.metrics = {
      memory: 0,
      cpu: 0,
      disk: 0,
      uptime: 0,
      errors: 0,
      activeServices: 0
    };
    this.alerts = [];
    this.thresholds = {
      memory: 80, // 80%
      cpu: 85,     // 85%
      disk: 90,    // 90%
      errors: 10   // 10 errors/hour
    };
  }

  async start() {
    if (this.isRunning) return;
    
    console.log('🤖 MonitoringBot starting...');
    this.isRunning = true;
    
    // Start monitoring loop
    this.monitoringLoop();
    
    // Start health checks
    this.startHealthChecks();
    
    console.log('✅ MonitoringBot started successfully');
    this.emit('started', { bot: this.name, timestamp: new Date() });
  }

  async stop() {
    if (!this.isRunning) return;
    
    console.log('🛑 MonitoringBot stopping...');
    this.isRunning = false;
    
    console.log('✅ MonitoringBot stopped');
    this.emit('stopped', { bot: this.name, timestamp: new Date() });
  }

  async monitoringLoop() {
    while (this.isRunning) {
      try {
        await this.collectMetrics();
        await this.checkThresholds();
        await this.saveMetrics();
        
        // Emit metrics for other bots
        this.emit('metrics', this.metrics);
        
      } catch (error) {
        console.error('❌ MonitoringBot error:', error);
        this.emit('error', { bot: this.name, error: error.message });
      }
      
      // Wait for next check
      await new Promise(resolve => setTimeout(resolve, this.checkInterval));
    }
  }

  async collectMetrics() {
    // Memory usage
    const memUsage = process.memoryUsage();
    this.metrics.memory = Math.round((memUsage.heapUsed / memUsage.heapTotal) * 100);
    
    // CPU usage (simplified)
    this.metrics.cpu = Math.round(Math.random() * 30 + 20); // Mock CPU usage
    
    // Disk usage
    try {
      const stats = await fs.stat('.');
      this.metrics.disk = Math.round(Math.random() * 20 + 40); // Mock disk usage
    } catch (error) {
      this.metrics.disk = 50;
    }
    
    // Uptime
    this.metrics.uptime = process.uptime();
    
    // Active services check
    this.metrics.activeServices = await this.checkActiveServices();
    
    console.log(`📊 Metrics: Memory ${this.metrics.memory}%, CPU ${this.metrics.cpu}%, Services ${this.metrics.activeServices}`);
  }

  async checkActiveServices() {
    const serviceFiles = [
      'mega-dashboard-backend.js',
      'quickcash-backend.js',
      'bots/public-bot.js',
      'bots/control-bot.js'
    ];
    
    let activeServices = 0;
    
    for (const service of serviceFiles) {
      try {
        await fs.access(service);
        activeServices++;
      } catch (error) {
        // Service file not found
      }
    }
    
    return activeServices;
  }

  async checkThresholds() {
    const alerts = [];
    
    // Memory threshold
    if (this.metrics.memory > this.thresholds.memory) {
      alerts.push({
        type: 'memory',
        level: 'warning',
        message: `Memory usage high: ${this.metrics.memory}%`,
        value: this.metrics.memory,
        threshold: this.thresholds.memory
      });
    }
    
    // CPU threshold
    if (this.metrics.cpu > this.thresholds.cpu) {
      alerts.push({
        type: 'cpu',
        level: 'warning',
        message: `CPU usage high: ${this.metrics.cpu}%`,
        value: this.metrics.cpu,
        threshold: this.thresholds.cpu
      });
    }
    
    // Disk threshold
    if (this.metrics.disk > this.thresholds.disk) {
      alerts.push({
        type: 'disk',
        level: 'critical',
        message: `Disk usage high: ${this.metrics.disk}%`,
        value: this.metrics.disk,
        threshold: this.thresholds.disk
      });
    }
    
    // Services threshold
    if (this.metrics.activeServices < 2) {
      alerts.push({
        type: 'services',
        level: 'critical',
        message: `Low active services: ${this.metrics.activeServices}`,
        value: this.metrics.activeServices,
        threshold: 2
      });
    }
    
    // Emit alerts
    if (alerts.length > 0) {
      this.alerts.push(...alerts);
      this.emit('alerts', alerts);
      
      // Keep only last 50 alerts
      if (this.alerts.length > 50) {
        this.alerts = this.alerts.slice(-50);
      }
    }
  }

  async startHealthChecks() {
    // Check file system health
    await this.checkFileSystem();
    
    // Check log files
    await this.checkLogFiles();
    
    // Check configuration files
    await this.checkConfigFiles();
  }

  async checkFileSystem() {
    const criticalDirs = ['logs', 'pids', 'backups'];
    
    for (const dir of criticalDirs) {
      try {
        await fs.access(dir);
      } catch (error) {
        // Create missing directory
        await fs.mkdir(dir, { recursive: true });
        console.log(`📁 Created missing directory: ${dir}`);
      }
    }
  }

  async checkLogFiles() {
    try {
      const logFiles = await fs.readdir('logs');
      const oldLogs = logFiles.filter(file => file.endsWith('.log'));
      
      for (const logFile of oldLogs) {
        const stats = await fs.stat(path.join('logs', logFile));
        const sizeInMB = stats.size / (1024 * 1024);
        
        // Rotate logs larger than 10MB
        if (sizeInMB > 10) {
          const oldPath = path.join('logs', logFile);
          const newPath = path.join('logs', `${logFile}.old`);
          await fs.rename(oldPath, newPath);
          console.log(`📝 Rotated log file: ${logFile}`);
        }
      }
    } catch (error) {
      // Logs directory doesn't exist, will be created by checkFileSystem
    }
  }

  async checkConfigFiles() {
    const configFiles = [
      'package.json',
      '.env',
      'api-config.json'
    ];
    
    for (const configFile of configFiles) {
      try {
        await fs.access(configFile);
      } catch (error) {
        console.warn(`⚠️ Missing config file: ${configFile}`);
      }
    }
  }

  async saveMetrics() {
    try {
      const metricsData = {
        timestamp: new Date().toISOString(),
        metrics: this.metrics,
        alerts: this.alerts.slice(-10) // Last 10 alerts
      };
      
      await fs.writeFile('logs/monitoring-metrics.json', JSON.stringify(metricsData, null, 2));
    } catch (error) {
      console.error('❌ Failed to save metrics:', error);
    }
  }

  getMetrics() {
    return {
      ...this.metrics,
      alerts: this.alerts.slice(-10),
      isRunning: this.isRunning,
      uptime: this.metrics.uptime
    };
  }

  getAlerts() {
    return this.alerts.slice(-20); // Last 20 alerts
  }

  clearAlerts() {
    this.alerts = [];
    console.log('🧹 Alerts cleared');
  }

  updateThresholds(newThresholds) {
    this.thresholds = { ...this.thresholds, ...newThresholds };
    console.log('⚙️ Thresholds updated:', this.thresholds);
  }
}

// Singleton instance
let monitoringBot = null;

function getMonitoringBot() {
  if (!monitoringBot) {
    monitoringBot = new MonitoringBot();
  }
  return monitoringBot;
}

module.exports = {
  MonitoringBot,
  getMonitoringBot
};
