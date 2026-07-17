#!/usr/bin/env python3
"""Shopify Quick Optimization -- Discount SMART10 + Collections SEO."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass


async def main():
    import aiohttp
    from modules.shopify_conversion_optimizer import create_discount_code

    # ── 1. Discount Code SMART10 (10% auf alles) ─────────────────────────────
    print("\n=== Discount Code SMART10 ===")
    result = await create_discount_code(
        code="SMART10",
        percent=10,
        min_subtotal=0.0,
        once_per_customer=False,
        title="SMART10 -- 10% auf alles (Smart Tech Shop)",
    )
    print(f"Discount: {result}")

    # ── 2. Smart + Custom Collections SEO-Update ──────────────────────────────
    print("\n=== Smart Collections SEO-Update ===")

    domain = os.getenv("SHOPIFY_MYSHOPIFY_DOMAIN") or os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if domain and ".myshopify.com" not in domain:
        import re
        store_url = os.getenv("SHOPIFY_STORE_URL", "")
        m = re.search(r"([\w-]+\.myshopify\.com)", store_url)
        if m:
            domain = m.group(1)

    token = (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
    ver = os.getenv("SHOPIFY_API_VERSION", "2026-04")

    if not domain or not token:
        print("FEHLER: SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlt")
        return

    seo_updates = {
        "smart home": (
            "Smart Home Gadgets kaufen -- Top Preise | ineedit",
            "Entdecke smarte Home-Geraete: Solaranlagen, AI-Gadgets, Kuechen-Tech. Top Qualitaet ab 19 Euro.",
        ),
        "solar": (
            "Solar & Energie Shop -- Powerstation kaufen | ineedit",
            "Komplette Solaranlagen, Balkonkraftwerke, Powerstations. Energieunabhaengig werden.",
        ),
        "kitchen": (
            "Smarte Kuechengeraete -- AI-Kitchen | ineedit",
            "Smart kitchen technology: AI coffee makers, smart mixers, connected cooking devices.",
        ),
        "kueche": (
            "Smarte Kuechengeraete -- AI-Kueche | ineedit",
            "Moderne Kuechentechnik mit KI-Integration. Vom Mixer bis zur smarten Kaffeemaschine.",
        ),
        "tech": (
            "Tech & Gadgets Shop | ineedit",
            "Moderne Technologie fuer den Alltag: Smart Devices, Gadgets, AI-Tools. Jetzt entdecken.",
        ),
        "gadget": (
            "Top Gadgets kaufen -- Smart Tech | ineedit",
            "Die besten Gadgets und Smart-Devices. Hochwertige Technik fuer dein Leben.",
        ),
        "energie": (
            "Energie & Solar Shop -- Off-Grid Loesungen | ineedit",
            "Solaranlagen, Powerstations, Balkonkraftwerke. Werde energieunabhaengig.",
        ),
        "outdoor": (
            "Smart Outdoor Equipment | ineedit",
            "Smarte Outdoor-Ausruestung: Solar-Ladegeraete, GPS-Tracker, Survival-Tech.",
        ),
        "sport": (
            "Smart Sports & Fitness Tech | ineedit",
            "Smarte Sport- und Fitness-Technologie: GPS-Uhren, Herzfrequenzmonitore, AI-Trainer.",
        ),
        "powerstation": (
            "Powerstations & mobile Stromspeicher | ineedit",
            "Tragbare Powerstations und Akkus fuer Camping, Outdoor und Notfall. Off-Grid ready.",
        ),
    }

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    base_url = f"https://{domain}/admin/api/{ver}"
    updated = skipped = errors = 0

    async with aiohttp.ClientSession() as s:
        # Smart Collections holen
        async with s.get(
            f"{base_url}/smart_collections.json?limit=250",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            if r.status != 200:
                print(f"FEHLER Smart Collections: HTTP {r.status}")
                return
            smart_colls = (await r.json()).get("smart_collections", [])

        await asyncio.sleep(0.6)

        # Custom Collections holen
        async with s.get(
            f"{base_url}/custom_collections.json?limit=250",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            custom_colls = (await r.json()).get("custom_collections", []) if r.status == 200 else []

        print(f"Gefunden: {len(smart_colls)} Smart + {len(custom_colls)} Custom Collections")

        all_colls = (
            [("smart_collections", c) for c in smart_colls]
            + [("custom_collections", c) for c in custom_colls]
        )

        for coll_type, c in all_colls:
            title_lower = c.get("title", "").lower()
            matched_seo = None
            for kw, seo in seo_updates.items():
                if kw in title_lower:
                    matched_seo = seo
                    break
            if not matched_seo:
                skipped += 1
                continue

            meta_title, meta_desc = matched_seo
            coll_id = c["id"]
            if coll_type == "smart_collections":
                update_key = "smart_collection"
                update_url = f"{base_url}/smart_collections/{coll_id}.json"
            else:
                update_key = "custom_collection"
                update_url = f"{base_url}/custom_collections/{coll_id}.json"

            payload = {
                update_key: {
                    "id": coll_id,
                    "metafields_global_title_tag": meta_title,
                    "metafields_global_description_tag": meta_desc,
                }
            }

            for attempt in range(3):
                await asyncio.sleep(0.6)  # max 2 calls/sec
                async with s.put(
                    update_url, headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as rr:
                    if rr.status == 429:
                        wait = int(float(rr.headers.get("Retry-After", 5)))
                        print(f"  429 -- warte {wait}s ...")
                        await asyncio.sleep(wait)
                        continue
                    if rr.status in (200, 201):
                        print(f"  SEO OK [{rr.status}]: {c['title']} -> {meta_title[:55]}...")
                        updated += 1
                    else:
                        body = await rr.text()
                        print(f"  SEO FEHLER [{rr.status}]: {c['title']} -- {body[:120]}")
                        errors += 1
                    break

    print("\n=== Ergebnis ===")
    if result.get("ok"):
        already = " (bereits vorhanden)" if result.get("already_existing") else ""
        discount_id = result.get("id") or result.get("rule_id", "N/A")
        print(f"Discount SMART10: ERSTELLT{already} -- ID: {discount_id}")
    else:
        print(f"Discount SMART10: FEHLER -- {result.get('error', 'unbekannt')}")
    print(f"Collections SEO-Updated: {updated}")
    print(f"Collections ohne Keyword-Match: {skipped}")
    print(f"Fehler: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
