#!/usr/bin/env python3
"""
Klaviyo Email Marketing Automation
Profiles, Lists, Flows, Campaigns — auto-sync from Digistore24 & Shopify
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("Klaviyo")

_BASE = "https://a.klaviyo.com/api"
_REVISION = "2024-10-15"


def _headers() -> Dict[str, str]:
    key = os.getenv("KLAVIYO_API_KEY", "")
    return {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision":      _REVISION,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _session(total: int = 30) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=total))


# ── Health ────────────────────────────────────────────────────────────────────

async def ping() -> tuple[bool, str]:
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        return False, "KLAVIYO_API_KEY nicht gesetzt"
    try:
        async with _session() as s:
            async with s.get(f"{_BASE}/accounts/", headers=_headers()) as r:
                if r.status == 200:
                    d = await r.json()
                    name = d.get("data", [{}])[0].get("attributes", {}).get("contact_information", {}).get("company_name", "OK")
                    return True, name
                return False, f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


# ── Profiles ──────────────────────────────────────────────────────────────────

async def get_profiles(count: int = 100) -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/profiles/",
                headers=_headers(),
                params={"page[size]": min(count, 100)}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":    p["id"],
                        "email": p["attributes"].get("email", ""),
                        "name":  f"{p['attributes'].get('first_name','')} {p['attributes'].get('last_name','')}".strip(),
                        "created": p["attributes"].get("created", ""),
                    }
                    for p in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_profiles: {e}")
        return []


async def upsert_profile(email: str, first_name: str = "", last_name: str = "",
                         phone: str = "", properties: Dict = None) -> Optional[str]:
    """Create or update a Klaviyo profile. Returns profile ID."""
    body = {
        "data": {
            "type": "profile",
            "attributes": {
                "email":      email,
                "first_name": first_name,
                "last_name":  last_name,
                **({"phone_number": phone} if phone else {}),
                "properties": properties or {},
            }
        }
    }
    try:
        async with _session() as s:
            async with s.post(f"{_BASE}/profile-import/", headers=_headers(), json=body) as r:
                if r.status in (200, 201):
                    d = await r.json()
                    return d.get("data", {}).get("id")
                log.warning(f"upsert_profile HTTP {r.status}: {await r.text()}")
                return None
    except Exception as e:
        log.error(f"upsert_profile: {e}")
        return None


# ── Lists ─────────────────────────────────────────────────────────────────────

async def get_lists() -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(f"{_BASE}/lists/", headers=_headers()) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {"id": lst["id"], "name": lst["attributes"].get("name", ""), "created": lst["attributes"].get("created", "")}
                    for lst in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_lists: {e}")
        return []


async def create_list(name: str) -> Optional[str]:
    body = {"data": {"type": "list", "attributes": {"name": name}}}
    try:
        async with _session() as s:
            async with s.post(f"{_BASE}/lists/", headers=_headers(), json=body) as r:
                if r.status in (200, 201):
                    return (await r.json()).get("data", {}).get("id")
                return None
    except Exception as e:
        log.error(f"create_list: {e}")
        return None


async def add_profile_to_list(list_id: str, profile_id: str) -> bool:
    body = {"data": [{"type": "profile", "id": profile_id}]}
    try:
        async with _session() as s:
            async with s.post(
                f"{_BASE}/lists/{list_id}/relationships/profiles/",
                headers=_headers(), json=body
            ) as r:
                return r.status in (200, 204)
    except Exception:
        return False


# ── Campaigns ─────────────────────────────────────────────────────────────────

async def get_campaigns(limit: int = 20) -> List[Dict]:
    try:
        async with _session() as s:
            async with s.get(
                f"{_BASE}/campaigns/",
                headers=_headers(),
                params={"filter": "equals(messages.channel,'email')", "page[size]": limit}
            ) as r:
                if r.status != 200:
                    return []
                d = await r.json()
                return [
                    {
                        "id":     c["id"],
                        "name":   c["attributes"].get("name", ""),
                        "status": c["attributes"].get("status", ""),
                        "created": c["attributes"].get("created_at", ""),
                    }
                    for c in d.get("data", [])
                ]
    except Exception as e:
        log.error(f"get_campaigns: {e}")
        return []


async def create_and_send_campaign(
    list_id: str,
    subject: str,
    from_email: str,
    from_name: str,
    html_body: str,
    campaign_name: str = "",
) -> Dict:
    """Create a Klaviyo campaign, set content, and send it."""
    name = campaign_name or f"SMB Campaign {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    # Klaviyo API 2024-10-15: campaign-messages must be included inline at creation
    camp_body = {
        "data": {
            "type": "campaign",
            "attributes": {
                "name": name,
                "audiences": {
                    "included": [list_id],
                    "excluded": [],
                },
                "send_strategy": {"method": "immediate"},
                "campaign-messages": {
                    "data": [{
                        "type": "campaign-message",
                        "attributes": {
                            "channel": "email",
                            "label": "Email",
                            "content": {
                                "subject": subject,
                                "preview_text": subject[:90],
                                "from_email": from_email,
                                "from_label": from_name,
                                "reply_to_email": from_email,
                            },
                        }
                    }]
                },
            }
        }
    }
    try:
        async with _session(total=60) as s:
            # 1. Create campaign (with inline messages)
            async with s.post(f"{_BASE}/campaigns/", headers=_headers(), json=camp_body) as r:
                resp_body = await r.json(content_type=None)
                if r.status not in (200, 201):
                    err_detail = str(resp_body)[:400]
                    log.error("Klaviyo campaign error: %s", err_detail)
                    return {"ok": False, "error": f"Campaign-Erstellung: HTTP {r.status}", "detail": err_detail}
                camp_data = resp_body["data"]
                camp_id = camp_data["id"]
                # Extract message id from inline response
                msgs = camp_data.get("relationships", {}).get("campaign-messages", {}).get("data", [])
                msg_id = msgs[0]["id"] if msgs else ""

            # 2. Set HTML content on message (if msg_id found)
            if msg_id and html_body:
                tmpl_body = {
                    "data": {
                        "type": "campaign-message",
                        "id": msg_id,
                        "attributes": {"content": {"html": html_body}},
                    }
                }
                async with s.patch(f"{_BASE}/campaign-messages/{msg_id}/", headers=_headers(), json=tmpl_body) as r:
                    await r.read()
                    if r.status not in (200, 204):
                        log.warning("Klaviyo template upload HTTP %s", r.status)

            # 3. Send — id=campaign_id per Klaviyo API 2024-10-15 (send-job uses id as campaign ref)
            log.info("Klaviyo send-job: camp_id=%s msg_id=%s", camp_id, msg_id)
            async with s.post(
                f"{_BASE}/campaign-send-jobs/",
                headers=_headers(),
                json={"data": {"type": "campaign-send-job", "id": camp_id}}
            ) as r:
                send_body = await r.json(content_type=None)
                if r.status not in (200, 201, 202):
                    return {"ok": False, "error": f"Senden: HTTP {r.status}",
                            "camp_id": camp_id, "msg_id": msg_id,
                            "detail": str(send_body)[:400]}

        return {"ok": True, "campaign_id": camp_id, "message_id": msg_id, "name": name}
    except Exception as e:
        log.error(f"create_and_send_campaign: {e}")
        return {"ok": False, "error": str(e)}


# ── Sync from Digistore24 ─────────────────────────────────────────────────────

async def sync_from_digistore(list_id: str) -> int:
    """Sync Digistore24 buyer emails into a Klaviyo list."""
    from pathlib import Path
    import json as _json
    data_dir = Path(__file__).parent.parent / "data"
    orders_file = data_dir / "digistore_orders.json"
    if not orders_file.exists():
        return 0
    try:
        orders = _json.loads(orders_file.read_text())
    except Exception:
        return 0

    synced = 0
    for order in orders:
        email = order.get("buyer_email") or order.get("email", "")
        if not email or "@" not in email:
            continue
        profile_id = await upsert_profile(
            email=email,
            first_name=order.get("first_name", ""),
            last_name=order.get("last_name", ""),
            properties={"source": "digistore24", "product": order.get("product_name", "")},
        )
        if profile_id:
            await add_profile_to_list(list_id, profile_id)
            synced += 1
    return synced


# ── Sync from Shopify ─────────────────────────────────────────────────────────

async def sync_from_shopify(list_id: str, limit: int = 50) -> int:
    """Sync Shopify customer emails into a Klaviyo list."""
    import os as _os
    token  = _os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    domain = _os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    if not token or not domain:
        return 0
    base    = f"https://{domain}" if not domain.startswith("http") else domain
    api_ver = _os.getenv("SHOPIFY_API_VERSION", "2024-10")
    headers = {"X-Shopify-Access-Token": token}
    synced  = 0
    try:
        async with _session() as s:
            async with s.get(
                f"{base}/admin/api/{api_ver}/customers.json?limit={limit}",
                headers=headers
            ) as r:
                if r.status != 200:
                    return 0
                customers = (await r.json()).get("customers", [])
        for c in customers:
            email = c.get("email", "")
            if not email:
                continue
            pid = await upsert_profile(
                email=email,
                first_name=c.get("first_name", ""),
                last_name=c.get("last_name", ""),
                properties={"source": "shopify", "orders_count": c.get("orders_count", 0)},
            )
            if pid:
                await add_profile_to_list(list_id, pid)
                synced += 1
    except Exception as e:
        log.error(f"sync_from_shopify: {e}")
    return synced


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_stats() -> Dict:
    ok, account = await ping()
    if not ok:
        return {"ok": False, "error": account}
    profiles  = await get_profiles(count=1)
    lists     = await get_lists()
    campaigns = await get_campaigns(limit=5)
    return {
        "ok":             True,
        "account":        account,
        "list_count":     len(lists),
        "campaign_count": len(campaigns),
        "lists":          lists[:5],
        "recent_campaigns": campaigns[:5],
    }


def _default_html(subject: str) -> str:
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
<h1 style="color:#2c3e50">{subject}</h1>
<p>Hallo,</p>
<p>entdecke jetzt die neueste KI-Einkommens-Strategie von AIITEC — vollautomatisiert, skalierbar und bewährt.</p>
<p style="margin:24px 0"><a href="https://www.digistore24.com/redir/669750/user37405262/" style="background:#e74c3c;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold">👉 Jetzt starten</a></p>
<p>Bis bald,<br><strong>Rudolf | AIITEC</strong></p>
<hr style="border:none;border-top:1px solid #eee;margin:30px 0">
<p style="font-size:11px;color:#999">AIITEC — KI-Automatisierung für dein Business | <a href="{{{{ unsubscribe_url }}}}">Abmelden</a></p>
</body></html>"""


async def send_campaign(subject: str, html_body: str = "", list_id: str = "") -> dict:
    """One-step: create + send Klaviyo campaign. Returns {ok, campaign_id, error}."""
    _list_id = list_id or os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
    from_email = os.getenv("KLAVIYO_FROM_EMAIL", "bullpowersrtkennels@gmail.com")
    from_name  = os.getenv("KLAVIYO_FROM_NAME", "Rudolf | AIITEC")
    _html = html_body or _default_html(subject)
    result = await create_and_send_campaign(
        list_id=_list_id,
        subject=subject,
        from_email=from_email,
        from_name=from_name,
        html_body=_html,
    )
    return result


async def run_with_brutus_traffic() -> dict:
    """Run Klaviyo stats then fire BRUTUS traffic for email marketing."""
    result = {}
    try:
        result["stats"] = await get_stats()
    except Exception as e:
        result["stats_error"] = str(e)
    try:
        from modules.brutus_traffic_engine import run_brutus_swarm
        result["brutus"] = await run_brutus_swarm(
            keywords=["Email Marketing Automation 2026", "Klaviyo E-Commerce Automation", "automatische Email Sequenz"],
            max_keywords=3,
        )
    except Exception as e:
        result["brutus_error"] = str(e)
    return result
