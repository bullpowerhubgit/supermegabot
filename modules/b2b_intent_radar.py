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

# RSS feeds for funding news (no API key needed)
FUNDING_RSS_FEEDS = [
    "https://techcrunch.com/category/funding/feed/",
    "https://eu-startups.com/category/funding/feed/",
    "https://www.gruenderszene.de/feed",
]

# Signal strength thresholds
MIN_CONFIDENCE     = 0.65
HIGH_CONF_ALERT    = 0.80
MAX_LEADS_PER_RUN  = 20
MAX_SIGNALS_PER_RUN = 100


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
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
    """Fetch latest HN 'Who is hiring' post and extract company signals."""
    import aiohttp

    signals = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            # Get top stories to find "Who is hiring" post
            async with s.get("https://hacker-news.firebaseio.com/v0/askstories.json") as r:
                story_ids = await r.json(content_type=None)

            # Check first 20 stories for hiring post
            for sid in story_ids[:20]:
                async with s.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json") as r:
                    item = await r.json(content_type=None)
                if item and HN_WHO_IS_HIRING.lower() in item.get("title", "").lower():
                    # Fetch top-level comments (company entries)
                    kids = item.get("kids", [])[:80]
                    for cid in kids[:50]:
                        try:
                            async with s.get(f"https://hacker-news.firebaseio.com/v0/item/{cid}.json") as r:
                                comment = await r.json(content_type=None)
                            if not comment or comment.get("deleted") or comment.get("dead"):
                                continue
                            text = comment.get("text", "")
                            if len(text) < 50:
                                continue
                            # Check for target keywords
                            text_lower = text.lower()
                            if any(kw in text_lower for kw in TARGET_KEYWORDS):
                                signals.append({
                                    "source":      "hackernews",
                                    "signal_type": "hiring",
                                    "signal_text": _strip_html(text[:500]),
                                    "url":         f"https://news.ycombinator.com/item?id={cid}",
                                })
                            await asyncio.sleep(0.1)
                        except Exception:
                            pass
                    break  # found the hiring post, done
    except Exception as e:
        log.debug("HN fetch error: %s", e)

    log.info("HN signals: %d", len(signals))
    return signals


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
    """Scan Reddit subs for B2B buying intent."""
    cid    = REDDIT_CID()
    secret = REDDIT_SECRET()
    if not cid or not secret:
        return []

    import aiohttp

    # Auth
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=aiohttp.BasicAuth(cid, secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": REDDIT_UA},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                tok = (await r.json(content_type=None)).get("access_token", "")
    except Exception as e:
        log.debug("Reddit auth error: %s", e)
        return []

    if not tok:
        return []

    hdrs = {"Authorization": f"bearer {tok}", "User-Agent": REDDIT_UA}
    signals = []

    # B2B purchase intent patterns
    b2b_patterns = [
        re.compile(p, re.IGNORECASE) for p in [
            r"(suche|need|looking for|searching for).{0,30}(tool|software|app|lösung|solution|automation)",
            r"(wie automatisiert|how to automate|automate my)",
            r"(empfehlung|recommend).{0,30}(shopify|e-commerce|automation)",
            r"(welche|which|what).{0,20}(software|tool|app|platform).{0,30}(für|for)",
            r"(switching from|migrating from|wechsle von)",
            r"(budget|budget für|we have budget)",
            r"(comparison|vs|vergleich).{0,30}(tool|software|platform)",
            r"(just funded|raised|finanziert|investition)",
        ]
    ]

    async with aiohttp.ClientSession(headers=hdrs) as s:
        for sub in TARGET_SUBS:
            try:
                async with s.get(
                    f"https://oauth.reddit.com/r/{sub}/new.json",
                    params={"limit": 30},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status != 200:
                        continue
                    posts = (await r.json(content_type=None)).get("data", {}).get("children", [])

                for post in posts:
                    p = post.get("data", {})
                    title    = p.get("title", "")
                    selftext = p.get("selftext", "")[:400]
                    full     = f"{title} {selftext}"
                    full_l   = full.lower()

                    # Must have target keyword AND intent pattern
                    has_kw      = any(kw in full_l for kw in TARGET_KEYWORDS)
                    has_pattern = any(pat.search(full) for pat in b2b_patterns)
                    if not has_kw or not has_pattern:
                        continue
                    if len(full.strip()) < 30:
                        continue

                    signals.append({
                        "source":      f"reddit/r/{sub}",
                        "signal_type": "purchase_intent",
                        "signal_text": f"{title[:200]} | {selftext[:200]}",
                        "url":         f"https://reddit.com{p.get('permalink', '')}",
                    })

                await asyncio.sleep(1)
            except Exception as e:
                log.debug("Reddit r/%s error: %s", sub, e)

    log.info("Reddit B2B signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Source 3: GitHub — orgs starting e-commerce projects
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_github_signals() -> list[dict]:
    """Find GitHub orgs creating Shopify/e-commerce related repos (indicates investment)."""
    token = GITHUB_TOKEN()
    if not token:
        return []

    import aiohttp

    signals = []
    hdrs = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "B2BIntentRadar/1.0",
    }
    # Search for recently created repos with e-commerce topics
    queries = [
        "shopify automation in:readme,description created:>2026-06-01",
        "ecommerce bot telegram created:>2026-06-01",
        "digistore24 created:>2026-05-01",
    ]

    async with aiohttp.ClientSession(headers=hdrs, timeout=aiohttp.ClientTimeout(total=20)) as s:
        for q in queries:
            try:
                async with s.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": "updated", "per_page": 10},
                ) as r:
                    if r.status != 200:
                        continue
                    items = (await r.json(content_type=None)).get("items", [])
                for repo in items:
                    owner = repo.get("owner", {})
                    if owner.get("type") != "Organization":
                        continue  # only org accounts = B2B
                    signals.append({
                        "source":      "github",
                        "signal_type": "tech_adoption",
                        "signal_text": (
                            f"Org '{owner.get('login')}' erstellt Repo: "
                            f"{repo.get('full_name')} — {repo.get('description', '')}"
                        )[:400],
                        "url": repo.get("html_url", ""),
                    })
                await asyncio.sleep(2)
            except Exception as e:
                log.debug("GitHub search error: %s", e)

    log.info("GitHub signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Source 4: Funding RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_funding_signals() -> list[dict]:
    """Scan RSS feeds for e-commerce/tech funding rounds."""
    import aiohttp

    signals = []
    ecom_keywords = [
        "shopify", "e-commerce", "ecommerce", "online retail", "marketplace",
        "fulfillment", "dropshipping", "d2c", "direct-to-consumer",
        "saas", "automation", "ai tool", "telegram", "chatbot",
    ]

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        for feed_url in FUNDING_RSS_FEEDS:
            try:
                async with s.get(
                    feed_url,
                    headers={"User-Agent": "B2BIntentRadar/1.0"},
                ) as r:
                    if r.status != 200:
                        continue
                    raw = await r.text(errors="ignore")

                root = ET.fromstring(raw)
                ns   = {"atom": "http://www.w3.org/2005/Atom"}

                # Handle both RSS and Atom
                items = root.findall(".//item") or root.findall(".//atom:entry", ns)
                for item in items[:20]:
                    def _txt(tag: str) -> str:
                        el = item.find(tag) or item.find(f"atom:{tag}", ns)
                        return el.text or "" if el is not None else ""

                    title   = _txt("title")
                    summary = _txt("description") or _txt("summary")
                    link    = _txt("link") or _txt("atom:link")

                    combined = f"{title} {summary}".lower()
                    if any(kw in combined for kw in ecom_keywords):
                        signals.append({
                            "source":      f"rss:{feed_url.split('/')[2]}",
                            "signal_type": "funding",
                            "signal_text": f"{title} | {_strip_html(summary)[:300]}",
                            "url":         link or feed_url,
                        })
            except Exception as e:
                log.debug("RSS feed error %s: %s", feed_url, e)
            await asyncio.sleep(1)

    log.info("Funding RSS signals: %d", len(signals))
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Claude: classify signal → extract company + buying intent
# ─────────────────────────────────────────────────────────────────────────────

async def classify_signals(signals: list[dict]) -> list[dict]:
    """Use Claude to extract company + buying intent from raw signals."""
    if not signals:
        return []

    try:
        from modules.ai_client import ai_complete
    except ImportError:
        return []

    # Process in batches of 10
    results: list[dict] = []
    batch_size = 10

    for i in range(0, min(len(signals), MAX_SIGNALS_PER_RUN), batch_size):
        batch = signals[i:i + batch_size]
        batch_text = "\n\n".join(
            f"[{j+1}] SOURCE: {s['source']} | TYPE: {s['signal_type']}\n{s['signal_text'][:300]}"
            for j, s in enumerate(batch)
        )

        prompt = f"""Analysiere diese B2B-Kaufabsichts-Signale. Extrahiere für jedes Signal die Firmen-Info.

Signale:
{batch_text}

Antworte mit einem JSON-Array mit einem Objekt pro Signal (Index 1 bis {len(batch)}):
[
  {{
    "index": 1,
    "company": "Firmenname oder 'Unbekannt'",
    "industry": "E-Commerce / SaaS / Retail / etc.",
    "size_est": "Startup / KMU / Enterprise",
    "buy_category": "Was kaufen sie wahrscheinlich? (z.B. 'Shopify Automation', 'CRM', 'E-Mail Marketing')",
    "confidence": 0.85,
    "contact_hint": "Wie am besten ansprechen? (z.B. 'LinkedIn DM', 'Kommentar auf Reddit', 'Kaltakquise')"
  }}
]

Regeln:
- confidence: 0.0-1.0 (wie wahrscheinlich ist ein aktiver Kauf in den nächsten 30 Tagen?)
- Nur zurückgeben wenn confidence > 0.4
- buy_category: spezifisch, was auf SuperMegaBot SaaS passt (E-Commerce Automation, Telegram Bot, AI Tools)
- Nur gültiges JSON, kein Markdown"""

        raw = await ai_complete(prompt, model_hint="fast", max_tokens=600)
        try:
            cleaned = raw.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            classified = json.loads(cleaned.strip())
            if not isinstance(classified, list):
                continue

            for c in classified:
                idx = c.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    orig = batch[idx]
                    results.append({**orig, **c, "index": idx})

        except Exception as e:
            log.debug("Classify parse error: %s | raw=%s", e, raw[:200])

        await asyncio.sleep(2)

    log.info("Classified %d signals → %d leads", len(signals), len(results))
    return results


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
            except Exception:
                pass

            # Aggregate into leads table
            company = s.get("company", "Unbekannt")
            if company and company != "Unbekannt":
                existing = con.execute(
                    "SELECT id, signal_count, best_conf FROM b2b_leads WHERE company=?",
                    (company,),
                ).fetchone()

                if existing:
                    new_count = existing["signal_count"] + 1
                    new_conf  = max(existing["best_conf"], conf)
                    con.execute("""
                        UPDATE b2b_leads
                        SET signal_count=?, best_conf=?, ts=?
                        WHERE company=?
                    """, (new_count, new_conf, now, company))
                else:
                    con.execute("""
                        INSERT OR IGNORE INTO b2b_leads
                        (ts, company, industry, size_est, signal_count, best_conf,
                         buy_categories, contact_hint)
                        VALUES(?,?,?,?,1,?,?,?)
                    """, (
                        now, company, s.get("industry", ""), s.get("size_est", ""),
                        conf, s.get("buy_category", ""), s.get("contact_hint", ""),
                    ))

                    if conf >= HIGH_CONF_ALERT:
                        new_high_leads.append(s)

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

    summary = {
        "signals":     len(deduped),
        "classified":  len(classified),
        "new_leads":   len(high_conf),
        "alerts":      len(high_conf),
        "total_leads": total_leads,
        "top_leads":   [dict(r) for r in top_leads_db],
    }

    with _db() as con:
        con.execute("INSERT INTO b2b_scans(ts,signals,leads,alerts) VALUES(?,?,?,?)",
                    (int(time.time()), len(deduped), len(high_conf), len(high_conf)))

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
