#!/usr/bin/env python3
"""
Claude Agent Collab — SuperMegaBot × Multi-Agent (Claude/AI fallback)
====================================================================
Agents: health · marketing · growth · rudiclone · outreach
Assets: DM sheet · Case Studies · Sales-Call · Stripe ineedit.com.co
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

_FALLBACK = (
    "1) Stripe Checkout €49 Trial (ineedit.com.co only).\n"
    "2) 15 DE-DMs + Case Study Hook.\n"
    "3) Strategy Call → t.me/DudiRudibot.\n"
    "4) LinkedIn/X Traffic auf Buy-Link.\n"
    "5) Pinterest wartet — nicht blocken."
)


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete

        text = await ai_complete(
            prompt,
            system=(
                "Du bist SuperMegaBot Multi-Agent Coordinator. "
                "Stripe NUR ineedit.com.co. Immer Case Study + Sales-Call-Prozess. "
                "Deutsch, kurz, umsatzfokussiert."
            ),
            max_tokens=max_tokens,
        )
        if text and str(text).strip() and not str(text).startswith("["):
            return str(text).strip()
    except Exception as e:
        log.warning("AI: %s", e)
    return _FALLBACK


def _sales_ctx() -> str:
    try:
        from modules.sales_call_process import sales_process_summary

        s = sales_process_summary()
        cases = "; ".join(f"{c['title']}: {c['result']}" for c in s["cases"][:3])
        return (
            f"Trial: {s['cta']['primary_url']} | Call: {s['cta']['secondary_url']} | "
            f"Cases: {cases}"
        )
    except Exception:
        return "Trial buy.stripe.com SuperMegaBot €49 | Call t.me/DudiRudibot"


async def _agent_health() -> dict[str, Any]:
    text = await _ai(
        "SuperMegaBot health: 5 Risiken (Payments ineedit.com.co, Deploy, Keys, Traffic, Compliance).",
        400,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_marketing(focus: str) -> dict[str, Any]:
    text = await _ai(
        f"Marketing agent. Focus: {focus}. {_sales_ctx()}\n"
        "3 DE CTAs + 1 Call-Invite + 1 Case-Hook für SuperMegaBot Starter €49.",
        500,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_growth(focus: str) -> dict[str, Any]:
    text = await _ai(
        f"Growth agent. Focus: {focus}. {_sales_ctx()}\n"
        "Kanäle: Telegram DM, LinkedIn, Meta. Wochenplan + erwartete Leads.",
        500,
    )
    return {"ok": True, "summary": text[:2000]}


async def _agent_rudiclone(focus: str) -> dict[str, Any]:
    try:
        from modules.rudiclone import RudiPersona

        text = await RudiPersona().respond(
            f"Als RudiClone: {focus}. Priorität Umsatz HEUTE. Stripe=ineedit.com.co."
        )
        return {"ok": True, "summary": str(text)[:2000]}
    except Exception as e:
        text = await _ai(
            f"RudiClone: {focus}. Eine harte Revenue-Priorität diese Woche. {_sales_ctx()}",
            350,
        )
        return {"ok": True, "summary": text[:2000], "fallback": True, "note": str(e)[:80]}


async def _agent_outreach() -> dict[str, Any]:
    dms: list[str] = []
    follow: dict[str, str] = {}
    try:
        from modules.telegram_dm_sheet import pick, followups

        dms = pick("de", 5)
        follow = followups()
    except Exception:
        dms = [
            "Kurze Frage: automatisierst du Shopify Support schon?",
            "Case: −40% Support-Zeit — 15-Min Strategy Call?",
            "SuperMegaBot Starter €49 — 7 Tage testen?",
        ]
        try:
            from modules.sales_call_process import telegram_book_script, telegram_after_case

            follow = {
                "book_call": telegram_book_script(),
                "after_case": telegram_after_case("shopify"),
            }
        except Exception:
            pass
    return {"ok": True, "dms": dms, "count": len(dms), "followups": follow}


async def run_collab_cycle(
    focus: str | None = None,
    notify: bool = False,
    task: str | None = None,
) -> dict[str, Any]:
    """Full multi-agent cycle. `task` accepted for agent_teams compatibility."""
    focus = focus or task or "MRR mit Trial + Strategy Call + Case Studies"
    health, marketing, growth, rudi, outreach = await asyncio.gather(
        _agent_health(),
        _agent_marketing(focus),
        _agent_growth(focus),
        _agent_rudiclone(focus),
        _agent_outreach(),
    )
    synthesis = await _ai(
        "8-Zeilen Aktionsplan (Umsatz heute), aus:\n"
        f"Health: {(health.get('summary') or '')[:200]}\n"
        f"Mkt: {(marketing.get('summary') or '')[:200]}\n"
        f"Growth: {(growth.get('summary') or '')[:200]}\n"
        f"Rudi: {(rudi.get('summary') or '')[:200]}\n"
        f"DMs: {outreach.get('count')}",
        400,
    )
    if not (synthesis or "").strip():
        synthesis = _FALLBACK

    report = {
        "ok": True,
        "focus": focus,
        "synthesis": synthesis,
        "at": datetime.now(timezone.utc).isoformat(),
        "stripe_domain": "ineedit.com.co",
        "agents": {
            "claude_health": health,
            "marketing": marketing,
            "growth": growth,
            "rudiclone": rudi,
            "outreach": outreach,
        },
        "agent_ok": {
            "claude_health": bool(health.get("ok")),
            "marketing": bool(marketing.get("ok")),
            "growth": bool(growth.get("ok")),
            "rudiclone": bool(rudi.get("ok")),
            "outreach": bool(outreach.get("ok")),
        },
    }
    path = OUT_DIR / f"collab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    report["path"] = str(path)
    report["saved"] = str(path)

    if notify:
        token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
        chat = os.getenv("TELEGRAM_CHAT_ID") or ""
        if token and chat:
            try:
                import aiohttp

                msg = (
                    f"🤝 <b>Claude Collab</b> · ineedit.com.co\n"
                    f"{synthesis[:900]}\n"
                    f"DMs: {outreach.get('count')}"
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


async def run_outreach_pack(
    lang: str = "de", n: int = 5, notify: bool = False
) -> dict[str, Any]:
    try:
        from modules.telegram_dm_sheet import pick, followups

        base = pick(lang, n)
        fu = followups()
        return {
            "ok": True,
            "base": base,
            "messages": base,
            "polished": "\n".join(base),
            "followups": fu,
        }
    except Exception as e:
        o = await _agent_outreach()
        return {"ok": True, "base": o.get("dms", [])[:n], "error": str(e)[:100]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = asyncio.run(run_collab_cycle(notify=False))
    print(
        json.dumps(
            {
                "ok": r["ok"],
                "path": r.get("path"),
                "agent_ok": r.get("agent_ok"),
                "synthesis": (r.get("synthesis") or "")[:300],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
