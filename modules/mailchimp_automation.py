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


# ── Maximum-Setup Additions ───────────────────────────────────────────────────

async def create_welcome_automation(list_id: str, from_name: str = "SuperMegaBot") -> dict:
    """Create a 3-email welcome automation sequence for new subscribers.

    Emails: Welcome (day 0), Feature intro (day 3), Upsell (day 7).

    Returns:
        {"ok": True, "automations": [{"name": ..., "id": ...}]}
    """
    if not MC_API_KEY or not HAS_AIOHTTP:
        log.warning("Mailchimp not configured — skipping create_welcome_automation")
        return {"ok": False, "error": "Mailchimp not configured"}

    sequence = [
        {
            "name":    "Welcome to SuperMegaBot",
            "subject": "Willkommen bei SuperMegaBot 🤖",
            "delay":   0,
            "body":    (
                "<h2>Willkommen an Bord!</h2>"
                "<p>Dein SuperMegaBot-Account ist jetzt aktiv. Hier sind deine ersten Schritte:</p>"
                "<ul><li>Dashboard öffnen</li><li>Shopify verbinden</li><li>Ersten Autopilot starten</li></ul>"
                "<p>Bei Fragen antworte einfach auf diese E-Mail.</p>"
            ),
        },
        {
            "name":    "SuperMegaBot: Entdecke alle Features",
            "subject": "Diese 5 Features sparen dir 10h/Woche",
            "delay":   3,
            "body":    (
                "<h2>Deine Top-5 Features</h2>"
                "<ol>"
                "<li><b>Shopify Autopilot</b> — Produkte automatisch importieren &amp; optimieren</li>"
                "<li><b>KI-Texte</b> — Produktbeschreibungen per Klick</li>"
                "<li><b>Telegram-Alerts</b> — Immer informiert</li>"
                "<li><b>Revenue Analytics</b> — Umsatz in Echtzeit</li>"
                "<li><b>SEO Optimizer</b> — Meta-Tags automatisch verbessern</li>"
                "</ol>"
            ),
        },
        {
            "name":    "SuperMegaBot: Upgrade auf Pro",
            "subject": "Bereit für den nächsten Level? Upgrade auf Pro",
            "delay":   7,
            "body":    (
                "<h2>Mehr Power mit SuperMegaBot Pro</h2>"
                "<p>Pro-Nutzer machen im Schnitt <b>3x mehr Umsatz</b> als Starter-Nutzer.</p>"
                "<p><a href='https://supermegabot.com/pricing'>Jetzt upgraden — nur €99/Monat</a></p>"
            ),
        },
    ]

    created = []
    import aiohttp as _aiohttp
    for step in sequence:
        campaign_payload = {
            "type": "regular",
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": step["subject"],
                "title":        step["name"],
                "from_name":    from_name,
                "reply_to":     "noreply@supermegabot.com",
            },
        }
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.post(
                    f"{MC_BASE}/campaigns",
                    headers=_auth_header(),
                    json=campaign_payload,
                    timeout=_aiohttp.ClientTimeout(total=15),
                ) as resp:
                    campaign = await resp.json(content_type=None)

            if "id" not in campaign:
                log.warning("Welcome automation step failed: %s", campaign.get("detail"))
                continue

            campaign_id = campaign["id"]
            async with _aiohttp.ClientSession() as session:
                async with session.put(
                    f"{MC_BASE}/campaigns/{campaign_id}/content",
                    headers=_auth_header(),
                    json={"html": step["body"]},
                    timeout=_aiohttp.ClientTimeout(total=15),
                ) as resp:
                    pass

            created.append({"name": step["name"], "id": campaign_id, "delay_days": step["delay"]})
            log.info("Welcome automation created: %s (id=%s)", step["name"], campaign_id)
        except Exception as exc:
            log.error("create_welcome_automation step '%s': %s", step["name"], exc)

    return {"ok": len(created) > 0, "automations": created}


async def tag_customer_by_purchase(list_id: str, email: str, product_names: list) -> dict:
    """Tag a Mailchimp subscriber based on their purchased products.

    Args:
        list_id:       Mailchimp audience ID
        email:         Customer email address
        product_names: List of product names/categories purchased

    Returns:
        {"ok": True, "tags_applied": [...]}
    """
    if not MC_API_KEY or not HAS_AIOHTTP:
        return {"ok": False, "error": "Mailchimp not configured"}

    import hashlib, aiohttp as _aiohttp
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()

    # Build meaningful tags from product names
    tags = []
    for name in product_names:
        name_lower = name.lower()
        if any(kw in name_lower for kw in ["starter", "basic", "free"]):
            tags.append("plan:starter")
        elif any(kw in name_lower for kw in ["pro", "professional"]):
            tags.append("plan:pro")
        elif any(kw in name_lower for kw in ["enterprise", "business"]):
            tags.append("plan:enterprise")
        tags.append(f"bought:{name[:40].strip().replace(' ', '-').lower()}")

    tags = list(set(tags))  # deduplicate
    if not tags:
        return {"ok": True, "tags_applied": [], "note": "No tags to apply"}

    try:
        async with _aiohttp.ClientSession() as session:
            async with session.post(
                f"{MC_BASE}/lists/{list_id}/members/{email_hash}/tags",
                headers=_auth_header(),
                json={"tags": [{"name": t, "status": "active"} for t in tags]},
                timeout=_aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 204):
                    log.info("Tagged %s with %d tags in Mailchimp", email, len(tags))
                    return {"ok": True, "tags_applied": tags, "email": email}
                body = await resp.text()
                return {"ok": False, "error": f"HTTP {resp.status}: {body[:200]}"}
    except Exception as exc:
        log.error("tag_customer_by_purchase: %s", exc)
        return {"ok": False, "error": str(exc)}


async def get_revenue_attribution(count: int = 20) -> dict:
    """Analyse which Mailchimp campaigns generated revenue (by click/send stats).

    Returns campaigns sorted by revenue-proxy score (unique_clicks / sends * 100).

    Returns:
        {"ok": True, "campaigns": [{"id": ..., "subject": ..., "attribution_score": float, ...}]}
    """
    if not MC_API_KEY or not HAS_AIOHTTP:
        return {"ok": False, "error": "Mailchimp not configured"}

    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as session:
            async with session.get(
                f"{MC_BASE}/campaigns",
                headers=_auth_header(),
                params={
                    "count":      count,
                    "status":     "sent",
                    "sort_field": "send_time",
                    "sort_dir":   "DESC",
                    "fields":     "campaigns.id,campaigns.settings.subject_line,campaigns.settings.title,"
                                  "campaigns.report_summary,campaigns.send_time",
                },
                timeout=_aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)

        campaigns_raw = data.get("campaigns", [])
        result = []
        for c in campaigns_raw:
            summary = c.get("report_summary", {}) or {}
            sends         = summary.get("emails_sent", 0) or 0
            unique_clicks = summary.get("unique_subscriber_clicks", 0) or 0
            opens         = summary.get("unique_opens", 0) or 0
            unsubscribes  = summary.get("unsubscribes", 0) or 0

            # Revenue-proxy score: click-through rate weighted by open rate
            ctr  = (unique_clicks / sends * 100) if sends else 0
            ctor = (unique_clicks / opens * 100) if opens else 0
            attribution_score = round((ctr * 0.6 + ctor * 0.4), 3)

            result.append({
                "id":               c.get("id"),
                "subject":          c.get("settings", {}).get("subject_line", ""),
                "title":            c.get("settings", {}).get("title", ""),
                "send_time":        c.get("send_time", ""),
                "sends":            sends,
                "unique_clicks":    unique_clicks,
                "unique_opens":     opens,
                "unsubscribes":     unsubscribes,
                "ctr_pct":          round(ctr, 2),
                "ctor_pct":         round(ctor, 2),
                "attribution_score": attribution_score,
            })

        # Sort by attribution score (highest first)
        result.sort(key=lambda x: -x["attribution_score"])
        log.info("Revenue attribution: %d campaigns analysed", len(result))
        return {"ok": True, "campaigns": result}
    except Exception as exc:
        log.error("get_revenue_attribution: %s", exc)
        return {"ok": False, "error": str(exc), "campaigns": []}
