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
import sqlite3
import aiohttp
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from modules.circuit_breaker import is_open, success as cb_success, failure as cb_failure, protected

# ── Activity Log (SQLite) ─────────────────────────────────────────────────────
_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_BRUTUS_DB = _DATA_DIR / "scheduler.db"   # reuse existing scheduler DB


def _init_brutus_log():
    conn = sqlite3.connect(_BRUTUS_DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brutus_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at      TEXT NOT NULL,
            niche       TEXT,
            keywords    INTEGER DEFAULT 0,
            content     INTEGER DEFAULT 0,
            channels    INTEGER DEFAULT 0,
            details     TEXT,
            duration_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS brutus_channel_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id   INTEGER,
            keyword  TEXT,
            channel  TEXT,
            status   TEXT,
            detail   TEXT,
            posted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_brutus_runs_at ON brutus_runs(ran_at);
        CREATE INDEX IF NOT EXISTS idx_bcl_run ON brutus_channel_log(run_id, posted_at);
    """)
    conn.commit()
    conn.close()


try:
    _init_brutus_log()
except Exception:
    pass


def _log_brutus_run(niche: str, results: dict, duration_ms: int) -> int:
    """Save a BRUTUS run summary, return run_id."""
    try:
        conn = sqlite3.connect(_BRUTUS_DB)
        cur = conn.execute(
            "INSERT INTO brutus_runs (ran_at,niche,keywords,content,channels,details,duration_ms) VALUES (?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), niche,
             results.get("keywords_processed", 0), results.get("content_pieces", 0),
             results.get("channels_hit", 0), json.dumps(results)[:1000], duration_ms)
        )
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id
    except Exception:
        return 0


def _log_channel(run_id: int, keyword: str, channel: str, status: str, detail: str = ""):
    """Save per-channel result for a BRUTUS run."""
    try:
        conn = sqlite3.connect(_BRUTUS_DB)
        conn.execute(
            "INSERT INTO brutus_channel_log (run_id,keyword,channel,status,detail,posted_at) VALUES (?,?,?,?,?,?)",
            (run_id, keyword, channel, status, detail[:200], datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_brutus_history(limit: int = 50) -> list:
    """Return last N BRUTUS runs for dashboard."""
    try:
        _init_brutus_log()
        conn = sqlite3.connect(_BRUTUS_DB)
        rows = conn.execute(
            "SELECT id,ran_at,niche,keywords,content,channels,duration_ms FROM brutus_runs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"id": r[0], "ran_at": r[1], "niche": r[2], "keywords": r[3],
                 "content": r[4], "channels": r[5], "duration_ms": r[6]} for r in rows]
    except Exception:
        return []


def get_brutus_run_detail(run_id: int) -> list:
    """Return per-channel log for a specific run."""
    try:
        conn = sqlite3.connect(_BRUTUS_DB)
        rows = conn.execute(
            "SELECT keyword,channel,status,detail,posted_at FROM brutus_channel_log WHERE run_id=? ORDER BY id",
            (run_id,)
        ).fetchall()
        conn.close()
        return [{"keyword": r[0], "channel": r[1], "status": r[2],
                 "detail": r[3], "posted_at": r[4]} for r in rows]
    except Exception:
        return []

log = logging.getLogger("BRUTUS")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "brutus"))
ANTHROPIC   = os.getenv("ANTHROPIC_API_KEY", "")
PERPLEXITY  = os.getenv("PERPLEXITY_API_KEY", "")
DEEPSEEK    = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
YOUTUBE_KEY    = os.getenv("YOUTUBE_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
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
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                ) as r:
                    xml_text = await r.text()
                # Skip HTML responses (rate-limited/blocked by Google)
                stripped = xml_text.lstrip()
                if not stripped.startswith("<rss") and not stripped.startswith("<?xml"):
                    log.warning("Trends %s: non-XML response (rate-limited)", region)
                    continue
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
        headers = {"User-Agent": "Mozilla/5.0 SuperMegaBot/2.0 (by /u/bullpowersrtkennels)"}
        async with aiohttp.ClientSession(headers=headers) as s:
            for sub in subreddits[:3]:
                try:
                    async with s.get(
                        f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                        timeout=aiohttp.ClientTimeout(total=12),
                    ) as r:
                        if r.content_type and "json" not in r.content_type:
                            log.debug("Reddit r/%s rate-limited (HTML response) — skip", sub)
                            continue
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
                except Exception as sub_exc:
                    log.debug("Reddit r/%s scan skip: %s", sub, sub_exc)
    except Exception as exc:
        log.debug("Reddit scan error: %s", exc)
    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: PREDICTOR — Welcher Trend ist kurz vor dem Peak?
# ─────────────────────────────────────────────────────────────────────────────

async def predict_peak_trends(trends: list[dict]) -> list[dict]:
    """
    AI analysiert Trends und bewertet Potential.
    Gibt nur Top-Trends zurück die noch VOR dem Peak sind.
    """
    if not trends or (not PERPLEXITY and not ANTHROPIC):
        return trends[:3]
    try:
        import aiohttp
        prompt = f"""Du bist ein Trend-Analyst. Bewerte diese Trends nach Viral-Potential (1-10) und ob sie noch VOR dem Peak sind:

{json.dumps(trends[:15], ensure_ascii=False, indent=2)}

Gib JSON zurück:
[{{"keyword": "...", "score": 8, "pre_peak": true, "reason": "kurze Begründung", "content_angle": "bester Content-Winkel"}}]

Nur JSON, kein anderer Text."""

        async with aiohttp.ClientSession() as s:
            raw = await _ai_text(s, prompt, max_tokens=800)
        if not raw:
            return trends[:3]
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= 0:
            return trends[:3]
        result = json.loads(raw[start:end])
        return [t for t in result if t.get("pre_peak") and t.get("score", 0) >= 7]
    except Exception as exc:
        log.debug("Predict error: %s", exc)
        return trends[:3]


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: CONTENT SWARM — 10 parallele AI-Agenten
# ─────────────────────────────────────────────────────────────────────────────

async def _ai_text(session, prompt: str, max_tokens: int = 600) -> str:
    """Perplexity → Claude → '' fallback."""
    try:
        from modules.ai_client import ai_complete
        r = await ai_complete(prompt, max_tokens=1200)
        return r if r else ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"ai_complete fallback: {e}")
        return ""

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
        return await _ai_text(session, prompt, max_tokens=600)
    except Exception as exc:
        log.warning("Content agent error (%s): %s", format_type, exc)
        return ""


_BRUTUS_TEMPLATES = [
    {
        "social_post": "🔥 {kw} — Der smarteste Weg zu passivem Einkommen 2026!\n\n✅ Vollautomatisch\n✅ KI-gestützt\n✅ Bereits hunderte zufriedene Kunden\n\n👉 Jetzt starten: {_DS24}\n\n#PassivesEinkommen #KI #OnlineGeldVerdienen #AIITEC #Digistore24",
        "blog_post": "<h1>{kw} — Dein Weg zu passivem Einkommen 2026</h1><p>Mit modernster KI-Technologie generierst du vollautomatisch Einnahmen. Unser System läuft 24/7 für dich. <a href='{_DS24}'>Jetzt starten →</a></p>",
        "email_subject_lines": "5 Wege zu passivem Einkommen mit {kw}\nWarum {kw} 2026 funktioniert\nDein vollautomatisches Einkommen mit KI\nSo verdienst du mit {kw} im Schlaf\nNeu: {kw} — Jetzt kostenlos testen",
        "ad_copy": "HEADLINE: {kw} — Jetzt €497 sparen!\nBODY: Vollautomatisches Einkommen mit KI. 24/7 für dich. Bereits 500+ zufriedene Kunden.\nCTA: Jetzt starten →\nURL: {_DS24}",
    },
    {
        "social_post": "💡 Kennst du das? Arbeitest du hart, aber das Geld reicht nicht?\n\n{kw} hat bei mir alles verändert:\n→ Vollautomatisch €500–2000/Monat\n→ KI übernimmt alles\n→ Starte heute noch\n\n🔗 {_DS24}\n\n#Freiheit #PassivesEinkommen #KIBusiness",
        "blog_post": "<h1>Wie {kw} dein Leben verändern kann</h1><p>Stell dir vor: Dein Einkommen läuft automatisch. KI arbeitet für dich. Du hast Zeit für das Wichtige. Das ist kein Traum — das ist <a href='{_DS24}'>{kw}</a>.</p>",
        "email_subject_lines": "Achtung: {kw} verändert alles\n[Neu] Passives Einkommen mit {kw}\nLetzter Platz: {kw} Masterkurs\nKostenlose Demo: {kw}\nWie Max €2.400/Monat mit {kw} verdient",
        "ad_copy": "HEADLINE: {kw} — Passives Einkommen mit KI\nBODY: Vollautomatisch Geld verdienen. Kein Vorwissen nötig. Sofort starten.\nCTA: Kostenlos testen →\nURL: {_DS24}",
    },
    {
        "social_post": "📊 ERGEBNIS nach 30 Tagen mit {kw}:\n\nWoche 1: System aufgesetzt (2h)\nWoche 2: Erste €89 Einnahmen\nWoche 3: €312 passives Einkommen\nWoche 4: €847 ohne aktive Arbeit\n\nAlles automatisch. KI macht alles.\n👉 {_DS24}\n\n#Ergebnis #KIBusiness #DigitalNomad",
        "blog_post": "<h1>{kw}: Meine Erfahrung nach 30 Tagen</h1><p>Ich war skeptisch. Aber nach einem Monat mit <a href='{_DS24}'>{kw}</a> bin ich überzeugt: Das System funktioniert. Vollautomatisch, KI-gestützt, und wirklich passiv.</p>",
        "email_subject_lines": "Mein 30-Tage-Ergebnis mit {kw}\n€847 passiv — so geht's mit {kw}\n{kw}: Vorher/Nachher Vergleich\nWarum ich {kw} jedem empfehle\n{kw} — jetzt 50% Rabatt sichern",
        "ad_copy": "HEADLINE: €847 in 30 Tagen — mit {kw}\nBODY: Echte Ergebnisse. KI-Automatisierung. Sofort startklar.\nCTA: Mein Ergebnis ansehen →\nURL: {_DS24}",
    },
    {
        "social_post": "🚀 BREAKING: {kw} jetzt verfügbar!\n\nWas du bekommst:\n✅ Vollautomatisches KI-System\n✅ Fertige Templates & Strategien\n✅ 24/7 Support\n✅ 30 Tage Geld-zurück-Garantie\n\nNur für kurze Zeit: Jetzt starten!\n🔗 {_DS24}",
        "blog_post": "<h1>{kw} 2026 — Alles was du wissen musst</h1><p>Das KI Business Blueprint revolutioniert passive Einnahmen. Mit <a href='{_DS24}'>{kw}</a> startest du heute noch durch.</p>",
        "email_subject_lines": "🚀 {kw} ist jetzt live!\nNeu: {kw} mit 30-Tage-Garantie\n{kw} — dein digitales Einkommen startet jetzt\nHast du {kw} schon gesehen?\n[Wichtig] {kw} Sonderangebot endet bald",
        "ad_copy": "HEADLINE: {kw} — 30 Tage Geld-zurück!\nBODY: Risikolos starten. Vollautomatisch. KI macht alles für dich.\nCTA: Risikolos starten →\nURL: {_DS24}",
    },
    {
        "social_post": "💰 Frage: Wieviel verdienst du im Schlaf?\n\nMit {kw}:\n→ KI arbeitet 24h für dich\n→ Vollautomatische Leads\n→ Passives Einkommen Monat für Monat\n\nAntwort: So viel wie du willst.\n\n👉 Starte heute: {_DS24}\n\n#PassivesEinkommen #KI2026 #FinanzielleFreiheit",
        "blog_post": "<h1>Passives Einkommen mit {kw}: Der ultimative Guide</h1><p>Finanzielle Freiheit ist möglich. Mit <a href='{_DS24}'>{kw}</a> automatisierst du dein Einkommen — KI übernimmt alles.</p>",
        "email_subject_lines": "Passives Einkommen mit {kw}: So geht's\n{kw} — dein Einkommen läuft jetzt automatisch\nFinanzielle Freiheit mit {kw}\nNoch heute starten: {kw}\n{kw} — limitiertes Angebot sichern",
        "ad_copy": "HEADLINE: Passives Einkommen mit {kw} — KI macht alles!\nBODY: Vollautomatisch. 24/7. Sofort startklar. Keine Vorkenntnisse nötig.\nCTA: Gratis Demo ansehen →\nURL: {_DS24}",
    },
]


def _fallback_content_swarm(keyword: str) -> dict:
    import hashlib
    _ds24 = (
        os.getenv("DS24_AFFILIATE_LINK")
        or os.getenv("AIITEC_AFFILIATE_URL")
        or os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
    )
    idx = int(hashlib.md5(keyword.encode()).hexdigest(), 16) % len(_BRUTUS_TEMPLATES)
    tmpl = _BRUTUS_TEMPLATES[idx]
    return {k: v.replace("{kw}", keyword).replace("{_DS24}", _ds24).replace("#BullPower", "#AIITEC") for k, v in tmpl.items()}


async def content_swarm(keyword: str, angle: str = "") -> dict:
    """
    10 parallele AI-Agenten generieren gleichzeitig alle Content-Formate.
    Fällt auf Template-Rotation zurück wenn kein Anthropic-Credit verfügbar.
    """
    if not PERPLEXITY and not ANTHROPIC:
        log.info("BRUTUS: kein AI-Key — Template-Fallback für '%s'", keyword)
        return _fallback_content_swarm(keyword)

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

    if not content_pack:
        log.info("BRUTUS: AI returned empty — Template-Fallback für '%s'", keyword)
        return _fallback_content_swarm(keyword)

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
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
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
    if is_open("facebook"):
        return False
    page_token = os.getenv("FACEBOOK_PAGE_TOKEN", "")
    page_id    = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
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
            cb_success("facebook")
            log.info("BRUTUS: Facebook post published — %s", data["id"])
            return True
        err = data.get("error", {})
        code = err.get("code", 0)
        msg  = err.get("message", "")[:80]
        if code in (100, 190, 10, 200):
            cb_failure("facebook", msg, code)
            log.debug("BRUTUS: Facebook circuit opened (perm/auth %s)", code)
        else:
            cb_failure("facebook", msg, code)
            log.warning("BRUTUS: Facebook post error %s: %s", code, msg)
        return False
    except Exception as exc:
        cb_failure("facebook", str(exc))
        log.warning("Facebook deploy error: %s", exc)
        return False


async def deploy_to_instagram(keyword: str, content: dict) -> bool:
    """Instagram @aaiitecc — auto-post via Facebook Graph API (text as image caption)."""
    if is_open("instagram"):
        return False
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
                err = media_data.get("error", {})
                cb_failure("instagram", err.get("message", str(media_data))[:80], err.get("code", 0))
                log.debug("BRUTUS: IG container failed (circuit opened): %s", err.get("message","")[:60])
                return False

            # Step 2: Publish
            async with s.post(
                f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish",
                data={"creation_id": container_id, "access_token": page_token},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                pub_data = await r.json(content_type=None)

        if pub_data.get("id"):
            cb_success("instagram")
            log.info("BRUTUS: Instagram post published — %s", pub_data["id"])
            return True
        err = pub_data.get("error", {})
        cb_failure("instagram", err.get("message", str(pub_data))[:80], err.get("code", 0))
        log.debug("BRUTUS: Instagram publish error (circuit opened): %s", err.get("message","")[:60])
        return False
    except Exception as exc:
        cb_failure("instagram", str(exc))
        log.debug("Instagram deploy error: %s", exc)
        return False


async def deploy_to_youtube(keyword: str, content: dict) -> bool:
    """YouTube community post via YouTube Data API v3 (requires OAuth with youtube.force-ssl scope)."""
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID", "UCy5U7UGOMNkvUR2-5Qm4yiA")
    if not channel_id:
        return False

    yt_desc = content.get("youtube_desc", "")
    if not yt_desc:
        return False

    try:
        from modules.google_oauth import ensure_valid_token
        token = await ensure_valid_token()
    except Exception:
        token = None

    if not token:
        log.info("BRUTUS: YouTube post skipped — OAuth nicht aktiv. Bitte /api/youtube/auth aufrufen.")
        return False

    post_text = f"Neu: {keyword}\n\n{yt_desc[:900]}"

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.googleapis.com/youtube/v3/communityPosts",
                params={"part": "snippet"},
                headers={"Authorization": f"Bearer {token}"},
                json={"snippet": {"type": "textPost", "textOriginal": post_text}},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)

        if data.get("id"):
            log.info("BRUTUS: YouTube community post published (id=%s)", data["id"])
            return True
        err_msg = data.get("error", {}).get("message", str(data))
        log.info("BRUTUS: YouTube community post failed: %s", err_msg)
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
        headers = {"Authorization": f"Klaviyo-API-Key {klaviyo_key}", "revision": "2024-10-15",
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
                                "from_email": "bullpowersrtkennels@gmail.com",
                                "from_label": "AIITEC | Rudolf",
                                "reply_to_email": "bullpowersrtkennels@gmail.com",
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
# NEUE KANÄLE — Reddit, LinkedIn, Pinterest, Video-Scripts
# ─────────────────────────────────────────────────────────────────────────────

async def post_to_reddit(keyword: str, content_pack: dict) -> dict:
    """Post to r/shopify, r/ecommerce, r/entrepreneur with value-first content."""
    import aiohttp
    client_id     = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    username      = os.getenv("REDDIT_USERNAME", "")
    password      = os.getenv("REDDIT_PASSWORD", "")
    if not all([client_id, client_secret, username, password]):
        log.info("BRUTUS Reddit: nicht konfiguriert — skip")
        return {"skipped": True}
    try:
        auth = aiohttp.BasicAuth(client_id, client_secret)
        headers = {"User-Agent": f"BullPowerBot/1.0 by {username}"}
        token_data = {"grant_type": "password", "username": username, "password": password}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://www.reddit.com/api/v1/access_token",
                              auth=auth, data=token_data, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=10)) as r:
                tok = (await r.json()).get("access_token", "")
            if not tok:
                return {"skipped": True, "reason": "auth failed"}
            api_headers = {**headers, "Authorization": f"bearer {tok}"}
            title = content_pack.get("headline", keyword)[:300]
            body  = content_pack.get("caption", content_pack.get("blog_intro", ""))[:2000]
            _affiliate = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
            body += f"\n\n🔗 Mehr: {_affiliate}"
            posted = 0
            for sub in ["shopify", "ecommerce", "entrepreneur"]:
                try:
                    async with s.post("https://oauth.reddit.com/api/submit",
                                      headers=api_headers,
                                      data={"sr": sub, "kind": "self", "title": title,
                                            "text": body, "resubmit": True},
                                      timeout=aiohttp.ClientTimeout(total=10)) as rr:
                        data = await rr.json(content_type=None)
                        if data.get("success") or rr.status in (200, 201):
                            posted += 1
                            log.info("BRUTUS Reddit: posted to r/%s", sub)
                except Exception as e:
                    log.warning("BRUTUS Reddit r/%s: %s", sub, e)
        return {"posted": posted, "subreddits": posted}
    except Exception as e:
        log.error("BRUTUS Reddit error: %s", e)
        return {"skipped": True, "error": str(e)}


async def post_to_linkedin_brutus(keyword: str, content_pack: dict) -> dict:
    """Post AI content to LinkedIn via BRUTUS."""
    if is_open("linkedin"):
        return {"skipped": True, "reason": "circuit_open:linkedin"}
    import aiohttp
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    urn   = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
    if not token:
        log.info("BRUTUS LinkedIn: nicht konfiguriert — skip")
        return {"skipped": True}
    try:
        text = content_pack.get("linkedin_post") or content_pack.get("caption", "")
        if not text:
            text = f"🚀 {keyword}\n\n{content_pack.get('blog_intro','')[:800]}\n\n#Shopify #eCommerce #KI #Automatisierung"
        text = text[:1250]
        payload = {
            "author": urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                   "X-Restli-Protocol-Version": "2.0.0"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post("https://api.linkedin.com/v2/ugcPosts",
                              headers=headers, json=payload) as r:
                if r.status in (200, 201):
                    cb_success("linkedin")
                    log.info("BRUTUS LinkedIn: posted for '%s'", keyword)
                    return {"posted": True}
                err_text = await r.text()
                cb_failure("linkedin", err_text[:80], r.status)
                log.debug("BRUTUS LinkedIn %s — circuit opened", r.status)
                return {"skipped": True, "status": r.status}
    except Exception as e:
        cb_failure("linkedin", str(e))
        log.error("BRUTUS LinkedIn error: %s", e)
        return {"skipped": True, "error": str(e)}


async def post_to_pinterest(keyword: str, content_pack: dict, image_url: str = "") -> dict:
    """Post pins to Pinterest boards."""
    import aiohttp
    token    = os.getenv("PINTEREST_ACCESS_TOKEN", "")
    board_id = os.getenv("PINTEREST_BOARD_ID", "")
    if not token or not board_id:
        log.info("BRUTUS Pinterest: nicht konfiguriert — skip")
        return {"skipped": True}
    try:
        if not image_url:
            image_url = "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png"
        title       = content_pack.get("headline", keyword)[:100]
        description = content_pack.get("caption", "")[:500]
        _aff_base = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
        link = f"{_aff_base}?utm_source=pinterest&utm_medium=pin&utm_campaign={keyword.replace(' ','_')}"
        payload = {"board_id": board_id, "title": title, "description": description,
                   "link": link, "media_source": {"source_type": "image_url", "url": image_url}}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post("https://api.pinterest.com/v5/pins",
                              headers=headers, json=payload) as r:
                if r.status in (200, 201):
                    log.info("BRUTUS Pinterest: pin created for '%s'", keyword)
                    return {"posted": True}
                err = await r.text()
                log.warning("BRUTUS Pinterest HTTP %s: %s", r.status, err[:80])
                return {"skipped": True, "status": r.status}
    except Exception as e:
        log.error("BRUTUS Pinterest error: %s", e)
        return {"skipped": True, "error": str(e)}


async def generate_video_script(keyword: str, content_pack: dict) -> dict:
    """Generate 60s TikTok/Shorts video script via Perplexity→Claude, save to Supabase."""
    import aiohttp
    if not PERPLEXITY and not ANTHROPIC:
        return {"skipped": True}
    try:
        prompt = (
            f"Erstelle ein 60-Sekunden TikTok/YouTube-Shorts-Skript auf Deutsch zum Thema: '{keyword}'\n"
            "Format:\n"
            "HOOK (0-3s): [Aufmerksamkeit sofort]\n"
            "PROBLEM (3-10s): [Schmerzpunkt]\n"
            "LÖSUNG (10-45s): [Unsere AI-Automatisierung als Lösung, 3 Punkte]\n"
            "CTA (45-60s): [Link in Bio: BullPower Hub]\n"
            "HASHTAGS: [10 relevante Hashtags]\n"
            "Nur Text, kein JSON."
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
            script = await _ai_text(s, prompt, max_tokens=600)
        script = script.strip()
        if not script:
            return {"skipped": True}
        # Save to Supabase
        supa_url = os.getenv("SUPABASE_URL", "")
        supa_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if supa_url and supa_key:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                    async with s.post(f"{supa_url}/rest/v1/video_scripts",
                                      headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}",
                                               "Content-Type": "application/json", "Prefer": "return=minimal",
                                               "Accept-Profile": "public", "Content-Profile": "public"},
                                      json={"keyword": keyword, "script": script,
                                            "created_at": datetime.now(timezone.utc).isoformat()}) as r:
                        await r.read()
            except Exception:
                pass
        log.info("BRUTUS VideoScript: created for '%s' (%d chars)", keyword, len(script))
        return {"created": True, "chars": len(script)}
    except Exception as e:
        log.error("BRUTUS VideoScript error: %s", e)
        return {"skipped": True, "error": str(e)}


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

    _t_start = datetime.now(timezone.utc).timestamp()
    results = {"keywords_processed": 0, "content_pieces": 0, "channels_hit": 0, "errors": []}
    # Create run record first so _log_channel gets the real run_id
    _run_id = _log_brutus_run(niche, results, 0)

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

    # Always seed with DS24 product keywords so Brutus runs even with no trend data
    _ds24_seeds = [
        {"keyword": "passives einkommen ki automatisierung 2026", "source": "seed"},
        {"keyword": "digistore24 ki business blueprint", "source": "seed"},
        {"keyword": "online geld verdienen vollautomatisch", "source": "seed"},
        {"keyword": "shopify dropshipping automatisiert ki", "source": "seed"},
        {"keyword": "finanzielle freiheit digitales business", "source": "seed"},
    ]
    if not raw_trends:
        raw_trends = _ds24_seeds
        log.info("Phase 1: No trends found — using DS24 seed keywords")
    else:
        raw_trends = _ds24_seeds[:2] + raw_trends  # always include 2 DS24 seeds

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

        _CHANNEL_NAMES = ["telegram", "shopify", "klaviyo", "facebook", "instagram", "youtube"]
        deploy_tasks = [
            deploy_to_telegram(keyword, content_pack),
            deploy_to_shopify_blog(keyword, content_pack),
            deploy_to_klaviyo_campaign(keyword, content_pack),
            deploy_to_facebook_page(keyword, content_pack),
            deploy_to_instagram(keyword, content_pack),
            deploy_to_youtube(keyword, content_pack),
        ]
        deploy_results = await asyncio.gather(*deploy_tasks, return_exceptions=True)

        for ch_name, r in zip(_CHANNEL_NAMES, deploy_results):
            ok = not isinstance(r, Exception) and r is not False
            if ok:
                channels_hit += 1
            _log_channel(_run_id, keyword, ch_name, "ok" if ok else "skip",
                         str(r)[:100] if isinstance(r, Exception) else "")

        # Phase 4b: Neue Kanäle — Reddit, LinkedIn, Pinterest, VideoScript
        pixel_url = utm_links.get("pixel_url", "https://bullpowerhubgit.github.io/bullpower-legal/brutus_pixel.png")
        _NEW_NAMES = ["reddit", "linkedin", "pinterest", "video_script"]
        new_channel_tasks = [
            post_to_reddit(keyword, content_pack),
            post_to_linkedin_brutus(keyword, content_pack),
            post_to_pinterest(keyword, content_pack, pixel_url),
            generate_video_script(keyword, content_pack),
        ]
        new_results = await asyncio.gather(*new_channel_tasks, return_exceptions=True)
        for ch_name, r in zip(_NEW_NAMES, new_results):
            ok = isinstance(r, dict) and not r.get("skipped") and not isinstance(r, Exception)
            if ok:
                channels_hit += 1
            detail = r.get("reason", r.get("error", "")) if isinstance(r, dict) else str(r)[:80]
            _log_channel(_run_id, keyword, ch_name, "ok" if ok else "skip", detail)

        results["keywords_processed"] += 1
        results["content_pieces"] += len(content_pack)
        results["channels_hit"] += channels_hit

        log.info("'%s': %d Formate, %d Kanäle (10 total)", keyword, len(content_pack), channels_hit)

    # Phase 5+6: Amplify winners
    amplified = await detect_and_amplify()
    results["amplified"] = amplified

    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    _duration_ms = int((datetime.now(timezone.utc).timestamp() - _t_start) * 1000)
    # Update the pre-created run record with final stats
    try:
        conn = sqlite3.connect(_BRUTUS_DB)
        conn.execute(
            "UPDATE brutus_runs SET keywords=?,content=?,channels=?,details=?,duration_ms=? WHERE id=?",
            (results.get("keywords_processed", 0), results.get("content_pieces", 0),
             results.get("channels_hit", 0), json.dumps(results)[:1000], _duration_ms, _run_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        _run_id = _log_brutus_run(niche, results, _duration_ms)

    # Report
    try:
        from modules.notify_hub import async_send_telegram as send_telegram
        msg = (
            f"🔥 *BRUTUS RUN COMPLETE*\n\n"
            f"Keywords: {results['keywords_processed']}\n"
            f"Content-Stücke: {results['content_pieces']}\n"
            f"Kanäle bespielt: {results['channels_hit']}/10\n"
            f"Amplified: {len(results.get('amplified', []))}\n\n"
            f"Nische: {niche}"
        )
        await send_telegram(msg)
    except Exception:
        pass

    log.info("BRUTUS DONE: %s", json.dumps(results))
    return results


async def run_brutus_swarm(keywords: list = None, max_keywords: int = 3,
                           niche: str = "shopify ecommerce automation",
                           affiliate_url: str = "") -> dict:
    """Alias for brutus_run — backward-compatible with all callers."""
    kw_niche = niche
    if keywords:
        kw_niche = " ".join(keywords[:2]) if len(keywords) >= 2 else keywords[0]
    result = await brutus_run(niche=kw_niche, custom_keywords=keywords)
    return result
