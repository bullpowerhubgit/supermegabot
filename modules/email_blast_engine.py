#!/usr/bin/env python3
"""
Email Blast Engine — Vollautomatische Revenue-Email-Maschine.
Gleichzeitig: Mailchimp + Klaviyo + SMTP. KI schreibt konvertierende Texte.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiohttp

log = logging.getLogger("EmailBlastEngine")

SHOP_URL    = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
FROM_EMAIL  = os.getenv("FROM_EMAIL", "hello@ineedit.com.co")
SHOP        = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOK = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER = os.getenv("SHOPIFY_API_VERSION", "2026-04")

KLAVIYO_KEY = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")

MAILCHIMP_KEY = os.getenv("MAILCHIMP_API_KEY", "")
# Auto-detect DC from API key suffix (e.g. "xxxxx-us21" → "us21")
def _mc_dc() -> str:
    key = MAILCHIMP_KEY
    if key and "-" in key:
        return key.rsplit("-", 1)[-1]
    return os.getenv("MAILCHIMP_DC", "us7")
MAILCHIMP_DC  = _mc_dc()
MAILCHIMP_LIST = os.getenv("MAILCHIMP_LIST_ID", "")

def _smtp_accounts_list() -> list:
    from modules.gmail_accounts import configured_accounts
    return [
        {"user": a.email, "pw": a.password, "host": a.smtp_host}
        for a in configured_accounts()
    ]

EMAIL_SUBJECTS = [
    "🔥 Exklusiv für dich: {offer}",
    "⚡ Nur heute: {offer}",
    "🎯 {offer} — Jetzt sichern!",
    "💰 Spare €{amount} auf {offer}",
    "📦 Neu eingetroffen: {offer}",
]


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get_shopify_products(limit: int = 5) -> list:
    if not SHOP or not SHOPIFY_TOK:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOP}/admin/api/{SHOPIFY_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOK},
                params={"limit": limit, "status": "active"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                return (await r.json()).get("products", [])
    except Exception:
        return []


async def generate_revenue_email(products: list = None, offers: list = None) -> dict:
    """KI schreibt konvertierenden HTML-Email-Text mit Produkten/Angeboten."""
    product_list = ""
    if products:
        for p in products[:4]:
            title = p.get("title", "")
            price = (p.get("variants") or [{}])[0].get("price", "")
            handle = p.get("handle", "")
            link = f"{SHOP_URL}/products/{handle}" if handle else SHOP_URL
            product_list += f"• {title} — €{price}: {link}\n"
    else:
        product_list = f"• Entdecke alle Angebote: {SHOP_URL}"

    prompt = f"""Schreibe einen professionellen deutschen Marketing-Email-Text (HTML).
Produkte:
{product_list}
Shop: {SHOP_URL}

HTML-Format:
- Betreff-worthy Headline (h2, Farbe: #e63946)
- Kurze Einleitung (2 Sätze, persönlich)
- Produkte als HTML-Liste
- 1 großer CTA-Button (Hintergrund: #e63946, Text: "Jetzt kaufen →", Link: {SHOP_URL})
- Professionelle Grußformel

Kein DOCTYPE. Nur body-content. Max 300 Wörter."""

    html = await _ai(prompt, 500)
    if not html:
        _nl = "\n"
        _li_list = product_list.replace("•", "<li>").replace(_nl, "</li>")
        html = (
            f'<h2 style="color:#e63946">🔥 Exklusive Angebote für dich!</h2>'
            f"<p>Entdecke unsere neuesten Highlights:</p>"
            f"<ul>{_li_list}</ul>"
            f'<a href="{SHOP_URL}" style="background:#e63946;color:#fff;padding:12px 24px;'
            f'text-decoration:none;border-radius:4px;display:inline-block;margin:16px 0">Jetzt kaufen →</a>'
            f"<p>Viele Grüße,<br>Dein Shop-Team</p>"
        )

    subject_template = random.choice(EMAIL_SUBJECTS)
    subject = subject_template.format(
        offer=(products[0].get("title", "Neuheiten")[:30] if products else "Aktuelle Angebote"),
        amount=random.randint(5, 30)
    )
    return {"ok": True, "html": html, "subject": subject}


async def send_via_klaviyo(subject: str, html: str) -> dict:
    """Sendet Email-Kampagne via Klaviyo."""
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "no KLAVIYO_API_KEY"}
    try:
        from modules.klaviyo_automation import send_campaign
        result = await send_campaign(subject=subject, html_body=html)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def send_via_mailchimp(subject: str, html: str) -> dict:
    """Sendet Email-Kampagne via Mailchimp."""
    if not MAILCHIMP_KEY or not MAILCHIMP_LIST:
        return {"ok": False, "error": "no MAILCHIMP credentials"}
    try:
        async with aiohttp.ClientSession() as s:
            # Create campaign
            async with s.post(
                f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/campaigns",
                auth=aiohttp.BasicAuth("user", MAILCHIMP_KEY),
                json={
                    "type": "regular",
                    "recipients": {"list_id": MAILCHIMP_LIST},
                    "settings": {
                        "subject_line": subject,
                        "from_name": "BullPowerHub",
                        "reply_to": FROM_EMAIL,
                    }
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json()
            cid = data.get("id")
            if not cid:
                return {"ok": False, "error": str(data)[:200]}

            # Set content
            async with s.put(
                f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/campaigns/{cid}/content",
                auth=aiohttp.BasicAuth("user", MAILCHIMP_KEY),
                json={"html": html},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r2:
                pass

            # Send
            async with s.post(
                f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/campaigns/{cid}/actions/send",
                auth=aiohttp.BasicAuth("user", MAILCHIMP_KEY),
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r3:
                return {"ok": r3.status < 300, "campaign_id": cid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def send_via_smtp(subject: str, html: str, to_email: str = "") -> dict:
    """Sendet Email via Gmail SMTP (App-Passwort)."""
    account = next((a for a in _smtp_accounts_list() if a["user"] and a["pw"]), None)
    if not account:
        return {"ok": False, "error": "no SMTP credentials"}
    target = to_email or account["user"]
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = account["user"]
        msg["To"] = target
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(account["host"], 587, timeout=20) as smtp:
            smtp.ehlo(); smtp.starttls(); smtp.login(account["user"], account["pw"])
            smtp.sendmail(account["user"], target, msg.as_string())
        return {"ok": True, "from": account["user"], "to": target}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def blast_all_lists(subject: str, html: str) -> dict:
    """Gleichzeitig Klaviyo + Mailchimp + SMTP."""
    results = await asyncio.gather(
        send_via_klaviyo(subject, html),
        send_via_mailchimp(subject, html),
        return_exceptions=True,
    )
    klaviyo_ok = results[0].get("ok") if isinstance(results[0], dict) else False
    mailchimp_ok = results[1].get("ok") if isinstance(results[1], dict) else False
    return {
        "ok": klaviyo_ok or mailchimp_ok,
        "klaviyo": results[0] if isinstance(results[0], dict) else {"error": str(results[0])},
        "mailchimp": results[1] if isinstance(results[1], dict) else {"error": str(results[1])},
    }


async def run_daily_blast() -> dict:
    """Täglich: Trend-Produkte → KI-Email → Guardian-Check → blast_all_lists."""
    products = await _get_shopify_products(limit=4)
    email_data = await generate_revenue_email(products=products)
    if not email_data.get("ok"):
        return {"ok": False, "error": "email generation failed"}

    subject = email_data["subject"]
    html    = email_data["html"]

    # Qualitäts-Gate vor dem Blast
    try:
        from modules.email_guardian import validate_email
        ok, errors = validate_email(
            to_email="test@example.com",  # nur Content-Check, nicht Empfänger
            subject=subject,
            html_body=html,
            allow_private=True,  # Empfänger-Domain-Check überspringen (Massen-Mail)
        )
        if not ok:
            log.error("EmailBlastEngine BLOCKIERT (Guardian): %s", errors)
            return {"ok": False, "blocked": True, "errors": errors}
    except Exception as eg:
        log.error("EmailBlastEngine Guardian-Fehler — BLOCK: %s", eg)
        return {"ok": False, "error": f"guardian_error: {eg}"}

    blast = await blast_all_lists(subject, html)
    log.info("Daily email blast: klaviyo=%s mailchimp=%s",
             blast.get("klaviyo", {}).get("ok"), blast.get("mailchimp", {}).get("ok"))
    return {"ok": True, "subject": subject, "blast": blast}


async def get_email_stats() -> dict:
    """Status des Email-Blast-Moduls."""
    return {
        "ok": True,
        "klaviyo_configured": bool(KLAVIYO_KEY),
        "mailchimp_configured": bool(MAILCHIMP_KEY and MAILCHIMP_LIST),
        "smtp_accounts": len(_smtp_accounts_list()),
        "from_email": FROM_EMAIL,
    }


async def run_email_cycle() -> dict:
    """Scheduler-Einstiegspunkt."""
    return await run_daily_blast()


async def check_inbox_replies() -> dict:
    """IMAP-Postfach pollen — Stub (kein IMAP konfiguriert)."""
    return {"ok": True, "checked": 0, "replies": 0, "note": "IMAP not configured"}


async def get_daily_summary() -> dict:
    """Tägliche Email-Zusammenfassung."""
    stats = await get_email_stats()
    return {"ok": True, "summary": stats}
