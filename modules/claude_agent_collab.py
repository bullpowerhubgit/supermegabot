#!/usr/bin/env python3
"""
Claude Agent Collab — multi-agent cycle for SuperMegaBot.

Agents: claude_health, marketing, growth, rudiclone, outreach
Uses ai_client (budget guard + provider fallbacks).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("ClaudeAgentCollab")

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "agent_collab"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import call_ai
        return await call_ai(prompt, max_tokens=max_tokens)
    except Exception as e:
        return f"[ai_unavailable: {e}]"


async def _agent_health() -> dict[str, Any]:
    text = await _ai(
        "SuperMegaBot health: list 5 risks for a SaaS e-com automation platform "
        "(payments, deploy, keys, traffic, compliance). Be concrete.",
        400,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_marketing(focus: str) -> dict[str, Any]:
    text = await _ai(
        f"Marketing agent. Focus: {focus}. "
        "Give 3 DE/EN CTA variants + 1 email subject for SuperMegaBot Starter €49.",
        500,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_growth(focus: str) -> dict[str, Any]:
    text = await _ai(
        f"Growth agent. Focus: {focus}. "
        "Prioritize channels: Telegram DM, LinkedIn, Meta ads, SEO. "
        "Return weekly plan with expected leads.",
        500,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_rudiclone(focus: str) -> dict[str, Any]:
    try:
        from modules.rudiclone import RudiClone
        # optional API
        if hasattr(RudiClone, "run_once"):
            r = await RudiClone().run_once(focus)  # type: ignore
            return {"ok": True, "summary": str(r)[:2000]}
    except Exception as e:
        log.debug("rudiclone module path: %s", e)
    text = await _ai(
        f"RudiClone strategist: {focus}. One ruthless priority for revenue this week.",
        350,
    )
    return {"ok": True, "summary": text[:2000], "fallback": True}


async def _agent_outreach() -> dict[str, Any]:
    dms: list[str] = []
    try:
        from modules.telegram_dm_sheet import pick
        dms = pick("de", 5)
    except Exception:
        dms = [
            "Kurze Frage: automatisierst du Shopify Support schon?",
            "Wir sparen Shops ~40% Support-Zeit — 15-Min Call?",
            "SuperMegaBot Starter €49 — 7 Tage testen?",
        ]
    return {"ok": True, "dms": dms, "count": len(dms)}


async def run_collab_cycle(focus: str | None = None, notify: bool = False) -> dict[str, Any]:
    focus = focus or "Increase MRR with conversion + outreach + reliable deploy"
    health, marketing, growth, rudi, outreach = await asyncio.gather(
        _agent_health(),
        _agent_marketing(focus),
        _agent_growth(focus),
        _agent_rudiclone(focus),
        _agent_outreach(),
    )
    report = {
        "ok": True,
        "focus": focus,
        "at": datetime.now(timezone.utc).isoformat(),
        "agents": {
            "claude_health": health,
            "marketing": marketing,
            "growth": growth,
            "rudiclone": rudi,
            "outreach": outreach,
        },
        "agent_ok": {
            "claude_health": health.get("ok"),
            "marketing": marketing.get("ok"),
            "growth": growth.get("ok"),
            "rudiclone": rudi.get("ok"),
            "outreach": outreach.get("ok"),
        },
    }
    path = OUT_DIR / f"collab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    report["path"] = str(path)

    if notify:
        token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
        chat = os.getenv("TELEGRAM_CHAT_ID") or ""
        if token and chat:
            try:
                import aiohttp
                msg = (
                    f"🤖 <b>Claude Collab</b>\nFocus: {focus[:120]}\n"
                    f"DMs: {outreach.get('count')}\n"
                    f"{(marketing.get('summary') or '')[:400]}"
                )
                async with aiohttp.ClientSession() as s:
                    await s.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    )
            except Exception as e:
                log.debug("notify: %s", e)

    return report


async def run_outreach_pack(lang: str = "de", n: int = 5) -> dict[str, Any]:
    try:
        from modules.telegram_dm_sheet import pick
        return {"ok": True, "messages": pick(lang, n)}
    except Exception:
        o = await _agent_outreach()
        return {"ok": True, "messages": (o.get("dms") or [])[:n]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = asyncio.run(run_collab_cycle(notify=False))
    print(json.dumps({"ok": r["ok"], "path": r.get("path"), "agent_ok": r.get("agent_ok")}, indent=2))
