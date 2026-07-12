#!/usr/bin/env python3
"""
MegaBot Umsatzmaschine — KOMPLETT VOLL AUTONOM
Alle Engines real verdrahtet: Compliance, AI-Wrapper, Revenue-Tasks, Self-Expansion, KfW
Läuft 24/7 ohne menschlichen Eingriff.

Start:     python3 megabot_umsatzmaschine.py
Test:      python3 megabot_umsatzmaschine.py test
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# SuperMegaBot-Root im Pfad
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("MegaBotRunner")

CYCLE_INTERVAL_S = int(os.getenv("MEGABOT_CYCLE_S", "14400"))  # 4h


# ── Engines (echte Module) ─────────────────────────────────────────────────────

class EUComplianceRevenueEngine:
    """Echte Lieferung via modules/megabot_umsatzmaschine.py"""

    def __init__(self):
        from modules.megabot_umsatzmaschine import MegaBotUmsatzmaschine
        self._bot = MegaBotUmsatzmaschine()

    async def fulfill_order(self, customer_email: str, package: str) -> bool:
        """Liefert an einen echten Kunden (aus megabot_clients.json)."""
        clients = self._bot.clients
        hit = None
        for cid, c in clients.items():
            if c.get("email", "").lower() == customer_email.lower():
                hit = cid
                break
        if not hit:
            log.warning("Kein Kunde %s in megabot_clients.json", customer_email)
            return False
        result = await self._bot.trigger_immediate_delivery(hit)
        log.info("Delivery %s → %s: %s", customer_email, package, result.get("status"))
        return result.get("status") in ("delivered", "ok", True)

    async def run_daily_deliveries(self) -> dict:
        """Alle fälligen Kunden beliefern."""
        return await self._bot.run_daily_deliveries()


class AIWrapperEngine:
    """Echte AI-Wrapper via modules/megabot_ai_wrapper_engine.py"""

    async def auto_launch_wrapper(self) -> bool:
        from modules.megabot_ai_wrapper_engine import AIWrapperEngine as _E
        result = _E().auto_launch_wrappers()
        log.info("AI-Wrapper gelauncht: %d neue", len(result))
        return bool(result)

    async def promote_wrapper(self) -> dict:
        from modules.megabot_ai_wrapper_engine import run_ai_wrapper_cycle
        result = await run_ai_wrapper_cycle()
        log.info("Wrapper-Promotion: %s", result.get("status", result))
        return result


class SelfExpansionEngine:
    """Echte Self-Expansion via modules/megabot_self_expansion.py"""

    async def analyze_and_expand(self, revenue: dict, task_count: int) -> bool:
        from modules.megabot_self_expansion import SelfExpansionEngine as _E
        result = await _E().analyze_and_expand(current_revenue=revenue, task_count=task_count)
        log.info("Self-Expansion: %d Aktionen", len(result))
        return bool(result)


class KfWGenerator:
    """Echter KfW-Antrag via modules/megabot_kfw_generator.py"""

    async def generate_antrag(self) -> bool:
        from modules.megabot_kfw_generator import generate_kfw_pdf
        result = await generate_kfw_pdf()
        path = result.get("pdf_path", "")
        log.info("KfW-Antrag: %s", path or result.get("error", result))
        return result.get("ok", False)


# ── Haupt-Klasse ───────────────────────────────────────────────────────────────

class MegaBotUmsatzmaschine:
    def __init__(self):
        self.compliance = EUComplianceRevenueEngine()
        self.wrapper = AIWrapperEngine()
        self.expansion = SelfExpansionEngine()
        self.kfw = KfWGenerator()

    async def run_forever(self):
        log.info("🚀 MegaBot VOLL AUTONOM gestartet (24/7, Zyklus alle %dh)", CYCLE_INTERVAL_S // 3600)
        while True:
            await self._run_cycle()
            log.info("Nächster Zyklus in %dh", CYCLE_INTERVAL_S // 3600)
            await asyncio.sleep(CYCLE_INTERVAL_S)

    async def _run_cycle(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info("=== AUTONOMER ZYKLUS %s ===", ts)

        # 1. Compliance-Lieferungen (alle fälligen Kunden)
        try:
            delivery = await self.compliance.run_daily_deliveries()
            log.info("Deliveries: %d geliefert, %d übersprungen",
                     delivery.get("delivered", 0), delivery.get("skipped", 0))
        except Exception as e:
            log.error("Compliance-Delivery: %s", e)

        # 2. AI-Wrapper
        try:
            await self.wrapper.auto_launch_wrapper()
            await self.wrapper.promote_wrapper()
        except Exception as e:
            log.error("AI-Wrapper: %s", e)

        # 3. Revenue-Tasks via Scheduler-API
        await self._run_revenue_tasks()

        # 4. Self-Expansion
        try:
            revenue = await self._get_current_revenue()
            await self.expansion.analyze_and_expand(revenue, task_count=140)
        except Exception as e:
            log.error("Self-Expansion: %s", e)

        # 5. KfW
        try:
            await self.kfw.generate_antrag()
        except Exception as e:
            log.error("KfW: %s", e)

        log.info("=== Zyklus abgeschlossen ===")

    async def _run_revenue_tasks(self):
        """Triggert die wichtigsten Revenue-Tasks direkt."""
        tasks_to_run = [
            ("ds24_affiliate_blast",   "modules.digistore24_automation",  "run_affiliate_blast"),
            ("shopify_seo_blog",       "modules.shopify_seo_blog",        "run_seo_blog_cycle"),
            ("klaviyo_autonomy",       "modules.klaviyo_automation",      "run_klaviyo_cycle"),
            ("pinterest_cycle",        "modules.pinterest_autonomy",      "run_pinterest_cycle"),
        ]
        for name, mod_path, fn_name in tasks_to_run:
            try:
                import importlib
                mod = importlib.import_module(mod_path)
                fn = getattr(mod, fn_name, None)
                if fn:
                    result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                    log.info("Task %s: %s", name, result if isinstance(result, str) else "OK")
            except Exception as e:
                log.warning("Task %s: %s", name, e)

    async def _get_current_revenue(self) -> dict:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "http://localhost:8888/api/bot/execute",
                    json={"command": "/revenue"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    d = await r.json()
                    return {"response": d.get("response", "")}
        except Exception:
            return {}

    async def test_all(self):
        log.info("=== VOLLSTÄNDIGER TEST ===")
        await self._run_cycle()
        log.info("=== TEST ABGESCHLOSSEN ===")


# ── Entry Point ────────────────────────────────────────────────────────────────

bot = MegaBotUmsatzmaschine()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(bot.test_all())
    else:
        asyncio.run(bot.run_forever())
