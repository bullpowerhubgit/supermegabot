#!/usr/bin/env python3
"""Freelance Gig Engine — MAXIMUM TUNING v2.0
Fiverr + Upwork + Google Trends + IndexNow + LSI keywords + turbo scheduler"""
import asyncio, aiohttp, os, logging, sqlite3, random, uuid, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote
import anthropic

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
PORT              = int(os.getenv("PORT", 8093))
APP_URL           = os.getenv("APP_URL", "https://freelance-gig-engine-production.up.railway.app")
KV_API_KEY        = os.getenv("KLAVIYO_API_KEY", "")
MC_API_KEY        = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER         = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
MC_LIST_ID        = os.getenv("MAILCHIMP_LIST_ID", "")
INDEXNOW_KEY      = os.getenv("INDEXNOW_KEY", str(uuid.uuid5(uuid.NAMESPACE_URL, APP_URL)).replace("-",""))
_trending_cache: list[str] = []
_last_trends_fetch: float = 0

# ── SEO Traffic Engine Bridge ──────────────────────────────────────────────
_SEO_ENGINE = os.getenv("SEO_ENGINE_URL", "https://seo-traffic-engine-production.up.railway.app")
_AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bullpower-21")
_EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")


async def fetch_google_trends(geo: str = "DE") -> list[str]:
    global _trending_cache, _last_trends_fetch
    if time.time() - _last_trends_fetch < 7200:
        return _trending_cache
    url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
    keywords = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=12),
                             headers={"User-Agent": "Mozilla/5.0 (compatible; GigBot/2.0)"}) as r:
                if r.status == 200:
                    root = ET.fromstring(await r.text())
                    for item in root.findall(".//item"):
                        el = item.find("title")
                        if el is not None and el.text:
                            kw = el.text.strip().lower()
                            if any(t in kw for t in ["freelance","tech","ki","ai","geld","online","digital","seo","tool","software","entwickler","python","shopify"]):
                                keywords.append(kw)
    except Exception as e:
        logger.warning(f"Google Trends: {e}")
    if keywords:
        _trending_cache = keywords[:10]
        _last_trends_fetch = time.time()
    return _trending_cache


async def generate_lsi_keywords(keyword: str) -> list[str]:
    """Generate LSI keywords to boost gig visibility in Fiverr/Upwork search."""
    if not ANTHROPIC_API_KEY:
        return []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content":
                f"Give 10 LSI keywords (related search terms) for freelance service: '{keyword}'\nOnly keywords, one per line, no numbering."}]
        )
        return [line.strip() for line in msg.content[0].text.strip().split("\n") if line.strip()][:10]
    except Exception:
        return []


async def indexnow_ping(urls: list[str]) -> bool:
    payload = {
        "host": APP_URL.replace("https://","").replace("http://",""),
        "key": INDEXNOW_KEY,
        "keyLocation": f"{APP_URL}/{INDEXNOW_KEY}.txt",
        "urlList": urls[:50],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.indexnow.org/indexnow", json=payload,
                              headers={"Content-Type": "application/json; charset=utf-8"},
                              timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status in (200, 202)
    except Exception as e:
        logger.warning(f"IndexNow: {e}")
        return False


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


async def seo_push_keyword(keyword: str, url: str = "") -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{_SEO_ENGINE}/api/trigger/articles", json={"keyword": keyword}, timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status == 200
    except Exception:
        return False
# ── End SEO Bridge ──────────────────────────────────────────────────────────

SERVICES = [
    {
        "title": "Shopify Store Vollautomatisierung mit KI",
        "fiverr_category": "Programming & Tech > Web Programming",
        "upwork_category": "Web, Mobile & Software Dev > Ecommerce Development",
        "price_basic": 150, "price_standard": 350, "price_premium": 800,
        "delivery_days": [3, 7, 14],
        "skills": ["Shopify", "Python", "AI/ML", "Automation", "REST API"],
        "demo_url": "https://shopify-acquisition-engine-production.up.railway.app"
    },
    {
        "title": "SEO Audit & KI-optimierte Meta-Descriptions fuer deinen Shop",
        "fiverr_category": "Digital Marketing > SEO",
        "upwork_category": "Sales & Marketing > SEO - Search Engine Optimization",
        "price_basic": 50, "price_standard": 150, "price_premium": 400,
        "delivery_days": [1, 3, 7],
        "skills": ["SEO", "Content Writing", "Python", "Google Analytics"],
        "demo_url": "https://seo-turbo-tools-production.up.railway.app"
    },
    {
        "title": "Custom Telegram Bot mit KI und Stripe Payment",
        "fiverr_category": "Programming & Tech > Web Programming",
        "upwork_category": "Web, Mobile & Software Dev > Scripts & Utilities",
        "price_basic": 200, "price_standard": 500, "price_premium": 1200,
        "delivery_days": [5, 10, 21],
        "skills": ["Python", "Telegram API", "Stripe", "AI/ML", "aiohttp"],
        "demo_url": "https://supermegabot-production.up.railway.app"
    },
    {
        "title": "E-Commerce KI-Automatisierung: Produkt-Research, Pricing & Import",
        "fiverr_category": "Programming & Tech > Web Programming",
        "upwork_category": "Web, Mobile & Software Dev > Ecommerce Development",
        "price_basic": 100, "price_standard": 300, "price_premium": 700,
        "delivery_days": [3, 7, 14],
        "skills": ["Python", "Shopify API", "OpenAI", "Automation", "Scraping"],
        "demo_url": "https://shopify-acquisition-engine-production.up.railway.app"
    },
]

UPWORK_KEYWORDS = [
    "shopify automation python",
    "shopify app developer",
    "e-commerce automation ai",
    "telegram bot python stripe",
    "seo automation tool",
    "shopify api integration",
    "python automation freelancer",
    "ai ecommerce developer",
    "shopify product import automation",
    "custom bot development telegram",
]

DB_PATH = "/tmp/freelance_engine.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS gigs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT, service_title TEXT, content TEXT,
        content_type TEXT, created_at TEXT, sent_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT, job_title TEXT, proposal_text TEXT,
        bid_amount INTEGER, created_at TEXT
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
    async with aiohttp.ClientSession() as s:
        try:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4096], "parse_mode": "HTML"})
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")


async def generate_fiverr_gig(service: dict, lsi: list[str] = None, trending_topic: str = "") -> str:
    lsi_str = ", ".join(lsi[:8]) if lsi else ""
    trend_line = f"Trending topic to weave in: {trending_topic}\n" if trending_topic else ""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": f"""Create an optimized Fiverr gig description in ENGLISH that ranks #1 in Fiverr search:

SERVICE: {service['title']}
CATEGORY: {service['fiverr_category']}
LSI KEYWORDS TO INCLUDE NATURALLY: {lsi_str}
{trend_line}
BASIC: ${service['price_basic']} / {service['delivery_days'][0]} days
STANDARD: ${service['price_standard']} / {service['delivery_days'][1]} days
PREMIUM: ${service['price_premium']} / {service['delivery_days'][2]} days
DEMO: {service['demo_url']}

FORMAT:
## GIG TITLE (max 80 chars, keyword-rich):
[title]

## GIG DESCRIPTION:
[3-4 paragraphs: hook, what you get, why me, CTA]

## PACKAGE NAMES:
Basic: [catchy name]
Standard: [catchy name]
Premium: [catchy name]

## BASIC PACKAGE INCLUDES:
- [3 bullet points]

## STANDARD PACKAGE INCLUDES:
- [5 bullet points]

## PREMIUM PACKAGE INCLUDES:
- [7 bullet points]

## FAQ (3 questions):
Q: [question]
A: [answer]

## SEARCH TAGS (5 tags):
[tag1, tag2, tag3, tag4, tag5]

Tone: Professional, results-oriented, trustworthy."""}]
    )
    return resp.content[0].text


async def generate_upwork_proposal(service: dict, job_title: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": f"""Write a compelling Upwork proposal in ENGLISH:

JOB: {job_title}
MY SERVICE: {service['title']}
SKILLS: {', '.join(service['skills'])}
BID: ${service['price_standard']}
DEMO: {service['demo_url']}

FORMAT (Upwork best practice — MAX 200 words):
[HOOK - 1-2 sentences: directly address the job, show you read it]

[PROBLEM UNDERSTOOD - 2-3 sentences: what the client needs]

[MY SOLUTION - 3-4 sentences: how I solve it, concrete technologies]

[PROOF - 1-2 sentences: live demo + prior experience]

[NEXT STEP - 1 sentence: invite to chat]

No spam. No "I am expert" cliches."""}]
    )
    return resp.content[0].text


async def content_cycle():
    service = random.choice(SERVICES)
    now = datetime.now().isoformat()
    logger.info(f"Content cycle — service: {service['title']}")

    # Trending + LSI enrichment in parallel
    trending = await fetch_google_trends("DE")
    trending_topic = random.choice(trending) if trending else ""
    lsi = await generate_lsi_keywords(service["title"])

    fiverr_gig = await generate_fiverr_gig(service, lsi, trending_topic)

    job1 = random.choice(UPWORK_KEYWORDS)
    job2 = random.choice([k for k in UPWORK_KEYWORDS if k != job1])
    svc2 = random.choice([s for s in SERVICES if s != service])
    proposal1 = await generate_upwork_proposal(service, job1)
    proposal2 = await generate_upwork_proposal(svc2, job2)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO gigs (platform, service_title, content, content_type, created_at) VALUES (?,?,?,?,?)",
        ("fiverr", service["title"], fiverr_gig, "gig_description", now)
    )
    conn.execute(
        "INSERT INTO proposals (platform, job_title, proposal_text, bid_amount, created_at) VALUES (?,?,?,?,?)",
        ("upwork", job1, proposal1, service["price_standard"], now)
    )
    conn.execute(
        "INSERT INTO proposals (platform, job_title, proposal_text, bid_amount, created_at) VALUES (?,?,?,?,?)",
        ("upwork", job2, proposal2, svc2["price_standard"], now)
    )
    conn.commit()
    conn.close()

    await send_telegram(
        f"<b>FIVERR GIG — Optimiert &amp; Bereit!</b>\n"
        f"Service: <b>{service['title'][:60]}</b>\n"
        f"Basic ${service['price_basic']} | Standard ${service['price_standard']} | Premium ${service['price_premium']}\n"
        f"Demo: {service['demo_url']}\n\n"
        f"{fiverr_gig[:1500]}\n\n"
        f"Kopiere und poste auf fiverr.com/selling"
    )

    await asyncio.sleep(5)

    await send_telegram(
        f"<b>UPWORK PROPOSALS — 2x bereit!</b>\n\n"
        f"<b>Proposal 1</b> — Job: '{job1}'\n"
        f"Bid: ${service['price_standard']}\n\n"
        f"{proposal1[:900]}\n\n"
        f"---\n\n"
        f"<b>Proposal 2</b> — Job: '{job2}'\n"
        f"Bid: ${svc2['price_standard']}\n\n"
        f"{proposal2[:900]}\n\n"
        f"Suche diese Jobs auf upwork.com und sende die Proposals!"
    )

    # IndexNow ping for demo URLs
    await indexnow_ping([s["demo_url"] for s in SERVICES])

    logger.info("Content cycle done.")
    await klaviyo_track("Freelance Gig Cycle", {
        "gigs": 2, "proposals": 2,
        "lsi_keywords": len(lsi),
        "trending_topic": trending_topic,
        "service": service["title"],
    })


async def scheduler():
    await asyncio.sleep(90)
    await fetch_google_trends("DE")
    last_trends = time.time()
    while True:
        try:
            await content_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        await asyncio.sleep(6 * 3600)  # Every 6h (was 12h)
        if time.time() - last_trends >= 2 * 3600:
            await fetch_google_trends("DE")
            last_trends = time.time()


async def health_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    gigs = conn.execute("SELECT COUNT(*) FROM gigs").fetchone()[0]
    props = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
    conn.close()
    return web.json_response({
        "status": "ok",
        "service": "freelance-gig-engine",
        "version": "2.0-TURBO",
        "gigs_generated": gigs,
        "proposals_generated": props,
        "trending_topics": _trending_cache[:5],
        "indexnow_key": INDEXNOW_KEY[:8] + "...",
        "platforms": ["fiverr", "upwork"],
        "features": ["google-trends", "indexnow", "lsi-keywords", "klaviyo"],
    })


async def stats_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    gigs = conn.execute("SELECT COUNT(*) FROM gigs").fetchone()[0]
    props = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
    recent_gigs = conn.execute("SELECT platform, service_title, created_at FROM gigs ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return web.json_response({
        "gigs_total": gigs, "proposals_total": props,
        "recent_gigs": [{"platform": r[0], "service": r[1], "created_at": r[2]} for r in recent_gigs],
        "trending_topics": _trending_cache,
        "last_trends_fetch": datetime.fromtimestamp(_last_trends_fetch).isoformat() if _last_trends_fetch else None,
    })


async def trigger_handler(request):
    from aiohttp import web
    asyncio.create_task(content_cycle())
    return web.json_response({"status": "triggered", "message": "Generating Fiverr gig + 2 Upwork proposals..."})


async def ingest_handler(request):
    from aiohttp import web
    try:
        data = await request.json()
        title = data.get("title", "")
        url = data.get("url", "")
        keyword = data.get("keyword", "")
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        asyncio.create_task(generate_proposal_from_article(title, url, keyword))
        return web.json_response({"status": "accepted", "title": title})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def generate_proposal_from_article(title: str, url: str, keyword: str):
    service = random.choice(SERVICES)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=500,
        messages=[{"role": "user", "content": f"""Write an Upwork proposal in ENGLISH based on this article topic:
Article: "{title}"
Keyword: {keyword}
My service: {service['title']}
Demo: {service['demo_url']} and {url}
Bid: ${service['price_standard']}

MAX 150 words. Hook → Problem → Solution → Proof → CTA. No clichés."""}]
    )
    proposal = resp.content[0].text
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO proposals (platform, job_title, proposal_text, bid_amount, created_at) VALUES (?,?,?,?,?)",
                 ("upwork", f"Article-based: {title[:60]}", proposal, service["price_standard"], datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await send_telegram(
        f"📰➡️💼 <b>SEO Artikel → Upwork Proposal</b>\n"
        f"Artikel: <b>{title[:60]}</b>\n"
        f"Service: {service['title'][:50]}\n"
        f"Bid: ${service['price_standard']}\n\n"
        f"{proposal[:800]}\n\n"
        f"➡️ Suche ähnliche Jobs auf upwork.com"
    )


async def seo_products_handler(request):
    from aiohttp import web
    keyword = request.rel_url.query.get("keyword", "fiverr gigs erstellen")
    source = request.rel_url.query.get("source", "all")
    products = await seo_get_products(keyword, source)
    return web.json_response({"keyword": keyword, "products": products, "seo_engine": _SEO_ENGINE})


async def gigs_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    gigs = conn.execute(
        "SELECT platform, service_title, created_at FROM gigs ORDER BY id DESC LIMIT 10"
    ).fetchall()
    props = conn.execute(
        "SELECT platform, job_title, bid_amount, created_at FROM proposals ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return web.json_response({
        "gigs": [{"platform": r[0], "service": r[1], "created_at": r[2]} for r in gigs],
        "proposals": [{"platform": r[0], "job": r[1], "bid": r[2], "created_at": r[3]} for r in props]
    })


async def main():
    from aiohttp import web
    init_db()
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/stats", stats_handler)
    app.router.add_post("/api/trigger", trigger_handler)
    app.router.add_get("/api/gigs", gigs_handler)
    app.router.add_post("/api/ingest", ingest_handler)
    app.router.add_get("/api/seo/products", seo_products_handler)
    app.router.add_get(f"/{INDEXNOW_KEY}.txt",
                       lambda r: web.Response(text=INDEXNOW_KEY, content_type="text/plain"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"Freelance Gig Engine on port {PORT}")
    await send_telegram(
        "<b>Freelance Gig Engine gestartet!</b>\n"
        "Fiverr Gig Generator\n"
        "Upwork Proposal Generator\n\n"
        "Taglich 2x optimierte Proposals via Telegram!\n"
        "Erster Batch in 90 Sekunden..."
    )
    asyncio.create_task(scheduler())
    asyncio.create_task(_seo_broadcast_loop())
    await asyncio.Future()


async def _seo_broadcast_loop():
    await asyncio.sleep(45)
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                async with s.post('https://seo-traffic-engine-production.up.railway.app/api/generate',
                                  json={'topic': 'Fiverr Freelance und Upwork Automatisierung', 'auto_post': True}) as r:
                    if r.status == 200:
                        logger.info('SEO Bridge: Artikel generiert und gebroadcastet')
                    else:
                        logger.warning(f'SEO Bridge: HTTP {r.status}')
        except Exception as e:
            logger.error(f'SEO Bridge Fehler: {e}')
        await asyncio.sleep(6 * 3600)


if __name__ == "__main__":
    asyncio.run(main())
