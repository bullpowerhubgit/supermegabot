"""
whatsapp_abandoned_cart.py — WhatsApp Abandoned Cart Recovery
Sends personalized WhatsApp messages to customers who left carts behind.
Uses Meta WhatsApp Business Cloud API + Shopify abandoned checkouts.
"""
import os
import logging
import sqlite3
import json
from datetime import datetime, timezone, timedelta
import aiohttp

log = logging.getLogger(__name__)

# ── Env vars ──────────────────────────────────────────────────────────────────
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
SHOPIFY_SHOP_DOMAIN      = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VERSION      = os.getenv("SHOPIFY_API_VERSION", "2024-01")

DB_PATH = "data/whatsapp_carts.db"
WA_BASE = "https://graph.facebook.com/" + os.getenv("WA_API_VERSION", "v21.0")


# ── DB init ───────────────────────────────────────────────────────────────────

def _db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_carts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checkout_id   TEXT    UNIQUE,
            phone         TEXT,
            customer_name TEXT,
            total_price   TEXT,
            sent_at       TEXT,
            status        TEXT DEFAULT 'sent'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date          TEXT PRIMARY KEY,
            sent          INTEGER DEFAULT 0,
            recovered     INTEGER DEFAULT 0,
            revenue       REAL    DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()


def _is_already_sent(checkout_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("SELECT 1 FROM sent_carts WHERE checkout_id=?", (checkout_id,)).fetchone()
    conn.close()
    return row is not None


def _mark_sent(checkout_id: str, phone: str, name: str, total: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO sent_carts (checkout_id, phone, customer_name, total_price, sent_at) VALUES (?,?,?,?,?)",
        (checkout_id, phone, name, total, datetime.now(timezone.utc).isoformat()),
    )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO daily_stats(date,sent) VALUES(?,1) ON CONFLICT(date) DO UPDATE SET sent=sent+1",
        (today,),
    )
    conn.commit()
    conn.close()


# ── Shopify ───────────────────────────────────────────────────────────────────

async def get_abandoned_checkouts() -> list:
    """
    Fetch Shopify abandoned checkouts from the last 2–24 hours that have a phone number.
    Returns list of {checkout_id, customer_name, customer_phone, total_price, items, cart_url}.
    """
    if not SHOPIFY_SHOP_DOMAIN or not SHOPIFY_ADMIN_API_TOKEN:
        log.warning("Shopify credentials not set — skipping abandoned checkout fetch")
        return []

    now     = datetime.now(timezone.utc)
    cutoff  = now - timedelta(hours=24)
    min_age = now - timedelta(hours=2)

    url = (
        f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}"
        f"/checkouts.json?since_id=0&limit=50&status=open"
    )
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
        "Content-Type":           "application/json",
    }

    checkouts = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                data = await r.json()
                raw  = data.get("checkouts", [])
    except Exception as exc:
        log.error("Shopify checkout fetch error: %s", exc)
        return []

    for c in raw:
        # Must be abandoned (no completed_at) and in time window
        if c.get("completed_at"):
            continue
        created_raw = c.get("created_at", "")
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if not (cutoff <= created <= min_age):
            continue

        # Need a phone number
        customer = c.get("customer") or {}
        phone    = (
            c.get("shipping_address", {}).get("phone", "")
            or customer.get("phone", "")
            or c.get("billing_address", {}).get("phone", "")
        )
        if not phone:
            continue

        items = [
            f"{li.get('title','?')} ×{li.get('quantity',1)}"
            for li in c.get("line_items", [])
        ]

        checkouts.append({
            "checkout_id":    str(c.get("id", "")),
            "customer_name":  customer.get("first_name") or c.get("email", "Kunde").split("@")[0],
            "customer_phone": phone,
            "total_price":    c.get("total_price", "0.00"),
            "currency":       c.get("currency", "EUR"),
            "items":          items,
            "items_count":    len(items),
            "cart_url":       c.get("abandoned_checkout_url", f"https://{SHOPIFY_SHOP_DOMAIN}/cart"),
        })

    log.info("Shopify: found %d abandoned checkouts eligible for WA recovery", len(checkouts))
    return checkouts


# ── WhatsApp ──────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Ensure phone is E.164 with country code (default +49 if none)."""
    phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if not phone.startswith("+"):
        if phone.startswith("0"):
            phone = "+49" + phone[1:]
        else:
            phone = "+" + phone
    return phone


async def send_whatsapp_message(phone: str, message: str) -> dict:
    """
    Send a WhatsApp text message via Meta Cloud API.
    Returns response dict from Meta.
    """
    if not WHATSAPP_PHONE_NUMBER_ID or not WHATSAPP_ACCESS_TOKEN:
        log.warning("WhatsApp credentials not set — message not sent")
        return {"error": "credentials_missing"}

    phone = _normalize_phone(phone)
    url   = f"{WA_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                phone,
        "type":              "text",
        "text":              {"preview_url": True, "body": message},
    }
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as r:
            resp = await r.json()
            if r.status == 200:
                log.info("WA sent to %s", phone)
            else:
                log.warning("WA send error %d for %s: %s", r.status, phone, resp)
            return resp


# ── Main campaign ─────────────────────────────────────────────────────────────

async def run_recovery_campaign() -> dict:
    """
    Main entry point: fetch abandoned carts, send WA messages, track results.
    Returns {sent, skipped, errors}.
    """
    _db_init()
    checkouts = await get_abandoned_checkouts()

    sent   = 0
    skipped = 0
    errors  = 0

    for cart in checkouts:
        cid  = cart["checkout_id"]
        if _is_already_sent(cid):
            skipped += 1
            continue

        items_str = ", ".join(cart["items"][:3])
        if len(cart["items"]) > 3:
            items_str += f" (+{len(cart['items'])-3} weitere)"

        msg = (
            f"Hallo {cart['customer_name']}! 😊 "
            f"Du hast noch {items_str} in deinem Warenkorb bei ineedit.com.co. "
            f"Mit Code RESCUE10 sparst du 10%! → {cart['cart_url']}"
        )

        try:
            resp = await send_whatsapp_message(cart["customer_phone"], msg)
            if resp.get("error"):
                errors += 1
            else:
                _mark_sent(cid, cart["customer_phone"], cart["customer_name"], cart["total_price"])
                sent += 1
        except Exception as exc:
            log.error("WA send exception for checkout %s: %s", cid, exc)
            errors += 1

    log.info("WA Cart Recovery done — sent=%d skipped=%d errors=%d", sent, skipped, errors)
    return {"sent": sent, "skipped": skipped, "errors": errors}


def get_status() -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        _db_init()
        conn   = sqlite3.connect(DB_PATH)
        row    = conn.execute(
            "SELECT sent, recovered, revenue FROM daily_stats WHERE date=?", (today,)
        ).fetchone()
        conn.close()
        sent, recovered, revenue = (row if row else (0, 0, 0.0))
    except Exception:
        sent = recovered = 0
        revenue = 0.0

    return {
        "module":           "whatsapp_abandoned_cart",
        "wa_key_set":       bool(WHATSAPP_ACCESS_TOKEN),
        "shopify_set":      bool(SHOPIFY_ADMIN_API_TOKEN),
        "sent_today":       sent,
        "recovered_today":  recovered,
        "revenue_recovered": revenue,
    }
