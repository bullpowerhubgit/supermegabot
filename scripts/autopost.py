#!/usr/bin/env python3
"""
Autopost: Shopify Produkt → Facebook + Telegram
Läuft via GitHub Actions 4x täglich — kein Server nötig, €0 Kosten
"""
import os, random, requests, sys, json
from datetime import datetime

SHOPIFY_DOMAIN = os.environ["SHOPIFY_SHOP_DOMAIN"]
SHOPIFY_TOKEN  = os.environ["SHOPIFY_ADMIN_API_TOKEN"]
FB_PAGE_ID     = os.environ.get("FACEBOOK_PAGE_ID", "1016738738178786")
FB_TOKEN       = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
TG_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")
SHOP_URL       = "https://ineedit.com.co"

CAPTIONS = [
    "🔥 Trending jetzt: {title}\n💶 Nur €{price}\n👉 {link}\n\n#fashion #style #tshirt #streetwear",
    "✨ Neu im Shop: {title}\n💰 €{price} — Limitiert!\n🛒 {link}\n\n#onlineshopping #mode #outfit",
    "🛍️ {title}\n💶 Jetzt für €{price}\n👆 Link im Profil oder: {link}\n\n#shopping #tshirts #shop",
    "💥 Deal des Tages: {title}\n💵 €{price}\n🔗 {link}\n\n#sale #deals #fashion #clothing",
    "🎯 {title}\n⚡ Nur €{price} | Schnell zugreifen!\n{link}\n\n#streetstyle #tshirt #fashion",
]

def get_random_product():
    """Holt zufälliges Shopify-Produkt via cursor-based pagination."""
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/products.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

    # Zufälligen Offset über since_id Ansatz
    offsets = [1, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    since_id = random.choice(offsets)

    r = requests.get(url, headers=headers,
                     params={"limit": 20, "since_id": since_id, "status": "active"},
                     timeout=15)
    products = r.json().get("products", [])

    if not products:
        # Fallback: erste Seite
        r = requests.get(url, headers=headers,
                         params={"limit": 20, "status": "active"}, timeout=15)
        products = r.json().get("products", [])

    if not products:
        raise RuntimeError("Keine Shopify-Produkte gefunden")

    p = random.choice(products)
    img   = p.get("images", [{}])[0].get("src", "")
    price = p.get("variants", [{}])[0].get("price", "29.99")
    return {
        "title": p.get("title", "Top Produkt"),
        "price": price,
        "img":   img,
        "link":  f"{SHOP_URL}/products/{p.get('handle', '')}",
    }

def post_facebook(prod: dict) -> bool:
    if not FB_TOKEN:
        print("⚠️  FACEBOOK_PAGE_TOKEN nicht gesetzt — übersprungen")
        return False

    caption = random.choice(CAPTIONS).format(**prod)

    if prod["img"]:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos",
            data={"url": prod["img"], "caption": caption, "access_token": FB_TOKEN},
            timeout=20,
        )
    else:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
            data={"message": caption, "link": prod["link"], "access_token": FB_TOKEN},
            timeout=20,
        )

    result = r.json()
    if "error" in result:
        print(f"❌ Facebook: {result['error'].get('message', result)}", file=sys.stderr)
        return False

    post_id = result.get("id") or result.get("post_id", "?")
    print(f"✅ Facebook: post_id={post_id}")
    return True

def post_telegram(prod: dict) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️  Telegram-Credentials fehlen — übersprungen")
        return False

    text = (
        f"🛍 *{prod['title']}*\n"
        f"💶 €{prod['price']}\n"
        f"[➡️ Jetzt kaufen]({prod['link']})"
    )

    if prod["img"]:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT_ID, "photo": prod["img"],
                  "caption": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    else:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )

    result = r.json()
    ok = result.get("ok", False)
    print(f"{'✅' if ok else '❌'} Telegram: {result.get('description', 'ok')}")
    return ok

if __name__ == "__main__":
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"🚀 Autopost gestartet — {ts}")

    try:
        prod = get_random_product()
        print(f"📦 {prod['title']} | €{prod['price']}")
    except Exception as e:
        print(f"❌ Produkt-Fehler: {e}", file=sys.stderr)
        sys.exit(1)

    fb_ok = post_facebook(prod)
    tg_ok = post_telegram(prod)

    if not fb_ok and not tg_ok:
        print("❌ Alle Kanäle fehlgeschlagen", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Fertig — FB={'✅' if fb_ok else '❌'} TG={'✅' if tg_ok else '❌'}")
