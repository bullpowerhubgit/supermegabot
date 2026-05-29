#!/usr/bin/env node

/**
 * RudiBot Auto Backup Scheduler
 * Automatische Backups alle 6 Stunden
 * Cloud-Sync via rsync oder lokal
 */

import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import os from 'os';
import gcpConfig from './lib/gcp-config.js';

const execAsync = promisify(exec);

const BACKUP_DIR = path.join(os.homedir(), 'RudiBot-Data', 'backups');
const CLOUD_DIR = path.join(os.homedir(), 'RudiBot-Data', 'cloud-sync');
const LOG_FILE = path.join(os.homedir(), 'RudiBot-Data', 'backup.log');

class AutoBackupScheduler {
  constructor() {
    this.running = false;
    this.timer = null;
    this.interval = 6 * 60 * 60 * 1000; // 6 Stunden
    this.gcpProjectId = gcpConfig.projectId;
    this.gcpApis = gcpConfig.apiList;
  }

  log(message, level = 'INFO') {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level}] ${message}\n`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line.trim());
    try {
      fs.appendFileSync(LOG_FILE, line);
    } catch (e) {}
  }

  async createBackup() {
    try {
      const { CloudBackupManager } = await import('./cloud-backup-manager.js');
      const manager = new CloudBackupManager();
      const result = await manager.createFullBackup();
      
      if (result.success) {
        this.log(`Backup created: ${result.backupName} (${Math.round(result.totalSize / 1024)}KB)`);
        
        // Cleanup old backups (keep last 10)
        const cleanup = await manager.cleanupOldBackups(10);
        if (cleanup.removed > 0) {
          this.log(`Cleaned up ${cleanup.removed} old backups`);
        }
        
        return result;
      } else {
        this.log(`Backup failed: ${result.error}`, 'ERROR');
        return null;
      }
    } catch (error) {
      this.log(`Backup error: ${error.message}`, 'ERROR');
      return null;
    }
  }

  async syncToCloud() {
    try {
      // Local cloud sync (can be extended to real cloud)
      const latestBackup = this.getLatestBackup();
      if (!latestBackup) {
        this.log('No backup to sync', 'WARN');
        return;
      }

      const source = path.join(BACKUP_DIR, latestBackup);
      const dest = path.join(CLOUD_DIR, latestBackup);

      // Ensure cloud directory exists
      if (!fs.existsSync(dest)) {
        fs.cpSync(source, dest, { recursive: true });
        this.log(`Synced to cloud: ${latestBackup}`);
      }

      // Also sync to iCloud if available
      const iCloudPath = path.join(os.homedir(), 'Library/Mobile Documents/com~apple~CloudDocs/RudiBot-Backups');
      if (fs.existsSync(path.dirname(iCloudPath))) {
        try {
          fs.mkdirSync(iCloudPath, { recursive: true });
          const iCloudDest = path.join(iCloudPath, latestBackup);
          if (!fs.existsSync(iCloudDest)) {
            fs.cpSync(source, iCloudDest, { recursive: true });
            this.log(`Synced to iCloud: ${latestBackup}`);
          }
        } catch (e) {
          this.log(`iCloud sync skipped: ${e.message}`, 'WARN');
        }
      }

    } catch (error) {
      this.log(`Cloud sync error: ${error.message}`, 'ERROR');
    }
  }

  getLatestBackup() {
    try {
      const dirs = fs.readdirSync(BACKUP_DIR)
        .filter(d => d.startsWith('rudibot-full-'))
        .sort()
        .reverse();
      return dirs[0] || null;
    } catch (e) {
      return null;
    }
  }

  async tick() {
    this.log('Starting scheduled backup...');
    
    const backup = await this.createBackup();
    if (backup) {
      await this.syncToCloud();
    }
    
    this.log('Backup cycle completed');
  }

  start() {
    if (this.running) return;
    this.running = true;
    
    this.log('Auto Backup Scheduler started (every 6 hours)');
    
    // First backup immediately
    this.tick();
    
    // Schedule next backups
    this.timer = 
 setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('Auto Backup Scheduler stopped');
  }
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  const scheduler = new AutoBackupScheduler();
  
  process.on('SIGINT', () => scheduler.stop());
  process.on('SIGTERM', () => scheduler.stop());
  
  scheduler.start();
}

export { AutoBackupScheduler };
