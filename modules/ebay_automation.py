"""
eBay Automation — vollautonome eBay-Integration
- eBay Finding API: Produkte suchen (trending, bestseller)
- eBay Partner Network: Affiliate-Links generieren
- Shopify-Import: eBay-Produkte als Dropshipping-Produkte einpflegen
- BrutusCore: Neue Funde auf allen Kanälen posten
- Autonomous Loop: läuft alle 4h im Scheduler
"""
import os
import logging
import asyncio
import aiohttp
import json
import re
from datetime import datetime
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

EBAY_CLIENT_ID     = os.getenv("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "")
EBAY_CAMPAIGN_ID   = os.getenv("EBAY_CAMPAIGN_ID", "5339107261")
EBAY_CUSTOM_ID     = os.getenv("EBAY_CUSTOM_ID", "supermegabot")
EBAY_SITE_ID       = os.getenv("EBAY_SITE_ID", "77")  # 77=DE, 3=UK, 0=US
SHOPIFY_DOMAIN     = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN      = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
ANTHROPIC_KEY      = os.getenv("ANTHROPIC_API_KEY", "")

EBAY_FINDING_URL   = "https://svcs.ebay.com/services/search/FindingService/v1"
EBAY_TOKEN_URL     = "https://api.ebay.com/identity/v1/oauth2/token"

_ebay_token: str = ""
_token_expires: float = 0.0

TRENDING_KEYWORDS = [
    "smart home gadget", "led strip wifi", "fitness tracker 2026",
    "wireless earbuds", "phone case trending", "mini projector portable",
    "desk organizer", "kitchen gadget", "pet accessories", "travel accessory"
]


async def _get_app_token(session: aiohttp.ClientSession) -> str:
    global _ebay_token, _token_expires
    import time
    if _ebay_token and time.time() < _token_expires - 60:
        return _ebay_token
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        return ""
    try:
        import base64
        creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
        async with session.post(
            EBAY_TOKEN_URL,
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            d = await r.json()
            _ebay_token = d.get("access_token", "")
            _token_expires = time.time() + d.get("expires_in", 7200)
            return _ebay_token
    except Exception as e:
        logger.warning(f"eBay token error: {e}")
        return ""


def build_affiliate_link(ebay_url: str) -> str:
    """eBay Partner Network Rover-Link"""
    encoded = quote(ebay_url, safe="")
    return (
        f"https://rover.ebay.com/rover/1/707-53477-19255-0/1"
        f"?campid={EBAY_CAMPAIGN_ID}&toolid=10001"
        f"&customid={EBAY_CUSTOM_ID}&mpre={encoded}"
    )


async def search_items(keyword: str, count: int = 10, session: aiohttp.ClientSession = None) -> list:
    """eBay Finding API — sucht Produkte nach Keyword."""
    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": EBAY_CLIENT_ID,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": keyword,
        "paginationInput.entriesPerPage": str(min(count, 100)),
        "sortOrder": "BestMatch",
        "itemFilter(0).name": "Condition",
        "itemFilter(0).value": "New",
        "itemFilter(1).name": "LocatedIn",
        "itemFilter(1).value(0)": "DE",
        "itemFilter(1).value(1)": "AT",
        "outputSelector(0)": "PictureURLLarge",
        "outputSelector(1)": "SellerInfo",
    }
    url = f"{EBAY_FINDING_URL}?{urlencode(params)}"
    try:
        _sess = session or aiohttp.ClientSession()
        async with _sess.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await r.json(content_type=None)
        if not session:
            await _sess.close()

        items = (d.get("findItemsByKeywordsResponse", [{}])[0]
                  .get("searchResult", [{}])[0]
                  .get("item", []))
        result = []
        for item in items:
            price_str = (item.get("sellingStatus", [{}])[0]
                            .get("currentPrice", [{}])[0]
                            .get("__value__", "0"))
            img = (item.get("pictureURLLarge", [None])[0]
                   or item.get("galleryURL", [None])[0] or "")
            view_url = item.get("viewItemURL", [""])[0]
            result.append({
                "id":        item.get("itemId", [""])[0],
                "title":     item.get("title", [""])[0],
                "price_eur": float(price_str or 0),
                "image_url": img,
                "ebay_url":  view_url,
                "affiliate_url": build_affiliate_link(view_url) if view_url else "",
                "category":  item.get("primaryCategory", [{}])[0].get("categoryName", [""])[0],
            })
        return result
    except Exception as e:
        logger.error(f"eBay search '{keyword}': {e}")
        return []


async def _ai_improve(title: str, price: float, session: aiohttp.ClientSession) -> dict:
    """AI verbessert Titel + erstellt deutsche Beschreibung via Fallback-Chain."""
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f'Erstelle für dieses eBay-Produkt einen deutschen Shopify-Eintrag:\n"{title[:120]}"\n'
            f'Preis: €{price:.2f}\n'
            f'JSON: {{"title":"DE-Titel max 60 Zeichen","description":"HTML <p>+<ul>, 80-150 Wörter, kein eBay-Branding"}}'
        )
        txt = await ai_complete(prompt, max_tokens=400)
        if txt:
                m = re.search(r'\{[\s\S]+\}', txt)
                if m:
                    p = json.loads(m.group())
                    return {"title": p.get("title", title)[:70],
                            "description": p.get("description", f"<p>{title}</p>")}
    except Exception as e:
        logger.warning(f"eBay AI improve: {e}")
    return {"title": title[:70], "description": f"<p>{title}</p>"}


async def import_to_shopify(items: list, markup: float = 2.0) -> list:
    """Top eBay-Produkte als Shopify Dropshipping Produkte anlegen"""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    base = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}"
    imported = []
    async with aiohttp.ClientSession() as session:
        for item in items:
            if not item.get("price_eur") or item["price_eur"] < 1:
                continue
            sell_price = round(item["price_eur"] * markup, 2)
            improved = await _ai_improve(item["title"], sell_price, session)
            product = {
                "title": improved["title"],
                "body_html": improved["description"] + f'<p><small>Quelle: <a href="{item["affiliate_url"]}" target="_blank">eBay</a></small></p>',
                "vendor": "eBay Import",
                "product_type": item.get("category", "Gadget")[:50],
                "tags": "ebay,dropshipping,import,trending",
                "variants": [{
                    "price": str(sell_price),
                    "compare_at_price": str(round(sell_price * 1.3, 2)),
                    "inventory_management": None,
                    "inventory_policy": "continue",
                }],
            }
            if item.get("image_url"):
                product["images"] = [{"src": item["image_url"]}]
            try:
                async with session.post(f"{base}/products.json",
                                        json={"product": product}, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=20)) as r:
                    d = await r.json()
                    pid = d.get("product", {}).get("id")
                    imported.append({"ok": bool(pid), "shopify_id": pid,
                                     "title": improved["title"], "price": f"€{sell_price}",
                                     "ebay_id": item["id"], "affiliate": item["affiliate_url"]})
            except Exception as e:
                imported.append({"ok": False, "error": str(e), "ebay_id": item["id"]})
    return imported


async def run_ebay_auto_fill(keywords: list = None, items_per_kw: int = 5, markup: float = 2.0) -> dict:
    """Vollautomatisch: eBay suchen → Shopify importieren → BrutusCore feuern"""
    if not keywords:
        keywords = TRENDING_KEYWORDS[:5]

    all_items, all_imported = [], []
    async with aiohttp.ClientSession() as session:
        for kw in keywords:
            items = await search_items(kw, count=items_per_kw, session=session)
            all_items.extend(items)
            logger.info(f"eBay '{kw}': {len(items)} Produkte")
            await asyncio.sleep(0.5)

    if all_items:
        top = sorted(all_items, key=lambda x: x.get("price_eur", 0), reverse=True)[:15]
        all_imported = await import_to_shopify(top, markup=markup)

    ok = sum(1 for i in all_imported if i.get("ok"))

    # BrutusCore: neue eBay-Produkte auf allen Kanälen
    if ok > 0:
        try:
            from modules.brutus_core import fire as brutus_fire
            best = [i for i in all_imported if i.get("ok")][:2]
            for item in best:
                await brutus_fire(
                    title=f"🛒 eBay-Hit jetzt im Shop: {item['title'][:50]}",
                    body=f"Direkt importiert von eBay — {item['title']} für nur {item['price']}. Jetzt bestellen!",
                    link=f"https://{SHOPIFY_DOMAIN}/collections/all",
                    niche="dropshipping trending ebay gadgets",
                    tags=["ebay", "neu", "trending", "import"]
                )
        except Exception as e:
            logger.warning(f"eBay BrutusCore: {e}")

    result = {
        "found": len(all_items),
        "imported": ok,
        "failed": len(all_imported) - ok,
        "products": all_imported,
        "ts": datetime.utcnow().isoformat(),
    }
    logger.info(f"eBay Auto-Fill: {len(all_items)} gefunden, {ok} importiert")
    return result


async def post_affiliate_blast(niche: str = "smart home gadgets") -> dict:
    """Sucht Top-eBay-Produkte und postet Affiliate-Links via BrutusCore"""
    items = await search_items(niche, count=10)
    if not items:
        return {"ok": False, "reason": "no items found"}

    top3 = items[:3]
    lines = "\n".join([f"• {i['title'][:60]} — €{i['price_eur']:.2f} → {i['affiliate_url']}" for i in top3])
    try:
        from modules.brutus_core import fire as brutus_fire
        await brutus_fire(
            title=f"🔥 eBay Deals: {niche.title()}",
            body=f"Top Angebote heute:\n{lines}",
            link=top3[0]["affiliate_url"] if top3 else "https://ebay.de",
            niche=niche,
            tags=["ebay", "deals", "affiliate"]
        )
        return {"ok": True, "items": len(top3), "niche": niche}
    except Exception as e:
        return {"ok": False, "error": str(e)}
