#!/usr/bin/env python3
"""
Auto Funnel — Lead → Sale → Upsell → Retention
Vollautomatischer Verkaufstrichter. Jeder neue Lead wird sofort in alle
Mailing-Plattformen eingetragen und mit einer Kaufsequenz versorgt.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("AutoFunnel")

DATA_DIR       = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data" / "brutus"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
KLAVIYO_KEY    = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST   = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
MC_KEY         = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER      = os.getenv("MAILCHIMP_SERVER_PREFIX", "us7")
MC_LIST        = os.getenv("MAILCHIMP_LIST_ID", "606e45a6b0")
SUPA_URL       = os.getenv("SUPABASE_URL", "")
SUPA_KEY       = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SHOPIFY_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VER    = os.getenv("SHOPIFY_API_VERSION", "2024-10")
DS24_KEY       = os.getenv("DIGISTORE24_API_KEY", "")


async def _brutus_fire(message: str, channels: list = None):
    try:
        from modules.brutus_core import BrutusCore
        b = BrutusCore()
        await b.fire(message, channels=channels or ["telegram", "slack", "mailchimp", "klaviyo"])
    except Exception as _be:
        log.debug("Brutus fire skip: %s", _be)


async def _slack_notify(message: str, level: str = "info"):
    try:
        from modules.slack_notify import send_slack
        await send_slack(message, level=level)
    except Exception as _se:
        log.debug("Slack notify skip: %s", _se)


# ─────────────────────────────────────────────────────────────────────────────

async def _tg(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def _klaviyo_add_profile(email: str, first_name: str = "", properties: dict = None):
    if not KLAVIYO_KEY:
        return None
    import aiohttp
    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
        "revision": "2024-10-15",
        "Content-Type": "application/json",
    }
    profile_payload = {
        "data": {
            "type": "profile",
            "attributes": {
                "email": email,
                "first_name": first_name,
                **(properties or {}),
            }
        }
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://a.klaviyo.com/api/profiles/",
            headers=headers,
            json=profile_payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json(content_type=None)
    profile_id = data.get("data", {}).get("id", "")
    if not profile_id:
        # Profile may already exist — try to get by email
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://a.klaviyo.com/api/profiles/?filter=equals(email,\"{email}\")",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data2 = await r.json(content_type=None)
        items = data2.get("data", [])
        profile_id = items[0]["id"] if items else ""

    # Add to list
    if profile_id and KLAVIYO_LIST:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST}/relationships/profiles/",
                headers=headers,
                json={"data": [{"type": "profile", "id": profile_id}]},
                timeout=aiohttp.ClientTimeout(total=15),
            )
    return profile_id


async def _mailchimp_subscribe(email: str, tags: list = None):
    if not MC_KEY:
        return
    import aiohttp, base64
    auth = base64.b64encode(f"any:{MC_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    url = f"https://{MC_SERVER}.api.mailchimp.com/3.0/lists/{MC_LIST}/members"
    payload = {
        "email_address": email,
        "status": "subscribed",
        "tags": tags or [],
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(url, headers=headers, json=payload,
                          timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status not in (200, 201):
                body = await r.json(content_type=None)
                if body.get("title") == "Member Exists":
                    return  # already subscribed, fine
                log.warning("Mailchimp subscribe error: %s %s", r.status, body.get("detail",""))


async def _supabase_insert(table: str, row: dict):
    if not SUPA_URL or not SUPA_KEY:
        return
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{SUPA_URL}/rest/v1/{table}",
            headers={
                "Authorization": f"Bearer {SUPA_KEY}",
                "apikey": SUPA_KEY,
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=row,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status not in (200, 201):
                log.warning("Supabase insert error: %s %s", r.status, table)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

async def process_new_lead(email: str, source: str, product_hint: str = "") -> dict:
    """
    New lead enters the funnel:
    1. Klaviyo profile + list add
    2. Mailchimp subscribe
    3. Supabase log
    4. Telegram alert
    """
    if not email or "@" not in email:
        return {"ok": False, "error": "invalid email"}

    results = {}

    # Klaviyo
    try:
        pid = await _klaviyo_add_profile(email, properties={"source": source, "product_hint": product_hint})
        results["klaviyo_id"] = pid
    except Exception as e:
        log.warning("Lead Klaviyo error: %s", e)
        results["klaviyo_error"] = str(e)

    # Mailchimp
    try:
        await _mailchimp_subscribe(email, tags=[source, "auto-funnel"])
        results["mailchimp"] = "ok"
    except Exception as e:
        log.warning("Lead Mailchimp error: %s", e)
        results["mailchimp_error"] = str(e)

    # Supabase
    try:
        await _supabase_insert("lead_events", {
            "email": email,
            "source": source,
            "product_hint": product_hint,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        results["supabase"] = "ok"
    except Exception as e:
        log.warning("Lead Supabase error: %s", e)

    # Telegram
    await _tg(f"🎯 <b>Neuer Lead!</b>\n{email}\nQuelle: {source}" + (f"\nProdukt: {product_hint}" if product_hint else ""))
    log.info("New lead processed: %s via %s", email, source)
    return {"ok": True, **results}


async def trigger_purchase_sequence(email: str, product: str, amount_eur: float) -> dict:
    """
    Buyer entered — log the purchase, send Telegram alert, track Klaviyo event.
    """
    import aiohttp
    results = {}

    # Klaviyo event
    if KLAVIYO_KEY:
        try:
            headers = {
                "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
                "revision": "2024-10-15",
                "Content-Type": "application/json",
            }
            event_payload = {
                "data": {
                    "type": "event",
                    "attributes": {
                        "profile": {"$email": email},
                        "metric": {"name": "Purchase"},
                        "properties": {
                            "product": product,
                            "amount_eur": amount_eur,
                            "currency": "EUR",
                        },
                        "value": amount_eur,
                        "time": datetime.now(timezone.utc).isoformat(),
                    }
                }
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://a.klaviyo.com/api/events/",
                    headers=headers,
                    json=event_payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    results["klaviyo_event"] = r.status
        except Exception as e:
            log.warning("Purchase Klaviyo event error: %s", e)

    # Supabase
    try:
        await _supabase_insert("client_activity_log", {
            "email": email,
            "event_type": "purchase",
            "product": product,
            "amount_eur": amount_eur,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        results["supabase"] = "ok"
    except Exception as e:
        log.warning("Purchase Supabase error: %s", e)

    # Telegram
    await _tg(
        f"💰 <b>KAUF!</b>\n{email}\n{product}\n<b>€{amount_eur:.2f}</b>"
    )
    log.info("Purchase sequence triggered: %s — %s €%.2f", email, product, amount_eur)
    return {"ok": True, **results}


async def run_daily_funnel_tasks() -> dict:
    """Fetch last 7 days DS24 orders → trigger purchase sequence for new ones."""
    if not DS24_KEY:
        return {"error": "DS24_KEY not set"}

    import aiohttp
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    results = {"processed": 0, "errors": 0}

    # Load already-processed orders
    state_file = DATA_DIR / "funnel_processed_orders.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        seen: set = set(json.loads(state_file.read_text())) if state_file.exists() else set()
    except Exception:
        seen = set()

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.digistore24.com/api/call/seller/listOrders",
                headers={"X-DS-API-KEY": DS24_KEY},
                params={
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d"),
                    "page": 1,
                    "items_per_page": 50,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
    except Exception as e:
        log.warning("DS24 funnel fetch error: %s", e)
        return {"error": str(e)}

    orders = []
    d = data if isinstance(data, dict) else {}
    for key in ("data", "orders", "result"):
        if isinstance(d.get(key), list):
            orders = d[key]
            break
    if not orders and isinstance(data, list):
        orders = data

    new_ids = []
    for order in orders:
        order_id = str(order.get("order_id") or order.get("id", ""))
        if not order_id or order_id in seen:
            continue
        buyer = order.get("buyer") or {}
        email = buyer.get("email") or order.get("buyer_email", "")
        product = order.get("product_name") or order.get("product", "DS24 Produkt")
        amount = float(order.get("amount") or order.get("transaction_amount", 0) or 0)
        if email:
            try:
                await trigger_purchase_sequence(email, product, amount)
                results["processed"] += 1
            except Exception as e:
                log.warning("Funnel sequence error for %s: %s", email, e)
                results["errors"] += 1
        new_ids.append(order_id)
        seen.add(order_id)

    state_file.write_text(json.dumps(list(seen)))

    if results["processed"]:
        await _tg(
            f"🔄 <b>Auto Funnel Daily</b>\n"
            f"{results['processed']} neue Käufer verarbeitet\n"
            f"Gesamt bekannt: {len(seen)}"
        )
    log.info("Daily funnel: %d new, %d errors", results["processed"], results["errors"])
    return results


async def create_shopify_discount_for_leads() -> str:
    """Create WELCOME15 discount code (15% off, once per customer, 30 days)."""
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return "Shopify not configured"

    import aiohttp
    base    = f"https://{SHOPIFY_DOMAIN}" if not SHOPIFY_DOMAIN.startswith("http") else SHOPIFY_DOMAIN
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

    # Pre-check: test if write_price_rules scope is available
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{base}/admin/api/{SHOPIFY_VER}/price_rules.json?limit=1",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 403:
                    log.debug("Shopify write_price_rules scope not granted — discount creation skipped")
                    return "skip: write_price_rules scope not granted"
    except Exception:
        pass

    expires = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with aiohttp.ClientSession() as s:
            # Create price rule
            async with s.post(
                f"{base}/admin/api/{SHOPIFY_VER}/price_rules.json",
                headers=headers,
                json={"price_rule": {
                    "title": "WELCOME15",
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": "percentage",
                    "value": "-15.0",
                    "customer_selection": "all",
                    "once_per_customer": True,
                    "usage_limit": 500,
                    "starts_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ends_at": expires,
                }},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                rule_data = await r.json(content_type=None)

            rule_id = rule_data.get("price_rule", {}).get("id")
            if not rule_id:
                errors = rule_data.get("errors", {})
                if "permission" in str(errors).lower() or rule_data.get("status") == 403:
                    log.debug("Shopify price_rules: write_price_rules scope missing — skip")
                    return "skip: write_price_rules scope not granted"
                return f"Price rule creation failed: {rule_data}"

            # Create discount code
            async with s.post(
                f"{base}/admin/api/{SHOPIFY_VER}/price_rules/{rule_id}/discount_codes.json",
                headers=headers,
                json={"discount_code": {"code": "WELCOME15"}},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                code_data = await r.json(content_type=None)

        code = code_data.get("discount_code", {}).get("code", "WELCOME15")
        shop_url = f"https://{SHOPIFY_DOMAIN}"
        discount_url = f"{shop_url}/discount/{code}"
        await _tg(f"🎁 Willkommens-Rabatt erstellt: <b>{code}</b> (15% Rabatt)\n{discount_url}")
        log.info("Shopify discount created: %s", code)
        return discount_url
    except Exception as e:
        log.warning("Shopify discount error: %s", e)
        return f"Error: {e}"


async def run_auto_funnel() -> dict:
    """Master function — runs all funnel tasks."""
    log.info("AutoFunnel run started")
    results = {}

    try:
        daily = await run_daily_funnel_tasks()
        results["daily_funnel"] = daily
    except Exception as e:
        results["daily_funnel_error"] = str(e)

    # Create welcome discount if it doesn't exist yet
    discount_file = DATA_DIR / "welcome_discount.json"
    if not discount_file.exists():
        try:
            url = await create_shopify_discount_for_leads()
            discount_file.write_text(json.dumps({"url": url, "created_at": datetime.now().isoformat()}))
            if url.startswith("skip:"):
                results["discount_skipped"] = url
            else:
                results["discount_created"] = url
        except Exception as e:
            log.debug("Discount creation skipped: %s", e)
            results["discount_skipped"] = str(e)

    log.info("AutoFunnel run complete: %s", results)
    await _brutus_fire("🎯 Auto-Funnel: Lead → Sale Pipeline aktiv! Neue Leads werden automatisch konvertiert.")
    await _slack_notify("AutoFunnel run complete: " + str({k: v for k, v in results.items() if "error" not in str(k)})[:300], level="info")
    return results
