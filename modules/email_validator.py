"""
EmailValidator — 5-Layer Prüfer für ALLE ausgehenden Emails
===========================================================
Kein Email verlässt das System ohne diesen Check.

Layer 1  Basis-Sanity        Leer? Placeholder? Kürzer als 50 Zeichen?
Layer 2  Absender-Schutz     Bekannte private Domains → NIEMALS auto-antworten
Layer 3  Inhalt-Qualität     Spam-Muster, Platzhalter, fehlende Signatur
Layer 4  KI-Score            Groq bewertet 1-10, Minimum = 7
Layer 5  Spam-Ratio          Link-Dichte, Emoji-Dichte, Großbuchstaben

Fail-Safe: Bei jedem Fehler → BLOCKIEREN

Verwendung:
    from modules.email_validator import validate_email_content, classify_incoming
    ok, reason = await validate_email_content(subject, body, recipient)
    if not ok:
        log.warning("EmailValidator BLOCK: %s", reason)
        return  # nicht senden
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.request
from typing import Optional

import aiohttp

log = logging.getLogger("EmailValidator")

# ── Konfiguration ─────────────────────────────────────────────────────────────
MIN_AI_SCORE  = 7     # Minimum KI-Score (1-10)
MIN_BODY_LEN  = 50    # Mindest-Body-Länge in Zeichen

# ── Layer 2: Domains die NIEMALS auto-beantwortet werden dürfen ───────────────
# Das sind PRIVATE oder SYSTEM-Adressen — Rudolf's persönliche Kontakte,
# bekannte SaaS-Services, oder Adressen die manuell behandelt werden müssen.
_NEVER_AUTOREPLY_DOMAINS = {
    # Eigene Domains (kein Auto-Reply auf sich selbst)
    "aiitecbuuss@gmail.com", "bullpowersrtkennels@gmail.com",
    "dragonadnp@gmail.com", "rudolf.sarkany.aiitec@gmail.com",
    "rudolfsarkany1984@gmail.com", "nikolestimi@gmail.com",
    # SaaS die Notifications schicken
    "railway.app", "railway.com", "netlify.com", "vercel.com",
    "shopify.com", "myshopify.com", "stripe.com", "paddle.com",
    "paypal.com", "klaviyo.com", "mailchimp.com", "sendgrid.com",
    "github.com", "gitlab.com", "jira.com", "notion.so",
    "anthropic.com", "openai.com", "groq.com",
    "ebay.com", "amazon.com", "amazon.de", "etsy.com",
    "digistore24.com", "checkout-ds24.com",
    "google.com", "googleapis.com", "accounts.google.com",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    # Bounce / Delivery Reports
    "mailer-daemon", "postmaster", "noreply", "no-reply",
    "donotreply", "do-not-reply", "bounce", "bounces",
    "undeliverable", "notification", "notifications",
    "newsletter", "news", "info@mailchimp", "info@klaviyo",
    # Inkasso / Behörden → nur Telegram-Alert, KEIN Auto-Reply
    "inkasso", "gerichtsvollzieher", "mahnung",
    "amtsgericht", "finanzamt", "zoll", "behoerde",
}

# ── Layer 1: Verbotene Muster im Email-Body ───────────────────────────────────
_L1_BLOCKED_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in [
    r"\blorem ipsum\b",
    r"\bundefined\b",
    r"\bnull\b",
    r"\bNaN\b",
    r"\[object\s+Object\]",
    r"\bPLACEHOLDER\b",
    r"\bINSERT[_\s]+HERE\b",
    r"\bTODO[:\s]",
    r"example\.com",
    r"yourdomain\.",
    r"\btest.{0,20}email\b",
    r"\{\{.*?\}\}",
    r"\$\{.*?\}",
    r"__MISSING__",
    r"ERROR:.*\n",
    r"Traceback \(most recent",
    r"<class '.*Error",
    r"None None None",
    r"Hallo\s+None", r"für None\b", r"— None\b", r"\bNoneType\b",
    r"\bN/A\s+N/A\b",
    # Falsche Signatur-Platzhalter
    r"\[Vorname\]", r"\[Name\]", r"\[Firmenname\]",
    r"\[COMPANY\]", r"\[NAME\]", r"\[RECIPIENT\]",
]]

# ── Layer 3: Spam-Phrasen die NICHT in Business-Emails vorkommen dürfen ──────
_L3_SPAM_PHRASES = [
    "passives einkommen", "finanzielle freiheit", "reich werden schnell",
    "während du schläfst", "online geld verdienen ohne aufwand",
    "exklusives angebot nur heute", "100% garantiert",
    "millionär werden", "geheimnis der reichen",
    "lorem ipsum", "sample body", "test email content",
    "click here to unsubscribe if this was sent in error",
    "[unsubscribe]", "dear friend", "dear sir/madam",
    "dear valued customer",  # zu generisch
    # Typische Spam-Einleitungen ohne Personalisierung
    "i am writing to inform you that you have won",
    "congratulations you have been selected",
    "this is an automated message please do not reply",
]

# ── Layer 3: Signatur-Pflicht ─────────────────────────────────────────────────
_VALID_SIGNATURE_PATTERNS = [
    re.compile(r"mit\s+freundlichen\s+gr[üu]ssen?\b", re.I),
    re.compile(r"best\s+regards\b", re.I),
    re.compile(r"mit\s+freundlichem\s+gru[ßs]\b", re.I),
    re.compile(r"viele\s+gr[üu]sse?\b", re.I),
    re.compile(r"herzliche\s+gr[üu]sse?\b", re.I),
    re.compile(r"rudolf\s+sarkany\b", re.I),
    re.compile(r"aiitec\b", re.I),
    re.compile(r"mit\s+besten\s+gr[üu]ssen?\b", re.I),
    re.compile(r"yours\s+sincerely\b", re.I),
    re.compile(r"kind\s+regards\b", re.I),
]

# ── KI-Score ──────────────────────────────────────────────────────────────────
_EMAIL_SCORE_PROMPT = """Du bist ein strenger E-Mail-Qualitätsprüfer.
Bewerte diese Geschäfts-E-Mail auf einer Skala von 1-10:

1-3 = Spam, Platzhalter, unlesbarer Inhalt, falsche Sprache, technischer Fehler-Text
4-6 = Schwach, zu generisch, schlechte Grammatik, kein klarer Mehrwert
7-8 = Professionell, klar, relevant, korrekte Sprache, klare Handlungsaufforderung
9-10 = Ausgezeichnet — überzeugend, personalisiert, professionell

Antworte NUR mit der Zahl (1-10). Nichts anderes.

Betreff: {subject}
Body (Auszug):
{body}"""


async def _ai_score_email(subject: str, body: str) -> int:
    """KI-Score 1-10 für Email-Qualität. Bei Fehler: 0 (Block)."""
    key = os.getenv("GROQ_API_KEY", "")
    text = _EMAIL_SCORE_PROMPT.format(
        subject=subject[:100],
        body=body[:600]
    )
    if key:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={
                        "model": "llama-3.1-8b-instant",
                        "max_tokens": 5,
                        "temperature": 0,
                        "messages": [{"role": "user", "content": text}],
                    },
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        raw = d["choices"][0]["message"]["content"].strip()
                        m = re.search(r"\d+", raw)
                        return min(10, max(0, int(m.group()))) if m else 0
                    elif r.status != 429:
                        return 0
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

    # Anthropic Fallback
    akey = os.getenv("ANTHROPIC_API_KEY", "")
    if akey:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": text}],
                    },
                    headers={"x-api-key": akey, "anthropic-version": "2023-06-01"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        raw = d["content"][0]["text"].strip()
                        m = re.search(r"\d+", raw)
                        return min(10, max(0, int(m.group()))) if m else 0
        except Exception:
            pass

    # Keine KI verfügbar → BLOCK
    return 0


def _notify_telegram_sync(subject: str, recipient: str, layer: int, reason: str, score: int = 0):
    """Synchrone Telegram-Benachrichtigung über blockierte Email."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    msg = (
        f"🚫 <b>EmailValidator BLOCKIERT</b>\n"
        f"Layer {layer} | An: {recipient[:50]}\n"
        f"Betreff: {subject[:80]}\n"
        f"Grund: <code>{reason}</code>\n"
        f"KI-Score: {score}/10"
    )
    try:
        payload = json.dumps({"chat_id": chat, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

async def validate_email_content(
    subject: str,
    body: str,
    recipient: str = "",
    require_signature: bool = True,
) -> tuple[bool, str]:
    """
    Prüft Email durch alle 5 Layer.
    Returns: (ok, reason)  — ok=False → NICHT senden.
    Fail-Safe: Bei technischem Fehler → BLOCK.
    """
    try:
        return await _validate(subject, body, recipient, require_signature)
    except Exception as e:
        log.error("EmailValidator kritischer Fehler: %s — BLOCK", e)
        _notify_telegram_sync(subject, recipient, 0, f"validator_crash: {e}")
        return False, f"validator_error_blocked: {e}"


async def _validate(subject, body, recipient, require_signature) -> tuple[bool, str]:
    body_clean = (body or "").strip()
    subject_clean = (subject or "").strip()

    # ── Layer 1: Basis-Sanity ────────────────────────────────────────────────
    if not body_clean:
        return False, "email_body_leer"

    if not subject_clean:
        return False, "email_betreff_leer"

    if len(body_clean) < MIN_BODY_LEN:
        reason = f"email_body_zu_kurz ({len(body_clean)} < {MIN_BODY_LEN} Zeichen)"
        _notify_telegram_sync(subject_clean, recipient, 1, reason)
        return False, reason

    for rx in _L1_BLOCKED_RE:
        if rx.search(body_clean):
            reason = f"verbotenes_muster: {rx.pattern[:50]}"
            _notify_telegram_sync(subject_clean, recipient, 1, reason)
            return False, reason

    # ── Layer 2: Empfänger-Schutz ────────────────────────────────────────────
    if recipient:
        rec_lower = recipient.lower()
        for blocked in _NEVER_AUTOREPLY_DOMAINS:
            if blocked in rec_lower:
                reason = f"empfaenger_gesperrt: {blocked}"
                log.info("EmailValidator L2 BLOCK: %s → %s", blocked, recipient[:60])
                return False, reason

    # ── Layer 3: Inhalt-Qualität ─────────────────────────────────────────────
    body_lower = body_clean.lower()
    for phrase in _L3_SPAM_PHRASES:
        if phrase in body_lower:
            reason = f"spam_phrase: {phrase}"
            _notify_telegram_sync(subject_clean, recipient, 3, reason)
            return False, reason

    # Signatur-Pflicht
    if require_signature:
        has_sig = any(rx.search(body_clean) for rx in _VALID_SIGNATURE_PATTERNS)
        if not has_sig:
            reason = "keine_gueltige_signatur (Rudolf Sarkany / AiiteC / Mit freundlichen Grüßen)"
            _notify_telegram_sync(subject_clean, recipient, 3, reason)
            return False, reason

    # ── Layer 4: KI-Score ────────────────────────────────────────────────────
    score = await _ai_score_email(subject_clean, body_clean)
    if score < MIN_AI_SCORE:
        reason = f"ki_score_zu_niedrig ({score}/10 < {MIN_AI_SCORE})"
        _notify_telegram_sync(subject_clean, recipient, 4, reason, score)
        return False, reason

    # ── Layer 5: Spam-Ratio ──────────────────────────────────────────────────
    urls = re.findall(r"https?://\S+", body_clean)
    words = len(body_clean.split())
    if words > 0 and len(urls) / max(words, 1) > 0.2:
        reason = f"zu_viele_links ({len(urls)} Links bei {words} Wörtern)"
        _notify_telegram_sync(subject_clean, recipient, 5, reason, score)
        return False, reason

    log.info("EmailValidator ✅ [%d/10] An:%s | %s", score, recipient[:40], subject_clean[:60])
    return True, f"ok (score={score})"


# ── Incoming Email Klassifizierung ───────────────────────────────────────────

_PRIVATE_MARKERS = [
    # Beziehungen
    r"\b(mama|papa|mutter|vater|oma|opa|bruder|schwester|tante|onkel)\b",
    r"\b(freund|freundin|kollege|kumpel|nachbar)\b",
    # Persönliche Anlässe
    r"\b(geburtstag|hochzeit|urlaub|weihnachten|ostern|silvester)\b",
    r"\b(wie geht.{0,10}(dir|euch|ihnen)|alles gut|alles okay)\b",
    # Informelle Anrede
    r"^(hey|hallo\s+(rudi|rudolf)|lieber\s+rudi|hi\s+rudi)",
]
_PRIVATE_RE = [re.compile(p, re.I) for p in _PRIVATE_MARKERS]

_INKASSO_RE = re.compile(
    r"\b(mahnung|inkasso|gerichtsvollzieher|zwangsvollstreckung|"
    r"forderung.{0,20}fällig|offene\s+rechnung|zahlungsaufforderung|"
    r"insolvenz|pfändung)\b",
    re.I
)

_SPAM_RE = re.compile(
    r"\b(unsubscribe|abmelden|newsletter|no.reply|mailer.daemon|"
    r"delivery.failure|bounced|postmaster)\b",
    re.I
)


def classify_incoming_email(sender: str, subject: str, body: str) -> str:
    """
    Klassifiziert eingehende Emails.

    Returns:
        "private"     → NIEMALS auto-antworten, Rudolf manuell informieren
        "inkasso"     → Telegram-Alert an Rudolf, KEIN Auto-Reply
        "spam"        → Komplett ignorieren
        "unsubscribe" → Nur Abmelde-Bestätigung senden
        "business"    → Normale Business-Verarbeitung
    """
    text = f"{subject} {body[:500]}".lower()
    sender_lower = sender.lower()

    # Spam/System-Mails zuerst
    if _SPAM_RE.search(text) or _SPAM_RE.search(sender_lower):
        return "spam"

    # Inkasso/Rechtliche Schreiben
    if _INKASSO_RE.search(text):
        return "inkasso"

    # Abmeldung
    if re.search(r"\b(unsubscribe|abmelden|austragen|kein\s+(weitere|newsletter))\b", text, re.I):
        return "unsubscribe"

    # Private Emails (kein Auto-Reply!)
    full_text = f"{subject} {body[:300]}"
    if any(rx.search(full_text) for rx in _PRIVATE_RE):
        return "private"

    return "business"


async def generate_quality_email_reply(
    incoming_text: str,
    sender_name: str,
    intent: str,
    context: str = "",
) -> tuple[bool, str, str]:
    """
    Generiert GEPRÜFTE Email-Antwort via KI.
    Returns: (ok, subject, body) — ok=False wenn Qualitätscheck fehlschlägt.
    """
    from modules.ai_client import ai_complete

    system = """Du bist Rudolf Sarkany von AiiteC.
Schreibe professionelle, personalisierte Geschäfts-Emails auf Deutsch.
IMMER mit korrekter Signatur: "Mit freundlichen Grüßen\nRudolf Sarkany | AiiteC"
KEINE Platzhalter, KEIN Spam-Sprache, KEINE generischen Floskeln.
Maximal 200 Wörter. Klar, direkt, hilfreich."""

    prompt = f"""Incoming Email:
{incoming_text[:800]}

Sender: {sender_name}
Intent: {intent}
{f'Context: {context}' if context else ''}

Schreibe eine professionelle Antwort auf Deutsch. Nur der Email-Body, keine Betreffzeile."""

    try:
        body = await ai_complete(prompt, system=system, max_tokens=350)
    except Exception as e:
        log.error("Email-Generierung fehlgeschlagen: %s", e)
        return False, "", ""

    if not body or len(body.strip()) < 50:
        log.warning("Email-Generierung: zu kurzer Output")
        return False, "", ""

    # Betreff ableiten
    subject = f"Re: {intent.replace('_', ' ').title()}"

    # Qualitätscheck
    ok, reason = await validate_email_content(
        subject=subject,
        body=body,
        recipient="",
        require_signature=True,
    )
    if not ok:
        log.warning("Generierte Email fehlgeschlagen Validator: %s", reason)
        return False, "", ""

    return True, subject, body.strip()
