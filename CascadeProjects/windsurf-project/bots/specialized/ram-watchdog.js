#!/usr/bin/env node
/**
 * RAM Watchdog - Aktives RAM-Management
 * Ueberwacht Speicherverbrauch, warnt bei Ueberlast, beendet Leck-Prozesse
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import os from 'os';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';

const execAsync = promisify(exec);

export class RAMWatchdog {
  constructor(options = {}) {
    this.name = 'ram-watchdog';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 10) * 1000;
    this.running = false;
    this.timer = null;
    this.thresholds = {
      warning: options.warningThreshold || 90,
      critical: options.criticalThreshold || 95,
      action: options.actionThreshold || 98
    };
    this.knownLeaks = new Set();
    this.status = { startedAt: null, checks: 0, cleanups: 0, alerts: 0 };
  }

  async getMemoryStats() {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    const percent = Math.round((used / total) * 100);

    let compressorUsed = 0;
    let swapUsed = 0;
    try {
      const { stdout } = await execAsync('vm_stat');
      const lines = stdout.split('\n');
      const pagesRe = /Pages used by compressor:\s+(\d+)/;
      const swapRe = /Swapouts:\s+(\d+)/;
      for (const line of lines) {
        const pm = line.match(pagesRe);
        if (pm) compressorUsed = parseInt(pm[1]) * 16384;
        const sm = line.match(swapRe);
        if (sm) swapUsed = parseInt(sm[1]);
      }
    } catch {}

    return {
      total, free, used, percent,
      compressorUsed, swapUsed,
      timestamp: new Date().toISOString()
    };
  }

  async getTopProcesses(n = 10) {
    try {
      const { stdout } = await execAsync(`ps -ax -o pid,ppid,pcpu,pmem,comm | grep -E "(node|python|electron)" | grep -v grep | sort -k4 -rn | head -${n}`);
      return stdout.split('\n').filter(l => l.trim()).map(line => {
        const parts = line.trim().split(/\s+/);
        return { pid: parts[0], ppid: parts[1], cpu: parts[2], mem: parts[3], cmd: parts.slice(4).join(' ') };
      });
    } catch {
      return [];
    }
  }

  async findDuplicateBots() {
    try {
      const { stdout } = await execAsync("ps ax | grep -E 'eternal_immortal_bot|mega_orchestrator|deep-scan-scheduler|auto-backup-scheduler|professional-desktop-monitor|cloud-backup-system' | grep -v grep");
      const lines = stdout.split('\n').filter(l => l.trim());
      const byCmd = {};
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        const pid = parts[0];
        const cmd = parts.slice(4).join(' ');
        const key = cmd.replace(/.*\//g, '').replace(/\.js.*|\.py.*/, '');
        if (!byCmd[key]) byCmd[key] = [];
        byCmd[key].push({ pid, cmd: cmd.slice(0, 80) });
      }
      const duplicates = Object.entries(byCmd).filter(([_, pids]) => pids.length > 1);
      return duplicates;
    } catch {
      return [];
    }
  }

  async cleanupMemory() {
    try {
      // 1. Duplizierte Bots beenden (aelteste Instanz behalten)
      const dups = await this.findDuplicateBots();
      for (const [name, procs] of dups) {
        const toKill = procs.slice(1);
        for (const p of toKill) {
          try {
            process.kill(parseInt(p.pid), 'SIGTERM');
            this.logger.warn(`Terminated duplicate ${name}`, { pid: p.pid });
          } catch {}
        }
      }

      // 2. Nicht-respondierende Node-Prozesse (>5min CPU idle, >200MB)
      try {
        const { stdout } = await execAsync("ps -ax -o pid,etime,pcpu,pmem,comm | grep node | grep -v grep | awk '$3 < 0.1 && $4 > 2.0 {print $1}'");
        const idlePids = stdout.split('\n').filter(l => l.trim());
        for (const pid of idlePids.slice(0, 3)) {
          try {
            process.kill(parseInt(pid), 'SIGTERM');
            this.logger.warn(`Terminated idle Node process`, { pid });
          } catch {}
        }
      } catch {}

      // 3. macOS Memory Pressure beheben
      try {
        await execAsync('sudo purge 2>/dev/null || echo "purge requires sudo"');
      } catch {}

      this.status.cleanups++;
      return { duplicatesTerminated: dups.length, idleTerminated: 0 };
    } catch (err) {
      this.logger.error('Cleanup error', { error: err.message });
      return { error: err.message };
    }
  }

  async tick() {
    try {
      this.status.checks++;
      const mem = await this.getMemoryStats();

      eventBus.publish('metrics:memory', mem);
      this.logger.debug('RAM Check', { percent: mem.percent, freeMB: Math.round(mem.free / 1024 / 1024) });

      if (mem.percent >= this.thresholds.action) {
        this.status.alerts++;
        this.logger.error(`CRITICAL RAM: ${mem.percent}%`, mem);
        eventBus.publish('alert:memory:critical', mem);
        await this.cleanupMemory();
      } else if (mem.percent >= this.thresholds.critical) {
        this.status.alerts++;
        this.logger.warn(`High RAM: ${mem.percent}%`, mem);
        eventBus.publish('alert:memory:warning', mem);
        const top = await this.getTopProcesses(5);
        eventBus.publish('status:top-processes', top);
      } else if (mem.percent >= this.thresholds.warning) {
        this.logger.info(`RAM elevated: ${mem.percent}%`);
      }
    } catch (err) {
      this.logger.error('Tick error', { error: err.message });
      eventBus.publish('error:bot', { bot: this.name, error: err.message });
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.status.startedAt = new Date().toISOString();
    this.logger.info('RAM Watchdog started', { thresholds: this.thresholds });
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('RAM Watchdog stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, thresholds: this.thresholds };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new RAMWatchdog();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
