#!/usr/bin/env python3
"""
Bounce Monitor — Lieferfehler sofort erkennen und beheben
=========================================================
Läuft alle 30 Minuten (nach dem Email-Versand Zyklus).

Was es tut:
  1. Scannt alle Gmail-Postfächer auf MAILER-DAEMON / Delivery-Failure Emails
  2. Extrahiert die bounced E-Mail-Adresse aus dem Fehler-Text
  3. Markiert die Adresse in mass_outreach.db als "bounced" (nie mehr senden)
  4. Sendet Telegram-Alert mit Zusammenfassung
  5. Löscht/archiviert die Bounce-Emails aus Gmail (Postfach sauber halten)

Integration im Scheduler:
  ("bounce_monitor", task_bounce_monitor, 1800, 60)
"""
from __future__ import annotations

import email as email_lib
import imaplib
import json
import logging
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import aiohttp

log = logging.getLogger("BounceMonitor")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "bounce_monitor.db"

# ── Bounce-Erkennungs-Muster ──────────────────────────────────────────────────
_BOUNCE_SUBJECTS = re.compile(
    r"(mailer.daemon|delivery.status|delivery.fail|"
    r"undeliverable|failure.notice|mail.delivery.failed|"
    r"returned.mail|non.delivery|postmaster|bounce|"
    r"nicht.zugestellt|zustellung.fehlgeschlagen|"
    r"undelivered.mail|auto-reply|auto.antwort)",
    re.IGNORECASE
)

_BOUNCE_SENDERS = re.compile(
    r"(mailer.daemon|postmaster|noreply@.*\.(com|de|net|org)|"
    r"bounce@|bounces@|no.reply@|delivery@)",
    re.IGNORECASE
)

# Muster um bounced E-Mail-Adresse aus Body zu extrahieren
_FAILED_EMAIL_RE = re.compile(
    r"(?:to|an|failed to deliver.*?to|recipient|empfänger|final\s+recipient)\s*:?\s*"
    r"([\w._%+\-]+@[\w.\-]+\.\w{2,})",
    re.IGNORECASE
)
_EMAIL_IN_BODY_RE = re.compile(r"[\w._%+\-]+@[\w.\-]+\.\w{2,}")


# ── Bounce-Typen ─────────────────────────────────────────────────────────────
_HARD_BOUNCE = re.compile(
    r"(5\d\d\s|user.unknown|address.*rejected|no.such.user|"
    r"mailbox.not.found|invalid.address|does.not.exist|"
    r"account.*disabled|user.*not.*found|undeliverable)",
    re.IGNORECASE
)
_SOFT_BOUNCE = re.compile(
    r"(4\d\d\s|mailbox.full|quota|temporarily|retry|"
    r"too.many|server.busy|connection.timeout|"
    r"postfach.voll|vorübergehend)",
    re.IGNORECASE
)


def _init_db():
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS bounces (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        email       TEXT UNIQUE,
        bounce_type TEXT,
        raw_subject TEXT,
        detected_at TEXT DEFAULT (datetime('now')),
        count       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS scan_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account     TEXT,
        found       INTEGER,
        removed     INTEGER,
        scanned_at  TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    return conn


def _extract_bounced_email(subject: str, body: str, from_addr: str) -> Optional[str]:
    """Extrahiert die Empfänger-Adresse aus einem Bounce-Email."""
    # Aus dem Body (bevorzugt)
    m = _FAILED_EMAIL_RE.search(body)
    if m:
        addr = m.group(1).lower()
        if addr not in {"postmaster@", "noreply@", "mailer-daemon@"}:
            return addr

    # Alle Emails im Body finden — die die nicht @gmail.com, @googlemail etc. sind
    # könnten die bounced Adresse sein
    all_emails = _EMAIL_IN_BODY_RE.findall(body)
    our_domains = {"gmail.com", "googlemail.com", "railway.app"}
    for addr in all_emails:
        domain = addr.split("@")[-1].lower()
        if domain not in our_domains and len(domain) > 4:
            return addr.lower()

    return None


def _mark_bounced_in_outreach_db(email: str, bounce_type: str):
    """Markiert eine Email in der Outreach-DB als gebounced → nie wieder senden."""
    outreach_db = _BASE / "data" / "mass_outreach.db"
    if not outreach_db.exists():
        return
    try:
        conn = sqlite3.connect(str(outreach_db))
        # Tabelle prüfen ob 'status' Spalte existiert
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for (tbl,) in tables:
            try:
                conn.execute(
                    f"UPDATE {tbl} SET status='bounced' WHERE "
                    f"(email=? OR email LIKE ?) AND (status IS NULL OR status='pending' OR status='sent')",
                    (email, f"%{email}%")
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("Outreach-DB Update fehlgeschlagen für %s: %s", email, e)


def _mark_bounced_in_email_guardian(email: str):
    """Blockt Email dauerhaft im EmailGuardian."""
    guardian_db = _BASE / "data" / "email_guardian.db"
    if not guardian_db.exists():
        return
    try:
        conn = sqlite3.connect(str(guardian_db))
        conn.execute(
            "INSERT OR IGNORE INTO blocked_log(to_email, subject, reason) VALUES(?,?,?)",
            (email, "PERMANENT_BOUNCE", f"Hard bounce detected {datetime.now().date()}")
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _scan_account_for_bounces(
    user: str, password: str, conn: sqlite3.Connection
) -> List[Dict]:
    """Scannt ein Gmail-Konto auf Bounce-Emails."""
    bounces = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, password)
        mail.select("INBOX")

        # Letzte 3 Tage nach Bounce-Emails suchen
        since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, nums = mail.search(None, f'(SINCE "{since}")')

        uid_list = nums[0].split() if nums[0] else []
        log.info("BounceMonitor: %s — %d Emails scannen", user, len(uid_list))

        for num in uid_list[-100:]:  # Max 100 pro Lauf
            _, data = mail.fetch(num, "(RFC822)")
            if not data or not data[0]:
                continue
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)

            from_addr = msg.get("From", "")
            subject   = msg.get("Subject", "")

            # Ist das eine Bounce-Email?
            is_bounce = (
                _BOUNCE_SENDERS.search(from_addr) or
                _BOUNCE_SUBJECTS.search(subject)
            )
            if not is_bounce:
                continue

            # Body extrahieren
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode("utf-8", errors="replace")[:2000]
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")[:2000]

            # Bounce-Typ bestimmen
            if _HARD_BOUNCE.search(body + subject):
                bounce_type = "hard"
            elif _SOFT_BOUNCE.search(body + subject):
                bounce_type = "soft"
            else:
                bounce_type = "unknown"

            # Bounced E-Mail-Adresse extrahieren
            bounced_email = _extract_bounced_email(subject, body, from_addr)

            bounces.append({
                "from": from_addr[:100],
                "subject": subject[:200],
                "bounce_type": bounce_type,
                "bounced_email": bounced_email,
                "imap_num": num,
                "account": user,
            })

            # Hard-Bounce: Adresse dauerhaft blockieren
            if bounced_email and bounce_type == "hard":
                # In bounce-DB speichern
                try:
                    conn.execute(
                        "INSERT INTO bounces(email, bounce_type, raw_subject) "
                        "VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET count=count+1",
                        (bounced_email, bounce_type, subject[:200])
                    )
                    conn.commit()
                except Exception:
                    pass
                # In Outreach-DB als gebounced markieren
                _mark_bounced_in_outreach_db(bounced_email, bounce_type)
                # Im Guardian blockieren
                _mark_bounced_in_email_guardian(bounced_email)
                log.info("Hard-Bounce: %s → dauerhaft blockiert", bounced_email)

            # Bounce-Email archivieren (aus Inbox raus damit Gmail nicht voll wird)
            try:
                # In "[Gmail]/Alle Nachrichten" verschieben = aus Inbox entfernen
                mail.store(num, "+FLAGS", "\\Deleted")
            except Exception:
                pass

        try:
            mail.expunge()  # Gelöschte Emails wirklich entfernen
        except Exception:
            pass
        mail.logout()

    except Exception as e:
        log.warning("BounceMonitor IMAP-Fehler [%s]: %s", user, e)
    return bounces


async def _telegram_bounce_report(bounces: List[Dict]):
    """Telegram-Report über erkannte Bounces."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat or not bounces:
        return

    hard = [b for b in bounces if b["bounce_type"] == "hard"]
    soft = [b for b in bounces if b["bounce_type"] == "soft"]
    unk  = [b for b in bounces if b["bounce_type"] == "unknown"]

    lines = [
        f"📬 <b>Bounce Monitor Report</b>",
        f"Gesamt: {len(bounces)} Bounces",
        f"❌ Hard (dauerhaft blockiert): {len(hard)}",
        f"⚠️ Soft (temporär): {len(soft)}",
        f"❓ Unbekannt: {len(unk)}",
        "",
    ]
    if hard:
        lines.append("<b>Hard Bounces (aus Listen entfernt):</b>")
        for b in hard[:10]:
            em = b.get("bounced_email", "unbekannt")
            lines.append(f"  • <code>{em}</code>")
        if len(hard) > 10:
            lines.append(f"  ... und {len(hard)-10} weitere")

    msg = "\n".join(lines)
    try:
        payload = json.dumps({
            "chat_id": chat, "text": msg, "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


async def run_bounce_monitor() -> Dict:
    """Haupt-Task für den Scheduler."""
    conn = _init_db()
    all_bounces = []

    gmail_pairs = [
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
        ("GMAIL_USER_1",         "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_7",         "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_8",         "GMAIL_APP_PASSWORD_8"),
    ]

    for user_key, pass_key in gmail_pairs:
        user = os.getenv(user_key, "")
        pw   = os.getenv(pass_key, "")
        if not user or not pw:
            continue
        bounces = _scan_account_for_bounces(user, pw, conn)
        all_bounces.extend(bounces)

        # Scan-Log
        conn.execute(
            "INSERT INTO scan_log(account, found, removed) VALUES(?,?,?)",
            (user, len(bounces),
             len([b for b in bounces if b["bounce_type"] == "hard"]))
        )
        conn.commit()

    conn.close()

    if all_bounces:
        await _telegram_bounce_report(all_bounces)
        log.info(
            "BounceMonitor: %d Bounces gefunden (%d hard / %d soft)",
            len(all_bounces),
            len([b for b in all_bounces if b["bounce_type"] == "hard"]),
            len([b for b in all_bounces if b["bounce_type"] == "soft"]),
        )
    else:
        log.info("BounceMonitor: Keine Bounces gefunden — Postfach sauber ✅")

    return {
        "bounces_found": len(all_bounces),
        "hard_bounces": len([b for b in all_bounces if b["bounce_type"] == "hard"]),
        "soft_bounces": len([b for b in all_bounces if b["bounce_type"] == "soft"]),
    }


def get_bounce_stats() -> Dict:
    """Statistik über bounced Adressen."""
    if not _DB.exists():
        return {"total": 0, "hard": 0, "soft": 0}
    conn = _init_db()
    total = conn.execute("SELECT COUNT(*) FROM bounces").fetchone()[0]
    hard  = conn.execute("SELECT COUNT(*) FROM bounces WHERE bounce_type='hard'").fetchone()[0]
    soft  = conn.execute("SELECT COUNT(*) FROM bounces WHERE bounce_type='soft'").fetchone()[0]
    recent = conn.execute(
        "SELECT email, bounce_type, count, detected_at FROM bounces "
        "ORDER BY detected_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {
        "total": total, "hard": hard, "soft": soft,
        "recent": [
            {"email": r[0], "type": r[1], "count": r[2], "at": r[3]}
            for r in recent
        ]
    }


def is_bounced(email: str) -> bool:
    """Prüft ob eine Adresse hard-gebounced ist."""
    if not _DB.exists():
        return False
    try:
        conn = _init_db()
        row = conn.execute(
            "SELECT id FROM bounces WHERE email=? AND bounce_type='hard'",
            (email.lower(),)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False
