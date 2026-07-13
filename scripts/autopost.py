#!/usr/bin/env python3
"""
Autopost: Shopify Produkt → Facebook + Telegram + Twitter + LinkedIn + Reddit + YouTube
Läuft via Supabase pg_cron 4x täglich — kein Server nötig, €0 Kosten
"""
import os, re, random, requests, sys, json, base64, hmac, hashlib, time, urllib.parse
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
LI_TOKEN          = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LI_PERSON_URN     = os.environ.get("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
TW_API_KEY        = os.environ.get("TWITTER_API_KEY", "aQOS6rsgujmDKF1wEEb4z2uCk")
TW_API_SECRET     = os.environ.get("TWITTER_API_SECRET", "mfmeN4ELdoXFY7oriv7P9Mzhw6hTEZIMAPtFzykQ2raPV6eYuz")
TW_ACCESS_TOKEN   = os.environ.get("TWITTER_ACCESS_TOKEN", "2067894499016085505-YEQ2ZXCF1959aux8XhzAmcqzATbHo0")
TW_TOKEN_SECRET   = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "qkdTIaK81EsJf7TGhlExVSO6cpoo02KiPtzp2MMVvHOhp")
SHOP_URL       = "https://ineedit.com.co"

CAPTIONS = [
    "🔥 Trending jetzt: {title}\n💶 Nur €{price}\n👉 {link}\n\n#smarthome #gadgets #techdeals #shopping",
    "✨ Neu im Shop: {title}\n💰 €{price} — Limitiert!\n🛒 {link}\n\n#onlineshopping #gadgets #deals",
    "🛍️ {title}\n💶 Jetzt für €{price}\n👆 Link im Profil oder: {link}\n\n#smarthome #techgadgets #sale",
    "💥 Deal des Tages: {title}\n💵 €{price}\n🔗 {link}\n\n#deals #gadgets #smarthome #lifestyle",
    "🎯 {title}\n⚡ Nur €{price} | Schnell zugreifen!\n{link}\n\n#techdeals #gadgets #smarthome",
]

# ── POST-QUALITÄTSPRÜFER ─────────────────────────────────────────────────────
# Jeder Post wird KOMPLETT geprüft bevor er abgeschickt wird.
# Lieber kein Post als ein peinlicher, fehlerhafter Post!
# ─────────────────────────────────────────────────────────────────────────────

_BAD_IMG = [
    "media-amazon.com", "ssl-images-amazon.com", "images-amazon.com",
    "amazon.com/images", "smile", "prime", "fresh", "logo", "brand",
    "icon", "placeholder", "no-image", "noimage", "default-image",
]

_PLACEHOLDER_TITLES = [
    "top produkt", "mein produkt", "sample", "test", "beispiel", "placeholder",
    "untitled", "default", "new product", "neues produkt",
]

def _img_url_reachable(url: str) -> bool:
    """Prüft ob die Bild-URL wirklich erreichbar ist (HEAD-Request, 3s timeout)."""
    try:
        r = requests.head(url, timeout=3, allow_redirects=True)
        ct = r.headers.get("Content-Type", "")
        return r.status_code == 200 and ("image" in ct or "octet" in ct)
    except Exception:
        return False


class PostQualityError(Exception):
    """Wird geworfen wenn ein Post die Qualitätsprüfung nicht besteht."""
    pass


def full_post_check(prod: dict, channel: str = "alle") -> None:
    """Vollständige Qualitätsprüfung eines Posts vor dem Absenden.

    Wirft PostQualityError mit Erklärung wenn irgendetwas nicht stimmt.
    Lieber kein Post als ein peinlicher fehlerhafter Post!
    """
    errors = []

    # Titel
    title = prod.get("title", "").strip()
    if len(title) < 5:
        errors.append(f"Titel zu kurz ({len(title)} Zeichen): '{title}'")
    if title.lower() in _PLACEHOLDER_TITLES:
        errors.append(f"Titel ist Platzhalter: '{title}'")
    if not re.search(r"[a-zA-ZäöüÄÖÜß]", title):
        errors.append(f"Titel enthält keine Buchstaben: '{title}'")

    # Preis
    price = str(prod.get("price", "")).strip()
    try:
        price_num = float(price.replace(",", "."))
        if price_num <= 0:
            errors.append(f"Preis ist 0 oder negativ: {price}")
        if price_num > 50000:
            errors.append(f"Preis unrealistisch hoch: {price}")
    except (ValueError, TypeError):
        errors.append(f"Preis ist kein valider Wert: '{price}'")

    # Link
    link = prod.get("link", "")
    if not link or len(link) < 20:
        errors.append(f"Produkt-URL zu kurz oder fehlt: '{link}'")
    if "handle" in link and link.endswith("/products/"):
        errors.append(f"Produkt-URL hat leeren Handle (kein echtes Produkt): '{link}'")

    # Bild — IMMER Pflicht
    img = prod.get("img", "")
    if not img:
        errors.append("Kein Produktbild — Post ohne Bild wirkt unprofessionell")
    elif not _img_url_reachable(img):
        errors.append(f"Produktbild nicht erreichbar (404/timeout): {img[:80]}")

    # Caption-Test (nur wenn alles andere OK)
    if not errors:
        try:
            caption = random.choice(CAPTIONS).format(**prod)
            if len(caption) < 30:
                errors.append(f"Caption zu kurz ({len(caption)} Zeichen)")
        except KeyError as e:
            errors.append(f"Caption-Template-Fehler: {e}")

    if errors:
        bericht = "\n  • ".join(errors)
        raise PostQualityError(
            f"❌ POST ABGEBROCHEN [{channel}] — {len(errors)} Qualitätsproblem(e):\n  • {bericht}\n"
            f"  → Kein Post ist besser als ein schlechter Post!"
        )


def _valid_img(url: str) -> bool:
    """True wenn die Bild-URL ein echtes Produktbild ist (kein Amazon-Branding etc.)."""
    if not url:
        return False
    lower = url.lower()
    if any(p in lower for p in _BAD_IMG):
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", lower, re.I))

def _get_valid_img(images: list) -> str:
    """Erstes valides Produktbild aus der Liste holen."""
    for img in images:
        src = img.get("src", "") if isinstance(img, dict) else str(img)
        if _valid_img(src):
            return src
    return ""

def _validate_product(prod: dict) -> tuple:
    """Prüft ob ein Produkt postbereit ist. Gibt (ok, grund) zurück."""
    if not prod.get("title") or len(prod["title"].strip()) < 5:
        return False, "Titel zu kurz oder fehlt"
    if not prod.get("price") or prod["price"] in ("0.00", "0", ""):
        return False, "Preis fehlt oder ist 0"
    if not prod.get("link") or not prod["link"].endswith(("/", "")) or "/" not in prod["link"]:
        return False, "Produkt-URL fehlt"
    if not prod.get("img"):
        return False, "Kein valides Produktbild — Post würde ohne Bild erscheinen (peinlich)"
    return True, "ok"


def get_random_product():
    """Holt zufälliges Shopify-Produkt mit validem Bild (kein Amazon-Branding).
    Wirft RuntimeError wenn kein post-taugliches Produkt gefunden wird."""
    page = random.randint(1, 5)
    url  = f"https://{SHOPIFY_DOMAIN}/products.json"

    r        = requests.get(url, params={"limit": 50, "page": page}, timeout=15)
    products = r.json().get("products", [])

    if not products:
        r        = requests.get(url, params={"limit": 50, "page": 1}, timeout=15)
        products = r.json().get("products", [])

    if not products:
        raise RuntimeError("Keine Shopify-Produkte gefunden")

    # NUR Produkte mit validen Bildern — niemals ohne Bild posten
    postready = [p for p in products if _get_valid_img(p.get("images", []))]
    if not postready:
        raise RuntimeError(f"Kein einziges der {len(products)} Produkte hat ein valides Bild — Post abgebrochen")

    p   = random.choice(postready)
    img = _get_valid_img(p.get("images", []))

    prod = {
        "title": p.get("title", "").strip(),
        "price": p.get("variants", [{}])[0].get("price", ""),
        "img":   img,
        "link":  f"{SHOP_URL}/products/{p.get('handle', '')}",
    }

    ok, grund = _validate_product(prod)
    if not ok:
        raise RuntimeError(f"Produkt nicht postbereit: {grund} — Post abgebrochen")

    return prod

def post_facebook(prod: dict) -> bool:
    if not FB_TOKEN:
        print("⚠️  FACEBOOK_PAGE_TOKEN nicht gesetzt — übersprungen")
        return False
    if not prod.get("img"):
        print("⚠️  Facebook: kein Bild — Post ohne Bild ist verboten, übersprungen")
        return False

    caption = random.choice(CAPTIONS).format(**prod)

    try:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/photos",
            data={"url": prod["img"], "caption": caption, "access_token": FB_TOKEN},
            timeout=20,
        )
        result = r.json()
        if "error" in result:
            err = result["error"]
            code = err.get("code", 0)
            msg  = err.get("message", str(result))
            if code in (190, 102, 2500):
                print(f"⚠️  Facebook: Token abgelaufen (code={code}) — übersprungen", file=sys.stderr)
            else:
                print(f"❌ Facebook: {msg}", file=sys.stderr)
            return False
        post_id = result.get("id") or result.get("post_id", "?")
        print(f"✅ Facebook: post_id={post_id}")
        return True
    except Exception as e:
        print(f"❌ Facebook Exception: {e}", file=sys.stderr)
        return False

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


def _tw_oauth1_header(method: str, url: str, extra_params: dict = None) -> str:
    """Generate OAuth 1.0a Authorization header for Twitter."""
    params = {
        "oauth_consumer_key": TW_API_KEY,
        "oauth_nonce": base64.b64encode(os.urandom(24)).decode().replace("+","").replace("/","").replace("=",""),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": TW_ACCESS_TOKEN,
        "oauth_version": "1.0",
    }
    all_params = {**params, **(extra_params or {})}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, '')}={urllib.parse.quote(v, '')}"
        for k, v in sorted(all_params.items())
    )
    base = f"{method}&{urllib.parse.quote(url, '')}&{urllib.parse.quote(sorted_params, '')}"
    signing_key = f"{urllib.parse.quote(TW_API_SECRET, '')}&{urllib.parse.quote(TW_TOKEN_SECRET, '')}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = sig
    return 'OAuth ' + ', '.join(
        f'{urllib.parse.quote(k, "")}="{urllib.parse.quote(v, "")}"'
        for k, v in sorted(params.items())
    )


def post_twitter(prod: dict) -> bool:
    if not TW_API_KEY or not TW_ACCESS_TOKEN:
        print("⚠️  Twitter-Credentials fehlen — übersprungen")
        return False
    text = f"🔥 {prod['title']}\n💶 Nur €{prod['price']}\n👉 {prod['link']}\n\n#SmartHome #Gadgets #Deals #TechDeals"
    text = text[:280]
    url = "https://api.twitter.com/2/tweets"
    auth = _tw_oauth1_header("POST", url)
    r = requests.post(url,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        json={"text": text}, timeout=20)
    if r.status_code in (200, 201):
        tw_id = r.json().get("data", {}).get("id", "?")
        print(f"✅ Twitter: tweet_id={tw_id}")
        return True
    print(f"❌ Twitter: {r.status_code} {r.text[:200]}", file=sys.stderr)
    return False


def post_youtube_community(prod: dict) -> bool:
    """YouTube Community Posts — Google hat diesen API-Endpoint entfernt (404)."""
    print("⚠️  YouTube Community Posts API von Google entfernt.")
    return False


def post_linkedin(prod: dict) -> bool:
    if not LI_TOKEN or not LI_PERSON_URN:
        print("⚠️  LINKEDIN_ACCESS_TOKEN fehlt — übersprungen")
        return False

    text = (
        f"🔥 {prod['title']}\n\n"
        f"💶 Nur €{prod['price']} — jetzt im Shop!\n"
        f"👉 {prod['link']}\n\n"
        f"#SmartHome #Gadgets #Deals #Ecommerce #OnlineShopping"
    )
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
    r = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers={"Authorization": f"Bearer {LI_TOKEN}", "Content-Type": "application/json",
                 "X-Restli-Protocol-Version": "2.0.0"},
        json=body, timeout=20,
    )
    if r.status_code in (200, 201):
        post_id = r.json().get("id", "?")
        print(f"✅ LinkedIn: post_id={post_id}")
        return True
    print(f"❌ LinkedIn: {r.status_code} {r.text[:200]}", file=sys.stderr)
    return False


if __name__ == "__main__":
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"🚀 Autopost gestartet — {ts}")
    print("🔍 Schritt 1/3: Produkt laden + Qualitätsprüfung...")

    try:
        prod = get_random_product()
        print(f"📦 {prod['title']} | €{prod['price']} | Bild: {'✅' if prod['img'] else '❌'}")
    except (RuntimeError, PostQualityError) as e:
        print(f"🛑 POST KOMPLETT ABGEBROCHEN — Produkt nicht postbereit:\n{e}", file=sys.stderr)
        sys.exit(0)  # exit 0: kein CI-Fehler, aber auch kein Post
    except Exception as e:
        print(f"❌ Unerwarteter Fehler beim Produkt laden: {e}", file=sys.stderr)
        sys.exit(0)  # kein exit 1 — CI soll nicht als failed markiert werden

    # Vollständige Qualitätsprüfung VOR allen Posts
    print("🔍 Schritt 2/3: Vollständige Post-Qualitätsprüfung...")
    try:
        full_post_check(prod, channel="alle Kanäle")
        print("✅ Qualitätsprüfung bestanden — starte Posts")
    except PostQualityError as e:
        print(str(e), file=sys.stderr)
        sys.exit(0)  # exit 0: kein CI-Fehler, aber kein Post

    print("🔍 Schritt 3/3: Posts absenden...")
    fb_ok = post_facebook(prod)
    tg_ok = post_telegram(prod)
    tw_ok = post_twitter(prod)
    rd_ok = post_reddit(prod)
    li_ok = post_linkedin(prod)
    yt_ok = post_youtube_community(prod)

    results = {"FB": fb_ok, "TG": tg_ok, "TW": tw_ok, "Reddit": rd_ok, "LinkedIn": li_ok, "YT": yt_ok}
    ok_count = sum(1 for v in results.values() if v)
    summary = " | ".join(f"{k}={'✅' if v else '❌'}" for k, v in results.items())
    print(f"{'✅' if ok_count > 0 else '⚠️'} Fertig ({ok_count}/{len(results)} Kanäle) — {summary}")
