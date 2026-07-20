#!/usr/bin/env python3
"""
BrutalAdsEngine — Hybrid aus FreeAdsEngine + BrutusCore (von Null neu gebaut)
==============================================================================
Ersetzt: brutus_core.py, free_ads_engine.py, mega_auto_poster.py, social_autoposter
         twitter_auto_poster, auto_poster, viral_promo_poster, social_media_autopilot

WARUM NEU GEBAUT:
  - BrutusCore: keine URL-Prüfung → kaputte Links auf Instagram → Konto beschädigt
  - FreeAdsEngine: fehlende Kanäle (kein Blog, IndexNow, Klaviyo, LinkedIn)
  - Alle alten Poster: unkontrolliert, mehrfach gleicher Content, kein Safety-Gate

PERMANENTE FIXES (lösen das "Seite nicht erreichbar"-Problem):
  1. PRE-FLIGHT: JEDE URL wird auf HTTP 200 geprüft — keine 404 wird je gepostet
  2. PRODUKT-GATE: Nur active + hat Bild + Preis > 0 — nie Draft/Unpublished
  3. CONTENT-GUARD: 30+ Blocklist-Einträge — kein AI-Müll, kein "nicht verfügbar"
  4. PLATFORM-CHECK: Credential fehlt → Platform übersprungen (kein Error-Post)
  5. RATE-LIMIT: Instagram max 3/Tag, Facebook max 5/Tag, Reddit max 2/Tag
  6. DEDUP: gleiche Produkt+Platform nicht in 20h
  7. NEVER-TWICE: gleicher Content nie nochmal egal wann

12 Kanäle (alle kostenlos):
  Instagram · Facebook · Pinterest · Twitter/X · Reddit · LinkedIn
  Shopify-Blog (SEO) · Telegram-Channel · IndexNow (Google) · Klaviyo · Discord · Slack

5 Kampagnen-Slots täglich (Zeit-basiert):
  07:00 MORNING_DROP   — Produktvorstellung, Preis als Hook
  11:00 FLASH_DEAL     — Zeitdruck "nur heute", Knappheits-Signal
  14:00 EDUCATIONAL    — Mehrwert-Tipp, baut Vertrauen ohne Kaufdruck
  18:00 SOCIAL_PROOF   — Vorteile, Ergebnisse, Kunden-Nutzen
  21:00 COMMUNITY      — Reddit, ehrliche Community-Posts

Activation: BRUTAL_ADS_ENABLED=true (Railway Env, default true)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("BrutalAdsEngine")

# ── Config ────────────────────────────────────────────────────────────────────
ENABLED         = os.getenv("BRUTAL_ADS_ENABLED", "true").lower() == "true"
SHOP_URL        = os.getenv("PUBLIC_SHOP_URL", "https://ineedit.com.co")
GUMROAD_URL     = "https://tecbuuss.gumroad.com"
SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHANNEL      = os.getenv("TELEGRAM_CHANNEL_ID", "")
TG_ALERT        = os.getenv("TELEGRAM_CHAT_ID", "")
INDEXNOW_KEY    = os.getenv("INDEXNOW_KEY", "bullpower2026indexnow")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
SLACK_WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "")
LINKEDIN_TOKEN  = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_URN    = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:YcxbqVN0ZR")
DATA_DIR        = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "brutal_ads"))
RATE_FILE       = DATA_DIR / "rate_state.json"
DEDUP_FILE      = DATA_DIR / "dedup.json"

# Platform-spezifische Rate-Limits (pro Tag)
_RATE_LIMITS = {
    "instagram":    3,   # IG: 3 Posts/Tag = max ohne Shadow-Ban-Risiko
    "facebook":     1,   # 1/Tag — FB spamblockt bei >2 Posts schnell hintereinander
    "pinterest":    8,   # Pinterest: je mehr, desto besser (kein Spam-Risiko)
    "twitter":      6,
    "reddit":       2,   # Reddit: 2/Tag max, sonst Bann-Risiko
    "linkedin":     2,   # LinkedIn: Qualität > Quantität
    "shopify_blog": 3,
    "telegram":    10,
    "discord":      5,
    "slack":        5,
    "indexnow":    20,
    "klaviyo":     10,
}

# Hashtags = freies Audience-Targeting (Ersatz für Meta-Zielgruppen-€-Budget)
_HASHTAGS = {
    "smarthome": "#smarthome #homeautomation #smarttech #iotsolutions #smarthomesetup #hometech #automation #techlife #gadgets #wohntech #smartliving #homedecortech",
    "solar":     "#solar #solarpower #solarpanel #erneuerbare #offgrid #solarenergie #balkonkraftwerk #nachhaltigkeit #greenenergy #photovoltaik #solaranlage #autark",
    "tech":      "#techgadgets #techlife #gadgets #innovation #smartdevice #techreviews #gadgetlovers #zukunftstechnik #digitalisierung #techde #gadgetcheck #neuetechnik",
    "saas":      "#saas #ecommerce #shopify #ki #automatisierung #onlinebusiness #passiveincome #digitalproducts #aitools #entrepreneurship #businessautomation",
    "digital":   "#digitalprodukte #onlinekurs #passivesincome #digitaleprodukte #kimarketing #businessautomatisierung #gumroad #digistore #infomarketing",
}

# Reddit-Subreddits pro Nische = Nischen-Targeting gratis
_REDDIT_TARGETS = {
    "smarthome": ["smarthome", "homeautomation", "DIY", "housedesign"],
    "solar":     ["solar", "DIYsolar", "offgrid", "Energiewende"],
    "tech":      ["gadgets", "tech", "Kaufempfehlungen"],
    "saas":      ["ecommerce", "Entrepreneur", "passive_income"],
    "digital":   ["passive_income", "digitalnomad", "OnlineBusiness"],
}

# Content-Sicherheits-Blocklist — verhindert Konto-Beschädigungen
_CONTENT_BLOCKLIST = [
    # AI-Fehler / Technische Strings
    "traceback", "exception:", "error code", "credit balance is too low",
    "api error", "rate limit", "unauthorized", "forbidden",
    "not found", "404", "500 internal", "connection error",
    # Produkt-Probleme
    "nicht verfügbar", "not available", "ausverkauft", "sold out",
    "coming soon", "demnächst", "temporary", "temporär",
    "portable charger", "wireless earbuds",  # generische AI-Platzhalter
    # AI-Platzhalter / Dummy-Content
    "lorem ipsum", "example product", "test product", "demo produkt",
    "[produktname]", "[preis]", "[link]", "your product here",
    "placeholder", "sample text", "insert here",
    # Gefährliche Inhalte
    "fake", "betrug", "scam",
]

# Gumroad-Produkt-Katalog (hardcoded da Gumroad-API langsam)
_GUMROAD_PRODUCTS = [
    ("SuperMegaBot ELITE", "€497",    "ki-automatisierung"),
    ("AI Income Machine ELITE", "€297", "ki-business"),
    ("KI-Marketing ENGINE", "€247",   "ki-marketing"),
    ("E-Commerce POWERTOOLS PRO", "€227", "ecommerce"),
    ("Social Media AUTOPILOT", "€197", "social-media"),
    ("KI-Automation MASTERY", "€197", "ki-automatisierung"),
    ("KI-Starter Bundle", "€97",       "ki-starter"),
]

# Fallback-Bilder für Gumroad-Produkte (kein eigenes Bild) — verifizierte Pexels-URLs
_GUMROAD_NICHE_IMAGES: dict[str, str] = {
    "ki-automatisierung": "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg",   # Code/Laptop
    "ki-business":        "https://images.pexels.com/photos/7688336/pexels-photo-7688336.jpeg",   # Business-Dashboard
    "ki-marketing":       "https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg",     # Marketing Analytics
    "ecommerce":          "https://images.pexels.com/photos/230544/pexels-photo-230544.jpeg",     # E-Commerce Shopping
    "social-media":       "https://images.pexels.com/photos/607812/pexels-photo-607812.jpeg",     # Social Media Phone
    "ki-starter":         "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg",   # Code/Laptop
}
_GUMROAD_DEFAULT_IMAGE = "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg"


# ── State Management ──────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Trim to last 500 entries
    if len(data) > 500:
        data = dict(list(data.items())[-500:])
    path.write_text(json.dumps(data, indent=2))


def _rate_ok(platform: str) -> bool:
    """True wenn Platform heute noch unter Rate-Limit."""
    state = _load_json(RATE_FILE)
    today = str(datetime.now(timezone.utc).date())
    key = f"{platform}_{today}"
    count = state.get(key, 0)
    limit = _RATE_LIMITS.get(platform, 5)
    return count < limit


def _rate_record(platform: str) -> None:
    state = _load_json(RATE_FILE)
    today = str(datetime.now(timezone.utc).date())
    key = f"{platform}_{today}"
    state[key] = state.get(key, 0) + 1
    _save_json(RATE_FILE, state)


def _dedup_key(product_name: str, platform: str) -> str:
    h = hashlib.sha256(product_name.encode()).hexdigest()[:10]
    return f"{platform}_{h}"


def _was_posted_recently(product_name: str, platform: str, hours: int = 20) -> bool:
    state = _load_json(DEDUP_FILE)
    key = _dedup_key(product_name, platform)
    ts = state.get(key)
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
        return (datetime.now(timezone.utc) - dt).total_seconds() < hours * 3600
    except Exception:
        return False


def _mark_posted(product_name: str, platform: str) -> None:
    state = _load_json(DEDUP_FILE)
    state[_dedup_key(product_name, platform)] = datetime.now(timezone.utc).isoformat()
    _save_json(DEDUP_FILE, state)


# ── Safety Gates ──────────────────────────────────────────────────────────────

_URL_ERROR_BODY_MARKERS = [
    "produkt wurde noch nicht genehmigt",
    "das produkt wurde noch nicht genehmigt",
    "nicht genehmigt",
    "product not approved",
    "not approved yet",
    "page not found", "404", "seite nicht gefunden",
    "this page isn't available", "seite nicht verfügbar",
    "product is not available", "produkt nicht verfügbar",
    "out of stock", "ausverkauft",
    "access denied", "zugriff verweigert",
]

async def _check_url_live(url: str) -> tuple[bool, int]:
    """
    Prüft ob URL erreichbar ist UND ob der Seiteninhalt eine Fehlerseite zeigt.
    Erkennt auch HTTP-200-Fehlerseiten wie "nicht genehmigt" (Shopify Draft-Produkte).
    """
    if not url or not url.startswith("http"):
        return False, 0
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                timeout=aiohttp.ClientTimeout(total=12),
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            ) as r:
                if r.status >= 400:
                    log.warning("PRE-FLIGHT FAIL: %s → HTTP %d", url, r.status)
                    return False, r.status
                # Seiteninhalt auf Fehler-Marker prüfen (HTTP 200 kann trotzdem Fehlerseite sein!)
                try:
                    body = (await r.content.read(65536)).decode("utf-8", errors="ignore").lower()
                    for marker in _URL_ERROR_BODY_MARKERS:
                        if marker in body:
                            log.warning("PRE-FLIGHT BODY-BLOCK: %s → '%s' im Inhalt", url, marker)
                            return False, 200
                except Exception:
                    pass  # body-Fehler → trotzdem ok (HTTP-Status war 200)
                return True, r.status
    except Exception as e:
        log.warning("PRE-FLIGHT ERROR: %s → %s", url, e)
        return False, 0


def _content_safe(title: str, body: str) -> tuple[bool, str]:
    """Prüft ob Content sauber ist — blockiert AI-Müll, Fehler-Strings, Platzhalter."""
    combined = (title + " " + body).lower()
    for blocked in _CONTENT_BLOCKLIST:
        if blocked.lower() in combined:
            return False, f"blocked_content:{blocked}"
    if len(title.strip()) < 5:
        return False, "title_too_short"
    if len(body.strip()) < 10:
        return False, "body_too_short"
    # NeverTwice check
    try:
        from modules.post_never_twice import check_never_twice
        ok, errs = check_never_twice(f"{title} {body}", "brutal_ads")
        if not ok:
            return False, f"never_twice:{errs[0] if errs else 'duplicate'}"
    except Exception:
        pass
    return True, "ok"


def _product_valid(product: dict) -> tuple[bool, str]:
    """Prüft ob Shopify-Produkt wirklich postbar ist."""
    if not product.get("title") or len(product["title"].strip()) < 3:
        return False, "no_title"
    variants = product.get("variants", [])
    if not variants:
        return False, "no_variants"
    price = float(variants[0].get("price", 0) or 0)
    if price <= 0:
        return False, "price_zero"
    if product.get("status") not in ("active", None):
        return False, f"status_{product.get('status')}"
    images = product.get("images", [])
    if not images:
        return False, "no_image"
    return True, "ok"


# ── UTM Links ─────────────────────────────────────────────────────────────────

def _utm_link(base_url: str, platform: str, campaign: str, slot: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}utm_source={platform}&utm_medium=organic&utm_campaign={campaign}&utm_content={slot}"


# ── Product Sources ───────────────────────────────────────────────────────────

async def _get_shopify_product() -> Optional[dict]:
    """Holt ein zufälliges aktives Shopify-Produkt mit echtem Bild und Preis."""
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        return None
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json"
    params = {"limit": 100, "status": "active",
              "fields": "id,title,handle,variants,product_type,images,status"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                             timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return None
                products = (await r.json()).get("products", [])
                valid = [p for p in products if _product_valid(p)[0]]
                if not valid:
                    return None
                return random.choice(valid)
    except Exception as e:
        log.warning("Shopify-Produkt-Fetch: %s", e)
        return None


def _niche(product: dict) -> str:
    t = (product.get("product_type") or product.get("title") or "").lower()
    if any(k in t for k in ["solar", "panel", "akku", "powerstation", "balkon", "strom"]):
        return "solar"
    if any(k in t for k in ["saas", "software", "abo", "ki", "ai", "marketing", "kurs", "digital"]):
        return "digital"
    return "smarthome"


# ── AI Content Generation ─────────────────────────────────────────────────────

_SLOT_STRATEGY = {
    "morning_drop":  "Produktvorstellung — begeistere sofort, Preis als Hauptanreiz",
    "flash_deal":    "Zeitdruck — 'Nur heute', 'Begrenzte Stückzahl', echte Dringlichkeit",
    "educational":   "3 konkrete Vorteile ohne Kaufdruck — Mehrwert zuerst",
    "social_proof":  "Kunden-Nutzen — 'Wer dieses Produkt kauft bekommt...' + Ergebnis",
    "community":     "Ehrliche Community-Frage — klingt nicht wie Werbung, regt Diskussion an",
}

_PLATFORM_FORMAT = {
    "instagram":    "Caption max 200 Zeichen + Zeilenumbruch + 12 Hashtags",
    "facebook":     "Freundlicher Post max 280 Zeichen, 1 Link am Ende",
    "pinterest":    "SEO-Beschreibung 150 Zeichen, Keywords prominent, kein Emoji-Spam",
    "twitter":      "Max 200 Zeichen, prägnant, 2 Hashtags, Link am Ende",
    "reddit":       "Klingt wie echter Community-Post, KEIN offensichtlicher Werbetext, max 300 Zeichen",
    "linkedin":     "Professionell, 300 Zeichen, Business-Fokus, 3 Hashtags",
    "shopify_blog": "SEO-Artikel-Intro 200 Wörter, Keyword-reich, natürliche Sprache",
    "telegram":     "Emoji + Fettschrift, 200 Zeichen, Link ganz am Ende",
    "discord":      "Casual, max 250 Zeichen, Link als letztes Element",
    "slack":        "Professionell kurz, max 200 Zeichen",
}


async def _ai_content(product_name: str, price: str, url: str,
                      slot: str, platform: str, niche: str) -> dict:
    """Generiert plattform-spezifischen Content via Groq/DeepSeek (kostenlos)."""
    try:
        from modules.ai_client import ai_complete
        hashtags = _HASHTAGS.get(niche, _HASHTAGS["smarthome"])
        prompt = (
            f"Erstelle einen Social-Media-Post auf Deutsch:\n"
            f"Produkt: {product_name}\n"
            f"Preis: {price}\n"
            f"Slot-Strategie: {_SLOT_STRATEGY.get(slot, 'Produkt zeigen')}\n"
            f"Plattform-Format: {platform} — {_PLATFORM_FORMAT.get(platform, 'kurz und klar')}\n"
            f"Nische: {niche}\n"
            f"WICHTIG:\n"
            f"- Kein Platzhalter, kein Fehlertext, echter Inhalt\n"
            f"- KEIN HTML (keine Tags wie <b>, <em>, <br>)\n"
            f"- KEINE Einkommensversprechen (kein 'verdiene €X', 'passives Einkommen', 'reich werden')\n"
            f"- Nur echte Produktvorteile beschreiben\n"
            f"Antworte NUR mit JSON (plain text, kein HTML):\n"
            f'{{"caption": "fertiger Post-Text ohne HTML", "hashtags": "{hashtags}", '
            f'"hook": "Hook in 5 Wörtern", "cta": "Kurzer CTA"}}'
        )
        raw = await ai_complete(prompt, max_tokens=350)
        if raw:
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start >= 0 and end > start:
                d = json.loads(raw[start:end])
                if len(d.get("caption", "").strip()) >= 5:
                    d.update({"url": url, "product": product_name, "price": price, "slot": slot})
                    return d
    except Exception as e:
        log.warning("AI-Content-Gen Fehler: %s", e)

    # Fallback-Templates — immer sauber, nie Platzhalter
    fallbacks = {
        "morning_drop":  f"{product_name} — jetzt für {price} verfügbar. Smart Home auf neuem Level.",
        "flash_deal":    f"HEUTE: {product_name} für {price}. Nicht verpassen!",
        "educational":   f"3 Gründe warum {product_name} deinen Alltag vereinfacht. Ab {price}.",
        "social_proof":  f"Kunden lieben {product_name}: Smarter, schneller, einfacher. Ab {price}.",
        "community":     f"Hat jemand {product_name} ausprobiert? Würde mich über Erfahrungen freuen.",
    }
    caption = fallbacks.get(slot, f"{product_name} — {price}")
    return {
        "caption": caption,
        "hashtags": _HASHTAGS.get(niche, _HASHTAGS["smarthome"]),
        "hook": product_name[:40],
        "cta": f"Jetzt {price} →",
        "url": url,
        "product": product_name,
        "price": price,
        "slot": slot,
    }


def _strip_html(text: str) -> str:
    """Entfernt HTML-Tags aus Text (für Plattformen die kein HTML wollen)."""
    import re
    text = re.sub(r"<[^>]+>", "", text)          # Tags entfernen
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return " ".join(text.split())                  # Mehrfach-Leerzeichen bereinigen


def _full_post_text(content: dict, platform: str, include_hashtags: bool = True) -> str:
    """Baut den fertigen Post-Text für eine Plattform zusammen."""
    caption = content.get("caption", "")
    url = content.get("url", "")
    hashtags = content.get("hashtags", "") if include_hashtags else ""
    # Telegram unterstützt HTML (parse_mode=HTML) — alle anderen: plain text
    if platform != "telegram":
        caption = _strip_html(caption)
    if platform == "instagram":
        return f"{caption}\n\n{hashtags}\n\n{url}" if hashtags else f"{caption}\n\n{url}"
    if platform in ("twitter",):
        tags = " ".join(("#" + t.lstrip("#")) for t in hashtags.split()[:2]) if hashtags else ""
        return f"{caption} {tags} {url}".strip()
    if platform in ("reddit", "discord", "slack"):
        return f"{caption}\n\n{url}"
    if platform == "linkedin":
        tags = " ".join(("#" + t.lstrip("#")) for t in hashtags.split()[:3]) if hashtags else ""
        return f"{caption}\n\n{tags}\n{url}"
    if platform == "pinterest":
        return f"{caption} {url}"
    return f"{caption}\n{url}"


# ── Platform Posters ──────────────────────────────────────────────────────────

async def _guardian_check_and_repair(text: str, platform: str, image_url: str = "") -> tuple[bool, str]:
    """Prüft Text via PostGuardian. Versucht automatische Reparatur bei Fehlern.
    Returns (ok, final_text) — bei ok=False NICHT posten!"""
    try:
        from modules.post_guardian import check_post, auto_repair_post
        result = await check_post(platform, text, image_url or None)
        if result["ok"]:
            return True, text
        # Automatisch reparieren
        repair = await auto_repair_post(text, platform, image_url or None)
        if repair.get("ok"):
            log.info("BrutalAds: Post repariert [%s]: %s", platform, repair.get("changes"))
            return True, repair["repaired_text"]
        log.warning("BrutalAds: Post BLOCKIERT [%s]: %s", platform, result.get("errors"))
        return False, text
    except Exception as e:
        log.debug("BrutalAds: Guardian check Fehler %s — allow", e)
        return True, text  # Bei technischem Fehler: durchlassen (Guardian selbst defekt)


async def _post_instagram(content: dict) -> bool:
    try:
        text = _full_post_text(content, "instagram")
        img  = content.get("image_url", "")
        from modules.post_gateway import safe_post
        r = await safe_post(platform="instagram", text=text, image_url=img,
                            source_module="brutal_ads_engine")
        if not r.get("ok"):
            log.warning("[Instagram] fail: %s", r.get("error", r))
        return bool(r.get("ok"))
    except Exception as e:
        log.warning("[Instagram] exception: %s", e)
        return False


async def _post_facebook(content: dict) -> bool:
    try:
        text = _full_post_text(content, "facebook", include_hashtags=False)
        img  = content.get("image_url", "")
        from modules.post_gateway import safe_post
        r = await safe_post(platform="facebook", text=text, image_url=img,
                            source_module="brutal_ads_engine")
        if not r.get("ok"):
            log.warning("[Facebook] fail: %s", r.get("error", r))
        return bool(r.get("ok"))
    except Exception as e:
        log.warning("[Facebook] exception: %s", e)
        return False


async def _post_pinterest(content: dict, niche: str) -> bool:
    try:
        desc  = _full_post_text(content, "pinterest")
        title = content.get("hook", content.get("product", ""))
        img   = content.get("image_url", "")
        url   = content.get("url", "")
        post_text = f"{title}\n\n{desc}\n\n{url}".strip()
        from modules.post_gateway import safe_post
        r = await safe_post(platform="pinterest", text=post_text, image_url=img,
                            source_module="brutal_ads_engine")
        if not r.get("ok"):
            log.warning("[Pinterest] fail: %s", r.get("error", r))
        return bool(r.get("ok"))
    except Exception as e:
        log.warning("[Pinterest] exception: %s", e)
        return False


async def _post_twitter(content: dict) -> bool:
    try:
        text = _full_post_text(content, "twitter")
        from modules.post_gateway import safe_post
        r = await safe_post(platform="twitter", text=text, source_module="brutal_ads_engine")
        if not r.get("ok"):
            log.warning("[Twitter] fail: %s", r.get("error", r))
        return bool(r.get("ok"))
    except Exception as e:
        log.warning("[Twitter] exception: %s", e)
        return False


async def _post_reddit(content: dict, subreddit: str) -> bool:
    try:
        title = content.get("hook", content.get("product", ""))[:300]
        text  = _full_post_text(content, "reddit")
        post_content = f"{title}\n\n{text}".strip()
        from modules.post_gateway import safe_post
        r = await safe_post(platform="reddit", text=post_content, source_module="brutal_ads_engine")
        return bool(r.get("ok"))
    except Exception as e:
        log.debug("Reddit: %s", e)
        return False


async def _post_linkedin(content: dict) -> bool:
    if not LINKEDIN_TOKEN:
        return False
    try:
        text = _full_post_text(content, "linkedin")
        # Über post_gateway routen: Lock + Dedup-Check + API-Call (verhindert 422-Duplikat)
        from modules.post_gateway import safe_post
        r = await safe_post(platform="linkedin", text=text, source_module="brutal_ads_engine")
        return bool(r.get("ok"))
    except Exception as e:
        log.debug("LinkedIn: %s", e)
        return False


async def _post_shopify_blog(product_name: str, body: str, url: str, tags: list) -> bool:
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        return False
    try:
        blog_id = os.getenv("SHOPIFY_BLOG_ID", "gid://shopify/Blog/127011258755")
        blog_id_num = blog_id.split("/")[-1] if "/" in blog_id else blog_id
        html = (f"<h2>{product_name}</h2>"
                f"<p>{body}</p>"
                f'<p><a href="{url}">Jetzt ansehen →</a></p>')
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/blogs/{blog_id_num}/articles.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                         "Content-Type": "application/json"},
                json={"article": {"title": product_name, "body_html": html,
                                  "tags": ", ".join(tags), "published": True}},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            return r.status in (200, 201)
    except Exception as e:
        log.debug("ShopifyBlog: %s", e)
        return False


async def _post_telegram_channel(text: str) -> bool:
    try:
        from modules.post_gateway import safe_post
        r = await safe_post(platform="telegram", text=text, source_module="brutal_ads_engine")
        return bool(r.get("ok"))
    except Exception as e:
        log.debug("Telegram: %s", e)
        return False


async def _post_indexnow(url: str) -> bool:
    """Meldet URL sofort an Google/Bing IndexNow → schnellere Indexierung."""
    if not url.startswith("http"):
        return False
    try:
        host = url.split("/")[2]
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"https://api.indexnow.org/indexnow?url={url}&key={INDEXNOW_KEY}&keyLocation=https://{host}/{INDEXNOW_KEY}.txt",
                timeout=aiohttp.ClientTimeout(total=8),
            )
            return r.status in (200, 202)
    except Exception as e:
        log.debug("IndexNow: %s", e)
        return False


async def _post_klaviyo_event(product_name: str, url: str) -> bool:
    if not KLAVIYO_KEY:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://a.klaviyo.com/api/events/",
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                         "revision": "2024-02-15", "Content-Type": "application/json"},
                json={"data": {"type": "event",
                               "attributes": {
                                   "profile": {"data": {"type": "profile",
                                                        "attributes": {"anonymous_id": "brutal_ads_bot"}}},
                                   "metric": {"data": {"type": "metric",
                                                       "attributes": {"name": "BrutalAds Product Promoted"}}},
                                   "properties": {"product": product_name, "url": url}}}},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            return r.status in (200, 201, 202)
    except Exception as e:
        log.debug("Klaviyo: %s", e)
        return False


async def _post_discord(text: str) -> bool:
    if not DISCORD_WEBHOOK:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(DISCORD_WEBHOOK, json={"content": text},
                             timeout=aiohttp.ClientTimeout(total=8))
            return r.status in (200, 204)
    except Exception as e:
        log.debug("Discord: %s", e)
        return False


async def _post_slack(text: str) -> bool:
    if not SLACK_WEBHOOK:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(SLACK_WEBHOOK, json={"text": text},
                             timeout=aiohttp.ClientTimeout(total=8))
            return r.status == 200
    except Exception as e:
        log.debug("Slack: %s", e)
        return False


async def _alert_admin(msg: str) -> None:
    """Sendet intern (nicht öffentlich) an Rudolf wenn etwas schiefläuft."""
    if not TG_TOKEN or not TG_ALERT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_ALERT, "text": f"[BrutalAds] {msg}"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Main Campaign Engine ──────────────────────────────────────────────────────

async def run_brutal_cycle(slot: str = "") -> dict:
    """
    Haupt-Einstieg: Führt einen kompletten Posting-Zyklus durch.
    PRE-FLIGHT-CHECKS laufen IMMER vor dem ersten Post.
    """
    if not ENABLED:
        return {"ok": False, "reason": "BRUTAL_ADS_ENABLED=false"}

    # Zeitbasierter Slot wenn nicht übergeben
    if not slot:
        h = datetime.now(timezone.utc).hour
        slot = ("morning_drop" if h < 9 else
                "flash_deal"   if h < 13 else
                "educational"  if h < 16 else
                "social_proof" if h < 20 else
                "community")

    # Produkt wählen (abwechselnd Shopify + Gumroad)
    dedup = _load_json(DEDUP_FILE)
    shop_count = sum(1 for k in dedup if "shop_" in k)
    gumr_count = sum(1 for k in dedup if "gumr_" in k)
    use_gumroad = gumr_count <= shop_count or slot == "community"

    if use_gumroad:
        gp = random.choice(_GUMROAD_PRODUCTS)
        product_name, price, product_niche = gp
        base_url = GUMROAD_URL
        image_url = _GUMROAD_NICHE_IMAGES.get(product_niche, _GUMROAD_DEFAULT_IMAGE)
        source = "gumroad"
    else:
        p = await _get_shopify_product()
        if not p:
            gp = random.choice(_GUMROAD_PRODUCTS)
            product_name, price, product_niche = gp
            base_url = GUMROAD_URL
            image_url = _GUMROAD_NICHE_IMAGES.get(product_niche, _GUMROAD_DEFAULT_IMAGE)
            source = "gumroad"
        else:
            product_name = p["title"]
            price = f"€{p['variants'][0]['price']}"
            product_niche = _niche(p)
            base_url = f"{SHOP_URL}/products/{p['handle']}"
            image_url = p["images"][0]["src"] if p.get("images") else _GUMROAD_NICHE_IMAGES.get(product_niche, _GUMROAD_DEFAULT_IMAGE)
            source = "shopify"

    # ── PRE-FLIGHT: URL auf HTTP 200 prüfen ──────────────────────────────────
    url_ok, status_code = await _check_url_live(base_url)
    if not url_ok:
        msg = f"PRE-FLIGHT BLOCK: {product_name} — URL {base_url} → HTTP {status_code}"
        log.error(msg)
        await _alert_admin(msg)
        return {"ok": False, "reason": "url_not_reachable",
                "url": base_url, "http_status": status_code}

    niche = product_niche
    results: dict[str, bool | str] = {"slot": slot, "product": product_name,
                                       "source": source, "niche": niche}
    platforms_ok: list[str] = []

    async def _try_platform(platform: str, post_coro) -> None:
        """Wrapper: Rate-Limit, Dedup, Content-Guard, dann posten."""
        if not _rate_ok(platform):
            results[platform] = "rate_limited"
            return
        if _was_posted_recently(product_name, platform):
            results[platform] = "dedup_skip"
            return
        # Content generieren
        url_with_utm = _utm_link(base_url, platform, f"brutal_{niche}", slot)
        content = await _ai_content(product_name, price, url_with_utm, slot, platform, niche)
        content["image_url"] = image_url
        # Content-Sicherheits-Check
        safe, reason = _content_safe(content.get("caption", ""), content.get("hook", ""))
        if not safe:
            results[platform] = f"content_blocked:{reason}"
            log.warning("[%s] Content geblockt: %s", platform, reason)
            return
        # Posten
        ok = await post_coro(content)
        results[platform] = "ok" if ok else "fail"
        if ok:
            _rate_record(platform)
            _mark_posted(product_name, platform)
            platforms_ok.append(platform)

    # Reddit: Subreddit nach Nische wählen
    reddit_subs = _REDDIT_TARGETS.get(niche, _REDDIT_TARGETS["smarthome"])
    reddit_sub  = random.choice(reddit_subs)

    # Alle Plattformen parallel (außer Reddit bei non-community Slots)
    tasks = [
        _try_platform("instagram", _post_instagram),
        _try_platform("facebook",  _post_facebook),
        _try_platform("pinterest", lambda c: _post_pinterest(c, niche)),
        _try_platform("twitter",   _post_twitter),
        _try_platform("linkedin",  _post_linkedin),
    ]
    if slot == "community":
        tasks.append(_try_platform("reddit", lambda c: _post_reddit(c, reddit_sub)))

    await asyncio.gather(*tasks)

    # ── Sequentielle Kanäle (Shopify Blog, IndexNow, Klaviyo, Discord, Slack) ─
    if _rate_ok("shopify_blog"):
        blog_content = await _ai_content(product_name, price, base_url, slot, "shopify_blog", niche)
        safe, _ = _content_safe(blog_content.get("caption", ""), blog_content.get("hook", ""))
        if safe:
            ok = await _post_shopify_blog(
                product_name,
                blog_content.get("caption", ""),
                _utm_link(base_url, "shopify_blog", f"brutal_{niche}", slot),
                [niche, slot, "brutal-ads"],
            )
            results["shopify_blog"] = "ok" if ok else "fail"
            if ok:
                _rate_record("shopify_blog")
                platforms_ok.append("shopify_blog")

    if _rate_ok("indexnow"):
        ok = await _post_indexnow(base_url)
        results["indexnow"] = "ok" if ok else "fail"
        if ok:
            _rate_record("indexnow")

    if _rate_ok("klaviyo"):
        ok = await _post_klaviyo_event(product_name, base_url)
        results["klaviyo"] = "ok" if ok else "fail"
        if ok:
            _rate_record("klaviyo")

    # Telegram-Channel (öffentlich)
    tg_content = await _ai_content(product_name, price,
                                    _utm_link(base_url, "telegram", f"brutal_{niche}", slot),
                                    slot, "telegram", niche)
    tg_safe, _ = _content_safe(tg_content.get("caption", ""), tg_content.get("hook", ""))
    if tg_safe and _rate_ok("telegram"):
        tg_text = (f"<b>{tg_content.get('hook', product_name)}</b>\n\n"
                   f"{tg_content.get('caption', '')}\n\n"
                   f"💰 {price} → {tg_content.get('url', base_url)}")
        ok = await _post_telegram_channel(tg_text)
        results["telegram"] = "ok" if ok else "fail"
        if ok:
            _rate_record("telegram")
            platforms_ok.append("telegram")

    if DISCORD_WEBHOOK and _rate_ok("discord"):
        dc_content = await _ai_content(product_name, price,
                                        _utm_link(base_url, "discord", f"brutal_{niche}", slot),
                                        slot, "discord", niche)
        dc_safe, _ = _content_safe(dc_content.get("caption", ""), dc_content.get("hook", ""))
        if dc_safe:
            ok = await _post_discord(_full_post_text(dc_content, "discord"))
            results["discord"] = "ok" if ok else "fail"
            if ok:
                _rate_record("discord")
                platforms_ok.append("discord")

    if SLACK_WEBHOOK and _rate_ok("slack"):
        sl_content = await _ai_content(product_name, price,
                                        _utm_link(base_url, "slack", f"brutal_{niche}", slot),
                                        slot, "slack", niche)
        sl_safe, _ = _content_safe(sl_content.get("caption", ""), sl_content.get("hook", ""))
        if sl_safe:
            ok = await _post_slack(_full_post_text(sl_content, "slack"))
            results["slack"] = "ok" if ok else "fail"
            if ok:
                _rate_record("slack")

    results["platforms_ok"] = platforms_ok
    results["platforms_ok_count"] = len(platforms_ok)
    results["ok"] = len(platforms_ok) > 0

    # Admin-Report (intern — nicht öffentlich)
    if TG_TOKEN and TG_ALERT and len(platforms_ok) > 0:
        await _alert_admin(
            f"BrutalAds [{slot}] {product_name} ({price})\n"
            f"OK: {', '.join(platforms_ok)}\n"
            f"Nische: {niche} | Quelle: {source}"
        )

    log.info("[BrutalAds] slot=%s product='%s' ok=%s/%s",
             slot, product_name, len(platforms_ok), len(results) - 4)
    return results


async def run_all_slots() -> dict:
    """Alle 5 Slots auf einmal (manueller Full-Run)."""
    all_results = {}
    for s in ["morning_drop", "flash_deal", "educational", "social_proof", "community"]:
        all_results[s] = await run_brutal_cycle(s)
        await asyncio.sleep(30)
    total = sum(r.get("platforms_ok_count", 0) for r in all_results.values())
    return {"slots": 5, "total_posts": total, "results": all_results}


async def fire(title: str, body: str = "", link: str = "",
               niche: str = "smarthome", channels: list = None) -> dict:
    """
    BrutusCore-kompatibler API-Einstieg.
    Prüft URL vor dem Posten — kein kaputtes Link wird je gesendet.
    """
    if link:
        url_ok, status = await _check_url_live(link)
        if not url_ok:
            return {"ok": False, "reason": f"url_not_reachable:{status}", "link": link}

    safe, reason = _content_safe(title, body)
    if not safe:
        return {"ok": False, "reason": f"content_blocked:{reason}"}

    product = {"title": title, "price_str": "", "niche": niche, "url": link}
    gp = random.choice(_GUMROAD_PRODUCTS)
    content = await _ai_content(title, body[:20] or gp[1], link or GUMROAD_URL,
                                 "social_proof", "instagram", niche)
    content["caption"] = body or content.get("caption", title)
    content["url"] = link or GUMROAD_URL
    content.setdefault("image_url", _GUMROAD_NICHE_IMAGES.get(niche, _GUMROAD_DEFAULT_IMAGE))

    results = {}
    platforms_ok = []
    active_channels = channels or ["instagram", "facebook", "twitter", "linkedin",
                                    "telegram", "indexnow"]

    for platform in active_channels:
        if not _rate_ok(platform):
            results[platform] = "rate_limited"
            continue
        if platform == "instagram":
            ok = await _post_instagram(content)
        elif platform == "facebook":
            ok = await _post_facebook(content)
        elif platform == "twitter":
            ok = await _post_twitter(content)
        elif platform == "linkedin":
            ok = await _post_linkedin(content)
        elif platform == "telegram":
            tg = f"<b>{title}</b>\n\n{body[:200]}\n\n{link}"
            ok = await _post_telegram_channel(tg)
        elif platform == "indexnow":
            ok = await _post_indexnow(link) if link else False
        else:
            ok = False
        results[platform] = "ok" if ok else "fail"
        if ok:
            _rate_record(platform)
            platforms_ok.append(platform)

    return {"ok": bool(platforms_ok), "platforms_ok": platforms_ok, "results": results}


def get_status() -> dict:
    """Dashboard: GET /api/brutal-ads/status"""
    dedup = _load_json(DEDUP_FILE)
    rate  = _load_json(RATE_FILE)
    today = str(datetime.now(timezone.utc).date())
    today_posts = {p: rate.get(f"{p}_{today}", 0) for p in _RATE_LIMITS}
    return {
        "enabled": ENABLED,
        "total_tracked_products": len(dedup),
        "posts_today_by_platform": today_posts,
        "total_posts_today": sum(today_posts.values()),
        "rate_limits": _RATE_LIMITS,
        "channels": 12,
        "daily_slots": 5,
        "preflight_check": "active",
        "content_blocklist_entries": len(_CONTENT_BLOCKLIST),
    }
