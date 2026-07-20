#!/usr/bin/env python3
"""
Zentraler Email-Versand — SendGrid API primär, Gmail SMTP nur als Notfall-Fallback.

WARUM: Gmail App-Passwörter werden von Google automatisch revoziert wenn
verdächtiges Sendeverhalten erkannt wird. SendGrid-API-Keys sind stabil.
"""
import logging
import os

import aiohttp

log = logging.getLogger("SmtpEmail")

_SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")
_FROM_EMAIL   = os.getenv("SENDGRID_FROM_EMAIL", "aiitecbuuss@gmail.com")
_FROM_NAME    = os.getenv("SENDGRID_FROM_NAME", "AiiteC")


async def _send_via_sendgrid(to_email: str, subject: str, html_body: str) -> dict:
    """Sendet via SendGrid Web API v3 — kein SMTP, keine App-Passwörter."""
    if not _SENDGRID_KEY:
        return {"ok": False, "error": "SENDGRID_API_KEY nicht gesetzt"}
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": _FROM_EMAIL, "name": _FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {_SENDGRID_KEY}",
                         "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status in (200, 202):
                    log.info("SendGrid ✅ → %s | %s", to_email, subject[:60])
                    return {"ok": True, "via": "sendgrid", "to": to_email}
                body = await r.text()
                log.warning("SendGrid %d: %s", r.status, body[:200])
                return {"ok": False, "error": f"SendGrid {r.status}: {body[:100]}"}
    except Exception as e:
        log.warning("SendGrid Fehler: %s", e)
        return {"ok": False, "error": str(e)}


async def send_email(to_email: str, subject: str, html_body: str, from_email: str = "") -> dict:
    """
    Hauptfunktion: SendGrid primär → Gmail SMTP nur wenn SendGrid nicht konfiguriert.
    Gmail App-Passwörter werden NIE für Massen-Versand genutzt.
    """
    from modules.email_guard import validate_email
    ok_guard, guard_errors = validate_email(subject, html_body, to_email)
    if not ok_guard:
        log.warning("EmailGuard BLOCK: %s", guard_errors)
        return {"ok": False, "blocked": True, "errors": guard_errors}

    # 1. SendGrid (primär — stabile API, kein App-Passwort)
    if _SENDGRID_KEY:
        result = await _send_via_sendgrid(to_email, subject, html_body)
        if result["ok"]:
            try:
                from modules.email_guard import register_sent
                register_sent(to_email, subject, html_body)
            except Exception:
                pass
            return result

    # 2. Gmail SMTP (nur als letzter Ausweg — NUR für einzelne System-Mails)
    log.warning("SendGrid nicht verfügbar — Gmail SMTP Fallback für %s", to_email)
    try:
        from modules.gmail_accounts import send_email as ga_send
        ok, via = ga_send(to_email, subject, "", html=html_body)
        if ok:
            log.info("Gmail SMTP Fallback ✅ via %s → %s", via, to_email)
            try:
                from modules.email_guard import register_sent
                register_sent(to_email, subject, html_body)
            except Exception:
                pass
            return {"ok": True, "to": to_email, "subject": subject, "via": via}
    except Exception as e:
        log.warning("Gmail SMTP Fallback Fehler: %s", e)

    return {"ok": False, "error": "SendGrid + Gmail beide fehlgeschlagen"}


async def _delayed_bounce_check(to_email: str) -> None:
    import asyncio
    await asyncio.sleep(30)
    try:
        from modules.bounce_watcher import run_bounce_watcher
        await run_bounce_watcher()
    except Exception:
        pass


async def get_status() -> dict:
    sg_ok = bool(_SENDGRID_KEY)
    try:
        from modules.gmail_accounts import get_status as ga_status
        gs = ga_status()
        gmail_configured = gs.get("configured", 0)
    except Exception:
        gmail_configured = 0
    return {
        "ok": sg_ok or gmail_configured > 0,
        "sendgrid": sg_ok,
        "gmail_fallback": gmail_configured,
        "primary": "sendgrid" if sg_ok else "gmail_smtp",
    }
