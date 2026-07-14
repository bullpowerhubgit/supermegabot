"""
Autonomous Pilot — vollautonomes Gehirn von SuperMegaBot
=========================================================
Orchestriert alle Module 24/7, heilt Fehler selbst, skaliert Winner.
Rudolf muss NIE manuell eingreifen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("AutonomousPilot")

_DB_PATH   = Path(__file__).parent.parent / "data" / "autonomous_pilot.db"
_STATE_PATH = Path(__file__).parent.parent / "data" / "autonomous_pilot.json"

# ── KPI-Ziele ─────────────────────────────────────────────────────────────────
KPI_TARGETS = {
    "emails_per_day":     1000,
    "social_posts_per_day":  5,
    "affiliate_per_week":    5,
    "circuits_open":         0,
    "lead_queue_min":      500,
}

# ── DB ────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS action_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      REAL,
            action  TEXT,
            result  TEXT,
            success INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS kpi_history (
            date          TEXT,
            emails_sent   INTEGER DEFAULT 0,
            social_posts  INTEGER DEFAULT 0,
            affiliate_pitches INTEGER DEFAULT 0,
            circuits_open INTEGER DEFAULT 0,
            revenue_eur   REAL DEFAULT 0,
            leads_found   INTEGER DEFAULT 0,
            calls         INTEGER DEFAULT 0,
            PRIMARY KEY (date)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            ts      REAL,
            reason  TEXT,
            action  TEXT,
            outcome TEXT
        );
    """)
    conn.commit()
    return conn


def _log_action(action: str, result: str, success: bool = True) -> None:
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO action_log (ts,action,result,success) VALUES (?,?,?,?)",
                (time.time(), action, str(result)[:500], 1 if success else 0)
            )
    except Exception:
        pass


# ── State ────────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        if _STATE_PATH.exists():
            return json.loads(_STATE_PATH.read_text())
    except Exception:
        pass
    return {
        "last_email_batch":    0,
        "last_research":       0,
        "last_traffic_blast":  0,
        "last_affiliate":      0,
        "last_meta_optimize":  0,
        "last_daily_report":   0,
        "email_daily_count":   0,
        "email_day":           "",
        "social_daily_count":  0,
        "social_day":          "",
        "affiliate_week_count": 0,
        "affiliate_week":      "",
        "outreach_limit":      333,
        "linkedin_limit":      50,
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.debug("State save error: %s", e)


# ── Telegram ─────────────────────────────────────────────────────────────────
async def _telegram(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── KPI Reads ────────────────────────────────────────────────────────────────
def _read_emails_today() -> int:
    try:
        db = Path(__file__).parent.parent / "data" / "mass_outreach.db"
        if not db.exists():
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT COUNT(*) FROM sent_emails WHERE date(sent_at)=? AND status='sent'",
            (today,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _read_leads_total() -> int:
    try:
        db = Path(__file__).parent.parent / "data" / "mass_outreach.db"
        if not db.exists():
            return 0
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status='new'"
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _read_social_posts_today() -> int:
    try:
        db = Path(__file__).parent.parent / "data" / "traffic_maximizer.db"
        if not db.exists():
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE date(posted_at)=?", (today,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _read_affiliate_this_week() -> int:
    try:
        db = Path(__file__).parent.parent / "data" / "affiliate_recruiter.db"
        if not db.exists():
            return 0
        conn = sqlite3.connect(str(db))
        row = conn.execute(
            "SELECT COUNT(*) FROM sent WHERE strftime('%W-%Y', sent_at)=strftime('%W-%Y','now')"
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _read_circuits_open() -> list:
    try:
        from modules.circuit_breaker import get_status
        st = get_status()
        return [k for k, v in st.items() if v.get("state") == "open"]
    except Exception:
        return []


def _read_stripe_revenue_today() -> float:
    try:
        cache = Path(__file__).parent.parent / "data" / "stripe_cache.json"
        if not cache.exists():
            return 0.0
        d = json.loads(cache.read_text())
        return float(d.get("today_revenue", 0))
    except Exception:
        return 0.0


# ── Actions ──────────────────────────────────────────────────────────────────
async def _trigger_outreach_batch(limit: int = 333) -> str:
    try:
        from modules.mass_outreach_1000 import run_send_batch
        result = await run_send_batch(batch_limit=limit)
        return f"batch OK: {result}"
    except Exception as e:
        return f"batch error: {e}"


async def _trigger_research() -> str:
    try:
        from modules.mass_outreach_1000 import run_research
        result = await run_research(session_limit=200)
        return f"research OK: {result}"
    except Exception as e:
        return f"research error: {e}"


async def _trigger_traffic_blast() -> str:
    try:
        from modules.traffic_maximizer import run_full_traffic_blast
        result = await run_full_traffic_blast()
        return f"traffic OK: {result}"
    except Exception as e:
        return f"traffic error: {e}"


async def _trigger_email_ai() -> str:
    try:
        from modules.email_ai_conversations import process_all_inboxes
        result = await process_all_inboxes(since_hours=1)
        return f"email_ai OK: {result}"
    except Exception as e:
        return f"email_ai error: {e}"


async def _trigger_affiliate_pitches(limit: int = 15) -> str:
    try:
        from modules.affiliate_recruiter import run_affiliate_campaign
        result = await run_affiliate_campaign(limit=limit)
        return f"affiliate OK: {result}"
    except Exception as e:
        return f"affiliate error: {e}"


async def _trigger_meta_optimize() -> str:
    try:
        from modules.meta_ads_engine import run_auto_optimize
        result = await run_auto_optimize()
        return f"meta_ads OK: {result}"
    except Exception as e:
        return f"meta_ads error: {e}"


async def _trigger_linkedin_outreach(limit: int = 50) -> str:
    try:
        from modules.linkedin_dm_outreach import run_daily_outreach
        result = await run_daily_outreach(limit=limit)
        return f"linkedin OK: {result}"
    except Exception as e:
        return f"linkedin error: {e}"


async def _reset_all_circuits() -> list:
    try:
        from modules.circuit_breaker import reset_all
        return reset_all()
    except Exception:
        return []


# ── Main Pilot ────────────────────────────────────────────────────────────────
class AutonomousPilot:
    def __init__(self):
        self.state = _load_state()
        self.now   = time.time()
        self.dt    = datetime.now()

    def _elapsed(self, key: str) -> float:
        return self.now - self.state.get(key, 0)

    def _today(self) -> str:
        return self.dt.strftime("%Y-%m-%d")

    def _week(self) -> str:
        return self.dt.strftime("%W-%Y")

    def _hour(self) -> int:
        return self.dt.hour

    def _weekday(self) -> int:
        return self.dt.weekday()  # 0=Monday

    async def _check_and_reset_circuits(self) -> str:
        open_circuits = _read_circuits_open()
        if open_circuits:
            reset = await _reset_all_circuits()
            msg = f"Circuit reset: {reset}"
            _log_action("circuit_reset", msg)
            await _telegram(f"⚡ Autonomous Pilot: Circuit Reset\n{reset}")
            return msg
        return "circuits OK"

    async def _trigger_outreach_if_behind(self) -> str:
        emails_today = _read_emails_today()
        if emails_today < KPI_TARGETS["emails_per_day"] and self._elapsed("last_email_batch") > 7200:
            remaining = KPI_TARGETS["emails_per_day"] - emails_today
            limit = min(self.state.get("outreach_limit", 333), remaining)
            result = await _trigger_outreach_batch(limit)
            self.state["last_email_batch"] = self.now
            _log_action("outreach_batch", result)
            return result
        return f"outreach OK ({_read_emails_today()}/{KPI_TARGETS['emails_per_day']})"

    async def _trigger_social_if_silent(self) -> str:
        posts_today = _read_social_posts_today()
        if posts_today < KPI_TARGETS["social_posts_per_day"] and self._elapsed("last_traffic_blast") > 3600:
            result = await _trigger_traffic_blast()
            self.state["last_traffic_blast"] = self.now
            _log_action("traffic_blast", result)
            return result
        return f"social OK ({posts_today}/{KPI_TARGETS['social_posts_per_day']})"

    async def _process_email_backlog(self) -> str:
        if self._elapsed("last_email_ai") > 900:  # 15 min
            result = await _trigger_email_ai()
            self.state["last_email_ai"] = self.now
            _log_action("email_ai", result)
            return result
        return "email_ai OK"

    async def heal_if_broken(self) -> dict:
        results = {}
        checks = [
            ("circuit_breakers",  self._check_and_reset_circuits),
            ("outreach_behind",   self._trigger_outreach_if_behind),
            ("social_silent",     self._trigger_social_if_silent),
            ("email_backlog",     self._process_email_backlog),
        ]
        for name, fn in checks:
            try:
                results[name] = await fn()
            except Exception as e:
                results[name] = f"error: {e}"
                _log_action(name, str(e), success=False)
        return results

    async def scale_up_winners(self) -> None:
        """Skaliert gewinnende Kanäle automatisch hoch."""
        try:
            emails = _read_emails_today()
            # Wenn Email gut läuft → mehr pro Batch
            if emails >= 900 and self.state.get("outreach_limit", 333) < 500:
                self.state["outreach_limit"] = 500
                await _telegram("📈 Autonomous Pilot: Outreach auf 500/Batch erhöht (>900 heute)")
                _log_action("scale_up", "outreach_limit → 500")
        except Exception:
            pass

    async def run_scheduled_tasks(self) -> list:
        """Zeitgesteuerte Aufgaben — prüft Uhrzeit und Wochentag."""
        triggered = []
        h = self._hour()

        # Outreach-Batches: 09:00, 13:00, 21:00
        if h in (9, 13, 21) and self._elapsed("last_email_batch") > 7000:
            result = await _trigger_outreach_batch(self.state.get("outreach_limit", 333))
            self.state["last_email_batch"] = self.now
            triggered.append(("outreach_batch", result))
            _log_action("scheduled_outreach", result)

        # Research: täglich 07:00 wenn Lead-Queue < 500
        if h == 7 and _read_leads_total() < KPI_TARGETS["lead_queue_min"] and self._elapsed("last_research") > 20 * 3600:
            result = await _trigger_research()
            self.state["last_research"] = self.now
            triggered.append(("research", result))
            _log_action("scheduled_research", result)

        # Traffic Blast: 09:00, 12:00, 18:00
        if h in (9, 12, 18) and self._elapsed("last_traffic_blast") > 3 * 3600:
            result = await _trigger_traffic_blast()
            self.state["last_traffic_blast"] = self.now
            triggered.append(("traffic_blast", result))
            _log_action("scheduled_traffic", result)

        # LinkedIn: täglich 10:00
        if h == 10 and self._elapsed("last_linkedin") > 20 * 3600:
            result = await _trigger_linkedin_outreach(self.state.get("linkedin_limit", 50))
            self.state["last_linkedin"] = self.now
            triggered.append(("linkedin", result))
            _log_action("scheduled_linkedin", result)

        # Affiliate: Montag + Donnerstag 11:00
        if h == 11 and self._weekday() in (0, 3) and _read_affiliate_this_week() < KPI_TARGETS["affiliate_per_week"]:
            if self._elapsed("last_affiliate") > 40 * 3600:
                result = await _trigger_affiliate_pitches(15)
                self.state["last_affiliate"] = self.now
                triggered.append(("affiliate", result))
                _log_action("scheduled_affiliate", result)

        # Meta Ads Optimize: täglich 10:00
        if h == 10 and self._elapsed("last_meta_optimize") > 20 * 3600:
            result = await _trigger_meta_optimize()
            self.state["last_meta_optimize"] = self.now
            triggered.append(("meta_optimize", result))
            _log_action("scheduled_meta", result)

        # Daily Report: täglich 20:00
        if h == 20 and self._elapsed("last_daily_report") > 20 * 3600:
            await self.send_daily_report()
            self.state["last_daily_report"] = self.now
            triggered.append(("daily_report", "sent"))

        return triggered

    async def send_daily_report(self) -> None:
        emails    = _read_emails_today()
        posts     = _read_social_posts_today()
        affiliates = _read_affiliate_this_week()
        leads     = _read_leads_total()
        revenue   = _read_stripe_revenue_today()
        open_cb   = _read_circuits_open()

        # KPI-Status
        email_icon   = "✅" if emails >= KPI_TARGETS["emails_per_day"] else "⚠️"
        social_icon  = "✅" if posts  >= KPI_TARGETS["social_posts_per_day"] else "⚠️"
        affil_icon   = "✅" if affiliates >= KPI_TARGETS["affiliate_per_week"] else "⚠️"
        circuit_icon = "✅" if not open_cb else "🔴"

        # Geplante Aktionen für morgen
        planned = []
        if emails < KPI_TARGETS["emails_per_day"]:
            planned.append(f"📧 {KPI_TARGETS['emails_per_day'] - emails} Emails nachsenden")
        if leads < KPI_TARGETS["lead_queue_min"]:
            planned.append("🔍 Lead-Research starten")
        planned.append("📱 Traffic Blast 09:00, 12:00, 18:00")
        planned.append("⚡ Kontinuierliche Selbstheilung alle 5 Min")

        msg = (
            f"🤖 <b>SuperMegaBot Tagesbericht — {self._today()}</b>\n\n"
            f"💰 Einnahmen heute: <b>€{revenue:.2f}</b>\n"
            f"{email_icon} Emails gesendet: <b>{emails}/{KPI_TARGETS['emails_per_day']}</b>\n"
            f"🔍 Lead-Queue: <b>{leads}</b>\n"
            f"{social_icon} Social Posts: <b>{posts}/{KPI_TARGETS['social_posts_per_day']}</b>\n"
            f"{affil_icon} Affiliate-Pitches (Woche): <b>{affiliates}/{KPI_TARGETS['affiliate_per_week']}</b>\n"
            f"{circuit_icon} Circuit Breaker: <b>{'0 offen' if not open_cb else str(open_cb)}</b>\n"
            f"\n🎯 <b>Morgen automatisch:</b>\n"
            + "\n".join(f"- {p}" for p in planned)
        )
        await _telegram(msg)

        # KPI in DB speichern
        try:
            with _db() as conn:
                conn.execute("""
                    INSERT INTO kpi_history
                      (date, emails_sent, social_posts, affiliate_pitches,
                       circuits_open, revenue_eur, leads_found)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(date) DO UPDATE SET
                      emails_sent=excluded.emails_sent,
                      social_posts=excluded.social_posts,
                      affiliate_pitches=excluded.affiliate_pitches,
                      circuits_open=excluded.circuits_open,
                      revenue_eur=excluded.revenue_eur,
                      leads_found=excluded.leads_found
                """, (self._today(), emails, posts, affiliates,
                      len(open_cb), revenue, leads))
        except Exception:
            pass

    async def run_autonomous_cycle(self) -> dict:
        """Hauptfunktion — wird alle 5 Minuten vom Scheduler aufgerufen."""
        log.info("AutonomousPilot cycle start")
        results = {"ts": self.now, "actions": [], "healed": {}, "scheduled": []}

        # 1. Selbstheilung
        try:
            healed = await self.heal_if_broken()
            results["healed"] = healed
        except Exception as e:
            log.error("heal_if_broken error: %s", e)

        # 2. Zeitgesteuerte Aufgaben
        try:
            scheduled = await self.run_scheduled_tasks()
            results["scheduled"] = scheduled
        except Exception as e:
            log.error("run_scheduled_tasks error: %s", e)

        # 3. Self-Scaling
        try:
            await self.scale_up_winners()
        except Exception as e:
            log.error("scale_up_winners error: %s", e)

        # State speichern
        _save_state(self.state)
        _log_action("cycle", json.dumps(results)[:400])

        log.info("AutonomousPilot cycle done: %d healed, %d scheduled",
                 len(results["healed"]), len(results["scheduled"]))
        return results

    def get_stats(self) -> dict:
        try:
            conn = _db()
            today_row = conn.execute(
                "SELECT * FROM kpi_history WHERE date=?", (self._today(),)
            ).fetchone()
            last_actions = conn.execute(
                "SELECT * FROM action_log ORDER BY ts DESC LIMIT 10"
            ).fetchall()
            conn.close()
            return {
                "today": dict(today_row) if today_row else {},
                "last_actions": [dict(r) for r in last_actions],
                "state": self.state,
            }
        except Exception as e:
            return {"error": str(e)}


# ── Scheduler-Entry ───────────────────────────────────────────────────────────
async def run_pilot_cycle() -> str:
    pilot = AutonomousPilot()
    result = await pilot.run_autonomous_cycle()
    healed = len([v for v in result.get("healed", {}).values() if "error" not in str(v)])
    sched  = len(result.get("scheduled", []))
    return f"AutonomousPilot: {healed} healed, {sched} scheduled tasks triggered"


def get_pilot_stats() -> dict:
    return AutonomousPilot().get_stats()
