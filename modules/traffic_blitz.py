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
import base64
import json
import logging
import os
import random
import re
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
SHOPIFY_VER      = lambda: os.getenv("SHOPIFY_API_VERSION", "2026-04")
GITHUB_TOKEN     = lambda: os.getenv("GITHUB_TOKEN", "")
GITHUB_PAGES_REPO = "bullpowerhubgit/bullpowerhubgit.github.io"
DEVTO_KEY        = lambda: os.getenv("DEVTO_API_KEY", "")
DS24_URL = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")
INDEXNOW_KEY     = "bullpowerhubgit"
INDEXNOW_DOMAINS = [
    # Railway backend
    "supermegabot-production.up.railway.app",
    # Shopify store
    "ineedit.com.co",
    # GitHub Pages
    "bullpowerhubgit.github.io",
    # Vercel — alle 50 Projekte
    "shopify-automation-api.vercel.app",
    "bullpower-hub.vercel.app",
    "shopify-acquisition-engine.vercel.app",
    "shopify-suite.vercel.app",
    "lead-capture.vercel.app",
    "gumroad-discord.vercel.app",
    "launcher.vercel.app",
    "telegram-bot.vercel.app",
    "cognitive-symphony.vercel.app",
    "creatorstudio-pro.vercel.app",
    "creatorai-ultra.vercel.app",
    "digistore24-suite.vercel.app",
    "shopify-brutal-tuning.vercel.app",
    "autoincome-ai.vercel.app",
    "bullpower-ai.vercel.app",
    "master-dashboard.vercel.app",
    "digistore24-automation-suite.vercel.app",
    "autoincome-aii.vercel.app",
    "monetization-hub.vercel.app",
    "steuercockpit.vercel.app",
    "rudibot.vercel.app",
    "digifabrikos.vercel.app",
    "digistore24-automation4.vercel.app",
    "aiitec-system.vercel.app",
    "aiitec-backend.vercel.app",
    "digistore24-automation.vercel.app",
    "digifabrik.vercel.app",
    "digifabrikk.vercel.app",
    "gistore.vercel.app",
    "etsy-gumroad.vercel.app",
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
    """Generate + publish a Shopify blog post — delegates to shopify_max_tuner."""
    domain = SHOPIFY_DOMAIN()
    token  = SHOPIFY_TOKEN()
    if not domain or not token:
        return {"ok": False, "error": "Shopify not configured"}
    try:
        from modules.shopify_max_tuner import auto_publish_seo_blog
        result = await auto_publish_seo_blog()
        if result.get("published"):
            return {"ok": True, **result}
        # Fallback to GitHub Pages on any Shopify failure
        log.info("Shopify blog unavailable (%s) — GitHub Pages fallback", result.get("error","?"))
        return await create_github_seo_post(topic)
    except Exception as exc:
        log.warning("Shopify blog error (%s) — GitHub Pages fallback", exc)
        return await create_github_seo_post(topic)

async def _create_shopify_blog_post_direct(topic: str | None = None) -> dict:
    """Direct Shopify blog post (original implementation — kept as backup)."""
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
                log.warning("Shopify blog unavailable (write_content scope missing) — falling back to GitHub Pages")
                return await create_github_seo_post(topic)

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
                async with s.post(endpoint, json=payload) as r:
                    await r.read()
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
                    async with s.post(ep, json=payload) as r:
                        await r.read()
            submitted += len(url_list)
        except Exception as _e:
            log.debug("skipped: %s", _e)
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


# ── GitHub Pages Blog Publisher ───────────────────────────────────────────────

async def post_github_pages(title: str, body_md: str, tags: list[str] | None = None) -> dict:
    """Push a new HTML blog post to bullpowerhubgit.github.io via GitHub API."""
    token = GITHUB_TOKEN()
    if not token:
        return {"ok": False, "error": "GITHUB_TOKEN missing"}

    now   = datetime.now(timezone.utc)
    date  = now.strftime("%Y-%m-%d")
    ts    = now.strftime("%H%M%S")
    slug  = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")
    path  = f"blog/{date}-{ts}-{slug}.html"
    tag_str = ", ".join(tags or ["KI", "E-Commerce", "Automatisierung"])
    # Convert markdown-ish to HTML
    body_html = body_md.replace("\n## ", "\n<h2>").replace("\n### ", "\n<h3>")
    body_html = re.sub(r"<h2>([^\n]+)", r"<h2>\1</h2>", body_html)
    body_html = re.sub(r"<h3>([^\n]+)", r"<h3>\1</h3>", body_html)
    body_html = "\n".join(
        f"<p>{l}</p>" if l and not l.startswith("<") else l
        for l in body_html.split("\n")
    )
    content = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="KI & E-Commerce Automatisierung — {tag_str}">
<meta name="keywords" content="{tag_str}">
<link rel="stylesheet" href="/style.css">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"{title}","datePublished":"{date}","author":{{"@type":"Person","name":"Rudolf Sarkany"}}}}</script>
</head>
<body>
<article>
<h1>{title}</h1>
<p><time datetime="{date}">{date}</time> | Tags: {tag_str}</p>
{body_html}
</article>
<footer><p><a href="/">Zurück zur Startseite</a> | <a href="{DS24_URL}">KI Income System</a></p></footer>
</body>
</html>"""
    encoded = base64.b64encode(content.encode()).decode()
    try:
        gh_headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            # Check if file already exists (get SHA for update)
            sha = None
            async with s.get(
                f"https://api.github.com/repos/{GITHUB_PAGES_REPO}/contents/{path}",
                headers=gh_headers,
            ) as chk:
                if chk.status == 200:
                    sha = (await chk.json()).get("sha")
            payload = {"message": f"blog: {title[:72]}", "content": encoded}
            if sha:
                payload["sha"] = sha
            async with s.put(
                f"https://api.github.com/repos/{GITHUB_PAGES_REPO}/contents/{path}",
                headers=gh_headers,
                json=payload,
            ) as r:
                if r.status in (200, 201):
                    url = f"https://bullpowerhubgit.github.io/{path}"
                    await _indexnow_ping(url)
                    log.info("GitHub Pages: published '%s'", title)
                    return {"ok": True, "title": title, "url": url, "path": path}
                body = await r.text()
                log.warning("GitHub Pages %s: %s", r.status, body[:120])
                return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as exc:
        log.error("GitHub Pages error: %s", exc)
        return {"ok": False, "error": str(exc)}


async def create_github_seo_post(topic: str | None = None) -> dict:
    """Generate AI article and publish to GitHub Pages."""
    topic = topic or random.choice(SEO_TOPICS)
    prompt = f"""Erstelle einen SEO-optimierten Blog-Artikel auf Deutsch:

Thema: "{topic}"

Anforderungen:
- 600-800 Wörter in Markdown
- H2/H3-Überschriften (## / ###)
- 2 natürliche Links zu: {DS24_URL}
- FAQ-Sektion (3 Fragen) am Ende

Antworte NUR mit JSON:
{{"title": "SEO Titel max 65 Zeichen", "body": "vollständiger Markdown-Artikel", "tags": ["tag1","tag2","tag3"]}}"""

    raw = await ai_complete(prompt, max_tokens=1500)
    try:
        s, e = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[s:e])
    except Exception:
        data = {
            "title": f"{topic} — Anleitung 2026",
            "body": f"## {topic}\n\nErfahre wie du mit KI-Tools dein Online-Business automatisierst.\n\n[Jetzt starten]({DS24_URL})\n\n## FAQ\n\n**Was ist das?**\nEin System für automatische Online-Einnahmen.\n\n**Wie starte ich?**\nRegistriere dich und folge der Anleitung.",
            "tags": ["KI", "E-Commerce", "Automatisierung"],
        }
    return await post_github_pages(data["title"], data["body"], data.get("tags"))


# ── DEV.to Publisher ──────────────────────────────────────────────────────────

async def post_devto(title: str, body_md: str, tags: list[str] | None = None) -> dict:
    """Publish article to DEV.to (needs DEVTO_API_KEY)."""
    key = DEVTO_KEY()
    if not key or key.startswith("MISSING"):
        return {"ok": False, "error": "DEVTO_API_KEY not set"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                "https://dev.to/api/articles",
                headers={"api-key": key, "Content-Type": "application/json"},
                json={"article": {
                    "title": title,
                    "body_markdown": body_md,
                    "published": True,
                    "tags": (tags or ["ai", "ecommerce", "automation"])[:4],
                }},
            ) as r:
                if r.status in (200, 201):
                    d = await r.json(content_type=None)
                    url = d.get("url", "")
                    await _indexnow_ping(url)
                    log.info("DEV.to published: %s", url)
                    return {"ok": True, "url": url, "title": title}
                body = await r.text()
                log.warning("DEV.to %s: %s", r.status, body[:120])
                return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


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
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
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

    task_defs = [
        ("linkedin",  lambda: linkedin_ai_post(topic)),
        ("shopify",   lambda: create_shopify_blog_post(topic)),
        ("indexnow",  lambda: indexnow_blast()),
        ("telegram",  lambda: post_telegram_seo(topic)),
    ]

    for name, coro_fn in task_defs:
        try:
            results[name] = await coro_fn()
        except Exception as exc:
            results[name] = {"ok": False, "error": str(exc)}

    ok_count = sum(1 for v in results.values() if (v if isinstance(v, bool) else v.get("ok", False)))
    log.info("Traffic Blitz: %d/%d channels OK | topic: %s", ok_count, len(task_defs), topic)
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
    """Publish 3 SEO blog posts — Shopify if scope available, GitHub Pages as fallback."""
    results = []
    topics  = random.sample(SEO_TOPICS, min(3, len(SEO_TOPICS)))
    for t in topics:
        r = await create_shopify_blog_post(t)  # auto-falls back to GitHub Pages
        results.append(r)
        await asyncio.sleep(5)
    # Always also push 1 dedicated GitHub Pages + 1 DEV.to post
    gh = await create_github_seo_post(random.choice(SEO_TOPICS))
    results.append(gh)
    await indexnow_blast()
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "published": ok, "topics": topics}
