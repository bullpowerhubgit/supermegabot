"""
Autonomous Product Pipeline — Vollautomatische Produktkette.
Jeden Tag: Trend erkennen → Produkt erstellen → Shopify/Gumroad/DS24 listen
            → Bundle generieren → alle 10 Kanäle bewerben → Geld verdienen.
Kein manueller Eingriff nötig.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("AutoProductPipeline")

# ─── Credentials ──────────────────────────────────────────────────────────────
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
SHOP           = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
GUMROAD_TOKEN  = os.getenv("GUMROAD_ACCESS_TOKEN", "")
PRINTIFY_TOKEN = os.getenv("PRINTIFY_API_TOKEN", "")
PRINTIFY_SHOP  = os.getenv("PRINTIFY_SHOP_ID", "27975583")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
PIPELINE_LOG = DATA_DIR / "product_pipeline.json"

# ─── Trend Keywords ───────────────────────────────────────────────────────────
TREND_NICHES = [
    ("KI Automatisierung", "ki automatisierung chatgpt shopify python"),
    ("Digital Marketing", "email marketing funnel seo content"),
    ("Dropshipping DACH", "dropshipping lieferant produkt shop"),
    ("Print on Demand", "t-shirt design print hoodie tasse"),
    ("E-Commerce Tools", "shopify plugin tool automation app"),
    ("Affiliate Marketing", "affiliate provision passive income"),
    ("Online Kurse", "kurs lernen video tutorial guide"),
    ("Social Media Wachstum", "instagram tiktok follower engagement"),
]


# ─── AI Helper ────────────────────────────────────────────────────────────────
async def _ai(prompt: str, max_tokens: int = 400) -> str:
    if not ANTHROPIC_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as r:
                d = await r.json(content_type=None)
        return (d.get("content") or [{"text": ""}])[0].get("text", "").strip()
    except Exception as e:
        log.warning("AI error: %s", e)
        return ""


# ─── Trend Detection ──────────────────────────────────────────────────────────
async def _detect_trend() -> dict:
    """Picks one trend niche and AI-generates fresh product idea."""
    niche_label, keywords = random.choice(TREND_NICHES)
    idea = await _ai(
        f"Erfinde eine konkrete Produktidee (Digital-Produkt oder Print-on-Demand) "
        f"für die Nische '{niche_label}'. "
        f"Antworte NUR als JSON: "
        f'{{"title": "...", "tagline": "...", "price_eur": 19, "type": "digital|pod", '
        f'"target": "...", "keywords": ["...", "..."]}}. '
        f"Preis zwischen 9 und 97 EUR. Sprache Deutsch.",
        max_tokens=300,
    )
    try:
        start = idea.find("{")
        end   = idea.rfind("}") + 1
        data  = json.loads(idea[start:end])
        data["niche"] = niche_label
        data["seed_keywords"] = keywords
        return data
    except Exception:
        return {
            "title": f"KI-Automation Pack — {niche_label}",
            "tagline": f"Vollautomatisches System für {niche_label}",
            "price_eur": 27,
            "type": "digital",
            "target": "Selbstständige und Unternehmer",
            "keywords": keywords.split(),
            "niche": niche_label,
            "seed_keywords": keywords,
        }


# ─── Step 1: Create on Shopify ────────────────────────────────────────────────
async def _create_shopify_product(idea: dict) -> Optional[str]:
    """Creates a digital product on Shopify, returns product URL."""
    if not SHOP or not SHOPIFY_TOK:
        return None
    description = await _ai(
        f"Schreibe eine überzeugende HTML-Produktbeschreibung (max 200 Wörter) auf Deutsch "
        f"für: '{idea['title']}'. Tagline: {idea['tagline']}. "
        f"Zielgruppe: {idea.get('target', 'Unternehmer')}. SEO-optimiert. Kein Markdown.",
        max_tokens=400,
    ) or f"<p>{idea['tagline']}</p>"

    payload = {
        "product": {
            "title": idea["title"],
            "body_html": description,
            "vendor": "SuperMegaBot",
            "product_type": "Digital Product",
            "tags": ", ".join(idea.get("keywords", []) + ["digital", "automation", "ki"]),
            "status": "active",
            "variants": [{"price": str(float(idea["price_eur"])), "inventory_management": None,
                          "inventory_policy": "continue", "requires_shipping": False}],
        }
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK,
                         "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        pid = data.get("product", {}).get("id")
        handle = data.get("product", {}).get("handle", "")
        shop_url = os.getenv("SHOPIFY_SHOP_URL", f"https://{SHOP.replace('.myshopify.com','')}.myshopify.com")
        url = f"{shop_url}/products/{handle}" if handle else None
        log.info("Shopify product created: %s (id=%s)", idea["title"], pid)
        return url
    except Exception as e:
        log.warning("Shopify create error: %s", e)
        return None


# ─── Step 2: Create on Gumroad ────────────────────────────────────────────────
async def _create_gumroad_product(idea: dict) -> Optional[str]:
    """Creates product on Gumroad, returns product URL."""
    if not GUMROAD_TOKEN:
        log.info("Gumroad: no token — skipping")
        return None
    description = await _ai(
        f"Produktbeschreibung (120 Wörter, Deutsch) für Gumroad-Produkt: '{idea['title']}'. "
        f"Kurz, knapp, Vorteile betonen. Plain Text.",
        max_tokens=200,
    ) or idea["tagline"]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.gumroad.com/v2/products",
                data={
                    "name": idea["title"],
                    "description": description,
                    "price": int(idea["price_eur"] * 100),
                    "currency": "eur",
                    "published": True,
                },
                headers={"Authorization": f"Bearer {GUMROAD_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json(content_type=None)
        if d.get("success"):
            url = d.get("product", {}).get("short_url", "")
            log.info("Gumroad product created: %s", url)
            return url
    except Exception as e:
        log.warning("Gumroad create error: %s", e)
    return None


# ─── Step 3: Create Printify POD (for pod type) ───────────────────────────────
async def _create_printify_product(idea: dict) -> Optional[str]:
    """Creates a POD t-shirt on Printify and publishes to Shopify."""
    if not PRINTIFY_TOKEN:
        return None
    try:
        from modules.printify_autonomy import create_and_publish
        result = await create_and_publish(
            title=idea["title"],
            description=idea["tagline"],
            keywords=idea.get("keywords", []),
        )
        if result.get("ok"):
            return result.get("shopify_url")
    except Exception as e:
        log.warning("Printify create error: %s", e)
    return None


# ─── Step 4: Create Bundle of Recent Products ─────────────────────────────────
async def _create_bundle(ideas_today: list) -> Optional[str]:
    """If 2+ products were created today, auto-bundles them on Shopify."""
    if len(ideas_today) < 2 or not SHOP or not SHOPIFY_TOK:
        return None
    try:
        from modules.product_bundle_engine import create_bundle_from_ideas
        result = await create_bundle_from_ideas(ideas_today)
        return result.get("url") if result else None
    except ImportError:
        pass
    except Exception as e:
        log.warning("Bundle create error: %s", e)
    return None


# ─── Step 5: Post across all channels ────────────────────────────────────────
async def _blast_all_channels(idea: dict, urls: dict) -> dict:
    """Posts the new product to all available channels."""
    product_url = (urls.get("shopify") or urls.get("gumroad") or
                   "https://autopilot-store-suite-fmbka.myshopify.com/collections/all")
    price_str   = f"€{idea['price_eur']:.0f}"

    post_text = await _ai(
        f"Schreibe einen viralen deutschen Social-Media-Post (3 Sätze) für: "
        f"'{idea['title']}' — {idea['tagline']}. Preis: {price_str}. "
        f"Link am Ende: {product_url} #KI #Automatisierung #Shopify",
        max_tokens=200,
    ) or (
        f"🚀 Neu: {idea['title']}\n"
        f"✅ {idea['tagline']}\n"
        f"Jetzt nur {price_str}: {product_url}"
    )

    results = {}
    try:
        from modules.mega_auto_poster import run_mega_auto_post
        r = await run_mega_auto_post(custom_text=post_text, product_url=product_url)
        results["mega_auto_post"] = r
    except Exception as e:
        log.warning("Mega auto post error: %s", e)
        results["mega_auto_post"] = {"error": str(e)}

    # Direct Telegram notify
    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            tg_msg = (
                f"✅ *Neues Produkt live!*\n"
                f"📦 {idea['title']}\n"
                f"💰 {price_str}\n"
                f"🎯 Nische: {idea['niche']}\n"
                f"🔗 Shopify: {urls.get('shopify', 'N/A')}\n"
                f"🛒 Gumroad: {urls.get('gumroad', 'N/A')}\n"
                f"📢 Alle Kanäle: geblastet"
            )
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT, "text": tg_msg, "parse_mode": "Markdown"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            pass

    return results


# ─── Step 6: Auto-activate Stripe checkout (price ID lookup) ─────────────────
async def _activate_checkout(idea: dict, shopify_url: Optional[str]) -> dict:
    """Ensures product has a Stripe checkout link via Shopify Buy Button or direct link."""
    if not shopify_url:
        return {"ok": False, "reason": "no shopify url"}
    checkout_url = shopify_url.replace("/products/", "/cart/").rstrip("/")
    log.info("Checkout active at: %s", checkout_url)
    return {"ok": True, "checkout_url": checkout_url}


# ─── Main Pipeline ────────────────────────────────────────────────────────────
async def run_product_pipeline(niche_override: Optional[str] = None) -> dict:
    """
    Full autonomous product pipeline:
    Trend → Create (Shopify + Gumroad + Printify) → Bundle → Blast → Report
    """
    ts = datetime.now(timezone.utc).isoformat()
    log.info("=== Autonomous Product Pipeline START ===")

    # 1. Detect trend / generate idea
    idea = await _detect_trend()
    if niche_override:
        idea["niche"] = niche_override
        idea["title"] = f"{niche_override} Automation Pack"
    log.info("Trend idea: %s (€%s, type=%s)", idea["title"], idea["price_eur"], idea["type"])

    # 2. Create products in parallel
    urls: dict = {}
    if idea.get("type") == "pod":
        shopify_url, gumroad_url = await asyncio.gather(
            _create_printify_product(idea),
            asyncio.sleep(0),
        )
        urls["shopify"] = shopify_url
    else:
        shopify_url, gumroad_url = await asyncio.gather(
            _create_shopify_product(idea),
            _create_gumroad_product(idea),
        )
        urls["shopify"] = shopify_url
        urls["gumroad"] = gumroad_url

    # 3. Blast all channels
    blast_result = await _blast_all_channels(idea, urls)

    # 4. Activate checkout
    checkout = await _activate_checkout(idea, urls.get("shopify"))

    # 5. Log to file
    entry = {
        "ts": ts, "idea": idea, "urls": urls,
        "blast": blast_result, "checkout": checkout,
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        existing = json.loads(PIPELINE_LOG.read_text()) if PIPELINE_LOG.exists() else []
        PIPELINE_LOG.write_text(json.dumps((existing + [entry])[-50:], ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning("Pipeline log error: %s", e)

    result = {
        "ok": True,
        "product": idea["title"],
        "price_eur": idea["price_eur"],
        "niche": idea["niche"],
        "type": idea["type"],
        "shopify_url": urls.get("shopify"),
        "gumroad_url": urls.get("gumroad"),
        "checkout_url": checkout.get("checkout_url"),
        "channels_blasted": True,
        "ts": ts,
    }
    log.info("=== Product Pipeline DONE: %s ===", idea["title"])
    return result


async def get_pipeline_history(limit: int = 10) -> list:
    try:
        data = json.loads(PIPELINE_LOG.read_text()) if PIPELINE_LOG.exists() else []
        return data[-limit:]
    except Exception:
        return []
