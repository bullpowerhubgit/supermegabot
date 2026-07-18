"""
TikTok Ads Engine — autonomous campaign management for ineedit.com.co.
Uses TikTok Marketing API v1.3.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import aiohttp

log = logging.getLogger("TikTokAdsEngine")

TK_ACCESS_TOKEN   = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TK_ADVERTISER_ID  = os.getenv("TIKTOK_ADVERTISER_ID", "")
TK_APP_KEY        = os.getenv("TIKTOK_APP_KEY", "")
TK_APP_SECRET     = os.getenv("TIKTOK_APP_SECRET", "")
SHOP_URL          = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
TG_TOKEN          = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT           = os.getenv("TELEGRAM_CHAT_ID", "")

API_BASE = "https://business-api.tiktok.com/open_api/v1.3"


def _tk_headers() -> dict:
    return {
        "Access-Token": TK_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg[:4096]},
            )
    except Exception:
        pass


async def get_campaigns() -> list[dict]:
    """Fetch all active TikTok campaigns for the advertiser."""
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"{API_BASE}/campaign/get/",
                headers=_tk_headers(),
                params={
                    "advertiser_id": TK_ADVERTISER_ID,
                    "page_size": 20,
                },
            ) as r:
                data = await r.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("list", [])
        log.warning("TikTok get_campaigns: %s", data.get("message", ""))
    except Exception as e:
        log.warning("TikTok get_campaigns error: %s", e)
    return []


async def create_traffic_campaign(budget: float = 10.0) -> dict:
    """Create a daily budget traffic campaign targeting DE/AT/CH."""
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return {"ok": False, "error": "no TikTok credentials"}
    payload = {
        "advertiser_id": TK_ADVERTISER_ID,
        "campaign_name": f"ineedit_traffic_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "objective_type": "TRAFFIC",
        "budget_mode": "BUDGET_MODE_DAY",
        "budget": budget,
        "operation_status": "ENABLE",
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{API_BASE}/campaign/create/",
                headers=_tk_headers(),
                json=payload,
            ) as r:
                data = await r.json()
        if data.get("code") == 0:
            campaign_id = data["data"]["campaign_id"]
            log.info("TikTok campaign created: %s", campaign_id)
            return {"ok": True, "campaign_id": campaign_id}
        return {"ok": False, "error": data.get("message", str(data)[:200])}
    except Exception as e:
        log.warning("TikTok create_campaign error: %s", e)
        return {"ok": False, "error": str(e)}


async def create_ad_group(campaign_id: str, budget: float = 5.0) -> dict:
    """Create an ad group targeting DE/AT/CH, 18-45, Smart Home/Technology interests."""
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return {"ok": False, "error": "no credentials"}
    payload = {
        "advertiser_id": TK_ADVERTISER_ID,
        "campaign_id": campaign_id,
        "adgroup_name": f"ineedit_dach_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
        "placement_type": "PLACEMENT_TYPE_AUTOMATIC",
        "location_ids": ["6252001", "2782113", "2658434"],  # DE, AT, CH GeoName IDs
        "age": ["AGE_18_24", "AGE_25_34", "AGE_35_44", "AGE_45_54"],
        "budget_mode": "BUDGET_MODE_DAY",
        "budget": budget,
        "schedule_type": "SCHEDULE_START_END",
        "schedule_start_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "schedule_end_time": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "optimization_goal": "CLICK",
        "bid_type": "BID_TYPE_NO_BID",
        "operation_status": "ENABLE",
        "audience_type": "CUSTOM_AUDIENCE",
        "interest_category_ids": ["4", "27"],  # Technology, Home & Garden approximate
        "click_attribution_window": "CLICK_7D",
        "video_download_disabled": False,
        "external_action": "LANDING_PAGE",
        "pixel_id": os.getenv("TIKTOK_PIXEL_ID", ""),
    }
    # Remove empty pixel_id
    if not payload["pixel_id"]:
        del payload["pixel_id"]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{API_BASE}/adgroup/create/",
                headers=_tk_headers(),
                json=payload,
            ) as r:
                data = await r.json()
        if data.get("code") == 0:
            adgroup_id = data["data"]["adgroup_id"]
            log.info("TikTok ad group created: %s", adgroup_id)
            return {"ok": True, "adgroup_id": adgroup_id}
        return {"ok": False, "error": data.get("message", str(data)[:200])}
    except Exception as e:
        log.warning("TikTok create_adgroup error: %s", e)
        return {"ok": False, "error": str(e)}


async def create_ad(adgroup_id: str, creative: dict | None = None) -> dict:
    """Create an ad with image/text creative pointing to ineedit.com.co."""
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return {"ok": False, "error": "no credentials"}
    default_creative = {
        "ad_name": f"ineedit_ad_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
        "ad_text": "🔥 Smart Home Gadgets & Solar — Top Deals auf ineedit.com.co!",
        "call_to_action": "SHOP_NOW",
        "landing_page_url": SHOP_URL,
        "display_name": "ineedit Smart Home",
        "profile_image_url": f"{SHOP_URL}/cdn/shop/files/logo.png",
    }
    payload = {
        "advertiser_id": TK_ADVERTISER_ID,
        "adgroup_id": adgroup_id,
        "creatives": [{**(creative or {}), **default_creative, **(creative or {})}],
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{API_BASE}/ad/create/",
                headers=_tk_headers(),
                json=payload,
            ) as r:
                data = await r.json()
        if data.get("code") == 0:
            return {"ok": True, "ad_ids": data.get("data", {}).get("ad_ids", [])}
        return {"ok": False, "error": data.get("message", str(data)[:200])}
    except Exception as e:
        log.warning("TikTok create_ad error: %s", e)
        return {"ok": False, "error": str(e)}


async def get_insights(days: int = 7) -> dict:
    """Fetch campaign performance for the last N days."""
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return {"ok": False, "error": "no credentials"}
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"{API_BASE}/report/integrated/get/",
                headers=_tk_headers(),
                params={
                    "advertiser_id": TK_ADVERTISER_ID,
                    "report_type": "BASIC",
                    "dimensions": '["stat_time_day"]',
                    "metrics": '["spend","clicks","impressions","conversion","cost_per_conversion"]',
                    "start_date": start_date,
                    "end_date": end_date,
                    "page_size": 10,
                },
            ) as r:
                data = await r.json()
        if data.get("code") == 0:
            rows = data.get("data", {}).get("list", [])
            total_spend = sum(float(r.get("metrics", {}).get("spend", 0)) for r in rows)
            total_clicks = sum(int(r.get("metrics", {}).get("clicks", 0)) for r in rows)
            total_conversions = sum(float(r.get("metrics", {}).get("conversion", 0)) for r in rows)
            return {
                "ok": True,
                "period_days": days,
                "total_spend": round(total_spend, 2),
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "cpc": round(total_spend / max(total_clicks, 1), 3),
            }
        log.warning("TikTok insights: %s", data.get("message", ""))
        return {"ok": False, "error": data.get("message", "unknown")}
    except Exception as e:
        log.warning("TikTok get_insights error: %s", e)
        return {"ok": False, "error": str(e)}


async def run_tiktok_ads_cycle(budget: float = 10.0) -> dict:
    """
    Main orchestrator: check for active campaigns,
    create one if none exist, then fetch insights.
    """
    if not TK_ACCESS_TOKEN or not TK_ADVERTISER_ID:
        return {"ok": False, "error": "TIKTOK_ACCESS_TOKEN or TIKTOK_ADVERTISER_ID not set"}

    campaigns = await get_campaigns()
    active = [c for c in campaigns if c.get("operation_status") == "ENABLE"]

    created_campaign = None
    if not active:
        log.info("No active TikTok campaigns — creating new one")
        result = await create_traffic_campaign(budget=budget)
        if result.get("ok"):
            campaign_id = result["campaign_id"]
            ag = await create_ad_group(campaign_id, budget=budget / 2)
            if ag.get("ok"):
                await create_ad(ag["adgroup_id"])
            created_campaign = campaign_id
        else:
            log.warning("TikTok campaign creation failed: %s", result.get("error"))

    insights = await get_insights(days=7)

    # Nur senden wenn aktive Kampagnen ODER neue erstellt ODER Umsatz > 0
    has_activity = (created_campaign or len(active) > 0
                    or float(insights.get("total_spend", 0)) > 0
                    or int(insights.get("total_conversions", 0)) > 0)
    if has_activity:
        msg = (
            f"📱 TikTok Ads Update\n"
            f"{'✅ Neue Kampagne erstellt: ' + str(created_campaign) if created_campaign else f'✅ {len(active)} aktive Kampagne(n)'}\n"
            f"📊 Letzte 7 Tage: €{insights.get('total_spend',0)} | "
            f"{insights.get('total_clicks',0)} Klicks | "
            f"{insights.get('total_conversions',0)} Conversions"
        )
        await _tg(msg)
    else:
        log.debug("TikTok Ads: 0 Aktivität — kein Telegram")

    return {
        "ok": True,
        "active_campaigns": len(active),
        "created_campaign": created_campaign,
        "insights": insights,
    }


async def get_tiktok_status() -> dict:
    """Return current TikTok Ads status."""
    campaigns = await get_campaigns()
    active = [c for c in campaigns if c.get("operation_status") == "ENABLE"]
    insights = await get_insights(days=7)
    return {
        "ok": True,
        "configured": bool(TK_ACCESS_TOKEN and TK_ADVERTISER_ID),
        "advertiser_id": TK_ADVERTISER_ID[:6] + "..." if TK_ADVERTISER_ID else "",
        "total_campaigns": len(campaigns),
        "active_campaigns": len(active),
        "insights_7d": insights,
    }
