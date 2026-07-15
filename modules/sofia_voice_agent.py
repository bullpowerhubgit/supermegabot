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
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

import aiohttp

log = logging.getLogger("Sofia")

TWILIO_SID           = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN         = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE         = os.getenv("TWILIO_PHONE_NUMBER", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
ANTHROPIC_KEY        = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT         = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_KEY           = os.getenv("STRIPE_SECRET_KEY", "")
SHOP_URL             = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
BASE_URL             = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"

# In-memory Gesprächsspeicher (Call-SID → Verlauf)
# Primär In-Memory für niedrige Latenz; SQLite als Persistenz-Backup bei Server-Restart.
_conversations: Dict[str, dict] = {}

# Deduplication: Nummern die bereits eine SMS/WhatsApp erhalten haben (In-Memory).
# Verhindert Doppel-SMS bei Twilio-Retries oder Mehrfach-Anrufen.
_sms_sent: set = set()

_CONV_DB = Path(__file__).parent.parent / "data" / "sofia_conversations.db"


def _conv_db_init() -> sqlite3.Connection:
    """Erstellt/öffnet die Konversations-Datenbank."""
    _CONV_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_CONV_DB), check_same_thread=False, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_calls (
            call_sid   TEXT PRIMARY KEY,
            data       TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _conv_save(call_sid: str) -> None:
    """Schreibt den aktuellen Gesprächszustand in SQLite (fire-and-forget)."""
    conv = _conversations.get(call_sid)
    if not conv:
        return
    try:
        conn = _conv_db_init()
        conn.execute(
            "INSERT OR REPLACE INTO active_calls (call_sid, data, updated_at) VALUES (?,?,?)",
            (call_sid, json.dumps(conv, ensure_ascii=False), time.time())
        )
        conn.commit()
        conn.close()
    except Exception as _e:
        log.debug("Conv-SQLite save: %s", _e)


def _conv_recover(call_sid: str) -> Optional[dict]:
    """Lädt Gespräch aus SQLite — Fallback nach Railway-Restart (max 1 Stunde alt)."""
    try:
        conn = _conv_db_init()
        row = conn.execute(
            "SELECT data, updated_at FROM active_calls WHERE call_sid=?", (call_sid,)
        ).fetchone()
        conn.close()
        if row and (time.time() - row[1]) < 3600:
            return json.loads(row[0])
    except Exception as _e:
        log.debug("Conv-SQLite recover: %s", _e)
    return None


def _conv_delete(call_sid: str) -> None:
    """Entfernt abgeschlossenen Anruf aus SQLite."""
    try:
        conn = _conv_db_init()
        conn.execute("DELETE FROM active_calls WHERE call_sid=?", (call_sid,))
        conn.commit()
        conn.close()
    except Exception as _e:
        log.debug("Conv-SQLite delete: %s", _e)

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


def _process_reply(conv: dict, reply: str) -> str:
    """Kaufsignal erkennen, Marker entfernen, History speichern."""
    if "[KAUFSIGNAL]" in reply or "[SMS_SENDEN]" in reply:
        conv["buy_signal"] = True
        # Spezifischere Fragmente zuerst — verhindert Fehlzuordnungen bei ähnlichen Namen
        for prod in [
            "Roboter-Rasenmäher", "Rasenmäher",
            "Balkonkraftwerk", "Solar",
            "Sicherheitskamera", "Kamera",
            "Thermostat",
            "Starter Set", "Starter",
            "LED System", "LED",
        ]:
            if prod.lower() in reply.lower():
                conv["product"] = prod
                break
    clean = re.sub(r'\[KAUFSIGNAL\]|\[SMS_SENDEN\]', '', reply).strip()
    conv["history"].append({"role": "assistant", "content": clean})
    return clean


async def _ai_response(call_sid: str, user_text: str) -> str:
    """Generiert Sofia-Antwort über zentralen ai_client (Ollama → Groq → Anthropic)."""
    # Nach Railway-Restart: Gespräch aus SQLite wiederherstellen
    if call_sid not in _conversations:
        recovered = _conv_recover(call_sid)
        if recovered:
            log.info("Sofia [%s] Gespräch aus SQLite wiederhergestellt nach Restart", call_sid)
            _conversations[call_sid] = recovered
    conv = _conversations.setdefault(call_sid, {"history": [], "buy_signal": False, "product": None})
    conv["history"].append({"role": "user", "content": user_text})

    # Kontext auf letzte 8 Turns begrenzen (Latenz für Voice!)
    history_text = "\n".join(
        f"{'Kunde' if m['role']=='user' else 'Sofia'}: {m['content']}"
        for m in conv["history"][-8:]
    )
    prompt = f"Gesprächsverlauf:\n{history_text}\n\nSofia antwortet jetzt (1-2 Sätze):"

    try:
        from modules.ai_client import ai_complete
        reply = await ai_complete(prompt, system=SOFIA_SYSTEM, model_hint="fast", max_tokens=120)
        if reply:
            result = _process_reply(conv, reply.strip())
            _conv_save(call_sid)
            return result
    except Exception as e:
        log.warning("Sofia ai_complete: %s", e)

    fallback = "Entschuldigung, einen Moment bitte. Könnten Sie das wiederholen?"
    conv["history"].append({"role": "assistant", "content": fallback})
    _conv_save(call_sid)
    return fallback


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
    _conv_save(call_sid)
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

    conv = _conversations.pop(call_sid, None)
    if conv is None:
        conv = _conv_recover(call_sid) or {}
    _conv_delete(call_sid)
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

    # Multi-Agenten-Cascade — IMMER für abgeschlossene Anrufe, auch < 30s.
    # Die Dauer-Logik liegt im Hub (sofia_agent_hub.py); kurze Anrufe (Aufhänger,
    # Falschanruf) werden dort minimal geloggt statt hier verloren zu gehen.
    if call_status == "completed":
        try:
            from modules.sofia_agent_hub import trigger_post_call_cascade
            transcript = "\n".join(
                f"{'Kunde' if m['role']=='user' else 'Sofia'}: {m['content']}"
                for m in history
            )
            asyncio.create_task(trigger_post_call_cascade(
                call_sid      = call_sid,
                duration      = duration,
                buying_signal = buy_signal,
                transcript    = transcript,
                from_number   = from_number,
                product_id    = product,
            ))
        except Exception as e:
            log.debug("Sofia Hub: %s", e)


async def _post_call_actions(call_sid: str, sms_now: bool = False) -> None:
    """Sofort-SMS wenn Kunde im Gespräch 'Ja' sagt."""
    conv = _conversations.get(call_sid, {})
    from_number = conv.get("from", "")
    product     = conv.get("product", "Smart Home Produkt")
    if sms_now and from_number:
        await _send_post_call_sms(from_number, product, True)


def _get_stripe_payment_link(product_name: str) -> str:
    """Gibt vorkonfigurierten Stripe Payment Link zurück (aus .env).
    Reihenfolge: spezifischere Fragmente zuerst — kein Fehlmatch bei Substring-Überschneidungen.
    """
    link_map = [
        ("Roboter-Rasenmäher", "STRIPE_LINK_ENTERPRISE"),
        ("Rasenmäher",         "STRIPE_LINK_ENTERPRISE"),
        ("Balkonkraftwerk",    "STRIPE_PAYMENT_LINK_AUTOMATON_SUITE"),
        ("Solar",              "STRIPE_PAYMENT_LINK_AUTOMATON_SUITE"),
        ("Sicherheitskamera",  "STRIPE_LINK_PRO"),
        ("Kamera",             "STRIPE_LINK_PRO"),
        ("Thermostat",         "STRIPE_LINK_PRO"),
        ("Starter Set",        "STRIPE_LINK_STARTER"),
        ("Starter",            "STRIPE_LINK_STARTER"),
        ("LED System",         "STRIPE_LINK_STARTER"),
        ("LED",                "STRIPE_LINK_STARTER"),
    ]
    name_lower = product_name.lower()
    for key_fragment, env_var in link_map:
        if key_fragment.lower() in name_lower:
            link = os.getenv(env_var)
            if link:
                return link
    # Fallback: Starter-Link oder Shop-URL
    return os.getenv("STRIPE_LINK_STARTER") or f"{SHOP_URL}/collections/smart-home"


async def _send_post_call_sms(to_number: str, product: str, buy_signal: bool) -> None:
    """Sendet WhatsApp (bevorzugt) oder SMS mit Payment Link nach dem Anruf.

    Schutz:
    - Deduplication via _sms_sent (in-memory): verhindert Doppel-Nachrichten bei
      Twilio-Retries oder Mehrfach-Anrufen derselben Nummer.
    - Placeholder-Produkt: Wenn kein echtes Produkt bekannt, generischer Katalog-Link
      ohne internen Fallback-String ("Smart Home Produkt") in der Kunden-Nachricht.
    - WhatsApp-first: Wenn TWILIO_WHATSAPP_FROM konfiguriert, wird WhatsApp versucht;
      bei Fehler automatischer Fallback auf klassische SMS.
    """
    if not TWILIO_SID or not TWILIO_TOKEN:
        log.warning("Sofia Nachricht: Twilio nicht konfiguriert")
        return

    # Issue 4: Deduplication — keine Doppel-Nachricht an dieselbe Nummer
    if to_number in _sms_sent:
        log.info("Sofia Dedup: Nachricht für %s bereits gesendet, überspringe", to_number)
        return

    payment_url = _get_stripe_payment_link(product)

    # Issue 3: Placeholder-Schutz — nie "Smart Home Produkt" dem Kunden zeigen
    _placeholder = "Smart Home Produkt"
    product_is_known = product and product != _placeholder
    if product_is_known:
        sms_text = (
            f"Hallo! Hier ist Sofia von AIITEC.\n"
            f"Ihr persönlicher Link für {product}:\n"
            f"{payment_url}\n"
            f"Fragen? Rufen Sie uns an: {TWILIO_PHONE}"
        )
    else:
        # Kein konkretes Produkt bekannt → generischer Katalog-Link
        catalog_url = f"{SHOP_URL}/collections/smart-home"
        sms_text = (
            f"Hallo! Hier ist Sofia von AIITEC.\n"
            f"Schauen Sie sich unser aktuelles Angebot an:\n"
            f"{catalog_url}\n"
            f"Fragen? Rufen Sie uns an: {TWILIO_PHONE}"
        )
        payment_url = catalog_url

    # Issue 2: WhatsApp zuerst, SMS als Fallback
    sent_via: Optional[str] = None
    if TWILIO_WHATSAPP_FROM:
        try:
            import base64
            wa_to = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
            auth_header = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                    data={"From": TWILIO_WHATSAPP_FROM, "To": wa_to, "Body": sms_text},
                    headers={"Authorization": f"Basic {auth_header}"},
                ) as r:
                    if r.status in (200, 201):
                        sent_via = "whatsapp"
                        log.info("Sofia WhatsApp ✅ → %s: %s", to_number, payment_url)
                    else:
                        data = await r.json()
                        log.warning("Sofia WhatsApp failed %s: %s — falle auf SMS zurück",
                                    r.status, data.get("message", ""))
        except Exception as e:
            log.warning("Sofia WhatsApp error: %s — falle auf SMS zurück", e)

    # SMS-Fallback wenn WhatsApp nicht konfiguriert oder fehlgeschlagen
    if sent_via is None:
        if not TWILIO_PHONE:
            log.warning("Sofia SMS: TWILIO_PHONE_NUMBER nicht konfiguriert")
            return
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
                        sent_via = "sms"
                        log.info("Sofia SMS ✅ → %s: %s", to_number, payment_url)
                    else:
                        log.warning("Sofia SMS failed %s: %s", r.status, data.get("message", ""))
        except Exception as e:
            log.warning("Sofia SMS error: %s", e)

    # Deduplication-Set aktualisieren wenn Nachricht erfolgreich versendet
    if sent_via:
        _sms_sent.add(to_number)


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
