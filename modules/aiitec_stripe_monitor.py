#!/usr/bin/env python3
"""
AIITEC Stripe Payment Monitor — Echtzeit-Zahlungsüberwachung
=============================================================
Prüft alle 5 Min die Stripe-API auf neue Checkouts/Zahlungen.
Bei jeder Zahlung → sofort Telegram-Alert + Auto-Onboarding-Email.

Starten:
  python3 modules/aiitec_stripe_monitor.py          # Daemon
  python3 modules/aiitec_stripe_monitor.py --check  # Einmalig
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [STRIPE-MON] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("StripeMonitor")

_BASE = Path(__file__).parent.parent

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_STRIPE_KEY  = lambda: os.getenv("STRIPE_SECRET_KEY", "")
_TG_TOKEN    = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT     = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_GMAIL_USER  = lambda: os.getenv("GMAIL_USER_4", "aiitecbuuss@gmail.com")
_GMAIL_PASS  = lambda: os.getenv("GMAIL_APP_PASSWORD_4", "")

CHECK_INTERVAL = 300   # 5 Minuten
_SEEN_PAYMENTS: set = set()

# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str):
    token = _TG_TOKEN(); chat = _TG_CHAT()
    if not token or not chat: return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram: %s", e)

# ── Stripe API ────────────────────────────────────────────────────────────────

async def _stripe_get(path: str, params: dict = None):
    key = _STRIPE_KEY()
    if not key:
        return None
    url = f"https://api.stripe.com/v1/{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params or {},
                         auth=aiohttp.BasicAuth(key, ""),
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
            log.warning("Stripe %s → %d", path, r.status)
            return None

# ── Onboarding-Email ─────────────────────────────────────────────────────────

def _send_onboarding_email(to_email: str, customer_name: str, amount_eur: float, product: str):
    subject = f"Willkommen bei AIITEC — {product} ist jetzt aktiv!"
    body = f"""Hallo {customer_name or 'dort'},

herzlichen Glückwunsch und willkommen bei AIITEC! 🎉

Ihre Zahlung von €{amount_eur:.0f} wurde erfolgreich verarbeitet.
Ihr Produkt *{product}* ist jetzt aktiv.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 IHRE NÄCHSTEN SCHRITTE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Dashboard aufrufen:
   https://dist-pi-jet-78.vercel.app/

2. Setup-Call buchen (kostenlos, 30 Min):
   Antworten Sie auf diese Email mit Ihren verfügbaren Zeiten.

3. Erste Leads kommen innerhalb von 24 Stunden.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Bei Fragen: Einfach auf diese Email antworten.

Mit freundlichen Grüßen,
Rudolf Sarkany
AIITEC — AI Business Automation
aiitecbuuss@gmail.com
"""
    user = _GMAIL_USER(); pwd = _GMAIL_PASS()
    if not pwd:
        log.warning("[ONBOARDING] Kein Gmail-Passwort")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Rudolf Sarkany — AIITEC <{user}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(user, pwd)
            s.sendmail(user, [to_email], msg.as_string())
        log.info("[ONBOARDING] ✉ Gesendet → %s", to_email)
        return True
    except Exception as e:
        log.error("[ONBOARDING] Fehler: %s", e)
        return False

# ── Hauptprüfung ─────────────────────────────────────────────────────────────

async def check_payments() -> int:
    """Prüft Stripe auf neue erfolgreiche Zahlungen der letzten 10 Min."""
    since = int(time.time()) - 600  # 10 Minuten zurück

    data = await _stripe_get("payment_intents", {
        "limit": "25",
        "created[gte]": str(since),
    })
    if not data:
        return 0

    new_count = 0
    for pi in data.get("data", []):
        pid = pi.get("id", "")
        if pid in _SEEN_PAYMENTS or pi.get("status") != "succeeded":
            continue
        _SEEN_PAYMENTS.add(pid)

        amount_eur = pi.get("amount", 0) / 100
        currency   = pi.get("currency", "eur").upper()
        customer_email = pi.get("receipt_email") or (
            pi.get("charges", {}).get("data", [{}])[0].get("billing_details", {}).get("email", "")
        )
        customer_name = (
            pi.get("charges", {}).get("data", [{}])[0].get("billing_details", {}).get("name", "")
        )
        description = pi.get("description", "AIITEC Subscription")
        created_ts  = pi.get("created", 0)

        log.info("💰 NEUE ZAHLUNG: %s %s von %s", currency, amount_eur, customer_email)
        new_count += 1

        # Telegram-Alert
        await _tg(
            f"💰 *NEUE ZAHLUNG!*\n\n"
            f"💵 Betrag: *{currency} {amount_eur:.0f}*\n"
            f"👤 Kunde: {customer_name or 'Unbekannt'}\n"
            f"📧 Email: {customer_email or 'n/a'}\n"
            f"📦 Produkt: {description}\n"
            f"🔑 ID: `{pid}`\n\n"
            f"_Onboarding-Email wurde automatisch gesendet!_"
        )

        # Onboarding-Email
        if customer_email:
            _send_onboarding_email(customer_email, customer_name, amount_eur, description)

    # Auch Checkout-Sessions prüfen
    sessions = await _stripe_get("checkout/sessions", {
        "limit": "25",
        "created[gte]": str(since),
        "status": "complete",
    })
    if sessions:
        for sess in sessions.get("data", []):
            sid = sess.get("id", "")
            if sid in _SEEN_PAYMENTS:
                continue
            _SEEN_PAYMENTS.add(sid)

            amount_eur = sess.get("amount_total", 0) / 100
            currency   = sess.get("currency", "eur").upper()
            email      = sess.get("customer_details", {}).get("email", "")
            name       = sess.get("customer_details", {}).get("name", "")
            product    = sess.get("metadata", {}).get("product", "AIITEC Subscription")

            log.info("💰 CHECKOUT ABGESCHLOSSEN: %s %s von %s", currency, amount_eur, email)
            new_count += 1

            await _tg(
                f"🎉 *CHECKOUT ABGESCHLOSSEN!*\n\n"
                f"💵 *{currency} {amount_eur:.0f}*\n"
                f"👤 {name or 'Unbekannt'}\n"
                f"📧 {email or 'n/a'}\n"
                f"📦 {product}\n\n"
                f"_GELD IST DA! Onboarding läuft..._"
            )

            if email:
                _send_onboarding_email(email, name, amount_eur, product)

    return new_count

# ── Daemon ────────────────────────────────────────────────────────────────────

async def daemon():
    log.info("Stripe Payment Monitor gestartet — alle %ds prüfen", CHECK_INTERVAL)
    await _tg(
        "💳 *Stripe Payment Monitor* gestartet!\n"
        "Prüft alle 5 Min auf neue Zahlungen.\n"
        "Bei Zahlung → sofort Telegram-Alert + Onboarding-Email."
    )
    while True:
        try:
            new = await check_payments()
            if new > 0:
                log.info("✅ %d neue Zahlungen verarbeitet", new)
        except Exception as e:
            log.error("Fehler: %s", e)
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    if "--check" in sys.argv:
        n = await check_payments()
        print(f"Neue Zahlungen: {n}")
    else:
        await daemon()

if __name__ == "__main__":
    asyncio.run(main())
