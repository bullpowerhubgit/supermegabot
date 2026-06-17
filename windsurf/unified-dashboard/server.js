#!/usr/bin/env node
/**
 * ╔══════════════════════════════════════════════════════════════╗
 * ║     RUDIBOT UNIFIED DASHBOARD - Command & Control Center      ║
 * ║     Alle Services · Ein Dashboard · Ein Tool                  ║
 * ╚══════════════════════════════════════════════════════════════╝
 */

const express = require('express');
const http = require('http');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const app = express();
const PORT = process.env.UNIFIED_PORT || 9000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ── Service Registry ──────────────────────────────────────────────────
const SERVICES = {
  windsurfApi: { name: 'Windsurf API', port: 3001, type: 'api', url: 'http://localhost:3001' },
  windsurfGateway: { name: 'Windsurf Gateway', port: 8080, type: 'api', url: 'http://localhost:8080' },
  rudibotV2: { name: 'RudiBot v2.0 (Main)', port: 3200, type: 'api', url: 'http://localhost:3200' },
  eternalGuardian: { name: 'Eternal Guardian', port: 3201, type: 'api', url: 'http://localhost:3201' },
  shopifyDashboard: { name: 'Shopify Dashboard', port: 3000, type: 'api', url: 'http://localhost:3000' },
  rudibotMaster: { name: 'RudiBot Master', port: 9900, type: 'api', url: 'http://localhost:9900' },
  shopifyAlt: { name: 'Shopify Dashboard (Alt)', port: 8082, type: 'api', url: 'http://localhost:8082' },
  pm2: { name: 'PM2 Process Manager', port: null, type: 'process', cmd: 'pm2 status' },
  armyCommander: { name: 'Army Commander', port: null, type: 'process', cmd: 'pgrep -f army_commander' },
  metaSupervisor: { name: 'Meta-Supervisor', port: null, type: 'process', cmd: 'pgrep -f meta_supervisor' },
};

// ── Health Check Cache ──────────────────────────────────────────────────
let healthCache = {};
let lastHealthCheck = 0;
const HEALTH_CACHE_TTL = 5000; // 5 seconds

// ── Helper: Check if port is open ─────────────────────────────────────
function checkPort(port, timeout = 2000) {
  return new Promise((resolve) => {
    const req = http.request({ hostname: 'localhost', port, method: 'GET', timeout }, (res) => {
      resolve({ ok: true, status: res.statusCode });
    });
    req.on('error', () => resolve({ ok: false, status: 0 }));
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, status: 0 }); });
    req.end();
  });
}

// ── Helper: Check process ─────────────────────────────────────────────
function checkProcess(cmd) {
  return new Promise((resolve) => {
    exec(cmd, { timeout: 3000 }, (error, stdout) => {
      resolve({ ok: !error && stdout.trim().length > 0, pid: stdout.trim() || null });
    });
  });
}

// ── Health Check All Services ─────────────────────────────────────────
async function checkAllServices() {
  const now = Date.now();
  if (now - lastHealthCheck < HEALTH_CACHE_TTL && Object.keys(healthCache).length > 0) {
    return healthCache;
  }

  const results = {};
  for (const [key, svc] of Object.entries(SERVICES)) {
    try {
      if (svc.type === 'api' && svc.port) {
        const portCheck = await checkPort(svc.port);
        results[key] = { ...svc, status: portCheck.ok ? 'online' : 'offline', statusCode: portCheck.status, lastCheck: new Date().toISOString() };
      } else if (svc.type === 'process') {
        const procCheck = await checkProcess(svc.cmd);
        results[key] = { ...svc, status: procCheck.ok ? 'online' : 'offline', pid: procCheck.pid, lastCheck: new Date().toISOString() };
      }
    } catch (e) {
      results[key] = { ...svc, status: 'error', error: e.message, lastCheck: new Date().toISOString() };
    }
  }

  healthCache = results;
  lastHealthCheck = now;
  return results;
}

// ── API Routes ────────────────────────────────────────────────────────

// Health endpoint for all services
app.get('/api/health', async (_req, res) => {
  const health = await checkAllServices();
  res.json(health);
});

// System info
app.get('/api/system', (_req, res) => {
  res.json({
    platform: os.platform(),
    arch: os.arch(),
    hostname: os.hostname(),
    uptime: os.uptime(),
    loadavg: os.loadavg(),
    totalMem: os.totalmem(),
    freeMem: os.freemem(),
    cpus: os.cpus().length,
    nodeVersion: process.version,
    timestamp: new Date().toISOString()
  });
});

// Quick action: restart a service
app.post('/api/action/restart', (req, res) => {
  const { service } = req.body;
  const allowed = ['windsurfApi', 'telegramBot', 'eternalGuardian'];
  if (!allowed.includes(service)) {
    return res.status(400).json({ error: 'Service not allowed for restart' });
  }

  let cmd;
  if (service === 'windsurfApi') cmd = 'cd /Users/rudolfsarkany/windsurf && npm run dev';
  else if (service === 'telegramBot') cmd = 'cd /Users/rudolfsarkany/windsurf-telegram-bot && npm start';
  else if (service === 'eternalGuardian') cmd = 'cd /Users/rudolfsarkany/rudibot-eternal && python3 eternal_guardian.py';

  const child = spawn(cmd, { shell: true, detached: true, stdio: 'ignore' });
  child.unref();
  res.json({ ok: true, message: `Restart initiated for ${service}`, pid: child.pid });
});

// Quick action: run shell command
app.post('/api/action/exec', (req, res) => {
  const { command, cwd } = req.body;
  const allowedPrefixes = ['pm2', 'git', 'docker', 'python3', 'node', 'npm', 'ls', 'ps', 'cat', 'tail', 'echo', 'curl', 'wget', 'mkdir', 'cp', 'mv', 'rm'];
  const cmdBase = command.trim().split(' ')[0];
  if (!allowedPrefixes.includes(cmdBase)) {
    return res.status(403).json({ error: 'Command not allowed' });
  }

  exec(command, { cwd: cwd || process.cwd(), timeout: 30000 }, (error, stdout, stderr) => {
    res.json({
      ok: !error,
      stdout: stdout?.toString() || '',
      stderr: stderr?.toString() || '',
      exitCode: error?.code || 0
    });
  });
});

// Get latest logs from a service
app.get('/api/logs/:service', (req, res) => {
  const { service } = req.params;
  const logPaths = {
    eternal: '/Users/rudolfsarkany/rudibot-eternal/logs/eternal.log',
    guardian: '/Users/rudolfsarkany/rudibot-eternal/logs/eternal.log',
    windsurf: '/Users/rudolfsarkany/windsurf/server.log',
    telegram: '/Users/rudolfsarkany/windsurf-telegram-bot/logs',
    rudibot: '/Users/rudolfsarkany/CascadeProjects/rudibot/server.log',
    pm2: '/Users/rudolfsarkany/.pm2/logs',
  };

  const logPath = logPaths[service];
  if (!logPath || !fs.existsSync(logPath)) {
    return res.json({ lines: [], error: 'Log file not found' });
  }

  try {
    const stats = fs.statSync(logPath);
    if (stats.isDirectory()) {
      const files = fs.readdirSync(logPath).filter(f => f.endsWith('.log')).slice(0, 5);
      return res.json({ files, path: logPath, isDirectory: true });
    }
    const fd = fs.openSync(logPath, 'r');
    const bufferSize = 1024 * 64; // 64KB
    const buffer = Buffer.alloc(bufferSize);
    const bytesRead = fs.readSync(fd, buffer, 0, bufferSize, Math.max(0, stats.size - bufferSize));
    fs.closeSync(fd);
    const content = buffer.toString('utf8', 0, bytesRead);
    const lines = content.split('\n').filter(l => l.trim()).slice(-100);
    res.json({ lines, path: logPath });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── OpenClaw AI Assistant ────────────────────────────────────────────
const OPENCLAW_URL = process.env.OPENCLAW_URL || 'http://127.0.0.1:18789';
const OPENCLAW_TOKEN = process.env.OPENCLAW_TOKEN || '';

app.post('/api/assistant/chat', async (req, res) => {
  const { message, context, use_tools } = req.body;
  if (!message) return res.status(400).json({ error: 'Message required' });

  try {
    const payload = {
      prompt: message,
      model: process.env.OPENCLAW_MODEL || 'anthropic/claude-sonnet-4-20250514',
      system: `Du bist RudiBot AI, der universelle Assistent für das gesamte RudiBot System.

DEINE FÄHIGKEITEN:
- Services starten/stoppen/restarten (PM2, Windsurf API, Guardian, Shopify)
- Webhook-Einstellungen konfigurieren
- Shopify-Themen und -Einstellungen verwalten
- System-Logs analysieren und Fehler beheben
- API-Keys und Secrets rotieren
- Health Checks durchführen
- Backups erstellen und wiederherstellen
- Konfigurationen ändern (.env, config files)

STANDARDKOMMANDOS:
- Service restart: "restart <service>"
- Log anzeigen: "logs <service>"
- Status check: "status <service>"
- Env ändern: "set <key>=<value>"
- Backup: "backup <project>"

Antworte präzise und lösungsorientiert.`,
      temperature: 0.7,
      max_tokens: 4096,
      stream: false
    };

    const ocReq = http.request({
      hostname: '127.0.0.1',
      port: 18789,
      path: '/api/v1/completions',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': OPENCLAW_TOKEN ? `Bearer ${OPENCLAW_TOKEN}` : '',
        'X-OpenClaw-Token': OPENCLAW_TOKEN
      }
    }, (ocRes) => {
      let data = '';
      ocRes.on('data', chunk => data += chunk);
      ocRes.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          res.json({
            ok: true,
            response: parsed.content || parsed.text || parsed.response || data,
            model: parsed.model,
            tokens: parsed.tokens
          });
        } catch {
          res.json({ ok: true, response: data });
        }
      });
    });

    ocReq.on('error', (err) => {
      res.status(502).json({ error: 'OpenClaw connection failed', detail: err.message });
    });

    ocReq.write(JSON.stringify(payload));
    ocReq.end();
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Fallback: Wenn OpenClaw nicht läuft, lokale Antwort
app.post('/api/assistant/local', (req, res) => {
  const { message } = req.body;
  const lower = message.toLowerCase();

  let response = '';
  if (lower.includes('status') || lower.includes('health')) {
    response = 'Ich kann den Status der Services prüfen. Nutze das Dashboard oder frag: "status windsurf"';
  } else if (lower.includes('restart') || lower.includes('start')) {
    response = 'Services können über das Dashboard gestartet/gestoppt werden. Klicke auf die Action-Buttons in den jeweiligen Sektionen.';
  } else if (lower.includes('log') || lower.includes('fehler')) {
    response = 'Logs sind im Log-Viewer unten rechts verfügbar. Wähle den Service aus dem Dropdown.';
  } else if (lower.includes('shopify')) {
    response = 'Shopify-Integration: Dashboard auf Port 3000/8082, API-Endpunkte unter /api/proxy/shopifyDashboard/';
  } else if (lower.includes('webhook')) {
    response = 'Webhook-Einstellungen: Siehe WEBHOOK_SETUP.md. Endpunkt: /api/v1/webhooks im jeweiligen Service.';
  } else if (lower.includes('help') || lower.includes('hilfe')) {
    response = `RudiBot AI Assistent - Befehle:
• status <service> - Service-Status prüfen
• restart <service> - Service neustarten
• logs <service> - Logs anzeigen
• shopify - Shopify-Info
• webhook - Webhook-Setup
• backup - Backup erstellen
• env - Umgebungsvariablen anzeigen`;
  } else {
    response = `Hallo! Ich bin RudiBot AI. Ich kann dir helfen mit:
• System-Status und Health Checks
• Service-Management (start/stop/restart)
• Log-Analyse und Fehlerbehebung
• Shopify & Webhook Konfiguration
• Backup und Restore
• API-Key Management

Was möchtest du tun?`;
  }

  res.json({ ok: true, response, source: 'local' });
});

// ── Orchestrator Proxy (RudiBot King) ────────────────────────────────
app.get('/api/orchestrator', async (_req, res) => {
  try {
    const proxyReq = http.request({
      hostname: 'localhost',
      port: 3001,
      path: '/api/orchestrator',
      method: 'GET',
      timeout: 5000
    }, (proxyRes) => {
      let data = '';
      proxyRes.on('data', chunk => data += chunk);
      proxyRes.on('end', () => {
        try {
          res.json(JSON.parse(data));
        } catch {
          res.json({ raw: data });
        }
      });
    });
    proxyReq.on('error', () => res.status(502).json({ error: 'Orchestrator offline' }));
    proxyReq.end();
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Quick action via orchestrator
app.post('/api/orchestrator/:service/:action', async (req, res) => {
  const { service, action } = req.params;
  try {
    const proxyReq = http.request({
      hostname: 'localhost',
      port: 3001,
      path: `/api/orchestrator/${service}/${action}`,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeout: 10000
    }, (proxyRes) => {
      let data = '';
      proxyRes.on('data', chunk => data += chunk);
      proxyRes.on('end', () => {
        try { res.json(JSON.parse(data)); } catch { res.json({ raw: data }); }
      });
    });
    proxyReq.on('error', () => res.status(502).json({ error: 'Orchestrator offline' }));
    if (req.body) proxyReq.write(JSON.stringify(req.body));
    proxyReq.end();
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Proxy to other services
app.all('/api/proxy/:service/*', async (req, res) => {
  const { service } = req.params;
  const targetPath = req.params[0] || '';
  const svc = SERVICES[service];
  if (!svc || !svc.url) {
    return res.status(404).json({ error: 'Service not found' });
  }

  try {
    const proxyReq = http.request({
      hostname: 'localhost',
      port: svc.port,
      path: '/' + targetPath + (req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''),
      method: req.method,
      headers: { ...req.headers, host: `localhost:${svc.port}` }
    }, (proxyRes) => {
      res.status(proxyRes.statusCode);
      Object.entries(proxyRes.headers).forEach(([k, v]) => res.setHeader(k, v));
      proxyRes.pipe(res);
    });

    proxyReq.on('error', (err) => {
      res.status(502).json({ error: 'Proxy failed', detail: err.message });
    });

    if (req.body && Object.keys(req.body).length > 0) {
      proxyReq.write(JSON.stringify(req.body));
    }
    proxyReq.end();
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Serve Dashboard ───────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ── Start Server ──────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`╔══════════════════════════════════════════════════════════════╗`);
  console.log(`║     RUDIBOT UNIFIED DASHBOARD                                ║`);
  console.log(`║     Port: ${PORT}                                            ║`);
  console.log(`║     URL:  http://localhost:${PORT}                            ║`);
  console.log(`╚══════════════════════════════════════════════════════════════╝`);
});
