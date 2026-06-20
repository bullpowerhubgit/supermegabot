"""
Fiverr SEO Promoter — kein offizielles API nötig.
Postet Fiverr-Gig-Links via KI-generiertem Content auf Telegram, Klaviyo, LinkedIn.
Läuft alle 6h automatisch via Scheduler.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger("FiverrPromoter")

ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
KLAVIYO_KEY    = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST   = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
LINKEDIN_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN   = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")

# Gig-URLs aus ENV überschreiben; Fallback auf Standard-Gigs
_env_gigs = [u.strip() for u in os.getenv("FIVERR_GIG_URLS", "").split(",") if u.strip()]

DEFAULT_GIGS = [
    {"url": "https://www.fiverr.com/bullpowerhub/shopify-ki-automation",
     "title": "Shopify KI-Vollautomation einrichten", "price": 97},
    {"url": "https://www.fiverr.com/bullpowerhub/digistore24-funnel",
     "title": "Digistore24 Funnel + Email-Sequenz aufbauen", "price": 67},
    {"url": "https://www.fiverr.com/bullpowerhub/supermegabot-setup",
     "title": "SuperMegaBot Installation & Einrichtung", "price": 149},
]

for _u in _env_gigs:
    DEFAULT_GIGS.append({"url": _u, "title": "Premium Automation Service", "price": 97})


async def _generate_promo(gig: dict) -> str:
    if not ANTHROPIC_KEY:
        return (f"🎯 {gig['title']}\n"
                f"✅ Professionell | ⚡ Schnell | 💯 Garantiert\n"
                f"Ab €{gig['price']} auf Fiverr: {gig['url']}")
    try:
        import aiohttp
        prompt = (
            f"Schreibe einen knappen, viralen deutschen Social-Media-Post (max 3 Sätze) "
            f"für diesen Fiverr-Service: '{gig['title']}' (ab €{gig['price']}). "
            f"Nutzen betonen, Ende: {gig['url']} #Fiverr #Automatisierung"
        )
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 220,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return (d.get("content") or [{"text": ""}])[0].get("text", "").strip()
    except Exception as e:
        log.warning("Promo gen error: %s", e)
        return f"🎯 {gig['title']} — ab €{gig['price']}\n{gig['url']}"


async def _post_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4096]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
        return d.get("ok", False)
    except Exception:
        return False


async def _post_linkedin(text: str) -> bool:
    if not LINKEDIN_TOKEN:
        return False
    try:
        import aiohttp
        urn = LINKEDIN_URN if LINKEDIN_URN.startswith("urn:li:") else f"urn:li:person:{LINKEDIN_URN}"
        payload = {
            "author": urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
            }},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}",
                         "Content-Type": "application/json",
                         "X-Restli-Protocol-Version": "2.0.0"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return bool(d.get("id"))
    except Exception:
        return False


async def run_fiverr_promotion_cycle() -> dict:
    gigs = DEFAULT_GIGS[:5]
    results = []
    for gig in gigs:
        text = await _generate_promo(gig)
        tg   = await _post_telegram(text)
        li   = await _post_linkedin(text)
        results.append({"gig": gig["title"][:50], "telegram": tg, "linkedin": li})
        log.info("Fiverr promo: %s | TG=%s LI=%s", gig["title"][:40], tg, li)
        await asyncio.sleep(3)

    return {
        "ok": True,
        "gigs_promoted": len(results),
        "results": results,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
