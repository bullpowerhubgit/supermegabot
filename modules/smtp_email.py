#!/usr/bin/env python3
"""SMTP email fallback — uses Gmail or custom SMTP when other providers fail"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("SMTP")


async def send_email(to_email: str, subject: str, html_body: str, from_email: str = "") -> dict:
    """Send email via alle konfigurierten Gmail-Konten (Round-Robin + Fallback)."""
    from modules.email_guard import validate_email
    ok_guard, guard_errors = validate_email(subject, html_body, to_email)
    if not ok_guard:
        log.warning("EmailGuard BLOCK — Email nicht gesendet: %s", guard_errors)
        return {"ok": False, "blocked": True, "errors": guard_errors}

    from modules.gmail_accounts import send_email as ga_send
    ok, via = ga_send(to_email, subject, "", html=html_body)
    if ok:
        log.info("SMTP email sent to %s via %s — subject: %s", to_email, via, subject)
        return {"ok": True, "to": to_email, "subject": subject, "from": via or from_email}
    return {"ok": False, "error": "alle Gmail-Konten fehlgeschlagen oder nicht konfiguriert"}


async def get_status() -> dict:
    from modules.gmail_accounts import get_status as ga_status
    s = ga_status()
    return {"ok": s["configured"] > 0, "configured": s["configured"], **s}
