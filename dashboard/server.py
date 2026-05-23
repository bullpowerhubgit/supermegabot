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

from aiohttp import web
import aiohttp

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
    {"id": "cratorhub", "name": "CreatorHub", "port": 3000,
     "start_cmd": "cd '/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/Documents/GitHub/digifabrik' && nohup npx tsx server.ts >> /tmp/cratorhub.log 2>&1 &",
     "pattern": "digifabrik.*server", "icon": "🎨"},
    {"id": "ollama", "name": "Ollama LLM", "port": 11434,
     "start_cmd": "ollama serve &",
     "pattern": "ollama serve", "icon": "🧠"},
    {"id": "openclaw", "name": "OpenClaw Gateway", "port": 18789,
     "start_cmd": "openclaw gateway run",
     "pattern": "openclaw", "icon": "🦞"},
    # ── Heute gebaut ────────────────────────────────────────────────────────
    {"id": "shopify_ai_suite", "name": "Shopify AI Suite (Railway)", "port": 0,
     "start_cmd": "echo 'Deployed on Railway: https://shopify-suite-v2-production.up.railway.app'",
     "pattern": "RAILWAY_REMOTE",
     "url": "https://shopify-suite-v2-production.up.railway.app",
     "health_url": "https://shopify-suite-v2-production.up.railway.app/health",
     "icon": "🛍️"},
    {"id": "windsurf_shopify", "name": "Windsurf API Gateway", "port": 18789,
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
          <option value="fast">llama3.2 (schnell)</option>
          <option value="gemma4">gemma4</option>
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
        <span>CreatorHub Server</span><span class="badge badge-yellow">Port 3000</span>
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
async function api(path, data=null) {
  try {
    const opts = data
      ? { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) }
      : {};
    const r = await fetch('/api' + path, opts);
    return await r.json();
  } catch(e) { return { error: e.message }; }
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
  ).join('\n');
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
  document.getElementById('chat-box').innerHTML = '<div class="msg msg-bot">Chat geleert. Wie kann ich helfen?</div>';
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
  const r = await api('/shopify/status');
  const el = document.getElementById('shopify-data');
  if (r.ok) {
    el.innerHTML = `<div>Store: <strong>${r.store || 'N/A'}</strong></div>
      <div>Produkte: ${r.products || '?'} · Bestellungen: ${r.orders || '?'}</div>
      <div style="margin-top:4px"><span class="badge badge-green">✓ Verbunden</span></div>`;
  } else if (r.error && r.error.includes('401')) {
    el.innerHTML = `<span class="badge badge-orange">⚠ Token abgelaufen</span>
      <div style="margin-top:6px;font-size:0.72rem;color:var(--muted)">Neu generieren: suitenew.myshopify.com → Admin → Apps → API-Zugangsdaten</div>`;
  } else {
    el.innerHTML = `<div class="error-text">${r.error || 'Nicht verbunden'}</div>
      <div style="margin-top:4px"><span class="badge badge-yellow">⚠ Setup erforderlich</span></div>`;
  }
}

async function shopifyAction(type) {
  showToast(type + ' wird geladen...', true);
  const el = document.getElementById('shopify-data');
  const r = await api('/shopify/status');
  if (!r.ok) { showToast(r.error || 'Shopify Fehler', false); return; }
  el.innerHTML = `<div style="color:var(--muted);font-size:0.75rem">${type} – Daten kommen direkt vom Shopify API</div>`;
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
  document.getElementById('log-box').innerHTML = '<div style="opacity:0.4">Logs geleert</div>';
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
    text += '\n';
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
        return web.json_response({"prices": prices})
    except Exception as e:
        return web.json_response({"error": str(e)})


async def handle_trading_arbitrage(req):
    try:
        from modules.trading_bot import TradingBot
        bot = TradingBot()
        opps = await bot.scan_quick()
        return web.json_response({"opportunities": opps})
    except Exception as e:
        return web.json_response({"error": str(e)})


async def handle_telegram_status(req):
    token = TELEGRAM_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    return web.json_response({
        "configured": bool(token),
        "chat_id": TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", ""),
    })


async def handle_telegram_send(req):
    if not TELEGRAM_TOKEN:
        return web.json_response({"ok": False, "error": "No token configured"})
    try:
        data = await req.json()
        message = data.get("message", "")
        chat_id = TELEGRAM_CHAT_ID
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"chat_id": chat_id, "text": message}) as r:
                ok = r.status == 200
                return web.json_response({"ok": ok})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def handle_shopify_status(req):
    store = os.getenv("SHOPIFY_STORE_URL", "")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    if not store or not token:
        return web.json_response({"ok": False, "error": "SHOPIFY_STORE_URL / SHOPIFY_ACCESS_TOKEN nicht gesetzt"})
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            url = f"{store}/admin/api/2024-01/shop.json"
            headers = {"X-Shopify-Access-Token": token}
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    d = await r.json()
                    return web.json_response({"ok": True, "store": d.get("shop", {}).get("name", store)})
                return web.json_response({"ok": False, "error": f"HTTP {r.status}"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


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
            result = await ap.run_task(goal, agent_id)
            return web.json_response({"results": [result]})
        else:
            results = await ap.run_autopilot_mode(goal)
            return web.json_response({"results": results})
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
        result = await run_full_automation(niche)
        return web.json_response(result)
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
            result = await generate_product_listing(product)
        elif content_type == "social":
            result = await generate_social_content(product, platform)
        elif content_type == "ads":
            result = await generate_ad_copy(product)
        else:
            result = {"error": "Unbekannter content_type"}
        return web.json_response(result)
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
        pid = None
        try:
            ps = subprocess.run(["pgrep", "-f", svc["pattern"]], capture_output=True, text=True)
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


async def handle_health(req):
    return web.json_response({
        "status": "ok",
        "service": "supermegabot-dashboard",
        "port": PORT,
        "uptime": time.time(),
    })


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
# App Factory
# ---------------------------------------------------------------------------

async def create_app():
    from core.mega_orchestrator import MegaOrchestrator
    bot = MegaOrchestrator()
    await bot.start()

    app = web.Application()
    app["bot"] = bot

    # Existing routes
    app.router.add_get("/", handle_index)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/system", handle_system)
    app.router.add_get("/api/services", handle_services_legacy)
    app.router.add_get("/api/trading/prices", handle_trading_prices)
    app.router.add_get("/api/trading/arbitrage", handle_trading_arbitrage)
    app.router.add_get("/api/telegram/status", handle_telegram_status)
    app.router.add_post("/api/telegram/send", handle_telegram_send)
    app.router.add_get("/api/shopify/status", handle_shopify_status)
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
    app.router.add_get("/api/processes", handle_processes)
    app.router.add_get("/health", handle_health)

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
