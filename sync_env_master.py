#!/usr/bin/env python3
"""
SuperMegaBot — Master ENV Sync
================================
Liest Keys aus supermegabot/.env und synchronisiert sie in alle Satelliten-Projekte.
Im Gegensatz zum alten sync_env.py sind KEINE Werte hartcodiert.

Usage:
  python3 sync_env_master.py              # Sync aller Projekte
  python3 sync_env_master.py --dry-run    # Nur anzeigen
  python3 sync_env_master.py --validate   # ENV validieren + API tests
  python3 sync_env_master.py --railway    # Railway Variables sync (braucht railway CLI)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Master .env laden ──────────────────────────────────────────────────────────
MASTER_ENV = Path(__file__).parent / ".env"

def load_master() -> dict[str, str]:
    """Lädt alle Keys aus der Master .env."""
    if not MASTER_ENV.exists():
        print(f"❌ Master .env nicht gefunden: {MASTER_ENV}")
        sys.exit(1)
    result: dict[str, str] = {}
    for line in MASTER_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if k and v and v not in ("", '""', "''"):
            result[k] = v
    return result

MASTER: dict[str, str] = {}

# ── Projekte, die Keys brauchen ────────────────────────────────────────────────
PROJECTS = [
    # (Pfad zu .env, [Keys die gesynct werden sollen])
    (
        "/Users/rudolfsarkany/windsurf-auto-heal/.env",
        ["SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_API_KEY", "SHOPIFY_API_SECRET",
         "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    ),
    (
        "/Users/rudolfsarkany/windsurf-github-app/.env",
        ["GITHUB_TOKEN", "GITHUB_WEBHOOK_SECRET", "GITHUB_USER"],
    ),
    (
        "/Users/rudolfsarkany/windsurf-telegram-bot/.env",
        ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "AUTHORIZED_USER_ID",
         "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
    ),
    (
        "/Users/rudolfsarkany/windsurf-api-gateway/.env",
        ["SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN", "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN"],
    ),
    (
        "/Users/rudolfsarkany/rudibot-eternal/.env",
        ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
         "GITHUB_TOKEN", "SHOPIFY_ACCESS_TOKEN"],
    ),
    (
        "/Users/rudolfsarkany/kivo/.env",
        ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
    ),
    # supermegabot selbst — stellt sicher dass alle Keys vorhanden sind
    (
        "/Users/rudolfsarkany/supermegabot/.env",
        [
            # AI Keys
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
            "OPENROUTER_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY",
            # Core
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "GITHUB_TOKEN", "GITHUB_USER",
            # Commerce
            "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ACCESS_TOKEN",
            "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
            "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
            # Marketing
            "KLAVIYO_API_KEY", "MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX",
            "PRINTIFY_API_KEY", "DIGISTORE24_API_KEY",
            # Social
            "META_ACCESS_TOKEN", "META_PAGE_ID", "INSTAGRAM_ACCOUNT_ID",
            "TWITTER_API_KEY_AIITEC",
        ],
    ),
]

# ── RAILWAY KEYS — welche Keys auf Railway gesetzt sein müssen ─────────────────
RAILWAY_REQUIRED = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
    "OPENROUTER_API_KEY", "GEMINI_API_KEY",
    "SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_API_KEY", "SHOPIFY_API_SECRET",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PUBLISHABLE_KEY",
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY",
    "KLAVIYO_API_KEY", "MAILCHIMP_API_KEY", "MAILCHIMP_SERVER_PREFIX",
    "PRINTIFY_API_KEY", "DIGISTORE24_API_KEY",
    "META_ACCESS_TOKEN", "META_PAGE_ID", "INSTAGRAM_ACCOUNT_ID",
    "GITHUB_TOKEN",
]

PLACEHOLDER_RE = re.compile(r"^(your_|REPLACE_|TODO_|xxx|<|DEIN_|placeholder|changeme)", re.I)


def backup_env(path: Path) -> Path | None:
    if not path.exists():
        return None
    bak = path.parent / (path.name + ".bak")
    if not bak.exists() or (datetime.now().timestamp() - bak.stat().st_mtime) > 3600:
        shutil.copy2(path, bak)
        return bak
    return None


def sync_project(path_str: str, keys: list[str], dry_run: bool = False) -> str:
    global MASTER
    p = Path(path_str)
    if not p.parent.exists():
        return f"  ⏭️  SKIP {p.parent} (existiert nicht)"

    if not p.exists():
        if dry_run:
            return f"  [DRY] Würde erstellen: {p}"
        p.write_text("# Auto-generated .env\n", encoding="utf-8")

    lines = p.read_text(encoding="utf-8").splitlines()
    existing: dict[str, str] = {}
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            existing[k.strip()] = v.strip()

    appends, updates = [], []
    for key in keys:
        if key not in MASTER:
            continue
        val = MASTER[key]
        if not val:
            continue
        if key not in existing:
            appends.append(key)
        elif PLACEHOLDER_RE.match(existing[key]) or existing[key] == "":
            updates.append(key)

    if not appends and not updates:
        return f"  ✅ OK      {p}"

    if dry_run:
        return f"  [DRY] {p.name}: +{len(appends)} neu, ~{len(updates)} ersetzt"

    bak = backup_env(p)
    new_lines = []
    for line in lines:
        s = line.strip()
        replaced = False
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            k = k.strip()
            if k in updates and MASTER.get(k):
                new_lines.append(f"{k}={MASTER[k]}")
                replaced = True
        if not replaced:
            new_lines.append(line)

    if appends:
        new_lines += ["", "# ── Synced from supermegabot/.env ──────────────────"]
        for key in appends:
            new_lines.append(f"{key}={MASTER[key]}")

    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    bak_note = f" (bak: {bak.name})" if bak else ""
    return f"  ✅ UPDATED {p}: +{len(appends)} neu, ~{len(updates)} ersetzt{bak_note}"


def sync_railway(dry_run: bool = False):
    """Setzt alle fehlenden Railway-Variables über CLI."""
    if not shutil.which("railway"):
        print("  ⚠️  railway CLI nicht installiert. Installieren: npm i -g @railway/cli")
        return
    print("\n  Lade Railway-Variablen…")
    try:
        result = subprocess.run(
            ["railway", "variables", "--json"],
            capture_output=True, text=True, timeout=30
        )
        existing_vars = json.loads(result.stdout) if result.stdout else {}
    except Exception as e:
        print(f"  ❌ railway variables --json fehlgeschlagen: {e}")
        return

    to_set = []
    for key in RAILWAY_REQUIRED:
        if key in MASTER and key not in existing_vars:
            to_set.append(key)

    if not to_set:
        print("  ✅ Alle Railway-Variablen vorhanden")
        return

    print(f"  Setze {len(to_set)} fehlende Railway-Variablen…")
    for key in to_set:
        val = MASTER[key]
        if dry_run:
            print(f"    [DRY] railway variables set {key}=***")
        else:
            r = subprocess.run(
                ["railway", "variables", "set", f"{key}={val}", "--service", "supermegabot"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                print(f"    ✅ {key}")
            else:
                print(f"    ❌ {key}: {r.stderr[:100]}")


def check_missing_railway_keys():
    """Zeigt welche Keys auf Railway fehlen könnten."""
    print("\n  Railway Required Keys:")
    for key in RAILWAY_REQUIRED:
        in_master = key in MASTER and bool(MASTER[key])
        status = "✅" if in_master else "❌"
        print(f"    {status} {key}")


def main():
    global MASTER
    parser = argparse.ArgumentParser(description="SuperMegaBot ENV Sync")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", action="store_true", help="API Tests ausführen")
    parser.add_argument("--railway", action="store_true", help="Railway Variables sync")
    parser.add_argument("--check-railway", action="store_true", help="Railway Keys anzeigen")
    args = parser.parse_args()

    MASTER = load_master()
    print(f"\n{'═'*55}")
    print(f"  SuperMegaBot Master ENV Sync")
    print(f"  Keys in Master: {len(MASTER)}")
    print(f"{'═'*55}\n")

    for path_str, keys in PROJECTS:
        result = sync_project(path_str, keys, dry_run=args.dry_run)
        print(result)

    if args.railway:
        sync_railway(dry_run=args.dry_run)

    if args.check_railway:
        check_missing_railway_keys()

    if args.validate:
        print("\n  Starte API-Validierung…")
        import subprocess
        subprocess.run([sys.executable, str(Path(__file__).parent / "env_validator.py")])

    print(f"\n{'═'*55}")
    print("  Sync abgeschlossen.")
    print(f"{'═'*55}\n")


if __name__ == "__main__":
    main()
