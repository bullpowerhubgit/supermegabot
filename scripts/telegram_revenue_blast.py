#!/usr/bin/env python3
"""Telegram Revenue Blast — Stripe Checkout erstellen + Promo senden."""
import json, os, urllib.request, urllib.parse
from pathlib import Path

env_file = Path('/Users/rudolfsarkany/supermegabot/.env')
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or ""
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")

def stripe_req(path, data):
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/{path}",
        data=encoded,
        headers={
            "Authorization": f"Bearer {STRIPE_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, json.loads(e.read().decode())

def tg(method, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── 1. Stripe Checkout Session ───────────────────────────────────────────────
print("=== STRIPE CHECKOUT ===")
checkout_url = None

if not STRIPE_KEY:
    print("ERROR: STRIPE_SECRET_KEY not set")
elif not STRIPE_PRICE_PRO:
    print("ERROR: STRIPE_PRICE_PRO not set — using payment_link fallback")
else:
    result, err = stripe_req("checkout/sessions", {
        "mode": "subscription",
        "line_items[0][price]": STRIPE_PRICE_PRO,
        "line_items[0][quantity]": "1",
        "success_url": "https://supermegabot.up.railway.app/success?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://supermegabot.up.railway.app/pricing",
        "allow_promotion_codes": "true",
        "metadata[source]": "telegram_blast_20260617",
        "metadata[discount]": "promo_79",
    })
    if result:
        checkout_url = result.get("url")
        print(f"Checkout Session: {result.get('id')}")
        print(f"URL: {checkout_url}")
    else:
        print(f"Stripe error: {err}")
        # Try payment_links instead
        links_result, links_err = stripe_req("payment_links", {})
        if links_result and links_result.get("data"):
            checkout_url = links_result["data"][0].get("url")
            print(f"Fallback payment link: {checkout_url}")

if not checkout_url:
    checkout_url = "https://buy.stripe.com/supermegabot-pro"
    print(f"Using static fallback URL: {checkout_url}")

# ── 2. Telegram Promo senden ─────────────────────────────────────────────────
print("\n=== TELEGRAM PROMO ===")
if not TOKEN or not CHAT_ID:
    print(f"ERROR: TOKEN={bool(TOKEN)}, CHAT_ID={bool(CHAT_ID)}")
    exit(1)

msg = f"""🚀 <b>SuperMegaBot PRO — Heute nur €79/mo</b> <s>€99</s>

✅ Shopify Vollautomatisierung
✅ KI Content Pipeline (Claude + GPT)
✅ Digistore24 Integration
✅ Telegram Premium Commands
✅ Revenue Analytics Dashboard

⏰ <b>Angebot läuft 24h</b>

👉 <a href="{checkout_url}">Jetzt starten →</a>"""

keyboard = [[{"text": "🛒 PRO für €79/mo starten", "url": checkout_url}]]

res = tg("sendMessage", {
    "chat_id": CHAT_ID,
    "text": msg,
    "parse_mode": "HTML",
    "reply_markup": {"inline_keyboard": keyboard},
})

if res.get("ok"):
    print(f"✅ Promo gesendet! Message ID: {res['result']['message_id']}")
    print(f"Chat: {CHAT_ID}")
else:
    print(f"❌ Senden fehlgeschlagen: {res}")

print(f"\nCheckout URL: {checkout_url}")
