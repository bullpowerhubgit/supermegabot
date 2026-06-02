#!/usr/bin/env node
/**
 * SuperMegaBot System Manager v2.0
 * Superintelligenter Memory + Disk Guard
 * Präventiv. Selbstheilend. Lautlos.
 */

const { exec, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

class SystemManager {
  constructor() {
    // Schwellenwerte
    this.memWarn = 75;
    this.memCritical = 90;
    this.diskWarn = 80;
    this.diskCritical = 90;
    this.diskEmergency = 94;

    // Pfade
    this.logFile = path.join(__dirname, '.system.log');
    this.stateFile = path.join(__dirname, '.system-state.json');

    // Interner Zustand
    this.history = { mem: [], disk: [] };
    this.lastAction = 0;
    this.cooldown = 300000; // 5 Minuten zwischen großen Aktionen
    this.isCleaning = false;

    // Lade vorherigen Zustand
    this.loadState();
  }

  loadState() {
    try {
      if (fs.existsSync(this.stateFile)) {
        const saved = JSON.parse(fs.readFileSync(this.stateFile, 'utf8'));
        this.history = saved.history || { mem: [], disk: [] };
        this.lastAction = saved.lastAction || 0;
      }
    } catch (e) { /* stumm */ }
  }

  saveState() {
    try {
      fs.writeFileSync(this.stateFile, JSON.stringify({
        history: this.history,
        lastAction: this.lastAction,
        timestamp: Date.now()
      }));
    } catch (e) { /* stumm */ }
  }

  log(msg, level = 'info') {
    const now = new Date().toISOString().slice(11, 19);
    const line = `[${now}] ${msg}\n`;
    try { fs.appendFileSync(this.logFile, line); } catch (e) {}
    if (level === 'critical' || level === 'error') {
      console.error(line.trim());
    }
  }

  // ── System-Metriken ──

  getMemoryUsage() {
    try {
      const out = execSync("ps -A -o %mem | awk '{s+=$1} END {printf \"%.1f\", s}'", { encoding: 'utf8', timeout: 5000 });
      return parseFloat(out.trim()) || 0;
    } catch (e) { return 0; }
  }

  getDiskUsage() {
    try {
      const out = execSync("df /System/Volumes/Data | tail -1 | awk '{print $5}' | sed 's/%//'", { encoding: 'utf8', timeout: 5000 });
      return parseInt(out.trim()) || 0;
    } catch (e) { return 0; }
  }

  // ── Intelligente Trend-Analyse ──

  getTrend(values) {
    if (values.length < 6) return 0;
    const recent = values.slice(-6);
    const firstAvg = recent.slice(0, 3).reduce((a, b) => a + b, 0) / 3;
    const lastAvg = recent.slice(-3).reduce((a, b) => a + b, 0) / 3;
    return lastAvg - firstAvg; // positiv = steigend
  }

  predictCrossing(values, threshold) {
    const trend = this.getTrend(values);
    if (trend <= 0) return Infinity;
    const current = values[values.length - 1] || 0;
    if (current >= threshold) return 0;
    const diff = threshold - current;
    return Math.round(diff / (trend / 3)); // geschätzte Minuten bis Threshold
  }

  // ── Präventive Maßnahmen ──

  canAct() {
    return Date.now() - this.lastAction > this.cooldown;
  }

  quickMemoryFix() {
    try {
      execSync('killall -9 Windsurf > /dev/null 2>&1 || true');
      execSync('killall -9 Code\ Helper\ \(Renderer\) > /dev/null 2>&1 || true');
      execSync('ps aux | grep "<defunct>" | awk "{print \$2}" | xargs kill -9 > /dev/null 2>&1 || true');
      execSync('purge > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  softMemoryFix() {
    this.quickMemoryFix();
    try {
      // Nur Prozesse >10% RAM die >30min laufen
      const procs = execSync("ps -eo pid,pcpu,pmem,time,comm | awk '$3 > 10 {print $1}'", { encoding: 'utf8' }).trim().split('\n');
      procs.forEach(pid => {
        if (pid && pid !== 'PID') {
          try { execSync(`kill -15 ${pid} > /dev/null 2>&1 || true`); } catch (e) {}
        }
      });
    } catch (e) {}
  }

  emergencyMemoryFix() {
    this.softMemoryFix();
    try {
      // Harte Maßnahmen
      execSync('killall -9 Docker > /dev/null 2>&1 || true');
      execSync('killall -9 Chrome > /dev/null 2>&1 || true');
      execSync('launchctl stop com.docker.docker > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  // ── Disk-Cleanup ──

  cleanCaches() {
    try {
      execSync('find ~/Library/Caches -type f -atime +3 -delete > /dev/null 2>&1 || true');
      execSync('find ~/Library/Caches -type d -empty -delete > /dev/null 2>&1 || true');
      execSync('rm -rf ~/Library/Caches/com.apple.Safari/* > /dev/null 2>&1 || true');
      execSync('rm -rf ~/Library/Caches/com.google.Chrome/* > /dev/null 2>&1 || true');
      execSync('rm -rf ~/Library/Caches/com.github.GitHubClient/* > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  cleanDownloads() {
    try {
      const dls = path.join(process.env.HOME, 'Downloads');
      execSync(`find "${dls}" -name "*.xip" -type f -delete > /dev/null 2>&1 || true`);
      execSync(`find "${dls}" -name "*.dmg" -type f -atime +1 -delete > /dev/null 2>&1 || true`);
      execSync(`find "${dls}" -name "*\([0-9]\)*" -type f -delete > /dev/null 2>&1 || true`);
      execSync(`find "${dls}" -name "*.crdownload" -type f -delete > /dev/null 2>&1 || true`);
      execSync(`rm -rf "${dls}/ARCHIVES" > /dev/null 2>&1 || true`);
      execSync(`rm -rf "${dls}/INSTALLERS" > /dev/null 2>&1 || true`);
    } catch (e) {}
  }

  cleanLogs() {
    try {
      execSync('find ~/Library/Logs -type f -name "*.log" -atime +2 -delete > /dev/null 2>&1 || true');
      execSync('find /var/log -type f -name "*.log" -atime +2 -delete > /dev/null 2>&1 || true');
      execSync('find ~/Library/Application\ Support -name "*.log" -type f -size +50M -delete > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  cleanTrashAndTemp() {
    try {
      execSync('rm -rf ~/.Trash/* > /dev/null 2>&1 || true');
      execSync('find /tmp -type f -atime +1 -delete > /dev/null 2>&1 || true');
      execSync('find ~/Library/Application\ Support -name "node_modules" -type d -atime +7 -exec rm -rf {} + > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  cleanDevCaches() {
    try {
      execSync('find ~/Library/Application\ Support -name "crx_cache" -type d -exec rm -rf {} + > /dev/null 2>&1 || true');
      execSync('find ~/Library/Application\ Support -name "CachedExtensions" -type d -exec rm -rf {} + > /dev/null 2>&1 || true');
      execSync('find ~/Library/Application\ Support -name "*.old" -type f -delete > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  emergencyDiskFix() {
    this.cleanCaches();
    this.cleanDownloads();
    this.cleanLogs();
    this.cleanTrashAndTemp();
    this.cleanDevCaches();
    try {
      execSync('rm -rf ~/Library/Application\ Support/Google/Chrome/Default/Service\ Worker/* > /dev/null 2>&1 || true');
      execSync('rm -rf ~/Library/Application\ Support/Google/Chrome/Default/GPUCache/* > /dev/null 2>&1 || true');
      execSync('rm -rf ~/Library/Application\ Support/Code/CachedData/* > /dev/null 2>&1 || true');
    } catch (e) {}
  }

  // ── Haupt-Prüfschleife ──

  async check() {
    const mem = this.getMemoryUsage();
    const disk = this.getDiskUsage();

    // History füllen (max 60 Einträge = 30 Minuten)
    this.history.mem.push(mem);
    this.history.disk.push(disk);
    if (this.history.mem.length > 60) this.history.mem.shift();
    if (this.history.disk.length > 60) this.history.disk.shift();

    const memTrend = this.getTrend(this.history.mem);
    const diskTrend = this.getTrend(this.history.disk);
    const memPredict = this.predictCrossing(this.history.mem, this.memCritical);
    const diskPredict = this.predictCrossing(this.history.disk, this.diskCritical);

    // ═══════════════════════════════════════════════════
    // DISK: Emergency (>94%)
    // ═══════════════════════════════════════════════════
    if (disk >= this.diskEmergency && this.canAct()) {
      this.log(`DISK EMERGENCY: ${disk}% — sofortige Maßnahmen`, 'critical');
      this.emergencyDiskFix();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // DISK: Critical (>90%)
    if (disk >= this.diskCritical && this.canAct()) {
      this.log(`DISK CRITICAL: ${disk}% — Cleanup gestartet`, 'error');
      this.emergencyDiskFix();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // DISK: Warning (>80%) oder Trend steigend
    if ((disk >= this.diskWarn || (diskTrend > 2 && disk > 70)) && this.canAct()) {
      this.log(`DISK WARN: ${disk}% (Trend: +${memTrend.toFixed(1)}%/min) — präventiver Cleanup`, 'info');
      this.cleanCaches();
      this.cleanLogs();
      this.cleanTrashAndTemp();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // ═══════════════════════════════════════════════════
    // MEMORY: Critical (>90%)
    // ═══════════════════════════════════════════════════
    if (mem >= this.memCritical && this.canAct()) {
      this.log(`MEM CRITICAL: ${mem.toFixed(1)}% — Emergency cleanup`, 'critical');
      this.emergencyMemoryFix();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // MEMORY: Warning (>75%) oder Trend steigend + bald Critical
    if ((mem >= this.memWarn || (memTrend > 3 && memPredict < 5)) && this.canAct()) {
      this.log(`MEM WARN: ${mem.toFixed(1)}% (Trend: +${memTrend.toFixed(1)}%/min, Critical in ~${memPredict}min) — präventiver Fix`, 'info');
      this.softMemoryFix();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // ═══════════════════════════════════════════════════
    // PRÄVENTIV: Beides moderat hoch
    // ═══════════════════════════════════════════════════
    if (disk >= 75 && mem >= 70 && this.canAct()) {
      this.log(`SYSTEM LOAD: MEM ${mem.toFixed(1)}% + DISK ${disk}% — kombinierter Cleanup`, 'info');
      this.quickMemoryFix();
      this.cleanCaches();
      this.lastAction = Date.now();
      this.saveState();
      return;
    }

    // Nur alle 10 Minuten Status loggen wenn alles OK
    if (Date.now() % 600000 < 31000) {
      this.log(`OK — MEM: ${mem.toFixed(1)}% | DISK: ${disk}% | Trend: MEM ${memTrend > 0 ? '+' : ''}${memTrend.toFixed(1)}/min, DISK ${diskTrend > 0 ? '+' : ''}${diskTrend.toFixed(1)}/min`);
    }

    this.saveState();
  }

  start() {
    this.log('🛡️  System Manager v2.0 gestartet — präventiver Schutz aktiv');
    this.check();

    // Alle 30 Sekunden checken
    setInterval(() => this.check(), 30000);
  }
}

// ═══════════════════════════════════════════════════════
// START
// ═══════════════════════════════════════════════════════
const manager = new SystemManager();
manager.start();

process.on('SIGINT', () => {
  manager.log('System Manager gestoppt');
  process.exit(0);
});
process.on('SIGTERM', () => {
  manager.log('System Manager gestoppt');
  process.exit(0);
});
