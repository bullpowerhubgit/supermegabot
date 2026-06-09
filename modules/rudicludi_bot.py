#!/usr/bin/env python3
"""
RudiCludiBot — Kunden-Bot für SuperMegaBot SaaS
@RudiCludiBot — öffentlicher Bot für Kunden

Commands:
  /start      — Begrüßung + Produkt-Übersicht
  /plans      — Abo-Pläne mit Preisen
  /subscribe  — Checkout-Link für gewählten Plan
  /status     — Eigener Abo-Status
  /support    — Support-Anfrage weiterleiten
  /help       — Alle Commands
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp

log = logging.getLogger("RudiCludiBot")

BASE_DIR = Path(__file__).parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_2", "")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8888")

PLANS_TEXT = """
💎 <b>SuperMegaBot Pläne</b>

🟢 <b>Starter — €49/Monat</b>
• Shopify Sync (500 Produkte)
• Basic AI (50 Calls/Tag)
• Telegram Bot
• 14 Tage kostenlos testen

🔵 <b>Pro — €99/Monat</b>
• Alle Integrationen
• Erweiterte KI (500 Calls/Tag)
• SEO Autopilot
• Analytics Dashboard
• Digistore24 Sync
• 14 Tage kostenlos testen

🟣 <b>Enterprise — €299/Monat</b>
• Unbegrenzte KI-Calls
• White-Label Option
• Priority Support
• Custom Agents
• Bis zu 5 Stores
• 14 Tage kostenlos testen

👉 /subscribe starter|pro|enterprise
"""

WELCOME_TEXT = """
👋 Willkommen bei <b>SuperMegaBot</b>!

Ich bin dein KI-gestützter E-Commerce Assistent.
Automatisiere Shopify, Digistore24, Marketing und mehr.

📋 /plans — Alle Pläne ansehen
🚀 /subscribe — Jetzt starten (14 Tage gratis)
❓ /support — Hilfe bekommen
"""


async def _send(chat_id: str | int, text: str, keyboard=None) -> None:
    if not BOT_TOKEN:
        return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning(f"Send error: {e}")


async def _get_checkout_url(plan: str, email: str) -> str | None:
    """Holt Checkout-URL vom SuperMegaBot Dashboard."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{DASHBOARD_URL}/api/checkout",
                json={"plan": plan, "email": email, "base_url": DASHBOARD_URL},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json()
                return data.get("checkout_url")
    except Exception as e:
        log.error(f"Checkout URL error: {e}")
        return None


async def handle_update(update: dict) -> None:
    msg = update.get("message") or update.get("callback_query", {}).get("message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user = msg["chat"].get("first_name", "Kunde")
    text = msg.get("text", "").strip()

    if text.startswith("/start"):
        await _send(chat_id, WELCOME_TEXT, keyboard=[
            [{"text": "📋 Pläne ansehen", "callback_data": "plans"}],
            [{"text": "🚀 Kostenlos starten", "callback_data": "subscribe_pro"}],
        ])

    elif text.startswith("/plans"):
        await _send(chat_id, PLANS_TEXT)

    elif text.startswith("/subscribe"):
        parts = text.split()
        plan = parts[1].lower() if len(parts) > 1 else "pro"
        if plan not in ("starter", "pro", "enterprise"):
            await _send(chat_id, "Bitte wähle: /subscribe starter | /subscribe pro | /subscribe enterprise")
            return
        await _send(chat_id, f"⏳ Erstelle Checkout für <b>{plan.title()}</b>-Plan...")
        # Email aus Telegram-Profil nicht verfügbar — User auffordern
        await _send(chat_id, (
            f"Sende mir deine E-Mail-Adresse für den {plan.title()}-Plan.\n"
            f"Format: <code>email@example.com</code>"
        ))
        # TODO: Conversation state für Email-Eingabe

    elif text.startswith("/support"):
        question = text[9:].strip() or "Neue Support-Anfrage"
        if ADMIN_CHAT_ID:
            await _send(ADMIN_CHAT_ID,
                f"📩 <b>Support von {user}</b> (Chat: {chat_id})\n\n{question}")
        await _send(chat_id, "✅ Deine Anfrage wurde weitergeleitet. Wir melden uns bald!")

    elif text.startswith("/help"):
        await _send(chat_id, (
            "<b>@RudiCludiBot Commands</b>\n\n"
            "/start — Begrüßung\n"
            "/plans — Alle Abo-Pläne\n"
            "/subscribe starter|pro|enterprise — Jetzt abonnieren\n"
            "/status — Dein Abo-Status\n"
            "/support — Support-Anfrage\n"
            "/help — Diese Hilfe"
        ))

    elif "@" in text and "." in text:
        # Email-Eingabe für Checkout
        email = text.strip()
        await _send(chat_id, f"⏳ Erstelle Checkout-Link für {email}...")
        url = await _get_checkout_url("pro", email)
        if url:
            await _send(chat_id,
                f"🚀 <b>Dein persönlicher Checkout-Link:</b>\n\n{url}\n\n"
                f"✅ 14 Tage kostenlos testen — jederzeit kündbar.")
        else:
            await _send(chat_id, "❌ Checkout konnte nicht erstellt werden. Versuche es später erneut oder kontaktiere /support")


async def run():
    if not BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN_2 nicht gesetzt — RudiCludiBot inaktiv")
        return

    log.info("RudiCludiBot (@RudiCludiBot) gestartet")
    offset = 0
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30, "limit": 10},
                    timeout=aiohttp.ClientTimeout(total=35),
                ) as r:
                    if r.status == 401:
                        log.error("RudiCludiBot: Ungültiger Token (TELEGRAM_BOT_TOKEN_2)")
                        return
                    data = await r.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        asyncio.create_task(handle_update(update))
        except Exception as e:
            log.warning(f"RudiCludiBot poll error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
    asyncio.run(run())
