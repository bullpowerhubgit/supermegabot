import http from 'http';
import { execSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import gcpConfig from './lib/gcp-config.js';

const PORT = 9999;
const GCP_PROJECT_ID = gcpConfig.projectId;
const GCP_APIS = gcpConfig.apiList;

function getPM2Status() {
  try {
    const output = execSync('pm2 jlist 2>/dev/null', { encoding: 'utf8', timeout: 5000 });
    return JSON.parse(output).map(p => ({
      name: p.name,
      status: p.pm2_env.status,
      pid: p.pid,
      restarts: p.pm2_env.restart_time,
      memory: p.monit ? p.monit.memory : 0,
      cpu: p.monit ? p.monit.cpu : 0
    }));
  } catch { return []; }
}

function getWatchdogStatus() {
  try {
    const pidfile = '/tmp/supermegabot-watchdog.pid';
    if (fs.existsSync(pidfile)) {
      const pid = fs.readFileSync(pidfile, 'utf8').trim();
      try { execSync(`ps -p ${pid}`, { stdio: 'ignore' }); return { running: true, pid }; } catch { return { running: false }; }
    }
    return { running: false };
  } catch { return { running: false }; }
}

function getDeepScanStatus() {
  try {
    const pidfile = '/tmp/supermegabot-deepscan.pid';
    if (fs.existsSync(pidfile)) {
      const pid = fs.readFileSync(pidfile, 'utf8').trim();
      try { execSync(`ps -p ${pid}`, { stdio: 'ignore' }); return { running: true, pid }; } catch { return { running: false }; }
    }
    return { running: false };
  } catch { return { running: false }; }
}

function getSystemStats() {
  return {
    totalmem: Math.round(os.totalmem() / 1024 / 1024),
    freemem: Math.round(os.freemem() / 1024 / 1024),
    usedmem: Math.round((os.totalmem() - os.freemem()) / 1024 / 1024),
    percent: Math.round(((os.totalmem() - os.freemem()) / os.totalmem()) * 100),
    uptime: Math.round(os.uptime()),
    loadavg: os.loadavg(),
    cpus: os.cpus().length
  };
}

function getStatusJSON() {
  return JSON.stringify({
    timestamp: new Date().toISOString(),
    system: getSystemStats(),
    pm2: getPM2Status(),
    watchdog: getWatchdogStatus(),
    deepscan: getDeepScanStatus()
  });
}

const HTML = `<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>SuperMegaBot Monitor</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0a0a0f; color:#e0e0e0; padding:24px; }
.header { display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; padding-bottom:16px; border-bottom:1px solid #1e1e2e; }
.header h1 { font-size:24px; font-weight:600; letter-spacing:-0.5px; }
.live-dot { width:8px; height:8px; border-radius:50%; background:#00ff88; display:inline-block; animation:pulse 2s infinite; margin-right:8px; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:24px; }
.card { background:#13131f; border-radius:12px; padding:20px; border:1px solid #1e1e2e; transition:border-color .2s; }
.card:hover { border-color:#2a2a3e; }
.card-title { font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#6e6e8a; margin-bottom:12px; font-weight:500; }
.metric { display:flex; justify-content:space-between; margin:8px 0; }
.metric-label { color:#8e8ea8; font-size:13px; }
.metric-value { font-size:14px; font-weight:500; font-variant-numeric:tabular-nums; }
.status-online { color:#00ff88; } .status-offline { color:#ff5555; } .status-warn { color:#ffaa00; }
.ram-bar { height:8px; border-radius:4px; background:#1e1e2e; overflow:hidden; margin-top:8px; }
.ram-fill { height:100%; border-radius:4px; transition:width .5s; }
.ram-fill.good { background:#00ff88; } .ram-fill.warn { background:#ffaa00; } .ram-fill.critical { background:#ff5555; }
.service-row { display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-bottom:1px solid #1e1e2e; }
.service-row:last-child { border-bottom:none; }
.service-name { font-size:14px; font-weight:500; }
.service-badge { font-size:11px; padding:3px 10px; border-radius:20px; font-weight:600; }
.badge-online { background:rgba(0,255,136,.12); color:#00ff88; }
.badge-offline { background:rgba(255,85,85,.12); color:#ff5555; }
.badge-errored { background:rgba(255,170,0,.12); color:#ffaa00; }
.footer { text-align:center; margin-top:24px; font-size:12px; color:#4a4a5e; }
.refresh-btn { background:#1e1e2e; border:1px solid #2a2a3e; color:#e0e0e0; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:13px; }
.refresh-btn:hover { background:#2a2a3e; }
</style></head><body>
<div class="header"><h1><span class="live-dot"></span>SuperMegaBot Monitor</h1><button class="refresh-btn" onclick="loadData()">Refresh</button></div>
<div class="grid">
  <div class="card"><div class="card-title">System</div>
    <div class="metric"><span class="metric-label">RAM</span><span class="metric-value" id="ram-text">...</span></div>
    <div class="ram-bar"><div class="ram-fill good" id="ram-bar" style="width:0%"></div></div>
    <div class="metric"><span class="metric-label">CPU Cores</span><span class="metric-value" id="cpu-cores">...</span></div>
    <div class="metric"><span class="metric-label">Load</span><span class="metric-value" id="load">...</span></div>
    <div class="metric"><span class="metric-label">Uptime</span><span class="metric-value" id="uptime">...</span></div>
  </div>
  <div class="card"><div class="card-title">Services</div>
    <div class="metric"><span class="metric-label">PM2 Apps</span><span class="metric-value status-online" id="pm2-count">...</span></div>
    <div class="metric"><span class="metric-label">Watchdog</span><span class="metric-value" id="wd-status">...</span></div>
    <div class="metric"><span class="metric-label">DeepScan</span><span class="metric-value" id="ds-status">...</span></div>
  </div>
</div>
<div class="card" style="margin-bottom:16px"><div class="card-title">PM2 Services</div><div id="pm2-list">...</div></div>
<div class="footer">SuperMegaBot Monitor v1.0 &middot; Auto-refresh every 5s</div>
<script>
async function loadData(){
  try{
    const res=await fetch('/api/status'); const data=await res.json();
    document.getElementById('ram-text').textContent=data.system.usedmem+'MB / '+data.system.totalmem+'MB ('+data.system.percent+'%)';
    const bar=document.getElementById('ram-bar'); bar.style.width=data.system.percent+'%';
    bar.className='ram-fill '+(data.system.percent<70?'good':data.system.percent<85?'warn':'critical');
    document.getElementById('cpu-cores').textContent=data.system.cpus;
    document.getElementById('load').textContent=data.system.loadavg.map(x=>x.toFixed(2)).join(' / ');
    const u=data.system.uptime; document.getElementById('uptime').textContent=Math.floor(u/3600)+'h '+Math.floor((u%3600)/60)+'m';
    document.getElementById('pm2-count').textContent=data.pm2.length+' online';
    const wd=document.getElementById('wd-status'); wd.textContent=data.watchdog.running?'Running (PID '+data.watchdog.pid+')':'Stopped'; wd.className='metric-value '+(data.watchdog.running?'status-online':'status-offline');
    const ds=document.getElementById('ds-status'); ds.textContent=data.deepscan.running?'Running (PID '+data.deepscan.pid+')':'Stopped'; ds.className='metric-value '+(data.deepscan.running?'status-online':'status-offline');
    const list=document.getElementById('pm2-list');
    list.innerHTML=data.pm2.map(p=>{const cls=p.status==='online'?'badge-online':p.status==='errored'?'badge-errored':'badge-offline';return'<div class="service-row"><span class="service-name">'+p.name+'</span><span class="service-badge '+cls+'">'+p.status+'</span></div>';}).join('')||'<div style="color:#4a4a5e;padding:10px 0">No PM2 processes</div>';
  }catch(e){console.error('Load failed:',e);}
}
loadData(); 
 setInterval(loadData,5000);
</script></body></html>`;

const server = http.createServer((req, res) => {
  if (req.url === '/api/status') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(getStatusJSON());
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(HTML);
  }
});

server.listen(PORT, () => {
  // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // // console.debug('SuperMegaBot Monitor: http://localhost:' + PORT);
});
