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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path.home()))

from aiohttp import web
import aiohttp


def _client_session(total_timeout: int = 15):
  resolver = aiohttp.resolver.ThreadedResolver()
  connector = aiohttp.TCPConnector(resolver=resolver, ttl_dns_cache=300)
  timeout = aiohttp.ClientTimeout(total=total_timeout)
  return aiohttp.ClientSession(timeout=timeout, connector=connector)

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

PORT = int(os.getenv("DASHBOARD_PORT", "8888"))

log = logging.getLogger("Dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Service definitions for Start/Stop control
# ---------------------------------------------------------------------------

SERVICES = [
    {"id": "dashboard", "name": "SuperMegaBot", "port": 8888,
     "start_cmd": "cd /Users/rudolfsarkany/supermegabot && python3 dashboard/server.py",
     "pattern": "dashboard/server.py", "icon": "🤖"},
    {"id": "telegram_bot", "name": "Telegram Bot", "port": 3200,
     "start_cmd": "cd '/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/telegram-automation-bot' && nohup node server.js >> logs/server.log 2>&1 &",
     "pattern": "telegram-automation-bot.*server.js", "icon": "✈️"},
    {"id": "cratorhub", "name": "CreatorHub", "port": 3002,
     "start_cmd": "cd '/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/digifabrik' && nohup npx tsx server.ts >> /tmp/cratorhub.log 2>&1 &",
     "pattern": "digifabrik.*server", "icon": "🎨"},
    {"id": "ollama", "name": "Ollama LLM", "port": 11434,
     "start_cmd": "ollama serve &",
     "pattern": "ollama serve", "icon": "🧠"},
    {"id": "openclaw", "name": "OpenClaw Gateway", "port": 18789,
     "start_cmd": "openclaw gateway run",
     "pattern": "openclaw", "icon": "🦞"},
    {"id": "windsurf_shopify_suite", "name": "Shopify Webhook Suite", "port": 3001,
     "start_cmd": "cd /Users/rudolfsarkany/windsurf-shopify-suite && nohup npm start >> /tmp/windsurf-shopify-suite.log 2>&1 &",
     "pattern": "windsurf-shopify-suite", "icon": "🛒"},
    {"id": "windsurf_telegram_bot", "name": "Windsurf Telegram Bot", "port": 8000,
     "start_cmd": "cd /Users/rudolfsarkany/windsurf-telegram-bot && nohup npm start >> /tmp/windsurf-telegram-bot.log 2>&1 &",
     "pattern": "windsurf-telegram-bot.*index.js", "icon": "🤖"},
    # ── Heute gebaut ────────────────────────────────────────────────────────
    {"id": "shopify_ai_suite", "name": "Shopify AI Suite (Railway)", "port": 0,
     "start_cmd": "echo 'Deployed on Railway: https://shopify-suite-v2-production.up.railway.app'",
     "pattern": "RAILWAY_REMOTE",
     "url": "https://shopify-suite-v2-production.up.railway.app",
     "health_url": "https://shopify-suite-v2-production.up.railway.app/health",
     "icon": "🛍️"},
    {"id": "windsurf_shopify", "name": "Windsurf API Gateway", "port": 8080,
     "start_cmd": "cd /Users/rudolfsarkany/windsurf-api-gateway && nohup node src/index.js >> /tmp/windsurf-api-gateway.log 2>&1 &",
     "pattern": "windsurf-api-gateway.*index.js", "icon": "🌊"},
    {"id": "windsurf_autoheal", "name": "Windsurf Auto-Heal", "port": 9000,
     "start_cmd": "cd /Users/rudolfsarkany/windsurf-auto-heal && nohup npm start >> /tmp/windsurf-autoheal.log 2>&1 &",
     "pattern": "windsurf-auto-heal.*index.js", "icon": "🏥"},
    {"id": "password_sync", "name": "Password Sync", "port": 3005,
     "start_cmd": "cd /Users/rudolfsarkany/password-sync-suite/web-app && PORT=3005 nohup npm start >> /tmp/password-sync.log 2>&1 &",
     "pattern": "password-sync-suite.*server.js", "icon": "🔐"},
    {"id": "rudibot_eternal", "name": "RudiBot Eternal", "port": 0,
     "start_cmd": "cd /Users/rudolfsarkany/rudibot-eternal && nohup python3 immortal_bot.py >> /tmp/rudibot-eternal.log 2>&1 &",
     "pattern": "immortal_bot.py", "icon": "♾️"},
    {"id": "kivo", "name": "KIVO Voice", "port": 0,
     "start_cmd": "cd /Users/rudolfsarkany/kivo && nohup python3 kivo.py >> /tmp/kivo.log 2>&1 &",
     "pattern": "kivo.py", "icon": "🎙️"},
]

# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SuperMegaBot Dashboard</title>
<style>
:root {
  --bg: #0a0a0f;
  --surface: #12121a;
  --card: #1a1a26;
  --accent: #6c63ff;
  --accent2: #ff6584;
  --green: #43d98c;
  --yellow: #ffd700;
  --red: #ff4757;
  --orange: #ff6b35;
  --text: #e8e8f0;
  --muted: #7070a0;
  --border: #2a2a40;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
  min-height: 100vh;
}

/* ── Header ── */
.header {
  background: linear-gradient(135deg, var(--accent) 0%, #9f7aea 100%);
  padding: 16px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 20px rgba(108,99,255,0.4);
  flex-wrap: wrap;
  gap: 10px;
}
.header h1 { font-size: 1.6rem; font-weight: 700; color: #fff; }
.header .subtitle { font-size: 0.8rem; opacity: 0.85; margin-top: 2px; }
.header-center { font-size: 1.1rem; font-weight: 600; color: rgba(255,255,255,0.9); }
.header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.status-pill {
  background: rgba(255,255,255,0.2);
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.78rem;
  display: flex; align-items: center; gap: 6px;
}
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
@keyframes slideIn { from{transform:translateX(100px);opacity:0} to{transform:translateX(0);opacity:1} }

/* Quick action bar */
.quick-bar {
  background: rgba(0,0,0,0.3);
  padding: 10px 28px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border);
}
.quick-btn {
  background: rgba(108,99,255,0.2);
  border: 1px solid rgba(108,99,255,0.4);
  color: var(--text);
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 500;
  transition: all 0.2s;
}
.quick-btn:hover { background: rgba(108,99,255,0.4); transform: translateY(-1px); }

/* ── Grid ── */
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 20px 24px;
  max-width: 1800px;
  margin: 0 auto;
}
@media (max-width: 1400px) { .grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 1000px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px)  { .grid { grid-template-columns: 1fr; } }

.col-2 { grid-column: span 2; }
.col-3 { grid-column: span 3; }
.col-4 { grid-column: span 4; }
@media (max-width: 1400px) { .col-4 { grid-column: span 3; } }
@media (max-width: 1000px) { .col-2,.col-3,.col-4 { grid-column: span 2; } }
@media (max-width: 640px)  { .col-2,.col-3,.col-4 { grid-column: span 1; } }

/* ── Card ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 18px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
.card-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
}
.card-icon {
  width: 38px; height: 38px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center; font-size: 1.2rem; flex-shrink: 0;
}
.card-title { font-size: 0.95rem; font-weight: 600; }
.card-subtitle { font-size: 0.72rem; color: var(--muted); }

/* ── Stat bars ── */
.stat-bar { margin: 8px 0; }
.stat-label { display: flex; justify-content: space-between; font-size: 0.78rem; margin-bottom: 4px; }
.bar-track { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s; }
.bar-green  { background: linear-gradient(90deg, var(--green), #6edfa0); }
.bar-yellow { background: linear-gradient(90deg, var(--yellow), #ffec6e); }
.bar-red    { background: linear-gradient(90deg, var(--red), #ff758c); }
.bar-accent { background: linear-gradient(90deg, var(--accent), #9f7aea); }

/* ── Stats grid ── */
.stats-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat-box { background: var(--surface); border-radius: 10px; padding: 10px; text-align: center; }
.stat-value { font-size: 1.4rem; font-weight: 700; color: var(--accent); }
.stat-label-sm { font-size: 0.68rem; color: var(--muted); margin-top: 2px; }

/* ── Chat ── */
.chat-box {
  background: var(--surface); border-radius: 10px;
  height: 220px; overflow-y: auto; padding: 10px;
  margin-bottom: 10px; display: flex; flex-direction: column; gap: 8px;
}
.msg { max-width: 85%; padding: 8px 12px; border-radius: 12px; font-size: 0.83rem; line-height: 1.4; }
.msg-user { align-self: flex-end; background: var(--accent); color: #fff; }
.msg-bot  { align-self: flex-start; background: var(--border); }
.chat-input-row { display: flex; gap: 8px; }
.chat-input {
  flex: 1; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 9px 12px; color: var(--text); font-size: 0.83rem; outline: none;
}
.chat-input:focus { border-color: var(--accent); }

/* ── Buttons ── */
.btn {
  padding: 7px 14px; border-radius: 8px; border: none; cursor: pointer;
  font-size: 0.8rem; font-weight: 500; transition: opacity 0.2s, transform 0.1s;
}
.btn:hover { opacity: 0.85; transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn-primary { background: var(--accent); color: #fff; }
.btn-green   { background: var(--green); color: #000; }
.btn-red     { background: var(--red); color: #fff; }
.btn-orange  { background: var(--orange); color: #fff; }
.btn-ghost   { background: var(--border); color: var(--text); }
.btn-sm      { padding: 4px 9px; font-size: 0.72rem; }
.btn-xs      { padding: 2px 7px; font-size: 0.68rem; border-radius: 5px; }

/* ── Tables ── */
.table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
.table th { color: var(--muted); font-weight: 500; padding: 5px 7px; text-align: left; border-bottom: 1px solid var(--border); }
.table td { padding: 5px 7px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.badge { padding: 2px 7px; border-radius: 20px; font-size: 0.68rem; font-weight: 600; }
.badge-green  { background: rgba(67,217,140,0.18); color: var(--green); }
.badge-red    { background: rgba(255,71,87,0.18); color: var(--red); }
.badge-yellow { background: rgba(255,215,0,0.18); color: var(--yellow); }
.badge-orange { background: rgba(255,107,53,0.18); color: var(--orange); }

/* ── Service rows ── */
.svc-row {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 8px; background: var(--surface);
  margin-bottom: 6px;
}
.svc-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.svc-dot.on  { background: var(--green); box-shadow: 0 0 6px var(--green); }
.svc-dot.off { background: var(--red); }
.svc-name { flex: 1; font-size: 0.82rem; font-weight: 500; }
.svc-port { font-size: 0.68rem; color: var(--muted); margin-right: 4px; }
.svc-btns { display: flex; gap: 4px; }

/* ── Mac control ── */
.mac-output {
  margin-top: 10px; font-size: 0.78rem; background: var(--surface);
  border-radius: 8px; padding: 10px; min-height: 50px; white-space: pre-wrap;
  color: var(--green); font-family: monospace; max-height: 120px; overflow-y: auto;
}
.mac-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }

/* ── Log box ── */
.log-box {
  background: #050508; border-radius: 8px; padding: 10px;
  height: 200px; overflow-y: auto; font-family: monospace;
  font-size: 0.72rem; color: var(--green); line-height: 1.5;
}

/* ── AutoPilot ── */
#agent-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; margin-bottom: 14px; }
.agent-card {
  background: var(--surface); border-radius: 10px; padding: 10px 6px;
  text-align: center; cursor: pointer; border: 1px solid var(--border);
  transition: all 0.2s;
}
.agent-card:hover { border-color: var(--accent); }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── Misc ── */
.loading { opacity: 0.5; font-style: italic; font-size: 0.78rem; }
.error-text { color: var(--red); font-size: 0.78rem; }
.vol-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
input[type=range] { flex: 1; accent-color: var(--accent); }

/* ── Tabs ── */
.tab-nav {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex; gap: 2px; padding: 0 16px;
  overflow-x: auto; scrollbar-width: none;
}
.tab-nav::-webkit-scrollbar { display: none; }
.tab-btn {
  padding: 11px 16px; background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted); cursor: pointer; font-size: 0.82rem; white-space: nowrap;
  font-family: inherit; transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.tab-iframe {
  width: 100%; height: calc(100vh - 118px); border: none;
  background: var(--surface); display: block;
}
/* ── Remote Desktop Card ── */
.crd-input {
  width: 100%; background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; font-size: 0.78rem; font-family: monospace;
  margin-bottom: 8px; resize: vertical; min-height: 54px;
}
.crd-input:focus { outline: none; border-color: var(--accent); }
</style>
</head>
<body>

<!-- ══ HEADER ══ -->
<div class="header">
  <div>
    <h1>SuperMegaBot 🤖</h1>
    <div class="subtitle">M4 Pro · 48GB · macOS · 95% Lokal</div>
  </div>
  <div class="header-center" id="clock"></div>
  <div class="header-right">
    <div class="status-pill"><div class="dot"></div><span id="bot-status">Online</span></div>
  </div>
</div>

<!-- ══ QUICK ACTION BAR ══ -->
<div class="quick-bar">
  <button class="quick-btn" onclick="quickMac('screenshot')">📸 Screenshot</button>
  <button class="quick-btn" onclick="quickNotify()">🔔 Benachrichtigung</button>
  <button class="quick-btn" onclick="quickMac('lock')">🔒 Sperren</button>
  <button class="quick-btn" onclick="quickMac('sleep_display')">🌙 Display aus</button>
</div>

<!-- ══ TAB NAV ══ -->
<div class="tab-nav">
  <button class="tab-btn active" data-tab="home" onclick="switchTab('home')">🤖 SuperMegaBot</button>
  <button class="tab-btn" data-tab="telegram" onclick="switchTab('telegram')">✈️ Telegram Bot</button>
  <button class="tab-btn" data-tab="shopify-apps" onclick="switchTab('shopify-apps')">🛒 Shopify Apps</button>
  <button class="tab-btn" data-tab="nailschip" onclick="switchTab('nailschip')">💅 NailsChip</button>
  <button class="tab-btn" data-tab="revenue" onclick="switchTab('revenue')">💰 Revenue Hub</button>
  <button class="tab-btn" data-tab="income" onclick="switchTab('income')">📊 Income Engine</button>
  <button class="tab-btn" data-tab="social" onclick="switchTab('social')">🌐 Social</button>
  <button class="tab-btn" data-tab="windsurf-shopify" onclick="switchTab('windsurf-shopify')">🏪 Windsurf Shop</button>
  <button class="tab-btn" data-tab="password-sync" onclick="switchTab('password-sync')">🔑 Passwort Sync</button>
  <button class="tab-btn" data-tab="cratorhub" onclick="switchTab('cratorhub')">🎨 CreatorHub</button>
  <button class="tab-btn" data-tab="remote" onclick="switchTab('remote')">🖥️ Remote Desktop</button>
  <button class="tab-btn" data-tab="rudiclone" onclick="switchTab('rudiclone')">🧬 Rudiclone</button>
</div>

<!-- ══ TAB: HOME (SuperMegaBot Dashboard) ══ -->
<div id="tab-home" class="tab-panel active">

<!-- ══ MAIN GRID ══ -->
<div class="grid">

  <!-- ── Services (2 cols) ── -->
  <div class="card col-2">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#43d98c,#00b894)">⚡</div>
      <div><div class="card-title">Services</div><div class="card-subtitle">Live Status · Start/Stop</div></div>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="loadServices()">↺ Refresh</button>
    </div>
    <div id="services-list"><div class="loading">Prüfe Services...</div></div>
  </div>

  <!-- ── System Stats (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#667eea,#764ba2)">💻</div>
      <div><div class="card-title">System</div><div class="card-subtitle" id="sys-uptime">M4 Pro · 48GB RAM</div></div>
    </div>
    <div class="stat-bar">
      <div class="stat-label"><span>CPU</span><span id="cpu-val">–</span></div>
      <div class="bar-track"><div class="bar-fill bar-accent" id="cpu-bar" style="width:0%"></div></div>
    </div>
    <div class="stat-bar">
      <div class="stat-label"><span>RAM</span><span id="ram-val">–</span></div>
      <div class="bar-track"><div class="bar-fill bar-green" id="ram-bar" style="width:0%"></div></div>
    </div>
    <div class="stat-bar">
      <div class="stat-label"><span>SSD</span><span id="disk-val">–</span></div>
      <div class="bar-track"><div class="bar-fill bar-yellow" id="disk-bar" style="width:0%"></div></div>
    </div>
    <div class="stats-2" style="margin-top:10px">
      <div class="stat-box"><div class="stat-value" id="cpu-cores">14</div><div class="stat-label-sm">CPU Kerne</div></div>
      <div class="stat-box"><div class="stat-value" id="proc-count">–</div><div class="stat-label-sm">Prozesse</div></div>
    </div>
  </div>

  <!-- ── Mac Control (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">🖥️</div>
      <div><div class="card-title">Mac Steuerung</div><div class="card-subtitle">Direkte Aktionen</div></div>
    </div>

    <div class="vol-row">
      <span style="font-size:0.75rem;color:var(--muted)">🔊</span>
      <input type="range" id="vol-slider" min="0" max="100" value="50">
      <span id="vol-val" style="font-size:0.75rem;min-width:28px">50</span>
      <button class="btn btn-ghost btn-sm" onclick="setVolume()">Set</button>
    </div>

    <div class="mac-actions">
      <button class="btn btn-ghost btn-sm" onclick="macAction('clipboard_get')">📋 Clipboard</button>
      <button class="btn btn-ghost btn-sm" onclick="macAction('empty_trash')">🗑️ Papierkorb</button>
      <button class="btn btn-ghost btn-sm" onclick="macOpenUrl()">🌐 URL öffnen</button>
      <button class="btn btn-ghost btn-sm" onclick="macAction('running_apps')">📱 Apps</button>
      <button class="btn btn-ghost btn-sm" onclick="macAction('system_info')">ℹ️ System Info</button>
      <button class="btn btn-ghost btn-sm" onclick="loadProcesses()">⚙️ Prozesse</button>
    </div>
    <div class="mac-output" id="mac-output">Bereit.</div>
  </div>

  <!-- ── KI Chat (2 cols) ── -->
  <div class="card col-2">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)">🤖</div>
      <div><div class="card-title">KI-Assistent</div><div class="card-subtitle">Ollama · 100% lokal</div></div>
      <div style="margin-left:auto;display:flex;gap:6px;align-items:center">
        <select id="model-select" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:0.72rem">
          <option value="gemma4" selected>gemma4 (schnell)</option>
          <option value="fast">llama3.2</option>
          <option value="code">codellama</option>
          <option value="analysis">mistral</option>
        </select>
      </div>
    </div>
    <div class="chat-box" id="chat-box">
      <div class="msg msg-bot">Hallo! Ich bin SuperMegaBot. Was kann ich für dich tun?</div>
    </div>
    <div class="chat-input-row">
      <input class="chat-input" id="chat-input" placeholder="Schreib eine Nachricht..." onkeydown="if(event.key==='Enter')sendChat()">
      <button class="btn btn-primary" onclick="sendChat()">Senden</button>
      <button class="btn btn-ghost btn-sm" onclick="clearChat()">✕</button>
    </div>
  </div>

  <!-- ── Trading Bot (2 cols) ── -->
  <div class="card col-2">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#ffd700,#ff6b35)">📈</div>
      <div><div class="card-title">Trading Bot</div><div class="card-subtitle">Multi-Exchange Arbitrage</div></div>
      <div style="margin-left:auto;display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="loadPrices()">🔄 Preise laden</button>
        <button class="btn btn-green btn-sm" onclick="scanArbitrage()">📊 Arbitrage scannen</button>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <div>
        <div style="font-size:0.7rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em">LIVE PREISE</div>
        <div id="prices-list" class="loading">Lade Preise...</div>
      </div>
      <div>
        <div style="font-size:0.7rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em">ARBITRAGE CHANCEN</div>
        <div id="arb-list" class="loading">Scan läuft...</div>
      </div>
    </div>
  </div>

  <!-- ── Telegram (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#0088cc,#00b4d8)">✈️</div>
      <div><div class="card-title">Telegram</div><div class="card-subtitle">Bot Status & Senden</div></div>
    </div>
    <div id="tg-status" class="loading" style="margin-bottom:10px;font-size:0.82rem">Prüfe...</div>
    <input id="tg-msg" class="chat-input" placeholder="Nachricht senden..." style="width:100%;margin-bottom:8px">
    <button class="btn btn-primary" style="width:100%" onclick="sendTelegram()">✈️ Senden</button>
  </div>

  <!-- ── Shopify (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#96f7d2,#08d4a5)">🛒</div>
      <div><div class="card-title">Shopify</div><div class="card-subtitle">Store Analytics</div></div>
    </div>
    <div id="shopify-data" class="loading" style="font-size:0.82rem;margin-bottom:10px">Lade Shopify...</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="loadShopify()">↺ Status</button>
      <button class="btn btn-ghost btn-sm" onclick="shopifyAction('products')">Produkte</button>
      <button class="btn btn-ghost btn-sm" onclick="shopifyAction('orders')">Bestellungen</button>
      <button class="btn btn-ghost btn-sm" onclick="shopifyAction('analytics')">Analytics</button>
    </div>
  </div>

  <!-- ── GMC Status (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#4285f4,#34a853)">🛒</div>
      <div><div class="card-title">Google Merchant Center</div><div class="card-subtitle">GMC Status & Produkte</div></div>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="loadGMC()">↺</button>
    </div>
    <div id="gmc-data"><div class="loading">Lade GMC...</div></div>
  </div>

  <!-- ── Ollama Models (1 col) ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#a18cd1,#fbc2eb)">🧠</div>
      <div><div class="card-title">Ollama Models</div><div class="card-subtitle">Lokal · Kostenlos</div></div>
    </div>
    <div id="models-list" class="loading" style="display:flex;flex-direction:column;gap:6px">Lade Models...</div>
  </div>

  <!-- ── Live Logs (2 cols) ── -->
  <div class="card col-2">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#2d3436,#636e72)">📜</div>
      <div><div class="card-title">Live Logs</div><div class="card-subtitle">Letzte 80 Zeilen</div></div>
      <div style="margin-left:auto;display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="loadLogs()">↺ Aktualisieren</button>
        <button class="btn btn-red btn-sm" onclick="clearLogs()">🗑️ Löschen</button>
      </div>
    </div>
    <div class="log-box" id="log-box"><div style="opacity:0.4">Lade Logs...</div></div>
  </div>

  <!-- ── AutoPilot (full width) ── -->
  <div class="card col-4" style="border:1px solid rgba(108,99,255,0.4);background:linear-gradient(135deg,rgba(108,99,255,0.08),rgba(159,122,234,0.05))">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#6c63ff,#9f7aea);font-size:1.4rem">🚀</div>
      <div>
        <div class="card-title" style="font-size:1.05rem">AutoPilot Modus</div>
        <div class="card-subtitle">Multi-Agent AI System · CEO + 7 Spezial-Agenten · Lokal via Ollama</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <div id="autopilot-status-dot" class="dot" style="background:var(--muted)"></div>
        <span id="autopilot-status-text" style="font-size:0.78rem;color:var(--muted)">Bereit</span>
      </div>
    </div>
    <div id="agent-grid"></div>
    <div style="background:var(--surface);border-radius:12px;padding:14px">
      <div style="font-size:0.7rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em">AutoPilot Ziel</div>
      <textarea id="autopilot-goal"
        style="width:100%;background:transparent;border:1px solid var(--border);border-radius:8px;padding:10px;color:var(--text);font-size:0.83rem;resize:vertical;min-height:70px;outline:none;font-family:inherit"
        placeholder="Beschreibe dein Ziel z.B.: 'Analysiere meinen Shopify Store und erstelle einen Optimierungsplan'"></textarea>
      <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="runAutoPilot()" style="flex:1;min-width:140px">🚀 AutoPilot starten</button>
        <select id="agent-select" style="background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:7px;font-size:0.8rem">
          <option value="">Auto (CEO entscheidet)</option>
          <option value="ceo">👑 CEO Agent</option>
          <option value="shopify">🛒 Shopify Agent</option>
          <option value="marketing">📣 Marketing Agent</option>
          <option value="coding">💻 Coding Agent</option>
          <option value="research">🔬 Research Agent</option>
          <option value="finance">💰 Finance Agent</option>
          <option value="automation">⚙️ Automation Agent</option>
          <option value="security">🛡️ Security Agent</option>
        </select>
        <button class="btn btn-ghost btn-sm" onclick="loadAgentLogs()">📋 Logs</button>
      </div>
    </div>
    <div id="autopilot-results" style="margin-top:10px;display:flex;flex-direction:column;gap:8px;max-height:400px;overflow-y:auto"></div>
  </div>

  <!-- ── GEHEIMWAFFE (2 cols) ── -->
  <div class="card col-2" style="border:1px solid rgba(255,215,0,0.4);background:linear-gradient(135deg,rgba(255,215,0,0.06),rgba(255,107,53,0.04))">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#ffd700,#ff6b35);font-size:1.3rem">⚔️</div>
      <div>
        <div class="card-title" style="font-size:1.05rem">GEHEIMWAFFE</div>
        <div class="card-subtitle">Automated Shopify Growth · Winning Products · AI Content · Viral Ads</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div style="background:var(--surface);border-radius:10px;padding:12px">
        <div style="font-size:0.7rem;color:var(--muted);margin-bottom:7px;text-transform:uppercase">Nische / Produkt</div>
        <input id="gw-niche" class="chat-input" placeholder="z.B. Haustiere, Fitness, Baby..." style="width:100%;margin-bottom:7px">
        <button class="btn btn-primary" style="width:100%;background:linear-gradient(135deg,#ffd700,#ff6b35);color:#000" onclick="runGeheimwaffe()">
          ⚔️ GEHEIMWAFFE AKTIVIEREN
        </button>
      </div>
      <div style="background:var(--surface);border-radius:10px;padding:12px">
        <div style="font-size:0.7rem;color:var(--muted);margin-bottom:7px;text-transform:uppercase">Schnell-Content</div>
        <input id="gw-product" class="chat-input" placeholder="Produktname..." style="width:100%;margin-bottom:6px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">
          <button class="btn btn-ghost btn-sm" onclick="gwContent('listing')">📝 Listing</button>
          <button class="btn btn-ghost btn-sm" onclick="gwContent('social','tiktok')">🎵 TikTok</button>
          <button class="btn btn-ghost btn-sm" onclick="gwContent('social','instagram')">📸 Instagram</button>
          <button class="btn btn-ghost btn-sm" onclick="gwContent('ads')">📣 Ads</button>
        </div>
      </div>
    </div>
    <div id="gw-results" style="margin-top:10px;background:var(--surface);border-radius:10px;padding:12px;min-height:70px;font-size:0.8rem;white-space:pre-wrap;display:none"></div>
  </div>

  <!-- ── Agent Task History (2 cols) ── -->
  <div class="card col-2">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)">📋</div>
      <div><div class="card-title">Agent Task-History</div><div class="card-subtitle">Alle ausgeführten Aufgaben</div></div>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="loadAgentLogs()">↺ Refresh</button>
    </div>
    <div id="agent-logs" style="font-size:0.75rem;display:flex;flex-direction:column;gap:5px;max-height:180px;overflow-y:auto">
      <div class="loading">Lade Logs...</div>
    </div>
  </div>

  <!-- ── Backup & Bot Integration ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#2d3436,#636e72)">💾</div>
      <div><div class="card-title">Backups & Bots</div><div class="card-subtitle">Bestehende Bots integriert</div></div>
    </div>
    <div style="font-size:0.78rem;display:flex;flex-direction:column;gap:7px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>windsurf-telegram-bot</span><span class="badge badge-green">✓ Integriert</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>windsurf-auto-heal</span><span class="badge badge-green">✓ Aktiv</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>CreatorHub Server</span><span class="badge badge-yellow">Port 3002</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>Shopify AI Suite</span><span class="badge badge-green">✓ Keys OK</span>
      </div>
    </div>
    <button class="btn btn-ghost btn-sm" style="margin-top:10px;width:100%" onclick="runBackup()">💾 Backup jetzt</button>
    <div id="backup-result" style="margin-top:5px;font-size:0.72rem;color:var(--muted)"></div>
  </div>

  <!-- ── Self-Healing Log ── -->
  <div class="card">
    <div class="card-header">
      <div class="card-icon" style="background:linear-gradient(135deg,#ff6b6b,#ee5a24)">🔧</div>
      <div><div class="card-title">Self-Healing</div><div class="card-subtitle">Auto-Reparatur Log</div></div>
    </div>
    <div id="heal-log" style="font-size:0.75rem;background:var(--surface);border-radius:8px;padding:10px;height:140px;overflow-y:auto;font-family:monospace">
      <div style="color:var(--green)">✓ System bereit</div>
      <div style="color:var(--green)">✓ Self-Healing aktiv</div>
      <div style="color:var(--green)">✓ Pattern Learning läuft</div>
    </div>
  </div>

</div><!-- /grid -->
</div><!-- /tab-home -->

<!-- ══ TAB: Telegram Bot ══ -->
<div id="tab-telegram" class="tab-panel">
  <iframe class="tab-iframe" data-local-url="http://localhost:3200" title="Telegram Bot"></iframe>
</div>

<!-- ══ TAB: Shopify Apps Suite ══ -->
<div id="tab-shopify-apps" class="tab-panel">
  <iframe class="tab-iframe" data-path="/shopify-apps" title="Shopify Apps"></iframe>
</div>

<!-- ══ TAB: NailsChip Studio ══ -->
<div id="tab-nailschip" class="tab-panel">
  <iframe class="tab-iframe" data-path="/nailschip" title="NailsChip"></iframe>
</div>

<!-- ══ TAB: Revenue Hub ══ -->
<div id="tab-revenue" class="tab-panel">
  <iframe class="tab-iframe" data-path="/revenue" title="Revenue Hub"></iframe>
</div>

<!-- ══ TAB: Income Engine ══ -->
<div id="tab-income" class="tab-panel">
  <iframe class="tab-iframe" data-path="/income" title="Income Engine"></iframe>
</div>

<!-- ══ TAB: Social ══ -->
<div id="tab-social" class="tab-panel">
  <iframe class="tab-iframe" data-path="/social" title="Social"></iframe>
</div>

<!-- ══ TAB: Windsurf Shopify ══ -->
<div id="tab-windsurf-shopify" class="tab-panel">
  <iframe class="tab-iframe" src="https://shopify-suite-v2-production.up.railway.app" title="Windsurf Shopify"></iframe>
</div>

<!-- ══ TAB: Password Sync ══ -->
<div id="tab-password-sync" class="tab-panel">
  <iframe class="tab-iframe" src="http://localhost:3005" title="Password Sync"></iframe>
</div>

<!-- ══ TAB: CreatorHub ══ -->
<div id="tab-cratorhub" class="tab-panel">
  <iframe class="tab-iframe" src="http://localhost:3002" title="CreatorHub"></iframe>
</div>

<!-- ══ TAB: Remote Desktop ══ -->
<div id="tab-remote" class="tab-panel">
  <div style="padding:32px;max-width:700px;margin:0 auto">
    <div class="card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">🖥️</div>
        <div><div class="card-title">Chrome Remote Desktop</div><div class="card-subtitle">Host-Registrierung</div></div>
      </div>
      <p style="font-size:0.82rem;color:var(--muted);margin-bottom:14px">
        Hole den Auth-Code von <a href="https://remotedesktop.google.com/headless" target="_blank" style="color:var(--accent)">remotedesktop.google.com/headless</a>
        und füge ihn hier ein.
      </p>
      <label style="font-size:0.75rem;color:var(--muted);display:block;margin-bottom:4px">Auth Code (--code=...)</label>
      <textarea class="crd-input" id="crd-code" placeholder="4/0AeoWuM_bnLD2e3zP8tn2..."></textarea>
      <button class="btn btn-primary" style="width:100%;margin-bottom:10px" onclick="registerCRD()">🖥️ Remote Desktop registrieren</button>
      <div id="crd-result" style="font-size:0.78rem;font-family:monospace;background:var(--surface);border-radius:8px;padding:10px;min-height:40px;white-space:pre-wrap;display:none"></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:linear-gradient(135deg,#43d98c,#00b894)">ℹ️</div>
        <div><div class="card-title">Anleitung</div></div>
      </div>
      <ol style="font-size:0.82rem;color:var(--muted);line-height:1.8;padding-left:18px">
        <li>Öffne <strong style="color:var(--text)">remotedesktop.google.com/headless</strong></li>
        <li>Klicke auf <strong style="color:var(--text)">Set up via SSH</strong> → <strong style="color:var(--text)">Begin</strong></li>
        <li>Kopiere den Auth-Code (beginnt mit <code style="color:var(--accent)">4/0A...</code>)</li>
        <li>Füge ihn oben ein und klicke <strong style="color:var(--text)">registrieren</strong></li>
        <li>Verbinde dich dann über <strong style="color:var(--text)">remotedesktop.google.com</strong></li>
      </ol>
    </div>
  </div>
</div>

<!-- ══ TAB: Rudiclone ══ -->
<div id="tab-rudiclone" class="tab-panel">
  <div style="padding:24px;max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:20px">

    <!-- A: Persona -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)">🧬</div>
        <div><div class="card-title">A — Rudi Persona</div><div class="card-subtitle">KI-Klon · Rudi's Sprache</div></div>
      </div>
      <textarea id="persona-input" class="crd-input" placeholder="Was würde Rudi zu diesem Problem sagen..."></textarea>
      <button class="btn btn-primary" style="width:100%;margin-bottom:10px" onclick="personaAsk()">🧬 Rudi fragen</button>
      <div id="persona-result" style="font-size:0.82rem;background:var(--surface);border-radius:8px;padding:12px;min-height:60px;white-space:pre-wrap;display:none"></div>
    </div>

    <!-- B: System Clone -->
    <div class="card">
      <div class="card-header">
        <div class="card-icon" style="background:linear-gradient(135deg,#43d98c,#00b894)">💾</div>
        <div><div class="card-title">B — System Clone</div><div class="card-subtitle">Backup · Restore · Diff</div></div>
      </div>
      <button class="btn btn-primary" style="width:100%;margin-bottom:8px" onclick="createSnapshot()">📸 Snapshot erstellen</button>
      <button class="btn btn-ghost btn-sm" style="width:100%;margin-bottom:8px" onclick="loadSnapshots()">📋 Snapshots anzeigen</button>
      <div id="snapshot-result" style="font-size:0.75rem;font-family:monospace;background:var(--surface);border-radius:8px;padding:10px;min-height:40px;white-space:pre-wrap;display:none"></div>
      <div id="snapshots-list" style="margin-top:8px;font-size:0.75rem"></div>
    </div>

    <!-- C: Sub-Agents (full width) -->
    <div class="card col-2" style="grid-column:span 2">
      <div class="card-header">
        <div class="card-icon" style="background:linear-gradient(135deg,#667eea,#764ba2)">🤖</div>
        <div><div class="card-title">C — Sub-Agenten</div><div class="card-subtitle">SystemDiagnose · Shopify · Trade · LoadMonitor</div></div>
        <div style="margin-left:auto;display:flex;gap:6px">
          <button class="btn btn-green btn-sm" onclick="startAgents()">▶ Alle starten</button>
          <button class="btn btn-ghost btn-sm" onclick="loadAgentStatus()">↺ Status</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px">
        <button class="btn btn-ghost btn-sm" onclick="runAgent('SystemDiagnoseAgent')">🔍 System Diagnose</button>
        <button class="btn btn-ghost btn-sm" onclick="runAgent('ShopifyAgent')">🛒 Shopify Check</button>
        <button class="btn btn-ghost btn-sm" onclick="runAgent('TradeAgent')">📈 Trade Scan</button>
        <button class="btn btn-ghost btn-sm" onclick="runAgent('LoadMonitor')">⚡ Load Monitor</button>
      </div>
      <div id="agents-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px">
        <div class="loading">Lade Status...</div>
      </div>
    </div>

  </div>
</div>

<script>
const session = 'dashboard_' + Date.now();

// ── Toast ──
function showToast(msg, ok=true) {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;top:20px;right:20px;z-index:9999;background:${ok?'#43d98c':'#ff4757'};color:#000;padding:12px 20px;border-radius:10px;font-weight:600;font-size:0.85rem;box-shadow:0 4px 16px rgba(0,0,0,0.4);animation:slideIn 0.3s ease`;
  t.textContent = (ok ? '✓ ' : '✗ ') + msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ── Clock ──
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('de-DE');
}, 1000);
document.getElementById('clock').textContent = new Date().toLocaleTimeString('de-DE');

// ── API helper ──
const RAILWAY_SUITE_URL = 'https://shopify-suite-v2-production.up.railway.app';

function isLocalHost() {
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1';
}

function resolveSuiteUrl(path='') {
  const base = isLocalHost() ? 'http://localhost:3200' : RAILWAY_SUITE_URL;
  return base + path;
}

function resolveTabIframeUrl(iframe) {
  if (iframe.dataset.localUrl) {
    return isLocalHost() ? iframe.dataset.localUrl : '';
  }
  if (iframe.dataset.path) {
    return resolveSuiteUrl(iframe.dataset.path);
  }
  return iframe.dataset.src || '';
}

async function api(path, data=null) {
  try {
    const opts = data
      ? { method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(data), cache:'no-store' }
      : { headers:{'Accept':'application/json'}, cache:'no-store' };
    const r = await fetch('/api' + path, opts);
    const raw = await r.text();
    let parsed;
    try {
      parsed = raw ? JSON.parse(raw) : {};
    } catch (_) {
      parsed = { ok: r.ok, error: raw || ('HTTP ' + r.status) };
    }
    if (typeof parsed.ok === 'undefined') parsed.ok = r.ok;
    if (!parsed.ok && !parsed.error) parsed.error = 'HTTP ' + r.status;
    return parsed;
  } catch(e) {
    return { ok: false, error: e?.message || 'Failed to fetch' };
  }
}

// ── Services ──
async function svcAction(id, action) {
  showToast('Ausführen: ' + action + '...', true);
  const r = await api('/services/action', { id, action });
  showToast(r.ok ? (r.service + ' → ' + action) : (r.error || 'Fehler'), r.ok);
  setTimeout(loadServices, 2000);
}

async function loadServices() {
  const r = await api('/services/status');
  const el = document.getElementById('services-list');
  if (!r.services) { el.innerHTML = '<div class="error-text">Fehler beim Laden</div>'; return; }
  el.innerHTML = r.services.map(s => `
    <div class="svc-row">
      <div class="svc-dot ${s.running ? 'on' : 'off'}"></div>
      <span style="font-size:1rem">${s.icon}</span>
      <span class="svc-name">${s.name}</span>
      <span class="svc-port">${s.port > 0 ? ':' + s.port : ''}</span>
      <div class="svc-btns">
        <button class="btn btn-green btn-xs" onclick="svcAction('${s.id}','start')">▶</button>
        <button class="btn btn-red btn-xs" onclick="svcAction('${s.id}','stop')">■</button>
        <button class="btn btn-ghost btn-xs" onclick="svcAction('${s.id}','restart')">↺</button>
      </div>
    </div>
  `).join('');
}

// ── System Stats ──
async function loadSystem() {
  const r = await api('/system');
  if (r.error) return;
  const cpu = r.cpu_percent || 0;
  document.getElementById('cpu-val').textContent = cpu + '%';
  document.getElementById('cpu-bar').style.width = cpu + '%';
  document.getElementById('cpu-bar').className = 'bar-fill ' + (cpu > 80 ? 'bar-red' : cpu > 50 ? 'bar-yellow' : 'bar-accent');
  const ram = r.memory_percent || 0;
  document.getElementById('ram-val').textContent = `${r.memory_used_gb||0}GB / ${r.memory_total_gb||48}GB (${ram}%)`;
  document.getElementById('ram-bar').style.width = ram + '%';
  document.getElementById('ram-bar').className = 'bar-fill ' + (ram > 85 ? 'bar-red' : ram > 60 ? 'bar-yellow' : 'bar-green');
  const disk = r.disk_percent || 0;
  document.getElementById('disk-val').textContent = `${r.disk_used_gb||0}GB belegt · ${r.disk_free_gb||0}GB frei`;
  document.getElementById('disk-bar').style.width = disk + '%';
  if (r.process_count) document.getElementById('proc-count').textContent = r.process_count;
}

// ── Mac Actions (direct, no chat) ──
async function macAction(action, extra={}) {
  const out = document.getElementById('mac-output');
  out.textContent = '⏳ ' + action + '...';
  const r = await api('/mac/action', { action, ...extra });
  if (!r.ok) {
    out.textContent = '✗ ' + (r.error || 'Fehler');
    showToast(r.error || 'Mac Fehler', false);
    return;
  }
  const result = r.result;
  if (typeof result === 'object') {
    out.textContent = JSON.stringify(result, null, 2);
  } else {
    out.textContent = String(result || 'OK');
  }
  showToast(action + ' OK', true);
}

async function quickMac(action) {
  const r = await api('/mac/action', { action });
  showToast(r.ok ? action + ' OK' : (r.error || 'Fehler'), r.ok);
}

async function quickNotify() {
  const msg = prompt('Benachrichtigung:', 'Test von SuperMegaBot');
  if (!msg) return;
  const r = await api('/mac/action', { action: 'notify', title: 'SuperMegaBot', message: msg });
  showToast(r.ok ? 'Benachrichtigung gesendet' : (r.error || 'Fehler'), r.ok);
}

function setVolume() {
  const level = document.getElementById('vol-slider').value;
  macAction('volume', { level: parseInt(level) });
}

document.getElementById('vol-slider').oninput = function() {
  document.getElementById('vol-val').textContent = this.value;
};

function macOpenUrl() {
  const url = prompt('URL öffnen:', 'https://google.com');
  if (url) macAction('open_url', { url });
}

async function loadProcesses() {
  const out = document.getElementById('mac-output');
  out.textContent = '⏳ Lade Prozesse...';
  const r = await api('/processes');
  if (r.error) { out.textContent = '✗ ' + r.error; return; }
  out.textContent = (r.processes || []).map(p =>
    `${String(p.cpu).padStart(5)}% CPU  ${String(p.mem).padStart(4)}% MEM  ${p.name}`
  ).join('\\n');
}

// ── Chat ──
async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMsg(text, 'user');
  const typing = addMsg('...', 'bot');
  const r = await api('/chat', { text, session_id: session, model: document.getElementById('model-select').value });
  typing.remove();
  addMsg(r.response || r.error || 'Fehler', 'bot');
}

function addMsg(text, role) {
  const box = document.getElementById('chat-box');
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function clearChat() {
  (async () => {
    const r = await api('/chat/clear', { session_id: session });
    document.getElementById('chat-box').innerHTML = '<div class="msg msg-bot">Chat geleert. Wie kann ich helfen?</div>';
    showToast(r.ok ? 'Chat-Verlauf geleert' : ('Chat nur lokal geleert: ' + (r.error || 'Fehler')), r.ok);
  })();
}

// ── Prices ──
async function loadPrices() {
  const r = await api('/trading/prices');
  const el = document.getElementById('prices-list');
  if (!r.prices) { el.innerHTML = '<div class="error-text">Fehler</div>'; return; }
  el.innerHTML = Object.entries(r.prices).map(([pair, data]) =>
    `<div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.8rem">
      <span style="color:var(--muted)">${pair}</span>
      <span style="font-weight:600">$${(data.avg||0).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})}</span>
    </div>`
  ).join('');
}

async function scanArbitrage() {
  document.getElementById('arb-list').innerHTML = '<div class="loading">Scanne...</div>';
  const r = await api('/trading/arbitrage');
  const el = document.getElementById('arb-list');
  if (!r.opportunities || r.opportunities.length === 0) {
    el.innerHTML = '<div style="color:var(--muted);font-size:0.78rem">Keine Chancen ≥ 0.5%</div>';
    return;
  }
  el.innerHTML = r.opportunities.slice(0,5).map(o =>
    `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">
      <div>
        <div style="font-weight:600;font-size:0.8rem">${o.pair}</div>
        <div style="font-size:0.68rem;color:var(--muted)">${o.exchange_buy}→${o.exchange_sell}</div>
      </div>
      <span class="badge badge-green">+${o.profit_pct}%</span>
    </div>`
  ).join('');
}

// ── Telegram ──
async function loadTgStatus() {
  const r = await api('/telegram/status');
  if (!r.ok && r.error) {
    document.getElementById('tg-status').innerHTML = `<span class="badge badge-red">✗ Verbindungsfehler</span> ${r.error}`;
    return;
  }
  document.getElementById('tg-status').innerHTML = r.configured
    ? `<span class="badge badge-green">✓ Konfiguriert</span> Chat ID: ${r.chat_id || '?'}`
    : '<span class="badge badge-red">✗ Nicht konfiguriert</span> TELEGRAM_BOT_TOKEN setzen';
}

async function sendTelegram() {
  const msg = document.getElementById('tg-msg').value.trim();
  if (!msg) return;
  const r = await api('/telegram/send', { message: msg });
  document.getElementById('tg-msg').value = '';
  showToast(r.ok ? 'Gesendet!' : ('Fehler: ' + (r.error || 'Unbekannt')), r.ok);
}

// ── Shopify ──
async function loadShopify() {
  const r = await api('/shopify/status?section=summary');
  const el = document.getElementById('shopify-data');
  if (r.ok) {
    el.innerHTML = `<div>Store: <strong>${r.store || 'N/A'}</strong></div>
      <div>Produkte: ${r.products || '?'} · Bestellungen: ${r.orders || '?'}</div>
      <div style="margin-top:4px"><span class="badge badge-green">✓ Verbunden</span></div>`;
  } else if (r.error && r.error.includes('401')) {
    el.innerHTML = `<span class="badge badge-orange">⚠ Token abgelaufen</span>
      <div style="margin-top:6px;font-size:0.72rem;color:var(--muted)">Neu generieren: suitenew.myshopify.com → Admin → Apps → API-Zugangsdaten</div>`;
  } else if (r.error && r.error.toLowerCase().includes('failed to fetch')) {
    el.innerHTML = `<div class="error-text">Dashboard API nicht erreichbar (${r.error})</div>
      <div style="margin-top:4px"><span class="badge badge-yellow">⚠ Verbindung prüfen</span></div>`;
  } else {
    el.innerHTML = `<div class="error-text">${r.error || 'Nicht verbunden'}</div>
      <div style="margin-top:4px"><span class="badge badge-yellow">⚠ Setup erforderlich</span></div>`;
  }
}

async function shopifyAction(type) {
  showToast(type + ' wird geladen...', true);
  const el = document.getElementById('shopify-data');
  const r = await api('/shopify/status?section=' + encodeURIComponent(type));
  if (!r.ok) { showToast(r.error || 'Shopify Fehler', false); return; }
  if (type === 'products') {
    const items = r.products || [];
    el.innerHTML = `<div style="font-size:0.75rem;color:var(--muted);margin-bottom:6px">${items.length} Produkte aus der echten Shopify Admin API</div>` +
      items.slice(0, 8).map(p => `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><strong>${p.title || 'Untitled'}</strong><div style="font-size:0.7rem;color:var(--muted)">${p.status || ''} · ${p.vendor || ''}</div></div>`).join('');
  } else if (type === 'orders') {
    const items = r.orders || [];
    el.innerHTML = `<div style="font-size:0.75rem;color:var(--muted);margin-bottom:6px">${items.length} Bestellungen aus der echten Shopify Admin API</div>` +
      items.slice(0, 8).map(o => `<div style="padding:6px 0;border-bottom:1px solid var(--border)"><strong>${o.name || 'Order'}</strong><div style="font-size:0.7rem;color:var(--muted)">${o.displayFinancialStatus || ''} · ${o.displayFulfillmentStatus || ''}</div></div>`).join('');
  } else if (type === 'analytics') {
    const a = r.analytics || {};
    el.innerHTML = `<div>Shop: <strong>${a.shop || r.store || 'N/A'}</strong></div>
      <div>Umsatz: <strong>€${Number(a.revenue || 0).toFixed(2)}</strong></div>
      <div>Orders: ${a.orders_total || 0} · Paid: ${a.orders_paid || 0}</div>`;
  } else {
    el.innerHTML = `<div style="color:var(--muted);font-size:0.75rem">${type} – Daten kommen direkt von der echten Shopify Admin API</div>`;
  }
}

// ── Ollama Models ──
async function loadModels() {
  const r = await api('/ollama/models');
  const el = document.getElementById('models-list');
  if (!r.models || r.models.length === 0) {
    el.innerHTML = '<div class="error-text">Ollama nicht erreichbar</div><div style="font-size:0.72rem;color:var(--muted);margin-top:4px">Starte: ollama serve</div>';
    return;
  }
  el.innerHTML = r.models.map(m => `
    <div style="display:flex;align-items:center;gap:8px">
      <span class="dot"></span>
      <span style="font-size:0.8rem;flex:1">${m.name}</span>
      <span style="font-size:0.68rem;color:var(--muted)">${m.size || ''}</span>
      <button class="btn btn-ghost btn-xs" onclick="setModel('${m.name}')">Chat</button>
    </div>
  `).join('');
}

function setModel(name) {
  const sel = document.getElementById('model-select');
  // add as option if not present
  let found = false;
  for (let opt of sel.options) { if (opt.value === name) { found = true; sel.value = name; break; } }
  if (!found) {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    sel.appendChild(opt);
    sel.value = name;
  }
  showToast('Model: ' + name, true);
}

// ── GMC ──
async function loadGMC() {
  const r = await api('/gmc');
  const el = document.getElementById('gmc-data');
  if (r.error) {
    el.innerHTML = `<div class="error-text">${escHtml(r.error)}</div>`;
    return;
  }
  const gmc = r.gmc || r;
  const suspended = gmc.suspended || false;
  const suspendIcon = suspended ? '🔴' : '🟢';
  const suspendText = suspended ? 'Gesperrt ⛔' : 'Aktiv ✅';
  const shopifyProds = r.shopify_products || {};
  const total = shopifyProds.total ?? shopifyProds.count ?? (gmc.shopify_products ?? '?');
  const active = shopifyProds.active ?? '?';
  const gmcApproved = gmc.products_approved ?? 0;
  const gmcDisapproved = gmc.products_disapproved ?? 0;
  const shipping = gmc.shipping_policies_count ?? (r.policies?.shipping_services ?? 15);
  const returns = gmc.return_policies_count ?? (r.policies?.return_policies ?? 2);
  const identityPending = gmc.identity_verification_pending ?? !gmc.identity_verified;
  const identityIcon = identityPending ? '⏳' : '✅';
  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
      <span style="font-size:1.2rem">${suspendIcon}</span>
      <span style="font-weight:600;font-size:0.88rem">${suspendText}</span>
      <span style="margin-left:auto;font-size:0.68rem;color:var(--muted)">ID ${gmc.merchant_id||'?'}</span>
    </div>
    <div style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">Produkte</div>
    <div class="stats-2" style="margin-bottom:8px">
      <div class="stat-box"><div class="stat-value" style="font-size:1.1rem">${total}</div><div class="stat-label-sm">Shopify aktiv</div></div>
      <div class="stat-box"><div class="stat-value" style="font-size:1.1rem;color:var(--green)">${gmcApproved}</div><div class="stat-label-sm">GMC ✅</div></div>
    </div>
    <div style="font-size:0.78rem;display:flex;flex-direction:column;gap:4px">
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--muted)">GMC abgelehnt</span>
        <span style="color:${gmcDisapproved>0?'var(--red)':'var(--green)'}">${gmcDisapproved}</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--muted)">Versandrichtlinien</span>
        <span>${shipping} ✓</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--muted)">Rückgaberichtlinien</span>
        <span>${returns} ✓</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:var(--muted)">Identität</span>
        <span>${identityIcon} ${identityPending ? 'Ausstehend' : 'Verifiziert'}</span>
      </div>
    </div>`;
}

// ── Logs ──
async function loadLogs() {
  const r = await api('/logs');
  const el = document.getElementById('log-box');
  if (!r.lines) { el.innerHTML = '<div class="error-text">Fehler</div>'; return; }
  el.innerHTML = r.lines.filter(Boolean).map(l =>
    `<div>${escHtml(l)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

function clearLogs() {
  (async () => {
    const r = await api('/logs/clear', {});
    document.getElementById('log-box').innerHTML = '<div style="opacity:0.4">Logs geleert</div>';
    showToast(r.ok ? 'Logs serverseitig geleert' : ('Logs nur lokal geleert: ' + (r.error || 'Fehler')), r.ok);
  })();
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── AutoPilot ──
async function loadAgentGrid() {
  const r = await api('/autopilot/agents');
  const el = document.getElementById('agent-grid');
  if (!r.agents) return;
  el.innerHTML = r.agents.map(a => `
    <div class="agent-card" onclick="selectAgent('${a.id}')" id="agent-btn-${a.id}"
      style="border-color:${a.color}33;background:${a.color}11">
      <div style="font-size:1.3rem">${a.emoji}</div>
      <div style="font-size:0.65rem;margin-top:3px;font-weight:600">${a.name}</div>
      <div style="font-size:0.58rem;color:var(--muted);margin-top:1px">${(a.role||'').split(' ')[0]}</div>
    </div>
  `).join('');
}

function selectAgent(id) {
  document.getElementById('agent-select').value = id;
  document.querySelectorAll('[id^="agent-btn-"]').forEach(b => b.style.opacity = '0.6');
  const btn = document.getElementById(`agent-btn-${id}`);
  if (btn) btn.style.opacity = '1';
}

async function runAutoPilot() {
  const goal = document.getElementById('autopilot-goal').value.trim();
  if (!goal) { showToast('Bitte Ziel eingeben', false); return; }
  const agentId = document.getElementById('agent-select').value;
  document.getElementById('autopilot-status-dot').style.background = '#ffd700';
  document.getElementById('autopilot-status-text').textContent = 'Läuft...';
  const resultsEl = document.getElementById('autopilot-results');
  resultsEl.innerHTML = `<div style="text-align:center;padding:20px;color:var(--muted)">
    <div style="font-size:2rem;margin-bottom:8px">🤖</div>
    <div>Agenten arbeiten... (Ollama lokal)</div>
  </div>`;
  const r = await api('/autopilot/run', { goal, agent_id: agentId || null });
  document.getElementById('autopilot-status-dot').style.background = 'var(--green)';
  document.getElementById('autopilot-status-text').textContent = 'Fertig';
  if (r.error) {
    resultsEl.innerHTML = `<div class="error-text" style="padding:10px">${r.error}</div>`;
    return;
  }
  const results = r.results || [r];
  resultsEl.innerHTML = results.map(res => `
    <div style="background:var(--surface);border-radius:10px;padding:12px;border-left:3px solid var(--accent)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-weight:600;font-size:0.85rem">${res.agent_name || res.agent || ''}</span>
        <span style="font-size:0.68rem;color:var(--muted);margin-left:auto">${res.duration_ms||0}ms</span>
      </div>
      <div style="font-size:0.72rem;color:var(--muted);margin-bottom:6px;font-style:italic">${(res.task||'').substring(0,80)}</div>
      <div style="font-size:0.8rem;white-space:pre-wrap;line-height:1.5">${res.result||''}</div>
    </div>
  `).join('');
  loadAgentLogs();
}

async function loadAgentLogs() {
  const r = await api('/autopilot/logs');
  const el = document.getElementById('agent-logs');
  if (!r.logs || r.logs.length === 0) {
    el.innerHTML = '<div style="color:var(--muted)">Noch keine Aufgaben</div>';
    return;
  }
  el.innerHTML = r.logs.map(l => `
    <div style="display:flex;gap:7px;align-items:flex-start;padding:5px;background:var(--surface);border-radius:6px">
      <span style="font-size:0.68rem;color:var(--muted);white-space:nowrap">${l.timestamp?.substring(11,19)||''}</span>
      <span class="badge badge-green" style="font-size:0.58rem">${l.agent}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.75rem">${l.task?.substring(0,60)||''}</span>
    </div>
  `).join('');
}

// ── Geheimwaffe ──
async function runGeheimwaffe() {
  const niche = document.getElementById('gw-niche').value.trim() || 'General';
  const el = document.getElementById('gw-results');
  el.style.display = 'block';
  el.textContent = '⚔️ Geheimwaffe läuft... (AI analysiert Markt lokal via Ollama)';
  const r = await api('/geheimwaffe/run', { niche });
  if (r.error) { el.textContent = 'Fehler: ' + r.error; return; }
  let text = `✅ GEHEIMWAFFE ERGEBNIS für: ${niche}\n\n`;
  if (r.winning_products?.length) {
    text += `🏆 TOP WINNING PRODUCTS:\n`;
    r.winning_products.forEach((p, i) => {
      text += `${i+1}. ${p.title || 'Produkt'}\n`;
      if (p.why_winning) text += `   → ${p.why_winning}\n`;
      if (p.profit_margin) text += `   Marge: ${p.profit_margin}\n`;
    });
    text += '\\n';
  }
  if (r.listing?.title) text += `📝 LISTING:\n${r.listing.title}\n${r.listing.seo_description||''}\n\n`;
  if (r.social?.tiktok?.content) text += `🎵 TIKTOK:\n${r.social.tiktok.content?.substring(0,200)}...\n\n`;
  if (r.forecast?.month3_target) text += `📈 PROGNOSE:\nMonat 1: ${r.forecast.month1_target}\nMonat 2: ${r.forecast.month2_target}\nMonat 3: ${r.forecast.month3_target}\n`;
  el.textContent = text;
}

async function gwContent(type, platform='tiktok') {
  const product = document.getElementById('gw-product').value.trim();
  if (!product) { showToast('Produktname eingeben', false); return; }
  const el = document.getElementById('gw-results');
  el.style.display = 'block';
  el.textContent = `Generiere ${type}...`;
  const r = await api('/geheimwaffe/content', { product, type, platform });
  if (r.error) { el.textContent = 'Fehler: ' + r.error; return; }
  let text = `${type.toUpperCase()} für: ${product}\n\n`;
  if (typeof r === 'object') {
    Object.entries(r).forEach(([k, v]) => { if (typeof v === 'string') text += `${k}:\n${v}\n\n`; });
  }
  el.textContent = text;
}

async function runBackup() {
  const r = await api('/backup/run', {});
  document.getElementById('backup-result').textContent = r.ok
    ? `✓ Backup: ${r.path?.split('/').slice(-2).join('/')}`
    : `✗ ${r.error}`;
  showToast(r.ok ? 'Backup erstellt' : r.error, r.ok);
}

// ── Init & Auto-refresh ──
async function init() {
  await Promise.all([
    loadSystem(), loadServices(), loadPrices(),
    loadTgStatus(), loadShopify(), loadModels(),
    loadAgentGrid(), loadLogs(), loadGMC()
  ]);
  scanArbitrage();
  loadAgentLogs();
}

init();
setInterval(loadSystem,   5000);
setInterval(loadServices, 30000);
setInterval(loadPrices,   30000);
setInterval(scanArbitrage, 60000);
setInterval(loadLogs,     8000);
setInterval(loadGMC,      60000);

// ── Rudiclone ──
async function personaAsk() {
  const text = document.getElementById('persona-input').value.trim();
  if (!text) return;
  const res = document.getElementById('persona-result');
  res.style.display = 'block';
  res.textContent = '⏳ Rudi denkt nach...';
  const r = await api('/rudiclone/persona', { text });
  res.textContent = r.ok ? r.response : ('❌ ' + (r.error || 'Fehler'));
}

async function createSnapshot() {
  const el = document.getElementById('snapshot-result');
  el.style.display = 'block';
  el.textContent = '⏳ Erstelle System-Snapshot...';
  const r = await api('/rudiclone/snapshot', {});
  el.textContent = r.ok ? ('✅ Snapshot: ' + r.path) : ('❌ ' + r.error);
  if (r.ok) showToast('Snapshot erstellt', true);
  loadSnapshots();
}

async function loadSnapshots() {
  const r = await api('/rudiclone/snapshots');
  const el = document.getElementById('snapshots-list');
  if (!r.ok || !r.snapshots?.length) { el.innerHTML = '<div class="loading">Keine Snapshots</div>'; return; }
  el.innerHTML = r.snapshots.map(s => `
    <div style="display:flex;justify-content:space-between;padding:5px 8px;background:var(--surface);border-radius:6px;margin-bottom:4px;font-size:0.72rem">
      <span style="color:var(--text)">${s.name}</span>
      <span style="color:var(--muted)">${s.size_kb}KB · ${new Date(s.created).toLocaleString('de-DE')}</span>
    </div>`).join('');
}

async function loadAgentStatus() {
  const r = await api('/rudiclone/agents');
  const el = document.getElementById('agents-grid');
  if (!r.ok) { el.innerHTML = '<div class="error-text">' + (r.error||'Fehler') + '</div>'; return; }
  const agents = r.agents || {};
  el.innerHTML = Object.entries(agents).map(([name, s]) => `
    <div style="background:var(--surface);border-radius:10px;padding:10px;font-size:0.75rem">
      <div style="font-weight:600;margin-bottom:4px">${name}</div>
      <div style="color:${s.running?'var(--green)':'var(--muted)'}">${s.running?'🟢 läuft':'⚪ gestoppt'}</div>
      <div style="color:var(--muted);font-size:0.7rem">Läufe: ${s.run_count||0} · Fehler: ${s.error_count||0}</div>
      <div style="color:var(--muted);font-size:0.68rem;margin-top:2px">${s.last_run?new Date(s.last_run*1000).toLocaleTimeString('de-DE'):'-'}</div>
    </div>`).join('');
}

async function startAgents() {
  const r = await api('/rudiclone/agents/start', {});
  showToast(r.ok ? r.message : r.error, r.ok);
  setTimeout(loadAgentStatus, 2000);
}

async function runAgent(name) {
  showToast('▶ ' + name + '...', true);
  const r = await api('/rudiclone/agents/run', { agent: name });
  if (r.ok) showToast('✓ ' + name + ' fertig', true);
  else showToast('✗ ' + (r.error||'Fehler'), false);
  setTimeout(loadAgentStatus, 1000);
}

// ── Tab Navigation ──
function switchTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('tab-' + tabId);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');
  // lazy-load iframe on first visit
  if (panel) {
    const iframe = panel.querySelector('iframe');
    if (iframe && !iframe.src) {
      const targetUrl = resolveTabIframeUrl(iframe);
      if (targetUrl) {
        iframe.src = targetUrl;
      } else if (tabId === 'telegram') {
        panel.innerHTML = '<div style="padding:24px;color:var(--muted)">Telegram Bot ist nur lokal auf diesem Mac unter <strong>http://localhost:3200</strong> verfuegbar.</div>';
      }
    }
  }
}

// ── Chrome Remote Desktop ──
async function registerCRD() {
  const code = document.getElementById('crd-code').value.trim();
  if (!code) { showToast('Auth-Code fehlt', false); return; }
  const result = document.getElementById('crd-result');
  result.style.display = 'block';
  result.textContent = '⏳ Registriere Remote Desktop Host...';
  const r = await api('/remote-desktop/register', { code });
  if (r.ok) {
    result.textContent = '✅ Erfolgreich registriert!\\n\\n' + (r.output || '');
    showToast('Remote Desktop registriert!', true);
  } else {
    result.textContent = '❌ Fehler: ' + (r.error || 'Unbekannt') + '\\n\\n' + (r.output || '');
    showToast(r.error || 'Fehler', false);
  }
}
</script>
</body>
</html>'''


# ---------------------------------------------------------------------------
# API Routes — existing handlers
# ---------------------------------------------------------------------------

async def handle_index(req):
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_chat(req):
    try:
        data = await req.json()
        text = data.get("text", "")
        session_id = data.get("session_id", "dashboard")
        sys.path.insert(0, str(BASE_DIR))
        from core.mega_orchestrator import MegaOrchestrator
        bot = req.app["bot"]
        response = await bot.process(text, session_id)
        return web.json_response({"response": response, "session_id": session_id})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_system(req):
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return web.json_response({
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
        return web.json_response({"error": "psutil not installed"})


async def handle_services_legacy(req):
    """Legacy /api/services endpoint — kept for backward compat."""
    import socket
    service_list = [
        {"name": "SuperMegaBot Dashboard", "port": PORT},
        {"name": "Telegram-Automation-Bot", "port": 3200},
        {"name": "CreatorHub", "port": 3002},
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
    # ccxt market-loading deaktiviert — verursacht 83% CPU + PM2-Crashloop
    # Lightweight Binance public API stattdessen
    try:
        pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        prices = {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for pair in pairs:
                try:
                    async with session.get(
                        f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            prices[pair] = float(d.get("price", 0))
                except Exception:
                    pass
        return web.json_response({"prices": prices, "source": "binance-public"})
    except Exception as e:
        return web.json_response({"prices": {}, "error": str(e)})


async def handle_trading_arbitrage(req):
    # ccxt arbitrage-scan deaktiviert — zu CPU-intensiv für Production
    return web.json_response({
        "opportunities": [],
        "info": "Arbitrage-Scan pausiert (CPU-Schutz). Via Telegram /trading aktivieren."
    })


async def handle_telegram_status(req):
    token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    return web.json_response({
        "configured": bool(token),
        "chat_id": TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", ""),
    })


async def handle_telegram_send(req):
  if not TELEGRAM_TOKEN:
    return web.json_response({"ok": False, "error": "No token configured"})

  message = ""
  try:
    data = await req.json()
    message = data.get("message", "")
    chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with _client_session(15) as s:
      async with s.post(url, json={"chat_id": chat_id, "text": message}) as r:
        if r.status == 200:
          return web.json_response({"ok": True})
  except Exception:
    pass

  # DNS/network fallback via urllib
  try:
    import urllib.request

    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode("utf-8")
    req_u = urllib.request.Request(
      f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
      data=payload,
      headers={"Content-Type": "application/json"},
      method="POST",
    )
    with urllib.request.urlopen(req_u, timeout=15) as resp:
      return web.json_response({"ok": 200 <= getattr(resp, "status", 0) < 300})
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_status(req):
    try:
        section = (req.query.get("section") or "summary").strip().lower()
        from modules import shopify_client

        if section == "products":
            products = await shopify_client.get_products(limit=20)
            return web.json_response({"ok": True, "section": section, "products": products, "count": len(products)})

        if section == "orders":
            orders = await shopify_client.get_orders(limit=20)
            return web.json_response({"ok": True, "section": section, "orders": orders, "count": len(orders)})

        if section == "analytics":
            analytics = await shopify_client.get_analytics_summary()
            return web.json_response({"ok": True, "section": section, "analytics": analytics})

        shop = await shopify_client.get_shop_info()
        analytics = await shopify_client.get_analytics_summary()
        products = await shopify_client.get_products(limit=5)
        orders = await shopify_client.get_orders(limit=5)
        return web.json_response({
            "ok": True,
            "store": shop.get("name") or shop.get("myshopifyDomain") or os.getenv("SHOPIFY_SHOP_DOMAIN", ""),
            "currency": shop.get("currencyCode", "EUR"),
            "products": len(products),
            "orders": len(orders),
            "revenue": analytics.get("revenue", 0),
            "section": section,
            "shop": shop,
            "analytics": analytics,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_printify_status(req):
    token = os.getenv("PRINTIFY_TOKEN", "")
    shop_id = os.getenv("PRINTIFY_SHOP_ID", "")
    if not token:
        return web.json_response({"ok": False, "error": "PRINTIFY_TOKEN fehlt"})
    try:
        headers = {"Authorization": f"Bearer {token}"}
        async with _client_session(10) as session:
            async with session.get("https://api.printify.com/v1/shops.json", headers=headers) as r:
                body = await r.text()
                if r.status != 200:
                    return web.json_response({"ok": False, "error": f"HTTP {r.status}", "detail": body[:200]})
                shops = json.loads(body)
                shop = shops[0] if isinstance(shops, list) and shops else {}
                if not shop_id:
                    shop_id = str(shop.get("id", ""))

                orders = []
                products = []
                if shop_id:
                    async with session.get(f"https://api.printify.com/v1/shops/{shop_id}/orders.json", headers=headers) as ro:
                        if ro.status == 200:
                            orders_body = await ro.text()
                            orders = json.loads(orders_body) or []
                    async with session.get(f"https://api.printify.com/v1/shops/{shop_id}/products.json", headers=headers) as rp:
                        if rp.status == 200:
                            products_body = await rp.text()
                            products = json.loads(products_body) or []

                return web.json_response({
                    "ok": True,
                    "shop": shop,
                    "shop_id": shop_id,
                    "shops_count": len(shops) if isinstance(shops, list) else 0,
                    "orders_count": len(orders) if isinstance(orders, list) else 0,
                    "products_count": len(products) if isinstance(products, list) else 0,
                    "orders": orders[:10] if isinstance(orders, list) else [],
                    "products": products[:10] if isinstance(products, list) else [],
                })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ── Rudiclone handlers ──────────────────────────────────────────────────────

_rudiclone_agents = None

def _get_rudiclone():
    try:
        from modules.rudiclone import RudiPersona, RudiSystemClone, RudiAgents
        return RudiPersona(), RudiSystemClone(), RudiAgents()
    except Exception as e:
        return None, None, None

async def handle_rudiclone_persona(req):
    try:
        data = await req.json()
        text = data.get("text", "").strip()
        if not text:
            return web.json_response({"ok": False, "error": "text fehlt"})
        persona, _, _ = _get_rudiclone()
        if not persona:
            return web.json_response({"ok": False, "error": "RudiPersona nicht verfügbar"})
        response = await asyncio.wait_for(persona.respond(text), timeout=60)
        return web.json_response({"ok": True, "response": response, "stats": persona.get_stats()})
    except asyncio.TimeoutError:
        return web.json_response({
            "ok": False,
            "timeout": True,
            "error": "Rudiclone Persona Timeout. Ollama prüfen und Anfrage kürzen."
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_rudiclone_snapshot(req):
    try:
        _, clone, _ = _get_rudiclone()
        if not clone:
            return web.json_response({"ok": False, "error": "RudiSystemClone nicht verfügbar"})
        path = await clone.snapshot()
        return web.json_response({"ok": True, "path": str(path)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_rudiclone_snapshots(req):
    try:
        _, clone, _ = _get_rudiclone()
        if not clone:
            return web.json_response({"ok": False, "snapshots": []})
        snaps = clone.list_snapshots()
        return web.json_response({"ok": True, "snapshots": snaps})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e), "snapshots": []})

async def handle_rudiclone_agents_status(req):
    global _rudiclone_agents
    try:
        import inspect
        from modules.rudiclone import RudiAgents
        if _rudiclone_agents is None:
            _rudiclone_agents = RudiAgents()
        status = _rudiclone_agents.get_status()
        if inspect.isawaitable(status):
            status = await status
        return web.json_response({"ok": True, "agents": status})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_rudiclone_agents_start(req):
    global _rudiclone_agents
    try:
        from modules.rudiclone import RudiAgents
        if _rudiclone_agents is None:
            _rudiclone_agents = RudiAgents()
        asyncio.create_task(_rudiclone_agents.start_all())
        return web.json_response({"ok": True, "message": "Alle Sub-Agenten gestartet"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_rudiclone_run_once(req):
    global _rudiclone_agents
    try:
        data = await req.json()
        name = data.get("agent", "").strip()
        from modules.rudiclone import RudiAgents
        if _rudiclone_agents is None:
            _rudiclone_agents = RudiAgents()
        result = await _rudiclone_agents.run_once(name)
        return web.json_response({"ok": True, "result": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_remote_desktop_register(req):
    """Register Chrome Remote Desktop host on macOS using one-time auth code from remotedesktop.google.com/headless"""
    import shutil, platform
    try:
        data = await req.json()
        code = data.get("code", "").strip()

        # Status-only request (no code) — return installation status
        if not code:
            host_binary = _find_crd_binary()
            installed = host_binary is not None
            return web.json_response({
                "ok": True,
                "installed": installed,
                "binary": host_binary,
                "platform": platform.system(),
                "instructions": (
                    "Besuche https://remotedesktop.google.com/headless → "
                    "'Einrichten' → Auth-Code kopieren → hier einfügen"
                ) if installed else (
                    "Chrome Remote Desktop Host nicht installiert. "
                    "Download: https://remotedesktop.google.com/access → 'Remote-Zugriff einrichten'"
                ),
            })

        host_binary = _find_crd_binary()
        if not host_binary:
            return web.json_response({
                "ok": False,
                "error": "Chrome Remote Desktop Host nicht installiert.",
                "fix": "Download unter https://remotedesktop.google.com/access → 'Remote-Zugriff einrichten'",
            })

        redirect_url = "https://remotedesktop.google.com/_/oauthredirect"
        import socket
        hostname = socket.gethostname()

        # macOS: use the installed host binary directly
        cmd = (
            f'"{host_binary}" '
            f'--code="{code}" '
            f'--redirect-url="{redirect_url}" '
            f'--name="{hostname}"'
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            return web.json_response({"ok": False, "error": "Timeout (30s)"})
        output = (stdout.decode() + stderr.decode()).strip()
        success = proc.returncode == 0
        return web.json_response({
            "ok": success,
            "output": output or ("Erfolgreich registriert!" if success else "Fehler beim Registrieren"),
            "returncode": proc.returncode,
            "access_url": "https://remotedesktop.google.com/access" if success else None,
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


def _find_crd_binary():
    """Find Chrome Remote Desktop host binary on macOS or Linux."""
    import shutil
    candidates = [
        # macOS (Chrome)
        "/Library/Application Support/Google/Chrome Remote Desktop/chrome-remote-desktop-host",
        # macOS (alternative path)
        "/Applications/Chrome Remote Desktop Host.app/Contents/MacOS/chrome-remote-desktop-host",
        # Linux
        "/opt/google/chrome-remote-desktop/start-host",
        "/usr/bin/chrome-remote-desktop",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("chrome-remote-desktop") or shutil.which("chrome-remote-desktop-host")


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
                    return web.json_response({"models": models})
                return web.json_response({"models": []})
    except Exception:
        return web.json_response({"models": []})


async def handle_autopilot_agents(req):
    from modules.autopilot import AutoPilot
    ap = AutoPilot()
    return web.json_response({"agents": ap.get_agent_list()})


async def handle_autopilot_run(req):
    try:
        data = await req.json()
        goal = data.get("goal", "")
        agent_id = data.get("agent_id") or None
        from modules.autopilot import AutoPilot
        ap = AutoPilot()
        if agent_id:
            result = await asyncio.wait_for(ap.run_task(goal, agent_id), timeout=15)
            return web.json_response({"results": [result]})
        else:
            results = await asyncio.wait_for(ap.run_autopilot_mode(goal), timeout=15)
            return web.json_response({"results": results})
    except asyncio.TimeoutError:
        return web.json_response({
            "ok": False,
            "timeout": True,
            "error": "AutoPilot dauert zu lange. Bitte präziseren Prompt nutzen oder später erneut versuchen."
        })
    except Exception as e:
        log.error(f"AutoPilot error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_autopilot_logs(req):
    from modules.autopilot import AutoPilot
    ap = AutoPilot()
    return web.json_response({"logs": ap.get_logs(30)})


async def handle_geheimwaffe_run(req):
    try:
        data = await req.json()
        niche = data.get("niche", "General")
        from modules.geheimwaffe import run_full_automation
        result = await asyncio.wait_for(run_full_automation(niche), timeout=15)
        return web.json_response(result)
    except asyncio.TimeoutError:
        return web.json_response({
            "ok": False,
            "timeout": True,
            "error": "Geheimwaffe-Run dauert zu lange. Bitte mit kleinerem Scope erneut ausführen."
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_geheimwaffe_content(req):
    try:
        data = await req.json()
        product = data.get("product", "")
        content_type = data.get("type", "listing")
        platform = data.get("platform", "tiktok")
        from modules.geheimwaffe import generate_product_listing, generate_social_content, generate_ad_copy
        if content_type == "listing":
            result = await asyncio.wait_for(generate_product_listing(product), timeout=15)
        elif content_type == "social":
            result = await asyncio.wait_for(generate_social_content(product, platform), timeout=15)
        elif content_type == "ads":
            result = await asyncio.wait_for(generate_ad_copy(product), timeout=15)
        else:
            result = {"error": "Unbekannter content_type"}
        return web.json_response(result)
    except asyncio.TimeoutError:
        return web.json_response({
            "ok": False,
            "timeout": True,
            "error": "Content-Generierung Timeout. Bitte kürzeren Prompt oder anderes Modell nutzen."
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_gmc(req):
    try:
        sys.path.insert(0, str(BASE_DIR))
        from modules.gmc_monitor import get_full_status
        status = await get_full_status()
        return web.json_response(status)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_backup_status(req):
    backups = []
    backup_paths = [
        BASE_DIR / "data",
        Path("/Users/rudolfsarkany/windsurf-telegram-bot"),
        Path("/Users/rudolfsarkany/CreatorHub Anonym & Profitabel"),
    ]
    for p in backup_paths:
        if p.exists():
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


# ---------------------------------------------------------------------------
# NEW API Routes
# ---------------------------------------------------------------------------

async def handle_mac_action(req):
    data = await req.json()
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

async def handle_services_status(req):
  import socket
  import urllib.request

  result = []
  for svc in SERVICES:
    port_ok = False
    remote_ok = False

    if svc.get("port", 0) > 0:
      try:
        sock = socket.create_connection(("localhost", svc["port"]), timeout=0.5)
        sock.close()
        port_ok = True
      except Exception:
        pass

    if svc.get("health_url") or svc.get("url"):
      check_url = svc.get("health_url") or svc.get("url")
      try:
        with urllib.request.urlopen(check_url, timeout=3) as resp:
          remote_ok = 200 <= getattr(resp, "status", 0) < 400
      except Exception:
        # Fallback via curl because Python DNS can intermittently fail in this process.
        try:
          cp = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", check_url],
            capture_output=True,
            text=True,
          )
          code = int((cp.stdout or "0").strip() or "0")
          remote_ok = 200 <= code < 400
        except Exception:
          remote_ok = False

    pid = None
    try:
      ps = subprocess.run(["pgrep", "-f", svc["pattern"]], capture_output=True, text=True)
      if ps.returncode == 0 and ps.stdout.strip():
        pid = ps.stdout.strip().split('\n')[0]
    except Exception:
      pass

    result.append({
      "id": svc["id"],
      "name": svc["name"],
      "port": svc["port"],
      "icon": svc["icon"],
      "ok": port_ok or remote_ok,
      "pid": pid,
      "running": port_ok or remote_ok or bool(pid),
    })

  return web.json_response({"services": result})


async def handle_service_action(req):
    data = await req.json()
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


async def handle_logs(req):
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
    return web.json_response({"lines": lines[-80:]})


async def handle_logs_clear(req):
    cleared = []
    errors = []
    for lf in [BASE_DIR / "logs" / "supermegabot.log", Path("/tmp/supermegabot.log")]:
        if lf.exists():
            try:
                lf.write_text("")
                cleared.append(str(lf))
            except Exception as e:
                errors.append(f"{lf}: {e}")
    return web.json_response({"ok": len(errors) == 0, "cleared": cleared, "errors": errors})


async def handle_chat_clear(req):
    try:
        data = await req.json()
    except Exception:
        data = {}
    session_id = data.get("session_id", "dashboard")
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return web.json_response({"ok": True, "session_id": session_id, "deleted": 0})
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
        deleted = cur.rowcount if cur.rowcount is not None else 0
        conn.commit()
        conn.close()
        return web.json_response({"ok": True, "session_id": session_id, "deleted": deleted})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e), "session_id": session_id})


async def handle_health(req):
    return web.json_response({
        "status": "ok",
        "service": "supermegabot-dashboard",
        "port": PORT,
        "uptime": time.time(),
    })


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
        return web.json_response({"processes": procs})
    except Exception as e:
        return web.json_response({"error": str(e)})


# ---------------------------------------------------------------------------
# Guardian / Eternal Handlers
# ---------------------------------------------------------------------------

GUARDIAN_BASE = "http://localhost:3201"

def _guardian_headers():
    import hashlib
    secret = os.getenv('GUARDIAN_API_SECRET', '')
    api_key = hashlib.sha256(secret.encode()).hexdigest()[:32] if secret else ''
    return {"X-API-Key": api_key, "Content-Type": "application/json"}

async def handle_guardian_health(req):
    """Check Guardian health status"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/health", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"status": "unavailable", "error": str(e)})

async def handle_guardian_status(req):
    """Get full Guardian status"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/status", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e), "guardian": "unavailable"})

async def handle_guardian_services(req):
    """List Guardian monitored services"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/status", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response({"services": data.get("services", []), "overall": data.get("overall_health")})
    except Exception as e:
        return web.json_response({"error": str(e)})

async def handle_guardian_heal(req):
    """Heal a service via Guardian"""
    try:
        data = await req.json()
        service = data.get("service", "rudibot_main")
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{GUARDIAN_BASE}/api/v1/services/heal", headers=_guardian_headers(), json={"service": service}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                result = await r.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e), "healed": False})

async def handle_guardian_agents(req):
    """List registered Guardian agents"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/agents", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response({"agents": data if isinstance(data, list) else []})
    except Exception as e:
        return web.json_response({"error": str(e), "agents": []})

async def handle_guardian_brain(req):
    """Get Guardian brain summary"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/brain/summary", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e), "patterns_learned": 0, "total_repairs": 0})

async def handle_guardian_notify(req):
    """Send notification via Guardian"""
    try:
        data = await req.json()
        message = data.get("message", "")
        priority = data.get("priority", "normal")
        if not message:
            return web.json_response({"error": "message required", "sent": False})
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{GUARDIAN_BASE}/api/v1/notify", headers=_guardian_headers(), json={"message": message, "priority": priority}, timeout=aiohttp.ClientTimeout(total=5)) as r:
                result = await r.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e), "sent": False})

async def handle_guardian_backups(req):
    """List all available backups"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{GUARDIAN_BASE}/api/v1/backups", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e), "backups": [], "count": 0})

async def handle_guardian_backup(req):
    """Trigger manual backup"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{GUARDIAN_BASE}/api/v1/backup", headers=_guardian_headers(), timeout=aiohttp.ClientTimeout(total=30)) as r:
                result = await r.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e), "backup": "failed"})

async def handle_guardian_restore(req):
    """Restore project from backup"""
    try:
        data = await req.json()
        project = data.get("project", "")
        backup_date = data.get("date")
        if not project:
            return web.json_response({"error": "project required", "success": False})
        import aiohttp
        payload = {"project": project}
        if backup_date:
            payload["date"] = backup_date
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{GUARDIAN_BASE}/api/v1/restore", headers=_guardian_headers(), json=payload, timeout=aiohttp.ClientTimeout(total=60)) as r:
                result = await r.json()
                return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e), "success": False})


# ---------------------------------------------------------------------------
# Self-Learner Handlers
# ---------------------------------------------------------------------------

async def handle_self_learner_status(req):
    try:
        if _self_learner:
            skills = _self_learner.skills
            built_ins = [s for s in skills.values() if s.source == "built-in"]
            learned  = [s for s in skills.values() if s.source in ("learned","api")]
            return web.json_response({
                "ok": True,
                "tool": _self_learner.tool_name,
                "total_skills": len(skills),
                "built_in": len(built_ins),
                "learned": len(learned),
                "telegram": _self_learner.telegram_notify,
                "skills_list": [{"name":s.name,"desc":s.desc,"source":s.source,"usage":s.usage_count}
                                 for s in skills.values()],
            })
        return web.json_response({"ok": False, "error": "SelfLearner nicht verfügbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_self_learner_learn(req):
    try:
        data = await req.json()
        desc = data.get("description", "")
        if not desc:
            return web.json_response({"ok": False, "error": "description fehlt"})
        if _self_learner:
            result = _self_learner.handle_command(f"/lerne {desc}")
            return web.json_response({"ok": True, "result": result})
        return web.json_response({"ok": False, "error": "SelfLearner nicht verfügbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_self_learner_skills(req):
    try:
        if _self_learner:
            result = _self_learner.handle_command("/skills")
            return web.json_response({"ok": True, "result": result})
        return web.json_response({"ok": False, "error": "SelfLearner nicht verfügbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_self_learner_delete(req):
    try:
        data = await req.json()
        name = data.get("name", "")
        if not name:
            return web.json_response({"ok": False, "error": "name fehlt"})
        if _self_learner:
            result = _self_learner.handle_command(f"/skill_del {name}")
            return web.json_response({"ok": True, "result": result})
        return web.json_response({"ok": False, "error": "SelfLearner nicht verfügbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_self_learner_find_api(req):
    try:
        data = await req.json()
        task = data.get("task", "")
        if not task:
            return web.json_response({"ok": False, "error": "task fehlt"})
        if _self_learner:
            result = _self_learner.handle_command(f"/api_finde {task}")
            return web.json_response({"ok": True, "result": result})
        return web.json_response({"ok": False, "error": "SelfLearner nicht verfügbar"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Army / Micro Bot Status Handler
# ---------------------------------------------------------------------------

async def handle_army_status(req):
    try:
        import json as _json
        state_file = BASE_DIR.parent / "rudibot-army" / "shared" / "army_state.json"
        if state_file.exists():
            state = _json.loads(state_file.read_text(errors="ignore"))
            return web.json_response({"ok": True, "agents": state.get("agents", {}),
                                       "events": state.get("events", [])[-20:]})
        return web.json_response({"ok": False, "error": "army_state.json nicht gefunden"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

async def create_app():
    # Mega-Orchestrator nur starten wenn KEIN eigenständiger Prozess läuft
    # (verhindert 409-Konflikt bei doppeltem Telegram-Polling)
    import subprocess as _sp
    _orch_running = _sp.run(
        ["pgrep", "-f", "core/mega_orchestrator.py"],
        capture_output=True
    ).returncode == 0

    _orch_api_up = False
    if _orch_running:
        try:
            import socket as _socket
            with _socket.create_connection(("127.0.0.1", 8889), timeout=1.0):
                _orch_api_up = True
        except Exception:
            _orch_api_up = False

    if not (_orch_running and _orch_api_up):
        from core.mega_orchestrator import MegaOrchestrator
        bot = MegaOrchestrator()
        await bot.start()
    else:
        # Dummy-Objekt — Dashboard leitet Chat-Requests per HTTP weiter
        class _BotProxy:
            async def process(self, text, session_id="default"):
                try:
                    import aiohttp as _aio
                    async with _aio.ClientSession() as s:
                        async with s.post(
                            "http://127.0.0.1:8889/api/chat",
                            json={"text": text, "session_id": session_id},
                            timeout=_aio.ClientTimeout(total=30)
                        ) as r:
                            d = await r.json()
                            return d.get("response", d.get("result", str(d)))
                except Exception as ex:
                    return f"Orchestrator antwortet nicht: {ex}"
        bot = _BotProxy()

    app = web.Application()
    app["bot"] = bot

    # Existing routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/dashboard", handle_index)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/chat/clear", handle_chat_clear)
    app.router.add_get("/api/system", handle_system)
    app.router.add_get("/api/services", handle_services_legacy)
    app.router.add_get("/api/trading/prices", handle_trading_prices)
    app.router.add_get("/api/trading/arbitrage", handle_trading_arbitrage)
    app.router.add_get("/api/telegram/status", handle_telegram_status)
    app.router.add_post("/api/telegram/send", handle_telegram_send)
    app.router.add_get("/api/shopify/status", handle_shopify_status)
    app.router.add_get("/api/printify/status", handle_printify_status)
    app.router.add_get("/api/ollama/models", handle_ollama_models)
    app.router.add_get("/api/autopilot/agents", handle_autopilot_agents)
    app.router.add_post("/api/autopilot/run", handle_autopilot_run)
    app.router.add_get("/api/autopilot/logs", handle_autopilot_logs)
    app.router.add_post("/api/geheimwaffe/run", handle_geheimwaffe_run)
    app.router.add_post("/api/geheimwaffe/content", handle_geheimwaffe_content)
    app.router.add_get("/api/backup/status", handle_backup_status)
    app.router.add_post("/api/backup/run", handle_backup_run)

    # GMC route
    app.router.add_get("/api/gmc", handle_gmc)

    # New routes
    app.router.add_post("/api/mac/action", handle_mac_action)
    app.router.add_get("/api/services/status", handle_services_status)
    app.router.add_post("/api/services/action", handle_service_action)
    app.router.add_get("/api/logs", handle_logs)
    app.router.add_post("/api/logs/clear", handle_logs_clear)
    app.router.add_get("/api/processes", handle_processes)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/monitor", handle_monitor)
    app.router.add_post("/api/monitor/refresh", handle_monitor_refresh)

    # Self-Learner routes
    app.router.add_post("/api/remote-desktop/register", handle_remote_desktop_register)
    # Rudiclone routes
    app.router.add_post("/api/rudiclone/persona", handle_rudiclone_persona)
    app.router.add_post("/api/rudiclone/snapshot", handle_rudiclone_snapshot)
    app.router.add_get("/api/rudiclone/snapshots", handle_rudiclone_snapshots)
    app.router.add_get("/api/rudiclone/agents", handle_rudiclone_agents_status)
    app.router.add_post("/api/rudiclone/agents/start", handle_rudiclone_agents_start)
    app.router.add_post("/api/rudiclone/agents/run", handle_rudiclone_run_once)
    app.router.add_get("/api/self-learner/status", handle_self_learner_status)
    app.router.add_post("/api/self-learner/learn", handle_self_learner_learn)
    app.router.add_post("/api/self-learner/skills", handle_self_learner_skills)
    app.router.add_post("/api/self-learner/delete", handle_self_learner_delete)
    app.router.add_post("/api/self-learner/find-api", handle_self_learner_find_api)

    # Guardian / Eternal routes
    app.router.add_get("/api/guardian/health", handle_guardian_health)
    app.router.add_get("/api/guardian/status", handle_guardian_status)
    app.router.add_get("/api/guardian/services", handle_guardian_services)
    app.router.add_post("/api/guardian/heal", handle_guardian_heal)
    app.router.add_get("/api/guardian/agents", handle_guardian_agents)
    app.router.add_get("/api/guardian/brain", handle_guardian_brain)
    app.router.add_post("/api/guardian/notify", handle_guardian_notify)
    app.router.add_get("/api/guardian/backups", handle_guardian_backups)
    app.router.add_post("/api/guardian/backup", handle_guardian_backup)
    app.router.add_post("/api/guardian/restore", handle_guardian_restore)

    return app


if __name__ == "__main__":
    async def _main():
        app = await create_app()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_port=True)
        await site.start()
        print(f"\n{'='*50}\n  SuperMegaBot Dashboard\n  http://localhost:{PORT}\n{'='*50}\n")
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    asyncio.run(_main())
