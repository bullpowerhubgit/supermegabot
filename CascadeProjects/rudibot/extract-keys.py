#!/usr/bin/env python3
"""
extract-keys.py
Extrahiert alle API Keys aus .env.new und zeigt sie übersichtlich an
"""

import re
from pathlib import Path

def extract_keys_from_env_new():
    """Extrahiert alle API Keys aus .env.new"""
    env_new = Path("/Users/rudolfsarkany/CascadeProjects/rudibot/.env.new")
    
    if not env_new.exists():
        print("❌ .env.new nicht gefunden")
        return {}
    
    with open(env_new, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Patterns für verschiedene API Key Formate
    patterns = {
        'Anthropic Claude': r'sk-ant-api03-[a-zA-Z0-9_-]+',
        'OpenAI': r'sk-proj-[a-zA-Z0-9_-]+',
        'Perplexity': r'pplx-[a-zA-Z0-9_-]+',
        'GitHub Token': r'ghp_[a-zA-Z0-9]+',
        'GitHub PAT': r'github_pat_[a-zA-Z0-9_-]+',
        'Shopify Admin Token': r'shpat_[a-zA-Z0-9]+',
        'Shopify Secret': r'shpss_[a-zA-Z0-9]+',
        'Shopify Refresh': r'[a-f0-9]{32}-[0-9]+',
        'Shopify Automation': r'atkn_[a-zA-Z0-9_-]+',
        'Printify JWT': r'eyJ[a-zA-Z0-9._-]+',
        'Printify Token': r'prtapi_[a-zA-Z0-9]+',
        'Supabase Anon': r'eyJ[a-zA-Z0-9._-]{150,}',
        'Stripe': r'sk_live_[a-zA-Z0-9]+',
        'Telegram Bot': r'\d+:[a-zA-Z0-9_-]+',
        'YouTube API': r'AIzaSy[a-zA-Z0-9_-]+',
        'Google AI': r'AIzaSy[a-zA-Z0-9_-]+',
        'Klaviyo': r'pk_[a-zA-Z0-9_-]+',
        'Mailchimp': r'[a-f0-9]{32}-us\d{2}',
        'Digistore API': r'\d+-[a-zA-Z0-9]+',
        'Vercel Token': r'vercel_[a-zA-Z0-9]+',
        'Client ID': r'\d{13,}',
    }
    
    found_keys = {}
    
    for service, pattern in patterns.items():
        matches = re.findall(pattern, content)
        if matches:
            # Entferne Duplikate und nimm den längsten/besten Match
            unique_matches = list(set(matches))
            if unique_matches:
                found_keys[service] = unique_matches
    
    return found_keys

def extract_specific_from_lines():
    """Extrahiert Keys aus den spezifischen Linien die der User gezeigt hat"""
    
    # Aus den Zeilen 1119-1150 die neuen Keys
    specific_keys = {
        'Shopify Admin Token (neu)': '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',
        'Shopify API Key': '5cd88be4517ea081ce5518152b73e33f', 
        'Shopify Secret (neu)': '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',
        'Klaviyo Key (neu)': 'pk_X7HUrZ_933ca50212317aed57ac767e86e4d7b1e6',
    }
    
    return specific_keys

def compare_with_current_env():
    """Vergleicht gefundene Keys mit aktueller .env"""
    env_file = Path("/Users/rudolfsarkany/CascadeProjects/rudibot/.env")
    
    if not env_file.exists():
        print("❌ .env nicht gefunden")
        return {}
    
    with open(env_file, 'r') as f:
        current_content = f.read()
    
    # Extrahiere aktuelle Keys
    current_patterns = {
        'ANTHROPIC_API_KEY': r'sk-ant-api03-[a-zA-Z0-9_-]+',
        'OPENAI_API_KEY': r'sk-proj-[a-zA-Z0-9_-]+',
        'PERPLEXITY_API_KEY': r'pplx-[a-zA-Z0-9_-]+',
        'GITHUB_TOKEN': r'ghp_[a-zA-Z0-9]+',
        'SHOPIFY_ADMIN_TOKEN': r'shpat_[a-zA-Z0-9]+',
        'SHOPIFY_CLIENT_SECRET': r'shpss_[a-zA-Z0-9]+',
        'PRINTIFY_API_KEY': r'eyJ[a-zA-Z0-9._-]+',
        'STRIPE_API_KEY': r'sk_live_[a-zA-Z0-9]+',
        'TELEGRAM_BOT_TOKEN': r'\d+:[a-zA-Z0-9_-]+',
        'KLAVIYO_API_KEY': r'pk_[a-zA-Z0-9_-]+',
    }
    
    current_keys = {}
    for var, pattern in current_patterns.items():
        matches = re.findall(pattern, current_content)
        if matches:
            current_keys[var] = matches[0]
    
    return current_keys

def main():
    print("═══════════════════════════════════════════")
    print("  API KEY EXTRACTOR - .env.new")
    print("═══════════════════════════════════════════\n")
    
    # 1. Extrahiere alle Keys aus .env.new
    print("🔍 Gefundene Keys in .env.new:\n")
    all_keys = extract_keys_from_env_new()
    
    for service, keys in all_keys.items():
        print(f"📋 {service}:")
        for i, key in enumerate(keys[:3], 1):  # Max 3 anzeigen
            masked = key[:8] + "..." + key[-8:] if len(key) > 20 else key
            print(f"   {i}. {masked}")
        if len(keys) > 3:
            print(f"   ... und {len(keys)-3} weitere")
        print()
    
    # 2. Zeige spezifische neue Keys
    print("🆕 NEUE/VERÄNDERTE KEYS (aus Zeilen 1119-1150):\n")
    new_keys = extract_specific_from_lines()
    for service, key in new_keys.items():
        masked = key[:8] + "..." + key[-8:] if len(key) > 20 else key
        print(f"🔑 {service:25} {masked}")
    
    # 3. Vergleich mit aktueller .env
    print(f"\n🔄 Vergleich mit aktueller .env:\n")
    current_keys = compare_with_current_env()
    
    updates_needed = []
    
    # Prüfe Shopify Keys
    if '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' in str(all_keys.values()):
        current_shopify = current_keys.get('SHOPIFY_ADMIN_TOKEN', '')
        if current_shopify != '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':
            updates_needed.append(('SHOPIFY_ADMIN_TOKEN', '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'))
    
    # Prüfe Klaviyo Key
    if 'pk_X7HUrZ_933ca50212317aed57ac767e86e4d7b1e6' in str(all_keys.values()):
        current_klaviyo = current_keys.get('KLAVIYO_API_KEY', '')
        if current_klaviyo != 'pk_X7HUrZ_933ca50212317aed57ac767e86e4d7b1e6':
            updates_needed.append(('KLAVIYO_API_KEY', 'pk_X7HUrZ_933ca50212317aed57ac767e86e4d7b1e6'))
    
    # Prüfe Shopify Secret
    if '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' in str(all_keys.values()):
        current_secret = current_keys.get('SHOPIFY_CLIENT_SECRET', '')
        if current_secret != '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':
            updates_needed.append(('SHOPIFY_CLIENT_SECRET', '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'))
    
    if updates_needed:
        print("📝 BENÖTIGTE AKTUALISIERUNGEN:")
        for var, value in updates_needed:
            masked = value[:8] + "..." + value[-8:] if len(value) > 20 else value
            print(f"   • {var}: {masked}")
    else:
        print("✅ Alle Keys sind aktuell")
    
    print(f"\n═══════════════════════════════════════════")
    print(f"📊 Zusammenfassung:")
    print(f"   • In .env.new gefunden: {len(all_keys)} Service-Typen")
    print(f"   • Neue/veränderte Keys: {len(new_keys)}")
    print(f"   • Updates benötigt: {len(updates_needed)}")
    print(f"═══════════════════════════════════════════\n")
    
    return updates_needed

if __name__ == '__main__':
    main()
