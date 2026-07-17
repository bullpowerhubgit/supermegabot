#!/usr/bin/env python3
"""
Buyer Intent Router — priorisiert kaufnahe Leads und stößt passende Follow-ups an.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

log = logging.getLogger("BuyerIntentRouter")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
_TIMEOUT = aiohttp.ClientTimeout(total=20)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts() -> str:
    return _now().isoformat()


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Accept-Profile": "public",
        "Content-Profile": "public",
        "Prefer": "return=minimal",
    }


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _revenue_boost(revenue_band: str) -> int:
    text = (revenue_band or "").lower()
    if "150.000" in text or "150000" in text or "über" in text:
        return 25
    if "50.000" in text or "50000" in text:
        return 18
    if "15.000" in text or "15000" in text:
        return 12
    if "5.000" in text or "5000" in text:
        return 6
    return 0


def _score_lead(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata_dict(row.get("metadata"))
    event_type = str(row.get("event_type") or "").lower()
    email = str(row.get("email") or "").strip().lower()
    created_at = _parse_dt(str(row.get("created_at") or "")) or _now()
    age_hours = max((_now() - created_at).total_seconds() / 3600.0, 0.0)
    plan = str(metadata.get("plan") or "").strip() or "Starter"
    revenue_band = str(metadata.get("revenue") or "").strip()
    shop_url = str(metadata.get("shop_url") or "").strip()
    problem = str(metadata.get("problem") or "").strip()
    name = str(metadata.get("name") or row.get("name") or "").strip()

    base_scores = {
        "ht_demo_application": 72,
        "sofia_call": 58,
        "ht_demo_view": 32,
        "ds24_purchase": 84,
        "outreach_email_sent": 18,
    }
    score = base_scores.get(event_type, 20)
    score += _revenue_boost(revenue_band)
    score += {"Enterprise": 12, "Scale": 8, "Growth": 4}.get(plan, 0)
    if shop_url.startswith("http"):
        score += 6
    if problem:
        score += 5
    if age_hours <= 2:
        score += 12
    elif age_hours <= 6:
        score += 8
    elif age_hours <= 24:
        score += 4
    elif age_hours > 72:
        score -= 10
    score = max(0, min(score, 100))

    if event_type == "ds24_purchase":
        action = "upsell_pro"
    elif score >= 85:
        action = "priority_call"
    elif score >= 65:
        action = "send_checkout_and_call"
    elif score >= 45:
        action = "send_case_study"
    else:
        action = "nurture"

    return {
        "email": email,
        "name": name,
        "event_type": event_type,
        "score": score,
        "action": action,
        "plan": plan,
        "revenue_band": revenue_band,
        "shop_url": shop_url,
        "problem": problem,
        "created_at": created_at.isoformat(),
        "age_hours": round(age_hours, 1),
        "metadata": metadata,
    }


async def _supabase_select(table: str, query: str) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return []
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.get(f"{SUPABASE_URL}/rest/v1/{table}?{query}", headers=_headers()) as r:
            if r.status != 200:
                log.warning("Supabase select failed %s/%s: %s", table, query[:80], r.status)
                return []
            data = await r.json(content_type=None)
            return data if isinstance(data, list) else []


async def _supabase_insert(table: str, payload: dict[str, Any]) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return False
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
        async with s.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), json=payload) as r:
            return r.status in (200, 201)


async def _recent_followup_exists(email: str, hours: int = 24) -> bool:
    if not email:
        return True
    cutoff = (_now() - timedelta(hours=hours)).isoformat()
    rows = await _supabase_select(
        "client_activity_log",
        "select=email,event_type,created_at"
        f"&email=eq.{email}"
        "&event_type=eq.buyer_priority_followup"
        f"&created_at=gte.{cutoff}"
        "&limit=1",
    )
    return bool(rows)


async def get_hot_leads(limit: int = 10, hours: int = 72) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return {"ok": False, "skipped": True, "reason": "supabase_not_configured", "leads": []}
    cutoff = (_now() - timedelta(hours=hours)).isoformat()
    rows = await _supabase_select(
        "lead_events",
        "select=event_type,email,name,metadata,created_at"
        f"&created_at=gte.{cutoff}"
        "&order=created_at.desc"
        f"&limit={max(limit * 5, 25)}",
    )
    scored: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        lead = _score_lead(row)
        key = (lead["email"], lead["event_type"])
        if not lead["email"] or key in seen:
            continue
        seen.add(key)
        scored.append(lead)
    scored.sort(key=lambda item: (-item["score"], item["age_hours"]))
    top = scored[:limit]
    return {
        "ok": True,
        "leads": top,
        "count": len(top),
        "at": _ts(),
    }


async def run_buyer_priority_cycle(limit: int = 5) -> dict[str, Any]:
    summary = {
        "ok": True,
        "configured": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),
        "processed": 0,
        "followups_sent": 0,
        "top_leads": [],
        "actions": [],
        "at": _ts(),
    }
    hot = await get_hot_leads(limit=limit, hours=96)
    if not hot.get("ok"):
        return {**summary, **hot}

    leads = hot.get("leads") or []
    summary["top_leads"] = leads

    try:
        from modules.email_onboarding_autopilot import enroll_lead
        from modules.notify_hub import notify_async
        from modules.sales_call_process import SALES_CALL_URL, STRIPE_PRO, STRIPE_STARTER
    except Exception as e:
        return {**summary, "ok": False, "error": str(e)[:160]}

    for lead in leads:
        email = lead.get("email", "")
        if not email or await _recent_followup_exists(email, hours=24):
            continue
        summary["processed"] += 1
        action = lead.get("action")
        if action in ("priority_call", "send_checkout_and_call", "send_case_study"):
            day = 1 if action == "send_case_study" else 0
            result = await enroll_lead(email, lead.get("name", ""), day=day)
            if result.get("ok"):
                summary["followups_sent"] += 1
            checkout = STRIPE_PRO if lead.get("score", 0) >= 85 else STRIPE_STARTER
            await _supabase_insert(
                "client_activity_log",
                {
                    "email": email,
                    "event_type": "buyer_priority_followup",
                    "product": f"{action}:{lead.get('plan')}",
                    "amount_eur": 0,
                    "created_at": _ts(),
                },
            )
            await notify_async(
                f"Hot Lead {lead.get('score')}/100: {email}",
                (
                    f"Aktion: {action}\n"
                    f"Plan: {lead.get('plan')} | Revenue: {lead.get('revenue_band') or 'n/a'}\n"
                    f"Checkout: {checkout}\nCall: {SALES_CALL_URL}"
                ),
                "info",
            )
            summary["actions"].append(
                {
                    "email": email,
                    "action": action,
                    "score": lead.get("score"),
                    "followup_ok": bool(result.get("ok")),
                }
            )
        elif action == "upsell_pro":
            await _supabase_insert(
                "client_activity_log",
                {
                    "email": email,
                    "event_type": "buyer_priority_followup",
                    "product": "upsell_pro:existing_buyer",
                    "amount_eur": 0,
                    "created_at": _ts(),
                },
            )
            summary["actions"].append(
                {"email": email, "action": action, "score": lead.get("score"), "followup_ok": True}
            )

    return summary
