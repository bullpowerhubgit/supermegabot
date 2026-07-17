#!/usr/bin/env python3
"""Upsell Engine — 2-Tage-Post-Purchase Upsell via SendGrid."""
from __future__ import annotations
import asyncio, json, logging, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List
import aiohttp

log = logging.getLogger("UpsellEngine")
_SENT_FILE = Path(__file__).resolve().parents[1] / "data" / "upsell_sent.json"
_SHOP_URL  = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
_MAX_PER_CYCLE = 10


def _load_sent() -> set:
    try:
        if _SENT_FILE.exists():
            return set(json.loads(_SENT_FILE.read_text()).get("order_ids", []))
    except Exception:
        pass
    return set()


def _save_sent(sent: set) -> None:
    _SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SENT_FILE.write_text(json.dumps({"order_ids": list(sent)}, indent=2))


async def get_recent_orders(days: int = 2) -> List[Dict]:
    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ACCESS_TOKEN", "") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    ver    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not domain or not token:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                f"https://{domain}/admin/api/{ver}/orders.json",
                headers={"X-Shopify-Access-Token": token},
                params={"status": "any", "created_at_min": since, "limit": 50,
                        "fields": "id,email,customer,total_price,line_items,created_at"},
            ) as r:
                if r.status == 200:
                    return (await r.json()).get("orders", [])
    except Exception as e:
        log.warning("Shopify orders: %s", e)
    return []


def build_upsell_offer(order: Dict) -> Dict:
    try:
        price = float(order.get("total_price", "0") or 0)
    except ValueError:
        price = 0.0
    if price >= 50:
        return {
            "product_title": "Solar Powerstation Bundle 500W",
            "upsell_suggestion": "Ergaenze dein Setup mit unserer Bestseller-Powerstation",
            "upsell_link": f"{_SHOP_URL}/collections/solar",
        }
    return {
        "product_title": "SmartHome Starter Kit",
        "upsell_suggestion": "Dein perfekter Einstieg ins smarte Zuhause",
        "upsell_link": f"{_SHOP_URL}/collections/smart-home",
    }


async def send_upsell_email(email: str, name: str, order: Dict, upsell: Dict) -> Dict:
    from modules.sendgrid_blast import send_single
    first   = name.split()[0] if name else "du"
    subject = "Ergaenze dein Smart-Home-Set perfekt 🏠"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0d0d0d;color:#e0e0e0;padding:24px;border-radius:10px">
  <h2 style="color:#ff6b35">Hey {first}, danke fuer deine Bestellung! 🎉</h2>
  <p>Wir haben das perfekte Produkt, das dein Setup ergaenzt:</p>
  <div style="background:#1a1a1a;padding:16px;border-radius:8px;margin:16px 0">
    <h3 style="color:#ff6b35;margin:0 0 8px 0">{upsell['product_title']}</h3>
    <p style="margin:0;color:#ccc">{upsell['upsell_suggestion']}</p>
  </div>
  <a href="{upsell['upsell_link']}" style="display:inline-block;background:#ff6b35;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;margin:16px 0">Jetzt entdecken &rarr;</a>
  <hr style="border-color:#2a2a2a;margin:24px 0">
  <p style="font-size:11px;color:#555;text-align:center">
    <a href="{_SHOP_URL}" style="color:#555">ineedit.com.co</a> |
    <a href="{_SHOP_URL}/pages/unsubscribe" style="color:#555">Abmelden</a>
  </p>
</div>"""
    return await send_single(email, first, subject, html)


async def run_upsell_cycle() -> Dict:
    sent_ids = _load_sent()
    orders   = await get_recent_orders(days=2)
    if not orders:
        return {"ok": True, "sent": 0, "skipped": 0, "reason": "no recent orders"}

    sent = 0
    skipped = 0
    for order in orders[:_MAX_PER_CYCLE]:
        order_id = str(order.get("id", ""))
        email    = (order.get("email") or "").strip()
        customer = order.get("customer") or {}
        name     = f"{customer.get('first_name','')} {customer.get('last_name','')}".strip()

        if not email or order_id in sent_ids:
            skipped += 1
            continue

        upsell = build_upsell_offer(order)
        result = await send_upsell_email(email, name, order, upsell)
        if result.get("ok"):
            sent_ids.add(order_id)
            sent += 1
        else:
            skipped += 1
        await asyncio.sleep(0.1)

    _save_sent(sent_ids)
    return {"ok": True, "sent": sent, "skipped": skipped, "checked": len(orders)}
