"""Twitter/X Auto Poster — postet automatisch Tweets via Twitter API v2 (OAuth 1.0a)."""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger("TwitterPoster")

# OAuth 1.0a credentials (required for posting tweets)
TWITTER_API_KEY        = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET     = os.getenv("TWITTER_API_SECRET", "") or os.getenv("TWITTER_API_KEY_SECRET", "")
TWITTER_ACCESS_TOKEN   = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET  = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "") or os.getenv("TWITTER_ACCESS_SECRET", "")

ANTHROPIC = os.getenv("ANTHROPIC_API_KEY", "")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
POSTED_FILE = DATA_DIR / "twitter_posted.json"


def _oauth1_header(method: str, url: str, body: dict) -> str:
    """Build OAuth 1.0a Authorization header for Twitter API v2."""
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return ""

    params = {
        "oauth_consumer_key":     TWITTER_API_KEY,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            TWITTER_ACCESS_TOKEN,
        "oauth_version":          "1.0",
    }

    # Build signature base string
    all_params = {**params}
    param_str = "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
                         for k, v in sorted(all_params.items()))
    base_str = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(param_str, safe=""),
    ])

    # Sign with HMAC-SHA1
    signing_key = f"{urllib.parse.quote(TWITTER_API_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_SECRET, safe='')}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()
    ).decode()
    params["oauth_signature"] = signature

    header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(params.items())
    )
    return header


def _load_posted() -> set:
    try:
        return set(json.loads(POSTED_FILE.read_text()))
    except Exception:
        return set()


def _save_posted(posted: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_FILE.write_text(json.dumps(sorted(posted)))


_TWEET_TEMPLATES = [
    "🚀 KI-Automatisierung 2026 — dein Business läuft auf Autopilot! Shopify + DS24 + BRUTUS = passives Einkommen. #KI #PassivesEinkommen #Shopify",
    "💰 Online Geld verdienen 2026 geht einfacher denn je mit KI-Tools! AliExpress Dropshipping + Affiliate vollautomatisch. #Dropshipping #Ecommerce",
    "🤖 BRUTUS postet täglich auf 6+ Kanälen automatisch für dich. E-Commerce auf Autopilot — kein manueller Aufwand! #AIAutomation #Business",
    "📈 Shopify + AI = perfekte Kombination 2026. Produkte importieren, Texte erstellen, Traffic generieren — alles autonom! #Shopify #KI",
    "🔥 Passives Einkommen mit KI: DS24 Affiliate + automatischer Content + BRUTUS Traffic. So geht's 2026! #PassivIncome #Automatisierung",
    "💡 Digitale Produkte verkaufen war nie einfacher: KI schreibt, BRUTUS postet, du verdienst. #DigitaleProdukte #OnlineBusiness",
]

async def generate_tweet(topic: str, product: str = "AI Income Machine") -> str | None:
    """Generate a tweet via AI fallback chain — always returns content."""
    import random
    try:
        from modules.ai_client import ai_complete
        prompt = (f'Schreibe einen viralen Tweet auf Deutsch über "{topic}". '
                  f'Max 260 Zeichen. 2-3 Hashtags. Nur den Tweet-Text.')
        result = await ai_complete(prompt, max_tokens=150)
        if result and len(result.strip()) > 20:
            return result.strip()[:280]
    except Exception as e:
        log.warning("Tweet gen error: %s", e)
    # Template fallback — never returns None
    return random.choice(_TWEET_TEMPLATES)


async def post_tweet(text: str) -> dict:
    """Post a tweet via Twitter API v2 with OAuth 1.0a."""
    try:
        from modules.post_guard import validate_and_log
        if not await validate_and_log(text, platform="twitter"):
            return {"ok": False, "blocked": True, "reason": "PostGuard: Qualitätsprüfung nicht bestanden"}
    except Exception:
        pass

    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return {"ok": False, "error": "Twitter OAuth 1.0a credentials not set (need API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)"}

    content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    posted = _load_posted()
    if content_hash in posted:
        return {"ok": False, "error": "Already posted (duplicate)"}

    url = "https://api.twitter.com/2/tweets"
    body = {"text": text}
    auth_header = _oauth1_header("POST", url, body)

    try:
        import aiohttp
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)

        if data.get("data", {}).get("id"):
            posted.add(content_hash)
            _save_posted(posted)
            log.info("Tweet posted: %s", data["data"]["id"])
            return {"ok": True, "tweet_id": data["data"]["id"], "text": text[:50]}
        else:
            err = data.get("detail") or str(data.get("errors", data))[:120]
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
