#!/usr/bin/env python3
"""
Google Merchant Center Feed Uploader
======================================
Registriert den Shopping Feed als Scheduled Fetch via Content API v2.1.
Authentifizierung: Service Account (GCP_SERVICE_ACCOUNT_KEY_B64) oder User OAuth Token.
"""
from __future__ import annotations
import asyncio, base64, json, logging, os, time
from typing import Optional

import aiohttp

log = logging.getLogger("GMCFeedUploader")

MERCHANT_ID = os.getenv("GMC_MERCHANT_ID", "5813214419")
FEED_URL    = "https://supermegabot-production.up.railway.app/api/gmc/feed.xml"
CONTENT_API = "https://shoppingcontent.googleapis.com/content/v2.1"


async def _sa_token() -> str:
    """JWT-Auth mit Service Account Key (GCP_SERVICE_ACCOUNT_KEY_B64)."""
    key_b64 = os.getenv("GCP_SERVICE_ACCOUNT_KEY_B64", "")
    if not key_b64:
        return ""
    try:
        key_obj = json.loads(base64.b64decode(key_b64).decode())
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.primitives.hashes import SHA256
        from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15

        now     = int(time.time())
        header  = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b'=').decode()
        payload = {
            "iss":   key_obj["client_email"],
            "scope": "https://www.googleapis.com/auth/content",
            "aud":   "https://oauth2.googleapis.com/token",
            "exp":   now + 3600, "iat": now,
        }
        payload_b64   = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
        signing_input = f"{header}.{payload_b64}".encode()
        private_key   = load_pem_private_key(key_obj["private_key"].encode(), password=None)
        sig           = private_key.sign(signing_input, PKCS1v15(), SHA256())
        jwt           = f"{header}.{payload_b64}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            r = await s.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            })
            return (await r.json()).get("access_token", "")
    except Exception as e:
        log.warning("SA token error: %s", e)
        return ""


async def _user_token() -> str:
    """Refresh user OAuth token (GOOGLE_REFRESH_TOKEN)."""
    refresh = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    client_id     = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not refresh or not client_id:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            r = await s.post("https://oauth2.googleapis.com/token", json={
                "grant_type": "refresh_token", "refresh_token": refresh,
                "client_id": client_id, "client_secret": client_secret,
            })
            return (await r.json()).get("access_token", "")
    except Exception:
        return ""


async def get_token() -> str:
    """SA token first, user token as fallback."""
    token = await _sa_token()
    if not token:
        token = await _user_token()
    return token


async def register_scheduled_fetch(token: Optional[str] = None) -> dict:
    """Registriert den Feed-URL als Scheduled Fetch in GMC."""
    token = token or await get_token()
    if not token:
        return {"ok": False, "error": "Kein Google-Token — klicke /api/google/auth"}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        # Check existing feeds
        r = await s.get(f"{CONTENT_API}/{MERCHANT_ID}/datafeeds", headers=headers)
        d = await r.json()

        if r.status == 401:
            return {"ok": False, "error": "SA hat keinen GMC-Zugang — bitte SA als Nutzer in Merchant Center hinzufügen"}
        if r.status == 403:
            return {"ok": False, "error": "SA als Admin in GMC eintragen: merchants.google.com → Einstellungen → Nutzer"}
        if r.status != 200:
            return {"ok": False, "error": d.get("error", {}).get("message", str(d))[:100]}

        existing = d.get("resources", [])
        for feed in existing:
            if feed.get("fetchSchedule", {}).get("fetchUrl", "") == FEED_URL:
                return {"ok": True, "status": "already_registered", "feed_id": feed.get("id")}

        # Register new feed
        r2 = await s.post(
            f"{CONTENT_API}/{MERCHANT_ID}/datafeeds",
            headers=headers,
            json={
                "name":            "SuperMegaBot AutoFeed DE",
                "contentType":     "products",
                "contentLanguage": "de",
                "targetCountry":   "DE",
                "format":          {"fileEncoding": "utf-8"},
                "fetchSchedule": {
                    "weekday":  "monday",
                    "hour":     6,
                    "timeZone": "Europe/Berlin",
                    "fetchUrl": FEED_URL,
                    "paused":   False,
                },
            },
        )
        d2 = await r2.json()
        if r2.status in (200, 201):
            feed_id = d2.get("id", "?")
            log.info("GMC Feed registriert: ID=%s", feed_id)
            return {"ok": True, "status": "registered", "feed_id": feed_id, "feed_url": FEED_URL}
        return {"ok": False, "error": d2.get("error", {}).get("message", str(d2))[:100]}


async def list_feeds(token: Optional[str] = None) -> dict:
    token = token or await get_token()
    if not token:
        return {"ok": False, "error": "Kein Token"}
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        r = await s.get(f"{CONTENT_API}/{MERCHANT_ID}/datafeeds", headers=headers)
        d = await r.json()
        if r.status == 200:
            return {"ok": True, "feeds": d.get("resources", [])}
        return {"ok": False, "error": d.get("error", {}).get("message", "")[:80], "status": r.status}
