#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  Monitoring Agent v1.0                                           ║
║  Überwacht alle Services · Sendet Alerts · Erstellt Reports    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, logging, urllib.request, socket, subprocess
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from webhook_notifier import broadcast

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('MonitoringAgent')

REPORT_DIR = Path(__file__).parent.parent / 'logs' / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

MONITORED_SERVICES = [
    {'name': 'RudiBot Main', 'port': 3200, 'url': 'http://localhost:3200/health'},
    {'name': 'Guardian API', 'port': 3201, 'url': 'http://localhost:3201/health'},
    {'name': 'Ollama LLM', 'port': 11434, 'url': 'http://localhost:11434/api/tags'},
    {'name': 'SuperMegaBot', 'port': 8888, 'url': 'http://localhost:8888'},
    {'name': 'Password-Sync', 'port': 3005, 'url': 'http://localhost:3005/health'},
    {'name': 'Auto-Heal', 'port': 9000, 'url': 'http://localhost:9000'},
    {'name': 'API Gateway', 'port': 8080, 'url': 'http://localhost:8080'},
    {'name': 'Redis', 'port': 6379, 'url': None},
]


def check_service(svc):
    if svc.get('url'):
        try:
            req = urllib.request.Request(svc['url'], method='HEAD', timeout=5)
            with urllib.request.urlopen(req) as resp:
                return resp.status < 500
        except urllib.error.HTTPError as e:
            return e.code < 500
        except:
            return False
    else:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect(('127.0.0.1', svc['port']))
            return True
        except:
            return False


def run_health_check():
    results = []
    down_services = []
    for svc in MONITORED_SERVICES:
        ok = check_service(svc)
        results.append({'name': svc['name'], 'port': svc['port'], 'status': 'UP' if ok else 'DOWN'})
        if not ok:
            down_services.append(svc['name'])
        log.info(f"{'✓' if ok else '✗'} {svc['name']} (:{svc['port']})")
    
    if down_services:
        broadcast(
            '⚠️ Service Alert',
            f"Services DOWN: {', '.join(down_services)}",
            'error'
        )
    
    return results, down_services


def generate_daily_report():
    results, down = run_health_check()
    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'summary': {
            'total': len(results),
            'up': sum(1 for r in results if r['status'] == 'UP'),
            'down': len(down),
        },
        'services': results,
    }
    
    # Save report
    report_file = REPORT_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.write_text(json.dumps(report, indent=2))
    log.info(f'Report saved: {report_file}')
    
    return report


def generate_weekly_report():
    report = generate_daily_report()
    uptime_pct = (report['summary']['up'] / report['summary']['total']) * 100
    
    broadcast(
        '📊 Weekly Report',
        f"Uptime: {uptime_pct:.1f}%\n"
        f"Services: {report['summary']['up']}/{report['summary']['total']} UP\n"
        f"Down: {', '.join([s['name'] for s in report['services'] if s['status'] == 'DOWN']) or 'None'}",
        'info'
    )
    return report


def main():
    log.info('Monitoring Agent started')
    while True:
        generate_daily_report()
        # Weekly report on Sundays
        if datetime.now().weekday() == 6:  # Sunday
            if datetime.now().hour == 8:
                generate_weekly_report()
        time.sleep(300)  # 5 minutes


if __name__ == '__main__':
    main()
