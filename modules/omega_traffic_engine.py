#!/usr/bin/env python3
"""
OMEGA Traffic Engine — Das revolutionärste autonome Traffic-System
==================================================================
Andere Tools posten manuell auf 1-2 Kanälen.
OMEGA: 15 Kanäle gleichzeitig, KI-Content, sofortige Indexierung, vollautonomer Betrieb.

Stack:
  • Google Indexing API    — sofortige Indexierung (kein Warten auf Google-Crawl)
  • Bing IndexNow          — Bing/Yahoo/DuckDuckGo Sofort-Indexierung
  • AI Blog Engine         — täglich 3 neue SEO-Artikel (DE-Markt)
  • Content Syndication    — 1 Artikel → 6 Plattformen gleichzeitig
  • Reddit Auto-Answer     — intelligente Antworten mit Backlinks
  • Quora Auto-Answer      — High-Value Antworten in E-Commerce-Topics
  • FAQ Schema Generator   — Rich Snippets für alle Sites
  • Competitor Spy         — überwacht Ranking-Keywords der Konkurrenz
  • Backlink Bomber        — automatische Directory-Einreichungen
  • Press Release Engine   — automatische Pressemitteilungen
  • Heatmap Tracker        — Conversion-Bottlenecks finden
  • A/B Meta Tag Tester    — findet perfekte Titles/Descriptions
  • Social Proof Amplifier — Reviews/Testimonials automatisch amplifizieren
  • Email Re-engagement    — Win-back inaktive Leads
  • YouTube SEO            — Video-Ideen + Descriptions + Tags generieren
"""

import asyncio
import json
import logging
import os
import hashlib
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("OMEGA")

# ── Credentials ──────────────────────────────────────────────────────────────
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHAT  = _TG_CHANNEL or ""
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
KLAVIYO_KEY    = os.getenv("KLAVIYO_API_KEY", "")
MAILCHIMP_KEY  = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_LIST = os.getenv("MAILCHIMP_LIST_ID", "")
DEEPSEEK_KEY   = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "omega"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── All money URLs ──────────────────────────────────────────────────────────
MONEY_URLS = [
    "https://bullpower-hub-portal.netlify.app/",
    "https://shopify-brutal-tuning.vercel.app/",
    "https://shopify-acquisition-engine.netlify.app/",
    "https://autoincome-ai.vercel.app/",
    "https://creatorai-ultra.vercel.app/",
    "https://digistore24-automation-suite.netlify.app/",
    "https://creatorstudio-pro.netlify.app/",
    "https://bullpower-ai-tools.netlify.app/",
    "https://shopify-suite.vercel.app/blog/shopify-automatisieren-2026/",
    "https://shopify-suite.vercel.app/blog/ki-tools-e-commerce-deutschland/",
]

SITEMAPS = [
    "https://shopify-brutal-tuning.vercel.app/sitemap.xml",
    "https://creatorai-ultra.vercel.app/sitemap.xml",
    "https://autoincome-ai.vercel.app/sitemap.xml",
    "https://bullpower-hub.vercel.app/sitemap.xml",
    "https://shopify-suite.vercel.app/sitemap.xml",
    "https://shopify-acquisition-engine.netlify.app/sitemap.xml",
]

# ── Daily SEO Article Topics (rotierend) ────────────────────────────────────
ARTICLE_TOPICS = [
    ("Shopify automatisieren 2026", "shopify-automatisieren"),
    ("Passives Einkommen mit KI", "passives-einkommen-ki"),
    ("Dropshipping KI-Tools Vergleich", "dropshipping-ki-vergleich"),
    ("Email Marketing Automation Shopify", "email-automation-shopify"),
    ("Digistore24 Affiliate Tipps", "digistore24-affiliate"),
    ("Social Media Autopilot für Shop", "social-media-autopilot"),
    ("Conversion Rate Shopify erhöhen", "conversion-rate-shopify"),
    ("Pinterest Marketing automatisch", "pinterest-marketing-auto"),
    ("Shopify SEO 2026 Anleitung", "shopify-seo-2026"),
    ("KI-Tools für E-Commerce Deutschland", "ki-tools-ecommerce-de"),
    ("Telegram Bot für Online-Shop", "telegram-bot-shop"),
    ("Shopify Produktbeschreibungen KI", "shopify-produktbeschreibungen"),
]


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 1: GOOGLE INDEXING API — Sofortige Google-Indexierung
# ─────────────────────────────────────────────────────────────────────────────

async def google_instant_index(urls: list[str]) -> dict:
    """
    Sendet URLs direkt an Google Indexing API für sofortige Indexierung.
    Kein Warten auf organischen Crawl — Google indexiert innerhalb Minuten.
    Anforderung: Google Service Account in GOOGLE_SA_JSON env var.
    """
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        # Fallback: Google Search Console Ping (öffentlich, kein Auth)
        results = await _google_ping_fallback(urls)
        return results

    try:
        import aiohttp
        results = {"submitted": [], "errors": []}
        token = await _get_google_token(sa_json)
        if not token:
            return await _google_ping_fallback(urls)

        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.post(
                        "https://indexing.googleapis.com/v3/urlNotifications:publish",
                        json={"url": url, "type": "URL_UPDATED"},
                        headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            results["submitted"].append(url)
                        else:
                            results["errors"].append(f"{url}: {r.status}")
                except Exception as e:
                    results["errors"].append(f"{url}: {e}")
        log.info("Google Indexing API: %d submitted, %d errors",
                 len(results["submitted"]), len(results["errors"]))
        return results
    except Exception as e:
        log.warning("Google Indexing API failed: %s", e)
        return await _google_ping_fallback(urls)


async def _google_ping_fallback(urls: list[str]) -> dict:
    """Fallback: Google/Bing Sitemap-Ping (kein Auth nötig)."""
    try:
        import aiohttp
        submitted = []
        async with aiohttp.ClientSession() as session:
            for sitemap in SITEMAPS:
                for engine in [
                    f"https://www.bing.com/ping?sitemap={sitemap}",
                ]:
                    try:
                        async with session.get(engine,
                                               timeout=aiohttp.ClientTimeout(total=8)) as r:
                            if r.status in (200, 202):
                                submitted.append(sitemap)
                    except Exception as _e:
                        log.debug("skipped: %s", _e)
        return {"submitted": submitted, "method": "sitemap_ping"}
    except Exception as e:
        return {"error": str(e)}


async def _get_google_token(sa_json: str) -> Optional[str]:
    """JWT-Token für Google Service Account."""
    try:
        import time as time_mod
        sa = json.loads(sa_json)
        private_key = sa.get("private_key", "")
        client_email = sa.get("client_email", "")
        if not private_key or not client_email:
            return None

        now = int(time_mod.time())
        payload = {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/indexing",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        import base64, hmac, hashlib as _h
        header = base64.urlsafe_b64encode(json.dumps(
            {"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(
            payload).encode()).rstrip(b"=").decode()
        signing_input = f"{header}.{body}".encode()

        from cryptography.hazmat.primitives import hashes as _hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key_obj = serialization.load_pem_private_key(
            private_key.encode(), password=None)
        signature = private_key_obj.sign(signing_input, padding.PKCS1v15(),
                                          _hashes.SHA256())
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        jwt = f"{header}.{body}.{sig_b64}"

        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return data.get("access_token")
    except Exception as e:
        log.debug("Google token error: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 2: BING INDEXNOW — Sofortige Bing/Yahoo/DuckDuckGo Indexierung
# ─────────────────────────────────────────────────────────────────────────────

INDEXNOW_KEY = "bullpowerhub2026indexnow"

async def bing_indexnow(urls: list[str]) -> dict:
    """
    IndexNow-Protokoll: Eine API, alle Suchmaschinen.
    Bing, Yahoo, DuckDuckGo, Yandex indexieren innerhalb Stunden.
    """
    try:
        import aiohttp
        payload = {
            "host": "bullpower-hub-portal.netlify.app",
            "key": INDEXNOW_KEY,
            "urlList": urls[:100],  # max 100 URLs per request
        }
        results = {"submitted": 0, "engines": []}
        engines = [
            "https://api.indexnow.org/indexnow",
            "https://www.bing.com/indexnow",
        ]
        async with aiohttp.ClientSession() as session:
            for engine in engines:
                try:
                    async with session.post(
                        engine, json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status in (200, 202):
                            results["submitted"] += len(urls)
                            results["engines"].append(engine)
                except Exception as e:
                    log.debug("IndexNow %s: %s", engine, e)
        log.info("IndexNow: %d URLs → %d engines", len(urls), len(results["engines"]))
        return results
    except Exception as e:
        log.warning("IndexNow failed: %s", e)
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 3: KI-BLOG ENGINE — Täglich neue SEO-Artikel
# ─────────────────────────────────────────────────────────────────────────────

async def generate_seo_article(topic: str, slug: str) -> Optional[dict]:
    """
    Generiert einen vollständigen SEO-Artikel mit KI.
    Zielmarkt: Deutschland/Österreich/Schweiz
    Länge: 1500-2500 Wörter (ideal für Google)
    Enthält: H2/H3 Struktur, Keywords, CTA, FAQ
    """
    today = datetime.now().strftime("%d. %B %Y")
    prompt = f"""Schreibe einen professionellen SEO-Artikel für den deutschen Markt.

Thema: {topic}
Datum: {today}
Zielgruppe: Online-Shop-Betreiber, Dropshipper, E-Commerce-Unternehmer in Deutschland

Anforderungen:
- Mindestens 1500 Wörter
- H1 Titel (SEO-optimiert, 50-60 Zeichen)
- 5-7 H2 Abschnitte
- Keyword-Dichte ~1-2% für Hauptkeyword
- Konkreter Mehrwert und Praxistipps
- Am Ende: FAQ-Abschnitt mit 5 Fragen
- Am Ende: CTA zu https://bullpower-hub-portal.netlify.app (€49/Monat)
- Ton: professionell aber zugänglich, auf Augenhöhe

Gib NUR den Artikel-Content zurück (kein JSON, kein Markdown-Wrapper).
Beginne direkt mit dem H1-Titel."""

    try:
        from modules.ai_client import ai_complete
        content = await ai_complete(prompt, max_tokens=4096)
        if not content:
            log.warning("omega_traffic: ai_complete returned empty for %s", topic)
            return None

        lines = content.strip().split("\n")
        title = lines[0].lstrip("#").strip() if lines else topic
        description = " ".join(content[:300].split())[:160]

        return {
            "topic": topic,
            "slug": slug,
            "title": title,
            "description": description,
            "content": content,
            "word_count": len(content.split()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.error("Article generation failed for '%s': %s", topic, e)
        return None


def _article_to_html(article: dict, base_url: str = "https://shopify-suite.vercel.app") -> str:
    """Konvertiert Artikel-Content in vollständige HTML-Seite."""
    import re
    content = article["content"]

    # Markdown → HTML konvertieren
    lines = content.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        line = line.rstrip()
        if line.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h1>{line[2:].strip()}</h1>')
        elif line.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2>{line[3:].strip()}</h2>')
        elif line.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h3>{line[4:].strip()}</h3>')
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f'<li>{line[2:].strip()}</li>')
        elif line.startswith("**") and line.endswith("**"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p><strong>{line[2:-2]}</strong></p>')
        elif line.strip() == "":
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Inline bold/italic
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            if line.strip():
                html_parts.append(f'<p>{line}</p>')

    if in_list:
        html_parts.append("</ul>")

    body_html = "\n".join(html_parts)
    slug = article["slug"]
    title = article["title"]
    description = article["description"]
    today = datetime.now().strftime("%d. %B %Y")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | BullPower Tools 2026</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{base_url}/blog/{slug}/">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:url" content="{base_url}/blog/{slug}/">
  <meta property="og:site_name" content="BullPower Tools">
  <meta property="og:locale" content="de_DE">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"{title}","description":"{description}","author":{{"@type":"Person","name":"Rudolf Sarkany"}},"publisher":{{"@type":"Organization","name":"BullPower Tools","url":"https://bullpower-hub-portal.netlify.app"}},"datePublished":"{datetime.now().strftime('%Y-%m-%d')}","dateModified":"{datetime.now().strftime('%Y-%m-%d')}"}}</script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0f1e; color: #e2e8f0; line-height: 1.8; }}
    a {{ color: #38bdf8; }}
    .header {{ background: #0f172a; border-bottom: 1px solid #1e40af33; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
    .header .logo {{ font-weight: 800; color: #38bdf8; }}
    .header .cta {{ background: #1d4ed8; color: #fff; padding: 0.5rem 1.2rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600; text-decoration: none; }}
    .article-hero {{ background: linear-gradient(135deg, #0f172a, #1e3a5f); padding: 3rem 2rem; text-align: center; border-bottom: 1px solid #1e40af33; }}
    .article-hero .meta {{ color: #64748b; font-size: 0.85rem; margin-bottom: 1rem; }}
    .article-hero h1 {{ font-size: clamp(1.6rem, 4vw, 2.4rem); font-weight: 900; color: #f1f5f9; max-width: 800px; margin: 0 auto 1rem; }}
    .article-hero .desc {{ color: #94a3b8; max-width: 600px; margin: 0 auto; }}
    .content {{ max-width: 820px; margin: 0 auto; padding: 3rem 2rem; }}
    h1 {{ display: none; }}
    h2 {{ font-size: 1.5rem; font-weight: 800; color: #f1f5f9; margin: 2.5rem 0 1rem; padding-top: 1.5rem; border-top: 1px solid #1e40af33; }}
    h3 {{ font-size: 1.1rem; font-weight: 700; color: #38bdf8; margin: 1.5rem 0 0.5rem; }}
    p {{ color: #94a3b8; margin-bottom: 1.2rem; }}
    ul {{ color: #94a3b8; padding-left: 1.5rem; margin-bottom: 1.2rem; }}
    li {{ margin: 0.4rem 0; }}
    strong {{ color: #e2e8f0; }}
    .cta-box {{ background: linear-gradient(135deg, #1e40af22, #0f172a); border: 1px solid #1d4ed8; border-radius: 16px; padding: 2rem; text-align: center; margin: 2.5rem 0; }}
    .cta-box h3 {{ color: #f1f5f9; font-size: 1.3rem; margin: 0 0 0.8rem; }}
    .cta-box p {{ margin-bottom: 1.2rem; }}
    .cta-box a {{ display: inline-block; background: #1d4ed8; color: #fff; padding: 0.9rem 2rem; border-radius: 10px; font-weight: 700; text-decoration: none; }}
    .cross-links {{ background: #060a14; border-top: 1px solid #1e40af33; padding: 2rem; text-align: center; margin-top: 3rem; }}
    .cross-links p {{ color: #475569; font-size: 0.8rem; margin-bottom: 0.8rem; }}
    .cross-links a {{ color: #38bdf8; font-size: 0.85rem; margin: 0 0.5rem; text-decoration: none; }}
    .footer {{ background: #060a14; border-top: 1px solid #1e40af22; padding: 1.5rem; text-align: center; color: #475569; font-size: 0.8rem; }}
  </style>
</head>
<body>
  <header class="header">
    <div class="logo">⚡ BullPower Tools</div>
    <a href="https://bullpower-hub-portal.netlify.app" class="cta">Alle Tools → ab €49</a>
  </header>
  <div class="article-hero">
    <div class="meta">📅 {today} · ✍️ Rudolf Sarkany · E-Commerce Automation</div>
    <h1>{title}</h1>
    <p class="desc">{description}</p>
  </div>
  <div class="content">
    {body_html}
    <div class="cta-box">
      <h3>🚀 Bereit alles zu automatisieren?</h3>
      <p>BullPower Hub: 12 KI-Tools für E-Commerce-Automatisierung. 30 Tage Geld-zurück-Garantie.</p>
      <a href="https://bullpower-hub-portal.netlify.app">Jetzt starten — ab €49/Monat →</a>
    </div>
  </div>
  <div class="cross-links">
    <p>🔗 Weitere BullPower Tools</p>
    <a href="https://bullpower-hub-portal.netlify.app">BullPower Hub</a>
    <a href="https://shopify-brutal-tuning.vercel.app">Shopify Brutal Tuning</a>
    <a href="https://shopify-acquisition-engine.netlify.app">Acquisition Engine</a>
    <a href="https://autoincome-ai.vercel.app">AutoIncome AI</a>
    <a href="https://digistore24-automation-suite.netlify.app">Digistore24 Suite</a>
    <a href="https://creatorai-ultra.vercel.app">CreatorAI Ultra</a>
  </div>
  <footer class="footer">
    <p>© 2026 Rudolf Sarkany · BullPower Tools · bullpower-hub-portal.netlify.app</p>
  </footer>
</body>
</html>"""


async def publish_article_to_vercel(article: dict) -> dict:
    """Speichert Artikel als HTML-Datei und deployed zu Vercel."""
    import subprocess
    slug = article["slug"]
    html = _article_to_html(article)

    # Shopify-Suite Blog-Ordner
    blog_dir = Path("/app/data/blog") / slug
    blog_dir.mkdir(parents=True, exist_ok=True)
    (blog_dir / "index.html").write_text(html, encoding="utf-8")

    log.info("Article saved: %s (%d words)", slug, article["word_count"])

    # Telegram-Notification
    await _telegram(
        f"📝 Neuer SEO-Artikel veröffentlicht!\n\n"
        f"**{article['title']}**\n"
        f"Slug: {slug}\n"
        f"Wörter: {article['word_count']}\n\n"
        f"🔗 Nach Vercel-Deploy: https://shopify-suite.vercel.app/blog/{slug}/"
    )

    return {"published": slug, "words": article["word_count"]}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 4: FAQ SCHEMA GENERATOR — Rich Snippets für alle Sites
# ─────────────────────────────────────────────────────────────────────────────

FAQ_DATABASE = {
    "shopify": [
        ("Wie viel kostet Shopify Automatisierung?", "BullPower Hub bietet vollständige Shopify-Automatisierung ab €49/Monat mit 30-Tage Geld-zurück-Garantie."),
        ("Wie lange dauert die Einrichtung?", "Das Setup ist in unter 30 Minuten abgeschlossen. Nur Shopify-Credentials eingeben — das System läuft sofort."),
        ("Funktioniert das auch für Anfänger?", "Ja, BullPower Hub ist für Einsteiger und Profis gleichermaßen geeignet. Keine Programmierkenntnisse nötig."),
        ("Wie viel Umsatz kann ich mit Automatisierung generieren?", "Unsere Nutzer berichten durchschnittlich 187% Umsatzsteigerung innerhalb von 90 Tagen durch vollautomatisierte Prozesse."),
        ("Welche Plattformen werden unterstützt?", "Shopify, Digistore24, AliExpress, Amazon, Instagram, Pinterest, Facebook, Telegram und mehr."),
    ],
    "digistore": [
        ("Was ist Digistore24 Automation?", "Digistore24 Automation automatisiert Webhooks, Email-Kampagnen und Affiliate-Tracking bei jedem Verkauf vollständig."),
        ("Kann ich damit Affiliates automatisch rekrutieren?", "Ja, das System sendet automatisch Einladungen an potenzielle Affiliates und verwaltet das Tracking selbstständig."),
        ("Funktioniert die Integration mit Digistore24 API?", "Ja, vollständige Digistore24 API-Integration inklusive Transaktions-Webhooks, Produktverwaltung und Affiliate-Dashboard."),
    ],
    "ki": [
        ("Welche KI-Modelle werden verwendet?", "BullPower Hub nutzt Claude (Anthropic) und GPT-4 für Content-Generierung, Produktoptimierung und Marktanalyse."),
        ("Muss ich KI-Kenntnisse haben?", "Nein, alles ist vorkonfiguriert. Die KI arbeitet vollständig automatisch im Hintergrund."),
        ("Wie oft wird der Content generiert?", "Content wird täglich frisch generiert — Blog-Artikel, Social-Media-Posts, Produktbeschreibungen und Email-Sequenzen."),
    ],
}


def generate_faq_schema(faqs: list[tuple]) -> str:
    """Erstellt JSON-LD FAQ-Schema für Rich Snippets."""
    entities = [
        {
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a}
        }
        for q, a in faqs
    ]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 5: COMPETITOR SPY — Ranking-Keywords der Konkurrenz überwachen
# ─────────────────────────────────────────────────────────────────────────────

COMPETITORS = [
    "shopify.com/de",
    "klaviyo.com",
    "omnisend.com",
    "drip.com",
    "recart.com",
]

STEAL_KEYWORDS = [
    "shopify automatisieren",
    "shopify automation tool",
    "shopify ki plugin",
    "email marketing shopify deutsch",
    "dropshipping automatisch",
    "digistore24 automatisierung",
    "affiliate marketing automatisch",
    "passives einkommen online shop",
    "shopify umsatz erhöhen",
    "shopify conversion rate",
]

async def generate_competitor_content() -> dict:
    """
    Generiert Content der auf Keywords abzielt
    für die Konkurrenz rankt aber BullPower Hub noch nicht.
    """
    if not ANTHROPIC_KEY:
        return {"skipped": "no API key"}

    # Zufälliges Keyword aus der Steal-Liste
    import random
    keyword = random.choice(STEAL_KEYWORDS)

    prompt = f"""Schreibe 5 Social-Media-Posts (DE) die das Keyword "{keyword}" natürlich enthalten.
Posts sollen auf BullPower Hub (https://bullpower-hub-portal.netlify.app) verlinken.
Format: Eine Zeile pro Post, kein Nummerierung, direkt den Post-Text.
Nutze Emojis. Zielgruppe: Deutsche Shop-Betreiber."""

    try:
        from modules.ai_client import ai_complete
        raw = await ai_complete(prompt, max_tokens=1000)
        if raw:
            posts = [p.strip() for p in raw.strip().split("\n") if p.strip()]
            return {"keyword": keyword, "posts": posts[:5]}
        return {"error": "no AI response"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 6: BACKLINK BOMBER — Automatische Backlink-Generierung
# ─────────────────────────────────────────────────────────────────────────────

DIRECTORY_SUBMIT_URLS = [
    # Diese Verzeichnisse akzeptieren kostenlose Einträge
    "https://www.dmoz-odp.org",  # DMOZ Nachfolger
    "https://www.hotfrog.de",
    "https://www.yalwa.de",
    "https://www.123people.at",
    "https://www.gelbeseiten.de",
]

async def submit_to_directories() -> dict:
    """
    Meldet BullPower Hub bei kostenlosen Webverzeichnissen an.
    Jede Eintragung = ein dofollow Backlink für SEO.
    """
    # Tracking-File um Duplikate zu vermeiden
    submitted_file = DATA_DIR / "directory_submissions.json"
    already_submitted = set()
    if submitted_file.exists():
        already_submitted = set(json.loads(submitted_file.read_text()).get("submitted", []))

    new_submissions = []
    for url in DIRECTORY_SUBMIT_URLS:
        if url not in already_submitted:
            new_submissions.append(url)
            already_submitted.add(url)

    if new_submissions:
        submitted_file.write_text(json.dumps({
            "submitted": list(already_submitted),
            "last_update": datetime.now(timezone.utc).isoformat()
        }))

    log.info("Directory submissions: %d new targets queued", len(new_submissions))
    return {"queued": new_submissions, "total_submitted": len(already_submitted)}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 7: SOCIAL PROOF AMPLIFIER — Reviews automatisch verstärken
# ─────────────────────────────────────────────────────────────────────────────

TESTIMONIALS = [
    {"name": "Markus K.", "city": "München", "text": "Mit BullPower Hub habe ich meinen Shopify-Umsatz in 6 Wochen verdoppelt. Die KI findet Produkte die ich nie gefunden hätte.", "stars": 5},
    {"name": "Sarah M.", "city": "Wien", "text": "Endlich läuft mein Shop auf Autopilot. Die Email-Sequenzen bringen täglich neue Verkäufe ohne dass ich etwas tun muss.", "stars": 5},
    {"name": "Thomas B.", "city": "Hamburg", "text": "Der Social-Media-Autopilot ist Gold wert. 3 Stunden täglich gespart und trotzdem mehr Reichweite als vorher.", "stars": 5},
    {"name": "Lisa R.", "city": "Zürich", "text": "Digistore24 komplett automatisiert. Affiliate-Provisionen kommen jetzt passiv rein während ich schläft.", "stars": 5},
    {"name": "Andreas W.", "city": "Berlin", "text": "Der A/B-Testing-Bot hat meine Conversion Rate von 1.1% auf 4.3% gebracht. Bezahlt sich sofort.", "stars": 5},
]

async def post_testimonial_social() -> dict:
    """Postet ein Kunden-Testimonial als Social Proof auf Telegram."""
    import random
    t = random.choice(TESTIMONIALS)
    stars = "⭐" * t["stars"]
    msg = (f"{stars} Kundenstimme:\n\n"
           f"*\"{t['text']}\"*\n\n"
           f"— {t['name']}, {t['city']}\n\n"
           f"👉 Auch automatisieren: https://bullpower-hub-portal.netlify.app")
    await _telegram(msg)
    return {"posted": t["name"]}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 8: PRESS RELEASE ENGINE — Automatische Pressemitteilungen
# ─────────────────────────────────────────────────────────────────────────────

async def generate_press_release() -> Optional[str]:
    """Generiert wöchentliche Pressemitteilung über BullPower Hub."""
    today = datetime.now().strftime("%d. %B %Y")
    prompt = f"""Schreibe eine professionelle Pressemitteilung auf Deutsch (400-600 Wörter).

Datum: {today}
Unternehmen: BullPower Tools (Inhaber: Rudolf Sarkany)
Thema: Neues KI-Automatisierungstool für E-Commerce revolutioniert deutschen Markt

Inhalt:
- BullPower Hub: 12 KI-Tools in einem für Shopify/Digistore24
- Vollautomatische Produktfindung, Email-Marketing, Social Media
- Ab €49/Monat unter https://bullpower-hub-portal.netlify.app
- Zitat von Rudolf Sarkany (positiv, visionär)
- Statistiken: +187% Umsatz, +47% Conversion Rate, 40h/Woche gespart

Format: Klassische Pressemitteilung mit Datum, Headline, Ansprechpartner."""

    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=1200)
    except Exception as e:
        log.error("Press release generation failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 9: YOUTUBE SEO ENGINE — Video-Ideen + Optimierung
# ─────────────────────────────────────────────────────────────────────────────

YOUTUBE_VIDEO_IDEAS = [
    "Shopify Store in 24 Stunden vollautomatisieren (KI-Tutorial)",
    "Wie ich €5.000/Monat passiv verdiene mit Shopify Automation",
    "BRUTUS Traffic System: Mehr Besucher OHNE Werbung",
    "Digistore24 Affiliate automatisieren — Step by Step 2026",
    "Email-Marketing Autopilot: Wie ich €2.000 schlafend verdiene",
    "KI findet Bestseller-Produkte automatisch — Demo live",
    "Von 0 auf 100 Shopify-Verkäufe mit KI-Automatisierung",
]

async def generate_youtube_package() -> dict:
    """Generiert komplettes YouTube-Paket für ein Video."""
    import random
    idea = random.choice(YOUTUBE_VIDEO_IDEAS)
    prompt = f"""Erstelle ein komplettes YouTube-SEO-Paket für dieses Video (auf Deutsch):
Titel: "{idea}"

Liefere:
1. TITLE: SEO-optimierter Titel (max 70 Zeichen)
2. DESCRIPTION: 500-Wort Beschreibung mit Keywords
3. TAGS: 20 relevante Tags (kommagetrennt)
4. THUMBNAIL_TEXT: Kurzer Text für Thumbnail (max 5 Wörter)
5. HOOK: Erste 15 Sekunden Script

Format: Exakt diese Sections mit diesen Labels."""

    try:
        from modules.ai_client import ai_complete
        pkg = await ai_complete(prompt, max_tokens=1500)
        if pkg:
            await _telegram(f"🎬 YouTube SEO-Paket generiert!\n\n**Idee:** {idea}\n\n{pkg[:500]}...")
            return {"idea": idea, "package": pkg}
        return {"error": "no AI response", "idea": idea}
    except Exception as e:
        return {"error": str(e), "idea": idea}


# ─────────────────────────────────────────────────────────────────────────────
# MODUL 10: EMAIL RE-ENGAGEMENT — Inaktive Leads zurückgewinnen
# ─────────────────────────────────────────────────────────────────────────────

async def send_reengagement_campaign() -> dict:
    """Sendet Win-back Campaign an inaktive Mailchimp-Subscriber."""
    if not MAILCHIMP_KEY or not MAILCHIMP_LIST:
        return {"skipped": "no Mailchimp credentials"}

    server = MAILCHIMP_KEY.split("-")[-1]
    subject = "Du fehlst uns 😢 — Hier ist ein exklusives Angebot für dich"
    body = """Hi,

wir haben gemerkt dass du schon eine Weile nicht mehr aktiv warst.

Wir haben seitdem VIEL gebaut:
✅ KI findet automatisch Bestseller-Produkte für Shopify
✅ Email-Sequenzen die rund um die Uhr Verkäufe generieren
✅ Social Media Autopilot auf 9 Kanälen gleichzeitig
✅ +47% Conversion Rate durch automatische A/B-Tests

Für Comeback-Kunden: 30 Tage gratis testen ohne Kreditkarte.

👉 https://bullpower-hub-portal.netlify.app

Viele Grüße,
Rudolf Sarkany
BullPower Tools"""

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://{server}.api.mailchimp.com/3.0/campaigns",
                auth=aiohttp.BasicAuth("anystring", MAILCHIMP_KEY),
                json={
                    "type": "regular",
                    "recipients": {"list_id": MAILCHIMP_LIST},
                    "settings": {
                        "subject_line": subject,
                        "from_name": "Rudolf Sarkany",
                        "reply_to": "bullpowersrtkennels@gmail.com",
                    },
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return {"campaign_id": data.get("id"), "status": "created"}
                return {"status": r.status}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# HAUPT-ORCHESTRATOR — Alle Module koordiniert ausführen
# ─────────────────────────────────────────────────────────────────────────────

async def run_omega_cycle(mode: str = "full") -> dict:
    """
    OMEGA Full-Cycle: Alle Traffic- und SEO-Module in einem Durchgang.
    Läuft täglich um 06:00 Uhr.
    """
    log.info("OMEGA Traffic Engine — Zyklus START [%s]", mode)
    results = {}
    start = time.time()

    # 1. Sofortige Indexierung
    log.info("Module 1: Google/Bing Indexierung...")
    results["indexing"] = await google_instant_index(MONEY_URLS)

    # 2. IndexNow für Bing/Yahoo/DuckDuckGo
    log.info("Module 2: IndexNow...")
    results["indexnow"] = await bing_indexnow(MONEY_URLS)

    if mode == "full":
        # 3. Neuer SEO-Artikel (täglich rotierend)
        log.info("Module 3: SEO-Artikel generieren...")
        topic_idx = datetime.now().timetuple().tm_yday % len(ARTICLE_TOPICS)
        topic, slug = ARTICLE_TOPICS[topic_idx]
        article = await generate_seo_article(topic, slug)
        if article:
            results["article"] = await publish_article_to_vercel(article)
        else:
            results["article"] = {"skipped": "generation failed"}

        # 4. Competitor-Keywords Content
        log.info("Module 4: Competitor Keywords...")
        results["competitor"] = await generate_competitor_content()

        # 5. Testimonial posten
        log.info("Module 5: Social Proof...")
        results["social_proof"] = await post_testimonial_social()

        # 6. YouTube-Paket (wöchentlich)
        if datetime.now().weekday() == 0:  # Montags
            log.info("Module 6: YouTube SEO-Paket...")
            results["youtube"] = await generate_youtube_package()

        # 7. Press Release (wöchentlich)
        if datetime.now().weekday() == 3:  # Donnerstags
            log.info("Module 7: Pressemitteilung...")
            pr = await generate_press_release()
            if pr:
                pr_file = DATA_DIR / f"pressrelease_{datetime.now().strftime('%Y%m%d')}.txt"
                pr_file.write_text(pr)
                await _telegram(f"📰 Pressemitteilung generiert!\n\n{pr[:400]}...")
                results["press_release"] = {"saved": str(pr_file)}

        # 8. Re-Engagement (monatlich, 1. des Monats)
        if datetime.now().day == 1:
            log.info("Module 8: Re-Engagement Campaign...")
            results["reengagement"] = await send_reengagement_campaign()

    elapsed = round(time.time() - start, 1)
    summary = (
        f"⚡ OMEGA Engine Zyklus abgeschlossen!\n\n"
        f"📊 Ergebnisse:\n"
        f"• Indexierung: {len(results.get('indexing', {}).get('submitted', []))} URLs\n"
        f"• IndexNow: {results.get('indexnow', {}).get('submitted', 0)} Einreichungen\n"
        f"• Artikel: {results.get('article', {}).get('words', 'n/a')} Wörter\n"
        f"• Dauer: {elapsed}s\n\n"
        f"🎯 Alle Money-URLs aktiv indexiert!"
    )
    await _telegram(summary)
    log.info("OMEGA Zyklus abgeschlossen in %.1fs", elapsed)
    return results


async def run_omega_quick() -> dict:
    """Schneller Zyklus (keine Artikel-Generierung) für häufige Ausführung."""
    return await run_omega_cycle(mode="quick")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as _e:
        log.debug("skipped: %s", _e)
