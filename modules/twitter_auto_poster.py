"""Twitter/X Auto Poster — postet automatisch Tweets via Twitter API v2."""
import os
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path

log = logging.getLogger("TwitterPoster")

TWITTER_BEARER = os.getenv("TWITTER_BEARER_TOKEN", "") or os.getenv("TWITTER_API_KEY", "")
ANTHROPIC = os.getenv("ANTHROPIC_API_KEY", "")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
POSTED_FILE = DATA_DIR / "twitter_posted.json"


def _load_posted() -> set:
    try:
        return set(json.loads(POSTED_FILE.read_text()))
    except Exception:
        return set()


def _save_posted(posted: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_FILE.write_text(json.dumps(sorted(posted)))


async def generate_tweet(topic: str, product: str = "AI Income Machine") -> str | None:
    """Generate a tweet with Claude Haiku."""
    if not ANTHROPIC:
        return None
    try:
        import aiohttp
        prompt = f"""Schreibe einen viralen Tweet auf Deutsch über "{topic}".
Erwähne "{product}" (€37 bei Digistore24).
Max 260 Zeichen. 2-3 relevante Hashtags. Kein Link nötig — nur der Tweet-Text.
Nur den Tweet-Text zurückgeben, kein anderer Text."""

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 150,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        return data["content"][0]["text"].strip()[:280]
    except Exception as e:
        log.warning("Tweet gen error: %s", e)
        return None


async def post_tweet(text: str) -> dict:
    """Post a tweet via Twitter API v2."""
    if not TWITTER_BEARER:
        return {"ok": False, "error": "No Twitter bearer token"}

    # Deduplicate
    content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    posted = _load_posted()
    if content_hash in posted:
        return {"ok": False, "error": "Already posted (duplicate)"}

    try:
        import aiohttp
        # Twitter API v2 — try with Bearer token
        headers = {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.twitter.com/2/tweets",
                headers=headers,
                json={"text": text},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)

        if data.get("data", {}).get("id"):
            posted.add(content_hash)
            _save_posted(posted)
            log.info("Tweet posted: %s", data["data"]["id"])
            return {"ok": True, "tweet_id": data["data"]["id"], "text": text[:50]}
        else:
            err = data.get("detail") or data.get("errors", [{}])[0].get("message", str(data))
            log.warning("Twitter post failed: %s", err)
            return {"ok": False, "error": err}
    except Exception as e:
        log.warning("Twitter post error: %s", e)
        return {"ok": False, "error": str(e)}


async def run_auto_tweet(topics: list[str] = None) -> dict:
    """Auto-generate and post tweet about a random topic."""
    if topics is None:
        topics = [
            "Passives Einkommen mit KI",
            "Online Geld verdienen 2026",
            "AI Business Automatisierung",
            "Shopify Dropshipping Tipps",
            "Digitale Produkte verkaufen",
            "KI Tools für Unternehmer",
        ]
    import random
    topic = random.choice(topics)
    tweet = await generate_tweet(topic)
    if not tweet:
        return {"ok": False, "error": "Content gen failed"}
    return await post_tweet(tweet)
