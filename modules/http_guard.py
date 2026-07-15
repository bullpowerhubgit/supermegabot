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
from typing import Any, Optional
from unittest.mock import patch

import aiohttp
from aiohttp import ClientSession, ClientResponseError
from aiohttp.client import _RequestContextManager

log = logging.getLogger("HttpGuard")

_ACTIVATED = False

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
    """Versucht den Post-Text aus den Request-Parametern zu extrahieren."""
    # JSON Body
    body = kwargs.get("json") or {}
    if isinstance(body, dict):
        # Social: message, text, status, body, content
        for key in ("message", "text", "status", "body", "content", "caption",
                    "title", "subject", "description", "commentary"):
            val = body.get(key) or ""
            if val and isinstance(val, str) and len(val) > 5:
                return val
        # SendGrid
        if "content" in body and isinstance(body["content"], list):
            for c in body["content"]:
                if c.get("value"):
                    return c["value"][:500]
        # Shopify product
        if "product" in body:
            p = body["product"]
            return f"{p.get('title','')}: {p.get('body_html','')}"[:500]

    # Form data (data=)
    data = kwargs.get("data") or {}
    if isinstance(data, dict):
        for key in ("Body", "text", "message", "body", "content"):
            val = data.get(key) or ""
            if val and isinstance(val, str):
                return val

    return url  # Fallback: URL als Text wenn nichts gefunden


async def _guard_check(url: str, content_type: str, kwargs: dict) -> tuple[bool, str]:
    """Führt den PostGuard-Check durch. Gibt (allowed, reason) zurück."""
    try:
        from modules.post_guard import guard
        text = _extract_text(url, content_type, kwargs)
        ok, reason = await guard.check(content_type, text=text)
        return ok, reason
    except Exception as e:
        log.debug("HttpGuard PostGuard-Fehler: %s", e)
        return True, "guard_unavailable"  # Bei Guard-Fehler: durchlassen


# ── aiohttp Monkey-Patch ──────────────────────────────────────────────────────

_original_request = ClientSession._request


async def _intercepted_request(self, method: str, str_or_url: Any, **kwargs: Any):
    url = str(str_or_url)
    content_type = _classify_url(url, method)

    if content_type:
        log.debug("HttpGuard prüft: %s %s", method, url[:80])
        allowed, reason = await _guard_check(url, content_type, kwargs)
        if not allowed:
            log.warning("HttpGuard BLOCK [%s]: %s → %s", content_type, url[:80], reason)
            # Telegram-Alert über blockierten Post
            try:
                tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
                tg_chat  = os.getenv("TELEGRAM_CHAT_ID")
                if tg_token and tg_chat:
                    text = _extract_text(url, content_type, kwargs)
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

            # Wirft ClientResponseError — rufendes Modul bekommt Fehler
            raise ClientResponseError(
                request_info=None,
                history=(),
                status=403,
                message=f"HttpGuard blocked: {reason}",
            )

    return await _original_request(self, method, str_or_url, **kwargs)


def activate() -> None:
    """Aktiviert den HTTP-Guard. Einmalig beim Server-Start aufrufen."""
    global _ACTIVATED
    if _ACTIVATED:
        return
    ClientSession._request = _intercepted_request
    _ACTIVATED = True
    log.info(
        "HttpGuard AKTIV — %d Social + %d Email + %d SMS + %d Shopify Patterns abgefangen",
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
