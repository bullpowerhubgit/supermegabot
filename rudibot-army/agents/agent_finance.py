#!/usr/bin/env python3
"""💰 Finance Agent — Trackt Einnahmen, Ausgaben, warnt bei Anomalien"""
import sys, os, time, json, datetime
from pathlib import Path

ARMY_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = ARMY_DIR / "shared"
sys.path.insert(0, str(SHARED_DIR))
from bus import report, notify_telegram, load_state

ID = "finance"
DATA_FILE = SHARED_DIR / "finance_cache.json"

def load_cache():
    try:
        if DATA_FILE.exists():
            return json.loads(DATA_FILE.read_text(errors="ignore"))
    except: pass
    return {"daily": {}, "alerts": [], "total_revenue": 0}

def save_cache(d):
    DATA_FILE.write_text(json.dumps(d, indent=2))

def call_api(path):
    import urllib.request
    try:
        r = urllib.request.urlopen(f"http://localhost:3200{path}", timeout=10)
        return json.loads(r.read())
    except: return {}

def run():
    print(f"[{ID}] 💰 Finance Agent gestartet")
    while True:
        try:
            today = datetime.date.today().isoformat()
            cache = load_cache()
            
            # Shopify Revenue
            shopify = call_api("/api/shopify/live-orders")
            if shopify.get("error"):
                report(ID, "warning", f"Shopify API Fehler: {str(shopify.get('error'))[:60]}", {
                    "error": shopify.get("error")
                })
                time.sleep(600)
                continue
            today_rev = float(shopify.get("todayRevenue", 0))
            total_rev = float(shopify.get("revenue", 0))
            
            # Printify Revenue  
            printify = call_api("/api/printify/orders")
            if printify.get("error"):
                report(ID, "warning", f"Printify API Fehler: {str(printify.get('error'))[:60]}", {
                    "error": printify.get("error")
                })
                time.sleep(600)
                continue
            p_orders = printify.get("total", 0)
            
            # Tagesvergleich
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            yesterday_rev = cache["daily"].get(yesterday, {}).get("shopify", 0)
            
            if today_rev > 0 and yesterday_rev > 0:
                change_pct = ((today_rev - yesterday_rev) / yesterday_rev) * 100
                if change_pct > 50:
                    notify_telegram(f"📈 <b>Umsatz +{change_pct:.0f}%!</b> Heute: €{today_rev:.2f}")
                elif change_pct < -50:
                    notify_telegram(f"📉 <b>Umsatz -{abs(change_pct):.0f}%</b> Heute nur €{today_rev:.2f}")
            
            cache["daily"][today] = {"shopify": today_rev, "printify": p_orders}
            cache["total_revenue"] = total_rev
            cache["daily"] = {k:v for k,v in cache["daily"].items() if k >= (datetime.date.today() - datetime.timedelta(days=30)).isoformat()}
            save_cache(cache)
            
            report(ID, "ok", f"Finance: €{today_rev:.2f} heute | €{total_rev:.2f} gesamt", {
                "today_revenue": today_rev, "total_revenue": total_rev,
                "printify_orders": p_orders, "yesterday_revenue": yesterday_rev
            })
        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")
        time.sleep(600)  # alle 10 Minuten

if __name__ == "__main__":
    run()
