#!/usr/bin/env node

/**
 * Monitoring Bot
 * Überwacht System-Health, API-Status und Performance-Metriken
 * Spezialisiert auf Früherkennung von Problemen
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

class MonitoringBot {
  constructor(options = {}) {
    this.interval = (options.interval || 30) * 1000;
    this.logFile = options.logFile || path.join(process.cwd(), 'logs', 'monitoring-bot.log');
    this.maxLogSize = options.maxLogSize || 5 * 1024 * 1024;
    this.maxLogFiles = options.maxLogFiles || 3;
    this.running = false;
    this.timer = null;
    this.metrics = new Map();
    this.thresholds = {
      memory: options.memoryThreshold || 80,
      cpu: options.cpuThreshold || 90,
      disk: options.diskThreshold || 85,
      apiResponse: options.apiResponseThreshold || 5000
    };
    
    this.ensureLogDir();
  }

  ensureLogDir() {
    const logDir = path.dirname(this.logFile);
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }
  }

  checkLogRotation() {
    try {
      if (fs.existsSync(this.logFile)) {
        const stats = fs.statSync(this.logFile);
        if (stats.size > this.maxLogSize) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const backupFile = `${this.logFile}.${timestamp}.backup`;
          fs.renameSync(this.logFile, backupFile);
          this.cleanOldBackups();
        }
      }
    } catch (error) {
      console.error('Log rotation error:', error.message);
    }
  }

  cleanOldBackups() {
    try {
      const dir = path.dirname(this.logFile);
      const basename = path.basename(this.logFile);
      const files = fs.readdirSync(dir)
        .filter(f => f.startsWith(basename) && f.endsWith('.backup'))
        .map(f => ({
          name: f,
          path: path.join(dir, f),
          time: fs.statSync(path.join(dir, f)).mtime.getTime()
        }))
        .sort((a, b) => b.time - a.time);
      
      if (files.length > this.maxLogFiles) {
        files.slice(this.maxLogFiles).forEach(f => {
          fs.unlinkSync(f.path);
        });
      }
    } catch (error) {
      console.error('Backup cleanup error:', error.message);
    }
  }

  log(level, message) {
    this.checkLogRotation();
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    fs.appendFileSync(this.logFile, line);
  }

  async getSystemMetrics() {
    try {
      const mem = {
        total: os.totalmem(),
        free: os.freemem(),
        used: os.totalmem() - os.freemem(),
        percent: Math.round(((os.totalmem() - os.freemem()) / os.totalmem()) * 100)
      };

      const cpu = await this.getCPUUsage();
      const disk = await this.getDiskUsage();

      return { memory: mem, cpu, disk };
    } catch (error) {
      this.log('error', `Fehler beim Sammeln von Systemmetriken: ${error.message}`);
      return null;
    }
  }

  async getCPUUsage() {
    try {
      const { stdout } = await execAsync("top -l 1 | grep 'CPU usage' | awk '{print $3}' | sed 's/%//g'");
      return parseFloat(stdout.trim()) || 0;
    } catch {
      return 0;
    }
  }

  async getDiskUsage() {
    try {
      const { stdout } = await execAsync("df -h / | tail -1 | awk '{print $5}' | sed 's/%//g'");
      return parseInt(stdout.trim()) || 0;
    } catch {
      return 0;
    }
  }

  async checkAPIEndpoints() {
    const endpoints = [
      { name: 'Anthropic', url: 'https://api.anthropic.com/v1/health', timeout: 5000 },
      { name: 'OpenAI', url: 'https://api.openai.com/v1/models', timeout: 5000 },
      { name: 'Perplexity', url: 'https://api.perplexity.ai', timeout: 5000 },
      { name: 'GCP Vertex AI', url: 'https://europe-west1-gen-lang-client-0895465231.cloudfunctions.net/vertexAIProxy', timeout: 10000 }
    ];

    const results = [];
    for (const endpoint of endpoints) {
      try {
        const start = Date.now();
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), endpoint.timeout);
        
        const response = await fetch(endpoint.url, { 
          method: 'HEAD',
          signal: controller.signal 
        }).catch(() => ({ ok: false, status: 0 }));
        
        clearTimeout(timeout);
        const responseTime = Date.now() - start;

        results.push({
          name: endpoint.name,
          status: response.ok ? 'UP' : 'DOWN',
          responseTime,
          healthy: response.ok && responseTime < this.thresholds.apiResponse
        });
      } catch (error) {
        results.push({
          name: endpoint.name,
          status: 'ERROR',
          responseTime: -1,
          healthy: false,
          error: error.message
        });
      }
    }

    return results;
  }

  async checkProjectFiles() {
    try {
      const criticalFiles = [
        'api-config.json',
        'package.json',
        'watchdog.js',
        'components/quick-cash/AutoShopSuite.tsx',
        'components/quick-cash/QuickCashSystem.tsx'
      ];

      const results = [];
      for (const file of criticalFiles) {
        const filePath = path.join(process.cwd(), file);
        const exists = fs.existsSync(filePath);
        const size = exists ? fs.statSync(filePath).size : 0;
        const modified = exists ? fs.statSync(filePath).mtime : null;

        results.push({
          file,
          exists,
          size,
          modified,
          healthy: exists && size > 0
        });
      }

      return results;
    } catch (error) {
      this.log('error', `Fehler beim Prüfen der Projektdateien: ${error.message}`);
      return [];
    }
  }

  async tick() {
    try {
      const metrics = await this.getSystemMetrics();
      if (!metrics) return;

      this.log('info', `System Status - RAM: ${metrics.memory.percent}% | CPU: ${metrics.cpu}% | Disk: ${metrics.disk}%`);

      // Memory Check
      if (metrics.memory.percent > this.thresholds.memory) {
        this.log('warn', `⚠️ Hoher RAM-Verbrauch: ${metrics.memory.percent}% (Threshold: ${this.thresholds.memory}%)`);
      }

      // CPU Check
      if (metrics.cpu > this.thresholds.cpu) {
        this.log('warn', `⚠️ Hohe CPU-Auslastung: ${metrics.cpu}% (Threshold: ${this.thresholds.cpu}%)`);
      }

      // Disk Check
      if (metrics.disk > this.thresholds.disk) {
        this.log('warn', `⚠️ Hohe Festplattennutzung: ${metrics.disk}% (Threshold: ${this.thresholds.disk}%)`);
      }

      // API Check (every 5 ticks = 2.5 minutes)
      if (!this.apiCheckCounter) this.apiCheckCounter = 0;
      this.apiCheckCounter++;
      
      if (this.apiCheckCounter >= 5) {
        this.apiCheckCounter = 0;
        const apiStatus = await this.checkAPIEndpoints();
        apiStatus.forEach(api => {
          if (!api.healthy) {
            this.log('warn', `⚠️ API Problem: ${api.name} - Status: ${api.status}, Response: ${api.responseTime}ms`);
          } else {
            this.log('info', `✅ API OK: ${api.name} - Response: ${api.responseTime}ms`);
          }
        });
      }

      // File Check (every 10 ticks = 5 minutes)
      if (!this.fileCheckCounter) this.fileCheckCounter = 0;
      this.fileCheckCounter++;
      
      if (this.fileCheckCounter >= 10) {
        this.fileCheckCounter = 0;
        const fileStatus = await this.checkProjectFiles();
        fileStatus.forEach(file => {
          if (!file.healthy) {
            this.log('error', `🚨 Kritische Datei Problem: ${file.file} - Existiert: ${file.exists}, Größe: ${file.size}`);
          }
        });
      }

    } catch (error) {
      this.log('error', `Monitoring Fehler: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', '🤖 Monitoring Bot gestartet');
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('info', '🛑 Monitoring Bot gestoppt');
  }
}

// Konfiguration
const bot = new MonitoringBot({
  interval: 30,
  memoryThreshold: 80,
  cpuThreshold: 90,
  diskThreshold: 85,
  apiResponseThreshold: 5000
});

process.on('SIGINT', () => bot.stop());
process.on('SIGTERM', () => bot.stop());

bot.start();
