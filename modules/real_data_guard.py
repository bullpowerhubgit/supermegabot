#!/usr/bin/env python3
"""
Real Data Guard — kein Demo-Fallback, nur echte API-Daten.
Gibt immer klare Fehlermeldungen wenn APIs nicht konfiguriert sind.
"""
import os
import logging
from typing import Dict, List, Tuple

log = logging.getLogger("RealDataGuard")


def check_shopify() -> Tuple[bool, str]:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip()
    token = (os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")).strip()
    if not domain:
        return False, "SHOPIFY_SHOP_DOMAIN fehlt in .env"
    if not token or token.startswith("shpat_DEIN"):
        return False, "SHOPIFY_ADMIN_API_TOKEN fehlt — gehe zu Shopify Admin → Apps → Develop apps → Admin API access token kopieren"
    return True, f"Shopify: {domain}"


def check_claude() -> Tuple[bool, str]:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key or key.startswith("sk-ant-DEIN"):
        return False, "ANTHROPIC_API_KEY fehlt"
    return True, "Claude API: OK"


def check_stripe() -> Tuple[bool, str]:
    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not key or "DEIN" in key:
        return False, "STRIPE_SECRET_KEY fehlt"
    return True, f"Stripe: {'LIVE' if key.startswith('sk_live') else 'TEST'}"


def check_supabase() -> Tuple[bool, str]:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or "DEIN" in url:
        return False, "SUPABASE_URL fehlt"
    return True, f"Supabase: {url[:40]}"


def check_telegram() -> Tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or "DEIN" in token:
        return False, "TELEGRAM_BOT_TOKEN fehlt"
    return True, "Telegram: OK"


def get_system_health() -> Dict:
    checks = {
        "shopify":  check_shopify(),
        "claude":   check_claude(),
        "stripe":   check_stripe(),
        "supabase": check_supabase(),
        "telegram": check_telegram(),
    }
    services = {
        name: {"ok": ok, "message": msg}
        for name, (ok, msg) in checks.items()
    }
    critical_ok = checks["shopify"][0] and checks["claude"][0]
    score = sum(1 for ok, _ in checks.values() if ok)
    return {
        "services": services,
        "score": score,
        "max_score": len(checks),
        "critical_ok": critical_ok,
        "ready": critical_ok,
        "missing": [msg for ok, msg in checks.values() if not ok],
    }


def require_shopify():
    """Wirft Exception wenn Shopify nicht konfiguriert ist."""
    ok, msg = check_shopify()
    if not ok:
        raise RuntimeError(f"Shopify nicht konfiguriert: {msg}")


def require_claude():
    ok, msg = check_claude()
    if not ok:
        raise RuntimeError(f"Claude nicht konfiguriert: {msg}")
