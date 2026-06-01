/**
 * SuperMegaBot Maintenance Bot - Backup-Management, Update-Management, Security-Patches
 * Zuständig: Backup-Management, Update-Management, Security-Patches, Dependency Updates
 */

import fs from 'fs';
import { exec } from 'child_process';
import path from 'path';
import crypto from 'crypto';

class MaintenanceBot {
  constructor() {
    this.name = 'MaintenanceBot';
    this.interval = 300000; // 5 Minuten
    this.isRunning = false;
    this.maintenanceTasks = [];
    this.backupDirectory = path.join(process.cwd(), 'backups');
    this.logDirectory = path.join(process.cwd(), 'logs');
  }

  async start() {
    console.log(`🤖 ${this.name} starting...`);
    this.isRunning = true;
    
    // Ensure directories exist
    this.ensureDirectories();
    
    // Haupt-Maintenance Loop
    this.maintenanceInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      await this.performMaintenance();
    }, this.interval);
    
    console.log(`✅ ${this.name} started - Running maintenance every ${this.interval/1000}s`);
  }

  ensureDirectories() {
    const dirs = [this.backupDirectory, this.logDirectory];
    for (const dir of dirs) {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
        console.log(`📁 Created directory: ${dir}`);
      }
    }
  }

  async performMaintenance() {
    console.log(`🔧 ${this.name}: Performing maintenance tasks...`);
    
    // 1. Backup Management
    await this.manageBackups();
    
    // 2. Update Management
    await this.manageUpdates();
    
    // 3. Security Patches
    await this.checkSecurityPatches();
    
    // 4. Dependency Updates
    await this.manageDependencies();
    
    // 5. Log Rotation
    await this.rotateLogs();
    
    // 6. Health Check
    await this.performHealthCheck();
  }

  async manageBackups() {
    console.log(`💾 ${this.name}: Managing backups...`);
    
    // Create daily backup if not exists
    const today = new Date().toISOString().split('T')[0];
    const dailyBackupPath = path.join(this.backupDirectory, `backup_${today}`);
    
    if (!fs.existsSync(dailyBackupPath)) {
      console.log(`📦 ${this.name}: Creating daily backup...`);
      await this.createBackup(dailyBackupPath);
      
      this.maintenanceTasks.push({
        type: 'backup',
        action: 'create_daily',
        timestamp: new Date().toISOString(),
        path: dailyBackupPath
      });
    }
    
    // Clean old backups (keep last 7 days)
    await this.cleanOldBackups(7);
    
    // Verify backup integrity
    await this.verifyBackups();
  }

  async createBackup(backupPath) {
    try {
      // Create backup directory
      fs.mkdirSync(backupPath, { recursive: true });
      
      // Backup important files
      const filesToBackup = [
        'package.json',
        'api-config.json',
        '.env',
        'prisma/schema.prisma'
      ];
      
      for (const file of filesToBackup) {
        const sourcePath = path.join(process.cwd(), file);
        if (fs.existsSync(sourcePath)) {
          const destPath = path.join(backupPath, file);
          fs.copyFileSync(sourcePath, destPath);
          console.log(`📄 Backed up: ${file}`);
        }
      }
      
      // Backup source code (excluding node_modules)
      await this.execCommand(`cp -r $(find . -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" | grep -v node_modules) ${backupPath}/`);
      
      // Create backup metadata
      const metadata = {
        timestamp: new Date().toISOString(),
        files: filesToBackup,
        checksum: this.calculateDirectoryChecksum(backupPath)
      };
      
      fs.writeFileSync(
        path.join(backupPath, 'metadata.json'),
        JSON.stringify(metadata, null, 2)
      );
      
      console.log(`✅ Backup created: ${backupPath}`);
    } catch (error) {
      console.error(`❌ Backup creation failed:`, error.message);
    }
  }

  async cleanOldBackups(daysToKeep) {
    try {
      const backups = fs.readdirSync(this.backupDirectory);
      const now = Date.now();
      const maxAge = daysToKeep * 24 * 60 * 60 * 1000;
      
      for (const backup of backups) {
        const backupPath = path.join(this.backupDirectory, backup);
        const stats = fs.statSync(backupPath);
        
        if (now - stats.mtimeMs > maxAge) {
          console.log(`🗑️ ${this.name}: Removing old backup: ${backup}`);
          await this.execCommand(`rm -rf ${backupPath}`);
          
          this.maintenanceTasks.push({
            type: 'backup',
            action: 'remove_old',
            timestamp: new Date().toISOString(),
            path: backupPath
          });
        }
      }
    } catch (error) {
      console.error('Failed to clean old backups:', error.message);
    }
  }

  async verifyBackups() {
    try {
      const backups = fs.readdirSync(this.backupDirectory);
      
      for (const backup of backups) {
        const backupPath = path.join(this.backupDirectory, backup);
        const metadataPath = path.join(backupPath, 'metadata.json');
        
        if (fs.existsSync(metadataPath)) {
          const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf-8'));
          const currentChecksum = this.calculateDirectoryChecksum(backupPath);
          
          if (metadata.checksum !== currentChecksum) {
            console.warn(`⚠️ ${this.name}: Backup integrity check failed for ${backup}`);
          }
        }
      }
    } catch (error) {
      console.error('Backup verification failed:', error.message);
    }
  }

  calculateDirectoryChecksum(dir) {
    const hash = crypto.createHash('sha256');
    
    const files = this.getAllFiles(dir);
    for (const file of files) {
      const content = fs.readFileSync(file);
      hash.update(content);
    }
    
    return hash.digest('hex');
  }

  getAllFiles(dir) {
    const files = [];
    
    const items = fs.readdirSync(dir);
    for (const item of items) {
      const fullPath = path.join(dir, item);
      const stats = fs.statSync(fullPath);
      
      if (stats.isDirectory()) {
        files.push(...this.getAllFiles(fullPath));
      } else {
        files.push(fullPath);
      }
    }
    
    return files;
  }

  async manageUpdates() {
    console.log(`🔄 ${this.name}: Checking for updates...`);
    
    // Check for npm updates
    try {
      const outdated = await this.execCommand('npm outdated --json');
      if (outdated) {
        const outdatedPackages = JSON.parse(outdated);
        console.log(`📦 ${this.name}: ${Object.keys(outdatedPackages).length} outdated packages`);
        
        this.maintenanceTasks.push({
          type: 'update',
          action: 'check_outdated',
          timestamp: new Date().toISOString(),
          count: Object.keys(outdatedPackages).length
        });
      }
    } catch (error) {
      // No outdated packages or command failed
    }
    
    // Check for git updates if in git repository
    if (fs.existsSync('.git')) {
      try {
        const status = await this.execCommand('git status --short');
        if (status.trim()) {
          console.log(`⚠️ ${this.name}: Uncommitted changes detected`);
        }
        
        const branch = await this.execCommand('git rev-parse --abbrev-ref HEAD');
        console.log(`🌿 ${this.name}: Current branch: ${branch.trim()}`);
      } catch (error) {
        console.error('Git check failed:', error.message);
      }
    }
  }

  async checkSecurityPatches() {
    console.log(`🔒 ${this.name}: Checking for security patches...`);
    
    // Run npm audit
    try {
      const auditResult = await this.execCommand('npm audit --json');
      const auditData = JSON.parse(auditResult);
      
      if (auditData.vulnerabilities && Object.keys(auditData.vulnerabilities).length > 0) {
        const vulnCount = Object.keys(auditData.vulnerabilities).length;
        console.log(`🚨 ${this.name}: ${vulnCount} vulnerabilities found`);
        
        this.maintenanceTasks.push({
          type: 'security',
          action: 'vulnerabilities_found',
          timestamp: new Date().toISOString(),
          count: vulnCount
        });
        
        // Attempt auto-fix for low-severity vulnerabilities
        try {
          await this.execCommand('npm audit fix');
          console.log(`✅ ${this.name}: Auto-fixed vulnerabilities`);
        } catch (error) {
          console.log(`⚠️ ${this.name}: Some vulnerabilities require manual fix`);
        }
      } else {
        console.log(`✅ ${this.name}: No vulnerabilities found`);
      }
    } catch (error) {
      console.error('Security audit failed:', error.message);
    }
  }

  async manageDependencies() {
    console.log(`📦 ${this.name}: Managing dependencies...`);
    
    // Check for unused dependencies
    try {
      const depcheckResult = await this.execCommand('npx depcheck --json');
      const depcheckData = JSON.parse(depcheckResult);
      
      if (depcheckData.dependencies && Object.keys(depcheckData.dependencies).length > 0) {
        console.log(`🗑️ ${this.name}: ${Object.keys(depcheckData.dependencies).length} unused dependencies`);
        
        this.maintenanceTasks.push({
          type: 'dependency',
          action: 'unused_found',
          timestamp: new Date().toISOString(),
          count: Object.keys(depcheckData.dependencies).length
        });
      }
    } catch (error) {
      // depcheck not installed or no unused dependencies
    }
  }

  async rotateLogs() {
    console.log(`📝 ${this.name}: Rotating logs...`);
    
    const logFiles = [
      'monitoring.log',
      'alerts.log',
      'api-usage.log',
      'maintenance.log'
    ];
    
    for (const logFile of logFiles) {
      const logPath = path.join(this.logDirectory, logFile);
      
      if (fs.existsSync(logPath)) {
        const stats = fs.statSync(logPath);
        const sizeInMB = stats.size / (1024 * 1024);
        
        // Rotate if log file is larger than 10MB
        if (sizeInMB > 10) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const rotatedPath = path.join(this.logDirectory, `${logFile}.${timestamp}`);
          
          fs.renameSync(logPath, rotatedPath);
          console.log(`🔄 ${this.name}: Rotated log: ${logFile}`);
          
          this.maintenanceTasks.push({
            type: 'log',
            action: 'rotate',
            timestamp: new Date().toISOString(),
            file: logFile,
            size: sizeInMB
          });
        }
      }
    }
  }

  async performHealthCheck() {
    console.log(`🏥 ${this.name}: Performing health check...`);
    
    // Check disk space
    try {
      const dfResult = await this.execCommand('df -h .');
      const lines = dfResult.split('\n');
      if (lines.length > 1) {
        const parts = lines[1].split(/\s+/);
        const usedPercent = parts[4];
        
        if (parseInt(usedPercent) > 80) {
          console.warn(`⚠️ ${this.name}: Disk usage high: ${usedPercent}`);
          
          this.maintenanceTasks.push({
            type: 'health',
            action: 'disk_warning',
            timestamp: new Date().toISOString(),
            usage: usedPercent
          });
        }
      }
    } catch (error) {
      console.error('Disk check failed:', error.message);
    }
    
    // Check process health
    const memUsage = process.memoryUsage();
    if (memUsage.heapUsed > 500 * 1024 * 1024) {
      console.warn(`⚠️ ${this.name}: High memory usage: ${(memUsage.heapUsed / 1024 / 1024).toFixed(2)} MB`);
    }
  }

  async execCommand(command) {
    return new Promise((resolve, reject) => {
      exec(command, { cwd: process.cwd() }, (error, stdout, stderr) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(stdout);
      });
    });
  }

  async stop() {
    console.log(`🛑 ${this.name} stopping...`);
    this.isRunning = false;
    clearInterval(this.maintenanceInterval);
    console.log(`✅ ${this.name} stopped`);
  }

  getStatus() {
    return {
      name: this.name,
      isRunning: this.isRunning,
      interval: this.interval,
      tasksPerformed: this.maintenanceTasks.length,
      backupDirectory: this.backupDirectory,
      logDirectory: this.logDirectory
    };
  }

  getMaintenanceReport() {
    return {
      totalTasks: this.maintenanceTasks.length,
      tasksByType: this.groupTasksByType(),
      recentTasks: this.maintenanceTasks.slice(-10),
      backupCount: fs.readdirSync(this.backupDirectory).length
    };
  }

  groupTasksByType() {
    const grouped = {};
    for (const task of this.maintenanceTasks) {
      if (!grouped[task.type]) {
        grouped[task.type] = 0;
      }
      grouped[task.type]++;
    }
    return grouped;
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new MaintenanceBot();
  bot.start();
  
  // Graceful shutdown
  process.on('SIGINT', async () => {
    await bot.stop();
    process.exit(0);
  });
}

export default MaintenanceBot;
