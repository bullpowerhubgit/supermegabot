#!/usr/bin/env python3
"""
Shopify Token Renewer — Automatische Token-Prüfung & Erneuerung
Scannt alle .env Dateien, testet alle Tokens, wählt gültigen aus.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════
# KONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

STORE_DOMAIN = os.getenv('SHOPIFY_SHOP_DOMAIN', 'suitenew.myshopify.com')
API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2024-10')

PROJECT_DIRS = [
    '/Users/rudolfsarkany/local-projects/telegram-automation-bot',
    '/Users/rudolfsarkany/windsurf-telegram-bot',
    '/Users/rudolfsarkany/windsurf-shopify-suite',
    '/Users/rudolfsarkany/shopify-ai-suite',
    '/Users/rudolfsarkany/rudibot-eternal',
    '/Users/rudolfsarkany/supermegabot',
]

# ═══════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════

def log(msg, level='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    colors = {'info': '\033[36m', 'ok': '\033[32m', 'warn': '\033[33m', 'error': '\033[31m', 'reset': '\033[0m'}
    c = colors.get(level, colors['info'])
    print(f"{c}[{ts}] {msg}{colors['reset']}")

# ═══════════════════════════════════════════════════════════════════════
# TOKEN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

def extract_tokens_from_env(env_path: Path):
    """Extrahiere alle Shopify Tokens aus einer .env Datei"""
    tokens = {}
    if not env_path.exists():
        return tokens
    
    content = env_path.read_text()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for key in ['SHOPIFY_ACCESS_TOKEN', 'SHOPIFY_ACCESS_TOKEN_2', 'SHOPIFY_ADMIN_TOKEN',
                    'SHOPIFY_OPENAIR_TOKEN', 'SHOPIFY_SUITE_ACCESS_TOKEN']:
            if line.startswith(f'{key}='):
                val = line.split('=', 1)[1].strip()
                if val and len(val) > 10:
                    tokens[key] = val
    return tokens

def find_all_tokens():
    """Scanne alle Projekte nach Tokens"""
    all_tokens = {}
    log('Scanning all projects for Shopify tokens...', 'info')
    
    for proj_dir in PROJECT_DIRS:
        env_path = Path(proj_dir) / '.env'
        if env_path.exists():
            tokens = extract_tokens_from_env(env_path)
            if tokens:
                all_tokens[proj_dir] = tokens
                log(f'  Found {len(tokens)} token(s) in {env_path.name}')
    
    return all_tokens

# ═══════════════════════════════════════════════════════════════════════
# TOKEN VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def test_token(token: str, shop_domain: str = None) -> dict:
    """Teste einen Token gegen die Shopify API"""
    domain = shop_domain or STORE_DOMAIN
    if not domain.startswith('http'):
        domain = f'https://{domain}'
    
    url = f"{domain}/admin/api/{API_VERSION}/shop.json"
    
    try:
        req = urllib.request.Request(url, method='GET')
        req.add_header('X-Shopify-Access-Token', token)
        req.add_header('Content-Type', 'application/json')
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return {
                'valid': True,
                'status': resp.status,
                'shop': data.get('shop', {}).get('name', 'unknown'),
                'domain': data.get('shop', {}).get('domain', domain),
            }
    except urllib.error.HTTPError as e:
        return {
            'valid': False,
            'status': e.code,
            'error': f'HTTP {e.code}: {e.reason}',
        }
    except Exception as e:
        return {
            'valid': False,
            'status': 0,
            'error': str(e),
        }

# ═══════════════════════════════════════════════════════════════════════
# TOKEN RENEWAL VIA CLI REFRESH
# ═══════════════════════════════════════════════════════════════════════

def try_cli_refresh(env_path: Path) -> str:
    """Versuche Token über Shopify CLI Refresh Token zu erneuern"""
    if not env_path.exists():
        return None
    
    content = env_path.read_text()
    
    # Extract credentials
    refresh_token = None
    client_id = None
    
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('SHOPIFY_CLI_REFRESH_TOKEN='):
            refresh_token = line.split('=', 1)[1].strip()
        if line.startswith('SHOPIFY_CLI_CLIENT_ID='):
            client_id = line.split('=', 1)[1].strip()
    
    if not refresh_token or not client_id:
        log('  No CLI refresh credentials found', 'warn')
        return None
    
    log('  Attempting CLI token refresh...', 'info')
    
    # Shopify OAuth token endpoint
    token_url = 'https://accounts.shopify.com/oauth/token'
    payload = {
        'client_id': client_id,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(token_url, data=data, headers={
            'Content-Type': 'application/json'
        }, method='POST')
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if 'access_token' in result:
                log('  ✅ CLI refresh successful!', 'ok')
                return result['access_token']
            else:
                log(f'  ⚠️ Refresh response: {result}', 'warn')
                return None
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else 'unknown'
        log(f'  ❌ CLI refresh failed: HTTP {e.code} — {body[:100]}', 'error')
        return None
    except Exception as e:
        log(f'  ❌ CLI refresh error: {e}', 'error')
        return None

# ═══════════════════════════════════════════════════════════════════════
# ENV UPDATE
# ═══════════════════════════════════════════════════════════════════════

def update_env_token(env_path: Path, new_token: str, backup: bool = True):
    """Aktualisiere SHOPIFY_ACCESS_TOKEN in .env Datei"""
    if not env_path.exists():
        return False
    
    content = env_path.read_text()
    
    # Backup
    if backup:
        backup_path = env_path.with_suffix('.env.bak')
        backup_path.write_text(content)
        log(f'  Backup saved: {backup_path.name}')
    
    # Update token
    new_content = []
    updated = False
    for line in content.splitlines():
        if line.strip().startswith('SHOPIFY_ACCESS_TOKEN=') and not line.strip().startswith('SHOPIFY_ACCESS_TOKEN_'):
            new_content.append(f'SHOPIFY_ACCESS_TOKEN={new_token}')
            updated = True
        else:
            new_content.append(line)
    
    if not updated:
        new_content.append(f'\n# Updated by shopify_token_renewer.py\nSHOPIFY_ACCESS_TOKEN={new_token}')
    
    env_path.write_text('\n'.join(new_content))
    log(f'  ✅ Updated: {env_path}')
    return True

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    log('╔══════════════════════════════════════════════════════════════╗', 'ok')
    log('║    SHOPIFY TOKEN RENEWER                                     ║', 'ok')
    log(f'║    {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                                  ║', 'ok')
    log('╚══════════════════════════════════════════════════════════════╝', 'ok')
    
    # 1. Find all tokens
    all_tokens = find_all_tokens()
    
    if not all_tokens:
        log('No Shopify tokens found in any project!', 'error')
        sys.exit(1)
    
    # 2. Test all tokens
    log('═' * 60, 'info')
    log('Testing all tokens...', 'info')
    log('═' * 60, 'info')
    
    valid_tokens = []
    for proj_dir, tokens in all_tokens.items():
        for key, token in tokens.items():
            result = test_token(token)
            if result['valid']:
                log(f'  ✅ {key}: VALID (Shop: {result["shop"]})', 'ok')
                valid_tokens.append((proj_dir, key, token, result))
            else:
                log(f'  ❌ {key}: {result["error"]}', 'error')
    
    # 3. If valid token found, sync to all projects
    if valid_tokens:
        best_proj, best_key, best_token, best_result = valid_tokens[0]
        log(f'\n✅ Valid token found in {Path(best_proj).name}: {best_key}', 'ok')
        log(f'   Shop: {best_result["shop"]} ({best_result["domain"]})', 'ok')
        
        log('\n═' * 60, 'info')
        log('Syncing valid token to all projects...', 'info')
        log('═' * 60, 'info')
        
        for proj_dir in PROJECT_DIRS:
            env_path = Path(proj_dir) / '.env'
            if env_path.exists() and proj_dir != best_proj:
                update_env_token(env_path, best_token)
        
        log('\n✅ All projects updated with valid token!', 'ok')
        return 0
    
    # 4. No valid token — try CLI refresh
    log('\n' + '═' * 60, 'warn')
    log('No valid tokens found. Attempting CLI refresh...', 'warn')
    log('═' * 60, 'warn')
    
    for proj_dir in PROJECT_DIRS:
        env_path = Path(proj_dir) / '.env'
        if not env_path.exists():
            continue
        
        log(f'Trying {Path(proj_dir).name}...')
        new_token = try_cli_refresh(env_path)
        
        if new_token:
            # Test the new token
            result = test_token(new_token)
            if result['valid']:
                log(f'\n✅ New token valid! Shop: {result["shop"]}', 'ok')
                
                # Sync to all
                for p in PROJECT_DIRS:
                    ep = Path(p) / '.env'
                    if ep.exists():
                        update_env_token(ep, new_token)
                
                log('\n✅ All projects updated with refreshed token!', 'ok')
                return 0
            else:
                log(f'  ⚠️ Refreshed token invalid: {result["error"]}', 'warn')
    
    # 5. Everything failed — manual instructions
    log('\n' + '═' * 60, 'error')
    log('AUTOMATIC RENEWAL FAILED', 'error')
    log('═' * 60, 'error')
    log('''
Manual steps required:

1. Go to your Shopify Admin:
   https://suitenew.myshopify.com/admin/settings/apps_and_sales_channels

2. Click "Develop apps" → "Create an app"

3. Configure Admin API access scopes:
   - read_products, write_products
   - read_orders, write_orders
   - read_customers, write_customers
   - read_inventory, write_inventory
   - read_themes, write_themes

4. Install the app to your store

5. Copy the Admin API access token

6. Update all .env files:
''', 'error')
    
    for proj_dir in PROJECT_DIRS:
        env_path = Path(proj_dir) / '.env'
        if env_path.exists():
            log(f'   {env_path}', 'info')
    
    log('\n   SHOPIFY_ACCESS_TOKEN=shpat_YOUR_NEW_TOKEN', 'ok')
    log('\nOr run: shopify app generate-token', 'ok')
    
    return 1

if __name__ == '__main__':
    sys.exit(main())
