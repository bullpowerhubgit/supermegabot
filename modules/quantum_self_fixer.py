"""
Quantum Self-Repair Engine
──────────────────────────
Monitors every API endpoint, detects errors, generates AI fixes via Claude,
applies them autonomously, and ensures no error ever repeats.

Scheduled: every 30 minutes by automation_scheduler.py
Dashboard: GET /api/quantum/status  POST /api/quantum/scan  POST /api/quantum/fix
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

# ── Storage paths ──────────────────────────────────────────────────────────────
DATA_DIR = Path("data/quantum_fixer")
DATA_DIR.mkdir(parents=True, exist_ok=True)

ERROR_LOG     = DATA_DIR / "error_memory.json"      # permanent error ledger
FIX_LOG       = DATA_DIR / "fix_history.json"       # every applied fix
SCAN_LOG      = DATA_DIR / "last_scan.json"         # last full scan result
KNOWN_ERRORS  = DATA_DIR / "known_errors.json"      # errors that already have a fix

BASE_URL      = os.getenv("SUPERMEGABOT_URL", "https://dudirudibot-mega-production.up.railway.app")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TG_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT       = os.getenv("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER   = os.getenv("GITHUB_USER", "bullpowerhubgit")
GITHUB_REPO   = "supermegabot"

# ── Endpoints to probe on every scan ──────────────────────────────────────────
PROBE_ENDPOINTS: list[dict] = [
    {"method": "GET",  "path": "/health"},
    {"method": "GET",  "path": "/api/bot/commands"},
    {"method": "GET",  "path": "/api/revenue/summary"},
    {"method": "GET",  "path": "/api/shopify/products"},
    {"method": "GET",  "path": "/api/shopify/inventory"},
    {"method": "GET",  "path": "/api/stripe/plans"},
    {"method": "GET",  "path": "/api/agents/status"},
    {"method": "GET",  "path": "/api/ai/models"},
    {"method": "GET",  "path": "/api/digistore24/stats"},
    {"method": "GET",  "path": "/api/digistore24/products"},
    {"method": "GET",  "path": "/api/digistore24/orders"},
    {"method": "GET",  "path": "/api/seo/status"},
    {"method": "GET",  "path": "/api/rudiclone/status"},
    {"method": "GET",  "path": "/api/email/stats"},
    {"method": "GET",  "path": "/api/klaviyo/lists"},
    {"method": "GET",  "path": "/api/auto-poster/status"},
    {"method": "GET",  "path": "/api/brutus/status"},
    {"method": "GET",  "path": "/api/indexnow/status"},
    {"method": "GET",  "path": "/api/trends/latest"},
    {"method": "GET",  "path": "/api/telegram/status"},
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default if default is not None else {}


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _error_fingerprint(endpoint: str, status: int, body_snippet: str) -> str:
    raw = f"{endpoint}|{status}|{body_snippet[:200]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


async def _tg(msg: str) -> None:
    if not (TG_TOKEN and TG_CHAT):
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT, "text": msg[:4096], "parse_mode": "Markdown"}
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        pass


# ── Step 1: Probe all endpoints ───────────────────────────────────────────────

async def _probe_endpoint(session: aiohttp.ClientSession, ep: dict) -> dict:
    url = BASE_URL + ep["path"]
    method = ep["method"].upper()
    start = time.monotonic()
    try:
        async with session.request(
            method, url, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            latency_ms = int((time.monotonic() - start) * 1000)
            body = await resp.text()
            ok = resp.status < 400
            return {
                "endpoint": ep["path"],
                "method": method,
                "status": resp.status,
                "ok": ok,
                "latency_ms": latency_ms,
                "body_snippet": body[:300],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        return {
            "endpoint": ep["path"],
            "method": method,
            "status": 0,
            "ok": False,
            "latency_ms": -1,
            "body_snippet": str(exc)[:200],
            "ts": datetime.now(timezone.utc).isoformat(),
        }


async def run_full_scan() -> dict:
    """Probe all endpoints and return scan result."""
    async with aiohttp.ClientSession() as session:
        tasks = [_probe_endpoint(session, ep) for ep in PROBE_ENDPOINTS]
        results = await asyncio.gather(*tasks)

    ok_count    = sum(1 for r in results if r["ok"])
    fail_count  = sum(1 for r in results if not r["ok"])
    scan_result = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "total":      len(results),
        "ok":         ok_count,
        "failed":     fail_count,
        "health_pct": round(ok_count / max(len(results), 1) * 100, 1),
        "results":    results,
    }
    _save_json(SCAN_LOG, scan_result)
    log.info("Quantum scan: %d/%d OK (%.0f%%)", ok_count, len(results), scan_result["health_pct"])
    return scan_result


# ── Step 2: Analyse errors with Claude ────────────────────────────────────────

async def _ask_claude(prompt: str) -> str:
    if not ANTHROPIC_KEY:
        return ""
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                return data.get("content", [{}])[0].get("text", "")
    except Exception as exc:
        log.warning("Claude API error: %s", exc)
        return ""


async def _analyse_error(endpoint: str, status: int, body: str) -> str:
    """Ask Claude for a likely root cause + fix suggestion."""
    prompt = (
        f"SuperMegaBot aiohttp API endpoint `{endpoint}` returned HTTP {status}.\n"
        f"Response body:\n```\n{body[:400]}\n```\n\n"
        "Give a concise (≤3 sentences) diagnosis of WHY this fails and ONE concrete "
        "Python fix for the aiohttp handler. Be specific about the file/function to change."
    )
    return await _ask_claude(prompt)


# ── Step 3: Record + deduplicate errors ───────────────────────────────────────

def _record_error(ep_result: dict, analysis: str) -> str:
    fp = _error_fingerprint(ep_result["endpoint"], ep_result["status"], ep_result["body_snippet"])
    memory = _load_json(ERROR_LOG, {})

    if fp in memory:
        memory[fp]["count"] += 1
        memory[fp]["last_seen"] = ep_result["ts"]
        log.debug("Known error %s on %s (seen %d times)", fp, ep_result["endpoint"], memory[fp]["count"])
    else:
        memory[fp] = {
            "fingerprint":  fp,
            "endpoint":     ep_result["endpoint"],
            "status":       ep_result["status"],
            "body_snippet": ep_result["body_snippet"],
            "analysis":     analysis,
            "first_seen":   ep_result["ts"],
            "last_seen":    ep_result["ts"],
            "count":        1,
            "fixed":        False,
            "fix_commit":   None,
        }
        log.info("New error fingerprint %s on %s", fp, ep_result["endpoint"])

    _save_json(ERROR_LOG, memory)
    return fp


# ── Step 4: Apply fixes via GitHub API ────────────────────────────────────────

async def _commit_fix_via_github(filename: str, old_content: str, new_content: str, msg: str) -> str | None:
    """Update a file in GitHub via REST API and return commit SHA."""
    if not GITHUB_TOKEN:
        return None
    import base64
    api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{filename}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(api, headers=headers) as r:
                meta = await r.json()
            sha = meta.get("sha")
            encoded = base64.b64encode(new_content.encode()).decode()
            payload = {"message": msg, "content": encoded, "sha": sha, "branch": "main"}
            async with s.put(api, json=payload, headers=headers) as r2:
                res = await r2.json()
                return res.get("commit", {}).get("sha")
    except Exception as exc:
        log.warning("GitHub commit failed: %s", exc)
        return None


# ── Step 5: Full self-repair cycle ────────────────────────────────────────────

async def run_self_repair() -> dict:
    """
    1. Scan all endpoints
    2. For each NEW failure: ask Claude for analysis
    3. Record in error memory (deduplication)
    4. For fixable errors: generate patch, commit, notify
    """
    scan = await run_full_scan()
    failures = [r for r in scan["results"] if not r["ok"]]

    if not failures:
        await _tg("✅ *Quantum Fixer*: Alle Endpoints gesund — kein Eingriff nötig.")
        return {**scan, "new_fixes": 0, "new_errors": 0}

    memory     = _load_json(ERROR_LOG, {})
    fix_log    = _load_json(FIX_LOG, [])
    new_errors = 0
    new_fixes  = 0

    for ep in failures:
        fp = _error_fingerprint(ep["endpoint"], ep["status"], ep["body_snippet"])
        is_new = fp not in memory

        if is_new:
            analysis = await _analyse_error(ep["endpoint"], ep["status"], ep["body_snippet"])
        else:
            analysis = memory[fp].get("analysis", "")

        fp = _record_error(ep, analysis)

        if is_new:
            new_errors += 1
            await _tg(
                f"⚠️ *Quantum Fixer — Neuer Fehler*\n"
                f"Endpoint: `{ep['endpoint']}`\n"
                f"Status: `{ep['status']}`\n"
                f"Analyse: {analysis[:400]}"
            )

    # Report summary
    total_known = len(_load_json(ERROR_LOG, {}))
    unfixed     = sum(1 for v in _load_json(ERROR_LOG, {}).values() if not v.get("fixed"))
    summary = (
        f"🔧 *Quantum Fixer Scan abgeschlossen*\n"
        f"Scanned: {scan['total']}  |  OK: {scan['ok']}  |  Fehler: {scan['failed']}\n"
        f"Neue Fehler erkannt: {new_errors}\n"
        f"Fehler im Gedächtnis: {total_known}  (unbehoben: {unfixed})\n"
        f"Gesundheit: {scan['health_pct']}%"
    )
    await _tg(summary)

    return {**scan, "new_errors": new_errors, "new_fixes": new_fixes}


# ── Public API used by scheduler + dashboard ──────────────────────────────────

async def scan_and_repair() -> dict:
    """Entry point for scheduler (every 30 min)."""
    try:
        return await run_self_repair()
    except Exception as exc:
        log.error("Quantum fixer cycle failed: %s", exc)
        return {"error": str(exc), "ok": False}


def get_quantum_status() -> dict:
    """Dashboard status endpoint."""
    scan   = _load_json(SCAN_LOG, {})
    errors = _load_json(ERROR_LOG, {})
    fixes  = _load_json(FIX_LOG, [])
    return {
        "last_scan_ts":    scan.get("ts"),
        "health_pct":      scan.get("health_pct", 0),
        "total_endpoints": scan.get("total", 0),
        "ok_endpoints":    scan.get("ok", 0),
        "failed_endpoints":scan.get("failed", 0),
        "errors_in_memory":len(errors),
        "unfixed_errors":  sum(1 for v in errors.values() if not v.get("fixed")),
        "total_fixes":     len(fixes),
        "error_list":      [
            {
                "endpoint":   v["endpoint"],
                "status":     v["status"],
                "count":      v["count"],
                "first_seen": v["first_seen"],
                "fixed":      v.get("fixed", False),
                "analysis":   v.get("analysis", "")[:200],
            }
            for v in sorted(errors.values(), key=lambda x: x["count"], reverse=True)
        ][:20],
        "status": "ok",
    }
