#!/usr/bin/env python3
"""
BPI Compliance Engine — Vollautomatische Abwicklung für 10 EU-Compliance-Tools
- Stripe Webhook → Kaufabwicklung → Gmail-Lieferung
- B2B Outreach: zielgruppenspezifische Anschreiben (Shopify, KMU, Kanzleien, HR)
- Automatische Social-Posts nach Verkauf
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
log = logging.getLogger("BPICompliance")

# ── Credentials ───────────────────────────────────────────────────────
STRIPE_SK        = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
GMAIL_USER       = os.getenv("GMAIL_USER", "aiitecbuuss@gmail.com")
GMAIL_PASS       = os.getenv("GMAIL_APP_PASSWORD", os.getenv("GMAIL_PASSWORD", "rqcd uzim npsl odgw"))
TG_TOKEN         = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT          = os.getenv("TELEGRAM_CHAT_ID", "")
NETLIFY_BASE     = "https://extraordinary-daffodil-239faa.netlify.app"

# ── Produkt-Katalog ───────────────────────────────────────────────────
PRODUCTS = {
    "gpsr-shop-shield": {
        "name": "GPSR Shop-Shield",
        "price": 39,
        "stripe_link": "https://buy.stripe.com/28E4gB9jA7XY0c80Oi4F33N",
        "landing": f"{NETLIFY_BASE}/gpsr-shop-shield.html",
        "target": "shopify",
        "subject": "🛡️ GPSR-Pflicht ab 13.12.2024 — Ihr Shop ist betroffen",
        "delivery_html": """
<h2>Willkommen beim GPSR Shop-Shield!</h2>
<p>Vielen Dank für Ihre Bestellung. Ihr GPSR Shop-Shield ist jetzt aktiv.</p>
<p><b>Ihr nächster Schritt:</b> Verbinden Sie Ihren Shopify-Shop unter:<br>
<a href="{NETLIFY_BASE}/gpsr-shop-shield.html?token={token}">→ Shop jetzt verbinden</a></p>
<p>Bei Fragen: aiitecbuuss@gmail.com</p>""",
    },
    "bfsg-barriere-scanner": {
        "name": "BFSG Barriere-Scanner",
        "price": 39,
        "stripe_link": "https://buy.stripe.com/aFa00leDUguu3ok7cG4F33O",
        "landing": f"{NETLIFY_BASE}/bfsg-barriere-scanner.html",
        "target": "ecommerce",
        "subject": "♿ BFSG-Pflicht ab 28.06.2025 — Kostenlose Barrierefreiheitsprüfung",
        "delivery_html": """<h2>BFSG Barriere-Scanner aktiviert!</h2>
<p>Ihr Scanner ist bereit. Geben Sie Ihre Website-URL ein und erhalten Sie sofort einen Compliance-Report.</p>
<p><a href="{NETLIFY_BASE}/bfsg-barriere-scanner.html?token={token}">→ Ersten Scan starten</a></p>""",
    },
    "e-rechnung-autopilot": {
        "name": "E-Rechnungs-Autopilot",
        "price": 29,
        "stripe_link": "https://buy.stripe.com/14AdRb0N41zA2kgdB44F33P",
        "landing": f"{NETLIFY_BASE}/e-rechnung-autopilot.html",
        "target": "alle",
        "subject": "📄 E-Rechnungspflicht 2025 — Jetzt automatisch umstellen",
        "delivery_html": """<h2>E-Rechnungs-Autopilot aktiviert!</h2>
<p>Ab sofort werden alle Ihre Rechnungen automatisch in ZUGFeRD/XRechnung konvertiert.</p>
<p><a href="{NETLIFY_BASE}/e-rechnung-autopilot.html?token={token}">→ API-Key einrichten</a></p>""",
    },
    "nis2-kmu-check": {
        "name": "NIS2 KMU-Check",
        "price": 49,
        "stripe_link": "https://buy.stripe.com/6oU8wR0N40vw7EA54y4F33Q",
        "landing": f"{NETLIFY_BASE}/nis2-kmu-check.html",
        "target": "kmu",
        "subject": "🔐 NIS2-Betroffenheit prüfen — Bußgelder bis 7 Mio. € vermeiden",
        "delivery_html": """<h2>NIS2 KMU-Check gestartet!</h2>
<p>Prüfen Sie jetzt Ihre NIS2-Betroffenheit und erhalten Sie einen Maßnahmenplan.</p>
<p><a href="{NETLIFY_BASE}/nis2-kmu-check.html?token={token}">→ Check starten</a></p>""",
    },
    "ppwr-verpackungs-radar": {
        "name": "PPWR Verpackungs-Radar",
        "price": 49,
        "stripe_link": "https://buy.stripe.com/bJebJ32Vcguu6Aw54y4F33R",
        "landing": f"{NETLIFY_BASE}/ppwr-verpackungs-radar.html",
        "target": "hersteller",
        "subject": "📦 PPWR-Verordnung 2025 — Verpackungskonformität automatisch prüfen",
        "delivery_html": """<h2>PPWR Verpackungs-Radar aktiv!</h2>
<p>Laden Sie Ihren Produktkatalog hoch und erhalten Sie sofort einen Konformitätsbericht.</p>
<p><a href="{NETLIFY_BASE}/ppwr-verpackungs-radar.html?token={token}">→ Katalog prüfen</a></p>""",
    },
    "cra-melde-waechter": {
        "name": "CRA Melde-Wächter",
        "price": 59,
        "stripe_link": "https://buy.stripe.com/9B6bJ32Vcfqq1gc8gK4F33S",
        "landing": f"{NETLIFY_BASE}/cra-melde-waechter.html",
        "target": "hardware",
        "subject": "🔒 Cyber Resilience Act — Automatische Schwachstellen-Meldung ab 2025",
        "delivery_html": """<h2>CRA Melde-Wächter aktiviert!</h2>
<p>Verbinden Sie Ihr Produkt-Repository für automatisches Schwachstellen-Monitoring.</p>
<p><a href="{NETLIFY_BASE}/cra-melde-waechter.html?token={token}">→ Repository verbinden</a></p>""",
    },
    "eudr-lieferketten-pass": {
        "name": "EUDR Lieferketten-Pass",
        "price": 69,
        "stripe_link": "https://buy.stripe.com/7sYaEZanE5PQcYUfJc4F33T",
        "landing": f"{NETLIFY_BASE}/eudr-lieferketten-pass.html",
        "target": "import",
        "subject": "🌿 EUDR-Pflicht 2025 — Entwaldungsfreiheit automatisch nachweisen",
        "delivery_html": """<h2>EUDR Lieferketten-Pass bereit!</h2>
<p>Reichen Sie Ihre Lieferantendaten ein und erhalten Sie Ihren Sorgfaltspflichten-Pass.</p>
<p><a href="{NETLIFY_BASE}/eudr-lieferketten-pass.html?token={token}">→ Lieferanten eingeben</a></p>""",
    },
    "zvg-expose-engine": {
        "name": "ZVG Exposé-Engine",
        "price": 49,
        "stripe_link": "https://buy.stripe.com/9B614pcvM5PQ4so68C4F33U",
        "landing": f"{NETLIFY_BASE}/zvg-expose-engine.html",
        "target": "immobilien",
        "subject": "🏠 Zwangsversteigerungen 2025 — Automatische Exposé-Generierung",
        "delivery_html": """<h2>ZVG Exposé-Engine aktiviert!</h2>
<p>Ihr erstes Exposé ist kostenlos. Geben Sie das Objekt ein und wir generieren das Exposé in 60 Sekunden.</p>
<p><a href="{NETLIFY_BASE}/zvg-expose-engine.html?token={token}">→ Erstes Exposé erstellen</a></p>""",
    },
    "hr-ki-hochrisiko-audit": {
        "name": "HR-KI Hochrisiko-Audit",
        "price": 99,
        "stripe_link": "https://buy.stripe.com/6oUdRb0N4baagb67cG4F33V",
        "landing": f"{NETLIFY_BASE}/hr-ki-hochrisiko-audit.html",
        "target": "hr",
        "subject": "🤖 EU AI Act — HR-Tools auditieren, Bußgelder bis 15 Mio. € vermeiden",
        "delivery_html": """<h2>HR-KI Hochrisiko-Audit gestartet!</h2>
<p>Reichen Sie Ihre HR-Tool-Liste ein und erhalten Sie eine Risikoklassifizierung nach EU AI Act.</p>
<p><a href="{NETLIFY_BASE}/hr-ki-hochrisiko-audit.html?token={token}">→ HR-Tools einreichen</a></p>""",
    },
    "kanzlei-mandanten-radar": {
        "name": "Kanzlei-Mandanten-Radar",
        "price": 290,
        "stripe_link": "https://buy.stripe.com/8x27sNdzQemm7EAeF84F33W",
        "landing": f"{NETLIFY_BASE}/kanzlei-mandanten-radar.html",
        "target": "kanzlei",
        "subject": "⚖️ Exklusives Mandanten-Monitoring für Ihre Kanzlei",
        "delivery_html": """<h2>Kanzlei-Mandanten-Radar aktiviert!</h2>
<p>Ihr Monitoring ist eingerichtet. Legen Sie Ihre Region und Zielgruppe fest.</p>
<p><a href="{NETLIFY_BASE}/kanzlei-mandanten-radar.html?token={token}">→ Region konfigurieren</a></p>""",
    },
}

# ── B2B Outreach-Targets ──────────────────────────────────────────────
OUTREACH_TEMPLATES = {
    "shopify": {
        "product": "gpsr-shop-shield",
        "search_queries": [
            "site:shopify.com shop",
            "shopify shop Deutschland kontakt",
        ],
        "email_intro": """Sehr geehrte Damen und Herren,

ab dem 13. Dezember 2024 gilt die EU-Produktsicherheitsverordnung (GPSR) —
Ihr Online-Shop muss für jedes Produkt einen verantwortlichen EU-Ansprechpartner
und vollständige Sicherheitsdaten hinterlegen. Bußgelder: bis zu €100.000.

Unser GPSR Shop-Shield prüft Ihren Shopify-Katalog automatisch für nur €39/Monat.""",
    },
    "kmu": {
        "product": "nis2-kmu-check",
        "email_intro": """Sehr geehrte Damen und Herren,

die NIS2-Richtlinie gilt seit Oktober 2024 auch für viele KMU —
betroffen sind Unternehmen ab 50 Mitarbeitern oder €10 Mio. Umsatz in kritischen Sektoren.
Bußgelder: bis zu €7 Mio. oder 1,4% des weltweiten Umsatzes.

Unser NIS2 KMU-Check ermittelt Ihre Betroffenheit und liefert einen Maßnahmenplan für €49/Monat.""",
    },
    "kanzlei": {
        "product": "kanzlei-mandanten-radar",
        "email_intro": """Sehr geehrte Damen und Herren,

als spezialisierte Kanzlei wissen Sie: EU-Compliance-Mandate sind 2025 der Wachstumsmarkt.
Unser Kanzlei-Mandanten-Radar identifiziert täglich Unternehmen in Ihrer Region,
die dringend rechtliche Beratung zu GPSR, NIS2, CRA, EUDR oder BFSG benötigen.

Ab €290/Monat — und Sie sichern sich Ihre Region exklusiv.""",
    },
    "hr": {
        "product": "hr-ki-hochrisiko-audit",
        "email_intro": """Sehr geehrte Damen und Herren,

der EU AI Act klassifiziert viele HR-Tools (Bewerbermanagement, Performance-Software,
KI-gestützte Entlassungsanalysen) als Hochrisiko-KI-Systeme.
Bußgelder: bis zu €15 Mio. oder 3% des Umsatzes.

Unser HR-KI Hochrisiko-Audit prüft alle Ihre HR-Tools für €99/Monat.""",
    },
    "alle": {
        "product": "e-rechnung-autopilot",
        "email_intro": """Sehr geehrte Damen und Herren,

ab 2025 (>€800k Umsatz) und ab 2027 (alle Unternehmen) ist die E-Rechnung
im B2B-Bereich in Deutschland Pflicht. PDF per E-Mail ist dann keine gültige Rechnung mehr.

Unser E-Rechnungs-Autopilot wandelt jede Rechnung automatisch um — für nur €29/Monat.""",
    },
}


# ── E-Mail-Lieferung ──────────────────────────────────────────────────
def send_gmail(to: str, subject: str, html_body: str, text_body: str = "") -> bool:
    try:
        from modules.gmail_accounts import _is_valid_recipient
        if not _is_valid_recipient(to):
            log.warning("BLOCKED (noreply/dead): %s", to)
            return False
    except ImportError:
        pass
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"BullPower BPI <{GMAIL_USER}>"
        msg["To"]      = to
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo(); server.starttls(); server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to, msg.as_string())
        return True
    except Exception as e:
        log.error("Gmail Fehler: %s", e)
        return False


# ── Stripe Webhook Handler ─────────────────────────────────────────────
async def handle_stripe_event(event: dict) -> dict:
    """Verarbeitet checkout.session.completed → Lieferung per E-Mail."""
    event_type = event.get("type", "")
    if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
        return {"ok": True, "action": "ignored", "type": event_type}

    session = event.get("data", {}).get("object", {})
    customer_email = (
        session.get("customer_details", {}).get("email")
        or session.get("receipt_email")
        or ""
    )
    customer_name = (
        session.get("customer_details", {}).get("name", "Kunde")
        or "Kunde"
    )
    amount = session.get("amount_total", 0) // 100
    currency = session.get("currency", "eur").upper()

    # Produkt-Slug aus Metadata oder Line Items ermitteln
    slug = session.get("metadata", {}).get("slug", "")
    if not slug:
        # Versuche über Line Items
        line_items_url = f"https://api.stripe.com/v1/checkout/sessions/{session.get('id', '')}/line_items"
        async with aiohttp.ClientSession() as s:
            async with s.get(
                line_items_url,
                auth=aiohttp.BasicAuth(STRIPE_SK, ""),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                li_data = await r.json()
        for item in li_data.get("data", []):
            price_meta = item.get("price", {}).get("metadata", {})
            if price_meta.get("slug"):
                slug = price_meta["slug"]
                break

    product = PRODUCTS.get(slug, {})
    product_name = product.get("name", "BPI Compliance Tool")
    import secrets
    token = secrets.token_urlsafe(16)

    # Liefer-E-Mail senden
    if customer_email:
        delivery_html = product.get("delivery_html", "<p>Danke für Ihre Bestellung!</p>")
        delivery_html = delivery_html.format(NETLIFY_BASE=NETLIFY_BASE, token=token)
        html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#0a0c10;color:#00d48a;padding:16px;text-align:center;margin-bottom:20px">
  <h1 style="margin:0">⚡ BullPower BPI</h1>
</div>
<p>Hallo {customer_name},</p>
{delivery_html}
<hr style="border:1px solid #eee;margin:20px 0">
<p style="color:#666;font-size:12px">
  Rechnung: {product_name} · {amount} {currency}/Monat<br>
  BullPower AI GmbH · aiitecbuuss@gmail.com
</p></body></html>"""
        sent = send_gmail(
            customer_email,
            f"✅ {product_name} — Ihre Zugangsdaten",
            html,
        )
        log.info("Lieferung an %s: %s", customer_email, "✅" if sent else "❌")

    # Telegram-Benachrichtigung
    await _tg(
        f"💰 *Neuer Verkauf!*\n"
        f"Produkt: {product_name}\n"
        f"Betrag: €{amount}/Monat\n"
        f"Kunde: {customer_name} ({customer_email})\n"
        f"Token: `{token[:8]}...`"
    )

    return {"ok": True, "action": "delivered", "product": product_name, "to": customer_email}


# ── B2B E-Mail-Outreach ────────────────────────────────────────────────
async def run_b2b_outreach(
    target_type: str = "alle",
    targets: list[dict] | None = None,
    max_emails: int = 50,
) -> dict:
    """
    Sendet B2B-Outreach-E-Mails für das passende Compliance-Tool.
    targets = [{"email": "...", "company": "...", "name": "..."}, ...]
    """
    template = OUTREACH_TEMPLATES.get(target_type, OUTREACH_TEMPLATES["alle"])
    product = PRODUCTS.get(template["product"], {})
    intro = template["email_intro"]
    stripe_link = product.get("stripe_link", "")
    product_name = product.get("name", "BPI Tool")
    landing = product.get("landing", NETLIFY_BASE)

    if not targets:
        log.warning("Keine Outreach-Targets übergeben")
        return {"ok": False, "error": "keine targets"}

    sent = 0
    failed = 0
    for t in targets[:max_emails]:
        email = t.get("email", "")
        company = t.get("company", "Ihr Unternehmen")
        name = t.get("name", "Damen und Herren")
        if not email:
            continue

        subject = product.get("subject", f"EU-Compliance: {product_name}")
        html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#0a0c10;color:#00d48a;padding:16px;margin-bottom:20px">
  <h2 style="margin:0;color:#00d48a">{product_name}</h2>
  <p style="margin:4px 0;color:#888;font-size:12px">BullPower AI · EU-Compliance-Automatisierung</p>
</div>
<p>Sehr geehrte/r {name},</p>
<div style="white-space:pre-line">{intro}</div>
<div style="margin:24px 0;text-align:center">
  <a href="{stripe_link}" style="background:#00d48a;color:#000;padding:14px 28px;text-decoration:none;font-weight:bold;font-size:16px;display:inline-block">
    Jetzt aktivieren — ab €{product.get('price', 0)}/Monat →
  </a>
</div>
<p style="color:#666;font-size:12px">
  <a href="{landing}">Mehr Informationen</a> ·
  Abmelden: Antworten Sie mit "Abmelden"<br>
  BullPower AI · aiitecbuuss@gmail.com
</p></body></html>"""

        text = f"{intro}\n\nJetzt aktivieren: {stripe_link}\n\nMehr: {landing}"
        ok = send_gmail(email, subject, html, text)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(1.2)  # Rate Limit: max 50/min

    result = {"ok": True, "sent": sent, "failed": failed, "product": product_name}
    await _tg(f"📧 *B2B Outreach abgeschlossen*\n{product_name}\nGesendet: {sent} | Fehler: {failed}")
    log.info("B2B Outreach: %d gesendet, %d Fehler", sent, failed)
    return result


# ── Scheduler-Einstieg ─────────────────────────────────────────────────
async def run_bpi_compliance_cycle() -> dict:
    """Täglich: Stats prüfen, Landing Pages OK, Telegram-Report."""
    results = {}
    async with aiohttp.ClientSession() as s:
        for slug, prod in PRODUCTS.items():
            try:
                async with s.get(prod["landing"], timeout=aiohttp.ClientTimeout(total=10)) as r:
                    results[slug] = {"ok": r.status == 200, "status": r.status}
            except Exception as e:
                results[slug] = {"ok": False, "error": str(e)}

    ok_count = sum(1 for v in results.values() if v.get("ok"))
    total = len(results)
    msg = f"🌐 *BPI Compliance Pages*\n{ok_count}/{total} Landing Pages online\n"
    for slug, r in results.items():
        name = PRODUCTS[slug]["name"]
        icon = "✅" if r.get("ok") else "❌"
        msg += f"{icon} {name}\n"
    await _tg(msg)
    return {"ok": True, "pages_ok": ok_count, "total": total, "details": results}


async def get_status() -> dict:
    return {
        "products": len(PRODUCTS),
        "netlify_url": NETLIFY_BASE,
        "outreach_templates": list(OUTREACH_TEMPLATES.keys()),
        "stripe_configured": bool(STRIPE_SK),
        "gmail_configured": bool(GMAIL_PASS),
    }


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass
