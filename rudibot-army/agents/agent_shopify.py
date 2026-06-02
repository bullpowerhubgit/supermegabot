#!/usr/bin/env python3
"""🛒 Shopify Agent — Überwacht Orders, Products, Revenue in Echtzeit"""
import sys, os, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

ID = "shopify"

# Dashboard-API (SuperMegaBot) als primäre Quelle
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8888")


def call_api(path: str, base: str = DASHBOARD_URL) -> dict:
    import urllib.request
    try:
        r = urllib.request.urlopen(f"{base}{path}", timeout=10)
        return json.loads(r.read())
    except Exception:
        return {}


def run():
    print(f"[{ID}] 🛒 Shopify Agent gestartet")
    last_order_count = 0

    while True:
        try:
            data = call_api("/api/shopify/status")
            orders = data.get("order_count", data.get("total", 0))
            revenue = data.get("revenue", data.get("total_revenue", "0"))
            today_rev = data.get("today_revenue", data.get("todayRevenue", "0"))
            today_orders = data.get("today_orders", data.get("todayOrders", 0))
            products = data.get("product_count", 0)

            # Neue Bestellungen erkennen
            try:
                order_int = int(orders)
            except (ValueError, TypeError):
                order_int = 0

            if order_int > last_order_count and last_order_count > 0:
                new = order_int - last_order_count
                notify_telegram(
                    f"🛒 <b>{new} neue Bestellung(en)!</b>\n"
                    f"Heute: {today_orders} Orders | €{today_rev}"
                )
            last_order_count = max(order_int, last_order_count)

            report(ID, "ok",
                   f"Orders: {orders} | €{revenue} Gesamt | €{today_rev} Heute | {products} Produkte",
                   {
                       "orders": orders, "revenue": revenue,
                       "today_orders": today_orders, "today_revenue": today_rev,
                       "products": products,
                   })

        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")

        time.sleep(120)


if __name__ == "__main__":
    run()
