"""
revenue_watchdog.py — Revenue Watchdog for SuperMegaBot / ineedit.com.co

Monitors all revenue channels every 30 min and auto-triggers corrective actions.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE       = Path(__file__).resolve().parent.parent
_WD_DB      = _BASE / "data" / "revenue_watchdog.db"
_OUTREACH_DB = _BASE / "data" / "mass_outreach.db"
_CART_DB    = _BASE / "data" / "abandoned_cart.db"
_ROAS_DB    = _BASE / "data" / "meta_roas_max.db"

_DASHBOARD  = os.getenv("SUPERMEGABOT_INTERNAL_URL", "http://localhost:8888")

# ---------------------------------------------------------------------------
# DB bootstrap
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    _WD_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_WD_DB))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            ts                  REAL    NOT NULL,
            shopify_orders_today    INT     DEFAULT 0,
            shopify_revenue_eur     REAL    DEFAULT 0.0,
            emails_sent_today       INT     DEFAULT 0,
            leads_in_db             INT     DEFAULT 0,
            carts_abandoned         INT     DEFAULT 0,
            carts_recovered         INT     DEFAULT 0,
            meta_ads_spend          REAL    DEFAULT 0.0,
            meta_ads_roas           REAL    DEFAULT 0.0,
            ds24_revenue            REAL    DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS actions_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              REAL    NOT NULL,
            trigger_name    TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            result          TEXT
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _shopify_metrics_today() -> tuple[int, float]:
    """Returns (orders_today, revenue_eur_today) from Shopify Admin API (sync wrapper)."""
    import urllib.request
    import json as _json

    shop   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
    token  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    if not shop or not token:
        log.warning("Shopify-Credentials fehlen — Snapshot-Werte bleiben 0")
        return 0, 0.0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    url   = (
        f"https://{shop}/admin/api/2026-04/orders.json"
        f"?status=any&created_at_min={today}&limit=250&fields=id,total_price,currency"
    )
    try:
        req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data   = _json.loads(resp.read())
            orders = data.get("orders", [])
            revenue = sum(float(o.get("total_price", 0)) for o in orders)
            return len(orders), round(revenue, 2)
    except Exception as exc:
        log.warning("Shopify-API-Fehler: %s", exc)
        return 0, 0.0


def _outreach_metrics() -> tuple[int, int]:
    """Returns (leads_count, emails_sent_today)."""
    try:
        if not _OUTREACH_DB.exists():
            return 0, 0
        conn = sqlite3.connect(str(_OUTREACH_DB))
        leads_total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        today_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sent_today  = conn.execute(
            "SELECT COUNT(*) FROM sends WHERE sent_at >= ?", (today_str,)
        ).fetchone()[0]
        conn.close()
        return leads_total, sent_today
    except Exception as exc:
        log.warning("Outreach-DB-Fehler: %s", exc)
        return 0, 0


def _cart_metrics() -> tuple[int, int]:
    """Returns (carts_abandoned, carts_recovered)."""
    try:
        if not _CART_DB.exists():
            return 0, 0
        conn = sqlite3.connect(str(_CART_DB))
        total     = conn.execute(
            "SELECT COUNT(*) FROM cart_recoveries WHERE is_completed = 0"
        ).fetchone()[0]
        recovered = conn.execute(
            "SELECT COUNT(*) FROM cart_recoveries WHERE is_completed = 1"
        ).fetchone()[0]
        conn.close()
        return total, recovered
    except Exception as exc:
        log.warning("Cart-DB-Fehler: %s", exc)
        return 0, 0


def _roas_metrics() -> tuple[float, float]:
    """Returns (meta_ads_spend, meta_ads_roas) from latest insights_log row."""
    try:
        if not _ROAS_DB.exists():
            return 0.0, 0.0
        conn = sqlite3.connect(str(_ROAS_DB))
        row = conn.execute(
            "SELECT spend, roas FROM insights_log ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return float(row[0] or 0), float(row[1] or 0)
        return 0.0, 0.0
    except Exception as exc:
        log.warning("ROAS-DB-Fehler: %s", exc)
        return 0.0, 0.0


def _ds24_revenue_today() -> float:
    """Returns Digistore24 revenue from today (from cached JSON if present)."""
    import json as _json
    cache_path = _BASE / "data" / "digistore_orders.json"
    try:
        if not cache_path.exists():
            return 0.0
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(cache_path) as f:
            orders = _json.load(f)
        if not isinstance(orders, list):
            return 0.0
        total = sum(
            float(o.get("order_total", 0))
            for o in orders
            if str(o.get("date_created", "")).startswith(today_str)
        )
        return round(total, 2)
    except Exception as exc:
        log.warning("DS24-Fehler: %s", exc)
        return 0.0


def _hours_since_last_shopify_order() -> float:
    """Returns hours since last Shopify order (from local cache or 999 if unknown)."""
    import json as _json
    cache_path = _BASE / "data" / "shopify_last_order.json"
    try:
        if not cache_path.exists():
            return 999.0
        with open(cache_path) as f:
            data = _json.load(f)
        last_ts = data.get("created_at", "")
        if not last_ts:
            return 999.0
        # Parse ISO timestamp
        last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - last_dt
        return round(delta.total_seconds() / 3600, 2)
    except Exception as exc:
        log.warning("Last-Order-Cache-Fehler: %s", exc)
        return 999.0


def _revenue_this_week() -> float:
    """Sum of shopify_revenue_eur from last 7 days of snapshots."""
    try:
        cutoff = time.time() - 7 * 86400
        conn   = _get_conn()
        row    = conn.execute(
            "SELECT COALESCE(SUM(shopify_revenue_eur), 0) FROM snapshots WHERE ts >= ?",
            (cutoff,)
        ).fetchone()
        conn.close()
        return float(row[0] if row else 0)
    except Exception as exc:
        log.warning("Revenue-Week-Fehler: %s", exc)
        return 0.0


def _last_rule6_alert_ts() -> float:
    """Returns timestamp of last 'rule6_weekly_zero' alert, or 0 if never."""
    try:
        conn = _get_conn()
        row  = conn.execute(
            "SELECT ts FROM actions_log WHERE trigger_name = 'rule6_weekly_zero' ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Main snapshot collector
# ---------------------------------------------------------------------------

async def take_snapshot() -> dict[str, Any]:
    """Collects all revenue metrics and persists a snapshot row. Returns the dict."""
    orders_today, revenue_today = _shopify_metrics_today()
    leads_count, emails_sent   = _outreach_metrics()
    carts_abandoned, recovered  = _cart_metrics()
    ads_spend, ads_roas         = _roas_metrics()
    ds24_rev                    = _ds24_revenue_today()

    snapshot: dict[str, Any] = {
        "ts":                    time.time(),
        "shopify_orders_today":  orders_today,
        "shopify_revenue_eur":   revenue_today,
        "emails_sent_today":     emails_sent,
        "leads_in_db":           leads_count,
        "carts_abandoned":       carts_abandoned,
        "carts_recovered":       recovered,
        "meta_ads_spend":        ads_spend,
        "meta_ads_roas":         ads_roas,
        "ds24_revenue":          ds24_rev,
    }

    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO snapshots
               (ts, shopify_orders_today, shopify_revenue_eur, emails_sent_today,
                leads_in_db, carts_abandoned, carts_recovered, meta_ads_spend,
                meta_ads_roas, ds24_revenue)
               VALUES (:ts, :shopify_orders_today, :shopify_revenue_eur, :emails_sent_today,
                       :leads_in_db, :carts_abandoned, :carts_recovered, :meta_ads_spend,
                       :meta_ads_roas, :ds24_revenue)""",
            snapshot,
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.error("Snapshot-DB-Schreib-Fehler: %s", exc)

    log.info(
        "Snapshot: orders=%d revenue=%.2f€ leads=%d emails=%d carts=%d roas=%.2f",
        orders_today, revenue_today, leads_count, emails_sent,
        carts_abandoned, ads_roas,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Telegram alert
# ---------------------------------------------------------------------------

async def _telegram_alert(session: aiohttp.ClientSession, message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        log.warning("Telegram-Credentials fehlen — Alert nicht gesendet: %s", message[:80])
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with session.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning("Telegram-HTTP %s: %s", resp.status, body[:120])
    except Exception as exc:
        log.warning("Telegram-Fehler: %s", exc)


# ---------------------------------------------------------------------------
# Action helper
# ---------------------------------------------------------------------------

async def _post_action(
    session: aiohttp.ClientSession,
    trigger_name: str,
    action_path: str,
    payload: dict | None = None,
) -> str:
    """POST to dashboard API endpoint. Returns result string."""
    url = f"{_DASHBOARD}{action_path}"
    try:
        async with session.post(
            url,
            json=payload or {},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            status = resp.status
            body   = (await resp.text())[:200]
            result = f"HTTP {status}: {body}"
            log.info("[%s] %s → %s", trigger_name, action_path, result)
            return result
    except Exception as exc:
        result = f"FEHLER: {exc}"
        log.warning("[%s] %s → %s", trigger_name, action_path, result)
        return result


def _log_action(trigger_name: str, action: str, result: str) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO actions_log (ts, trigger_name, action, result) VALUES (?, ?, ?, ?)",
            (time.time(), trigger_name, action, result),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.error("Actions-Log-Fehler: %s", exc)


# ---------------------------------------------------------------------------
# Rule evaluator
# ---------------------------------------------------------------------------

async def check_and_act(snapshot: dict[str, Any]) -> list[str]:
    """Evaluates all 6 watchdog rules and fires corrective actions. Returns triggered list."""
    triggered: list[str] = []

    async with aiohttp.ClientSession() as session:

        # ------------------------------------------------------------------
        # Rule 1 — 48h ohne Bestellung
        # ------------------------------------------------------------------
        hours_no_order = _hours_since_last_shopify_order()
        if snapshot["shopify_orders_today"] == 0 and hours_no_order > 48:
            trigger = "rule1_48h_no_order"
            log.warning("[%s] Aktiv: %d Bestellungen, %.1fh ohne Order", trigger,
                        snapshot["shopify_orders_today"], hours_no_order)

            r1 = await _post_action(session, trigger, "/api/trust/run")
            _log_action(trigger, "POST /api/trust/run", r1)

            r2 = await _post_action(session, trigger, "/api/traffic/accelerate")
            _log_action(trigger, "POST /api/traffic/accelerate", r2)

            msg = "⚠️ 48h ohne Bestellung — Trust + Traffic reaktiviert"
            await _telegram_alert(session, msg)
            triggered.append(f"{trigger}: Trust+Traffic reaktiviert")

        # ------------------------------------------------------------------
        # Rule 2 — Email-Pipeline lahm
        # ------------------------------------------------------------------
        hour_now = datetime.now(timezone.utc).hour
        if snapshot["emails_sent_today"] < 50 and 8 <= hour_now <= 20:
            trigger = "rule2_email_pipeline_slow"
            log.warning("[%s] Aktiv: nur %d E-Mails heute", trigger,
                        snapshot["emails_sent_today"])

            r = await _post_action(session, trigger, "/api/mass-outreach/blast")
            _log_action(trigger, "POST /api/mass-outreach/blast", r)

            msg = "📧 Email-Pipeline lahm — Blast gestartet"
            await _telegram_alert(session, msg)
            triggered.append(f"{trigger}: Email-Blast gestartet")

        # ------------------------------------------------------------------
        # Rule 3 — Abandoned Cart Recovery
        # ------------------------------------------------------------------
        if (
            snapshot["carts_abandoned"] > 3
            and snapshot["carts_recovered"] == 0
        ):
            trigger = "rule3_cart_recovery"
            log.warning("[%s] Aktiv: %d abgebrochene Warenkörbe, 0 recovered",
                        trigger, snapshot["carts_abandoned"])

            r = await _post_action(session, trigger, "/api/cart-recovery/run")
            _log_action(trigger, "POST /api/cart-recovery/run", r)

            msg = f"🛒 {snapshot['carts_abandoned']} abgebrochene Warenkörbe — Recovery gestartet"
            await _telegram_alert(session, msg)
            triggered.append(f"{trigger}: Cart-Recovery für {snapshot['carts_abandoned']} Carts")

        # ------------------------------------------------------------------
        # Rule 4 — Zu wenig Leads
        # ------------------------------------------------------------------
        if snapshot["leads_in_db"] < 100:
            trigger = "rule4_low_leads"
            log.warning("[%s] Aktiv: nur %d Leads in DB", trigger,
                        snapshot["leads_in_db"])

            r = await _post_action(session, trigger, "/api/mass-outreach/research")
            _log_action(trigger, "POST /api/mass-outreach/research", r)

            msg = f"🔍 Nur {snapshot['leads_in_db']} Leads — Recherche gestartet"
            await _telegram_alert(session, msg)
            triggered.append(f"{trigger}: Lead-Recherche gestartet ({snapshot['leads_in_db']} Leads)")

        # ------------------------------------------------------------------
        # Rule 5 — Meta ROAS kritisch
        # ------------------------------------------------------------------
        roas  = snapshot["meta_ads_roas"]
        spend = snapshot["meta_ads_spend"]
        if roas > 0 and roas < 1.5 and spend > 20:
            trigger = "rule5_roas_critical"
            log.warning("[%s] Aktiv: ROAS=%.2f, Spend=%.2f€", trigger, roas, spend)

            r = await _post_action(session, trigger, "/api/roas/optimize")
            _log_action(trigger, "POST /api/roas/optimize", r)

            msg = f"⚠️ Meta ROAS {roas:.2f} kritisch — Kampagnen pausiert"
            await _telegram_alert(session, msg)
            triggered.append(f"{trigger}: ROAS-Optimizer ausgeführt (ROAS={roas:.2f})")

        # ------------------------------------------------------------------
        # Rule 6 — Wochenbericht €0 Umsatz (max 1× pro 24h)
        # ------------------------------------------------------------------
        last_r6 = _last_rule6_alert_ts()
        if time.time() - last_r6 >= 86400:
            week_rev = _revenue_this_week()
            if week_rev == 0:
                trigger = "rule6_weekly_zero"
                log.warning("[%s] Aktiv: €0 Wochenumsatz", trigger)

                _log_action(trigger, "Telegram-Alert wöchentlicher €0-Umsatz",
                            "Alert gesendet")

                msg = "📊 WOCHENBERICHT: €0 Umsatz — Prüfe ob Shopify Checkout aktiv ist"
                await _telegram_alert(session, msg)
                triggered.append(f"{trigger}: €0-Wochenumsatz-Alert gesendet")

    return triggered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_watchdog_cycle() -> str:
    """Full watchdog cycle: snapshot → rules → actions. Returns summary string."""
    try:
        snapshot  = await take_snapshot()
        triggered = await check_and_act(snapshot)
        revenue   = snapshot.get("shopify_revenue_eur", 0.0)
        count     = len(triggered)
        summary   = (
            f"Watchdog: {count} Action{'s' if count != 1 else ''} triggered, "
            f"Revenue heute: €{revenue:.2f}"
        )
        log.info(summary)
        return summary
    except Exception as exc:
        log.error("Watchdog-Zyklus-Fehler: %s", exc)
        return f"Watchdog-Fehler: {exc}"


async def get_watchdog_stats() -> dict[str, Any]:
    """Returns last 10 snapshots and last 10 actions from DB."""
    try:
        conn = _get_conn()

        snap_rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY ts DESC LIMIT 10"
        ).fetchall()
        act_rows  = conn.execute(
            "SELECT * FROM actions_log ORDER BY ts DESC LIMIT 10"
        ).fetchall()

        conn.close()

        snapshots = [dict(r) for r in snap_rows]
        actions   = [dict(r) for r in act_rows]

        # Human-readable timestamps
        for s in snapshots:
            s["ts_human"] = datetime.fromtimestamp(s["ts"], tz=timezone.utc).isoformat()
        for a in actions:
            a["ts_human"] = datetime.fromtimestamp(a["ts"], tz=timezone.utc).isoformat()

        return {"snapshots": snapshots, "actions": actions}
    except Exception as exc:
        log.error("Watchdog-Stats-Fehler: %s", exc)
        return {"snapshots": [], "actions": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Standalone entry-point (for cron / direct invocation)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        result = await run_watchdog_cycle()
        print(result)

    asyncio.run(_main())
