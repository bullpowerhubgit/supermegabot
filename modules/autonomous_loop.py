#!/usr/bin/env python3
"""
Autonomous Loop — Claude → Tests → Deploy → Payments → Analytics → Next Iteration

Phases:
  1. code_health     — syntax / self-checks
  2. claude_iterate  — AI agents propose next feature/fix from analytics
  3. payments        — Stripe billing snapshot + Lemon Squeezy catalog
  4. onboarding      — Resend/Loops sequence health
  5. analytics       — Plausible/PostHog → optimization tasks
  6. plan_next       — persist next iteration plan for Claude/CI

CLI:
  python3 -m modules.autonomous_loop
  python3 -m modules.autonomous_loop --quick
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import py_compile
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("AutonomousLoop")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "autonomous_loop"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_report(report: dict) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = DATA_DIR / f"loop_{ts}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    latest = DATA_DIR / "latest.json"
    latest.write_text(json.dumps(report, indent=2, default=str))
    return path


# ── Phase 1: Code health ─────────────────────────────────────────────────────

def phase_code_health(max_files: int = 80) -> dict[str, Any]:
    errors: list[str] = []
    checked = 0
    paths = []
    for pattern in ("modules/*.py", "core/*.py", "dashboard/*.py", "scripts/api_precheck.py"):
        paths.extend(sorted(ROOT.glob(pattern))[:max_files])
    # unique preserve order
    seen = set()
    unique = []
    for p in paths:
        if p not in seen and p.is_file():
            seen.add(p)
            unique.append(p)
    for p in unique[:max_files]:
        try:
            py_compile.compile(str(p), doraise=True)
            checked += 1
        except Exception as e:
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    # lightweight module self-checks
    extra: dict[str, Any] = {}
    try:
        from modules.stripe_guards import self_check
        extra["stripe_guards"] = self_check()
    except Exception as e:
        extra["stripe_guards"] = {"ok": False, "error": str(e)[:120]}
    return {
        "ok": len(errors) == 0,
        "checked": checked,
        "errors": errors[:20],
        "extra": extra,
        "at": _now(),
    }


# ── Phase 2: Claude / agents ─────────────────────────────────────────────────

async def phase_claude_iterate(analytics_tasks: list[dict] | None = None) -> dict[str, Any]:
    top = (analytics_tasks or [{}])[0]
    task = (
        top.get("detail")
        or top.get("title")
        or "Increase MRR: improve conversion CTAs, onboarding, and first-payment funnel."
    )
    results: dict[str, Any] = {"task": task, "agents": {}}

    # Prefer dedicated collab if present
    try:
        from modules.claude_agent_collab import run_collab_cycle
        results["agents"]["claude_collab"] = await run_collab_cycle(focus=task)
    except Exception as e:
        results["agents"]["claude_collab"] = {"ok": False, "error": str(e)[:160]}

    try:
        from modules.agent_teams import run_team
        results["agents"]["growth"] = await run_team(
            "growth",
            f"Autonomous loop iteration. Focus: {task}. Return 3 concrete code/marketing actions.",
            notify=False,
        )
        results["agents"]["marketing"] = await run_team(
            "marketing",
            f"Autonomous loop. Focus: {task}. Draft email/social angle + CTA.",
            notify=False,
        )
        results["agents"]["revenue"] = await run_team(
            "revenue",
            "Snapshot Stripe health and list blockers to first payment.",
            notify=False,
        )
    except Exception as e:
        results["agents"]["agent_teams"] = {"ok": False, "error": str(e)[:160]}

    # Direct AI fallback for next-patch suggestion
    try:
        from modules.ai_client import call_ai
        prompt = (
            "You are SuperMegaBot autonomous engineer. Given analytics/revenue task, "
            "output JSON with keys: summary, code_changes (list of files+intent), "
            "deploy_safe (bool), expected_revenue_impact.\n"
            f"Task: {task}\n"
            f"Analytics tasks: {json.dumps(analytics_tasks or [])[:1500]}"
        )
        text = await call_ai(prompt, max_tokens=800)
        results["ai_plan"] = text[:4000]
        results["ok"] = True
    except Exception as e:
        results["ai_plan"] = None
        results["ok"] = bool(results.get("agents"))
        results["ai_error"] = str(e)[:160]

    results["at"] = _now()
    return results


# ── Phase 3: Payments (Stripe + Lemon) ───────────────────────────────────────

async def phase_payments() -> dict[str, Any]:
    out: dict[str, Any] = {"stripe": {}, "lemon": {}, "mrr": 0.0}

    # Stripe bullpower-only snapshot
    try:
        from modules.stripe_key_resolver import get_working_stripe_key, assert_bullpower_only
        key = get_working_stripe_key()
        assert_bullpower_only(key)
        out["stripe"]["key_ok"] = True
    except Exception as e:
        out["stripe"]["key_ok"] = False
        out["stripe"]["error"] = str(e)[:160]

    try:
        from modules.stripe_auto_billing import run_billing_cycle
        out["stripe"]["billing"] = await run_billing_cycle()
    except Exception:
        # fallback minimal balance
        try:
            import aiohttp
            from modules.stripe_key_resolver import get_working_stripe_key
            key = get_working_stripe_key()
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.stripe.com/v1/balance",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    bal = await r.json()
                async with s.get(
                    "https://api.stripe.com/v1/subscriptions?status=active&limit=20",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    subs = await r.json()
            active = (subs.get("data") or []) if isinstance(subs, dict) else []
            mrr = 0.0
            for sub in active:
                for item in (sub.get("items") or {}).get("data") or []:
                    price = item.get("price") or {}
                    if price.get("recurring") and price.get("unit_amount"):
                        mrr += price["unit_amount"] / 100.0
            out["stripe"]["balance"] = bal
            out["stripe"]["active_subscriptions"] = len(active)
            out["mrr"] = round(mrr, 2)
        except Exception as e:
            out["stripe"]["snapshot_error"] = str(e)[:160]

    try:
        from modules.lemon_squeezy_autopilot import run_lemon_cycle
        out["lemon"] = await run_lemon_cycle()
    except Exception as e:
        out["lemon"] = {"ok": False, "error": str(e)[:160]}

    out["ok"] = bool(out["stripe"].get("key_ok") or out["lemon"].get("ok") or out["lemon"].get("skipped"))
    out["at"] = _now()
    return out


# ── Phase 4: Email onboarding ────────────────────────────────────────────────

async def phase_onboarding() -> dict[str, Any]:
    try:
        from modules.email_onboarding_autopilot import run_onboarding_health
        return await run_onboarding_health()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


# ── Phase 5: Analytics feedback ──────────────────────────────────────────────

async def phase_analytics(stripe_mrr: float = 0.0) -> dict[str, Any]:
    try:
        from modules.analytics_feedback import collect_analytics_feedback
        return await collect_analytics_feedback(stripe_mrr=stripe_mrr)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160], "optimization_tasks": []}


# ── Phase 6: Persist next plan ───────────────────────────────────────────────

def phase_plan_next(report: dict) -> dict[str, Any]:
    tasks = (report.get("analytics") or {}).get("optimization_tasks") or []
    ai_plan = (report.get("claude") or {}).get("ai_plan")
    plan = {
        "generated_at": _now(),
        "top_tasks": tasks[:5],
        "ai_plan_excerpt": (ai_plan or "")[:1500],
        "mrr": (report.get("payments") or {}).get("mrr"),
        "code_health_ok": (report.get("code_health") or {}).get("ok"),
        "next_actions": [
            "Ship highest-priority optimization_task",
            "Keep Stripe bullpower-only + payment links live",
            "Run email day-0 enroll on new leads",
            "CI: tests → main → Railway/Vercel auto-deploy",
            "Re-run autonomous loop after deploy",
        ],
    }
    plan_path = DATA_DIR / "next_iteration.json"
    plan_path.write_text(json.dumps(plan, indent=2, default=str))
    # Also update a machine-readable backlog for Claude Code / CI
    backlog = ROOT / "data" / "autonomous_loop" / "BACKLOG.md"
    lines = [
        "# Autonomous Loop Backlog",
        f"_Generated {_now()}_",
        "",
        f"**MRR:** {plan.get('mrr')}",
        f"**Code health:** {plan.get('code_health_ok')}",
        "",
        "## Top tasks",
    ]
    for t in tasks[:8]:
        lines.append(f"- **[{t.get('priority')}]** {t.get('title')}: {t.get('detail')}")
    if ai_plan:
        lines.extend(["", "## AI plan (excerpt)", "```", str(ai_plan)[:2000], "```"])
    backlog.write_text("\n".join(lines) + "\n")
    return {"ok": True, "plan_path": str(plan_path), "backlog": str(backlog)}


async def phase_notify(report: dict) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    chat = os.getenv("TELEGRAM_CHAT_ID") or ""
    if not token or not chat:
        return
    mrr = (report.get("payments") or {}).get("mrr")
    top = ((report.get("analytics") or {}).get("top_task") or {})
    text = (
        "⚡ <b>Autonomous Loop</b>\n"
        f"Code: {'OK' if (report.get('code_health') or {}).get('ok') else 'FAIL'}\n"
        f"MRR: €{mrr}\n"
        f"Next: {top.get('title') or 'n/a'}\n"
        f"Report: data/autonomous_loop/latest.json"
    )
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text[:3500], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.debug("telegram skip: %s", e)


# ── Full cycle ───────────────────────────────────────────────────────────────

async def run_autonomous_loop(quick: bool = False, notify: bool = True) -> dict[str, Any]:
    """
    Full autonomous cycle. `quick` skips heavy Claude team runs.
    """
    report: dict[str, Any] = {
        "ok": True,
        "started_at": _now(),
        "mode": "quick" if quick else "full",
        "phases": [],
    }

    # 1 code
    ch = phase_code_health(max_files=40 if quick else 100)
    report["code_health"] = ch
    report["phases"].append("code_health")
    if not ch.get("ok"):
        report["ok"] = False

    # 3 payments early (MRR for analytics)
    pay = await phase_payments()
    report["payments"] = pay
    report["phases"].append("payments")

    # 5 analytics
    analytics = await phase_analytics(stripe_mrr=float(pay.get("mrr") or 0))
    report["analytics"] = analytics
    report["phases"].append("analytics")

    # 2 claude (uses analytics)
    if quick:
        report["claude"] = {
            "ok": True,
            "skipped": True,
            "reason": "quick mode",
            "task": (analytics.get("top_task") or {}).get("title"),
        }
    else:
        report["claude"] = await phase_claude_iterate(analytics.get("optimization_tasks"))
    report["phases"].append("claude_iterate")

    # 4 onboarding
    report["onboarding"] = await phase_onboarding()
    report["phases"].append("onboarding")

    # 6 plan
    report["next"] = phase_plan_next(report)
    report["phases"].append("plan_next")

    report["finished_at"] = _now()
    path = _write_report(report)
    report["report_path"] = str(path)

    if notify:
        await phase_notify(report)

    log.info(
        "Autonomous loop done ok=%s mrr=%s path=%s",
        report.get("ok"),
        pay.get("mrr"),
        path,
    )
    return report


async def run_loop_cycle() -> str:
    """Scheduler-friendly string summary."""
    r = await run_autonomous_loop(quick=False, notify=True)
    top = ((r.get("analytics") or {}).get("top_task") or {}).get("title") or "n/a"
    return f"autonomous_loop ok={r.get('ok')} mrr={((r.get('payments') or {}).get('mrr'))} next={top}"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="SuperMegaBot Autonomous Loop")
    ap.add_argument("--quick", action="store_true", help="Skip heavy Claude teams")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = asyncio.run(
            run_autonomous_loop(quick=args.quick, notify=not args.no_notify)
        )
        print(json.dumps({
            "ok": report.get("ok"),
            "mrr": (report.get("payments") or {}).get("mrr"),
            "top_task": (report.get("analytics") or {}).get("top_task"),
            "report_path": report.get("report_path"),
            "phases": report.get("phases"),
        }, indent=2, default=str))
        return 0 if report.get("ok") else 1
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
