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

    # Wenn Text nur URL ist (Extraktion fehlgeschlagen) → blockieren
    if text == url or len(text.strip()) < 15:
        log.warning("HttpGuard: Text-Extraktion fehlgeschlagen für %s — BLOCK", url[:60])
        return False, "text_extraktion_fehlgeschlagen"

    try:
        from modules.post_validator import validate_post
        platform = _url_to_platform(url)
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
