"""
KI-Leasing Stripe Portal
B2B SaaS subscription portal for AI leasing packages.
Features: Stripe Checkout, Webhook Handler, Client Dashboard, Landing Page,
          Welcome Email, Cancellation Flow.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET_KI_LEASING", "")
STRIPE_API_BASE = "https://api.stripe.com/v1"

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@supermegabot.com")

BASE_URL = os.getenv("BASE_URL", "https://supermegabot-production.up.railway.app")

DB_PATH = Path(os.getenv("DATA_DIR", "/tmp")) / "ki_leasing.db"

PACKAGES = {
    "basic": {
        "name": "Basic",
        "price_eur": 49900,
        "interval": "month",
        "description": "KI-Leasing Basic — 1 KI-Agent, 100 Leads/Monat",
        "features": ["1 KI-Agent", "100 Leads/Monat", "Email-Support", "Dashboard-Zugang"],
    },
    "pro": {
        "name": "Pro",
        "price_eur": 99900,
        "interval": "month",
        "description": "KI-Leasing Pro — 5 KI-Agenten, 500 Leads/Monat",
        "features": ["5 KI-Agenten", "500 Leads/Monat", "Priority-Support", "API-Zugang", "Reporting"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_eur": 149900,
        "interval": "month",
        "description": "KI-Leasing Enterprise — Unbegrenzte Agenten",
        "features": ["Unbegrenzte Agenten", "Unbegrenzte Leads", "Dedicated Support", "White-Label", "SLA 99.9%"],
    },
}

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
            CREATE TABLE IF NOT EXISTS stripe_prices (
                package TEXT PRIMARY KEY,
                price_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                package TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                dashboard_token TEXT UNIQUE,
                renewal_date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS client_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                leads_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS checkout_sessions (
                session_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                package TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


_init_db()

# ---------------------------------------------------------------------------
# Stripe API helpers
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
        elif method == "DELETE":
            async with session.delete(url, headers=headers) as resp:
                return await resp.json()
    return {}


async def _get_or_create_price_id(package: str) -> str:
    with _get_db() as conn:
        row = conn.execute("SELECT price_id FROM stripe_prices WHERE package=?", (package,)).fetchone()
        if row:
            return row["price_id"]

    pkg = PACKAGES[package]
    product = await _stripe_request("POST", "/products", {
        "name": pkg["description"],
        "description": ", ".join(pkg["features"]),
    })
    product_id = product["id"]
    price = await _stripe_request("POST", "/prices", {
        "product": product_id,
        "unit_amount": pkg["price_eur"],
        "currency": "eur",
        "recurring[interval]": pkg["interval"],
    })
    price_id = price["id"]

    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stripe_prices (package, price_id, product_id, created_at) VALUES (?,?,?,?)",
            (package, price_id, product_id, datetime.utcnow().isoformat()),
        )
    return price_id


# ---------------------------------------------------------------------------
# 1. Stripe Checkout
# ---------------------------------------------------------------------------

async def create_checkout_session(email: str, package: str) -> dict:
    if package not in PACKAGES:
        raise ValueError(f"Unknown package: {package}")
    price_id = await _get_or_create_price_id(package)
    session = await _stripe_request("POST", "/checkout/sessions", {
        "customer_email": email,
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{BASE_URL}/ki-leasing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{BASE_URL}/ki-leasing?cancelled=1",
        "metadata[package]": package,
        "metadata[email]": email,
    })
    session_id = session.get("id", "")
    with _get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO checkout_sessions (session_id, email, package) VALUES (?,?,?)",
            (session_id, email, package),
        )
    return {"url": session.get("url", ""), "session_id": session_id}


# ---------------------------------------------------------------------------
# 2. Stripe Webhook Handler
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
        logger.error("Signature verification error: %s", exc)
        return False


async def _handle_stripe_webhook(request: web.Request) -> web.Response:
    payload = await request.read()
    sig_header = request.headers.get("Stripe-Signature", "")
    if not _verify_stripe_signature(payload, sig_header, STRIPE_WEBHOOK_SECRET):
        logger.warning("Invalid Stripe signature on KI-Leasing webhook")
        return web.Response(status=400, text="Invalid signature")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return web.Response(status=400, text="Invalid JSON")
    event_type = event.get("type", "")
    data_obj = event.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        await _on_checkout_completed(data_obj)
    elif event_type == "customer.subscription.deleted":
        await _on_subscription_deleted(data_obj)
    elif event_type == "invoice.payment_succeeded":
        await _on_invoice_paid(data_obj)
    elif event_type == "customer.subscription.updated":
        await _on_subscription_updated(data_obj)
    else:
        logger.debug("Unhandled webhook event: %s", event_type)
    return web.Response(text="ok")


async def _on_checkout_completed(obj: dict):
    email = obj.get("customer_email") or obj.get("metadata", {}).get("email", "")
    package = obj.get("metadata", {}).get("package", "basic")
    customer_id = obj.get("customer", "")
    subscription_id = obj.get("subscription", "")
    token = secrets.token_urlsafe(32)
    renewal = (datetime.utcnow() + timedelta(days=30)).isoformat()
    with _get_db() as conn:
        conn.execute("""
            INSERT INTO clients (email, stripe_customer_id, stripe_subscription_id, package, status, dashboard_token, renewal_date)
            VALUES (?,?,?,?,'active',?,?)
            ON CONFLICT(email) DO UPDATE SET
                stripe_customer_id=excluded.stripe_customer_id,
                stripe_subscription_id=excluded.stripe_subscription_id,
                package=excluded.package,
                status='active',
                dashboard_token=excluded.dashboard_token,
                renewal_date=excluded.renewal_date
        """, (email, customer_id, subscription_id, package, token, renewal))
    try:
        await _send_welcome_email(email, package, token)
    except Exception as exc:
        logger.error("Failed to send welcome email to %s: %s", email, exc)


async def _on_subscription_deleted(obj: dict):
    subscription_id = obj.get("id", "")
    with _get_db() as conn:
        conn.execute("UPDATE clients SET status='cancelled' WHERE stripe_subscription_id=?", (subscription_id,))
    logger.info("Subscription cancelled: %s", subscription_id)


async def _on_invoice_paid(obj: dict):
    customer_id = obj.get("customer", "")
    renewal = (datetime.utcnow() + timedelta(days=30)).isoformat()
    with _get_db() as conn:
        conn.execute("UPDATE clients SET renewal_date=?, status='active' WHERE stripe_customer_id=?", (renewal, customer_id))
    logger.info("Invoice paid for customer: %s", customer_id)


async def _on_subscription_updated(obj: dict):
    subscription_id = obj.get("id", "")
    status = obj.get("status", "active")
    with _get_db() as conn:
        conn.execute("UPDATE clients SET status=? WHERE stripe_subscription_id=?", (status, subscription_id))
    logger.info("Subscription updated: %s -> %s", subscription_id, status)


# ---------------------------------------------------------------------------
# 3. Client Dashboard HTML
# ---------------------------------------------------------------------------

def _get_client_by_token(token: str) -> Optional[dict]:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE dashboard_token=? AND status='active'", (token,)
        ).fetchone()
        return dict(row) if row else None


def _get_client_stats(client_id: int) -> dict:
    with _get_db() as conn:
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        leads = conn.execute(
            "SELECT COALESCE(SUM(leads_count),0) as total FROM client_reports WHERE client_id=? AND created_at>=?",
            (client_id, seven_days_ago),
        ).fetchone()["total"]
        reports = conn.execute(
            "SELECT COUNT(*) as cnt FROM client_reports WHERE client_id=? AND created_at>=?",
            (client_id, seven_days_ago),
        ).fetchone()["cnt"]
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM client_reports WHERE client_id=?", (client_id,)
        ).fetchone()["cnt"]
        avg_success = conn.execute(
            "SELECT COALESCE(AVG(success_rate),0.0) as avg FROM client_reports WHERE client_id=?", (client_id,)
        ).fetchone()["avg"]
        history = conn.execute(
            "SELECT report_type, leads_count, success_rate, created_at FROM client_reports WHERE client_id=? ORDER BY created_at DESC LIMIT 20",
            (client_id,),
        ).fetchall()
    return {
        "leads_7d": leads,
        "reports_7d": reports,
        "total_reports": total,
        "success_rate": round(avg_success, 1),
        "history": [dict(r) for r in history],
    }


def generate_client_dashboard(token: str) -> str:
    client = _get_client_by_token(token)
    if not client:
        return "<h1 style='font-family:sans-serif;color:#e2e8f0;background:#0f1117;min-height:100vh;margin:0;padding:2rem;'>Ungültiger oder abgelaufener Zugangslink.</h1>"
    stats = _get_client_stats(client["id"])
    pkg = PACKAGES.get(client["package"], PACKAGES["basic"])
    renewal = client.get("renewal_date", "")[:10] if client.get("renewal_date") else "—"
    rows = ""
    for r in stats["history"]:
        rows += f"<tr><td>{r['created_at'][:10]}</td><td>{r['report_type']}</td><td>{r['leads_count']}</td><td>{r['success_rate']:.1f}%</td></tr>"
    features_html = "".join(f"<li>{f}</li>" for f in pkg["features"])
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Leasing Dashboard</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--accent:#6366f1;--text:#e2e8f0;--muted:#64748b;--border:#2d3748;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;padding:2rem;}}
h1{{font-size:1.75rem;margin-bottom:0.5rem;}}
.subtitle{{color:var(--muted);margin-bottom:2rem;}}
.grid-4{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem;}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem;}}
.card-label{{font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem;}}
.card-value{{font-size:2rem;font-weight:700;color:var(--accent);}}
.layout{{display:grid;grid-template-columns:1fr 300px;gap:1.5rem;}}
@media(max-width:768px){{.layout{{grid-template-columns:1fr;}}}}
table{{width:100%;border-collapse:collapse;}}
th,td{{padding:0.75rem 1rem;text-align:left;border-bottom:1px solid var(--border);font-size:0.875rem;}}
th{{color:var(--muted);font-weight:600;}}
tr:last-child td{{border-bottom:none;}}
.badge{{display:inline-block;padding:0.25rem 0.75rem;border-radius:9999px;font-size:0.75rem;font-weight:700;background:var(--accent);color:#fff;}}
ul{{padding-left:1.25rem;}}li{{margin:0.4rem 0;font-size:0.9rem;}}
.cancel-link{{display:block;text-align:center;margin-top:1rem;color:var(--muted);font-size:0.8rem;text-decoration:none;}}
.cancel-link:hover{{color:#ef4444;}}
</style>
</head>
<body>
<h1>KI-Leasing Dashboard</h1>
<p class="subtitle">Willkommen, {client['email']}</p>
<div class="grid-4">
  <div class="card"><div class="card-label">Leads (7 Tage)</div><div class="card-value">{stats['leads_7d']}</div></div>
  <div class="card"><div class="card-label">Reports (7 Tage)</div><div class="card-value">{stats['reports_7d']}</div></div>
  <div class="card"><div class="card-label">Erfolgsrate</div><div class="card-value">{stats['success_rate']}%</div></div>
  <div class="card"><div class="card-label">Reports gesamt</div><div class="card-value">{stats['total_reports']}</div></div>
</div>
<div class="layout">
  <div class="card">
    <h2 style="margin-bottom:1rem;font-size:1.1rem;">Report-Verlauf</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead><tr><th>Datum</th><th>Typ</th><th>Leads</th><th>Erfolgsrate</th></tr></thead>
        <tbody>{rows if rows else '<tr><td colspan="4" style="color:var(--muted)">Noch keine Reports vorhanden.</td></tr>'}</tbody>
      </table>
    </div>
  </div>
  <div class="card">
    <div class="card-label" style="margin-bottom:0.75rem;">Aktuelles Paket</div>
    <span class="badge">{pkg['name']}</span>
    <p style="margin-top:1rem;font-size:0.9rem;color:var(--muted);">Verlängerung am</p>
    <p style="font-weight:600;margin-top:0.25rem;">{renewal}</p>
    <hr style="border-color:var(--border);margin:1rem 0;">
    <ul>{features_html}</ul>
    <a href="/ki-leasing/cancel?token={token}" class="cancel-link">Abonnement kündigen</a>
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 4. B2B Landing Page
# ---------------------------------------------------------------------------

def generate_landing_page(cancelled: bool = False) -> str:
    notice = ""
    if cancelled:
        notice = '<div style="background:#7f1d1d;border:1px solid #ef4444;border-radius:8px;padding:1rem;margin-bottom:1.5rem;color:#fca5a5;">Zahlung abgebrochen. Du kannst es jederzeit erneut versuchen.</div>'
    pkg_cards = ""
    for key, pkg in PACKAGES.items():
        price_eur = pkg["price_eur"] // 100
        features_html = "".join(f'<li style="margin:0.4rem 0;font-size:0.9rem;">&#10003; {f}</li>' for f in pkg["features"])
        highlight = ' style="border:2px solid #6366f1;"' if key == "pro" else ""
        pkg_cards += f"""
<div class="pkg-card"{highlight}>
  <h3 style="font-size:1.2rem;margin-bottom:0.25rem;">{pkg['name']}</h3>
  <div style="font-size:2.5rem;font-weight:800;color:#6366f1;margin:0.75rem 0;">&#8364;{price_eur}<span style="font-size:1rem;font-weight:400;color:#64748b;">/Monat</span></div>
  <ul style="list-style:none;padding:0;margin-bottom:1.5rem;">{features_html}</ul>
  <form action="/ki-leasing/checkout" method="POST">
    <input type="hidden" name="package" value="{key}">
    <input type="email" name="email" placeholder="deine@email.de" required style="width:100%;padding:0.6rem 0.8rem;background:#0f1117;border:1px solid #2d3748;border-radius:6px;color:#e2e8f0;margin-bottom:0.75rem;font-size:0.9rem;">
    <button type="submit" style="width:100%;padding:0.75rem;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;">Jetzt starten</button>
  </form>
</div>"""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Leasing &#8212; Intelligente Automatisierung auf Mietbasis</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--accent:#6366f1;--text:#e2e8f0;--muted:#64748b;--border:#2d3748;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;}}
.container{{max-width:1100px;margin:0 auto;padding:0 1.5rem;}}
header{{padding:2rem 0;text-align:center;}}
.hero{{padding:5rem 0 3rem;text-align:center;}}
.hero h1{{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;line-height:1.1;margin-bottom:1rem;}}
.hero p{{font-size:1.2rem;color:var(--muted);max-width:600px;margin:0 auto 2rem;}}
.stats-bar{{display:flex;justify-content:center;gap:3rem;flex-wrap:wrap;padding:2rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:4rem;}}
.stat{{text-align:center;}}
.stat-val{{font-size:2rem;font-weight:800;color:var(--accent);}}
.stat-label{{font-size:0.8rem;color:var(--muted);margin-top:0.25rem;}}
.pkg-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin-bottom:4rem;}}
.pkg-card{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:2rem;}}
.section{{padding:3rem 0;}}
.section h2{{font-size:1.75rem;text-align:center;margin-bottom:2rem;}}
.steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.5rem;}}
.step{{background:var(--card);border-radius:12px;padding:1.5rem;text-align:center;}}
.step-num{{width:40px;height:40px;background:var(--accent);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;margin:0 auto 1rem;}}
.testimonials{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.5rem;margin-bottom:3rem;}}
.testimonial{{background:var(--card);border-radius:12px;padding:1.5rem;border-left:3px solid var(--accent);}}
.faq{{max-width:700px;margin:0 auto;}}
.faq-item{{border-bottom:1px solid var(--border);padding:1.25rem 0;}}
.faq-q{{font-weight:600;margin-bottom:0.5rem;}}
.faq-a{{color:var(--muted);font-size:0.9rem;line-height:1.6;}}
footer{{background:var(--card);border-top:1px solid var(--border);padding:3rem 0;text-align:center;}}
.gradient{{background:linear-gradient(135deg,#6366f1,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
</style>
</head>
<body>
<header><div class="container"><div style="font-size:1.3rem;font-weight:800;">&#9889; KI-Leasing</div></div></header>
<div class="container">
{notice}
<div class="hero">
  <h1>KI-Agenten<br><span class="gradient">mieten statt kaufen</span></h1>
  <p>Vollautomatisierte Lead-Generierung, Analyse und Reporting &#8212; ohne Upfront-Kosten. Monatlich k&#252;ndbar.</p>
</div>
<div class="stats-bar">
  <div class="stat"><div class="stat-val">500+</div><div class="stat-label">Aktive Kunden</div></div>
  <div class="stat"><div class="stat-val">2.4M</div><div class="stat-label">Leads generiert</div></div>
  <div class="stat"><div class="stat-val">98.7%</div><div class="stat-label">Uptime</div></div>
  <div class="stat"><div class="stat-val">4.9&#9733;</div><div class="stat-label">Kundenbewertung</div></div>
</div>
<div class="pkg-grid">{pkg_cards}</div>
<div class="section">
  <h2>So einfach geht's</h2>
  <div class="steps">
    <div class="step"><div class="step-num">1</div><h3>Paket w&#228;hlen</h3><p style="color:var(--muted);margin-top:0.5rem;font-size:0.9rem;">W&#228;hle dein passendes KI-Leasing-Paket</p></div>
    <div class="step"><div class="step-num">2</div><h3>Bezahlen</h3><p style="color:var(--muted);margin-top:0.5rem;font-size:0.9rem;">Sichere Zahlung &#252;ber Stripe &#8212; monatlich, k&#252;ndbar</p></div>
    <div class="step"><div class="step-num">3</div><h3>Dashboard</h3><p style="color:var(--muted);margin-top:0.5rem;font-size:0.9rem;">Sofort Zugang zum pers&#246;nlichen Dashboard</p></div>
    <div class="step"><div class="step-num">4</div><h3>Ergebnisse</h3><p style="color:var(--muted);margin-top:0.5rem;font-size:0.9rem;">KI-Agenten arbeiten automatisch f&#252;r dich</p></div>
  </div>
</div>
<div class="section">
  <h2>Das sagen unsere Kunden</h2>
  <div class="testimonials">
    <div class="testimonial"><p style="margin-bottom:1rem;">"Innerhalb von 3 Wochen haben wir 340 qualifizierte Leads erhalten. Unglaublich effizient."</p><strong>&#8212; Max S., E-Commerce Unternehmer</strong></div>
    <div class="testimonial"><p style="margin-bottom:1rem;">"Das Enterprise-Paket hat unsere Vertriebskosten um 60% gesenkt. Absolut empfehlenswert."</p><strong>&#8212; Julia K., Marketing-Leiterin</strong></div>
    <div class="testimonial"><p style="margin-bottom:1rem;">"Setup in 5 Minuten, erste Ergebnisse nach 2 Stunden. So muss SaaS funktionieren."</p><strong>&#8212; Thomas B., Startup-Gr&#252;nder</strong></div>
  </div>
</div>
<div class="section">
  <h2>H&#228;ufige Fragen</h2>
  <div class="faq">
    <div class="faq-item"><div class="faq-q">Kann ich jederzeit k&#252;ndigen?</div><div class="faq-a">Ja, du kannst dein Abonnement jederzeit zum Monatsende k&#252;ndigen. Keine Mindestlaufzeit.</div></div>
    <div class="faq-item"><div class="faq-q">Wie sicher sind meine Daten?</div><div class="faq-a">Alle Daten werden verschl&#252;sselt auf deutschen Servern gespeichert. DSGVO-konform.</div></div>
    <div class="faq-item"><div class="faq-q">Gibt es eine Testphase?</div><div class="faq-a">Wir bieten eine 14-t&#228;gige Geld-zur&#252;ck-Garantie f&#252;r alle Pakete.</div></div>
    <div class="faq-item"><div class="faq-q">Was passiert nach der Zahlung?</div><div class="faq-a">Du erh&#228;ltst sofort eine Welcome-Email mit deinem pers&#246;nlichen Dashboard-Zugang.</div></div>
    <div class="faq-item"><div class="faq-q">Kann ich das Paket wechseln?</div><div class="faq-a">Ja, ein Upgrade ist jederzeit m&#246;glich. Der Differenzbetrag wird anteilig berechnet.</div></div>
    <div class="faq-item"><div class="faq-q">Welche Zahlungsmethoden werden akzeptiert?</div><div class="faq-a">Kreditkarte, SEPA-Lastschrift, PayPal und alle g&#228;ngigen Zahlungsmethoden &#252;ber Stripe.</div></div>
  </div>
</div>
</div>
<footer>
  <div class="container">
    <p style="color:var(--muted);margin-bottom:0.5rem;">&#169; 2026 KI-Leasing &#8212; Ein Produkt von SuperMegaBot</p>
    <p style="color:var(--muted);font-size:0.8rem;">Sichere Zahlung via Stripe &#183; DSGVO-konform &#183; Made in Germany</p>
  </div>
</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 5. Welcome Email
# ---------------------------------------------------------------------------

async def _send_welcome_email(email: str, package: str, token: str):
    pkg = PACKAGES.get(package, PACKAGES["basic"])
    dashboard_url = f"{BASE_URL}/ki-leasing/dashboard?token={token}"
    cancel_url = f"{BASE_URL}/ki-leasing/cancel?token={token}"
    features_html = "".join(f"<li style='margin:6px 0;'>&#10003; {f}</li>" for f in pkg["features"])
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;padding:2rem;margin:0;">
<div style="max-width:560px;margin:0 auto;background:#1a1d27;border-radius:16px;padding:2.5rem;border:1px solid #2d3748;">
  <div style="text-align:center;margin-bottom:2rem;">
    <div style="font-size:1.5rem;font-weight:800;">&#9889; KI-Leasing</div>
    <h1 style="font-size:1.75rem;margin:1rem 0 0.5rem;">Willkommen an Bord!</h1>
    <p style="color:#64748b;">Dein {pkg['name']}-Paket ist jetzt aktiv.</p>
  </div>
  <div style="background:#0f1117;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;">
    <h2 style="font-size:1rem;margin-bottom:1rem;color:#6366f1;">Dein Paket: {pkg['name']}</h2>
    <ul style="list-style:none;padding:0;margin:0;">{features_html}</ul>
  </div>
  <div style="text-align:center;margin-bottom:1.5rem;">
    <a href="{dashboard_url}" style="display:inline-block;background:#6366f1;color:#fff;padding:0.875rem 2rem;border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;">&#8594; Dashboard &#246;ffnen</a>
  </div>
  <p style="font-size:0.8rem;color:#64748b;text-align:center;">Dieser Link ist personalisiert und nur f&#252;r dich bestimmt. Bitte nicht weitergeben.</p>
  <hr style="border:none;border-top:1px solid #2d3748;margin:1.5rem 0;">
  <p style="font-size:0.75rem;color:#475569;text-align:center;">Du m&#246;chtest k&#252;ndigen? <a href="{cancel_url}" style="color:#94a3b8;">Hier klicken</a></p>
</div>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Willkommen bei KI-Leasing &#8212; Dein {pkg['name']}-Paket ist aktiv"
    msg["From"] = FROM_EMAIL
    msg["To"] = email
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [email], msg.as_string())
    logger.info("Welcome email sent to %s", email)


# ---------------------------------------------------------------------------
# 6. Cancellation Flow
# ---------------------------------------------------------------------------

async def cancel_subscription(subscription_id: str) -> dict:
    result = await _stripe_request("DELETE", f"/subscriptions/{subscription_id}")
    return result


async def _handle_cancel_get(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("token", "")
    client = _get_client_by_token(token)
    if not client:
        return web.Response(content_type="text/html", text="<h1 style='font-family:sans-serif;'>Ung&#252;ltiger Token.</h1>")
    pkg = PACKAGES.get(client["package"], PACKAGES["basic"])
    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>K&#252;ndigung best&#228;tigen</title>
<style>
body{{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}}
.box{{background:#1a1d27;border:1px solid #2d3748;border-radius:16px;padding:2.5rem;max-width:480px;width:100%;text-align:center;}}
h1{{font-size:1.5rem;margin-bottom:1rem;}}
p{{color:#64748b;margin-bottom:1.5rem;line-height:1.6;}}
.btn-cancel{{background:#ef4444;color:#fff;border:none;padding:0.75rem 2rem;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;width:100%;margin-bottom:0.75rem;}}
.btn-back{{background:transparent;color:#6366f1;border:1px solid #6366f1;padding:0.75rem 2rem;border-radius:8px;font-size:1rem;cursor:pointer;width:100%;text-decoration:none;display:inline-block;}}
</style>
</head>
<body>
<div class="box">
  <div style="font-size:3rem;margin-bottom:1rem;">&#9888;&#65039;</div>
  <h1>Abonnement k&#252;ndigen?</h1>
  <p>Du bist dabei, dein <strong>{pkg['name']}</strong>-Paket zu k&#252;ndigen.<br>Du verlierst sofort den Zugang zu allen Features.</p>
  <form method="POST" action="/ki-leasing/cancel">
    <input type="hidden" name="token" value="{token}">
    <button type="submit" class="btn-cancel">Ja, jetzt k&#252;ndigen</button>
  </form>
  <a href="/ki-leasing/dashboard?token={token}" class="btn-back">Zur&#252;ck zum Dashboard</a>
</div>
</body></html>"""
    return web.Response(content_type="text/html", text=html)


async def _handle_cancel_post(request: web.Request) -> web.Response:
    data = await request.post()
    token = data.get("token", "")
    client = _get_client_by_token(token)
    if not client:
        return web.Response(status=404, text="Client not found")
    subscription_id = client.get("stripe_subscription_id", "")
    if subscription_id:
        try:
            await cancel_subscription(subscription_id)
        except Exception as exc:
            logger.error("Stripe cancellation error: %s", exc)
    with _get_db() as conn:
        conn.execute("UPDATE clients SET status='cancelled' WHERE dashboard_token=?", (token,))
    html = """<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Gek&#252;ndigt</title>
<style>body{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}.box{background:#1a1d27;border:1px solid #2d3748;border-radius:16px;padding:2.5rem;max-width:480px;width:100%;text-align:center;}</style>
</head>
<body>
<div class="box">
  <div style="font-size:3rem;margin-bottom:1rem;">&#9989;</div>
  <h1 style="font-size:1.5rem;margin-bottom:1rem;">K&#252;ndigung best&#228;tigt</h1>
  <p style="color:#64748b;">Dein Abonnement wurde erfolgreich gek&#252;ndigt. Du erh&#228;ltst eine Best&#228;tigung per Email.</p>
  <a href="/ki-leasing" style="display:inline-block;margin-top:1.5rem;color:#6366f1;">&#8592; Zur&#252;ck zur Startseite</a>
</div>
</body></html>"""
    return web.Response(content_type="text/html", text=html)


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

async def _handle_landing(request: web.Request) -> web.Response:
    cancelled = request.rel_url.query.get("cancelled") == "1"
    return web.Response(content_type="text/html", text=generate_landing_page(cancelled))


async def _handle_checkout_post(request: web.Request) -> web.Response:
    data = await request.post()
    email = data.get("email", "").strip()
    package = data.get("package", "basic").strip()
    if not email or package not in PACKAGES:
        raise web.HTTPBadRequest(text="Ungueltige Eingabe")
    try:
        result = await create_checkout_session(email, package)
        raise web.HTTPFound(result["url"])
    except web.HTTPFound:
        raise
    except Exception as exc:
        logger.error("Checkout error: %s", exc)
        raise web.HTTPInternalServerError(text=str(exc))


async def _handle_success(request: web.Request) -> web.Response:
    session_id = request.rel_url.query.get("session_id", "")
    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Zahlung erfolgreich</title>
<style>body{{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}}.box{{background:#1a1d27;border:1px solid #2d3748;border-radius:16px;padding:2.5rem;max-width:480px;width:100%;text-align:center;}}</style>
</head>
<body>
<div class="box">
  <div style="font-size:3rem;margin-bottom:1rem;">&#127881;</div>
  <h1 style="font-size:1.5rem;margin-bottom:1rem;">Zahlung erfolgreich!</h1>
  <p style="color:#64748b;line-height:1.6;">Dein KI-Leasing ist jetzt aktiv.<br>Du erh&#228;ltst in K&#252;rze eine Email mit deinem pers&#246;nlichen Dashboard-Zugang.</p>
  <p style="color:#475569;font-size:0.8rem;margin-top:1.5rem;">Session: {session_id[:20]}...</p>
</div>
</body></html>"""
    return web.Response(content_type="text/html", text=html)


async def _handle_dashboard(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("token", "")
    return web.Response(content_type="text/html", text=generate_client_dashboard(token))


async def _api_packages(request: web.Request) -> web.Response:
    return web.json_response({
        k: {**v, "price_eur_display": f"EUR {v['price_eur'] // 100}/Monat"}
        for k, v in PACKAGES.items()
    })


async def _api_checkout(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    email = body.get("email", "").strip()
    package = body.get("package", "basic").strip()
    if not email or package not in PACKAGES:
        raise web.HTTPBadRequest(text="email and package required")
    result = await create_checkout_session(email, package)
    return web.json_response(result)


async def _api_status(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("token", "")
    client = _get_client_by_token(token)
    if not client:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({
        "email": client["email"],
        "package": client["package"],
        "status": client["status"],
        "renewal_date": client["renewal_date"],
    })


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register_routes(app: web.Application):
    app.router.add_get("/ki-leasing", _handle_landing)
    app.router.add_post("/ki-leasing/checkout", _handle_checkout_post)
    app.router.add_get("/ki-leasing/success", _handle_success)
    app.router.add_get("/ki-leasing/dashboard", _handle_dashboard)
    app.router.add_get("/ki-leasing/cancel", _handle_cancel_get)
    app.router.add_post("/ki-leasing/cancel", _handle_cancel_post)
    app.router.add_post("/ki-leasing/stripe-webhook", _handle_stripe_webhook)
    app.router.add_get("/api/ki-leasing/packages", _api_packages)
    app.router.add_post("/api/ki-leasing/checkout", _api_checkout)
    app.router.add_get("/api/ki-leasing/status", _api_status)
    logger.info("KI-Leasing routes registered (10 routes)")
