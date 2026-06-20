#!/usr/bin/env python3
"""
GitHubBlogPublisher — Auto-publishes SEO articles to GitHub Pages.
No Shopify write_content scope needed. Uses GitHub API to push HTML blog posts
to bullpowerhubgit.github.io/shopify-brutal-tuning-landing/blog/<slug>/

Each article is:
- Full SEO HTML with meta tags, schema.org, canonical URL
- Auto-submitted to IndexNow (Bing/Yandex/Seznam)
- Posted as Telegram teaser
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("GitHubBlog")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER  = os.getenv("GITHUB_USER", "bullpowerhubgit")
GITHUB_REPO  = os.getenv("GITHUB_BLOG_REPO", "shopify-brutal-tuning-landing")
ANTHROPIC    = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")
INDEXNOW_KEY = "bullpower2026indexnow"
BASE_URL     = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}"
DS24_URL     = os.getenv("DS24_AFFILIATE_LINK", "https://www.digistore24.com/redir/669750/user37405262/")
PRODUCT_NAME = os.getenv("DS24_PRODUCT_NAME", "KI Business Blueprint")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DEDUP_FILE = DATA_DIR / "github_blog_published.json"


def _slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r'[äöüß]', lambda m: {'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}[m.group()], s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:60]


def _load_published() -> set:
    try:
        return set(json.loads(DEDUP_FILE.read_text()))
    except Exception:
        return set()


def _save_published(published: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(sorted(published)))


# ── Content Generation ────────────────────────────────────────────────────────

async def _generate_article(topic: str) -> dict:
    if not ANTHROPIC:
        return _fallback(topic)
    try:
        import aiohttp
        prompt = f"""Erstelle einen vollständigen SEO-optimierten Blog-Artikel auf Deutsch.
Thema: "{topic}"
Produkt: {PRODUCT_NAME} — Link: {DS24_URL}

Antworte NUR mit JSON:
{{
  "title": "Haupt-Keyword vorne, 55-65 Zeichen, klickstark",
  "meta_description": "150-160 Zeichen, Keyword + CTA enthalten",
  "h1": "Überschrift für den Artikel (leicht abweichend vom title)",
  "intro": "2-3 Sätze Einleitung — Problem ansprechen, Lösung andeuten",
  "sections": [
    {{"h2": "Abschnitt 1 Titel", "content": "200-300 Wörter HTML-Inhalt mit <p>, <ul><li>-Tags"}},
    {{"h2": "Abschnitt 2 Titel", "content": "200-300 Wörter HTML-Inhalt"}},
    {{"h2": "Abschnitt 3 Titel", "content": "200-300 Wörter HTML-Inhalt"}},
    {{"h2": "Fazit", "content": "100 Wörter Zusammenfassung + CTA zu {DS24_URL}"}}
  ],
  "tags": ["seo-keyword-1", "seo-keyword-2", "seo-keyword-3"],
  "reading_time": 5
}}"""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 2000,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                data = await r.json(content_type=None)
        raw = (data.get("content") or [{"text": "{}"}])[0].get("text", "{}")
        s_pos, e_pos = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s_pos:e_pos])
    except Exception as exc:
        log.warning("Article gen error: %s", exc)
        return _fallback(topic)


def _fallback(topic: str) -> dict:
    return {
        "title": f"{topic} — Kompletter Guide 2026",
        "meta_description": f"Alles über {topic}. Tipps, Tools und Strategien für passives Einkommen.",
        "h1": f"{topic} — So geht's richtig",
        "intro": f"{topic} ist einer der wichtigsten Bereiche im Online-Business 2026. Hier erklären wir dir alles was du brauchst.",
        "sections": [
            {"h2": "Warum jetzt der richtige Zeitpunkt ist",
             "content": f"<p>Die Digitalisierung macht {topic} einfacher denn je. Mit den richtigen Tools kannst du sofort starten.</p>"},
            {"h2": f"Die beste Strategie für {topic}",
             "content": f"<p>Setze auf Automatisierung und KI-gestützte Tools. <a href='{DS24_URL}'>{PRODUCT_NAME}</a> bietet genau das.</p>"},
            {"h2": "Fazit",
             "content": f"<p>Starte jetzt: <a href='{DS24_URL}' style='color:#7c3aed;font-weight:bold'>{PRODUCT_NAME} →</a></p>"},
        ],
        "tags": ["passives-einkommen", "ki-business", "online-verdienen"],
        "reading_time": 4,
    }


# ── HTML Builder ──────────────────────────────────────────────────────────────

def _build_html(article: dict, slug: str, pub_date: str) -> str:
    title = article["title"]
    desc  = article["meta_description"]
    h1    = article.get("h1", title)
    intro = article.get("intro", "")
    art_url = f"{BASE_URL}/blog/{slug}/"
    sections_html = ""
    for sec in article.get("sections", []):
        sections_html += f"\n<h2>{sec['h2']}</h2>\n{sec['content']}\n"

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": desc,
        "author": {"@type": "Organization", "name": "BullPower Hub"},
        "publisher": {"@type": "Organization", "name": "BullPower Hub",
                      "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/logo.png"}},
        "datePublished": pub_date,
        "url": art_url,
    }, ensure_ascii=False)

    tags_html = " ".join(f'<a href="{BASE_URL}/blog/tag/{t}/" class="tag">#{t}</a>'
                         for t in article.get("tags", []))

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{art_url}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{art_url}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<script type="application/ld+json">{schema}</script>
<style>
  body{{font-family:system-ui,-apple-system,sans-serif;max-width:780px;margin:0 auto;padding:20px 16px;color:#1a1a2e;line-height:1.7}}
  h1{{font-size:2rem;color:#7c3aed;margin-bottom:.5rem}}
  h2{{font-size:1.4rem;color:#4c1d95;margin-top:2rem}}
  .meta{{color:#666;font-size:.9rem;margin-bottom:2rem}}
  .cta{{background:#7c3aed;color:#fff;padding:14px 28px;text-decoration:none;border-radius:8px;display:inline-block;margin:20px 0;font-weight:bold}}
  .tag{{background:#f3e8ff;color:#7c3aed;padding:4px 10px;border-radius:20px;text-decoration:none;font-size:.85rem;margin-right:6px}}
  nav{{background:#7c3aed;padding:12px 20px}};nav a{{color:#fff;text-decoration:none;font-weight:bold}}
  footer{{border-top:1px solid #e5e7eb;margin-top:3rem;padding-top:1rem;color:#666;font-size:.85rem}}
</style>
</head>
<body>
<nav><a href="{BASE_URL}/">← BullPower Hub</a></nav>
<br>
<article>
<h1>{h1}</h1>
<p class="meta">📅 {pub_date} &bull; ⏱ {article.get("reading_time",5)} Min Lesezeit &bull; BullPower Hub</p>
<p><strong>{intro}</strong></p>
{sections_html}
<div style="text-align:center;margin:2rem 0;padding:2rem;background:#f3e8ff;border-radius:12px">
  <p><strong>🚀 Jetzt starten und sofort mehr verdienen!</strong></p>
  <a href="{DS24_URL}" class="cta">✨ {PRODUCT_NAME} — Jetzt kaufen →</a>
</div>
<p>{tags_html}</p>
</article>
<footer>
  <p>© 2026 BullPower Hub | <a href="{BASE_URL}/">Startseite</a> | <a href="{DS24_URL}">Shop</a></p>
</footer>
</body>
</html>"""


# ── GitHub API Publisher ──────────────────────────────────────────────────────

async def _github_push_file(path: str, content: str, message: str) -> bool:
    """Create or update a file in GitHub repo via API."""
    if not GITHUB_TOKEN:
        return False
    try:
        import aiohttp
        encoded = base64.b64encode(content.encode("utf-8")).decode()
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as s:
            # Check if file exists (need SHA for update)
            sha = None
            async with s.get(api_url, headers=headers,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    existing = await r.json(content_type=None)
                    sha = existing.get("sha")

            payload = {"message": message, "content": encoded}
            if sha:
                payload["sha"] = sha

            async with s.put(api_url, headers=headers, json=payload,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                ok = r.status in (200, 201)
                if not ok:
                    err = await r.text()
                    log.warning("GitHub push failed %s: %s", r.status, err[:100])
                return ok
    except Exception as exc:
        log.warning("GitHub push error: %s", exc)
        return False


async def _indexnow_submit(url: str) -> bool:
    """Submit single URL to IndexNow for immediate Bing/Yandex indexing."""
    try:
        import aiohttp
        endpoints = [
            "https://api.indexnow.org/indexnow",
            "https://www.bing.com/indexnow",
        ]
        ok_count = 0
        payload = {
            "host": f"{GITHUB_USER}.github.io",
            "key": INDEXNOW_KEY,
            "keyLocation": f"{BASE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": [url],
        }
        async with aiohttp.ClientSession() as s:
            for ep in endpoints:
                async with s.post(ep, json=payload,
                                  headers={"Content-Type": "application/json"},
                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status in (200, 202):
                        ok_count += 1
        log.info("IndexNow: %d/2 accepted %s", ok_count, url)
        return ok_count > 0
    except Exception as exc:
        log.warning("IndexNow error: %s", exc)
        return False


async def _telegram_notify(title: str, url: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        import aiohttp
        text = f"📝 <b>Neuer Blog-Artikel published!</b>\n\n{title}\n\n🔗 <a href='{url}'>Artikel lesen</a>\n💰 <a href='{DS24_URL}'>{PRODUCT_NAME} kaufen</a>"
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                         json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"},
                         timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        pass


# ── Main Run Function ─────────────────────────────────────────────────────────

BLOG_TOPICS = [
    "Passives Einkommen mit KI — Was wirklich funktioniert 2026",
    "Shopify Automation für Anfänger — Schritt für Schritt Guide",
    "Digistore24 Affiliate Marketing — Kompletter Blueprint",
    "Online Geld verdienen mit KI-Tools — Die besten Methoden",
    "Dropshipping 2026 — So startest du ohne Risiko",
    "AI Income Machine — Was steckt dahinter?",
    "E-Commerce Automatisierung — Vollautomatisches Online Business",
    "Klaviyo Email Marketing — Umsatz verdoppeln mit Automation",
    "Shopify SEO 2026 — Mehr Besucher ohne Werbebudget",
    "KI Business Blueprint — Von 0 auf passives Einkommen",
    "Affiliate Marketing Strategien die 2026 noch funktionieren",
    "Digitale Produkte verkaufen — Der komplette Guide",
]


async def publish_blog_article(topic: str | None = None) -> dict:
    """Generate and publish one SEO article to GitHub Pages."""
    import random
    if not topic:
        topic = random.choice(BLOG_TOPICS)

    published = _load_published()
    topic_hash = hashlib.sha256(topic.encode()).hexdigest()[:12]
    if topic_hash in published:
        log.info("GitHubBlog: topic already published, skipping: %s", topic[:40])
        return {"ok": False, "reason": "already published", "topic": topic}

    log.info("GitHubBlog: generating article for '%s'", topic[:50])
    article = await _generate_article(topic)
    slug = _slug(article.get("title", topic))
    pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    html = _build_html(article, slug, pub_date)
    file_path = f"blog/{slug}/index.html"
    commit_msg = f"blog: add article '{article['title'][:50]}' ({pub_date})"

    pushed = await _github_push_file(file_path, html, commit_msg)
    if not pushed:
        return {"ok": False, "reason": "GitHub push failed", "topic": topic}

    art_url = f"{BASE_URL}/blog/{slug}/"
    log.info("GitHubBlog: published → %s", art_url)

    # IndexNow + Telegram in parallel
    await asyncio.gather(
        _indexnow_submit(art_url),
        _telegram_notify(article["title"], art_url),
        return_exceptions=True,
    )

    published.add(topic_hash)
    _save_published(published)

    return {
        "ok": True,
        "title": article["title"],
        "url": art_url,
        "slug": slug,
        "topic": topic,
    }
