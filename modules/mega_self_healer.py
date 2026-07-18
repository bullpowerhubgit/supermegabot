#!/usr/bin/env python3
"""
SuperMegaBot — MegaSelfHealer
Production-grade self-healing engine.

Components:
  1. API_HEALTH_CHECKS  — 15 platforms polled every 5 minutes
  2. TASK_MONITOR       — SQLite scheduler.db audit: stuck + failing tasks
  3. REVENUE_CHECKER    — live revenue from Stripe, Klaviyo, DS24
  4. TELEGRAM_ALERTER   — structured hourly + critical-event alerts
  5. AUTO_FIX_ACTIONS   — Klaviyo 401, stuck tasks, DB lock, env reload
  6. Routes             — /api/health/all  /api/healer/log
                          /api/healer/run  /api/revenue/summary

Run standalone:  python3 modules/mega_self_healer.py
Integrate:       from modules.mega_self_healer import create_healer_app
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import web

try:
    from modules.ai_client import ai_complete
except ImportError:
    ai_complete = None  # type: ignore[assignment]

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HEALER_LOG_PATH    = DATA_DIR / "mega_healer_log.json"
HEALER_STATE_PATH  = DATA_DIR / "mega_healer_state.json"
SCHEDULER_DB_PATH  = DATA_DIR / "scheduler.db"

# ── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MegaHealer] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "mega_healer.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("mega_self_healer")

# ── Env helpers ────────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _reload_env() -> None:
    """Re-read .env file into os.environ at runtime (hot credential reload)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ[k] = v
        log.info(".env reloaded into os.environ")
    except Exception as exc:
        log.warning("env reload failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# 1. API HEALTH CHECKS
# ══════════════════════════════════════════════════════════════════════════════

HEALTH_CHECK_INTERVAL = 300  # 5 minutes


class PlatformHealth:
    """Single API health probe result."""

    __slots__ = ("platform", "ok", "latency_ms", "error", "checked_at")

    def __init__(
        self,
        platform: str,
        ok: bool,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        self.platform   = platform
        self.ok         = ok
        self.latency_ms = round(latency_ms, 1)
        self.error      = error
        self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok":         self.ok,
            "latency_ms": self.latency_ms,
            "error":      self.error,
            "checked_at": self.checked_at,
        }


async def _probe(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    **kwargs: Any,
) -> Tuple[bool, float, Optional[str]]:
    """Fire a single HTTP probe. Returns (ok, latency_ms, error_str)."""
    t0 = time.monotonic()
    try:
        async with session.request(method, url, **kwargs) as resp:
            latency = (time.monotonic() - t0) * 1000
            if resp.status < 500:
                return True, latency, None
            body = await resp.text()
            return False, latency, f"HTTP {resp.status}: {body[:120]}"
    except asyncio.TimeoutError:
        return False, (time.monotonic() - t0) * 1000, "timeout"
    except Exception as exc:
        return False, (time.monotonic() - t0) * 1000, str(exc)[:120]


async def _ai_complete_probe() -> Tuple[bool, float, Optional[str]]:
    """Check AI availability via ai_client (Groq → DeepSeek → OpenRouter → Anthropic fallback)."""
    if ai_complete is None:
        return False, 0.0, "ai_client module not available"
    t0 = time.monotonic()
    try:
        result = await ai_complete(prompt="ping", system="Reply with: pong", max_tokens=1)
        latency = (time.monotonic() - t0) * 1000
        if result:
            return True, latency, None
        return False, latency, "empty response from ai_complete"
    except Exception as exc:
        return False, (time.monotonic() - t0) * 1000, str(exc)[:120]


async def check_all_platforms() -> Dict[str, PlatformHealth]:
    """
    Poll all 15 platforms and return a mapping of platform → PlatformHealth.
    Every network call has a hard 10-second timeout.
    """
    timeout = aiohttp.ClientTimeout(total=10)
    results: Dict[str, PlatformHealth] = {}

    # ── gather env once ───────────────────────────────────────────────────────
    shopify_domain  = _env("SHOPIFY_SHOP_DOMAIN")
    shopify_token   = _env("SHOPIFY_ADMIN_API_TOKEN", _env("SHOPIFY_ACCESS_TOKEN"))
    shopify_ver     = _env("SHOPIFY_API_VERSION", "2024-01")
    stripe_key      = _env("STRIPE_SECRET_KEY")
    anthropic_key   = _env("ANTHROPIC_API_KEY")
    openai_key      = _env("OPENAI_API_KEY")
    klaviyo_key     = _env("KLAVIYO_API_KEY")
    supabase_url    = _env("SUPABASE_URL")
    supabase_anon   = _env("SUPABASE_ANON_KEY")
    tg_token        = _env("TELEGRAM_BOT_TOKEN")
    meta_token      = _env("META_ACCESS_TOKEN", _env("FACEBOOK_PAGE_TOKEN_AIITEC"))
    linkedin_token  = _env("LINKEDIN_ACCESS_TOKEN")
    twilio_sid      = _env("TWILIO_ACCOUNT_SID")
    twilio_auth     = _env("TWILIO_AUTH_TOKEN")
    sendgrid_key    = _env("SENDGRID_API_KEY")
    printify_token  = _env("PRINTIFY_API_TOKEN", _env("PRINTIFY_TOKEN"))
    youtube_key     = _env("YOUTUBE_API_KEY")
    ds24_key        = _env("DIGISTORE24_API_KEY")

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def run(name: str, coro) -> None:
            ok, ms, err = await coro
            results[name] = PlatformHealth(name, ok, ms, err)

        probes = [
            # 1. Shopify
            run("shopify", _probe(
                session, "GET",
                f"https://{shopify_domain}/admin/api/{shopify_ver}/shop.json",
                headers={"X-Shopify-Access-Token": shopify_token},
            ) if shopify_domain and shopify_token else _fake_miss("shopify_creds_missing")),

            # 2. Stripe
            run("stripe", _probe(
                session, "GET",
                "https://api.stripe.com/v1/balance",
                headers={"Authorization": f"Bearer {stripe_key}"},
            ) if stripe_key else _fake_miss("stripe_key_missing")),

            # 3. Anthropic — routed via ai_client (Groq→DeepSeek→OpenRouter→Anthropic)
            run("anthropic", _ai_complete_probe()
                if anthropic_key else _fake_miss("anthropic_key_missing")),

            # 4. OpenAI — routed via ai_client (Groq→DeepSeek→OpenRouter→Anthropic)
            run("openai", _ai_complete_probe()
                if openai_key else _fake_miss("openai_key_missing")),

            # 5. Klaviyo
            run("klaviyo", _probe(
                session, "GET",
                "https://a.klaviyo.com/api/lists/",
                headers={
                    "Authorization": f"Klaviyo-API-Key {klaviyo_key}",
                    "revision": "2024-02-15",
                },
            ) if klaviyo_key else _fake_miss("klaviyo_key_missing")),

            # 6. Supabase
            run("supabase", _probe(
                session, "GET",
                f"{supabase_url}/rest/v1/",
                headers={
                    "apikey": supabase_anon,
                    "Authorization": f"Bearer {supabase_anon}",
                },
            ) if supabase_url and supabase_anon else _fake_miss("supabase_creds_missing")),

            # 7. Telegram
            run("telegram", _probe(
                session, "GET",
                f"https://api.telegram.org/bot{tg_token}/getMe",
            ) if tg_token else _fake_miss("telegram_token_missing")),

            # 8. Meta / Facebook
            run("meta", _probe(
                session, "GET",
                f"https://graph.facebook.com/me?fields=id&access_token={meta_token}",
            ) if meta_token else _fake_miss("meta_token_missing")),

            # 9. LinkedIn
            run("linkedin", _probe(
                session, "GET",
                "https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {linkedin_token}"},
            ) if linkedin_token else _fake_miss("linkedin_token_missing")),

            # 10. Twilio
            run("twilio", _probe(
                session, "GET",
                f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}.json",
                auth=aiohttp.BasicAuth(twilio_sid, twilio_auth),
            ) if twilio_sid and twilio_auth else _fake_miss("twilio_creds_missing")),

            # 11. SendGrid
            run("sendgrid", _probe(
                session, "GET",
                "https://api.sendgrid.com/v3/scopes",
                headers={"Authorization": f"Bearer {sendgrid_key}"},
            ) if sendgrid_key else _fake_miss("sendgrid_key_missing")),

            # 12. Printify
            run("printify", _probe(
                session, "GET",
                "https://api.printify.com/v1/shops.json",
                headers={"Authorization": f"Bearer {printify_token}"},
            ) if printify_token else _fake_miss("printify_token_missing")),

            # 13. YouTube
            run("youtube", _probe(
                session, "GET",
                f"https://www.googleapis.com/youtube/v3/channels?mine=true&part=id",
                headers={"Authorization": f"Bearer {youtube_key}"},
            ) if youtube_key else _fake_miss("youtube_key_missing")),

            # 14. DS24
            run("ds24", _probe(
                session, "GET",
                f"https://www.digistore24.com/api/call/listTransactions/JSON/?api_key={ds24_key}",
            ) if ds24_key else _fake_miss("ds24_key_missing")),

            # 15. Self / local dashboard
            run("dashboard", _probe(
                session, "GET",
                f"http://localhost:{_env('DASHBOARD_PORT', '8888')}/health",
            )),
        ]

        await asyncio.gather(*probes, return_exceptions=True)

    return results


async def _fake_miss(reason: str) -> Tuple[bool, float, str]:
    """Return a failed probe immediately when credentials are absent."""
    return False, 0.0, reason


# ══════════════════════════════════════════════════════════════════════════════
# 2. TASK MONITOR
# ══════════════════════════════════════════════════════════════════════════════

TASK_RESTART_ENDPOINT = (
    f"http://localhost:{_env('DASHBOARD_PORT', '8888')}/api/tasks/restart"
)


class TaskMonitor:
    """
    Reads data/scheduler.db and identifies:
     - Tasks that have not run in > 2× their observed average interval.
     - Tasks whose last 3 consecutive runs all failed.
    """

    def __init__(self, db_path: Path = SCHEDULER_DB_PATH) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def get_stuck_tasks(self, stale_hours: float = 2.0) -> List[Dict[str, Any]]:
        """
        Return tasks whose last successful run is older than `stale_hours`.
        We compute per-task median run interval; a task is 'stuck' when
        time-since-last-run > max(stale_hours, 2 * median_interval).
        """
        if not self.db_path.exists():
            return []

        stuck: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        try:
            conn = self._connect()
            rows = conn.execute(
                """
                SELECT task_name,
                       ran_at,
                       success
                FROM   task_runs
                WHERE  ran_at >= datetime('now', '-7 days')
                ORDER  BY task_name, ran_at
                """
            ).fetchall()
            conn.close()
        except sqlite3.OperationalError as exc:
            log.warning("task_monitor DB error: %s", exc)
            return []

        # Group by task name
        by_task: Dict[str, List[datetime]] = defaultdict(list)
        latest_run: Dict[str, datetime] = {}
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["ran_at"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            by_task[row["task_name"]].append(ts)
            if row["task_name"] not in latest_run or ts > latest_run[row["task_name"]]:
                latest_run[row["task_name"]] = ts

        for task_name, run_times in by_task.items():
            run_times.sort()
            last = latest_run[task_name]
            age_h = (now - last).total_seconds() / 3600

            # Compute median interval
            if len(run_times) >= 2:
                gaps = [
                    (run_times[i + 1] - run_times[i]).total_seconds()
                    for i in range(len(run_times) - 1)
                ]
                gaps.sort()
                median_gap_h = gaps[len(gaps) // 2] / 3600
                threshold_h = max(stale_hours, 2.0 * median_gap_h)
            else:
                threshold_h = stale_hours

            if age_h > threshold_h:
                stuck.append(
                    {
                        "task":        task_name,
                        "last_run":    last.isoformat(),
                        "age_hours":   round(age_h, 2),
                        "threshold_h": round(threshold_h, 2),
                        "status":      "stuck",
                    }
                )

        return stuck

    def get_failing_tasks(self, consecutive: int = 3) -> List[Dict[str, Any]]:
        """Return tasks whose last `consecutive` runs all have success=0."""
        if not self.db_path.exists():
            return []

        failing: List[Dict[str, Any]] = []

        try:
            conn = self._connect()
            task_names = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT task_name FROM task_runs "
                    "WHERE ran_at >= datetime('now', '-2 days')"
                ).fetchall()
            ]
        except sqlite3.OperationalError as exc:
            log.warning("task_monitor get_failing_tasks DB error: %s", exc)
            return []

        for name in task_names:
            try:
                rows = conn.execute(
                    "SELECT success FROM task_runs "
                    "WHERE task_name = ? ORDER BY ran_at DESC LIMIT ?",
                    (name, consecutive),
                ).fetchall()
            except sqlite3.OperationalError:
                continue

            if len(rows) >= consecutive and all(r["success"] == 0 for r in rows):
                failing.append({"task": name, "consecutive_failures": consecutive})

        conn.close()
        return failing

    async def restart_task(self, task_name: str) -> bool:
        """POST to the dashboard's restart endpoint."""
        url = f"{TASK_RESTART_ENDPOINT}/{task_name}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=8)
            ) as session:
                async with session.post(url) as resp:
                    if resp.status < 300:
                        log.info("restarted task %s via dashboard", task_name)
                        return True
                    body = await resp.text()
                    log.warning(
                        "restart %s returned %s: %s", task_name, resp.status, body[:80]
                    )
                    return False
        except Exception as exc:
            log.error("restart %s failed: %s", task_name, exc)
            return False

    def summary(self) -> Dict[str, Any]:
        stuck   = self.get_stuck_tasks()
        failing = self.get_failing_tasks()
        return {
            "stuck_tasks":   stuck,
            "failing_tasks": failing,
            "stuck_count":   len(stuck),
            "failing_count": len(failing),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 3. REVENUE CHECKER
# ══════════════════════════════════════════════════════════════════════════════


class RevenueChecker:
    """Query live APIs for actual revenue numbers."""

    async def stripe_revenue(self) -> Dict[str, Any]:
        key = _env("STRIPE_SECRET_KEY")
        if not key:
            return {"error": "STRIPE_SECRET_KEY missing", "total_eur": 0.0}

        yesterday = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        headers   = {"Authorization": f"Bearer {key}"}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=12)
        ) as session:
            # Balance
            balance_data: Dict[str, Any] = {}
            try:
                async with session.get(
                    "https://api.stripe.com/v1/balance", headers=headers
                ) as r:
                    if r.status == 200:
                        balance_data = await r.json()
            except Exception as exc:
                log.warning("stripe balance error: %s", exc)

            # Recent charges (last 24 h)
            charges_total = 0.0
            charges_count = 0
            try:
                async with session.get(
                    "https://api.stripe.com/v1/charges",
                    headers=headers,
                    params={
                        "limit":          "100",
                        "created[gte]":   str(yesterday),
                    },
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        for ch in data.get("data", []):
                            if ch.get("paid") and not ch.get("refunded"):
                                charges_total += ch.get("amount", 0) / 100
                                charges_count += 1
            except Exception as exc:
                log.warning("stripe charges error: %s", exc)

        # Available balance (EUR preferred)
        avail_eur = 0.0
        for entry in balance_data.get("available", []):
            if entry.get("currency") == "eur":
                avail_eur = entry.get("amount", 0) / 100

        return {
            "balance_available_eur": avail_eur,
            "charges_24h_eur":       round(charges_total, 2),
            "charges_24h_count":     charges_count,
            "total_eur":             round(charges_total, 2),
        }

    async def klaviyo_revenue(self) -> Dict[str, Any]:
        key = _env("KLAVIYO_API_KEY")
        if not key:
            return {"error": "KLAVIYO_API_KEY missing", "total_eur": 0.0}

        headers = {
            "Authorization": f"Klaviyo-API-Key {key}",
            "revision":      "2024-02-15",
        }

        campaigns_sent   = 0
        campaigns_draft  = 0
        estimated_reach  = 0

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12)
            ) as session:
                async with session.get(
                    "https://a.klaviyo.com/api/campaigns/",
                    headers=headers,
                    params={"filter": "equals(channel,'email')"},
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        for camp in data.get("data", []):
                            status = (
                                camp.get("attributes", {}).get("status", "").lower()
                            )
                            if status == "sent":
                                campaigns_sent += 1
                            elif status in ("draft", "scheduled"):
                                campaigns_draft += 1
        except Exception as exc:
            log.warning("klaviyo campaigns error: %s", exc)

        return {
            "campaigns_sent":   campaigns_sent,
            "campaigns_draft":  campaigns_draft,
            "estimated_reach":  estimated_reach,
            "total_eur":        0.0,  # Klaviyo doesn't expose revenue directly
        }

    async def ds24_revenue(self) -> Dict[str, Any]:
        key = _env("DIGISTORE24_API_KEY")
        if not key:
            return {"error": "DIGISTORE24_API_KEY missing", "total_eur": 0.0}

        total_eur   = 0.0
        count       = 0
        raw_error   = None

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(
                    "https://www.digistore24.com/api/call/listTransactions/JSON/",
                    params={
                        "api_key":    key,
                        "date_range": "last_30_days",
                        "status":     "complete",
                    },
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        txns = data.get("data", {}).get("transactions", [])
                        for t in txns:
                            amount = float(t.get("amount", 0) or 0)
                            total_eur += amount
                            count += 1
                    else:
                        raw_error = f"HTTP {r.status}"
        except Exception as exc:
            raw_error = str(exc)[:80]
            log.warning("ds24 revenue error: %s", exc)

        return {
            "transactions_30d": count,
            "total_eur":        round(total_eur, 2),
            "error":            raw_error,
        }

    async def shopify_revenue(self) -> Dict[str, Any]:
        domain  = _env("SHOPIFY_SHOP_DOMAIN")
        token   = _env("SHOPIFY_ADMIN_API_TOKEN", _env("SHOPIFY_ACCESS_TOKEN"))
        version = _env("SHOPIFY_API_VERSION", "2024-01")

        if not domain or not token:
            return {"error": "shopify_creds_missing", "total_eur": 0.0}

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        total_eur = 0.0
        count     = 0

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(
                    f"https://{domain}/admin/api/{version}/orders.json",
                    headers={"X-Shopify-Access-Token": token},
                    params={
                        "status":          "any",
                        "created_at_min":  yesterday,
                        "financial_status": "paid",
                        "limit":           "250",
                    },
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        for order in data.get("orders", []):
                            total_eur += float(
                                order.get("total_price", 0) or 0
                            )
                            count += 1
        except Exception as exc:
            log.warning("shopify revenue error: %s", exc)
            return {"error": str(exc)[:80], "total_eur": 0.0}

        return {
            "orders_24h":   count,
            "total_eur":    round(total_eur, 2),
        }

    async def all_revenue(self) -> Dict[str, Any]:
        shopify, stripe, klaviyo, ds24 = await asyncio.gather(
            self.shopify_revenue(),
            self.stripe_revenue(),
            self.klaviyo_revenue(),
            self.ds24_revenue(),
            return_exceptions=True,
        )

        def _safe(result: Any) -> Dict[str, Any]:
            if isinstance(result, Exception):
                return {"error": str(result), "total_eur": 0.0}
            return result  # type: ignore[return-value]

        shopify  = _safe(shopify)
        stripe   = _safe(stripe)
        klaviyo  = _safe(klaviyo)
        ds24     = _safe(ds24)

        grand_total = (
            shopify.get("total_eur", 0.0)
            + stripe.get("total_eur", 0.0)
            + ds24.get("total_eur", 0.0)
        )

        return {
            "shopify_revenue":   shopify,
            "stripe_revenue":    stripe,
            "klaviyo_stats":     klaviyo,
            "ds24_revenue":      ds24,
            "total_eur":         round(grand_total, 2),
            "timestamp":         datetime.now(timezone.utc).isoformat(),
        }


# ══════════════════════════════════════════════════════════════════════════════
# 4. TELEGRAM ALERTER
# ══════════════════════════════════════════════════════════════════════════════


class TelegramAlerter:
    """Send structured status and critical-event alerts via Telegram Bot API."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self) -> None:
        self.bot_token   = _env("TELEGRAM_BOT_TOKEN")
        self.chat_id     = _env("TELEGRAM_CHAT_ID")
        self._last_hourly: Optional[datetime] = None

    @property
    def _enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send(self, text: str) -> bool:
        if not self._enabled:
            log.warning("Telegram alerter disabled — TELEGRAM_BOT_TOKEN or CHAT_ID missing")
            return False
        url = f"{self.BASE_URL}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body = await resp.text()
                    log.warning("telegram send failed %s: %s", resp.status, body[:120])
                    return False
        except Exception as exc:
            log.error("telegram send exception: %s", exc)
            return False

    async def alert_platform_down(self, platform: str, error: str) -> None:
        text = (
            f"🔴 <b>CRITICAL: {platform.upper()} DOWN</b>\n"
            f"<code>{error}</code>\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        await self.send(text)

    async def alert_revenue_zero(self, hours: int = 48) -> None:
        text = (
            f"⚠️ <b>REVENUE ALERT</b>\n"
            f"No revenue recorded for {hours}h\n"
            f"Check Shopify, Stripe, DS24.\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        await self.send(text)

    async def hourly_summary(
        self,
        health: Dict[str, PlatformHealth],
        revenue: Dict[str, Any],
        tasks: Dict[str, Any],
        actions_taken: List[str],
    ) -> None:
        now = datetime.now(timezone.utc)
        # Throttle to once per hour
        if (
            self._last_hourly
            and (now - self._last_hourly).total_seconds() < 3500
        ):
            return

        ok_count    = sum(1 for h in health.values() if h.ok)
        total_count = len(health)
        down_names  = [n for n, h in health.items() if not h.ok]

        status_icon = "🟢" if ok_count == total_count else (
            "🔴" if ok_count < total_count // 2 else "🟡"
        )

        down_line = (
            f"\n🔴 Down: {', '.join(down_names)}" if down_names else ""
        )
        fix_line = (
            f"\n🔧 Actions: {'; '.join(actions_taken[:3])}"
            if actions_taken else ""
        )
        stuck_line = (
            f"\n⚠️ Stuck tasks: {tasks.get('stuck_count', 0)}"
            " | Failing: "
            f"{tasks.get('failing_count', 0)}"
        ) if tasks.get("stuck_count") or tasks.get("failing_count") else ""

        text = (
            f"{status_icon} <b>SuperMegaBot Status</b>\n"
            f"🔌 Platforms: {ok_count}/{total_count} online"
            f"{down_line}\n"
            f"💶 Revenue (24h): €{revenue.get('total_eur', 0.0):.2f}\n"
            f"📊 Tasks: {total_count - tasks.get('stuck_count', 0)}"
            f"/{total_count} healthy"
            f"{stuck_line}"
            f"{fix_line}\n"
            f"🕐 {now.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        sent = await self.send(text)
        if sent:
            self._last_hourly = now


# ══════════════════════════════════════════════════════════════════════════════
# 5. AUTO-FIX ACTIONS
# ══════════════════════════════════════════════════════════════════════════════


class AutoFixer:
    """
    Apply targeted repairs based on health check results and task monitor data.
    Every action is recorded to the heal log.
    """

    def __init__(self, log_path: Path = HEALER_LOG_PATH) -> None:
        self.log_path = log_path
        self._load_log()

    def _load_log(self) -> None:
        try:
            self._heal_log: List[Dict[str, Any]] = (
                json.loads(self.log_path.read_text())
                if self.log_path.exists()
                else []
            )
        except Exception:
            self._heal_log = []

    def _save_log(self) -> None:
        try:
            self.log_path.write_text(
                json.dumps(self._heal_log[-500:], indent=2, default=str)
            )
        except Exception as exc:
            log.warning("heal log save failed: %s", exc)

    def record(
        self,
        platform: str,
        problem: str,
        action: str,
        success: bool,
        detail: str = "",
    ) -> None:
        entry = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "problem":  problem,
            "action":   action,
            "success":  success,
            "detail":   detail[:200],
        }
        self._heal_log.append(entry)
        self._save_log()
        level = logging.INFO if success else logging.WARNING
        log.log(level, "[fix] %s / %s → %s (%s)", platform, problem, action, "OK" if success else "FAIL")

    def last_n(self, n: int = 50) -> List[Dict[str, Any]]:
        return self._heal_log[-n:]

    # ── specific fixers ───────────────────────────────────────────────────────

    async def fix_klaviyo_401(self) -> bool:
        """Reload .env and verify new key works."""
        _reload_env()
        new_key = _env("KLAVIYO_API_KEY")
        if not new_key:
            self.record("klaviyo", "401_unauthorized", "env_reload", False, "key still empty after reload")
            return False

        # Quick verification
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as session:
            try:
                async with session.get(
                    "https://a.klaviyo.com/api/lists/",
                    headers={
                        "Authorization": f"Klaviyo-API-Key {new_key}",
                        "revision":      "2024-02-15",
                    },
                ) as r:
                    ok = r.status < 400
                    self.record(
                        "klaviyo",
                        "401_unauthorized",
                        "key_reload_from_env",
                        ok,
                        f"HTTP {r.status} after reload",
                    )
                    return ok
            except Exception as exc:
                self.record("klaviyo", "401_unauthorized", "key_reload_from_env", False, str(exc))
                return False

    async def fix_stripe_error(self, error_detail: str) -> bool:
        """Log Stripe errors for manual triage — no auto-fix (financial safety)."""
        self.record(
            "stripe",
            "api_error",
            "logged_for_manual_review",
            False,
            error_detail[:200],
        )
        log.error("STRIPE ERROR (manual action required): %s", error_detail)
        return False

    async def fix_stuck_task(self, task_name: str, task_monitor: TaskMonitor) -> bool:
        """Request scheduler to restart a stuck task via the dashboard REST API."""
        ok = await task_monitor.restart_task(task_name)
        self.record(
            "scheduler",
            f"task_stuck:{task_name}",
            "restart_via_dashboard",
            ok,
            f"POST /api/tasks/restart/{task_name}",
        )
        return ok

    async def fix_db_locked(self, db_path: Path) -> bool:
        """Close any stale handles by reconnecting with WAL checkpoint."""
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            conn.close()
            self.record("sqlite", "db_locked", "wal_checkpoint", True, str(db_path))
            return True
        except Exception as exc:
            self.record("sqlite", "db_locked", "wal_checkpoint", False, str(exc))
            return False

    async def apply_all(
        self,
        health: Dict[str, PlatformHealth],
        task_summary: Dict[str, Any],
        task_monitor: TaskMonitor,
    ) -> List[str]:
        """
        Run all applicable auto-fix heuristics.
        Returns a list of human-readable action descriptions.
        """
        actions: List[str] = []

        # ── Klaviyo 401 ───────────────────────────────────────────────────────
        kh = health.get("klaviyo")
        if kh and not kh.ok and kh.error and "401" in str(kh.error):
            fixed = await self.fix_klaviyo_401()
            actions.append(
                f"klaviyo 401 → env reload ({'fixed' if fixed else 'still broken'})"
            )

        # ── Stripe error log ──────────────────────────────────────────────────
        sh = health.get("stripe")
        if sh and not sh.ok:
            await self.fix_stripe_error(sh.error or "unknown")
            actions.append(f"stripe error logged: {(sh.error or '')[:60]}")

        # ── Stuck tasks ───────────────────────────────────────────────────────
        for t in task_summary.get("stuck_tasks", [])[:5]:  # cap at 5 per cycle
            name = t["task"]
            fixed = await self.fix_stuck_task(name, task_monitor)
            actions.append(f"task restart: {name} ({'ok' if fixed else 'failed'})")

        # ── DB lock check ─────────────────────────────────────────────────────
        if SCHEDULER_DB_PATH.exists():
            try:
                conn = sqlite3.connect(str(SCHEDULER_DB_PATH), timeout=2)
                conn.execute("SELECT 1")
                conn.close()
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    await self.fix_db_locked(SCHEDULER_DB_PATH)
                    actions.append("scheduler DB lock → WAL checkpoint")

        return actions


# ══════════════════════════════════════════════════════════════════════════════
# 6. ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

ZERO_REVENUE_ALERT_HOURS = 48


class MegaSelfHealer:
    """
    Top-level orchestrator that runs all subsystems in a continuous loop.
    State is persisted in data/mega_healer_state.json.
    """

    def __init__(self) -> None:
        self.task_monitor    = TaskMonitor()
        self.revenue_checker = RevenueChecker()
        self.alerter         = TelegramAlerter()
        self.fixer           = AutoFixer()

        self._health_cache:  Dict[str, PlatformHealth] = {}
        self._revenue_cache: Dict[str, Any]            = {}
        self._task_cache:    Dict[str, Any]             = {}

        # track when revenue was last non-zero
        self._last_nonzero_revenue_ts: Optional[datetime] = None
        self._load_state()

    def _state_path(self) -> Path:
        return HEALER_STATE_PATH

    def _load_state(self) -> None:
        try:
            if self._state_path().exists():
                raw = json.loads(self._state_path().read_text())
                ts  = raw.get("last_nonzero_revenue_ts")
                if ts:
                    self._last_nonzero_revenue_ts = datetime.fromisoformat(ts)
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            self._state_path().write_text(
                json.dumps(
                    {
                        "last_nonzero_revenue_ts": (
                            self._last_nonzero_revenue_ts.isoformat()
                            if self._last_nonzero_revenue_ts
                            else None
                        )
                    },
                    default=str,
                )
            )
        except Exception:
            pass

    # ── single heal cycle ────────────────────────────────────────────────────

    async def run_cycle(self) -> Dict[str, Any]:
        log.info("=== heal cycle start ===")
        cycle_start = time.monotonic()

        # 1. Platform health
        try:
            self._health_cache = await check_all_platforms()
        except Exception as exc:
            log.error("health check error: %s", exc)

        down_platforms = [n for n, h in self._health_cache.items() if not h.ok]
        if down_platforms:
            log.warning("DOWN: %s", down_platforms)

        # 2. Task monitor
        try:
            self._task_cache = self.task_monitor.summary()
        except Exception as exc:
            log.error("task monitor error: %s", exc)
            self._task_cache = {}

        # 3. Revenue
        try:
            self._revenue_cache = await self.revenue_checker.all_revenue()
        except Exception as exc:
            log.error("revenue check error: %s", exc)
            self._revenue_cache = {"total_eur": 0.0}

        # 4. Auto-fix
        actions: List[str] = []
        try:
            actions = await self.fixer.apply_all(
                self._health_cache, self._task_cache, self.task_monitor
            )
        except Exception as exc:
            log.error("auto-fix error: %s", exc)

        # 5. Critical alerts
        now = datetime.now(timezone.utc)
        for name, h in self._health_cache.items():
            if not h.ok:
                # only alert for genuine platform failures, not missing credentials
                if h.error and "_missing" not in str(h.error):
                    await self.alerter.alert_platform_down(name, h.error or "")

        # Revenue zero guard
        total = self._revenue_cache.get("total_eur", 0.0)
        if total > 0:
            self._last_nonzero_revenue_ts = now
            self._save_state()
        elif self._last_nonzero_revenue_ts is not None:
            gap_h = (now - self._last_nonzero_revenue_ts).total_seconds() / 3600
            if gap_h >= ZERO_REVENUE_ALERT_HOURS:
                await self.alerter.alert_revenue_zero(int(gap_h))

        # 6. Hourly Telegram summary
        await self.alerter.hourly_summary(
            self._health_cache, self._revenue_cache, self._task_cache, actions
        )

        elapsed = round((time.monotonic() - cycle_start) * 1000)
        log.info("=== heal cycle done in %dms ===", elapsed)

        return {
            "cycle_ms":     elapsed,
            "platforms_ok": sum(1 for h in self._health_cache.values() if h.ok),
            "platforms_total": len(self._health_cache),
            "down":         down_platforms,
            "actions":      actions,
            "total_eur":    total,
        }

    async def run_forever(self) -> None:
        """
        Continuous loop:
          - health checks every 5 minutes
          - tasks and revenue on the same cadence
        """
        log.info("MegaSelfHealer running — interval=%ds", HEALTH_CHECK_INTERVAL)
        while True:
            try:
                await self.run_cycle()
            except Exception as exc:
                log.error("unhandled cycle error: %s", exc)
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# 6. AIOHTTP ROUTE HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

_healer_instance: Optional[MegaSelfHealer] = None


def _get_healer() -> MegaSelfHealer:
    global _healer_instance
    if _healer_instance is None:
        _healer_instance = MegaSelfHealer()
    return _healer_instance


async def handle_health_all(request: web.Request) -> web.Response:
    """GET /api/health/all — full platform health check (live)."""
    healer  = _get_healer()
    results = await check_all_platforms()

    # Update cache
    healer._health_cache = results

    payload = {
        platform: h.to_dict() for platform, h in results.items()
    }
    ok_count = sum(1 for h in results.values() if h.ok)
    payload["_summary"] = {
        "platforms_ok":    ok_count,
        "platforms_total": len(results),
        "all_ok":          ok_count == len(results),
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }
    return web.json_response(payload)


async def handle_healer_log(request: web.Request) -> web.Response:
    """GET /api/healer/log — last 50 repair actions."""
    n       = int(request.rel_url.query.get("n", 50))
    healer  = _get_healer()
    entries = healer.fixer.last_n(min(n, 200))
    return web.json_response({
        "count":   len(entries),
        "entries": entries,
    })


async def handle_healer_run(request: web.Request) -> web.Response:
    """POST /api/healer/run — trigger a manual healing cycle."""
    healer = _get_healer()
    try:
        result = await healer.run_cycle()
        return web.json_response({"ok": True, "result": result})
    except Exception as exc:
        log.error("manual heal cycle error: %s", exc)
        return web.json_response(
            {"ok": False, "error": str(exc)}, status=500
        )


async def handle_revenue_summary(request: web.Request) -> web.Response:
    """GET /api/revenue/summary — live revenue from all sources."""
    healer  = _get_healer()
    revenue = await healer.revenue_checker.all_revenue()
    return web.json_response(revenue)


# ══════════════════════════════════════════════════════════════════════════════
# 7. APP FACTORY
# ══════════════════════════════════════════════════════════════════════════════


def create_healer_app() -> web.Application:
    """
    Create and return the aiohttp Application.
    Use this to mount routes into the main dashboard or run standalone.
    """
    app = web.Application()
    app.router.add_get( "/api/health/all",      handle_health_all)
    app.router.add_get( "/api/healer/log",       handle_healer_log)
    app.router.add_post("/api/healer/run",        handle_healer_run)
    app.router.add_get( "/api/revenue/summary",   handle_revenue_summary)

    # Start background loop on app startup
    async def on_startup(application: web.Application) -> None:
        healer = _get_healer()
        application["healer_task"] = asyncio.create_task(healer.run_forever())
        log.info("MegaSelfHealer background task started")

    async def on_cleanup(application: web.Application) -> None:
        task: asyncio.Task = application.get("healer_task")  # type: ignore[assignment]
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        log.info("MegaSelfHealer background task stopped")

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


# ══════════════════════════════════════════════════════════════════════════════
# 8. ENTRY POINT (standalone mode)
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    port = int(_env("HEALER_PORT", "8889"))
    app  = create_healer_app()
    log.info("Starting MegaSelfHealer on port %d", port)
    web.run_app(app, port=port, access_log=None)


if __name__ == "__main__":
    main()
