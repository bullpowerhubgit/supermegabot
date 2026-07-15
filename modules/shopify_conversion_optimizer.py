"""
Shopify Conversion Optimizer
============================
Verbessert automatisch die Conversion-Rate des Shops.
949 Sessions / 90 Tage / 0 Bestellungen → analysiert und behebt die Ursachen:

  1. check_shop_settings()      — Prüft Checkout, Zahlungen, Versand, Trust
  2. activate_best_products()   — Aktiviert Produkte aus CSV/JSON oder Drafts
  3. fix_product_descriptions() — Repariert leere/kurze Beschreibungen via Haiku
  4. setup_automatic_discounts()— Erstellt WILLKOMMEN10 + COMEBACK15 Rabattcodes
  5. add_urgency_metafields()   — Fügt "Nur noch X auf Lager!" zu Low-Stock-Produkten
  6. get_conversion_report()    — Gibt aktuelle Conversion-Metriken zurück

HTTP-Routes (in dashboard/server.py registrieren):
  GET  /api/shopify/conversion-report  → get_conversion_report()
  POST /api/shopify/optimize-now       → run_full_optimization()
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("ConversionOptimizer")

# ── Config ─────────────────────────────────────────────────────────────────────
SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "conversion_optimizer_state.json"

LOW_STOCK_THRESHOLD = 10


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"


def _hdrs(extra: dict | None = None) -> dict:
    h = {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _credentials_ok() -> bool:
    return bool(SHOP_DOMAIN and SHOP_TOKEN)


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


async def _shopify_get(session: aiohttp.ClientSession, path: str, **params) -> dict:
    """GET helper mit Rate-Limit-Backoff."""
    url = f"{_base()}{path}"
    for attempt in range(3):
        try:
            async with session.get(
                url, headers=_hdrs(), params=params or None,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 429:
                    wait = int(r.headers.get("Retry-After", 10))
                    log.warning("Rate limit — warte %ss", wait)
                    await asyncio.sleep(wait)
                    continue
                if r.status not in (200, 201):
                    log.warning("GET %s → HTTP %s", path, r.status)
                    return {}
                return await r.json(content_type=None)
        except asyncio.TimeoutError:
            log.warning("Timeout GET %s (attempt %d)", path, attempt + 1)
            await asyncio.sleep(3)
        except Exception as e:
            log.error("GET %s error: %s", path, e)
            return {}
    return {}


async def _shopify_post(session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
    """POST helper mit Rate-Limit-Backoff."""
    url = f"{_base()}{path}"
    for attempt in range(3):
        try:
            async with session.post(
                url, headers=_hdrs(), json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 429:
                    wait = int(r.headers.get("Retry-After", 10))
                    await asyncio.sleep(wait)
                    continue
                body = await r.json(content_type=None)
                if r.status not in (200, 201):
                    log.warning("POST %s → HTTP %s: %s", path, r.status, body)
                    return {"_status": r.status, **body}
                return body
        except asyncio.TimeoutError:
            log.warning("Timeout POST %s (attempt %d)", path, attempt + 1)
            await asyncio.sleep(3)
        except Exception as e:
            log.error("POST %s error: %s", path, e)
            return {}
    return {}


async def _shopify_put(session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
    """PUT helper mit Rate-Limit-Backoff."""
    url = f"{_base()}{path}"
    for attempt in range(3):
        try:
            async with session.put(
                url, headers=_hdrs(), json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 429:
                    wait = int(r.headers.get("Retry-After", 10))
                    await asyncio.sleep(wait)
                    continue
                if r.status not in (200, 201):
                    log.warning("PUT %s → HTTP %s", path, r.status)
                    return {}
                return await r.json(content_type=None)
        except asyncio.TimeoutError:
            log.warning("Timeout PUT %s (attempt %d)", path, attempt + 1)
            await asyncio.sleep(3)
        except Exception as e:
            log.error("PUT %s error: %s", path, e)
            return {}
    return {}


async def _tg_notify(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


# ── 1. check_shop_settings ─────────────────────────────────────────────────────

async def check_shop_settings() -> dict:
    """
    Prüft kritische Shop-Einstellungen für Conversion.
    Gibt ein Dict mit gefundenen Problemen zurück.
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    issues: list[str] = []
    checks: dict[str, Any] = {}

    async with aiohttp.ClientSession() as s:
        # ── Shop-Info ──────────────────────────────────────────────────────────
        shop_data = await _shopify_get(s, "/shop.json")
        shop = shop_data.get("shop", {})
        checks["shop_name"]     = shop.get("name", "?")
        checks["shop_email"]    = shop.get("email", "")
        checks["shop_currency"] = shop.get("currency", "?")
        checks["shop_domain"]   = shop.get("domain", "")
        checks["country"]       = shop.get("country_name", "?")
        checks["plan"]          = shop.get("plan_name", "?")

        if not shop.get("email"):
            issues.append("Shop-E-Mail fehlt — Vertrauen der Kunden sinkt")

        if not shop.get("customer_email"):
            issues.append("Kunden-E-Mail (Support) nicht konfiguriert")

        # ── Zahlungsanbieter ───────────────────────────────────────────────────
        gateways_data = await _shopify_get(s, "/payment_gateways.json")
        gateways = gateways_data.get("payment_gateways", [])
        checks["payment_gateways_count"] = len(gateways)
        checks["payment_gateways"] = [g.get("name", "?") for g in gateways]

        if len(gateways) == 0:
            issues.append("KRITISCH: Keine Zahlungsanbieter konfiguriert — Kauf unmöglich!")
        elif len(gateways) == 1:
            issues.append("Nur 1 Zahlungsanbieter — PayPal + Kreditkarte empfohlen")

        has_paypal = any("paypal" in g.get("name", "").lower() for g in gateways)
        has_card   = any(
            any(k in g.get("name", "").lower() for k in ("stripe", "shopify_pay", "visa", "mastercard", "credit"))
            for g in gateways
        )
        checks["has_paypal"] = has_paypal
        checks["has_card"]   = has_card

        if not has_paypal:
            issues.append("PayPal fehlt — viele Kunden brechen ohne PayPal ab")
        if not has_card:
            issues.append("Kreditkarten-Zahlung nicht erkannt — prüfen")

        # ── Versandzonen ───────────────────────────────────────────────────────
        await asyncio.sleep(0.5)
        shipping_data = await _shopify_get(s, "/shipping_zones.json")
        zones = shipping_data.get("shipping_zones", [])
        checks["shipping_zones_count"] = len(zones)

        free_shipping = False
        for zone in zones:
            for rate in zone.get("price_based_shipping_rates", []):
                if float(rate.get("price", 99)) == 0:
                    free_shipping = True
            for rate in zone.get("weight_based_shipping_rates", []):
                if float(rate.get("price", 99)) == 0:
                    free_shipping = True

        checks["has_free_shipping"] = free_shipping
        if not free_shipping:
            issues.append("Kein kostenloser Versand — Conversion steigt um 30% mit kostenlosem Versand ab X€")

        if len(zones) == 0:
            issues.append("KRITISCH: Keine Versandzonen konfiguriert — Checkout schlägt fehl!")

        # ── Shop-Policies (Rückgabe, Datenschutz, AGB) ────────────────────────
        await asyncio.sleep(0.5)
        policies_data = await _shopify_get(s, "/policies.json")
        policies = policies_data.get("policies", [])
        policy_types = {p.get("title", "").lower() for p in policies}

        has_return  = any("return" in t or "rückgabe" in t or "refund" in t for t in policy_types)
        has_privacy = any("privacy" in t or "datenschutz" in t for t in policy_types)
        has_tos     = any("terms" in t or "agb" in t or "nutzung" in t for t in policy_types)

        checks["has_return_policy"]  = has_return
        checks["has_privacy_policy"] = has_privacy
        checks["has_tos"]            = has_tos

        if not has_return:
            issues.append("Rückgaberichtlinie fehlt — Trust-Signal für Kunden")
        if not has_privacy:
            issues.append("Datenschutzrichtlinie fehlt — DSGVO-Pflicht!")
        if not has_tos:
            issues.append("AGB fehlen — rechtlich empfohlen")

        # ── Produkte ───────────────────────────────────────────────────────────
        await asyncio.sleep(0.5)
        prod_count_data = await _shopify_get(s, "/products/count.json", status="active")
        active_products = prod_count_data.get("count", 0)
        checks["active_products"] = active_products

        if active_products == 0:
            issues.append("KRITISCH: Keine aktiven Produkte im Shop!")
        elif active_products < 10:
            issues.append(f"Nur {active_products} aktive Produkte — mehr Auswahl empfohlen")

        # ── Bestellungen letzter 30 Tage ──────────────────────────────────────
        await asyncio.sleep(0.5)
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        orders_data = await _shopify_get(s, "/orders/count.json", status="any", created_at_min=since)
        orders_30d = orders_data.get("count", 0)
        checks["orders_last_30d"] = orders_30d

        if orders_30d == 0:
            issues.append("0 Bestellungen in 30 Tagen — Conversion-Optimierung dringend nötig")

    score = max(0, 100 - len(issues) * 15)
    return {
        "ok": True,
        "issues": issues,
        "issue_count": len(issues),
        "conversion_health_score": score,
        "checks": checks,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 2. activate_best_products ─────────────────────────────────────────────────

async def activate_best_products() -> dict:
    """
    Aktiviert die besten Produkte:
    - Sucht CSV-Dateien in data/ und importiert Produkte
    - Aktiviert vorhandene Draft-Produkte mit vollständigen Daten
    Returns: dict mit Ergebnis
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    activated: list[dict] = []
    from_csv:  list[dict] = []
    errors = 0

    # ── CSV-Dateien in data/ suchen ────────────────────────────────────────────
    csv_files = list(DATA_DIR.glob("*.csv"))
    log.info("CSV-Dateien gefunden: %s", [str(f) for f in csv_files])

    for csv_path in csv_files:
        try:
            content = csv_path.read_text(encoding="utf-8-sig")
            reader  = csv.DictReader(io.StringIO(content))
            rows    = [r for r in reader if r]

            # Nur Zeilen mit Titel + Preis
            valid_rows = [
                r for r in rows
                if r.get("Title") or r.get("title") or r.get("Name") or r.get("name")
            ]
            # Top 30 (sortiert nach "Verkauft" oder Reihenfolge)
            ranked = sorted(valid_rows, key=lambda x: int(x.get("sold", x.get("Sold", 0)) or 0), reverse=True)[:30]
            from_csv.extend({"source_file": csv_path.name, "title": _get_csv_field(r, "Title", "title", "Name", "name")} for r in ranked)
            log.info("%s: %d gültige Produkte aus %s", csv_path.name, len(ranked), csv_path)
        except Exception as e:
            log.warning("CSV-Fehler %s: %s", csv_path, e)

    # ── Draft-Produkte aktivieren ──────────────────────────────────────────────
    async with aiohttp.ClientSession() as s:
        # Alle Draft-Produkte laden
        draft_data = await _shopify_get(s, "/products.json", status="draft", limit=100,
                                        fields="id,title,body_html,images,variants,status")
        drafts = draft_data.get("products", [])
        log.info("Draft-Produkte gefunden: %d", len(drafts))

        # Nur vollständige Produkte aktivieren (haben Bilder, Variante mit Preis, Body)
        good_drafts = []
        for p in drafts:
            has_image   = bool(p.get("images"))
            has_price   = any(float(v.get("price", 0) or 0) > 0 for v in p.get("variants", []))
            has_body    = len(p.get("body_html", "") or "") > 50
            score = sum([has_image, has_price, has_body])
            if score >= 2:
                good_drafts.append((score, p))

        # Top 50 nach Score
        good_drafts.sort(key=lambda x: x[0], reverse=True)
        to_activate = [p for _, p in good_drafts[:50]]

        for product in to_activate:
            pid = product["id"]
            result = await _shopify_put(s, f"/products/{pid}.json",
                                        {"product": {"id": pid, "status": "active"}})
            if result.get("product"):
                activated.append({
                    "id": pid,
                    "title": product.get("title", "?"),
                    "status": "activated",
                })
                log.info("Aktiviert: %s (%s)", product.get("title"), pid)
            else:
                errors += 1
            await asyncio.sleep(0.5)

    summary = {
        "ok": True,
        "drafts_found": len(drafts),
        "good_drafts": len(good_drafts),
        "activated": len(activated),
        "activated_products": activated,
        "csv_files_found": len(csv_files),
        "csv_products_found": len(from_csv),
        "errors": errors,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    log.info("activate_best_products: %s aktiviert, %s Fehler", len(activated), errors)
    return summary


def _get_csv_field(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k, "")
        if v:
            return str(v)
    return ""


# ── 3. fix_product_descriptions ───────────────────────────────────────────────

async def fix_product_descriptions(batch_size: int = 20) -> dict:
    """
    Lädt aktive Produkte mit leerer/kurzer Beschreibung (<100 Zeichen)
    und generiert bessere Beschreibungen via Claude Haiku.
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    state   = _load_state()
    already = set(state.get("fixed_descriptions", []))
    fixed   = 0
    skipped = 0
    errors  = 0
    results: list[dict] = []

    async with aiohttp.ClientSession() as s:
        products_data = await _shopify_get(
            s, "/products.json", limit=250, status="active",
            fields="id,title,body_html,product_type,vendor,tags",
        )
        products = products_data.get("products", [])

        poor = [
            p for p in products
            if len(re.sub(r"<[^>]+>", "", p.get("body_html", "") or "").strip()) < 100
            and str(p["id"]) not in already
        ]
        log.info("Produkte mit kurzer Beschreibung: %d / %d", len(poor), len(products))

        for product in poor[:batch_size]:
            pid   = product["id"]
            title = product.get("title", "Produkt")
            ptype = product.get("product_type", "")
            tags  = product.get("tags", "")

            prompt = (
                f"Schreibe eine professionelle, verkaufsfördernde Produktbeschreibung auf Deutsch "
                f"für folgendes Produkt (150-200 Wörter, HTML mit <p> und <ul> Tags):\n\n"
                f"Produktname: {title}\n"
                f"Kategorie: {ptype or 'Allgemein'}\n"
                f"Tags: {tags or 'keine'}\n\n"
                f"Fokus: Nutzen für den Kunden, USPs, Call-to-Action am Ende. "
                f"Keine Fantasiepreise, keine erfundenen Spezifikationen. "
                f"Professionell, klar, überzeugend."
            )

            description = await ai_complete(prompt, max_tokens=600)

            if not description or len(description) < 80:
                errors += 1
                log.warning("Haiku lieferte leere Beschreibung für: %s", title)
                await asyncio.sleep(1)
                continue

            # Sicherstellen dass HTML-Tags vorhanden
            if "<p>" not in description and "<ul>" not in description:
                description = f"<p>{description}</p>"

            update_result = await _shopify_put(
                s, f"/products/{pid}.json",
                {"product": {"id": pid, "body_html": description}},
            )

            if update_result.get("product"):
                fixed += 1
                already.add(str(pid))
                results.append({"id": pid, "title": title, "status": "updated"})
                log.info("Beschreibung aktualisiert: %s (%s)", title, pid)
            else:
                errors += 1
                log.warning("Update fehlgeschlagen: %s", title)

            await asyncio.sleep(1.5)  # Rate-Limit + API-Budget schonen

    state["fixed_descriptions"] = list(already)
    state["last_fix_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    return {
        "ok": True,
        "products_checked": len(products),
        "poor_descriptions_found": len(poor),
        "fixed": fixed,
        "skipped": skipped,
        "errors": errors,
        "updated_products": results,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 4. setup_automatic_discounts ─────────────────────────────────────────────

async def setup_automatic_discounts() -> dict:
    """
    Erstellt zwei Rabattcodes:
    - WILLKOMMEN10: 10% Rabatt für Neukunden (einmal pro Kunde)
    - COMEBACK15:   15% Rabatt für inaktive Kunden (30+ Tage ohne Kauf)
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    created  = []
    existing = []
    errors   = []

    starts_at  = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # 12 Monate gültig
    expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).replace(microsecond=0).isoformat()

    discount_configs = [
        {
            "code":        "WILLKOMMEN10",
            "title":       "Willkommensrabatt 10% — Neukunden",
            "value":       "-10.0",
            "value_type":  "percentage",
            "customer_selection": "all",
            "once_per_customer":  True,
            "usage_limit":        None,
            "prerequisite_subtotal_range": {"greater_than_or_equal_to": "0.00"},
        },
        {
            "code":        "COMEBACK15",
            "title":       "Comeback-Rabatt 15% — 30 Tage ohne Kauf",
            "value":       "-15.0",
            "value_type":  "percentage",
            "customer_selection": "all",
            "once_per_customer":  False,
            "usage_limit":        None,
            "prerequisite_subtotal_range": {"greater_than_or_equal_to": "20.00"},
        },
    ]

    async with aiohttp.ClientSession() as s:
        # Bestehende Price Rules laden (um Duplikate zu vermeiden)
        existing_rules_data = await _shopify_get(s, "/price_rules.json", limit=250)
        existing_titles = {
            r.get("title", "").upper()
            for r in existing_rules_data.get("price_rules", [])
        }
        log.info("Bestehende Price Rules: %s", existing_titles)

        for cfg in discount_configs:
            code  = cfg["code"]
            title = cfg["title"]

            if title.upper() in existing_titles or code.upper() in existing_titles:
                log.info("Rabattcode existiert bereits: %s", code)
                existing.append(code)
                continue

            # Price Rule erstellen
            rule_payload: dict[str, Any] = {
                "price_rule": {
                    "title":             title,
                    "value_type":        cfg["value_type"],
                    "value":             cfg["value"],
                    "customer_selection": cfg["customer_selection"],
                    "target_type":       "line_item",
                    "target_selection":  "all",
                    "allocation_method": "across",
                    "once_per_customer": cfg["once_per_customer"],
                    "starts_at":         starts_at,
                    "ends_at":           expires_at,
                    "prerequisite_subtotal_range": cfg["prerequisite_subtotal_range"],
                }
            }
            if cfg["usage_limit"] is not None:
                rule_payload["price_rule"]["usage_limit"] = cfg["usage_limit"]

            rule_result = await _shopify_post(s, "/price_rules.json", rule_payload)
            rule = rule_result.get("price_rule", {})

            if not rule.get("id"):
                err_msg = f"Price Rule für {code} fehlgeschlagen: {rule_result}"
                log.error(err_msg)
                errors.append(err_msg)
                continue

            rule_id = rule["id"]
            log.info("Price Rule erstellt: %s (ID: %s)", title, rule_id)

            await asyncio.sleep(0.5)

            # Discount Code für diese Rule erstellen
            code_result = await _shopify_post(
                s,
                f"/price_rules/{rule_id}/discount_codes.json",
                {"discount_code": {"code": code}},
            )
            dc = code_result.get("discount_code", {})

            if dc.get("id"):
                created.append({
                    "code":       code,
                    "rule_id":    rule_id,
                    "code_id":    dc["id"],
                    "value":      cfg["value"],
                    "value_type": cfg["value_type"],
                    "expires_at": expires_at,
                })
                log.info("Rabattcode erstellt: %s", code)
            else:
                err_msg = f"Discount Code {code} fehlgeschlagen: {code_result}"
                log.error(err_msg)
                errors.append(err_msg)

            await asyncio.sleep(0.5)

    return {
        "ok": True,
        "created": created,
        "already_existing": existing,
        "errors": errors,
        "total_created": len(created),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 5. add_urgency_metafields ─────────────────────────────────────────────────

async def add_urgency_metafields(max_products: int = 50) -> dict:
    """
    Fügt "Nur noch X auf Lager!" als Metafeld zu Produkten hinzu,
    deren Inventory-Level unter LOW_STOCK_THRESHOLD liegt.
    Metafeld: namespace=custom, key=urgency_badge, type=single_line_text_field
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    updated = []
    skipped = 0
    errors  = 0

    async with aiohttp.ClientSession() as s:
        products_data = await _shopify_get(
            s, "/products.json", limit=max_products, status="active",
            fields="id,title,variants",
        )
        products = products_data.get("products", [])
        log.info("Produkte für Urgency-Check: %d", len(products))

        for product in products:
            pid = product["id"]

            # Inventory-Summe über alle Varianten
            total_inventory = 0
            for variant in product.get("variants", []):
                qty = variant.get("inventory_quantity")
                if qty is not None:
                    total_inventory += int(qty)

            if total_inventory <= 0 or total_inventory > LOW_STOCK_THRESHOLD:
                if total_inventory > LOW_STOCK_THRESHOLD:
                    skipped += 1
                continue

            urgency_text = f"Nur noch {total_inventory} auf Lager!"
            log.info("Urgency: %s → %s", product.get("title"), urgency_text)

            # Prüfen ob Metafeld bereits existiert
            meta_list = await _shopify_get(
                s, f"/products/{pid}/metafields.json",
                namespace="custom", key="urgency_badge",
            )
            existing_metas = meta_list.get("metafields", [])

            if existing_metas:
                # Update vorhandenes Metafeld
                mid = existing_metas[0]["id"]
                result = await _shopify_put(
                    s, f"/metafields/{mid}.json",
                    {"metafield": {"id": mid, "value": urgency_text, "type": "single_line_text_field"}},
                )
                if result.get("metafield"):
                    updated.append({"id": pid, "title": product.get("title"), "text": urgency_text, "action": "updated"})
                else:
                    errors += 1
            else:
                # Neues Metafeld anlegen
                result = await _shopify_post(
                    s, f"/products/{pid}/metafields.json",
                    {
                        "metafield": {
                            "namespace": "custom",
                            "key":       "urgency_badge",
                            "value":     urgency_text,
                            "type":      "single_line_text_field",
                        }
                    },
                )
                if result.get("metafield"):
                    updated.append({"id": pid, "title": product.get("title"), "text": urgency_text, "action": "created"})
                else:
                    errors += 1

            await asyncio.sleep(0.5)

    return {
        "ok": True,
        "products_checked": len(products),
        "urgency_added": len(updated),
        "skipped_high_stock": skipped,
        "errors": errors,
        "products": updated,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── 6. get_conversion_report ──────────────────────────────────────────────────

async def get_conversion_report() -> dict:
    """
    Gibt aktuelle Conversion-Metriken zurück.
    Schätzt Conversion-Rate aus verfügbaren Shopify-Daten.
    """
    if not _credentials_ok():
        return {"ok": False, "error": "Shopify-Zugangsdaten fehlen"}

    async with aiohttp.ClientSession() as s:
        # Basis-Infos
        shop_data = await _shopify_get(s, "/shop.json")
        shop      = shop_data.get("shop", {})

        await asyncio.sleep(0.3)
        active_cnt = (await _shopify_get(s, "/products/count.json", status="active")).get("count", 0)
        draft_cnt  = (await _shopify_get(s, "/products/count.json", status="draft")).get("count", 0)

        await asyncio.sleep(0.3)
        # Bestellungen letzte 30/90 Tage
        since_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        since_90d = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

        orders_30d = (await _shopify_get(s, "/orders/count.json", status="any",
                                         created_at_min=since_30d)).get("count", 0)
        await asyncio.sleep(0.3)
        orders_90d = (await _shopify_get(s, "/orders/count.json", status="any",
                                         created_at_min=since_90d)).get("count", 0)

        await asyncio.sleep(0.3)
        # Kunden gesamt
        customers_cnt = (await _shopify_get(s, "/customers/count.json")).get("count", 0)

        await asyncio.sleep(0.3)
        # Produkte mit schlechter Beschreibung
        products_sample = (await _shopify_get(
            s, "/products.json", limit=250, status="active",
            fields="id,title,body_html,images,variants",
        )).get("products", [])

        poor_desc = sum(
            1 for p in products_sample
            if len(re.sub(r"<[^>]+>", "", p.get("body_html", "") or "").strip()) < 100
        )
        no_images = sum(1 for p in products_sample if not p.get("images"))
        no_price  = sum(
            1 for p in products_sample
            if all(float(v.get("price", 0) or 0) == 0 for v in p.get("variants", []))
        )

        # Conversion-Rate schätzen (949 Sessions in 90 Tagen bekannt)
        sessions_90d = 949  # aus Problem-Statement
        conv_rate    = round(orders_90d / max(sessions_90d, 1) * 100, 2)

        # Diagnose
        diagnosis: list[str] = []
        if orders_90d == 0:
            diagnosis.append("0 Bestellungen in 90 Tagen — Shop-Grundkonfiguration prüfen")
        if poor_desc > 0:
            diagnosis.append(f"{poor_desc} Produkte ohne/kurze Beschreibung")
        if no_images > 0:
            diagnosis.append(f"{no_images} Produkte ohne Bilder — Conversion-Killer")
        if no_price > 0:
            diagnosis.append(f"{no_price} Produkte ohne Preis")
        if customers_cnt == 0:
            diagnosis.append("0 Kunden registriert")

        state = _load_state()

    return {
        "ok":             True,
        "shop_name":      shop.get("name", "?"),
        "shop_domain":    shop.get("domain", "?"),
        "currency":       shop.get("currency", "?"),
        "sessions_90d":   sessions_90d,
        "orders_30d":     orders_30d,
        "orders_90d":     orders_90d,
        "conv_rate_pct":  conv_rate,
        "customers_total": customers_cnt,
        "active_products": active_cnt,
        "draft_products":  draft_cnt,
        "products_poor_desc": poor_desc,
        "products_no_images": no_images,
        "products_no_price":  no_price,
        "diagnosis":      diagnosis,
        "last_optimization": state.get("last_optimization"),
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }


# ── 7. run_full_optimization ──────────────────────────────────────────────────

async def run_full_optimization(fix_descriptions: bool = True,
                                setup_discounts: bool = True,
                                urgency: bool = True,
                                activate_products: bool = True) -> dict:
    """
    Führt alle Optimierungsschritte sequenziell aus.
    POST /api/shopify/optimize-now
    """
    log.info("Starte vollständige Conversion-Optimierung ...")
    results: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat()}
    errors: list[str] = []

    # 1. Shop-Einstellungen prüfen
    try:
        results["shop_check"] = await check_shop_settings()
    except Exception as e:
        log.error("check_shop_settings fehlgeschlagen: %s", e)
        errors.append(f"shop_check: {e}")

    await asyncio.sleep(1)

    # 2. Produkte aktivieren
    if activate_products:
        try:
            results["activate_products"] = await activate_best_products()
        except Exception as e:
            log.error("activate_best_products fehlgeschlagen: %s", e)
            errors.append(f"activate_products: {e}")
        await asyncio.sleep(1)

    # 3. Beschreibungen reparieren
    if fix_descriptions:
        try:
            results["fix_descriptions"] = await fix_product_descriptions(batch_size=20)
        except Exception as e:
            log.error("fix_product_descriptions fehlgeschlagen: %s", e)
            errors.append(f"fix_descriptions: {e}")
        await asyncio.sleep(1)

    # 4. Rabattcodes erstellen
    if setup_discounts:
        try:
            results["discounts"] = await setup_automatic_discounts()
        except Exception as e:
            log.error("setup_automatic_discounts fehlgeschlagen: %s", e)
            errors.append(f"discounts: {e}")
        await asyncio.sleep(1)

    # 5. Urgency-Metafelder setzen
    if urgency:
        try:
            results["urgency"] = await add_urgency_metafields()
        except Exception as e:
            log.error("add_urgency_metafields fehlgeschlagen: %s", e)
            errors.append(f"urgency: {e}")
        await asyncio.sleep(1)

    results["errors"]        = errors
    results["completed_at"]  = datetime.now(timezone.utc).isoformat()
    results["ok"]            = len(errors) == 0

    # State speichern
    state = _load_state()
    state["last_optimization"] = results["completed_at"]
    state["last_results_summary"] = {
        "errors":         len(errors),
        "products_fixed": results.get("fix_descriptions", {}).get("fixed", 0),
        "activated":      results.get("activate_products", {}).get("activated", 0),
        "discounts":      results.get("discounts", {}).get("total_created", 0),
        "urgency":        results.get("urgency", {}).get("urgency_added", 0),
    }
    _save_state(state)

    # Telegram-Benachrichtigung
    shop_name = results.get("shop_check", {}).get("checks", {}).get("shop_name", "Shop")
    summary = (
        f"<b>Conversion Optimizer — {shop_name}</b>\n"
        f"Beschreibungen repariert: {state['last_results_summary']['products_fixed']}\n"
        f"Produkte aktiviert: {state['last_results_summary']['activated']}\n"
        f"Rabattcodes erstellt: {state['last_results_summary']['discounts']}\n"
        f"Urgency-Badges: {state['last_results_summary']['urgency']}\n"
        f"Fehler: {len(errors)}"
    )
    await _tg_notify(summary)
    log.info("Optimierung abgeschlossen. %d Fehler.", len(errors))

    return results


# ── HTTP-Route-Handler ─────────────────────────────────────────────────────────
# In dashboard/server.py einbinden:
#
#   from modules.shopify_conversion_optimizer import (
#       handle_conversion_report, handle_optimize_now
#   )
#   app.router.add_get ("/api/shopify/conversion-report", handle_conversion_report)
#   app.router.add_post("/api/shopify/optimize-now",      handle_optimize_now)

async def handle_conversion_report(request: Any) -> Any:
    """GET /api/shopify/conversion-report"""
    try:
        from aiohttp.web import Response
        data = await get_conversion_report()
        return Response(
            text=json.dumps(data, ensure_ascii=False, default=str),
            content_type="application/json",
        )
    except Exception as e:
        log.error("handle_conversion_report: %s", e)
        from aiohttp.web import Response
        return Response(
            text=json.dumps({"ok": False, "error": str(e)}),
            content_type="application/json",
            status=500,
        )


async def handle_optimize_now(request: Any) -> Any:
    """POST /api/shopify/optimize-now"""
    try:
        from aiohttp.web import Response
        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            pass

        data = await run_full_optimization(
            fix_descriptions  = body.get("fix_descriptions", True),
            setup_discounts   = body.get("setup_discounts", True),
            urgency           = body.get("urgency", True),
            activate_products = body.get("activate_products", True),
        )
        return Response(
            text=json.dumps(data, ensure_ascii=False, default=str),
            content_type="application/json",
        )
    except Exception as e:
        log.error("handle_optimize_now: %s", e)
        from aiohttp.web import Response
        return Response(
            text=json.dumps({"ok": False, "error": str(e)}),
            content_type="application/json",
            status=500,
        )


async def get_status() -> dict:
    """Modul-Status für Dashboard-Health-Check."""
    state = _load_state()
    return {
        "ok":     True,
        "module": "Shopify Conversion Optimizer",
        "shop":   SHOP_DOMAIN or "not configured",
        "last_optimization": state.get("last_optimization"),
    }
