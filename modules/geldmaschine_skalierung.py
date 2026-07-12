"""
Geldmaschine — delegiert an Revenue Engine (nur Geld-Aktionen).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

log = logging.getLogger("GeldmaschineSkalierung")

TARGET_MONTHLY_EUR = float(os.getenv("SCALING_TARGET_EUR", "1000"))


async def _get_monthly_revenue() -> Dict[str, Any]:
    from modules.revenue_engine import get_monthly_revenue
    r = await get_monthly_revenue()
    r["target_eur"] = TARGET_MONTHLY_EUR
    r["progress_pct"] = round(
        min(100.0, r["month_eur"] / TARGET_MONTHLY_EUR * 100), 1
    ) if TARGET_MONTHLY_EUR else 0
    return r


async def run_scaling_cycle() -> Dict[str, Any]:
    from modules.revenue_engine import run_revenue_cycle
    result = await run_revenue_cycle()
    rev = result.get("revenue", {})
    rev["target_eur"] = TARGET_MONTHLY_EUR
    rev["progress_pct"] = round(
        min(100.0, rev.get("month_eur", 0) / TARGET_MONTHLY_EUR * 100), 1
    ) if TARGET_MONTHLY_EUR else 0
    result["revenue"] = rev
    result["strategies"] = result.pop("steps", {})
    return result


async def get_scaling_status() -> Dict[str, Any]:
    from modules.revenue_engine import get_revenue_status
    status = await get_revenue_status()
    status["target_monthly_eur"] = TARGET_MONTHLY_EUR
    status["revenue"]["target_eur"] = TARGET_MONTHLY_EUR
    return status


async def run_scaling_cycle_str() -> str:
    from modules.revenue_engine import run_revenue_cycle_str
    return await run_revenue_cycle_str()