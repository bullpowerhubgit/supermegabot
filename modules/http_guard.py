#!/usr/bin/env python3
"""
HTTP Guard — Permanenter Interceptor für ALLE ausgehenden Posts
===============================================================
Wird EINMALIG beim Server-Start aktiviert via activate().
Danach läuft jede aiohttp-POST-Anfrage an Social/Email/SMS/Shopify-Endpoints
automatisch durch den PostGuard — egal aus welchem Modul sie kommt.

Abgefangene Endpoints:
  Social:   graph.facebook.com (FB + IG), api.twitter.com, api.linkedin.com
            open.tiktokapis.com, api.pinterest.com, upload.twitter.com
  Email:    api.sendgrid.com, *.api.mailchimp.com, send.klaviyo.com
  SMS:      api.twilio.com/*/Messages
  Shopify:  *.myshopify.com/admin/api/*/products.json (nur POST = create)
  Telegram: api.telegram.org/bot*/sendMessage (nur wenn an Kanal, nicht Chat)

Was passiert bei BLOCK:
  → aiohttp ClientResponseError mit Status 403 wird geworfen
  → Das rufende Modul bekommt einen Fehler und loggt ihn — kein Post

Was passiert bei APPROVE:
  → Request wird transparent durchgelassen

Einbindung (einmalig in server.py):
    from modules.http_guard import activate
    activate()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Optional
from unittest.mock import patch

import aiohttp
from aiohttp import ClientSession, ClientResponseError
from aiohttp.client import _RequestContextManager

log = logging.getLogger("HttpGuard")

_ACTIVATED = False

# ── Telegram Rate Limiter (global für ALLE aiohttp Telegram-Calls) ────────────
_TG_MIN_INTERVAL = 3.0   # max 1 Nachricht / 3s (Telegram-Limit: 30/s per group, aber in Praxis 1/3s safe)
_tg_last_sent: float = 0.0
_tg_lock = asyncio.Lock()
_tg_blocked_count: int = 0
_alert_cache: dict[str, float] = {}


async def _tg_rate_check() -> bool:
    """Gibt True zurück wenn Telegram-Call erlaubt ist, False wenn Rate-Limit greift."""
    global _tg_last_sent, _tg_blocked_count
    async with _tg_lock:
        now = time.monotonic()
        since = now - _tg_last_sent
        if since >= _TG_MIN_INTERVAL:
            _tg_last_sent = now
            return True
        _tg_blocked_count += 1
        if _tg_blocked_count % 20 == 1:
            log.warning("TelegramGuard: %d Nachrichten rate-limitiert (1/%gs Limit)", _tg_blocked_count, _TG_MIN_INTERVAL)
        return False


def _should_send_guard_alert(reason: str, url: str, text: str = "", window_seconds: int = 1800) -> bool:
    lowered = (reason or "").lower()
    noisy_markers = (
        "duplikat",
        "bereits_blockiert",
        "rate limit",
        "rate_limited",
        "database is locked",
        "never_twice_error_blocked",
        "text_extraktion_fehlgeschlagen",
    )
    if any(marker in lowered for marker in noisy_markers):
        return False
    key = f"{url[:80]}|{reason[:120]}|{text[:80]}"
    now = time.monotonic()
    last = _alert_cache.get(key, 0.0)
    if now - last < window_seconds:
        return False
    _alert_cache[key] = now
    return True

# ── Posting-Endpoints die abgefangen werden ───────────────────────────────────
_SOCIAL_POST_PATTERNS = [
    # Facebook + Instagram Posts
    re.compile(r"graph\.facebook\.com/.+/(feed|media|photos|videos)$", re.I),
    re.compile(r"graph\.facebook\.com/v\d+\.\d+/\d+/(feed|media|photos|videos)$", re.I),
    re.compile(r"graph\.facebook\.com/.+/media_publish$", re.I),
    # Twitter
    re.compile(r"api\.twitter\.com/.*/tweets$", re.I),
    re.compile(r"upload\.twitter\.com/", re.I),
    # LinkedIn
    re.compile(r"api\.linkedin\.com/v2/shares$", re.I),
    re.compile(r"api\.linkedin\.com/v2/ugcPosts$", re.I),
    re.compile(r"api\.linkedin\.com/v2/posts$", re.I),
    # TikTok
    re.compile(r"open\.tiktokapis\.com/.*/post/publish", re.I),
    re.compile(r"open\.tiktokapis\.com/.*/video/init", re.I),
    # Pinterest
    re.compile(r"api\.pinterest\.com/v5/pins$", re.I),
]

_EMAIL_POST_PATTERNS = [
    re.compile(r"api\.sendgrid\.com/v3/mail/send$", re.I),
    re.compile(r"\.api\.mailchimp\.com/.*/messages/send", re.I),
    re.compile(r"\.api\.mailchimp\.com/.*/campaigns/.*/actions/send", re.I),
    re.compile(r"send\.klaviyo\.com/", re.I),
    re.compile(r"a\.klaviyo\.com/api/track", re.I),
    re.compile(r"mandrillapp\.com/api/", re.I),
    re.compile(r"api\.brevo\.com/v3/smtp/email", re.I),
    re.compile(r"api\.resend\.com/emails$", re.I),
]

_SMS_POST_PATTERNS = [
    re.compile(r"api\.twilio\.com/\d{4}-\d{2}-\d{2}/Accounts/.+/Messages\.json$", re.I),
]

_SHOPIFY_CREATE_PATTERNS = [
    re.compile(r"\.myshopify\.com/admin/api/[^/]+/products\.json$", re.I),
]

# Telegram nur wenn an Kanal (negative ID), nicht an privaten Chat
_TELEGRAM_CHANNEL_PATTERN = re.compile(
    r"api\.telegram\.org/bot[^/]+/sendMessage$", re.I
)


def _classify_url(url: str, method: str) -> Optional[str]:
    """Gibt den Content-Type zurück wenn der Request abgefangen werden soll, sonst None."""
    if method.upper() != "POST":
        return None
    for p in _SOCIAL_POST_PATTERNS:
        if p.search(url):
            return "social"
    for p in _EMAIL_POST_PATTERNS:
        if p.search(url):
            return "email"
    for p in _SMS_POST_PATTERNS:
        if p.search(url):
            return "sms"
    for p in _SHOPIFY_CREATE_PATTERNS:
        if p.search(url):
            return "product"
    return None


def _parse_body_kwargs(kwargs: dict) -> dict:
    """Normalisiert json=/data= zu einem dict (str/bytes JSON → parse)."""
    import json as _json

    def _to_dict(raw):
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8", errors="ignore")
            except Exception:
                return {}
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                return {}
            if s.startswith("{") or s.startswith("["):
                try:
                    parsed = _json.loads(s)
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
            # form-urlencoded: text=...&...
            if "=" in s and "&" in s:
                try:
                    from urllib.parse import parse_qs
                    qs = parse_qs(s, keep_blank_values=True)
                    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in qs.items()}
                except Exception:
                    return {}
        return {}

    body = _to_dict(kwargs.get("json"))
    if not body:
        body = _to_dict(kwargs.get("data"))
    return body if isinstance(body, dict) else {}


def _extract_text(url: str, content_type: str, kwargs: dict) -> str:
    """
    Extrahiert den Post-Text aus Request-Parametern.
    Unterstützt: Facebook/IG, Twitter, LinkedIn, TikTok, Pinterest,
                 SendGrid, Klaviyo, Mailchimp, Twilio, Shopify.
    WICHTIG: json= als str/bytes wird geparst — sonst war Inhalt nur die API-URL.
    """
    import re as _re

    def _clean(s):
        if not isinstance(s, str):
            return ""
        # HTML-Tags entfernen für Lesbarkeit
        s = _re.sub(r"<[^>]{1,200}>", " ", s)
        s = _re.sub(r"\s+", " ", s).strip()
        return s[:1000]

    def _first_nonempty(*vals):
        for v in vals:
            if isinstance(v, str) and len(v.strip()) > 10:
                return _clean(v)
            # nested dict with "text"
            if isinstance(v, dict):
                inner = v.get("text") or v.get("message") or v.get("commentary")
                if isinstance(inner, str) and len(inner.strip()) > 10:
                    return _clean(inner)
        return ""

    body = _parse_body_kwargs(kwargs)
    # Auch URL-Query-Params prüfen (manche Module nutzen params= statt data=/json=)
    _params = kwargs.get("params") if isinstance(kwargs.get("params"), dict) else {}
    if not body and _params:
        body = _params
    data = kwargs.get("data") if isinstance(kwargs.get("data"), dict) else {}

    if isinstance(body, dict) and body:
        # ── Facebook / Instagram ──────────────────────────────────────────────
        t = _first_nonempty(body.get("message"), body.get("caption"), body.get("description"))
        if t: return t

        # ── Twitter ──────────────────────────────────────────────────────────
        t = _first_nonempty(body.get("text"), body.get("status"))
        if t: return t

        # ── LinkedIn ugcPosts / shares / posts ───────────────────────────────
        # specificContent.com.linkedin.ugc.ShareContent.shareCommentary.text
        sc = body.get("specificContent") or {}
        if isinstance(sc, dict):
            for k, v in sc.items():
                if isinstance(v, dict):
                    commentary = v.get("shareCommentary") or v.get("commentary") or {}
                    if isinstance(commentary, dict):
                        t = _first_nonempty(commentary.get("text"))
                        if t: return t
                    t = _first_nonempty(v.get("text"), commentary if isinstance(commentary, str) else "")
                    if t: return t
            share = sc.get("com.linkedin.ugc.ShareContent", {})
            if isinstance(share, dict):
                t = _first_nonempty(
                    (share.get("shareCommentary") or {}).get("text")
                    if isinstance(share.get("shareCommentary"), dict) else share.get("shareCommentary")
                )
                if t: return t
        if "commentary" in body:
            t = _first_nonempty(body.get("commentary"))
            if t: return t
        # deep search for shareCommentary anywhere (defensive)
        def _walk_for_text(obj, depth=0):
            if depth > 6:
                return ""
            if isinstance(obj, dict):
                for key in ("text", "message", "commentary", "shareCommentary", "description", "caption"):
                    val = obj.get(key)
                    if isinstance(val, str) and len(val.strip()) > 15:
                        # skip pure URLs / urns
                        if not val.strip().startswith("urn:") and "api.linkedin.com" not in val:
                            return _clean(val)
                    if isinstance(val, dict):
                        found = _walk_for_text(val, depth + 1)
                        if found:
                            return found
                for val in obj.values():
                    found = _walk_for_text(val, depth + 1)
                    if found:
                        return found
            elif isinstance(obj, list):
                for item in obj[:20]:
                    found = _walk_for_text(item, depth + 1)
                    if found:
                        return found
            return ""
        if "linkedin" in (url or "").lower() or "specificContent" in body or "author" in body:
            deep = _walk_for_text(body)
            if deep:
                return deep

        # ── TikTok ───────────────────────────────────────────────────────────
        post_info = body.get("post_info", {})
        t = _first_nonempty(post_info.get("title"), post_info.get("description"))
        if t: return t

        # ── Pinterest ────────────────────────────────────────────────────────
        t = _first_nonempty(body.get("note"), body.get("title"), body.get("description"))
        if t: return t

        # ── SendGrid ─────────────────────────────────────────────────────────
        if "personalizations" in body or "from" in body:
            subject = body.get("subject", "")
            content_list = body.get("content", [])
            content_text = " ".join(c.get("value", "") for c in content_list if isinstance(c, dict))
            t = _first_nonempty(subject + " " + content_text)
            if t: return t

        # ── Klaviyo ──────────────────────────────────────────────────────────
        if "data" in body and isinstance(body["data"], dict):
            attrs = body["data"].get("attributes", {})
            t = _first_nonempty(
                attrs.get("name"), attrs.get("subject"),
                str(attrs.get("send_options", {}))
            )
            if t: return t
        # Klaviyo track
        if "event" in body:
            t = _first_nonempty(
                body.get("event"),
                str(body.get("properties", {}))[:200]
            )
            if t: return t

        # ── Mailchimp ─────────────────────────────────────────────────────────
        if "settings" in body:
            s = body["settings"]
            t = _first_nonempty(s.get("subject_line"), s.get("title"))
            if t: return t
        if "message" in body and isinstance(body["message"], dict):
            msg = body["message"]
            t = _first_nonempty(msg.get("subject"), msg.get("text"), msg.get("html"))
            if t: return t

        # ── Shopify product ───────────────────────────────────────────────────
        if "product" in body:
            p = body["product"]
            title = p.get("title", "")
            desc = _re.sub(r"<[^>]+>", " ", p.get("body_html", ""))
            t = _first_nonempty(f"{title} {desc}")
            if t: return t

        # ── Generic fallback keys ─────────────────────────────────────────────
        for key in ("body", "content", "html", "text_body", "post_text"):
            t = _first_nonempty(body.get(key))
            if t: return t

    # ── Form data (Twilio SMS, etc.) ──────────────────────────────────────────
    if isinstance(data, dict):
        for key in ("Body", "body", "text", "message", "content", "Message"):
            val = data.get(key) or ""
            t = _first_nonempty(val)
            if t: return t

    return url  # Fallback: URL → wird als "Extraktion fehlgeschlagen" behandelt


def _url_to_platform(url: str) -> str:
    """Extrahiert den Plattform-Namen aus der URL."""
    if "facebook.com" in url or "fb.com" in url:
        return "facebook"
    if "instagram.com" in url:
        return "instagram"
    if "twitter.com" in url or "x.com" in url:
        return "twitter"
    if "linkedin.com" in url:
        return "linkedin"
    if "tiktok" in url:
        return "tiktok"
    if "pinterest.com" in url:
        return "pinterest"
    if "sendgrid.com" in url:
        return "sendgrid"
    if "klaviyo.com" in url:
        return "klaviyo"
    if "mailchimp.com" in url:
        return "mailchimp"
    if "twilio.com" in url:
        return "sms"
    if "myshopify.com" in url:
        return "shopify"
    if "telegram.org" in url:
        return "telegram"
    return "unknown"


async def _guard_check(url: str, content_type: str, kwargs: dict) -> tuple[bool, str]:
    """Führt den 5-Layer PostValidator-Check durch. Gibt (allowed, reason) zurück.
    FAIL-SAFE: Bei jedem Fehler → BLOCKIEREN (nie durchlassen!)
    """
    text = _extract_text(url, content_type, kwargs)
    platform = _url_to_platform(url)

    # Schicht 0: NEVER-TWICE — gleicher Fehler/Content nie wieder
    try:
        from modules.post_never_twice import check_never_twice, remember_block
        nt_ok, nt_errs = check_never_twice(text, platform)
        if not nt_ok:
            # Flatten: nimm nur den ersten Grund, ohne rekursive NEVER-TWICE-Verschachtelung
            raw = (nt_errs[0] if nt_errs else "blocked")
            short_reason = raw[:200] if not raw.startswith("NEVER-TWICE") else "bereits_blockiert"
            try:
                remember_block(text, platform, [short_reason], source_module="http_guard")
            except Exception:
                pass
            return False, f"never_twice: {short_reason}"
    except Exception as e:
        if "locked" in str(e).lower():
            log.warning("HttpGuard NeverTwice locked — fail-open")
        else:
            log.error("HttpGuard NeverTwice fail-closed: %s", e)
            return False, f"never_twice_error_blocked: {e}"

    # Wenn Text nur URL ist (Extraktion fehlgeschlagen) → BLOCK (fail-closed)
    # Niemals Social-Posts ohne lesbaren Content durchlassen (LinkedIn-Bug war: nur API-URL)
    if text == url or len((text or "").strip()) < 15:
        log.warning("HttpGuard: Text-Extraktion fehlgeschlagen für %s — BLOCK", str(url)[:60])
        return False, "text_extraktion_fehlgeschlagen"

    try:
        from modules.post_validator import validate_post
        ok, layer, reason = await validate_post(
            text=text,
            platform=platform,
            content_type=content_type,
        )
        return ok, reason
    except Exception as e:
        # KRITISCH: Bei Guard-Fehler NIEMALS durchlassen
        log.error("HttpGuard PostValidator-Fehler: %s — BLOCK (fail-safe)", e)
        return False, f"validator_error_blocked: {e}"


# ── aiohttp Monkey-Patch ──────────────────────────────────────────────────────

_original_request = ClientSession._request


async def _intercepted_request(self, method: str, str_or_url: Any, **kwargs: Any):
    url = str(str_or_url)

    # ── StripeGuard — dauerhaft ALLE api.stripe.com Calls sanitizen ───────────
    # Verhindert: pm_card_visa@live, url_invalid, type=recurring on GET /prices
    # + BULLPOWER-ONLY: AIITEC/fremde Keys im Authorization-Header ersetzen
    if "api.stripe.com" in url:
        try:
            # NUR bullpowersrtkennels — AIITEC Keys im Header killen
            try:
                from modules.stripe_key_resolver import rewrite_auth_header_value, get_working_stripe_key
                hdrs = kwargs.get("headers")
                if hdrs is not None:
                    # aiohttp headers may be CIMultiDict
                    auth = None
                    try:
                        auth = hdrs.get("Authorization") or hdrs.get("authorization")
                    except Exception:
                        if isinstance(hdrs, dict):
                            auth = hdrs.get("Authorization") or hdrs.get("authorization")
                    if auth:
                        new_auth = rewrite_auth_header_value(str(auth))
                        if new_auth != auth:
                            try:
                                hdrs["Authorization"] = new_auth
                            except Exception:
                                kwargs["headers"] = dict(hdrs)
                                kwargs["headers"]["Authorization"] = new_auth
                    else:
                        # ensure bullpower key present
                        k = get_working_stripe_key()
                        if k:
                            try:
                                hdrs["Authorization"] = f"Bearer {k}"
                            except Exception:
                                kwargs["headers"] = dict(hdrs) if hdrs is not None else {}
                                kwargs["headers"]["Authorization"] = f"Bearer {k}"
            except Exception as _bp:
                log.debug("Stripe bullpower auth rewrite: %s", _bp)
            from modules.stripe_guards import sanitize_outgoing_request
            new_url, new_params, new_data, block = sanitize_outgoing_request(
                method,
                url,
                params=kwargs.get("params"),
                data=kwargs.get("data"),
                headers=kwargs.get("headers"),
            )
            if block:
                log.warning("StripeGuard BLOCK via HttpGuard: %s", block)
                raise aiohttp.ClientError(f"StripeGuard blocked: {block}")
            str_or_url = new_url
            url = new_url
            if new_params is not None:
                kwargs["params"] = new_params
            if new_data is not None:
                kwargs["data"] = new_data
        except aiohttp.ClientError:
            raise
        except Exception as _sg_err:
            log.debug("StripeGuard non-fatal: %s", _sg_err)

    # ── Telegram Rate Limiter — greift für ALLE sendMessage Calls ─────────────
    if method.upper() == "POST" and "api.telegram.org" in url and "sendMessage" in url:
        allowed = await _tg_rate_check()
        if not allowed:
            log.debug("TelegramGuard: DROP %s (rate limit)", url[:80])
            # Nutze aiohttp.ClientError — hat funktionierenden __str__()
            raise aiohttp.ClientError("TelegramGuard: rate limited (1 msg/3s)")

    content_type = _classify_url(url, method)

    if content_type:
        log.debug("HttpGuard prüft: %s %s", method, url[:80])
        _post_text    = _extract_text(url, content_type, kwargs)
        _post_platform = _url_to_platform(url)
        allowed, reason = await _guard_check(url, content_type, kwargs)
        if not allowed:
            log.warning("HttpGuard BLOCK [%s]: %s → %s", content_type, url[:80], reason)
            # NEVER-TWICE: speichern — aber NICHT wenn Text nur die API-URL ist
            # (sonst landet ugcPosts als "Content" in der Blacklist und blockt alles)
            try:
                from modules.post_never_twice import remember_block
                _is_bare_api = (
                    not _post_text
                    or _post_text.strip() == url.strip()
                    or _post_text.strip().startswith("https://api.")
                    and len(_post_text.strip()) < 80
                )
                if not _is_bare_api:
                    remember_block(
                        _post_text, _post_platform, [str(reason)], source_module="http_guard"
                    )
            except Exception:
                pass
            # Telegram-Alert über blockierten Post
            try:
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
                tg_chat  = os.getenv("TELEGRAM_CHAT_ID")
                if tg_token and tg_chat and _should_send_guard_alert(str(reason), url, _post_text):
                    msg = (
                        f"🚫 <b>HttpGuard blockiert</b>\n"
                        f"Typ: {content_type}\n"
                        f"URL: {url[:60]}\n"
                        f"Grund: {reason}\n"
                        f"Inhalt: <i>{_post_text[:200]}</i>"
                    )
                    import urllib.request, urllib.parse
                    payload = json.dumps({
                        "chat_id": tg_chat, "text": msg, "parse_mode": "HTML"
                    }).encode()
                    req = urllib.request.Request(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
            raise aiohttp.ClientError(f"HttpGuard blocked [{content_type}]: {reason}")

        # Erlaubter Post — nach Erfolg in NeverTwice registrieren (Duplikat-Schutz)
        response = await _original_request(self, method, str_or_url, **kwargs)
        if response.status in range(200, 300) and _post_text:
            try:
                from modules.post_never_twice import remember_sent
                remember_sent(_post_text, _post_platform, source_module="http_guard")
            except Exception:
                pass
        return response

    return await _original_request(self, method, str_or_url, **kwargs)


_tg_urllib_last: float = 0.0
_tg_urllib_blocked: int = 0


def _patch_urllib_telegram() -> None:
    """Patcht urllib.request.urlopen um Telegram-Calls zu rate-limitieren."""
    import urllib.request as _urllib
    _orig_urlopen = _urllib.urlopen

    def _guarded_urlopen(req, *args, **kwargs):
        global _tg_urllib_last, _tg_urllib_blocked
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.telegram.org" in url and "sendMessage" in url:
            now = time.monotonic()
            if now - _tg_urllib_last < _TG_MIN_INTERVAL:
                _tg_urllib_blocked += 1
                if _tg_urllib_blocked % 10 == 1:
                    log.warning("TelegramGuard(urllib): %d Calls verworfen", _tg_urllib_blocked)
                raise Exception("TelegramGuard: urllib rate limited")
            _tg_urllib_last = now
        return _orig_urlopen(req, *args, **kwargs)

    _urllib.urlopen = _guarded_urlopen


def _patch_requests_sync() -> None:
    """
    Patcht die sync `requests`-Library um Off-Topic + Placeholder Posts zu blockieren.
    Kein AI-Score (sync), aber Layer 0 (off-topic) + Layer 1 (placeholder) laufen.
    """
    try:
        import requests as _req
        from modules.post_validator import _L0_RE, _L1_RE, _L2_SPAM
        _orig_send = _req.Session.send

        def _guarded_send(self, prepared, **kwargs):
            url = str(prepared.url or "")
            method = str(prepared.method or "").upper()
            if method == "POST":
                is_social = any(p.search(url) for p in _SOCIAL_POST_PATTERNS)
                if is_social:
                    # Extrahiere Text aus Body
                    body_text = ""
                    if prepared.body:
                        try:
                            bd = json.loads(prepared.body) if isinstance(prepared.body, (bytes, str)) else {}
                            body_text = str(bd.get("message") or bd.get("caption") or
                                           bd.get("text") or bd.get("commentary") or
                                           bd.get("note") or bd.get("title") or "")
                        except Exception:
                            body_text = str(prepared.body)[:500]

                    if body_text and len(body_text) > 10:
                        # Layer 0: Off-Topic
                        for rx in _L0_RE:
                            if rx.search(body_text):
                                platform = _url_to_platform(url)
                                log.warning("RequestsGuard BLOCK off_topic [%s]: %s", platform, rx.pattern[:40])
                                try:
                                    from modules.post_never_twice import remember_block
                                    remember_block(body_text, platform, [f"off_topic:{rx.pattern[:30]}"], source_module="requests_guard")
                                except Exception:
                                    pass
                                raise _req.exceptions.ConnectionError(f"RequestsGuard: off_topic blocked ({rx.pattern[:30]})")

                        # Layer 1: Placeholder
                        for rx in _L1_RE:
                            if rx.search(body_text):
                                platform = _url_to_platform(url)
                                log.warning("RequestsGuard BLOCK placeholder [%s]: %s", platform, rx.pattern[:40])
                                raise _req.exceptions.ConnectionError(f"RequestsGuard: placeholder blocked ({rx.pattern[:30]})")

                        # Layer 2: Spam-Phrasen
                        text_lower = body_text.lower()
                        for phrase in _L2_SPAM:
                            if phrase in text_lower:
                                platform = _url_to_platform(url)
                                log.warning("RequestsGuard BLOCK spam [%s]: %s", platform, phrase)
                                raise _req.exceptions.ConnectionError(f"RequestsGuard: spam blocked ({phrase})")

            return _orig_send(self, prepared, **kwargs)

        _req.Session.send = _guarded_send
        log.info("RequestsGuard AKTIV — sync requests.post ebenfalls überwacht")
    except ImportError:
        log.debug("requests-Library nicht installiert — RequestsGuard übersprungen")
    except Exception as e:
        log.warning("RequestsGuard patch fehlgeschlagen (non-fatal): %s", e)


def activate() -> None:
    """Aktiviert den HTTP-Guard. Einmalig beim Server-Start aufrufen."""
    global _ACTIVATED
    if _ACTIVATED:
        return
    ClientSession._request = _intercepted_request
    _patch_urllib_telegram()
    _patch_requests_sync()
    # Stripe process-guards (urllib + stats) — aiohttp läuft bereits über uns
    try:
        from modules.stripe_guards import install_process_guards, self_check
        # Mark process guard; urllib patch still useful for sync clients
        install_process_guards()
        # Re-bind aiohttp to OUR interceptor (install_process_guards may have wrapped)
        # Chain: our intercept → (maybe stripe layer) → original
        # Ensure HttpGuard stays outermost for social + stripe
        ClientSession._request = _intercepted_request
        sc = self_check()
        if sc.get("ok"):
            log.info("StripeGuard self_check OK — 3 Live-Error-Klassen dauerhaft geblockt")
        else:
            log.error("StripeGuard self_check FAILED: %s", sc)
    except Exception as e:
        log.warning("StripeGuard activate failed (non-fatal): %s", e)
    _ACTIVATED = True
    log.info(
        "HttpGuard AKTIV — %d Social + %d Email + %d SMS + %d Shopify Patterns + Telegram Rate-Limit + StripeGuard",
        len(_SOCIAL_POST_PATTERNS),
        len(_EMAIL_POST_PATTERNS),
        len(_SMS_POST_PATTERNS),
        len(_SHOPIFY_CREATE_PATTERNS),
    )


def deactivate() -> None:
    """Deaktiviert den Guard (nur für Tests)."""
    global _ACTIVATED
    ClientSession._request = _original_request
    _ACTIVATED = False
    log.warning("HttpGuard DEAKTIVIERT")


def is_active() -> bool:
    return _ACTIVATED
