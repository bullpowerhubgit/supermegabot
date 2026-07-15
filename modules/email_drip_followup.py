"""
Email Drip Follow-Up — 7-Tage B2B Sequenz
==========================================
Schreibt Follow-Up-Emails an Leads die bereits kontaktiert wurden aber nicht
geantwortet haben. 4 Stufen: Tag 2, 4, 7, 14.
Liest Leads aus data/mass_outreach.db, sendet via SMTP-Pool.
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

log = logging.getLogger("EmailDrip")

_BASE        = Path(__file__).parent.parent
_DRIP_DB     = _BASE / "data" / "email_drip.db"
_OUTREACH_DB = _BASE / "data" / "mass_outreach.db"


# ── Drip-Sequenz Texte ────────────────────────────────────────────────────────

DRIP_STEPS = [
    {
        "step":     1,
        "delay_h":  48,   # 2 Tage nach letztem Kontakt
        "subject":  "Kurze Nachfrage: Shop-Automatisierung für {company}",
        "body":     (
            "Hallo {first_name},\n\n"
            "ich hatte Ihnen vor ein paar Tagen geschrieben bezüglich der Automatisierung "
            "Ihres Online-Shops.\n\n"
            "Darf ich kurz fragen: Wäre eine 10-Minuten-Demo interessant für Sie? "
            "Ich zeige Ihnen konkret, wie {company} mit unserem System Zeit und Kosten spart.\n\n"
            "Kurze Antwort genügt.\n\n"
            "Mit freundlichen Grüßen\n"
            "Rudolf Sarkany\n"
            "SuperMegaBot · ineedit.com.co"
        ),
    },
    {
        "step":     2,
        "delay_h":  96,   # 4 Tage
        "subject":  "1 konkretes Beispiel — wie {company} 10h/Woche sparen könnte",
        "body":     (
            "Hallo {first_name},\n\n"
            "kurzes Beispiel aus der Praxis:\n\n"
            "Ein ähnlicher Händler spart mit unserem System täglich 2 Stunden bei der "
            "Produktpflege, 30 Minuten bei Bestellbestätigungen und läuft dank automatischem "
            "Preismonitoring immer wettbewerbsfähig.\n\n"
            "Für {company} könnte das je nach Bestandsgröße 8–15 Stunden pro Woche bedeuten — "
            "die Sie lieber in Wachstum investieren.\n\n"
            "Wenn das interessant klingt, antworten Sie einfach mit 'Demo' — "
            "ich reserviere Ihnen einen kostenlosen Slot.\n\n"
            "Beste Grüße\n"
            "Rudolf Sarkany · SuperMegaBot"
        ),
    },
    {
        "step":     3,
        "delay_h":  168,  # 7 Tage
        "subject":  "Letzte Möglichkeit: Kostenlose Demo für {company}",
        "body":     (
            "Hallo {first_name},\n\n"
            "das ist meine letzte Nachricht zu diesem Thema — ich verspreche es.\n\n"
            "Wir bieten {company} eine kostenlose 30-Minuten-Demo ohne jede Verpflichtung. "
            "Sie sehen live, wie die Automatisierung bei Ihrem Shop aussehen würde.\n\n"
            "Falls das nichts für Sie ist: kein Problem, ich melde mich nicht mehr.\n"
            "Falls doch: Antworten Sie einfach mit 'Ja' — ich melde mich sofort.\n\n"
            "Mit freundlichen Grüßen\n"
            "Rudolf Sarkany\n"
            "SuperMegaBot · https://ineedit.com.co"
        ),
    },
    {
        "step":     4,
        "delay_h":  336,  # 14 Tage
        "subject":  "Auf Wiedersehen von SuperMegaBot",
        "body":     (
            "Hallo {first_name},\n\n"
            "ich habe in den vergangenen Wochen mehrfach versucht, Sie zu erreichen — "
            "ohne Rückmeldung.\n\n"
            "Das respektiere ich vollständig und schreibe Ihnen nicht mehr.\n\n"
            "Falls Sie in Zukunft doch Interesse an Shop-Automatisierung haben sollten, "
            "finden Sie uns jederzeit unter:\n"
            "https://ineedit.com.co\n\n"
            "Ich wünsche {company} weiterhin viel Erfolg.\n\n"
            "Herzliche Grüße\n"
            "Rudolf Sarkany · SuperMegaBot"
        ),
    },
]


# ── Database ──────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DRIP_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DRIP_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drip_sequence (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_email  TEXT,
            step        INTEGER,
            scheduled_at REAL,
            sent_at     REAL,
            status      TEXT DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_drip_pending
            ON drip_sequence (status, scheduled_at);
        CREATE TABLE IF NOT EXISTS drip_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_email  TEXT,
            step        INTEGER,
            subject     TEXT,
            sent_at     REAL,
            error       TEXT
        );
    """)
    conn.commit()
    return conn


def _outreach_db() -> Optional[sqlite3.Connection]:
    if not _OUTREACH_DB.exists():
        return None
    conn = sqlite3.connect(str(_OUTREACH_DB))
    conn.row_factory = sqlite3.Row
    return conn


# ── Enroll leads ──────────────────────────────────────────────────────────────

async def enroll_sent_leads() -> int:
    """
    Holt Leads mit status='sent' aus mass_outreach.db die noch nicht
    in der Drip-Sequenz sind und schreibt alle 4 Steps.
    """
    odb = _outreach_db()
    if not odb:
        log.warning("mass_outreach.db nicht gefunden — Drip-Enroll übersprungen")
        return 0

    cutoff = time.time() - 86400  # mindestens 1 Tag seit letztem Kontakt
    try:
        sent_leads = odb.execute(
            "SELECT email, company, first_name, last_contact FROM leads "
            "WHERE status='sent' AND (last_contact IS NULL OR last_contact < ?)",
            (cutoff,)
        ).fetchall()
    except Exception as e:
        log.warning("Outreach DB Lesefehler: %s", e)
        return 0
    finally:
        odb.close()

    if not sent_leads:
        return 0

    ddb     = _db()
    enrolled = 0
    now     = time.time()

    for lead in sent_leads:
        email = lead["email"]

        already = ddb.execute(
            "SELECT COUNT(*) FROM drip_sequence WHERE lead_email=?", (email,)
        ).fetchone()[0]
        if already > 0:
            continue

        last_contact = lead["last_contact"] or now
        for step in DRIP_STEPS:
            scheduled = last_contact + step["delay_h"] * 3600
            ddb.execute(
                "INSERT INTO drip_sequence (lead_email, step, scheduled_at, status) VALUES (?,?,?,?)",
                (email, step["step"], scheduled, "pending")
            )
        enrolled += 1

    ddb.commit()
    ddb.close()
    log.info("Drip-Enroll: %d neue Leads eingeschrieben", enrolled)
    return enrolled


# ── Enroll single lead (called by sofia_agent_hub after phone calls) ──────────

async def enroll_lead(email: str, product_id: str = "general", source: str = "manual") -> bool:
    """
    Trägt einen einzelnen Lead direkt in alle 4 Drip-Schritte ein.
    Wird von sofia_agent_hub.py nach Telefonanrufen aufgerufen.
    Signatur: enroll_lead(email, product_id, source)
    """
    if not email:
        log.warning("enroll_lead: keine Email angegeben")
        return False

    ddb = _db()
    try:
        already = ddb.execute(
            "SELECT COUNT(*) FROM drip_sequence WHERE lead_email=?", (email,)
        ).fetchone()[0]
        if already > 0:
            log.debug("enroll_lead: %s bereits in Drip-Sequenz", email)
            return False

        now = time.time()
        for step in DRIP_STEPS:
            scheduled = now + step["delay_h"] * 3600
            ddb.execute(
                "INSERT INTO drip_sequence (lead_email, step, scheduled_at, status) VALUES (?,?,?,?)",
                (email, step["step"], scheduled, "pending")
            )
        ddb.commit()
        log.info("enroll_lead: %s eingetragen — source=%s product=%s", email, source, product_id)
        return True
    except Exception as e:
        log.warning("enroll_lead Fehler: %s", e)
        return False
    finally:
        ddb.close()


# ── Send due drips ────────────────────────────────────────────────────────────

def _smtp_config_from_env() -> dict:
    return {
        "host":     os.getenv("SMTP_HOST", os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")),
        "port":     int(os.getenv("SMTP_PORT", os.getenv("GMAIL_SMTP_PORT", "587"))),
        "user":     os.getenv("SMTP_USER", os.getenv("GMAIL_SMTP_USER", "")),
        "password": os.getenv("SMTP_PASS", os.getenv("GMAIL_SMTP_PASS", os.getenv("GMAIL_APP_PASSWORD_1", ""))),
        "from":     os.getenv("SMTP_FROM", os.getenv("GMAIL_SMTP_USER", "noreply@ineedit.com.co")),
    }


def _render(template: str, **kwargs) -> str:
    for k, v in kwargs.items():
        template = template.replace("{" + k + "}", str(v) if v else "Ihr Unternehmen")
    return template


def _send_smtp(cfg: dict, to_email: str, subject: str, body: str) -> None:
    msg                 = MIMEMultipart("alternative")
    msg["Subject"]      = subject
    msg["From"]         = cfg["from"]
    msg["To"]           = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
        s.ehlo()
        s.starttls()
        s.login(cfg["user"], cfg["password"])
        s.sendmail(cfg["from"], [to_email], msg.as_string())


async def send_due_drips(smtp_config: Optional[dict] = None, batch_size: int = 50) -> dict:
    if not smtp_config:
        smtp_config = _smtp_config_from_env()

    if not smtp_config.get("user") or not smtp_config.get("password"):
        log.warning("SMTP-Credentials fehlen — Drip übersprungen")
        return {"sent": 0, "failed": 0, "errors": ["SMTP credentials missing"]}

    odb = _outreach_db()
    ddb = _db()
    now = time.time()

    due = ddb.execute(
        "SELECT id, lead_email, step FROM drip_sequence "
        "WHERE status='pending' AND scheduled_at <= ? LIMIT ?",
        (now, batch_size)
    ).fetchall()

    sent = 0
    failed = 0
    errors = []

    for row in due:
        seq_id = row["id"]
        email  = row["lead_email"]
        step_n = row["step"]

        # Lead-Daten aus outreach DB
        company    = "Ihr Unternehmen"
        first_name = "Hallo"
        if odb:
            lead = odb.execute(
                "SELECT company, first_name FROM leads WHERE email=?", (email,)
            ).fetchone()
            if lead:
                company    = lead["company"] or company
                first_name = lead["first_name"] or first_name

        step_def = next((s for s in DRIP_STEPS if s["step"] == step_n), None)
        if not step_def:
            ddb.execute("UPDATE drip_sequence SET status='error' WHERE id=?", (seq_id,))
            continue

        subject = _render(step_def["subject"], company=company, first_name=first_name)
        body    = _render(step_def["body"],    company=company, first_name=first_name)

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, _send_smtp, smtp_config, email, subject, body
            )
            ddb.execute(
                "UPDATE drip_sequence SET status='sent', sent_at=? WHERE id=?",
                (now, seq_id)
            )
            ddb.execute(
                "INSERT INTO drip_log (lead_email, step, subject, sent_at) VALUES (?,?,?,?)",
                (email, step_n, subject, now)
            )
            sent += 1
            log.info("Drip Step %d gesendet an %s", step_n, email)
        except Exception as exc:
            err_msg = str(exc)[:200]
            ddb.execute(
                "UPDATE drip_sequence SET status='error' WHERE id=?", (seq_id,)
            )
            ddb.execute(
                "INSERT INTO drip_log (lead_email, step, subject, sent_at, error) VALUES (?,?,?,?,?)",
                (email, step_n, subject, now, err_msg)
            )
            errors.append(f"{email}: {err_msg}")
            failed += 1

    ddb.commit()
    ddb.close()
    if odb:
        odb.close()

    log.info("Drip-Run: %d gesendet, %d Fehler", sent, failed)
    return {"sent": sent, "failed": failed, "errors": errors[:5]}


# ── Main cycle ────────────────────────────────────────────────────────────────

async def run_drip_cycle(smtp_config: Optional[dict] = None) -> str:
    enrolled = await enroll_sent_leads()
    result   = await send_due_drips(smtp_config)
    return (
        f"Drip: {enrolled} neue Leads eingeschrieben, "
        f"{result['sent']} Emails gesendet, {result['failed']} Fehler"
    )


async def get_drip_stats() -> dict:
    ddb = _db()
    total    = ddb.execute("SELECT COUNT(*) FROM drip_sequence").fetchone()[0]
    pending  = ddb.execute("SELECT COUNT(*) FROM drip_sequence WHERE status='pending'").fetchone()[0]
    sent     = ddb.execute("SELECT COUNT(*) FROM drip_sequence WHERE status='sent'").fetchone()[0]
    errors   = ddb.execute("SELECT COUNT(*) FROM drip_sequence WHERE status='error'").fetchone()[0]
    by_step  = {}
    for s in DRIP_STEPS:
        n = ddb.execute(
            "SELECT COUNT(*) FROM drip_log WHERE step=?", (s["step"],)
        ).fetchone()[0]
        by_step[f"step_{s['step']}_day{s['delay_h']//24}"] = n
    ddb.close()
    return {
        "total_enrolled": total,
        "pending":        pending,
        "sent":           sent,
        "errors":         errors,
        "step_breakdown": by_step,
    }
