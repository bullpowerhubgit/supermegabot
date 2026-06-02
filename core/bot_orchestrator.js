/**
 * SuperMegaBot Bot Orchestrator - Zentrale Bot-Steuerung
 * Zuständig: Bot-Koordination, Load-Balancing, Health-Management
 */

import MonitorBot from './monitor-bot.js';
import APIHealthBot from './api-health-bot.js';
import FixerBot from './fixer-bot.js';
import OptimizerBot from './optimizer-bot.js';
import MaintenanceBot from './maintenance-bot.js';

class BotOrchestrator {
  constructor() {
    this.name = 'BotOrchestrator';
    this.bots = new Map();
    this.isRunning = false;
    this.startTime = Date.now();
  }

  async start() {
    console.log(`🎯 ${this.name} starting all bots...`);
    this.isRunning = true;

    // Bots initialisieren und starten
    await this.startBot('monitor', new MonitorBot());
    await this.startBot('api-health', new APIHealthBot());
    await this.startBot('fixer', new FixerBot());
    await this.startBot('optimizer', new OptimizerBot());
    await this.startBot('maintenance', new MaintenanceBot());

    // Orchestrator Loop
    this.orchestratorInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      await this.checkBotHealth();
      await this.balanceLoad();
      await this.reportStatus();
    }, 30000); // 30 Sekunden

    console.log(`✅ ${this.name} started with ${this.bots.size} bots`);
    this.setupGracefulShutdown();
  }

  async startBot(name, bot) {
    try {
      await bot.start();
      this.bots.set(name, {
        instance: bot,
        startTime: Date.now(),
        status: 'running',
        restarts: 0,
        lastHealthCheck: Date.now()
      });
      console.log(`✅ Bot started: ${name}`);
    } catch (error) {
      console.error(`❌ Failed to start bot ${name}:`, error.message);
      this.bots.set(name, {
        instance: bot,
        startTime: Date.now(),
        status: 'failed',
        restarts: 0,
        lastHealthCheck: Date.now(),
        error: error.message
      });
    }
  }

  async checkBotHealth() {
    for (const [name, botInfo] of this.bots) {
      try {
        const status = botInfo.instance.getStatus();
        botInfo.lastHealthCheck = Date.now();
        
        if (!status.isRunning && botInfo.status === 'running') {
          console.log(`🚨 Bot ${name} stopped unexpectedly`);
          await this.restartBot(name);
        }
        
        botInfo.status = status.isRunning ? 'running' : 'stopped';
      } catch (error) {
        console.error(`❌ Health check failed for bot ${name}:`, error.message);
        botInfo.status = 'error';
      }
    }
  }

  async restartBot(name) {
    const botInfo = this.bots.get(name);
    if (!botInfo) return;

    console.log(`🔄 Restarting bot: ${name}`);
    
    try {
      await botInfo.instance.stop();
      await new Promise(resolve => setTimeout(resolve, 2000)); // 2 Sekunden warten
      await botInfo.instance.start();
      
      botInfo.restarts++;
      botInfo.startTime = Date.now();
      botInfo.status = 'running';
      
      console.log(`✅ Bot restarted: ${name} (restart #${botInfo.restarts})`);
    } catch (error) {
      console.error(`❌ Failed to restart bot ${name}:`, error.message);
      botInfo.status = 'failed';
    }
  }

  async balanceLoad() {
    const systemLoad = this.getSystemLoad();
    
    // Bei hoher Systemlast Bots pausieren
    if (systemLoad.memory > 85) {
      console.log(`⚠️ High memory usage (${systemLoad.memory}%), pausing non-critical bots`);
      await this.pauseNonCriticalBots();
    }
    
    // Bei niedriger Systemlast alle Bots wieder aktivieren
    if (systemLoad.memory < 70) {
      await this.resumeAllBots();
    }
  }

  getSystemLoad() {
    const memUsage = process.memoryUsage();
    const memoryUsage = (memUsage.heapUsed / memUsage.heapTotal) * 100;
    
    return {
      memory: memoryUsage.toFixed(2),
      uptime: process.uptime(),
      bots: this.bots.size
    };
  }

  async pauseNonCriticalBots() {
    // Monitor Bot ist kritisch, API Health Bot kann pausiert werden
    const apiHealthBot = this.bots.get('api-health');
    if (apiHealthBot && apiHealthBot.status === 'running') {
      await apiHealthBot.instance.stop();
      apiHealthBot.status = 'paused';
      console.log(`⏸️ Paused bot: api-health`);
    }
  }

  async resumeAllBots() {
    for (const [name, botInfo] of this.bots) {
      if (botInfo.status === 'paused') {
        try {
          await botInfo.instance.start();
          botInfo.status = 'running';
          console.log(`▶️ Resumed bot: ${name}`);
        } catch (error) {
          console.error(`❌ Failed to resume bot ${name}:`, error.message);
        }
      }
    }
  }

  async reportStatus() {
    const status = {
      orchestrator: {
        name: this.name,
        uptime: Date.now() - this.startTime,
        isRunning: this.isRunning,
        bots: this.bots.size
      },
      bots: {},
      system: this.getSystemLoad(),
      timestamp: new Date().toISOString()
    };

    for (const [name, botInfo] of this.bots) {
      try {
        status.bots[name] = {
          status: botInfo.status,
          uptime: Date.now() - botInfo.startTime,
          restarts: botInfo.restarts,
          lastHealthCheck: botInfo.lastHealthCheck,
          error: botInfo.error || null
        };
      } catch (error) {
        status.bots[name] = {
          status: 'error',
          error: error.message
        };
      }
    }

    // Status loggen
    console.log(`📊 Bot Status Report: ${JSON.stringify(status, null, 2)}`);
    
    // In Datei schreiben
    const fs = await import('fs');
    try {
      fs.appendFileSync('./logs/bot-status.log', JSON.stringify(status) + '\n');
    } catch (error) {
      console.error('Failed to write status log:', error.message);
    }

    return status;
  }

  setupGracefulShutdown() {
    const shutdown = async () => {
      console.log(`🛑 ${this.name} shutting down all bots...`);
      this.isRunning = false;
      
      // Alle Bots stoppen
      for (const [name, botInfo] of this.bots) {
        try {
          await botInfo.instance.stop();
          console.log(`✅ Bot stopped: ${name}`);
        } catch (error) {
          console.error(`❌ Failed to stop bot ${name}:`, error.message);
        }
      }
      
      clearInterval(this.orchestratorInterval);
      console.log(`✅ ${this.name} shutdown complete`);
      process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  }

  async stop() {
    this.isRunning = false;
    clearInterval(this.orchestratorInterval);
    
    for (const [name, botInfo] of this.bots) {
      try {
        await botInfo.instance.stop();
      } catch (error) {
        console.error(`Failed to stop bot ${name}:`, error.message);
      }
    }
  }

  getStatus() {
    return this.reportStatus();
  }

  getBotCount() {
    return this.bots.size;
  }

  getRunningBots() {
    return Array.from(this.bots.entries())
      .filter(([name, info]) => info.status === 'running')
      .map(([name]) => name);
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const orchestrator = new BotOrchestrator();
  orchestrator.start();
}

export default BotOrchestrator;
