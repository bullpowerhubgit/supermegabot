#!/usr/bin/env node

/**
 * Continuous System Monitor
 * Monitors system resources and automatically fixes issues
 */

const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

const fs = require('fs');
const path = require('path');

const CONFIG = {
  checkInterval: 10000, // 10 seconds
  loadThreshold: 50, // Alert if load average > 50
  criticalLoad: 80, // Critical if load average > 80
  cpuThreshold: 90, // Alert if CPU usage > 90%
  memoryThreshold: 90, // Alert if memory > 90%
  diskThreshold: 85, // Alert if disk usage > 85%
  criticalDisk: 95, // Critical if disk usage > 95%
  logFile: './system-monitor.log',
  maxLogSize: 5 * 1024 * 1024, // 5 MB max log size
  autoCleanup: true
};

const rotateLogIfNeeded = () => {
  try {
    if (fs.existsSync(CONFIG.logFile)) {
      const stats = fs.statSync(CONFIG.logFile);
      if (stats.size > CONFIG.maxLogSize) {
        const backup = `${CONFIG.logFile}.old`;
        if (fs.existsSync(backup)) fs.unlinkSync(backup);
        fs.renameSync(CONFIG.logFile, backup);
      }
    }
  } catch (e) {}
};

const log = (message) => {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] ${message}\n`;
  console.log(line.trim());
  try {
    rotateLogIfNeeded();
    fs.appendFileSync(CONFIG.logFile, line);
  } catch (e) {}
};

const getLoadAverage = async () => {
  try {
    const { stdout } = await execAsync('uptime');
    const match = stdout.match(/load averages?: ([\d.]+)/);
    return match ? parseFloat(match[1]) : 0;
  } catch (e) {
    return 0;
  }
};

const getCpuUsage = async () => {
  try {
    const { stdout } = await execAsync('top -l 1 | grep "CPU usage"');
    const match = stdout.match(/(\d+\.?\d*)% idle/);
    return match ? 100 - parseFloat(match[1]) : 0;
  } catch (e) {
    return 0;
  }
};

const getMemoryUsage = async () => {
  try {
    const { stdout } = await execAsync('vm_stat');
    const lines = stdout.split('\n');
    let free = 0, active = 0, inactive = 0, wired = 0;
    
    for (const line of lines) {
      if (line.includes('Pages free:')) free = parseInt(line.split(':')[1].trim()) * 4096;
      if (line.includes('Pages active:')) active = parseInt(line.split(':')[1].trim()) * 4096;
      if (line.includes('Pages inactive:')) inactive = parseInt(line.split(':')[1].trim()) * 4096;
      if (line.includes('Pages wired down:')) wired = parseInt(line.split(':')[1].trim()) * 4096;
    }
    
    const total = free + active + inactive + wired;
    const used = active + inactive + wired;
    return total > 0 ? (used / total) * 100 : 0;
  } catch (e) {
    return 0;
  }
};

const getDiskUsage = async () => {
  try {
    const { stdout } = await execAsync('df -h / | tail -1 | awk \'{print $5}\' | tr -d \'%\'');
    return parseInt(stdout.trim()) || 0;
  } catch (e) {
    return 0;
  }
};

const cleanupCaches = async () => {
  try {
    const caches = [
      '~/Library/Caches/com.apple.textunderstandingd',
      '~/Library/Caches/SiriTTS',
      '~/Library/Caches/Comet',
      '~/Library/Caches/com.apple.helpd',
      '~/Library/Caches/com.apple.parsecd'
    ];
    
    let totalCleaned = 0;
    for (const cache of caches) {
      try {
        const expanded = cache.replace('~', process.env.HOME);
        if (fs.existsSync(expanded)) {
          const { stdout } = await execAsync(`du -sk "${expanded}" 2>/dev/null | awk '{print $1}'`);
          const size = parseInt(stdout.trim()) || 0;
          await execAsync(`rm -rf "${expanded}"/* 2>/dev/null`).catch(() => {});
          totalCleaned += size;
        }
      } catch (e) {}
    }
    
    if (totalCleaned > 0) {
      log(`Cleaned ${(totalCleaned / 1024).toFixed(1)} MB of caches`);
    }
    return totalCleaned;
  } catch (e) {
    return 0;
  }
};

const cleanupLogs = async () => {
  try {
    const logDirs = [
      '~/Library/Logs',
      '/var/log'
    ];
    
    let totalCleaned = 0;
    for (const logDir of logDirs) {
      try {
        const expanded = logDir.replace('~', process.env.HOME);
        if (fs.existsSync(expanded)) {
          const { stdout } = await execAsync(`find "${expanded}" -name "*.log*" -type f -mtime +7 -exec du -sk {} + 2>/dev/null | awk '{sum+=$1} END {print sum}'`);
          const size = parseInt(stdout.trim()) || 0;
          await execAsync(`find "${expanded}" -name "*.log*" -type f -mtime +7 -delete 2>/dev/null`).catch(() => {});
          totalCleaned += size;
        }
      } catch (e) {}
    }
    
    if (totalCleaned > 0) {
      log(`Cleaned ${(totalCleaned / 1024).toFixed(1)} MB of old logs`);
    }
    return totalCleaned;
  } catch (e) {
    return 0;
  }
};

const killFindProcesses = async () => {
  try {
    await execAsync('pkill -f "find /Users/rudolfsarkany -type f -size"');
    log('Killed find processes');
  } catch (e) {
    // No processes to kill
  }
};

const killHighCpuProcesses = async () => {
  try {
    const { stdout } = await execAsync("ps aux | awk '{print $3, $2, $11}' | sort -nr | head -5");
    const lines = stdout.trim().split('\n').slice(1);
    
    for (const line of lines) {
      const [cpu, pid, cmd] = line.trim().split(/\s+/);
      if (parseFloat(cpu) > 50 && !cmd.includes('kernel_task') && !cmd.includes('WindowServer')) {
        await execAsync(`kill -9 ${pid}`).catch(() => {});
        log(`Killed high CPU process: ${cmd} (PID: ${pid}, CPU: ${cpu}%)`);
      }
    }
  } catch (e) {
    // Ignore errors
  }
};

const sendAlert = async (message) => {
  try {
    await execAsync(`osascript -e 'display notification "${message}" with title "System Monitor" sound name "Basso"'`);
  } catch (e) {
    // Silent fail
  }
};

const monitor = async () => {
  const load = await getLoadAverage();
  const cpu = await getCpuUsage();
  const memory = await getMemoryUsage();
  
  log(`Load: ${load.toFixed(2)} | CPU: ${cpu.toFixed(1)}% | Memory: ${memory.toFixed(1)}%`);
  
  if (load > CONFIG.criticalLoad) {
    log(`CRITICAL: Load average ${load.toFixed(2)}!`);
    await killFindProcesses();
    await killHighCpuProcesses();
    await sendAlert(`Critical load: ${load.toFixed(2)} - Auto-fix applied`);
  } else if (load > CONFIG.loadThreshold) {
    log(`WARNING: Load average ${load.toFixed(2)} high`);
    await killFindProcesses();
  }
  
  if (cpu > CONFIG.cpuThreshold) {
    log(`WARNING: CPU usage ${cpu.toFixed(1)}% high`);
    await killHighCpuProcesses();
  }
  
  if (memory > CONFIG.memoryThreshold) {
    if (memory > 95) log(`WARNING: Memory usage ${memory.toFixed(1)}% high`);
    await execAsync('purge').catch(() => {});
  }
  
  const disk = await getDiskUsage();
  if (disk > CONFIG.criticalDisk) {
    log(`CRITICAL: Disk usage ${disk}%! Running emergency cleanup...`);
    await cleanupCaches();
    await cleanupLogs();
    await sendAlert(`Critical disk usage: ${disk}% - Auto-cleanup applied`);
  } else if (disk > CONFIG.diskThreshold) {
    log(`WARNING: Disk usage ${disk}% high`);
    if (CONFIG.autoCleanup) {
      await cleanupCaches();
      await cleanupLogs();
    }
  }
};

log('System Monitor started');

const interval = setInterval(monitor, CONFIG.checkInterval);

process.on('SIGINT', () => {
  clearInterval(interval);
  log('System Monitor stopped');
  process.exit(0);
});

process.on('SIGTERM', () => {
  clearInterval(interval);
  log('System Monitor stopped');
  process.exit(0);
});
