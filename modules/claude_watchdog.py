"""
Claude Watchdog — Autonomer System-Guardian für SuperMegaBot.
Läuft alle 6h via automation_scheduler. Prüft + berichtet + schreibt CURRENT_STATUS.md.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("ClaudeWatchdog")

RAILWAY_URL = os.getenv("RAILWAY_URL", "https://supermegabot-production.up.railway.app")
TG_BOT      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")
STATUS_FILE = Path(__file__).parent.parent / "CURRENT_STATUS.md"

_CHECKS = []  # Ergebnisse des letzten Runs


async def _tg(text: str) -> None:
    try:
        from modules.telegram_throttle import send as tg_send
        await tg_send(text)
    except Exception:
        pass


async def check_health() -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{RAILWAY_URL}/health") as r:
                data = await r.json(content_type=None)
                ok = data.get("status") == "ok"
                circuits = data.get("circuits_open", [])
                return {"ok": ok, "circuits": circuits, "uptime": data.get("uptime_seconds", 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def check_revenue() -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"{RAILWAY_URL}/api/revenue/summary") as r:
                data = await r.json(content_type=None)
                shopify = data.get("shopify", {}).get("today_eur", 0)
                ds24    = data.get("ds24", {}).get("today_eur", 0)
                return {"shopify_today": shopify, "ds24_today": ds24, "total_today": shopify + ds24}
    except Exception as e:
        return {"error": str(e)}


async def check_ai_providers() -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{RAILWAY_URL}/api/ai/status") as r:
                if r.status == 200:
                    return await r.json(content_type=None)
    except Exception:
        pass
    return {}


async def run_watchdog() -> dict:
    """Hauptfunktion — wird vom Scheduler aufgerufen."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("ClaudeWatchdog: Start %s", now)

    health, revenue, ai = await asyncio.gather(
        check_health(),
        check_revenue(),
        check_ai_providers(),
    )

    issues = []
    ok_list = []

    # Health
    if health.get("ok"):
        uptime_h = round(health.get("uptime", 0) / 3600, 1)
        ok_list.append(f"✅ Server online ({uptime_h}h uptime)")
        if health.get("circuits"):
            issues.append(f"⚠️ Circuit Breaker offen: {', '.join(health['circuits'])}")
    else:
        issues.append(f"🚨 Server DOWN: {health.get('error', '?')}")

    # Revenue
    total = revenue.get("total_today", 0)
    if total > 0:
        ok_list.append(f"✅ Umsatz heute: €{total:.2f}")
    else:
        ok_list.append("ℹ️ Umsatz heute: €0")

    # Zusammenfassung
    status = "🟢 ALLES OK" if not issues else f"🔴 {len(issues)} PROBLEM(E)"

    lines = [
        f"*SuperMegaBot Watchdog* — {now}",
        f"Status: {status}",
        "",
    ]
    if issues:
        lines += issues
    lines += ok_list

    # Nur bei Problemen oder täglich 08:00 melden
    hour = datetime.now(timezone.utc).hour
    if issues or hour in (7, 8):
        await _tg("\n".join(lines))
        log.info("ClaudeWatchdog: Telegram-Report gesendet (%d Issues)", len(issues))

    result = {
        "timestamp": now,
        "health": health,
        "revenue": revenue,
        "issues": issues,
        "ok": len(issues) == 0,
    }

    _update_status_md(result)
    return result


def _update_status_md(result: dict) -> None:
    """Schreibt Watchdog-Ergebnis in CURRENT_STATUS.md."""
    try:
        content = STATUS_FILE.read_text(encoding="utf-8") if STATUS_FILE.exists() else ""
        ts = result["timestamp"]
        issues_str = "\n".join(f"  - {i}" for i in result["issues"]) if result["issues"] else "  - keine"
        block = (
            f"\n## 🤖 WATCHDOG LETZTER CHECK: {ts}\n"
            f"- Health: {'✅ OK' if result['health'].get('ok') else '❌ DOWN'}\n"
            f"- Umsatz heute: €{result['revenue'].get('total_today', 0):.2f}\n"
            f"- Probleme:\n{issues_str}\n"
        )
        marker = "## 🤖 WATCHDOG LETZTER CHECK:"
        if marker in content:
            start = content.index(marker)
            end = content.find("\n## ", start + 1)
            content = content[:start] + block.lstrip("\n") + (content[end:] if end > 0 else "")
        else:
            content = content.rstrip() + "\n" + block
        STATUS_FILE.write_text(content, encoding="utf-8")
    except Exception as e:
        log.warning("ClaudeWatchdog: CURRENT_STATUS.md Update fehlgeschlagen: %s", e)
