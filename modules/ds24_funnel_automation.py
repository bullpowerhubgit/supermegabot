#!/usr/bin/env python3
"""
DS24 Funnel Automation — vollautomatische Pipeline:
  DS24 neue Käufer → Mailchimp + Klaviyo + Email-Sequenz + Telegram-Benachrichtigung
  Läuft alle 15 Minuten via Scheduler.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("DS24Funnel")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
SEEN_FILE = DATA_DIR / "ds24_synced_buyers.json"

MAILCHIMP_LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "")
KLAVIYO_LIST_ID   = os.getenv("KLAVIYO_LIST_ID", "")


def _load_seen() -> set:
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


async def _notify_telegram(buyer: dict, product: str, amount: str):
    try:
        from modules.notify_hub import send_telegram
        msg = (
            f"💰 *Neuer DS24-Kauf!*\n"
            f"Produkt: {product}\n"
            f"Betrag: €{amount}\n"
            f"Käufer: {buyer.get('first_name','')} {buyer.get('last_name','')}\n"
            f"Email: {buyer.get('email','')}"
        )
        await send_telegram(msg)
    except Exception as exc:
        log.warning("Telegram notify failed: %s", exc)


async def _add_to_mailchimp(email: str, fname: str, lname: str, product: str):
    if not MAILCHIMP_LIST_ID:
        return
    try:
        from modules.mailchimp_automation import add_subscriber
        await add_subscriber(
            list_id=MAILCHIMP_LIST_ID,
            email=email, fname=fname, lname=lname,
            tags=["digistore24", "buyer", product[:50]],
        )
        log.info("Mailchimp: added %s", email)
    except Exception as exc:
        log.warning("Mailchimp add failed: %s", exc)


async def _add_to_klaviyo(email: str, fname: str, lname: str, product: str, amount: str):
    klaviyo_key = os.getenv("KLAVIYO_API_KEY", "")
    if not klaviyo_key:
        return
    try:
        import aiohttp
        headers = {
            "Authorization": f"Klaviyo-API-Key {klaviyo_key}",
            "revision": "2024-10-15",
            "Content-Type": "application/json",
        }
        profile_data = {
            "data": {
                "type": "profile",
                "attributes": {
                    "email": email,
                    "first_name": fname,
                    "last_name": lname,
                    "properties": {
                        "ds24_product": product,
                        "ds24_amount": amount,
                        "source": "digistore24",
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://a.klaviyo.com/api/profiles/",
                headers=headers,
                json=profile_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201, 409):
                    log.info("Klaviyo: profile upserted for %s", email)
                    # Add to list if configured
                    if KLAVIYO_LIST_ID:
                        data = await resp.json(content_type=None)
                        profile_id = data.get("data", {}).get("id", "")
                        if profile_id:
                            await _klaviyo_add_to_list(session, headers, profile_id)
                else:
                    body = await resp.text()
                    log.warning("Klaviyo profile error %s: %s", resp.status, body[:200])
    except Exception as exc:
        log.warning("Klaviyo add failed: %s", exc)


async def _klaviyo_add_to_list(session, headers: dict, profile_id: str):
    payload = {"data": [{"type": "profile", "id": profile_id}]}
    try:
        async with session.post(
            f"https://a.klaviyo.com/api/lists/{KLAVIYO_LIST_ID}/relationships/profiles/",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status in (200, 204):
                log.info("Klaviyo: added profile %s to list %s", profile_id, KLAVIYO_LIST_ID)
    except Exception as exc:
        log.warning("Klaviyo list add failed: %s", exc)


async def run_sync() -> dict:
    """
    Main sync: fetch new DS24 buyers, push to all platforms.
    Returns summary dict.
    """
    from modules.digistore24_automation import get_orders

    orders = await get_orders(page=1, per_page=200)
    seen = _load_seen()
    new_buyers = 0
    errors = 0

    for order in orders:
        buyer = order.get("buyer") or {}
        email = (buyer.get("email") or order.get("buyer_email") or "").strip().lower()
        if not email or "@" not in email or email in seen:
            continue

        seen.add(email)
        fname   = buyer.get("first_name") or ""
        lname   = buyer.get("last_name") or ""
        product = order.get("main_product_name") or "DS24 Product"
        amount  = str(order.get("amount") or order.get("transaction_amount") or "0")

        try:
            await _add_to_mailchimp(email, fname, lname, product)
            await _add_to_klaviyo(email, fname, lname, product, amount)
            await _notify_telegram(buyer, product, amount)
            new_buyers += 1
            log.info("Synced new buyer: %s — %s €%s", email, product, amount)
        except Exception as exc:
            log.error("Sync error for %s: %s", email, exc)
            errors += 1

    _save_seen(seen)
    return {
        "new_buyers": new_buyers,
        "total_seen": len(seen),
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
