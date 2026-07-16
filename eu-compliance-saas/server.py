#!/usr/bin/env python3
"""EU Compliance Revenue Engine — Autonome Geldmaschine
4 Einnahmeströme: AI-Act · HS-Code · VAT-OSS · ZVG-Leads
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
sys_path_parent = BASE_DIR.parent
import sys
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    _env = BASE_DIR / ".env"
    if _env.exists():
        for line in _env.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from modules.ai_act_scanner import generate_compliance_report, bulk_scan_stores, ARTICLE_50_DISCLOSURE_BANNER
from modules.hs_classifier import classify_hs_code, classify_product_catalog, calculate_customs_impact
from modules.vat_oss_engine import calculate_vat_liability, generate_quarterly_prefill, assess_non_eu_seller_risk, EU_VAT_RATES, OSS_REGISTRATION_STEPS
from modules.zvg_radar import fetch_zvg_listings, get_nrw_market_stats
from modules.auto_poster import twitter_posting_loop, telegram_marketing_loop, post_new_subscriber_announcement
from modules.lead_finder import lead_scan_loop, get_lead_stats
from modules.email_engine import onboard_new_subscriber, send_welcome_email

PORT = int(os.getenv("PORT", "8090"))
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PK = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL = os.getenv("RAILWAY_STATIC_URL", f"http://localhost:{PORT}")

log = logging.getLogger("EUComplianceSaaS")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_start = time.time()
_subscribers = {}  # email -> {plan, stripe_customer_id, created_at}
_leads_cache = []
_lead_cache_ts = 0

# ---------------------------------------------------------------------------
# Stripe Checkout
# ---------------------------------------------------------------------------
# High-Ticket Live Payment Links (Wave 3 — Stripe Live)
PLANS = {
    "starter": {
        "name": "AI-Act Starter",
        "price_eur": 497,
        "payment_link": "https://buy.stripe.com/14A4gBanE7XY1gc40u4F42Ef",
        "features": ["AI-Act Art. 50 Scanner", "Disclosure-Banner-Generator", "1 Shop", "E-Mail-Report"],
        "stripe_price_data": {"currency": "eur", "unit_amount": 49700, "recurring": {"interval": "month"}, "product_data": {"name": "EU Compliance Starter — AI-Act Scanner"}},
    },
    "pro": {
        "name": "Compliance Pro",
        "price_eur": 997,
        "payment_link": "https://buy.stripe.com/7sY5kFeDUa665ws7cG4F42Eg",
        "features": ["Alles in Starter", "HS-Code Klassifizierung (500 Produkte/mo)", "EU VAT OSS Assistent", "5 Shops", "Prioritäts-Support"],
        "stripe_price_data": {"currency": "eur", "unit_amount": 99700, "recurring": {"interval": "month"}, "product_data": {"name": "EU Compliance Pro — AI-Act + HS-Code + VAT OSS"}},
    },
    "enterprise": {
        "name": "Revenue Engine",
        "price_eur": 2497,
        "payment_link": "https://buy.stripe.com/9B63cx67ofqq0c88gK4F42Eh",
        "features": ["Alles in Pro", "ZVG NRW Lead Radar (unbegrenzt)", "HS-Code Bulk (5000 Produkte/mo)", "Unbegrenzte Shops", "API-Zugang", "Telegram-Alerts"],
        "stripe_price_data": {"currency": "eur", "unit_amount": 249700, "recurring": {"interval": "month"}, "product_data": {"name": "EU Compliance Enterprise — Full Revenue Engine"}},
    },
}


async def create_stripe_session(plan_key: str, email: str, success_url: str, cancel_url: str) -> str:
    """Erstellt Stripe Checkout Session."""
    if not STRIPE_SECRET:
        return f"{BASE_URL}/demo-checkout?plan={plan_key}&email={email}"
    plan = PLANS[plan_key]
    payload = {
        "mode": "subscription",
        "customer_email": email,
        "line_items[0][price_data][currency]": plan["stripe_price_data"]["currency"],
        "line_items[0][price_data][unit_amount]": str(plan["stripe_price_data"]["unit_amount"]),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": plan["stripe_price_data"]["product_data"]["name"],
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    headers = {"Authorization": f"Bearer {STRIPE_SECRET}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                return data.get("url", cancel_url)
    except Exception as e:
        log.error("Stripe error: %s", e)
        return cancel_url


# ---------------------------------------------------------------------------
# Telegram Notifications
# ---------------------------------------------------------------------------
async def telegram_notify(msg: str):
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


# ---------------------------------------------------------------------------
# Autonomes Lead-Gen (läuft im Hintergrund)
# ---------------------------------------------------------------------------
async def autonomous_lead_gen_loop():
    """Läuft alle 6h: scannt öffentliche Shopify-Stores, sendet Compliance-Alerts."""
    SAMPLE_SHOPS = [
        "ineedit.com.co",
        "allbirds.com",
        "gymshark.com",
        "babbel.com",
    ]
    while True:
        try:
            log.info("Autonomes Lead-Gen startet...")
            results = await bulk_scan_stores(SAMPLE_SHOPS)
            violations = [r for r in results if isinstance(r, dict) and r.get("violations")]
            if violations:
                msg = (
                    f"🚨 <b>EU Compliance Alert</b>\n"
                    f"⚖️ {len(violations)} Shops mit AI-Act-Verstößen gefunden!\n"
                    f"💰 Bußgeldrisiko: bis €15 Mio. pro Shop\n"
                    f"📅 Frist: 2. August 2026 ({(datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days} Tage)\n"
                    f"🔗 {BASE_URL}"
                )
                await telegram_notify(msg)
            log.info("Lead-Gen: %d Violations gefunden", len(violations))
        except Exception as e:
            log.error("Lead-Gen error: %s", e)
        await asyncio.sleep(6 * 3600)


async def zvg_refresh_loop():
    """Aktualisiert ZVG-Leads alle 4h."""
    global _leads_cache, _lead_cache_ts
    while True:
        try:
            _leads_cache = await fetch_zvg_listings("NRW", 50)
            _lead_cache_ts = time.time()
            log.info("ZVG: %d Leads geladen", len(_leads_cache))
            if _leads_cache:
                top = _leads_cache[0]
                await telegram_notify(
                    f"🏠 <b>ZVG NRW Update</b>\n"
                    f"📊 {len(_leads_cache)} neue Zwangsversteigerungs-Leads\n"
                    f"🏆 Top Lead: {top.get('property_type','?')} in {top.get('location','?')}\n"
                    f"💶 Schätzwert: €{top.get('estimated_value_eur',0):,.0f}"
                )
        except Exception as e:
            log.error("ZVG refresh error: %s", e)
        await asyncio.sleep(4 * 3600)


async def daily_revenue_report():
    """Sendet täglich einen Revenue-Report via Telegram."""
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            subscriber_count = len(_subscribers)
            mrr = sum(PLANS.get(s.get("plan", ""), {}).get("price_eur", 0) for s in _subscribers.values())
            await telegram_notify(
                f"💰 <b>EU Compliance SaaS — Daily Report</b>\n"
                f"👥 Subscribers: {subscriber_count}\n"
                f"📈 MRR: €{mrr:,.0f}/Monat\n"
                f"📅 Nächste AI-Act-Frist: {(datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days} Tage\n"
                f"🔗 {BASE_URL}"
            )
        except Exception as e:
            log.error("Daily report error: %s", e)


# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------

async def handle_health(req):
    return web.json_response({"status": "ok", "service": "eu-compliance-saas", "uptime": time.time() - _start})


async def handle_index(req):
    html = _get_landing_page()
    return web.Response(text=html, content_type="text/html")


async def handle_checkout(req):
    try:
        body = await req.json()
    except Exception:
        body = dict(req.rel_url.query)
    plan = body.get("plan", "starter")
    email = body.get("email", "")
    if plan not in PLANS:
        return web.json_response({"error": "Invalid plan"}, status=400)
    # Prefer live Payment Links (high-ticket Wave 3)
    plink = PLANS[plan].get("payment_link")
    if plink:
        await telegram_notify(
            f"🛒 <b>Checkout → Payment Link</b>\nPlan: {plan} (€{PLANS[plan]['price_eur']}/mo)\nEmail: {email or '—'}"
        )
        return web.json_response({"checkout_url": plink, "plan": plan, "mode": "payment_link"})
    if not email:
        return web.json_response({"error": "Email required"}, status=400)
    success_url = f"{BASE_URL}/success?plan={plan}&email={email}"
    cancel_url = f"{BASE_URL}/?cancelled=1"
    url = await create_stripe_session(plan, email, success_url, cancel_url)
    await telegram_notify(f"🛒 <b>Neuer Checkout!</b>\nPlan: {plan} (€{PLANS[plan]['price_eur']}/mo)\nEmail: {email}")
    return web.json_response({"checkout_url": url, "plan": plan})


async def handle_success(req):
    plan = req.rel_url.query.get("plan", "")
    email = req.rel_url.query.get("email", "")
    if email and plan:
        price = PLANS.get(plan, {}).get("price_eur", 0)
        _subscribers[email] = {"plan": plan, "created_at": datetime.now(timezone.utc).isoformat()}
        await telegram_notify(
            f"✅ <b>NEUER SUBSCRIBER!</b>\n"
            f"📧 {email}\n"
            f"📦 Plan: {plan} — €{price}/Monat\n"
            f"💰 MRR +€{price}"
        )
        asyncio.create_task(onboard_new_subscriber(email, plan))
        asyncio.create_task(post_new_subscriber_announcement(email, plan, price))
    return web.Response(text=_get_success_page(plan, email), content_type="text/html")


async def handle_scan_shop(req):
    """POST /api/scan — AI-Act Compliance Scan."""
    try:
        body = await req.json()
        shop_url = body.get("shop_url", "").strip().replace("https://", "").replace("http://", "")
        if not shop_url:
            return web.json_response({"error": "shop_url required"}, status=400)
        report = await generate_compliance_report(shop_url)
        return web.json_response(report)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_hs_classify(req):
    """POST /api/hs-classify — HS Code Klassifizierung."""
    try:
        body = await req.json()
        title = body.get("title", "")
        description = body.get("description", "")
        if not title:
            return web.json_response({"error": "title required"}, status=400)
        result = await classify_hs_code(title, description, ANTHROPIC_KEY)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_hs_bulk(req):
    """POST /api/hs-bulk — Bulk HS Code Klassifizierung."""
    try:
        body = await req.json()
        products = body.get("products", [])
        if not products:
            return web.json_response({"error": "products array required"}, status=400)
        results = await classify_product_catalog(products[:100], ANTHROPIC_KEY)
        return web.json_response({"results": results, "count": len(results)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_customs_impact(req):
    """GET /api/customs-impact?products=N&orders=M"""
    n = int(req.rel_url.query.get("products", 100))
    m = int(req.rel_url.query.get("orders", 500))
    return web.json_response(calculate_customs_impact(n, m))


async def handle_vat_calculate(req):
    """POST /api/vat/calculate — MwSt-Berechnung."""
    try:
        body = await req.json()
        sales = body.get("sales_by_country", {})
        if not sales:
            return web.json_response({"error": "sales_by_country required"}, status=400)
        return web.json_response(calculate_vat_liability(sales))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_vat_risk(req):
    """POST /api/vat/risk — Risikoanalyse für Nicht-EU-Verkäufer."""
    try:
        body = await req.json()
        country = body.get("country", "US")
        revenue = float(body.get("annual_eu_revenue", 50000))
        return web.json_response(assess_non_eu_seller_risk(country, revenue))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_vat_prefill(req):
    """POST /api/vat/prefill — OSS Quartalsvoranmeldung."""
    try:
        body = await req.json()
        q = int(body.get("quarter", 3))
        year = int(body.get("year", 2026))
        sales = body.get("sales_by_country", {"DE": 10000, "FR": 5000, "NL": 3000})
        return web.json_response(generate_quarterly_prefill(q, year, sales))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_zvg_leads(req):
    """GET /api/zvg/leads — ZVG NRW Lead-Liste."""
    global _leads_cache, _lead_cache_ts
    if not _leads_cache or (time.time() - _lead_cache_ts) > 3600:
        _leads_cache = await fetch_zvg_listings("NRW", 50)
        _lead_cache_ts = time.time()
    limit = int(req.rel_url.query.get("limit", 20))
    min_score = int(req.rel_url.query.get("min_score", 0))
    filtered = [l for l in _leads_cache if l.get("lead_score", 0) >= min_score]
    return web.json_response({
        "leads": filtered[:limit],
        "total": len(filtered),
        "market_stats": get_nrw_market_stats(),
        "cached_at": datetime.fromtimestamp(_lead_cache_ts, tz=timezone.utc).isoformat() if _lead_cache_ts else None,
    })


async def handle_zvg_stats(req):
    return web.json_response(get_nrw_market_stats())


async def handle_plans(req):
    return web.json_response({k: {kk: vv for kk, vv in v.items() if kk != "stripe_price_data"} for k, v in PLANS.items()})


async def handle_dashboard(req):
    """Internes Admin-Dashboard."""
    mrr = sum(PLANS.get(s.get("plan", ""), {}).get("price_eur", 0) for s in _subscribers.values())
    days_to_deadline = (datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    lead_stats = get_lead_stats()
    return web.json_response({
        "uptime_seconds": time.time() - _start,
        "subscribers": len(_subscribers),
        "mrr_eur": mrr,
        "arr_eur": mrr * 12,
        "leads_cached": len(_leads_cache),
        "lead_pipeline": lead_stats,
        "days_to_ai_act_deadline": days_to_deadline,
        "services": {
            "ai_act_scanner": "active",
            "hs_classifier": "active",
            "vat_oss": "active",
            "zvg_radar": "active",
            "auto_poster_twitter": "active",
            "auto_poster_telegram": "active",
            "lead_finder": "active",
            "email_engine": "active",
        },
    })


async def handle_lead_stats(req):
    return web.json_response(get_lead_stats())


# ---------------------------------------------------------------------------
# Landing Page HTML (dark theme)
# ---------------------------------------------------------------------------
def _days_to_deadline():
    d = (datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    return max(0, d)


def _get_landing_page() -> str:
    days = _days_to_deadline()
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU Compliance Revenue Engine — AI-Act · HS-Code · VAT-OSS · ZVG Leads</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0f;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;line-height:1.6}}
.hero{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:80px 20px;text-align:center}}
.countdown-badge{{display:inline-block;background:#dc2626;color:#fff;padding:8px 20px;border-radius:999px;font-size:14px;font-weight:700;margin-bottom:20px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.7}}}}
h1{{font-size:clamp(28px,5vw,56px);font-weight:800;background:linear-gradient(135deg,#818cf8,#c084fc,#fb7185);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:20px}}
.subtitle{{font-size:20px;color:#94a3b8;max-width:700px;margin:0 auto 40px}}
.cta-row{{display:flex;gap:16px;justify-content:center;flex-wrap:wrap}}
.btn-primary{{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:16px 36px;border-radius:12px;font-size:18px;font-weight:700;text-decoration:none;cursor:pointer;border:none;transition:transform 0.2s}}
.btn-primary:hover{{transform:translateY(-2px)}}
.btn-secondary{{background:transparent;color:#818cf8;padding:16px 36px;border-radius:12px;font-size:18px;font-weight:700;text-decoration:none;cursor:pointer;border:2px solid #6366f1}}
.section{{padding:60px 20px;max-width:1100px;margin:0 auto}}
.section-title{{font-size:32px;font-weight:800;text-align:center;margin-bottom:12px;color:#f1f5f9}}
.section-sub{{text-align:center;color:#94a3b8;margin-bottom:48px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px}}
.card{{background:#1e1e2e;border:1px solid #2d2d3d;border-radius:16px;padding:28px;transition:border-color 0.2s}}
.card:hover{{border-color:#6366f1}}
.card-icon{{font-size:36px;margin-bottom:16px}}
.card-title{{font-size:20px;font-weight:700;color:#f1f5f9;margin-bottom:8px}}
.card-desc{{color:#94a3b8;font-size:15px}}
.card-price{{margin-top:12px;font-size:22px;font-weight:800;color:#818cf8}}
.fine-box{{background:#1a0a0a;border:1px solid #dc2626;border-radius:16px;padding:32px;margin:40px 0;text-align:center}}
.fine-amount{{font-size:48px;font-weight:900;color:#dc2626}}
.plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}}
.plan{{background:#1e1e2e;border:1px solid #2d2d3d;border-radius:16px;padding:32px;position:relative}}
.plan.featured{{border-color:#6366f1;background:linear-gradient(135deg,#1e1e3e,#1a1a2e)}}
.plan-badge{{position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:#6366f1;color:#fff;padding:4px 16px;border-radius:999px;font-size:12px;font-weight:700}}
.plan-name{{font-size:22px;font-weight:800;color:#f1f5f9;margin-bottom:8px}}
.plan-price{{font-size:42px;font-weight:900;color:#818cf8}}
.plan-period{{font-size:16px;color:#64748b}}
.plan-features{{list-style:none;margin:24px 0;color:#94a3b8}}
.plan-features li{{padding:8px 0;border-bottom:1px solid #2d2d3d;display:flex;align-items:center;gap:8px}}
.plan-features li::before{{content:"✓";color:#22c55e;font-weight:700}}
.checkout-btn{{width:100%;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px;border-radius:10px;font-size:16px;font-weight:700;border:none;cursor:pointer;transition:transform 0.2s;margin-top:16px}}
.checkout-btn:hover{{transform:translateY(-2px)}}
.urgency{{background:linear-gradient(135deg,#1a0a0a,#0a0a0f);border-top:1px solid #dc2626;padding:40px 20px;text-align:center}}
.stat-row{{display:flex;justify-content:center;gap:48px;flex-wrap:wrap;margin:40px 0}}
.stat{{text-align:center}}
.stat-num{{font-size:40px;font-weight:900;color:#818cf8}}
.stat-label{{color:#64748b;font-size:14px}}
footer{{text-align:center;padding:40px 20px;color:#475569;font-size:14px;border-top:1px solid #1e1e2e}}
</style>
</head>
<body>
<div class="hero">
  <div class="countdown-badge">⚠️ NUR NOCH {days} TAGE — AI-Act Frist: 2. August 2026</div>
  <h1>EU Compliance Revenue Engine</h1>
  <p class="subtitle">Automatisierter Schutz vor EU-Bußgeldern bis €15 Mio. — für Shopify-Shops, Nicht-EU-Verkäufer & Immobilien-Investoren</p>
  <div class="cta-row">
    <a class="btn-primary" href="#plans">Jetzt absichern ab €49/Monat</a>
    <a class="btn-secondary" href="/api/scan" target="_blank">Gratis Shop-Scan</a>
  </div>
</div>

<div class="section">
  <h2 class="section-title">4 EU-Pflichttermine. 4 Einnahmeströme.</h2>
  <p class="section-sub">Wer wartet, zahlt. Wer automatisiert, verdient.</p>
  <div class="cards">
    <div class="card">
      <div class="card-icon">🤖</div>
      <div class="card-title">AI-Act Art. 50</div>
      <div class="card-desc">Chatbot-Offenlegungspflicht & KI-Content-Kennzeichnung. Frist: 2. August 2026.</div>
      <div class="card-price">bis €15 Mio. Bußgeld</div>
    </div>
    <div class="card">
      <div class="card-icon">📦</div>
      <div class="card-title">EU Zollreform</div>
      <div class="card-desc">€150-Freigrenze abgeschafft. €3 pro HS-Code ab 1. Juli 2026. Automatisierte Klassifizierung.</div>
      <div class="card-price">€5/Paket ohne Tool</div>
    </div>
    <div class="card">
      <div class="card-icon">🇪🇺</div>
      <div class="card-title">EU VAT OSS</div>
      <div class="card-desc">Nicht-EU-Verkäufer: Null-Schwellenwert. Sofortiger MwSt-Pflicht ab dem 1. EU-Verkauf.</div>
      <div class="card-price">+20% MwSt-Risiko</div>
    </div>
    <div class="card">
      <div class="card-icon">🏠</div>
      <div class="card-title">ZVG NRW Leads</div>
      <div class="card-desc">Zwangsversteigerungs-Radar. NRW = 19% des DE-Volumens. €50–200 CPL für B2B.</div>
      <div class="card-price">€50–200 / Lead</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="fine-box">
    <div style="color:#94a3b8;font-size:16px;margin-bottom:8px">AI-Act Verstoß kostet bis zu</div>
    <div class="fine-amount">€15.000.000</div>
    <div style="color:#94a3b8;margin-top:8px">oder 3% des weltweiten Jahresumsatzes — Art. 99 Abs. 4 lit. g EU-KI-VO</div>
    <div style="margin-top:24px;font-size:20px;color:#22c55e;font-weight:700">vs. €497/Monat mit unserem Starter-Plan</div>
  </div>
</div>

<div class="section">
  <div class="stat-row">
    <div class="stat"><div class="stat-num">{days}</div><div class="stat-label">Tage bis AI-Act-Frist</div></div>
    <div class="stat"><div class="stat-num">4,6 Mrd.</div><div class="stat-label">Pakete/Jahr betroffen (Zoll)</div></div>
    <div class="stat"><div class="stat-num">8.500+</div><div class="stat-label">ZVG-Fälle/Jahr in NRW</div></div>
    <div class="stat"><div class="stat-num">27</div><div class="stat-label">EU-Länder, null Schwellenwert</div></div>
  </div>
</div>

<div class="section" id="plans">
  <h2 class="section-title">Wähle deinen Plan</h2>
  <p class="section-sub">Monatlich kündbar. Keine Einrichtungsgebühr. Sofort aktiv.</p>
  <div class="plans">
    <div class="plan">
      <div class="plan-name">🛡️ Starter</div>
      <div><span class="plan-price">€497</span><span class="plan-period">/Monat</span></div>
      <ul class="plan-features">
        <li>AI-Act Art. 50 Scanner</li>
        <li>Disclosure-Banner-Generator</li>
        <li>1 Shopify-Shop</li>
        <li>Monatlicher Compliance-Report</li>
        <li>E-Mail-Support</li>
      </ul>
      <a class="checkout-btn" href="https://buy.stripe.com/14A4gBanE7XY1gc40u4F42Ef" style="display:block;text-align:center;text-decoration:none">Jetzt starten — €497/mo</a>
    </div>
    <div class="plan featured">
      <div class="plan-badge">BELIEBT</div>
      <div class="plan-name">⚡ Compliance Pro</div>
      <div><span class="plan-price">€997</span><span class="plan-period">/Monat</span></div>
      <ul class="plan-features">
        <li>Alles in Starter</li>
        <li>HS-Code Klassifizierung (500/mo)</li>
        <li>EU VAT OSS Assistent</li>
        <li>5 Shopify-Shops</li>
        <li>Quartals-Voranmeldung Prefill</li>
        <li>Prioritäts-Support</li>
      </ul>
      <a class="checkout-btn" href="https://buy.stripe.com/7sY5kFeDUa665ws7cG4F42Eg" style="display:block;text-align:center;text-decoration:none">Pro starten — €997/mo</a>
    </div>
    <div class="plan">
      <div class="plan-name">🚀 Revenue Engine</div>
      <div><span class="plan-price">€2.497</span><span class="plan-period">/Monat</span></div>
      <ul class="plan-features">
        <li>Alles in Pro</li>
        <li>ZVG NRW Lead Radar (∞)</li>
        <li>HS-Code Bulk (5.000/mo)</li>
        <li>Unbegrenzte Shops</li>
        <li>API-Zugang</li>
        <li>Telegram-Echtzeit-Alerts</li>
        <li>Dedicated Support</li>
      </ul>
      <a class="checkout-btn" href="https://buy.stripe.com/9B63cx67ofqq0c88gK4F42Eh" style="display:block;text-align:center;text-decoration:none">Enterprise — €2.497/mo</a>
    </div>
  </div>
</div>

<div class="urgency">
  <h2 style="font-size:28px;font-weight:800;color:#f1f5f9;margin-bottom:12px">⏰ Die Uhr läuft</h2>
  <p style="color:#94a3b8;max-width:600px;margin:0 auto">
    Artikel 50 der EU-KI-Verordnung tritt am <strong style="color:#dc2626">2. August 2026</strong> in Kraft.
    Jeder Shop mit KI-Chat, KI-Empfehlungen oder KI-generierten Inhalten braucht sofort eine Offenlegung.
    Ohne Compliance drohen Bußgelder, die jedes Startup sofort vernichten.
  </p>
</div>

<footer>
  <p>EU Compliance Revenue Engine · Powered by SuperMegaBot · <a href="/health" style="color:#6366f1">Health</a> · <a href="/api/plans" style="color:#6366f1">API</a></p>
  <p style="margin-top:8px">Rechtsgrundlagen: EU-KI-VO (EU) 2024/1689 Art. 50 · VO (EU) 2026/382 · MwSt-RL 2006/112/EG Art. 59c</p>
</footer>

<div id="checkout-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9999;display:none;align-items:center;justify-content:center">
  <div style="background:#1e1e2e;border:1px solid #6366f1;border-radius:16px;padding:40px;max-width:440px;width:90%">
    <h3 style="font-size:22px;margin-bottom:20px;color:#f1f5f9">Plan aktivieren</h3>
    <input id="checkout-email" type="email" placeholder="deine@email.de" style="width:100%;background:#0a0a0f;border:1px solid #2d2d3d;color:#e2e8f0;padding:14px;border-radius:8px;font-size:16px;margin-bottom:16px">
    <button onclick="doCheckout()" style="width:100%;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:14px;border-radius:10px;font-size:16px;font-weight:700;border:none;cursor:pointer">Weiter zu Stripe →</button>
    <p style="margin-top:12px;text-align:center;color:#475569;font-size:13px">Sicher via Stripe · Kreditkarte / SEPA / PayPal</p>
    <button onclick="closeModal()" style="position:absolute;top:16px;right:20px;background:none;border:none;color:#475569;font-size:24px;cursor:pointer">×</button>
  </div>
</div>

<script>
let _plan = 'starter';
function checkout(plan) {{
  _plan = plan;
  document.getElementById('checkout-modal').style.display='flex';
  document.getElementById('checkout-email').focus();
}}
function closeModal() {{ document.getElementById('checkout-modal').style.display='none'; }}
async function doCheckout() {{
  const email = document.getElementById('checkout-email').value.trim();
  if(!email || !email.includes('@')) {{ alert('Bitte gültige E-Mail eingeben'); return; }}
  try {{
    const r = await fetch('/api/checkout', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{plan:_plan,email}})}});
    const d = await r.json();
    if(d.checkout_url) window.location.href = d.checkout_url;
  }} catch(e) {{ alert('Fehler: ' + e.message); }}
}}
document.getElementById('checkout-modal').addEventListener('click', e => {{
  if(e.target === document.getElementById('checkout-modal')) closeModal();
}});
</script>
</body>
</html>"""


def _get_success_page(plan: str, email: str) -> str:
    plan_data = PLANS.get(plan, {})
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><title>Willkommen — EU Compliance SaaS</title>
<style>body{{background:#0a0a0f;color:#e2e8f0;font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:20px}}
.box{{background:#1e1e2e;border:1px solid #22c55e;border-radius:20px;padding:48px;max-width:500px}}
h1{{font-size:36px;color:#22c55e;margin-bottom:16px}}p{{color:#94a3b8}}
.back{{display:inline-block;margin-top:24px;background:#6366f1;color:#fff;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:700}}</style>
</head>
<body>
<div class="box">
  <h1>✅ Willkommen!</h1>
  <p>Plan: <strong style="color:#818cf8">{plan_data.get('name', plan)}</strong></p>
  <p style="margin-top:8px">€{plan_data.get('price_eur', 0)}/Monat — Bestätigung an {email}</p>
  <p style="margin-top:24px;color:#64748b">Du bist jetzt gegen EU-Compliance-Bußgelder abgesichert. Onboarding-E-Mail folgt in Kürze.</p>
  <a class="back" href="/">Zum Dashboard →</a>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------
def create_app():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/plans", handle_plans)
    app.router.add_get("/api/dashboard", handle_dashboard)
    app.router.add_post("/api/checkout", handle_checkout)
    app.router.add_get("/success", handle_success)
    app.router.add_post("/api/scan", handle_scan_shop)
    app.router.add_post("/api/hs-classify", handle_hs_classify)
    app.router.add_post("/api/hs-bulk", handle_hs_bulk)
    app.router.add_get("/api/customs-impact", handle_customs_impact)
    app.router.add_post("/api/vat/calculate", handle_vat_calculate)
    app.router.add_post("/api/vat/risk", handle_vat_risk)
    app.router.add_post("/api/vat/prefill", handle_vat_prefill)
    app.router.add_get("/api/zvg/leads", handle_zvg_leads)
    app.router.add_get("/api/zvg/stats", handle_zvg_stats)
    app.router.add_get("/api/leads", handle_lead_stats)
    return app


async def main():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("EU Compliance SaaS gestartet auf Port %s", PORT)
    await telegram_notify(
        f"🚀 <b>EU Compliance SaaS gestartet!</b>\n"
        f"🔗 {BASE_URL}\n"
        f"⏰ {_days_to_deadline()} Tage bis AI-Act-Frist\n"
        f"💰 4 Revenue-Module aktiv"
    )
    asyncio.create_task(autonomous_lead_gen_loop())
    asyncio.create_task(zvg_refresh_loop())
    asyncio.create_task(daily_revenue_report())
    asyncio.create_task(twitter_posting_loop())
    asyncio.create_task(telegram_marketing_loop(_leads_cache))
    asyncio.create_task(lead_scan_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
