#!/usr/bin/env node
const http = require('http');
const { exec } = require('child_process');
const os = require('os');

const PORT = 3200;

function run(cmd) {
  return new Promise((res, rej) => {
    exec(cmd, { env: { ...process.env, PATH: '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin' } }, (e, out) => {
      if (e && !out) rej(e);
      else res(out || '');
    });
  });
}

async function getData() {
  const total = os.totalmem(), free = os.freemem();
  const mem = { total: (total/1e9).toFixed(1), used: ((total-free)/1e9).toFixed(1), free: (free/1e9).toFixed(1), pct: Math.round((total-free)/total*100) };
  let cpu = 0; try { cpu = Math.min(Math.round(parseFloat(await run("ps -A -o %cpu | awk '{s+=$1} END {print s}'"))), 100); } catch {}
  let disk = 0; try { disk = parseInt((await run("df -H / | tail -1 | awk '{print $5}'")).replace('%','')); } catch {}

  const svcs = [];
  for (const s of ['watchdog','watchdog-monitor','mega-dashboard','bot-system','launcher']) {
    try { const out = await run(`launchctl list | grep "com.supermegabot.${s}" | head -1`); const p = out.trim().split(/\s+/); svcs.push({name: s, pid: p[0]||'-', code: p[1]||'stopped', label: (p[2]||'').replace('com.supermegabot.','')}); }
    catch { svcs.push({name: s, pid: '-', code: 'stopped', label: s}); }
  }

  const bots = [];
  for (const [n,p] of [['Orchestrator','bot-system'],['Public Bot','public-bot.js'],['Control Bot','control-bot.js'],['MTProto','mtproto-client.js']]) {
    try { const pid = (await run(`pgrep -f "${p}"`)).trim(); bots.push({name: n, status: 'running', pid}); }
    catch { bots.push({name: n, status: 'stopped', pid: '-'}); }
  }

  let wds = [];
  try { const out = await run('launchctl list | grep watchdog'); wds = out.trim().split('\n').map(l=>{const p=l.trim().split(/\s+/); return p.length>=3?{pid:p[0],code:p[1],label:p[2]}:null;}).filter(Boolean); } catch {}

  const alerts = [];
  if (mem.pct > 90) alerts.push({t: 'critical', text: `RAM kritisch: ${mem.pct}%`});
  else if (mem.pct > 75) alerts.push({t: 'warn', text: `RAM hoch: ${mem.pct}%`});
  if (cpu > 90) alerts.push({t: 'critical', text: `CPU kritisch: ${cpu}%`});
  else if (cpu > 75) alerts.push({t: 'warn', text: `CPU hoch: ${cpu}%`});
  const down = bots.filter(b => b.status === 'stopped');
  if (down.length > 0) alerts.push({t: 'warn', text: `${down.length} Bot(s) offline`});

  return { mem, cpu, disk, bots, svcs, wds, alerts, uptime: Math.round(os.uptime()), now: new Date().toLocaleTimeString('de-DE') };
}

function badge(s) {
  if (s === 'running' || s === '0') return '<span class="b ok">OK</span>';
  if (s === 'stopped' || s === '-') return '<span class="b bad">OFF</span>';
  return '<span class="b warn">'+s+'</span>';
}

async function html() {
  const d = await getData();
  const mc = d.mem.pct > 90 ? '#ef4444' : d.mem.pct > 75 ? '#f59e0b' : '#10b981';
  const cc = d.cpu > 90 ? '#ef4444' : d.cpu > 75 ? '#f59e0b' : '#10b981';
  const dc = d.disk > 85 ? '#ef4444' : d.disk > 70 ? '#f59e0b' : '#10b981';
  const ft = s => { const da=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60); return da>0?`${da}d ${h}h ${m}m`:h>0?`${h}h ${m}m`:`${m}m`; };

  return `<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>SuperMegaBot Command Center</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b14;--bg2:#0f172a;--bg3:#1e2937;--a:#3b82f6;--a2:#8b5cf6;--ok:#10b981;--warn:#f59e0b;--bad:#ef4444;--t:#f1f5f9;--t2:#94a3b8;--b:rgba(148,163,184,0.1)}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--t);font-size:13px}
.hdr{background:var(--bg2);border-bottom:1px solid var(--b);padding:12px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.hdr h1{font-size:16px;font-weight:700;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .sub{font-size:10px;color:var(--t2);text-transform:uppercase;letter-spacing:1px}
.hdr .time{font-size:12px;color:var(--t2);display:flex;align-items:center;gap:6px}
.live{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.wrap{max-width:1200px;margin:0 auto;padding:16px 20px}

.tabs{display:flex;gap:2px;margin-bottom:14px;background:var(--bg2);padding:3px;border-radius:8px;border:1px solid var(--b);width:fit-content}
.tab{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;color:var(--t2);cursor:pointer;border:none;background:transparent}
.tab.on{background:linear-gradient(135deg,var(--a),var(--a2));color:#fff}

.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--bg2);border:1px solid var(--b);border-radius:10px;padding:14px;position:relative}
.card::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--a),var(--a2));opacity:.5}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.card-v{font-size:22px;font-weight:700}
.card-l{font-size:10px;color:var(--t2);text-transform:uppercase;letter-spacing:.5px}
.bar{height:3px;border-radius:2px;background:var(--bg3);overflow:hidden;margin-top:6px}
.bar-f{height:100%;border-radius:2px;transition:width .5s}
.meta{display:flex;justify-content:space-between;margin-top:4px;font-size:10px;color:var(--t2)}

.alert{padding:10px 12px;border-radius:8px;margin-bottom:8px;display:flex;align-items:center;gap:8px;border:1px solid;font-size:13px}
.alert.crit{background:rgba(239,68,68,.05);border-color:rgba(239,68,68,.2);color:var(--bad)}
.alert.warn{background:rgba(245,158,11,.05);border-color:rgba(245,158,11,.2);color:var(--warn)}
.alert.ok{background:rgba(16,185,129,.05);border-color:rgba(16,185,129,.2);color:var(--ok);justify-content:center}

.b{padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
.b.ok{background:rgba(16,185,129,.12);color:var(--ok)}
.b.bad{background:rgba(239,68,68,.12);color:var(--bad)}
.b.warn{background:rgba(245,158,11,.12);color:var(--warn)}

.sec{background:var(--bg2);border:1px solid var(--b);border-radius:10px;margin-bottom:12px;overflow:hidden}
.sec-h{padding:10px 14px;border-bottom:1px solid var(--b);display:flex;justify-content:space-between;align-items:center;font-size:14px;font-weight:600}
.sec-b{padding:10px 14px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:7px 8px;color:var(--t2);font-size:9px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--b);font-weight:700;background:var(--bg3)}
td{padding:7px 8px;border-bottom:1px solid var(--b)}
tr:hover td{background:rgba(59,130,246,.02)}
.btn{padding:4px 10px;border-radius:5px;font-size:11px;font-weight:600;border:none;cursor:pointer;background:linear-gradient(135deg,var(--a),var(--a2));color:#fff}
.btn:hover{opacity:.9}
.btn-g{background:var(--bg3);color:var(--t2);border:1px solid var(--b)}
.btn-g:hover{color:var(--t)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:700px){.row2{grid-template-columns:1fr}}
.foot{position:fixed;bottom:0;left:0;right:0;background:var(--bg2);border-top:1px solid var(--b);padding:8px 20px;display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--t2)}
.hidden{display:none}
</style></head><body>

<div class="hdr">
  <div><h1>SuperMegaBot Command Center</h1><div class="sub">Ein Dashboard. Alle Systeme.</div></div>
  <div class="time"><span class="live"></span>${d.now}</div>
</div>

<div class="wrap">

<div class="tabs">
  <div class="tab on" onclick="show('dash')">Dashboard</div>
  <div class="tab" onclick="show('svc')">Services</div>
  <div class="tab" onclick="show('bot')">Bots</div>
</div>

<!-- DASHBOARD -->
<div id="dash" class="page">
  <div class="grid">
    <div class="card">
      <div class="card-top"><div><div class="card-v" style="color:${mc}">${d.mem.pct}%</div><div class="card-l">RAM</div></div></div>
      <div class="bar"><div class="bar-f" style="width:${d.mem.pct}%;background:${mc}"></div></div>
      <div class="meta"><span>${d.mem.used}/${d.mem.total} GB</span></div>
    </div>
    <div class="card">
      <div class="card-top"><div><div class="card-v" style="color:${cc}">${d.cpu}%</div><div class="card-l">CPU</div></div></div>
      <div class="bar"><div class="bar-f" style="width:${Math.min(d.cpu,100)}%;background:${cc}"></div></div>
      <div class="meta"><span>${os.cpus().length} Cores</span></div>
    </div>
    <div class="card">
      <div class="card-top"><div><div class="card-v" style="color:${dc}">${d.disk}%</div><div class="card-l">DISK</div></div></div>
      <div class="bar"><div class="bar-f" style="width:${d.disk}%;background:${dc}"></div></div>
      <div class="meta"><span>Macintosh HD</span></div>
    </div>
    <div class="card">
      <div class="card-top"><div><div class="card-v" style="color:var(--a)">${ft(d.uptime)}</div><div class="card-l">UPTIME</div></div></div>
      <div class="meta"><span>${d.bots.filter(b=>b.status==='running').length}/${d.bots.length} active</span></div>
    </div>
  </div>

  <div class="row2">
    <div class="sec">
      <div class="sec-h">Alerts</div>
      <div class="sec-b">
        ${d.alerts.length===0?'<div class="alert ok">System OK - Keine Warnungen</div>':d.alerts.map(a=>`<div class="alert ${a.t}"><strong>${a.t.toUpperCase()}</strong> - ${a.text}</div>`).join('')}
      </div>
    </div>
    <div class="sec">
      <div class="sec-h">Quick Actions</div>
      <div class="sec-b" style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" onclick="act('/api/restart-watchdog')">Restart Watchdog</button>
        <button class="btn" onclick="act('/api/restart-bots')">Restart Bots</button>
        <button class="btn" onclick="act('/api/cleanup')">Run Cleanup</button>
        <button class="btn btn-g" onclick="location.reload()">Refresh</button>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sec-h">Watchdogs</div>
    <div class="sec-b">
      <table><thead><tr><th>Label</th><th>PID</th><th>Status</th></tr></thead><tbody>
        ${d.wds.map(w=>`<tr><td><strong>${w.label.replace('com.supermegabot.','')}</strong></td><td>${w.pid}</td><td>${badge(w.code)}</td></tr>`).join('')}
        ${d.wds.length===0?'<tr><td colspan="3" style="text-align:center;color:var(--t2)">Keine Watchdogs gefunden</td></tr>':''}
      </tbody></table>
    </div>
  </div>
</div>

<!-- SERVICES -->
<div id="svc" class="page hidden">
  <div class="sec">
    <div class="sec-h">System Services</div>
    <div class="sec-b">
      <table><thead><tr><th>Service</th><th>PID</th><th>Status</th><th>Action</th></tr></thead><tbody>
        ${d.svcs.map(s=>`<tr><td><strong>${s.name}</strong></td><td>${s.pid}</td><td>${badge(s.code)}</td><td><button class="btn btn-g" onclick="act('/api/toggle/${s.name}')">${s.code==='0'?'Stop':'Start'}</button></td></tr>`).join('')}
      </tbody></table>
    </div>
  </div>
</div>

<!-- BOTS -->
<div id="bot" class="page hidden">
  <div class="sec">
    <div class="sec-h">Bot Status</div>
    <div class="sec-b">
      <table><thead><tr><th>Bot</th><th>Status</th><th>PID</th></tr></thead><tbody>
        ${d.bots.map(b=>`<tr><td><strong>${b.name}</strong></td><td>${badge(b.status)}</td><td>${b.pid}</td></tr>`).join('')}
      </tbody></table>
    </div>
  </div>
</div>

</div>

<div class="foot"><span>Auto-Refresh alle 5s</span><span>http://localhost:${PORT}</span></div>

<script>
function show(id){ document.querySelectorAll('.page').forEach(p=>p.classList.add('hidden')); document.getElementById(id).classList.remove('hidden'); document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on')); event.target.classList.add('on'); }
function act(url){ fetch(url).then(r=>r.text()).then(t=>{ alert(t); location.reload(); }).catch(e=>alert('Error: '+e.message)); }
setInterval(()=>location.reload(),5000);
</script>
</body></html>`;
}

const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-cache');

  if (req.url === '/' || req.url === '/index.html') {
    try { res.writeHead(200, {'Content-Type': 'text/html'}); res.end(await html()); }
    catch(e) { res.writeHead(500); res.end('Error: '+e.message); }
  }
  else if (req.url === '/api/status') {
    try { const d = await getData(); res.writeHead(200, {'Content-Type': 'application/json'}); res.end(JSON.stringify(d)); }
    catch(e) { res.writeHead(500); res.end(JSON.stringify({error: e.message})); }
  }
  else if (req.url === '/api/restart-watchdog') {
    try {
      await run('launchctl bootout gui/$(id -u)/com.supermegabot.watchdog 2>/dev/null; sleep 1; launchctl bootstrap gui/$(id -u) ~/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/com.supermegabot.watchdog.plist');
      res.writeHead(200); res.end('Watchdog restarted');
    } catch(e) { res.writeHead(500); res.end('Error: '+e.message); }
  }
  else if (req.url === '/api/restart-bots') {
    try {
      await run('launchctl bootout gui/$(id -u)/com.supermegabot.bot-system 2>/dev/null; sleep 1; launchctl bootstrap gui/$(id -u) ~/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/com.supermegabot.bot-system.plist');
      res.writeHead(200); res.end('Bots restarted');
    } catch(e) { res.writeHead(500); res.end('Error: '+e.message); }
  }
  else if (req.url === '/api/cleanup') {
    try {
      await run('pkill -f "Comet.app" 2>/dev/null; pkill -f "Visual Studio Code" 2>/dev/null');
      res.writeHead(200); res.end('Cleanup done - RAM-heavy apps closed');
    } catch(e) { res.writeHead(500); res.end('Error: '+e.message); }
  }
  else if (req.url.startsWith('/api/toggle/')) {
    const svc = req.url.replace('/api/toggle/', '');
    try {
      const out = await run(`launchctl list | grep "com.supermegabot.${svc}" | head -1`);
      const parts = out.trim().split(/\s+/);
      if (parts[1] === '0') {
        await run(`launchctl bootout gui/$(id -u)/com.supermegabot.${svc}`);
        res.writeHead(200); res.end(`${svc} stopped`);
      } else {
        await run(`launchctl bootstrap gui/$(id -u) ~/supermegabot-windsurf-agents/CascadeProjects/windsurf-project/com.supermegabot.${svc}.plist`);
        res.writeHead(200); res.end(`${svc} started`);
      }
    } catch(e) { res.writeHead(500); res.end('Error: '+e.message); }
  }
  else { res.writeHead(404); res.end('Not found'); }
});

server.listen(PORT, () => console.log(`Command Center http://localhost:${PORT}`));
