#!/usr/bin/env python3
"""
eBay + BRUTUS — Automatisierter eBay Affiliate Traffic Engine
============================================================
Sucht Trending-Produkte, generiert Content, postet überall via BRUTUS.
Kein OAuth nötig — funktioniert mit eBay Partner Network Affiliate Links.
"""
import asyncio
import logging
import os
import json
import aiohttp
from datetime import datetime, timezone

log = logging.getLogger("EbayBrutus")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
EBAY_CAMPAIGN  = os.getenv("EBAY_CAMPAIGN_ID", "")

EBAY_DE_SEARCH = "https://www.ebay.de/sch/i.html?_nkw={query}&_sop=12"  # sorted by newly listed

TRENDING_NICHES = [
    "Shopify automation tool",
    "E-Commerce software",
    "Dropshipping tool",
    "Print on demand",
    "affiliate marketing kurs",
    "online geld verdienen",
    "passive income tool",
]


def build_ebay_link(query: str, campaign_id: str = "") -> str:
    """Build eBay search affiliate link."""
    import urllib.parse
    encoded = urllib.parse.quote(query)
    base = f"https://www.ebay.de/sch/i.html?_nkw={encoded}&_sop=12"
    if campaign_id:
        base += f"&mkcid=1&mkrid=707-53477-19255-0&siteid=77&campid={campaign_id}&mkevt=1"
    return base


async def _ai(prompt: str) -> str:
    """AI content via central fallback chain."""
    try:
        from modules.ai_client import ai_complete
        result = await ai_complete(prompt, max_tokens=400)
        if result:
            return result
    except Exception:
        pass
    # Fallback template
    return f"Top eBay Deals: E-Commerce & Automation Tools im Angebot! Spare jetzt und starte durch."


async def _telegram(text: str) -> bool:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT):
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("ok", False)
    except Exception:
        return False


async def _brutus_blast(keyword: str, content: str, link: str) -> dict:
    """Use BRUTUS to amplify eBay affiliate content."""
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        r = await run_brutus_swarm(niche=f"ebay {keyword}", affiliate_url=link)
        return r
    except Exception as e:
        # Fallback: direct Telegram post
        ok = await _telegram(content[:4096])
        return {"channels_hit": 1 if ok else 0, "content_pieces": 1}


async def run_ebay_brutus_cycle() -> dict:
    """Full cycle: pick niche → generate content → blast via BRUTUS."""
    import random
    niche = random.choice(TRENDING_NICHES)
    link  = build_ebay_link(niche, EBAY_CAMPAIGN)

    prompt = (
        f"Schreibe einen kurzen, überzeugenden deutschen Social-Media-Post (max 280 Zeichen) "
        f"über '{niche}' auf eBay. Erwähne Angebote, Rabatte, Qualität. "
        f"Mache neugierig und zum Klicken auffordern. Emoji nutzen. Kein Hashtag nötig."
    )
    content = await _ai(prompt)

    tg_msg = (
        f"🛒 *eBay Deal — {niche}*\n\n"
        f"{content}\n\n"
        f"👉 [Jetzt ansehen]({link})"
    )

    tg_ok = await _telegram(tg_msg)
    brutus_r = await _brutus_blast(niche, tg_msg, link)

    result = {
        "niche": niche,
        "link": link,
        "telegram_ok": tg_ok,
        "channels_hit": brutus_r.get("channels_hit", 0),
        "content_pieces": brutus_r.get("content_pieces", 1),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    log.info("eBay BRUTUS cycle done: %s", result)
    return result


async def run_ebay_multi_blast(count: int = 3) -> dict:
    """Run multiple eBay niches in parallel for max reach."""
    import random
    niches = random.sample(TRENDING_NICHES, min(count, len(TRENDING_NICHES)))
    tasks  = [run_ebay_brutus_cycle() for _ in niches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_channels = sum(r.get("channels_hit", 0) for r in results if isinstance(r, dict))
    return {
        "cycles": len(niches),
        "channels_hit": total_channels,
        "results": [r for r in results if isinstance(r, dict)],
    }
