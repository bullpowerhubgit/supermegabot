#!/usr/bin/env python3
"""
Stripe Auto-Billing — vollautomatische Abrechnung.
- Täglich: alle Subscriptions prüfen
- failed payment → Telegram + Email
- neue Sub → Willkommens-Email + Klaviyo + Telegram
- Payment Links für DS24-Produkte automatisch erstellen
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("StripeAutoBilling")

STRIPE_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
FROM_EMAIL      = os.getenv("FROM_EMAIL", "hello@autopilot-store-suite-fmbka.myshopify.com")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_BASE     = "https://api.stripe.com/v1"


def _stripe_headers() -> dict:
    return {"Authorization": f"Bearer {STRIPE_KEY}"}


async def _stripe_get(path: str, params: dict = None) -> dict:
    if not STRIPE_KEY:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{STRIPE_BASE}{path}",
                headers=_stripe_headers(),
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json() if r.status < 400 else {}
    except Exception:
        return {}


async def _stripe_post(path: str, data: dict) -> dict:
    if not STRIPE_KEY:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{STRIPE_BASE}{path}",
                headers={**_stripe_headers(),
                         "Content-Type": "application/x-www-form-urlencoded"},
                data=data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.json() if r.status < 400 else {}
    except Exception:
        return {}


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def _send_email(to: str, subject: str, html: str) -> None:
    try:
        from modules.email_blast_engine import send_via_smtp
        await send_via_smtp(subject=subject, html=html, to_email=to)
    except Exception as e:
        log.debug("Email to %s failed: %s", to, e)


async def check_subscriptions() -> dict:
    """Alle aktiven Subscriptions prüfen — failed payments + neue Subs erkennen."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "no STRIPE_SECRET_KEY"}

    subs = await _stripe_get("/subscriptions", {"limit": "100", "status": "all"})
    items = subs.get("data", [])

    failed  = 0
    new_sub = 0
    active  = 0

    for sub in items:
        status = sub.get("status", "")
        email  = sub.get("customer_details", {}).get("email", "")

        # Customer-Email über Customer-ID holen falls nötig
        if not email:
            cid = sub.get("customer", "")
            if cid:
                cdata = await _stripe_get(f"/customers/{cid}")
                email = cdata.get("email", "")

        if status == "past_due":
            failed += 1
            amount = sub.get("items", {}).get("data", [{}])[0].get(
                "price", {}).get("unit_amount", 0) or 0
            amt_str = str(amount // 100)
            await _telegram(
                f"⚠️ <b>Zahlung fehlgeschlagen!</b>\n"
                f"Kunde: {email}\n"
                f"Betrag: €{amt_str}\n"
                f"Sub-ID: {sub.get('id', '')}"
            )
            if email:
                await _send_email(
                    to=email,
                    subject="Ihre Zahlung konnte nicht verarbeitet werden",
                    html=(
                        "<h2>Zahlungsproblem</h2>"
                        "<p>Leider konnte Ihre letzte Zahlung nicht verarbeitet werden. "
                        "Bitte aktualisieren Sie Ihre Zahlungsmethode.</p>"
                        "<p><a href='https://billing.stripe.com/p/login/'>Zahlungsmethode aktualisieren</a></p>"
                    ),
                )

        elif status == "active":
            active += 1
            created = sub.get("created", 0)
            now_ts  = int(datetime.now(timezone.utc).timestamp())
            if now_ts - created < 86400:  # weniger als 24h alt = neu
                new_sub += 1
                if email:
                    await _send_email(
                        to=email,
                        subject="Willkommen bei BullPowerHub! 🎉",
                        html=(
                            "<h2>Willkommen! 🎉</h2>"
                            "<p>Ihr Abonnement ist aktiv. Vielen Dank für Ihr Vertrauen!</p>"
                            "<p>Sie haben jetzt Zugang zu allen Premium-Features.</p>"
                        ),
                    )
                    try:
                        from modules.klaviyo_autonomy import track_event
                        await track_event(
                            email=email,
                            event_name="Stripe Subscription Started",
                            properties={"sub_id": sub.get("id", "")},
                        )
                    except Exception:
                        pass
                await _telegram(
                    f"🎉 <b>NEUE SUBSCRIPTION!</b>\n"
                    f"Kunde: {email}\n"
                    f"Sub-ID: {sub.get('id', '')}"
                )

    return {
        "ok":     True,
        "total":  len(items),
        "active": active,
        "failed": failed,
        "new":    new_sub,
    }


async def create_payment_link(name: str, price_cents: int,
                              currency: str = "eur") -> dict:
    """Erstellt einen Stripe Payment Link."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "no STRIPE_SECRET_KEY"}

    # 1. Price erstellen
    price = await _stripe_post("/prices", {
        "unit_amount": str(price_cents),
        "currency":    currency,
        "product_data[name]": name,
    })
    price_id = price.get("id")
    if not price_id:
        return {"ok": False, "error": str(price)[:200]}

    # 2. Payment Link erstellen
    link = await _stripe_post("/payment_links", {
        "line_items[0][price]":    price_id,
        "line_items[0][quantity]": "1",
    })
    url = link.get("url")
    return {
        "ok":       bool(url),
        "url":      url,
        "price_id": price_id,
        "name":     name,
        "amount":   price_cents,
        "currency": currency,
    }


async def create_ds24_payment_links() -> dict:
    """Erstellt Payment Links für die wichtigsten Abo-Pläne."""
    plans = [
        ("BullPowerHub Starter",    4900, "eur"),
        ("BullPowerHub Pro",        9900, "eur"),
        ("BullPowerHub Enterprise", 29900, "eur"),
    ]
    created = []
    for name, cents, cur in plans:
        result = await create_payment_link(name, cents, cur)
        if result.get("ok"):
            created.append({"name": name, "url": result["url"],
                            "amount_eur": cents // 100})
        await asyncio.sleep(0.5)

    return {"ok": len(created) > 0, "payment_links": created}


async def get_billing_stats() -> dict:
    """Stripe Revenue-Übersicht."""
    if not STRIPE_KEY:
        return {"ok": False, "error": "no STRIPE_SECRET_KEY"}

    charges = await _stripe_get("/charges", {"limit": "100"})
    items   = charges.get("data", [])
    paid    = [c for c in items if c.get("paid") and not c.get("refunded")]
    total   = sum(c.get("amount", 0) for c in paid) / 100

    subs  = await _stripe_get("/subscriptions", {"status": "active", "limit": "100"})
    n_sub = len(subs.get("data", []))

    return {
        "ok":                 True,
        "total_charges":      len(paid),
        "total_revenue_eur":  round(total, 2),
        "active_subscriptions": n_sub,
    }


async def run_billing_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    return await check_subscriptions()
