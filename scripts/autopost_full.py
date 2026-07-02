#!/usr/bin/env python3
"""
SuperMegaBot — Multi-Platform Autopost
Plattformen: Facebook · Instagram · LinkedIn · Telegram · Reddit · Discord · Gumroad · Pinterest · eBay
Läuft 4x täglich via automation_scheduler.py
"""
import os, re, random, requests, sys, json, base64, logging, time
from datetime import datetime, timezone
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("autopost")

# ── Shopify ──────────────────────────────────────────────────────────────────
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_URL       = "https://ineedit.com.co"

# ── Facebook / Instagram ─────────────────────────────────────────────────────
FB_PAGE_ID_AIITEC  = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
FB_PAGE_ID_INEEDIT = os.getenv("FACEBOOK_PAGE_ID_INEEDIT", "1058648427339278")
FB_TOKEN_AIITEC    = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", os.getenv("FACEBOOK_PAGE_TOKEN", ""))
FB_TOKEN_INEEDIT   = os.getenv("FACEBOOK_PAGE_TOKEN_I_NEED_IT", "")
IG_BUSINESS_ID     = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "17841478315197796")

# ── Telegram ─────────────────────────────────────────────────────────────────
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── LinkedIn ──────────────────────────────────────────────────────────────────
LI_TOKEN      = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LI_REFRESH    = os.getenv("LINKEDIN_REFRESH_TOKEN", "")
LI_CLIENT_ID  = os.getenv("LINKEDIN_CLIENT_ID", "")
LI_CLIENT_SEC = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LI_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")

# ── Reddit ────────────────────────────────────────────────────────────────────
REDDIT_CLIENT_ID  = os.getenv("REDDIT_CLIENT_ID", "hqgJAQe6Qiu5s5r1Vqc0Og")
REDDIT_CLIENT_SEC = os.getenv("REDDIT_CLIENT_SECRET", "xsH99P7iCQAPeknbAXe5F9Nd9fV7aA")
REDDIT_USER       = os.getenv("REDDIT_USERNAME", "bullpowersrtkennels")
REDDIT_PASS       = os.getenv("REDDIT_PASSWORD", "Upper-Competition505")
REDDIT_REFRESH    = os.getenv("REDDIT_REFRESH_TOKEN", "")
REDDIT_SUBS       = ["Entrepreneur", "ecommerce", "dropshipping", "SmartHomeDeals", "gadgets"]

# ── Discord ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN      = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# ── Gumroad ───────────────────────────────────────────────────────────────────
GUMROAD_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", os.getenv("GUMROAD_TOKEN", ""))

# ── YouTube ───────────────────────────────────────────────────────────────────
YT_CLIENT_ID  = os.getenv("GOOGLE_CLIENT_ID_AIITEC", "")
YT_CLIENT_SEC = os.getenv("GOOGLE_CLIENT_SECRET_AIITEC", "")
YT_REFRESH    = os.getenv("YOUTUBE_REFRESH_TOKEN", os.getenv("GOOGLE_REFRESH_TOKEN_AIITEC", ""))
YT_CHANNEL    = os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")

# ── Pinterest ─────────────────────────────────────────────────────────────────
PINTEREST_TOKEN    = os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")

# ── eBay ──────────────────────────────────────────────────────────────────────
EBAY_CLIENT_ID  = os.getenv("EBAY_CLIENT_ID", "IRV7wFsqtKC76676391G2237LhVpgNCRZ1")
EBAY_CLIENT_SEC = os.getenv("EBAY_CLIENT_SECRET", "cyc7CRQrFzz~XhcUCRsrHEUJx8agTnp")
EBAY_USER_TOKEN = os.getenv("EBAY_USER_TOKEN", "")

# ── Amazon Affiliate ──────────────────────────────────────────────────────────
AMAZON_TAG = os.getenv("AMAZON_ASSOCIATES_TAG", "bullpowerhub-21")

# ── Captions ──────────────────────────────────────────────────────────────────
CAPTIONS_DE = [
    "🔥 Trending: {title}\n💶 Nur €{price}\n👉 {link}\n\n#smarthome #gadgets #techdeals #deals",
    "✨ Neu im Shop: {title}\n💰 €{price} — jetzt zugreifen!\n🛒 {link}\n\n#onlineshopping #gadgets #deals",
    "🛍️ {title}\n💶 Jetzt für €{price}\n👆 {link}\n\n#shopping #techgadgets #smarthome #sale",
    "💥 Deal: {title}\n💵 €{price}\n🔗 {link}\n\n#deals #gadgets #smarthome #lifestyle",
    "🎯 {title}\n⚡ Nur €{price} | Schnell!\n{link}\n\n#techdeals #gadgets #smarthome",
    "🌟 {title} — Top-Bewertungen!\n💶 €{price} | 🚚 Schnelle Lieferung\n{link}\n\n#shopping #deals",
    "🏆 Bestseller: {title}\n€{price} | ⭐⭐⭐⭐⭐ Qualität\n👉 {link}\n\n#bestseller #gadgets",
]

CAPTIONS_EN = [
    "🔥 Trending: {title}\n💶 Only €{price}\n👉 {link}\n\n#smarthome #gadgets #techdeals",
    "✨ New in shop: {title}\n€{price} — grab it now!\n🛒 {link}\n\n#deals #gadgets #tech",
    "💥 Deal of the day: {title}\n€{price}\n🔗 {link}\n\n#deals #gadgets #smarthome",
]

_BAD_IMG = ["media-amazon.com", "ssl-images-amazon.com", "images-amazon.com",
            "amazon.com/images", "logo", "brand", "icon", "placeholder",
            "no-image", "noimage", "default-image", "images.unsplash.com",
            "picsum.photos", "loremflickr"]

def _valid_img(url: str) -> bool:
    if not url: return False
    lower = url.lower()
    if any(p in lower for p in _BAD_IMG): return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", lower, re.I))

def _get_valid_img(images: list) -> str:
    for img in images:
        src = img.get("src", "") if isinstance(img, dict) else str(img)
        if _valid_img(src): return src
    return ""

def _caption(prod: dict, captions=None) -> str:
    tpl = random.choice(captions or CAPTIONS_DE)
    return tpl.format(**prod)

# ── Shopify Product ───────────────────────────────────────────────────────────

def get_random_product(vendor_blacklist=("Auto-Import", "AutoPilot Store", "AIITEC", "BullPowerHub")):
    page = random.randint(1, 8)
    url  = f"https://{SHOPIFY_DOMAIN}/products.json"
    products = []
    for pg in [page, 1, 2, 3]:
        try:
            r = requests.get(url, params={"limit": 50, "page": pg}, timeout=15)
            products = r.json().get("products", [])
            if products: break
        except Exception:
            continue
    if not products:
        raise RuntimeError("Keine Shopify-Produkte gefunden")
    products = [p for p in products if p.get("vendor", "") not in vendor_blacklist]
    with_img = [p for p in products if _get_valid_img(p.get("images", []))]
    pool = with_img or products
    if not pool:
        raise RuntimeError("Keine geeigneten Produkte")
    p   = random.choice(pool)
    img = _get_valid_img(p.get("images", []))
    price = p.get("variants", [{}])[0].get("price", "0")
    if float(price) == 29.99:
        log.warning("Placeholder-Preis €29.99 entdeckt — überspringe")
        pool = [x for x in pool if x.get("variants", [{}])[0].get("price", "0") != "29.99"]
        if pool:
            p = random.choice(pool)
            img = _get_valid_img(p.get("images", []))
            price = p.get("variants", [{}])[0].get("price", "0")
    return {
        "title": p.get("title", "Top Produkt"),
        "price": price,
        "img":   img,
        "link":  f"{SHOP_URL}/products/{p.get('handle', '')}",
        "handle": p.get("handle", ""),
    }

# ── Facebook ──────────────────────────────────────────────────────────────────

def post_facebook(prod: dict, page_id: str = None, token: str = None) -> bool:
    page_id = page_id or FB_PAGE_ID_AIITEC
    token   = token or FB_TOKEN_AIITEC
    if not token:
        log.warning("FACEBOOK_PAGE_TOKEN nicht gesetzt")
        return False
    caption = _caption(prod)
    if prod["img"]:
        r = requests.post(f"https://graph.facebook.com/v21.0/{page_id}/photos",
            data={"url": prod["img"], "caption": caption, "access_token": token}, timeout=20)
    else:
        r = requests.post(f"https://graph.facebook.com/v21.0/{page_id}/feed",
            data={"message": caption, "link": prod["link"], "access_token": token}, timeout=20)
    result = r.json()
    if "error" in result:
        log.error("Facebook: %s", result["error"].get("message", result))
        return False
    log.info("✅ Facebook (Page %s): %s", page_id, result.get("id") or result.get("post_id"))
    return True

# ── Instagram ─────────────────────────────────────────────────────────────────

def post_instagram(prod: dict) -> bool:
    if not FB_TOKEN_AIITEC or not IG_BUSINESS_ID:
        log.warning("Instagram: Token oder IG_BUSINESS_ID fehlt")
        return False
    if not prod["img"]:
        log.warning("Instagram: Kein Bild — übersprungen (IG braucht Bild)")
        return False
    caption = _caption(prod)
    # Step 1: Create media container
    r1 = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_BUSINESS_ID}/media",
        data={"image_url": prod["img"], "caption": caption, "access_token": FB_TOKEN_AIITEC},
        timeout=20)
    data1 = r1.json()
    if "error" in data1:
        log.error("Instagram create: %s", data1["error"].get("message", data1))
        return False
    creation_id = data1.get("id")
    if not creation_id:
        log.error("Instagram: Keine creation_id")
        return False
    # Step 2: Publish media container
    time.sleep(2)
    r2 = requests.post(
        f"https://graph.facebook.com/v21.0/{IG_BUSINESS_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": FB_TOKEN_AIITEC},
        timeout=20)
    data2 = r2.json()
    if "error" in data2:
        log.error("Instagram publish: %s", data2["error"].get("message", data2))
        return False
    log.info("✅ Instagram: post_id=%s", data2.get("id", "?"))
    return True

# ── Telegram ──────────────────────────────────────────────────────────────────

def post_telegram(prod: dict) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        log.warning("Telegram: Credentials fehlen")
        return False
    text = (f"🛍 *{prod['title']}*\n"
            f"💶 €{prod['price']}\n"
            f"[➡️ Jetzt kaufen]({prod['link']})")
    if prod["img"]:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT_ID, "photo": prod["img"],
                  "caption": text, "parse_mode": "Markdown"}, timeout=15)
    else:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)
    result = r.json()
    ok = result.get("ok", False)
    if ok:
        log.info("✅ Telegram: message_id=%s", result.get("result", {}).get("message_id"))
    else:
        log.error("Telegram: %s", result.get("description"))
    return ok

# ── LinkedIn ──────────────────────────────────────────────────────────────────

def _li_refresh_token() -> str:
    if not LI_REFRESH: return LI_TOKEN
    r = requests.post("https://www.linkedin.com/oauth/v2/accessToken",
        data={"grant_type": "refresh_token", "refresh_token": LI_REFRESH,
              "client_id": LI_CLIENT_ID, "client_secret": LI_CLIENT_SEC},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    new_token = r.json().get("access_token", "")
    if new_token:
        log.info("LinkedIn token refreshed")
        # Update .env in memory for this session
        os.environ["LINKEDIN_ACCESS_TOKEN"] = new_token
    return new_token or LI_TOKEN

def post_linkedin(prod: dict) -> bool:
    token = _li_refresh_token()
    if not token or not LI_PERSON_URN:
        log.warning("LinkedIn: Token fehlt")
        return False
    text = (f"🔥 {prod['title']}\n\n"
            f"💶 Nur €{prod['price']} — jetzt im Shop!\n"
            f"👉 {prod['link']}\n\n"
            f"#SmartHome #Gadgets #Deals #Ecommerce #OnlineShopping #AI #Innovation")
    body = {
        "author": LI_PERSON_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "ARTICLE",
                "media": [{"status": "READY", "originalUrl": prod["link"]}],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    r = requests.post("https://api.linkedin.com/v2/ugcPosts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "X-Restli-Protocol-Version": "2.0.0"},
        json=body, timeout=20)
    if r.status_code in (200, 201):
        log.info("✅ LinkedIn: %s", r.json().get("id", "?"))
        return True
    log.error("LinkedIn: %s %s", r.status_code, r.text[:200])
    return False

# ── Reddit ────────────────────────────────────────────────────────────────────

def _reddit_token() -> str:
    creds = base64.b64encode(f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SEC}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}",
               "User-Agent": "SuperMegaBot:v2.1 (by /u/bullpowersrtkennels)"}
    # Try refresh token first, then password flow
    if REDDIT_REFRESH:
        r = requests.post("https://www.reddit.com/api/v1/access_token",
            headers=headers, data={"grant_type": "refresh_token", "refresh_token": REDDIT_REFRESH},
            timeout=15)
        token = r.json().get("access_token", "")
        if token: return token
    # Password flow (only works for "script" app type)
    r = requests.post("https://www.reddit.com/api/v1/access_token",
        headers=headers,
        data={"grant_type": "password", "username": REDDIT_USER, "password": REDDIT_PASS},
        timeout=15)
    return r.json().get("access_token", "")

def post_reddit(prod: dict) -> bool:
    token = _reddit_token()
    if not token:
        log.error("Reddit: Token-Refresh fehlgeschlagen (App-Typ muss 'script' sein)")
        return False
    sub   = random.choice(REDDIT_SUBS)
    title = f"🔥 {prod['title']} — nur €{prod['price']} | ineedit.com.co"
    body  = (f"**{prod['title']}**\n\n"
             f"💶 Preis: **€{prod['price']}**\n"
             f"🛒 [Jetzt kaufen]({prod['link']})\n\n"
             f"*Automatisierter Post — SuperMegaBot v2*")
    r = requests.post("https://oauth.reddit.com/api/submit",
        headers={"Authorization": f"bearer {token}",
                 "User-Agent": "SuperMegaBot:v2.1 (by /u/bullpowersrtkennels)"},
        data={"sr": sub, "kind": "self", "title": title, "text": body, "resubmit": True},
        timeout=20)
    data = r.json()
    url  = data.get("json", {}).get("data", {}).get("url", "")
    errs = data.get("json", {}).get("errors", [])
    if errs:
        log.error("Reddit r/%s: %s", sub, errs)
        return False
    log.info("✅ Reddit r/%s: %s", sub, url or "gepostet")
    return True

# ── Discord ───────────────────────────────────────────────────────────────────

def post_discord(prod: dict) -> bool:
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        log.warning("Discord: Token oder Channel-ID fehlt (DISCORD_CHANNEL_ID setzen)")
        return False
    text = (f"🛍️ **{prod['title']}**\n"
            f"💶 **€{prod['price']}**\n"
            f"🔗 {prod['link']}\n\n"
            f"#deals #gadgets #smarthome")
    payload = {"content": text}
    if prod["img"]:
        payload["embeds"] = [{"image": {"url": prod["img"]}, "color": 0xC9A84C}]
    r = requests.post(f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
        headers={"Authorization": f"Bot {DISCORD_TOKEN}", "Content-Type": "application/json"},
        json=payload, timeout=15)
    if r.status_code == 200:
        log.info("✅ Discord: message_id=%s", r.json().get("id", "?"))
        return True
    log.error("Discord: %s %s", r.status_code, r.text[:200])
    return False

# ── Pinterest ─────────────────────────────────────────────────────────────────

def post_pinterest(prod: dict) -> bool:
    token = PINTEREST_TOKEN or os.getenv("PINTEREST_ACCESS_TOKEN", "")
    board = PINTEREST_BOARD_ID or os.getenv("PINTEREST_BOARD_ID", "")
    if not token or not board:
        log.warning("Pinterest: ACCESS_TOKEN oder BOARD_ID fehlt (OAuth nötig)")
        return False
    if not prod["img"]:
        log.warning("Pinterest: Kein Bild — übersprungen")
        return False
    body = {
        "board_id": board,
        "title": prod["title"],
        "description": f"💶 €{prod['price']} | {prod['link']}",
        "link": prod["link"],
        "media_source": {"source_type": "image_url", "url": prod["img"]},
    }
    r = requests.post("https://api.pinterest.com/v5/pins",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=20)
    if r.status_code in (200, 201):
        log.info("✅ Pinterest: pin_id=%s", r.json().get("id", "?"))
        return True
    log.error("Pinterest: %s %s", r.status_code, r.text[:200])
    return False

# ── Gumroad ───────────────────────────────────────────────────────────────────

def post_gumroad_update(prod: dict) -> bool:
    if not GUMROAD_TOKEN:
        log.warning("Gumroad: ACCESS_TOKEN fehlt")
        return False
    # Post as an update/ping to followers
    r = requests.get("https://api.gumroad.com/v2/products",
        params={"access_token": GUMROAD_TOKEN}, timeout=15)
    if r.status_code != 200:
        log.error("Gumroad: %s %s", r.status_code, r.text[:200])
        return False
    products = r.json().get("products", [])
    if not products:
        log.warning("Gumroad: Keine Produkte gefunden")
        return False
    log.info("✅ Gumroad: %d Produkte aktiv — kein direktes Posting via API (nur Produktverwaltung)", len(products))
    return True

# ── YouTube ───────────────────────────────────────────────────────────────────

def _yt_access_token() -> str:
    if not YT_REFRESH or not YT_CLIENT_ID or not YT_CLIENT_SEC:
        return ""
    r = requests.post("https://oauth2.googleapis.com/token",
        data={"client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SEC,
              "refresh_token": YT_REFRESH, "grant_type": "refresh_token"}, timeout=15)
    token = r.json().get("access_token", "")
    if token:
        log.info("✅ YouTube: Access token OK")
    else:
        log.error("YouTube token refresh failed: %s", r.json())
    return token

def post_youtube_community(prod: dict) -> bool:
    token = _yt_access_token()
    if not token:
        log.warning("YouTube: Kein Access Token")
        return False
    # YouTube Community Posts API (v3 - activities endpoint)
    text = (f"🔥 {prod['title']}\n\n"
            f"💶 Nur €{prod['price']}\n"
            f"👉 {prod['link']}\n\n"
            f"#SmartHome #Gadgets #Deals")
    body = {
        "kind": "youtube#activity",
        "snippet": {
            "type": "bulletin",
            "bulletin": {"resourceId": {}},
            "description": text,
        }
    }
    r = requests.post(
        "https://www.googleapis.com/youtube/v3/activities",
        params={"part": "snippet,contentDetails"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=20)
    if r.status_code in (200, 201):
        log.info("✅ YouTube Community: %s", r.json().get("id", "?"))
        return True
    # YouTube Community Posts endpoint changed/deprecated - try channel posts
    log.warning("YouTube Community API: %s (API endpoint deprecated by Google)", r.status_code)
    return False

# ── eBay Classified Ad ────────────────────────────────────────────────────────

def _ebay_app_token() -> str:
    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SEC}".encode()).decode()
    r = requests.post("https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=15)
    return r.json().get("access_token", "")

def post_ebay_listing(prod: dict) -> bool:
    if not EBAY_USER_TOKEN:
        log.warning("eBay: USER_TOKEN fehlt (OAuth nötig für Listings)")
        return False
    # Would need user-level OAuth token to create listings
    token = _ebay_app_token()
    if token:
        log.info("✅ eBay: App-Token OK (User-OAuth für Listings noch nötig)")
    return False

# ── Facebook ineedit Page ─────────────────────────────────────────────────────

def post_facebook_ineedit(prod: dict) -> bool:
    if not FB_TOKEN_INEEDIT:
        log.warning("Facebook ineedit: Token fehlt")
        return False
    return post_facebook(prod, page_id=FB_PAGE_ID_INEEDIT, token=FB_TOKEN_INEEDIT)

# ── Main ──────────────────────────────────────────────────────────────────────

def run_autopost(dry_run: bool = False):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("🚀 Multi-Platform Autopost — %s", ts)

    try:
        prod = get_random_product()
        log.info("📦 Produkt: %s | €%s | img=%s", prod["title"], prod["price"], "✅" if prod["img"] else "❌")
    except Exception as e:
        log.error("Produkt-Fehler: %s", e)
        sys.exit(1)

    if dry_run:
        log.info("DRY RUN — kein echter Post")
        log.info("Würde posten: %s", json.dumps(prod, ensure_ascii=False))
        return

    results = {}

    # Facebook AiiteC Page
    results["Facebook_AiiteC"]  = post_facebook(prod)
    # Facebook ineedit Page
    results["Facebook_ineedit"] = post_facebook_ineedit(prod)
    # Instagram
    results["Instagram"]  = post_instagram(prod)
    # Telegram
    results["Telegram"]   = post_telegram(prod)
    # LinkedIn
    results["LinkedIn"]   = post_linkedin(prod)
    # Reddit
    results["Reddit"]     = post_reddit(prod)
    # Discord
    results["Discord"]    = post_discord(prod)
    # Pinterest
    results["Pinterest"]  = post_pinterest(prod)
    # YouTube Community
    results["YouTube"]    = post_youtube_community(prod)
    # Gumroad
    results["Gumroad"]    = post_gumroad_update(prod)
    # eBay
    results["eBay"]       = post_ebay_listing(prod)

    ok  = [k for k, v in results.items() if v]
    err = [k for k, v in results.items() if not v]

    log.info("✅ OK: %s", ", ".join(ok) if ok else "–")
    if err:
        log.warning("❌ Fehler/nicht konfiguriert: %s", ", ".join(err))

    if not results.get("Facebook_AiiteC") and not results.get("Telegram"):
        log.error("Haupt-Kanäle fehlgeschlagen")
        sys.exit(1)

    log.info("🎉 Autopost abgeschlossen — %d/%d Plattformen", len(ok), len(results))

if __name__ == "__main__":
    dry = "--dry" in sys.argv or "--dry-run" in sys.argv
    run_autopost(dry_run=dry)
