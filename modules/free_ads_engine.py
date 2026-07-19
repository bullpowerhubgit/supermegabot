#!/usr/bin/env python3
"""
FreeAdsEngine — Vollautomatischer Meta-Ads-Ersatz (kostenlos)
=============================================================
Strategie: Statt €10–20/Tag Meta-Budget → 5 Posts tägl. auf 6 Plattformen.
Hashtag-Targeting (gratis) statt Zielgruppen-Budget.
Reels/Pinterest-Algorithmus (gratis) statt Paid Reach.

5 tägliche Kampagnen-Slots:
  Slot 1 (07:00)  MORNING_DROP   — Produktvorstellung mit Preisanreiz
  Slot 2 (11:00)  FLASH_DEAL     — Zeitdruck-Content (nur heute)
  Slot 3 (14:00)  EDUCATIONAL    — Mehrwert-Tipp (baut Vertrauen)
  Slot 4 (18:00)  SOCIAL_PROOF   — Testimonial / Vorteile
  Slot 5 (21:00)  COMMUNITY      — Reddit-Nischen-Posts

Plattformen (alle kostenlos):
  Instagram @aaiitecc (4.799 Follower) | Facebook AiiteC Page
  TikTok | Pinterest | Twitter/X | Reddit (r/smarthome etc.)

Activation: FREE_ADS_ENABLED=true (Railway Env)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("FreeAdsEngine")

ENABLED        = os.getenv("FREE_ADS_ENABLED", "true").lower() == "true"
SHOP_URL       = os.getenv("PUBLIC_SHOP_URL", "https://ineedit.com.co")
GUMROAD_URL    = "https://tecbuuss.gumroad.com"
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
DATA_DIR       = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "free_ads"))

# Hashtag-Sets = freie Alternative zu Meta-Zielgruppen-Targeting
_HASHTAGS = {
    "smarthome":  "#smarthome #homeautomation #smarttech #iotsolutions #smarthomesetup #hometech #automation #techlife #gadgets #wohntech",
    "solar":      "#solar #solarpower #solarpanel #erneuerbare #offgrid #solarenergie #balkonkraftwerk #nachhaltigkeit #greenenergy #photovoltaik",
    "tech":       "#techgadgets #techlife #gadgets #innovation #smartdevice #techreviews #gadgetlovers #zukunftstechnik #digitalisierung #techde",
    "saas":       "#saas #ecommerce #shopify #ki #automatisierung #onlinebusiness #passiveincome #digitalproducts #aitools #entrepreneurship",
    "digital":    "#digitalprodukte #onlinekurs #passivesincome #digitaleprodukte #kimarketing #businessautomatisierung #gumroad #digistore",
}

_REDDIT_TARGETS = [
    ("smarthome",    "r/smarthome"),
    ("smarthome",    "r/homeautomation"),
    ("solar",        "r/solar"),
    ("solar",        "r/DIYsolar"),
    ("tech",         "r/gadgets"),
    ("saas",         "r/ecommerce"),
    ("digital",      "r/passive_income"),
]


def _utm(source: str, campaign: str, content: str = "") -> str:
    p = f"utm_source={source}&utm_medium=organic&utm_campaign={campaign}"
    if content:
        p += f"&utm_content={content}"
    return p


def _shop_link(product_handle: str, slot: str, platform: str) -> str:
    base = f"{SHOP_URL}/products/{product_handle}"
    return f"{base}?{_utm(platform, 'free_ads_shop', slot)}"


def _gumroad_link(platform: str, slot: str) -> str:
    return f"{GUMROAD_URL}?{_utm(platform, 'free_ads_gumroad', slot)}"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _load_posted() -> dict:
    p = DATA_DIR / "posted.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _mark_posted(key: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    posted = _load_posted()
    posted[key] = datetime.now(timezone.utc).isoformat()
    # Keep last 200 entries
    if len(posted) > 200:
        posted = dict(list(posted.items())[-200:])
    (DATA_DIR / "posted.json").write_text(json.dumps(posted, indent=2))


def _was_posted_today(key: str) -> bool:
    posted = _load_posted()
    ts = posted.get(key)
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() < 20 * 3600
    except Exception:
        return False


# ── Content Generation ────────────────────────────────────────────────────────

async def _generate_content(product_name: str, price: str, url: str,
                             slot: str, platform: str, niche: str) -> dict:
    """KI generiert plattform-spezifischen Ad-Content via Groq/DeepSeek (gratis)."""
    try:
        from modules.ai_client import ai_complete

        slot_prompts = {
            "morning_drop":  "Produktvorstellung — begeistere auf Anhieb, Preis als Highlight",
            "flash_deal":    "Zeitdruck-Angebot — 'Nur heute', 'Begrenzte Stückzahl', Dringlichkeit",
            "educational":   "Erkläre den Hauptvorteil in 3 Sätzen — Mehrwert ohne Kaufdruck",
            "social_proof":  "Vertrauen aufbauen — 'Kunden lieben es weil...', Ergebnisse zeigen",
            "community":     "Ehrlicher Community-Post — Frage stellen, Diskussion anstoßen",
        }

        platform_hints = {
            "instagram": "Caption mit Emojis, max 200 Zeichen Text + 10 Hashtags",
            "facebook":  "Freundlicher Post, max 250 Zeichen, 1 Link",
            "tiktok":    "Hook in 3 Wörtern, dann 2 Punkte, CTA am Ende, max 150 Zeichen",
            "pinterest": "SEO-Beschreibung mit Keywords, max 200 Zeichen",
            "twitter":   "Tweet max 200 Zeichen + Link, 2 Hashtags",
            "reddit":    "Echter Community-Post ohne offensichtliche Werbung, max 300 Zeichen",
        }

        prompt = f"""Erstelle einen Social-Media-Post auf Deutsch für:
Produkt: {product_name}
Preis: {price}
Link: {url}
Plattform: {platform} — {platform_hints.get(platform, '')}
Strategie: {slot_prompts.get(slot, 'Produkt vorstellen')}
Nische: {niche}

Antworte NUR mit JSON (kein Markdown):
{{
  "caption": "Post-Text fertig zum Kopieren",
  "hashtags": "{_HASHTAGS.get(niche, _HASHTAGS['tech'])}",
  "hook": "Erste 5 Wörter als Aufmerksamkeits-Hook",
  "cta": "Kurzer Call-to-Action"
}}"""

        raw = await ai_complete(prompt, max_tokens=400)
        if not raw:
            raise ValueError("ai_complete returned empty")

        # JSON aus Response extrahieren
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            data["url"] = url
            data["product"] = product_name
            data["slot"] = slot
            return data
    except Exception as e:
        log.warning("Content-Gen fehlgeschlagen: %s", e)

    # Fallback-Template wenn AI nicht antwortet
    templates = {
        "morning_drop": f"Guten Morgen! {product_name} — Jetzt für {price} verfügbar.",
        "flash_deal":   f"FLASH DEAL: {product_name} nur {price}. Heute bestellen!",
        "educational":  f"Tipp des Tages: {product_name} macht dein Zuhause smarter. Ab {price}.",
        "social_proof": f"Kunden lieben {product_name}: Smart, modern und ab {price} verfügbar.",
        "community":    f"Hat jemand Erfahrung mit Smart Home Produkten? Wir haben {product_name} für {price}.",
    }
    return {
        "caption": templates.get(slot, f"{product_name} — {price}"),
        "hashtags": _HASHTAGS.get(niche, _HASHTAGS["tech"]),
        "hook": product_name[:30],
        "cta": f"Jetzt für {price} →",
        "url": url,
        "product": product_name,
        "slot": slot,
    }


# ── PostGuard — Prüfung + Reparatur vor jedem Post ───────────────────────────

async def _guard(text: str, platform: str, image_url: str = "") -> tuple:
    """PostGuardian check + auto-repair. Returns (ok, final_text).
    Bei ok=False: NICHT posten. Teilt die Logik mit brutal_ads_engine, keine Duplikate."""
    try:
        from modules.post_guardian import check_post, auto_repair_post
        result = await check_post(platform, text, image_url or None)
        if result["ok"]:
            return True, text
        repair = await auto_repair_post(text, platform, image_url or None)
        if repair.get("ok"):
            log.info("FreeAds: Post repariert [%s]: %s", platform, repair.get("changes"))
            return True, repair["repaired_text"]
        log.warning("FreeAds: Post BLOCKIERT [%s]: %s", platform, result.get("errors"))
        return False, text
    except Exception as e:
        log.debug("FreeAds: Guardian-Fehler %s — allow", e)
        return True, text  # Guardian selbst defekt → durchlassen


# ── Platform Posters ──────────────────────────────────────────────────────────

async def _post_instagram(content: dict) -> dict:
    try:
        from modules.social_autoposter import post_to_instagram
        caption = f"{content['caption']}\n\n{content['hashtags']}\n\n{content['url']}"
        ok, caption = await _guard(caption, "instagram")
        if not ok:
            return {"ok": False, "reason": "content_blocked_by_guard"}
        result = await post_to_instagram(caption=caption, image_url="")
        return result or {"ok": False, "reason": "no_result"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:60]}


async def _post_facebook(content: dict) -> dict:
    try:
        from modules.social_autoposter import post_to_facebook
        msg = f"{content['caption']}\n\n{content['cta']}: {content['url']}"
        ok, msg = await _guard(msg, "facebook")
        if not ok:
            return {"ok": False, "reason": "content_blocked_by_guard"}
        result = await post_to_facebook(message=msg, link=content["url"])
        return result or {"ok": False, "reason": "no_result"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:60]}


async def _post_pinterest(content: dict, niche: str) -> dict:
    try:
        from modules.social_connectors import PinterestConnector
        pc = PinterestConnector()
        board_map = {
            "smarthome": os.getenv("PINTEREST_BOARD_SMARTHOME", ""),
            "solar": os.getenv("PINTEREST_BOARD_SOLAR", ""),
            "tech": os.getenv("PINTEREST_BOARD_TECH", ""),
            "default": os.getenv("PINTEREST_BOARD_ID", ""),
        }
        board = board_map.get(niche) or board_map["default"]
        if not board:
            return {"ok": False, "reason": "PINTEREST_BOARD_ID not set"}
        desc = f"{content['caption']} {content['hashtags']}"
        ok, desc = await _guard(desc, "pinterest")
        if not ok:
            return {"ok": False, "reason": "content_blocked_by_guard"}
        result = await pc.create_pin(
            board_id=board,
            title=content["hook"],
            description=desc,
            link=content["url"],
            image_url="",
        )
        return result or {"ok": False, "reason": "no_result"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:60]}


async def _post_twitter(content: dict) -> dict:
    try:
        from modules.twitter_auto_poster import run_auto_tweet
        tweet = f"{content['hook']} — {content['caption'][:120]}\n{content['url']}"
        ok, tweet = await _guard(tweet, "twitter")
        if not ok:
            return {"ok": False, "reason": "content_blocked_by_guard"}
        result = await run_auto_tweet(custom_text=tweet)
        return result or {"ok": False, "reason": "no_result"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:60]}


async def _post_reddit(content: dict, subreddit: str, product_name: str) -> dict:
    try:
        from modules.social_connectors import RedditConnector
        rc = RedditConnector()
        title = f"{content['hook']}: {product_name}"
        text  = f"{content['caption']}\n\nMehr Infos: {content['url']}"
        ok, text = await _guard(text, "reddit")
        if not ok:
            return {"ok": False, "reason": "content_blocked_by_guard"}
        result = await rc.submit_post(
            subreddit=subreddit.lstrip("r/"),
            title=title,
            text=text,
        )
        return result or {"ok": False, "reason": "no_result"}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:60]}


# ── Product Sources ───────────────────────────────────────────────────────────

async def _get_shopify_product() -> Optional[dict]:
    """Holt ein zufälliges aktives Shopify-Produkt (Smart Home Nische)."""
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        return None
    import aiohttp
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json"
    params = {"limit": 50, "status": "active", "fields": "id,title,handle,variants,product_type"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                products = [p for p in data.get("products", [])
                            if p.get("variants") and float(p["variants"][0].get("price", 0)) > 0]
                if not products:
                    return None
                p = random.choice(products)
                price = p["variants"][0].get("price", "?")
                return {"name": p["title"], "handle": p["handle"],
                        "price": f"€{price}", "type": p.get("product_type", "smarthome")}
    except Exception as e:
        log.warning("Shopify-Produkt-Fetch: %s", e)
        return None


_GUMROAD_PRODUCTS = [
    ("SuperMegaBot ELITE", "€497"),
    ("AI Income Machine ELITE", "€297"),
    ("KI-Marketing ENGINE", "€247"),
    ("E-Commerce POWERTOOLS PRO", "€227"),
    ("Social Media AUTOPILOT", "€197"),
    ("KI-Automation MASTERY", "€197"),
    ("KI-Starter Bundle", "€97"),
]


def _niche_for_product(product: dict) -> str:
    t = (product.get("type") or product.get("name") or "").lower()
    if any(k in t for k in ["solar", "panel", "akku", "powerstation", "balkon"]):
        return "solar"
    if any(k in t for k in ["saas", "software", "abo", "ki", "ai", "marketing"]):
        return "saas"
    if any(k in t for k in ["digital", "kurs", "ebook", "gumroad"]):
        return "digital"
    return "smarthome"


# ── Main Campaign Runner ──────────────────────────────────────────────────────

async def run_campaign_slot(slot: str = "") -> dict:
    """
    Führt einen Posting-Slot aus (ein kompletter organischer 'Ad-Run').
    Slot wird automatisch nach Uhrzeit gewählt wenn nicht übergeben.
    """
    if not ENABLED:
        return {"ok": False, "reason": "FREE_ADS_ENABLED=false"}

    # Slot automatisch nach Uhrzeit
    if not slot:
        h = datetime.now(timezone.utc).hour
        if h < 9:
            slot = "morning_drop"
        elif h < 13:
            slot = "flash_deal"
        elif h < 16:
            slot = "educational"
        elif h < 20:
            slot = "social_proof"
        else:
            slot = "community"

    # Produkt wählen: abwechselnd Shop und Gumroad
    posted = _load_posted()
    shop_count  = sum(1 for k in posted if "shop" in k)
    gumr_count  = sum(1 for k in posted if "gumroad" in k)
    use_gumroad = (gumr_count < shop_count) or slot == "community"

    if use_gumroad:
        gp = random.choice(_GUMROAD_PRODUCTS)
        product = {"name": gp[0], "price": gp[1], "type": "digital"}
        get_url = lambda plat: _gumroad_link(plat, slot)
    else:
        product = await _get_shopify_product()
        if not product:
            log.warning("Kein Shopify-Produkt gefunden — nutze Gumroad")
            gp = random.choice(_GUMROAD_PRODUCTS)
            product = {"name": gp[0], "price": gp[1], "type": "digital"}
            get_url = lambda plat: _gumroad_link(plat, slot)
        else:
            get_url = lambda plat: _shop_link(product["handle"], slot, plat)

    niche = _niche_for_product(product)
    post_key = f"{slot}_{_hash(product['name'])}_{datetime.now(timezone.utc).date()}"

    if _was_posted_today(post_key):
        return {"ok": True, "skipped": True, "reason": "already_posted_today",
                "product": product["name"]}

    results: dict[str, dict] = {}
    platforms_run = 0

    # ── Instagram (primär wie Meta Ads Platzierung) ──────────────────────────
    ig_key = f"ig_{post_key}"
    if not _was_posted_today(ig_key):
        url = get_url("instagram")
        content = await _generate_content(product["name"], product["price"],
                                           url, slot, "instagram", niche)
        results["instagram"] = await _post_instagram(content)
        if results["instagram"].get("ok") or results["instagram"].get("id"):
            _mark_posted(ig_key)
            platforms_run += 1
        await asyncio.sleep(2)

    # ── Facebook ─────────────────────────────────────────────────────────────
    fb_key = f"fb_{post_key}"
    if not _was_posted_today(fb_key):
        url = get_url("facebook")
        content = await _generate_content(product["name"], product["price"],
                                           url, slot, "facebook", niche)
        results["facebook"] = await _post_facebook(content)
        if results["facebook"].get("ok") or results["facebook"].get("id"):
            _mark_posted(fb_key)
            platforms_run += 1
        await asyncio.sleep(2)

    # ── Pinterest (lange Post-Lebensdauer = organischer Dauerbrenner) ────────
    pin_key = f"pin_{post_key}"
    if not _was_posted_today(pin_key):
        url = get_url("pinterest")
        content = await _generate_content(product["name"], product["price"],
                                           url, slot, "pinterest", niche)
        results["pinterest"] = await _post_pinterest(content, niche)
        if results["pinterest"].get("ok") or results["pinterest"].get("id"):
            _mark_posted(pin_key)
            platforms_run += 1
        await asyncio.sleep(2)

    # ── Twitter/X ────────────────────────────────────────────────────────────
    tw_key = f"tw_{post_key}"
    if not _was_posted_today(tw_key):
        url = get_url("twitter")
        content = await _generate_content(product["name"], product["price"],
                                           url, slot, "twitter", niche)
        results["twitter"] = await _post_twitter(content)
        if results["twitter"].get("ok") or results["twitter"].get("id"):
            _mark_posted(tw_key)
            platforms_run += 1
        await asyncio.sleep(2)

    # ── Reddit (Nischen-Community = präzises Targeting ohne Budget) ──────────
    if slot == "community":
        targets = [t for t in _REDDIT_TARGETS if t[0] == niche or niche == "smarthome"]
        target = random.choice(targets) if targets else _REDDIT_TARGETS[0]
        rd_key = f"reddit_{target[1]}_{post_key}"
        if not _was_posted_today(rd_key):
            url = get_url("reddit")
            content = await _generate_content(product["name"], product["price"],
                                               url, slot, "reddit", niche)
            results["reddit"] = await _post_reddit(content, target[1], product["name"])
            if results["reddit"].get("ok") or results["results"].get("id") if "results" in results else False:
                _mark_posted(rd_key)
                platforms_run += 1

    _mark_posted(post_key)
    ok_platforms = [p for p, r in results.items() if r.get("ok") or r.get("id")]

    # ── Telegram-Report ───────────────────────────────────────────────────────
    if TG_TOKEN and TG_CHAT and platforms_run > 0:
        import aiohttp
        msg = (f"📢 FreeAds [{slot}]\n"
               f"Produkt: {product['name']} ({product['price']})\n"
               f"Nische: {niche} | {platforms_run} Plattformen\n"
               + "\n".join(f"  {'✅' if p in ok_platforms else '⚠️'} {p}" for p in results))
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": msg},
                    timeout=aiohttp.ClientTimeout(total=8),
                )
        except Exception:
            pass

    log.info("[FreeAds] Slot=%s Produkt=%s Plattformen=%d/%d",
             slot, product["name"], len(ok_platforms), len(results))

    return {
        "ok": True,
        "slot": slot,
        "product": product["name"],
        "price": product["price"],
        "niche": niche,
        "platforms_attempted": list(results.keys()),
        "platforms_ok": ok_platforms,
        "platforms_run": platforms_run,
        "results": {k: ("ok" if (v.get("ok") or v.get("id")) else v.get("reason", "fail"))
                    for k, v in results.items()},
    }


async def run_free_ads_cycle() -> dict:
    """Scheduler-Einstieg: automatischer Slot anhand der Uhrzeit."""
    return await run_campaign_slot()


async def run_all_slots() -> dict:
    """Alle 5 Slots auf einmal (für manuellen Full-Run oder Test)."""
    results = {}
    for slot in ["morning_drop", "flash_deal", "educational", "social_proof", "community"]:
        results[slot] = await run_campaign_slot(slot)
        await asyncio.sleep(10)
    total_ok = sum(r.get("platforms_run", 0) for r in results.values())
    return {"slots_run": 5, "total_platform_posts": total_ok, "results": results}


def get_status() -> dict:
    """Dashboard-Status für /api/free-ads/status."""
    posted = _load_posted()
    today = str(datetime.now(timezone.utc).date())
    today_posts = {k: v for k, v in posted.items() if today in v}
    return {
        "enabled": ENABLED,
        "total_tracked": len(posted),
        "posts_today": len(today_posts),
        "last_posts": list(today_posts.keys())[-10:],
        "platforms": ["instagram", "facebook", "pinterest", "twitter", "reddit"],
        "daily_slots": 5,
        "equivalent_ad_spend": f"€{len(today_posts) * 2:.0f}–€{len(today_posts) * 5:.0f}",
    }
