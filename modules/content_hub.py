#!/usr/bin/env python3
"""
ContentHub — Zentrales Content-Generation-System für SuperMegaBot

Vereint alle 5 ehemaligen Content-Engine-Services:
  seo-traffic-engine, social-traffic-engine, meta-social-engine,
  visual-content-engine, freelance-gig-engine

Läuft direkt im supermegabot Scheduler — kein separater Railway-Service nötig.
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
from datetime import datetime

import aiohttp
import anthropic

logger = logging.getLogger("ContentHub")

ANTHROPIC_API_KEY          = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID           = os.getenv("TELEGRAM_CHAT_ID", "")
TWITTER_API_KEY            = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET         = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN       = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
FACEBOOK_ACCESS_TOKEN      = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID           = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
DISCORD_WEBHOOK_URL        = os.getenv("DISCORD_WEBHOOK_URL", "")
BASE_URL                   = os.getenv(
    "SUPERMEGABOT_DASHBOARD_URL",
    "https://supermegabot-production.up.railway.app",
)

_DATA_DIR = os.getenv("DATA_DIR", "/tmp")
DB_PATH   = os.path.join(_DATA_DIR, "content_hub.db")

PRODUCTS = [
    {"name": "Shopify Acquisition Engine", "url": "https://shopify-acquisition-engine-production.up.railway.app", "price": "€49/mo", "niche": "E-Commerce Automatisierung"},
    {"name": "SEO Turbo Tools",            "url": "https://seo-turbo-tools-production.up.railway.app",            "price": "€29/mo", "niche": "SEO & Marketing"},
    {"name": "iComeAuto SaaS",             "url": "https://icomeauto-saas-production.up.railway.app",             "price": "€29/mo", "niche": "Passives Einkommen"},
    {"name": "SuperMegaBot",               "url": "https://supermegabot-production.up.railway.app",           "price": "€49/mo", "niche": "KI Business Automatisierung"},
    {"name": "Telegram Automation Bot",    "url": "https://telegram-automation-bot-production.up.railway.app",    "price": "€39/mo", "niche": "Telegram Marketing"},
]

SEO_KEYWORDS = [
    "shopify produkte automatisch importieren",
    "shopify ki automatisierung",
    "seo analyse kostenlos",
    "meta beschreibung generator ki",
    "passives einkommen automatisierung",
    "ki tools online business",
    "digistore24 automatisierung",
    "affiliate marketing automatisieren",
    "telegram bot erstellen python",
    "shopify dropshipping automatisieren",
    "e-commerce automatisierung tools",
    "shopify bestseller produkte finden",
    "ki content generator deutsch",
    "geld verdienen mit automatisierung",
    "seo score verbessern tipps",
]

FREELANCE_SERVICES = [
    {"title": "Shopify Store Vollautomatisierung mit KI", "price": 350, "url": "https://shopify-acquisition-engine-production.up.railway.app"},
    {"title": "SEO Audit & KI Meta-Descriptions",        "price": 150, "url": "https://seo-turbo-tools-production.up.railway.app"},
    {"title": "Custom Telegram Bot mit Stripe Payment",  "price": 500, "url": "https://supermegabot-production.up.railway.app"},
    {"title": "E-Commerce KI-Automatisierung Setup",     "price": 300, "url": "https://shopify-acquisition-engine-production.up.railway.app"},
]


# ── Database ───────────────────────────────────────────────────────────────

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seo_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE, title TEXT, content TEXT,
            keyword TEXT, excerpt TEXT, word_count INTEGER,
            created_at TEXT, views INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS content_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, content_type TEXT, content TEXT,
            product TEXT, status TEXT DEFAULT 'queued',
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def _save_article(slug: str, title: str, content: str, keyword: str, excerpt: str, word_count: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO seo_articles (slug,title,content,keyword,excerpt,word_count,created_at) VALUES (?,?,?,?,?,?,?)",
        (slug, title, content, keyword, excerpt, word_count, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────

def _haiku(prompt: str, max_tokens: int = 500) -> str:
    """Sync AI wrapper — versucht OpenRouter direkt, dann Fallback-Templates."""
    import requests as _req, random as _rnd
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key:
        try:
            r = _req.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "liquid/lfm-2.5-1.2b-instruct:free",
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens},
                timeout=25,
            )
            d = r.json()
            choices = d.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
    _ds24 = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
    _templates = [
        f"🚀 E-Commerce Automation auf Autopilot! DS24 Affiliate aktiv. 👉 {_ds24}",
        f"💰 Online Geld verdienen 2026: KI-Tools automatisieren dein Business komplett. {_ds24}",
        f"🤖 Shopify + DS24 + KI = passives Einkommen 24/7! {_ds24}",
        f"📈 BRUTUS Traffic läuft — alle Kanäle werden bespielt. Jetzt starten: {_ds24}",
        f"🎯 DS24 Affiliate + BRUTUS = passive Einnahmen täglich! {_ds24}",
    ]
    return _rnd.choice(_templates)


async def _tg(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4096], "parse_mode": "HTML"}, timeout=aiohttp.ClientTimeout(total=8))
    except Exception as e:
        logger.warning("Telegram send error: %s", e)


# ── Auto-post functions ────────────────────────────────────────────────────

async def _post_twitter(text: str) -> bool:
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
        return False
    try:
        import base64, hashlib, hmac as _hmac, secrets, time, urllib.parse
        url = "https://api.twitter.com/2/tweets"
        nonce = secrets.token_hex(16)
        ts = str(int(time.time()))
        params = {
            "oauth_consumer_key": TWITTER_API_KEY,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": ts,
            "oauth_token": TWITTER_ACCESS_TOKEN,
            "oauth_version": "1.0",
        }
        base_str = "&".join([
            "POST",
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote("&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in sorted(params.items())), safe=""),
        ])
        signing_key = f"{urllib.parse.quote(TWITTER_API_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_TOKEN_SECRET, safe='')}"
        sig = base64.b64encode(_hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
        params["oauth_signature"] = sig
        auth_header = "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(params.items()))
        async with aiohttp.ClientSession() as s:
            r = await s.post(url, json={"text": text[:280]}, headers={"Authorization": auth_header, "Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10))
            d = await r.json()
            return "data" in d
    except Exception as e:
        logger.error("Twitter post error: %s", e)
        return False


async def _post_facebook(text: str) -> bool:
    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/feed",
                params={"access_token": FACEBOOK_ACCESS_TOKEN},
                json={"message": text},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            d = await r.json()
            return "id" in d
    except Exception as e:
        logger.error("Facebook post error: %s", e)
        return False


async def _post_discord(text: str) -> bool:
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(DISCORD_WEBHOOK_URL, json={"content": text[:2000]}, timeout=aiohttp.ClientTimeout(total=8))
            return r.status in (200, 204)
    except Exception as e:
        logger.error("Discord post error: %s", e)
        return False


# ── SEO Article generation ─────────────────────────────────────────────────

def _generate_article(keyword: str, product: dict) -> dict:
    raw = _haiku(f"""Schreibe einen SEO-optimierten Blog-Artikel auf Deutsch.

Keyword: "{keyword}"
Ziel-Link: {product['url']} ({product['name']})

FORMAT (reines HTML):
META: [Meta-Description 150-160 Zeichen]
SLUG: [url-slug-ohne-umlaute]

<h1>[Titel]</h1>
<p>[Einleitung]</p>
<h2>[Abschnitt 1]</h2>
<p>[Inhalt]</p>
<h2>[Abschnitt 2]</h2><p>[Inhalt]</p>
<h2>[Abschnitt 3]</h2><p>[Inhalt]</p>
<h2>Fazit</h2>
<p>[CTA mit Link zu {product['url']}]</p>

800-1000 Wörter, echter Mehrwert.""", max_tokens=2000)

    meta = ""
    slug = (keyword.lower()
            .replace(" ", "-").replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))
    for line in raw.split("\n"):
        if line.startswith("META:"):
            meta = line.replace("META:", "").strip()
        elif line.startswith("SLUG:"):
            slug = line.replace("SLUG:", "").strip()

    content_html = "\n".join(l for l in raw.split("\n") if not l.startswith(("META:", "SLUG:")))
    word_count = len(content_html.split())
    title = keyword.title()

    _save_article(slug, title, content_html, keyword, meta, word_count)
    return {"slug": slug, "title": title, "keyword": keyword, "meta": meta,
            "content": content_html, "url": f"{BASE_URL}/blog/{slug}"}


# ── Social content generation ──────────────────────────────────────────────

def _generate_social(article: dict, product: dict) -> dict:
    prompt = f"""Erstelle Social-Media-Inhalte auf Deutsch für:
Artikel: {article['title']}
Produkt: {product['name']} — {product['url']}

Antworte NUR mit JSON:
{{
  "facebook": "2-3 Absätze + CTA + 5 Hashtags",
  "instagram": "Caption + 10 Hashtags DE+EN",
  "tiktok": "45-Sek-Script: Hook→Problem→Lösung→CTA",
  "reddit": "helpful post in English with natural link",
  "linkedin": "3 business insights + link",
  "pinterest": "TITEL:[max 100 chars] BESCHREIBUNG:[150 chars]"
}}"""
    try:
        raw = _haiku(prompt, max_tokens=1200)
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start >= 0:
            return json.loads(raw[start:end])
    except Exception:
        pass
    return {p: f"{article['title']} — {product['url']}" for p in
            ["facebook", "instagram", "tiktok", "reddit", "linkedin", "pinterest"]}


# ── Main cycles ────────────────────────────────────────────────────────────

async def run_content_cycle() -> str:
    """SEO-Artikel + alle Social-Inhalte generieren und verteilen. Alle 6h."""
    keyword = random.choice(SEO_KEYWORDS)
    product = random.choice(PRODUCTS)
    logger.info("ContentHub cycle: keyword='%s' product='%s'", keyword, product["name"])

    # Generate (sync calls, run in executor to avoid blocking event loop)
    loop = asyncio.get_event_loop()
    article = await loop.run_in_executor(None, _generate_article, keyword, product)
    social  = await loop.run_in_executor(None, _generate_social, article, product)

    # Auto-post
    tweet   = f"📖 {article['title']}\n\n{article['meta']}\n\n{article['url']}"
    tw_ok   = await _post_twitter(tweet)
    fb_ok   = await _post_facebook(social["facebook"])
    dc_ok   = await _post_discord(social["reddit"])

    # Telegram report
    await _tg(
        f"📰 <b>NEUER SEO-ARTIKEL</b>\n"
        f"Keyword: <code>{keyword}</code>\n"
        f"Titel: {article['title']}\n"
        f"URL: {article['url']}\n\n"
        f"{'✅ Twitter' if tw_ok else '📋 Twitter Queue'} | "
        f"{'✅ Facebook' if fb_ok else '📋 Facebook Queue'} | "
        f"{'✅ Discord' if dc_ok else '📋 Discord Queue'}"
    )
    await asyncio.sleep(3)
    await _tg(
        f"📱 <b>SOCIAL: {article['title'][:50]}</b>\n\n"
        f"📸 <b>Instagram:</b>\n{social['instagram'][:400]}\n\n"
        f"🎬 <b>TikTok:</b>\n{social['tiktok'][:400]}"
    )
    await asyncio.sleep(3)
    await _tg(
        f"🔗 <b>COMMUNITY CONTENT</b>\n\n"
        f"📌 <b>Pinterest:</b>\n{social['pinterest'][:250]}\n\n"
        f"💼 <b>LinkedIn:</b>\n{social['linkedin'][:350]}\n\n"
        f"👾 <b>Reddit:</b>\n{social['reddit'][:350]}"
    )

    logger.info("ContentHub cycle done — Twitter:%s Facebook:%s Discord:%s", tw_ok, fb_ok, dc_ok)
    return f"Artikel: {article['title']} | TW:{tw_ok} FB:{fb_ok} DC:{dc_ok}"


async def run_freelance_cycle() -> str:
    """Fiverr Gig + Upwork Proposal generieren. Alle 12h."""
    service = random.choice(FREELANCE_SERVICES)
    logger.info("Freelance cycle: %s", service["title"])

    loop = asyncio.get_event_loop()
    gig = await loop.run_in_executor(None, _haiku,
        f"Fiverr Gig EN für: {service['title']}\n${service['price']}\nDemo: {service['url']}\n"
        "Title + Description (3 paragraphs) + 3 Packages + 5 Search Tags", 700)
    proposal = await loop.run_in_executor(None, _haiku,
        f"Upwork Proposal EN, max 150 words:\nService: {service['title']}\n"
        f"Bid: ${service['price']}\nDemo: {service['url']}\nNo clichés, direct value.", 350)

    await _tg(
        f"💼 <b>FIVERR GIG BEREIT</b>\n{service['title']}\n\n{gig[:800]}\n\n"
        f"🚀 <b>UPWORK PROPOSAL</b>\n\n{proposal[:500]}\n\n"
        f"➡️ Poste auf fiverr.com + upwork.com"
    )
    return f"Freelance: {service['title']} | ${service['price']}"


# ── Stats API (für Dashboard) ─────────────────────────────────────────────

async def get_stats() -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        articles = conn.execute("SELECT COUNT(*) FROM seo_articles").fetchone()[0]
        queued   = conn.execute("SELECT COUNT(*) FROM content_queue WHERE status='queued'").fetchone()[0]
        last_row = conn.execute("SELECT keyword, created_at FROM seo_articles ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return {
            "articles_generated": articles,
            "content_queued":     queued,
            "last_article":       last_row[0] if last_row else None,
            "last_generated":     last_row[1] if last_row else None,
        }
    except Exception:
        return {"articles_generated": 0, "content_queued": 0}
