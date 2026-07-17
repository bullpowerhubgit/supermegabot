#!/usr/bin/env python3
"""
Agent Teams — Orchestrates specialized agent sub-teams.

Teams:
  growth    — RudiClone + Geheimwaffe: business strategy + competitor intel
  shopify   — Product sync, SEO, pricing, inventory
  marketing — Klaviyo/Mailchimp campaigns, social media posting
  revenue   — Stripe/Digistore24 monitoring, upsell detection
  system    — Health checks, self-healer, storage monitor

Each team can be triggered via:
  - POST /api/agents/run  { "team": "growth", "task": "..." }
  - Scheduled: automation_scheduler.py
  - Telegram: /team_run growth
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("agent_teams")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_SMART_MODEL = os.getenv("OLLAMA_SMART_MODEL", "llama3.2:70b")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1") or os.getenv("TELEGRAM_BOT_TOKEN_2") or ""
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def _send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text[:4096],
                "parse_mode": "HTML",
            }, timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.warning(f"Telegram notify failed: {e}")


async def _call_claude(prompt: str, max_tokens: int = 1024) -> str:
    """Call Claude via ai_client (Budget Guard + multi-provider fallback)."""
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception as e:
        log.error("agent_teams _call_claude via ai_client failed: %s", e)
        return f"[Claude error: {e}]"


async def _call_ollama(prompt: str, model: str | None = None) -> str:
    """Call local Ollama for cheaper/faster tasks."""
    try:
        import aiohttp
        m = model or OLLAMA_SMART_MODEL
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": m, "prompt": prompt, "stream": False},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                data = await r.json()
                return data.get("response", "")
    except Exception as e:
        log.warning(f"Ollama error: {e}")
        return f"[Ollama unavailable: {e}]"


# ── Team definitions ─────────────────────────────────────────────────────────

TEAM_REGISTRY: Dict[str, Dict] = {
    "growth": {
        "description": "Business strategy, competitor analysis, growth opportunities",
        "agents": ["rudi_clone", "geheimwaffe"],
        "use_claude": True,
    },
    "shopify": {
        "description": "Product sync, SEO optimization, pricing analysis",
        "agents": ["shopify_analyst", "seo_agent"],
        "use_claude": False,
    },
    "marketing": {
        "description": "Email campaigns, social media, ad optimization",
        "agents": ["campaign_agent", "social_agent"],
        "use_claude": True,
    },
    "revenue": {
        "description": "Revenue monitoring, upsell detection, churn prevention",
        "agents": ["revenue_agent", "stripe_watcher"],
        "use_claude": False,
    },
    "system": {
        "description": "Health monitoring, self-healing, storage management",
        "agents": ["health_agent", "self_healer"],
        "use_claude": False,
    },
    "claude_collab": {
        "description": "SuperMegaBot × Claude multi-agent collab (health + marketing + growth + DMs)",
        "agents": ["claude_agent", "team_marketing", "team_growth", "rudiclone", "outreach_pack"],
        "use_claude": True,
    },
    "autonomous_loop": {
        "description": "Full loop: tests → Claude → Stripe/Lemon → email → analytics → next plan",
        "agents": ["code_health", "payments", "analytics", "onboarding", "planner"],
        "use_claude": True,
    },
    "outreach": {
        "description": "Telegram DM outreach using iCloud DM sheet + AI polish",
        "agents": ["dm_sheet", "claude_polish"],
        "use_claude": True,
    },
}


async def run_team(team: str, task: str, notify: bool = True) -> Dict[str, Any]:
    """Run a named agent team on a task."""
    team_info = TEAM_REGISTRY.get(team)
    if not team_info:
        return {"ok": False, "error": f"Unknown team: {team}. Available: {list(TEAM_REGISTRY.keys())}"}

    log.info(f"Agent team '{team}' starting: {task[:100]}")
    started = datetime.utcnow().isoformat()

    # Dedicated collab paths (Claude agents + SuperMegaBot assets together)
    if team == "claude_collab":
        try:
            from modules.claude_agent_collab import run_collab_cycle
            collab = await run_collab_cycle(notify=notify)
            return {
                "ok": bool(collab.get("ok")),
                "team": team,
                "task": task,
                "started_at": started,
                "completed_at": datetime.utcnow().isoformat(),
                "agents": team_info["agents"],
                "result": collab.get("synthesis") or json.dumps(collab.get("agent_ok", {}), default=str),
                "collab": collab,
            }
        except Exception as e:
            log.error("claude_collab team failed: %s", e)
            return {"ok": False, "team": team, "error": str(e)}

    if team == "autonomous_loop":
        try:
            from modules.autonomous_loop import run_autonomous_loop
            special = await run_autonomous_loop(quick=False, notify=notify)
            return {
                "ok": bool(special.get("ok")),
                "team": team,
                "task": task,
                "started_at": started,
                "completed_at": datetime.utcnow().isoformat(),
                "agents": team_info["agents"],
                "result": {
                    "mrr": (special.get("payments") or {}).get("mrr"),
                    "top_task": (special.get("analytics") or {}).get("top_task"),
                    "report_path": special.get("report_path"),
                    "phases": special.get("phases"),
                },
            }
        except Exception as e:
            return {"ok": False, "team": team, "error": str(e)[:200]}

    if team == "outreach":
        try:
            from modules.claude_agent_collab import run_outreach_pack
            pack = await run_outreach_pack(lang="de", n=5, notify=notify)
            result_text = pack.get("polished") or "\n".join(pack.get("base") or [])
            return {
                "ok": bool(pack.get("ok")),
                "team": team,
                "task": task,
                "started_at": started,
                "completed_at": datetime.utcnow().isoformat(),
                "agents": team_info["agents"],
                "result": result_text,
                "pack": pack,
            }
        except Exception as e:
            log.error("outreach team failed: %s", e)
            return {"ok": False, "team": team, "error": str(e)}

    if team_info["use_claude"]:
        prompt = (
            f"You are a {team_info['description']} agent for SuperMegaBot, a SaaS e-commerce automation platform.\n\n"
            f"Task: {task}\n\n"
            f"Agents in this team: {', '.join(team_info['agents'])}\n\n"
            "Analyze the task and provide a concrete action plan with specific steps. "
            "Focus on revenue impact and actionable insights."
        )
        result_text = await _call_claude(prompt)
    else:
        prompt = (
            f"Agent team: {team} — {team_info['description']}\n"
            f"Task: {task}\n"
            f"Provide a brief action summary."
        )
        result_text = await _call_ollama(prompt)

    result = {
        "ok": True,
        "team": team,
        "task": task,
        "started_at": started,
        "completed_at": datetime.utcnow().isoformat(),
        "agents": team_info["agents"],
        "result": result_text,
    }

    if notify:
        msg = f"🤖 <b>Agent Team: {team.upper()}</b>\n{task[:100]}\n\n{result_text[:500]}"
        await _send_telegram(msg)

    log.info(f"Agent team '{team}' completed")
    return result


async def run_all_teams_health_check() -> Dict[str, Any]:
    """Quick health check across all teams — used by scheduler."""
    results = {}
    for team_name in TEAM_REGISTRY:
        try:
            r = await run_team(team_name, "Quick status check — report current system health", notify=False)
            results[team_name] = {"ok": True, "summary": r["result"][:200]}
        except Exception as e:
            results[team_name] = {"ok": False, "error": str(e)}
    return results


def list_teams() -> List[Dict]:
    return [
        {
            "name": k,
            "description": v["description"],
            "agents": v["agents"],
            "ai_backend": "claude" if v["use_claude"] else "ollama",
        }
        for k, v in TEAM_REGISTRY.items()
    ]
