"""
High-Ticket Demo System
========================
Verwaltet Demo-Environments und Live-Demo-Daten für Interessenten:
- Demo-View-Tracking in Supabase
- Personalisierte Demo-Daten generieren
- Follow-up nach Demo-View
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("ht_demo_system")

DEMO_METRICS = {
    "products_synced": 847,
    "todays_revenue": 4821,
    "hours_saved_week": 40,
    "active_platforms": 7,
    "leads_today": 12,
    "posts_today": 23,
    "ai_optimizations": 34,
    "weekly_reach": 14392,
}


async def get_demo_data(shop_revenue: int = 25000) -> dict:
    """Generiert personalisierte Demo-Metriken basierend auf Shop-Revenue."""
    scale = max(1.0, shop_revenue / 25000)

    return {
        "products_synced": min(int(DEMO_METRICS["products_synced"] * scale), 9999),
        "todays_revenue": int(DEMO_METRICS["todays_revenue"] * scale),
        "hours_saved_week": int(DEMO_METRICS["hours_saved_week"] + (scale - 1) * 15),
        "active_platforms": DEMO_METRICS["active_platforms"],
        "leads_today": int(DEMO_METRICS["leads_today"] * scale),
        "posts_today": DEMO_METRICS["posts_today"],
        "ai_optimizations": int(DEMO_METRICS["ai_optimizations"] * scale),
        "weekly_reach": int(DEMO_METRICS["weekly_reach"] * scale),
        "roi_estimate_year": int(shop_revenue * 0.22 * 12 + 2080 * 50),
        "personalized": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def track_demo_view(ip: str = "", referrer: str = "", plan: str = "") -> None:
    """Trackt einen Demo-Page-View in Supabase."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return

    try:
        import aiohttp
        payload = {
            "event_type": "ht_demo_view",
            "email": "anonymous",
            "metadata": json.dumps({
                "referrer": referrer[:200] if referrer else "",
                "plan_hint": plan,
                "ts": datetime.now(timezone.utc).isoformat(),
            }),
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            await s.post(
                f"{url}/rest/v1/lead_events",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=payload,
            )
    except Exception as e:
        log.debug("Demo view tracking failed (non-critical): %s", e)


async def get_demo_stats() -> dict:
    """Gibt Demo-View-Statistiken zurück."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return {"views": 0, "applications": 0, "conversion_rate": 0}

    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(
                f"{url}/rest/v1/lead_events?event_type=eq.ht_demo_view&select=count",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Accept": "application/vnd.pgrst.object+json",
                         "Prefer": "count=exact"},
            ) as r:
                views = int(r.headers.get("Content-Range", "0/0").split("/")[-1]) if r.status == 200 else 0

            async with s.get(
                f"{url}/rest/v1/lead_events?event_type=eq.ht_demo_application&select=count",
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Accept": "application/vnd.pgrst.object+json",
                         "Prefer": "count=exact"},
            ) as r:
                apps = int(r.headers.get("Content-Range", "0/0").split("/")[-1]) if r.status == 200 else 0

        return {
            "views": views,
            "applications": apps,
            "conversion_rate": round(apps / views * 100, 1) if views > 0 else 0,
        }
    except Exception as e:
        log.error("Demo stats failed: %s", e)
        return {"views": 0, "applications": 0, "conversion_rate": 0, "error": str(e)}
