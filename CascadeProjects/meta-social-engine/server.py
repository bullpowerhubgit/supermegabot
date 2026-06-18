#!/usr/bin/env python3
"""Meta Social Engine — Autonomous Facebook, Instagram & Pinterest poster"""
import asyncio, aiohttp, os, json, logging, sqlite3, random
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


async def generate_meta_post(product: dict, post_type: str = "facebook") -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if post_type == "instagram":
        prompt = f"""Erstelle einen Instagram-Post auf Deutsch für: {product['name']}
Preis: {product['price']}
Tagline: {product['tagline']}

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
URL: {product['url']}

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

    logger.info(f"Content cycle done — FB:{fb_posted} IG:{ig_posted} PIN:{pin_posted} Product:{product['name']}")


async def scheduler():
    await asyncio.sleep(30)
    while True:
        try:
            await content_cycle()
        except Exception as e:
            logger.error(f"Content cycle error: {e}")
            await send_telegram(f"⚠️ Meta Engine Fehler: {e}")
        await asyncio.sleep(4 * 3600)


async def health_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    posted = conn.execute("SELECT COUNT(*) FROM posts WHERE status='posted'").fetchone()[0]
    conn.close()
    return web.json_response({
        "status": "ok",
        "service": "meta-social-engine",
        "total_posts_queued": count,
        "auto_posted": posted,
        "facebook_connected": bool(FB_ACCESS_TOKEN and FB_PAGE_ID),
        "instagram_connected": bool(IG_ACCOUNT_ID and FB_ACCESS_TOKEN),
        "pinterest_connected": bool(PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID),
        "schedule": "every 4 hours",
    })


async def trigger_handler(request):
    from aiohttp import web
    asyncio.create_task(content_cycle())
    return web.json_response({"status": "triggered", "message": "Content cycle started"})


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


async def main():
    from aiohttp import web
    init_db()

    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_post("/api/trigger", trigger_handler)
    app.router.add_get("/api/posts", posts_handler)
    app.router.add_post("/api/ingest", ingest_handler)

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
        f"⏰ Posting alle 4 Stunden\n"
        f"Erster Content in 30 Sekunden..."
    )

    asyncio.create_task(scheduler())
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
