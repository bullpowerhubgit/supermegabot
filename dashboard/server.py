#!/usr/bin/env python3
"""SuperMegaBot Dashboard Server - Port 8888"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SERVER_START_TIME = time.time()

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))
_HOME_PATH = str(Path.home())
if _HOME_PATH not in sys.path:
    sys.path.append(_HOME_PATH)

from aiohttp import web
import aiohttp

# Self-Learner integration
try:
    from self_learner_core import SelfLearner
    _self_learner = SelfLearner("supermegabot", telegram_notify=True)
    _self_learner.load_learned_skills()
except Exception:
    _self_learner = None

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    # fallback: manual parse
    _env_file = BASE_DIR / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

PORT = int(os.getenv("PORT") or os.getenv("DASHBOARD_PORT", "8888"))

log = logging.getLogger("Dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# In-memory cache: {key: (timestamp, data)}
# ---------------------------------------------------------------------------
_cache: dict = {}

def _cache_get(key: str, ttl: int):
    """Return cached value if still fresh, else None."""
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None

def _cache_set(key: str, data):
    _cache[key] = (time.time(), data)

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Service definitions for Start/Stop control
# ---------------------------------------------------------------------------

_HOME = Path.home()

def _ext(env_var: str, default_rel: str) -> str:
    """Gibt Pfad aus Env-Var zurück, sonst HOME/default_rel."""
    return os.getenv(env_var, str(_HOME / default_rel))

SERVICES = [
    {"id": "dashboard", "name": "SuperMegaBot", "port": 8888,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 dashboard/server.py >> /tmp/supermegabot.log 2>&1 &",
     "pattern": "dashboard/server.py", "icon": "🤖"},
    {"id": "rudibot_army", "name": "RudiBot Army", "port": 0,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 rudibot-army/army_commander.py >> /tmp/rudibot-army.log 2>&1 &",
     "pattern": "army_commander.py", "icon": "🪖"},
    {"id": "mega_orchestrator", "name": "Mega Orchestrator", "port": 0,
     "start_cmd": f"cd {BASE_DIR} && nohup python3 core/mega_orchestrator.py >> /tmp/mega-orchestrator.log 2>&1 &",
     "pattern": "mega_orchestrator.py", "icon": "🧩"},
    {"id": "telegram_bot", "name": "Telegram Bot", "port": 3200,
     "start_cmd": f"cd {_ext('TELEGRAM_BOT_DIR','telegram-automation-bot')} && nohup node server.js >> /tmp/telegram-bot.log 2>&1 &",
     "pattern": "telegram-automation-bot.*server.js", "icon": "✈️"},
    {"id": "cratorhub", "name": "CreatorHub", "port": 3000,
     "start_cmd": f"cd {_ext('DIGIFABRIK_DIR','digifabrik')} && nohup npx tsx server.ts >> /tmp/cratorhub.log 2>&1 &",
     "pattern": "digifabrik.*server", "icon": "🎨"},
    {"id": "ollama", "name": "Ollama LLM", "port": 11434,
     "start_cmd": "ollama serve >> /tmp/ollama.log 2>&1 &",
     "pattern": "ollama serve", "icon": "🧠"},
    {"id": "openclaw", "name": "OpenClaw Gateway", "port": 18789,
     "start_cmd": "openclaw gateway run",
     "pattern": "openclaw", "icon": "🦞"},
    {"id": "windsurf_shopify_suite", "name": "Shopify Webhook Suite", "port": 3001,
     "start_cmd": f"cd {_ext('SHOPIFY_SUITE_DIR','windsurf-shopify-suite')} && nohup npm start >> /tmp/windsurf-shopify-suite.log 2>&1 &",
     "pattern": "windsurf-shopify-suite", "icon": "🛒"},
    {"id": "windsurf_telegram_bot", "name": "Windsurf Telegram Bot", "port": 8000,
     "start_cmd": f"cd {_ext('WS_TELEGRAM_DIR','windsurf-telegram-bot')} && nohup npm start >> /tmp/windsurf-telegram-bot.log 2>&1 &",
     "pattern": "windsurf-telegram-bot.*index.js", "icon": "🤖"},
    {"id": "shopify_ai_suite", "name": "Shopify AI Suite (Railway)", "port": 0,
     "start_cmd": "echo 'Deployed on Railway'",
     "pattern": "RAILWAY_REMOTE",
     "url": "https://shopify-suite-v2-production.up.railway.app",
     "health_url": "https://shopify-suite-v2-production.up.railway.app/health",
     "icon": "🛍️"},
    {"id": "windsurf_shopify", "name": "Windsurf API Gateway", "port": 8080,
     "start_cmd": f"cd {_ext('API_GATEWAY_DIR','windsurf-api-gateway')} && nohup node src/index.js >> /tmp/windsurf-api-gateway.log 2>&1 &",
     "pattern": "windsurf-api-gateway.*index.js", "icon": "🌊"},
    {"id": "windsurf_autoheal", "name": "Windsurf Auto-Heal", "port": 9000,
     "start_cmd": f"cd {_ext('AUTO_HEAL_DIR','windsurf-auto-heal')} && nohup npm start >> /tmp/windsurf-autoheal.log 2>&1 &",
     "pattern": "windsurf-auto-heal.*index.js", "icon": "🏥"},
    {"id": "password_sync", "name": "Password Sync", "port": 3005,
     "start_cmd": f"cd {_ext('PASSWORD_SYNC_DIR','password-sync-suite/web-app')} && PORT=3005 nohup npm start >> /tmp/password-sync.log 2>&1 &",
     "pattern": "password-sync-suite.*server.js", "icon": "🔐"},
    {"id": "rudibot_eternal", "name": "RudiBot Eternal", "port": 0,
     "start_cmd": f"cd {_ext('ETERNAL_BOT_DIR','rudibot-eternal')} && nohup python3 immortal_bot.py >> /tmp/rudibot-eternal.log 2>&1 &",
     "pattern": "immortal_bot.py", "icon": "♾️"},
    {"id": "kivo", "name": "KIVO Voice", "port": 0,
     "start_cmd": f"cd {_ext('KIVO_DIR','kivo')} && nohup python3 kivo.py >> /tmp/kivo.log 2>&1 &",
     "pattern": "kivo.py", "icon": "🎙️"},
]

# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

_INDEX_HTML = Path(__file__).parent / 'index.html'


# ══════════════════════════════════════════════════════════════════════════════
# REVENUE AUTOPILOT DASHBOARD HTML
# ══════════════════════════════════════════════════════════════════════════════
_REVENUE_AUTOPILOT_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>💰 Revenue Autopilot — SuperMegaBot</title>
<style>
  :root{--green:#00d4aa;--red:#ff4757;--yellow:#ffa502;--blue:#1e90ff;--dark:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--dark);color:var(--text);min-height:100vh}
  header{background:linear-gradient(135deg,#1a1f2e,#0d1117);border-bottom:1px solid var(--border);padding:18px 24px;display:flex;align-items:center;gap:12px}
  header h1{font-size:1.4rem;font-weight:700}header span{font-size:.85rem;color:var(--muted)}
  .badge{background:#00d4aa22;color:var(--green);border:1px solid var(--green);border-radius:20px;padding:3px 10px;font-size:.75rem;font-weight:600}
  .container{padding:20px 24px;max-width:1600px;margin:0 auto}
  .grid-4{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-bottom:24px}
  .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
  .grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:24px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
  .card h2{font-size:.8rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}
  .stat{font-size:2rem;font-weight:800;color:var(--text)}
  .stat-sub{font-size:.8rem;color:var(--muted);margin-top:4px}
  .green{color:var(--green)} .red{color:var(--red)} .yellow{color:var(--yellow)} .blue{color:var(--blue)}
  .btn{display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border-radius:8px;border:none;font-size:.85rem;font-weight:600;cursor:pointer;transition:.2s}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .btn-green{background:#00d4aa22;color:var(--green);border:1px solid var(--green)}
  .btn-green:hover:not(:disabled){background:#00d4aa44}
  .btn-red{background:#ff475722;color:var(--red);border:1px solid var(--red)}
  .btn-red:hover:not(:disabled){background:#ff475744}
  .btn-blue{background:#1e90ff22;color:var(--blue);border:1px solid var(--blue)}
  .btn-blue:hover:not(:disabled){background:#1e90ff44}
  .btn-yellow{background:#ffa50222;color:var(--yellow);border:1px solid var(--yellow)}
  .btn-yellow:hover:not(:disabled){background:#ffa50244}
  .btn-solid{background:var(--green);color:#000;font-weight:700}
  .btn-solid:hover:not(:disabled){background:#00b899}
  .actions{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}
  table{width:100%;border-collapse:collapse;font-size:.85rem}
  th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);color:var(--muted);font-weight:600;font-size:.75rem;text-transform:uppercase}
  td{padding:10px 12px;border-bottom:1px solid #21262d}
  tr:hover td{background:#1c2128}
  .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}
  .tag-green{background:#00d4aa22;color:var(--green)}
  .tag-red{background:#ff475722;color:var(--red)}
  .tag-yellow{background:#ffa50222;color:var(--yellow)}
  .tag-blue{background:#1e90ff22;color:var(--blue)}
  input,select{background:#21262d;border:1px solid var(--border);border-radius:6px;color:var(--text);padding:8px 12px;font-size:.85rem;width:100%}
  input:focus,select:focus{outline:none;border-color:var(--green)}
  .form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
  label{font-size:.8rem;color:var(--muted);margin-bottom:4px;display:block}
  .flash-msg{padding:12px 16px;border-radius:8px;font-size:.85rem;margin-bottom:16px;display:none}
  .flash-msg.show{display:block}
  .flash-ok{background:#00d4aa22;color:var(--green);border:1px solid #00d4aa44}
  .flash-err{background:#ff475722;color:var(--red);border:1px solid #ff475744}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid currentColor;border-top-color:transparent;border-radius:50%;animation:spin .6s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .section-title{font-size:1.1rem;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:8px}
  .empty{color:var(--muted);font-style:italic;padding:20px;text-align:center}
  .progress-bar{height:6px;background:#21262d;border-radius:3px;overflow:hidden;margin-top:6px}
  .progress-fill{height:100%;border-radius:3px;background:var(--green)}
  .share-box{background:#21262d;border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;font-size:.9rem;word-break:break-all;color:var(--green);margin-top:8px}
  @media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr}.form-row{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div style="font-size:1.8rem">💰</div>
  <div>
    <h1>Revenue Autopilot</h1>
    <span>SuperMegaBot · Shopify Automation Suite</span>
  </div>
  <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
    <span class="badge" id="live-badge">⚡ LIVE</span>
    <button class="btn btn-green" onclick="loadAll()">🔄 Refresh</button>
  </div>
</header>

<div class="container">

  <!-- Flash message -->
  <div class="flash-msg" id="flash"></div>

  <!-- ── KPI Cards ── -->
  <div class="grid-4" id="kpi-grid">
    <div class="card"><h2>💶 Heute</h2><div class="stat green" id="kpi-today">—</div><div class="stat-sub" id="kpi-today-orders">—</div></div>
    <div class="card"><h2>📅 7 Tage</h2><div class="stat" id="kpi-7d">—</div><div class="stat-sub" id="kpi-7d-orders">—</div></div>
    <div class="card"><h2>📆 30 Tage</h2><div class="stat" id="kpi-30d">—</div><div class="stat-sub" id="kpi-30d-orders">—</div></div>
    <div class="card"><h2>🛒 Offene Carts</h2><div class="stat yellow" id="kpi-carts">—</div><div class="stat-sub" id="kpi-carts-value">potentieller Umsatz</div></div>
    <div class="card"><h2>📦 Offene Bestellungen</h2><div class="stat blue" id="kpi-pending">—</div><div class="stat-sub" id="kpi-pending-value">—</div></div>
    <div class="card"><h2>⚠️ Wenig Lager</h2><div class="stat red" id="kpi-inventory">—</div><div class="stat-sub">≤ 5 Stück</div></div>
    <div class="card"><h2>💡 Ø Bestellwert (30T)</h2><div class="stat" id="kpi-aov">—</div><div class="stat-sub">Average Order Value</div></div>
    <div class="card"><h2>🎯 Umsatz gestern</h2><div class="stat" id="kpi-yesterday">—</div><div class="stat-sub" id="kpi-yesterday-orders">—</div></div>
  </div>

  <div class="grid-2">

    <!-- ── Aktionen ── -->
    <div class="card">
      <div class="section-title">⚡ Schnell-Aktionen</div>

      <!-- Abandoned Cart Recovery -->
      <div style="margin-bottom:20px">
        <div style="font-size:.85rem;color:var(--muted);margin-bottom:8px">🛒 Abandoned Cart Recovery</div>
        <div class="actions">
          <button class="btn btn-yellow" onclick="recoverCarts(24)">Letzte 24h</button>
          <button class="btn btn-yellow" onclick="recoverCarts(48)">Letzte 48h</button>
          <button class="btn btn-red" onclick="recoverCarts(72)">Letzte 72h</button>
        </div>
      </div>

      <!-- Flash Sale -->
      <div style="margin-bottom:20px">
        <div style="font-size:.85rem;color:var(--muted);margin-bottom:8px">🔥 Flash Sale erstellen</div>
        <div class="form-row">
          <div><label>Rabatt %</label><input id="fs-pct" type="number" value="20" min="5" max="80"></div>
          <div><label>Dauer (Std)</label><input id="fs-hours" type="number" value="24" min="1" max="168"></div>
        </div>
        <div style="margin-bottom:8px"><label>Code (leer = auto)</label><input id="fs-code" placeholder="z.B. SOMMER20"></div>
        <div style="margin-bottom:12px"><label>Mindestbestellwert (€)</label><input id="fs-min" type="number" value="0" min="0"></div>
        <button class="btn btn-solid" onclick="createFlashSale()" style="width:100%">🔥 Flash Sale starten</button>
        <div id="fs-result" class="share-box" style="display:none"></div>
      </div>

      <!-- Bulk Price -->
      <div style="margin-bottom:20px">
        <div style="font-size:.85rem;color:var(--muted);margin-bottom:8px">💲 Preise anpassen</div>
        <div class="form-row">
          <div><label>Methode</label>
            <select id="bp-method">
              <option value="percent">% Änderung</option>
              <option value="fixed_add">+ Fester Betrag (€)</option>
              <option value="fixed_set">Preis setzen (€)</option>
            </select>
          </div>
          <div><label>Wert</label><input id="bp-value" type="number" value="10" step="0.01"></div>
        </div>
        <div class="form-row">
          <div><label>Min Preis (€)</label><input id="bp-min" type="number" value="0"></div>
          <div><label>Max Preis (€)</label><input id="bp-max" type="number" value="9999"></div>
        </div>
        <button class="btn btn-blue" onclick="bulkPrice()" style="width:100%">💲 Alle Preise anpassen</button>
      </div>

      <!-- Auto Publish & AI Descriptions -->
      <div class="actions">
        <button class="btn btn-green" onclick="publishDrafts()" id="btn-publish">📢 Drafts veröffentlichen</button>
        <button class="btn btn-blue" onclick="aiDescriptions()" id="btn-ai">🤖 AI Beschreibungen (5)</button>
      </div>
    </div>

    <!-- ── Abandoned Carts Table ── -->
    <div class="card">
      <div class="section-title">🛒 Verlassene Warenkörbe <span id="carts-count" class="badge" style="font-size:.7rem"></span></div>
      <div id="carts-table"><div class="empty">Lade Daten…</div></div>
    </div>
  </div>

  <div class="grid-3">
    <!-- ── Top Sellers ── -->
    <div class="card">
      <div class="section-title">🏆 Top-Seller (30 Tage)</div>
      <div id="top-sellers"><div class="empty">Lade…</div></div>
    </div>

    <!-- ── Zero/Slow Sellers ── -->
    <div class="card">
      <div class="section-title">😴 Null-Verkäufe (aktive Produkte)</div>
      <div id="zero-sellers"><div class="empty">Lade…</div></div>
    </div>

    <!-- ── Upsell Pairs ── -->
    <div class="card">
      <div class="section-title">🔗 Zusammen gekauft (Upsell)</div>
      <div id="upsell-pairs"><div class="empty">Lade…</div></div>
    </div>
  </div>

  <!-- ── Low Inventory ── -->
  <div class="card" style="margin-bottom:24px">
    <div class="section-title">⚠️ Niedriger Lagerbestand (≤ 5 Stück)</div>
    <div id="inventory-table"><div class="empty">Lade…</div></div>
  </div>

</div>

<script>
const API = '';
const fmt = (v,c='EUR')=>new Intl.NumberFormat('de-DE',{style:'currency',currency:c}).format(v||0);

function flash(msg,ok=true){
  const el=document.getElementById('flash');
  el.className='flash-msg show '+(ok?'flash-ok':'flash-err');
  el.textContent=msg;
  setTimeout(()=>el.classList.remove('show'),5000);
}

function setBtn(id,loading){
  const b=document.getElementById(id);
  if(!b)return;
  b.disabled=loading;
  if(loading)b.dataset.orig=b.innerHTML;
  b.innerHTML=loading?'<span class="spinner"></span> Läuft…':b.dataset.orig;
}

async function api(path,method='GET',body=null){
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  const r=await fetch(API+path,opts);
  return r.json();
}

async function loadRevenue(){
  try{
    const d=await api('/api/revenue/dashboard');
    if(!d.ok)return;
    const r=d.revenue||{};
    document.getElementById('kpi-today').textContent=fmt(r.today?.revenue);
    document.getElementById('kpi-today-orders').textContent=`${r.today?.orders||0} Bestellungen`;
    document.getElementById('kpi-7d').textContent=fmt(r['7d']?.revenue);
    document.getElementById('kpi-7d-orders').textContent=`${r['7d']?.orders||0} Bestellungen`;
    document.getElementById('kpi-30d').textContent=fmt(r['30d']?.revenue);
    document.getElementById('kpi-30d-orders').textContent=`${r['30d']?.orders||0} Bestellungen`;
    document.getElementById('kpi-yesterday').textContent=fmt(r.yesterday?.revenue);
    document.getElementById('kpi-yesterday-orders').textContent=`${r.yesterday?.orders||0} Bestellungen`;
    document.getElementById('kpi-aov').textContent=fmt(r['30d']?.aov);
    document.getElementById('kpi-pending').textContent=r.pending_orders||0;
    document.getElementById('kpi-pending-value').textContent=fmt(r.pending_revenue)+' ausstehend';

    const carts=d.abandoned_carts||[];
    document.getElementById('kpi-carts').textContent=carts.length;
    const cartVal=carts.reduce((s,c)=>s+c.total,0);
    document.getElementById('kpi-carts-value').textContent=fmt(cartVal)+' potentiell';
    document.getElementById('carts-count').textContent=carts.length;

    const inv=d.low_inventory||[];
    document.getElementById('kpi-inventory').textContent=inv.length;

    renderCarts(carts);
    renderInventory(inv);
  }catch(e){console.error(e)}
}

function renderCarts(carts){
  const el=document.getElementById('carts-table');
  if(!carts.length){el.innerHTML='<div class="empty">Keine offenen Warenkörbe 🎉</div>';return;}
  el.innerHTML=`<table><thead><tr><th>E-Mail</th><th>Artikel</th><th>Wert</th><th>Erstellt</th></tr></thead><tbody>
    ${carts.slice(0,10).map(c=>`<tr>
      <td>${c.email||'<span style="color:var(--muted)">anonym</span>'}</td>
      <td><small>${c.product_titles.slice(0,2).join(', ')||'—'}</small></td>
      <td class="yellow">${fmt(c.total)}</td>
      <td><small>${new Date(c.created_at).toLocaleDateString('de')}</small></td>
    </tr>`).join('')}
  </tbody></table>`;
}

function renderInventory(items){
  const el=document.getElementById('inventory-table');
  if(!items.length){el.innerHTML='<div class="empty">Lager OK — kein Handlungsbedarf</div>';return;}
  el.innerHTML=`<table><thead><tr><th>Produkt</th><th>SKU</th><th>Bestand</th><th>Preis</th></tr></thead><tbody>
    ${items.map(i=>`<tr>
      <td>${i.title}</td>
      <td><code style="color:var(--muted)">${i.sku||'—'}</code></td>
      <td><span class="tag ${i.inventory<=0?'tag-red':i.inventory<=2?'tag-yellow':'tag-blue'}">${i.inventory} Stk</span></td>
      <td>${fmt(i.price)}</td>
    </tr>`).join('')}
  </tbody></table>`;
}

async function loadPerformance(){
  try{
    const d=await api('/api/revenue/product-performance?days=30');
    if(!d.ok)return;
    const topEl=document.getElementById('top-sellers');
    if(d.top_sellers?.length){
      const maxR=d.top_sellers[0].revenue;
      topEl.innerHTML=d.top_sellers.slice(0,8).map((p,i)=>`
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:.85rem">
            <span>${i+1}. ${p.title.slice(0,30)}${p.title.length>30?'…':''}</span>
            <span class="green">${fmt(p.revenue)}</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${Math.round(p.revenue/maxR*100)}%"></div></div>
          <div style="font-size:.75rem;color:var(--muted)">${p.units_sold} Stk · ${p.orders} Bestellungen</div>
        </div>`).join('');
    }else{topEl.innerHTML='<div class="empty">Keine Verkäufe in 30 Tagen</div>';}

    const zeroEl=document.getElementById('zero-sellers');
    if(d.zero_sellers?.length){
      zeroEl.innerHTML=`<div style="color:var(--muted);font-size:.8rem;margin-bottom:8px">${d.zero_seller_count} Produkte ohne Verkauf</div>
        <table><thead><tr><th>Produkt</th><th>Preis</th></tr></thead><tbody>
        ${d.zero_sellers.slice(0,10).map(p=>`<tr>
          <td style="font-size:.82rem">${p.title.slice(0,35)}${p.title.length>35?'…':''}</td>
          <td>${fmt(p.price)}</td>
        </tr>`).join('')}</tbody></table>`;
    }else{zeroEl.innerHTML='<div class="empty">Alle Produkte haben Verkäufe 🎉</div>';}
  }catch(e){console.error(e)}
}

async function loadUpsell(){
  try{
    const d=await api('/api/revenue/upsell-pairs?limit=8');
    const el=document.getElementById('upsell-pairs');
    if(!d.pairs?.length){el.innerHTML='<div class="empty">Nicht genug Bestelldaten</div>';return;}
    el.innerHTML=d.pairs.map(p=>`
      <div style="border-bottom:1px solid var(--border);padding:10px 0">
        <div style="font-size:.82rem;font-weight:600">${p.product_a.slice(0,25)}…</div>
        <div style="font-size:.75rem;color:var(--muted)">➜ wird oft mit gekauft:</div>
        <div style="font-size:.82rem;color:var(--green)">${p.product_b.slice(0,25)}…</div>
        <span class="tag tag-blue">${p.bought_together}× zusammen</span>
      </div>`).join('');
  }catch(e){console.error(e)}
}

async function recoverCarts(hours){
  flash(`Starte Cart Recovery für letzte ${hours}h…`);
  const d=await api('/api/revenue/recover-carts','POST',{hours});
  if(d.ok)flash(`✅ ${d.emails_sent} Recovery-Emails gesendet · ${fmt(d.potential_revenue)} potentiell`);
  else flash('❌ Fehler: '+d.error,false);
}

async function createFlashSale(){
  const pct=parseInt(document.getElementById('fs-pct').value)||20;
  const hours=parseInt(document.getElementById('fs-hours').value)||24;
  const code=document.getElementById('fs-code').value.trim().toUpperCase();
  const min=parseFloat(document.getElementById('fs-min').value)||0;
  flash('Erstelle Flash Sale…');
  const d=await api('/api/revenue/flash-sale','POST',{discount_pct:pct,title:code||undefined,duration_hours:hours,min_purchase:min});
  const el=document.getElementById('fs-result');
  if(d.ok){
    el.style.display='block';
    el.textContent=d.share_message+'\n\nCode: '+d.code;
    flash(`✅ Flash Sale aktiv! Code: ${d.code} · ${pct}% für ${hours}h`);
  }else{el.style.display='none';flash('❌ '+d.error,false);}
}

async function bulkPrice(){
  const method=document.getElementById('bp-method').value;
  const value=parseFloat(document.getElementById('bp-value').value)||10;
  const min=parseFloat(document.getElementById('bp-min').value)||0;
  const max=parseFloat(document.getElementById('bp-max').value)||9999;
  const label=method==='percent'?`${value>0?'+':''}${value}%`:`${value>0?'+':''}${fmt(value)}`;
  if(!confirm(`Alle Preise um ${label} anpassen?\nPreisbereich: ${fmt(min)} – ${fmt(max)}`))return;
  flash('Passe Preise an…');
  const d=await api('/api/revenue/bulk-price','POST',{method,value,min_price:min,max_price:max});
  if(d.ok)flash(`✅ ${d.updated_variants} Varianten aktualisiert`);
  else flash('❌ '+d.error,false);
}

async function publishDrafts(){
  setBtn('btn-publish',true);
  flash('Veröffentliche Draft-Produkte…');
  const d=await api('/api/revenue/publish-drafts','POST');
  setBtn('btn-publish',false);
  if(d.ok)flash(`✅ ${d.published} Produkte veröffentlicht`);
  else flash('❌ '+d.error,false);
}

async function aiDescriptions(){
  setBtn('btn-ai',true);
  flash('Claude generiert SEO-Beschreibungen…');
  const d=await api('/api/revenue/ai-descriptions','POST',{limit:5,language:'de'});
  setBtn('btn-ai',false);
  if(d.ok)flash(`✅ ${d.updated} Beschreibungen aktualisiert`);
  else flash('❌ '+d.error,false);
}

async function loadAll(){
  await Promise.all([loadRevenue(),loadPerformance(),loadUpsell()]);
}

// Auto-refresh every 60 seconds
loadAll();
setInterval(loadAll,60000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# API Routes — existing handlers
# ---------------------------------------------------------------------------

async def handle_index(req):
    try:
        html = _INDEX_HTML.read_text(encoding="utf-8")
    except Exception:
        html = "<h1>Dashboard nicht gefunden</h1><p>dashboard/index.html fehlt</p>"
    return web.Response(text=html, content_type="text/html")


async def handle_chat(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        text = data.get("text") or data.get("message") or ""
        session_id = data.get("session_id", "dashboard")
        bot = req.app["bot"]
        response = await bot.process(text, session_id)
        return web.json_response({"ok": True, "response": response, "session_id": session_id})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bot_execute(req):
    """Telegram Hub Bridge → Dashboard CommandRouter.
    Called by telegram_hub_bridge.py for every incoming Telegram message.
    """
    try:
        data = await req.json()
        command = data.get("command", "").strip()
        session_id = data.get("session_id", "telegram")
        if not command:
            return web.json_response({"ok": False, "error": "command is required"}, status=400)
        bot = req.app["bot"]
        response = await bot.process(command, session_id)
        return web.json_response({"ok": True, "response": response})
    except Exception as e:
        log.error("handle_bot_execute error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_bot_commands(req):
    """Return all registered bot commands (for /commands meta-command in Telegram)."""
    try:
        bot = req.app["bot"]
        all_cmds = list(bot.router.routes.keys())
        slash_cmds = sorted(c for c in all_cmds if c.startswith("/"))
        other_cmds = sorted(c for c in all_cmds if not c.startswith("/"))
        return web.json_response({
            "ok": True,
            "total": len(all_cmds),
            "slash": slash_cmds,
            "all": slash_cmds + other_cmds,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_system(req):
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return web.json_response({
            "ok": True,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_used_gb": round(mem.used / 1024**3, 1),
            "memory_total_gb": round(mem.total / 1024**3, 1),
            "memory_percent": round(mem.percent, 1),
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_free_gb": round(disk.free / 1024**3, 1),
            "disk_percent": round(disk.percent, 1),
            "process_count": len(psutil.pids()),
        })
    except ImportError:
        return web.json_response({"ok": False, "error": "psutil not installed"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_services_legacy(req):
    """Legacy /api/services endpoint — kept for backward compat."""
    import socket
    service_list = [
        {"name": "SuperMegaBot Dashboard", "port": PORT},
        {"name": "Telegram-Automation-Bot", "port": 3200},
        {"name": "CreatorHub", "port": 3000},
        {"name": "Ollama", "port": 11434},
        {"name": "OpenClaw Gateway", "port": 18789},
        {"name": "Windsurf API Gateway", "port": 8080},
    ]
    for s in service_list:
        if s["port"] == PORT:
            s["ok"] = True
            continue
        try:
            sock = socket.create_connection(("localhost", s["port"]), timeout=1)
            sock.close()
            s["ok"] = True
        except Exception:
            s["ok"] = False
    return web.json_response({"services": service_list})


async def handle_trading_prices(req):
    try:
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        prices = await bot.get_quick_prices()
        return web.json_response({"ok": True, "prices": prices})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_trading_arbitrage(req):
    try:
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        opps = await bot.scan_quick()
        return web.json_response({"ok": True, "opportunities": opps})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_telegram_status(req):
    token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    return web.json_response({
        "ok": True,
        "configured": bool(token),
        "chat_id": TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", ""),
    })


async def handle_telegram_send(req):
    if not TELEGRAM_TOKEN:
        return web.json_response({"ok": False, "error": "No token configured"})
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        message = data.get("message", "")
        if not message:
            return web.json_response({"ok": False, "error": "message is required"}, status=400)
        chat_id = TELEGRAM_CHAT_ID
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(url, json={"chat_id": chat_id, "text": message}) as r:
                ok = r.status == 200
                return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_shopify_status(req):
    store = os.getenv("SHOPIFY_STORE_URL", "").strip().rstrip("/")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip().rstrip("/")

    if not token:
        return web.json_response({"ok": False, "error": "SHOPIFY_ACCESS_TOKEN nicht gesetzt"})

    # Build base URL: prefer explicit domain, fall back to SHOPIFY_STORE_URL
    if domain:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        base = domain
    elif store:
        if not store.startswith("http"):
            store = f"https://{store}"
        base = store
    else:
        return web.json_response({"ok": False, "error": "SHOPIFY_STORE_URL oder SHOPIFY_SHOP_DOMAIN nicht gesetzt"})

    api_version = os.getenv("SHOPIFY_API_VERSION", "2024-10")
    try:
        connector = aiohttp.TCPConnector(ssl=True, limit=5)
        timeout = aiohttp.ClientTimeout(total=10, connect=6)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as s:
            url = f"{base}/admin/api/{api_version}/shop.json"
            headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    d = await r.json()
                    shop = d.get("shop", {})
                    # Also fetch product + order counts
                    prod_url = f"{base}/admin/api/{api_version}/products/count.json"
                    order_url = f"{base}/admin/api/{api_version}/orders/count.json?status=any"
                    prod_count = order_count = "?"
                    try:
                        async with s.get(prod_url, headers=headers) as pr:
                            if pr.status == 200:
                                prod_count = (await pr.json()).get("count", "?")
                    except Exception:
                        pass
                    try:
                        async with s.get(order_url, headers=headers) as or_:
                            if or_.status == 200:
                                order_count = (await or_.json()).get("count", "?")
                    except Exception:
                        pass
                    return web.json_response({
                        "ok": True,
                        "store": shop.get("name", base),
                        "domain": shop.get("domain", ""),
                        "email": shop.get("email", ""),
                        "currency": shop.get("currency", ""),
                        "plan": shop.get("plan_display_name", ""),
                        "product_count": prod_count,
                        "order_count": order_count,
                    })
                elif r.status == 401:
                    return web.json_response({"ok": False, "error": "Token ungültig (401) — neu generieren"})
                elif r.status == 402:
                    return web.json_response({"ok": False, "error": "Shop gesperrt (402)"})
                else:
                    body = await r.text()
                    return web.json_response({"ok": False, "error": f"HTTP {r.status}: {body[:100]}"})
    except aiohttp.ClientConnectorError as e:
        return web.json_response({"ok": False, "error": f"DNS/Verbindung fehlgeschlagen: {e.host} — Shop-URL prüfen"})
    except aiohttp.ServerTimeoutError:
        return web.json_response({"ok": False, "error": "Timeout — Shopify nicht erreichbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_legacy(req):
    """Compatibility alias for older dashboards expecting /api/shopify."""
    return await handle_shopify_status(req)


async def handle_ollama_models(req):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{OLLAMA_BASE}/api/tags") as r:
                if r.status == 200:
                    data = await r.json()
                    models = [
                        {"name": m["name"], "size": f"{m.get('size', 0) // 1024//1024//1024:.1f}GB"}
                        for m in data.get("models", [])
                    ]
                    return web.json_response({"ok": True, "models": models})
                return web.json_response({"ok": False, "models": []})
    except Exception as e:
        return web.json_response({"ok": False, "models": [], "error": str(e)})


async def handle_autopilot_agents(req):
    try:
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        return web.json_response({"ok": True, "agents": ap.get_agent_list()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_autopilot_run(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        goal = data.get("goal", "")
        agent_id = data.get("agent_id") or None
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        if agent_id:
            result = await ap.run_task(goal, agent_id)
            return web.json_response({"ok": True, "results": [result]})
        else:
            results = await ap.run_autopilot_mode(goal)
            return web.json_response({"ok": True, "results": results})
    except Exception as e:
        log.error(f"AutoPilot error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_autopilot_logs(req):
    try:
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        return web.json_response({"ok": True, "logs": ap.get_logs(30)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_geheimwaffe_run(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        niche = data.get("niche", "General")
        from modules.geheimwaffe import run_full_automation
        result = await run_full_automation(niche)
        if "ok" not in result:
            result["ok"] = True
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_geheimwaffe_content(req):
    try:
        try:
            data = await req.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
        product = data.get("product", "")
        content_type = data.get("type", "listing")
        platform = data.get("platform", "tiktok")
        from modules.geheimwaffe import generate_product_listing, generate_social_content, generate_ad_copy
        if content_type == "listing":
            result = await generate_product_listing(product)
        elif content_type == "social":
            result = await generate_social_content(product, platform)
        elif content_type == "ads":
            result = await generate_ad_copy(product)
        else:
            return web.json_response({"ok": False, "error": "Unbekannter content_type"}, status=400)
        if "ok" not in result:
            result["ok"] = True
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_gmc(req):
    try:
        sys.path.insert(0, str(BASE_DIR))
        from modules.gmc_monitor import get_full_status
        status = await get_full_status()
        if "ok" not in status:
            status["ok"] = True
        return web.json_response(status)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_backup_status(req):
    backups = []
    extra_dirs = [d.strip() for d in os.getenv("BACKUP_EXTRA_DIRS", "").split(",") if d.strip()]
    backup_paths = [BASE_DIR / "data"] + [Path(d) for d in extra_dirs]
    for p in backup_paths:
        if p.exists():
            try:
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                backups.append({"path": str(p), "exists": True, "size_mb": round(size/1024/1024, 1)})
            except Exception:
                backups.append({"path": str(p), "exists": True})
    return web.json_response({"backups": backups, "count": len(backups)})


async def handle_backup_run(req):
    import shutil
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BASE_DIR / "data" / "backups" / ts
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE_DIR / ".env", backup_dir / "supermegabot.env")
        shutil.copy2(DATA_DIR / "memory.db", backup_dir / "memory.db")
        return web.json_response({"ok": True, "path": str(backup_dir)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_legacy(req):
    """Compatibility alias for older dashboards expecting /api/revenue."""
    return await handle_revenue_summary(req)


async def handle_analytics_legacy(req):
    """Compatibility alias for older dashboards expecting /api/analytics."""
    return await handle_revenue_analytics(req)


async def handle_kpis_legacy(req):
    """Compatibility alias for older dashboards expecting /api/kpis."""
    return await handle_revenue_summary(req)


# ---------------------------------------------------------------------------
# NEW API Routes
# ---------------------------------------------------------------------------

async def handle_mac_action(req):
    try:
        data = await req.json()
    except Exception:
        data = {}
    action = data.get("action", "")
    try:
        from modules.mac_controller import MacController
        mac = MacController()
        if action == "screenshot":
            result = await mac.take_screenshot()
        elif action == "notify":
            result = await mac.notify(data.get("title", "SuperMegaBot"), data.get("message", ""))
        elif action == "volume":
            result = await mac.set_volume(int(data.get("level", 50)))
        elif action == "lock":
            result = await mac.lock_screen()
        elif action == "sleep_display":
            result = await mac.sleep_display()
        elif action == "empty_trash":
            result = await mac.empty_trash()
        elif action == "open_url":
            result = await mac.open_url_safari(data.get("url", ""))
        elif action == "clipboard_get":
            result = await mac.get_clipboard()
        elif action == "system_info":
            result = await mac.get_system_info()
            return web.json_response({"ok": True, "result": result})
        elif action == "running_apps":
            result = await mac.list_running_apps()
            return web.json_response({"ok": True, "result": result})
        else:
            return web.json_response({"ok": False, "error": f"Unknown action: {action}"})
        return web.json_response({"ok": True, "result": str(result)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_agents_legacy(req):
    """Compatibility alias for older dashboards expecting /api/agents."""
    return await handle_autopilot_agents(req)


async def handle_chat_clear(req):
    """Delete stored conversation history for a session."""
    try:
        data = await req.json() if req.can_read_body else {}
        session_id = str(data.get("session_id", "dashboard")).strip() or "dashboard"
        deleted = req.app["bot"].memory.clear_history(session_id)
        return web.json_response({"ok": True, "session_id": session_id, "deleted": deleted})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_services_status(req):
    import socket
    result = []
    for svc in SERVICES:
        port_ok = False
        if svc.get("port", 0) > 0:
            try:
                sock = socket.create_connection(("localhost", svc["port"]), timeout=0.5)
                sock.close()
                port_ok = True
            except Exception:
                pass

        # Special case: Railway remote service — HTTP health check
        if svc["id"] == "shopify_ai_suite":
            try:
                import urllib.request
                urllib.request.urlopen(svc.get("health_url", svc.get("url", "")), timeout=5)
                port_ok = True
            except Exception:
                pass
            result.append({
                "id": svc["id"], "name": svc["name"], "port": svc["port"],
                "icon": svc["icon"], "ok": port_ok, "pid": None, "running": port_ok,
                "remote": True,
            })
            continue

        # Special case: mega_orchestrator is embedded in this process
        if svc["id"] == "mega_orchestrator":
            result.append({
                "id": svc["id"], "name": svc["name"], "port": svc["port"],
                "icon": svc["icon"], "ok": True, "pid": str(os.getpid()), "running": True,
                "note": "Eingebettet in Dashboard",
            })
            continue

        pid = None
        pattern = svc.get("pattern", "")
        if pattern and pattern != "RAILWAY_REMOTE":
            try:
                ps = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
                if ps.returncode == 0 and ps.stdout.strip():
                    pid = ps.stdout.strip().split('\n')[0]
            except Exception:
                pass

        result.append({
            "id": svc["id"], "name": svc["name"], "port": svc["port"],
            "icon": svc["icon"], "ok": port_ok, "pid": pid,
            "running": port_ok or bool(pid),
        })
    return web.json_response({"services": result})


async def handle_service_action(req):
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    action = data.get("action", "")
    svc_id = data.get("id", "")
    svc = next((s for s in SERVICES if s["id"] == svc_id), None)
    if not svc:
        return web.json_response({"ok": False, "error": f"Service {svc_id} not found"})
    try:
        if action in ("stop", "restart"):
            subprocess.run(["pkill", "-f", svc["pattern"]], capture_output=True)
            await asyncio.sleep(0.8)
        if action in ("start", "restart"):
            if svc["id"] == "dashboard":
                return web.json_response({"ok": False, "error": "Dashboard kann sich nicht selbst starten"})
            subprocess.Popen(svc["start_cmd"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(1.5)
        return web.json_response({"ok": True, "action": action, "service": svc["name"]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_service_start(req):
    """Startet einen Service (dedizierter Endpoint für /api/service/start)."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    svc_id = data.get("id", "")
    svc = next((s for s in SERVICES if s["id"] == svc_id), None)
    if not svc:
        return web.json_response({"ok": False, "error": f"Service {svc_id} not found"}, status=404)
    if svc["id"] == "dashboard":
        return web.json_response({"ok": False, "error": "Dashboard kann sich nicht selbst starten"}, status=400)
    try:
        subprocess.Popen(svc["start_cmd"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(1.5)
        return web.json_response({"ok": True, "action": "start", "service": svc["name"]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_service_stop(req):
    """Stoppt einen Service (dedizierter Endpoint für /api/service/stop)."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    svc_id = data.get("id", "")
    svc = next((s for s in SERVICES if s["id"] == svc_id), None)
    if not svc:
        return web.json_response({"ok": False, "error": f"Service {svc_id} not found"}, status=404)
    try:
        subprocess.run(["pkill", "-f", svc["pattern"]], capture_output=True)
        await asyncio.sleep(0.8)
        return web.json_response({"ok": True, "action": "stop", "service": svc["name"]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_logs(req):
    try:
        lines = []
        for lf in [BASE_DIR / "logs" / "supermegabot.log", Path("/tmp/supermegabot.log")]:
            if lf.exists():
                try:
                    content = lf.read_text(errors='replace').split('\n')
                    lines.extend(content[-60:])
                except Exception:
                    pass
        if not lines:
            lines = ["Keine Logs vorhanden — Bot läuft möglicherweise ohne Log-Datei"]
        return web.json_response({"ok": True, "lines": lines[-80:]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_logs_clear(req):
    """Clear the primary dashboard log files used by the legacy UI."""
    try:
        cleared = []
        for lf in [BASE_DIR / "logs" / "supermegabot.log", Path("/tmp/supermegabot.log")]:
            if lf.exists():
                lf.write_text("")
                cleared.append(str(lf))
        return web.json_response({"ok": True, "cleared": cleared})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_health(req):
    cached = _cache_get("system_health", 30)
    if cached is not None:
        # Always return fresh uptime
        cached = dict(cached)
        cached["uptime_seconds"] = round(time.time() - _SERVER_START_TIME, 1)
        return web.json_response(cached)
    result = {
        "status": "ok",
        "service": "supermegabot-dashboard",
        "port": PORT,
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
        "started_at": datetime.fromtimestamp(_SERVER_START_TIME, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shopify_domain": os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
        "bots": {
            "admin_bot": bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1")),
            "customer_bot": bool(os.getenv("TELEGRAM_BOT_TOKEN_2")),
        },
    }
    _cache_set("system_health", result)
    return web.json_response(result)


async def handle_status_legacy(req):
    """Compatibility alias for older dashboards expecting /api/status."""
    return await handle_status_full(req)


async def handle_metrics_legacy(req):
    """Compatibility alias for older dashboards expecting /api/metrics."""
    return await handle_system(req)


async def handle_status_full(req):
    """Full system status including all configured integrations."""
    import socket

    def _port_open(port: int) -> bool:
        try:
            sock = socket.create_connection(("localhost", port), timeout=1)
            sock.close()
            return True
        except Exception:
            return False

    # Ollama check
    ollama_ok = False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{os.getenv('OLLAMA_HOST', 'http://localhost:11434')}/api/tags") as r:
                ollama_ok = r.status == 200
    except Exception:
        pass

    return web.json_response({
        "status": "ok",
        "uptime_seconds": round(time.time() - _SERVER_START_TIME, 1),
        "telegram": {
            "admin_bot_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1")),
            "customer_bot_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN_2")),
            "chat_id_configured": bool(os.getenv("TELEGRAM_CHAT_ID")),
        },
        "shopify": {
            "configured": bool(os.getenv("SHOPIFY_SHOP_DOMAIN") and (os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN"))),
            "domain": os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
            "api_version": os.getenv("SHOPIFY_API_VERSION", "2026-04"),
            "store2_configured": bool(os.getenv("SHOPIFY_STORE2_DOMAIN") and os.getenv("SHOPIFY_STORE2_TOKEN")),
            "store2_domain": os.getenv("SHOPIFY_STORE2_DOMAIN", "soolar.myshopify.com"),
        },
        "stripe": {
            "configured": bool(os.getenv("STRIPE_SECRET_KEY")),
            "webhook_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET")),
        },
        "supabase": {
            "configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY")),
            "url": os.getenv("SUPABASE_URL", ""),
        },
        "ollama": {
            "configured": bool(os.getenv("OLLAMA_HOST")),
            "online": ollama_ok,
            "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        },
        "ai": {
            "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        },
    })


# ── RudiBot Army Integration ─────────────────────────────────────────────────

ARMY_STATE_FILE = BASE_DIR / "rudibot-army" / "shared" / "army_state.json"

async def handle_army_status(req):
    """Gibt den aktuellen Status aller Army-Agenten zurück."""
    try:
        if ARMY_STATE_FILE.exists():
            state = json.loads(ARMY_STATE_FILE.read_text(errors='ignore'))
        else:
            state = {"agents": {}, "events": [], "fixes": [], "stats": {}}
        # Laufende Prozesse prüfen
        army_running = False
        try:
            r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                               capture_output=True, text=True)
            army_running = r.returncode == 0 and bool(r.stdout.strip())
        except Exception:
            pass
        return web.json_response({
            "ok": True,
            "army_running": army_running,
            "agents": state.get("agents", {}),
            "events": state.get("events", [])[-20:],
            "agent_count": len(state.get("agents", {})),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_army_start(req):
    """Startet die Army wenn sie nicht läuft."""
    try:
        r = subprocess.run(["pgrep", "-f", "army_commander.py"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return web.json_response({"ok": True, "msg": "Army läuft bereits"})
        log_path = Path("/tmp/rudibot-army.log")
        with open(log_path, "a") as lf:
            subprocess.Popen(
                [sys.executable, str(BASE_DIR / "rudibot-army" / "army_commander.py")],
                stdout=lf, stderr=lf, start_new_session=True,
            )
        return web.json_response({"ok": True, "msg": "Army gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_monitor(req):
    """Mega Monitoring Dashboard"""
    html_path = Path(__file__).parent / "mega_monitor.html"
    if html_path.exists():
        return web.Response(
            text=html_path.read_text(encoding="utf-8"),
            content_type="text/html",
            charset="utf-8",
        )
    # Wenn HTML fehlt → neu generieren
    try:
        import subprocess
        py = Path(__file__).parent / "mega_monitor.py"
        subprocess.run(["python3", str(py)], timeout=30)
        if html_path.exists():
            return web.Response(
                text=html_path.read_text(encoding="utf-8"),
                content_type="text/html",
                charset="utf-8",
            )
    except Exception as e:
        pass
    return web.Response(text=f"<h2>Monitor wird generiert... <a href='/monitor'>Reload</a></h2>", content_type="text/html")


async def handle_monitor_refresh(req):
    """Dashboard neu generieren und zurückgeben"""
    try:
        import subprocess
        py = Path(__file__).parent / "mega_monitor.py"
        subprocess.run(["python3", str(py)], timeout=60, check=True)
        return web.json_response({"ok": True, "msg": "Dashboard aktualisiert"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_processes(req):
    try:
        import psutil
        procs = []
        for p in sorted(
            psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']),
            key=lambda x: x.info['cpu_percent'] or 0,
            reverse=True
        )[:15]:
            cmd = ' '.join(p.info['cmdline'] or [p.info['name'] or ''])[:60]
            procs.append({
                "pid": p.info['pid'],
                "name": p.info['name'],
                "cpu": round(p.info['cpu_percent'] or 0, 1),
                "mem": round(p.info['memory_percent'] or 0, 1),
                "cmd": cmd,
            })
        return web.json_response({"ok": True, "processes": procs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Storage Monitor API
# ---------------------------------------------------------------------------

async def handle_storage_status(req):
    try:
        from modules.storage_monitor import get_status_dict
        return web.json_response(get_status_dict())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_storage_cleanup(req):
    try:
        data = await req.json() if req.can_read_body else {}
        max_age = int(data.get("max_age_hours", 24))
        from modules.storage_monitor import run_cleanup
        result = run_cleanup(max_age_hours=max_age)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_offload(req):
    try:
        data = await req.json() if req.can_read_body else {}
        mountpoint = data.get("mountpoint", "/")
        min_mb = float(data.get("min_file_mb", 50.0))
        from modules.storage_monitor import run_offload
        result = run_offload(source_mountpoint=mountpoint, min_file_mb=min_mb)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_large_files(req):
    try:
        directory = req.rel_url.query.get("dir", str(BASE_DIR))
        try:
            min_mb = float(req.rel_url.query.get("min_mb", "50"))
        except (ValueError, TypeError):
            min_mb = 50.0
        from modules.storage_monitor import find_large_files
        files = find_large_files(Path(directory), min_size_mb=min_mb, limit=30)
        return web.json_response({"ok": True, "files": files, "directory": directory})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_history(req):
    try:
        try:
            limit = int(req.rel_url.query.get("limit", "50"))
        except (ValueError, TypeError):
            limit = 50
        from modules.storage_monitor import get_event_history
        return web.json_response({"ok": True, "events": get_event_history(limit)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_storage_widget(req):
    widget = Path(__file__).parent / "storage_widget.html"
    if widget.exists():
        return web.Response(text=widget.read_text(), content_type="text/html")
    return web.Response(text="Storage widget not found", status=404)


# ---------------------------------------------------------------------------
# Self-Learner API
# ---------------------------------------------------------------------------

async def handle_self_learner_status(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "status": "disabled", "reason": "self_learner_core not available"})
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        return web.json_response({"ok": True, "status": "active", "skills_count": len(skills), "skills": list(skills.keys())})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_learn(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        skill_name = data.get("skill")
        skill_data = data.get("data", {})
        if not skill_name:
            return web.json_response({"ok": False, "error": "skill name required"}, status=400)
        _self_learner.learn(skill_name, skill_data)
        return web.json_response({"ok": True, "learned": skill_name})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_skills(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "skills": [], "error": "self_learner_core not available"})
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        return web.json_response({"ok": True, "skills": list(skills.keys()), "count": len(skills)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_delete(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        skill_name = data.get("skill")
        if not skill_name:
            return web.json_response({"ok": False, "error": "skill name required"}, status=400)
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        if skill_name in skills:
            del skills[skill_name]
            return web.json_response({"ok": True, "deleted": skill_name})
        return web.json_response({"ok": False, "error": f"skill '{skill_name}' not found"}, status=404)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_self_learner_find_api(req):
    try:
        if _self_learner is None:
            return web.json_response({"ok": False, "error": "self_learner_core not available"}, status=503)
        data = await req.json() if req.can_read_body else {}
        query = data.get("query", "")
        skills = _self_learner.learned_skills if hasattr(_self_learner, 'learned_skills') else {}
        matches = [k for k in skills.keys() if query.lower() in k.lower()] if query else list(skills.keys())
        return web.json_response({"ok": True, "query": query, "matches": matches, "count": len(matches)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# New section handlers: API Keys, GitHub, Cloud, Bot Repair, Notes, Railway
# ---------------------------------------------------------------------------

_WATCHED_ENV_KEYS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_API_TOKEN",
    "SHOPIFY_STORE_URL", "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_API_VERSION",
    "OLLAMA_HOST", "OLLAMA_FAST_MODEL", "OLLAMA_SMART_MODEL", "OLLAMA_CODE_MODEL",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY",
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
    "GOOGLE_ADS_CLIENT_ID", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "GCP_PROJECT_ID", "GMC_MERCHANT_ID",
    "ETERNAL_BOT_DIR", "KIVO_DIR",
    "DASHBOARD_PORT", "SHOPIFY_SUITE_URL",
    # E-Commerce & Automation
    "DIGISTORE24_API_KEY", "PRINTIFY_API_KEY", "PRINTIFY_SHOP_ID",
    "ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "GUMROAD_ACCESS_TOKEN",
    "MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX",
    "STRIPE_SECRET_KEY", "KLAVIYO_API_KEY",
    # Social Media
    "TIKTOK_CLIENT_KEY", "PINTEREST_ACCESS_TOKEN",
    "META_ACCESS_TOKEN", "META_PAGE_ID",
    "TWITTER_BEARER_TOKEN", "DISCORD_BOT_TOKEN",
    "YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID",
    "REDDIT_CLIENT_ID",
    # Infrastructure
    "GITHUB_TOKEN", "RAILWAY_TOKEN",
]

# Key format validators (no network needed)
_KEY_FORMATS = {
    "OPENAI_API_KEY":        lambda v: v.startswith("sk-"),
    "ANTHROPIC_API_KEY":     lambda v: v.startswith("sk-ant-"),
    "PERPLEXITY_API_KEY":    lambda v: v.startswith("pplx-") or len(v) > 20,
    "TELEGRAM_BOT_TOKEN":    lambda v: ":" in v and len(v) > 20,
    "SHOPIFY_ACCESS_TOKEN":  lambda v: v.startswith("shpat_") or v.startswith("shpss_") or len(v) > 20,
    "SHOPIFY_API_KEY":       lambda v: len(v) > 20,
    "SHOPIFY_API_SECRET":    lambda v: v.startswith("shpss_") or len(v) > 20,
    "SUPABASE_URL":          lambda v: "supabase" in v or v.startswith("http"),
    "SUPABASE_ANON_KEY":     lambda v: len(v) > 50,
    "SUPABASE_SERVICE_ROLE_KEY": lambda v: len(v) > 50,
}


async def _validate_key(session: aiohttp.ClientSession, key: str, val: str) -> str:
    """Returns 'valid', 'present', or 'missing'."""
    if not val:
        return "missing"

    # Format check first (fast, no network)
    fmt_check = _KEY_FORMATS.get(key)
    if fmt_check and not fmt_check(val):
        return "present"  # set but wrong format

    # Network validation for critical keys
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        if key == "OPENAI_API_KEY":
            async with session.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {val}"},
                timeout=timeout
            ) as r:
                return "valid" if r.status == 200 else "present"

        elif key == "ANTHROPIC_API_KEY":
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": val,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=timeout
            ) as r:
                return "valid" if r.status in (200, 400) else "present"

        elif key == "SUPABASE_URL" and os.environ.get("SUPABASE_ANON_KEY"):
            async with session.get(
                f"{val}/rest/v1/",
                headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
                timeout=timeout
            ) as r:
                return "valid" if r.status < 500 else "present"

    except Exception:
        pass

    # Not validated via network — but set + format ok
    return "present"


async def handle_api_keys(req):
    """Returns validation status for all tracked env keys."""
    validate = req.rel_url.query.get("validate", "1") == "1"
    result = {}
    async with aiohttp.ClientSession() as session:
        for key in _WATCHED_ENV_KEYS:
            val = os.environ.get(key, "")
            if not val:
                status = "missing"
            elif validate:
                status = await _validate_key(session, key, val)
            else:
                status = "present"
            result[key] = {
                "status": status,          # "valid" | "present" | "missing"
                "set": bool(val),
                "length": len(val),
                "preview": val[:4] + "..." if len(val) > 4 else ("(set)" if val else ""),
            }
    set_count    = sum(1 for v in result.values() if v["set"])
    valid_count  = sum(1 for v in result.values() if v["status"] == "valid")
    return web.json_response({
        "ok": True, "keys": result,
        "summary": {"total": len(result), "set": set_count, "valid": valid_count}
    })


async def handle_github_status(req):
    """Returns current git branch, last commit, and remote URL."""
    try:
        def _git(args):
            r = subprocess.run(["git", "-C", str(BASE_DIR)] + args,
                               capture_output=True, text=True, timeout=8)
            return r.stdout.strip() if r.returncode == 0 else ""
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        commit = _git(["log", "-1", "--oneline"])
        remote = _git(["remote", "get-url", "origin"])
        status = _git(["status", "--porcelain"])
        staged = len([l for l in status.splitlines() if l and l[0] in "MADRCU"])
        unstaged = len([l for l in status.splitlines() if l and l[1] in "MADRCU?"])
        return web.json_response({
            "ok": True,
            "branch": branch,
            "commit": commit,
            "remote": remote,
            "staged": staged,
            "unstaged": unstaged,
            "clean": not bool(status.strip()),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_github_push(req):
    """Git add -A, commit with timestamp, push to current branch."""
    try:
        def _git(args):
            r = subprocess.run(["git", "-C", str(BASE_DIR)] + args,
                               capture_output=True, text=True, timeout=30)
            return r.returncode == 0, r.stdout.strip(), r.stderr.strip()

        ok, out, err = _git(["status", "--porcelain"])
        if not out.strip():
            return web.json_response({"ok": True, "message": "Nichts zu committen"})

        ts = time.strftime("%Y-%m-%d %H:%M")
        _git(["add", "-A"])
        ok, out, err = _git(["commit", "-m", f"Dashboard auto-commit {ts}"])
        if not ok:
            return web.json_response({"ok": False, "error": f"Commit: {err}"})

        branch_ok, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"])
        push_ok, push_out, push_err = _git(["push", "origin", branch])
        if push_ok:
            return web.json_response({"ok": True, "message": f"Gepusht: {branch} ✅"})
        return web.json_response({"ok": False, "error": push_err[:200]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pipedrive_status(req):
    try:
        from modules.pipedrive_client import check_status
        return web.json_response(await check_status())
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_pipedrive_deals(req):
    try:
        from modules.pipedrive_client import list_deals
        limit = int(req.rel_url.query.get("limit", 20))
        deals = await list_deals(limit=limit)
        return web.json_response({"ok": True, "deals": deals, "count": len(deals)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_pipedrive_deal_create(req):
    try:
        from modules.pipedrive_client import create_deal
        body = await req.json()
        deal = await create_deal(
            title=body["title"],
            value=float(body.get("value", 0)),
            currency=body.get("currency", "EUR"),
            person_id=body.get("person_id"),
            org_id=body.get("org_id"),
        )
        return web.json_response({"ok": True, "deal": deal})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_pipedrive_persons(req):
    try:
        from modules.pipedrive_client import list_persons
        persons = await list_persons(limit=int(req.rel_url.query.get("limit", 20)))
        return web.json_response({"ok": True, "persons": persons, "count": len(persons)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_railway_status(req):
    try:
        from modules.railway_client import check_status
        result = await check_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})


async def handle_railway_volumes(req):
    project_id = req.rel_url.query.get("project_id") or os.getenv("RAILWAY_PROJECT_ID", "")
    if not project_id:
        return web.json_response({"ok": False, "error": "project_id required"})
    try:
        from modules.railway_client import list_volumes
        volumes = await list_volumes(project_id)
        return web.json_response({"ok": True, "volumes": volumes})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_railway_backups(req):
    volume_instance_id = req.rel_url.query.get("volume_instance_id", "")
    if not volume_instance_id:
        return web.json_response({"ok": False, "error": "volume_instance_id required"})
    try:
        from modules.railway_client import list_backups
        backups = await list_backups(volume_instance_id)
        return web.json_response({"ok": True, "backups": backups})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_railway_backup_create(req):
    data = await req.json()
    volume_instance_id = data.get("volume_instance_id", "")
    if not volume_instance_id:
        return web.json_response({"ok": False, "error": "volume_instance_id required"})
    try:
        from modules.railway_client import create_backup
        backup_id = await create_backup(volume_instance_id)
        return web.json_response({"ok": True, "backup_id": backup_id})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_railway_backup_restore(req):
    data = await req.json()
    try:
        from modules.railway_client import restore_backup
        ok = await restore_backup(data["backup_id"], data["volume_instance_id"])
        return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_cloud_status(req):
    """Check Railway + ngrok availability."""
    railway_url = os.getenv("SHOPIFY_SUITE_URL",
                            "https://shopify-suite-v2-production.up.railway.app")
    results = {}
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        # Railway
        try:
            async with s.get(f"{railway_url}/health") as r:
                results["railway"] = {"ok": r.status < 400, "status": r.status, "url": railway_url}
        except Exception as e:
            results["railway"] = {"ok": False, "error": str(e)[:80], "url": railway_url}
        # ngrok
        try:
            async with s.get("http://localhost:4040/api/tunnels") as r:
                d = await r.json()
                tunnels = [t.get("public_url", "") for t in d.get("tunnels", [])]
                results["ngrok"] = {"ok": True, "tunnels": tunnels}
        except Exception:
            results["ngrok"] = {"ok": False, "tunnels": []}
    return web.json_response({"ok": True, "services": results})


async def handle_bot_repair_status(req):
    """Returns self-healer status + recent heal history."""
    try:
        heal_log = DATA_DIR / "heal_history.json"
        history = []
        if heal_log.exists():
            history = json.loads(heal_log.read_text())[-20:]
        known = {}
        known_file = DATA_DIR / "known_fixes.json"
        if known_file.exists():
            known = json.loads(known_file.read_text())
        return web.json_response({
            "ok": True,
            "total_fixes": len(history),
            "known_problems": len(known),
            "recent": history[-5:],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_repair_run(req):
    """Trigger self-healer scan."""
    try:
        sys.path.insert(0, str(BASE_DIR / "core"))
        from self_healer import SelfHealer
        healer = SelfHealer()
        fixes = await healer.run_auto_fixes()
        errors = await healer.scan_logs_for_errors()
        return web.json_response({
            "ok": True,
            "fixes_applied": fixes,
            "log_errors": [e["error"] for e in errors],
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_get(req):
    """Get saved notes."""
    notes_file = DATA_DIR / "notes.json"
    notes = []
    if notes_file.exists():
        try:
            notes = json.loads(notes_file.read_text())
        except Exception:
            pass
    return web.json_response({"ok": True, "notes": notes})


async def handle_notes_save(req):
    """Save a note."""
    try:
        data = await req.json()
        text = str(data.get("text", "")).strip()[:2000]
        if not text:
            return web.json_response({"ok": False, "error": "Leere Notiz"})
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            try:
                notes = json.loads(notes_file.read_text())
            except Exception:
                pass
        notes.append({"text": text, "created": datetime.now().isoformat()})
        notes = notes[-100:]
        notes_file.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_delete(req):
    """Delete a note by index."""
    try:
        data = await req.json()
        idx = int(data.get("index", -1))
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            notes = json.loads(notes_file.read_text())
        if 0 <= idx < len(notes):
            notes.pop(idx)
            notes_file.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_deepscan(req):
    """Run a comprehensive system deep scan."""
    results = {"timestamp": datetime.now().isoformat(), "checks": {}}

    # 1. Python syntax check on key files
    key_files = [
        BASE_DIR / "core" / "mega_orchestrator.py",
        BASE_DIR / "core" / "self_healer.py",
        BASE_DIR / "dashboard" / "server.py",
        BASE_DIR / "modules" / "telegram_control.py",
    ]
    syntax_ok = []
    syntax_err = []
    for f in key_files:
        if not f.exists():
            continue
        try:
            import ast
            ast.parse(f.read_text())
            syntax_ok.append(f.name)
        except SyntaxError as e:
            syntax_err.append(f"{f.name}: {e}")
    results["checks"]["syntax"] = {"ok": not syntax_err, "ok_files": syntax_ok, "errors": syntax_err}

    # 2. Env vars
    required_env = ["TELEGRAM_BOT_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN"]
    missing_env = [k for k in required_env if not os.environ.get(k)]
    results["checks"]["env"] = {"ok": not missing_env, "missing": missing_env}

    # 3. Ollama
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(f"{OLLAMA_BASE}/api/tags") as r:
                results["checks"]["ollama"] = {"ok": r.status == 200}
    except Exception:
        results["checks"]["ollama"] = {"ok": False}

    # 4. Army state
    army_state = BASE_DIR / "rudibot-army" / "shared" / "army_state.json"
    results["checks"]["army_state"] = {"ok": army_state.exists()}

    # 5. Disk
    try:
        import psutil
        disk = psutil.disk_usage("/")
        results["checks"]["disk"] = {
            "ok": disk.percent < 90,
            "percent": disk.percent,
            "free_gb": disk.free // 1024 ** 3,
        }
    except ImportError:
        results["checks"]["disk"] = {"ok": True, "note": "psutil nicht installiert"}

    # Summary
    total = len(results["checks"])
    passed = sum(1 for v in results["checks"].values() if v.get("ok"))
    results["summary"] = {"total": total, "passed": passed, "failed": total - passed}
    return web.json_response(results)


async def handle_automation_status(req):
    """Return automation scheduler status + recent task runs."""
    try:
        from core.automation_scheduler import get_scheduler, get_last_runs
        sched = get_scheduler()
        return web.json_response({
            "ok": True,
            "status": sched.status(),
            "recent_runs": get_last_runs(limit=30),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_automation_run(req):
    """Manually trigger a specific automation task."""
    try:
        data = await req.json()
        task_name = data.get("task", "")
        from core.automation_scheduler import get_scheduler
        sched = get_scheduler()
        result = await sched.run_now(task_name)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_automation_tasks(req):
    """Return full task list with intervals and last-run info."""
    try:
        from core.automation_scheduler import TASKS, get_task_stats
        stats = get_task_stats()
        tasks = []
        for name, _fn, interval_s, delay_s in TASKS:
            s = stats.get(name, {})
            tasks.append({
                "name":       name,
                "interval_s": interval_s,
                "interval_label": (
                    f"{interval_s // 3600}h" if interval_s >= 3600
                    else f"{interval_s // 60}min"
                ),
                "last_run":  s.get("last_run"),
                "total_runs": s.get("total", 0),
                "ok_runs":    s.get("ok", 0),
                "avg_ms":     s.get("avg_ms", 0),
            })
        return web.json_response({"ok": True, "tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_social_status(req):
    """Ping all social media platform connectors."""
    try:
        from modules.social_connectors import ping_all
        results = await ping_all()
        if "ok" not in results:
            results["ok"] = True
        return web.json_response(results)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_digistore_status(req):
    try:
        from modules.digistore24_automation import ping, get_sales_stats, get_products
        ok = await ping()
        stats = await get_sales_stats() if ok else {}
        products = await get_products() if ok else []
        return web.json_response({"ok": ok, "stats": stats, "product_count": len(products)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_digistore_orders(req):
    try:
        from modules.digistore24_automation import get_orders
        try:
            page = int(req.rel_url.query.get("page", "1"))
        except (ValueError, TypeError):
            page = 1
        orders = await get_orders(page=page)
        return web.json_response({"ok": True, "orders": orders})
    except Exception as e:
        return web.json_response({"ok": False, "orders": [], "error": str(e)})


async def handle_mailchimp_status(req):
    try:
        from modules.mailchimp_automation import ping, get_lists
        ok, account = await ping()
        lists = await get_lists() if ok else []
        return web.json_response({"ok": ok, "account": account, "lists": lists})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_sync(req):
    try:
        from modules.mailchimp_automation import sync_from_digistore, get_lists
        lists = await get_lists()
        if not lists:
            return web.json_response({"ok": False, "error": "Keine Listen gefunden"})
        list_id = (await req.json()).get("list_id") or lists[0]["id"]
        count = await sync_from_digistore(list_id)
        return web.json_response({"ok": True, "synced": count})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mailchimp_campaign(req):
    """Create and send a Mailchimp campaign."""
    try:
        data = await req.json()
        from modules.mailchimp_automation import ping, get_lists
        ok, account = await ping()
        if not ok:
            return web.json_response({"ok": False, "error": "Mailchimp nicht konfiguriert"})
        import aiohttp, os
        key    = os.getenv("MAILCHIMP_API_KEY", "")
        prefix = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")
        if "-" in key:
            prefix = key.split("-")[-1]
        base = f"https://{prefix}.api.mailchimp.com/3.0"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        lists = await get_lists()
        list_id = data.get("list_id") or (lists[0]["id"] if lists else "")
        if not list_id:
            return web.json_response({"ok": False, "error": "Keine Mailchimp-Liste gefunden"})
        campaign_body = {
            "type": "regular",
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": data.get("subject", "SuperMegaBot Newsletter"),
                "from_name":    data.get("from_name", "SuperMegaBot"),
                "reply_to":     data.get("reply_to", "noreply@supermegabot.com"),
            },
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(f"{base}/campaigns", headers=headers, json=campaign_body) as r:
                if r.status not in (200, 201):
                    body = await r.text()
                    return web.json_response({"ok": False, "error": f"HTTP {r.status}: {body[:200]}"})
                camp = await r.json()
            camp_id = camp["id"]
            content_body = {"html": data.get("body_html", "<p>Hallo!</p>")}
            async with s.put(f"{base}/campaigns/{camp_id}/content", headers=headers, json=content_body) as r:
                if r.status not in (200, 204):
                    return web.json_response({"ok": False, "error": "Content-Upload fehlgeschlagen"})
            async with s.post(f"{base}/campaigns/{camp_id}/actions/send", headers=headers) as r:
                if r.status not in (200, 204):
                    return web.json_response({"ok": False, "error": "Senden fehlgeschlagen"})
        return web.json_response({"ok": True, "campaign_id": camp_id, "subject": data.get("subject")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_memory_save(req):
    """Save a key-value memory note (alias for notes endpoint)."""
    try:
        import json as _json
        data = await req.json()
        key   = str(data.get("key", "")).strip()
        value = str(data.get("value", "")).strip()
        if not key:
            return web.json_response({"ok": False, "error": "key erforderlich"})
        mem_file = DATA_DIR / "memory.json"
        memory: dict = {}
        if mem_file.exists():
            try:
                memory = _json.loads(mem_file.read_text())
            except Exception:
                pass
        memory[key] = {"value": value, "updated": datetime.now().isoformat()}
        mem_file.write_text(_json.dumps(memory, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "key": key, "total": len(memory)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_notes_save_alias(req):
    """Alias: /api/notes/save → same as /api/notes POST."""
    try:
        import json as _json
        data = await req.json()
        key   = str(data.get("key", data.get("text", ""))).strip()
        value = str(data.get("value", "")).strip()
        notes_file = DATA_DIR / "notes.json"
        notes = []
        if notes_file.exists():
            try:
                notes = _json.loads(notes_file.read_text())
            except Exception:
                pass
        notes.append({"key": key, "text": value or key, "created": datetime.now().isoformat()})
        notes = notes[-200:]
        notes_file.write_text(_json.dumps(notes, indent=2, ensure_ascii=False))
        return web.json_response({"ok": True, "count": len(notes)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_status(req):
    try:
        from modules.printify_automation import ping, get_stats
        ok = await ping()
        stats = await get_stats() if ok else {}
        return web.json_response({"ok": ok, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_autofulfill(req):
    try:
        from modules.printify_automation import auto_fulfill_pending
        result = await auto_fulfill_pending()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_etsy_status(req):
    try:
        from modules.ecommerce_connectors import EtsyConnector
        etsy = EtsyConnector()
        ok, info = await etsy.ping()
        stats = await etsy.get_stats() if ok else {}
        return web.json_response({"ok": ok, "info": info, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_gumroad_status(req):
    try:
        from modules.ecommerce_connectors import GumroadConnector
        gum = GumroadConnector()
        info = await gum.ping()
        ok = info.get("connected", False)
        stats = await gum.get_stats() if ok else {}
        return web.json_response({"ok": ok, "info": info, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_status(req):
    """Revenue aggregation across all platforms."""
    try:
        from modules.revenue_aggregator import get_platform_revenue
        revenue = await get_platform_revenue()
        return web.json_response({"ok": True, "revenue": revenue})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_report(req):
    """Generate and return daily revenue report."""
    try:
        from modules.revenue_aggregator import get_daily_report, save_daily_snapshot
        report = await get_daily_report()
        await save_daily_snapshot()
        return web.json_response({"ok": True, "report": report})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_seo_status(req):
    """SEO score for all Shopify products."""
    try:
        from modules.seo_automation import generate_sitemap_data
        sitemap = await generate_sitemap_data()
        return web.json_response({"ok": True, "sitemap": sitemap})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_seo_run(req):
    """Run AI-powered SEO optimizer on Shopify products."""
    try:
        data = await req.json() if req.can_read_body else {}
        limit = int(data.get("limit", 5))
        from modules.seo_automation import optimize_all_shopify_products
        result = await optimize_all_shopify_products(limit=limit)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# REVENUE AUTOPILOT — Shopify Revenue Engine Handlers
# ══════════════════════════════════════════════════════════════════════════════

async def handle_revenue_dashboard(req):
    """Vollständiges Revenue Dashboard (Umsatz + Carts + Inventory)."""
    try:
        from modules.shopify_revenue_engine import get_full_dashboard
        data = await get_full_dashboard()
        return web.json_response({"ok": True, **data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_summary(req):
    """GET /api/revenue/summary — Cached 5min revenue summary."""
    cached = _cache_get("revenue_summary", 300)
    if cached is not None:
        return web.json_response(cached)
    try:
        from modules.shopify_revenue_engine import get_revenue_summary
        data = await get_revenue_summary()
        result = {"ok": True, **data}
        _cache_set("revenue_summary", result)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_revenue_analytics(req):
    """Umsatz-Analyse: heute, 7T, 30T, offene Bestellungen. Cached 5min."""
    cached = _cache_get("revenue_summary", 300)
    if cached is not None:
        return web.json_response(cached)
    try:
        from modules.shopify_revenue_engine import get_revenue_summary
        data = await get_revenue_summary()
        result = {"ok": True, **data}
        _cache_set("revenue_summary", result)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_abandoned_carts(req):
    """Alle offenen / verlassenen Warenkörbe."""
    try:
        try:
            hours = int(req.rel_url.query.get("hours", "24"))
        except (ValueError, TypeError):
            hours = 24
        from modules.shopify_revenue_engine import get_abandoned_carts
        carts = await get_abandoned_carts(hours)
        return web.json_response({"ok": True, "count": len(carts), "carts": carts})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_recover_carts(req):
    """Alle offenen Carts per Recovery-E-Mail ansprechen."""
    try:
        data = await req.json() if req.can_read_body else {}
        hours = int(data.get("hours", 24))
        from modules.shopify_revenue_engine import recover_all_carts
        result = await recover_all_carts(hours)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_flash_sale(req):
    """Flash Sale durch direkte Preisaktualisierung — kein Discount-Code nötig."""
    try:
        data = await req.json() if req.can_read_body else {}
        from modules.shopify_revenue_engine import create_flash_sale
        pct = int(data.get("discount_percent", data.get("discount_pct", 20)))
        result = await create_flash_sale(
            discount_pct=pct,
            title=data.get("title", ""),
            duration_hours=int(data.get("duration_hours", 24)),
            collection_id=data.get("collection_id"),
            min_purchase=float(data.get("min_purchase", 0)),
            product_ids=data.get("product_ids"),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_restore_flash_sale(req):
    """Originalpreise nach Flash Sale wiederherstellen."""
    try:
        from modules.shopify_revenue_engine import restore_flash_sale
        result = await restore_flash_sale()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bulk_price_update(req):
    """Preise für alle oder ausgewählte Produkte auf einmal anpassen."""
    try:
        data = await req.json() if req.can_read_body else {}
        from modules.shopify_revenue_engine import bulk_price_update
        result = await bulk_price_update(
            product_ids=data.get("product_ids"),
            method=data.get("method", "percent"),
            value=float(data.get("value", 10)),
            min_price=float(data.get("min_price", 0)),
            max_price=float(data.get("max_price", 99999)),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_product_performance(req):
    """Top-Seller, Slow-Mover und Zero-Seller Analyse."""
    try:
        try:
            days = int(req.rel_url.query.get("days", "30"))
        except (ValueError, TypeError):
            days = 30
        from modules.shopify_revenue_engine import get_product_performance
        data = await get_product_performance(days)
        return web.json_response({"ok": True, **data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_all_products_prices(req):
    """Alle Produkte mit aktuellen Preisen. Cached 2min."""
    cached = _cache_get("shopify_products", 120)
    if cached is not None:
        return web.json_response(cached)
    try:
        from modules.shopify_revenue_engine import get_all_products_with_prices
        products = await get_all_products_with_prices()
        result = {"ok": True, "count": len(products), "products": products}
        _cache_set("shopify_products", result)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_ai_descriptions(req):
    """Claude generiert SEO-Beschreibungen für Produkte (Bulk)."""
    try:
        data = await req.json() if req.can_read_body else {}
        from modules.shopify_revenue_engine import generate_ai_descriptions_bulk
        result = await generate_ai_descriptions_bulk(
            product_ids=data.get("product_ids"),
            limit=int(data.get("limit", 5)),
            language=data.get("language", "de"),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_low_inventory(req):
    """Produkte mit niedrigem Lagerbestand."""
    try:
        try:
            threshold = int(req.rel_url.query.get("threshold", "5"))
        except (ValueError, TypeError):
            threshold = 5
        from modules.shopify_revenue_engine import get_low_inventory
        items = await get_low_inventory(threshold)
        return web.json_response({"ok": True, "count": len(items), "items": items})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_publish_drafts(req):
    """Alle Draft-Produkte automatisch veröffentlichen."""
    try:
        from modules.shopify_revenue_engine import auto_publish_drafts
        result = await auto_publish_drafts()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_upsell_pairs(req):
    """Produkte die häufig zusammen gekauft werden (Upsell-Empfehlungen)."""
    try:
        try:
            limit = int(req.rel_url.query.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10
        from modules.shopify_revenue_engine import get_upsell_pairs
        pairs = await get_upsell_pairs(limit)
        return web.json_response({"ok": True, "pairs": pairs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── YouTube Analytics ─────────────────────────────────────────────────────────

async def handle_youtube_dashboard(req):
    """YouTube Kanal-Dashboard: Abonnenten, Views, Videos."""
    try:
        from modules.youtube_analytics import get_full_dashboard
        return web.json_response(await get_full_dashboard())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_youtube_stats(req):
    try:
        from modules.youtube_analytics import get_channel_stats
        return web.json_response(await get_channel_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_youtube_latest(req):
    try:
        try:
            n = int(req.rel_url.query.get("limit", "10"))
        except (ValueError, TypeError):
            n = 10
        from modules.youtube_analytics import get_latest_videos
        return web.json_response(await get_latest_videos(n))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_youtube_top(req):
    try:
        try:
            n = int(req.rel_url.query.get("limit", "10"))
        except (ValueError, TypeError):
            n = 10
        from modules.youtube_analytics import get_top_videos
        return web.json_response(await get_top_videos(n))
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Revenue Autopilot Frontend ─────────────────────────────────────────────────

async def handle_revenue_autopilot_ui(req):
    """Standalone Revenue Autopilot Dashboard HTML."""
    html = _REVENUE_AUTOPILOT_HTML
    return web.Response(text=html, content_type="text/html", charset="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# AUTOPILOT CREATORHUB — Agent System Handlers
# ══════════════════════════════════════════════════════════════════════════════

_AUTOPILOT_HTML_PATH = Path(__file__).parent / "autopilot.html"


async def handle_autopilot_ui(req):
    """AutoPilot CreatorHub Dashboard."""
    try:
        html = _AUTOPILOT_HTML_PATH.read_text(encoding="utf-8")
        return web.Response(text=html, content_type="text/html", charset="utf-8")
    except Exception as e:
        return web.Response(text=f"Error: {e}", status=500)


async def handle_agents_status_all(req):
    """Status aller 10 AI-Agenten."""
    try:
        from modules.autopilot_agents import get_all_status
        statuses = await get_all_status()
        return web.json_response({"ok": True, "agents": statuses})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_agents_run(req):
    """Einen Agenten ausführen: {agent, task, params}."""
    try:
        data = await req.json()
        agent = data.get("agent", "ceo")
        task = data.get("task", "status")
        params = data.get("params", {})
        from modules.autopilot_agents import run_agent
        result = await run_agent(agent, task, params)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_agents_logs(req):
    """Letzte Logs aller Agenten."""
    try:
        try:
            limit = int(req.rel_url.query.get("limit", "50"))
        except (ValueError, TypeError):
            limit = 50
        from modules.autopilot_agents import get_all_logs
        logs = await get_all_logs(limit)
        return web.json_response({"ok": True, "logs": logs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════

async def handle_dropshipping_status(req):
    """Dropshipping pipeline status."""
    try:
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        trending = await wf.find_trending_products("general")
        return web.json_response({"ok": True, "trending_count": len(trending), "sample": trending[:3]})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_dropshipping_run(req):
    """Run a full dropshipping pipeline for a niche."""
    try:
        data = await req.json() if req.can_read_body else {}
        niche = data.get("niche", "trending")
        from modules.dropshipping_automation import DropshippingWorkflow
        wf = DropshippingWorkflow()
        result = await wf.full_pipeline(niche)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pod_status(req):
    """Print-on-Demand status via Printify."""
    try:
        from modules.printify_automation import get_stats, get_pending_orders
        stats = await get_stats()
        pending = await get_pending_orders()
        return web.json_response({"ok": True, "stats": stats, "pending_count": len(pending)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_status(req):
    try:
        from modules.klaviyo_automation import get_stats
        return web.json_response(await get_stats())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_lists(req):
    try:
        from modules.klaviyo_automation import get_lists
        lists = await get_lists()
        return web.json_response({"ok": True, "lists": lists})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_sync(req):
    try:
        try:
            data = await req.json()
        except Exception:
            data = {}
        list_id = data.get("list_id", "")
        source  = data.get("source", "digistore")
        from modules.klaviyo_automation import sync_from_digistore, sync_from_shopify, get_lists
        if not list_id:
            lists = await get_lists()
            list_id = lists[0]["id"] if lists else ""
        if not list_id:
            return web.json_response({"ok": False, "error": "Keine Klaviyo-Liste gefunden"})
        if source == "shopify":
            count = await sync_from_shopify(list_id)
        else:
            count = await sync_from_digistore(list_id)
        return web.json_response({"ok": True, "synced": count, "list_id": list_id, "source": source})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_klaviyo_campaign(req):
    try:
        data = await req.json()
        from modules.klaviyo_automation import create_and_send_campaign, get_lists
        list_id = data.get("list_id", "")
        if not list_id:
            lists = await get_lists()
            list_id = lists[0]["id"] if lists else ""
        if not list_id:
            return web.json_response({"ok": False, "error": "Keine Liste gefunden"})
        result = await create_and_send_campaign(
            list_id=list_id,
            subject=data.get("subject", "SuperMegaBot Newsletter"),
            from_email=data.get("from_email", "noreply@supermegabot.com"),
            from_name=data.get("from_name", "SuperMegaBot"),
            html_body=data.get("body_html", "<p>Hallo!</p>"),
            campaign_name=data.get("name", ""),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_clones_status(req):
    """Return status of all specialized bot-clone workers."""
    try:
        from core.bot_clones import get_bot_status
        return web.json_response(await get_bot_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_bot_clone_run(req):
    """Manually trigger a specific bot-clone action."""
    try:
        data = await req.json()
        bot_name = data.get("bot", "")
        action   = data.get("action", "status")
        from core.bot_clones import run_bot_action
        result = await run_bot_action(bot_name, action)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Watchdog Proxy ───────────────────────────────────────────────────────────

async def handle_watchdog_status(req):
    """Proxy GET /api/watchdog/status → http://localhost:9003/status"""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("http://localhost:9003/status") as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return web.json_response(data)
                return web.json_response({"ok": False, "error": f"HTTP {r.status}"})
    except Exception as e:
        return web.json_response({"ok": False, "status": "offline", "error": str(e)})


# ── Agenten Hub Proxy ─────────────────────────────────────────────────────────

async def handle_agents_hub(req):
    """Proxy GET /api/agents/hub → http://localhost:9998/status"""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("http://localhost:9998/status") as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    return web.json_response(data)
                return web.json_response({"ok": False, "error": f"HTTP {r.status}"})
    except Exception as e:
        return web.json_response({"ok": False, "status": "offline", "error": str(e)})


async def handle_agents_teams_list(req):
    try:
        from modules.agent_teams import list_teams
        return web.json_response({"ok": True, "teams": list_teams()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_agents_teams_run(req):
    try:
        data = await req.json()
        team = data.get("team", "").strip()
        task = data.get("task", "").strip()
        notify = data.get("notify", True)
        if not team or not task:
            return web.json_response({"ok": False, "error": "team and task required"}, status=400)
        from modules.agent_teams import run_team
        result = await run_team(team, task, notify=notify)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Monetization ─────────────────────────────────────────────────────────────

async def handle_plans_list(req):
    try:
        from modules.monetization import get_plans_info
        return web.json_response({"ok": True, "plans": get_plans_info()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_checkout_create(req):
    try:
        data = await req.json()
        plan = data.get("plan", "").strip()
        email = data.get("email", "").strip()
        base_url = data.get("base_url", os.getenv("DASHBOARD_URL", "http://localhost:8888"))
        if not plan or not email:
            return web.json_response({"ok": False, "error": "plan and email required"}, status=400)
        from modules.monetization import create_checkout_session
        session = create_checkout_session(
            plan=plan,
            customer_email=email,
            success_url=f"{base_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/checkout/cancel",
        )
        return web.json_response({"ok": True, "checkout_url": session.get("url"), "session_id": session.get("id")})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_mrr(req):
    try:
        from modules.monetization import get_mrr
        mrr = get_mrr()
        return web.json_response({"ok": True, "mrr_eur": mrr, "arr_eur": mrr * 12})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Stripe ───────────────────────────────────────────────────────────────────

async def handle_stripe_status(req):
    try:
        from modules.stripe_automation import get_stats
        data = await get_stats()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_balance(req):
    try:
        from modules.stripe_automation import get_balance
        data = await get_balance()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_charges(req):
    try:
        from modules.stripe_automation import get_charges
        try:
            days = int(req.rel_url.query.get("days", "30"))
            limit = int(req.rel_url.query.get("limit", "20"))
        except (ValueError, TypeError):
            days, limit = 30, 20
        data = await get_charges(limit=limit, days_back=days)
        return web.json_response({"ok": True, "charges": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_customers(req):
    try:
        from modules.stripe_automation import get_customers
        data = await get_customers(limit=50)
        return web.json_response({"ok": True, "customers": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_revenue(req):
    try:
        from modules.stripe_automation import get_revenue_summary
        try:
            days = int(req.rel_url.query.get("days", "30"))
        except (ValueError, TypeError):
            days = 30
        data = await get_revenue_summary(days_back=days)
        if "ok" not in data:
            data["ok"] = True
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_webhook(req):
    try:
        payload = await req.read()
        sig_header = req.headers.get("Stripe-Signature", "")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        from modules.stripe_automation import verify_webhook_signature, handle_webhook_event
        if webhook_secret and not verify_webhook_signature(payload, sig_header, webhook_secret):
            return web.json_response({"ok": False, "error": "Invalid signature"}, status=400)

        event = json.loads(payload)
        result = await handle_webhook_event(event)
        # Sofort-Benachrichtigung bei Revenue-Events
        try:
            from modules.notify_hub import handle_stripe_payment_event
            handle_stripe_payment_event(event)
        except Exception:
            pass
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_checkout(req):
    """Create Stripe Checkout Session for subscription."""
    try:
        data = await req.json()
        price_id = data.get("price_id")
        if not price_id:
            return web.json_response({"ok": False, "error": "price_id required"}, status=400)

        from modules.stripe_automation import create_checkout_session
        result = await create_checkout_session(price_id)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})



async def handle_stripe_mrr(req):
    """GET /api/stripe/mrr — Monthly Recurring Revenue from active subscriptions."""
    try:
        from modules.stripe_automation import get_mrr
        result = await get_mrr()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_churn(req):
    """GET /api/stripe/churn — Churn rate from canceled subscriptions."""
    try:
        try:
            days_back = int(req.rel_url.query.get("days", "30"))
        except (ValueError, TypeError):
            days_back = 30
        from modules.stripe_automation import get_churn_rate
        result = await get_churn_rate(days_back=days_back)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_subscriptions(req):
    """GET /api/stripe/subscriptions — List active Stripe subscriptions."""
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY", "")
        if not stripe_lib.api_key:
            return web.json_response({"ok": False, "subscriptions": [], "error": "No Stripe key configured"})
        subs = stripe_lib.Subscription.list(status="active", limit=20)
        result = []
        for s in subs.data:
            item = s["items"]["data"][0] if s.get("items") and s["items"]["data"] else {}
            plan = item.get("plan") or item.get("price") or {}
            result.append({
                "id": s["id"],
                "status": s["status"],
                "created": s["created"],
                "current_period_end": s["current_period_end"],
                "amount": (plan.get("amount") or 0) / 100,
                "currency": (plan.get("currency") or "eur").upper(),
                "interval": plan.get("interval") or "month",
            })
        return web.json_response({"ok": True, "subscriptions": result})
    except Exception as e:
        return web.json_response({"ok": False, "subscriptions": [], "error": str(e)})


async def handle_stripe_setup_products(req):
    """POST /api/stripe/setup-products — Create all SaaS tiers in Stripe."""
    try:
        from modules.stripe_automation import setup_saas_products
        result = await setup_saas_products()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_stripe_portal(req):
    """Create Stripe Customer Portal session."""
    try:
        data = await req.json()
        customer_id = data.get("customer_id")
        if not customer_id:
            return web.json_response({"ok": False, "error": "customer_id required"}, status=400)

        from modules.stripe_automation import create_customer_portal_session
        result = await create_customer_portal_session(customer_id)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Google Drive ──────────────────────────────────────────────────────────────

# ── Google OAuth2 ─────────────────────────────────────────────────────────────

async def handle_google_auth(req):
    """Redirect to Google OAuth2 login."""
    try:
        from modules.google_oauth import get_auth_url
        url = get_auth_url()
        raise web.HTTPFound(url)
    except web.HTTPFound:
        raise
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_callback(req):
    """Handle OAuth2 callback, exchange code for token."""
    code  = req.rel_url.query.get("code", "")
    error = req.rel_url.query.get("error", "")
    if error:
        return web.Response(
            content_type="text/html",
            text=f"<h2>❌ Google Auth Fehler: {error}</h2><a href='/'>Dashboard</a>"
        )
    if not code:
        return web.Response(
            content_type="text/html",
            text="<h2>❌ Kein Code erhalten</h2><a href='/'>Dashboard</a>"
        )
    try:
        from modules.google_oauth import exchange_code
        result = await exchange_code(code)
        if result.get("ok"):
            html = """
            <html><head><title>Google verbunden</title>
            <style>body{font-family:Inter,sans-serif;background:#040508;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
            .box{text-align:center;padding:40px;background:#0d1117;border:1px solid #1e293b;border-radius:12px}
            h2{color:#6ee7b7}a{color:#4f8ef7;text-decoration:none}</style></head>
            <body><div class="box">
            <h2>✅ Google Drive verbunden!</h2>
            <p>Token gespeichert — Drive Backup &amp; API aktiv.</p>
            <a href="/">← Zurück zum Dashboard</a>
            </div></body></html>"""
        else:
            html = f"<h2>❌ Token-Fehler: {result.get('error')}</h2><a href='/'>Dashboard</a>"
        return web.Response(content_type="text/html", text=html)
    except Exception as e:
        return web.Response(content_type="text/html", text=f"<h2>❌ {e}</h2><a href='/'>Dashboard</a>")


async def handle_google_status(req):
    try:
        from modules.google_oauth import get_status
        return web.json_response(await get_status())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_refresh(req):
    try:
        from modules.google_oauth import refresh_token
        return web.json_response(await refresh_token())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_google_revoke(req):
    try:
        from modules.google_oauth import revoke
        ok = await revoke()
        return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_status(req):
    try:
        from modules.google_drive_automation import get_stats
        data = await get_stats()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_files(req):
    try:
        from modules.google_drive_automation import list_files
        query = req.rel_url.query.get("q", "")
        try:
            limit = int(req.rel_url.query.get("limit", "20"))
        except (ValueError, TypeError):
            limit = 20
        data  = await list_files(query=query, page_size=limit)
        return web.json_response({"ok": True, "files": data})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_drive_backup(req):
    try:
        from modules.google_drive_automation import auto_backup
        result = await auto_backup()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


@web.middleware
async def logging_middleware(request, handler):
    """Log all POST requests with body size and response time."""
    start = time.time()
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        if request.method == "POST":
            log.warning("POST %s failed in %dms: %s", request.path, elapsed_ms, exc)
        raise
    elapsed_ms = int((time.time() - start) * 1000)
    if request.method == "POST":
        body_size = request.content_length or 0
        log.info("POST %s %dms body=%db status=%s",
                 request.path, elapsed_ms, body_size, response.status)
    return response


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response




# ---------------------------------------------------------------------------
# GROWTH ENGINE API
# ---------------------------------------------------------------------------
async def handle_growth_dashboard(req):
    try:
        from modules.growth_engine import get_growth_dashboard
        data = await get_growth_dashboard()
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_growth_dashboard: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_create(req):
    try:
        body = await req.json()
        email = body.get("email", "").strip()
        name  = body.get("name", "").strip()
        if not email:
            return web.json_response({"ok": False, "error": "email required"}, status=400)
        from modules.growth_engine import create_referral_code
        data = await create_referral_code(email, name)
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_create: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_stats(req):
    try:
        from modules.growth_engine import get_referral_stats
        data = await get_referral_stats()
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_stats: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_referral_top(req):
    try:
        try:
            limit = int(req.rel_url.query.get("limit", "10"))
        except (ValueError, TypeError):
            limit = 10
        from modules.growth_engine import get_top_referrers
        data = await get_top_referrers(limit=limit)
        return web.json_response({"ok": True, "data": data})
    except Exception as e:
        log.error("handle_referral_top: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_review_automation_run(req):
    try:
        from modules.growth_engine import run_review_automation
        result = await run_review_automation()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        log.error("handle_review_automation_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_winback_run(req):
    try:
        from modules.growth_engine import run_winback_automation
        result = await run_winback_automation()
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        log.error("handle_winback_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)




# ---------------------------------------------------------------------------
# DYNAMIC PRICING + EMAIL SEQUENCES API
# ---------------------------------------------------------------------------
async def handle_pricing_dashboard(req):
    """GET /api/pricing/dashboard — pricing metrics for last 30 days."""
    try:
        from modules.dynamic_pricing import get_pricing_dashboard
        data = await get_pricing_dashboard()
        return web.json_response({"ok": True, **data})
    except Exception as e:
        log.error("handle_pricing_dashboard: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_run(req):
    """POST /api/pricing/run — trigger a dynamic pricing cycle."""
    try:
        body = {}
        if req.can_read_body:
            try:
                body = await req.json()
            except Exception:
                pass
        max_products = int(body.get("max_products", 20))
        from modules.dynamic_pricing import run_dynamic_pricing_cycle
        result = await run_dynamic_pricing_cycle(max_products=max_products)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        log.error("handle_pricing_run: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_history(req):
    """GET /api/pricing/history?product_id=...&days=30"""
    try:
        product_id = req.rel_url.query.get("product_id")
        try:
            days = int(req.rel_url.query.get("days", "30"))
        except (ValueError, TypeError):
            days = 30
        from modules.dynamic_pricing import get_pricing_history
        history = await get_pricing_history(product_id=product_id, days=days)
        return web.json_response({"ok": True, "history": history, "count": len(history)})
    except Exception as e:
        log.error("handle_pricing_history: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_pricing_enable(req):
    """POST /api/pricing/enable — {product_id, min_price, max_price}"""
    try:
        body = await req.json()
        product_id = str(body.get("product_id", ""))
        min_price  = float(body.get("min_price", 0))
        max_price  = float(body.get("max_price", 0))
        if not product_id:
            return web.json_response({"ok": False, "error": "product_id required"}, status=400)
        from modules.dynamic_pricing import enable_auto_pricing
        result = await enable_auto_pricing(product_id, min_price, max_price)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_pricing_enable: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


# ── Email Sequence handlers ───────────────────────────────────────────────────

async def handle_email_sequence_stats(req):
    """GET /api/email/stats — open/send stats per sequence."""
    try:
        from modules.email_sequence_engine import get_sequence_stats
        result = await get_sequence_stats()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_stats: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_enroll(req):
    """POST /api/email/enroll — {email, name, sequence, metadata}"""
    try:
        body     = await req.json()
        email    = str(body.get("email", "")).strip()
        name     = str(body.get("name", "")).strip()
        sequence = str(body.get("sequence", "")).strip()
        metadata = body.get("metadata") or {}
        if not email or not sequence:
            return web.json_response(
                {"ok": False, "error": "email and sequence are required"}, status=400
            )
        from modules.email_sequence_engine import enroll_customer
        result = await enroll_customer(email, name, sequence, metadata)
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_enroll: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_process(req):
    """POST /api/email/process — process all due emails."""
    try:
        from modules.email_sequence_engine import process_due_emails
        result = await process_due_emails()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_process: %s", e)
        return web.json_response({"ok": False, "error": str(e)})


async def handle_email_sequence_enroll_new(req):
    """POST /api/email/enroll-new — auto-enroll new Shopify customers."""
    try:
        from modules.email_sequence_engine import auto_enroll_new_customers
        result = await auto_enroll_new_customers()
        return web.json_response(result)
    except Exception as e:
        log.error("handle_email_sequence_enroll_new: %s", e)
        return web.json_response({"ok": False, "error": str(e)})




# ---------------------------------------------------------------------------
# B2B PIPELINE + WHATSAPP + TIKTOK API
# ---------------------------------------------------------------------------
async def handle_b2b_pipeline_stats(req):
    try:
        from modules.b2b_pipeline import get_pipeline_stats
        stats = await get_pipeline_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_pipeline_leads(req):
    try:
        from modules.b2b_pipeline import get_pipeline_leads
        stage = req.rel_url.query.get("stage")
        try:
            limit = int(req.rel_url.query.get("limit", "50"))
        except (ValueError, TypeError):
            limit = 50
        leads = await get_pipeline_leads(stage=stage, limit=limit)
        return web.json_response({"ok": True, "leads": leads, "count": len(leads)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_add(req):
    try:
        from modules.b2b_pipeline import add_lead
        data = await req.json()
        lead = await add_lead(
            email=data.get("email", ""),
            name=data.get("name", ""),
            company=data.get("company", ""),
            website=data.get("website", ""),
            niche=data.get("niche", ""),
            source=data.get("source", "manual_import"),
            score=int(data.get("score", 0)),
            notes=data.get("notes", ""),
        )
        return web.json_response({"ok": True, "lead": lead})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_lead_update(req):
    try:
        from modules.b2b_pipeline import update_lead_stage
        data = await req.json()
        lead_id = int(data.get("id", 0))
        stage   = data.get("stage", "")
        notes   = data.get("notes", "")
        if not lead_id or not stage:
            return web.json_response({"ok": False, "error": "id and stage required"}, status=400)
        result = await update_lead_stage(lead_id, stage, notes)
        return web.json_response({"ok": True, "lead": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_prospecting_run(req):
    try:
        from modules.b2b_pipeline import run_daily_prospecting
        data = {}
        try:
            data = await req.json()
        except Exception:
            pass
        result = await run_daily_prospecting()
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_b2b_outreach_send(req):
    try:
        from modules.b2b_pipeline import send_outreach_email
        data = await req.json()
        lead_id = int(data.get("lead_id", 0))
        if not lead_id:
            return web.json_response({"ok": False, "error": "lead_id required"}, status=400)
        success = await send_outreach_email(lead_id)
        return web.json_response({"ok": success})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── WhatsApp handlers ─────────────────────────────────────────────────────────

async def handle_whatsapp_webhook_verify(req):
    """Meta webhook verification (GET)."""
    try:
        from modules.whatsapp_automation import verify_webhook
        mode      = req.rel_url.query.get("hub.mode", "")
        token     = req.rel_url.query.get("hub.verify_token", "")
        challenge = req.rel_url.query.get("hub.challenge", "")
        if mode == "subscribe":
            response = await verify_webhook(token, challenge)
            if response:
                return web.Response(text=response)
        return web.Response(status=403, text="Forbidden")
    except Exception as e:
        return web.Response(status=500, text=str(e))


async def handle_whatsapp_webhook(req):
    """Meta webhook events (POST)."""
    try:
        from modules.whatsapp_automation import process_webhook
        data = await req.json()
        await process_webhook(data)
        return web.json_response({"ok": True})
    except Exception as e:
        log.error("WhatsApp webhook error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_send(req):
    try:
        from modules.whatsapp_automation import send_message
        data = await req.json()
        to      = data.get("to", "")
        message = data.get("message", "")
        if not to or not message:
            return web.json_response({"ok": False, "error": "to and message required"}, status=400)
        success = await send_message(to, message)
        return web.json_response({"ok": success})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_broadcast(req):
    try:
        from modules.whatsapp_automation import broadcast_to_subscribers
        data    = await req.json()
        message = data.get("message", "")
        numbers = data.get("numbers", [])
        if not message or not numbers:
            return web.json_response({"ok": False, "error": "message and numbers required"}, status=400)
        result = await broadcast_to_subscribers(message, numbers)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_whatsapp_stats(req):
    try:
        from modules.whatsapp_automation import get_whatsapp_stats
        stats = await get_whatsapp_stats()
        return web.json_response({"ok": True, **stats})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── TikTok Shop handlers ──────────────────────────────────────────────────────

async def handle_tiktok_sync_products(req):
    try:
        from modules.tiktok_shop_sync import sync_products_to_tiktok
        data = {}
        try:
            data = await req.json()
        except Exception:
            pass
        limit  = int((data or {}).get("limit", 50))
        result = await sync_products_to_tiktok(limit=limit)
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_orders(req):
    try:
        from modules.tiktok_shop_sync import get_tiktok_orders
        try:
            days = int(req.rel_url.query.get("days", "7"))
        except (ValueError, TypeError):
            days = 7
        orders = await get_tiktok_orders(days=days)
        return web.json_response({"ok": True, "orders": orders, "count": len(orders)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_analytics(req):
    try:
        from modules.tiktok_shop_sync import get_tiktok_analytics
        analytics = await get_tiktok_analytics()
        return web.json_response({"ok": True, **analytics})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_combined_revenue(req):
    try:
        from modules.tiktok_shop_sync import get_combined_revenue
        revenue = await get_combined_revenue()
        return web.json_response({"ok": True, **revenue})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_tiktok_promotion(req):
    try:
        from modules.tiktok_shop_sync import create_tiktok_promotion
        data         = await req.json()
        product_id   = data.get("product_id", "")
        discount_pct = int(data.get("discount_pct", 10))
        hours        = int(data.get("hours", 24))
        if not product_id:
            return web.json_response({"ok": False, "error": "product_id required"}, status=400)
        result = await create_tiktok_promotion(product_id, discount_pct, hours)
        return web.json_response({"ok": result.get("success", False), **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── TikTok Research / Ad Library handlers ────────────────────────────────────

async def handle_tiktok_research_status(req):
    try:
        from modules.tiktok_research import check_status
        result = await check_status()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_tiktok_research_ads(req):
    """POST /api/tiktok/research/ads — query Ad Library."""
    try:
        from modules.tiktok_research import query_ads
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass

        date_min = body.get("date_min", "")
        date_max = body.get("date_max", "")
        if not date_min or not date_max:
            return web.json_response(
                {"ok": False, "error": "date_min and date_max required (YYYYMMDD)"},
                status=400,
            )

        result = await query_ads(
            date_min=date_min,
            date_max=date_max,
            country_code=body.get("country_code", "ALL"),
            search_term=body.get("search_term", ""),
            search_type=body.get("search_type", "fuzzy_phrase"),
            advertiser_business_ids=body.get("advertiser_business_ids"),
            unique_users_seen_min=body.get("unique_users_seen_min", ""),
            unique_users_seen_max=body.get("unique_users_seen_max", ""),
            max_count=int(body.get("max_count", 20)),
            search_id=body.get("search_id", ""),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── SEMrush handlers ──────────────────────────────────────────────────────────

async def handle_semrush_keyword(req):
    phrase = req.rel_url.query.get("phrase", "")
    db = req.rel_url.query.get("db", "de")
    if not phrase:
        return web.json_response({"error": "phrase required"}, status=400)
    try:
        from modules.semrush_client import keyword_overview, keyword_related
        import asyncio
        overview, related = await asyncio.gather(
            keyword_overview(phrase, db),
            keyword_related(phrase, db, 20),
        )
        return web.json_response({"phrase": phrase, "overview": overview, "related": related})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_domain(req):
    domain = req.rel_url.query.get("domain", "")
    db = req.rel_url.query.get("db", "de")
    if not domain:
        return web.json_response({"error": "domain required"}, status=400)
    try:
        from modules.semrush_client import domain_overview, domain_organic_keywords, domain_competitors, domain_backlinks
        import asyncio
        overview, keywords, competitors, backlinks = await asyncio.gather(
            domain_overview(domain, db),
            domain_organic_keywords(domain, db, 20),
            domain_competitors(domain, db, 10),
            domain_backlinks(domain),
        )
        return web.json_response({
            "domain": domain,
            "overview": overview,
            "top_keywords": keywords,
            "competitors": competitors,
            "backlinks": backlinks,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_niche(req):
    kw = req.rel_url.query.get("keyword", "")
    domain = req.rel_url.query.get("domain", None)
    db = req.rel_url.query.get("db", "de")
    if not kw:
        return web.json_response({"error": "keyword required"}, status=400)
    try:
        from modules.semrush_client import research_niche
        result = await research_niche(kw, domain, db)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_semrush_serp(req):
    phrase = req.rel_url.query.get("phrase", "")
    db = req.rel_url.query.get("db", "de")
    if not phrase:
        return web.json_response({"error": "phrase required"}, status=400)
    try:
        from modules.semrush_client import keyword_organic_results
        results = await keyword_organic_results(phrase, db)
        return web.json_response({"phrase": phrase, "serp": results})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Meta Ads handlers ─────────────────────────────────────────────────────────

async def handle_meta_ads_status(req):
    try:
        from modules.meta_ads import check_status
        return web.json_response(await check_status())
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_meta_campaigns(req):
    try:
        from modules.meta_ads import list_campaigns
        campaigns = await list_campaigns()
        return web.json_response({"ok": True, "campaigns": campaigns, "count": len(campaigns)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_campaign_create(req):
    try:
        from modules.meta_ads import create_campaign
        body = await req.json()
        result = await create_campaign(
            name=body.get("name", "SuperMegaBot Campaign"),
            objective=body.get("objective", "OUTCOME_SALES"),
            daily_budget_eur=float(body.get("daily_budget_eur", 10.0)),
            status=body.get("status", "PAUSED"),
        )
        return web.json_response({"ok": "id" in result, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_campaign_launch(req):
    """Launch full campaign (campaign + adset + creative + ad) from Shopify product."""
    try:
        from modules.meta_ads import launch_shopify_campaign
        body = await req.json()
        result = await launch_shopify_campaign(
            product_title=body.get("product_title", ""),
            product_url=body.get("product_url", ""),
            product_image=body.get("product_image", ""),
            product_price=float(body.get("product_price", 0)),
            daily_budget_eur=float(body.get("daily_budget_eur", 10.0)),
            countries=body.get("countries", ["DE", "AT", "CH"]),
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_saas_campaign(req):
    """Launch SuperMegaBot SaaS lead-gen campaign."""
    try:
        from modules.meta_ads import launch_saas_campaign
        body = {}
        try:
            body = await req.json()
        except Exception:
            pass
        result = await launch_saas_campaign(
            daily_budget_eur=float(body.get("daily_budget_eur", 20.0))
        )
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_pixel_stats(req):
    try:
        from modules.meta_ads import get_pixel_stats, get_pixel_events
        stats = await get_pixel_stats()
        events = await get_pixel_events(days=7)
        return web.json_response({"ok": True, "pixel": stats, "events_7d": events})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_meta_oauth_url(req):
    """Return the OAuth URL to generate a Meta Marketing API token."""
    app_id = os.getenv("FACEBOOK_APP_ID", "1225412136200609")
    scopes = ",".join([
        "ads_management", "ads_read", "pages_manage_ads",
        "pages_read_engagement", "pages_manage_posts",
        "instagram_basic", "instagram_content_publish",
        "business_management", "public_profile",
    ])
    redirect = "https://developers.facebook.com/tools/explorer/"
    url = (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect}"
        f"&scope={scopes}"
        f"&response_type=token"
    )
    return web.json_response({
        "ok": True,
        "oauth_url": url,
        "instructions": [
            "1. Klick den oauth_url Link",
            "2. Mit Facebook-Account einloggen (Aiitec)",
            "3. Alle Berechtigungen genehmigen",
            "4. Den generierten Token kopieren",
            "5. Als META_ADS_TOKEN in .env speichern oder hier senden"
        ],
        "required_permissions": scopes.split(","),
        "ad_account": os.getenv("META_AD_ACCOUNT_ID", ""),
        "page_id": os.getenv("FACEBOOK_PAGE_ID", ""),
    })


# ══════════════════════════════════════════════════════════════════════════════
# SALESFORCE / AGENTFORCE CRM
# ══════════════════════════════════════════════════════════════════════════════

async def handle_salesforce_stats(req):
    try:
        from modules.salesforce_client import get_stats
        return web.json_response({"ok": True, **(await get_stats())})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_leads(req):
    try:
        from modules.salesforce_client import get_leads
        status = req.rel_url.query.get("status")
        leads = await get_leads(status=status)
        return web.json_response({"ok": True, "count": len(leads), "leads": leads})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_contacts(req):
    try:
        from modules.salesforce_client import get_contacts
        contacts = await get_contacts()
        return web.json_response({"ok": True, "count": len(contacts), "contacts": contacts})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_opportunities(req):
    try:
        from modules.salesforce_client import get_opportunities
        stage = req.rel_url.query.get("stage")
        opps = await get_opportunities(stage=stage)
        return web.json_response({"ok": True, "count": len(opps), "opportunities": opps})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_create_lead(req):
    try:
        data = await req.json() if req.can_read_body else {}
        from modules.salesforce_client import create_lead
        result = await create_lead(
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", "Lead"),
            email=data.get("email", ""),
            company=data.get("company", "Unknown"),
            phone=data.get("phone", ""),
            source=data.get("source", "SuperMegaBot"),
        )
        return web.json_response({"ok": True, **result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_sync_klaviyo(req):
    try:
        from modules.salesforce_client import sync_klaviyo_to_sf
        return web.json_response(await sync_klaviyo_to_sf())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_salesforce_import_b2b(req):
    try:
        from modules.salesforce_client import import_sf_leads_to_b2b
        return web.json_response(await import_sf_leads_to_b2b())
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY AUTONOMY MASTER
# ══════════════════════════════════════════════════════════════════════════════

async def handle_autonomy_health(req):
    try:
        from modules.shopify_autonomy_master import get_service
        svc = get_service()
        return web.json_response({"ok": True, **svc.health()})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_autonomy_trigger(req):
    job_id = req.match_info.get("job_id", "")
    try:
        from modules.shopify_autonomy_master import get_service, order_orchestrator, inventory_sync, price_optimizer, telegram_digest, recovery_reconciliation, catalog_watchdog
        svc = get_service()
        job_map = {
            "order_orchestrator": order_orchestrator,
            "inventory_sync": inventory_sync,
            "price_optimizer": price_optimizer,
            "telegram_digest": telegram_digest,
            "recovery_reconciliation": recovery_reconciliation,
            "catalog_watchdog": catalog_watchdog,
        }
        if job_id not in job_map:
            return web.json_response({"ok": False, "error": f"Unknown job: {job_id}", "available": list(job_map.keys())})
        result = job_map[job_id](svc)
        return web.json_response({"ok": True, "job_id": job_id, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_autonomy_history(req):
    job_id = req.match_info.get("job_id", "")
    try:
        from modules.shopify_autonomy_master import get_service
        svc = get_service()
        history = svc.state.read(f"history:{job_id}", default={"runs": []})
        return web.json_response({"ok": True, "job_id": job_id, **history})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_queue_stats(req):
    try:
        from core.job_queue import HermesQueue
        return web.json_response(HermesQueue.get().stats())
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_queue_enqueue(req):
    try:
        data = await req.json()
        from core.job_queue import enqueue
        job_id = await enqueue(data.get("name", "notify"),
                               data.get("payload", {}),
                               data.get("priority", 5))
        return web.json_response({"ok": True, "job_id": job_id})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def create_app():
    from core.mega_orchestrator import MegaOrchestrator
    bot = MegaOrchestrator()
    await bot.start()

    # Start Hermes Job Queue
    try:
        from core.job_queue import HermesQueue
        asyncio.create_task(HermesQueue.get().start(workers=3))
        log.info("Hermes Job Queue started")
    except Exception as e:
        log.warning("Hermes start failed: %s", e)

    app = web.Application(middlewares=[logging_middleware, cors_middleware])
    app["bot"] = bot

    # Existing routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/terms",   lambda r: web.FileResponse(BASE_DIR / "dashboard" / "terms.html"))
    app.router.add_get("/privacy", lambda r: web.FileResponse(BASE_DIR / "dashboard" / "privacy.html"))
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/chat/clear", handle_chat_clear)
    # Telegram Hub Bridge endpoints
    app.router.add_post("/api/bot/execute", handle_bot_execute)
    app.router.add_get("/api/bot/commands", handle_bot_commands)
    app.router.add_get("/api/system", handle_system)
    app.router.add_get("/api/status", handle_status_legacy)
    app.router.add_get("/api/metrics", handle_metrics_legacy)
    app.router.add_get("/api/services", handle_services_legacy)
    app.router.add_get("/api/trading/prices", handle_trading_prices)
    app.router.add_get("/api/trading/arbitrage", handle_trading_arbitrage)
    app.router.add_get("/api/telegram/status", handle_telegram_status)
    app.router.add_post("/api/telegram/send", handle_telegram_send)
    app.router.add_get("/api/shopify", handle_shopify_legacy)
    app.router.add_get("/api/shopify/status", handle_shopify_status)
    app.router.add_get("/api/ollama/models", handle_ollama_models)
    app.router.add_get("/api/autopilot/agents", handle_autopilot_agents)
    app.router.add_post("/api/autopilot/run", handle_autopilot_run)
    app.router.add_get("/api/autopilot/logs", handle_autopilot_logs)
    app.router.add_post("/api/geheimwaffe/run", handle_geheimwaffe_run)
    app.router.add_post("/api/geheimwaffe/content", handle_geheimwaffe_content)
    app.router.add_get("/api/backup/status", handle_backup_status)
    app.router.add_post("/api/backup/run", handle_backup_run)
    app.router.add_post("/api/backup", handle_backup_run)

    # GMC route
    app.router.add_get("/api/gmc", handle_gmc)

    # New routes
    app.router.add_post("/api/mac/action", handle_mac_action)
    app.router.add_get("/api/services/status", handle_services_status)
    app.router.add_post("/api/services/action", handle_service_action)
    app.router.add_post("/api/service/start", handle_service_start)
    app.router.add_post("/api/service/stop", handle_service_stop)
    app.router.add_get("/api/logs", handle_logs)
    app.router.add_post("/api/logs/clear", handle_logs_clear)
    app.router.add_get("/api/processes", handle_processes)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/status/full", handle_status_full)
    app.router.add_get("/api/army/status", handle_army_status)
    app.router.add_post("/api/army/start", handle_army_start)
    app.router.add_get("/monitor", handle_monitor)
    app.router.add_post("/api/monitor/refresh", handle_monitor_refresh)

    # Self-Learner routes
    app.router.add_get("/api/self-learner/status", handle_self_learner_status)
    app.router.add_post("/api/self-learner/learn", handle_self_learner_learn)
    app.router.add_post("/api/self-learner/skills", handle_self_learner_skills)
    app.router.add_post("/api/self-learner/delete", handle_self_learner_delete)
    app.router.add_post("/api/self-learner/find-api", handle_self_learner_find_api)

    # Storage Monitor routes
    app.router.add_get("/api/storage/status",      handle_storage_status)
    app.router.add_post("/api/storage/cleanup",    handle_storage_cleanup)
    app.router.add_post("/api/storage/offload",    handle_storage_offload)
    app.router.add_get("/api/storage/large-files", handle_storage_large_files)
    app.router.add_get("/api/storage/history",     handle_storage_history)
    app.router.add_get("/storage", handle_storage_widget)

    # ── New section routes ────────────────────────────────────────────────────
    app.router.add_get("/api/keys",               handle_api_keys)
    app.router.add_get("/api/github/status",      handle_github_status)
    app.router.add_post("/api/github/push",       handle_github_push)
    app.router.add_get("/api/cloud/status",           handle_cloud_status)
    app.router.add_get("/api/pipedrive/status",        handle_pipedrive_status)
    app.router.add_get("/api/pipedrive/deals",         handle_pipedrive_deals)
    app.router.add_post("/api/pipedrive/deals",        handle_pipedrive_deal_create)
    app.router.add_get("/api/pipedrive/persons",       handle_pipedrive_persons)
    app.router.add_get("/api/railway/status",         handle_railway_status)
    app.router.add_get("/api/railway/volumes",        handle_railway_volumes)
    app.router.add_get("/api/railway/backups",        handle_railway_backups)
    app.router.add_post("/api/railway/backup/create", handle_railway_backup_create)
    app.router.add_post("/api/railway/backup/restore",handle_railway_backup_restore)
    app.router.add_get("/api/bot-repair/status",  handle_bot_repair_status)
    app.router.add_post("/api/bot-repair/run",    handle_bot_repair_run)
    app.router.add_get("/api/notes",              handle_notes_get)
    app.router.add_post("/api/notes",             handle_notes_save)
    app.router.add_delete("/api/notes",           handle_notes_delete)
    app.router.add_get("/api/deepscan",           handle_deepscan)

    # ── Automation Scheduler ──────────────────────────────────────────────────
    app.router.add_get("/api/automation/status",      handle_automation_status)
    app.router.add_post("/api/automation/run",        handle_automation_run)
    app.router.add_get("/api/automation/tasks",       handle_automation_tasks)

    # ── Social Media ──────────────────────────────────────────────────────────
    app.router.add_get("/api/social/status",          handle_social_status)

    # ── Digistore24 ───────────────────────────────────────────────────────────
    app.router.add_get("/api/digistore/status",       handle_digistore_status)
    app.router.add_get("/api/digistore/orders",       handle_digistore_orders)

    # ── Mailchimp ─────────────────────────────────────────────────────────────
    app.router.add_get("/api/mailchimp/status",       handle_mailchimp_status)
    app.router.add_post("/api/mailchimp/sync",        handle_mailchimp_sync)
    app.router.add_post("/api/mailchimp/campaign",    handle_mailchimp_campaign)
    app.router.add_post("/api/memory/save",           handle_memory_save)
    app.router.add_post("/api/notes/save",            handle_notes_save_alias)

    # ── Printify ──────────────────────────────────────────────────────────────
    app.router.add_get("/api/printify/status",        handle_printify_status)
    app.router.add_post("/api/printify/autofulfill",  handle_printify_autofulfill)

    # ── Etsy + Gumroad ────────────────────────────────────────────────────────
    app.router.add_get("/api/etsy/status",            handle_etsy_status)
    app.router.add_get("/api/gumroad/status",         handle_gumroad_status)

    # ── Revenue Aggregator ────────────────────────────────────────────────────
    app.router.add_get("/api/revenue/status",         handle_revenue_status)
    app.router.add_get("/api/revenue/report",         handle_revenue_report)

    # ── SEO Autopilot ─────────────────────────────────────────────────────────
    app.router.add_get("/api/seo/status",             handle_seo_status)
    app.router.add_post("/api/seo/run",               handle_seo_run)

    # ── Dropshipping ──────────────────────────────────────────────────────────
    app.router.add_get("/api/dropshipping/status",    handle_dropshipping_status)
    app.router.add_post("/api/dropshipping/run",      handle_dropshipping_run)

    # ── Print-on-Demand ───────────────────────────────────────────────────────
    app.router.add_get("/api/pod/status",             handle_pod_status)

    # ── Klaviyo ───────────────────────────────────────────────────────────────
    app.router.add_get("/api/klaviyo/status",         handle_klaviyo_status)
    app.router.add_get("/api/klaviyo/lists",          handle_klaviyo_lists)
    app.router.add_post("/api/klaviyo/sync",          handle_klaviyo_sync)
    app.router.add_post("/api/klaviyo/campaign",      handle_klaviyo_campaign)

    # ── Bot Clones ────────────────────────────────────────────────────────────
    app.router.add_get("/api/bots/status",            handle_bot_clones_status)
    app.router.add_post("/api/bots/run",              handle_bot_clone_run)

    # ── Watchdog + Agenten Hub ────────────────────────────────────────────────
    app.router.add_get("/api/watchdog/status",        handle_watchdog_status)
    app.router.add_get("/api/agents/hub",             handle_agents_hub)

    # ── Agent Teams ───────────────────────────────────────────────────────────
    app.router.add_get("/api/agents/teams",           handle_agents_teams_list)
    app.router.add_post("/api/agents/run",            handle_agents_teams_run)

    # ── Monetization ──────────────────────────────────────────────────────────
    app.router.add_get("/api/plans",                  handle_plans_list)
    app.router.add_post("/api/stripe/checkout",       handle_stripe_checkout)
    app.router.add_post("/api/stripe/portal",         handle_stripe_portal)
    app.router.add_post("/api/checkout",              handle_checkout_create)
    app.router.add_get("/api/mrr",                    handle_mrr)

    # ── Stripe ────────────────────────────────────────────────────────────────
    app.router.add_get("/api/stripe/status",          handle_stripe_status)
    app.router.add_get("/api/stripe/balance",         handle_stripe_balance)
    app.router.add_get("/api/stripe/charges",         handle_stripe_charges)
    app.router.add_get("/api/stripe/customers",       handle_stripe_customers)
    app.router.add_get("/api/stripe/revenue",         handle_stripe_revenue)
    app.router.add_post("/api/stripe/webhook",        handle_stripe_webhook)
    app.router.add_get("/api/stripe/mrr",             handle_stripe_mrr)
    app.router.add_get("/api/stripe/churn",           handle_stripe_churn)
    app.router.add_get("/api/stripe/subscriptions",   handle_stripe_subscriptions)
    app.router.add_post("/api/stripe/setup-products", handle_stripe_setup_products)
    app.router.add_post("/webhook/telegram",          handle_telegram_webhook)
    app.router.add_post("/api/webhook/telegram",      handle_telegram_webhook)

    # ── Google OAuth2 ─────────────────────────────────────────────────────────
    app.router.add_get("/api/google/auth",            handle_google_auth)
    app.router.add_get("/api/google/callback",        handle_google_callback)
    app.router.add_get("/api/google/status",          handle_google_status)
    app.router.add_post("/api/google/refresh",        handle_google_refresh)
    app.router.add_post("/api/google/revoke",         handle_google_revoke)

    # ── Google Drive ──────────────────────────────────────────────────────────
    app.router.add_get("/api/drive/status",           handle_drive_status)
    app.router.add_get("/api/drive/files",            handle_drive_files)
    app.router.add_post("/api/drive/backup",          handle_drive_backup)

    # ── AutoPilot CreatorHub ───────────────────────────────────────────────────
    app.router.add_get("/autopilot",                          handle_autopilot_ui)
    app.router.add_get("/api/creatorhub/status",              handle_agents_status_all)
    app.router.add_post("/api/creatorhub/run",                handle_agents_run)
    app.router.add_get("/api/creatorhub/logs",                handle_agents_logs)
    app.router.add_get("/api/agents/logs",                    handle_agents_logs)

    # ── Revenue Autopilot ──────────────────────────────────────────────────────
    app.router.add_get("/revenue",                            handle_revenue_autopilot_ui)
    app.router.add_get("/api/revenue",                       handle_revenue_legacy)
    app.router.add_get("/api/analytics",                     handle_analytics_legacy)
    app.router.add_get("/api/kpis",                          handle_kpis_legacy)
    app.router.add_get("/api/revenue/dashboard",             handle_revenue_dashboard)
    app.router.add_get("/api/revenue/summary",              handle_revenue_summary)
    app.router.add_get("/api/revenue/analytics",             handle_revenue_analytics)
    app.router.add_get("/api/revenue/abandoned-carts",       handle_abandoned_carts)
    app.router.add_post("/api/revenue/recover-carts",        handle_recover_carts)
    app.router.add_post("/api/revenue/flash-sale",           handle_flash_sale)
    app.router.add_post("/api/revenue/restore-flash-sale",   handle_restore_flash_sale)
    app.router.add_post("/api/revenue/bulk-price",           handle_bulk_price_update)
    app.router.add_get("/api/revenue/product-performance",   handle_product_performance)
    app.router.add_get("/api/revenue/products",              handle_all_products_prices)
    app.router.add_post("/api/revenue/ai-descriptions",      handle_ai_descriptions)
    app.router.add_get("/api/revenue/low-inventory",         handle_low_inventory)
    app.router.add_post("/api/revenue/publish-drafts",       handle_publish_drafts)
    app.router.add_get("/api/revenue/upsell-pairs",          handle_upsell_pairs)
    app.router.add_get("/api/youtube/dashboard",             handle_youtube_dashboard)
    app.router.add_get("/api/youtube/stats",                 handle_youtube_stats)
    app.router.add_get("/api/youtube/latest",                handle_youtube_latest)
    app.router.add_get("/api/youtube/top",                   handle_youtube_top)

    # Growth Engine
    app.router.add_get("/api/growth/dashboard",           handle_growth_dashboard)
    app.router.add_post("/api/growth/referral/create",    handle_referral_create)
    app.router.add_get("/api/growth/referral/stats",      handle_referral_stats)
    app.router.add_get("/api/growth/referral/top",        handle_referral_top)
    app.router.add_post("/api/growth/reviews/run",        handle_review_automation_run)
    app.router.add_post("/api/growth/winback/run",        handle_winback_run)

    # Dynamic Pricing + Email Sequences
    app.router.add_get("/api/pricing/dashboard",          handle_pricing_dashboard)
    app.router.add_post("/api/pricing/run",               handle_pricing_run)
    app.router.add_get("/api/pricing/history",            handle_pricing_history)
    app.router.add_post("/api/pricing/enable",            handle_pricing_enable)
    app.router.add_get("/api/email/stats",                handle_email_sequence_stats)
    app.router.add_post("/api/email/enroll",              handle_email_sequence_enroll)
    app.router.add_post("/api/email/process",             handle_email_sequence_process)
    app.router.add_post("/api/email/enroll-new",          handle_email_sequence_enroll_new)

    # B2B Pipeline + WhatsApp + TikTok
    app.router.add_get("/api/b2b/stats",                  handle_b2b_pipeline_stats)
    app.router.add_get("/api/b2b/leads",                  handle_b2b_pipeline_leads)
    app.router.add_post("/api/b2b/lead",                  handle_b2b_lead_add)
    app.router.add_post("/api/b2b/lead/update",           handle_b2b_lead_update)
    app.router.add_post("/api/b2b/prospect",              handle_b2b_prospecting_run)
    app.router.add_post("/api/b2b/outreach",              handle_b2b_outreach_send)
    app.router.add_get("/webhook/whatsapp",               handle_whatsapp_webhook_verify)
    app.router.add_post("/webhook/whatsapp",              handle_whatsapp_webhook)
    app.router.add_post("/api/whatsapp/send",             handle_whatsapp_send)
    app.router.add_post("/api/whatsapp/broadcast",        handle_whatsapp_broadcast)
    app.router.add_get("/api/whatsapp/stats",             handle_whatsapp_stats)
    app.router.add_post("/api/tiktok/sync",               handle_tiktok_sync_products)
    app.router.add_get("/api/tiktok/orders",              handle_tiktok_orders)
    app.router.add_get("/api/tiktok/analytics",           handle_tiktok_analytics)
    app.router.add_get("/api/tiktok/revenue",             handle_tiktok_combined_revenue)
    app.router.add_post("/api/tiktok/promotion",          handle_tiktok_promotion)
    app.router.add_get("/api/tiktok/research/status",     handle_tiktok_research_status)
    app.router.add_post("/api/tiktok/research/ads",       handle_tiktok_research_ads)
    app.router.add_get("/api/agents",                     handle_agents_legacy)

    # SEMrush
    # Hermes Job Queue
    app.router.add_get("/api/queue/stats",                handle_queue_stats)
    app.router.add_post("/api/queue/enqueue",             handle_queue_enqueue)

    # SEMrush
    app.router.add_get("/api/semrush/keyword",            handle_semrush_keyword)
    app.router.add_get("/api/semrush/domain",             handle_semrush_domain)
    app.router.add_get("/api/semrush/niche",              handle_semrush_niche)
    app.router.add_get("/api/semrush/serp",               handle_semrush_serp)

    # Meta Ads
    app.router.add_get("/api/meta/status",                handle_meta_ads_status)
    app.router.add_get("/api/meta/campaigns",             handle_meta_campaigns)
    app.router.add_post("/api/meta/campaign/create",      handle_meta_campaign_create)
    app.router.add_post("/api/meta/campaign/launch",      handle_meta_campaign_launch)
    app.router.add_post("/api/meta/saas-campaign",        handle_meta_saas_campaign)
    app.router.add_get("/api/meta/pixel",                 handle_meta_pixel_stats)
    app.router.add_get("/api/meta/oauth-url",             handle_meta_oauth_url)

    # ── Salesforce handlers injected here (defined above create_app) ──────────
    # Salesforce / Agentforce CRM
    app.router.add_get("/api/salesforce/stats",           handle_salesforce_stats)
    app.router.add_get("/api/salesforce/leads",           handle_salesforce_leads)
    app.router.add_get("/api/salesforce/contacts",        handle_salesforce_contacts)
    app.router.add_get("/api/salesforce/opportunities",   handle_salesforce_opportunities)
    app.router.add_post("/api/salesforce/lead",           handle_salesforce_create_lead)
    app.router.add_post("/api/salesforce/sync/klaviyo",   handle_salesforce_sync_klaviyo)
    app.router.add_post("/api/salesforce/sync/b2b",       handle_salesforce_import_b2b)

    # Shopify Autonomy Master
    app.router.add_get("/api/autonomy/health",            handle_autonomy_health)
    app.router.add_post("/api/autonomy/trigger/{job_id}", handle_autonomy_trigger)
    app.router.add_get("/api/autonomy/history/{job_id}",  handle_autonomy_history)

    return app


def _free_port(port: int) -> None:
    """Kill whatever holds the port (macOS + Linux)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
                log.info("Killed PID %s on port %s", pid, port)
            except Exception:
                pass
    except Exception:
        pass


async def handle_telegram_webhook(req):
    """Handle incoming Telegram webhook messages via Railway deployment."""
    try:
        data = await req.json()
        log.info("📨 Telegram webhook: %s", json.dumps(data, indent=2)[:500])
        
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            user = message.get("from", {})
            
            # Process through existing bot system
            bot = req.app["bot"]
            response = await bot.process(text, f"tg-{chat_id}")
            
            # Send response back
            if TELEGRAM_TOKEN:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                async with aiohttp.ClientSession() as s:
                    await s.post(url, json={
                        "chat_id": chat_id,
                        "text": response[:3800] or "(leere Antwort)",
                        "disable_web_page_preview": True
                    })
            
        return web.json_response({"status": "ok"})
    except Exception as e:
        log.error("Telegram webhook error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _register_telegram_webhook():
    """Auto-register Telegram webhook on Railway startup."""
    railway_url = os.getenv("RAILWAY_STATIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_url and TELEGRAM_TOKEN:
        base = f"https://{railway_url}" if not railway_url.startswith("http") else railway_url
        try:
            wh_url = f"{base}/webhook/telegram"
            async with aiohttp.ClientSession() as s:
                r = await s.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
                    json={"url": wh_url, "allowed_updates": ["message", "edited_message"]}
                )
                result = await r.json()
                log.info("Telegram webhook set: %s → %s", wh_url, result.get("description", ""))
        except Exception as e:
            log.warning("Telegram webhook setup failed: %s", e)


if __name__ == "__main__":
    async def _main():
        # Startup ENV check
        missing = [v for v in ["TELEGRAM_BOT_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SUPABASE_URL"] if not os.getenv(v)]
        if missing:
            log.warning("⚠️ Fehlende ENV-Variablen: %s", ', '.join(missing))

        log.info("Prüfe Port %s...", PORT)
        _free_port(PORT)
        import asyncio as _aio
        await _aio.sleep(0.5)   # kurz warten damit OS den Port freigibt

        app = await create_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True)
        await site.start()
        log.info("SuperMegaBot Dashboard läuft auf http://localhost:%s", PORT)
        
        # Auto-register Telegram webhook on Railway
        await _register_telegram_webhook()
        
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    asyncio.run(_main())
