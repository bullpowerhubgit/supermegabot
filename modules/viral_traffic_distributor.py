#!/usr/bin/env python3
"""
Viral Traffic Distributor — Echtzeit-Trends → 8-Kanal Omnichannel Distribution.

Pipeline: scan_realtime_trends() → generate_omnichannel_content() → distribute_everywhere()
Kanäle: Telegram, LinkedIn, Twitter/X, Reddit-style, Email (Klaviyo), Shopify Blog,
        Dev.to, IndexNow + Bing/Google ping, GitHub Pages (via API), Medium
BrutusClone blast nach jedem Cycle. Quantum self-improvement nach 10 Cycles.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("ViralTrafficDistributor")

# ── Env vars ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
LINKEDIN_TOKEN  = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN    = os.getenv("LINKEDIN_PERSON_URN", "")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_SECRET  = os.getenv("TWITTER_API_SECRET", "")
TWITTER_TOKEN   = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_TSECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER     = os.getenv("SHOPIFY_API_VERSION", "2024-10")
DEVTO_KEY       = os.getenv("DEVTO_API_KEY", "")
INDEXNOW_KEY    = os.getenv("INDEXNOW_KEY", "supermegabot2024")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER     = os.getenv("GITHUB_USER", "bullpowerhubgit")

DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp"))
_POSTED_FILE = DATA_DIR / "vtd_posted.json"
_CYCLE_COUNT_FILE = DATA_DIR / "vtd_cycles.json"

# ── Trend sources (no API key needed) ────────────────────────────────────────
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=DE"
REDDIT_HOT_JSON   = "https://www.reddit.com/r/all/hot.json?limit=10"
REDDIT_RISING_JSON = "https://www.reddit.com/r/entrepreneur/rising.json?limit=5"

_UA = "Mozilla/5.0 (compatible; SuperMegaBot/2.0; +https://autopilot-store-suite-fmbka.myshopify.com)"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_posted() -> set:
    try:
        return set(json.loads(_POSTED_FILE.read_text()))
    except Exception:
        return set()


def _save_posted(posted: set) -> None:
    try:
        _POSTED_FILE.write_text(json.dumps(list(posted)[-500:]))
    except Exception:
        pass


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _cycle_count() -> int:
    try:
        return json.loads(_CYCLE_COUNT_FILE.read_text()).get("count", 0)
    except Exception:
        return 0


def _increment_cycle() -> int:
    n = _cycle_count() + 1
    try:
        _CYCLE_COUNT_FILE.write_text(json.dumps({"count": n}))
    except Exception:
        pass
    return n


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


# ── 1. Trend Scanner ──────────────────────────────────────────────────────────

async def scan_realtime_trends() -> list[dict]:
    """Scan Google Trends RSS + Reddit hot — no API keys required."""
    topics: list[dict] = []
    headers = {"User-Agent": _UA, "Accept": "application/json, text/xml"}

    async with aiohttp.ClientSession(headers=headers) as s:
        # Google Trends RSS (DE)
        try:
            async with s.get(GOOGLE_TRENDS_RSS, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    xml_text = await r.text()
                    root = ET.fromstring(xml_text)
                    for item in root.findall(".//item")[:8]:
                        title_el = item.find("title")
                        traffic_el = item.find("{https://trends.google.com/trending/rss}approx_traffic")
                        if title_el is not None and title_el.text:
                            topics.append({
                                "topic": title_el.text.strip(),
                                "source": "google_trends_de",
                                "traffic": traffic_el.text if traffic_el is not None else "1K+",
                            })
        except Exception as e:
            log.debug("Google Trends RSS error: %s", e)

        # Reddit /r/all hot
        try:
            async with s.get(
                REDDIT_HOT_JSON,
                headers={**headers, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    for post in data.get("data", {}).get("children", [])[:5]:
                        d = post.get("data", {})
                        title = d.get("title", "")
                        if title and len(title) > 10:
                            topics.append({
                                "topic": title[:120],
                                "source": "reddit_hot",
                                "traffic": f"{d.get('score', 0):,} upvotes",
                            })
        except Exception as e:
            log.debug("Reddit hot error: %s", e)

        # Reddit /r/entrepreneur rising
        try:
            async with s.get(
                REDDIT_RISING_JSON,
                headers={**headers, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    for post in data.get("data", {}).get("children", [])[:3]:
                        d = post.get("data", {})
                        title = d.get("title", "")
                        if title and len(title) > 10:
                            topics.append({
                                "topic": title[:120],
                                "source": "reddit_entrepreneur",
                                "traffic": f"{d.get('score', 0):,} upvotes",
                            })
        except Exception as e:
            log.debug("Reddit entrepreneur error: %s", e)

    log.info("Trends found: %d topics", len(topics))
    return topics


# ── 2. Omnichannel Content Generator ─────────────────────────────────────────

async def generate_omnichannel_content(trend: dict) -> dict:
    """AI generates 8 content variants from one trending topic."""
    topic = trend.get("topic", "trending topic")
    source = trend.get("source", "")
    traffic = trend.get("traffic", "")

    prompt = f"""Trending topic: "{topic}" (source: {source}, traffic: {traffic})

Erstelle 8 verschiedene Content-Varianten auf DEUTSCH für maximale Reichweite.
Jede Variante ist für einen anderen Kanal optimiert.
Antworte NUR mit diesem JSON (kein Markdown drumherum):

{{
  "tweet": "Max 280 Zeichen. Viral, mit 3 Hashtags. Hook im ersten Satz.",
  "linkedin": "3 Absätze. Professioneller Insight. Ende mit Frage an Community. Max 1200 Zeichen.",
  "telegram": "Kurz, mit Emojis. Max 500 Zeichen. Direkt und aktivierend.",
  "email_subject": "Max 50 Zeichen. Neugier wecken.",
  "email_body": "150 Wörter. Story-Format. CTA am Ende.",
  "blog_intro": "200 Wörter. SEO-optimiert. H1 Überschrift + Intro-Paragraph.",
  "shopify_product": "Produkttitel (max 60 Zeichen) + Beschreibung (100 Wörter) + 5 Tags.",
  "seo_meta": "title (60 Zeichen) + description (155 Zeichen) für Google."
}}"""

    ai_raw = await _ai(prompt, max_tokens=1200)
    try:
        start = ai_raw.find("{")
        end = ai_raw.rfind("}") + 1
        content = json.loads(ai_raw[start:end])
    except Exception:
        # Fallback content
        content = {
            "tweet": f"🔥 Trending: {topic[:200]} #trending #viral #business",
            "linkedin": f"Spannendes Trend-Thema: {topic}\n\nDas zeigt: Die Welt verändert sich schnell. Was denkt ihr darüber?",
            "telegram": f"🔥 Trending jetzt: {topic[:300]}",
            "email_subject": f"Trending: {topic[:45]}",
            "email_body": f"Hallo,\n\n{topic} ist gerade viral. Das bedeutet neue Chancen für dein Business.\n\nJetzt handeln!",
            "blog_intro": f"# {topic}\n\n{topic} ist derzeit eines der meistdiskutierten Themen.",
            "shopify_product": f"{topic[:55]} | Trending\nAktuelle Trendprodukte. trending,viral,bestseller,2026,DE",
            "seo_meta": f"title: {topic[:55]} | meta: {topic[:150]} — jetzt entdecken.",
        }
    content["topic"] = topic
    content["source"] = source
    content["hash"] = _hash(topic)
    return content


# ── 3. Channel Distributors ───────────────────────────────────────────────────

async def _post_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status == 200
    except Exception as e:
        log.debug("Telegram post error: %s", e)
        return False


async def _post_linkedin(text: str) -> bool:
    if not LINKEDIN_TOKEN or not LINKEDIN_URN:
        return False
    try:
        payload = {
            "author": LINKEDIN_URN,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text[:3000]},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}", "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("LinkedIn post error: %s", e)
        return False


async def _post_shopify_blog(title: str, body: str, tags: str) -> bool:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False
    try:
        payload = {
            "article": {
                "title": title[:255],
                "body_html": f"<p>{body}</p>",
                "tags": tags[:255],
                "published": True,
            }
        }
        async with aiohttp.ClientSession() as s:
            # Use first blog (id=1 or fetch first)
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                blogs = (await r.json(content_type=None)).get("blogs", [])
            blog_id = blogs[0]["id"] if blogs else None
            if not blog_id:
                return False
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("Shopify blog error: %s", e)
        return False


async def _post_devto(title: str, body: str, tags: list) -> bool:
    if not DEVTO_KEY:
        return False
    try:
        payload = {
            "article": {
                "title": title[:255],
                "body_markdown": body[:10000],
                "tags": tags[:4],
                "published": True,
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://dev.to/api/articles",
                headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("Dev.to post error: %s", e)
        return False


async def _ping_indexnow(url: str) -> bool:
    """Submit URL to IndexNow (Bing + Google via Yandex bridge)."""
    try:
        shop_domain = SHOPIFY_DOMAIN or "autopilot-store-suite-fmbka.myshopify.com"
        payload = {
            "host": shop_domain,
            "key": INDEXNOW_KEY,
            "urlList": [url],
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.indexnow.org/indexnow",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                ok = r.status in (200, 202)
            # Also ping Bing
            async with s.post(
                "https://www.bing.com/indexnow",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r2:
                ok = ok or r2.status in (200, 202)
        return ok
    except Exception as e:
        log.debug("IndexNow error: %s", e)
        return False


async def _post_klaviyo_campaign(subject: str, body: str) -> bool:
    if not KLAVIYO_KEY:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            # Create campaign
            payload = {
                "data": {
                    "type": "campaign",
                    "attributes": {
                        "name": f"VTD {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} — {subject[:40]}",
                        "audiences": {"included": []},
                        "send_strategy": {"method": "immediate"},
                        "campaign-messages": {
                            "data": [{
                                "type": "campaign-message",
                                "attributes": {
                                    "channel": "email",
                                    "label": subject[:100],
                                    "content": {
                                        "subject": subject[:255],
                                        "preview_text": subject[:90],
                                        "from_email": "noreply@autopilot-store-suite-fmbka.myshopify.com",
                                        "from_label": "SuperMegaBot",
                                        "body": f"<html><body><p>{body}</p></body></html>",
                                    }
                                }
                            }]
                        }
                    }
                }
            }
            async with s.post(
                "https://a.klaviyo.com/api/campaigns/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                    "revision": "2024-10-15",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.debug("Klaviyo campaign error: %s", e)
        return False


async def _post_github_pages(title: str, body: str, slug: str) -> bool:
    """Commit a new post to GitHub Pages blog via API."""
    if not GITHUB_TOKEN or not GITHUB_USER:
        return False
    try:
        import base64
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"_posts/{date_str}-{slug[:50]}.md"
        content_md = f"---\nlayout: post\ntitle: \"{title[:100]}\"\ndate: {date_str}\ncategories: trending\n---\n\n{body}"
        encoded = base64.b64encode(content_md.encode()).decode()
        repo = f"{GITHUB_USER}/{GITHUB_USER}.github.io"
        async with aiohttp.ClientSession() as s:
            async with s.put(
                f"https://api.github.com/repos/{repo}/contents/{filename}",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
                json={
                    "message": f"post: {title[:60]}",
                    "content": encoded,
                    "branch": "main",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("GitHub Pages error: %s", e)
        return False


# ── 4. Distribute Everywhere ──────────────────────────────────────────────────

async def distribute_everywhere(content: dict) -> dict:
    """Fire all channels in parallel. Returns per-channel results."""
    topic = content.get("topic", "")
    results: dict[str, bool] = {}

    shop_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://autopilot-store-suite-fmbka.myshopify.com"

    # Build blog title from blog_intro first line
    blog_intro = content.get("blog_intro", "")
    blog_title_raw = blog_intro.split("\n")[0].lstrip("# ").strip() or topic[:60]
    slug = blog_title_raw.lower().replace(" ", "-")[:50]
    blog_article_url = f"{shop_url}/blogs/news/{slug}"

    # Parse shopify_product field
    sp_raw = content.get("shopify_product", "")
    sp_lines = sp_raw.split("\n")
    sp_title = sp_lines[0][:60] if sp_lines else topic[:60]
    sp_body = "\n".join(sp_lines[1:])[:500] if len(sp_lines) > 1 else sp_raw[:500]
    sp_tags_raw = sp_lines[-1] if len(sp_lines) > 2 else "trending"
    sp_tags = [t.strip() for t in sp_tags_raw.split(",")][:4]

    tasks = [
        ("telegram",       _post_telegram(content.get("telegram", ""))),
        ("linkedin",       _post_linkedin(content.get("linkedin", ""))),
        ("shopify_blog",   _post_shopify_blog(blog_title_raw, blog_intro, ",".join(sp_tags))),
        ("devto",          _post_devto(blog_title_raw, content.get("blog_intro", ""), sp_tags)),
        ("klaviyo",        _post_klaviyo_campaign(content.get("email_subject", ""), content.get("email_body", ""))),
        ("indexnow",       _ping_indexnow(blog_article_url)),
        ("github_pages",   _post_github_pages(blog_title_raw, blog_intro, slug)),
    ]

    done = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (name, _), result in zip(tasks, done):
        results[name] = result is True

    hits = sum(1 for v in results.values() if v)
    log.info("Distributed '%s': %d/%d channels OK", topic[:50], hits, len(tasks))
    return results


# ── 5. BrutusClone blast ──────────────────────────────────────────────────────

async def _brutus_blast(content: dict) -> None:
    try:
        from modules.brutus_core import fire
        shop_url = f"https://{SHOPIFY_DOMAIN}" if SHOPIFY_DOMAIN else "https://autopilot-store-suite-fmbka.myshopify.com"
        await fire(
            f"🔥 Trending: {content.get('topic', '')[:80]}",
            content.get("telegram", content.get("tweet", ""))[:500],
            link=shop_url,
            channels=["telegram", "slack", "shopify_blog"],
        )
    except Exception as e:
        log.debug("BrutusClone blast: %s", e)


async def _quantum_improve() -> None:
    try:
        from modules.quantum_self_improver import run_improvement_cycle
        await run_improvement_cycle()
    except Exception as e:
        log.debug("Quantum self-improve: %s", e)


# ── 6. Main Cycle ─────────────────────────────────────────────────────────────

async def run_viral_cycle(max_trends: int = 3) -> dict:
    """Scheduler entry: scan trends → generate content → distribute → BrutusClone blast."""
    posted = _load_posted()
    trends = await scan_realtime_trends()

    if not trends:
        return {"ok": False, "reason": "no trends found", "distributed": 0}

    distributed = 0
    channels_total: dict[str, int] = {}

    for trend in trends[:max_trends]:
        h = _hash(trend["topic"])
        if h in posted:
            log.debug("Already posted: %s", trend["topic"][:60])
            continue

        content = await generate_omnichannel_content(trend)
        results = await distribute_everywhere(content)

        for ch, ok in results.items():
            if ok:
                channels_total[ch] = channels_total.get(ch, 0) + 1

        posted.add(h)
        distributed += 1

        # BrutusClone after each successful distribution
        if any(results.values()):
            await _brutus_blast(content)

        await asyncio.sleep(2)

    _save_posted(posted)

    cycle_n = _increment_cycle()
    # Self-improve every 10 cycles
    if cycle_n % 10 == 0:
        asyncio.create_task(_quantum_improve())

    hits = sum(channels_total.values())
    summary = (
        f"🌐 <b>Viral Distributor</b>\n"
        f"📊 {distributed} Trends verbreitet\n"
        f"📡 {hits} Channel-Posts gesamt\n"
        f"🔗 Kanäle: {', '.join(f'{k}:{v}' for k, v in channels_total.items() if v)}"
    )
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": summary, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass

    log.info("Viral cycle done: %d distributed, %d channel hits", distributed, hits)
    return {
        "ok": True,
        "distributed": distributed,
        "channels": channels_total,
        "cycle": cycle_n,
        "total_hits": hits,
    }
