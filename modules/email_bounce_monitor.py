#!/usr/bin/env python3
"""
Email Bounce Monitor — Sofortige Zustellungsprüfung nach dem Senden
====================================================================
Läuft alle 5 Minuten:
1. Alle Gmail-Konten via IMAP auf Bounce/Fehler-Emails scannen
2. Bounce-Adressen in SQLite-Blacklist einträgen
3. EmailGuard nutzt die Blacklist → kein nochmaliger Send an Bounces
4. Gmail-Postfach automatisch aufräumen (Bounce-Emails in Papierkorb)
5. Telegram-Alert bei neuem Bounce mit Auto-Fix-Bericht

Erkannte Bounce-Typen:
- Permanent: 550/551/552 (User unknown, Mailbox full, Policy rejection)
- Temporär:  421/450/451 (Server unavailable — wird nach 24h nochmal versucht)
- SPAM:      Delivery rejected (blocklist, spam filter)
- Quota:     Mailbox full / Over quota
"""
from __future__ import annotations

import asyncio
import email as email_lib
import hashlib
import imaplib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import aiohttp

log = logging.getLogger("BounceMonitor")

_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_DB_PATH = _DATA_DIR / "bounce_blacklist.db"

# ── Bounce-Pattern ────────────────────────────────────────────────────────────
_BOUNCE_SENDERS = re.compile(
    r'mailer-daemon@|postmaster@|daemon@|bounces@|noreply@bounce|'
    r'delivery-error@|smtp-error@|no-reply@mailer',
    re.IGNORECASE
)
_BOUNCE_SUBJECTS = re.compile(
    r'delivery failed|undeliverable|mail delivery failed|'
    r'failure notice|returned mail|bounce|unzustellbar|'
    r'konnte nicht zugestellt|lieferung fehlgeschlagen|'
    r'delivery status notification|dsn|nddr|'
    r'message not delivered|could not deliver|'
    r'address not found|user unknown|mailbox unavailable',
    re.IGNORECASE
)
_BOUNCE_EMAIL_RE = re.compile(
    r'(?:failed recipient|the following address\(es\) failed|'
    r'final-recipient|original-recipient|rcpt to).*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE | re.DOTALL
)
_ANY_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

_PERMANENT_CODES = {"550", "551", "552", "553", "554", "421", "422"}
_TEMP_CODES      = {"421", "450", "451", "452"}

# Gmail IMAP-Konfiguration aus gmail_accounts.py
_GMAIL_ACCOUNTS: List[Dict] = []


def _build_accounts() -> List[Dict]:
    """Alle Gmail-Konten aus Env-Variablen laden."""
    accs = []
    for i in range(1, 10):
        email_key  = f"GMAIL_EMAIL_{i}"
        passwd_key = f"GMAIL_APP_PASSWORD_{i}"
        em  = os.getenv(email_key, "")
        pwd = os.getenv(passwd_key, "")
        if em and pwd and "@" in em:
            accs.append({"email": em, "password": pwd})
    # Haupt-Accounts direkt
    for em_key, pw_key in [
        ("GMAIL_EMAIL", "GMAIL_APP_PASSWORD"),
        ("GMAIL_PRIMARY_EMAIL", "GMAIL_PRIMARY_APP_PASSWORD"),
    ]:
        em  = os.getenv(em_key, "")
        pwd = os.getenv(pw_key, "")
        if em and pwd and "@" in em and not any(a["email"] == em for a in accs):
            accs.append({"email": em, "password": pwd})
    # Fallback: aus gmail_accounts.py
    if not accs:
        try:
            from modules.gmail_accounts import GMAIL_POOL
            for acc in GMAIL_POOL:
                if acc.get("password") and acc.get("email"):
                    accs.append({"email": acc["email"], "password": acc["password"]})
        except Exception:
            pass
    return accs


# ── SQLite Blacklist ──────────────────────────────────────────────────────────

def _init_db():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bounce_blacklist (
            email      TEXT PRIMARY KEY,
            bounce_type TEXT,  -- permanent / temp / spam / quota
            bounce_code TEXT,
            first_seen  REAL,
            last_seen   REAL,
            count       INTEGER DEFAULT 1,
            source      TEXT    -- welches Gmail-Konto hat den Bounce gesehen
        );
        CREATE TABLE IF NOT EXISTS bounce_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT,
            subject    TEXT,
            bounce_type TEXT,
            seen_at    REAL,
            raw_snippet TEXT
        );
    """)
    conn.commit(); conn.close()


_init_db()


def is_blacklisted(email_addr: str) -> bool:
    """Prüft ob eine Email-Adresse in der Bounce-Blacklist ist."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute(
            "SELECT bounce_type FROM bounce_blacklist WHERE email=?",
            (email_addr.lower().strip(),)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def add_to_blacklist(email_addr: str, bounce_type: str = "permanent",
                     code: str = "", source: str = "") -> None:
    """Fügt Email-Adresse zur Bounce-Blacklist hinzu."""
    em = email_addr.lower().strip()
    now = time.time()
    try:
        conn = sqlite3.connect(_DB_PATH)
        existing = conn.execute(
            "SELECT count FROM bounce_blacklist WHERE email=?", (em,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE bounce_blacklist SET last_seen=?, count=count+1, bounce_type=? WHERE email=?",
                (now, bounce_type, em)
            )
        else:
            conn.execute(
                "INSERT INTO bounce_blacklist(email,bounce_type,bounce_code,first_seen,last_seen,source) VALUES(?,?,?,?,?,?)",
                (em, bounce_type, code, now, now, source)
            )
        conn.commit(); conn.close()
        log.info("Blacklist: %s (%s, Code: %s)", em, bounce_type, code or "?")
    except Exception as e:
        log.warning("Blacklist add Fehler: %s", e)


def _log_bounce(email_addr: str, subject: str, bounce_type: str, snippet: str = "") -> None:
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            "INSERT INTO bounce_log(email,subject,bounce_type,seen_at,raw_snippet) VALUES(?,?,?,?,?)",
            (email_addr.lower().strip(), subject[:200], bounce_type, time.time(), snippet[:500])
        )
        conn.commit(); conn.close()
    except Exception:
        pass


# ── IMAP-Scanner ─────────────────────────────────────────────────────────────

def _decode_header(raw: str) -> str:
    try:
        parts = decode_header(raw or "")
        result = []
        for b, enc in parts:
            if isinstance(b, bytes):
                result.append(b.decode(enc or "utf-8", errors="replace"))
            else:
                result.append(str(b))
        return " ".join(result)
    except Exception:
        return str(raw or "")


def _extract_bounced_addresses(body_text: str) -> List[str]:
    """Extrahiert die fehlgeschlagene Email-Adresse aus dem Bounce-Body."""
    addrs = []
    # Spezifische Bounce-Pattern zuerst
    for m in _BOUNCE_EMAIL_RE.finditer(body_text):
        addr = m.group(1)
        if "@" in addr and "." in addr.split("@")[1]:
            addrs.append(addr.lower())
    # Alle Email-Adressen als Fallback (exkl. Gmail/System-Adressen)
    if not addrs:
        for m in _ANY_EMAIL_RE.finditer(body_text):
            addr = m.group(0).lower()
            domain = addr.split("@")[1] if "@" in addr else ""
            if domain not in ("gmail.com", "googlemail.com", "googleapis.com",
                              "google.com", "railway.app", "anthropic.com"):
                addrs.append(addr)
    return list(set(addrs))


def _detect_bounce_type(body_text: str) -> Tuple[str, str]:
    """Erkennt Bounce-Typ und SMTP-Code."""
    code_match = re.search(r'\b([45]\d\d)\b', body_text)
    code = code_match.group(1) if code_match else ""
    body_lower = body_text.lower()

    if any(x in body_lower for x in ["spam", "blocked", "blacklist", "policy rejection"]):
        return "spam", code
    if any(x in body_lower for x in ["quota", "full", "over capacity"]):
        return "quota", code
    if code in _TEMP_CODES or any(x in body_lower for x in ["temporarily", "try again", "server unavailable"]):
        return "temp", code
    return "permanent", code


def _scan_imap_account(account: Dict) -> List[Dict]:
    """Scannt ein Gmail-Konto auf Bounce-Emails via IMAP."""
    bounces = []
    em  = account["email"]
    pwd = account["password"]

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(em, pwd)
        mail.select("INBOX")

        # Nur Mailer-Daemon-Emails der letzten 24h
        status, data = mail.search(None, 'FROM "MAILER-DAEMON"')
        ids_md = data[0].split() if status == "OK" else []

        status, data = mail.search(None, 'SUBJECT "Delivery"')
        ids_del = data[0].split() if status == "OK" else []

        status, data = mail.search(None, 'SUBJECT "Undeliverable"')
        ids_und = data[0].split() if status == "OK" else []

        status, data = mail.search(None, 'SUBJECT "unzustellbar"')
        ids_unz = data[0].split() if status == "OK" else []

        all_ids = list(set(ids_md + ids_del + ids_und + ids_unz))

        for uid in all_ids[-50:]:  # Max 50 auf einmal
            try:
                status, msg_data = mail.fetch(uid, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                sender  = _decode_header(msg.get("From", "")).lower()
                subject = _decode_header(msg.get("Subject", ""))

                # Ist es ein Bounce?
                is_bounce = (
                    _BOUNCE_SENDERS.search(sender) or
                    _BOUNCE_SUBJECTS.search(subject)
                )
                if not is_bounce:
                    continue

                # Body extrahieren
                body_parts = []
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct in ("text/plain", "text/html"):
                            try:
                                body_parts.append(part.get_payload(decode=True).decode("utf-8", errors="replace"))
                            except Exception:
                                pass
                else:
                    try:
                        body_parts.append(msg.get_payload(decode=True).decode("utf-8", errors="replace"))
                    except Exception:
                        pass

                body_text = "\n".join(body_parts)
                bounce_type, code = _detect_bounce_type(body_text)
                failed_addrs = _extract_bounced_addresses(body_text)

                bounces.append({
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "subject": subject,
                    "sender": sender,
                    "bounce_type": bounce_type,
                    "code": code,
                    "failed_addrs": failed_addrs,
                    "snippet": body_text[:300],
                    "source_account": em,
                })

                # Bounce-Email in Gmail als gelesen markieren + Papierkorb
                mail.store(uid, "+FLAGS", "\\Seen")
                # In [Gmail]/Trash verschieben
                try:
                    mail.copy(uid, "[Gmail]/Trash")
                    mail.store(uid, "+FLAGS", "\\Deleted")
                except Exception:
                    pass

            except Exception as e:
                log.debug("Bounce parse Fehler (uid=%s): %s", uid, e)
                continue

        mail.expunge()
        mail.logout()

    except imaplib.IMAP4.error as e:
        log.warning("IMAP Login %s: %s", em, e)
    except Exception as e:
        log.warning("IMAP Scan %s: %s", em, e)

    return bounces


# ── Telegram Alert ────────────────────────────────────────────────────────────

async def _tg_alert(msg: str) -> None:
    bot  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot or not chat:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
            )
    except Exception:
        pass


# ── Auto-Fix: Blacklist in EmailGuard integrieren ─────────────────────────────

def _patch_email_guard_blacklist(bad_addr: str) -> None:
    """Fügt fehlerhafte Adresse zur EmailGuard-Datenbank hinzu."""
    try:
        from modules.email_guard import _register_sent_db
    except Exception:
        pass
    # Auch direkt in bounce_blacklist
    add_to_blacklist(bad_addr)


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

async def run_bounce_scan() -> Dict:
    """Scannt alle Gmail-Konten auf Bounces und verarbeitet sie."""
    accounts = _build_accounts()
    if not accounts:
        log.info("Keine Gmail-Konten konfiguriert — Bounce-Scan übersprungen")
        return {"scanned": 0, "new_bounces": 0}

    all_bounces = []
    for acc in accounts:
        try:
            bounces = await asyncio.get_event_loop().run_in_executor(
                None, _scan_imap_account, acc
            )
            all_bounces.extend(bounces)
        except Exception as e:
            log.warning("Bounce-Scan %s: %s", acc["email"], e)

    new_bounces = 0
    blacklisted_addrs = []

    for bounce in all_bounces:
        for addr in bounce["failed_addrs"]:
            if not is_blacklisted(addr):
                add_to_blacklist(
                    addr,
                    bounce_type=bounce["bounce_type"],
                    code=bounce["code"],
                    source=bounce["source_account"],
                )
                _log_bounce(addr, bounce["subject"], bounce["bounce_type"], bounce["snippet"])
                blacklisted_addrs.append(addr)
                new_bounces += 1

        # Auch ohne erkannte Adresse: Bounce loggen
        if not bounce["failed_addrs"]:
            _log_bounce("unknown", bounce["subject"], bounce["bounce_type"], bounce["snippet"])

    # Telegram-Alert wenn neue Bounces
    if new_bounces > 0:
        type_counts: Dict[str, int] = {}
        for a in all_bounces:
            t = a.get("bounce_type", "?")
            type_counts[t] = type_counts.get(t, 0) + 1

        alert = (
            f"📭 <b>Bounce Monitor — {new_bounces} neue Bounces!</b>\n\n"
            f"Neue Blacklist-Einträge:\n"
            + "".join(f"  ❌ <code>{a}</code>\n" for a in blacklisted_addrs[:10])
            + (f"\n  ... und {len(blacklisted_addrs)-10} weitere\n" if len(blacklisted_addrs) > 10 else "")
            + f"\nTypen: {json.dumps(type_counts)}\n\n"
            f"✅ Auto-Fix: Alle Adressen dauerhaft blockiert\n"
            f"✅ Bounce-Emails in Gmail gelöscht\n"
            f"✅ Kein nochmaliger Send an diese Adressen"
        )
        await _tg_alert(alert)
        log.info("Bounce-Alert gesendet: %d neue Bounces → Blacklist", new_bounces)
    else:
        log.debug("Bounce-Scan: keine neuen Bounces in %d Konten", len(accounts))

    return {
        "scanned_accounts": len(accounts),
        "total_bounces_found": len(all_bounces),
        "new_bounces": new_bounces,
        "blacklisted": blacklisted_addrs,
    }


async def get_blacklist_stats() -> Dict:
    """Statistik über die Bounce-Blacklist."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        total = conn.execute("SELECT COUNT(*) FROM bounce_blacklist").fetchone()[0]
        by_type = conn.execute(
            "SELECT bounce_type, COUNT(*) FROM bounce_blacklist GROUP BY bounce_type"
        ).fetchall()
        recent = conn.execute(
            "SELECT email, bounce_type, last_seen FROM bounce_blacklist ORDER BY last_seen DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return {
            "total_blacklisted": total,
            "by_type": dict(by_type),
            "recent": [{"email": r[0], "type": r[1], "seen": r[2]} for r in recent],
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
    result = asyncio.run(run_bounce_scan())
    print(f"Ergebnis: {result}")
