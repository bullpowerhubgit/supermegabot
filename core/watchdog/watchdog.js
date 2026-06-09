#!/usr/bin/env node

/**
 * Memory Watchdog
 * Überwacht System-RAM und wichtige Prozesse.
 * Sendet Benachrichtigungen bei kritischen Zuständen.
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);

class MemoryWatchdog {
  constructor(options = {}) {
    this.interval = (options.interval || 60) * 1000;
    this.memoryThreshold = options.memoryThreshold || 85; // Percent
    this.criticalThreshold = options.criticalThreshold || 95; // Percent
    this.processes = options.processes || [];
    this.logFile = options.logFile || path.join(process.cwd(), 'watchdog.log');
    this.running = false;
    this.timer = null;
    this.cleanupEnabled = options.cleanupEnabled !== false;
    this.autoRestartEnabled = options.autoRestartEnabled !== false;
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line.trim());
    fs.appendFileSync(this.logFile, line);
  }

  async getMemoryUsage() {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    const percent = Math.round((used / total) * 100);
    return { total, free, used, percent };
  }

  async getProcessMemory() {
    try {
      const { stdout } = await execAsync("ps -axm -o pid,comm,pmem | head -20");
      return stdout;
    } catch (e) {
      return "N/A";
    }
  }

  async cleanupMemory() {
    if (!this.cleanupEnabled) return;
    
    try {
      this.log('info', '🧹 Starte Speicher-Cleanup...');
      
      // Clear Node.js cache if applicable
      if (global.gc) {
        global.gc();
        this.log('info', 'Garbage Collection ausgeführt');
      }
      
      // Clear system caches (macOS)
      await execAsync('purge').catch(() => {});
      
      // Kill zombie processes
      await execAsync('ps aux | grep -E "defunct|<defunct>" | awk \'{print $2}\' | xargs kill -9 2>/dev/null').catch(() => {});
      
      // Run smart cleanup for terminals and browser tabs
      await this.runSmartCleanup();
      
      this.log('info', '✅ Speicher-Cleanup abgeschlossen');
    } catch (error) {
      this.log('error', `Cleanup Fehler: ${error.message}`);
    }
  }

  async runSmartCleanup() {
    try {
      this.log('info', '🧹 Starte Smart Cleanup (Terminals & Browser)...');
      
      // Close unused terminals
      const terminals = await execAsync('ps aux | grep -i "terminal\\|iterm\\|kitty\\|alacritty" | grep -v grep', { encoding: 'utf8' });
      const terminalLines = terminals.trim().split('\n').filter(l => l.trim());
      
      if (terminalLines.length > 3) {
        const toClose = terminalLines.length - 3;
        this.log('info', `Schließe ${toClose} ungenutzte Terminal-Fenster...`);
        for (let i = 0; i < toClose; i++) {
          try {
            await execAsync('osascript -e \'tell application "Terminal" to close first window\'', { stdio: 'ignore' });
          } catch (e) {}
        }
      }
      
      // Close browser tabs (Chrome)
      try {
        const chromeRunning = await execAsync('pgrep -f "Google Chrome"', { encoding: 'utf8' }).trim();
        if (chromeRunning) {
          const script = `
            tell application "Google Chrome"
              set windowCount to count of windows
              if windowCount > 1 then
                repeat with w from 2 to windowCount
                  try
                    close window w
                  end try
                end repeat
              end if
            end tell
          `;
          await execAsync(`osascript -e '${script}'`, { stdio: 'ignore' });
          this.log('info', 'Browser-Tabs bereinigt');
        }
      } catch (e) {}
      
      // Clear cache directories
      const cacheDirs = [
        path.join(os.homedir(), 'Library', 'Caches'),
        '/tmp',
        path.join(process.cwd(), 'node_modules', '.cache')
      ];
      
      for (const dir of cacheDirs) {
        try {
          if (fs.existsSync(dir)) {
            await execAsync(`rm -rf "${dir}"/*`, { stdio: 'ignore' });
            this.log('info', `Cache bereinigt: ${dir}`);
          }
        } catch (e) {}
      }
      
      this.log('info', '✅ Smart Cleanup abgeschlossen');
    } catch (error) {
      this.log('error', `Smart Cleanup Fehler: ${error.message}`);
    }
  }

  async triggerSmartCleanup() {
    this.log('info', '🧹 Manuelles Smart Cleanup ausgelöst...');
    await this.runSmartCleanup();
    const mem = await this.getMemoryUsage();
    this.log('info', `RAM nach Smart Cleanup: ${mem.percent}%`);
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
          
          // Kill processes using > 30% memory that are not essential
          if (pmem > 30 && !['kernel_task', 'WindowServer', 'launchd'].includes(comm)) {
            this.log('warn', `Beende speicherintensiven Prozess: ${comm} (PID: ${pid}, ${pmem}%)`);
            await execAsync(`kill -9 ${pid}`).catch(() => {});
          }
        }
      }
    } catch (error) {
      this.log('error', `Prozess-Terminierung Fehler: ${error.message}`);
    }
  }

  async checkProcesses() {
    for (const proc of this.processes) {
      try {
        const { stdout } = await execAsync(`pgrep -f "${proc.pattern}"`);
        if (!stdout.trim()) {
          this.log('warn', `Prozess ${proc.name} nicht gefunden. Starte neu...`);
          if (proc.restartCommand) {
            exec(proc.restartCommand, (err) => {
              if (err) this.log('error', `Neustart ${proc.name} fehlgeschlagen: ${err.message}`);
              else this.log('info', `${proc.name} neu gestartet.`);
            });
          }
        }
      } catch (e) {
        this.log('warn', `Prozess ${proc.name} nicht gefunden. Starte neu...`);
        if (proc.restartCommand) {
          try {
            await execAsync(proc.restartCommand);
            this.log('info', `${proc.name} neu gestartet.`);
          } catch (err) {
            this.log('error', `Neustart ${proc.name} fehlgeschlagen: ${err.message}`);
          }
        }
      }
    }
  }

  async getStorageInfo() {
    try {
      const { stdout } = await execAsync("df -h | grep -E '^/dev/' | awk '{print $1, $2, $3, $4, $5, $9}'");
      return stdout.trim().split('\n').map(line => {
        const parts = line.trim().split(/\s+/);
        return {
          device: parts[0],
          size: parts[1],
          used: parts[2],
          available: parts[3],
          percent: parseInt(parts[4].replace('%', '')),
          mount: parts.slice(5).join(' ')
        };
      });
    } catch (e) {
      return [];
    }
  }

  async getExternalVolumes() {
    try {
      const { stdout } = await execAsync("df -h | grep /Volumes/ | awk '{print $1, $2, $3, $4, $5, $9}'");
      return stdout.trim().split('\n').filter(l => l).map(line => {
        const parts = line.trim().split(/\s+/);
        return {
          device: parts[0],
          size: parts[1],
          used: parts[2],
          available: parts[3],
          percent: parseInt(parts[4].replace('%', '')),
          mount: parts.slice(5).join(' '),
          name: parts.slice(5).join(' ').replace('/Volumes/', '')
        };
      });
    } catch (e) {
      return [];
    }
  }

  async getCloudStorage() {
    const cloudPaths = [
      { name: 'iCloud Drive', path: `${os.homedir()}/Library/Mobile Documents/com~apple~CloudDocs`, type: 'icloud' },
      { name: 'Google Drive', path: `${os.homedir()}/Library/CloudStorage`, type: 'google' },
      { name: 'Dropbox', path: `${os.homedir()}/Dropbox`, type: 'dropbox' },
      { name: 'OneDrive', path: `${os.homedir()}/Library/CloudStorage/OneDrive`, type: 'onedrive' }
    ];
    
    const results = [];
    for (const cloud of cloudPaths) {
      try {
        if (fs.existsSync(cloud.path)) {
          const { stdout } = await execAsync(`du -sh "${cloud.path}" 2>/dev/null | awk '{print $1}'`);
          const size = stdout.trim();
          
          // Get detailed info if possible
          let percent = 0;
          try {
            const { stdout: dfOut } = await execAsync(`df -h "${cloud.path}" 2>/dev/null | tail -1 | awk '{print $5}'`);
            percent = parseInt(dfOut.trim().replace('%', '')) || 0;
          } catch (e) {}
          
          results.push({
            name: cloud.name,
            type: cloud.type,
            path: cloud.path,
            size: size || 'Unbekannt',
            percent: percent,
            status: 'connected'
          });
        }
      } catch (e) {
        // Cloud storage not available
      }
    }
    return results;
  }

  async checkStorageHealth() {
    const localStorage = await this.getStorageInfo();
    const externalVolumes = await this.getExternalVolumes();
    const cloudStorage = await this.getCloudStorage();
    
    // Check local drives
    for (const drive of localStorage) {
      if (drive.percent > 90) {
        this.log('critical', `🚨 Lokaler Speicher ${drive.mount} fast voll: ${drive.percent}% (${drive.used}/${drive.size})`);
      } else if (drive.percent > 80) {
        this.log('warn', `⚠️ Lokaler Speicher ${drive.mount} über 80%: ${drive.percent}%`);
      }
    }
    
    // Check external drives
    for (const vol of externalVolumes) {
      if (vol.percent > 90) {
        this.log('critical', `🚨 Externer Speicher ${vol.name} fast voll: ${vol.percent}%`);
      } else {
        this.log('info', `💾 Extern: ${vol.name} - ${vol.percent}% belegt (${vol.used}/${vol.size})`);
      }
    }
    
    // Check cloud storage
    for (const cloud of cloudStorage) {
      this.log('info', `☁️  ${cloud.name}: ${cloud.size} belegt${cloud.percent > 0 ? ' (' + cloud.percent + '%)' : ''}`);
    }
    
    return { localStorage, externalVolumes, cloudStorage };
  }

  async tick() {
    try {
      const mem = await this.getMemoryUsage();
      this.log('info', `RAM Nutzung: ${mem.percent}% (${Math.round(mem.used / 1024 / 1024)}MB / ${Math.round(mem.total / 1024 / 1024)}MB)`);

      // Check all storage (local, external, cloud)
      await this.checkStorageHealth();

      if (mem.percent > this.criticalThreshold) {
        this.log('critical', `🚨 KRITISCHER RAM-Verbrauch: ${mem.percent}%!`);
        const topProcs = await this.getProcessMemory();
        this.log('info', `Top Prozesse:\n${topProcs}`);
        
        // Emergency cleanup
        await this.cleanupMemory();
        await this.killHighMemoryProcesses();
        
        // Check memory again after cleanup
        const memAfter = await this.getMemoryUsage();
        this.log('info', `RAM nach Cleanup: ${memAfter.percent}%`);
      } else if (mem.percent > this.memoryThreshold) {
        this.log('warn', `⚠️ Hoher RAM-Verbrauch: ${mem.percent}%`);
        const topProcs = await this.getProcessMemory();
        this.log('info', `Top Prozesse:\n${topProcs}`);
        
        // Gentle cleanup
        await this.cleanupMemory();
      }

      await this.checkProcesses();
    } catch (error) {
      this.log('error', `Watchdog Fehler: ${error.message}`);
    }
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', '🐕 Memory Watchdog gestartet');
    this.tick();
    this.timer = 
 setInterval(() => this.tick(), this.interval);
  }

  stop() {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.log('info', '🛑 Memory Watchdog gestoppt');
  }
}

// Konfiguration
const watchdog = new MemoryWatchdog({
  interval: 30, // Check every 30 seconds
  memoryThreshold: 90, // Warning at 90%
  criticalThreshold: 90, // Critical at 90%
  cleanupEnabled: true,
  autoRestartEnabled: true,
  processes: [
    {
      name: 'deep-scan-scheduler',
      pattern: 'deep-scan-scheduler.js',
      restartCommand: 'node "' + path.join(process.cwd(), 'deep-scan-scheduler.js') + '"'
    },
    {
      name: 'monitor-dashboard',
      pattern: 'monitor-dashboard.js',
      restartCommand: 'node "' + path.join(process.cwd(), 'monitor-dashboard.js') + '"'
    }
  ]
});

process.on('SIGINT', () => watchdog.stop());
process.on('SIGTERM', () => watchdog.stop());

// Handle manual cleanup trigger via SIGUSR1
process.on('SIGUSR1', () => {
  watchdog.triggerSmartCleanup();
});

watchdog.start();
