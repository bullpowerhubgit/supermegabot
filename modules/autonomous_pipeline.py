#!/usr/bin/env python3
"""
Vollautonome Produkt-Pipeline
==============================
Kein einziger manueller Schritt. Komplett selbstständig:

1. GENERIEREN  — KI erstellt Produkte (DS24, Shopify, Gumroad)
2. SORTIEREN   — automatisch in Kategorien/Collections
3. BUNDELN     — KI erstellt Bundles aus Einzelprodukten
4. POSTEN      — BrutusCore blasted auf alle 12 Kanäle
5. VERKAUFEN   — Stripe/DS24 Checkout, automatische Preisoptimierung
6. ABBUCHEN    — Stripe Webhooks → Supabase → Telegram-Alert
7. OPTIMIEREN  — KI analysiert was verkauft, skaliert Best-Seller

Läuft täglich vollautomatisch via Scheduler.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("AutonomousPipeline")

SHOPIFY_SHOP  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER   = os.getenv("SHOPIFY_API_VERSION", "2026-04")
DS24_KEY      = os.getenv("DS24_API_KEY", "")
AFFILIATE_ID  = os.getenv("DS24_AFFILIATE_ID", "user37405262")
STRIPE_KEY    = os.getenv("STRIPE_SECRET_KEY", "")


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _shopify_post(path: str, data: dict) -> dict:
    if not SHOPIFY_SHOP or not SHOPIFY_TOKEN:
        return {"error": "no shopify credentials"}
    try:
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_VER}{path}"
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                json=data,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def _shopify_get(path: str, params: dict = None) -> dict:
    if not SHOPIFY_SHOP or not SHOPIFY_TOKEN:
        return {}
    try:
        url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_VER}{path}"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


# ─── STUFE 1: GENERIEREN ─────────────────────────────────────────────────────

PRODUCT_NICHES = [
    ("KI & Automation", ["KI-Tool", "Automation-Guide", "ChatGPT-Kurs", "Prompt Engineering"]),
    ("Business & Geld", ["Business-Plan", "Passives Einkommen", "Freelancing", "E-Commerce"]),
    ("Gesundheit & Fitness", ["Ernährungs-Guide", "Workout-Plan", "Mindset-Coaching", "Schlaf-Optimierung"]),
    ("Marketing & Traffic", ["SEO-Guide", "Social Media Kit", "Email-Marketing", "Content-Strategie"]),
    ("Persönlichkeit", ["Produktivitäts-System", "Habit-Tracker", "Zeitmanagement", "Mindfulness"]),
]


async def generate_product_idea(niche: str, product_type: str) -> dict:
    """KI generiert vollständige Produktidee mit Preis + Beschreibung."""
    prompt = (
        f"Erstelle ein digitales Produkt für DS24/Shopify. Nische: {niche}, Typ: {product_type}.\n"
        f"Antworte NUR mit JSON (kein Markdown):\n"
        f'{{\"name\": \"Produktname (max 60 Zeichen)\", '
        f'\"description\": \"Kurzbeschreibung (2 Sätze)\", '
        f'\"price\": 47, '
        f'\"tags\": [\"tag1\", \"tag2\", \"tag3\"], '
        f'\"category\": \"{niche}\"}}'
    )
    raw = await _ai(prompt, 200)
    try:
        import json
        import re
        m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.warning("Ignored error: %s", e)
    return {
        "name": f"{product_type} — {niche} Guide 2026",
        "description": f"Schritt-für-Schritt Anleitung zu {niche}. Sofort umsetzbar.",
        "price": random.choice([27, 37, 47, 67, 97]),
        "tags": [niche.lower(), product_type.lower(), "digital"],
        "category": niche,
    }


async def create_shopify_product(idea: dict) -> Optional[str]:
    """Erstellt Shopify-Produkt aus Idee. Gibt product_id zurück."""
    from modules.product_gatekeeper import validate_product
    ok, reason = validate_product(
        title=idea.get("name", ""),
        vendor="iNeedit",
        product_type=idea.get("category", ""),
        price=float(idea.get("price", 0)),
    )
    if not ok:
        log.warning("Gatekeeper blockiert Produkt: %s — %s", idea.get("name","")[:50], reason)
        return None

    img_url = ""
    payload = {
        "product": {
            "title": idea["name"],
            "body_html": f"<p>{idea['description']}</p>",
            "vendor": "iNeedit",
            "product_type": idea.get("category", "Smart Gadget"),
            "tags": ",".join(idea.get("tags", [])),
            "status": "active",
            "variants": [{
                "price": str(idea.get("price", 47)),
                "requires_shipping": False,
                "inventory_management": None,
            }],
            "images": [{"src": img_url}],
        }
    }
    result = await _shopify_post("/products.json", payload)
    pid = result.get("product", {}).get("id")
    if pid:
        log.info("Shopify Produkt erstellt: %s (id=%s)", idea["name"][:40], pid)
    return str(pid) if pid else None


# ─── STUFE 2: SORTIEREN ──────────────────────────────────────────────────────

async def auto_sort_into_collections(product_ids: list, category: str) -> dict:
    """Legt Collection an (oder nutzt bestehende) und fügt Produkte hinzu."""
    if not product_ids:
        return {"ok": False, "error": "no products"}

    # Collection suchen oder erstellen
    cols = await _shopify_get("/custom_collections.json", {"title": category, "limit": 1})
    existing = cols.get("custom_collections", [])
    if existing:
        col_id = existing[0]["id"]
    else:
        r = await _shopify_post("/custom_collections.json", {
            "custom_collection": {
                "title": category,
                "published": True,
                "sort_order": "best-selling",
            }
        })
        col_id = r.get("custom_collection", {}).get("id")
        if not col_id:
            return {"ok": False, "error": "collection creation failed"}

    # Produkte hinzufügen
    added = 0
    for pid in product_ids:
        r = await _shopify_post("/collects.json", {
            "collect": {"product_id": int(pid), "collection_id": col_id}
        })
        if r.get("collect"):
            added += 1
        await asyncio.sleep(0.2)

    return {"ok": True, "collection_id": col_id, "added": added, "category": category}


# ─── STUFE 3: BUNDELN ────────────────────────────────────────────────────────

async def create_bundle(products: list, bundle_name: str = "") -> dict:
    """Erstellt ein Bundle aus mehreren Produkten als neue Collection + Discount."""
    if len(products) < 2:
        return {"ok": False, "error": "need at least 2 products for bundle"}

    # Bundle-Name generieren
    if not bundle_name:
        names = [p.get("name", p.get("title", ""))[:20] for p in products[:3]]
        bundle_name = await _ai(
            f"Kurzer Bundle-Name (max 40 Zeichen) für: {', '.join(names)}. Auf Deutsch.",
            max_tokens=30,
        ) or f"Bundle {len(products)}er Paket"

    # Bundle als Collection
    col_result = await _shopify_post("/custom_collections.json", {
        "custom_collection": {
            "title": bundle_name[:100],
            "published": True,
            "body_html": f"<p>Exklusives Bundle: Spare 20% wenn du alle {len(products)} Produkte zusammen kaufst.</p>",
        }
    })
    col_id = col_result.get("custom_collection", {}).get("id")
    if not col_id:
        return {"ok": False, "error": "bundle collection failed"}

    # Produkte in Bundle
    product_ids = [str(p.get("id", p.get("product_id", ""))) for p in products if p.get("id") or p.get("product_id")]
    added = 0
    for pid in product_ids:
        if pid:
            r = await _shopify_post("/collects.json", {
                "collect": {"product_id": int(pid), "collection_id": col_id}
            })
            if r.get("collect"):
                added += 1
            await asyncio.sleep(0.2)

    # Discount-Code für Bundle (20% Rabatt)
    total_price = sum(float(p.get("price", 47)) for p in products)
    discount_result = await _shopify_post("/price_rules.json", {
        "price_rule": {
            "title": f"BUNDLE{len(products)}ER",
            "target_type": "line_item",
            "target_selection": "all",
            "allocation_method": "across",
            "value_type": "percentage",
            "value": "-20.0",
            "customer_selection": "all",
            "starts_at": datetime.now(timezone.utc).isoformat(),
        }
    })
    price_rule_id = discount_result.get("price_rule", {}).get("id")
    discount_code = ""
    if price_rule_id:
        dc = await _shopify_post(f"/price_rules/{price_rule_id}/discount_codes.json", {
            "discount_code": {"code": f"BUNDLE{len(products)}ER"}
        })
        discount_code = dc.get("discount_code", {}).get("code", "")

    return {
        "ok": True,
        "bundle_name": bundle_name,
        "collection_id": col_id,
        "products_added": added,
        "discount_code": discount_code,
        "original_value": total_price,
        "bundle_value": round(total_price * 0.8, 2),
    }


# ─── STUFE 4: POSTEN ─────────────────────────────────────────────────────────

async def blast_product(product: dict, discount_code: str = "") -> dict:
    """BrutusCore blasted Produkt auf alle Kanäle."""
    name  = product.get("name", product.get("title", "Neues Produkt"))
    price = product.get("price", "47")
    shop  = os.getenv("SHOPIFY_SHOP_URL", f"https://{SHOPIFY_SHOP}")
    link  = product.get("link", shop)

    content_prompt = (
        f"Schreibe einen kurzen (3 Sätze) deutschen Marketing-Post für: '{name}', Preis €{price}.\n"
        f"Emotional, überzeugend. CTA am Ende. Link: {link}"
    )
    content = await _ai(content_prompt, 120) or f"Neues Produkt: {name} — Jetzt für nur €{price}! {link}"

    if discount_code:
        content += f"\n🎁 Spare 20% mit Code: {discount_code}"

    try:
        from modules.brutus_core import fire
        result = await fire(name, content, link=link,
                            channels=["telegram", "slack", "discord", "mailchimp", "klaviyo", "shopify_blog"])
        return {"ok": True, "blasted": True, "channels": 6}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── STUFE 5+6: VERKAUFEN + ABBUCHEN (Stripe) ────────────────────────────────

async def create_stripe_payment_link(product: dict) -> dict:
    """Erstellt automatisch einen Stripe Payment Link für ein Produkt."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "no STRIPE_SECRET_KEY"}
    try:
        price = float(product.get("price", 47))
        name  = product.get("name", product.get("title", "Produkt"))[:100]

        async with aiohttp.ClientSession() as s:
            # Price Object erstellen
            async with s.post(
                "https://api.stripe.com/v1/prices",
                auth=aiohttp.BasicAuth(STRIPE_KEY, ""),
                data={
                    "currency": "eur",
                    "unit_amount": str(int(price * 100)),
                    "product_data[name]": name,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                price_obj = await r.json()
            price_id = price_obj.get("id")
            if not price_id:
                return {"ok": False, "error": str(price_obj)[:200]}

            # Payment Link (Redirect-URL via stripe_guards → nie url_invalid)
            from modules.stripe_guards import build_thank_you_url, sanitize_post_data
            _thanks = (
                os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/")
                + "/api/ds24/dankeseite"
            )
            _plink = sanitize_post_data("/payment_links", {
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "after_completion[type]": "redirect",
                "after_completion[redirect][url]": build_thank_you_url(
                    _thanks, product_name=name
                ),
            })
            async with s.post(
                "https://api.stripe.com/v1/payment_links",
                auth=aiohttp.BasicAuth(STRIPE_KEY, ""),
                data=_plink,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r2:
                link_obj = await r2.json()

        pay_link = link_obj.get("url", "")
        return {"ok": True, "payment_link": pay_link, "price_id": price_id, "price_eur": price}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── STUFE 7: OPTIMIEREN ─────────────────────────────────────────────────────

async def analyze_and_scale_bestsellers() -> dict:
    """Analysiert Shopify-Verkäufe und skaliert Best-Seller automatisch."""
    try:
        # Top-Produkte nach Verkäufen
        orders = await _shopify_get("/orders.json", {"status": "paid", "limit": 50})
        order_list = orders.get("orders", [])

        product_sales: dict = {}
        for order in order_list:
            for item in order.get("line_items", []):
                pid = str(item.get("product_id", ""))
                product_sales[pid] = product_sales.get(pid, 0) + item.get("quantity", 1)

        top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:5]

        scaled = 0
        for pid, sales in top_products:
            if sales >= 2:
                # Blast Top-Seller auf extra Kanäle
                await blast_product({"id": pid, "name": f"Bestseller #{pid}", "price": "47"})
                scaled += 1

        return {
            "ok": True,
            "total_orders": len(order_list),
            "unique_products": len(product_sales),
            "top_products": top_products[:5],
            "scaled_campaigns": scaled,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── VOLLSTÄNDIGER PIPELINE-ZYKLUS ───────────────────────────────────────────

async def run_full_pipeline(products_per_niche: int = 3) -> dict:
    """
    Vollständiger Pipeline-Durchlauf (täglich im Scheduler):
    Generieren → Sortieren → Bundeln → Posten → Stripe-Links → Analysieren
    """
    log.info("Starte vollautonome Produkt-Pipeline")
    stats = {
        "generated": 0, "sorted": 0, "bundled": 0,
        "blasted": 0, "payment_links": 0, "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    all_shopify_ids: list = []
    niche_products: dict = {}

    # STUFE 1+2+3: Pro Nische Produkte generieren + sortieren
    for niche_name, product_types in PRODUCT_NICHES:
        created_this_niche: list = []

        for ptype in product_types[:products_per_niche]:
            idea = await generate_product_idea(niche_name, ptype)
            pid = await create_shopify_product(idea)
            if pid:
                stats["generated"] += 1
                all_shopify_ids.append(pid)
                created_this_niche.append({"id": pid, "name": idea["name"], "price": idea.get("price", 47)})

                # STUFE 4: Sofort blasten
                blast = await blast_product(idea)
                if blast.get("ok"):
                    stats["blasted"] += 1

                # STUFE 5: Stripe Payment Link
                if STRIPE_KEY:
                    stripe_link = await create_stripe_payment_link(idea)
                    if stripe_link.get("ok"):
                        stats["payment_links"] += 1

                await asyncio.sleep(0.5)

        # STUFE 2: In Collection sortieren
        if created_this_niche:
            sort_result = await auto_sort_into_collections(
                [p["id"] for p in created_this_niche], niche_name
            )
            if sort_result.get("ok"):
                stats["sorted"] += sort_result.get("added", 0)
            niche_products[niche_name] = created_this_niche

        await asyncio.sleep(1.0)

    # STUFE 3: Bundles aus je Nische
    for niche_name, products in niche_products.items():
        if len(products) >= 2:
            bundle = await create_bundle(products[:3], f"{niche_name} Bundle")
            if bundle.get("ok"):
                stats["bundled"] += 1
                # Bundle auch blasten
                await blast_product(
                    {"name": bundle["bundle_name"], "price": bundle["bundle_value"]},
                    discount_code=bundle.get("discount_code", ""),
                )

    # STUFE 7: Best-Seller skalieren
    scale_result = await analyze_and_scale_bestsellers()

    # Telegram-Abschlussbericht
    try:
        from modules.brutus_core import fire
        await fire(
            "🚀 Pipeline-Zyklus abgeschlossen!",
            f"Generiert: {stats['generated']} Produkte\n"
            f"Sortiert: {stats['sorted']} in Collections\n"
            f"Bundles: {stats['bundled']}\n"
            f"Geblastet: {stats['blasted']}\n"
            f"Stripe Links: {stats['payment_links']}\n"
            f"Best-Seller skaliert: {scale_result.get('scaled_campaigns', 0)}",
            channels=["telegram"],
        )
    except Exception as e:
        log.warning("Ignored error: %s", e)

    log.info("Pipeline abgeschlossen: %s", stats)
    return {"ok": True, **stats, "scale": scale_result}


async def run_pipeline_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    if os.getenv("SOCIAL_POSTING_PAUSED", "").lower() in ("1", "true", "yes"):
        log.warning("AutonomousPipeline: SOCIAL_POSTING_PAUSED=true — übersprungen")
        return {"ok": False, "skipped": True, "reason": "SOCIAL_POSTING_PAUSED"}
    return await run_full_pipeline(products_per_niche=2)
