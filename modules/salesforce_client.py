"""Salesforce / Agentforce REST API client for SuperMegaBot CRM integration."""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("SalesforceClient")

SF_INSTANCE = os.getenv("SALESFORCE_INSTANCE_URL", "")
SF_SESSION  = os.getenv("SALESFORCE_SESSION_ID", "")
SF_VERSION  = os.getenv("SALESFORCE_API_VERSION", "v67.0")
SF_BASE     = f"{SF_INSTANCE}/services/data/{SF_VERSION}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {SF_SESSION}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str) -> dict:
    url = SF_BASE + path if not path.startswith("http") else path
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _post(path: str, payload: dict) -> dict:
    url = SF_BASE + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()) if r.length else {}


def _patch(path: str, payload: dict) -> int:
    url = SF_BASE + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def soql(query: str) -> list[dict]:
    """Run a SOQL query and return all records (handles pagination)."""
    if not SF_INSTANCE or not SF_SESSION:
        raise RuntimeError("Salesforce not configured — set SALESFORCE_INSTANCE_URL and SALESFORCE_SESSION_ID")
    url = f"{SF_BASE}/query/?q={urllib.parse.quote(query)}"
    records: list[dict] = []
    while url:
        d = _get(url)
        records.extend(d.get("records", []))
        next_url = d.get("nextRecordsUrl")
        url = f"{SF_INSTANCE}{next_url}" if next_url else None
    for r in records:
        r.pop("attributes", None)
    return records


async def get_leads(status: str | None = None, limit: int = 200) -> list[dict]:
    where = f"WHERE Status = '{status}'" if status else ""
    return soql(f"SELECT Id,FirstName,LastName,Email,Company,Phone,Status,LeadSource,Industry FROM Lead {where} LIMIT {limit}")


async def get_contacts(limit: int = 200) -> list[dict]:
    return soql(f"SELECT Id,FirstName,LastName,Email,Phone,Account.Name,Title FROM Contact LIMIT {limit}")


async def get_accounts(limit: int = 200) -> list[dict]:
    return soql(f"SELECT Id,Name,Industry,Website,AnnualRevenue,Phone,BillingCountry FROM Account LIMIT {limit}")


async def get_opportunities(stage: str | None = None, limit: int = 200) -> list[dict]:
    where = f"WHERE StageName = '{stage}'" if stage else ""
    return soql(f"SELECT Id,Name,Amount,StageName,CloseDate,AccountId FROM Opportunity {where} ORDER BY CloseDate DESC LIMIT {limit}")


async def create_lead(
    first_name: str,
    last_name: str,
    email: str,
    company: str,
    phone: str = "",
    source: str = "SuperMegaBot",
    description: str = "",
) -> dict:
    payload = {
        "FirstName": first_name,
        "LastName": last_name or "Unknown",
        "Email": email,
        "Company": company or "Unknown",
        "LeadSource": source,
        "Status": "Open - Not Contacted",
    }
    if phone:
        payload["Phone"] = phone
    if description:
        payload["Description"] = description
    return _post("/sobjects/Lead", payload)


async def update_lead_status(lead_id: str, status: str) -> bool:
    try:
        code = _patch(f"/sobjects/Lead/{lead_id}", {"Status": status})
        return code in (200, 204)
    except Exception as e:
        log.warning("update_lead_status %s: %s", lead_id, e)
        return False


async def create_contact(
    first_name: str,
    last_name: str,
    email: str,
    phone: str = "",
    account_name: str = "",
) -> dict:
    payload = {
        "FirstName": first_name,
        "LastName": last_name or "Unknown",
        "Email": email,
    }
    if phone:
        payload["Phone"] = phone
    return _post("/sobjects/Contact", payload)


async def get_stats() -> dict:
    leads = soql("SELECT Status, COUNT(Id) cnt FROM Lead GROUP BY Status")
    opps  = soql("SELECT StageName, SUM(Amount) total, COUNT(Id) cnt FROM Opportunity GROUP BY StageName")
    total_pipeline = sum(o.get("total") or 0 for o in opps)
    closed_won = next((o.get("total") or 0 for o in opps if o.get("StageName") == "Closed Won"), 0)
    return {
        "leads_by_status": {l.get("Status"): l.get("cnt") for l in leads},
        "total_leads": sum(l.get("cnt", 0) for l in leads),
        "opportunities_by_stage": {o.get("StageName"): {"count": o.get("cnt"), "amount": o.get("total")} for o in opps},
        "total_pipeline_usd": total_pipeline,
        "closed_won_usd": closed_won,
        "instance": SF_INSTANCE,
        "api_version": SF_VERSION,
    }


async def sync_klaviyo_to_sf() -> dict:
    """Push all Klaviyo profiles to Salesforce as Leads."""
    import aiohttp
    kv_key = os.getenv("KLAVIYO_API_KEY", "")
    if not kv_key:
        return {"ok": False, "error": "KLAVIYO_API_KEY not set"}

    headers = {"Authorization": f"Klaviyo-API-Key {kv_key}", "revision": "2024-10-15"}
    created = 0
    skipped = 0
    async with aiohttp.ClientSession() as s:
        async with s.get("https://a.klaviyo.com/api/profiles/?page[size]=100", headers=headers) as r:
            profiles = (await r.json()).get("data", [])

    for p in profiles:
        attr = p.get("attributes", {})
        email = attr.get("email", "")
        if not email:
            skipped += 1
            continue
        # Check if lead already exists
        existing = soql(f"SELECT Id FROM Lead WHERE Email = '{email}' LIMIT 1")
        if existing:
            skipped += 1
            continue
        try:
            await create_lead(
                first_name=attr.get("first_name", "") or "",
                last_name=attr.get("last_name", "") or "Subscriber",
                email=email,
                company=attr.get("organization", "") or "Klaviyo Subscriber",
                source="Klaviyo",
            )
            created += 1
        except Exception as e:
            log.warning("SF lead create for %s: %s", email, e)
            skipped += 1

    return {"ok": True, "created": created, "skipped": skipped, "total_profiles": len(profiles)}


async def import_sf_leads_to_b2b() -> dict:
    """Import Salesforce leads into local B2B pipeline."""
    from modules.b2b_pipeline import add_lead, get_leads as b2b_leads

    sf_leads = await get_leads(status="Open - Not Contacted")
    existing = await b2b_leads()
    existing_emails = {l.get("email", "").lower() for l in existing}

    added = 0
    for lead in sf_leads:
        email = lead.get("Email", "")
        if not email or email.lower() in existing_emails:
            continue
        await add_lead(
            company=lead.get("Company", "Unknown"),
            email=email,
            domain="",
            niche=lead.get("Industry", "general").lower().replace(" ", "_") if lead.get("Industry") else "general",
            contact_name=f"{lead.get('FirstName','')} {lead.get('LastName','')}".strip(),
            source="salesforce",
        )
        added += 1
        existing_emails.add(email.lower())

    return {"ok": True, "sf_leads_found": len(sf_leads), "imported_to_b2b": added}
