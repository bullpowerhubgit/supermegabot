#!/usr/bin/env node
/**
 * Unified Bot Orchestrator
 * Koordiniert alle 5 spezialisierten Bots:
 * - monitoring-bot
 * - error-detection-bot
 * - repair-bot
 * - maintenance-bot
 * - optimization-bot
 */

import { MonitoringBot } from './specialized/monitoring-bot.js';
import { ErrorDetectionBot } from './specialized/error-detection-bot.js';
import { RepairBot } from './specialized/repair-bot.js';
import { MaintenanceBot } from './specialized/maintenance-bot.js';
import { OptimizationBot } from './specialized/optimization-bot.js';
import { RAMWatchdog } from './specialized/ram-watchdog.js';
import { UnifiedLogger } from './shared/unified-logger.js';
import { eventBus } from './shared/event-bus.js';

export class UnifiedOrchestrator {
  constructor() {
    this.name = 'unified-orchestrator';
    this.logger = new UnifiedLogger({ name: this.name });
    this.bots = new Map();
    this.running = false;
    this.startTime = null;
    this.registerBots();
    this.setupEventListeners();
  }

  registerBots() {
    this.bots.set('monitoring', { instance: new MonitoringBot(), description: 'Systemueberwachung und API-Health' });
    this.bots.set('error-detection', { instance: new ErrorDetectionBot(), description: 'Fehlererkennung in Logs und Prozessen' });
    this.bots.set('repair', { instance: new RepairBot(), description: 'Automatische Fehlerbehebung' });
    this.bots.set('maintenance', { instance: new MaintenanceBot(), description: 'Wartung, Health-Checks, Backups' });
    this.bots.set('optimization', { instance: new OptimizationBot(), description: 'Performance und Conversion-Optimierung' });
    this.bots.set('ram-watchdog', { instance: new RAMWatchdog(), description: 'Aktives RAM-Management und Memory-Cleanup' });
  }

  setupEventListeners() {
    eventBus.subscribe('alert:critical', (data) => {
      this.logger.error('CRITICAL alert received', { count: data.length });
      const repair = this.bots.get('repair');
      if (repair && repair.instance.running) {
        this.logger.info('Triggering repair bot for critical alerts');
      }
    });

    eventBus.subscribe('alert:threshold', (data) => {
      this.logger.warn('Threshold alert', data);
    });

    eventBus.subscribe('error:bot', (data) => {
      this.logger.error(`Bot error: ${data.bot}`, { error: data.error });
    });

    eventBus.subscribe('alert:memory:critical', (data) => {
      this.logger.error('CRITICAL RAM alert', data);
      const repair = this.bots.get('repair');
      if (repair && repair.instance.running) {
        this.logger.info('Triggered repair bot after memory critical');
      }
    });

    eventBus.subscribe('*', ({ event, data }) => {
      if (event.startsWith('bot:')) return;
      this.logger.debug(`Event: ${event}`);
    });
  }

  startBot(name) {
    const bot = this.bots.get(name);
    if (!bot) {
      this.logger.error(`Unknown bot: ${name}`);
      return false;
    }
    if (bot.instance.running) {
      this.logger.warn(`Bot ${name} already running`);
      return false;
    }
    bot.instance.start();
    this.logger.info(`Started ${name}`);
    return true;
  }

  stopBot(name) {
    const bot = this.bots.get(name);
    if (!bot) return false;
    if (!bot.instance.running) return false;
    bot.instance.stop();
    this.logger.info(`Stopped ${name}`);
    return true;
  }

  startAll() {
    this.running = true;
    this.startTime = new Date().toISOString();
    this.logger.info('=== Starting all specialized bots ===');
    for (const [name, bot] of this.bots) {
      try {
        bot.instance.start();
      } catch (err) {
        this.logger.error(`Failed to start ${name}`, { error: err.message });
      }
    }
    eventBus.publish('orchestrator:started', { bots: Array.from(this.bots.keys()), time: this.startTime });
  }

  stopAll() {
    this.logger.info('=== Stopping all specialized bots ===');
    for (const [name, bot] of this.bots) {
      try {
        bot.instance.stop();
      } catch (err) {
        this.logger.error(`Failed to stop ${name}`, { error: err.message });
      }
    }
    this.running = false;
    eventBus.publish('orchestrator:stopped', { time: new Date().toISOString() });
  }

  getStatus() {
    const statuses = {};
    for (const [name, bot] of this.bots) {
      statuses[name] = {
        running: bot.instance.running,
        ...bot.instance.getStatus()
      };
    }
    return {
      orchestrator: this.name,
      running: this.running,
      startTime: this.startTime,
      bots: statuses,
      uptime: this.startTime ? Date.now() - new Date(this.startTime).getTime() : 0
    };
  }

  printStatus() {
    const status = this.getStatus();
    console.log('\n=== Bot Orchestrator Status ===');
    console.log(`Orchestrator: ${status.running ? 'RUNNING' : 'STOPPED'}`);
    console.log(`Uptime: ${status.uptime ? (status.uptime / 1000).toFixed(0) + 's' : 'N/A'}`);
    const ramBot = status.bots['ram-watchdog'];
    if (ramBot && ramBot.lastMetrics) {
      const r = ramBot.lastMetrics;
      const bar = '█'.repeat(Math.round(r.percent / 10)) + '░'.repeat(10 - Math.round(r.percent / 10));
      console.log(`RAM: ${bar} ${r.percent}% (${Math.round(r.free / 1024 / 1024)}MB free)`);
    }
    console.log('\nBots:');
    for (const [name, s] of Object.entries(status.bots)) {
      const emoji = s.running ? '\u2705' : '\u274c';
      console.log(`  ${emoji} ${name.padEnd(18)} | ${s.running ? 'RUNNING' : 'STOPPED'}`);
    }
    console.log('');
  }
}

// CLI
if (import.meta.url === `file://${process.argv[1]}`) {
  const orchestrator = new UnifiedOrchestrator();
  const command = process.argv[2];

  switch (command) {
    case 'start':
    case 'start-all':
      orchestrator.startAll();
      setInterval(() => orchestrator.printStatus(), 30000);
      break;
    case 'stop':
    case 'stop-all':
      orchestrator.stopAll();
      process.exit(0);
      break;
    case 'status':
      orchestrator.printStatus();
      process.exit(0);
      break;
    case 'start-bot':
      orchestrator.startBot(process.argv[3]);
      break;
    case 'stop-bot':
      orchestrator.stopBot(process.argv[3]);
      break;
    default:
      console.log('Usage: node bots/unified-orchestrator.js [start-all|stop-all|status|start-bot <name>|stop-bot <name>]');
      console.log('Bots: monitoring, error-detection, repair, maintenance, optimization, ram-watchdog');
      process.exit(0);
  }

  process.on('SIGINT', () => {
    orchestrator.stopAll();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    orchestrator.stopAll();
    process.exit(0);
  });
}
