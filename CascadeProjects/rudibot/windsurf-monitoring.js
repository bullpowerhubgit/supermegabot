// ============================================================
// windsurf-monitoring.js — AutoPilot Live Monitor
// Rudolf Sarkany · Port 9001 · Production Ready
// Start: node windsurf-monitoring.js
// Dashboard: http://localhost:9001
// ============================================================
'use strict';
require('dotenv').config();

const http = require('http');
const PORT = process.env.MONITORING_PORT || 9001;
const CHECK_INTERVAL = parseInt(process.env.HEALTH_CHECK_INTERVAL) || 30000;

// ── State ─────────────────────────────────────────────────────
const state = {
  startTime: Date.now(),
  checks: [],
  history: [],       // letzten 20 Check-Ergebnisse
  alerts: [],        // aktive Alerts
  botPid: null,
  serverPid: null,
};

// ── Check Functions ───────────────────────────────────────────
async function checkService(name, fn) {
  const t0 = Date.now();
  try {
    const result = await fn();
    const ms = Date.now() - t0;
    return { name, status: 'ok', ms, detail: result || 'OK', ts: new Date().toISOString() };
  } catch(e) {
    const ms = Date.now() - t0;
    return { name, status: 'error', ms, detail: e.message, ts: new Date().toISOString() };
  }
}

async function runChecks() {
  const results = await Promise.allSettled([

    checkService('Server :3200', async () => {
      const r = await fetchWithTimeout('http://localhost:3200/api/health', 5000);
      if (!r.ok) throw new Error('HTTP '+r.status);
      const d = await r.json();
      return `uptime=${d.uptime} mem=${d.memory}`;
    }),

    checkService('Claude API', async () => {
      const key = process.env.ANTHROPIC_API_KEY;
      if (!key) throw new Error('ANTHROPIC_API_KEY fehlt!');
      const r = await fetchWithTimeout('https://api.anthropic.com/v1/models', 8000, { headers: { 'x-api-key': key } });
      if (!r.ok) throw new Error('HTTP '+r.status);
      return 'API erreichbar';
    }),

    checkService('Shopify Store1', async () => {
      const tok = process.env.SHOPIFY_ADMIN_TOKEN;
      const store = process.env.SHOPIFY_STORE_URL;
      if (!tok || !store) throw new Error('Keys fehlen!');
      const r = await fetchWithTimeout(`https://${store}/admin/api/2025-01/shop.json`, 8000, {
        headers: { 'X-Shopify-Access-Token': tok }
      });
      if (!r.ok) throw new Error('HTTP '+r.status+' — Token rotieren?');
      const d = await r.json();
      return d.shop?.name || 'OK';
    }),


    checkService('GitHub API', async () => {
      const tok = process.env.GITHUB_TOKEN;
      if (!tok) throw new Error('GITHUB_TOKEN fehlt!');
      const r = await fetchWithTimeout('https://api.github.com/user', 8000, {
        headers: { 'Authorization': `token ${tok}` }
      });
      if (!r.ok) throw new Error('HTTP '+r.status+' — Token rotieren?');
      const d = await r.json();
      return `@${d.login} (${d.public_repos} repos)`;
    }),

    checkService('ENV Keys', async () => {
      const keys = {
        ANTHROPIC_API_KEY: !!process.env.ANTHROPIC_API_KEY,
        TELEGRAM_BOT_TOKEN: !!process.env.TELEGRAM_BOT_TOKEN,
        OPENAI_API_KEY: !!process.env.OPENAI_API_KEY,
        PERPLEXITY_API_KEY: !!process.env.PERPLEXITY_API_KEY,
        GITHUB_TOKEN: !!process.env.GITHUB_TOKEN,
        SHOPIFY_ADMIN_TOKEN: !!process.env.SHOPIFY_ADMIN_TOKEN,
        SHOPIFY_STORE2_TOKEN: !!process.env.SHOPIFY_STORE2_TOKEN,
      };
      const missing = Object.entries(keys).filter(([,v])=>!v).map(([k])=>k);
      if (missing.length) throw new Error(`Fehlen: ${missing.join(', ')}`);
      return `${Object.keys(keys).length}/${Object.keys(keys).length} vorhanden`;
    }),

  ]);

  state.checks = results.map(r => r.value || r.reason);
  state.history.unshift({ ts: new Date().toISOString(), checks: state.checks });
  if (state.history.length > 20) state.history.pop();

  // Alerts
  state.alerts = state.checks.filter(c => c.status === 'error').map(c => ({
    service: c.name, message: c.detail, ts: c.ts
  }));

  const ok  = state.checks.filter(c => c.status === 'ok').length;
  const err = state.checks.filter(c => c.status === 'error').length;
  const ts  = new Date().toLocaleTimeString('de-DE');
  console.log(`[${ts}] Health: ${ok}/${state.checks.length} OK${err ? ` · ⚠️ ${err} Fehler` : ' ✅'}`);
  if (err) state.checks.filter(c=>c.status==='error').forEach(c => console.error(`   ❌ ${c.name}: ${c.detail}`));
}

async function fetchWithTimeout(url, timeout = 5000, opts = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try { return await fetch(url, { ...opts, signal: ctrl.signal }); }
  finally { clearTimeout(timer); }
}

// ── HTML Dashboard ────────────────────────────────────────────
function dashboard() {
  const uptime = Math.round((Date.now() - state.startTime) / 1000);
  const mem    = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
  const ok     = state.checks.filter(c => c.status === 'ok').length;
  const total  = state.checks.length;
  const pct    = total ? Math.round(ok / total * 100) : 0;

  const rows = state.checks.map(c => `
    <tr>
      <td>${c.name}</td>
      <td><span class="badge ${c.status === 'ok' ? 'ok' : 'err'}">${c.status === 'ok' ? '✅ OK' : '❌ FEHLER'}</span></td>
      <td>${c.ms}ms</td>
      <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.detail}</td>
      <td>${c.ts?.slice(11,19)||''}</td>
    </tr>`).join('');

  const alertHtml = state.alerts.length ? state.alerts.map(a =>
    `<div class="alert">⚠️ <strong>${a.service}:</strong> ${a.message}</div>`).join('')
    : '<div class="ok-banner">✅ Alle Services funktionieren</div>';

  return `<!DOCTYPE html><html lang="de"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>RudiBot Monitor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#08080f;color:#e2e8f0;font-family:'Segoe UI',sans-serif;padding:20px}
.hdr{background:linear-gradient(135deg,#0f0f1a,#1a0830);border:1px solid #1e1e32;border-radius:12px;padding:16px 20px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center}
h1{font-size:18px;font-weight:800;color:#fff}
.sub{font-size:11px;color:#64748b}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat{background:#0f0f1a;border:1px solid #1e1e32;border-radius:10px;padding:14px;text-align:center}
.stat-v{font-size:24px;font-weight:900;color:#fff;margin:4px 0}
.stat-l{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.card{background:#0f0f1a;border:1px solid #1e1e32;border-radius:12px;padding:16px;margin-bottom:14px}
h2{font-size:14px;font-weight:700;color:#fff;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{background:#0d1117;color:#64748b;text-align:left;padding:7px 10px;border-bottom:1px solid #1e1e32;font-size:10px;text-transform:uppercase;letter-spacing:.05em}
td{padding:7px 10px;border-bottom:1px solid #1e1e32}
tr:hover td{background:rgba(124,58,237,.05)}
.badge{padding:2px 8px;border-radius:8px;font-size:10px;font-weight:700}
.badge.ok{background:rgba(16,185,129,.2);color:#6ee7b7;border:1px solid rgba(16,185,129,.3)}
.badge.err{background:rgba(239,68,68,.2);color:#fca5a5;border:1px solid rgba(239,68,68,.3)}
.alert{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#fca5a5;padding:8px 12px;border-radius:7px;margin-bottom:6px;font-size:12px}
.ok-banner{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);color:#6ee7b7;padding:8px 12px;border-radius:7px;font-size:12px}
.prog{background:#0d1117;border-radius:5px;height:6px;overflow:hidden;margin-top:6px}
.pb{height:100%;border-radius:5px;background:linear-gradient(90deg,#7c3aed,#06b6d4);transition:width .5s}
@media(max-width:500px){.stats{grid-template-columns:1fr 1fr}}
</style>
</head><body>
<div class="hdr">
  <div><h1>🤖 RudiBot Monitor</h1><div class="sub">AutoPilot Business Bot · Port 9001 · Auto-Refresh 30s</div></div>
  <div style="font-size:11px;color:#64748b">${new Date().toLocaleString('de-DE')}</div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-l">Health Score</div><div class="stat-v" style="color:${pct===100?'#10b981':pct>=50?'#f59e0b':'#ef4444'}">${pct}%</div>
    <div class="prog"><div class="pb" style="width:${pct}%;background:${pct===100?'linear-gradient(90deg,#10b981,#06b6d4)':pct>=50?'linear-gradient(90deg,#f59e0b,#10b981)':'linear-gradient(90deg,#ef4444,#f59e0b)'}"></div></div>
  </div>
  <div class="stat"><div class="stat-l">Services OK</div><div class="stat-v">${ok}/${total}</div></div>
  <div class="stat"><div class="stat-l">Uptime</div><div class="stat-v" style="font-size:18px">${Math.floor(uptime/3600)}h ${Math.floor((uptime%3600)/60)}m</div></div>
  <div class="stat"><div class="stat-l">Memory</div><div class="stat-v">${mem}MB</div></div>
</div>

<div class="card">${alertHtml}</div>

<div class="card">
  <h2>Service Status</h2>
  <table><tr><th>Service</th><th>Status</th><th>Latenz</th><th>Detail</th><th>Zeit</th></tr>${rows}</table>
</div>

<div class="card">
  <h2>Quick Links</h2>
  <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:12px">
    <a href="http://localhost:3200/api/health" style="color:#67e8f9" target="_blank">🔗 Server Health</a> ·
    <a href="http://localhost:3200/api/status" style="color:#67e8f9" target="_blank">📊 API Status</a> ·
    <a href="http://localhost:3200/api/shopify/store" style="color:#67e8f9" target="_blank">🛒 Shopify Store</a> ·
    <a href="http://localhost:3200/api/github/repos" style="color:#67e8f9" target="_blank">🐙 GitHub Repos</a>
  </div>
</div>
</body></html>`;
}

// ── HTTP Server ───────────────────────────────────────────────
const server = http.createServer((req, res) => {
  if (req.url === '/monitoring-stats') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    return res.end(JSON.stringify({ uptime: Math.round((Date.now()-state.startTime)/1000), checks: state.checks, alerts: state.alerts, history: state.history.slice(0,5) }));
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(dashboard());
});

// ── Start ─────────────────────────────────────────────────────
server.listen(PORT, async () => {
  console.log(`\n📊 Monitoring Dashboard: http://localhost:${PORT}`);
  console.log(`📈 Stats API: http://localhost:${PORT}/monitoring-stats`);
  console.log(`⏱  Check-Intervall: ${CHECK_INTERVAL/1000}s\n`);
  await runChecks();
  setInterval(runChecks, CHECK_INTERVAL);
});
