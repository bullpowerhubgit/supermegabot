const fs = require('fs');
const path = require('path');

/**
 * Scheduler — Die 5 Dauer-Loops für AUTONOMOUS SETUP
 * 
 * 1. Monitoring Loop:     Alle 5 Minuten — Health, APIs, Security
 * 2. Research Loop:         Täglich 07:00 — Neue Releases, Doku-Änderungen
 * 3. Optimization Loop:   Täglich 08:00 — Kosten, Abos, ineffiziente Tools
 * 4. Execution Loop:        Kontinuierlich — Task Queue Verarbeitung
 * 5. Approval Loop:         Kontinuierlich — Freigaben prüfen, Escalation
 */

class Scheduler {
  constructor(options = {}) {
    this.orchestrator = options.orchestrator;
    this.logger = options.logger || console;
    this.storagePath = options.storagePath || path.join(__dirname, '../../state/scheduler');
    this.isRunning = false;
    this.intervals = {};
    
    this.ensureStorageDir();
    this.loadScheduleConfig();
  }

  ensureStorageDir() {
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
  }

  loadScheduleConfig() {
    const configPath = path.join(__dirname, '../../config/schedules.json');
    
    try {
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf8');
        this.config = JSON.parse(content);
      } else {
        this.createDefaultConfig(configPath);
      }
    } catch (err) {
      this.logger.error?.('scheduler.config.load_failed', { error: err.message });
      this.config = this.getDefaultConfig();
    }
  }

  createDefaultConfig(configPath) {
    const config = this.getDefaultConfig();
    const dir = path.dirname(configPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
    this.config = config;
  }

  getDefaultConfig() {
    return {
      monitoring_loop: {
        enabled: true,
        interval: '*/5 * * * *', // Every 5 minutes
        actions: ['health_check', 'api_validation', 'log_scan'],
        description: 'APIs, Server, Logs, Health, Response-Zeiten, Fehler'
      },
      research_loop: {
        enabled: true,
        interval: '0 7 * * *', // Daily at 07:00
        actions: ['check_releases', 'check_documentation', 'scan_new_sources'],
        description: 'Neue APIs, Dokumentationsänderungen, Anbieteränderungen'
      },
      optimization_loop: {
        enabled: true,
        interval: '0 8 * * *', // Daily at 08:00
        actions: ['cost_analysis', 'subscription_audit', 'unused_tools_scan'],
        description: 'Kosten, Reibung, unnötige Tools, ineffiziente Abos'
      },
      security_weekly: {
        enabled: true,
        interval: '0 6 * * 1', // Weekly Monday at 06:00
        actions: ['security_scan', 'deep_scan', 'dependency_check'],
        description: 'Wöchentliche Sicherheitsprüfung'
      },
      daily_summary: {
        enabled: true,
        interval: '0 20 * * *', // Daily at 20:00
        actions: ['daily_report', 'executive_summary'],
        description: 'Täglicher Zusammenfassungsbericht'
      },
      execution_loop: {
        enabled: true,
        interval: '*/30 * * * * *', // Every 30 seconds (cron-like)
        actions: ['process_queue', 'cleanup_tasks'],
        description: 'Task Queue Verarbeitung'
      },
      approval_loop: {
        enabled: true,
        interval: '*/60 * * * * *', // Every 60 seconds
        actions: ['cleanup_expired_approvals', 'escalate_pending'],
        description: 'Freigaben prüfen, Escalation'
      }
    };
  }

  /**
   * Start all enabled loops
   */
  start() {
    if (this.isRunning) {
      this.logger.warn?.('scheduler.already_running');
      return;
    }

    this.isRunning = true;
    this.logger.info?.('scheduler.started');

    // Start each configured loop
    for (const [loopName, loopConfig] of Object.entries(this.config)) {
      if (loopConfig.enabled) {
        this.startLoop(loopName, loopConfig);
      }
    }
  }

  /**
   * Start a single loop
   */
  startLoop(loopName, loopConfig) {
    const intervalMs = this.parseInterval(loopConfig.interval);
    
    this.intervals[loopName] = setInterval(async () => {
      await this.executeLoop(loopName, loopConfig);
    }, intervalMs);

    this.logger.info?.('scheduler.loop.started', {
      loop: loopName,
      interval: loopConfig.interval,
      intervalMs
    });
  }

  /**
   * Parse cron-like interval to milliseconds
   * Supports: cron syntax and special shortcuts
   */
  parseInterval(interval) {
    // Special shortcuts
    if (interval === '*/5 * * * *') return 5 * 60 * 1000; // 5 minutes
    if (interval === '0 7 * * *') return 24 * 60 * 60 * 1000; // 24 hours (simplified)
    if (interval === '0 8 * * *') return 24 * 60 * 60 * 1000;
    if (interval === '0 6 * * 1') return 7 * 24 * 60 * 60 * 1000; // 7 days
    if (interval === '0 20 * * *') return 24 * 60 * 60 * 1000;
    if (interval === '*/30 * * * * *') return 30 * 1000; // 30 seconds
    if (interval === '*/60 * * * * *') return 60 * 1000; // 60 seconds
    
    // Default: parse as seconds if numeric
    const numericValue = parseInt(interval, 10);
    if (!isNaN(numericValue) && numericValue > 0) {
      return numericValue * 1000;
    }

    // Fallback: 5 minutes
    return 5 * 60 * 1000;
  }

  /**
   * Execute a single loop iteration
   */
  async executeLoop(loopName, loopConfig) {
    const runId = `run-${Date.now()}`;
    
    this.logger.info?.('scheduler.loop.executing', {
      loop: loopName,
      runId,
      actions: loopConfig.actions
    });

    for (const action of loopConfig.actions) {
      try {
        await this.executeAction(action, loopName, runId);
      } catch (err) {
        this.logger.error?.('scheduler.loop.action_failed', {
          loop: loopName,
          action,
          runId,
          error: err.message
        });
      }
    }

    this.logger.info?.('scheduler.loop.completed', {
      loop: loopName,
      runId
    });
  }

  /**
   * Execute a single action via the orchestrator
   */
  async executeAction(action, loopName, runId) {
    if (!this.orchestrator) {
      this.logger.warn?.('scheduler.no_orchestrator', { action });
      return;
    }

    // Submit as event to orchestrator
    const result = await this.orchestrator.submitEvent(action, 'scheduler');
    
    this.logger.info?.('scheduler.action.completed', {
      action,
      loop: loopName,
      runId,
      result: result.status
    });
  }

  /**
   * Stop all loops
   */
  stop() {
    this.isRunning = false;
    
    for (const [loopName, interval] of Object.entries(this.intervals)) {
      clearInterval(interval);
      this.logger.info?.('scheduler.loop.stopped', { loop: loopName });
    }
    
    this.intervals = {};
    this.logger.info?.('scheduler.stopped');
  }

  /**
   * Get current status
   */
  getStatus() {
    return {
      isRunning: this.isRunning,
      activeLoops: Object.keys(this.intervals),
      config: Object.entries(this.config).map(([name, config]) => ({
        name,
        enabled: config.enabled,
        interval: config.interval,
        actions: config.actions
      }))
    };
  }

  /**
   * Enable/disable a specific loop
   */
  setLoopState(loopName, enabled) {
    if (this.config[loopName]) {
      this.config[loopName].enabled = enabled;
      
      if (enabled && !this.intervals[loopName]) {
        this.startLoop(loopName, this.config[loopName]);
      } else if (!enabled && this.intervals[loopName]) {
        clearInterval(this.intervals[loopName]);
        delete this.intervals[loopName];
      }
      
      this.logger.info?.('scheduler.loop.state_changed', { loop: loopName, enabled });
    }
  }

  /**
   * Execute a loop immediately (for testing or manual triggers)
   */
  async triggerLoop(loopName) {
    const loopConfig = this.config[loopName];
    if (!loopConfig) {
      throw new Error(`Loop ${loopName} not found`);
    }

    this.logger.info?.('scheduler.loop.manual_trigger', { loop: loopName });
    await this.executeLoop(loopName, loopConfig);
  }
}

module.exports = { Scheduler };
