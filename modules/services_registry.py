"""
Live service registry — all deployed Railway services with health check.
"""
import os
import logging
import aiohttp

log = logging.getLogger(__name__)

SERVICES = [
    {"name": "supermegabot",          "url": "https://dudirudibot-mega-production.up.railway.app",          "revenue": True},
    {"name": "shopify-acquisition",   "url": "https://shopify-acquisition-engine-production.up.railway.app", "revenue": True},
    {"name": "seo-turbo-tools",       "url": "https://seo-turbo-tools-production.up.railway.app",            "revenue": True},
    {"name": "steuercockpit",         "url": "https://steuercockpit-production-44c9.up.railway.app",         "revenue": True},
    {"name": "icomeauto",             "url": "https://icomeauto-production-e4e5.up.railway.app",             "revenue": True},
    {"name": "adposter-engine",       "url": "https://adposter-engine-production-2d15.up.railway.app",      "revenue": False},
]

async def check_all() -> list:
    results = []
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for svc in SERVICES:
            try:
                async with session.get(f"{svc['url']}/health") as r:
                    data = await r.json()
                    results.append({**svc, "status": data.get("status", "unknown"), "http": r.status})
            except Exception as e:
                results.append({**svc, "status": "unreachable", "error": str(e)[:80]})
    return results
