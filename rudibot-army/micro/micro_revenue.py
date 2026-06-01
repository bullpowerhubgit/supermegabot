#!/usr/bin/env python3
"""💸 Micro-Revenue — Stündlicher Shopify-Umsatz-Check + Tages-Zusammenfassung

Usage:
  python3 micro_revenue.py          # loop (jede Stunde)
  python3 micro_revenue.py --once   # einmaliger Test, dann Exit
"""
import sys, os
import pathlib, time, json, datetime, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'shared'))
from bus import report, notify_telegram, get_env

ID = "micro_revenue"
INTERVAL = 3600  # Stündlich

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8888")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")


def _check_env() -> list[str]:
    """Gibt Liste der fehlenden Pflicht-Variablen zurück."""
    missing = []
    for k in ("SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP_DOMAIN"):
        if not get_env(k):
            missing.append(k)
    return missing


def fetch_revenue() -> dict | None:
    """Holt Umsatz-Daten: Dashboard → Shopify API direkt."""
    # Primär: SuperMegaBot Dashboard
    try:
        r = urllib.request.urlopen(f"{DASHBOARD_URL}/api/shopify/status", timeout=5)
        data = json.loads(r.read())
        if data and data.get("ok"):
            return {
                "source": "dashboard",
                "today_revenue": float(data.get("today_revenue", data.get("todayRevenue", 0)) or 0),
                "order_count":   int(data.get("today_orders", data.get("todayOrders", 0)) or 0),
            }
    except Exception:
        pass

    # Fallback: Shopify Admin API direkt
    token = get_env("SHOPIFY_ACCESS_TOKEN")
    shop  = get_env("SHOPIFY_SHOP_DOMAIN")
    if not token or not shop:
        return None
    try:
        today = datetime.date.today().isoformat()
        url = (f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
               f"?status=paid&created_at_min={today}T00:00:00Z&fields=total_price,currency")
        req = urllib.request.Request(url)
        req.add_header("X-Shopify-Access-Token", token)
        r = urllib.request.urlopen(req, timeout=15)
        data = json.loads(r.read())
        orders = data.get("orders", [])
        total = sum(float(o.get("total_price", 0)) for o in orders)
        currency = orders[0].get("currency", "EUR") if orders else "EUR"
        return {
            "source": "shopify_direct",
            "today_revenue": round(total, 2),
            "order_count": len(orders),
            "currency": currency,
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"[{ID}] ❌ Shopify HTTP {e.code}: {body}", flush=True)
        return None
    except Exception as e:
        print(f"[{ID}] ❌ Shopify Fehler: {e}", flush=True)
        return None


def run_once() -> bool:
    """Einmaliger Test — gibt True bei Erfolg zurück."""
    print(f"[{ID}] Shopify-Verbindungstest...", flush=True)

    missing = _check_env()
    if missing:
        print(f"[{ID}] ❌ Fehlende Env-Variablen: {', '.join(missing)}", flush=True)
        print(f"[{ID}]    → .env prüfen oder: export {missing[0]}=dein_wert", flush=True)
        return False

    shop = get_env("SHOPIFY_SHOP_DOMAIN")
    print(f"[{ID}] Shop: {shop}", flush=True)
    print(f"[{ID}] API-Version: {SHOPIFY_API_VERSION}", flush=True)

    data = fetch_revenue()
    today = datetime.date.today()

    if data:
        rev    = data["today_revenue"]
        orders = data["order_count"]
        cur    = data.get("currency", "EUR")
        source = data.get("source", "?")
        print(f"[{ID}] ✅ Shopify API erreichbar (via {source})", flush=True)
        print(f"[{ID}] 📊 Heute {today}:", flush=True)
        print(f"[{ID}]    Umsatz:      {cur} {rev:.2f}", flush=True)
        print(f"[{ID}]    Bestellungen: {orders}", flush=True)
        report(ID, "ok", f"Umsatz heute: {cur} {rev:.2f} ({orders} Orders)",
               {"revenue": rev, "orders": orders, "currency": cur, "date": str(today)})
        return True
    else:
        print(f"[{ID}] ❌ Shopify API nicht erreichbar", flush=True)
        print(f"[{ID}]    → Token gültig? SHOPIFY_SHOP_DOMAIN korrekt?", flush=True)
        report(ID, "warning", "Shopify API nicht erreichbar", {})
        return False


def run():
    """Dauerhafter Loop — stündlich."""
    print(f"[{ID}] 💸 Micro-Revenue gestartet (Interval: {INTERVAL}s)", flush=True)
    last_day = None
    daily_revenue = 0.0

    while True:
        data = fetch_revenue()
        today = datetime.date.today()

        if data:
            rev    = data["today_revenue"]
            orders = data["order_count"]
            cur    = data.get("currency", "EUR")
            daily_revenue = rev

            print(f"[{ID}] ✅ {today} — {cur} {rev:.2f} ({orders} Bestellungen)", flush=True)

            if today != last_day and datetime.datetime.now().hour >= 20:
                notify_telegram(
                    f"💸 <b>Tages-Umsatz:</b> {cur} {daily_revenue:.2f}\n"
                    f"📦 Bestellungen: {orders}\n"
                    f"📅 {today}"
                )
                last_day = today

            report(ID, "ok", f"Umsatz heute: {cur} {rev:.2f} ({orders} Orders)",
                   {"revenue": rev, "orders": orders, "currency": cur, "date": str(today)})
        else:
            print(f"[{ID}] ⚠️  Shopify API nicht erreichbar — retry in {INTERVAL}s", flush=True)
            report(ID, "warning", "Shopify API nicht erreichbar", {})

        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv or "--test" in sys.argv:
        ok = run_once()
        sys.exit(0 if ok else 1)
    else:
        run()
