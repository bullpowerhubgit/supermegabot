"""
Bridge to Hermes Agent (rudibot-1).
Hermes runs locally on socket mode and exposes no HTTP API by default.
This module calls it via:
  1. HERMES_API_URL — if you run a custom HTTP wrapper in rudibot-1
  2. subprocess (hermes CLI) — direct local execution
  3. claude-code delegation — via Claude API with the hermes-agent skill
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

HERMES_API_URL = os.getenv("HERMES_API_URL", "")
HERMES_DIR = os.path.expanduser(os.getenv("HERMES_DIR", "~/rudibot-1"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


async def _call_http_api(prompt: str, context: str = "") -> Optional[str]:
    if not HERMES_API_URL:
        return None
    payload = {"prompt": prompt, "context": context}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{HERMES_API_URL}/run",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("result") or data.get("output")
                logger.warning("Hermes HTTP API returned %s", r.status)
    except Exception as exc:
        logger.error("Hermes HTTP API error: %s", exc)
    return None


def _call_subprocess(prompt: str) -> Optional[str]:
    """Run a one-shot Hermes Agent task via subprocess."""
    try:
        result = subprocess.run(
            ["python3", "-m", "hermes_agent.cli", "--task", prompt],
            cwd=HERMES_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.warning("Hermes CLI error: %s", result.stderr[:200])
    except FileNotFoundError:
        logger.info("Hermes CLI not found at %s", HERMES_DIR)
    except subprocess.TimeoutExpired:
        logger.warning("Hermes CLI timed out")
    except Exception as exc:
        logger.error("Hermes subprocess error: %s", exc)
    return None


async def delegate(prompt: str, context: str = "") -> dict:
    """
    Delegate a task to Hermes Agent.
    Returns {"ok": bool, "result": str, "method": str}
    """
    result = await _call_http_api(prompt, context)
    if result:
        return {"ok": True, "result": result, "method": "http_api"}

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _call_subprocess, prompt)
    if result:
        return {"ok": True, "result": result, "method": "subprocess"}

    return {
        "ok": False,
        "result": "",
        "method": "none",
        "error": (
            "Hermes nicht erreichbar. "
            "Setze HERMES_API_URL oder stelle sicher, dass rudibot-1 einen HTTP-Endpunkt hat."
        ),
    }


async def analyze_revenue(data: dict) -> dict:
    prompt = (
        f"Analysiere diese Umsatzdaten und gib 3 konkrete Handlungsempfehlungen: {data}"
    )
    result = await delegate(prompt, context="revenue_analysis")
    # Ergebnis auch an Slack + Telegram senden
    if result.get("ok") and result.get("result"):
        try:
            from modules.slack_notify import send_slack
            await send_slack(f"🧠 Hermes Revenue-Analyse:\n{result['result'][:500]}", level="info")
        except Exception:
            pass
        try:
            from modules.notify_hub import notify
            notify("Hermes Analyse", result["result"][:300], "info")
        except Exception:
            pass
    return result


async def market_research(topic: str) -> dict:
    prompt = f"Führe eine Marktrecherche zu folgendem Thema durch und liste die Top-5-Chancen: {topic}"
    return await delegate(prompt, context="market_research")


async def health_check() -> dict:
    if HERMES_API_URL:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{HERMES_API_URL}/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return {"ok": r.status == 200, "url": HERMES_API_URL}
        except Exception:
            pass

    try:
        proc = subprocess.run(
            ["python3", "-c", "import hermes_agent; print('ok')"],
            cwd=HERMES_DIR,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {"ok": proc.returncode == 0, "method": "subprocess"}
    except Exception:
        pass

    return {
        "ok": False,
        "error": "Hermes nicht konfiguriert. Setze HERMES_API_URL.",
        "dir": HERMES_DIR,
    }


# ── Central Job Queue Dispatcher ─────────────────────────────────────────────

QUEUE_WORKER_URL = os.getenv("QUEUE_WORKER_URL", "http://localhost:5555")


async def dispatch_job(job_name: str, data: dict | None = None) -> dict:
    """
    Dispatch a job to the central BullMQ queue worker (shared/worker.js).
    Falls back to direct HTTP call to supermegabot API if worker not available.
    """
    payload = {"name": job_name, "data": data or {}}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{QUEUE_WORKER_URL}/job",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status == 200:
                    result = await r.json()
                    logger.info("Job dispatched via queue: %s id=%s", job_name, result.get("job_id"))
                    return {"ok": True, "method": "queue", "job_id": result.get("job_id")}
                logger.warning("Queue worker HTTP %s for job %s", r.status, job_name)
    except Exception as exc:
        logger.info("Queue worker not available (%s) — falling back to direct call", exc)

    # Fallback: call supermegabot dashboard API directly
    smb_url = os.getenv("SUPERMEGABOT_URL", "http://localhost:8888")
    job_routes = {
        "shopify_sync": "/api/shopify/sync",
        "revenue_snapshot": "/api/revenue/summary",
        "cart_recovery": "/api/revenue/carts/recover",
        "flash_sale": "/api/revenue/flash-sale",
        "flash_sale_restore": "/api/revenue/flash-sale/restore",
        "telegram_blast": "/api/telegram/send",
        "digistore24_sync": "/api/digistore24/sync",
        "stripe_sync": "/api/stripe/subscriptions",
    }
    route = job_routes.get(job_name)
    if route:
        try:
            method = "POST" if data else "GET"
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    f"{smb_url}{route}",
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    result = await r.json()
                    logger.info("Job %s executed via direct API: %s", job_name, r.status)
                    return {"ok": r.status < 400, "method": "direct_api", "result": result}
        except Exception as exc:
            logger.error("Direct API fallback for %s failed: %s", job_name, exc)

    return {"ok": False, "error": f"Could not dispatch job {job_name}: queue and direct API unavailable"}
