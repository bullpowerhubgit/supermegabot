#!/usr/bin/env python3
"""Unified Social Media Connectors — async, credential-safe."""

import os
import json
import logging
import base64
from typing import Dict, List, Optional, Tuple, Any

import aiohttp

log = logging.getLogger("SocialConnectors")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# 1. TikTok
# ---------------------------------------------------------------------------

class TikTokConnector:
    BASE = "https://open.tiktokapis.com/v2"

    def __init__(self) -> None:
        self.client_key = _env("TIKTOK_CLIENT_KEY")
        self.client_secret = _env("TIKTOK_CLIENT_SECRET")
        self.access_token = _env("TIKTOK_ACCESS_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    async def ping(self) -> Tuple[bool, str]:
        if not self.access_token:
            return False, "Kein API-Key konfiguriert (TIKTOK_ACCESS_TOKEN)"
        url = f"{self.BASE}/user/info/?fields=display_name"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status in (401, 403):
                        return False, f"TikTok auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    name = data.get("data", {}).get("user", {}).get("display_name", "?")
                    return True, f"TikTok verbunden — @{name}"
        except Exception as exc:
            return False, f"TikTok Fehler: {str(exc)[:80]}"

    async def post_video(
        self,
        title: str,
        video_url: str,
        privacy: str = "PUBLIC_TO_EVERYONE",
    ) -> Dict[str, Any]:
        if not self.access_token:
            return {"available": False, "reason": "TIKTOK_ACCESS_TOKEN not set"}
        url = f"{self.BASE}/post/publish/video/init/"
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": video_url,
            },
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._headers(), json=payload) as resp:
                return await resp.json()

    async def get_stats(self) -> Dict[str, Any]:
        if not self.access_token:
            return {"available": False, "reason": "TIKTOK_ACCESS_TOKEN not set", "platform": "tiktok"}
        url = f"{self.BASE}/research/adlib/ad/detail/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "tiktok"}
                return await resp.json()


# ---------------------------------------------------------------------------
# 2. Pinterest
# ---------------------------------------------------------------------------

class PinterestConnector:
    BASE = "https://api.pinterest.com/v5"

    def __init__(self) -> None:
        self.access_token = _env("PINTEREST_ACCESS_TOKEN")
        self.default_board_id = _env("PINTEREST_BOARD_ID")

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def ping(self) -> Tuple[bool, str]:
        if not self.access_token:
            return False, "Kein API-Key konfiguriert (PINTEREST_ACCESS_TOKEN)"
        url = f"{self.BASE}/user_account"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status in (401, 403):
                        return False, f"Pinterest auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    username = data.get("username", "?")
                    return True, f"Pinterest verbunden — @{username}"
        except Exception as exc:
            return False, f"Pinterest Fehler: {str(exc)[:80]}"

    async def create_pin(
        self,
        title: str,
        description: str,
        image_url: str,
        link: str,
        board_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        board = board_id or self.default_board_id
        if not self.access_token:
            return {"available": False, "reason": "PINTEREST_ACCESS_TOKEN not set"}
        url = f"{self.BASE}/pins"
        payload = {
            "title": title,
            "description": description,
            "board_id": board,
            "link": link,
            "media_source": {"source_type": "image_url", "url": image_url},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._headers(), json=payload) as resp:
                return await resp.json()

    async def get_boards(self) -> Dict[str, Any]:
        if not self.access_token:
            return {"available": False, "reason": "PINTEREST_ACCESS_TOKEN not set"}
        url = f"{self.BASE}/boards"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "pinterest"}
                return await resp.json()

    async def get_analytics(self) -> Dict[str, Any]:
        if not self.access_token:
            return {"available": False, "reason": "PINTEREST_ACCESS_TOKEN not set", "platform": "pinterest"}
        url = f"{self.BASE}/user_account/analytics"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "pinterest"}
                return await resp.json()


# ---------------------------------------------------------------------------
# 3. Meta (Instagram + Facebook)
# ---------------------------------------------------------------------------

class MetaConnector:
    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self) -> None:
        self.access_token = _env("META_ACCESS_TOKEN")
        self.page_id = _env("META_PAGE_ID")
        self.ig_account_id = _env("INSTAGRAM_ACCOUNT_ID")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.page_id)

    def _params(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        p: Dict[str, str] = {"access_token": self.access_token}
        if extra:
            p.update(extra)
        return p

    async def ping(self) -> Tuple[bool, str]:
        if not self.access_token or not self.page_id:
            return False, "Kein API-Key konfiguriert (META_ACCESS_TOKEN / META_PAGE_ID)"
        url = f"{self.BASE}/{self.page_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=self._params({"fields": "name,followers_count"}),
                ) as resp:
                    if resp.status in (401, 403):
                        return False, f"Meta auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    name = data.get("name", "?")
                    followers = data.get("followers_count", "?")
                    return True, f"Meta verbunden — {name} ({followers} Follower)"
        except Exception as exc:
            return False, f"Meta Fehler: {str(exc)[:80]}"

    async def post_photo(self, image_url: str, caption: str) -> Dict[str, Any]:
        if not self.access_token or not self.ig_account_id:
            return {"available": False, "reason": "META_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not set", "platform": "instagram"}
        # Step 1 — create container
        create_url = f"{self.BASE}/{self.ig_account_id}/media"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                create_url,
                params=self._params({"image_url": image_url, "caption": caption}),
            ) as resp:
                container = await resp.json()
                container_id = container.get("id")
                if not container_id:
                    return container

            # Step 2 — publish
            publish_url = f"{self.BASE}/{self.ig_account_id}/media_publish"
            async with session.post(
                publish_url,
                params=self._params({"creation_id": container_id}),
            ) as resp:
                return await resp.json()

    async def post_fb_page(self, message: str, link: str = "") -> Dict[str, Any]:
        if not self.access_token or not self.page_id:
            return {"available": False, "reason": "META_ACCESS_TOKEN or META_PAGE_ID not set", "platform": "facebook"}
        url = f"{self.BASE}/{self.page_id}/feed"
        payload: Dict[str, str] = {"message": message}
        if link:
            payload["link"] = link
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, params=self._params(), data=payload
            ) as resp:
                return await resp.json()

    async def get_insights(self) -> Dict[str, Any]:
        if not self.access_token or not self.ig_account_id:
            return {"available": False, "reason": "META_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not set", "platform": "instagram"}
        url = f"{self.BASE}/{self.ig_account_id}/insights"
        params = self._params(
            {
                "metric": "impressions,reach,follower_count",
                "period": "day",
            }
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "instagram"}
                return await resp.json()


# ---------------------------------------------------------------------------
# 4. Reddit
# ---------------------------------------------------------------------------

class RedditConnector:
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    BASE = "https://oauth.reddit.com"

    def __init__(self) -> None:
        self.client_id = _env("REDDIT_CLIENT_ID")
        self.client_secret = _env("REDDIT_CLIENT_SECRET")
        self.username = _env("REDDIT_USERNAME")
        self.password = _env("REDDIT_PASSWORD")
        self.user_agent = _env("REDDIT_USER_AGENT", "SuperMegaBot/1.0")
        self._token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.username and self.password)

    def _has_creds(self) -> bool:
        return self.is_configured()

    async def _get_token(self) -> Optional[str]:
        if self._token:
            return self._token
        creds = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {creds}",
            "User-Agent": self.user_agent,
        }
        data = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, headers=headers, data=data) as resp:
                if resp.status != 200:
                    return None
                result = await resp.json()
                self._token = result.get("access_token")
                return self._token

    def _headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"bearer {token}",
            "User-Agent": self.user_agent,
        }

    async def ping(self) -> Tuple[bool, str]:
        if not self._has_creds():
            return False, "Kein API-Key konfiguriert (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET)"
        token = await self._get_token()
        if not token:
            return False, "Reddit OAuth-Token konnte nicht abgerufen werden"
        url = f"{self.BASE}/api/v1/me"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers(token)) as resp:
                    if resp.status in (401, 403):
                        return False, f"Reddit auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    name = data.get("name", "?")
                    karma = data.get("total_karma", 0)
                    return True, f"Reddit verbunden — u/{name} (Karma: {karma})"
        except Exception as exc:
            return False, f"Reddit Fehler: {str(exc)[:80]}"

    async def submit_post(
        self,
        subreddit: str,
        title: str,
        text: str = "",
        url: str = "",
        flair: str = "",
    ) -> Dict[str, Any]:
        if not self._has_creds():
            return {"available": False, "reason": "REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD not set", "platform": "reddit"}
        token = await self._get_token()
        if not token:
            return {"error": "token_error", "platform": "reddit"}
        api_url = f"{self.BASE}/api/submit"
        kind = "link" if url else "self"
        payload: Dict[str, Any] = {
            "sr": subreddit,
            "title": title,
            "kind": kind,
            "resubmit": True,
            "nsfw": False,
            "spoiler": False,
        }
        if text:
            payload["text"] = text
        if url:
            payload["url"] = url
        if flair:
            payload["flair_text"] = flair
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url, headers=self._headers(token), data=payload
            ) as resp:
                return await resp.json()

    async def get_subreddit_posts(
        self, subreddit: str, limit: int = 10
    ) -> Dict[str, Any]:
        if not self._has_creds():
            return {"available": False, "reason": "REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD not set", "subreddit": subreddit}
        token = await self._get_token()
        if not token:
            return {"error": "token_error", "subreddit": subreddit}
        api_url = f"{self.BASE}/r/{subreddit}/hot.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url,
                headers=self._headers(token),
                params={"limit": str(limit)},
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "subreddit": subreddit}
                return await resp.json()


# ---------------------------------------------------------------------------
# 5. YouTube
# ---------------------------------------------------------------------------

class YouTubeConnector:
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self) -> None:
        self.api_key = _env("YOUTUBE_API_KEY")
        self.channel_id = _env("YOUTUBE_CHANNEL_ID")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def ping(self) -> Tuple[bool, str]:
        if not self.api_key or not self.channel_id:
            return False, "Kein API-Key konfiguriert (YOUTUBE_API_KEY / YOUTUBE_CHANNEL_ID)"
        url = f"{self.BASE}/channels"
        params = {
            "part": "snippet",
            "id": self.channel_id,
            "key": self.api_key,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status in (400, 401, 403):
                        return False, f"YouTube auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    items = data.get("items", [])
                    if not items:
                        return False, "YouTube: Channel nicht gefunden"
                    title = items[0].get("snippet", {}).get("title", "?")
                    return True, f"YouTube verbunden — {title}"
        except Exception as exc:
            return False, f"YouTube Fehler: {str(exc)[:80]}"

    async def get_channel_stats(self) -> Dict[str, Any]:
        if not self.api_key or not self.channel_id:
            return {"available": False, "reason": "YOUTUBE_API_KEY or YOUTUBE_CHANNEL_ID not set", "platform": "youtube"}
        url = f"{self.BASE}/channels"
        params = {"part": "statistics", "id": self.channel_id, "key": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status in (400, 401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "youtube"}
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    return {"error": "channel_not_found", "platform": "youtube"}
                return items[0].get("statistics", {})

    async def search_videos(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        if not self.api_key:
            return {"available": False, "reason": "YOUTUBE_API_KEY not set"}
        url = f"{self.BASE}/search"
        params = {
            "part": "snippet",
            "q": query,
            "maxResults": str(max_results),
            "key": self.api_key,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status in (400, 401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "youtube"}
                return await resp.json()

    async def get_trending(self, region_code: str = "DE") -> Dict[str, Any]:
        if not self.api_key:
            return {"available": False, "reason": "YOUTUBE_API_KEY not set", "region": region_code}
        url = f"{self.BASE}/videos"
        params = {
            "part": "snippet",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": "10",
            "key": self.api_key,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status in (400, 401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "youtube"}
                return await resp.json()


# ---------------------------------------------------------------------------
# 6. Twitter / X
# ---------------------------------------------------------------------------

class TwitterConnector:
    BASE = "https://api.twitter.com/2"

    def __init__(self) -> None:
        self.bearer_token = _env("TWITTER_BEARER_TOKEN")
        self.api_key = _env("TWITTER_API_KEY")
        self.api_secret = _env("TWITTER_API_SECRET")
        self.access_token = _env("TWITTER_ACCESS_TOKEN")
        self.access_secret = _env("TWITTER_ACCESS_SECRET")

    def is_configured(self) -> bool:
        return bool(self.bearer_token)

    def _bearer_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    def _oauth_headers(self) -> Dict[str, str]:
        # For tweet posting, Bearer token is sufficient for app-only read.
        # OAuth 1.0a signing would be required for write; we use the bearer token
        # as a simplification (works for v2 write when user context is set up via OAuth2 PKCE).
        return self._bearer_headers()

    async def ping(self) -> Tuple[bool, str]:
        if not self.bearer_token:
            return False, "Kein API-Key konfiguriert (TWITTER_BEARER_TOKEN)"
        url = f"{self.BASE}/users/me"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._bearer_headers()) as resp:
                    if resp.status in (401, 403):
                        return False, f"Twitter auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    user = data.get("data", {})
                    name = user.get("username", "?")
                    return True, f"Twitter verbunden — @{name}"
        except Exception as exc:
            return False, f"Twitter Fehler: {str(exc)[:80]}"

    async def post_tweet(self, text: str) -> Dict[str, Any]:
        if not self.bearer_token:
            return {"available": False, "reason": "TWITTER_BEARER_TOKEN not set", "platform": "twitter"}
        url = f"{self.BASE}/tweets"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._oauth_headers(), json={"text": text}
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "twitter"}
                return await resp.json()

    async def get_mentions(self, user_id: str, max_results: int = 10) -> Dict[str, Any]:
        if not self.bearer_token:
            return {"available": False, "reason": "TWITTER_BEARER_TOKEN not set"}
        url = f"{self.BASE}/users/{user_id}/mentions"
        params = {"max_results": str(max(5, min(max_results, 100)))}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._bearer_headers(), params=params
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "twitter"}
                return await resp.json()

    async def search_recent(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        if not self.bearer_token:
            return {"available": False, "reason": "TWITTER_BEARER_TOKEN not set"}
        url = f"{self.BASE}/tweets/search/recent"
        params = {
            "query": query,
            "max_results": str(max(10, min(max_results, 100))),
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self._bearer_headers(), params=params
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "twitter"}
                return await resp.json()


# ---------------------------------------------------------------------------
# 7. Discord
# ---------------------------------------------------------------------------

class DiscordConnector:
    BASE = "https://discord.com/api/v10"

    def __init__(self) -> None:
        self.bot_token = _env("DISCORD_BOT_TOKEN")
        self.default_channel_id = _env("DISCORD_CHANNEL_ID")
        self.webhook_url = _env("DISCORD_WEBHOOK_URL")

    def is_configured(self) -> bool:
        return bool(self.bot_token or self.webhook_url)

    def _bot_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json",
        }

    async def ping(self) -> Tuple[bool, str]:
        # Prefer webhook check (no auth needed), fall back to gateway
        if self.webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.webhook_url) as resp:
                        if resp.status in (401, 403):
                            return False, f"Discord Webhook ungültig (HTTP {resp.status})"
                        data = await resp.json()
                        wh_name = data.get("name", "?")
                        return True, f"Discord Webhook verbunden — #{wh_name}"
            except Exception as exc:
                return False, f"Discord Webhook Fehler: {str(exc)[:80]}"

        if not self.bot_token:
            return False, "Kein API-Key konfiguriert (DISCORD_BOT_TOKEN / DISCORD_WEBHOOK_URL)"

        url = f"{self.BASE}/gateway"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._bot_headers()) as resp:
                    if resp.status in (401, 403):
                        return False, f"Discord Bot auth fehlgeschlagen (HTTP {resp.status})"
                    data = await resp.json()
                    gateway = data.get("url", "?")
                    return True, f"Discord verbunden — Gateway: {gateway}"
        except Exception as exc:
            return False, f"Discord Fehler: {str(exc)[:80]}"

    async def send_message(
        self,
        content: str,
        channel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        channel = channel_id or self.default_channel_id

        # Use webhook if available and no explicit channel override
        if self.webhook_url and not channel_id:
            payload = {"content": content}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    params={"wait": "true"},
                ) as resp:
                    if resp.status in (400, 401, 403):
                        return {"error": f"HTTP {resp.status}", "platform": "discord"}
                    return await resp.json() if resp.content_length else {"ok": True}

        if not self.bot_token or not channel:
            return {"available": False, "reason": "DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID not set", "platform": "discord"}
        url = f"{self.BASE}/channels/{channel}/messages"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._bot_headers(), json={"content": content}
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "discord"}
                return await resp.json()

    async def send_embed(
        self,
        title: str,
        description: str,
        color: int = 0x3498DB,
        fields: Optional[List[Dict[str, Any]]] = None,
        channel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        embed: Dict[str, Any] = {
            "title": title,
            "description": description,
            "color": color,
        }
        if fields:
            embed["fields"] = fields

        channel = channel_id or self.default_channel_id

        # Webhook path
        if self.webhook_url and not channel_id:
            payload = {"embeds": [embed]}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    params={"wait": "true"},
                ) as resp:
                    if resp.status in (400, 401, 403):
                        return {"error": f"HTTP {resp.status}", "platform": "discord"}
                    return await resp.json() if resp.content_length else {"ok": True}

        if not self.bot_token or not channel:
            return {"available": False, "reason": "DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID not set", "platform": "discord"}
        url = f"{self.BASE}/channels/{channel}/messages"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=self._bot_headers(), json={"embeds": [embed]}
            ) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "discord"}
                return await resp.json()


# ---------------------------------------------------------------------------
# Registry & convenience
# ---------------------------------------------------------------------------

CONNECTORS: Dict[str, type] = {
    "tiktok": TikTokConnector,
    "pinterest": PinterestConnector,
    "meta": MetaConnector,
    "reddit": RedditConnector,
    "youtube": YouTubeConnector,
    "twitter": TwitterConnector,
    "discord": DiscordConnector,
}


async def ping_all() -> Dict[str, Dict]:
    """Ping all connectors, return status dict."""
    results: Dict[str, Dict] = {}
    for name, cls in CONNECTORS.items():
        try:
            connected, info = await cls().ping()
            results[name] = {"connected": connected, "info": info}
        except Exception as exc:
            results[name] = {"connected": False, "info": str(exc)[:80]}
    return results


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        print("Pinging all social connectors …\n")
        statuses = await ping_all()
        for platform, status in statuses.items():
            icon = "✓" if status["connected"] else "✗"
            print(f"  [{icon}] {platform:12s}  {status['info']}")

    asyncio.run(_main())


# ---------------------------------------------------------------------------
# Maximum-Setup: Cross-Platform Scheduler + AI Content Tools
# ---------------------------------------------------------------------------

import asyncio as _sc_asyncio
import datetime as _sc_dt
import os as _sc_os
import re as _sc_re
import logging as _sc_log

_sclog = _sc_log.getLogger("SocialConnectors.Max")


async def schedule_post(
    content: str,
    platforms: list,
    scheduled_for: str,
    image_url: str = "",
    link: str = "",
) -> dict:
    """Schedule a post across multiple social platforms simultaneously.

    Posts are published immediately if scheduled_for is in the past or within 60s.
    Otherwise returns a scheduled task dict (requires an external job runner to
    actually fire it at the right time — integrates with automation_scheduler).

    Args:
        content:        Post text
        platforms:      List of platform names: ["tiktok", "meta", "twitter", "discord", "reddit", "pinterest"]
        scheduled_for:  ISO datetime string "2026-06-10T15:00:00" (local time)
        image_url:      Optional image URL (used for Instagram/Pinterest)
        link:           Optional link (Reddit/Twitter)

    Returns:
        {"ok": True, "scheduled_at": str, "results": {platform: result}}
    """
    try:
        scheduled_dt = _sc_dt.datetime.fromisoformat(scheduled_for)
    except ValueError:
        return {"ok": False, "error": f"Invalid scheduled_for format: {scheduled_for}. Use ISO: YYYY-MM-DDTHH:MM:SS"}

    now = _sc_dt.datetime.now()
    delay_seconds = (scheduled_dt - now).total_seconds()

    async def _publish_now() -> dict:
        connectors_map = {
            "tiktok":    TikTokConnector(),
            "meta":      MetaConnector(),
            "twitter":   TwitterConnector(),
            "discord":   DiscordConnector(),
            "reddit":    RedditConnector(),
            "pinterest": PinterestConnector(),
        }
        results = {}
        tasks = []

        async def _post_to(platform: str) -> None:
            c = connectors_map.get(platform)
            if not c:
                results[platform] = {"error": "unknown platform"}
                return
            try:
                if platform == "tiktok":
                    if image_url:
                        r = await c.post_video(title=content[:150], video_url=image_url)
                    else:
                        r = {"skipped": True, "reason": "TikTok requires video_url"}
                elif platform == "meta":
                    if image_url:
                        r = await c.post_photo(image_url=image_url, caption=content)
                    else:
                        r = await c.post_fb_page(message=content, link=link)
                elif platform == "twitter":
                    text = content[:280]
                    if link:
                        text = f"{text[:277-len(link)]} {link}"
                    r = await c.post_tweet(text)
                elif platform == "discord":
                    r = await c.send_message(content)
                elif platform == "reddit":
                    r = await c.submit_post(
                        subreddit=_sc_os.getenv("REDDIT_DEFAULT_SUBREDDIT", "test"),
                        title=content[:300],
                        url=link or "",
                        text=content if not link else "",
                    )
                elif platform == "pinterest":
                    r = await c.create_pin(
                        title=content[:100],
                        description=content,
                        image_url=image_url,
                        link=link or "https://supermegabot.com",
                    )
                else:
                    r = {"error": "platform not implemented"}
                results[platform] = r
            except Exception as exc:
                results[platform] = {"error": str(exc)[:120]}

        for p in platforms:
            tasks.append(_post_to(p))

        await _sc_asyncio.gather(*tasks)
        return results

    if delay_seconds <= 60:
        # Publish immediately
        _sclog.info("Publishing now to %d platforms: %s", len(platforms), platforms)
        results = await _publish_now()
        return {
            "ok":           True,
            "mode":         "immediate",
            "scheduled_at": scheduled_for,
            "platforms":    platforms,
            "results":      results,
        }
    else:
        # Return scheduled task descriptor; caller should store and execute later
        _sclog.info("Scheduled post for %s on %s (in %.0fs)", scheduled_for, platforms, delay_seconds)
        return {
            "ok":            True,
            "mode":          "scheduled",
            "scheduled_at":  scheduled_for,
            "delay_seconds": int(delay_seconds),
            "platforms":     platforms,
            "content":       content[:200],
            "image_url":     image_url,
            "link":          link,
            "note":          "Store this dict and execute via automation_scheduler at scheduled_at",
        }


async def get_best_posting_times(platform: str = "all") -> dict:
    """AI analysis of optimal posting times for maximum engagement.

    Uses Claude/OpenAI to recommend posting windows based on platform best practices
    and niche (e-commerce / SaaS). Falls back to evidence-based static data
    if no AI key is available.

    Args:
        platform: "tiktok", "instagram", "twitter", "facebook", "all"

    Returns:
        {"ok": True, "recommendations": {platform: [{"day": str, "hours": [...], "reason": str}]}}
    """
    # Evidence-based defaults (used as fallback + context)
    static_recommendations = {
        "tiktok":    [
            {"day": "Tuesday",   "hours": [9, 19, 21], "reason": "Highest TikTok engagement mid-morning and evening"},
            {"day": "Thursday",  "hours": [12, 19, 21], "reason": "Peak TikTok watch time on Thursdays"},
            {"day": "Friday",    "hours": [17, 20, 22], "reason": "Weekend wind-down browsing starts Friday evening"},
        ],
        "instagram": [
            {"day": "Wednesday", "hours": [11, 15], "reason": "Instagram peak: Wednesday 11am and 3pm"},
            {"day": "Friday",    "hours": [10, 11], "reason": "Friday morning scroll before work"},
            {"day": "Saturday",  "hours": [9, 11],  "reason": "Weekend morning browsing"},
        ],
        "twitter":   [
            {"day": "Tuesday",  "hours": [8, 9, 10],   "reason": "B2B Twitter peaks Tuesday-Thursday morning"},
            {"day": "Wednesday", "hours": [8, 9, 10],   "reason": "Midweek engagement highest"},
            {"day": "Thursday",  "hours": [8, 9, 10],   "reason": "Pre-weekend decision-making peak"},
        ],
        "facebook":  [
            {"day": "Wednesday", "hours": [13, 14, 15], "reason": "Facebook lunch-hour peak"},
            {"day": "Thursday",  "hours": [8, 12, 13], "reason": "B2C Facebook peaks Thursday"},
            {"day": "Friday",    "hours": [13, 14],    "reason": "TGIF social media browsing spike"},
        ],
    }

    anthropic_key = _sc_os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = _sc_os.getenv("OPENAI_API_KEY", "")

    if not anthropic_key and not openai_key:
        # Return static recommendations
        if platform == "all":
            return {"ok": True, "source": "static", "recommendations": static_recommendations}
        return {"ok": True, "source": "static", "recommendations": {platform: static_recommendations.get(platform, [])}}

    # Use AI for personalised recommendations
    target_platforms = list(static_recommendations.keys()) if platform == "all" else [platform]
    prompt = (
        f"Du bist Social-Media-Experte für E-Commerce / SaaS (DACH-Markt).\n"
        f"Analysiere optimale Posting-Zeiten für folgende Plattformen: {', '.join(target_platforms)}.\n"
        f"Zielgruppe: E-Commerce-Unternehmer, Online-Marketer, 25-45 Jahre, DACH-Region.\n\n"
        f"Antworte als JSON:\n"
        f'{{"recommendations": {{'
        f'"platform_name": [{{"day": "Monday", "hours": [9, 15, 19], "reason": "Begründung"}}]'
        f"}}}}"
    )

    try:
        import aiohttp as _ah
        if anthropic_key:
            async with _ah.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-3-5-haiku-20241022", "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]},
                    timeout=_ah.ClientTimeout(total=30),
                ) as r:
                    d = await r.json(content_type=None)
            raw = d.get("content", [{}])[0].get("text", "")
        else:
            async with _ah.ClientSession() as s:
                async with s.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024},
                    timeout=_ah.ClientTimeout(total=30),
                ) as r:
                    d = await r.json(content_type=None)
            raw = d.get("choices", [{}])[0].get("message", {}).get("content", "")

        import json
        m = _sc_re.search(r'\{[\s\S]*\}', raw)
        if m:
            parsed = json.loads(m.group())
            ai_recs = parsed.get("recommendations", {})
            if ai_recs:
                return {"ok": True, "source": "ai", "recommendations": ai_recs}
    except Exception as exc:
        _sclog.warning("get_best_posting_times AI call failed: %s — using static data", exc)

    # Fallback to static
    if platform == "all":
        return {"ok": True, "source": "static_fallback", "recommendations": static_recommendations}
    return {"ok": True, "source": "static_fallback", "recommendations": {platform: static_recommendations.get(platform, [])}}


async def create_viral_hook(
    product_or_topic: str,
    platform: str = "tiktok",
    style: str = "curiosity",
) -> dict:
    """Generate viral content hooks for TikTok/Instagram Reels/Twitter.

    Hooks are the opening 1-2 sentences that stop the scroll.

    Args:
        product_or_topic: Product name or topic to create hooks for
        platform:         "tiktok", "instagram", "twitter", "facebook"
        style:            "curiosity" | "shock" | "benefit" | "story" | "controversy"

    Returns:
        {"ok": True, "hooks": [{"hook": str, "style": str, "explanation": str}]}
    """
    anthropic_key = _sc_os.getenv("ANTHROPIC_API_KEY", "")
    openai_key    = _sc_os.getenv("OPENAI_API_KEY", "")

    style_descriptions = {
        "curiosity":    "Neugier wecken, Fragen aufwerfen die man beantworten will",
        "shock":        "Überraschendes Statement, das widerspricht was man erwartet",
        "benefit":      "Klarer konkreter Nutzen in Sekunden kommuniziert",
        "story":        "Persönliche Geschichte die sofort eine Verbindung schafft",
        "controversy":  "Kontroverser oder provokanter Einstieg der polarisiert",
    }

    style_desc = style_descriptions.get(style, style_descriptions["curiosity"])
    platform_limits = {"tiktok": 150, "instagram": 125, "twitter": 200, "facebook": 200}
    char_limit = platform_limits.get(platform, 150)

    # Fallback hooks if no AI available
    fallback_hooks = [
        {"hook": f"Ich hab {product_or_topic} 30 Tage lang getestet — das hätte ich nie erwartet...", "style": "curiosity", "explanation": "Neugier durch unerwartetes Ergebnis"},
        {"hook": f"99% der {platform}-Nutzer machen diesen Fehler mit {product_or_topic} #viral", "style": "shock", "explanation": "Shock-Faktor durch Statistik"},
        {"hook": f"So sparst du mit {product_or_topic} 10 Stunden pro Woche (ernsthaft)", "style": "benefit", "explanation": "Konkreter quantifizierter Nutzen"},
    ]

    if not anthropic_key and not openai_key:
        return {"ok": True, "source": "fallback", "hooks": fallback_hooks, "platform": platform}

    prompt = (
        f"Erstelle 5 virale Content-Hooks auf Deutsch für {platform.upper()} zum Thema: \"{product_or_topic}\".\n"
        f"Hook-Style: {style} — {style_desc}\n"
        f"Max. {char_limit} Zeichen pro Hook.\n"
        f"Die Hooks sollen den Scroll SOFORT stoppen.\n\n"
        f'Antworte als JSON:\n{{"hooks": [{{"hook": "...", "style": "{style}", "explanation": "warum viral"}}]}}'
    )

    try:
        import aiohttp as _ah, json
        if anthropic_key:
            async with _ah.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-3-5-haiku-20241022", "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]},
                    timeout=_ah.ClientTimeout(total=30),
                ) as r:
                    d = await r.json(content_type=None)
            raw = d.get("content", [{}])[0].get("text", "")
        else:
            async with _ah.ClientSession() as s:
                async with s.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024},
                    timeout=_ah.ClientTimeout(total=30),
                ) as r:
                    d = await r.json(content_type=None)
            raw = d.get("choices", [{}])[0].get("message", {}).get("content", "")

        m = _sc_re.search(r'\{[\s\S]*\}', raw)
        if m:
            parsed = json.loads(m.group())
            hooks = parsed.get("hooks", [])
            if hooks:
                _sclog.info("Generated %d viral hooks for '%s' on %s", len(hooks), product_or_topic, platform)
                return {"ok": True, "source": "ai", "hooks": hooks, "platform": platform, "style": style}
    except Exception as exc:
        _sclog.warning("create_viral_hook AI failed: %s — using fallback", exc)

    return {"ok": True, "source": "fallback", "hooks": fallback_hooks, "platform": platform}
