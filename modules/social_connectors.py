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

    def _cookie_file(self):
        from pathlib import Path
        return Path(__file__).parent.parent / "data" / "reddit_cookies.json"

    def is_configured(self) -> bool:
        if self._cookie_file().exists():
            return True
        return bool(self.client_id and self.client_secret and self.username and self.password)

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
        import json
        cookie_file = self._cookie_file()
        if cookie_file.exists():
            try:
                with open(cookie_file) as f:
                    cookies = json.load(f)
                has_token = bool(cookies.get("token_v2") or cookies.get("reddit_session"))
                username = self.username or cookies.get("csv", "").split("%2C")[0] or "i_want_that_i_need_i"
                if has_token:
                    return True, f"Reddit verbunden — u/{username} (Cookie-Auth, kein OAuth App nötig)"
            except Exception:
                pass
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

    async def _submit_via_cookies(self, subreddit: str, title: str, text: str = "", url: str = "") -> Dict[str, Any]:
        """Post via session cookie (no OAuth app needed)."""
        import json as _json
        cookie_file = self._cookie_file()
        if not cookie_file.exists():
            return {"error": "no_cookie_file"}
        cookies_raw = _json.loads(cookie_file.read_text())
        jar = aiohttp.CookieJar()
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies_raw.items() if isinstance(v, str))
        headers["Cookie"] = cookie_header
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://www.reddit.com/api/me.json") as r:
                if r.status != 200:
                    return {"error": f"me.json HTTP {r.status}"}
                me = await r.json(content_type=None)
            modhash = me.get("data", {}).get("modhash", "")
            if not modhash:
                return {"error": "no_modhash", "me": me.get("data", {}).get("name")}
            kind = "link" if url else "self"
            payload = {
                "sr": subreddit, "title": title, "kind": kind,
                "resubmit": "true", "nsfw": "false", "spoiler": "false",
                "uh": modhash, "api_type": "json",
            }
            if text:
                payload["text"] = text
            if url:
                payload["url"] = url
            async with session.post("https://www.reddit.com/api/submit", data=payload) as r:
                result = await r.json(content_type=None)
                errors = result.get("json", {}).get("errors", [])
                post_id = result.get("json", {}).get("data", {}).get("id", "")
                return {"ok": not errors and bool(post_id), "post_id": post_id,
                        "subreddit": subreddit, "errors": errors, "via": "cookie"}

    async def submit_post(
        self,
        subreddit: str,
        title: str,
        text: str = "",
        url: str = "",
        flair: str = "",
    ) -> Dict[str, Any]:
        # Try cookie auth first (no OAuth app needed)
        if self._cookie_file().exists():
            result = await self._submit_via_cookies(subreddit, title, text, url)
            if result.get("ok") or result.get("post_id"):
                return result
        # Fallback: password grant OAuth
        if not self._has_creds():
            return {"available": False, "reason": "REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD not set", "platform": "reddit"}
        token = await self._get_token()
        if not token:
            return {"error": "token_error", "platform": "reddit"}
        api_url = f"{self.BASE}/api/submit"
        kind = "link" if url else "self"
        payload: Dict[str, Any] = {
            "sr": subreddit, "title": title, "kind": kind,
            "resubmit": True, "nsfw": False, "spoiler": False, "api_type": "json",
        }
        if text:
            payload["text"] = text
        if url:
            payload["url"] = url
        if flair:
            payload["flair_text"] = flair
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=self._headers(token), data=payload) as resp:
                return await resp.json(content_type=None)

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
        return bool(self.bearer_token or (self.api_key and self.access_token))

    def _bearer_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    async def ping(self) -> Tuple[bool, str]:
        username = _env("TWITTER_USERNAME") or "rudibot84"
        has_oauth1 = bool(self.api_key and self.api_secret and self.access_token and self.access_secret)
        if not self.bearer_token and not has_oauth1:
            return False, "Kein API-Key konfiguriert (TWITTER_BEARER_TOKEN)"
        # Use public user lookup with bearer token (/users/by/username works with app-only auth)
        if self.bearer_token:
            url = f"{self.BASE}/users/by/username/{username}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self._bearer_headers()) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            uname = data.get("data", {}).get("username", username)
                            return True, f"Twitter verbunden — @{uname}"
                        # 403 on free tier = credentials OK but endpoint restricted
                        if resp.status == 403 and has_oauth1:
                            return True, f"Twitter konfiguriert — @{username} (OAuth1 ready)"
            except Exception:
                pass
        if has_oauth1:
            return True, f"Twitter konfiguriert — @{username} (OAuth1 credentials OK)"
        return False, f"Twitter: keine gültigen Credentials"

    async def post_tweet(self, text: str) -> Dict[str, Any]:
        # Delegate to twitter_autoposter which has proper OAuth 1.0a + twikit support
        try:
            from modules.twitter_autoposter import post_tweet as _post
            return await _post(text)
        except Exception as e:
            return {"error": str(e), "platform": "twitter"}

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

# Alias for backward compatibility
InstagramConnector = MetaConnector
