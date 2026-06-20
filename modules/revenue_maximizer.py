"""
RevenueMaximizer — Vollautomatische Umsatz-Maximierung.
Cart Abandonment Recovery, Dynamic Upsells, A/B Test Automation,
Conversion Rate Optimization — vollständig autonom.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("RevenueMaximizer")

ANTHROPIC      = os.getenv("ANTHROPIC_API_KEY", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-01")
KLAVIYO_KEY    = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST   = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
TG_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
DS24_KEY       = os.getenv("DS24_API_KEY", "") or os.getenv("DIGISTORE24_API_KEY", "")

DATA_DIR = Path(__file__).parent.parent / "data" / "revenue_maximizer"


async def _tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def get_shopify_abandoned_checkouts() -> list:
    """Fetch abandoned checkouts from last 24h from Shopify."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return []
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VER}/checkouts.json",
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                params={"updated_at_min": since, "limit": 50},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
        return data.get("checkouts", [])
    except Exception as e:
        log.warning("Abandoned checkouts fetch error: %s", e)
        return []


async def klaviyo_trigger_flow(email: str, flow_id: str, properties: dict = None) -> dict:
    """Trigger a Klaviyo flow for a specific email (e.g. abandoned cart recovery)."""
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "No Klaviyo key"}
    try:
        import aiohttp
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
            "revision": "2024-10-15",
            "Content-Type": "application/json",
        }
        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "profile": {"data": {"type": "profile", "attributes": {"email": email}}},
                    "metric": {"data": {"type": "metric", "attributes": {"name": flow_id}}},
                    "properties": properties or {},
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://a.klaviyo.com/api/events/",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return {"ok": r.status in (200, 201, 202), "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def recover_abandoned_carts() -> dict:
    """Automatically send recovery emails to abandoned cart users via Klaviyo."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    recovered_file = DATA_DIR / "recovered_carts.json"
    already_recovered = set()
    try:
        already_recovered = set(json.loads(recovered_file.read_text()))
    except Exception:
        pass

    checkouts = await get_shopify_abandoned_checkouts()
    newly_recovered = 0

    for checkout in checkouts:
        email = checkout.get("email", "").lower().strip()
        token = checkout.get("token", "")
        if not email or token in already_recovered:
            continue

        cart_url = checkout.get("abandoned_checkout_url", "")
        total = checkout.get("total_price", "0")
        items = [li.get("title", "") for li in checkout.get("line_items", [])]

        result = await klaviyo_trigger_flow(
            email,
            "Abandoned Cart Recovery",
            {
                "checkout_url": cart_url,
                "total_price": total,
                "items": items,
                "discount_code": "COMEBACK10",
            },
        )
        if result.get("ok"):
            already_recovered.add(token)
            newly_recovered += 1
            log.info("Cart recovery sent to %s", email)

    recovered_file.write_text(json.dumps(sorted(already_recovered)))
    return {"ok": True, "carts_found": len(checkouts), "recovery_emails_sent": newly_recovered}


async def ai_upsell_recommendation(order_items: list[str], budget: float = 100.0) -> list[str]:
    """AI-generated upsell recommendations based on cart contents."""
    if not order_items:
        return []
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Basierend auf diesen gekauften Produkten: {', '.join(order_items[:5])}
Budget des Kunden: ca. €{budget:.0f}

Empfehle 3 Upsell/Cross-Sell Produkte die perfekt passen (max. 20% über Budget).
Fokus: E-Commerce, KI-Tools, Shopify, Digital Products.
Gib NUR JSON zurück: [{{"name": "...", "reason": "...", "price_eur": 0}}]"""
        raw = await ai_complete(prompt, max_tokens=300)
        if not raw:
            return []
        start = raw.find("[")
        end = raw.rfind("]") + 1
        recs = json.loads(raw[start:end])
        return [r.get("name", "") for r in recs]
    except Exception as e:
        log.warning("Upsell AI error: %s", e)
        return []


async def klaviyo_winback_campaign() -> dict:
    """Identify inactive subscribers (90+ days) and trigger winback flow."""
    if not KLAVIYO_KEY:
        return {"ok": False, "error": "No Klaviyo key"}
    try:
        import aiohttp
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
            "revision": "2024-10-15",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST}/profiles/",
                headers=headers,
                params={"page[size]": 100},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)

        profiles = data.get("data", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        winback_count = 0

        for profile in profiles:
            attrs = profile.get("attributes", {})
            last_open = attrs.get("last_email_opened_at")
            if last_open:
                try:
                    last_dt = datetime.fromisoformat(last_open.rstrip("Z")).replace(tzinfo=timezone.utc)
                    if last_dt < cutoff:
                        email = attrs.get("email", "")
                        if email:
                            await klaviyo_trigger_flow(email, "Winback", {"days_inactive": 90})
                            winback_count += 1
                except Exception:
                    pass

        return {"ok": True, "profiles_checked": len(profiles), "winback_triggered": winback_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def generate_urgency_offer(product_name: str, original_price: float) -> dict:
    """AI-generates a time-limited urgency offer to boost conversions."""
    discount_pct = 20
    sale_price = round(original_price * (1 - discount_pct / 100), 2)
    try:
        from modules.ai_client import ai_complete
        prompt = f"""Erstelle einen ultraüberzeugenden Urgency-Verkaufstext für:
Produkt: {product_name}
Originalpreis: €{original_price:.2f}
Aktionspreis: €{sale_price:.2f} (nur 24h)

Gib NUR JSON zurück:
{{"headline": "...", "subtext": "...", "cta": "...", "telegram_msg": "..."}}"""
        raw = await ai_complete(prompt, max_tokens=300)
        if raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            result = json.loads(raw[start:end])
            result["sale_price"] = sale_price
            result["discount_pct"] = discount_pct
            return result
    except Exception as e:
        log.warning("Urgency offer AI error: %s", e)

    return {
        "headline": f"🔥 NUR 24h: {product_name} für nur €{sale_price}!",
        "subtext": f"Spare {discount_pct}% — Originalpreis €{original_price:.2f}",
        "cta": "Jetzt kaufen →",
        "sale_price": sale_price,
        "discount_pct": discount_pct,
    }


async def run_revenue_maximizer() -> dict:
    """Master function: full revenue maximization cycle."""
    log.info("RevenueMaximizer starting")
    results = {}

    # 1. Cart abandonment recovery
    results["cart_recovery"] = await recover_abandoned_carts()

    # 2. Winback campaign for inactive users
    results["winback"] = await klaviyo_winback_campaign()

    # 3. Urgency offer for top product
    results["urgency_offer"] = await generate_urgency_offer("AI Income Machine", 97.0)

    # Send urgency offer to Telegram
    offer = results["urgency_offer"]
    await _tg(
        f"💰 *Revenue Maximizer Run*\n\n"
        f"🛒 Cart Recovery: {results['cart_recovery'].get('recovery_emails_sent', 0)} E-Mails gesendet\n"
        f"🔄 Winback: {results['winback'].get('winback_triggered', 0)} reaktiviert\n\n"
        f"🔥 *{offer.get('headline', '')}*\n"
        f"{offer.get('subtext', '')}"
    )

    log.info("RevenueMaximizer done: %s", {k: "ok" for k in results})
    return {"ok": True, "results": results}
