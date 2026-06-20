#!/usr/bin/env python3
"""Upwork Client — Contracts, Earnings, Job Search via Upwork API v3 + OAuth 2.0."""
import logging
import os
import subprocess
from typing import Dict, List

log = logging.getLogger("UpworkClient")

_BASE     = "https://www.upwork.com/api"
_REDIRECT = "https://dudirudibot-mega-production.up.railway.app/api/upwork/callback"


def _access_token() -> str:
    return os.getenv("UPWORK_ACCESS_TOKEN", "")


def _client_id() -> str:
    return os.getenv("UPWORK_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("UPWORK_CLIENT_SECRET", "")


def _headers() -> Dict:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }


def _set_railway(key: str, value: str) -> None:
    try:
        subprocess.run(
            ["railway", "variables", "set", f"{key}={value}", "--service", "dudirudibot-mega"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


async def _get(path: str, params: dict = None) -> dict:
    import aiohttp
    if not _access_token():
        raise ValueError("UPWORK_ACCESS_TOKEN not set — visit /api/upwork/auth to connect")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(f"{_BASE}{path}", headers=_headers(), params=params or {}) as r:
            if r.status == 401:
                raise PermissionError("Upwork 401 — Token abgelaufen, OAuth neu starten")
            r.raise_for_status()
            return await r.json(content_type=None)


def get_oauth_url(state: str = "supermegabot") -> str:
    """Build Upwork OAuth2 authorization URL."""
    from urllib.parse import urlencode
    if not _client_id():
        raise ValueError("UPWORK_CLIENT_ID not set")
    params = urlencode({
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _REDIRECT,
        "state": state,
    })
    return f"https://www.upwork.com/ab/account-security/oauth2/authorize?{params}"


async def exchange_oauth_code(code: str) -> Dict:
    """Exchange authorization code for access + refresh token."""
    import aiohttp
    if not _client_id() or not _client_secret():
        return {"ok": False, "error": "UPWORK_CLIENT_ID / UPWORK_CLIENT_SECRET not set"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.upwork.com/api/v3/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _REDIRECT,
                    "client_id": _client_id(),
                    "client_secret": _client_secret(),
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)

        token = data.get("access_token", "")
        refresh = data.get("refresh_token", "")
        if not token:
            return {"ok": False, "error": str(data)}

        _set_railway("UPWORK_ACCESS_TOKEN", token)
        if refresh:
            _set_railway("UPWORK_REFRESH_TOKEN", refresh)
        log.info("Upwork OAuth token saved")
        return {"ok": True, "token_saved": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_profile() -> dict:
    """GET /api/profiles/v1/me.json — Freelancer profile."""
    try:
        data = await _get("/profiles/v1/me.json")
        p = data.get("profile", data)
        return {
            "connected": True,
            "name": p.get("name", ""),
            "title": p.get("title", ""),
            "rate": p.get("rate", {}).get("amount", {}).get("amount", 0),
            "total_hours": p.get("stats", {}).get("totalHours", 0),
            "total_jobs": p.get("stats", {}).get("totalJobsWorked", 0),
            "feedback_score": p.get("stats", {}).get("feedbackScore", 0),
        }
    except Exception as e:
        log.debug("Upwork profile error: %s", e)
        return {"connected": False, "error": str(e)}


async def get_active_contracts() -> List[dict]:
    """GET /api/hr/v2/engagements.json?status=active — Active contracts."""
    if not _access_token():
        return []
    try:
        data = await _get("/hr/v2/engagements.json", params={"status": "active", "page": 0, "per_page": 20})
        return data.get("engagements", {}).get("engagement", []) if isinstance(data.get("engagements"), dict) else []
    except Exception as e:
        log.debug("Upwork contracts error: %s", e)
        return []


async def get_earnings(months: int = 1) -> dict:
    """GET earnings report — monthly summary."""
    if not _access_token():
        return {"earnings_month": 0, "hours_month": 0}
    try:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        start = (now.replace(day=1) - timedelta(days=30 * (months - 1))).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        data = await _get(
            "/hr/v2/reports/provider/earnings/hours.json",
            params={"tq": f"SELECT amount,hours WHERE worked_on >= '{start}' AND worked_on <= '{end}'"}
        )
        rows = data.get("table", {}).get("rows", [])
        total_amount = sum(float(r.get("c", [{}])[0].get("v", 0) or 0) for r in rows)
        total_hours = sum(float(r.get("c", [{}])[-1].get("v", 0) or 0) for r in rows) if rows else 0
        return {
            "earnings_month": round(total_amount, 2),
            "hours_month": round(total_hours, 1),
            "period": f"{start} → {end}",
        }
    except Exception as e:
        log.debug("Upwork earnings error: %s", e)
        return {"earnings_month": 0, "hours_month": 0}


async def search_jobs(keywords: str = "python automation", budget_min: int = 100) -> List[dict]:
    """GET /api/profiles/v2/search/jobs.json — Job search."""
    if not _access_token():
        return []
    try:
        data = await _get(
            "/profiles/v2/search/jobs.json",
            params={"q": keywords, "budget": budget_min, "paging": "0;10"}
        )
        jobs = data.get("jobs", {})
        if isinstance(jobs, dict):
            jobs = jobs.get("job", [])
        return jobs[:10] if isinstance(jobs, list) else []
    except Exception as e:
        log.debug("Upwork job search error: %s", e)
        return []


async def get_stats() -> dict:
    """Combined dashboard stats for Upwork."""
    if not _access_token():
        return {
            "connected": False,
            "error": "UPWORK_ACCESS_TOKEN not set",
            "oauth_url": "/api/upwork/auth",
        }
    try:
        import asyncio
        profile, contracts, earnings = await asyncio.gather(
            get_profile(),
            get_active_contracts(),
            get_earnings(),
            return_exceptions=True,
        )
        return {
            "connected": True,
            "name": profile.get("name", "") if isinstance(profile, dict) else "",
            "rate_per_hour": profile.get("rate", 0) if isinstance(profile, dict) else 0,
            "feedback_score": profile.get("feedback_score", 0) if isinstance(profile, dict) else 0,
            "active_contracts": len(contracts) if isinstance(contracts, list) else 0,
            "earnings_month": earnings.get("earnings_month", 0) if isinstance(earnings, dict) else 0,
            "hours_month": earnings.get("hours_month", 0) if isinstance(earnings, dict) else 0,
            "total_jobs": profile.get("total_jobs", 0) if isinstance(profile, dict) else 0,
        }
    except Exception as e:
        log.debug("Upwork get_stats error: %s", e)
        return {"connected": False, "error": str(e)}


async def run_with_brutus_traffic() -> dict:
    """Search trending Upwork job keywords → blast via BRUTUS."""
    stats = await get_stats()
    keywords = [
        "KI Automatisierung Freelancer 2026",
        "Python Shopify Automation Developer",
        "E-Commerce Bot Development",
    ]

    brutus_result = {}
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_result = await run_brutus_swarm(keywords=keywords, max_keywords=3)
    except Exception as e:
        log.debug("BRUTUS blast error: %s", e)

    return {
        "upwork_stats": stats,
        "brutus_posts": brutus_result.get("posts_sent", 0),
        "keywords": keywords,
    }
