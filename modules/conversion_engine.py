#!/usr/bin/env python3
"""
Conversion Engine — ineedit.com.co
Analysiert Shopify-Funnel, identifiziert Bottlenecks und führt tägliche
Optimierungen durch (fehlende Beschreibungen, Bilder, Preisfehler).

Scheduler-Exports:
  - run_conversion_scan()    -> str
  - run_daily_optimization() -> str
  - analyze_funnel()         -> dict
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv

# ── Umgebung laden ────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("ConversionEngine")

# ── Pfade ─────────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent.parent
_DATA_DIR = _BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_STATE_FILE = _DATA_DIR / "conversion_engine.json"


# ── Shopify-Konfiguration ─────────────────────────────────────────────────────
def _shopify_cfg() -> Tuple[str, str, str]:
    """Gibt (token, domain, version) zurück oder wirft ValueError."""
    token = (
        os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
    domain = (
        os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        or os.getenv("SHOPIFY_STORE_DOMAIN", "")
    )
    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    if not token or not domain:
        raise ValueError(
            "SHOPIFY_ADMIN_API_TOKEN (oder SHOPIFY_ACCESS_TOKEN) "
            "und SHOPIFY_SHOP_DOMAIN müssen gesetzt sein."
        )
    domain = domain.rstrip("/")
    if not domain.startswith("https://"):
        domain = f"https://{domain}"
    return token, domain, version


def _shopify_headers(token: str) -> Dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Telegram-Hilfsfunktion ────────────────────────────────────────────────────
async def _send_telegram(
    session: aiohttp.ClientSession,
    message: str,
    parse_mode: str = "HTML",
) -> None:
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tg_token or not chat_id:
        log.warning("Telegram-Credentials fehlen — Alert nicht gesendet.")
        return
    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
    try:
        async with session.post(
            url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning("Telegram-Fehler %s: %s", resp.status, body[:200])
            else:
                log.info("Telegram-Alert gesendet.")
    except Exception as exc:
        log.warning("Telegram-Ausnahme: %s", exc)


# ── State-Verwaltung ──────────────────────────────────────────────────────────
def _load_state() -> Dict[str, Any]:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("State-Datei defekt, starte neu: %s", exc)
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        _STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        log.error("State konnte nicht gespeichert werden: %s", exc)


# ── Shopify-API-Hilfsfunktionen ───────────────────────────────────────────────
async def _get_orders_last_24h(
    session: aiohttp.ClientSession,
    token: str,
    domain: str,
    version: str,
) -> List[Dict]:
    """Lädt alle Bestellungen der letzten 24 Stunden."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    url = (
        f"{domain}/admin/api/{version}/orders.json"
        f"?created_at_min={since}&status=any&limit=250"
    )
    orders: List[Dict] = []
    headers = _shopify_headers(token)
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                orders = data.get("orders", [])
            else:
                body = await resp.text()
                log.warning(
                    "Orders-API Fehler %s: %s", resp.status, body[:300]
                )
    except Exception as exc:
        log.error("Orders-Request fehlgeschlagen: %s", exc)
    return orders


async def _get_analytics_sessions(
    session: aiohttp.ClientSession,
    token: str,
    domain: str,
    version: str,
) -> Optional[int]:
    """
    Versucht Shop-Sessions über Analytics-API zu lesen.
    Gibt None zurück wenn die API nicht verfügbar ist (Plus-Feature).
    """
    url = f"{domain}/admin/api/{version}/analytics/reports.json"
    headers = _shopify_headers(token)
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                reports = data.get("reports", [])
                for r in reports:
                    if "session" in r.get("name", "").lower():
                        return int(r.get("value", 0))
            elif resp.status in (403, 404, 422):
                log.info(
                    "Analytics-API nicht verfügbar (Status %s) — Shopify Plus Feature.",
                    resp.status,
                )
            else:
                log.warning("Analytics-API Status %s", resp.status)
    except Exception as exc:
        log.warning("Analytics-Request fehlgeschlagen: %s", exc)
    return None


async def _get_all_active_products(
    session: aiohttp.ClientSession,
    token: str,
    domain: str,
    version: str,
) -> List[Dict]:
    """Lädt alle aktiven Produkte (cursor-paginiert)."""
    headers = _shopify_headers(token)
    products: List[Dict] = []
    page_info: Optional[str] = None
    limit = 250

    while True:
        if page_info:
            url = (
                f"{domain}/admin/api/{version}/products.json"
                f"?status=active&limit={limit}&page_info={page_info}"
            )
        else:
            url = (
                f"{domain}/admin/api/{version}/products.json"
                f"?status=active&limit={limit}"
            )

        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.warning(
                        "Products-API Fehler %s: %s", resp.status, body[:300]
                    )
                    break
                data = await resp.json()
                batch = data.get("products", [])
                products.extend(batch)

                # Cursor-Pagination via Link-Header
                link_header = resp.headers.get("Link", "")
                next_page_info: Optional[str] = None
                if 'rel="next"' in link_header:
                    for part in link_header.split(","):
                        if 'rel="next"' in part:
                            start = part.find("page_info=")
                            if start != -1:
                                pi = part[start + 10:]
                                pi = pi.split("&")[0].split(">")[0].strip()
                                next_page_info = pi
                                break
                page_info = next_page_info

                if not page_info or len(batch) < limit:
                    break
        except Exception as exc:
            log.error("Products-Pagination Fehler: %s", exc)
            break

    return products


async def _update_product(
    session: aiohttp.ClientSession,
    token: str,
    domain: str,
    version: str,
    product_id: int,
    payload: Dict,
) -> bool:
    """Aktualisiert ein Produkt via Admin API."""
    url = f"{domain}/admin/api/{version}/products/{product_id}.json"
    headers = _shopify_headers(token)
    try:
        async with session.put(
            url,
            headers=headers,
            json={"product": payload},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                return True
            body = await resp.text()
            log.warning(
                "Produkt %s Update Fehler %s: %s", product_id, resp.status, body[:200]
            )
    except Exception as exc:
        log.error("Produkt %s Update Ausnahme: %s", product_id, exc)
    return False


# ── Bottleneck-Analyse ────────────────────────────────────────────────────────
def _identify_bottleneck(
    sessions: int, add_to_cart: int, checkouts: int, orders: int
) -> List[str]:
    """Bestimmt den schwächsten Funnel-Schritt."""
    bottlenecks: List[str] = []

    if sessions == 0:
        bottlenecks.append("KEIN_TRAFFIC")
        return bottlenecks

    atc_rate = add_to_cart / sessions * 100
    chk_rate = checkouts / sessions * 100
    conv_rate = orders / sessions * 100

    if atc_rate < 2.0:
        bottlenecks.append(f"KEIN_ADD_TO_CART ({atc_rate:.1f}%)")
    elif chk_rate < 1.0:
        bottlenecks.append(f"KEIN_CHECKOUT ({chk_rate:.1f}%)")
    elif conv_rate < 0.5:
        bottlenecks.append(f"CHECKOUT_ABBRUCH ({conv_rate:.1f}%)")
    else:
        bottlenecks.append("OK")

    return bottlenecks


# ── SEO-Templates ─────────────────────────────────────────────────────────────
def _build_seo_description(title: str, product_type: str, tags: str) -> str:
    """Erstellt eine strukturierte Produkt-Beschreibung."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:4]
    if tag_list:
        feature_text = "\n".join(
            f"<li>{t.replace('-', ' ').title()}</li>" for t in tag_list
        )
    else:
        feature_text = (
            "<li>Professionelle Qualität</li>\n<li>Schnelle Lieferung</li>"
        )
    ptype = product_type or "Produkt"

    return (
        f"<h2>{title}</h2>\n"
        f"<p>Entdecken Sie {title} — ein hochwertiges {ptype} für anspruchsvolle Kunden. "
        f"Perfekt für den täglichen Einsatz und langlebige Nutzung.</p>\n"
        f"<h3>Highlights</h3>\n"
        f"<ul>\n{feature_text}\n"
        f"<li>Geprüfte Qualität</li>\n<li>30 Tage Rückgaberecht</li>\n</ul>\n"
        f"<p>Bestellen Sie jetzt und profitieren Sie von schnellem Versand direkt zu Ihnen nach Hause.</p>"
    )


def _build_seo_title(original_title: str) -> str:
    """Verbessert einen zu kurzen Produkttitel für SEO."""
    title = original_title.strip()
    if len(title) < 30:
        return f"{title} — Premium Qualität | Schnelle Lieferung"
    return title


# ── Öffentliche Scheduler-Funktionen ─────────────────────────────────────────

async def run_conversion_scan() -> str:
    """
    Analysiert Shopify-Sessions + Bestellungen der letzten 24h.
    Sendet Telegram-Alert wenn Conversion-Rate < 0.5%.
    Speichert State in data/conversion_engine.json.

    Returns: "Sessions: X | Orders: Y | Rate: Z% | Bottleneck: [...]"
    """
    log.info("Starte Conversion-Scan ...")

    try:
        token, domain, version = _shopify_cfg()
    except ValueError as exc:
        msg = f"ConversionEngine Konfigurationsfehler: {exc}"
        log.error(msg)
        return msg

    state = _load_state()
    now_ts = datetime.now(timezone.utc).isoformat()

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        # 1. Bestellungen der letzten 24h
        orders = await _get_orders_last_24h(http, token, domain, version)
        order_count = len(orders)

        # 2. Sessions über Analytics-API (Shopify Plus) versuchen
        sessions_from_api = await _get_analytics_sessions(http, token, domain, version)

        if sessions_from_api is not None:
            session_count = sessions_from_api
            session_source = "analytics_api"
        else:
            # Fallback: bekannter Baseline-Wert aus State
            session_count = state.get("last_known_sessions_24h", 949)
            session_source = "state_baseline"
            log.info(
                "Analytics-API nicht verfügbar — Baseline: %d Sessions",
                session_count,
            )

        # 3. Conversion-Rate
        conv_rate = (order_count / session_count * 100) if session_count > 0 else 0.0

        # 4. Add-to-Cart + Checkouts aus State (Shopify liefert diese nicht direkt)
        add_to_cart = state.get(
            "last_add_to_cart_24h", max(1, int(session_count * 0.03))
        )
        checkouts = state.get(
            "last_checkouts_24h", max(0, int(session_count * 0.015))
        )

        # 5. Bottleneck identifizieren
        bottlenecks = _identify_bottleneck(
            session_count, add_to_cart, checkouts, order_count
        )

        # 6. State persistieren
        state.update(
            {
                "last_scan_ts": now_ts,
                "last_sessions_24h": session_count,
                "last_orders_24h": order_count,
                "last_conv_rate": conv_rate,
                "last_bottlenecks": bottlenecks,
                "session_source": session_source,
            }
        )
        _save_state(state)

        # 7. Telegram-Alert bei Conversion < 0.5%
        if conv_rate < 0.5:
            alert_msg = (
                f"<b>Conversion-Alert: ineedit.com.co</b>\n\n"
                f"<b>Sessions (24h):</b> {session_count:,}\n"
                f"<b>Bestellungen (24h):</b> {order_count}\n"
                f"<b>Conversion-Rate:</b> {conv_rate:.2f}%\n\n"
                f"<b>Bottleneck:</b> {', '.join(bottlenecks)}\n\n"
                f"Rate unter 0,5% — sofortige Massnahmen erforderlich!\n"
                f"{now_ts[:19]} UTC"
            )
            await _send_telegram(http, alert_msg)
            log.warning(
                "Conversion-Alert: %.2f%% Rate, Bottleneck: %s",
                conv_rate,
                bottlenecks,
            )

    result = (
        f"Sessions: {session_count} | Orders: {order_count} | "
        f"Rate: {conv_rate:.2f}% | Bottleneck: {bottlenecks}"
    )
    log.info("Conversion-Scan abgeschlossen: %s", result)
    return result


async def run_daily_optimization() -> str:
    """
    Prueft alle aktiven Produkte auf:
      - Fehlende Beschreibungen  -> Auto-Fix via SEO-Template
      - Keine Bilder             -> Warnung (kein Auto-Fix)
      - Preis < 5 EUR            -> Warnung
      - Zu kurze Titel           -> Auto-Fix SEO-Titel

    Returns: "Geprueft: X | Fixes: Y"
    """
    log.info("Starte taegliche Produkt-Optimierung ...")

    try:
        token, domain, version = _shopify_cfg()
    except ValueError as exc:
        msg = f"ConversionEngine Konfigurationsfehler: {exc}"
        log.error(msg)
        return msg

    state = _load_state()
    now_ts = datetime.now(timezone.utc).isoformat()

    fixes_applied = 0
    warnings: List[str] = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as http:
        products = await _get_all_active_products(http, token, domain, version)
        checked = len(products)
        log.info("%d aktive Produkte geladen.", checked)

        for product in products:
            pid = product.get("id")
            title = (product.get("title") or "").strip()
            body_html = (product.get("body_html") or "").strip()
            images = product.get("images", [])
            variants = product.get("variants", [])
            product_type = product.get("product_type", "")
            tags = product.get("tags", "")

            update_payload: Dict[str, Any] = {}

            # Pruefung 1: Fehlende / sehr kurze Beschreibung
            if not body_html or len(body_html) < 50:
                update_payload["body_html"] = _build_seo_description(
                    title, product_type, tags
                )
                log.debug(
                    "Produkt %s (%s): Beschreibung ergaenzt.", pid, title[:40]
                )

            # Pruefung 2: Keine Bilder
            if not images:
                warnings.append(f"KEIN_BILD: {title[:50]} (ID: {pid})")
                log.warning(
                    "Produkt %s hat keine Bilder: %s", pid, title[:50]
                )

            # Pruefung 3: Preis < 5 EUR
            for variant in variants:
                try:
                    price = float(variant.get("price", "0") or "0")
                    if 0.0 < price < 5.0:
                        warnings.append(
                            f"PREIS_UNTER_5: {title[:40]} "
                            f"(ID: {pid}, Preis: EUR {price:.2f})"
                        )
                        log.warning(
                            "Produkt %s: Preis unter EUR 5 (EUR %.2f): %s",
                            pid, price, title[:40],
                        )
                        break
                except (ValueError, TypeError):
                    pass

            # Pruefung 4: Titel zu kurz -> SEO-Verbesserung
            if len(title) < 30 and "title" not in update_payload:
                new_title = _build_seo_title(title)
                if new_title != title:
                    update_payload["title"] = new_title
                    log.debug(
                        "Produkt %s: SEO-Titel: %s", pid, new_title[:60]
                    )

            # Update durchfuehren
            if update_payload:
                success = await _update_product(
                    http, token, domain, version, pid, update_payload
                )
                if success:
                    fixes_applied += 1
                    log.info(
                        "Produkt %s (%s) aktualisiert: %s",
                        pid,
                        title[:40],
                        list(update_payload.keys()),
                    )
                else:
                    log.warning("Produkt %s Update fehlgeschlagen.", pid)

                # Rate-Limit schonen
                await asyncio.sleep(0.3)

        # Telegram-Report bei Warnungen
        if warnings:
            warn_text = "\n".join(f"- {w}" for w in warnings[:20])
            excess = max(0, len(warnings) - 20)
            msg = (
                f"<b>Produkt-Optimierung: ineedit.com.co</b>\n\n"
                f"Geprueft: {checked} Produkte\n"
                f"Fixes: {fixes_applied}\n"
                f"Warnungen: {len(warnings)}\n\n"
                f"<b>Probleme (erste 20):</b>\n{warn_text}"
            )
            if excess > 0:
                msg += f"\n... und {excess} weitere"
            msg += f"\n\n{now_ts[:19]} UTC"
            await _send_telegram(http, msg)

    state.update(
        {
            "last_optimization_ts": now_ts,
            "last_optimization_checked": checked,
            "last_optimization_fixes": fixes_applied,
            "last_optimization_warnings": len(warnings),
        }
    )
    _save_state(state)

    result = f"Geprueft: {checked} | Fixes: {fixes_applied}"
    log.info("Taegliche Optimierung abgeschlossen: %s", result)
    return result


async def analyze_funnel() -> dict:
    """
    Analysiert den gesamten Conversion-Funnel.

    Returns:
        {
          "leads": int,
          "orders": int,
          "weakest_stage": str,
          "weakest_rate": float,
          "conversion_steps": [{"stage": str, "count": int, "rate": float}],
          "transition_analysis": [...],
          "overall_conversion_rate": float,
          "analyzed_at": str,
        }
    """
    log.info("Starte Funnel-Analyse ...")

    state = _load_state()

    # Werte aus letztem Scan oder Defaults
    sessions = state.get("last_sessions_24h", 949)
    orders = state.get("last_orders_24h", 0)
    add_to_cart = state.get("last_add_to_cart_24h", max(1, int(sessions * 0.03)))
    checkouts = state.get("last_checkouts_24h", max(0, int(sessions * 0.015)))

    # Frische Bestellungszahl laden
    try:
        token, domain, version = _shopify_cfg()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as http:
            fresh_orders = await _get_orders_last_24h(http, token, domain, version)
            orders = len(fresh_orders)
            state["last_orders_24h"] = orders
            _save_state(state)
    except Exception as exc:
        log.warning(
            "Frische Bestellungen konnten nicht geladen werden: %s", exc
        )

    def safe_rate(numerator: int, denominator: int) -> float:
        return round((numerator / denominator * 100), 2) if denominator > 0 else 0.0

    steps = [
        {
            "stage": "Besucher (Sessions)",
            "count": sessions,
            "rate": 100.0,
        },
        {
            "stage": "Add to Cart",
            "count": add_to_cart,
            "rate": safe_rate(add_to_cart, sessions),
        },
        {
            "stage": "Checkout gestartet",
            "count": checkouts,
            "rate": safe_rate(checkouts, sessions),
        },
        {
            "stage": "Bestellungen",
            "count": orders,
            "rate": safe_rate(orders, sessions),
        },
    ]

    # Uebergangsraten zwischen Stufen
    transition_rates: List[Dict] = []
    for i in range(1, len(steps)):
        prev_count = steps[i - 1]["count"]
        curr_count = steps[i]["count"]
        t_rate = safe_rate(curr_count, prev_count)
        transition_rates.append(
            {
                "from": steps[i - 1]["stage"],
                "to": steps[i]["stage"],
                "rate": t_rate,
            }
        )

    if transition_rates:
        weakest = min(transition_rates, key=lambda x: x["rate"])
        weakest_stage = f"{weakest['from']} -> {weakest['to']}"
        weakest_rate = weakest["rate"]
    else:
        weakest_stage = "Kein Traffic"
        weakest_rate = 0.0

    overall_rate = safe_rate(orders, sessions)

    result = {
        "leads": sessions,
        "orders": orders,
        "weakest_stage": weakest_stage,
        "weakest_rate": weakest_rate,
        "conversion_steps": steps,
        "transition_analysis": transition_rates,
        "overall_conversion_rate": overall_rate,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    log.info(
        "Funnel-Analyse: %d Sessions -> %d Orders (%.2f%%) | Schwach: %s (%.2f%%)",
        sessions,
        orders,
        overall_rate,
        weakest_stage,
        weakest_rate,
    )
    return result


# ── Direktaufruf (Test) ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        print("=== Conversion Scan ===")
        print(await run_conversion_scan())

        print("\n=== Funnel-Analyse ===")
        print(json.dumps(await analyze_funnel(), ensure_ascii=False, indent=2, default=str))

        print("\n=== Taegliche Optimierung ===")
        print(await run_daily_optimization())

    asyncio.run(_main())
