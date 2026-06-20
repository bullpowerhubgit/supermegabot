#!/usr/bin/env python3
"""SMTP email fallback — uses Gmail or custom SMTP when other providers fail"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("SMTP")


async def send_email(to_email: str, subject: str, html_body: str, from_email: str = "") -> dict:
    """Send email via SMTP. Supports Gmail (set SMTP_USER + SMTP_PASS env vars)."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", os.getenv("GMAIL_USER", ""))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("GMAIL_APP_PASSWORD", ""))
    from_addr = from_email or smtp_user

    if not smtp_user or not smtp_pass:
        return {"ok": False, "error": "SMTP_USER/SMTP_PASS not configured"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_email, msg.as_string())

        log.info("SMTP email sent to %s — subject: %s", to_email, subject)
        return {"ok": True, "to": to_email, "subject": subject}
    except Exception as e:
        log.error("SMTP error: %s", e)
        return {"ok": False, "error": str(e)}


async def get_status() -> dict:
    smtp_user = os.getenv("SMTP_USER", os.getenv("GMAIL_USER", ""))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("GMAIL_APP_PASSWORD", ""))
    configured = bool(smtp_user and smtp_pass)
    return {
        "ok": configured,
        "configured": configured,
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user_set": bool(smtp_user),
    }
