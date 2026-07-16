#!/usr/bin/env python3
"""
Demo-System für High-Ticket Produkte — SuperMegaBot / AIITEC / Telegram.
Erstellt: 2026-07-16 — Wave 13

Features:
- 14-Tage Trial ohne Credit Card
- Demo-Zugänge mit echten Daten aus ineedit.com.co
- Demo-Call Buchung via Telegram-Alert an Rudolf
- Demo-Session-Management (SQLite)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiohttp

log = logging.getLogger("DemoSystem")

# ─── Konfiguration ────────────────────────────────────────────────────────────
TELEGRAM_BOT   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2025-01")
BASE_URL       = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"

_DEMO_DB = Path(__file__).parent.parent / "data" / "demo_sessions.db"


# ─── Datenbank ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DEMO_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DEMO_DB), check_same_thread=False, timeout=5)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS demo_sessions (
            session_id   TEXT PRIMARY KEY,
            email        TEXT NOT NULL,
            name         TEXT,
            company      TEXT,
            product_id   TEXT NOT NULL,
            created_at   REAL NOT NULL,
            expires_at   REAL NOT NULL,
            status       TEXT DEFAULT 'active',
            trial_data   TEXT
        );
        CREATE TABLE IF NOT EXISTS demo_calls (
            call_id      TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL,
            phone        TEXT,
            company      TEXT,
            product_id   TEXT NOT NULL,
            preferred_dt TEXT,
            notes        TEXT,
            created_at   REAL NOT NULL,
            status       TEXT DEFAULT 'pending'
        );
    """)
    conn.commit()
    return conn


# ─── Demo-Session erstellen ───────────────────────────────────────────────────

async def create_demo_session(
    email: str,
    product_id: str = "smb_growth",
    name: str = "",
    company: str = "",
    trial_days: int = 14,
) -> dict[str, Any]:
    """
    Erstellt eine 14-Tage Demo-Session ohne Credit Card.
    Gibt Session-Token, Zugangsdaten und Onboarding-Link zurück.
    """
    session_id = str(uuid.uuid4())
    now = time.time()
    expires_at = now + (trial_days * 86400)

    # Demo-Produkte aus Shopify laden (echte Daten)
    demo_products = await _load_demo_products(limit=10)

    trial_data = {
        "session_id": session_id,
        "product_id": product_id,
        "demo_products": demo_products,
        "dashboard_url": f"{BASE_URL}/demo/{session_id}",
        "bot_command": f"/demo_{session_id[:8]}",
        "api_key": f"demo_{session_id.replace('-', '')[:24]}",
    }

    conn = _db()
    conn.execute(
        """INSERT INTO demo_sessions
           (session_id, email, name, company, product_id, created_at, expires_at, status, trial_data)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, email, name, company, product_id, now, expires_at, "active",
         json.dumps(trial_data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

    # Telegram-Alert an Rudolf
    await _notify_rudolf_new_demo(email, name, company, product_id, session_id, trial_days)

    expires_dt = datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y")
    return {
        "success": True,
        "session_id": session_id,
        "email": email,
        "product_id": product_id,
        "trial_days": trial_days,
        "expires_date": expires_dt,
        "dashboard_url": trial_data["dashboard_url"],
        "api_key": trial_data["api_key"],
        "bot_command": trial_data["bot_command"],
        "demo_products_count": len(demo_products),
        "message": (
            f"Demo-Zugang aktiviert! Du hast {trial_days} Tage kostenlos Zugang. "
            f"Dashboard: {trial_data['dashboard_url']}"
        ),
        "next_steps": [
            f"1. Dashboard öffnen: {trial_data['dashboard_url']}",
            "2. Onboarding-Call buchen (kostenlos, 60 min): /demo_call",
            "3. Telegram-Bot testen: @DudiRudibot",
            "4. Bei Fragen: direkt auf diesen Bot antworten",
        ],
    }


async def get_demo_session(session_id: str) -> Optional[dict[str, Any]]:
    """Gibt eine bestehende Demo-Session zurück."""
    conn = _db()
    row = conn.execute(
        "SELECT * FROM demo_sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    cols = ["session_id", "email", "name", "company", "product_id",
            "created_at", "expires_at", "status", "trial_data"]
    data = dict(zip(cols, row))
    data["trial_data"] = json.loads(data["trial_data"]) if data["trial_data"] else {}
    data["is_expired"] = time.time() > data["expires_at"]
    data["days_remaining"] = max(0, int((data["expires_at"] - time.time()) / 86400))
    return data


def get_demo_credentials(session_id: str) -> dict[str, str]:
    """Gibt Demo-Zugangsdaten ohne Credit Card zurück."""
    conn = _db()
    row = conn.execute(
        "SELECT trial_data, expires_at FROM demo_sessions WHERE session_id=? AND status='active'",
        (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "Session nicht gefunden oder abgelaufen"}
    trial_data = json.loads(row[0]) if row[0] else {}
    expires_dt = datetime.fromtimestamp(row[1]).strftime("%d.%m.%Y %H:%M")
    return {
        "session_id": session_id,
        "dashboard_url": trial_data.get("dashboard_url", f"{BASE_URL}/demo/{session_id}"),
        "api_key": trial_data.get("api_key", ""),
        "bot_command": trial_data.get("bot_command", ""),
        "telegram_bot": "@DudiRudibot",
        "expires": expires_dt,
        "no_credit_card": "true",
        "note": "Kein Credit Card erforderlich. Nach dem Trial kannst du direkt upgraden.",
    }


# ─── Demo-Call buchen ─────────────────────────────────────────────────────────

async def schedule_demo_call(
    name: str,
    email: str,
    product_id: str = "smb_growth",
    phone: str = "",
    company: str = "",
    preferred_datetime: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """
    Bucht einen Demo-Call mit Rudolf — sendet sofort Telegram-Alert.
    Kein externes Calendly nötig: Rudolf bestätigt direkt per Telegram.
    """
    call_id = str(uuid.uuid4())
    now = time.time()

    conn = _db()
    conn.execute(
        """INSERT INTO demo_calls
           (call_id, name, email, phone, company, product_id, preferred_dt, notes, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (call_id, name, email, phone, company, product_id, preferred_datetime, notes, now)
    )
    conn.commit()
    conn.close()

    # Telegram-Alert mit Kalender-ähnlicher Darstellung
    await _notify_rudolf_demo_call(
        call_id, name, email, phone, company, product_id, preferred_datetime, notes
    )

    from modules.high_ticket_products import ALL_HT_PRODUCTS
    product = ALL_HT_PRODUCTS.get(product_id, {})
    product_name = product.get("name", product_id)
    product_price = (
        f"€{product['price_monthly']}/mo"
        if product.get("price_monthly")
        else f"€{product.get('price_onetime', '?')} einmalig"
    )

    return {
        "success": True,
        "call_id": call_id,
        "name": name,
        "email": email,
        "product": product_name,
        "product_price": product_price,
        "preferred_datetime": preferred_datetime or "Flexibel",
        "message": (
            f"Demo-Call wurde angefragt! Rudolf Sarkany wird sich binnen 4 Business-Stunden "
            f"bei dir melden um einen Termin zu bestätigen."
        ),
        "what_to_expect": [
            "60 Minuten 1:1 mit Rudolf Sarkany",
            "Live-Demo deines Shopify-Stores mit echten Daten",
            "ROI-Kalkulation speziell für dein Business",
            "Q&A — alle Fragen werden beantwortet",
            "Unverbindlich — kein Verkaufsdruck",
        ],
        "contact_confirmation": f"Bestätigungs-E-Mail an: {email}",
    }


# ─── Demo-Produkte aus Shopify laden (echte Daten) ───────────────────────────

async def _load_demo_products(limit: int = 10) -> list[dict[str, str]]:
    """Lädt echte Produkte aus ineedit.com.co für Demo-Zwecke."""
    if not SHOPIFY_TOKEN:
        log.warning("DemoSystem: Kein SHOPIFY_ADMIN_API_TOKEN — Demo-Produkte leer")
        return []
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/products.json?limit={limit}&status=active"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    products = data.get("products", [])
                    return [
                        {
                            "id": str(p.get("id", "")),
                            "title": p.get("title", ""),
                            "vendor": p.get("vendor", ""),
                            "product_type": p.get("product_type", ""),
                            "price": p.get("variants", [{}])[0].get("price", "0.00") if p.get("variants") else "0.00",
                        }
                        for p in products
                    ]
                else:
                    log.warning("DemoSystem: Shopify returned %s", r.status)
    except Exception as e:
        log.warning("DemoSystem: Shopify load failed: %s", e)
    return []


# ─── Telegram-Notifications ──────────────────────────────────────────────────

async def _send_telegram(text: str) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        log.warning("DemoSystem: Kein Telegram konfiguriert")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    log.warning("DemoSystem Telegram: %s", await r.text())
    except Exception as e:
        log.warning("DemoSystem Telegram send failed: %s", e)


async def _notify_rudolf_new_demo(
    email: str, name: str, company: str, product_id: str,
    session_id: str, trial_days: int
) -> None:
    from modules.high_ticket_products import ALL_HT_PRODUCTS
    product = ALL_HT_PRODUCTS.get(product_id, {})
    product_name = product.get("name", product_id)
    price_str = (
        f"€{product['price_monthly']}/mo"
        if product.get("price_monthly")
        else f"€{product.get('price_onetime', '?')} einmalig"
    )
    text = (
        f"🆕 <b>NEUE DEMO-SESSION</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name: {name or 'unbekannt'}\n"
        f"📧 E-Mail: {email}\n"
        f"🏢 Firma: {company or 'unbekannt'}\n"
        f"📦 Produkt: {product_name}\n"
        f"💶 Preis: {price_str}\n"
        f"⏰ Trial: {trial_days} Tage\n"
        f"🔗 Session: {session_id[:8]}...\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 Follow-up in 24h empfohlen!"
    )
    await _send_telegram(text)


async def _notify_rudolf_demo_call(
    call_id: str, name: str, email: str, phone: str, company: str,
    product_id: str, preferred_datetime: str, notes: str
) -> None:
    from modules.high_ticket_products import ALL_HT_PRODUCTS
    product = ALL_HT_PRODUCTS.get(product_id, {})
    product_name = product.get("name", product_id)
    price_str = (
        f"€{product['price_monthly']}/mo"
        if product.get("price_monthly")
        else f"€{product.get('price_onetime', '?')} einmalig"
    )
    text = (
        f"📞 <b>DEMO-CALL ANFRAGE</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name: <b>{name}</b>\n"
        f"📧 E-Mail: {email}\n"
        f"📱 Telefon: {phone or 'nicht angegeben'}\n"
        f"🏢 Firma: {company or 'nicht angegeben'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 Produkt: <b>{product_name}</b>\n"
        f"💶 Preis: {price_str}\n"
        f"📅 Wunschtermin: {preferred_datetime or 'flexibel'}\n"
        f"💬 Notizen: {notes or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Call-ID: {call_id[:8]}\n"
        f"👉 Antworten: direkt auf {email} oder {phone or 'E-Mail'}"
    )
    await _send_telegram(text)


# ─── Aktive Demos auflisten ──────────────────────────────────────────────────

def list_active_demos() -> list[dict[str, Any]]:
    """Gibt alle aktiven (nicht abgelaufenen) Demo-Sessions zurück."""
    conn = _db()
    rows = conn.execute(
        """SELECT session_id, email, name, company, product_id, expires_at
           FROM demo_sessions
           WHERE status='active' AND expires_at > ?
           ORDER BY expires_at DESC""",
        (time.time(),)
    ).fetchall()
    conn.close()
    return [
        {
            "session_id": r[0],
            "email": r[1],
            "name": r[2] or "",
            "company": r[3] or "",
            "product_id": r[4],
            "expires_date": datetime.fromtimestamp(r[5]).strftime("%d.%m.%Y"),
            "days_remaining": max(0, int((r[5] - time.time()) / 86400)),
        }
        for r in rows
    ]


def list_pending_calls() -> list[dict[str, Any]]:
    """Gibt alle offenen Demo-Call-Anfragen zurück."""
    conn = _db()
    rows = conn.execute(
        """SELECT call_id, name, email, phone, company, product_id, preferred_dt, notes, created_at
           FROM demo_calls WHERE status='pending'
           ORDER BY created_at DESC""",
    ).fetchall()
    conn.close()
    return [
        {
            "call_id": r[0],
            "name": r[1],
            "email": r[2],
            "phone": r[3] or "",
            "company": r[4] or "",
            "product_id": r[5],
            "preferred_datetime": r[6] or "flexibel",
            "notes": r[7] or "",
            "created_date": datetime.fromtimestamp(r[8]).strftime("%d.%m.%Y %H:%M"),
        }
        for r in rows
    ]


# ─── Demo-Session ablaufen lassen ────────────────────────────────────────────

def expire_old_sessions() -> int:
    """Markiert abgelaufene Sessions als 'expired'. Gibt Anzahl zurück."""
    conn = _db()
    cur = conn.execute(
        "UPDATE demo_sessions SET status='expired' WHERE status='active' AND expires_at < ?",
        (time.time(),)
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


# ─── Async Test ──────────────────────────────────────────────────────────────

async def _demo_test() -> None:
    print("=== DEMO SYSTEM TEST ===\n")

    # Demo-Session erstellen
    result = await create_demo_session(
        email="test@example.com",
        product_id="smb_growth",
        name="Max Mustermann",
        company="Mustermann GmbH",
    )
    print("Demo-Session erstellt:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Demo-Call buchen
    call = await schedule_demo_call(
        name="Max Mustermann",
        email="test@example.com",
        product_id="smb_growth",
        phone="+43 123 456789",
        company="Mustermann GmbH",
        preferred_datetime="Donnerstag 14:00-16:00 Uhr",
        notes="Shopify-Store mit 200 Produkten, brauche Automatisierung",
    )
    print("\nDemo-Call gebucht:")
    print(json.dumps(call, indent=2, ensure_ascii=False))

    # Aktive Demos
    demos = list_active_demos()
    print(f"\nAktive Demos: {len(demos)}")


if __name__ == "__main__":
    import json
    asyncio.run(_demo_test())
