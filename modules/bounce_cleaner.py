#!/usr/bin/env python3
"""
IMAP Bounce-Cleaner — alle 6 Minuten Bounce/DSN-Mails auto-löschen.
Bounced Empfänger werden in bounce_blacklist.db gesperrt.
"""
from __future__ import annotations

import asyncio
import imaplib
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("BounceCleaner")

_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_DB_PATH  = _DATA_DIR / "bounce_blacklist.db"
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

_BOUNCE_FROM_PATTERN = re.compile(
    r'mailer-daemon|postmaster|mail.*delivery|delivery.*fail|'
    r'noreply.*bounce|bounce.*noreply|daemon@',
    re.IGNORECASE,
)
_BOUNCE_SUBJ_PATTERN = re.compile(
    r'delivery status notification|mail delivery fail|undeliverable|'
    r'unzustellbar|konnte nicht zugestellt|failure notice|returned mail|'
    r'lieferung fehlgeschlagen|message not delivered|could not deliver|'
    r'address not found|user unknown|mailbox unavailable|bounce',
    re.IGNORECASE,
)
_RCPT_RE = re.compile(
    r'(?:failed recipient|the following address.*?failed|'
    r'final-recipient|rcpt to|to:)\s*[:\<]?\s*'
    r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE | re.DOTALL,
)

_GMAIL_TRASH = "[Gmail]/Trash"


def _init_db() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS bounced (
        email TEXT PRIMARY KEY,
        reason TEXT,
        ts TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cleaner_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account TEXT,
        deleted INTEGER,
        ts TEXT
    )""")
    c.commit()
    c.close()


def _add_bounced(emails: List[str], reason: str) -> None:
    if not emails:
        return
    ts = datetime.now(timezone.utc).isoformat()
    c = sqlite3.connect(_DB_PATH)
    for em in emails:
        try:
            c.execute(
                "INSERT OR IGNORE INTO bounced(email,reason,ts) VALUES(?,?,?)",
                (em.lower().strip(), reason[:200], ts),
            )
        except Exception:
            pass
    c.commit()
    c.close()


def _build_imap_search() -> str:
    """IMAP OR-Suche für alle Bounce-Patterns."""
    return (
        '(OR OR OR '
        'FROM "mailer-daemon" '
        'SUBJECT "Delivery Status Notification" '
        'SUBJECT "Mail delivery failed" '
        '(OR SUBJECT "Undeliverable" SUBJECT "unzustellbar"))'
    )


def _extract_rcpt_from_body(raw: bytes) -> List[str]:
    text = raw.decode(errors="replace")
    return list({m.lower() for m in _RCPT_RE.findall(text) if "@" in m})


def _delete_messages_imap(imap: imaplib.IMAP4_SSL, msg_ids: List[bytes]) -> Tuple[int, List[str]]:
    """Mails in Papierkorb verschieben. Gibt (Anzahl, bounced_emails) zurück."""
    if not msg_ids:
        return 0, []
    bounced: List[str] = []
    deleted = 0
    chunk_size = 50
    for i in range(0, len(msg_ids), chunk_size):
        chunk = msg_ids[i : i + chunk_size]
        id_str = b",".join(chunk).decode()
        # Körper holen für Bounce-Adresse
        try:
            typ, data = imap.fetch(id_str, "(BODY[])")
            if data:
                for part in data:
                    if isinstance(part, tuple) and len(part) > 1:
                        bounced.extend(_extract_rcpt_from_body(part[1]))
        except Exception:
            pass
        # In Papierkorb kopieren
        try:
            imap.copy(id_str, _GMAIL_TRASH)
        except Exception:
            pass
        # Als gelöscht markieren
        try:
            imap.store(id_str, "+FLAGS", "\\Deleted")
        except Exception:
            pass
        deleted += len(chunk)
    try:
        imap.expunge()
    except Exception:
        pass
    return deleted, list(set(bounced))


async def _send_telegram(msg: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                json={"chat_id": _TG_CHAT, "text": msg[:4000], "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.debug("Telegram send failed: %s", e)


async def run_bounce_cleaner(full_scan: bool = False) -> Dict:
    """
    Verbindet alle IMAP-Konten, löscht Bounce/DSN-Mails, trägt Bounces in DB ein.

    Args:
        full_scan: True = ALLE Mails (inkl. gesehen), False = nur UNSEEN (Standard)

    Returns:
        {"ok": True, "deleted": N, "accounts": {email: count}}
    """
    _init_db()

    try:
        from modules.gmail_accounts import configured_accounts
        accounts = configured_accounts()
    except Exception as e:
        return {"ok": False, "error": str(e), "deleted": 0}

    total_deleted = 0
    per_account: Dict[str, int] = {}
    all_bounced: List[str] = []

    for acc in accounts:
        if not acc.configured or not acc.imap_host:
            continue
        try:
            imap = imaplib.IMAP4_SSL(acc.imap_host, timeout=20)
            imap.login(acc.email, acc.password.replace(" ", ""))
            imap.select("INBOX")

            # Suche aufbauen
            search_criterion = _build_imap_search()
            if not full_scan:
                search_criterion = f"(UNSEEN {search_criterion})"

            typ, ids_raw = imap.search(None, search_criterion)
            if typ != "OK" or not ids_raw or not ids_raw[0]:
                imap.logout()
                per_account[acc.email] = 0
                continue

            msg_ids = ids_raw[0].split()
            if not msg_ids:
                imap.logout()
                per_account[acc.email] = 0
                continue

            log.info("BounceCleaner %s: %d Bounce-Mails gefunden", acc.email, len(msg_ids))
            n_deleted, bounced = _delete_messages_imap(imap, msg_ids)
            imap.logout()

            per_account[acc.email] = n_deleted
            total_deleted += n_deleted
            all_bounced.extend(bounced)
            if n_deleted:
                log.info("BounceCleaner %s: %d Mails gelöscht", acc.email, n_deleted)

        except imaplib.IMAP4.error as e:
            log.warning("BounceCleaner IMAP Fehler %s: %s", acc.email, str(e)[:80])
            per_account[acc.email] = -1
        except Exception as e:
            log.warning("BounceCleaner Fehler %s: %s", acc.email, str(e)[:80])
            per_account[acc.email] = -1

    # Bounced Adressen in DB
    if all_bounced:
        _add_bounced(list(set(all_bounced)), "imap_bounce_dsn")

    # Telegram-Alert nur wenn Bounces gelöscht
    if total_deleted > 0:
        lines = "\n".join(f"  {em}: {n}" for em, n in per_account.items() if n > 0)
        await _send_telegram(
            f"🗑️ *Bounce-Cleaner*: {total_deleted} Mails gelöscht\n{lines}"
        )

    return {
        "ok": True,
        "deleted": total_deleted,
        "accounts": per_account,
        "bounced_blocked": len(set(all_bounced)),
    }


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    result = asyncio.run(run_bounce_cleaner(full_scan=True))
    print(result)
