#!/usr/bin/env python3
"""
Analytics Feedback — Plausible / PostHog → structured insights for Claude loop.

Reads traffic + product events and returns prioritized optimization tasks.
Missing keys degrade gracefully (no crash).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("AnalyticsFeedback")

POSTHOG_HOST = (os.getenv("POSTHOG_HOST") or "https://eu.i.posthog.com").rstrip("/")
POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY") or os.getenv("POSTHOG_PERSONAL_API_KEY") or ""
POSTHOG_PROJECT_ID = os.getenv("POSTHOG_PROJECT_ID") or ""
PLAUSIBLE_API_KEY = os.getenv("PLAUSIBLE_API_KEY") or ""
PLAUSIBLE_SITE_ID = os.getenv("PLAUSIBLE_SITE_ID") or os.getenv("PLAUSIBLE_DOMAIN") or ""


async def fetch_plausible(period: str = "7d") -> dict[str, Any]:
    if not PLAUSIBLE_API_KEY or not PLAUSIBLE_SITE_ID:
        return {"ok": False, "skipped": True, "reason": "PLAUSIBLE_API_KEY or SITE_ID missing"}
    url = "https://plausible.io/api/v1/stats/aggregate"
    params = {
        "site_id": PLAUSIBLE_SITE_ID,
        "period": period,
        "metrics": "visitors,pageviews,bounce_rate,visit_duration",
    }
    headers = {"Authorization": f"Bearer {PLAUSIBLE_API_KEY}"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(url, params=params, headers=headers) as r:
                data = await r.json(content_type=None)
                if r.status >= 400:
                    return {"ok": False, "status": r.status, "error": str(data)[:200]}
                results = data.get("results") or data
                return {"ok": True, "provider": "plausible", "period": period, "metrics": results}
    except Exception as e:
        log.warning("Plausible fetch failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}


async def fetch_posthog_insights() -> dict[str, Any]:
    if not POSTHOG_API_KEY:
        return {"ok": False, "skipped": True, "reason": "POSTHOG_API_KEY missing"}
    # Prefer project events summary via query API when project id known
    headers = {
        "Authorization": f"Bearer {POSTHOG_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as s:
            if POSTHOG_PROJECT_ID:
                url = f"{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT_ID}/insights/trend/"
                payload = {
                    "events": [{"id": "$pageview", "type": "events", "order": 0}],
                    "date_from": "-7d",
                    "interval": "day",
                }
                async with s.post(url, headers=headers, json=payload) as r:
                    data = await r.json(content_type=None)
                    if r.status >= 400:
                        # fallback: list projects (auth check)
                        return {
                            "ok": False,
                            "status": r.status,
                            "error": str(data)[:200],
                            "auth_probe": await _posthog_auth_probe(s, headers),
                        }
                    return {"ok": True, "provider": "posthog", "trend": data}
            # Auth-only probe
            probe = await _posthog_auth_probe(s, headers)
            return {"ok": probe.get("ok", False), "provider": "posthog", "probe": probe}
    except Exception as e:
        log.warning("PostHog fetch failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}


async def _posthog_auth_probe(session: aiohttp.ClientSession, headers: dict) -> dict:
    try:
        async with session.get(f"{POSTHOG_HOST}/api/users/@me/", headers=headers) as r:
            body = await r.json(content_type=None)
            return {"ok": r.status < 400, "status": r.status, "user": str(body)[:120]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _to_tasks(plausible: dict, posthog: dict, stripe_mrr: float = 0.0) -> list[dict]:
    """Convert analytics into Claude-ready optimization tasks."""
    tasks: list[dict] = []
    if plausible.get("ok"):
        m = plausible.get("metrics") or {}
        visitors = _num(m, "visitors")
        bounce = _num(m, "bounce_rate")
        if visitors is not None and visitors < 50:
            tasks.append({
                "priority": "high",
                "area": "traffic",
                "title": "Raise organic/paid traffic",
                "detail": f"Only {visitors} visitors in period — boost SEO, IndexNow, LinkedIn, Meta.",
            })
        if bounce is not None and bounce > 65:
            tasks.append({
                "priority": "high",
                "area": "conversion",
                "title": "Reduce bounce rate",
                "detail": f"Bounce ~{bounce}% — tighten hero CTA, case studies, load speed.",
            })
    elif not plausible.get("skipped"):
        tasks.append({
            "priority": "medium",
            "area": "analytics",
            "title": "Fix Plausible integration",
            "detail": str(plausible.get("error") or plausible)[:180],
        })

    if posthog.get("ok"):
        tasks.append({
            "priority": "low",
            "area": "product",
            "title": "Review PostHog funnels",
            "detail": "Pageview trend available — map signup→checkout drop-offs.",
        })
    elif not posthog.get("skipped"):
        tasks.append({
            "priority": "medium",
            "area": "analytics",
            "title": "Fix PostHog integration",
            "detail": str(posthog.get("error") or posthog)[:180],
        })

    if stripe_mrr <= 0:
        tasks.append({
            "priority": "critical",
            "area": "revenue",
            "title": "Zero MRR — close first paying customers",
            "detail": "Run outreach + Sales-Call CTAs + verify Stripe Payment Links live.",
        })

    if not tasks:
        tasks.append({
            "priority": "low",
            "area": "iterate",
            "title": "Ship incremental UX/conversion win",
            "detail": "Analytics healthy — A/B one CTA or pricing microcopy.",
        })
    return tasks


def _num(metrics: dict, key: str) -> float | None:
    node = metrics.get(key)
    if node is None:
        return None
    if isinstance(node, dict):
        v = node.get("value")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    try:
        return float(node)
    except (TypeError, ValueError):
        return None


async def collect_analytics_feedback(stripe_mrr: float = 0.0) -> dict[str, Any]:
    plausible, posthog = await __import__("asyncio").gather(
        fetch_plausible(),
        fetch_posthog_insights(),
    )
    tasks = _to_tasks(plausible, posthog, stripe_mrr)
    return {
        "ok": True,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "plausible": plausible,
        "posthog": posthog,
        "optimization_tasks": tasks,
        "top_task": tasks[0] if tasks else None,
    }
