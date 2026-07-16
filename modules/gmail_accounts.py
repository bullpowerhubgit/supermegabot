#!/usr/bin/env python3
"""Zentrale Gmail/SMTP-Konten-Verwaltung — alle 8 Konten, Round-Robin, Fallback."""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("GmailAccounts")

SECRETS_FILE = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "gmail_secrets.json"

DEFAULT_EMAILS: Dict[int, str] = {
    1: "dragonadnp@gmail.com",
    3: "bullpowersrtkennels@gmail.com",
    5: "aiitecbuuss@gmail.com",
    7: "rudolf.sarkany.aiitec@gmail.com",
    8: "rudolfsarkany1984@gmail.com",
}

ALIASES: List[Tuple[str, str, int]] = [
    ("GMAIL_USER_AIITEC", "GMAIL_APP_PASSWORD_AIITEC", 5),
    ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER", 3),
    ("GMAIL_USER", "GMAIL_APP_PASSWORD", 0),
]

_rr_idx = 0
_GMAIL_DAILY_EXHAUSTED: set = set()  # Session-persistentes Set für 550-5.4.5-Accounts
_GMAIL_AUTH_FAILED: set = set()  # BadCredentials — bis Restart/Refresh deaktiviert

# Permanently skip accounts known bad until password rotated (env override)
_DISABLED_ACCOUNTS_ENV = "GMAIL_DISABLED_INDEXES"  # e.g. "4,2"

# ── Globaler Tages-Counter (verhindert 550-Overruns) ─────────────────────────
import sqlite3 as _sqlite3
import time as _time

_COUNTER_DB = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data")) / "email_guard.db"
MAX_PER_ACCOUNT_PER_DAY = 80   # 5 Konten × 80 = 400/Tag Gesamt-Pool

def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()

def _init_counter_db() -> None:
    try:
        _COUNTER_DB.parent.mkdir(parents=True, exist_ok=True)
        c = _sqlite3.connect(_COUNTER_DB)
        c.execute("""CREATE TABLE IF NOT EXISTS smtp_daily_counts (
            account TEXT, date TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (account, date)
        )""")
        c.commit(); c.close()
    except Exception:
        pass

try:
    _init_counter_db()
except Exception:
    pass

def _account_count_today(email: str) -> int:
    try:
        c = _sqlite3.connect(_COUNTER_DB)
        row = c.execute(
            "SELECT count FROM smtp_daily_counts WHERE account=? AND date=?",
            (email.lower(), _today())
        ).fetchone()
        c.close()
        return row[0] if row else 0
    except Exception:
        return 0

def _increment_count(email: str) -> None:
    try:
        c = _sqlite3.connect(_COUNTER_DB)
        c.execute("""INSERT INTO smtp_daily_counts(account,date,count) VALUES(?,?,1)
                     ON CONFLICT(account,date) DO UPDATE SET count=count+1""",
                  (email.lower(), _today()))
        c.commit(); c.close()
    except Exception:
        pass

def _is_account_at_limit(email: str) -> bool:
    return _account_count_today(email) >= MAX_PER_ACCOUNT_PER_DAY


def _load_secrets() -> Dict[str, str]:
    """Runtime-Passwörter aus data/gmail_secrets.json (nicht in Git)."""
    if not SECRETS_FILE.exists():
        return {}
    try:
        import json
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (data.get("passwords") or data).items()}
    except Exception:
        return {}


def _save_secret(index: int, password: str) -> None:
    import json
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {"passwords": _load_secrets()}
    data["passwords"][str(index)] = password.strip()
    SECRETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


@dataclass
class GmailAccount:
    index: int
    email: str
    password: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    label: str

    @property
    def configured(self) -> bool:
        return bool(self.email and self.password)


def _password_for(index: int) -> str:
    secrets = _load_secrets()
    if secrets.get(str(index)):
        return secrets[str(index)].strip()
    pwd = os.getenv(f"GMAIL_APP_PASSWORD_{index}", "").strip()
    if pwd:
        return pwd
    for user_key, pass_key, idx in ALIASES:
        if idx == index:
            return os.getenv(pass_key, "").strip()
    return ""


def _email_for(index: int) -> str:
    return (
        os.getenv(f"GMAIL_USER_{index}", "").strip()
        or DEFAULT_EMAILS.get(index, "")
    )


def _hosts_for(index: int, email: str) -> Tuple[str, int, str]:
    if index == 6 or email.endswith("@aitec.de"):
        smtp = os.getenv("SMTP_HOST_6", "smtp.strato.de")
        imap = os.getenv("IMAP_HOST_6", "imap.strato.de")
        return smtp, 465, imap
    return "smtp.gmail.com", 465, "imap.gmail.com"


def list_accounts() -> List[GmailAccount]:
    """Alle 8 Konten — mit oder ohne Passwort."""
    seen: set[str] = set()
    accounts: List[GmailAccount] = []
    for i in range(1, 9):
        email = _email_for(i)
        if not email or email in seen:
            continue
        seen.add(email)
        smtp_host, smtp_port, imap_host = _hosts_for(i, email)
        accounts.append(GmailAccount(
            index=i,
            email=email,
            password=_password_for(i),
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            imap_host=imap_host,
            label=f"konto_{i}",
        ))
    return accounts


def _disabled_indexes() -> set[int]:
    raw = os.getenv(_DISABLED_ACCOUNTS_ENV, "4").strip()  # default: disable #4 looopwave until rotated
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def configured_accounts() -> List[GmailAccount]:
    disabled = _disabled_indexes()
    return [
        a for a in list_accounts()
        if a.configured
        and a.index not in disabled
        and a.email.lower() not in _GMAIL_AUTH_FAILED
        and a.email not in _GMAIL_DAILY_EXHAUSTED
    ]


def pick_account() -> Optional[GmailAccount]:
    """Round-Robin über konfigurierte, nicht-gesperrte Konten."""
    global _rr_idx
    pool = configured_accounts()
    if not pool:
        return None
    acc = pool[_rr_idx % len(pool)]
    _rr_idx += 1
    return acc


def test_smtp(account: GmailAccount, timeout: int = 12) -> Dict[str, Any]:
    if not account.configured:
        return {"ok": False, "email": account.email, "error": "no_password"}
    if account.index in _disabled_indexes():
        return {"ok": False, "email": account.email, "error": "disabled_until_password_rotated"}
    try:
        ctx = ssl.create_default_context()
        if account.smtp_port == 465:
            with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=timeout, context=ctx) as s:
                s.login(account.email, account.password.replace(" ", ""))
        else:
            with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=timeout) as s:
                s.starttls(context=ctx)
                s.login(account.email, account.password.replace(" ", ""))
        _GMAIL_AUTH_FAILED.discard(account.email.lower())
        return {"ok": True, "email": account.email, "host": account.smtp_host}
    except smtplib.SMTPAuthenticationError as e:
        _GMAIL_AUTH_FAILED.add(account.email.lower())
        log.warning("Gmail AUTH failed — disabled for session: %s", account.email)
        return {"ok": False, "email": account.email, "error": f"auth_failed: {str(e)[:80]}"}
    except Exception as e:
        return {"ok": False, "email": account.email, "error": str(e)[:120]}


def test_all_accounts() -> Dict[str, Any]:
    results = [test_smtp(a) for a in list_accounts()]
    ok = [r for r in results if r.get("ok")]
    return {
        "total": len(results),
        "configured": sum(1 for a in list_accounts() if a.configured),
        "working": len(ok),
        "accounts": results,
    }


def _build_message(
    account: GmailAccount,
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    attachment_path: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative" if html else "mixed")
    msg["Subject"] = subject
    msg["From"] = account.email
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    data = attachment_bytes
    fname = attachment_name
    if not data and attachment_path and Path(attachment_path).exists():
        data = Path(attachment_path).read_bytes()
        fname = fname or Path(attachment_path).name
    if data:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{fname or "attachment"}"')
        msg.attach(part)
    return msg


def _smtp_send(account: GmailAccount, msg: MIMEMultipart, to_email: str, timeout: int = 25) -> None:
    ctx = ssl.create_default_context()
    if account.smtp_port == 465:
        with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=timeout, context=ctx) as s:
            s.login(account.email, account.password.replace(" ", ""))
            s.send_message(msg)
    else:
        with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=timeout) as s:
            s.starttls(context=ctx)
            s.login(account.email, account.password.replace(" ", ""))
            s.send_message(msg)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    account_index: Optional[int] = None,
) -> Tuple[bool, str]:
    """Versendet via einem Konto; bei Fehler alle anderen probieren."""
    pool: List[GmailAccount]
    if account_index:
        pool = [a for a in list_accounts() if a.index == account_index and a.configured]
    else:
        first = pick_account()
        rest = [a for a in configured_accounts() if not first or a.email != first.email]
        pool = ([first] if first else []) + rest

    if not pool:
        log.warning("Kein Gmail-Konto mit Passwort konfiguriert")
        return False, ""

    for acc in pool:
        if acc.email in _GMAIL_DAILY_EXHAUSTED:
            continue
        if _is_account_at_limit(acc.email):
            log.warning("SMTP %s Tages-Cap (%d) erreicht — übersprungen", acc.email, MAX_PER_ACCOUNT_PER_DAY)
            continue
        if acc.email.lower() in _GMAIL_AUTH_FAILED or acc.index in _disabled_indexes():
            continue
        try:
            msg = _build_message(acc, to_email, subject, body, html=html)
            _smtp_send(acc, msg, to_email)
            _increment_count(acc.email)
            log.info("SMTP → %s via %s (%d/%d heute)", to_email, acc.email,
                     _account_count_today(acc.email), MAX_PER_ACCOUNT_PER_DAY)
            return True, acc.email
        except smtplib.SMTPAuthenticationError as e:
            _GMAIL_AUTH_FAILED.add(acc.email.lower())
            log.warning("SMTP AUTH fail — skip account for session: %s (%s)", acc.email, e)
            continue
        except smtplib.SMTPDataError as e:
            if e.smtp_code == 550 and b"5.4.5" in (e.smtp_error or b""):
                _GMAIL_DAILY_EXHAUSTED.add(acc.email)
                log.warning("SMTP %s Tageslimit (Gmail 550) — für heute deaktiviert", acc.email)
            else:
                log.warning("SMTP %s fehlgeschlagen: %s", acc.email, e)
        except smtplib.SMTPRecipientsRefused as e:
            # 550 on recipient = hard bounce (user unknown) — block recipient, NOT our account
            for refused_email, (code, msg) in (e.recipients or {}).items():
                code_s = str(code)
                msg_s = (msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg))[:120]
                if code_s.startswith("55"):
                    try:
                        from modules.bounce_watcher import mark_bounced
                        mark_bounced(refused_email or to_email, f"SMTP {code_s}: {msg_s}")
                        log.warning("Hard bounce → blocklist: %s (%s)", refused_email or to_email, msg_s)
                    except Exception as be:
                        log.debug("mark_bounced failed: %s", be)
            # Only treat as sender daily limit if Gmail quota wording
            blob = str(e.recipients)
            if "5.4.5" in blob or "Daily user sending limit" in blob:
                _GMAIL_DAILY_EXHAUSTED.add(acc.email)
                log.warning("SMTP %s Tageslimit (Recipients 550 quota) — für heute deaktiviert", acc.email)
            else:
                log.warning("SMTP %s recipient refused: %s", acc.email, e)
        except Exception as e:
            err_str = str(e)
            if "5.4.5" in err_str or "Daily user sending limit" in err_str:
                _GMAIL_DAILY_EXHAUSTED.add(acc.email)
                log.warning("SMTP %s Tageslimit (Gmail 550) — für heute deaktiviert", acc.email)
            else:
                log.warning("SMTP %s fehlgeschlagen: %s", acc.email, e)
    return False, ""


def send_email_with_attachment(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
    account_index: Optional[int] = None,
) -> Tuple[bool, str]:
    pool: List[GmailAccount]
    if account_index:
        pool = [a for a in list_accounts() if a.index == account_index and a.configured]
    else:
        first = pick_account()
        rest = [a for a in configured_accounts() if not first or a.email != first.email]
        pool = ([first] if first else []) + rest

    if not pool:
        return False, ""

    for acc in pool:
        try:
            msg = _build_message(
                acc, to_email, subject, body,
                attachment_path=attachment_path,
                attachment_bytes=attachment_bytes,
                attachment_name=attachment_name,
            )
            _smtp_send(acc, msg, to_email)
            log.info("SMTP+Anhang → %s via %s", to_email, acc.email)
            return True, acc.email
        except Exception as e:
            log.warning("SMTP+Anhang %s fehlgeschlagen: %s", acc.email, e)
    return False, ""


async def async_send_email(
    to_email: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    account_index: Optional[int] = None,
) -> Tuple[bool, str]:
    """Async wrapper — runs blocking SMTP in thread pool so the event loop stays free."""
    return await asyncio.to_thread(send_email, to_email, subject, body, html, account_index)


async def async_send_email_with_attachment(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_name: Optional[str] = None,
    account_index: Optional[int] = None,
) -> Tuple[bool, str]:
    """Async wrapper for send_email_with_attachment."""
    return await asyncio.to_thread(
        send_email_with_attachment,
        to_email, subject, body,
        attachment_path, attachment_bytes, attachment_name, account_index,
    )


def get_status() -> Dict[str, Any]:
    accounts = list_accounts()
    return {
        "total_accounts": len(accounts),
        "configured": sum(1 for a in accounts if a.configured),
        "accounts": [
            {"index": a.index, "email": a.email, "configured": a.configured, "host": a.smtp_host}
            for a in accounts
        ],
    }


def configure_account(index: int, password: str, email: str = "") -> Dict[str, Any]:
    """App-Passwort speichern + SMTP testen. index 1-8."""
    if not 1 <= index <= 8:
        return {"ok": False, "error": "index muss 1-8 sein"}
    if not password or len(password.replace(" ", "")) < 8:
        return {"ok": False, "error": "App-Passwort fehlt oder ungültig"}
    if email:
        os.environ[f"GMAIL_USER_{index}"] = email.strip()
    _save_secret(index, password)
    acc = next((a for a in list_accounts() if a.index == index), None)
    if not acc:
        return {"ok": False, "error": "Konto nicht gefunden"}
    acc = GmailAccount(
        index=acc.index, email=email or acc.email, password=password.strip(),
        smtp_host=acc.smtp_host, smtp_port=acc.smtp_port,
        imap_host=acc.imap_host, label=acc.label,
    )
    test = test_smtp(acc)
    railway_synced = False
    if test.get("ok"):
        try:
            import subprocess
            r = subprocess.run(
                ["railway", "variables", "set", f"GMAIL_APP_PASSWORD_{index}={password.strip()}"],
                capture_output=True, text=True, timeout=15,
            )
            railway_synced = r.returncode == 0
        except Exception:
            pass
    return {
        "ok": test.get("ok", False),
        "index": index,
        "email": acc.email,
        "smtp": test,
        "railway_synced": railway_synced,
        "message": "Konto aktiv" if test.get("ok") else test.get("error", "SMTP fehlgeschlagen"),
    }