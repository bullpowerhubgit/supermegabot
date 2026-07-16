#!/usr/bin/env python3
"""
Twitter/X Auto-Poster — Vollautomatisches Twitter Marketing
============================================================
Postet täglich KI-generierten Content auf @AIITEC.
Integration: Shopify-Produkte, SEO-Artikel, Testimonials, Angebote.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("TwitterAutoPoster")

# ── Credentials ──────────────────────────────────────────────────────────────
API_KEY          = os.getenv("TWITTER_API_KEY", "")
API_SECRET       = os.getenv("TWITTER_API_SECRET", "")
ACCESS_TOKEN     = os.getenv("TWITTER_ACCESS_TOKEN", "")
ACCESS_SECRET    = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", os.getenv("TWITTER_ACCESS_SECRET", ""))
BEARER_TOKEN     = os.getenv("TWITTER_BEARER_TOKEN", "")
CLIENT_ID        = os.getenv("TWITTER_CLIENT_ID", "")
CLIENT_SECRET_V2 = os.getenv("TWITTER_CLIENT_SECRET", "")

ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHAT    = _TG_CHANNEL or ""
SHOPIFY_DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN    = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "twitter"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

TWITTER_API_V2 = "https://api.twitter.com/2"

# ── Content-Kategorien (rotierend) ───────────────────────────────────────────
TWEET_TEMPLATES = [
    # Conversion/Offer
    "🔥 2003 Top-Produkte. Günstige Preise. Schnelle Lieferung.\n\nDein Online-Shop für Smarthome, Fitness, Outdoor & mehr:\n👉 https://ineedit.com.co\n\n#OnlineShop #Smarthome #Gadgets",
    "💰 Technik-Gadgets, Fitness-Tools, Outdoor-Equipment — alles auf einen Blick!\n\n✅ Riesige Auswahl\n✅ Top Preise\n✅ Direkte Lieferung\n\nhttps://ineedit.com.co #Ecommerce #Deutschland",
    "⚡ Smarte Produkte für ein smarteres Leben.\n\nVon Smart Home bis Outdoor-Abenteuer — alles bei uns:\n👉 https://ineedit.com.co\n\n#SmartHome #Fitness #Outdoor #Gadgets",
    # Educational
    "📊 Warum smarte Gadgets deinen Alltag revolutionieren:\n\n✅ Mehr Effizienz\n✅ Weniger Aufwand\n✅ Mehr Lebensqualität\n\n🛒 Jetzt entdecken: https://ineedit.com.co\n\n#Smarthome #LifeHacks",
    "🤖 Smart Home 2026: Diese Geräte sind ein Muss!\n\n→ Intelligente Steckdosen\n→ Smart Lampen & Beamer\n→ Fitness Tracker & Wearables\n→ Outdoor Gadgets\n\nAlle bei: https://ineedit.com.co #SmartHome",
    # Product spotlights
    "⭐ Top-Seller: Smarte WLAN-Steckdose mit Energiemessung!\n\nSteuere alles per App — spar Strom, spare Kosten.\n\n🔗 https://ineedit.com.co\n\n#SmartHome #Energie #Gadgets",
    "📈 Outdoor-Saison ist da!\n\n🏕️ Camping-Sets\n🎒 Trekking-Rucksäcke\n☀️ Solar-Gadgets\n🌿 Garten-Tools\n\nAlles in einem Shop: https://ineedit.com.co\n#Outdoor #Camping #Sommer",
    # FOMO/Urgency
    "⏰ Die beliebtesten Produkte fliegen raus!\n\nJetzt zuschlagen — top Preise auf:\n• Smarthome-Geräte\n• Fitness Equipment\n• Outdoor-Zubehör\n\nhttps://ineedit.com.co\n#Sale #Angebot",
    # Tips
    "💡 Fitness-Tipp: Ein guter Tracker macht den Unterschied!\n\nSleep-Analyse, Herzrate, Kalorientracking — alles in einer Uhr.\n\n🛒 Jetzt kaufen: https://ineedit.com.co\n#Fitness #Smartwatch #Gesundheit",
    "🎯 3 Must-Have Gadgets für 2026:\n\n1. Smart Home Hub für zentrale Steuerung\n2. Fitness Tracker mit Schlafanalyse\n3. Solar-Powerbank für unterwegs\n\nAlle verfügbar bei: https://ineedit.com.co",
]

HASHTAG_SETS = [
    "#ShopifyAutomation #KI #Ecommerce #OnlineMarketing",
    "#Dropshipping #Shopify #PassivesEinkommen #KITools",
    "#EcommerceGrowth #Shopify #Marketing #Automation",
    "#OnlineShop #Digitalisierung #KI #AutomatischesEinkommen",
    "#ShopifyTipps #Conversion #EmailMarketing #Deutschland",
]


# ─────────────────────────────────────────────────────────────────────────────
# OAuth 1.0a Signierung für Twitter API v1.1
# ─────────────────────────────────────────────────────────────────────────────

def _oauth1_header(method: str, url: str, params: dict = None) -> str:
    """Generiert OAuth 1.0a Authorization Header."""
    oauth_params = {
        "oauth_consumer_key": API_KEY,
        "oauth_nonce": hashlib.md5(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": ACCESS_TOKEN,
        "oauth_version": "1.0",
    }

    all_params = {**oauth_params, **(params or {})}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base_string = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = f"{urllib.parse.quote(API_SECRET, safe='')}&{urllib.parse.quote(ACCESS_SECRET, safe='')}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature
    header_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


# ─────────────────────────────────────────────────────────────────────────────
# Tweet senden via Twitter API v2
# ─────────────────────────────────────────────────────────────────────────────

MAKE_WEBHOOK_URL  = os.getenv("TWITTER_MAKE_WEBHOOK", "")
TWITTER_USERNAME  = os.getenv("TWITTER_USERNAME", "AIITEC")
TWITTER_EMAIL     = os.getenv("TWITTER_EMAIL", "aiitecbuuss@gmail.com")
TWITTER_PASSWORD  = os.getenv("TWITTER_PASSWORD", "")

TWIKIT_COOKIES_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "twikit_cookies.json"
_twikit_client = None


async def _get_twikit_client():
    """Twikit Client mit Login (inoffizielle Twitter Web API — kein bezahlter Plan nötig)."""
    global _twikit_client
    if _twikit_client:
        return _twikit_client
    if not TWITTER_PASSWORD:
        return None
    try:
        from twikit import Client as TwikitClient
        c = TwikitClient("de-DE")
        if TWIKIT_COOKIES_FILE.exists():
            c.load_cookies(str(TWIKIT_COOKIES_FILE))
            log.info("twikit: cookies geladen")
        else:
            await c.login(
                auth_info_1=TWITTER_USERNAME,
                auth_info_2=TWITTER_EMAIL,
                password=TWITTER_PASSWORD,
            )
            c.save_cookies(str(TWIKIT_COOKIES_FILE))
            log.info("twikit: login erfolgreich, cookies gespeichert")
        _twikit_client = c
        return c
    except Exception as e:
        log.error("twikit login fehler: %s", e)
        return None


async def post_tweet(text: str, reply_to_id: Optional[str] = None) -> dict:
    """Sendet Tweet: 1) twikit (web, kostenlos) → 2) Make.com Webhook → 3) API v2."""
    import aiohttp
    try:
        from modules.post_guardian import validate_post as _gcheck
        ok, errs = _gcheck(text, platform="twitter")
        if not ok:
            log.warning("Tweet blockiert: %s | Preview: %s", errs, text[:80])
            return {"ok": False, "blocked": True, "errors": errs}
    except Exception as _e:
        log.debug("PostGuardian nicht verfügbar: %s", _e)
    text = text[:280]

    # Weg 1: twikit (inoffizielle Web-API, KEIN bezahlter Plan nötig)
    client = await _get_twikit_client()
    if client:
        try:
            tweet = await client.create_tweet(text=text, reply_to=reply_to_id)
            tweet_id = str(tweet.id)
            log.info("twikit tweet gesendet: %s", tweet_id)
            # Telegram Notification
            if TELEGRAM_TOKEN and TELEGRAM_CHAT:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sess:
                    await sess.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={"chat_id": TELEGRAM_CHAT, "text": f"🐦 Tweet live!\nhttps://twitter.com/{TWITTER_USERNAME}/status/{tweet_id}\n\n{text[:100]}..."},
                    )
            return {"ok": True, "id": tweet_id, "via": "twikit", "url": f"https://twitter.com/{TWITTER_USERNAME}/status/{tweet_id}"}
        except Exception as e:
            log.warning("twikit fehler: %s — versuche Fallback", e)
            _twikit_client = None  # Reset für nächsten Versuch
            TWIKIT_COOKIES_FILE.unlink(missing_ok=True)

    # Weg 2: Make.com Webhook (falls konfiguriert)
    if MAKE_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    MAKE_WEBHOOK_URL,
                    json={"text": text, "reply_to": reply_to_id},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status in (200, 202, 204):
                        log.info("Tweet via Make.com Webhook gesendet")
                        return {"ok": True, "via": "make_webhook", "text": text[:50]}
                    log.warning("Make webhook status %d", r.status)
        except Exception as e:
            log.warning("Make webhook error: %s", e)

    # Weg 3: Direkte Twitter API v2 (nur wenn echte Access Tokens vorhanden)
    _valid_token = ACCESS_TOKEN and not ACCESS_TOKEN.startswith("NEEDS_")
    if not _valid_token:
        log.info("Kein gültiges Access Token — OAuth1 übersprungen")
        return {"ok": False, "error": "no_valid_access_token", "detail": "Bitte Access Token in Railway setzen"}
    try:
        url = f"{TWITTER_API_V2}/tweets"
        payload = {"text": text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        auth_header = _oauth1_header("POST", url)

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(
                url,
                json=payload,
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                if r.status == 201:
                    tweet_id = data.get("data", {}).get("id", "?")
                    log.info("Tweet posted via API: %s", tweet_id)
                    return {"ok": True, "id": tweet_id}
                log.error("Tweet API failed: %d %s", r.status, data)
                return {"ok": False, "status": r.status, "detail": data}
    except Exception as e:
        log.error("Tweet exception: %s", e)
        return {"ok": False, "error": str(e)}


async def post_thread(tweets: list[str]) -> dict:
    """Postet einen Twitter-Thread (Antwort-Kette)."""
    results = []
    last_id = None
    for tweet in tweets:
        result = await post_tweet(tweet, reply_to_id=last_id)
        if result.get("ok"):
            last_id = result["id"]
            results.append(result)
        await asyncio.sleep(2)  # Rate limit respect
    return {"thread_length": len(results), "tweets": results}


# ─────────────────────────────────────────────────────────────────────────────
# KI-generierte Tweets
# ─────────────────────────────────────────────────────────────────────────────

async def generate_ai_tweet(topic: str = "shopify automation") -> Optional[str]:
    """Generiert KI-Tweet für das gegebene Thema via Fallback-Chain."""
    import random
    hashtags = random.choice(HASHTAG_SETS)
    prompt = f"""Schreibe einen Tweet auf DEUTSCH für das Thema: "{topic}"

Regeln:
- Max 250 Zeichen (Platz für URL)
- Starte mit starkem Hook (Emoji + Zahl oder Frage)
- Konkreter Mehrwert oder Statistik
- Endet mit Link: https://ineedit.com.co
- Füge diese Hashtags hinzu: {hashtags}
- Ton: direkt, professionell, Mehrwert-orientiert
- NUR den Tweet-Text ausgeben, keine Erklärungen"""

    try:
        from modules.ai_client import ai_complete
        result = await ai_complete(prompt, max_tokens=300)
        return result.strip() if result else random.choice(TWEET_TEMPLATES)
    except Exception as e:
        log.error("AI tweet generation failed: %s", e)
        return random.choice(TWEET_TEMPLATES)


async def generate_shopify_product_tweet() -> Optional[str]:
    """Tweet über ein aktuelles Shopify-Produkt aus dem Store."""
    try:
        import aiohttp, random
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/2024-10/products.json?limit=10&status=active",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                products = data.get("products", [])
                if not products:
                    return None
                product = random.choice(products)
                title = product.get("title", "Produkt")
                price = product.get("variants", [{}])[0].get("price", "?")
                store_url = os.getenv("PUBLIC_SHOP_URL", os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co"))
                tweet = (f"🛍️ NEU im Store: {title[:60]}\n\n"
                         f"💰 Preis: €{price}\n"
                         f"✅ Günstige Preise · Schnelle Lieferung\n\n"
                         f"👉 {store_url}\n\n"
                         f"#OnlineShop #Gadgets #Smarthome")
                return tweet[:280]
    except Exception as e:
        log.debug("Product tweet failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Haupt-Post-Funktionen
# ─────────────────────────────────────────────────────────────────────────────

TOPICS = [
    "shopify automation 2026",
    "dropshipping KI-Tools",
    "passives einkommen online",
    "email marketing automation",
    "conversion rate optimierung shopify",
    "digistore24 affiliate automatisch",
    "social media autopilot",
    "shopify produkte automatisch finden",
]

async def post_daily_tweets(count: int = 3) -> dict:
    """
    Postet täglich mehrere Tweets zu verschiedenen Themen.
    Rotiert durch Topics für maximale Keyword-Abdeckung.
    """
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("twitter_autoposter: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    import random
    posted = []
    failed = []

    # Tweet 1: KI-generiert zu Zufalls-Topic
    topic = random.choice(TOPICS)
    tweet_text = await generate_ai_tweet(topic)
    if tweet_text:
        result = await post_tweet(tweet_text)
        if result.get("ok"):
            posted.append({"type": "ai_topic", "id": result["id"]})
        else:
            failed.append({"type": "ai_topic", "error": result})
        await asyncio.sleep(5)

    # Tweet 2: Template aus Rotation
    if count >= 2:
        # Verhindere Duplikate via Index-File
        idx_file = DATA_DIR / "tweet_template_idx.txt"
        idx = int(idx_file.read_text().strip()) if idx_file.exists() else 0
        tweet_text = TWEET_TEMPLATES[idx % len(TWEET_TEMPLATES)]
        idx_file.write_text(str(idx + 1))

        result = await post_tweet(tweet_text)
        if result.get("ok"):
            posted.append({"type": "template", "id": result["id"]})
        else:
            failed.append({"type": "template", "error": result})
        await asyncio.sleep(5)

    # Tweet 3: Shopify-Produkt (wenn konfiguriert)
    if count >= 3 and SHOPIFY_DOMAIN and SHOPIFY_TOKEN:
        product_tweet = await generate_shopify_product_tweet()
        if product_tweet:
            result = await post_tweet(product_tweet)
            if result.get("ok"):
                posted.append({"type": "product", "id": result["id"]})
            else:
                failed.append({"type": "product", "error": result})

    summary = {"posted": len(posted), "failed": len(failed), "tweets": posted}
    log.info("Twitter daily: %d posted, %d failed", len(posted), len(failed))

    # Telegram-Notification
    await _telegram(
        f"🐦 Twitter Auto-Post abgeschlossen!\n"
        f"✅ {len(posted)} Tweets gepostet\n"
        f"❌ {len(failed)} Fehler\n"
        f"Account: @AIITEC (2019056604868456448)"
    )
    return summary


async def post_seo_thread() -> dict:
    """Postet einen SEO-optimierten Thread (3-5 Tweets) via AI Fallback-Chain."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("twitter_autoposter seo_thread: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    prompt = """Erstelle einen Twitter-Thread auf DEUTSCH (3 Tweets) zum Thema:
"Wie man Shopify 2026 vollautomatisiert mit KI"

Format:
TWEET 1: Hook (max 250 Zeichen)
TWEET 2: Details/Tipps (max 250 Zeichen)
TWEET 3: CTA + Link zu https://ineedit.com.co (max 250 Zeichen)

Verwende Emojis. Schreibe NUR die 3 Tweets, getrennt durch "---"."""

    try:
        from modules.ai_client import ai_complete
        content = await ai_complete(prompt, max_tokens=600)
        if not content:
            return {"error": "no AI response"}
        tweets = [t.strip() for t in content.split("---") if t.strip()]
        return await post_thread(tweets[:3])
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

async def run_with_brutus_traffic(topic: str = "Shopify Automation 2026") -> dict:
    """Post AI-generated Tweet then fire BRUTUS traffic swarm. Skips gracefully if no credentials."""
    if not ACCESS_SECRET:
        log.info("TWITTER_ACCESS_TOKEN_SECRET not set — Twitter skipped gracefully")
        return {"ok": False, "skipped": True, "reason": "TWITTER_ACCESS_SECRET not set"}

    tweet_text = await generate_ai_tweet(topic)
    tweet_result = {}
    if tweet_text:
        tweet_result = await post_tweet(tweet_text)

    brutus_result = {}
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        brutus_result = await run_brutus_swarm(
            niche=topic,
            affiliate_url=os.getenv("DS24_AFFILIATE_LINK",
                                    os.getenv("DS24_AFFILIATE_LINK", "")),
        )
    except Exception as e:
        brutus_result = {"error": str(e)}

    return {"twitter": tweet_result, "brutus": brutus_result}


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as _e:
        log.debug("suppressed: %s", _e)
