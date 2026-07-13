#!/usr/bin/env python3
"""
TikTok Content Posting & Analytics — SuperMegaBot
API v2: Content Posting API + Login Kit
Sandbox: sbaw5uysvdzyc9p5me / Scopes: user.info.basic, video.list, video.publish (nach Freischaltung)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("TikTokSync")

BASE           = "https://open.tiktokapis.com/v2"
CLIENT_KEY     = os.getenv("TIKTOK_CLIENT_KEY", os.getenv("TIKTOK_APP_KEY", ""))
CLIENT_SECRET  = os.getenv("TIKTOK_CLIENT_SECRET", os.getenv("TIKTOK_APP_SECRET", ""))
_ACCESS_TOKEN  = os.getenv("TIKTOK_ACCESS_TOKEN", "")
_REFRESH_TOKEN = os.getenv("TIKTOK_REFRESH_TOKEN", "")
OPEN_ID        = os.getenv("TIKTOK_OPEN_ID", "")
DS24_LINK      = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
SHOP_DOMAIN    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")

_token_cache: dict = {}


def _headers(token: str = "") -> dict:
    tok = token or _token_cache.get("access_token") or _ACCESS_TOKEN
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


async def _refresh_token() -> str:
    """Erneuert den Access Token via Refresh Token. Gibt neuen Token zurück."""
    if not CLIENT_KEY or not CLIENT_SECRET or not _REFRESH_TOKEN:
        return _ACCESS_TOKEN

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": CLIENT_KEY,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": _REFRESH_TOKEN,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()

    new_token = data.get("access_token", "")
    new_refresh = data.get("refresh_token", "")
    if new_token:
        _token_cache["access_token"] = new_token
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 86400)
        if new_refresh:
            _token_cache["refresh_token"] = new_refresh
        log.info("TikTok token refreshed (expires in %ds)", data.get("expires_in", 86400))
    return new_token or _ACCESS_TOKEN


async def _get_token() -> str:
    """Gibt gültigen Token zurück — refresht automatisch wenn nötig."""
    cached = _token_cache.get("access_token")
    expires_at = _token_cache.get("expires_at", 0)
    if cached and time.time() < expires_at - 300:
        return cached
    if _REFRESH_TOKEN and CLIENT_KEY:
        return await _refresh_token()
    return _ACCESS_TOKEN


async def get_user_info() -> dict:
    """Liest Profil-Daten des verbundenen TikTok Accounts."""
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "kein TikTok Token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/user/info/",
                headers=_headers(token),
                params={"fields": "open_id,display_name,avatar_url,union_id"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            return {"ok": False, "error": data["error"].get("message")}
        return {"ok": True, "user": data.get("data", {}).get("user", {})}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_videos(max_count: int = 10) -> dict:
    """Listet eigene TikTok Videos mit Stats."""
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "kein TikTok Token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/video/list/",
                headers=_headers(token),
                params={"fields": "id,title,video_description,duration,view_count,like_count,comment_count,share_count,create_time,cover_image_url"},
                json={"max_count": min(max_count, 20)},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            return {"ok": False, "error": data["error"].get("message")}
        videos = data.get("data", {}).get("videos", [])
        return {"ok": True, "videos": videos, "count": len(videos)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_video_from_url(video_url: str, title: str, description: str = "",
                               privacy: str = "SELF_ONLY", disable_comments: bool = False) -> dict:
    """
    Postet ein Video via Content Posting API (Pull-from-URL Methode).
    Benötigt Scope: video.publish
    privacy: PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR | SELF_ONLY
    """
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "kein TikTok Token"}

    payload = {
        "post_info": {
            "title": title[:2200],
            "description": description[:2200] if description else title[:2200],
            "disable_comment": disable_comments,
            "privacy_level": privacy,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/post/publish/video/init/",
                headers=_headers(token),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                data = await r.json()
        if data.get("error", {}).get("code") not in (None, "ok"):
            err = data.get("error", {})
            if "scope" in err.get("message", "").lower() or err.get("code") == "scope_not_authorized":
                return {
                    "ok": False,
                    "error": "scope_not_authorized",
                    "hint": "video.publish Scope fehlt! Im TikTok Developer Portal: Products → Content Posting API hinzufügen → Scope video.publish aktivieren",
                }
            return {"ok": False, "error": err.get("message", str(data))}
        pub_id = data.get("data", {}).get("publish_id", "")
        return {"ok": True, "publish_id": pub_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_publish_status(publish_id: str) -> dict:
    """Prüft den Status eines geposteten Videos."""
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "kein Token"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/post/publish/status/fetch/",
                headers=_headers(token),
                json={"publish_id": publish_id},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        return {"ok": True, "data": data.get("data", {})}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def generate_video_caption(topic: str = "", product_name: str = "",
                                  product_url: str = "", lang: str = "de") -> str:
    """AI-generierter viraler Caption mit CTA und Hashtags."""
    try:
        from modules.ai_client import ai_complete
        if lang == "de":
            prompt = (
                f"Schreibe einen viralen TikTok-Text (max 200 Zeichen) auf Deutsch über: "
                f"{topic or product_name or 'KI-Business Automatisierung'}. "
                f"Inklusive 3-5 Hashtags. Keine Einkommensversprechen. "
                f"{'CTA: ' + product_url if product_url else ''}"
            )
        else:
            prompt = (
                f"Write a viral TikTok caption (max 200 chars) in English about: "
                f"{topic or product_name or 'AI Business Automation'}. "
                f"Include 3-5 hashtags. No income claims. "
                f"{'CTA: ' + product_url if product_url else ''}"
            )
        return await ai_complete(prompt, max_tokens=120)
    except Exception:
        tags = "#KIBusiness #Automatisierung #OnlineShop #Shopify #ECommerce"
        return f"🚀 Mit KI das Business automatisieren! {product_url or DS24_LINK} {tags}"


async def _tg_notify(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def get_status() -> dict:
    token = await _get_token()
    return {
        "configured": bool(token),
        "client_key": CLIENT_KEY[:8] + "..." if CLIENT_KEY else "",
        "open_id": OPEN_ID,
        "sandbox": True,
        "scopes_active": ["user.info.basic", "video.list"],
        "scopes_needed": ["video.publish", "video.upload"],
        "posting_ready": False,
        "note": "Content Posting API im TikTok Developer Portal aktivieren → Scope video.publish hinzufügen",
    }


async def run_tiktok_cycle() -> dict:
    """Scheduler: Token refreshen, Stats holen, Content vorbereiten."""
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "kein TikTok Token konfiguriert"}

    user = await get_user_info()
    videos = await get_videos(max_count=5)
    caption = await generate_video_caption(topic="Smart Home Gadgets E-Commerce")

    result = {
        "ok": True,
        "user": user.get("user", {}),
        "video_count": videos.get("count", 0),
        "top_video": None,
        "caption_ready": caption,
    }

    vids = videos.get("videos", [])
    if vids:
        top = max(vids, key=lambda v: v.get("view_count", 0))
        result["top_video"] = {
            "id": top.get("id"),
            "title": top.get("title", "")[:60],
            "views": top.get("view_count", 0),
            "likes": top.get("like_count", 0),
        }

    display = user.get("user", {}).get("display_name", "AIITEC")
    msg = (
        f"📱 *TikTok Cycle* — @{display}\n"
        f"Videos: {videos.get('count', 0)}\n"
        f"{'Top: ' + result['top_video']['title'] + ' (' + str(result['top_video']['views']) + ' Views)' if result['top_video'] else ''}\n"
        f"Caption bereit: _{caption[:100]}_"
    )
    await _tg_notify(msg)
    return result
