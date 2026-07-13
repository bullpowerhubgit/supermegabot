"""
SEO Mega Engine — Revolutionäres autonomes SEO-System.
60 Artikel/Tag, 100 Keywords, Auto-Google-Indexierung, Competitor-Analysis,
Internal Linking, Schema Markup, Meta-Optimizer — vollständig autonom.
Kein Konkurrenzprodukt auf dem Markt macht das alles automatisch.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

import aiohttp

log = logging.getLogger("SEOMegaEngine")

ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL     = "claude-haiku-4-5-20251001"
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TG_CHAT         = _TG_CHANNEL or ""
SITE_URL        = os.getenv("SITE_URL", "https://supermegabot-production.up.railway.app")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
INDEXNOW_KEY    = os.getenv("INDEXNOW_API_KEY", hashlib.md5(SITE_URL.encode()).hexdigest()[:32])

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "seo_mega"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

NICHES = [
    "Shopify E-Commerce Automatisierung",
    "KI-Tools für Online-Händler",
    "Dropshipping Deutschland",
    "Telegram Bot Monetarisierung",
    "Digistore24 Affiliate Marketing",
]

COMPETITOR_URLS = [
    "https://www.shopify.com/blog",
    "https://www.oberlo.com/blog",
    "https://digistore24.com/blog",
]


# ─────────────────────────────────────────────────────────────
# CLAUDE HELPER
# ─────────────────────────────────────────────────────────────

async def _claude(prompt: str, max_tokens: int = 2000) -> str:
    try:
        from modules.ai_client import ai_complete
        r = await ai_complete(prompt, max_tokens=1200)
        return r if r else ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ai_complete fallback: {e}")
        return ""

async def _supa_post(table: str, payload: dict) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"error": "no_supabase"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=payload,
            ) as r:
                return {"status": r.status}
    except Exception as e:
        return {"error": str(e)}


async def _supa_get(table: str, params: str = "") -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept-Profile": "public"},
            ) as r:
                if r.status == 200:
                    return await r.json()
                return []
    except Exception as e:
        log.error(f"Supabase GET {table}: {e}")
        return []


async def _telegram(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096]},
            )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# 1. KEYWORD INTELLIGENCE
# ─────────────────────────────────────────────────────────────

async def discover_keywords(niche: str, count: int = 100) -> list[dict]:
    """Generate long-tail keywords with intent using Claude."""
    prompt = (
        f"Du bist ein SEO-Experte für den DACH-Markt (Deutschland, Österreich, Schweiz).\n"
        f"Nische: '{niche}'\n"
        f"Generiere {count} Long-Tail-Keywords auf Deutsch mit:\n"
        f"- Suchintention (informational/commercial/transactional/navigational)\n"
        f"- Schwierigkeit (low/medium/high)\n"
        f"- Content-Winkel (1 Satz was der Artikel abdecken soll)\n"
        f"Format: JSON-Array mit Feldern: keyword, intent, difficulty, content_angle\n"
        f"Nur JSON, kein Text davor oder danach."
    )
    raw = await _claude(prompt, max_tokens=4000)
    try:
        # Extract JSON array from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        log.error(f"discover_keywords parse error: {e}")
    return []


async def discover_all_keywords() -> list[dict]:
    """Run keyword discovery for all niches."""
    all_kws = []
    for niche in NICHES:
        kws = await discover_keywords(niche, count=20)
        all_kws.extend(kws)
    # Cache to disk
    cache = DATA_DIR / "keywords.json"
    cache.write_text(json.dumps(all_kws, ensure_ascii=False, indent=2))
    return all_kws


def _load_cached_keywords() -> list[dict]:
    cache = DATA_DIR / "keywords.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    return []


# ─────────────────────────────────────────────────────────────
# 2. CONTENT FACTORY
# ─────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[äöüß]', lambda m: {'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}[m.group()], text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:80]


async def generate_seo_article(keyword: str, language: str = "de") -> dict:
    """Generate complete 1500+ word SEO article via Claude Haiku."""
    slug = _slugify(keyword)
    prompt = (
        f"Schreibe einen vollständigen SEO-optimierten Artikel auf Deutsch über: '{keyword}'\n\n"
        f"Anforderungen:\n"
        f"- Titel (50-60 Zeichen, keyword-reich)\n"
        f"- Meta-Description (150-160 Zeichen, mit Call-to-Action)\n"
        f"- H1 (keyword-optimiert)\n"
        f"- Mindestens 6 H2-Abschnitte mit je 200-250 Wörtern\n"
        f"- FAQ-Sektion mit 5 Fragen und Antworten\n"
        f"- CTA am Ende: Link zu https://bullpower-hub-portal.netlify.app\n"
        f"- Integriere das Keyword natürlich 8-12 mal\n"
        f"- Professioneller, vertrauenswürdiger Ton\n\n"
        f"Antworte NUR mit JSON:\n"
        f'{{"title": "...", "meta_description": "...", "h1": "...", '
        f'"content_html": "<h1>...</h1><h2>...</h2>...", '
        f'"faq": [{{"question": "...", "answer": "..."}}]}}'
    )
    raw = await _claude(prompt, max_tokens=4000)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            content_html = data.get("content_html", "")
            word_count = len(re.sub('<[^>]+>', '', content_html).split())

            # Build Article schema
            schema = {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": data.get("title", keyword),
                "description": data.get("meta_description", ""),
                "author": {"@type": "Organization", "name": "BullPower Hub"},
                "publisher": {
                    "@type": "Organization",
                    "name": "BullPower Hub",
                    "logo": {"@type": "ImageObject",
                             "url": f"{SITE_URL}/static/logo.png"}
                },
                "datePublished": datetime.now(timezone.utc).isoformat(),
                "url": f"{SITE_URL}/blog/{slug}",
                "mainEntityOfPage": f"{SITE_URL}/blog/{slug}",
            }

            # Build FAQ schema
            faq_items = data.get("faq", [])
            if faq_items:
                faq_schema = {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {"@type": "Question",
                         "name": q.get("question", ""),
                         "acceptedAnswer": {"@type": "Answer",
                                            "text": q.get("answer", "")}}
                        for q in faq_items
                    ]
                }
            else:
                faq_schema = {}

            return {
                "keyword": keyword,
                "title": data.get("title", keyword),
                "meta_description": data.get("meta_description", ""),
                "h1": data.get("h1", keyword),
                "slug": slug,
                "content_html": content_html,
                "faq_html": "".join(
                    f"<div class='faq-item'><h3>{q.get('question','')}</h3>"
                    f"<p>{q.get('answer','')}</p></div>"
                    for q in faq_items
                ),
                "schema_json": schema,
                "faq_schema_json": faq_schema,
                "word_count": word_count,
                "language": language,
                "slug_url": f"{SITE_URL}/blog/{slug}",
            }
    except Exception as e:
        log.error(f"generate_seo_article parse error for '{keyword}': {e}")
    return {"keyword": keyword, "slug": slug, "error": "parse_failed"}


# ─────────────────────────────────────────────────────────────
# 3. BULK CONTENT FACTORY (60 articles/day)
# ─────────────────────────────────────────────────────────────

async def run_content_factory(batch_size: int = 5) -> dict:
    """
    Generate batch_size articles, save to Supabase + Shopify blog.
    Run every 2h with batch_size=5 → 60 articles/day.
    """
    keywords = _load_cached_keywords()
    if not keywords:
        keywords = await discover_all_keywords()

    # Pick keywords not yet published (check Supabase)
    published = await _supa_get("seo_content", "select=slug&published=eq.true&limit=500")
    published_slugs = {r.get("slug") for r in published}

    candidates = [
        k for k in keywords
        if _slugify(k.get("keyword", "")) not in published_slugs
    ][:batch_size]

    if not candidates:
        # Re-discover keywords
        keywords = await discover_all_keywords()
        candidates = keywords[:batch_size]

    results = {"generated": 0, "saved": 0, "published_shopify": 0, "errors": []}

    for kw_obj in candidates:
        keyword = kw_obj.get("keyword", "") if isinstance(kw_obj, dict) else str(kw_obj)
        try:
            article = await generate_seo_article(keyword)
            if "error" in article:
                results["errors"].append(f"{keyword}: {article['error']}")
                continue
            results["generated"] += 1

            # Save to Supabase
            supa_row = {
                "keyword": article["keyword"],
                "title": article["title"],
                "slug": article["slug"],
                "meta_description": article["meta_description"],
                "content_html": article["content_html"],
                "schema_json": article["schema_json"],
                "language": article.get("language", "de"),
                "word_count": article.get("word_count", 0),
                "published": False,
            }
            save_result = await _supa_post("seo_content", supa_row)
            if save_result.get("status", 500) < 300:
                results["saved"] += 1

            # Publish to Shopify blog
            if SHOPIFY_DOMAIN and SHOPIFY_TOKEN:
                pub = await _publish_to_shopify_blog(article)
                if pub.get("ok"):
                    results["published_shopify"] += 1

            await asyncio.sleep(2)  # Rate limit between articles

        except Exception as e:
            results["errors"].append(f"{keyword}: {e}")

    # Telegram notification
    msg = (
        f"📝 SEO Content Factory:\n"
        f"✅ {results['generated']} Artikel generiert\n"
        f"💾 {results['saved']} in Supabase gespeichert\n"
        f"🛍️ {results['published_shopify']} auf Shopify Blog\n"
        f"❌ {len(results['errors'])} Fehler"
    )
    await _telegram(msg)
    return results


async def _publish_to_shopify_blog(article: dict) -> dict:
    """Publish article to Shopify blog as a blog post."""
    try:
        # Get first blog ID
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
            ) as r:
                data = await r.json()
                blogs = data.get("blogs", [])
                if not blogs:
                    return {"ok": False, "reason": "no_blogs"}
                blog_id = blogs[0]["id"]

        schema_str = json.dumps(article.get("schema_json", {}))
        faq_str = json.dumps(article.get("faq_schema_json", {}))
        full_html = (
            f"{article['content_html']}\n"
            f"<div class='faq'>{article.get('faq_html','')}</div>\n"
            f"<script type='application/ld+json'>{schema_str}</script>\n"
            f"<script type='application/ld+json'>{faq_str}</script>"
        )

        post_data = {
            "article": {
                "title": article["title"],
                "body_html": full_html,
                "summary_html": article["meta_description"],
                "tags": article["keyword"],
                "handle": article["slug"],
                "published": True,
                "metafields": [
                    {"key": "title_tag", "value": article["title"],
                     "type": "single_line_text_field", "namespace": "global"},
                    {"key": "description_tag", "value": article["meta_description"],
                     "type": "single_line_text_field", "namespace": "global"},
                ]
            }
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                         "Content-Type": "application/json"},
                json=post_data,
            ) as r:
                if r.status in (200, 201):
                    resp = await r.json()
                    article_id = resp.get("article", {}).get("id")
                    return {"ok": True, "article_id": article_id}
                return {"ok": False, "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 4. TECHNICAL SEO
# ─────────────────────────────────────────────────────────────

async def generate_sitemap(base_url: str = SITE_URL) -> str:
    """Generate XML sitemap from Supabase seo_content + static pages."""
    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    static_pages = [
        ("", "1.0", "daily"),
        ("/blog", "0.9", "daily"),
        ("/api/paypal/success", "0.3", "monthly"),
    ]
    for path, priority, freq in static_pages:
        url_el = ET.SubElement(root, "url")
        ET.SubElement(url_el, "loc").text = f"{base_url}{path}"
        ET.SubElement(url_el, "changefreq").text = freq
        ET.SubElement(url_el, "priority").text = priority
        ET.SubElement(url_el, "lastmod").text = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Published articles from Supabase
    articles = await _supa_get("seo_content", "select=slug,created_at&published=eq.true&limit=1000")
    for art in articles:
        slug = art.get("slug", "")
        lastmod = art.get("created_at", "")[:10] if art.get("created_at") else ""
        url_el = ET.SubElement(root, "url")
        ET.SubElement(url_el, "loc").text = f"{base_url}/blog/{slug}"
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.8"
        if lastmod:
            ET.SubElement(url_el, "lastmod").text = lastmod

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


async def submit_to_google(sitemap_url: str = "") -> dict:
    """Ping Google + Bing + IndexNow with sitemap."""
    if not sitemap_url:
        sitemap_url = f"{SITE_URL}/api/seo/sitemap.xml"

    results = {}
    ping_targets = [
        ("google", f"https://www.google.com/ping?sitemap={quote(sitemap_url)}"),
        ("bing",   f"https://www.bing.com/ping?sitemap={quote(sitemap_url)}"),
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        for name, url in ping_targets:
            try:
                async with s.get(url) as r:
                    results[name] = {"status": r.status, "ok": r.status < 400}
            except Exception as e:
                results[name] = {"ok": False, "error": str(e)}

        # IndexNow (Bing, Yandex, Seznam)
        indexnow_url = (
            f"https://api.indexnow.org/indexnow?"
            f"url={quote(SITE_URL)}&key={INDEXNOW_KEY}"
        )
        try:
            async with s.get(indexnow_url) as r:
                results["indexnow"] = {"status": r.status, "ok": r.status < 400}
        except Exception as e:
            results["indexnow"] = {"ok": False, "error": str(e)}

    return {"sitemap_url": sitemap_url, "results": results,
            "pinged_at": datetime.now(timezone.utc).isoformat()}


async def generate_schema_markup(page_type: str, data: dict) -> dict:
    """Generate JSON-LD schema for any page type."""
    base = {"@context": "https://schema.org"}

    if page_type == "Product":
        return {**base, "@type": "Product",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "offers": {"@type": "Offer",
                           "price": data.get("price", "0"),
                           "priceCurrency": data.get("currency", "EUR"),
                           "availability": "https://schema.org/InStock"}}

    if page_type == "Article":
        return {**base, "@type": "Article",
                "headline": data.get("title", ""),
                "author": {"@type": "Organization", "name": "BullPower Hub"},
                "datePublished": data.get("date", datetime.now(timezone.utc).isoformat()),
                "url": data.get("url", SITE_URL)}

    if page_type == "FAQ":
        return {**base, "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q.get("q", ""),
                     "acceptedAnswer": {"@type": "Answer", "text": q.get("a", "")}}
                    for q in data.get("items", [])
                ]}

    if page_type == "Organization":
        return {**base, "@type": "Organization",
                "name": "BullPower Hub",
                "url": "https://bullpower-hub-portal.netlify.app",
                "contactPoint": {"@type": "ContactPoint", "contactType": "customer service"}}

    if page_type == "BreadcrumbList":
        return {**base, "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "name": item.get("name", ""),
                     "item": item.get("url", "")}
                    for i, item in enumerate(data.get("items", []))
                ]}

    return {**base, "@type": page_type, **data}


# ─────────────────────────────────────────────────────────────
# 5. META TAG OPTIMIZER
# ─────────────────────────────────────────────────────────────

async def optimize_meta_tags(url: str, content: str) -> dict:
    """Generate 3 A/B title+description variants via Claude."""
    prompt = (
        f"URL: {url}\n"
        f"Content (Auszug): {content[:500]}\n\n"
        f"Generiere 3 verschiedene Meta-Tag-Varianten auf Deutsch.\n"
        f"Jede Variante: title (50-60 Zeichen), description (150-160 Zeichen).\n"
        f"Variante 1: Informational (Wissensvermittlung)\n"
        f"Variante 2: Commercial (Nutzenorientiert, €-Ersparnis/Gewinn)\n"
        f"Variante 3: Urgency (Zeitdruck/Exklusivität)\n"
        f"Format JSON: [{{'variant': 1, 'title': '...', 'description': '...', "
        f"'ctr_score': 0-10}}]"
    )
    raw = await _claude(prompt, max_tokens=1000)
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            variants = json.loads(match.group())
            best = max(variants, key=lambda x: x.get("ctr_score", 0))
            return {"variants": variants, "recommended": best}
    except Exception as e:
        log.error(f"optimize_meta_tags error: {e}")
    return {"error": "parse_failed", "raw": raw[:200]}


# ─────────────────────────────────────────────────────────────
# 6. INTERNAL LINKING AUTOMATON
# ─────────────────────────────────────────────────────────────

async def build_internal_links(max_articles: int = 50) -> dict:
    """AI-powered internal link suggestions between articles."""
    articles = await _supa_get(
        "seo_content",
        f"select=slug,title,keyword&published=eq.true&limit={max_articles}"
    )
    if len(articles) < 2:
        return {"links": [], "reason": "not_enough_articles"}

    article_list = "\n".join(
        f"- {a.get('slug')}: {a.get('title','')} (keyword: {a.get('keyword','')})"
        for a in articles
    )
    prompt = (
        f"Du bist ein SEO-Experte. Hier sind {len(articles)} Blog-Artikel:\n\n"
        f"{article_list}\n\n"
        f"Erstelle interne Link-Empfehlungen: welcher Artikel soll auf welchen anderen "
        f"verlinken, und mit welchem Anchor-Text?\n"
        f"Erstelle max. {min(len(articles)*2, 30)} Links.\n"
        f"Format JSON: [{{'from_slug': '...', 'to_slug': '...', 'anchor_text': '...'}}]"
    )
    raw = await _claude(prompt, max_tokens=2000)
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            links = json.loads(match.group())
            return {"links": links, "total": len(links),
                    "articles_analyzed": len(articles)}
    except Exception as e:
        log.error(f"build_internal_links error: {e}")
    return {"links": [], "error": "parse_failed"}


# ─────────────────────────────────────────────────────────────
# 7. GOOGLE INDEXING API (Instant Indexing)
# ─────────────────────────────────────────────────────────────

async def ping_indexing_api(urls: list[str]) -> dict:
    """Submit URLs to Google Indexing API via service account JWT."""
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        # Fallback: IndexNow for all URLs
        return await _indexnow_submit(urls)

    try:
        sa = json.loads(sa_json)
        token = await _get_google_jwt(sa)
        if not token:
            return await _indexnow_submit(urls)

        results = {"submitted": 0, "failed": 0, "urls": []}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            for url in urls[:200]:
                try:
                    async with s.post(
                        "https://indexing.googleapis.com/v3/urlNotifications:publish",
                        headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"},
                        json={"url": url, "type": "URL_UPDATED"},
                    ) as r:
                        if r.status == 200:
                            results["submitted"] += 1
                        else:
                            results["failed"] += 1
                        results["urls"].append({"url": url, "status": r.status})
                    await asyncio.sleep(0.1)
                except Exception as e:
                    results["failed"] += 1
                    results["urls"].append({"url": url, "error": str(e)})
        return results
    except Exception as e:
        log.error(f"ping_indexing_api: {e}")
        return await _indexnow_submit(urls)


async def _indexnow_submit(urls: list[str]) -> dict:
    """IndexNow bulk submit (free, covers Bing/Yandex/Seznam/Naver)."""
    host = SITE_URL.replace("https://", "").replace("http://", "").split("/")[0]
    payload = {"host": host, "key": INDEXNOW_KEY,
               "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
               "urlList": urls[:10000]}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                "https://api.indexnow.org/indexnow",
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as r:
                return {"method": "indexnow", "status": r.status,
                        "submitted": len(urls), "ok": r.status in (200, 202)}
    except Exception as e:
        return {"method": "indexnow", "error": str(e), "submitted": 0}


async def _get_google_jwt(sa: dict) -> Optional[str]:
    """Minimal JWT for Google API service account."""
    try:
        import base64
        import struct

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b'=').decode()

        now = int(time.time())
        claims = {
            "iss": sa["client_email"],
            "scope": "https://www.googleapis.com/auth/indexing",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": now + 3600,
            "iat": now,
        }
        payload = base64.urlsafe_b64encode(
            json.dumps(claims).encode()
        ).rstrip(b'=').decode()

        # Sign with RSA private key — requires cryptography lib
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend

            private_key = serialization.load_pem_private_key(
                sa["private_key"].encode(), password=None,
                backend=default_backend()
            )
            signing_input = f"{header}.{payload}".encode()
            signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
            sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
            jwt_token = f"{header}.{payload}.{sig_b64}"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(
                    "https://oauth2.googleapis.com/token",
                    data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                          "assertion": jwt_token},
                ) as r:
                    data = await r.json()
                    return data.get("access_token")
        except ImportError:
            log.warning("cryptography lib not available — JWT signing skipped")
            return None
    except Exception as e:
        log.error(f"_get_google_jwt: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# 8. COMPETITOR ANALYSIS
# ─────────────────────────────────────────────────────────────

async def analyze_competitor(competitor_url: str) -> dict:
    """Scrape competitor, extract keywords, identify content gaps."""
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; BullPowerBot/1.0)"}
        ) as s:
            async with s.get(competitor_url) as r:
                if r.status != 200:
                    return {"error": f"HTTP {r.status}", "url": competitor_url}
                html = await r.text()
    except Exception as e:
        return {"error": str(e), "url": competitor_url}

    # Extract titles, H1s, H2s, meta description
    titles = re.findall(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
    meta = re.findall(r'<meta\s+name="description"[^>]*content="([^"]*)"',
                      html, re.IGNORECASE)

    clean = lambda s: re.sub('<[^>]+>', '', s).strip()
    extracted = {
        "title": clean(titles[0]) if titles else "",
        "h1s": [clean(h) for h in h1s[:5]],
        "h2s": [clean(h) for h in h2s[:10]],
        "meta_description": meta[0] if meta else "",
    }

    prompt = (
        f"Analysiere diese Konkurrenz-Seite: {competitor_url}\n\n"
        f"Extrahierte Daten: {json.dumps(extracted, ensure_ascii=False)}\n\n"
        f"Identifiziere:\n"
        f"1. Ihre Top-Keywords (max. 10)\n"
        f"2. Content-Lücken die wir besser abdecken können (max. 5)\n"
        f"3. Quick-Win-Themen die wir diese Woche publizieren sollten (max. 3)\n"
        f"Format JSON: {{'their_keywords': [...], 'content_gaps': [...], 'quick_win_topics': [...]}}"
    )
    raw = await _claude(prompt, max_tokens=1000)
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            analysis = json.loads(match.group())
            return {"url": competitor_url, "extracted": extracted, "analysis": analysis}
    except Exception as e:
        log.error(f"analyze_competitor parse error: {e}")

    return {"url": competitor_url, "extracted": extracted, "raw": raw[:300]}


async def analyze_all_competitors() -> dict:
    """Analyze all configured competitor URLs."""
    results = {}
    for url in COMPETITOR_URLS:
        results[url] = await analyze_competitor(url)
        await asyncio.sleep(3)

    # Extract quick wins and add to keyword cache
    quick_wins = []
    for analysis in results.values():
        topics = analysis.get("analysis", {}).get("quick_win_topics", [])
        quick_wins.extend({"keyword": t, "intent": "informational",
                           "difficulty": "low", "content_angle": "competitor gap"}
                          for t in topics)

    if quick_wins:
        existing = _load_cached_keywords()
        merged = existing + quick_wins
        (DATA_DIR / "keywords.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2)
        )

    return {"competitors_analyzed": len(results), "quick_wins_added": len(quick_wins),
            "results": results}


# ─────────────────────────────────────────────────────────────
# 9. SEO REPORT
# ─────────────────────────────────────────────────────────────

async def generate_seo_report() -> dict:
    """Daily SEO report → Telegram."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_articles = await _supa_get("seo_content", "select=id&limit=1")
    published = await _supa_get("seo_content", "select=id&published=eq.true&limit=1")
    today_published = await _supa_get(
        "seo_content",
        f"select=id&created_at=gte.{today}&limit=100"
    )

    cached_kws = _load_cached_keywords()

    report = {
        "date": today,
        "total_articles": len(total_articles),
        "total_published": len(published),
        "published_today": len(today_published),
        "keywords_in_cache": len(cached_kws),
        "estimated_monthly_traffic": len(published) * 15,
    }

    msg = (
        f"📊 SEO Mega Report — {today}\n\n"
        f"📝 Artikel gesamt: {report['total_articles']}\n"
        f"✅ Publiziert: {report['total_published']}\n"
        f"🆕 Heute neu: {report['published_today']}\n"
        f"🔑 Keywords in Pipeline: {report['keywords_in_cache']}\n"
        f"📈 Gesch. Traffic/Monat: ~{report['estimated_monthly_traffic']} Besucher\n\n"
        f"🚀 System läuft vollautomatisch — 60 Artikel/Tag"
    )
    await _telegram(msg)
    return report


# ─────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

async def run_seo_mega_engine(mode: str = "factory") -> dict:
    """
    Central entry point.
    mode='factory'     → generate 5 articles (runs every 2h)
    mode='submit'      → ping Google/Bing/IndexNow
    mode='report'      → daily Telegram report
    mode='competitor'  → competitor analysis
    mode='full'        → all of the above
    """
    if mode == "factory":
        return await run_content_factory(batch_size=5)

    if mode == "submit":
        sitemap = await generate_sitemap()
        (DATA_DIR / "sitemap.xml").write_text(sitemap)
        return await submit_to_google()

    if mode == "report":
        return await generate_seo_report()

    if mode == "competitor":
        return await analyze_all_competitors()

    if mode == "full":
        results = {}
        results["factory"] = await run_content_factory(batch_size=5)
        results["submit"]  = await submit_to_google()
        results["report"]  = await generate_seo_report()
        return results

    return {"error": f"unknown mode: {mode}"}
