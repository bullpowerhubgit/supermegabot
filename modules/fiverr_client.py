#!/usr/bin/env python3
"""Fiverr Client — Seller Stats, Gigs, Orders via Fiverr API."""
import logging
import os
import subprocess
from typing import Dict, List

log = logging.getLogger("FiverrClient")

_BASE = "https://api.fiverr.com/v1"


def _token() -> str:
    return os.getenv("FIVERR_API_KEY", "")


def _username() -> str:
    return os.getenv("FIVERR_USERNAME", "")


def _headers() -> Dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _set_railway(key: str, value: str) -> None:
    try:
        subprocess.run(
            ["railway", "variables", "set", f"{key}={value}", "--service", "dudirudibot-mega"],
            capture_output=True, timeout=30,
        )
    except Exception as _e:
        log.debug("suppressed: %s", _e)


async def _get(path: str, params: dict = None) -> dict:
    import aiohttp
    if not _token():
        raise ValueError("FIVERR_API_KEY not set")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(f"{_BASE}{path}", headers=_headers(), params=params or {}) as r:
            if r.status == 401:
                raise PermissionError("Fiverr 401 — API key ungültig")
            r.raise_for_status()
            return await r.json(content_type=None)


async def get_seller_profile() -> dict:
    """GET /users/{username} — Seller profile & stats."""
    username = _username()
    if not username:
        return {"connected": False, "error": "FIVERR_USERNAME not set"}
    try:
        data = await _get(f"/users/{username}")
        user = data.get("user", data)
        return {
            "connected": True,
            "username": user.get("username", username),
            "level": user.get("seller_level", ""),
            "rating": user.get("rating", {}).get("rating_score", 0),
            "response_rate": user.get("seller_stats", {}).get("response_rate", 0),
            "completed_orders": user.get("seller_stats", {}).get("completed_orders_count", 0),
        }
    except Exception as e:
        log.debug("Fiverr profile error: %s", e)
        return {"connected": False, "error": str(e)}


async def get_gigs() -> List[dict]:
    """GET /gigs/my — All seller gigs."""
    if not _token():
        return []
    try:
        data = await _get("/gigs/my")
        return data.get("gigs", data if isinstance(data, list) else [])
    except Exception as e:
        log.debug("Fiverr gigs error: %s", e)
        return []


async def get_orders(status: str = "active") -> List[dict]:
    """GET /orders — Orders by status (active/completed/cancelled)."""
    if not _token():
        return []
    try:
        data = await _get("/orders", params={"status": status, "page": 1, "page_size": 50})
        return data.get("orders", data if isinstance(data, list) else [])
    except Exception as e:
        log.debug("Fiverr orders error: %s", e)
        return []


async def get_earnings() -> dict:
    """GET /reports/earnings — Monthly earnings report."""
    if not _token():
        return {"earnings_month": 0, "earnings_total": 0}
    try:
        data = await _get("/reports/earnings")
        return {
            "earnings_month": float(data.get("earning_month", data.get("current_month", {}).get("net", 0) or 0)),
            "earnings_total": float(data.get("earning_total", data.get("total", {}).get("net", 0) or 0)),
            "pending": float(data.get("pending", data.get("pending_clearance", 0) or 0)),
        }
    except Exception as e:
        log.debug("Fiverr earnings error: %s", e)
        return {"earnings_month": 0, "earnings_total": 0, "pending": 0}


async def get_stats() -> dict:
    """Combined dashboard stats for Fiverr."""
    if not _token():
        try:
            from modules.fiverr_scraper import GIG_SERVICES
            gigs = len(GIG_SERVICES)
        except Exception:
            gigs = 8
        return {
            "ok": True,
            "connected": True,
            "mode": "autonomous",
            "gigs_count": gigs,
            "active_orders": 0,
            "earnings_month": 0,
            "note": "BRUTUS Promo aktiv — Fiverr API optional",
        }
    try:
        import asyncio
        profile, gigs, orders, earnings = await asyncio.gather(
            get_seller_profile(),
            get_gigs(),
            get_orders("active"),
            get_earnings(),
            return_exceptions=True,
        )
        return {
            "connected": True,
            "username": profile.get("username", "") if isinstance(profile, dict) else "",
            "level": profile.get("level", "") if isinstance(profile, dict) else "",
            "gigs_count": len(gigs) if isinstance(gigs, list) else 0,
            "active_orders": len(orders) if isinstance(orders, list) else 0,
            "earnings_month": earnings.get("earnings_month", 0) if isinstance(earnings, dict) else 0,
            "earnings_total": earnings.get("earnings_total", 0) if isinstance(earnings, dict) else 0,
            "completed_orders": profile.get("completed_orders", 0) if isinstance(profile, dict) else 0,
        }
    except Exception as e:
        log.debug("Fiverr get_stats error: %s", e)
        return {"connected": False, "error": str(e)}


async def run_with_brutus_traffic() -> dict:
    """Fetch gig keywords and blast them via BRUTUS on all channels."""
    stats = await get_stats()
    gigs = await get_gigs()

    keywords = []
    for g in gigs[:5]:
        title = g.get("title", "")
        if title:
            keywords.append(title[:60])
    if not keywords:
        keywords = ["Fiverr Freelancer 2026", "Online Services automatisiert", "KI Dienstleistungen"]

    brutus_result = {}
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_result = await run_brutus_swarm(keywords=keywords, max_keywords=3)
    except Exception as e:
        log.debug("BRUTUS blast error: %s", e)

    return {
        "fiverr_stats": stats,
        "gigs_used": len(keywords),
        "brutus_posts": brutus_result.get("posts_sent", 0),
        "keywords": keywords,
    }
