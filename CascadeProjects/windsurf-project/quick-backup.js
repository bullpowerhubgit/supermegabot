#!/usr/bin/env node

/**
 * 📦 Quick Backup - Creates instant backup of project
 */

import fs from 'fs';
import path from 'path';
import os from 'os';
import { execSync } from 'child_process';

const PROJECT_DIR = process.cwd();
const BACKUP_DIR = path.join(os.homedir(), 'RudiBot-Data', 'backups');
const CLOUD_DIR = path.join(os.homedir(), 'RudiBot-Data', 'cloud-sync');

class QuickBackup {
  constructor() {
    this.timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    this.backupName = `rudibot-quick-${this.timestamp}`;
    this.backupPath = path.join(BACKUP_DIR, this.backupName);
  }

  log(msg) {
    console.log(`📦 [Quick Backup] ${msg}`);
  }

  async createBackup() {
    this.log('Creating quick backup...');
    
    // Create backup directory
    fs.mkdirSync(this.backupPath, { recursive: true });
    fs.mkdirSync(CLOUD_DIR, { recursive: true });
    
    // Copy all JS files
    const files = fs.readdirSync(PROJECT_DIR).filter(f => f.endsWith('.js') || f.endsWith('.json') || f.endsWith('.md') || f.endsWith('.sh') || f.endsWith('.py'));
    
    const results = [];
    for (const file of files) {
      try {
        const src = path.join(PROJECT_DIR, file);
        const dest = path.join(this.backupPath, file);
        fs.copyFileSync(src, dest);
        const stat = fs.statSync(dest);
        results.push({ file, size: stat.size, success: true });
      } catch (e) {
        results.push({ file, error: e.message, success: false });
      }
    }
    
    // Copy lib and services directories
    for (const subdir of ['lib', 'services', 'prisma']) {
      const srcDir = path.join(PROJECT_DIR, subdir);
      if (fs.existsSync(srcDir)) {
        const destDir = path.join(this.backupPath, subdir);
        fs.mkdirSync(destDir, { recursive: true });
        this.copyDir(srcDir, destDir);
      }
    }
    
    // Create manifest
    const manifest = {
      timestamp: new Date().toISOString(),
      hostname: os.hostname(),
      platform: os.platform(),
      files: results,
      totalSize: results.reduce((sum, r) => sum + (r.size || 0), 0),
      gitBranch: this.getGitBranch(),
      gitCommit: this.getGitCommit()
    };
    
    fs.writeFileSync(path.join(this.backupPath, 'manifest.json'), JSON.stringify(manifest, null, 2));
    
    // Copy to cloud sync
    const cloudBackupPath = path.join(CLOUD_DIR, this.backupName);
    this.copyDir(this.backupPath, cloudBackupPath);
    
    // Cleanup old backups (keep last 5)
    this.cleanupOldBackups();
    
    this.log(`✅ Backup created: ${this.backupName}`);
    this.log(`📊 Files: ${results.length}, Size: ${(manifest.totalSize / 1024 / 1024).toFixed(2)} MB`);
    this.log(`☁️ Cloud sync: ${cloudBackupPath}`);
    
    return {
      success: true,
      backupName: this.backupName,
      backupPath: this.backupPath,
      cloudPath: cloudBackupPath,
      manifest
    };
  }

  copyDir(src, dest) {
    if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
    const entries = fs.readdirSync(src, { withFileTypes: true });
    for (const entry of entries) {
      const srcPath = path.join(src, entry.name);
      const destPath = path.join(dest, entry.name);
      if (entry.isDirectory()) {
        this.copyDir(srcPath, destPath);
      } else {
        fs.copyFileSync(srcPath, destPath);
      }
    }
  }

  getGitBranch() {
    try {
      return execSync('git rev-parse --abbrev-ref HEAD', { cwd: PROJECT_DIR, encoding: 'utf8' }).trim();
    } catch (e) {
      return 'unknown';
    }
  }

  getGitCommit() {
    try {
      return execSync('git rev-parse HEAD', { cwd: PROJECT_DIR, encoding: 'utf8' }).trim();
    } catch (e) {
      return 'unknown';
    }
  }

  cleanupOldBackups() {
    try {
      const backups = fs.readdirSync(BACKUP_DIR)
        .filter(d => d.startsWith('rudibot-'))
        .map(d => ({
          name: d,
          path: path.join(BACKUP_DIR, d),
          mtime: fs.statSync(path.join(BACKUP_DIR, d)).mtime
        }))
        .sort((a, b) => b.mtime - a.mtime);
      
      if (backups.length > 5) {
        const toRemove = backups.slice(5);
        for (const backup of toRemove) {
          fs.rmSync(backup.path, { recursive: true, force: true });
          const cloudPath = path.join(CLOUD_DIR, backup.name);
          if (fs.existsSync(cloudPath)) {
            fs.rmSync(cloudPath, { recursive: true, force: true });
          }
          this.log(`Cleaned up old backup: ${backup.name}`);
        }
      }
    } catch (e) {}
  }
}

// Run backup
const backup = new QuickBackup();
backup.createBackup().catch(err => {
  console.error('❌ Backup failed:', err);
  process.exit(1);
});
