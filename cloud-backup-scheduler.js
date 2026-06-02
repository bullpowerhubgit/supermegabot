#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const cron = require('node-cron');

class CloudBackupScheduler {
  constructor() {
    this.backupDir = '/Users/rudolfsarkany/backups';
    this.cloudDir = '/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/RudiBotBackups';
    this.backupScript = '/Users/rudolfsarkany/create_full_backup.sh';
    this.isRunning = false;
    this.lastBackup = null;
    this.backupHistory = [];
    
    // Ensure directories exist
    [this.backupDir, this.cloudDir].forEach(dir => {
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    });
    
    // Load backup history
    this.loadBackupHistory();
    
    console.log('☁️ Cloud Backup Scheduler initialized');
    console.log(`📁 Local backup dir: ${this.backupDir}`);
    console.log(`☁️ Cloud backup dir: ${this.cloudDir}`);
  }
  
  loadBackupHistory() {
    try {
      const historyFile = path.join(this.cloudDir, 'backup_history.json');
      if (fs.existsSync(historyFile)) {
        this.backupHistory = JSON.parse(fs.readFileSync(historyFile, 'utf8'));
        this.lastBackup = this.backupHistory[0] || null;
      }
    } catch (error) {
      console.error('Failed to load backup history:', error.message);
    }
  }
  
  saveBackupHistory() {
    try {
      const historyFile = path.join(this.cloudDir, 'backup_history.json');
      fs.writeFileSync(historyFile, JSON.stringify(this.backupHistory, null, 2));
    } catch (error) {
      console.error('Failed to save backup history:', error.message);
    }
  }
  
  async runBackup() {
    if (this.isRunning) {
      console.log('⚠️ Backup already running, skipping...');
      return false;
    }
    
    this.isRunning = true;
    const startTime = new Date();
    const backupId = startTime.toISOString().replace(/[:.]/g, '-');
    
    console.log(`🚀 Starting cloud backup: ${backupId}`);
    
    try {
      // Run the backup script
      const output = execSync(this.backupScript, { 
        encoding: 'utf8', 
        timeout: 600000, // 10 minutes timeout
        cwd: '/Users/rudolfsarkany'
      });
      
      console.log('✅ Backup script completed');
      
      // Get backup size
      const backupDate = startTime.toISOString().split('T')[0];
      const backupPath = path.join(this.backupDir, backupDate);
      let backupSize = 'Unknown';
      
      if (fs.existsSync(backupPath)) {
        try {
          const stats = execSync(`du -sh "${backupPath}"`, { encoding: 'utf8' });
          backupSize = stats.split('\t')[0];
        } catch (e) {
          backupSize = 'Unknown';
        }
      }
      
      // Create backup record
      const backupRecord = {
        id: backupId,
        date: backupDate,
        timestamp: startTime.toISOString(),
        size: backupSize,
        status: 'success',
        duration: Math.round((Date.now() - startTime.getTime()) / 1000),
        output: output.substring(0, 1000), // Truncate output
        cloudPath: path.join(this.cloudDir, backupDate)
      };
      
      // Add to history
      this.backupHistory.unshift(backupRecord);
      if (this.backupHistory.length > 30) this.backupHistory.pop(); // Keep last 30 backups
      this.lastBackup = backupRecord;
      
      // Save history
      this.saveBackupHistory();
      
      console.log(`✅ Cloud backup completed successfully`);
      console.log(`📊 Size: ${backupSize}`);
      console.log(`⏱️ Duration: ${backupRecord.duration}s`);
      console.log(`☁️ Cloud: ${backupRecord.cloudPath}`);
      
      return backupRecord;
      
    } catch (error) {
      console.error('❌ Backup failed:', error.message);
      
      // Create failure record
      const backupRecord = {
        id: backupId,
        date: startTime.toISOString().split('T')[0],
        timestamp: startTime.toISOString(),
        size: 'Failed',
        status: 'failed',
        duration: Math.round((Date.now() - startTime.getTime()) / 1000),
        error: error.message
      };
      
      this.backupHistory.unshift(backupRecord);
      if (this.backupHistory.length > 30) this.backupHistory.pop();
      this.lastBackup = backupRecord;
      this.saveBackupHistory();
      
      return backupRecord;
    } finally {
      this.isRunning = false;
    }
  }
  
  async runIncrementalBackup() {
    console.log('🔄 Running incremental backup...');
    
    // For now, incremental backup is just a normal backup with different naming
    const result = await this.runBackup();
    if (result && result.status === 'success') {
      // Rename to indicate incremental
      const backupPath = path.join(this.backupDir, result.date);
      const incrementalPath = path.join(this.backupDir, `${result.date}_incremental`);
      
      if (fs.existsSync(backupPath)) {
        try {
          fs.renameSync(backupPath, incrementalPath);
          console.log(`📝 Incremental backup saved to: ${incrementalPath}`);
        } catch (error) {
          console.error('Failed to rename incremental backup:', error.message);
        }
      }
    }
    
    return result;
  }
  
  getBackupStatus() {
    return {
      isRunning: this.isRunning,
      lastBackup: this.lastBackup,
      totalBackups: this.backupHistory.length,
      recentBackups: this.backupHistory.slice(0, 5),
      nextScheduledBackup: this.getNextScheduledBackup()
    };
  }
  
  getNextScheduledBackup() {
    const now = new Date();
    const schedules = [
      { name: 'Daily Full', time: '02:00', next: this.getNextRunTime('02:00') },
      { name: 'Weekly Full', time: 'Sunday 03:00', next: this.getNextWeeklyRunTime('Sunday', '03:00') },
      { name: 'Incremental', time: '12:00', next: this.getNextRunTime('12:00') }
    ];
    
    return schedules;
  }
  
  getNextRunTime(time) {
    const [hours, minutes] = time.split(':').map(Number);
    const now = new Date();
    const next = new Date();
    next.setHours(hours, minutes, 0, 0);
    
    if (next <= now) {
      next.setDate(next.getDate() + 1);
    }
    
    return next.toISOString();
  }
  
  getNextWeeklyRunTime(day, time) {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const targetDay = days.indexOf(day);
    const [hours, minutes] = time.split(':').map(Number);
    
    const now = new Date();
    const next = new Date();
    
    // Set to target day
    const currentDay = now.getDay();
    const daysToAdd = targetDay - currentDay;
    next.setDate(now.getDate() + (daysToAdd <= 0 ? daysToAdd + 7 : daysToAdd));
    next.setHours(hours, minutes, 0, 0);
    
    return next.toISOString();
  }
  
  cleanupOldBackups() {
    console.log('🧹 Cleaning up old backups...');
    
    try {
      const retentionDays = 30; // Keep backups for 30 days
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - retentionDays);
      
      // Clean local backups
      if (fs.existsSync(this.backupDir)) {
        const backups = fs.readdirSync(this.backupDir);
        let deletedCount = 0;
        
        backups.forEach(backup => {
          const backupPath = path.join(this.backupDir, backup);
          const stats = fs.statSync(backupPath);
          
          if (stats.mtime < cutoffDate) {
            fs.rmSync(backupPath, { recursive: true, force: true });
            deletedCount++;
          }
        });
        
        console.log(`🗑️ Deleted ${deletedCount} old local backups`);
      }
      
      // Clean cloud backups
      if (fs.existsSync(this.cloudDir)) {
        const backups = fs.readdirSync(this.cloudDir);
        let deletedCount = 0;
        
        backups.forEach(backup => {
          const backupPath = path.join(this.cloudDir, backup);
          const stats = fs.statSync(backupPath);
          
          if (stats.mtime < cutoffDate && backup !== 'backup_history.json') {
            fs.rmSync(backupPath, { recursive: true, force: true });
            deletedCount++;
          }
        });
        
        console.log(`☁️ Deleted ${deletedCount} old cloud backups`);
      }
      
    } catch (error) {
      console.error('Cleanup failed:', error.message);
    }
  }
  
  startScheduler() {
    console.log('⏰ Starting backup scheduler...');
    
    // Daily full backup at 02:00
    cron.schedule('0 2 * * *', async () => {
      console.log('🕐 Running scheduled daily full backup...');
      await this.runBackup();
    }, { timezone: 'Europe/Berlin' });
    
    // Weekly full backup on Sunday at 03:00
    cron.schedule('0 3 * * 0', async () => {
      console.log('🕐 Running scheduled weekly full backup...');
      await this.runBackup();
      await this.cleanupOldBackups(); // Cleanup after weekly backup
    }, { timezone: 'Europe/Berlin' });
    
    // Incremental backup at 12:00
    cron.schedule('0 12 * * *', async () => {
      console.log('🕐 Running scheduled incremental backup...');
      await this.runIncrementalBackup();
    }, { timezone: 'Europe/Berlin' });
    
    // Cleanup old backups daily at 04:00
    cron.schedule('0 4 * * *', async () => {
      console.log('🕐 Running scheduled cleanup...');
      await this.cleanupOldBackups();
    }, { timezone: 'Europe/Berlin' });
    
    console.log('✅ Backup scheduler started');
    console.log('📅 Schedule:');
    console.log('  - Daily full backup: 02:00');
    console.log('  - Weekly full backup: Sunday 03:00');
    console.log('  - Incremental backup: 12:00');
    console.log('  - Cleanup: 04:00');
  }
  
  // Manual backup trigger
  async triggerBackup(type = 'full') {
    console.log(`🔔 Manual backup triggered: ${type}`);
    
    if (type === 'incremental') {
      return await this.runIncrementalBackup();
    } else {
      return await this.runBackup();
    }
  }
}

// Initialize and start scheduler
const scheduler = new CloudBackupScheduler();

// Start scheduler
scheduler.startScheduler();

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down Cloud Backup Scheduler...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n🛑 Shutting down Cloud Backup Scheduler...');
  process.exit(0);
});

console.log('☁️ Cloud Backup Scheduler is running');
console.log('📊 Current status:', scheduler.getBackupStatus());
