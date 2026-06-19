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
API_KEY          = os.getenv("TWITTER_API_KEY", "gjYgqqqMwOH5tfaKdxOmOIcIG")
API_SECRET       = os.getenv("TWITTER_API_SECRET", "vND5rZnqbsOqeCQ4GOyt26EFhrf09MCjls9erbmgG7J1ccRXOE")
ACCESS_TOKEN     = os.getenv("TWITTER_ACCESS_TOKEN", "2015131234226102272-Nr8jnMFAKR2l1YP3qFN2XZvHwFiqIl")
ACCESS_SECRET    = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "8bTVNNTgXpxsh43Ch0haNYVvV56JKaAiEf3vuml8YqDfz")
BEARER_TOKEN     = os.getenv("TWITTER_BEARER_TOKEN", "AAAAAAAAAAAAAAAAAAAAAJqK7QEAAAAAnXVEODfbyABWhvU2i5hDM%2BofsTg%3DGSumD9UBcpqtZ8ZZUfnXR2GbIt8GUaW7E0d3WL72vYMPzZLW31")
CLIENT_ID        = os.getenv("TWITTER_CLIENT_ID", "SGh5aXVSejJUTE00dzJXM3RXM0s6MTpjaQ")
CLIENT_SECRET    = os.getenv("TWITTER_CLIENT_SECRET", "5ZEYC5Y1jo2sVZCY4htJVLkmSqNhg87Cn20NmCAvrFo5i-sgmW")

ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "twitter"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

TWITTER_API_V2 = "https://api.twitter.com/2"

# ── Content-Kategorien (rotierend) ───────────────────────────────────────────
TWEET_TEMPLATES = [
    # Conversion/Offer
    "🔥 Shopify auf Autopilot: KI findet Bestseller, optimiert Preise, postet überall.\n\nKein manueller Aufwand mehr. Ab €49/Monat:\n👉 https://bullpower-hub-portal.netlify.app\n\n#ShopifyAutomation #KI #Ecommerce",
    "💰 +187% Umsatz in 90 Tagen — vollautomatisch.\n\nKeine Werbung. KI-Automatisierung macht's möglich:\n✅ Produkte finden\n✅ Emails senden\n✅ Social Media posten\n\nhttps://bullpower-hub-portal.netlify.app #BullPowerHub",
    "⚡ Shopify Brutal Tuning: +47% Conversion Rate garantiert.\n\nA/B-Tests, Page Speed & CRO — alles automatisch.\n👉 https://shopify-brutal-tuning.vercel.app\n\n#Shopify #CRO #Ecommerce",
    # Educational
    "📊 Warum 90% der Shopify-Stores nie profitabel werden:\n\n❌ Manuell Produkte suchen\n❌ Keine Email-Automation\n❌ Kein A/B-Testing\n\n✅ Lösung: https://bullpower-hub-portal.netlify.app\n\n#Shopify #OnlineShop",
    "🤖 KI im E-Commerce 2026:\n\n→ Produktrecherche: 2h → 2min\n→ Produktbeschreibungen: 20min → sofort\n→ Social Media: täglich → automatisch\n→ Umsatz: +187%\n\nhttps://bullpower-hub-portal.netlify.app #AI #KI",
    # Social Proof
    "⭐⭐⭐⭐⭐ Kundenstimme:\n\n\"In 6 Wochen meinen Shopify-Umsatz verdoppelt. Die KI findet Produkte die ich nie gefunden hätte.\"\n— Markus K., München\n\n🔗 https://bullpower-hub-portal.netlify.app",
    "📈 Zahlen die für sich sprechen:\n\n• 187% mehr Umsatz (Ø 90 Tage)\n• +47% Conversion Rate\n• 40h/Woche gespart\n• 9 Social-Kanäle gleichzeitig\n\nhttps://bullpower-hub-portal.netlify.app\n#ShopifyAutomation",
    # FOMO/Urgency
    "⏰ Während du manuell Produkte suchst, laufen automatisierte Stores auf Hochtouren.\n\nDer Unterschied: Ein Tool. Ab €49/Monat.\n\nhttps://bullpower-hub-portal.netlify.app\n#Shopify #Automation",
    # Tips
    "💡 Shopify Tipp: Abandoned Cart Emails generieren 15-20% des Umsatzes zurück.\n\nAber 78% der Shops haben keine automatischen Cart-Recovery-Emails.\n\nFix in 5 Min: https://bullpower-hub-portal.netlify.app\n#Shopify #EmailMarketing",
    "🎯 3 Dinge die sofort deinen Shopify-Umsatz erhöhen:\n\n1. Abandoned Cart Email (automatisch)\n2. Post-Purchase Upsell (KI-gesteuert)\n3. Social Proof auf Produktseiten\n\nAlles automatisch: https://bullpower-hub-portal.netlify.app",
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
                async with aiohttp.ClientSession() as sess:
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
            async with aiohttp.ClientSession() as session:
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

    # Weg 3: Direkte Twitter API v2
    try:
        url = f"{TWITTER_API_V2}/tweets"
        payload = {"text": text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        auth_header = _oauth1_header("POST", url)

        async with aiohttp.ClientSession() as session:
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
    """Generiert KI-Tweet für das gegebene Thema."""
    if not ANTHROPIC_KEY:
        import random
        return random.choice(TWEET_TEMPLATES)

    import random
    hashtags = random.choice(HASHTAG_SETS)
    prompt = f"""Schreibe einen Tweet auf DEUTSCH für das Thema: "{topic}"

Regeln:
- Max 250 Zeichen (Platz für URL)
- Starte mit starkem Hook (Emoji + Zahl oder Frage)
- Konkreter Mehrwert oder Statistik
- Endet mit Link: https://bullpower-hub-portal.netlify.app
- Füge diese Hashtags hinzu: {hashtags}
- Ton: direkt, professionell, Mehrwert-orientiert
- NUR den Tweet-Text ausgeben, keine Erklärungen"""

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json()
                return data["content"][0]["text"].strip()
    except Exception as e:
        log.error("AI tweet generation failed: %s", e)
        import random
        return random.choice(TWEET_TEMPLATES)


async def generate_shopify_product_tweet() -> Optional[str]:
    """Tweet über ein aktuelles Shopify-Produkt aus dem Store."""
    try:
        import aiohttp, random
        async with aiohttp.ClientSession() as session:
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
                tweet = (f"🛍️ NEU im Store: {title[:60]}\n\n"
                         f"💰 Preis: €{price}\n"
                         f"🤖 KI-kuratiert & automatisch importiert\n\n"
                         f"Shop: https://{SHOPIFY_DOMAIN}\n"
                         f"Automation: https://bullpower-hub-portal.netlify.app\n\n"
                         f"#Shopify #Dropshipping #OnlineShop")
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
    """Postet einen SEO-optimierten Thread (3-5 Tweets)."""
    if not ANTHROPIC_KEY:
        return {"skipped": "no API key"}

    prompt = """Erstelle einen Twitter-Thread auf DEUTSCH (3 Tweets) zum Thema:
"Wie man Shopify 2026 vollautomatisiert mit KI"

Format:
TWEET 1: Hook (max 250 Zeichen)
TWEET 2: Details/Tipps (max 250 Zeichen)
TWEET 3: CTA + Link zu https://bullpower-hub-portal.netlify.app (max 250 Zeichen)

Verwende Emojis. Schreibe NUR die 3 Tweets, getrennt durch "---"."""

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 600,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as r:
                data = await r.json()
                content = data["content"][0]["text"]
                tweets = [t.strip() for t in content.split("---") if t.strip()]
                return await post_thread(tweets[:3])
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass
