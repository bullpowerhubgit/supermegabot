#!/usr/bin/env node
/**
 * Adaptive Deep-Scan System
 * Comprehensive system for adaptive scanning with configuration management and reporting
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const AdaptiveDeepScanMaster = require('./adaptive-deepscan-master');

class AdaptiveDeepScanSystem {
  constructor(options = {}) {
    this.options = {
      configPath: options.configPath || path.join(__dirname, 'deepscan-config.json'),
      reportsPath: options.reportsPath || path.join(__dirname, 'reports'),
      maxReports: options.maxReports || 100,
      autoCleanup: options.autoCleanup !== false,
      ...options
    };
    
    this.configs = [
      'gcp-config.json',
      'API_CONFIG_TEMPLATE.env',
      '.env'
    ];
    
    this.reportTemplates = {
      'API_CONFIG_TEMPLATE.env': `# Facebook Marketing API
FACEBOOK_APP_ID=your_app_id
FACEBOOK_APP_SECRET=your_app_secret

# Google Cloud Platform
GOOGLE_PROJECT_ID=your_project_id
GOOGLE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----
your_private_key_here
-----END PRIVATE KEY-----

# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Database Connections
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
REDIS_URL=redis://localhost:6379

# API Keys
STRIPE_SECRET_KEY=sk_test_your_stripe_key
TWILIO_AUTH_TOKEN=your_twilio_token
SENDGRID_API_KEY=your_sendgrid_key`,
      
      '.env': `# Environment Configuration
NODE_ENV=production
PORT=3000

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=rudibot
DB_USER=rudibot_user
DB_PASSWORD=secure_password_here

# Security
JWT_SECRET=your_jwt_secret_here
ENCRYPTION_KEY=your_encryption_key_here
SESSION_SECRET=your_session_secret_here

# External APIs
OPENAI_API_KEY=sk-your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GITHUB_TOKEN=ghp_your_github_token

# Cloud Services
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json`,
      
      'gcp-config.json': `{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nYour private key here\\n-----END PRIVATE KEY-----\\n",
  "client_email": "service-account@your-project.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/service-account%40your-project.iam.gserviceaccount.com"
}`
    };
    
    this.ensureDirectories();
    this.loadConfiguration();
  }

  // Ensure required directories exist
  ensureDirectories() {
    const dirs = [this.options.reportsPath];
    dirs.forEach(dir => {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    });
  }

  // Load configuration
  loadConfiguration() {
    try {
      if (fs.existsSync(this.options.configPath)) {
        const configData = fs.readFileSync(this.options.configPath, 'utf8');
        this.config = JSON.parse(configData);
      } else {
        this.config = this.getDefaultConfiguration();
        this.saveConfiguration();
      }
    } catch (err) {
      console.warn('Failed to load configuration, using defaults:', err.message);
      this.config = this.getDefaultConfiguration();
    }
  }

  // Get default configuration
  getDefaultConfiguration() {
    return {
      version: '1.0.0',
      created: new Date().toISOString(),
      scanSettings: {
        maxDepth: 5,
        maxFileSize: 100 * 1024 * 1024, // 100MB
        excludePatterns: [
          'node_modules',
          '.git',
          '.cache',
          'temp',
          'tmp',
          '.DS_Store',
          'Thumbs.db'
        ],
        securityScan: true,
        generateReports: true,
        autoEncrypt: false
      },
      securitySettings: {
        sensitiveExtensions: ['.env', '.key', '.pem', '.p12', '.pfx', '.jks'],
        sensitivePatterns: [
          'password',
          'api[_-]?key',
          'secret',
          'token',
          'private[_-]?key'
        ],
        encryptionEnabled: false,
        backupSensitiveFiles: true
      },
      reporting: {
        maxReports: 100,
        reportFormat: 'json',
        includeStatistics: true,
        includeRecommendations: true,
        autoCleanup: true
      },
      notifications: {
        enabled: false,
        webhook: null,
        email: null
      }
    };
  }

  // Save configuration
  saveConfiguration() {
    try {
      fs.writeFileSync(this.options.configPath, JSON.stringify(this.config, null, 2));
    } catch (err) {
      console.error('Failed to save configuration:', err.message);
    }
  }

  // Execute adaptive scan
  async executeScan(targetPath, customOptions = {}) {
    const scanOptions = {
      ...this.config.scanSettings,
      ...customOptions
    };
    
    const scanner = new AdaptiveDeepScanMaster(scanOptions);
    const reportPath = path.join(this.options.reportsPath, `adaptive-deepscan-report-${Date.now()}.json`);
    
    console.log(`🚀 Starting Adaptive Deep-Scan System...`);
    console.log(`📁 Target: ${targetPath}`);
    console.log(`⚙️ Max Depth: ${scanOptions.maxDepth}`);
    console.log(`🔒 Security Scan: ${scanOptions.securityScan ? 'Enabled' : 'Disabled'}`);
    
    const report = await scanner.execute(targetPath, reportPath);
    
    // Post-processing
    await this.postProcessReport(report);
    
    // Cleanup old reports
    if (this.config.reporting.autoCleanup) {
      await this.cleanupOldReports();
    }
    
    return report;
  }

  // Post-process report
  async postProcessReport(report) {
    // Add system metadata
    report.system_info = {
      platform: process.platform,
      arch: process.arch,
      node_version: process.version,
      scanner_version: this.config.version,
      timestamp: new Date().toISOString()
    };
    
    // Add configuration analysis
    report.configuration_analysis = this.analyzeConfigurations(report);
    
    // Add security score
    report.security_score = this.calculateSecurityScore(report);
    
    // Save updated report
    const reportPath = path.join(this.options.reportsPath, `${report.scan_id}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  }

  // Analyze configurations found during scan
  analyzeConfigurations(report) {
    const analysis = {
      found_configs: [],
      missing_configs: [],
      security_risks: [],
      recommendations: []
    };
    
    // Check for configuration files
    for (const configName of this.configs) {
      const foundFiles = report.statistics?.largest_files?.filter(f => 
        f.name === configName || f.path.includes(configName)
      ) || [];
      
      if (foundFiles.length > 0) {
        analysis.found_configs.push({
          name: configName,
          files: foundFiles,
          security_issues: report.security_issues.filter(issue => 
            issue.file.includes(configName)
          )
        });
      } else {
        analysis.missing_configs.push(configName);
      }
    }
    
    // Analyze security risks in configurations
    analysis.found_configs.forEach(config => {
      if (config.security_issues.length > 0) {
        analysis.security_risks.push({
          config: config.name,
          risks: config.security_issues,
          severity: config.security_issues.some(i => i.severity === 'high') ? 'high' : 'medium'
        });
      }
    });
    
    // Generate recommendations
    if (analysis.security_risks.length > 0) {
      analysis.recommendations.push({
        type: 'security',
        priority: 'high',
        message: 'Security risks detected in configuration files',
        actions: ['Encrypt sensitive data', 'Restrict file permissions', 'Use environment variables']
      });
    }
    
    return analysis;
  }

  // Calculate security score
  calculateSecurityScore(report) {
    const issues = report.security_issues || [];
    const totalFiles = report.statistics?.total_files || 1;
    
    let score = 100; // Start with perfect score
    
    // Deduct points for security issues
    issues.forEach(issue => {
      switch (issue.severity) {
        case 'high':
          score -= 10;
          break;
        case 'medium':
          score -= 5;
          break;
        case 'low':
          score -= 2;
          break;
      }
    });
    
    // Bonus points for good practices
    const sensitiveFiles = issues.filter(i => i.type === 'sensitive_file');
    if (sensitiveFiles.length === 0) {
      score += 5;
    }
    
    // Ensure score is within bounds
    score = Math.max(0, Math.min(100, score));
    
    return {
      score,
      grade: this.getSecurityGrade(score),
      issues_count: issues.length,
      files_scanned: totalFiles,
      risk_level: this.getRiskLevel(score)
    };
  }

  // Get security grade
  getSecurityGrade(score) {
    if (score >= 90) return 'A';
    if (score >= 80) return 'B';
    if (score >= 70) return 'C';
    if (score >= 60) return 'D';
    return 'F';
  }

  // Get risk level
  getRiskLevel(score) {
    if (score >= 80) return 'low';
    if (score >= 60) return 'medium';
    return 'high';
  }

  // Cleanup old reports
  async cleanupOldReports() {
    try {
      const files = fs.readdirSync(this.options.reportsPath);
      const reportFiles = files.filter(f => f.startsWith('adaptive-deepscan-report-') && f.endsWith('.json'));
      
      if (reportFiles.length > this.config.reporting.maxReports) {
        // Sort by creation time (newest first)
        const filesWithStats = reportFiles.map(file => {
          const filePath = path.join(this.options.reportsPath, file);
          const stats = fs.statSync(filePath);
          return { file, path: filePath, mtime: stats.mtime };
        }).sort((a, b) => b.mtime - a.mtime);
        
        // Delete oldest files
        const filesToDelete = filesWithStats.slice(this.config.reporting.maxReports);
        filesToDelete.forEach(({ file, path }) => {
          fs.unlinkSync(path);
          console.log(`🗑️ Cleaned up old report: ${file}`);
        });
      }
    } catch (err) {
      console.error('Failed to cleanup old reports:', err.message);
    }
  }

  // Generate configuration templates
  generateConfigTemplate(configName) {
    return this.reportTemplates[configName] || `# Configuration template for ${configName}\n# Add your configuration here`;
  }

  // Create secure configuration
  createSecureConfig(configName, values = {}) {
    const template = this.generateConfigTemplate(configName);
    let config = template;
    
    // Replace placeholder values
    Object.entries(values).forEach(([key, value]) => {
      const placeholder = new RegExp(`your_${key}_here`, 'g');
      config = config.replace(placeholder, value);
    });
    
    // Encrypt if enabled
    if (this.config.securitySettings.encryptionEnabled) {
      config = this.encryptConfig(config);
    }
    
    return config;
  }

  // Encrypt configuration
  encryptConfig(config) {
    const algorithm = 'aes-256-gcm';
    const key = crypto.scryptSync(this.config.securitySettings.encryptionKey || 'default-key', 'salt', 32);
    const iv = crypto.randomBytes(16);
    
    const cipher = crypto.createCipher(algorithm, key, iv);
    let encrypted = cipher.update(config, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    const authTag = cipher.getAuthTag();
    
    return {
      encrypted: true,
      algorithm,
      iv: iv.toString('hex'),
      authTag: authTag.toString('hex'),
      data: encrypted
    };
  }

  // Decrypt configuration
  decryptConfig(encryptedConfig) {
    if (!encryptedConfig.encrypted) {
      return encryptedConfig;
    }
    
    const algorithm = encryptedConfig.algorithm;
    const key = crypto.scryptSync(this.config.securitySettings.encryptionKey || 'default-key', 'salt', 32);
    const iv = Buffer.from(encryptedConfig.iv, 'hex');
    const authTag = Buffer.from(encryptedConfig.authTag, 'hex');
    
    const decipher = crypto.createDecipher(algorithm, key, iv);
    decipher.setAuthTag(authTag);
    
    let decrypted = decipher.update(encryptedConfig.data, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  }

  // Get scan history
  getScanHistory(limit = 10) {
    try {
      const files = fs.readdirSync(this.options.reportsPath);
      const reportFiles = files.filter(f => f.startsWith('adaptive-deepscan-report-') && f.endsWith('.json'));
      
      const reports = reportFiles.map(file => {
        const filePath = path.join(this.options.reportsPath, file);
        const stats = fs.statSync(filePath);
        return {
          file,
          path: filePath,
          mtime: stats.mtime,
          size: stats.size
        };
      }).sort((a, b) => b.mtime - a.mtime).slice(0, limit);
      
      return reports;
    } catch (err) {
      console.error('Failed to get scan history:', err.message);
      return [];
    }
  }

  // Get system status
  getSystemStatus() {
    const history = this.getScanHistory(5);
    const lastScan = history[0];
    
    return {
      version: this.config.version,
      status: 'active',
      last_scan: lastScan ? {
        timestamp: lastScan.mtime.toISOString(),
        file: lastScan.file,
        size: lastScan.size
      } : null,
      total_scans: history.length,
      configuration: {
        security_scan_enabled: this.config.scanSettings.securityScan,
        auto_cleanup: this.config.reporting.autoCleanup,
        max_reports: this.config.reporting.maxReports
      },
      storage: {
        reports_path: this.options.reportsPath,
        config_path: this.options.configPath
      }
    };
  }
}

// CLI interface
if (require.main === module) {
  const args = process.argv.slice(2);
  const command = args[0] || 'scan';
  const targetPath = args[1] || process.cwd();
  
  const system = new AdaptiveDeepScanSystem();
  
  switch (command) {
    case 'scan':
      system.executeScan(targetPath)
        .then(report => {
          console.log('\n✅ Adaptive Deep-Scan completed!');
          console.log(`📊 Security Score: ${report.security_score.score}/100 (${report.security_score.grade})`);
          console.log(`📁 Reports saved to: ${system.options.reportsPath}`);
        })
        .catch(err => {
          console.error('❌ Scan failed:', err.message);
          process.exit(1);
        });
      break;
      
    case 'status':
      const status = system.getSystemStatus();
      console.log('📊 Adaptive Deep-Scan System Status:');
      console.log(JSON.stringify(status, null, 2));
      break;
      
    case 'history':
      const history = system.getScanHistory();
      console.log('📜 Recent Scans:');
      history.forEach((scan, i) => {
        console.log(`${i + 1}. ${scan.file} (${scan.mtime.toISOString()})`);
      });
      break;
      
    case 'config':
      const configName = args[1];
      if (configName) {
        const template = system.generateConfigTemplate(configName);
        console.log(`📝 Configuration template for ${configName}:`);
        console.log(template);
      } else {
        console.log('Available config templates:', system.configs);
      }
      break;
      
    default:
      console.log('Usage:');
      console.log('  node adaptive-deepscan-system.js scan [path]');
      console.log('  node adaptive-deepscan-system.js status');
      console.log('  node adaptive-deepscan-system.js history');
      console.log('  node adaptive-deepscan-system.js config [name]');
  }
}

module.exports = AdaptiveDeepScanSystem;
