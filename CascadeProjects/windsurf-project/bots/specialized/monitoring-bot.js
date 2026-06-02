#!/usr/bin/env node
/**
 * Monitoring Bot - Systemueberwachung
 * Ueberwacht System-Health, API-Status, Performance-Metriken, Prozesse
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';
import { secureConfig } from '../shared/secure-config.js';

const execAsync = promisify(exec);

export class MonitoringBot {
  constructor(options = {}) {
    this.name = 'monitoring-bot';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 30) * 1000;
    this.running = false;
    this.timer = null;
    this.metricsHistory = [];
    this.maxHistory = 200;
    this.thresholds = {
      memory: options.memoryThreshold || 80,
      cpu: options.cpuThreshold || 90,
      disk: options.diskThreshold || 85,
      apiResponse: options.apiResponseThreshold || 5000
    };
    this.counters = { api: 0, file: 0, process: 0 };
    this.status = { startedAt: null, checks: 0, alerts: 0 };
  }

  async getSystemMetrics() {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    const mem = {
      total, free, used,
      percent: Math.round((used / total) * 100)
    };

    let cpu = 0;
    try {
      const { stdout } = await execAsync("top -l 1 | grep 'CPU usage' | awk '{print $3}' | sed 's/%//g'");
      cpu = parseFloat(stdout.trim()) || 0;
    } catch {}

    let disk = 0;
    try {
      const { stdout } = await execAsync("df -h / | tail -1 | awk '{print $5}' | sed 's/%//g'");
      disk = parseInt(stdout.trim()) || 0;
    } catch {}

    return { memory: mem, cpu, disk, timestamp: new Date().toISOString() };
  }

  async checkAPIEndpoints() {
    const endpoints = [
      { name: 'Anthropic', url: 'https://api.anthropic.com/v1/health', timeout: 5000 },
      { name: 'OpenAI', url: 'https://api.openai.com/v1/models', timeout: 5000 },
      { name: 'Perplexity', url: 'https://api.perplexity.ai', timeout: 5000 },
      { name: 'Shopify', url: 'https://suite-8091.myshopify.com/admin/api/2026-04/shop.json', timeout: 8000 }
    ];

    const results = [];
    for (const ep of endpoints) {
      try {
        const start = Date.now();
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), ep.timeout);
        const response = await fetch(ep.url, { method: 'HEAD', signal: controller.signal }).catch(() => ({ ok: false, status: 0 }));
        clearTimeout(t);
        const rt = Date.now() - start;
        results.push({ name: ep.name, status: response.ok ? 'UP' : 'DOWN', responseTime: rt, healthy: response.ok && rt < this.thresholds.apiResponse });
      } catch (err) {
        results.push({ name: ep.name, status: 'ERROR', responseTime: -1, healthy: false, error: err.message });
      }
    }
    return results;
  }

  async checkProcesses() {
    try {
      const { stdout } = await execAsync('ps aux | grep -E "node|python" | grep -v grep | wc -l');
      return { processCount: parseInt(stdout.trim()) || 0 };
    } catch {
      return { processCount: 0 };
    }
  }

  async checkCriticalFiles() {
    const files = ['api-config.json', 'package.json', 'watchdog.js', 'my-shop/backend/index.js'];
    const results = [];
    for (const f of files) {
      const fp = path.join(process.cwd(), f);
      const exists = fs.existsSync(fp);
      const size = exists ? fs.statSync(fp).size : 0;
      results.push({ file: f, exists, size, healthy: exists && size > 0 });
    }
    return results;
  }

  recordMetrics(metrics) {
    this.metricsHistory.push(metrics);
    if (this.metricsHistory.length > this.maxHistory) {
      this.metricsHistory = this.metricsHistory.slice(-this.maxHistory);
    }
  }

  evaluateThresholds(metrics) {
    const alerts = [];
    if (metrics.memory.percent > this.thresholds.memory) {
      if (metrics.memory.percent > 90) alerts.push({ type: 'memory', severity: 'warning', value: metrics.memory.percent, threshold: 90 });
    }
    if (metrics.cpu > this.thresholds.cpu) {
      alerts.push({ type: 'cpu', severity: 'warning', value: metrics.cpu, threshold: this.thresholds.cpu });
    }
    if (metrics.disk > this.thresholds.disk) {
      alerts.push({ type: 'disk', severity: 'warning', value: metrics.disk, threshold: this.thresholds.disk });
    }
    return alerts;
  }

  async tick() {
    try {
      this.status.checks++;
      const metrics = await this.getSystemMetrics();
      this.recordMetrics(metrics);

      this.logger.info('System Status', { ram: metrics.memory.percent, cpu: metrics.cpu, disk: metrics.disk });
      eventBus.publish('metrics:system', metrics);

      const alerts = this.evaluateThresholds(metrics);
      for (const alert of alerts) {
        this.status.alerts++;
        this.logger.warn(`Threshold exceeded: ${alert.type}`, alert);
        eventBus.publish('alert:threshold', alert);
      }

      this.counters.api++;
      if (this.counters.api >= 5) {
        this.counters.api = 0;
        const apiStatus = await this.checkAPIEndpoints();
        const down = apiStatus.filter(a => !a.healthy);
        if (down.length) {
          this.logger.warn('API issues detected', { count: down.length, apis: down.map(d => d.name) });
          eventBus.publish('alert:api', down);
        }
        eventBus.publish('status:api', apiStatus);
      }

      this.counters.file++;
      if (this.counters.file >= 10) {
        this.counters.file = 0;
        const fileStatus = await this.checkCriticalFiles();
        const bad = fileStatus.filter(f => !f.healthy);
        if (bad.length) {
          this.logger.error('Critical file issues', { files: bad.map(f => f.file) });
          eventBus.publish('alert:files', bad);
        }
      }

      this.counters.process++;
      if (this.counters.process >= 6) {
        this.counters.process = 0;
        const procStatus = await this.checkProcesses();
        eventBus.publish('status:processes', procStatus);
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
    this.logger.info('Monitoring Bot started');
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('Monitoring Bot stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, lastMetrics: this.metricsHistory.slice(-1)[0] || null };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new MonitoringBot();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
