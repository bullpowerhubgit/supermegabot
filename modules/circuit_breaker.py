#!/usr/bin/env python3
"""
Circuit Breaker + Self-Healing Pipeline
========================================
Schützt alle API-Calls vor Cascading Failures.
Bei Fehler → automatischer Cooldown → Retry → Telegram-Alert.

Usage:
    from modules.circuit_breaker import breaker, is_open

    async def post_linkedin(text):
        if is_open("linkedin"):
            return {"skipped": True, "reason": "circuit_open"}
        try:
            result = await _do_post(text)
            breaker.success("linkedin")
            return result
        except Exception as e:
            breaker.failure("linkedin", str(e))
            raise
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Any

log = logging.getLogger("CircuitBreaker")

# ── Config per service ────────────────────────────────────────────────────────
_CONFIGS: dict[str, dict] = {
    "linkedin":   {"threshold": 3, "cooldown": 3600, "half_open_after": 900},
    "facebook":   {"threshold": 3, "cooldown": 1800, "half_open_after": 600},
    "instagram":  {"threshold": 3, "cooldown": 1800, "half_open_after": 600},
    "twitter":    {"threshold": 3, "cooldown": 3600, "half_open_after": 900},
    "openai":     {"threshold": 5, "cooldown": 300,  "half_open_after": 60},
    "anthropic":  {"threshold": 5, "cooldown": 300,  "half_open_after": 60},
    "shopify":    {"threshold": 5, "cooldown": 120,  "half_open_after": 30},
    "supabase":   {"threshold": 5, "cooldown": 120,  "half_open_after": 30},
    "telegram":   {"threshold": 5, "cooldown": 60,   "half_open_after": 15},
    "digistore":  {"threshold": 3, "cooldown": 300,  "half_open_after": 60},
    "klaviyo":    {"threshold": 5, "cooldown": 180,  "half_open_after": 60},
    "mailchimp":  {"threshold": 5, "cooldown": 180,  "half_open_after": 60},
    "default":    {"threshold": 5, "cooldown": 300,  "half_open_after": 60},
}

_STATE: dict[str, dict] = defaultdict(lambda: {
    "failures": 0,
    "state": "closed",   # closed | open | half_open
    "opened_at": 0.0,
    "last_error": "",
    "total_calls": 0,
    "total_failures": 0,
})


def _cfg(service: str) -> dict:
    return _CONFIGS.get(service, _CONFIGS["default"])


def is_open(service: str) -> bool:
    """Returns True if circuit is OPEN (calls should be skipped)."""
    s = _STATE[service]
    if s["state"] == "closed":
        return False
    if s["state"] == "open":
        cfg = _cfg(service)
        elapsed = time.time() - s["opened_at"]
        if elapsed >= cfg["half_open_after"]:
            s["state"] = "half_open"
            log.info("Circuit %s → half_open after %.0fs", service, elapsed)
            return False
        return True
    return False  # half_open → allow one through


def success(service: str) -> None:
    """Call after a successful API call — resets the circuit."""
    s = _STATE[service]
    s["total_calls"] += 1
    if s["state"] != "closed":
        log.info("Circuit %s → closed (recovered)", service)
    s["failures"] = 0
    s["state"] = "closed"


def failure(service: str, error: str = "", http_status: int = 0) -> None:
    """Call after a failed API call — may open the circuit."""
    s = _STATE[service]
    s["total_calls"] += 1
    s["total_failures"] += 1
    s["last_error"] = error[:120]

    # 429 / rate-limit: open immediately with long cooldown
    if http_status == 429 or "rate" in error.lower() or "429" in error:
        s["state"] = "open"
        s["opened_at"] = time.time()
        s["failures"] = _cfg(service)["threshold"]
        log.warning("Circuit %s → open (rate_limit)", service)
        _telegram_alert(service, "rate_limit_429", error)
        return

    # permission / auth errors: open immediately, no point retrying
    if http_status in (401, 403) or any(x in error.lower() for x in ("permission", "unauthorized", "forbidden")):
        s["state"] = "open"
        s["opened_at"] = time.time()
        s["failures"] = _cfg(service)["threshold"]
        log.warning("Circuit %s → open (auth/permission)", service)
        _telegram_alert(service, "auth_error", error)
        return

    s["failures"] += 1
    threshold = _cfg(service)["threshold"]
    if s["failures"] >= threshold and s["state"] == "closed":
        s["state"] = "open"
        s["opened_at"] = time.time()
        log.warning("Circuit %s → open after %d failures", service, s["failures"])
        _telegram_alert(service, "threshold_reached", error)


def _telegram_alert(service: str, reason: str, error: str) -> None:
    try:
        from modules.notify_hub import send_telegram
        msg = (f"🔴 <b>Circuit Breaker: {service.upper()}</b>\n"
               f"Grund: {reason}\n"
               f"Fehler: {error[:100]}\n"
               f"Status: OPEN — Calls werden für {_cfg(service)['cooldown']}s pausiert")
        send_telegram(msg)
    except Exception:
        pass


def get_status() -> dict:
    """Returns circuit status for all services — for /api/health endpoint."""
    result = {}
    for name, s in _STATE.items():
        cfg = _cfg(name)
        cooldown_left = 0
        if s["state"] == "open":
            elapsed = time.time() - s["opened_at"]
            cooldown_left = max(0, cfg["cooldown"] - elapsed)
        result[name] = {
            "state": s["state"],
            "failures": s["failures"],
            "cooldown_left_s": int(cooldown_left),
            "total_calls": s["total_calls"],
            "total_failures": s["total_failures"],
            "last_error": s["last_error"],
        }
    return result


def reset(service: str) -> None:
    """Manually reset a circuit to closed."""
    _STATE[service]["state"] = "closed"
    _STATE[service]["failures"] = 0
    log.info("Circuit %s manually reset → closed", service)


# ── Decorator for automatic circuit breaking ──────────────────────────────────

def protected(service: str):
    """
    Async decorator — wraps a coroutine with circuit breaker logic.

    @protected("linkedin")
    async def post_linkedin(text: str) -> dict: ...
    """
    def decorator(fn: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            if is_open(service):
                s = _STATE[service]
                remain = int(max(0, _cfg(service)["cooldown"] - (time.time() - s["opened_at"])))
                log.debug("Circuit %s OPEN — skip (%ds left)", service, remain)
                return {"skipped": True, "reason": f"circuit_open:{service}", "cooldown_s": remain}
            try:
                result = await fn(*args, **kwargs)
                # Auto-detect failure from result dict
                if isinstance(result, dict):
                    err = result.get("error", "")
                    status = result.get("status", 0)
                    if err or (isinstance(status, int) and status >= 400):
                        failure(service, str(err), int(status) if status else 0)
                    else:
                        success(service)
                else:
                    success(service)
                return result
            except Exception as exc:
                failure(service, str(exc))
                raise
        wrapper.__name__ = fn.__name__
        wrapper.__doc__  = fn.__doc__
        return wrapper
    return decorator


# Singleton export
breaker_success  = success
breaker_failure  = failure
breaker_is_open  = is_open
breaker_reset    = reset
breaker_status   = get_status
