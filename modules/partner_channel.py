#!/usr/bin/env python3
"""
SYS-13: Partner Channel & Reseller CRM
=======================================
Verwaltet Partner die über SYS-10 (Bulk Outreach) oder andere Kanäle
zu Resellern werden wollen.

Funktionen:
  - Erkennt Replies aus Gmail die Interesse signalisieren
  - Sendet automatisches Onboarding-Kit
  - Trackt Referrals + Provisionen
  - White-Label Landing Page Generator
  - Monatlicher Provisionsabrechnung-Report (Telegram)
"""
from __future__ import annotations

import asyncio
import imaplib
import email as email_lib
import json
import logging
import os
import re
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PARTNER-CRM] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("PartnerChannel")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "bulk_outreach.db"  # Gleiche DB wie SYS-10

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

GMAIL_USER = os.getenv("GMAIL_USER_5", "aiitecbuuss@gmail.com")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD_5", "rqcd uzim npsl odgw")
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Interesse-Erkennung in Antworten ─────────────────────────────────────────

INTEREST_KEYWORDS = [
    "interessiert", "interesse", "klingt gut", "ja gerne", "mehr informationen",
    "können wir", "call", "gespräch", "meeting", "termin", "wie funktioniert",
    "provision", "reseller", "partner", "weiterleiten", "empfehlen",
    "ja", "bitte", "schicken sie", "further information", "yes", "interested",
]

UNSUBSCRIBE_KEYWORDS = [
    "abmelden", "abbestellen", "kein interesse", "nicht interessiert",
    "bitte keine", "entfernen", "stop", "unsubscribe", "remove",
]

def _classify_reply(body: str) -> str:
    """Klassifiziert eine Reply per KI, Fallback auf Keywords."""
    try:
        from modules.claude_automation import classify
        result = classify(
            body[:800],
            ["interested", "unsubscribe", "other"]
        ).lower().strip()
        if result in ("interested", "unsubscribe", "other"):
            return result
    except Exception:
        pass
    # Keyword-Fallback
    body_lower = body.lower()
    for kw in UNSUBSCRIBE_KEYWORDS:
        if kw in body_lower:
            return "unsubscribe"
    for kw in INTEREST_KEYWORDS:
        if kw in body_lower:
            return "interested"
    return "other"

# ── Onboarding-Kit ────────────────────────────────────────────────────────────

ONBOARDING_KIT = """\
Sehr geehrte Damen und Herren,

vielen Dank für Ihr Interesse am AIITEC Partner-Programm!

Hier ist Ihr Partner-Kit:

── IHR PARTNER-CODE ────────────────────────────────────────────────────────
{partner_code}

Teilen Sie diesen Code mit Ihren Kunden. Jeder Auftrag der mit Ihrem Code
eingeht, bringt Ihnen automatisch 30% Provision.

── SO FUNKTIONIERT ES ──────────────────────────────────────────────────────
1. Kunde bestellt bei uns (Link oder E-Mail) → nennt Ihren Partner-Code
2. Wir liefern den Service in 24-48h
3. Sie erhalten am Monatsende Ihre Provision per Überweisung

── UNSERE SERVICES (ZUM WEITEREMPFEHLEN) ──────────────────────────────────
• Shopify KI-Produktbeschreibungen: 50 Stück → €79 → Ihre Provision: €23,70
  URL: https://monetization-hub-bullpowerhubgits-projects.vercel.app

• eBay/Amazon Listings KI: 100 Listings → €99 → Ihre Provision: €29,70
  URL: https://etsy-gumroad-bullpowerhubgits-projects.vercel.app

• KI-Vertragscheck: pro Vertrag → €129 → Ihre Provision: €38,70
  URL: https://cognitive-symphony-bullpowerhubgits-projects.vercel.app

• Makler Exposé KI: 15 Exposés → €199 → Ihre Provision: €59,70
  URL: https://digifabrik-bullpowerhubgits-projects.vercel.app

• Rechtstexte KI: Impressum+AGB+Datenschutz → €49 → Ihre Provision: €14,70
  URL: https://steuercockpit-bullpowerhubgits-projects.vercel.app

• Social Media KI-Kalender: €69/Monat → Ihre Provision: €20,70/Monat
  URL: https://desktop-tutorial-bullpowerhubgits-projects.vercel.app

• Handwerker Angebots-KI: 30 Angebote → €79 → Ihre Provision: €23,70
  URL: https://hospital-wage-calculator-kpeb-bullpowerhubgits-projects.vercel.app

• EU AI Act Risiko-Radar: ab €299/Report → Ihre Provision: ab €89,70
  URL: https://dist-pi-jet-78.vercel.app

• Hotel & Gastro Texte KI: Website+Zimmer+Menü+10 Bewertungen → €149 → Ihre Provision: €44,70
  URL: https://etsy-gumroad-8zig-bullpowerhubgits-projects.vercel.app

• Stellenanzeigen KI: 10 Inserate → €99 → Ihre Provision: €29,70
  URL: https://digifabrikos-bullpowerhubgits-projects.vercel.app

• Kfz-Händler Fahrzeugtexte KI: 50 Texte → €99 → Ihre Provision: €29,70
  URL: https://digifabrikk-bullpowerhubgits-projects.vercel.app

• Fitness-Studio Content KI: 30 Posts+Newsletter → €69/Monat → Ihre Provision: €20,70/Monat
  URL: https://hospital-wage-calculator-vercel-zzdj-bullpowerhubgits-projects.vercel.app

• Versicherungsmakler Angebots-KI: 20 Briefe+10 Nachfass → €129 → Ihre Provision: €38,70
  URL: https://hospital-wage-calculator-vercel-bullpowerhubgits-projects.vercel.app

• Steuerberater Mandanten-Newsletter KI: €149/Monat → Ihre Provision: €44,70/Monat recurring
  URL: https://telegram-bot-bullpowerhubgits-projects.vercel.app

• Unternehmensverkauf-Exposé KI: 5 M&A-Dokumente → €499 → Ihre Provision: €149,70
  URL: https://gistore-bullpowerhubgits-projects.vercel.app

• Wohnungswirtschaft Mieterbrief KI: unbegrenzte Briefe → €249/Monat → Ihre Provision: €74,70/Monat
  URL: https://gumroad-discord-bullpowerhubgits-projects.vercel.app

── WHITE-LABEL ──────────────────────────────────────────────────────────────
Auf Anfrage erstellen wir Ihnen eine Landing Page mit Ihrem Logo + Ihren
Preisen. Ihre Kunden sehen nur Ihr Unternehmen — wir liefern im Hintergrund.
Einfach antworten: "White-Label gewünscht: [Ihr Unternehmensname]"

── SUPPORT ──────────────────────────────────────────────────────────────────
Fragen? Direkt antworten oder: aiitecbuuss@gmail.com

Wir freuen uns auf die Zusammenarbeit!

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com
"""

def _generate_partner_code(company_name: str) -> str:
    import hashlib
    h = hashlib.md5(company_name.encode()).hexdigest()[:6].upper()
    return f"AIITEC-{h}"

def _send_onboarding_email(to_email: str, partner_code: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Ihr Partner-Kit ist bereit — Code: {partner_code}"
        msg["From"]    = f"Rudolf Sarkany | AIITEC <{GMAIL_USER}>"
        msg["To"]      = to_email
        body = ONBOARDING_KIT.format(partner_code=partner_code)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        log.error(f"Onboarding-Mail Fehler an {to_email}: {e}")
        return False

# ── Gmail IMAP Reply-Scanner ──────────────────────────────────────────────────

def _fetch_replies(since_days: int = 1) -> List[Dict]:
    """Holt neue Replies aus dem aiitecbuuss@gmail.com Postfach."""
    replies = []
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(GMAIL_USER, GMAIL_PASS)
        M.select("INBOX")

        since = (datetime.now().replace(tzinfo=None) - __import__("datetime").timedelta(days=since_days))
        date_str = since.strftime("%d-%b-%Y")
        _, data = M.search(None, f'(SINCE "{date_str}")')

        for num in data[0].split():
            _, msg_data = M.fetch(num, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])
            from_addr = msg.get("From", "")
            subject   = msg.get("Subject", "")

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    pass

            email_match = re.search(r'[\w.\-]+@[\w.\-]+\.[a-z]{2,}', from_addr)
            if email_match:
                replies.append({
                    "from_email": email_match.group(0),
                    "from_name": from_addr.split("<")[0].strip().strip('"'),
                    "subject": subject,
                    "body": body[:2000],
                    "classification": _classify_reply(body),
                })

        M.logout()
    except Exception as e:
        log.error(f"IMAP Fehler: {e}")
    return replies

# ── DB-Operationen ────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _mark_unsubscribed(email: str):
    with _db() as c:
        c.execute("UPDATE bo_outreach SET status='unsubscribed' WHERE email=?", (email,))
        c.execute("UPDATE bo_companies SET segment='UNSUBSCRIBED' WHERE email=?", (email,))

def _mark_replied(email: str):
    now = int(time.time())
    with _db() as c:
        c.execute("UPDATE bo_outreach SET replied_at=?, status='replied' WHERE email=? AND status IN ('sent','followup_sent')", (now, email))

def _add_partner(email: str, name: str, partner_code: str):
    now = int(time.time())
    with _db() as c:
        try:
            co = c.execute("SELECT id FROM bo_companies WHERE email=?", (email,)).fetchone()
            company_id = co["id"] if co else None
            c.execute("""
                INSERT OR IGNORE INTO bo_partners
                    (company_id, email, status, commission_pct, onboarded_at)
                VALUES (?, ?, 'onboarded', 30.0, ?)
            """, (company_id, email, now))
        except Exception as e:
            log.warning(f"Partner-Insert Fehler: {e}")

# ── Provisionsabrechnung ──────────────────────────────────────────────────────

async def send_monthly_commission_report():
    """Sendet monatliche Übersicht an Telegram."""
    with _db() as c:
        partners = c.execute("SELECT * FROM bo_partners WHERE status='onboarded'").fetchall()
        total_referrals = sum(p["total_referrals"] for p in partners)
        total_earned    = sum(p["total_earned"]    for p in partners)

    msg = (
        f"💰 <b>SYS-13 Partner Channel — Monatsbericht</b>\n"
        f"👥 Aktive Partner: {len(partners)}\n"
        f"🎯 Gesamt Referrals: {total_referrals}\n"
        f"💶 Gesamt Provisionen: €{total_earned:.2f}\n"
        f"📋 Partner-Liste im bo_partners SQLite Table"
    )
    if TG_TOKEN and TG_CHAT:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
            )

# ── Hauptschleife ─────────────────────────────────────────────────────────────

async def run_reply_scanner() -> Dict:
    log.info("SYS-13: Scanne Replies...")
    replies = _fetch_replies(since_days=1)
    log.info(f"{len(replies)} Antworten gefunden")

    new_partners   = 0
    unsubscribes   = 0
    other_replies  = 0

    for reply in replies:
        email = reply["from_email"]
        cls   = reply["classification"]
        _mark_replied(email)

        if cls == "unsubscribe":
            _mark_unsubscribed(email)
            unsubscribes += 1
            log.info(f"Abmeldung: {email}")

        elif cls == "interested":
            partner_code = _generate_partner_code(reply["from_name"] or email)
            _add_partner(email, reply["from_name"], partner_code)
            ok = _send_onboarding_email(email, partner_code)
            if ok:
                new_partners += 1
                log.info(f"✅ Neuer Partner: {email} — Code: {partner_code}")
            await asyncio.sleep(5)

        else:
            other_replies += 1
            log.info(f"Antwort (unklassifiziert): {email}")

    if new_partners or unsubscribes:
        token = TG_TOKEN
        chat  = TG_CHAT
        if token and chat:
            msg = (
                f"📬 <b>SYS-13 Reply-Scan</b>\n"
                f"🤝 Neue Partner: {new_partners}\n"
                f"🚫 Abmeldungen: {unsubscribes}\n"
                f"❓ Sonstige: {other_replies}"
            )
            async with aiohttp.ClientSession() as s:
                await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": msg, "parse_mode": "HTML"})

    return {"new_partners": new_partners, "unsubscribes": unsubscribes}


async def main():
    log.info("SYS-13: Partner Channel startet")
    while True:
        try:
            result = await run_reply_scanner()
            log.info(f"Reply-Scan: {result}")
        except Exception as e:
            log.error(f"Fehler: {e}")
        await asyncio.sleep(3600)  # Stündlich prüfen


if __name__ == "__main__":
    asyncio.run(main())
