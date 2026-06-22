#!/usr/bin/env python3
"""
Shopify Product Deduplicator — setzt duplizierte Produkte auf 'draft'.
Behalte das BESTE Exemplar (meiste Bilder > längste Beschreibung > höchste ID).
Kein Löschen — alle können im Admin wiederhergestellt werden.

Nutzung:
  python3 scripts/shopify_dedup.py --dry-run   # zeigt was passieren würde
  python3 scripts/shopify_dedup.py             # führt durch
"""
from __future__ import annotations
import requests, os, re, time, sys
from pathlib import Path

env = Path(__file__).parent.parent / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SHOP    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
TOKEN   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
BASE    = f"https://{SHOP}/admin/api/{VERSION}"
DELAY   = 0.7   # slightly slower to avoid rate limits alongside other parallel scripts


def fetch_all_active() -> list[dict]:
    products = []
    url = f"{BASE}/products.json?limit=250&status=active&fields=id,title,images,body_html"
    while url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json().get("products", [])
        products.extend(batch)
        print(f"  Geladen: {len(products)}", end="\r", flush=True)
        link = r.headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.strip().split(";")[0].strip().strip("<>")
        time.sleep(DELAY)
    return products


def score(p: dict) -> tuple:
    """Higher score = better product to keep."""
    img_count = len(p.get("images") or [])
    desc_len = len(re.sub(r"<[^>]+>", "", p.get("body_html") or ""))
    pid = p["id"]
    return (img_count, desc_len, pid)


def set_draft(pid: int, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            r = requests.put(
                f"{BASE}/products/{pid}.json",
                headers=HEADERS,
                json={"product": {"id": pid, "status": "draft"}},
                timeout=60,
            )
            return r.status_code == 200
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return False


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Shopify Product Deduplicator {'[DRY-RUN]' if dry_run else ''}")
    print(f"Shop: {SHOP}")
    print()
    print("Lade alle aktiven Produkte...")
    products = fetch_all_active()
    print(f"\n{len(products)} Produkte geladen.\n")

    # Group by exact title
    by_title: dict[str, list[dict]] = {}
    for p in products:
        by_title.setdefault(p["title"], []).append(p)

    dupe_groups = {t: ps for t, ps in by_title.items() if len(ps) > 1}
    total_extra = sum(len(v) - 1 for v in dupe_groups.values())

    print(f"Unique Titel: {len(by_title)}")
    print(f"Duplikat-Gruppen: {len(dupe_groups)}")
    print(f"Extra Produkte zum Archivieren: {total_extra}")
    print()

    archived = 0
    errors = 0

    for title, group in sorted(dupe_groups.items(), key=lambda x: -len(x[1])):
        # Sort: best first (keep[0]), rest get drafted
        ranked = sorted(group, key=score, reverse=True)
        keep = ranked[0]
        to_draft = ranked[1:]

        keep_imgs = len(keep.get("images") or [])
        keep_desc = len(re.sub(r"<[^>]+>", "", keep.get("body_html") or ""))
        print(f"  {len(group)}x '{title[:52]}' → keep ID {keep['id']} ({keep_imgs} imgs, {keep_desc} chars)")

        for p in to_draft:
            if dry_run:
                print(f"     [DRY] would archive ID {p['id']}")
            else:
                ok = set_draft(p["id"])
                if ok:
                    archived += 1
                else:
                    errors += 1
                    print(f"     ❌ FEHLER bei ID {p['id']}")
                time.sleep(DELAY)

    print()
    if dry_run:
        print(f"[DRY-RUN] Würde {total_extra} Produkte auf 'draft' setzen.")
        print(f"Zum Ausführen: python3 scripts/shopify_dedup.py")
    else:
        print(f"✅ FERTIG! {archived} Produkte auf 'draft' gesetzt. {errors} Fehler.")
        print(f"Rückgängig: Shopify Admin → Produkte → Entwürfe → Status auf 'Aktiv' setzen")


if __name__ == "__main__":
    main()
