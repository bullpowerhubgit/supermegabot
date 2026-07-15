#!/usr/bin/env python3
"""
Email-KI: Vollautomatische Gesprächs-KI für alle eingehenden Email-Antworten
=============================================================================
Vollständig lebhaft — erkennt Absicht, antwortet sofort, schließt Deals.

Was es tut (alle 15 Minuten):
  1. Liest neue Antworten aus Gmail-Postfächern (alle 5 Accounts)
  2. Klassifiziert: Interesse / Einwand / Preis-Frage / Termin / Abmeldung / Spam
  3. Generiert lebhafte, persönliche Antwort via Claude
  4. Sendet sofort zurück (gleicher Account wie Outreach)
  5. Bei Termin-Anfrage: Kalender-Link senden
  6. Bei Kauf-Signal: Stripe-Checkout-Link senden
  7. Trackt alles in Supabase + Telegram-Benachrichtigung

Konversations-Typen die KI beherrscht:
  ✅ "Ja, ich bin interessiert" → Demo-Buchung + Follow-Up
  ✅ "Was kostet das?" → Preisliste + Testangebot
  ✅ "Ich bin bereits Kunde" → VIP-Behandlung + Upsell
  ✅ "Kein Interesse" → Höflich bestätigen + Opt-out
  ✅ "Rufen Sie mich an" → Telefonnummer abfragen + Sofia-Queue
  ✅ "Zu teuer" → Einwand behandeln + Starter-Plan anbieten
  ✅ "Wie funktioniert das?" → Erklärung + Demo
  ✅ "Wann kann ich starten?" → Sofort-Onboarding
  ✅ Mehrfach-Antworten / Follow-Up-Threads → Kontext merken
  ✅ Unbekannte Fragen → KI antwortet trotzdem passend

Scheduler: alle 15 Minuten
CLI:
  python3 modules/email_ai_conversations.py --run-now
  python3 modules/email_ai_conversations.py --stats
"""
from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import json
import logging
import os
import re
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("EmailAI")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "email_conversations.db"

# ── Env ───────────────────────────────────────────────────────────────────────
def _e(k: str, d: str = "") -> str: return os.getenv(k, d)

TG_TOKEN      = lambda: _e("TELEGRAM_BOT_TOKEN")
TG_CHAT       = lambda: _e("TELEGRAM_CHAT_ID")
PUBLIC_URL    = lambda: _e("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")

GMAIL_ACCOUNTS = [
    {"user": _e("GMAIL_USER_AIITEC",    "aiitecbuuss@gmail.com"),
     "pass": _e("GMAIL_APP_PASSWORD_AIITEC"),
     "name": "Rudolf Sarkany | AiiteC"},
    {"user": _e("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com"),
     "pass": _e("GMAIL_APP_PASSWORD_BULLPOWER"),
     "name": "Rudolf Sarkany | BullPower"},
    {"user": _e("GMAIL_USER_1",         "dragonadnp@gmail.com"),
     "pass": _e("GMAIL_APP_PASSWORD_1"),
     "name": "Rudolf Sarkany"},
    {"user": _e("GMAIL_USER_7",         "rudolf.sarkany.aiitec@gmail.com"),
     "pass": _e("GMAIL_APP_PASSWORD_7"),
     "name": "Rudolf Sarkany | AiiteC"},
    {"user": _e("GMAIL_USER_8",         "rudolfsarkany1984@gmail.com"),
     "pass": _e("GMAIL_APP_PASSWORD_8"),
     "name": "Rudolf Sarkany"},
]

STRIPE_LINKS = {
    "starter":    os.getenv("STRIPE_LINK_STARTER",    "https://buy.stripe.com/plink_1Ti4nuRJECiV6vSmFVom8L5E"),
    "pro":        os.getenv("STRIPE_LINK_PRO",        "https://buy.stripe.com/plink_1Ti4nvRJECiV6vSmFHKXWjbz"),
    "enterprise": os.getenv("STRIPE_LINK_ENTERPRISE", "https://buy.stripe.com/plink_1Ti4nwRJECiV6vSmgL2lZ7uk"),
    "demo":       "https://aiitec-saas-production.up.railway.app",
    "cal":        "https://cal.com/aiitec",
}

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
        CREATE TABLE IF NOT EXISTS threads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id    TEXT UNIQUE,
            from_email   TEXT,
            company      TEXT,
            account      TEXT,
            stage        TEXT DEFAULT 'new',
            intent       TEXT,
            last_reply   TEXT,
            last_sent    TEXT,
            reply_count  INTEGER DEFAULT 0,
            converted    INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id    TEXT,
            direction    TEXT,
            subject      TEXT,
            body         TEXT,
            sent_at      TEXT DEFAULT (datetime('now'))
        );
        """)

# ── Email-Intent Klassifikation ───────────────────────────────────────────────
INTENT_PATTERNS = {
    "interested":  ["interessiert", "ja", "gerne", "klingt gut", "mehr erfahren",
                    "erzählen", "schicken", "demo", "termin", "gespräch"],
    "price":       ["preis", "kosten", "kostet", "was zahle", "tarif", "plan",
                    "pricing", "günstig", "teuer", "budget", "angebot"],
    "objection":   ["zu teuer", "kein budget", "kein bedarf", "nicht nötig",
                    "funktioniert nicht", "glaube nicht", "zweifel"],
    "call_request":["anrufen", "telefonieren", "rückruf", "rufnummer", "nummer",
                    "telefon", "call", "sprechen"],
    "how_works":   ["wie funktioniert", "was genau", "erkläre", "zeige", "beispiel",
                    "wie sieht", "was macht", "mehr details"],
    "start_now":   ["starten", "anfangen", "loslegen", "sofort", "wann kann",
                    "zugang", "anmelden", "registrieren", "kaufen"],
    "unsubscribe": ["abmelden", "kein interesse", "bitte keine", "stop", "unsubscribe",
                    "entfernen", "aufhören", "nicht mehr"],
    "existing":    ["schon kunde", "bereits", "habe schon", "nutze schon"],
    "meeting":     ["termin", "meeting", "call buchen", "kalender", "zeit finden",
                    "wann passt", "verfügbar"],
}

def classify_intent(text: str) -> str:
    text_l = text.lower()
    scores = {intent: 0 for intent in INTENT_PATTERNS}
    for intent, keywords in INTENT_PATTERNS.items():
        for kw in keywords:
            if kw in text_l:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"

# ── KI-Antwort Generator ──────────────────────────────────────────────────────
KONVERSATIONS_SYSTEM = """Du bist Rudolf Sarkanys persönlicher KI-Sales-Assistent für AiiteC.
Du antwortest auf eingehende Business-Emails auf Deutsch — lebhaft, menschlich, überzeugend.

Stil:
- Persönlich und warm, nie roboterhaft
- Kurz und prägnant (max 120 Wörter)
- Immer mit konkretem nächsten Schritt
- Begeistert aber nicht übertrieben
- Schreibe wie ein echter Mensch — NICHT wie Marketing-Text
- KEINE Platzhalter wie [Name], [Produkt], {variable} verwenden

Produkte:
- Starter €49/Monat: 1 Shop, Grundfunktionen, KI-Automatisierung
- Pro €99/Monat: 3 Shops, alle KI-Features, Priorität-Support
- Enterprise €299/Monat: Unlimited Shops, White-Label, dedizierter Account Manager
- 14 Tage KOSTENLOS testen (keine Kreditkarte nötig)

Kauf-Links:
- Starter: https://buy.stripe.com/plink_1Ti4nuRJECiV6vSmFVom8L5E
- Pro: https://buy.stripe.com/plink_1Ti4nvRJECiV6vSmFHKXWjbz
- Enterprise: https://buy.stripe.com/plink_1Ti4nwRJECiV6vSmgL2lZ7uk
- Demo buchen: https://cal.com/aiitec

Signatur IMMER am Ende (genauso):
Mit freundlichen Grüßen,
Rudolf Sarkany | AiiteC – KI-Automatisierung für E-Commerce
"""

INTENT_PROMPTS = {
    "interested": (
        "Der Interessent hat positiv geantwortet. "
        "Bedanke dich herzlich, gib 2 konkrete Vorteile für seine Branche, "
        "schick den Demo-Link und schlage einen kurzen 15-Minuten-Call vor."
    ),
    "price": (
        "Der Interessent fragt nach dem Preis. "
        "Erkläre die 3 Pläne kurz (Starter €49, Pro €99, Enterprise €299), "
        "betone die kostenlose 14-Tage-Testphase, "
        "und frage welcher Plan am besten passt."
    ),
    "objection": (
        "Der Interessent hat einen Einwand (zu teuer / kein Bedarf). "
        "Verstehe den Einwand, behandle ihn konkret, "
        "biete die kostenlose Testphase als risikofreien Einstieg an. "
        "Nie aufdringlich."
    ),
    "call_request": (
        "Der Interessent möchte telefonieren. "
        "Bestätige enthusiastisch, "
        "bitte um seine Telefonnummer ODER gib den Kalender-Link. "
        "Schlage konkrete Zeitfenster vor (Mo-Fr 9-18 Uhr)."
    ),
    "how_works": (
        "Der Interessent fragt wie das System funktioniert. "
        "Erkläre in 3 einfachen Schritten was die KI macht, "
        "nenne 1 konkretes Ergebnis (z.B. '80% weniger manuelle Arbeit'), "
        "lade zur kostenlosen Demo ein."
    ),
    "start_now": (
        "Der Interessent will sofort starten — super! "
        "Gib direkten Link zum 14-Tage-Gratistest, "
        "erkläre dass er in 5 Minuten loslegen kann, "
        "biete an bei der Einrichtung zu helfen."
    ),
    "unsubscribe": (
        "Der Empfänger möchte abgemeldet werden. "
        "Bestätige freundlich die Abmeldung, "
        "entschuldige die Störung, wünsche alles Gute. "
        "Kein Sales-Versuch."
    ),
    "existing": (
        "Der Empfänger ist bereits Kunde. "
        "Bedanke dich herzlich, frage ob alles gut läuft, "
        "erwähne 1 neue Feature das ihn interessieren könnte (Upsell)."
    ),
    "meeting": (
        "Der Interessent will einen Termin buchen. "
        "Gib sofort den Kalender-Link: https://cal.com/aiitec "
        "Bestätige die Buchung und freue dich auf das Gespräch."
    ),
    "general": (
        "Allgemeine/persönliche Antwort auf eine Email die keinem klaren Intent entspricht. "
        "Lies den Email-Inhalt sorgfältig und antworte PASSEND auf die konkrete Frage oder Situation. "
        "Sei menschlich, persönlich, hilfreich. "
        "Falls es sich um eine rein persönliche Email handelt (kein Verkaufsgespräch nötig), "
        "antworte entsprechend freundlich ohne Sales-Pitch. "
        "Erwähne die kostenlose Demo nur wenn es thematisch passt."
    ),
}

_REPLY_PLACEHOLDER_RE = re.compile(
    r'\[(?:Name|Produkt|Link|URL|Firma|Company|INSERT|PLATZHALTER)[^\]]*\]'
    r'|\{[a-z_]+\}(?!\d)'      # unersetztes {variable}
    r'|\{\{[^}]+\}\}'          # unersetztes {{variable}}
    r'|als\s+ki[- ]sprachmodell'
    r'|ich\s+bin\s+(eine\s+)?ki\b',
    re.IGNORECASE,
)
_FAKE_URL_RE = re.compile(
    r'example\.com|yoursite|buy\.stripe\.com/starter\b|'
    r'bullpower-hub\.vercel\.app|localhost|127\.0\.0\.1',
    re.IGNORECASE,
)


def _validate_email_reply(text: str) -> tuple[bool, str]:
    """Prüft ob eine generierte Email-Antwort sendbar ist."""
    if not text or len(text.strip()) < 40:
        return False, "zu kurz"
    if len(text) > 3000:
        return False, "zu lang"
    m = _REPLY_PLACEHOLDER_RE.search(text)
    if m:
        return False, f"Platzhalter gefunden: {m.group()!r}"
    m = _FAKE_URL_RE.search(text)
    if m:
        return False, f"Ungültige URL: {m.group()!r}"
    if text.count("{") > 2 or text.count("[") > 3:
        return False, "zu viele unbearbeitete Klammern"
    return True, ""


async def generate_reply(incoming_email: str, company: str,
                          intent: str, thread_history: str = "") -> str:
    """Claude generiert lebhafte, personalisierte Antwort — mit Qualitätsprüfung."""
    from modules.ai_client import ai_complete
    intent_instruction = INTENT_PROMPTS.get(intent, INTENT_PROMPTS["general"])
    ctx = f"\nKonversationsverlauf:\n{thread_history}\n" if thread_history else ""
    prompt = (
        f"Eingehende Email von {company or 'einem Interessenten'}:\n"
        f"---\n{incoming_email[:1000]}\n---\n"
        f"{ctx}\n"
        f"Erkannter Intent: {intent}\n\n"
        f"Aufgabe: {intent_instruction}\n\n"
        f"WICHTIG: Keine Platzhalter wie [Name] oder {{variable}} verwenden. "
        f"Verwende echte Links aus dem System-Prompt. Endet immer mit der Signatur."
    )
    for attempt in range(2):
        text = await ai_complete(prompt, system=KONVERSATIONS_SYSTEM, max_tokens=350)
        if text:
            text = text.strip()
            ok, reason = _validate_email_reply(text)
            if ok:
                return text
            log.warning("Email-Reply Qualitätsfehler (Versuch %d): %s", attempt + 1, reason)

    # Sicheres Fallback-Template
    cal_link = "https://cal.com/aiitec"
    return (
        f"Vielen Dank für Ihre Nachricht!\n\n"
        f"Ich freue mich über Ihr Interesse und melde mich in Kürze persönlich bei Ihnen.\n\n"
        f"Falls Sie sofort starten möchten, buchen Sie hier direkt einen 15-Minuten-Call:\n"
        f"{cal_link}\n\n"
        f"Mit freundlichen Grüßen,\n"
        f"Rudolf Sarkany | AiiteC – KI-Automatisierung für E-Commerce"
    )

# ── Gmail IMAP Reader ─────────────────────────────────────────────────────────
def _decode_header_str(h: str) -> str:
    parts = decode_header(h or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)

def _extract_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    # Quoted-Text entfernen (>-Zeilen)
    lines = [l for l in body.splitlines() if not l.startswith(">") and l.strip()]
    return "\n".join(lines[:30])

def _fetch_inbox_replies(account: Dict, since_hours: int = 1) -> List[Dict]:
    """Liest neue Antworten aus Gmail via IMAP."""
    replies = []
    user = account.get("user", "")
    pw   = account.get("pass", "")
    if not user or not pw:
        return replies
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, pw)
        mail.select("INBOX")
        since = (datetime.now() - timedelta(hours=since_hours)).strftime("%d-%b-%Y")
        _, nums = mail.search(None, f'(UNSEEN SINCE "{since}")')
        for num in (nums[0].split() or [])[-50:]:
            _, data = mail.fetch(num, "(RFC822)")
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)
            from_addr = _decode_header_str(msg.get("From", ""))
            subject   = _decode_header_str(msg.get("Subject", ""))
            msg_id    = msg.get("Message-ID", "")
            in_reply   = msg.get("In-Reply-To", "")
            body      = _extract_body(msg)
            email_match = re.search(r'[\w._%+\-]+@[\w.\-]+\.\w{2,}', from_addr)
            from_email  = email_match.group(0).lower() if email_match else from_addr
            if not body or len(body) < 3:
                continue
            # Eigene Emails überspringen
            if any(acc["user"] in from_email for acc in GMAIL_ACCOUNTS):
                continue
            # ── NUR echte persönliche Antworten beantworten ──────────────
            # REGEL: Nur antworten wenn ECHTE Person schreibt
            # NICHT antworten: Newsletter, System, Marketing, Bestätigungen
            _dom = from_email.split("@")[-1] if "@" in from_email else ""
            _loc = from_email.split("@")[0]  if "@" in from_email else ""

            # Blockierte Domains (Systeme, Automations, Plattformen)
            _BLOCK_DOMAINS = {
                # Plattform-Systeme
                "github.com", "github.io", "noreply.github.com",
                "facebookmail.com", "accounts.google.com", "google.com",
                "bounce.twitter.com", "smtp.linkedin.com",
                "stripe.com", "shopify.com", "shopifyemail.com",
                "klaviyo.com", "sendgrid.net", "mailchimp.com",
                "beehiiv.com", "substack.com", "convertkit.com",
                "googlemail.com", "googlegroups.com",
                "bounces.amazon.com", "amazonses.com",
                "railway.app", "vercel.com", "netlify.com",
                "joonix.net", "storebotmail.joonix.net",
                # Marketing & Massen-Dienste
                "mailjet.com", "sparkpost.com", "postmarkapp.com",
                "sendpulse.com", "activecampaign.com", "getresponse.com",
                "aweber.com", "constantcontact.com", "hubspot.com",
                "intercom.io", "zendesk.com", "freshdesk.com",
                "salesforce.com", "mailerlite.com", "brevo.com",
                # Digistore/Affiliate
                "digistore24.com", "checkout-ds24.com", "ds24.com",
                "clickbank.com", "jvzoo.com", "warrior.com",
                # Payment-Benachrichtigungen
                "paypal.com", "payoneer.com", "wise.com", "klarna.com",
            }

            # Blockierte Absender-Prefixes (automatische Adressen)
            _BLOCK_PREFIXES = (
                "noreply", "no-reply", "no.reply", "donotreply", "do-not-reply",
                "do_not_reply", "not-reply",
                "mailer-daemon", "postmaster", "bounce", "bounces", "bounce+",
                "notification", "notifications", "notify",
                "newsletter", "news", "updates", "update",
                "alert", "alerts", "alarm",
                "system", "daemon", "robot", "bot", "auto",
                "bulk", "automated", "automation",
                "marketing", "promo", "promotion", "sales-",
                "billing", "invoice", "receipt", "order",
                "confirmation", "confirm", "verify", "verification",
                "welcome", "onboarding", "signup",
                "unsubscribe", "optout",
                "admin@", "webmaster", "hostmaster",
                "delivery", "tracking", "shipping",
            )

            # Subject-Keywords die auf Auto-Mails hinweisen (NICHT antworten)
            _BLOCK_SUBJECTS = (
                "unsubscribe", "newsletter", "automated", "do not reply",
                "autoresponder", "out of office", "vacation", "abwesenheit",
                "delivery failed", "delivery status", "bounced",
                "invoice", "rechnung", "order confirmation", "bestellbestätigung",
                "receipt", "quittung", "payment confirmation", "zahlung",
                "welcome to", "willkommen bei", "account created",
                "password reset", "passwort", "verify your",
                "your subscription", "trial", "upgrade your",
                "security alert", "login attempt", "new sign",
            )

            _subj_lower = subject.lower()
            if any(kw in _subj_lower for kw in _BLOCK_SUBJECTS):
                log.debug("  [SKIP-SUBJECT] %s | %s", from_email, subject[:50])
                continue

            if _dom in _BLOCK_DOMAINS or any(_loc.startswith(p) for p in _BLOCK_PREFIXES):
                log.debug("  [SKIP-SYSTEM] %s", from_email)
                continue

            # X-Mailer / List-Unsubscribe Header → Massen-Email → nicht antworten
            if msg.get("List-Unsubscribe") or msg.get("List-ID"):
                log.debug("  [SKIP-BULK] %s (List-* header)", from_email)
                continue
            if msg.get("X-Mailer", "").lower() in (
                "mailchimp", "klaviyo", "sendgrid", "hubspot",
                "activecampaign", "brevo", "mailerlite",
            ):
                log.debug("  [SKIP-MAILER] %s", from_email)
                continue
            replies.append({
                "account":    user,
                "from_email": from_email,
                "from_name":  re.sub(r'<.*>', '', from_addr).strip().strip('"'),
                "subject":    subject,
                "body":       body,
                "msg_id":     msg_id,
                "thread_ref": in_reply,
                "imap_num":   num,
            })
        mail.logout()
    except Exception as e:
        log.warning("IMAP error (%s): %s", user, e)
    return replies

# ── Email senden ──────────────────────────────────────────────────────────────
def _send_reply(account: Dict, to_email: str, subject: str,
                body: str, in_reply_to: str = "") -> bool:
    user = account["user"]
    pw   = account["pass"]
    name = account.get("name", "Rudolf Sarkany | AiiteC")
    if not pw:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = subject if subject.startswith("Re:") else f"Re: {subject}"
        msg["From"]     = f"{name} <{user}>"
        msg["To"]       = to_email
        msg["Reply-To"] = user
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"]  = in_reply_to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, pw)
            s.sendmail(user, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.error("Reply send error (%s → %s): %s", user, to_email, e)
        return False

# ── Konversations-Verarbeitungs-Loop ─────────────────────────────────────────
async def process_all_inboxes(since_hours: int = 1) -> Dict:
    """Liest alle Postfächer, beantwortet alle neuen Replies."""
    init_db()
    total_replies  = 0
    total_answered = 0
    unsubscribes   = 0

    for account in GMAIL_ACCOUNTS:
        if not account.get("pass"):
            continue
        replies = _fetch_inbox_replies(account, since_hours)
        log.info("📥 %s: %d neue Antworten", account["user"], len(replies))

        for reply in replies:
            total_replies += 1
            from_email = reply["from_email"]
            body       = reply["body"]
            subject    = reply["subject"]
            company    = reply["from_name"] or from_email.split("@")[0]
            thread_id  = reply["thread_ref"] or reply["msg_id"]

            # ── Private / Spam / System Emails sofort überspringen ──────────────
            try:
                from modules.email_validator import classify_incoming_email
                email_class = classify_incoming_email(from_email, subject, body)
            except Exception:
                email_class = "business"

            if email_class == "private":
                log.info("  [PRIVATE] %s — kein Auto-Reply (Rudolf manuell!)", from_email)
                await _tg_notify_block(
                    from_email, company, "private",
                    "Private Email erkannt — kein Auto-Reply. Bitte manuell beantworten!"
                )
                continue
            if email_class in ("spam", "inkasso"):
                if email_class == "inkasso":
                    await _tg_notify_block(
                        from_email, company, "inkasso",
                        "⚠️ INKASSO/RECHTLICH erkannt — Rudolf manuell beantworten!"
                    )
                log.info("  [%s] %s — übersprungen", email_class.upper(), from_email)
                continue
            if email_class == "unsubscribe":
                log.info("  [UNSUBSCRIBE] %s", from_email)
                try:
                    from modules.mass_outreach_1000 import handle_unsubscribe
                    handle_unsubscribe(from_email)
                except Exception:
                    pass
                continue

            intent = classify_intent(body)
            log.info("  → %s | Intent: %s", from_email, intent)

            # Thread-History laden
            thread_history = ""
            with _db() as db:
                thread = db.execute(
                    "SELECT * FROM threads WHERE from_email=?", (from_email,)
                ).fetchone()
                if thread:
                    msgs = db.execute(
                        "SELECT direction, body FROM messages "
                        "WHERE thread_id=? ORDER BY sent_at DESC LIMIT 4",
                        (thread["thread_id"],)
                    ).fetchall()
                    thread_history = "\n".join(
                        f"{'Wir' if m['direction']=='out' else 'Kunde'}: {m['body'][:200]}"
                        for m in reversed(msgs)
                    )

            # Antwort generieren
            ai_reply = await generate_reply(body, company, intent, thread_history)

            # Finale Qualitätsprüfung vor dem Senden (5-Layer)
            reply_ok, reply_err = _validate_email_reply(ai_reply)
            if not reply_ok:
                log.error("Email-Reply L1 BLOCKIERT [%s]: %s | Reply: %s...",
                          from_email, reply_err, ai_reply[:80])
                await _tg_notify_block(from_email, company, intent, reply_err)
                continue
            # Erweiterte 5-Layer Prüfung via email_validator
            try:
                from modules.email_validator import validate_email_content
                adv_ok, adv_reason = await validate_email_content(
                    subject=f"Re: {subject}",
                    body=ai_reply,
                    recipient=from_email,
                    require_signature=True,
                )
                if not adv_ok:
                    log.error("Email-Reply VALIDATOR-BLOCK [%s]: %s", from_email, adv_reason)
                    await _tg_notify_block(from_email, company, intent, adv_reason)
                    continue
            except Exception as ev:
                log.error("email_validator Fehler — BLOCK: %s", ev)
                await _tg_notify_block(from_email, company, intent, f"validator_error: {ev}")
                continue

            # Unsubscribe verarbeiten
            if intent == "unsubscribe":
                unsubscribes += 1
                try:
                    from modules.mass_outreach_1000 import handle_unsubscribe
                    handle_unsubscribe(from_email)
                except Exception:
                    pass

            # Telefonnummer erkennen → Sofia-Queue
            if intent == "call_request":
                phone_match = re.search(r'(\+?\d[\d\s\-()]{7,15}\d)', body)
                if phone_match:
                    phone = re.sub(r'[\s\-()]', '', phone_match.group(1))
                    try:
                        from modules.phone_ai_assistant import add_to_outbound_queue
                        add_to_outbound_queue(phone, company, "Default", from_email)
                        log.info("📞 Sofia-Queue: %s", phone)
                    except Exception:
                        pass

            # Blocklist-Check vor dem Senden
            try:
                from modules.bounce_watcher import is_blocked
                if is_blocked(from_email):
                    log.info("BounceBlocklist: kein Reply an %s (gebounced)", from_email)
                    continue
            except Exception:
                pass

            # Antwort senden
            sent = await asyncio.to_thread(_send_reply, account, from_email, subject, ai_reply,
                                reply["msg_id"])
            if sent:
                total_answered += 1
                # Konversion tracken
                converted = 1 if intent in ("start_now", "meeting") else 0
                with _db() as db:
                    db.execute("""
                        INSERT OR IGNORE INTO threads
                        (thread_id, from_email, company, account, intent, stage, last_reply)
                        VALUES (?,?,?,?,?,?,datetime('now'))
                    """, (thread_id, from_email, company, account["user"],
                           intent, intent))
                    db.execute("""
                        UPDATE threads SET intent=?, last_sent=datetime('now'),
                        reply_count=reply_count+1, converted=MAX(converted,?)
                        WHERE from_email=?
                    """, (intent, converted, from_email))
                    db.execute(
                        "INSERT INTO messages (thread_id, direction, subject, body) "
                        "VALUES (?,?,?,?)",
                        (thread_id, "in", subject, body[:2000])
                    )
                    db.execute(
                        "INSERT INTO messages (thread_id, direction, subject, body) "
                        "VALUES (?,?,?,?)",
                        (thread_id, "out", f"Re: {subject}", ai_reply[:2000])
                    )
                log.info("  ✅ Geantwortet → %s (Intent: %s)", from_email, intent)
                await _tg_notify(from_email, company, intent, body[:200], ai_reply[:200])
            await asyncio.sleep(1)

    return {
        "replies_found": total_replies,
        "answered":      total_answered,
        "unsubscribes":  unsubscribes,
    }

# ── Telegram Benachrichtigung ─────────────────────────────────────────────────
async def _tg_notify(from_email: str, company: str,
                      intent: str, incoming: str, reply: str) -> None:
    icons = {
        "interested":   "🟢", "price": "💰", "start_now": "🚀",
        "meeting":      "📅", "call_request": "📞",
        "objection":    "🟡", "how_works": "❓",
        "unsubscribe":  "🔴", "general": "📧",
    }
    icon = icons.get(intent, "📧")
    msg  = (
        f"{icon} <b>Email-Antwort verarbeitet</b>\n"
        f"Von: <b>{company}</b> ({from_email})\n"
        f"Intent: <b>{intent}</b>\n\n"
        f"📩 <i>{incoming[:150]}...</i>\n\n"
        f"🤖 <i>{reply[:150]}...</i>"
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

async def _tg_notify_block(from_email: str, company: str, intent: str, reason: str) -> None:
    """Telegram-Alert wenn Email-Antwort blockiert wird."""
    msg = (
        f"⛔ <b>Email-Antwort BLOCKIERT</b>\n"
        f"Von: <b>{company}</b> ({from_email})\n"
        f"Intent: <b>{intent}</b>\n"
        f"Grund: <code>{reason}</code>\n\n"
        f"<i>Bitte manuell beantworten!</i>"
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


# ── Stats ─────────────────────────────────────────────────────────────────────
def get_stats() -> Dict:
    init_db()
    with _db() as db:
        total    = db.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        today    = db.execute(
            "SELECT COUNT(*) FROM threads WHERE last_sent > date('now')"
        ).fetchone()[0]
        by_intent = {
            row["intent"]: row["cnt"]
            for row in db.execute(
                "SELECT intent, COUNT(*) as cnt FROM threads GROUP BY intent"
            ).fetchall()
        }
        converted = db.execute(
            "SELECT COUNT(*) FROM threads WHERE converted=1"
        ).fetchone()[0]
    return {
        "threads_total": total, "answered_today": today,
        "converted": converted, "by_intent": by_intent,
    }

# ── Watchdog: Fehler-Erkennung + Telegram-Alert ───────────────────────────────
async def _watchdog_alert(error_msg: str) -> None:
    """Sendet Alarm via Telegram wenn etwas schief läuft."""
    msg = (
        f"⚠️ <b>Email-KI Fehler</b>\n"
        f"{error_msg}\n\n"
        f"Bitte prüfen: railway logs oder IMAP-Verbindung."
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

# ── Scheduler-Task ────────────────────────────────────────────────────────────
async def run_email_ai_cycle() -> str:
    """Läuft alle 10 Minuten. Beantwortet nur echte persönliche Emails."""
    try:
        result = await process_all_inboxes(since_hours=1)
        answered = result['answered']
        found    = result['replies_found']

        # Watchdog: wenn viele gefunden aber nichts beantwortet → Alarm
        if found > 5 and answered == 0:
            await _watchdog_alert(
                f"⚠️ {found} Emails gefunden aber 0 beantwortet!\n"
                f"Möglicher Fehler: Gmail App-Passwort abgelaufen oder KI-API nicht erreichbar."
            )

        return (
            f"Email-KI: {found} Antworten gefunden, "
            f"{answered} beantwortet, "
            f"{result['unsubscribes']} abgemeldet ✅"
        )
    except Exception as e:
        err = f"Email-KI Crash: {e}"
        log.error(err)
        await _watchdog_alert(err)
        return f"❌ {err}"

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
                        format="%(asctime)s [EmailAI] %(message)s")
    args = sys.argv[1:]
    if "--run-now" in args:
        r = asyncio.run(process_all_inboxes(since_hours=24))
        print(json.dumps(r, indent=2))
    elif "--stats" in args:
        print(json.dumps(get_stats(), indent=2, ensure_ascii=False))
    else:
        print(__doc__)
