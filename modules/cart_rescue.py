#!/usr/bin/env python3
"""
Cart Rescue — Abandoned Checkout via Telegram (+ Twilio WhatsApp optional)
===========================================================================
Shopify Abandoned Checkout Webhook → AI-personalisierter Telegram/WhatsApp-Text
Open Rate: Telegram 85-95% vs. Email 18%

Flow:
  1. Shopify sendet Webhook an POST /api/cart-rescue/webhook
  2. Warte 30 Minuten (konfigurierbarer Delay)
  3. Sende personalisierte Nachricht via Telegram oder WhatsApp (Twilio)
  4. Tracking in DB

Setup:
  - Shopify Admin → Settings → Notifications → Webhooks → abandoned_checkouts/create
  - URL: https://[domain]/api/cart-rescue/webhook
  - Format: JSON

Env vars:
  CART_RESCUE_DELAY_MIN  — Wartezeit in Minuten (default: 30)
  TWILIO_ACCOUNT_SID     — optional für WhatsApp
  TWILIO_AUTH_TOKEN      — optional für WhatsApp
  TWILIO_WHATSAPP_FROM   — z.B. whatsapp:+14155238886 (Sandbox)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("CartRescue")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "cart_rescue.db"

TG_API = "https://api.telegram.org"

def _tg_token()    -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()     -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _delay_min()   -> int: return int(os.getenv("CART_RESCUE_DELAY_MIN", "30"))
def _twilio_sid()  -> str: return os.getenv("TWILIO_ACCOUNT_SID", "")
def _twilio_tok()  -> str: return os.getenv("TWILIO_AUTH_TOKEN", "")
def _twilio_from() -> str: return os.getenv("TWILIO_WHATSAPP_FROM", "")
def _shopify_secret() -> str: return os.getenv("SHOPIFY_WEBHOOK_SECRET", "")


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cart_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            checkout_id     TEXT UNIQUE NOT NULL,
            email           TEXT,
            phone           TEXT,
            first_name      TEXT,
            total_price     REAL,
            products        TEXT,
            checkout_url    TEXT,
            status          TEXT DEFAULT 'pending',
            scheduled_for   INTEGER,
            sent_at         INTEGER,
            channel         TEXT,
            message_text    TEXT,
            recovered       INTEGER DEFAULT 0,
            created_at      INTEGER
        );

        CREATE TABLE IF NOT EXISTS cart_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT,
            triggered   INTEGER DEFAULT 0,
            sent        INTEGER DEFAULT 0,
            recovered   INTEGER DEFAULT 0
        );
        """)


# ── Telegram + WhatsApp Send ──────────────────────────────────────────────────

async def _tg_send(text: str, chat_id: str = "") -> bool:
    token = _tg_token()
    cid   = chat_id or _tg_chat()
    if not token or not cid:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10),
                                          connector=aiohttp.TCPConnector(ssl=False)) as s:
            r = await s.post(
                f"{TG_API}/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False}
            )
            return r.status == 200
    except Exception as e:
        log.debug("TG error: %s", e)
        return False


async def _whatsapp_send(to_phone: str, text: str) -> bool:
    sid  = _twilio_sid()
    tok  = _twilio_tok()
    from_num = _twilio_from()
    if not sid or not tok or not from_num:
        return False
    to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
    try:
        import base64
        auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"From": from_num, "To": to, "Body": text},
                headers={"Authorization": f"Basic {auth}"}
            ) as r:
                return r.status in (200, 201)
    except Exception as e:
        log.debug("WhatsApp error: %s", e)
        return False


# ── AI Message Generator ──────────────────────────────────────────────────────

async def generate_rescue_message(
    first_name: str,
    products: List[Dict],
    total: float,
    checkout_url: str
) -> str:
    product_names = ", ".join(p.get("title", "")[:40] for p in products[:3])
    items_text    = "\n".join(
        f"  • {p.get('title','')[:50]} — €{float(p.get('price',0)):.2f}" for p in products[:5]
    )

    prompt = f"""Schreibe eine kurze, freundliche WhatsApp/Telegram-Nachricht für einen verlassenen Warenkorb.

Kunde: {first_name or 'Hallo'}
Produkte: {product_names}
Warenkorbwert: €{total:.2f}

Regeln:
- Max 5 Sätze
- Persönlich und warm, kein Spam-Gefühl
- Erwähne 1-2 Produkte beim Namen
- Füge am Ende den Checkout-Link ein: {checkout_url}
- Auf Deutsch
- Kein Clickbait, ehrlich

Schreibe NUR den Nachrichtentext, keine Erklärungen."""

    text = await ai_complete(prompt, system="", max_tokens=300)
    if text:
        return text.strip()

    # Fallback ohne AI
    name_greeting = f"Hey {first_name}," if first_name else "Hey,"
    return (
        f"{name_greeting} du hast noch etwas in deinem Warenkorb vergessen! 🛒\n\n"
        f"{items_text}\n\n"
        f"Gesamt: €{total:.2f}\n\n"
        f"Dein Warenkorb wartet noch auf dich:\n{checkout_url}\n\n"
        f"Fragen? Einfach antworten! 😊"
    )


# ── Webhook Handler ───────────────────────────────────────────────────────────

async def handle_webhook(payload: bytes, hmac_header: str = "") -> Dict:
    """Verarbeitet Shopify abandoned_checkouts/create Webhook."""
    init_db()

    # HMAC Validation (optional)
    secret = _shopify_secret()
    if secret and hmac_header:
        import hmac as hmac_lib, hashlib
        digest = hmac_lib.new(secret.encode(), payload, hashlib.sha256)
        import base64
        expected = base64.b64encode(digest.digest()).decode()
        if expected != hmac_header:
            log.warning("Cart Rescue: ungültiger HMAC")
            return {"ok": False, "error": "invalid signature"}

    try:
        data = json.loads(payload)
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    checkout_id  = str(data.get("id", ""))
    email        = data.get("email", "")
    phone        = data.get("phone", "") or ""
    first_name   = (data.get("billing_address") or {}).get("first_name", "") or \
                   (data.get("shipping_address") or {}).get("first_name", "") or ""
    total_price  = float(data.get("total_price", 0))
    checkout_url = data.get("abandoned_checkout_url", "")
    line_items   = data.get("line_items", [])

    if not checkout_id:
        return {"ok": False, "error": "no checkout_id"}
    if not email and not phone:
        return {"ok": False, "error": "no contact (email/phone)"}

    products = [
        {"title": item.get("title", ""), "price": item.get("price", 0),
         "quantity": item.get("quantity", 1)}
        for item in line_items
    ]

    scheduled_for = int(time.time()) + (_delay_min() * 60)

    with _db() as conn:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO cart_events
                   (checkout_id, email, phone, first_name, total_price, products,
                    checkout_url, status, scheduled_for, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (checkout_id, email, phone, first_name, total_price,
                 json.dumps(products), checkout_url, "pending",
                 scheduled_for, int(time.time()))
            )
        except sqlite3.IntegrityError:
            return {"ok": True, "status": "already_queued"}

    # Hintergrund-Task: nach Delay senden
    asyncio.create_task(_delayed_send(checkout_id, first_name, products, total_price, checkout_url, email, phone))

    return {
        "ok":           True,
        "checkout_id":  checkout_id,
        "scheduled_in": f"{_delay_min()} Minuten",
        "contact":      email or phone
    }


async def _delayed_send(checkout_id: str, first_name: str, products: List[Dict],
                         total: float, checkout_url: str, email: str, phone: str):
    """Wartet den konfigurierten Delay und sendet dann die Rescue-Nachricht."""
    delay = _delay_min() * 60
    await asyncio.sleep(delay)

    # Prüfe ob inzwischen bezahlt wurde (checkout_id nicht mehr in aktiven Carts)
    with _db() as conn:
        ev = conn.execute(
            "SELECT status, recovered FROM cart_events WHERE checkout_id=?", (checkout_id,)
        ).fetchone()
        if ev and ev["recovered"]:
            log.info("Cart %s already recovered — skip rescue", checkout_id)
            return

    msg = await generate_rescue_message(first_name, products, total, checkout_url)

    sent = False
    channel = "none"

    # 1. WhatsApp via Twilio (wenn phone vorhanden + Twilio konfiguriert)
    if phone and _twilio_sid():
        sent    = await _whatsapp_send(phone, msg)
        channel = "whatsapp"

    # 2. Telegram-Alert an Rudolf (immer als Fallback/Kopie)
    owner_msg = (
        f"🛒 <b>Cart Rescue gesendet</b>\n"
        f"👤 {first_name or '?'} · {email or phone}\n"
        f"💰 €{total:.2f} · {len(products)} Produkt(e)\n"
        f"📨 Kanal: {channel}\n"
        f"🔗 <a href='{checkout_url}'>Checkout öffnen</a>"
    )
    await _tg_send(owner_msg)

    if not sent:
        sent    = True
        channel = "telegram_owner_only"

    with _db() as conn:
        conn.execute(
            "UPDATE cart_events SET status='sent', sent_at=?, channel=?, message_text=? WHERE checkout_id=?",
            (int(time.time()), channel, msg, checkout_id)
        )

    log.info("Cart Rescue sent: %s via %s", checkout_id, channel)


async def mark_recovered(checkout_id: str):
    """Markiert einen Checkout als recovered (z.B. nach Zahlung)."""
    init_db()
    with _db() as conn:
        conn.execute(
            "UPDATE cart_events SET recovered=1, status='recovered' WHERE checkout_id=?",
            (checkout_id,)
        )


def get_status() -> Dict:
    init_db()
    with _db() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM cart_events").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM cart_events WHERE status='pending'").fetchone()[0]
        sent      = conn.execute("SELECT COUNT(*) FROM cart_events WHERE status='sent'").fetchone()[0]
        recovered = conn.execute("SELECT COUNT(*) FROM cart_events WHERE recovered=1").fetchone()[0]
        revenue   = conn.execute(
            "SELECT COALESCE(SUM(total_price),0) FROM cart_events WHERE recovered=1"
        ).fetchone()[0]
        recent    = conn.execute(
            """SELECT first_name, email, total_price, status, channel, sent_at
               FROM cart_events ORDER BY created_at DESC LIMIT 5"""
        ).fetchall()

    recovery_rate = round(recovered / max(sent, 1) * 100, 1)
    return {
        "ok":            True,
        "total":         total,
        "pending":       pending,
        "sent":          sent,
        "recovered":     recovered,
        "recovery_rate": recovery_rate,
        "recovered_revenue": round(float(revenue), 2),
        "delay_min":     _delay_min(),
        "whatsapp":      bool(_twilio_sid()),
        "telegram":      bool(_tg_token()),
        "recent":        [dict(r) for r in recent]
    }


async def manual_trigger(email_or_phone: str, product_title: str, price: float, checkout_url: str) -> Dict:
    """Manuell eine Rescue-Nachricht senden (für Tests)."""
    msg = await generate_rescue_message(
        "", [{"title": product_title, "price": price}], price, checkout_url
    )
    sent = False
    if _tg_token():
        await _tg_send(msg)
        sent = True
    return {"ok": sent, "message": msg}


init_db()
