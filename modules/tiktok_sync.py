#!/usr/bin/env python3
"""
TikTok Business Automation — post scheduling, product links, analytics.
Requires: TIKTOK_ACCESS_TOKEN, TIKTOK_ADVERTISER_ID (optional)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import aiohttp

log = logging.getLogger("TikTokSync")

ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
ADVERTISER_ID = os.getenv("TIKTOK_ADVERTISER_ID", "")
OPEN_API = "https://open-api.tiktok.com"
BASE = "https://open.tiktokapis.com/v2"
DS24 = os.getenv("DS24_AFFILIATE_LINK", "https://www.digistore24.com/redir/669750/user37405262/")
SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


async def get_status() -> dict:
    return {
        "configured": bool(ACCESS_TOKEN),
        "token_set": bool(ACCESS_TOKEN),
        "advertiser_id": bool(ADVERTISER_ID),
        "ds24_link": DS24,
        "shop": f"https://{SHOP}",
    }


async def get_user_info() -> dict:
    if not ACCESS_TOKEN:
        return {"ok": False, "error": "TIKTOK_ACCESS_TOKEN not set"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/user/info/",
                headers=_headers(),
                params={"fields": "display_name,follower_count,video_count"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            return {"ok": False, "error": data["error"].get("message")}
        user = data.get("data", {}).get("user", {})
        return {"ok": True, "user": user}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_video_caption(caption: str, video_url: str = "") -> dict:
    """Schedule a TikTok post — requires VIDEO_UPLOAD flow or Creator API."""
    if not ACCESS_TOKEN:
        return {"ok": False, "error": "TIKTOK_ACCESS_TOKEN not set. Get at developers.tiktok.com"}
    return {
        "ok": False,
        "error": "TikTok video upload requires manual auth via OAuth2 + Content Posting API",
        "next_step": "Set TIKTOK_ACCESS_TOKEN in Railway after OAuth flow at developers.tiktok.com",
    }


async def generate_caption(topic: str = "") -> str:
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Schreibe einen viralen TikTok Caption (max 150 Zeichen) auf Englisch über: {topic or 'KI-Business Automatisierung'}. "
            f"Füge 3-5 relevante Hashtags hinzu. Affiliate: {DS24}"
        )
        return await ai_complete(prompt, max_tokens=100)
    except Exception:
        return f"🚀 Automate your business with AI! {DS24} #business #automation #ecommerce #ai #money"


async def run_tiktok_cycle() -> dict:
    """Scheduler entry point: generate content, report status."""
    status = await get_status()
    if not status["configured"]:
        caption = await generate_caption()
        log.info("TikTok caption generated (no token yet): %s", caption[:60])
        return {
            "ok": True,
            "action": "content_generated",
            "caption": caption,
            "note": "Set TIKTOK_ACCESS_TOKEN to enable posting",
        }
    user = await get_user_info()
    caption = await generate_caption()
    log.info("TikTok cycle: user=%s caption=%s", user, caption[:60])
    return {"ok": True, "user": user, "caption": caption, "status": status}
