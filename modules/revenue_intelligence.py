"""Revenue Intelligence System — forecast, optimize, plug leaks, maximize every €."""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")

_AI_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _ai(prompt: str, max_tokens: int = 1024) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


async def _stripe_get(path: str, params: dict = None) -> dict:
    if not STRIPE_SECRET_KEY:
        return {}
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.get(
            f"https://api.stripe.com/v1/{path}",
            auth=aiohttp.BasicAuth(STRIPE_SECRET_KEY, ""),
            params=params or {},
        ) as r:
            return await r.json() if r.status == 200 else {}


async def _supabase_query(table: str, select: str = "*", filters: str = "") -> list:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters:
        url += f"&{filters}"
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Accept-Profile": "public"}
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.get(url, headers=headers) as r:
            return await r.json() if r.status == 200 else []


async def _supabase_insert(table: str, data: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
               "Content-Type": "application/json", "Prefer": "return=minimal"}
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, json=data) as r:
            return r.status in (200, 201)


# ── 1. Revenue Forecaster ─────────────────────────────────────────────────────

async def forecast_revenue(days_ahead: int = 30) -> dict:
    """Pull 90-day Stripe history → AI forecast next N days."""
    since = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp())
    charges = await _stripe_get("charges", {"created[gte]": str(since), "limit": "100"})
    data_points = charges.get("data", [])

    # Aggregate by day
    daily: dict[str, float] = {}
    for ch in data_points:
        if ch.get("status") != "succeeded":
            continue
        day = datetime.fromtimestamp(ch["created"], tz=timezone.utc).strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + ch.get("amount", 0) / 100

    total_90d = sum(daily.values())
    avg_daily = total_90d / 90 if total_90d else 0

    prompt = (
        f"Du bist Revenue-Analyst. Letzte 90 Tage Umsatz: €{total_90d:.2f} total, "
        f"€{avg_daily:.2f}/Tag Durchschnitt. "
        f"Prognostiziere die nächsten {days_ahead} Tage. "
        f"Gib zurück: Gesamtprognose (€), Trend (steigend/stagnierend/fallend), "
        f"Konfidenz (hoch/mittel/niedrig), 3 konkrete Maßnahmen. Kurz und präzise auf Deutsch."
    )
    ai_analysis = await _ai(prompt, 512)

    forecast_total = avg_daily * days_ahead * 1.05  # 5% growth assumption
    result = {
        "total_90d_actual": round(total_90d, 2),
        "avg_daily": round(avg_daily, 2),
        "forecast_total": round(forecast_total, 2),
        "days_ahead": days_ahead,
        "ai_analysis": ai_analysis,
        "data_points": len(data_points),
    }
    await _supabase_insert("agent_execution_log", {
        "agent": "revenue_intelligence", "action": "forecast",
        "result": str(result)[:500], "created_at": datetime.now(timezone.utc).isoformat()
    })
    return result


# ── 2. Price Intelligence ─────────────────────────────────────────────────────

async def scan_competitor_prices(competitor_urls: list = None) -> dict:
    """Fetch competitor pages, extract prices, compare."""
    urls = competitor_urls or [
        "https://apps.shopify.com/categories/marketing-social-media-posting",
    ]
    results = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        for url in urls:
            try:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        html = await r.text()
                        prices = re.findall(r'€\s*(\d+[\.,]\d+|\d+)', html)
                        results.append({"url": url, "prices_found": prices[:5]})
            except Exception as e:
                results.append({"url": url, "error": str(e)[:80]})
    return {"competitors_scanned": len(results), "results": results}


async def calculate_optimal_price(product_id: str, cost: float, demand_signal: float = 1.0) -> float:
    """Dynamic optimal price: 3x cost base + demand + time adjustments."""
    base = cost * 3
    demand_adj = base * 0.10 * (demand_signal - 1)
    hour = datetime.now().hour
    time_adj = base * 0.15 if 9 <= hour <= 20 else 0  # peak hours premium
    optimal = max(base + demand_adj + time_adj, cost * 2)
    return round(optimal, 2)


# ── 3. Churn Prediction ───────────────────────────────────────────────────────

async def identify_churn_risk() -> list[dict]:
    """Score customers by inactivity and trigger retention campaigns."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    clients = await _supabase_query(
        "clients", "id,email,created_at,last_active",
        f"last_active=lt.{cutoff}&order=last_active.asc&limit=50"
    )
    at_risk = []
    for c in clients:
        days_inactive = 0
        if c.get("last_active"):
            try:
                last = datetime.fromisoformat(c["last_active"].replace("Z", "+00:00"))
                days_inactive = (datetime.now(timezone.utc) - last).days
            except Exception as _e:
                log.debug("suppressed: %s", _e)
        score = min(int(days_inactive * 3), 100)
        entry = {"customer_id": c.get("id"), "email": c.get("email"),
                 "churn_score": score, "days_inactive": days_inactive,
                 "recommended_action": "win_back_campaign" if score >= 60 else "nudge_email"}
        at_risk.append(entry)
        if score >= 60 and c.get("email"):
            log.info(f"High churn risk: {c.get('email')} score={score}")
            try:
                from modules.email_sequence_engine import enroll
                await enroll(c["email"], "winback")
            except Exception as _e:
                log.warning(f"Winback enroll failed for {c.get('email')}: {_e}")
    return at_risk


# ── 4. LTV Calculator ─────────────────────────────────────────────────────────

async def calculate_customer_ltv(customer_email: str) -> dict:
    """Pull Stripe charge history for customer, calculate LTV + segment."""
    customers = await _stripe_get("customers", {"email": customer_email, "limit": "1"})
    data = customers.get("data", [])
    if not data:
        return {"email": customer_email, "ltv": 0, "segment": "Unknown", "orders": 0}

    customer_id = data[0]["id"]
    charges = await _stripe_get("charges", {"customer": customer_id, "limit": "100"})
    orders = [c for c in charges.get("data", []) if c.get("status") == "succeeded"]
    total = sum(c.get("amount", 0) for c in orders) / 100

    segment = "Bronze"
    if total >= 500:
        segment = "Platinum"
    elif total >= 200:
        segment = "Gold"
    elif total >= 50:
        segment = "Silver"

    return {
        "email": customer_email, "stripe_id": customer_id,
        "ltv": round(total, 2), "orders": len(orders), "segment": segment,
        "avg_order": round(total / max(len(orders), 1), 2),
    }


# ── 5. Revenue Leak Detector ──────────────────────────────────────────────────

async def detect_revenue_leaks() -> list[dict]:
    """Find money being left on the table and auto-act."""
    leaks = []

    # Check failed Stripe payments
    since = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    failed = await _stripe_get("charges", {
        "created[gte]": str(since), "status": "failed", "limit": "20"
    })
    for ch in failed.get("data", []):
        leaks.append({
            "type": "failed_payment",
            "amount": ch.get("amount", 0) / 100,
            "email": ch.get("billing_details", {}).get("email", ""),
            "action": "retry_payment_email",
        })

    # Check Supabase leads without follow-up
    cutoff_leads = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    stale_leads = await _supabase_query(
        "lead_events", "id,email,created_at",
        f"created_at=lt.{cutoff_leads}&contacted=is.false&limit=20"
    )
    for lead in stale_leads:
        leaks.append({
            "type": "uncontacted_lead",
            "email": lead.get("email", ""),
            "created_at": lead.get("created_at", ""),
            "action": "send_follow_up_email",
        })

    if leaks:
        msg = f"🚨 <b>Revenue Leaks detected: {len(leaks)}</b>\n"
        for lk in leaks[:5]:
            msg += f"• {lk['type']}: {lk.get('email','?')} → {lk['action']}\n"
        await _telegram(msg)

    return leaks


# ── 6. Competitive Intelligence ───────────────────────────────────────────────

async def track_competitors_daily() -> dict:
    """Daily competitor monitoring with AI summary."""
    competitors = [
        "https://klaviyo.com/pricing",
        "https://omnisend.com/pricing",
    ]
    findings = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        for url in competitors:
            try:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                    if r.status == 200:
                        html = await r.text()
                        prices = re.findall(r'\$\s*(\d+)|€\s*(\d+)', html)
                        findings.append({"url": url, "prices": [p[0] or p[1] for p in prices[:3]]})
            except Exception as e:
                findings.append({"url": url, "error": str(e)[:60]})

    summary = await _ai(
        f"Konkurrenz-Analyse für E-Commerce Automation SaaS. "
        f"Gefundene Daten: {findings}. "
        f"Gib 3 konkrete Empfehlungen wie wir uns abheben können. Auf Deutsch, kurz.",
        400
    )
    result = {"findings": findings, "ai_summary": summary, "checked_at": datetime.now(timezone.utc).isoformat()}
    await _telegram(f"📊 <b>Konkurrenz-Monitor</b>\n{summary[:400]}")
    return result


# ── 7. Revenue Autopilot ──────────────────────────────────────────────────────

async def revenue_autopilot() -> dict:
    """Hourly: scan all revenue signals, auto-act on each."""
    import random
    actions_taken = []

    # Check for new Stripe subscriptions in last hour
    since = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    subs = await _stripe_get("subscriptions", {"created[gte]": str(since), "limit": "10"})
    new_subs = subs.get("data", [])
    if new_subs:
        for sub in new_subs:
            await _telegram(
                f"🎉 <b>Neuer Subscriber!</b>\n"
                f"Plan: {sub.get('items',{}).get('data',[{}])[0].get('price',{}).get('nickname','?')}\n"
                f"ID: {sub.get('id','?')}"
            )
        actions_taken.append(f"alerted_new_subs:{len(new_subs)}")

    # Detect revenue leaks
    leaks = await detect_revenue_leaks()
    if leaks:
        actions_taken.append(f"leaks_found:{len(leaks)}")

    # Check churn risk
    at_risk = await identify_churn_risk()
    high_risk = [c for c in at_risk if c.get("churn_score", 0) >= 80]
    if high_risk:
        await _telegram(
            f"⚠️ <b>{len(high_risk)} Kunden mit hohem Churn-Risiko!</b>\n"
            + "\n".join(f"• {c['email']} (Score: {c['churn_score']})" for c in high_risk[:3])
        )
        actions_taken.append(f"churn_alerts:{len(high_risk)}")

    # Proaktiv: DS24 Affiliate Blast wenn keine neuen Subs (immer Umsatz pushen)
    if not new_subs:
        try:
            ds24_link = os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/669750")
            shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
            promos = [
                f"💰 Passives Einkommen mit KI-Automation? Starte jetzt → {ds24_link}",
                f"🚀 Shopify-Shop vollautomatisch betreiben — so geht's: {ds24_link}",
                f"📈 Affiliate-Marketing + Shopify = monatliche Einnahmen. Infos: {ds24_link}",
                f"🤖 KI-Business in 2026: Shopify, DS24, Klaviyo — alles automatisch. Start: {ds24_link}",
            ]
            promo = random.choice(promos)
            from modules.brutus_core import fire
            await fire("💰 Revenue Push", promo, channels=["telegram"])
            actions_taken.append("ds24_promo_blast")
        except Exception as _e:
            log.debug("suppressed: %s", _e)

    # Proaktiv: Gumroad Digital Products bewerben
    try:
        ds24_url = "https://www.checkout-ds24.com/product/669750"
        ds24_promos = [
            f"📦 Digitale Produkte — sofort downloadbar: {gumroad_url}",
            f"💡 KI E-Commerce Autopilot 2026 — 50+ Templates: {gumroad_url}",
        ]
        ds24_promo = random.choice(ds24_promos)
        from modules.brutus_core import fire
        await fire("Gumroad Promo", gumroad_promo, channels=["telegram"])
        actions_taken.append("gumroad_promo_blast")
    except Exception as _e:
        log.debug("suppressed: %s", _e)

    return {"actions": actions_taken, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── 8. Daily Revenue Briefing ─────────────────────────────────────────────────

async def send_revenue_briefing() -> dict:
    """Every morning 8am: full revenue briefing to Telegram."""
    # Yesterday's revenue
    yesterday_start = int((datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0).timestamp())
    yesterday_end = int((datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=23, minute=59, second=59).timestamp())

    charges = await _stripe_get("charges", {
        "created[gte]": str(yesterday_start),
        "created[lte]": str(yesterday_end),
        "status": "succeeded", "limit": "100"
    })
    yesterday_revenue = sum(c.get("amount", 0) for c in charges.get("data", [])) / 100

    # Today's leads
    today_start = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)).isoformat()
    leads_today = await _supabase_query("lead_events", "id", f"created_at=gte.{today_start}")

    # AI recommendations
    recommendations = await _ai(
        f"E-Commerce SaaS Revenue-Briefing. "
        f"Gestern: €{yesterday_revenue:.2f} Umsatz. "
        f"Neue Leads heute: {len(leads_today)}. "
        f"Gib 3 konkrete Maßnahmen für heute, die sofort Umsatz bringen. Kurz, auf Deutsch.",
        400
    )

    msg = (
        f"☀️ <b>Revenue Briefing — {datetime.now().strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 Gestern: <b>€{yesterday_revenue:.2f}</b>\n"
        f"👥 Leads heute: <b>{len(leads_today)}</b>\n\n"
        f"🎯 <b>Top 3 Maßnahmen heute:</b>\n{recommendations[:500]}"
    )
    await _telegram(msg)

    return {
        "yesterday_revenue": round(yesterday_revenue, 2),
        "leads_today": len(leads_today),
        "briefing_sent": True,
    }
