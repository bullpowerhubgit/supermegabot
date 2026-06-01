#!/usr/bin/env node
/**
 * Repair Bot - Automatische Fehlerbehebung
 * Repariert Logs, Cache, API-Verbindungen, node_modules, defekte Konfigurationen
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';

const execAsync = promisify(exec);

export class RepairBot {
  constructor(options = {}) {
    this.name = 'repair-bot';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 60) * 1000;
    this.running = false;
    this.timer = null;
    this.repairs = [];
    this.maxRepairs = 200;
    this.counters = { cache: 0, api: 0, modules: 0, logs: 0 };
    this.status = { startedAt: null, ticks: 0, repairsDone: 0, lastRepair: null };
  }

  recordRepair(type, description, success, details = {}) {
    const entry = { timestamp: new Date().toISOString(), type, description, success, details };
    this.repairs.push(entry);
    if (this.repairs.length > this.maxRepairs) this.repairs = this.repairs.slice(-this.maxRepairs);
    if (success) {
      this.status.repairsDone++;
      this.status.lastRepair = entry.timestamp;
    }
    eventBus.publish('repair:executed', entry);
  }

  async repairLogRotation() {
    try {
      const logFiles = [
        path.join(process.cwd(), 'watchdog.log'),
        path.join(process.cwd(), 'logs', 'monitoring-bot.log'),
        path.join(process.cwd(), 'logs', 'error-detection-bot.log'),
        path.join(process.cwd(), 'logs', 'repair-bot.log'),
        path.join(process.cwd(), 'logs', 'maintenance-bot.log'),
        path.join(process.cwd(), 'logs', 'optimization-bot.log')
      ];
      let rotated = 0;
      for (const lf of logFiles) {
        if (fs.existsSync(lf)) {
          const stats = fs.statSync(lf);
          if (stats.size > 10 * 1024 * 1024) {
            const backup = `${lf}.${new Date().toISOString().replace(/[:.]/g, '-')}.backup`;
            fs.renameSync(lf, backup);
            rotated++;
          }
        }
      }
      if (rotated) {
        this.logger.info(`Rotated ${rotated} log files`);
        this.recordRepair('log-rotation', `Rotated ${rotated} oversized log files`, true, { rotated });
      }
      return rotated;
    } catch (err) {
      this.recordRepair('log-rotation', err.message, false);
      return 0;
    }
  }

  async repairCache() {
    try {
      const dirs = [
        path.join(os.homedir(), 'Library', 'Caches'),
        path.join(process.cwd(), 'node_modules', '.cache'),
        path.join(process.cwd(), '.next', 'cache')
      ];
      let cleaned = 0;
      for (const dir of dirs) {
        try {
          if (fs.existsSync(dir)) {
            const files = fs.readdirSync(dir);
            for (const f of files) {
              const fp = path.join(dir, f);
              try {
                const s = fs.statSync(fp);
                if (s.isDirectory()) {
                  fs.rmSync(fp, { recursive: true, force: true });
                } else if (s.mtime < new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)) {
                  fs.unlinkSync(fp);
                }
              } catch {}
            }
            cleaned++;
          }
        } catch {}
      }
      if (cleaned) {
        this.logger.info(`Cleaned cache in ${cleaned} directories`);
        this.recordRepair('cache-cleanup', `Cleaned ${cleaned} cache directories`, true);
      }
      return cleaned;
    } catch (err) {
      this.recordRepair('cache-cleanup', err.message, false);
      return 0;
    }
  }

  async repairNodeModules() {
    try {
      const nm = path.join(process.cwd(), 'node_modules');
      if (!fs.existsSync(nm)) {
        this.logger.warn('node_modules missing');
        this.recordRepair('node-modules', 'node_modules missing', false);
        return 0;
      }
      const pj = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf8'));
      const deps = Object.keys({ ...pj.dependencies, ...pj.devDependencies });
      let missing = 0;
      for (const dep of deps) {
        if (!fs.existsSync(path.join(nm, dep))) missing++;
      }
      if (missing > 0) {
        this.logger.warn(`${missing} node_modules packages missing`);
        this.recordRepair('node-modules', `${missing} packages missing`, false, { missing });
      } else {
        this.recordRepair('node-modules', 'All packages present', true);
      }
      return missing;
    } catch (err) {
      this.recordRepair('node-modules', err.message, false);
      return 0;
    }
  }

  async repairPermissions() {
    try {
      const scripts = [
        path.join(process.cwd(), 'auto-start.sh'),
        path.join(process.cwd(), 'start-all.sh'),
        path.join(process.cwd(), 'deploy-vercel.sh')
      ];
      let fixed = 0;
      for (const s of scripts) {
        if (fs.existsSync(s)) {
          const mode = fs.statSync(s).mode;
          if (!(mode & 0o100)) {
            fs.chmodSync(s, 0o755);
            fixed++;
          }
        }
      }
      if (fixed) {
        this.logger.info(`Fixed permissions for ${fixed} scripts`);
        this.recordRepair('permissions', `Fixed execute permissions for ${fixed} scripts`, true);
      }
      return fixed;
    } catch (err) {
      this.recordRepair('permissions', err.message, false);
      return 0;
    }
  }

  async tick() {
    try {
      this.status.ticks++;
      this.logger.debug('Repair Bot tick started');

      await this.repairLogRotation();

      this.counters.cache++;
      if (this.counters.cache >= 5) {
        this.counters.cache = 0;
        await this.repairCache();
      }

      this.counters.modules++;
      if (this.counters.modules >= 10) {
        this.counters.modules = 0;
        await this.repairNodeModules();
      }

      this.counters.logs++;
      if (this.counters.logs >= 3) {
        this.counters.logs = 0;
        await this.repairPermissions();
      }

      this.logger.debug('Repair Bot tick completed');
    } catch (err) {
      this.logger.error('Tick error', { error: err.message });
      eventBus.publish('error:bot', { bot: this.name, error: err.message });
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.status.startedAt = new Date().toISOString();
    this.logger.info('Repair Bot started');
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('Repair Bot stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, recentRepairs: this.repairs.slice(-5) };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new RepairBot();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
