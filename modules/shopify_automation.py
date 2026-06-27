"""
Shopify Automation — Bestell-Alarm, Produkt-Management, Analytics per Telegram.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from typing import Any, Optional

log = logging.getLogger("shopify_automation")

TELEGRAM_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN_2") or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-10")


def _shopify_get(endpoint: str) -> dict:
    domain = SHOPIFY_DOMAIN()
    token = SHOPIFY_TOKEN()
    if not domain or not token:
        return {"error": "Shopify nicht konfiguriert"}
    url = f"https://{domain}/admin/api/{API_VERSION()}/{endpoint}"
    req = urllib.request.Request(url, headers={
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _shopify_post(endpoint: str, data: dict) -> dict:
    domain = SHOPIFY_DOMAIN()
    token = SHOPIFY_TOKEN()
    if not domain or not token:
        return {"error": "Shopify nicht konfiguriert"}
    url = f"https://{domain}/admin/api/{API_VERSION()}/{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _tg_send_sync(text: str, chat_id: str = None) -> None:
    token = TELEGRAM_TOKEN()
    cid = chat_id or TELEGRAM_CHAT_ID()
    if not token or not cid:
        return
    data = json.dumps({"chat_id": cid, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.error("Telegram send error: %s", e)


# ── Bestellungen ────────────────────────────────────────────────────────────

def get_recent_orders(limit: int = 10) -> list[dict]:
    result = _shopify_get(f"orders.json?limit={limit}&status=any")
    return result.get("orders", [])


def format_orders_message(orders: list[dict]) -> str:
    if not orders:
        return "📦 Keine Bestellungen gefunden."
    lines = ["📦 *Letzte Bestellungen:*\n"]
    for o in orders[:10]:
        total = o.get("total_price", "0")
        currency = o.get("currency", "EUR")
        name = o.get("name", "#?")
        email = o.get("email", "anonym")
        status = o.get("financial_status", "?")
        lines.append(f"• {name} — *{total} {currency}* — {email} — {status}")
    return "\n".join(lines)


def notify_new_order(order: dict) -> None:
    total = order.get("total_price", "0")
    currency = order.get("currency", "EUR")
    name = order.get("name", "#?")
    email = order.get("email", "anonym")
    items = order.get("line_items", [])
    item_names = ", ".join(i.get("name", "?") for i in items[:3])
    msg = (
        f"🛒 *NEUE BESTELLUNG!*\n\n"
        f"Bestellung: {name}\n"
        f"💰 Betrag: *{total} {currency}*\n"
        f"📧 Kunde: {email}\n"
        f"📦 Produkte: {item_names}"
    )
    _tg_send_sync(msg)


# ── Produkte ─────────────────────────────────────────────────────────────────

def get_product_count() -> dict:
    result = _shopify_get("products/count.json")
    return {"total": result.get("count", 0)}


def get_products_summary(limit: int = 5) -> str:
    result = _shopify_get(f"products.json?limit={limit}&fields=id,title,status,variants")
    products = result.get("products", [])
    if not products:
        return "Keine Produkte gefunden."
    lines = ["🛍️ *Produkte:*\n"]
    for p in products:
        price = p.get("variants", [{}])[0].get("price", "?")
        status = "✅" if p.get("status") == "active" else "⏸"
        lines.append(f"{status} {p['title']} — €{price}")
    return "\n".join(lines)


def create_product_simple(title: str, price: str, description: str = "") -> dict:
    data = {
        "product": {
            "title": title,
            "body_html": description or title,
            "status": "active",
            "variants": [{"price": price, "inventory_management": "shopify"}]
        }
    }
    result = _shopify_post("products.json", data)
    return result.get("product", result)


# ── Analytics ────────────────────────────────────────────────────────────────

def get_revenue_today() -> dict:
    import datetime
    today = datetime.date.today().isoformat()
    result = _shopify_get(f"orders.json?created_at_min={today}T00:00:00&financial_status=paid&fields=total_price,currency")
    orders = result.get("orders", [])
    total = sum(float(o.get("total_price", 0)) for o in orders)
    return {"orders": len(orders), "revenue": round(total, 2), "date": today}


def get_shopify_status_message() -> str:
    count = get_product_count()
    revenue = get_revenue_today()
    orders = get_recent_orders(limit=3)

    configured = bool(SHOPIFY_DOMAIN() and SHOPIFY_TOKEN())
    status = "✅ Verbunden" if configured else "❌ Nicht konfiguriert"

    msg = (
        f"🛒 *Shopify Status*\n\n"
        f"Status: {status}\n"
        f"Shop: {SHOPIFY_DOMAIN() or 'nicht gesetzt'}\n\n"
        f"📦 Produkte: {count.get('total', '?')}\n"
        f"💰 Umsatz heute: €{revenue.get('revenue', 0)}\n"
        f"📋 Bestellungen heute: {revenue.get('orders', 0)}\n"
    )

    if orders:
        latest = orders[0]
        msg += f"\n*Letzte Bestellung:*\n{latest.get('name')} — €{latest.get('total_price')} — {latest.get('email', 'anonym')}"

    return msg


# ── Webhook-Handler ──────────────────────────────────────────────────────────

async def handle_shopify_order_webhook(order_data: dict) -> None:
    """Aufgerufen wenn Shopify eine neue Bestellung sendet."""
    try:
        notify_new_order(order_data)
    except Exception as e:
        log.error("Order webhook error: %s", e)


async def get_customers(limit: int = 50) -> list:
    """Get Shopify customers list."""
    import os, aiohttp
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    if not domain or not token:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/{version}/customers.json?limit={limit}",
                headers={"X-Shopify-Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status == 200:
                    return (await r.json()).get("customers", [])
    except Exception:
        pass
    return []
