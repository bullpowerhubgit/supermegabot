#!/usr/bin/env node

/**
 * Optimization Bot
 * Performance-Optimierung und Code-Verbesserungen
 * Überwacht Bundle-Size, Ladezeiten und API-Caching
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';

const execAsync = promisify(exec);

class OptimizationBot {
  constructor(options = {}) {
    this.interval = (options.interval || 300) * 1000;
    this.logFile = options.logFile || path.join(process.cwd(), 'logs', 'optimization-bot.log');
    this.maxLogSize = options.maxLogSize || 5 * 1024 * 1024;
    this.maxLogFiles = options.maxLogFiles || 3;
    this.running = false;
    this.timer = null;
    this.optimizations = [];
    
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

  recordOptimization(type, description, impact) {
    this.optimizations.push({
      timestamp: new Date().toISOString(),
      type,
      description,
      impact
    });
    
    if (this.optimizations.length > 100) {
      this.optimizations = this.optimizations.slice(-50);
    }
  }

  async checkBundleSize() {
    try {
      this.log('info', '📦 Prüfe Bundle-Size...');
      
      const buildDir = path.join(process.cwd(), '.next');
      if (!fs.existsSync(buildDir)) {
        this.log('info', 'ℹ️ Kein Build-Verzeichnis gefunden');
        return;
      }

      let totalSize = 0;
      const jsFiles = [];
      
      function scanDir(dir) {
        const items = fs.readdirSync(dir);
        for (const item of items) {
          const fullPath = path.join(dir, item);
          const stats = fs.statSync(fullPath);
          
          if (stats.isDirectory()) {
            scanDir(fullPath);
          } else if (item.endsWith('.js') || item.endsWith('.js.map')) {
            totalSize += stats.size;
            if (item.endsWith('.js')) {
              jsFiles.push({ name: item, size: stats.size });
            }
          }
        }
      }
      
      scanDir(buildDir);
      
      const sizeMB = totalSize / 1024 / 1024;
      this.log('info', `📦 Bundle-Size: ${sizeMB.toFixed(2)} MB (${jsFiles.length} JS-Dateien)`);
      
      if (sizeMB > 50) {
        this.log('warn', `⚠️ Bundle ist groß (${sizeMB.toFixed(2)} MB) - Code-Splitting empfohlen`);
        this.recordOptimization('bundle', 'Bundle-Size zu groß', 'high');
      }

      const largestFiles = jsFiles.sort((a, b) => b.size - a.size).slice(0, 5);
      largestFiles.forEach(f => {
        this.log('info', `  📄 ${f.name}: ${(f.size / 1024).toFixed(2)} KB`);
      });

    } catch (error) {
      this.log('error', `❌ Bundle-Size Prüfung fehlgeschlagen: ${error.message}`);
    }
  }

  async checkDependencies() {
    try {
      this.log('info', '📦 Prüfe Dependencies...');
      
      const packageJsonPath = path.join(process.cwd(), 'package.json');
      const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
      
      const deps = { ...packageJson.dependencies, ...packageJson.devDependencies };
      const depCount = Object.keys(deps).length;
      
      this.log('info', `📦 ${depCount} Dependencies installiert`);
      
      if (depCount > 100) {
        this.log('warn', `⚠️ Viele Dependencies (${depCount}) - Überprüfung empfohlen`);
        this.recordOptimization('dependencies', `${depCount} Dependencies - möglicherweise zu viele`, 'medium');
      }

    } catch (error) {
      this.log('error', `❌ Dependency-Prüfung fehlgeschlagen: ${error.message}`);
    }
  }

  async analyzeCodeQuality() {
    try {
      this.log('info', '🔍 Analysiere Code-Qualität...');
      
      const criticalFiles = [
        'components/quick-cash/AutoShopSuite.tsx',
        'components/quick-cash/QuickCashSystem.tsx',
        'api-config.json',
        'watchdog.js'
      ];

      for (const file of criticalFiles) {
        const filePath = path.join(process.cwd(), file);
        if (fs.existsSync(filePath)) {
          const content = fs.readFileSync(filePath, 'utf8');
          const lines = content.split('\n');
          
          let issues = 0;
          
          // Check for console.log in production files
          if (file.endsWith('.tsx') || file.endsWith('.ts')) {
            const consoleLogs = lines.filter(l => l.includes('console.log'));
            if (consoleLogs.length > 5) {
              this.log('warn', `⚠️ ${file}: ${consoleLogs.length} console.log Statements gefunden`);
              issues++;
            }
          }
          
          // Check for TODO/FIXME comments
          const todos = lines.filter(l => l.includes('TODO') || l.includes('FIXME'));
          if (todos.length > 0) {
            this.log('info', `ℹ️ ${file}: ${todos.length} TODO/FIXME Kommentare`);
            issues++;
          }
          
          if (issues === 0) {
            this.log('info', `✅ ${file}: OK`);
          }
        }
      }

    } catch (error) {
      this.log('error', `❌ Code-Qualität Analyse fehlgeschlagen: ${error.message}`);
    }
  }

  async suggestOptimizations() {
    try {
      this.log('info', '💡 Generiere Optimierungs-Vorschläge...');
      
      const suggestions = [];
      
      // Check for potential API caching improvements
      const apiConfigPath = path.join(process.cwd(), 'api-config.json');
      if (fs.existsSync(apiConfigPath)) {
        const config = JSON.parse(fs.readFileSync(apiConfigPath, 'utf8'));
        
        if (!config.system || !config.system.cacheEnabled) {
          suggestions.push('API-Caching aktivieren für bessere Performance');
        }
      }
      
      // Check for missing compression
      const nextConfigPath = path.join(process.cwd(), 'next.config.js');
      if (fs.existsSync(nextConfigPath)) {
        const content = fs.readFileSync(nextConfigPath, 'utf8');
        if (!content.includes('compress')) {
          suggestions.push('Gzip/Kompression in next.config.js aktivieren');
        }
      }
      
      // Check for image optimization
      const publicDir = path.join(process.cwd(), 'public');
      if (fs.existsSync(publicDir)) {
        const imageFiles = fs.readdirSync(publicDir).filter(f => /\.(jpg|jpeg|png|gif)$/.test(f));
        if (imageFiles.length > 0) {
          suggestions.push('Bilder optimieren oder Next.js Image Component verwenden');
        }
      }
      
      if (suggestions.length > 0) {
        suggestions.forEach(s => {
          this.log('info', `💡 ${s}`);
        });
        this.recordOptimization('suggestion', `${suggestions.length} Optimierungen vorgeschlagen`, 'medium');
      } else {
        this.log('info', '✅ Keine Optimierungs-Vorschläge - alles gut!');
      }

    } catch (error) {
      this.log('error', `❌ Optimierungs-Vorschläge fehlgeschlagen: ${error.message}`);
    }
  }

  async tick() {
    try {
      this.log('info', '⚡ Optimization Bot Tick gestartet');

      await this.checkBundleSize();
      await this.checkDependencies();
      await this.analyzeCodeQuality();
      await this.suggestOptimizations();

      this.log('info', '✅ Optimization Bot Tick abgeschlossen');
    } catch (error) {
      this.log('error', `Optimization Bot Fehler: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', '⚡ Optimization Bot gestartet');
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('info', '🛑 Optimization Bot gestoppt');
  }
}

// Konfiguration
const bot = new OptimizationBot({
  interval: 300
});

process.on('SIGINT', () => bot.stop());
process.on('SIGTERM', () => bot.stop());

bot.start();
