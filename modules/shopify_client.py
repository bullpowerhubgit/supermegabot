"""
Shopify Admin API Client mit Auto-Refresh
Nutzt Shopify CLI identity tokens (atkn_2) mit automatischem Refresh
Fallback auf shpat_ wenn vorhanden
"""

import os
import time
import json
import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Config aus .env
STORE_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
STORE_URL = f"https://{STORE_DOMAIN}"
# Suite-Token bevorzugt (volle Scopes: products, orders, inventory, analytics, customers)
SHPAT_TOKEN = os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
CLI_CLIENT_ID = os.getenv("SHOPIFY_CLI_CLIENT_ID", "fbdb2649-e327-4907-8f67-908d24cfd7e3")
CLI_REFRESH_TOKEN = os.getenv("SHOPIFY_CLI_REFRESH_TOKEN", "")
# Railway Suite Dashboard URL
SUITE_URL = os.getenv("SHOPIFY_SUITE_URL", "https://shopify-suite-v2-production.up.railway.app")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# Token-Cache (im Speicher)
_token_cache: Dict[str, Any] = {
    "access_token": None,
    "expires_at": 0,
    "refresh_token": CLI_REFRESH_TOKEN,
}


async def _refresh_atkn_token() -> Optional[str]:
    """Refreshed den Shopify CLI identity token via accounts.shopify.com"""
    refresh_tok = _token_cache["refresh_token"] or CLI_REFRESH_TOKEN
    if not refresh_tok:
        return None

    if not HAS_AIOHTTP:
        return None

    try:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": CLI_CLIENT_ID,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://accounts.shopify.com/oauth/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_token = data.get("access_token")
                    new_refresh = data.get("refresh_token")
                    expires_in = data.get("expires_in", 7199)

                    if new_token:
                        _token_cache["access_token"] = new_token
                        _token_cache["expires_at"] = time.time() + expires_in - 60
                        if new_refresh:
                            _token_cache["refresh_token"] = new_refresh
                        logger.info("Shopify CLI token refreshed, expires in %ds", expires_in)
                        return new_token
                else:
                    body = await resp.text()
                    logger.warning("Token refresh failed %d: %s", resp.status, body[:200])
    except Exception as e:
        logger.warning("Token refresh error: %s", e)
    return None


async def _get_bearer_token() -> Optional[str]:
    """Gibt einen gültigen Bearer token zurück (refreshed bei Bedarf)"""
    # Noch gültig?
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]
    # Refresh
    return await _refresh_atkn_token()


def _get_auth_headers(bearer: Optional[str]) -> Dict[str, str]:
    """Wählt den besten verfügbaren Auth-Header"""
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}
    elif SHPAT_TOKEN and SHPAT_TOKEN != "NEUER_TOKEN_ERFORDERLICH":
        return {"X-Shopify-Access-Token": SHPAT_TOKEN}
    return {}


async def graphql(query: str, variables: Optional[Dict] = None) -> Dict:
    """Admin GraphQL Anfrage mit Auto-Auth"""
    if not HAS_AIOHTTP:
        return {"errors": "aiohttp not installed"}

    bearer = await _get_bearer_token()
    headers = {
        "Content-Type": "application/json",
        **_get_auth_headers(bearer),
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    url = f"{STORE_URL}/admin/api/2024-10/graphql.json"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            return data


async def rest_get(endpoint: str) -> Dict:
    """REST GET: endpoint z.B. 'products/count.json'"""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}

    bearer = await _get_bearer_token()
    headers = _get_auth_headers(bearer)
    url = f"{STORE_URL}/admin/api/2024-10/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            return await resp.json()


# ─── Convenience Functions ────────────────────────────────────────────────────

async def get_products(limit: int = 20, status: str = "any") -> list:
    """Produkte abrufen"""
    q = """
    query GetProducts($first: Int!) {
        products(first: $first) {
            edges { node {
                id title status totalInventory
                priceRangeV2 { minVariantPrice { amount currencyCode } }
                vendor productType tags
            }}
        }
    }
    """
    r = await graphql(q, {"first": limit})
    return [e["node"] for e in r.get("data", {}).get("products", {}).get("edges", [])]


async def get_orders(limit: int = 20, status: str = "any") -> list:
    """Bestellungen abrufen"""
    q = """
    query GetOrders($first: Int!) {
        orders(first: $first, sortKey: CREATED_AT, reverse: true) {
            edges { node {
                id name createdAt displayFulfillmentStatus displayFinancialStatus
                currentTotalPriceSet { shopMoney { amount currencyCode } }
                customer { email firstName lastName }
            }}
        }
    }
    """
    r = await graphql(q, {"first": limit})
    return [e["node"] for e in r.get("data", {}).get("orders", {}).get("edges", [])]


async def get_shop_info() -> Dict:
    """Shop-Info"""
    q = "{ shop { name email myshopifyDomain plan { displayName } currencyCode } }"
    r = await graphql(q)
    return r.get("data", {}).get("shop", {})


async def create_product(title: str, price: float, vendor: str = "", body_html: str = "",
                          product_type: str = "", tags: list = None) -> Dict:
    """Neues Produkt anlegen"""
    q = """
    mutation CreateProduct($input: ProductInput!) {
        productCreate(input: $input) {
            product { id title status }
            userErrors { field message }
        }
    }
    """
    variables = {
        "input": {
            "title": title,
            "vendor": vendor,
            "bodyHtml": body_html,
            "productType": product_type,
            "tags": tags or [],
            "variants": [{"price": str(price)}],
        }
    }
    r = await graphql(q, variables)
    return r.get("data", {}).get("productCreate", {})


async def get_analytics_summary() -> Dict:
    """Umsatz-Übersicht"""
    q = """
    {
        shop {
            name
            currencyCode
        }
        orders(first: 50, sortKey: CREATED_AT, reverse: true) {
            edges { node {
                currentTotalPriceSet { shopMoney { amount } }
                displayFinancialStatus
                createdAt
            }}
        }
    }
    """
    r = await graphql(q)
    if "data" not in r:
        return {}
    orders = [e["node"] for e in r["data"].get("orders", {}).get("edges", [])]
    total = sum(float(o["currentTotalPriceSet"]["shopMoney"]["amount"]) for o in orders)
    paid = [o for o in orders if o["displayFinancialStatus"] == "PAID"]
    return {
        "shop": r["data"].get("shop", {}).get("name", ""),
        "currency": r["data"].get("shop", {}).get("currencyCode", "EUR"),
        "orders_total": len(orders),
        "orders_paid": len(paid),
        "revenue": round(total, 2),
    }


# ─── GitHub-Shopify Integration ───────────────────────────────────────────────

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "bullpowerhubgit")


async def sync_products_to_github(repo: str = "shopify-products-backup") -> Dict:
    """Exportiert Produkte als JSON nach GitHub"""
    if not HAS_AIOHTTP or not GITHUB_TOKEN:
        return {"error": "GitHub token oder aiohttp fehlt"}

    products = await get_products(limit=250)
    content = json.dumps(products, indent=2, ensure_ascii=False, default=str)

    import base64
    encoded = base64.b64encode(content.encode()).decode()

    # Prüfe ob Datei schon existiert (für SHA)
    file_path = "products.json"
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    sha = None
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as resp:
            if resp.status == 200:
                existing = await resp.json()
                sha = existing.get("sha")

        payload = {
            "message": f"Shopify product sync {time.strftime('%Y-%m-%d %H:%M')}",
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha

        async with session.put(api_url, json=payload, headers=headers) as resp:
            result = await resp.json()
            if resp.status in (200, 201):
                return {"ok": True, "products": len(products), "url": result.get("content", {}).get("html_url")}
            return {"error": f"GitHub {resp.status}", "detail": str(result)[:200]}


async def github_shopify_webhook_deploy(repo: str, branch: str = "main") -> Dict:
    """Triggert GitHub Actions Workflow für Shopify Deploy"""
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN fehlt"}

    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo}/actions/workflows/shopify-deploy.yml/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {"ref": branch}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 204:
                return {"ok": True, "message": f"Deploy-Workflow gestartet für {repo}@{branch}"}
            return {"error": f"GitHub {resp.status}"}


# ─── Test ─────────────────────────────────────────────────────────────────────

async def _test():
    shop = await get_shop_info()
    print(f"Store: {shop}")
    products = await get_products(limit=3)
    print(f"Products ({len(products)}):")
    for p in products:
        print(f"  - {p['title']} | Status: {p['status']}")
    analytics = await get_analytics_summary()
    print(f"Analytics: {analytics}")


if __name__ == "__main__":
    asyncio.run(_test())
