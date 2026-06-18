"""SEO Traffic Engine Bridge — module for SuperMegaBot."""
import asyncio
import logging
import os
import urllib.parse

import aiohttp

log = logging.getLogger("seo_bridge")
SEO_ENGINE_URL = os.getenv("SEO_ENGINE_URL", "https://seo-traffic-engine-production.up.railway.app")
AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpower-21")
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")


async def get_amazon_products(keyword: str, limit: int = 5) -> list:
    """Returns Amazon affiliate search links for keyword."""
    url = f"https://www.amazon.de/s?k={urllib.parse.quote(keyword)}&tag={AMAZON_TAG}"
    return [{"title": f"Amazon Produkte: {keyword}", "url": url, "source": "amazon", "type": "search"}]


async def get_ebay_products(keyword: str, limit: int = 5) -> list:
    """Returns eBay products via API or search fallback."""
    if EBAY_APP_ID:
        try:
            params = {
                "OPERATION-NAME": "findItemsByKeywords",
                "SERVICE-VERSION": "1.0.0",
                "SECURITY-APPNAME": EBAY_APP_ID,
                "RESPONSE-DATA-FORMAT": "JSON",
                "keywords": keyword,
                "paginationInput.entriesPerPage": str(limit),
            }
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://svcs.ebay.com/services/search/FindingService/v1",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = (
                            data.get("findItemsByKeywordsResponse", [{}])[0]
                            .get("searchResult", [{}])[0]
                            .get("item", [])
                        )
                        return [
                            {
                                "title": i.get("title", [""])[0],
                                "url": i.get("viewItemURL", [""])[0],
                                "price": (
                                    i.get("sellingStatus", [{}])[0]
                                    .get("currentPrice", [{}])[0]
                                    .get("__value__", "")
                                ),
                                "source": "ebay",
                            }
                            for i in items[:limit]
                        ]
        except Exception as e:
            log.warning(f"eBay API: {e}")
    return [
        {
            "title": f"eBay Produkte: {keyword}",
            "url": f"https://www.ebay.de/sch/i.html?_nkw={urllib.parse.quote(keyword)}",
            "source": "ebay",
            "type": "search",
        }
    ]


async def push_keyword_to_seo(keyword: str) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{SEO_ENGINE_URL}/api/trigger/articles",
                json={"keyword": keyword},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                ok = r.status == 200
                log.info(f"SEO keyword push '{keyword}': {'ok' if ok else 'fail'}")
                return ok
    except Exception as e:
        log.warning(f"SEO push error: {e}")
        return False


async def get_marketplace_products(keyword: str, source: str = "all", limit: int = 5) -> dict:
    """Get products from Amazon and/or eBay."""
    result: dict = {"keyword": keyword, "amazon": [], "ebay": []}
    if source in ("amazon", "all"):
        result["amazon"] = await get_amazon_products(keyword, limit)
    if source in ("ebay", "all"):
        result["ebay"] = await get_ebay_products(keyword, limit)
    return result


async def get_seo_stats() -> dict:
    """Get article stats from SEO traffic engine."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{SEO_ENGINE_URL}/stats",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return {}
