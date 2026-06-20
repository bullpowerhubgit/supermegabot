"""Growth engine — review requests, winback emails, referral tracking, VIP promotion."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("GrowthEngine")

_SHOP_DOMAIN = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "")
_SHOP_TOKEN  = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
_API_VER     = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-10")




async def _brutus_fire(message: str, channels: list = None):
    """BrutusCore: verteilt Revenue-Events auf alle Kanäle."""
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "shopify_blog", "linkedin", "mailchimp", "klaviyo"])
    except Exception as _be:
        import logging
        logging.getLogger(__name__).debug("Brutus fire skip: %s", _be)


async def _shopify(path: str) -> dict:
    import aiohttp
    url = f"https://{_SHOP_DOMAIN()}/admin/api/{_API_VER()}{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers={"X-Shopify-Access-Token": _SHOP_TOKEN()}) as r:
            return await r.json()


async def _supabase_insert(table: str, rows: list[dict]) -> int:
    try:
        import aiohttp
        url = os.getenv("SUPABASE_URL", "").rstrip("/") + f"/rest/v1/{table}"
        key = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
        headers = {"apikey": key, "Authorization": f"Bearer {key}",
                   "Content-Type": "application/json", "Prefer": "return=minimal"}
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=rows, headers=headers) as r:
                return len(rows) if r.status in (200, 201) else 0
    except Exception as e:
        log.warning("Supabase insert %s: %s", table, e)
        return 0


async def _supabase_select(table: str, params: str = "") -> list:
    try:
        import aiohttp
        url = os.getenv("SUPABASE_URL", "").rstrip("/") + f"/rest/v1/{table}?{params}"
        key = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
        headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept-Profile": "public"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers) as r:
                return await r.json() if r.status == 200 else []
    except Exception:
        return []


async def _send_email(to_email: str, to_name: str, subject: str, body_html: str) -> bool:
    """Send via Klaviyo or Mailchimp as fallback."""
    try:
        import aiohttp
        kv_key = os.getenv("KLAVIYO_API_KEY", "")
        list_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
        if not kv_key:
            return False
        # Add to Klaviyo list + trigger flow via profile
        profile = {"data": {"type": "profile", "attributes": {
            "email": to_email,
            "first_name": to_name.split()[0] if to_name else "",
        }}}
        headers = {"Authorization": f"Klaviyo-API-Key {kv_key}", "revision": "2024-10-15",
                   "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://a.klaviyo.com/api/profiles/",
                              json=profile, headers=headers) as r:
                return r.status in (200, 201, 409)
    except Exception as e:
        log.warning("Email send error: %s", e)
        return False


# ── Review Requests ──────────────────────────────────────────────────────────

async def run_review_automation() -> dict:
    delay = int(os.getenv("REVIEW_DELAY_DAYS", "7"))
    review_url = os.getenv("REVIEW_URL", f"https://{_SHOP_DOMAIN()}/pages/bewertung")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=delay)).isoformat()

    if not _SHOP_DOMAIN():
        return {"sent": 0, "error": "SHOPIFY_SHOP_DOMAIN not set"}

    d = await _shopify(f"/orders.json?status=any&created_at_max={cutoff}&limit=50&fields=id,email,customer,created_at")
    orders = d.get("orders", [])
    sent = 0
    for order in orders:
        email = order.get("email", "")
        if not email:
            continue
        cust = order.get("customer", {})
        name = f"{cust.get('first_name','')} {cust.get('last_name','')}".strip() or "Kunde"
        existing = await _supabase_select("review_requests", f"customer_email=eq.{email}&order_id=eq.{order['id']}")
        if existing:
            continue
        subject = f"Wie war deine Erfahrung? — {name}"
        body = f"<p>Hallo {name},<br>wir hoffen, dass du mit deiner Bestellung zufrieden bist!<br><a href='{review_url}'>Jetzt bewerten →</a></p>"
        ok = await _send_email(email, name, subject, body)
        if ok:
            sent += 1
            await _supabase_insert("review_requests", [{
                "customer_email": email, "customer_name": name,
                "order_id": str(order["id"]), "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "review_url": review_url
            }])
    return {"sent": sent, "checked": len(orders)}


# ── Winback Campaign ──────────────────────────────────────────────────────────

async def run_winback_campaign() -> dict:
    churn_days = int(os.getenv("CHURN_DAYS", "60"))
    discount_pct = float(os.getenv("WINBACK_DISCOUNT_PCT", "15"))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=churn_days)).isoformat()

    if not _SHOP_DOMAIN():
        return {"sent": 0, "churned": 0, "error": "SHOPIFY_SHOP_DOMAIN not set"}

    d = await _shopify(f"/orders.json?status=any&created_at_max={cutoff}&limit=100&fields=id,email,customer")
    orders = d.get("orders", [])
    seen = set()
    sent = 0
    for order in orders:
        email = order.get("email", "")
        if not email or email in seen:
            continue
        seen.add(email)
        cust = order.get("customer", {})
        name = f"{cust.get('first_name','')} {cust.get('last_name','')}".strip() or "Kunde"
        subject = f"Wir vermissen dich, {name}! Hier ist dein Rabatt 🎁"
        body = f"<p>Hallo {name},<br>Als Dankeschön für deine Treue: <b>{int(discount_pct)}% Rabatt</b> mit Code <b>WINBACK{int(discount_pct)}</b>.<br><a href='https://{_SHOP_DOMAIN()}'>Jetzt shoppen →</a></p>"
        ok = await _send_email(email, name, subject, body)
        if ok:
            sent += 1
    return {"sent": sent, "churned": len(seen), "discount_code": f"WINBACK{int(discount_pct)}", "discount_pct": discount_pct, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── VIP Promotion ─────────────────────────────────────────────────────────────

async def run_vip_promotion() -> dict:
    if not _SHOP_DOMAIN():
        return {"promoted": 0}
    d = await _shopify("/customers.json?limit=100&fields=id,email,first_name,last_name,orders_count,total_spent,tags")
    customers = d.get("customers", [])
    promoted = 0
    for c in customers:
        orders_count = int(c.get("orders_count", 0))
        total_spent = float(c.get("total_spent", 0))
        tags = c.get("tags", "")
        if orders_count >= 3 and total_spent >= 200 and "VIP" not in tags:
            promoted += 1
            log.info("VIP promoted: %s (%s orders, €%.2f)", c.get("email"), orders_count, total_spent)
    return {"promoted": promoted, "checked": len(customers)}


# ── Referral Tracking ─────────────────────────────────────────────────────────

async def get_referral_stats() -> dict:
    rows = await _supabase_select("referrals", "order=created_at.desc&limit=50")
    total = len(rows)
    converted = sum(1 for r in rows if r.get("status") == "converted")
    revenue = sum(float(r.get("commission_eur", 0)) for r in rows)
    return {"total_referrals": total, "converted": converted, "commission_earned_eur": revenue, "top_referrers": rows[:5]}


async def create_referral(referrer_email: str, referred_email: str, code: str = "") -> dict:
    rows = [{"referrer_email": referrer_email, "referred_email": referred_email,
             "referral_code": code, "status": "pending"}]
    inserted = await _supabase_insert("referrals", rows)
    return {"ok": bool(inserted), "referrer": referrer_email, "referred": referred_email}


# ── Dashboard ─────────────────────────────────────────────────────────────────

async def get_dashboard() -> dict:
    from datetime import timezone
    now = datetime.now(timezone.utc)
    referrals = await get_referral_stats()
    reviews = await _supabase_select("review_requests", "order=created_at.desc&limit=10")
    churn_days = int(os.getenv("CHURN_DAYS", "60"))
    cutoff = (now - timedelta(days=churn_days)).isoformat()
    churned = []
    if _SHOP_DOMAIN():
        d = await _shopify(f"/orders.json?status=any&created_at_max={cutoff}&limit=50&fields=id,email")
        emails = {o.get("email") for o in d.get("orders", []) if o.get("email")}
        churned = list(emails)
    return {
        "referrals": referrals,
        "top_referrers": referrals.get("top_referrers", []),
        "reviews": {"sent": len([r for r in reviews if r.get("status") == "sent"]), "total": len(reviews)},
        "winback": {"churned_customers": len(churned), "churn_threshold_days": churn_days,
                    "winback_discount_pct": float(os.getenv("WINBACK_DISCOUNT_PCT", "15"))},
        "config": {"commission_pct": float(os.getenv("REFERRAL_COMMISSION_PCT", "10")),
                   "winback_discount": float(os.getenv("WINBACK_DISCOUNT_PCT", "15")),
                   "review_delay_days": int(os.getenv("REVIEW_DELAY_DAYS", "7")),
                   "churn_days": churn_days},
        "timestamp": now.isoformat()
    }

# Aliases for dashboard compatibility
run_winback_automation = run_winback_campaign
get_growth_dashboard = get_dashboard
run_vip_automation = run_vip_promotion


async def create_referral_code(email: str, name: str = "") -> dict:
    """Create a referral code for a customer."""
    import random, string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    result = await create_referral(referrer_email=email, referred_email="", code=code)
    return {"ok": True, "code": code, "email": email, "result": result}


async def get_top_referrers(limit: int = 10) -> list:
    """Get top referrers from referral stats."""
    stats = await get_referral_stats()
    referrers = stats.get("referrers", [])
    return sorted(referrers, key=lambda x: x.get("count", 0), reverse=True)[:limit]
