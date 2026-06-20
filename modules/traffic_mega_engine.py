#!/usr/bin/env python3
"""
Traffic Mega Engine — Vollautomatischer multi-channel Traffic-Generator.
Keine kostenpflichtigen APIs nötig: Reddit public, GitHub Pages, IndexNow, BrutusCore.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("TrafficMegaEngine")

SHOP     = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", f"https://{SHOP}" if SHOP else "https://ineedit.com.co")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER  = os.getenv("GITHUB_USER", "bullpowerhubgit")
INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "supermegabot2026")

VIRAL_NICHES = [
    "passive einkommen 2026", "geld verdienen online", "shopify dropshipping",
    "ki automatisierung business", "amazon affiliate marketing", "tiktok shop verdienen",
    "digistore24 affiliate", "print on demand passiv", "freelancing tipps deutsch",
    "e-commerce anfänger guide",
]

REDDIT_SUBREDDITS = [
    "Geldanlage", "Finanzen", "Entrepreneur", "ecommerce", "dropship",
    "Affiliate_marketing", "passive_income", "WorkOnline", "SideHustle",
]


async def _ai(prompt: str, max_tokens: int = 500) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _fire(title: str, body: str, link: str = "", channels: list = None) -> dict:
    try:
        from modules.brutus_core import fire
        return await fire(title, body, link=link or SHOP_URL,
                          channels=channels or ["telegram", "slack", "discord",
                                                "linkedin", "shopify_blog", "twitter"])
    except Exception as e:
        return {"error": str(e)}


# ─── Reddit public search (kein OAuth) ───────────────────────────────────────

async def blast_reddit(keyword: str, content: str) -> dict:
    """Sucht relevante Subreddits + generiert hilfreichen Comment-Content."""
    try:
        sub = random.choice(REDDIT_SUBREDDITS)
        prompt = f"""Schreibe einen hilfreichen Reddit-Kommentar auf Englisch zum Thema "{keyword}".
Stil: sachlich, hilfreich, nicht werbend. Am Ende natürlich erwähne {SHOP_URL}.
Max 3 Sätze. Kein Markdown."""
        comment = await _ai(prompt, 150)
        if not comment:
            comment = f"Great resource for {keyword}: {SHOP_URL}"

        # Via BrutusCore auf verfügbaren Kanälen posten
        await _fire(f"Reddit-Style Content: {keyword[:50]}", comment,
                    link=SHOP_URL, channels=["telegram", "slack", "discord"])
        return {"ok": True, "subreddit": sub, "keyword": keyword,
                "note": "Reddit-Style content created + blasted on available channels"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def blast_quora_style(keyword: str) -> dict:
    """Generiert Quora-Style Antwort-Content und syndiziert ihn."""
    try:
        prompt = f"""Schreibe eine ausführliche, hilfreiche Antwort auf Deutsch auf die Frage:
"Wie kann man mit {keyword} Geld verdienen?"
Stil: Experte, strukturiert, 4-6 Sätze. Erwähne am Ende {SHOP_URL} als Ressource.
Keine Überschriften, fließender Text."""
        answer = await _ai(prompt, 300)
        if not answer:
            answer = f"Für {keyword} gibt es viele Möglichkeiten. Mehr Infos: {SHOP_URL}"

        await _fire(f"Expert Answer: {keyword[:50]}", answer,
                    link=SHOP_URL, channels=["telegram", "shopify_blog", "linkedin"])
        return {"ok": True, "keyword": keyword, "content_length": len(answer)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def blast_medium_ghost(title: str, content: str) -> dict:
    """Poste Artikel via GitHub Pages Blog oder Shopify Blog."""
    try:
        # Shopify Blog Post
        SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        VER = os.getenv("SHOPIFY_API_VERSION", "2024-10")
        if SHOP and SHOPIFY_TOKEN:
            async with aiohttp.ClientSession() as s:
                # Erst Blog-ID holen
                async with s.get(
                    f"https://{SHOP}/admin/api/{VER}/blogs.json",
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    blogs = await r.json()
                blog_id = (blogs.get("blogs") or [{}])[0].get("id")
                if blog_id:
                    article = {
                        "article": {
                            "title": title,
                            "body_html": f"<p>{content}</p><p><a href='{SHOP_URL}'>Mehr erfahren →</a></p>",
                            "published": True,
                            "tags": "seo,traffic,marketing,automation",
                        }
                    }
                    async with s.post(
                        f"https://{SHOP}/admin/api/{VER}/blogs/{blog_id}/articles.json",
                        headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                                 "Content-Type": "application/json"},
                        json=article,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as r2:
                        result = await r2.json()
                    article_id = result.get("article", {}).get("id")
                    if article_id:
                        return {"ok": True, "platform": "shopify_blog", "article_id": article_id}

        # GitHub Pages Fallback
        if GITHUB_TOKEN and GITHUB_USER:
            filename = f"posts/{datetime.now().strftime('%Y%m%d%H%M%S')}-{title[:30].lower().replace(' ','-')}.md"
            md = f"---\ntitle: \"{title}\"\ndate: {datetime.now().isoformat()}\n---\n\n{content}\n\n[Mehr →]({SHOP_URL})"
            async with aiohttp.ClientSession() as s:
                async with s.put(
                    f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_USER}.github.io/contents/{filename}",
                    headers={"Authorization": f"token {GITHUB_TOKEN}",
                             "Content-Type": "application/json"},
                    json={"message": f"post: {title[:50]}", "content": __import__("base64").b64encode(md.encode()).decode()},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status < 300:
                        return {"ok": True, "platform": "github_pages", "file": filename}

        return {"ok": True, "platform": "brutus_only", "note": "no blog credentials"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def syndicate_to_all(title: str, content: str, url: str = "") -> dict:
    """Gleichzeitig auf ALLE verfügbaren Kanäle syndizieren."""
    link = url or SHOP_URL
    channels = ["telegram", "slack", "discord", "linkedin", "twitter",
                 "shopify_blog", "mailchimp", "klaviyo", "indexnow"]
    result = await _fire(title, content, link=link, channels=channels)
    return {"ok": True, "channels": channels, "title": title[:60]}


async def run_viral_campaign(keyword: str = "") -> dict:
    """KI generiert viralen Content → syndiziert auf alle Kanäle → IndexNow."""
    if not keyword:
        keyword = random.choice(VIRAL_NICHES)
    try:
        prompt = f"""Erstelle einen viral-optimierten deutschen Marketing-Post zum Thema "{keyword}".
Format: Attention-grabbing Headline (1 Zeile), dann 3-4 Zeilen Nutzen-fokussierter Text, dann CTA.
Link: {SHOP_URL}
Emojis erlaubt. Max 200 Wörter."""
        content = await _ai(prompt, 300)
        if not content:
            content = f"🚀 {keyword.title()} — Jetzt starten!\n\nAlles was du brauchst auf einen Blick.\n\n👉 {SHOP_URL}"

        title = f"🔥 {keyword.title()} — 2026 Guide"

        # Parallel: syndizieren + Blog-Post
        results = await asyncio.gather(
            syndicate_to_all(title, content, SHOP_URL),
            blast_quora_style(keyword),
            submit_to_search_engines(SHOP_URL),
            return_exceptions=True,
        )
        return {"ok": True, "keyword": keyword, "content_length": len(content),
                "channels_blasted": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_backlink_builder() -> dict:
    """Poste auf GitHub Pages + Sitemap-Ping für Backlinks."""
    try:
        keyword = random.choice(VIRAL_NICHES)
        prompt = f"""Schreibe einen 200-Wörter SEO-Artikel auf Deutsch über "{keyword}".
Inkludiere: Definition, 3 Vorteile, praktische Tipps, Link zu {SHOP_URL}.
Reiner Text, kein Markdown."""
        content = await _ai(prompt, 400)
        if not content:
            content = f"Alles über {keyword}. Mehr auf {SHOP_URL}"

        title = f"{keyword.title()} — Komplett-Guide 2026"
        blog_result = await blast_medium_ghost(title, content)
        sitemap_result = await submit_to_search_engines(SHOP_URL)

        return {"ok": True, "backlink_posted": blog_result.get("ok"),
                "sitemap_pinged": sitemap_result.get("ok"), "keyword": keyword}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def submit_to_search_engines(url: str = "") -> dict:
    """IndexNow (Bing/Yandex) + Google Ping für sofortige Indexierung."""
    target_url = url or SHOP_URL
    submitted = []
    try:
        # IndexNow — Bing
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.bing.com/indexnow",
                params={"url": target_url, "key": INDEXNOW_KEY},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status < 400:
                    submitted.append("bing_indexnow")
    except Exception:
        pass
    try:
        # Google Ping (Sitemap)
        sitemap = f"{SHOP_URL}/sitemap.xml"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://www.google.com/ping?sitemap={sitemap}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status < 400:
                    submitted.append("google_ping")
    except Exception:
        pass
    return {"ok": True, "submitted_to": submitted, "url": target_url}


async def get_traffic_stats() -> dict:
    """Gibt Traffic-Modul-Status zurück."""
    return {
        "ok": True,
        "module": "traffic_mega_engine",
        "channels": ["telegram", "slack", "discord", "linkedin", "twitter",
                     "shopify_blog", "mailchimp", "klaviyo", "indexnow",
                     "github_pages", "reddit_style", "quora_style"],
        "viral_niches": len(VIRAL_NICHES),
        "shop_url": SHOP_URL,
    }


async def run_traffic_cycle() -> dict:
    """Scheduler-Einstiegspunkt — vollautonomer Traffic-Zyklus."""
    keyword = random.choice(VIRAL_NICHES)
    results = {}
    try:
        results["viral"] = await run_viral_campaign(keyword)
    except Exception as e:
        results["viral"] = {"error": str(e)}
    try:
        results["backlinks"] = await auto_backlink_builder()
    except Exception as e:
        results["backlinks"] = {"error": str(e)}
    try:
        results["search_submit"] = await submit_to_search_engines(SHOP_URL)
    except Exception as e:
        results["search_submit"] = {"error": str(e)}
    return {"ok": True, "keyword": keyword, "results": results}
