"""Pipedrive CRM integration — deals, persons, organisations, webhooks."""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("Pipedrive")

_BASE = "https://api.pipedrive.com/v1"


def _cfg() -> tuple[str, str]:
    token = os.getenv("PIPEDRIVE_API_TOKEN", "")
    domain = os.getenv("PIPEDRIVE_COMPANY_DOMAIN", "aiitec")
    return token, domain


async def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    import aiohttp
    token, domain = _cfg()
    base = _BASE
    p = {"api_token": token, **(params or {})}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}{path}", params=p) as r:
            return await r.json()


async def _post(path: str, body: dict) -> dict[str, Any]:
    import aiohttp
    token, _ = _cfg()
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{_BASE}{path}", params={"api_token": token}, json=body) as r:
            return await r.json()


async def _put(path: str, body: dict) -> dict[str, Any]:
    import aiohttp
    token, _ = _cfg()
    async with aiohttp.ClientSession() as s:
        async with s.put(f"{_BASE}{path}", params={"api_token": token}, json=body) as r:
            return await r.json()


# ── Deals ─────────────────────────────────────────────────────────────────────

async def list_deals(limit: int = 20, status: str = "all_not_deleted") -> list:
    d = await _get("/deals", {"limit": limit, "status": status})
    return d.get("data") or []


async def create_deal(title: str, value: float = 0, currency: str = "EUR",
                      person_id: int | None = None, org_id: int | None = None) -> dict:
    body: dict = {"title": title, "value": value, "currency": currency}
    if person_id:
        body["person_id"] = person_id
    if org_id:
        body["org_id"] = org_id
    d = await _post("/deals", body)
    return d.get("data") or {}


async def update_deal(deal_id: int, **fields) -> dict:
    d = await _put(f"/deals/{deal_id}", fields)
    return d.get("data") or {}


# ── Persons ───────────────────────────────────────────────────────────────────

async def list_persons(limit: int = 20) -> list:
    d = await _get("/persons", {"limit": limit})
    return d.get("data") or []


async def create_person(name: str, email: str = "", phone: str = "") -> dict:
    body: dict = {"name": name}
    if email:
        body["email"] = [{"value": email, "primary": True}]
    if phone:
        body["phone"] = [{"value": phone, "primary": True}]
    d = await _post("/persons", body)
    return d.get("data") or {}


async def find_person_by_email(email: str) -> dict | None:
    d = await _get("/persons/search", {"term": email, "fields": "email", "limit": 1})
    items = (d.get("data") or {}).get("items") or []
    return items[0]["item"] if items else None


# ── Organisations ─────────────────────────────────────────────────────────────

async def list_orgs(limit: int = 20) -> list:
    d = await _get("/organizations", {"limit": limit})
    return d.get("data") or []


async def create_org(name: str) -> dict:
    d = await _post("/organizations", {"name": name})
    return d.get("data") or {}


# ── Pipeline / Stages ─────────────────────────────────────────────────────────

async def list_pipelines() -> list:
    d = await _get("/pipelines")
    return d.get("data") or []


async def list_stages(pipeline_id: int | None = None) -> list:
    params = {"pipeline_id": pipeline_id} if pipeline_id else {}
    d = await _get("/stages", params)
    return d.get("data") or []


# ── Activities ────────────────────────────────────────────────────────────────

async def create_activity(subject: str, deal_id: int, activity_type: str = "call",
                          due_date: str = "", note: str = "") -> dict:
    body = {"subject": subject, "deal_id": deal_id, "type": activity_type}
    if due_date:
        body["due_date"] = due_date
    if note:
        body["note"] = note
    d = await _post("/activities", body)
    return d.get("data") or {}


# ── Shopify → Pipedrive auto-sync ─────────────────────────────────────────────

async def sync_shopify_customer(email: str, name: str, order_value: float,
                                 order_id: str) -> dict:
    """Create or update person + deal from a Shopify order."""
    person = await find_person_by_email(email)
    if not person:
        person = await create_person(name=name, email=email)
    person_id = person.get("id")

    deal = await create_deal(
        title=f"Shopify Order #{order_id} — {name}",
        value=order_value,
        currency="EUR",
        person_id=person_id,
    )
    log.info("Pipedrive deal created: %s (€%.2f)", deal.get("title"), order_value)
    return {"person": person, "deal": deal}


# ── Status ────────────────────────────────────────────────────────────────────

async def check_status() -> dict[str, Any]:
    token, domain = _cfg()
    if not token:
        return {"status": "error", "message": "PIPEDRIVE_API_TOKEN not set"}
    try:
        d = await _get("/users/me")
        user = d.get("data") or {}
        return {
            "status": "ok",
            "user": user.get("name"),
            "email": user.get("email"),
            "company": user.get("company_name"),
            "domain": domain,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
