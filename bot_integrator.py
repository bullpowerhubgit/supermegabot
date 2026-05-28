#!/usr/bin/env python3
"""
Bot Integrator — Zentrale Integration aller Projekte
Verbindet: Guardian, Shopify, Telegram, API Gateway, Auto-Heal, DeepScan
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/Users/rudolfsarkany/rudibot-eternal')
from guardian_client import GuardianClient

# ═══════════════════════════════════════════════════════════════════════
# SERVICE REGISTRY
# ═══════════════════════════════════════════════════════════════════════

SERVICES = {
    'guardian':      {'port': 3201, 'dir': '/Users/rudolfsarkany/rudibot-eternal',          'cmd': 'python3 eternal_guardian.py --api',     'health': '/api/v1/health'},
    'telegram_bot':  {'port': 3200, 'dir': '/Users/rudolfsarkany/windsurf-telegram-bot',    'cmd': 'npm start',                              'health': '/health'},
    'api_gateway':   {'port': 8080, 'dir': '/Users/rudolfsarkany/windsurf-api-gateway',     'cmd': 'npm start',                              'health': '/health'},
    'shopify_ai':    {'port': 3002, 'dir': '/Users/rudolfsarkany/shopify-ai-suite',           'cmd': 'node server.js',                         'health': '/health'},
    'github_app':    {'port': 3000, 'dir': '/Users/rudolfsarkany/windsurf-github-app',        'cmd': 'npm start',                              'health': '/health'},
    'shopify_suite': {'port': 3001, 'dir': '/Users/rudolfsarkany/windsurf-shopify-suite',    'cmd': 'npm start',                              'health': '/health'},
}

# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def log(msg, level='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    colors = {'info': '\033[36m', 'ok': '\033[32m', 'warn': '\033[33m', 'error': '\033[31m', 'reset': '\033[0m'}
    c = colors.get(level, colors['info'])
    print(f"{c}[{ts}] {msg}{colors['reset']}")

def check_port(port):
    """Pruefe ob Port belegt ist"""
    try:
        result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True, timeout=2)
        return result.returncode == 0 and bool(result.stdout.strip())
    except:
        return False

def http_get(host, port, path, timeout=3):
    """Einfacher HTTP GET"""
    try:
        req = urllib.request.Request(f'http://{host}:{port}{path}', method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:200]
    except Exception as e:
        return 0, str(e)

# ═══════════════════════════════════════════════════════════════════════
# SERVICE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def check_service(name, cfg):
    """Pruefe Service Health"""
    status, body = http_get('localhost', cfg['port'], cfg['health'])
    healthy = status == 200
    if healthy:
        log(f'{name}: ✅ Port {cfg["port"]} healthy', 'ok')
    else:
        log(f'{name}: ❌ Port {cfg["port"]} not responding (status={status})', 'warn')
    return healthy

def start_service(name, cfg):
    """Starte einen Service"""
    log(f'{name}: Starting...')
    try:
        subprocess.Popen(
            cfg['cmd'], shell=True, cwd=cfg['dir'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        time.sleep(3)
        if check_service(name, cfg):
            log(f'{name}: ✅ Started', 'ok')
            return True
        else:
            log(f'{name}: ⚠️ Start failed', 'warn')
            return False
    except Exception as e:
        log(f'{name}: ❌ Error: {e}', 'error')
        return False

def ensure_all_services():
    """Stelle sicher dass alle Services laufen"""
    log('═' * 60, 'info')
    log('ENSURING ALL SERVICES', 'info')
    log('═' * 60, 'info')

    results = {}
    for name, cfg in SERVICES.items():
        if check_service(name, cfg):
            results[name] = 'running'
        else:
            results[name] = 'starting'
            start_service(name, cfg)

    return results

# ═══════════════════════════════════════════════════════════════════════
# GUARDIAN INTEGRATION
# ═══════════════════════════════════════════════════════════════════════

def integrate_with_guardian():
    """Verbinde alle Services mit Guardian"""
    log('═' * 60, 'info')
    log('GUARDIAN INTEGRATION', 'info')
    log('═' * 60, 'info')

    try:
        client = GuardianClient()
    except Exception as e:
        log(f'Guardian Client Error: {e}', 'error')
        return False

    # Registriere alle Services als Agents
    for name, cfg in SERVICES.items():
        try:
            client.register_agent(
                agent_id=f'integrator-{name}',
                agent_type='service',
                endpoint=f'http://localhost:{cfg["port"]}'
            )
            log(f'Guardian: ✅ Registered {name}', 'ok')
        except Exception as e:
            log(f'Guardian: ⚠️ {name} registration: {e}', 'warn')

    # Sende Integrations-Notification
    try:
        client.notify(
            '🔗 Bot Integrator: Alle Services verbunden und bei Guardian registriert',
            priority='normal'
        )
        log('Guardian: ✅ Notification sent', 'ok')
    except Exception as e:
        log(f'Guardian: ⚠️ Notification: {e}', 'warn')

    return True

# ═══════════════════════════════════════════════════════════════════════
# BROADCAST — Agenten benachrichtigen
# ═══════════════════════════════════════════════════════════════════════

def broadcast_to_agents(message, priority='normal'):
    """Sende Nachricht an alle laufenden Agenten/ Services"""
    log('═' * 60, 'info')
    log('BROADCAST TO ALL AGENTS', 'info')
    log('═' * 60, 'info')

    # 1. Guardian Notification
    try:
        client = GuardianClient()
        client.notify(message, priority=priority)
        log('Guardian: ✅ Notification sent', 'ok')
    except Exception as e:
        log(f'Guardian: ⚠️ {e}', 'warn')

    # 2. HTTP Broadcast an alle Service /notify Endpoints (falls vorhanden)
    for name, cfg in SERVICES.items():
        for notify_path in ['/api/notify', '/notify', '/webhook']:
            try:
                req = urllib.request.Request(
                    f'http://localhost:{cfg["port"]}{notify_path}',
                    data=json.dumps({'message': message, 'priority': priority}).encode(),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        log(f'{name}: ✅ Notified via {notify_path}', 'ok')
                        break
            except:
                pass
        else:
            log(f'{name}: ℹ️  No notify endpoint (OK)', 'info')

    # 3. Telegram Bot Nachricht (falls aktiv)
    try:
        telegram_msg = f"📢 <b>System Update</b>\n\n{message}"
        req = urllib.request.Request(
            f'http://localhost:3200/api/notify',
            data=json.dumps({'message': telegram_msg}).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                log('Telegram Bot: ✅ Notified', 'ok')
    except:
        pass

    log('\n✅ Broadcast complete', 'ok')

# ═══════════════════════════════════════════════════════════════════════
# DEEPSCAN
# ═══════════════════════════════════════════════════════════════════════

def run_deepscan():
    """Fuehre DeepScan durch"""
    log('═' * 60, 'info')
    log('RUNNING DEEPSCAN', 'info')
    log('═' * 60, 'info')

    script = Path('/Users/rudolfsarkany/supermegabot/deep_scan_repair.py')
    if not script.exists():
        log('DeepScan script not found', 'error')
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script), '--fix'],
            capture_output=True, text=True, timeout=120,
            cwd='/Users/rudolfsarkany/supermegabot'
        )
        log('DeepScan completed', 'ok')
        if result.stdout:
            for line in result.stdout.splitlines()[-20:]:
                if line.strip():
                    log(f'  {line}', 'info')
        return True
    except Exception as e:
        log(f'DeepScan error: {e}', 'error')
        return False

# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD API
# ═══════════════════════════════════════════════════════════════════════

def get_master_status():
    """Erstelle Master Status JSON fuer Dashboard"""
    status = {
        'timestamp': datetime.now().isoformat(),
        'services': {},
        'guardian': {},
        'agents': []
    }

    # Service Health
    for name, cfg in SERVICES.items():
        code, body = http_get('localhost', cfg['port'], cfg['health'])
        status['services'][name] = {
            'port': cfg['port'],
            'healthy': code == 200,
            'status_code': code
        }

    # Guardian Status
    try:
        code, body = http_get('localhost', 3201, '/api/v1/health')
        if code == 200:
            status['guardian'] = json.loads(body)
    except:
        pass

    # Agents
    try:
        code, body = http_get('localhost', 3201, '/api/v1/agents')
        if code == 200:
            data = json.loads(body)
            status['agents'] = data.get('agents', [])
    except:
        pass

    return status

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log('╔══════════════════════════════════════════════════════════════╗', 'ok')
    log('║    BOT INTEGRATOR — Multi-Project Integration               ║', 'ok')
    log(f'║    {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                                  ║', 'ok')
    log('╚══════════════════════════════════════════════════════════════╝', 'ok')

    # 1. Services sicherstellen
    ensure_all_services()

    # 2. Guardian Integration
    integrate_with_guardian()

    # 3. DeepScan (optional)
    if '--deepscan' in sys.argv:
        run_deepscan()

    # 4. Status ausgeben
    status = get_master_status()
    log('═' * 60, 'info')
    log('MASTER STATUS', 'info')
    log('═' * 60, 'info')

    healthy = 0
    total = 0
    for name, svc in status['services'].items():
        total += 1
        if svc['healthy']:
            healthy += 1
            log(f'  ✅ {name:<20} Port {svc["port"]}', 'ok')
        else:
            log(f'  ❌ {name:<20} Port {svc["port"]} (code={svc["status_code"]})', 'warn')

    log(f'\n  Services: {healthy}/{total} healthy', 'ok' if healthy == total else 'warn')
    log(f'  Agents:   {len(status["agents"])} registered', 'info')

    # Speichere Status
    status_file = Path('/tmp/bot_integrator_status.json')
    status_file.write_text(json.dumps(status, indent=2))
    log(f'  Status:   {status_file}', 'info')

    log('\n✅ Integration complete', 'ok')

if __name__ == '__main__':
    main()
