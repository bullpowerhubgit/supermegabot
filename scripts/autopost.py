#!/usr/bin/env python3
"""
Autopost: Shopify Produkt → Facebook + Telegram + Reddit + YouTube Community
Läuft via Supabase pg_cron 4x täglich — kein Server nötig, €0 Kosten
"""
import os, random, requests, sys, json, base64
from datetime import datetime, timezone

SHOPIFY_DOMAIN  = os.environ.get("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
FB_PAGE_ID      = os.environ.get("FACEBOOK_PAGE_ID", "1016738738178786")
FB_TOKEN        = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
TG_TOKEN        = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")
REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "hqgJAQe6Qiu5s5r1Vqc0Og")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "xsH99P7iCQAPeknbAXe5F9Nd9fV7aA")
REDDIT_REFRESH_TOKEN = os.environ.get("REDDIT_REFRESH_TOKEN", "")
REDDIT_SUBREDDITS    = ["Entrepreneur", "ecommerce", "dropshipping", "passive_income"]
YT_CLIENT_ID      = os.environ.get("GOOGLE_CLIENT_ID_AIITEC", os.environ.get("YOUTUBE_CLIENT_ID", ""))
YT_CLIENT_SECRET  = os.environ.get("GOOGLE_CLIENT_SECRET_AIITEC", os.environ.get("YOUTUBE_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN  = os.environ.get("YOUTUBE_REFRESH_TOKEN", os.environ.get("GOOGLE_REFRESH_TOKEN_AIITEC", ""))
YT_CHANNEL_ID     = os.environ.get("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")
SHOP_URL       = "https://ineedit.com.co"

CAPTIONS = [
    "🔥 Trending jetzt: {title}\n💶 Nur €{price}\n👉 {link}\n\n#smarthome #gadgets #techdeals #shopping",
    "✨ Neu im Shop: {title}\n💰 €{price} — Limitiert!\n🛒 {link}\n\n#onlineshopping #gadgets #deals",
    "🛍️ {title}\n💶 Jetzt für €{price}\n👆 Link im Profil oder: {link}\n\n#smarthome #techgadgets #sale",
    "💥 Deal des Tages: {title}\n💵 €{price}\n🔗 {link}\n\n#deals #gadgets #smarthome #lifestyle",
    "🎯 {title}\n⚡ Nur €{price} | Schnell zugreifen!\n{link}\n\n#techdeals #gadgets #smarthome",
]

def get_random_product():
    """Holt zufälliges Shopify-Produkt via öffentlichem Storefront-Endpoint (kein Admin-Token nötig)."""
    # Zufällige Seite für Abwechslung
    page = random.randint(1, 5)
    url = f"https://{SHOPIFY_DOMAIN}/products.json"

    r = requests.get(url, params={"limit": 50, "page": page}, timeout=15)
    products = r.json().get("products", [])

    if not products:
        # Fallback: erste Seite
        r = requests.get(url, params={"limit": 50, "page": 1}, timeout=15)
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

def _reddit_get_token() -> str:
    """Get Reddit access token from refresh token."""
    if not REDDIT_REFRESH_TOKEN:
        return ""
    creds = base64.b64encode(f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        headers={"Authorization": f"Basic {creds}",
                 "User-Agent": "SuperMegaBot:v2.0 (by /u/bullpowersrtkennels)"},
        data={"grant_type": "refresh_token", "refresh_token": REDDIT_REFRESH_TOKEN},
        timeout=15,
    )
    return r.json().get("access_token", "")


def post_reddit(prod: dict) -> bool:
    if not REDDIT_REFRESH_TOKEN:
        print("⚠️  REDDIT_REFRESH_TOKEN fehlt — übersprungen (einmalig: python3 scripts/oauth_connect.py reddit)")
        return False
    token = _reddit_get_token()
    if not token:
        print("❌ Reddit: Token-Refresh fehlgeschlagen")
        return False
    sub = random.choice(REDDIT_SUBREDDITS)
    title = f"🔥 {prod['title']} — nur €{prod['price']} | Smart Home Deals"
    body  = (f"Entdecke dieses Gadget: **{prod['title']}**\n\n"
             f"💶 Preis: €{prod['price']}\n"
             f"🔗 Jetzt ansehen: {prod['link']}\n\n"
             f"Automatisierter Post von SuperMegaBot")
    r = requests.post(
        "https://oauth.reddit.com/api/submit",
        headers={"Authorization": f"bearer {token}",
                 "User-Agent": "SuperMegaBot:v2.0 (by /u/bullpowersrtkennels)"},
        data={"sr": sub, "kind": "self", "title": title, "text": body, "resubmit": True},
        timeout=20,
    )
    result = r.json()
    if r.status_code == 200 and not result.get("jquery"):
        err = next((x for row in result.get("jquery", [[]])[10:12] for x in (row[3:4] or []) if "error" in str(x).lower()), None)
        if err:
            print(f"❌ Reddit r/{sub}: {err}", file=sys.stderr)
            return False
    url = result.get("json", {}).get("data", {}).get("url", "")
    print(f"✅ Reddit r/{sub}: {url or 'gepostet'}")
    return True


def _yt_get_token() -> str:
    """Refresh YouTube access token."""
    if not YT_REFRESH_TOKEN or not YT_CLIENT_ID or not YT_CLIENT_SECRET:
        return ""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=15)
    return r.json().get("access_token", "")


def post_youtube_community(prod: dict) -> bool:
    """Post to YouTube Community tab (requires channel 500+ subs — we have 4160)."""
    if not YT_REFRESH_TOKEN:
        print("⚠️  YOUTUBE_REFRESH_TOKEN fehlt — übersprungen (einmalig: python3 scripts/oauth_connect.py youtube)")
        return False
    token = _yt_get_token()
    if not token:
        print("❌ YouTube: Token-Refresh fehlgeschlagen")
        return False
    text = (f"🔥 {prod['title']}\n"
            f"💶 Nur €{prod['price']}\n"
            f"👉 {prod['link']}\n\n"
            f"#smarthome #gadgets #onlineshopping #deals")
    body: dict = {
        "snippet": {
            "type": "text",
            "text": text,
        }
    }
    r = requests.post(
        "https://www.googleapis.com/youtube/v3/communityPosts?part=snippet",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=20,
    )
    result = r.json()
    if "id" in result:
        print(f"✅ YouTube Community: post_id={result['id']}")
        return True
    err = result.get("error", {}).get("message", str(result))
    print(f"❌ YouTube Community: {err}", file=sys.stderr)
    return False


if __name__ == "__main__":
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"🚀 Autopost gestartet — {ts}")

    try:
        prod = get_random_product()
        print(f"📦 {prod['title']} | €{prod['price']}")
    except Exception as e:
        print(f"❌ Produkt-Fehler: {e}", file=sys.stderr)
        sys.exit(1)

    fb_ok = post_facebook(prod)
    tg_ok = post_telegram(prod)
    rd_ok = post_reddit(prod)
    yt_ok = post_youtube_community(prod)

    results = {"FB": fb_ok, "TG": tg_ok, "Reddit": rd_ok, "YT": yt_ok}
    summary = " | ".join(f"{k}={'✅' if v else '❌'}" for k, v in results.items())
    print(f"✅ Fertig — {summary}")

    if not fb_ok and not tg_ok:
        print("❌ Haupt-Kanäle fehlgeschlagen", file=sys.stderr)
        sys.exit(1)
