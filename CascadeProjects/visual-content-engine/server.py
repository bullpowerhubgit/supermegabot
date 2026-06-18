#!/usr/bin/env python3
"""Visual Content Engine — TikTok + Pinterest + Discord autonomous poster"""
import asyncio, aiohttp, os, json, logging, sqlite3
from datetime import datetime
import anthropic

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", os.getenv("PINTEREST_API_KEY", ""))
PINTEREST_AD_ACCOUNT_ID = os.getenv("PINTEREST_AD_ACCOUNT_ID", "549769611978")
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
TIKTOK_APP_KEY = os.getenv("TIKTOK_APP_KEY", "")
TIKTOK_APP_SECRET = os.getenv("TIKTOK_APP_SECRET", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", os.getenv("TIKTOK_RESEARCH_TOKEN", ""))
PORT        = int(os.getenv("PORT", 8092))
KV_API_KEY  = os.getenv("KLAVIYO_API_KEY", "")
MC_API_KEY  = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER   = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
MC_LIST_ID  = os.getenv("MAILCHIMP_LIST_ID", "")

PRODUCTS = [
    {"name": "Shopify Acquisition Engine", "url": "https://shopify-acquisition-engine-production.up.railway.app", "price": "49€/mo", "niche": "E-Commerce Automatisierung"},
    {"name": "SEO Turbo Tools", "url": "https://seo-turbo-tools-production.up.railway.app", "price": "29€/mo", "niche": "SEO & Online Marketing"},
    {"name": "iComeAuto SaaS", "url": "https://icomeauto-saas-production.up.railway.app", "price": "29€/mo", "niche": "Passives Einkommen"},
    {"name": "SuperMegaBot", "url": "https://dudirudibot-mega-production.up.railway.app", "price": "49€/mo", "niche": "KI Business Automatisierung"},
]

DB_PATH = "/tmp/visual_content.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        content TEXT,
        product_name TEXT,
        status TEXT DEFAULT 'queued',
        created_at TEXT,
        posted_at TEXT
    )""")
    conn.commit()
    conn.close()


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


async def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4096], "parse_mode": "HTML"})
    except Exception as e:
        logger.error(f"Telegram error: {e}")


async def generate_tiktok_script(product: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        messages=[{"role": "user", "content": f"""Erstelle ein virales TikTok-Video-Script (45-60 Sekunden gesprochen) auf Deutsch für: {product['name']}
Nische: {product['niche']} | Preis: {product['price']}

FORMAT:
🎬 HOOK (0-3 Sek): Schockierender Einstieg der stoppt
📖 PROBLEM (3-10 Sek): Das Problem das JEDER kennt
💡 LÖSUNG (10-30 Sek): Wie {product['name']} das löst — 3 konkrete Punkte
🎯 BEWEIS (30-45 Sek): Eine konkrete Zahl oder Ergebnis
🚀 CTA (45-60 Sek): "Link in Bio" + Text-Overlay

[TECHNISCH]
Empfohlene Sounds: (2 aktuelle TikTok Trends)
Hashtags: #automatisierung #onlinebusiness #ki #shopify #passiveseinkommen #geldverdienen #sidehustle #ecommerce #seo #deutschland"""}]
    )
    return resp.content[0].text


async def generate_pinterest_content(product: dict) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": f"""Pinterest Pin für: {product['name']} ({product['price']}) — {product['url']}

Exaktes Format (keine anderen Zeilen):
TITEL: [max 100 Zeichen, keyword-optimiert, Deutsch]
BESCHREIBUNG: [200-500 Zeichen, natürliche Keywords, CTA am Ende, Deutsch]
KEYWORDS: [20 Keywords komma-separiert, Deutsch und Englisch gemischt]
BOARD: [Empfohlener Board-Name]
BILDKONZEPT: [Kurze Beschreibung für Canva: Farbe, Text-Overlay, Stil]"""}]
    )
    text = resp.content[0].text
    result = {"raw": text, "url": product["url"], "product": product["name"]}
    for line in text.split("\n"):
        if line.startswith("TITEL:"): result["title"] = line[6:].strip()
        elif line.startswith("BESCHREIBUNG:"): result["description"] = line[13:].strip()
        elif line.startswith("KEYWORDS:"): result["keywords"] = line[9:].strip()
        elif line.startswith("BOARD:"): result["board"] = line[6:].strip()
    return result


async def generate_discord_post(product: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": f"""Discord Community Post für #{product['niche'].lower().replace(' ', '-')} Channel.
Produkt: {product['name']} — {product['price']} — {product['url']}

STIL: Als Community-Mitglied, hilfreich, NICHT werbend. Deutsch.
- 2-3 Sätze persönliche Erfahrung/Beobachtung
- 3 Bullet-Points mit Emojis was es kann
- Link natürlich eingebaut (kein "Klicke hier")
- Offene Frage ans Community
- MAX 250 Wörter, kein Spam-Ton, keine Ausrufezeichen-Ketten"""}]
    )
    return resp.content[0].text


async def post_to_pinterest_api(pin_data: dict) -> bool:
    """Auto-post via Pinterest API v5 if token + board available."""
    if not PINTEREST_ACCESS_TOKEN or not PINTEREST_BOARD_ID:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            payload = {
                "board_id": PINTEREST_BOARD_ID,
                "title": pin_data.get("title", pin_data["product"])[:100],
                "description": pin_data.get("description", "")[:500],
                "link": pin_data["url"],
                "media_source": {
                    "source_type": "image_url",
                    "url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=800"
                }
            }
            resp = await s.post(
                "https://api.pinterest.com/v5/pins",
                headers={"Authorization": f"Bearer {PINTEREST_ACCESS_TOKEN}", "Content-Type": "application/json"},
                json=payload
            )
            data = await resp.json()
            if "id" in data:
                logger.info(f"Pinterest pin created: {data['id']}")
                return True
            logger.warning(f"Pinterest API response: {data}")
            return False
    except Exception as e:
        logger.error(f"Pinterest post error: {e}")
        return False


async def post_to_discord_webhook(content: str) -> bool:
    """Auto-post via Discord webhook if configured."""
    if not DISCORD_WEBHOOK:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            resp = await s.post(DISCORD_WEBHOOK, json={"content": content[:2000]})
            return resp.status in (200, 204)
    except Exception as e:
        logger.error(f"Discord webhook error: {e}")
        return False


async def content_cycle():
    import random
    product = random.choice(PRODUCTS)
    now = datetime.now().isoformat()
    logger.info(f"Content cycle start — product: {product['name']}")

    tiktok = await generate_tiktok_script(product)
    pinterest = await generate_pinterest_content(product)
    discord = await generate_discord_post(product)

    conn = sqlite3.connect(DB_PATH)
    for platform, content in [("tiktok", tiktok), ("pinterest", pinterest["raw"]), ("discord", discord)]:
        conn.execute(
            "INSERT INTO content (platform, content, product_name, created_at) VALUES (?,?,?,?)",
            (platform, content, product["name"], now)
        )
    conn.commit()
    conn.close()

    pinterest_posted = await post_to_pinterest_api(pinterest)
    discord_posted = await post_to_discord_webhook(discord)

    await send_telegram(
        f"🎬 <b>TIKTOK SCRIPT BEREIT</b>\n"
        f"📦 Produkt: {product['name']}\n\n"
        f"{tiktok[:900]}\n\n"
        f"<i>➡️ Copy & poste auf TikTok @dein-account</i>"
    )
    await asyncio.sleep(3)
    await send_telegram(
        f"📌 <b>PINTEREST PIN {'✅ AUTO-POSTED' if pinterest_posted else '📋 BEREIT ZUM POSTEN'}</b>\n"
        f"📦 Produkt: {product['name']}\n\n"
        f"{pinterest['raw'][:700]}"
        + (f"\n\n<i>➡️ Poste auf Pinterest mit Board: {pinterest.get('board','Automatisierung')}</i>" if not pinterest_posted else "")
    )
    await asyncio.sleep(3)
    await send_telegram(
        f"💬 <b>DISCORD POST {'✅ AUTO-POSTED' if discord_posted else '📋 BEREIT ZUM POSTEN'}</b>\n\n"
        f"{discord[:700]}"
        + ("\n\n<i>➡️ Poste in relevante Discord Server (Shopify, Online Business, KI)</i>" if not discord_posted else "")
    )

    logger.info(f"Cycle done — Pinterest:{pinterest_posted} Discord:{discord_posted}")
    await klaviyo_track("Visual Content Cycle", {
        "product": product["name"],
        "pinterest_posted": pinterest_posted,
        "discord_posted": discord_posted,
    })


async def scheduler():
    await asyncio.sleep(30)
    await content_cycle()
    while True:
        await asyncio.sleep(5 * 3600)
        try:
            await content_cycle()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            await send_telegram(f"⚠️ Visual Engine Error: {e}")


async def health_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
    by_platform = {
        row[0]: row[1]
        for row in conn.execute("SELECT platform, COUNT(*) FROM content GROUP BY platform")
    }
    conn.close()
    return web.json_response({
        "status": "ok",
        "service": "visual-content-engine",
        "version": "1.0.0",
        "total_content": total,
        "by_platform": by_platform,
        "integrations": {
            "pinterest_api": bool(PINTEREST_ACCESS_TOKEN),
            "discord_webhook": bool(DISCORD_WEBHOOK),
            "tiktok_app_key": bool(TIKTOK_APP_KEY),
            "tiktok_manual_queue": True,
        }
    })


async def trigger_handler(request):
    from aiohttp import web
    asyncio.create_task(content_cycle())
    return web.json_response({"status": "triggered", "message": "Content cycle started"})


async def create_visual_from_article(title: str, url: str, keyword: str, excerpt: str):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tiktok_resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=500,
        messages=[{"role": "user", "content": f"TikTok Video Script (45 Sek) auf Deutsch für Artikel:\n\"{title}\"\nKeyword: {keyword}\nExcerpt: {excerpt[:200]}\n\nFormat: Hook(3s)→Problem(10s)→Lösung(25s)→CTA: {url}\nEnergisch, viral, Deutsch."}]
    )
    tiktok_text = tiktok_resp.content[0].text
    pin_resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=300,
        messages=[{"role": "user", "content": f"Pinterest Pin für Artikel: {title}\nLink: {url}\nBeschreibung 150 Zeichen + 10 Keywords auf Deutsch."}]
    )
    pin_text = pin_resp.content[0].text
    discord_text = f"📖 **{title}**\n\n{excerpt[:300]}\n\n🔗 {url}\n\n#{keyword.replace(' ','').title()}"
    discord_posted = await post_to_discord_webhook(discord_text)
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    for platform, content in [("tiktok", tiktok_text), ("pinterest", pin_text), ("discord", discord_text)]:
        conn.execute("INSERT INTO content (platform, content, product_name, created_at) VALUES (?,?,?,?)",
                     (platform, content, title[:60], now))
    conn.commit()
    conn.close()
    if PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID:
        await post_to_pinterest_api({"title": title[:100], "description": pin_text[:500], "url": url, "product": title})
    await send_telegram(f"📰➡️🎬 <b>SEO Artikel → TikTok Script</b>\n<b>{title[:60]}</b>\n\n{tiktok_text[:700]}")
    await asyncio.sleep(2)
    await send_telegram(f"📰➡️📌 <b>SEO Artikel → Pinterest {'✅ AUTO-POSTED' if PINTEREST_ACCESS_TOKEN else '📋 BEREIT'}</b>\n{title[:60]}\n\n{pin_text[:400]}\n🔗 {url}")
    if discord_posted:
        logger.info(f"Discord auto-posted article: {title[:50]}")


async def ingest_handler(request):
    from aiohttp import web
    try:
        data = await request.json()
        title = data.get("title", "")
        url = data.get("url", "")
        if not title or not url:
            return web.json_response({"error": "title and url required"}, status=400)
        asyncio.create_task(create_visual_from_article(title, url, data.get("keyword", ""), data.get("excerpt", "")))
        return web.json_response({"status": "accepted", "title": title})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def content_list_handler(request):
    from aiohttp import web
    platform = request.rel_url.query.get("platform", "")
    conn = sqlite3.connect(DB_PATH)
    if platform:
        rows = conn.execute(
            "SELECT id, platform, product_name, status, created_at FROM content WHERE platform=? ORDER BY id DESC LIMIT 20",
            (platform,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, platform, product_name, status, created_at FROM content ORDER BY id DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return web.json_response([
        {"id": r[0], "platform": r[1], "product": r[2], "status": r[3], "created_at": r[4]}
        for r in rows
    ])


async def main():
    from aiohttp import web
    init_db()
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_post("/api/trigger", trigger_handler)
    app.router.add_get("/api/content", content_list_handler)
    app.router.add_post("/api/ingest", ingest_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Visual Content Engine on port {PORT}")

    await send_telegram(
        "🎨 <b>Visual Content Engine LIVE!</b>\n\n"
        "📊 Plattformen:\n"
        f"🎬 TikTok Scripts — {'✅ Generierung aktiv' if ANTHROPIC_API_KEY else '❌ ANTHROPIC_API_KEY fehlt'}\n"
        f"📌 Pinterest — {'✅ API Auto-Post' if PINTEREST_ACCESS_TOKEN else '📋 Queue via Telegram'}\n"
        f"💬 Discord — {'✅ Webhook Auto-Post' if DISCORD_WEBHOOK else '📋 Queue via Telegram'}\n\n"
        "⏱️ Erster Content in 30 Sekunden..."
    )

    asyncio.create_task(scheduler())
    asyncio.create_task(_seo_broadcast_loop())
    await asyncio.Future()


async def _seo_broadcast_loop():
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.post('https://seo-traffic-engine-production.up.railway.app/api/generate',
                                  json={'topic': 'TikTok Pinterest Content Automatisierung', 'auto_post': True}) as r:
                    if r.status == 200:
                        logger.info('SEO Bridge: Artikel generiert und gebroadcastet')
                    else:
                        logger.warning(f'SEO Bridge: HTTP {r.status}')
        except Exception as e:
            logger.error(f'SEO Bridge Fehler: {e}')
        await asyncio.sleep(6 * 3600)


if __name__ == "__main__":
    asyncio.run(main())
