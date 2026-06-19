"""
ContentVelocityEngine — Mass AI content generation at scale.
One topic → 10 content pieces across all formats, auto-published everywhere.
"""
import asyncio
import hashlib
import json
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("ContentVelocity")

ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER     = os.getenv("SHOPIFY_API_VERSION", "2024-01")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT         = os.getenv("TELEGRAM_CHAT_ID", "")

PRODUCT_NAME    = os.getenv("DS24_PRODUCT_NAME", "AI Income Machine")
PRODUCT_URL     = os.getenv("DS24_PRODUCT_URL", "https://www.digistore24.com/product/669750")
PRODUCT_PRICE   = os.getenv("DS24_PRODUCT_PRICE", "€37")

DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "content_velocity"
DEDUP_FILE  = DATA_DIR / "published.json"
LOG_FILE    = DATA_DIR / "log.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_published() -> set:
    try:
        return set(json.loads(DEDUP_FILE.read_text()))
    except Exception:
        return set()


def _save_published(published: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(sorted(published)))


def _append_log(entry: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logs = []
    try:
        logs = json.loads(LOG_FILE.read_text())
    except Exception:
        pass
    logs.append(entry)
    LOG_FILE.write_text(json.dumps(logs[-500:], ensure_ascii=False, indent=2))


def _title_hash(title: str) -> str:
    return hashlib.sha256(title.encode()).hexdigest()[:16]


# ── Trending Topics ───────────────────────────────────────────────────────────

async def _fetch_trending() -> list[str]:
    try:
        import aiohttp
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                text = await r.text()
        root = ET.fromstring(text)
        topics = []
        for item in root.iter("item"):
            t = item.find("title")
            if t is not None and t.text:
                topics.append(t.text.strip())
        return topics[:10]
    except Exception as e:
        log.warning("Trends fetch error: %s", e)
        return [
            "KI Geld verdienen 2026", "Passives Einkommen sofort",
            "Shopify Automatisierung Deutschland", "AI Business Tools",
            "Online Verkaufen ohne Lager",
        ]


# ── Master Content Generator ──────────────────────────────────────────────────

async def generate_master_content(topic: str, product_name: str = PRODUCT_NAME,
                                   product_url: str = PRODUCT_URL,
                                   price: str = PRODUCT_PRICE) -> dict | None:
    """Generate all 10 content formats in a single Claude Haiku call."""
    if not ANTHROPIC_KEY:
        log.warning("No ANTHROPIC_API_KEY — skipping content generation")
        return None
    try:
        import aiohttp
        prompt = f"""Du bist ein professioneller Multi-Channel Content Creator.
Thema: "{topic}"
Produkt: {product_name} | Preis: {price} | Link: {product_url}

Erstelle Content auf Deutsch für ALLE folgenden Formate.
Gib NUR valides JSON zurück (kein anderer Text außerhalb):

{{
  "blog_article_title": "SEO-optimierter Artikel-Titel (max 65 Zeichen, Haupt-Keyword vorne)",
  "blog_article": "<h1>Titel</h1><p>1200-Wort Artikel auf Deutsch. Informativer Mehrwert. <h2>Abschnitt 1</h2>...<h2>Abschnitt 2</h2>... Natürliche Erwähnung von {product_name} ({price}) als Lösung. CTA am Ende.</p>",
  "tweet": "Viraler Tweet max 270 Zeichen. Hook + Mehrwert + 2-3 Hashtags. Kein direkter Spam. {product_url}",
  "instagram_caption": "Emoji-reicher IG Caption. Hook-Zeile, Mehrwert-Punkte, CTA, Hashtags (15 relevante). Max 400 Zeichen.",
  "linkedin_post": "Professioneller Post, max 200 Zeichen, 2-3 Business-Hashtags, subtiler Hinweis auf Produkt.",
  "email_subject": "Email-Betreffzeile (max 50 Zeichen, neugierig, kein Spam-Trigger)",
  "email_body_html": "<html><body><h2>Betreff</h2><p>Personalisierte E-Mail mit echtem Mehrwert zum Thema {topic}. Erkläre Problem, präsentiere Lösung ({product_name}) natürlich. CTA-Button. Max 250 Wörter.</p><a href='{product_url}' style='background:#ff6600;color:white;padding:12px 24px;border-radius:6px;text-decoration:none'>Jetzt ansehen →</a></body></html>",
  "pinterest_description": "SEO-optimierte Pinterest-Beschreibung, 500 Zeichen, keyword-reich, Mehrwert kommunizieren, Link am Ende.",
  "youtube_description": "YouTube-Video-Beschreibung (500 Zeichen). Erkläre was im Video ist. Keywords. Link in erste Zeile.",
  "whatsapp_message": "Informeller WhatsApp-Text, max 200 Zeichen. Freundlich, persönlich, Link eingebaut.",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"]
}}"""

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 2500,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=35),
            ) as r:
                data = await r.json(content_type=None)

        raw = data["content"][0]["text"]
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        log.error("Content generation error: %s", e)
        return None


# ── Publishers ────────────────────────────────────────────────────────────────

async def publish_shopify_blog(title: str, body_html: str) -> dict:
    """POST new article to Shopify blog."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "error": "Shopify not configured"}
    try:
        import aiohttp
        # Get blog ID (use first blog, typically "news")
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                blogs = (await r.json(content_type=None)).get("blogs", [])

            if not blogs:
                return {"ok": False, "error": "No blogs found in Shopify"}

            blog_id = blogs[0]["id"]
            payload = {"article": {"title": title, "body_html": body_html,
                                    "published": True, "author": "BullPower Hub"}}

            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                         "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                result = await r.json(content_type=None)

        article = result.get("article", {})
        article_id = article.get("id")
        handle = article.get("handle", "")
        url = f"https://{SHOPIFY_DOMAIN}/blogs/news/{handle}" if handle else ""
        log.info("Shopify blog published: %s → %s", title[:40], url)
        return {"ok": bool(article_id), "article_id": article_id, "url": url}
    except Exception as e:
        log.warning("Shopify blog error: %s", e)
        return {"ok": False, "error": str(e)}


async def send_telegram_broadcast(text: str) -> dict:
    """Broadcast message to Telegram channel."""
    if not TG_TOKEN or not TG_CHAT:
        return {"ok": False, "error": "Telegram not configured"}
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text[:4096],
                      "parse_mode": "HTML", "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        ok = d.get("ok", False)
        log.info("Telegram broadcast: %s", ok)
        return {"ok": ok, "message_id": d.get("result", {}).get("message_id")}
    except Exception as e:
        log.warning("Telegram broadcast error: %s", e)
        return {"ok": False, "error": str(e)}


async def _ping_search_engines(url: str) -> dict:
    """Ping Google, Bing, IndexNow with new URL for instant indexing."""
    results = {}
    if not url:
        return results
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            # Google ping
            try:
                async with s.get(
                    f"https://www.google.com/ping?sitemap={url}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    results["google"] = r.status == 200
            except Exception:
                results["google"] = False

            # Bing ping
            try:
                async with s.get(
                    f"https://www.bing.com/ping?sitemap={url}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    results["bing"] = r.status == 200
            except Exception:
                results["bing"] = False

    except Exception as e:
        log.warning("Search engine ping error: %s", e)
    return results


# ── Master Runner ─────────────────────────────────────────────────────────────

async def run_content_velocity(topic: str | None = None,
                                product_name: str = PRODUCT_NAME,
                                product_url: str = PRODUCT_URL,
                                price: str = PRODUCT_PRICE) -> dict:
    """
    Master function: pick trending topic → generate 10 content formats
    → publish Shopify blog + Telegram simultaneously → log everything.
    """
    log.info("ContentVelocityEngine: starting run")

    if topic is None:
        topics = await _fetch_trending()
        topic = topics[0] if topics else "KI Business Automatisierung 2026"

    published = _load_published()
    title_hash = _title_hash(topic)
    if title_hash in published:
        log.info("ContentVelocity: topic already published, skipping: %s", topic)
        return {"ok": True, "skipped": True, "reason": "duplicate", "topic": topic}

    content = await generate_master_content(topic, product_name, product_url, price)
    if not content:
        return {"ok": False, "error": "Content generation failed", "topic": topic}

    blog_title = content.get("blog_article_title", topic)
    blog_body  = content.get("blog_article", "")
    tg_text    = (
        f"<b>{blog_title}</b>\n\n"
        f"{content.get('instagram_caption', '')[:400]}\n\n"
        f"<a href='{product_url}'>→ {product_name} ({price})</a>"
    )

    # Publish blog + Telegram in parallel
    blog_result, tg_result = await asyncio.gather(
        publish_shopify_blog(blog_title, blog_body),
        send_telegram_broadcast(tg_text),
        return_exceptions=True,
    )

    blog_result = blog_result if isinstance(blog_result, dict) else {"ok": False, "error": str(blog_result)}
    tg_result   = tg_result   if isinstance(tg_result, dict)   else {"ok": False, "error": str(tg_result)}

    # Ping search engines with new blog URL
    ping_result = {}
    if blog_result.get("url"):
        ping_result = await _ping_search_engines(blog_result["url"])

    published.add(title_hash)
    _save_published(published)

    summary = {
        "topic": topic,
        "blog_title": blog_title,
        "blog": blog_result,
        "telegram": tg_result,
        "search_engine_pings": ping_result,
        "content_formats_generated": [k for k in content if k not in ("blog_article",)],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _append_log(summary)

    log.info("ContentVelocity done: blog=%s tg=%s topic=%s",
             blog_result.get("ok"), tg_result.get("ok"), topic[:40])

    return {"ok": True, "summary": summary, "content": content}


def get_latest_content() -> list[dict]:
    """Return last 20 published content entries for dashboard display."""
    try:
        entries = json.loads(LOG_FILE.read_text())
        return entries[-20:]
    except Exception:
        return []
