/**
 * SuperMegaBot Bot Orchestrator
 * Koordiniert alle spezialisierten Bots
 */

const EventEmitter = require('events');
const { getMonitoringBot } = require('./monitoring-bot.cjs');
const { getRepairBot } = require('./repair-bot.cjs');
const { getMaintenanceBot } = require('./maintenance-bot.js');
const { getOptimizationBot } = require('./optimization-bot.js');

class BotOrchestrator extends EventEmitter {
  constructor() {
    super();
    this.name = 'BotOrchestrator';
    this.bots = new Map();
    this.isRunning = false;
    this.healthCheckInterval = 30000; // 30 Sekunden
    this.metrics = {
      totalBots: 0,
      activeBots: 0,
      totalRepairs: 0,
      totalAlerts: 0,
      uptime: 0
    };
  }

  async start() {
    if (this.isRunning) return;
    
    console.log('🎮 Bot Orchestrator starting...');
    this.isRunning = true;
    
    // Initialize all bots
    await this.initializeBots();
    
    // Start health monitoring
    this.startHealthMonitoring();
    
    // Start bot coordination
    this.startBotCoordination();
    
    console.log('✅ Bot Orchestrator started successfully');
    this.emit('started', { bot: this.name, timestamp: new Date() });
  }

  async stop() {
    if (!this.isRunning) return;
    
    console.log('🛑 Bot Orchestrator stopping...');
    this.isRunning = false;
    
    // Stop all bots
    for (const [name, bot] of this.bots) {
      try {
        await bot.stop();
        console.log(`✅ Stopped ${name}`);
      } catch (error) {
        console.error(`❌ Failed to stop ${name}:`, error);
      }
    }
    
    console.log('✅ Bot Orchestrator stopped');
    this.emit('stopped', { bot: this.name, timestamp: new Date() });
  }

  async initializeBots() {
    // Initialize Monitoring Bot
    const monitoringBot = getMonitoringBot();
    monitoringBot.on('metrics', (metrics) => {
      this.handleMonitoringMetrics(metrics);
    });
    
    monitoringBot.on('alerts', (alerts) => {
      this.handleMonitoringAlerts(alerts);
    });
    
    // Initialize Repair Bot
    const repairBot = getRepairBot();
    repairBot.on('repairStatus', (repairs) => {
      this.handleRepairStatus(repairs);
    });

    // Initialize Maintenance Bot
    const maintenanceBot = getMaintenanceBot();
    maintenanceBot.on('maintenanceStatus', (status) => {
      this.handleMaintenanceStatus(status);
    });

    // Initialize Optimization Bot
    const optimizationBot = getOptimizationBot();
    optimizationBot.on('optimizationStatus', (status) => {
      this.handleOptimizationStatus(status);
    });

    // Add bots to registry
    this.bots.set('MonitoringBot', monitoringBot);
    this.bots.set('RepairBot', repairBot);
    this.bots.set('MaintenanceBot', maintenanceBot);
    this.bots.set('OptimizationBot', optimizationBot);
    
    // Start all bots
    for (const [name, bot] of this.bots) {
      try {
        await bot.start();
        console.log(`✅ Started ${name}`);
        this.metrics.totalBots++;
        this.metrics.activeBots++;
      } catch (error) {
        console.error(`❌ Failed to start ${name}:`, error);
      }
    }
  }

  async startHealthMonitoring() {
    while (this.isRunning) {
      try {
        await this.checkBotHealth();
        await this.updateMetrics();
        
        // Emit health status
        this.emit('healthStatus', this.metrics);
        
      } catch (error) {
        console.error('❌ Health monitoring error:', error);
      }
      
      // Wait for next check
      await new Promise(resolve => setTimeout(resolve, this.healthCheckInterval));
    }
  }

  async startBotCoordination() {
    // Set up inter-bot communication
    const monitoringBot = this.bots.get('MonitoringBot');
    const repairBot = this.bots.get('RepairBot');
    
    // Monitoring -> Repair coordination
    monitoringBot.on('alerts', (alerts) => {
      const criticalAlerts = alerts.filter(alert => alert.level === 'critical');
      if (criticalAlerts.length > 0) {
        console.log('🚨 Critical alerts detected, triggering repair bot');
        repairBot.scanForIssues();
      }
    });
    
    // Repair -> Monitoring coordination
    repairBot.on('error', (error) => {
      console.log('🔧 Repair bot error, updating monitoring');
      monitoringBot.collectMetrics();
    });
  }

  async checkBotHealth() {
    for (const [name, bot] of this.bots) {
      try {
        // Check if bot is responsive
        if (bot.getMetrics) {
          const metrics = bot.getMetrics();
          if (!metrics.isRunning) {
            console.warn(`⚠️ ${name} is not running, attempting restart`);
            await this.restartBot(name);
          }
        }
      } catch (error) {
        console.error(`❌ Health check failed for ${name}:`, error);
        await this.restartBot(name);
      }
    }
  }

  async restartBot(botName) {
    const bot = this.bots.get(botName);
    if (!bot) return;
    
    try {
      console.log(`🔄 Restarting ${botName}...`);
      await bot.stop();
      await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds
      await bot.start();
      console.log(`✅ ${botName} restarted successfully`);
    } catch (error) {
      console.error(`❌ Failed to restart ${botName}:`, error);
    }
  }

  async updateMetrics() {
    this.metrics.uptime = process.uptime();
    this.metrics.activeBots = 0;
    
    for (const [name, bot] of this.bots) {
      if (bot.isRunning) {
        this.metrics.activeBots++;
      }
    }
    
    // Collect metrics from all bots
    const monitoringBot = this.bots.get('MonitoringBot');
    if (monitoringBot && monitoringBot.getMetrics) {
      const monitoringMetrics = monitoringBot.getMetrics();
      this.metrics.totalAlerts = monitoringMetrics.alerts.length;
    }
    
    const repairBot = this.bots.get('RepairBot');
    if (repairBot && repairBot.getRepairStatus) {
      const repairMetrics = repairBot.getRepairStatus();
      this.metrics.totalRepairs = repairMetrics.fixed;
    }
  }

  handleMonitoringMetrics(metrics) {
    // Emit metrics for external listeners
    this.emit('systemMetrics', {
      source: 'MonitoringBot',
      metrics,
      timestamp: new Date()
    });
    
    // Check for critical conditions
    if (metrics.memory > 90) {
      console.log('🚨 Critical memory usage detected');
      this.emit('criticalAlert', {
        type: 'memory',
        value: metrics.memory,
        timestamp: new Date()
      });
    }
  }

  handleMonitoringAlerts(alerts) {
    this.emit('systemAlerts', {
      source: 'MonitoringBot',
      alerts,
      timestamp: new Date()
    });
    
    // Count alerts by severity
    const criticalAlerts = alerts.filter(alert => alert.level === 'critical');
    if (criticalAlerts.length > 0) {
      console.log(`🚨 ${criticalAlerts.length} critical alerts detected`);
    }
  }

  handleRepairStatus(repairs) {
    this.emit('repairStatus', {
      source: 'RepairBot',
      repairs,
      timestamp: new Date()
    });

    if (repairs.fixed > 0) {
      console.log(`🔧 ${repairs.fixed} issues fixed`);
    }
  }

  handleMaintenanceStatus(status) {
    this.emit('maintenanceStatus', {
      source: 'MaintenanceBot',
      status,
      timestamp: new Date()
    });

    if (status.tasksCompleted > 0) {
      console.log(`🔨 ${status.tasksCompleted} maintenance tasks completed`);
    }
  }

  handleOptimizationStatus(status) {
    this.emit('optimizationStatus', {
      source: 'OptimizationBot',
      status,
      timestamp: new Date()
    });

    if (status.optimizationsApplied > 0) {
      console.log(`⚡ ${status.optimizationsApplied} optimizations applied`);
    }
  }

  getSystemStatus() {
    const botStatuses = {};
    
    for (const [name, bot] of this.bots) {
      botStatuses[name] = {
        isRunning: bot.isRunning,
        uptime: bot.uptime || 0,
        metrics: bot.getMetrics ? bot.getMetrics() : null
      };
    }
    
    return {
      orchestrator: {
        isRunning: this.isRunning,
        uptime: this.metrics.uptime,
        totalBots: this.metrics.totalBots,
        activeBots: this.metrics.activeBots
      },
      bots: botStatuses,
      system: {
        totalRepairs: this.metrics.totalRepairs,
        totalAlerts: this.metrics.totalAlerts
      }
    };
  }

  async executeCommand(command, params = {}) {
    switch (command) {
      case 'restart':
        if (params.botName) {
          await this.restartBot(params.botName);
        } else {
          await this.restartAllBots();
        }
        break;
        
      case 'status':
        return this.getSystemStatus();
        
      case 'health':
        return await this.checkBotHealth();
        
      case 'metrics':
        return this.metrics;
        
      case 'stop':
        if (params.botName) {
          const bot = this.bots.get(params.botName);
          if (bot) await bot.stop();
        } else {
          await this.stop();
        }
        break;
        
      case 'start':
        if (params.botName) {
          const bot = this.bots.get(params.botName);
          if (bot) await bot.start();
        } else {
          await this.start();
        }
        break;
        
      default:
        throw new Error(`Unknown command: ${command}`);
    }
  }

  async restartAllBots() {
    console.log('🔄 Restarting all bots...');
    
    for (const [name] of this.bots) {
      await this.restartBot(name);
    }
    
    console.log('✅ All bots restarted');
  }

  addBot(name, bot) {
    if (this.bots.has(name)) {
      throw new Error(`Bot ${name} already exists`);
    }
    
    this.bots.set(name, bot);
    this.metrics.totalBots++;
    
    if (this.isRunning) {
      bot.start();
      this.metrics.activeBots++;
    }
    
    console.log(`➕ Added bot: ${name}`);
  }

  removeBot(name) {
    const bot = this.bots.get(name);
    if (!bot) return;
    
    if (bot.isRunning) {
      bot.stop();
    }
    
    this.bots.delete(name);
    this.metrics.totalBots--;
    
    if (bot.isRunning) {
      this.metrics.activeBots--;
    }
    
    console.log(`➖ Removed bot: ${name}`);
  }

  getBotNames() {
    return Array.from(this.bots.keys());
  }

  getBot(name) {
    return this.bots.get(name);
  }
}

// Singleton instance
let botOrchestrator = null;

function getBotOrchestrator() {
  if (!botOrchestrator) {
    botOrchestrator = new BotOrchestrator();
  }
  return botOrchestrator;
}

module.exports = {
  BotOrchestrator,
  getBotOrchestrator
};
