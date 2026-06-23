#!/usr/bin/env python3
"""Meta Social Engine — Autonomous Facebook, Instagram & Pinterest poster"""
import asyncio, aiohttp, os, json, logging, sqlite3, random, time as _time
import xml.etree.ElementTree as ET
from datetime import datetime
import anthropic

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
# Facebook / Instagram (Meta Graph API)
FB_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", os.getenv("FACEBOOK_USER_TOKEN", os.getenv("FB_ACCESS_TOKEN", "")))
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", os.getenv("FB_PAGE_ID", ""))
FB_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
IG_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", os.getenv("IG_ACCOUNT_ID", ""))
# Pinterest API v5
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")
PORT = int(os.getenv("PORT", 8091))
SCHEDULE_INTERVAL = int(os.getenv("POST_INTERVAL_SECONDS", 1800))  # default 30 min
INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "a1b2c3d4e5f6789012345678901234ab")

_trending_cache: list = []
_last_trends_fetch: float = 0


async def fetch_google_trends() -> list:
    global _trending_cache, _last_trends_fetch
    if _time.time() - _last_trends_fetch < 7200:
        return _trending_cache
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    text = await r.text()
                    root = ET.fromstring(text)
                    topics = [item.findtext("title", "").strip()
                              for item in root.findall(".//item")
                              if item.findtext("title", "")][:10]
                    _trending_cache = topics
                    _last_trends_fetch = _time.time()
                    logger.info(f"Google Trends DE: {topics[:5]}")
                    return topics
    except Exception as e:
        logger.warning(f"Trends fetch: {e}")
    return _trending_cache or ["E-Commerce", "Shopify", "KI Tools", "Dropshipping", "Online Geld verdienen"]


async def indexnow_ping(url: str):
    try:
        payload = {"host": "bullpowerhub.de", "key": INDEXNOW_KEY, "urlList": [url]}
        async with aiohttp.ClientSession() as s:
            await s.post("https://api.indexnow.org/indexnow", json=payload,
                         timeout=aiohttp.ClientTimeout(total=8))
            logger.info(f"IndexNow ping: {url}")
    except Exception as e:
        logger.warning(f"IndexNow: {e}")
MC_API_KEY  = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER   = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
MC_LIST_ID  = os.getenv("MAILCHIMP_LIST_ID", "")
KV_API_KEY  = os.getenv("KLAVIYO_API_KEY", "")
KV_LIST_ID  = os.getenv("KLAVIYO_LIST_ID", "")

# ── SEO Traffic Engine Bridge ──────────────────────────────────────────────
_SEO_ENGINE = os.getenv("SEO_ENGINE_URL", "https://seo-traffic-engine-production.up.railway.app")
_AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpower-21")
_EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")


async def seo_get_products(keyword: str, source: str = "all") -> list:
    import urllib.parse
    results = []
    if source in ("amazon", "all"):
        amazon_url = f"https://www.amazon.de/s?k={urllib.parse.quote(keyword)}&tag={_AMAZON_TAG}"
        results.append({"title": f"Amazon: {keyword}", "url": amazon_url, "source": "amazon", "price": ""})
    if source in ("ebay", "all") and _EBAY_APP_ID:
        try:
            params = f"OPERATION-NAME=findItemsByKeywords&SERVICE-VERSION=1.0.0&SECURITY-APPNAME={_EBAY_APP_ID}&RESPONSE-DATA-FORMAT=JSON&keywords={urllib.parse.quote(keyword)}&paginationInput.entriesPerPage=3"
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://svcs.ebay.com/services/search/FindingService/v1?{params}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("findItemsByKeywordsResponse", [{}])[0].get("searchResult", [{}])[0].get("item", [])
                        for item in items[:3]:
                            results.append({"title": item.get("title", [""])[0], "url": item.get("viewItemURL", [""])[0], "source": "ebay", "price": item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0].get("__value__", "")})
        except Exception as e:
            logger.warning(f"eBay API: {e}")
    elif source in ("ebay", "all"):
        import urllib.parse as _up
        ebay_url = f"https://www.ebay.de/sch/i.html?_nkw={_up.quote(keyword)}"
        results.append({"title": f"eBay: {keyword}", "url": ebay_url, "source": "ebay", "price": ""})
    return results


async def klaviyo_track(event: str, props: dict):
    if not KV_API_KEY:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                "https://a.klaviyo.com/api/events/",
                headers={"Authorization": f"Klaviyo-API-Key {KV_API_KEY}",
                         "revision": "2024-06-15", "Content-Type": "application/json"},
                json={"data": {"type": "event", "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": event}}},
                    "properties": props,
                }}},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def seo_push_keyword(keyword: str, url: str = "") -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{_SEO_ENGINE}/api/trigger/articles", json={"keyword": keyword}, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status == 200
    except Exception:
        return False
# ── End SEO Bridge ──────────────────────────────────────────────────────────

PRODUCTS = [
    {"name": "Shopify Acquisition Engine", "url": "https://shopify-acquisition-engine-production.up.railway.app", "price": "€49/mo", "tagline": "KI findet automatisch Bestseller-Produkte für deinen Shopify-Store"},
    {"name": "SEO Turbo Tools", "url": "https://seo-turbo-tools-production.up.railway.app", "price": "€29/mo", "tagline": "Automatische SEO-Analyse & Meta-Description Generator"},
    {"name": "iComeAuto SaaS", "url": "https://icomeauto-saas-production.up.railway.app", "price": "€29/mo", "tagline": "Vollautomatisches Einkommenssystem"},
    {"name": "SuperMegaBot", "url": "https://dudirudibot-mega-production.up.railway.app", "price": "€49/mo", "tagline": "110+ Bot-Commands für E-Commerce Automatisierung"},
]

DB_PATH = "/tmp/meta_engine.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT, content TEXT, image_prompt TEXT,
        product_name TEXT, status TEXT DEFAULT 'queued',
        created_at TEXT, posted_at TEXT
    )""")
    conn.commit()
    conn.close()


async def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


def _fallback_meta_post(product: dict, post_type: str) -> dict:
    name = product["name"]
    price = product["price"]
    url = product["url"]
    tagline = product.get("tagline", "")
    if post_type == "instagram":
        content = (
            f"🚀 {name}\n\n{tagline}\n\n"
            f"💶 Nur {price} — Jetzt sichern!\n👉 Link in Bio\n\n"
            f"#OnlineBusiness #Shopify #Automatisierung #KI #Ecommerce #PassivEinkommen #Dropshipping"
        )
    else:
        content = (
            f"🔥 {name}\n\n{tagline}\n\n✅ Nur {price} — Sofort verfügbar!\n👉 {url}\n\n"
            f"#OnlineBusiness #Shopify #Automatisierung #KI"
        )
    return {"content": content, "product": name, "url": url, "platform": post_type}


async def generate_meta_post(product: dict, post_type: str = "facebook") -> dict:
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        trends = await fetch_google_trends()
        trend_hint = f"\nAktuelle Trends (einbauen wenn relevant): {', '.join(trends[:5])}" if trends else ""

        if post_type == "instagram":
            prompt = f"""Erstelle einen Instagram-Post auf Deutsch für: {product['name']}
Preis: {product['price']}
Tagline: {product['tagline']}{trend_hint}

FORMAT:
- Catchy Einstieg (1-2 Zeilen mit Emoji)
- 3-4 Zeilen Mehrwert/Benefits
- Call-to-Action (Link in Bio)
- 15-20 relevante Hashtags auf Deutsch und Englisch

Beispiel-Hashtags: #Shopify #Automatisierung #OnlineBusiness #KI #Dropshipping #Ecommerce #PassivEinkommen"""
        else:
            prompt = f"""Erstelle einen Facebook-Post auf Deutsch für: {product['name']}
Preis: {product['price']}
Tagline: {product['tagline']}
URL: {product['url']}{trend_hint}

FORMAT:
- Aufmerksamkeits-starker Titel (mit Emoji)
- 2-3 Absätze mit echtem Mehrwert
- Spezifische Vorteile als Liste
- Starker CTA mit Link
- 5-8 Hashtags

Ton: Professionell aber persönlich, wie ein Freund der einen tollen Tipp teilt."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.content[0].text
        return {"content": content, "product": product["name"], "url": product["url"], "platform": post_type}
    except Exception as e:
        logger.warning("generate_meta_post fallback (%s): %s", post_type, e)
        return _fallback_meta_post(product, post_type)


async def post_to_facebook(content: str, page_id: str, access_token: str) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                params={"access_token": access_token},
                json={"message": content}
            )
            data = await resp.json()
            if "id" in data:
                logger.info(f"Facebook post success: {data['id']}")
                return True
            else:
                logger.error(f"Facebook post failed: {data}")
                return False
    except Exception as e:
        logger.error(f"Facebook API error: {e}")
        return False


async def post_to_instagram(image_url: str, caption: str, ig_account_id: str, access_token: str) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(
                f"https://graph.facebook.com/v19.0/{ig_account_id}/media",
                params={"access_token": access_token},
                json={"image_url": image_url, "caption": caption}
            )
            data = await resp.json()
            creation_id = data.get("id")
            if not creation_id:
                return False
            await asyncio.sleep(2)
            resp2 = await s.post(
                f"https://graph.facebook.com/v19.0/{ig_account_id}/media_publish",
                params={"access_token": access_token},
                json={"creation_id": creation_id}
            )
            data2 = await resp2.json()
            return "id" in data2
    except Exception as e:
        logger.error(f"Instagram API error: {e}")
        return False


async def post_to_pinterest(title: str, description: str, link: str, image_url: str,
                             access_token: str, board_id: str) -> bool:
    """Pinterest API v5 — creates a Pin on the specified board."""
    try:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(
                "https://api.pinterest.com/v5/pins",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "board_id": board_id,
                    "title": title[:100],
                    "description": description[:500],
                    "link": link,
                    "media_source": {
                        "source_type": "image_url",
                        "url": image_url,
                    },
                }
            )
            data = await resp.json()
            if resp.status == 201 and "id" in data:
                logger.info(f"Pinterest pin created: {data['id']}")
                return True
            else:
                logger.error(f"Pinterest API failed ({resp.status}): {data}")
                return False
    except Exception as e:
        logger.error(f"Pinterest API error: {e}")
        return False


async def generate_pinterest_pin(product: dict) -> dict:
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f"Erstelle einen Pinterest Pin für: {product['name']}\n"
                f"Preis: {product['price']}\nTagline: {product['tagline']}\n\n"
                "FORMAT (JSON, kein Markdown):\n"
                "{\"title\": \"max 100 Zeichen\", \"description\": \"max 500 Zeichen mit Keywords für SEO\"}"
            )}]
        )
        try:
            pin = json.loads(resp.content[0].text)
        except Exception:
            pin = {"title": product["name"], "description": product["tagline"]}
        pin["link"] = product["url"]
        return pin
    except Exception as e:
        logger.warning("generate_pinterest_pin fallback: %s", e)
        return {"title": product["name"], "description": product.get("tagline", ""), "link": product["url"]}
    return pin


async def content_cycle():
    product = random.choice(PRODUCTS)

    fb_post = await generate_meta_post(product, "facebook")
    ig_post = await generate_meta_post(product, "instagram")
    pin_post = await generate_pinterest_pin(product)

    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO posts (platform, content, product_name, status, created_at) VALUES (?,?,?,?,?)",
                 ("facebook", fb_post["content"], product["name"], "queued", now))
    conn.execute("INSERT INTO posts (platform, content, product_name, status, created_at) VALUES (?,?,?,?,?)",
                 ("instagram", ig_post["content"], product["name"], "queued", now))
    conn.execute("INSERT INTO posts (platform, content, product_name, status, created_at) VALUES (?,?,?,?,?)",
                 ("pinterest", pin_post.get("description", ""), product["name"], "queued", now))
    conn.commit()
    conn.close()

    fb_posted = ig_posted = pin_posted = False
    og_image = f"{product['url']}/og-image.png"

    if FB_ACCESS_TOKEN and FB_PAGE_ID:
        fb_posted = await post_to_facebook(fb_post["content"], FB_PAGE_ID, FB_ACCESS_TOKEN)

    if IG_ACCOUNT_ID and FB_ACCESS_TOKEN:
        ig_posted = await post_to_instagram(og_image, ig_post["content"], IG_ACCOUNT_ID, FB_ACCESS_TOKEN)

    if PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID:
        pin_posted = await post_to_pinterest(
            title=pin_post.get("title", product["name"]),
            description=pin_post.get("description", product["tagline"]),
            link=product["url"],
            image_url=og_image,
            access_token=PINTEREST_ACCESS_TOKEN,
            board_id=PINTEREST_BOARD_ID,
        )

    status_fb = "✅ AUTO-GEPOSTET auf Facebook" if fb_posted else "📋 FACEBOOK (Queue)"
    status_ig = "✅ AUTO-GEPOSTET auf Instagram" if ig_posted else "📋 INSTAGRAM (Queue)"
    status_pin = "✅ AUTO-GEPOSTET auf Pinterest" if pin_posted else "📋 PINTEREST (Queue)"

    await send_telegram(
        f"📘 <b>{status_fb}</b>\n"
        f"Produkt: {product['name']} — {product['price']}\n\n"
        f"{fb_post['content'][:600]}\n\n"
        f"🔗 {product['url']}"
    )
    await asyncio.sleep(3)
    await send_telegram(
        f"📸 <b>{status_ig}</b>\n"
        f"Produkt: {product['name']} — {product['price']}\n\n"
        f"{ig_post['content'][:800]}"
    )
    await asyncio.sleep(2)
    await send_telegram(
        f"📌 <b>{status_pin}</b>\n"
        f"Produkt: {product['name']} — {product['price']}\n"
        f"Title: {pin_post.get('title', '')}\n"
        f"🔗 {product['url']}"
    )

    await klaviyo_track("Meta Content Cycle", {
        "product": product["name"],
        "facebook_posted": fb_posted,
        "instagram_posted": ig_posted,
        "pinterest_posted": pin_posted,
    })
    await indexnow_ping(product["url"])
    logger.info(f"Content cycle done — FB:{fb_posted} IG:{ig_posted} PIN:{pin_posted} Product:{product['name']}")


async def scheduler():
    await asyncio.sleep(30)
    while True:
        try:
            await content_cycle()
        except Exception as e:
            err_str = str(e)
            logger.error(f"Content cycle error: {e}")
            if "credit balance" in err_str or "billing" in err_str.lower() or "402" in err_str:
                logger.warning("Anthropic credits low — skipping, retry in %ds", SCHEDULE_INTERVAL)
            else:
                await send_telegram(f"⚠️ Meta Engine Fehler: {e}")
        await asyncio.sleep(SCHEDULE_INTERVAL)


async def health_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    posted = conn.execute("SELECT COUNT(*) FROM posts WHERE status='posted'").fetchone()[0]
    conn.close()
    # Validate Facebook token with a lightweight Graph API call
    fb_token_valid = False
    if FB_ACCESS_TOKEN and FB_PAGE_ID:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}",
                    params={"fields": "id", "access_token": FB_ACCESS_TOKEN},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    data = await r.json()
                    fb_token_valid = "id" in data and "error" not in data
        except Exception:
            fb_token_valid = False
    return web.json_response({
        "status": "ok",
        "service": "meta-social-engine",
        "total_posts_queued": count,
        "auto_posted": posted,
        "facebook_connected": fb_token_valid,
        "facebook_token_set": bool(FB_ACCESS_TOKEN and FB_PAGE_ID),
        "instagram_connected": bool(IG_ACCOUNT_ID) and fb_token_valid,
        "pinterest_connected": bool(PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID),
        "schedule": f"every {SCHEDULE_INTERVAL // 60} minutes",
        "warning": None if fb_token_valid else ("Facebook token expired or invalid — refresh at developers.facebook.com" if FB_ACCESS_TOKEN else "FACEBOOK_ACCESS_TOKEN not set"),
    })


async def trigger_handler(request):
    from aiohttp import web
    asyncio.create_task(content_cycle())
    return web.json_response({"status": "triggered", "message": "Content cycle started"})


async def schedule_set_handler(request):
    from aiohttp import web
    global SCHEDULE_INTERVAL
    try:
        body = await request.json()
        minutes = int(body.get("interval_minutes", 30))
        if minutes < 5 or minutes > 1440:
            return web.json_response({"error": "interval_minutes must be 5-1440"}, status=400)
        SCHEDULE_INTERVAL = minutes * 60
        return web.json_response({"status": "ok", "interval_minutes": minutes, "interval_seconds": SCHEDULE_INTERVAL})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def create_posts_from_article(title: str, url: str, keyword: str, excerpt: str):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    fb_resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=500,
        messages=[{"role": "user", "content": f"Facebook Post auf Deutsch für Artikel:\nTitel: {title}\nKeyword: {keyword}\nExcerpt: {excerpt}\nLink: {url}\n\nFormat: 2-3 Absätze + CTA + Link + 5 Hashtags. Professionell, nicht spam."}]
    )
    fb_text = fb_resp.content[0].text
    ig_resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=400,
        messages=[{"role": "user", "content": f"Instagram Caption für Artikel: {title}\nKeyword: {keyword}\nLink im Bio: {url}\n10 Hashtags DE/EN. Max 300 Wörter."}]
    )
    ig_text = ig_resp.content[0].text
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO posts (platform, content, product_name, status, created_at) VALUES (?,?,?,?,?)",
                 ("facebook", fb_text, title[:60], "queued", now))
    conn.execute("INSERT INTO posts (platform, content, product_name, status, created_at) VALUES (?,?,?,?,?)",
                 ("instagram", ig_text, title[:60], "queued", now))
    conn.commit()
    conn.close()
    if FB_ACCESS_TOKEN and FB_PAGE_ID:
        await post_to_facebook(fb_text, FB_PAGE_ID, FB_ACCESS_TOKEN)
    if PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID:
        og_image = f"{url}/og-image.png" if not url.endswith("/") else f"{url}og-image.png"
        await post_to_pinterest(
            title=title[:100], description=fb_text[:500], link=url,
            image_url=og_image,
            access_token=PINTEREST_ACCESS_TOKEN, board_id=PINTEREST_BOARD_ID,
        )
    await send_telegram(f"📰➡️📘 <b>SEO Artikel → Facebook</b>\n<b>{title[:80]}</b>\n\n{fb_text[:500]}\n\n🔗 {url}")
    await asyncio.sleep(2)
    await send_telegram(f"📰➡️📸 <b>SEO Artikel → Instagram</b>\n<b>{title[:60]}</b>\n\n{ig_text[:600]}")


async def ingest_handler(request):
    from aiohttp import web
    try:
        data = await request.json()
        title = data.get("title", "")
        url = data.get("url", "")
        if not title or not url:
            return web.json_response({"error": "title and url required"}, status=400)
        keyword = data.get("keyword", "")
        excerpt = data.get("excerpt", "")
        asyncio.create_task(create_posts_from_article(title, url, keyword, excerpt))
        return web.json_response({"status": "accepted", "title": title})
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return web.json_response({"error": str(e)}, status=500)



async def handle_fb_auth_page(request):
    """GET /auth/facebook — Step-by-step Facebook token setup guide."""
    from aiohttp import web
    fb_app_id = os.getenv("FACEBOOK_APP_ID", "")
    html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<title>Facebook Token Setup</title>
<style>
body{{background:#111;color:#e0e0e0;font-family:monospace;padding:2rem;max-width:700px;margin:0 auto}}
h1{{color:#1877f2}}h2{{color:#4a9eff;margin-top:2rem}}
.step{{background:#1a1a2a;border-left:3px solid #1877f2;padding:1rem;margin:1rem 0;border-radius:4px}}
.url{{background:#0a0a15;padding:.5rem;border-radius:4px;word-break:break-all;color:#4af;font-size:.85rem}}
.btn{{display:inline-block;background:#1877f2;color:#fff;padding:.6rem 1.2rem;border-radius:6px;text-decoration:none;margin:.5rem 0}}
code{{background:#1a1a2a;padding:2px 6px;border-radius:3px;color:#f0c040}}
</style></head><body>
<h1>🔵 Facebook Token Setup</h1>
<p>Einmalig einrichten — danach automatische Verlängerung alle 60 Tage.</p>

<h2>Schritt 1: Graph API Explorer öffnen</h2>
<div class="step">
<a href="https://developers.facebook.com/tools/explorer" target="_blank" class="btn">→ Graph API Explorer öffnen</a>
<p>1. Wähle oben rechts deine App: <code>{{fb_app_id or 'deine App'}}</code><br>
2. Klicke "Generate Access Token"<br>
3. Wähle deine Facebook-Seite<br>
4. Permissions aktivieren: <code>pages_manage_posts</code>, <code>pages_read_engagement</code>, <code>instagram_basic</code>, <code>instagram_content_publish</code></p>
</div>

<h2>Schritt 2: Long-Lived Token erstellen</h2>
<div class="step">
<p>Kopiere den Token aus Schritt 1, dann POST an:</p>
<div class="url">POST /auth/facebook/exchange</div>
<p>Body: <code>{{"short_token": "DEIN_TOKEN_HIER", "fb_app_id": "DEINE_APP_ID", "fb_app_secret": "DEIN_APP_SECRET"}}</code></p>
<p>Oder direkt per curl:</p>
<div class="url">curl -X POST http://localhost:8091/auth/facebook/exchange -H "Content-Type: application/json" -d '{{"short_token":"EAA...","fb_app_id":"...","fb_app_secret":"..."}}' </div>
</div>

<h2>Schritt 3: Page Token holen</h2>
<div class="step">
<p>Rufe auf: <code>GET /auth/facebook/pages?token=LONG_LIVED_TOKEN</code><br>
Du bekommst alle deine Pages + Page Access Tokens zurück.</p>
</div>

<h2>Schritt 4: ENV Variablen setzen</h2>
<div class="step">
<p>In Railway → meta-social-engine → Variables:</p>
<code>FACEBOOK_ACCESS_TOKEN</code> = Page Access Token<br>
<code>FACEBOOK_PAGE_ID</code> = Page ID<br>
<code>INSTAGRAM_ACCOUNT_ID</code> = IG Account ID (aus /me/accounts)<br>
<code>FACEBOOK_APP_ID</code> = App ID<br>
<code>FACEBOOK_APP_SECRET</code> = App Secret
</div>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_fb_token_exchange(request):
    """POST /auth/facebook/exchange — exchange short for long-lived token."""
    from aiohttp import web
    try:
        body = await request.json()
        short_token = body.get("short_token", "")
        app_id = body.get("fb_app_id", os.getenv("FACEBOOK_APP_ID", ""))
        app_secret = body.get("fb_app_secret", os.getenv("FACEBOOK_APP_SECRET", ""))

        if not all([short_token, app_id, app_secret]):
            return web.json_response({"ok": False, "error": "short_token, fb_app_id, fb_app_secret required"})

        async with aiohttp.ClientSession() as s:
            url = (
                f"https://graph.facebook.com/v19.0/oauth/access_token"
                f"?grant_type=fb_exchange_token"
                f"&client_id={app_id}&client_secret={app_secret}"
                f"&fb_exchange_token={short_token}"
            )
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()

        if "access_token" in data:
            long_token = data["access_token"]
            expires_in = data.get("expires_in", 5184000)
            return web.json_response({
                "ok": True,
                "long_lived_token": long_token,
                "expires_in_days": expires_in // 86400,
                "next_step": "Use GET /auth/facebook/pages?token=LONG_TOKEN to get page tokens",
                "env_var": "Set FACEBOOK_ACCESS_TOKEN=" + long_token[:20] + "...",
            })
        return web.json_response({"ok": False, "error": data})
    except Exception as e:
        logger.error(f"FB token exchange error: {e}")
        return web.json_response({"ok": False, "error": str(e)})


async def handle_fb_pages(request):
    """GET /auth/facebook/pages?token=... — list pages and their tokens."""
    from aiohttp import web
    token = request.rel_url.query.get("token", os.getenv("FACEBOOK_ACCESS_TOKEN", ""))
    if not token:
        return web.json_response({"ok": False, "error": "token param required"})

    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"https://graph.facebook.com/v19.0/me/accounts?access_token={token}",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()

    pages = data.get("data", [])
    result = []
    for p in pages:
        result.append({
            "page_name": p.get("name"),
            "page_id": p.get("id"),
            "page_token": p.get("access_token", "")[:30] + "...",
            "page_token_full": p.get("access_token", ""),
            "env": f"FACEBOOK_PAGE_ID={p.get('id')} FACEBOOK_ACCESS_TOKEN={p.get('access_token','')[:20]}...",
        })
    return web.json_response({"ok": True, "pages": result, "count": len(result)})


async def handle_pinterest_auth(request):
    """GET /auth/pinterest — Pinterest token setup guide."""
    from aiohttp import web
    html = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Pinterest Token Setup</title>
<style>body{background:#111;color:#e0e0e0;font-family:monospace;padding:2rem;max-width:700px;margin:0 auto}
h1{color:#e60023}h2{color:#ff6b81;margin-top:2rem}
.step{background:#1a1a2a;border-left:3px solid #e60023;padding:1rem;margin:1rem 0;border-radius:4px}
.url{background:#0a0a15;padding:.5rem;border-radius:4px;word-break:break-all;color:#f96a6a}
a{color:#e60023}.btn{display:inline-block;background:#e60023;color:#fff;padding:.6rem 1.2rem;border-radius:6px;text-decoration:none}
code{background:#1a1a2a;padding:2px 6px;border-radius:3px;color:#f0c040}</style></head><body>
<h1>📌 Pinterest Token Setup</h1>
<h2>Schritt 1: App öffnen</h2>
<div class="step">
<a href="https://developers.pinterest.com/apps/1580762" target="_blank" class="btn">→ Pinterest App 1580762 öffnen</a>
<p>→ "Generate access token"<br>
→ Scopes: <code>boards:read</code>, <code>pins:read</code>, <code>pins:write</code></p>
</div>
<h2>Schritt 2: Board ID holen</h2>
<div class="step">
<div class="url">GET /auth/pinterest/boards?token=DEIN_TOKEN</div>
<p>Gibt alle Boards mit IDs zurück</p>
</div>
<h2>Schritt 3: Railway Variables setzen</h2>
<div class="step">
<code>PINTEREST_ACCESS_TOKEN</code> = dein Token<br>
<code>PINTEREST_BOARD_ID</code> = Board ID für BullPower Posts
</div>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_pinterest_boards(request):
    """GET /auth/pinterest/boards?token=... — list boards."""
    from aiohttp import web
    token = request.rel_url.query.get("token", os.getenv("PINTEREST_ACCESS_TOKEN", ""))
    if not token:
        return web.json_response({"ok": False, "error": "token param required"})
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://api.pinterest.com/v5/boards",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
    boards = data.get("items", [])
    return web.json_response({
        "ok": True,
        "boards": [{"id": b["id"], "name": b["name"]} for b in boards],
    })

async def handle_pinterest_callback(request):
    """GET /auth/pinterest/callback — receives OAuth code, exchanges for token, saves to Railway."""
    from aiohttp import web
    import base64, subprocess

    code = request.rel_url.query.get("code", "")
    error = request.rel_url.query.get("error", "")

    if error:
        return web.Response(
            content_type="text/html",
            text=f"<h2 style='color:red'>Pinterest Fehler: {error}</h2>"
        )
    if not code:
        return web.Response(
            content_type="text/html",
            text="<h2 style='color:orange'>Kein Code erhalten — bitte erneut versuchen.</h2>"
        )

    app_id = os.getenv("PINTEREST_APP_ID", "")
    app_secret = os.getenv("PINTEREST_APP_SECRET", "")
    redirect_uri = "https://meta-social-engine-production.up.railway.app/auth/pinterest/callback"

    if not app_id or not app_secret:
        return web.json_response({"ok": False, "error": "PINTEREST_APP_ID or PINTEREST_APP_SECRET not set"})

    creds = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

    async with aiohttp.ClientSession() as s:
        r = await s.post(
            "https://api.pinterest.com/v5/oauth/token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        token_data = await r.json()

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 0)
    scope = token_data.get("scope", "")

    if not access_token:
        return web.json_response({"ok": False, "error": token_data})

    # Get user info to confirm token works
    async with aiohttp.ClientSession() as s:
        ur = await s.get(
            "https://api.pinterest.com/v5/user_account",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_data = await ur.json()
    username = user_data.get("username", "?")

    # Get first board ID
    board_id = ""
    async with aiohttp.ClientSession() as s:
        br = await s.get(
            "https://api.pinterest.com/v5/boards",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        board_data = await br.json()
    boards = board_data.get("items", [])
    if boards:
        board_id = boards[0]["id"]

    # Save to Railway env vars via railway CLI (fire-and-forget)
    vars_to_set = f"PINTEREST_ACCESS_TOKEN={access_token}"
    if refresh_token:
        vars_to_set += f" PINTEREST_REFRESH_TOKEN={refresh_token}"
    if board_id:
        vars_to_set += f" PINTEREST_BOARD_ID={board_id}"

    try:
        subprocess.Popen(
            f"railway variables set {vars_to_set}",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

    days = round(expires_in / 86400) if expires_in else "?"
    html = f"""<!DOCTYPE html>
<html><body style="background:#0a0a0f;color:#f0f0ff;font-family:sans-serif;padding:2rem;max-width:600px;margin:0 auto">
<div style="background:#13131f;border:1px solid rgba(229,78,78,.4);border-radius:16px;padding:2rem">
<h1 style="color:#e60023">📌 Pinterest verbunden!</h1>
<p>Account: <strong>@{username}</strong></p>
<p>Token läuft ab in: <strong>~{days} Tage</strong></p>
<p>Scopes: <code style="color:#f0c040">{scope}</code></p>
{"<p>Board: <strong>" + (boards[0]['name'] if boards else "—") + "</strong> (" + board_id + ")</p>" if board_id else ""}
<p style="color:#a3e635;margin-top:1rem">✅ Token + Board ID wurden automatisch in Railway gesetzt.</p>
<p style="color:#94a3b8;font-size:.85rem">Du kannst dieses Fenster schließen.</p>
</div></body></html>"""

    logger.info("Pinterest OAuth complete: @%s board=%s", username, board_id)
    return web.Response(content_type="text/html", text=html)


async def seo_products_handler(request):
    from aiohttp import web
    keyword = request.rel_url.query.get("keyword", "facebook marketing automatisierung")
    source = request.rel_url.query.get("source", "all")
    products = await seo_get_products(keyword, source)
    return web.json_response({"keyword": keyword, "products": products, "seo_engine": _SEO_ENGINE})


async def posts_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT platform, product_name, status, created_at FROM posts ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return web.json_response([
        {"platform": r[0], "product": r[1], "status": r[2], "created_at": r[3]} for r in rows
    ])


async def stats_handler(request):
    from aiohttp import web
    trends = await fetch_google_trends()
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    by_platform = {r[0]: r[1] for r in conn.execute(
        "SELECT platform, COUNT(*) FROM posts GROUP BY platform").fetchall()}
    posted = conn.execute("SELECT COUNT(*) FROM posts WHERE status='posted'").fetchone()[0]
    conn.close()
    return web.json_response({
        "version": "2.0-TURBO",
        "total_posts": total,
        "auto_posted": posted,
        "by_platform": by_platform,
        "trending": trends[:5],
        "schedule_interval_min": SCHEDULE_INTERVAL // 60,
    })


async def indexnow_key_handler(request):
    from aiohttp import web
    return web.Response(text=INDEXNOW_KEY, content_type="text/plain")


async def main():
    from aiohttp import web
    init_db()

    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_post("/api/trigger", trigger_handler)
    app.router.add_post("/api/schedule/set", schedule_set_handler)
    app.router.add_get("/api/posts", posts_handler)
    app.router.add_post("/api/ingest", ingest_handler)
    app.router.add_get("/api/seo/products", seo_products_handler)
    app.router.add_get("/auth/facebook",           handle_fb_auth_page)
    app.router.add_post("/auth/facebook/exchange", handle_fb_token_exchange)
    app.router.add_get("/auth/facebook/pages",     handle_fb_pages)
    app.router.add_get("/auth/pinterest",          handle_pinterest_auth)
    app.router.add_get("/auth/pinterest/callback", handle_pinterest_callback)
    app.router.add_get("/auth/pinterest/boards",   handle_pinterest_boards)
    app.router.add_get("/stats",                   stats_handler)
    app.router.add_get(f"/{INDEXNOW_KEY}.txt",     indexnow_key_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Meta Social Engine running on port {PORT}")

    fb_status = "✅ verbunden" if (FB_ACCESS_TOKEN and FB_PAGE_ID) else "⚠️ Token fehlt → Queue"
    ig_status = "✅ verbunden" if IG_ACCOUNT_ID else "⚠️ Account fehlt → Queue"
    pin_status = "✅ verbunden" if (PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID) else "⚠️ Token fehlt → Queue"

    await send_telegram(
        f"🚀 <b>Meta Social Engine v2 gestartet!</b>\n"
        f"📘 Facebook: {fb_status}\n"
        f"📸 Instagram: {ig_status}\n"
        f"📌 Pinterest: {pin_status}\n"
        f"⏰ Posting alle {SCHEDULE_INTERVAL // 60} Minuten\n"
        f"Erster Content in 30 Sekunden..."
    )

    asyncio.create_task(scheduler())
    asyncio.create_task(_seo_broadcast_loop())
    await asyncio.Future()


async def _seo_broadcast_loop():
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.post('https://seo-traffic-engine-production.up.railway.app/api/generate',
                                  json={'topic': 'E-Commerce Automation und KI-Tools', 'auto_post': True}) as r:
                    if r.status == 200:
                        logger.info('SEO Bridge: Artikel generiert und gebroadcastet')
                    else:
                        logger.warning(f'SEO Bridge: HTTP {r.status}')
        except Exception as e:
            logger.error(f'SEO Bridge Fehler: {e}')
        await asyncio.sleep(6 * 3600)


if __name__ == "__main__":
    asyncio.run(main())
