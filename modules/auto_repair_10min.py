#!/usr/bin/env python3
"""
Auto-Repair 10-Minuten-Wächter
================================
Läuft alle 10 Minuten. Prüft alles. Repariert sofort.
Sendet Telegram-Report über alle Reparaturen.

Checks (automatische Reparatur falls kaputt):
  1. Outreach-Emails — zu wenig gesendet → Batch triggern
  2. Shopify Conversion Booster — ScriptTag fehlt → neu injizieren
  3. Circuit Breakers — offen seit >15 Min (außer FB) → resetten
  4. Lead-Queue — weniger als 30 neue Leads → Mini-Research starten
  5. Scheduler-Tasks — kritische Tasks übersprungen → sofort ausführen
  6. Revenue-Tasks — DS24 + CRO > 3h nicht gelaufen → triggern
  7. SMTP-Rotation — prüfen ob Accounts konfiguriert
  8. DB-Gesundheit — SQLite-DBs zugänglich?
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("AutoRepair10")

_BASE = Path(__file__).parent.parent
_DATA = _BASE / "data"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
RAILWAY_URL    = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"
LOCAL_URL      = f"http://localhost:{os.getenv('PORT', '8888')}"

# Welche URL ist aktiv (Railway vs lokal)
_API_BASE      = RAILWAY_URL if os.getenv("RAILWAY_ENVIRONMENT") else LOCAL_URL


# ── Telegram ─────────────────────────────────────────────────────────────────

async def _tg(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT or not HAS_AIOHTTP:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text,
                      "parse_mode": "HTML", "disable_notification": True},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── HTTP Helper ───────────────────────────────────────────────────────────────

async def _get(path: str, base: str = "") -> Dict:
    base = base or _API_BASE
    if not HAS_AIOHTTP:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base}{path}",
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json(content_type=None)
    except Exception as e:
        log.debug("GET %s error: %s", path, e)
        return {}


async def _post(path: str, data: Dict = None, base: str = "") -> Dict:
    base = base or _API_BASE
    if not HAS_AIOHTTP:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{base}{path}", json=data or {},
                              headers={"Content-Type": "application/json"},
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json(content_type=None)
    except Exception as e:
        log.debug("POST %s error: %s", path, e)
        return {}


# ── State File (was zuletzt repariert) ───────────────────────────────────────

_STATE_FILE = _DATA / "auto_repair_state.json"

def _load_state() -> Dict:
    try:
        return json.loads(_STATE_FILE.read_text()) if _STATE_FILE.exists() else {}
    except Exception:
        return {}

def _save_state(state: Dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2))

def _last_action_minutes_ago(state: Dict, key: str) -> float:
    ts = state.get(key, 0)
    return (time.time() - ts) / 60


# ── CHECK 1: Outreach Emails ──────────────────────────────────────────────────

async def check_outreach(state: Dict, fixes: List[str]) -> Dict:
    stats = await _get("/api/mass-outreach/stats")
    if not stats:
        fixes.append("⚠️ Outreach-Stats nicht erreichbar")
        return state

    emails_today  = stats.get("emails_today", 0)
    leads_new     = stats.get("leads_new", 0)
    daily_limit   = stats.get("daily_limit", 1000)

    hour = datetime.now().hour
    expected_min  = max(0, (hour - 7) * 30)   # Ab 7 Uhr: ~30 Emails/Stunde erwartet

    if emails_today < expected_min and _last_action_minutes_ago(state, "outreach_trigger") > 15:
        r = await _post("/api/mass-outreach/send", {"limit": 200, "smart": True})
        if r.get("status") == "batch_started":
            state["outreach_trigger"] = time.time()
            fixes.append(f"📧 Outreach-Batch gestartet (war: {emails_today} < {expected_min} erwartet)")
    else:
        log.debug("Outreach OK: %d emails heute, %d neu", emails_today, leads_new)
    return state


# ── CHECK 2: Shopify Conversion Booster ──────────────────────────────────────

async def check_conversion_booster(state: Dict, fixes: List[str]) -> Dict:
    if _last_action_minutes_ago(state, "booster_check") < 60:
        return state  # Max 1x pro Stunde prüfen

    domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    if not domain or not token or not HAS_AIOHTTP:
        return state

    version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
    headers = {"X-Shopify-Access-Token": token}

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://{domain}/admin/api/{version}/script_tags.json?limit=250",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                data = await r.json(content_type=None)

        tags = data.get("script_tags", [])
        booster_live = any("bp-conversion-booster" in t.get("src", "") for t in tags)
        state["booster_check"] = time.time()

        if not booster_live:
            # Re-inject
            from modules.shopify_conversion_booster import run_conversion_boost
            result = await run_conversion_boost()
            if result.get("script", {}).get("ok"):
                state["booster_inject"] = time.time()
                fixes.append("🛍️ Shopify Conversion Booster neu injiziert (ScriptTag fehlte)")
            else:
                fixes.append(f"⚠️ Conversion Booster Inject fehlgeschlagen: {str(result)[:80]}")
        else:
            log.debug("Conversion Booster OK (%d ScriptTags)", len(tags))
    except Exception as e:
        log.warning("Booster-Check Fehler: %s", e)

    return state


# ── CHECK 3: Circuit Breakers ─────────────────────────────────────────────────

async def check_circuits(state: Dict, fixes: List[str]) -> Dict:
    health = await _get("/health")
    open_circuits = health.get("circuits_open", [])
    # Facebook-Circuit ist bekanntermaßen offen (Token expired) — ignorieren
    fixable = [c for c in open_circuits if c not in ("facebook", "fb")]

    if fixable and _last_action_minutes_ago(state, "circuit_reset") > 15:
        r = await _post("/api/circuit/reset", {})
        state["circuit_reset"] = time.time()
        fixes.append(f"⚡ Circuit Breaker resettet: {', '.join(fixable)}")
    elif fixable:
        log.debug("Circuit %s offen — zu früh zum Resetten", fixable)
    return state


# ── CHECK 4: Lead-Queue ───────────────────────────────────────────────────────

async def check_lead_queue(state: Dict, fixes: List[str]) -> Dict:
    stats = await _get("/api/mass-outreach/stats")
    leads_new = stats.get("leads_new", 999)

    if leads_new < 30 and _last_action_minutes_ago(state, "research_trigger") > 30:
        r = await _post("/api/mass-outreach/research", {})
        if r.get("status") in ("research_started", "ok"):
            state["research_trigger"] = time.time()
            fixes.append(f"🔍 Lead-Research gestartet (nur noch {leads_new} neue Leads)")
    return state


# ── CHECK 5: Revenue-Tasks (DS24 + CRO) ──────────────────────────────────────

async def check_revenue_tasks(state: Dict, fixes: List[str]) -> Dict:
    tasks_to_check = [
        ("ds24_traffic",  "ds24_trigger",  180),  # 3h
        ("cro_run",       "cro_trigger",    90),   # 1.5h
        ("github_blog",   "blog_trigger",  240),   # 4h
    ]
    for task_name, state_key, min_gap_min in tasks_to_check:
        if _last_action_minutes_ago(state, state_key) > min_gap_min:
            r = await _post("/api/scheduler/trigger", {"task": task_name})
            if r.get("status") == "ok":
                state[state_key] = time.time()
                fixes.append(f"▶️ Task '{task_name}' neu gestartet (>{min_gap_min}min nicht gelaufen)")
    return state


# ── CHECK 6: DB-Gesundheit ────────────────────────────────────────────────────

async def check_db_health(state: Dict, fixes: List[str]) -> Dict:
    dbs = [
        _DATA / "mass_outreach.db",
        _DATA / "ultra_acquisition.db",
    ]
    for db_path in dbs:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
        except Exception as e:
            fixes.append(f"💾 DB-Problem erkannt ({db_path.name}): {e}")
    return state


# ── CHECK 7: SMTP-Pool ────────────────────────────────────────────────────────

async def check_smtp_pool(state: Dict, fixes: List[str]) -> Dict:
    stats = await _get("/api/mass-outreach/stats")
    smtp_count = stats.get("smtp_accounts", 0)
    if smtp_count == 0:
        fixes.append("⚠️ Kein SMTP-Account konfiguriert! Bitte Env-Vars prüfen.")
    elif smtp_count < 3:
        fixes.append(f"⚠️ Nur {smtp_count} SMTP-Accounts aktiv — Kapazität niedrig!")
    return state


# ── CHECK 8: Outreach Gesamt-Tagesstatus ─────────────────────────────────────

async def check_daily_target(state: Dict, fixes: List[str]) -> Dict:
    stats = await _get("/api/mass-outreach/stats")
    emails_today = stats.get("emails_today", 0)
    daily_limit  = stats.get("daily_limit", 1000)
    hour = datetime.now().hour

    if hour >= 20 and emails_today < 200:
        fixes.append(
            f"📊 Tages-Warnung: Nur {emails_today}/{daily_limit} Emails bis {hour}:00 Uhr"
        )
    return state


# ── Haupt-Reparatur-Zyklus ────────────────────────────────────────────────────

async def run_repair_cycle() -> Dict:
    """Führt alle Checks durch und repariert automatisch."""
    start = time.time()
    state = _load_state()
    fixes: List[str] = []
    errors: List[str] = []

    checks = [
        ("Outreach",          check_outreach),
        ("Circuits",          check_circuits),
        ("Lead-Queue",        check_lead_queue),
        ("Revenue-Tasks",     check_revenue_tasks),
        ("DB-Gesundheit",     check_db_health),
        ("SMTP-Pool",         check_smtp_pool),
        ("Tages-Target",      check_daily_target),
        ("Conversion-Booster",check_conversion_booster),  # letzter (teurer Check)
    ]

    for name, fn in checks:
        try:
            state = await fn(state, fixes)
        except Exception as e:
            errors.append(f"❌ {name}: {e}")
            log.warning("AutoRepair check '%s' fehlgeschlagen: %s", name, e)

    _save_state(state)
    elapsed = time.time() - start

    result = {
        "fixes": fixes,
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
        "timestamp": datetime.now().isoformat(),
    }

    # Telegram-Report nur wenn etwas repariert oder Fehler
    if fixes or errors:
        lines = ["🔧 <b>Auto-Repair Report</b>"]
        if fixes:
            lines.append("\n<b>Repariert:</b>")
            lines.extend(f"  {f}" for f in fixes)
        if errors:
            lines.append("\n<b>Fehler:</b>")
            lines.extend(f"  {e}" for e in errors)
        lines.append(f"\n⏱️ {elapsed:.1f}s")
        await _tg("\n".join(lines))
        log.info("Auto-Repair: %d Fixes, %d Fehler", len(fixes), len(errors))
    else:
        log.debug("Auto-Repair: Alles OK (%.1fs)", elapsed)

    return result
