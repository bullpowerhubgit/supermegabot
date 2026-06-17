"""TikTok Research API — Ad Library query (POST /v2/research/adlib/ad/query/)."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

log = logging.getLogger("TikTokResearch")

_RESEARCH_BASE = "https://open.tiktokapis.com/v2/research"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

_cached_token: Optional[str] = None
_token_expires_at: float = 0.0


def _app_key() -> str:
    return os.getenv("TIKTOK_RESEARCH_APP_KEY", os.getenv("TIKTOK_APP_KEY", ""))


def _app_secret() -> str:
    return os.getenv("TIKTOK_RESEARCH_APP_SECRET", os.getenv("TIKTOK_APP_SECRET", ""))


async def _get_client_token() -> str:
    """Fetch or return cached client_credentials token (scope: research.adlib.basic)."""
    global _cached_token, _token_expires_at
    if _cached_token and time.time() < _token_expires_at - 60:
        return _cached_token

    # Check if static token is set in env
    static = os.getenv("TIKTOK_RESEARCH_TOKEN", "")
    if static:
        _cached_token = static
        _token_expires_at = time.time() + 7200
        return _cached_token

    key = _app_key()
    secret = _app_secret()
    if not key or not secret:
        raise RuntimeError("TIKTOK_RESEARCH_APP_KEY / TIKTOK_RESEARCH_APP_SECRET not set")

    try:
        import aiohttp
    except ImportError:
        raise RuntimeError("aiohttp not installed")

    payload = {
        "client_key": key,
        "client_secret": secret,
        "grant_type": "client_credentials",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(_TOKEN_URL, json=payload,
                          headers={"Content-Type": "application/json"}) as r:
            data = await r.json()

    if data.get("error", {}).get("code", "") not in ("ok", ""):
        raise RuntimeError(f"TikTok token error: {data}")

    token_data = data.get("data", {})
    _cached_token = token_data.get("access_token", "")
    expires_in = token_data.get("expires_in", 7200)
    _token_expires_at = time.time() + expires_in
    log.info("TikTok Research token fetched, expires in %ss", expires_in)
    return _cached_token


async def query_ads(
    date_min: str,
    date_max: str,
    country_code: str = "ALL",
    search_term: str = "",
    search_type: str = "fuzzy_phrase",
    advertiser_business_ids: list[int] | None = None,
    unique_users_seen_min: str = "",
    unique_users_seen_max: str = "",
    max_count: int = 20,
    search_id: str = "",
    fields: str = "ad.id,ad.first_shown_date,ad.last_shown_date,ad.status,ad.videos,ad.image_urls,ad.reach,advertiser.business_id,advertiser.business_name,advertiser.paid_by",
) -> dict[str, Any]:
    """Query TikTok Ad Library and return raw API response."""
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed"}

    token = await _get_client_token()

    filters: dict[str, Any] = {
        "ad_published_date_range": {"min": date_min, "max": date_max},
    }
    if country_code and country_code != "ALL":
        filters["country_code"] = country_code
    if advertiser_business_ids:
        filters["advertiser_business_ids"] = advertiser_business_ids
    if unique_users_seen_min or unique_users_seen_max:
        sr: dict[str, str] = {}
        if unique_users_seen_min:
            sr["min"] = unique_users_seen_min
        if unique_users_seen_max:
            sr["max"] = unique_users_seen_max
        filters["unique_users_seen_size_range"] = sr

    body: dict[str, Any] = {
        "filters": filters,
        "max_count": max_count,
    }
    if search_term:
        body["search_term"] = search_term
        body["search_type"] = search_type
    if search_id:
        body["search_id"] = search_id

    url = f"{_RESEARCH_BASE}/adlib/ad/query/?fields={fields}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=body, headers=headers) as r:
            return await r.json()


async def check_status() -> dict[str, Any]:
    """Validate Research API credentials by fetching a client token."""
    key = _app_key()
    if not key:
        return {"status": "error", "message": "TIKTOK_RESEARCH_APP_KEY not set"}
    try:
        token = await _get_client_token()
        return {
            "status": "ok",
            "token_preview": token[:12] + "...",
            "app_key": key,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
