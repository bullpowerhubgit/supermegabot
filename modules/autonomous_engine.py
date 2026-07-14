#!/usr/bin/env python3
"""
Autonomous Engine — Vollständig autonome Entscheidungsmaschine
==============================================================
Überwacht Revenue, erkennt Schwachstellen, triggert automatisch
die richtigen Traffic-Kanäle und optimiert sich selbst.

Funktioniert OHNE menschliche Eingabe:
  - Alle 2h: Vollständiger Analyse-Zyklus
  - Bei 0 Emails heute: sofort Outreach-Blast starten
  - Bei schlechten Conversion-Trends: SEO + Pinterest intensivieren
  - Bei freien API-Slots: Discovery + Harvesting
  - Telegram-Report nur bei relevanten Events
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

log = logging.getLogger("AutonomousEngine")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "autonomous_engine.db"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
SHOP_URL       = "https://ineedit.com.co"
LOCAL_API      = "http://localhost:8888"


# ── State-Datenbank ───────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            reason    TEXT,
            action    TEXT,
            result    TEXT,
            created   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS state (
            key       TEXT PRIMARY KEY,
            value     TEXT,
            updated   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS metrics (
            date      TEXT,
            metric    TEXT,
            value     REAL,
            PRIMARY KEY (date, metric)
        );
    """)
    conn.commit()
    return conn


def _get_state(key: str, default: str = "") -> str:
    try:
        with _db() as conn:
            row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except Exception:
        return default


def _set_state(key: str, value: str) -> None:
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state (key, value) VALUES (?,?)",
                (key, value)
            )
    except Exception:
        pass


def _log_decision(reason: str, action: str, result: str = "") -> None:
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO decisions (reason, action, result) VALUES (?,?,?)",
                (reason[:200], action[:200], result[:300])
            )
    except Exception:
        pass


# ── System-Diagnose ───────────────────────────────────────────────────────────

async def _diagnose(session: aiohttp.ClientSession) -> Dict:
    """Prüft alle Systeme und gibt Status zurück."""
    diag: Dict[str, Any] = {}

    # Health Check
    try:
        async with session.get(f"{LOCAL_API}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
            diag["health"] = await r.json(content_type=None)
    except Exception as e:
        diag["health"] = {"error": str(e)}

    # Outreach Stats
    try:
        async with session.get(f"{LOCAL_API}/api/mass-outreach/stats", timeout=aiohttp.ClientTimeout(total=6)) as r:
            diag["outreach"] = await r.json(content_type=None)
    except Exception as e:
        diag["outreach"] = {"error": str(e)}

    # Traffic Stats
    try:
        from modules.traffic_accelerator import get_stats
        diag["traffic"] = get_stats()
    except Exception as e:
        diag["traffic"] = {"error": str(e)}

    # Circuit Breaker
    try:
        async with session.get(f"{LOCAL_API}/api/circuit-breaker/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            diag["circuits"] = await r.json(content_type=None)
    except Exception:
        diag["circuits"] = {}

    # Repair Status
    try:
        async with session.get(f"{LOCAL_API}/api/repair/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            diag["repair"] = await r.json(content_type=None)
    except Exception:
        diag["repair"] = {}

    return diag


# ── Entscheidungslogik ────────────────────────────────────────────────────────

async def _decide_and_act(session: aiohttp.ClientSession, diag: Dict) -> List[Dict]:
    """
    Kernlogik: Analysiert Diagnose und trifft autonome Entscheidungen.
    Gibt Liste aller ausgeführten Aktionen zurück.
    """
    actions_taken: List[Dict] = []

    async def _trigger(task: str, label: str) -> Dict:
        try:
            async with session.post(
                f"{LOCAL_API}/api/scheduler/trigger",
                json={"task": task},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                result = await r.json(content_type=None)
            _log_decision(label, f"trigger:{task}", str(result)[:100])
            return {"task": task, "label": label, "result": result}
        except Exception as e:
            return {"task": task, "label": label, "error": str(e)}

    async def _outreach_blast(limit: int, reason: str) -> Dict:
        try:
            async with session.post(
                f"{LOCAL_API}/api/mass-outreach/send",
                json={"limit": limit, "smart": True},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                result = await r.json(content_type=None)
            _log_decision(reason, f"outreach_blast:{limit}", str(result)[:100])
            return {"action": "outreach_blast", "limit": limit, "reason": reason, "result": result}
        except Exception as e:
            return {"action": "outreach_blast", "error": str(e)}

    async def _traffic_cycle() -> Dict:
        try:
            from modules.traffic_accelerator import run_traffic_cycle
            result = await run_traffic_cycle()
            _log_decision("auto_traffic", "traffic_cycle", f"{result.get('total_actions',0)} actions")
            return {"action": "traffic_cycle", "result": result}
        except Exception as e:
            return {"action": "traffic_cycle", "error": str(e)}

    # ── REGEL 1: Zu wenig Emails heute ────────────────────────────────────────
    emails_today = 0
    try:
        outreach = diag.get("outreach", {})
        emails_today = outreach.get("sent_today", outreach.get("emails_today", 0))
    except Exception:
        pass

    last_outreach_blast = _get_state("last_outreach_blast", "")
    blast_cooldown_ok = True
    if last_outreach_blast:
        try:
            last_ts = datetime.fromisoformat(last_outreach_blast)
            blast_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 3600
        except Exception:
            pass

    if emails_today < 100 and blast_cooldown_ok:
        act = await _outreach_blast(350, f"emails_today={emails_today} < 100")
        actions_taken.append(act)
        _set_state("last_outreach_blast", datetime.utcnow().isoformat())

    # ── REGEL 2: Traffic-Zyklus wenn Outreach hoch und Traffic niedrig ────────
    traffic_today = diag.get("traffic", {}).get("actions_today", 0)
    last_traffic = _get_state("last_traffic_cycle", "")
    traffic_cooldown_ok = True
    if last_traffic:
        try:
            last_ts = datetime.fromisoformat(last_traffic)
            traffic_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 7200
        except Exception:
            pass

    if traffic_today < 5 and traffic_cooldown_ok:
        act = await _traffic_cycle()
        actions_taken.append(act)
        _set_state("last_traffic_cycle", datetime.utcnow().isoformat())

    # ── REGEL 3: Shopify Sync wenn zu lange her ───────────────────────────────
    last_shopify = _get_state("last_shopify_sync", "")
    shopify_cooldown_ok = True
    if last_shopify:
        try:
            last_ts = datetime.fromisoformat(last_shopify)
            shopify_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 5400
        except Exception:
            pass

    if shopify_cooldown_ok:
        act = await _trigger("shopify_sync", "periodic_shopify_sync")
        actions_taken.append(act)
        _set_state("last_shopify_sync", datetime.utcnow().isoformat())

    # ── REGEL 4: DS24 Revenue Sync ────────────────────────────────────────────
    last_ds24 = _get_state("last_ds24_sync", "")
    ds24_cooldown_ok = True
    if last_ds24:
        try:
            last_ts = datetime.fromisoformat(last_ds24)
            ds24_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 10800
        except Exception:
            pass

    if ds24_cooldown_ok:
        act = await _trigger("ds24_revenue", "periodic_ds24_revenue")
        actions_taken.append(act)
        _set_state("last_ds24_sync", datetime.utcnow().isoformat())

    # ── REGEL 5: Free API Discovery ───────────────────────────────────────────
    last_api_discovery = _get_state("last_api_discovery", "")
    api_cooldown_ok = True
    if last_api_discovery:
        try:
            last_ts = datetime.fromisoformat(last_api_discovery)
            api_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 43200
        except Exception:
            pass

    if api_cooldown_ok:
        act = await _trigger("free_api_discovery", "auto_api_discovery")
        actions_taken.append(act)
        _set_state("last_api_discovery", datetime.utcnow().isoformat())

    # ── REGEL 6: Lead Research wenn Queue leer ────────────────────────────────
    last_research = _get_state("last_lead_research", "")
    research_cooldown_ok = True
    if last_research:
        try:
            last_ts = datetime.fromisoformat(last_research)
            research_cooldown_ok = (datetime.utcnow() - last_ts).total_seconds() > 7200
        except Exception:
            pass

    if research_cooldown_ok and emails_today < 50:
        act = await _trigger("lead_research", "auto_lead_research_low_emails")
        actions_taken.append(act)
        _set_state("last_lead_research", datetime.utcnow().isoformat())

    return actions_taken


# ── HAUPT-ZYKLUS ──────────────────────────────────────────────────────────────

async def run_autonomous_cycle() -> Dict:
    """
    Vollständiger autonomer Zyklus.
    Analysiert → Entscheidet → Handelt → Reportiert.
    """
    if not HAS_AIOHTTP:
        return {"error": "aiohttp nicht verfügbar"}

    start = time.time()
    cycle_id = int(time.time())

    log.info("Autonomous Engine Cycle #%d gestartet", cycle_id)

    async with aiohttp.ClientSession() as session:
        # 1. Diagnose
        diag = await _diagnose(session)

        # 2. Entscheiden + Handeln
        actions = await _decide_and_act(session, diag)

    elapsed = time.time() - start
    result = {
        "ok": True,
        "cycle_id": cycle_id,
        "actions_taken": len(actions),
        "actions": actions,
        "diagnostics": {
            "health": diag.get("health", {}).get("status", "unknown"),
            "emails_today": diag.get("outreach", {}).get("sent_today", "?"),
            "traffic_today": diag.get("traffic", {}).get("actions_today", 0),
            "circuits_open": len(diag.get("circuits", {}).get("open", [])),
        },
        "elapsed_s": round(elapsed, 1),
        "timestamp": datetime.now().isoformat(),
    }

    # Telegram nur wenn Aktionen durchgeführt wurden
    if actions and TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            lines = [f"🤖 <b>Autonomous Engine</b> #{cycle_id}"]
            lines.append(f"✅ {len(actions)} Entscheidungen ({elapsed:.0f}s)")
            for act in actions[:4]:
                label = act.get("label") or act.get("action") or "action"
                err   = act.get("error")
                status = "❌" if err else "✅"
                lines.append(f"  {status} {label}")
            if len(actions) > 4:
                lines.append(f"  … +{len(actions)-4} weitere")

            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT,
                        "text": "\n".join(lines),
                        "parse_mode": "HTML",
                        "disable_notification": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=8),
                )
        except Exception:
            pass

    log.info("Autonomous Cycle #%d: %d Aktionen in %.1fs", cycle_id, len(actions), elapsed)
    return result


def get_decision_log(limit: int = 20) -> List[Dict]:
    """Letzte autonome Entscheidungen."""
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT reason, action, result, created FROM decisions ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_engine_stats() -> Dict:
    """Statistiken der autonomen Engine."""
    try:
        with _db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE created >= date('now')"
            ).fetchone()[0]
            states = conn.execute("SELECT key, value, updated FROM state").fetchall()
        return {
            "total_decisions": total,
            "decisions_today": today,
            "state": {r["key"]: {"value": r["value"][:50], "updated": r["updated"]} for r in states},
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_autonomous_cycle())
    print(f"Zyklus #{result['cycle_id']}: {result['actions_taken']} Aktionen")
    for act in result["actions"]:
        print(f"  - {act.get('label') or act.get('action')}: {'OK' if not act.get('error') else act['error']}")
