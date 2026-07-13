#!/usr/bin/env python3
"""
GPSR Compliance Engine — General Product Safety Regulation (EU 2023/988)
========================================================================
Automatisierter GPSR-Compliance-Check für Shopify-Produkte.

Gültig ab 13. Dezember 2024 für alle physischen Produkte auf dem EU-Markt.
Verkäufer außerhalb der EU brauchen einen Authorised Representative (AR) in der EU.

Wichtiger Hinweis: Diese Software bietet Checklisten + Dokumenten-Templates.
Die eigentliche Registrierung eines Authorised Representative erfordert eine
registrierte EU-Firma (z.B. GmbH, Ltd., etc.).

Preis: €129/Monat (Stripe Price ID: GPSR_PRICE_ID)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger("GpsrCompliance")

# ── Env ──────────────────────────────────────────────────────────────────────
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOM  = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER  = os.getenv("SHOPIFY_API_VERSION", "2024-10")
GPSR_PRICE   = os.getenv("GPSR_PRICE_ID", "")

# ── GPSR Checklist (12 Prüfpunkte nach EU 2023/988) ──────────────────────

GPSR_CHECKLIST: dict[str, dict[str, Any]] = {
    "risk_assessment": {
        "label":       "Risikoklassifizierung / Risk Assessment",
        "description": "Produkt wurde einer Risikoklassifizierung unterzogen (niedrig/mittel/hoch). "
                       "Technische Unterlagen vorhanden.",
        "required":    True,
        "weight":      15,
        "check_fields": ["tags", "description", "metafields"],
        "keywords":    ["risk", "risiko", "ce", "conformity", "certification"],
    },
    "product_marking": {
        "label":       "Produktkennzeichnung / Product Marking",
        "description": "CE-Zeichen (falls zutreffend), Hersteller-Name/-Adresse, "
                       "Losnummer/Seriennummer, Warnhinweise auf Deutsch.",
        "required":    True,
        "weight":      12,
        "check_fields": ["description", "tags"],
        "keywords":    ["ce ", "lot", "serie", "warnung", "warning", "hersteller"],
    },
    "conformity_declaration": {
        "label":       "Konformitätserklärung / Declaration of Conformity",
        "description": "EU-Konformitätserklärung (DoC) vorhanden, unterzeichnet, "
                       "aktuell (max. 5 Jahre alt).",
        "required":    True,
        "weight":      15,
        "check_fields": ["description", "metafields"],
        "keywords":    ["konformität", "conformity", "declaration", "doc", "eu 2023/988"],
    },
    "authorised_representative": {
        "label":       "Authorised Representative (EU) / Bevollmächtigter",
        "description": "Name und EU-Adresse eines Authorised Representative in der EU angegeben. "
                       "Pflicht für Hersteller außerhalb der EU.",
        "required":    True,
        "weight":      20,
        "check_fields": ["description", "vendor", "metafields"],
        "keywords":    ["authorised rep", "bevollmächtigt", "eu vertreter", "ar eu", "responsible person"],
    },
    "manufacturer_info": {
        "label":       "Herstellerinformationen / Manufacturer Information",
        "description": "Vollständiger Name und Adresse des Herstellers auf dem Produkt "
                       "oder der Verpackung angegeben.",
        "required":    True,
        "weight":      10,
        "check_fields": ["vendor", "description"],
        "keywords":    ["hersteller", "manufacturer", "made by", "hergestellt von"],
    },
    "safety_instructions": {
        "label":       "Sicherheitshinweise / Safety Instructions",
        "description": "Sicherheits- und Gebrauchsanweisungen in der Sprache des "
                       "Bestimmungslandes (Deutsch für DE-Markt).",
        "required":    True,
        "weight":      10,
        "check_fields": ["description", "body_html"],
        "keywords":    ["sicherheits", "safety", "achtung", "vorsicht", "caution", "anleitung"],
    },
    "product_traceability": {
        "label":       "Rückverfolgbarkeit / Product Traceability",
        "description": "Eindeutige Produktidentifikation (SKU, Barcode, EAN, GTIN) vorhanden. "
                       "Charge-/Lotnummer dokumentiert.",
        "required":    True,
        "weight":      8,
        "check_fields": ["sku", "barcode", "tags"],
        "keywords":    ["sku", "ean", "gtin", "barcode", "lot", "charge"],
    },
    "incident_reporting": {
        "label":       "Unfallmeldepflicht / Incident Reporting",
        "description": "Prozess zur Meldung von Produktunfällen an nationale Behörden "
                       "(z.B. RAPEX/Safety Gate) dokumentiert.",
        "required":    False,
        "weight":      5,
        "check_fields": ["description", "metafields"],
        "keywords":    ["rapex", "safety gate", "incident", "unfall", "meldung"],
    },
    "market_surveillance": {
        "label":       "Marktüberwachung / Market Surveillance",
        "description": "Interne Prozesse zur Überwachung von Kundenbeschwerden und "
                       "Sicherheitsvorfällen vorhanden.",
        "required":    False,
        "weight":      5,
        "check_fields": ["description"],
        "keywords":    ["überwachung", "surveillance", "complaint", "beschwerde"],
    },
    "recall_procedure": {
        "label":       "Rückrufverfahren / Recall Procedure",
        "description": "Schriftliches Rückrufverfahren für Sicherheitsrisiken dokumentiert. "
                       "Kontaktdaten für Verbraucher vorhanden.",
        "required":    False,
        "weight":      5,
        "check_fields": ["description", "metafields"],
        "keywords":    ["rückruf", "recall", "rücknahme", "withdrawal"],
    },
    "packaging_labeling": {
        "label":       "Verpackungskennzeichnung / Packaging & Labeling",
        "description": "Verpackung enthält alle gesetzlich vorgeschriebenen Angaben: "
                       "Recycling-Symbole, Materialangaben, Warnhinweise für Kinder.",
        "required":    True,
        "weight":      7,
        "check_fields": ["description", "tags"],
        "keywords":    ["verpackung", "packaging", "recycling", "entsorgung", "material"],
    },
    "digital_product_passport": {
        "label":       "Digitaler Produktpass / Digital Product Passport",
        "description": "Ab 2025/2026 für bestimmte Produktkategorien verpflichtend. "
                       "QR-Code mit Produktinformationen empfohlen.",
        "required":    False,
        "weight":      3,
        "check_fields": ["description", "tags", "metafields"],
        "keywords":    ["dpp", "digital passport", "produktpass", "qr-code"],
    },
}


# ── Core Scan ─────────────────────────────────────────────────────────────

def _collect_searchable_text(product: dict) -> str:
    """Extrahiere durchsuchbaren Text aus einem Shopify-Produkt."""
    parts = [
        product.get("title", ""),
        product.get("body_html", ""),
        product.get("vendor", ""),
        product.get("product_type", ""),
        " ".join(product.get("tags", []) if isinstance(product.get("tags"), list)
                 else str(product.get("tags", "")).split(",")),
    ]
    # Varianten SKU/Barcode
    for var in product.get("variants", []):
        parts.append(var.get("sku", ""))
        parts.append(var.get("barcode", "") or "")
    return " ".join(p for p in parts if p).lower()


def scan_product_for_gpsr(product: dict) -> dict:
    """
    Prüfe ein Shopify-Produkt gegen die GPSR-Checkliste.

    Args:
        product: Shopify-Produkt-Dict (aus Admin API)

    Returns:
        {product_id, product_title, issues, passed, score, compliant, checked_at}
    """
    product_id    = product.get("id", "unknown")
    product_title = product.get("title", "Unbekannt")
    searchable    = _collect_searchable_text(product)

    issues  = []
    passed  = []
    total_weight = 0
    score_weight = 0

    for check_id, check in GPSR_CHECKLIST.items():
        weight   = check["weight"]
        keywords = check.get("keywords", [])
        required = check.get("required", False)
        total_weight += weight

        # Keyword-Suche im Produkttext
        found = any(kw.lower() in searchable for kw in keywords)

        if found:
            score_weight += weight
            passed.append({
                "check_id": check_id,
                "label":    check["label"],
            })
        else:
            severity = "KRITISCH" if required else "EMPFOHLEN"
            issues.append({
                "check_id":    check_id,
                "label":       check["label"],
                "description": check["description"],
                "severity":    severity,
                "required":    required,
                "weight":      weight,
            })

    score     = round((score_weight / total_weight) * 100) if total_weight > 0 else 0
    compliant = score >= 70 and not any(i["required"] for i in issues)

    return {
        "product_id":    product_id,
        "product_title": product_title,
        "issues":        issues,
        "passed":        passed,
        "score":         score,
        "compliant":     compliant,
        "checked_at":    datetime.now(timezone.utc).isoformat(),
    }


def generate_gpsr_declaration(product: dict, company: dict) -> str:
    """
    Generiere eine HTML-Konformitätserklärung (GPSR Compliance Declaration).

    Hinweis: Dieses Dokument ist ein Software-Template. Für Rechtsgültigkeit
    muss es von einem qualifizierten Vertreter unterzeichnet werden.

    Args:
        product: Shopify-Produkt-Dict
        company: Dict mit {name, address, country, eu_rep_name, eu_rep_address}

    Returns:
        HTML-String der Konformitätserklärung
    """
    now           = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    product_title = product.get("title", "N/A")
    product_id    = product.get("id", "N/A")
    vendor        = product.get("vendor", company.get("name", "N/A"))
    sku_list      = ", ".join(
        v.get("sku", "") for v in product.get("variants", []) if v.get("sku")
    ) or "N/A"

    company_name      = company.get("name", "N/A")
    company_address   = company.get("address", "N/A")
    eu_rep_name       = company.get("eu_rep_name", "N/A")
    eu_rep_address    = company.get("eu_rep_address", "N/A")

    return dedent(f"""
    <!DOCTYPE html>
    <html lang="de">
    <head>
      <meta charset="UTF-8">
      <title>EU Konformitätserklärung — {product_title}</title>
      <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }}
        h1 {{ color: #003087; border-bottom: 2px solid #003087; padding-bottom: 10px; }}
        h2 {{ color: #003087; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        td, th {{ padding: 8px 12px; border: 1px solid #ddd; }}
        th {{ background: #f0f0f0; font-weight: bold; }}
        .warning {{ background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 4px; margin: 20px 0; }}
        .footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 20px; font-size: 12px; color: #666; }}
        .signature-box {{ border: 1px solid #333; padding: 20px; margin: 20px 0; min-height: 80px; }}
      </style>
    </head>
    <body>
      <h1>EU KONFORMITÄTSERKLÄRUNG</h1>
      <p><em>Gemäß EU-Verordnung 2023/988 (General Product Safety Regulation)</em></p>

      <div class="warning">
        ⚠️ <strong>Wichtig:</strong> Dieses Dokument wurde automatisch generiert (Software-Template).
        Es ersetzt keine rechtsgültige Konformitätserklärung. Bitte von einem Fachanwalt oder
        Authorised Representative prüfen und unterzeichnen lassen.
      </div>

      <h2>1. Produktinformationen</h2>
      <table>
        <tr><th>Feld</th><th>Wert</th></tr>
        <tr><td>Produktname</td><td>{product_title}</td></tr>
        <tr><td>Produktnummer / ID</td><td>{product_id}</td></tr>
        <tr><td>SKU(s)</td><td>{sku_list}</td></tr>
        <tr><td>Hersteller/Vendor</td><td>{vendor}</td></tr>
        <tr><td>Ausstellungsdatum</td><td>{now}</td></tr>
      </table>

      <h2>2. Hersteller / Wirtschaftsakteur</h2>
      <table>
        <tr><th>Feld</th><th>Wert</th></tr>
        <tr><td>Unternehmen</td><td>{company_name}</td></tr>
        <tr><td>Adresse</td><td>{company_address}</td></tr>
      </table>

      <h2>3. EU Authorised Representative (Bevollmächtigter)</h2>
      <table>
        <tr><th>Feld</th><th>Wert</th></tr>
        <tr><td>Name</td><td>{eu_rep_name}</td></tr>
        <tr><td>EU-Adresse</td><td>{eu_rep_address}</td></tr>
      </table>

      <h2>4. Erklärung</h2>
      <p>
        Hiermit erklärt der oben genannte Wirtschaftsakteur in alleiniger Verantwortung,
        dass das beschriebene Produkt den geltenden Anforderungen der EU-Verordnung 2023/988
        über die allgemeine Produktsicherheit entspricht.
      </p>
      <p>
        Das Produkt wurde gemäß den anwendbaren harmonisierten Normen und/oder technischen
        Spezifikationen bewertet. Die technischen Unterlagen sind beim oben genannten
        Wirtschaftsakteur verfügbar.
      </p>

      <h2>5. Unterschrift</h2>
      <div class="signature-box">
        <p>Ort, Datum: _________________________, {now}</p>
        <p>Name: _________________________</p>
        <p>Funktion: _________________________</p>
        <p>Unterschrift: _________________________</p>
      </div>

      <div class="footer">
        <p>Generiert von SuperMegaBot GPSR Compliance Engine | {now}</p>
        <p>EU-Verordnung 2023/988 | Gültig ab 13. Dezember 2024</p>
        <p>Preis: €129/Monat | GPSR_PRICE_ID: {GPSR_PRICE}</p>
      </div>
    </body>
    </html>
    """).strip()


# ── Shopify Integration ────────────────────────────────────────────────────

async def _fetch_shopify_products(limit: int = 50) -> list[dict]:
    """Lade Shopify-Produkte via Admin API."""
    if not SHOPIFY_DOM or not SHOPIFY_TOK:
        log.warning("Shopify-Credentials nicht gesetzt — überspringe Produktscan")
        return []

    url = (
        f"https://{SHOPIFY_DOM}/admin/api/{SHOPIFY_VER}/products.json"
        f"?limit={limit}&fields=id,title,body_html,vendor,product_type,tags,variants"
    )
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOK,
        "Content-Type":           "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("products", [])
                log.warning("Shopify API: HTTP %s", resp.status)
    except Exception as exc:
        log.warning("Shopify Fetch: %s", exc)
    return []


async def _send_tg(msg: str) -> None:
    """Sende Telegram-Benachrichtigung."""
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(
                url,
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.debug("TG Send: %s", exc)


async def run_gpsr_cycle() -> dict:
    """
    Haupt-Zyklus: Shopify-Produkte laden → GPSR-Check → Bericht via Telegram.

    Returns:
        {status, scanned, issues, compliant, non_compliant, avg_score,
         critical_issues, checked_at}
    """
    log.info("GPSR Compliance Engine — Zyklus startet")

    products = await _fetch_shopify_products(limit=50)
    if not products:
        log.warning("GPSR: Keine Shopify-Produkte geladen")
        return {
            "status":          "no_products",
            "scanned":         0,
            "issues":          0,
            "compliant":       0,
            "non_compliant":   0,
            "avg_score":       0,
            "critical_issues": 0,
            "checked_at":      datetime.now(timezone.utc).isoformat(),
        }

    scan_results  = []
    total_issues  = 0
    critical_cnt  = 0
    scores        = []

    for product in products:
        result = scan_product_for_gpsr(product)
        scan_results.append(result)
        total_issues += len(result["issues"])
        critical_cnt += sum(1 for i in result["issues"] if i["required"])
        scores.append(result["score"])

    compliant_cnt     = sum(1 for r in scan_results if r["compliant"])
    non_compliant_cnt = len(scan_results) - compliant_cnt
    avg_score         = round(sum(scores) / len(scores), 1) if scores else 0

    # Top 3 problematische Produkte für Report
    worst = sorted(scan_results, key=lambda r: r["score"])[:3]

    # Telegram-Bericht
    status_icon = "✅" if critical_cnt == 0 else "🚨"
    tg_lines = [
        f"{status_icon} <b>GPSR Compliance Report</b>",
        f"📦 {len(scan_results)} Produkte geprüft",
        f"✅ {compliant_cnt} compliant | ⚠️ {non_compliant_cnt} Non-Compliant",
        f"📊 Ø Score: {avg_score}/100 | Kritische Issues: {critical_cnt}",
    ]
    if worst and critical_cnt > 0:
        tg_lines.append("\n🔴 <b>Dringend beheben:</b>")
        for p in worst:
            if not p["compliant"]:
                crit = [i["label"] for i in p["issues"] if i["required"]]
                if crit:
                    tg_lines.append(f"• {p['product_title']} (Score: {p['score']})")
                    tg_lines.append(f"  Fehlt: {', '.join(crit[:2])}")

    await _send_tg("\n".join(tg_lines))

    log.info(
        "GPSR: %d geprüft | %d compliant | %d kritische Issues | Ø Score %.1f",
        len(scan_results), compliant_cnt, critical_cnt, avg_score,
    )

    return {
        "status":          "ok",
        "scanned":         len(scan_results),
        "issues":          total_issues,
        "compliant":       compliant_cnt,
        "non_compliant":   non_compliant_cnt,
        "avg_score":       avg_score,
        "critical_issues": critical_cnt,
        "checked_at":      datetime.now(timezone.utc).isoformat(),
        "price_id":        GPSR_PRICE,
    }
