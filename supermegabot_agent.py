#!/usr/bin/env python3
"""
SuperMegaBot Analyzer Agent
Registers with Guardian, checks all service health, reports anomalies, and sends real notifications.
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

# Load .env
def _load_env():
    for p in [Path(__file__).parent / '.env', Path('.env')]:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, val = line.partition('=')
                    val = val.split('#')[0].strip()
                    if key.strip() and key.strip() not in os.environ:
                        os.environ[key.strip()] = val
            break
        except FileNotFoundError:
            pass

_load_env()
sys.path.insert(0, str(Path(__file__).parent))
from guardian_client import GuardianClient

AGENT_ID = "supermegabot-analyzer"
AGENT_TYPE = "analyzer"

SMB_URL = os.getenv('SUPERMEGABOT_URL', 'http://localhost:8888')

SERVICE_PORTS = {
    'guardian':      int(os.getenv('GUARDIAN_API_PORT', '3201')),
    'supermegabot':  int(os.getenv('PORT', '8888')),
    'telegram_bot':  3200,
    'api_gateway':   8080,
    'shopify_ai':    3002,
    'github_app':    3000,
    'shopify_suite': 3001,
}


def _http_get(url: str, timeout: int = 4) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:500]
    except Exception as e:
        return 0, str(e)


def check_port(port: int) -> bool:
    """Check if a port is listening."""
    try:
        result = subprocess.run(
            ['ss', '-tnlp', f'sport = :{port}'],
            capture_output=True, text=True, timeout=3
        )
        return str(port) in result.stdout
    except Exception:
        # fallback: try HTTP
        code, _ = _http_get(f'http://localhost:{port}/', timeout=2)
        return code > 0


def analyze_services() -> dict:
    """Check all known service ports and report status."""
    results = {}
    for name, port in SERVICE_PORTS.items():
        healthy = check_port(port)
        results[name] = {
            'port': port,
            'healthy': healthy,
            'checked_at': datetime.now(timezone.utc).isoformat()
        }
    return results


def analyze_system() -> dict:
    """Read basic system metrics."""
    metrics = {}
    try:
        with open('/proc/meminfo') as f:
            lines = {l.split(':')[0]: l.split(':')[1].strip() for l in f if ':' in l}
        total = int(lines.get('MemTotal', '0 kB').split()[0])
        avail = int(lines.get('MemAvailable', '0 kB').split()[0])
        metrics['mem_used_pct'] = round((total - avail) / total * 100, 1) if total else 0
    except Exception:
        pass

    try:
        with open('/proc/loadavg') as f:
            parts = f.read().split()
        metrics['load_1m'] = float(parts[0])
        metrics['load_5m'] = float(parts[1])
    except Exception:
        pass

    try:
        result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=3)
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                metrics['disk_used_pct'] = int(parts[4].rstrip('%'))
                break
    except Exception:
        pass

    return metrics


def analyze_logs() -> list[str]:
    """Scan recent log files for ERROR/CRITICAL lines."""
    issues = []
    log_paths = [
        Path(__file__).parent / 'logs',
        Path('/tmp'),
    ]
    for base in log_paths:
        for log_file in list(base.glob('*.log'))[:5] if base.exists() else []:
            try:
                lines = log_file.read_text(errors='ignore').splitlines()
                for line in lines[-200:]:
                    if any(kw in line.upper() for kw in ('ERROR', 'CRITICAL', 'EXCEPTION', 'TRACEBACK')):
                        issues.append(f"[{log_file.name}] {line[:120]}")
            except Exception:
                pass
    return issues[:20]


def build_report(services: dict, system: dict, log_issues: list) -> dict:
    unhealthy = [name for name, s in services.items() if not s['healthy']]
    return {
        'agent_id': AGENT_ID,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'services': services,
        'system': system,
        'log_issues_count': len(log_issues),
        'log_issues_sample': log_issues[:5],
        'unhealthy_services': unhealthy,
        'overall_status': 'degraded' if unhealthy else 'healthy',
    }


def main():
    print(f"[{AGENT_ID}] Starting up...")

    try:
        client = GuardianClient()
    except ValueError as e:
        print(f"ERROR: Guardian Client init failed: {e}")
        print("Set GUARDIAN_API_SECRET in .env or environment.")
        return 1

    # Register with Guardian
    try:
        result = client.register_agent(AGENT_ID, AGENT_TYPE, endpoint=SMB_URL)
        print(f"Guardian registration: {result.get('registered', result)}")
    except Exception as e:
        print(f"WARN: Guardian registration: {e}")

    # Run analysis
    print("Analyzing services...")
    services = analyze_services()
    print("Reading system metrics...")
    system = analyze_system()
    print("Scanning logs...")
    log_issues = analyze_logs()

    report = build_report(services, system, log_issues)

    # Print report
    print(json.dumps(report, indent=2))

    # Report to Guardian
    unhealthy = report['unhealthy_services']
    if unhealthy:
        msg = f"⚠️ {AGENT_ID}: {len(unhealthy)} service(s) unhealthy: {', '.join(unhealthy)}"
        priority = "high"
    else:
        msg = f"✅ {AGENT_ID}: All {len(services)} services healthy. Mem: {system.get('mem_used_pct', '?')}% Load: {system.get('load_1m', '?')}"
        priority = "normal"

    if log_issues:
        msg += f" | {len(log_issues)} log error(s) found"

    try:
        result = client.notify(msg, priority=priority)
        print(f"Notification sent: {result.get('sent', False)}")
    except Exception as e:
        print(f"WARN: Notification failed: {e}")

    # Save report to /tmp for other processes to read
    report_path = Path('/tmp/supermegabot_analyzer_report.json')
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report saved: {report_path}")

    return 0 if not unhealthy else 1


if __name__ == '__main__':
    sys.exit(main())
