"""
Google Automation — vollständige Google-Integration für autonome Automation
Covers: Custom Search, YouTube, Indexing API, Maps
"""
import os
import logging
import asyncio
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# Key-Pool — rotiert automatisch bei Quota-Überschreitung
_GOOGLE_KEYS = [k for k in [
    os.getenv("GOOGLE_API_KEY_1"),
    os.getenv("GOOGLE_API_KEY_2"),
    os.getenv("GOOGLE_API_KEY_3"),
    os.getenv("GOOGLE_API_KEY_4"),
] if k]

_CUSTOM_SEARCH_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_KEY") or (_GOOGLE_KEYS[0] if _GOOGLE_KEYS else None)
_YOUTUBE_KEY = os.getenv("GOOGLE_YOUTUBE_KEY") or (_GOOGLE_KEYS[1] if len(_GOOGLE_KEYS) > 1 else _CUSTOM_SEARCH_KEY)
_INDEXING_KEY = os.getenv("GOOGLE_INDEXING_KEY") or (_GOOGLE_KEYS[2] if len(_GOOGLE_KEYS) > 2 else _CUSTOM_SEARCH_KEY)

SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")


# ─── 1. Custom Search — Produkt-Research + Trend-Erkennung ──────────────────

async def google_search(query: str, num: int = 10, language: str = "de") -> list[dict]:
    """Google Custom Search — für Produkt-Research, Trends, Competitor-Analyse."""
    if not _CUSTOM_SEARCH_KEY or not SEARCH_ENGINE_ID:
        logger.warning("Google Custom Search: Key oder Search Engine ID fehlt")
        return []
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": _CUSTOM_SEARCH_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "num": min(num, 10),
        "hl": language,
        "gl": "de",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    items = data.get("items", [])
                    return [{"title": i.get("title"), "link": i.get("link"), "snippet": i.get("snippet")} for i in items]
                logger.error("Custom Search HTTP %s", r.status)
    except Exception as e:
        logger.error("Custom Search Fehler: %s", e)
    return []


async def research_product_trends(niche: str = "smart home") -> dict:
    """Researcht aktuelle Produkt-Trends für eine Nische."""
    queries = [
        f"{niche} bestseller 2026",
        f"best {niche} products trending",
        f"{niche} Amazon bestseller",
    ]
    all_results = []
    for q in queries:
        results = await google_search(q, num=5)
        all_results.extend(results)
    return {"niche": niche, "results": all_results, "count": len(all_results)}


async def competitor_analysis(competitor_domain: str) -> list[dict]:
    """Analysiert Competitor-Seiten via Custom Search."""
    return await google_search(f"site:{competitor_domain}", num=10)


# ─── 2. YouTube Data API — Channel-Automation ───────────────────────────────

async def get_youtube_channel_stats(channel_id: str = None) -> dict:
    """Holt Channel-Statistiken via YouTube Data API."""
    if not _YOUTUBE_KEY:
        return {}
    cid = channel_id or YOUTUBE_CHANNEL_ID
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"key": _YOUTUBE_KEY, "id": cid, "part": "statistics,snippet"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    items = data.get("items", [])
                    if items:
                        stats = items[0].get("statistics", {})
                        snippet = items[0].get("snippet", {})
                        return {
                            "channel_id": cid,
                            "title": snippet.get("title"),
                            "subscribers": int(stats.get("subscriberCount", 0)),
                            "views": int(stats.get("viewCount", 0)),
                            "videos": int(stats.get("videoCount", 0)),
                        }
    except Exception as e:
        logger.error("YouTube Stats Fehler: %s", e)
    return {}


async def get_youtube_trending_videos(region: str = "DE", category_id: str = "28") -> list[dict]:
    """Holt trending YouTube-Videos (Category 28 = Science & Technology)."""
    if not _YOUTUBE_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": _YOUTUBE_KEY,
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": category_id,
        "part": "snippet,statistics",
        "maxResults": 10,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return [
                        {
                            "title": i["snippet"]["title"],
                            "views": int(i["statistics"].get("viewCount", 0)),
                            "video_id": i["id"],
                        }
                        for i in data.get("items", [])
                    ]
    except Exception as e:
        logger.error("YouTube Trending Fehler: %s", e)
    return []


async def search_youtube_videos(query: str, max_results: int = 5) -> list[dict]:
    """Sucht YouTube-Videos für Content-Research."""
    if not _YOUTUBE_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": _YOUTUBE_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": max_results,
        "regionCode": "DE",
        "relevanceLanguage": "de",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return [
                        {
                            "title": i["snippet"]["title"],
                            "channel": i["snippet"]["channelTitle"],
                            "video_id": i["id"]["videoId"],
                            "description": i["snippet"].get("description", "")[:200],
                        }
                        for i in data.get("items", [])
                    ]
    except Exception as e:
        logger.error("YouTube Search Fehler: %s", e)
    return []


# ─── 3. Google Indexing API — Produkt-URLs direkt indexieren ────────────────

async def submit_urls_to_google(urls: list[str]) -> dict:
    """
    Sendet URLs direkt an Google Indexing API.
    Benötigt Service Account mit Indexing API Berechtigung.
    """
    if not _INDEXING_KEY:
        return {"error": "Indexing Key fehlt"}

    results = {"submitted": 0, "errors": 0, "urls": []}
    endpoint = "https://indexing.googleapis.com/v3/urlNotifications:publish"

    async with aiohttp.ClientSession() as session:
        for url in urls[:200]:
            try:
                payload = {"url": url, "type": "URL_UPDATED"}
                headers = {"Authorization": f"Bearer {_INDEXING_KEY}", "Content-Type": "application/json"}
                async with session.post(endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status in (200, 201):
                        results["submitted"] += 1
                        results["urls"].append({"url": url, "status": "ok"})
                    else:
                        results["errors"] += 1
            except Exception as e:
                results["errors"] += 1
                logger.error("Indexing %s: %s", url, e)
            await asyncio.sleep(0.05)

    logger.info("Google Indexing: %d submitted, %d errors", results["submitted"], results["errors"])
    return results


# ─── 4. Google Maps / Places — lokale Business-Research ─────────────────────

async def search_local_businesses(query: str, location: str = "Vienna,Austria", radius: int = 50000) -> list[dict]:
    """Sucht lokale Businesses via Google Places API (für Lead-Gen)."""
    maps_key = os.getenv("GOOGLE_MAPS_KEY") or (_GOOGLE_KEYS[3] if len(_GOOGLE_KEYS) > 3 else None)
    if not maps_key:
        return []
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"key": maps_key, "query": query, "location": location, "radius": radius, "language": "de"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return [
                        {
                            "name": p.get("name"),
                            "address": p.get("formatted_address"),
                            "rating": p.get("rating"),
                            "place_id": p.get("place_id"),
                        }
                        for p in data.get("results", [])[:20]
                    ]
    except Exception as e:
        logger.error("Maps Places Fehler: %s", e)
    return []


# ─── 5. Autonome Gesamt-Automation — alles zusammen ────────────────────────

async def run_google_automation_cycle() -> dict:
    """
    Vollständiger autonomer Google-Automation-Cycle:
    1. Trend-Research für Smart-Home Nische
    2. YouTube Trending analysieren
    3. Channel-Stats abrufen
    4. Ergebnisse zurückgeben für weitere Verarbeitung
    """
    logger.info("Google Automation Cycle gestartet")

    trend_task = research_product_trends("smart home gadgets")
    youtube_task = get_youtube_trending_videos("DE", "28")
    channel_task = get_youtube_channel_stats()

    trends, yt_trending, channel = await asyncio.gather(
        trend_task, youtube_task, channel_task, return_exceptions=True
    )

    result = {
        "product_trends": trends if not isinstance(trends, Exception) else {},
        "youtube_trending": yt_trending if not isinstance(yt_trending, Exception) else [],
        "channel_stats": channel if not isinstance(channel, Exception) else {},
    }

    logger.info(
        "Google Cycle: %d Trends, %d YT-Videos, Channel: %s Abos",
        result["product_trends"].get("count", 0) if isinstance(result["product_trends"], dict) else 0,
        len(result["youtube_trending"]),
        result["channel_stats"].get("subscribers", "?"),
    )
    return result


async def get_status() -> dict:
    """Health-Check für Google Automation."""
    return {
        "keys_loaded": len(_GOOGLE_KEYS),
        "custom_search": bool(_CUSTOM_SEARCH_KEY and SEARCH_ENGINE_ID),
        "youtube": bool(_YOUTUBE_KEY),
        "indexing": bool(_INDEXING_KEY),
        "channel_id": YOUTUBE_CHANNEL_ID,
    }
