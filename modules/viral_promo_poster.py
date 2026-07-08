#!/usr/bin/env python3
"""
Viral Promo Poster — automatisches Multi-Channel Marketing für Viral Window Scanner.
Postet alle 6h auf: Facebook Page+Groups, Twitter/X, LinkedIn, Reddit, Telegram, Gumroad.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import random
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("ViralPromoPoster")

_BASE_DIR = Path(__file__).parent.parent
_DB_PATH  = _BASE_DIR / "data" / "promo_poster.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SUBSCRIBE_URL    = "https://supermegabot-production.up.railway.app/viral"
GUMROAD_PRODUCT_URL = "https://tecbuuss.gumroad.com/l/liastd"

# ── Env helpers ───────────────────────────────────────────────────────────────
def _fb_page_token()   -> str: return os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", "")
def _fb_page_id()      -> str: return os.getenv("FACEBOOK_PAGE_ID_AIITEC", "1016738738178786")
def _fb_user_token()   -> str: return os.getenv("FACEBOOK_USER_TOKEN", "")
def _tw_api_key()      -> str: return os.getenv("TWITTER_API_KEY", "")
def _tw_api_secret()   -> str: return os.getenv("TWITTER_API_SECRET", "")
def _tw_token()        -> str: return os.getenv("TWITTER_ACCESS_TOKEN", "")
def _tw_token_secret() -> str: return os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
def _li_token()        -> str: return os.getenv("LINKEDIN_ACCESS_TOKEN", "")
def _li_urn()          -> str: return os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
def _reddit_user()     -> str: return os.getenv("REDDIT_USERNAME", "bullpowersrtkennels")
def _reddit_pass()     -> str: return os.getenv("REDDIT_PASSWORD", "")
def _reddit_id()       -> str: return os.getenv("REDDIT_CLIENT_ID", "hqgJAQe6Qiu5s5r1Vqc0Og")
def _reddit_secret()   -> str: return os.getenv("REDDIT_CLIENT_SECRET", "")
def _tg_token()        -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()         -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _gumroad_token()   -> str: return os.getenv("GUMROAD_ACCESS_TOKEN", "")
def _anthropic_key()   -> str: return os.getenv("ANTHROPIC_API_KEY", "")

# Cooldowns in seconds
_COOLDOWNS = {
    "facebook_page":   86400,   # 1 day
    "facebook_group":  172800,  # 48 h
    "twitter":         43200,   # 12 h (2x/day)
    "linkedin":        86400,   # 1 day
    "reddit":          259200,  # 3 days per subreddit
    "telegram":        43200,   # 12 h
    "gumroad":         604800,  # 1 week (product creation)
}

_REDDIT_SUBREDDITS = [
    "dropshipping", "ecommerce", "Entrepreneur", "passive_income", "sidehustle",
]

_ANGLES = ["product_alert", "feature_highlight", "how_it_works", "success_story"]

# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS promo_posts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                platform   TEXT NOT NULL,
                channel    TEXT NOT NULL,
                angle      TEXT,
                content    TEXT,
                result     TEXT,
                posted_at  INTEGER NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_promo_platform ON promo_posts(platform, channel, posted_at)")


def _last_posted(platform: str, channel: str) -> int:
    with _db() as c:
        row = c.execute(
            "SELECT posted_at FROM promo_posts WHERE platform=? AND channel=? ORDER BY posted_at DESC LIMIT 1",
            (platform, channel)
        ).fetchone()
    return row["posted_at"] if row else 0


def _cooldown_ok(platform: str, channel: str) -> bool:
    key = platform if platform != "facebook_group" else "facebook_group"
    cooldown = _COOLDOWNS.get(key, 86400)
    return (time.time() - _last_posted(platform, channel)) >= cooldown


def _record(platform: str, channel: str, angle: str, content: str, result: str):
    with _db() as c:
        c.execute(
            "INSERT INTO promo_posts (platform,channel,angle,content,result,posted_at) VALUES (?,?,?,?,?,?)",
            (platform, channel, angle, content[:2000], result, int(time.time()))
        )

# ── HTTP session ──────────────────────────────────────────────────────────────

def _session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

# ── AI content generation ──────────────────────────────────────────────────────

async def generate_post_content(platform: str, angle: str, top_products: List[Dict]) -> str:
    product_str = ""
    if top_products:
        p = top_products[0]
        product_str = f"Trending Produkt: {p.get('keyword','Portable Blender')} (AI-Score {int(p.get('score',78))})"

    platform_hints = {
        "facebook": "Schreib auf Deutsch, Story-Stil, 3-4 Absätze, persönlich und authentisch, keine Hashtags am Anfang",
        "twitter":  "Schreib auf Englisch, max 270 Zeichen, Hook-first, 2-3 Hashtags am Ende",
        "linkedin": "Schreib auf Deutsch, professionell, B2B-Fokus, 3 kurze Absätze, kein Spam-Feeling",
        "reddit":   "Schreib auf Englisch, value-first, kein Verkaufs-Ton, hilfreich und authentisch, 3-5 Sätze",
        "telegram": "Schreib auf Deutsch, kurz, emoji-reich, max 3 Zeilen",
    }

    angle_hints = {
        "product_alert":      f"Zeige ein echtes Beispiel: {product_str}. Erkläre wie das Tool es 48h früher gefunden hat.",
        "feature_highlight":  "Hebe hervor: 6 Echtzeit-Signalquellen + AI-Score + automatischer Shopify-Import.",
        "how_it_works":       "Erkläre den Workflow: Signal → AI → Alert → Shopify. Kurz und klar.",
        "success_story":      "Erzähle eine kleine Geschichte: Dropshipper findet virales Produkt bevor alle anderen es haben.",
    }

    prompt = f"""Du bist ein Marketing-Experte. Erstelle einen Post für {platform}.

{platform_hints.get(platform, 'Kurz und klar')}

Winkel: {angle_hints.get(angle, angle)}

Produkt/Tool: Viral Window Scanner — findet viral gehende Dropshipping-Produkte bevor alle anderen.
Preise: Alert €29/mo, Pro €79/mo, Agency €199/mo
Gumroad Abo-Link: {GUMROAD_PRODUCT_URL}
Dashboard-Link: {SUBSCRIBE_URL}

Gib NUR den fertigen Post-Text zurück, keine Erklärungen."""

    key = _anthropic_key()
    if not key:
        return _fallback_content(platform, angle, top_products)

    try:
        async with _session() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
                      "messages": [{"role": "user", "content": prompt}]}
            ) as r:
                data = await r.json()
                return data.get("content", [{}])[0].get("text", "").strip()
    except Exception as e:
        log.warning("AI generation failed: %s", e)
        return _fallback_content(platform, angle, top_products)


def _fallback_content(platform: str, angle: str, top_products: List[Dict]) -> str:
    kw = top_products[0].get("keyword", "Portable Blender") if top_products else "Portable Blender"
    sc = int(top_products[0].get("score", 78)) if top_products else 78
    if platform == "twitter":
        return f"🔥 Found '{kw}' trending (AI Score {sc}/100) 48h before it hit Amazon. Automated alerts + Shopify import. {SUBSCRIBE_URL} #dropshipping #ecommerce"
    if platform == "telegram":
        return f"🔥 <b>Viral Scanner</b>: '{kw}' Score {sc}/100 — jetzt viral!\nAlert €29/mo 👉 {SUBSCRIBE_URL}"
    if platform == "reddit":
        return f"I built a scraper that found '{kw}' trending across TikTok, Google Trends and Amazon Movers simultaneously (score {sc}/100) — 48 hours before it went mainstream. Happy to share more details: {SUBSCRIBE_URL}"
    return (f"🔥 Neues Trend-Produkt entdeckt: {kw} (AI-Score: {sc}/100)\n\n"
            f"Unser Viral Window Scanner findet Produkte bevor alle anderen sie kennen — "
            f"automatisch in Shopify importiert.\n\n"
            f"Alert ab €29/mo 👉 {SUBSCRIBE_URL}")

# ── Facebook ──────────────────────────────────────────────────────────────────

async def post_facebook_page(text: str) -> Dict:
    token   = _fb_page_token()
    page_id = _fb_page_id()
    if not token:
        return {"ok": False, "error": "no FB page token"}
    try:
        async with _session() as s:
            async with s.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                params={"access_token": token},
                data={"message": text}
            ) as r:
                data = await r.json()
                if "id" in data:
                    return {"ok": True, "post_id": data["id"]}
                return {"ok": False, "error": data.get("error", {}).get("message", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_facebook_groups(text: str) -> List[Dict]:
    token = _fb_user_token()
    if not token:
        return [{"ok": False, "error": "no FB user token"}]

    results = []
    # Discover groups the user is member of
    try:
        async with _session() as s:
            async with s.get(
                "https://graph.facebook.com/v19.0/me/groups",
                params={"access_token": token, "fields": "id,name", "limit": "50"}
            ) as r:
                data = await r.json()
                groups = data.get("data", [])
    except Exception as e:
        return [{"ok": False, "error": f"groups fetch failed: {e}"}]

    if not groups:
        return [{"ok": False, "error": "no groups found or no permission"}]

    for group in groups[:10]:  # cap at 10 groups
        gid   = group.get("id", "")
        gname = group.get("name", gid)
        if not gid or not _cooldown_ok("facebook_group", gid):
            continue
        await asyncio.sleep(2)
        try:
            async with _session() as s:
                async with s.post(
                    f"https://graph.facebook.com/v19.0/{gid}/feed",
                    params={"access_token": token},
                    data={"message": text}
                ) as r:
                    resp = await r.json()
                    ok   = "id" in resp
                    res  = {"ok": ok, "group": gname, "gid": gid}
                    if not ok:
                        res["error"] = resp.get("error", {}).get("message", str(resp))
                    results.append(res)
                    if ok:
                        _record("facebook_group", gid, "", text, "ok")
        except Exception as e:
            results.append({"ok": False, "group": gname, "error": str(e)})

    return results or [{"ok": False, "error": "no eligible groups"}]

# ── Twitter / X ───────────────────────────────────────────────────────────────

def _oauth1_header(method: str, url: str, params: Dict) -> str:
    consumer_key    = _tw_api_key()
    consumer_secret = _tw_api_secret()
    token           = _tw_token()
    token_secret    = _tw_token_secret()

    nonce     = base64.b64encode(os.urandom(32)).decode().rstrip("=")
    timestamp = str(int(time.time()))

    oauth = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        timestamp,
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }

    base_params = {**params, **oauth}
    sorted_params = "&".join(
        f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(base_params.items())
    )
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(token_secret, safe='')}"
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth.items())
    )


async def post_twitter(text: str) -> Dict:
    if not _tw_api_key():
        return {"ok": False, "error": "no Twitter credentials"}
    text = text[:280]
    url  = "https://api.twitter.com/2/tweets"
    try:
        auth_header = _oauth1_header("POST", url, {})
        async with _session() as s:
            async with s.post(
                url,
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                json={"text": text}
            ) as r:
                data = await r.json()
                if r.status in (200, 201) and "data" in data:
                    return {"ok": True, "tweet_id": data["data"].get("id")}
                return {"ok": False, "error": data.get("detail", data.get("errors", str(data)))}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── LinkedIn ──────────────────────────────────────────────────────────────────

async def post_linkedin(text: str) -> Dict:
    token = _li_token()
    urn   = _li_urn()
    if not token:
        return {"ok": False, "error": "no LinkedIn token"}
    payload = {
        "author":          urn,
        "lifecycleState":  "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with _session() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                         "X-Restli-Protocol-Version": "2.0.0"},
                json=payload
            ) as r:
                if r.status in (200, 201):
                    loc = r.headers.get("X-RestLi-Id", "ok")
                    return {"ok": True, "post_id": loc}
                text_resp = await r.text()
                return {"ok": False, "error": f"HTTP {r.status}: {text_resp[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Reddit ────────────────────────────────────────────────────────────────────

async def _reddit_token() -> Optional[str]:
    ua = "ViralWindowScanner/1.0 by bullpowersrtkennels"
    try:
        async with _session() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={"User-Agent": ua},
                auth=aiohttp.BasicAuth(_reddit_id(), _reddit_secret()),
                data={"grant_type": "password", "username": _reddit_user(), "password": _reddit_pass()}
            ) as r:
                data = await r.json()
                return data.get("access_token")
    except Exception as e:
        log.warning("Reddit auth failed: %s", e)
        return None


async def post_reddit(subreddit: str, title: str, text: str) -> Dict:
    if not _reddit_id() or not _reddit_secret():
        return {"ok": False, "error": "no Reddit credentials"}
    token = await _reddit_token()
    if not token:
        return {"ok": False, "error": "Reddit auth failed"}
    ua = "ViralWindowScanner/1.0 by bullpowersrtkennels"
    try:
        await asyncio.sleep(2)  # Reddit rate limit
        async with _session() as s:
            async with s.post(
                "https://oauth.reddit.com/api/submit",
                headers={"Authorization": f"Bearer {token}", "User-Agent": ua},
                data={"sr": subreddit, "kind": "self", "title": title,
                      "text": text, "nsfw": "false", "spoiler": "false"}
            ) as r:
                data = await r.json()
                jquery = data.get("jquery", [])
                errors = [x for x in jquery if isinstance(x, list) and len(x) > 3 and x[3] and isinstance(x[3], list) and x[3]]
                if not errors:
                    return {"ok": True, "subreddit": subreddit}
                return {"ok": False, "error": str(errors[:2])}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Telegram ──────────────────────────────────────────────────────────────────

async def post_telegram_channels(text: str) -> Dict:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return {"ok": False, "error": "no Telegram credentials"}
    try:
        async with _session() as s:
            async with s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False}
            ) as r:
                data = await r.json()
                return {"ok": data.get("ok", False), "msg_id": data.get("result", {}).get("message_id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Gumroad ───────────────────────────────────────────────────────────────────

async def create_gumroad_product() -> Dict:
    # Produkt wurde bereits manuell erstellt und ist live:
    return {
        "ok": True,
        "url": GUMROAD_PRODUCT_URL,
        "id": "liastd",
        "note": "Product pre-created via browser — tecbuuss.gumroad.com"
    }

# ── Main orchestrator ─────────────────────────────────────────────────────────

async def run_promo_cycle(top_products: Optional[List[Dict]] = None) -> Dict:
    _init_db()

    # Load top products from viral scanner if not provided
    if top_products is None:
        try:
            from modules.viral_window_scanner import get_status
            status = await get_status()
            top_products = status.get("top_products", [])
        except Exception as e:
            log.warning("Could not load viral status: %s", e)
            top_products = []

    angle = random.choice(_ANGLES)
    results: Dict[str, object] = {"angle": angle, "platforms": [], "posted_count": 0, "errors": []}

    # ── Telegram ──────────────────────────────────────────────────────────────
    if _cooldown_ok("telegram", "main"):
        text = await generate_post_content("telegram", angle, top_products)
        res  = await post_telegram_channels(text)
        if res["ok"]:
            _record("telegram", "main", angle, text, "ok")
            results["platforms"].append("telegram")
            results["posted_count"] += 1
            log.info("Telegram OK")
        else:
            results["errors"].append(f"telegram: {res.get('error')}")
            log.warning("Telegram failed: %s", res.get("error"))

    # ── Twitter ───────────────────────────────────────────────────────────────
    if _cooldown_ok("twitter", "main") and _tw_api_key():
        text = await generate_post_content("twitter", angle, top_products)
        res  = await post_twitter(text)
        if res["ok"]:
            _record("twitter", "main", angle, text, "ok")
            results["platforms"].append("twitter")
            results["posted_count"] += 1
            log.info("Twitter OK: %s", res.get("tweet_id"))
        else:
            results["errors"].append(f"twitter: {res.get('error')}")
            log.warning("Twitter failed: %s", res.get("error"))

    # ── Facebook Page ─────────────────────────────────────────────────────────
    if _cooldown_ok("facebook_page", _fb_page_id()) and _fb_page_token():
        text = await generate_post_content("facebook", angle, top_products)
        res  = await post_facebook_page(text)
        if res["ok"]:
            _record("facebook_page", _fb_page_id(), angle, text, "ok")
            results["platforms"].append("facebook_page")
            results["posted_count"] += 1
            log.info("FB Page OK: %s", res.get("post_id"))
        else:
            results["errors"].append(f"facebook_page: {res.get('error')}")
            log.warning("FB Page failed: %s", res.get("error"))

    # ── Facebook Groups ───────────────────────────────────────────────────────
    if _fb_user_token():
        fb_text  = await generate_post_content("facebook", angle, top_products)
        grp_res  = await post_facebook_groups(fb_text)
        ok_count = sum(1 for r in grp_res if r.get("ok"))
        if ok_count:
            results["platforms"].append(f"facebook_groups({ok_count})")
            results["posted_count"] += ok_count
        for r in grp_res:
            if not r.get("ok"):
                results["errors"].append(f"fb_group {r.get('group','?')}: {r.get('error','?')}")

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    if _cooldown_ok("linkedin", "main") and _li_token():
        text = await generate_post_content("linkedin", angle, top_products)
        res  = await post_linkedin(text)
        if res["ok"]:
            _record("linkedin", "main", angle, text, "ok")
            results["platforms"].append("linkedin")
            results["posted_count"] += 1
            log.info("LinkedIn OK")
        else:
            results["errors"].append(f"linkedin: {res.get('error')}")
            log.warning("LinkedIn failed: %s", res.get("error"))

    # ── Reddit ────────────────────────────────────────────────────────────────
    if _reddit_id() and _reddit_secret():
        reddit_text = await generate_post_content("reddit", angle, top_products)
        kw    = top_products[0].get("keyword", "viral products") if top_products else "viral products"
        score = int(top_products[0].get("score", 78)) if top_products else 78
        title_templates = [
            f"I built a tool that found '{kw}' trending 48h before it went mainstream (score {score}/100)",
            f"How I auto-detect viral dropshipping products before everyone else — real example: {kw}",
            f"Found {kw} trending across 6 sources simultaneously — sharing my method",
            f"My AI spotted '{kw}' (score {score}) 2 days before Amazon Movers & Shakers listed it",
        ]
        title = random.choice(title_templates)
        for sub in _REDDIT_SUBREDDITS:
            if not _cooldown_ok("reddit", sub):
                continue
            res = await post_reddit(sub, title, reddit_text)
            if res["ok"]:
                _record("reddit", sub, angle, reddit_text, "ok")
                results["platforms"].append(f"reddit/r/{sub}")
                results["posted_count"] += 1
                log.info("Reddit r/%s OK", sub)
            else:
                results["errors"].append(f"reddit/{sub}: {res.get('error')}")
                log.warning("Reddit r/%s failed: %s", sub, res.get("error"))
            await asyncio.sleep(3)  # Reddit rate limit between subreddits

    # ── Gumroad (once per week) ───────────────────────────────────────────────
    if _cooldown_ok("gumroad", "product") and _gumroad_token():
        res = await create_gumroad_product()
        if res["ok"]:
            _record("gumroad", "product", "create", "", res.get("url", "ok"))
            results["platforms"].append("gumroad")
            results["posted_count"] += 1
            results["gumroad_url"] = res.get("url", "")
            log.info("Gumroad product OK: %s", res.get("url"))
        else:
            results["errors"].append(f"gumroad: {res.get('error')}")

    log.info("Promo cycle done: %d posts on %s", results["posted_count"], results["platforms"])
    return results


async def get_promo_stats() -> Dict:
    _init_db()
    with _db() as c:
        total = c.execute("SELECT COUNT(*) FROM promo_posts").fetchone()[0]
        by_platform = c.execute(
            "SELECT platform, COUNT(*) as cnt, MAX(posted_at) as last FROM promo_posts GROUP BY platform ORDER BY cnt DESC"
        ).fetchall()
        recent = c.execute(
            "SELECT platform, channel, angle, posted_at FROM promo_posts ORDER BY posted_at DESC LIMIT 20"
        ).fetchall()
    return {
        "ok":          True,
        "total_posts": total,
        "by_platform": [{"platform": r["platform"], "count": r["cnt"], "last": r["last"]} for r in by_platform],
        "recent":      [dict(r) for r in recent],
    }
