#!/usr/bin/env python3
"""🛒 Shopify Agent — Überwacht Orders, Products, Revenue in Echtzeit"""
import sys, os, time, json
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARMY_DIR / "shared"))
sys.path.insert(0, str(ARMY_DIR.parent))
from bus import report, notify_telegram, get_env, load_state
from modules import shopify_client

ID = "shopify"


async def fetch_shopify_data():
    try:
        shop = await shopify_client.get_shop_info()
        products = await shopify_client.get_products(limit=20)
        orders = await shopify_client.get_orders(limit=20)
        analytics = await shopify_client.get_analytics_summary()
        return {
            "shop": shop,
            "products": products,
            "orders": orders,
            "analytics": analytics,
        }
    except Exception as e:
        return {"error": str(e)}

def run():
    print(f"[{ID}] 🛒 Shopify Agent gestartet")
    last_order_count = 0
    while True:
        try:
            import asyncio
            data = asyncio.run(fetch_shopify_data())
            if data.get("error"):
                report(ID, "warning", f"Shopify API Fehler: {data['error'][:80]}", {"error": data["error"]})
                time.sleep(120)
                continue

            orders = data.get("orders", [])
            products = data.get("products", [])
            analytics = data.get("analytics", {})
            shop = data.get("shop", {})
            total_orders = len(orders)
            revenue = analytics.get("revenue", 0)
            today_rev = revenue
            today_orders = total_orders
            
            # Neue Bestellungen erkennen
            if total_orders > last_order_count and last_order_count > 0:
                new = total_orders - last_order_count
                notify_telegram(f"🛒 <b>{new} neue Bestellung(en)!</b>\nHeute: {today_orders} Orders, €{today_rev}")
            last_order_count = max(total_orders, last_order_count)
            
            report(ID, "ok", f"Shopify: {total_orders} Orders €{float(revenue or 0):.2f} | Produkte: {len(products)}", {
                "orders": total_orders, "revenue": revenue, "today": today_orders,
                "today_revenue": today_rev, "products": len(products), "shop": shop.get("name", "")
            })
        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")
        time.sleep(120)  # alle 2 Minuten

if __name__ == "__main__":
    run()
