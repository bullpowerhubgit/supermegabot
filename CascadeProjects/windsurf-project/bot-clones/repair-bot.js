#!/usr/bin/env node

/**
 * Repair Bot
 * Automatische Fehlerbehebung für bekannte Probleme
 * Repariert Logs, Cache, API-Verbindungen und Services
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

class RepairBot {
  constructor(options = {}) {
    this.interval = (options.interval || 60) * 1000;
    this.logFile = options.logFile || path.join(process.cwd(), 'logs', 'repair-bot.log');
    this.maxLogSize = options.maxLogSize || 5 * 1024 * 1024;
    this.maxLogFiles = options.maxLogFiles || 3;
    this.running = false;
    this.timer = null;
    this.repairHistory = [];
    
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

  recordRepair(type, description, success) {
    this.repairHistory.push({
      timestamp: new Date().toISOString(),
      type,
      description,
      success
    });
    
    if (this.repairHistory.length > 100) {
      this.repairHistory = this.repairHistory.slice(-50);
    }
  }

  async repairLogFiles() {
    try {
      this.log('info', '🔧 Prüfe Log-Dateien auf Übergröße...');
      
      const logFiles = [
        'watchdog.log',
        'logs/monitoring-bot.log',
        'logs/repair-bot.log',
        'logs/maintenance-bot.log'
      ];

      let repaired = 0;
      for (const logFile of logFiles) {
        const filePath = path.join(process.cwd(), logFile);
        if (fs.existsSync(filePath)) {
          const stats = fs.statSync(filePath);
          if (stats.size > 10 * 1024 * 1024) { // 10MB
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const backupFile = `${filePath}.${timestamp}.backup`;
            fs.renameSync(filePath, backupFile);
            this.log('info', `✅ Log-Datei rotiert: ${logFile} (${(stats.size / 1024 / 1024).toFixed(2)}MB)`);
            repaired++;
          }
        }
      }

      if (repaired === 0) {
        this.log('info', '✅ Alle Log-Dateien OK');
      }

      this.recordRepair('log', `${repaired} Log-Dateien rotiert`, true);
      return repaired;
    } catch (error) {
      this.log('error', `❌ Log-Reparatur fehlgeschlagen: ${error.message}`);
      this.recordRepair('log', error.message, false);
      return 0;
    }
  }

  async repairCache() {
    try {
      this.log('info', '🧹 Bereinige Cache-Verzeichnisse...');
      
      const cacheDirs = [
        path.join(os.homedir(), 'Library', 'Caches'),
        '/tmp',
        path.join(process.cwd(), 'node_modules', '.cache'),
        path.join(process.cwd(), '.next', 'cache')
      ];

      let cleaned = 0;
      for (const dir of cacheDirs) {
        try {
          if (fs.existsSync(dir)) {
            const { stdout } = await execAsync(`du -sh "${dir}" 2>/dev/null | awk '{print $1}'`);
            const size = stdout.trim();
            
            if (size && size !== '0B') {
              await execAsync(`rm -rf "${dir}"/* 2>/dev/null`);
              this.log('info', `✅ Cache bereinigt: ${dir} (${size})`);
              cleaned++;
            }
          }
        } catch (e) {}
      }

      this.recordRepair('cache', `${cleaned} Cache-Verzeichnisse bereinigt`, true);
      return cleaned;
    } catch (error) {
      this.log('error', `❌ Cache-Bereinigung fehlgeschlagen: ${error.message}`);
      this.recordRepair('cache', error.message, false);
      return 0;
    }
  }

  async repairAPIConnections() {
    try {
      this.log('info', '🔌 Prüfe API-Verbindungen...');
      
      const apiConfigPath = path.join(process.cwd(), 'api-config.json');
      if (!fs.existsSync(apiConfigPath)) {
        this.log('warn', '⚠️ api-config.json nicht gefunden');
        return 0;
      }

      const config = JSON.parse(fs.readFileSync(apiConfigPath, 'utf8'));
      let repaired = 0;

      for (const [service, settings] of Object.entries(config)) {
        if (settings.status === 'NEEDS_CONFIG') {
          this.log('warn', `⚠️ API ${service} benötigt Konfiguration: ${settings.instructions || ''}`);
        } else if (settings.status === 'ACTIVE') {
          this.log('info', `✅ API ${service} ist aktiv`);
        }
      }

      this.recordRepair('api', `API-Verbindungen geprüft`, true);
      return repaired;
    } catch (error) {
      this.log('error', `❌ API-Prüfung fehlgeschlagen: ${error.message}`);
      this.recordRepair('api', error.message, false);
      return 0;
    }
  }

  async repairNodeModules() {
    try {
      this.log('info', '📦 Prüfe node_modules...');
      
      const nodeModulesPath = path.join(process.cwd(), 'node_modules');
      if (!fs.existsSync(nodeModulesPath)) {
        this.log('warn', '⚠️ node_modules nicht gefunden - npm install erforderlich');
        this.recordRepair('node_modules', 'node_modules fehlt', false);
        return 0;
      }

      const packageJsonPath = path.join(process.cwd(), 'package.json');
      const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
      const deps = Object.keys({ ...packageJson.dependencies, ...packageJson.devDependencies });
      
      let missing = 0;
      for (const dep of deps) {
        const depPath = path.join(nodeModulesPath, dep);
        if (!fs.existsSync(depPath)) {
          missing++;
        }
      }

      if (missing > 0) {
        this.log('warn', `⚠️ ${missing} node_modules fehlen - npm install empfohlen`);
        this.recordRepair('node_modules', `${missing} Pakete fehlen`, false);
      } else {
        this.log('info', '✅ Alle node_modules vorhanden');
        this.recordRepair('node_modules', 'Alle Pakete OK', true);
      }

      return missing;
    } catch (error) {
      this.log('error', `❌ node_modules Prüfung fehlgeschlagen: ${error.message}`);
      this.recordRepair('node_modules', error.message, false);
      return 0;
    }
  }

  async tick() {
    try {
      this.log('info', '🔧 Repair Bot Tick gestartet');

      // Log-Dateien reparieren
      await this.repairLogFiles();

      // Cache bereinigen (every 5 ticks)
      if (!this.cacheCounter) this.cacheCounter = 0;
      this.cacheCounter++;
      if (this.cacheCounter >= 5) {
        this.cacheCounter = 0;
        await this.repairCache();
      }

      // API-Verbindungen prüfen (every 3 ticks)
      if (!this.apiCounter) this.apiCounter = 0;
      this.apiCounter++;
      if (this.apiCounter >= 3) {
        this.apiCounter = 0;
        await this.repairAPIConnections();
      }

      // node_modules prüfen (every 10 ticks)
      if (!this.modulesCounter) this.modulesCounter = 0;
      this.modulesCounter++;
      if (this.modulesCounter >= 10) {
        this.modulesCounter = 0;
        await this.repairNodeModules();
      }

      this.log('info', '✅ Repair Bot Tick abgeschlossen');
    } catch (error) {
      this.log('error', `Repair Bot Fehler: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', '🔧 Repair Bot gestartet');
    this.tick();
    this.timer = setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('info', '🛑 Repair Bot gestoppt');
  }
}

// Konfiguration
const bot = new RepairBot({
  interval: 60
});

process.on('SIGINT', () => bot.stop());
process.on('SIGTERM', () => bot.stop());

bot.start();
