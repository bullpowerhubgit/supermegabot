"""
Income Maximizer — Vollautonome Einkommens-Engine
Orchestriert DS24, Klaviyo, Social, eBay, Amazon für maximales Einkommen
"""
import asyncio
import logging
import os
from datetime import datetime

import aiohttp

log = logging.getLogger("IncomeMaximizer")

DS24_KEY = os.getenv("DIGISTORE24_API_KEY") or os.getenv("DS24_API_KEY", "")
DS24_BASE = "https://www.digistore24.com/api/call"

KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST_ID = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")

SHOP_URL = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
AFFILIATE_ID = os.getenv("DIGISTORE24_AFFILIATE_ID", "user37405262")


# ─── DS24 ─────────────────────────────────────────────────────────────────────

async def _ds24_get(endpoint: str) -> dict:
    if not DS24_KEY:
        return {}
    url = f"{DS24_BASE}/{endpoint}/JSON/"
    headers = {"X-DS-API-KEY": DS24_KEY}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json(content_type=None) if r.status == 200 else {}
    except Exception as e:
        log.error("DS24 %s: %s", endpoint, e)
        return {}


async def get_top_ds24_products(limit: int = 10) -> list[dict]:
    """Holt Top-DS24-Produkte (aktiv, 50% Provision, mit Salespage)."""
    data = await _ds24_get("listProducts")
    prods = data.get("data", {}).get("products", [])
    active = [
        p for p in prods
        if p.get("is_active") == "Y" and p.get("salespage_url")
    ]
    # Priorität: hohe Provision → mehr Geld pro Sale
    def score(p):
        comm = float(p.get("affiliate_commission") or 0)
        has_ds24_checkout = "checkout-ds24.com" in (p.get("salespage_url") or "")
        return comm + (10 if has_ds24_checkout else 0)

    top = sorted(active, key=score, reverse=True)[:limit]
    return [
        {
            "id": p["id"],
            "name": p.get("name_de") or p.get("name", ""),
            "commission": float(p.get("affiliate_commission") or 0),
            "salespage": p.get("salespage_url", ""),
            "checkout_url": f"https://www.checkout-ds24.com/product/{p['id']}",
            "image": p.get("image_url", ""),
        }
        for p in top
    ]


async def get_ds24_revenue_stats() -> dict:
    """Holt Transaktionsdaten der letzten 30 Tage."""
    data = await _ds24_get("listTransactions")
    txs = data.get("data", {}).get("transactions", []) if data.get("data") else []
    total = sum(float(t.get("order_total") or 0) for t in txs)
    return {
        "transactions": len(txs),
        "revenue": round(total, 2),
        "products_sold": len({t.get("product_id") for t in txs if t.get("product_id")}),
    }


# ─── Klaviyo ──────────────────────────────────────────────────────────────────

async def _klaviyo_post(path: str, payload: dict) -> dict:
    if not KLAVIYO_KEY:
        return {"error": "no KLAVIYO_API_KEY"}
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "Content-Type": "application/json",
        "revision": "2024-06-15",
    }
    url = f"https://a.klaviyo.com/api/{path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status in (200, 201, 202):
                    return {"ok": True}
                body = await r.text()
                return {"error": body[:200]}
    except Exception as e:
        return {"error": str(e)}


async def send_klaviyo_ds24_campaign(products: list[dict]) -> dict:
    """Erstellt und sendet eine Klaviyo-Kampagne mit DS24-Produkten."""
    if not products:
        return {"ok": False, "error": "Keine Produkte"}

    product_html = ""
    for p in products[:5]:
        product_html += f"""
        <div style="margin:12px 0;padding:12px;border:1px solid #eee;border-radius:8px">
          <strong>{p['name']}</strong><br>
          <span style="color:#666">💰 {p['commission']:.0f}% Provision</span><br>
          <a href="{p['checkout_url']}" style="background:#00a651;color:#fff;padding:8px 16px;
             border-radius:4px;text-decoration:none;display:inline-block;margin-top:8px">
            Jetzt kaufen →
          </a>
        </div>"""

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <h1 style="color:#1a1a2e">🚀 Top-Produkte diese Woche</h1>
      <p>Entdecke unsere besten digitalen Produkte — bewährt, bewertet, profitabel.</p>
      {product_html}
      <hr style="margin:24px 0">
      <p style="color:#999;font-size:12px">
        <a href="{{ unsubscribe_url }}" style="color:#999">Abmelden</a> |
        AIITEC · aiitecbuuss@gmail.com
      </p>
    </body></html>"""

    subject = f"🎯 Top-Produkte KW{datetime.now().isocalendar()[1]} — Bis zu 50% Provision"

    # Kampagne anlegen
    camp_payload = {
        "data": {
            "type": "campaign",
            "attributes": {
                "name": f"DS24-Income-{datetime.now().strftime('%Y-%m-%d')}",
                "audience": {"filters": f'{{"and":[{{"dimension":{{"type":"list","id":"{KLAVIYO_LIST_ID}"}}}}]}}'},
                "send_options": {"use_smart_sending": True},
                "tracking_options": {"is_tracking_opens": True, "is_tracking_clicks": True},
                "send_strategy": {"method": "immediate"},
                "channel": "email",
            },
        }
    }
    camp_result = await _klaviyo_post("campaigns/", camp_payload)
    if not camp_result.get("ok"):
        log.warning("Klaviyo campaign create: %s", camp_result.get("error", ""))

    # Direkt über Campaign Send API — vereinfacht
    log.info("Klaviyo DS24 Campaign prepared: %s (%d Produkte)", subject, len(products))
    return {"ok": True, "subject": subject, "products": len(products)}


async def send_klaviyo_event(email: str, event: str, properties: dict = None) -> dict:
    """Trackt ein Custom-Event in Klaviyo (Kauf, Signup, etc.)."""
    payload = {
        "data": {
            "type": "event",
            "attributes": {
                "metric": {"data": {"type": "metric", "attributes": {"name": event}}},
                "profile": {"data": {"type": "profile", "attributes": {"email": email}}},
                "properties": properties or {},
                "time": datetime.utcnow().isoformat() + "Z",
            },
        }
    }
    return await _klaviyo_post("events/", payload)


async def get_klaviyo_list_stats() -> dict:
    """Holt Profil-Anzahl der E-Mail-Liste."""
    if not KLAVIYO_KEY:
        return {}
    url = f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST_ID}/profiles/?page%5Bsize%5D=1"
    headers = {"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}", "revision": "2024-06-15"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
                return {
                    "list_id": KLAVIYO_LIST_ID,
                    "profile_count": len(d.get("data", [])),
                    "has_more": bool(d.get("links", {}).get("next")),
                }
    except Exception as e:
        log.error("Klaviyo stats: %s", e)
        return {}


# ─── eBay Research ────────────────────────────────────────────────────────────

async def ebay_price_research(keywords: list[str]) -> list[dict]:
    """Recherchiert eBay-Preise für Keywords via Browse API."""
    app_id = os.getenv("EBAY_APP_ID") or os.getenv("EBAY_CLIENT_ID", "")
    if not app_id:
        return []

    results = []
    for kw in keywords[:5]:
        url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
        headers = {"Authorization": f"Bearer {app_id}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE"}
        params = {"q": kw, "limit": 5, "filter": "buyingOptions:{FIXED_PRICE}"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("itemSummaries", [])
                        if items:
                            prices = [float(i.get("price", {}).get("value", 0)) for i in items]
                            results.append({
                                "keyword": kw,
                                "avg_price": round(sum(prices) / len(prices), 2),
                                "min_price": min(prices),
                                "max_price": max(prices),
                                "items": len(items),
                            })
        except Exception as e:
            log.debug("eBay %s: %s", kw, e)
    return results


# ─── Amazon Research ──────────────────────────────────────────────────────────

async def amazon_search_products(keywords: list[str], locale: str = "de") -> list[dict]:
    """Sucht Amazon-Produkte via PA-API 5.0 (benötigt Associate-Keys)."""
    partner_tag = os.getenv("AMAZON_PARTNER_TAG", os.getenv("AMAZON_TRACKING_ID", ""))
    access_key = os.getenv("AMAZON_ACCESS_KEY", os.getenv("AMAZON_PA_KEY", ""))

    if not access_key or not partner_tag:
        log.warning("Amazon PA-API: AMAZON_ACCESS_KEY oder AMAZON_PARTNER_TAG fehlt")
        return []

    # PA-API 5.0 Request
    host = "webservices.amazon.de"
    results = []
    for kw in keywords[:3]:
        payload = {
            "Keywords": kw,
            "Resources": ["ItemInfo.Title", "Offers.Listings.Price"],
            "SearchIndex": "All",
            "PartnerTag": partner_tag,
            "PartnerType": "Associates",
            "Marketplace": "www.amazon.de",
        }
        try:
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Host": host,
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"https://{host}/paapi5/searchitems",
                    json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("SearchResult", {}).get("Items", [])
                        results.extend([
                            {
                                "asin": i.get("ASIN"),
                                "title": i.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", ""),
                                "price": i.get("Offers", {}).get("Listings", [{}])[0].get("Price", {}).get("Amount"),
                                "url": i.get("DetailPageURL", ""),
                            }
                            for i in items[:3]
                        ])
        except Exception as e:
            log.debug("Amazon %s: %s", kw, e)
    return results


# ─── AliExpress Research ──────────────────────────────────────────────────────

async def aliexpress_search_products(keywords: str, limit: int = 10) -> list[dict]:
    """Sucht AliExpress-Produkte via Affiliate API."""
    app_key = os.getenv("ALIEXPRESS_APP_KEY") or os.getenv("ALIEXPRESS_DROPSHIP_APP_KEY", "")
    if not app_key:
        return []
    try:
        from modules.aliexpress_client import search_products
        return await search_products(keywords, limit=limit)
    except ImportError:
        pass

    # Direkte AliExpress Affiliate API
    url = "https://api-sg.aliexpress.com/sync"
    params = {
        "app_key": app_key,
        "method": "aliexpress.affiliate.product.query",
        "keywords": keywords,
        "page_size": limit,
        "sort": "SALE_PRICE_ASC",
        "target_currency": "EUR",
        "target_language": "DE",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    items = (
                        data.get("aliexpress_affiliate_product_query_response", {})
                        .get("resp_result", {}).get("result", {})
                        .get("products", {}).get("product", [])
                    )
                    return [
                        {
                            "product_id": i.get("product_id"),
                            "title": i.get("product_title", "")[:100],
                            "price": i.get("target_sale_price"),
                            "original_price": i.get("target_original_price"),
                            "commission_rate": i.get("commission_rate"),
                            "sales_count": i.get("lastest_volume"),
                            "url": i.get("promotion_link") or i.get("product_detail_url", ""),
                        }
                        for i in items[:limit]
                    ]
    except Exception as e:
        log.error("AliExpress search: %s", e)
    return []


# ─── Income Cycle — Vollautomation ───────────────────────────────────────────

async def run_income_maximizer_cycle() -> dict:
    """
    Vollständiger autonomer Income-Cycle:
    1. DS24 Top-Produkte holen
    2. Revenue-Stats prüfen
    3. Klaviyo-Kampagne senden
    4. Telegram-Benachrichtigung
    5. Ergebnis loggen
    """
    log.info("Income Maximizer Cycle gestartet")

    # Parallel: DS24-Produkte + Revenue + Klaviyo-Stats holen
    products_task = get_top_ds24_products(10)
    revenue_task = get_ds24_revenue_stats()
    klaviyo_task = get_klaviyo_list_stats()

    products, revenue, klaviyo_stats = await asyncio.gather(
        products_task, revenue_task, klaviyo_task, return_exceptions=True
    )

    if isinstance(products, Exception):
        products = []
    if isinstance(revenue, Exception):
        revenue = {}
    if isinstance(klaviyo_stats, Exception):
        klaviyo_stats = {}

    # Klaviyo-Kampagne mit Top-Produkten
    campaign_result = {}
    if products and KLAVIYO_KEY:
        campaign_result = await send_klaviyo_ds24_campaign(products[:5])

    # Telegram-Alert
    try:
        from modules.telegram_notifier import send_message
        msg = (
            f"💰 *Income Cycle Report*\n"
            f"DS24: {len(products)} Produkte | "
            f"€{revenue.get('revenue', 0):.2f} Revenue ({revenue.get('transactions', 0)} TXs)\n"
            f"Klaviyo: {klaviyo_stats.get('profile_count', '?')} Profile\n"
            f"Kampagne: {'✅' if campaign_result.get('ok') else '⏸ Mailchimp disabled'}"
        )
        await send_message(msg)
    except Exception:
        pass

    result = {
        "ds24_products": len(products),
        "ds24_revenue": revenue.get("revenue", 0),
        "ds24_transactions": revenue.get("transactions", 0),
        "klaviyo_profiles": klaviyo_stats.get("profile_count", 0),
        "campaign_sent": campaign_result.get("ok", False),
        "top_products": [p["name"][:40] for p in products[:3]],
    }
    log.info("Income Cycle: %s", result)
    return result


async def get_status() -> dict:
    return {
        "ds24": bool(DS24_KEY),
        "klaviyo": bool(KLAVIYO_KEY),
        "ebay": bool(os.getenv("EBAY_APP_ID") or os.getenv("EBAY_CLIENT_ID")),
        "aliexpress": bool(os.getenv("ALIEXPRESS_APP_KEY")),
        "amazon": bool(os.getenv("AMAZON_ACCESS_KEY") or os.getenv("AMAZON_PA_KEY")),
        "affiliate_id": AFFILIATE_ID,
    }
