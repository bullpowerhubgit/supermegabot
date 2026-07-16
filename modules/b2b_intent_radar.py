#!/usr/bin/env python3
"""
B2B Intent Radar — Welteinzigartige Kauf-Absichts-Maschine aus öffentlichen Signalen.

Problem: Bombora, 6sense, ZoomInfo verkaufen B2B-Intent-Daten für $12k-100k/Jahr.
Alle basieren auf Cookie-Tracking, das gerade stirbt (DSGVO, iOS, Chrome).
Der Nachfolger existiert nicht.

Lösung: Wenn eine Firma kurz vor einem Kauf steht, hinterlässt sie 15-20 öffentliche Signale:
  - "Wir suchen einen Shopify-Spezialisten" → investiert in Shopify
  - Startup bekommt €2M Seed → hat Budget für Tools
  - CEO verbindet sich mit 3 E-Commerce-Experten → plant Pivot
  - GitHub: Org beginnt Shopify-App-Verzeichnis → braucht Integration
  - Reddit: "Wie automatisiert ihr eure Bestellungen?" → sucht Lösung

Diese Signale sind öffentlich, GDPR-safe, kostenlos — und präziser als Cookies.

Monetarisierung:
  A) Direkter Outreach → SuperMegaBot SaaS verkaufen (€49-€299/Monat)
  B) Lead-Pakete verkaufen → andere Vendors zahlen €50-500/Lead

Datenquellen (alle kostenlos, keine API-Schlüssel außer GitHub):
  1. HackerNews "Who's Hiring" → Tech-Startups mit Budget
  2. Reddit (r/shopify, r/ecommerce, r/entrepreneur) → direkte Kaufabsicht
  3. GitHub → neue Orgs + Shopify-relevante Repos
  4. RSS-Feeds (TechCrunch, EU-Startups) → Funding-Runden
  5. Google News RSS → kein API-Key nötig, öffentliche XML-Feeds
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

log = logging.getLogger("B2BIntentRadar")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "b2b_intent_radar.db"

# ── Credentials ───────────────────────────────────────────────────────────────
GITHUB_TOKEN    = lambda: os.getenv("GITHUB_TOKEN", "")
REDDIT_CID      = lambda: os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_SECRET   = lambda: os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_UA       = "B2BIntentRadar/1.0 by SuperMegaBot"
TELEGRAM_TOKEN  = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = lambda: os.getenv("TELEGRAM_CHAT_ID", "")

# ── Target profile: what signals indicate a fit for SuperMegaBot SaaS ─────────
# Companies that match this profile are HIGH-VALUE leads
TARGET_KEYWORDS = [
    "shopify", "e-commerce", "ecommerce", "online shop", "onlineshop",
    "dropshipping", "fulfillment", "bestellungen automatisieren",
    "product import", "woocommerce", "amazon seller", "ebay seller",
    "digistore", "affiliate marketing", "saas", "automation",
    "telegram bot", "chatbot", "ai tools", "stripe integration",
]

# Reddit subs with high B2B purchase intent
TARGET_SUBS = [
    "shopify", "ecommerce", "entrepreneur", "startups", "smallbusiness",
    "dropship", "Unternehmertum", "de", "germany",
]

# HackerNews: month IDs for "Ask HN: Who is hiring?" (fetched dynamically)
HN_WHO_IS_HIRING = "Ask HN: Who is hiring?"

# RSS feeds for funding news (no API key needed) — nur noch URLs die 200 liefern
FUNDING_RSS_FEEDS = [
    # Google News RSS: zuverlässig, kein Key, GDPR-safe public
    "https://news.google.com/rss/search?q=Shopify+funding+OR+ecommerce+startup&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Shopify+OR+E-Commerce+Startup+Finanzierung&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=SaaS+automation+funding+OR+ecommerce+AI&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Digistore24+OR+dropshipping+tool+OR+shopify+app&hl=de&gl=DE&ceid=DE:de",
    "https://www.gruenderszene.de/feed",
    "https://feeds.feedburner.com/TechCrunch/",
]

# Signal strength thresholds
MIN_CONFIDENCE     = 0.55   # war 0.65 — zu streng bei Keyword-Klassifikation
HIGH_CONF_ALERT    = 0.80
MAX_LEADS_PER_RUN  = 40
MAX_SIGNALS_PER_RUN = 150


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(_DB).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS b2b_signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER,
                source      TEXT,
                company     TEXT,
                signal_type TEXT,
                signal_text TEXT,
                url         TEXT UNIQUE,
                industry    TEXT,
                size_est    TEXT,
                buy_category TEXT,
                confidence  REAL,
                processed   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS b2b_leads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER,
                company     TEXT UNIQUE,
                industry    TEXT,
                size_est    TEXT,
                signal_count INTEGER,
                best_conf    REAL,
                buy_categories TEXT,
                contact_hint TEXT,
                outreach_sent INTEGER DEFAULT 0,
                sold        INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS b2b_scans (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       INTEGER,
                signals  INTEGER,
                leads    INTEGER,
                alerts   INTEGER
            );
            CREATE INDEX IF NOT EXISTS b2b_signals_ts ON b2b_signals(ts);
            CREATE INDEX IF NOT EXISTS b2b_leads_conf ON b2b_leads(best_conf DESC);
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Source 1: HackerNews "Who's Hiring"
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_hn_signals() -> list[dict]:
    """HN via Algolia (zuverlässig) + optional Who's Hiring Comments."""
    import aiohttp

    signals: list[dict] = []
    queries = [
        "shopify automation OR shopify app",
        "ecommerce automation OR ecommerce bot",
        "looking for shopify developer",
        "who is hiring shopify",
        "saas e-commerce",
    ]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
            for q in queries:
                try:
                    async with s.get(
                        "https://hn.algolia.com/api/v1/search_by_date",
                        params={"query": q, "tags": "story", "hitsPerPage": 15},
                        headers={"User-Agent": "B2BIntentRadar/2.0"},
                    ) as r:
                        if r.status != 200:
                            continue
                        data = await r.json(content_type=None)
                    for hit in data.get("hits") or []:
                        title = hit.get("title") or ""
                        text = hit.get("story_text") or hit.get("comment_text") or ""
                        full = f"{title} {_strip_html(text)}"[:500]
                        if len(full) < 20:
                            continue
                        oid = hit.get("objectID") or hit.get("story_id") or ""
                        signals.append({
                            "source": "hackernews",
                            "signal_type": "hn_story",
                            "signal_text": full,
                            "url": f"https://news.ycombinator.com/item?id={oid}" if oid else hit.get("url") or "",
                            "company": _guess_company(full, hit.get("author") or ""),
                        })
                except Exception as e:
                    log.debug("HN Algolia q=%s: %s", q, e)
                await asyncio.sleep(0.3)

            # Who's Hiring — nur erste 10 Ask-Stories, dann max 30 Kids
            try:
                async with s.get("https://hacker-news.firebaseio.com/v0/askstories.json") as r:
                    story_ids = await r.json(content_type=None) or []
                for sid in story_ids[:12]:
                    async with s.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json") as r:
                        item = await r.json(content_type=None)
                    if not item:
                        continue
                    title = (item.get("title") or "").lower()
                    if "who is hiring" not in title and "who's hiring" not in title:
                        continue
                    for cid in (item.get("kids") or [])[:30]:
                        try:
                            async with s.get(f"https://hacker-news.firebaseio.com/v0/item/{cid}.json") as r:
                                comment = await r.json(content_type=None)
                            if not comment or comment.get("deleted") or comment.get("dead"):
                                continue
                            text = _strip_html(comment.get("text") or "")
                            if len(text) < 40:
                                continue
                            text_l = text.lower()
                            if not any(kw in text_l for kw in TARGET_KEYWORDS):
                                continue
                            signals.append({
                                "source": "hackernews",
                                "signal_type": "hiring",
                                "signal_text": text[:500],
                                "url": f"https://news.ycombinator.com/item?id={cid}",
                                "company": _guess_company(text, ""),
                            })
                        except Exception:
                            pass
                        await asyncio.sleep(0.05)
                    break
            except Exception as e:
                log.debug("HN hiring: %s", e)
    except Exception as e:
        log.warning("HN fetch error: %s", e)

    log.info("HN signals: %d", len(signals))
    return signals


def _guess_company(text: str, fallback: str = "") -> str:
    """Extract a usable company/handle name from signal text."""
    t = text or ""
    # HN style: Company | Role | Location
    m = re.search(r"^([A-Z][A-Za-z0-9 .&\-]{2,40})\s*[\|–—\-]", t.strip())
    if m:
        return m.group(1).strip()[:80]
    m = re.search(
        r"(?i)\b(?:at|bei|@)\s+([A-Z][A-Za-z0-9 .&\-]{2,40})\b", t
    )
    if m:
        return m.group(1).strip()[:80]
    m = re.search(r"(?i)\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\s+(?:is hiring|sucht|raises?|raised|funds?)", t)
    if m:
        return m.group(1).strip()[:80]
    # domain from URL in text
    m = re.search(r"https?://(?:www\.)?([a-z0-9\-]+)\.(?:com|io|de|co|ai|app)", t, re.I)
    if m:
        return m.group(1).replace("-", " ").title()[:80]
    if fallback and fallback not in ("deleted", "unknown"):
        return f"HN:{fallback}"[:80]
    # first 4 words as slug
    words = re.findall(r"[A-Za-zÄÖÜäöüß0-9]{3,}", t)
    if words:
        return " ".join(words[:3])[:60]
    return "Lead-" + str(abs(hash(t[:80])) % 100000)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#x27;", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Source 2: Reddit buying intent
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_reddit_signals() -> list[dict]:
    """Reddit B2B intent — OAuth wenn Keys da, sonst Pullpush, sonst Google News Reddit-Query."""
    import aiohttp

    signals: list[dict] = []
    b2b_patterns = [
        re.compile(p, re.IGNORECASE) for p in [
            r"(suche|need|looking for|searching for).{0,40}(tool|software|app|lösung|solution|automation)",
            r"(wie automatisiert|how to automate|automate my)",
            r"(empfehlung|recommend).{0,30}(shopify|e-commerce|automation)",
            r"(welche|which|what).{0,20}(software|tool|app|platform)",
            r"(switching from|migrating from|wechsle von)",
            r"(budget|raised|funding|finanziert)",
            r"(shopify|ecommerce|e-commerce|dropship)",
        ]
    ]

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
        # 1) Reddit OAuth (wenn vorhanden)
        token = ""
        cid, secret = REDDIT_CID(), REDDIT_SECRET()
        if cid and secret:
            try:
                import base64
                auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
                async with s.post(
                    "https://www.reddit.com/api/v1/access_token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": f"Basic {auth}",
                        "User-Agent": REDDIT_UA,
                    },
                ) as r:
                    if r.status == 200:
                        token = (await r.json(content_type=None)).get("access_token") or ""
            except Exception as e:
                log.debug("Reddit OAuth: %s", e)

        if token:
            for sub in TARGET_SUBS[:6]:
                try:
                    async with s.get(
                        f"https://oauth.reddit.com/r/{sub}/new",
                        params={"limit": 25},
                        headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_UA},
                    ) as r:
                        if r.status != 200:
                            continue
                        data = await r.json(content_type=None)
                    for child in (data.get("data") or {}).get("children") or []:
                        post = (child.get("data") or {})
                        title = post.get("title") or ""
                        selftext = (post.get("selftext") or "")[:400]
                        full = f"{title} {selftext}"
                        full_l = full.lower()
                        if not any(kw in full_l for kw in TARGET_KEYWORDS) and not any(
                            p.search(full) for p in b2b_patterns
                        ):
                            continue
                        if len(full.strip()) < 25:
                            continue
                        signals.append({
                            "source": f"reddit/r/{sub}",
                            "signal_type": "purchase_intent",
                            "signal_text": f"{title[:200]} | {selftext[:200]}",
                            "url": f"https://reddit.com{post.get('permalink') or ''}",
                            "company": _guess_company(full, post.get("author") or ""),
                        })
                except Exception as e:
                    log.debug("Reddit oauth r/%s: %s", sub, e)
                await asyncio.sleep(0.5)

        # 2) Pullpush fallback (public archive API)
        if len(signals) < 3:
            for sub in ("shopify", "ecommerce", "dropship", "entrepreneur"):
                try:
                    async with s.get(
                        "https://api.pullpush.io/reddit/search/submission/",
                        params={"subreddit": sub, "size": 15, "sort": "desc"},
                        headers={"User-Agent": REDDIT_UA},
                    ) as r:
                        if r.status != 200:
                            continue
                        data = await r.json(content_type=None)
                    for post in data.get("data") or []:
                        title = post.get("title") or ""
                        selftext = (post.get("selftext") or "")[:400]
                        full = f"{title} {selftext}"
                        if len(full.strip()) < 25:
                            continue
                        full_l = full.lower()
                        if not any(kw in full_l for kw in TARGET_KEYWORDS):
                            continue
                        signals.append({
                            "source": f"reddit/r/{sub}",
                            "signal_type": "purchase_intent",
                            "signal_text": f"{title[:200]} | {selftext[:200]}",
                            "url": post.get("full_link") or post.get("url") or "",
                            "company": _guess_company(full, post.get("author") or ""),
                        })
                except Exception as e:
                    log.debug("Pullpush r/%s: %s", sub, e)
                await asyncio.sleep(0.4)

        # 3) Google News as Reddit-signal proxy if still empty
        if len(signals) < 2:
            try:
                q = "site:reddit.com shopify automation OR ecommerce tool"
                gurl = f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
                async with s.get(gurl, headers={"User-Agent": "Mozilla/5.0 B2BIntentRadar/2.0"}) as r:
                    if r.status == 200:
                        raw = await r.text(errors="ignore")
                        root = ET.fromstring(raw)
                        for item in root.findall(".//item")[:15]:
                            title = (item.findtext("title") or "")
                            link = (item.findtext("link") or "")
                            desc = _strip_html(item.findtext("description") or "")
                            full = f"{title} {desc}"
                            if len(full) < 20:
                                continue
                            signals.append({
                                "source": "reddit/gnews",
                                "signal_type": "purchase_intent",
                                "signal_text": full[:400],
                                "url": link,
                                "company": _guess_company(full, ""),
                            })
            except Exception as e:
                log.debug("Reddit gnews: %s", e)

    log.info("Reddit B2B signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Source 3: GitHub — orgs starting e-commerce projects
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_github_signals() -> list[dict]:
    """GitHub: neue Shopify/E-Com Repos (Org + User) = Tech-Adoption Signal."""
    token = GITHUB_TOKEN()
    import aiohttp

    signals: list[dict] = []
    hdrs = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "B2BIntentRadar/2.0",
    }
    if token:
        hdrs["Authorization"] = f"token {token}"

    queries = [
        "shopify created:>2026-01-01",
        "shopify automation in:name,description,readme",
        "ecommerce bot OR shopify app created:>2025-06-01",
        "topic:shopify pushed:>2026-01-01",
    ]

    async with aiohttp.ClientSession(headers=hdrs, timeout=aiohttp.ClientTimeout(total=25)) as s:
        for q in queries:
            try:
                async with s.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": "updated", "order": "desc", "per_page": 12},
                ) as r:
                    if r.status != 200:
                        log.debug("GitHub search %s status %s", q[:40], r.status)
                        continue
                    items = (await r.json(content_type=None)).get("items", [])
                for repo in items:
                    owner = repo.get("owner") or {}
                    login = owner.get("login") or "unknown"
                    desc = repo.get("description") or ""
                    signals.append({
                        "source": "github",
                        "signal_type": "tech_adoption",
                        "signal_text": (
                            f"{'Org' if owner.get('type')=='Organization' else 'User'} "
                            f"'{login}' Repo {repo.get('full_name')} — {desc}"
                        )[:400],
                        "url": repo.get("html_url") or "",
                        "company": login,
                    })
                await asyncio.sleep(1.2)
            except Exception as e:
                log.debug("GitHub search error: %s", e)

    log.info("GitHub signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Source 4: Funding RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_funding_signals() -> list[dict]:
    """RSS + Google News für Funding/E-Com/SaaS Signale."""
    import aiohttp

    signals: list[dict] = []
    # Weicher: fast alles aus diesen Feeds ist B2B-relevant; Keyword nur als Boost
    ecom_keywords = [
        "shopify", "e-commerce", "ecommerce", "online retail", "marketplace",
        "fulfillment", "dropshipping", "d2c", "direct-to-consumer",
        "saas", "automation", "ai", "startup", "funding", "series", "seed",
        "finanzierung", "telegram", "chatbot", "retail", "commerce",
    ]

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        for feed_url in FUNDING_RSS_FEEDS:
            try:
                async with s.get(
                    feed_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; B2BIntentRadar/2.0)",
                        "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    },
                ) as r:
                    if r.status != 200:
                        log.debug("RSS %s status %s", feed_url[:50], r.status)
                        continue
                    raw = await r.text(errors="ignore")

                # Google News sometimes returns incomplete XML — strip bad chars
                raw = raw.lstrip("\ufeff")
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError:
                    # try wrap / recover first channel
                    m = re.search(r"(<rss[\s\S]+</rss>)", raw)
                    if not m:
                        continue
                    root = ET.fromstring(m.group(1))

                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//item") or root.findall(".//atom:entry", ns)
                for item in items[:25]:
                    def _txt(tag: str) -> str:
                        el = item.find(tag)
                        if el is None:
                            el = item.find(f"atom:{tag}", ns)
                        if el is None:
                            return ""
                        # Atom link is often attribute
                        if tag == "link" and el.get("href"):
                            return el.get("href") or ""
                        return (el.text or "") if el is not None else ""

                    title = _txt("title")
                    summary = _txt("description") or _txt("summary")
                    link = _txt("link")
                    if not link:
                        link_el = item.find("atom:link", ns)
                        if link_el is not None:
                            link = link_el.get("href") or ""

                    combined = f"{title} {summary}"
                    combined_l = combined.lower()
                    # Google News Feeds sind bereits gefiltert → alle Items nehmen
                    is_gnews = "news.google.com" in feed_url
                    if not is_gnews and not any(kw in combined_l for kw in ecom_keywords):
                        continue
                    if len(title.strip()) < 10:
                        continue
                    host = "gnews"
                    try:
                        host = feed_url.split("/")[2]
                    except Exception:
                        pass
                    signals.append({
                        "source": f"rss:{host}",
                        "signal_type": "funding",
                        "signal_text": f"{title} | {_strip_html(summary)[:300]}",
                        "url": link or feed_url,
                        "company": _guess_company(f"{title} {summary}", ""),
                    })
            except Exception as e:
                log.debug("RSS feed error %s: %s", feed_url[:60], e)
            await asyncio.sleep(0.5)

    log.info("Funding RSS signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Claude: classify signal → extract company + buying intent
# ─────────────────────────────────────────────────────────────────────────────

# ── Keyword-based B2B signal scoring (no AI needed) ──────────────────────────
_B2B_KEYWORDS = {
    "Shopify Automation": ["shopify", "woocommerce", "e-commerce", "ecommerce", "bestellungen", "shop", "online-shop", "magento"],
    "Telegram Bot":       ["telegram", "bot", "automation", "automatisierung", "channel", "gruppe"],
    "AI Tools":           ["ai", "künstliche intelligenz", "chatgpt", "claude", "llm", "openai", "ki-tool"],
    "CRM / Lead Gen":     ["crm", "leads", "kunden", "kundenverwaltung", "newsletter", "email-marketing", "mailchimp"],
    "E-Mail Marketing":   ["email", "newsletter", "mailchimp", "klaviyo", "kampagne", "subscribers"],
    "Analytics":          ["analytics", "tracking", "dashboard", "reporting", "daten", "auswertung"],
    "Payment / Stripe":   ["stripe", "zahlung", "bezahlung", "checkout", "payment", "abonnement"],
}

_INDUSTRY_HINTS = {
    "E-Commerce":     ["shopify", "woocommerce", "produkte", "versand", "bestellungen", "shop"],
    "SaaS":           ["saas", "subscription", "software", "api", "developer", "startup"],
    "Retail":         ["retail", "laden", "store", "verkauf", "händler"],
    "Marketing":      ["marketing", "content", "social media", "seo", "ads", "instagram", "tiktok"],
    "Dienstleistung": ["agentur", "agency", "freelancer", "beratung", "consulting"],
}

def _keyword_classify(signals: list[dict]) -> list[dict]:
    """Keyword-based B2B signal classification — no API needed."""
    results = []
    for i, s in enumerate(signals[:MAX_SIGNALS_PER_RUN]):
        text = (s.get("signal_text", "") + " " + s.get("title", "")).lower()

        # Detect buy category
        buy_category = "E-Commerce Automation"
        for cat, kws in _B2B_KEYWORDS.items():
            if any(kw in text for kw in kws):
                buy_category = cat
                break

        # Detect industry
        industry = "E-Commerce"
        for ind, kws in _INDUSTRY_HINTS.items():
            if any(kw in text for kw in kws):
                industry = ind
                break

        # Company immer setzen (sonst 0 Leads in DB!)
        company = (s.get("company") or "").strip()
        if not company or company == "Unbekannt":
            company = _guess_company(s.get("signal_text", "") or s.get("title", ""), "")

        # Confidence: base 0.60, +bonus for intent keywords
        high_intent = ["suche", "looking for", "brauche", "empfehlung", "recommendation",
                       "budget", "kaufen", "buy", "best tool", "welches tool",
                       "funding", "raised", "hiring", "automation", "shopify"]
        conf = 0.60 + 0.04 * sum(1 for kw in high_intent if kw in text)
        conf = min(conf, 0.92)

        src = s.get("source", "")
        if src.startswith("reddit"):
            contact_hint = "Reddit-Reply"
        elif src.startswith("rss"):
            contact_hint = "E-Mail Outreach"
        elif src == "github":
            contact_hint = "GitHub Issue"
        elif src == "hackernews":
            contact_hint = "HN-Kommentar"
        else:
            contact_hint = "LinkedIn DM"

        results.append({
            **s,
            "index":        i,
            "company":      company,
            "industry":     industry,
            "size_est":     "Startup" if s.get("source") in ("hackernews", "github") else "KMU",
            "buy_category": buy_category,
            "confidence":   round(conf, 2),
            "contact_hint": contact_hint,
        })

    log.info("Keyword-classified %d signals", len(results))
    return results


async def classify_signals(signals: list[dict]) -> list[dict]:
    """Extract company + buying intent — AI if available, keyword-fallback otherwise."""
    if not signals:
        return []

    # Try AI first
    try:
        from modules.ai_client import ai_complete
        results: list[dict] = []
        batch_size = 10
        for i in range(0, min(len(signals), MAX_SIGNALS_PER_RUN), batch_size):
            batch = signals[i:i + batch_size]
            batch_text = "\n\n".join(
                f"[{j+1}] SOURCE: {s['source']} | TYPE: {s['signal_type']}\n{s['signal_text'][:300]}"
                for j, s in enumerate(batch)
            )
            prompt = f"""Analysiere B2B-Kaufabsichts-Signale, extrahiere Firmen-Info. Nur JSON:
[{{"index":1,"company":"Name","industry":"E-Commerce","size_est":"Startup","buy_category":"Shopify Automation","confidence":0.85,"contact_hint":"Reddit-Reply"}}]

Signale:
{batch_text}

Regeln: confidence 0-1, nur >0.4, max {len(batch)} Objekte, gültiges JSON."""
            raw = await ai_complete(prompt, model_hint="fast", max_tokens=600)
            if raw:
                cleaned = raw.strip()
                if "```" in cleaned:
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                classified = json.loads(cleaned.strip())
                if isinstance(classified, list):
                    for c in classified:
                        idx = c.get("index", 0) - 1
                        if 0 <= idx < len(batch):
                            results.append({**batch[idx], **c, "index": idx})
            await asyncio.sleep(2)
        if results:
            log.info("AI classified %d signals → %d leads", len(signals), len(results))
            return results
    except Exception as e:
        log.debug("AI classification failed (%s) — using keyword fallback", e)

    # Keyword fallback — always works, no API needed
    return _keyword_classify(signals)


# ─────────────────────────────────────────────────────────────────────────────
# Save to DB + aggregate into leads
# ─────────────────────────────────────────────────────────────────────────────

def save_signals(classified: list[dict]) -> list[dict]:
    """Save classified signals to DB and return high-confidence new leads."""
    now = int(time.time())
    new_high_leads: list[dict] = []

    with _db() as con:
        for s in classified:
            conf = float(s.get("confidence", 0))
            if conf < MIN_CONFIDENCE:
                continue
            try:
                con.execute("""
                    INSERT OR IGNORE INTO b2b_signals
                    (ts, source, company, signal_type, signal_text, url,
                     industry, size_est, buy_category, confidence, processed)
                    VALUES(?,?,?,?,?,?,?,?,?,?,0)
                """, (
                    now, s.get("source", ""), s.get("company", "Unbekannt"),
                    s.get("signal_type", ""), s.get("signal_text", "")[:500],
                    s.get("url", ""), s.get("industry", ""),
                    s.get("size_est", ""), s.get("buy_category", ""), conf,
                ))
            except Exception as e:
                log.warning("Ignored error: %s", e)

            # Aggregate into leads — immer, auch ohne "schönen" Firmennamen
            company = (s.get("company") or "").strip() or _guess_company(
                s.get("signal_text", ""), ""
            )
            if not company:
                company = f"Signal-{abs(hash(s.get('url') or s.get('signal_text',''))) % 100000}"

            existing = con.execute(
                "SELECT id, signal_count, best_conf FROM b2b_leads WHERE company=?",
                (company,),
            ).fetchone()

            if existing:
                new_count = existing["signal_count"] + 1
                new_conf = max(existing["best_conf"], conf)
                con.execute(
                    """UPDATE b2b_leads SET signal_count=?, best_conf=?, ts=? WHERE company=?""",
                    (new_count, new_conf, now, company),
                )
                if conf >= HIGH_CONF_ALERT and new_count == 1:
                    new_high_leads.append(s)
            else:
                con.execute(
                    """INSERT OR IGNORE INTO b2b_leads
                       (ts, company, industry, size_est, signal_count, best_conf,
                        buy_categories, contact_hint)
                       VALUES(?,?,?,?,1,?,?,?)""",
                    (
                        now, company, s.get("industry", ""), s.get("size_est", ""),
                        conf, s.get("buy_category", ""), s.get("contact_hint", ""),
                    ),
                )
                if conf >= HIGH_CONF_ALERT:
                    new_high_leads.append(s)
            # new_leads counter uses high_conf list; also track any new row via conf>=MIN
            if not existing and conf >= MIN_CONFIDENCE:
                # already inserted; count as lead even if below HIGH_CONF
                pass

    return new_high_leads


# ─────────────────────────────────────────────────────────────────────────────
# Telegram alerts
# ─────────────────────────────────────────────────────────────────────────────

async def _send_high_conf_alert(lead: dict) -> None:
    import aiohttp

    token   = TELEGRAM_TOKEN()
    chat_id = TELEGRAM_CHAT()
    if not token or not chat_id:
        return

    conf = lead.get("confidence", 0)
    text = (
        f"🎯 <b>B2B Intent Signal — Hohe Konfidenz!</b>\n\n"
        f"Firma: <b>{lead.get('company', '?')}</b>\n"
        f"Branche: {lead.get('industry', '?')}\n"
        f"Größe: {lead.get('size_est', '?')}\n"
        f"Kaufabsicht: <b>{lead.get('buy_category', '?')}</b>\n"
        f"Konfidenz: <b>{conf:.0%}</b>\n"
        f"Kontakt: {lead.get('contact_hint', '?')}\n"
        f"Quelle: {lead.get('source', '?')}\n"
        f"URL: {lead.get('url', '')[:120]}\n\n"
        f"<i>Signal: {lead.get('signal_text', '')[:200]}</i>"
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
    except Exception as e:
        log.debug("Telegram alert error: %s", e)


async def _send_scan_report(summary: dict) -> None:
    import aiohttp

    token   = TELEGRAM_TOKEN()
    chat_id = TELEGRAM_CHAT()
    if not token or not chat_id:
        return

    top = summary.get("top_leads", [])
    lines = [
        f"📡 <b>B2B Intent Radar — Scan Bericht</b>",
        f"Signale gefunden: {summary['signals']}",
        f"Neue Leads: {summary['new_leads']}",
        f"High-Conf Alerts: {summary['alerts']}",
        f"Gesamt Leads in DB: {summary['total_leads']}",
    ]
    if top:
        lines.append("\n<b>Top Leads jetzt:</b>")
        for lead in top[:5]:
            lines.append(
                f"• <b>{lead['company']}</b> ({lead['size_est']}) — "
                f"{lead['buy_categories']} [{lead['best_conf']:.0%}]"
            )

    text = "\n".join(lines)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception as e:
        log.debug("Telegram report error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Full scan pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_b2b_scan() -> dict:
    """Full B2B Intent Radar pipeline: fetch all sources → classify → save → alert."""
    log.info("[B2BIntentRadar] Starting full scan")

    # Fetch all sources in parallel
    hn_task, reddit_task, github_task, funding_task = await asyncio.gather(
        fetch_hn_signals(),
        fetch_reddit_signals(),
        fetch_github_signals(),
        fetch_funding_signals(),
        return_exceptions=True,
    )

    all_signals: list[dict] = []
    for result in [hn_task, reddit_task, github_task, funding_task]:
        if isinstance(result, list):
            all_signals.extend(result)

    log.info("Total raw signals: %d", len(all_signals))

    # Deduplicate by URL
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for s in all_signals:
        url = s.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(s)
        elif not url:
            deduped.append(s)

    # Classify with Claude
    classified = await classify_signals(deduped)

    # Save and get high-confidence alerts
    high_conf = save_signals(classified)

    # Send Telegram alerts for high-confidence leads
    for lead in high_conf[:5]:
        await _send_high_conf_alert(lead)
        await asyncio.sleep(0.5)

    # Stats
    with _db() as con:
        total_leads  = con.execute("SELECT COUNT(*) FROM b2b_leads").fetchone()[0]
        top_leads_db = con.execute(
            "SELECT company, size_est, buy_categories, best_conf FROM b2b_leads "
            "ORDER BY best_conf DESC LIMIT 10"
        ).fetchall()

    # new_leads = alle klassifizierten mit conf>=MIN, nicht nur high_conf alerts
    new_leads_n = sum(1 for c in classified if float(c.get("confidence") or 0) >= MIN_CONFIDENCE)

    summary = {
        "signals":     len(deduped),
        "classified":  len(classified),
        "new_leads":   new_leads_n,
        "alerts":      len(high_conf),
        "total_leads": total_leads,
        "top_leads":   [dict(r) for r in top_leads_db],
        "sources": {
            "hn": sum(1 for s in deduped if s.get("source") == "hackernews"),
            "reddit": sum(1 for s in deduped if str(s.get("source","")).startswith("reddit")),
            "github": sum(1 for s in deduped if s.get("source") == "github"),
            "rss": sum(1 for s in deduped if str(s.get("source","")).startswith("rss")),
        },
    }

    with _db() as con:
        con.execute("INSERT INTO b2b_scans(ts,signals,leads,alerts) VALUES(?,?,?,?)",
                    (int(time.time()), len(deduped), new_leads_n, len(high_conf)))

    await _send_scan_report(summary)
    log.info("[B2BIntentRadar] Scan complete: %s", summary)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    try:
        with _db() as con:
            total_signals = con.execute("SELECT COUNT(*) FROM b2b_signals").fetchone()[0]
            total_leads   = con.execute("SELECT COUNT(*) FROM b2b_leads").fetchone()[0]
            high_leads    = con.execute(
                "SELECT COUNT(*) FROM b2b_leads WHERE best_conf>=?", (HIGH_CONF_ALERT,)
            ).fetchone()[0]
            top_leads = con.execute(
                "SELECT company, industry, size_est, signal_count, best_conf, "
                "buy_categories, contact_hint, outreach_sent "
                "FROM b2b_leads ORDER BY best_conf DESC LIMIT 20"
            ).fetchall()
            last_scan = con.execute(
                "SELECT ts, signals, leads, alerts FROM b2b_scans ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return {
            "total_signals":    total_signals,
            "total_leads":      total_leads,
            "high_conf_leads":  high_leads,
            "top_leads":        [dict(r) for r in top_leads],
            "last_scan":        dict(last_scan) if last_scan else None,
            "min_confidence":   MIN_CONFIDENCE,
            "alert_threshold":  HIGH_CONF_ALERT,
        }
    except Exception as e:
        return {"error": str(e)}


def get_leads_for_export() -> list[dict]:
    """Export all leads as a list — for selling or outreach."""
    try:
        with _db() as con:
            rows = con.execute(
                "SELECT * FROM b2b_leads WHERE outreach_sent=0 ORDER BY best_conf DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


async def mark_outreach_sent(company: str) -> bool:
    """Mark a lead as contacted."""
    with _db() as con:
        con.execute("UPDATE b2b_leads SET outreach_sent=1 WHERE company=?", (company,))
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler entry point
# ─────────────────────────────────────────────────────────────────────────────

async def scheduled_b2b_scan() -> str:
    try:
        result = await run_b2b_scan()
        return (
            f"B2BIntentRadar: {result['signals']} signale, "
            f"{result['classified']} klassifiziert, "
            f"{result['new_leads']} neue leads, "
            f"gesamt={result['total_leads']}"
        )
    except Exception as e:
        return f"B2BIntentRadar Fehler: {e}"


# Init
try:
    init_db()
except Exception as e:
    log.warning("B2BIntentRadar DB init failed: %s", e)
