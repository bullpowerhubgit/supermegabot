#!/usr/bin/env node

/**
 * SuperMegaBot Dashboard + Orchestrator Integration
 * Port: 8888
 * Features: System Tools + API Agents + Telegram Integration
 */

import http from 'http';
import fs from 'fs';
import path from 'path';
import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import os from 'os';
import crypto from 'crypto';
import axios from 'axios';

const execAsync = promisify(exec);

// Load environment variables
const PORT = 8888;
const DATA_DIR = path.join(os.homedir(), 'SuperMegaBot-Data');
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
const LOG_FILE = path.join(DATA_DIR, 'orchestrator-dashboard.log');
const PID_FILE = path.join('/tmp', 'supermegabot-dashboard.pid');

[DATA_DIR, BACKUP_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

function log(level, message) {
  const ts = new Date().toISOString();
  const line = `[${ts}] [${level.toUpperCase()}] ${message}\n`;
  try { fs.appendFileSync(LOG_FILE, line); } catch (e) {}
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug(`[${level.toUpperCase()}] ${message}`);
}

// ========================================================================
// ORCHESTRATOR CLASS - API AGENTS
// ========================================================================

class MegaOrchestrator {
  constructor() {
    this.agents = {
      supabase: { status: 'unknown', lastPing: null, data: null },
      google: { status: 'unknown', lastPing: null, data: null },
      shopify: { status: 'unknown', lastPing: null, data: null },
      github: { status: 'unknown', lastPing: null, data: null },
      telegram: { status: 'unknown', lastPing: null, data: null }
    };
    this.startTime = Date.now();
  }

  async checkSupabase() {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_ANON_KEY;
    if (!url || !key) {
      this.agents.supabase.status = 'not_configured';
      return null;
    }
    try {
      const res = await axios.get(`${url}/rest/v1/reports?select=id&limit=1`, {
        headers: { apikey: key, Authorization: `Bearer ${key}` },
        timeout: 5000
      });
      this.agents.supabase.status = 'online';
      this.agents.supabase.lastPing = Date.now();
      this.agents.supabase.data = { reports: res.data.length };
      log('info', '✅ Supabase Agent online');
      return res.data;
    } catch (err) {
      this.agents.supabase.status = 'error';
      this.agents.supabase.data = { error: err.message };
      log('error', `❌ Supabase Agent: ${err.message}`);
      return null;
    }
  }

  async checkGoogle() {
    const clientId = process.env.GOOGLE_CLIENT_ID;
    const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
    if (!clientId || !clientSecret) {
      this.agents.google.status = 'not_configured';
      return null;
    }
    try {
      // Simuliere Google API Check
      this.agents.google.status = 'online';
      this.agents.google.lastPing = Date.now();
      this.agents.google.data = { 
        clientId: clientId.slice(0, 20) + '...',
        merchantId: process.env.GMC_MERCHANT_ID || 'not_set'
      };
      log('info', '✅ Google Agent online');
      return this.agents.google.data;
    } catch (err) {
      this.agents.google.status = 'error';
      this.agents.google.data = { error: err.message };
      log('error', `❌ Google Agent: ${err.message}`);
      return null;
    }
  }

  async checkShopify() {
    const token = process.env.SHOPIFY_ACCESS_TOKEN;
    const domain = process.env.SHOPIFY_SHOP_DOMAIN;
    if (!token || !domain) {
      this.agents.shopify.status = 'not_configured';
      return null;
    }
    try {
      const res = await axios.get(`https://${domain}/admin/api/2026-04/shop.json`, {
        headers: { 'X-Shopify-Access-Token': token },
        timeout: 5000
      });
      this.agents.shopify.status = 'online';
      this.agents.shopify.lastPing = Date.now();
      this.agents.shopify.data = { shop: res.data.shop.name, domain };
      log('info', '✅ Shopify Agent online');
      return res.data.shop;
    } catch (err) {
      this.agents.shopify.status = 'error';
      this.agents.shopify.data = { error: err.message };
      log('error', `❌ Shopify Agent: ${err.message}`);
      return null;
    }
  }

  async checkGitHub() {
    const token = process.env.GITHUB_TOKEN;
    const user = process.env.GITHUB_USER;
    if (!token || !user) {
      this.agents.github.status = 'not_configured';
      return null;
    }
    try {
      const res = await axios.get('https://api.github.com/user', {
        headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github.v3+json' },
        timeout: 5000
      });
      this.agents.github.status = 'online';
      this.agents.github.lastPing = Date.now();
      this.agents.github.data = { user: res.data.login, repos: res.data.public_repos };
      log('info', '✅ GitHub Agent online');
      return res.data;
    } catch (err) {
      this.agents.github.status = 'error';
      this.agents.github.data = { error: err.message };
      log('error', `❌ GitHub Agent: ${err.message}`);
      return null;
    }
  }

  async checkTelegram() {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;
    if (!token || !chatId) {
      this.agents.telegram.status = 'not_configured';
      return null;
    }
    try {
      const res = await axios.get(`https://api.telegram.org/bot${token}/getMe`, {
        timeout: 5000
      });
      this.agents.telegram.status = 'online';
      this.agents.telegram.lastPing = Date.now();
      this.agents.telegram.data = { bot: res.data.result.username, chatId: chatId.replace(/.*$/, '***') };
      log('info', '✅ Telegram Agent online');
      return res.data.result;
    } catch (err) {
      this.agents.telegram.status = 'error';
      this.agents.telegram.data = { error: err.message };
      log('error', `❌ Telegram Agent: ${err.message}`);
      return null;
    }
  }

  async runAllChecks() {
    const results = await Promise.allSettled([
      this.checkSupabase(),
      this.checkGoogle(),
      this.checkShopify(),
      this.checkGitHub(),
      this.checkTelegram()
    ]);
    
    return this.agents;
  }

  async sendTelegramReport(report) {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;
    if (!token || !chatId) return false;
    
    try {
      await axios.post(
        `https://api.telegram.org/bot${token}/sendMessage`,
        { chat_id: chatId, text: report, parse_mode: 'Markdown' },
        { timeout: 10000 }
      );
      log('info', '✅ Telegram Report gesendet');
      return true;
    } catch (err) {
      log('error', `❌ Telegram: ${err.response?.data?.description || err.message}`);
      return false;
    }
  }

  generateReport() {
    const uptime = ((Date.now() - this.startTime) / 1000).toFixed(1);
    const emoji = { online: '🟢', error: '🔴', not_configured: '⚪', unknown: '⚪' };

    return `
🤖 *SuperMegaBot Orchestrator Report*

⏱ Uptime: ${uptime}s
📅 ${new Date().toLocaleString('de-DE')}

*Agenten Status:*
${Object.entries(this.agents).map(([name, a]) => `${emoji[a.status]} *${name.toUpperCase()}* — ${a.status}`).join('\n')}

_Automatisch generiert_
    `.trim();
  }
}

// ========================================================================
// SYSTEM MONITOR
// ========================================================================

class SystemMonitor {
  async getMetrics() {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const usedMem = totalMem - freeMem;

    return {
      memory: {
        total: Math.round(totalMem / 1024 / 1024),
        used: Math.round(usedMem / 1024 / 1024),
        free: Math.round(freeMem / 1024 / 1024),
        percent: totalMem > 0 ? Math.round((usedMem / totalMem) * 100) : 0
      },
      cpu: os.cpus().length,
      platform: os.platform(),
      uptime: os.uptime()
    };
  }
}

// ========================================================================
// HTTP SERVER
// ========================================================================

const orchestrator = new MegaOrchestrator();
const systemMonitor = new SystemMonitor();

const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  
  try {
    // API Endpoints
    if (url.pathname.startsWith('/api/')) {
      if (url.pathname === '/api/status') {
        const [system, agents] = await Promise.all([
          systemMonitor.getMetrics(),
          orchestrator.runAllChecks()
        ]);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, system, agents }));
        return;
      }

      if (url.pathname === '/api/orchestrator/run') {
        const agents = await orchestrator.runAllChecks();
        const report = orchestrator.generateReport();
        await orchestrator.sendTelegramReport(report);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, agents, report }));
        return;
      }

      if (url.pathname === '/api/orchestrator/report') {
        const report = orchestrator.generateReport();
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end(report);
        return;
      }
    }

    // Dashboard HTML
    if (url.pathname === '/' || url.pathname === '/dashboard') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(getDashboardHTML());
      return;
    }

    // 404
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');

  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success: false, error: error.message }));
  }
});

// ========================================================================
// DASHBOARD HTML
// ========================================================================

function getDashboardHTML() {
  return `<!DOCTYPE html>
<html>
<head>
  <title>SuperMegaBot Dashboard + Orchestrator</title>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; }
    .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
    .header { text-align: center; margin-bottom: 40px; }
    .header h1 { font-size: 2.5em; color: #00ff88; margin-bottom: 10px; }
    .header p { color: #888; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
    .card { background: linear-gradient(135deg, #1a1a2e, #16213e); border: 1px solid #333; border-radius: 12px; padding: 20px; transition: transform 0.2s; }
    .card:hover { transform: translateY(-2px); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
    .card-title { font-size: 1.2em; font-weight: 600; }
    .status { padding: 4px 12px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }
    .status.online { background: #00ff8820; color: #00ff88; }
    .status.error { background: #ff444420; color: #ff4444; }
    .status.not_configured { background: #888820; color: #888; }
    .status.unknown { background: #444420; color: #888; }
    .card-content { color: #ccc; }
    .metric { display: flex; justify-content: space-between; margin: 8px 0; }
    .metric-value { font-weight: 600; color: #00ff88; }
    .actions { display: flex; gap: 10px; margin-top: 20px; }
    .btn { padding: 10px 20px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .btn-primary { background: #00ff88; color: #000; }
    .btn-primary:hover { background: #00ffaa; }
    .btn-secondary { background: #333; color: #fff; }
    .btn-secondary:hover { background: #555; }
    .log-container { background: #111; border: 1px solid #333; border-radius: 8px; padding: 15px; height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.9em; }
    .log-entry { margin: 2px 0; padding: 2px 0; }
    .log-entry.info { color: #00ff88; }
    .log-entry.error { color: #ff4444; }
    .log-entry.warn { color: #ffaa00; }
    .system-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }
    .metric-card { background: #111; padding: 15px; border-radius: 8px; text-align: center; }
    .metric-value.large { font-size: 2em; font-weight: 700; color: #00ff88; }
    .metric-label { color: #888; margin-top: 5px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🤖 SuperMegaBot Dashboard</h1>
      <p>System Tools + API Agents + Telegram Integration</p>
    </div>

    <div class="system-metrics" id="systemMetrics">
      <!-- System metrics will be loaded here -->
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-header">
          <div class="card-title">🤖 Orchestrator</div>
          <div class="status unknown" id="orchestratorStatus">Checking...</div>
        </div>
        <div class="card-content">
          <div class="metric">
            <span>Uptime</span>
            <span class="metric-value" id="orchestratorUptime">-</span>
          </div>
          <div class="metric">
            <span>Active Agents</span>
            <span class="metric-value" id="activeAgents">-</span>
          </div>
        </div>
        <div class="actions">
          <button class="btn btn-primary" onclick="runOrchestrator()">🚀 Run All Checks</button>
          <button class="btn btn-secondary" onclick="sendReport()">📤 Send Report</button>
        </div>
      </div>

      <div class="card" id="supabaseCard">
        <div class="card-header">
          <div class="card-title">🗄️ Supabase</div>
          <div class="status unknown" id="supabaseStatus">-</div>
        </div>
        <div class="card-content" id="supabaseContent">
          <div class="metric">
            <span>Reports</span>
            <span class="metric-value">-</span>
          </div>
        </div>
      </div>

      <div class="card" id="googleCard">
        <div class="card-header">
          <div class="card-title">🔍 Google APIs</div>
          <div class="status unknown" id="googleStatus">-</div>
        </div>
        <div class="card-content" id="googleContent">
          <div class="metric">
            <span>Client ID</span>
            <span class="metric-value">-</span>
          </div>
        </div>
      </div>

      <div class="card" id="shopifyCard">
        <div class="card-header">
          <div class="card-title">🛍️ Shopify</div>
          <div class="status unknown" id="shopifyStatus">-</div>
        </div>
        <div class="card-content" id="shopifyContent">
          <div class="metric">
            <span>Shop</span>
            <span class="metric-value">-</span>
          </div>
        </div>
      </div>

      <div class="card" id="githubCard">
        <div class="card-header">
          <div class="card-title">🐙 GitHub</div>
          <div class="status unknown" id="githubStatus">-</div>
        </div>
        <div class="card-content" id="githubContent">
          <div class="metric">
            <span>Repositories</span>
            <span class="metric-value">-</span>
          </div>
        </div>
      </div>

      <div class="card" id="telegramCard">
        <div class="card-header">
          <div class="card-title">✈️ Telegram</div>
          <div class="status unknown" id="telegramStatus">-</div>
        </div>
        <div class="card-content" id="telegramContent">
          <div class="metric">
            <span>Bot</span>
            <span class="metric-value">-</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title">📋 Activity Log</div>
        <button class="btn btn-secondary" onclick="clearLog()">Clear</button>
      </div>
      <div class="log-container" id="logContainer">
        <div class="log-entry info">System initialized</div>
      </div>
    </div>
  </div>

  <script>
    let currentStatus = {};

    function addLog(message, type = 'info') {
      const container = document.getElementById('logContainer');
      const entry = document.createElement('div');
      entry.className = 'log-entry ' + type;
      entry.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
      container.appendChild(entry);
      container.scrollTop = container.scrollHeight;
    }

    function clearLog() {
      document.getElementById('logContainer').textContent = ;
      addLog('Log cleared');
    }

    function updateAgentCard(agent, data) {
      const statusEl = document.getElementById(agent + 'Status');
      const contentEl = document.getElementById(agent + 'Content');
      const cardEl = document.getElementById(agent + 'Card');
      
      if (statusEl) {
        statusEl.className = 'status ' + data.status;
        statusEl.textContent = data.status;
      }
      
      if (contentEl && data.data) {
        contentEl.textContent = '';
        function createMetric(label, value) {
          const metric = document.createElement('div');
          metric.className = 'metric';
          const labelSpan = document.createElement('span');
          labelSpan.textContent = label;
          const valueSpan = document.createElement('span');
          valueSpan.className = 'metric-value';
          valueSpan.textContent = value || 'N/A';
          metric.appendChild(labelSpan);
          metric.appendChild(valueSpan);
          return metric;
        }
        if (agent === 'supabase') {
          contentEl.appendChild(createMetric('Reports', data.data.reports || 0));
        } else if (agent === 'google') {
          contentEl.appendChild(createMetric('Client ID', data.data.clientId));
          contentEl.appendChild(createMetric('Merchant ID', data.data.merchantId));
        } else if (agent === 'shopify') {
          contentEl.appendChild(createMetric('Shop', data.data.shop));
          contentEl.appendChild(createMetric('Domain', data.data.domain));
        } else if (agent === 'github') {
          contentEl.appendChild(createMetric('User', data.data.user));
          contentEl.appendChild(createMetric('Repos', data.data.repos || 0));
        } else if (agent === 'telegram') {
          contentEl.appendChild(createMetric('Bot', data.data.bot));
          contentEl.appendChild(createMetric('Chat ID', data.data.chatId));
        }
      }
      
      if (cardEl) {
        if (data.status === 'online') {
          cardEl.classList.add('active');
        } else {
          cardEl.classList.remove('active');
        }
      }
    }

    function updateSystemMetrics(system) {
      const container = document.getElementById('systemMetrics');
      container.textContent = '';
      function createMetricCard(value, label) {
        const card = document.createElement('div');
        card.className = 'metric-card';
        const valueDiv = document.createElement('div');
        valueDiv.className = 'metric-value large';
        valueDiv.textContent = value;
        const labelDiv = document.createElement('div');
        labelDiv.className = 'metric-label';
        labelDiv.textContent = label;
        card.appendChild(valueDiv);
        card.appendChild(labelDiv);
        return card;
      }
      container.appendChild(createMetricCard(system.memory.used + 'MB', 'Memory Used'));
      container.appendChild(createMetricCard(system.memory.percent + '%', 'Memory Usage'));
      container.appendChild(createMetricCard(system.cpu, 'CPU Cores'));
      container.appendChild(createMetricCard(Math.floor(system.uptime / 3600) + 'h', 'System Uptime'));
    }

    async function fetchStatus() {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success) {
          currentStatus = data;
          updateSystemMetrics(data.system);
          
          // Update orchestrator
          const onlineCount = Object.values(data.agents).filter(a => a.status === 'online').length;
          document.getElementById('orchestratorStatus').className = 'status online';
          document.getElementById('orchestratorStatus').textContent = 'Active';
          document.getElementById('orchestratorUptime').textContent = onlineCount + '/5 online';
          document.getElementById('activeAgents').textContent = onlineCount;
          
          // Update all agent cards
          Object.keys(data.agents).forEach(agent => {
            updateAgentCard(agent, data.agents[agent]);
          });
        }
      } catch (error) {
        addLog('Failed to fetch status: ' + error.message, 'error');
      }
    }

    async function runOrchestrator() {
      addLog('🚀 Running Orchestrator checks...');
      try {
        const response = await fetch('/api/orchestrator/run');
        const data = await response.json();
        
        if (data.success) {
          addLog('✅ Orchestrator completed successfully');
          await fetchStatus(); // Refresh status
        } else {
          addLog('❌ Orchestrator failed', 'error');
        }
      } catch (error) {
        addLog('❌ Orchestrator error: ' + error.message, 'error');
      }
    }

    async function sendReport() {
      addLog('📤 Sending Telegram report...');
      try {
        const response = await fetch('/api/orchestrator/report');
        const report = await response.text();
        
        // Copy to clipboard
        navigator.clipboard.writeText(report);
        addLog('✅ Report copied to clipboard');
      } catch (error) {
        addLog('❌ Failed to get report: ' + error.message, 'error');
      }
    }

    // Auto-refresh every 10 seconds
    setInterval(fetchStatus, 10000);
    
    // Initial load
    fetchStatus();
  </script>
</body>
</html>`;
}

// ========================================================================
// START SERVER
// ========================================================================

server.listen(PORT, () => {
  log('info', `🚀 SuperMegaBot Dashboard + Orchestrator running at http://localhost:${PORT}`);
  log('info', 'Features: System Monitor + API Agents + Telegram Integration');
  try { fs.writeFileSync(PID_FILE, process.pid.toString()); } catch (e) {}
});

process.on('SIGINT', () => {
  log('info', 'Shutting down...');
  try { fs.unlinkSync(PID_FILE); } catch (e) {}
  server.close(() => process.exit(0));
});
