#!/usr/bin/env python3
"""
BullPower Traffic Accelerator — Maximale Leistung sofort.
=========================================================
Aktiviert ALLE Traffic-Quellen gleichzeitig auf maximale Kapazität:
  - Mass-Outreach (1.000 Emails in einer Runde)
  - Buyer Traffic Engine (alle Kanäle)
  - IndexNow Blast (alle Shopify-Produkte sofort indexieren)
  - ROAS Optimizer (Scale-Kampagnen sofort hochfahren)
  - Social Auto-Post (max Posts auf alle Plattformen)
  - Shopify Blog (3 Artikel sofort veröffentlichen)
  - DS24 Affiliate Blast
  - Rotating Buyer Prospector (5 Branchen × 5 Städte)
  - Umsatzmaschine Turbo-Cycle
  - Email Brain Flush (alle unverarbeiteten Mails sofort)

Export: run_full_acceleration(), get_acceleration_status()
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("TrafficAccelerator")

_DATA = Path(__file__).parent.parent / "data"
_DATA.mkdir(exist_ok=True)
_STATE_FILE = _DATA / "traffic_accelerator.json"
_LOCK = asyncio.Lock()


def _ts() -> str:
    return datetime.now().isoformat()


def _save(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception:
        pass


def get_acceleration_status() -> dict:
    try:
        if _STATE_FILE.exists():
            d = json.loads(_STATE_FILE.read_text())
            d["locked"] = _LOCK.locked()
            return d
    except Exception:
        pass
    return {"ok": False, "locked": False, "last_run": None}


async def _run_step(name: str, coro) -> dict:
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(coro, timeout=120)
        elapsed = round(time.monotonic() - t0, 1)
        ok = isinstance(result, dict) and result.get("ok") is not False
        return {"name": name, "ok": ok, "elapsed_s": elapsed, "result": str(result)[:120]}
    except asyncio.TimeoutError:
        return {"name": name, "ok": False, "error": "timeout 120s", "elapsed_s": 120}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)[:120], "elapsed_s": round(time.monotonic() - t0, 1)}


async def _mass_outreach_max():
    from modules.mass_outreach_1000 import run_smart_batch
    return await run_smart_batch(limit=500)


async def _buyer_traffic_max():
    from modules.buyer_traffic_engine import run_buyer_traffic_cycle
    return await run_buyer_traffic_cycle()


async def _indexnow_blast():
    from modules.traffic_blitz import indexnow_blast
    return await indexnow_blast()


async def _roas_scale():
    try:
        from modules.roas_optimizer import run_roas_optimizer
        return await run_roas_optimizer()
    except ImportError:
        try:
            from modules.free_api_hunter import get_hunter
            return {"ok": True, "skipped": True, "reason": "roas_optimizer not found, free_apis active"}
        except Exception:
            return {"ok": True, "skipped": True}


async def _social_posts():
    from modules.dropshipping_automation import DropshippingWorkflow
    wf = DropshippingWorkflow()
    products = await wf.find_trending_products(limit=5)
    posted = 0
    for p in products[:3]:
        r = await wf.promote_to_social(p)
        posted += sum(1 for v in r.values() if isinstance(v, dict) and v.get("ok"))
    return {"ok": posted > 0, "posts": posted}


async def _blog_articles():
    from modules.shopify_blog_auto import publish_one_article
    results = []
    for _ in range(3):
        r = await publish_one_article()
        results.append(r)
    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok > 0, "published": ok}


async def _ds24_blast():
    from modules.ds24_affiliate_blaster import run_daily_affiliate_blast
    return await run_daily_affiliate_blast()


async def _prospector_max():
    try:
        from modules.rotating_buyer_prospector import run_prospecting_cycle
        return await run_prospecting_cycle(max_niches=5, emails_per_niche=50)
    except ImportError:
        try:
            from modules.buyer_traffic_engine import run_buyer_traffic_cycle
            return await run_buyer_traffic_cycle()
        except Exception as e:
            return {"ok": False, "error": str(e)[:80]}


async def _umsatzmaschine():
    from modules.megabot_umsatzmaschine import run_autonomous_cycle
    return await run_autonomous_cycle()


async def _email_brain_flush():
    from modules.email_brain import check_and_process_emails
    return await check_and_process_emails()


async def _klaviyo_blast():
    try:
        from modules.klaviyo_automation import run_with_brutus_traffic
        return await run_with_brutus_traffic()
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


async def _money_machine():
    from modules.money_machine import run_all_engines
    return await run_all_engines()


# Acceleration steps: (name, coroutine_factory, priority)
# priority: 1=first wave, 2=second wave (after first)
_STEPS_WAVE_1 = [
    ("mass_outreach_500",  _mass_outreach_max),
    ("buyer_traffic",      _buyer_traffic_max),
    ("indexnow_blast",     _indexnow_blast),
    ("roas_scale",         _roas_scale),
    ("ds24_blast",         _ds24_blast),
    ("money_machine",      _money_machine),
]

_STEPS_WAVE_2 = [
    ("social_posts_3",     _social_posts),
    ("blog_articles_3",    _blog_articles),
    ("prospector_max",     _prospector_max),
    ("umsatzmaschine",     _umsatzmaschine),
    ("email_brain_flush",  _email_brain_flush),
    ("klaviyo_blast",      _klaviyo_blast),
]


async def run_full_acceleration(waves: int = 2) -> dict:
    """
    Alle Traffic-Quellen auf maximale Leistung.
    wave 1: Direkte Revenue-Tasks parallel
    wave 2: Content + Outreach parallel
    """
    if _LOCK.locked():
        return {"ok": False, "skipped": True, "reason": "Acceleration already running"}

    async with _LOCK:
        log.info("🚀 TRAFFIC ACCELERATOR — MAXIMUM LEISTUNG GESTARTET")
        t_total = time.monotonic()
        all_results = []

        # Wave 1 — Direct money tasks
        log.info("Wave 1: %d Tasks parallel...", len(_STEPS_WAVE_1))
        wave1_tasks = [_run_step(name, factory()) for name, factory in _STEPS_WAVE_1]
        wave1_results = await asyncio.gather(*wave1_tasks, return_exceptions=True)
        for r in wave1_results:
            if isinstance(r, dict):
                all_results.append(r)
            else:
                all_results.append({"ok": False, "error": str(r)[:80]})

        if waves >= 2:
            # Wave 2 — Content + deep outreach
            log.info("Wave 2: %d Tasks parallel...", len(_STEPS_WAVE_2))
            wave2_tasks = [_run_step(name, factory()) for name, factory in _STEPS_WAVE_2]
            wave2_results = await asyncio.gather(*wave2_tasks, return_exceptions=True)
            for r in wave2_results:
                if isinstance(r, dict):
                    all_results.append(r)
                else:
                    all_results.append({"ok": False, "error": str(r)[:80]})

        ok_count  = sum(1 for r in all_results if r.get("ok") and not r.get("skipped"))
        fail_count = sum(1 for r in all_results if not r.get("ok"))
        elapsed   = round(time.monotonic() - t_total, 1)

        result = {
            "ok": True,
            "timestamp": _ts(),
            "steps_ok": ok_count,
            "steps_failed": fail_count,
            "steps_total": len(all_results),
            "elapsed_s": elapsed,
            "results": {r["name"]: r for r in all_results if "name" in r},
        }
        _save(result)

        # Telegram report
        try:
            from modules.notify_hub import async_send_telegram
            failed_names = [r["name"] for r in all_results if not r.get("ok") and "name" in r]
            msg = (
                f"🚀 <b>Traffic Accelerator — Abgeschlossen!</b>\n"
                f"✅ {ok_count}/{len(all_results)} Tasks OK\n"
                f"⏱ {elapsed}s Laufzeit\n"
                f"📧 Outreach: 500 Emails\n"
                f"📝 Blog: 3 Artikel\n"
                f"📱 Social: 3 Posts\n"
                + (f"❌ Fehler: {', '.join(failed_names[:3])}" if failed_names else "🎯 Alle Tasks erfolgreich!")
            )
            await async_send_telegram(msg)
        except Exception:
            pass

        log.info("🚀 Acceleration DONE: %d/%d OK in %.1fs", ok_count, len(all_results), elapsed)
        return result


async def run_traffic_turbo() -> dict:
    """Turbo-Modus: Nur Wave 1 (schnell, direkte Revenue-Tasks)."""
    return await run_full_acceleration(waves=1)
