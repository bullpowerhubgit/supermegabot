#!/usr/bin/env python3
"""
Stripe Key Resolver — DAUERHAFT
================================
STRIPE_SECRET_KEY_AIITEC liefert oft 401 (Konto inaktiv).
Dieser Resolver wählt den ERSTEN funktionierenden Live-Key und cached ihn.

Usage:
    from modules.stripe_key_resolver import get_working_stripe_key
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

_CANDIDATES = (
    "STRIPE_SECRET_KEY",           # Main bullpower — primär
    "STRIPE_SECRET_KEY_AIITEC",    # oft 401 → skip
    "STRIPE_API_KEY",
    "STRIPE_SECRET_KEY_FULL",
)

_cache_key: Optional[str] = None
_cache_name: str = ""
_cache_ts: float = 0.0
_CACHE_TTL = 300  # 5 min
_dead: set[str] = set()  # keys known 401/403 this process


def _probe(key: str) -> bool:
    if not key or not key.startswith("sk_"):
        return False
    if key in _dead:
        return False
    try:
        req = urllib.request.Request(
            "https://api.stripe.com/v1/balance",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            _dead.add(key)
            log.warning("Stripe key dead (HTTP %s) prefix=%s…", e.code, key[:12])
        return False
    except Exception as e:
        log.debug("Stripe probe error: %s", e)
        return False


def get_working_stripe_key(force_refresh: bool = False) -> str:
    """Return a live-working Stripe secret key or ''."""
    global _cache_key, _cache_name, _cache_ts
    now = time.time()
    if (
        not force_refresh
        and _cache_key
        and (now - _cache_ts) < _CACHE_TTL
        and _cache_key not in _dead
    ):
        return _cache_key

    for name in _CANDIDATES:
        val = (os.getenv(name) or "").strip()
        if not val or val in _dead:
            continue
        if _probe(val):
            _cache_key = val
            _cache_name = name
            _cache_ts = now
            log.info("StripeKeyResolver: using %s (prefix %s…)", name, val[:12])
            return val

    # last resort: first non-empty without probe
    for name in _CANDIDATES:
        val = (os.getenv(name) or "").strip()
        if val and val not in _dead:
            log.warning("StripeKeyResolver: unprobed fallback %s", name)
            return val
    return ""


def get_working_stripe_key_name() -> str:
    get_working_stripe_key()
    return _cache_name or ""


def stripe_aiitec_status() -> dict:
    """Explicit status for AIITEC key (for dashboards / health)."""
    key = (os.getenv("STRIPE_SECRET_KEY_AIITEC") or "").strip()
    if not key:
        return {"configured": False, "ok": False, "error": "not set"}
    ok = _probe(key)
    return {
        "configured": True,
        "ok": ok,
        "prefix": key[:12],
        "error": None if ok else "401/403 — use main STRIPE_SECRET_KEY via resolver",
        "fallback": get_working_stripe_key_name() or "STRIPE_SECRET_KEY",
    }
