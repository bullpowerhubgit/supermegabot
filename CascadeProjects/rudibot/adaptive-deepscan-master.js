#!/usr/bin/env node
/**
 * Adaptive Deep-Scan Master System
 * Advanced file system scanning with adaptive algorithms, security analysis, and reporting
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');

class AdaptiveDeepScanMaster {
  constructor(options = {}) {
    this.configs = [
      'API_CONFIG_TEMPLATE.env',
      '.env',
      'gcp-config.json'
    ];
    
    this.options = {
      maxDepth: options.maxDepth || 5,
      maxFileSize: options.maxFileSize || 100 * 1024 * 1024, // 100MB
      excludePatterns: options.excludePatterns || [
        /node_modules/,
        /\.git/,
        /\.cache/,
        /temp/,
        /tmp/
      ],
      includePatterns: options.includePatterns || [],
      securityScan: options.securityScan !== false,
      generateReports: options.generateReports !== false,
      ...options
    };
    
    this.scanResults = {
      files: [],
      folders: [],
      securityIssues: [],
      patterns: {},
      statistics: {}
    };
    
    this.startTime = Date.now();
  }

  // Main scan method
  async scanDirectory(dirPath, currentDepth = 0) {
    if (currentDepth >= this.options.maxDepth) {
      return { files: [], folders: [], size: 0, count: 0 };
    }

    try {
      const items = fs.readdirSync(dirPath, { withFileTypes: true });
      const result = { files: [], folders: [], size: 0, count: 0 };

      for (const item of items) {
        const fullPath = path.join(dirPath, item.name);
        
        // Skip excluded patterns
        if (this.shouldExclude(fullPath, item.name)) {
          continue;
        }

        try {
          const stats = fs.statSync(fullPath);
          const itemInfo = this.createItemInfo(item, fullPath, stats, currentDepth);
          
          if (item.isDirectory()) {
            result.folders.push(itemInfo);
            if (currentDepth < this.options.maxDepth - 1) {
              const subScan = await this.scanDirectory(fullPath, currentDepth + 1);
              result.size += subScan.size;
              result.count += subScan.count;
              result.files.push(...subScan.files);
              result.folders.push(...subScan.folders);
            }
          } else {
            if (stats.size <= this.options.maxFileSize) {
              result.files.push(itemInfo);
              result.size += stats.size;
              result.count++;
              
              // Security scan for sensitive files
              if (this.options.securityScan) {
                await this.securityScanFile(itemInfo);
              }
              
              // Pattern analysis
              this.analyzePatterns(itemInfo);
            }
          }
        } catch (err) {
          // Log inaccessible files
          this.scanResults.securityIssues.push({
            type: 'access_denied',
            file: fullPath,
            error: err.message,
            timestamp: new Date().toISOString()
          });
        }
      }

      return result;
    } catch (error) {
      return { files: [], folders: [], size: 0, count: 0, error: error.message };
    }
  }

  // Create item information object
  createItemInfo(item, fullPath, stats, depth) {
    const info = {
      name: item.name,
      path: fullPath,
      size: stats.size,
      modified: stats.mtime,
      created: stats.birthtime,
      accessed: stats.atime,
      type: item.isDirectory() ? 'folder' : 'file',
      extension: item.isFile() ? path.extname(item.name) : null,
      depth: depth,
      permissions: stats.mode.toString(8),
      owner: stats.uid,
      group: stats.gid
    };

    // Add file hash for security-critical files
    if (this.isSecurityCritical(info)) {
      info.hash = this.calculateFileHash(fullPath);
    }

    return info;
  }

  // Check if file should be excluded
  shouldExclude(fullPath, name) {
    for (const pattern of this.options.excludePatterns) {
      if (pattern.test(fullPath) || pattern.test(name)) {
        return true;
      }
    }
    
    for (const pattern of this.options.includePatterns) {
      if (pattern.test(fullPath) || pattern.test(name)) {
        return false;
      }
    }
    
    return false;
  }

  // Security scan for files
  async securityScanFile(fileInfo) {
    const issues = [];

    // Check for sensitive file extensions
    const sensitiveExtensions = ['.env', '.key', '.pem', '.p12', '.pfx', '.jks'];
    if (sensitiveExtensions.includes(fileInfo.extension)) {
      issues.push({
        type: 'sensitive_file',
        severity: 'high',
        file: fileInfo.path,
        reason: `Sensitive file extension: ${fileInfo.extension}`,
        action: 'encrypt_sensitive_data'
      });
    }

    // Check for configuration files
    const configFiles = ['.env', 'config.json', 'settings.json', '.config'];
    if (configFiles.includes(fileInfo.name) || configFiles.some(ext => fileInfo.name.endsWith(ext))) {
      issues.push({
        type: 'config_file',
        severity: 'medium',
        file: fileInfo.path,
        reason: 'Configuration file detected',
        action: 'review_permissions'
      });
    }

    // Check file permissions
    const perms = parseInt(fileInfo.permissions, 8);
    if ((perms & 0o077) !== 0) { // Check for world-readable/writable
      issues.push({
        type: 'weak_permissions',
        severity: 'medium',
        file: fileInfo.path,
        reason: `Weak permissions: ${fileInfo.permissions}`,
        action: 'restrict_permissions'
      });
    }

    // Scan file content for sensitive patterns
    if (fileInfo.size < 1024 * 1024) { // Only scan files < 1MB
      await this.scanFileContent(fileInfo);
    }

    this.scanResults.securityIssues.push(...issues);
  }

  // Scan file content for sensitive patterns
  async scanFileContent(fileInfo) {
    try {
      const content = fs.readFileSync(fileInfo.path, 'utf8');
      const sensitivePatterns = [
        { pattern: /password\s*=\s*['"]?([^'"\s]+)/gi, type: 'password' },
        { pattern: /api[_-]?key\s*=\s*['"]?([^'"\s]+)/gi, type: 'api_key' },
        { pattern: /secret\s*=\s*['"]?([^'"\s]+)/gi, type: 'secret' },
        { pattern: /token\s*=\s*['"]?([^'"\s]+)/gi, type: 'token' },
        { pattern: /-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----/g, type: 'private_key' },
        { pattern: /sk-[a-zA-Z0-9]{48}/g, type: 'openai_key' },
        { pattern: /ghp_[a-zA-Z0-9]{36}/g, type: 'github_token' }
      ];

      for (const { pattern, type } of sensitivePatterns) {
        const matches = content.match(pattern);
        if (matches) {
          this.scanResults.securityIssues.push({
            type: 'sensitive_content',
            severity: 'high',
            file: fileInfo.path,
            reason: `Sensitive ${type} pattern detected`,
            matches: matches.length,
            action: 'encrypt_sensitive_data'
          });
        }
      }
    } catch (err) {
      // Can't read file content (binary file, permissions, etc.)
    }
  }

  // Analyze file patterns
  analyzePatterns(fileInfo) {
    const ext = fileInfo.extension || 'no_extension';
    const sizeCategory = this.categorizeSize(fileInfo.size);
    const ageCategory = this.categorizeAge(fileInfo.modified);
    
    // Extension patterns
    if (!this.scanResults.patterns.extensions) {
      this.scanResults.patterns.extensions = {};
    }
    this.scanResults.patterns.extensions[ext] = (this.scanResults.patterns.extensions[ext] || 0) + 1;
    
    // Size patterns
    if (!this.scanResults.patterns.sizes) {
      this.scanResults.patterns.sizes = {};
    }
    this.scanResults.patterns.sizes[sizeCategory] = (this.scanResults.patterns.sizes[sizeCategory] || 0) + 1;
    
    // Age patterns
    if (!this.scanResults.patterns.ages) {
      this.scanResults.patterns.ages = {};
    }
    this.scanResults.patterns.ages[ageCategory] = (this.scanResults.patterns.ages[ageCategory] || 0) + 1;
  }

  // Categorize file size
  categorizeSize(bytes) {
    if (bytes < 1024) return 'tiny';
    if (bytes < 1024 * 1024) return 'small';
    if (bytes < 10 * 1024 * 1024) return 'medium';
    if (bytes < 100 * 1024 * 1024) return 'large';
    return 'huge';
  }

  // Categorize file age
  categorizeAge(modified) {
    const age = Date.now() - modified.getTime();
    const days = age / (1000 * 60 * 60 * 24);
    
    if (days < 1) return 'recent';
    if (days < 7) return 'this_week';
    if (days < 30) return 'this_month';
    if (days < 365) return 'this_year';
    return 'old';
  }

  // Check if file is security critical
  isSecurityCritical(fileInfo) {
    const criticalExtensions = ['.env', '.key', '.pem', '.p12', '.pfx'];
    const criticalNames = ['.env', 'config.json', 'secrets.json'];
    
    return criticalExtensions.includes(fileInfo.extension) || 
           criticalNames.includes(fileInfo.name);
  }

  // Calculate file hash
  calculateFileHash(filePath) {
    try {
      const hash = crypto.createHash('sha256');
      const data = fs.readFileSync(filePath);
      hash.update(data);
      return hash.digest('hex');
    } catch (err) {
      return null;
    }
  }

  // Generate comprehensive report
  generateReport() {
    const endTime = Date.now();
    const scanDuration = endTime - this.startTime;
    
    const report = {
      scan_id: `adaptive-deepscan-report-${endTime}`,
      timestamp: new Date().toISOString(),
      duration_ms: scanDuration,
      duration_human: this.formatDuration(scanDuration),
      config: this.options,
      statistics: this.generateStatistics(),
      security_issues: this.scanResults.securityIssues,
      patterns: this.scanResults.patterns,
      recommendations: this.generateRecommendations()
    };

    return report;
  }

  // Generate statistics
  generateStatistics() {
    const stats = {
      total_files: this.scanResults.files.length,
      total_folders: this.scanResults.folders.length,
      total_size: this.scanResults.files.reduce((sum, file) => sum + file.size, 0),
      security_issues: this.scanResults.securityIssues.length,
      file_types: Object.keys(this.scanResults.patterns.extensions || {}),
      largest_files: this.scanResults.files
        .sort((a, b) => b.size - a.size)
        .slice(0, 10),
      oldest_files: this.scanResults.files
        .sort((a, b) => a.modified - b.modified)
        .slice(0, 10),
      newest_files: this.scanResults.files
        .sort((a, b) => b.modified - a.modified)
        .slice(0, 10)
    };

    stats.size_human = this.formatSize(stats.total_size);
    stats.avg_file_size = stats.total_files > 0 ? stats.total_size / stats.total_files : 0;
    stats.avg_file_size_human = this.formatSize(stats.avg_file_size);

    return stats;
  }

  // Generate recommendations
  generateRecommendations() {
    const recommendations = [];
    const issues = this.scanResults.securityIssues;

    // Security recommendations
    const highSeverityIssues = issues.filter(i => i.severity === 'high');
    if (highSeverityIssues.length > 0) {
      recommendations.push({
        type: 'security',
        priority: 'high',
        title: 'Address High-Severity Security Issues',
        description: `Found ${highSeverityIssues.length} high-severity security issues`,
        actions: ['Encrypt sensitive files', 'Restrict file permissions', 'Review API keys exposure']
      });
    }

    // File organization recommendations
    const largeFiles = this.scanResults.files.filter(f => f.size > 50 * 1024 * 1024);
    if (largeFiles.length > 0) {
      recommendations.push({
        type: 'optimization',
        priority: 'medium',
        title: 'Large Files Detected',
        description: `Found ${largeFiles.length} files larger than 50MB`,
        actions: ['Consider compression', 'Archive old files', 'Move to external storage']
      });
    }

    // Old files recommendations
    const oldFiles = this.scanResults.files.filter(f => 
      Date.now() - f.modified.getTime() > 365 * 24 * 60 * 60 * 1000
    );
    if (oldFiles.length > 0) {
      recommendations.push({
        type: 'maintenance',
        priority: 'low',
        title: 'Old Files Found',
        description: `Found ${oldFiles.length} files older than 1 year`,
        actions: ['Review and archive', 'Delete unnecessary files', 'Backup important data']
      });
    }

    return recommendations;
  }

  // Format size in human readable format
  formatSize(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes;
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    
    return `${size.toFixed(2)} ${units[unitIndex]}`;
  }

  // Format duration
  formatDuration(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  }

  // Save report to file
  async saveReport(report, outputPath = null) {
    const reportPath = outputPath || path.join(process.cwd(), `${report.scan_id}.json`);
    
    try {
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
      return reportPath;
    } catch (err) {
      throw new Error(`Failed to save report: ${err.message}`);
    }
  }

  // Main execution method
  async execute(scanPath, reportPath = null) {
    console.log(`🔍 Starting Adaptive Deep-Scan of: ${scanPath}`);
    
    const result = await this.scanDirectory(scanPath);
    this.scanResults.files = result.files;
    this.scanResults.folders = result.folders;
    
    console.log(`📊 Scan completed: ${result.files.length} files, ${result.folders.length} folders`);
    console.log(`🔒 Security issues found: ${this.scanResults.securityIssues.length}`);
    
    if (this.options.generateReports) {
      const report = this.generateReport();
      const savedPath = await this.saveReport(report, reportPath);
      console.log(`📄 Report saved: ${savedPath}`);
      return { ...report, report_path: savedPath };
    }
    
    return this.generateReport();
  }
}

// CLI interface
if (require.main === module) {
  const args = process.argv.slice(2);
  const scanPath = args[0] || process.cwd();
  const options = {};
  
  // Parse command line options
  for (let i = 1; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--max-depth=')) {
      options.maxDepth = parseInt(arg.split('=')[1]);
    } else if (arg.startsWith('--max-size=')) {
      options.maxFileSize = parseInt(arg.split('=')[1]) * 1024 * 1024;
    } else if (arg === '--no-security') {
      options.securityScan = false;
    } else if (arg === '--no-reports') {
      options.generateReports = false;
    }
  }
  
  const scanner = new AdaptiveDeepScanMaster(options);
  
  scanner.execute(scanPath)
    .then(report => {
      console.log('\n✅ Scan completed successfully!');
      console.log(`📈 Total files: ${report.statistics.total_files}`);
      console.log(`📁 Total folders: ${report.statistics.total_folders}`);
      console.log(`💾 Total size: ${report.statistics.size_human}`);
      console.log(`🔒 Security issues: ${report.security_issues.length}`);
      
      if (report.recommendations.length > 0) {
        console.log('\n💡 Recommendations:');
        report.recommendations.forEach(rec => {
          console.log(`  - ${rec.title} (${rec.priority})`);
        });
      }
    })
    .catch(err => {
      console.error('❌ Scan failed:', err.message);
      process.exit(1);
    });
}

module.exports = AdaptiveDeepScanMaster;
