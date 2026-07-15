"""AIITEC Email Engine — Mailchimp + Klaviyo Onboarding + Broadcast"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("EmailEngine")

MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY", "1d35dd606aad1a9f1bbd10d2dd2e2ea7-us7")
MAILCHIMP_SERVER  = "us7"
MAILCHIMP_LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
KLAVIYO_API_KEY   = os.getenv("KLAVIYO_API_KEY", "pk_VaCYq3_242945f7521ac82039ed5dbf7ff8e6cf1c")
KLAVIYO_LIST_ID   = os.getenv("KLAVIYO_AIITEC_LIST_ID", os.getenv("KLAVIYO_LIST_ID", "Xwxq6V"))
BASE_URL          = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")

MAILCHIMP_BASE = f"https://{MAILCHIMP_SERVER}.api.mailchimp.com/3.0"

WELCOME_EMAILS = {
    "starter": {
        "subject": "✅ Lead Agent aktiviert — dein erster Report kommt in 24h",
        "html": lambda email: f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#030308;color:#e2e8f0;padding:32px;border-radius:12px">
  <h1 style="color:#6366f1;font-size:28px;margin-bottom:8px">Lead Agent ist aktiv! 🚀</h1>
  <p style="color:#94a3b8;margin-bottom:24px">Dein KI-Vertriebsmitarbeiter startet jetzt — 24/7, ohne Pause.</p>
  <div style="background:#0d0d1a;border-radius:8px;padding:20px;margin-bottom:24px;border:1px solid #1e1e3a">
    <p style="color:#e2e8f0;font-size:16px;margin:0"><strong>Was jetzt passiert:</strong></p>
    <ol style="color:#94a3b8;line-height:2.2;margin:12px 0 0">
      <li>KI scannt täglich 50+ B2B-Firmen in deiner Zielgruppe</li>
      <li>Qualifizierung: Unternehmensgröße, Entscheidungsträger, Kontaktdaten</li>
      <li>Personalisierte Outreach-Email wird generiert + gesendet</li>
      <li>Antworten landen direkt in deinem Postfach</li>
    </ol>
  </div>
  <div style="background:#0a0a0f;border:1px solid #6366f1;border-radius:8px;padding:16px;margin:24px 0">
    <p style="color:#6366f1;margin:0;font-size:14px;font-weight:bold">📊 Erster Lead-Report: morgen 08:00 Uhr</p>
    <p style="color:#94a3b8;margin:6px 0 0;font-size:13px">Live-Dashboard: <a href="{BASE_URL}/dashboard" style="color:#6366f1">{BASE_URL}/dashboard</a></p>
  </div>
  <p style="color:#44446a;font-size:12px;margin-top:32px">AIITEC · {email} · <a href="{BASE_URL}" style="color:#44446a">{BASE_URL}</a></p>
</div>""",
    },
    "pro": {
        "subject": "✅ Compliance Wächter aktiv — Scan startet in 10 Minuten",
        "html": lambda email: f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#030308;color:#e2e8f0;padding:32px;border-radius:12px">
  <h1 style="color:#f59e0b;font-size:28px;margin-bottom:8px">Compliance Wächter ist online! 🛡️</h1>
  <p style="color:#94a3b8;margin-bottom:24px">Dein EU AI Act Schutzschild ist aktiv. Kein Bußgeld mehr.</p>
  <div style="background:#0d0d1a;border-radius:8px;padding:20px;margin-bottom:24px;border:1px solid #f59e0b">
    <p style="color:#e2e8f0;font-size:16px;margin:0 0 12px"><strong>Nächste Schritte:</strong></p>
    <ol style="color:#94a3b8;line-height:2.2;margin:0">
      <li>Shop-Domain eingeben → <a href="{BASE_URL}/api/scan" style="color:#f59e0b">POST {BASE_URL}/api/scan</a></li>
      <li>Compliance-Report + Banner-Code erhalten (JSON)</li>
      <li>Banner-Code in Shopify Theme.liquid einfügen (5 Min.)</li>
      <li>Täglicher Re-Scan + Telegram-Alert bei Änderung</li>
    </ol>
  </div>
  <div style="background:#1a0a0a;border:1px solid #ef4444;border-radius:8px;padding:16px;margin:24px 0">
    <p style="color:#f87171;margin:0;font-size:14px"><strong>⏰ Frist: 2. August 2026</strong><br>EU KI-Act Art. 50 tritt in Kraft. Du bist jetzt geschützt.</p>
  </div>
  <p style="color:#44446a;font-size:12px;margin-top:32px">AIITEC · {email} · <a href="{BASE_URL}" style="color:#44446a">{BASE_URL}</a></p>
</div>""",
    },
    "enterprise": {
        "subject": "✅ Intelligence Suite aktiv — erster Marktreport heute Nacht",
        "html": lambda email: f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#030308;color:#e2e8f0;padding:32px;border-radius:12px">
  <h1 style="color:#10b981;font-size:28px;margin-bottom:8px">Intelligence Suite ist live! 📡</h1>
  <p style="color:#94a3b8;margin-bottom:24px">Dein Marktintelligenz-System ist aktiviert. Täglich. Automatisch.</p>
  <div style="background:#0d0d1a;border-radius:8px;padding:20px;margin-bottom:24px;border:1px solid #10b981">
    <p style="color:#e2e8f0;margin:0 0 12px"><strong>Was du bekommst:</strong></p>
    <ul style="color:#94a3b8;line-height:2.2;margin:0">
      <li>🔍 Täglicher Wettbewerber-Scan (Preise, Produkte, Kampagnen)</li>
      <li>📈 Google Trends + Reddit Sentiment für deine Branche</li>
      <li>💡 KI-generierte Handlungsempfehlungen</li>
      <li>📱 Telegram-Push täglich 07:00 Uhr</li>
      <li>🎯 Lead Agent + Compliance Wächter inklusive</li>
    </ul>
  </div>
  <p style="color:#44446a;font-size:12px;margin-top:32px">AIITEC · {email} · <a href="{BASE_URL}" style="color:#44446a">{BASE_URL}</a></p>
</div>""",
    },
}

ONBOARDING_SEQUENCE = [
    {"day": 1, "subject": "📊 Tag 1: Dein Lead-Dashboard erklärt", "body": lambda u: f"So liest du deinen ersten Report: {u}/dashboard — alle Leads mit Score, Kontaktdaten und vorgeschlagenem Outreach-Text."},
    {"day": 3, "subject": "🎯 Tag 3: Erste Antworten — was jetzt?", "body": lambda u: f"Wenn ein Lead antwortet: Unser KI-Reply-Assistant ist unter {u}/api/reply — einfach die Antwort einfügen, KI generiert den perfekten Follow-up."},
    {"day": 7, "subject": "💡 Woche 1: Conversionrate optimieren", "body": lambda u: f"A/B-Test starten: {u}/api/ab-test — wir testen 2 Betreffzeilen gleichzeitig. Gewinner-Template läuft automatisch weiter."},
    {"day": 14, "subject": "📈 Woche 2: Hochskalieren", "body": lambda u: f"Mehr Leads = mehr Umsatz. Upgrade auf Enterprise: +Compliance Wächter +Intelligence Suite. Alles unter {u}/#enterprise."},
]


async def add_to_mailchimp(email: str, plan: str, tags: list = None) -> bool:
    if not MAILCHIMP_API_KEY or "your_" in MAILCHIMP_API_KEY:
        log.info("[DRY-RUN] Mailchimp: %s → %s", email, plan)
        return True
    import base64
    auth = base64.b64encode(f"anystring:{MAILCHIMP_API_KEY}".encode()).decode()
    payload = {
        "email_address": email,
        "status": "subscribed",
        "merge_fields": {"PLAN": plan, "SOURCE": "aiitec-saas"},
        "tags": (tags or []) + [f"plan-{plan}", "aiitec"],
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
                    ok = "Member Exists" in body or "already a list member" in body.lower()
                return ok
    except Exception as e:
        log.error("Mailchimp error: %s", e)
        return False


async def add_to_klaviyo(email: str, plan: str) -> bool:
    if not KLAVIYO_API_KEY or "your_" in KLAVIYO_API_KEY:
        log.info("[DRY-RUN] Klaviyo: %s → %s", email, plan)
        return True
    try:
        async with aiohttp.ClientSession() as s:
            profile_payload = {"data": {"type": "profile", "attributes": {"email": email, "properties": {"plan": plan, "source": "aiitec-saas"}}}}
            async with s.post(
                "https://a.klaviyo.com/api/profiles/",
                json=profile_payload,
                headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}", "revision": "2024-10-15", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status in (200, 201, 409):
                    data = await r.json()
                    profile_id = data.get("data", {}).get("id", "")
                    if profile_id and KLAVIYO_LIST_ID:
                        await s.post(
                            f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST_ID}/relationships/profiles/",
                            json={"data": [{"type": "profile", "id": profile_id}]},
                            headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}", "revision": "2024-10-15"},
                            timeout=aiohttp.ClientTimeout(total=10),
                        )
                    return True
    except Exception as e:
        log.error("Klaviyo error: %s", e)
    return False


async def send_welcome_email(email: str, plan: str) -> bool:
    mc_ok = await add_to_mailchimp(email, plan, tags=["welcome"])
    kl_ok = await add_to_klaviyo(email, plan)
    log.info("Welcome email: MC=%s KL=%s → %s plan=%s", mc_ok, kl_ok, email, plan)
    return mc_ok or kl_ok


async def onboard_new_subscriber(email: str, plan: str):
    await send_welcome_email(email, plan)
    log.info("Onboarding gestartet: %s / %s", email, plan)
