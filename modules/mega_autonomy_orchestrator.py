#!/usr/bin/env python3
"""
MegaAutonomyOrchestrator — Vollautonomes Master-System für ALLE Plattformen.
Koordiniert eBay, Amazon, AliExpress, Klaviyo, Gumroad, Stripe, DS24, Shopify.
KEIN BrutusCore / kein Telegram-Spam — nur echte Arbeit + Dashboard-Reports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("MegaAutonomy")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SHOPIFY_DOMAIN  = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN") or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER     = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL        = os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")
GUMROAD_TOKEN   = os.getenv("GUMROAD_ACCESS_TOKEN", "")
STRIPE_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")
EBAY_APP_ID     = os.getenv("EBAY_CLIENT_ID", "IRV7wFsqtKC76676391G2237LhVpgNCRZ1")
AMAZON_TAG      = os.getenv("AMAZON_ASSOCIATE_TAG", "bullpowerhub-21")
ALI_APP_KEY     = os.getenv("ALIEXPRESS_APP_KEY", "536860")
ALI_APP_SECRET  = os.getenv("ALIEXPRESS_APP_SECRET", "mmKF9pO8NZrEzdjpl6j0lXFoHhv213uN")
DS24_KEY        = os.getenv("DS24_API_KEY", "")
TG_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT         = os.getenv("TELEGRAM_CHAT_ID", "")


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _shopify_get(path: str, params: dict = None) -> dict:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {}
    try:
        from modules.shopify_client import rest_get
        return await rest_get(path + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""))
    except Exception:
        pass
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/{path}"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 429:
                    await asyncio.sleep(float(r.headers.get("Retry-After", 5)))
                return await r.json() if r.status < 400 else {}
    except Exception as e:
        log.debug("Shopify GET %s error: %s", path, e)
        return {}


async def _shopify_post(path: str, body: dict) -> dict:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {}
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/{path}"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    for _attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, headers=headers, json=body,
                                  timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429:
                        wait = float(r.headers.get("Retry-After", 5 * (_attempt + 1)))
                        log.warning("Shopify POST 429 (attempt %d/3), wait %.0fs", _attempt + 1, wait)
                        await asyncio.sleep(wait)
                        continue
                    return await r.json() if r.status < 400 else {}
        except Exception as e:
            log.debug("Shopify POST %s error: %s", path, e)
            return {}
    return {}


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


# ─── 1. eBay: Trending Smart Home Products → Shopify Import ─────────────────

async def run_ebay_import(count: int = 5) -> dict:
    """eBay Finding API → Shopify import (kein BrutusCore/Spam)."""
    FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
    KEYWORDS = [
        "smart home steckdose wlan", "wifi smart plug energy monitor",
        "zigbee gateway tuya", "smarthome beleuchtung set",
        "solar powerstation 1000w", "balkonkraftwerk set 800w",
        "smart thermostat wifi", "wlan steckdose schalter",
    ]
    kw = random.choice(KEYWORDS)
    items = []
    try:
        params = {
            "OPERATION-NAME": "findItemsByKeywords",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": EBAY_APP_ID,
            "RESPONSE-DATA-FORMAT": "JSON",
            "keywords": kw,
            "paginationInput.entriesPerPage": str(count),
            "itemFilter(0).name": "ListingType",
            "itemFilter(0).value": "FixedPrice",
            "itemFilter(1).name": "Condition",
            "itemFilter(1).value": "New",
            "itemFilter(2).name": "MinPrice",
            "itemFilter(2).value": "8",
            "sortOrder": "BestMatch",
            "outputSelector": "PictureURLSuperSize",
            "GLOBAL-ID": "EBAY-DE",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(FINDING_URL, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
        results = (data.get("findItemsByKeywordsResponse", [{}])[0]
                      .get("searchResult", [{}])[0]
                      .get("item", []))
        for item in results[:count]:
            title = item.get("title", [""])[0]
            url = item.get("viewItemURL", [""])[0]
            price_info = (item.get("sellingStatus", [{}])[0]
                             .get("currentPrice", [{}])[0])
            price = price_info.get("__value__", "")
            image = ""
            for img_key in ("pictureURLSuperSize", "galleryURL"):
                img_list = item.get(img_key, [])
                if img_list:
                    image = img_list[0]
                    break
            if title and float(price or 0) >= 8:
                items.append({"title": title[:120], "url": url,
                              "price": price, "image": image, "keyword": kw})
    except Exception as e:
        log.warning("eBay API: %s", e)

    imported = 0
    for item in items:
        try:
            from modules.product_gatekeeper import validate_product
            ok, _ = validate_product(title=item["title"], vendor="eBay Import",
                                     product_type="Smart Home", price=float(item["price"] or 0))
            if not ok:
                continue
            price_eur = round(float(item["price"] or 0) * 1.4, 2)  # markup 40%
            body = {
                "product": {
                    "title": item["title"],
                    "vendor": "eBay Import",
                    "product_type": "Smart Home",
                    "status": "active",
                    "body_html": f"<p>Smart Home Produkt — direkt verfügbar.</p>",
                    "tags": "smart-home,ebay-import,wifi",
                    "variants": [{"price": str(price_eur), "requires_shipping": True}],
                    "images": [{"src": item["image"]}] if item.get("image") else [],
                }
            }
            result = await _shopify_post("products.json", body)
            if result.get("product", {}).get("id"):
                imported += 1
                log.info("eBay→Shopify: %s (€%.2f)", item["title"][:60], price_eur)
        except Exception as e:
            log.debug("eBay import error: %s", e)

    return {"platform": "ebay", "found": len(items), "imported": imported,
            "keyword": kw}


# ─── 2. Amazon: Bestseller → Shopify Affiliate Blog Product ─────────────────

async def run_amazon_affiliate_research() -> dict:
    """Amazon.de Bestseller RSS → Shopify Blog oder Affiliate Collection."""
    import xml.etree.ElementTree as ET
    import re

    feeds = [
        "https://www.amazon.de/gp/rss/bestsellers/electronics",
        "https://www.amazon.de/gp/rss/bestsellers/sports",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SuperMegaBot/1.0)"}
    products = []
    for feed_url in feeds:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(feed_url, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    raw = await r.text()
            raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
            root = ET.fromstring(raw)
            for item in list(root.iter("item"))[:5]:
                title_el = item.find("title")
                link_el  = item.find("link")
                if title_el is None or link_el is None:
                    continue
                title = (title_el.text or "").strip()
                raw_link = (link_el.text or "").strip()
                asin_m = re.search(r'/dp/([A-Z0-9]{10})', raw_link)
                asin = asin_m.group(1) if asin_m else ""
                affiliate_url = (
                    f"https://www.amazon.de/dp/{asin}?tag={AMAZON_TAG}"
                    if asin else f"{raw_link}&tag={AMAZON_TAG}"
                )
                products.append({"title": title[:120], "url": affiliate_url, "asin": asin})
        except Exception as e:
            log.debug("Amazon RSS %s: %s", feed_url, e)

    # Save to data file for dashboard
    out_file = DATA_DIR / "amazon_affiliate_products.json"
    out_file.write_text(json.dumps(products[:20], ensure_ascii=False, indent=2))

    return {"platform": "amazon", "found": len(products), "saved": str(out_file)}


# ─── 3. AliExpress: Product Search → Shopify Import ─────────────────────────

async def run_aliexpress_import(count: int = 5) -> dict:
    """AliExpress Affiliate API → Shopify import."""
    import hashlib
    from urllib.parse import urlencode

    KEYWORDS = [
        "smart home steckdose wifi", "solar powerbank 20000mah",
        "smart plug energy monitor", "zigbee switch 1 gang",
        "led strip wifi rgb alexa",
    ]
    kw = random.choice(KEYWORDS)
    products = []

    try:
        ts = str(int(time.time() * 1000))
        params = {
            "method": "aliexpress.affiliate.product.query",
            "app_key": ALI_APP_KEY,
            "timestamp": ts,
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            "fields": "product_title,product_main_image_url,target_sale_price,product_detail_url",
            "keywords": kw,
            "target_currency": "EUR",
            "target_language": "DE",
            "page_size": str(count),
        }
        sign_str = ALI_APP_SECRET + "".join(
            f"{k}{v}" for k, v in sorted(params.items())
        ) + ALI_APP_SECRET
        params["sign"] = hashlib.md5(sign_str.encode()).hexdigest().upper()

        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://gw.api.taobao.com/router/rest",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()

        items = (data.get("aliexpress_affiliate_product_query_response", {})
                     .get("resp_result", {})
                     .get("result", {})
                     .get("products", {})
                     .get("product", []))
        for p in items[:count]:
            price = float(str(p.get("target_sale_price", "0")).replace(",", ".") or 0)
            if price < 5:
                continue
            products.append({
                "title": str(p.get("product_title", ""))[:120],
                "image": p.get("product_main_image_url", ""),
                "price": price,
                "url":   p.get("product_detail_url", ""),
            })
    except Exception as e:
        log.debug("AliExpress API: %s", e)

    imported = 0
    for p in products:
        try:
            from modules.product_gatekeeper import validate_product
            ok, _ = validate_product(title=p["title"], vendor="AliExpress Import",
                                     product_type="Smart Home", price=p["price"])
            if not ok:
                continue
            price_eur = round(p["price"] * 2.2, 2)  # markup 120%
            body = {
                "product": {
                    "title": p["title"],
                    "vendor": "AliExpress Import",
                    "product_type": "Smart Home",
                    "status": "active",
                    "body_html": "<p>Smart Home Gadget — sofort verfügbar.</p>",
                    "tags": "smart-home,aliexpress-import",
                    "variants": [{"price": str(price_eur), "requires_shipping": True}],
                    "images": [{"src": p["image"]}] if p.get("image") else [],
                }
            }
            result = await _shopify_post("products.json", body)
            if result.get("product", {}).get("id"):
                imported += 1
                log.info("AliExpress→Shopify: %s (€%.2f)", p["title"][:60], price_eur)
        except Exception as e:
            log.debug("AliExpress import: %s", e)

    return {"platform": "aliexpress", "found": len(products), "imported": imported}


# ─── 4. Klaviyo: Campaign für aktive Subscriber ──────────────────────────────

async def run_klaviyo_campaign() -> dict:
    """Klaviyo: Newsletter an echte Subscriber (kein Cold-Outreach)."""
    if not KLAVIYO_KEY:
        return {"platform": "klaviyo", "ok": False, "error": "no API key"}
    try:
        from modules.klaviyo_autonomy import run_klaviyo_cycle
        result = await run_klaviyo_cycle()
        return {"platform": "klaviyo", "ok": True, "result": result}
    except Exception as e:
        log.warning("Klaviyo cycle: %s", e)
        return {"platform": "klaviyo", "ok": False, "error": str(e)}


# ─── 5. Gumroad: Produkte anlegen + PDF hochladen ───────────────────────────

GUMROAD_PRODUCTS = [
    {
        "name": "SuperMegaBot ELITE — KI-Automation Komplett-System",
        "price": 49700,
        "description": "Das komplette SuperMegaBot KI-Automation-System: Shopify-Automation, DS24-Integration, Telegram-Bot, AI-Content-Generator, Multi-Platform-Posting. Sofort einsatzbereit. 120+ Seiten Anleitung + alle Skripte.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["automation", "ki", "shopify", "telegram"],
        "pdf": "supermegabot_elite.pdf",
        "cover_url": f"{SHOP_URL}/cdn/shop/files/supermegabot-cover.jpg",
    },
    {
        "name": "AI Income Machine ELITE — Passives Einkommen mit KI",
        "price": 29700,
        "description": "Komplettes System für passives Einkommen mit KI: Automatische Content-Erstellung, Affiliate-Marketing, Dropshipping-Automation. Praxisgetestet: €2.000–€10.000/Monat möglich.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["ki", "einkommen", "affiliate", "automation"],
        "pdf": "ai_income_machine.pdf",
        "cover_url": "",
    },
    {
        "name": "KI-Marketing ENGINE — Social Media Vollautomatik",
        "price": 24700,
        "description": "Automatisches Social Media Marketing mit KI: Facebook, Instagram, TikTok, LinkedIn, Pinterest vollautomatisch. KI-generierte Texte, Bilder, Kampagnen. 87-Punkte Checkliste.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["marketing", "social-media", "ki", "automation"],
        "pdf": "ki_marketing_engine.pdf",
        "cover_url": "",
    },
    {
        "name": "E-Commerce POWERTOOLS PRO — Shopify & eBay Masterkit",
        "price": 22700,
        "description": "Professionelles E-Commerce-Toolkit: Shopify-Optimierung, eBay-Integration, Amazon-Affiliate, AliExpress-Import, Preisoptimierung, SEO. Alle Tools + Anleitungen inklusive.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["ecommerce", "shopify", "ebay", "amazon"],
        "pdf": "ecommerce_powertools.pdf",
        "cover_url": "",
    },
    {
        "name": "Social Media AUTOPILOT — 7 Plattformen vollautomatisch",
        "price": 19700,
        "description": "Dein Social Media läuft 24/7 auf Autopilot: Instagram, Facebook, Twitter/X, LinkedIn, Pinterest, TikTok, Reddit. KI-Content, Scheduling, Analytics. Einmal einrichten — dauerhaft profitieren.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["social-media", "autopilot", "instagram", "tiktok"],
        "pdf": "social_media_autopilot.pdf",
        "cover_url": "",
    },
    {
        "name": "Print-on-Demand AUTOPILOT — Printify Vollautomatik",
        "price": 19700,
        "description": "Print-on-Demand ohne Aufwand: Printify-Automation, automatische Produkterstellung, Design-Generator, Bestellabwicklung. Von 0 auf €3.000/Monat mit PoD-Produkten.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["print-on-demand", "printify", "automation", "dropshipping"],
        "pdf": "pod_autopilot.pdf",
        "cover_url": "",
    },
    {
        "name": "KI-Automation MASTERY — Der komplette Kurs",
        "price": 19700,
        "description": "Vollständiger KI-Automation-Kurs: Von Grundlagen bis Experten-Level. Alle wichtigen KI-Tools, Prompts, Workflows. Inkl. 50+ KI-Prompt-Vorlagen und 12 Automation-Scripts.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["ki", "automation", "kurs", "prompts"],
        "pdf": "ki_automation_mastery.pdf",
        "cover_url": "",
    },
    {
        "name": "KI-Starter Bundle — Dein Einstieg in KI-Automation",
        "price": 9700,
        "description": "Perfekter Einstieg in KI-Automation: 30 ChatGPT-Prompts, 10 Automation-Templates, Schritt-für-Schritt Anleitungen. Ideal für Einsteiger ohne Vorkenntnisse.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["ki", "starter", "prompts", "einsteiger"],
        "pdf": "ki_marketing_engine.pdf",
        "cover_url": "",
    },
    {
        "name": "Print-on-Demand QUICKSTART — In 7 Tagen zum ersten Verkauf",
        "price": 9700,
        "description": "In 7 Tagen zum ersten Print-on-Demand Verkauf: Nische finden, Designs erstellen, bei Printify listen, Marketing starten. Mit Schritt-für-Schritt Aktionsplan.",
        "url": f"{SHOP_URL}/collections/digital",
        "tags": ["print-on-demand", "quickstart", "einsteiger"],
        "pdf": "pod_autopilot.pdf",
        "cover_url": "",
    },
]

PDF_DIR = Path("/private/tmp/gumroad_pdfs")


async def _gumroad_api(method: str, path: str, **kwargs) -> dict:
    """Gumroad API v2 call."""
    if not GUMROAD_TOKEN:
        return {"success": False, "message": "no GUMROAD_ACCESS_TOKEN"}
    base = "https://api.gumroad.com/v2"
    headers = {"Authorization": f"Bearer {GUMROAD_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as s:
            fn = getattr(s, method.lower())
            async with fn(f"{base}{path}", headers=headers,
                          timeout=aiohttp.ClientTimeout(total=30), **kwargs) as r:
                return await r.json()
    except Exception as e:
        return {"success": False, "message": str(e)}


async def _upload_pdf_to_gumroad(product_id: str, pdf_name: str) -> bool:
    """Lade PDF als Gumroad-Content via Multipart-Form-Data hoch."""
    pdf_path = PDF_DIR / pdf_name
    if not pdf_path.exists():
        log.warning("PDF nicht gefunden: %s", pdf_path)
        return False
    if not GUMROAD_TOKEN:
        return False
    try:
        import aiofiles
        from aiohttp import FormData
        form = FormData()
        form.add_field("access_token", GUMROAD_TOKEN)
        form.add_field("file", open(str(pdf_path), "rb"),
                       filename=pdf_name, content_type="application/pdf")
        async with aiohttp.ClientSession() as s:
            async with s.put(
                f"https://api.gumroad.com/v2/products/{product_id}/content_file",
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                result = await r.json()
                ok = result.get("success", False)
                if ok:
                    log.info("PDF hochgeladen: %s → Produkt %s", pdf_name, product_id)
                else:
                    log.warning("PDF upload fehlgeschlagen: %s — %s",
                                pdf_name, result.get("message", ""))
                return ok
    except Exception as e:
        log.warning("PDF upload error %s: %s", pdf_name, e)
        return False


async def run_gumroad_setup() -> dict:
    """Erstellt/aktualisiert alle 9 Gumroad-Produkte vollständig."""
    if not GUMROAD_TOKEN:
        return {"platform": "gumroad", "ok": False, "error": "kein GUMROAD_ACCESS_TOKEN"}

    # Bestehende Produkte laden
    existing_raw = await _gumroad_api("GET", "/products")
    existing = {p["name"]: p for p in existing_raw.get("products", [])}
    log.info("Gumroad: %d Produkte bereits vorhanden", len(existing))

    created = updated = files_uploaded = 0
    errors = []

    for prod in GUMROAD_PRODUCTS:
        try:
            existing_prod = existing.get(prod["name"])
            if existing_prod:
                # Update bestehend
                pid = existing_prod["id"]
                upd = await _gumroad_api("PUT", f"/products/{pid}", data={
                    "name":        prod["name"],
                    "description": prod["description"],
                    "price":       prod["price"],
                    "url":         prod["url"],
                    "published":   "true",
                })
                if upd.get("success"):
                    updated += 1
                    log.info("Gumroad updated: %s", prod["name"][:60])
                else:
                    errors.append({"name": prod["name"], "error": upd.get("message", "")})
                pid_for_upload = pid
            else:
                # Neu anlegen
                data = {
                    "name":        prod["name"],
                    "description": prod["description"],
                    "price":       prod["price"],
                    "url":         prod["url"],
                    "published":   "true",
                }
                result = await _gumroad_api("POST", "/products", data=data)
                if result.get("success"):
                    created += 1
                    pid_for_upload = result["product"]["id"]
                    log.info("Gumroad created: %s (ID: %s)", prod["name"][:60], pid_for_upload)
                else:
                    errors.append({"name": prod["name"], "error": result.get("message", "")})
                    continue

            # PDF hochladen
            if prod.get("pdf") and pid_for_upload:
                ok = await _upload_pdf_to_gumroad(pid_for_upload, prod["pdf"])
                if ok:
                    files_uploaded += 1

        except Exception as e:
            log.error("Gumroad setup error: %s — %s", prod["name"][:50], e)
            errors.append({"name": prod["name"], "error": str(e)})

    summary = (f"Gumroad: {created} erstellt, {updated} aktualisiert, "
               f"{files_uploaded} PDFs hochgeladen, {len(errors)} Fehler")
    log.info(summary)
    return {
        "platform": "gumroad",
        "ok": True,
        "created": created,
        "updated": updated,
        "files_uploaded": files_uploaded,
        "errors": errors,
        "summary": summary,
    }


# ─── 6. Stripe: Produkt-Katalog synchronisieren ──────────────────────────────

STRIPE_PRODUCTS = [
    {"name": "SuperMegaBot Starter", "price_eur": 4900,
     "description": "SuperMegaBot Starter-Plan: 5 Automation-Tasks, Shopify-Sync, Basis-AI."},
    {"name": "SuperMegaBot Pro", "price_eur": 9900,
     "description": "Pro-Plan: Alle 400+ Tasks, Multi-Platform, AI-Content, Priority Support."},
    {"name": "SuperMegaBot Enterprise", "price_eur": 29900,
     "description": "Enterprise: Unbegrenzte Nutzung, Custom AI-Training, Dedicated Support, White Label."},
]


async def run_stripe_catalog_sync() -> dict:
    """Stripe: Fehlende Produkte anlegen, alle Felder ausfüllen."""
    if not STRIPE_KEY:
        return {"platform": "stripe", "ok": False, "error": "no STRIPE_SECRET_KEY"}
    try:
        import stripe
        stripe.api_key = STRIPE_KEY
        _prod_list = stripe.Product.list(limit=100, active=True)
        _prods = _prod_list.data if hasattr(_prod_list, "data") else _prod_list.get("data", [])
        existing = {p["name"]: p for p in _prods}
        created = updated = 0
        for prod in STRIPE_PRODUCTS:
            ex = existing.get(prod["name"])
            if ex:
                stripe.Product.modify(ex["id"],
                    description=prod["description"],
                    metadata={"source": "supermegabot", "plan": prod["name"].lower().replace(" ", "_")})
                updated += 1
            else:
                new_prod = stripe.Product.create(
                    name=prod["name"],
                    description=prod["description"],
                    metadata={"source": "supermegabot"},
                )
                stripe.Price.create(
                    product=new_prod["id"],
                    unit_amount=prod["price_eur"],
                    currency="eur",
                    recurring={"interval": "month"},
                    metadata={"plan": prod["name"]},
                )
                created += 1
                log.info("Stripe Produkt angelegt: %s (€%.2f/mo)",
                         prod["name"], prod["price_eur"] / 100)
        return {"platform": "stripe", "ok": True,
                "created": created, "updated": updated}
    except ImportError:
        return {"platform": "stripe", "ok": False, "error": "stripe package not installed"}
    except Exception as e:
        log.warning("Stripe sync: %s", e)
        return {"platform": "stripe", "ok": False, "error": str(e)}


# ─── 7. DS24: Auto-Approve inaktive Produkte ────────────────────────────────

async def run_ds24_approve() -> dict:
    """DS24: Inaktive Produkte aktivieren."""
    try:
        from modules.ds24_autonomous_agent import approve_ds24_pending_products
        result = await approve_ds24_pending_products()
        return {"platform": "ds24", "ok": True, **result}
    except Exception as e:
        return {"platform": "ds24", "ok": False, "error": str(e)}


# ─── 8. Shopify: AI-Beschreibungen für leere Produkte ───────────────────────

async def run_shopify_description_fill(limit: int = 20) -> dict:
    """Shopify: Leere body_html mit KI-Beschreibungen füllen."""
    try:
        from modules.shopify_description_filler import fill_empty_descriptions
        result = await fill_empty_descriptions(limit=limit)
        return {"platform": "shopify_descriptions", "ok": True, "result": result}
    except Exception as e:
        return {"platform": "shopify_descriptions", "ok": False, "error": str(e)}


# ─── MASTER CYCLE: Alle Plattformen parallel ────────────────────────────────

async def run_mega_autonomy_cycle() -> dict:
    """
    Vollautonomer Master-Zyklus — alle Plattformen parallel.
    Kein Spam, keine BrutusCore-Posts — nur echte Plattform-Arbeit.
    """
    start = time.time()
    log.info("MegaAutonomy: Zyklus startet — alle Plattformen...")

    tasks = [
        ("ebay",           run_ebay_import(count=3)),
        ("amazon",         run_amazon_affiliate_research()),
        ("aliexpress",     run_aliexpress_import(count=3)),
        ("klaviyo",        run_klaviyo_campaign()),
        ("ds24",           run_ds24_approve()),
        ("shopify_desc",   run_shopify_description_fill(limit=15)),
    ]

    results = {}
    coros = [(name, coro) for name, coro in tasks]
    done = await asyncio.gather(*[c for _, c in coros], return_exceptions=True)
    for (name, _), result in zip(coros, done):
        if isinstance(result, Exception):
            results[name] = {"ok": False, "error": str(result)}
        else:
            results[name] = result

    elapsed = round(time.time() - start, 1)

    # Zusammenfassung bauen
    imported = sum([
        results.get("ebay", {}).get("imported", 0),
        results.get("aliexpress", {}).get("imported", 0),
    ])
    summary_parts = []
    if imported:
        summary_parts.append(f"🛒 {imported} neue Produkte importiert")
    amazon_found = results.get("amazon", {}).get("found", 0)
    if amazon_found:
        summary_parts.append(f"📦 Amazon: {amazon_found} Bestseller analysiert")
    ds24_activated = results.get("ds24", {}).get("activated", 0)
    if ds24_activated:
        summary_parts.append(f"✅ DS24: {ds24_activated} Produkte aktiviert")

    if summary_parts:
        msg = "🤖 <b>MegaAutonomy Zyklus</b>\n" + "\n".join(summary_parts)
        await _tg(msg)

    # Cache für Dashboard
    report = {
        "timestamp": int(time.time()),
        "elapsed_s": elapsed,
        "results": results,
        "imported": imported,
        "summary": "; ".join(summary_parts) if summary_parts else "Kein neuer Import",
    }
    (DATA_DIR / "mega_autonomy_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )

    log.info("MegaAutonomy: Zyklus fertig in %.1fs — %s",
             elapsed, report["summary"])
    return report


async def run_gumroad_full_setup() -> dict:
    """Einmalig: Alle Gumroad-Produkte vollständig einrichten + PDFs hochladen."""
    result = await run_gumroad_setup()
    if result.get("ok"):
        msg = (f"🎁 <b>Gumroad Setup fertig</b>\n"
               f"• {result['created']} erstellt\n"
               f"• {result['updated']} aktualisiert\n"
               f"• {result['files_uploaded']} PDFs hochgeladen")
        await _tg(msg)
    return result


async def run_stripe_full_sync() -> dict:
    """Einmalig: Stripe Produkt-Katalog vollständig synchronisieren."""
    result = await run_stripe_catalog_sync()
    if result.get("ok"):
        msg = (f"💳 <b>Stripe Sync fertig</b>\n"
               f"• {result.get('created', 0)} Produkte angelegt\n"
               f"• {result.get('updated', 0)} aktualisiert")
        await _tg(msg)
    return result


def get_mega_autonomy_status() -> dict:
    """Dashboard-Status."""
    report_file = DATA_DIR / "mega_autonomy_report.json"
    if report_file.exists():
        try:
            return json.loads(report_file.read_text())
        except Exception:
            pass
    return {"status": "no_data"}
