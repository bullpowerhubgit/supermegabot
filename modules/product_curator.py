"""
Product Curator — Shopify Produktqualitäts-Filter
===================================================
Liest alle Shopify-Produkte, bewertet sie nach Qualitätskriterien
und archiviert schlechte bzw. aktiviert gute Produkte automatisch.

Scoring-Kriterien (0–5 Punkte):
  +1  Echte Bilder (keine generischen/AliExpress-URLs)
  +1  Beschreibung > 100 Zeichen
  +1  Preis zwischen 10 € und 1.000 €
  +1  Titel ohne verbotene Schlüsselwörter
  +1  Bonus: Smart-Home/Solar/Tech-Nische ODER Preis 15–300 €

Archivieren: Score < 2
Aktivieren:  Score >= 3

Export: run_product_curation() → {archived, activated, total_reviewed}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("ProductCurator")

# ─── Config ──────────────────────────────────────────────────────────────────

SHOP_DOMAIN  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN   = (
    os.getenv("SHOPIFY_ADMIN_API_TOKEN")
    or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
)
API_VERSION  = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR     = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
RESULTS_FILE = DATA_DIR / "curation_results.json"

# Rate-limit: Shopify REST erlaubt ~2 req/s; wir halten ~1.5 req/s
_DELAY_FETCH  = 0.7   # zwischen Seiten-Requests
_DELAY_UPDATE = 0.7   # zwischen Status-Updates
_PAGE_SIZE    = 100   # Produkte pro Seite (REST max)

# ─── Verbotene / gute Indikatoren ────────────────────────────────────────────

FORBIDDEN_TITLE_WORDS = {
    "dropshipping", "wholesale", "aliexpress", "alibaba",
    "bulk order", "bulk buy", "sample", "factory direct",
    "oem", "odm", "moq", "supplier",
}

FORBIDDEN_IMAGE_HOSTS = {
    "aliexpress.com", "ae01.alicdn.com", "ae02.alicdn.com",
    "ae03.alicdn.com", "alicdn.com", "s.alicdn.com",
    "img.alicdn.com", "gloimg.com", "gearbest.com",
    "dhresource.com", "banggood.com", "wish.com",
}

GENERIC_IMAGE_PATTERNS = [
    r"no[_-]?image",
    r"placeholder",
    r"product[_-]?default",
    r"noimage",
    r"default[_-]?image",
    r"blank[_-]?product",
]

GOOD_NICHE_KEYWORDS = {
    "smart home", "solar", "tech", "gadget", "led", "wifi", "bluetooth",
    "wireless", "sensor", "charger", "powerstation", "power station",
    "balkonkraftwerk", "photovoltaik", "inverter", "roboter", "robot",
    "automation", "smart plug", "smart bulb", "smart lamp", "camera",
    "security cam", "doorbell", "hub", "controller", "monitor",
    "tracker", "gps", "e-bike", "ebike", "electric", "drone",
    "portable power", "usb-c", "usb c", "fast charge", "qi charging",
}

# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _base_url() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"


def _headers() -> dict:
    return {
        "X-Shopify-Access-Token": SHOP_TOKEN,
        "Content-Type": "application/json",
    }


def _is_generic_image(url: str) -> bool:
    """Gibt True zurück wenn die Bild-URL generisch/AliExpress ist."""
    if not url:
        return True
    parsed = urlparse(url.lower())
    if parsed.netloc:
        for host in FORBIDDEN_IMAGE_HOSTS:
            if host in parsed.netloc:
                return True
    for pattern in GENERIC_IMAGE_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def _score_product(product: dict) -> int:
    """
    Berechnet einen Qualitäts-Score zwischen 0 und 5.
    """
    score = 0
    title       = (product.get("title") or "").strip()
    body_html   = (product.get("body_html") or "")
    description = re.sub(r"<[^>]+>", "", body_html).strip()
    images      = product.get("images") or []
    variants    = product.get("variants") or []

    # Preis aus erstem Variant
    price = 0.0
    if variants:
        try:
            price = float(variants[0].get("price", 0) or 0)
        except (ValueError, TypeError):
            price = 0.0

    # ── Kriterium 1: Echter Bilder-Check ──────────────────────────────────────
    has_real_image = False
    if images:
        for img in images:
            src = img.get("src") or ""
            if src and not _is_generic_image(src):
                has_real_image = True
                break
    if has_real_image:
        score += 1

    # ── Kriterium 2: Beschreibung > 100 Zeichen ───────────────────────────────
    if len(description) > 100:
        score += 1

    # ── Kriterium 3: Preis zwischen 10 € und 1.000 € ─────────────────────────
    if 10.0 <= price <= 1000.0:
        score += 1

    # ── Kriterium 4: Titel ohne verbotene Wörter & Mindestlänge ──────────────
    title_lower = title.lower()
    has_forbidden = any(word in title_lower for word in FORBIDDEN_TITLE_WORDS)
    if not has_forbidden and len(title) >= 10:
        score += 1

    # ── Kriterium 5 (Bonus): Gute Nische ODER optimaler Preisbereich ──────────
    in_good_niche = any(kw in title_lower or kw in description.lower() for kw in GOOD_NICHE_KEYWORDS)
    good_price_range = 15.0 <= price <= 300.0
    if in_good_niche or good_price_range:
        score += 1

    return score


def _is_hard_reject(product: dict) -> bool:
    """
    Sofort-Ablehnung unabhängig vom Score:
    Preis < 5 €, Titel < 10 Zeichen, Beschreibung < 50 Zeichen,
    oder verbotene Wörter im Titel.
    """
    title     = (product.get("title") or "").strip()
    body_html = (product.get("body_html") or "")
    desc      = re.sub(r"<[^>]+>", "", body_html).strip()
    variants  = product.get("variants") or []
    price     = 0.0
    if variants:
        try:
            price = float(variants[0].get("price", 0) or 0)
        except (ValueError, TypeError):
            price = 0.0

    title_lower = title.lower()
    if price > 0 and price < 5.0:
        return True
    if len(title) < 10:
        return True
    if len(desc) < 50 and desc:
        return True
    if any(word in title_lower for word in FORBIDDEN_TITLE_WORDS):
        return True
    return False


# ─── Shopify API ─────────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    """Sendet eine Telegram-Nachricht."""
    if not TG_TOKEN or not TG_CHAT:
        logger.warning("Telegram nicht konfiguriert — Nachricht übersprungen")
        return
    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as sess:
            await sess.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=_aio.ClientTimeout(total=10),
            )
    except Exception as exc:
        logger.warning("Telegram-Fehler: %s", exc)


async def _fetch_all_products() -> list[dict]:
    """
    Holt alle Produkte via Shopify REST API (Cursor-Pagination).
    Gibt eine flache Liste aller Produkte zurück.
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp nicht installiert")
        return []

    all_products: list[dict] = []
    url = f"{_base_url()}/products.json"
    params = {"limit": _PAGE_SIZE, "status": "any", "fields": "id,title,body_html,images,variants,status"}

    async with aiohttp.ClientSession(headers=_headers()) as sess:
        page = 0
        while url:
            page += 1
            try:
                async with sess.get(url, params=params if page == 1 else None,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 429:
                        logger.warning("Rate-Limit — warte 5s")
                        await asyncio.sleep(5)
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Shopify GET /products.json %d: %s", resp.status, body[:200])
                        break

                    data = await resp.json()
                    batch = data.get("products", [])
                    all_products.extend(batch)
                    logger.info("Seite %d geladen — %d Produkte (gesamt: %d)", page, len(batch), len(all_products))

                    # Nächste Seite via Link-Header
                    link_header = resp.headers.get("Link", "")
                    url = _parse_next_link(link_header)
                    params = None  # Parameter nur bei erstem Request

            except Exception as exc:
                logger.error("Fehler beim Laden der Produkte: %s", exc)
                break

            await asyncio.sleep(_DELAY_FETCH)

    return all_products


def _parse_next_link(link_header: str) -> Optional[str]:
    """Extrahiert 'next' URL aus Shopify Link-Header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None


async def _update_product_status(product_id: int, new_status: str) -> bool:
    """
    Setzt den Status eines Produkts via REST PUT.
    new_status: 'active' | 'archived' | 'draft'
    """
    try:
        import aiohttp
    except ImportError:
        return False

    url = f"{_base_url()}/products/{product_id}.json"
    payload = {"product": {"id": product_id, "status": new_status}}

    try:
        async with aiohttp.ClientSession(headers=_headers()) as sess:
            async with sess.put(url, json=payload,
                                timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 429:
                    await asyncio.sleep(5)
                    return await _update_product_status(product_id, new_status)
                if resp.status in (200, 201):
                    return True
                body = await resp.text()
                logger.warning("Update %d → %s fehlgeschlagen %d: %s",
                               product_id, new_status, resp.status, body[:150])
                return False
    except Exception as exc:
        logger.error("Fehler bei Status-Update %d: %s", product_id, exc)
        return False


# ─── CSV-Vorschau (optional) ──────────────────────────────────────────────────

def _read_csv_preview(csv_path: str) -> Optional[list[dict]]:
    """Liest erste 5 Zeilen der SHOPIFY CSV — nur zur Diagnose."""
    p = Path(csv_path)
    if not p.exists():
        return None
    try:
        import csv
        rows = []
        with open(p, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= 5:
                    break
                rows.append(dict(row))
        return rows
    except Exception as exc:
        logger.warning("CSV-Vorschau fehlgeschlagen: %s", exc)
        return None


# ─── Hauptfunktion ────────────────────────────────────────────────────────────

async def run_product_curation() -> dict:
    """
    Führt die vollständige Produkt-Kuration durch.

    Returns:
        {archived: int, activated: int, total_reviewed: int}
    """
    logger.info("=== ProductCurator gestartet ===")

    # CSV-Vorschau (rein informativ)
    csv_path = "/Users/rudolfsarkany/Library/Mobile Documents/com~apple~CloudDocs/SHOPIFY_20000_PRODUCTS.csv"
    csv_rows = _read_csv_preview(csv_path)
    if csv_rows:
        logger.info("CSV-Vorschau (%s) — erste 5 Zeilen:", csv_path)
        for i, row in enumerate(csv_rows, 1):
            # Zeige die ersten 5 Spalten-Werte
            sample = dict(list(row.items())[:5])
            logger.info("  Zeile %d: %s", i, sample)
        csv_columns = list(csv_rows[0].keys()) if csv_rows else []
        logger.info("CSV-Spalten: %s", csv_columns)
    else:
        logger.info("CSV-Datei nicht gefunden oder nicht lesbar: %s", csv_path)

    # Konfigurationsprüfung
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        msg = "SHOPIFY_SHOP_DOMAIN oder SHOPIFY_ADMIN_API_TOKEN fehlen — Abbruch"
        logger.error(msg)
        await _tg(f"ProductCurator Fehler: {msg}")
        return {"archived": 0, "activated": 0, "total_reviewed": 0, "error": msg}

    await _tg(
        "ProductCurator gestartet\n"
        f"Shop: {SHOP_DOMAIN}\n"
        f"Lade alle Produkte..."
    )

    # ── Produkte laden ──────────────────────────────────────────────────────
    products = await _fetch_all_products()
    total = len(products)
    logger.info("Insgesamt %d Produkte geladen", total)

    if total == 0:
        msg = "Keine Produkte gefunden — Kuration abgebrochen"
        logger.warning(msg)
        await _tg(f"ProductCurator: {msg}")
        return {"archived": 0, "activated": 0, "total_reviewed": 0}

    # ── Scoring ─────────────────────────────────────────────────────────────
    to_archive: list[dict] = []
    to_activate: list[dict] = []
    scores_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    skip_already_correct = 0
    hard_rejected = 0

    for p in products:
        pid    = p.get("id")
        status = p.get("status", "")
        score  = _score_product(p)
        scores_distribution[min(score, 5)] += 1

        hard_rej = _is_hard_reject(p)
        if hard_rej:
            hard_rejected += 1

        if score < 2 or hard_rej:
            if status != "archived":
                to_archive.append({"id": pid, "title": p.get("title", "")[:60], "score": score})
        elif score >= 3:
            if status != "active":
                to_activate.append({"id": pid, "title": p.get("title", "")[:60], "score": score})
        else:
            skip_already_correct += 1

    logger.info(
        "Scoring abgeschlossen: %d zu archivieren, %d zu aktivieren, %d bereits korrekt",
        len(to_archive), len(to_activate), skip_already_correct
    )

    # ── Archivieren ─────────────────────────────────────────────────────────
    archived_ok   = 0
    archived_fail = 0
    for item in to_archive:
        ok = await _update_product_status(item["id"], "archived")
        if ok:
            archived_ok += 1
        else:
            archived_fail += 1
        await asyncio.sleep(_DELAY_UPDATE)

    # ── Aktivieren ──────────────────────────────────────────────────────────
    activated_ok   = 0
    activated_fail = 0
    for item in to_activate:
        ok = await _update_product_status(item["id"], "active")
        if ok:
            activated_ok += 1
        else:
            activated_fail += 1
        await asyncio.sleep(_DELAY_UPDATE)

    # ── Ergebnisse speichern ─────────────────────────────────────────────────
    result = {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "shop":               SHOP_DOMAIN,
        "total_reviewed":     total,
        "archived":           archived_ok,
        "archived_failed":    archived_fail,
        "activated":          activated_ok,
        "activated_failed":   activated_fail,
        "hard_rejected":      hard_rejected,
        "already_correct":    skip_already_correct,
        "scores_distribution": scores_distribution,
        "archived_sample":    to_archive[:20],
        "activated_sample":   to_activate[:20],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        RESULTS_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        logger.info("Ergebnisse gespeichert: %s", RESULTS_FILE)
    except Exception as exc:
        logger.warning("Konnte Ergebnisse nicht speichern: %s", exc)

    # ── Telegram-Report ──────────────────────────────────────────────────────
    score_summary = " | ".join(f"{k}★:{v}" for k, v in scores_distribution.items())
    tg_msg = (
        f"<b>ProductCurator abgeschlossen</b>\n\n"
        f"Shop: {SHOP_DOMAIN}\n"
        f"Gesamt geprüft: {total}\n"
        f"Archiviert: {archived_ok} (Fehler: {archived_fail})\n"
        f"Aktiviert:  {activated_ok} (Fehler: {activated_fail})\n"
        f"Hard-Rejects: {hard_rejected}\n"
        f"Bereits korrekt: {skip_already_correct}\n\n"
        f"Score-Verteilung:\n{score_summary}\n\n"
        f"Ergebnisse: data/curation_results.json"
    )
    await _tg(tg_msg)
    logger.info("ProductCurator fertig: archiviert=%d, aktiviert=%d, total=%d",
                archived_ok, activated_ok, total)

    return {
        "archived":       archived_ok,
        "activated":      activated_ok,
        "total_reviewed": total,
    }


# ─── CLI-Einstiegspunkt ───────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(run_product_curation())
    print(json.dumps(result, indent=2))
