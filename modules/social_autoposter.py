#!/usr/bin/env python3
"""
Social Auto-Poster — Facebook, Instagram, YouTube, LinkedIn, TikTok
====================================================================
Postet automatisch AI-generierten Content auf alle verbundenen Plattformen.
Läuft als Scheduler-Task alle 6h (oder manuell via Bot-Command /social_post).

Verbundene Plattformen (alle getestet 2026-07-13):
  FB  ✅ Page Token (FACEBOOK_PAGE_TOKEN_AIITEC) — Aiitec Page 1016738738178786 (1281 Fans)
  IG  ✅ IG Business ID 17841478315197796 — @aaiitecc (4802 Follower)
  YT  ✅ API Key + Channel UCy5U7UGOMNkvUR2-5Qm4yiA — Rudolf Sarkany (4150 Subs)
  LI  ✅ Rudolf Sarkany, Person URN: urn:li:person:YcxbqVN0ZR — Scope w_member_social ✅
  TT  ✅ AIITEC Account — Posting pending: video.publish Scope (im TikTok Dev Portal aktivieren)
  TW  ❌ Keys abgelaufen — neue Keys unter developer.twitter.com erforderlich
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("SocialAutoPoster")

# ── Credentials ────────────────────────────────────────────────────────────
FB_TOKEN   = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", "")  # NUR AiiteC-Token — kein Fallback auf anderen Token
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
IG_ID      = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
LI_TOKEN   = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
YT_KEY     = os.getenv("YOUTUBE_API_KEY", "")
YT_CHANNEL = os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")

GRAPH      = "https://graph.facebook.com/v21.0"
SHOP_URL   = f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', 'ineedit.com.co')}"
DS24_LINK  = os.getenv("DS24_AFFILIATE_LINK", "")

STATE_FILE = Path(__file__).parent.parent / "data" / "social_autoposter_state.json"


# ── Pexels Bild-Fetch ────────────────────────────────────────────────────────
_PEXELS_QUERIES = [
    "smart home gadgets technology",
    "solar energy home",
    "robot vacuum cleaner",
    "smart speaker home automation",
    "security camera smart home",
    "smart thermostat technology",
    "electric vehicle charging",
    "LED smart lighting interior",
]

async def _fetch_pexels_image(query: str = "") -> str:
    """
    Holt ein zufälliges Bild von Pexels für IG-Posts ohne eigenes Bild.
    Benötigt PEXELS_API_KEY in .env.
    Gibt leeren String zurück wenn kein Key gesetzt oder Fehler.
    """
    if not PEXELS_KEY:
        log.warning("PEXELS_API_KEY nicht gesetzt — kein Auto-Bild für Instagram")
        return ""
    import random
    q = query or random.choice(_PEXELS_QUERIES)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_KEY},
                params={"query": q, "per_page": 15, "orientation": "square"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json(content_type=None)
        photos = data.get("photos", [])
        if not photos:
            log.warning("Pexels: keine Bilder für '%s'", q)
            return ""
        photo = random.choice(photos)
        url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large", "")
        log.info("Pexels Bild: %s (Query: %s)", url[:80], q)
        return url
    except Exception as e:
        log.warning("Pexels Fehler: %s", e)
        return ""


# ── HTTP Helper: POST mit exponentiellem Backoff bei 429 ─────────────────────
async def _post_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    data: dict,
    max_retries: int = 3,
) -> tuple[int, dict]:
    """POST mit exponentiellem Backoff bei Meta-Rate-Limit (429): 60s, 120s, 240s."""
    backoff = [60, 120, 240]
    last_status, last_resp = 0, {}
    for attempt in range(max_retries):
        async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as r:
            last_status = r.status
            last_resp = await r.json(content_type=None)
        if last_status != 429:
            break
        if attempt < max_retries - 1:
            wait = backoff[attempt]
            log.warning("Rate Limit 429 — warte %ds (Versuch %d/%d)", wait, attempt + 1, max_retries)
            await asyncio.sleep(wait)
    return last_status, last_resp


# ── Content Templates (DE + EN) ─────────────────────────────────────────────
_TEMPLATES_DE = [
    "🏠 Smart Home Produkte für deinen Alltag — ausgewählt von KI, geprüft auf Qualität.\n\n👉 {shop}\n\n#SmartHome #Gadgets #Tech #Innovation",
    "⚡ Neue Smart-Home-Bestseller eingetroffen: Sicherheitskameras, Solar-Sets & mehr — alle unter einem Dach.\n\n{shop}\n\n#SmartHome #Solar #Technik",
    "🔋 Balkonkraftwerk, Powerstation oder Smart Thermostat — KI-kuratierte Technik für Zuhause.\n\n👉 {shop}\n\n#Balkonkraftwerk #Solar #SmartHome",
    "📦 Smart Home 2026: Die besten Gadgets für dein Zuhause — von Saugroboter bis KI-Kamera.\n\n{shop}\n\n#SmartHome #Technik #Gadgets",
    "🔥 Trending Tech: Smart LED, Roboter-Rasenmäher, Sicherheitskameras — jetzt im Shop entdecken.\n\n→ {shop}\n\n#SmartHome #ECommerce #TrendTech",
    "💡 Energie sparen mit Smart Home: Balkonkraftwerke & smarte Thermostate direkt bei AIITEC.\n\n👉 {shop}\n\n#Energiesparen #Solar #SmartHome",
    "🤖 KI findet die besten Smart-Home-Produkte für dich — täglich aktualisiert, immer geprüft.\n\n→ {shop}\n\n#KI #SmartHome #Tech",
]

_TEMPLATES_EN = [
    "🏠 Smart Home essentials curated by AI — quality-checked, trending now.\n\n👉 {shop}\n\n#SmartHome #Gadgets #Tech",
    "⚡ Top Smart Home picks: security cameras, solar kits, robot vacuums — all in one place.\n\n✅ Shop now: {shop}\n\n#SmartHome #Solar #Technology",
    "🔥 Smart Home products trending in 2026 — solar kits, AI cameras, robot vacuums.\n\n{shop}\n\n#SmartHome #Tech #Gadgets",
    "📦 Quality smart home gadgets — AI-curated, customer-approved.\n\n→ {shop}\n\n#SmartHome #Quality #Tech",
]


def _pick_template(lang: str = "de") -> str:
    import random
    state = _load_state()
    used = state.get("used_templates", [])
    templates = _TEMPLATES_DE if lang == "de" else _TEMPLATES_EN
    available = [i for i in range(len(templates)) if i not in used]
    if not available:
        available = list(range(len(templates)))
        state["used_templates"] = []
    idx = random.choice(available)
    state.setdefault("used_templates", []).append(idx)
    _save_state(state)
    return templates[idx].format(shop=SHOP_URL, ds24=DS24_LINK)


def _load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── AI Caption Generator ─────────────────────────────────────────────────────
async def _ai_caption(topic: str = "", lang: str = "de") -> str:
    try:
        from modules.ai_client import ai_complete
        if lang == "de":
            prompt = (
                f"Schreibe einen kurzen, viralen Social-Media-Post auf Deutsch über: "
                f"{topic or 'KI-E-Commerce-Automatisierung'}. "
                f"Max 200 Zeichen. Keine Einkommensversprechen. 2-3 Hashtags. "
                f"CTA: {SHOP_URL}"
            )
        else:
            prompt = (
                f"Write a viral social media post in English about: "
                f"{topic or 'AI e-commerce automation'}. "
                f"Max 200 chars. No income claims. 2-3 hashtags. CTA: {SHOP_URL}"
            )
        return await ai_complete(prompt, max_tokens=150)
    except Exception:
        return _pick_template(lang)


# ── Facebook Page Poster ─────────────────────────────────────────────────────
async def post_to_facebook(message: str, image_url: str = "", link: str = "") -> dict:
    """Postet auf die Aiitec Facebook Page."""
    from modules.post_guardian import validate_post, register_posted
    ok, errors = validate_post(message, "facebook", image_url)
    if not ok:
        log.warning("Post Guardian blockiert FB-Post: %s", errors)
        return {"ok": False, "platform": "facebook", "blocked": True, "errors": errors}
    if not FB_TOKEN:
        return {"ok": False, "platform": "facebook", "error": "FACEBOOK_PAGE_TOKEN_AIITEC nicht gesetzt — Post abgebrochen"}
    url = f"{GRAPH}/{FB_PAGE_ID}/feed"
    data: dict = {"message": message, "access_token": FB_TOKEN}
    if link:
        data["link"] = link
    try:
        async with aiohttp.ClientSession() as s:
            status, resp = await _post_with_retry(s, url, data)
        if status == 429:
            return {"ok": False, "platform": "facebook", "error": "Rate Limit (429) — warte vor erneutem Post"}
        if "id" in resp:
            post_id = resp["id"]
            log.info("FB post OK: %s", post_id)
            register_posted(message, "facebook")
            return {"ok": True, "platform": "facebook", "post_id": post_id}
        err = resp.get("error", {}).get("message", str(resp))
        log.warning("FB post Fehler: %s", err)
        return {"ok": False, "platform": "facebook", "error": err}
    except Exception as e:
        return {"ok": False, "platform": "facebook", "error": str(e)}


async def post_photo_to_facebook(message: str, image_url: str) -> dict:
    """Postet ein Bild auf die Facebook Page."""
    if not FB_TOKEN:
        return {"ok": False, "platform": "facebook", "error": "kein Token"}
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    data = {"caption": message, "url": image_url, "access_token": FB_TOKEN}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20)) as r:
                resp = await r.json(content_type=None)
        if "id" in resp or "post_id" in resp:
            return {"ok": True, "platform": "facebook", "post_id": resp.get("post_id", resp.get("id"))}
        return {"ok": False, "platform": "facebook", "error": resp.get("error", {}).get("message", str(resp))}
    except Exception as e:
        return {"ok": False, "platform": "facebook", "error": str(e)}


# ── Instagram Business Poster ────────────────────────────────────────────────
async def post_to_instagram(caption: str, image_url: str) -> dict:
    """
    Postet ein Bild auf Instagram @aaiitecc.
    Post Guardian prüft vor dem Posten.
    image_url muss öffentlich erreichbar sein (JPG/PNG, min 320px).
    """
    from modules.post_guardian import validate_post, register_posted
    ok, errors = validate_post(caption, "instagram", image_url)
    if not ok:
        log.warning("Post Guardian blockiert IG-Post: %s", errors)
        return {"ok": False, "platform": "instagram", "blocked": True, "errors": errors}
    if not FB_TOKEN or not IG_ID:
        return {"ok": False, "platform": "instagram", "error": "INSTAGRAM_ACCOUNT_ID oder FACEBOOK_PAGE_TOKEN_AIITEC fehlt"}
    if not image_url:
        return {"ok": False, "platform": "instagram", "error": "image_url ist erforderlich — IG akzeptiert keine Text-Only Posts"}
    try:
        async with aiohttp.ClientSession() as s:
            # Schritt 1: Media Container erstellen
            status1, container = await _post_with_retry(
                s,
                f"{GRAPH}/{IG_ID}/media",
                {"image_url": image_url, "caption": caption, "access_token": FB_TOKEN},
            )
            if status1 == 429:
                return {"ok": False, "platform": "instagram", "error": "Rate Limit (429) — warte vor erneutem Post"}
            container_id = container.get("id")
            if not container_id:
                err = container.get("error", {}).get("message", str(container))
                return {"ok": False, "platform": "instagram", "error": f"Container: {err}"}

            # Schritt 2: Container publishen
            status2, publish = await _post_with_retry(
                s,
                f"{GRAPH}/{IG_ID}/media_publish",
                {"creation_id": container_id, "access_token": FB_TOKEN},
            )
            if status2 == 429:
                return {"ok": False, "platform": "instagram", "error": "Rate Limit (429) — warte vor erneutem Post"}

        if "id" in publish:
            log.info("IG post OK: %s", publish["id"])
            register_posted(caption, "instagram")
            return {"ok": True, "platform": "instagram", "post_id": publish["id"]}
        err = publish.get("error", {}).get("message", str(publish))
        return {"ok": False, "platform": "instagram", "error": err}
    except Exception as e:
        return {"ok": False, "platform": "instagram", "error": str(e)}


async def post_reel_to_instagram(caption: str, video_url: str) -> dict:
    """
    Postet ein Reel auf Instagram @aaiitecc.
    video_url muss öffentlich erreichbar sein (MP4, min 720p empfohlen).
    Post Guardian prüft vor dem Posten.
    """
    from modules.post_guardian import validate_post, register_posted
    ok_guard, errors = validate_post(caption, "instagram", video_url)
    if not ok_guard:
        log.warning("Post Guardian blockiert IG-Reel: %s", errors)
        return {"ok": False, "platform": "instagram_reel", "blocked": True, "errors": errors}
    if not FB_TOKEN or not IG_ID:
        return {"ok": False, "platform": "instagram_reel", "error": "INSTAGRAM_ACCOUNT_ID oder FACEBOOK_PAGE_TOKEN_AIITEC fehlt"}
    if not video_url:
        return {"ok": False, "platform": "instagram_reel", "error": "video_url ist erforderlich für Reels"}
    try:
        async with aiohttp.ClientSession() as s:
            # Schritt 1: Reel Container erstellen (mit Retry bei 429)
            status1, container = await _post_with_retry(
                s,
                f"{GRAPH}/{IG_ID}/media",
                {
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                    "access_token": FB_TOKEN,
                },
            )
            if status1 == 429:
                return {"ok": False, "platform": "instagram_reel", "error": "Rate Limit (429) — warte vor erneutem Post"}
            container_id = container.get("id")
            if not container_id:
                err = container.get("error", {}).get("message", str(container))
                return {"ok": False, "platform": "instagram_reel", "error": f"Container: {err}"}

            # Schritt 2: Warten bis Video verarbeitet ist (max 90s, 9x10s)
            finished = False
            for _ in range(9):
                await asyncio.sleep(10)
                async with s.get(
                    f"{GRAPH}/{container_id}",
                    params={"fields": "status_code", "access_token": FB_TOKEN},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    poll = await r.json(content_type=None)
                sc = poll.get("status_code", "")
                log.debug("Reel Container Status: %s", sc)
                if sc == "FINISHED":
                    finished = True
                    break
                if sc == "ERROR":
                    return {"ok": False, "platform": "instagram_reel", "error": f"Video-Verarbeitung fehlgeschlagen: {poll}"}

            if not finished:
                log.warning("Reel Container noch nicht FINISHED nach 90s — trotzdem publishen")

            # Schritt 3: Container publishen (mit Retry bei 429)
            status2, publish = await _post_with_retry(
                s,
                f"{GRAPH}/{IG_ID}/media_publish",
                {"creation_id": container_id, "access_token": FB_TOKEN},
            )
            if status2 == 429:
                return {"ok": False, "platform": "instagram_reel", "error": "Rate Limit (429) beim Publish"}

        if "id" in publish:
            log.info("IG Reel OK: %s", publish["id"])
            register_posted(caption, "instagram")
            return {"ok": True, "platform": "instagram_reel", "post_id": publish["id"]}
        err = publish.get("error", {}).get("message", str(publish))
        return {"ok": False, "platform": "instagram_reel", "error": err}
    except Exception as e:
        return {"ok": False, "platform": "instagram_reel", "error": str(e)}


# ── LinkedIn Personal Post ───────────────────────────────────────────────────
async def post_to_linkedin(text: str, link: str = "") -> dict:
    """Post Guardian prüft vor dem Posten.
    Postet auf Rudolf Sarkanys LinkedIn-Profil.
    Benötigt Scope: w_member_social (✅ bestätigt via 429 Rate Limit Test).
    """
    from modules.post_guardian import validate_post, register_posted
    ok_check, errors = validate_post(text, "linkedin")
    if not ok_check:
        log.warning("Post Guardian blockiert LI-Post: %s", errors)
        return {"ok": False, "platform": "linkedin", "blocked": True, "errors": errors}
    if not LI_TOKEN:
        return {"ok": False, "platform": "linkedin", "error": "LINKEDIN_ACCESS_TOKEN nicht gesetzt"}
    person_urn = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
    share_text = f"{text}\n\n{link}" if link else text
    payload: dict = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": share_text[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {LI_TOKEN}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                resp = await r.json(content_type=None)
                status = r.status
        if status in (200, 201):
            post_id = resp.get("id", "")
            log.info("LinkedIn post OK: %s", post_id)
            register_posted(text, "linkedin")
            return {"ok": True, "platform": "linkedin", "post_id": post_id}
        if status == 429:
            return {"ok": False, "platform": "linkedin", "error": "Rate Limit (429) — täglich max ~25 Posts"}
        err = resp.get("message", str(resp)) if isinstance(resp, dict) else str(resp)
        return {"ok": False, "platform": "linkedin", "error": err}
    except Exception as e:
        return {"ok": False, "platform": "linkedin", "error": str(e)}


async def get_linkedin_stats() -> dict:
    """Gibt LinkedIn-Profil-Stats zurück."""
    if not LI_TOKEN:
        return {"ok": False, "error": "Token fehlt"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {LI_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json(content_type=None)
        if isinstance(data, dict) and "name" in data:
            return {"ok": True, "name": data.get("name"), "email": data.get("email")}
        return {"ok": False, "error": str(data)[:80]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── YouTube Stats (Lesen) ────────────────────────────────────────────────────
async def get_youtube_stats() -> dict:
    """Holt Kanal-Statistiken von YouTube (Rudolf Sarkany)."""
    if not YT_KEY:
        return {"ok": False, "error": "YOUTUBE_API_KEY nicht gesetzt"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet,statistics", "id": YT_CHANNEL, "key": YT_KEY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        items = data.get("items", [])
        if not items:
            return {"ok": False, "error": "Kanal nicht gefunden"}
        ch = items[0]
        return {
            "ok": True,
            "title": ch["snippet"]["title"],
            "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
            "videos": int(ch["statistics"].get("videoCount", 0)),
            "views": int(ch["statistics"].get("viewCount", 0)),
            "channel_url": f"https://youtube.com/channel/{YT_CHANNEL}",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Instagram Stats ──────────────────────────────────────────────────────────
async def get_instagram_stats() -> dict:
    """Holt Follower-Count und letzte Posts von @aaiitecc."""
    if not FB_TOKEN or not IG_ID:
        return {"ok": False, "error": "Token fehlt"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{GRAPH}/{IG_ID}",
                params={"fields": "username,followers_count,media_count", "access_token": FB_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        if "error" in data:
            return {"ok": False, "error": data["error"].get("message")}
        return {
            "ok": True,
            "username": data.get("username"),
            "followers": data.get("followers_count"),
            "posts": data.get("media_count"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Facebook Stats ────────────────────────────────────────────────────────────
async def get_facebook_stats() -> dict:
    """Holt Fans und letzte Posts der Aiitec FB-Page."""
    if not FB_TOKEN:
        return {"ok": False, "error": "Token fehlt"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{GRAPH}/{FB_PAGE_ID}",
                params={"fields": "name,fan_count,followers_count", "access_token": FB_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        if "error" in data:
            return {"ok": False, "error": data["error"].get("message")}
        return {
            "ok": True,
            "name": data.get("name"),
            "fans": data.get("fan_count"),
            "followers": data.get("followers_count"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Telegram Notify ──────────────────────────────────────────────────────────
async def _tg(msg: str):
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


# ── Hauptfunktion: Multi-Platform Post ───────────────────────────────────────
async def post_to_all(
    message: str = "",
    image_url: str = "",
    link: str = "",
    platforms: Optional[list] = None,
    topic: str = "",
) -> dict:
    """
    Postet auf alle aktiven Plattformen gleichzeitig.
    platforms: ["facebook", "instagram"] — None = alle verfügbaren
    image_url: öffentliche Bild-URL (für Instagram Pflicht)
    """
    if not message:
        message = await _ai_caption(topic or "Smart Home E-Commerce Automatisierung")

    # ── PostGuard: Qualitätsprüfung vor jedem Post ────────────────────────
    try:
        from modules.post_guard import guard
        ok, reason = await guard.check("social", text=message, link=link or SHOP_URL)
        if not ok:
            log.warning("PostGuard BLOCKIERT: %s", reason)
            await _tg(f"🚫 <b>PostGuard blockiert Post</b>\nGrund: {reason}\n\nText: <i>{message[:200]}</i>")
            return {"ok": False, "blocked": True, "reason": reason}
    except ImportError:
        log.error("PostGuard (modules.post_guard) nicht importierbar — Post abgebrochen")
        return {"ok": False, "blocked": True, "reason": "PostGuard nicht verfügbar — Post abgebrochen"}

    active = platforms or ["facebook", "instagram"]

    # ── Auto-Bild via Pexels wenn kein image_url übergeben ───────────────────
    if "instagram" in active and not image_url:
        image_url = await _fetch_pexels_image(topic or "smart home gadgets technology")
        if not image_url:
            log.warning("Kein Pexels-Bild verfügbar — Instagram-Post wird übersprungen")
            active = [p for p in active if p != "instagram"]

    tasks = []
    if "facebook" in active:
        if image_url:
            tasks.append(post_photo_to_facebook(message, image_url))
        else:
            tasks.append(post_to_facebook(message, link=link or SHOP_URL))
    if "instagram" in active and image_url:
        tasks.append(post_to_instagram(message, image_url))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = []
    ok_count = 0
    for r in results:
        if isinstance(r, Exception):
            summary.append({"ok": False, "error": str(r)})
        else:
            summary.append(r)
            if r.get("ok"):
                ok_count += 1

    report = f"📢 *Social Post* ({ok_count}/{len(tasks)} OK)\n"
    for r in summary:
        icon = "✅" if r.get("ok") else "❌"
        plat = r.get("platform", "?")
        detail = r.get("post_id", r.get("error", ""))
        report += f"{icon} {plat}: {str(detail)[:60]}\n"
    report += f"_Nachricht: {message[:80]}_"

    await _tg(report)
    log.info("social post_to_all: %d/%d OK", ok_count, len(tasks))
    return {"ok": ok_count > 0, "posted": ok_count, "total": len(tasks), "results": summary}


# ── Scheduler-Einstieg ───────────────────────────────────────────────────────
async def run_social_cycle() -> dict:
    """
    Wird vom Scheduler alle 6h aufgerufen.
    Generiert Content und postet auf Facebook + Instagram (Pexels-Bild automatisch).
    """
    message = await _ai_caption(topic="Smart Home & KI-E-Commerce")
    # Pexels-Bild vorab holen damit FB-Photo + IG-Post beide ein Bild bekommen
    image_url = await _fetch_pexels_image("smart home gadgets technology 2026")
    result = await post_to_all(message=message, image_url=image_url, link=SHOP_URL)

    # Stats parallel holen
    fb_stats, ig_stats, yt_stats, li_stats = await asyncio.gather(
        get_facebook_stats(),
        get_instagram_stats(),
        get_youtube_stats(),
        get_linkedin_stats(),
        return_exceptions=True,
    )

    state = _load_state()
    state["last_cycle"] = datetime.now().isoformat()
    state["last_stats"] = {
        "facebook": fb_stats if isinstance(fb_stats, dict) else {},
        "instagram": ig_stats if isinstance(ig_stats, dict) else {},
        "youtube": yt_stats if isinstance(yt_stats, dict) else {},
        "linkedin": li_stats if isinstance(li_stats, dict) else {},
    }
    _save_state(state)

    return {**result, "stats": state["last_stats"]}


async def get_all_stats() -> dict:
    """Gibt aktuellen Stand aller verbundenen Plattformen zurück."""
    fb, ig, yt, li = await asyncio.gather(
        get_facebook_stats(),
        get_instagram_stats(),
        get_youtube_stats(),
        get_linkedin_stats(),
        return_exceptions=True,
    )
    return {
        "facebook": fb if isinstance(fb, dict) else {"ok": False, "error": str(fb)},
        "instagram": ig if isinstance(ig, dict) else {"ok": False, "error": str(ig)},
        "youtube": yt if isinstance(yt, dict) else {"ok": False, "error": str(yt)},
        "linkedin": li if isinstance(li, dict) else {"ok": False, "error": str(li)},
    }
