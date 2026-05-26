#!/usr/bin/env python3
"""💸 Micro-Revenue — Stündlicher Shopify-Umsatz-Check + Tages-Zusammenfassung"""
import sys, os, time, json, datetime, urllib.request
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARMY_DIR / "shared"))
sys.path.insert(0, str(ARMY_DIR.parent))
from bus import report, notify_telegram, get_env
from modules import shopify_client

ID = "micro_revenue"
INTERVAL = 3600  # Stündlich

def fetch_revenue():
    """Holt Umsatz-Daten direkt aus der Shopify Admin API."""
    try:
        import asyncio
        analytics = asyncio.run(shopify_client.get_analytics_summary())
        orders = asyncio.run(shopify_client.get_orders(limit=50))
        if not analytics:
            return None
        return {
            "today_revenue": float(analytics.get("revenue", 0)),
            "order_count": len(orders),
            "shop": analytics.get("shop", ""),
        }
    except Exception:
        pass
    try:
        import asyncio
        analytics = asyncio.run(shopify_client.get_analytics_summary())
        return {"today_revenue": float(analytics.get("revenue", 0)), "order_count": int(analytics.get("orders_paid", 0))}
    except Exception:
        return None

def run():
    print(f"[{ID}] 💸 Micro-Revenue gestartet")
    last_day = None
    daily_revenue = 0.0

    while True:
        data = fetch_revenue()
        today = datetime.date.today()

        if data:
            rev = data.get("today_revenue", data.get("revenue", 0))
            orders = data.get("order_count", data.get("orders", 0))
            daily_revenue = rev

            # Tages-Zusammenfassung um Mitternacht
            if today != last_day and datetime.datetime.now().hour >= 20:
                notify_telegram(
                    f"💸 <b>Tages-Umsatz:</b> €{daily_revenue:.2f}\n"
                    f"📦 Bestellungen: {orders}\n"
                    f"📅 {today}"
                )
                last_day = today

            report(ID, "ok", f"Umsatz heute: €{rev:.2f} ({orders} Orders)",
                   {"revenue": rev, "orders": orders, "date": str(today)})
        else:
            report(ID, "warning", "Shopify API nicht erreichbar", {})

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
