#!/usr/bin/env node
/**
 * RudiBot Agenten-Hub
 * Zentrale Nervenzentrale - verbindet ALLE Agenten und Tools
 */

import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import http from 'http';
import fs from 'fs';
import path from 'path';
import os from 'os';
import ExterneAgenten from './externe-agenten.js';

const execAsync = promisify(exec);

class AgentenHub {
  constructor() {
    this.agents = new Map();
    this.events = [];
    this.port = 9998;
    this.startTime = Date.now();
    this.logFile = path.join(process.cwd(), 'agenten-hub.log');
    
    // Externe Agenten initialisieren
    this.externeAgenten = new ExterneAgenten();
    this.externeAgenten.on('response', (data) => {
      this.emitEvent('external_agent_response', data);
    });
    
    this.agentsConfig = [
      {
        name: 'ollama',
        type: 'ai',
        port: 11434,
        url: 'http://localhost:11434',
        startCmd: 'open -a Ollama',
        checkEndpoint: '/api/tags',
        description: 'Ollama AI Models'
      },
      {
        name: 'mega-dashboard',
        type: 'dashboard',
        port: 8890,
        url: 'http://localhost:8890',
        startCmd: 'python3 mega-server.py',
        description: 'Mega Dashboard'
      },
      {
        name: 'watchdog',
        type: 'monitor',
        processPattern: 'watchdog.js',
        startCmd: 'node watchdog.js',
        description: 'Memory & Storage Watchdog'
      },
      {
        name: 'n8n',
        type: 'workflow',
        port: 5678,
        url: 'http://localhost:5678',
        description: 'Workflow Automation',
        optional: true
      },
      {
        name: 'netdata',
        type: 'monitor',
        port: 19999,
        url: 'http://localhost:19999',
        description: 'System Monitoring',
        optional: true
      },
      {
        name: 'telegram-bot',
        type: 'notification',
        processPattern: 'telegram',
        description: 'Telegram Notifications'
      }
    ];
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    fs.appendFileSync(this.logFile, line);
  }

  async checkAgent(agent) {
    try {
      if (agent.port) {
        const { stdout } = await execAsync(`lsof -Pi :${agent.port} | grep LISTEN`);
        return stdout.trim().length > 0;
      }
      if (agent.processPattern) {
        const { stdout } = await execAsync(`pgrep -f "${agent.processPattern}"`);
        return stdout.trim().length > 0;
      }
      return false;
    } catch {
      return false;
    }
  }

  async startAgent(agent) {
    if (!agent.startCmd) return false;
    
    try {
      this.log('info', `🚀 Starte ${agent.name}...`);
      
      if (agent.startCmd.includes('open -a')) {
        await execAsync(agent.startCmd);
      } else {
        spawn(agent.startCmd.split(' ')[0], 
              agent.startCmd.split(' ').slice(1), {
          detached: true,
          stdio: 'ignore',
          cwd: process.cwd()
        });
      }
      
      await new Promise(r => setTimeout(r, 3000));
      const running = await this.checkAgent(agent);
      
      if (running) {
        this.log('success', `✅ ${agent.name} läuft`);
        this.emitEvent('agent_started', { agent: agent.name, url: agent.url });
      } else {
        this.log('warn', `⚠️ ${agent.name} konnte nicht starten`);
      }
      
      return running;
    } catch (e) {
      this.log('error', `❌ ${agent.name} Fehler: ${e.message}`);
      return false;
    }
  }

  async scanAllAgents() {
    this.log('info', '🔍 Scanne alle Agenten...');
    
    for (const agent of this.agentsConfig) {
      const running = await this.checkAgent(agent);
      const status = running ? 'running' : (agent.optional ? 'optional' : 'stopped');
      this.agents.set(agent.name, {
        ...agent,
        status: status,
        lastCheck: Date.now()
      });
      
      const icon = running ? '🟢' : (agent.optional ? '🟡' : '🔴');
      this.log('info', `${icon} ${agent.name}: ${running ? 'läuft' : (agent.optional ? 'optional' : 'gestoppt')}`);
    }
  }

  async startAll() {
    this.log('info', '🤖 AGENTEN-HUB STARTET ALLE SYSTEME');
    
    await this.scanAllAgents();
    
    for (const [name, agent] of this.agents) {
      if (agent.status === 'stopped' && agent.startCmd) {
        await this.startAgent(agent);
      }
    }
    
    await this.scanAllAgents();
    this.log('info', '✅ Alle Agenten gestartet');
  }

  emitEvent(type, data) {
    const event = {
      id: Date.now(),
      type,
      data,
      timestamp: new Date().toISOString()
    };
    this.events.push(event);
    
    if (this.events.length > 1000) {
      this.events = this.events.slice(-500);
    }
    
    this.log('event', `📡 ${type}: ${JSON.stringify(data)}`);
  }

  getStatus() {
    const agents = {};
    for (const [name, agent] of this.agents) {
      agents[name] = {
        status: agent.status,
        url: agent.url || null,
        port: agent.port || null,
        type: agent.type,
        description: agent.description
      };
    }
    
    return {
      hub: 'RudiBot Agenten-Hub',
      version: '2.0',
      uptime: Date.now() - this.startTime,
      timestamp: new Date().toISOString(),
      agents,
      events: this.events.slice(-20)
    };
  }

  serveDashboard() {
    const status = this.getStatus();
    
    let agentsHtml = '';
    
    // Lokale Agenten
    for (const [name, agent] of Object.entries(status.agents)) {
      let color, icon;
      if (agent.status === 'running') {
        color = '#4ecca3';
        icon = '🟢';
      } else if (agent.status === 'optional') {
        color = '#f39c12';
        icon = '🟡';
      } else {
        color = '#e74c3c';
        icon = '🔴';
      }
      const link = agent.url ? `<a href="${agent.url}" target="_blank" style="color:#3498db;text-decoration:none;">${agent.url}</a>` : '';
      
      agentsHtml += `
        <div style="background:rgba(0,0,0,0.2);padding:16px;border-radius:12px;margin:8px 0;border-left:4px solid ${color};">
          <div style="font-weight:bold;font-size:1.1em;">${icon} ${name}</div>
          <div style="color:#888;font-size:0.9em;">${agent.description}</div>
          <div style="color:${color};font-size:0.85em;margin-top:4px;">Status: ${agent.status}</div>
          ${link}
        </div>
      `;
    }
    
    // Externe Agenten
    const externeStatus = this.externeAgenten.getStatus();
    agentsHtml += `<div style="margin-top:20px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.1);"><h3 style="color:#3498db;">🌐 Externe AI Agenten</h3>`;
    
    for (const [name, agent] of Object.entries(externeStatus)) {
      const color = agent.status === 'active' ? '#3498db' : (agent.status === 'configured' ? '#f39c12' : '#e74c3c');
      const icon = agent.status === 'active' ? '🔵' : (agent.status === 'configured' ? '🟡' : '🔴');
      
      agentsHtml += `
        <div style="background:rgba(52,152,219,0.1);padding:16px;border-radius:12px;margin:8px 0;border-left:4px solid ${color};">
          <div style="font-weight:bold;font-size:1.1em;">${icon} ${agent.name}</div>
          <div style="color:#888;font-size:0.9em;">${agent.description}</div>
          <div style="color:${color};font-size:0.85em;margin-top:4px;">Status: ${agent.status}</div>
          <div style="color:#666;font-size:0.8em;">Type: ${agent.type}</div>
        </div>
      `;
    }
    agentsHtml += `</div>`;

    return `<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>RudiBot Agenten-Hub</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e);color:#eee;padding:20px;min-height:100vh;}
.header{text-align:center;padding:30px;background:rgba(78,204,163,0.1);border-radius:16px;margin-bottom:20px;border:1px solid rgba(78,204,163,0.3);}
.header h1{color:#4ecca3;font-size:2.5em;}
.btn{background:linear-gradient(135deg,#4ecca3,#3498db);border:none;padding:14px 28px;border-radius:10px;cursor:pointer;font-size:1em;color:#1a1a2e;font-weight:bold;margin:6px;}
.btn-danger{background:linear-gradient(135deg,#e74c3c,#c0392b);color:white;}
.section{background:rgba(22,33,62,0.6);border-radius:16px;padding:20px;margin-bottom:16px;}
.timestamp{color:#666;font-size:0.85em;text-align:center;margin-top:20px;}
</style>
</head>
<body>
<div class="header">
  <h1>🤖 Agenten-Hub</h1>
  <p>Alle Agenten im Überblick - Verbindungshub für alle Tools</p>
</div>

<div class="section" style="text-align:center;">
  <button class="btn" onclick="fetch('/start-all').then(()=>location.reload())">🚀 Alle starten</button>
  <button class="btn" onclick="fetch('/scan').then(()=>location.reload())">🔍 Neu scannen</button>
  <button class="btn btn-danger" onclick="fetch('/cleanup',{method:'POST'}).then(()=>alert('Cleanup done'))">🧹 Cleanup</button>
  <button class="btn" onclick="openAll()">🌐 Alle öffnen</button>
</div>

<div class="section">
  <h2 style="color:#4ecca3;">📊 Agenten Status</h2>
  ${agentsHtml}
</div>

<div class="section">
  <h2 style="color:#4ecca3;">📡 Letzte Events</h2>
  <div style="font-family:monospace;font-size:0.85em;color:#aaa;">
    ${this.events.slice(-10).map(e => `<div>[${e.type}] ${JSON.stringify(e.data).substring(0,80)}</div>`).join('')}
  </div>
</div>

<div class="timestamp">
  RudiBot Agenten-Hub v2.0 | Uptime: ${Math.floor((Date.now()-this.startTime)/1000)}s
</div>

<script>
function openAll(){
  ${Object.values(status.agents).filter(a=>a.url).map(a=>`window.open('${a.url}','_blank');`).join('')}
}
setInterval(()=>location.reload(),30000);
</script>
</body></html>`;
  }

  startServer() {
    const server = http.createServer(async (req, res) => {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      
      if (req.url === '/') {
        res.end(this.serveDashboard());
      } else if (req.url === '/api/status') {
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(this.getStatus()));
      } else if (req.url === '/start-all') {
        await this.startAll();
        res.writeHead(302, { Location: '/' });
        res.end();
      } else if (req.url === '/scan') {
        await this.scanAllAgents();
        res.writeHead(302, { Location: '/' });
        res.end();
      } else if (req.url === '/cleanup' && req.method === 'POST') {
        await execAsync('pkill -f zsh; pkill -f Terminal; purge');
        res.end('{"ok":true}');
      } else {
        res.statusCode = 404;
        res.end('Not found');
      }
    });

    server.listen(this.port, () => {
      this.log('info', `🤖 Agenten-Hub läuft auf http://localhost:${this.port}`);
      this.log('info', `   Starte alle Agenten automatisch...`);
      this.startAll();
    });
  }
}

const hub = new AgentenHub();
hub.startServer();

process.on('SIGINT', () => {
  hub.log('info', '🛑 Agenten-Hub wird gestoppt');
  process.exit(0);
});
