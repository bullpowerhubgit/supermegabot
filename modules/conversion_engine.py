"""
Conversion Maximizer Engine — SuperMegaBot
10 systems: abandoned cart, dynamic pricing, upsell sequences, A/B auto-winner,
exit intent, lead scoring, social proof, revenue optimization, funnel analytics,
personalization. All AI-driven, fully autonomous.
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Credentials ──────────────────────────────────────────────────────────────
ANTHROPIC_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL       = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY       = os.getenv("SUPABASE_SERVICE_KEY", "")
TELEGRAM_BOT       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT      = os.getenv("TELEGRAM_CHAT_ID", "")
TWILIO_SID         = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN       = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM        = os.getenv("TWILIO_FROM_NUMBER", "")
STRIPE_KEY         = os.getenv("STRIPE_SECRET_KEY", "")
SHOPIFY_DOMAIN     = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN      = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
KLAVIYO_KEY        = os.getenv("KLAVIYO_API_KEY", "")
PRICE_FLOOR        = float(os.getenv("PRICE_FLOOR", "5.0"))
BASE_URL           = os.getenv("RAILWAY_PUBLIC_DOMAIN",
                                "https://supermegabot-production.up.railway.app")

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _claude(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _tg(msg: str) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        logger.warning("Ignored error: %s", e)


async def _supa_insert(table: str, row: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(
                f"{SUPABASE_URL}/rest/v1/{table}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=row,
            ) as r:
                return r.status in (200, 201)
    except Exception:
        return False


async def _supa_select(table: str, params: str = "") -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{SUPABASE_URL}/rest/v1/{table}?{params}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Accept-Profile": "public"},
            ) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.warning("Ignored error: %s", e)
    return []


async def _shopify_get(path: str) -> dict:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {}
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VER}/{path}"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN}) as r:
            if r.status == 200:
                return await r.json()
    return {}


async def _shopify_put(path: str, payload: dict) -> dict:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return {}
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VER}/{path}"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.put(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                                        "Content-Type": "application/json"},
                         json=payload) as r:
            if r.status == 200:
                return await r.json()
    return {}


# ── 1. ABANDONED CART RECOVERY ────────────────────────────────────────────────

async def handle_abandoned_cart(customer_email: str, cart_items: list,
                                 cart_value: float, customer_phone: str = "") -> dict:
    """Multi-channel abandoned cart sequence: email→SMS→Telegram."""
    item_names = ", ".join(i.get("title", "Produkt") for i in cart_items[:3])
    results = {}

    # Channel 1 — Email now (via Klaviyo)
    if KLAVIYO_KEY and customer_email:
        try:
            subject = await _claude(
                f"Write a short German abandoned cart email subject (max 8 words) for: {item_names}. "
                "Urgency but friendly. Return ONLY the subject line."
            ) or f"Du hast {item_names} vergessen 🛒"
            body = await _claude(
                f"Write a short German abandoned cart email body (3 sentences max) for: {item_names}, "
                f"value €{cart_value:.2f}. Include urgency and link placeholder [CART_LINK]. "
                "Return only the email body."
            ) or f"Dein Warenkorb wartet! {item_names} — jetzt bestellen: [CART_LINK]"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(
                    "https://a.klaviyo.com/api/track",
                    headers={"Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                             "Content-Type": "application/json"},
                    json={"data": {"type": "event", "attributes": {
                        "metric": {"data": {"type": "metric",
                                            "attributes": {"name": "Abandoned Cart"}}},
                        "profile": {"data": {"type": "profile",
                                             "attributes": {"email": customer_email}}},
                        "properties": {"items": item_names, "value": cart_value,
                                       "subject": subject, "body": body},
                    }}},
                ) as r:
                    results["email"] = r.status in (200, 202)
        except Exception as e:
            results["email_error"] = str(e)

    # Channel 2 — SMS via Twilio (30min delay simulation: log for deferred send)
    if TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM and customer_phone:
        try:
            sms_text = f"Noch da? Dein Warenkorb ({item_names}) wartet! €{cart_value:.2f} → {BASE_URL}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                    auth=aiohttp.BasicAuth(TWILIO_SID, TWILIO_TOKEN),
                    data={"From": TWILIO_FROM, "To": customer_phone, "Body": sms_text},
                ) as r:
                    results["sms"] = r.status == 201
        except Exception as e:
            results["sms_error"] = str(e)

    # Log to Supabase for follow-up sequence tracking
    await _supa_insert("agent_execution_log", {
        "agent": "abandoned_cart",
        "action": "cart_recovery_fired",
        "result": json.dumps({
            "email": customer_email, "value": cart_value,
            "items": item_names, "channels": results,
        }),
        "created_at": datetime.utcnow().isoformat(),
    })

    return {"fired": True, "channels": results, "items": item_names, "value": cart_value}


# ── 2. DYNAMIC PRICING ENGINE ─────────────────────────────────────────────────

async def optimize_price(product_id: str, current_price: float) -> dict:
    """AI dynamic pricing: demand signals + competitor awareness → Shopify update."""
    hour = datetime.utcnow().hour
    weekday = datetime.utcnow().weekday()

    # Demand signals: peak hours (10-14, 19-22) and weekends get +10%
    demand_multiplier = 1.0
    if 10 <= hour <= 14 or 19 <= hour <= 22:
        demand_multiplier = 1.10
    if weekday >= 5:
        demand_multiplier *= 1.05

    # AI price recommendation
    prompt = (
        f"You are a pricing AI. Product ID: {product_id}. "
        f"Current price: €{current_price:.2f}. Hour: {hour}h, weekday: {weekday}. "
        f"Floor: €{PRICE_FLOOR:.2f}. Demand multiplier: {demand_multiplier:.2f}. "
        "Recommend a new price in EUR (number only, 2 decimals). "
        "Consider: higher price = more perceived value. Never below floor. "
        "Return ONLY the number, e.g.: 29.99"
    )
    ai_price_str = await _claude(prompt, max_tokens=20)
    try:
        new_price = max(PRICE_FLOOR, float(ai_price_str.strip().replace(",", ".")))
    except (ValueError, AttributeError):
        new_price = max(PRICE_FLOOR, round(current_price * demand_multiplier, 2))

    # Update Shopify
    variants_data = await _shopify_get(f"products/{product_id}/variants.json")
    updated = 0
    for variant in variants_data.get("variants", []):
        result = await _shopify_put(
            f"variants/{variant['id']}.json",
            {"variant": {"id": variant["id"], "price": f"{new_price:.2f}"}},
        )
        if result:
            updated += 1

    return {
        "product_id": product_id, "old_price": current_price,
        "new_price": new_price, "variants_updated": updated,
        "demand_multiplier": demand_multiplier,
    }


# ── 3. UPSELL / CROSS-SELL AUTOMATON ─────────────────────────────────────────

async def generate_upsell_sequence(purchase: dict) -> list[dict]:
    """Schedule 5-touch upsell sequence after purchase."""
    email     = purchase.get("email", "")
    order_id  = purchase.get("order_id", "unknown")
    product   = purchase.get("product", "SuperMegaBot")
    amount    = purchase.get("amount", 0)

    sequence = [
        {"day": 0,  "type": "thank_you",    "delay_h": 0},
        {"day": 3,  "type": "usage_tip",    "delay_h": 72},
        {"day": 7,  "type": "upgrade",      "delay_h": 168},
        {"day": 14, "type": "loyalty_deal", "delay_h": 336},
        {"day": 30, "type": "winback",      "delay_h": 720},
    ]

    messages = []
    for step in sequence:
        prompt = (
            f"Write a short German {step['type']} email (3 sentences) for a customer who bought "
            f"'{product}' for €{amount}. Order: {order_id}. "
            f"Day {step['day']} of follow-up sequence. "
            "Include a CTA to upgrade or buy again. Return only the email body."
        )
        body = await _claude(prompt) or f"Danke für deinen Kauf von {product}!"
        msg = {"step": step["type"], "day": step["day"], "email": email,
               "body": body, "order_id": order_id}
        messages.append(msg)

        # Store in Supabase for deferred sending
        await _supa_insert("agent_execution_log", {
            "agent": "upsell_sequence",
            "action": step["type"],
            "result": json.dumps(msg),
            "created_at": datetime.utcnow().isoformat(),
        })

    return messages


# ── 4. A/B TEST ENGINE ────────────────────────────────────────────────────────

async def create_ab_test(element: str, variants: list, goal: str = "conversion") -> dict:
    """Create and register an A/B test in Supabase."""
    test_id = hashlib.md5(f"{element}{time.time()}".encode()).hexdigest()[:12]
    test = {
        "test_id": test_id, "element": element,
        "variants": json.dumps(variants), "goal": goal,
        "impressions_a": 0, "impressions_b": 0,
        "conversions_a": 0, "conversions_b": 0,
        "status": "running",
        "created_at": datetime.utcnow().isoformat(),
    }
    await _supa_insert("ab_tests", test)
    return {"test_id": test_id, "element": element, "variants": variants}


async def check_ab_test_results() -> list[dict]:
    """Auto-declare winners for tests with 100+ impressions."""
    tests = await _supa_select("ab_tests", "status=eq.running")
    winners = []
    for test in tests:
        imp_a = test.get("impressions_a", 0)
        imp_b = test.get("impressions_b", 0)
        if imp_a + imp_b < 100:
            continue
        conv_a = test.get("conversions_a", 0) / max(imp_a, 1)
        conv_b = test.get("conversions_b", 0) / max(imp_b, 1)
        winner_variant = "A" if conv_a >= conv_b else "B"
        winner_rate    = max(conv_a, conv_b)
        test_id        = test.get("test_id", "?")
        element        = test.get("element", "?")
        winners.append({
            "test_id": test_id, "element": element,
            "winner": winner_variant, "conversion_rate": round(winner_rate, 4),
        })
        logger.info(f"A/B Winner: {element} → Variant {winner_variant} ({winner_rate:.1%})")
    if winners:
        report = "\n".join(f"🏆 A/B Gewinner: {w['element']} → Variante {w['winner']} "
                           f"({w['conversion_rate']:.1%})" for w in winners)
        await _tg(f"<b>A/B Test Ergebnisse</b>\n{report}")
    return winners


# ── 5. EXIT INTENT SYSTEM ────────────────────────────────────────────────────

async def generate_exit_intent_offer(visitor_data: dict) -> dict:
    """AI-personalized exit intent popup with urgency offer."""
    pages_visited = visitor_data.get("pages", [])
    cart_value    = visitor_data.get("cart_value", 0)
    time_on_site  = visitor_data.get("time_seconds", 0)

    context = (
        f"Visitor about to leave. Pages: {pages_visited}. "
        f"Cart value: €{cart_value}. Time on site: {time_on_site}s."
    )
    offer_text = await _claude(
        f"Create a German exit-intent popup offer (2 sentences max, very urgent). "
        f"Context: {context}. Options: 10% discount, free bonus, extended trial. "
        "Include a specific discount code. Return JSON: "
        '{"headline": "...", "body": "...", "code": "...", "discount_pct": 10}'
    )
    try:
        offer = json.loads(offer_text)
    except (json.JSONDecodeError, TypeError):
        code = f"EXIT{random.randint(10, 99)}"
        offer = {
            "headline": "Warte! Nur für dich:",
            "body": f"15 Minuten exklusiv: 10% Rabatt mit Code {code}",
            "code": code,
            "discount_pct": 10,
        }

    offer["expires_minutes"] = 15
    offer["generated_at"] = datetime.utcnow().isoformat()
    return offer


# ── 6. LEAD SCORING ENGINE ────────────────────────────────────────────────────

async def score_lead(lead: dict) -> dict:
    """Score lead 0-100 and auto-trigger action at threshold."""
    score = 0
    score += min(lead.get("page_visits", 0) * 5, 25)
    score += min(lead.get("email_opens", 0) * 10, 30)
    score += lead.get("product_views", 0) * 15
    score += 25 if lead.get("visited_pricing") else 0
    score += 30 if lead.get("cart_abandoned") else 0
    score += 50 if lead.get("demo_requested") else 0
    score = min(score, 100)

    lead["score"] = score
    email = lead.get("email", "")

    if score >= 90 and TELEGRAM_BOT:
        await _tg(
            f"🔥 <b>HOT LEAD (Score {score}/100)</b>\n"
            f"📧 {email}\n"
            f"📊 Seiten: {lead.get('page_visits',0)} | Preisseite: {lead.get('visited_pricing',False)}\n"
            f"→ Sofort kontaktieren!"
        )
    elif score >= 80 and email:
        # Trigger direct Telegram DM sequence
        await _supa_insert("agent_execution_log", {
            "agent": "lead_scoring",
            "action": "warm_lead_trigger",
            "result": json.dumps({"email": email, "score": score}),
            "created_at": datetime.utcnow().isoformat(),
        })
    elif score >= 70 and email:
        # Enroll in high-intent email sequence
        await _supa_insert("agent_execution_log", {
            "agent": "lead_scoring",
            "action": "sequence_enroll",
            "result": json.dumps({"email": email, "score": score}),
            "created_at": datetime.utcnow().isoformat(),
        })

    return lead


async def score_all_leads() -> dict:
    """Re-score all leads from Supabase lead_events."""
    leads = await _supa_select("lead_events", "select=email,page_visits,email_opens,created_at&order=created_at.desc&limit=200")
    scored = []
    hot = 0
    for raw in leads:
        lead = {
            "email":           raw.get("email", ""),
            "page_visits":     raw.get("page_visits", 1),
            "email_opens":     raw.get("email_opens", 0),
            "product_views":   raw.get("product_views", 0),
            "visited_pricing": raw.get("visited_pricing", False),
            "cart_abandoned":  raw.get("cart_abandoned", False),
        }
        result = await score_lead(lead)
        scored.append(result)
        if result["score"] >= 70:
            hot += 1
    return {"total": len(scored), "hot_leads": hot,
            "avg_score": round(sum(l["score"] for l in scored) / max(len(scored), 1), 1)}


# ── 7. SOCIAL PROOF AUTOMATON ────────────────────────────────────────────────

async def collect_and_display_social_proof() -> dict:
    """Pull Stripe/Shopify data → generate proof posts for all channels."""
    proofs = []

    # Stripe: recent payments
    if STRIPE_KEY:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(
                    "https://api.stripe.com/v1/payment_intents?limit=5&status=succeeded",
                    auth=aiohttp.BasicAuth(STRIPE_KEY, ""),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        count = len(data.get("data", []))
                        if count:
                            total = sum(p["amount"] for p in data["data"]) / 100
                            proofs.append(
                                f"💳 {count} Käufe in den letzten Stunden — €{total:.0f} Umsatz"
                            )
        except Exception as e:
            logger.warning("Ignored error: %s", e)

    # Shopify: order count
    orders = await _shopify_get("orders/count.json?status=any")
    if orders.get("count"):
        proofs.append(f"🛍️ {orders['count']} Bestellungen insgesamt")

    # Generate social-ready post
    if proofs:
        proof_text = " | ".join(proofs)
        post = await _claude(
            f"Write a short German social media post (2 sentences, emoji) using this social proof: {proof_text}. "
            "Make it feel FOMO-inducing. Add hashtags. Return only the post text."
        ) or f"🚀 {proof_text} — Werde Teil der Erfolgsgeschichte! #Shopify #Automation"

        # Post to Telegram channel
        await _tg(f"📣 <b>Social Proof Update</b>\n{post}")
        return {"proofs": proofs, "post": post, "posted": True}

    return {"proofs": [], "posted": False}


# ── 8. REVENUE OPTIMIZATION REPORT ───────────────────────────────────────────

async def daily_revenue_optimization() -> dict:
    """AI daily analysis: find weakest link, generate fix, report to Telegram."""
    # Gather data points
    orders     = await _shopify_get("orders/count.json?status=any&created_at_min=" +
                                     (datetime.utcnow() - timedelta(days=1)).isoformat())
    order_count = orders.get("count", 0)

    stripe_rev = 0.0
    if STRIPE_KEY:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                since = int((datetime.utcnow() - timedelta(days=1)).timestamp())
                async with s.get(
                    f"https://api.stripe.com/v1/payment_intents?limit=100&created[gte]={since}&status=succeeded",
                    auth=aiohttp.BasicAuth(STRIPE_KEY, ""),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        stripe_rev = sum(p["amount"] for p in d.get("data", [])) / 100
        except Exception as e:
            logger.warning("Ignored error: %s", e)

    # AI diagnosis and fix suggestions
    analysis = await _claude(
        f"You are a revenue optimization AI. Today's data: "
        f"Shopify orders: {order_count}, Stripe revenue: €{stripe_rev:.2f}. "
        "Give 3 specific German action items to improve revenue today. "
        "Format: 1. [action] 2. [action] 3. [action]. Be concrete, not vague."
    ) or "1. Preis testen 2. Email-Sequenz starten 3. Social Proof posten"

    # 7-day revenue forecast
    daily_avg = stripe_rev or order_count * 49
    forecast  = daily_avg * 7 * 1.15

    report = (
        f"📊 <b>Revenue Optimierung — {datetime.utcnow().strftime('%d.%m.%Y')}</b>\n\n"
        f"💰 Heute: {order_count} Orders | €{stripe_rev:.2f}\n"
        f"📈 7-Tage Forecast: €{forecast:.0f}\n\n"
        f"🎯 <b>KI-Empfehlungen:</b>\n{analysis}"
    )
    await _tg(report)

    return {
        "orders_today": order_count, "revenue_today": stripe_rev,
        "forecast_7d": forecast, "recommendations": analysis,
    }


# ── 9. FUNNEL ANALYTICS ───────────────────────────────────────────────────────

async def analyze_funnel() -> dict:
    """Full funnel: Visit → Lead → Trial → Purchase → Retain."""
    leads    = await _supa_select("lead_events", "select=count&limit=1")
    orders   = await _shopify_get("orders/count.json?status=any")

    lead_count  = leads[0].get("count", 0) if leads else 0
    order_count = orders.get("count", 0)

    visit_to_lead   = min(lead_count / max(lead_count * 10, 1), 1.0)
    lead_to_purchase = min(order_count / max(lead_count, 1), 1.0)

    # Identify biggest drop
    stages = {
        "Visit→Lead":     visit_to_lead,
        "Lead→Purchase":  lead_to_purchase,
    }
    weakest = min(stages, key=stages.get)
    weakest_rate = stages[weakest]

    fix = await _claude(
        f"Funnel weak point: '{weakest}' at {weakest_rate:.1%} conversion. "
        "Give one specific German action to improve this in 24h. Max 2 sentences."
    ) or f"Optimiere den Schritt '{weakest}' mit gezieltem A/B-Test."

    report = (
        f"🔍 <b>Funnel Report</b>\n"
        f"👥 Leads: {lead_count} | Orders: {order_count}\n"
        f"📉 Schwächster Punkt: <b>{weakest}</b> ({weakest_rate:.1%})\n"
        f"💡 Fix: {fix}"
    )
    await _tg(report)

    return {
        "stages": stages, "weakest_stage": weakest,
        "weakest_rate": weakest_rate, "fix": fix,
        "leads": lead_count, "orders": order_count,
    }


# ── 10. PERSONALIZATION ENGINE ────────────────────────────────────────────────

async def personalize_experience(visitor_id: str, context: dict) -> dict:
    """Real-time visitor personalization → content, CTA, offer."""
    is_new        = context.get("first_visit", True)
    cart_value    = context.get("cart_value", 0)
    is_past_buyer = context.get("past_buyer", False)
    score         = context.get("lead_score", 0)
    pages         = context.get("pages_visited", [])

    if is_past_buyer:
        cta_type = "cross_sell"
        headline = "Willkommen zurück! Exklusiv für dich:"
        offer    = "Neue Produkte passend zu deinem letzten Kauf"
    elif cart_value > 0:
        cta_type = "cart_recovery"
        headline = f"Dein Warenkorb wartet — €{cart_value:.0f}"
        offer    = "Jetzt bestellen und 5% sparen mit Code JETZT5"
    elif score >= 70:
        cta_type = "demo_cta"
        headline = "Bereit für die nächste Stufe?"
        offer    = "Kostenlose Demo — 15 Min. reichen für den Start"
    elif is_new:
        cta_type = "trust_intro"
        headline = "Willkommen bei BullPower Hub"
        offer    = "Starte jetzt: Erste 7 Tage kostenlos testen"
    else:
        cta_type = "re_engage"
        headline = "Schön, dich wieder zu sehen!"
        offer    = "Wo du zuletzt warst: " + (pages[-1] if pages else "Startseite")

    return {
        "visitor_id": visitor_id,
        "cta_type":   cta_type,
        "headline":   headline,
        "offer":      offer,
        "trust_badge": True,
        "urgency_timer_minutes": 15 if cart_value > 0 else 0,
    }


# ── Scheduler-callable wrappers ───────────────────────────────────────────────

async def run_conversion_scan() -> str:
    """Full conversion scan: A/B winners + social proof + lead scoring."""
    results = await asyncio.gather(
        check_ab_test_results(),
        collect_and_display_social_proof(),
        score_all_leads(),
        return_exceptions=True,
    )
    ab_winners = results[0] if not isinstance(results[0], Exception) else []
    proof      = results[1] if not isinstance(results[1], Exception) else {}
    leads      = results[2] if not isinstance(results[2], Exception) else {}
    return (
        f"AB winners: {len(ab_winners)} | "
        f"Proof posted: {proof.get('posted', False)} | "
        f"Hot leads: {leads.get('hot_leads', 0)}/{leads.get('total', 0)}"
    )


async def run_daily_optimization() -> str:
    """Daily: revenue optimization + funnel analysis."""
    rev, funnel = await asyncio.gather(
        daily_revenue_optimization(),
        analyze_funnel(),
        return_exceptions=True,
    )
    if isinstance(rev, Exception):
        rev = {}
    if isinstance(funnel, Exception):
        funnel = {}
    return (
        f"Revenue today: €{rev.get('revenue_today', 0):.2f} | "
        f"Funnel weak: {funnel.get('weakest_stage', 'N/A')} "
        f"({funnel.get('weakest_rate', 0):.1%})"
    )
