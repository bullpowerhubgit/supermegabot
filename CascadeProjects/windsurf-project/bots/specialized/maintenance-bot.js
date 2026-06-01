#!/usr/bin/env node
/**
 * Maintenance Bot - Wartung und Health-Checks
 * Fuehrt Health-Checks, Update-Pruefungen, Backup-Verifikation, Zertifikatspruefung durch
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import https from 'https';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';

const execAsync = promisify(exec);

export class MaintenanceBot {
  constructor(options = {}) {
    this.name = 'maintenance-bot';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 120) * 1000;
    this.running = false;
    this.timer = null;
    this.checks = [];
    this.maxChecks = 200;
    this.counters = { backup: 0, deps: 0, health: 0 };
    this.status = { startedAt: null, ticks: 0, checksPassed: 0, checksFailed: 0 };
  }

  recordCheck(type, description, passed, details = {}) {
    const entry = { timestamp: new Date().toISOString(), type, description, passed, details };
    this.checks.push(entry);
    if (this.checks.length > this.maxChecks) this.checks = this.checks.slice(-this.maxChecks);
    if (passed) this.status.checksPassed++; else this.status.checksFailed++;
    eventBus.publish('maintenance:check', entry);
  }

  async checkBackups() {
    try {
      const backupDir = path.join(process.cwd(), 'backups');
      if (!fs.existsSync(backupDir)) {
        this.recordCheck('backup', 'Backup directory missing', false);
        return { ok: false };
      }
      const backups = fs.readdirSync(backupDir)
        .map(f => ({ name: f, path: path.join(backupDir, f), stat: fs.statSync(path.join(backupDir, f)) }))
        .filter(f => f.stat.isDirectory() || f.name.endsWith('.json'))
        .sort((a, b) => b.stat.mtime.getTime() - a.stat.mtime.getTime());

      const latest = backups[0];
      const ageHours = latest ? (Date.now() - latest.stat.mtime.getTime()) / (1000 * 60 * 60) : Infinity;
      const ok = latest && ageHours < 24;
      this.recordCheck('backup', `Latest backup age: ${ageHours.toFixed(1)}h`, ok, { count: backups.length, latest: latest?.name });
      return { ok, count: backups.length, ageHours };
    } catch (err) {
      this.recordCheck('backup', err.message, false);
      return { ok: false, error: err.message };
    }
  }

  async checkOutdatedDependencies() {
    try {
      const { stdout } = await execAsync('npm outdated --json 2>/dev/null || echo "{}"');
      const outdated = JSON.parse(stdout || '{}');
      const keys = Object.keys(outdated);
      const critical = keys.filter(k => {
        const v = outdated[k];
        if (!v) return false;
        const current = v.current || '0.0.0';
        const latest = v.latest || '0.0.0';
        const majorDiff = parseInt(latest.split('.')[0]) - parseInt(current.split('.')[0]);
        return majorDiff >= 1;
      });
      this.recordCheck('dependencies', `${keys.length} outdated packages (${critical.length} critical)`, critical.length === 0, { outdated: keys.length, critical: critical.length });
      return { outdated: keys, critical };
    } catch {
      this.recordCheck('dependencies', 'Could not check outdated dependencies', false);
      return { outdated: [], critical: [] };
    }
  }

  async checkDiskHealth() {
    try {
      const { stdout } = await execAsync("df -h / | tail -1 | awk '{print $5}' | sed 's/%//g'");
      const used = parseInt(stdout.trim()) || 0;
      const ok = used < 90;
      this.recordCheck('disk', `Disk usage: ${used}%`, ok, { used });
      return { ok, used };
    } catch (err) {
      this.recordCheck('disk', err.message, false);
      return { ok: false };
    }
  }

  async checkServiceHealth() {
    const services = [
      { name: 'my-shop-backend', url: 'http://localhost:4001/api/health', expected: 'online' },
      { name: 'ollama', url: 'http://localhost:11434/api/tags', expected: 200 }
    ];
    const results = [];
    for (const svc of services) {
      try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(svc.url, { signal: controller.signal }).catch(() => ({ ok: false }));
        clearTimeout(t);
        const ok = res.ok;
        this.recordCheck('service', `${svc.name} health check`, ok, { url: svc.url });
        results.push({ name: svc.name, ok });
      } catch {
        this.recordCheck('service', `${svc.name} health check`, false);
        results.push({ name: svc.name, ok: false });
      }
    }
    return results;
  }

  async checkEnvFileHealth() {
    const envFiles = ['.env', '.env.local', '.env.platform'];
    let issues = 0;
    for (const ef of envFiles) {
      const fp = path.join(process.cwd(), ef);
      if (fs.existsSync(fp)) {
        const content = fs.readFileSync(fp, 'utf8');
        const emptyKeys = content.split('\n').filter(l => l.includes('=') && l.split('=')[1]?.trim() === '');
        if (emptyKeys.length) issues += emptyKeys.length;
      }
    }
    this.recordCheck('env', `${issues} empty env values found`, issues === 0, { issues });
    return { ok: issues === 0, issues };
  }

  async tick() {
    try {
      this.status.ticks++;
      this.logger.debug('Maintenance Bot tick started');

      this.counters.health++;
      if (this.counters.health >= 2) {
        this.counters.health = 0;
        await this.checkDiskHealth();
        await this.checkServiceHealth();
        await this.checkEnvFileHealth();
      }

      this.counters.backup++;
      if (this.counters.backup >= 5) {
        this.counters.backup = 0;
        await this.checkBackups();
      }

      this.counters.deps++;
      if (this.counters.deps >= 15) {
        this.counters.deps = 0;
        await this.checkOutdatedDependencies();
      }

      this.logger.debug('Maintenance Bot tick completed');
    } catch (err) {
      this.logger.error('Tick error', { error: err.message });
      eventBus.publish('error:bot', { bot: this.name, error: err.message });
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.status.startedAt = new Date().toISOString();
    this.logger.info('Maintenance Bot started');
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('Maintenance Bot stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, recentChecks: this.checks.slice(-5) };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new MaintenanceBot();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
