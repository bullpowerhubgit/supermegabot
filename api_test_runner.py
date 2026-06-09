#!/usr/bin/env python3
"""
API Test Runner — Automatische API-Validierung vor Deployment
Prüft alle Services auf Verfügbarkeit, korrekte Responses und Auth-Fehler.
"""

import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# SERVICE REGISTRY
# ═══════════════════════════════════════════════════════════════════════

SERVICES = {
    'guardian': {
        'port': 3201,
        'endpoints': [
            {'path': '/api/v1/status', 'method': 'GET', 'expect_status': 200},
            {'path': '/api/v1/agents', 'method': 'GET', 'expect_status': 200},
        ]
    },
    'telegram_bot': {
        'port': 3200,
        'endpoints': [
            {'path': '/api/status', 'method': 'GET', 'expect_status': 200},
            {'path': '/api/shopify/status', 'method': 'GET', 'expect_status': 200, 'expect_keys': ['success', 'products', 'orders']},
            {'path': '/api/dashboard/live', 'method': 'GET', 'expect_status': 200, 'expect_keys': ['timestamp', 'system']},
        ]
    },
    'shopify_suite': {
        'port': 3001,
        'endpoints': [
            {'path': '/health', 'method': 'GET', 'expect_status': 200},
            {'path': '/api/orders', 'method': 'GET', 'expect_status': 200, 'expect_keys': ['orders', 'count']},
            {'path': '/api/products', 'method': 'GET', 'expect_status': 200, 'expect_keys': ['products', 'count']},
        ]
    },
    'shopify_ai': {
        'port': 3002,
        'endpoints': [
            {'path': '/health', 'method': 'GET', 'expect_status': 200},
        ]
    },
    'api_gateway': {
        'port': 8080,
        'endpoints': [
            {'path': '/status', 'method': 'GET', 'expect_status': 200},
            {'path': '/health', 'method': 'GET', 'expect_status': 200},
        ]
    },
    'windsurf_telegram': {
        'port': 8000,
        'endpoints': [
            {'path': '/health', 'method': 'GET', 'expect_status': 200},
            {'path': '/api/shopify/orders', 'method': 'GET', 'expect_status': 200, 'expect_keys': ['orders']},
        ]
    },
}

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

def log(msg, level='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    colors = {'info': '\033[36m', 'ok': '\033[32m', 'warn': '\033[33m', 'error': '\033[31m', 'reset': '\033[0m'}
    c = colors.get(level, colors['info'])
    print(f"{c}[{ts}] {msg}{colors['reset']}")

# ═══════════════════════════════════════════════════════════════════════
# HTTP HELPERS
# ═══════════════════════════════════════════════════════════════════════

def http_request(host, port, path, method='GET', timeout=5):
    """Einfacher HTTP Request mit Fehlerbehandlung"""
    try:
        req = urllib.request.Request(f'http://{host}:{port}{path}', method=method)
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {'_raw': body[:200]}
            return {
                'status': resp.status,
                'data': data,
                'error': None
            }
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'data': {}, 'error': f'HTTP {e.code}: {e.reason}'}
    except urllib.error.URLError as e:
        return {'status': 0, 'data': {}, 'error': f'Connection failed: {e.reason}'}
    except Exception as e:
        return {'status': 0, 'data': {}, 'error': str(e)}

# ═══════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════

def run_tests():
    log('╔══════════════════════════════════════════════════════════════╗', 'ok')
    log('║    API TEST RUNNER — Pre-Deployment Validation              ║', 'ok')
    log(f'║    {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                                  ║', 'ok')
    log('╚══════════════════════════════════════════════════════════════╝', 'ok')
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for service_name, service_cfg in SERVICES.items():
        log(f'\n{"═"*60}', 'info')
        log(f'Testing {service_name.upper()} (port {service_cfg["port"]})', 'info')
        log(f'{"═"*60}', 'info')
        
        # Check if service is running
        is_optional = service_cfg.get('optional', False)
        health = http_request('localhost', service_cfg['port'], '/health', timeout=2)
        if health['status'] == 0:
            if is_optional:
                log(f'  ⚠️  Optional service {service_name} not running (port {service_cfg["port"]}) — skipping', 'warn')
                continue
            else:
                log(f'  ❌ Service not reachable on port {service_cfg["port"]}', 'error')
                failed_tests.append(f'{service_name}: Service offline')
                continue
        
        for endpoint in service_cfg['endpoints']:
            total_tests += 1
            path = endpoint['path']
            method = endpoint.get('method', 'GET')
            expect_status = endpoint.get('expect_status', 200)
            expect_keys = endpoint.get('expect_keys', [])
            
            result = http_request('localhost', service_cfg['port'], path, method)
            
            # Check status
            status_ok = result['status'] == expect_status
            
            # Check expected keys in response
            keys_ok = True
            missing_keys = []
            for key in expect_keys:
                if key not in result['data']:
                    keys_ok = False
                    missing_keys.append(key)
            
            # Check for auth errors in response body
            auth_error = False
            if result['data']:
                data_str = json.dumps(result['data'])
                if '401' in data_str or '403' in data_str or 'Token ungültig' in data_str:
                    auth_error = True
            
            if status_ok and keys_ok and not auth_error:
                log(f'  ✅ {method} {path} → {result["status"]}', 'ok')
                passed_tests += 1
            else:
                errors = []
                if not status_ok:
                    errors.append(f'status={result["status"]} (expected {expect_status})')
                if missing_keys:
                    errors.append(f'missing keys: {missing_keys}')
                if auth_error:
                    errors.append('AUTH ERROR in response')
                if result['error']:
                    errors.append(result['error'])
                
                log(f'  ❌ {method} {path} → {", ".join(errors)}', 'error')
                failed_tests.append(f'{service_name}:{path}')
    
    # Summary
    log('\n' + '═'*60, 'info')
    log('TEST SUMMARY', 'info')
    log('═'*60, 'info')
    log(f'  Total:   {total_tests}', 'info')
    log(f'  Passed:  {passed_tests}', 'ok')
    log(f'  Failed:  {len(failed_tests)}', 'error' if failed_tests else 'ok')
    
    if failed_tests:
        log('\n  Failed tests:', 'error')
        for ft in failed_tests:
            log(f'    • {ft}', 'error')
        log('\n  ⚠️  DEPLOYMENT BLOCKED — Fix errors first', 'error')
        return False
    else:
        log('\n  ✅ ALL TESTS PASSED — Safe to deploy', 'ok')
        return True

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    ok = run_tests()
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
