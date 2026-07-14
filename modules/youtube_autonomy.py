#!/usr/bin/env python3
"""
YouTube Autonomy — Trending Videos finden, Scripts generieren, Affiliate-Links einbauen.
GOOGLE_API_KEY bereits vorhanden! YouTube Data API v3.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

import aiohttp

log = logging.getLogger("YouTubeAutonomy")

YOUTUBE_KEY  = os.getenv("YOUTUBE_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
DS24_LINK    = os.getenv("DS24_AFFILIATE_LINK", f"{SHOP_URL}")
AMAZON_TAG   = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")

YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"

VIDEO_NICHES = [
    "passive income online 2026", "shopify dropshipping", "chatgpt money making",
    "amazon affiliate marketing", "tiktok shop business", "print on demand",
    "email marketing automation", "digital products geld verdienen",
    "ki tools für business", "affiliate marketing anfänger",
]

SCRIPT_HOOKS = [
    "Ich habe €{amount} in {days} Tagen verdient — so geht's:",
    "{count} Fehler die dich {amount}€ kosten (und wie du sie vermeidest):",
    "Die Wahrheit über {topic} die niemand dir sagt:",
    "Von 0 auf €{amount}/Monat mit {topic} — mein ehrlicher Bericht:",
    "Das {topic} System das wirklich funktioniert (keine BS):",
]


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def find_trending_videos(niche: str = "", max_results: int = 10) -> list:
    """YouTube Data API v3 — Trending Videos in Nische."""
    query = niche or random.choice(VIDEO_NICHES)

    if YOUTUBE_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{YOUTUBE_BASE}/search",
                    params={
                        "key": YOUTUBE_KEY,
                        "q": query,
                        "part": "snippet",
                        "type": "video",
                        "order": "viewCount",
                        "maxResults": max_results,
                        "relevanceLanguage": "de",
                        "publishedAfter": "2025-01-01T00:00:00Z",
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    data = await r.json()

            videos = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                videos.append({
                    "id": item.get("id", {}).get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "description": snippet.get("description", "")[:200],
                    "url": f"https://www.youtube.com/watch?v={item.get('id',{}).get('videoId','')}",
                })
            log.info("YouTube: found %d trending videos for '%s'", len(videos), query)
            return videos
        except Exception as e:
            log.warning("YouTube API error: %s", e)

    # Fallback: simulierte Trending-Daten
    return [
        {"title": f"Wie ich mit {query} €{random.randint(500,5000)}/Monat verdiene",
         "channel": "EcommercePro", "url": f"https://youtube.com/results?search_query={query.replace(' ','+')}",
         "id": "", "description": f"Kompletter Guide zu {query}"}
        for _ in range(3)
    ]


async def generate_video_content(topic: str = "") -> dict:
    """KI generiert vollständiges YouTube Video-Script + Titel + Tags + Beschreibung."""
    niche = topic or random.choice(VIDEO_NICHES)
    hook_template = random.choice(SCRIPT_HOOKS)
    hook = hook_template.format(
        amount=random.randint(500, 5000),
        days=random.randint(7, 30),
        count=random.randint(3, 10),
        topic=niche,
    )

    prompt = f"""Erstelle vollständigen YouTube Video-Content auf Deutsch für: "{niche}"

1. TITEL (klickbait-optimiert, max 60 Zeichen, Hook: "{hook[:40]}")
2. BESCHREIBUNG (150 Wörter: Intro + Was du lernst + Links)
   Inkludiere: {SHOP_URL} als Hauptlink, Amazon-Affiliate: https://amzn.to/affiliate
3. TAGS (15 Keywords, komma-separiert)
4. SCRIPT OUTLINE (5 Kapitel mit Timestamps)
5. CTA-Text (für Pinned Comment, 2 Sätze)

Trenne die Sektionen mit ---"""

    content = await _ai(prompt, 700)
    if not content:
        content = f"""TITEL: {hook} — Kompletter Guide 2026
---
BESCHREIBUNG: In diesem Video zeige ich dir alles über {niche}. Kostenlose Ressourcen: {SHOP_URL}
---
TAGS: {niche}, geld verdienen online, passive einkommen, 2026, anfänger guide
---
SCRIPT: Intro → Grundlagen → Strategie → Praxisbeispiel → CTA
---
CTA: Abonniere für wöchentliche Tipps! Link in der Beschreibung: {SHOP_URL}"""

    return {"ok": True, "topic": niche, "content": content,
            "shop_link": SHOP_URL, "amazon_tag": AMAZON_TAG}


async def blast_video_ideas(count: int = 3) -> dict:
    """Sendet Video-Ideen + Scripts an Telegram."""
    ideas_sent = 0
    for i in range(count):
        niche = random.choice(VIDEO_NICHES)
        try:
            content_data = await generate_video_content(niche)
            content = content_data.get("content", "")
            title_line = content.split("---")[0].replace("TITEL:", "").strip() if content else niche

            from modules.brutus_core import fire
            await fire(
                f"YouTube Idee: {title_line[:60]}",
                f"🎬 Neue YouTube Video-Idee!\n\nThema: {niche}\n\nTitel: {title_line[:80]}\n\n📊 Trends: https://trends.google.com/trends/explore?q={niche.replace(' ','+')}\n\n👉 {SHOP_URL}",
                link=SHOP_URL,
                channels=["telegram"]
            )
            ideas_sent += 1
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("YouTube blast error: %s", e)

    return {"ok": True, "ideas_sent": ideas_sent}


async def get_youtube_status() -> dict:
    """Status des YouTube-Moduls."""
    return {
        "ok": True,
        "api_configured": bool(YOUTUBE_KEY),
        "api_key_source": "YOUTUBE_API_KEY" if os.getenv("YOUTUBE_API_KEY") else "GOOGLE_API_KEY (fallback)",
        "niches": len(VIDEO_NICHES),
        "shop_url": SHOP_URL,
    }


async def run_youtube_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    niche = random.choice(VIDEO_NICHES)
    trending = await find_trending_videos(niche, max_results=5)
    ideas = await blast_video_ideas(count=2)
    return {"ok": True, "niche": niche, "trending_found": len(trending),
            "ideas_sent": ideas.get("ideas_sent", 0)}
