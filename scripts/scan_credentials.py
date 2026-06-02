#!/usr/bin/env python3
"""
scan_credentials.py — Scannt ALLE .env-Dateien auf dem System
und merged sie in ~/supermegabot/.env

Ausführen: python3 ~/supermegabot/scripts/scan_credentials.py
"""

import os
import re
import sys
from pathlib import Path

HOME = Path.home()
MEGA_ENV = HOME / "supermegabot" / ".env"

# Bekannte Projekte die .env-Dateien haben könnten
SCAN_DIRS = [
    HOME / "supermegabot",
    HOME / "telegram-automation-bot",
    HOME / "windsurf-telegram-bot",
    HOME / "windsurf-shopify-suite",
    HOME / "windsurf-api-gateway",
    HOME / "windsurf-auto-heal",
    HOME / "rudibot-eternal",
    HOME / "local-projects" / "telegram-automation-bot",
    HOME / "digifabrik",
    HOME / "cratorhub",
    HOME / "shopify-dashboard",
    HOME / "nailschip",
    HOME / "password-sync-suite",
    HOME,  # ~/.env
]

# Keys die wir suchen (Mapping: Key → Kategorie)
KEY_CATEGORIES = {
    # Shopify
    "SHOPIFY_ACCESS_TOKEN": "Shopify",
    "SHOPIFY_SHOP_DOMAIN": "Shopify",
    "SHOPIFY_API_KEY": "Shopify",
    "SHOPIFY_API_SECRET": "Shopify",
    "SHOPIFY_WEBHOOK_SECRET": "Shopify",
    # Telegram
    "TELEGRAM_BOT_TOKEN": "Telegram",
    "TELEGRAM_CHAT_ID": "Telegram",
    # Social Media
    "TIKTOK_CLIENT_KEY": "TikTok",
    "TIKTOK_CLIENT_SECRET": "TikTok",
    "TIKTOK_ACCESS_TOKEN": "TikTok",
    "PINTEREST_ACCESS_TOKEN": "Pinterest",
    "PINTEREST_BOARD_ID": "Pinterest",
    "META_ACCESS_TOKEN": "Meta/Instagram",
    "META_PAGE_ID": "Meta/Instagram",
    "INSTAGRAM_ACCOUNT_ID": "Meta/Instagram",
    "FACEBOOK_ACCESS_TOKEN": "Meta/Instagram",
    "FACEBOOK_PAGE_ID": "Meta/Instagram",
    "REDDIT_CLIENT_ID": "Reddit",
    "REDDIT_CLIENT_SECRET": "Reddit",
    "REDDIT_USERNAME": "Reddit",
    "REDDIT_PASSWORD": "Reddit",
    "YOUTUBE_API_KEY": "YouTube",
    "YOUTUBE_CHANNEL_ID": "YouTube",
    "TWITTER_BEARER_TOKEN": "Twitter/X",
    "TWITTER_API_KEY": "Twitter/X",
    "TWITTER_API_SECRET": "Twitter/X",
    "TWITTER_ACCESS_TOKEN": "Twitter/X",
    "TWITTER_ACCESS_SECRET": "Twitter/X",
    "DISCORD_BOT_TOKEN": "Discord",
    "DISCORD_CHANNEL_ID": "Discord",
    "DISCORD_WEBHOOK_URL": "Discord",
    # E-Commerce
    "DIGISTORE24_API_KEY": "Digistore24",
    "ETSY_API_KEY": "Etsy",
    "ETSY_ACCESS_TOKEN": "Etsy",
    "ETSY_SHOP_ID": "Etsy",
    "GUMROAD_ACCESS_TOKEN": "Gumroad",
    "PRINTIFY_API_KEY": "Printify",
    "PRINTIFY_SHOP_ID": "Printify",
    "MAILCHIMP_API_KEY": "Mailchimp",
    "MAILCHIMP_SERVER_PREFIX": "Mailchimp",
    "KLAVIYO_API_KEY": "Klaviyo",
    "STRIPE_SECRET_KEY": "Stripe",
    "STRIPE_PUBLISHABLE_KEY": "Stripe",
    # AI
    "OPENAI_API_KEY": "OpenAI",
    "ANTHROPIC_API_KEY": "Anthropic",
    "PERPLEXITY_API_KEY": "Perplexity",
    "GOOGLE_API_KEY": "Google",
    "GOOGLE_CLIENT_ID": "Google",
    "GOOGLE_CLIENT_SECRET": "Google",
    # Infrastructure
    "GITHUB_TOKEN": "GitHub",
    "SUPABASE_URL": "Supabase",
    "SUPABASE_ANON_KEY": "Supabase",
    "SUPABASE_SERVICE_KEY": "Supabase",
    "RAILWAY_TOKEN": "Railway",
    "GUARDIAN_API_SECRET": "Guardian",
}

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def parse_env_file(path: Path) -> dict:
    """Parse .env file, return dict of key→value."""
    result = {}
    try:
        text = path.read_text(errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # Remove surrounding quotes
            if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]
            # Skip empty values
            if val and not val.startswith("#"):
                result[key] = val
    except Exception:
        pass
    return result


def scan_all() -> dict:
    """Scan all .env files, return merged dict (last value wins for duplicates)."""
    found: dict[str, tuple[str, Path]] = {}  # key → (value, source_path)
    scanned = []

    for scan_dir in SCAN_DIRS:
        for env_file in [scan_dir / ".env", scan_dir / ".env.local", scan_dir / ".env.production"]:
            if env_file.exists():
                scanned.append(env_file)
                parsed = parse_env_file(env_file)
                for k, v in parsed.items():
                    if k in KEY_CATEGORIES:
                        if k not in found:  # first occurrence wins
                            found[k] = (v, env_file)

    # Also scan subdirectories one level deep
    for scan_dir in [HOME, HOME / "local-projects"]:
        if not scan_dir.exists():
            continue
        try:
            for subdir in scan_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("."):
                    env_file = subdir / ".env"
                    if env_file.exists() and env_file not in scanned:
                        scanned.append(env_file)
                        parsed = parse_env_file(env_file)
                        for k, v in parsed.items():
                            if k in KEY_CATEGORIES and k not in found:
                                found[k] = (v, env_file)
        except PermissionError:
            pass

    return found, scanned


def update_mega_env(found: dict):
    """Add found keys to ~/supermegabot/.env if not already present."""
    if MEGA_ENV.exists():
        current = parse_env_file(MEGA_ENV)
    else:
        current = {}

    new_entries = {}
    for key, (val, src) in found.items():
        if key not in current or not current[key] or current[key].startswith("#"):
            new_entries[key] = (val, src)

    if not new_entries:
        return 0

    # Append new entries to .env
    existing_text = MEGA_ENV.read_text() if MEGA_ENV.exists() else ""
    additions = [f"\n# ── Auto-gefunden von scan_credentials.py ──────────────────────────────────────"]
    for key, (val, src) in sorted(new_entries.items(), key=lambda x: KEY_CATEGORIES.get(x[0], "Z")):
        additions.append(f"# Quelle: {src}")
        additions.append(f"{key}={val}")
    additions.append("")

    MEGA_ENV.write_text(existing_text + "\n".join(additions))
    return len(new_entries)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 55)
    print("  SuperMegaBot — Credential Scanner")
    print("═" * 55 + "\n")

    print("🔍 Scanne alle .env Dateien...\n")
    found, scanned = scan_all()

    print(f"  Gescannte Dateien: {len(scanned)}")
    for f in scanned:
        print(f"    ✓ {f}")

    print(f"\n🔑 Gefundene API-Keys: {len(found)}\n")

    # Gruppiere nach Kategorie
    by_cat: dict[str, list] = {}
    for key, (val, src) in found.items():
        cat = KEY_CATEGORIES.get(key, "Sonstiges")
        if cat not in by_cat:
            by_cat[cat] = []
        # Maskiere den Wert
        masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "***"
        by_cat[cat].append(f"  {key} = {masked}  (aus: {src.name})")

    for cat, entries in sorted(by_cat.items()):
        print(f"  📂 {cat}")
        for e in entries:
            print(e)
        print()

    # Was fehlt noch?
    missing = {k: v for k, v in KEY_CATEGORIES.items() if k not in found}
    if missing:
        by_cat_missing: dict[str, list] = {}
        for key, cat in missing.items():
            by_cat_missing.setdefault(cat, []).append(key)
        print("❌ Noch nicht gefunden:")
        for cat, keys in sorted(by_cat_missing.items()):
            print(f"  {cat}: {', '.join(keys)}")
        print()

    # Update .env
    print(f"📝 Aktualisiere {MEGA_ENV}...")
    added = update_mega_env(found)
    if added:
        print(f"  ✅ {added} neue Keys zu .env hinzugefügt")
    else:
        print(f"  ✓ Alle Keys bereits vorhanden")

    print("\n" + "═" * 55)
    print("  Nächster Schritt:")
    print("  python3 ~/supermegabot/scripts/test_all_apis.py")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    main()
