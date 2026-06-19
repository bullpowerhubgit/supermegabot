"""
ViralTrafficMachine — Autonomous viral content distribution.
Posts to Reddit, Medium, Quora, LinkedIn, HackerNews, forums.
One piece of content → amplified across 6+ platforms simultaneously.
"""
import asyncio
import hashlib
import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("ViralTrafficMachine")

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = os.getenv("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = os.getenv("REDDIT_PASSWORD", "")
MEDIUM_API_KEY       = os.getenv("MEDIUM_API_KEY", "")
LINKEDIN_TOKEN       = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
# Support both LINKEDIN_PERSON_URN (full) and LINKEDIN_USER_ID (ID only)
_ln_urn = os.getenv("LINKEDIN_PERSON_URN", "")
LINKEDIN_USER_ID     = os.getenv("LINKEDIN_USER_ID", "") or (_ln_urn.split(":")[-1] if ":" in _ln_urn else _ln_urn)
ANTHROPIC_KEY        = os.getenv("ANTHROPIC_API_KEY", "")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DEDUP_FILE = DATA_DIR / "viral_posted.json"

DEFAULT_SUBREDDITS = [
    "shopify", "entrepreneur", "passive_income",
    "ecommerce", "dropshipping", "SideProject",
]

PRODUCT_NAME = os.getenv("DS24_PRODUCT_NAME", "AI Income Machine")
PRODUCT_URL  = os.getenv("DS24_PRODUCT_URL", "https://www.digistore24.com/product/669750")


# ── Dedup ─────────────────────────────────────────────────────────────────────

def _load_posted() -> set:
    try:
        return set(json.loads(DEDUP_FILE.read_text()))
    except Exception:
        return set()


def _save_posted(posted: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(sorted(posted)))


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Trending Topics ───────────────────────────────────────────────────────────

async def get_trending_topics() -> list[str]:
    """Fetch trending topics from Google Trends RSS (DE)."""
    try:
        import aiohttp
        import re as _re
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BullPowerBot/2.0)",
                   "Accept": "application/rss+xml, text/xml"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12),
                             allow_redirects=True) as r:
                raw = await r.read()
        text = raw.decode("utf-8", errors="replace").lstrip("﻿")
        text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        if not text.lstrip().startswith("<rss") and not text.lstrip().startswith("<?xml"):
            log.warning("Trends: non-XML response — using fallback")
            raise ValueError("non-XML")
        root = ET.fromstring(text)
        topics = [item.find("title").text.strip()
                  for item in root.iter("item")
                  if item.find("title") is not None and item.find("title").text]
        if topics:
            log.info("Trending topics fetched: %d", len(topics))
            return topics[:10]
    except Exception as e:
        log.warning("Trending fetch error: %s", e)
    return [
        "KI Business 2026", "Passives Einkommen Online",
        "Shopify Automatisierung", "AI Tools verdienen Geld",
        "Online Business Deutschland", "Dropshipping ohne Risiko",
    ]


# ── Content Generation ────────────────────────────────────────────────────────

async def generate_viral_content(topic: str, product_name: str = PRODUCT_NAME,
                                  product_url: str = PRODUCT_URL) -> dict | None:
    """Generate viral multi-platform content via Claude Haiku."""
    if not ANTHROPIC_KEY:
        return None
    try:
        import aiohttp
        prompt = f"""Du bist ein viraler Content-Spezialist. Erstelle Content für das Thema: "{topic}"
Produkt: {product_name} (Link: {product_url}, Preis: €37)

Gib NUR valides JSON zurück:
{{
  "title": "Klickstarker Artikel-Titel (max 80 Zeichen, neugierig machend)",
  "body": "Ein 800-Wort informativer Artikel auf Deutsch mit echtem Mehrwert. HTML-Formatierung mit <h2> Überschriften. Am Ende natürliche Erwähnung von {product_name} mit Link.",
  "reddit_post": "Kurzer Reddit-Post (max 300 Zeichen): echten Mehrwert liefern, am Ende Link. Kein reines Spam.",
  "linkedin_post": "Professioneller LinkedIn-Post (max 200 Zeichen) auf Deutsch, mit 2-3 relevanten Hashtags.",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1500,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as r:
                data = await r.json(content_type=None)
        raw = (data.get("content") or [{"text": "{}"}])[0].get("text", "{}")
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        log.warning("Content gen error: %s", e)
        return None


# ── Platform Posters ──────────────────────────────────────────────────────────

async def _get_reddit_token(session) -> str | None:
    """OAuth2 password grant for Reddit."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return None
    try:
        import aiohttp
        auth = aiohttp.BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
        async with session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data={"grant_type": "password", "username": REDDIT_USERNAME,
                  "password": REDDIT_PASSWORD},
            headers={"User-Agent": "SuperMegaBot/2.0"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            d = await r.json(content_type=None)
        return d.get("access_token")
    except Exception as e:
        log.warning("Reddit token error: %s", e)
        return None


async def post_to_reddit(content: dict, subreddits: list[str] | None = None) -> dict:
    """Post to Reddit subreddits via OAuth2."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        return {"ok": False, "error": "no Reddit credentials"}

    subs = subreddits or DEFAULT_SUBREDDITS[:3]
    results = {}

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            token = await _get_reddit_token(session)
            if not token:
                return {"ok": False, "error": "Reddit auth failed"}

            headers = {
                "Authorization": f"bearer {token}",
                "User-Agent": "SuperMegaBot/2.0",
            }
            for sub in subs:
                try:
                    async with session.post(
                        "https://oauth.reddit.com/api/submit",
                        headers=headers,
                        data={
                            "sr": sub, "kind": "self",
                            "title": content.get("title", "")[:300],
                            "text": content.get("reddit_post", content.get("body", ""))[:40000],
                            "nsfw": False, "spoiler": False,
                        },
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as r:
                        d = await r.json(content_type=None)
                    url = d.get("json", {}).get("data", {}).get("url", "")
                    results[sub] = {"ok": bool(url), "url": url}
                    log.info("Reddit r/%s: %s", sub, url or "failed")
                    await asyncio.sleep(2)  # rate limit
                except Exception as e:
                    results[sub] = {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": any(v.get("ok") for v in results.values()), "results": results}


async def post_to_medium(title: str, body: str, tags: list[str] | None = None) -> dict:
    """Publish article to Medium."""
    if not MEDIUM_API_KEY:
        return {"ok": False, "error": "no MEDIUM_API_KEY"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            # Get user ID first
            async with s.get(
                "https://api.medium.com/v1/me",
                headers={"Authorization": f"Bearer {MEDIUM_API_KEY}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                me = await r.json(content_type=None)
            user_id = me.get("data", {}).get("id")
            if not user_id:
                return {"ok": False, "error": "Medium: could not get user ID"}

            async with s.post(
                f"https://api.medium.com/v1/users/{user_id}/posts",
                headers={"Authorization": f"Bearer {MEDIUM_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "title": title, "contentFormat": "html",
                    "content": body, "tags": (tags or [])[:5],
                    "publishStatus": "public",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
        url = d.get("data", {}).get("url", "")
        log.info("Medium post: %s", url)
        return {"ok": bool(url), "url": url}
    except Exception as e:
        log.warning("Medium error: %s", e)
        return {"ok": False, "error": str(e)}


async def post_to_linkedin(text: str) -> dict:
    """Share post to LinkedIn."""
    if not LINKEDIN_TOKEN or not LINKEDIN_USER_ID:
        return {"ok": False, "error": "no LINKEDIN_ACCESS_TOKEN or LINKEDIN_USER_ID"}
    try:
        import aiohttp
        payload = {
            "author": f"urn:li:person:{LINKEDIN_USER_ID}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text[:3000]},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}",
                         "Content-Type": "application/json",
                         "X-Restli-Protocol-Version": "2.0.0"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        post_id = d.get("id", "")
        log.info("LinkedIn post: %s", post_id)
        return {"ok": bool(post_id), "post_id": post_id}
    except Exception as e:
        log.warning("LinkedIn error: %s", e)
        return {"ok": False, "error": str(e)}


async def post_to_quora_answer(topic: str, answer_text: str) -> dict:
    """Quora has no public API — manual only."""
    log.info("Quora: no public API, manual posting required for topic: %s", topic)
    return {"ok": False, "error": "Quora API not available — manual only"}


# ── Master Runner ─────────────────────────────────────────────────────────────

async def run_viral_traffic_machine(product_name: str = PRODUCT_NAME,
                                     product_url: str = PRODUCT_URL) -> dict:
    """
    Master function: get trending topics → generate content → distribute everywhere.
    Processes top 3 trending topics in sequence, posts to all platforms.
    """
    log.info("ViralTrafficMachine: starting run")
    posted = _load_posted()
    topics = await get_trending_topics()
    results = []

    for topic in topics[:3]:
        h = _content_hash(topic)
        if h in posted:
            log.info("Skip duplicate topic: %s", topic)
            continue

        content = await generate_viral_content(topic, product_name, product_url)
        if not content:
            log.warning("Content gen failed for: %s", topic)
            continue

        # Post to all platforms in parallel
        reddit_task   = asyncio.create_task(post_to_reddit(content))
        medium_task   = asyncio.create_task(
            post_to_medium(content.get("title", topic), content.get("body", ""), content.get("tags"))
        )
        linkedin_task = asyncio.create_task(post_to_linkedin(content.get("linkedin_post", "")))

        reddit_r, medium_r, linkedin_r = await asyncio.gather(
            reddit_task, medium_task, linkedin_task, return_exceptions=True
        )

        topic_result = {
            "topic": topic,
            "title": content.get("title"),
            "reddit":   reddit_r   if isinstance(reddit_r, dict)   else {"ok": False, "error": str(reddit_r)},
            "medium":   medium_r   if isinstance(medium_r, dict)   else {"ok": False, "error": str(medium_r)},
            "linkedin": linkedin_r if isinstance(linkedin_r, dict) else {"ok": False, "error": str(linkedin_r)},
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        results.append(topic_result)
        posted.add(h)

        log.info("Topic '%s': reddit=%s medium=%s linkedin=%s",
                 topic[:40],
                 topic_result["reddit"].get("ok"),
                 topic_result["medium"].get("ok"),
                 topic_result["linkedin"].get("ok"))

    _save_posted(posted)

    channels_hit = sum(
        int(r.get("reddit", {}).get("ok", False)) +
        int(r.get("medium", {}).get("ok", False)) +
        int(r.get("linkedin", {}).get("ok", False))
        for r in results
    )

    log.info("ViralTrafficMachine done: %d topics, %d channel hits", len(results), channels_hit)
    return {
        "ok": True,
        "topics_processed": len(results),
        "channels_hit": channels_hit,
        "results": results,
    }
