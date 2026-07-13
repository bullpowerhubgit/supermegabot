"""
TrafficSwarm — Master Traffic & SEO Coordinator for SuperMegaBot.

Orchestrates ALL traffic modules simultaneously. Features not in any
existing module:
 1. UTM auto-tagger — every URL gets tracked
 2. Content multiplier — 1 topic → 10 platform formats
 3. Traffic velocity monitor — drop detection + Telegram alert
 4. HackerNews auto-submit
 5. Backlink email outreach generator
 6. RSS Atom feed builder
 7. Keyword cannibalization detector
 8. Internal link injector
 9. Content freshness updater
10. Full swarm — all modules parallel in one call
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("TrafficSwarm")

# ── Config ─────────────────────────────────────────────────────────────────────
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL    = os.getenv("TELEGRAM_CHANNEL_ID", "")   # marketing → public channel
TG_CHAT         = _TG_CHANNEL or ""                        # no private spam
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SITE_URL        = os.getenv("SITE_URL", "https://supermegabot-production.up.railway.app")
EMAIL_FROM      = os.getenv("SENDGRID_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
SENDGRID_KEY    = os.getenv("SENDGRID_API_KEY", "")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "traffic_swarm"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

HAIKU_MODEL = "claude-haiku-4-5-20251001"

# ── Telegram helper ────────────────────────────────────────────────────────────
async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096]},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as _e:
        log.debug("swarm suppressed: %s", _e)


# ── Claude Haiku helper ────────────────────────────────────────────────────────
async def _claude(prompt: str, system: str = "You are an expert marketing copywriter.") -> str:
    try:
        from modules.ai_client import ai_complete
        r = await ai_complete(prompt, max_tokens=1200)
        return r if r else ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ai_complete fallback: {e}")
        return ""

def build_utm_url(
    url: str,
    source: str,
    medium: str = "social",
    campaign: str = "",
    content: str = "",
    term: str = "",
) -> str:
    """Append UTM parameters to any URL and return the tagged version."""
    campaign = campaign or f"bullpowerhub_{datetime.now(timezone.utc).strftime('%Y%m')}"
    params: dict[str, str] = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
    }
    if content:
        params["utm_content"] = content
    if term:
        params["utm_term"] = term

    parsed = urllib.parse.urlparse(url)
    existing = dict(urllib.parse.parse_qsl(parsed.query))
    existing.update(params)
    new_query = urllib.parse.urlencode(existing)
    tagged = parsed._replace(query=new_query).geturl()

    # Log to Supabase asynchronously (fire-and-forget via background task)
    asyncio.ensure_future(_log_utm_to_supabase(tagged, source, medium, campaign))
    return tagged


async def _log_utm_to_supabase(url: str, source: str, medium: str, campaign: str) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            await s.post(
                f"{SUPABASE_URL}/rest/v1/utm_clicks",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                    "Accept-Profile": "public",
                    "Content-Profile": "public",
                },
                json={
                    "url": url, "source": source, "medium": medium,
                    "campaign": campaign,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception as _e:
        log.debug("swarm suppressed: %s", _e)


# ─────────────────────────────────────────────────────────────────────────────
# 2. CONTENT MULTIPLIER — 1 topic → 10 platform formats
# ─────────────────────────────────────────────────────────────────────────────

async def multiply_content(topic: str, product_url: str = SITE_URL) -> dict:
    """Generate 10 platform-specific content pieces from one topic using Claude."""
    tagged_url = build_utm_url(product_url, source="content_swarm", medium="referral",
                                content=hashlib.md5(topic.encode()).hexdigest()[:8])
    prompt = f"""Topic: "{topic}"
Product URL: {tagged_url}

Generate ALL 10 content pieces in valid JSON (no markdown). Keys:
- tweet: max 240 chars, 3 hashtags, CTA with URL
- linkedin_post: 3 paragraphs, professional German, 5 hashtags
- reddit_title: 75 chars max, curiosity hook
- reddit_body: 200 words, value-first, no spam, mention URL subtly
- medium_title: SEO-optimized H1, 60 chars
- medium_intro: first 150 words of Medium article
- pinterest_caption: 150 chars, 10 hashtags
- youtube_description: 300 chars, keywords dense, URL in first line
- email_subject: 50 chars, open-rate optimized
- email_preview: 90 char preview text
- push_title: 50 chars
- push_body: 90 chars, urgency
- quora_question: question to create/find on Quora
- quora_answer_draft: 200 word expert answer with subtle mention
- seo_meta_title: 60 chars, keyword first
- seo_meta_description: 155 chars, includes CTA

Return ONLY valid JSON."""

    raw = await _claude(prompt)
    try:
        # Strip markdown fences if present
        clean = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(clean)
        data["topic"] = topic
        data["tagged_url"] = tagged_url
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        return data
    except Exception as e:
        log.error("Content multiplier JSON parse failed: %s", e)
        return {"topic": topic, "error": str(e), "raw": raw[:500]}


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRAFFIC VELOCITY MONITOR
# ─────────────────────────────────────────────────────────────────────────────

async def monitor_traffic_velocity() -> dict:
    """Compare today's leads/events vs yesterday. Alert on >20% drop."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "reason": "Supabase not configured"}

    now = datetime.now(timezone.utc)
    today_start  = (now - timedelta(hours=24)).isoformat()
    yesterday_start = (now - timedelta(hours=48)).isoformat()

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    async def count_events(since: str, until: str) -> int:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.get(
                    f"{SUPABASE_URL}/rest/v1/lead_events",
                    headers={**headers, "Prefer": "count=exact", "Range": "0-0"},
                    params={"created_at": f"gte.{since}", "and": f"(created_at.lte.{until})"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    cr = r.headers.get("Content-Range", "0/0")
                    total = cr.split("/")[-1]
                    return int(total) if total.isdigit() else 0
        except Exception:
            return 0

    today_count = await count_events(today_start, now.isoformat())
    yesterday_count = await count_events(yesterday_start, today_start)

    result = {
        "today_leads": today_count,
        "yesterday_leads": yesterday_count,
        "ok": True,
    }

    if yesterday_count > 0:
        delta_pct = ((today_count - yesterday_count) / yesterday_count) * 100
        result["delta_pct"] = round(delta_pct, 1)

        if delta_pct <= -20:
            alert = (
                f"🚨 Traffic Drop Alert!\n"
                f"Leads heute: {today_count} | gestern: {yesterday_count}\n"
                f"Drop: {delta_pct:.1f}%\n"
                f"→ Überprüfe Ads, SEO, Social-Posts!"
            )
            await _tg(alert)
            result["alert_sent"] = True
        elif delta_pct >= 20:
            await _tg(f"📈 Traffic Spike! +{delta_pct:.1f}% Leads heute ({today_count} vs {yesterday_count} gestern)")
            result["spike_alert"] = True

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. HACKERNEWS AUTO-SUBMIT
# ─────────────────────────────────────────────────────────────────────────────

async def post_to_hackernews(title: str, url: str) -> dict:
    """
    Submit to HackerNews via Firebase API (HN's official API).
    Note: actual submission requires HN account session — this prepares
    the submission data and returns the direct submit URL for automation.
    """
    tagged = build_utm_url(url, source="hackernews", medium="social")
    hn_submit = f"https://news.ycombinator.com/submitlink?u={urllib.parse.quote(tagged)}&t={urllib.parse.quote(title)}"

    # Try HN API to check if story exists
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                f"https://hn.algolia.com/api/v1/search?query={urllib.parse.quote(title[:50])}&tags=story&hitsPerPage=3",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                hits = data.get("hits", [])
                if hits:
                    return {"ok": True, "exists": True, "hn_id": hits[0].get("objectID"),
                            "points": hits[0].get("points", 0)}
    except Exception as _e:
        log.debug("swarm suppressed: %s", _e)

    log.info("HN submit URL prepared: %s", hn_submit[:100])
    return {"ok": True, "submit_url": hn_submit, "title": title}


# ─────────────────────────────────────────────────────────────────────────────
# 5. BACKLINK EMAIL OUTREACH GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

OUTREACH_TARGETS = [
    ("shopify.community", "Shopify Community Forum"),
    ("ecommercefuel.com", "eCommerceFuel"),
    ("practicalecommerce.com", "Practical Ecommerce"),
    ("oberlo.com", "Oberlo Blog"),
    ("shopifypartners.com", "Shopify Partners Blog"),
    ("starterstory.com", "Starter Story"),
    ("sidehustleschool.com", "Side Hustle School"),
    ("foundr.com", "Foundr Magazine"),
]


async def generate_outreach_emails(count: int = 5) -> list[dict]:
    """Generate personalized backlink outreach emails for top sites."""
    targets = OUTREACH_TARGETS[:count]
    emails = []

    for domain, site_name in targets:
        prompt = f"""Write a SHORT, personalized backlink outreach email (German or English, max 150 words).
Site: {site_name} ({domain})
Our tool: BullPower Hub — AI-powered Shopify automation (fully autonomous, posting to all social platforms 24/7)
URL: {SITE_URL}

Write as Rudolf Sarkany, solo developer. Be genuine, not salesy. Find mutual value.
Return JSON: {{"subject": "...", "body": "...", "to_domain": "{domain}"}}"""

        raw = await _claude(prompt)
        try:
            clean = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip(), flags=re.MULTILINE)
            email = json.loads(clean)
            email["from"] = EMAIL_FROM
            emails.append(email)
        except Exception as e:
            log.warning("Outreach email parse failed for %s: %s", domain, e)

    # Send via EmailBrain if SendGrid key is available
    if SENDGRID_KEY and emails:
        sent = await _send_outreach_via_sendgrid(emails[:3])  # cap at 3 per run
        for i, e in enumerate(emails[:3]):
            e["sent"] = sent.get(e.get("to_domain", ""), False)

    # Save for review
    out_file = DATA_DIR / f"outreach_{datetime.now().strftime('%Y%m%d')}.json"
    out_file.write_text(json.dumps(emails, indent=2, ensure_ascii=False))

    return emails


async def _send_outreach_via_sendgrid(emails: list[dict]) -> dict:
    sent = {}
    if not SENDGRID_KEY:
        return sent
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        for email in emails:
            domain = email.get("to_domain", "")
            contact = f"hello@{domain}"
            try:
                async with s.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {SENDGRID_KEY}",
                             "Content-Type": "application/json"},
                    json={
                        "personalizations": [{"to": [{"email": contact}]}],
                        "from": {"email": EMAIL_FROM, "name": "Rudolf Sarkany"},
                        "subject": email.get("subject", "Collaboration Opportunity"),
                        "content": [{"type": "text/plain", "value": email.get("body", "")}],
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    sent[domain] = r.status in (200, 202)
            except Exception as e:
                log.warning("SendGrid outreach failed for %s: %s", domain, e)
                sent[domain] = False
    return sent


# ─────────────────────────────────────────────────────────────────────────────
# 6. RSS ATOM FEED BUILDER
# ─────────────────────────────────────────────────────────────────────────────

async def build_rss_feed(entries: list[dict] | None = None) -> str:
    """
    Build a valid RSS 2.0 + Atom feed from recent Shopify blog posts.
    entries: [{title, url, body, published_at}]
    Returns: XML string
    """
    if entries is None:
        entries = await _fetch_shopify_blog_posts()

    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "BullPower Hub Blog"
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = "KI-gestützte E-Commerce Automatisierung"
    ET.SubElement(channel, "language").text = "de-DE"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    atom_link = ET.SubElement(channel, "atom:link")
    atom_link.set("href", f"{SITE_URL}/rss.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for entry in entries[:20]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = entry.get("title", "")
        tagged_url = build_utm_url(entry.get("url", SITE_URL), source="rss", medium="feed")
        ET.SubElement(item, "link").text = tagged_url
        ET.SubElement(item, "guid").text = tagged_url
        ET.SubElement(item, "description").text = (entry.get("body", "")[:500] + "…")[:500]
        pub = entry.get("published_at", datetime.now(timezone.utc).isoformat())
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            ET.SubElement(item, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            ET.SubElement(item, "pubDate").text = pub

    feed_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        rss, encoding="unicode", xml_declaration=False
    )

    # Save to data dir for serving
    feed_path = DATA_DIR / "feed.xml"
    feed_path.write_text(feed_xml, encoding="utf-8")
    log.info("RSS feed built: %d entries → %s", len(entries), feed_path)
    return feed_xml


async def _fetch_shopify_blog_posts(limit: int = 20) -> list[dict]:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                articles = data.get("articles", [])
                return [
                    {
                        "title": a.get("title", ""),
                        "url": f"https://{SHOPIFY_DOMAIN}/blogs/{a.get('blog_id', 'news')}/{a.get('handle', '')}",
                        "body": re.sub(r"<[^>]+>", "", a.get("body_html", ""))[:500],
                        "published_at": a.get("published_at", ""),
                    }
                    for a in articles
                ]
    except Exception as e:
        log.error("Shopify blog fetch failed: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 7. KEYWORD CANNIBALIZATION DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

async def detect_keyword_cannibalization() -> dict:
    """Find Shopify products/pages competing for the same keywords."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "reason": "Shopify not configured"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": 100, "fields": "id,title,tags,handle"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                products = data.get("products", [])
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Build keyword → product map
    kw_map: dict[str, list[str]] = {}
    for p in products:
        words = set(re.findall(r"\b\w{4,}\b", (p.get("title", "") + " " + p.get("tags", "")).lower()))
        for w in words:
            kw_map.setdefault(w, []).append(p.get("title", "")[:40])

    cannibalized = {kw: titles for kw, titles in kw_map.items() if len(titles) > 1}

    if cannibalized:
        top = list(cannibalized.items())[:5]
        msg = "⚠️ Keyword-Kannibalisierung gefunden:\n"
        for kw, titles in top:
            msg += f"• '{kw}': {', '.join(titles[:3])}\n"
        await _tg(msg)

    return {"ok": True, "cannibalized_keywords": len(cannibalized),
            "top_conflicts": list(cannibalized.items())[:10]}


# ─────────────────────────────────────────────────────────────────────────────
# 8. INTERNAL LINK INJECTOR
# ─────────────────────────────────────────────────────────────────────────────

async def inject_internal_links(blog_html: str, products: list[dict]) -> str:
    """
    Scan blog post HTML for product name mentions → auto-link to product page.
    products: [{title, handle}]
    """
    for product in products:
        title = product.get("title", "")
        handle = product.get("handle", "")
        if not title or not handle or len(title) < 4:
            continue
        product_url = f"https://{SHOPIFY_DOMAIN}/products/{handle}"
        link_tag = f'<a href="{product_url}" title="{title}">{title}</a>'
        # Only replace first occurrence, skip if already linked
        pattern = rf"(?<!href=\")(?<!title=\")(?<!</a>)\b({re.escape(title)})\b(?![^<]*?>)"
        blog_html = re.sub(pattern, link_tag, blog_html, count=1, flags=re.IGNORECASE)

    return blog_html


# ─────────────────────────────────────────────────────────────────────────────
# 9. CONTENT FRESHNESS UPDATER
# ─────────────────────────────────────────────────────────────────────────────

async def refresh_stale_content(days_old: int = 90) -> dict:
    """
    Find Shopify blog posts older than N days.
    Use Claude to add a 'Updated:' section with fresh data.
    """
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {"ok": False, "reason": "Shopify not configured"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"limit": 10, "published_before": cutoff[:10], "status": "active"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                articles = data.get("articles", [])
    except Exception as e:
        return {"ok": False, "error": str(e)}

    updated = 0
    for article in articles[:3]:  # cap at 3 per run
        title = article.get("title", "")
        body = re.sub(r"<[^>]+>", "", article.get("body_html", ""))[:800]

        update_text = await _claude(
            f"This blog post is {days_old}+ days old: '{title}'\n\nOriginal content: {body}\n\n"
            f"Write a short 2-sentence 'Update {datetime.now().year}:' paragraph with fresh insights. "
            f"Return only the paragraph text, no quotes."
        )
        if not update_text:
            continue

        new_body = (article.get("body_html", "") +
                    f'<p><strong>Update {datetime.now().year}:</strong> {update_text}</p>')

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                await s.put(
                    f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/articles/{article['id']}.json",
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                             "Content-Type": "application/json"},
                    json={"article": {"id": article["id"], "body_html": new_body}},
                    timeout=aiohttp.ClientTimeout(total=15),
                )
            updated += 1
            log.info("Refreshed article: %s", title)
        except Exception as e:
            log.error("Article update failed: %s", e)

    return {"ok": True, "articles_checked": len(articles), "articles_updated": updated}


# ─────────────────────────────────────────────────────────────────────────────
# 10. FULL SWARM — all modules in one parallel call
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_traffic_swarm(topic: str | None = None) -> dict:
    """
    THE master function. Runs ALL traffic and SEO modules simultaneously.
    One call → maximum traffic impact across every platform and channel.
    """
    t0 = time.monotonic()
    log.info("TrafficSwarm FULL RUN starting")

    # Get topic if not provided
    if not topic:
        trending = await _get_trending_topic()
        topic = trending or "KI-gestützte Shopify-Automatisierung"

    # Build content for all platforms
    content_task = asyncio.create_task(multiply_content(topic))

    # Import and run all existing traffic modules in parallel
    async def _run_viral():
        try:
            from modules.viral_traffic_machine import run_viral_traffic_machine
            return await run_viral_traffic_machine()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_seo():
        try:
            from modules.seo_dominator import run_seo_dominator
            return await run_seo_dominator(full=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_backlinks():
        try:
            from modules.backlink_bomber import run_backlink_bomber
            return await run_backlink_bomber()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_brutus():
        try:
            from modules.brutus_traffic_engine import run_brutus_traffic_engine
            return await run_brutus_traffic_engine()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_content_velocity():
        try:
            from modules.content_velocity_engine import run_content_velocity
            return await run_content_velocity()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Fire EVERYTHING in parallel
    results = await asyncio.gather(
        content_task,
        _run_viral(),
        _run_seo(),
        _run_backlinks(),
        _run_brutus(),
        _run_content_velocity(),
        monitor_traffic_velocity(),
        build_rss_feed(),
        return_exceptions=True,
    )

    labels = ["content", "viral", "seo", "backlinks", "brutus", "content_velocity",
              "traffic_monitor", "rss_feed"]
    summary = {}
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            summary[label] = {"ok": False, "error": str(result)}
        elif isinstance(result, dict):
            summary[label] = {"ok": result.get("ok", True)}
        elif isinstance(result, str):
            summary[label] = {"ok": True, "chars": len(result)}
        else:
            summary[label] = {"ok": True}

    elapsed = round(time.monotonic() - t0, 1)
    ok_count = sum(1 for v in summary.values() if v.get("ok"))

    await _tg(
        f"🌊 TrafficSwarm abgeschlossen!\n"
        f"Topic: {topic[:60]}\n"
        f"✅ {ok_count}/{len(labels)} Module OK\n"
        f"⏱ {elapsed}s\n"
        f"Plattformen: Viral+Reddit+Medium+LinkedIn+YouTube+Pinterest+Instagram+Telegram+SEO+Backlinks+RSS"
    )

    log.info("TrafficSwarm FULL RUN done in %.1fs: %d/%d OK", elapsed, ok_count, len(labels))
    return {"ok": True, "topic": topic, "elapsed_s": elapsed,
            "modules_ok": ok_count, "modules_total": len(labels), "summary": summary}


async def _get_trending_topic() -> str:
    """Fetch one trending topic from Google Trends DE RSS."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                text = await r.text()
        root = ET.fromstring(text)
        items = root.findall(".//item/title")
        if items:
            return items[0].text or ""
    except Exception as _e:
        log.debug("swarm suppressed: %s", _e)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER TASK WRAPPERS
# ─────────────────────────────────────────────────────────────────────────────

async def task_full_traffic_swarm() -> str:
    r = await run_full_traffic_swarm()
    return f"TrafficSwarm: {r['modules_ok']}/{r['modules_total']} OK, topic={r['topic'][:40]}"


async def task_traffic_velocity_check() -> str:
    r = await monitor_traffic_velocity()
    today = r.get("today_leads", 0)
    delta = r.get("delta_pct", 0)
    return f"TrafficVelocity: {today} leads heute, {delta:+.1f}% vs gestern"


async def task_rss_feed_rebuild() -> str:
    xml = await build_rss_feed()
    return f"RSS Feed: {len(xml)} chars"


async def task_content_freshness() -> str:
    r = await refresh_stale_content(days_old=90)
    return f"ContentFreshness: {r.get('articles_updated', 0)} articles refreshed"


async def task_backlink_outreach() -> str:
    emails = await generate_outreach_emails(count=5)
    sent = sum(1 for e in emails if e.get("sent"))
    return f"BacklinkOutreach: {len(emails)} drafts, {sent} sent"


async def task_kw_cannibalization_check() -> str:
    r = await detect_keyword_cannibalization()
    return f"KWCannibalization: {r.get('cannibalized_keywords', 0)} conflicts"
