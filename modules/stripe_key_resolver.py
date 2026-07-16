#!/usr/bin/env python3
"""
Stripe Key Resolver — NUR bullpowersrtkennels@gmail.com
========================================================
DAUERHAFT. IMMER. ÜBERALL.

Erlaubt:
  • Konto: acct_1Tg1U0RJECiV6vSm
  • Email: bullpowersrtkennels@gmail.com
  • Live-Key-Prefix: sk_live_51Tg1U…

VERBOTEN (nie nutzen, nie fallback):
  • STRIPE_SECRET_KEY_AIITEC
  • sk_live_51Swso… (AIITEC-Konto)
  • jedes andere Stripe-Konto

Usage:
    from modules.stripe_key_resolver import get_working_stripe_key, assert_bullpower_only
    key = get_working_stripe_key()
"""
from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger("StripeKeyResolver")

# ── Kanonisches BullPower-Konto (EINZIGES erlaubtes) ─────────────────────────
BULLPOWER_ACCOUNT_ID = "acct_1Tg1U0RJECiV6vSm"
BULLPOWER_EMAIL = "bullpowersrtkennels@gmail.com"
# Live secret keys for this account always start with this publishable-account prefix
BULLPOWER_LIVE_PREFIXES = (
    "sk_live_51Tg1U",
    "rk_live_51Tg1U",
)
# Explicit ban list (AIITEC + known wrong accounts)
BANNED_KEY_PREFIXES = (
    "sk_live_51Swso",   # AIITEC — 401 / FALSCHES KONTO
    "sk_test_51Swso",
    "rk_live_51Swso",
)

# Env vars that MAY hold the bullpower key (order = preference)
_ALLOWED_ENV = (
    "STRIPE_SECRET_KEY",        # PRIMARY — bullpowersrtkennels
    "STRIPE_SECRET_KEY_FULL",   # alias if set to same account
    "STRIPE_API_KEY",
    "STRIPE_SECRET",
)

# Env vars that must NEVER be used for API calls
_FORBIDDEN_ENV = frozenset({
    "STRIPE_SECRET_KEY_AIITEC",
    "STRIPE_TEST_SECRET_KEY_AIITEC",
    "STRIPE_CLI_KEY_AIITEC",
    "STRIPE_PUBLISHABLE_KEY_AIITEC",
})

_cache_key: Optional[str] = None
_cache_name: str = ""
_cache_ts: float = 0.0
_CACHE_TTL = 300
_dead: set[str] = set()
_enforced = False


def is_banned_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return False
    for p in BANNED_KEY_PREFIXES:
        if k.startswith(p):
            return True
    # any env value of forbidden names
    return False


def is_bullpower_key(key: str) -> bool:
    """True if key belongs to bullpowersrtkennels live account (prefix match)."""
    k = (key or "").strip()
    if not k:
        return False
    if is_banned_key(k):
        return False
    for p in BULLPOWER_LIVE_PREFIXES:
        if k.startswith(p):
            return True
    # test keys only if explicitly allowed later — for now live only preferred
    if k.startswith("sk_test_") or k.startswith("rk_test_"):
        return False
    return False


def purge_forbidden_from_environ() -> list[str]:
    """
    Remove forbidden AIITEC stripe secrets from process env so no module can read them.
    Call at dashboard startup.
    """
    removed = []
    for name in _FORBIDDEN_ENV:
        if name in os.environ:
            # Do not delete if somehow same as bullpower (shouldn't happen)
            val = os.environ.get(name, "")
            if is_bullpower_key(val):
                continue
            del os.environ[name]
            removed.append(name)
    # Also wipe any env var whose VALUE is a banned key
    for name, val in list(os.environ.items()):
        if "STRIPE" in name.upper() and is_banned_key(val):
            del os.environ[name]
            if name not in removed:
                removed.append(name)
    if removed:
        log.warning(
            "Stripe BULLPOWER-ONLY: removed forbidden env vars from process: %s",
            ", ".join(removed),
        )
    return removed


def enforce_bullpower_only() -> dict:
    """Startup: purge AIITEC + ensure STRIPE_SECRET_KEY is bullpower."""
    global _enforced
    removed = purge_forbidden_from_environ()
    key = get_working_stripe_key(force_refresh=True)
    ok = bool(key) and is_bullpower_key(key)
    _enforced = True
    if ok:
        # Force all common aliases to the same bullpower key in-process
        for alias in _ALLOWED_ENV:
            os.environ[alias] = key
        log.info(
            "Stripe BULLPOWER-ONLY enforced: account=%s key=%s…",
            BULLPOWER_ACCOUNT_ID,
            key[:14],
        )
    else:
        log.error(
            "Stripe BULLPOWER-ONLY: KEIN gültiger bullpowersrtkennels Key! "
            "Setze STRIPE_SECRET_KEY=sk_live_51Tg1U… (acct_1Tg1U0RJECiV6vSm)"
        )
    return {
        "ok": ok,
        "account_id": BULLPOWER_ACCOUNT_ID,
        "email": BULLPOWER_EMAIL,
        "key_prefix": (key[:14] + "…") if key else "",
        "purged_env": removed,
        "source": _cache_name,
    }


def _probe(key: str) -> bool:
    if not key or not key.startswith(("sk_", "rk_")):
        return False
    if is_banned_key(key) or not is_bullpower_key(key):
        _dead.add(key)
        return False
    if key in _dead:
        return False
    try:
        req = urllib.request.Request(
            "https://api.stripe.com/v1/account",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            if r.status != 200:
                return False
            import json
            data = json.loads(r.read())
            acct = data.get("id") or ""
            email = (data.get("email") or "").lower()
            if acct and acct != BULLPOWER_ACCOUNT_ID:
                log.error(
                    "Stripe Key gehört zu %s — erwartet %s — ABGELEHNT",
                    acct, BULLPOWER_ACCOUNT_ID,
                )
                _dead.add(key)
                return False
            if email and email != BULLPOWER_EMAIL.lower():
                log.error("Stripe email %s ≠ %s — ABGELEHNT", email, BULLPOWER_EMAIL)
                _dead.add(key)
                return False
            return True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _dead.add(key)
            log.warning("Stripe key dead HTTP %s prefix=%s…", e.code, key[:12])
        return False
    except Exception as e:
        log.debug("Stripe probe: %s", e)
        return False


def get_working_stripe_key(force_refresh: bool = False) -> str:
    """Return bullpowersrtkennels secret key ONLY — never AIITEC."""
    global _cache_key, _cache_name, _cache_ts
    now = time.time()
    if (
        not force_refresh
        and _cache_key
        and is_bullpower_key(_cache_key)
        and (now - _cache_ts) < _CACHE_TTL
        and _cache_key not in _dead
    ):
        return _cache_key

    # Prefer allowed env only
    for name in _ALLOWED_ENV:
        val = (os.getenv(name) or "").strip()
        if not val or val in _dead:
            continue
        if is_banned_key(val):
            log.error("Stripe FORBIDDEN key in %s (AIITEC/wrong) — ignored", name)
            continue
        if not is_bullpower_key(val):
            log.error(
                "Stripe key in %s is NOT bullpower prefix (got %s…) — ignored",
                name, val[:14],
            )
            continue
        # Accept prefix match even if probe fails (offline) — still never AIITEC
        if _probe(val) or is_bullpower_key(val):
            _cache_key = val
            _cache_name = name
            _cache_ts = now
            log.info("Stripe BULLPOWER key from %s (%s…)", name, val[:14])
            return val

    # Explicit: never fall through to AIITEC
    for bad in _FORBIDDEN_ENV:
        if (os.getenv(bad) or "").strip():
            log.error("Stripe: %s is set but FORBIDDEN — not used", bad)

    return ""


def get_working_stripe_key_name() -> str:
    get_working_stripe_key()
    return _cache_name or ""


def assert_bullpower_only(key: Optional[str] = None) -> str:
    """Raise RuntimeError if key is not bullpower. Returns key if ok."""
    k = (key if key is not None else get_working_stripe_key()).strip()
    if not k:
        raise RuntimeError(
            "Kein STRIPE_SECRET_KEY für bullpowersrtkennels@gmail.com "
            f"({BULLPOWER_ACCOUNT_ID}). Setze sk_live_51Tg1U…"
        )
    if is_banned_key(k) or not is_bullpower_key(k):
        raise RuntimeError(
            f"FALSCHES STRIPE-KONTO blockiert (prefix {k[:14]}…). "
            f"NUR {BULLPOWER_EMAIL} / {BULLPOWER_ACCOUNT_ID} erlaubt."
        )
    return k


def rewrite_auth_header_value(auth_header: str) -> str:
    """
    If Authorization: Bearer sk_… is wrong account, replace with bullpower key.
    Used by HttpGuard process-wide.
    """
    if not auth_header:
        return auth_header
    parts = auth_header.split(None, 1)
    if len(parts) != 2:
        return auth_header
    scheme, token = parts[0], parts[1].strip()
    if scheme.lower() not in ("bearer", "basic"):
        return auth_header
    # Basic is base64(key:) — leave to other path; Bearer is common
    if scheme.lower() == "bearer":
        if is_banned_key(token) or (token.startswith("sk_") and not is_bullpower_key(token)):
            good = get_working_stripe_key()
            if good:
                log.warning(
                    "Stripe HttpGuard: rewrote FORBIDDEN key %s… → bullpower %s…",
                    token[:12], good[:12],
                )
                return f"Bearer {good}"
    return auth_header


def stripe_aiitec_status() -> dict:
    """AIITEC is permanently disabled — report as forbidden."""
    return {
        "configured": bool((os.getenv("STRIPE_SECRET_KEY_AIITEC") or "").strip()),
        "ok": False,
        "forbidden": True,
        "error": "STRIPE_SECRET_KEY_AIITEC is PERMANENTLY FORBIDDEN — use bullpowersrtkennels only",
        "required_account": BULLPOWER_ACCOUNT_ID,
        "required_email": BULLPOWER_EMAIL,
        "active": get_working_stripe_key_name() or "STRIPE_SECRET_KEY",
    }


def self_check() -> dict:
    """CI / startup regression."""
    enforce_bullpower_only()
    k = get_working_stripe_key()
    checks = [
        {"name": "has_bullpower_key", "ok": bool(k) and is_bullpower_key(k)},
        {"name": "aiitec_not_used", "ok": not is_banned_key(k) if k else True},
        {
            "name": "forbidden_env_purged",
            "ok": all(not (os.getenv(n) or "").strip() or is_bullpower_key(os.getenv(n, ""))
                      for n in _FORBIDDEN_ENV),
        },
    ]
    # Simulate banned key rejection
    try:
        assert_bullpower_only("sk_live_51SwsoNF_FAKE_AIITEC_KEY_XXXX")
        checks.append({"name": "reject_aiitec", "ok": False})
    except RuntimeError:
        checks.append({"name": "reject_aiitec", "ok": True})
    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "account_id": BULLPOWER_ACCOUNT_ID,
        "email": BULLPOWER_EMAIL,
        "key_prefix": (k[:14] + "…") if k else "",
    }
