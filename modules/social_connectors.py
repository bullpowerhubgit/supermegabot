#!/usr/bin/env python3
"""Unified Social Media Connectors — async, credential-safe, mock-capable."""

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
            return {"mock": True, "publish_id": "mock_publish_id_001", "title": title}
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
            return {
                "mock": True,
                "follower_count": 12_500,
                "video_count": 87,
                "platform": "tiktok",
            }
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
            return {
                "mock": True,
                "id": "mock_pin_id_001",
                "title": title,
                "board_id": board,
            }
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
            return {
                "mock": True,
                "items": [
                    {"id": "mock_board_1", "name": "Moodboard"},
                    {"id": "mock_board_2", "name": "Products"},
                ],
            }
        url = f"{self.BASE}/boards"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status in (401, 403):
                    return {"error": f"HTTP {resp.status}", "platform": "pinterest"}
                return await resp.json()

    async def get_analytics(self) -> Dict[str, Any]:
        if not self.access_token:
            return {
                "mock": True,
                "impressions": 45_200,
                "saves": 1_340,
                "clicks": 980,
                "platform": "pinterest",
            }
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
            return {
                "mock": True,
                "id": "mock_ig_media_001",
                "caption": caption,
                "platform": "instagram",
            }
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
            return {
                "mock": True,
                "id": "mock_fb_post_001",
                "message": message,
                "platform": "facebook",
            }
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
            return {
                "mock": True,
                "impressions": 98_700,
                "reach": 54_100,
                "follower_count": 8_200,
                "platform": "instagram",
            }
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

    def _has_creds(self) -> bool:
        return bool(self.client_id and self.client_secret and self.username and self.password)

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
            return {
                "mock": True,
                "id": "mock_reddit_post_001",
                "subreddit": subreddit,
                "title": title,
                "platform": "reddit",
            }
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
            return {
                "mock": True,
                "posts": [
                    {"title": f"Mock Post {i+1}", "score": (10 - i) * 100, "id": f"mock_{i}"}
                    for i in range(min(limit, 3))
                ],
                "subreddit": subreddit,
            }
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
            return {
                "mock": True,
                "viewCount": "1250000",
                "subscriberCount": "34700",
                "videoCount": "312",
                "platform": "youtube",
            }
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
            return {
                "mock": True,
                "items": [
                    {
                        "id": {"videoId": "mock_vid_001"},
                        "snippet": {"title": f"Mock Video — {query}"},
                    }
                ],
            }
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
            return {
                "mock": True,
                "region": region_code,
                "items": [
                    {
                        "id": "mock_trending_001",
                        "snippet": {"title": "Mock Trending Video"},
                    }
                ],
            }
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
            return {
                "mock": True,
                "id": "mock_tweet_001",
                "text": text,
                "platform": "twitter",
            }
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
            return {
                "mock": True,
                "data": [
                    {"id": f"mock_mention_{i}", "text": f"Mock mention #{i+1}"}
                    for i in range(min(max_results, 3))
                ],
            }
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
            return {
                "mock": True,
                "data": [
                    {
                        "id": f"mock_tweet_{i}",
                        "text": f"Mock tweet about '{query}' #{i+1}",
                    }
                    for i in range(min(max_results, 3))
                ],
            }
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
            if not self.webhook_url:
                return {
                    "mock": True,
                    "id": "mock_discord_msg_001",
                    "content": content,
                }
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
            return {
                "mock": True,
                "id": "mock_discord_msg_001",
                "content": content,
                "platform": "discord",
            }
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
            if not self.webhook_url:
                return {
                    "mock": True,
                    "embed_title": title,
                    "platform": "discord",
                }
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
            return {
                "mock": True,
                "embed_title": title,
                "platform": "discord",
            }
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
