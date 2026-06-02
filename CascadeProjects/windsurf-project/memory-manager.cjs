#!/usr/bin/env node
/**
 * SuperMegaBot Memory Manager
 * Dauerhafte Lösung für Memory-Probleme
 * Verhindert kritische Memory-Usage automatisch
 */

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

class MemoryManager {
  constructor() {
    this.threshold = 85; // Warnung bei 85%
    this.critical = 95;   // Aktion bei 95%
    this.logFile = path.join(__dirname, 'memory.log');
    this.checkInterval = 30000; // 30 Sekunden
  }

  async getMemoryUsage() {
    return new Promise((resolve) => {
      exec("ps -A -o %mem | awk '{s+=$1} END {print s}'", (error, stdout) => {
        if (error) {
          resolve(0);
        } else {
          resolve(parseFloat(stdout.trim()) || 0);
        }
      });
    });
  }

  async getTopProcesses() {
    return new Promise((resolve) => {
      exec("ps aux | sort -nr -k 4 | head -10", (error, stdout) => {
        if (error) {
          resolve('');
        } else {
          resolve(stdout);
        }
      });
    });
  }

  async killZombieProcesses() {
    // Beende Zombie-Prozesse (beendete aber noch im Speicher)
    return new Promise((resolve) => {
      exec("ps aux | grep '<defunct>' | awk '{print $2}' | xargs kill -9 2>/dev/null || true", () => {
        resolve();
      });
    });
  }

  async cleanupOldLogs() {
    // Alte Logs aufräumen
    const logPath = path.join(__dirname, 'logs');
    if (fs.existsSync(logPath)) {
      const files = fs.readdirSync(logPath);
      const now = Date.now();
      const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 Tage

      files.forEach(file => {
        const filePath = path.join(logPath, file);
        const stats = fs.statSync(filePath);
        if (now - stats.mtime.getTime() > maxAge) {
          fs.unlinkSync(filePath);
        }
      });
    }
  }

  async limitBotProcesses() {
    // Beende doppelte Bot-Prozesse
    return new Promise((resolve) => {
      exec("ps aux | grep 'rudibot' | grep -v grep | awk '{print $2}' | sort | uniq -d | xargs kill -9 2>/dev/null || true", () => {
        resolve();
      });
    });
  }

  log(message) {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] ${message}\n`;
    fs.appendFileSync(this.logFile, logEntry);
    console.log(logEntry.trim());
  }

  async checkAndAct() {
    const memoryUsage = await this.getMemoryUsage();
    
    this.log(`Memory Usage: ${memoryUsage.toFixed(2)}%`);

    if (memoryUsage >= this.critical) {
      this.log(`🚨 CRITICAL: ${memoryUsage.toFixed(2)}% - Emergency cleanup!`);
      
      await this.killZombieProcesses();
      await this.limitBotProcesses();
      await this.cleanupOldLogs();
      
      // Optional: Beende nicht-kritische Prozesse
      exec("ps aux | grep 'node' | grep -v 'Windsurf' | awk '{print $2}' | tail -n +5 | xargs kill -9 2>/dev/null || true");
      
    } else if (memoryUsage >= this.threshold) {
      this.log(`⚠️ WARNING: ${memoryUsage.toFixed(2)}% - Starting cleanup...`);
      
      await this.killZombieProcesses();
      await this.cleanupOldLogs();
    }

    // Speichern des aktuellen Status
    const status = {
      timestamp: new Date().toISOString(),
      memoryUsage: memoryUsage.toFixed(2),
      threshold: this.threshold,
      critical: this.critical
    };
    
    fs.writeFileSync(
      path.join(__dirname, 'memory-status.json'),
      JSON.stringify(status, null, 2)
    );
  }

  start() {
    this.log('🚀 Memory Manager started');
    this.checkAndAct();
    
    setInterval(() => {
      this.checkAndAct();
    }, this.checkInterval);
  }
}

// Starte Manager
const manager = new MemoryManager();
manager.start();

// Graceful shutdown
process.on('SIGINT', () => {
  manager.log('👋 Memory Manager stopped');
  process.exit(0);
});
