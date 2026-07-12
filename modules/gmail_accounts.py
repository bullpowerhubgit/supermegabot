#!/usr/bin/env python3
"""Zentrale Gmail/SMTP-Konten-Verwaltung — alle 8 Konten, Round-Robin, Fallback."""
from __future__ import annotations

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

DEFAULT_EMAILS: Dict[int, str] = {
    1: "dragonadnp@gmail.com",
    2: "nikolestimi@gmail.com",
    3: "bullpowersrtkennels@gmail.com",
    4: "looopwave@gmail.com",
    5: "aiitecbuuss@gmail.com",
    6: "rudolf.sarkany@aitec.de",
    7: "rudolf.sarkany.aiitec@gmail.com",
    8: "rudolfsarkany1984@gmail.com",
}

ALIASES: List[Tuple[str, str, int]] = [
    ("GMAIL_USER_AIITEC", "GMAIL_APP_PASSWORD_AIITEC", 5),
    ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER", 3),
    ("GMAIL_USER", "GMAIL_APP_PASSWORD", 0),
]

_rr_idx = 0


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


def configured_accounts() -> List[GmailAccount]:
    return [a for a in list_accounts() if a.configured]


def pick_account() -> Optional[GmailAccount]:
    """Round-Robin über konfigurierte Konten."""
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
    try:
        ctx = ssl.create_default_context()
        if account.smtp_port == 465:
            with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=timeout, context=ctx) as s:
                s.login(account.email, account.password.replace(" ", ""))
        else:
            with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=timeout) as s:
                s.starttls(context=ctx)
                s.login(account.email, account.password.replace(" ", ""))
        return {"ok": True, "email": account.email, "host": account.smtp_host}
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
        try:
            msg = _build_message(acc, to_email, subject, body, html=html)
            _smtp_send(acc, msg, to_email)
            log.info("SMTP → %s via %s", to_email, acc.email)
            return True, acc.email
        except Exception as e:
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