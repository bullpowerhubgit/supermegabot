#!/usr/bin/env python3
"""
Upwork Freelancer Automation — profile management, job search, proposal generation.
Requires: UPWORK_API_KEY, UPWORK_API_SECRET, UPWORK_ACCESS_TOKEN, UPWORK_ACCESS_SECRET
API: https://developers.upwork.com/
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import aiohttp

log = logging.getLogger("UpworkSync")

API_KEY = os.getenv("UPWORK_API_KEY", "")
API_SECRET = os.getenv("UPWORK_API_SECRET", "")
ACCESS_TOKEN = os.getenv("UPWORK_ACCESS_TOKEN", "")
ACCESS_SECRET = os.getenv("UPWORK_ACCESS_SECRET", "")
BASE = "https://www.upwork.com/api"
DS24 = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/669750")
SHOP = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")

_configured = bool(API_KEY and ACCESS_TOKEN)


async def get_status() -> dict:
    return {
        "configured": _configured,
        "api_key_set": bool(API_KEY),
        "access_token_set": bool(ACCESS_TOKEN),
        "note": "Set UPWORK_API_KEY + UPWORK_ACCESS_TOKEN from developers.upwork.com" if not _configured else "OK",
    }


async def search_jobs(keywords: str = "shopify automation ai") -> dict:
    """Search for relevant Upwork jobs."""
    if not _configured:
        return {"ok": False, "error": "Upwork credentials not configured", "jobs": []}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/profiles/v2/search/jobs.json",
                params={"q": keywords, "paging": "0;10"},
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        jobs = data.get("jobs", {}).get("job", [])
        return {"ok": True, "count": len(jobs), "jobs": jobs[:5]}
    except Exception as e:
        return {"ok": False, "error": str(e), "jobs": []}


async def generate_proposal(job_title: str = "", budget: str = "") -> str:
    """AI-generated Upwork proposal."""
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Schreibe ein professionelles Upwork Angebot (Cover Letter) auf Englisch für: "
            f"{job_title or 'Shopify / E-Commerce Automation'}. Budget: {budget or 'flexible'}. "
            f"Max 300 Wörter. Überzeugend, konkret, mit Erfahrungsnachweis."
        )
        return await ai_complete(prompt, max_tokens=300)
    except Exception:
        return (
            f"Hi! I specialize in Shopify automation, AI integration, and e-commerce optimization. "
            f"I've built complete automation pipelines handling 600+ products with autonomous marketing.\n\n"
            f"For your project, I'll deliver:\n✅ Complete implementation\n✅ Full testing\n"
            f"✅ Documentation\n✅ 30-day support\n\nLet's discuss details. Best, Rudolf"
        )


async def run_upwork_cycle() -> dict:
    """Scheduler entry: search jobs, generate proposals."""
    status = await get_status()
    jobs = await search_jobs() if _configured else {"ok": False, "jobs": []}
    proposal = await generate_proposal()
    log.info("Upwork cycle: configured=%s jobs=%s", _configured, jobs.get("count", 0))
    return {
        "ok": True,
        "configured": _configured,
        "jobs_found": jobs.get("count", 0),
        "proposal_generated": bool(proposal),
        "proposal_preview": proposal[:100],
        "note": "Set UPWORK_API_KEY + UPWORK_ACCESS_TOKEN to enable job search",
    }
