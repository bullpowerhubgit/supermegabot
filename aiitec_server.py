#!/usr/bin/env python3
"""AIITEC SaaS — Autonome Geldmaschine
3 Produkte: Lead Agent · Compliance Wächter · Intelligence Suite
Stripe · Mailchimp · Klaviyo · Twitter · Telegram · Railway
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
import aiohttp

BASE_DIR = Path(__file__).parent
import sys
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    _env = BASE_DIR.parent / ".env"
    if _env.exists():
        for line in _env.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))

from modules.lead_finder import lead_scan_loop, get_lead_stats, get_all_leads
from modules.email_engine import onboard_new_subscriber
from modules.auto_poster import twitter_posting_loop, telegram_marketing_loop
from modules.reply_engine import reply_watchdog_loop, process_replies_once
from modules.twilio_handler import build_voice_twiml, notify_incoming_call, notify_voicemail, notify_transcript
from modules.sofia_voice_agent import (
    sofia_ws_handler, handle_incoming_call, handle_call_history, handle_call_stats,
    _init_db as _init_calls_db,
)
from modules.twilio_sms_blast import run_blast, send_single_sms
from modules.whatsapp_outreach import (
    handle_wa_webhook_verify, handle_wa_webhook_event, run_wa_blast,
)
from modules.linkedin_poster import linkedin_posting_loop, post_to_linkedin
from modules.stripe_portal import handle_portal
from modules.whatsapp_token_manager import (
    check_wa_token, process_new_token, run_token_health_check,
)
from modules.ollama_client import (
    ollama_available, list_models, ollama_chat, pull_model,
)
from modules.ai_client import ai_chat, ai_complete, api_status as ai_api_status, start_health_monitor
from modules.social_autoposter import run_social_cycle
from modules.email_sequence_engine import enroll_customer, process_due_emails, get_stats as email_stats
from modules.stripe_automation import get_revenue_summary, get_subscriptions, get_balance as stripe_balance
from modules.klaviyo_automation import ping as klaviyo_ping, get_profile_count, upsert_profile as klaviyo_upsert
from modules.content_factory import generate_blog_post, generate_social_batch

PORT         = int(os.getenv("PORT", "8091"))
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PK     = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
BASE_URL      = os.getenv("RAILWAY_STATIC_URL", f"http://localhost:{PORT}")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

log = logging.getLogger("AIITECSaaS")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_start   = time.time()
_revenue = {"total_mrr": 0, "subscribers": {}}

# ── Pläne ─────────────────────────────────────────────────────────────────────
PLANS = {
    "starter": {
        "name": "Lead Agent",
        "price_eur": 500,
        "tagline": "KI findet täglich 10 neue Kunden für dich",
        "color": "#6366f1",
        "features": [
            "KI-Agent scannt täglich 50+ B2B-Firmen",
            "10+ qualifizierte Leads pro Tag",
            "Personalisierte Outreach-Emails (automatisch)",
            "Antwort-Tracking + CRM-Integration",
            "Telegram-Alert bei heißen Leads",
        ],
        "stripe_price_data": {
            "currency": "eur",
            "unit_amount": 50000,
            "recurring": {"interval": "month"},
            "product_data": {"name": "AIITEC Lead Agent — KI-B2B-Vertrieb"},
        },
    },
    "pro": {
        "name": "Compliance Wächter",
        "price_eur": 1500,
        "tagline": "EU AI Act konform in 24h. Kein Bußgeld.",
        "color": "#f59e0b",
        "features": [
            "Täglicher Compliance-Scan (AI Act Art. 50 + DSGVO)",
            "Automatisches Disclosure-Banner für deinen Shop",
            "Bußgeld-Früherkennung (bis €15 Mio. Risiko)",
            "Rechtssicherer Bericht für Dokumentationspflicht",
            "Unbegrenzte Shops + API-Zugang",
        ],
        "stripe_price_data": {
            "currency": "eur",
            "unit_amount": 150000,
            "recurring": {"interval": "month"},
            "product_data": {"name": "AIITEC Compliance Wächter — EU AI Act + DSGVO"},
        },
    },
    "enterprise": {
        "name": "Intelligence Suite",
        "price_eur": 2000,
        "tagline": "Wettbewerber-Radar. Täglich. Automatisch.",
        "color": "#10b981",
        "features": [
            "Alles aus Lead Agent + Compliance Wächter",
            "Täglicher Wettbewerber-Scan (Preise, Produkte, Kampagnen)",
            "Google Trends + Reddit Sentiment deiner Branche",
            "KI-generierte Handlungsempfehlungen",
            "Telegram-Push täglich 07:00 + API-Vollzugang",
        ],
        "stripe_price_data": {
            "currency": "eur",
            "unit_amount": 200000,
            "recurring": {"interval": "month"},
            "product_data": {"name": "AIITEC Intelligence Suite — Full Automation"},
        },
    },
}


# ── Stripe ────────────────────────────────────────────────────────────────────
async def create_stripe_session(plan_key: str, email: str, success_url: str, cancel_url: str) -> str:
    plan = PLANS.get(plan_key)
    if not plan:
        raise ValueError(f"Unbekannter Plan: {plan_key}")
    if not STRIPE_SECRET:
        return f"{BASE_URL}/success?plan={plan_key}&email={email}&demo=1"
    pd = plan["stripe_price_data"]
    data = {
        "mode": "subscription",
        "customer_email": email,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price_data][currency]": pd["currency"],
        "line_items[0][price_data][unit_amount]": str(pd["unit_amount"]),
        "line_items[0][price_data][recurring][interval]": pd["recurring"]["interval"],
        "line_items[0][price_data][product_data][name]": pd["product_data"]["name"],
        "line_items[0][quantity]": "1",
        "payment_method_types[0]": "card",
        "payment_method_types[1]": "sepa_debit",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=data,
            headers={"Authorization": f"Bearer {STRIPE_SECRET}"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            resp = await r.json()
            if "url" not in resp:
                raise RuntimeError(f"Stripe: {resp}")
            return resp["url"]


# ── Routes ────────────────────────────────────────────────────────────────────
async def handle_index(req):
    return web.Response(text=_landing_page(), content_type="text/html")


async def handle_checkout(req):
    try:
        body = await req.json()
    except Exception:
        body = dict(req.rel_url.query)
    plan  = body.get("plan", "starter")
    email = body.get("email", "")
    if plan not in PLANS:
        return web.json_response({"error": "Unbekannter Plan"}, status=400)
    if not email or "@" not in email:
        return web.json_response({"error": "E-Mail erforderlich"}, status=400)
    try:
        url = await create_stripe_session(
            plan, email,
            success_url=f"{BASE_URL}/success?plan={plan}&email={email}",
            cancel_url=f"{BASE_URL}/?cancelled=1",
        )
        return web.json_response({"checkout_url": url, "plan": plan})
    except Exception as e:
        log.error("Checkout Fehler: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def handle_success(req):
    plan  = req.rel_url.query.get("plan", "starter")
    email = req.rel_url.query.get("email", "")
    _revenue["subscribers"][email] = {"plan": plan, "ts": datetime.now(timezone.utc).isoformat()}
    _revenue["total_mrr"] += PLANS.get(plan, {}).get("price_eur", 0)
    if email:
        asyncio.create_task(onboard_new_subscriber(email, plan))
        await _notify_telegram(
            f"💰 <b>Neuer Kunde!</b>\n"
            f"📧 {email}\n"
            f"📦 Plan: {PLANS[plan]['name']}\n"
            f"💶 MRR +€{PLANS[plan]['price_eur']}/mo\n"
            f"📈 Gesamt MRR: €{_revenue['total_mrr']}/mo"
        )
    return web.Response(text=_success_page(plan, email), content_type="text/html")


async def handle_stripe_webhook(req):
    payload = await req.read()
    sig = req.headers.get("Stripe-Signature", "")
    try:
        event = json.loads(payload)
        etype = event.get("type", "")
        if etype == "checkout.session.completed":
            session = event["data"]["object"]
            email   = session.get("customer_email", "")
            plan    = session.get("metadata", {}).get("plan", "starter")
            if email:
                asyncio.create_task(onboard_new_subscriber(email, plan))
                log.info("Zahlung bestätigt: %s / %s", email, plan)
    except Exception as e:
        log.error("Webhook Fehler: %s", e)
    return web.json_response({"received": True})


async def handle_health(req):
    return web.json_response({
        "status": "ok",
        "service": "aiitec-saas",
        "uptime_seconds": round(time.time() - _start),
        "mrr_eur": _revenue["total_mrr"],
        "subscribers": len(_revenue["subscribers"]),
    })


async def handle_plans(req):
    return web.json_response({
        k: {kk: vv for kk, vv in v.items() if kk != "stripe_price_data"}
        for k, v in PLANS.items()
    })


async def handle_leads(req):
    stats = get_lead_stats()
    return web.json_response(stats)


async def handle_scan(req):
    """Kostenloser Compliance-Scan für Lead-Magneten."""
    try:
        body = await req.json()
    except Exception:
        body = dict(req.rel_url.query)
    domain = body.get("domain", req.rel_url.query.get("domain", ""))
    if not domain:
        return web.json_response({"error": "domain fehlt"}, status=400)
    from modules.lead_finder import scan_store_for_ai_widgets
    async with aiohttp.ClientSession() as session:
        result = await scan_store_for_ai_widgets(domain, session)
    result["upgrade_url"] = f"{BASE_URL}/#compliance"
    result["fix_available"] = bool(result.get("violations"))
    return web.json_response(result)


async def handle_stats(req):
    leads = get_lead_stats()
    return web.json_response({
        "mrr_eur": _revenue["total_mrr"],
        "subscribers": len(_revenue["subscribers"]),
        "leads": leads,
        "uptime_seconds": round(time.time() - _start),
    })


# ── Twilio Webhooks ───────────────────────────────────────────────────────────
async def handle_twilio_voice(req):
    """Twilio ruft diese URL an wenn jemand auf +17625685298 anruft."""
    data = await req.post()
    caller   = data.get("From", data.get("Caller", "unbekannt"))
    call_sid = data.get("CallSid", "")
    asyncio.create_task(notify_incoming_call(caller, call_sid))
    twiml = build_voice_twiml(missed=False)
    return web.Response(text=twiml, content_type="text/xml")


async def handle_twilio_recording(req):
    """Twilio-Callback wenn Voicemail-Aufnahme fertig."""
    data = await req.post()
    caller   = data.get("From", data.get("Caller", "unbekannt"))
    duration = data.get("RecordingDuration", "?")
    rec_url  = data.get("RecordingUrl", "")
    asyncio.create_task(notify_voicemail(caller, duration, rec_url))
    return web.Response(text="<Response/>", content_type="text/xml")


async def handle_twilio_transcript(req):
    """Twilio-Callback wenn Transkript fertig."""
    data = await req.post()
    caller     = data.get("From", data.get("Caller", "unbekannt"))
    transcript = data.get("TranscriptionText", "")
    rec_sid    = data.get("RecordingSid", "")
    if transcript:
        asyncio.create_task(notify_transcript(caller, transcript, rec_sid))
    return web.Response(text="<Response/>", content_type="text/xml")


# ── Reply Engine Trigger ──────────────────────────────────────────────────────
async def handle_reply_trigger(req):
    """Manueller Trigger: sofort einen Email-Reply-Scan starten."""
    stats = await process_replies_once()
    return web.json_response({"status": "ok", "stats": stats})


# ── SMS Blast API ─────────────────────────────────────────────────────────────
async def handle_sms_blast(req):
    """POST /api/sms/blast — SMS Kampagne starten."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    max_sms   = int(body.get("max_sms", 50))
    product   = body.get("product", "")
    dry_run   = bool(body.get("dry_run", False))
    stats = await run_blast(max_sms=max_sms, product_filter=product, dry_run=dry_run)
    return web.json_response(stats)


async def _handle_wa_blast(req):
    try:
        body = await req.json()
    except Exception:
        body = {}
    stats = await run_wa_blast(
        max_sends=int(body.get("max_sends", 20)),
        dry_run=bool(body.get("dry_run", False)),
    )
    return web.json_response(stats)


async def handle_sms_single(req):
    """POST /api/sms/send — Einzelne SMS senden."""
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)
    to  = body.get("to", "")
    msg = body.get("message", "")
    if not to or not msg:
        return web.json_response({"error": "'to' und 'message' erforderlich"}, status=400)
    result = await send_single_sms(to, msg)
    return web.json_response(result)


# ── Telegram Notify ──────────────────────────────────────────────────────────
async def _notify_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass


# ── Landing Page ─────────────────────────────────────────────────────────────
def _landing_page() -> str:
    days = max(0, (datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days)
    plans_html = ""
    for key, plan in PLANS.items():
        features = "".join(f'<li style="color:#94a3b8;padding:6px 0;border-bottom:1px solid #1e1e3a">✓ {f}</li>' for f in plan["features"])
        plans_html += f"""
        <div style="background:#0d0d1a;border:1px solid {plan['color']}33;border-radius:16px;padding:28px;display:flex;flex-direction:column">
          <div style="color:{plan['color']};font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">{plan['name']}</div>
          <div style="font-size:36px;font-weight:800;color:#f1f5f9;margin-bottom:4px">€{plan['price_eur']:,}<span style="font-size:16px;font-weight:400;color:#64748b">/mo</span></div>
          <div style="color:#94a3b8;font-size:14px;margin-bottom:20px">{plan['tagline']}</div>
          <ul style="list-style:none;padding:0;margin:0 0 24px;flex:1">{features}</ul>
          <button onclick="checkout('{key}')" style="width:100%;background:{plan['color']};color:#fff;padding:14px;border-radius:10px;font-size:16px;font-weight:700;border:none;cursor:pointer;transition:opacity 0.2s" onmouseover="this.style.opacity=0.85" onmouseout="this.style.opacity=1">
            Jetzt starten — €{plan['price_eur']:,}/mo
          </button>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIITEC — KI-Automatisierung für B2B</title>
<meta name="description" content="Lead Agent · Compliance Wächter · Intelligence Suite. Vollautonome KI-Systeme die für dich Geld verdienen.">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#030308;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6}}
a{{color:#6366f1;text-decoration:none}}
.container{{max-width:1100px;margin:0 auto;padding:0 24px}}
.hero{{padding:80px 0 60px;text-align:center}}
.badge{{display:inline-block;background:#1e1e3a;color:#f59e0b;font-size:13px;font-weight:600;padding:6px 16px;border-radius:20px;margin-bottom:24px;border:1px solid #f59e0b44}}
h1{{font-size:clamp(36px,6vw,64px);font-weight:900;line-height:1.1;margin-bottom:20px;background:linear-gradient(135deg,#e2e8f0,#6366f1);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.subtitle{{font-size:20px;color:#94a3b8;max-width:600px;margin:0 auto 40px}}
.stats{{display:flex;gap:40px;justify-content:center;flex-wrap:wrap;margin-bottom:60px}}
.stat{{text-align:center}}
.stat-num{{font-size:36px;font-weight:800;color:#6366f1}}
.stat-label{{font-size:13px;color:#64748b;margin-top:4px}}
.plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px;margin-bottom:80px}}
.countdown{{background:linear-gradient(135deg,#1a0a0a,#0d0d1a);border:1px solid #ef444444;border-radius:16px;padding:32px;text-align:center;margin-bottom:60px}}
.countdown-num{{font-size:56px;font-weight:900;color:#ef4444;line-height:1}}
.faq{{margin-bottom:80px}}
.faq-item{{border-bottom:1px solid #1e1e3a;padding:20px 0}}
.faq-q{{font-weight:600;color:#e2e8f0;margin-bottom:8px}}
.faq-a{{color:#94a3b8;font-size:14px;line-height:1.7}}
footer{{border-top:1px solid #1e1e3a;padding:32px 0;text-align:center;color:#44446a;font-size:13px}}
.modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;align-items:center;justify-content:center}}
.modal.open{{display:flex}}
.modal-box{{background:#0d0d1a;border:1px solid #2d2d3d;border-radius:16px;padding:32px;width:100%;max-width:420px}}
.modal-box h3{{font-size:20px;font-weight:700;margin-bottom:6px}}
.modal-box p{{color:#94a3b8;font-size:14px;margin-bottom:20px}}
.modal-input{{width:100%;background:#030308;border:1px solid #2d2d3d;color:#e2e8f0;padding:14px;border-radius:8px;font-size:16px;margin-bottom:12px}}
.modal-input:focus{{outline:none;border-color:#6366f1}}
.modal-btn{{width:100%;background:#6366f1;color:#fff;padding:14px;border-radius:8px;font-size:16px;font-weight:700;border:none;cursor:pointer}}
.modal-close{{position:absolute;top:16px;right:20px;font-size:24px;cursor:pointer;color:#64748b;background:none;border:none}}
#anchor-leads{{scroll-margin-top:80px}}
#anchor-compliance{{scroll-margin-top:80px}}
#anchor-enterprise{{scroll-margin-top:80px}}
</style>
</head>
<body>

<div class="hero container">
  <div class="badge">⚡ Vollautonome KI-Systeme — Läuft 24/7 ohne dich</div>
  <h1>Dein Unternehmen auf Autopilot</h1>
  <p class="subtitle">Leads finden. Compliance sichern. Wettbewerber überwachen. Alles automatisch — während du schläfst.</p>
  <div class="stats">
    <div class="stat"><div class="stat-num">10+</div><div class="stat-label">qualifizierte Leads/Tag</div></div>
    <div class="stat"><div class="stat-num">€15M</div><div class="stat-label">max. AI-Act Bußgeld</div></div>
    <div class="stat"><div class="stat-num">24/7</div><div class="stat-label">vollautomatisch</div></div>
    <div class="stat"><div class="stat-num">48h</div><div class="stat-label">bis erste Ergebnisse</div></div>
  </div>
</div>

<div class="container">
  <div class="countdown" id="anchor-compliance">
    <div style="color:#94a3b8;font-size:14px;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px">EU KI-Act Artikel 50 — Frist</div>
    <div class="countdown-num">{days}</div>
    <div style="color:#ef4444;font-size:20px;font-weight:600;margin:8px 0">Tage verbleibend</div>
    <div style="color:#94a3b8;font-size:14px;max-width:500px;margin:0 auto">
      Shops mit KI-Chat, KI-Empfehlungen oder KI-Zahlungsoptionen ohne Offenlegung riskieren <strong style="color:#f87171">Bußgelder bis €15.000.000</strong>. Unser Compliance Wächter schützt dich in 24h.
    </div>
  </div>

  <div id="anchor-leads" style="margin-bottom:24px">
    <h2 style="font-size:28px;font-weight:800;margin-bottom:8px;text-align:center">Wähle dein System</h2>
    <p style="text-align:center;color:#94a3b8;margin-bottom:32px">Alle Pläne monatlich kündbar · Keine versteckten Kosten</p>
  </div>

  <div class="plans">{plans_html}</div>

  <div class="faq" id="anchor-enterprise">
    <h2 style="font-size:24px;font-weight:800;margin-bottom:24px">Häufige Fragen</h2>
    <div class="faq-item">
      <div class="faq-q">Wie schnell sehe ich erste Ergebnisse?</div>
      <div class="faq-a">Lead Agent: Erste qualifizierte Leads innerhalb 24h. Compliance Wächter: Scan-Report + Banner-Code in 10 Minuten. Intelligence Suite: Erste Wettbewerber-Reports beim nächsten Tages-Run (spätestens 24h).</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Was genau macht der Lead Agent?</div>
      <div class="faq-a">Der KI-Agent scannt täglich 50+ B2B-Firmen in deiner Zielgruppe, qualifiziert sie nach Firmengröße und Entscheidungsträger, generiert personalisierte Outreach-Emails und versendet sie automatisch. Du siehst nur die Antworten.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Ist der Compliance Wächter rechtssicher?</div>
      <div class="faq-a">Der automatisch generierte Disclosure-Banner erfüllt die Anforderungen von EU KI-Act Art. 50. Für rechtsverbindliche Beratung empfehlen wir zusätzlich einen Anwalt — wir übernehmen die technische Implementierung.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Kann ich jederzeit kündigen?</div>
      <div class="faq-a">Ja, jederzeit zum Monatsende. Kein Mindestvertrag, keine Kündigungsgebühr. Über Stripe selbst verwaltet.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Was kostet der Einstieg wirklich?</div>
      <div class="faq-a">Lead Agent: €500/mo · Compliance Wächter: €1.500/mo · Intelligence Suite: €2.000/mo. Keine Einrichtungsgebühr, keine versteckten Kosten. Stripe-Rechnung monatlich.</div>
    </div>
  </div>
</div>

<footer>
  <div class="container">
    <p>AIITEC · Rudolf Sarkany · <a href="mailto:aiitecbuuss@gmail.com">aiitecbuuss@gmail.com</a> · <a href="{BASE_URL}/api/scan">Kostenloser Compliance-Scan</a></p>
    <p style="margin-top:8px">© 2026 AIITEC · Alle Rechte vorbehalten · <a href="{BASE_URL}/#compliance">Datenschutz</a></p>
  </div>
</footer>

<div class="modal" id="checkout-modal">
  <div class="modal-box" style="position:relative">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h3 id="modal-title">Plan auswählen</h3>
    <p id="modal-desc">Gib deine E-Mail ein um fortzufahren</p>
    <input class="modal-input" type="email" id="modal-email" placeholder="deine@email.de" autocomplete="email">
    <button class="modal-btn" id="modal-btn" onclick="submitCheckout()">Weiter zu Stripe →</button>
    <p style="color:#44446a;font-size:11px;margin-top:12px;text-align:center">Sicher via Stripe · Kein Account nötig · Kündbar jederzeit</p>
  </div>
</div>

<script>
let _plan = 'starter';
function checkout(plan) {{
  _plan = plan;
  const names = {{starter:'Lead Agent — €500/mo',pro:'Compliance Wächter — €1.500/mo',enterprise:'Intelligence Suite — €2.000/mo'}};
  document.getElementById('modal-title').textContent = names[plan] || plan;
  document.getElementById('checkout-modal').classList.add('open');
  document.getElementById('modal-email').focus();
}}
function closeModal() {{
  document.getElementById('checkout-modal').classList.remove('open');
}}
document.getElementById('checkout-modal').addEventListener('click', function(e) {{
  if(e.target === this) closeModal();
}});
async function submitCheckout() {{
  const email = document.getElementById('modal-email').value.trim();
  if(!email || !email.includes('@')) {{
    document.getElementById('modal-email').style.borderColor='#ef4444';
    return;
  }}
  const btn = document.getElementById('modal-btn');
  btn.textContent = 'Weiterleitung...';
  btn.disabled = true;
  try {{
    const r = await fetch('/api/checkout', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{plan: _plan, email}})
    }});
    const d = await r.json();
    if(d.checkout_url) {{
      window.location.href = d.checkout_url;
    }} else {{
      btn.textContent = 'Fehler — bitte erneut versuchen';
      btn.disabled = false;
    }}
  }} catch(e) {{
    btn.textContent = 'Fehler — bitte erneut versuchen';
    btn.disabled = false;
  }}
}}
document.getElementById('modal-email').addEventListener('keydown', function(e) {{
  if(e.key === 'Enter') submitCheckout();
}});
</script>
</body>
</html>"""


def _success_page(plan: str, email: str) -> str:
    p = PLANS.get(plan, PLANS["starter"])
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Zahlung erfolgreich — AIITEC</title>
<style>body{{background:#030308;color:#e2e8f0;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{background:#0d0d1a;border:1px solid {p['color']}44;border-radius:16px;padding:48px;text-align:center;max-width:480px;width:90%}}
h1{{color:{p['color']};font-size:28px;margin-bottom:12px}}p{{color:#94a3b8;margin-bottom:24px}}
.btn{{display:inline-block;background:{p['color']};color:#fff;padding:14px 28px;border-radius:10px;font-weight:700;text-decoration:none}}</style>
</head><body>
<div class="box">
  <div style="font-size:64px;margin-bottom:16px">✅</div>
  <h1>Zahlung bestätigt!</h1>
  <p><strong>{p['name']}</strong> ist jetzt aktiv.<br>Willkommens-Email an <strong>{email}</strong> unterwegs.</p>
  <a href="{BASE_URL}" class="btn">Zum Dashboard →</a>
</div>
</body></html>"""


# ── Universal AI Route ────────────────────────────────────────────────────────
async def handle_ai_status(req):
    """GET /api/ai/status — zeigt Status aller APIHunt Provider."""
    return web.json_response(ai_api_status())


async def handle_ai_chat(req):
    """POST /api/ai/chat — Claude → OpenAI → OpenRouter → Ollama."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)

    messages  = data.get("messages")
    prompt    = data.get("prompt", "")
    system    = data.get("system", "")
    max_tok   = int(data.get("max_tokens", 500))
    temp      = float(data.get("temperature", 0.7))
    prefer    = data.get("prefer", "claude")

    if not messages:
        if not prompt:
            return web.json_response({"error": "messages or prompt required"}, status=400)
        messages = [{"role": "user", "content": prompt}]

    result = await ai_chat(messages, system=system, max_tokens=max_tok,
                           temperature=temp, prefer=prefer)
    if result is None:
        return web.json_response({"error": "Alle KI-Provider fehlgeschlagen"}, status=503)
    return web.json_response({"response": result})


# ── Ollama Routes ─────────────────────────────────────────────────────────────
async def handle_ollama_status(req):
    avail = await ollama_available()
    models = await list_models() if avail else []
    return web.json_response({
        "available": avail,
        "model_count": len(models),
        "models": [m["name"] for m in models],
    })


async def handle_ollama_models(req):
    models = await list_models()
    return web.json_response({"models": models})


async def handle_ollama_chat(req):
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)

    messages = data.get("messages")
    if not messages:
        prompt = data.get("prompt", "")
        if not prompt:
            return web.json_response({"error": "messages or prompt required"}, status=400)
        messages = [{"role": "user", "content": prompt}]

    model   = data.get("model")
    max_tok = int(data.get("max_tokens", 800))
    temp    = float(data.get("temperature", 0.7))

    result = await ollama_chat(messages, model=model, temperature=temp, max_tokens=max_tok)
    if result is None:
        return web.json_response({"error": "Ollama nicht verfügbar"}, status=503)
    return web.json_response({"response": result, "model": model or "auto"})


async def handle_ollama_pull(req):
    try:
        data = await req.json()
        model = data.get("model", "")
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)

    if not model:
        return web.json_response({"error": "model required"}, status=400)

    asyncio.create_task(pull_model(model))
    return web.json_response({"status": "pulling", "model": model})


# ── WhatsApp Token Routes ──────────────────────────────────────────────────────
async def handle_wa_token_status(req):
    result = await check_wa_token()
    return web.json_response(result)


async def handle_wa_token_update(req):
    """POST {"token": "EAAA..."} oder Telegram-Bot-Befehl /wa_token EAAA..."""
    try:
        data = await req.json()
        new_token = data.get("token", "").strip()
    except Exception:
        text = await req.text()
        new_token = text.strip()

    if not new_token:
        return web.json_response({"ok": False, "error": "token fehlt"}, status=400)

    result = await process_new_token(new_token)
    status = 200 if result.get("ok") else 400
    return web.json_response(result, status=status)


async def email_sequence_loop():
    """Verarbeitet fällige Email-Sequenz-Schritte alle 15 Minuten."""
    await asyncio.sleep(90)
    while True:
        try:
            result = await process_due_emails()
            if result.get("sent", 0) > 0:
                log.info("Email-Sequenz: %d E-Mails gesendet", result["sent"])
        except Exception as e:
            log.warning("Email-Sequenz Fehler: %s", e)
        await asyncio.sleep(15 * 60)


async def social_posting_loop():
    """Social Media Autoposter — FB/IG/LinkedIn alle 4 Stunden."""
    await asyncio.sleep(120)
    while True:
        try:
            result = await run_social_cycle()
            log.info("Social-Cycle: %s", result)
        except Exception as e:
            log.warning("Social-Poster Fehler: %s", e)
        await asyncio.sleep(4 * 3600)


async def wa_token_watchdog_loop():
    """Prüft WA Token alle 6 Stunden — bei Fehler Telegram-Alarm."""
    import asyncio
    await asyncio.sleep(60)  # kurz warten nach Start
    while True:
        try:
            await run_token_health_check()
        except Exception as e:
            log.warning("WA token check error: %s", e)
        await asyncio.sleep(6 * 3600)


# ── Email Sequence Routes ─────────────────────────────────────────────────────
async def handle_email_enroll(req):
    """POST /api/email/enroll — Lead in Sequenz einschreiben."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)
    email    = data.get("email", "")
    sequence = data.get("sequence", "welcome")
    name     = data.get("first_name", "")
    if not email or "@" not in email:
        return web.json_response({"error": "E-Mail erforderlich"}, status=400)
    result = await enroll_customer(email, sequence=sequence, first_name=name, metadata=data.get("metadata"))
    return web.json_response(result)


async def handle_email_stats(req):
    """GET /api/email/stats — Sequenz-Statistiken."""
    stats = await email_stats()
    return web.json_response(stats)


# ── Stripe Automation Routes ──────────────────────────────────────────────────
async def handle_stripe_revenue(req):
    """GET /api/stripe/revenue — Umsatz-Zusammenfassung."""
    days = int(req.rel_url.query.get("days", 30))
    summary = await get_revenue_summary(days_back=days)
    return web.json_response(summary)


async def handle_stripe_subs(req):
    """GET /api/stripe/subs — Aktive Abonnements."""
    limit  = int(req.rel_url.query.get("limit", 20))
    status = req.rel_url.query.get("status", "active")
    subs   = await get_subscriptions(limit=limit, status=status)
    return web.json_response({"count": len(subs), "subscriptions": subs})


async def handle_stripe_balance(req):
    """GET /api/stripe/balance — Stripe Guthaben."""
    balance = await stripe_balance()
    return web.json_response(balance)


# ── Klaviyo Routes ────────────────────────────────────────────────────────────
async def handle_klaviyo_status(req):
    """GET /api/klaviyo/status — Verbindungstest."""
    ok, msg = await klaviyo_ping()
    count   = await get_profile_count() if ok else 0
    return web.json_response({"ok": ok, "message": msg, "profile_count": count})


async def handle_klaviyo_subscribe(req):
    """POST /api/klaviyo/subscribe — Profil anlegen/aktualisieren."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)
    email = data.get("email", "")
    if not email or "@" not in email:
        return web.json_response({"error": "E-Mail erforderlich"}, status=400)
    profile_id = await klaviyo_upsert(
        email      = email,
        first_name = data.get("first_name", ""),
        last_name  = data.get("last_name", ""),
        phone      = data.get("phone", ""),
        properties = data.get("properties"),
    )
    return web.json_response({"ok": bool(profile_id), "profile_id": profile_id})


# ── Compliance Wächter Routes (AI Act Art.50) ────────────────────────────────
async def handle_compliance_scan(req):
    """POST /api/compliance/scan — Website auf AI Act Art.50 scannen."""
    try:
        data = await req.json()
    except Exception:
        data = dict(req.rel_url.query)
    url = data.get("url", data.get("domain", ""))
    if not url:
        return web.json_response({"error": "url oder domain erforderlich"}, status=400)
    if not url.startswith("http"):
        url = f"https://{url}"
    from modules.ai_act_art50_engine import scan_website_for_ai_content
    result = await scan_website_for_ai_content(url)
    return web.json_response(result)


async def handle_compliance_report(req):
    """POST /api/compliance/report — Vollständiger Compliance-Report."""
    try:
        data = await req.json()
    except Exception:
        data = dict(req.rel_url.query)
    domain = data.get("domain", "").replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        return web.json_response({"error": "domain erforderlich"}, status=400)
    from modules.ai_act_art50_engine import generate_compliance_report
    report = await generate_compliance_report(domain)
    return web.json_response(report)


async def handle_compliance_banner(req):
    """POST /api/compliance/banner — Disclosure-Banner-Code generieren."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    shop = data.get("shop", "")
    lang = data.get("language", "de")
    from modules.ai_act_art50_engine import generate_disclosure_banner
    banner = await generate_disclosure_banner(shop_name=shop, language=lang)
    return web.json_response(banner)


async def handle_compliance_status(req):
    """GET /api/compliance/status — Art50 Engine Status."""
    from modules.ai_act_art50_engine import get_status
    status = await get_status()
    return web.json_response(status)


# ── Content Factory Routes ────────────────────────────────────────────────────
async def handle_content_blog(req):
    """POST /api/content/blog — KI-Blog-Post generieren."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)
    topic    = data.get("topic", "")
    keywords = data.get("keywords", [])
    lang     = data.get("language", "de")
    if not topic:
        return web.json_response({"error": "topic erforderlich"}, status=400)
    result = await generate_blog_post(topic=topic, keywords=keywords, language=lang)
    return web.json_response(result)


async def handle_content_social(req):
    """POST /api/content/social — Social-Media-Batch generieren."""
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"error": "JSON required"}, status=400)
    message   = data.get("message", "")
    brand_url = data.get("brand_url", BASE_URL)
    if not message:
        return web.json_response({"error": "message erforderlich"}, status=400)
    result = await generate_social_batch(core_message=message, brand_url=brand_url)
    return web.json_response(result)


# ── App Setup ─────────────────────────────────────────────────────────────────
async def on_startup(app):
    _init_calls_db()
    asyncio.create_task(lead_scan_loop())
    asyncio.create_task(twitter_posting_loop())
    asyncio.create_task(telegram_marketing_loop())
    asyncio.create_task(reply_watchdog_loop())
    asyncio.create_task(linkedin_posting_loop())
    asyncio.create_task(wa_token_watchdog_loop())
    asyncio.create_task(email_sequence_loop())
    asyncio.create_task(social_posting_loop())
    start_health_monitor()
    log.info("AIITEC SaaS gestartet auf Port %d", PORT)
    log.info("URL: %s", BASE_URL)
    log.info("Pläne: %s", ", ".join(f"{k}=€{v['price_eur']}" for k, v in PLANS.items()))
    log.info("Reply Watchdog: aktiv (alle 10 Min)")
    log.info("WA Token Watchdog: aktiv (alle 6h)")


def build_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.router.add_get("/",              handle_index)
    app.router.add_get("/health",        handle_health)
    app.router.add_post("/api/checkout", handle_checkout)
    app.router.add_get("/api/checkout",  handle_checkout)
    app.router.add_get("/success",       handle_success)
    app.router.add_post("/webhook",      handle_stripe_webhook)
    app.router.add_get("/api/plans",     handle_plans)
    app.router.add_get("/api/leads",     handle_leads)
    app.router.add_get("/api/scan",      handle_scan)
    app.router.add_post("/api/scan",     handle_scan)
    app.router.add_get("/api/stats",     handle_stats)
    # Twilio Legacy Webhooks (Fallback ohne OpenAI Realtime)
    app.router.add_post("/webhook/twilio-voice",       handle_twilio_voice)
    app.router.add_post("/webhook/twilio-recording",   handle_twilio_recording)
    app.router.add_post("/webhook/twilio-transcript",  handle_twilio_transcript)
    # Sofia KI-Rezeptionistin — Haupt-Webhook + WebSocket Bridge
    app.router.add_post("/api/phone/incoming",   handle_incoming_call)
    app.router.add_get("/api/phone/calls",       handle_call_history)
    app.router.add_get("/api/phone/stats",       handle_call_stats)
    app.router.add_get("/ws/sofia",              sofia_ws_handler)
    # SMS Blast
    app.router.add_post("/api/sms/blast",        handle_sms_blast)
    app.router.add_post("/api/sms/send",         handle_sms_single)
    # Reply Engine manueller Trigger
    app.router.add_post("/api/reply-now",  handle_reply_trigger)
    app.router.add_get("/api/reply-now",   handle_reply_trigger)
    # WhatsApp Business
    app.router.add_get("/webhook/whatsapp",  handle_wa_webhook_verify)
    app.router.add_post("/webhook/whatsapp", handle_wa_webhook_event)
    app.router.add_post("/api/wa/blast",     _handle_wa_blast)
    # Stripe Billing Portal
    app.router.add_get("/portal",            handle_portal)
    app.router.add_post("/portal",           handle_portal)
    # WhatsApp Token Management
    app.router.add_get("/api/whatsapp/token/status", handle_wa_token_status)
    app.router.add_post("/api/whatsapp/token",        handle_wa_token_update)
    # KI universell — APIHunt (Ollama → Groq → DeepSeek → OpenRouter → Gemini → Anthropic → OpenAI → Perplexity)
    app.router.add_post("/api/ai/chat",               handle_ai_chat)
    app.router.add_get("/api/ai/status",              handle_ai_status)
    # Ollama lokal
    app.router.add_get("/api/ollama/status",          handle_ollama_status)
    app.router.add_get("/api/ollama/models",          handle_ollama_models)
    app.router.add_post("/api/ollama/chat",           handle_ollama_chat)
    app.router.add_post("/api/ollama/pull",           handle_ollama_pull)
    # Email Sequenzen
    app.router.add_post("/api/email/enroll",          handle_email_enroll)
    app.router.add_get("/api/email/stats",            handle_email_stats)
    # Stripe Automation
    app.router.add_get("/api/stripe/revenue",         handle_stripe_revenue)
    app.router.add_get("/api/stripe/subs",            handle_stripe_subs)
    app.router.add_get("/api/stripe/balance",         handle_stripe_balance)
    # Klaviyo
    app.router.add_get("/api/klaviyo/status",         handle_klaviyo_status)
    app.router.add_post("/api/klaviyo/subscribe",     handle_klaviyo_subscribe)
    # Content Factory
    app.router.add_post("/api/content/blog",          handle_content_blog)
    app.router.add_post("/api/content/social",        handle_content_social)
    # Compliance Wächter (AI Act Art.50 — Kernprodukt)
    app.router.add_post("/api/compliance/scan",       handle_compliance_scan)
    app.router.add_get("/api/compliance/scan",        handle_compliance_scan)
    app.router.add_post("/api/compliance/report",     handle_compliance_report)
    app.router.add_post("/api/compliance/banner",     handle_compliance_banner)
    app.router.add_get("/api/compliance/status",      handle_compliance_status)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), port=PORT, host="0.0.0.0")
