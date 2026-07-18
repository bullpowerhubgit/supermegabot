#!/usr/bin/env python3
"""
Email Bounce Fixer — Automatisches Delivery-Monitoring + Auto-Reparatur
=======================================================================
Nach JEDEM Email-Versand + alle 5 Minuten via IMAP:

1. IMAP-Scan: Gmail auf Bounce-Nachrichten (Mailer-Daemon, Undeliverable)
2. Extrahiere fehlerhafter Empfänger aus Bounce-Email
3. Auto-Fix: entfernt fehlerhafte Adresse aus:
   - Mailchimp → unsubscribe/archive
   - Klaviyo → suppress
   - Email-Sequence-Engine → deaktivieren
   - Lokale Bounce-Blacklist
4. Telegram-Alert: was wurde wann gefixed
5. Mailchimp + Klaviyo Bounce-Reports abfragen (nach Kampagnen-Versand)

Ergebnis: Gmail wird nicht mehr mit Fehlermeldungen geflutet.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("EmailBounceFixer")

_ROOT    = Path(__file__).parent.parent
_DB_PATH = _ROOT / "data" / "bounce_blacklist.db"

# ── Bounce-Erkennungs-Signale (Betreff + Absender) ───────────────────────────
_BOUNCE_SUBJECTS = [
    "delivery failed", "delivery failure", "mail delivery failed",
    "undeliverable", "undelivered mail", "returned mail",
    "failed to deliver", "could not deliver", "non-delivery",
    "message not delivered", "delivery status notification",
    "permanent failure", "address rejected", "user unknown",
    "mailbox not found", "no such user", "account does not exist",
    "quota exceeded", "mailbox full", "address not found",
    # Deutsch
    "zustellung fehlgeschlagen", "nicht zustellbar", "rückläufer",
    "konnte nicht zugestellt werden",
]
_BOUNCE_SENDERS = [
    "mailer-daemon", "postmaster", "mail delivery subsystem",
    "mail system", "mail delivery", "noreply@", "no-reply@",
]

# Regex: Email-Adresse aus Bounce-Text extrahieren
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')

# ── Datenbank ─────────────────────────────────────────────────────────────────
def _init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS bounced (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            reason TEXT,
            fixed_mailchimp INTEGER DEFAULT 0,
            fixed_klaviyo   INTEGER DEFAULT 0,
            fixed_sequences INTEGER DEFAULT 0,
            detected_at TEXT DEFAULT (datetime('now')),
            fixed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS processed_bounce_uids (
            uid TEXT PRIMARY KEY,
            account TEXT,
            detected_at TEXT DEFAULT (datetime('now'))
        );
        """)

def is_blacklisted(email_addr: str) -> bool:
    """Prüft ob Adresse bereits gebounced/gesperrt ist."""
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        return bool(c.execute("SELECT id FROM bounced WHERE email=?", (email_addr.lower(),)).fetchone())

def _mark_bounce_detected(email_addr: str, reason: str):
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute(
            "INSERT OR IGNORE INTO bounced(email, reason) VALUES(?,?)",
            (email_addr.lower(), reason)
        )

def _mark_fixed(email_addr: str, mailchimp: bool = False, klaviyo: bool = False, sequences: bool = False):
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute(
            "UPDATE bounced SET fixed_mailchimp=?, fixed_klaviyo=?, fixed_sequences=?, fixed_at=? WHERE email=?",
            (int(mailchimp), int(klaviyo), int(sequences), datetime.now().isoformat(), email_addr.lower())
        )

def _is_uid_processed(uid: str) -> bool:
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        return bool(c.execute("SELECT uid FROM processed_bounce_uids WHERE uid=?", (uid,)).fetchone())

def _mark_uid_processed(uid: str, account: str):
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute("INSERT OR IGNORE INTO processed_bounce_uids(uid, account) VALUES(?,?)", (uid, account))

def get_blacklist(limit: int = 200) -> list[dict]:
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as c:
        rows = c.execute(
            "SELECT email, reason, fixed_mailchimp, fixed_klaviyo, fixed_sequences, detected_at "
            "FROM bounced ORDER BY detected_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(zip(["email","reason","mc","kv","seq","ts"], r)) for r in rows]


# ── Telegram Alert ────────────────────────────────────────────────────────────
async def _tg(msg: str):
    tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


# ── Bounce aus Email extrahieren ──────────────────────────────────────────────
def _is_bounce_email(subject: str, sender: str) -> bool:
    s = (subject + " " + sender).lower()
    return (
        any(sig in s for sig in _BOUNCE_SUBJECTS) or
        any(sig in s for sig in _BOUNCE_SENDERS)
    )

def _extract_bounced_address(subject: str, body_text: str, original_sender: str) -> Optional[str]:
    """
    Versucht die fehlerhafte Empfänger-Adresse aus der Bounce-Email zu extrahieren.
    Prüft verschiedene Formate (RFC 3464, Exchange, Google, Postfix).
    """
    # Ausschluss-Adressen — das sind unsere eigenen Sender-Adressen
    _OWN_EMAILS = {
        os.getenv("SMTP_USER", "").lower(),
        os.getenv("BREVO_FROM_EMAIL", "").lower(),
        os.getenv("SENDGRID_FROM_EMAIL", "").lower(),
        "aiitecbuuss@gmail.com",
        "bullpowersrtkennels@gmail.com",
        "b20c16001@smtp-brevo.com",
        "noreply@", "mailer-daemon@", "postmaster@",
    }

    candidates = []

    # RFC 3464: "Final-Recipient: rfc822; email@example.com"
    m = re.search(r'Final-Recipient:\s*rfc822;\s*([^\s\r\n]+)', body_text, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip().lower())

    # "To: email@example.com" in Bounce-Header
    m = re.search(r'(?:To|Delivered-To):\s*<?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>?',
                  body_text, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).lower())

    # "The following address(es) failed:" pattern (Exim/Postfix)
    m = re.search(r'address(?:es)? (?:failed|could not be delivered)[^\n]*\n\s*([^\s\n]+)',
                  body_text, re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip().lower())

    # Alle Email-Adressen aus Body extrahieren und filtern
    all_emails = [e.lower() for e in _EMAIL_RE.findall(body_text)]
    for e in all_emails:
        if not any(own in e for own in _OWN_EMAILS if own):
            candidates.append(e)

    # Ersten validen Kandidaten zurückgeben (kein eigener Absender)
    for c in candidates:
        if "@" in c and not any(own in c for own in _OWN_EMAILS if own):
            if not c.startswith("mailer-daemon") and not c.startswith("postmaster"):
                return c

    return None


# ── Auto-Fix: aus allen Listen entfernen ─────────────────────────────────────
async def _remove_from_mailchimp(email_addr: str) -> bool:
    """Unsubscribe/archive in Mailchimp."""
    key    = os.getenv("MAILCHIMP_API_KEY", "")
    server = os.getenv("MAILCHIMP_SERVER", "us5")
    lst_id = os.getenv("MAILCHIMP_LIST_ID", "")
    if not key or not lst_id:
        return False
    import hashlib
    email_hash = hashlib.md5(email_addr.lower().encode()).hexdigest()
    try:
        async with aiohttp.ClientSession() as s:
            # Setze auf unsubscribed
            async with s.patch(
                f"https://{server}.api.mailchimp.com/3.0/lists/{lst_id}/members/{email_hash}",
                headers={"Authorization": f"apikey {key}"},
                json={"status": "unsubscribed"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status in (200, 204)
    except Exception as e:
        log.warning("Mailchimp remove %s: %s", email_addr, e)
        return False


async def _suppress_in_klaviyo(email_addr: str) -> bool:
    """Email in Klaviyo suppressieren (keine weiteren Emails)."""
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/profile-suppression-bulk-create-jobs/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {key}",
                    "revision": "2024-02-15",
                    "Content-Type": "application/json",
                },
                json={
                    "data": {
                        "type": "profile-suppression-bulk-create-job",
                        "attributes": {
                            "profiles": {"data": [{"type": "profile", "attributes": {"email": email_addr}}]}
                        }
                    }
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status in (200, 201, 202)
    except Exception as e:
        log.warning("Klaviyo suppress %s: %s", email_addr, e)
        return False


def _deactivate_in_sequences(email_addr: str) -> bool:
    """Email-Sequenz-Enrollment deaktivieren."""
    try:
        from modules.email_sequence_engine import _load_db, _save_db
        db = _load_db()
        changed = False
        for enr in db.get("enrollments", []):
            if enr.get("email", "").lower() == email_addr.lower() and enr.get("active", True):
                enr["active"] = False
                changed = True
        if changed:
            _save_db(db)
        return changed
    except Exception as e:
        log.warning("Sequence deactivate %s: %s", email_addr, e)
        return False


def _mark_bounced_in_outreach(email_addr: str) -> bool:
    """Adresse in email_outreach_bulk als bounced markieren."""
    try:
        from modules.email_outreach_bulk import mark_bounced
        return mark_bounced(email_addr)
    except Exception:
        return False


async def fix_bounced_address(email_addr: str, reason: str = "IMAP bounce detected") -> dict:
    """
    Vollständiger Auto-Fix für eine fehlerhafte Email-Adresse.
    Entfernt aus ALLEN Systemen gleichzeitig.
    """
    email_addr = email_addr.lower().strip()
    if not email_addr or "@" not in email_addr:
        return {"ok": False, "error": "Ungültige Adresse"}

    _mark_bounce_detected(email_addr, reason)

    # Parallel: alle Systeme gleichzeitig updaten
    mc_ok, kv_ok = await asyncio.gather(
        _remove_from_mailchimp(email_addr),
        _suppress_in_klaviyo(email_addr),
        return_exceptions=True,
    )
    mc_ok = mc_ok is True
    kv_ok = kv_ok is True
    seq_ok = _deactivate_in_sequences(email_addr)
    out_ok = _mark_bounced_in_outreach(email_addr)

    _mark_fixed(email_addr, mailchimp=mc_ok, klaviyo=kv_ok, sequences=seq_ok)

    fixed_systems = []
    if mc_ok:   fixed_systems.append("Mailchimp")
    if kv_ok:   fixed_systems.append("Klaviyo")
    if seq_ok:  fixed_systems.append("Sequences")
    if out_ok:  fixed_systems.append("Outreach-DB")

    log.info("Bounce-Fix %s: %s", email_addr, fixed_systems)
    return {
        "ok": True,
        "email": email_addr,
        "reason": reason,
        "fixed": fixed_systems,
        "mailchimp": mc_ok,
        "klaviyo": kv_ok,
        "sequences": seq_ok,
        "outreach": out_ok,
    }


# ── IMAP Bounce-Scanner ───────────────────────────────────────────────────────
def _fetch_bounce_emails(user: str, password: str, label: str) -> list[dict]:
    """Scannt Gmail IMAP nach Bounce-Emails (noch nicht verarbeitete)."""
    bounces = []
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(user, password)
        imap.select("INBOX")

        # Suche nach ungelesenen Emails von Mailer-Daemon + ähnlichen
        _, data = imap.search(None, "UNSEEN")
        uid_list = data[0].split() if data[0] else []

        for uid_bytes in uid_list[-50:]:  # max 50 pro Scan
            uid = uid_bytes.decode()
            if _is_uid_processed(uid):
                continue

            # Komplette Email holen (Header + Body)
            _, msg_data = imap.fetch(uid_bytes, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email_lib.message_from_bytes(raw)

            sender  = email_lib.utils.parseaddr(msg.get("From", ""))[1].lower()
            subject = ""
            for part, enc in email_lib.header.decode_header(msg.get("Subject", "")):
                if isinstance(part, bytes):
                    subject += part.decode(enc or "utf-8", errors="replace")
                else:
                    subject += str(part)
            subject = subject.strip()

            if not _is_bounce_email(subject, sender):
                continue

            # Body extrahieren
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "message/delivery-status"):
                        try:
                            body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    body = str(msg.get_payload())

            bounced_addr = _extract_bounced_address(subject, body, sender)
            bounces.append({
                "uid": uid,
                "account": label,
                "sender": sender,
                "subject": subject[:200],
                "bounced_email": bounced_addr,
                "body_snippet": body[:500],
            })
            _mark_uid_processed(uid, label)

            # Email als gelesen markieren (räumt Postfach auf)
            imap.store(uid_bytes, "+FLAGS", "\\Seen")

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.warning("IMAP Bounce-Scan [%s]: %s", label, e)
    except Exception as e:
        log.error("Bounce-Scan [%s]: %s", label, e)
    return bounces


# ── Mailchimp + Klaviyo Bounce-Reports ────────────────────────────────────────
async def check_mailchimp_bounces(campaign_id: str = "") -> list[str]:
    """Holt Bounce-/Fehler-Adressen aus Mailchimp."""
    key    = os.getenv("MAILCHIMP_API_KEY", "")
    server = os.getenv("MAILCHIMP_SERVER", "us5")
    lst_id = os.getenv("MAILCHIMP_LIST_ID", "")
    if not key or not lst_id:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            # Alle Mitglieder mit Status cleaned (hard bounce) oder unsubscribed
            async with s.get(
                f"https://{server}.api.mailchimp.com/3.0/lists/{lst_id}/members",
                headers={"Authorization": f"apikey {key}"},
                params={"status": "cleaned", "count": 100, "fields": "members.email_address"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        return [m["email_address"] for m in data.get("members", [])]
    except Exception as e:
        log.warning("Mailchimp bounce report: %s", e)
        return []


async def check_klaviyo_suppressions() -> list[str]:
    """Holt supprimierte Adressen aus Klaviyo."""
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://a.klaviyo.com/api/profile-suppressions/",
                headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-02-15"},
                params={"page[size]": 50},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        return [p.get("attributes", {}).get("email", "") for p in data.get("data", [])]
    except Exception as e:
        log.warning("Klaviyo suppressions: %s", e)
        return []


# ── MASTER BOUNCE-SCAN + AUTO-FIX ────────────────────────────────────────────
async def run_bounce_fix_cycle() -> dict:
    """
    Kompletter Bounce-Fix-Zyklus:
    1. IMAP-Scan aller Gmail-Konten nach Bounce-Emails
    2. Extrahiere fehlerhafte Adressen
    3. Auto-Fix: aus Mailchimp + Klaviyo + Sequenzen entfernen
    4. Mailchimp/Klaviyo Bounce-Reports prüfen
    5. Telegram-Report
    """
    _init_db()
    start = time.time()
    all_bounced: list[dict] = []
    fixed_count = 0
    already_known = 0

    # IMAP-Accounts holen
    accounts = []
    u1 = os.getenv("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com")
    p1 = os.getenv("GMAIL_APP_PASSWORD_BULLPOWER", "")
    if u1 and p1:
        accounts.append({"user": u1, "password": p1, "label": "BullPower"})
    u2 = os.getenv("GMAIL_USER_PERSONAL", "")
    p2 = os.getenv("GMAIL_APP_PASSWORD_PERSONAL", "")
    if u2 and p2 and u2 != u1:
        accounts.append({"user": u2, "password": p2, "label": "Personal"})

    # 1. IMAP Bounce-Scan (sync, in executor)
    loop = asyncio.get_event_loop()
    for acc in accounts:
        bounces = await loop.run_in_executor(
            None, _fetch_bounce_emails, acc["user"], acc["password"], acc["label"]
        )
        all_bounced.extend(bounces)

    # 2. Mailchimp Bounce-Report
    mc_bounced = await check_mailchimp_bounces()
    for email_addr in mc_bounced:
        if email_addr and not is_blacklisted(email_addr):
            all_bounced.append({"bounced_email": email_addr, "subject": "Mailchimp Hard Bounce", "uid": None})

    # 3. Auto-Fix für alle gefundenen
    fix_results = []
    for b in all_bounced:
        addr = b.get("bounced_email")
        if not addr:
            continue
        if is_blacklisted(addr):
            already_known += 1
            continue

        result = await fix_bounced_address(
            addr,
            reason=b.get("subject", "IMAP bounce")[:200]
        )
        if result.get("ok"):
            fixed_count += 1
            fix_results.append(result)

    elapsed = round(time.time() - start, 1)

    # 4. Telegram-Report
    if fix_results:
        lines = [f"🔧 <b>Bounce Auto-Fix</b> ({elapsed}s)\n"]
        lines.append(f"✅ {fixed_count} fehlerhafte Adressen gefixed\n")
        for r in fix_results[:10]:
            sys_str = ", ".join(r.get("fixed", []))
            lines.append(f"• <code>{r['email']}</code> → {sys_str}")
        if len(fix_results) > 10:
            lines.append(f"…+{len(fix_results)-10} weitere")
        await _tg("\n".join(lines))
        log.info("Bounce-Fix: %d gefixed, %d bereits bekannt", fixed_count, already_known)
    else:
        log.info("Bounce-Scan: keine neuen Bounces (%d bereits bekannt)", already_known)

    return {
        "ok": True,
        "scanned_accounts": len(accounts),
        "bounces_found": len(all_bounced),
        "fixed": fixed_count,
        "already_known": already_known,
        "elapsed": elapsed,
    }


# ── Wird direkt nach Email-Versand aufgerufen ─────────────────────────────────
async def post_send_check(emails_sent: list[str], wait_seconds: int = 30) -> dict:
    """
    Nach Email-Versand aufrufen. Wartet kurz dann prüft IMAP auf Bounces.
    Empfehlung: await post_send_check(sent_emails, wait_seconds=30)
    """
    if wait_seconds > 0:
        await asyncio.sleep(min(wait_seconds, 60))
    return await run_bounce_fix_cycle()


if __name__ == "__main__":
    import sys, json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if "--stats" in sys.argv:
        print(json.dumps({"blacklist_count": len(get_blacklist()), "recent": get_blacklist(10)}, indent=2, ensure_ascii=False))
    else:
        result = asyncio.run(run_bounce_fix_cycle())
        print(json.dumps(result, indent=2, ensure_ascii=False))
