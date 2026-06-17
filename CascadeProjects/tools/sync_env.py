#!/usr/bin/env python3
"""
ENV Sync Tool — synchronisiert Secrets aus supermegabot master in Projekt-.envs
Erstellt fehlende Dateien, ersetzt Platzhalter, behält bestehende Werte.
Nutze: python3 sync_env.py [--dry-run]
"""

import argparse
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
# Master-Werte aus supermegabot
# ═══════════════════════════════════════════════════════════════════════════════
MASTER = {
    'TELEGRAM_BOT_TOKEN': '8600739487:AAHBUDXDfazS9ySOt-p0d2_Ye-OxWx5tWVA',
    'TELEGRAM_CHAT_ID': '5088771245',
    'AUTHORIZED_USER_ID': '5088771245',
    'GITHUB_TOKEN': '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',
    'GITHUB_FINE_GRAINED_TOKEN': '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',
    'GITHUB_USER': 'bullpowerhubgit',
    'GITHUB_WEBHOOK_SECRET': '212f381fa2fc6c037d305756c56d6330f9c70447e37fdc55a0bc4da274f1cc3a',
    'OPENAI_API_KEY': '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',
    'ANTHROPIC_API_KEY': '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',
    'SHOPIFY_ACCESS_TOKEN': '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',
    'SHOPIFY_SHOP_DOMAIN': 'autopilot-store-suite-fmbka.myshopify.com',
    'SHOPIFY_SHOP': 'autopilot-store-suite-fmbka',
    'SHOPIFY_API_KEY': '5cd88be4517ea081ce5518152b73e33f',
    'SHOPIFY_API_SECRET': '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',
    'SHOPIFY_WEBHOOK_SECRET': '212f381fa2fc6c037d305756c56d6330f9c70447e37fdc55a0bc4da274f1cc3a',
    'OLLAMA_URL': 'http://127.0.0.1:11434',
    'OLLAMA_MODEL': 'gemma4:latest',
}

PLACEHOLDER_RE = re.compile(r'^(your_|REPLACE_|TODO_|xxx)', re.I)


def backup_env(path: Path) -> Optional[Path]:
    """Erstellt .env.bak vor dem Überschreiben (max 1 Backup pro Tag)."""
    if not path.exists():
        return None
    bak = path.parent / (path.name + '.bak')
    # Überschreibe Backup nur wenn älter als 1h (vermeidet Spam bei mehreren Runs)
    if not bak.exists() or (datetime.now() - datetime.fromtimestamp(bak.stat().st_mtime)).total_seconds() > 3600:
        shutil.copy2(path, bak)
        return bak
    return None


def sync_env(path_str: str, keys_to_sync: list[str], dry_run: bool = False) -> str:
    p = Path(path_str)
    created = False

    if not p.exists():
        if dry_run:
            return f"  [DRY] Würde erstellen: {p}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Auto-generated .env\n", encoding="utf-8")
        created = True

    lines = p.read_text(encoding="utf-8").splitlines()
    existing: dict[str, str] = {}
    for line in lines:
        line_s = line.strip()
        if line_s and not line_s.startswith('#') and '=' in line_s:
            k, _, v = line_s.partition('=')
            existing[k.strip()] = v.strip()

    appends: list[str] = []
    updates: list[str] = []
    for key in keys_to_sync:
        if key not in MASTER:
            continue
        val = MASTER[key]
        if not val:
            continue
        if key not in existing:
            appends.append(key)
        elif PLACEHOLDER_RE.match(existing[key]):
            updates.append(key)

    if not appends and not updates:
        status = "CREATED" if created else "OK"
        return f"  {status}: {p.name}"

    if dry_run:
        return f"  [DRY] {p.name}: +{len(appends)} neu, ~{len(updates)} ersetzt"

    bak = backup_env(p)
    new_lines: list[str] = []
    for line in lines:
        line_s = line.strip()
        replaced = False
        if line_s and not line_s.startswith('#') and '=' in line_s:
            k, sep, v = line_s.partition('=')
            k = k.strip()
            if k in updates and PLACEHOLDER_RE.match(v.strip()):
                new_lines.append(f"{k}={MASTER[k]}")
                replaced = True
        if not replaced:
            new_lines.append(line)

    if appends:
        new_lines.append("")
        new_lines.append("# ── Synced from supermegabot master ──────────────────────────────────")
        for key in appends:
            new_lines.append(f"{key}={MASTER[key]}")

    p.write_text('\n'.join(new_lines) + '\n', encoding="utf-8")
    return f"  {'CREATED' if created else 'UPDATED'} {p}: +{len(appends)} neu, ~{len(updates)} ersetzt" + (f" (bak: {bak.name})" if bak else "")


PROJECTS = [
    ('/Users/rudolfsarkany/windsurf-auto-heal/.env',
     ['SHOPIFY_SHOP', 'SHOPIFY_API_KEY', 'SHOPIFY_API_SECRET', 'SHOPIFY_ACCESS_TOKEN',
      'GITHUB_TOKEN', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']),
    ('/Users/rudolfsarkany/windsurf-github-app/.env',
     ['GITHUB_TOKEN', 'GITHUB_WEBHOOK_SECRET', 'GITHUB_USER']),
    ('/Users/rudolfsarkany/windsurf-telegram-bot/.env',
     ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'AUTHORIZED_USER_ID',
      'OLLAMA_URL', 'OLLAMA_MODEL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']),
    ('/Users/rudolfsarkany/windsurf-api-gateway/.env',
     ['SHOPIFY_ACCESS_TOKEN', 'SHOPIFY_SHOP_DOMAIN', 'TELEGRAM_BOT_TOKEN', 'GITHUB_TOKEN']),
    ('/Users/rudolfsarkany/rudibot-eternal/.env',
     ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
      'GITHUB_TOKEN', 'SHOPIFY_ACCESS_TOKEN', 'OLLAMA_URL']),
    ('/Users/rudolfsarkany/kivo/.env',
     ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OLLAMA_URL']),
]


def main():
    parser = argparse.ArgumentParser(description="Sync ENV files across projects")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht schreiben")
    args = parser.parse_args()

    print("=== ENV SYNC ERGEBNISSE ===")
    for path, keys in PROJECTS:
        result = sync_env(path, keys, dry_run=args.dry_run)
        print(result)
    print("=== FERTIG ===")


if __name__ == "__main__":
    main()
