"""
Shopify Conversion Rate Optimizer
Analysiert und verbessert die Conversion Rate des ineedit.com.co Shops.
Fokus: fehlende Beschreibungen, Bilder, Preise — und gezielte Produkt-Aktivierung.
"""

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Konfiguration ─────────────────────────────────────────────────────────────

API_VERSION = "2024-01"
MIN_PRICE = 5.0
MAX_PRICE = 500.0
MIN_DESCRIPTION_LEN = 50
DESCRIPTION_TEMPLATE = (
    "Hochwertiges {title} – ideal für den modernen Alltag. "
    "Schnelle Lieferung, Top-Qualität."
)


def _shop_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")


def _admin_token() -> str:
    return (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )


def _base_url() -> str:
    domain = _shop_domain()
    if not domain:
        raise ValueError("SHOPIFY_SHOP_DOMAIN ist nicht gesetzt")
    return f"https://{domain}/admin/api/{API_VERSION}"


def _auth_headers() -> Dict[str, str]:
    token = _admin_token()
    if not token:
        raise ValueError("Kein Shopify Admin API Token gefunden (SHOPIFY_ADMIN_API_TOKEN)")
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── HTTP-Hilfsfunktionen ──────────────────────────────────────────────────────

def _get(url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Synchroner GET mit optionalen Query-Parametern. Gibt parsed JSON zurück."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_auth_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            link_header = resp.headers.get("Link", "")
            data = json.loads(raw)
            data["_link_header"] = link_header
            return data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("GET %s → HTTP %d: %s", url, exc.code, body[:300])
        raise
    except urllib.error.URLError as exc:
        logger.error("GET %s → URLError: %s", url, exc.reason)
        raise


def _put(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Synchroner PUT mit JSON-Body."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=_auth_headers(), method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_err = exc.read().decode("utf-8", errors="replace")
        logger.error("PUT %s → HTTP %d: %s", url, exc.code, body_err[:300])
        raise


def _next_page_url(link_header: str) -> Optional[str]:
    """Extrahiert die 'next'-URL aus dem Shopify Link-Header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            url_part = part.split(";")[0].strip()
            if url_part.startswith("<") and url_part.endswith(">"):
                return url_part[1:-1]
    return None


def _fetch_all_products(published_status: str = "any") -> List[Dict[str, Any]]:
    """
    Holt alle Produkte mit Pagination (limit=250 pro Seite).
    published_status: 'any' | 'published' | 'unpublished'
    """
    products: List[Dict[str, Any]] = []
    url = f"{_base_url()}/products.json"
    params: Dict[str, Any] = {
        "limit": 250,
        "published_status": published_status,
        "fields": "id,title,body_html,images,variants,status,published_at",
    }

    page = 1
    while url:
        logger.info("Lade Produkt-Seite %d …", page)
        if page == 1:
            data = _get(url, params)
        else:
            # Bei Folgeseiten ist die URL bereits vollständig (mit Cursor)
            data = _get(url)

        batch = data.get("products", [])
        products.extend(batch)
        logger.info("  → %d Produkte geladen (gesamt: %d)", len(batch), len(products))

        url = _next_page_url(data.get("_link_header", ""))
        page += 1
        if url:
            time.sleep(0.3)  # Rate-Limit schonen (2 req/s Burst-Budget)

    return products


# ─── Analyse-Hilfsfunktionen ──────────────────────────────────────────────────

def _has_image(product: Dict) -> bool:
    return bool(product.get("images"))


def _has_description(product: Dict) -> bool:
    body = (product.get("body_html") or "").strip()
    # HTML-Tags abziehen für reine Textlänge
    import re
    text = re.sub(r"<[^>]+>", "", body)
    return len(text) >= MIN_DESCRIPTION_LEN


def _price_ok(product: Dict) -> Tuple[bool, float]:
    """Gibt (ok, min_price) zurück. Prüft ob min. 1 Variante im erlaubten Bereich liegt."""
    variants = product.get("variants", [])
    prices = []
    for v in variants:
        try:
            p = float(v.get("price", 0) or 0)
            if p > 0:
                prices.append(p)
        except (ValueError, TypeError):
            pass
    if not prices:
        return False, 0.0
    min_p = min(prices)
    return MIN_PRICE <= min_p <= MAX_PRICE, min_p


def _product_score(product: Dict) -> int:
    """0–3 Punkte: Bild + Beschreibung + Preis."""
    score = 0
    if _has_image(product):
        score += 1
    if _has_description(product):
        score += 1
    ok, _ = _price_ok(product)
    if ok:
        score += 1
    return score


# ─── Öffentliche API ──────────────────────────────────────────────────────────

def audit_store() -> Dict[str, Any]:
    """
    Prüft den Shopify-Store auf Conversion-Probleme.

    Rückgabe-Dict:
    {
        "total_products": int,
        "published": int,
        "unpublished": int,
        "missing_description": int,
        "missing_image": int,
        "price_out_of_range": int,
        "fully_optimized": int,    # alle 3 Kriterien erfüllt
        "score_distribution": {0:n, 1:n, 2:n, 3:n},
        "conversion_readiness_pct": float,
        "issues": [str, …],
    }
    """
    logger.info("audit_store: starte Store-Analyse …")
    products = _fetch_all_products(published_status="any")

    total = len(products)
    published = sum(1 for p in products if p.get("status") == "active")
    unpublished = total - published
    no_desc = 0
    no_img = 0
    bad_price = 0
    fully_ok = 0
    score_dist: Dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    for p in products:
        has_img = _has_image(p)
        has_desc = _has_description(p)
        price_fine, _ = _price_ok(p)

        if not has_desc:
            no_desc += 1
        if not has_img:
            no_img += 1
        if not price_fine:
            bad_price += 1
        if has_img and has_desc and price_fine:
            fully_ok += 1

        s = _product_score(p)
        score_dist[s] = score_dist.get(s, 0) + 1

    readiness = round((fully_ok / total * 100) if total else 0.0, 1)

    issues: List[str] = []
    if no_desc:
        issues.append(f"{no_desc} Produkte ohne ausreichende Beschreibung (< {MIN_DESCRIPTION_LEN} Zeichen)")
    if no_img:
        issues.append(f"{no_img} Produkte ohne Bild")
    if bad_price:
        issues.append(f"{bad_price} Produkte mit Preis außerhalb €{MIN_PRICE}–€{MAX_PRICE}")
    if unpublished:
        issues.append(f"{unpublished} Produkte nicht veröffentlicht")
    if readiness < 30:
        issues.append(f"Conversion-Readiness kritisch: {readiness}% (Ziel: ≥ 70%)")

    result = {
        "total_products": total,
        "published": published,
        "unpublished": unpublished,
        "missing_description": no_desc,
        "missing_image": no_img,
        "price_out_of_range": bad_price,
        "fully_optimized": fully_ok,
        "score_distribution": score_dist,
        "conversion_readiness_pct": readiness,
        "issues": issues,
    }
    logger.info("audit_store: %s", result)
    return result


def fix_missing_descriptions(limit: int = 20) -> int:
    """
    Setzt für Produkte mit fehlender/zu kurzer Beschreibung einen Standard-Text.
    Verarbeitet maximal `limit` Produkte pro Aufruf.
    Gibt die Anzahl der aktualisierten Produkte zurück.
    """
    logger.info("fix_missing_descriptions: limit=%d", limit)
    import re

    products = _fetch_all_products(published_status="any")

    # Nur Produkte ohne ausreichende Beschreibung
    to_fix = [p for p in products if not _has_description(p)]
    to_fix = to_fix[:limit]

    if not to_fix:
        logger.info("fix_missing_descriptions: Keine Produkte mit fehlender Beschreibung gefunden.")
        return 0

    fixed = 0
    for p in to_fix:
        pid = p["id"]
        title = (p.get("title") or "Produkt").strip()
        description = DESCRIPTION_TEMPLATE.format(title=title)
        url = f"{_base_url()}/products/{pid}.json"
        payload = {"product": {"id": pid, "body_html": description}}
        try:
            _put(url, payload)
            logger.info("fix_missing_descriptions: Produkt %d ('%s') aktualisiert.", pid, title)
            fixed += 1
            time.sleep(0.25)  # Rate-Limit: max. 4 req/s
        except Exception as exc:
            logger.warning("fix_missing_descriptions: Fehler bei Produkt %d: %s", pid, exc)

    logger.info("fix_missing_descriptions: %d / %d Produkte korrigiert.", fixed, len(to_fix))
    return fixed


def activate_best_products(limit: int = 50) -> int:
    """
    Publiziert die Top-N Produkte nach Score (Bild + Beschreibung + Preis > 0).
    Ignoriert bereits aktive Produkte.
    Gibt die Anzahl der aktivierten Produkte zurück.
    """
    logger.info("activate_best_products: limit=%d", limit)
    products = _fetch_all_products(published_status="any")

    # Nur inaktive Produkte mit Score 3 (alle Kriterien erfüllt)
    candidates = [
        p for p in products
        if p.get("status") != "active" and _product_score(p) == 3
    ]

    # Fallback: Score 2 wenn nicht genug Score-3-Kandidaten
    if len(candidates) < limit:
        score2 = [
            p for p in products
            if p.get("status") != "active"
            and _product_score(p) == 2
            and p not in candidates
        ]
        candidates.extend(score2)

    # Nach Score sortieren (3 zuerst), dann nach Preis absteigend
    def sort_key(p: Dict) -> Tuple:
        _, price = _price_ok(p)
        return (_product_score(p), price)

    candidates.sort(key=sort_key, reverse=True)
    candidates = candidates[:limit]

    if not candidates:
        logger.info("activate_best_products: Keine geeigneten Produkte zum Aktivieren gefunden.")
        return 0

    activated = 0
    for p in candidates:
        pid = p["id"]
        title = (p.get("title") or "–").strip()
        url = f"{_base_url()}/products/{pid}.json"
        payload = {"product": {"id": pid, "status": "active"}}
        try:
            _put(url, payload)
            logger.info("activate_best_products: Produkt %d ('%s') aktiviert.", pid, title)
            activated += 1
            time.sleep(0.25)
        except Exception as exc:
            logger.warning("activate_best_products: Fehler bei Produkt %d: %s", pid, exc)

    logger.info("activate_best_products: %d Produkte aktiviert.", activated)
    return activated


def get_conversion_stats() -> Dict[str, Any]:
    """
    Gibt aktuelle Store-Gesundheitsmetriken zurück (schnell, kein Vollscan).
    Nutzt published_status=published für Speed.
    """
    logger.info("get_conversion_stats: lade veröffentlichte Produkte …")
    try:
        products = _fetch_all_products(published_status="published")
    except Exception as exc:
        logger.error("get_conversion_stats: Fehler beim Laden: %s", exc)
        return {"error": str(exc)}

    total = len(products)
    with_img = sum(1 for p in products if _has_image(p))
    with_desc = sum(1 for p in products if _has_description(p))
    with_price, _ = zip(*((_price_ok(p)) for p in products)) if products else ([], [])
    price_ok_count = sum(with_price) if products else 0
    fully_ok = sum(1 for p in products if _product_score(p) == 3)

    stats = {
        "published_products": total,
        "with_image": with_img,
        "with_image_pct": round(with_img / total * 100, 1) if total else 0.0,
        "with_description": with_desc,
        "with_description_pct": round(with_desc / total * 100, 1) if total else 0.0,
        "with_valid_price": price_ok_count,
        "with_valid_price_pct": round(price_ok_count / total * 100, 1) if total else 0.0,
        "fully_conversion_ready": fully_ok,
        "conversion_readiness_pct": round(fully_ok / total * 100, 1) if total else 0.0,
    }
    logger.info("get_conversion_stats: %s", stats)
    return stats


async def run_conversion_cycle() -> Dict[str, Any]:
    """
    Vollständiger Optimierungsdurchlauf (async, kompatibel mit aiohttp-Event-Loop):
    1. Store-Audit
    2. Fehlende Beschreibungen reparieren (max. 20)
    3. Stats zurückgeben

    Gibt ein zusammenfassendes Dict zurück.
    """
    logger.info("run_conversion_cycle: starte …")
    loop = asyncio.get_event_loop()

    # Alle blockierenden HTTP-Calls in Thread-Pool ausführen
    audit = await loop.run_in_executor(None, audit_store)
    logger.info("run_conversion_cycle: Audit abgeschlossen.")

    fixed = 0
    if audit.get("missing_description", 0) > 0:
        fixed = await loop.run_in_executor(None, lambda: fix_missing_descriptions(limit=20))
        logger.info("run_conversion_cycle: %d Beschreibungen repariert.", fixed)

    stats = await loop.run_in_executor(None, get_conversion_stats)
    logger.info("run_conversion_cycle: Stats abgerufen.")

    result = {
        "cycle": "conversion_optimizer",
        "audit": audit,
        "descriptions_fixed": fixed,
        "current_stats": stats,
        "recommendations": _build_recommendations(audit, stats),
    }
    logger.info("run_conversion_cycle: abgeschlossen. Ergebnis: %s", result)
    return result


# ─── Interne Hilfsfunktionen ──────────────────────────────────────────────────

def _build_recommendations(audit: Dict, stats: Dict) -> List[str]:
    """Leitet konkrete Handlungsempfehlungen aus Audit + Stats ab."""
    recs: List[str] = []

    missing_desc = audit.get("missing_description", 0)
    if missing_desc > 0:
        recs.append(
            f"{missing_desc} Produkte haben keine Beschreibung → "
            "fix_missing_descriptions() ausführen (erhöht SEO + Trust)."
        )

    missing_img = audit.get("missing_image", 0)
    if missing_img > 0:
        recs.append(
            f"{missing_img} Produkte haben kein Bild → "
            "Bilder manuell hochladen oder Supplier-Feed prüfen."
        )

    bad_price = audit.get("price_out_of_range", 0)
    if bad_price > 0:
        recs.append(
            f"{bad_price} Produkte haben Preise außerhalb €{MIN_PRICE}–€{MAX_PRICE} → "
            "Preise überprüfen und korrigieren."
        )

    unpublished = audit.get("unpublished", 0)
    if unpublished > 0:
        recs.append(
            f"{unpublished} Produkte nicht veröffentlicht → "
            "activate_best_products() ausführen für qualifizierte Produkte."
        )

    readiness = stats.get("conversion_readiness_pct", 0)
    if readiness < 50:
        recs.append(
            f"Conversion-Readiness: {readiness}% (Ziel: ≥ 70%). "
            "Kombination aus Bild-, Beschreibungs- und Preisfixes erforderlich."
        )
    elif readiness < 70:
        recs.append(
            f"Conversion-Readiness: {readiness}% — auf 70%+ optimieren für bessere Conversion."
        )

    if not recs:
        recs.append(
            f"Store gut aufgestellt: {readiness}% Conversion-Readiness. "
            "Nächster Schritt: A/B-Tests für Produktseiten und Checkout-Flow."
        )

    return recs


# ─── CLI-Direktaufruf ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"

    if cmd == "audit":
        result = audit_store()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "fix":
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        n = fix_missing_descriptions(limit=lim)
        print(f"Korrigiert: {n}")
    elif cmd == "activate":
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        n = activate_best_products(limit=lim)
        print(f"Aktiviert: {n}")
    elif cmd == "stats":
        result = get_conversion_stats()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "cycle":
        result = asyncio.run(run_conversion_cycle())
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Unbekannter Befehl: {cmd}")
        print("Verfügbar: audit | fix [limit] | activate [limit] | stats | cycle")
        sys.exit(1)
