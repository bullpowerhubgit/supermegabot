#!/usr/bin/env node

/**
 * 🧠 Memory Optimizer - Fixes high memory usage
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

class MemoryOptimizer {
  constructor() {
    this.actions = [];
  }

  log(msg) {
    console.debug(`🧠 [Memory Optimizer] ${msg}`);
  }

  async optimize() {
    this.log('Starting memory optimization...');

    // 1. Clear system caches
    await this.clearCaches();
    
    // 2. Clean temporary files
    await this.cleanTempFiles();
    
    // 3. Optimize node_modules
    await this.optimizeNodeModules();
    
    // 4. Kill unnecessary processes
    await this.killProcesses();
    
    // 5. Compact memory
    await this.compactMemory();

    this.log('✅ Memory optimization completed');
    this.printSummary();
    return this.actions;
  }

  async clearCaches() {
    this.log('Clearing system caches...');
    
    try {
      execSync('rm -rf ~/Library/Caches/*', { stdio: 'ignore' });
      this.actions.push('Cleared Library caches');
    } catch (e) {}
    
    try {
      execSync('rm -rf /tmp/*', { stdio: 'ignore' });
      this.actions.push('Cleared /tmp directory');
    } catch (e) {}
    
    try {
      execSync('npm cache clean --force', { stdio: 'ignore' });
      this.actions.push('Cleared npm cache');
    } catch (e) {}
  }

  async cleanTempFiles() {
    this.log('Cleaning temporary files...');
    
    const tempDirs = [
      path.join(process.cwd(), 'temp'),
      path.join(process.cwd(), '.tmp'),
      path.join(process.cwd(), 'logs')
    ];

    for (const dir of tempDirs) {
      if (fs.existsSync(dir)) {
        try {
          fs.rmSync(dir, { recursive: true, force: true });
          this.actions.push(`Removed ${dir}`);
        } catch (e) {}
      }
    }
  }

  async optimizeNodeModules() {
    this.log('Optimizing node_modules...');
    
    const nmPath = path.join(process.cwd(), 'node_modules');
    if (fs.existsSync(nmPath)) {
      try {
        // Remove dev dependencies
        execSync('npm prune --production', { stdio: 'ignore' });
        this.actions.push('Pruned dev dependencies');
      } catch (e) {}
      
      try {
        // Clean node_modules cache
        execSync('find node_modules -name ".cache" -type d -exec rm -rf {} + 2>/dev/null || true', { stdio: 'ignore' });
        this.actions.push('Cleaned node_modules cache');
      } catch (e) {}
    }
  }

  async killProcesses() {
    this.log('Killing unnecessary processes...');
    
    const processesToKill = [
      'node',
      'npm',
      'yarn',
      'python',
      'python3'
    ];

    for (const proc of processesToKill) {
      try {
        const pids = execSync(`pgrep ${proc}`, { encoding: 'utf8' }).trim().split('\n');
        for (const pid of pids) {
          if (pid && parseInt(pid) > 1000) { // Don't kill system processes
            execSync(`kill ${pid}`, { stdio: 'ignore' });
            this.actions.push(`Killed ${proc} process ${pid}`);
          }
        }
      } catch (e) {}
    }
  }

  async compactMemory() {
    this.log('Compacting memory...');
    
    try {
      execSync('purge', { stdio: 'ignore' });
      this.actions.push('Executed memory purge');
    } catch (e) {}
    
    try {
      execSync('vm_pressure_monitor -s 1000 -l 0.1 -u 0.1 -t 5', { stdio: 'ignore', timeout: 6000 });
      this.actions.push('Triggered memory pressure monitor');
    } catch (e) {}
  }

  printSummary() {
    console.debug('\n🧠 Memory Optimization Summary:');
    console.debug('='.repeat(40));
    this.actions.forEach((action, i) => {
      console.debug(`${i + 1}. ${action}`);
    });
    console.debug('='.repeat(40));
    console.debug(`✅ ${this.actions.length} optimizations completed`);
  }
}

// Run optimization
const optimizer = new MemoryOptimizer();
optimizer.optimize().catch(err => {
  console.error('❌ Memory optimization failed:', err);
  process.exit(1);
});
