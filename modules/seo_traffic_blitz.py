#!/usr/bin/env python3
"""
SEO Traffic Blitz — vollautonome SEO + Traffic Engine
Keine neuen APIs nötig — nutzt bestehende Shopify, Google, Telegram Keys.
"""
import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("SEOBlitz")

SHOP_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOP_VER     = os.getenv("SHOPIFY_API_VERSION", "2024-10")
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")
STORE_URL    = "https://autopilot-store-suite-fmbka.myshopify.com"
BLOG_GID     = f"gid://shopify/Blog/{os.getenv('SHOPIFY_BLOG_ID', '127011258755')}"

SEO_KEYWORDS = [
    "Shopify Dropshipping 2026", "Online Geld verdienen Deutschland",
    "Passives Einkommen KI", "AliExpress Dropshipping Anleitung",
    "Print on Demand Gewinn", "Amazon FBA Alternative 2026",
    "TikTok viral Produkte 2026", "Shopify Anfänger Guide",
    "KI Business automatisieren", "Side Hustle Deutschland 2026",
    "Geld verdienen Österreich online", "Schweiz Online Business starten",
    "Dropshipping Einsteiger Tipps", "Affiliate Marketing DS24",
    "Shopify SEO optimieren", "E-Commerce Automation Tools",
    "Digitale Produkte verkaufen", "Printify T-Shirts verkaufen",
    "eBay Dropshipping 2026", "Klaviyo Email Marketing",
    "Mailchimp Shopify Integration", "Twilio SMS Marketing",
    "KI Produktbeschreibungen automatisch", "Shopify Apps kostenlos",
    "WooCommerce vs Shopify 2026", "Online Shop ohne Lager",
    "Meistverkaufte Produkte AliExpress", "Instagram Shop erstellen",
    "TikTok Shop Produkte", "Bestseller Nischen finden",
    "Passive Einnahmen ohne Startkapital", "Digistore24 Affiliate starten",
]

TEMPLATES = [
    "🚀 {kw} — mit KI und Automatisierung jetzt einfacher als je zuvor! 👉 {url}",
    "💡 Tipp des Tages: {kw}. Schau dir das an: {url} #PassivesEinkommen",
    "📈 {kw}: Die beste Strategie 2026! Mehr Info: {url} #ECommerce #KI",
    "🔥 Hot: {kw} — vollautomatisch, passiv, profitabel. Start: {url}",
    "💰 {kw} — so geht passives Einkommen 2026! {url} #Dropshipping",
]


async def _tg(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown",
                      "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("ok", False)
    except Exception:
        return False


async def _shopify_graphql(query: str, variables: dict = None) -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/graphql.json",
                headers={"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                return await r.json(content_type=None)
    except Exception as e:
        return {"error": str(e)}


# ── 1. Sitemap Ping ───────────────────────────────────────────────────────────

async def run_sitemap_submit() -> dict:
    """Submit URLs via IndexNow (Bing/Yandex) — modern replacement for deprecated ping endpoints."""
    sitemap = f"{STORE_URL}/sitemap.xml"
    store_pages = [
        STORE_URL,
        f"{STORE_URL}/collections/all",
        f"{STORE_URL}/blogs/must-have-trends-tipps",
    ]
    ok = 0
    total = 0

    # IndexNow: Bing + Yandex + IndexNow hub all accept this protocol
    indexnow_key = os.getenv("INDEXNOW_KEY", "supermegabot2026")
    indexnow_endpoints = [
        "https://api.indexnow.org/indexnow",
        "https://www.bing.com/indexnow",
        "https://yandex.com/indexnow",
    ]
    payload = {
        "host": "autopilot-store-suite-fmbka.myshopify.com",
        "key": indexnow_key,
        "keyLocation": f"{STORE_URL}/{indexnow_key}.txt",
        "urlList": store_pages,
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        for endpoint in indexnow_endpoints:
            total += 1
            try:
                async with s.post(endpoint, json=payload,
                                  headers={"Content-Type": "application/json; charset=utf-8"}) as r:
                    if r.status in (200, 202):
                        ok += 1
                        log.info("IndexNow OK: %s", endpoint)
                    else:
                        log.warning("IndexNow %s: HTTP %d", endpoint, r.status)
            except Exception as e:
                log.warning("IndexNow %s error: %s", endpoint, e)

    return {"pings_ok": ok, "pings_total": total, "sitemap": sitemap, "protocol": "IndexNow"}


# ── 2. Keyword Content Blast ──────────────────────────────────────────────────

async def run_keyword_content_blast(count: int = 5) -> dict:
    """Post keyword-optimized content to Telegram + trigger BRUTUS."""
    keywords = random.sample(SEO_KEYWORDS, min(count, len(SEO_KEYWORDS)))
    channels_hit = 0
    posted = 0

    for kw in keywords:
        text = random.choice(TEMPLATES).format(kw=kw, url=STORE_URL)
        tg_ok = await _tg(f"🔍 *SEO-Content*\n\n{text}")
        if tg_ok:
            channels_hit += 1

        try:
            from modules.brutus_traffic_engine import brutus_run
            r = await brutus_run(niche=kw)
            channels_hit += r.get("channels_hit", 0)
        except Exception:
            pass

        posted += 1
        await asyncio.sleep(1)

    return {"keywords_posted": posted, "channels_hit": channels_hit}


# ── 3. Directory Submit (logged) ──────────────────────────────────────────────

async def run_backlink_directory_submit() -> dict:
    """Log free directory submission targets — builds awareness."""
    directories = [
        "https://www.gelbeseiten.de", "https://www.klicktel.de",
        "https://www.cylex.de", "https://www.stadtbranchenbuch.com",
        "https://www.meinprospekt.de", "https://www.firmen.wko.at",
        "https://www.search.ch", "https://www.local.ch",
        "https://www.das-telefonbuch.de", "https://www.11880.com",
        "https://www.meinestadt.de", "https://www.yelp.de",
        "https://www.foursquare.com", "https://www.hotfrog.de",
        "https://www.wlw.de", "https://www.kompass.com/de",
    ]
    log.info("Directory targets: %d sites for %s", len(directories), STORE_URL)
    await _tg(
        f"📋 *Backlink-Verzeichnisse* ({len(directories)} Ziele)\n\n"
        f"Shop: {STORE_URL}\n"
        f"Targets: GelbeSeiten, Yelp, Cylex, WKO, local.ch, 11880, ..."
    )
    return {"directories_targeted": len(directories), "store_url": STORE_URL}


# ── 4. Schema SEO Inject ──────────────────────────────────────────────────────

async def run_schema_markup_inject(limit: int = 10) -> dict:
    """Update Shopify product SEO titles/descriptions via GraphQL metafields."""
    if not SHOP_TOKEN or not SHOP_DOMAIN:
        return {"products_updated": 0, "error": "no shopify credentials"}

    # Fetch products
    q = """{ products(first: %d) { edges { node { id title seo { title description } } } } }""" % limit
    data = await _shopify_graphql(q)
    products = data.get("data", {}).get("products", {}).get("edges", [])
    if not products:
        return {"products_updated": 0, "error": "no products fetched"}

    updated = 0
    mutation = """
mutation UpdateSEO($id: ID!, $seo: SEOInput!) {
  productUpdate(input: {id: $id, seo: $seo}) {
    product { id seo { title description } }
    userErrors { field message }
  }
}"""
    for edge in products:
        node = edge["node"]
        pid = node["id"]
        title = node.get("title", "")
        seo = node.get("seo", {})
        # Only update if SEO description is missing/short
        if seo.get("description") and len(seo["description"]) > 50:
            continue
        seo_title = f"{title} | autopilot-store-suite-fmbka.myshopify.com — Best Deals 2026"[:255]
        seo_desc  = (f"Entdecke {title} bei autopilot-store-suite-fmbka.myshopify.com — "
                     f"Top-Preise, schnelle Lieferung, vollautomatischer Shop. "
                     f"Shopify Dropshipping 2026.")[:320]
        r = await _shopify_graphql(mutation, {
            "id": pid,
            "seo": {"title": seo_title, "description": seo_desc}
        })
        errs = r.get("data", {}).get("productUpdate", {}).get("userErrors", [])
        if not errs:
            updated += 1
        await asyncio.sleep(0.3)

    log.info("Schema SEO: %d/%d products updated", updated, len(products))
    return {"products_updated": updated, "products_checked": len(products)}


# ── 5. Internal Link Builder ──────────────────────────────────────────────────

async def run_internal_link_builder() -> dict:
    """Create a Mega Guide blog post linking all other articles via Shopify GraphQL."""
    if not SHOP_TOKEN or not SHOP_DOMAIN:
        return {"articles_linked": 0, "error": "no shopify credentials"}

    # Fetch existing articles
    q = """{
  blog(id: "%s") {
    articles(first: 20) { edges { node { title handle } } }
  }
}""" % BLOG_GID
    data = await _shopify_graphql(q)
    articles = data.get("data", {}).get("blog", {}).get("articles", {}).get("edges", [])

    if not articles:
        return {"articles_linked": 0, "error": "no articles found"}

    links_html = "\n".join([
        f'<li><a href="{STORE_URL}/blogs/must-have-trends-tipps/{a["node"]["handle"]}">'
        f'{a["node"]["title"]}</a></li>'
        for a in articles
    ])

    body = f"""<h1>Der ultimative E-Commerce Guide 2026 — Alle Themen auf einen Blick</h1>
<p>Hier findest du alle unsere Guides zu Shopify, Dropshipping, KI-Automatisierung und passivem Einkommen.</p>
<h2>Alle Artikel</h2>
<ul>
{links_html}
</ul>
<h2>Warum automatisieren?</h2>
<p>Mit modernen KI-Tools läuft dein Online-Business 24/7 — Shopify, AliExpress, Amazon, Print on Demand alles vollautomatisch.</p>
<p><strong><a href="{STORE_URL}">👉 Jetzt bei autopilot-store-suite-fmbka.myshopify.com stöbern →</a></strong></p>"""

    mutation = """
mutation CreateArticle($article: ArticleCreateInput!) {
  articleCreate(article: $article) {
    article { id title handle }
    userErrors { field message }
  }
}"""
    r = await _shopify_graphql(mutation, {
        "article": {
            "blogId": BLOG_GID,
            "title": f"E-Commerce Mega Guide 2026 — Alle Tipps & Tricks",
            "body": body,
            "isPublished": True,
            "tags": ["guide", "seo", "ecommerce", "2026", "shopify"],
            "author": {"name": "BullPower Hub"},
        }
    })
    art = r.get("data", {}).get("articleCreate", {}).get("article", {})
    if art and art.get("id"):
        log.info("Internal link builder: created guide linking %d articles", len(articles))
        return {"articles_linked": len(articles), "guide_handle": art.get("handle")}
    errs = r.get("data", {}).get("articleCreate", {}).get("userErrors", [])
    return {"articles_linked": 0, "error": str(errs)[:100]}


# ── 6. Full SEO Blast ─────────────────────────────────────────────────────────

async def run_full_seo_blast() -> dict:
    """Run all SEO tasks in sequence."""
    ts = datetime.now(timezone.utc).isoformat()
    log.info("Full SEO Blast starting at %s", ts)

    sitemap = await run_sitemap_submit()
    await asyncio.sleep(1)
    keywords = await run_keyword_content_blast(count=5)
    await asyncio.sleep(1)
    schema = await run_schema_markup_inject(limit=10)
    await asyncio.sleep(1)
    dirs = await run_backlink_directory_submit()

    summary = {
        "sitemap_pings": sitemap.get("pings_ok", 0),
        "keywords_posted": keywords.get("keywords_posted", 0),
        "channels_hit": keywords.get("channels_hit", 0),
        "schema_updated": schema.get("products_updated", 0),
        "directories_targeted": dirs.get("directories_targeted", 0),
        "internal_links": 0,
        "ts": ts,
    }
    log.info("Full SEO Blast done: %s", summary)
    return summary
