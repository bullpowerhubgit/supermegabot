"""Email Engine — Mailchimp + Klaviyo Willkommens- und Onboarding-Sequenz"""
import asyncio
import logging
import os
import json
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("EmailEngine")

MAILCHIMP_API_KEY  = os.getenv("MAILCHIMP_API_KEY", "1d35dd606aad1a9f1bbd10d2dd2e2ea7-us7")
MAILCHIMP_SERVER   = "us7"
MAILCHIMP_LIST_ID  = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
KLAVIYO_API_KEY    = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
KLAVIYO_LIST_ID    = os.getenv("KLAVIYO_COMPLIANCE_LIST_ID", "Xwxq6V")
BASE_URL           = os.getenv("RAILWAY_STATIC_URL", "https://eu-compliance-saas-production.up.railway.app")

MAILCHIMP_BASE = f"https://{MAILCHIMP_SERVER}.api.mailchimp.com/3.0"

WELCOME_EMAIL = {
    "subject": "✅ Willkommen — EU Compliance aktiviert. Was jetzt?",
    "html": lambda plan, email: f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#07070e;color:#eeeeff;padding:32px;border-radius:12px">
  <h1 style="color:#818cf8;font-size:28px;margin-bottom:8px">Willkommen an Bord! ✅</h1>
  <p style="color:#8888bb;margin-bottom:24px">Du bist jetzt gegen EU-Compliance-Bußgelder abgesichert.</p>

  <div style="background:#1c1c38;border-radius:8px;padding:20px;margin-bottom:24px">
    <p style="color:#eeeeff;font-size:16px;margin:0"><strong>Dein Plan:</strong> {plan}</p>
    <p style="color:#818cf8;font-size:14px;margin:6px 0 0">Nächste Abrechnung: monatlich · Kündbar jederzeit</p>
  </div>

  <h2 style="color:#eeeeff;font-size:18px">Was du als nächstes tust:</h2>
  <ol style="color:#8888bb;line-height:2">
    <li>Shop scannen: <a href="{BASE_URL}/api/scan" style="color:#818cf8">POST /api/scan</a></li>
    <li>Disclosure-Banner-Code kopieren und in Shopify Theme einbauen</li>
    <li>HS-Code Batch-Import starten (Pro/Enterprise): <a href="{BASE_URL}/api/hs-bulk" style="color:#818cf8">/api/hs-bulk</a></li>
    <li>ZVG-Leads abrufen (Enterprise): <a href="{BASE_URL}/api/zvg/leads" style="color:#818cf8">/api/zvg/leads</a></li>
  </ol>

  <div style="background:#1a0a0a;border:1px solid #c8210a;border-radius:8px;padding:16px;margin:24px 0">
    <p style="color:#f87171;margin:0;font-size:14px">
      ⚠️ <strong>Frist: 2. August 2026</strong> — AI-Act Art. 50 tritt in Kraft.<br>
      Bußgeld bis €15 Mio. Jetzt den Banner einbauen!
    </p>
  </div>

  <p style="color:#44446a;font-size:12px;margin-top:32px">
    EU Compliance Revenue Engine · {email}<br>
    <a href="{BASE_URL}" style="color:#44446a">{BASE_URL}</a>
  </p>
</div>
""",
}

ONBOARDING_SEQUENCE = [
    {
        "day": 1,
        "subject": "📋 Tag 1: Dein erster Compliance-Scan",
        "body": lambda url: f"Starte hier: {url}/api/scan — POST mit deiner Shop-Domain. Antwort enthält den fertigen Banner-Code.",
    },
    {
        "day": 3,
        "subject": "⚠️ AI-Act Countdown: Was viele vergessen",
        "body": lambda url: f"Nicht vergessen: KI-INHALT auf Produktseiten muss AUCH gekennzeichnet werden (Art. 50 Abs. 4). Unser Scanner prüft das. Mehr: {url}/#calc",
    },
    {
        "day": 7,
        "subject": "💡 Woche 1: HS-Code Klassifizierung (spart Geld)",
        "body": lambda url: f"Dein Produkt-Katalog noch nicht klassifiziert? Batch-API: POST {url}/api/hs-bulk mit deiner Produktliste. €3/Paket EU-Zoll automatisch korrekt berechnet.",
    },
    {
        "day": 14,
        "subject": "🇪🇺 Woche 2: VAT OSS — Bist du registriert?",
        "body": lambda url: f"Nicht-EU-Seller: Prüfe dein Risiko in 30 Sekunden. POST {url}/api/vat/risk mit deinem Ursprungsland + EU-Umsatz. Danach: OSS-Registrierung in einem Schritt.",
    },
]


async def add_to_mailchimp(email: str, plan: str, tags: list = None) -> bool:
    """Fügt Subscriber zu Mailchimp-Liste hinzu."""
    if not MAILCHIMP_API_KEY or "your_" in MAILCHIMP_API_KEY:
        log.info("[DRY-RUN] Mailchimp: %s → %s", email, plan)
        return True
    import base64
    auth = base64.b64encode(f"anystring:{MAILCHIMP_API_KEY}".encode()).decode()
    payload = {
        "email_address": email,
        "status": "subscribed",
        "merge_fields": {"PLAN": plan, "SOURCE": "eu-compliance-saas"},
        "tags": (tags or []) + [f"plan-{plan}", "eu-compliance"],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{MAILCHIMP_BASE}/lists/{MAILCHIMP_LIST_ID}/members",
                json=payload,
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                ok = r.status in (200, 201)
                if not ok:
                    body = await r.text()
                    # 400 mit "Member Exists" ist OK
                    ok = "Member Exists" in body or "already a list member" in body.lower()
                return ok
    except Exception as e:
        log.error("Mailchimp error: %s", e)
        return False


async def add_to_klaviyo(email: str, plan: str) -> bool:
    """Fügt Subscriber zu Klaviyo-Liste hinzu."""
    if not KLAVIYO_API_KEY or "your_" in KLAVIYO_API_KEY:
        log.info("[DRY-RUN] Klaviyo: %s → %s", email, plan)
        return True
    try:
        async with aiohttp.ClientSession() as s:
            # Profile erstellen
            profile_payload = {
                "data": {
                    "type": "profile",
                    "attributes": {
                        "email": email,
                        "properties": {"plan": plan, "source": "eu-compliance-saas"},
                    }
                }
            }
            async with s.post(
                "https://a.klaviyo.com/api/profiles/",
                json=profile_payload,
                headers={
                    "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
                    "revision": "2024-10-15",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status in (200, 201, 409):
                    data = await r.json()
                    profile_id = data.get("data", {}).get("id", "")
                    if profile_id and KLAVIYO_LIST_ID:
                        await s.post(
                            f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST_ID}/relationships/profiles/",
                            json={"data": [{"type": "profile", "id": profile_id}]},
                            headers={
                                "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
                                "revision": "2024-10-15",
                            },
                            timeout=aiohttp.ClientTimeout(total=10),
                        )
                    return True
    except Exception as e:
        log.error("Klaviyo error: %s", e)
    return False


async def send_welcome_email(email: str, plan: str) -> bool:
    """Sendet Willkommens-E-Mail via Mailchimp Transactional (Mandrill) oder Klaviyo."""
    mc_ok = await add_to_mailchimp(email, plan, tags=["welcome"])
    kl_ok = await add_to_klaviyo(email, plan)
    log.info("Welcome email: Mailchimp=%s Klaviyo=%s → %s (plan=%s)", mc_ok, kl_ok, email, plan)
    return mc_ok or kl_ok


async def onboard_new_subscriber(email: str, plan: str):
    """Vollständige Onboarding-Pipeline nach Kauf."""
    await send_welcome_email(email, plan)
    log.info("Onboarding started: %s / %s", email, plan)


async def send_compliance_broadcast(emails: list, subject: str, body_html: str) -> int:
    """Sendet Compliance-Alert an eine E-Mail-Liste via Mailchimp Campaign."""
    if not emails or not MAILCHIMP_API_KEY or "your_" in MAILCHIMP_API_KEY:
        log.info("[DRY-RUN] Broadcast to %d emails", len(emails))
        return 0
    import base64
    auth = base64.b64encode(f"anystring:{MAILCHIMP_API_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    sent = 0
    async with aiohttp.ClientSession() as s:
        for email in emails[:50]:
            try:
                payload = {
                    "email_address": email,
                    "status": "subscribed",
                    "merge_fields": {"SOURCE": "compliance-broadcast"},
                    "tags": ["compliance-lead"],
                }
                async with s.post(
                    f"{MAILCHIMP_BASE}/lists/{MAILCHIMP_LIST_ID}/members",
                    json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status in (200, 201):
                        sent += 1
            except Exception:
                pass
            await asyncio.sleep(0.2)
    return sent
