#!/usr/bin/env node

/**
 * Mega Dashboard Server - Professionelles zentrales Dashboard
 * Bündelt: System-Monitoring, Bot-Status, Watchdog, Services
 * Keine externen CDN-Abhängigkeiten - alles inline
 */

import http from 'http';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';
import os from 'os';

const execAsync = promisify(exec);
const PORT = 3200;

// SVG Icons inline (kein FontAwesome CDN)
const ICONS = {
  robot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>',
  memory: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="9" y1="4" x2="9" y2="20"/></svg>',
  cpu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>',
  disk: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="12" rx="10" ry="10"/><path d="M12 2a10 10 0 0 1 10 10"/><circle cx="12" cy="12" r="4"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  terminal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  stop: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
  cloud: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>',
  activity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  zap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
};

class MegaDashboard {
  constructor() {
    this.port = PORT;
    this.history = { memory: [], cpu: [], timestamps: [] };
    this.maxHistory = 60;
    this.server = null;
  }

  log(level, msg) {
    const line = `[${new Date().toISOString()}] [${level.toUpperCase()}] ${msg}`;
    // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(line);
    try { fs.appendFileSync('/tmp/mega-dashboard.log', line + '\n'); } catch {}
  }

  async getSystemStats() {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    return {
      totalGB: (total / 1024 / 1024 / 1024).toFixed(1),
      usedGB: (used / 1024 / 1024 / 1024).toFixed(1),
      freeGB: (free / 1024 / 1024 / 1024).toFixed(1),
      percent: Math.round((used / total) * 100),
      uptime: Math.round(os.uptime()),
      cpus: os.cpus().length
    };
  }

  async getCPUUsage() {
    try {
      const { stdout } = await execAsync("ps -A -o %cpu | awk '{s+=$1} END {print s}'");
      return Math.min(Math.round(parseFloat(stdout.trim()) || 0), 100);
    } catch { return 0; }
  }

  async getDiskUsage() {
    try {
      const { stdout } = await execAsync("df -H / | tail -1 | awk '{print $5}'");
      return parseInt(stdout.replace('%', '').trim()) || 0;
    } catch { return 0; }
  }

  async getBotStatus() {
    const bots = [];
    // Check individual bot processes
    const botFiles = [
      { name: 'Public Bot', pattern: 'public-bot.js' },
      { name: 'Control Bot', pattern: 'control-bot.js' },
      { name: 'MTProto Client', pattern: 'mtproto-client.js' }
    ];
    for (const bot of botFiles) {
      try {
        const { stdout } = await execAsync(`pgrep -f "${bot.pattern}"`);
        bots.push({ name: bot.name, status: 'running', pid: stdout.trim() });
      } catch {
        bots.push({ name: bot.name, status: 'stopped', pid: '-' });
      }
    }
    // Check bot-system orchestrator
    try {
      const { stdout } = await execAsync('launchctl list | grep "com.supermegabot.bot-system"');
      const parts = stdout.trim().split(/\s+/);
      if (parts.length >= 3 && parts[1] === '0') {
        bots.push({ name: 'Bot Orchestrator', status: 'running', pid: parts[0] });
        // Try to read active bots from log
        try {
          const { stdout: logOut } = await execAsync('tail -20 /tmp/bot-system.log');
          const activeMatch = logOut.match(/Health:\s*(\d+)\/(\d+)\s*bots\s*active/);
          if (activeMatch) {
            bots.push({ name: `Internal Bots (${activeMatch[1]}/${activeMatch[2]})`, status: 'running', pid: 'internal' });
          }
        } catch {}
      } else {
        bots.push({ name: 'Bot Orchestrator', status: 'stopped', pid: '-' });
      }
    } catch {
      bots.push({ name: 'Bot Orchestrator', status: 'stopped', pid: '-' });
    }
    return bots;
  }

  async getWatchdogStatus() {
    try {
      const { stdout } = await execAsync('launchctl list | grep "com.supermegabot.watchdog"');
      const lines = stdout.trim().split('\n');
      const results = [];
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 3) {
          results.push({ label: parts[2], pid: parts[0], status: parts[1] });
        }
      }
      return results;
    } catch { return []; }
  }

  async getServices() {
    const services = [];
    const serviceList = [
      'com.supermegabot.watchdog',
      'com.supermegabot.watchdog-monitor',
      'com.supermegabot.mega-dashboard',
      'com.supermegabot.bot-system',
      'com.supermegabot.launcher',
      'com.supermegabot.backup'
    ];
    for (const svc of serviceList) {
      try {
        const { stdout } = await execAsync(`launchctl list | grep "${svc}" | head -1`);
        const parts = stdout.trim().split(/\s+/);
        if (parts.length >= 3) {
          services.push({ name: svc.replace('com.supermegabot.', ''), label: parts[2], pid: parts[0], code: parts[1] });
        }
      } catch {
        services.push({ name: svc.replace('com.supermegabot.', ''), label: svc, pid: '-', code: 'stopped' });
      }
    }
    return services;
  }

  async getTopProcesses() {
    try {
      const { stdout } = await execAsync("ps -axm -o pid,comm,pmem,rss,pcpu | head -11 | tail -10");
      return stdout.trim().split('\n').map(line => {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 5) {
          return { pid: parts[0], name: parts[1].split('/').pop(), mem: parseFloat(parts[2]) || 0, rss: Math.round((parseInt(parts[3])||0)/1024), cpu: parseFloat(parts[4]) || 0 };
        }
        return null;
      }).filter(Boolean);
    } catch { return []; }
  }

  updateHistory(memory, cpu) {
    const now = Date.now();
    this.history.memory.push(memory);
    this.history.cpu.push(cpu);
    this.history.timestamps.push(now);
    if (this.history.memory.length > this.maxHistory) {
      this.history.memory.shift();
      this.history.cpu.shift();
      this.history.timestamps.shift();
    }
  }

  async getData() {
    const mem = await this.getSystemStats();
    const cpu = await this.getCPUUsage();
    const disk = await this.getDiskUsage();
    const bots = await this.getBotStatus();
    const watchdogs = await this.getWatchdogStatus();
    const services = await this.getServices();
    const processes = await this.getTopProcesses();

    this.updateHistory(mem.percent, cpu);

    const alerts = [];
    if (mem.percent > 90) alerts.push({ type: 'critical', text: `RAM kritisch: ${mem.percent}%` });
    else if (mem.percent > 75) alerts.push({ type: 'warning', text: `RAM hoch: ${mem.percent}%` });
    if (cpu > 90) alerts.push({ type: 'critical', text: `CPU kritisch: ${cpu}%` });
    if (disk > 85) alerts.push({ type: 'warning', text: `Disk voll: ${disk}%` });
    const stoppedBots = bots.filter(b => b.status === 'stopped');
    if (stoppedBots.length > 0) alerts.push({ type: 'warning', text: `${stoppedBots.length} Bot(s) offline` });

    return { mem, cpu, disk, bots, watchdogs, services, processes, alerts, history: this.history };
  }

  getDashboardHTML(data) {
    const { mem, cpu, disk, bots, watchdogs, services, processes, alerts } = data;
    const memColor = mem.percent > 90 ? '#ef4444' : mem.percent > 75 ? '#f59e0b' : '#10b981';
    const cpuColor = cpu > 90 ? '#ef4444' : cpu > 75 ? '#f59e0b' : '#10b981';
    const diskColor = disk > 85 ? '#ef4444' : disk > 70 ? '#f59e0b' : '#10b981';

    const formatTime = (sec) => {
      const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
      return d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`;
    };

    return `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mega Dashboard - SuperMegaBot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0e1a;--bg2:#111827;--bg3:#1f2937;--accent:#3b82f6;--accent2:#8b5cf6;--success:#10b981;--warning:#f59e0b;--danger:#ef4444;--text:#f3f4f6;--text2:#9ca3af;--border:rgba(255,255,255,0.08)}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,var(--bg2),var(--bg3));border-bottom:1px solid var(--border);padding:20px 32px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.logo{font-size:24px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:flex;align-items:center;gap:10px}
.logo svg{width:28px;height:28px;stroke:var(--accent);-webkit-text-fill-color:initial}
.status-pill{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;background:rgba(16,185,129,0.15);color:var(--success);display:flex;align-items:center;gap:6px}
.status-pill svg{width:14px;height:14px}
.container{max-width:1400px;margin:0 auto;padding:24px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:24px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:24px;position:relative;overflow:hidden;transition:transform .2s}
.card:hover{transform:translateY(-2px)}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--accent2))}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.card-icon{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;color:#fff}
.card-icon svg{width:22px;height:22px}
.card-value{font-size:32px;font-weight:700;margin-bottom:4px}
.card-label{font-size:13px;color:var(--text2);text-transform:uppercase;letter-spacing:.5px}
.card-bar{height:6px;border-radius:3px;background:var(--bg3);overflow:hidden;margin-top:12px}
.card-bar-fill{height:100%;border-radius:3px;transition:width .5s ease}
.row-2{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:24px}
.row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:24px}
.section-title{font-size:18px;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.section-title svg{width:20px;height:20px;color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;padding:12px 16px;color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border);font-weight:600}
td{padding:12px 16px;border-bottom:1px solid var(--border)}
tr:last-child td{border-bottom:none}
.badge{padding:4px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-success{background:rgba(16,185,129,0.15);color:var(--success)}
.badge-danger{background:rgba(239,68,68,0.15);color:var(--danger)}
.badge-warning{background:rgba(245,158,11,0.15);color:var(--warning)}
.alert-box{padding:14px 18px;border-radius:12px;margin-bottom:12px;display:flex;align-items:center;gap:12px;border-left:3px solid}
.alert-critical{background:rgba(239,68,68,0.08);border-color:var(--danger);color:var(--danger)}
.alert-warning{background:rgba(245,158,11,0.08);border-color:var(--warning);color:var(--warning)}
.alert-box svg{width:20px;height:20px;flex-shrink:0}
.empty-state{text-align:center;padding:40px;color:var(--text2);font-size:14px}
.empty-state svg{width:48px;height:48px;margin-bottom:12px;opacity:.3}
.refresh-bar{position:fixed;bottom:0;left:0;right:0;background:var(--bg2);border-top:1px solid var(--border);padding:12px 32px;display:flex;justify-content:space-between;align-items:center;font-size:13px;color:var(--text2)}
.refresh-bar button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:8px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;font-size:13px}
.refresh-bar button:hover{background:#2563eb}
.refresh-bar button svg{width:14px;height:14px}
.process-name{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,1fr)}.row-2,.row-3{grid-template-columns:1fr}}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
  <div class="logo">${ICONS.robot} Mega Dashboard</div>
  <div class="status-pill">${ICONS.check} System Online</div>
</div>
<div class="container">

<!-- Stat Cards -->
<div class="grid">
  <div class="card">
    <div class="card-header"><div class="card-icon">${ICONS.memory}</div></div>
    <div class="card-value" style="color:${memColor}">${mem.percent}%</div>
    <div class="card-label">RAM Usage</div>
    <div class="card-bar"><div class="card-bar-fill" style="width:${mem.percent}%;background:${memColor}"></div></div>
    <div style="margin-top:8px;font-size:12px;color:var(--text2)">${mem.usedGB} / ${mem.totalGB} GB</div>
  </div>
  <div class="card">
    <div class="card-header"><div class="card-icon">${ICONS.cpu}</div></div>
    <div class="card-value" style="color:${cpuColor}">${cpu}%</div>
    <div class="card-label">CPU Usage</div>
    <div class="card-bar"><div class="card-bar-fill" style="width:${cpu}%;background:${cpuColor}"></div></div>
    <div style="margin-top:8px;font-size:12px;color:var(--text2)">${mem.cpus} Cores</div>
  </div>
  <div class="card">
    <div class="card-header"><div class="card-icon">${ICONS.disk}</div></div>
    <div class="card-value" style="color:${diskColor}">${disk}%</div>
    <div class="card-label">Disk Usage</div>
    <div class="card-bar"><div class="card-bar-fill" style="width:${disk}%;background:${diskColor}"></div></div>
    <div style="margin-top:8px;font-size:12px;color:var(--text2)">Macintosh HD</div>
  </div>
  <div class="card">
    <div class="card-header"><div class="card-icon">${ICONS.clock}</div></div>
    <div class="card-value" style="color:var(--accent)">${formatTime(mem.uptime)}</div>
    <div class="card-label">System Uptime</div>
  </div>
</div>

<!-- Alerts -->
<div class="card" style="margin-bottom:24px">
  <div class="section-title">${ICONS.alert} Active Alerts (${alerts.length})</div>
  ${alerts.length === 0 ? `<div class="empty-state">${ICONS.shield}<br>Keine aktiven Warnungen - System OK</div>` : alerts.map(a => `<div class="alert-box alert-${a.type}">${a.type === 'critical' ? ICONS.alert : ICONS.zap}<div>${a.text}</div></div>`).join('')}
</div>

<!-- Bots & Services -->
<div class="row-2">
  <div class="card">
    <div class="section-title">${ICONS.robot} Bot Status</div>
    <table>
      <thead><tr><th>Bot</th><th>Status</th><th>PID</th></tr></thead>
      <tbody>
        ${bots.map(b => `<tr><td><strong>${b.name}</strong></td><td><span class="badge badge-${b.status === 'running' ? 'success' : 'danger'}">${b.status}</span></td><td>${b.pid}</td></tr>`).join('')}
      </tbody>
    </table>
  </div>
  <div class="card">
    <div class="section-title">${ICONS.shield} Watchdog Services</div>
    <table>
      <thead><tr><th>Service</th><th>Status</th></tr></thead>
      <tbody>
        ${watchdogs.map(w => `<tr><td><strong>${w.label.replace('com.supermegabot.', '').replace('com.', '')}</strong></td><td><span class="badge badge-${w.code === '0' ? 'success' : w.code === '-9' ? 'warning' : 'danger'}">${w.code === '0' ? 'Running' : w.code}</span></td></tr>`).join('')}
        ${watchdogs.length === 0 ? '<tr><td colspan="2" style="text-align:center;color:var(--text2)">Keine Watchdogs gefunden</td></tr>' : ''}
      </tbody>
    </table>
  </div>
</div>

<!-- System Services -->
<div class="card" style="margin-bottom:24px">
  <div class="section-title">${ICONS.activity} System Services</div>
  <table>
    <thead><tr><th>Service</th><th>Label</th><th>PID</th><th>Status</th></tr></thead>
    <tbody>
      ${services.map(s => `<tr><td><strong>${s.name}</strong></td><td>${s.label}</td><td>${s.pid}</td><td><span class="badge badge-${s.code === '0' ? 'success' : s.code === 'stopped' ? 'danger' : 'warning'}">${s.code === '0' ? 'Running' : s.code}</span></td></tr>`).join('')}
    </tbody>
  </table>
</div>

<!-- Top Processes -->
<div class="card">
  <div class="section-title">${ICONS.chart} Top Processes</div>
  <table>
    <thead><tr><th>Process</th><th>PID</th><th>CPU%</th><th>RAM%</th><th>RAM MB</th></tr></thead>
    <tbody>
      ${processes.map(p => `<tr><td class="process-name">${p.name}</td><td>${p.pid}</td><td>${p.cpu}%</td><td>${p.mem}%</td><td>${p.rss}</td></tr>`).join('')}
    </tbody>
  </table>
</div>

</div>
<div class="refresh-bar">
  <span>Auto-Refresh alle 5 Sekunden</span>
  <button onclick="location.reload()">${ICONS.refresh} Jetzt aktualisieren</button>
</div>
<script>
setInterval(()=>location.reload(),5000);
</script>
</body>
</html>`;
  }

  start() {
    this.server = http.createServer(async (req, res) => {
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Cache-Control', 'no-cache');

      if (req.url === '/' || req.url === '/index.html') {
        try {
          const data = await this.getData();
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(this.getDashboardHTML(data));
        } catch (e) {
          res.writeHead(500);
          res.end(`Error: ${e.message}`);
        }
      } else if (req.url === '/api/status') {
        try {
          const data = await this.getData();
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(data));
        } catch (e) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: e.message }));
        }
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    this.server.listen(this.port, () => {
      this.log('info', `Mega Dashboard running on http://localhost:${this.port}`);
    });

    process.on('SIGTERM', () => {
      this.log('info', 'Shutting down...');
      this.server.close();
      process.exit(0);
    });
  }
}

new MegaDashboard().start();
