#!/usr/bin/env python3
"""MegaBot Self-Expansion — revenue-getriebene Task-Aktivierung."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("SelfExpansion")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "self_expansion.json"
TASKS_DIR = DATA_DIR / "expansion_tasks"


class SelfExpansionEngine:
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or TASKS_DIR)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"history": [], "active_modules": []}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")

    async def analyze_and_expand(
        self,
        current_revenue: Optional[Dict[str, float]] = None,
        task_count: int = 140,
    ) -> List[Dict[str, Any]]:
        """Triggert echte Revenue-Module statt leerer Platzhalter-Dateien."""
        if current_revenue is None:
            current_revenue = await self._fetch_revenue_breakdown()

        expansions: List[Dict[str, Any]] = []
        rev_total = float(current_revenue.get("Revenue Tasks", current_revenue.get("month_eur", 0)))

        if rev_total < 300:
            r = await self._run_affiliate_blast()
            expansions.append({"type": "new_affiliate_blast", "result": r, "reason": f"revenue {rev_total}<300"})

        if current_revenue.get("AI-Wrapper Nischen-SaaS", 0) == 0:
            from modules.megabot_ai_wrapper_engine import run_ai_wrapper_cycle
            r = await run_ai_wrapper_cycle()
            expansions.append({"type": "wrapper_promotion_task", "result": r})

        if current_revenue.get("EU Compliance Revenue Engine", 0) == 0:
            r = await self._run_compliance_promo()
            expansions.append({"type": "compliance_revenue_push", "result": r})

        if task_count < 150:
            r = await self._run_marketplace_expander()
            expansions.append({"type": "marketplace_expander", "result": r})

        self.state.setdefault("history", []).extend(expansions)
        self.state["last_run"] = datetime.now().isoformat()
        self._save()
        return expansions

    async def _fetch_revenue_breakdown(self) -> Dict[str, float]:
        out: Dict[str, float] = {"Revenue Tasks": 0, "AI-Wrapper Nischen-SaaS": 0, "EU Compliance Revenue Engine": 0}
        try:
            from modules.revenue_engine import get_monthly_revenue
            import asyncio
            rev = await get_monthly_revenue()
            out["Revenue Tasks"] = float(rev.get("month_eur", 0))
            out["month_eur"] = out["Revenue Tasks"]
        except Exception as e:
            log.warning("revenue fetch: %s", e)
        return out

    async def _run_affiliate_blast(self) -> Dict[str, Any]:
        try:
            from modules.ds24_affiliate_blaster import run_daily_affiliate_blast
            return await run_daily_affiliate_blast()
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    async def _run_marketplace_expander(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        try:
            from modules.ebay_autonomy import run_ebay_cycle
            results["ebay"] = await run_ebay_cycle()
        except Exception as e:
            results["ebay"] = {"error": str(e)[:80]}
        try:
            from modules.amazon_autonomy import run_amazon_cycle
            results["amazon"] = await run_amazon_cycle()
        except Exception as e:
            results["amazon"] = {"error": str(e)[:80]}
        return {"ok": any(isinstance(v, dict) and v.get("ok") for v in results.values()), "results": results}

    async def _run_compliance_promo(self) -> Dict[str, Any]:
        try:
            from modules.megabot_eu_compliance_engine import EUComplianceRevenueEngine
            from modules.megabot_umsatzmaschine import get_umsatzmaschine
            eng = EUComplianceRevenueEngine(get_umsatzmaschine())
            return await eng.run_revenue_cycle()
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    def get_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "last_run": self.state.get("last_run"),
            "expansions_total": len(self.state.get("history", [])),
            "last_expansions": (self.state.get("history") or [])[-5:],
        }