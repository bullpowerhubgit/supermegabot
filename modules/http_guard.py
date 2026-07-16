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


def _extract_text(url: str, content_type: str, kwargs: dict) -> str:
    """
    Extrahiert den Post-Text aus Request-Parametern.
    Unterstützt: Facebook/IG, Twitter, LinkedIn, TikTok, Pinterest,
                 SendGrid, Klaviyo, Mailchimp, Twilio, Shopify.
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
        return ""

    body = kwargs.get("json") or {}
    data = kwargs.get("data") or {}

    if isinstance(body, dict):
        # ── Facebook / Instagram ──────────────────────────────────────────────
        t = _first_nonempty(body.get("message"), body.get("caption"), body.get("description"))
        if t: return t

        # ── Twitter ──────────────────────────────────────────────────────────
        t = _first_nonempty(body.get("text"), body.get("status"))
        if t: return t

        # ── LinkedIn ─────────────────────────────────────────────────────────
        if "specificContent" in body:
            sc = body["specificContent"]
            share = sc.get("com.linkedin.ugc.ShareContent", {})
            text_obj = share.get("shareCommentary", {})
            t = _first_nonempty(text_obj.get("text"))
            if t: return t
        if "commentary" in body:
            t = _first_nonempty(body.get("commentary"))
            if t: return t
        # LinkedIn ugcPosts format
        if "author" in body and "lifecycleState" in body:
            media = body.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {})
            t = _first_nonempty(media.get("shareCommentary", {}).get("text"))
            if t: return t

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
            try:
                remember_block(text, platform, nt_errs, source_module="http_guard")
            except Exception:
                pass
            return False, f"never_twice: {nt_errs[0] if nt_errs else 'blocked'}"
    except Exception as e:
        log.error("HttpGuard NeverTwice fail-closed: %s", e)
        return False, f"never_twice_error_blocked: {e}"

    # Wenn Text nur URL ist (Extraktion fehlgeschlagen) → blockieren
    if text == url or len(text.strip()) < 15:
        log.warning("HttpGuard: Text-Extraktion fehlgeschlagen für %s — BLOCK", url[:60])
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
    if "api.stripe.com" in url:
        try:
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
        allowed, reason = await _guard_check(url, content_type, kwargs)
        if not allowed:
            log.warning("HttpGuard BLOCK [%s]: %s → %s", content_type, url[:80], reason)
            text = _extract_text(url, content_type, kwargs)
            # NEVER-TWICE: speichern — gleicher Fehler nie wieder
            try:
                from modules.post_never_twice import remember_block
                remember_block(
                    text,
                    _url_to_platform(url),
                    [str(reason)],
                    source_module="http_guard",
                )
            except Exception:
                pass
            # Telegram-Alert über blockierten Post
            try:
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
                tg_chat  = os.getenv("TELEGRAM_CHAT_ID")
                if tg_token and tg_chat:
                    msg = (
                        f"🚫 <b>HttpGuard blockiert</b>\n"
                        f"Typ: {content_type}\n"
                        f"URL: {url[:60]}\n"
                        f"Grund: {reason}\n"
                        f"Inhalt: <i>{text[:200]}</i>"
                    )
                    # Direkter urllib-Call um Rekursion zu vermeiden
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

            # ClientError (NICHT ClientResponseError(None) — crasht bei str(e)!)
            raise aiohttp.ClientError(f"HttpGuard blocked [{content_type}]: {reason}")

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


def activate() -> None:
    """Aktiviert den HTTP-Guard. Einmalig beim Server-Start aufrufen."""
    global _ACTIVATED
    if _ACTIVATED:
        return
    ClientSession._request = _intercepted_request
    _patch_urllib_telegram()
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
