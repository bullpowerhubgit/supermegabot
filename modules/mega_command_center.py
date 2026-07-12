#!/usr/bin/env python3
"""
BullPower MEGA Command Center — Master-Orchestrator für alle Revenue-Systeme.

Verbindet: Umsatzmaschine · Revenue Engine · Shopify Blog · Social Auto-Post
           Buyer Traffic · DS24 · Klaviyo · Money Machine · Email Brain
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("MegaCommandCenter")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "mega_command_center.json"
MEGA_INTERVAL_S = int(os.getenv("MEGA_INTERVAL_S", "14400"))  # 4h
_CYCLE_LOCK = asyncio.Lock()


def _load_state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


async def _safe(coro, name: str) -> Dict[str, Any]:
    try:
        r = await coro
        return r if isinstance(r, dict) else {"ok": True, "result": str(r)[:200]}
    except Exception as e:
        log.warning("%s: %s", name, e)
        return {"ok": False, "error": str(e)[:160]}


async def _step_umsatzmaschine() -> Dict[str, Any]:
    from modules.megabot_umsatzmaschine import run_autonomous_cycle
    return await run_autonomous_cycle()


async def _step_money_machine() -> Dict[str, Any]:
    from modules.money_machine import run_all_engines
    return await run_all_engines()


async def _step_buyer_traffic() -> Dict[str, Any]:
    from modules.buyer_traffic_engine import run_buyer_traffic_cycle
    return await run_buyer_traffic_cycle()


async def _step_shopify_blog() -> Dict[str, Any]:
    from modules.shopify_blog_auto import publish_one_article
    return await publish_one_article()


async def _step_social_post() -> Dict[str, Any]:
    from modules.dropshipping_automation import DropshippingWorkflow
    wf = DropshippingWorkflow()
    products = await wf.find_trending_products(limit=3)
    posted = 0
    results: List[Dict] = []
    for p in products[:2]:
        r = await wf.promote_to_social(p)
        posted += sum(1 for v in r.values() if isinstance(v, dict) and v.get("ok"))
        results.append(r)
    return {"ok": posted > 0, "posts": posted, "products": len(products), "details": results}


async def _step_klaviyo() -> Dict[str, Any]:
    from modules.klaviyo_automation import run_with_brutus_traffic
    return await run_with_brutus_traffic()


async def _step_ds24() -> Dict[str, Any]:
    from modules.ds24_affiliate_blaster import run_daily_affiliate_blast
    return await run_daily_affiliate_blast()


async def _step_email_daily() -> Dict[str, Any]:
    from modules.email_blast_engine import run_daily_blast
    return await run_daily_blast()


async def _step_indexnow() -> Dict[str, Any]:
    from modules.traffic_blitz import indexnow_blast
    return await indexnow_blast()


async def _step_email_brain() -> Dict[str, Any]:
    from modules.email_brain import check_and_process_emails
    return await check_and_process_emails()


async def _step_revenue_only() -> Dict[str, Any]:
    from modules.revenue_engine import run_revenue_cycle
    return await run_revenue_cycle()


async def run_mega_cycle(steps: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Vollständiger MEGA-Zyklus — alle Geld- und Traffic-Systeme.
    steps: optional subset — default = alles
    """
    if os.getenv("MEGA_AUTONOMOUS", "true").lower() in ("false", "0", "off"):
        return {"ok": False, "skipped": True, "reason": "MEGA_AUTONOMOUS=off"}

    if _CYCLE_LOCK.locked():
        return {"ok": True, "skipped": True, "reason": "cycle_already_running"}

    async with _CYCLE_LOCK:
        return await _run_mega_cycle_inner(steps)


async def _run_mega_cycle_inner(steps: Optional[List[str]] = None) -> Dict[str, Any]:
    log.info("═══ MEGA Command Center START ═══")
    state = _load_state()
    all_steps = {
        "umsatzmaschine": _step_umsatzmaschine(),
        "money_machine": _step_money_machine(),
        "buyer_traffic": _step_buyer_traffic(),
        "shopify_blog": _step_shopify_blog(),
        "social_post": _step_social_post(),
        "klaviyo": _step_klaviyo(),
        "ds24": _step_ds24(),
        "email_blast": _step_email_daily(),
        "indexnow": _step_indexnow(),
        "email_brain": _step_email_brain(),
    }
    selected = {k: v for k, v in all_steps.items() if not steps or k in steps}
    names = list(selected.keys())
    results_raw = await asyncio.gather(*selected.values(), return_exceptions=True)

    steps_out: Dict[str, Any] = {}
    ok_count = 0
    for name, raw in zip(names, results_raw):
        if isinstance(raw, Exception):
            steps_out[name] = {"ok": False, "error": str(raw)[:160]}
        else:
            steps_out[name] = raw if isinstance(raw, dict) else {"ok": True, "result": str(raw)[:120]}
            if steps_out[name].get("ok") is not False and not steps_out[name].get("skipped"):
                ok_count += 1

    revenue = await _safe(_step_revenue_only(), "revenue_snapshot")
    try:
        from modules.revenue_engine import get_monthly_revenue
        rev = await get_monthly_revenue()
    except Exception as e:
        rev = {"error": str(e)[:80]}

    result = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "mode": "mega_command_center",
        "steps_ok": ok_count,
        "steps_total": len(names),
        "steps": steps_out,
        "revenue": rev,
        "revenue_cycle": revenue,
    }

    state["last_run"] = result["timestamp"]
    state["cycles_total"] = int(state.get("cycles_total", 0)) + 1
    state["last_result"] = {
        "steps_ok": ok_count,
        "month_eur": rev.get("month_eur", 0),
        "progress_pct": rev.get("progress_pct", 0),
    }
    _save_state(state)

    try:
        from modules.notify_hub import async_send_telegram
        await async_send_telegram(
            f"⚡ MEGA Command Center\n"
            f"✅ {ok_count}/{len(names)} Systeme OK\n"
            f"💰 Monat: €{rev.get('month_eur', 0):.0f} ({rev.get('progress_pct', 0)}% Ziel)\n"
            f"Blog: {'✅' if steps_out.get('shopify_blog', {}).get('ok') else '—'} | "
            f"Social: {steps_out.get('social_post', {}).get('posts', 0)} Posts | "
            f"Traffic: {steps_out.get('buyer_traffic', {}).get('total_actions', 0)} Aktionen"
        )
    except Exception:
        pass

    log.info("MEGA Command Center DONE — %d/%d OK | €%.0f/Monat",
             ok_count, len(names), float(rev.get("month_eur", 0)))
    return result


async def run_daily_cycle() -> Dict[str, Any]:
    """Täglicher Fokus: Content + Traffic + Geld."""
    return await run_mega_cycle([
        "umsatzmaschine", "buyer_traffic", "shopify_blog",
        "social_post", "klaviyo", "ds24", "email_blast", "indexnow",
    ])


async def run_autonomous_loop() -> None:
    await asyncio.sleep(int(os.getenv("MEGA_BOOT_DELAY_S", "120")))
    log.info("MEGA Command Center loop gestartet (alle %ds)", MEGA_INTERVAL_S)
    while True:
        try:
            await run_mega_cycle()
        except Exception as e:
            log.error("MEGA cycle Fehler: %s", e)
        await asyncio.sleep(MEGA_INTERVAL_S)


def get_status() -> Dict[str, Any]:
    state = _load_state()
    autonomous = os.getenv("MEGA_AUTONOMOUS", "true").lower() not in ("false", "0", "off")
    return {
        "ok": True,
        "autonomous": autonomous,
        "interval_hours": MEGA_INTERVAL_S / 3600,
        "last_run": state.get("last_run"),
        "cycles_total": state.get("cycles_total", 0),
        "last_result": state.get("last_result", {}),
        "systems": [
            "umsatzmaschine", "money_machine", "buyer_traffic", "shopify_blog",
            "social_post", "klaviyo", "ds24", "email_blast", "indexnow", "email_brain",
        ],
    }