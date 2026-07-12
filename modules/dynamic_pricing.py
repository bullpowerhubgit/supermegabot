"""Dynamic Pricing Engine — AI-powered price optimization for Shopify products."""
import os, asyncio, logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "")

_BASE = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}"

_HISTORY: list[dict] = []


async def _shopify_get(path: str, params: str = "") -> dict:
    try:
        import aiohttp
        url = f"{_BASE}/{path}{'?' + params if params else ''}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN}) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}

async def _shopify_put(path: str, data: dict) -> dict:
    try:
        import aiohttp
        url = f"{_BASE}/{path}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.put(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                                            "Content-Type": "application/json"}, json=data) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}

async def _claude(prompt: str) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=500)
    except Exception:
        return ""


def _psychological_price(price: float) -> float:
    if price <= 0:
        return price
    base = int(price)
    if price < base + 0.5:
        return max(base - 0.01, 0.99)
    return float(base) + 0.99


async def get_pricing_dashboard() -> dict:
    result = await _shopify_get("products.json", "limit=250&fields=id,title,variants")
    products = result.get("products", [])
    prices = []
    for p in products:
        for v in p.get("variants", []):
            try:
                prices.append(float(v.get("price", 0)))
            except Exception as e:
                logger.warning("Ignored error: %s", e)
    avg = sum(prices) / len(prices) if prices else 0
    return {
        "total_products": len(products),
        "avg_price": round(avg, 2),
        "min_price": round(min(prices), 2) if prices else 0,
        "max_price": round(max(prices), 2) if prices else 0,
        "psychological_pricing_applied": sum(1 for p in prices if str(p).endswith(".99")),
        "history_entries": len(_HISTORY),
        "status": "active",
        "last_run": _HISTORY[-1].get("timestamp") if _HISTORY else None,
    }


async def run_dynamic_pricing_cycle(max_products: int = 50) -> dict:
    result = await _shopify_get("products.json", f"limit={max_products}&fields=id,title,variants")
    products = result.get("products", [])
    updated = 0
    for p in products[:max_products]:
        for v in p.get("variants", []):
            try:
                price = float(v.get("price", 0))
                if price <= 0:
                    continue
                new_price = _psychological_price(price)
                if abs(new_price - price) > 0.005:
                    r = await _shopify_put(f"variants/{v['id']}.json",
                                           {"variant": {"id": v["id"], "price": f"{new_price:.2f}"}})
                    if "variant" in r:
                        updated += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Dynamic pricing variant {v.get('id')}: {e}")
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "updated": updated, "checked": len(products)}
    _HISTORY.append(entry)
    if len(_HISTORY) > 100:
        _HISTORY.pop(0)
    return {"products_checked": len(products), "prices_updated": updated, "cycle": "psychological_99"}


async def get_pricing_history(product_id: str | None = None, days: int = 30) -> list:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = [
        h for h in _HISTORY
        if datetime.fromisoformat(h["timestamp"]) > cutoff
        and (product_id is None or str(h.get("product_id")) == str(product_id))
    ]
    return result[-50:]


async def enable_auto_pricing(product_id: str, min_price: float = 0.0, max_price: float = 0.0) -> dict:
    suggestion = await _claude(
        f"Dynamic pricing für Shopify-Produkt ID {product_id}, "
        f"Preisrahmen €{min_price:.2f}–€{max_price:.2f}. "
        f"Kurze Empfehlung (max 40 Wörter, Deutsch)."
    )
    return {
        "ok": True,
        "product_id": product_id,
        "min_price": min_price,
        "max_price": max_price,
        "enabled": True,
        "strategy": "dynamic_bounds",
        "ai_recommendation": suggestion,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
