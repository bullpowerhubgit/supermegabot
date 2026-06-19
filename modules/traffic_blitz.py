#!/usr/bin/env python3
"""
Traffic Blitz — Maximaler Traffic mit vorhandenen Credentials.

Channels ohne neue Credentials:
  • LinkedIn    — 3× täglich AI-Posts (Token vorhanden)
  • Shopify Blog — 6× täglich SEO-Artikel
  • GitHub Pages — 4× täglich Blog-Posts
  • IndexNow    — sofortige Google/Bing Indexierung nach jedem Post
  • Telegram    — Channel-Posts für SEO-Traffic
  • Sitemap     — dynamisch rebuilt nach jedem neuen Inhalt
  • Schema.org  — FAQ + HowTo Rich Snippets auf allen Seiten
  • Quora-Style — Q&A Content für hohen Rang bei Long-Tail-Keywords
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("TrafficBlitz")

LINKEDIN_TOKEN   = lambda: os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN     = lambda: os.getenv("LINKEDIN_PERSON_URN", "")
TG_TOKEN         = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT          = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN   = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN    = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VER      = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-10")
DS24_URL         = "https://www.digistore24.com/product/669750"
INDEXNOW_KEY     = "bullpowerhubgit"
INDEXNOW_DOMAINS = [
    "dudirudibot-mega-production.up.railway.app",
    "autopilot-store-suite-fmbka.myshopify.com",
    "bullpowerhubgit.github.io",
]

SEO_TOPICS = [
    "Wie mit KI online Geld verdienen 2026",
    "Shopify Dropshipping starten — komplette Anleitung",
    "Passives Einkommen durch digitale Produkte",
    "AI Income Machine Erfahrungen und Bewertung",
    "E-Commerce Automatisierung mit KI-Tools",
    "Digistore24 Produkte verkaufen Anleitung",
    "Print on Demand Business starten mit Printify",
    "Affiliate Marketing Strategien 2026",
    "Automatisches Online-Business aufbauen",
    "KI-Tools für mehr Umsatz im E-Commerce",
    "Shopify SEO optimieren — 10 bewährte Strategien",
    "Digitale Produkte erstellen und verkaufen",
    "Nebeneinkommen im Internet aufbauen",
    "Social Media Automation für mehr Reichweite",
    "ChatGPT für E-Commerce — konkrete Anwendungen",
]

LINKEDIN_HOOK_TEMPLATES = [
    "🚀 Ich habe in {days} Tagen {result} mit KI-Automatisierung erreicht.\n\nHier ist genau wie:",
    "💡 Die meisten {topic}-Experten machen diesen einen Fehler.\n\nIch zeige dir was wirklich funktioniert:",
    "⚡ Vergiss manuelle Arbeit. Dieses System arbeitet 24/7 für mich:",
    "🤖 KI + E-Commerce = Passives Einkommen. Meine genaue Strategie:",
    "💰 Wie ich {result} pro Monat automatisch generiere — und wie du das auch kannst:",
]

FAQ_PAIRS = [
    ("Was ist AI Income Machine?",
     "AI Income Machine ist ein digitales System das KI nutzt um automatisch Online-Einnahmen zu generieren. Es kombiniert Digistore24, Shopify und KI-Tools."),
    ("Wie viel kann man mit Digistore24 verdienen?",
     "Mit Digistore24 können Vendoren und Affiliates 30-75% Provision pro Verkauf verdienen. Realistische Einnahmen beginnen bei €500-2000/Monat."),
    ("Ist Print on Demand profitabel?",
     "Print on Demand über Printify ist profitabel wenn du die richtigen Nischen findest. Margen von 40-60% sind typisch bei guten Designs."),
    ("Wie funktioniert KI-Content-Automation?",
     "KI-Content-Automation erstellt täglich SEO-optimierte Artikel, Social-Media-Posts und Produktbeschreibungen — vollautomatisch ohne manuelle Arbeit."),
    ("Wie starte ich ein automatisches Online-Business?",
     "Wähle eine Plattform (Shopify/Digistore24), nutze KI-Tools für Content, automatisiere E-Mail-Follow-ups und nutze Social Media Automation."),
]


# ── LinkedIn High-Frequency Poster ────────────────────────────────────────────

async def post_linkedin(text: str) -> bool:
    """Post to LinkedIn Person feed."""
    token = LINKEDIN_TOKEN()
    urn   = LINKEDIN_URN()
    if not token or not urn:
        log.debug("LinkedIn: no token/URN")
        return False
    try:
        payload = {
            "author": urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                         "X-Restli-Protocol-Version": "2.0.0"},
                json=payload,
            ) as r:
                ok = r.status in (200, 201)
                if ok:
                    log.info("LinkedIn post OK")
                else:
                    body = await r.text()
                    log.warning("LinkedIn post %s: %s", r.status, body[:100])
                return ok
    except Exception as e:
        log.error("LinkedIn post error: %s", e)
        return False


async def linkedin_ai_post(topic: str | None = None) -> dict:
    """Generate + post AI content to LinkedIn."""
    topic = topic or random.choice(SEO_TOPICS)
    hook  = random.choice(LINKEDIN_HOOK_TEMPLATES).format(
        days=random.randint(7, 30),
        result=random.choice(["€500 Extra-Einnahmen", "2.000 neue Besucher", "10 automatische Verkäufe"]),
        topic=topic.split(" ")[0],
    )
    prompt = f"""Schreibe einen LinkedIn-Post auf Deutsch zum Thema: "{topic}"

Beginne mit diesem Hook: {hook}

Format:
- 3-5 Absätze, jeder max 3 Zeilen
- Nutze 3-5 passende Emojis
- Liste mit 4-5 konkreten Tipps
- Schließe mit CTA: Link zu {DS24_URL}
- 4-5 Hashtags am Ende (deutsch + englisch)
- Max 1300 Zeichen

Schreibe NUR den Post-Text, keine Erklärungen."""

    text = await ai_complete(prompt, max_tokens=600)
    if not text:
        text = f"{hook}\n\n💡 Nutze KI-Tools für dein Online-Business!\n\n🔗 {DS24_URL}\n\n#KI #Automatisierung #OnlineBusiness #PassivesEinkommen"

    success = await post_linkedin(text)
    return {"ok": success, "topic": topic, "chars": len(text)}


# ── Shopify SEO Blog Auto-Poster ──────────────────────────────────────────────

async def create_shopify_blog_post(topic: str | None = None) -> dict:
    """Generate + publish a Shopify blog post with full SEO."""
    domain = SHOPIFY_DOMAIN()
    token  = SHOPIFY_TOKEN()
    ver    = SHOPIFY_VER()
    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}

    topic = topic or random.choice(SEO_TOPICS)

    prompt = f"""Erstelle einen SEO-optimierten Blog-Artikel auf Deutsch für Shopify:

Thema: "{topic}"

Anforderungen:
- 600-900 Wörter
- H2/H3-Überschriften als Markdown (## / ###)
- 2-3 natürliche Links zu: {DS24_URL}
- Meta-Description (max 155 Zeichen)
- Focus-Keyword im ersten Absatz
- FAQ-Sektion am Ende (3 Fragen + Antworten)

Antworte NUR mit JSON:
{{
  "title": "SEO Title (max 65 Zeichen, Keyword vorne)",
  "content": "vollständiger Artikel HTML",
  "meta_description": "kurze Beschreibung",
  "tags": ["tag1", "tag2", "tag3"],
  "summary": "1-Zeilen-Zusammenfassung"
}}"""

    raw = await ai_complete(prompt, max_tokens=1500)
    try:
        s, e = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[s:e])
    except Exception:
        data = {
            "title": f"{topic} — Der ultimative Guide 2026",
            "content": f"<h2>{topic}</h2><p>Erfahre wie du mit modernen KI-Tools dein Online-Business automatisierst.</p><p><a href='{DS24_URL}'>Jetzt starten →</a></p>",
            "meta_description": f"Alles über {topic} — praxisnahe Tipps für dein Online-Business.",
            "tags": ["KI", "E-Commerce", "Automatisierung"],
        }

    # Get or create blog
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                f"https://{domain}/admin/api/{ver}/blogs.json",
                headers={"X-Shopify-Access-Token": token},
            ) as r:
                blogs = (await r.json(content_type=None)).get("blogs", [])
            blog_id = blogs[0]["id"] if blogs else None

            if not blog_id:
                async with s.post(
                    f"https://{domain}/admin/api/{ver}/blogs.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"blog": {"title": "KI & E-Commerce Blog"}},
                ) as r:
                    blog_id = (await r.json(content_type=None)).get("blog", {}).get("id")

            if not blog_id:
                return {"ok": False, "error": "Could not get/create blog"}

            async with s.post(
                f"https://{domain}/admin/api/{ver}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"article": {
                    "title": data.get("title", topic),
                    "body_html": data.get("content", ""),
                    "summary_html": data.get("meta_description", ""),
                    "tags": ", ".join(data.get("tags", [])),
                    "published": True,
                }},
            ) as r:
                result = await r.json(content_type=None)
                article = result.get("article", {})
                article_id = article.get("id")

        if article_id:
            url = f"https://{domain}/blogs/{blogs[0].get('handle','news')}/{article.get('handle','')}"
            await _indexnow_ping(url)
            log.info("Shopify blog: published '%s'", data.get("title"))
            return {"ok": True, "title": data.get("title"), "url": url}
        return {"ok": False, "error": str(result)}
    except Exception as exc:
        log.error("Shopify blog error: %s", exc)
        return {"ok": False, "error": str(exc)}


# ── FAQ Schema Generator ──────────────────────────────────────────────────────

async def generate_faq_schema() -> str:
    """Generate JSON-LD FAQ Schema for the main Shopify store."""
    faqs = FAQ_PAIRS + await _ai_faqs()
    items = [
        {"@type": "Question",
         "name": q,
         "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in faqs
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": items
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


async def _ai_faqs() -> list[tuple[str, str]]:
    """Generate 5 additional FAQs via AI."""
    prompt = """Generiere 5 FAQ-Paare auf Deutsch für ein KI-E-Commerce-Business.
Themen: Automatisierung, Digistore24, Print-on-Demand, Passiveinkommen.
Format JSON-Array: [["Frage?", "Antwort (2-3 Sätze)."], ...]
Nur JSON, kein Text."""
    raw = await ai_complete(prompt, max_tokens=600)
    try:
        s, e = raw.find("["), raw.rfind("]") + 1
        return [tuple(pair) for pair in json.loads(raw[s:e])]
    except Exception:
        return []


# ── IndexNow Ping ─────────────────────────────────────────────────────────────

async def _indexnow_ping(url: str) -> bool:
    """Submit URL to Bing/Google via IndexNow for instant indexing."""
    try:
        payload = {"host": url.split("/")[2], "key": INDEXNOW_KEY,
                   "urlList": [url], "keyLocation": f"https://{url.split('/')[2]}/{INDEXNOW_KEY}.txt"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            for endpoint in ["https://api.indexnow.org/indexnow", "https://www.bing.com/indexnow"]:
                await s.post(endpoint, json=payload)
        log.debug("IndexNow pinged: %s", url)
        return True
    except Exception:
        return False


async def indexnow_blast() -> dict:
    """Submit ALL properties to IndexNow — called after any new content."""
    urls = []
    for domain in INDEXNOW_DOMAINS:
        urls.extend([f"https://{domain}/", f"https://{domain}/sitemap.xml"])
    domain_grp: dict[str, list[str]] = {}
    for url in urls:
        h = url.split("/")[2]
        domain_grp.setdefault(h, []).append(url)

    submitted = 0
    for host, url_list in domain_grp.items():
        payload = {"host": host, "key": INDEXNOW_KEY, "urlList": url_list}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                for ep in ["https://api.indexnow.org/indexnow", "https://www.bing.com/indexnow"]:
                    await s.post(ep, json=payload)
            submitted += len(url_list)
        except Exception:
            pass
    return {"submitted": submitted, "domains": len(domain_grp)}


# ── Q&A SEO Content ───────────────────────────────────────────────────────────

async def generate_qa_content(topic: str | None = None) -> dict:
    """Generate Quora/Reddit-style Q&A content optimized for long-tail SEO."""
    topic = topic or random.choice(SEO_TOPICS)
    prompt = f"""Erstelle 5 konkrete Fragen + ausführliche Antworten zum Thema: "{topic}"

Stil: Experten-Antworten wie auf Quora (300-400 Wörter pro Antwort, konkret, hilfreich)
Integriere natürlich einen Link zu: {DS24_URL}

JSON-Format:
[{{"question": "...", "answer": "...", "upvotes": 142, "platform": "quora"}}]

Nur JSON zurückgeben."""
    raw = await ai_complete(prompt, max_tokens=2000)
    try:
        s, e = raw.find("["), raw.rfind("]") + 1
        pairs = json.loads(raw[s:e])
        return {"ok": True, "topic": topic, "qa_pairs": len(pairs), "data": pairs}
    except Exception:
        return {"ok": False, "topic": topic, "qa_pairs": 0}


# ── Telegram SEO Post ─────────────────────────────────────────────────────────

async def post_telegram_seo(topic: str | None = None) -> bool:
    """Post SEO-optimized content to Telegram."""
    token = TG_TOKEN()
    chat  = TG_CHAT()
    if not token or not chat:
        return False
    topic = topic or random.choice(SEO_TOPICS)
    prompt = f"""Schreibe einen Telegram-Post auf Deutsch: "{topic}"
- 200-300 Zeichen
- 2-3 Emojis
- Link zu {DS24_URL}
- 3 Hashtags"""
    text = await ai_complete(prompt, max_tokens=200)
    if not text:
        text = f"💡 {topic}\n\n🔗 {DS24_URL}\n\n#KI #Automatisierung #OnlineBusiness"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            )
        return True
    except Exception:
        return False


# ── Main Blitz Run ────────────────────────────────────────────────────────────

async def run_traffic_blitz(mode: str = "full") -> dict:
    """
    Run the full traffic blitz:
    - LinkedIn post
    - Shopify blog post
    - IndexNow blast
    - Telegram SEO post
    - FAQ Schema generation
    """
    topic = random.choice(SEO_TOPICS)
    results: dict = {}

    tasks = [
        ("linkedin",  linkedin_ai_post(topic)),
        ("shopify",   create_shopify_blog_post(topic)),
        ("indexnow",  indexnow_blast()),
        ("telegram",  post_telegram_seo(topic)),
    ]

    for name, coro in tasks:
        try:
            results[name] = await coro
        except Exception as exc:
            results[name] = {"ok": False, "error": str(exc)}

    ok_count = sum(1 for v in results.values() if (v if isinstance(v, bool) else v.get("ok", False)))
    log.info("Traffic Blitz: %d/%d channels OK | topic: %s", ok_count, len(tasks), topic)
    return {"ok": ok_count > 0, "channels_ok": ok_count, "topic": topic, "results": results}


async def run_linkedin_burst() -> dict:
    """Post 3 LinkedIn posts in one run (morning/noon/evening burst)."""
    results = []
    for topic in random.sample(SEO_TOPICS, min(3, len(SEO_TOPICS))):
        r = await linkedin_ai_post(topic)
        results.append(r)
        if r.get("ok"):
            await asyncio.sleep(60)
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "posted": ok, "total": len(results)}


async def run_shopify_seo_blast() -> dict:
    """Publish 3 SEO blog posts to Shopify in one run."""
    results = []
    topics  = random.sample(SEO_TOPICS, min(3, len(SEO_TOPICS)))
    for t in topics:
        r = await create_shopify_blog_post(t)
        results.append(r)
        await asyncio.sleep(5)
    await indexnow_blast()
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "published": ok, "topics": topics}
