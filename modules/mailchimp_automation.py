#!/usr/bin/env python3
"""Mailchimp automation — audiences, campaigns, subscriber sync"""
import os
import logging
from base64 import b64encode

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("Mailchimp")

MC_API_KEY       = os.getenv("MAILCHIMP_API_KEY", "")
MC_SERVER_PREFIX = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")
MC_BASE          = f"https://{MC_SERVER_PREFIX}.api.mailchimp.com/3.0"


def _auth_header():
    token = b64encode(f"any:{MC_API_KEY}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


async def ping():
    """Test Mailchimp connection. Returns (True, account_name) or (False, error)."""
    if not MC_API_KEY:
        return False, "MAILCHIMP_API_KEY not configured"
    if not HAS_AIOHTTP:
        return False, "aiohttp not installed"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MC_BASE}/ping",
                headers=_auth_header(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json(content_type=None)
        if resp.status == 200:
            # Also fetch account name
            account_name = data.get("health_status", "OK")
            try:
                async with aiohttp.ClientSession() as session2:
                    async with session2.get(
                        MC_BASE,
                        headers=_auth_header(),
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp2:
                        root = await resp2.json(content_type=None)
                account_name = root.get("account_name", account_name)
            except Exception:
                pass
            return True, account_name
        return False, data.get("detail", "Auth failed")
    except Exception as exc:
        log.error("Mailchimp ping error: %s", exc)
        return False, str(exc)


async def get_lists():
    """Return list of Mailchimp audiences."""
    if not MC_API_KEY or not HAS_AIOHTTP:
        return []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MC_BASE}/lists",
                headers=_auth_header(),
                params={"count": 100, "fields": "lists.id,lists.name,lists.stats"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
        return data.get("lists", [])
    except Exception as exc:
        log.error("Mailchimp get_lists error: %s", exc)
        return []


async def get_list_stats(list_id: str):
    """Return stats for a specific list/audience."""
    if not MC_API_KEY or not HAS_AIOHTTP:
        return {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MC_BASE}/lists/{list_id}",
                headers=_auth_header(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
        return data.get("stats", {})
    except Exception as exc:
        log.error("Mailchimp get_list_stats error: %s", exc)
        return {}


async def get_campaigns(count: int = 10):
    """Return recent campaigns."""
    if not MC_API_KEY or not HAS_AIOHTTP:
        return []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MC_BASE}/campaigns",
                headers=_auth_header(),
                params={"count": count, "sort_field": "create_time", "sort_dir": "DESC"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
        return data.get("campaigns", [])
    except Exception as exc:
        log.error("Mailchimp get_campaigns error: %s", exc)
        return []


async def add_subscriber(list_id: str, email: str, fname: str = "", lname: str = "", tags=None):
    """Add or update a subscriber in a Mailchimp list."""
    if not MC_API_KEY or not HAS_AIOHTTP:
        log.warning("Mailchimp not configured — skipping add_subscriber")
        return {"status": "skipped"}

    import hashlib
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()
    payload = {
        "email_address": email,
        "status_if_new": "subscribed",
        "status": "subscribed",
        "merge_fields": {},
    }
    if fname:
        payload["merge_fields"]["FNAME"] = fname
    if lname:
        payload["merge_fields"]["LNAME"] = lname
    if tags:
        payload["tags"] = [{"name": t, "status": "active"} for t in tags]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{MC_BASE}/lists/{list_id}/members/{email_hash}",
                headers=_auth_header(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
        return data
    except Exception as exc:
        log.error("Mailchimp add_subscriber error: %s", exc)
        return {"error": str(exc)}


async def create_campaign(list_id: str, subject: str, from_name: str, body_html: str):
    """Create a regular campaign with HTML content and mark it ready to send."""
    if not MC_API_KEY or not HAS_AIOHTTP:
        log.warning("Mailchimp not configured — cannot create campaign")
        return {"error": "Mailchimp not configured"}

    # Step 1: Create the campaign object
    campaign_payload = {
        "type": "regular",
        "recipients": {"list_id": list_id},
        "settings": {
            "subject_line": subject,
            "from_name": from_name,
            "reply_to": MC_API_KEY.split("-")[0] + "@mailchimp.com",
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MC_BASE}/campaigns",
                headers=_auth_header(),
                json=campaign_payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                campaign = await resp.json(content_type=None)

        if "id" not in campaign:
            return {"error": campaign.get("detail", "Failed to create campaign"), "raw": campaign}

        campaign_id = campaign["id"]

        # Step 2: Set the HTML content
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{MC_BASE}/campaigns/{campaign_id}/content",
                headers=_auth_header(),
                json={"html": body_html},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                content_result = await resp.json(content_type=None)

        campaign["content_set"] = resp.status == 200
        return campaign

    except Exception as exc:
        log.error("Mailchimp create_campaign error: %s", exc)
        return {"error": str(exc)}


async def sync_from_digistore(list_id: str) -> int:
    """Fetch DS24 orders and add buyer emails to Mailchimp list. Returns count of synced subscribers."""
    try:
        from modules.digistore24_automation import get_orders
    except ImportError:
        log.error("digistore24_automation module not found")
        return 0

    orders = await get_orders(page=1, per_page=200)
    synced = 0
    seen = set()

    for order in orders:
        email = order.get("buyer_email") or order.get("customer_email") or order.get("email") or ""
        email = email.strip().lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)

        fname = order.get("first_name") or order.get("buyer_first_name") or ""
        lname = order.get("last_name") or order.get("buyer_last_name") or ""

        result = await add_subscriber(
            list_id=list_id,
            email=email,
            fname=fname,
            lname=lname,
            tags=["digistore24", "buyer"],
        )
        if "error" not in result:
            synced += 1

    log.info("DS24 -> Mailchimp sync: %d subscribers added to list %s", synced, list_id)
    return synced
