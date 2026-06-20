"""eBay Browse API + Affiliate Integration (EPN)."""
import os
import logging
import base64
from datetime import datetime, timezone

log = logging.getLogger("eBayClient")

EBAY_APP_ID       = os.getenv("EBAY_APP_ID", "")
EBAY_CERT_ID      = os.getenv("EBAY_CERT_ID", "")
EBAY_TOKEN        = os.getenv("EBAY_OAUTH_TOKEN", "")
EBAY_CAMPAIGN_ID  = os.getenv("EBAY_CAMPAIGN_ID", "5338722076")  # EPN default
EBAY_AFFILIATE_ID = os.getenv("EBAY_AFFILIATE_ID", "5575623462")  # EPN publisher default
EBAY_BASE         = "https://api.ebay.com/buy/browse/v1"
EBAY_AUTH_URL     = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SITE         = "EBAY_DE"


def build_affiliate_link(item_id: str) -> str:
    base = f"https://www.ebay.de/itm/{item_id}" if item_id else "https://www.ebay.de"
    if EBAY_CAMPAIGN_ID and EBAY_AFFILIATE_ID:
        return f"{base}?campid={EBAY_CAMPAIGN_ID}&customid=smb&toolid=10001&mkevt=1&mkcid=1&mkrid=707-53477-19255-0"
    return base


async def get_oauth_token() -> str:
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return ""
    try:
        import aiohttp
        creds = base64.b64encode(f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()).decode()
        async with aiohttp.ClientSession() as s:
            async with s.post(
                EBAY_AUTH_URL,
                headers={"Authorization": f"Basic {creds}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        token = data.get("access_token", "")
        log.info("eBay OAuth token obtained")
        return token
    except Exception as e:
        log.warning("eBay OAuth error: %s", e)
        return ""


async def search_items(keywords: str, limit: int = 10, category: str = "") -> dict:
    token = EBAY_TOKEN or await get_oauth_token()
    if not token:
        return {"ok": False, "error": "EBAY_APP_ID + EBAY_CERT_ID required", "items": []}
    try:
        import aiohttp
        params: dict = {"q": keywords, "limit": min(limit, 50)}
        if category:
            params["category_ids"] = category
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{EBAY_BASE}/item_summary/search",
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": EBAY_SITE,
                         "Content-Type": "application/json"},
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        result = []
        for item in data.get("itemSummaries", []):
            item_id = item.get("itemId", "").replace("v1|", "").split("|")[0]
            result.append({
                "id": item_id,
                "title": item.get("title", "")[:100],
                "price": item.get("price", {}).get("value", "0"),
                "currency": item.get("price", {}).get("currency", "EUR"),
                "image": (item.get("image") or {}).get("imageUrl", ""),
                "affiliate_link": build_affiliate_link(item_id),
                "condition": item.get("condition", ""),
                "seller": item.get("seller", {}).get("username", ""),
            })
        return {"ok": True, "items": result, "total": data.get("total", 0), "keywords": keywords}
    except Exception as e:
        log.warning("eBay search error: %s", e)
        return {"ok": False, "error": str(e), "items": []}


async def get_trending_items(category: str = "139973", limit: int = 10) -> dict:
    return await search_items("trending bestseller", limit=limit, category=category)


async def get_stats() -> dict:
    return {
        "ok": True,
        "configured": bool(EBAY_APP_ID and EBAY_CERT_ID),
        "epn_active": bool(EBAY_CAMPAIGN_ID and EBAY_AFFILIATE_ID),
        "app_id_set": bool(EBAY_APP_ID),
        "campaign_id_set": bool(EBAY_CAMPAIGN_ID),
        "marketplace": EBAY_SITE,
        "affiliate_base": "https://www.ebay.de",
        "affiliate_link_active": bool(EBAY_CAMPAIGN_ID),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def run_with_brutus_traffic(keywords: str = "trending bestseller online shop") -> dict:
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        items = await search_items(keywords, limit=5)
        kws = ["eBay Angebote Deutschland", "günstig kaufen online", "eBay Affiliate Deals", keywords]
        brutus_result = await run_brutus_swarm(keywords=kws, max_keywords=4)
        return {"ok": True, "items_found": len(items.get("items", [])), "brutus": brutus_result}
    except Exception as e:
        log.warning("eBay BRUTUS error: %s", e)
        return {"ok": False, "error": str(e)}
