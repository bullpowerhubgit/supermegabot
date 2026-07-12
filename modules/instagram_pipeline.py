#!/usr/bin/env python3
"""
Instagram + Facebook Pipeline
==============================
Postet automatisch auf:
  - Facebook AIITEC Page (1016738738178786)
  - Instagram @aaiitecc (17841478315197796)
Alle 3h via Scheduler. Generiert AI-Content + holt Shopify-Produktbild.
Token: FACEBOOK_PAGE_TOKEN_AIITEC (gesetzt nach OAuth-Klick)
"""
from __future__ import annotations
import asyncio, logging, os, random
from datetime import datetime

import aiohttp

log = logging.getLogger("InstagramPipeline")

FB_BASE        = "https://graph.facebook.com/v19.0"
PAGE_ID        = os.getenv("FACEBOOK_PAGE_ID_AIITEC", "1016738738178786")
IG_USER_ID     = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")     # system alerts only
TG_CHANNEL     = os.getenv("TELEGRAM_CHANNEL_ID", "")  # marketing posts → public channel

STORE_URL      = "https://ineedit.com.co"
DS24_LINK      = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")

_IG_STATE_FILE = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "social")) / "ig_last_posted.json"


def _ig_posted_today() -> bool:
    """Returns True if Instagram was already posted to today (UTC)."""
    import json
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if _IG_STATE_FILE.exists():
            data = json.loads(_IG_STATE_FILE.read_text())
            return data.get("last_date") == today
    except Exception:
        pass
    return False


def _ig_mark_posted() -> None:
    import json
    _IG_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IG_STATE_FILE.write_text(json.dumps({"last_date": datetime.now().strftime("%Y-%m-%d")}))

CONTENT_POOL = [
    ("🔥 KI-Business auf Autopilot!", "Stell dir vor: dein Online-Business läuft 24/7 — ohne dass du dabei sein musst. Mit KI-Automatisierung wird das Realität. Produkte, Marketing, Emails — alles automatisch. 💡 Link in Bio!"),
    ("💰 Passives Einkommen 2026", "Mehr als 500 Unternehmer nutzen bereits KI-Tools um monatlich 4-stellige Einnahmen zu generieren — vollautomatisch. Starte noch heute! 🚀"),
    ("🛍️ Shopify ohne manuellen Aufwand", "Trending-Produkte werden automatisch importiert, Preise optimiert, Beschreibungen mit KI geschrieben. Dein Shop verdient Geld während du schläfst. ✅"),
    ("⚡ Der schnellste Weg zum Online-Business", "Schritt 1: KI-Tool einrichten (1x)\nSchritt 2: Alles läuft automatisch\nSchritt 3: Einnahmen checken 😎\nSo einfach kann es sein!"),
    ("📈 +187% Umsatz in 90 Tagen", "Das ist kein Märchen — das sind echte Ergebnisse mit KI-E-Commerce-Automatisierung. Willst du wissen wie? Kommentiere 'INFO' oder klick auf Link in Bio!"),
    ("🤖 KI macht deinen Shop profitabel", "Amazon-Bestseller erkennen ✅\nPreise automatisch optimieren ✅\nEmails automatisch senden ✅\nSocial Media automatisch bespielen ✅\nDu: Ergebnisse genießen 😊"),
    ("💡 Geheimtipp für Online-Seller", "Die erfolgreichsten Shopify-Stores nutzen KI für alles — Produktrecherche, Texte, Marketing. Anfänger machen das manuell und verlieren. Klug sein = automatisieren!"),
    ("🎯 Digistore24 Affiliate — so geht's", "Über 400 Produkte, sofortige Auszahlung, bis zu 75% Provision. Mit dem richtigen Traffic-System läuft das vollautomatisch. 🔥 Details → Link in Bio"),
]


async def _page_token() -> str:
    """Gibt den AIITEC Page Token zurück."""
    return (
        os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC") or
        os.getenv("FACEBOOK_PAGE_TOKEN") or
        os.getenv("META_ACCESS_TOKEN") or
        ""
    )


async def _generate_content() -> tuple[str, str]:
    """Generiert Titel + Text (OpenClaw → Fallback auf Pool)."""
    try:
        from modules.open_claw import claw_complete
        prompt = ("Erstelle einen kurzen viralen Instagram-Post auf Deutsch (max 120 Wörter) "
                  "über KI-Automatisierung für E-Commerce / Online Business. "
                  "Mit Emojis, Hashtags, Call-to-Action. "
                  "Kein Markdown, nur Text.")
        text = await asyncio.wait_for(claw_complete(prompt, fast=True), timeout=15)
        if text and len(text) > 30:
            lines = text.strip().split("\n", 1)
            title = lines[0][:60].strip("*#- ")
            body  = text.strip()
            return title, body
    except Exception:
        pass
    title, body = random.choice(CONTENT_POOL)
    hashtags = "\n\n#KI #Shopify #PassivesEinkommen #OnlineBusiness #Automatisierung #Ecommerce #MakeMoneyOnline #AIitec"
    return title, body + hashtags


async def _get_shopify_image() -> str:
    """Holt erstes Shopify-Produktbild (öffentlich zugänglich)."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json?limit=10&fields=images",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
            ) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
        products = data.get("products", [])
        random.shuffle(products)
        for p in products:
            imgs = p.get("images", [])
            if imgs:
                src = imgs[0].get("src", "")
                if src and src.startswith("https://"):
                    return src
    except Exception:
        pass
    return ""


async def post_to_facebook(text: str, page_token: str) -> dict:
    """Postet auf Facebook AIITEC Page."""
    if not page_token:
        return {"ok": False, "error": "kein FACEBOOK_PAGE_TOKEN_AIITEC gesetzt"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"{FB_BASE}/{PAGE_ID}/feed",
                params={"access_token": page_token},
                json={"message": text},
            ) as r:
                d = await r.json(content_type=None)
        if d.get("id"):
            return {"ok": True, "post_id": d["id"]}
        err = d.get("error", {})
        return {"ok": False, "error": err.get("message", str(d))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_to_instagram(caption: str, image_url: str, page_token: str) -> dict:
    """Postet auf Instagram @aaiitecc via Graph API (braucht Bild-URL)."""
    if not page_token:
        return {"ok": False, "error": "kein Token"}
    if not image_url:
        return {"ok": False, "error": "kein Bild verfügbar"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            # Schritt 1: Media Container erstellen
            async with s.post(
                f"{FB_BASE}/{IG_USER_ID}/media",
                params={"access_token": page_token},
                json={"image_url": image_url, "caption": caption},
            ) as r:
                media_resp = await r.json(content_type=None)

            creation_id = media_resp.get("id")
            if not creation_id:
                err = media_resp.get("error", {})
                return {"ok": False, "error": f"media create: {err.get('message', str(media_resp))[:120]}"}

            await asyncio.sleep(3)

            # Schritt 2: Veröffentlichen
            async with s.post(
                f"{FB_BASE}/{IG_USER_ID}/media_publish",
                params={"access_token": page_token},
                json={"creation_id": creation_id},
            ) as r:
                pub_resp = await r.json(content_type=None)

        if pub_resp.get("id"):
            return {"ok": True, "ig_post_id": pub_resp["id"]}
        err = pub_resp.get("error", {})
        return {"ok": False, "error": f"publish: {err.get('message', str(pub_resp))[:120]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _tg(msg: str) -> None:
    # Marketing pipeline status → public channel only (not private chat)
    chat_id = TG_CHANNEL or TG_CHAT
    if not TG_TOKEN or not chat_id:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
    except Exception:
        pass


async def run_pipeline() -> dict:
    """Hauptfunktion: generiert Content + postet auf FB + IG."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("instagram_pipeline: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    if _ig_posted_today():
        log.info("instagram_pipeline: bereits heute gepostet — übersprungen")
        return {"ok": False, "skipped": True, "reason": "IG_DAILY_LIMIT"}
    title, text = await _generate_content()
    image_url   = await _get_shopify_image()
    token       = await _page_token()

    results = {
        "title": title[:60],
        "has_token": bool(token),
        "has_image": bool(image_url),
        "facebook": {},
        "instagram": {},
        "timestamp": datetime.now().isoformat(),
    }

    if not token:
        await _tg(
            "⚠️ <b>Instagram/Facebook Pipeline</b>\n\n"
            "Kein Token — bitte einmalig klicken:\n"
            "https://supermegabot-production.up.railway.app/api/facebook/oauth"
        )
        return {**results, "error": "FACEBOOK_PAGE_TOKEN_AIITEC nicht gesetzt"}

    # Facebook post
    fb_result = await post_to_facebook(text, token)
    results["facebook"] = fb_result

    # Instagram post (nur wenn Bild verfügbar)
    ig_result = await post_to_instagram(text, image_url, token)
    results["instagram"] = ig_result

    # Telegram-Bestätigung
    fb_ok = fb_result.get("ok")
    ig_ok = ig_result.get("ok")
    status_msg = (
        f"📱 <b>Social Pipeline ausgeführt</b>\n\n"
        f"📘 Facebook AIITEC: {'✅ gepostet' if fb_ok else '❌ ' + fb_result.get('error','?')[:60]}\n"
        f"📸 Instagram @aaiitecc: {'✅ gepostet' if ig_ok else '❌ ' + ig_result.get('error','?')[:60]}\n\n"
        f"📝 {title[:50]}"
    )
    await _tg(status_msg)

    if fb_ok or ig_ok:
        _ig_mark_posted()
    log.info("InstagramPipeline: FB=%s IG=%s", fb_ok, ig_ok)
    return results
