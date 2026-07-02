#!/usr/bin/env python3
"""
Autopost: Shopify Produkt → Facebook + Telegram
Läuft via GitHub Actions alle 6h — kein Server nötig
"""
import os, random, requests, json, sys

SHOPIFY_DOMAIN = os.environ["SHOPIFY_SHOP_DOMAIN"]
SHOPIFY_TOKEN  = os.environ["SHOPIFY_ADMIN_API_TOKEN"]
FB_PAGE_ID     = os.environ["FACEBOOK_PAGE_ID"]
FB_TOKEN       = os.environ["FACEBOOK_PAGE_TOKEN"]
TG_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT_ID     = os.environ["TELEGRAM_CHAT_ID"]
SHOP_URL       = "https://ineedit.com.co"

def get_random_product():
    # Zufällige Seite aus ~10k Produkten wählen
    page = random.randint(1, 100)
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/products.json"
    r = requests.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                     params={"limit": 10, "page": page, "status": "active"})
    products = r.json().get("products", [])
    if not products:
        # Fallback Seite 1
        r = requests.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                         params={"limit": 10, "status": "active"})
        products = r.json().get("products", [])
    p = random.choice(products)
    img = p.get("images", [{}])[0].get("src", "")
    price = p.get("variants", [{}])[0].get("price", "29.99")
    handle = p.get("handle", "")
    title = p.get("title", "")
    return title, price, img, f"{SHOP_URL}/products/{handle}"

def post_facebook(title, price, img_url, link):
    caption = (
        f"🛍️ {title}\n\n"
        f"💶 Nur €{price}\n"
        f"👉 Jetzt kaufen: {link}\n\n"
        f"#fashion #style #shopping #onlineshop #tshirt"
    )
    if img_url:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos",
            data={"url": img_url, "caption": caption, "access_token": FB_TOKEN}
        )
    else:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
            data={"message": caption, "link": link, "access_token": FB_TOKEN}
        )
    result = r.json()
    if "error" in result:
        print(f"FB Fehler: {result['error']}", file=sys.stderr)
        return False
    print(f"✅ Facebook: post_id={result.get('id') or result.get('post_id')}")
    return True

def post_telegram(title, price, img_url, link):
    text = (
        f"🛍 *{title}*\n"
        f"💶 €{price}\n"
        f"[Jetzt kaufen]({link})"
    )
    if img_url:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT_ID, "photo": img_url,
                  "caption": text, "parse_mode": "Markdown"}
        )
    else:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        )
    result = r.json()
    ok = result.get("ok", False)
    print(f"{'✅' if ok else '❌'} Telegram: {result.get('description','ok')}")
    return ok

if __name__ == "__main__":
    print("🚀 Autopost gestartet...")
    title, price, img, link = get_random_product()
    print(f"📦 Produkt: {title} | €{price}")
    post_facebook(title, price, img, link)
    post_telegram(title, price, img, link)
    print("✅ Fertig.")
