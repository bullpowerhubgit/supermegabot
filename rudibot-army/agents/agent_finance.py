#!/usr/bin/env python3
"""💰 Finance Agent — Trackt Einnahmen, warnt bei Anomalien"""
import sys, os, time, json, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram

ID = "finance"
ARMY_DIR  = Path(__file__).parent.parent
DATA_FILE = ARMY_DIR / "shared" / "finance_cache.json"

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8888")


def load_cache() -> dict:
    try:
        if DATA_FILE.exists():
            return json.loads(DATA_FILE.read_text())
    except Exception:
        pass
    return {"daily": {}, "alerts": [], "total_revenue": 0}


def save_cache(d: dict):
    try:
        DATA_FILE.write_text(json.dumps(d, indent=2))
    except Exception:
        pass


def call_api(path: str) -> dict:
    import urllib.request
    try:
        r = urllib.request.urlopen(f"{DASHBOARD_URL}{path}", timeout=10)
        return json.loads(r.read())
    except Exception:
        return {}


def run():
    print(f"[{ID}] 💰 Finance Agent gestartet")

    while True:
        try:
            today = datetime.date.today().isoformat()
            cache = load_cache()

            shopify = call_api("/api/shopify/status")
            today_rev = float(shopify.get("today_revenue", shopify.get("todayRevenue", 0)) or 0)
            total_rev = float(shopify.get("revenue", shopify.get("total_revenue", 0)) or 0)

            # Tagesvergleich
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            yesterday_rev = cache["daily"].get(yesterday, {}).get("shopify", 0)

            if today_rev > 0 and yesterday_rev > 0:
                change_pct = ((today_rev - yesterday_rev) / yesterday_rev) * 100
                if change_pct > 50:
                    notify_telegram(f"📈 <b>Umsatz +{change_pct:.0f}%!</b> Heute: €{today_rev:.2f}")
                elif change_pct < -50:
                    notify_telegram(f"📉 <b>Umsatz -{abs(change_pct):.0f}%</b> Heute: €{today_rev:.2f}")

            cache["daily"][today] = {"shopify": today_rev}
            cache["total_revenue"] = total_rev
            # Nur 30 Tage Verlauf behalten
            cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            cache["daily"] = {k: v for k, v in cache["daily"].items() if k >= cutoff}
            save_cache(cache)

            report(ID, "ok",
                   f"€{today_rev:.2f} heute | €{total_rev:.2f} gesamt",
                   {
                       "today_revenue": today_rev,
                       "total_revenue": total_rev,
                       "yesterday_revenue": yesterday_rev,
                   })

        except Exception as e:
            report(ID, "error", f"Fehler: {str(e)[:80]}")

        time.sleep(600)


if __name__ == "__main__":
    run()
