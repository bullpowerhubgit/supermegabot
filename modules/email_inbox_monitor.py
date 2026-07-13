#!/usr/bin/env python3
"""
Email Inbox Monitor — alle 5 Minuten: Eingang UND Ausgang überwachen
====================================================================
Scannt Gmail IMAP alle 5 Minuten auf neue ungelesene E-Mails.
Kategorisiert: Bestellung, Anfrage, Antwort, Bounce, Spam.
Sendet Telegram-Alert bei neuen wichtigen Emails.
Speichert History in SQLite.
"""

from __future__ import annotations

import asyncio
import email as email_lib
import imaplib
import logging
import os
import re
import sqlite3
import time
from email.header import decode_header as _dh
from pathlib import Path
from typing import Dict, List

import aiohttp

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "inbox_monitor.db"

# Kategorisierungs-Signale
_CATEGORY_RULES = [
    ("bestellung",  ["zahlung", "payment", "order", "kauf", "stripe", "checkout", "invoice", "rechnung", "subscription"]),
    ("anfrage",     ["anfrage", "interest", "ich hätte", "ich würde", "would like", "information", "interested", "kontakt"]),
    ("antwort",     ["re:", "aw:", "antwort", "reply", "danke", "thank", "vielen dank", "verstanden"]),
    ("bounce",      ["mailer-daemon", "delivery failed", "undeliverable", "failed to deliver", "bounced", "non-delivery"]),
    ("spam",        ["unsubscribe", "casino", "crypto", "bitcoin", "invest now", "million dollar", "click here"]),
]


def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inbox_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT UNIQUE,
            account     TEXT,
            sender      TEXT,
            subject     TEXT,
            category    TEXT,
            seen_at     INTEGER,
            alerted     INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _decode_str(s: str) -> str:
    parts = []
    for chunk, enc in _dh(s or ""):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return " ".join(parts).strip()


def _categorize(subject: str, sender: str) -> str:
    text = (subject + " " + sender).lower()
    for cat, signals in _CATEGORY_RULES:
        if any(sig in text for sig in signals):
            return cat
    return "sonstige"


def _imap_accounts() -> list:
    accounts = []
    user1 = os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
    pass1 = os.getenv("GMAIL_APP_PASSWORD_AIITEC", "")
    if user1 and pass1:
        accounts.append({"user": user1, "password": pass1, "label": "AiiteC"})
    user2 = os.getenv("GMAIL_USER_PERSONAL", os.getenv("EMAIL_FROM", ""))
    pass2 = os.getenv("GMAIL_APP_PASSWORD_PERSONAL", os.getenv("EMAIL_PASSWORD", ""))
    if user2 and pass2 and user2 != user1:
        accounts.append({"user": user2, "password": pass2, "label": "Personal"})
    return accounts


def _scan_inbox(account: dict, conn: sqlite3.Connection) -> List[Dict]:
    new_emails = []
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(account["user"], account["password"])
        imap.select("INBOX")

        _, data = imap.search(None, "UNSEEN")
        uid_list = data[0].split() if data[0] else []

        for uid_bytes in uid_list[-30:]:
            uid = uid_bytes.decode()
            already = conn.execute("SELECT id FROM inbox_log WHERE uid=?", (uid,)).fetchone()
            if already:
                continue

            _, msg_data = imap.fetch(uid_bytes, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email_lib.message_from_bytes(raw)
            sender  = _decode_str(msg.get("From", ""))
            subject = _decode_str(msg.get("Subject", "(kein Betreff)"))
            cat     = _categorize(subject, sender)

            conn.execute(
                "INSERT OR IGNORE INTO inbox_log (uid, account, sender, subject, category, seen_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, account["label"], sender[:200], subject[:300], cat, int(time.time()))
            )
            conn.commit()
            new_emails.append({
                "uid":      uid,
                "account":  account["label"],
                "sender":   sender,
                "subject":  subject,
                "category": cat,
            })

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.warning("IMAP Fehler [%s]: %s", account.get("label"), e)
    except Exception as e:
        log.error("inbox_scan [%s]: %s", account.get("label"), e)
    return new_emails


async def _tg_alert(emails: List[Dict], session: aiohttp.ClientSession):
    token   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    # Gruppiere nach Kategorie
    by_cat: Dict[str, List] = {}
    for e in emails:
        by_cat.setdefault(e["category"], []).append(e)

    emoji_map = {
        "bestellung": "💰",
        "anfrage":    "📩",
        "antwort":    "↩️",
        "bounce":     "❌",
        "spam":       "🗑",
        "sonstige":   "📧",
    }

    lines = ["📬 **Neue Emails** (5-min-Scan)\n"]
    for cat, items in by_cat.items():
        emoji = emoji_map.get(cat, "📧")
        lines.append(f"{emoji} **{cat.upper()}** ({len(items)})")
        for e in items[:3]:
            sender_short = e["sender"][:40].split("<")[0].strip()
            subject_short = e["subject"][:60]
            lines.append(f"  • [{e['account']}] {sender_short}")
            lines.append(f"    _{subject_short}_")
        if len(items) > 3:
            lines.append(f"  _...und {len(items)-3} weitere_")

    text = "\n".join(lines)
    try:
        await session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=aiohttp.ClientTimeout(total=10),
        )
    except Exception as e:
        log.warning("Telegram Alert Fehler: %s", e)


async def run_inbox_monitor() -> Dict:
    """Scannt alle Gmail-Postfächer auf neue Emails, schickt Telegram-Alert."""
    conn     = _db()
    accounts = _imap_accounts()
    if not accounts:
        conn.close()
        return {"ok": False, "reason": "no_gmail_accounts"}

    all_new: List[Dict] = []
    for acc in accounts:
        new = _scan_inbox(acc, conn)
        all_new.extend(new)

    conn.close()

    # Nur bei neuen, nicht-spam Emails alarmieren
    alert_emails = [e for e in all_new if e["category"] != "spam"]
    if alert_emails:
        async with aiohttp.ClientSession() as session:
            await _tg_alert(alert_emails, session)

    log.info(
        "Inbox Monitor: %d Konten, %d neu (%d Alerts)",
        len(accounts), len(all_new), len(alert_emails)
    )
    return {
        "ok":         True,
        "accounts":   len(accounts),
        "new_total":  len(all_new),
        "alerted":    len(alert_emails),
        "by_category": {
            cat: sum(1 for e in all_new if e["category"] == cat)
            for cat in set(e["category"] for e in all_new)
        },
    }


async def get_inbox_summary(limit: int = 50) -> Dict:
    """Letzte N eingehende Emails für Dashboard."""
    conn = _db()
    rows = conn.execute(
        "SELECT uid, account, sender, subject, category, seen_at FROM inbox_log "
        "ORDER BY seen_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return {
        "emails": [
            {"uid": r[0], "account": r[1], "sender": r[2],
             "subject": r[3], "category": r[4], "ts": r[5]}
            for r in rows
        ]
    }
