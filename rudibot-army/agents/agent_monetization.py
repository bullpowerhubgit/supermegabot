#!/usr/bin/env python3
"""💰 Monetization Agent — Trackt Umsatz, prüft Ziele, gibt Empfehlungen"""
import sys, os, time, json, subprocess, re, urllib.request
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from bus import report, notify_telegram
from learner_mixin import AgentLearner

ID = "monetization"

# Ziele
GOALS = {
    "daily": 500.0,
    "weekly": 3500.0,
    "monthly": 15000.0,
}

# Dashboard-Datei
DASHBOARD_DATA = Path(__file__).parent.parent / "dashboard_data.json"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ID}] {msg}")
    return f"[{ts}] {msg}"

def get_stripe_revenue():
    """Holt Stripe-Umsatz der letzten 24h"""
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key or not stripe_key.startswith("sk_"):
        return 0.0, "no_key"
    try:
        since = int(time.time() - 86400)
        req = urllib.request.Request(
            f"https://api.stripe.com/v1/charges?limit=100&created[gte]={since}",
            headers={"Authorization": f"Bearer {stripe_key}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            total = sum(ch.get("amount", 0) for ch in data.get("data", [])) / 100
            return total, "ok"
    except Exception as e:
        return 0.0, f"error: {e}"

def get_shopify_revenue():
    """Holt Shopify-Bestellungen der letzten 24h"""
    shopify_key = os.environ.get("SHOPIFY_API_KEY", "")
    shopify_domain = os.environ.get("SHOPIFY_SHOP_DOMAIN", "")
    if not shopify_key or not shopify_domain:
        return 0.0, "no_config"
    try:
        req = urllib.request.Request(
            f"https://{shopify_domain}/admin/api/2024-01/orders.json?status=any&limit=50&created_at_min={datetime.now() - timedelta(days=1):%Y-%m-%dT%H:%M:%S}",
            headers={"X-Shopify-Access-Token": shopify_key}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            total = sum(float(o.get("total_price", 0)) for o in data.get("orders", []))
            return total, "ok"
    except Exception as e:
        return 0.0, f"error: {e}"

def load_history():
    """Lädt Umsatz-History aus JSON"""
    if DASHBOARD_DATA.exists():
        try:
            return json.loads(DASHBOARD_DATA.read_text())
        except Exception:
            pass
    return {"daily": [], "weekly": [], "alerts_sent": []}

def save_history(data):
    """Speichert Umsatz-History"""
    DASHBOARD_DATA.write_text(json.dumps(data, indent=2))

def check_goals(daily_rev, history):
    """Prüft ob Ziele erreicht, sendet Alerts bei Nichterreichung"""
    alerts = []
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Daily
    if daily_rev < GOALS["daily"] * 0.5:
        alert_key = f"daily_low_{today_str}"
        if alert_key not in history.get("alerts_sent", []):
            alerts.append(f"🔴 Tagesumsatz nur €{daily_rev:.2f} (Ziel: €{GOALS['daily']})")
            history.setdefault("alerts_sent", []).append(alert_key)

    # Weekly
    week_rev = sum(d.get("amount", 0) for d in history.get("daily", [])[-7:]) + daily_rev
    if week_rev < GOALS["weekly"] * 0.3 and now.weekday() == 6:  # Sonntag
        alert_key = f"weekly_low_{now.strftime('%Y-W%W')}"
        if alert_key not in history.get("alerts_sent", []):
            alerts.append(f"🟠 Wochenumsatz nur €{week_rev:.2f} (Ziel: €{GOALS['weekly']})")
            history.setdefault("alerts_sent", []).append(alert_key)

    for alert in alerts:
        notify_telegram(f"💰 <b>Monetization Alert</b>\n{alert}\n\n💡 Tipp: Prüfe Conversion-Rate oder starte eine Kampagne.")

    return alerts

def get_recommendations(daily_rev, active_platforms):
    """Gibt monetarisierungs-basierte Empfehlungen"""
    recs = []
    if daily_rev < 50:
        recs.append("🚀 Starte eine Email-Kampagne über SendGrid/Mailchimp")
    if daily_rev < 100 and "shopify" in active_platforms:
        recs.append("🛒 Prüfe Shopify-Cart-Abbruch — retargeting nötig")
    if "stripe" not in active_platforms:
        recs.append("💳 Stripe nicht konfiguriert — Zahlungen nicht trackbar")
    if len([e for e in [
        "dragonadnp@gmail.com", "nikolestimi@gmail.com", "looopwave@gmail.com",
        "aitecbuuss@gmail.com", "rudolf.sarkany@aitec.de", "rudolf.sarkany.aiitec@gmail.com"
    ] if True]) > 3:
        recs.append("👥 Nutze ungenutzte Konten für mehr Shopify/Shops")
    return recs

def update_dashboard_data(history, daily_rev, sources):
    """Schreibt Daten für das HTML-Dashboard"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "daily_revenue": round(daily_rev, 2),
        "weekly_revenue": round(sum(d.get("amount", 0) for d in history.get("daily", [])[-7:]) + daily_rev, 2),
        "monthly_revenue": round(sum(d.get("amount", 0) for d in history.get("daily", [])[-30:]) + daily_rev, 2),
        "sources": sources,
        "goals": GOALS,
        "recommendations": get_recommendations(daily_rev, [s["source"] for s in sources]),
    }
    DASHBOARD_DATA.write_text(json.dumps(data, indent=2))

def run():
    print(f"[{ID}] 💰 Monetization Agent gestartet")
    print(f"[{ID}] Ziele: Daily €{GOALS['daily']} | Weekly €{GOALS['weekly']} | Monthly €{GOALS['monthly']}")
    learner = AgentLearner(ID)

    while True:
        try:
            # Sammle Umsatz aus allen Quellen
            stripe_rev, stripe_status = get_stripe_revenue()
            shopify_rev, shopify_status = get_shopify_revenue()

            daily_rev = stripe_rev + shopify_rev
            sources = []
            if stripe_rev > 0:
                sources.append({"source": "stripe", "amount": stripe_rev, "status": stripe_status})
            if shopify_rev > 0:
                sources.append({"source": "shopify", "amount": shopify_rev, "status": shopify_status})

            # History laden & updaten
            history = load_history()
            history.setdefault("daily", []).append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "amount": daily_rev,
                "sources": sources,
            })
            # Nur letzte 90 Tage behalten
            history["daily"] = history["daily"][-90:]

            # Ziele prüfen
            alerts = check_goals(daily_rev, history)
            save_history(history)

            # Dashboard updaten
            update_dashboard_data(history, daily_rev, sources)

            # Report
            status = "ok" if daily_rev > 0 else "warning"
            msg = f"Daily: €{daily_rev:.2f} | Sources: {len(sources)}"
            report(ID, status, msg, {
                "daily_revenue": daily_rev,
                "stripe_status": stripe_status,
                "shopify_status": shopify_status,
                "alerts": len(alerts),
            })
            learner.log_cycle(status, msg, {"revenue": daily_rev})

            # Empfehlungen
            recs = get_recommendations(daily_rev, [s["source"] for s in sources])
            if recs:
                print(f"[{ID}] 💡 Empfehlungen: {recs[0]}")

        except Exception as e:
            log(f"ERROR: {e}")
            report(ID, "error", str(e)[:80])

        time.sleep(600)  # Alle 10 Min

if __name__ == "__main__":
    run()
