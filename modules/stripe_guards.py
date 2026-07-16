#!/usr/bin/env python3
"""
stripe_guards.py — dauerhafte Stripe Live-Mode-Sicherheit

Verhindert die drei historischen Live-API-Fehlerklassen permanent:

  1. invalid_request_error / payment_method
     → Test-only Tokens (pm_card_visa, …) werden im Live-Modus blockiert
  2. url_invalid bei payment_links
     → Redirect-URLs und Produktnamen werden immer URL-encoded
  3. type=recurring in GET /prices
     → Query-Param `type` wird vor dem Request entfernt; Filter lokal

Alle Stripe-Module sollen diese Helpers nutzen. Die HTTP-Wrapper in
stripe_revenue_activator / stripe_payment_links rufen sanitize_* automatisch.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable, Mapping, MutableMapping, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

log = logging.getLogger("stripe_guards")

# ── Test-only payment method IDs (Stripe docs) ───────────────────────────────
# These only exist in test mode. Using them with sk_live_* → invalid_request_error.
TEST_ONLY_PAYMENT_METHODS: frozenset[str] = frozenset({
    "pm_card_visa",
    "pm_card_visa_debit",
    "pm_card_mastercard",
    "pm_card_amex",
    "pm_card_discover",
    "pm_card_diners",
    "pm_card_jcb",
    "pm_card_unionpay",
    "pm_card_chargeDeclined",
    "pm_card_chargeDeclinedInsufficientFunds",
    "pm_card_authenticationRequired",
    "pm_card_threeDSecure2Required",
    "pm_usBankAccount",
    "pm_sepa_debit",
    "tok_visa",
    "tok_visa_debit",
    "tok_mastercard",
    "tok_amex",
    "tok_chargeDeclined",
})

_TEST_PM_PREFIXES = ("pm_card_", "tok_")

# Stripe secret key env names, priority order (FULL first)
_KEY_ENV_NAMES = (
    "STRIPE_SECRET_KEY_FULL",
    "STRIPE_SECRET_KEY",
    "STRIPE_SECRET_KEY_AIITEC",
    "STRIPE_API_KEY",
    "STRIPE_SECRET",
    "STRIPE_TEST_SECRET_KEY",
    "STRIPE_TEST_SECRET_KEY_AIITEC",
)

DEFAULT_THANK_YOU = "https://ineedit.com.co/pages/danke"


# ── Key / mode ───────────────────────────────────────────────────────────────

def resolve_stripe_key() -> str:
    """Return the active Stripe secret key (FULL has priority)."""
    for name in _KEY_ENV_NAMES:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return ""


def resolve_stripe_key_source() -> tuple[str, str]:
    """Return (env_name, key) for the first configured secret key."""
    for name in _KEY_ENV_NAMES:
        val = (os.getenv(name) or "").strip()
        if val:
            return name, val
    return "", ""


def is_live_key(key: Optional[str] = None) -> bool:
    k = (key if key is not None else resolve_stripe_key()).strip()
    return k.startswith("sk_live_") or k.startswith("rk_live_")


def is_test_key(key: Optional[str] = None) -> bool:
    k = (key if key is not None else resolve_stripe_key()).strip()
    return k.startswith("sk_test_") or k.startswith("rk_test_")


def stripe_mode(key: Optional[str] = None) -> str:
    """Return 'live', 'test', or 'unknown'."""
    if is_live_key(key):
        return "live"
    if is_test_key(key):
        return "test"
    return "unknown"


# ── 1) payment_method guards ─────────────────────────────────────────────────

def is_test_only_payment_method(payment_method: str) -> bool:
    pm = (payment_method or "").strip()
    if not pm:
        return False
    if pm in TEST_ONLY_PAYMENT_METHODS:
        return True
    # Any pm_card_* without a real pm_ id shape is treated as test helper
    if pm.startswith("pm_card_"):
        return True
    if pm.startswith("tok_") and not pm.startswith("tok_1"):
        return True
    return False


def allow_test_payment_method(key: Optional[str], payment_method: str) -> bool:
    """False if this PM must not be sent with the given key."""
    if not is_test_only_payment_method(payment_method):
        return True
    return is_test_key(key)


def guard_payment_method(
    key: Optional[str],
    payment_method: str,
    *,
    raise_on_block: bool = False,
) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    In live mode, test-only PMs are blocked permanently.
    """
    if not payment_method:
        return True, "no payment_method"
    if allow_test_payment_method(key, payment_method):
        return True, "ok"
    msg = (
        f"blocked test-only payment_method={payment_method!r} in "
        f"{stripe_mode(key)} mode (use only with sk_test_)"
    )
    log.warning("stripe_guards: %s", msg)
    if raise_on_block:
        raise RuntimeError(msg)
    return False, msg


def sanitize_payment_intent_data(
    key: Optional[str],
    data: MutableMapping[str, Any],
) -> tuple[MutableMapping[str, Any], Optional[str]]:
    """
    Strip/block test-only payment_method fields when key is live.
    Returns (data, skip_reason). If skip_reason is set, caller must NOT POST.
    """
    pm = str(data.get("payment_method") or data.get("payment_method_data") or "")
    # only string PM ids
    if "payment_method" in data:
        pm = str(data.get("payment_method") or "")
        ok, reason = guard_payment_method(key, pm)
        if not ok:
            return data, reason
    return data, None


# ── 2) URL / payment_link guards ─────────────────────────────────────────────

def urlquote_product(name: str, max_len: int = 120) -> str:
    """URL-encode a product name for use in query params (never raw spaces/umlauts)."""
    return quote(str(name or "Produkt"), safe="")[:max_len]


def build_thank_you_url(
    base: Optional[str] = None,
    *,
    product_name: str = "",
    extra: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Build a Stripe-safe after_completion redirect URL.
    Product names are always percent-encoded → prevents url_invalid.
    """
    base_url = (base or os.getenv("STRIPE_THANK_YOU_URL") or DEFAULT_THANK_YOU).strip()
    parts = urlsplit(base_url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    if product_name:
        q["product"] = str(product_name)
    if extra:
        for k, v in extra.items():
            q[str(k)] = str(v) if v is not None else ""
    # urlencode + quote_via=quote → spaces/umlauts/slashes never raw
    query = urlencode(q, quote_via=quote, safe="")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


_REDIRECT_URL_KEYS = frozenset({
    "after_completion[redirect][url]",
    "success_url",
    "cancel_url",
    "return_url",
})


def _ensure_url_safe(url: str) -> str:
    """
    Re-encode query string of a URL if it contains unsafe raw characters.
    Leaves already-valid URLs unchanged.
    """
    if not url or not isinstance(url, str):
        return url
    # Stripe rejects whitespace and many raw unicode chars in redirect URLs
    if not re.search(r"[\s<>\"{}|\\^`\u0080-\uffff]", url):
        # also reject unencoded spaces already covered; if query looks fine, keep
        if " " not in url and "\n" not in url:
            # still re-encode product= values that have unencoded specials
            parts = urlsplit(url)
            if not parts.query:
                return url
            pairs = parse_qsl(parts.query, keep_blank_values=True)
            # If original query had non-ascii or spaces, parse_qsl already decoded
            # Always re-encode for safety
            new_q = urlencode(pairs, quote_via=quote, safe="")
            if new_q == parts.query:
                return url
            return urlunsplit((parts.scheme, parts.netloc, parts.path, new_q, parts.fragment))
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    new_q = urlencode(pairs, quote_via=quote, safe="")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_q, parts.fragment))


def sanitize_redirect_url(url: str) -> str:
    """Public alias: make a redirect URL Stripe-safe."""
    return _ensure_url_safe(url)


def sanitize_payment_link_payload(data: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """
    Ensure payment_link / checkout POST bodies never send raw product names in URLs.
    Mutates and returns data.
    """
    for key in list(data.keys()):
        if key in _REDIRECT_URL_KEYS or key.endswith("[redirect][url]") or key.endswith("success_url"):
            val = data.get(key)
            if isinstance(val, str) and val:
                data[key] = _ensure_url_safe(val)
    return data


def payment_link_payload(
    price_id: str,
    *,
    product_name: str = "",
    thank_you_base: Optional[str] = None,
    quantity: int = 1,
    allow_promotion_codes: bool = True,
    billing_address_collection: str = "auto",
) -> dict[str, str]:
    """Build a form-encoded payment_link create payload (always safe)."""
    redirect = build_thank_you_url(thank_you_base, product_name=product_name)
    payload: dict[str, str] = {
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": str(quantity),
        "after_completion[type]": "redirect",
        "after_completion[redirect][url]": redirect,
        "billing_address_collection": billing_address_collection,
    }
    if allow_promotion_codes:
        payload["allow_promotion_codes"] = "true"
    return sanitize_payment_link_payload(payload)


# ── 3) GET /prices guards ────────────────────────────────────────────────────

def sanitize_prices_params(
    params: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Strip deprecated/fragile `type` query param from GET /prices.
    Filter recurring/one_time locally via filter_prices_by_type() instead.
    """
    out: dict[str, Any] = dict(params or {})
    removed = out.pop("type", None)
    # also handle type[] style if ever used
    removed_list = out.pop("type[]", None)
    if removed is not None or removed_list is not None:
        log.debug(
            "stripe_guards: stripped type=%r from /prices query (filter locally)",
            removed if removed is not None else removed_list,
        )
    return out


def filter_prices_by_type(
    prices: Iterable[Mapping[str, Any]],
    price_type: Optional[str] = None,
) -> list[dict]:
    """
    Local filter: price_type in {'recurring', 'one_time', None}.
    None → return all as list[dict].
    """
    items = [dict(p) for p in prices]
    if not price_type:
        return items
    want = str(price_type).lower().strip()
    if want == "recurring":
        return [p for p in items if p.get("recurring") or p.get("type") == "recurring"]
    if want in ("one_time", "one-time", "onetime"):
        return [p for p in items if not p.get("recurring") and p.get("type") != "recurring"]
    return items


def sanitize_get_params(path: str, params: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """
    Path-aware query sanitizer for any Stripe GET.
    Currently: /prices → drop type.
    """
    p = dict(params or {})
    path_norm = (path or "").split("?")[0].rstrip("/")
    if path_norm.endswith("/prices") or path_norm == "prices" or path_norm.endswith("prices"):
        return sanitize_prices_params(p)
    return p


def sanitize_post_data(path: str, data: Optional[MutableMapping[str, Any]] = None) -> MutableMapping[str, Any]:
    """
    Path-aware body sanitizer for Stripe POST.
    payment_links / checkout → fix redirect URLs.
    payment_intents → block handled by caller with key (see guard).
    """
    d: MutableMapping[str, Any] = dict(data or {})
    path_norm = (path or "").split("?")[0].rstrip("/")
    if (
        "payment_links" in path_norm
        or "checkout/sessions" in path_norm
        or path_norm.endswith("payment_links")
    ):
        return sanitize_payment_link_payload(d)
    return d


# ── Self-check (no network) ──────────────────────────────────────────────────

def self_check() -> dict[str, Any]:
    """Offline regression checks for the three permanent guards."""
    results = []

    # 1) live blocks pm_card_visa
    ok, _ = guard_payment_method("sk_live_x", "pm_card_visa")
    results.append({"name": "block_pm_card_visa_live", "ok": not ok})

    # 1b) test allows pm_card_visa
    ok2, _ = guard_payment_method("sk_test_x", "pm_card_visa")
    results.append({"name": "allow_pm_card_visa_test", "ok": ok2})

    # 2) product name encoded
    url = build_thank_you_url("https://example.com/danke", product_name="Abo Pro / 99€")
    encoded_ok = " " not in url and "/ " not in url and "99" in url and "product=" in url
    results.append({"name": "urlquote_product_name", "ok": encoded_ok, "url": url})

    # 2b) sanitize fixes raw space in redirect
    fixed = sanitize_payment_link_payload({
        "after_completion[redirect][url]": "https://example.com/danke?product=Hello World",
    })
    u = fixed["after_completion[redirect][url]"]
    results.append({"name": "sanitize_redirect_spaces", "ok": " " not in u, "url": u})

    # 3) type stripped from prices params
    cleaned = sanitize_prices_params({"active": "true", "type": "recurring", "limit": "100"})
    results.append({
        "name": "strip_type_from_prices",
        "ok": "type" not in cleaned and cleaned.get("active") == "true",
        "params": cleaned,
    })

    # 3b) local recurring filter
    sample = [
        {"id": "1", "recurring": {"interval": "month"}},
        {"id": "2", "recurring": None, "type": "one_time"},
    ]
    rec = filter_prices_by_type(sample, "recurring")
    results.append({"name": "local_recurring_filter", "ok": len(rec) == 1 and rec[0]["id"] == "1"})

    all_ok = all(r["ok"] for r in results)
    return {"ok": all_ok, "checks": results, "mode": stripe_mode(), "key_set": bool(resolve_stripe_key())}


if __name__ == "__main__":
    import json
    print(json.dumps(self_check(), indent=2, ensure_ascii=False))
