#!/usr/bin/env python3
"""
KI-Telefon-Verkaufsassistent "Max" — Vollautomatisch via OpenAI Realtime API
=============================================================================
Architektur: Twilio Voice → WebSocket → OpenAI Realtime API → WebSocket → Twilio Voice

Max führt vollautomatische Verkaufsgespräche auf Deutsch.
Keine menschliche Beteiligung nötig — KI übernimmt komplett.

Flow Inbound (Kunde ruft an):
  Anruf → Twilio → POST /api/phone/incoming → TwiML → WS /ws/phone
  → PhoneAIBridge → OpenAI Realtime API (gpt-4o-realtime-preview) → Audio zurück

Flow Outbound (Max ruft Leads an):
  POST /api/phone/outbound → Twilio REST API → Anruf → gleicher Flow

API-Routen (in dashboard/server.py registriert):
  POST /api/phone/incoming     — Twilio Webhook (eingehend)
  POST /api/phone/status       — Twilio Call-Status Updates
  GET  /api/phone/stats        — Statistiken
  POST /api/phone/outbound     — Outbound-Anruf starten
  WS   /ws/phone               — Twilio Media Stream WebSocket

Setup:
  1. TWILIO_PHONE_NUMBER in .env setzen (Twilio-Nummer kaufen)
  2. Webhook auf /api/phone/incoming setzen
  3. Testen: python3 modules/phone_ai_assistant.py --test-call +49XXXXXXXXXX
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import sqlite3
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import web
import websockets
import websockets.exceptions

log = logging.getLogger("PhoneAI")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "phone_calls.db"

# ── Environment ───────────────────────────────────────────────────────────────
def _e(k: str, d: str = "") -> str:
    return os.getenv(k, d)

def TWILIO_SID()    -> str: return _e("TWILIO_ACCOUNT_SID")
def TWILIO_TOKEN()  -> str: return _e("TWILIO_AUTH_TOKEN")
def TWILIO_NUMBER() -> str: return _e("TWILIO_PHONE_NUMBER", "")
def OPENAI_KEY()    -> str: return _e("OPENAI_API_KEY")
def TG_TOKEN()      -> str: return _e("TELEGRAM_BOT_TOKEN")
def TG_CHAT()       -> str: return _e("TELEGRAM_CHAT_ID")
def PUBLIC_URL()    -> str:
    return _e("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")

# ── Active bridges (call_sid → PhoneAIBridge) ─────────────────────────────────
_active_bridges: Dict[str, "PhoneAIBridge"] = {}

# ── Product contexts ──────────────────────────────────────────────────────────
_SOFIA_BASE = (
    "Du bist Sofia, die KI-Verkaufsassistentin von AIITEC. "
    "Du sprichst natürlich, selbstbewusst und überzeugend auf Deutsch. "
    "Dein Ziel: Bedarf erkennen, passendes Produkt empfehlen, Abschluss erzielen.\n\n"
    "Gesprächsstruktur:\n"
    "1. Begrüße: 'AIITEC, guten Tag, hier ist Sofia. Was kann ich für Sie tun?'\n"
    "2. Stelle 1-2 gezielte Fragen zum konkreten Bedarf.\n"
    "3. Empfehle das passende Produkt mit Preis — selbstbewusst, ohne zu zögern.\n"
    "4. Behandle Einwände direkt:\n"
    "   - 'zu teuer' → Nutzen betonen, ROI erklären, kleineres Paket anbieten\n"
    "   - 'muss ich besprechen' → Entscheider einbeziehen, Termin vereinbaren\n"
    "   - 'kein Vertrauen' → Referenzen nennen, Demo anbieten, Geld-zurück-Garantie\n"
    "5. Abschluss: 'Soll ich Ihnen den Bestelllink direkt per SMS schicken?'\n"
    "6. Bei Ja: Bestätige dass der Link kommt und verabschiede dich freundlich.\n\n"
    "Regeln:\n"
    "- Maximal 3-4 Sätze pro Antwort (Telefon = kurz!)\n"
    "- Immer natürlich und menschlich klingen — kein Roboter-Tonfall\n"
    "- Preise selbstbewusst nennen — nicht zögern oder entschuldigen\n"
    "- Bei klarem Desinteresse: höflich verabschieden\n"
    "- Niemals lügen — Vertrauen ist wichtiger als der Abschluss\n"
    "- Kaufsignale aktiv erkennen: 'wie viel kostet', 'wie bestelle ich', 'klingt gut', "
    "'interessiert mich', 'schicken Sie mir' — dann sofort abschließen!\n"
)

PRODUCT_CONTEXTS: Dict[str, str] = {
    "general": (
        _SOFIA_BASE +
        "\nProdukt-Kontext: AIITEC KI-Automatisierungslösungen für Unternehmen.\n"
        "Produkte: SuperMegaBot Starter (€49/Mo), Pro (€99/Mo), Enterprise (€299/Mo).\n"
        "Wir helfen KMUs, mit KI Zeit zu sparen, Umsatz zu steigern und Prozesse zu automatisieren.\n"
        "USPs: Sofort einsatzbereit, keine technischen Kenntnisse nötig, "
        "messbare Ergebnisse in 30 Tagen, persönlicher Support, Geld-zurück-Garantie 14 Tage.\n"
        "Nächster Schritt: Bestelllink per SMS schicken oder Demo vereinbaren."
    ),
    "shopify": (
        _MAX_BASE +
        "\nProdukt-Kontext: BullPower Shopify Automatisierungs-SaaS\n"
        "Wir automatisieren den kompletten Shopify-Betrieb: Produktpflege, Bestellverarbeitung, "
        "Kundensegmentierung, Preisoptimierung und Marketing — alles KI-gesteuert.\n"
        "Preise: Starter €49/Monat (bis 500 Produkte), Pro €99/Monat (bis 5.000 Produkte), "
        "Enterprise €299/Monat (unbegrenzt + White-Label).\n"
        "Typische Kundenergebnisse: 60% weniger manueller Aufwand, +25% Conversion Rate, "
        "3x mehr Produkte im Sortiment ohne mehr Arbeit.\n"
        "USP: Als einzige Lösung verbindet BullPower KI-Produkterstellung, "
        "automatisches SEO und Preisoptimierung in einem System.\n"
        "Nächster Schritt: 14-Tage-Gratis-Test starten."
    ),
    "digistore": (
        _MAX_BASE +
        "\nProdukt-Kontext: BullPower DigiStore24 Optimierungs-Suite\n"
        "Wir maximieren die Einnahmen von DigiStore24-Vendoren und Affiliates durch "
        "KI-optimierte Produktbeschreibungen, automatische Affiliate-Akquise und "
        "datengesteuerte Umsatzprognosen.\n"
        "Typische Ergebnisse: +40% Conversion Rate, 3x mehr aktive Affiliates, "
        "automatisches Tracking und Optimierung in Echtzeit.\n"
        "Für wen: DigiStore24-Vendor mit mindestens einem digitalen Produkt, "
        "der mehr Umsatz will ohne mehr Arbeit.\n"
        "Nächster Schritt: Kostenlose Analyse des bestehenden DigiStore24-Accounts."
    ),
    "ai_tools": (
        _MAX_BASE +
        "\nProdukt-Kontext: BullPower KI-API-Zugang\n"
        "Wir bieten KI-API-Zugänge zu Claude, GPT-4o und Gemini — gebündelt, "
        "abgerechnet und mit eigenem Billing-System für Weiterverkauf.\n"
        "Perfekt für: Agenturen, SaaS-Entwickler und Tech-Unternehmen die KI-Features "
        "einbauen wollen ohne selbst bei Anthropic/OpenAI zu integrieren.\n"
        "Preisstufen: Micro (€29/Mo, 100k Tokens), Standard (€99/Mo, 1M Tokens), "
        "Pro (€299/Mo, 10M Tokens) — alles ohne Einzelabrechnung.\n"
        "USP: Einheitliche API, ein Vertrag, eine Rechnung — egal ob Claude oder GPT-4o.\n"
        "Nächster Schritt: API-Key für 7 Tage kostenlos testen."
    ),
    "telegram": (
        _MAX_BASE +
        "\nProdukt-Kontext: BullPower Telegram Subscription-Bot\n"
        "Wir bauen und betreiben Telegram-Bots mit Abo-Modell für Influencer, "
        "Communities und Content-Creator — komplett automatisiert.\n"
        "Der Bot übernimmt: Zahlungsabwicklung (Stripe/PayPal), Mitglieder-Management, "
        "Premium-Content-Verteilung, automatische Kündigung und Mahnungen.\n"
        "Typische Creator verdienen: €500-5.000/Monat passiv mit 100-1.000 Abonnenten.\n"
        "Preise: Setup ab €299 einmalig, dann 5% Revenue-Share (kein Monatsabo).\n"
        "USP: Einzige Lösung mit vollautomatischer Aboverwaltung und "
        "eingebautem Anti-Churn-System.\n"
        "Nächster Schritt: Kostenlosen Setup-Call vereinbaren."
    ),
}

# ── Database ──────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Erstellt phone_calls.db mit calls- und appointments-Tabellen."""
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS calls (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid     TEXT UNIQUE,
            direction    TEXT DEFAULT 'inbound',
            to_number    TEXT DEFAULT '',
            from_number  TEXT DEFAULT '',
            product_id   TEXT DEFAULT 'general',
            status       TEXT DEFAULT 'initiated',
            started_at   TEXT DEFAULT (datetime('now')),
            ended_at     TEXT,
            duration_sec INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid      TEXT,
            contact_name  TEXT DEFAULT '',
            contact_email TEXT DEFAULT '',
            contact_phone TEXT DEFAULT '',
            product_id    TEXT DEFAULT 'general',
            scheduled_at  TEXT,
            notes         TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_calls_sid  ON calls (call_sid);
        CREATE INDEX IF NOT EXISTS idx_calls_date ON calls (started_at);
        CREATE INDEX IF NOT EXISTS idx_appt_sid   ON appointments (call_sid);
        """)
    log.info("phone_calls.db initialisiert: %s", _DB)


# ── Audio conversion helpers ──────────────────────────────────────────────────
def _build_mulaw_decode_table() -> List[int]:
    """Erstellt die 256-Eintrags-Lookup-Tabelle für μ-law → PCM16 Dekodierung."""
    table: List[int] = []
    for i in range(256):
        u = ~i & 0xFF           # Bits invertieren (G.711 μ-law ist bit-invertiert gespeichert)
        sign = u >> 7           # Bit 7: Vorzeichen (1 = negativ)
        exp  = (u >> 4) & 0x07  # Bits 6-4: Exponent
        mant = u & 0x0F         # Bits 3-0: Mantisse
        # Magnitude berechnen, auf 16-Bit skalieren (<<exp+2 statt <<exp)
        mag = ((mant << 1) + 33) << (exp + 2)
        sample = -mag if sign else mag
        # Auf 16-Bit-Bereich begrenzen
        table.append(max(-32768, min(32767, sample)))
    return table


_MULAW_DECODE_TABLE: List[int] = _build_mulaw_decode_table()


def _mulaw_to_pcm24k(data: bytes) -> bytes:
    """Konvertiert μ-law 8kHz-Bytes zu PCM 16-Bit 24kHz (für OpenAI Realtime API).

    Schritt 1: μ-law → PCM 16-Bit bei 8kHz (Lookup-Tabelle)
    Schritt 2: Lineares Upsampling 8kHz → 24kHz (Faktor 3, Interpolation)
    """
    if not data:
        return b""

    # Schritt 1: μ-law → PCM 8kHz
    pcm8: List[int] = [_MULAW_DECODE_TABLE[b] for b in data]
    n = len(pcm8)

    # Schritt 2: Lineare Interpolation 8kHz → 24kHz (3 Ausgabesamples pro Eingang)
    pcm24: List[int] = []
    for i in range(n):
        s0 = pcm8[i]
        s1 = pcm8[i + 1] if i + 1 < n else s0
        d  = s1 - s0
        pcm24.append(max(-32768, min(32767, s0)))
        pcm24.append(max(-32768, min(32767, s0 + d // 3)))
        pcm24.append(max(-32768, min(32767, s0 + (d * 2) // 3)))

    return struct.pack(f"<{len(pcm24)}h", *pcm24)


def _encode_mulaw_sample(sample: int) -> int:
    """Kodiert einen einzelnen PCM 16-Bit Sample zu einem μ-law Byte."""
    if sample < 0:
        sample = -sample
        sign = 0x80
    else:
        sign = 0
    sample = min(sample + 33, 32767)  # Bias addieren
    # Exponent bestimmen (höchstes gesetztes Bit im Bereich bit5..bit12)
    exp = 7
    for i in range(7, -1, -1):
        if sample >= (1 << (i + 5)):
            exp = i
            break
    mant = (sample >> (exp + 1)) & 0x0F
    return ~(sign | (exp << 4) | mant) & 0xFF


def _pcm24k_to_mulaw(data: bytes) -> bytes:
    """Konvertiert PCM 16-Bit 24kHz (von OpenAI) zu μ-law 8kHz (für Twilio).

    Schritt 1: Dezimierung 24kHz → 8kHz (jeden 3. Sample behalten)
    Schritt 2: PCM 16-Bit → μ-law kodieren
    """
    if not data:
        return b""
    n = len(data) // 2
    if n == 0:
        return b""
    samples = struct.unpack(f"<{n}h", data[: n * 2])
    # Dezimierung: jeden 3. Sample nehmen
    decimated = samples[::3]
    return bytes(_encode_mulaw_sample(s) for s in decimated)


# ── TwiML Generator ───────────────────────────────────────────────────────────
def generate_inbound_twiml(call_sid: str, product_id: str = "general") -> str:
    """Erzeugt TwiML-String für eingehenden Anruf.

    Verbindet Twilio Media Streams mit unserem WebSocket-Bridge-Endpoint.
    Max begrüßt den Anrufer nach WebSocket-Verbindungsaufbau.
    """
    domain = PUBLIC_URL()
    ws_url = f"wss://{domain}/ws/phone?call_sid={call_sid}&product={product_id}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "  <Connect>\n"
        f'    <Stream url="{ws_url}">\n'
        f'      <Parameter name="callSid"   value="{call_sid}"/>\n'
        f'      <Parameter name="productId" value="{product_id}"/>\n'
        "    </Stream>\n"
        "  </Connect>\n"
        "</Response>"
    )


# ── WebSocket Bridge: Twilio ↔ OpenAI Realtime API ───────────────────────────
_OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"


class PhoneAIBridge:
    """Bridges Twilio Media Streams WebSocket ↔ OpenAI Realtime API.

    Twilio sendet μ-law 8kHz Audio, OpenAI erwartet PCM 16-Bit 24kHz.
    OpenAI antwortet mit PCM 16-Bit 24kHz, Twilio erwartet μ-law 8kHz.
    """

    def __init__(
        self,
        call_sid: str,
        product_id: str,
        ws_client: web.WebSocketResponse,
    ) -> None:
        self.call_sid   = call_sid
        self.product_id = product_id
        self.ws_twilio  = ws_client  # aiohttp WebSocketResponse (Server-Seite)
        self.stream_sid = ""
        self._started   = datetime.now(timezone.utc)
        self._done      = asyncio.Event()

    # ── Session-Konfiguration für OpenAI ──────────────────────────────────────
    def _build_session_config(self) -> Dict[str, Any]:
        prompt = PRODUCT_CONTEXTS.get(self.product_id, PRODUCT_CONTEXTS["general"])
        return {
            "type": "session.update",
            "session": {
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600,
                },
                "input_audio_format":  "pcm16",
                "output_audio_format": "pcm16",
                "voice": "alloy",
                "instructions": prompt,
                "modalities": ["text", "audio"],
                "temperature": 0.8,
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
            },
        }

    # ── Main Run Loop ──────────────────────────────────────────────────────────
    async def run(self) -> None:
        """Verbindet Twilio ↔ OpenAI Realtime und bridged Audio bidirektional."""
        if not OPENAI_KEY():
            log.error("[%s] OPENAI_API_KEY fehlt — Bridge abgebrochen", self.call_sid)
            return

        headers = {
            "Authorization": f"Bearer {OPENAI_KEY()}",
            "OpenAI-Beta":   "realtime=v1",
        }
        try:
            async with websockets.connect(
                _OPENAI_REALTIME_URL,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=10,
                max_size=10 * 1024 * 1024,  # 10 MB
            ) as openai_ws:
                log.info("[%s] OpenAI Realtime verbunden", self.call_sid)

                # Session konfigurieren
                await openai_ws.send(json.dumps(self._build_session_config()))

                # Bidirektionale Bridge starten
                t1 = asyncio.create_task(
                    self._twilio_to_openai(openai_ws), name=f"t2o-{self.call_sid}"
                )
                t2 = asyncio.create_task(
                    self._openai_to_twilio(openai_ws), name=f"o2t-{self.call_sid}"
                )

                done, pending = await asyncio.wait(
                    [t1, t2], return_when=asyncio.FIRST_COMPLETED
                )

                # Verbleibende Tasks abbrechen
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

                # Exceptions aus fertigen Tasks loggen
                for task in done:
                    if not task.cancelled() and task.exception():
                        log.warning(
                            "[%s] Bridge-Task-Fehler: %s",
                            self.call_sid, task.exception()
                        )

        except websockets.exceptions.InvalidURI as e:
            log.error("[%s] Ungültige WebSocket-URI: %s", self.call_sid, e)
        except websockets.exceptions.ConnectionClosedError as e:
            log.warning("[%s] OpenAI WS geschlossen: %s", self.call_sid, e)
        except OSError as e:
            log.error("[%s] Netzwerkfehler zu OpenAI: %s", self.call_sid, e)
        except Exception as e:
            log.error("[%s] Bridge-Fehler: %s", self.call_sid, e)
        finally:
            self._done.set()
            log.info("[%s] Bridge beendet", self.call_sid)

    # ── Twilio → OpenAI (Audio weitersenden) ──────────────────────────────────
    async def _twilio_to_openai(self, openai_ws: Any) -> None:
        """Liest Audio von Twilio (μ-law 8kHz), konvertiert und sendet an OpenAI."""
        greeting_sent = False
        try:
            async for msg in self.ws_twilio:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data  = json.loads(msg.data)
                        event = data.get("event", "")

                        if event == "connected":
                            log.info("[%s] Twilio Media Stream verbunden", self.call_sid)

                        elif event == "start":
                            start_data     = data.get("start", {})
                            self.stream_sid = start_data.get("streamSid", "")
                            # CallSid aus Twilio-Event extrahieren (falls nicht in URL)
                            if not self.call_sid or self.call_sid.startswith("ws_"):
                                self.call_sid = start_data.get("callSid", self.call_sid)
                            log.info(
                                "[%s] Stream gestartet (streamSid=%s)",
                                self.call_sid, self.stream_sid
                            )

                            # Begrüßung triggern (einmalig)
                            if not greeting_sent:
                                greeting_sent = True
                                await asyncio.sleep(0.3)  # kurze Pause für Verbindungsaufbau
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{
                                            "type": "input_text",
                                            "text": "Bitte beginne das Gespräch jetzt mit deiner Begrüßung auf Deutsch."
                                        }]
                                    }
                                }))
                                await openai_ws.send(json.dumps({"type": "response.create"}))

                        elif event == "media":
                            payload = data.get("media", {}).get("payload", "")
                            if payload:
                                mulaw = base64.b64decode(payload)
                                pcm   = _mulaw_to_pcm24k(mulaw)
                                await openai_ws.send(json.dumps({
                                    "type":  "input_audio_buffer.append",
                                    "audio": base64.b64encode(pcm).decode(),
                                }))

                        elif event == "stop":
                            log.info("[%s] Twilio Stream gestoppt", self.call_sid)
                            break

                    except json.JSONDecodeError:
                        log.debug("[%s] Kein JSON: %s", self.call_sid, msg.data[:80])
                    except Exception as e:
                        log.warning("[%s] Twilio→OpenAI Fehler: %s", self.call_sid, e)

                elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                    break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("[%s] _twilio_to_openai Ausnahme: %s", self.call_sid, e)
        finally:
            # Signalisiere OpenAI-Seite ebenfalls zu beenden
            self._done.set()

    # ── OpenAI → Twilio (Audio zurücksenden) ──────────────────────────────────
    async def _openai_to_twilio(self, openai_ws: Any) -> None:
        """Empfängt Audio von OpenAI Realtime, konvertiert und sendet an Twilio."""
        try:
            async for raw_msg in openai_ws:
                if self._done.is_set():
                    break
                try:
                    data       = json.loads(raw_msg if isinstance(raw_msg, str) else raw_msg.decode())
                    event_type = data.get("type", "")

                    if event_type == "response.audio.delta":
                        # PCM 24kHz → μ-law 8kHz → Twilio
                        delta = data.get("delta", "")
                        if delta and self.stream_sid:
                            pcm   = base64.b64decode(delta)
                            mulaw = _pcm24k_to_mulaw(pcm)
                            b64   = base64.b64encode(mulaw).decode()
                            await self.ws_twilio.send_str(json.dumps({
                                "event":     "media",
                                "streamSid": self.stream_sid,
                                "media":     {"payload": b64},
                            }))

                    elif event_type == "response.audio.done":
                        # Ende-Markierung an Twilio senden
                        if self.stream_sid and not self.ws_twilio.closed:
                            with contextlib.suppress(Exception):
                                await self.ws_twilio.send_str(json.dumps({
                                    "event":     "mark",
                                    "streamSid": self.stream_sid,
                                    "mark":      {"name": "response_end"},
                                }))

                    elif event_type == "session.updated":
                        log.debug("[%s] OpenAI Session aktualisiert", self.call_sid)

                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = data.get("transcript", "")
                        if transcript:
                            log.info("[%s] Kunde: %s", self.call_sid, transcript)

                    elif event_type == "response.text.done":
                        text = data.get("text", "")
                        if text:
                            log.info("[%s] Max: %s", self.call_sid, text[:120])

                    elif event_type == "error":
                        err = data.get("error", {})
                        log.error(
                            "[%s] OpenAI Fehler: %s — %s",
                            self.call_sid, err.get("code"), err.get("message")
                        )

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    log.warning("[%s] OpenAI→Twilio Fehler: %s", self.call_sid, e)

        except websockets.exceptions.ConnectionClosed:
            log.info("[%s] OpenAI WS geschlossen", self.call_sid)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("[%s] _openai_to_twilio Ausnahme: %s", self.call_sid, e)


# ── Outbound Call ─────────────────────────────────────────────────────────────
async def trigger_outbound_call(
    to_number: str,
    product_id: str = "general",
    contact_name: str = "",
) -> str:
    """Initiiert einen ausgehenden Twilio-Anruf.

    Returns:
        call_sid wenn erfolgreich, '' bei Fehler.
    """
    from_num = TWILIO_NUMBER()
    if not from_num:
        log.error("TWILIO_PHONE_NUMBER nicht gesetzt — Outbound-Anruf abgebrochen")
        return ""
    if not TWILIO_SID() or not TWILIO_TOKEN():
        log.error("Twilio-Credentials fehlen")
        return ""

    webhook_url = f"https://{PUBLIC_URL()}/api/phone/incoming?product={product_id}"
    status_url  = f"https://{PUBLIC_URL()}/api/phone/status"

    payload = {
        "From":                  from_num,
        "To":                    to_number,
        "Url":                   webhook_url,
        "StatusCallback":        status_url,
        "StatusCallbackMethod":  "POST",
        "MachineDetection":      "Enable",
        "MachineDetectionTimeout": "5",
    }
    try:
        result = await _twilio_api("POST", "/Calls.json", payload)
        call_sid = result.get("sid", "")
        if call_sid:
            # In DB erfassen
            _record_call(
                call_sid=call_sid,
                direction="outbound",
                from_number=from_num,
                to_number=to_number,
                product_id=product_id,
                status="initiated",
            )
            log.info(
                "Outbound-Anruf initiiert: %s → %s (product=%s)",
                call_sid, to_number, product_id
            )
        return call_sid
    except Exception as e:
        log.error("Outbound-Anruf fehlgeschlagen (%s): %s", to_number, e)
        return ""


# ── Status & Stats ────────────────────────────────────────────────────────────
def get_status() -> Dict[str, Any]:
    """Gibt aktuellen System-Status zurück.

    Returns:
        Dict mit active_calls, calls_today, appointments_booked, avg_duration_sec
    """
    try:
        with _db() as conn:
            active_calls = len(_active_bridges)
            calls_today  = conn.execute(
                "SELECT COUNT(*) FROM calls WHERE started_at >= date('now')"
            ).fetchone()[0]
            appointments = conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE created_at >= date('now', '-30 days')"
            ).fetchone()[0]
            avg_row = conn.execute(
                "SELECT AVG(duration_sec) FROM calls WHERE duration_sec > 0"
            ).fetchone()
            avg_dur = round(float(avg_row[0] or 0), 1)

        return {
            "active_calls":       active_calls,
            "calls_today":        calls_today,
            "appointments_booked": appointments,
            "avg_duration_sec":   avg_dur,
        }
    except Exception as e:
        log.warning("get_status Fehler: %s", e)
        return {
            "active_calls":       len(_active_bridges),
            "calls_today":        0,
            "appointments_booked": 0,
            "avg_duration_sec":   0.0,
        }


# ── aiohttp Route Handlers ────────────────────────────────────────────────────
async def handle_phone_incoming(request: web.Request) -> web.Response:
    """POST /api/phone/incoming — Twilio Webhook bei eingehendem Anruf.

    Gibt TwiML zurück, das Twilio anweist einen Media Stream WebSocket zu öffnen.
    """
    try:
        body = await request.post()
    except Exception:
        body = {}  # type: ignore[assignment]

    call_sid    = body.get("CallSid", f"sid_{int(time.time())}")
    from_number = body.get("From",    "")
    to_number   = body.get("To",      "")

    # product_id aus Query-Parameter (kann beim Outbound-Anruf gesetzt sein)
    product_id = request.rel_url.query.get("product", "general")
    if product_id not in PRODUCT_CONTEXTS:
        product_id = "general"

    # Anruf in DB erfassen
    _record_call(
        call_sid=call_sid,
        direction="inbound",
        from_number=from_number,
        to_number=to_number,
        product_id=product_id,
        status="ringing",
    )

    twiml = generate_inbound_twiml(call_sid, product_id)
    log.info(
        "Eingehender Anruf: %s von %s (product=%s)", call_sid, from_number, product_id
    )
    return web.Response(text=twiml, content_type="text/xml")


async def handle_phone_status(request: web.Request) -> web.Response:
    """POST /api/phone/status — Twilio Call-Status-Callback."""
    try:
        body = await request.post()
    except Exception:
        body = {}  # type: ignore[assignment]

    call_sid = body.get("CallSid",      "")
    status   = body.get("CallStatus",   "")
    duration = int(body.get("CallDuration", 0) or 0)

    if call_sid:
        try:
            with _db() as conn:
                conn.execute(
                    "UPDATE calls SET status=?, duration_sec=?, ended_at=datetime('now') "
                    "WHERE call_sid=?",
                    (status, duration, call_sid),
                )
        except Exception as e:
            log.warning("Status-Update Fehler: %s", e)

        if status == "completed":
            _active_bridges.pop(call_sid, None)
            asyncio.create_task(_notify_telegram(call_sid, duration, status))
            if duration >= 30:
                asyncio.create_task(_send_sms_payment_link(call_sid, duration))
            log.info("Anruf beendet: %s (Dauer: %ds)", call_sid, duration)

    return web.Response(text="OK")


async def handle_phone_stats(request: web.Request) -> web.Response:
    """GET /api/phone/stats — Statistiken und aktive Anrufe."""
    try:
        with _db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM calls WHERE started_at >= date('now')"
            ).fetchone()[0]
            appts = conn.execute(
                "SELECT COUNT(*) FROM appointments"
            ).fetchone()[0]
            avg_row = conn.execute(
                "SELECT AVG(duration_sec) FROM calls WHERE duration_sec > 0"
            ).fetchone()
            avg_dur = round(float(avg_row[0] or 0), 1)
            recent = conn.execute(
                "SELECT call_sid, direction, from_number, to_number, product_id, "
                "status, duration_sec, started_at "
                "FROM calls ORDER BY started_at DESC LIMIT 10"
            ).fetchall()

        return web.json_response({
            "ok":              True,
            "total_calls":     total,
            "calls_today":     today,
            "appointments":    appts,
            "avg_duration_sec": avg_dur,
            "active_now":      len(_active_bridges),
            "active_call_sids": list(_active_bridges.keys()),
            "twilio_number":   TWILIO_NUMBER() or "nicht konfiguriert",
            "recent":          [dict(r) for r in recent],
        })
    except Exception as e:
        log.error("handle_phone_stats Fehler: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_outbound_trigger(request: web.Request) -> web.Response:
    """POST /api/phone/outbound — Outbound-Anruf auslösen.

    Body (JSON):
        to_number:    Zielrufnummer (E.164)
        product_id:   Produktkontext (optional)
        contact_name: Name des Kontakts (optional)
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    to_number    = body.get("to_number", body.get("phone", ""))
    product_id   = body.get("product_id", body.get("product", "general"))
    contact_name = body.get("contact_name", body.get("name", ""))

    if not to_number:
        return web.json_response(
            {"ok": False, "error": "to_number fehlt"}, status=400
        )
    if product_id not in PRODUCT_CONTEXTS:
        product_id = "general"

    call_sid = await trigger_outbound_call(to_number, product_id, contact_name)
    if call_sid:
        return web.json_response({"ok": True, "call_sid": call_sid, "to": to_number})
    return web.json_response(
        {"ok": False, "error": "Anruf konnte nicht initiiert werden"}, status=500
    )


async def handle_phone_ws(request: web.Request) -> web.WebSocketResponse:
    """GET /ws/phone — Twilio Media Stream WebSocket Handler.

    Twilio verbindet sich hier nach TwiML-Anweisung.
    PhoneAIBridge übernimmt die bidirektionale Audio-Bridge zu OpenAI.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # call_sid aus Query-Parameter oder wird aus Twilio "start"-Event befüllt
    query      = request.rel_url.query
    call_sid   = query.get("call_sid", f"ws_{int(time.time())}")
    product_id = query.get("product", "general")
    if product_id not in PRODUCT_CONTEXTS:
        product_id = "general"

    log.info("WS-Verbindung: call_sid=%s product=%s", call_sid, product_id)

    bridge = PhoneAIBridge(call_sid, product_id, ws)
    _active_bridges[call_sid] = bridge

    try:
        await bridge.run()
    except Exception as e:
        log.error("WS-Handler Fehler [%s]: %s", call_sid, e)
    finally:
        # Aufräumen: Bridge entfernen
        _active_bridges.pop(call_sid, None)
        # Falls Bridge call_sid aktualisiert hat (aus Twilio "start" event)
        _active_bridges.pop(bridge.call_sid, None)

    return ws


# ── Twilio REST API Helper ────────────────────────────────────────────────────
async def _twilio_api(method: str, path: str, data: Optional[Dict] = None) -> Dict:
    """Sendet einen Request an die Twilio REST API."""
    sid   = TWILIO_SID()
    token = TWILIO_TOKEN()
    if not sid or not token:
        raise ValueError("Twilio-Credentials (SID/TOKEN) nicht konfiguriert")
    url  = f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}"
    auth = aiohttp.BasicAuth(sid, token)
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            async with session.post(
                url, data=data, auth=auth,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                return await resp.json()
        else:
            async with session.get(
                url, auth=auth,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                return await resp.json()


# ── DB Helpers ────────────────────────────────────────────────────────────────
def _record_call(
    call_sid: str,
    direction: str = "inbound",
    from_number: str = "",
    to_number: str = "",
    product_id: str = "general",
    status: str = "initiated",
) -> None:
    """Speichert oder aktualisiert einen Anruf in der DB."""
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO calls "
                "(call_sid, direction, from_number, to_number, product_id, status) "
                "VALUES (?,?,?,?,?,?)",
                (call_sid, direction, from_number, to_number, product_id, status),
            )
    except Exception as e:
        log.warning("_record_call Fehler: %s", e)


def record_appointment(
    call_sid: str,
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    product_id: str = "general",
    scheduled_at: str = "",
    notes: str = "",
) -> int:
    """Speichert einen gebuchten Termin in der DB. Gibt die Zeilen-ID zurück."""
    try:
        with _db() as conn:
            cursor = conn.execute(
                "INSERT INTO appointments "
                "(call_sid, contact_name, contact_email, contact_phone, "
                "product_id, scheduled_at, notes) VALUES (?,?,?,?,?,?,?)",
                (call_sid, contact_name, contact_email, contact_phone,
                 product_id, scheduled_at, notes),
            )
            return cursor.lastrowid or 0
    except Exception as e:
        log.warning("record_appointment Fehler: %s", e)
        return 0


# ── Telegram-Benachrichtigung ─────────────────────────────────────────────────
_KAUFSIGNAL_KEYWORDS = (
    "wie viel kostet", "wie bestelle", "klingt gut", "interessiert mich",
    "schicken sie", "ja gerne", "machen wir", "einverstanden", "nehme ich",
    "bestellen", "kaufen", "link schicken", "sms schicken", "payment",
)


async def _send_sms_payment_link(call_sid: str, duration: int) -> None:
    """Schickt nach jedem Anruf >30s einen Stripe-Paymentlink per SMS."""
    sid   = TWILIO_SID()
    token = TWILIO_TOKEN()
    if not sid or not token:
        return
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT from_number, product_id FROM calls WHERE call_sid=?", (call_sid,)
            ).fetchone()
        if not row:
            return
        to_number  = row["from_number"]
        product_id = row["product_id"] or "general"

        # Passenden Stripe-Link aus DB holen (oder Fallback)
        try:
            import sqlite3 as _sqlite3
            link_db = _BASE / "data" / "payment_links.db"
            if link_db.exists():
                with _sqlite3.connect(str(link_db)) as lc:
                    lc.row_factory = _sqlite3.Row
                    link_row = lc.execute(
                        "SELECT link_url FROM payment_links ORDER BY RANDOM() LIMIT 1"
                    ).fetchone()
                    pay_url = link_row["link_url"] if link_row else "https://aiitec.de"
            else:
                pay_url = "https://aiitec.de"
        except Exception:
            pay_url = "https://aiitec.de"

        body = (
            f"Hallo! Hier ist Sofia von AIITEC. "
            f"Wie versprochen — Ihr persönlicher Bestelllink: {pay_url} "
            f"Bei Fragen einfach antworten. Viel Erfolg!"
        )
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"To": to_number, "From": TWILIO_NUMBER(), "Body": body},
                auth=aiohttp.BasicAuth(sid, token),
                timeout=aiohttp.ClientTimeout(total=10),
            )
        log.info("SMS-Paymentlink gesendet an %s nach %ds Anruf", to_number, duration)
    except Exception as e:
        log.warning("SMS-Paymentlink Fehler: %s", e)


async def _notify_telegram(call_sid: str, duration: int, status: str) -> None:
    """Sendet Anrufbericht an Telegram — 🔥 bei Kaufsignal."""
    token = TG_TOKEN()
    chat  = TG_CHAT()
    if not token or not chat:
        return
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT direction, from_number, to_number, product_id, transcript "
                "FROM calls WHERE call_sid=?",
                (call_sid,)
            ).fetchone()
        if not row:
            return
        direction  = row["direction"]
        number     = row["to_number"] if direction == "outbound" else row["from_number"]
        product    = row["product_id"]
        transcript = (row["transcript"] or "").lower()
        appts      = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE call_sid=?", (call_sid,)
        ).fetchone()[0]

        kaufsignal = any(kw in transcript for kw in _KAUFSIGNAL_KEYWORDS)
        icon = "🔥" if kaufsignal else ("📞" if direction == "inbound" else "📲")
        sms_hint = " — SMS-Link gesendet ✅" if duration >= 30 else ""
        msg = (
            f"{icon} <b>{'KAUFSIGNAL!' if kaufsignal else 'Anruf beendet'}</b>\n"
            f"Nummer: {number}\n"
            f"Produkt: {product}\n"
            f"Dauer: {duration}s{sms_hint}\n"
            f"Termine: {'✅ ' + str(appts) if appts else '❌ keine'}"
        )
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("Telegram-Benachrichtigung fehlgeschlagen: %s", e)


# ── Twilio Nummer kaufen (einmaliges Setup) ───────────────────────────────────
async def buy_phone_number(country_code: str = "DE") -> str:
    """Kauft eine neue Twilio-Nummer für das angegebene Land.

    Args:
        country_code: ISO-3166 Ländercode (z.B. 'DE', 'US', 'GB')

    Returns:
        Gekaufte Rufnummer (E.164) oder '' bei Fehler.
    """
    sid    = TWILIO_SID()
    token  = TWILIO_TOKEN()
    domain = PUBLIC_URL()

    async with aiohttp.ClientSession() as session:
        # Verfügbare Nummern suchen
        async with session.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}"
            f"/AvailablePhoneNumbers/{country_code}/Local.json"
            "?VoiceEnabled=true&SmsEnabled=true",
            auth=aiohttp.BasicAuth(sid, token),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()

        numbers = data.get("available_phone_numbers", [])
        if not numbers:
            raise ValueError(f"Keine Nummern in {country_code} verfügbar")

        phone_number = numbers[0]["phone_number"]
        webhook_url  = f"https://{domain}/api/phone/incoming"

        # Nummer kaufen und Webhook setzen
        async with session.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            data={
                "PhoneNumber":           phone_number,
                "VoiceUrl":              webhook_url,
                "VoiceMethod":           "POST",
                "StatusCallback":        f"https://{domain}/api/phone/status",
                "StatusCallbackMethod":  "POST",
            },
            auth=aiohttp.BasicAuth(sid, token),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp2:
            result = await resp2.json()

    purchased = result.get("phone_number", phone_number)
    log.info("Neue Twilio-Nummer gekauft: %s", purchased)
    return purchased


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _load_env() -> None:
        ef = _BASE / ".env"
        if ef.exists():
            for line in ef.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(
                        k.strip(), v.strip().strip('"').strip("'")
                    )

    _load_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PhoneAI] %(levelname)s %(message)s",
    )

    args = sys.argv[1:]

    if "--init-db" in args:
        init_db()
        print(f"DB initialisiert: {_DB}")

    elif "--buy-number" in args:
        idx     = args.index("--buy-number")
        country = args[idx + 1] if idx + 1 < len(args) else "DE"
        number  = asyncio.run(buy_phone_number(country))
        print(f"Gekaufte Nummer: {number}")
        print(f"→ In .env eintragen: TWILIO_PHONE_NUMBER={number}")

    elif "--test-call" in args:
        idx = args.index("--test-call")
        to  = args[idx + 1] if idx + 1 < len(args) else ""
        if not to:
            print("Verwendung: --test-call +49XXXXXXXXXX [product_id]")
        else:
            product = args[idx + 2] if idx + 2 < len(args) else "shopify"
            sid     = asyncio.run(trigger_outbound_call(to, product, "Test-Kontakt"))
            print(f"Anruf initiiert: {sid}" if sid else "Fehler beim Anruf")

    elif "--status" in args:
        init_db()
        status = get_status()
        for k, v in status.items():
            print(f"  {k}: {v}")

    elif "--stats" in args:
        init_db()
        with _db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            appts = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
        print(f"Anrufe gesamt: {total} | Termine gebucht: {appts}")

    else:
        print(__doc__)
        print("\nBefehle:")
        print("  --init-db              DB-Tabellen erstellen")
        print("  --buy-number [DE]      Twilio-Nummer kaufen")
        print("  --test-call +49...     Test-Outbound-Anruf")
        print("  --status               System-Status anzeigen")
        print("  --stats                Anruf-Statistiken anzeigen")
