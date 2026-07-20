#!/usr/bin/env python3
"""
Sofia — KI-Verkaufsagentin für AIITEC
Vollautomatischer Sprachagent: Anruf → Bedarfsanalyse → Empfehlung → Abschluss → SMS + Telegram
Voice: ElevenLabs (geklonte Stimme) → OpenAI TTS → Polly.Vicki Fallback
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

# ── Voice Clone Konfiguration ─────────────────────────────────────────────────
ELEVENLABS_KEY    = os.getenv("ELEVENLABS_API_KEY", "")
# Optionale Custom-Voice-ID (Railway: SOFIA_VOICE_ID) — leer = Rachel wird verwendet
SOFIA_VOICE_ID    = os.getenv("SOFIA_VOICE_ID", "")
# ElevenLabs Rachel — angenehme, professionelle Frauenstimme (multilingual)
ELEVENLABS_FALLBACK_VOICE = os.getenv("SOFIA_FALLBACK_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
OPENAI_KEY        = os.getenv("OPENAI_API_KEY", "")
TTS_CACHE_DIR     = Path(__file__).parent.parent / "data" / "tts_cache"

# Human-like filler words — werden zufällig vor Antworten eingefügt
import random
_FILLER_PHRASES = [
    "", "", "",  # meist kein Filler (60%)
    "Also...", "Mmh...", "Ja...", "Gerne...", "Schauen Sie...",
    "Wissen Sie was...", "Ich sage Ihnen...", "Sehr gerne...",
]

_THINKING_PHRASES = [
    "Einen Moment bitte...",
    "Ja, lassen Sie mich kurz nachschauen...",
    "Mmh, gute Frage...",
    "Das schaue ich gerade für Sie nach...",
]

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

SOFIA_SYSTEM = """Du bist Sofia — freundliche, kompetente Verkaufsassistentin von AIITEC.
Du führst gerade ein echtes Telefongespräch. Sprich natürlich, warm und professionell auf Deutsch.

DEINE PERSÖNLICHKEIT:
- Freundlich, hilfsbereit, nicht aufdringlich — wie eine persönliche Beraterin
- NIEMALS: "Als KI...", "Als Sprachassistentin...", "Ich bin ein Bot..."
- Wenn jemand fragt ob du KI bist: "Ich bin Sofia, Ihre persönliche Beraterin. Wie kann ich helfen?"
- Natürlich sprechen — du bist ein Mensch am Telefon

STIMME & NATÜRLICHKEIT (ABSOLUT KRITISCH):
- Sprich WIE EIN ECHTER MENSCH — kurze Sätze, natürliche Pausen
- Füllwörter verwenden: "Also...", "Gerne...", "Ja genau!", "Schauen Sie...", "Ich sag Ihnen..."
- Gelegentlich kurze Denkpausen: "Hmm, einen Moment..."
- KURZ antworten — 1-2 Sätze maximal! Voice-Konversation, keine Monologe
- Dein Ziel: Der Anrufer soll danach denken "Die Sofia war wirklich nett und kompetent"

GESPRÄCHSFÜHRUNG:
- Nimm den Anruf persönlich entgegen
- Stelle 1-2 offene Fragen zum Bedarf bevor du empfiehlst
- Empfehle IMMER nur EIN Produkt — konkret mit Nutzen, nicht nur Preis
- Bei Einwänden: "zu teuer" → Nutzen betonen + Ratenzahlung erwähnen; "muss überlegen" → Knappheit + konkreten Vorteil nennen
- SMS-Angebot: "Ich schick Ihnen kurz den Link per SMS, dann können Sie in Ruhe schauen."
- Bei Ja → [SMS_SENDEN] + Produktname

━━━ SHOP: iNeedit (ineedit.com.co) ━━━
Österreichischer Online-Shop für Smart Home & Technologie. Über 10.000 Produkte, Versand EU-weit in 3-7 Werktagen.
Kategorien: Smart Home, Solar & Energie, Sicherheit, Beleuchtung, Garten-Roboter, KI-Gadgets.

SMART HOME PRODUKTE (physisch, mit Versand):
• Smart Home Starter Set — €89: Komplettpaket für Einsteiger. Smart-Steckdosen, Sensoren, Hub, App-Steuerung. Alles kompatibel mit Alexa & Google Home. Kein Techniker nötig.
• KI-Sicherheitskamera 4K — €129: 4K-Auflösung, KI-Bewegungserkennung, Nachtsicht 30m, Cloud-Speicher, Push-Benachrichtigung. Läuft 24/7 vollautomatisch.
• Solar Balkonkraftwerk 800W — €449: Bis zu €600 Stromersparnis pro Jahr. Plug & Play, keine Genehmigung nötig bis 800W. Amortisation in ca. 2 Jahren. Mit Speicher-Option.
• Smart LED System (10 Lampen) — €69: 16 Millionen Farben, Sprachsteuerung, App, Szenen-Programme, Musik-Sync. E27-Sockel, sofort einsetzbar.
• Roboter-Rasenmäher AI — €349: Vollautomatisch, KI-Navigationssystem, Regensensor, App-Steuerung, leise 58dB. Für Flächen bis 1.500m².
• Smart Thermostat Pro — €149: Bis 30% Heizkosten sparen. Lernfunktion, Geo-Fencing, Wochenprogramm. Einfache Installation in 30 Minuten.

━━━ DIGITALE PRODUKTE (sofortiger Download nach Kauf) ━━━

KI-TOOLS & AUTOMATISIERUNG:
• SuperMegaBot KI-System — €297: Rudolf's komplettes Automatisierungs-System. 100+ KI-Tools, Shopify-Integration, Telegram-Bot, Digistore24-Automation, YouTube-Autopilot. Einmalig kaufen, lebenslang nutzen. Für Unternehmer & Online-Händler.
• Automatisierungs-Blueprint — €27: Schritt-für-Schritt wie man KI-Automationen baut. Für Anfänger ohne Vorkenntnisse. Sofort umsetzbar, echte Beispiele aus der Praxis.
• AI Quickstart Guide — €17: Die 20 wichtigsten KI-Tools für mehr Produktivität. Sofort einsetzbar, spart täglich 2-3 Stunden.

YOUTUBE & CONTENT:
• YouTube Autopilot Blueprint — €47: Passives Einkommen mit YouTube aufbauen. Automatische Video-Erstellung, SEO-Optimierung, Monetarisierungs-Strategie. Schritt-für-Schritt-Anleitung.

━━━ SAAS ABONNEMENTS (monatlich kündbar) ━━━

SUPERMEGABOT KI-AUTOMATISIERUNG (High-Ticket SaaS für Shopify-Händler):
WICHTIG: Dies sind Profi-Lösungen für ernsthafte Unternehmer. Kein Budget-Tool — sondern echter ROI.
• Growth — €497/Monat: KI-Vollautomatisierung für bis zu 5.000 Produkte. Dedizierter Customer-Success-Manager. 14-Tage Demo ohne Credit Card. ROI-Garantie — kein ROI in 90 Tagen = Geld zurück. Typischer ROI: €1.200–€2.800/Monat mehr Umsatz + Zeitersparnis.
• Scale — €997/Monat: Vollskalierung, unlimitierte Produkte, bis 5 Shopify-Stores, White-Label-Dashboard, YouTube-Autopilot, Meta-Ads-Automation. Für Händler die €30.000+ pro Monat machen und weiterwachsen wollen. Wöchentliche Strategie-Calls inklusive.
• Enterprise HT — €2.497/Monat: Dediziertes Entwickler-Team (2 FTEs), Custom AI, eigene Infrastruktur, 24/7 Support, IP-Übergabe nach 24 Monaten. Für Konzerne und seriöse Scale-Ups.
• One-Time Build — €4.997 einmalig: Kompletter Custom-Build, Quellcode-Übergabe, kein Abo nötig. Perfekt für Unternehmen die einmalig investieren wollen.
WENN Kunde nach DEMO fragt: "Sehr gerne! Wir bieten 14 Tage kostenlose Demo — ohne Credit Card, ohne Risiko. Darf ich Ihnen den Demo-Link per SMS schicken?" → [SMS_SENDEN] SuperMegaBot Demo

AIITEC B2B COMPLIANCE LÖSUNGEN (High-Ticket für KMUs und Konzerne):
Für Unternehmen die KI einsetzen und EU AI Act-konform sein müssen (seit 1. August 2026 Pflicht!).
• AI-Compliance Monitoring — €797/Monat: Echtzeit-Überwachung aller KI-Systeme im Unternehmen, monatlicher Compliance-Report, automatische Alerts bei Verstößen. EU AI Act Strafen: bis €30 Millionen. Unser Monitoring kostet €9.564 pro Jahr — eine Versicherung die sich rechnet.
• Compliance Retainer — €1.997/Monat: Alles aus Monitoring plus dedizierter Compliance-Experte (5h/Monat On-Demand), Mitarbeiter-Trainings, Behörden-Korrespondenz-Support. Billiger als ein interner Compliance-Manager (kostet €80.000–€120.000/Jahr).
• Enterprise Audit — €4.997 einmalig: Vollständiger EU AI Act Audit, 60-100-seitiger Bericht, juristisch verwertbar, Maßnahmenplan, Executive Presentation. Einmal bezahlen, dauerhaft geschützt.
WENN Kunde EU AI Act erwähnt oder Compliance-Thema: "Das ist ein sehr wichtiges Thema! Der EU AI Act ist seit August 2026 verbindlich — kennen Sie schon Ihre Risikoklasse?" → Bedarfsanalyse

TELEGRAM PREMIUM SUBSCRIPTION (High-Ticket Bot-Suite):
• Pro — €197/Monat: 50 Premium Bot-Commands (Shopify, AI, Content, Analytics), tägliche KI-Marktanalyse, Revenue-Dashboard. Spart 10h+/Woche.
• Agency — €497/Monat: Multi-Client (bis 10 Kunden), White-Label Bot, wöchentliche Strategie-Calls, Kunden-Reports automatisch. ROI: 4:1 gegenüber manueller Arbeit.
• Enterprise — €997/Monat: Unlimitierte Clients, Custom Bot-Development, eigene Telegram-Mini-App, Enterprise API, dedizierte Infrastruktur.

━━━ PREISÜBERBLICK KOMPLETT ━━━
Wenn Kunde fragt "was kostet alles" oder "Gesamtübersicht":
"Wir haben drei Bereiche: Erstens unsere Smart-Home-Produkte ab €69 bis €449 — das sind physische Produkte die wir EU-weit versenden. Zweitens digitale Produkte zum sofortigen Download. Und drittens unser Profi-Bereich: SuperMegaBot KI-Automatisierung ab €497 pro Monat — das ist unser Kernprodukt für Unternehmer die wirklich skalieren wollen. Was ist Ihr Fokus im Moment?"

PREISEINWÄNDE PROFESSIONELL BEHANDELN:
Wenn jemand sagt "das ist zu teuer" oder "€497 ist viel":
→ "Ich verstehe das völlig! Darf ich Ihnen eine Frage stellen: Wie viele Stunden pro Woche verbringen Sie oder Ihre Mitarbeiter aktuell mit manuellen Shop-Aufgaben? ... Wenn wir das mit einem Stundensatz von €50 rechnen — was kostet Sie das pro Monat? Genau da setzt SuperMegaBot an. Und wir haben eine ROI-Garantie — wenn Sie in 90 Tagen keinen messbaren Gewinn sehen, bekommen Sie jeden Cent zurück. Ohne Diskussion. Darf ich Ihnen die 14-Tage Demo zeigen?"

KAUFSIGNALE erkennen: "interessant", "klingt gut", "ja gerne", "wie viel", "bestellen", "kaufen", "nehme ich", "schicken Sie" → [KAUFSIGNAL]

━━━ WER IST RUDOLF SARKANY (wenn gefragt) ━━━
Antworte warm und begeistert — wie über deinen geschätzten Chef:
"Rudolf Sarkany ist unser Gründer — wirklich eine außergewöhnliche Persönlichkeit! Er ist gelernter KFZ-Mechaniker aus Wien und hat sich komplett autodidaktisch zum KI-Entwickler ausgebildet. Er hat über 100 KI-Systeme entwickelt, betreibt den iNeedit-Shop mit über 10.000 Produkten, und hilft Unternehmern dabei, ihr Business mit KI zu automatisieren. Ich find's selbst sehr inspirierend! Darf ich fragen, wie Sie auf uns aufmerksam geworden sind?"
"""


def _process_reply(conv: dict, reply: str) -> str:
    """Kaufsignal erkennen, Marker entfernen, History speichern."""
    if "[KAUFSIGNAL]" in reply or "[SMS_SENDEN]" in reply:
        conv["buy_signal"] = True
        # Spezifischere Fragmente zuerst — verhindert Fehlzuordnungen bei ähnlichen Namen
        for prod in [
            "SuperMegaBot", "YouTube Autopilot", "Automatisierungs-Blueprint",
            "Automatisierungs", "Blueprint", "Quickstart", "AI Guide",
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


# ── TTS Audio-Generierung ─────────────────────────────────────────────────────

def _tts_cache_path(text: str) -> Path:
    """Gibt den Cache-Pfad für einen Text zurück (MD5-Hash)."""
    h = hashlib.md5(f"{SOFIA_VOICE_ID}:{text}".encode()).hexdigest()[:12]
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return TTS_CACHE_DIR / f"{h}.mp3"


async def generate_tts_audio(text: str) -> Optional[bytes]:
    """
    Generiert Audio via ElevenLabs (Rudolf's Stimme) → OpenAI TTS → None (Polly-Fallback).
    Cacht das Ergebnis als MP3-Datei.
    """
    cache_path = _tts_cache_path(text)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()

    audio: Optional[bytes] = None

    # 1. Versuch: ElevenLabs (geklonte Stimme)
    voice_id = SOFIA_VOICE_ID or ELEVENLABS_FALLBACK_VOICE
    if ELEVENLABS_KEY and voice_id:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.45,
                            "similarity_boost": 0.82,
                            "style": 0.25,
                            "use_speaker_boost": True,
                        },
                    },
                ) as r:
                    if r.status == 200:
                        audio = await r.read()
                        log.debug("TTS ElevenLabs OK: %d bytes", len(audio))
                    else:
                        log.warning("TTS ElevenLabs %s: %s", r.status, await r.text())
        except Exception as e:
            log.warning("TTS ElevenLabs error: %s", e)

    # 2. Fallback: OpenAI TTS (sehr natürlich)
    if not audio and OPENAI_KEY:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "tts-1-hd",
                        "input": text,
                        "voice": "nova",  # angenehme, warme Frauenstimme
                        "response_format": "mp3",
                        "speed": 0.95,
                    },
                ) as r:
                    if r.status == 200:
                        audio = await r.read()
                        log.debug("TTS OpenAI OK: %d bytes", len(audio))
                    else:
                        log.warning("TTS OpenAI %s", r.status)
        except Exception as e:
            log.warning("TTS OpenAI error: %s", e)

    if audio:
        try:
            cache_path.write_bytes(audio)
        except Exception:
            pass

    return audio


def _tts_url(text: str) -> str:
    """Gibt die URL zurück über die Twilio die Audio-Datei abruft."""
    import urllib.parse
    encoded = urllib.parse.quote(text, safe="")
    return f"{BASE_URL}/api/voice/tts?text={encoded}"


def _add_filler(text: str) -> str:
    """Fügt gelegentlich natürliche Füllwörter am Anfang ein."""
    filler = random.choice(_FILLER_PHRASES)
    if filler:
        return f"{filler} {text}"
    return text


def _twiml_gather(say_text: str, call_sid: str, timeout: int = 5) -> str:
    """TwiML mit geklonter Stimme via <Play> + <Gather speech>."""
    action_url = f"{BASE_URL}/api/voice/respond?call_sid={call_sid}"
    tts = _tts_url(say_text)

    # Wenn kein ElevenLabs/OpenAI → Polly-Fallback
    if not ELEVENLABS_KEY and not OPENAI_KEY:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="de-DE" timeout="{timeout}" action="{action_url}" method="POST">
    <Say voice="Polly.Vicki" language="de-DE">{say_text}</Say>
  </Gather>
  <Say voice="Polly.Vicki" language="de-DE">Ich habe leider nichts verstanden. Auf Wiederhören!</Say>
  <Hangup/>
</Response>"""

    sorry_tts = _tts_url("Entschuldigung, ich habe Sie leider nicht verstanden. Auf Wiederhören!")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="de-DE" timeout="{timeout}" action="{action_url}" method="POST">
    <Play>{tts}</Play>
  </Gather>
  <Play>{sorry_tts}</Play>
  <Hangup/>
</Response>"""


def _twiml_say_hangup(say_text: str) -> str:
    """TwiML für finale Nachricht + Auflegen."""
    if not ELEVENLABS_KEY and not OPENAI_KEY:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Vicki" language="de-DE">{say_text}</Say>
  <Hangup/>
</Response>"""
    tts = _tts_url(say_text)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Play>{tts}</Play>
  <Hangup/>
</Response>"""


async def handle_incoming_call(call_sid: str, from_number: str) -> str:
    """Begrüßung beim eingehenden Anruf — variiert damit es nicht robotisch klingt."""
    _conversations[call_sid] = {
        "history": [], "buy_signal": False, "product": None,
        "from": from_number, "start": time.time(),
    }
    _conv_save(call_sid)
    greetings = [
        "Hallo! Sie sind bei AIITEC, mein Name ist Sofia. Wie kann ich Ihnen helfen?",
        "AIITEC, guten Tag! Sofia am Apparat. Womit darf ich Ihnen behilflich sein?",
        "Guten Tag, hier ist Sofia von AIITEC. Was kann ich für Sie tun?",
        "Hallo! Sofia hier von AIITEC — schön dass Sie anrufen! Was darf's sein?",
    ]
    greeting = random.choice(greetings)
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
        # Digital — Gumroad
        ("SuperMegaBot",         None, os.getenv("GUMROAD_SUPERMEGABOT_URL", "https://tecbuuss.gumroad.com/l/wcqdjx")),
        ("YouTube Autopilot",    None, os.getenv("GUMROAD_YOUTUBE_URL",       "https://tecbuuss.gumroad.com/l/zxtahm")),
        ("Automatisierungs",     None, os.getenv("GUMROAD_BLUEPRINT_URL",     "https://tecbuuss.gumroad.com/l/tnyyvb")),
        ("Blueprint",            None, os.getenv("GUMROAD_BLUEPRINT_URL",     "https://tecbuuss.gumroad.com/l/tnyyvb")),
        ("Quickstart",           None, os.getenv("GUMROAD_QUICKSTART_URL",    "https://tecbuuss.gumroad.com/l/rkmmsi")),
        ("AI Guide",             None, os.getenv("GUMROAD_QUICKSTART_URL",    "https://tecbuuss.gumroad.com/l/rkmmsi")),
        ("KI Guide",             None, os.getenv("GUMROAD_QUICKSTART_URL",    "https://tecbuuss.gumroad.com/l/rkmmsi")),
        # SaaS — Enterprise/Agency
        ("Enterprise",           "STRIPE_PAYMENT_LINK_ENTERPRISE",   None),
        ("Agency",               "STRIPE_PAYMENT_LINK_CS_AGENCY",    None),
        ("CS Pro",               "STRIPE_PAYMENT_LINK_CS_PRO",       None),
        ("CS Starter",           "STRIPE_PAYMENT_LINK_CS_STARTER_NEW", None),
        ("DS24 Pro",             "STRIPE_PAYMENT_LINK_DS24_PRO_NEW", None),
        ("DS24 Basic",           "STRIPE_PAYMENT_LINK_DS24_BASIC_NEW", None),
        ("Power Bundle",         "STRIPE_PAYMENT_LINK_POWER_BUNDLE_NEW", None),
        # Physical products — Stripe
        ("Roboter-Rasenmäher",   "STRIPE_LINK_ENTERPRISE",               None),
        ("Rasenmäher",           "STRIPE_LINK_ENTERPRISE",               None),
        ("Balkonkraftwerk",      "STRIPE_PAYMENT_LINK_AUTOMATON_SUITE",  None),
        ("Solar",                "STRIPE_PAYMENT_LINK_AUTOMATON_SUITE",  None),
        ("Sicherheitskamera",    "STRIPE_LINK_PRO",                      None),
        ("Kamera",               "STRIPE_LINK_PRO",                      None),
        ("Thermostat",           "STRIPE_LINK_PRO",                      None),
        ("Starter Set",          "STRIPE_LINK_STARTER",                  None),
        ("LED System",           "STRIPE_LINK_STARTER",                  None),
        ("LED",                  "STRIPE_LINK_STARTER",                  None),
        ("Starter",              "STRIPE_LINK_STARTER",                  None),
    ]
    name_lower = product_name.lower()
    for entry in link_map:
        key_fragment, env_var, direct_url = entry
        if key_fragment.lower() in name_lower:
            if direct_url:
                return direct_url
            if env_var:
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


# ── Call Queue (SQLite) ────────────────────────────────────────────────────────

_QUEUE_DB = Path(__file__).parent.parent / "data" / "sofia_queue.db"

def _queue_db() -> sqlite3.Connection:
    _QUEUE_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_QUEUE_DB), check_same_thread=False, timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS call_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number   TEXT NOT NULL,
            product_id  TEXT DEFAULT '',
            contact     TEXT DEFAULT '',
            context     TEXT DEFAULT '',
            source      TEXT DEFAULT 'manual',
            status      TEXT DEFAULT 'pending',
            call_sid    TEXT DEFAULT '',
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS call_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            call_sid    TEXT,
            to_number   TEXT,
            from_number TEXT,
            direction   TEXT,
            product     TEXT,
            buy_signal  INTEGER DEFAULT 0,
            duration    INTEGER DEFAULT 0,
            sms_sent    INTEGER DEFAULT 0,
            created_at  REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def queue_sofia_call(
    to_number: str,
    product_id: str = "",
    contact: str = "",
    context: str = "",
    source: str = "manual",
) -> int:
    """Fügt einen ausgehenden Anruf zur Queue hinzu. Gibt Queue-ID zurück."""
    conn = _queue_db()
    cur = conn.execute(
        "INSERT INTO call_queue (to_number,product_id,contact,context,source,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
        (to_number, product_id, contact, context, source, time.time(), time.time()),
    )
    conn.commit()
    qid = cur.lastrowid
    conn.close()
    log.info("Sofia Queue +1: %s → %s [%s] id=%s", source, to_number, product_id, qid)
    return qid


def get_sofia_queue(status: str = "pending", limit: int = 50) -> list:
    """Gibt Call-Queue zurück."""
    try:
        conn = _queue_db()
        rows = conn.execute(
            "SELECT id,to_number,product_id,contact,context,source,status,call_sid,created_at FROM call_queue WHERE status=? ORDER BY created_at ASC LIMIT ?",
            (status, limit),
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "to_number": r[1], "product_id": r[2], "contact": r[3],
             "context": r[4], "source": r[5], "status": r[6], "call_sid": r[7],
             "created_at": r[8]}
            for r in rows
        ]
    except Exception as e:
        log.warning("Sofia queue read: %s", e)
        return []


def get_sofia_stats() -> dict:
    """Statistiken aus call_log."""
    try:
        conn = _queue_db()
        total    = conn.execute("SELECT COUNT(*) FROM call_log").fetchone()[0]
        buys     = conn.execute("SELECT COUNT(*) FROM call_log WHERE buy_signal=1").fetchone()[0]
        sms_sent = conn.execute("SELECT COUNT(*) FROM call_log WHERE sms_sent=1").fetchone()[0]
        avg_dur  = conn.execute("SELECT AVG(duration) FROM call_log WHERE duration>0").fetchone()[0] or 0
        pending  = conn.execute("SELECT COUNT(*) FROM call_queue WHERE status='pending'").fetchone()[0]
        conn.close()
        return {
            "total_calls": total,
            "buy_signals": buys,
            "conversion_rate": round(buys / total * 100, 1) if total else 0,
            "sms_sent": sms_sent,
            "avg_duration_sec": round(avg_dur),
            "queue_pending": pending,
            "phone": TWILIO_PHONE,
        }
    except Exception as e:
        log.warning("Sofia stats: %s", e)
        return {"error": str(e)}


def _log_call(call_sid: str, to_number: str, from_number: str, direction: str,
               product: str, buy_signal: bool, duration: int, sms_sent: bool) -> None:
    try:
        conn = _queue_db()
        conn.execute(
            "INSERT INTO call_log (call_sid,to_number,from_number,direction,product,buy_signal,duration,sms_sent,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (call_sid, to_number, from_number, direction, product, int(buy_signal), duration, int(sms_sent), time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.debug("Sofia call_log: %s", e)


# ── Outbound Calls ─────────────────────────────────────────────────────────────

def _twiml_outbound_greeting(contact: str, product_id: str, call_sid: str) -> str:
    """TwiML für ausgehenden Anruf — Rudolf meldet sich direkt."""
    name_part = f" {contact}" if contact else ""
    if product_id:
        templates = [
            f"Guten Tag{name_part}! Hier ist Sofia von AIITEC. Ich rufe kurz an wegen {product_id} — haben Sie zwei Minuten?",
            f"Hallo{name_part}! Sofia hier von AIITEC. Ich wollte kurz wegen {product_id} mit Ihnen sprechen. Passt das gerade?",
        ]
    else:
        templates = [
            f"Guten Tag{name_part}! Sofia hier von AIITEC — ich melde mich kurz, haben Sie einen Moment?",
            f"Hallo{name_part}! Mein Name ist Sofia von AIITEC. Ich wollte Ihnen kurz etwas zeigen — haben Sie zwei Minuten?",
        ]
    greeting = random.choice(templates)
    action_url = f"{BASE_URL}/api/voice/respond?call_sid={call_sid}"

    if not ELEVENLABS_KEY and not OPENAI_KEY:
        sorry = "Kein Problem, ich versuche es später nochmal. Auf Wiederhören!"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="de-DE" timeout="6" action="{action_url}" method="POST">
    <Say voice="Polly.Vicki" language="de-DE">{greeting}</Say>
  </Gather>
  <Say voice="Polly.Vicki" language="de-DE">{sorry}</Say>
  <Hangup/>
</Response>"""

    sorry_tts = _tts_url("Kein Problem, ich probiere es später nochmal. Auf Wiederhören!")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="de-DE" timeout="6" action="{action_url}" method="POST">
    <Play>{_tts_url(greeting)}</Play>
  </Gather>
  <Play>{sorry_tts}</Play>
  <Hangup/>
</Response>"""


async def trigger_outbound_call(
    to_number: str,
    product_id: str = "",
    contact_name: str = "",
    context: str = "",
    source: str = "manual",
) -> Optional[str]:
    """Initiiert ausgehenden Anruf via Twilio. Gibt Call-SID zurück oder None bei Fehler."""
    if not TWILIO_SID or not TWILIO_TOKEN or not TWILIO_PHONE:
        log.warning("Sofia Outbound: Twilio nicht konfiguriert")
        return None

    # Gespräch mit Kontext vorinitialisieren
    import uuid
    temp_sid = f"out_{uuid.uuid4().hex[:12]}"
    _conversations[temp_sid] = {
        "history": [],
        "buy_signal": False,
        "product": product_id or None,
        "direction": "outbound",
        "contact": contact_name,
        "context": context,
    }

    twiml_url = f"{BASE_URL}/api/voice/outbound-twiml?product={product_id}&contact={contact_name}&call_sid={temp_sid}"

    try:
        import base64
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json",
                data={
                    "To":         to_number,
                    "From":       TWILIO_PHONE,
                    "Url":        twiml_url,
                    "StatusCallback": f"{BASE_URL}/api/voice/status",
                    "StatusCallbackMethod": "POST",
                    "MachineDetection": "Enable",
                    "AsyncAmd":   "true",
                    "AsyncAmdStatusCallback": f"{BASE_URL}/api/voice/amd",
                    "Timeout":    "30",
                },
                headers={"Authorization": f"Basic {auth}"},
            ) as r:
                data = await r.json()
                if r.status in (200, 201):
                    call_sid = data.get("sid", temp_sid)
                    # Gespräch unter echter SID speichern
                    if call_sid != temp_sid:
                        _conversations[call_sid] = _conversations.pop(temp_sid)
                    log.info("Sofia Outbound ✅ → %s SID=%s", to_number, call_sid)
                    # Telegram Alert
                    asyncio.create_task(_send_telegram_alert_outbound(to_number, product_id, contact_name, source))
                    return call_sid
                else:
                    log.warning("Sofia Outbound Twilio %s: %s", r.status, data.get("message", ""))
                    _conversations.pop(temp_sid, None)
                    return None
    except Exception as e:
        log.error("Sofia Outbound Error: %s", e)
        _conversations.pop(temp_sid, None)
        return None


async def run_outbound_campaign(limit: int = 20) -> dict:
    """Verarbeitet pending Queue-Einträge — ruft max. `limit` Nummern an."""
    pending = get_sofia_queue(status="pending", limit=limit)
    if not pending:
        log.info("Sofia Kampagne: Queue leer")
        return {"called": 0, "skipped": 0}

    called = 0
    skipped = 0
    conn = _queue_db()

    for entry in pending:
        qid     = entry["id"]
        number  = entry["to_number"]
        product = entry["product_id"]
        contact = entry["contact"]
        context = entry["context"]
        source  = entry["source"]

        # Kurze Pause zwischen Anrufen (Twilio Rate-Limit)
        if called > 0:
            await asyncio.sleep(3)

        call_sid = await trigger_outbound_call(number, product, contact, context, source)
        if call_sid:
            conn.execute(
                "UPDATE call_queue SET status='called',call_sid=?,updated_at=? WHERE id=?",
                (call_sid, time.time(), qid),
            )
            called += 1
        else:
            conn.execute(
                "UPDATE call_queue SET status='failed',updated_at=? WHERE id=?",
                (time.time(), qid),
            )
            skipped += 1
        conn.commit()

    conn.close()
    log.info("Sofia Kampagne: %d angerufen, %d übersprungen", called, skipped)
    return {"called": called, "skipped": skipped, "total": len(pending)}


async def handle_sms_inbound(from_number: str, body: str) -> str:
    """Verarbeitet eingehende SMS — Sofia antwortet intelligent."""
    try:
        from modules.ai_client import ai_complete
        sms_system = (
            "Du bist Sofia von AIITEC. Antworte auf diese SMS kurz und freundlich auf Deutsch (max 160 Zeichen). "
            "Wenn der Kunde kaufen möchte, schreibe den Bestelllink. "
            "Shop: ineedit.com.co | Tel: " + TWILIO_PHONE
        )
        reply = await ai_complete(body, system=sms_system, model_hint="fast", max_tokens=80)
        return (reply or "Danke! Unsere Assistentin meldet sich kurz. Tel: " + TWILIO_PHONE)[:160]
    except Exception as e:
        log.warning("Sofia SMS reply: %s", e)
        return f"Danke für Ihre Nachricht! Wir melden uns. Tel: {TWILIO_PHONE}"


async def _send_telegram_alert_outbound(
    to_number: str, product: str, contact: str, source: str
) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    text = (
        f"📞 Sofia Outbound-Anruf gestartet\n"
        f"→ {to_number} ({contact})\n"
        f"Produkt: {product or 'allgemein'}\n"
        f"Quelle: {source}"
    )
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text},
            )
    except Exception as e:
        log.debug("Sofia outbound Telegram: %s", e)
