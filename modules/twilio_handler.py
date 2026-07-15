"""Twilio Anruf-Handler für AIITEC — professionelle TTS-Begrüßung + Voicemail → Telegram"""
import asyncio
import logging
import os

import aiohttp

log = logging.getLogger("TwilioHandler")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL       = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")

# TwiML-Begrüßung
GREETING_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="de-DE" voice="Polly.Hans">
    Herzlich willkommen bei AIITEC! Sie haben Rudolf Sarkany erreicht.
    Wir helfen Unternehmen mit KI-gesteuerter Lead-Generierung und EU AI Act Compliance.
    Bitte hinterlassen Sie nach dem Signal Ihren Namen, Ihr Unternehmen und Ihr Anliegen.
    Wir melden uns innerhalb von 24 Stunden persönlich bei Ihnen.
  </Say>
  <Record
    maxLength="120"
    playBeep="true"
    recordingStatusCallback="{base_url}/webhook/twilio-recording"
    transcribeCallback="{base_url}/webhook/twilio-transcript"
    transcribe="true"
  />
  <Say language="de-DE" voice="Polly.Hans">
    Vielen Dank für Ihre Nachricht. Auf Wiedersehen!
  </Say>
</Response>"""

MISSED_CALL_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="de-DE" voice="Polly.Hans">
    Herzlich willkommen bei AIITEC!
    Wir sind gerade nicht erreichbar. Bitte hinterlassen Sie eine Nachricht nach dem Signal.
  </Say>
  <Record maxLength="120" playBeep="true"
    recordingStatusCallback="{base_url}/webhook/twilio-recording"
    transcribeCallback="{base_url}/webhook/twilio-transcript"
    transcribe="true"
  />
</Response>"""


def build_voice_twiml(missed: bool = False) -> str:
    template = MISSED_CALL_TWIML if missed else GREETING_TWIML
    return template.replace("{base_url}", BASE_URL)


async def notify_incoming_call(caller: str, call_sid: str):
    msg = (
        f"📞 <b>Eingehender Anruf!</b>\n"
        f"📱 Von: <code>{caller}</code>\n"
        f"🆔 SID: <code>{call_sid}</code>\n"
        f"⏰ Begrüßung läuft..."
    )
    await _telegram(msg)


async def notify_voicemail(caller: str, duration: str, recording_url: str, transcript: str = ""):
    msg = (
        f"🎙️ <b>Neue Voicemail!</b>\n"
        f"📱 Von: <code>{caller}</code>\n"
        f"⏱️ Länge: {duration}s\n"
    )
    if transcript:
        msg += f"📝 Transkript:\n<i>{transcript[:400]}</i>\n"
    if recording_url:
        msg += f"🔗 Aufnahme: {recording_url}"
    await _telegram(msg)


async def notify_transcript(caller: str, transcript: str, recording_sid: str):
    msg = (
        f"📝 <b>Voicemail-Transkript</b>\n"
        f"📱 Von: <code>{caller}</code>\n"
        f"💬 Text:\n<i>{transcript[:600]}</i>\n"
        f"🆔 Aufnahme: <code>{recording_sid}</code>"
    )
    await _telegram(msg)


async def _telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception as e:
        log.warning("Telegram Fehler: %s", e)
