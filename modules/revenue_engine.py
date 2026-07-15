"""
Revenue Engine — nur Aktionen die Geld bringen.

Fokus: Eigene DS24-Produkte (669750 €37) → Traffic → Klaviyo → Kauf.
Kein SEO-Spam, kein 19k-Produkt-Import, kein Vanity-Posting.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("RevenueEngine")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "revenue_engine.json"

# 100% Erlös — eigene Produkte
OWN_PRODUCTS: List[Dict[str, str]] = [
    {
        "id": "669750",
        "name": "AI Income Machine – 90-Day Blueprint",
        "url": os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/669750"),
        "price": "€37",
        "niche": "ai",
    },
    # 704677 DEAKTIVIERT — DS24 Genehmigung ausstehend
]

META_BUDGET_EUR = float(os.getenv("META_DAILY_BUDGET_EUR", "5"))


def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


async def get_monthly_revenue() -> Dict[str, Any]:
    """Echter Monatsumsatz — DS24 + Shopify + Stripe."""
    month_eur = 0.0
    breakdown: Dict[str, float] = {}

    try:
        from modules.digistore24_automation import get_sales_stats
        ds = await get_sales_stats()
        breakdown["ds24"] = float(ds.get("month", 0))
        month_eur += breakdown["ds24"]
    except Exception as e:
        log.warning("DS24: %s", e)
        breakdown["ds24"] = 0.0

    try:
        from modules.stripe_client import get_revenue_stats
        st = await get_revenue_stats()
        breakdown["stripe"] = float(st.get("month_revenue", st.get("today_revenue", 0)))
        month_eur += breakdown["stripe"]
    except Exception as e:
        log.warning("Stripe: %s", e)
        breakdown["stripe"] = 0.0

    try:
        from modules.shopify_client import get_analytics_summary
        sh = await get_analytics_summary()
        breakdown["shopify"] = float(sh.get("revenue_month", sh.get("revenue", 0)))
        month_eur += breakdown["shopify"]
    except Exception as e:
        log.warning("Shopify: %s", e)
        breakdown["shopify"] = 0.0

    target = float(os.getenv("SCALING_TARGET_EUR", "1000"))
    return {
        "month_eur": round(month_eur, 2),
        "target_eur": target,
        "progress_pct": round(min(100.0, month_eur / target * 100), 1) if target else 0,
        "breakdown": breakdown,
        "month": datetime.now(timezone.utc).strftime("%Y-%m"),
    }


async def _step_ds24_buyers() -> Dict[str, Any]:
    """Neue DS24-Käufer → Klaviyo + Email-Sequenz."""
    from modules.ds24_funnel_automation import run_sync, run_funnel
    sync = await run_sync()
    funnel = await run_funnel()
    return {
        "ok": True,
        "new_buyers": sync.get("new_buyers", 0),
        "sync": sync,
        "funnel": funnel,
    }


async def _step_blast_own_products() -> Dict[str, Any]:
    """Eigene DS24-Produkte auf Telegram/Reddit/Klaviyo — kein Fremd-Spam."""
    from modules.ds24_affiliate_blaster import blast_all_approved
    r = await blast_all_approved(delay=3.0)
    return {
        "ok": True,
        "blasted": r.get("blasted", 0),
        "reason": r.get("reason", ""),
        "products": [p["id"] for p in OWN_PRODUCTS],
    }


async def _step_klaviyo_checkout() -> Dict[str, Any]:
    """Klaviyo Checkout-Flow für eigene Produkte an alle Subscriber."""
    from modules.klaviyo_automation import send_checkout_flow
    offers = [
        {"name": p["name"], "url": p["url"], "price": p["price"], "id": p["id"]}
        for p in OWN_PRODUCTS
    ]
    r = await send_checkout_flow(offers, max_profiles=100, send_email=True)
    return {"ok": r.get("ok", False), **r}


async def _step_cart_recovery() -> Dict[str, Any]:
    """Abandoned Cart + Flash-Sales."""
    results: Dict[str, Any] = {}
    try:
        from modules.abandoned_cart_recovery import run_abandoned_cart_recovery
        results["cart"] = await run_abandoned_cart_recovery()
    except Exception as e:
        results["cart"] = str(e)
    try:
        from modules.revenue_fast_track import run_revenue_fast_track
        results["fast_track"] = await run_revenue_fast_track()
    except Exception as e:
        results["fast_track"] = {"error": str(e)}
    return {"ok": True, **results}


async def _step_meta_ads() -> Dict[str, Any]:
    """Meta Ads auf DS24-Landing — nur wenn Credentials + Opt-in."""
    if not os.getenv("META_AD_ACCOUNT_ID") or not os.getenv("META_ACCESS_TOKEN"):
        return {"ok": False, "skipped": True, "reason": "META credentials fehlen"}

    from modules.ads_engine import create_facebook_ad_campaign
    product = OWN_PRODUCTS[0]  # AI Income Machine €37 — einziges aktives Produkt
    r = await create_facebook_ad_campaign(
        {"name": product["name"], "url": product["url"]},
        budget_eur=META_BUDGET_EUR,
    )

    auto = os.getenv("META_ADS_AUTO_ACTIVATE", "").lower() in ("1", "true", "yes")
    if auto and r.get("campaign_id") and not r.get("skipped"):
        try:
            import aiohttp
            token = os.getenv("META_ACCESS_TOKEN", "")
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://graph.facebook.com/v18.0/{r['campaign_id']}",
                    params={"access_token": token, "status": "ACTIVE"},
                )
            r["status"] = "ACTIVE"
        except Exception as e:
            r["activate_error"] = str(e)[:120]

    return {"ok": not r.get("skipped"), **r}


async def run_revenue_cycle() -> Dict[str, Any]:
    """Geld-Zyklus — 5 Schritte, parallel wo möglich."""
    log.info("Revenue Engine START")
    state = _load_state()
    revenue = await get_monthly_revenue()

    buyers, blast, klaviyo, cart, ads = await asyncio.gather(
        _step_ds24_buyers(),
        _step_blast_own_products(),
        _step_klaviyo_checkout(),
        _step_cart_recovery(),
        _step_meta_ads(),
        return_exceptions=True,
    )

    def _norm(r: Any, name: str) -> Dict[str, Any]:
        if isinstance(r, Exception):
            return {"ok": False, "error": str(r)}
        return r if isinstance(r, dict) else {"ok": False, "error": f"{name}: unexpected"}

    result = {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "revenue": revenue,
        "mode": "revenue_first",
        "steps": {
            "1_ds24_buyers": _norm(buyers, "buyers"),
            "2_blast_own": _norm(blast, "blast"),
            "3_klaviyo_checkout": _norm(klaviyo, "klaviyo"),
            "4_cart_recovery": _norm(cart, "cart"),
            "5_meta_ads": _norm(ads, "ads"),
        },
    }

    state["last_cycle"] = result
    state["cycles_total"] = int(state.get("cycles_total", 0)) + 1
    state["last_run"] = result["timestamp"]
    _save_state(state)

    rev = revenue
    blast_n = result["steps"]["2_blast_own"].get("blasted", 0)
    klav_n = result["steps"]["3_klaviyo_checkout"].get("events_sent", 0)
    buyers_n = result["steps"]["1_ds24_buyers"].get("new_buyers", 0)

    try:
        from modules.notify_hub import async_send_telegram
        await async_send_telegram(
            f"💰 Revenue-Zyklus\n"
            f"Monat: €{rev['month_eur']:.2f}\n"
            f"DS24 Käufer: {buyers_n} | Blast: {blast_n} | Klaviyo: {klav_n} Events"
        )
    except Exception:
        pass

    log.info("Revenue Engine DONE — €%.2f/Monat", rev["month_eur"])
    return result


async def get_revenue_status() -> Dict[str, Any]:
    state = _load_state()
    revenue = await get_monthly_revenue()
    return {
        "ok": True,
        "mode": "revenue_first",
        "revenue": revenue,
        "own_products": OWN_PRODUCTS,
        "automation": {
            "enabled": os.getenv("REVENUE_MODE", "false").lower() in ("true", "1", "on"),
            "interval_hours": 2,
            "cycles_total": state.get("cycles_total", 0),
            "last_run": state.get("last_run"),
            "meta_auto_activate": os.getenv("META_ADS_AUTO_ACTIVATE", "false"),
            "meta_daily_budget_eur": META_BUDGET_EUR,
        },
        "last_cycle": state.get("last_cycle"),
        "focus": "DS24 eigene Produkte → Klaviyo → Meta Ads",
    }


async def run_revenue_cycle_str() -> str:
    if os.getenv("REVENUE_MODE", "false").lower() not in ("true", "1", "on"):
        return "Revenue Engine: deaktiviert (REVENUE_MODE nicht gesetzt)"
    r = await run_revenue_cycle()
    rev = r.get("revenue", {})
    blast = r.get("steps", {}).get("2_blast_own", {})
    return (
        f"Revenue: €{rev.get('month_eur', 0):.2f} | "
        f"Blast {blast.get('blasted', 0)} | "
        f"Klaviyo {r.get('steps', {}).get('3_klaviyo_checkout', {}).get('events_sent', 0)}"
    )