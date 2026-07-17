#!/usr/bin/env python3
"""
Local AI Autopilot — OpenClaw/Ollama health + autonomous content/revenue helpers.

Used by the autonomous loop so local models actively contribute to every iteration
instead of only serving as a hidden fallback.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_topic() -> str:
    return os.getenv(
        "OPENCLAW_AUTOMATION_TOPIC",
        "ineedit.com.co Shopify Automation mit KI, Stripe und Telegram",
    )


async def local_ai_health() -> dict[str, Any]:
    from modules.ai_client import api_status
    from modules.open_claw import CLAW_MODEL, FAST_MODEL, OLLAMA_BASE, SMART_MODEL, cache_stats, get_models, is_online

    online = await is_online()
    models = await get_models() if online else []
    provider_status = api_status()
    return {
        "ok": True,
        "online": online,
        "base": OLLAMA_BASE,
        "default_model": CLAW_MODEL,
        "fast_model": FAST_MODEL,
        "smart_model": SMART_MODEL,
        "model_count": len(models),
        "models": models[:12],
        "cache": cache_stats(),
        "api_hunt": provider_status,
        "at": _now(),
    }


async def run_local_ai_cycle(topic: str | None = None) -> dict[str, Any]:
    from modules.open_claw import claw_generate_content, claw_revenue_strategy

    health = await local_ai_health()
    topic = (topic or _default_topic()).strip()
    if not health.get("online"):
        return {
            "ok": False,
            "skipped": True,
            "reason": "OpenClaw/Ollama offline",
            "topic": topic,
            "health": health,
            "at": _now(),
        }

    revenue_strategy = await claw_revenue_strategy()
    telegram = await claw_generate_content(topic, "telegram")
    seo = await claw_generate_content(topic, "seo")
    return {
        "ok": True,
        "topic": topic,
        "health": health,
        "revenue_strategy": revenue_strategy[:1200],
        "telegram_draft": (telegram.get("text") or "")[:800],
        "seo_draft": (seo.get("text") or "")[:1200],
        "source": "OpenClaw/Ollama",
        "at": _now(),
    }
