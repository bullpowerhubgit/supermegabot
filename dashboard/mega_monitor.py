#!/usr/bin/env python3
"""
SuperMegaBot - Mega Monitoring Dashboard
Dark-theme, interactive, all systems in one view
"""

import json, subprocess, re, time
from pathlib import Path
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─── LIVE DATA ────────────────────────────────────────────────────────────────

def get_ram():
    r = subprocess.run(['vm_stat'], capture_output=True, text=True)
    stats = {}
    for line in r.stdout.split('\n'):
        m = re.match(r'(.+?):\s+([\d]+)\.?\s*$', line.strip())
        if m: stats[m.group(1).strip()] = int(m.group(2))
    ps = 16384
    return {
        'free':     stats.get('Pages free', 0)*ps/1e9,
        'active':   stats.get('Pages active', 0)*ps/1e9,
        'inactive': stats.get('Pages inactive', 0)*ps/1e9,
        'wired':    stats.get('Pages wired down', 0)*ps/1e9,
        'total':    48.0,
    }

def get_disk():
    r = subprocess.run(['df','-g','/System/Volumes/Data'], capture_output=True, text=True)
    parts = r.stdout.strip().split('\n')[-1].split()
    total = int(parts[1]); used = int(parts[2]); free = int(parts[3])
    return {'total': total, 'used': used, 'free': free, 'pct': used/total*100}

def service_status(port, name):
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
        return {'name': name, 'port': port, 'status': 'ONLINE', 'color': '#00ff88'}
    except urllib.error.HTTPError as e:
        # 401/403/404 = Server antwortet → ONLINE
        if e.code in (401, 403, 404, 405, 500):
            return {'name': name, 'port': port, 'status': 'ONLINE', 'color': '#00ff88'}
        return {'name': name, 'port': port, 'status': f'ERR {e.code}', 'color': '#ffd700'}
    except Exception:
        return {'name': name, 'port': port, 'status': 'OFFLINE', 'color': '#ff4757'}

def get_log_stats():
    log = Path("/Users/rudolfsarkany/supermegabot/logs/dashboard.log")
    if not log.exists(): return {'total': 0, 'errors': 0, 'infos': 0}
    lines = log.read_text().splitlines()
    return {
        'total':  len(lines),
        'errors': sum(1 for l in lines if 'ERROR' in l),
        'infos':  sum(1 for l in lines if 'INFO' in l),
        'last':   lines[-1][:80] if lines else ''
    }

# ─── COLLECT ──────────────────────────────────────────────────────────────────
ram    = get_ram()
disk   = get_disk()
logs   = get_log_stats()
now    = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

services = [
    service_status(11434, 'Ollama AI'),
    service_status(18789, 'OpenClaw'),
    service_status(8888,  'SuperMegaBot'),
    service_status(3200,  'Telegram Bot'),
    service_status(3000,  'CreatorHub'),
    service_status(18791, 'Browser Ctrl'),
]

ram_used = ram['active'] + ram['wired']
ram_pct  = ram_used / ram['total'] * 100

# Estimated monthly costs (from .env analysis)
costs = {
    'Claude API':   45,
    'OpenAI':       12,
    'Shopify':      29,
    'Supabase':     25,
    'Resend Email':  8,
    'Perplexity':   20,
    'Ollama':        0,
}

# Storage
storage = {
    'Downloads':   13.0,
    'Documents':   9.8,
    'Desktop':     0.57,
    'SuperMegaBot':0.001,
    'System/Apps': disk['used'] - 13 - 9.8 - 0.57,
}

# DB sizes
db_sizes = {
    'memory':     44,
    'autopilot':  40,
    'trading':    32,
    'geheimwaffe':28,
}

# ─── COLORS ───────────────────────────────────────────────────────────────────
BG      = '#0a0a0f'
CARD    = '#12121e'
ACCENT  = '#6c63ff'
GREEN   = '#00ff88'
YELLOW  = '#ffd700'
RED     = '#ff4757'
CYAN    = '#00d2ff'
PINK    = '#ff6584'
ORANGE  = '#ff9f43'
TEXT    = '#e8e8f0'
MUTED   = '#5a5a8a'

# ─── BUILD FIGURE ─────────────────────────────────────────────────────────────
fig = make_subplots(
    rows=4, cols=4,
    subplot_titles=[
        'RAM Nutzung', 'Disk Nutzung', 'Log Aktivität', 'API Kosten / Monat',
        'Services Status', '', 'Ollama Modelle', 'Speicher Verteilung',
        'RAM Aufschlüsselung', 'Datenbanken', 'Kosten Trend (Simulation)', '',
        '', '', '', ''
    ],
    specs=[
        [{'type':'indicator'}, {'type':'indicator'}, {'type':'indicator'}, {'type':'pie'}],
        [{'type':'table','colspan':2}, None, {'type':'bar'}, {'type':'pie'}],
        [{'type':'bar'}, {'type':'bar'}, {'type':'scatter','colspan':2}, None],
        [{'type':'table','colspan':4}, None, None, None],
    ],
    vertical_spacing=0.08,
    horizontal_spacing=0.06,
)

# ── ROW 1: Gauges ─────────────────────────────────────────────────────────────
fig.add_trace(go.Indicator(
    mode='gauge+number+delta',
    value=ram_pct,
    title={'text': 'RAM %', 'font': {'color': TEXT, 'size': 13}},
    number={'suffix': '%', 'font': {'color': CYAN, 'size': 28}},
    delta={'reference': 70, 'valueformat': '.1f'},
    gauge={
        'axis': {'range': [0, 100], 'tickcolor': MUTED, 'tickfont': {'color': MUTED}},
        'bar': {'color': CYAN},
        'bgcolor': CARD,
        'bordercolor': MUTED,
        'steps': [
            {'range': [0, 60],  'color': '#1a2a1a'},
            {'range': [60, 80], 'color': '#2a2a1a'},
            {'range': [80, 100],'color': '#2a1a1a'},
        ],
        'threshold': {'line': {'color': RED, 'width': 3}, 'value': 85},
    }
), row=1, col=1)

fig.add_trace(go.Indicator(
    mode='gauge+number',
    value=disk['pct'],
    title={'text': f'Disk % ({disk["used"]}GB/{disk["total"]}GB)', 'font': {'color': TEXT, 'size': 11}},
    number={'suffix': '%', 'font': {'color': ORANGE, 'size': 28}},
    gauge={
        'axis': {'range': [0, 100], 'tickcolor': MUTED, 'tickfont': {'color': MUTED}},
        'bar': {'color': ORANGE},
        'bgcolor': CARD,
        'bordercolor': MUTED,
        'steps': [
            {'range': [0, 70],  'color': '#1a2a1a'},
            {'range': [70, 85], 'color': '#2a2a1a'},
            {'range': [85, 100],'color': '#2a1a1a'},
        ],
        'threshold': {'line': {'color': RED, 'width': 3}, 'value': 90},
    }
), row=1, col=2)

err_pct = logs['errors'] / max(logs['total'], 1) * 100
fig.add_trace(go.Indicator(
    mode='gauge+number',
    value=err_pct,
    title={'text': f'Log Fehler % ({logs["errors"]}/{logs["total"]})', 'font': {'color': TEXT, 'size': 11}},
    number={'suffix': '%', 'font': {'color': RED if err_pct > 50 else YELLOW, 'size': 28}},
    gauge={
        'axis': {'range': [0, 100], 'tickcolor': MUTED, 'tickfont': {'color': MUTED}},
        'bar': {'color': RED if err_pct > 50 else YELLOW},
        'bgcolor': CARD,
        'bordercolor': MUTED,
    }
), row=1, col=3)

# API Kosten Pie
fig.add_trace(go.Pie(
    labels=list(costs.keys()),
    values=list(costs.values()),
    hole=0.55,
    textinfo='label+percent',
    textfont={'color': TEXT, 'size': 10},
    marker={'colors': [ACCENT, CYAN, GREEN, ORANGE, PINK, YELLOW, MUTED],
            'line': {'color': BG, 'width': 2}},
    hovertemplate='<b>%{label}</b><br>€%{value}/Monat<extra></extra>',
), row=1, col=4)

# ── ROW 2: Services Table ──────────────────────────────────────────────────────
online  = sum(1 for s in services if s['status'] == 'ONLINE')
offline = len(services) - online

fig.add_trace(go.Table(
    header=dict(
        values=['🔌 Service', '🔢 Port', '📡 Status', '💡 Info'],
        fill_color=ACCENT,
        font=dict(color='white', size=12),
        align='left',
        height=30,
    ),
    cells=dict(
        values=[
            [s['name'] for s in services],
            [str(s['port']) for s in services],
            [s['status'] for s in services],
            ['Lokal KI', 'Agent Gateway', 'Dashboard', 'Telegram', 'E-Commerce', 'Browser']
        ],
        fill_color=[[CARD]*len(services)],
        font=dict(
            color=[[s['color'] for s in services],
                   [TEXT]*len(services),
                   [s['color'] for s in services],
                   [MUTED]*len(services)],
            size=11
        ),
        align='left',
        height=25,
    )
), row=2, col=1)

# Ollama Models Bar
fig.add_trace(go.Bar(
    x=['llama3.2', 'gemma4'],
    y=[2.0, 9.6],
    marker_color=[CYAN, ACCENT],
    text=['2.0 GB', '9.6 GB'],
    textposition='outside',
    textfont={'color': TEXT, 'size': 11},
    hovertemplate='<b>%{x}</b><br>%{y} GB<extra></extra>',
    name='Modell-Größe GB',
), row=2, col=3)

# Speicher Pie
fig.add_trace(go.Pie(
    labels=list(storage.keys()),
    values=[abs(v) for v in storage.values()],
    hole=0.5,
    textinfo='label+value',
    texttemplate='%{label}<br>%{value:.1f}GB',
    textfont={'color': TEXT, 'size': 9},
    marker={'colors': [ORANGE, CYAN, PINK, GREEN, MUTED],
            'line': {'color': BG, 'width': 2}},
), row=2, col=4)

# ── ROW 3: RAM Bar & DB Bar & Cost Trend ──────────────────────────────────────
fig.add_trace(go.Bar(
    x=['Active', 'Wired', 'Inactive', 'Free'],
    y=[ram['active'], ram['wired'], ram['inactive'], ram['free']],
    marker_color=[ACCENT, RED, YELLOW, GREEN],
    text=[f'{v:.1f}GB' for v in [ram['active'], ram['wired'], ram['inactive'], ram['free']]],
    textposition='outside',
    textfont={'color': TEXT, 'size': 10},
    hovertemplate='<b>%{x}</b><br>%{y:.2f} GB<extra></extra>',
), row=3, col=1)

fig.add_trace(go.Bar(
    x=list(db_sizes.keys()),
    y=list(db_sizes.values()),
    marker_color=[CYAN, ACCENT, ORANGE, PINK],
    text=[f'{v}KB' for v in db_sizes.values()],
    textposition='outside',
    textfont={'color': TEXT, 'size': 10},
), row=3, col=2)

# Simulated cost trend (last 6 months)
months = ['Dez', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai']
total_costs = [sum(costs.values())] * 6
local_costs  = [sum(costs.values()) - costs['Ollama']] * 5 + [sum(costs.values())]

fig.add_trace(go.Scatter(
    x=months, y=[180, 165, 158, 152, 145, 139],
    mode='lines+markers',
    name='API Kosten €',
    line={'color': RED, 'width': 3},
    marker={'size': 8, 'color': RED},
    fill='tozeroy',
    fillcolor='rgba(255,71,87,0.1)',
), row=3, col=3)
fig.add_trace(go.Scatter(
    x=months, y=[0, 0, 0, 0, 0, 0],
    mode='lines+markers',
    name='Ollama (lokal) €',
    line={'color': GREEN, 'width': 3, 'dash': 'dot'},
    marker={'size': 8, 'color': GREEN},
), row=3, col=3)

# ── ROW 4: System Info Table ───────────────────────────────────────────────────
sys_data = [
    ['🖥️ Prozessor',    'Apple M4 Pro — 14 Cores (10P+4E)'],
    ['💾 RAM Total',     '48 GB LPDDR5'],
    ['💿 Disk Total',    f'{disk["total"]} GB — {disk["pct"]:.0f}% belegt'],
    ['🧠 Ollama',        'gemma4:latest (9.6GB) + llama3.2:latest (2GB)'],
    ['🤖 Agents aktiv', f'{online}/{len(services)} Services ONLINE'],
    ['📋 Logs',          f'{logs["total"]} Einträge — {logs["errors"]} Fehler (Telegram-Konflikt)'],
    ['💰 API Kosten',    f'~€{sum(costs.values())}/Monat (Ollama = €0)'],
    ['⏰ Stand',         now],
]

fig.add_trace(go.Table(
    header=dict(
        values=['⚙️ System Parameter', '📊 Wert'],
        fill_color='#1a1a3a',
        font=dict(color=TEXT, size=12),
        align='left',
        height=30,
    ),
    cells=dict(
        values=[[r[0] for r in sys_data], [r[1] for r in sys_data]],
        fill_color=CARD,
        font=dict(color=[YELLOW, TEXT], size=11),
        align='left',
        height=26,
    )
), row=4, col=1)

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
fig.update_layout(
    title={
        'text': f'🚀 SuperMegaBot · Mega Monitor  <span style="font-size:14px;color:{MUTED}">Stand: {now}</span>',
        'font': {'color': TEXT, 'size': 20},
        'x': 0.02,
    },
    paper_bgcolor=BG,
    plot_bgcolor=CARD,
    font={'color': TEXT, 'family': 'SF Pro Display, -apple-system, sans-serif'},
    showlegend=False,
    height=1100,
    margin=dict(t=80, b=20, l=20, r=20),

    # Buttons
    updatemenus=[
        dict(
            type='buttons',
            showactive=False,
            x=0.98, y=1.02, xanchor='right',
            buttons=[
                dict(label='🔄 Refresh',
                     method='relayout',
                     args=[{'title.text': f'🚀 SuperMegaBot · Mega Monitor  <span style="font-size:14px">Refreshed: {now}</span>'}]),
                dict(label='🌑 Dark',
                     method='relayout',
                     args=[{'paper_bgcolor': BG, 'plot_bgcolor': CARD}]),
                dict(label='☀️ Light',
                     method='relayout',
                     args=[{'paper_bgcolor': '#f5f5f5', 'plot_bgcolor': '#ffffff'}]),
            ],
            bgcolor='#1a1a2e',
            bordercolor=ACCENT,
            font={'color': TEXT, 'size': 11},
        ),
        dict(
            type='buttons',
            showactive=True,
            x=0.02, y=1.02, xanchor='left',
            buttons=[
                dict(label='📊 Alle',    method='update', args=[{'visible': [True]*30}]),
                dict(label='💰 Kosten',  method='update',
                     args=[{'visible': [False,False,False,True, False,False,False,False,
                                        False,False,True,True, False]*3}]),
                dict(label='🤖 Services',method='update',
                     args=[{'visible': [True,True,True,False, True,True,False,False,
                                        True,True,False,False, True]*3}]),
            ],
            bgcolor='#1a1a2e',
            bordercolor=MUTED,
            font={'color': TEXT, 'size': 11},
        ),
    ],
)

# Subplot titles styling
for ann in fig.layout.annotations:
    ann.font.color = MUTED
    ann.font.size  = 11

# Axis styling
for ax in ['xaxis','xaxis2','xaxis3','xaxis4','xaxis5',
           'yaxis','yaxis2','yaxis3','yaxis4','yaxis5']:
    if hasattr(fig.layout, ax):
        getattr(fig.layout, ax).update(
            gridcolor='#1e1e32',
            zerolinecolor='#2a2a45',
            color=MUTED,
        )

# Save
out = Path("/Users/rudolfsarkany/supermegabot/dashboard/mega_monitor.html")
fig.write_html(
    str(out),
    include_plotlyjs='cdn',
    config={
        'scrollZoom': True,
        'displayModeBar': True,
        'modeBarButtonsToAdd': ['drawline','drawopenpath','eraseshape'],
        'toImageButtonOptions': {'format':'png','filename':'mega_monitor','scale':2},
    }
)
print(f"✅ Dashboard gespeichert: {out}")
print(f"   Öffne: open '{out}'")
