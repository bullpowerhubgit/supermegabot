#!/usr/bin/env python3
"""
Email Auto-Responder — Business-E-Mails automatisch bearbeiten
==============================================================
Läuft zusammen mit email_inbox_monitor (alle 5 Minuten).
Reagiert NUR auf echte Geschäftsmails — keine Newsletter, kein Spam.

Kategorien die automatisch beantwortet werden:
  - bestellung / Kundenanfrage zu Bestellungen → Bestellnummer anfordern
  - anfrage / Interesse an Services → Service-Übersicht + Termin
  - outreach_reply / Antwort auf unsere Outreach-Mails → Follow-Up
  - compliance_anfrage / Frage zu unseren Compliance-Tools → Angebot
  - mahnung / Inkasso → Draft erstellen + Telegram-Alert
  - bewerbung / Job-Anfrage → Standard-Ablehnung oder Interesse
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiohttp

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "auto_responder.db"
BASE_URL  = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://supermegabot-production.up.railway.app")
SHOP_URL  = os.getenv("SHOP_URL", "https://ineedit.com.co")

# ── Was ist ein Geschäfts-E-Mail? ─────────────────────────────────────────────

# Sender-Domains/Muster die NIEMALS auto-beantwortet werden
_SKIP_SENDERS = [
    "noreply", "no-reply", "mailer-daemon", "newsletter", "donotreply",
    "notifications@github", "notify@", "alerts@", "automated@",
    "@ebay", "@amazon", "@etoro", "@kraken", "@paypal", "@stripe",
    "@trustpilot", "@tor-project", "@postman", "@lists.", "digest@",
    "service@faircollect",  # Inkasso separat behandelt
]

# Signale die auf eine echte Geschäfts-E-Mail hindeuten
_BUSINESS_SIGNALS = {
    "bestellung": [
        "bestellung", "order", "meine bestellung", "my order", "bestell",
        "lieferung", "delivery", "tracking", "versand", "ship",
        "rechnung", "invoice", "rücksendung", "return", "refund", "rückgabe",
        "fulfill", "fulfilled",
    ],
    "service_anfrage": [
        "anfrage", "inquiry", "interest", "angebot", "quote", "preise",
        "pricing", "kosten", "zusammenarbeit", "kooperation", "partnership",
        "beauftragen", "hire", "buchen", "booking", "demo", "termin",
        "would like", "ich möchte", "können sie", "can you",
    ],
    "compliance_anfrage": [
        "gpsr", "ai act", "e-rechnung", "nis2", "cra", "bfsg", "ppwr", "eudr",
        "compliance", "dsgvo", "gdpr", "zertifizierung", "audit", "prüfung",
        "kanzlei", "steuerberater", "zwangsversteigerung", "zvg",
    ],
    "outreach_reply": [
        "re:", "aw:", "re :","antw:", "auf ihre", "zu ihrer nachricht",
        "danke für", "thank you for", "bezüglich ihrer", "regarding your",
        "ihre anfrage", "ihre email", "your email", "your message",
    ],
    "mahnung": [
        "mahnung", "mahnverfahren", "forderung", "inkasso", "zahlung ausstehend",
        "zahlungsaufforderung", "schuldner", "faircollect", "creditreform",
        "collection", "overdue", "past due",
    ],
    "bewerbung": [
        "bewerbung", "application", "lebenslauf", "cv", "resume",
        "stelle", "position", "job", "karriere", "career",
    ],
}

# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auto_responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email_uid   TEXT UNIQUE,
            sender      TEXT,
            subject     TEXT,
            category    TEXT,
            action      TEXT,
            response_sent INTEGER DEFAULT 0,
            processed_at  INTEGER
        )
    """)
    conn.commit()
    return conn


# ── Klassifizierung ───────────────────────────────────────────────────────────

def _is_business_email(sender: str, subject: str) -> bool:
    """Prüft ob eine E-Mail überhaupt eine Geschäfts-E-Mail ist."""
    sender_l = sender.lower()
    if any(skip in sender_l for skip in _SKIP_SENDERS):
        return False
    text = (sender + " " + subject).lower()
    return any(
        any(sig in text for sig in signals)
        for signals in _BUSINESS_SIGNALS.values()
    )


def _classify(sender: str, subject: str, snippet: str = "") -> Optional[str]:
    """Gibt die Business-Kategorie zurück oder None wenn nicht Geschäftlich."""
    if not _is_business_email(sender, subject):
        return None
    text = (sender + " " + subject + " " + snippet).lower()
    for cat, signals in _BUSINESS_SIGNALS.items():
        if any(sig in text for sig in signals):
            return cat
    return None


# ── E-Mail senden (SMTP) ──────────────────────────────────────────────────────

def _send_reply(to_email: str, subject: str, body: str,
                reply_subject: str = "") -> bool:
    smtp_user = os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
    smtp_pass = os.getenv("GMAIL_APP_PASSWORD_AIITEC", "")
    if not smtp_pass:
        log.warning("GMAIL_APP_PASSWORD_AIITEC fehlt — kein Auto-Reply")
        return False

    reply_subj = reply_subject or (
        f"Re: {subject}" if not subject.startswith("Re:") else subject
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = f"AiiteC Support <{smtp_user}>"
    msg["To"]      = to_email
    msg["Subject"] = reply_subj

    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [to_email], msg.as_string())
        log.info("Auto-Reply gesendet → %s [%s]", to_email, reply_subj)
        return True
    except Exception as e:
        log.error("SMTP Auto-Reply Fehler: %s", e)
        return False


# ── Telegram Alert ────────────────────────────────────────────────────────────

async def _tg(text: str, session: aiohttp.ClientSession):
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        await session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10),
        )
    except Exception as e:
        log.warning("Telegram Alert Fehler: %s", e)


# ── Antwort-Templates ─────────────────────────────────────────────────────────

def _reply_bestellung(sender: str, subject: str) -> str:
    return f"""Vielen Dank für Ihre Nachricht!

Wir haben Ihre Anfrage erhalten und kümmern uns darum.

Damit wir Ihre Bestellung schnellstmöglich bearbeiten können, teilen Sie uns bitte Folgendes mit:
• Ihre Bestellnummer (zu finden in Ihrer Bestellbestätigung)
• Eine kurze Beschreibung Ihres Anliegens

Shop: {SHOP_URL}
Bestellungen werden werktags innerhalb von 24h bearbeitet.

Mit freundlichen Grüßen
AiiteC Support Team
aiitecbuuss@gmail.com"""


def _reply_service_anfrage(sender: str, subject: str) -> str:
    return f"""Vielen Dank für Ihr Interesse!

Wir freuen uns über Ihre Anfrage und melden uns binnen 24 Stunden mit einem individuellen Angebot.

Unsere Services im Überblick:
• KI-Mitarbeiter-Leasing (ab €300/Monat) — vollautonome KI-Agenten für Ihr Unternehmen
• EU AI Act Compliance-Paket (ab €199) — GPSR, NIS2, E-Rechnung, HR-KI
• Shopify-Automatisierung & E-Commerce KI
• Telegram-Bot-Manufaktur (€490 einmalig + €49/Monat)

Alle Services: {BASE_URL}/compliance

Für dringende Anfragen: aiitecbuuss@gmail.com

Mit freundlichen Grüßen
Rudolf Sarkany — AiiteC
{BASE_URL}"""


def _reply_compliance_anfrage(sender: str, subject: str) -> str:
    # Welches Tool ist gemeint?
    text = (subject).lower()
    tool = "Compliance-Tool"
    url  = f"{BASE_URL}/compliance"
    if "gpsr" in text:
        tool, url = "GPSR Shop-Shield", f"{BASE_URL}/gpsr"
    elif "e-rechnung" in text or "erechnung" in text:
        tool, url = "E-Rechnungs-Autopilot", f"{BASE_URL}/e-rechnung"
    elif "nis2" in text:
        tool, url = "NIS2 KMU-Check", f"{BASE_URL}/nis2"
    elif "ai act" in text or "aiact" in text or "hr-ki" in text:
        tool, url = "HR-KI Hochrisiko-Audit (AI Act)", f"{BASE_URL}/hr-ki-audit"
    elif "bfsg" in text:
        tool, url = "BFSG Barriere-Scanner", f"{BASE_URL}/bfsg"
    elif "zvg" in text or "zwangsversteigerung" in text:
        tool, url = "ZVG Exposé-Engine", f"{BASE_URL}/zvg"
    elif "kanzlei" in text:
        tool, url = "Kanzlei-Mandanten-Radar", f"{BASE_URL}/kanzlei-radar"

    return f"""Vielen Dank für Ihre Anfrage zu unserem {tool}!

Wir haben Ihre Nachricht erhalten und erstellen Ihnen innerhalb von 24 Stunden ein individuelles Angebot.

Mehr Informationen zum {tool}: {url}

⚡ AI Act Frist: 02.08.2026 — noch ca. 20 Tage!
Alle unsere Compliance-Tools helfen Ihnen, gesetzeskonform zu bleiben und Bußgelder zu vermeiden.

Mit freundlichen Grüßen
Rudolf Sarkany — AiiteC
aiitecbuuss@gmail.com | {BASE_URL}"""


def _reply_outreach_reply(sender: str, subject: str) -> str:
    return f"""Vielen Dank für Ihre Rückmeldung!

Wir freuen uns über Ihr Interesse und melden uns persönlich innerhalb von 24 Stunden bei Ihnen.

Falls Sie sofort mehr erfahren möchten:
→ {BASE_URL}/compliance

Mit freundlichen Grüßen
Rudolf Sarkany — AiiteC
aiitecbuuss@gmail.com"""


def _body_for_category(cat: str, sender: str, subject: str) -> Optional[str]:
    """Gibt den E-Mail-Body für eine Kategorie zurück. None = nicht auto-antworten."""
    if cat == "bestellung":
        return _reply_bestellung(sender, subject)
    if cat == "service_anfrage":
        return _reply_service_anfrage(sender, subject)
    if cat == "compliance_anfrage":
        return _reply_compliance_anfrage(sender, subject)
    if cat == "outreach_reply":
        return _reply_outreach_reply(sender, subject)
    # mahnung und bewerbung → kein Auto-Reply, nur Telegram-Alert + Draft-Flag
    return None


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

async def run_auto_responder(emails: List[Dict]) -> Dict:
    """
    Verarbeitet eine Liste neuer E-Mails (aus email_inbox_monitor).
    Beantwortet nur echte Geschäftsmails automatisch.

    emails: [{"uid", "account", "sender", "subject", "category", ...}]
    """
    conn = _db()
    replied = 0
    alerted = 0
    skipped = 0
    errors  = 0

    alert_lines: List[str] = []

    async with aiohttp.ClientSession() as session:
        for email in emails:
            uid     = email.get("uid", "")
            sender  = email.get("sender", "")
            subject = email.get("subject", "")
            snippet = email.get("snippet", "")

            # Schon verarbeitet?
            already = conn.execute(
                "SELECT id FROM auto_responses WHERE email_uid=?", (uid,)
            ).fetchone()
            if already:
                continue

            # Business-Klassifizierung
            cat = _classify(sender, subject, snippet)

            conn.execute(
                "INSERT OR IGNORE INTO auto_responses "
                "(email_uid, sender, subject, category, action, processed_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, sender[:200], subject[:300], cat or "non-business", "pending", int(time.time()))
            )
            conn.commit()

            if not cat:
                skipped += 1
                continue

            # Mahnverfahren → Telegram-Alert + kein Auto-Reply (Zahlungsentscheidung beim Menschen)
            if cat == "mahnung":
                alert_lines.append(
                    f"🚨 *MAHNUNG erhalten*\nVon: {sender}\nBetreff: {subject}\n"
                    f"→ Sofort prüfen! Draft-Antwort im Postfach."
                )
                conn.execute(
                    "UPDATE auto_responses SET action='alerted' WHERE email_uid=?", (uid,)
                )
                conn.commit()
                alerted += 1
                continue

            # Bewerbung → Telegram-Alert, kein Auto-Reply
            if cat == "bewerbung":
                alert_lines.append(
                    f"📄 *Bewerbung eingegangen*\nVon: {sender}\nBetreff: {subject}"
                )
                conn.execute(
                    "UPDATE auto_responses SET action='alerted' WHERE email_uid=?", (uid,)
                )
                conn.commit()
                alerted += 1
                continue

            # Alle anderen Geschäftsmails → Auto-Reply
            body = _body_for_category(cat, sender, subject)
            if not body:
                skipped += 1
                continue

            # E-Mail-Adresse aus Sender extrahieren
            m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", sender)
            if not m:
                skipped += 1
                continue
            to_addr = m.group(0)

            ok = _send_reply(to_addr, subject, body)
            action = "replied" if ok else "reply_failed"
            conn.execute(
                "UPDATE auto_responses SET action=?, response_sent=? WHERE email_uid=?",
                (action, 1 if ok else 0, uid)
            )
            conn.commit()

            if ok:
                replied += 1
                alert_lines.append(
                    f"📬 *Auto-Reply gesendet* [{cat}]\nAn: {to_addr}\nBetreff: {subject[:60]}"
                )
            else:
                errors += 1

        # Sammelt-Alert wenn etwas passiert ist
        if alert_lines:
            text = "🤖 *Auto-Responder Report*\n\n" + "\n\n".join(alert_lines)
            await _tg(text, session)

    conn.close()
    log.info(
        "Auto-Responder: %d beantwortet | %d alerted | %d übersprungen | %d Fehler",
        replied, alerted, skipped, errors
    )
    return {
        "ok":      True,
        "replied": replied,
        "alerted": alerted,
        "skipped": skipped,
        "errors":  errors,
    }


async def get_responder_log(limit: int = 50) -> List[Dict]:
    """Letzte Auto-Response-Aktionen für Dashboard."""
    conn = _db()
    rows = conn.execute(
        "SELECT email_uid, sender, subject, category, action, processed_at "
        "FROM auto_responses ORDER BY processed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {"uid": r[0], "sender": r[1], "subject": r[2],
         "category": r[3], "action": r[4], "ts": r[5]}
        for r in rows
    ]
