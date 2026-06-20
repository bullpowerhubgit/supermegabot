"""
Ultra SEO Arsenal — Maximum Traffic & Indexing Power.
Submits all BullPower properties to 5 search engines via IndexNow,
generates master sitemap covering all 14 Railway services,
auto-posts parasite SEO content to high-DA sites,
pings every time new content goes live.
"""
import asyncio
import json
import logging
import os
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("UltraSEOArsenal")

ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")

# All BullPower properties — 14 Railway services + GitHub Pages
ALL_PROPERTIES = {
    "supermegabot":          "https://dudirudibot-mega-production.up.railway.app",
    "meta_social":           "https://meta-social-engine-production.up.railway.app",
    "seo_turbo":             "https://seo-turbo-tools-production.up.railway.app",
    "freelance_gig":         "https://freelance-gig-engine-production.up.railway.app",
    "visual_content":        "https://visual-content-engine-production.up.railway.app",
    "adposter":              "https://adposter-engine-production.up.railway.app",
    "icomeauto":             "https://icomeauto-saas-production.up.railway.app",
    "creatorai_ultra":       "https://creatorai-ultra-production.up.railway.app",
    "revenue_hub":           "https://revenue-hub-notifications-production.up.railway.app",
    "shopify_automaton":     "https://shopify-automaton-suite-production-e405.up.railway.app",
    "steuercockpit":         "https://steuercockpit-production-44c9.up.railway.app",
    "seo_traffic":           "https://seo-traffic-engine-production.up.railway.app",
    "social_traffic":        "https://social-traffic-engine-production.up.railway.app",
    "shopify_acquisition":   "https://shopify-acquisition-engine-production.up.railway.app",
    # GitHub Pages
    "lead_capture":          "https://bullpowerhubgit.github.io/bullpower-lead",
    "shopify_suite_gh":      "https://bullpowerhubgit.github.io/shopify-suite-landing",
    "brutal_tuning_gh":      "https://bullpowerhubgit.github.io/shopify-brutal-tuning-landing",
    "legal":                 "https://bullpowerhubgit.github.io/bullpower-legal",
}

# High-value pages for each property
PROPERTY_PATHS = {
    "supermegabot":        ["/", "/health", "/api/offers"],
    "icomeauto":           ["/", "/pricing"],
    "creatorai_ultra":     ["/", "/pricing"],
    "steuercockpit":       ["/", "/pricing"],
    "shopify_acquisition": ["/", "/billing/plans"],
    "shopify_automaton":   ["/", "/pricing"],
    "lead_capture":        ["/", "/index.html"],
    "shopify_suite_gh":    ["/", "/index.html"],
    "brutal_tuning_gh":    ["/", "/index.html"],
}

# IndexNow key (same across all properties — Bing-based, picked up by Yandex, Seznam, Naver)
INDEXNOW_KEY  = "bullpower2026indexnow"
INDEXNOW_ENDPOINTS = [
    "https://api.indexnow.org/indexnow",
    "https://www.bing.com/indexnow",
    "https://yandex.com/indexnow",
]


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def _claude(prompt: str, max_tokens: int = 800) -> str:
    try:
        from modules.ai_client import ai_complete
        r = await ai_complete(prompt, max_tokens=1200)
        return r if r else ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ai_complete fallback: {e}")
        return ""

def generate_master_sitemap() -> str:
    """Generate XML sitemap covering all BullPower properties."""
    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for prop_key, base_url in ALL_PROPERTIES.items():
        paths = PROPERTY_PATHS.get(prop_key, ["/"])
        for path in paths:
            url_el = ET.SubElement(root, "url")
            ET.SubElement(url_el, "loc").text = base_url.rstrip("/") + path
            ET.SubElement(url_el, "lastmod").text = now
            ET.SubElement(url_el, "changefreq").text = "daily"
            ET.SubElement(url_el, "priority").text = "0.9" if path == "/" else "0.7"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


async def submit_indexnow(urls: list[str]) -> dict:
    """Submit URLs to IndexNow — instant indexing on Bing, Yandex, Seznam, Naver."""
    if not urls:
        return {"submitted": 0}

    host = "dudirudibot-mega-production.up.railway.app"
    payload = {
        "host": host,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{host}/{INDEXNOW_KEY}.txt",
        "urlList": urls[:100],  # IndexNow limit
    }

    results = {}
    async with aiohttp.ClientSession() as s:
        for ep in INDEXNOW_ENDPOINTS:
            try:
                r = await s.post(
                    ep,
                    json=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
                results[ep] = r.status
            except Exception as e:
                results[ep] = str(e)

    submitted = sum(1 for v in results.values() if v in (200, 202))
    log.info(f"IndexNow: {submitted}/{len(INDEXNOW_ENDPOINTS)} endpoints accepted {len(urls)} URLs")
    return {"submitted": submitted, "urls": len(urls), "results": results}


async def submit_all_properties_to_indexnow() -> dict:
    """Submit every BullPower property page to IndexNow."""
    all_urls = []
    for prop_key, base_url in ALL_PROPERTIES.items():
        paths = PROPERTY_PATHS.get(prop_key, ["/"])
        for path in paths:
            all_urls.append(base_url.rstrip("/") + path)

    result = await submit_indexnow(all_urls)
    log.info(f"Submitted {len(all_urls)} BullPower URLs to IndexNow")
    return {**result, "total_urls": len(all_urls)}


async def ping_search_engines_sitemap(sitemap_url: str = "") -> dict:
    """Ping Google + Bing with sitemap URL."""
    if not sitemap_url:
        sitemap_url = f"https://dudirudibot-mega-production.up.railway.app/sitemap.xml"

    endpoints = [
        f"https://www.google.com/ping?sitemap={sitemap_url}",
        f"https://www.bing.com/ping?sitemap={sitemap_url}",
    ]
    if SHOPIFY_DOMAIN:
        shopify_sitemap = f"https://{SHOPIFY_DOMAIN}/sitemap.xml"
        endpoints += [
            f"https://www.google.com/ping?sitemap={shopify_sitemap}",
            f"https://www.bing.com/ping?sitemap={shopify_sitemap}",
        ]

    results = {}
    async with aiohttp.ClientSession() as s:
        for ep in endpoints:
            try:
                r = await s.get(ep, timeout=aiohttp.ClientTimeout(total=10))
                results[ep.split("?")[0]] = r.status
            except Exception as e:
                results[ep.split("?")[0]] = str(e)

    log.info(f"Sitemap ping results: {results}")
    return results


async def generate_parasite_seo_content(topic: str = "") -> dict:
    """Use Claude to generate high-DA parasite SEO content for Reddit/Medium/LinkedIn."""
    if not topic:
        topics = [
            "Shopify Automatisierung mit KI 2026",
            "Passives Einkommen Online Business KI",
            "E-Commerce Automatisierung Deutschland",
            "KI Tools für Online-Shop-Betreiber",
            "Steueroptimierung Selbstständige KI",
            "Content Creator KI Tools kostenlos",
            "Digistore24 Produkte verkaufen automatisch",
        ]
        topic = random.choice(topics)

    prompt = f"""Schreibe einen 300-Wort Fachartikel auf Deutsch über: "{topic}"

Format: Markdown-kompatibler Text
- Beginne mit einer starken Hook-Aussage
- 3 konkrete Tipps/Punkte
- Natürliche Keywords: KI, Automatisierung, Online Business, BullPower Hub
- Ende mit CTA: "Mehr erfahren: https://dudirudibot-mega-production.up.railway.app/"
- Kein Clickbait, echte Informationen
- Tone: professionell aber zugänglich

Nur den Artikeltext, keine Metadaten."""

    content = await _claude(prompt, max_tokens=600)
    title_prompt = f'Erstelle einen SEO-optimierten Titel (max 60 Zeichen) für diesen Artikel:\n{content[:200]}\nNur den Titel, nichts anderes.'
    title = await _claude(title_prompt, max_tokens=80)

    return {"topic": topic, "title": title.strip(), "content": content.strip()}


async def post_to_medium_rss(title: str, content: str) -> dict:
    """Post article via Medium API (if MEDIUM_TOKEN set)."""
    medium_token = os.getenv("MEDIUM_TOKEN", "")
    medium_user = os.getenv("MEDIUM_USER_ID", "")
    if not medium_token or not medium_user:
        return {"status": "skipped", "reason": "MEDIUM_TOKEN not set"}

    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"https://api.medium.com/v1/users/{medium_user}/posts",
                headers={
                    "Authorization": f"Bearer {medium_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": title,
                    "contentFormat": "markdown",
                    "content": content,
                    "publishStatus": "public",
                    "tags": ["KI", "Online Business", "Automatisierung", "E-Commerce"],
                    "canonicalUrl": "https://dudirudibot-mega-production.up.railway.app/",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            )
            data = await r.json()
            url = data.get("data", {}).get("url", "")
            return {"status": "posted", "url": url}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def generate_and_submit_indexnow_key() -> str:
    """Serve the IndexNow key verification file content."""
    return INDEXNOW_KEY


async def run_ultra_seo_cycle() -> dict:
    """Full Ultra SEO cycle — sitemap ping + IndexNow + parasite content."""
    results = {}

    # 1. Submit all properties to IndexNow
    log.info("Ultra SEO: submitting all properties to IndexNow...")
    indexnow_result = await submit_all_properties_to_indexnow()
    results["indexnow"] = indexnow_result

    # 2. Ping Google + Bing with sitemaps
    log.info("Ultra SEO: pinging search engines with sitemaps...")
    ping_result = await ping_search_engines_sitemap()
    results["sitemap_ping"] = ping_result

    # 3. Generate parasite SEO content
    log.info("Ultra SEO: generating parasite SEO content...")
    parasite = await generate_parasite_seo_content()
    results["parasite_content"] = {"topic": parasite["topic"], "title": parasite["title"]}

    # 4. Try to post to Medium
    if parasite["content"]:
        medium = await post_to_medium_rss(parasite["title"], parasite["content"])
        results["medium"] = medium

    total_urls = indexnow_result.get("total_urls", 0)
    indexed = indexnow_result.get("submitted", 0)

    summary = (
        f"🚀 *Ultra SEO Arsenal Complete*\n"
        f"• IndexNow: {total_urls} URLs → {indexed}/3 engines\n"
        f"• Sitemap: Google + Bing gepingt\n"
        f"• Content: \"{parasite['title'][:40]}...\"\n"
        f"• Zeit: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )
    await _tg(summary)
    log.info(f"Ultra SEO cycle complete: {total_urls} URLs submitted")

    return results


async def instant_index_new_content(url: str, description: str = "") -> dict:
    """Called immediately after any new content is published — instant indexing."""
    log.info(f"Instant indexing: {url}")

    # Submit to IndexNow
    result = await submit_indexnow([url])

    # Also ping Google/Bing
    sitemap = f"https://dudirudibot-mega-production.up.railway.app/sitemap.xml"
    async with aiohttp.ClientSession() as s:
        for ping_url in [
            f"https://www.google.com/ping?sitemap={sitemap}",
            f"https://www.bing.com/ping?sitemap={sitemap}",
        ]:
            try:
                await s.get(ping_url, timeout=aiohttp.ClientTimeout(total=8))
            except Exception:
                pass

    return {"url": url, "indexnow": result}


async def generate_keyword_clusters(niche: str = "E-Commerce KI Automatisierung") -> list[str]:
    """AI-generated 50+ long-tail keyword clusters for maximum organic reach."""
    prompt = f"""Generiere 50 Long-Tail-Keywords für die Nische: "{niche}"

Format: Eine Liste mit je einem Keyword pro Zeile.
Mix aus:
- Informational: "wie man X macht", "was ist X"
- Commercial: "bestes X Tool", "X kaufen", "X Preis"
- Transactional: "X kostenlos", "X testen", "X anmelden"
- Local: "X Deutschland", "X Österreich"

Nur die Keywords, keine Nummerierung, keine Erklärungen."""

    raw = await _claude(prompt, max_tokens=800)
    keywords = [k.strip() for k in raw.strip().split("\n") if k.strip() and len(k.strip()) > 5]
    log.info(f"Generated {len(keywords)} keyword clusters for: {niche}")
    return keywords[:50]


async def seo_health_check() -> dict:
    """Check all BullPower properties are reachable and returning 200."""
    results = {}
    async with aiohttp.ClientSession() as s:
        for prop_key, base_url in list(ALL_PROPERTIES.items())[:8]:  # check top 8
            try:
                r = await s.get(base_url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True)
                results[prop_key] = r.status
            except Exception as e:
                results[prop_key] = f"error: {e}"

    ok = sum(1 for v in results.values() if v == 200)
    log.info(f"SEO Health: {ok}/{len(results)} properties reachable")
    return {"ok": ok, "total": len(results), "details": results}
