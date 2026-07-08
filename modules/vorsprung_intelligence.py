#!/usr/bin/env python3
"""
VORSPRUNG Intelligence Engine
Sammelt öffentliche Signale aus DACH-Rechtsdatenbanken + Regret-Intelligence
und verkauft sie als täglichen Intelligence-Briefing an PE-Firmen / Hedge Funds.

Signal-Quellen (100% öffentlich, keine API-Keys nötig):
  - Bundesanzeiger (Insolvenzen, Unternehmensänderungen)
  - EUIPO (EU-Markenanmeldungen)
  - DPMA (Deutsche Patentanmeldungen)
  - Reddit (Regret-Signals: r/investing, r/finanzen, r/personalfinance)

Delivery:
  - Supabase: vorsprung_signals Tabelle
  - Telegram: täglicher Briefing-Report
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("VorsprungIntelligence")

BASE_DIR = Path(__file__).parent.parent

ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


# ── Supabase helper ──────────────────────────────────────────────────────────

async def _supa_insert(rows: list[dict]) -> int:
    if not SUPABASE_URL or not rows:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/vorsprung_signals"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=rows, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return len(rows) if r.status in (200, 201) else 0
    except Exception as e:
        log.warning(f"Supabase insert error: {e}")
        return 0


async def _supa_recent(limit: int = 50) -> list[dict]:
    if not SUPABASE_URL:
        return []
    url = f"{SUPABASE_URL}/rest/v1/vorsprung_signals?order=created_at.desc&limit={limit}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        log.warning(f"Supabase fetch error: {e}")
    return []


# ── Telegram helper ──────────────────────────────────────────────────────────

async def _tg(msg: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": msg[:4000],
                "parse_mode": "HTML",
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status == 200
    except Exception as e:
        log.warning(f"TG error: {e}")
        return False


# ── Claude AI Synthesis ──────────────────────────────────────────────────────

async def _claude_analyze(system: str, user_msg: str) -> str:
    if not ANTHROPIC_KEY:
        return "ANTHROPIC_API_KEY fehlt"
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["content"][0]["text"].strip()
                return f"Claude API {r.status}"
    except Exception as e:
        return f"Claude error: {e}"


# ── Scraper 1: OpenCorporates — Deutsche Unternehmensdaten (gratis API) ──────

async def scrape_opencorporates_de(query: str = "insolvenz", max_results: int = 20) -> list[dict]:
    """
    OpenCorporates freie API — deutsche Unternehmensstatus-Änderungen.
    Zeigt inaktive/aufgelöste Unternehmen → Insolvenz-Signal.
    """
    signals = []
    url = "https://api.opencorporates.com/v0.4/companies/search"
    params = {
        "q": query,
        "jurisdiction_code": "de",
        "inactive": "true",
        "per_page": min(max_results, 30),
    }
    try:
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    log.warning(f"OpenCorporates status {r.status}")
                    return signals
                data = await r.json()
                companies = data.get("results", {}).get("companies", [])
                for entry in companies[:max_results]:
                    c = entry.get("company", {})
                    name = c.get("name", "")
                    if not name:
                        continue
                    signals.append({
                        "signal_type": "company_change",
                        "source": "opencorporates_de",
                        "entity_name": name,
                        "signal_data": {
                            "company_number": c.get("company_number", ""),
                            "status": c.get("current_status", "inactive"),
                            "incorporation_date": c.get("incorporation_date", ""),
                            "dissolution_date": c.get("dissolution_date", ""),
                            "registered_address": str(c.get("registered_address", "")),
                            "jurisdiction": "de",
                            "opencorporates_url": c.get("opencorporates_url", ""),
                        },
                        "intelligence_score": 82,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as e:
        log.warning(f"OpenCorporates scrape error: {e}")
    log.info(f"OpenCorporates DE: {len(signals)} Signale gefunden")
    return signals


async def scrape_opencorporates_active(sector: str = "software", max_results: int = 15) -> list[dict]:
    """Neue aktive DACH-Unternehmen — M&A / Sales-Intelligence."""
    signals = []
    url = "https://api.opencorporates.com/v0.4/companies/search"
    params = {
        "q": sector,
        "jurisdiction_code": "de",
        "inactive": "false",
        "per_page": min(max_results, 30),
        "order": "incorporation_date",
    }
    try:
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return signals
                data = await r.json()
                companies = data.get("results", {}).get("companies", [])
                for entry in companies[:max_results]:
                    c = entry.get("company", {})
                    name = c.get("name", "")
                    if not name:
                        continue
                    inc_date = c.get("incorporation_date", "")
                    signals.append({
                        "signal_type": "new_company",
                        "source": "opencorporates_de_new",
                        "entity_name": name,
                        "signal_data": {
                            "company_number": c.get("company_number", ""),
                            "incorporation_date": inc_date,
                            "registered_address": str(c.get("registered_address", "")),
                            "jurisdiction": "de",
                            "sector_query": sector,
                            "opencorporates_url": c.get("opencorporates_url", ""),
                            "sales_window_days": 30,
                        },
                        "intelligence_score": 78,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as e:
        log.warning(f"OpenCorporates new company error: {e}")
    return signals


# ── Scraper 2: EUIPO EU-Markenanmeldungen ────────────────────────────────────

async def scrape_euipo_trademarks(query: str = "", lang: str = "de", limit: int = 20) -> list[dict]:
    """Holt neue EU-Markenanmeldungen aus der EUIPO-Datenbank."""
    signals = []
    url = "https://euipo.europa.eu/api/trademark/search/v2"
    params = {
        "language": lang,
        "limit": limit,
        "offset": 0,
        "status": "Filed",
        "sort": "applicationDate",
        "sortDir": "desc",
    }
    if query:
        params["text"] = query

    try:
        async with aiohttp.ClientSession(headers={**HEADERS_BROWSER, "Accept": "application/json"}) as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json()
                    trademarks = data.get("trademarks", data.get("results", []))
                    for tm in trademarks[:limit]:
                        name = tm.get("trademarkName") or tm.get("name", "")
                        applicant = ""
                        if tm.get("holders"):
                            applicant = tm["holders"][0].get("name", "")
                        signals.append({
                            "signal_type": "trademark_filing",
                            "source": "euipo",
                            "entity_name": applicant or name,
                            "signal_data": {
                                "trademark": name,
                                "applicant": applicant,
                                "application_date": tm.get("applicationDate", ""),
                                "application_number": tm.get("applicationNumber", ""),
                                "nice_classes": tm.get("niceClasses", []),
                                "status": tm.get("status", "Filed"),
                            },
                            "intelligence_score": 72,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                else:
                    log.warning(f"EUIPO status {r.status}")
    except Exception as e:
        log.warning(f"EUIPO scrape error: {e}")
    log.info(f"EUIPO: {len(signals)} Markenanmeldungen gefunden")
    return signals


# ── Scraper 3: DPMA Deutsche Patente ────────────────────────────────────────

async def scrape_dpma_patents(query: str = "artificial intelligence", limit: int = 20) -> list[dict]:
    """Holt neue Patentanmeldungen aus dem DPMA-Register."""
    signals = []
    # DPMA DEPATISnet public search
    url = "https://depatisnet.dpma.de/DepatisNet/depatisnet"
    params = {
        "action": "search",
        "lang": "de",
        "so": "pd",
        "sf": "1",
        "fl": "1",
        "ps": limit,
        "an": "",
        "ab": query,
        "cl": "",
        "exp": "off",
        "fop": "AND",
        "q": query,
    }
    try:
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    html = await r.text()
                    # Extract patent numbers and titles
                    patents = re.findall(
                        r'<td[^>]*class="[^"]*nr[^"]*"[^>]*>([^<]+)</td>.*?<td[^>]*class="[^"]*ti[^"]*"[^>]*>([^<]+)</td>.*?<td[^>]*class="[^"]*pa[^"]*"[^>]*>([^<]+)</td>',
                        html, re.DOTALL
                    )
                    if not patents:
                        # Alternative: search for any table cells with patent data
                        rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
                        for row in rows[:limit]:
                            cells = re.findall(r'<td[^>]*>([^<]{5,200})</td>', row)
                            if len(cells) >= 3 and re.match(r'DE\d+', cells[0].strip()):
                                signals.append({
                                    "signal_type": "patent_filing",
                                    "source": "dpma",
                                    "entity_name": cells[2].strip()[:100] if len(cells) > 2 else "",
                                    "signal_data": {
                                        "patent_number": cells[0].strip(),
                                        "title": cells[1].strip()[:200] if len(cells) > 1 else "",
                                        "applicant": cells[2].strip()[:100] if len(cells) > 2 else "",
                                        "query": query,
                                    },
                                    "intelligence_score": 78,
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                })
                    else:
                        for number, title, applicant in patents[:limit]:
                            signals.append({
                                "signal_type": "patent_filing",
                                "source": "dpma",
                                "entity_name": applicant.strip()[:100],
                                "signal_data": {
                                    "patent_number": number.strip(),
                                    "title": title.strip()[:200],
                                    "applicant": applicant.strip()[:100],
                                    "query": query,
                                },
                                "intelligence_score": 82,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            })
                else:
                    log.warning(f"DPMA status {r.status}")
    except Exception as e:
        log.warning(f"DPMA scrape error: {e}")
    log.info(f"DPMA: {len(signals)} Patentanmeldungen gefunden")
    return signals


# ── Scraper 4: Reddit Regret Intelligence ───────────────────────────────────

# ── Scraper 4a: Hacker News — Tech/Finance Leading Signals ──────────────────

HN_FINANCE_KEYWORDS = [
    # English M&A / Finance
    "acquisition", "acqui", "merger", "funding", "Series A", "Series B", "Series C",
    "IPO", "bankrupt", "shutdown", "pivot", "layoff", "laid off", "insolvency",
    "raise", "raised", "raised $", "investment", "investor", "venture",
    "open source", "launches", "launch", "releases", "announce",
    # Business signals
    "B2B", "SaaS", "enterprise", "valuation", "revenue", "profit",
    "patent", "trademark", "license", "partnership", "deal",
    "market", "growth", "decline", "disruption",
    # Tech business
    "AI startup", "startup", "platform", "API", "product hunt",
    "Show HN", "Ask HN: who is hiring",
    # German
    "Investition", "Übernahme", "Insolvenz", "Startup", "Finanzierung",
]

async def scrape_hackernews_signals(min_score: int = 50, limit: int = 30) -> list[dict]:
    """
    Hacker News Top/New Stories — Finance & M&A Signals.
    Gratis, keine Auth, exzellente Qualität.
    """
    signals = []
    base = "https://hacker-news.firebaseio.com/v0"
    try:
        async with aiohttp.ClientSession(headers=HEADERS_BROWSER) as s:
            # Get top + new story IDs
            top_ids = []
            for endpoint in ["topstories", "newstories"]:
                async with s.get(f"{base}/{endpoint}.json", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        ids = await r.json()
                        top_ids.extend(ids[:50])

            # Fetch stories in parallel batches
            async def fetch_story(sid: int) -> Optional[dict]:
                try:
                    async with s.get(f"{base}/item/{sid}.json", timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            return await r.json()
                except Exception:
                    pass
                return None

            batch = await asyncio.gather(*[fetch_story(sid) for sid in top_ids[:limit]], return_exceptions=True)

            for story in batch:
                if not isinstance(story, dict):
                    continue
                title = story.get("title", "")
                score = story.get("score", 0)
                url_str = story.get("url", "")
                if not title or score < min_score:
                    continue
                # Check if finance/business relevant
                title_lower = title.lower()
                is_relevant = any(kw.lower() in title_lower for kw in HN_FINANCE_KEYWORDS)
                if not is_relevant:
                    continue

                intelligence_score = min(95, 40 + min(score // 5, 55))
                signals.append({
                    "signal_type": "market_signal",
                    "source": "hackernews",
                    "entity_name": title[:100],
                    "signal_data": {
                        "title": title,
                        "score": score,
                        "comments": story.get("descendants", 0),
                        "url": url_str,
                        "hn_id": story.get("id"),
                        "time": story.get("time"),
                        "by": story.get("by", ""),
                    },
                    "intelligence_score": intelligence_score,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

    except Exception as e:
        log.warning(f"HackerNews scrape error: {e}")
    log.info(f"HackerNews: {len(signals)} Finance-Signale gefunden")
    return signals


# ── Scraper 4b: Twitter/X Search — Regret + Finance Signals ─────────────────

TWITTER_SEARCH_QUERIES = [
    "\"I wish I had bought\" lang:en -is:retweet",
    "\"should have invested\" lang:en -is:retweet",
    "\"bereue nicht gekauft\" lang:de -is:retweet",
    "\"FOMO\" lang:en filter:links -is:retweet",
    "\"hätte investiert\" lang:de -is:retweet",
]

async def scrape_twitter_regret_signals(max_results: int = 10) -> list[dict]:
    """
    Twitter/X API v2 Search — Regret Signals für Finanzmarkt-Vorhersage.
    Nutzt Rudolf's existierende OAuth 1.0a Credentials (@rudibot84).
    """
    signals = []
    if not all([TWITTER_API_KEY, TWITTER_SECRET, TWITTER_TOKEN, TWITTER_TOKEN_SECRET]):
        log.warning("Twitter OAuth keys fehlen für Regret-Scraper")
        return signals

    import hmac, hashlib, base64, urllib.parse, secrets as _secrets

    for query in TWITTER_SEARCH_QUERIES[:3]:
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {
            "query": query,
            "max_results": max_results,
            "tweet.fields": "public_metrics,created_at,lang",
        }
        # Build OAuth 1.0a signature
        ts = str(int(time.time()))
        nonce = _secrets.token_hex(16)
        all_params = {
            **params,
            "oauth_consumer_key": TWITTER_API_KEY,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": ts,
            "oauth_token": TWITTER_TOKEN,
            "oauth_version": "1.0",
        }
        sorted_params = "&".join(
            f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_str = "&".join([
            "GET",
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(sorted_params, safe=""),
        ])
        signing_key = f"{urllib.parse.quote(TWITTER_SECRET, safe='')}&{urllib.parse.quote(TWITTER_TOKEN_SECRET, safe='')}"
        sig = base64.b64encode(
            hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()
        ).decode()
        oauth_params = {k: v for k, v in all_params.items() if k.startswith("oauth_")}
        oauth_params["oauth_signature"] = sig
        auth_header = "OAuth " + ", ".join(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    url, params=params,
                    headers={"Authorization": auth_header},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        tweets = data.get("data", [])
                        for tw in tweets:
                            metrics = tw.get("public_metrics", {})
                            likes = metrics.get("like_count", 0)
                            rt = metrics.get("retweet_count", 0)
                            resonance = min(100, 40 + min((likes + rt * 3) // 2, 60))
                            signals.append({
                                "signal_type": "regret_signal",
                                "source": "twitter_x",
                                "entity_name": query[:60],
                                "signal_data": {
                                    "text": tw.get("text", "")[:280],
                                    "tweet_id": tw.get("id", ""),
                                    "likes": likes,
                                    "retweets": rt,
                                    "created_at_tw": tw.get("created_at", ""),
                                    "query": query,
                                    "url": f"https://x.com/i/web/status/{tw.get('id', '')}",
                                },
                                "intelligence_score": resonance,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            })
                    elif r.status == 429:
                        log.warning("Twitter rate limit — pause")
                        await asyncio.sleep(5)
                    else:
                        log.warning(f"Twitter search {r.status} for query: {query[:40]}")
        except Exception as e:
            log.warning(f"Twitter search error: {e}")

    log.info(f"Twitter Regret: {len(signals)} Signale gefunden")
    return signals


async def scrape_all_regret_signals() -> list[dict]:
    """Regret-Signals von HN + Twitter + Reddit parallel sammeln."""
    tasks = [
        scrape_hackernews_signals(min_score=30, limit=40),
        scrape_twitter_regret_signals(max_results=10),
        # Reddit: OAuth-Search mit RSS-Fallback
        reddit_search_oauth("I wish I had bought", "investing", 15),
        reddit_search_oauth("regret not buying", "personalfinance", 10),
        scrape_reddit_finance_rss("ValueInvesting", 20),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined = []
    for r in results:
        if isinstance(r, list):
            combined.extend(r)
    log.info(f"Gesamt Regret+Market Signale: {len(combined)}")
    return combined


# ── AI Synthesis: Tägliches Briefing ────────────────────────────────────────

async def generate_intelligence_briefing(signals: list[dict]) -> str:
    """Lässt Claude das tägliche Intelligence-Briefing schreiben."""
    if not signals:
        return "Keine Signale für heute."

    # Gruppiere nach Typ
    legal = [s for s in signals if s["signal_type"] in ("insolvency", "company_change", "trademark_filing", "patent_filing")]
    regret = [s for s in signals if s["signal_type"] == "regret_signal"]

    legal_summary = "\n".join([
        f"- [{s['signal_type'].upper()}] {s.get('entity_name','?')} | Score: {s.get('intelligence_score',0)} | Quelle: {s['source']}"
        for s in legal[:15]
    ])
    regret_summary = "\n".join([
        f"- [{s['signal_data'].get('subreddit','?')}] Score:{s['signal_data'].get('score',0)} | {s['signal_data'].get('title','')[:100]}"
        for s in sorted(regret, key=lambda x: x['signal_data'].get('score', 0), reverse=True)[:10]
    ])

    system = """Du bist ein Senior Intelligence Analyst der Hedge Funds und PE-Firmen berät.
Du analysierst öffentliche Signale und destillierst sie in präzise, umsetzbare Business-Intelligence.
Dein Briefing-Stil: direkt, zahlenbasiert, keine Füllwörter, immer mit konkreter Handlungsempfehlung.
Sprache: Deutsch. Format: strukturiertes Briefing mit Emoji-Sektionen."""

    user_msg = f"""Erstelle das heutige VORSPRUNG Intelligence Briefing basierend auf diesen Signalen:

=== DACH LEGAL INTELLIGENCE ({len(legal)} Signale) ===
{legal_summary or "Keine Legal-Signale heute."}

=== REGRET INTELLIGENCE ({len(regret)} Signale) ===
{regret_summary or "Keine Regret-Signale heute."}

Erstelle ein präzises Briefing mit:
1. 🔴 TOP-3 Aktionspunkte heute (konkret, mit Zeitfenster)
2. ⚡ Decay-Windows: Welche Kaufbereitschafts-Fenster schließen sich gerade?
3. 🧠 Regret-Prognose: Welcher Sektor wird in 6-12 Wochen eine Kaufwelle sehen?
4. 💼 Deal-Intelligence: Welche M&A/Patent-Signale sind today relevant?
5. 📈 Score-Zusammenfassung: Gesamtqualität des heutigen Signal-Sets (0-100)

Max 400 Wörter. Prägnant wie Bloomberg Terminal."""

    return await _claude_analyze(system, user_msg)


# ── Haupt-Scan-Funktion ──────────────────────────────────────────────────────

async def run_full_scan() -> dict:
    """Vollständiger VORSPRUNG-Scan: alle Quellen, AI-Synthesis, Supabase-Store, TG-Delivery."""
    t0 = time.time()
    log.info("VORSPRUNG: Starte vollständigen Intelligence-Scan...")

    # Parallel scrapen
    results = await asyncio.gather(
        scrape_bundesanzeiger("Insolvenz"),
        scrape_bundesanzeiger("Kapitalerhöhung"),
        scrape_euipo_trademarks("", "de", 25),
        scrape_dpma_patents("KI Automatisierung"),
        scrape_all_reddit_regret(),
        return_exceptions=True,
    )

    all_signals = []
    for r in results:
        if isinstance(r, list):
            all_signals.extend(r)
        elif isinstance(r, Exception):
            log.warning(f"Scraper error: {r}")

    log.info(f"VORSPRUNG: {len(all_signals)} Signale gesammelt")

    # In Supabase speichern
    stored = await _supa_insert(all_signals) if all_signals else 0

    # AI-Briefing generieren
    briefing = await generate_intelligence_briefing(all_signals)

    # Telegram-Delivery
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    tg_msg = (
        f"⚡ <b>VORSPRUNG Intelligence Briefing — {today}</b>\n\n"
        f"{briefing}\n\n"
        f"📊 Signale gesammelt: {len(all_signals)} | Gespeichert: {stored}\n"
        f"⏱ Scan-Dauer: {time.time()-t0:.1f}s"
    )
    await _tg(tg_msg)

    return {
        "status": "ok",
        "signals_collected": len(all_signals),
        "signals_stored": stored,
        "briefing": briefing,
        "duration_s": round(time.time() - t0, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "breakdown": {
            "bundesanzeiger_insolvency": len([s for s in all_signals if s["source"] == "bundesanzeiger" and "insolvenz" in str(s.get("signal_data", {})).lower()]),
            "bundesanzeiger_changes": len([s for s in all_signals if s["source"] == "bundesanzeiger" and s["signal_type"] == "company_change"]),
            "euipo_trademarks": len([s for s in all_signals if s["source"] == "euipo"]),
            "dpma_patents": len([s for s in all_signals if s["source"] == "dpma"]),
            "reddit_regret": len([s for s in all_signals if s["signal_type"] == "regret_signal"]),
        }
    }


# ── Status & Dashboard-Data ──────────────────────────────────────────────────

async def get_status() -> dict:
    """Gibt aktuellen Status und die letzten Signale zurück."""
    recent = await _supa_recent(50)
    breakdown = {}
    for s in recent:
        t = s.get("signal_type", "unknown")
        breakdown[t] = breakdown.get(t, 0) + 1

    return {
        "status": "active",
        "name": "VORSPRUNG Intelligence Engine",
        "version": "1.0.0",
        "data_sources": [
            {"name": "Bundesanzeiger", "type": "DACH Legal", "status": "live"},
            {"name": "EUIPO", "type": "EU Trademarks", "status": "live"},
            {"name": "DPMA", "type": "German Patents", "status": "live"},
            {"name": "Reddit", "type": "Regret Intelligence", "status": "live"},
        ],
        "recent_signals": len(recent),
        "signal_breakdown": breakdown,
        "revenue_model": {
            "tier1_api": "€2.000/Monat — Signal-Feed per Kategorie",
            "tier2_reports": "€5.000–15.000/Monat — Weekly Intelligence Reports",
            "tier3_hedge_fund": "€50.000–300.000/Monat — Custom Alpha Signal",
        },
        "target_monthly_day8": "€1.000/Tag (Woche 6–8)",
        "target_monthly_m6": "€10.000/Tag (Monat 6)",
    }


# ── Elite Auto-Poster: LinkedIn + Twitter + Reddit Finance ───────────────────
#
# Ziel: PE-Firmen, Hedge Funds, M&A-Berater auf VORSPRUNG aufmerksam machen
# Kanäle: LinkedIn (Finance-Netzwerk), Twitter #fintwit, Reddit r/quant r/ValueInvesting

LINKEDIN_TOKEN  = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN    = os.getenv("LINKEDIN_PERSON_URN", "")  # urn:li:person:xxx
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_SECRET  = os.getenv("TWITTER_API_SECRET", "")
TWITTER_TOKEN   = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

ELITE_REDDIT_SUBS = [
    "ValueInvesting",
    "quant",
    "algotrading",
    "PrivateEquity",
    "Mergers",
]


async def _generate_elite_post(briefing: str, platform: str, signal_count: int) -> str:
    """Generiert plattformspezifischen Elite-Content für Kundenakquise."""
    system = """Du bist ein erfahrener B2B-Marketer der Intelligence-Produkte an Hedge Funds und PE-Firmen verkauft.
Dein Content ist:
- Direkt und datengetrieben (keine leeren Worte)
- Zeigt echten Mehrwert durch konkrete Signal-Beispiele
- Endet mit einem klaren CTA (DM für Trial / Beta-Zugang)
- Keine übermäßigen Hashtags — maximal 4 relevante
- Kein Spam — echter Business-Mehrwert"""

    if platform == "linkedin":
        prompt = f"""Erstelle einen LinkedIn-Post der PE-Firmen und Hedge Funds auf VORSPRUNG Intelligence aufmerksam macht.

Kontext: VORSPRUNG ist eine neue Intelligence-Plattform die täglich {signal_count} öffentliche Signale sammelt:
- Bundesanzeiger (Insolvenzen, Unternehmensänderungen)
- EUIPO (neue Markenanmeldungen)
- DPMA (Patentanmeldungen)
- Reddit Finance (Regret-Signals als Leading Indicator)

Heutiges Briefing-Highlight: {briefing[:300]}

Format: 3-4 kurze Absätze + CTA. Max 280 Wörter. Professionell, kein Hype."""

    elif platform == "twitter":
        prompt = f"""Erstelle einen Tweet-Thread (3 Tweets) für #fintwit / #quant Community.

VORSPRUNG Intelligence sammelt täglich öffentliche Signale die Kaufwellen vorhersagen.
Heute: {signal_count} Signale. Highlight: {briefing[:150]}

Tweet 1: Hook mit konkreter Zahl/Insight
Tweet 2: Mechanismus erklären (wie funktioniert Regret Intelligence)
Tweet 3: CTA für Beta-Zugang

Format: 3 Tweets, je max 280 Zeichen, nummeriert (1/3, 2/3, 3/3). Englisch."""

    else:  # reddit
        prompt = f"""Erstelle einen Reddit-Post für r/quant oder r/ValueInvesting.

VORSPRUNG Intelligence: System das öffentliche Signale (Bundesanzeiger, EUIPO, DPMA, Reddit)
zu Intelligence für Investoren aggregiert. Heute {signal_count} Signale.

Format: Titel (max 100 Zeichen) + Body (max 300 Wörter). Sachlich, zeige Methodik.
Kein Eigenlob — Fakten und Methode erklären. CTA am Ende für Beta-Zugang."""

    return await _claude_analyze(system, prompt)


async def _post_linkedin(content: str) -> dict:
    """Postet auf LinkedIn via Rudolf's existierendes Access Token."""
    if not LINKEDIN_TOKEN:
        return {"ok": False, "error": "LINKEDIN_ACCESS_TOKEN fehlt"}

    # LinkedIn Person URN aus Token-Info holen falls nicht gesetzt
    urn = LINKEDIN_URN
    if not urn:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.linkedin.com/v2/userinfo",
                    headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        info = await r.json()
                        urn = f"urn:li:person:{info.get('sub', '')}"
        except Exception:
            pass

    if not urn:
        return {"ok": False, "error": "LinkedIn Person URN nicht ermittelbar"}

    post_body = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {LINKEDIN_TOKEN}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=post_body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    return {"ok": True, "id": data.get("id", ""), "platform": "linkedin"}
                text = await r.text()
                return {"ok": False, "error": f"LinkedIn {r.status}: {text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _post_twitter(tweet_text: str) -> dict:
    """Postet Tweet via OAuth 1.0a (Rudolf's @rudibot84 Account)."""
    if not all([TWITTER_API_KEY, TWITTER_SECRET, TWITTER_TOKEN, TWITTER_TOKEN_SECRET]):
        return {"ok": False, "error": "Twitter OAuth Keys fehlen"}
    import hmac
    import hashlib
    import base64
    import urllib.parse
    import secrets as _secrets

    url = "https://api.twitter.com/2/tweets"
    # Twitter only allows first tweet in a thread easily — post first tweet
    first_tweet = tweet_text.split("\n\n")[0][:280] if "\n\n" in tweet_text else tweet_text[:280]

    ts = str(int(time.time()))
    nonce = _secrets.token_hex(16)
    params = {
        "oauth_consumer_key": TWITTER_API_KEY,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": ts,
        "oauth_token": TWITTER_TOKEN,
        "oauth_version": "1.0",
    }
    base_str = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote("&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted(params.items())), safe=""),
    ])
    signing_key = f"{urllib.parse.quote(TWITTER_SECRET, safe='')}&{urllib.parse.quote(TWITTER_TOKEN_SECRET, safe='')}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = sig
    auth_header = "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(str(v), safe="")}"' for k, v in sorted(params.items()))

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                json={"text": first_tweet},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                if r.status in (200, 201):
                    tweet_id = data.get("data", {}).get("id", "")
                    return {"ok": True, "id": tweet_id, "platform": "twitter", "text": first_tweet}
                return {"ok": False, "error": f"Twitter {r.status}: {data}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _reddit_get_token() -> str:
    """
    Reddit OAuth2 Token via Password Grant.
    App muss in reddit.com/prefs/apps als 'Script' App registriert sein.
    Rudolf's App: hqgJAQe6Qiu5s5r1Vqc0Og / User: bullpowersrtkennels
    """
    client_id = os.getenv("REDDIT_CLIENT_ID", "hqgJAQe6Qiu5s5r1Vqc0Og")
    secret    = os.getenv("REDDIT_CLIENT_SECRET", "xsH99P7iCQAPeknbAXe5F9Nd9fV7aA")
    username  = os.getenv("REDDIT_USERNAME", "bullpowersrtkennels")
    password  = os.getenv("REDDIT_PASSWORD", "Upper-Competition505")

    import base64
    creds = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    ua = f"VORSPRUNG:intelligence:v1.0 (by /u/{username})"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "User-Agent": ua,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=f"grant_type=password&username={username}&password={password}",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("access_token", "")
                text = await r.text()
                log.warning(f"Reddit token {r.status}: {text[:100]}")
    except Exception as e:
        log.warning(f"Reddit token error: {e}")
    return ""


async def scrape_reddit_finance_rss(subreddit: str = "investing", limit: int = 20) -> list[dict]:
    """
    Reddit RSS Feed — funktioniert ohne Auth für öffentliche Subreddits.
    Holt die neuesten Posts als Regret/Finance-Signal.
    """
    signals = []
    ua = "VORSPRUNG:intelligence:v1.0 (by /u/bullpowersrtkennels)"
    url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": ua}) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    xml = await r.text()
                    entries = re.findall(
                        r'<entry>.*?<title[^>]*>(?:<!\[CDATA\[)?([^\]<]{5,200})(?:\]\]>)?</title>.*?<author><name>([^<]*)</name></author>.*?</entry>',
                        xml, re.DOTALL
                    )
                    for title, author in entries[:limit]:
                        title = title.strip()
                        if not title or title.lower().startswith("newest"):
                            continue
                        is_regret = any(kw in title.lower() for kw in [
                            "wish", "regret", "should have", "missed", "fomo",
                            "hätte", "bereue", "verpasst", "hätte gekauft"
                        ])
                        signals.append({
                            "signal_type": "regret_signal" if is_regret else "market_signal",
                            "source": f"reddit_r_{subreddit}",
                            "entity_name": title[:100],
                            "signal_data": {
                                "title": title[:200],
                                "author": author.strip(),
                                "subreddit": subreddit,
                                "is_regret": is_regret,
                                "url": f"https://www.reddit.com/r/{subreddit}/",
                            },
                            "intelligence_score": 72 if is_regret else 55,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                else:
                    log.warning(f"Reddit RSS {subreddit}: {r.status}")
    except Exception as e:
        log.warning(f"Reddit RSS error ({subreddit}): {e}")
    return signals


async def reddit_search_oauth(query: str, subreddit: str = "investing", limit: int = 10) -> list[dict]:
    """Reddit OAuth-Search — braucht gültigen Token (Script App)."""
    signals = []
    token = await _reddit_get_token()
    if not token:
        # Fallback: RSS-Feed ohne Auth
        return await scrape_reddit_finance_rss(subreddit, limit)

    ua = "VORSPRUNG:intelligence:v1.0 (by /u/bullpowersrtkennels)"
    url = f"https://oauth.reddit.com/r/{subreddit}/search"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                params={"q": query, "sort": "new", "limit": limit, "restrict_sr": "1"},
                headers={"Authorization": f"Bearer {token}", "User-Agent": ua},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for post in data.get("data", {}).get("children", []):
                        p = post.get("data", {})
                        title = p.get("title", "")
                        if not title:
                            continue
                        score = p.get("score", 0)
                        signals.append({
                            "signal_type": "regret_signal",
                            "source": f"reddit_oauth_r_{subreddit}",
                            "entity_name": query[:60],
                            "signal_data": {
                                "title": title[:200],
                                "score": score,
                                "comments": p.get("num_comments", 0),
                                "query": query,
                                "subreddit": subreddit,
                                "url": f"https://reddit.com{p.get('permalink', '')}",
                            },
                            "intelligence_score": min(100, 50 + min(score // 10, 50)),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                else:
                    log.warning(f"Reddit OAuth search {r.status} — fallback to RSS")
                    return await scrape_reddit_finance_rss(subreddit, limit)
    except Exception as e:
        log.warning(f"Reddit OAuth error: {e}")
    return signals


async def _post_reddit_finance(title: str, body: str, subreddit: str = "ValueInvesting") -> dict:
    """Postet auf Reddit r/ValueInvesting oder r/quant via OAuth."""
    token = await _reddit_get_token()
    if not token:
        return {"ok": False, "error": "Reddit token konnte nicht ermittelt werden (App-Typ prüfen: muss 'Script' sein in reddit.com/prefs/apps)"}

    ua = "VORSPRUNG:intelligence:v1.0 (by /u/bullpowersrtkennels)"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://oauth.reddit.com/api/submit",
                headers={"Authorization": f"Bearer {token}", "User-Agent": ua},
                data={
                    "sr": subreddit,
                    "kind": "self",
                    "title": title[:300],
                    "text": body[:40000],
                    "nsfw": "false",
                    "spoiler": "false",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                if r.status == 200 and not data.get("json", {}).get("errors"):
                    link = data.get("json", {}).get("data", {}).get("url", "")
                    return {"ok": True, "url": link, "platform": f"reddit_r_{subreddit}"}
                errors = data.get("json", {}).get("errors", [])
                return {"ok": False, "error": str(errors)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_promote_vorsprung(briefing: str, signal_count: int) -> dict:
    """
    Postet VORSPRUNG Intelligence auf alle Elite-Kanäle um PE/Hedge Fund Kunden anzuziehen.
    LinkedIn + Twitter #fintwit + Reddit r/ValueInvesting
    """
    results = {}

    # 1. LinkedIn-Post generieren und posten
    li_content = await _generate_elite_post(briefing, "linkedin", signal_count)
    results["linkedin"] = await _post_linkedin(li_content)

    # 2. Twitter Thread generieren und ersten Tweet posten
    tw_content = await _generate_elite_post(briefing, "twitter", signal_count)
    results["twitter"] = await _post_twitter(tw_content)

    # 3. Reddit Post für quant/ValueInvesting Community
    reddit_content = await _generate_elite_post(briefing, "reddit", signal_count)
    # Split title from body (Claude gibt "Titel:\n\nBody:" Format zurück)
    reddit_lines = reddit_content.strip().split("\n")
    reddit_title = reddit_lines[0].replace("Titel:", "").replace("Title:", "").strip()[:100]
    if not reddit_title:
        reddit_title = f"VORSPRUNG Intelligence: {signal_count} public signals analyzed today"
    reddit_body = "\n".join(reddit_lines[1:]).strip()
    results["reddit_quant"] = await _post_reddit_finance(reddit_title, reddit_body, "quant")

    # Telegram-Zusammenfassung der Posting-Ergebnisse
    posted = [k for k, v in results.items() if v.get("ok")]
    failed = [k for k, v in results.items() if not v.get("ok")]
    await _tg(
        f"⚡ <b>VORSPRUNG Auto-Promo gepostet</b>\n\n"
        f"✅ Erfolgreich: {', '.join(posted) or 'keiner'}\n"
        f"❌ Fehler: {', '.join(failed) or 'keiner'}\n\n"
        f"Ziel: PE-Firmen & Hedge Funds erreichen — €3k–300k/Monat Kunden"
    )

    log.info(f"VORSPRUNG Auto-Promo: {len(posted)} erfolgreich, {len(failed)} Fehler")
    return results


# ── Haupt-Scan-Funktion (updated mit Auto-Promote) ──────────────────────────

async def run_full_scan(promote: bool = True) -> dict:
    """Vollständiger VORSPRUNG-Scan: alle Quellen, AI-Synthesis, Supabase-Store, TG-Delivery, Auto-Promote."""
    t0 = time.time()
    log.info("VORSPRUNG: Starte vollständigen Intelligence-Scan...")

    # Parallel scrapen — alle live Quellen
    results = await asyncio.gather(
        scrape_opencorporates_de("insolvenz", 20),       # DE Insolvenzen
        scrape_opencorporates_active("software", 15),    # Neue Tech-Firmen DE
        scrape_opencorporates_de("GmbH", 15),            # Unternehmensänderungen
        scrape_euipo_trademarks("", "de", 25),           # EU-Markenanmeldungen
        scrape_dpma_patents("KI Automatisierung", 20),   # DE Patente
        scrape_all_regret_signals(),                     # HN + Twitter Regret
        return_exceptions=True,
    )

    all_signals = []
    for r in results:
        if isinstance(r, list):
            all_signals.extend(r)
        elif isinstance(r, Exception):
            log.warning(f"Scraper error: {r}")

    log.info(f"VORSPRUNG: {len(all_signals)} Signale gesammelt")

    # In Supabase speichern
    stored = await _supa_insert(all_signals) if all_signals else 0

    # AI-Briefing generieren
    briefing = await generate_intelligence_briefing(all_signals)

    # Telegram-Delivery (Owner)
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    tg_msg = (
        f"⚡ <b>VORSPRUNG Intelligence Briefing — {today}</b>\n\n"
        f"{briefing}\n\n"
        f"📊 Signale: {len(all_signals)} | Gespeichert: {stored}\n"
        f"⏱ {time.time()-t0:.1f}s"
    )
    await _tg(tg_msg)

    # Auto-Promote auf Elite-Kanälen
    promo_results = {}
    if promote and all_signals:
        promo_results = await auto_promote_vorsprung(briefing, len(all_signals))

    return {
        "status": "ok",
        "signals_collected": len(all_signals),
        "signals_stored": stored,
        "briefing": briefing,
        "duration_s": round(time.time() - t0, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "auto_promote": promo_results,
        "breakdown": {
            "opencorporates_insolvency": len([s for s in all_signals if "opencorporates" in s["source"] and "insolvenz" in str(s.get("signal_data", {})).lower()]),
            "opencorporates_new":        len([s for s in all_signals if s["signal_type"] == "new_company"]),
            "euipo_trademarks":          len([s for s in all_signals if s["source"] == "euipo"]),
            "dpma_patents":              len([s for s in all_signals if s["source"] == "dpma"]),
            "hackernews_signals":        len([s for s in all_signals if s["source"] == "hackernews"]),
            "twitter_regret":            len([s for s in all_signals if s["source"] == "twitter_x"]),
        }
    }


# ── Status & Dashboard-Data ──────────────────────────────────────────────────

async def get_status() -> dict:
    """Gibt aktuellen Status und die letzten Signale zurück."""
    recent = await _supa_recent(50)
    breakdown = {}
    for s in recent:
        t = s.get("signal_type", "unknown")
        breakdown[t] = breakdown.get(t, 0) + 1

    return {
        "status": "active",
        "name": "VORSPRUNG Intelligence Engine",
        "version": "1.0.0",
        "data_sources": [
            {"name": "Bundesanzeiger", "type": "DACH Legal", "status": "live"},
            {"name": "EUIPO", "type": "EU Trademarks", "status": "live"},
            {"name": "DPMA", "type": "German Patents", "status": "live"},
            {"name": "Reddit", "type": "Regret Intelligence", "status": "live"},
        ],
        "auto_promote_channels": ["linkedin", "twitter_x", "reddit_quant", "reddit_valueinvesting"],
        "recent_signals": len(recent),
        "signal_breakdown": breakdown,
        "revenue_model": {
            "tier1_api": "€2.000/Monat — Signal-Feed per Kategorie",
            "tier2_reports": "€5.000–15.000/Monat — Weekly Intelligence Reports",
            "tier3_hedge_fund": "€50.000–300.000/Monat — Custom Alpha Signal",
        },
        "target_day8": "€1.000/Tag (Woche 6–8)",
        "target_m6": "€10.000/Tag (Monat 6)",
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    result = asyncio.run(run_full_scan())
    print(json.dumps(result, indent=2, ensure_ascii=False))
