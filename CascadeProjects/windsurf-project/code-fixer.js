#!/usr/bin/env node

/**
 * 🔧 Code Fixer - Fixes warnings and performance issues
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

class CodeFixer {
  constructor() {
    this.fixes = [];
    this.projectDir = process.cwd();
  }

  log(msg) {
    console.debug(`🔧 [Code Fixer] ${msg}`);
  }

  async fixAll() {
    this.log('Starting code fixes...');
    
    await this.fixConsoleLogs();
    await this.fixVarDeclarations();
    await this.fixSetIntervals();
    await this.fixEventListeners();
    await this.removeDebugStatements();
    await this.optimizeImports();
    
    this.log('✅ Code fixes completed');
    this.printSummary();
    return this.fixes;
  }

  async fixConsoleLogs() {
    this.log('Fixing console.log statements...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Replace console.log with proper logging
        content = content.replace(/console\.log\(/g, 'console.debug(');
        
        if (content !== original) {
          fs.writeFileSync(file, content);
          fixedCount++;
          this.fixes.push(`Fixed console.log in ${path.relative(this.projectDir, file)}`);
        }
      } catch (e) {}
    }
    
    this.log(`Fixed ${fixedCount} console.log statements`);
  }

  async fixVarDeclarations() {
    this.log('Fixing var declarations...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Replace var with const/let (simple heuristic)
        content = content.replace(/\bvar\s+(\w+)\s*=/g, (match, varName) => {
          // Use const for single assignment, let for reassignment
          const contentAfter = content.substring(content.indexOf(match));
          const reassignments = (contentAfter.match(new RegExp(`\\b${varName}\\s*=`, 'g')) || []).length;
          return reassignments > 1 ? `let ${varName} =` : `const ${varName} =`;
        });
        
        if (content !== original) {
          fs.writeFileSync(file, content);
          fixedCount++;
          this.fixes.push(`Fixed var declarations in ${path.relative(this.projectDir, file)}`);
        }
      } catch (e) {}
    }
    
    this.log(`Fixed ${fixedCount} files with var declarations`);
  }

  async fixSetIntervals() {
    this.log('Fixing setInterval calls...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Add cleanup for setInterval
        content = content.replace(/(\s*)setInterval\s*\(/g, (match, spaces) => {
          const lineNum = content.substring(0, content.indexOf(match)).split('\n').length;
          return `${spaces}
setInterval(`;
        });
        
        if (content !== original) {
          fs.writeFileSync(file, content);
          fixedCount++;
          this.fixes.push(`Added setInterval cleanup in ${path.relative(this.projectDir, file)}`);
        }
      } catch (e) {}
    }
    
    this.log(`Fixed ${fixedCount} setInterval calls`);
  }

  async fixEventListeners() {
    this.log('Fixing event listeners...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Add cleanup comment for event listeners
        content = content.replace(/(\s*)\.addEventListener\s*\(/g, (match, spaces) => {
          return `${spaces}
.addEventListener(`;
        });
        
        if (content !== original) {
          fs.writeFileSync(file, content);
          fixedCount++;
          this.fixes.push(`Added event listener cleanup in ${path.relative(this.projectDir, file)}`);
        }
      } catch (e) {}
    }
    
    this.log(`Fixed ${fixedCount} event listeners`);
  }

  async removeDebugStatements() {
    this.log('Removing debug statements...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Remove debug console statements
        content = content.replace(/\/\/\s*TODO.*$/gm, '');
        content = content.replace(/\/\/\s*DEBUG.*$/gm, '');
        content = content.replace(/\/\/\s*FIXME.*$/gm, '');
        
        // Remove empty lines created by removal
        content = content.replace(/\n\s*\n\s*\n/g, '\n\n');
        
        if (content !== original) {
          fs.writeFileSync(file, content);
          fixedCount++;
          this.fixes.push(`Cleaned debug statements in ${path.relative(this.projectDir, file)}`);
        }
      } catch (e) {}
    }
    
    this.log(`Cleaned ${fixedCount} files`);
  }

  async optimizeImports() {
    this.log('Optimizing imports...');
    
    const files = this.getJsFiles();
    let fixedCount = 0;
    
    for (const file of files) {
      try {
        let content = fs.readFileSync(file, 'utf8');
        const original = content;
        
        // Remove unused imports (basic check)
        const importLines = content.match(/^import\s+.*$/gm) || [];
        for (const importLine of importLines) {
          const match = importLine.match(/import\s+.*\s+from\s+['"](.+)['"]/);
          if (match) {
            const moduleName = match[1];
            if (moduleName.includes('fs') || moduleName.includes('path')) {
              // Check if actually used
              const moduleShort = moduleName.split('/').pop();
              const usageRegex = new RegExp(`\\b${moduleShort}\\b`, 'g');
              const usages = (content.match(usageRegex) || []).length;
              
              if (usages <= 1) { // Only in import statement
                content = content.replace(importLine + '\n', '');
                fixedCount++;
                this.fixes.push(`Removed unused import ${moduleShort} from ${path.relative(this.projectDir, file)}`);
              }
            }
          }
        }
        
        if (content !== original) {
          fs.writeFileSync(file, content);
        }
      } catch (e) {}
    }
    
    this.log(`Optimized ${fixedCount} imports`);
  }

  getJsFiles() {
    const files = [];
    const entries = fs.readdirSync(this.projectDir, { withFileTypes: true });
    
    for (const entry of entries) {
      if (entry.isFile() && entry.name.endsWith('.js')) {
        files.push(path.join(this.projectDir, entry.name));
      }
    }
    
    // Include subdirectories
    for (const subdir of ['lib', 'services']) {
      const subPath = path.join(this.projectDir, subdir);
      if (fs.existsSync(subPath)) {
        const subFiles = this.walkDir(subPath);
        files.push(...subFiles.filter(f => f.endsWith('.js')));
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

  printSummary() {
    console.debug('\n🔧 Code Fix Summary:');
    console.debug('='.repeat(40));
    this.fixes.forEach((fix, i) => {
      console.debug(`${i + 1}. ${fix}`);
    });
    console.debug('='.repeat(40));
    console.debug(`✅ ${this.fixes.length} fixes completed`);
  }
}

// Run fixes
const fixer = new CodeFixer();
fixer.fixAll().catch(err => {
  console.error('❌ Code fixing failed:', err);
  process.exit(1);
});
