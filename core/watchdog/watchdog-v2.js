#!/usr/bin/env node

/**
 * Smart Memory Watchdog v2
 * Intelligent system monitoring with predictive alerting,
 * crash recovery, and persistent auto-restart.
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';
import gcpConfig from './lib/gcp-config.js';

const execAsync = promisify(exec);

/**
 * SmartWatchdog - Advanced system monitor
 */
class SmartWatchdog {
  constructor(options = {}) {
    this.interval = (options.interval || 30) * 1000;
    this.memoryThreshold = options.memoryThreshold || 80;
    this.criticalThreshold = options.criticalThreshold || 92;
    this.processes = options.processes || [];
    this.logFile = options.logFile || path.join(process.cwd(), 'watchdog.log');
    this.pidFile = options.pidFile || path.join('/tmp', 'supermegabot-watchdog.pid');
    this.running = false;
    this.timer = null;
    this.cleanupEnabled = options.cleanupEnabled !== false;
    this.autoRestartEnabled = options.autoRestartEnabled !== false;
    this.gcpProjectId = gcpConfig.projectId;
    this.gcpApis = gcpConfig.apiList;
    
    // Smart memory tracking
    this.memoryHistory = [];
    this.maxHistorySize = 20; // Keep last 20 readings for trend analysis
    this.lastCleanupTime = 0;
    this.cleanupCooldown = 120000; // 2 min between cleanups
    
    // Process health tracking
    this.processHealth = new Map();
    this.restartAttempts = new Map();
    this.maxRestartAttempts = 5;
    this.restartResetTime = 300000; // 5 min
    
    // Alert throttling
    this.lastAlertTime = 0;
    this.alertCooldown = 300000; // 5 min between alerts
    
    this.writePid();
  }

  writePid() {
    try {
      fs.writeFileSync(this.pidFile, process.pid.toString());
    } catch (e) {
      console.error('Failed to write PID file:', e.message);
    }
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    
    // Console output for debugging
    if (level === 'critical' || level === 'error') {
      console.error(line.trim());
    } else if (level === 'warn') {
      console.warn(line.trim());
    } else {
      // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line.trim());
    }
    
    // File logging
    try {
      fs.appendFileSync(this.logFile, line);
    } catch (e) {
      // Silent fail for logging errors
    }
  }

  async getMemoryUsage() {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    const percent = Math.round((used / total) * 100);
    return { total, free, used, percent, timestamp: Date.now() };
  }

  /**
   * Analyze memory trend to predict critical states
   */
  analyzeMemoryTrend() {
    if (this.memoryHistory.length < 5) return { trend: 'insufficient_data', prediction: null };
    
    // Get last 5 readings
    const recent = this.memoryHistory.slice(-5);
    const values = recent.map(r => r.percent);
    
    // Calculate trend direction
    const first = values[0];
    const last = values[values.length - 1];
    const diff = last - first;
    
    // Calculate rate of change per minute
    const timeSpan = (recent[recent.length - 1].timestamp - recent[0].timestamp) / 60000; // minutes
    const ratePerMinute = timeSpan > 0 ? diff / timeSpan : 0;
    
    let trend = 'stable';
    if (diff > 5) trend = 'rising';
    else if (diff < -5) trend = 'falling';
    
    // Predict when critical threshold will be reached
    let prediction = null;
    if (ratePerMinute > 0 && last < this.criticalThreshold) {
      const minutesToCritical = (this.criticalThreshold - last) / ratePerMinute;
      if (minutesToCritical > 0 && minutesToCritical < 30) {
        prediction = {
          minutesToCritical: Math.round(minutesToCritical),
          willReachCritical: true
        };
      }
    }
    
    return { trend, ratePerMinute: Math.round(ratePerMinute * 10) / 10, prediction };
  }

  async getProcessMemory() {
    try {
      const { stdout } = await execAsync("ps -axm -o pid,comm,pmem,rss | head -20");
      return stdout;
    } catch (e) {
      return "N/A";
    }
  }

  async cleanupMemory() {
    if (!this.cleanupEnabled) return;
    
    const now = Date.now();
    if (now - this.lastCleanupTime < this.cleanupCooldown) {
      this.log('info', 'Cleanup skipped: cooldown active');
      return;
    }
    
    try {
      this.log('info', 'Starting memory cleanup...');
      this.lastCleanupTime = now;
      
      // Node.js garbage collection
      if (global.gc) {
        global.gc();
        this.log('info', 'GC executed');
      }
      
      // macOS purge
      await execAsync('purge').catch(() => {});
      
      // Clear DNS cache
      await execAsync('dscacheutil -flushcache').catch(() => {});
      
      this.log('info', 'Memory cleanup completed');
    } catch (error) {
      this.log('error', `Cleanup error: ${error.message}`);
    }
  }

  async killHighMemoryProcesses() {
    try {
      const { stdout } = await execAsync("ps -axm -o pid,comm,pmem,rss | sort -k3 -nr | head -10");
      const lines = stdout.trim().split('\n').slice(1);
      
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 4) {
          const pid = parts[0];
          const pmem = parseFloat(parts[2]);
          const comm = parts[1];
          
          if (pmem > 25 && !['kernel_task', 'WindowServer', 'launchd', 'loginwindow', 'Dock'].includes(comm)) {
            this.log('warn', `Killing high-memory process: ${comm} (PID: ${pid}, ${pmem}%)`);
            await execAsync(`kill -9 ${pid}`).catch(() => {});
          }
        }
      }
    } catch (error) {
      this.log('error', `Process termination error: ${error.message}`);
    }
  }

  async checkProcesses() {
    for (const proc of this.processes) {
      try {
        const { stdout } = await execAsync(`pgrep -f "${proc.pattern}"`);
        if (!stdout.trim()) {
          await this.restartProcess(proc);
        } else {
          // Mark as healthy
          this.processHealth.set(proc.name, { status: 'running', lastSeen: Date.now() });
        }
      } catch (e) {
        await this.restartProcess(proc);
      }
    }
  }

  async restartProcess(proc) {
    const now = Date.now();
    const attempts = this.restartAttempts.get(proc.name) || { count: 0, lastAttempt: 0 };
    
    // Reset attempts after cooldown
    if (now - attempts.lastAttempt > this.restartResetTime) {
      attempts.count = 0;
    }
    
    if (attempts.count >= this.maxRestartAttempts) {
      this.log('critical', `Process ${proc.name} failed to restart after ${this.maxRestartAttempts} attempts`);
      return;
    }
    
    attempts.count++;
    attempts.lastAttempt = now;
    this.restartAttempts.set(proc.name, attempts);
    
    this.log('warn', `Process ${proc.name} not found. Restarting (attempt ${attempts.count}/${this.maxRestartAttempts})...`);
    
    if (proc.restartCommand) {
      try {
        // Use spawn for detached restart
        const child = spawn(proc.restartCommand, [], {
          detached: true,
          stdio: 'ignore',
          shell: true,
          cwd: proc.cwd || process.cwd()
        });
        child.unref();
        
        this.log('info', `${proc.name} restarted. PID: ${child.pid}`);
        this.processHealth.set(proc.name, { status: 'restarted', lastSeen: now, pid: child.pid });
      } catch (err) {
        this.log('error', `Restart ${proc.name} failed: ${err.message}`);
      }
    }
  }

  async sendAlert(title, message) {
    const now = Date.now();
    if (now - this.lastAlertTime < this.alertCooldown) {
      return; // Throttle alerts
    }
    this.lastAlertTime = now;
    
    try {
      // macOS notification
      await execAsync(`osascript -e 'display notification "${message}" with title "${title}" sound name "Glass"'`);
    } catch (e) {
      // Silent fail
    }
  }

  async tick() {
    try {
      const mem = await this.getMemoryUsage();
      
      // Add to history
      this.memoryHistory.push(mem);
      if (this.memoryHistory.length > this.maxHistorySize) {
        this.memoryHistory.shift();
      }
      
      // Analyze trend
      const trend = this.analyzeMemoryTrend();
      
      this.log('info', `RAM: ${mem.percent}% (${Math.round(mem.used / 1024 / 1024)}MB / ${Math.round(mem.total / 1024 / 1024)}MB) | Trend: ${trend.trend}${trend.prediction ? ` | Critical in ~${trend.prediction.minutesToCritical}min` : ''}`);

      // Predictive alert
      if (trend.prediction && trend.prediction.willReachCritical) {
        this.log('warn', `Predictive alert: Will reach critical in ~${trend.prediction.minutesToCritical} minutes`);
        await this.sendAlert('Watchdog Warning', `RAM will reach critical in ~${trend.prediction.minutesToCritical}min`);
        await this.cleanupMemory();
      }

      if (mem.percent > this.criticalThreshold) {
        this.log('critical', `CRITICAL RAM: ${mem.percent}%!`);
        const topProcs = await this.getProcessMemory();
        this.log('info', `Top processes:\n${topProcs}`);
        
        await this.cleanupMemory();
        await this.killHighMemoryProcesses();
        await this.sendAlert('Watchdog CRITICAL', `RAM at ${mem.percent}%! Cleanup performed.`);
        
        // Check again after cleanup
        const memAfter = await this.getMemoryUsage();
        this.log('info', `RAM after cleanup: ${memAfter.percent}%`);
        
        if (memAfter.percent > this.criticalThreshold) {
          this.log('critical', 'RAM still critical after cleanup! Consider manual intervention.');
        }
      } else if (mem.percent > this.memoryThreshold) {
        this.log('warn', `High RAM: ${mem.percent}%`);
        await this.cleanupMemory();
      }

      await this.checkProcesses();
      
      // Update PID file
      this.writePid();
      
    } catch (error) {
      this.log('error', `Watchdog tick error: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', 'Smart Watchdog v2 started');
    this.tick();
    this.timer = 
 setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    
    try {
      fs.unlinkSync(this.pidFile);
    } catch (e) {}
    
    this.log('info', 'Smart Watchdog stopped');
  }
}

// Configuration
const watchdog = new SmartWatchdog({
  interval: 30,
  memoryThreshold: 80,
  criticalThreshold: 92,
  cleanupEnabled: true,
  autoRestartEnabled: true,
  processes: [
    {
      name: 'deep-scan-scheduler',
      pattern: 'deep-scan-scheduler.js',
      restartCommand: 'node "' + path.join(process.cwd(), 'deep-scan-scheduler.js') + '"',
      cwd: process.cwd()
    },
    {
      name: 'main-bot',
      pattern: 'main-bot-complete.js',
      restartCommand: 'node "' + path.join('/Users/rudolfsarkany/windsurf-telegram-bot', 'main-bot-complete.js') + '"',
      cwd: '/Users/rudolfsarkany/windsurf-telegram-bot'
    }
  ]
});

process.on('SIGINT', () => watchdog.stop());
process.on('SIGTERM', () => watchdog.stop());
process.on('uncaughtException', (err) => {
  console.error('Uncaught exception:', err.message);
  watchdog.stop();
  process.exit(1);
});

watchdog.start();
