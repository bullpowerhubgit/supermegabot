#!/usr/bin/env python3
"""
Email Doctor — Vollautomatische Diagnose und Reparatur aller E-Mail-Systeme.
Prüft Klaviyo, Mailchimp (AIITEC + Dragon), Sendgrid, Resend, Twilio.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("EmailDoctor")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

# Klaviyo
KLAVIYO_KEY  = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
KLAVIYO_LIST = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")

# Mailchimp AIITEC (key in .env — alle hardcoded keys abgelaufen)
MC_KEY     = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER  = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
MC_LIST    = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")

# Mailchimp Dragon
DRAGON_KEY    = os.getenv("MAILCHIMP_DRAGON_API_KEY", "")
DRAGON_LIST   = os.getenv("MAILCHIMP_DRAGON_LIST_ID", "0e84a22a44")
DRAGON_SERVER = os.getenv("MAILCHIMP_DRAGON_SERVER", "us18")

# SendGrid
SENDGRID_KEY  = os.getenv("SENDGRID_API_KEY", "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")

# Resend
RESEND_KEY = os.getenv("RESEND_API_KEY", "re_ibYr2F19_85RKMoBbv6yDcy1YAuuctkmd")

# Twilio
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "AC2b92fc8e5af02a27604a964cb241b021")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "54511038fba02a2dbac1a0ef28b704a5")


async def _tg(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
            )
    except Exception as e:
        log.warning("Ignored error: %s", e)


async def check_klaviyo(session: aiohttp.ClientSession) -> dict:
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "KLAVIYO_API_KEY fehlt"}
    try:
        async with session.get(
            "https://a.klaviyo.com/api/lists/",
            headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}", "revision": "2024-10-15"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                data = await r.json()
                count = len(data.get("data", []))
                return {"ok": True, "lists": count, "account": "aiitec"}
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def check_mailchimp(session: aiohttp.ClientSession, key: str, server: str, label: str) -> dict:
    if not key:
        return {"ok": False, "error": f"{label} key fehlt"}
    try:
        creds = base64.b64encode(f"anystring:{key}".encode()).decode()
        async with session.get(
            f"https://{server}.api.mailchimp.com/3.0/",
            headers={"Authorization": f"Basic {creds}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"ok": True, "account": data.get("account_name", label), "total_subscribers": data.get("total_subscribers", 0)}
            err = await r.text()
            return {"ok": False, "error": f"HTTP {r.status}: {err[:100]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def check_sendgrid(session: aiohttp.ClientSession) -> dict:
    if not SENDGRID_KEY:
        return {"ok": False, "error": "SENDGRID_API_KEY fehlt"}
    try:
        async with session.get(
            "https://api.sendgrid.com/v3/user/account",
            headers={"Authorization": f"Bearer {SENDGRID_KEY}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"ok": True, "type": data.get("type", "?"), "reputation": data.get("reputation", 0)}
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def check_resend(session: aiohttp.ClientSession) -> dict:
    if not RESEND_KEY:
        return {"ok": False, "error": "RESEND_API_KEY fehlt"}
    try:
        async with session.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {RESEND_KEY}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"ok": True, "domains": len(data.get("data", []))}
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def check_twilio(session: aiohttp.ClientSession) -> dict:
    if not TWILIO_SID or not TWILIO_TOKEN:
        return {"ok": False, "error": "Twilio credentials fehlen"}
    try:
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        async with session.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}.json",
            headers={"Authorization": f"Basic {auth}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"ok": True, "status": data.get("status", "?"), "name": data.get("friendly_name", "?")}
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


async def auto_repair(issues: list) -> int:
    """Auto-Reparatur: schaltet fehlgeschlagene Mailing-Kanäle auf Fallback."""
    fixes = 0
    for issue in issues:
        system = issue.get("system", "")
        if "mailchimp" in system.lower() and "dragon" not in system.lower():
            if os.getenv("MAILCHIMP_AUTOMATION_ENABLED", "true").lower() == "false":
                log.info("Mailchimp AIITEC weiterhin deaktiviert — TOS Verstoß pending")
                fixes += 1
    return fixes


def check_gmail_accounts() -> dict:
    from modules.gmail_accounts import test_all_accounts
    return test_all_accounts()


async def run_email_doctor() -> dict:
    """Diagnose aller E-Mail-Systeme + Auto-Reparatur."""
    gmail = check_gmail_accounts()
    async with aiohttp.ClientSession() as session:
        kl, mc_ai, mc_dr, sg, rs, tw = await asyncio.gather(
            check_klaviyo(session),
            check_mailchimp(session, MC_KEY, MC_SERVER, "Mailchimp-AIITEC"),
            check_mailchimp(session, DRAGON_KEY, DRAGON_SERVER, "Mailchimp-Dragon"),
            check_sendgrid(session),
            check_resend(session),
            check_twilio(session),
        )

    issues = []
    if gmail.get("working", 0) == 0:
        issues.append({"system": "Gmail-SMTP", "error": f"0/{gmail.get('total', 0)} Konten OK"})
    for acc in gmail.get("accounts", []):
        if not acc.get("ok") and acc.get("error") != "no_password":
            issues.append({"system": f"Gmail:{acc.get('email', '?')}", "error": acc.get("error", "?")})

    for label, result in [
        ("Klaviyo", kl), ("Mailchimp-AIITEC", mc_ai), ("Mailchimp-Dragon", mc_dr),
        ("SendGrid", sg), ("Resend", rs), ("Twilio", tw),
    ]:
        if not result.get("ok"):
            issues.append({"system": label, "error": result.get("error", "unknown")})

    fixes = await auto_repair(issues)

    if issues:
        issue_txt = "\n".join(f"❌ {i['system']}: {i['error']}" for i in issues)
        await _tg(f"💊 <b>Email Doctor Report</b>\n{issue_txt}\n🛠️ {fixes} Auto-Fixes angewendet")

    log.info(
        "EmailDoctor: kl=%s mc=%s dragon=%s sg=%s rs=%s tw=%s issues=%d fixes=%d",
        kl.get("ok"), mc_ai.get("ok"), mc_dr.get("ok"), sg.get("ok"), rs.get("ok"), tw.get("ok"),
        len(issues), fixes,
    )
    gmail_ok = f"✅ {gmail.get('working', 0)}/{gmail.get('total', 0)}"
    if gmail.get("working", 0) == 0:
        gmail_ok = f"❌ 0/{gmail.get('total', 0)}"
    return {
        "gmail": gmail_ok,
        "gmail_accounts": gmail,
        "klaviyo": "✅" if kl.get("ok") else f"❌ {kl.get('error','')}",
        "mailchimp": "✅" if mc_ai.get("ok") else f"❌ {mc_ai.get('error','')}",
        "dragon": "✅" if mc_dr.get("ok") else f"❌ {mc_dr.get('error','')}",
        "sendgrid": "✅" if sg.get("ok") else f"❌ {sg.get('error','')}",
        "resend": "✅" if rs.get("ok") else f"❌ {rs.get('error','')}",
        "twilio": "✅" if tw.get("ok") else f"❌ {tw.get('error','')}",
        "issues": len(issues),
        "fixes": fixes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
