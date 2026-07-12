#!/usr/bin/env python3
"""
Geldmaschine Skalierung — vollautomatischer Plan zu €10.000/Monat.

5 Strategien (Scheduler alle 4h):
  1. Retargeting Budget skalieren (Meta Ads)
  2. Solar + Smart Home Produkte hochladen
  3. Klaviyo/Mailchimp Flows + DS24 Upsell-Funnel
  4. UGC-Videos + A/B-Tests
  5. Checkout-Optimierung (CRO + Abandoned Cart)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("GeldmaschineSkalierung")

TARGET_MONTHLY_EUR = float(os.getenv("SCALING_TARGET_EUR", "10000"))
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "geldmaschine_skalierung.json"
SCALING_NICHES = frozenset({"smart_home"})
SCALING_KEYWORDS = ("solar",)
PRODUCTS_PER_CYCLE = int(os.getenv("SCALING_PRODUCTS_PER_CYCLE", "25"))
MONTHLY_PRODUCT_CAP = int(os.getenv("SCALING_MONTHLY_PRODUCT_CAP", "100"))


def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _get_monthly_revenue() -> Dict[str, Any]:
    """Echter Monatsumsatz aus DS24 + Shopify + Stripe."""
    month_eur = 0.0
    breakdown: Dict[str, float] = {}

    try:
        from modules.digistore24_automation import get_sales_stats
        ds = await get_sales_stats()
        breakdown["ds24"] = float(ds.get("month", 0))
        month_eur += breakdown["ds24"]
    except Exception as e:
        log.warning("DS24 stats: %s", e)
        breakdown["ds24"] = 0.0

    try:
        from modules.stripe_client import get_revenue_stats
        st = await get_revenue_stats()
        # Stripe client returns today; use month if available
        stripe_month = float(st.get("month_revenue", st.get("today_revenue", 0)))
        breakdown["stripe"] = stripe_month
        month_eur += stripe_month
    except Exception as e:
        log.warning("Stripe stats: %s", e)
        breakdown["stripe"] = 0.0

    try:
        from modules.shopify_client import get_analytics_summary
        sh = await get_analytics_summary()
        shopify_month = float(sh.get("revenue_month", sh.get("revenue", 0)))
        breakdown["shopify"] = shopify_month
        month_eur += shopify_month
    except Exception as e:
        log.warning("Shopify stats: %s", e)
        breakdown["shopify"] = 0.0

    return {
        "month_eur": round(month_eur, 2),
        "target_eur": TARGET_MONTHLY_EUR,
        "progress_pct": round(min(100.0, month_eur / TARGET_MONTHLY_EUR * 100), 1) if TARGET_MONTHLY_EUR else 0,
        "breakdown": breakdown,
        "month": _month_key(),
    }


async def _step_retargeting() -> Dict[str, Any]:
    """Strategie 1: Retargeting-Kampagnen für alle Segmente."""
    from modules.ads_engine import create_retargeting_campaign, monitor_ad_performance

    segments = ["visitors", "cart_abandoners", "product_viewers"]
    campaigns = []
    for seg in segments:
        try:
            r = await create_retargeting_campaign(segment=seg)
            campaigns.append({"segment": seg, **r})
        except Exception as e:
            campaigns.append({"segment": seg, "error": str(e)})

    perf = {}
    try:
        perf = await monitor_ad_performance()
    except Exception as e:
        perf = {"error": str(e)}

    created = sum(1 for c in campaigns if c.get("campaign_id"))
    skipped = all(c.get("skipped") for c in campaigns if "skipped" in c)
    return {"ok": not skipped or created > 0, "campaigns": campaigns, "performance": perf, "created": created}


async def _step_products(state: Dict[str, Any]) -> Dict[str, Any]:
    """Strategie 2: Solar + Smart Home Produkte (max 100/Monat)."""
    month = _month_key()
    monthly = state.get("products_by_month", {})
    already = int(monthly.get(month, 0))
    remaining = max(0, MONTHLY_PRODUCT_CAP - already)
    if remaining == 0:
        return {"ok": True, "skipped": True, "reason": f"Monatslimit {MONTHLY_PRODUCT_CAP} erreicht"}

    count = min(PRODUCTS_PER_CYCLE, remaining)
    from modules.shopify_mass_creator import mass_create_shopify_products, blast_shopify_products

    create_r = await mass_create_shopify_products(
        count=count,
        workers=3,
        niches=list(SCALING_NICHES),
        keywords=list(SCALING_KEYWORDS),
    )
    blast_r = await blast_shopify_products(limit=5)
    created = int(create_r.get("created", 0))
    monthly[month] = already + created
    state["products_by_month"] = monthly
    return {
        "ok": True,
        "created": created,
        "blasted": blast_r.get("blasted", 0),
        "monthly_total": monthly[month],
        "monthly_cap": MONTHLY_PRODUCT_CAP,
    }


async def _step_crm_flows() -> Dict[str, Any]:
    """Strategie 3: Klaviyo/Mailchimp + DS24 Upsell-Funnel."""
    results: Dict[str, Any] = {}

    try:
        from modules.ds24_funnel_automation import run_sync
        results["ds24_sync"] = await run_sync()
    except Exception as e:
        results["ds24_sync"] = {"error": str(e)}

    try:
        from modules.auto_sorter import create_klaviyo_segments
        results["klaviyo_segments"] = await create_klaviyo_segments()
    except Exception as e:
        results["klaviyo_segments"] = {"error": str(e)}

    try:
        from modules.mailchimp_autonomy import run_mailchimp_cycle
        results["mailchimp"] = await run_mailchimp_cycle()
    except Exception as e:
        results["mailchimp"] = {"error": str(e)}

    try:
        from modules.ds24_funnel_automation import run_funnel
        results["ds24_funnel"] = await run_funnel()
    except Exception as e:
        results["ds24_funnel"] = {"error": str(e)}

    ok = any(
        isinstance(v, dict) and (v.get("ok") or v.get("new_buyers", 0) > 0)
        for v in results.values()
    )
    return {"ok": ok, **results}


async def _step_ugc_ab() -> Dict[str, Any]:
    """Strategie 4: UGC-Videos + A/B-Tests."""
    results: Dict[str, Any] = {}

    try:
        from modules.conversion_engine import run_conversion_scan, run_daily_optimization
        results["ab_scan"] = await run_conversion_scan()
        results["daily_opt"] = await run_daily_optimization()
    except Exception as e:
        results["conversion"] = {"error": str(e)}

    try:
        from modules.youtube_autonomy import run_youtube_cycle
        results["youtube"] = await run_youtube_cycle()
    except Exception as e:
        results["youtube"] = {"error": str(e)}

    try:
        from modules.content_factory import find_trending_topics, generate_content_package
        topics = await find_trending_topics("solar smart home ecommerce")
        topic = topics[0]["topic"] if topics else "Smart Home Solar Produkte 2026"
        results["content"] = await generate_content_package(topic)
    except Exception as e:
        results["content"] = {"error": str(e)}

    return {"ok": True, **results}


async def _step_checkout() -> Dict[str, Any]:
    """Strategie 5: Checkout-Blast + Express + Cart Recovery."""
    results: Dict[str, Any] = {}

    try:
        from modules.cro_engine import run_cro
        results["cro"] = await run_cro()
    except Exception as e:
        results["cro"] = {"error": str(e)}

    try:
        from modules.abandoned_cart_recovery import run_abandoned_cart_recovery
        results["cart_recovery"] = await run_abandoned_cart_recovery()
    except Exception as e:
        results["cart_recovery"] = {"error": str(e)}

    try:
        from modules.revenue_fast_track import run_revenue_fast_track
        results["fast_track"] = await run_revenue_fast_track()
    except Exception as e:
        results["fast_track"] = {"error": str(e)}

    return {"ok": True, **results}


async def run_scaling_cycle() -> Dict[str, Any]:
    """Vollständiger Skalierungs-Zyklus — alle 5 Strategien parallel wo möglich."""
    log.info("Geldmaschine Skalierung START — Ziel €%.0f/Monat", TARGET_MONTHLY_EUR)
    state = _load_state()
    revenue_before = await _get_monthly_revenue()

    retargeting, products, crm, ugc, checkout = await asyncio.gather(
        _step_retargeting(),
        _step_products(state),
        _step_crm_flows(),
        _step_ugc_ab(),
        _step_checkout(),
        return_exceptions=True,
    )

    def _norm(r: Any, name: str) -> Dict[str, Any]:
        if isinstance(r, Exception):
            return {"ok": False, "error": str(r)}
        return r if isinstance(r, dict) else {"ok": False, "error": f"{name}: unexpected result"}

    result = {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "revenue": revenue_before,
        "strategies": {
            "1_retargeting": _norm(retargeting, "retargeting"),
            "2_products": _norm(products, "products"),
            "3_crm_flows": _norm(crm, "crm"),
            "4_ugc_ab": _norm(ugc, "ugc"),
            "5_checkout": _norm(checkout, "checkout"),
        },
    }

    state["last_cycle"] = result
    state["cycles_total"] = int(state.get("cycles_total", 0)) + 1
    state["last_run"] = result["timestamp"]
    _save_state(state)

    try:
        from modules.brutus_core import fire
        rev = revenue_before
        await fire(
            "💰 Geldmaschine Skalierung — Zyklus abgeschlossen",
            f"Monat: €{rev['month_eur']:.2f} / €{rev['target_eur']:.0f} ({rev['progress_pct']}%)\n"
            f"Retargeting: {result['strategies']['1_retargeting'].get('created', 0)} Kampagnen\n"
            f"Produkte: +{result['strategies']['2_products'].get('created', 0)}\n"
            f"DS24 Sync: {result['strategies']['3_crm_flows'].get('ds24_sync', {}).get('new_buyers', 0)} neue Käufer",
            channels=["telegram"],
        )
    except Exception as e:
        log.debug("Telegram notify skip: %s", e)

    log.info("Geldmaschine Skalierung DONE — €%.2f / €%.0f", revenue_before["month_eur"], TARGET_MONTHLY_EUR)
    return result


async def get_scaling_status() -> Dict[str, Any]:
    """Status für Dashboard/API — echte Revenue-Daten."""
    state = _load_state()
    revenue = await _get_monthly_revenue()
    return {
        "ok": True,
        "target_monthly_eur": TARGET_MONTHLY_EUR,
        "revenue": revenue,
        "automation": {
            "enabled": os.getenv("GELDMASCHINE_SKALIERUNG_ENABLED", "true").lower() not in ("false", "0", "off"),
            "interval_hours": 4,
            "products_per_cycle": PRODUCTS_PER_CYCLE,
            "monthly_product_cap": MONTHLY_PRODUCT_CAP,
            "cycles_total": state.get("cycles_total", 0),
            "last_run": state.get("last_run"),
        },
        "last_cycle": state.get("last_cycle"),
        "products_by_month": state.get("products_by_month", {}),
    }


async def run_scaling_cycle_str() -> str:
    """Scheduler-Wrapper."""
    if os.getenv("GELDMASCHINE_SKALIERUNG_ENABLED", "true").lower() in ("false", "0", "off"):
        return "Geldmaschine Skalierung: deaktiviert"
    r = await run_scaling_cycle()
    rev = r.get("revenue", {})
    prod = r.get("strategies", {}).get("2_products", {})
    return (
        f"Skalierung: €{rev.get('month_eur', 0):.2f}/{rev.get('target_eur', 0):.0f} "
        f"({rev.get('progress_pct', 0)}%) | +{prod.get('created', 0)} Produkte"
    )