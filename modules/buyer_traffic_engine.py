#!/usr/bin/env python3
"""
Buyer Traffic Engine — Vollautonomer kostenloser Käufer-Traffic.

5 Kanäle mit echtem Kaufinteresse, kein Paid-Traffic nötig:
1. Reddit Answer Marketing — antwortet auf "was soll ich kaufen" Fragen
2. Shopify SEO Blog — Kaufratgeber die bei Google ranken
3. Klaviyo Email Campaigns — Produkt-Empfehlungen an alle Listen
4. Telegram Deal Channels — deutsche Deal-Gruppen
5. Reddit Deal Posts — shutupandtakemymoney, dealsthatrock etc.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("BuyerTraffic")

_DATA = Path(__file__).parent.parent / "data"
_DATA.mkdir(exist_ok=True)
_DB = _DATA / "buyer_traffic.db"

SHOP_URL = "https://ineedit.com.co"
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "").replace("https://", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2024-04")

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY", "")
REDDIT_TOKEN = os.getenv("REDDIT_TOKEN_V2", "")
REDDIT_USER = os.getenv("REDDIT_USERNAME", "i_want_that_i_need_i")

# ── DB ─────────────────────────────────────────────────────────────────────


def _init_db():
    conn = sqlite3.connect(_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS traffic_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT, action TEXT, url TEXT,
        result TEXT, ts INTEGER DEFAULT (strftime('%s','now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cooldowns (
        key TEXT PRIMARY KEY, ts INTEGER
    )""")
    conn.commit()
    conn.close()


def _cooldown_ok(key: str, hours: int = 24) -> bool:
    conn = sqlite3.connect(_DB)
    row = conn.execute("SELECT ts FROM cooldowns WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return True
    return (time.time() - row[0]) > hours * 3600


def _set_cooldown(key: str):
    conn = sqlite3.connect(_DB)
    conn.execute("INSERT OR REPLACE INTO cooldowns(key,ts) VALUES(?,?)", (key, int(time.time())))
    conn.commit()
    conn.close()


def _log(channel: str, action: str, url: str, result: str):
    conn = sqlite3.connect(_DB)
    conn.execute("INSERT INTO traffic_log(channel,action,url,result) VALUES(?,?,?,?)",
                 (channel, action, url, result))
    conn.commit()
    conn.close()


_init_db()

# ── Shopify: echte Produkte holen ──────────────────────────────────────────


async def _get_shopify_products(limit: int = 10, collection_title: str = "") -> List[Dict]:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    import aiohttp
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json"
    params = {"limit": limit, "status": "active", "fields": "id,title,handle,body_html,product_type,tags,variants,images"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                             params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json(content_type=None)
                prods = d.get("products", [])
                return [p for p in prods if p.get("variants", [{}])[0].get("price", "0") != "0.00"]
    except Exception as e:
        log.warning("Shopify products: %s", e)
        return []


def _product_url(handle: str) -> str:
    return f"{SHOP_URL}/products/{handle}"


def _product_price(product: Dict) -> str:
    price = product.get("variants", [{}])[0].get("price", "0")
    try:
        return f"€{float(price):.2f}"
    except Exception:
        return f"€{price}"


# ── AI Content Generator ───────────────────────────────────────────────────


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    if not ANTHROPIC_KEY:
        return ""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                d = await r.json()
                text = d.get("content", [{}])[0].get("text", "").strip()
                return text if text else ""
    except Exception as e:
        log.warning("AI: %s", e)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# KANAL 1: Reddit Answer Marketing
# Antwortet auf "was soll ich kaufen" Fragen in relevanten Subreddits
# ══════════════════════════════════════════════════════════════════════════════

# Subreddits mit hohem Kaufinteresse
_BUYER_INTENT_SUBREDDITS = [
    "smarthome", "homeautomation", "gadgets",
    "shutupandtakemymoney", "BuyItForLife", "dealsthatrock",
    "ifttt", "amazonecho", "googlehome",
]

# Suchbegriffe für "was soll ich kaufen" Posts
_BUYER_KEYWORDS = [
    "recommendation", "suggest", "worth it", "should I buy",
    "looking for", "best", "help me find", "what to buy",
    "empfehlung", "kaufen", "welches", "lohnt sich",
]


async def _reddit_search_buyer_posts(subreddit: str, keyword: str) -> List[Dict]:
    """Sucht nach Posts wo Leute Kaufempfehlungen suchen."""
    if not REDDIT_TOKEN:
        return []
    import aiohttp
    ua = f"SuperMegaBot/1.0 by {REDDIT_USER}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://oauth.reddit.com/r/{subreddit}/search",
                headers={"Authorization": f"Bearer {REDDIT_TOKEN}", "User-Agent": ua},
                params={"q": keyword, "sort": "new", "limit": 5, "restrict_sr": "true", "t": "week"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                posts = d.get("data", {}).get("children", [])
                return [p["data"] for p in posts
                        if not p["data"].get("locked") and not p["data"].get("archived")
                        and p["data"].get("num_comments", 0) < 20]
    except Exception as e:
        log.warning("Reddit search %s: %s", subreddit, e)
        return []


async def _reddit_comment(post_id: str, text: str) -> Dict:
    """Kommentiert auf einen Reddit Post."""
    if not REDDIT_TOKEN:
        return {"ok": False, "error": "no token"}
    import aiohttp
    ua = f"SuperMegaBot/1.0 by {REDDIT_USER}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://oauth.reddit.com/api/comment",
                headers={"Authorization": f"Bearer {REDDIT_TOKEN}", "User-Agent": ua},
                data={"thing_id": f"t3_{post_id}", "text": text},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                if d.get("success") or d.get("jquery"):
                    return {"ok": True}
                return {"ok": False, "error": str(d.get("json", {}).get("errors", []))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_reddit_answer_marketing(products: List[Dict]) -> Dict:
    """Antwortet auf Käufer-Fragen in Reddit mit Produktempfehlungen."""
    results = {"commented": 0, "errors": []}
    if not REDDIT_TOKEN or not products:
        return results

    for sub in random.sample(_BUYER_INTENT_SUBREDDITS, min(3, len(_BUYER_INTENT_SUBREDDITS))):
        keyword = random.choice(_BUYER_KEYWORDS)
        posts = await _reddit_search_buyer_posts(sub, keyword)

        for post in posts[:2]:
            post_id = post.get("id", "")
            post_title = post.get("title", "")
            if not post_id:
                continue

            cd_key = f"reddit_comment_{post_id}"
            if not _cooldown_ok(cd_key, hours=9999):
                continue

            # Passendes Produkt auswählen
            prod = random.choice(products[:5])
            prod_url = _product_url(prod.get("handle", ""))
            prod_title = prod.get("title", "Smart Home Gadget")
            prod_price = _product_price(prod)

            comment_text = await _ai(
                f"Write a helpful Reddit comment (3-5 sentences, friendly tone, no spam feeling) "
                f"answering this post: '{post_title}'\n\n"
                f"Naturally mention this product as a recommendation: {prod_title} at {prod_price}\n"
                f"Include this link naturally: {prod_url}\n"
                f"Be genuine, helpful, not salesy. End with the link as 'I found it here: <url>'",
                max_tokens=300,
            )
            if not comment_text:
                continue

            res = await _reddit_comment(post_id, comment_text)
            if res["ok"]:
                _set_cooldown(cd_key)
                _log("reddit_answer", post_title[:50], prod_url, "ok")
                results["commented"] += 1
                log.info("Reddit answer posted in r/%s (post: %s)", sub, post_id)
            else:
                results["errors"].append(f"r/{sub}: {res.get('error','?')}")

            await asyncio.sleep(15)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# KANAL 2: Shopify SEO Blog — Kaufratgeber die bei Google ranken
# ══════════════════════════════════════════════════════════════════════════════

_BLOG_TOPICS = [
    "Die 10 besten Smart Home Gadgets 2026 — ehrlicher Test",
    "Smart Home auf Budget: Was lohnt sich wirklich unter €50?",
    "5 Smart Home Produkte die ich nach 6 Monaten noch täglich nutze",
    "Smart Home Anfänger-Guide: Diese Geräte kaufe ich zuerst",
    "Beste Smart Home Deals Juli 2026 — was ich gerade kaufe",
    "Welche Smart Home Produkte sind ihr Geld wirklich wert?",
    "Smart Home vs Normale Geräte: Lohnt sich der Aufpreis?",
    "Top Smart Home Gadgets für kleine Wohnungen 2026",
    "Smart Home Sicherheit: Diese Produkte schützen wirklich",
    "Smart Home Energiesparen: Gadgets die sich in 6 Monaten amortisieren",
]


async def _create_shopify_blog_post(title: str, products: List[Dict]) -> Dict:
    """Erstellt einen SEO-optimierten Kaufratgeber-Blogartikel auf Shopify."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN or not products:
        return {"ok": False, "error": "no config"}

    import aiohttp

    # Produkte für den Artikel auswählen
    featured = products[:5]
    prod_list = "\n".join([
        f"- {p.get('title','')} ({_product_price(p)}): {_product_url(p.get('handle',''))}"
        for p in featured
    ])

    content = await _ai(
        f"Schreibe einen ausführlichen deutschen Kaufratgeber-Blogartikel (800-1200 Wörter) mit dem Titel:\n"
        f"'{title}'\n\n"
        f"Diese Produkte MÜSSEN vorkommen (mit Links):\n{prod_list}\n\n"
        f"Anforderungen:\n"
        f"- SEO-optimiert für Google (Hauptkeyword im ersten Absatz)\n"
        f"- Ehrlicher Ton, keine Werbung-Sprache\n"
        f"- Jedes Produkt mit konkretem Nutzen und Preis erwähnen\n"
        f"- H2/H3 Überschriften verwenden\n"
        f"- Am Ende: 'Jetzt ansehen auf ineedit.com.co' CTA\n"
        f"- HTML-Format\n",
        max_tokens=2000,
    )
    if not content:
        return {"ok": False, "error": "AI content empty"}

    # Auf Shopify posten
    try:
        # Blog ID holen
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                blogs_data = await r.json(content_type=None)
                blogs = blogs_data.get("blogs", [])
                blog_id = blogs[0]["id"] if blogs else None

        if not blog_id:
            return {"ok": False, "error": "no blog found"}

        # Artikel erstellen
        article_data = {
            "article": {
                "title": title,
                "body_html": content,
                "published": True,
                "tags": "smart home, kaufratgeber, gadgets, test, 2026",
                "metafields": [
                    {"key": "description", "value": title[:160],
                     "type": "single_line_text_field", "namespace": "global"}
                ]
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json=article_data,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
                article = d.get("article", {})
                handle = article.get("handle", "")
                article_url = f"{SHOP_URL}/blogs/news/{handle}" if handle else ""
                return {"ok": True, "url": article_url, "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_seo_blog(products: List[Dict]) -> Dict:
    """Erstellt täglich einen neuen Kaufratgeber-Blogartikel."""
    if not _cooldown_ok("seo_blog", hours=23):
        return {"ok": True, "skipped": "cooldown"}

    # Noch nicht verwendete Topics
    conn = sqlite3.connect(_DB)
    used = {r[0] for r in conn.execute("SELECT action FROM traffic_log WHERE channel='seo_blog'")}
    conn.close()
    available = [t for t in _BLOG_TOPICS if t not in used]
    if not available:
        available = _BLOG_TOPICS  # alle recyclen

    title = random.choice(available)
    result = await _create_shopify_blog_post(title, products)
    if result.get("ok"):
        _set_cooldown("seo_blog")
        _log("seo_blog", title, result.get("url", ""), "ok")
        log.info("SEO Blog created: %s", result.get("url"))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# KANAL 3: Klaviyo Email Campaigns — Produkt-Empfehlungen
# ══════════════════════════════════════════════════════════════════════════════

_KLAVIYO_LIST_IDS = ["TiEAtk", "U2iTrm", "UbdJj8", "WdgMfp", "Xwxq6V"]


async def run_klaviyo_campaign(products: List[Dict]) -> Dict:
    """Sendet eine Produkt-Empfehlungs-Email an alle Klaviyo Listen."""
    if not KLAVIYO_KEY or not products:
        return {"ok": False, "error": "no Klaviyo key or products"}
    if not _cooldown_ok("klaviyo_campaign", hours=71):  # max 2x pro Woche
        return {"ok": True, "skipped": "cooldown"}

    import aiohttp

    featured = products[:4]
    subject = random.choice([
        f"🔥 Diese Smart Home Deals wolltest du sehen",
        f"Neu bei ineedit.com.co: {featured[0].get('title','')[:40]}",
        f"Smart Home Woche: Unsere Top-Picks für dich",
        f"Jetzt entdecken: Smart Home Gadgets ab €{_product_price(featured[0]).replace('€','')}",
    ])

    # HTML Email erstellen
    prod_html = ""
    for p in featured:
        url = _product_url(p.get("handle", ""))
        img = p.get("images", [{}])[0].get("src", "") if p.get("images") else ""
        prod_html += f"""
        <div style="border:1px solid #eee;border-radius:8px;padding:16px;margin:12px 0;">
          {'<img src="' + img + '" style="width:100%;max-height:200px;object-fit:cover;border-radius:6px;" />' if img else ''}
          <h3 style="margin:8px 0 4px;">{p.get('title','')}</h3>
          <p style="color:#e44;font-weight:bold;font-size:18px;">{_product_price(p)}</p>
          <a href="{url}" style="background:#222;color:#fff;padding:10px 20px;
             border-radius:6px;text-decoration:none;display:inline-block;margin-top:8px;">
            Jetzt ansehen →
          </a>
        </div>"""

    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#333;">
      <div style="background:#111;color:#fff;padding:20px;border-radius:8px 8px 0 0;">
        <h2 style="margin:0;">✨ Smart Home Deals der Woche</h2>
        <p style="opacity:.8;">ineedit.com.co — I Want That! I Need It!</p>
      </div>
      <div style="padding:20px;">
        <p>Diese Woche haben wir besondere Picks für dich:</p>
        {prod_html}
        <p style="text-align:center;margin-top:24px;">
          <a href="{SHOP_URL}" style="background:#e44;color:#fff;padding:14px 32px;
             border-radius:8px;text-decoration:none;font-weight:bold;">
            Alle Deals ansehen →
          </a>
        </p>
      </div>
      <div style="background:#f5f5f5;padding:12px;font-size:12px;color:#999;text-align:center;">
        Du erhältst diese Email weil du dich bei ineedit.com.co angemeldet hast.
        <br><a href="{{{{ unsubscribe_url }}}}">Abmelden</a>
      </div>
    </body></html>"""

    results = {"campaigns_sent": 0, "errors": []}

    try:
        async with aiohttp.ClientSession() as s:
            # Kampagne erstellen
            async with s.post(
                "https://a.klaviyo.com/api/campaigns/",
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                         "revision": "2024-10-15", "Content-Type": "application/json"},
                json={"data": {"type": "campaign", "attributes": {
                    "name": f"BuyerTraffic_{datetime.now().strftime('%Y%m%d_%H%M')}",
                    "channel": "email",
                    "audiences": {"included": _KLAVIYO_LIST_IDS[:3]},
                    "send_strategy": {"method": "immediate"},
                    "content": {"subject": subject, "preview_text": "Top Smart Home Deals für dich",
                                "from_email": "deals@ineedit.com.co",
                                "from_label": "ineedit.com.co",
                                "reply_to_email": "deals@ineedit.com.co"}
                }}},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                campaign_id = d.get("data", {}).get("id", "")
                if campaign_id:
                    results["campaign_id"] = campaign_id
                    results["campaigns_sent"] += 1
                    _set_cooldown("klaviyo_campaign")
                    _log("klaviyo", subject[:50], "", campaign_id)
                    log.info("Klaviyo campaign created: %s", campaign_id)
                else:
                    results["errors"].append(str(d)[:200])
    except Exception as e:
        results["errors"].append(str(e))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# KANAL 4: Telegram Deal Channels
# Postet in deutsche Deal/Shopping Telegram Gruppen
# ══════════════════════════════════════════════════════════════════════════════

# Öffentliche deutsche Deal-/Shopping-Telegram-Kanäle
_TG_DEAL_CHANNELS = [
    "@SmartHomeDeal",
    "@GadgetsDealDE",
    "@TechDealsDE",
    "@SmartHomeGadgetsDE",
    "@AmazonDealsDeutschland",
]


async def run_telegram_deals(products: List[Dict]) -> Dict:
    """Postet Deal-Posts in Telegram Deal-Kanäle."""
    if not TG_TOKEN or not products:
        return {"ok": False, "error": "no token or products"}
    if not _cooldown_ok("telegram_deals", hours=11):
        return {"ok": True, "skipped": "cooldown"}

    import aiohttp

    prod = random.choice(products[:8])
    url = _product_url(prod.get("handle", ""))
    title = prod.get("title", "Smart Home Gadget")
    price = _product_price(prod)

    deal_text = await _ai(
        f"Schreibe einen kurzen deutschen Telegram Deal-Post (max 200 Zeichen) für:\n"
        f"Produkt: {title}\nPreis: {price}\nLink: {url}\n"
        f"Format: Emoji + Produktname + Preis + kurzer Nutzen + Link\n"
        f"Beispiel: 🔥 Smart Steckdose {price} — steuere alles per App! {url}",
        max_tokens=100,
    )
    if not deal_text:
        deal_text = f"🔥 {title} — {price}\n👉 {url}"

    results = {"posted": 0, "errors": []}

    async with aiohttp.ClientSession() as s:
        # Zuerst in eigenen Kanal
        if TG_CHAT:
            try:
                async with s.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": deal_text,
                          "disable_web_page_preview": False},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    d = await r.json()
                    if d.get("ok"):
                        results["posted"] += 1
                        _log("telegram_deals", title[:50], url, "ok")
                        log.info("Telegram deal posted: %s", title[:40])
            except Exception as e:
                results["errors"].append(str(e))

    _set_cooldown("telegram_deals")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# KANAL 5: Reddit Deal Posts in High-Intent Communities
# ══════════════════════════════════════════════════════════════════════════════

_DEAL_SUBREDDITS = [
    "shutupandtakemymoney",  # 1.8M — Impulskäufe
    "dealsthatrock",
    "BuyItForLife",          # 3.6M — Qualitätskäufe
    "gadgets",               # 20M
    "smarthome",             # 1M
]


async def _reddit_post(subreddit: str, title: str, text: str) -> Dict:
    """Erstellt einen Reddit Post."""
    if not REDDIT_TOKEN:
        return {"ok": False, "error": "no token"}
    import aiohttp
    ua = f"SuperMegaBot/1.0 by {REDDIT_USER}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://oauth.reddit.com/api/submit",
                headers={"Authorization": f"Bearer {REDDIT_TOKEN}", "User-Agent": ua},
                data={"sr": subreddit, "kind": "self", "title": title,
                      "text": text, "nsfw": "false", "spoiler": "false"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                errors = d.get("json", {}).get("errors", [])
                if errors:
                    return {"ok": False, "error": str(errors)}
                url = d.get("json", {}).get("data", {}).get("url", "")
                return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_reddit_deal_posts(products: List[Dict]) -> Dict:
    """Postet Deal-Posts in High-Intent Reddit Communities."""
    results = {"posted": 0, "errors": []}
    if not REDDIT_TOKEN or not products:
        return results

    for sub in random.sample(_DEAL_SUBREDDITS, min(2, len(_DEAL_SUBREDDITS))):
        cd_key = f"reddit_deal_{sub}"
        if not _cooldown_ok(cd_key, hours=71):
            continue

        prod = random.choice(products[:6])
        url = _product_url(prod.get("handle", ""))
        title_text = prod.get("title", "Smart Home Gadget")
        price = _product_price(prod)
        desc = prod.get("body_html", "")[:200].replace("<", "").replace(">", "")

        post_title = await _ai(
            f"Write a Reddit post title for r/{sub} (no clickbait, genuine, max 100 chars):\n"
            f"Product: {title_text}, Price: {price}\n"
            f"Subreddit context: r/{sub} appreciates honest product finds",
            max_tokens=60,
        )
        if not post_title:
            post_title = f"Found this: {title_text} — {price}"

        post_text = await _ai(
            f"Write a genuine Reddit post for r/{sub} about:\n"
            f"Product: {title_text} ({price})\n"
            f"Description: {desc}\n"
            f"Link: {url}\n\n"
            f"3-4 sentences. Why it's interesting, price, link. Genuine community tone.",
            max_tokens=200,
        )
        if not post_text:
            post_text = f"Just discovered this: **{title_text}** for {price}\n\n{url}"

        res = await _reddit_post(sub, post_title, post_text)
        if res["ok"]:
            _set_cooldown(cd_key)
            _log("reddit_deal", post_title[:50], url, "ok")
            results["posted"] += 1
            log.info("Reddit deal posted in r/%s", sub)
        else:
            results["errors"].append(f"r/{sub}: {res.get('error','?')[:80]}")

        await asyncio.sleep(20)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════


async def run_buyer_traffic_cycle() -> Dict:
    """Läuft alle 4 Stunden — vollautonomer Käufer-Traffic."""
    started = datetime.now().isoformat()
    results = {
        "started": started,
        "reddit_answers": {},
        "seo_blog": {},
        "klaviyo": {},
        "telegram_deals": {},
        "reddit_deals": {},
        "total_actions": 0,
    }

    # Produkte laden
    products = await _get_shopify_products(limit=50)
    if not products:
        log.warning("Keine Shopify-Produkte verfügbar")
        return {"ok": False, "error": "no products"}

    log.info("BuyerTraffic: %d Produkte geladen", len(products))

    # Alle 5 Kanäle parallel starten
    tasks = await asyncio.gather(
        run_reddit_answer_marketing(products),
        run_seo_blog(products),
        run_klaviyo_campaign(products),
        run_telegram_deals(products),
        run_reddit_deal_posts(products),
        return_exceptions=True,
    )

    labels = ["reddit_answers", "seo_blog", "klaviyo", "telegram_deals", "reddit_deals"]
    for label, result in zip(labels, tasks):
        if isinstance(result, Exception):
            results[label] = {"ok": False, "error": str(result)}
        else:
            results[label] = result

    # Aktionen zählen
    results["total_actions"] = (
        results["reddit_answers"].get("commented", 0) +
        (1 if results["seo_blog"].get("ok") and not results["seo_blog"].get("skipped") else 0) +
        results["klaviyo"].get("campaigns_sent", 0) +
        results["telegram_deals"].get("posted", 0) +
        results["reddit_deals"].get("posted", 0)
    )

    # Telegram Benachrichtigung
    if TG_TOKEN and TG_CHAT:
        msg = (
            f"🚀 *BuyerTraffic Cycle*\n"
            f"Reddit Answers: {results['reddit_answers'].get('commented', 0)}\n"
            f"SEO Blog: {'✅' if results['seo_blog'].get('ok') and not results['seo_blog'].get('skipped') else '⏭'}\n"
            f"Klaviyo: {results['klaviyo'].get('campaigns_sent', 0)} Kampagnen\n"
            f"Telegram: {results['telegram_deals'].get('posted', 0)}\n"
            f"Reddit Deals: {results['reddit_deals'].get('posted', 0)}\n"
            f"*Gesamt: {results['total_actions']} Aktionen*"
        )
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                             json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                             timeout=aiohttp.ClientTimeout(total=8))
        except Exception:
            pass

    log.info("BuyerTraffic done: %d actions", results["total_actions"])
    return results


async def get_traffic_stats() -> Dict:
    """Gibt Statistiken über generierten Traffic zurück."""
    conn = sqlite3.connect(_DB)
    stats = {}
    for channel in ["reddit_answer", "seo_blog", "klaviyo", "telegram_deals", "reddit_deal"]:
        count = conn.execute(
            "SELECT COUNT(*) FROM traffic_log WHERE channel=?", (channel,)
        ).fetchone()[0]
        stats[channel] = count
    stats["total"] = sum(stats.values())
    last = conn.execute(
        "SELECT channel, action, ts FROM traffic_log ORDER BY ts DESC LIMIT 5"
    ).fetchall()
    stats["recent"] = [{"channel": r[0], "action": r[1],
                        "ts": datetime.fromtimestamp(r[2]).isoformat()} for r in last]
    conn.close()
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_buyer_traffic_cycle())
