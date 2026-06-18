#!/usr/bin/env python3
"""
BRUTUS — Brutal Revenue & Traffic Unified System
================================================
Das brutalste Traffic-Tool das je gebaut wurde.

Andere Tools: reaktiv, manuell, ein Kanal.
BRUTUS: prädiktiv, vollautomatisch, alle Kanäle gleichzeitig.

Ablauf:
  1. SCAN    — Trends in Echtzeit erkennen (5-Min-Intervall)
  2. PREDICT — Welche Trends kurz vor Peak sind
  3. SWARM   — 10 parallele AI-Agenten generieren Content
  4. DEPLOY  — Alle Kanäle gleichzeitig bespielen
  5. DETECT  — Was geht viral? Was konvertiert?
  6. AMPLIFY — Winner skalieren, Loser killen
  7. PROFIT  — Revenue direkt zu Traffic-Quelle zurückverfolgen
"""
import asyncio
import json
import logging
import os
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("BRUTUS")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "brutus"))
ANTHROPIC  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI     = os.getenv("OPENAI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
YOUTUBE_KEY    = os.getenv("YOUTUBE_API_KEY", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: TREND SCANNER — Echtzeit Trend-Erkennung
# ─────────────────────────────────────────────────────────────────────────────

async def scan_youtube_trends(niche: str = "shopify automation") -> list[dict]:
    """YouTube trending Videos in Nische — extrahiere Winning-Keywords."""
    if not YOUTUBE_KEY:
        return []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet", "q": niche, "type": "video",
                    "order": "viewCount", "maxResults": 10,
                    "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
                    "key": YOUTUBE_KEY,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        results = []
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            results.append({
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "published": sn.get("publishedAt", "")[:10],
                "video_id": item.get("id", {}).get("videoId", ""),
            })
        return results
    except Exception as exc:
        log.warning("YouTube scan error: %s", exc)
        return []


async def scan_google_trends_rss(keywords: list[str]) -> list[dict]:
    """Google Trends RSS — Daily Trending Topics."""
    try:
        import aiohttp
        import xml.etree.ElementTree as ET
        trends = []
        async with aiohttp.ClientSession() as s:
            for region in ["DE", "AT", "CH"]:
                async with s.get(
                    f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={region}",
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as r:
                    xml_text = await r.text()
                root = ET.fromstring(xml_text)
                for item in root.findall(".//item")[:10]:
                    title = item.findtext("title", "")
                    traffic = item.findtext("{https://trends.google.com/trends/trendingsearches/daily}approx_traffic", "0")
                    trends.append({"keyword": title, "traffic": traffic, "region": region})
        return trends
    except Exception as exc:
        log.warning("Google Trends scan error: %s", exc)
        return []


async def scan_reddit_hot(subreddits: list[str] = None) -> list[dict]:
    """Reddit Hot Posts — viral Content frühzeitig erkennen."""
    if subreddits is None:
        subreddits = ["shopify", "ecommerce", "entrepreneur", "dropshipping", "passive_income"]
    results = []
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            for sub in subreddits[:3]:
                async with s.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                    headers={"User-Agent": "BRUTUS/1.0"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    data = await r.json(content_type=None)
                for post in data.get("data", {}).get("children", []):
                    p = post.get("data", {})
                    if p.get("score", 0) > 100:
                        results.append({
                            "title": p.get("title", ""),
                            "score": p.get("score", 0),
                            "comments": p.get("num_comments", 0),
                            "url": p.get("url", ""),
                            "subreddit": sub,
                        })
    except Exception as exc:
        log.warning("Reddit scan error: %s", exc)
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: PREDICTOR — Welcher Trend ist kurz vor dem Peak?
# ─────────────────────────────────────────────────────────────────────────────

async def predict_peak_trends(trends: list[dict]) -> list[dict]:
    """
    AI analysiert Trends und bewertet Potential.
    Gibt nur Top-Trends zurück die noch VOR dem Peak sind.
    """
    if not trends or not ANTHROPIC:
        return trends[:3]
    try:
        import aiohttp
        prompt = f"""Du bist ein Trend-Analyst. Bewerte diese Trends nach Viral-Potential (1-10) und ob sie noch VOR dem Peak sind:

{json.dumps(trends[:15], ensure_ascii=False, indent=2)}

Gib JSON zurück:
[{{"keyword": "...", "score": 8, "pre_peak": true, "reason": "kurze Begründung", "content_angle": "bester Content-Winkel"}}]

Nur JSON, kein anderer Text."""

        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 800,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        raw = data["content"][0]["text"]
        start = raw.find("[")
        end = raw.rfind("]") + 1
        result = json.loads(raw[start:end])
        return [t for t in result if t.get("pre_peak") and t.get("score", 0) >= 7]
    except Exception as exc:
        log.warning("Predict error: %s", exc)
        return trends[:3]


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: CONTENT SWARM — 10 parallele AI-Agenten
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_single(session, keyword: str, format_type: str, angle: str = "") -> str:
    """Ein einzelner Content-Agent."""
    prompts = {
        "blog_post": f"Schreibe einen SEO-optimierten Blog-Post (400 Wörter, Deutsch) über: '{keyword}'. Angle: {angle}. Mit H1, H2, starker CTA am Ende. Fokus auf Mehrwert und Long-Tail Keywords.",
        "youtube_desc": f"Schreibe eine YouTube Video-Beschreibung (200 Wörter) für: '{keyword}'. Mit Keywords, Timestamps-Vorschlägen, CTA und Tags-Liste.",
        "email_subject_lines": f"Generiere 5 Email-Betreffzeilen für das Thema '{keyword}'. Je 1x Neugier, Dringlichkeit, Nutzen, Frage, Zahl. Auf Deutsch.",
        "social_post": f"Schreibe 3 Social Media Posts (Deutsch) über '{keyword}': 1x kurz (Twitter-Style), 1x mittel (LinkedIn), 1x mit Hashtags (Instagram). Mit starken Hooks.",
        "product_seo": f"Schreibe SEO-optimierten Produkttext (150 Wörter) für ein Produkt zum Thema '{keyword}'. Mit Meta-Title (60 Zeichen), Meta-Description (155 Zeichen), 5 Keywords.",
        "ad_copy": f"Schreibe 3 Facebook/Instagram Ad-Texte für '{keyword}': 1x Problem-Lösung, 1x Social Proof, 1x Dringlichkeit. Je Headline + Body + CTA.",
        "pinterest_pins": f"Erstelle 5 Pinterest Pin-Beschreibungen für '{keyword}'. Keyword-reich, mit Call-to-Action, 150-300 Zeichen je Pin.",
        "faq_seo": f"Erstelle 8 FAQ-Fragen und Antworten (SEO-optimiert, Deutsch) zum Thema '{keyword}'. Format: Frage + 2-Satz-Antwort. Gut für Featured Snippets.",
        "reddit_post": f"Schreibe einen authentischen Reddit-Post (nicht werblich, hilfreich) über '{keyword}'. Conversational, mit echter Erfahrung, subtil auf Lösung hinweisend.",
        "press_release": f"Schreibe eine kurze Pressemitteilung (200 Wörter, Deutsch) über eine Innovation im Bereich '{keyword}'. Professioneller Stil, newsworthy angle.",
    }

    prompt = prompts.get(format_type, prompts["blog_post"])
    try:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 600,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=aiohttp.ClientTimeout(total=25),
        ) as r:
            data = await r.json(content_type=None)
        return data["content"][0]["text"]
    except Exception as exc:
        log.warning("Content agent error (%s): %s", format_type, exc)
        return ""


async def content_swarm(keyword: str, angle: str = "") -> dict:
    """
    10 parallele AI-Agenten generieren gleichzeitig alle Content-Formate.
    Das ist der Kern von BRUTUS — was kein anderes Tool macht.
    """
    formats = [
        "blog_post", "youtube_desc", "email_subject_lines",
        "social_post", "product_seo", "ad_copy",
        "pinterest_pins", "faq_seo", "reddit_post", "press_release"
    ]

    log.info("BRUTUS Content Swarm: 10 Agenten für '%s'", keyword)

    import aiohttp
    async with aiohttp.ClientSession() as session:
        tasks = [_generate_single(session, keyword, fmt, angle) for fmt in formats]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    content_pack = {}
    for fmt, result in zip(formats, results):
        if isinstance(result, str) and result:
            content_pack[fmt] = result

    log.info("BRUTUS Swarm fertig: %d/%d Formate generiert", len(content_pack), len(formats))
    return content_pack


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: DEPLOY — Alle Kanäle gleichzeitig bespielen
# ─────────────────────────────────────────────────────────────────────────────

async def deploy_to_telegram(keyword: str, content: dict):
    """Telegram Channel — sofortige Reichweite."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        social = content.get("social_post", "")[:800]
        msg = f"🚀 *BRUTUS Auto-Post*\n\nThema: {keyword}\n\n{social}"
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        log.info("BRUTUS: Deployed to Telegram")
    except Exception as exc:
        log.warning("Telegram deploy error: %s", exc)


async def deploy_to_shopify_blog(keyword: str, content: dict) -> bool:
    """Shopify Blog — SEO-Artikel direkt publizieren."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return False
    blog_content = content.get("blog_post", "")
    if not blog_content:
        return False
    try:
        import aiohttp
        # Get or create blog
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/blogs.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                blogs_data = await r.json(content_type=None)
            blogs = blogs_data.get("blogs", [])
            blog_id = blogs[0]["id"] if blogs else None

            if not blog_id:
                async with s.post(
                    f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/blogs.json",
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                    json={"blog": {"title": "BRUTUS SEO Blog"}},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    blog_data = await r.json(content_type=None)
                blog_id = blog_data.get("blog", {}).get("id")

            if not blog_id:
                return False

            # Create article
            async with s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/blogs/{blog_id}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"},
                json={"article": {
                    "title": keyword,
                    "body_html": blog_content.replace("\n", "<br>"),
                    "tags": keyword,
                    "published": True,
                }},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                result = await r.json(content_type=None)

        if result.get("article", {}).get("id"):
            log.info("BRUTUS: Shopify Blog Artikel published: %s", keyword)
            return True
    except Exception as exc:
        log.warning("Shopify blog deploy error: %s", exc)
    return False


async def deploy_to_facebook_page(keyword: str, content: dict) -> bool:
    """Facebook Page IWIN — automatisch posten."""
    page_token = os.getenv("FACEBOOK_PAGE_TOKEN", "")
    page_id    = os.getenv("FACEBOOK_PAGE_ID", "1135864516276500")
    if not page_token:
        return False
    social = content.get("social_post", "")
    if not social:
        return False
    # Take the LinkedIn-style part (medium length)
    lines = [l.strip() for l in social.split("\n") if l.strip()]
    post_text = "\n".join(lines[:8])[:900]
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                data={"message": post_text, "access_token": page_token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        if data.get("id"):
            log.info("BRUTUS: Facebook post published — %s", data["id"])
            return True
        log.warning("BRUTUS: Facebook post error: %s", data)
        return False
    except Exception as exc:
        log.warning("Facebook deploy error: %s", exc)
        return False


async def deploy_to_instagram(keyword: str, content: dict) -> bool:
    """Instagram @aaiitecc — auto-post via Facebook Graph API (text as image caption)."""
    ig_user_id = os.getenv("INSTAGRAM_ID_AIITEC", "17841478315197796")
    page_token  = os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC", "")
    if not page_token or not ig_user_id:
        return False

    social = content.get("social_post", "")
    if not social:
        return False

    # Pick the Instagram-style section with hashtags
    lines = [l.strip() for l in social.split("\n") if l.strip()]
    post_text = "\n".join(lines[:12])[:2200]

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            # Step 1: Create media container (image_url required for IG — use a hosted pixel)
            async with s.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media",
                data={
                    "image_url": "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png",
                    "caption": post_text,
                    "access_token": page_token,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                media_data = await r.json(content_type=None)

            container_id = media_data.get("id", "")
            if not container_id:
                # Fallback: try text-only reel description (not standard but some accounts allow)
                log.warning("BRUTUS: IG container creation failed: %s", media_data)
                return False

            # Step 2: Publish
            async with s.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
                data={"creation_id": container_id, "access_token": page_token},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                pub_data = await r.json(content_type=None)

        if pub_data.get("id"):
            log.info("BRUTUS: Instagram post published — %s", pub_data["id"])
            return True
        log.warning("BRUTUS: Instagram publish error: %s", pub_data)
        return False
    except Exception as exc:
        log.warning("Instagram deploy error: %s", exc)
        return False


async def deploy_to_youtube(keyword: str, content: dict) -> bool:
    """YouTube community post via YouTube Data API v3."""
    youtube_key = os.getenv("YOUTUBE_API_KEY", "")
    channel_id  = os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")
    if not youtube_key or not channel_id:
        return False

    yt_desc = content.get("youtube_desc", "")
    if not yt_desc:
        return False

    post_text = f"Neu: {keyword}\n\n{yt_desc[:900]}"

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.googleapis.com/youtube/v3/activities",
                params={"part": "snippet", "key": youtube_key},
                json={
                    "snippet": {
                        "type": "bulletin",
                        "bulletin": {"resourceId": {"kind": "youtube#channel", "channelId": channel_id}},
                        "description": post_text,
                    }
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)

        if data.get("id"):
            log.info("BRUTUS: YouTube community post published")
            return True
        # YouTube community posts require OAuth, not just API key — log gracefully
        log.info("BRUTUS: YouTube post needs OAuth (API key insufficient): %s", data.get("error", {}).get("message", ""))
        return False
    except Exception as exc:
        log.warning("YouTube deploy error: %s", exc)
        return False


async def deploy_to_klaviyo_campaign(keyword: str, content: dict):
    """Klaviyo — Email-Kampagne für viralen Trend."""
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    list_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
    if not klaviyo_key:
        return

    subjects = content.get("email_subject_lines", "")
    if not subjects:
        return

    first_subject = subjects.split("\n")[0].strip().lstrip("1234567890.- ")[:100]
    if not first_subject:
        return

    try:
        import aiohttp
        headers = {"Authorization": f"Klaviyo-API-Key {klaviyo_key}", "revision": "2024-06-15",
                   "Content-Type": "application/json"}
        campaign_payload = {
            "data": {
                "type": "campaign",
                "attributes": {
                    "name": f"BRUTUS — {keyword[:50]} — {datetime.now().strftime('%d.%m')}",
                    "audiences": {"included": [list_id]},
                    "send_strategy": {"method": "immediate"},
                    "campaign-messages": {"data": [{
                        "type": "campaign-message",
                        "attributes": {
                            "definition": {
                                "type": "email",
                                "subject": first_subject,
                                "preview_text": f"Hot Trend: {keyword[:80]}",
                                "from_email": "hello@bullpowerhub.com",
                                "from_label": "BullPower Hub",
                                "reply_to_email": "hello@bullpowerhub.com",
                            }
                        }
                    }]}
                }
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://a.klaviyo.com/api/campaigns/", headers=headers,
                              json=campaign_payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status in (200, 201):
                    log.info("BRUTUS: Klaviyo campaign created for '%s'", keyword)
    except Exception as exc:
        log.warning("Klaviyo deploy error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5+6: VIRAL DETECTOR + AMPLIFIER
# ─────────────────────────────────────────────────────────────────────────────

async def detect_and_amplify():
    """
    Prüft welche BRUTUS-Contents performen.
    Amplifiziert Winners automatisch — mehr Posts, mehr Kanäle.
    """
    state_file = DATA_DIR / "performance_state.json"
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        state = {}

    amplified = []
    for keyword, data in state.items():
        deploys = data.get("deploys", 0)
        engagement = data.get("engagement_score", 0)
        # Simple rule: wenn 2+ Deploys und Engagement > 0 → amplifizieren
        if deploys >= 2 and engagement > 5:
            log.info("BRUTUS AMPLIFY: '%s' (score=%d) → extra push", keyword, engagement)
            amplified.append(keyword)

    return amplified


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7: REVENUE TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def generate_utm_links(keyword: str, base_url: str = None) -> dict:
    """
    UTM-Links für Revenue-Attribution.
    Jeder BRUTUS-Content bekommt eigene UTM-Parameter.
    """
    if not base_url:
        base_url = f"https://{SHOPIFY_DOMAIN}"

    keyword_slug = keyword.lower().replace(" ", "-")[:30]
    timestamp = datetime.now().strftime("%Y%m%d")

    return {
        "blog": f"{base_url}?utm_source=brutus&utm_medium=blog&utm_campaign={keyword_slug}&utm_content={timestamp}",
        "email": f"{base_url}?utm_source=brutus&utm_medium=email&utm_campaign={keyword_slug}&utm_content={timestamp}",
        "social": f"{base_url}?utm_source=brutus&utm_medium=social&utm_campaign={keyword_slug}&utm_content={timestamp}",
        "youtube": f"{base_url}?utm_source=brutus&utm_medium=youtube&utm_campaign={keyword_slug}&utm_content={timestamp}",
    }


def _save_state(keyword: str, content_pack: dict, utm_links: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state_file = DATA_DIR / "performance_state.json"
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        state = {}

    content_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
    state[keyword] = {
        "hash": content_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formats": list(content_pack.keys()),
        "utm_links": utm_links,
        "deploys": state.get(keyword, {}).get("deploys", 0) + 1,
        "engagement_score": 0,
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    # Save full content pack
    content_file = DATA_DIR / f"content_{content_hash}.json"
    content_file.write_text(json.dumps({
        "keyword": keyword, "utm_links": utm_links, "content": content_pack,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# BRUTUS MAIN RUN — Alles in einem Durchlauf
# ─────────────────────────────────────────────────────────────────────────────

async def brutus_run(niche: str = "shopify ecommerce automation", custom_keywords: list = None) -> dict:
    """
    BRUTUS Hauptlauf:
    Scan → Predict → Swarm → Deploy → Track
    Ein Durchlauf = hunderte Content-Stücke auf allen Kanälen.
    """
    log.info("=" * 60)
    log.info("BRUTUS START — Nische: %s", niche)
    log.info("=" * 60)

    results = {"keywords_processed": 0, "content_pieces": 0, "channels_hit": 0, "errors": []}

    # Phase 1: Scan
    log.info("Phase 1: Scanning trends...")
    yt_trends, reddit_trends, google_trends = await asyncio.gather(
        scan_youtube_trends(niche),
        scan_reddit_hot(),
        scan_google_trends_rss([niche]),
        return_exceptions=True,
    )

    raw_trends = []
    if isinstance(yt_trends, list):
        raw_trends += [{"keyword": t["title"], "source": "youtube"} for t in yt_trends]
    if isinstance(reddit_trends, list):
        raw_trends += [{"keyword": t["title"], "source": "reddit", "score": t.get("score", 0)} for t in reddit_trends]
    if isinstance(google_trends, list):
        raw_trends += [{"keyword": t["keyword"], "source": "google_trends"} for t in google_trends]

    if custom_keywords:
        raw_trends = [{"keyword": k, "source": "custom"} for k in custom_keywords] + raw_trends

    log.info("Phase 1 done: %d raw trends found", len(raw_trends))

    # Phase 2: Predict
    log.info("Phase 2: Predicting peak trends...")
    top_trends = await predict_peak_trends(raw_trends)
    if not top_trends:
        top_trends = raw_trends[:3]

    log.info("Phase 2 done: %d pre-peak trends selected", len(top_trends))

    # Phase 3+4+7: Swarm + Deploy + Track (parallel per keyword)
    for trend in top_trends[:5]:
        keyword = trend.get("keyword", "")
        angle = trend.get("content_angle", "")
        if not keyword:
            continue

        log.info("Phase 3: Content Swarm für '%s'...", keyword)
        content_pack = await content_swarm(keyword, angle)

        if not content_pack:
            continue

        utm_links = generate_utm_links(keyword)
        _save_state(keyword, content_pack, utm_links)

        log.info("Phase 4: Deploying '%s' to all channels...", keyword)
        channels_hit = 0

        deploy_tasks = [
            deploy_to_telegram(keyword, content_pack),
            deploy_to_shopify_blog(keyword, content_pack),
            deploy_to_klaviyo_campaign(keyword, content_pack),
            deploy_to_facebook_page(keyword, content_pack),
            deploy_to_instagram(keyword, content_pack),
            deploy_to_youtube(keyword, content_pack),
        ]
        deploy_results = await asyncio.gather(*deploy_tasks, return_exceptions=True)

        for r in deploy_results:
            if not isinstance(r, Exception) and r is not False:
                channels_hit += 1

        results["keywords_processed"] += 1
        results["content_pieces"] += len(content_pack)
        results["channels_hit"] += channels_hit

        log.info("'%s': %d Formate, %d Kanäle", keyword, len(content_pack), channels_hit)

    # Phase 5+6: Amplify winners
    amplified = await detect_and_amplify()
    results["amplified"] = amplified

    results["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Report
    try:
        from modules.notify_hub import send_telegram
        msg = (
            f"🔥 *BRUTUS RUN COMPLETE*\n\n"
            f"Keywords: {results['keywords_processed']}\n"
            f"Content-Stücke: {results['content_pieces']}\n"
            f"Kanäle bespielt: {results['channels_hit']}/6\n"
            f"Amplified: {len(results.get('amplified', []))}\n\n"
            f"Nische: {niche}"
        )
        await send_telegram(msg)
    except Exception:
        pass

    log.info("BRUTUS DONE: %s", json.dumps(results))
    return results
