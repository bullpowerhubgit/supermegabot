#!/usr/bin/env python3
"""
BullPower ENV Sync + Validator
================================
Prüft alle API-Keys, sync zu Railway, validiert Verbindungen.
Usage: python3 modules/env_sync.py [--validate] [--sync-railway] [--report]
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("EnvSync")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# .env laden
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

BASE = Path(__file__).parent.parent


def _http_get(url: str, headers: Optional[Dict] = None, timeout: int = 8) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)[:100]


def _test_nonempty(key: str) -> Tuple[bool, str]:
    v = os.getenv(key, "")
    if not v or v in ("undefined", "null", "none", "your_key_here"):
        return False, "Leer oder Platzhalter"
    return True, f"{v[:8]}..."


def _test_telegram(key: str) -> Tuple[bool, str]:
    token = os.getenv(key, "")
    if not token:
        return False, "Token fehlt"
    status, body = _http_get(f"https://api.telegram.org/bot{token}/getMe")
    if status == 200 and '"ok":true' in body:
        try:
            data = json.loads(body)
            return True, f"@{data['result']['username']}"
        except Exception:
            return True, "OK"
    return False, f"HTTP {status}"


def _test_shopify(key: str) -> Tuple[bool, str]:
    token = os.getenv(key, "")
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not token or not domain:
        return False, "Token oder Domain fehlt"
    status, body = _http_get(
        f"https://{domain}/admin/api/{version}/shop.json",
        {"X-Shopify-Access-Token": token}
    )
    if status == 200:
        try:
            name = json.loads(body)["shop"]["name"]
            return True, name
        except Exception:
            return True, "OK"
    if status == 429:
        return True, "Rate-limited (aber Key OK)"
    return False, f"HTTP {status}"


def _test_stripe(key: str) -> Tuple[bool, str]:
    secret = os.getenv(key, "")
    if not secret:
        return False, "Key fehlt"
    token = base64.b64encode(f"{secret}:".encode()).decode()
    status, body = _http_get(
        "https://api.stripe.com/v1/balance",
        {"Authorization": f"Basic {token}"}
    )
    if status == 200:
        try:
            data = json.loads(body)
            eur = next((a["amount"] / 100 for a in data.get("available", []) if a.get("currency") == "eur"), 0)
            mode = "LIVE" if secret.startswith("sk_live_") else "TEST"
            return True, f"{mode} Balance: €{eur:.2f}"
        except Exception:
            return True, "OK"
    return False, f"HTTP {status}"


def _test_supabase(key: str) -> Tuple[bool, str]:
    url = os.getenv(key, "")
    svc_key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
    if not url or not svc_key:
        return False, "URL oder Key fehlt"
    status, body = _http_get(
        f"{url}/rest/v1/agent_memory?limit=1",
        {"apikey": svc_key, "Authorization": f"Bearer {svc_key}"}
    )
    if status == 200:
        return True, "REST OK"
    return False, f"HTTP {status}: {body[:60]}"


def _test_klaviyo(key: str) -> Tuple[bool, str]:
    api_key = os.getenv(key, "")
    if not api_key:
        return False, "Key fehlt"
    status, body = _http_get(
        "https://a.klaviyo.com/api/lists/",
        {"Authorization": f"Klaviyo-API-Key {api_key}", "revision": "2024-02-15"}
    )
    if status == 200:
        try:
            n = len(json.loads(body).get("data", []))
            return True, f"{n} Listen"
        except Exception:
            return True, "OK"
    return False, f"HTTP {status}"


def _test_anthropic(key: str) -> Tuple[bool, str]:
    api_key = os.getenv(key, "")
    if not api_key:
        return False, "Key fehlt"
    if api_key.startswith("sk-ant-"):
        return True, f"{api_key[:12]}... (Format OK, kein Verbrauchs-Test)"
    return False, "Unbekanntes Format"


def _test_openai(key: str) -> Tuple[bool, str]:
    api_key = os.getenv(key, "")
    if not api_key:
        return False, "Key fehlt"
    if api_key.startswith("sk-"):
        return True, f"{api_key[:8]}... (Format OK)"
    return False, "Unbekanntes Format"


def _test_github(key: str) -> Tuple[bool, str]:
    token = os.getenv(key, "")
    if not token:
        return False, "Token fehlt"
    status, body = _http_get(
        "https://api.github.com/user",
        {"Authorization": f"token {token}", "User-Agent": "SuperMegaBot"}
    )
    if status == 200:
        try:
            return True, json.loads(body).get("login", "OK")
        except Exception:
            return True, "OK"
    return False, f"HTTP {status}"


# ── Alle benötigten Env-Vars mit Validierungs-Regeln ─────────────────────────

REQUIRED_VARS: List[Dict] = [
    # ── Telegram ──
    {"key": "TELEGRAM_BOT_TOKEN",         "test": _test_telegram,  "group": "Telegram", "critical": True},
    {"key": "TELEGRAM_CHAT_ID",           "test": _test_nonempty,  "group": "Telegram", "critical": True},
    # ── Shopify ──
    {"key": "SHOPIFY_SHOP_DOMAIN",        "test": _test_nonempty,  "group": "Shopify",  "critical": True},
    {"key": "SHOPIFY_ADMIN_API_TOKEN",    "test": _test_shopify,   "group": "Shopify",  "critical": True},
    {"key": "SHOPIFY_API_VERSION",        "test": _test_nonempty,  "group": "Shopify",  "critical": False},
    # ── Stripe ──
    {"key": "STRIPE_SECRET_KEY",          "test": _test_stripe,    "group": "Stripe",   "critical": True},
    {"key": "STRIPE_WEBHOOK_SECRET",      "test": _test_nonempty,  "group": "Stripe",   "critical": False},
    {"key": "STRIPE_PRICE_STARTER",       "test": _test_nonempty,  "group": "Stripe",   "critical": False},
    {"key": "STRIPE_PRICE_PRO",           "test": _test_nonempty,  "group": "Stripe",   "critical": False},
    # ── Supabase ──
    {"key": "SUPABASE_URL",               "test": _test_supabase,  "group": "Supabase", "critical": True},
    {"key": "SUPABASE_SERVICE_KEY",       "test": _test_nonempty,  "group": "Supabase", "critical": True},
    {"key": "SUPABASE_ANON_KEY",          "test": _test_nonempty,  "group": "Supabase", "critical": False},
    # ── Klaviyo ──
    {"key": "KLAVIYO_API_KEY",            "test": _test_klaviyo,   "group": "Klaviyo",  "critical": False},
    # ── SMTP ──
    {"key": "GMAIL_USER_5",               "test": _test_nonempty,  "group": "SMTP",     "critical": False},
    {"key": "GMAIL_APP_PASSWORD_5",       "test": _test_nonempty,  "group": "SMTP",     "critical": False},
    {"key": "GMAIL_USER",                 "test": _test_nonempty,  "group": "SMTP",     "critical": False},
    {"key": "GMAIL_APP_PASSWORD",         "test": _test_nonempty,  "group": "SMTP",     "critical": False},
    # ── Anthropic / OpenAI ──
    {"key": "ANTHROPIC_API_KEY",          "test": _test_anthropic, "group": "AI",       "critical": False},
    {"key": "OPENAI_API_KEY",             "test": _test_openai,    "group": "AI",       "critical": False},
    # ── Meta ──
    {"key": "FACEBOOK_PAGE_TOKEN_AIITEC", "test": _test_nonempty,  "group": "Meta",     "critical": False},
    {"key": "FACEBOOK_PAGE_ID",           "test": _test_nonempty,  "group": "Meta",     "critical": False},
    # ── GitHub ──
    {"key": "GITHUB_TOKEN",               "test": _test_github,    "group": "GitHub",   "critical": False},
    # ── DS24 ──
    {"key": "DS24_API_KEY",               "test": _test_nonempty,  "group": "DS24",     "critical": False},
]


# ── Validator ─────────────────────────────────────────────────────────────────

def validate_all() -> Dict:
    results = {"ok": [], "fail": [], "groups": {}}
    for spec in REQUIRED_VARS:
        key = spec["key"]
        group = spec["group"]
        critical = spec["critical"]
        test_fn = spec["test"]

        try:
            ok, detail = test_fn(key)
        except Exception as e:
            ok, detail = False, f"Exception: {e}"

        entry = {
            "key": key,
            "ok": ok,
            "detail": detail,
            "critical": critical,
        }

        if ok:
            results["ok"].append(entry)
        else:
            results["fail"].append(entry)

        if group not in results["groups"]:
            results["groups"][group] = []
        results["groups"][group].append(entry)

    return results


def print_report(results: Dict) -> None:
    print()
    print("=" * 60)
    print("  BullPower ENV Validator Report")
    print("=" * 60)

    for group, entries in results["groups"].items():
        ok_count = sum(1 for e in entries if e["ok"])
        print(f"\n  📦 {group}  ({ok_count}/{len(entries)} OK)")
        for e in entries:
            icon = "✅" if e["ok"] else ("🚨" if e["critical"] else "⚠️")
            print(f"     {icon} {e['key']:<35} {e['detail']}")

    total = len(results["ok"]) + len(results["fail"])
    ok = len(results["ok"])
    fail_critical = sum(1 for e in results["fail"] if e["critical"])

    print()
    print("=" * 60)
    print(f"  Gesamt: {ok}/{total} OK | {len(results['fail'])} fehlen | {fail_critical} kritisch")
    if fail_critical == 0:
        print("  ✅ Alle kritischen Keys vorhanden — System kann starten!")
    else:
        print(f"  🚨 {fail_critical} kritische Keys fehlen — System läuft eingeschränkt!")
    print("=" * 60)
    print()


# ── Railway Sync ──────────────────────────────────────────────────────────────

RAILWAY_REQUIRED_VARS = [
    # System
    "REVENUE_MODE",
    "SOCIAL_POSTING_PAUSED",
    "PAUSE_ALL_POSTING",
    "PORT",
    # Shopify
    "SHOPIFY_SHOP_DOMAIN",
    "SHOPIFY_ADMIN_API_TOKEN",
    "SHOPIFY_API_VERSION",
    "SHOPIFY_CUSTOM_DOMAIN",
    "SHOPIFY_SHOP_URL",
    # Stripe
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_STARTER",
    "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_ENTERPRISE",
    "STRIPE_TEST_WEBHOOK_SECRET",
    # Supabase
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    # Telegram
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    # AI
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    # Meta
    "FACEBOOK_PAGE_TOKEN_AIITEC",
    "FACEBOOK_PAGE_ID",
    "FACEBOOK_IG_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ID",
    # Email
    "KLAVIYO_API_KEY",
    "MAILCHIMP_API_KEY",
    "MAILCHIMP_LIST_ID",
    "GMAIL_USER_5",
    "GMAIL_APP_PASSWORD_5",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    # GitHub
    "GITHUB_TOKEN",
    "GITHUB_USER",
    # DS24
    "DS24_API_KEY",
    # Twitter
    "TWITTER_COOKIES_JSON",
    # LinkedIn
    "LINKEDIN_ACCESS_TOKEN",
    # TikTok
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "TIKTOK_ACCESS_TOKEN",
]

RAILWAY_DEFAULTS = {
    "REVENUE_MODE": "false",
    "SHOPIFY_API_VERSION": "2026-04",
}


def generate_railway_env_file() -> None:
    """Erstellt railway-env.txt mit allen aktuellen Werten für copy-paste ins Railway Dashboard."""
    output_file = BASE / "data" / "railway-env-export.txt"
    output_file.parent.mkdir(exist_ok=True)

    lines = [
        "# BullPower SuperMegaBot — Railway Environment Variables",
        "# Generiert: " + __import__("datetime").datetime.now().isoformat()[:19],
        "# Copy-Paste in: Railway Dashboard → Service → Variables",
        "",
    ]

    missing = []
    for key in RAILWAY_REQUIRED_VARS:
        val = os.getenv(key, RAILWAY_DEFAULTS.get(key, ""))
        if val:
            lines.append(f"{key}={val}")
        else:
            lines.append(f"# FEHLT: {key}=")
            missing.append(key)

    output_file.write_text("\n".join(lines))
    log.info(f"Railway-Env-Export: {output_file} ({len(RAILWAY_REQUIRED_VARS)-len(missing)}/{len(RAILWAY_REQUIRED_VARS)} Vars)")
    if missing:
        log.warning(f"Fehlende Railway-Vars: {', '.join(missing)}")


# ── Async validate ────────────────────────────────────────────────────────────

async def run_validation() -> int:
    """Returns exit code: 0 = alles OK, 1 = kritische Fehler."""
    results = await asyncio.get_event_loop().run_in_executor(None, validate_all)
    print_report(results)
    generate_railway_env_file()

    fail_critical = sum(1 for e in results["fail"] if e["critical"])
    return 0 if fail_critical == 0 else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BullPower ENV Validator")
    parser.add_argument("--validate", action="store_true", help="Alle Keys validieren")
    parser.add_argument("--railway-export", action="store_true", help="Railway-Env-Datei generieren")
    args = parser.parse_args()

    if args.railway_export:
        try:
            from dotenv import load_dotenv
            load_dotenv(BASE / ".env", override=True)
        except ImportError:
            pass
        generate_railway_env_file()
        print(f"✅ Railway-Env-Export: data/railway-env-export.txt")
    else:
        sys.exit(asyncio.run(run_validation()))
