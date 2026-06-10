#!/usr/bin/env python3
"""
YouTube Analytics Module — Rudolf Sarkany Channel Tracker
Kanal: UCy5U7UGOMNkvUR2-5Qm4yiA (Rudolf Sarkany, 4190 Abos, 154 Videos)
"""

import logging
import os
from typing import Any, Dict, List, Optional

log = logging.getLogger("YouTubeAnalytics")

_BASE = "https://www.googleapis.com/youtube/v3"


def _key() -> str:
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def _channel() -> str:
    return os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA").strip()


async def _get(endpoint: str, params: Dict) -> Dict:
    try:
        import aiohttp
        params["key"] = _key()
        url = f"{_BASE}/{endpoint}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    text = await r.text()
                    return {"error": f"HTTP {r.status}: {text[:200]}"}
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def get_channel_stats() -> Dict:
    """Kanal-Statistiken: Abonnenten, Views, Videos."""
    if not _key():
        return {"ok": False, "error": "YOUTUBE_API_KEY nicht gesetzt"}
    data = await _get("channels", {
        "part": "snippet,statistics,brandingSettings",
        "id": _channel(),
    })
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items", [])
    if not items:
        return {"ok": False, "error": "Kanal nicht gefunden"}
    ch = items[0]
    st = ch.get("statistics", {})
    sn = ch.get("snippet", {})
    return {
        "ok": True,
        "channel_id": _channel(),
        "title": sn.get("title"),
        "description": sn.get("description", "")[:200],
        "country": sn.get("country"),
        "subscribers": int(st.get("subscriberCount", 0)),
        "total_views": int(st.get("viewCount", 0)),
        "video_count": int(st.get("videoCount", 0)),
        "thumbnail": sn.get("thumbnails", {}).get("default", {}).get("url"),
    }


async def get_latest_videos(max_results: int = 10) -> Dict:
    """Neueste Videos mit Statistiken."""
    if not _key():
        return {"ok": False, "error": "YOUTUBE_API_KEY nicht gesetzt"}
    search_data = await _get("search", {
        "part": "snippet,id",
        "channelId": _channel(),
        "order": "date",
        "maxResults": max_results,
        "type": "video",
    })
    if "error" in search_data:
        return {"ok": False, "error": search_data["error"]}

    items = search_data.get("items", [])
    if not items:
        return {"ok": True, "videos": [], "total": 0}

    video_ids = ",".join(i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId"))
    stats_data = await _get("videos", {
        "part": "statistics,snippet",
        "id": video_ids,
    })

    stats_map = {}
    for v in stats_data.get("items", []):
        stats_map[v["id"]] = v.get("statistics", {})

    videos = []
    for item in items:
        vid_id = item.get("id", {}).get("videoId", "")
        sn = item.get("snippet", {})
        st = stats_map.get(vid_id, {})
        videos.append({
            "id": vid_id,
            "title": sn.get("title", ""),
            "published": sn.get("publishedAt", "")[:10],
            "thumbnail": sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "url": f"https://youtube.com/watch?v={vid_id}",
        })

    total_views = sum(v["views"] for v in videos)
    return {
        "ok": True,
        "videos": videos,
        "total": search_data.get("pageInfo", {}).get("totalResults", len(videos)),
        "period_views": total_views,
    }


async def get_top_videos(max_results: int = 10) -> Dict:
    """Top-Videos nach Aufrufen sortiert."""
    if not _key():
        return {"ok": False, "error": "YOUTUBE_API_KEY nicht gesetzt"}
    data = await _get("search", {
        "part": "snippet,id",
        "channelId": _channel(),
        "order": "viewCount",
        "maxResults": max_results,
        "type": "video",
    })
    if "error" in data:
        return {"ok": False, "error": data["error"]}

    items = data.get("items", [])
    if not items:
        return {"ok": True, "videos": []}

    video_ids = ",".join(i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId"))
    stats_data = await _get("videos", {"part": "statistics,snippet", "id": video_ids})

    videos = []
    for v in stats_data.get("items", []):
        st = v.get("statistics", {})
        sn = v.get("snippet", {})
        videos.append({
            "id": v["id"],
            "title": sn.get("title", ""),
            "published": sn.get("publishedAt", "")[:10],
            "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)),
            "url": f"https://youtube.com/watch?v={v['id']}",
        })
    videos.sort(key=lambda x: x["views"], reverse=True)
    return {"ok": True, "videos": videos}


async def get_full_dashboard() -> Dict:
    """Vollständiges YouTube Dashboard — Kanal + Videos + Top."""
    import asyncio
    stats, latest, top = await asyncio.gather(
        get_channel_stats(),
        get_latest_videos(5),
        get_top_videos(5),
    )
    return {
        "ok": True,
        "channel": stats,
        "latest_videos": latest.get("videos", []),
        "top_videos": top.get("videos", []),
        "total_video_count": stats.get("video_count", 0),
        "subscribers": stats.get("subscribers", 0),
        "total_views": stats.get("total_views", 0),
    }
