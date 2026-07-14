"""
Sales Funnel Closer — Stripe Payment → Onboarding → Upsell
===========================================================
Wenn jemand zahlt: sofort Willkommens-Sequenz starten + Upsell-Queue befüllen.
Scheduler ruft run_funnel_cycle() alle 30 Minuten auf.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("SalesFunnelCloser")

_DB = Path(__file__).parent.parent / "data" / "sales_funnel.db"

PAYMENT_LINKS = {
    "starter":    "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203",
    "pro":        "https://buy.stripe.com/bJecN7gM23HIgb6dB44F204",
    "enterprise": "https://buy.stripe.com/bJefZj9jA7XYaQMaoS4F205",
}

# Stripe Price IDs → Tier-Mapping (aus .env oder Fallback-Defaults)
TIER_BY_PRICE = {
    os.getenv("STRIPE_PRICE_STARTER",    "price_starter"):    "starter",
    os.getenv("STRIPE_PRICE_PRO",        "price_pro"):        "pro",
    os.getenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise"): "enterprise",
}

UPSELL_DELAY = {
    "starter":    14 * 86400,  # 14 Tage → Pro
    "pro":        30 * 86400,  # 30 Tage → Enterprise
    "enterprise": 0,           # kein Upsell
}

UPSELL_TARGET = {
    "starter": "pro",
    "pro":     "enterprise",
}


# ─── DB ───────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS email_queue (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT NOT NULL,
            name         TEXT DEFAULT '',
            subject      TEXT NOT NULL,
            html_body    TEXT NOT NULL,
            scheduled_at REAL NOT NULL,
            sent_at      REAL,
            error        TEXT
        );
        CREATE TABLE IF NOT EXISTS upsell_queue (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT NOT NULL,
            customer_id  TEXT DEFAULT '',
            current_tier TEXT NOT NULL,
            target_tier  TEXT NOT NULL,
            fire_at      REAL NOT NULL,
            sent_at      REAL
        );
        CREATE TABLE IF NOT EXISTS processed_payments (
            payment_id   TEXT PRIMARY KEY,
            email        TEXT,
            tier         TEXT,
            processed_at REAL
        );
    """)
    conn.commit()
    return conn


# ─── Tier-Erkennung ───────────────────────────────────────────────────────────

def _detect_tier(event_data: dict) -> str:
    """Erkennt Tier aus Stripe Event (PaymentIntent oder Subscription)."""
    # Versuche über line_items / price_id
    obj = event_data.get("object", {})

    # Subscription
    items = obj.get("items", {}).get("data", [])
    for item in items:
        price_id = item.get("price", {}).get("id", "")
        if price_id in TIER_BY_PRICE:
            return TIER_BY_PRICE[price_id]

    # PaymentIntent → amount
    amount = obj.get("amount", 0)
    if amount >= 29900:
        return "enterprise"
    if amount >= 9900:
        return "pro"
    if amount >= 4900:
        return "starter"

    # Metadata-Fallback
    meta = obj.get("metadata", {})
    tier = meta.get("tier", meta.get("plan", "starter")).lower()
    return tier if tier in ("starter", "pro", "enterprise") else "starter"


def _extract_customer(event_data: dict) -> tuple[str, str]:
    """Gibt (email, name) aus Stripe Event zurück."""
    obj = event_data.get("object", {})

    # Direkt im Objekt
    email = obj.get("receipt_email") or obj.get("email") or ""
    name  = obj.get("name") or ""

    # Aus customer-Objekt (expandiert)
    customer = obj.get("customer") or {}
    if isinstance(customer, dict):
        email = email or customer.get("email", "")
        name  = name  or customer.get("name", "")

    # Aus billing_details
    billing = obj.get("billing_details") or {}
    email = email or billing.get("email", "")
    name  = name  or billing.get("name", "")

    return email.strip(), (name or "Kunde").strip()


# ─── Email-Templates ──────────────────────────────────────────────────────────

def _email_welcome(name: str, tier: str) -> tuple[str, str]:
    tier_de = {"starter": "Starter (€49/Mo)", "pro": "Pro (€99/Mo)", "enterprise": "Enterprise (€299/Mo)"}
    return (
        f"🎉 Willkommen bei SuperMegaBot, {name}!",
        f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#111;color:#eee;padding:24px">
<h2 style="color:#00ff88">🚀 Dein SuperMegaBot ist aktiv!</h2>
<p>Hallo {name},</p>
<p>herzlich willkommen! Dein <strong>{tier_de.get(tier, tier)}</strong>-Plan ist sofort aktiv.</p>
<h3>Erste Schritte:</h3>
<ol>
  <li>📊 Dashboard öffnen: <a href="https://supermegabot-production.up.railway.app" style="color:#00ff88">supermegabot-production.up.railway.app</a></li>
  <li>🔧 API-Keys eintragen (Shopify, Telegram, Stripe)</li>
  <li>🤖 Automatisierung aktivieren: /api/bot/execute</li>
</ol>
<p>Bei Fragen antworte einfach auf diese Email.</p>
<p style="color:#888">SuperMegaBot — Dein KI-Autopilot für E-Commerce</p>
</body></html>"""
    )


def _email_tips(name: str, tier: str) -> tuple[str, str]:
    next_link = PAYMENT_LINKS.get(UPSELL_TARGET.get(tier, "pro"), "")
    return (
        f"💡 {name}, so holst du das Maximum aus SuperMegaBot",
        f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#111;color:#eee;padding:24px">
<h2 style="color:#00ff88">5 Tipps für mehr Umsatz diese Woche</h2>
<p>Hallo {name},</p>
<ol>
  <li>🏪 <strong>Shopify-Sync</strong>: POST /api/shopify/sync — täglich automatisch</li>
  <li>📧 <strong>Mass-Outreach</strong>: POST /api/mass-outreach/send — 1.000 Emails täglich</li>
  <li>📢 <strong>Social Blast</strong>: POST /api/traffic/blast — LinkedIn + Facebook + Blog</li>
  <li>🤝 <strong>Affiliate</strong>: POST /api/affiliate/recruit — 30% Provision auf Empfehlungen</li>
  <li>📊 <strong>ROAS</strong>: GET /api/meta-ads/stats — Meta Ads Ergebnisse live</li>
</ol>
{"<p>🚀 <a href='" + next_link + "' style='color:#00ff88'>Upgrade jetzt für mehr Power →</a></p>" if next_link else ""}
</body></html>"""
    )


def _email_upsell(name: str, current_tier: str, target_tier: str) -> tuple[str, str]:
    prices = {"pro": "€99/Mo", "enterprise": "€299/Mo"}
    link = PAYMENT_LINKS.get(target_tier, "")
    tier_de = {"pro": "Pro", "enterprise": "Enterprise"}
    features = {
        "pro":        ["Unbegrenzte Shopify Produkte", "5.000 Emails/Tag", "Priority Support", "A/B Testing"],
        "enterprise": ["Alles aus Pro", "Eigene KI-Agenten", "WhatsApp Automation", "Dedicated Server"],
    }
    feat_html = "".join(f"<li>✅ {f}</li>" for f in features.get(target_tier, []))
    return (
        f"⬆️ {name}, upgrade auf {tier_de.get(target_tier, target_tier)} — {prices.get(target_tier, '')}",
        f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#111;color:#eee;padding:24px">
<h2 style="color:#00ff88">Zeit für mehr Wachstum, {name}!</h2>
<p>Du nutzt SuperMegaBot seit einiger Zeit — jetzt ist der perfekte Moment für ein Upgrade.</p>
<h3>Was du mit {tier_de.get(target_tier, target_tier)} bekommst:</h3>
<ul>{feat_html}</ul>
<p style="text-align:center;margin:32px 0">
  <a href="{link}" style="background:#00ff88;color:#000;padding:14px 32px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:18px">
    Jetzt upgraden für {prices.get(target_tier, '')} →
  </a>
</p>
<p style="color:#888;font-size:12px">14 Tage Geld-zurück-Garantie. Keine Mindestlaufzeit.</p>
</body></html>"""
    )


# ─── Kernfunktionen ───────────────────────────────────────────────────────────

def send_welcome_sequence(email: str, name: str, tier: str) -> None:
    """3 Emails in Queue stellen: sofort, +2 Tage, +7 Tage."""
    now = time.time()
    emails = [
        (now,              *_email_welcome(name, tier)),
        (now + 2 * 86400,  *_email_tips(name, tier)),
        (now + 7 * 86400,  *_email_upsell(name, tier, UPSELL_TARGET.get(tier, "pro"))),
    ]
    with _db() as conn:
        conn.executemany(
            "INSERT INTO email_queue (email, name, subject, html_body, scheduled_at) VALUES (?,?,?,?,?)",
            [(email, name, subj, body, ts) for ts, subj, body in emails]
        )
        conn.commit()
    log.info("Welcome sequence queued for %s (%s)", email, tier)


def queue_upsell(email: str, tier: str, customer_id: str = "") -> None:
    """Upsell-Email nach 14/30 Tagen in Queue stellen."""
    delay = UPSELL_DELAY.get(tier, 0)
    target = UPSELL_TARGET.get(tier)
    if not delay or not target:
        return
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO upsell_queue (email, customer_id, current_tier, target_tier, fire_at)
               VALUES (?, ?, ?, ?, ?)""",
            (email, customer_id, tier, target, time.time() + delay)
        )
        conn.commit()
    log.info("Upsell queued: %s → %s in %.0f days", email, target, delay / 86400)


def handle_stripe_payment(event_data: dict) -> dict:
    """Einstiegspunkt für Stripe Webhook Events (payment_intent.succeeded etc.)."""
    obj = event_data.get("object", {})
    payment_id = obj.get("id", f"pay_{int(time.time())}")

    with _db() as conn:
        if conn.execute("SELECT 1 FROM processed_payments WHERE payment_id=?", (payment_id,)).fetchone():
            return {"status": "already_processed", "payment_id": payment_id}

    email, name = _extract_customer(event_data)
    tier = _detect_tier(event_data)
    customer_id = obj.get("customer") if isinstance(obj.get("customer"), str) else ""

    if not email:
        log.warning("No email in Stripe event %s", payment_id)
        return {"status": "no_email", "payment_id": payment_id}

    send_welcome_sequence(email, name, tier)
    queue_upsell(email, tier, customer_id or "")

    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_payments (payment_id, email, tier, processed_at) VALUES (?,?,?,?)",
            (payment_id, email, tier, time.time())
        )
        conn.commit()

    log.info("Payment processed: %s | %s | tier=%s", payment_id, email, tier)
    return {"status": "ok", "email": email, "tier": tier, "payment_id": payment_id}


async def process_email_queue() -> dict:
    """Sendet alle fälligen Emails aus der Queue."""
    try:
        from modules.smtp_email import send_email
    except ImportError:
        log.error("smtp_email nicht verfügbar")
        return {"sent": 0, "errors": 1}

    now = time.time()
    sent = 0
    errors = 0

    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM email_queue WHERE scheduled_at <= ? AND sent_at IS NULL ORDER BY scheduled_at LIMIT 50",
            (now,)
        ).fetchall()

    for row in rows:
        try:
            result = await send_email(
                to_email=row["email"],
                subject=row["subject"],
                html_body=row["html_body"],
            )
            with _db() as conn:
                if result.get("success"):
                    conn.execute("UPDATE email_queue SET sent_at=? WHERE id=?", (now, row["id"]))
                    sent += 1
                else:
                    conn.execute("UPDATE email_queue SET error=? WHERE id=?",
                                 (str(result.get("error", "unknown")), row["id"]))
                    errors += 1
                conn.commit()
        except Exception as e:
            log.error("Email send failed for %s: %s", row["email"], e)
            errors += 1

    return {"sent": sent, "errors": errors, "pending": len(rows) - sent}


async def process_upsell_queue() -> dict:
    """Sendet fällige Upsell-Emails."""
    try:
        from modules.smtp_email import send_email
    except ImportError:
        return {"sent": 0}

    now = time.time()
    sent = 0

    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM upsell_queue WHERE fire_at <= ? AND sent_at IS NULL LIMIT 20",
            (now,)
        ).fetchall()

    for row in rows:
        try:
            subj, body = _email_upsell(row["email"].split("@")[0].title(),
                                        row["current_tier"], row["target_tier"])
            result = await send_email(to_email=row["email"], subject=subj, html_body=body)
            if result.get("success"):
                with _db() as conn:
                    conn.execute("UPDATE upsell_queue SET sent_at=? WHERE id=?", (now, row["id"]))
                    conn.commit()
                sent += 1
        except Exception as e:
            log.error("Upsell send failed: %s", e)

    return {"sent": sent}


def get_stats() -> dict:
    """Übersicht: Emails, Upsells, Conversions."""
    with _db() as conn:
        total_queued  = conn.execute("SELECT COUNT(*) FROM email_queue").fetchone()[0]
        total_sent    = conn.execute("SELECT COUNT(*) FROM email_queue WHERE sent_at IS NOT NULL").fetchone()[0]
        total_pending = conn.execute("SELECT COUNT(*) FROM email_queue WHERE sent_at IS NULL AND scheduled_at <= ?", (time.time(),)).fetchone()[0]
        upsell_sent   = conn.execute("SELECT COUNT(*) FROM upsell_queue WHERE sent_at IS NOT NULL").fetchone()[0]
        upsell_pend   = conn.execute("SELECT COUNT(*) FROM upsell_queue WHERE sent_at IS NULL").fetchone()[0]
        payments      = conn.execute("SELECT COUNT(*), tier FROM processed_payments GROUP BY tier").fetchall()

    return {
        "emails_queued":  total_queued,
        "emails_sent":    total_sent,
        "emails_pending": total_pending,
        "upsells_sent":   upsell_sent,
        "upsells_pending": upsell_pend,
        "payments_by_tier": {r[1]: r[0] for r in payments},
    }


async def run_funnel_cycle() -> str:
    """Scheduler-Einstiegspunkt: email_queue + upsell_queue verarbeiten."""
    email_result  = await process_email_queue()
    upsell_result = await process_upsell_queue()
    stats = get_stats()
    summary = (
        f"FunnelCloser: {email_result['sent']} emails sent, "
        f"{upsell_result['sent']} upsells sent, "
        f"{stats['emails_pending']} pending"
    )
    log.info(summary)
    return summary
