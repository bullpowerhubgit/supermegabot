#!/usr/bin/env python3
"""🛒 Shopify Agent — Überwacht Orders, Products, Revenue in Echtzeit"""
import sys, os, time, json
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, get_env, load_state

ID = "shopify"

def call_api(path):
    import urllib.request
    try:
        r = urllib.request.urlopen(f"http://localhost:3200{path}", timeout=10)
        return json.loads(r.read())
    except: return {}

def run():
    print(f"[{ID}] 🛒 Shopify Agent gestartet")
    last_order_count = 0
    while True:
        try:
            data = call_api("/api/shopify/live-orders")
            orders = data.get("total", 0)
            revenue = data.get("revenue", "0")
            today_rev = data.get("todayRevenue", "0")
            today_orders = data.get("todayOrders", 0)
            
            # Neue Bestellungen erkennen
            if orders > last_order_count and last_order_count > 0:
                new = orders - last_order_count
                notify_telegram(f"🛒 <b>{new} neue Bestellung(en)!</b>\nHeute: {today_orders} Orders, €{today_rev}")
            last_order_count = max(orders, last_order_count)
            
            # Printify check
            pdata = call_api("/api/printify/orders")
            printify_orders = pdata.get("total", 0)
            
            report(ID, "ok", f"Shopify: {orders} Orders €{revenue} | Printify: {printify_orders}", {
                "orders": orders, "revenue": revenue, "today": today_orders,
                "today_revenue": today_rev, "printify": printify_orders
            })
        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")
        time.sleep(120)  # alle 2 Minuten

if __name__ == "__main__":
    run()
