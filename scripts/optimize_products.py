#!/usr/bin/env python3
"""
Shopify Produkt-Beschreibungs-Optimierer mit Ollama (lokale KI).
Liest alle Produkte ohne SEO-Beschreibung und schreibt neue via llama3.2.
Paginiert via since_id, kann beliebig oft ausgeführt werden (idempotent).

Nutzung:
  python3 scripts/optimize_products.py            # Batch von 50
  python3 scripts/optimize_products.py --limit 100
  python3 scripts/optimize_products.py --all      # alle 1410+ optimieren
"""
import asyncio
import argparse
import logging
import os
import re
import sys
from pathlib import Path

import aiohttp

# Load .env
for l in (Path(__file__).parent.parent / ".env").read_text().split("\n"):
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "").replace("https://", "").rstrip("/")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")
BASE    = f"https://{DOMAIN}/admin/api/{VERSION}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
OLLAMA  = os.getenv("OLLAMA_BASE", "http://localhost:11434") + "/api/chat"
MODEL   = os.getenv("OLLAMA_FAST_MODEL", "llama3.2:latest")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ProductOptimizer")

SYSTEM = """Du bist ein SEO-Experte für deutschen E-Commerce.
Erstelle eine Shopify-Produktbeschreibung auf Deutsch:
- Max 180 Wörter
- HTML mit <strong> für Highlights und <ul><li> für Features
- Fokus: konkreter Nutzen, wichtigste Features, Kaufanreiz
- Natürliche Sprache, kein Keyword-Stuffing
- Endet mit Call-to-Action Satz"""


async def generate_description(title: str, current: str = "") -> str:
    prompt = (f"Produkt: {title}\n"
              f"Aktuelle Beschreibung: {current[:150] if current else 'keine'}\n\n"
              "Erstelle eine bessere SEO-Produktbeschreibung auf Deutsch mit HTML.")
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": 420},
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=55)) as s:
            async with s.post(OLLAMA, json=payload) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    return d.get("message", {}).get("content", "")
    except Exception as e:
        log.debug("Ollama error: %s", e)
    return ""


async def update_product(session: aiohttp.ClientSession, prod_id: int, body_html: str) -> bool:
    payload = {"product": {"id": prod_id, "body_html": body_html}}
    async with session.put(f"{BASE}/products/{prod_id}.json", headers=HEADERS, json=payload) as r:
        return r.status == 200


async def fetch_products_needing_optimization(min_desc_len: int = 200) -> list[dict]:
    """Load all products with short/no description via since_id pagination."""
    needs_opt = []
    last_id = 0

    async with aiohttp.ClientSession() as s:
        while True:
            url = f"{BASE}/products.json?limit=250&fields=id,title,body_html&status=active&since_id={last_id}"
            async with s.get(url, headers=HEADERS) as r:
                batch = (await r.json()).get("products", [])
            if not batch:
                break
            last_id = batch[-1]["id"]
            for p in batch:
                body = p.get("body_html") or ""
                clean = re.sub(r"<[^>]+>", "", body)
                if len(clean) < min_desc_len:
                    needs_opt.append(p)
            if len(batch) < 250:
                break

    return needs_opt


async def main(limit: int = 50, all_products: bool = False):
    log.info("Lade Produkte von Shopify...")
    needs_opt = await fetch_products_needing_optimization()
    log.info("Gesamt ohne SEO-Beschreibung: %d", len(needs_opt))

    target = needs_opt if all_products else needs_opt[:limit]
    log.info("Optimiere %d Produkte mit %s...", len(target), MODEL)

    updated = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        for i, p in enumerate(target):
            title = p["title"]
            current = re.sub(r"<[^>]+>", "", p.get("body_html") or "")
            print(f"  [{i+1}/{len(target)}] {title[:50]}...", end=" ", flush=True)

            new_desc = await generate_description(title, current)
            if new_desc and len(new_desc) > 50:
                ok = await update_product(session, p["id"], new_desc)
                if ok:
                    updated += 1
                    print("✅")
                else:
                    failed += 1
                    print("❌ API")
            else:
                failed += 1
                print("⚠ leer")

    print(f"\n✅ {updated}/{len(target)} Produkte optimiert! ({failed} fehlgeschlagen)")
    print(f"🔄 Noch {max(0, len(needs_opt)-len(target))} weitere brauchen Optimierung")
    print("→ Erneut ausführen für nächste Batch: python3 scripts/optimize_products.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="Anzahl Produkte (default: 50)")
    parser.add_argument("--all", action="store_true", help="Alle Produkte optimieren")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, all_products=args.all))
