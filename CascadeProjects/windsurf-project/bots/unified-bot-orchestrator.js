#!/usr/bin/env node
/**
 * Unified Bot Orchestrator - Zentrale Bot-Koordination
 * Koordiniert alle spezialisierten Bots, verwaltet Status, Events und Fallbacks
 */

import { MonitoringBot } from './specialized/monitoring-bot.js';
import { RepairBot } from './specialized/repair-bot.js';
import { OptimizationBot } from './specialized/optimization-bot.js';
import { ErrorDetectionBot } from './specialized/error-detection-bot.js';
import { MaintenanceBot } from './specialized/maintenance-bot.js';
import { UnifiedLogger } from './shared/unified-logger.js';
import { eventBus } from './shared/event-bus.js';

export class UnifiedBotOrchestrator {
  constructor(options = {}) {
    this.name = 'unified-bot-orchestrator';
    this.logger = new UnifiedLogger({ name: this.name });
    this.bots = new Map();
    this.running = false;
    this.status = {
      startedAt: null,
      totalBots: 0,
      activeBots: 0,
      totalEvents: 0,
      criticalAlerts: 0,
      lastHealthCheck: null
    };
    this.healthCheckInterval = options.healthCheckInterval || 60000;
    this.healthCheckTimer = null;
    
    this.initializeBots(options);
    this.setupEventSubscriptions();
  }

  initializeBots(options) {
    const botConfigs = {
      monitoring: { class: MonitoringBot, interval: 30, priority: 'high' },
      repair: { class: RepairBot, interval: 60, priority: 'medium' },
      optimization: { class: OptimizationBot, interval: 300, priority: 'low' },
      errorDetection: { class: ErrorDetectionBot, interval: 45, priority: 'high' },
      maintenance: { class: MaintenanceBot, interval: 120, priority: 'medium' }
    };

    for (const [name, config] of Object.entries(botConfigs)) {
      try {
        const bot = new config.class({
          interval: config.interval,
          ...options[name]
        });
        this.bots.set(name, {
          instance: bot,
          config,
          status: 'stopped',
          lastError: null,
          restartCount: 0
        });
        this.logger.info(`Bot initialized: ${name}`);
      } catch (err) {
        this.logger.error(`Failed to initialize bot: ${name}`, { error: err.message });
      }
    }

    this.status.totalBots = this.bots.size;
  }

  setupEventSubscriptions() {
    eventBus.subscribe('bot:started', (data) => {
      const botEntry = this.bots.get(data.bot);
      if (botEntry) {
        botEntry.status = 'running';
        botEntry.lastError = null;
        this.status.activeBots = Array.from(this.bots.values()).filter(b => b.status === 'running').length;
        this.logger.info(`Bot started: ${data.bot}`, { activeBots: this.status.activeBots });
      }
    });

    eventBus.subscribe('bot:stopped', (data) => {
      const botEntry = this.bots.get(data.bot);
      if (botEntry) {
        botEntry.status = 'stopped';
        this.status.activeBots = Array.from(this.bots.values()).filter(b => b.status === 'running').length;
        this.logger.info(`Bot stopped: ${data.bot}`, { activeBots: this.status.activeBots });
      }
    });

    eventBus.subscribe('error:bot', (data) => {
      const botEntry = this.bots.get(data.bot);
      if (botEntry) {
        botEntry.lastError = data.error;
        botEntry.restartCount++;
        this.logger.error(`Bot error: ${data.bot}`, { error: data.error, restartCount: botEntry.restartCount });
        
        if (botEntry.restartCount > 3) {
          this.logger.critical(`Bot ${data.bot} requires manual intervention`, { restartCount: botEntry.restartCount });
          eventBus.publish('alert:critical', { 
            type: 'bot-failure', 
            bot: data.bot, 
            restartCount: botEntry.restartCount 
          });
        }
      }
    });

    eventBus.subscribe('alert:critical', (data) => {
      this.status.criticalAlerts++;
      this.logger.critical('Critical alert received', data);
      
      if (data.type === 'bot-failure') {
        this.handleBotFailure(data.bot);
      }
    });

    eventBus.subscribe('*', (data) => {
      this.status.totalEvents++;
    });
  }

  async handleBotFailure(botName) {
    const botEntry = this.bots.get(botName);
    if (!botEntry) return;

    this.logger.warn(`Attempting to recover failed bot: ${botName}`);
    
    try {
      botEntry.instance.stop();
      await new Promise(resolve => setTimeout(resolve, 2000));
      botEntry.instance.start();
      botEntry.restartCount = 0;
      this.logger.info(`Bot recovered: ${botName}`);
    } catch (err) {
      this.logger.error(`Failed to recover bot: ${botName}`, { error: err.message });
    }
  }

  async startBot(botName) {
    const botEntry = this.bots.get(botName);
    if (!botEntry) {
      this.logger.error(`Bot not found: ${botName}`);
      return false;
    }

    if (botEntry.status === 'running') {
      this.logger.warn(`Bot already running: ${botName}`);
      return true;
    }

    try {
      botEntry.instance.start();
      return true;
    } catch (err) {
      this.logger.error(`Failed to start bot: ${botName}`, { error: err.message });
      return false;
    }
  }

  async stopBot(botName) {
    const botEntry = this.bots.get(botName);
    if (!botEntry) {
      this.logger.error(`Bot not found: ${botName}`);
      return false;
    }

    if (botEntry.status === 'stopped') {
      this.logger.warn(`Bot already stopped: ${botName}`);
      return true;
    }

    try {
      botEntry.instance.stop();
      return true;
    } catch (err) {
      this.logger.error(`Failed to stop bot: ${botName}`, { error: err.message });
      return false;
    }
  }

  async startAll() {
    if (this.running) {
      this.logger.warn('Orchestrator already running');
      return;
    }

    this.running = true;
    this.status.startedAt = new Date().toISOString();
    this.logger.info('Starting all bots...');

    const startOrder = ['monitoring', 'errorDetection', 'repair', 'maintenance', 'optimization'];
    const results = {};

    for (const botName of startOrder) {
      results[botName] = await this.startBot(botName);
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    this.startHealthChecks();
    this.logger.info('All bots started', { results });
    return results;
  }

  async stopAll() {
    if (!this.running) {
      this.logger.warn('Orchestrator not running');
      return;
    }

    this.running = false;
    this.stopHealthChecks();
    this.logger.info('Stopping all bots...');

    const stopOrder = ['optimization', 'maintenance', 'repair', 'errorDetection', 'monitoring'];
    const results = {};

    for (const botName of stopOrder) {
      results[botName] = await this.stopBot(botName);
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    this.logger.info('All bots stopped', { results });
    return results;
  }

  startHealthChecks() {
    this.healthCheckTimer = setInterval(() => {
      this.performHealthCheck();
    }, this.healthCheckInterval);
  }

  stopHealthChecks() {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }
  }

  async performHealthCheck() {
    this.status.lastHealthCheck = new Date().toISOString();
    const healthStatus = {};

    for (const [name, botEntry] of this.bots) {
      try {
        const botStatus = botEntry.instance.getStatus();
        healthStatus[name] = {
          status: botEntry.status,
          running: botStatus.running,
          lastError: botEntry.lastError,
          restartCount: botEntry.restartCount
        };

        if (!botStatus.running && botEntry.config.priority === 'high') {
          this.logger.warn(`High-priority bot not running: ${name}`);
          await this.startBot(name);
        }
      } catch (err) {
        healthStatus[name] = { error: err.message };
      }
    }

    eventBus.publish('orchestrator:health-check', { 
      timestamp: this.status.lastHealthCheck,
      healthStatus,
      activeBots: this.status.activeBots,
      criticalAlerts: this.status.criticalAlerts
    });

    return healthStatus;
  }

  getOverallStatus() {
    const botStatuses = {};
    for (const [name, botEntry] of this.bots) {
      try {
        botStatuses[name] = {
          ...botEntry.instance.getStatus(),
          orchestratorStatus: botEntry.status,
          restartCount: botEntry.restartCount,
          priority: botEntry.config.priority
        };
      } catch (err) {
        botStatuses[name] = { error: err.message };
      }
    }

    return {
      orchestrator: {
        ...this.status,
        running: this.running
      },
      bots: botStatuses,
      eventHistory: eventBus.getRecent(null, 20)
    };
  }

  getBotStatus(botName) {
    const botEntry = this.bots.get(botName);
    if (!botEntry) {
      return { error: 'Bot not found' };
    }

    try {
      return {
        ...botEntry.instance.getStatus(),
        orchestratorStatus: botEntry.status,
        restartCount: botEntry.restartCount,
        priority: botEntry.config.priority
      };
    } catch (err) {
      return { error: err.message };
    }
  }

  async restartBot(botName) {
    await this.stopBot(botName);
    await new Promise(resolve => setTimeout(resolve, 1000));
    return await this.startBot(botName);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const orchestrator = new UnifiedBotOrchestrator();
  
  orchestrator.startAll();
  
  process.on('SIGINT', async () => {
    console.log('\nShutting down orchestrator...');
    await orchestrator.stopAll();
    process.exit(0);
  });
  
  process.on('SIGTERM', async () => {
    await orchestrator.stopAll();
    process.exit(0);
  });

  process.on('message', (msg) => {
    if (msg.command === 'status') {
      process.send(orchestrator.getOverallStatus());
    } else if (msg.command === 'restart') {
      orchestrator.restartBot(msg.bot).then(result => {
        process.send({ command: 'restart', bot: msg.bot, result });
      });
    }
  });
}
