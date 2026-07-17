#!/usr/bin/env python3
"""
Autonomous Master — Vollständiger Loop-Orchestrator.

Ein einziger Einstiegspunkt der ALLE 6 Komponenten in Sequenz ausführt:

  Phase 1: Code Health (Syntax-Check)
  Phase 2: Analytics (Plausible/PostHog — graceful wenn Keys fehlen)
  Phase 3: Payments (Stripe Snapshot + neue Zahlungen verarbeiten)
  Phase 4: Lemon Squeezy (graceful wenn Keys fehlen)
  Phase 5: Email Onboarding (Resend — Key vorhanden → funktioniert JETZT)
  Phase 6: Claude/Ollama → Plan für nächste Iteration
  Phase 7: Auto-Commit wenn plan.deploy_safe=True
  Phase 8: Telegram Master-Report

Scheduler: alle 3h als 'autonomous_master'
CLI:        python3 -m modules.autonomous_master [--quick]
API:        POST /api/autonomous-master/run  (X-API-Key: DASHBOARD_API_KEY)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("AutonomousMaster")

_BASE     = Path(__file__).resolve().parents[1]
_DATA_DIR = _BASE / "data" / "autonomous_master"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tg_token() -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()  -> str: return os.getenv("TELEGRAM_CHAT_ID", "")


# ── Phase-Wrapper (nie abstürzen) ─────────────────────────────────────────────

async def _run_phase(name: str, coro) -> dict[str, Any]:
    t0 = time.time()
    try:
        result = await coro
        return {"phase": name, "ok": True, "data": result, "ms": int((time.time()-t0)*1000)}
    except Exception as e:
        log.warning("Phase %s Fehler: %s", name, e)
        return {"phase": name, "ok": False, "error": str(e)[:200], "ms": int((time.time()-t0)*1000)}


# ── Phase 1: Code Health ──────────────────────────────────────────────────────

async def phase_1_code_health() -> dict[str, Any]:
    from modules.autonomous_loop import phase_code_health
    return phase_code_health(max_files=60)


# ── Phase 2: Analytics ────────────────────────────────────────────────────────

async def phase_2_analytics() -> dict[str, Any]:
    try:
        from modules.analytics_feedback import get_analytics_tasks
        return await get_analytics_tasks()
    except Exception as e:
        return {"ok": False, "skipped": True, "reason": str(e)[:120]}


# ── Phase 3: Stripe Payments ──────────────────────────────────────────────────

async def phase_3_payments() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from modules.stripe_payment_hook import task_stripe_payment_poll, get_payment_stats
        poll_result = await task_stripe_payment_poll()
        stats       = await get_payment_stats()
        out["poll"] = poll_result
        out["stats"] = stats
        out["ok"]   = True
    except Exception as e:
        out["ok"]    = False
        out["error"] = str(e)[:120]
    # Stripe Billing Snapshot
    try:
        from modules.stripe_auto_billing import run_billing_cycle
        out["billing"] = await run_billing_cycle()
    except Exception:
        pass
    return out


# ── Phase 4: Lemon Squeezy ────────────────────────────────────────────────────

async def phase_4_lemon() -> dict[str, Any]:
    try:
        from modules.lemon_squeezy_autopilot import run_lemon_cycle
        return await run_lemon_cycle()
    except Exception as e:
        return {"ok": False, "skipped": True, "reason": str(e)[:120]}


# ── Phase 5: Email Onboarding ─────────────────────────────────────────────────

async def phase_5_onboarding() -> dict[str, Any]:
    try:
        from modules.email_onboarding_autopilot import health_check
        return await health_check()
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ── Phase 6: KI-Plan ─────────────────────────────────────────────────────────

async def phase_6_ai_plan(analytics_data: dict, payment_data: dict, quick: bool = False) -> dict[str, Any]:
    """Claude/Ollama generiert Plan für nächste Iteration."""
    analytics_tasks = analytics_data.get("tasks") or []
    mrr = (payment_data.get("stats") or {}).get("total_revenue_eur", 0)

    context = (
        f"MRR/Einnahmen bisher: €{mrr:.2f}\n"
        f"Analytics-Tasks: {json.dumps(analytics_tasks[:3])}\n"
    )
    prompt = (
        f"Du bist SuperMegaBot autonomer Engineer für ineedit.com.co.\n"
        f"Kontext: {context}\n\n"
        f"Erstelle einen JSON-Plan mit:\n"
        f"  summary: string (was wird verbessert, max 80 Zeichen)\n"
        f"  code_changes: Liste von {{file, intent}}\n"
        f"  deploy_safe: bool (True nur wenn Änderungen sicher sind)\n"
        f"  expected_revenue_impact: string\n"
        f"Antworte NUR mit gültigem JSON."
    )
    try:
        from modules.open_claw import claw_complete
        raw = await claw_complete(prompt, max_tokens=500)
        # JSON extrahieren
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            plan = json.loads(raw[start:end])
        else:
            plan = {"summary": raw[:80], "deploy_safe": False, "code_changes": [], "expected_revenue_impact": "?"}
        return {"ok": True, "plan": plan, "raw": raw[:1000]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "plan": {"deploy_safe": False}}


# ── Phase 7: Auto-Commit ──────────────────────────────────────────────────────

async def phase_7_commit(ai_result: dict) -> dict[str, Any]:
    try:
        from modules.loop_commit_engine import run_commit_cycle
        plan = ai_result.get("plan") or {}
        report = {
            "claude_iterate": {
                "ai_plan": json.dumps(plan),
                "ok": ai_result.get("ok", False),
            }
        }
        return await run_commit_cycle(report)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ── Phase 8: Telegram Master-Report ──────────────────────────────────────────

async def _send_master_report(phases: dict, duration_s: float) -> None:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return

    def status(phase_name: str) -> str:
        p = phases.get(phase_name, {})
        if p.get("ok"):  return "✅"
        if p.get("skipped"): return "⏭"
        return "❌"

    mrr = 0.0
    try:
        mrr = phases.get("payments", {}).get("data", {}).get("stats", {}).get("total_revenue_eur", 0)
    except Exception:
        pass

    plan_summary = ""
    try:
        plan_summary = phases.get("ai_plan", {}).get("data", {}).get("plan", {}).get("summary", "")
    except Exception:
        pass

    commit_url = ""
    try:
        commit_url = phases.get("commit", {}).get("data", {}).get("pr_url", "")
    except Exception:
        pass

    msg = (
        f"🤖 <b>Autonomous Master Cycle</b> ({duration_s:.0f}s)\n\n"
        f"{status('code_health')} Code Health\n"
        f"{status('analytics')} Analytics (Plausible/PostHog)\n"
        f"{status('payments')} Stripe — €{mrr:.2f} gesamt\n"
        f"{status('lemon')} Lemon Squeezy\n"
        f"{status('onboarding')} Resend Onboarding\n"
        f"{status('ai_plan')} KI-Plan\n"
        f"{status('commit')} Auto-Commit\n"
    )
    if plan_summary:
        msg += f"\n📋 Plan: <i>{plan_summary}</i>"
    if commit_url:
        msg += f"\n🚀 PR: {commit_url}"

    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram Fehler: %s", e)


# ── Master Cycle ──────────────────────────────────────────────────────────────

async def run_master_cycle(quick: bool = False) -> dict[str, Any]:
    """Führt alle 8 Phasen aus — nie abstürzen, immer reporten."""
    t_start = time.time()
    log.info("🚀 Autonomous Master Cycle startet (quick=%s)", quick)

    phases: dict[str, Any] = {}

    # Phase 1-5 ausführen
    phases["code_health"] = await _run_phase("code_health",  phase_1_code_health())
    phases["analytics"]   = await _run_phase("analytics",    phase_2_analytics())
    phases["payments"]    = await _run_phase("payments",     phase_3_payments())
    phases["lemon"]       = await _run_phase("lemon",        phase_4_lemon())
    phases["onboarding"]  = await _run_phase("onboarding",   phase_5_onboarding())

    # Phase 6: KI-Plan (mit Kontext aus Phase 2+3)
    analytics_data = phases["analytics"].get("data") or {}
    payment_data   = phases["payments"].get("data") or {}
    phases["ai_plan"] = await _run_phase("ai_plan", phase_6_ai_plan(analytics_data, payment_data, quick))

    # Phase 7: Auto-Commit
    ai_result = phases["ai_plan"].get("data") or {}
    phases["commit"] = await _run_phase("commit", phase_7_commit(ai_result))

    duration = time.time() - t_start

    # Report speichern
    report = {
        "phases": phases,
        "duration_s": round(duration, 1),
        "at": _now(),
        "quick": quick,
    }
    ts    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path  = _DATA_DIR / f"master_{ts}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    (_DATA_DIR / "latest.json").write_text(json.dumps(report, indent=2, default=str))

    # Phase 8: Telegram Report
    await _send_master_report(phases, duration)

    log.info("✅ Master Cycle abgeschlossen in %.1fs", duration)
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [MASTER] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Überspringe schwere Agent-Teams")
    args = parser.parse_args()
    asyncio.run(run_master_cycle(quick=args.quick))
