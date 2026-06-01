/**
 * SuperMegaBot Maintenance Bot
 * Dependency Updates, Backup-Management, Log-Analyse
 */

const EventEmitter = require('events');
const fs = require('fs').promises;
const path = require('path');
const { exec } = require('child_process');
const util = require('util');
const execPromise = util.promisify(exec);

class MaintenanceBot extends EventEmitter {
  constructor() {
    super();
    this.name = 'MaintenanceBot';
    this.isRunning = false;
    this.checkInterval = 300000; // 5 Minuten
    this.maintenance = {
      dependencies: 0,
      backups: 0,
      logs: 0,
      cleanup: 0
    };
    this.backupSchedule = {
      enabled: true,
      interval: 3600000, // 1 Stunde
      maxBackups: 10,
      lastBackup: null
    };
    this.logAnalysis = {
      enabled: true,
      maxLogSize: 10 * 1024 * 1024, // 10MB
      retentionDays: 7,
      patterns: [
        { type: 'error', pattern: /ERROR|error|Error/i, severity: 'high' },
        { type: 'warning', pattern: /WARNING|warning|Warning/i, severity: 'medium' },
        { type: 'critical', pattern: /CRITICAL|critical|Critical/i, severity: 'critical' }
      ]
    };
  }

  async start() {
    if (this.isRunning) return;
    
    console.log('🔧 MaintenanceBot starting...');
    this.isRunning = true;
    
    // Start maintenance loop
    this.maintenanceLoop();
    
    // Start backup scheduler
    this.startBackupScheduler();
    
    // Initial maintenance tasks
    await this.performInitialMaintenance();
    
    console.log('✅ MaintenanceBot started successfully');
    this.emit('started', { bot: this.name, timestamp: new Date() });
  }

  async stop() {
    if (!this.isRunning) return;
    
    console.log('🛑 MaintenanceBot stopping...');
    this.isRunning = false;
    
    console.log('✅ MaintenanceBot stopped');
    this.emit('stopped', { bot: this.name, timestamp: new Date() });
  }

  async maintenanceLoop() {
    while (this.isRunning) {
      try {
        await this.checkDependencies();
        await this.analyzeLogs();
        await this.performCleanup();
        await this.checkSystemHealth();
        
        // Emit maintenance status
        this.emit('maintenanceStatus', this.maintenance);
        
      } catch (error) {
        console.error('❌ MaintenanceBot error:', error);
        this.emit('error', { bot: this.name, error: error.message });
      }
      
      // Wait for next check
      await new Promise(resolve => setTimeout(resolve, this.checkInterval));
    }
  }

  async performInitialMaintenance() {
    console.log('🔍 Performing initial maintenance...');
    
    // Create necessary directories
    await this.createDirectories();
    
    // Check dependencies
    await this.checkDependencies();
    
    // Analyze existing logs
    await this.analyzeLogs();
    
    // Perform initial backup
    await this.createBackup('initial');
    
    console.log('✅ Initial maintenance complete');
  }

  async createDirectories() {
    const directories = [
      'logs',
      'backups',
      'cache',
      'config',
      'reports',
      'temp'
    ];
    
    for (const dir of directories) {
      try {
        await fs.access(dir);
      } catch (error) {
        await fs.mkdir(dir, { recursive: true });
        console.log(`📁 Created directory: ${dir}`);
      }
    }
  }

  async checkDependencies() {
    try {
      // Check package.json
      const packageJson = await fs.readFile('package.json', 'utf8');
      const pkg = JSON.parse(packageJson);
      
      if (pkg.dependencies) {
        const dependencies = Object.keys(pkg.dependencies);
        console.log(`📦 Checking ${dependencies.length} dependencies...`);
        
        // Check for outdated packages
        try {
          const { stdout } = await execPromise('npm outdated --json');
          const outdated = JSON.parse(stdout);
          
          if (Object.keys(outdated).length > 0) {
            console.log(`⚠️ Found ${Object.keys(outdated).length} outdated packages`);
            await this.handleOutdatedPackages(outdated);
          }
        } catch (error) {
          // npm outdated failed, continue
        }
        
        // Check for security vulnerabilities
        try {
          const { stdout } = await execPromise('npm audit --json');
          const audit = JSON.parse(stdout);
          
          if (audit.vulnerabilities && Object.keys(audit.vulnerabilities).length > 0) {
            console.log(`🚨 Found ${Object.keys(audit.vulnerabilities).length} vulnerabilities`);
            await this.handleSecurityVulnerabilities(audit);
          }
        } catch (error) {
          // npm audit failed, continue
        }
      }
      
      this.maintenance.dependencies++;
    } catch (error) {
      console.error('❌ Dependency check failed:', error);
    }
  }

  async handleOutdatedPackages(outdated) {
    const updates = [];
    
    for (const [pkg, info] of Object.entries(outdated)) {
      updates.push({
        package: pkg,
        current: info.current,
        wanted: info.wanted,
        latest: info.latest,
        type: info.type || 'dependencies'
      });
    }
    
    // Save outdated packages report
    await fs.writeFile('reports/outdated-packages.json', JSON.stringify(updates, null, 2));
    
    // Auto-update patch versions
    for (const update of updates) {
      if (update.type === 'dependencies' && this.isPatchUpdate(update.current, update.latest)) {
        try {
          await execPromise(`npm update ${update.package}`);
          console.log(`✅ Updated ${update.package} to ${update.latest}`);
        } catch (error) {
          console.error(`❌ Failed to update ${update.package}:`, error);
        }
      }
    }
  }

  async handleSecurityVulnerabilities(audit) {
    const vulnerabilities = [];
    
    for (const [id, vuln] of Object.entries(audit.vulnerabilities)) {
      vulnerabilities.push({
        id,
        title: vuln.title,
        severity: vuln.severity,
        url: vuln.url,
        fixAvailable: vuln.fixAvailable
      });
    }
    
    // Save vulnerabilities report
    await fs.writeFile('reports/security-vulnerabilities.json', JSON.stringify(vulnerabilities, null, 2));
    
    // Auto-fix low severity vulnerabilities
    for (const vuln of vulnerabilities) {
      if (vuln.severity === 'low' && vuln.fixAvailable) {
        try {
          await execPromise('npm audit fix');
          console.log(`🔧 Fixed low severity vulnerability: ${vuln.title}`);
        } catch (error) {
          console.error(`❌ Failed to fix vulnerability: ${vuln.title}`);
        }
      }
    }
  }

  isPatchUpdate(current, latest) {
    const currentParts = current.split('.');
    const latestParts = latest.split('.');
    
    return currentParts[0] === latestParts[0] && 
           currentParts[1] === latestParts[1] && 
           currentParts[2] !== latestParts[2];
  }

  async startBackupScheduler() {
    if (!this.backupSchedule.enabled) return;
    
    console.log('💾 Starting backup scheduler...');
    
    const backupLoop = async () => {
      while (this.isRunning && this.backupSchedule.enabled) {
        try {
          await this.createBackup('scheduled');
          await this.cleanupOldBackups();
        } catch (error) {
          console.error('❌ Backup failed:', error);
        }
        
        // Wait for next backup
        await new Promise(resolve => setTimeout(resolve, this.backupSchedule.interval));
      }
    };
    
    backupLoop();
  }

  async createBackup(type = 'manual') {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupName = `backup-${type}-${timestamp}`;
    const backupDir = path.join('backups', backupName);
    
    console.log(`💾 Creating ${type} backup: ${backupName}`);
    
    try {
      // Create backup directory
      await fs.mkdir(backupDir, { recursive: true });
      
      // Backup critical files
      const filesToBackup = [
        'package.json',
        'package-lock.json',
        'api-config.json',
        '.env',
        'bots/',
        'config/',
        'utils/'
      ];
      
      for (const file of filesToBackup) {
        try {
          const stats = await fs.stat(file);
          if (stats.isDirectory()) {
            await this.copyDirectory(file, path.join(backupDir, file));
          } else {
            await fs.copyFile(file, path.join(backupDir, file));
          }
        } catch (error) {
          // File might not exist, continue
        }
      }
      
      // Create backup metadata
      const metadata = {
        name: backupName,
        type,
        timestamp: new Date().toISOString(),
        files: filesToBackup,
        size: await this.getDirectorySize(backupDir)
      };
      
      await fs.writeFile(path.join(backupDir, 'metadata.json'), JSON.stringify(metadata, null, 2));
      
      this.backupSchedule.lastBackup = new Date();
      this.maintenance.backups++;
      
      console.log(`✅ Backup created: ${backupName}`);
      this.emit('backupCreated', metadata);
      
    } catch (error) {
      console.error(`❌ Backup failed: ${backupName}`, error);
      throw error;
    }
  }

  async copyDirectory(src, dest) {
    await fs.mkdir(dest, { recursive: true });
    const entries = await fs.readdir(src, { withFileTypes: true });
    
    for (const entry of entries) {
      const srcPath = path.join(src, entry.name);
      const destPath = path.join(dest, entry.name);
      
      if (entry.isDirectory()) {
        await this.copyDirectory(srcPath, destPath);
      } else {
        await fs.copyFile(srcPath, destPath);
      }
    }
  }

  async getDirectorySize(dirPath) {
    let totalSize = 0;
    
    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });
      
      for (const entry of entries) {
        const entryPath = path.join(dirPath, entry.name);
        
        if (entry.isDirectory()) {
          totalSize += await this.getDirectorySize(entryPath);
        } else {
          const stats = await fs.stat(entryPath);
          totalSize += stats.size;
        }
      }
    } catch (error) {
      // Directory access error
    }
    
    return totalSize;
  }

  async cleanupOldBackups() {
    try {
      const backups = await fs.readdir('backups');
      const backupDirs = backups.filter(name => name.startsWith('backup-'));
      
      if (backupDirs.length > this.backupSchedule.maxBackups) {
        // Sort by creation time (newest first)
        const backupStats = [];
        
        for (const backupDir of backupDirs) {
          const fullPath = path.join('backups', backupDir);
          const stats = await fs.stat(fullPath);
          backupStats.push({ name: backupDir, path: fullPath, mtime: stats.mtime });
        }
        
        backupStats.sort((a, b) => b.mtime - a.mtime);
        
        // Remove oldest backups
        const toRemove = backupStats.slice(this.backupSchedule.maxBackups);
        
        for (const backup of toRemove) {
          await this.removeDirectory(backup.path);
          console.log(`🗑️ Removed old backup: ${backup.name}`);
        }
      }
    } catch (error) {
      console.error('❌ Backup cleanup failed:', error);
    }
  }

  async removeDirectory(dirPath) {
    try {
      await fs.rm(dirPath, { recursive: true, force: true });
    } catch (error) {
      // Fallback for older Node.js versions
      try {
        const { stdout } = await execPromise(`rm -rf "${dirPath}"`);
      } catch (rmError) {
        console.error(`❌ Failed to remove directory ${dirPath}:`, rmError);
      }
    }
  }

  async analyzeLogs() {
    if (!this.logAnalysis.enabled) return;
    
    try {
      const logFiles = await fs.readdir('logs');
      const logAnalysis = {
        timestamp: new Date().toISOString(),
        files: [],
        summary: {
          totalErrors: 0,
          totalWarnings: 0,
          totalCritical: 0,
          largestFile: null,
          totalSize: 0
        }
      };
      
      for (const logFile of logFiles) {
        if (logFile.endsWith('.log')) {
          const analysis = await this.analyzeLogFile(logFile);
          logAnalysis.files.push(analysis);
          
          // Update summary
          logAnalysis.summary.totalErrors += analysis.errors;
          logAnalysis.summary.totalWarnings += analysis.warnings;
          logAnalysis.summary.totalCritical += analysis.critical;
          logAnalysis.summary.totalSize += analysis.size;
          
          if (!logAnalysis.summary.largestFile || analysis.size > logAnalysis.summary.largestFile.size) {
            logAnalysis.summary.largestFile = analysis;
          }
        }
      }
      
      // Save log analysis
      await fs.writeFile('reports/log-analysis.json', JSON.stringify(logAnalysis, null, 2));
      
      // Handle large log files
      for (const file of logAnalysis.files) {
        if (file.size > this.logAnalysis.maxLogSize) {
          await this.rotateLogFile(file.name);
        }
      }
      
      // Clean old logs
      await this.cleanOldLogs();
      
      this.maintenance.logs++;
      console.log(`📊 Analyzed ${logAnalysis.files.length} log files`);
      
    } catch (error) {
      console.error('❌ Log analysis failed:', error);
    }
  }

  async analyzeLogFile(logFile) {
    const filePath = path.join('logs', logFile);
    const stats = await fs.stat(filePath);
    
    const analysis = {
      name: logFile,
      size: stats.size,
      modified: stats.mtime,
      errors: 0,
      warnings: 0,
      critical: 0,
      lines: 0
    };
    
    try {
      const content = await fs.readFile(filePath, 'utf8');
      const lines = content.split('\n');
      analysis.lines = lines.length;
      
      for (const pattern of this.logAnalysis.patterns) {
        const matches = content.match(pattern.pattern);
        const count = matches ? matches.length : 0;
        
        switch (pattern.type) {
          case 'error':
            analysis.errors += count;
            break;
          case 'warning':
            analysis.warnings += count;
            break;
          case 'critical':
            analysis.critical += count;
            break;
        }
      }
    } catch (error) {
      // File read error
    }
    
    return analysis;
  }

  async rotateLogFile(logFile) {
    const filePath = path.join('logs', logFile);
    const rotatedPath = path.join('logs', `${logFile}.old`);
    
    try {
      await fs.rename(filePath, rotatedPath);
      console.log(`📝 Rotated log file: ${logFile}`);
    } catch (error) {
      console.error(`❌ Failed to rotate log file ${logFile}:`, error);
    }
  }

  async cleanOldLogs() {
    const retentionMs = this.logAnalysis.retentionDays * 24 * 60 * 60 * 1000;
    const cutoffTime = Date.now() - retentionMs;
    
    try {
      const logFiles = await fs.readdir('logs');
      
      for (const logFile of logFiles) {
        const filePath = path.join('logs', logFile);
        const stats = await fs.stat(filePath);
        
        if (stats.mtime.getTime() < cutoffTime) {
          await fs.unlink(filePath);
          console.log(`🗑️ Removed old log: ${logFile}`);
        }
      }
    } catch (error) {
      console.error('❌ Log cleanup failed:', error);
    }
  }

  async performCleanup() {
    const cleanupTasks = [
      this.cleanupTempFiles,
      this.cleanupCache,
      this.cleanupOldReports
    ];
    
    for (const task of cleanupTasks) {
      try {
        await task.call(this);
      } catch (error) {
        console.error('❌ Cleanup task failed:', error);
      }
    }
    
    this.maintenance.cleanup++;
  }

  async cleanupTempFiles() {
    try {
      const files = await fs.readdir('temp');
      const tempFiles = files.filter(file => 
        file.startsWith('.tmp') || 
        file.startsWith('~') || 
        file.endsWith('.tmp')
      );
      
      for (const tempFile of tempFiles) {
        await fs.unlink(path.join('temp', tempFile));
      }
      
      console.log(`🧹 Cleaned ${tempFiles.length} temp files`);
    } catch (error) {
      // Temp directory might not exist
    }
  }

  async cleanupCache() {
    try {
      const cacheDir = 'cache';
      const files = await fs.readdir(cacheDir);
      const now = Date.now();
      let cleaned = 0;
      
      for (const file of files) {
        const filePath = path.join(cacheDir, file);
        const stats = await fs.stat(filePath);
        
        // Remove cache files older than 1 hour
        if (now - stats.mtime.getTime() > 3600000) {
          await fs.unlink(filePath);
          cleaned++;
        }
      }
      
      console.log(`🧹 Cleaned ${cleaned} cache files`);
    } catch (error) {
      // Cache directory might not exist
    }
  }

  async cleanupOldReports() {
    try {
      const reports = await fs.readdir('reports');
      const now = Date.now();
      const retentionMs = 7 * 24 * 60 * 60 * 1000; // 7 days
      
      for (const report of reports) {
        const filePath = path.join('reports', report);
        const stats = await fs.stat(filePath);
        
        if (now - stats.mtime.getTime() > retentionMs) {
          await fs.unlink(filePath);
          console.log(`🗑️ Removed old report: ${report}`);
        }
      }
    } catch (error) {
      // Reports directory might not exist
    }
  }

  async checkSystemHealth() {
    const health = {
      timestamp: new Date().toISOString(),
      memory: process.memoryUsage(),
      uptime: process.uptime(),
      version: process.version,
      platform: process.platform
    };
    
    // Save health report
    await fs.writeFile('reports/system-health.json', JSON.stringify(health, null, 2));
  }

  getMaintenanceStatus() {
    return {
      ...this.maintenance,
      backupSchedule: this.backupSchedule,
      logAnalysis: this.logAnalysis,
      isRunning: this.isRunning
    };
  }

  async generateMaintenanceReport() {
    const report = {
      timestamp: new Date().toISOString(),
      maintenance: this.maintenance,
      backupSchedule: this.backupSchedule,
      logAnalysis: this.logAnalysis,
      recommendations: await this.generateMaintenanceRecommendations()
    };
    
    await fs.writeFile('reports/maintenance-report.json', JSON.stringify(report, null, 2));
    return report;
  }

  async generateMaintenanceRecommendations() {
    const recommendations = [];
    
    // Analyze maintenance data and generate recommendations
    if (this.maintenance.dependencies === 0) {
      recommendations.push({
        type: 'dependencies',
        priority: 'medium',
        description: 'No dependency checks performed recently',
        action: 'run_dependency_check'
      });
    }
    
    if (!this.backupSchedule.lastBackup || Date.now() - this.backupSchedule.lastBackup.getTime() > 7200000) {
      recommendations.push({
        type: 'backup',
        priority: 'high',
        description: 'No recent backup found',
        action: 'create_backup'
      });
    }
    
    return recommendations;
  }
}

// Singleton instance
let maintenanceBot = null;

function getMaintenanceBot() {
  if (!maintenanceBot) {
    maintenanceBot = new MaintenanceBot();
  }
  return maintenanceBot;
}

module.exports = {
  MaintenanceBot,
  getMaintenanceBot
};
