#!/usr/bin/env node
/**
 * Optimization Bot - Performance und Conversion
 * Ueberwacht Bundle-Size, Code-Qualitaet, Performance-Metriken, Conversion-nahe Verbesserungen
 */

import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import { UnifiedLogger } from '../shared/unified-logger.js';
import { eventBus } from '../shared/event-bus.js';

const execAsync = promisify(exec);

export class OptimizationBot {
  constructor(options = {}) {
    this.name = 'optimization-bot';
    this.logger = new UnifiedLogger({ name: this.name });
    this.interval = (options.interval || 300) * 1000;
    this.running = false;
    this.timer = null;
    this.optimizations = [];
    this.maxOpts = 200;
    this.counters = { bundle: 0, quality: 0, assets: 0 };
    this.status = { startedAt: null, scans: 0, suggestions: 0, improvements: 0 };
  }

  recordOpt(type, description, impact, details = {}) {
    const entry = { timestamp: new Date().toISOString(), type, description, impact, details };
    this.optimizations.push(entry);
    if (this.optimizations.length > this.maxOpts) this.optimizations = this.optimizations.slice(-this.maxOpts);
    this.status.suggestions++;
    eventBus.publish('optimization:suggestion', entry);
  }

  async checkBundleSize() {
    try {
      const buildDir = path.join(process.cwd(), '.next');
      if (!fs.existsSync(buildDir)) return null;
      let total = 0;
      const jsFiles = [];
      const scan = (dir) => {
        for (const item of fs.readdirSync(dir)) {
          const fp = path.join(dir, item);
          const s = fs.statSync(fp);
          if (s.isDirectory()) scan(fp);
          else if (item.endsWith('.js')) { total += s.size; jsFiles.push({ name: item, size: s.size }); }
        }
      };
      scan(buildDir);
      const mb = total / 1024 / 1024;
      if (mb > 50) {
        this.recordOpt('bundle', `Bundle size large: ${mb.toFixed(2)} MB`, 'high', { sizeMB: mb, files: jsFiles.length });
      }
      return { sizeMB: mb, files: jsFiles.length };
    } catch (err) {
      return null;
    }
  }

  async checkCodeQuality() {
    try {
      const criticalFiles = [
        'my-shop/backend/index.js',
        'services/analytics.service.ts',
        'services/klaviyo.service.ts'
      ];
      let issues = 0;
      for (const f of criticalFiles) {
        const fp = path.join(process.cwd(), f);
        if (!fs.existsSync(fp)) continue;
        const content = fs.readFileSync(fp, 'utf8');
        const consoleLogs = (content.match(/console\.log/g) || []).length;
        const todos = (content.match(/TODO|FIXME/g) || []).length;
        const innerHTML = (content.match(/innerHTML/g) || []).length;
        if (consoleLogs > 5) { issues++; this.recordOpt('code-quality', `${f}: ${consoleLogs} console.log statements`, 'medium', { file: f }); }
        if (innerHTML > 0) { issues++; this.recordOpt('security', `${f}: ${innerHTML} innerHTML usages (XSS risk)`, 'high', { file: f }); }
        if (todos > 0) { this.recordOpt('code-quality', `${f}: ${todos} TODO/FIXME comments`, 'low', { file: f }); }
      }
      return issues;
    } catch {
      return 0;
    }
  }

  async checkAssetOptimization() {
    try {
      const publicDir = path.join(process.cwd(), 'public');
      if (!fs.existsSync(publicDir)) return null;
      const images = fs.readdirSync(publicDir).filter(f => /\.(jpg|jpeg|png|gif|webp)$/i.test(f));
      const large = images.filter(f => fs.statSync(path.join(publicDir, f)).size > 500 * 1024);
      if (large.length) {
        this.recordOpt('assets', `${large.length} unoptimized images (>500KB) in public/`, 'medium', { count: large.length });
      }
      return { total: images.length, large: large.length };
    } catch {
      return null;
    }
  }

  async checkPerformanceMetrics() {
    try {
      const nextConfig = path.join(process.cwd(), 'next.config.js');
      if (fs.existsSync(nextConfig)) {
        const content = fs.readFileSync(nextConfig, 'utf8');
        if (!content.includes('compress')) {
          this.recordOpt('performance', 'Gzip compression not enabled in next.config.js', 'medium', { file: 'next.config.js' });
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  async checkConversionOptimization() {
    try {
      const dashboards = [
        'mega-dashboard.html',
        'ultimate-ecommerce-dashboard.html',
        'shopify-dashboard.html'
      ];
      for (const db of dashboards) {
        const fp = path.join(process.cwd(), db);
        if (!fs.existsSync(fp)) continue;
        const content = fs.readFileSync(fp, 'utf8');
        const hasAnalytics = content.includes('gtag') || content.includes('analytics') || content.includes('dataLayer');
        const hasButtons = content.includes('<button');
        const hasOnclick = content.includes('onclick=');
        if (hasButtons && !hasOnclick) {
          this.recordOpt('conversion', `${db}: Buttons exist but may lack handlers`, 'high', { file: db });
        }
        if (!hasAnalytics) {
          this.recordOpt('conversion', `${db}: No analytics tracking detected`, 'medium', { file: db });
        }
      }
    } catch {}
  }

  async tick() {
    try {
      this.status.scans++;
      this.logger.debug('Optimization Bot tick started');

      this.counters.bundle++;
      if (this.counters.bundle >= 3) {
        this.counters.bundle = 0;
        await this.checkBundleSize();
        await this.checkAssetOptimization();
      }

      this.counters.quality++;
      if (this.counters.quality >= 2) {
        this.counters.quality = 0;
        await this.checkCodeQuality();
        await this.checkPerformanceMetrics();
        await this.checkConversionOptimization();
      }

      this.logger.debug('Optimization Bot tick completed');
    } catch (err) {
      this.logger.error('Tick error', { error: err.message });
      eventBus.publish('error:bot', { bot: this.name, error: err.message });
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.status.startedAt = new Date().toISOString();
    this.logger.info('Optimization Bot started');
    eventBus.publish('bot:started', { bot: this.name });
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.logger.info('Optimization Bot stopped');
    eventBus.publish('bot:stopped', { bot: this.name });
  }

  getStatus() {
    return { ...this.status, running: this.running, name: this.name, recentSuggestions: this.optimizations.slice(-5) };
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new OptimizationBot();
  bot.start();
  process.on('SIGINT', () => bot.stop());
  process.on('SIGTERM', () => bot.stop());
}
