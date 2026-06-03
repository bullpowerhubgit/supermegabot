#!/usr/bin/env python3
"""
.env Cleaner — bereinigt, dedupliziert und merged .env Dateien
Usage: python3 scripts/clean_env.py
"""
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

HOME = Path.home()

# Quell-Dateien (werden alle eingelesen und gemergt)
SOURCES = [
    HOME / "supermegabot" / ".env",
    HOME / "CascadeProjects" / "rudibot" / ".env",
]

# Ziel
TARGET = HOME / "supermegabot" / ".env"

# Korrekte Werte (überschreiben alles andere)
CORRECT_VALUES = {
    "SHOPIFY_SHOP_DOMAIN": "iwiini-td2xdoae.myshopify.com",
    "SHOPIFY_STORE_URL":   "https://iwiini-td2xdoae.myshopify.com",
    "SHOPIFY_SHOP":        "iwiini-td2xdoae.myshopify.com",
}

# Zeilen die definitiv raus müssen (kaputte Muster)
BAD_PATTERNS = [
    r"^TELEGRAM_API_ID@",       # kaputte Telegram-Zeile
    r"^=\d{10}:",               # Token-Fragment nach kaputter Zeile
    r"^Token for the bot",      # BotFather-Text
    r"^\d{10}:AA[A-Za-z0-9_-]+$",  # nackter Token ohne Key
    r"^rudolfsarkany@",         # Terminal-Prompt
    r"^\[PM2\]",                # PM2-Output
    r"^zsh:",                   # Shell-Fehler
]

# Kategorien für übersichtliche Ausgabe
CATEGORIES = {
    "Dashboard":   ["DASHBOARD_PORT"],
    "Telegram":    ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"],
    "Shopify":     ["SHOPIFY_"],
    "Stripe":      ["STRIPE_"],
    "Google":      ["GOOGLE_", "GCP_"],
    "Supabase":    ["SUPABASE_"],
    "AI":          ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY", "OLLAMA_"],
    "Mailchimp":   ["MAILCHIMP_"],
    "Klaviyo":     ["KLAVIYO_"],
    "Printify":    ["PRINTIFY_"],
    "Digistore24": ["DIGISTORE24_"],
    "Social":      ["META_", "YOUTUBE_", "FACEBOOK_", "TWITTER_", "TIKTOK_", "PINTEREST_", "REDDIT_", "DISCORD_"],
    "Guardian":    ["GUARDIAN_", "ETERNAL_"],
    "GitHub":      ["GITHUB_"],
    "Railway":     ["RAILWAY_"],
    "Paths":       ["_DIR", "SUPERMEGABOT_", "WS_", "API_GATEWAY_", "SHOPIFY_AI_", "SHOPIFY_SUITE_"],
    "Watchdog":    ["WATCHDOG_"],
    "Other":       [],
}


def is_bad_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    for pattern in BAD_PATTERNS:
        if re.match(pattern, stripped):
            return True
    return False


def parse_env(path: Path) -> dict:
    """Lese .env und gib dict zurück."""
    result = {}
    if not path.exists():
        print(f"  ⏭  Nicht gefunden: {path}")
        return result
    print(f"  📂 Lese: {path}")
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if is_bad_line(line):
            print(f"     ❌ Entfernt: {stripped[:60]}")
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip()
            # Quotes entfernen
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            if key and val:
                result[key] = val
    return result


def get_category(key: str) -> str:
    for cat, prefixes in CATEGORIES.items():
        if cat == "Other":
            continue
        for prefix in prefixes:
            if key.startswith(prefix) or key == prefix.rstrip("_"):
                return cat
    return "Other"


def format_env(merged: dict) -> str:
    lines = [
        "# SuperMegaBot — Environment Variables",
        f"# Bereinigt: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "# NICHT in Git committen!",
        "",
    ]

    categorized = {cat: {} for cat in CATEGORIES}
    for key, val in sorted(merged.items()):
        cat = get_category(key)
        categorized[cat][key] = val

    for cat, keys in categorized.items():
        if not keys:
            continue
        lines.append(f"# ── {cat} {'─' * (50 - len(cat))}")
        for key, val in sorted(keys.items()):
            lines.append(f"{key}={val}")
        lines.append("")

    return "\n".join(lines)


def main():
    print("━" * 60)
    print("  SuperMegaBot .env Cleaner")
    print("━" * 60)

    # Backup
    if TARGET.exists():
        backup = TARGET.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy(TARGET, backup)
        print(f"\n✅ Backup: {backup.name}")

    # Alle Quellen einlesen und mergen
    print("\n📥 Lese Quellen:")
    merged = {}
    for source in SOURCES:
        data = parse_env(source)
        # Erste Quelle gewinnt (supermegabot .env hat Priorität)
        for key, val in data.items():
            if key not in merged:
                merged[key] = val
            else:
                if merged[key] != val:
                    print(f"     ℹ️  Duplikat {key}: behalte '{merged[key][:20]}...' (ignoriere '{val[:20]}...')")

    # Korrekte Werte erzwingen
    print("\n✏️  Setze korrekte Werte:")
    for key, val in CORRECT_VALUES.items():
        old = merged.get(key, "(nicht vorhanden)")
        merged[key] = val
        if old != val:
            print(f"  {key}: '{old[:30]}' → '{val}'")
        else:
            print(f"  {key}: ✅ bereits korrekt")

    # Schreiben
    output = format_env(merged)
    TARGET.write_text(output)

    print(f"\n✅ Gespeichert: {TARGET}")
    print(f"   {len(merged)} Variablen, sauber kategorisiert")

    # Zusammenfassung
    print("\n━" * 60)
    print("  ZUSAMMENFASSUNG")
    print("━" * 60)
    important = ["SHOPIFY_SHOP_DOMAIN", "SHOPIFY_ACCESS_TOKEN",
                 "TELEGRAM_BOT_TOKEN", "SUPABASE_URL", "SUPABASE_ANON_KEY",
                 "STRIPE_SECRET_KEY", "ANTHROPIC_API_KEY"]
    for key in important:
        val = merged.get(key, "")
        if val:
            masked = val[:6] + "***"
            print(f"  ✅ {key:<30} {masked}")
        else:
            print(f"  ❌ {key:<30} (fehlt!)")

    print("\n  Nächste Schritte:")
    missing = [k for k in important if not merged.get(k)]
    for key in missing:
        print(f"  → {key} eintragen")

    if not missing:
        print("  → python3 test_live_connections.py")


if __name__ == "__main__":
    main()
