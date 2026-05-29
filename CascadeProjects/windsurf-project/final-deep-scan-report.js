#!/usr/bin/env node

/**
 * 🔍 FINAL COMPREHENSIVE DEEP SCAN REPORT
 * Scans entire system: code, APIs, cloud, security, performance
 */

import fs from 'fs';
import path from 'path';
import os from 'os';
import { execSync } from 'child_process';

const PROJECT_DIR = process.cwd();
const REPORT_FILE = path.join(PROJECT_DIR, 'FINAL_DEEP_SCAN_REPORT.json');

class FinalDeepScan {
  constructor() {
    this.issues = { critical: [], warning: [], info: [] };
    this.scanResults = {};
    this.startTime = Date.now();
  }

  log(msg, level = 'INFO') {
    const ts = new Date().toISOString();
    console.debug(`[${ts}] [${level}] ${msg}`);
  }

  async run() {
    this.log('🚀 Starting FINAL COMPREHENSIVE DEEP SCAN...');

    await this.scanProjectFiles();
    await this.scanSecurity();
    await this.scanAPIs();
    await this.scanCloudData();
    await this.scanSystemHealth();
    await this.scanPerformance();
    await this.scanDependencies();
    await this.scanGitStatus();

    const report = this.generateReport();
    fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2));

    this.printSummary(report);
    this.log(`✅ Report saved to: ${REPORT_FILE}`);
    return report;
  }

  getAllSourceFiles() {
    const files = [];
    const entries = fs.readdirSync(PROJECT_DIR, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isFile() && (entry.name.endsWith('.js') || entry.name.endsWith('.py') || entry.name.endsWith('.json') || entry.name.endsWith('.env') || entry.name.endsWith('.md'))) {
        files.push(path.join(PROJECT_DIR, entry.name));
      }
    }
    // Include lib and services dirs
    for (const subdir of ['lib', 'services', 'prisma', 'templates']) {
      const subPath = path.join(PROJECT_DIR, subdir);
      if (fs.existsSync(subPath)) {
        const subFiles = this.walkDir(subPath);
        files.push(...subFiles);
      }
    }
    return files;
  }

  walkDir(dir) {
    const files = [];
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory() && entry.name !== 'node_modules') {
        files.push(...this.walkDir(fullPath));
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
    return files;
  }

  async scanProjectFiles() {
    this.log('📁 Scanning project files...');
    const files = this.getAllSourceFiles();
    const stats = { totalFiles: files.length, byType: {}, totalLines: 0, largestFiles: [] };

    for (const file of files) {
      const ext = path.extname(file);
      stats.byType[ext] = (stats.byType[ext] || 0) + 1;
      try {
        const content = fs.readFileSync(file, 'utf8');
        const lines = content.split('\n').length;
        stats.totalLines += lines;
        stats.largestFiles.push({ file: path.relative(PROJECT_DIR, file), lines });
      } catch (e) {}
    }

    stats.largestFiles.sort((a, b) => b.lines - a.lines);
    this.scanResults.projectFiles = stats;
    this.log(`✅ Found ${files.length} files, ${stats.totalLines} total lines`);
  }

  async scanSecurity() {
    this.log('🔒 Scanning security...');
    const files = this.getAllSourceFiles();
    const securityIssues = [];

    const patterns = [
      { regex: /password\s*=\s*['"`][^'"`]+['"`]/i, type: 'hardcoded-password', severity: 'critical' },
      { regex: /api[_-]?key\s*=\s*['"`][^'"`]+['"`]/i, type: 'hardcoded-api-key', severity: 'critical' },
      { regex: /secret\s*=\s*['"`][^'"`]+['"`]/i, type: 'hardcoded-secret', severity: 'critical' },
      { regex: /token\s*=\s*['"`][^'"`]{20,}['"`]/i, type: 'hardcoded-token', severity: 'critical' },
      { regex: /innerHTML\s*=/, type: 'xss-risk', severity: 'high' },
      { regex: /eval\s*\(/, type: 'eval-risk', severity: 'high' },
      { regex: /exec\s*\(/, type: 'command-injection-risk', severity: 'medium' },
    ];

    for (const file of files) {
      if (file.endsWith('.md') || file.endsWith('package-lock.json')) continue;
      try {
        const content = fs.readFileSync(file, 'utf8');
        const lines = content.split('\n');
        for (let i = 0; i < lines.length; i++) {
          for (const { regex, type, severity } of patterns) {
            if (regex.test(lines[i])) {
              const issue = {
                file: path.relative(PROJECT_DIR, file),
                line: i + 1,
                type,
                severity,
                snippet: lines[i].trim().substring(0, 100)
              };
              securityIssues.push(issue);
              this.issues[severity === 'critical' ? 'critical' : severity === 'high' ? 'warning' : 'info'].push(issue);
            }
          }
        }
      } catch (e) {}
    }

    this.scanResults.security = {
      totalIssues: securityIssues.length,
      byType: securityIssues.reduce((acc, i) => { acc[i.type] = (acc[i.type] || 0) + 1; return acc; }, {}),
      issues: securityIssues
    };
    this.log(`✅ Security scan: ${securityIssues.length} issues found`);
  }

  async scanAPIs() {
    this.log('🔌 Scanning API integrations...');
    const apis = [];

    // Check for Supabase
    if (fs.existsSync(path.join(PROJECT_DIR, 'lib', 'supabase.js'))) {
      apis.push({ name: 'Supabase', file: 'lib/supabase.js', status: 'configured' });
    }

    // Check for Telegram
    const telegramFiles = ['telegram-direct-client.js', 'telegram-notification-client.js'];
    for (const tf of telegramFiles) {
      if (fs.existsSync(path.join(PROJECT_DIR, 'services', tf))) {
        apis.push({ name: 'Telegram Bot', file: `services/${tf}`, status: 'configured' });
      }
    }

    // Check for Prisma
    if (fs.existsSync(path.join(PROJECT_DIR, 'prisma', 'schema.prisma'))) {
      apis.push({ name: 'Prisma ORM', file: 'prisma/schema.prisma', status: 'configured' });
    }

    // Check for cloud backup
    if (fs.existsSync(path.join(PROJECT_DIR, 'cloud-backup-manager.js'))) {
      apis.push({ name: 'Cloud Backup Manager', file: 'cloud-backup-manager.js', status: 'configured' });
    }

    // Check environment variables
    const envFiles = ['.env', 'API_CONFIG_TEMPLATE.env'];
    for (const ef of envFiles) {
      if (fs.existsSync(path.join(PROJECT_DIR, ef))) {
        apis.push({ name: 'Environment Config', file: ef, status: 'present' });
      }
    }

    this.scanResults.apis = apis;
    this.log(`✅ API scan: ${apis.length} integrations found`);
  }

  async scanCloudData() {
    this.log('☁️ Scanning cloud data...');
    const cloudStatus = { backups: [], syncStatus: 'unknown', externalServices: [] };

    // Check backup directories
    const backupDir = path.join(os.homedir(), 'RudiBot-Data', 'backups');
    const cloudDir = path.join(os.homedir(), 'RudiBot-Data', 'cloud-sync');

    if (fs.existsSync(backupDir)) {
      const backups = fs.readdirSync(backupDir).filter(d => d.startsWith('rudibot-'));
      cloudStatus.backups = backups.map(b => ({
        name: b,
        path: path.join(backupDir, b),
        date: fs.statSync(path.join(backupDir, b)).mtime
      }));
    }

    if (fs.existsSync(cloudDir)) {
      cloudStatus.syncStatus = 'active';
    } else {
      cloudStatus.syncStatus = 'not-configured';
    }

    // Check for external notification services
    if (fs.existsSync(path.join(PROJECT_DIR, 'services', 'external-notification-example.js'))) {
      cloudStatus.externalServices.push('External Notification Service');
    }

    this.scanResults.cloudData = cloudStatus;
    this.log(`✅ Cloud scan: ${cloudStatus.backups.length} backups found`);
  }

  async scanSystemHealth() {
    this.log('🏥 Scanning system health...');
    const health = {
      platform: os.platform(),
      arch: os.arch(),
      uptime: os.uptime(),
      totalMemory: os.totalmem(),
      freeMemory: os.freemem(),
      memoryUsage: ((1 - os.freemem() / os.totalmem()) * 100).toFixed(2),
      cpuCount: os.cpus().length,
      loadAverage: os.loadavg(),
      hostname: os.hostname()
    };

    if (health.memoryUsage > 85) {
      this.issues.critical.push({ type: 'high-memory-usage', message: `Memory usage: ${health.memoryUsage}%` });
    }

    this.scanResults.systemHealth = health;
    this.log(`✅ System health: ${health.memoryUsage}% memory usage`);
  }

  async scanPerformance() {
    this.log('⚡ Scanning performance...');
    const perfIssues = [];
    const files = this.getAllSourceFiles().filter(f => f.endsWith('.js') || f.endsWith('.py'));

    const patterns = [
      { regex: /for\s*\(\s*.*\s*in\s*.*\.length\s*\)/, type: 'inefficient-loop' },
      { regex: /console\.log\(/, type: 'debug-statement' },
      { regex: /var\s+\w+/, type: 'deprecated-var' },
      { regex: /setInterval\s*\(/, type: 'potential-memory-leak' },
      { regex: /\.addEventListener\s*\(/, type: 'event-listener' },
    ];

    for (const file of files) {
      try {
        const content = fs.readFileSync(file, 'utf8');
        const lines = content.split('\n');
        for (let i = 0; i < lines.length; i++) {
          for (const { regex, type } of patterns) {
            if (regex.test(lines[i])) {
              perfIssues.push({ file: path.relative(PROJECT_DIR, file), line: i + 1, type });
            }
          }
        }
      } catch (e) {}
    }

    this.scanResults.performance = {
      totalIssues: perfIssues.length,
      byType: perfIssues.reduce((acc, i) => { acc[i.type] = (acc[i.type] || 0) + 1; return acc; }, {}),
      issues: perfIssues.slice(0, 50) // Limit output
    };
    this.log(`✅ Performance scan: ${perfIssues.length} issues found`);
  }

  async scanDependencies() {
    this.log('📦 Scanning dependencies...');
    const deps = { node: [], python: [], outdated: [] };

    if (fs.existsSync(path.join(PROJECT_DIR, 'package.json'))) {
      try {
        const pkg = JSON.parse(fs.readFileSync(path.join(PROJECT_DIR, 'package.json'), 'utf8'));
        deps.node = Object.keys(pkg.dependencies || {});
        deps.devNode = Object.keys(pkg.devDependencies || {});
      } catch (e) {}
    }

    // Check for package-lock for version info
    if (fs.existsSync(path.join(PROJECT_DIR, 'node_modules'))) {
      const nmSize = this.getDirSize(path.join(PROJECT_DIR, 'node_modules'));
      deps.nodeModulesSize = `${(nmSize / 1024 / 1024).toFixed(2)} MB`;
    }

    this.scanResults.dependencies = deps;
    this.log(`✅ Dependencies: ${deps.node.length} Node packages`);
  }

  async scanGitStatus() {
    this.log('📝 Scanning git status...');
    const gitStatus = { branch: 'unknown', uncommitted: 0, untracked: 0, lastCommit: null };

    try {
      gitStatus.branch = execSync('git rev-parse --abbrev-ref HEAD', { cwd: PROJECT_DIR, encoding: 'utf8' }).trim();
    } catch (e) {}

    try {
      const status = execSync('git status --porcelain', { cwd: PROJECT_DIR, encoding: 'utf8' });
      const lines = status.split('\n').filter(l => l.trim());
      gitStatus.uncommitted = lines.filter(l => l.startsWith('M') || l.startsWith('A') || l.startsWith('D')).length;
      gitStatus.untracked = lines.filter(l => l.startsWith('??')).length;
    } catch (e) {}

    try {
      gitStatus.lastCommit = execSync('git log -1 --format=%cd', { cwd: PROJECT_DIR, encoding: 'utf8' }).trim();
    } catch (e) {}

    this.scanResults.gitStatus = gitStatus;
    this.log(`✅ Git status: ${gitStatus.uncommitted} uncommitted, ${gitStatus.untracked} untracked`);
  }

  getDirSize(dir) {
    let size = 0;
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        size += this.getDirSize(fullPath);
      } else {
        size += fs.statSync(fullPath).size;
      }
    }
    return size;
  }

  generateReport() {
    return {
      scanMeta: {
        timestamp: new Date().toISOString(),
        duration: Date.now() - this.startTime,
        projectDir: PROJECT_DIR,
        hostname: os.hostname()
      },
      summary: {
        totalIssues: this.issues.critical.length + this.issues.warning.length + this.issues.info.length,
        critical: this.issues.critical.length,
        warnings: this.issues.warning.length,
        info: this.issues.info.length
      },
      issues: this.issues,
      ...this.scanResults
    };
  }

  printSummary(report) {
    console.debug('\n' + '='.repeat(70));
    console.debug('🔍  F I N A L   D E E P   S C A N   R E P O R T');
    console.debug('='.repeat(70));
    console.debug(`\n📊  SUMMARY`);
    console.debug(`   Total Issues: ${report.summary.totalIssues}`);
    console.debug(`   Critical:     ${report.summary.critical}`);
    console.debug(`   Warnings:     ${report.summary.warnings}`);
    console.debug(`   Info:         ${report.summary.info}`);
    console.debug(`\n📁  PROJECT FILES`);
    console.debug(`   Total Files:  ${report.projectFiles?.totalFiles || 0}`);
    console.debug(`   Total Lines:  ${report.projectFiles?.totalLines || 0}`);
    console.debug(`\n🔌  API INTEGRATIONS`);
    report.apis?.forEach(api => console.debug(`   ${api.name}: ${api.status}`));
    console.debug(`\n☁️  CLOUD DATA`);
    console.debug(`   Backups:      ${report.cloudData?.backups?.length || 0}`);
    console.debug(`   Sync Status:  ${report.cloudData?.syncStatus || 'unknown'}`);
    console.debug(`\n🏥  SYSTEM HEALTH`);
    console.debug(`   Memory:       ${report.systemHealth?.memoryUsage}%`);
    console.debug(`   Uptime:       ${Math.floor(report.systemHealth?.uptime / 3600)}h`);
    console.debug(`\n⚡  PERFORMANCE`);
    console.debug(`   Issues:       ${report.performance?.totalIssues || 0}`);
    console.debug(`\n📦  DEPENDENCIES`);
    console.debug(`   Node:         ${report.dependencies?.node?.length || 0} packages`);
    console.debug(`   Size:         ${report.dependencies?.nodeModulesSize || 'N/A'}`);
    console.debug(`\n📝  GIT`);
    console.debug(`   Branch:       ${report.gitStatus?.branch}`);
    console.debug(`   Uncommitted:  ${report.gitStatus?.uncommitted}`);
    console.debug(`   Untracked:    ${report.gitStatus?.untracked}`);

    if (report.issues.critical.length > 0) {
      console.debug(`\n🚨  CRITICAL ISSUES:`);
      report.issues.critical.slice(0, 5).forEach(i => console.debug(`   • [${i.type}] ${i.file}:${i.line} - ${i.snippet || i.message}`));
    }

    console.debug('\n' + '='.repeat(70));
    console.debug(`📄 Full report: ${REPORT_FILE}`);
    console.debug('='.repeat(70) + '\n');
  }
}

// Run the scan
const scanner = new FinalDeepScan();
scanner.run().catch(err => {
  console.error('❌ Scan failed:', err);
  process.exit(1);
});
