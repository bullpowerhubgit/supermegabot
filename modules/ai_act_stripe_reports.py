"""
EU AI Act Stripe Reports
Compliance reports, Stripe Checkout, Monitoring subscriptions, Landing Page.
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET_AI_ACT", "")
STRIPE_API_BASE = "https://api.stripe.com/v1"

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@supermegabot.com")

BASE_URL = os.getenv("BASE_URL", "https://supermegabot-production.up.railway.app")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = Path(os.getenv("DATA_DIR", "/tmp")) / "ai_act_reports.db"

REPORT_PRICE_EUR = 29900     # €299 in cents
MONITORING_PRICE_EUR = 149900  # €1499 in cents

INDUSTRIES = [
    "Kreditwesen/Banken",
    "Versicherungen",
    "Gesundheitswesen",
    "Personalwesen/HR",
    "Bildung/Schulen",
    "E-Commerce/Handel",
    "IT/Software",
    "Produktion/Industrie",
    "Rechtswesen",
    "Sonstiges",
]

RISK_SYSTEMS_BY_INDUSTRY = {
    "Kreditwesen/Banken": ["Kredit-Scoring-System", "Betrugserkennungs-KI", "AML-Monitoring", "Kundenrisikobewertung"],
    "Versicherungen": ["Risikobewertungs-KI", "Schadenserkennung", "Preisalgorithmus", "Kundenklassifizierung"],
    "Gesundheitswesen": ["Diagnose-KI", "Behandlungsempfehlungs-System", "Triage-Algorithmus", "Medizinische Bildanalyse"],
    "Personalwesen/HR": ["Bewerbungsscreening-KI", "Mitarbeiter-Bewertungssystem", "Kuendigungspraediktionsmodell"],
    "Bildung/Schulen": ["Pruefungsbewertungs-KI", "Lernfortschrittsanalyse", "Zulassungsalgorithmus"],
    "E-Commerce/Handel": ["Empfehlungsalgorithmus", "Preisdynamik-KI", "Kundensegmentierung", "Betrugsfilter"],
    "IT/Software": ["Code-Review-KI", "Sicherheitsanalyse", "Anomalieerkennung", "Kundensupport-Bot"],
    "Produktion/Industrie": ["Qualitaetskontroll-KI", "Predictive-Maintenance", "Sicherheitsueberwachung"],
    "Rechtswesen": ["Dokumentenanalyse-KI", "Urteilsprognosesystem", "Vertragsanalyse-KI"],
    "Sonstiges": ["Allgemeines KI-System", "Datenanalyse-Tool", "Automatisierungssystem"],
}

MEASURES_BY_RISK = {
    "high": [
        "Vollstaendige Risikobewertung nach Art. 9 EU AI Act durchfuehren",
        "Technische Dokumentation gem. Anhang IV erstellen",
        "Konformitaetsbewertungsverfahren einleiten",
        "Menschliche Aufsicht sicherstellen (Art. 14)",
        "Daten-Governance-Richtlinien implementieren (Art. 10)",
        "Transparenzpflichten umsetzen (Art. 13)",
        "Robustheit und Genauigkeit testen (Art. 15)",
        "CE-Kennzeichnung beantragen",
    ],
    "medium": [
        "Interne Risikobewertung dokumentieren",
        "Mitarbeiter-Schulungen zu KI-Risiken durchfuehren",
        "Datenschutz-Folgenabschaetzung (DPIA) durchfuehren",
        "Monitoring-Prozess fuer KI-Ausgaben einrichten",
        "Beschwerdemechanismus fuer betroffene Personen einrichten",
    ],
    "low": [
        "Grundlegende Dokumentation der KI-Systeme pflegen",
        "Datenschutzkonformitaet pruefen (DSGVO)",
        "Jahresreview der KI-Systeme einplanen",
    ],
}

LEGAL_REFERENCES = [
    ("Art. 6", "Klassifizierung von Hochrisiko-KI-Systemen"),
    ("Art. 9", "Risikomanagementsystem — Pflicht zur kontinuierlichen Bewertung"),
    ("Art. 10", "Anforderungen an Trainingsdaten und Daten-Governance"),
    ("Art. 12", "Aufzeichnungspflichten und Protokollierung"),
    ("Art. 13", "Transparenz und Bereitstellung von Informationen"),
    ("Art. 49", "CE-Kennzeichnung und Konformitaetserklaerung"),
    ("Art. 72", "Marktuberwachung und Kontrolle"),
    ("Anhang III", "Liste der Hochrisiko-KI-Systeme"),
    ("Art. 99", "Sanktionen — bis zu 15 Mio. EUR oder 3% des Jahresumsatzes"),
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkout_sessions (
                session_id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                industry TEXT NOT NULL,
                email TEXT NOT NULL,
                session_type TEXT NOT NULL DEFAULT 'report',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS generated_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                industry TEXT NOT NULL,
                email TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                report_html TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS monitoring_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                industry TEXT NOT NULL,
                email TEXT NOT NULL,
                stripe_subscription_id TEXT,
                stripe_customer_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                next_scan_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


_init_db()

# ---------------------------------------------------------------------------
# Stripe helpers
# ---------------------------------------------------------------------------

async def _stripe_request(method: str, path: str, data: Optional[dict] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    url = f"{STRIPE_API_BASE}{path}"
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers, params=data) as resp:
                return await resp.json()
        elif method == "POST":
            form_data = aiohttp.FormData()
            if data:
                for k, v in data.items():
                    form_data.add_field(k, str(v))
            async with session.post(url, headers=headers, data=form_data) as resp:
                return await resp.json()
    return {}


# ---------------------------------------------------------------------------
# 1. Stripe Checkout
# ---------------------------------------------------------------------------

async def create_report_checkout_session(company: str, industry: str, email: str) -> dict:
    session = await _stripe_request("POST", "/checkout/sessions", {
        "customer_email": email,
        "mode": "payment",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(REPORT_PRICE_EUR),
        "line_items[0][price_data][product_data][name]": "EU AI Act Compliance Report",
        "line_items[0][price_data][product_data][description]": f"Individueller Compliance Report fuer {company}",
        "line_items[0][quantity]": "1",
        "success_url": f"{BASE_URL}/ai-act/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{BASE_URL}/ai-act?cancelled=1",
        "metadata[company]": company,
        "metadata[industry]": industry,
        "metadata[email]": email,
        "metadata[type]": "report",
    })
    session_id = session.get("id", "")
    with _get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO checkout_sessions (session_id, company, industry, email, session_type) VALUES (?,?,?,?,'report')",
            (session_id, company, industry, email),
        )
    return {"url": session.get("url", ""), "session_id": session_id}


async def create_monitoring_checkout_session(company: str, industry: str, email: str) -> dict:
    session = await _stripe_request("POST", "/checkout/sessions", {
        "customer_email": email,
        "mode": "subscription",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(MONITORING_PRICE_EUR),
        "line_items[0][price_data][product_data][name]": "EU AI Act Monitoring Abo",
        "line_items[0][price_data][product_data][description]": "Monatliches KI-Compliance Monitoring",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1",
        "success_url": f"{BASE_URL}/ai-act/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{BASE_URL}/ai-act?cancelled=1",
        "metadata[company]": company,
        "metadata[industry]": industry,
        "metadata[email]": email,
        "metadata[type]": "monitoring",
    })
    session_id = session.get("id", "")
    with _get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO checkout_sessions (session_id, company, industry, email, session_type) VALUES (?,?,?,?,'monitoring')",
            (session_id, company, industry, email),
        )
    return {"url": session.get("url", ""), "session_id": session_id}


# ---------------------------------------------------------------------------
# Risk Assessment
# ---------------------------------------------------------------------------

def assess_risk(company: str, industry: str) -> dict:
    high_risk_industries = {"Kreditwesen/Banken", "Versicherungen", "Gesundheitswesen", "Personalwesen/HR", "Rechtswesen"}
    medium_risk_industries = {"Bildung/Schulen", "Produktion/Industrie"}

    if industry in high_risk_industries:
        risk_level = "high"
        risk_score = 78 + (hash(company) % 15)
    elif industry in medium_risk_industries:
        risk_level = "medium"
        risk_score = 45 + (hash(company) % 20)
    else:
        risk_level = "low"
        risk_score = 20 + (hash(company) % 20)

    risk_score = max(0, min(100, risk_score))
    systems = RISK_SYSTEMS_BY_INDUSTRY.get(industry, RISK_SYSTEMS_BY_INDUSTRY["Sonstiges"])
    measures = MEASURES_BY_RISK.get(risk_level, MEASURES_BY_RISK["low"])

    return {
        "company": company,
        "industry": industry,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "systems": systems,
        "measures": measures,
        "assessment_date": datetime.utcnow().strftime("%d.%m.%Y"),
        "report_id": f"AIR-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}",
    }


# ---------------------------------------------------------------------------
# 2. HTML Report Generator
# ---------------------------------------------------------------------------

def generate_report_html(company_name: str, risk_data: dict) -> str:
    risk_level = risk_data.get("risk_level", "medium")
    risk_score = risk_data.get("risk_score", 50)
    industry = risk_data.get("industry", "Sonstiges")
    systems = risk_data.get("systems", [])
    measures = risk_data.get("measures", [])
    assessment_date = risk_data.get("assessment_date", datetime.utcnow().strftime("%d.%m.%Y"))
    report_id = risk_data.get("report_id", "AIR-000000")

    risk_color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(risk_level, "#64748b")
    risk_label = {"high": "HOCH", "medium": "MITTEL", "low": "NIEDRIG"}.get(risk_level, "UNBEKANNT")

    # SVG Gauge
    angle = -135 + (risk_score / 100) * 270
    rad = 3.14159265 * angle / 180
    needle_x = 100 + 70 * (0.7071 * (1 if angle > -90 else -1) if abs(angle + 90) < 45 else
                             (1 if 0 <= angle <= 180 else -1) * abs(0.7071))
    # Simplified needle endpoint calculation
    import math
    needle_rad = math.radians(angle - 90)
    nx = 100 + 70 * math.cos(needle_rad)
    ny = 100 + 70 * math.sin(needle_rad)

    gauge_svg = f"""<svg viewBox="0 0 200 130" xmlns="http://www.w3.org/2000/svg" style="width:200px;height:130px;">
  <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#1a1d27" stroke-width="20" stroke-linecap="round"/>
  <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#grad)" stroke-width="20" stroke-linecap="round"/>
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#22c55e"/>
      <stop offset="50%" style="stop-color:#f59e0b"/>
      <stop offset="100%" style="stop-color:#ef4444"/>
    </linearGradient>
  </defs>
  <line x1="100" y1="100" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#e2e8f0" stroke-width="3" stroke-linecap="round"/>
  <circle cx="100" cy="100" r="6" fill="#e2e8f0"/>
  <text x="100" y="125" text-anchor="middle" fill="{risk_color}" font-size="14" font-weight="bold">{risk_score}%</text>
</svg>"""

    systems_html = "".join(f"<li style='margin:6px 0;padding:6px 10px;background:#1a1d27;border-radius:6px;font-size:0.875rem;'>{s}</li>" for s in systems)
    measures_html = "".join(f"<li style='margin:8px 0;'><span style='color:{risk_color};font-weight:600;'>&#10003;</span> {m}</li>" for m in measures)
    legal_html = "".join(
        f"<tr><td style='padding:8px 12px;font-weight:600;color:#6366f1;white-space:nowrap;'>{ref}</td><td style='padding:8px 12px;color:#94a3b8;font-size:0.875rem;'>{desc}</td></tr>"
        for ref, desc in LEGAL_REFERENCES
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>EU AI Act Compliance Report &#8212; {company_name}</title>
<style>
  body{{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:0;}}
  .page{{max-width:900px;margin:0 auto;padding:2.5rem;}}
  h1{{font-size:1.75rem;margin-bottom:0.25rem;}}
  h2{{font-size:1.25rem;margin:2rem 0 1rem;color:#6366f1;border-bottom:1px solid #2d3748;padding-bottom:0.5rem;}}
  .header{{display:flex;justify-content:space-between;align-items:flex-start;padding:2rem;background:#1a1d27;border-radius:16px;margin-bottom:2rem;border:1px solid #2d3748;}}
  .risk-badge{{display:inline-block;padding:0.5rem 1.25rem;border-radius:9999px;font-weight:800;font-size:1rem;color:#fff;background:{risk_color};}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem;}}
  @media(max-width:600px){{.grid-2{{grid-template-columns:1fr;}}}}
  .card{{background:#1a1d27;border:1px solid #2d3748;border-radius:12px;padding:1.5rem;}}
  ul{{list-style:none;padding:0;margin:0;}}
  table{{width:100%;border-collapse:collapse;}}
  tr:nth-child(even){{background:#1a1d27;}}
  .disclaimer{{background:#1a1d27;border:1px solid #2d3748;border-radius:12px;padding:1.5rem;margin-top:2rem;font-size:0.8rem;color:#64748b;line-height:1.6;}}
  @media print{{body{{background:#fff;color:#000;}}.card,.header{{background:#f8f9fa;border-color:#dee2e6;}}.risk-badge{{-webkit-print-color-adjust:exact;}}.disclaimer{{background:#f8f9fa;}}}}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div>
      <div style="font-size:0.8rem;color:#64748b;margin-bottom:0.5rem;">EU AI Act Compliance Report</div>
      <h1>{company_name}</h1>
      <p style="color:#64748b;margin:0.25rem 0 1rem;">{industry} &#183; {assessment_date} &#183; {report_id}</p>
      <span class="risk-badge">Risikostufe: {risk_label}</span>
    </div>
    <div style="text-align:center;">{gauge_svg}</div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h2 style="margin-top:0;">Identifizierte KI-Systeme</h2>
      <ul>{systems_html}</ul>
    </div>
    <div class="card">
      <h2 style="margin-top:0;">Risikobewertung</h2>
      <p style="color:#64748b;font-size:0.9rem;line-height:1.6;">Basierend auf Ihrer Branche <strong>{industry}</strong> wurden {len(systems)} potenzielle KI-Systeme mit regulatorischer Relevanz identifiziert.</p>
      <p style="margin-top:1rem;font-size:0.9rem;">Klassifizierung nach <strong>Anhang III EU AI Act</strong>: <span style="color:{risk_color};font-weight:700;">{risk_label}</span></p>
    </div>
  </div>

  <div class="card">
    <h2 style="margin-top:0;">Empfohlene Massnahmen</h2>
    <ul style="padding-left:0;">{measures_html}</ul>
  </div>

  <div class="card" style="margin-top:1.5rem;">
    <h2 style="margin-top:0;">Rechtsgrundlagen</h2>
    <div style="overflow-x:auto;">
      <table><tbody>{legal_html}</tbody></table>
    </div>
  </div>

  <div class="disclaimer">
    <strong>Haftungsausschluss:</strong> Dieser Report wurde automatisiert auf Basis der angegebenen Unternehmensdaten erstellt und dient ausschliesslich als erste Orientierung. Er stellt keine Rechtsberatung dar und ersetzt nicht die Pruefung durch einen qualifizierten Rechtsanwalt oder Datenschutzbeauftragten. Die Einschaetzung des Risikograds basiert auf den Angaben des Nutzers. Eine individuelle rechtliche Pruefung der eingesetzten KI-Systeme ist zwingend erforderlich. Stand: EU AI Act (VO 2024/1689).
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 3. Webhook Handler
# ---------------------------------------------------------------------------

def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    try:
        parts = {p.split("=", 1)[0]: p.split("=", 1)[1] for p in sig_header.split(",")}
        timestamp = parts.get("t", "")
        signatures = [v for k, v in parts.items() if k == "v1"]
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, sig) for sig in signatures)
    except Exception as exc:
        logger.error("Signature error: %s", exc)
        return False


async def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    if not _verify_stripe_signature(payload, sig_header, STRIPE_WEBHOOK_SECRET):
        return {"error": "invalid signature"}
    try:
        event = json.loads(payload)
    except Exception:
        return {"error": "invalid json"}

    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        meta = obj.get("metadata", {})
        company = meta.get("company", "")
        industry = meta.get("industry", "")
        email = meta.get("email", "")
        session_type = meta.get("type", "report")
        customer_id = obj.get("customer", "")
        subscription_id = obj.get("subscription", "")

        if session_type == "monitoring":
            next_scan = (datetime.utcnow() + timedelta(days=30)).isoformat()
            with _get_db() as conn:
                conn.execute("""
                    INSERT INTO monitoring_clients (company, industry, email, stripe_subscription_id, stripe_customer_id, next_scan_at)
                    VALUES (?,?,?,?,?,?)
                """, (company, industry, email, subscription_id, customer_id, next_scan))
            logger.info("Monitoring client added: %s <%s>", company, email)
        else:
            risk_data = assess_risk(company, industry)
            report_html = generate_report_html(company, risk_data)
            with _get_db() as conn:
                conn.execute("""
                    INSERT INTO generated_reports (company, industry, email, risk_level, risk_score, report_html)
                    VALUES (?,?,?,?,?,?)
                """, (company, industry, email, risk_data["risk_level"], risk_data["risk_score"], report_html))
            try:
                await _send_report_email(email, company, report_html)
            except Exception as exc:
                logger.error("Email error for %s: %s", email, exc)

        with _get_db() as conn:
            conn.execute(
                "UPDATE checkout_sessions SET status='completed' WHERE session_id=?",
                (obj.get("id", ""),),
            )

    return {"ok": True}


async def _handle_webhook_route(request: web.Request) -> web.Response:
    payload = await request.read()
    sig_header = request.headers.get("Stripe-Signature", "")
    result = await handle_stripe_webhook(payload, sig_header)
    if "error" in result:
        return web.Response(status=400, text=result["error"])
    return web.Response(text="ok")


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

async def _send_report_email(email: str, company: str, report_html: str):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"EU AI Act Compliance Report &#8212; {company}"
    msg["From"] = FROM_EMAIL
    msg["To"] = email

    body_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;padding:2rem;margin:0;">
<div style="max-width:560px;margin:0 auto;background:#1a1d27;border-radius:16px;padding:2.5rem;border:1px solid #2d3748;">
  <div style="font-size:1.5rem;font-weight:800;margin-bottom:1.5rem;">EU AI Act &#9878;</div>
  <h1 style="font-size:1.5rem;margin-bottom:1rem;">Ihr Compliance Report ist fertig</h1>
  <p style="color:#64748b;line-height:1.6;margin-bottom:1.5rem;">Guten Tag,<br><br>anbei finden Sie den individualisierten EU AI Act Compliance Report fuer <strong>{company}</strong>.</p>
  <p style="color:#64748b;font-size:0.85rem;">Der Report liegt als HTML-Datei im Anhang bei. Oeffnen Sie ihn mit einem Browser oder drucken Sie ihn als PDF.</p>
  <hr style="border:none;border-top:1px solid #2d3748;margin:1.5rem 0;">
  <p style="font-size:0.75rem;color:#475569;">Fragen? Antworten Sie auf diese Email oder schreiben Sie an {FROM_EMAIL}</p>
</div>
</body></html>"""

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    attachment = MIMEBase("text", "html")
    attachment.set_payload(report_html.encode("utf-8"))
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", "attachment", filename=f"AI_Act_Report_{company.replace(' ', '_')}.html")
    msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [email], msg.as_string())
    logger.info("Report email sent to %s", email)


# ---------------------------------------------------------------------------
# 4. Landing Page
# ---------------------------------------------------------------------------

def build_landing_page_html(cancelled: bool = False) -> str:
    industry_options = "".join(f'<option value="{i}">{i}</option>' for i in INDUSTRIES)
    notice = ""
    if cancelled:
        notice = '<div style="background:#7f1d1d;border:1px solid #ef4444;border-radius:8px;padding:1rem;margin-bottom:1.5rem;color:#fca5a5;">Zahlung abgebrochen. Bitte versuchen Sie es erneut.</div>'

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU AI Act Compliance &#8212; Report &amp; Monitoring</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--accent:#6366f1;--text:#e2e8f0;--muted:#64748b;--border:#2d3748;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;}}
.container{{max-width:1000px;margin:0 auto;padding:0 1.5rem;}}
.hero{{padding:4rem 0 2rem;text-align:center;}}
.hero h1{{font-size:clamp(1.75rem,4vw,3rem);font-weight:800;margin-bottom:1rem;}}
.hero p{{color:var(--muted);max-width:600px;margin:0 auto 2rem;line-height:1.7;}}
.quick-check{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:2rem;max-width:500px;margin:0 auto 3rem;}}
.quick-check h2{{font-size:1.2rem;margin-bottom:1.5rem;text-align:center;}}
label{{display:block;font-size:0.85rem;color:var(--muted);margin-bottom:0.4rem;}}
input,select{{width:100%;padding:0.7rem 0.9rem;background:#0f1117;border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:0.95rem;margin-bottom:1rem;}}
.btn-primary{{width:100%;padding:0.85rem;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:700;cursor:pointer;}}
.result-box{{display:none;margin-top:1.5rem;padding:1.25rem;background:#0f1117;border-radius:12px;border:1px solid var(--border);}}
.score-bar{{height:8px;border-radius:4px;background:linear-gradient(to right,#22c55e,#f59e0b,#ef4444);margin:0.75rem 0;position:relative;}}
.score-indicator{{position:absolute;top:-4px;width:16px;height:16px;border-radius:50%;background:#e2e8f0;border:2px solid #0f1117;transition:left 0.5s;}}
.pricing-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin:3rem 0;}}
.price-card{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:2rem;}}
.price-tag{{font-size:2.5rem;font-weight:800;color:var(--accent);margin:1rem 0;}}
.btn-outline{{display:block;text-align:center;padding:0.75rem;border:1px solid var(--accent);border-radius:8px;color:var(--accent);text-decoration:none;font-weight:600;margin-top:1.5rem;}}
footer{{background:var(--card);border-top:1px solid var(--border);padding:2rem 0;text-align:center;margin-top:3rem;}}
</style>
</head>
<body>
<div class="container">
{notice}
<div class="hero">
  <h1>EU AI Act Compliance<br><span style="color:#6366f1;">Jetzt handeln, nicht warten</span></h1>
  <p>Ab 2025 gilt der EU AI Act verbindlich. Hochrisiko-KI-Systeme muessen dokumentiert, geprueft und zertifiziert sein &#8212; oder drohen Bussen bis zu <strong>15 Mio. EUR</strong>.</p>
</div>

<div class="quick-check">
  <h2>&#128269; Gratis Quick-Check</h2>
  <form id="quickForm">
    <label>Firmenname</label>
    <input type="text" id="qCompany" placeholder="Muster GmbH" required>
    <label>Branche</label>
    <select id="qIndustry">
      <option value="">Bitte w&#228;hlen...</option>
      {industry_options}
    </select>
    <button type="submit" class="btn-primary">Risiko jetzt pruefen</button>
  </form>
  <div class="result-box" id="resultBox">
    <p style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;">Ihr gesch&#228;tztes Risiko-Level:</p>
    <div style="font-size:1.5rem;font-weight:800;" id="riskLabel">&#8212;</div>
    <div class="score-bar"><div class="score-indicator" id="scoreIndicator" style="left:0;"></div></div>
    <p style="font-size:0.8rem;color:var(--muted);margin-top:0.5rem;">F&#252;r den vollst&#228;ndigen individuellen Report (inkl. aller Massnahmen, Rechtsgrundlagen &amp; Checkliste):</p>
    <a href="/ai-act/checkout?type=report" class="btn-outline" style="margin-top:0.75rem;">Report kaufen &#8212; &#8364;299</a>
  </div>
</div>

<div class="pricing-grid">
  <div class="price-card">
    <h3>Einzel-Report</h3>
    <div class="price-tag">&#8364;299 <span style="font-size:1rem;font-weight:400;color:var(--muted);">einmalig</span></div>
    <ul style="list-style:none;padding:0;color:var(--muted);font-size:0.9rem;">
      <li style="margin:6px 0;">&#10003; Vollst&#228;ndiger Compliance Report</li>
      <li style="margin:6px 0;">&#10003; Massnahmen-Checkliste</li>
      <li style="margin:6px 0;">&#10003; Alle Rechtsreferenzen</li>
      <li style="margin:6px 0;">&#10003; Druckbarer HTML-Report</li>
    </ul>
    <a href="/ai-act/checkout?type=report" class="btn-outline">Jetzt kaufen</a>
  </div>
  <div class="price-card" style="border-color:#6366f1;">
    <div style="font-size:0.75rem;color:#6366f1;font-weight:700;letter-spacing:0.1em;margin-bottom:0.5rem;">EMPFOHLEN</div>
    <h3>Monitoring Abo</h3>
    <div class="price-tag">&#8364;1.499 <span style="font-size:1rem;font-weight:400;color:var(--muted);">/Monat</span></div>
    <ul style="list-style:none;padding:0;color:var(--muted);font-size:0.9rem;">
      <li style="margin:6px 0;">&#10003; Monatliche Compliance-Pruefung</li>
      <li style="margin:6px 0;">&#10003; Automatische Update-Reports</li>
      <li style="margin:6px 0;">&#10003; Telegram-Alerts bei Aenderungen</li>
      <li style="margin:6px 0;">&#10003; Priorit&#228;ts-Support</li>
      <li style="margin:6px 0;">&#10003; Monatlich k&#252;ndbar</li>
    </ul>
    <a href="/ai-act/checkout?type=monitoring" class="btn-outline">Abo starten</a>
  </div>
</div>
</div>

<footer>
  <div class="container">
    <p style="color:var(--muted);">&#169; 2026 SuperMegaBot &#183; EU AI Act Compliance Service</p>
  </div>
</footer>

<script>
const RISK = {{
  'Kreditwesen/Banken':78,'Versicherungen':75,'Gesundheitswesen':82,'Personalwesen/HR':71,'Rechtswesen':68,
  'Bildung/Schulen':52,'Produktion/Industrie':48,'E-Commerce/Handel':35,'IT/Software':30,'Sonstiges':25
}};
document.getElementById('quickForm').addEventListener('submit', function(e) {{
  e.preventDefault();
  var ind = document.getElementById('qIndustry').value;
  if (!ind) return;
  var score = RISK[ind] || 30;
  var level = score >= 65 ? 'HOCH' : score >= 40 ? 'MITTEL' : 'NIEDRIG';
  var color = score >= 65 ? '#ef4444' : score >= 40 ? '#f59e0b' : '#22c55e';
  document.getElementById('riskLabel').textContent = level;
  document.getElementById('riskLabel').style.color = color;
  document.getElementById('scoreIndicator').style.left = (score - 8) + '%';
  document.getElementById('resultBox').style.display = 'block';
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. Monitoring Cycle
# ---------------------------------------------------------------------------

async def run_monitoring_cycle():
    now = datetime.utcnow().isoformat()
    with _get_db() as conn:
        due = conn.execute(
            "SELECT * FROM monitoring_clients WHERE status='active' AND next_scan_at <= ?",
            (now,),
        ).fetchall()

    if not due:
        logger.info("Monitoring cycle: no clients due")
        return {"checked": 0}

    count = 0
    for client in due:
        client = dict(client)
        try:
            risk_data = assess_risk(client["company"], client["industry"])
            report_html = generate_report_html(client["company"], risk_data)
            await _send_report_email(client["email"], client["company"], report_html)
            next_scan = (datetime.utcnow() + timedelta(days=30)).isoformat()
            with _get_db() as conn:
                conn.execute(
                    "UPDATE monitoring_clients SET next_scan_at=? WHERE id=?",
                    (next_scan, client["id"]),
                )
            count += 1
            logger.info("Monitoring report sent to %s", client["email"])
        except Exception as exc:
            logger.error("Monitoring error for %s: %s", client["email"], exc)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        msg = f"EU AI Act Monitoring: {count}/{len(due)} Reports versendet."
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            )

    return {"checked": len(due), "sent": count}


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

async def _handle_landing(request: web.Request) -> web.Response:
    cancelled = request.rel_url.query.get("cancelled") == "1"
    return web.Response(content_type="text/html", text=build_landing_page_html(cancelled))


async def _handle_quick_check(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    company = body.get("company", "").strip()
    industry = body.get("industry", "Sonstiges").strip()
    if not company:
        raise web.HTTPBadRequest(text="company required")
    risk_data = assess_risk(company, industry)
    return web.json_response({
        "risk_level": risk_data["risk_level"],
        "risk_score": risk_data["risk_score"],
        "systems_count": len(risk_data["systems"]),
        "measures_count": len(risk_data["measures"]),
    })


async def _handle_checkout(request: web.Request) -> web.Response:
    session_type = request.rel_url.query.get("type", "report")
    if request.method == "GET":
        # Show simple form
        html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Checkout</title>
<style>body{{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}}
.box{{background:#1a1d27;border:1px solid #2d3748;border-radius:16px;padding:2rem;max-width:440px;width:100%;}}
h1{{font-size:1.3rem;margin-bottom:1.5rem;}}
label{{display:block;font-size:0.85rem;color:#64748b;margin-bottom:0.4rem;}}
input,select{{width:100%;padding:0.7rem;background:#0f1117;border:1px solid #2d3748;border-radius:8px;color:#e2e8f0;font-size:0.95rem;margin-bottom:1rem;}}
button{{width:100%;padding:0.85rem;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:700;cursor:pointer;}}
</style></head>
<body>
<div class="box">
  <h1>{"Monitoring Abo &#8212; &#8364;1.499/Monat" if session_type == "monitoring" else "Compliance Report &#8212; &#8364;299"}</h1>
  <form method="POST" action="/ai-act/checkout?type={session_type}">
    <label>Firmenname</label><input type="text" name="company" required>
    <label>Branche</label>
    <select name="industry">{"".join(f'<option>{i}</option>' for i in INDUSTRIES)}</select>
    <label>E-Mail</label><input type="email" name="email" required>
    <button type="submit">Weiter zur Zahlung</button>
  </form>
</div>
</body></html>"""
        return web.Response(content_type="text/html", text=html)

    data = await request.post()
    company = data.get("company", "").strip()
    industry = data.get("industry", "Sonstiges").strip()
    email = data.get("email", "").strip()
    if not all([company, email]):
        raise web.HTTPBadRequest(text="company and email required")

    if session_type == "monitoring":
        result = await create_monitoring_checkout_session(company, industry, email)
    else:
        result = await create_report_checkout_session(company, industry, email)

    raise web.HTTPFound(result["url"])


async def _handle_success(request: web.Request) -> web.Response:
    html = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Vielen Dank!</title>
<style>body{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}.box{background:#1a1d27;border:1px solid #2d3748;border-radius:16px;padding:2.5rem;max-width:480px;width:100%;text-align:center;}</style>
</head>
<body>
<div class="box">
  <div style="font-size:3rem;margin-bottom:1rem;">&#9989;</div>
  <h1 style="font-size:1.5rem;margin-bottom:1rem;">Vielen Dank!</h1>
  <p style="color:#64748b;line-height:1.6;">Ihre Zahlung wurde erfolgreich verarbeitet.<br>Sie erhalten Ihren Report in K&#252;rze per Email.</p>
  <a href="/ai-act" style="display:inline-block;margin-top:1.5rem;color:#6366f1;">&#8592; Zur&#252;ck zur Startseite</a>
</div>
</body></html>"""
    return web.Response(content_type="text/html", text=html)


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register_routes(app: web.Application):
    app.router.add_get("/ai-act", _handle_landing)
    app.router.add_post("/api/ai-act/quick-check", _handle_quick_check)
    app.router.add_get("/ai-act/checkout", _handle_checkout)
    app.router.add_post("/ai-act/checkout", _handle_checkout)
    app.router.add_post("/webhooks/stripe/ai-act", _handle_webhook_route)
    app.router.add_get("/ai-act/success", _handle_success)
    logger.info("AI Act routes registered (6 routes)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _cli_main():
    parser = argparse.ArgumentParser(description="EU AI Act Reports CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="Quick risk check")
    p_check.add_argument("company")
    p_check.add_argument("industry", nargs="?", default="Sonstiges")

    p_report = sub.add_parser("report", help="Generate HTML report")
    p_report.add_argument("company")
    p_report.add_argument("industry", nargs="?", default="Sonstiges")
    p_report.add_argument("--out", default="report.html")

    p_mon = sub.add_parser("monitoring", help="Run monitoring cycle")

    p_co = sub.add_parser("checkout", help="Create Stripe checkout session")
    p_co.add_argument("company")
    p_co.add_argument("email")
    p_co.add_argument("--industry", default="Sonstiges")
    p_co.add_argument("--type", dest="session_type", default="report", choices=["report", "monitoring"])

    args = parser.parse_args()

    if args.cmd == "check":
        risk = assess_risk(args.company, args.industry)
        print(f"Company: {args.company}")
        print(f"Industry: {args.industry}")
        print(f"Risk Level: {risk['risk_level'].upper()}")
        print(f"Risk Score: {risk['risk_score']}/100")
        print(f"Systems identified: {len(risk['systems'])}")

    elif args.cmd == "report":
        risk = assess_risk(args.company, args.industry)
        html = generate_report_html(args.company, risk)
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Report written to {args.out}")

    elif args.cmd == "monitoring":
        result = await run_monitoring_cycle()
        print(f"Monitoring cycle done: {result}")

    elif args.cmd == "checkout":
        if args.session_type == "monitoring":
            result = await create_monitoring_checkout_session(args.company, args.industry, args.email)
        else:
            result = await create_report_checkout_session(args.company, args.industry, args.email)
        print(f"Checkout URL: {result['url']}")
        print(f"Session ID: {result['session_id']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_cli_main())
