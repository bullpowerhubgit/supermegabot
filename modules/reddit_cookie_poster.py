#!/usr/bin/env python3
"""
Reddit Cookie-Poster — kein OAuth2 App nötig.
Authentifiziert via Chrome-Session-Cookies (reddit_session + token_v2).
Tägl. auto-refresh via Scheduler (wie Twitter Cookie-Auth).

Kein Script App, kein CAPTCHA, kein OAuth Flow.
"""
import asyncio
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("RedditCookiePoster")

BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / "data"
COOKIES_FILE = DATA_DIR / "reddit_cookies.json"

REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "")

# Global rate-limit tracker — prevents bursting for low-karma accounts
_last_post_time: float = 0.0
MIN_POST_INTERVAL_S = 600  # 10 minutes between posts (low-karma accounts need this)

SUBREDDITS_DEFAULT = [
    "passive_income", "entrepreneur", "ecommerce", "dropshipping",
    "affiliatemarketing", "smallbusiness", "Flipping",
    "SideProject", "WorkOnline", "makinmoney",
]


# ── Chrome cookie extraction ──────────────────────────────────────────────────

def _chrome_aes_key() -> Optional[bytes]:
    try:
        from Crypto.Protocol.KDF import PBKDF2
        r = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
            capture_output=True, text=True, timeout=5,
        )
        raw = r.stdout.strip()
        if not raw:
            return None
        return PBKDF2(raw.encode(), b"saltysalt", 16, 1003)
    except Exception as e:
        log.warning("AES key error: %s", e)
        return None


def _decrypt(enc_bytes: bytes, aes_key: bytes) -> str:
    try:
        from Crypto.Cipher import AES
        enc = bytes(enc_bytes)
        if enc[:3] != b"v10":
            return enc.decode("utf-8", errors="ignore")
        iv = b" " * 16
        cipher = AES.new(aes_key, AES.MODE_CBC, IV=iv)
        dec = cipher.decrypt(enc[3:])
        pad = dec[-1]
        raw = dec[:-pad]
        if len(raw) > 32:
            raw = raw[32:]
        return raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def refresh_cookies() -> bool:
    """Extract Reddit cookies from Chrome → save to data/reddit_cookies.json."""
    aes_key = _chrome_aes_key()
    if not aes_key:
        log.warning("Chrome AES key unavailable")
        return False

    chrome_path = os.path.expanduser(
        "~/Library/Application Support/Google/Chrome/Default/Cookies"
    )
    if not os.path.exists(chrome_path):
        log.warning("Chrome Cookies DB not found")
        return False

    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(chrome_path, tmp)
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute("""
            SELECT name, value, encrypted_value, host_key
            FROM cookies
            WHERE host_key LIKE '%.reddit.com'
        """)
        rows = cur.fetchall()
        conn.close()
    finally:
        os.unlink(tmp)

    cookies: dict = {}
    for name, val, enc, host in rows:
        v = val if val else _decrypt(enc, aes_key)
        if v and name not in cookies:
            cookies[name] = v

    if not cookies.get("token_v2") and not cookies.get("reddit_session"):
        log.warning("Reddit: no auth cookies — must be logged in to Chrome")
        return False

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    log.info("Reddit cookies refreshed (%d keys)", len(cookies))
    return True


def _load_cookies() -> dict:
    if COOKIES_FILE.exists():
        try:
            cookies = json.loads(COOKIES_FILE.read_text())
            if cookies.get("token_v2"):
                return cookies
        except Exception as _e:
            log.debug("skipped: %s", _e)
    # Fallback: env var REDDIT_TOKEN_V2 (used on Railway where data/ is not deployed)
    env_token = os.getenv("REDDIT_TOKEN_V2", "")
    if env_token:
        return {"token_v2": env_token}
    return {}


def _cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ── Reddit API via cookies ────────────────────────────────────────────────────

async def _get_modhash(session: aiohttp.ClientSession, cookies: dict) -> str:
    """Get modhash (CSRF token) needed for write operations."""
    try:
        async with session.get(
            "https://www.reddit.com/api/me.json",
            headers={
                "Cookie": _cookie_header(cookies),
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            d = await r.json(content_type=None)
            return d.get("data", {}).get("modhash", "")
    except Exception as e:
        log.warning("modhash fetch failed: %s", e)
        return ""


async def _fetch_first_flair(subreddit: str, token: str, username: str) -> str:
    """Fetch the first available link flair ID for a subreddit."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://oauth.reddit.com/r/{subreddit}/api/link_flair_v2",
                headers={"Authorization": f"Bearer {token}",
                         "User-Agent": f"SuperMegaBot/2.0 by /u/{username}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                flairs = await r.json(content_type=None)
                if isinstance(flairs, list) and flairs:
                    flair_id = flairs[0].get("id", "")
                    log.info("Auto-selected flair '%s' for r/%s", flairs[0].get("text", "?"), subreddit)
                    return flair_id
    except Exception as e:
        log.warning("Flair fetch failed for r/%s: %s", subreddit, e)
    return ""


async def submit_post(
    subreddit: str,
    title: str,
    text: str = "",
    url: str = "",
    flair_id: str = "",
) -> dict:
    """
    Submit a post to Reddit via token_v2 Bearer (Chrome session JWT).
    No OAuth2 app, no CAPTCHA, no script-type app needed.
    Returns {"ok": True, "url": "..."} or {"ok": False, "error": "..."}
    """
    global _last_post_time
    import time
    elapsed = time.time() - _last_post_time
    if elapsed < MIN_POST_INTERVAL_S:
        wait_s = int(MIN_POST_INTERVAL_S - elapsed)
        log.info("Reddit: rate-limit guard — waiting %ds before posting", wait_s)
        await asyncio.sleep(wait_s)

    cookies = _load_cookies()
    token = cookies.get("token_v2", "")

    if not token:
        if not refresh_cookies():
            return {"ok": False, "error": "No Reddit cookies — not logged in to Chrome"}
        cookies = _load_cookies()
        token = cookies.get("token_v2", "")

    if not token:
        return {"ok": False, "error": "token_v2 not found in cookies"}

    post_type = "link" if url else "self"
    payload: dict = {
        "sr":       subreddit,
        "kind":     post_type,
        "title":    title[:300],
        "api_type": "json",
        "nsfw":     "false",
    }
    if url:
        payload["url"] = url
    else:
        payload["text"] = text[:40000]
    if flair_id:
        payload["flair_id"] = flair_id

    username = REDDIT_USERNAME or "SuperMegaBot"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://oauth.reddit.com/api/submit",
                data=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": f"SuperMegaBot/2.0 by /u/{username}",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    json_d = d.get("json", d)
    errors = json_d.get("errors", [])
    if errors:
        err_str = str(errors)
        # Auto-fetch flair and retry if flair required
        if "FLAIR_REQUIRED" in err_str or "SUBMIT_VALIDATION_FLAIR_REQUIRED" in err_str:
            flair_id = await _fetch_first_flair(subreddit, token, username)
            if flair_id:
                payload["flair_id"] = flair_id
                try:
                    async with aiohttp.ClientSession() as sf:
                        async with sf.post(
                            "https://oauth.reddit.com/api/submit", data=payload,
                            headers={"Authorization": f"Bearer {token}",
                                     "User-Agent": f"SuperMegaBot/2.0 by /u/{username}"},
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as rf:
                            d = await rf.json(content_type=None)
                    json_d = d.get("json", d)
                    errors = json_d.get("errors", [])
                except Exception as _e:
                    log.debug("skipped: %s", _e)
        # token expired — refresh and retry once
        if errors and any("UNAUTHENTICATED" in str(e) or "auth" in str(e).lower() for e in errors):
            if refresh_cookies():
                cookies = _load_cookies()
                token = cookies.get("token_v2", "")
                if token:
                    try:
                        async with aiohttp.ClientSession() as s2:
                            async with s2.post(
                                "https://oauth.reddit.com/api/submit", data=payload,
                                headers={"Authorization": f"Bearer {token}",
                                         "User-Agent": f"SuperMegaBot/2.0 by /u/{username}"},
                                timeout=aiohttp.ClientTimeout(total=20),
                            ) as r2:
                                d = await r2.json(content_type=None)
                        json_d = d.get("json", d)
                        errors = json_d.get("errors", [])
                    except Exception as _e:
                        log.debug("skipped: %s", _e)
        if errors:
            return {"ok": False, "error": str(errors)}

    post_url = json_d.get("data", {}).get("url", "")
    if not post_url:
        return {"ok": False, "error": "No URL returned", "raw": d}

    import time
    _last_post_time = time.time()
    log.info("Reddit posted to r/%s: %s", subreddit, post_url)
    return {"ok": True, "url": post_url, "subreddit": subreddit}


async def post_to_subreddits(
    title: str,
    text: str = "",
    url: str = "",
    subreddits: list = None,
    max_posts: int = 3,
) -> list:
    """Post to multiple subreddits with rate limiting."""
    targets = (subreddits or SUBREDDITS_DEFAULT)[:max_posts]
    results = []
    for sub in targets:
        r = await submit_post(sub, title, text=text, url=url)
        results.append({"subreddit": sub, **r})
        if r.get("ok"):
            await asyncio.sleep(30)  # Reddit rate limit: 1 post / 10min per sub
        else:
            await asyncio.sleep(5)
    return results


# ── Cookie auto-refresh task ──────────────────────────────────────────────────

async def task_reddit_cookie_refresh() -> str:
    ok = refresh_cookies()
    return f"Reddit cookies {'refreshed OK' if ok else 'refresh FAILED (not logged in to Chrome?)'}"


# ── Quick test ────────────────────────────────────────────────────────────────

async def _test():
    print("Refreshing cookies...")
    ok = refresh_cookies()
    print(f"Cookie refresh: {'OK' if ok else 'FAILED'}")
    if not ok:
        return

    cookies = _load_cookies()
    print(f"Cookies: {list(cookies.keys())}")

    # Test auth
    async with aiohttp.ClientSession() as s:
        modhash = await _get_modhash(s, cookies)
    print(f"Modhash: {modhash[:10]}..." if modhash else "Modhash: FAILED")

    if modhash:
        print("\nPosting test to r/test...")
        r = await submit_post(
            "test",
            "SuperMegaBot Cookie Auth Test",
            text="Automated post via cookie auth — kein OAuth2 nötig!",
        )
        print(f"Result: {r}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_test())
