#!/usr/bin/env python3
"""
RSS Feed Publisher — generiert RSS/Atom Feed aus Shopify Blog-Artikeln.
Speichert feed.rss in data/ und sendet URL via Telegram.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import aiohttp

log = logging.getLogger("RSSPublisher")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOP_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
STORE_URL   = "https://ineedit.com.co"
DATA_DIR    = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
RSS_FILE    = DATA_DIR / "feed.rss"
BLOG_ID     = os.getenv("SHOPIFY_BLOG_ID", "127011258755")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")


async def generate_rss_feed(limit: int = 20) -> dict:
    """Fetch latest blog articles from Shopify and generate RSS XML."""
    if not SHOP_TOKEN or not SHOP_DOMAIN:
        return {"ok": False, "error": "no shopify credentials"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/blogs/{BLOG_ID}/articles.json",
                headers={"X-Shopify-Access-Token": SHOP_TOKEN},
                params={"limit": limit, "published_status": "published"},
            ) as r:
                data = await r.json(content_type=None)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    articles = data.get("articles", [])
    if not articles:
        return {"ok": False, "error": "no articles returned"}

    now_rfc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    for a in articles:
        title   = escape(a.get("title", ""))
        handle  = a.get("handle", "")
        link    = f"{STORE_URL}/blogs/must-have-trends-tipps/{handle}"
        summary = escape(a.get("summary_html") or a.get("body_html", "")[:200])
        pub_date = a.get("published_at", now_rfc)
        try:
            from email.utils import format_datetime
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(pub_date.replace("Z", "+00:00"))
            pub_date = format_datetime(dt)
        except Exception:
            pass
        items.append(f"""    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{summary}</description>
      <pubDate>{pub_date}</pubDate>
      <guid>{link}</guid>
    </item>""")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>ineedit.com.co — Must-Have Trends &amp; Tipps</title>
    <link>{STORE_URL}</link>
    <description>E-Commerce Tipps, Dropshipping Guides, KI-Automatisierung — BullPower Hub</description>
    <language>de</language>
    <lastBuildDate>{now_rfc}</lastBuildDate>
    <atom:link href="{STORE_URL}/feed.rss" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    RSS_FILE.write_text(rss_xml, encoding="utf-8")
    log.info("RSS feed written: %d articles → %s", len(articles), RSS_FILE)

    # Telegram notification
    if TG_TOKEN and TG_CHAT:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                await s.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT,
                          "text": f"📡 *RSS Feed aktualisiert*\n{len(articles)} Artikel\nFeed: {STORE_URL}/feed.rss",
                          "parse_mode": "Markdown"},
                )
        except Exception:
            pass

    return {"ok": True, "articles": len(articles), "file": str(RSS_FILE)}
