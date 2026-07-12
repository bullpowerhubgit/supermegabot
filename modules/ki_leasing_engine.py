#!/usr/bin/env python3
"""
KI-Mitarbeiter-Leasing Engine — SYS-01
========================================
Verkauft KI-Arbeit als Abo-Service. Kein Software-Verkauf — Ergebnis-Lieferung.

Pakete:
  Basic  (€499/mo)  — 10 B2B-Leads täglich per Email
  Pro    (€999/mo)  — 25 Leads + EU AI Act Alert + monatl. Compliance-Report

Ablauf:
  1. Kunde öffnet /ki-leasing → wählt Paket
  2. Stripe Checkout (Abo) → Zahlung
  3. Webhook aktiviert Client-Account in SQLite
  4. Tägl. 08:30: Bester-Leads-Report per Email an alle aktiven Clients
  5. Telegram-Alert an Rudolf bei Neuabo / Kündigung

Steuern:
  python3 modules/ki_leasing_engine.py --now        # Sofort-Report testen
  python3 modules/ki_leasing_engine.py --stats      # Aktuellen Status zeigen
  python3 modules/ki_leasing_engine.py --list       # Alle Clients listen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import sqlite3
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("KILeasing")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "ki_leasing.db"

# ── Env ──────────────────────────────────────────────────────────────────────

def _load_env():
    env_file = _BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

def _stripe_key()    -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _gmail_user()    -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass()    -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
def _tg_token()      -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()       -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _dashboard_url() -> str: return os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")
def _webhook_secret()-> str: return os.getenv("KI_LEASING_WEBHOOK_SECRET", os.getenv("STRIPE_WEBHOOK_SECRET", ""))

# ── Stripe Price IDs (im DB gespeichert, automatisch erstellt) ────────────────

PACKAGES = {
    "basic": {
        "label":       "Lead-Agent Basic",
        "price_cents": 49900,
        "currency":    "eur",
        "leads":       10,
        "features":    ["10 qualifizierte B2B-Leads täglich", "Personalisierte Email-Reports", "Insolvenz + Handelsregister Daten", "Telegram-Alert auf Anfrage"],
    },
    "pro": {
        "label":       "Compliance-Wächter Pro",
        "price_cents": 99900,
        "currency":    "eur",
        "leads":       25,
        "features":    ["25 B2B-Leads täglich", "EU AI Act Compliance-Monitoring", "Monatlicher Compliance-Report (PDF)", "Priority Email-Support", "Alle Basic-Features"],
    },
}

# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(_DB_PATH))

def init_db():
    with _db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                email                TEXT    NOT NULL,
                package              TEXT    NOT NULL DEFAULT 'basic',
                stripe_customer_id   TEXT,
                stripe_subscription_id TEXT,
                stripe_session_id    TEXT,
                active               INTEGER NOT NULL DEFAULT 0,
                leads_sent_total     INTEGER NOT NULL DEFAULT 0,
                last_report_sent     TEXT,
                created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
                activated_at         TEXT,
                cancelled_at         TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_email ON clients(email);
            CREATE TABLE IF NOT EXISTS stripe_products (
                key        TEXT PRIMARY KEY,
                stripe_id  TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS report_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id  INTEGER NOT NULL,
                sent_at    TEXT    NOT NULL,
                leads_count INTEGER NOT NULL DEFAULT 0,
                status     TEXT    NOT NULL DEFAULT 'ok'
            );
        """)

# ── Stripe: Produkt + Preis erstellen wenn nicht vorhanden ───────────────────

async def _ensure_stripe_price(package_key: str) -> str:
    with _db() as c:
        row = c.execute("SELECT stripe_id FROM stripe_products WHERE key=?", (f"price_{package_key}",)).fetchone()
        if row:
            return row[0]

    pkg = PACKAGES[package_key]
    key = _stripe_key()
    if not key:
        return ""

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.stripe.com/v1/products",
            headers={"Authorization": f"Bearer {key}"},
            data={"name": f"KI-Leasing {pkg['label']}", "metadata[service]": "ki_leasing"}
        ) as r:
            prod = await r.json()
            product_id = prod.get("id", "")

        if not product_id:
            return ""

        async with s.post(
            "https://api.stripe.com/v1/prices",
            headers={"Authorization": f"Bearer {key}"},
            data={
                "product":             product_id,
                "unit_amount":         str(pkg["price_cents"]),
                "currency":            pkg["currency"],
                "recurring[interval]": "month",
                "metadata[package]":   package_key,
            }
        ) as r:
            price = await r.json()
            price_id = price.get("id", "")

    if price_id:
        with _db() as c:
            c.execute(
                "INSERT OR REPLACE INTO stripe_products(key,stripe_id) VALUES(?,?)",
                (f"price_{package_key}", price_id)
            )
        log.info("Stripe Preis erstellt: %s → %s", package_key, price_id)

    return price_id


async def create_checkout(email: str, package: str = "basic") -> Dict:
    if package not in PACKAGES:
        package = "basic"
    key = _stripe_key()
    if not key:
        return {"ok": False, "error": "STRIPE_SECRET_KEY nicht gesetzt"}

    price_id = await _ensure_stripe_price(package)
    if not price_id:
        return {"ok": False, "error": "Stripe Preis konnte nicht erstellt werden"}

    base = _dashboard_url()
    pkg  = PACKAGES[package]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "payment_method_types[]":  "card",
                    "mode":                    "subscription",
                    "line_items[0][price]":    price_id,
                    "line_items[0][quantity]": "1",
                    "customer_email":          email,
                    "success_url": f"{base}/ki-leasing/success?session={{CHECKOUT_SESSION_ID}}",
                    "cancel_url":  f"{base}/ki-leasing",
                    "metadata[package]":  package,
                    "metadata[service]":  "ki_leasing",
                    "subscription_data[metadata][package]":  package,
                    "subscription_data[metadata][service]":  "ki_leasing",
                }
            ) as r:
                d = await r.json()
                if "id" in d:
                    _upsert_client_pending(email, package, d["id"])
                return {
                    "ok":           "id" in d,
                    "checkout_url": d.get("url", ""),
                    "session_id":   d.get("id", ""),
                    "error":        d.get("error", {}).get("message", "") if "error" in d else ""
                }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _upsert_client_pending(email: str, package: str, session_id: str):
    with _db() as c:
        c.execute("""
            INSERT INTO clients(email, package, stripe_session_id, active)
            VALUES(?,?,?,0)
            ON CONFLICT(email) DO UPDATE SET
              package=excluded.package,
              stripe_session_id=excluded.stripe_session_id
        """, (email, package, session_id))


# ── Webhook Handler ───────────────────────────────────────────────────────────

async def handle_webhook(event: Dict) -> str:
    event_type = event.get("type", "")
    obj        = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        session_id   = obj.get("id", "")
        email        = obj.get("customer_email", "") or obj.get("customer_details", {}).get("email", "")
        customer_id  = obj.get("customer", "")
        sub_id       = obj.get("subscription", "")
        package      = obj.get("metadata", {}).get("package", "basic")
        if email and sub_id:
            _activate_client(email, package, customer_id, sub_id, session_id)
            await _tg_alert(f"🎉 <b>Neuer KI-Leasing Client!</b>\n📧 {email}\n📦 Paket: {PACKAGES.get(package,{}).get('label',package)}\n💰 €{PACKAGES.get(package,{}).get('price_cents',0)//100}/Monat")
        return f"activated:{email}"

    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        sub_id = obj.get("id", "")
        if sub_id:
            email = _deactivate_client(sub_id)
            await _tg_alert(f"❌ <b>KI-Leasing Kündigung</b>\n📧 {email or 'unbekannt'}\nSub-ID: {sub_id}")
        return f"cancelled:{sub_id}"

    elif event_type == "customer.subscription.updated":
        sub_id = obj.get("id", "")
        status = obj.get("status", "")
        if sub_id and status == "active":
            with _db() as c:
                c.execute("UPDATE clients SET active=1 WHERE stripe_subscription_id=?", (sub_id,))
        return f"updated:{sub_id}:{status}"

    return f"ignored:{event_type}"


def _activate_client(email: str, package: str, customer_id: str, sub_id: str, session_id: str):
    with _db() as c:
        c.execute("""
            INSERT INTO clients(email, package, stripe_customer_id, stripe_subscription_id, stripe_session_id, active, activated_at)
            VALUES(?,?,?,?,?,1,datetime('now'))
            ON CONFLICT(email) DO UPDATE SET
              package=excluded.package,
              stripe_customer_id=excluded.stripe_customer_id,
              stripe_subscription_id=excluded.stripe_subscription_id,
              stripe_session_id=excluded.stripe_session_id,
              active=1,
              activated_at=datetime('now'),
              cancelled_at=NULL
        """, (email, package, customer_id, sub_id, session_id))
    log.info("Client aktiviert: %s (%s)", email, package)


def _deactivate_client(sub_id: str) -> Optional[str]:
    with _db() as c:
        row = c.execute("SELECT email FROM clients WHERE stripe_subscription_id=?", (sub_id,)).fetchone()
        c.execute("UPDATE clients SET active=0, cancelled_at=datetime('now') WHERE stripe_subscription_id=?", (sub_id,))
    return row[0] if row else None


def get_active_clients() -> List[Dict]:
    with _db() as c:
        rows = c.execute("""
            SELECT id, email, package, leads_sent_total, last_report_sent, activated_at
            FROM clients WHERE active=1 ORDER BY activated_at DESC
        """).fetchall()
    return [
        {"id": r[0], "email": r[1], "package": r[2], "leads_sent": r[3],
         "last_report": r[4], "since": r[5]}
        for r in rows
    ]


def get_stats() -> Dict:
    with _db() as c:
        total_active   = c.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]
        total_clients  = c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        basic_count    = c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND package='basic'").fetchone()[0]
        pro_count      = c.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND package='pro'").fetchone()[0]
        leads_today    = c.execute("SELECT COALESCE(SUM(leads_count),0) FROM report_log WHERE date(sent_at)=date('now')").fetchone()[0]
        total_reports  = c.execute("SELECT COUNT(*) FROM report_log WHERE status='ok'").fetchone()[0]

    mrr = basic_count * 499 + pro_count * 999
    return {
        "active_clients":  total_active,
        "total_clients":   total_clients,
        "basic_clients":   basic_count,
        "pro_clients":     pro_count,
        "mrr_eur":         mrr,
        "leads_today":     leads_today,
        "total_reports":   total_reports,
    }


# ── Daily Report Generation ───────────────────────────────────────────────────

def _get_leads_for_report(package: str) -> List[Dict]:
    limit = PACKAGES.get(package, PACKAGES["basic"])["leads"]
    leads = []

    outreach_db = _BASE / "data" / "outreach_autonomous.db"
    if outreach_db.exists():
        try:
            with sqlite3.connect(str(outreach_db)) as c:
                rows = c.execute("""
                    SELECT company_name, score, category, contact_email, court, amount_eur
                    FROM leads WHERE score >= 50
                    ORDER BY score DESC, scraped_at DESC LIMIT ?
                """, (limit,)).fetchall()
                for r in rows:
                    leads.append({
                        "company":  r[0] or "Unbekannte GmbH",
                        "score":    r[1] or 0,
                        "type":     "Insolvenz",
                        "category": r[2] or "—",
                        "contact":  r[3] or "",
                        "detail":   f"Amtsgericht {r[4]}" if r[4] else "",
                        "amount":   f"€{r[5]:,.0f}" if r[5] else "k.A.",
                    })
        except Exception as e:
            log.warning("Lead-DB Insolvenz Fehler: %s", e)

    if len(leads) < limit:
        act_db = _BASE / "data" / "ai_act_scanner.db"
        if act_db.exists():
            try:
                with sqlite3.connect(str(act_db)) as c:
                    extra = limit - len(leads)
                    rows = c.execute("""
                        SELECT company_name, risk_score, industry, contact_email, risk_level
                        FROM companies WHERE risk_score >= 60
                        ORDER BY risk_score DESC LIMIT ?
                    """, (extra,)).fetchall()
                    for r in rows:
                        leads.append({
                            "company":  r[0] or "KMU ohne Name",
                            "score":    r[1] or 60,
                            "type":     "AI-Act-Risiko",
                            "category": r[2] or "IT/Software",
                            "contact":  r[3] or "",
                            "detail":   f"Risiko-Level: {r[4]}" if r[4] else "",
                            "amount":   "Bußgeld bis €35 Mio.",
                        })
            except Exception as e:
                log.warning("Lead-DB AI-Act Fehler: %s", e)

    if not leads:
        log.warning("KI-Leasing: Keine echten Leads — Quellen prüfen")

    return leads[:limit]


def _build_report_html(client: Dict, leads: List[Dict]) -> str:
    pkg_info = PACKAGES.get(client["package"], PACKAGES["basic"])
    rows_html = ""
    for i, lead in enumerate(leads, 1):
        score_color = "#10B981" if lead["score"] >= 75 else "#F59E0B" if lead["score"] >= 60 else "#6B7280"
        type_color  = "#EF4444" if lead["type"] == "Insolvenz" else "#8B5CF6"
        rows_html += f"""
        <tr>
          <td style="padding:12px 10px;border-bottom:1px solid #1E2430;font-weight:600;color:#E2E8F0">{i}. {lead['company']}</td>
          <td style="padding:12px 10px;border-bottom:1px solid #1E2430;text-align:center">
            <span style="background:{type_color}20;color:{type_color};padding:2px 8px;font-size:11px;font-weight:700;letter-spacing:0.1em">{lead['type']}</span>
          </td>
          <td style="padding:12px 10px;border-bottom:1px solid #1E2430;text-align:center;font-family:monospace;font-weight:700;color:{score_color}">{lead['score']}</td>
          <td style="padding:12px 10px;border-bottom:1px solid #1E2430;color:#64748B;font-size:13px">{lead['detail']}</td>
          <td style="padding:12px 10px;border-bottom:1px solid #1E2430;color:#F59E0B;font-family:monospace;font-size:13px">{lead['amount']}</td>
        </tr>"""

    today = datetime.now().strftime("%d. %B %Y")
    return f"""<!DOCTYPE html><html lang="de">
<head><meta charset="utf-8"><title>KI-Leasing Tages-Report</title></head>
<body style="margin:0;padding:0;background:#07090E;font-family:system-ui,-apple-system,sans-serif;color:#E2E8F0">
<div style="max-width:700px;margin:0 auto;padding:32px 16px">
  <div style="border-top:3px solid #F5A623;padding-top:24px;margin-bottom:28px">
    <div style="font-family:monospace;font-size:10px;color:#F5A623;letter-spacing:0.2em;text-transform:uppercase;margin-bottom:8px">BULL POWER INTELLIGENCE — KI-LEASING</div>
    <h1 style="font-size:24px;font-weight:900;letter-spacing:-0.03em;margin-bottom:4px">Ihr Tages-Report</h1>
    <div style="font-family:monospace;font-size:12px;color:#64748B">{today} — Paket: <span style="color:#F5A623">{pkg_info['label']}</span></div>
  </div>

  <div style="background:#0E1219;border:1px solid #1E2430;padding:20px;margin-bottom:24px;display:flex;gap:32px">
    <div>
      <div style="font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-transform:uppercase">Leads heute</div>
      <div style="font-size:36px;font-weight:900;color:#F5A623;font-family:monospace;line-height:1">{len(leads)}</div>
    </div>
    <div style="border-left:1px solid #1E2430;padding-left:32px">
      <div style="font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:6px">Ihr KI-Mitarbeiter liefert:</div>
      <div style="font-size:13px;color:#94A3B8;line-height:1.8">Insolvenz-Leads • AI-Act-Risiko-Firmen<br>Score-Bewertung 0–100 • Tägl. um 08:30</div>
    </div>
  </div>

  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #1E2430;background:#0C0F17">
    <thead>
      <tr style="background:#111520">
        <th style="padding:10px;font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-align:left;border-bottom:1px solid #1E2430">UNTERNEHMEN</th>
        <th style="padding:10px;font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-align:center;border-bottom:1px solid #1E2430">TYP</th>
        <th style="padding:10px;font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-align:center;border-bottom:1px solid #1E2430">SCORE</th>
        <th style="padding:10px;font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-align:left;border-bottom:1px solid #1E2430">DETAIL</th>
        <th style="padding:10px;font-family:monospace;font-size:9px;color:#64748B;letter-spacing:0.15em;text-align:left;border-bottom:1px solid #1E2430">POTENZIAL</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>

  <div style="margin-top:24px;padding:16px;border:1px solid #1E2430;background:#0C0F17">
    <div style="font-family:monospace;font-size:10px;color:#64748B;margin-bottom:6px">NÄCHSTER REPORT:</div>
    <div style="font-size:13px;color:#94A3B8">Morgen um 08:30 Uhr automatisch — ohne Ihr Zutun.</div>
  </div>

  <div style="margin-top:32px;border-top:1px solid #1E2430;padding-top:16px;font-family:monospace;font-size:10px;color:#374151;line-height:1.8">
    KI-Leasing Engine — SuperMegaBot Intelligence Unit<br>
    Ihr Paket: {pkg_info['label']} | {pkg_info['leads']} Leads/Tag<br>
    Kündigung: Antwort auf diese Email mit "KÜNDIGEN"
  </div>
</div>
</body></html>"""


def _send_email(to: str, subject: str, html: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = _gmail_user()
        msg["To"]      = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(_gmail_user(), _gmail_pass())
            s.sendmail(_gmail_user(), to, msg.as_string())
        return True
    except Exception as e:
        log.error("Email-Fehler an %s: %s", to, e)
        return False


async def send_daily_reports() -> Dict:
    clients = get_active_clients()
    if not clients:
        log.info("Keine aktiven KI-Leasing Clients — kein Report.")
        return {"sent": 0, "errors": 0}

    today   = datetime.now().strftime("%d.%m.%Y")
    sent    = 0
    errors  = 0

    for client in clients:
        try:
            leads = _get_leads_for_report(client["package"])
            html  = _build_report_html(client, leads)
            subj  = f"📊 Ihr KI-Leasing Report — {len(leads)} Leads — {today}"

            ok = _send_email(client["email"], subj, html)
            status = "ok" if ok else "error"

            with _db() as c:
                c.execute(
                    "INSERT INTO report_log(client_id,sent_at,leads_count,status) VALUES(?,datetime('now'),?,?)",
                    (client["id"], len(leads), status)
                )
                if ok:
                    c.execute(
                        "UPDATE clients SET leads_sent_total=leads_sent_total+?, last_report_sent=datetime('now') WHERE id=?",
                        (len(leads), client["id"])
                    )

            if ok:
                sent += 1
                log.info("Report gesendet: %s (%d Leads)", client["email"], len(leads))
            else:
                errors += 1
        except Exception as e:
            log.error("Report-Fehler für %s: %s", client.get("email"), e)
            errors += 1

    summary = f"✅ KI-Leasing Reports: {sent} gesendet, {errors} Fehler — {today}"
    await _tg_alert(summary)
    log.info(summary)
    return {"sent": sent, "errors": errors}


async def run_daily_loop():
    while True:
        now = datetime.now()
        if now.hour == 8 and now.minute == 30:
            log.info("KI-Leasing: Starte tägliche Reports...")
            await send_daily_reports()
            await asyncio.sleep(60)
        await asyncio.sleep(30)


async def _tg_alert(text: str):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
    except Exception as _e:
        log.debug("skipped: %s", _e)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [KILeasing] %(levelname)s — %(message)s")
    init_db()
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--now":
        print("Sende Test-Report...")
        asyncio.run(send_daily_reports())
    elif arg == "--stats":
        s = get_stats()
        print(f"Aktive Clients: {s['active_clients']} | MRR: €{s['mrr_eur']}/mo")
        print(f"Basic: {s['basic_clients']} | Pro: {s['pro_clients']}")
        print(f"Leads heute: {s['leads_today']} | Reports gesamt: {s['total_reports']}")
    elif arg == "--list":
        for c in get_active_clients():
            print(f"  {c['email']} ({c['package']}) — {c['leads_sent']} Leads gesendet — seit {c['since']}")
    else:
        print("Starte KI-Leasing Daily Loop (08:30 täglich)...")
        asyncio.run(run_daily_loop())

init_db()
