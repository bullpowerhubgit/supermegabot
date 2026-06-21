#!/usr/bin/env python3
"""
DS24 Affiliate Blaster — Alle genehmigten Affiliate-Produkte blasten
======================================================================
Blasted externe Affiliate-Produkte UND eigene aiitec-Produkte (704xxx)
auf Telegram, Slack, Discord, LinkedIn, Shopify Blog, Mailchimp, Klaviyo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone

log = logging.getLogger("DS24AffiliateBlaster")

AFFILIATE_ID = os.getenv("DS24_AFFILIATE_ID", "user37405262")
DS24_API_KEY = os.getenv("DIGISTORE24_API_KEY", "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N")

# ─── Alle 22 genehmigten Affiliate-Produkte (Links von DS24, 2026-06-20) ─────

DS24_APPROVED_PRODUCTS = [
    {"id": "576000", "seller": "wildghosts",
     "link": "https://www.checkout-ds24.com/redir/576000/user37405262/",
     "niche": "lifestyle", "category": "Digital"},
    {"id": "578000", "seller": "Annag-v",
     "link": "https://www.checkout-ds24.com/redir/578000/user37405262/",
     "niche": "coaching", "category": "Digital"},
    {"id": "581000", "seller": "Lisagier",
     "link": "https://www.checkout-ds24.com/redir/581000/user37405262/",
     "niche": "business", "category": "Digital"},
    {"id": "587000", "seller": "Madelaine-DeinSeelenCoach",
     "link": "https://challenge.madelaine-deinseelencoach.de/12-energie-booster/#aff=user37405262",
     "niche": "mindset", "category": "Challenge", "title": "12 Energie-Booster Challenge"},
    {"id": "590000", "seller": "Schoenberghof",
     "link": "https://www.equitao.de/termine/kraeuterwanderung/#aff=user37405262",
     "niche": "nature", "category": "Event", "title": "Kräuterwanderung"},
    {"id": "597000", "seller": "DrMareikeAwe",
     "link": "https://www.checkout-ds24.com/redir/597000/user37405262/",
     "niche": "health", "category": "Digital"},
    {"id": "546000", "seller": "Contemplatio",
     "link": "https://www.checkout-ds24.com/redir/546000/user37405262/",
     "niche": "mindfulness", "category": "Digital"},
    {"id": "558000", "seller": "EdTraMo",
     "link": "https://www.checkout-ds24.com/redir/558000/user37405262/",
     "niche": "education", "category": "Digital"},
    {"id": "560000", "seller": "pixelpioneers",
     "link": "https://goironpump.com/sizepump-tsl-d24/#aff=user37405262",
     "niche": "fitness", "category": "Supplement", "title": "IronPump Size"},
    {"id": "554000", "seller": "crawomarketing",
     "link": "https://www.checkout-ds24.com/redir/554000/user37405262/",
     "niche": "marketing", "category": "Digital"},
    {"id": "570000", "seller": "fusionai",
     "link": "https://www.checkout-ds24.com/redir/570000/user37405262/",
     "niche": "ai", "category": "Digital"},
    {"id": "543000", "seller": "OlivierinChina",
     "link": "https://www.checkout-ds24.com/redir/543000/user37405262/",
     "niche": "travel", "category": "Digital"},
    {"id": "542000", "seller": "ellevol",
     "link": "https://www.checkout-ds24.com/redir/542000/user37405262/",
     "niche": "lifestyle", "category": "Digital"},
    {"id": "685000", "seller": "mvpgroup",
     "link": "https://www.checkout-ds24.com/redir/685000/user37405262/",
     "niche": "business", "category": "Digital"},
    {"id": "690000", "seller": "buzzpjb",
     "link": "https://www.checkout-ds24.com/redir/690000/user37405262/",
     "niche": "marketing", "category": "Digital"},
    {"id": "660000", "seller": "Leuchtling",
     "link": "https://www.checkout-ds24.com/redir/660000/user37405262/",
     "niche": "mindset", "category": "Digital"},
    {"id": "645000", "seller": "DS24-A3OffersEU",
     "link": "https://www.checkout-ds24.com/redir/645000/user37405262/",
     "niche": "business", "category": "Digital"},
    {"id": "650000", "seller": "InstandPro",
     "link": "https://www.checkout-ds24.com/redir/650000/user37405262/",
     "niche": "software", "category": "Digital"},
    {"id": "620000", "seller": "RaphaelZippusch",
     "link": "https://www.checkout-ds24.com/redir/620000/user37405262/",
     "niche": "business", "category": "Digital"},
    {"id": "625000", "seller": "EarLitMedia",
     "link": "https://www.checkout-ds24.com/redir/625000/user37405262/",
     "niche": "media", "category": "Digital"},
    {"id": "630000", "seller": "omclub",
     "link": "https://www.checkout-ds24.com/redir/630000/user37405262/",
     "niche": "mindfulness", "category": "Digital"},
    {"id": "610000", "seller": "Starsirius",
     "link": "https://www.checkout-ds24.com/redir/610000/user37405262/",
     "niche": "lifestyle", "category": "Digital"},
]

# Nischen-Texte für KI-Content-Generierung
NICHE_HOOKS = {
    "ai":          "KI verändert alles — steig jetzt ein!",
    "business":    "Mehr Umsatz, weniger Arbeit — so geht's.",
    "coaching":    "Dein Leben, deine Regeln — mit dem richtigen Coach.",
    "education":   "Wissen ist Macht — und dieser Kurs gibt beides.",
    "fitness":     "Dein Traumkörper ist näher als du denkst.",
    "health":      "Gesundheit ist dein wertvollstes Kapital.",
    "lifestyle":   "Lebe das Leben, das du verdienst.",
    "marketing":   "Mehr Kunden, mehr Umsatz — vollautomatisch.",
    "media":       "Content ist King — werde Publisher.",
    "mindfulness": "Innere Ruhe in 30 Tagen — wissenschaftlich belegt.",
    "mindset":     "Ein einziger Gedanke kann alles verändern.",
    "nature":      "Zurück zur Natur — das Geheimnis der Energie.",
    "software":    "Software die dein Business transformiert.",
    "travel":      "Die Welt entdecken — smart und günstig.",
}


async def _ai(prompt: str, max_tokens: int = 200) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def generate_affiliate_post(product: dict) -> str:
    """KI schreibt einen kurzen deutschen Affiliate-Post."""
    niche = product.get("niche", "business")
    hook = NICHE_HOOKS.get(niche, "Top-Angebot — jetzt sichern!")
    title = product.get("title", f"Top-Produkt #{product['id']}")

    prompt = f"""Schreibe einen kurzen, überzeugenden deutschen Affiliate-Post (3-4 Sätze).
Produkt: {title} (Nische: {niche})
Hook: {hook}
Link: {product['link']}

Format:
Zeile 1: Aufmerksamkeit-Hook (emotional)
Zeile 2-3: Nutzen + Ergebnis
Zeile 4: CTA mit Link

Kein Hashtag, kein Emoji-Spam, max 2 Emojis gesamt. Auf Deutsch."""

    text = await _ai(prompt, max_tokens=150)
    if not text or len(text) < 30:
        text = (f"{hook}\n\n"
                f"Dieses Angebot von {product['seller']} ist genau das Richtige "
                f"für alle die {niche} ernstnehmen.\n\n"
                f"👉 Jetzt ansehen: {product['link']}")
    return text


async def blast_single_product(product: dict, channels: list = None) -> dict:
    """Einen Affiliate-Produkt auf allen Kanälen blasten."""
    try:
        content = await generate_affiliate_post(product)
        title = product.get("title", f"DS24 Empfehlung #{product['id']}")

        from modules.brutus_core import fire
        ch = channels or ["telegram", "slack", "discord", "linkedin",
                          "shopify_blog", "mailchimp", "klaviyo"]
        result = await fire(title, content, link=product["link"], channels=ch)
        log.info("Blasted product %s via %d channels", product["id"], len(ch))
        return {"ok": True, "product_id": product["id"], "channels": len(ch)}
    except Exception as e:
        log.warning("Blast error product %s: %s", product["id"], e)
        return {"ok": False, "error": str(e)}


async def blast_all_approved(delay: float = 2.0) -> dict:
    """Alle 22 genehmigten Affiliate-Produkte blasten — vollautomatisch."""
    blasted = 0
    failed = 0
    results = []

    log.info("Starte Blast von %d genehmigten DS24-Produkten", len(DS24_APPROVED_PRODUCTS))

    # Telegram-Start-Meldung
    try:
        from modules.brutus_core import fire
        await fire(
            "🚀 DS24 Affiliate-Blast gestartet!",
            f"Blaste jetzt {len(DS24_APPROVED_PRODUCTS)} genehmigte Affiliate-Produkte "
            f"auf allen Kanälen.\nLinks wurden von DS24 aktualisiert.",
            channels=["telegram", "slack"]
        )
    except Exception:
        pass

    for product in DS24_APPROVED_PRODUCTS:
        r = await blast_single_product(product)
        if r.get("ok"):
            blasted += 1
        else:
            failed += 1
        results.append(r)
        await asyncio.sleep(delay)

    # Abschluss-Meldung
    try:
        from modules.brutus_core import fire
        await fire(
            f"✅ DS24 Affiliate-Blast abgeschlossen!",
            f"{blasted}/{len(DS24_APPROVED_PRODUCTS)} Produkte erfolgreich auf allen Kanälen.\n"
            f"Affiliate-ID: {AFFILIATE_ID}",
            channels=["telegram", "slack"]
        )
    except Exception:
        pass

    # Supabase loggen
    try:
        from modules.supabase_client import get_client
        for r in results:
            if r.get("ok"):
                get_client().table("ds24_affiliate_blasts").insert({
                    "product_id": r["product_id"],
                    "channels": r.get("channels", 0),
                    "blasted_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
    except Exception:
        pass

    return {
        "ok": True,
        "blasted": blasted,
        "failed": failed,
        "total": len(DS24_APPROVED_PRODUCTS),
    }


async def blast_niche(niche: str) -> dict:
    """Nur Produkte einer bestimmten Nische blasten."""
    products = [p for p in DS24_APPROVED_PRODUCTS if p.get("niche") == niche]
    if not products:
        return {"ok": False, "error": f"Keine Produkte für Nische: {niche}"}
    blasted = 0
    for p in products:
        r = await blast_single_product(p)
        if r.get("ok"):
            blasted += 1
        await asyncio.sleep(1.5)
    return {"ok": True, "niche": niche, "blasted": blasted, "total": len(products)}


async def blast_random(count: int = 3) -> dict:
    """Zufällig 'count' Affiliate-Produkte blasten (für stündlichen Scheduler)."""
    selection = random.sample(DS24_APPROVED_PRODUCTS, min(count, len(DS24_APPROVED_PRODUCTS)))
    blasted = 0
    for p in selection:
        r = await blast_single_product(p, channels=["telegram", "slack", "discord"])
        if r.get("ok"):
            blasted += 1
        await asyncio.sleep(1.0)
    return {"ok": True, "blasted": blasted, "selected": len(selection)}


async def get_own_aiitec_products(limit: int = 30) -> list:
    """Eigene aiitec-Produkte (704xxx) dynamisch von DS24 API holen."""
    try:
        import aiohttp
        url = "https://www.digistore24.com/api/call/listProducts/JSON/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"X-DS-API-KEY": DS24_API_KEY},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
        products = data.get("data", {}).get("products", [])
        result = []
        for p in products[:limit]:
            pid = str(p.get("id", ""))
            name = p.get("name", f"Produkt {pid}")
            result.append({
                "id": pid,
                "seller": "aiitec",
                "title": name,
                "link": f"https://www.checkout-ds24.com/redir/{pid}/{AFFILIATE_ID}/",
                "niche": "business",
                "category": "Digital",
                "own_product": True,
            })
        log.info("Eigene aiitec-Produkte geladen: %d", len(result))
        return result
    except Exception as e:
        log.warning("Konnte aiitec-Produkte nicht laden: %s", e)
        return []


async def blast_own_products(limit: int = 10) -> dict:
    """Top-N eigene aiitec-Produkte blasten (Direktverkauf — 100% Erlös)."""
    products = await get_own_aiitec_products(limit=limit)
    if not products:
        return {"ok": False, "error": "Keine eigenen Produkte gefunden"}
    blasted = 0
    for p in products:
        r = await blast_single_product(p, channels=["telegram", "slack", "discord"])
        if r.get("ok"):
            blasted += 1
        await asyncio.sleep(1.5)
    return {"ok": True, "blasted": blasted, "total": len(products), "type": "own_products"}


async def update_links_in_env() -> dict:
    """Speichert alle Affiliate-Links als DS24_AFFILIATE_LINKS_JSON in Supabase."""
    try:
        import json as _json
        from modules.supabase_client import get_client
        links_json = _json.dumps({
            p["id"]: p["link"] for p in DS24_APPROVED_PRODUCTS
        })
        get_client().table("agent_memory").upsert({
            "key": "ds24_affiliate_links",
            "value": links_json,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"ok": True, "saved": len(DS24_APPROVED_PRODUCTS)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_affiliate_stats() -> dict:
    """Statistiken über alle Affiliate-Produkte."""
    niches = {}
    for p in DS24_APPROVED_PRODUCTS:
        n = p.get("niche", "unknown")
        niches[n] = niches.get(n, 0) + 1
    return {
        "ok": True,
        "total_products": len(DS24_APPROVED_PRODUCTS),
        "affiliate_id": AFFILIATE_ID,
        "niches": niches,
        "products": [
            {"id": p["id"], "seller": p["seller"], "niche": p["niche"],
             "link": p["link"], "category": p.get("category", "Digital")}
            for p in DS24_APPROVED_PRODUCTS
        ],
    }


async def run_affiliate_cycle() -> dict:
    """Scheduler-Einstiegspunkt: 3 zufällige Produkte stündlich blasten."""
    return await blast_random(count=3)


async def run_daily_affiliate_blast() -> dict:
    """Täglich: alle externen Affiliate-Produkte + Top-20 eigene aiitec-Produkte."""
    external = await blast_all_approved(delay=2.0)
    own = await blast_own_products(limit=20)
    return {
        "ok": True,
        "external_blasted": external.get("blasted", 0),
        "own_blasted": own.get("blasted", 0),
        "total_blasted": external.get("blasted", 0) + own.get("blasted", 0),
    }
