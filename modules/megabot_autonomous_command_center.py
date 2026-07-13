#!/usr/bin/env python3
"""MegaBot Autonomous Self-Expanding Command Center — Revenue-Fokus 24/7."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AutonomousCC")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "autonomous_command_center.json"
LOOP_INTERVAL_S = int(os.getenv("AUTONOMOUS_CC_INTERVAL_S", "300"))


class AutonomousDashboard:
    def __init__(self):
        self.status = "running"
        self.last_analysis: Optional[datetime] = None
        self.engines: Dict[str, Dict[str, Any]] = {}
        self.expansion_log: List[Dict[str, Any]] = []
        self.problems_detected: List[str] = []
        self.active_tasks = 140
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "status": self.status,
            "last_analysis": self.last_analysis.isoformat() if self.last_analysis else None,
            "engines": self.engines,
            "expansion_log": self.expansion_log[-50:],
            "problems": self.problems_detected[-20:],
            "active_tasks": self.active_tasks,
        }, indent=2, default=str), encoding="utf-8")

    async def _refresh_engines(self) -> None:
        rev = 0.0
        try:
            from modules.revenue_engine import get_monthly_revenue
            r = await get_monthly_revenue()
            rev = float(r.get("month_eur", 0))
        except Exception:
            pass
        self.engines = {
            "Funding & Intelligence": {"status": "active", "revenue": 0},
            "EU Compliance Revenue Engine": {"status": "active", "revenue": 0},
            "AI-Wrapper Nischen-SaaS": {"status": "active", "revenue": 0},
            "Revenue Tasks": {"status": "active", "revenue": rev},
            "Intelligence Briefs": {"status": "active", "revenue": 0},
        }
        if rev < 200:
            self.problems_detected.append(f"Revenue unter €200 (aktuell €{rev:.0f})")

    async def analyze_performance(self) -> Dict[str, Any]:
        await self._refresh_engines()
        log.info("Performance-Analyse — Revenue €%.0f", self.engines["Revenue Tasks"]["revenue"])
        return {"revenue_eur": self.engines["Revenue Tasks"]["revenue"], "engines": self.engines}

    async def self_repair(self) -> Dict[str, Any]:
        repaired = 0
        count = 0
        if self.problems_detected:
            try:
                from modules.circuit_breaker import reset_all
                reset_all()
                repaired += 1
            except Exception:
                pass
            try:
                from modules.gmail_accounts import test_all_accounts
                g = test_all_accounts()
                if g.get("working", 0) == 0:
                    self.problems_detected.append("Kein Gmail SMTP — Deliveries gefährdet")
            except Exception:
                pass
            count = len(self.problems_detected)
            self.problems_detected.clear()
            log.info("Self-Repair: %d Probleme bearbeitet", count)
        return {"repaired": repaired, "cleared_problems": count}

    async def propose_and_execute_expansions(self) -> List[Dict[str, Any]]:
        from modules.megabot_self_expansion import SelfExpansionEngine
        eng = SelfExpansionEngine()
        rev_map = {k: float(v.get("revenue", 0)) for k, v in self.engines.items()}
        expansions = await eng.analyze_and_expand(rev_map, self.active_tasks)
        self.expansion_log.extend(expansions)
        for ex in expansions:
            log.info("Expansion: %s", ex.get("type"))
        return expansions

    async def run_revenue_cycle(self) -> Dict[str, Any]:
        """Ein Zyklus — Compliance + AI-Wrapper + Expansion."""
        from modules.megabot_umsatzmaschine import get_umsatzmaschine
        from modules.megabot_ai_wrapper_engine import run_ai_wrapper_cycle
        from modules.megabot_eu_compliance_engine import EUComplianceRevenueEngine

        bot = get_umsatzmaschine()
        await self.analyze_performance()
        await self.self_repair()

        compliance = EUComplianceRevenueEngine(bot)
        comp = await compliance.run_revenue_cycle()
        wrapper = await run_ai_wrapper_cycle()
        expansions = await self.propose_and_execute_expansions()

        self.last_analysis = datetime.now()
        self._save()
        return {
            "ok": True,
            "timestamp": self.last_analysis.isoformat(),
            "compliance": comp,
            "ai_wrapper": wrapper,
            "expansions": expansions,
            "engines": self.engines,
        }

    async def run_autonomous_loop(self) -> None:
        log.info("Autonomous Command Center gestartet (alle %ds)", LOOP_INTERVAL_S)
        while True:
            try:
                await self.run_revenue_cycle()
            except Exception as e:
                log.error("Autonomous loop: %s", e)
                self.problems_detected.append(str(e)[:120])
            await asyncio.sleep(LOOP_INTERVAL_S)

    def get_full_status(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "last_analysis": self.last_analysis.isoformat() if self.last_analysis else self._state.get("last_analysis"),
            "active_tasks": self.active_tasks,
            "engines": self.engines or self._state.get("engines", {}),
            "expansion_suggestions": len(self.expansion_log),
            "problems": len(self.problems_detected),
            "autonomous_mode": True,
        }


_dashboard: Optional[AutonomousDashboard] = None


def get_autonomous_dashboard() -> AutonomousDashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = AutonomousDashboard()
    return _dashboard


async def run_revenue_test() -> Dict[str, Any]:
    """Test: Compliance-Lieferung + AI-Wrapper + Expansion."""
    from modules.megabot_umsatzmaschine import get_umsatzmaschine
    from modules.megabot_eu_compliance_engine import EUComplianceRevenueEngine
    from modules.megabot_ai_wrapper_engine import AIWrapperEngine
    from modules.megabot_self_expansion import SelfExpansionEngine

    bot = get_umsatzmaschine()
    test_email = os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")

    compliance = EUComplianceRevenueEngine(bot)
    fulfill = await compliance.fulfill_order(test_email, "Compliance Pro", shop_url="ineedit.com.co")

    wrapper = AIWrapperEngine()
    launched = wrapper.auto_launch_wrappers()
    promo = await wrapper.promote_wrappers()

    expansion = SelfExpansionEngine()
    expansions = await expansion.analyze_and_expand({"Revenue Tasks": 194}, 140)

    return {
        "ok": fulfill.get("ok") and promo.get("ok", True),
        "compliance_delivery": fulfill,
        "ai_wrappers_launched": len(launched),
        "ai_wrapper_promo": promo,
        "expansions": expansions,
    }


async def start_autonomous_loop_background() -> None:
    if os.getenv("AUTONOMOUS_CC_ENABLED", "true").lower() in ("false", "0", "off"):
        return
    await asyncio.sleep(int(os.getenv("AUTONOMOUS_CC_BOOT_DELAY_S", "180")))
    await get_autonomous_dashboard().run_autonomous_loop()