#!/usr/bin/env python3
"""
DS24 Marktplatz-Automatisierung
================================
1. Scannt DS24-Marktplatz nach Top-Produkten (30%+ Provision)
2. Bewirbt automatisch um Affiliate-Status
3. Alle genehmigten Produkte → BrutusCore-Blast auf alle Kanäle
4. Supabase-Tracking aller Bewerbungen + Genehmigungen
5. Tägliche KI-Analyse: welche Nischen performen am besten
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("DS24MarketplaceAuto")

DS24_KEY      = os.getenv("DS24_API_KEY", "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N")
AFFILIATE_ID  = os.getenv("DS24_AFFILIATE_ID", "user37405262")
ACCOUNT_ID    = DS24_KEY.split("-")[0] if "-" in DS24_KEY else "1581233"
DS24_BASE     = "https://www.digistore24.com/api/call"

# Nischen die automatisch gescannt werden
TARGET_NICHES = [
    "ki", "künstliche intelligenz", "ai", "geld verdienen",
    "online business", "affiliate", "software", "coaching",
    "mindset", "fitness", "abnehmen", "ecommerce", "shopify",
    "copywriting", "social media", "youtube", "tiktok",
    "finanzen", "krypto", "immobilien", "trading",
]

# Mindest-Provision für Auto-Bewerbung
MIN_COMMISSION_PCT = 30.0


async def _ds24_get(endpoint: str, params: dict = None) -> dict:
    url = f"{DS24_BASE}/{endpoint}/?format=json"
    if params:
        url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"X-DS-API-KEY": DS24_KEY},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"result": "error", "message": str(e)}


async def _ds24_post(endpoint: str, data: dict) -> dict:
    url = f"{DS24_BASE}/{endpoint}/?format=json"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                headers={"X-DS-API-KEY": DS24_KEY, "Content-Type": "application/json"},
                json=data,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"result": "error", "message": str(e)}


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def scan_marketplace(niche: str = "", limit: int = 20) -> list:
    """DS24-Marktplatz scannen — Top-Produkte nach Provision."""
    results = []
    keywords = [niche] if niche else TARGET_NICHES[:8]

    for kw in keywords:
        data = await _ds24_get("listMarketplaceProducts", {
            "search": kw,
            "language": "de",
            "limit": 50,
        })
        products = (
            data.get("data", {}).get("products", []) or
            data.get("data", {}).get("product_list", []) or
            []
        )
        for p in products:
            commission = float(p.get("affiliate_commission_percentage", 0) or
                               p.get("affiliate_commission", 0) or 0)
            if commission < MIN_COMMISSION_PCT:
                continue
            pid = str(p.get("id", p.get("product_id", "")))
            if not pid:
                continue
            results.append({
                "product_id":   pid,
                "name":         p.get("name", p.get("title", ""))[:80],
                "price":        float(p.get("price", 0) or 0),
                "currency":     p.get("currency", "EUR"),
                "commission":   commission,
                "vendor":       p.get("owner_name", p.get("vendor", ""))[:50],
                "niche":        kw,
                "checkout_url": p.get("orderform_customer_url", ""),
                "affiliate_link": (
                    f"https://www.checkout-ds24.com/redir/{pid}/{AFFILIATE_ID}/"
                ),
            })
        await asyncio.sleep(0.3)

    # Deduplizieren + sortieren
    seen = set()
    unique = []
    for p in sorted(results, key=lambda x: x["commission"], reverse=True):
        if p["product_id"] not in seen:
            seen.add(p["product_id"])
            unique.append(p)
    return unique[:limit]


async def apply_for_affiliate(product_id: str, message: str = "") -> dict:
    """Bewirbt sich automatisch für Affiliate-Status eines Produkts."""
    if not message:
        message = (
            "Hallo, ich betreibe einen erfolgreichen Marketing-Kanal "
            "(bullpowerhub.com) mit starker Zielgruppe im Bereich Online-Business. "
            "Ich möchte gerne Ihr Produkt als Affiliate vermarkten und bin überzeugt, "
            "dass ich Ihnen hochwertige Verkäufe bringen kann. "
            "Ich arbeite mit E-Mail-Marketing, Social Media und SEO."
        )
    result = await _ds24_post("requestAffiliate", {
        "product_id": product_id,
        "message":    message,
    })
    success = result.get("result") == "success"
    return {
        "ok":         success,
        "product_id": product_id,
        "result":     result.get("result", ""),
        "message":    result.get("message", str(result)[:200]),
    }


async def _save_application(product: dict, status: str) -> None:
    try:
        from modules.supabase_client import get_client
        get_client().table("ds24_affiliate_applications").upsert({
            "product_id":  product["product_id"],
            "name":        product.get("name", ""),
            "commission":  product.get("commission", 0),
            "vendor":      product.get("vendor", ""),
            "niche":       product.get("niche", ""),
            "status":      status,
            "applied_at":  datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.debug("Supabase save failed: %s", e)


async def auto_apply_batch(products: list) -> dict:
    """Bewirbt sich auf alle übergebenen Produkte."""
    applied = 0
    failed  = 0
    already = 0

    for p in products:
        # KI-generierte Bewerbungsnachricht pro Produkt
        msg = await _ai(
            f"Schreibe eine kurze (3 Sätze) deutsche Affiliate-Bewerbung für das DS24-Produkt "
            f"'{p['name']}' von {p.get('vendor','dem Anbieter')}. "
            f"Professionell, überzeugend, erkläre meinen Marketing-Kanal BullPowerHub.",
            max_tokens=120,
        )
        result = await apply_for_affiliate(p["product_id"], msg)
        if result.get("ok"):
            applied += 1
            await _save_application(p, "applied")
            log.info("Affiliate-Bewerbung OK: %s (%s)", p["product_id"], p["name"][:40])
        elif "already" in result.get("message", "").lower():
            already += 1
            await _save_application(p, "already_applied")
        else:
            failed += 1
            await _save_application(p, "failed")
            log.warning("Bewerbung fehlgeschlagen: %s — %s", p["product_id"], result.get("message","")[:80])
        await asyncio.sleep(1.0)

    return {"applied": applied, "failed": failed, "already_applied": already}


MAX_BLASTS_PER_DAY = 3  # Maximal 3 DS24-Posts pro Tag — kein Spam!

async def _ds24_link_ok(link: str) -> bool:
    """Prüft ob DS24-Link wirklich kaufbar ist (nicht nur HTTP 200)."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(link, allow_redirects=True,
                             timeout=aiohttp.ClientTimeout(total=8),
                             headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status >= 400:
                    return False
                body = await r.text(errors="ignore")
                bad = ["nicht verkauft werden", "not available for sale",
                       "kann nicht verkauft", "temporarily unavailable",
                       "currently unavailable", "nicht verfügbar"]
                return not any(b in body.lower() for b in bad)
    except Exception:
        return False


async def blast_approved_marketplace_products() -> dict:
    """Holt genehmigte Affiliate-Links + postet MAX 3 pro Tag mit Link-Check."""
    import json, hashlib
    from pathlib import Path
    state_file = Path(__file__).parent.parent / "data" / "ds24_blast_state.json"
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        state = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent_today = state.get("date") == today and state.get("count", 0) or 0

    if sent_today >= MAX_BLASTS_PER_DAY:
        log.info("DS24 Blast: Tageslimit %d erreicht — übersprungen", MAX_BLASTS_PER_DAY)
        return {"ok": True, "blasted": 0, "reason": "daily_limit_reached", "sent_today": sent_today}

    data = await _ds24_get("listAffiliateLinks")
    links = (
        data.get("data", {}).get("affiliate_links", []) or
        data.get("data", {}).get("products", []) or
        []
    )
    approved = [p for p in links if p.get("approval_status", "approved") in ("approved", "")]
    blasted = 0

    for p in approved[:10]:
        if sent_today + blasted >= MAX_BLASTS_PER_DAY:
            break
        pid = str(p.get("product_id", p.get("id", "")))
        name = p.get("name", p.get("title", f"Produkt #{pid}"))[:60]
        link = f"https://www.checkout-ds24.com/redir/{pid}/{AFFILIATE_ID}/"
        commission = float(p.get("affiliate_commission_percentage", 0) or 0)

        # Link-Check BEVOR wir posten!
        if not await _ds24_link_ok(link):
            log.warning("DS24 Produkt %s nicht verfügbar — übersprungen", pid)
            continue

        content = await _ai(
            f"Kurzer überzeugender Affiliate-Post (3 Sätze, deutsch) für: {name}. "
            f"Provision {commission}%. Link: {link}",
            max_tokens=100,
        ) or f"Top Empfehlung: {name} — {commission}% Provision. Jetzt ansehen: {link}"

        try:
            from modules.brutus_core import fire
            await fire(name, content, link=link,
                       channels=["telegram", "slack"])
            blasted += 1
        except Exception as e:
            log.warning("Blast error %s: %s", pid, e)
        await asyncio.sleep(5.0)

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"date": today, "count": sent_today + blasted}))
    return {"ok": True, "blasted": blasted, "total_approved": len(approved)}


async def run_full_marketplace_cycle() -> dict:
    """
    Vollständiger Zyklus (täglich im Scheduler):
    1. Marktplatz scannen
    2. Auf alle Top-Produkte bewerben
    3. Genehmigte Produkte blasten
    4. Telegram-Bericht
    """
    log.info("Starte DS24 Marktplatz-Zyklus")

    # 1. Scannen
    products = await scan_marketplace(limit=30)
    log.info("Gescannt: %d Produkte mit 30%%+ Provision", len(products))

    # 2. Bewerben
    apply_result = await auto_apply_batch(products)

    # 3. Blast
    blast_result = await blast_approved_marketplace_products()

    # 4. Telegram-Report
    try:
        from modules.brutus_core import fire
        await fire(
            "📊 DS24 Marktplatz-Report",
            f"Gescannt: {len(products)} Produkte\n"
            f"Bewerbungen: {apply_result['applied']} neu, "
            f"{apply_result['already_applied']} schon beworben\n"
            f"Geblastet: {blast_result['blasted']} genehmigte Produkte",
            channels=["telegram"],
        )
    except Exception:
        pass

    return {
        "ok":         True,
        "scanned":    len(products),
        "applied":    apply_result["applied"],
        "already":    apply_result["already_applied"],
        "failed":     apply_result["failed"],
        "blasted":    blast_result.get("blasted", 0),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


async def get_marketplace_stats() -> dict:
    """Statistiken: Bewerbungen, Genehmigungen, Revenue aus Supabase."""
    try:
        from modules.supabase_client import get_client
        apps = get_client().table("ds24_affiliate_applications").select("*").execute()
        rows = apps.data or []
        by_status = {}
        by_niche  = {}
        for r in rows:
            s = r.get("status", "unknown")
            n = r.get("niche", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
            by_niche[n]  = by_niche.get(n, 0) + 1

        purchases = get_client().table("ds24_purchases").select("price").execute()
        total_revenue = sum(float(p.get("price", 0) or 0) for p in (purchases.data or []))

        return {
            "ok":            True,
            "total_applications": len(rows),
            "by_status":    by_status,
            "by_niche":     by_niche,
            "total_revenue_eur": round(total_revenue, 2),
            "recent_applied": [
                {"id": r["product_id"], "name": r.get("name","")[:40],
                 "commission": r.get("commission",0), "status": r.get("status","")}
                for r in sorted(rows, key=lambda x: x.get("applied_at",""), reverse=True)[:10]
            ],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_marketplace_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    return await run_full_marketplace_cycle()
