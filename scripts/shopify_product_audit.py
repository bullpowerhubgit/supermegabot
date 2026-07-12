#!/usr/bin/env python3
"""
Shopify Product Audit — bewertet alle aktiven Produkte nach Bild-Qualität,
Beschreibung und Sales. Gibt sortierte Liste aus OHNE zu löschen.
"""
import asyncio
import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp

SHOP  = os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VER   = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE  = f"https://{SHOP}/admin/api/{VER}"
HDR   = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

GENERIC_KEYWORDS = [
    "high-tech", "high tech", "gadget", "product", "item",
    "best quality", "hot selling", "factory", "wholesale",
    "aliexpress", "dropship", "lorem ipsum",
    "description here", "add description",
    "enter your", "click here", "buy now",
]

GENERIC_TITLE_PATTERNS = [
    r"^\d+\s*(pcs|units|pieces|pack)",
    r"^new\s+\d{4}",
    r"hot sale",
    r"free shipping",
    r"wholesale",
]


def score_product(p: dict, sales_set: set) -> dict:
    score = 0
    reasons = []

    images = p.get("images", [])
    img_count = len(images)

    # Bild-Scoring
    if img_count == 0:
        score += 10
        reasons.append("Kein Bild (10)")
    elif img_count == 1:
        score += 2
        reasons.append("Nur 1 Bild (2)")

    # Beschreibung prüfen
    body = (p.get("body_html") or "").lower().strip()
    body_text = re.sub(r"<[^>]+>", " ", body).strip()

    if len(body_text) < 50:
        score += 4
        reasons.append(f"Beschreibung zu kurz ({len(body_text)} Zeichen) (4)")
    elif len(body_text) < 150:
        score += 2
        reasons.append(f"Beschreibung kurz ({len(body_text)} Zeichen) (2)")

    for kw in GENERIC_KEYWORDS:
        if kw in body_text:
            score += 3
            reasons.append(f"Generisches Keyword: '{kw}' (3)")
            break

    # Titel prüfen
    title = (p.get("title") or "").lower()
    for pat in GENERIC_TITLE_PATTERNS:
        if re.search(pat, title, re.IGNORECASE):
            score += 3
            reasons.append(f"Generischer Titel: '{pat}' (3)")
            break

    # product_type fehlt
    if not p.get("product_type"):
        score += 1
        reasons.append("Kein product_type (1)")

    # Vendor fehlt / generisch
    vendor = (p.get("vendor") or "").lower()
    if not vendor or vendor in ("vendor", "default", "supplier", "factory", ""):
        score += 1
        reasons.append("Kein/generischer Vendor (1)")

    # 0 Sales
    pid = p.get("id")
    if pid not in sales_set:
        score += 3
        reasons.append("0 Verkäufe 30T (3)")

    return {
        "id": pid,
        "title": p.get("title", "—")[:80],
        "product_type": p.get("product_type", "—"),
        "vendor": p.get("vendor", "—"),
        "img_count": img_count,
        "body_len": len(body_text),
        "score": score,
        "reasons": "; ".join(reasons),
        "admin_url": f"https://admin.shopify.com/store/autopilot-store-suite-fmbka/products/{pid}",
        "published_at": p.get("published_at", "—"),
    }


async def fetch_all(session, path, key, params=None):
    results = []
    url = f"{BASE}/{path}"
    p = params or {}
    while url:
        async with session.get(url, headers=HDR, params=p if url == f"{BASE}/{path}" else None) as r:
            r.raise_for_status()
            data = await r.json()
            batch = data.get(key, [])
            results.extend(batch)
            link = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = m.group(1) if m else None
            p = {}
            print(f"  {key}: {len(results):,} geladen…", end="\r")
    print()
    return results


async def main():
    print("=" * 60)
    print("SHOPIFY PRODUCT AUDIT — LeakHunter Pro")
    print("=" * 60)

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:

        # 1) Alle aktiven Produkte laden
        print("\n[1/3] Lade aktive Produkte…")
        products = await fetch_all(session, "products.json", "products", {
            "limit": 250,
            "status": "active",
            "fields": "id,title,status,body_html,images,product_type,vendor,published_at,variants",
        })
        print(f"  → {len(products):,} aktive Produkte geladen")

        # 2) Orders letzte 30 Tage → welche Produkte haben Sales?
        print("\n[2/3] Lade Orders (30 Tage)…")
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        orders = await fetch_all(session, "orders.json", "orders", {
            "limit": 250,
            "created_at_min": since,
            "financial_status": "paid",
            "status": "any",
            "fields": "id,line_items,cancelled_at",
        })
        sales_pids = set()
        for o in orders:
            if not o.get("cancelled_at"):
                for li in o.get("line_items", []):
                    pid = li.get("product_id")
                    if pid:
                        sales_pids.add(pid)
        print(f"  → {len(orders):,} Orders, {len(sales_pids):,} Produkte mit Sales")

    # 3) Alle Produkte bewerten
    print("\n[3/3] Bewerte Produkte…")
    scored = [score_product(p, sales_pids) for p in products]
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Ausgabe
    print(f"\n{'='*60}")
    print(f"AUDIT-ERGEBNIS: {len(scored):,} aktive Produkte analysiert")
    print(f"{'='*60}")

    critical  = [p for p in scored if p["score"] >= 10]
    high      = [p for p in scored if 5 <= p["score"] < 10]
    medium    = [p for p in scored if 2 <= p["score"] < 5]
    ok        = [p for p in scored if p["score"] < 2]

    print(f"\n🔴 KRITISCH (Score ≥10) — sofort löschen:   {len(critical):,}")
    print(f"🟠 HOCH (Score 5-9)  — prüfen/löschen:      {len(high):,}")
    print(f"🟡 MITTEL (Score 2-4) — optimieren:          {len(medium):,}")
    print(f"🟢 OK (Score <2):                             {len(ok):,}")

    print(f"\n{'='*60}")
    print("TOP 30 SCHLECHTESTE PRODUKTE (Score absteigend):")
    print(f"{'='*60}")
    for p in scored[:30]:
        print(f"\n  Score {p['score']:2d} | {p['title'][:60]}")
        print(f"          Typ: {p['product_type'][:30]} | Bilder: {p['img_count']} | Beschr: {p['body_len']} Zeichen")
        print(f"          Gründe: {p['reasons'][:120]}")
        print(f"          URL: {p['admin_url']}")

    # CSV Export
    out = Path("/tmp/shopify_audit.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        fields = ["score", "title", "product_type", "vendor", "img_count", "body_len", "reasons", "admin_url", "id"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(scored)

    # JSON für späteres Löschen
    json_out = Path("/tmp/shopify_audit.json")
    json_out.write_text(json.dumps(scored, ensure_ascii=False, indent=2))

    print(f"\n{'='*60}")
    print(f"✅ CSV gespeichert: {out}")
    print(f"✅ JSON gespeichert: {json_out}")
    print(f"\n⚠️  NOCH NICHTS GELÖSCHT — warte auf deine Bestätigung!")
    print(f"{'='*60}")

    return scored


if __name__ == "__main__":
    asyncio.run(main())
