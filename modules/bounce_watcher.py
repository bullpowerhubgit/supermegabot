#!/usr/bin/env python3
"""
BounceWatcher — Scannt alle Gmail-Konten nach Delivery-Fehlern.
Läuft alle 30 Minuten. Blockiert fehlerhafte Adressen dauerhaft.

Flow:
  IMAP-Scan → Bounce erkannt → Adresse extrahieren →
  Blocklist speichern → EmailGuard blockiert künftige Sends →
  Telegram-Alert
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
from pathlib import Path
from typing import List, Optional

import aiohttp

log = logging.getLogger("BounceWatcher")

_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_DB_PATH = _DATA_DIR / "email_guard.db"

TG_BOT  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Bounce-Erkennungs-Patterns ────────────────────────────────────────────────
_BOUNCE_SENDERS = re.compile(
    r'mailer-daemon|postmaster|daemon@|bounces?\.|bounce\+|'
    r'noreply@bounce|mail-delivery|delivery-failure|'
    r'no-reply@bounce|return@|auto-reply',
    re.IGNORECASE,
)
_BOUNCE_SUBJECTS = re.compile(
    r'delivery.*(failed|failure|error|status)|'
    r'undeliverable|undelivered|'
    r'mail.*(konnte nicht|nicht zugestellt|failed)|'
    r'bounce|'
    r'failed to deliver|'
    r'returned mail|'
    r'Zustellungsfehler|'
    r'Nicht zustellbar|'
    r'Unzustellbar',
    re.IGNORECASE,
)

# Extrahiert die ursprüngliche Empfänger-Adresse aus dem Bounce-Text
_FAILED_TO_RE = re.compile(
    r'(?:final recipient|original recipient|failed recipient|'
    r'to:|recipient|empfänger)[:\s]+<?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>?',
    re.IGNORECASE,
)
_EMAIL_IN_BODY = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# ── Blocklist DB ──────────────────────────────────────────────────────────────

# Known hard bounces / dead mailboxes (seeded once)
_SEED_BOUNCES = (
    ("noreply@supermegabot.com", "test/noreply hard bounce"),
    ("info@wirecard.de", "wirecard insolvent 2020"),
    ("test@bullpower.de", "test address"),
    ("test@test.com", "test address"),
    ("null@null.com", "invalid"),
    ("nobody@nowhere.com", "invalid"),
    ("info@example.com", "example.com"),
    ("admin@example.com", "example.com"),
    ("contact@wirecard.com", "wirecard insolvent"),
    ("office@wirecard.de", "wirecard insolvent"),
    ("support@supermegabot.com", "internal test domain"),
)


def _init_db() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE, to_email TEXT, sent_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bounce_blocklist (
            email       TEXT PRIMARY KEY,
            reason      TEXT,
            first_seen  REAL,
            count       INTEGER DEFAULT 1
        )
    """)
    # seed permanent bounce addresses
    for em, reason in _SEED_BOUNCES:
        conn.execute(
            "INSERT OR IGNORE INTO bounce_blocklist(email,reason,first_seen,count) VALUES(?,?,?,1)",
            (em.lower(), reason, time.time()),
        )
    conn.commit()
    conn.close()


def add_to_blocklist(email_addr: str, reason: str) -> bool:
    """Gibt True zurück wenn neu, False wenn schon drin."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        existing = conn.execute(
            "SELECT count FROM bounce_blocklist WHERE email=?", (email_addr.lower(),)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE bounce_blocklist SET count=count+1, reason=? WHERE email=?",
                (reason, email_addr.lower()),
            )
            conn.commit(); conn.close()
            return False
        conn.execute(
            "INSERT INTO bounce_blocklist(email,reason,first_seen) VALUES(?,?,?)",
            (email_addr.lower(), reason, time.time()),
        )
        conn.commit(); conn.close()
        return True
    except Exception as e:
        log.error("Blocklist-DB Fehler: %s", e)
        return False


def is_blocked(email_addr: str) -> bool:
    """Gibt True zurück wenn Email auf der Blocklist steht."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute(
            "SELECT 1 FROM bounce_blocklist WHERE email=?", (email_addr.lower(),)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def get_blocklist(limit: int = 200) -> list:
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            "SELECT email, reason, count, first_seen FROM bounce_blocklist ORDER BY first_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"email": r[0], "reason": r[1], "count": r[2], "first_seen": r[3]} for r in rows]
    except Exception:
        return []


# ── IMAP Scanner ──────────────────────────────────────────────────────────────

def _imap_scan_account(acc) -> List[dict]:
    """Scannt ein Konto nach Bounce-Mails. Gibt Liste von {email, reason, subject} zurück."""
    bounces = []
    try:
        mail = imaplib.IMAP4_SSL(acc.imap_host, 993)
        mail.login(acc.email, acc.password)
        mail.select("INBOX")

        _, uids = mail.search(None, "UNSEEN")
        uid_list = uids[0].split() if uids[0] else []

        for uid in uid_list[-50:]:  # max 50 ungelesene pro Konto
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                sender  = msg.get("From", "").lower()
                subject = msg.get("Subject", "")
                to_addr = msg.get("To", "")

                is_bounce = (
                    _BOUNCE_SENDERS.search(sender) or
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
                            try:
                                body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                            except Exception:
                                pass
                else:
                    try:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        pass

                # Ziel-Adresse extrahieren
                failed_addr = None
                m = _FAILED_TO_RE.search(body)
                if m:
                    failed_addr = m.group(1)
                else:
                    # Alle Adressen im Body sammeln, eigene Konten rausfiltern
                    all_addrs = _EMAIL_IN_BODY.findall(body)
                    own_domains = {"gmail.com", "googlemail.com", "aiitec.de"}
                    candidates = [
                        a for a in all_addrs
                        if a.lower() != acc.email.lower()
                        and not any(a.lower().endswith(d) for d in own_domains)
                        and a.lower() != sender.lower()
                    ]
                    if candidates:
                        failed_addr = candidates[0]

                # Als gelesen markieren + in Gmail-Papierkorb verschieben (hält Postfach sauber)
                mail.store(uid, "+FLAGS", "\\Seen")
                try:
                    mail.copy(uid, "[Gmail]/Trash")
                    mail.store(uid, "+FLAGS", "\\Deleted")
                except Exception:
                    pass

                if failed_addr and "@" in failed_addr:
                    bounces.append({
                        "email": failed_addr.lower().strip(),
                        "reason": f"Bounce von {acc.email}: {subject[:80]}",
                        "subject": subject,
                        "account": acc.email,
                    })
                    log.info("Bounce erkannt: %s → %s via %s", failed_addr, subject[:50], acc.email)
                else:
                    # Bounce ohne erkennbare Adresse — nur loggen
                    log.warning(
                        "Bounce-Mail ohne erkennbare Adresse: [%s] %s — From: %s",
                        acc.email, subject[:60], sender[:60],
                    )
                    bounces.append({
                        "email": None,
                        "reason": f"Bounce ohne Adresse: {subject[:80]}",
                        "subject": subject,
                        "account": acc.email,
                    })

            except Exception as e:
                log.debug("Fehler bei UID %s: %s", uid, e)

        mail.expunge()  # Papierkorb endgültig leeren
        mail.logout()
    except Exception as e:
        log.warning("IMAP-Fehler bei %s: %s", getattr(acc, "email", "?"), e)
    return bounces


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str) -> None:
    try:
        from modules.telegram_throttle import send as tg_send
        await tg_send(text)
    except Exception:
        pass


# ── Haupt-Run ─────────────────────────────────────────────────────────────────

async def run_bounce_watcher() -> dict:
    """Scannt alle Gmail-Konten — wird vom Scheduler aufgerufen."""
    _init_db()
    try:
        from modules.gmail_accounts import configured_accounts
        accounts = configured_accounts()
    except Exception as e:
        log.error("gmail_accounts nicht ladbar: %s", e)
        return {"error": str(e)}

    all_bounces: List[dict] = []

    loop = asyncio.get_event_loop()
    for acc in accounts:
        bounces = await loop.run_in_executor(None, _imap_scan_account, acc)
        all_bounces.extend(bounces)

    new_blocks = 0
    for b in all_bounces:
        addr = b.get("email")
        if addr:
            is_new = add_to_blocklist(addr, b["reason"])
            if is_new:
                new_blocks += 1

    # Telegram-Report nur wenn neue Bounces gefunden
    if new_blocks > 0:
        blocked_list = "\n".join(
            f"  ❌ {b['email']} ({b['account']})"
            for b in all_bounces if b.get("email")
        )
        msg = (
            f"📬 *BounceWatcher — {new_blocks} neue Fehler-Adressen geblockt*\n\n"
            f"{blocked_list}\n\n"
            f"_Diese Adressen erhalten KEINE weiteren Emails mehr._"
        )
        await _tg(msg)
        log.info("BounceWatcher: %d neue Bounces → Blocklist", new_blocks)
    elif all_bounces:
        log.info("BounceWatcher: %d Bounces — alle bereits in Blocklist", len(all_bounces))
    else:
        log.debug("BounceWatcher: keine neuen Bounce-Mails")

    return {
        "scanned_accounts": len(accounts),
        "bounces_found": len(all_bounces),
        "new_blocks": new_blocks,
    }
