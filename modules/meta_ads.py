"""Meta (Facebook + Instagram) Ads automation — campaigns, ad sets, creatives, pixel."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("MetaAds")

_API = "https://graph.facebook.com/v21.0"


def _token() -> str:
    return (
        os.getenv("META_ADS_TOKEN")
        or os.getenv("FACEBOOK_ACCESS_TOKEN")
        or os.getenv("META_USER_TOKEN")
        or os.getenv("FACEBOOK_USER_TOKEN")
        or ""
    )


def _ad_account() -> str:
    return os.getenv("META_AD_ACCOUNT_ID", "")


def _page_id() -> str:
    return os.getenv("FACEBOOK_PAGE_ID", "")


def _pixel_id() -> str:
    return os.getenv("FACEBOOK_PIXEL_ID", "")


async def _get(path: str, params: dict | None = None) -> dict:
    import aiohttp
    p = {"access_token": _token(), **(params or {})}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{_API}{path}", params=p) as r:
            return await r.json()


async def _post(path: str, data: dict) -> dict:
    import aiohttp
    data["access_token"] = _token()
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{_API}{path}", data=data) as r:
            return await r.json()


# ── Status ────────────────────────────────────────────────────────────────────

async def check_status() -> dict:
    token = _token()
    if not token:
        return {"status": "error", "message": "META_ADS_TOKEN not set"}
    acc = _ad_account()
    if not acc:
        return {"status": "error", "message": "META_AD_ACCOUNT_ID not set"}
    try:
        d = await _get(f"/{acc}", {"fields": "id,name,account_status,currency,amount_spent,balance"})
        if "error" in d:
            return {"status": "error", "message": d["error"].get("message", "?"), "needs_permission": "ads_management"}
        status_map = {1: "ACTIVE", 2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW", 9: "IN_GRACE_PERIOD"}
        return {
            "status": "ok",
            "account_id": d.get("id"),
            "name": d.get("name"),
            "account_status": status_map.get(d.get("account_status", 0), str(d.get("account_status"))),
            "currency": d.get("currency"),
            "amount_spent_eur": float(d.get("amount_spent", 0)) / 100,
            "balance": float(d.get("balance", 0)) / 100,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Campaigns ─────────────────────────────────────────────────────────────────

async def list_campaigns() -> list:
    acc = _ad_account()
    d = await _get(f"/{acc}/campaigns", {
        "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time,insights{spend,impressions,clicks,ctr,cpc}"
    })
    return d.get("data", [])


async def create_campaign(
    name: str,
    objective: str = "OUTCOME_SALES",
    daily_budget_eur: float = 10.0,
    status: str = "PAUSED",
) -> dict:
    """Create a campaign. Starts PAUSED by default for safety review."""
    acc = _ad_account()
    data = {
        "name": name,
        "objective": objective,
        "status": status,
        "daily_budget": int(daily_budget_eur * 100),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "special_ad_categories": "[]",
    }
    d = await _post(f"/{acc}/campaigns", data)
    if "error" in d:
        log.error("Campaign create error: %s", d["error"])
    else:
        log.info("Campaign created: %s (id=%s)", name, d.get("id"))
    return d


# ── Ad Sets ───────────────────────────────────────────────────────────────────

async def create_adset(
    campaign_id: str,
    name: str,
    daily_budget_eur: float = 5.0,
    countries: list[str] | None = None,
    age_min: int = 25,
    age_max: int = 55,
    genders: list[int] | None = None,
    interests: list[dict] | None = None,
    optimization_goal: str = "OFFSITE_CONVERSIONS",
    billing_event: str = "IMPRESSIONS",
    status: str = "PAUSED",
) -> dict:
    acc = _ad_account()
    countries = countries or ["DE", "AT", "CH"]
    targeting = {
        "age_min": age_min,
        "age_max": age_max,
        "geo_locations": {"countries": countries},
    }
    if genders:
        targeting["genders"] = genders
    if interests:
        targeting["flexible_spec"] = [{"interests": interests}]
    pixel = _pixel_id()
    data = {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": int(daily_budget_eur * 100),
        "billing_event": billing_event,
        "optimization_goal": optimization_goal,
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": json.dumps(targeting),
        "status": status,
        "start_time": "",
    }
    if pixel:
        data["promoted_object"] = json.dumps({
            "pixel_id": pixel,
            "custom_event_type": "PURCHASE",
        })
    d = await _post(f"/{acc}/adsets", data)
    if "error" in d:
        log.error("Ad set create error: %s", d["error"])
    else:
        log.info("Ad set created: %s (id=%s)", name, d.get("id"))
    return d


# ── Ad Creatives ──────────────────────────────────────────────────────────────

async def create_ad_creative(
    name: str,
    title: str,
    body: str,
    image_url: str,
    link_url: str,
    call_to_action: str = "SHOP_NOW",
) -> dict:
    acc = _ad_account()
    page_id = _page_id()
    object_story_spec = {
        "page_id": page_id,
        "link_data": {
            "image_hash": "",
            "link": link_url,
            "message": body,
            "name": title,
            "call_to_action": {"type": call_to_action, "value": {"link": link_url}},
        },
    }
    # Upload image first if URL provided
    if image_url:
        img_data = {"url": image_url, "access_token": _token()}
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{_API}/{acc}/adimages", data=img_data) as r:
                img_resp = await r.json()
        images = img_resp.get("images", {})
        if images:
            first_key = list(images.keys())[0]
            img_hash = images[first_key].get("hash", "")
            if img_hash:
                object_story_spec["link_data"]["image_hash"] = img_hash

    data = {
        "name": name,
        "object_story_spec": json.dumps(object_story_spec),
    }
    d = await _post(f"/{acc}/adcreatives", data)
    if "error" in d:
        log.error("Creative create error: %s", d["error"])
    return d


async def create_ad(
    adset_id: str,
    creative_id: str,
    name: str,
    status: str = "PAUSED",
) -> dict:
    acc = _ad_account()
    data = {
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": status,
    }
    return await _post(f"/{acc}/ads", data)


# ── Pixel ─────────────────────────────────────────────────────────────────────

async def get_pixel_stats() -> dict:
    pixel = _pixel_id()
    if not pixel:
        return {"error": "FACEBOOK_PIXEL_ID not set"}
    d = await _get(f"/{pixel}", {"fields": "id,name,last_fired_time,is_unavailable"})
    return d


async def get_pixel_events(days: int = 7) -> dict:
    pixel = _pixel_id()
    d = await _get(f"/{pixel}/stats", {"start_time": f"-{days*86400}", "aggregation": "event"})
    return d


# ── Full Campaign Launch ───────────────────────────────────────────────────────

async def launch_shopify_campaign(
    product_title: str,
    product_url: str,
    product_image: str,
    product_price: float,
    daily_budget_eur: float = 10.0,
    countries: list[str] | None = None,
) -> dict:
    """End-to-end: campaign + ad set + creative + ad from a Shopify product."""
    countries = countries or ["DE", "AT", "CH"]

    # 1. Campaign
    campaign = await create_campaign(
        name=f"SMB | {product_title[:40]} | Sales",
        objective="OUTCOME_SALES",
        daily_budget_eur=daily_budget_eur,
        status="PAUSED",
    )
    campaign_id = campaign.get("id")
    if not campaign_id:
        return {"ok": False, "error": "Campaign creation failed", "detail": campaign}

    # 2. Ad Set — DACH targeting
    adset = await create_adset(
        campaign_id=campaign_id,
        name=f"DACH 25-55 | {product_title[:30]}",
        daily_budget_eur=daily_budget_eur,
        countries=countries,
        age_min=25,
        age_max=55,
        optimization_goal="OFFSITE_CONVERSIONS",
        status="PAUSED",
    )
    adset_id = adset.get("id")
    if not adset_id:
        return {"ok": False, "error": "Ad set creation failed", "detail": adset, "campaign_id": campaign_id}

    # 3. Creative
    body_text = (
        f"🛍️ {product_title} — jetzt nur €{product_price:.2f}!\n"
        f"✅ Schnelle Lieferung · Zufriedenheitsgarantie\n"
        f"👉 Jetzt shoppen!"
    )
    creative = await create_ad_creative(
        name=f"Creative | {product_title[:40]}",
        title=product_title,
        body=body_text,
        image_url=product_image,
        link_url=product_url,
        call_to_action="SHOP_NOW",
    )
    creative_id = creative.get("id")
    if not creative_id:
        return {"ok": False, "error": "Creative creation failed", "detail": creative, "campaign_id": campaign_id, "adset_id": adset_id}

    # 4. Ad
    ad = await create_ad(
        adset_id=adset_id,
        creative_id=creative_id,
        name=f"Ad | {product_title[:40]}",
        status="PAUSED",
    )

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad.get("id"),
        "status": "PAUSED — activate in Meta Ads Manager",
        "product": product_title,
        "daily_budget_eur": daily_budget_eur,
        "targeting": f"DACH (DE/AT/CH), Age 25-55",
    }


async def launch_saas_campaign(daily_budget_eur: float = 20.0) -> dict:
    """Launch a SaaS subscription campaign for SuperMegaBot plans."""
    import os
    shop_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "your-store.myshopify.com")

    campaign = await create_campaign(
        name="SMB | SaaS Subscription | Lead Gen",
        objective="OUTCOME_LEADS",
        daily_budget_eur=daily_budget_eur,
        status="PAUSED",
    )
    campaign_id = campaign.get("id")
    if not campaign_id:
        return {"ok": False, "error": campaign}

    # Shopify Store Owners targeting
    interests = [
        {"id": "6003716139471", "name": "Shopify"},
        {"id": "6003348604647", "name": "E-commerce"},
        {"id": "6002925298879", "name": "Dropshipping"},
    ]
    adset = await create_adset(
        campaign_id=campaign_id,
        name="Shopify Store Owners DE/AT/CH | 25-55",
        daily_budget_eur=daily_budget_eur,
        countries=["DE", "AT", "CH"],
        age_min=25,
        age_max=55,
        interests=interests,
        optimization_goal="LEAD_GENERATION",
        status="PAUSED",
    )
    adset_id = adset.get("id")

    creative = await create_ad_creative(
        name="Creative | SaaS | SuperMegaBot",
        title="KI-Automation für deinen Shopify-Shop",
        body=(
            "🤖 SuperMegaBot automatisiert deinen E-Commerce-Shop komplett.\n"
            "✅ Shopify Sync · Dynamic Pricing · AI-Content · Email-Automation\n"
            "🚀 Starte für nur €49/Monat — 30 Tage Geld-zurück-Garantie"
        ),
        image_url="",
        link_url=f"https://{shop_domain}",
        call_to_action="LEARN_MORE",
    )
    creative_id = creative.get("id")

    ad = None
    if adset_id and creative_id:
        ad = await create_ad(
            adset_id=adset_id,
            creative_id=creative_id,
            name="Ad | SaaS | SuperMegaBot",
            status="PAUSED",
        )

    return {
        "ok": bool(campaign_id),
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad.get("id") if ad else None,
        "targeting": "Shopify Store Owners, DACH, 25-55",
        "daily_budget_eur": daily_budget_eur,
        "status": "PAUSED",
    }
