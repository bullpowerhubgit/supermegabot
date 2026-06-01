/**
 * SuperMegaBot Fixer Bot - Automatische Fehlererkennung & Reparatur
 * Zuständig: Common Errors auto-fix, Code-Quality Checks, Dependency Updates
 */

import fs from 'fs';
import { exec } from 'child_process';
import path from 'path';

class FixerBot {
  constructor() {
    this.name = 'FixerBot';
    this.interval = 60000; // 1 Minute
    this.isRunning = false;
    this.fixesApplied = [];
    this.scanDirectory = process.cwd();
  }

  async start() {
    console.log(`🤖 ${this.name} starting...`);
    this.isRunning = true;
    
    // Haupt-Fix Loop
    this.fixingInterval = setInterval(async () => {
      if (!this.isRunning) return;
      
      await this.scanAndFix();
    }, this.interval);
    
    console.log(`✅ ${this.name} started - Scanning every ${this.interval/1000}s`);
  }

  async scanAndFix() {
    console.log(`🔍 ${this.name}: Scanning for issues...`);
    
    const issues = await this.detectIssues();
    
    if (issues.length === 0) {
      console.log(`✅ ${this.name}: No issues detected`);
      return;
    }
    
    console.log(`⚠️ ${this.name}: Found ${issues.length} issues`);
    
    for (const issue of issues) {
      await this.fixIssue(issue);
    }
  }

  async detectIssues() {
    const issues = [];
    
    // 1. Check for common syntax errors
    const syntaxErrors = await this.checkSyntaxErrors();
    issues.push(...syntaxErrors);
    
    // 2. Check for missing dependencies
    const depErrors = await this.checkDependencies();
    issues.push(...depErrors);
    
    // 3. Check for common security issues
    const securityIssues = await this.checkSecurityIssues();
    issues.push(...securityIssues);
    
    // 4. Check for unused files
    const unusedFiles = await this.checkUnusedFiles();
    issues.push(...unusedFiles);
    
    return issues;
  }

  async checkSyntaxErrors() {
    const issues = [];
    const jsFiles = await this.findFiles('*.js', this.scanDirectory);
    const jsxFiles = await this.findFiles('*.jsx', this.scanDirectory);
    const tsFiles = await this.findFiles('*.ts', this.scanDirectory);
    const tsxFiles = await this.findFiles('*.tsx', this.scanDirectory);
    
    const allFiles = [...jsFiles, ...jsxFiles, ...tsFiles, ...tsxFiles];
    
    for (const file of allFiles) {
      try {
        // Skip node_modules and build directories
        if (file.includes('node_modules') || file.includes('dist') || file.includes('build')) {
          continue;
        }
        
        const content = fs.readFileSync(file, 'utf-8');
        
        // Check for common syntax errors
        if (content.includes('innerHTML') && !content.includes('escapeHtml')) {
          issues.push({
            type: 'security',
            severity: 'high',
            file: file,
            message: 'innerHTML usage without escapeHtml function',
            autoFixable: true
          });
        }
        
        // Check for console.log in production
        if (content.includes('console.log') && !file.includes('test')) {
          issues.push({
            type: 'quality',
            severity: 'low',
            file: file,
            message: 'console.log found in production code',
            autoFixable: true
          });
        }
        
        // Check for hardcoded API keys
        if (content.includes('sk-ant-api03') || content.includes('DEIN_API_KEY')) {
          issues.push({
            type: 'security',
            severity: 'high',
            file: file,
            message: 'Hardcoded API key detected',
            autoFixable: false
          });
        }
        
      } catch (error) {
        // File read error - skip
      }
    }
    
    return issues;
  }

  async checkDependencies() {
    const issues = [];
    
    try {
      const packageJsonPath = path.join(this.scanDirectory, 'package.json');
      if (fs.existsSync(packageJsonPath)) {
        const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
        
        // Check for outdated dependencies
        for (const dep of Object.keys(packageJson.dependencies || {})) {
          try {
            const result = await this.execCommand(`npm outdated ${dep} --json`);
            if (result) {
              issues.push({
                type: 'dependency',
                severity: 'medium',
                file: 'package.json',
                message: `Outdated dependency: ${dep}`,
                autoFixable: true
              });
            }
          } catch (error) {
            // npm outdated returns error if no outdated packages
          }
        }
      }
    } catch (error) {
      console.error('Dependency check failed:', error.message);
    }
    
    return issues;
  }

  async checkSecurityIssues() {
    const issues = [];
    
    // Check for .env files in git
    const gitignorePath = path.join(this.scanDirectory, '.gitignore');
    if (fs.existsSync(gitignorePath)) {
      const gitignore = fs.readFileSync(gitignorePath, 'utf-8');
      if (!gitignore.includes('.env') && !gitignore.includes('*.env')) {
        issues.push({
          type: 'security',
          severity: 'high',
          file: '.gitignore',
          message: '.env files not in .gitignore',
          autoFixable: true
        });
      }
    }
    
    // Check for exposed API keys in config files
    const configFiles = await this.findFiles('*config*.json', this.scanDirectory);
    for (const file of configFiles) {
      try {
        const content = fs.readFileSync(file, 'utf-8');
        if (content.includes('sk-ant-api03') || content.includes('DEIN_API_KEY')) {
          issues.push({
            type: 'security',
            severity: 'high',
            file: file,
            message: 'Exposed API key in config file',
            autoFixable: false
          });
        }
      } catch (error) {
        // File read error - skip
      }
    }
    
    return issues;
  }

  async checkUnusedFiles() {
    const issues = [];
    
    // Check for empty files
    const allFiles = await this.findFiles('*', this.scanDirectory);
    for (const file of allFiles) {
      try {
        if (file.includes('node_modules') || file.includes('dist') || file.includes('build')) {
          continue;
        }
        
        const stats = fs.statSync(file);
        if (stats.isFile() && stats.size === 0) {
          issues.push({
            type: 'quality',
            severity: 'low',
            file: file,
            message: 'Empty file detected',
            autoFixable: true
          });
        }
      } catch (error) {
        // File stat error - skip
      }
    }
    
    return issues;
  }

  async fixIssue(issue) {
    console.log(`🔧 ${this.name}: Fixing ${issue.type} issue in ${issue.file}`);
    
    try {
      switch (issue.type) {
        case 'security':
          await this.fixSecurityIssue(issue);
          break;
        case 'quality':
          await this.fixQualityIssue(issue);
          break;
        case 'dependency':
          await this.fixDependencyIssue(issue);
          break;
        default:
          console.log(`⚠️ ${this.name}: Unknown issue type: ${issue.type}`);
      }
      
      this.fixesApplied.push({
        ...issue,
        fixedAt: new Date().toISOString()
      });
      
      console.log(`✅ ${this.name}: Fixed ${issue.message}`);
    } catch (error) {
      console.error(`❌ ${this.name}: Failed to fix ${issue.message}:`, error.message);
    }
  }

  async fixSecurityIssue(issue) {
    if (issue.message.includes('.env')) {
      // Add .env to .gitignore
      const gitignorePath = path.join(this.scanDirectory, '.gitignore');
      let gitignore = '';
      if (fs.existsSync(gitignorePath)) {
        gitignore = fs.readFileSync(gitignorePath, 'utf-8');
      }
      
      if (!gitignore.includes('.env')) {
        gitignore += '\n# Environment variables\n.env\n.env.local\n.env.*.local\n';
        fs.writeFileSync(gitignorePath, gitignore);
      }
    }
    
    if (issue.message.includes('innerHTML')) {
      // Add escapeHtml function if missing
      const content = fs.readFileSync(issue.file, 'utf-8');
      if (!content.includes('escapeHtml')) {
        const escapeHtmlFunction = `
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}
`;
        const newContent = escapeHtmlFunction + content;
        fs.writeFileSync(issue.file, newContent);
      }
    }
  }

  async fixQualityIssue(issue) {
    if (issue.message.includes('console.log')) {
      // Comment out console.log statements
      const content = fs.readFileSync(issue.file, 'utf-8');
      const newContent = content.replace(/console\.log\(/g, '// console.log(');
      fs.writeFileSync(issue.file, newContent);
    }
    
    if (issue.message.includes('Empty file')) {
      // Delete empty files
      fs.unlinkSync(issue.file);
    }
  }

  async fixDependencyIssue(issue) {
    try {
      const depName = issue.message.split(': ')[1];
      await this.execCommand(`npm update ${depName}`);
    } catch (error) {
      console.error(`Failed to update dependency:`, error.message);
    }
  }

  async findFiles(pattern, directory) {
    return new Promise((resolve) => {
      exec(`find ${directory} -name "${pattern}" -type f`, (error, stdout) => {
        if (error) {
          resolve([]);
          return;
        }
        const files = stdout.trim().split('\n').filter(f => f);
        resolve(files);
      });
    });
  }

  async execCommand(command) {
    return new Promise((resolve, reject) => {
      exec(command, (error, stdout, stderr) => {
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
    clearInterval(this.fixingInterval);
    console.log(`✅ ${this.name} stopped`);
  }

  getStatus() {
    return {
      name: this.name,
      isRunning: this.isRunning,
      interval: this.interval,
      fixesApplied: this.fixesApplied.length,
      scanDirectory: this.scanDirectory
    };
  }

  getFixesReport() {
    return {
      totalFixes: this.fixesApplied.length,
      fixesByType: this.groupFixesByType(),
      recentFixes: this.fixesApplied.slice(-10)
    };
  }

  groupFixesByType() {
    const grouped = {};
    for (const fix of this.fixesApplied) {
      if (!grouped[fix.type]) {
        grouped[fix.type] = 0;
      }
      grouped[fix.type]++;
    }
    return grouped;
  }
}

// Auto-start wenn direkt ausgeführt
if (import.meta.url === `file://${process.argv[1]}`) {
  const bot = new FixerBot();
  bot.start();
  
  // Graceful shutdown
  process.on('SIGINT', async () => {
    await bot.stop();
    process.exit(0);
  });
}

export default FixerBot;
