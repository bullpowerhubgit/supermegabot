#!/usr/bin/env python3
"""
Sofia — KI-Verkaufsagentin für AIITEC
Vollautomatischer Sprachagent: Anruf → Bedarfsanalyse → Empfehlung → Abschluss → SMS + Telegram
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, Optional

import aiohttp

log = logging.getLogger("Sofia")

TWILIO_SID    = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE  = os.getenv("TWILIO_PHONE_NUMBER", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_KEY    = os.getenv("STRIPE_SECRET_KEY", "")
SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
BASE_URL      = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"

# In-memory Gesprächsspeicher (Call-SID → Verlauf)
_conversations: Dict[str, dict] = {}

SOFIA_SYSTEM = """Du bist Sofia, eine selbstbewusste deutschsprachige Verkäuferin von AIITEC (ineedit.com.co).
Dein Ziel: Bedarf verstehen → passendes Smart-Home/Tech-Produkt empfehlen → Kauf abschließen.

REGELN:
- Antworte IMMER auf Deutsch, kurz (1-3 Sätze), gesprächig, warm aber direkt
- Stelle maximal 2 Fragen zum Bedarf bevor du empfiehlst
- Empfehle EIN konkretes Produkt mit Preis — keine Optionsliste
- Einwände behandeln: "zu teuer" → Nutzen betonen / kleinere Alternative; "muss überlegen" → sanfter Druck + Knappheit
- Wenn Kaufbereitschaft → frage: "Soll ich Ihnen den Link direkt per SMS schicken?"
- Wenn JA/OK/Ja bitte → antworte mit: [SMS_SENDEN] und dem Produkt-Name

PRODUKTE (empfehle je nach Bedarf):
- Smart Home Starter Set: €89 — für Einsteiger, einfache Installation
- KI-Sicherheitskamera 4K: €129 — für Sicherheit/Überwachung
- Solar Balkonkraftwerk 800W: €449 — für Stromsparen
- Smart LED System (10 Lampen): €69 — für Ambiente/Licht
- Roboter-Rasenmäher AI: €349 — für Gartenpflege
- Smart Thermostat Pro: €149 — für Heizungssteuerung

KAUFSIGNALE erkennen: "interessant", "klingt gut", "ja gerne", "wie viel", "bestellen" → markiere mit [KAUFSIGNAL]"""


async def _ai_response(call_sid: str, user_text: str) -> str:
    """Generiert Sofia-Antwort via Claude Haiku."""
    conv = _conversations.setdefault(call_sid, {"history": [], "buy_signal": False, "product": None})
    conv["history"].append({"role": "user", "content": user_text})

    messages = conv["history"][-10:]  # max 10 turns

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "system": SOFIA_SYSTEM,
                    "messages": messages,
                },
            ) as r:
                data = await r.json()
                reply = data.get("content", [{}])[0].get("text", "Entschuldigung, können Sie das wiederholen?")
    except Exception as e:
        log.warning("Sofia AI: %s", e)
        reply = "Entschuldigung, einen Moment bitte."

    # Kaufsignal detektieren
    if "[KAUFSIGNAL]" in reply or "[SMS_SENDEN]" in reply:
        conv["buy_signal"] = True
        # Produkt aus Text extrahieren
        for prod in ["Solar", "Kamera", "Thermostat", "Rasenmäher", "LED", "Starter"]:
            if prod in reply:
                conv["product"] = prod
                break

    # Markers aus Antwort entfernen
    clean = re.sub(r'\[KAUFSIGNAL\]|\[SMS_SENDEN\]', '', reply).strip()
    conv["history"].append({"role": "assistant", "content": clean})
    return clean


def _twiml_gather(say_text: str, call_sid: str, timeout: int = 5) -> str:
    """Erstellt TwiML mit <Say> + <Gather speech>."""
    action_url = f"{BASE_URL}/api/voice/respond?call_sid={call_sid}"
    # Polly.Vicki = AWS Polly deutsche Frauenstimme via Twilio
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="de-DE" timeout="{timeout}" action="{action_url}" method="POST">
    <Say voice="Polly.Vicki" language="de-DE">{say_text}</Say>
  </Gather>
  <Say voice="Polly.Vicki" language="de-DE">Ich habe leider nichts verstanden. Auf Wiederhören!</Say>
  <Hangup/>
</Response>"""


def _twiml_say_hangup(say_text: str) -> str:
    """TwiML für finale Nachricht + Auflegen."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Vicki" language="de-DE">{say_text}</Say>
  <Hangup/>
</Response>"""


async def handle_incoming_call(call_sid: str, from_number: str) -> str:
    """Begrüßung beim eingehenden Anruf."""
    _conversations[call_sid] = {
        "history": [], "buy_signal": False, "product": None,
        "from": from_number, "start": time.time(),
    }
    greeting = "AIITEC, guten Tag, hier ist Sofia. Was kann ich für Sie tun?"
    return _twiml_gather(greeting, call_sid, timeout=6)


async def handle_voice_response(call_sid: str, speech_result: str, confidence: float = 1.0) -> str:
    """Verarbeitet Spracheingabe → AI-Antwort → TwiML."""
    if not speech_result or confidence < 0.4:
        return _twiml_gather("Ich habe Sie leider nicht verstanden. Könnten Sie das wiederholen?", call_sid)

    log.info("Sofia [%s] Kunde: %s (conf=%.2f)", call_sid, speech_result[:80], confidence)

    conv = _conversations.get(call_sid, {})
    wants_sms = any(w in speech_result.lower() for w in ["ja", "ja bitte", "ok", "klar", "gerne", "schicken"])
    send_sms_trigger = conv.get("buy_signal") and wants_sms

    if send_sms_trigger:
        reply = await _ai_response(call_sid, speech_result)
        asyncio.create_task(_post_call_actions(call_sid, sms_now=True))
        return _twiml_say_hangup(
            f"{reply} Ich schicke Ihnen den Link gerade per SMS. Vielen Dank und auf Wiederhören!"
        )

    reply = await _ai_response(call_sid, speech_result)
    log.info("Sofia [%s] antwortet: %s", call_sid, reply[:80])

    # Prüfe ob SMS-Angebot im Reply
    if "sms schicken" in reply.lower() or "link per sms" in reply.lower():
        return _twiml_gather(reply, call_sid, timeout=8)

    return _twiml_gather(reply, call_sid)


async def handle_call_status(call_sid: str, call_status: str, duration: int) -> None:
    """Wird aufgerufen wenn Anruf endet — sendet SMS + Telegram."""
    if call_status not in ("completed", "busy", "no-answer"):
        return

    conv = _conversations.pop(call_sid, {})
    from_number = conv.get("from", "")
    buy_signal  = conv.get("buy_signal", False)
    product     = conv.get("product", "Smart Home Produkt")
    history     = conv.get("history", [])

    log.info("Sofia call %s ended: %s, %ds, buy=%s", call_sid, call_status, duration, buy_signal)

    # SMS nach Anrufen >30 Sekunden
    if duration >= 30 and from_number and call_status == "completed":
        asyncio.create_task(_send_post_call_sms(from_number, product, buy_signal))

    # Telegram-Alert immer
    asyncio.create_task(_send_telegram_alert(from_number, duration, buy_signal, product, history))


async def _post_call_actions(call_sid: str, sms_now: bool = False) -> None:
    """Sofort-SMS wenn Kunde im Gespräch 'Ja' sagt."""
    conv = _conversations.get(call_sid, {})
    from_number = conv.get("from", "")
    product     = conv.get("product", "Smart Home Produkt")
    if sms_now and from_number:
        await _send_post_call_sms(from_number, product, True)


def _get_stripe_payment_link(product_name: str) -> str:
    """Gibt vorkonfigurierten Stripe Payment Link zurück (aus .env)."""
    # Mapping Produktname → STRIPE_LINK_* env var
    link_map = {
        "Solar":      "STRIPE_PAYMENT_LINK_AUTOMATON_SUITE",
        "Kamera":     "STRIPE_LINK_PRO",
        "Thermostat": "STRIPE_LINK_PRO",
        "Rasenmäher": "STRIPE_LINK_ENTERPRISE",
        "LED":        "STRIPE_LINK_STARTER",
        "Starter":    "STRIPE_LINK_STARTER",
    }
    for key_fragment, env_var in link_map.items():
        if key_fragment in product_name:
            link = os.getenv(env_var)
            if link:
                return link
    # Fallback: Starter-Link oder Shop-URL
    return os.getenv("STRIPE_LINK_STARTER") or f"{SHOP_URL}/collections/smart-home"


async def _send_post_call_sms(to_number: str, product: str, buy_signal: bool) -> None:
    """Sendet SMS mit Payment Link nach dem Anruf."""
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_PHONE:
        log.warning("Sofia SMS: Twilio nicht konfiguriert")
        return

    payment_url = _get_stripe_payment_link(product)
    sms_text = (
        f"Hallo! Hier ist Sofia von AIITEC 🏠\n"
        f"Ihr persönlicher Link für {product}:\n"
        f"{payment_url}\n"
        f"Fragen? Rufen Sie uns an: {TWILIO_PHONE}"
    )

    try:
        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(TWILIO_SID, TWILIO_TOKEN),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as s:
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                data={"From": TWILIO_PHONE, "To": to_number, "Body": sms_text},
            ) as r:
                data = await r.json()
                if r.status == 201:
                    log.info("Sofia SMS ✅ → %s: %s", to_number, payment_url)
                else:
                    log.warning("Sofia SMS failed %s: %s", r.status, data.get("message",""))
    except Exception as e:
        log.warning("Sofia SMS error: %s", e)


async def _send_telegram_alert(
    from_number: str, duration: int, buy_signal: bool, product: str, history: list
) -> None:
    """Sendet Telegram-Alert mit Gesprächszusammenfassung."""
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return

    icon = "🔥🔥🔥 KAUFSIGNAL!" if buy_signal else "📞 Anruf"
    summary_lines = []
    for msg in history[-6:]:
        role = "👤" if msg["role"] == "user" else "🤖 Sofia"
        summary_lines.append(f"{role}: {msg['content'][:80]}")

    text = (
        f"{icon}\n"
        f"Nummer: {from_number}\n"
        f"Dauer: {duration}s\n"
        f"Produkt: {product}\n"
        f"\nGespräch:\n" + "\n".join(summary_lines)
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4000]},
            )
        log.info("Sofia Telegram alert ✅ buy=%s", buy_signal)
    except Exception as e:
        log.warning("Sofia Telegram: %s", e)
