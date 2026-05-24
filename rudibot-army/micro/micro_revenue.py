#!/usr/bin/env python3
"""💸 Micro-Revenue — Stündlicher Shopify-Umsatz-Check + Tages-Zusammenfassung"""
import sys, os, time, json, datetime, urllib.request
sys.path.insert(0, os.path.expanduser("~/rudibot-army/shared"))
from bus import report, notify_telegram, get_env

ID = "micro_revenue"
INTERVAL = 3600  # Stündlich

def fetch_revenue():
    """Holt Umsatz-Daten vom lokalen Bot-Server oder Shopify API."""
    try:
        r = urllib.request.urlopen("http://localhost:3200/api/shopify/revenue", timeout=10)
        return json.loads(r.read())
    except:
        pass
    # Fallback: Shopify API direkt
    token = get_env("SHOPIFY_ACCESS_TOKEN")
    shop  = get_env("SHOPIFY_SHOP_DOMAIN")
    if not token or not shop:
        return None
    try:
        today = datetime.date.today().isoformat()
        url = f"https://{shop}/admin/api/2024-01/orders.json?status=paid&created_at_min={today}T00:00:00Z&fields=total_price"
        req = urllib.request.Request(url)
        req.add_header("X-Shopify-Access-Token", token)
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read())
        orders = data.get("orders", [])
        total = sum(float(o.get("total_price", 0)) for o in orders)
        return {"today_revenue": round(total, 2), "order_count": len(orders)}
    except:
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
