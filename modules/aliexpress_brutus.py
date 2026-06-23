#!/usr/bin/env python3
"""
AliExpress + BRUTUS — Automatisierter Traffic Engine ohne OAuth
==============================================================
Generiert AliExpress Affiliate-Links und bespielt alle Kanäle via BRUTUS.
Kein OAuth nötig — nutzt affiliate Link-Builder direkt.
"""
import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("AliBrutus")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
DS24_LINK      = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")

ALI_TRACKING_ID = os.getenv("ALIEXPRESS_TRACKING_ID", "")
ALI_APP_KEY     = os.getenv("ALIEXPRESS_APP_KEY", "537346")

TRENDING_NICHES = [
    ("Smart Home Steckdose", "smart home steckdose wlan"),
    ("WiFi Smart Plug", "wifi smart plug energy monitor"),
    ("Smart Garden", "smart garden bewässerung automatisch"),
    ("Zigbee Smart Home", "zigbee gateway smart home"),
    ("LED Strip WiFi", "led streifen wifi alexa"),
    ("Tuya Smart Schalter", "tuya smart schalter"),
    ("Smart Thermostat", "smart thermostat wifi heizung"),
    ("KI Smart Speaker", "ai smart speaker home assistant"),
]


def build_ali_link(keyword: str) -> str:
    """Build an AliExpress search affiliate link."""
    import urllib.parse
    q = urllib.parse.quote(keyword)
    base = f"https://www.aliexpress.com/wholesale?SearchText={q}&sortType=total_tranQty_desc"
    if ALI_TRACKING_ID:
        base += f"&aff_platform=default&aff_short_key={ALI_TRACKING_ID}"
    return base


async def _ai(prompt: str) -> str:
    try:
        from modules.ai_client import ai_complete
        r = await ai_complete(prompt, max_tokens=350)
        if r:
            return r
    except Exception:
        pass
    return "🔥 AliExpress Bestseller 2026 — Dropshipping & Reselling Profi-Tipps!"


async def _telegram(text: str) -> bool:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT):
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "Markdown",
                      "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("ok", False)
    except Exception:
        return False


async def run_aliexpress_brutus_cycle() -> dict:
    """Full cycle: pick niche → content → BRUTUS blast."""
    name, keyword = random.choice(TRENDING_NICHES)
    link = build_ali_link(keyword)

    prompt = (
        f"Schreibe einen deutschen Social-Media-Post (max 280 Zeichen) über "
        f"'{name}' von AliExpress für Dropshipping oder Reselling. "
        f"Preise, Qualität, Profit. Emoji. Kein Link einfügen."
    )
    body = await _ai(prompt)

    tg_msg = f"🛍 *AliExpress: {name}*\n\n{body}\n\n👉 [Jetzt ansehen]({link})"
    tg_ok = await _telegram(tg_msg)

    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_r = await run_brutus_swarm(
            niche=f"aliexpress {keyword}",
            affiliate_url=link,
        )
    except Exception as e:
        brutus_r = {"channels_hit": 1 if tg_ok else 0, "content_pieces": 1}

    return {
        "niche": name,
        "link": link,
        "telegram_ok": tg_ok,
        "channels_hit": brutus_r.get("channels_hit", 0),
        "content_pieces": brutus_r.get("content_pieces", 1),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def run_aliexpress_multi_blast(count: int = 3) -> dict:
    """Blast multiple AliExpress niches in parallel."""
    niches = random.sample(TRENDING_NICHES, min(count, len(TRENDING_NICHES)))
    tasks = [run_aliexpress_brutus_cycle() for _ in niches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_ch = sum(r.get("channels_hit", 0) for r in results if isinstance(r, dict))
    return {
        "cycles": len(niches),
        "channels_hit": total_ch,
        "results": [r for r in results if isinstance(r, dict)],
    }


async def run_aliexpress_dropshipping_blast() -> dict:
    """Special: generate DS24 Affiliate + AliExpress dropshipping combo content."""
    prompt = (
        "Schreibe 3 kurze Dropshipping Tipps für AliExpress zu Shopify auf Deutsch. "
        "Max 400 Zeichen. Emoji. Erwähne Automatisierung und AI."
    )
    body = await _ai(prompt)
    tg_msg = (
        f"🤖 *Dropshipping Automation 2026*\n\n{body}\n\n"
        f"🔗 Affiliate: {DS24_LINK}"
    )
    tg_ok = await _telegram(tg_msg)

    try:
        from modules.brutus_traffic_engine import brutus_run
        r = await brutus_run(niche="aliexpress dropshipping shopify automation 2026")
    except Exception as e:
        r = {"channels_hit": 1 if tg_ok else 0, "content_pieces": 1}

    return {
        "ok": tg_ok,
        "channels_hit": r.get("channels_hit", 0),
        "content_pieces": r.get("content_pieces", 1),
    }
