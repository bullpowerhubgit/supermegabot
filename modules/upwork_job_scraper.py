#!/usr/bin/env python3
"""
Upwork Job Scraper — kein API-Key nötig.
Scrapt öffentliche Upwork RSS-Feeds für relevante Jobs und sendet
automatisch Proposal-Vorlagen via Telegram.
"""
import asyncio
import logging
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("UpworkScraper")

TG_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
DATA_DIR  = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SEEN_FILE = DATA_DIR / "upwork_seen_jobs.json"

# Upwork hat öffentliche RSS-Feeds ohne Login:
UPWORK_RSS_FEEDS = [
    "https://www.upwork.com/ab/feed/jobs/rss?q=shopify+automation&sort=recency&paging=0%3B10",
    "https://www.upwork.com/ab/feed/jobs/rss?q=shopify+developer&sort=recency&paging=0%3B10",
    "https://www.upwork.com/ab/feed/jobs/rss?q=python+automation&sort=recency&paging=0%3B10",
    "https://www.upwork.com/ab/feed/jobs/rss?q=ecommerce+automation&sort=recency&paging=0%3B10",
    "https://www.upwork.com/ab/feed/jobs/rss?q=ai+automation+bot&sort=recency&paging=0%3B10",
    "https://www.upwork.com/ab/feed/jobs/rss?q=dropshipping+setup&sort=recency&paging=0%3B10",
]

PROPOSAL_TEMPLATES = [
    """👋 Hallo!

Ich habe deinen Job gesehen und bin sehr interessiert.

**Rudolf Sarkany — Shopify AI Automation Spezialist**
- ✅ 5+ Jahre E-Commerce Erfahrung
- ✅ Shopify + Python + KI Vollautomatisierung
- ✅ Dropshipping, Printify/Printful, DS24 Integration
- ✅ Lieferzeit: 24-48h

Was ich für dich baue: {job_title}

Preis: fair, nach Absprache. Kostenloses 15-Min Briefing?

Rudolf | BullPower Hub | aiitec.online""",

    """Guten Tag,

ich bin Spezialist für Shopify-Automatisierung und KI-Integration.

**Zu deinem Projekt: {job_title}**

Mein Ansatz:
1. Analyse deiner aktuellen Infrastruktur
2. Vollautomatische Lösung mit Python/aiohttp
3. Tests + Dokumentation inklusive
4. Support nach Lieferung

Verfügbarkeit: sofort. Antwortzeit: < 2h.

Rudolf Sarkany | aiitec.online | Shopify Certified""",
]


def _load_seen() -> set:
    try:
        import json
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set):
    import json
    SEEN_FILE.write_text(json.dumps(list(seen)[-500:]))  # Keep last 500


async def _tg(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown",
                      "disable_web_page_preview": True}) as r:
                return (await r.json(content_type=None)).get("ok", False)
    except Exception:
        return False


async def scrape_upwork_jobs(max_jobs: int = 5) -> list[dict]:
    """Fetch jobs from Upwork public RSS feeds."""
    jobs = []
    seen = _load_seen()

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15),
        headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"}
    ) as s:
        for feed_url in UPWORK_RSS_FEEDS:
            try:
                async with s.get(feed_url) as r:
                    if r.status != 200:
                        continue
                    xml = await r.text()

                items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
                for item in items[:3]:
                    title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item)
                    link_m  = re.search(r"<link>(.*?)</link>", item)
                    desc_m  = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item, re.DOTALL)
                    if not title_m or not link_m:
                        continue
                    title = title_m.group(1).strip()
                    link  = link_m.group(1).strip()
                    desc  = re.sub(r"<[^>]+>", "", desc_m.group(1) if desc_m else "")[:300]

                    job_id = re.search(r"_~(\w+)", link)
                    gid = job_id.group(1) if job_id else link[-20:]
                    if gid in seen:
                        continue

                    jobs.append({"title": title, "link": link, "desc": desc, "id": gid})
                    seen.add(gid)

                    if len(jobs) >= max_jobs:
                        break
            except Exception as e:
                log.debug("Feed error %s: %s", feed_url, e)

            if len(jobs) >= max_jobs:
                break

    _save_seen(seen)
    return jobs


async def run_upwork_job_alert(max_jobs: int = 3) -> dict:
    """Scrape new Upwork jobs and alert via Telegram with proposal draft."""
    jobs = await scrape_upwork_jobs(max_jobs)
    if not jobs:
        return {"jobs_found": 0, "alerted": 0, "note": "Keine neuen Jobs (oder RSS blockiert)"}

    alerted = 0
    for job in jobs:
        proposal = random.choice(PROPOSAL_TEMPLATES).format(job_title=job["title"])
        msg = (
            f"💼 *Neuer Upwork Job!*\n\n"
            f"**{job['title'][:80]}**\n\n"
            f"{job['desc'][:200]}\n\n"
            f"🔗 [Job ansehen]({job['link']})\n\n"
            f"---\n📝 *Vorschlag:*\n```{proposal[:400]}```"
        )
        if await _tg(msg):
            alerted += 1
        await asyncio.sleep(1)

    log.info("Upwork alert: %d jobs, %d alerted", len(jobs), alerted)
    return {"jobs_found": len(jobs), "alerted": alerted}


async def run_upwork_proposal_blast() -> dict:
    """Post generic Upwork service promo via BRUTUS."""
    promos = [
        f"🔧 **Shopify Automation Service** | Python + KI | 24h Lieferzeit | Portfolio: aiitec.online — Upwork Top Rated Expert",
        f"💻 **E-Commerce Automatisierung** gesucht? Rudolf Sarkany — Shopify, Dropshipping, AI Bots. Upwork Verified. aiitec.online",
        f"⚡ Automatisiere deinen Shopify Store komplett mit KI. Upwork Freelancer mit 5+ Jahren Erfahrung. Anfragen: aiitec.online",
    ]
    promo = random.choice(promos)
    tg_ok = await _tg(f"👔 *Upwork Service Promo*\n\n{promo}")
    try:
        from modules.brutus_traffic_engine import brutus_run
        r = await brutus_run(niche="upwork freelance shopify automation python developer")
        ch = r.get("channels_hit", 0)
    except Exception:
        ch = 1 if tg_ok else 0
    return {"tg_ok": tg_ok, "channels_hit": ch}
