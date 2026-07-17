#!/usr/bin/env python3
"""
SMB Outreach Automation — 5-Stufen Email-Sequenz für Shopify/E-Commerce-Betreiber.

Sequenz:
  Tag 0: Erstkontakt (Template 1)
  Tag 1: 24h-Follow-up
  Tag 3: Value-Email
  Tag 5: Abandoned-Cart-Fokus (Template 6)
  Tag 7: Trial-Closing

Usage:
  from modules.smb_outreach_auto import task_smb_outreach_daily, add_prospect, get_status
  asyncio.run(task_smb_outreach_daily())
  add_prospect("email@firma.de", "Max Müller", "FirmaGmbH")
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

log = logging.getLogger("SMBOutreach")

_BASE = Path(__file__).resolve().parents[1]
_DB   = _BASE / "data" / "smb_outreach.db"

# ── Stripe Trial-Link ────────────────────────────────────────────────────────
STRIPE_LINK_GROWTH = os.getenv(
    "STRIPE_LINK_SMB_GROWTH",
    "https://buy.stripe.com/6oUeVfbrIemme2Ycx04F47j8",
)

# ── Gmail-Pool (Account-Rotation wenn Limit erreicht) ───────────────────────
def _env(key: str, default: str = "") -> str:
    if not os.environ.get(key):
        ef = _BASE / ".env"
        if ef.exists():
            for line in ef.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return os.getenv(key, default)

# Rotation: aiitecbuuss → rudolf.aiitec → rudolfsarkany1984 → dragonadnp
_GMAIL_POOL = [
    ("GMAIL_USER_5",  "GMAIL_APP_PASSWORD_5",  "aiitecbuuss@gmail.com"),
    ("GMAIL_USER_7",  "GMAIL_APP_PASSWORD_7",  "rudolf.sarkany.aiitec@gmail.com"),
    ("GMAIL_USER_8",  "GMAIL_APP_PASSWORD_8",  "rudolfsarkany1984@gmail.com"),
    ("GMAIL_USER_1",  "GMAIL_APP_PASSWORD_1",  "dragonadnp@gmail.com"),
]

def _get_available_sender() -> tuple[str, str] | tuple[None, None]:
    """Gibt (user, pass) des ersten Accounts zurück der noch nicht limit-gesperrt ist."""
    _env("GMAIL_USER_5")  # .env laden
    for user_key, pass_key, default_user in _GMAIL_POOL:
        user = os.getenv(user_key, default_user)
        pw   = os.getenv(pass_key, "")
        if not pw:
            continue
        blocked_flag = f"_GMAIL_LIMIT_{user_key}"
        if os.environ.get(blocked_flag):
            log.debug("Account %s heute gesperrt — skip", user)
            continue
        return user, pw
    return None, None

def _mark_limit(user_key: str) -> None:
    os.environ[f"_GMAIL_LIMIT_{user_key}"] = "1"

# ── Email-Sequenz ────────────────────────────────────────────────────────────
SEQUENCE = [
    {"step": 1, "day_offset": 0, "template": 1,       "subject": "Shopify + Telegram Automation — kurze Frage"},
    {"step": 2, "day_offset": 1, "template": "24h",   "subject": "Kurze Nachfrage — {company}"},
    {"step": 3, "day_offset": 3, "template": "value", "subject": "5 Automation-Tipps für Shopify-Betreiber"},
    {"step": 4, "day_offset": 5, "template": 6,       "subject": "Abandoned Checkouts — automatisch zurückgewinnen"},
    {"step": 5, "day_offset": 7, "template": "close", "subject": "7-Tage Trial — direkt starten"},
]

# Echte Kontakte werden via add_prospect() hinzugefügt.
# NIEMALS Fake-Adressen hier eintragen!
SEED_CONTACTS: list[dict] = []

# ── SQLite ───────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smb_contacts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            email     TEXT UNIQUE NOT NULL,
            name      TEXT DEFAULT '',
            company   TEXT DEFAULT '',
            status    TEXT DEFAULT 'active',
            added_at  INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smb_sends (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            step        INTEGER NOT NULL,
            sent_at     INTEGER DEFAULT (strftime('%s','now')),
            success     INTEGER DEFAULT 1,
            error       TEXT DEFAULT '',
            UNIQUE(email, step)
        )
    """)
    conn.commit()
    return conn


def add_prospect(email: str, name: str = "", company: str = "") -> bool:
    """Fügt einen neuen Outreach-Kontakt hinzu (Dedup per Email)."""
    try:
        with _db() as c:
            c.execute(
                "INSERT OR IGNORE INTO smb_contacts(email, name, company) VALUES(?,?,?)",
                (email.lower().strip(), name.strip(), company.strip()),
            )
        log.info("Prospect hinzugefügt: %s (%s)", email, company)
        return True
    except Exception as e:
        log.error("add_prospect Fehler: %s", e)
        return False


def _get_pending_sends() -> list[dict]:
    """Gibt alle (contact, step) zurück die noch gesendet werden müssen."""
    now = int(time.time())
    pending = []
    with _db() as c:
        contacts = c.execute(
            "SELECT * FROM smb_contacts WHERE status='active'"
        ).fetchall()
        for contact in contacts:
            for seq in SEQUENCE:
                step      = seq["step"]
                day_off   = seq["day_offset"]
                send_time = contact["added_at"] + day_off * 86400
                if now < send_time:
                    continue
                already = c.execute(
                    "SELECT id FROM smb_sends WHERE email=? AND step=? AND success=1",
                    (contact["email"], step),
                ).fetchone()
                if already:
                    continue
                pending.append({
                    "email":    contact["email"],
                    "name":     contact["name"] or "Hallo",
                    "company":  contact["company"] or "Ihr Unternehmen",
                    "step":     step,
                    "template": seq["template"],
                    "subject":  seq["subject"],
                })
    return pending


def _send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    """Sendet via Gmail-Pool — wechselt automatisch bei Daily-Limit."""
    for idx, (user_key, pass_key, default_user) in enumerate(_GMAIL_POOL):
        if os.environ.get(f"_GMAIL_LIMIT_{user_key}"):
            continue
        user = os.getenv(user_key, default_user)
        pw   = os.getenv(pass_key, "")
        if not pw:
            continue
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Rudolf Sarkany | AIITEC <{user}>"
            msg["To"]      = to
            msg.attach(MIMEText(body, "plain", "utf-8"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
                s.ehlo()
                s.starttls()
                s.login(user, pw)
                s.sendmail(user, [to], msg.as_string())
            return True, ""
        except smtplib.SMTPRecipientsRefused as e:
            return False, f"SMTP refused: {e}"
        except Exception as e:
            err = str(e)
            if "Daily user sending limit exceeded" in err or "5.4.5" in err:
                log.warning("Gmail-Limit: %s → nächster Account", user)
                _mark_limit(user_key)
                continue
            return False, err[:200]
    return False, "Alle Gmail-Accounts haben Daily-Limit erreicht"


def _record_send(email: str, step: int, success: bool, error: str = "") -> None:
    with _db() as c:
        c.execute(
            "INSERT OR REPLACE INTO smb_sends(email, step, sent_at, success, error) VALUES(?,?,?,?,?)",
            (email, step, int(time.time()), 1 if success else 0, error),
        )


# ── Haupt-Task ───────────────────────────────────────────────────────────────

async def task_smb_outreach_daily() -> dict[str, Any]:
    """Scheduler-Task: täglich ausführen — sendet fällige Sequence-Emails."""
    from modules.telegram_dm_templates import get_template

    # Seed-Kontakte nur beim allerersten Lauf eintragen
    for sc in SEED_CONTACTS:
        add_prospect(sc["email"], sc.get("name", ""), sc.get("company", ""))

    pending = _get_pending_sends()
    sent = 0
    errors = 0
    skipped = 0

    for item in pending:
        tmpl = get_template(
            item["template"],
            name=item["name"],
            company=item["company"],
            stripe_link=STRIPE_LINK_GROWTH,
        )
        subject = item["subject"].format(
            name=item["name"],
            company=item["company"],
        )
        ok, err = _send_email(item["email"], subject, tmpl["body"])
        _record_send(item["email"], item["step"], ok, err)

        if ok:
            sent += 1
            log.info("✅ Schritt %d gesendet an %s", item["step"], item["email"])
        else:
            if "Daily-Limit" in err or "Alle Gmail" in err:
                skipped += 1
                log.warning("Alle Accounts voll — übersprungen: %s", item["email"])
                break  # Kein Sinn mehr weiterzumachen heute
            else:
                errors += 1
                log.error("❌ Fehler an %s (Schritt %d): %s", item["email"], item["step"], err)

        await asyncio.sleep(8)  # Anti-Spam-Delay

    result = {
        "pending": len(pending),
        "sent": sent,
        "errors": errors,
        "skipped_limit": skipped,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    log.info("SMB Outreach: %s", result)
    return result


async def get_status() -> dict[str, Any]:
    """Gibt Übersicht über Kontakte und Versandstatus zurück."""
    with _db() as c:
        total     = c.execute("SELECT COUNT(*) FROM smb_contacts WHERE status='active'").fetchone()[0]
        sends     = c.execute("SELECT COUNT(*) FROM smb_sends WHERE success=1").fetchone()[0]
        errors    = c.execute("SELECT COUNT(*) FROM smb_sends WHERE success=0").fetchone()[0]
        completed = c.execute(
            "SELECT COUNT(DISTINCT email) FROM smb_sends WHERE step=5 AND success=1"
        ).fetchone()[0]
        recent = c.execute(
            "SELECT email, step, sent_at FROM smb_sends ORDER BY sent_at DESC LIMIT 5"
        ).fetchall()
    return {
        "active_contacts":  total,
        "emails_sent":      sends,
        "errors":           errors,
        "sequences_complete": completed,
        "recent_sends": [dict(r) for r in recent],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(get_status()))
