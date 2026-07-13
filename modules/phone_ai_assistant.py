#!/usr/bin/env python3
"""
KI-Telefonassistentin "Sofia" — Vollautomatische Sales-Demos per Telefon
=========================================================================
Vollautomatisch: kein Mensch nötig. Sofia führt das Gespräch, bucht Demos,
sendet Links per SMS, trackt alles in Supabase.

Flow Inbound (Kunde ruft an):
  Anruf → Twilio → /api/phone/incoming → TwiML → WebSocket /ws/phone
  → Whisper STT → Claude Haiku (Sales-Script) → OpenAI TTS → Twilio Audio

Flow Outbound (Sofia ruft Leads an):
  Lead aus mass_outreach DB → Twilio API: Anruf initiieren
  → gleicher Audio-Pipeline → Demo-Link per SMS bei Interesse

Stimme: OpenAI TTS "nova" (weiblich, natürlich klingendes Deutsch)
STT:    OpenAI Whisper (€0.006/min)
KI:     Claude Haiku (schnell, <500ms)
TTS:    OpenAI TTS nova (€0.015/1000 Zeichen)

Setup:
  1. Twilio-Nummer kaufen: python3 modules/phone_ai_assistant.py --buy-number +49
  2. Webhook setzen:       python3 modules/phone_ai_assistant.py --setup-webhook
  3. Test-Anruf:           python3 modules/phone_ai_assistant.py --test-call +49XXXXXXXXXX
  4. Outbound-Kampagne:    python3 modules/phone_ai_assistant.py --outbound 10

API-Routen (in dashboard/server.py registriert):
  POST /api/phone/incoming     — Twilio Webhook (eingehend)
  POST /api/phone/status       — Twilio Call-Status Updates
  GET  /api/phone/stats        — Statistiken
  WS   /ws/phone               — Twilio Media Stream WebSocket
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sqlite3
import struct
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import web

log = logging.getLogger("PhoneAI")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "phone_ai.db"

# ── Env ───────────────────────────────────────────────────────────────────────
def _e(k: str, d: str = "") -> str: return os.getenv(k, d)

TWILIO_SID      = lambda: _e("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN    = lambda: _e("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER   = lambda: _e("TWILIO_PHONE_NUMBER", "")
OPENAI_KEY      = lambda: _e("OPENAI_API_KEY")
ANTHROPIC_KEY   = lambda: _e("ANTHROPIC_API_KEY")
TG_TOKEN        = lambda: _e("TELEGRAM_BOT_TOKEN")
TG_CHAT         = lambda: _e("TELEGRAM_CHAT_ID")
PUBLIC_URL      = lambda: _e("RAILWAY_PUBLIC_DOMAIN",
                              "supermegabot-production.up.railway.app")
DEMO_URL        = "https://bullpower-hub.vercel.app"

# ── DB ────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS calls (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid     TEXT UNIQUE,
            direction    TEXT DEFAULT 'inbound',
            from_number  TEXT,
            to_number    TEXT,
            status       TEXT DEFAULT 'initiated',
            outcome      TEXT,
            duration_sec INTEGER DEFAULT 0,
            transcript   TEXT,
            interest     INTEGER DEFAULT 0,
            demo_sent    INTEGER DEFAULT 0,
            started_at   TEXT DEFAULT (datetime('now')),
            ended_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS outbound_queue (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phone        TEXT UNIQUE,
            company      TEXT,
            industry     TEXT DEFAULT 'Default',
            lead_email   TEXT,
            status       TEXT DEFAULT 'pending',
            attempts     INTEGER DEFAULT 0,
            scheduled_at TEXT DEFAULT (datetime('now')),
            called_at    TEXT
        );
        """)

# ── Audio: μ-law ↔ PCM (Twilio sendet 8kHz μ-law) ────────────────────────────
def _ulaw_to_pcm(ulaw_bytes: bytes) -> bytes:
    """Konvertiert μ-law 8kHz zu PCM 16-bit."""
    pcm = []
    for byte in ulaw_bytes:
        byte = ~byte & 0xFF
        sign = byte & 0x80
        exp  = (byte >> 4) & 0x07
        mant = byte & 0x0F
        sample = ((mant << 1) + 33) << exp
        if sign:
            sample = -sample
        pcm.append(max(-32768, min(32767, sample)))
    return struct.pack(f"<{len(pcm)}h", *pcm)

def _pcm_to_ulaw(pcm_bytes: bytes) -> bytes:
    """Konvertiert PCM 16-bit zu μ-law 8kHz für Twilio."""
    result = []
    samples = struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes)
    for sample in samples:
        if sample < 0:
            sample = -sample
            sign = 0x80
        else:
            sign = 0
        sample = min(sample + 33, 32767)
        exp = 7
        for i in range(7, -1, -1):
            if sample >= (1 << (i + 5)):
                exp = i
                break
        mant = (sample >> (exp + 1)) & 0x0F
        ulaw = ~(sign | (exp << 4) | mant) & 0xFF
        result.append(ulaw)
    return bytes(result)

def _build_wav(pcm_data: bytes, sample_rate: int = 8000) -> bytes:
    """PCM → WAV für Whisper."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()

# ── STT: OpenAI Whisper ───────────────────────────────────────────────────────
async def _transcribe(audio_wav: bytes) -> str:
    """Whisper transkribiert deutschen Anruf-Audio."""
    if not OPENAI_KEY():
        return ""
    try:
        data = aiohttp.FormData()
        data.add_field("file", audio_wav, filename="audio.wav",
                       content_type="audio/wav")
        data.add_field("model", "whisper-1")
        data.add_field("language", "de")
        data.add_field("prompt",
                       "Geschäftsgespräch auf Deutsch über KI-Automatisierung und Shopify.")
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_KEY()}"},
                data=data,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                if r.status == 200:
                    j = await r.json()
                    return j.get("text", "").strip()
    except Exception as e:
        log.warning("Whisper error: %s", e)
    return ""

# ── TTS: OpenAI nova (Deutsch) ────────────────────────────────────────────────
async def _synthesize(text: str) -> bytes:
    """OpenAI TTS 'nova' → μ-law Audio für Twilio."""
    if not OPENAI_KEY():
        return b""
    try:
        payload = {
            "model": "tts-1",
            "input": text[:4096],
            "voice": "nova",
            "response_format": "wav",
            "speed": 0.95,
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/audio/speech",
                json=payload,
                headers={"Authorization": f"Bearer {OPENAI_KEY()}"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning("TTS error: %s", e)
    return b""

# ── KI-Gehirn: Claude Haiku Sales-Agent ──────────────────────────────────────
SOFIA_SYSTEM = """Du bist Sofia, eine professionelle KI-Vertriebsassistentin von AiiteC.
Du führst telefonische Demo-Gespräche auf Deutsch.

Dein Ziel: Interesse wecken → Demo-Link per SMS senden → Termin vereinbaren.

Gesprächsstruktur:
1. Begrüßung + kurze Erklärung warum du anrufst
2. Eine offene Frage zum aktuellen Problem des Unternehmens
3. Kurze Lösung präsentieren (max 2 Sätze)
4. Demo-Link per SMS anbieten
5. Freundlich verabschieden

Regeln:
- Maximal 2-3 Sätze pro Antwort (Telefon = kurz!)
- Wenn der Angerufene kein Interesse hat: höflich bedanken und auflegen
- Wenn Interesse: Demo-Link erwähnen und SMS anbieten
- Nie aufdringlich, immer professionell
- Auf Einwände eingehen, nicht ignorieren

Branchen-spezifische Hooks:
- E-Commerce/Shopify: "Automatisierung von Produktlisten und Bestellungen"
- IT-Dienstleister: "KI-Agenten als White-Label für Ihre Kunden"
- Marketing-Agentur: "5x mehr Content in der Hälfte der Zeit"
- Steuerberater: "EU AI Act Compliance-Tool für Ihre Mandanten"
- Handwerk: "Automatische Neukundengewinnung in Ihrer Region"

Erkenne wenn jemand:
- INTERESSIERT ist → sage "Demo-Link"
- KEIN INTERESSE hat → sage "Auf Wiederhören"
- TERMIN will → sage "Kalender-Link"
"""

class SofiaConversation:
    """Zustandsbehaftete Telefon-Konversation mit Sofia."""

    def __init__(self, call_sid: str, from_number: str,
                 industry: str = "Default", company: str = ""):
        self.call_sid    = call_sid
        self.from_number = from_number
        self.industry    = industry
        self.company     = company
        self.history: List[Dict] = []
        self.interest    = False
        self.ended       = False
        self.transcript  = []

    def _greeting(self) -> str:
        hooks = {
            "E-Commerce":       "Shopify-Automatisierung",
            "IT-Dienstleister": "KI-Mitarbeiter für Ihre Kunden",
            "Marketing-Agentur":"KI-Content-Erstellung",
            "Steuerberater":    "EU AI Act Compliance",
            "Handwerk":         "automatische Neukundengewinnung",
            "Default":          "KI-Automatisierung",
        }
        topic = hooks.get(self.industry, hooks["Default"])
        name  = self.company or "Ihr Unternehmen"
        return (
            f"Guten Tag! Mein Name ist Sofia, ich rufe von AiiteC an. "
            f"Wir hatten Ihnen eine Email zur {topic} geschickt. "
            f"Haben Sie kurz zwei Minuten?"
        )

    async def respond(self, user_text: str) -> str:
        """Generiert nächste Antwort von Sofia via Claude Haiku."""
        self.transcript.append(f"Kunde: {user_text}")
        if not user_text.strip():
            return "Hallo? Können Sie mich hören?"

        self.history.append({"role": "user", "content": user_text})

        # Keyword-Erkennung
        low = user_text.lower()
        if any(w in low for w in ["kein interesse", "nein danke", "nicht interessiert",
                                   "kein bedarf", "aufhören", "bitte nicht mehr"]):
            self.ended = True
            return "Verstehe, danke für Ihre Zeit. Auf Wiederhören und einen schönen Tag!"

        if any(w in low for w in ["ja", "gerne", "interessant", "erzählen",
                                    "schicken", "sms", "demo", "link"]):
            self.interest = True

        try:
            async with aiohttp.ClientSession() as s:
                payload = {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "system": SOFIA_SYSTEM,
                    "messages": self.history[-8:],
                }
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers={"x-api-key": ANTHROPIC_KEY(),
                              "anthropic-version": "2023-06-01"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        reply = data["content"][0]["text"].strip()
                    else:
                        reply = "Könnten Sie das bitte wiederholen?"
        except Exception as e:
            log.warning("Claude error: %s", e)
            reply = "Einen Moment bitte, ich bin gleich wieder da."

        # Ende erkennen
        if any(w in reply.lower() for w in ["auf wiederhören", "wiedersehen",
                                              "schönen tag", "tschüss"]):
            self.ended = True

        if "demo-link" in reply.lower() or "sms" in reply.lower():
            self.interest = True

        self.history.append({"role": "assistant", "content": reply})
        self.transcript.append(f"Sofia: {reply}")
        return reply

# Aktive WebSocket-Verbindungen (call_sid → SofiaConversation)
_active_calls: Dict[str, SofiaConversation] = {}
_audio_buffers: Dict[str, bytearray] = {}

# ── WebSocket Handler (Twilio Media Streams) ──────────────────────────────────
async def handle_phone_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket /ws/phone — Twilio sendet Audio, Sofia antwortet."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    call_sid      = None
    stream_sid    = None
    conversation  = None
    audio_buf     = bytearray()
    last_speech   = time.time()
    silence_threshold = 1.5  # Sekunden Stille → verarbeiten

    log.info("Neue WebSocket-Verbindung von Twilio")

    async def _send_audio(text: str) -> None:
        """TTS → base64 μ-law → Twilio."""
        wav = await _synthesize(text)
        if not wav or not stream_sid:
            return
        # WAV → PCM extrahieren
        try:
            buf = io.BytesIO(wav)
            with wave.open(buf, "rb") as wf:
                pcm = wf.readframes(wf.getnframes())
        except Exception:
            pcm = wav[44:]  # WAV-Header überspringen
        ulaw = _pcm_to_ulaw(pcm)
        b64  = base64.b64encode(ulaw).decode()
        msg  = json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": b64}
        })
        await ws.send_str(msg)
        # Mark = Ende des Audio-Streams signalisieren
        await ws.send_str(json.dumps({
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": "response_end"}
        }))

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                event = data.get("event")

                if event == "connected":
                    log.info("Twilio Media Stream verbunden")

                elif event == "start":
                    call_sid   = data.get("start", {}).get("callSid", "")
                    stream_sid = data.get("start", {}).get("streamSid", "")
                    log.info("Anruf gestartet: %s", call_sid)
                    # Gespeicherte Konversation holen oder neue erstellen
                    conversation = _active_calls.get(call_sid)
                    if not conversation:
                        conversation = SofiaConversation(call_sid, "unknown")
                        _active_calls[call_sid] = conversation
                    greeting = conversation._greeting()
                    await asyncio.sleep(0.5)
                    await _send_audio(greeting)
                    conversation.history.append({
                        "role": "assistant", "content": greeting
                    })
                    conversation.transcript.append(f"Sofia: {greeting}")

                elif event == "media":
                    payload = data.get("media", {}).get("payload", "")
                    if payload:
                        ulaw = base64.b64decode(payload)
                        pcm  = _ulaw_to_pcm(ulaw)
                        audio_buf.extend(pcm)
                        last_speech = time.time()

                elif event == "mark":
                    pass  # Sofia hat fertig gesprochen

                elif event == "stop":
                    log.info("Anruf beendet: %s", call_sid)
                    break

            except Exception as e:
                log.error("WebSocket error: %s", e)

        elif msg.type == web.WSMsgType.ERROR:
            break

        # Stille erkennen → Transkribieren + Antworten
        if audio_buf and (time.time() - last_speech) > silence_threshold:
            chunk = bytes(audio_buf)
            audio_buf.clear()
            wav_data = _build_wav(chunk)

            if len(chunk) > 4000:  # min ~0.25 Sekunden Audio
                text = await _transcribe(wav_data)
                if text and conversation:
                    log.info("[%s] Kunde: %s", call_sid, text)
                    reply = await conversation.respond(text)
                    log.info("[%s] Sofia: %s", call_sid, reply)
                    await _send_audio(reply)

                    if conversation.ended:
                        await asyncio.sleep(2)
                        # Anruf beenden via Twilio API
                        asyncio.create_task(_end_call(call_sid))
                        break

                    if conversation.interest:
                        # SMS mit Demo-Link senden
                        asyncio.create_task(
                            _send_sms(conversation.from_number,
                                       f"Hallo! Hier ist Sofia von AiiteC. "
                                       f"Ihr persönlicher Demo-Zugang: {DEMO_URL}\n"
                                       f"14 Tage kostenlos testen!")
                        )
                        conversation.interest = False  # einmalig senden

    # Anruf-Daten speichern
    if call_sid and conversation:
        _save_call(call_sid, conversation)

    return ws

# ── Twilio API Helpers ────────────────────────────────────────────────────────
async def _twilio_api(method: str, path: str, data: Dict = None) -> Dict:
    sid   = TWILIO_SID()
    token = TWILIO_TOKEN()
    url   = f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}"
    auth  = aiohttp.BasicAuth(sid, token)
    async with aiohttp.ClientSession() as s:
        if method == "POST":
            async with s.post(url, data=data, auth=auth,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
        else:
            async with s.get(url, auth=auth,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()

async def _end_call(call_sid: str) -> None:
    await _twilio_api("POST", f"/Calls/{call_sid}.json", {"Status": "completed"})

async def _send_sms(to: str, body: str) -> None:
    if not TWILIO_NUMBER():
        return
    await _twilio_api("POST", "/Messages.json", {
        "From": TWILIO_NUMBER(),
        "To":   to,
        "Body": body,
    })

async def _make_outbound_call(to: str, industry: str = "Default",
                               company: str = "") -> str:
    """Initiiert ausgehenden Anruf — Sofia ruft Lead an."""
    from_num = TWILIO_NUMBER()
    if not from_num:
        raise ValueError("TWILIO_PHONE_NUMBER nicht gesetzt")
    webhook = f"https://{PUBLIC_URL()}/api/phone/incoming"
    result  = await _twilio_api("POST", "/Calls.json", {
        "From": from_num,
        "To":   to,
        "Url":  webhook,
        "StatusCallback": f"https://{PUBLIC_URL()}/api/phone/status",
        "StatusCallbackMethod": "POST",
        "MachineDetection": "Enable",
        "MachineDetectionTimeout": "5",
    })
    call_sid = result.get("sid", "")
    if call_sid:
        conv = SofiaConversation(call_sid, to, industry, company)
        _active_calls[call_sid] = conv
        with _db() as db:
            db.execute(
                "INSERT OR IGNORE INTO calls (call_sid, direction, from_number, to_number, status) "
                "VALUES (?,?,?,?,?)",
                (call_sid, "outbound", from_num, to, "initiated")
            )
    return call_sid

# ── DB Helpers ────────────────────────────────────────────────────────────────
def _save_call(call_sid: str, conv: SofiaConversation) -> None:
    transcript = "\n".join(conv.transcript)
    with _db() as db:
        db.execute("""
            INSERT OR REPLACE INTO calls
            (call_sid, direction, from_number, status, outcome, transcript, interest, ended_at)
            VALUES (?,?,?,?,?,?,?,datetime('now'))
        """, (
            call_sid, "inbound", conv.from_number,
            "completed",
            "interested" if conv.interest else "no_interest",
            transcript, int(conv.interest)
        ))
    _active_calls.pop(call_sid, None)

# ── TwiML Webhook Handler ─────────────────────────────────────────────────────
async def handle_phone_incoming(request: web.Request) -> web.Response:
    """POST /api/phone/incoming — Twilio ruft diesen Webhook bei eingehendem Anruf."""
    body = await request.post()
    call_sid    = body.get("CallSid", "")
    from_number = body.get("From", "")
    industry    = "Default"

    # Konversation vorbereiten
    conv = SofiaConversation(call_sid, from_number, industry)
    _active_calls[call_sid] = conv

    ws_url = f"wss://{PUBLIC_URL()}/ws/phone"
    twiml  = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}">
      <Parameter name="callSid" value="{call_sid}"/>
    </Stream>
  </Connect>
</Response>"""
    return web.Response(text=twiml, content_type="text/xml")

async def handle_phone_status(request: web.Request) -> web.Response:
    """POST /api/phone/status — Twilio Call-Status Updates."""
    body = await request.post()
    call_sid = body.get("CallSid", "")
    status   = body.get("CallStatus", "")
    duration = int(body.get("CallDuration", 0))
    with _db() as db:
        db.execute(
            "UPDATE calls SET status=?, duration_sec=?, ended_at=datetime('now') WHERE call_sid=?",
            (status, duration, call_sid)
        )
    if status == "completed":
        conv = _active_calls.pop(call_sid, None)
        if conv:
            _save_call(call_sid, conv)
        await _telegram_report(call_sid, duration)
    return web.Response(text="OK")

async def handle_phone_stats(request: web.Request) -> web.Response:
    """GET /api/phone/stats"""
    with _db() as db:
        total    = db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        today    = db.execute(
            "SELECT COUNT(*) FROM calls WHERE started_at > date('now')"
        ).fetchone()[0]
        interest = db.execute(
            "SELECT COUNT(*) FROM calls WHERE interest=1"
        ).fetchone()[0]
        demos    = db.execute(
            "SELECT COUNT(*) FROM calls WHERE demo_sent=1"
        ).fetchone()[0]
        recent   = db.execute(
            "SELECT call_sid, direction, from_number, status, outcome, duration_sec, started_at "
            "FROM calls ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
    return web.json_response({
        "total_calls": total, "calls_today": today,
        "interested": interest, "demos_sent": demos,
        "active_now": len(_active_calls),
        "recent": [dict(r) for r in recent],
        "twilio_number": TWILIO_NUMBER(),
    })

async def handle_outbound_trigger(request: web.Request) -> web.Response:
    """POST /api/phone/outbound — Outbound-Kampagne starten."""
    body = await request.json() if request.content_length else {}
    count = int(body.get("count", 5))
    results = await run_outbound_batch(count)
    return web.json_response(results)

# ── Telegram Report ───────────────────────────────────────────────────────────
async def _telegram_report(call_sid: str, duration: int) -> None:
    with _db() as db:
        row = db.execute(
            "SELECT * FROM calls WHERE call_sid=?", (call_sid,)
        ).fetchone()
    if not row:
        return
    icon = "🟢" if row["interest"] else "🔴"
    msg  = (
        f"{icon} <b>Anruf beendet</b>\n"
        f"Von: {row['from_number']}\n"
        f"Dauer: {duration}s\n"
        f"Ergebnis: <b>{row['outcome'] or 'unbekannt'}</b>\n"
        f"Demo-Link gesendet: {'✅' if row['demo_sent'] else '❌'}"
    )
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN()}/sendMessage",
                json={"chat_id": TG_CHAT(), "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8)
            )
    except Exception:
        pass

# ── Outbound-Kampagne ─────────────────────────────────────────────────────────
async def run_outbound_batch(count: int = 10) -> Dict:
    """Ruft N Leads aus der Queue automatisch an."""
    init_db()
    with _db() as db:
        leads = db.execute("""
            SELECT id, phone, company, industry FROM outbound_queue
            WHERE status='pending' AND attempts < 2
              AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))
            ORDER BY id ASC LIMIT ?
        """, (count,)).fetchall()

    called = 0
    errors = 0
    for lead in leads:
        try:
            call_sid = await _make_outbound_call(
                lead["phone"], lead["industry"], lead["company"]
            )
            with _db() as db:
                db.execute(
                    "UPDATE outbound_queue SET status='called', attempts=attempts+1, "
                    "called_at=datetime('now') WHERE id=?", (lead["id"],)
                )
            called += 1
            await asyncio.sleep(5)  # 5s zwischen Anrufen
        except Exception as e:
            errors += 1
            log.error("Outbound call error (%s): %s", lead["phone"], e)
            with _db() as db:
                db.execute(
                    "UPDATE outbound_queue SET attempts=attempts+1 WHERE id=?",
                    (lead["id"],)
                )
    return {"called": called, "errors": errors}

def add_to_outbound_queue(phone: str, company: str = "",
                           industry: str = "Default", email: str = "") -> bool:
    """Fügt Lead zur Outbound-Queue hinzu."""
    if not phone or len(phone) < 8:
        return False
    init_db()
    try:
        with _db() as db:
            db.execute(
                "INSERT OR IGNORE INTO outbound_queue (phone, company, industry, lead_email) "
                "VALUES (?,?,?,?)", (phone, company, industry, email)
            )
        return True
    except Exception:
        return False

# ── Twilio Setup ──────────────────────────────────────────────────────────────
async def buy_phone_number(country: str = "DE") -> str:
    """Kauft eine Twilio-Nummer (einmalig ~€1/Monat)."""
    sid   = TWILIO_SID()
    token = TWILIO_TOKEN()
    async with aiohttp.ClientSession() as s:
        # Verfügbare Nummern suchen
        async with s.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}"
            f"/AvailablePhoneNumbers/{country}/Local.json?VoiceEnabled=true&SmsEnabled=true",
            auth=aiohttp.BasicAuth(sid, token)
        ) as r:
            data = await r.json()
        numbers = data.get("available_phone_numbers", [])
        if not numbers:
            raise ValueError(f"Keine Nummern in {country} verfügbar")
        number = numbers[0]["phone_number"]
        webhook = f"https://{PUBLIC_URL()}/api/phone/incoming"
        async with s.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            data={
                "PhoneNumber": number,
                "VoiceUrl": webhook,
                "VoiceMethod": "POST",
                "SmsUrl": webhook,
                "StatusCallback": f"https://{PUBLIC_URL()}/api/phone/status",
            },
            auth=aiohttp.BasicAuth(sid, token)
        ) as r2:
            result = await r2.json()
    purchased = result.get("phone_number", number)
    log.info("Neue Twilio-Nummer: %s", purchased)
    return purchased

async def setup_webhook() -> None:
    """Setzt Webhook-URL auf bestehende Twilio-Nummer."""
    sid     = TWILIO_SID()
    token   = TWILIO_TOKEN()
    webhook = f"https://{PUBLIC_URL()}/api/phone/incoming"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            auth=aiohttp.BasicAuth(sid, token)
        ) as r:
            data = await r.json()
        numbers = data.get("incoming_phone_numbers", [])
        for num in numbers:
            num_sid = num["sid"]
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}"
                f"/IncomingPhoneNumbers/{num_sid}.json",
                data={"VoiceUrl": webhook, "VoiceMethod": "POST"},
                auth=aiohttp.BasicAuth(sid, token)
            ) as r2:
                log.info("Webhook gesetzt für %s: %s", num["phone_number"], webhook)

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _load_env():
        ef = _BASE / ".env"
        if ef.exists():
            for line in ef.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    _load_env()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [PhoneAI] %(message)s")
    args = sys.argv[1:]

    if "--init-db" in args:
        init_db(); print("DB OK")

    elif "--buy-number" in args:
        idx = args.index("--buy-number")
        country = args[idx+1] if idx+1 < len(args) else "DE"
        num = asyncio.run(buy_phone_number(country))
        print(f"Gekaufte Nummer: {num}")
        print(f"→ TWILIO_PHONE_NUMBER={num} in .env eintragen!")

    elif "--setup-webhook" in args:
        asyncio.run(setup_webhook())
        print("Webhook gesetzt.")

    elif "--test-call" in args:
        idx = args.index("--test-call")
        to = args[idx+1] if idx+1 < len(args) else ""
        if not to:
            print("Verwendung: --test-call +49XXXXXXXXXX")
        else:
            sid = asyncio.run(_make_outbound_call(to, "E-Commerce", "Testfirma"))
            print(f"Anruf initiiert: {sid}")

    elif "--outbound" in args:
        idx = args.index("--outbound")
        n = int(args[idx+1]) if idx+1 < len(args) and args[idx+1].isdigit() else 5
        result = asyncio.run(run_outbound_batch(n))
        print(f"Outbound: {result}")

    elif "--stats" in args:
        init_db()
        with _db() as db:
            total = db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            interest = db.execute("SELECT COUNT(*) FROM calls WHERE interest=1").fetchone()[0]
        print(f"Anrufe gesamt: {total} | Interessiert: {interest}")

    else:
        print(__doc__)
