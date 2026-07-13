#!/usr/bin/env python3
"""
Social Media Autopilot — Product-driven auto-posting
=====================================================
Fetches real Shopify products (with images), generates platform-optimised
German captions via Claude Haiku, then posts 3× per day to:
  • Facebook  (Graph API page feed)
  • Instagram (Graph API container → publish)
  • Twitter/X (OAuth 1.0a v2)
  • Pinterest (v5 API)

Schedule: every 8 h (delay offset 2460 s to avoid collision with other tasks).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("SocialAutopilot")

# ── Credentials ─────────────────────────────────────────────────────────────
_e = os.getenv

FB_TOKEN   = _e("FACEBOOK_PAGE_TOKEN_AIITEC") or _e("META_ACCESS_TOKEN", "")
FB_PAGE_ID = _e("FACEBOOK_PAGE_ID", "1016738738178786")
IG_ID      = _e("INSTAGRAM_ACCOUNT_ID", "17841478315197796")

TW_API_KEY    = _e("TWITTER_API_KEY", "")
TW_API_SECRET = _e("TWITTER_API_SECRET", "")
TW_TOKEN      = _e("TWITTER_ACCESS_TOKEN", "")
TW_TOKEN_SEC  = _e("TWITTER_ACCESS_TOKEN_SECRET", "")

PIN_TOKEN  = _e("PINTEREST_ACCESS_TOKEN", "")
PIN_BOARD  = _e("PINTEREST_BOARD_ID", "")  # optional — posts to user's profile if blank

SHOP_DOMAIN = _e("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = _e("SHOPIFY_ADMIN_API_TOKEN", "")
SHOP_VER    = _e("SHOPIFY_API_VERSION", "2025-01")

ANTHROPIC_KEY = _e("ANTHROPIC_API_KEY", "")

GRAPH = "https://graph.facebook.com/v19.0"
STATE_FILE = Path(__file__).parent.parent / "data" / "social_autopilot_state.json"


# ── State helpers ────────────────────────────────────────────────────────────
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"posted_product_ids": [], "cycle": 0}


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


# ── Shopify: fetch next unposted product ─────────────────────────────────────
async def _get_shopify_product(session: aiohttp.ClientSession) -> Optional[dict]:
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return None
    state = _load_state()
    posted_ids = set(state.get("posted_product_ids", []))

    url = (f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/products.json"
           f"?status=active&limit=50&fields=id,title,body_html,images,handle,tags")
    headers = {"X-Shopify-Access-Token": SHOP_TOKEN}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        products = data.get("products", [])
        for p in products:
            if str(p["id"]) not in posted_ids and p.get("images"):
                return p
        # all posted — reset
        state["posted_product_ids"] = []
        _save_state(state)
        if products and products[0].get("images"):
            return products[0]
    except Exception as ex:
        log.warning("Shopify fetch error: %s", ex)
    return None


def _mark_posted(product_id) -> None:
    state = _load_state()
    ids = state.get("posted_product_ids", [])
    if str(product_id) not in ids:
        ids.append(str(product_id))
    state["posted_product_ids"] = ids
    _save_state(state)


# ── Caption generation via Claude Haiku ─────────────────────────────────────
async def _generate_caption(session: aiohttp.ClientSession, product: dict,
                             platform: str) -> str:
    title = product.get("title", "Smart Produkt")
    body = re.sub(r"<[^>]+>", " ", product.get("body_html", "")).strip()[:300]
    tags = product.get("tags", "")
    shop_link = f"https://{SHOP_DOMAIN}/products/{product.get('handle', '')}"

    char_limits = {
        "facebook": 500, "instagram": 300, "twitter": 270, "pinterest": 400
    }
    limit = char_limits.get(platform, 400)

    platform_notes = {
        "facebook": "Locker, informativ. Mit 3-5 relevanten Hashtags. Link am Ende.",
        "instagram": "Emotional, lifestyle-orientiert. 5-8 Hashtags. Kein Link (nur in Bio).",
        "twitter": f"Prägnant, max {limit} Zeichen inkl. Link. 2-3 Hashtags.",
        "pinterest": "Beschreibend, suchmaschinenoptimiert. Fokus auf Nutzen und Keywords.",
    }
    note = platform_notes.get(platform, "")

    prompt = (
        f"Schreibe einen {platform.upper()} Post auf Deutsch für dieses Produkt.\n"
        f"Produkt: {title}\n"
        f"Details: {body}\n"
        f"Tags: {tags}\n"
        f"Shop-Link: {shop_link}\n\n"
        f"Hinweise: {note}\n"
        f"Max {limit} Zeichen. Nur den Post-Text ausgeben, kein Kommentar."
    )

    if not ANTHROPIC_KEY:
        return f"🛒 {title}\n\n{shop_link}\n\n#SmartHome #Gadgets #Technik"

    try:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            if r.status == 200:
                resp = await r.json()
                text = resp["content"][0]["text"].strip()
                return text[:limit]
    except Exception as ex:
        log.warning("Haiku caption error: %s", ex)

    return f"🛒 {title}\n\n{shop_link}\n\n#SmartHome #Gadgets #Technik"


# ── Facebook post ─────────────────────────────────────────────────────────────
async def _post_facebook(session: aiohttp.ClientSession, caption: str,
                          image_url: str) -> dict:
    if not FB_TOKEN or not FB_PAGE_ID:
        return {"ok": False, "error": "no FB credentials"}
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    payload = {"url": image_url, "caption": caption, "access_token": FB_TOKEN}
    try:
        async with session.post(url, data=payload,
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json()
            if r.status == 200 and "id" in data:
                return {"ok": True, "post_id": data["id"], "platform": "facebook"}
            return {"ok": False, "error": data.get("error", {}).get("message", str(data))}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


# ── Instagram post ────────────────────────────────────────────────────────────
async def _post_instagram(session: aiohttp.ClientSession, caption: str,
                           image_url: str) -> dict:
    if not FB_TOKEN or not IG_ID:
        return {"ok": False, "error": "no IG credentials"}
    try:
        # Step 1: create container
        url1 = f"{GRAPH}/{IG_ID}/media"
        payload1 = {"image_url": image_url, "caption": caption,
                    "access_token": FB_TOKEN}
        async with session.post(url1, data=payload1,
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
            d = await r.json()
            if r.status != 200 or "id" not in d:
                return {"ok": False, "error": d.get("error", {}).get("message", str(d))}
            container_id = d["id"]

        await asyncio.sleep(3)

        # Step 2: publish
        url2 = f"{GRAPH}/{IG_ID}/media_publish"
        payload2 = {"creation_id": container_id, "access_token": FB_TOKEN}
        async with session.post(url2, data=payload2,
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
            d2 = await r.json()
            if r.status == 200 and "id" in d2:
                return {"ok": True, "post_id": d2["id"], "platform": "instagram"}
            return {"ok": False, "error": d2.get("error", {}).get("message", str(d2))}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


# ── Twitter/X OAuth 1.0a ──────────────────────────────────────────────────────
def _tw_oauth_header(method: str, url: str, params: dict) -> str:
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    ts = str(int(time.time()))
    oauth_params = {
        "oauth_consumer_key": TW_API_KEY,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": ts,
        "oauth_token": TW_TOKEN,
        "oauth_version": "1.0",
    }
    all_params = {**params, **oauth_params}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = (urllib.parse.quote(TW_API_SECRET, safe="") + "&" +
                   urllib.parse.quote(TW_TOKEN_SEC, safe=""))
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature
    header_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


async def _post_twitter(session: aiohttp.ClientSession, caption: str) -> dict:
    if not TW_API_KEY or not TW_TOKEN:
        return {"ok": False, "error": "no Twitter credentials"}
    url = "https://api.twitter.com/2/tweets"
    body = {"text": caption[:280]}
    auth = _tw_oauth_header("POST", url, {})
    try:
        async with session.post(
            url,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            json=body,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            d = await r.json()
            if r.status in (200, 201) and d.get("data", {}).get("id"):
                return {"ok": True, "tweet_id": d["data"]["id"], "platform": "twitter"}
            return {"ok": False, "error": str(d)}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


# ── Pinterest post ────────────────────────────────────────────────────────────
async def _post_pinterest(session: aiohttp.ClientSession, caption: str,
                           image_url: str, title: str, link: str) -> dict:
    if not PIN_TOKEN:
        return {"ok": False, "error": "no Pinterest token"}
    url = "https://api.pinterest.com/v5/pins"
    body = {
        "title": title[:100],
        "description": caption[:500],
        "link": link,
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    if PIN_BOARD:
        body["board_id"] = PIN_BOARD
    try:
        async with session.post(
            url,
            headers={"Authorization": f"Bearer {PIN_TOKEN}",
                     "Content-Type": "application/json"},
            json=body,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            d = await r.json()
            if r.status in (200, 201) and d.get("id"):
                return {"ok": True, "pin_id": d["id"], "platform": "pinterest"}
            return {"ok": False, "error": str(d)}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


# ── Main cycle ────────────────────────────────────────────────────────────────
async def run_autopilot_cycle() -> dict:
    results = []
    async with aiohttp.ClientSession() as session:
        product = await _get_shopify_product(session)
        if not product:
            return {"ok": False, "error": "no Shopify product available", "posted": 0}

        title = product.get("title", "Produkt")
        image_url = product["images"][0]["src"]
        handle = product.get("handle", "")
        shop_link = f"https://{SHOP_DOMAIN}/products/{handle}" if SHOP_DOMAIN else ""

        # Generate captions for each platform in parallel
        captions = await asyncio.gather(
            _generate_caption(session, product, "facebook"),
            _generate_caption(session, product, "instagram"),
            _generate_caption(session, product, "twitter"),
            _generate_caption(session, product, "pinterest"),
            return_exceptions=True,
        )
        fb_cap, ig_cap, tw_cap, pin_cap = [
            c if isinstance(c, str) else f"🛒 {title}" for c in captions
        ]

        # Post in parallel
        posts = await asyncio.gather(
            _post_facebook(session, fb_cap, image_url),
            _post_instagram(session, ig_cap, image_url),
            _post_twitter(session, tw_cap),
            _post_pinterest(session, pin_cap, image_url, title, shop_link),
            return_exceptions=True,
        )

        for p in posts:
            if isinstance(p, Exception):
                results.append({"ok": False, "error": str(p)})
            else:
                results.append(p)

        ok_count = sum(1 for r in results if isinstance(r, dict) and r.get("ok"))
        if ok_count > 0:
            _mark_posted(product["id"])
            state = _load_state()
            state["cycle"] = state.get("cycle", 0) + 1
            _save_state(state)

        log.info("Social autopilot cycle done — %d/%d platforms OK — product: %s",
                 ok_count, len(results), title)
        return {"ok": ok_count > 0, "posted": ok_count, "product": title,
                "results": results}


async def get_status() -> dict:
    state = _load_state()
    return {
        "posted_products_count": len(state.get("posted_product_ids", [])),
        "total_cycles": state.get("cycle", 0),
        "platforms": ["facebook", "instagram", "twitter", "pinterest"],
        "schedule": "every 8 hours",
        "credentials": {
            "facebook": bool(FB_TOKEN),
            "instagram": bool(FB_TOKEN and IG_ID),
            "twitter": bool(TW_API_KEY and TW_TOKEN),
            "pinterest": bool(PIN_TOKEN),
        },
    }
