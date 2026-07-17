#!/usr/bin/env python3
"""
Sofia SMS Agent — Autonome SMS-Verkäuferin
=========================================
- Eingehende SMS: Gesprächsgedächtnis + Verkaufsfluss → Payment-Link
- Ausgehend: Welcome, Cart-Recovery (3-Schritt), Upsell, Weekly-Deals
- Deduplication, Opt-Out-Handling, Telegram-Alerts bei Kaufsignal
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("SofiaSMS")

TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER", "")
TELEGRAM_BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT= os.getenv("TELEGRAM_CHAT_ID", "")
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
BASE_URL     = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"

# ── Datenbank ───────────────────────────────────────────────────────────────────

_DB = Path(__file__).parent.parent / "data" / "sofia_sms.db"

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB), check_same_thread=False, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_conversations (
            phone       TEXT PRIMARY KEY,
            history     TEXT NOT NULL DEFAULT '[]',
            buy_signal  INTEGER DEFAULT 0,
            product     TEXT DEFAULT '',
            opt_out     INTEGER DEFAULT 0,
            last_msg_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_outbox (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number   TEXT NOT NULL,
            message     TEXT NOT NULL,
            campaign    TEXT DEFAULT '',
            status      TEXT DEFAULT 'pending',
            sent_at     REAL DEFAULT 0,
            created_at  REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_sent_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number   TEXT NOT NULL,
            message     TEXT NOT NULL,
            campaign    TEXT DEFAULT '',
            sid         TEXT DEFAULT '',
            created_at  REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


# ── Opt-Out Erkennung ─────────────────────────────────────────────────────────

_OPT_OUT_KEYWORDS = {"stop", "stopp", "abmelden", "keine sms", "nein danke", "unsubscribe", "quit", "end", "cancel"}

def _is_opt_out(text: str) -> bool:
    return any(k in text.lower() for k in _OPT_OUT_KEYWORDS)

def _is_opt_in(text: str) -> bool:
    return any(k in text.lower() for k in {"ja", "start", "info", "hilfe", "angebote", "newsletter"})


# ── Sofia SMS Persönlichkeit ──────────────────────────────────────────────────

SMS_SYSTEM = """Du bist Sofia — die KI-Assistentin von AIITEC (Rudolf Sarkany).
Du antwortest auf SMS. Regeln:
- Maximal 160 Zeichen pro Antwort (SMS-Limit!)
- Deutsch, warmherzig, direkt — kein Roboter-Ton
- Bei Interesse → Payment-Link anbieten
- Bei Kaufsignal → schreibe [KAUF] am Ende (wird nicht gesendet)
- Bei Opt-Out Wunsch → freundlich verabschieden, schreibe [OPTOUT]

Produkte: Smart Home ab €69 | SuperMegaBot €297 | SaaS ab €497/Mo
Shop: ineedit.com.co | Tel: """ + TWILIO_PHONE


async def _sofia_sms_reply(phone: str, user_text: str) -> str:
    """Generiert Sofia-Antwort mit Gesprächsgedächtnis."""
    conn = _db()
    row = conn.execute(
        "SELECT history, buy_signal, product FROM sms_conversations WHERE phone=?", (phone,)
    ).fetchone()

    history   = json.loads(row[0]) if row else []
    buy_signal= bool(row[1]) if row else False
    product   = row[2] if row else ""

    history.append({"role": "user", "content": user_text})

    # Kontext: letzte 6 SMS
    ctx = "\n".join(
        f"{'Kunde' if m['role']=='user' else 'Sofia'}: {m['content']}"
        for m in history[-6:]
    )
    prompt = f"SMS-Verlauf:\n{ctx}\n\nSofia antwortet (max 140 Zeichen, ohne Anführungszeichen):"

    reply = ""
    try:
        from modules.ai_client import ai_complete
        reply = await ai_complete(prompt, system=SMS_SYSTEM, model_hint="fast", max_tokens=60) or ""
    except Exception as e:
        log.warning("Sofia SMS ai: %s", e)
        reply = f"Danke! Unser Shop: {SHOP_URL} | Tel: {TWILIO_PHONE}"

    # Marker erkennen
    if "[KAUF]" in reply or "kaufsignal" in reply.lower():
        buy_signal = True
        product    = _extract_product(reply) or product or "Smart Home Starter Set"
    if "[OPTOUT]" in reply:
        conn.execute("UPDATE sms_conversations SET opt_out=1 WHERE phone=?", (phone,))
        conn.commit()
        conn.close()
        clean = re.sub(r'\[KAUF\]|\[OPTOUT\]', '', reply).strip()[:160]
        return clean

    clean = re.sub(r'\[KAUF\]|\[OPTOUT\]', '', reply).strip()[:160]
    history.append({"role": "assistant", "content": clean})

    now = time.time()
    conn.execute("""
        INSERT INTO sms_conversations (phone, history, buy_signal, product, last_msg_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(phone) DO UPDATE SET
            history=excluded.history,
            buy_signal=excluded.buy_signal,
            product=CASE WHEN excluded.product!='' THEN excluded.product ELSE product END,
            last_msg_at=excluded.last_msg_at
    """, (phone, json.dumps(history, ensure_ascii=False), int(buy_signal), product, now))
    conn.commit()
    conn.close()

    # Kaufsignal → Telegram Alert + Payment-Link SMS
    if buy_signal:
        asyncio.create_task(_on_buy_signal(phone, product))

    return clean


def _extract_product(text: str) -> str:
    for p in ["SuperMegaBot", "Balkonkraftwerk", "Solar", "Rasenmäher", "Sicherheitskamera",
              "Thermostat", "LED", "Starter", "Blueprint", "Quickstart", "Enterprise", "Agency"]:
        if p.lower() in text.lower():
            return p
    return ""


async def _on_buy_signal(phone: str, product: str) -> None:
    """Kaufsignal: Telegram Alert + Payment-Link senden."""
    from modules.sofia_voice_agent import _get_stripe_payment_link
    payment_url = _get_stripe_payment_link(product)

    # Payment SMS
    sms = (
        f"Super! Hier ist Ihr persönlicher Bestelllink:\n"
        f"{payment_url}\n"
        f"Fragen? {TWILIO_PHONE} — Sofia"
    )
    await send_sms(phone, sms[:160], campaign="buy_signal")

    # Telegram
    if TELEGRAM_BOT and TELEGRAM_CHAT:
        text = f"🔥 SMS KAUFSIGNAL!\n📱 {phone}\n🛍 {product}\n💳 {payment_url}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                await s.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT, "text": text},
                )
        except Exception as e:
            log.debug("SMS buy signal TG: %s", e)


# ── Inbound SMS Handler ────────────────────────────────────────────────────────

async def handle_sms_inbound(from_number: str, body: str) -> str:
    """Verarbeitet eingehende SMS — Sofia antwortet mit Gesprächsgedächtnis.
    Gibt TwiML-Response-Text zurück (für Twilio)."""
    if not body:
        return '<?xml version="1.0"?><Response/>'

    conn = _db()
    row = conn.execute("SELECT opt_out FROM sms_conversations WHERE phone=?", (from_number,)).fetchone()
    conn.close()
    if row and row[0]:
        twiml = '<?xml version="1.0"?><Response><Message>Sie sind abgemeldet. Antworten Sie START um sich wieder anzumelden.</Message></Response>'
        return twiml

    if _is_opt_out(body):
        conn = _db()
        conn.execute("""
            INSERT INTO sms_conversations (phone, history, last_msg_at, opt_out)
            VALUES (?,?,?,1)
            ON CONFLICT(phone) DO UPDATE SET opt_out=1
        """, (from_number, "[]", time.time()))
        conn.commit()
        conn.close()
        reply = "Sie wurden abgemeldet. Antworten Sie START um wieder Nachrichten zu erhalten."
        asyncio.create_task(_telegram_sms_alert(from_number, body, reply, False))
        return f'<?xml version="1.0"?><Response><Message>{reply}</Message></Response>'

    reply = await _sofia_sms_reply(from_number, body)
    asyncio.create_task(_telegram_sms_alert(from_number, body, reply, False))
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'


async def _telegram_sms_alert(phone: str, incoming: str, reply: str, buy: bool) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    icon = "🔥" if buy else "📱"
    text = f"{icon} SMS von {phone}\n💬 {incoming[:80]}\n🤖 Sofia: {reply[:80]}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text},
            )
    except Exception:
        pass


# ── Outbound SMS ───────────────────────────────────────────────────────────────

async def send_sms(to_number: str, message: str, campaign: str = "manual") -> Optional[str]:
    """Sendet eine einzelne SMS via Twilio. Gibt Message-SID zurück."""
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_PHONE:
        log.warning("Sofia SMS: Twilio nicht konfiguriert")
        return None

    # Opt-Out check
    conn = _db()
    row = conn.execute("SELECT opt_out FROM sms_conversations WHERE phone=?", (to_number,)).fetchone()
    conn.close()
    if row and row[0]:
        log.info("Sofia SMS: %s hat opt-out — übersprungen", to_number)
        return None

    try:
        import base64
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                data={"From": TWILIO_PHONE, "To": to_number, "Body": message[:160]},
                headers={"Authorization": f"Basic {auth}"},
            ) as r:
                data = await r.json()
                if r.status in (200, 201):
                    sid = data.get("sid", "")
                    conn = _db()
                    conn.execute(
                        "INSERT INTO sms_sent_log (to_number,message,campaign,sid,created_at) VALUES (?,?,?,?,?)",
                        (to_number, message[:160], campaign, sid, time.time()),
                    )
                    conn.commit()
                    conn.close()
                    log.info("SMS ✅ → %s [%s] SID=%s", to_number, campaign, sid)
                    return sid
                log.warning("SMS Twilio %s: %s", r.status, data.get("message", ""))
                return None
    except Exception as e:
        log.error("send_sms error: %s", e)
        return None


# ── SMS-Kampagnen ─────────────────────────────────────────────────────────────

async def send_welcome_sms(phone: str, name: str = "", product: str = "") -> Optional[str]:
    """Willkommens-SMS für neue Leads / Subscriber."""
    name_part = f" {name.split()[0]}" if name else ""
    if product:
        msg = (
            f"Hallo{name_part}! Sofia hier von AIITEC 👋 "
            f"Ihr Interesse an {product} freut uns! "
            f"Mehr Infos: {SHOP_URL} | Fragen? Einfach antworten!"
        )
    else:
        msg = (
            f"Hallo{name_part}! Sofia hier von AIITEC 👋 "
            f"Smart Home & KI-Automation ab €69. "
            f"Angebote: {SHOP_URL} | Einfach antworten für Infos!"
        )
    return await send_sms(phone, msg[:160], campaign="welcome")


async def send_cart_recovery_sms(phone: str, product: str, step: int = 1) -> Optional[str]:
    """Warenkorb-Abbrecher SMS — 3-Schritt-Sequenz."""
    from modules.sofia_voice_agent import _get_stripe_payment_link
    link = _get_stripe_payment_link(product) if product else f"{SHOP_URL}/cart"

    if step == 1:
        msg = f"Hallo! Sie haben {product or 'Produkte'} im Warenkorb vergessen 🛒 Jetzt bestellen: {link}"
    elif step == 2:
        msg = f"Nur noch wenige auf Lager! Ihr {product or 'Artikel'} wartet. Jetzt sichern: {link}"
    else:
        msg = f"Letzter Hinweis: {product or 'Ihr Artikel'} — 10% Rabatt mit Code SOFIA10: {link}"

    return await send_sms(phone, msg[:160], campaign=f"cart_recovery_step{step}")


async def send_upsell_sms(phone: str, purchased_product: str, upsell_product: str = "") -> Optional[str]:
    """Post-Purchase Upsell SMS."""
    from modules.sofia_voice_agent import _get_stripe_payment_link
    up = upsell_product or "SuperMegaBot KI-Automation"
    link = _get_stripe_payment_link(up)
    msg = (
        f"Danke für Ihren Kauf von {purchased_product}! 🎉 "
        f"Passend dazu: {up} — {link}"
    )
    return await send_sms(phone, msg[:160], campaign="upsell")


async def send_weekly_deals_blast(numbers: list, deals_text: str = "") -> dict:
    """Weekly Deals SMS an alle Subscriber (max 200/Durchlauf)."""
    if not deals_text:
        deals_text = f"🔥 Deals diese Woche: Smart Home ab €69, Solar-Sets ab €299. Shop: {SHOP_URL} | Antwort STOP = Abmeldung"

    sent = 0
    failed = 0
    for number in numbers[:200]:
        sid = await send_sms(number, deals_text[:160], campaign="weekly_deals")
        if sid:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.3)  # Twilio Rate-Limit

    log.info("Sofia Weekly Deals: %d gesendet, %d fehler", sent, failed)
    return {"sent": sent, "failed": failed, "total": len(numbers)}


async def run_sms_outbox() -> dict:
    """Verarbeitet pending SMS aus der Outbox (max 50/Durchlauf)."""
    conn = _db()
    rows = conn.execute(
        "SELECT id, to_number, message, campaign FROM sms_outbox WHERE status='pending' ORDER BY created_at ASC LIMIT 50"
    ).fetchall()
    conn.close()

    sent = 0
    failed = 0
    for row in rows:
        oid, to_number, message, campaign = row
        sid = await send_sms(to_number, message, campaign)
        conn = _db()
        if sid:
            conn.execute("UPDATE sms_outbox SET status='sent', sent_at=? WHERE id=?", (time.time(), oid))
            sent += 1
        else:
            conn.execute("UPDATE sms_outbox SET status='failed' WHERE id=?", (oid,))
            failed += 1
        conn.commit()
        conn.close()
        await asyncio.sleep(0.2)

    return {"sent": sent, "failed": failed, "total": len(rows)}


def queue_sms(to_number: str, message: str, campaign: str = "manual") -> int:
    """Fügt SMS zur Outbox hinzu (für spätere Verarbeitung)."""
    conn = _db()
    cur = conn.execute(
        "INSERT INTO sms_outbox (to_number, message, campaign, created_at) VALUES (?,?,?,?)",
        (to_number, message[:160], campaign, time.time()),
    )
    conn.commit()
    oid = cur.lastrowid
    conn.close()
    return oid


def get_sms_stats() -> dict:
    """SMS-Statistiken aus DB."""
    try:
        conn = _db()
        total_sent    = conn.execute("SELECT COUNT(*) FROM sms_sent_log").fetchone()[0]
        total_inbound = conn.execute("SELECT COUNT(*) FROM sms_conversations").fetchone()[0]
        buy_signals   = conn.execute("SELECT COUNT(*) FROM sms_conversations WHERE buy_signal=1").fetchone()[0]
        opt_outs      = conn.execute("SELECT COUNT(*) FROM sms_conversations WHERE opt_out=1").fetchone()[0]
        pending       = conn.execute("SELECT COUNT(*) FROM sms_outbox WHERE status='pending'").fetchone()[0]
        active_convos = conn.execute(
            "SELECT COUNT(*) FROM sms_conversations WHERE last_msg_at > ?", (time.time() - 86400,)
        ).fetchone()[0]
        conn.close()
        return {
            "total_sent":     total_sent,
            "total_inbound":  total_inbound,
            "buy_signals":    buy_signals,
            "opt_outs":       opt_outs,
            "active_convos_24h": active_convos,
            "outbox_pending": pending,
        }
    except Exception as e:
        return {"error": str(e)}


async def run_cart_recovery_campaign() -> dict:
    """Liest Warenkorbabbrecher aus DB und sendet Sequenz-SMS."""
    sent = 0
    try:
        import sqlite3 as _sq
        cart_db = Path(__file__).parent.parent / "data" / "abandoned_carts.db"
        if not cart_db.exists():
            return {"sent": 0, "note": "Keine Cart-DB"}
        conn = _sq.connect(str(cart_db), timeout=5)
        rows = conn.execute(
            """SELECT phone, product_title, sms_step
               FROM abandoned_carts
               WHERE phone != '' AND sms_step < 3 AND opt_out = 0
                 AND created_at < ? AND (last_sms_at IS NULL OR last_sms_at < ?)
               LIMIT 30""",
            (time.time() - 1800, time.time() - 86400),
        ).fetchall()
        conn.close()
        for phone, product, step in rows:
            sid = await send_cart_recovery_sms(phone, product or "", step + 1)
            if sid:
                c = _sq.connect(str(cart_db), timeout=5)
                c.execute(
                    "UPDATE abandoned_carts SET sms_step=sms_step+1, last_sms_at=? WHERE phone=?",
                    (time.time(), phone),
                )
                c.commit()
                c.close()
                sent += 1
                await asyncio.sleep(0.5)
    except Exception as e:
        log.warning("cart_recovery_sms: %s", e)
    return {"sent": sent}
