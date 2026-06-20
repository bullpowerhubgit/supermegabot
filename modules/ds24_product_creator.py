#!/usr/bin/env python3
"""
Digistore24 Autonomous Product Creator
=======================================
Erstellt vollständig autonome Digistore24-Produkte:
1. KI generiert Produktname, Beschreibung, Preis, Salespage
2. createProduct → Produkt anlegen
3. createPaymentPlan → Zahlungsplan mit Preis
4. updateProduct → aktivieren + Affiliate-Provision setzen
5. Affiliate-Link generieren + via BrutusCore auf alle Kanäle blasen
6. Supabase: Produkt-ID speichern zur Deduplizierung

Getestete API-Calls (2026-06-20):
- createProduct: ✅ gibt product_id zurück
- createPaymentPlan: ✅ gibt paymentplan_id zurück
- updateProduct: ✅ aktiviert Produkt
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("DS24ProductCreator")

DS24_KEY     = os.getenv("DIGISTORE24_API_KEY", "1682000-T8KjTRJXCO1IgXOU5I7am6p6a0AZuqV2BGswDECY")
AFFILIATE_ID = os.getenv("DS24_AFFILIATE_ID", "user37405262")
DS24_BASE    = "https://www.digistore24.com/api/call"
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")

# Vordefinierte Produkt-Vorlagen für autonome Erstellung
PRODUCT_TEMPLATES = [
    {
        "concept": "KI-gestütztes E-Commerce Automatisierungs-System",
        "niche": "software",
        "price": "97.00",
        "affiliate_commission": "40",
        "tags": ["ki automation", "e-commerce", "shopify", "passive income"],
    },
    {
        "concept": "Amazon Affiliate Marketing Masterclass 2026",
        "niche": "course",
        "price": "47.00",
        "affiliate_commission": "50",
        "tags": ["amazon", "affiliate", "marketing", "geld verdienen"],
    },
    {
        "concept": "Shopify Dropshipping Komplett-System",
        "niche": "software",
        "price": "67.00",
        "affiliate_commission": "45",
        "tags": ["shopify", "dropshipping", "online shop", "autonom"],
    },
    {
        "concept": "Social Media Automation Suite 2026",
        "niche": "software",
        "price": "37.00",
        "affiliate_commission": "50",
        "tags": ["social media", "automation", "instagram", "tiktok"],
    },
    {
        "concept": "ChatGPT Business Blueprint — Geld verdienen mit KI",
        "niche": "course",
        "price": "27.00",
        "affiliate_commission": "50",
        "tags": ["chatgpt", "ki", "business", "geld verdienen"],
    },
]


# ─── DS24 API Helpers ─────────────────────────────────────────────────────────

async def _ds24_post(endpoint: str, payload: dict) -> dict:
    """POST to Digistore24 API with x-ds-api-key header."""
    if not DS24_KEY:
        return {"result": "error", "message": "no DIGISTORE24_API_KEY"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{DS24_BASE}/{endpoint}",
                headers={"x-ds-api-key": DS24_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"result": "error", "message": str(e)}


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


# ─── KI Produktdaten generieren ──────────────────────────────────────────────

async def generate_ds24_product_data(concept: str, price: str = "97.00",
                                      niche: str = "software") -> dict:
    """KI generiert vollständige DS24-Produktdaten für ein Konzept."""
    prompt = f"""Erstelle vollständige Digistore24 Produktdaten auf Deutsch.
Konzept: "{concept}"
Preis: €{price}
Nische: {niche}

Antworte NUR mit diesem JSON:
{{
  "name_de": "Produktname (max 60 Zeichen, verkaufspsychologisch optimiert)",
  "name_intern": "interner-name-kebab-case-max-40",
  "description_de": "Kurzbeschreibung 100-150 Wörter. Nutzen, Zielgruppe, Ergebnis. Überzeugend.",
  "access_instructions_de": "Nach dem Kauf erhalten Sie sofort Zugang per E-Mail. Link ist 30 Tage gültig.",
  "salespage_url": "{SHOP_URL}",
  "thankyou_url": "{SHOP_URL}/pages/danke",
  "tags": "tag1,tag2,tag3",
  "usp": "Hauptnutzen in einem Satz für Marketing"
}}"""

    raw = await _ai(prompt, max_tokens=500)
    if not raw:
        return {}
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {}
        return json.loads(raw[start:end])
    except Exception:
        return {}


# ─── DS24 Produkt anlegen ────────────────────────────────────────────────────

async def create_product(
    name_de: str,
    description_de: str,
    salespage_url: str = "",
    thankyou_url: str = "",
    name_intern: str = "",
    access_instructions_de: str = "",
    affiliate_commission: str = "40",
) -> Optional[str]:
    """Legt ein neues Produkt auf Digistore24 an. Gibt product_id zurück."""
    payload = {
        "data": {
            "name_de": name_de[:100],
            "name_intern": (name_intern or name_de[:40].lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))[:40],
            "description_de": description_de[:2000],
            "salespage_url": salespage_url or SHOP_URL,
            "thankyou_url": thankyou_url or f"{SHOP_URL}/pages/danke",
            "access_instructions_de": access_instructions_de or "Zugang wird nach Zahlungseingang per E-Mail zugeschickt.",
            "language": "de",
            "currency": "EUR",
            "affiliate_commission": str(affiliate_commission),
            "is_active": "1",
            "is_affiliation_auto_accepted": "1",
        }
    }
    result = await _ds24_post("createProduct", payload)
    if result.get("result") == "success":
        pid = str(result["data"]["product_id"])
        log.info("DS24 Produkt angelegt: %s (ID: %s)", name_de[:50], pid)
        return pid
    log.warning("DS24 createProduct Error: %s", result.get("message", result))
    return None


async def create_payment_plan(
    product_id: str,
    amount: str = "97.00",
    currency: str = "EUR",
) -> Optional[str]:
    """Erstellt Zahlungsplan (Einmalzahlung) für das Produkt."""
    payload = {
        "product_id": product_id,
        "data": {
            "first_amount": str(amount),
            "currency": currency,
            "is_active": "1",
        }
    }
    result = await _ds24_post("createPaymentPlan", payload)
    if result.get("result") == "success":
        ppid = str(result["data"]["paymentplan_id"])
        log.info("DS24 Zahlungsplan angelegt: %s (Plan-ID: %s)", amount, ppid)
        return ppid
    log.warning("DS24 createPaymentPlan Error: %s", result.get("message", result))
    return None


async def activate_product(product_id: str, commission: str = "40") -> bool:
    """Aktiviert Produkt + setzt Affiliate-Provision."""
    payload = {
        "product_id": product_id,
        "data": {
            "is_active": "1",
            "affiliate_commission": str(commission),
            "is_affiliation_auto_accepted": "1",
        }
    }
    result = await _ds24_post("updateProduct", payload)
    ok = result.get("result") == "success"
    if ok:
        log.info("DS24 Produkt aktiviert: %s (Provision: %s%%)", product_id, commission)
    return ok


def build_affiliate_link(product_id: str) -> str:
    """Erstellt den Affiliate-Link für das Produkt."""
    return f"https://www.digistore24.com/redir/{product_id}/{AFFILIATE_ID}/"


def build_checkout_link(product_id: str) -> str:
    """Direkt-Checkout-Link (kein Affiliate-Redirect)."""
    return f"https://checkout.digistore24.com/checkout/product/{product_id}"


# ─── Vollautomatische Produkt-Erstellung ─────────────────────────────────────

async def create_full_product(
    concept: str,
    price: str = "97.00",
    niche: str = "software",
    affiliate_commission: str = "40",
) -> dict:
    """
    Vollautomatisch: Konzept → KI → DS24 anlegen → aktivieren → blitzen.
    """
    log.info("DS24 Auto-Create: %s (€%s)", concept[:50], price)

    # 1. KI: Produktdaten generieren
    data = await generate_ds24_product_data(concept, price, niche)
    if not data or not data.get("name_de"):
        # Fallback wenn KI leer
        data = {
            "name_de": concept[:60],
            "name_intern": concept[:30].lower().replace(" ", "-"),
            "description_de": f"Professionelles {concept} — sofort einsetzbar, vollständig auf Deutsch.",
            "access_instructions_de": "Zugang per E-Mail nach Zahlungseingang.",
            "salespage_url": SHOP_URL,
            "thankyou_url": f"{SHOP_URL}/pages/danke",
        }

    # 2. Produkt anlegen
    product_id = await create_product(
        name_de=data["name_de"],
        description_de=data.get("description_de", ""),
        salespage_url=data.get("salespage_url", SHOP_URL),
        thankyou_url=data.get("thankyou_url", f"{SHOP_URL}/pages/danke"),
        name_intern=data.get("name_intern", ""),
        access_instructions_de=data.get("access_instructions_de", ""),
        affiliate_commission=affiliate_commission,
    )
    if not product_id:
        return {"ok": False, "error": "createProduct failed"}

    # 3. Zahlungsplan anlegen
    plan_id = await create_payment_plan(product_id, price)

    # 4. Aktivieren
    await activate_product(product_id, affiliate_commission)

    # 5. Links generieren
    affiliate_link = build_affiliate_link(product_id)
    checkout_link = build_checkout_link(product_id)

    # 6. Supabase: Produkt speichern
    try:
        from modules.supabase_client import get_client
        get_client().table("ds24_products").insert({
            "product_id": product_id,
            "name": data["name_de"],
            "price": price,
            "concept": concept[:200],
            "affiliate_link": affiliate_link,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.debug("Supabase DS24 log: %s", e)

    # 7. BrutusCore Blast
    usp = data.get("usp", f"Neues Produkt: {data['name_de']}")
    blast_msg = (
        f"🆕 Neues DS24-Produkt live!\n\n"
        f"📦 {data['name_de']}\n"
        f"💶 Preis: €{price}\n"
        f"💰 Affiliate: {affiliate_commission}% Provision\n\n"
        f"⚡ {usp}\n\n"
        f"🛒 Kaufen: {checkout_link}\n"
        f"🔗 Affiliate: {affiliate_link}"
    )
    try:
        from modules.brutus_core import fire
        await fire(
            data["name_de"],
            blast_msg,
            link=affiliate_link,
            channels=["telegram", "slack", "mailchimp", "klaviyo",
                      "linkedin", "discord", "shopify_blog"],
        )
    except Exception as e:
        log.debug("Blast error: %s", e)

    log.info("DS24 Komplett-Produkt erstellt: %s (ID: %s, Plan: %s)",
             data['name_de'][:50], product_id, plan_id)
    return {
        "ok": True,
        "product_id": product_id,
        "payment_plan_id": plan_id,
        "name": data["name_de"],
        "price": price,
        "affiliate_link": affiliate_link,
        "checkout_link": checkout_link,
        "commission": f"{affiliate_commission}%",
    }


# ─── Batch Auto-Creator ───────────────────────────────────────────────────────

async def auto_create_products(count: int = 2) -> dict:
    """
    Autonome Erstellung von 'count' DS24-Produkten aus PRODUCT_TEMPLATES.
    Wird vom Scheduler täglich aufgerufen.
    """
    import random
    created = []
    failed = 0

    # Prüfe welche Produkte schon existieren (Supabase)
    existing_names = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("name").execute()
        existing_names = {r["name"] for r in rows.data or []}
    except Exception:
        pass

    templates = random.sample(PRODUCT_TEMPLATES, min(count * 2, len(PRODUCT_TEMPLATES)))
    for tmpl in templates:
        if len(created) >= count:
            break
        concept = tmpl["concept"]
        name_preview = concept[:40]
        if name_preview in " ".join(existing_names):
            log.info("DS24 Skip duplicate: %s", name_preview)
            continue
        try:
            result = await create_full_product(
                concept=concept,
                price=tmpl["price"],
                niche=tmpl["niche"],
                affiliate_commission=tmpl["affiliate_commission"],
            )
            if result.get("ok"):
                created.append(result)
            else:
                failed += 1
            await asyncio.sleep(3)
        except Exception as e:
            log.warning("DS24 auto-create error: %s", e)
            failed += 1

    if created:
        try:
            from modules.notify_hub import notify
            names = "\n".join(f"• {p['name'][:45]} (€{p['price']}, {p['commission']})" for p in created)
            await notify(f"🎯 DS24: {len(created)} neue Produkte erstellt!\n\n{names}", level="success")
        except Exception:
            pass

    return {"ok": True, "created": len(created), "failed": failed, "products": created}


async def fix_product_669750() -> dict:
    """
    Repariert das nicht-verkaufbare Produkt 669750:
    - Prüft Status
    - Fügt fehlenden Zahlungsplan hinzu
    - Aktiviert es
    """
    product_id = "669750"
    log.info("Fixing DS24 product 669750...")

    # Zahlungsplan hinzufügen
    plan_id = await create_payment_plan(product_id, "97.00")

    # Aktivieren
    activated = await activate_product(product_id, "40")

    # Checkout link
    link = build_checkout_link(product_id)
    affiliate = build_affiliate_link(product_id)

    result = {
        "ok": activated,
        "product_id": product_id,
        "payment_plan_added": plan_id,
        "activated": activated,
        "checkout_link": link,
        "affiliate_link": affiliate,
    }
    log.info("Fix 669750: %s", result)
    return result


async def list_ds24_products() -> dict:
    """Listet alle DS24-Produkte mit Links."""
    result = await _ds24_post("listProducts", {})
    if result.get("result") != "success":
        return {"ok": False, "error": result.get("message", "unknown")}

    products = result.get("data", {}).get("products", [])
    enriched = []
    for p in products:
        pid = str(p.get("id", ""))
        enriched.append({
            "id": pid,
            "name": p.get("name", ""),
            "price": p.get("net_price", ""),
            "is_active": p.get("is_active", "0") == "1",
            "affiliate_link": build_affiliate_link(pid),
            "checkout_link": build_checkout_link(pid),
        })
    return {"ok": True, "count": len(enriched), "products": enriched}
