#!/usr/bin/env python3
"""
SendGrid Blast Engine — Ersetzt defektes Gmail-SMTP.
1.000 Emails/Tag (Free), 100.000/Monat (Paid) via SendGrid API v3.
Blast an Klaviyo-Profilliste + Abandoned Cart + Welcome Sequenz.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("SendGridBlast")

SG_KEY         = os.getenv("SENDGRID_API_KEY", "") or os.getenv("SENDGRID_API_KEY_AIITEC", "")
SG_FROM_EMAIL  = os.getenv("SENDGRID_FROM_EMAIL", "hello@ineedit.com.co")
SG_FROM_NAME   = os.getenv("SENDGRID_FROM_NAME", "ineedit Smart Home")
SG_BASE        = "https://api.sendgrid.com/v3"

KLAVIYO_KEY    = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_BASE   = "https://a.klaviyo.com/api"

SHOP_DOMAIN    = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN     = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOP_VER       = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL       = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")


def _klaviyo_list_id() -> str:
    raw = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
    m = re.search(r"'id':\s*'([A-Za-z0-9]+)'", str(raw))
    return m.group(1) if m else (str(raw).strip().strip("'\"") if len(str(raw)) < 20 else "Xwxq6V")


def _sg_headers() -> Dict:
    return {
        "Authorization": f"Bearer {SG_KEY}",
        "Content-Type": "application/json",
    }


def _kv_headers() -> Dict:
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "revision": "2024-10-15",
        "Content-Type": "application/json",
    }


# ── Email templates ───────────────────────────────────────────────────────────

def _dark_email_wrapper(content_html: str, unsubscribe_url: str = "") -> str:
    unsub = unsubscribe_url or f"{SHOP_URL}/pages/unsubscribe"
    return f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;background:#0d0d0d;color:#e0e0e0;padding:24px;border-radius:10px">
  {content_html}
  <hr style="border-color:#2a2a2a;margin:24px 0">
  <p style="font-size:11px;color:#555;text-align:center">
    Du erhältst diese E-Mail, weil du auf <a href="{SHOP_URL}" style="color:#555">ineedit.com.co</a> eingekauft oder dich angemeldet hast.
    <br><a href="{unsub}" style="color:#555">Abmelden</a>
  </p>
</div>"""


def _cta_button(text: str, url: str) -> str:
    return (f'<a href="{url}" style="display:inline-block;background:#ff6b35;color:#fff;'
            f'padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;'
            f'font-size:16px;margin:16px 0">{text}</a>')


def build_revenue_email_html(products: List[Dict]) -> Tuple[str, str]:
    """Build dark-theme revenue email. Returns (subject, html)."""
    subjects = [
        "🔥 Deine Smart-Home-Highlights dieser Woche",
        "⚡ Top-Produkte — jetzt bei ineedit.com.co",
        "💡 Smart Home Deals — nur für dich",
        f"🎯 {random.randint(5, 25)}% sparen auf smarte Technik",
        "🏠 Diese Woche beliebt: Smart Home & Solar",
    ]
    subject = random.choice(subjects)

    product_blocks = ""
    for p in products[:4]:
        title = p.get("title", "")[:60]
        handle = p.get("handle", "")
        link = f"{SHOP_URL}/products/{handle}"
        price = ""
        variants = p.get("variants", [{}])
        if variants:
            price = variants[0].get("price", "")
        images = p.get("images", [])
        img_src = images[0].get("src", "") if images else ""
        img_tag = f'<img src="{img_src}" alt="{title}" style="max-width:120px;border-radius:6px;margin-right:12px">' if img_src else ""

        product_blocks += f"""
<div style="display:flex;align-items:center;background:#1a1a1a;border-radius:8px;padding:12px;margin:8px 0">
  {img_tag}
  <div>
    <strong style="color:#fff;font-size:14px">{title}</strong><br>
    <span style="color:#ff6b35;font-size:16px;font-weight:bold">€{price}</span><br>
    <a href="{link}" style="color:#ff6b35;font-size:12px;text-decoration:none">Jetzt ansehen →</a>
  </div>
</div>"""

    if not product_blocks:
        product_blocks = f'<p><a href="{SHOP_URL}/collections/all" style="color:#ff6b35">Alle Produkte ansehen →</a></p>'

    content = f"""
<h2 style="color:#ff6b35;margin:0 0 12px">🔥 Exklusive Angebote für dich</h2>
<p style="color:#ccc;font-size:14px">Entdecke diese Woche die beliebtesten Smart-Home-Produkte:</p>
{product_blocks}
<div style="margin:20px 0;text-align:center">
  <div style="background:#1a1a1a;border-radius:8px;padding:12px;margin-bottom:12px">
    <span style="color:#fff">✅ <strong>Kostenloser Versand</strong> ab €50</span>&nbsp;&nbsp;
    <span style="color:#fff">🔄 <strong>30 Tage</strong> Rückgabe</span>&nbsp;&nbsp;
    <span style="color:#fff">🔒 <strong>Sicher</strong> bezahlen</span>
  </div>
  {_cta_button("Jetzt shoppen →", SHOP_URL + "/collections/all")}
</div>"""
    return subject, _dark_email_wrapper(content)


def build_abandoned_cart_html(first_name: str, cart_url: str, product_name: str) -> Tuple[str, str]:
    subject = f"⚠️ {first_name}, du hast etwas vergessen!"
    content = f"""
<h2 style="color:#ff6b35;margin:0 0 12px">Dein Warenkorb wartet!</h2>
<p style="color:#ccc">Hallo {first_name or "du"},</p>
<p style="color:#ccc">du hast <strong style="color:#fff">{product_name}</strong> in deinem Warenkorb gelassen. Sichere dir deinen Artikel noch heute!</p>
<div style="background:#1a1a1a;border-radius:8px;padding:16px;margin:16px 0">
  <p style="color:#fff;margin:0">⏰ <strong>Limitiertes Angebot</strong> — Artikel können ausverkauft sein!</p>
</div>
{_cta_button("Jetzt kaufen →", cart_url or SHOP_URL)}
<p style="color:#777;font-size:13px">Fragen? Antworte einfach auf diese E-Mail.</p>"""
    return subject, _dark_email_wrapper(content)


def build_welcome_html(first_name: str) -> Tuple[str, str]:
    subject = f"👋 Willkommen bei ineedit, {first_name or 'du'}!"
    content = f"""
<h2 style="color:#ff6b35;margin:0 0 12px">Schön, dass du da bist! 🎉</h2>
<p style="color:#ccc">Hallo {first_name or ""},</p>
<p style="color:#ccc">willkommen bei <strong style="color:#fff">ineedit.com.co</strong> — deinem Shop für smarte Technik!</p>
<div style="background:#1a1a1a;border-radius:8px;padding:16px;margin:16px 0">
  <p style="color:#fff;margin:0 0 8px">🎁 <strong>Als Willkommensgeschenk:</strong></p>
  <p style="color:#ccc;margin:0">Kostenloser Versand auf deine erste Bestellung — kein Mindestbestellwert!</p>
</div>
{_cta_button("Shop jetzt entdecken →", SHOP_URL + "/collections/all")}
<p style="color:#ccc">Viel Freude beim Einkaufen!<br><strong style="color:#fff">Das ineedit Team</strong></p>"""
    return subject, _dark_email_wrapper(content)


# ── Core send ─────────────────────────────────────────────────────────────────

async def _send_resend(to_email: str, to_name: str, subject: str, html: str,
                       from_email: Optional[str] = None) -> bool:
    """Resend.com — primärer Sender (kein IP-Problem, sofort aktiv)."""
    key = os.getenv("RESEND_API_KEY", "")
    if not key:
        return False
    sender_email = from_email or os.getenv("BREVO_FROM_EMAIL", SG_FROM_EMAIL)
    sender_name  = os.getenv("BREVO_FROM_NAME", SG_FROM_NAME)
    # Resend: onboarding@resend.dev funktioniert ohne Domain-Verifizierung
    if "ineedit.com.co" not in sender_email and "resend.dev" not in sender_email:
        sender_email = "onboarding@resend.dev"
    payload = {
        "from":    f"{sender_name} <{sender_email}>",
        "to":      [to_email],
        "subject": subject,
        "html":    html,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            ) as r:
                if r.status in (200, 201):
                    log.info("Resend ✅ → %s", to_email)
                    return True
                body = await r.text()
                log.warning("Resend %s %s: %s", r.status, to_email, body[:200])
                return False
    except Exception as e:
        log.warning("Resend error %s: %s", to_email, e)
        return False


async def _send_brevo_rest(to_email: str, to_name: str, subject: str, html: str,
                           from_email: Optional[str] = None) -> bool:
    """Brevo REST API — primärer Sender."""
    key = os.getenv("BREVO_API_KEY", "")
    if not key:
        return False
    sender_email = from_email or os.getenv("BREVO_FROM_EMAIL", SG_FROM_EMAIL)
    sender_name  = os.getenv("BREVO_FROM_NAME", SG_FROM_NAME)
    payload = {
        "sender":      {"name": sender_name, "email": sender_email},
        "to":          [{"email": to_email, "name": to_name or ""}],
        "subject":     subject,
        "htmlContent": html,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": key, "Content-Type": "application/json"},
                json=payload,
            ) as r:
                if r.status in (200, 201):
                    log.info("Brevo REST ✅ → %s", to_email)
                    return True
                body = await r.text()
                log.warning("Brevo REST %s %s: %s", r.status, to_email, body[:200])
                return False
    except Exception as e:
        log.warning("Brevo REST error %s: %s", to_email, e)
        return False


async def _send_brevo_smtp(to_email: str, to_name: str, subject: str, html: str,
                           from_email: Optional[str] = None) -> bool:
    """Brevo SMTP — Fallback wenn REST nicht verfügbar."""
    smtp_user = os.getenv("BREVO_SMTP_USER", "")
    smtp_pass = os.getenv("BREVO_SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return False
    sender = from_email or os.getenv("BREVO_FROM_EMAIL", SG_FROM_EMAIL)
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{SG_FROM_NAME} <{sender}>"
        msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=15) as s:
            s.ehlo(); s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(sender, [to_email], msg.as_string())
        log.info("Brevo SMTP ✅ → %s", to_email)
        return True
    except Exception as e:
        log.warning("Brevo SMTP %s: %s", to_email, e)
        return False


async def send_single(to_email: str, to_name: str, subject: str, html: str,
                      from_email: Optional[str] = None) -> Dict:
    """Send via Resend → Brevo REST → Brevo SMTP → SendGrid (fallback)."""
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "invalid to_email"}
    try:
        from modules.gmail_accounts import _is_valid_recipient
        if not _is_valid_recipient(to_email):
            log.warning("BLOCKED (noreply/dead): %s", to_email)
            return {"ok": False, "error": "blocked_noreply_dead"}
    except ImportError:
        pass

    # Resend (primär — kein IP-Problem, sofort aktiv)
    if await _send_resend(to_email, to_name, subject, html, from_email):
        return {"ok": True, "to": to_email, "via": "resend"}

    # Brevo REST Fallback (wenn aktiviert)
    if await _send_brevo_rest(to_email, to_name, subject, html, from_email):
        return {"ok": True, "to": to_email, "via": "brevo_rest"}

    # Brevo SMTP Fallback
    if await _send_brevo_smtp(to_email, to_name, subject, html, from_email):
        return {"ok": True, "to": to_email, "via": "brevo_smtp"}

    # SendGrid Fallback
    if not SG_KEY:
        return {"ok": False, "error": "no sender configured"}
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name or ""}]}],
        "from": {"email": from_email or SG_FROM_EMAIL, "name": SG_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
        "tracking_settings": {
            "click_tracking": {"enable": True},
            "open_tracking": {"enable": True},
        },
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(f"{SG_BASE}/mail/send", headers=_sg_headers(), json=payload) as r:
                if r.status in (200, 202):
                    return {"ok": True, "to": to_email, "via": "sendgrid"}
                body = await r.text()
                log.warning("SendGrid %s: %s %s", to_email, r.status, body[:200])
                return {"ok": False, "status": r.status, "error": body[:200]}
    except Exception as e:
        log.warning("SendGrid error %s: %s", to_email, e)
        return {"ok": False, "error": str(e)}


# ── Klaviyo profile collection ────────────────────────────────────────────────

async def _get_klaviyo_profiles() -> List[Dict]:
    if not KLAVIYO_KEY:
        return []
    profiles = []
    url = f"{KLAVIYO_BASE}/profiles/"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            while url:
                async with s.get(url, headers=_kv_headers(),
                                  params={"fields[profile]": "email,first_name"}) as r:
                    if r.status != 200:
                        break
                    data = await r.json()
                    profiles.extend(data.get("data", []))
                    url = data.get("links", {}).get("next")
    except Exception as e:
        log.warning("Klaviyo profiles: %s", e)
    return profiles


# ── Bulk blast ────────────────────────────────────────────────────────────────

async def blast_klaviyo_list(subject: str, html: str) -> Dict:
    """Send to every Klaviyo profile via SendGrid. Rate-limited: 10 concurrent."""
    profiles = await _get_klaviyo_profiles()
    if not profiles:
        return {"ok": False, "error": "no Klaviyo profiles", "sent": 0}

    sent = 0
    failed = 0
    sem = asyncio.Semaphore(10)

    async def _send_one(profile: Dict) -> bool:
        attrs = profile.get("attributes", {})
        email = attrs.get("email", "").strip()
        name = attrs.get("first_name", "") or ""
        _demo_domains = {"klaviyo-demo.com", "example.com", "mailinator.com", "test.com"}
        if not email or "@" not in email or email.split("@")[-1] in _demo_domains:
            return False
        async with sem:
            r = await send_single(email, name, subject, html)
            await asyncio.sleep(0.05)
            return r.get("ok", False)

    results = await asyncio.gather(*[_send_one(p) for p in profiles], return_exceptions=True)
    for r in results:
        if r is True:
            sent += 1
        else:
            failed += 1

    log.info("SendGrid blast: %d sent, %d failed of %d recipients", sent, failed, len(profiles))
    return {"ok": sent > 0, "sent": sent, "failed": failed, "total": len(profiles)}


# ── Specific email types ──────────────────────────────────────────────────────

async def send_abandoned_cart_email(email: str, first_name: str,
                                    cart_url: str, product_name: str) -> Dict:
    subject, html = build_abandoned_cart_html(first_name, cart_url, product_name)
    return await send_single(email, first_name, subject, html)


async def send_welcome_email(email: str, first_name: str) -> Dict:
    subject, html = build_welcome_html(first_name)
    return await send_single(email, first_name, subject, html)


# ── Shopify top products ──────────────────────────────────────────────────────

async def _get_shopify_top_products(limit: int = 4) -> List[Dict]:
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(
                f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOP_TOKEN},
                params={"limit": limit, "status": "active", "sort_by": "best-selling",
                        "fields": "id,title,handle,images,variants"},
            ) as r:
                if r.status == 200:
                    return (await r.json()).get("products", [])
    except Exception as e:
        log.warning("Shopify top products: %s", e)
    return []


# ── Daily revenue email ───────────────────────────────────────────────────────

async def _blast_mailchimp_campaign(subject: str, html: str) -> Dict:
    """Sendet Campaign an AIITEC Mailchimp-Liste (bc5c7887cf)."""
    import base64 as _b64
    mc_key = os.getenv("MAILCHIMP_API_KEY", "")
    if not mc_key:
        return {"ok": False, "error": "no MAILCHIMP_API_KEY"}
    dc      = mc_key.split("-")[-1] if "-" in mc_key else "us5"
    list_id = os.getenv("MAILCHIMP_LIST_ID", "bc5c7887cf")
    from_email = os.getenv("MAILCHIMP_FROM_EMAIL", "rudolfsarkany1984@gmail.com")
    from_name  = os.getenv("BREVO_FROM_NAME", "ineedit Smart Home")
    auth = _b64.b64encode(f"anystring:{mc_key}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    base = f"https://{dc}.api.mailchimp.com/3.0"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            # Kampagne erstellen
            async with s.post(f"{base}/campaigns", headers=headers, json={
                "type": "regular",
                "recipients": {"list_id": list_id},
                "settings": {
                    "subject_line": subject,
                    "from_name": from_name,
                    "reply_to": from_email,
                },
            }) as r:
                camp = await r.json()
                camp_id = camp.get("id", "")
                if not camp_id:
                    log.warning("Mailchimp campaign create failed: %s", camp)
                    return {"ok": False, "error": "campaign create failed"}

            # Content setzen
            async with s.put(f"{base}/campaigns/{camp_id}/content",
                             headers=headers, json={"html": html}) as r:
                if r.status not in (200, 204):
                    err = await r.text()
                    log.warning("Mailchimp content set failed: %s", err[:200])
                    return {"ok": False, "error": "content set failed"}

            # Senden
            async with s.post(f"{base}/campaigns/{camp_id}/actions/send",
                              headers=headers) as r:
                if r.status in (200, 204):
                    log.info("Mailchimp Campaign ✅ gesendet: %s", camp_id)
                    return {"ok": True, "campaign_id": camp_id, "via": "mailchimp"}
                err = await r.text()
                log.warning("Mailchimp send failed %s: %s", r.status, err[:200])
                return {"ok": False, "error": err[:200]}
    except Exception as e:
        log.warning("Mailchimp campaign: %s", e)
        return {"ok": False, "error": str(e)}


async def run_daily_revenue_email() -> Dict:
    """
    Main daily cycle:
    1. Fetch top 4 Shopify products
    2. Build dark-theme revenue email
    3. Blast via Mailchimp → Klaviyo → SendGrid
    """
    products = await _get_shopify_top_products(limit=4)
    subject, html = build_revenue_email_html(products)

    # Mailchimp Campaign (primär — verifizierter Sender, keine IP-Probleme)
    mc_result = await _blast_mailchimp_campaign(subject, html)
    if mc_result.get("ok"):
        log.info("Daily email via Mailchimp ✅")
        return {"ok": True, "subject": subject, "products_used": len(products), "blast": mc_result}

    # Fallback: Klaviyo-Einzelversand
    result = await blast_klaviyo_list(subject, html)

    log.info("Daily revenue email: %s", result)
    return {
        "ok": result.get("ok"),
        "subject": subject,
        "products_used": len(products),
        "blast": result,
    }


# ── Status ────────────────────────────────────────────────────────────────────

async def get_sendgrid_status() -> Dict:
    """Check SendGrid account credits and today's send stats."""
    if not SG_KEY:
        return {"ok": False, "configured": False, "error": "no SENDGRID_API_KEY"}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{SG_BASE}/stats",
                headers=_sg_headers(),
                params={"start_date": today, "end_date": today, "aggregated_by": "day"},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    stats = data[0].get("stats", [{}])[0].get("metrics", {}) if data else {}
                    profiles = await _get_klaviyo_profiles()
                    return {
                        "ok": True,
                        "configured": True,
                        "today_requests": stats.get("requests", 0),
                        "today_delivered": stats.get("delivered", 0),
                        "today_opens": stats.get("opens", 0),
                        "today_clicks": stats.get("clicks", 0),
                        "klaviyo_recipients": len(profiles),
                        "from_email": SG_FROM_EMAIL,
                    }
    except Exception as e:
        log.warning("SendGrid status: %s", e)
    return {"ok": False, "configured": bool(SG_KEY), "error": "stats check failed"}
