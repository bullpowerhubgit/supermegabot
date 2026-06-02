"""
Printify API Client mit voller Automatisierung
Unterstützt Shopify-Sync, Produkt-Automatisierung und Bestellabwicklung
"""

import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Printify API Config
PRINTIFY_API_KEY = os.getenv("PRINTIFY_API_KEY", "")
PRINTIFY_SHOP_ID = os.getenv("PRINTIFY_SHOP_ID", "")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


def _client_session(total_timeout: int = 30):
    """Use threaded DNS resolution to avoid broken async DNS providers."""
    resolver = aiohttp.resolver.ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=total_timeout)
    return aiohttp.ClientSession(timeout=timeout, connector=connector)


async def _printify_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
    """Printify API Request"""
    if not HAS_AIOHTTP:
        return {"error": "aiohttp not installed"}
    
    if not PRINTIFY_API_KEY:
        return {"error": "PRINTIFY_API_KEY not configured"}
    
    url = f"https://api.printify.com/v1{endpoint}"
    headers = {
        "Authorization": f"Bearer {PRINTIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with _client_session(30) as session:
            if method == "GET":
                async with session.get(url, headers=headers) as resp:
                    return await resp.json()
            elif method == "POST":
                async with session.post(url, json=data, headers=headers) as resp:
                    return await resp.json()
            elif method == "PUT":
                async with session.put(url, json=data, headers=headers) as resp:
                    return await resp.json()
            elif method == "DELETE":
                async with session.delete(url, headers=headers) as resp:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Printify API error: {e}")
        return {"error": str(e)}


# ─── Shop Management ───────────────────────────────────────────────────────

async def get_shops() -> List[Dict]:
    """Alle Printify Shops abrufen"""
    result = await _printify_request("GET", "/shops.json")
    return result if isinstance(result, list) else []


async def get_shop_info(shop_id: str = None) -> Dict:
    """Shop-Info abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    return await _printify_request("GET", f"/shops/{shop_id}.json")


# ─── Product Management ─────────────────────────────────────────────────────

async def get_products(shop_id: str = None, limit: int = 50) -> List[Dict]:
    """Produkte abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return []
    
    result = await _printify_request("GET", f"/shops/{shop_id}/products.json")
    if isinstance(result, list):
        return result[:limit]
    return []


async def get_product(product_id: str, shop_id: str = None) -> Dict:
    """Einzelnes Produkt abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    return await _printify_request("GET", f"/shops/{shop_id}/products/{product_id}.json")


async def create_product(shop_id: str = None, product_data: Dict = None) -> Dict:
    """Neues Produkt erstellen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    if not product_data:
        return {"error": "No product data provided"}
    
    return await _printify_request("POST", f"/shops/{shop_id}/products.json", product_data)


async def update_product(product_id: str, shop_id: str = None, product_data: Dict = None) -> Dict:
    """Produkt aktualisieren"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    if not product_data:
        return {"error": "No product data provided"}
    
    return await _printify_request("PUT", f"/shops/{shop_id}/products/{product_id}.json", product_data)


async def delete_product(product_id: str, shop_id: str = None) -> Dict:
    """Produkt löschen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    return await _printify_request("DELETE", f"/shops/{shop_id}/products/{product_id}.json")


async def publish_product(product_id: str, shop_id: str = None) -> Dict:
    """Produkt veröffentlichen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    return await _printify_request("POST", f"/shops/{shop_id}/products/{product_id}/publish.json")


# ─── Shopify Integration ────────────────────────────────────────────────────

async def get_shopify_connections(shop_id: str = None) -> List[Dict]:
    """Shopify-Verbindungen abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return []
    
    result = await _printify_request("GET", f"/shops/{shop_id}/shopify/connect.json")
    return result if isinstance(result, list) else []


async def sync_to_shopify(product_id: str, shop_id: str = None) -> Dict:
    """Produkt zu Shopify synchronisieren"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    # First check if Shopify is connected
    connections = await get_shopify_connections(shop_id)
    if not connections:
        return {"error": "Shopify not connected to this Printify shop"}
    
    return await _printify_request("POST", f"/shops/{shop_id}/products/{product_id}/publish.json")


# ─── Order Management ───────────────────────────────────────────────────────

async def get_orders(shop_id: str = None, limit: int = 50) -> List[Dict]:
    """Bestellungen abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return []
    
    result = await _printify_request("GET", f"/shops/{shop_id}/orders.json")
    if isinstance(result, list):
        return result[:limit]
    return []


async def get_order(order_id: str, shop_id: str = None) -> Dict:
    """Einzelne Bestellung abrufen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    return await _printify_request("GET", f"/shops/{shop_id}/orders/{order_id}.json")


async def create_order(shop_id: str = None, order_data: Dict = None) -> Dict:
    """Neue Bestellung erstellen"""
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    if not order_data:
        return {"error": "No order data provided"}
    
    return await _printify_request("POST", f"/shops/{shop_id}/orders.json", order_data)


# ─── Full Automation Functions ──────────────────────────────────────────────

async def full_automation_sync(shop_id: str = None) -> Dict:
    """
    Volle Automatisierung: Alle Produkte zu Shopify synchronisieren
    """
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    try:
        # Alle Produkte abrufen
        products = await get_products(shop_id)
        
        results = {
            "total_products": len(products),
            "synced": 0,
            "failed": 0,
            "errors": []
        }
        
        for product in products:
            try:
                product_id = product.get("id")
                if product_id:
                    # Produkt zu Shopify veröffentlichen
                    sync_result = await sync_to_shopify(product_id, shop_id)
                    if "error" not in sync_result:
                        results["synced"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append({
                            "product_id": product_id,
                            "error": sync_result.get("error")
                        })
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "product_id": product.get("id"),
                    "error": str(e)
                })
        
        results["timestamp"] = datetime.now().isoformat()
        return results
        
    except Exception as e:
        return {"error": str(e)}


async def auto_publish_new_products(shop_id: str = None) -> Dict:
    """
    Automatisches Veröffentlichen neuer Produkte
    """
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    try:
        products = await get_products(shop_id)
        
        results = {
            "total": len(products),
            "published": 0,
            "already_published": 0,
            "failed": 0
        }
        
        for product in products:
            product_id = product.get("id")
            is_published = product.get("published_at")
            
            if not is_published:
                try:
                    publish_result = await publish_product(product_id, shop_id)
                    if "error" not in publish_result:
                        results["published"] += 1
                    else:
                        results["failed"] += 1
                except Exception as e:
                    results["failed"] += 1
            else:
                results["already_published"] += 1
        
        results["timestamp"] = datetime.now().isoformat()
        return results
        
    except Exception as e:
        return {"error": str(e)}


async def get_automation_status(shop_id: str = None) -> Dict:
    """
    Status der Automatisierung abrufen
    """
    shop_id = shop_id or PRINTIFY_SHOP_ID
    if not shop_id:
        return {"error": "No shop ID provided"}
    
    try:
        products = await get_products(shop_id)
        orders = await get_orders(shop_id)
        connections = await get_shopify_connections(shop_id)
        
        return {
            "shop_id": shop_id,
            "total_products": len(products),
            "total_orders": len(orders),
            "shopify_connected": len(connections) > 0,
            "shopify_connections": connections,
            "last_sync": datetime.now().isoformat(),
            "automation_enabled": True
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Test ───────────────────────────────────────────────────────────────────

async def _test():
    """Test-Funktion"""
    shops = await get_shops()
    print(f"Shops: {len(shops)}")
    
    if shops:
        shop_id = shops[0].get("id")
        status = await get_automation_status(shop_id)
        print(f"Status: {status}")


if __name__ == "__main__":
    asyncio.run(_test())
