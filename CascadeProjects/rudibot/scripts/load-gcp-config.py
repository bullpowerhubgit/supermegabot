#!/usr/bin/env python3
"""
load-gcp-config.py
Lädt die GCP-Konfiguration und synchronisiert Keys mit .env
"""

import json
import os
import sys
from pathlib import Path

# Pfade
BASE_DIR = Path(__file__).parent.parent
GCP_CONFIG = BASE_DIR / "RudiBot-Secure-API" / "gcp-config.json"
ENV_FILE = BASE_DIR / ".env"

def load_gcp_config():
    """Lädt gcp-config.json und gibt die Config-Dict zurück."""
    if not GCP_CONFIG.exists():
        print(f"❌ Datei nicht gefunden: {GCP_CONFIG}")
        sys.exit(1)
    
    with open(GCP_CONFIG, 'r') as f:
        config = json.load(f)
    
    return config

def get_project_id(config):
    """Extrahiert die GCP Projekt-ID."""
    return config.get('project', {}).get('id')

def get_service_account(config):
    """Extrahiert Service Account Info."""
    return config.get('service_account', {})

def get_api_keys(config):
    """Extrahiert alle API Keys aus der Config."""
    apis = config.get('apis', {})
    keys = {}
    for api_name, api_config in apis.items():
        if api_config.get('enabled') and api_config.get('api_key'):
            keys[api_name] = api_config['api_key']
    return keys

def update_env_file(keys_dict):
    """Aktualisiert .env mit neuen Keys (nur wenn sie existieren und nicht PLACEHOLDER sind)."""
    if not ENV_FILE.exists():
        print(f"❌ .env nicht gefunden: {ENV_FILE}")
        return False
    
    with open(ENV_FILE, 'r') as f:
        content = f.read()
    
    # Mapping: gcp-config api_name -> .env variable name
    mapping = {
        'youtube': 'YOUTUBE_API_KEY',
        'google_ai': 'GOOGLE_AI_API_KEY',
    }
    
    updated = []
    for api_name, var_name in mapping.items():
        if api_name in keys_dict:
            key = keys_dict[api_name]
            # Prüfe ob die Variable in .env existiert
            if f'{var_name}=' in content:
                # Ersetze den Wert
                import re
                pattern = rf'{var_name}=.*'
                replacement = f'{var_name}={key}'
                content = re.sub(pattern, replacement, content)
                updated.append(var_name)
    
    if updated:
        with open(ENV_FILE, 'w') as f:
            f.write(content)
        print(f"✅ .env aktualisiert: {', '.join(updated)}")
    else:
        print("ℹ️  Keine Änderungen in .env nötig")
    
    return True

def main():
    print("═══════════════════════════════════════════")
    print("  GCP CONFIG LOADER")
    print("═══════════════════════════════════════════\n")
    
    config = load_gcp_config()
    
    # Projekt Info
    project_id = get_project_id(config)
    print(f"📁 Projekt ID:     {project_id}")
    print(f"📛 Projekt Name:   {config.get('project', {}).get('name')}")
    print(f"🔢 Projekt Number: {config.get('project', {}).get('number')}")
    
    # Service Account
    sa = get_service_account(config)
    if sa:
        print(f"\n👤 Service Account: {sa.get('client_email')}")
        pk = sa.get('private_key', '')
        if pk and not pk.endswith('...'):
            print(f"🔑 Private Key:     ✅ Vorhanden")
        else:
            print(f"🔑 Private Key:     ⚠️  Platzhalter/Abgeschnitten")
    
    # API Keys
    keys = get_api_keys(config)
    print(f"\n🔑 Aktive API Keys:")
    for api_name, key in keys.items():
        masked = key[:10] + "..." + key[-4:] if len(key) > 20 else "***"
        print(f"   • {api_name:12} {masked}")
    
    # .env Sync
    print(f"\n🔄 Synchronisiere mit .env...")
    update_env_file(keys)
    
    print("\n═══════════════════════════════════════════")
    print("✅ GCP Config geladen und synchronisiert!")
    print("═══════════════════════════════════════════\n")
    
    return config

if __name__ == '__main__':
    main()
