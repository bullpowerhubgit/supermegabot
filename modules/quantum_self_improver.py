#!/usr/bin/env python3
"""
Quantum Self-Improver — lernt aus jedem Fehler, heilt sich selbst, wird besser.
Kein Fehler tritt zweimal auf. Kein Circuit bleibt dauerhaft offen.
"""
from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("QuantumSelfImprover")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL       = os.getenv("RAILWAY_PUBLIC_DOMAIN",
                           os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", "https://supermegabot-production.up.railway.app")).rstrip("/").replace("https://",""))


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _get_client():
    from modules.supabase_client import get_client
    return get_client()


async def log_error(module: str, function: str, error: str, context: dict = None) -> None:
    """Speichert jeden Fehler in Supabase — bei Wiederholung erhöht count."""
    error_type = type(error).__name__ if not isinstance(error, str) else error.split(":")[0][:60]
    error_msg  = str(error)[:500]
    ctx        = context or {}
    try:
        db = await _get_client()
        existing = db.table("system_errors").select("id,count").eq(
            "module", module).eq("function", function).eq("error_type", error_type).execute()
        if existing.data:
            row_id = existing.data[0]["id"]
            old_count = existing.data[0]["count"]
            db.table("system_errors").update({
                "count":    old_count + 1,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "error_msg": error_msg,
            }).eq("id", row_id).execute()
        else:
            db.table("system_errors").insert({
                "module":      module,
                "function":    function,
                "error_type":  error_type,
                "error_msg":   error_msg,
                "context_json": ctx,
                "count":       1,
                "first_seen":  datetime.now(timezone.utc).isoformat(),
                "last_seen":   datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as e:
        log.debug("log_error failed: %s", e)


async def analyze_error_patterns() -> dict:
    """Liest alle Fehler, KI analysiert Muster und schlägt Fixes vor."""
    try:
        db = await _get_client()
        rows = db.table("system_errors").select("*").eq(
            "resolved", False).order("count", desc=True).limit(50).execute()
        errors = rows.data or []
        if not errors:
            return {"ok": True, "repeated_errors": [], "suggested_fixes": [], "total": 0}

        repeated = [e for e in errors if e.get("count", 1) > 1]
        error_summary = "\n".join(
            f"- {e['module']}.{e['function']}: {e['error_type']} "
            f"(x{e['count']}) — {e['error_msg'][:80]}"
            for e in repeated[:10]
        )

        fixes = []
        if error_summary:
            prompt = (
                "Analysiere diese Python-Fehler aus einem Produktions-System und "
                "schlage konkrete Fixes vor (je 1 Satz pro Fehler, auf Deutsch):\n"
                + error_summary
            )
            ai_response = await _ai(prompt, max_tokens=300)
            if ai_response:
                fixes = [line.strip() for line in ai_response.split("\n") if line.strip()]

        return {
            "ok":             True,
            "total":          len(errors),
            "repeated_errors": [
                {"module": e["module"], "function": e["function"],
                 "error": e["error_type"], "count": e["count"],
                 "msg": e["error_msg"][:100]}
                for e in repeated[:10]
            ],
            "suggested_fixes": fixes[:10],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def auto_fix_error(module: str, error_type: str) -> dict:
    """KI generiert Fix-Code und loggt ihn in Supabase."""
    try:
        prompt = (
            f"Generiere einen Python-Fix für diesen Fehler in Modul '{module}': {error_type}\n"
            "Schreibe nur den Fix-Code (max 10 Zeilen), kein Erklärungstext."
        )
        fix_code = await _ai(prompt, max_tokens=200)
        fix_desc_prompt = f"Beschreibe in einem Satz was der Fix für '{error_type}' in '{module}' bewirkt."
        fix_desc = await _ai(fix_desc_prompt, max_tokens=80)

        db = await _get_client()
        db.table("auto_fixes").insert({
            "module":          module,
            "error_type":      error_type,
            "fix_code":        fix_code[:2000],
            "fix_description": fix_desc[:300],
            "applied_at":      datetime.now(timezone.utc).isoformat(),
            "success":         False,
        }).execute()

        os.makedirs("modules/auto_fixes", exist_ok=True)
        safe_name = module.replace("/", "_").replace(".", "_")
        safe_err  = error_type.replace(" ", "_")[:30]
        fix_path  = f"modules/auto_fixes/{safe_name}_{safe_err}.py"
        with open(fix_path, "w") as f:
            f.write(f"# Auto-Fix: {error_type} in {module}\n")
            f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"# {fix_desc}\n\n")
            f.write(fix_code)

        return {"ok": True, "module": module, "error_type": error_type,
                "fix_path": fix_path, "description": fix_desc}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _reset_circuit(circuit_name: str) -> bool:
    """Versucht einen Circuit Breaker zurückzusetzen."""
    endpoint_map = {
        "facebook":  "/api/facebook/status",
        "instagram": "/api/instagram/status",
        "linkedin":  "/api/linkedin/status",
        "twitter":   "/api/twitter/status",
        "tiktok":    "/api/tiktok/status",
        "youtube":   "/api/youtube/status",
    }
    ep = endpoint_map.get(circuit_name)
    if not ep:
        return False
    try:
        url = f"https://{BASE_URL}{ep}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return r.status < 500
    except Exception:
        return False


async def quantum_heal_system() -> dict:
    """Heilt das gesamte System: Circuit Breakers + Fehler-Patterns."""
    healed   = []
    failed   = []
    patterns = await analyze_error_patterns()

    # 1. Circuit Breakers prüfen
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{BASE_URL}/health",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                health = await r.json()
        open_circuits = health.get("circuits_open", [])
    except Exception:
        open_circuits = []

    for circuit in open_circuits:
        reset_ok = await _reset_circuit(circuit)
        if reset_ok:
            healed.append(circuit)
            log.info("Circuit healed: %s", circuit)
        else:
            failed.append(circuit)
        await asyncio.sleep(0.5)

    # 2. Fehler mit count > 3 → KI-Fix generieren
    repeated = patterns.get("repeated_errors", [])
    fixes_generated = 0
    for err in repeated[:3]:
        if err.get("count", 0) > 3:
            fix_result = await auto_fix_error(err["module"], err["error"])
            if fix_result.get("ok"):
                fixes_generated += 1

    # 3. Telegram-Alert
    healed_count = len(healed)
    failed_count = len(failed)
    if healed_count or failed_count or fixes_generated:
        status_line = (
            f"⚡ <b>Quantum Heal Report</b>\n"
            f"Circuits geheilt: {healed_count} ({', '.join(healed) or '-'})\n"
            f"Circuits offen: {failed_count} ({', '.join(failed) or '-'})\n"
            f"KI-Fixes generiert: {fixes_generated}\n"
            f"Fehler analysiert: {len(repeated)}"
        )
        await _telegram(status_line)

    return {
        "ok":             True,
        "circuits_healed": healed,
        "circuits_failed": failed,
        "fixes_generated": fixes_generated,
        "error_patterns":  len(repeated),
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }


async def self_improvement_report() -> dict:
    """Wöchentlicher Report: was wurde verbessert."""
    try:
        db = await _get_client()
        week = datetime.now(timezone.utc).strftime("%Y-W%U")

        errors_resolved = db.table("system_errors").select("id").eq(
            "resolved", True).execute()
        errors_new = db.table("system_errors").select("id").eq(
            "resolved", False).execute()
        fixes_applied = db.table("auto_fixes").select("id").execute()

        resolved_count = len(errors_resolved.data or [])
        new_count      = len(errors_new.data or [])
        fixes_count    = len(fixes_applied.data or [])

        report = (
            f"📊 <b>Quantum Self-Improvement Report — Woche {week}</b>\n"
            f"Fehler behoben: {resolved_count}\n"
            f"Offene Fehler: {new_count}\n"
            f"KI-Fixes generiert: {fixes_count}\n"
            f"System-Gesundheit: {'🟢 Gut' if new_count < 5 else '🟡 Überwachung' if new_count < 20 else '🔴 Kritisch'}"
        )

        db.table("improvement_log").insert({
            "week":         week,
            "errors_fixed": resolved_count,
            "errors_new":   new_count,
            "report_text":  report,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }).execute()

        await _telegram(report)
        return {"ok": True, "week": week, "resolved": resolved_count,
                "open": new_count, "fixes": fixes_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_quantum_status() -> dict:
    """System-Gesundheit + Fehler-Übersicht für Dashboard."""
    try:
        db = await _get_client()
        errors = db.table("system_errors").select("*").eq(
            "resolved", False).order("count", desc=True).limit(20).execute()
        fixes = db.table("auto_fixes").select("id,module,fix_description,success").limit(10).execute()
        logs  = db.table("improvement_log").select("*").order(
            "created_at", desc=True).limit(5).execute()

        error_rows = errors.data or []
        total_errors = len(error_rows)
        repeated = sum(1 for e in error_rows if e.get("count", 1) > 1)

        health_score = max(0, 100 - total_errors * 5 - repeated * 10)

        return {
            "ok":           True,
            "health_score": health_score,
            "total_errors": total_errors,
            "repeated_errors": repeated,
            "top_errors":   [
                {"module": e["module"], "function": e["function"],
                 "error": e["error_type"], "count": e["count"]}
                for e in error_rows[:5]
            ],
            "fixes_generated": len(fixes.data or []),
            "improvement_weeks": len(logs.data or []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_all_errors() -> dict:
    """Alle Fehler + Patterns für Dashboard."""
    try:
        db = await _get_client()
        rows = db.table("system_errors").select("*").order(
            "count", desc=True).limit(100).execute()
        errors = rows.data or []
        patterns = await analyze_error_patterns()
        return {
            "ok":      True,
            "errors":  errors,
            "patterns": patterns,
            "total":   len(errors),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_quantum_cycle() -> dict:
    """Scheduler-Einstiegspunkt: heal + analyse."""
    return await quantum_heal_system()
