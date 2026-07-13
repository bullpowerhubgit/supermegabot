"""
stripe_payment_links.py — Stripe Payment Links Generator & Manager
Creates and manages Stripe Payment Links for all active products.
"""
import os
import base64
import logging
import json
from datetime import datetime, timezone
import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_API_BASE  = "https://api.stripe.com/v1"
SHOP_THANK_YOU   = "https://ineedit.com.co/pages/danke"


def _stripe_auth() -> str:
    """Return Basic-auth header value for Stripe API."""
    token = base64.b64encode(f"{STRIPE_SECRET_KEY}:".encode()).decode()
    return f"Basic {token}"


async def _stripe_get(session: aiohttp.ClientSession, path: str, params: dict = None) -> dict:
    url = f"{STRIPE_API_BASE}{path}"
    async with session.get(url, params=params, headers={"Authorization": _stripe_auth()}) as r:
        return await r.json()


async def _stripe_post(session: aiohttp.ClientSession, path: str, data: dict) -> dict:
    url = f"{STRIPE_API_BASE}{path}"
    async with session.post(url, data=data, headers={"Authorization": _stripe_auth()}) as r:
        return await r.json()


async def get_all_payment_links() -> list:
    """GET /v1/payment_links — returns list of all payment links."""
    async with aiohttp.ClientSession() as session:
        result = await _stripe_get(session, "/payment_links", {"limit": "100"})
        links = result.get("data", [])
        log.info("Stripe: %d payment links fetched", len(links))
        return links


async def _get_active_prices(session: aiohttp.ClientSession) -> list:
    """Return all active prices with their product names."""
    result = await _stripe_get(session, "/prices", {
        "active": "true",
        "limit": "100",
        "expand[]": "data.product",
    })
    prices = []
    for p in result.get("data", []):
        product = p.get("product", {})
        if isinstance(product, dict) and product.get("active"):
            prices.append({
                "price_id":     p["id"],
                "product_id":   product.get("id", ""),
                "product_name": product.get("name", "Produkt"),
                "amount":       p.get("unit_amount", 0),
                "currency":     p.get("currency", "eur"),
            })
    return prices


async def _get_existing_link_price_ids(session: aiohttp.ClientSession) -> set:
    """Return set of price_ids that already have a payment link."""
    result = await _stripe_get(session, "/payment_links", {"limit": "100"})
    ids = set()
    for link in result.get("data", []):
        for item in link.get("line_items", {}).get("data", []):
            if item.get("price", {}).get("id"):
                ids.add(item["price"]["id"])
    return ids


async def create_payment_links_for_all_products() -> list:
    """
    Create a Stripe Payment Link for each active price that doesn't have one yet.
    Returns list of {product_name, payment_link_url, price_id}.
    """
    created = []
    async with aiohttp.ClientSession() as session:
        prices   = await _get_active_prices(session)
        existing = await _get_existing_link_price_ids(session)

        for price in prices:
            pid = price["price_id"]
            if pid in existing:
                log.debug("Payment link already exists for price %s — skipping", pid)
                continue

            safe_name = price["product_name"].replace(" ", "_").replace("/", "-")
            redirect_url = f"{SHOP_THANK_YOU}?product={safe_name}"

            payload = {
                "line_items[0][price]":    pid,
                "line_items[0][quantity]": "1",
                "after_completion[type]":                 "redirect",
                "after_completion[redirect][url]":        redirect_url,
                "allow_promotion_codes": "true",
                "billing_address_collection": "required",
            }
            resp = await _stripe_post(session, "/payment_links", payload)

            if resp.get("id"):
                entry = {
                    "product_name":     price["product_name"],
                    "payment_link_url": resp.get("url", ""),
                    "price_id":         pid,
                    "link_id":          resp["id"],
                }
                created.append(entry)
                log.info("Created payment link for '%s': %s", price["product_name"], resp.get("url"))
            else:
                log.warning("Failed to create link for %s: %s", pid, resp.get("error", {}).get("message"))

    log.info("Stripe Payment Links: %d created", len(created))
    return created


async def generate_product_landing_page(
    product_name: str,
    price: str,
    description: str,
    payment_link_url: str,
) -> str:
    """Return a simple HTML landing page for a product checkout."""
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{product_name} – Jetzt kaufen</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0f0f0f; color: #f0f0f0; min-height: 100vh;
          display: flex; align-items: center; justify-content: center; }}
  .card {{ background: #1a1a1a; border-radius: 16px; padding: 48px;
           max-width: 540px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,.6); }}
  h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 16px; color: #fff; }}
  .price {{ font-size: 2.8rem; font-weight: 800; color: #4ade80; margin: 24px 0; }}
  p {{ color: #aaa; line-height: 1.7; margin-bottom: 24px; }}
  .btn {{ display: block; width: 100%; padding: 18px; background: #4ade80;
          color: #000; font-size: 1.2rem; font-weight: 700; border: none;
          border-radius: 10px; cursor: pointer; text-align: center;
          text-decoration: none; transition: background .2s; }}
  .btn:hover {{ background: #22c55e; }}
  .trust {{ margin-top: 20px; font-size: .85rem; color: #666; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <h1>{product_name}</h1>
  <div class="price">{price}</div>
  <p>{description}</p>
  <a href="{payment_link_url}" class="btn">Jetzt kaufen &rarr;</a>
  <p class="trust">&#128274; Sicher & verschlüsselt · 30-Tage-Geld-zurück-Garantie</p>
</div>
</body>
</html>"""
    return html


def get_status() -> dict:
    """Return basic status dict (synchronous for quick health checks)."""
    stripe_ok = bool(STRIPE_SECRET_KEY)
    return {
        "module":          "stripe_payment_links",
        "stripe_key_set":  stripe_ok,
        "products_count":  0,
        "links_active":    0,
        "revenue_today":   0.0,
    }


# ── Route handler ─────────────────────────────────────────────────────────────

async def handle_stripe_links(req: web.Request) -> web.Response:
    """GET /api/stripe/payment-links — return all payment links as JSON."""
    try:
        links = await get_all_payment_links()
        return web.json_response({"ok": True, "count": len(links), "links": links})
    except Exception as exc:
        log.exception("handle_stripe_links error")
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
