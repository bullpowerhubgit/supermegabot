#!/usr/bin/env node
/**
 * SuperMegaBot Disk Space Manager
 * Dauerhafte Lösung für volle Festplatte
 */

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

class DiskManager {
  constructor() {
    this.threshold = 85; // Warnung bei 85%
    this.critical = 95;  // Aktion bei 95%
    this.logFile = path.join(__dirname, 'disk.log');
    this.checkInterval = 60000; // 60 Sekunden
  }

  async getDiskUsage() {
    return new Promise((resolve) => {
      exec("df -h /System/Volumes/Data | tail -1 | awk '{print $5}' | sed 's/%//'", (error, stdout) => {
        if (error) {
          resolve(0);
        } else {
          resolve(parseInt(stdout.trim()) || 0);
        }
      });
    });
  }

  async cleanDownloads() {
    // Lösche alte .xip und .dmg Dateien in Downloads
    const downloads = path.join(process.env.HOME, 'Downloads');
    const patterns = ['*.xip', '*.dmg', '*.pkg', '*.zip'];
    
    for (const pattern of patterns) {
      exec(`find "${downloads}" -name "${pattern}" -type f -atime +7 -delete 2>/dev/null || true`);
    }
    
    // Lösche Duplikate (Dateien mit (1), (2) etc.)
    exec(`find "${downloads}" -name '*\([0-9]\)*' -type f -delete 2>/dev/null || true`);
  }

  async cleanCaches() {
    // System Caches
    const caches = [
      path.join(process.env.HOME, 'Library/Caches'),
      path.join(process.env.HOME, 'Library/Caches/com.apple.Safari'),
      path.join(process.env.HOME, 'Library/Caches/com.google.Chrome'),
      '/Library/Caches'
    ];
    
    for (const cache of caches) {
      if (fs.existsSync(cache)) {
        exec(`find "${cache}" -type f -atime +30 -delete 2>/dev/null || true`);
      }
    }
  }

  async cleanLogs() {
    // Alte Logs
    const logs = [
      path.join(process.env.HOME, 'Library/Logs'),
      '/var/log'
    ];
    
    for (const log of logs) {
      if (fs.existsSync(log)) {
        exec(`find "${log}" -type f -name '*.log' -atime +7 -delete 2>/dev/null || true`);
      }
    }
  }

  async cleanTempFiles() {
    // Temp Dateien
    exec('find /tmp -type f -atime +3 -delete 2>/dev/null || true');
    exec(`find "${path.join(process.env.HOME, 'Library/Application Support')}" -name '*.tmp' -type f -delete 2>/dev/null || true`);
  }

  async cleanTrash() {
    // Leere Papierkorb
    exec('rm -rf ~/.Trash/* 2>/dev/null || true');
  }

  log(message) {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] ${message}\n`;
    fs.appendFileSync(this.logFile, logEntry);
    console.log(logEntry.trim());
  }

  async checkAndAct() {
    const diskUsage = await this.getDiskUsage();
    
    this.log(`Disk Usage: ${diskUsage}%`);

    if (diskUsage >= this.critical) {
      this.log(`🚨 CRITICAL: ${diskUsage}% - Emergency cleanup!`);
      
      await this.cleanDownloads();
      await this.cleanCaches();
      await this.cleanLogs();
      await this.cleanTempFiles();
      await this.cleanTrash();
      
    } else if (diskUsage >= this.threshold) {
      this.log(`⚠️ WARNING: ${diskUsage}% - Starting cleanup...`);
      
      await this.cleanCaches();
      await this.cleanLogs();
      await this.cleanTempFiles();
    }

    // Speichern des aktuellen Status
    const status = {
      timestamp: new Date().toISOString(),
      diskUsage: diskUsage,
      threshold: this.threshold,
      critical: this.critical
    };
    
    fs.writeFileSync(
      path.join(__dirname, 'disk-status.json'),
      JSON.stringify(status, null, 2)
    );
  }

  start() {
    this.log('🚀 Disk Manager started');
    this.checkAndAct();
    
    setInterval(() => {
      this.checkAndAct();
    }, this.checkInterval);
  }
}

// Starte Manager
const manager = new DiskManager();
manager.start();

// Graceful shutdown
process.on('SIGINT', () => {
  manager.log('👋 Disk Manager stopped');
  process.exit(0);
});
