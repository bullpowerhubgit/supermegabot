#!/usr/bin/env python3
"""
Zentraler Email-Client — Resend (primär) → Klaviyo → SMTP Fallback.
Ersetzt Mailchimp (beide Konten disabled) und SendGrid (Credits erschöpft).
"""
from __future__ import annotations
import asyncio, logging, os
import aiohttp

log = logging.getLogger("EmailClient")

_RESEND_KEY1 = lambda: os.getenv("RESEND_API_KEY", "re_ibYr2F19_85RKMoBbv6yDcy1YAuuctkmd")
_RESEND_KEY2 = "re_QpJeXP4i_2893JyiExMazp9cxKLKkrSUn"
_KLAVIYO_KEY = lambda: os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")

FROM_DEFAULT = "AIITEC <onboarding@resend.dev>"
REPLY_TO     = os.getenv("REPLY_TO_EMAIL", "aiitecbuuss@gmail.com")


async def send_email(to: str | list[str], subject: str, html: str,
                     from_addr: str = FROM_DEFAULT) -> bool:
    """Send via Resend. Returns True on success."""
    to_list = [to] if isinstance(to, str) else to
    for key in [_RESEND_KEY1(), _RESEND_KEY2]:
        if not key:
            continue
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post("https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"from": from_addr, "to": to_list, "subject": subject,
                          "html": html, "reply_to": REPLY_TO}
                ) as r:
                    if r.status in (200, 201):
                        d = await r.json(content_type=None)
                        log.info("Resend OK id=%s to=%s", d.get("id"), to_list[:1])
                        return True
                    body = await r.text()
                    log.warning("Resend %s: %s", r.status, body[:120])
        except Exception as e:
            log.debug("Resend error: %s", e)
    return False


async def blast_all_known_emails(subject: str, html: str) -> dict:
    """Blast to all known contacts from Klaviyo + hardcoded list."""
    emails = set()

    # Klaviyo contacts
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get("https://a.klaviyo.com/api/profiles/?page[size]=50",
                headers={"Authorization": f"Klaviyo-API-Key {_KLAVIYO_KEY()}",
                         "revision": "2024-02-15"}
            ) as r:
                if r.status == 200:
                    d = await r.json(content_type=None)
                    for p in d.get("data", []):
                        em = p.get("attributes", {}).get("email", "")
                        if em and "@" in em:
                            emails.add(em)
    except Exception as e:
        log.debug("Klaviyo fetch: %s", e)

    # Known leads
    hardcoded = [
        "bullpowersrtkennels@gmail.com",
        "aiitecbuuss@gmail.com",
        "dragonadnp@gmail.com",
    ]
    for em in hardcoded:
        emails.add(em)

    log.info("Blasting to %d emails", len(emails))
    sent, failed = 0, 0
    for email in emails:
        ok = await send_email(email, subject, html)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.3)

    return {"sent": sent, "failed": failed, "total": len(emails)}


async def send_payment_blast() -> dict:
    """Sofort-Blast: Stripe + PayPal Links an alle bekannten Emails."""
    subject = "KI Automation System 2026 — EUR 97 — Sofortzugang"
    html = """
<html><body style="font-family:Arial,sans-serif;background:#0a0a0a;color:#ffffff;padding:30px;max-width:600px;margin:0 auto;">
<h1 style="color:#FFD700;font-size:28px;">🤖 KI Automation System 2026</h1>
<p style="font-size:16px;color:#cccccc;">Vollautomatisches Einnahmesystem — Shopify + Digistore24 + AI</p>
<h2 style="color:#FF6B00;">Einmalig EUR 97 — Sofortzugang</h2>
<p style="color:#aaaaaa;">Was du bekommst:</p>
<ul style="color:#cccccc;">
<li>Vollautomatischer Shopify-Store</li>
<li>Digistore24 Affiliate-System (417 Produkte)</li>
<li>KI-Content-Generator</li>
<li>Telegram Revenue-Bot</li>
</ul>
<a href="https://buy.stripe.com/dRm6oJ67ofqq6Aw8gK4F21y"
   style="background:#FFD700;color:#000;padding:18px 40px;text-decoration:none;font-weight:bold;border-radius:8px;display:inline-block;margin:15px 0;font-size:18px;">
   💳 JETZT MIT KARTE KAUFEN
</a><br>
<a href="https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business=bullpowersrtkennels%40gmail.com&amount=97.00&currency_code=EUR&item_name=KI+Automation+System+2026&no_shipping=1"
   style="background:#0070BA;color:#fff;padding:18px 40px;text-decoration:none;font-weight:bold;border-radius:8px;display:inline-block;margin:5px 0;font-size:18px;">
   💰 MIT PAYPAL ZAHLEN
</a>
<p style="margin-top:20px;"><a href="https://tecbuuss.gumroad.com/l/wcqdjx" style="color:#FFD700;">Mehr Infos zum Produkt →</a></p>
<hr style="border:1px solid #333;margin:20px 0;">
<p style="font-size:11px;color:#555;">AIITEC — AI Automation | Diese E-Mail wurde automatisch generiert</p>
</body></html>"""
    return await blast_all_known_emails(subject, html)
