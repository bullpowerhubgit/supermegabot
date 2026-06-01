#!/usr/bin/env node
/**
 * Error Detection Bot - Fehlererkennung
 * Ueberwacht Logs, Exceptions, Ausfaelle, korreliert Alerts
 */

import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';

const execAsync = promisify(exec);

export class ErrorDetectionBot {
  constructor(options = {}) {
    this.name = 'error-detection-bot';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 45) * 1000;
    this.running = false;
    this.timer = null;
    this.errorPatterns = [
      { pattern: /error|exception|fatal|crash/i, type: 'runtime', severity: 'high' },
      { pattern: /timeout|etimedout|econnrefused/i, type: 'network', severity: 'medium' },
      { pattern: /enoent|not found|cannot find module/i, type: 'missing', severity: 'high' },
      { pattern: /memory.*exhausted|heap out of memory|allocation failed/i, type: 'memory', severity: 'critical' },
      { pattern: /unhandled rejection|uncaught exception/i, type: 'unhandled', severity: 'critical' },
      { pattern: /xss|injection|csrf|sanitiz/i, type: 'security', severity: 'critical' }
    ];
    this.knownErrors = new Map();
    this.maxKnown = 200;
    this.status = { startedAt: null, scans: 0, errorsFound: 0, uniqueErrors: 0 };
  }

  getLogFiles() {
    const candidates = [
      path.join(process.cwd(), 'watchdog.log'),
      path.join(process.cwd(), 'logs', 'monitoring-bot.log'),
      path.join(process.cwd(), 'logs', 'repair-bot.log'),
      path.join(process.cwd(), 'logs', 'maintenance-bot.log'),
      path.join(process.cwd(), 'logs', 'optimization-bot.log')
    ];
    return candidates.filter(f => fs.existsSync(f));
  }

  tailFile(filePath, lines = 100) {
    try {
      const data = fs.readFileSync(filePath, 'utf8');
      const allLines = data.split('\n');
      return allLines.slice(-lines);
    } catch {
      return [];
    }
  }

  analyzeLogLines(lines, source) {
    const findings = [];
    for (const line of lines) {
      if (!line.trim()) continue;
      for (const { pattern, type, severity } of this.errorPatterns) {
        if (pattern.test(line)) {
          const hash = Buffer.from(line.slice(0, 120)).toString('base64').slice(0, 32);
          const isNew = !this.knownErrors.has(hash);
          if (isNew) {
            this.knownErrors.set(hash, { firstSeen: new Date().toISOString(), count: 1, line: line.slice(0, 200) });
            if (this.knownErrors.size > this.maxKnown) {
              const firstKey = this.knownErrors.keys().next().value;
              this.knownErrors.delete(firstKey);
            }
          } else {
            const entry = this.knownErrors.get(hash);
            entry.count++;
            entry.lastSeen = new Date().toISOString();
          }
          findings.push({ source, type, severity, line: line.slice(0, 200), hash, isNew, timestamp: new Date().toISOString() });
          break;
        }
      }
    }
    return findings;
  }

  async checkSystemJournal() {
    try {
      const { stdout } = await execAsync('log show --predicate \'subsystem == "com.supermegabot"\' --last 5m --style compact 2>/dev/null | tail -20 || echo ""');
      return stdout.split('\n').filter(l => l.trim());
    } catch {
      return [];
    }
  }

  async checkNodeProcesses() {
    try {
      const { stdout } = await execAsync('ps aux | grep node | grep -v grep');
      const lines = stdout.split('\n').filter(l => l.trim());
      const zombies = lines.filter(l => l.includes('<defunct>') || l.includes('zombie'));
      return { total: lines.length, zombies: zombies.length, details: zombies };
    } catch {
      return { total: 0, zombies: 0, details: [] };
    }
  }

  async tick() {
    try {
      this.status.scans++;
      const allFindings = [];

      const logFiles = this.getLogFiles();
      for (const logFile of logFiles) {
        const lines = this.tailFile(logFile, 50);
        const findings = this.analyzeLogLines(lines, path.basename(logFile));
        allFindings.push(...findings);
      }

      const journalLines = await this.checkSystemJournal();
      if (journalLines.length) {
        const findings = this.analyzeLogLines(journalLines, 'system-journal');
        allFindings.push(...findings);
      }

      const procStatus = await this.checkNodeProcesses();
      if (procStatus.zombies > 0) {
        allFindings.push({ source: 'process-check', type: 'zombie', severity: 'medium', line: `${procStatus.zombies} zombie processes detected`, isNew: true, timestamp: new Date().toISOString() });
      }

      const newFindings = allFindings.filter(f => f.isNew);
      const critical = newFindings.filter(f => f.severity === 'critical');
      const high = newFindings.filter(f => f.severity === 'high');

      if (critical.length) {
        this.status.errorsFound += critical.length;
        this.status.uniqueErrors = this.knownErrors.size;
        this.logger.error('Critical errors detected', { count: critical.length, sources: [...new Set(critical.map(f => f.source))] });
        eventBus.publish('alert:critical', critical);
      }
      if (high.length) {
        this.status.errorsFound += high.length;
        this.logger.warn('High severity errors detected', { count: high.length });
        eventBus.publish('alert:high', high);
      }

      if (allFindings.length) {
        eventBus.publish('scan:errors', { total: allFindings.length, new: newFindings.length, bySeverity: { critical: critical.length, high: high.length, medium: allFindings.filter(f => f.severity === 'medium').length } });
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
    this.logger.info('Error Detection Bot started');
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('Error Detection Bot stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, knownErrors: this.knownErrors.size };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new ErrorDetectionBot();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
