#!/usr/bin/env python3
"""Freelance Gig Engine — Fiverr + Upwork Content Generator"""
import asyncio, aiohttp, os, logging, sqlite3, random
from datetime import datetime
import anthropic

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5088771245")
PORT = int(os.getenv("PORT", 8093))

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
        "demo_url": "https://dudirudibot-mega-production.up.railway.app"
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


async def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as s:
        try:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4096], "parse_mode": "HTML"})
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")


async def generate_fiverr_gig(service: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": f"""Create an optimized Fiverr gig description in ENGLISH:

SERVICE: {service['title']}
CATEGORY: {service['fiverr_category']}
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

    fiverr_gig = await generate_fiverr_gig(service)

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

    logger.info("Content cycle done.")


async def scheduler():
    await asyncio.sleep(90)
    while True:
        try:
            await content_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        await asyncio.sleep(12 * 3600)


async def health_handler(request):
    from aiohttp import web
    conn = sqlite3.connect(DB_PATH)
    gigs = conn.execute("SELECT COUNT(*) FROM gigs").fetchone()[0]
    props = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
    conn.close()
    return web.json_response({
        "status": "ok",
        "service": "freelance-gig-engine",
        "gigs_generated": gigs,
        "proposals_generated": props,
        "platforms": ["fiverr", "upwork"]
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
    app.router.add_post("/api/trigger", trigger_handler)
    app.router.add_get("/api/gigs", gigs_handler)
    app.router.add_post("/api/ingest", ingest_handler)
    app.router.add_get("/api/seo/products", seo_products_handler)
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
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
