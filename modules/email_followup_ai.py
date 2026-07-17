"""
email_followup_ai.py — KI-gestützte Email Follow-Up Sequenz
============================================================
Generiert personalisierte Follow-Up Emails mit Claude/AI via ai_complete().
Erkennt Antworten via IMAP → stoppt Sequenz automatisch.
Erstellt HMAC-basierte Abmelde-Tokens pro Lead.

Verwendung:
  from modules.email_followup_ai import run_ai_followup_cycle, check_replies, generate_followup_email
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import imaplib
import json
import logging
import os
import random
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

log = logging.getLogger("EmailFollowupAI")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "followup_ai.db"

# ── Konfiguration ─────────────────────────────────────────────────────────────

FOLLOWUP_STEPS = [
    {"step": 1, "delay_days": 7,  "tone": "friendly"},
    {"step": 2, "delay_days": 14, "tone": "value_focused"},
    {"step": 3, "delay_days": 21, "tone": "breakup"},
]

_UNSUBSCRIBE_SECRET = os.getenv("EMAIL_UNSUBSCRIBE_SECRET", "smb-unsub-2026-secret")
_BASE_URL           = os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

# SMTP-Pool: bevorzugt SMTP_*, Fallback auf Gmail-Accounts
def _smtp_pool() -> list[dict]:
    accounts = []
    for i in range(1, 9):
        user = os.getenv(f"GMAIL_USER_{i}", "")
        pw   = os.getenv(f"GMAIL_APP_PASSWORD_{i}", "")
        if user and pw:
            accounts.append({"user": user, "password": pw, "host": "smtp.gmail.com", "port": 465, "ssl": True})
    # Custom SMTP (z.B. Mailjet/SendGrid)
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_host = os.getenv("SMTP_HOST", "")
    if smtp_user and smtp_pass and smtp_host:
        accounts.insert(0, {
            "user": smtp_user, "password": smtp_pass,
            "host": smtp_host, "port": int(os.getenv("SMTP_PORT", "587")), "ssl": False,
        })
    return accounts or [{"user": os.getenv("GMAIL_USER_5", "aiitecbuuss@gmail.com"),
                         "password": os.getenv("GMAIL_APP_PASSWORD_5", ""),
                         "host": "smtp.gmail.com", "port": 465, "ssl": True}]


def _imap_accounts() -> list[dict]:
    """Gibt IMAP-Accounts zurück für Reply-Detection."""
    accounts = []
    for i in range(1, 9):
        user = os.getenv(f"GMAIL_USER_{i}", "")
        pw   = os.getenv(f"GMAIL_APP_PASSWORD_{i}", "")
        if user and pw and "gmail" in user:
            accounts.append({"user": user, "password": pw, "host": "imap.gmail.com"})
    return accounts


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS followup_leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            company       TEXT,
            first_name    TEXT,
            segment       TEXT,
            service_fit   TEXT,
            source        TEXT DEFAULT 'manual',
            enrolled_at   REAL,
            replied_at    REAL,
            unsubscribed  INTEGER DEFAULT 0,
            unsubscribed_at REAL,
            notes         TEXT
        );
        CREATE TABLE IF NOT EXISTS followup_queue (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_email    TEXT NOT NULL,
            step          INTEGER NOT NULL,
            scheduled_at  REAL NOT NULL,
            sent_at       REAL,
            status        TEXT DEFAULT 'pending',
            subject       TEXT,
            body_preview  TEXT
        );
        CREATE TABLE IF NOT EXISTS followup_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_email  TEXT,
            step        INTEGER,
            subject     TEXT,
            sent_at     REAL,
            error       TEXT,
            ai_generated INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_fq_pending
            ON followup_queue (status, scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_fq_email
            ON followup_queue (lead_email);
    """)
    conn.commit()
    return conn


# ── Unsubscribe-Tokens ────────────────────────────────────────────────────────

def generate_unsub_token(email: str) -> str:
    """Erstellt HMAC-SHA256 Token für sicheres Abmelden."""
    msg = f"{email}:{_UNSUBSCRIBE_SECRET}".encode()
    return hmac.new(_UNSUBSCRIBE_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]


def verify_unsub_token(email: str, token: str) -> bool:
    """Prüft Abmelde-Token."""
    expected = generate_unsub_token(email)
    return hmac.compare_digest(expected, token)


def unsubscribe_link(email: str) -> str:
    token = generate_unsub_token(email)
    return f"{_BASE_URL}/api/email/unsubscribe?email={email}&token={token}"


# ── KI-Generierung ────────────────────────────────────────────────────────────

async def generate_followup_email(
    email: str,
    company: str,
    first_name: str,
    segment: str,
    service_fit: str,
    step: int,
    tone: str,
    prior_sends: int = 1,
) -> tuple[str, str]:
    """
    Generiert KI-personalisierten Follow-Up via ai_complete().
    Gibt (subject, body) zurück.
    Fallback auf statisches Template wenn KI nicht verfügbar.
    """
    from modules.ai_client import ai_complete

    service_labels = {
        "eu_ai_act":            "EU AI Act Compliance (ab €299)",
        "vertragscheck":        "KI-Vertragscheck (ab €129)",
        "rechtstexte":          "Rechtstexte KI (€49)",
        "angebots_ki":          "Handwerker Angebots-KI (€79)",
        "shopify_texte":        "Shopify Produktbeschreibungen KI (€79)",
        "amazon_listings":      "Amazon/eBay Listing-KI (€99)",
        "expose_ki":            "Makler Exposé-KI (€199)",
        "social_media_kalender": "Social Media KI-Kalender (€69/Mo)",
    }
    fits      = [s.strip() for s in (service_fit or "").split(",") if s.strip()]
    svc_text  = ", ".join(service_labels.get(f, f) for f in fits) if fits else "KI-gestützte Business-Services"
    unsub_url = unsubscribe_link(email)

    tone_instructions = {
        "friendly":     "freundlich und neugierig, frage ob die Email ankam",
        "value_focused": "konkret auf Mehrwert fokussiert, nenne 1 spezifischen Vorteil für diese Branche",
        "breakup":      "respektvoll und abschließend, erkläre dass dies die letzte Nachricht ist",
    }
    tone_desc = tone_instructions.get(tone, "professionell und freundlich")

    prompt = f"""Schreibe eine B2B Follow-Up Email auf Deutsch an:
- Empfänger: {first_name or 'Guten Tag'} bei {company or 'Ihrem Unternehmen'}
- Branche/Segment: {segment or 'Unternehmen'}
- Angebotene Services: {svc_text}
- Folge-Versuch: {step} (bereits {prior_sends}x kontaktiert)
- Ton: {tone_desc}

Regeln:
1. Maximal 120 Wörter im Body
2. Persönlich, nicht generisch
3. Kein Spam-Trigger-Wörter
4. Abmelde-Link am Ende: {unsub_url}
5. Absender: Rudolf Sarkany | AIITEC

Antworte NUR mit JSON: {{"subject": "...", "body": "..."}}"""

    system = "Du bist ein erfahrener B2B-Sales-Texter. Antworte ausschließlich mit validem JSON."

    try:
        raw = await ai_complete(prompt, system=system, max_tokens=400, model_hint="fast")
        raw = raw.strip()
        # JSON aus Markdown-Block extrahieren falls nötig
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        subject = str(data.get("subject", "")).strip()
        body    = str(data.get("body", "")).strip()
        if subject and body:
            log.debug("AI Follow-Up Step %d generiert für %s", step, email)
            return subject, body
    except Exception as exc:
        log.warning("AI-Generierung fehlgeschlagen (Step %d, %s): %s — Fallback", step, email, exc)

    # ── Statisches Fallback-Template ──────────────────────────────────────────
    return _static_followup(company, first_name, step, svc_text, unsub_url)


def _static_followup(company: str, first_name: str, step: int, svc_text: str, unsub_url: str) -> tuple[str, str]:
    co   = company or "Ihr Unternehmen"
    name = first_name or "Guten Tag"
    templates = {
        1: (
            f"Kurze Nachfrage: KI-Services für {co}",
            f"{name},\n\nich wollte kurz nachfragen, ob meine letzte Email bei Ihnen ankam.\n\n"
            f"Wir bieten: {svc_text}\n\n"
            f"Reseller-Modell: 30% Provision, kein eigener Aufwand.\n\n"
            f"Kurze Antwort genügt.\n\nRudolf Sarkany | AIITEC\n\n"
            f"Abmelden: {unsub_url}"
        ),
        2: (
            f"1 konkreter Vorteil für {co}",
            f"{name},\n\nkurzes Beispiel: Ein Partner aus Ihrer Branche generiert durch "
            f"unser Reseller-Programm monatlich €800–2.000 Zusatzeinnahmen.\n\n"
            f"Services: {svc_text}\n\n"
            f"Interesse? Einfach antworten.\n\nRudolf Sarkany | AIITEC\n\n"
            f"Abmelden: {unsub_url}"
        ),
        3: (
            f"Letzte Nachricht von AIITEC",
            f"{name},\n\ndas ist meine letzte Email — ich verspreche es.\n\n"
            f"Falls Sie in Zukunft KI-Services für Ihre Kunden benötigen: "
            f"https://supermegabot-production.up.railway.app\n\n"
            f"Viel Erfolg für {co}!\n\nRudolf Sarkany | AIITEC\n\n"
            f"Abmelden: {unsub_url}"
        ),
    }
    return templates.get(step, templates[3])


# ── Lead-Verwaltung ───────────────────────────────────────────────────────────

async def enroll_lead(
    email: str,
    company: str = "",
    first_name: str = "",
    segment: str = "",
    service_fit: str = "",
    source: str = "manual",
    notes: str = "",
) -> dict:
    """
    Trägt einen Lead in die AI-Follow-Up Sequenz ein.
    Überspringt bereits abgemeldete oder bereits eingetragene Leads.
    """
    if not email or "@" not in email:
        return {"ok": False, "error": "Ungültige Email"}

    now  = time.time()
    conn = _db()
    try:
        existing = conn.execute("SELECT id, unsubscribed FROM followup_leads WHERE email=?", (email,)).fetchone()
        if existing:
            if existing["unsubscribed"]:
                return {"ok": False, "error": "Abgemeldet"}
            return {"ok": False, "already": True}

        conn.execute(
            "INSERT INTO followup_leads (email, company, first_name, segment, service_fit, source, enrolled_at, notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (email, company, first_name, segment, service_fit, source, now, notes),
        )
        for step_def in FOLLOWUP_STEPS:
            scheduled = now + step_def["delay_days"] * 86400
            conn.execute(
                "INSERT INTO followup_queue (lead_email, step, scheduled_at, status) VALUES (?,?,?,'pending')",
                (email, step_def["step"], scheduled),
            )
        conn.commit()
        log.info("Lead eingetragen: %s [%s / %s]", email, segment, source)
        return {"ok": True, "email": email, "steps_scheduled": len(FOLLOWUP_STEPS)}
    except sqlite3.IntegrityError:
        return {"ok": False, "already": True}
    finally:
        conn.close()


async def enroll_from_outreach_db() -> int:
    """
    Liest Leads mit status='sent' aus bulk_outreach.db und trägt sie in die
    AI-Follow-Up Sequenz ein (wenn noch nicht vorhanden).
    """
    bulk_db_path = _BASE / "data" / "bulk_outreach.db"
    if not bulk_db_path.exists():
        log.debug("bulk_outreach.db nicht gefunden — kein Auto-Enroll")
        return 0

    bulk = sqlite3.connect(str(bulk_db_path))
    bulk.row_factory = sqlite3.Row
    try:
        rows = bulk.execute("""
            SELECT DISTINCT co.email, co.name, co.segment, co.service_fit
            FROM bo_outreach out
            JOIN bo_companies co ON co.id = out.company_id
            WHERE out.status = 'sent'
              AND out.replied_at IS NULL
        """).fetchall()
    except Exception as e:
        log.warning("Bulk-DB Lesefehler: %s", e)
        return 0
    finally:
        bulk.close()

    enrolled = 0
    for row in rows:
        result = await enroll_lead(
            email=row["email"],
            company=row["name"] or "",
            segment=row["segment"] or "",
            service_fit=row["service_fit"] or "",
            source="bulk_outreach",
        )
        if result.get("ok"):
            enrolled += 1

    if enrolled:
        log.info("Auto-Enroll: %d Leads aus bulk_outreach.db eingetragen", enrolled)
    return enrolled


# ── Reply-Detection via IMAP ──────────────────────────────────────────────────

async def check_replies() -> int:
    """
    Prüft alle konfigurierten Gmail-Konten via IMAP auf Antworten.
    Markiert Leads als replied → alle ausstehenden Steps werden auf 'cancelled' gesetzt.
    Gibt Anzahl erkannter Antworten zurück.
    """
    accounts = _imap_accounts()
    if not accounts:
        log.debug("Keine IMAP-Accounts konfiguriert — Reply-Check übersprungen")
        return 0

    conn = _db()
    try:
        # Alle bekannten Lead-Emails laden
        lead_emails = {
            row[0].lower()
            for row in conn.execute("SELECT email FROM followup_leads WHERE replied_at IS NULL AND unsubscribed=0").fetchall()
        }
    finally:
        conn.close()

    if not lead_emails:
        return 0

    found_replies: list[str] = []

    for acct in accounts:
        if not acct["password"]:
            continue
        try:
            replies = await asyncio.get_event_loop().run_in_executor(
                None, _imap_scan_replies, acct, lead_emails
            )
            found_replies.extend(replies)
        except Exception as e:
            log.warning("IMAP-Scan Fehler (%s): %s", acct["user"], e)

    if not found_replies:
        return 0

    now  = time.time()
    conn = _db()
    try:
        for email in set(found_replies):
            conn.execute("UPDATE followup_leads SET replied_at=? WHERE email=?", (now, email))
            conn.execute(
                "UPDATE followup_queue SET status='cancelled' WHERE lead_email=? AND status='pending'",
                (email,)
            )
            log.info("Antwort erkannt: %s — Sequenz abgebrochen", email)
        conn.commit()
    finally:
        conn.close()

    return len(set(found_replies))


def _imap_scan_replies(acct: dict, lead_emails: set[str]) -> list[str]:
    """Synchroner IMAP-Scan (wird in Executor ausgeführt)."""
    found: list[str] = []
    try:
        mail = imaplib.IMAP4_SSL(acct["host"])
        mail.login(acct["user"], acct["password"])
        mail.select("INBOX")

        # Emails der letzten 30 Tage prüfen
        _, data = mail.search(None, "SINCE", "30-days-ago")
        if data[0]:
            for num in data[0].split():
                try:
                    _, msg_data = mail.fetch(num, "(BODY[HEADER.FIELDS (FROM)])")
                    if msg_data and msg_data[0]:
                        header = msg_data[0][1].decode("utf-8", errors="ignore").lower()
                        for lead_email in lead_emails:
                            if lead_email in header:
                                found.append(lead_email)
                                break
                except Exception:
                    continue
        mail.logout()
    except imaplib.IMAP4.error as e:
        log.debug("IMAP Login-Fehler (%s): %s", acct["user"], e)
    except Exception as e:
        log.warning("IMAP Fehler: %s", e)
    return found


# ── Unsubscribe-Handler ───────────────────────────────────────────────────────

async def handle_unsubscribe(email: str, token: str) -> dict:
    """
    Verarbeitet Abmeldeanfragen.
    Gibt {"ok": True/False, "message": str} zurück.
    """
    if not verify_unsub_token(email, token):
        return {"ok": False, "message": "Ungültiger Token"}

    now  = time.time()
    conn = _db()
    try:
        row = conn.execute("SELECT id, unsubscribed FROM followup_leads WHERE email=?", (email,)).fetchone()
        if not row:
            return {"ok": False, "message": "Email nicht gefunden"}
        if row["unsubscribed"]:
            return {"ok": True, "message": "Bereits abgemeldet"}

        conn.execute(
            "UPDATE followup_leads SET unsubscribed=1, unsubscribed_at=? WHERE email=?",
            (now, email),
        )
        conn.execute(
            "UPDATE followup_queue SET status='cancelled' WHERE lead_email=? AND status='pending'",
            (email,),
        )
        conn.commit()
        log.info("Abmeldung: %s", email)
        return {"ok": True, "message": "Erfolgreich abgemeldet"}
    finally:
        conn.close()


# ── Email senden ─────────────────────────────────────────────────────────────

def _send_email_smtp(smtp_acct: dict, to_email: str, subject: str, body: str, from_name: str = "Rudolf Sarkany | AIITEC") -> None:
    """Sendet via SMTP (SSL oder STARTTLS)."""
    try:
        from modules.gmail_accounts import _is_valid_recipient
        if not _is_valid_recipient(to_email):
            log.warning("BLOCKED (noreply/dead): %s", to_email)
            return
    except ImportError:
        pass
    msg              = MIMEMultipart("alternative")
    msg["Subject"]   = subject
    msg["From"]      = f"{from_name} <{smtp_acct['user']}>"
    msg["To"]        = to_email
    msg["Reply-To"]  = os.getenv("REPLY_TO_EMAIL", "aiitecbuuss@gmail.com")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if smtp_acct.get("ssl", True):
        with smtplib.SMTP_SSL(smtp_acct["host"], smtp_acct["port"], timeout=20) as s:
            s.login(smtp_acct["user"], smtp_acct["password"])
            s.sendmail(smtp_acct["user"], to_email, msg.as_string())
    else:
        with smtplib.SMTP(smtp_acct["host"], smtp_acct["port"], timeout=20) as s:
            s.ehlo()
            s.starttls()
            s.login(smtp_acct["user"], smtp_acct["password"])
            s.sendmail(smtp_acct["user"], to_email, msg.as_string())


# ── Hauptlauf ─────────────────────────────────────────────────────────────────

async def send_due_followups(batch_size: int = 30, rate_limit_s: float = 45.0) -> dict:
    """
    Sendet alle fälligen Follow-Up Emails (scheduled_at <= now).
    Nutzt AI für Content-Generierung, rotiert SMTP-Pool.
    Gibt {"sent": int, "failed": int, "skipped_replied": int, "skipped_unsub": int} zurück.
    """
    pool = _smtp_pool()
    if not any(a["password"] for a in pool):
        log.warning("Kein SMTP-Passwort konfiguriert — Follow-Up übersprungen")
        return {"sent": 0, "failed": 0, "skipped_replied": 0, "skipped_unsub": 0}

    conn = _db()
    now  = time.time()
    due  = conn.execute(
        "SELECT fq.id, fq.lead_email, fq.step "
        "FROM followup_queue fq "
        "JOIN followup_leads fl ON fl.email = fq.lead_email "
        "WHERE fq.status='pending' AND fq.scheduled_at <= ? "
        "  AND fl.replied_at IS NULL AND fl.unsubscribed=0 "
        "ORDER BY fq.scheduled_at ASC LIMIT ?",
        (now, batch_size),
    ).fetchall()
    conn.close()

    sent              = 0
    failed            = 0
    skipped_replied   = 0
    skipped_unsub     = 0
    smtp_idx          = random.randint(0, len(pool) - 1)

    for row in due:
        seq_id     = row["id"]
        email      = row["lead_email"]
        step_num   = row["step"]

        # Lead-Daten nachladen
        conn = _db()
        lead = conn.execute(
            "SELECT company, first_name, segment, service_fit, replied_at, unsubscribed "
            "FROM followup_leads WHERE email=?", (email,)
        ).fetchone()
        # Wieviele Steps bereits gesendet
        prior_count = conn.execute(
            "SELECT COUNT(*) FROM followup_queue WHERE lead_email=? AND status='sent'",
            (email,)
        ).fetchone()[0]
        conn.close()

        if not lead:
            log.warning("Lead nicht gefunden: %s", email)
            continue
        if lead["replied_at"]:
            skipped_replied += 1
            _cancel_lead_queue(email)
            continue
        if lead["unsubscribed"]:
            skipped_unsub += 1
            _cancel_lead_queue(email)
            continue

        step_def = next((s for s in FOLLOWUP_STEPS if s["step"] == step_num), None)
        if not step_def:
            log.warning("Unbekannter Step %d für %s", step_num, email)
            continue

        # KI-Generierung
        subject, body = await generate_followup_email(
            email=email,
            company=lead["company"] or "",
            first_name=lead["first_name"] or "",
            segment=lead["segment"] or "",
            service_fit=lead["service_fit"] or "",
            step=step_num,
            tone=step_def["tone"],
            prior_sends=prior_count,
        )

        # SMTP-Konto mit Passwort wählen
        acct = None
        for i in range(len(pool)):
            candidate = pool[(smtp_idx + i) % len(pool)]
            if candidate["password"]:
                acct = candidate
                smtp_idx = (smtp_idx + i + 1) % len(pool)
                break
        if not acct:
            log.error("Kein SMTP-Konto mit Passwort — Abbruch")
            break

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, _send_email_smtp, acct, email, subject, body
            )
            conn = _db()
            conn.execute(
                "UPDATE followup_queue SET status='sent', sent_at=?, subject=?, body_preview=? WHERE id=?",
                (now, subject, body[:200], seq_id),
            )
            conn.execute(
                "INSERT INTO followup_log (lead_email, step, subject, sent_at, ai_generated) VALUES (?,?,?,?,?)",
                (email, step_num, subject, now, 1),
            )
            conn.commit()
            conn.close()
            sent += 1
            log.info("Follow-Up Step %d gesendet → %s", step_num, email)
        except Exception as exc:
            err = str(exc)[:300]
            conn = _db()
            conn.execute("UPDATE followup_queue SET status='error' WHERE id=?", (seq_id,))
            conn.execute(
                "INSERT INTO followup_log (lead_email, step, subject, sent_at, error) VALUES (?,?,?,?,?)",
                (email, step_num, subject, now, err),
            )
            conn.commit()
            conn.close()
            failed += 1
            log.warning("SMTP Fehler (%s Step %d): %s", email, step_num, err)

        if rate_limit_s > 0:
            await asyncio.sleep(rate_limit_s + random.uniform(0, 15))

    log.info("AI Follow-Up: %d gesendet, %d Fehler, %d Antworten-Skip, %d Abmelde-Skip",
             sent, failed, skipped_replied, skipped_unsub)
    return {
        "sent":             sent,
        "failed":           failed,
        "skipped_replied":  skipped_replied,
        "skipped_unsub":    skipped_unsub,
    }


def _cancel_lead_queue(email: str) -> None:
    conn = _db()
    try:
        conn.execute("UPDATE followup_queue SET status='cancelled' WHERE lead_email=? AND status='pending'", (email,))
        conn.commit()
    finally:
        conn.close()


# ── Statistiken ────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    conn = _db()
    try:
        total      = conn.execute("SELECT COUNT(*) FROM followup_leads").fetchone()[0]
        active     = conn.execute("SELECT COUNT(*) FROM followup_leads WHERE replied_at IS NULL AND unsubscribed=0").fetchone()[0]
        replied    = conn.execute("SELECT COUNT(*) FROM followup_leads WHERE replied_at IS NOT NULL").fetchone()[0]
        unsub      = conn.execute("SELECT COUNT(*) FROM followup_leads WHERE unsubscribed=1").fetchone()[0]
        sent_total = conn.execute("SELECT COUNT(*) FROM followup_log WHERE error IS NULL").fetchone()[0]
        errors     = conn.execute("SELECT COUNT(*) FROM followup_log WHERE error IS NOT NULL").fetchone()[0]
        ai_pct_row = conn.execute(
            "SELECT AVG(ai_generated)*100 FROM followup_log WHERE error IS NULL"
        ).fetchone()[0]
        by_step: dict[str, int] = {}
        for s in FOLLOWUP_STEPS:
            n = conn.execute(
                "SELECT COUNT(*) FROM followup_log WHERE step=? AND error IS NULL", (s["step"],)
            ).fetchone()[0]
            by_step[f"step_{s['step']}_day{s['delay_days']}"] = n
        pending = conn.execute(
            "SELECT COUNT(*) FROM followup_queue WHERE status='pending'"
        ).fetchone()[0]
        return {
            "total_leads":  total,
            "active_leads": active,
            "replied":      replied,
            "unsubscribed": unsub,
            "emails_sent":  sent_total,
            "errors":       errors,
            "ai_generated_pct": round(ai_pct_row or 0, 1),
            "pending_queue": pending,
            "by_step":      by_step,
        }
    finally:
        conn.close()


# ── Haupt-Zyklus ──────────────────────────────────────────────────────────────

async def run_ai_followup_cycle() -> str:
    """
    Kompletter Zyklus:
    1. Auto-Enroll aus bulk_outreach.db
    2. IMAP Reply-Check
    3. AI Follow-Up Emails senden
    Gibt Status-String zurück.
    """
    enrolled = await enroll_from_outreach_db()
    replies  = await check_replies()
    result   = await send_due_followups()
    return (
        f"AI-FollowUp: {enrolled} Leads eingetragen, "
        f"{replies} Antworten erkannt, "
        f"{result['sent']} Emails gesendet ({result['failed']} Fehler)"
    )
