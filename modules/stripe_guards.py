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

# Stripe secret key env names — NUR bullpowersrtkennels@gmail.com Konto!
# NIEMALS STRIPE_SECRET_KEY_AIITEC verwenden (401, falsches Konto)
_KEY_ENV_NAMES = (
    "STRIPE_SECRET_KEY_FULL",
    "STRIPE_SECRET_KEY",   # bullpowersrtkennels@gmail.com — IMMER diese!
    "STRIPE_API_KEY",
    "STRIPE_SECRET",
    "STRIPE_TEST_SECRET_KEY",
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


# ── Process-level interceptor (aiohttp + urllib) ─────────────────────────────

_PROCESS_GUARD_ACTIVE = False
_BLOCKED_STATS: dict[str, int] = {
    "payment_method_live": 0,
    "type_stripped": 0,
    "url_sanitized": 0,
}


def key_from_auth_header(headers: Any) -> str:
    """Extract Stripe secret key from Authorization header (Bearer or Basic)."""
    if not headers:
        return resolve_stripe_key()
    try:
        if hasattr(headers, "get"):
            auth = headers.get("Authorization") or headers.get("authorization") or ""
        elif isinstance(headers, Mapping):
            auth = headers.get("Authorization") or headers.get("authorization") or ""
        else:
            auth = ""
    except Exception:
        auth = ""
    auth = str(auth)
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    if auth.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode()
            return decoded.split(":", 1)[0]
        except Exception:
            pass
    return resolve_stripe_key()


def _params_to_dict(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, Mapping):
        return dict(params)
    if isinstance(params, (list, tuple)):
        out: dict[str, Any] = {}
        for item in params:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out[str(item[0])] = item[1]
        return out
    return {}


def _data_to_mutable(data: Any) -> Optional[MutableMapping[str, Any]]:
    if data is None:
        return None
    if isinstance(data, MutableMapping):
        return data
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, (list, tuple)):
        out: dict[str, Any] = {}
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out[str(item[0])] = item[1]
        return out
    return None


class StripeGuardBlocked(RuntimeError):
    """Raised when a live-mode request would hit Stripe with a test-only PM."""


def sanitize_outgoing_request(
    method: str,
    url: str,
    *,
    params: Any = None,
    data: Any = None,
    headers: Any = None,
) -> tuple[str, Any, Any, Optional[str]]:
    """
    Sanitize any outgoing Stripe API call.

    Returns (url, params, data, block_reason).
    If block_reason is set, caller MUST NOT send the request to Stripe.
    """
    if "api.stripe.com" not in (url or ""):
        return url, params, data, None

    method_u = (method or "GET").upper()
    parts = urlsplit(url)
    path = parts.path or ""
    # Query embedded in URL
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    pdict = _params_to_dict(params)
    if pdict:
        q.update({str(k): v for k, v in pdict.items()})

    # 3) GET /prices — strip type forever
    if method_u == "GET" and ("/prices" in path or path.rstrip("/").endswith("prices")):
        before = dict(q)
        q = sanitize_prices_params(q)
        if "type" in before or "type[]" in before:
            _BLOCKED_STATS["type_stripped"] += 1
            log.info("stripe_guards[process]: stripped type from GET %s", path)
        # Alles in params, URL-Query leeren → kein Doppel-Encoding durch aiohttp
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        params = q
        return url, params, data, None

    # POST body guards
    if method_u in ("POST", "PUT", "PATCH"):
        mdata = _data_to_mutable(data)
        if mdata is not None:
            # 1) payment_intents + test PM in live
            if "payment_intents" in path:
                key = key_from_auth_header(headers)
                _, skip = sanitize_payment_intent_data(key, mdata)
                if skip:
                    _BLOCKED_STATS["payment_method_live"] += 1
                    log.warning("stripe_guards[process]: BLOCKED %s — %s", path, skip)
                    return url, params, mdata, skip

            # 2) payment_links / checkout redirect URLs
            if "payment_links" in path or "checkout/sessions" in path:
                before_urls = {
                    k: mdata.get(k)
                    for k in list(mdata.keys())
                    if "url" in k.lower()
                }
                mdata = sanitize_post_data(path, mdata)
                after_urls = {
                    k: mdata.get(k)
                    for k in list(mdata.keys())
                    if "url" in k.lower()
                }
                if before_urls != after_urls:
                    _BLOCKED_STATS["url_sanitized"] += 1
                    log.info("stripe_guards[process]: sanitized redirect URL on %s", path)
            data = mdata

    return url, params, data, None


def install_process_guards() -> bool:
    """
    Install process-wide Stripe guards on aiohttp + urllib.
    Safe to call multiple times. Chains with HttpGuard if already patched.
    """
    global _PROCESS_GUARD_ACTIVE
    if _PROCESS_GUARD_ACTIVE:
        return True

    try:
        import aiohttp
        from aiohttp import ClientSession
    except ImportError:
        log.warning("stripe_guards: aiohttp missing — process guard partial")
        ClientSession = None  # type: ignore
        aiohttp = None  # type: ignore

    if ClientSession is not None:
        _prev = ClientSession._request

        async def _stripe_safe_request(self, method, str_or_url, **kwargs):
            url = str(str_or_url)
            if "api.stripe.com" in url:
                params = kwargs.get("params")
                data = kwargs.get("data")
                headers = kwargs.get("headers")
                new_url, new_params, new_data, block = sanitize_outgoing_request(
                    method, url, params=params, data=data, headers=headers,
                )
                if block:
                    raise aiohttp.ClientError(f"StripeGuard blocked: {block}")
                str_or_url = new_url
                if new_params is not None:
                    kwargs["params"] = new_params
                elif "params" in kwargs and new_params is None:
                    pass
                if new_data is not None:
                    kwargs["data"] = new_data
            return await _prev(self, method, str_or_url, **kwargs)

        ClientSession._request = _stripe_safe_request  # type: ignore[method-assign]
        log.info("stripe_guards: aiohttp ClientSession._request patched (process-wide)")

    # urllib for sync clients (stripe_client etc.)
    try:
        import urllib.request as _urllib

        _orig_urlopen = _urllib.urlopen

        def _guarded_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "api.stripe.com" in url:
                method = getattr(req, "get_method", lambda: "GET")()
                headers = dict(req.headers) if hasattr(req, "headers") else {}
                # data on Request
                body = getattr(req, "data", None)
                data_map = None
                if body and isinstance(body, (bytes, bytearray)):
                    try:
                        data_map = dict(parse_qsl(body.decode(), keep_blank_values=True))
                    except Exception:
                        data_map = None
                new_url, _, new_data, block = sanitize_outgoing_request(
                    method, url, params=None, data=data_map, headers=headers,
                )
                if block:
                    raise RuntimeError(f"StripeGuard blocked: {block}")
                if new_url != url and hasattr(req, "full_url"):
                    req.full_url = new_url
                if new_data is not None and method.upper() in ("POST", "PUT", "PATCH"):
                    encoded = urlencode(
                        {k: str(v) for k, v in new_data.items()},
                        quote_via=quote,
                        safe="",
                    ).encode()
                    req.data = encoded
                    # Request may use full_url only
                    try:
                        req.full_url = new_url
                    except Exception:
                        pass
            return _orig_urlopen(req, *args, **kwargs)

        _urllib.urlopen = _guarded_urlopen  # type: ignore[assignment]
        log.info("stripe_guards: urllib.urlopen patched (process-wide)")
    except Exception as exc:
        log.warning("stripe_guards: urllib patch failed: %s", exc)

    _PROCESS_GUARD_ACTIVE = True
    return True


def is_process_guard_active() -> bool:
    return _PROCESS_GUARD_ACTIVE


def guard_stats() -> dict[str, Any]:
    return {
        "active": _PROCESS_GUARD_ACTIVE,
        "stats": dict(_BLOCKED_STATS),
        "mode": stripe_mode(),
        "key_set": bool(resolve_stripe_key()),
    }


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

    # 1c) process sanitizer blocks live PI
    _, _, _, block = sanitize_outgoing_request(
        "POST",
        "https://api.stripe.com/v1/payment_intents",
        data={"payment_method": "pm_card_visa", "amount": "100"},
        headers={"Authorization": "Bearer sk_live_testkey"},
    )
    results.append({"name": "process_block_live_pm", "ok": bool(block)})

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

    # 2c) process sanitizer encodes payment_links URL
    _, _, pdata, _ = sanitize_outgoing_request(
        "POST",
        "https://api.stripe.com/v1/payment_links",
        data={
            "after_completion[redirect][url]": "https://x.com/danke?product=Hello World",
            "line_items[0][price]": "price_1",
        },
    )
    redir = (pdata or {}).get("after_completion[redirect][url]", "")
    results.append({
        "name": "process_sanitize_plink_url",
        "ok": isinstance(redir, str) and " " not in redir,
        "url": redir,
    })

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

    # 3c) process sanitizer strips type from URL query → params
    new_url, new_params, _, _ = sanitize_outgoing_request(
        "GET",
        "https://api.stripe.com/v1/prices?active=true&type=recurring&limit=100",
    )
    p = new_params or {}
    results.append({
        "name": "process_strip_type_from_url",
        "ok": (
            "type=" not in (new_url or "")
            and "type" not in p
            and str(p.get("active")) == "true"
        ),
        "url": new_url,
        "params": p,
    })

    all_ok = all(r["ok"] for r in results)
    return {
        "ok": all_ok,
        "checks": results,
        "mode": stripe_mode(),
        "key_set": bool(resolve_stripe_key()),
        "process_guard": _PROCESS_GUARD_ACTIVE,
        "stats": dict(_BLOCKED_STATS),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(self_check(), indent=2, ensure_ascii=False))
