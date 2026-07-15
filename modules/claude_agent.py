"""
Claude Autonomous Agent — Rudolf's permanent right hand.
Läuft auf Railway, prüft System-Health, repariert autonom, sendet Telegram-Bericht.
"""
import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime

import aiohttp

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")

SYSTEM_PROMPT = """Du bist der SuperMegaBot-Assistent — Rudolfs autonomer rechter Hand.
Du läufst auf Railway und überwachst das System.

Deine Aufgaben:
1. Analysiere den übergebenen System-Status
2. Identifiziere kritische Probleme (Fehler, abgelaufene Tokens, ausgefallene Services)
3. Gib einen strukturierten Bericht zurück mit:
   - ✅ Was läuft gut
   - ⚠️ Was Aufmerksamkeit braucht
   - 🔧 Was du empfiehlst zu tun

Antworte IMMER auf Deutsch. Sei präzise und actionable. Max 500 Zeichen.
"""


async def _call_claude(user_message: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "ANTHROPIC_API_KEY nicht gesetzt"

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["content"][0]["text"]
            else:
                text = await resp.text()
                log.error("Claude API Fehler %s: %s", resp.status, text[:200])
                return f"API-Fehler {resp.status}"


async def _check_health() -> dict:
    results = {}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"https://{RAILWAY_URL}/health",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                results["health"] = data.get("status", "unknown")
                results["circuits_open"] = data.get("circuits_open", [])
                results["uptime"] = data.get("uptime_seconds", 0)
        except Exception as exc:
            results["health"] = f"error: {exc}"
    return results


async def _send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10),
        )


async def run_agent_check() -> str:
    """Vollständiger Agent-Check: Health + Claude-Analyse + Telegram-Report."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    log.info("Claude Agent Check gestartet: %s", ts)

    health = await _check_health()
    health_str = (
        f"Railway: {health.get('health', 'unknown')}\n"
        f"Circuit Breakers offen: {health.get('circuits_open', [])}\n"
        f"Uptime: {health.get('uptime', 0):.0f}s\n"
    )

    analysis = await _call_claude(
        f"System-Status {ts}:\n{health_str}\n"
        "Analysiere und gib Empfehlungen."
    )

    report = f"🤖 <b>Claude Agent — {ts}</b>\n\n{analysis}"
    await _send_telegram(report)
    log.info("Claude Agent Check abgeschlossen: %s", analysis[:100])
    return analysis


async def run_syntax_check() -> list[str]:
    """Python-Syntax aller Module prüfen, Fehler zurückgeben."""
    errors = []
    base = os.path.dirname(os.path.dirname(__file__))
    for subdir in ("modules", "core", "dashboard"):
        path = os.path.join(base, subdir)
        if not os.path.isdir(path):
            continue
        for fname in os.listdir(path):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(path, fname)
            try:
                result = subprocess.run(
                    ["python3", "-m", "py_compile", fpath],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    errors.append(f"{fpath}: {result.stderr.strip()}")
            except Exception as exc:
                errors.append(f"{fpath}: {exc}")
    return errors
