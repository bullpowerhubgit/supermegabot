#!/usr/bin/env python3
"""
Revenue Dashboard Data — Lightweight Aggregator.

Sammelt Stats von ALLEN Revenue-Quellen für das MEGA Dashboard:
  - Stripe Charges + Subscriptions
  - Shopify Orders + Products
  - DS24 Transactions
  - Klaviyo Subscriber Count
  - SQLite Pipeline Stats (Leads, Affiliates, Promo-Logs)

Keine Fake-Daten. Leere Quellen → 0 zurückgeben.
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
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("RevenueDashboard")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))

# ── Credentials ────────────────────────────────────────────────────────────────
_STRIPE_KEY  = lambda: (
    os.getenv("STRIPE_SECRET_KEY")
    or os.getenv("STRIPE_SECRET_KEY_AIITEC", "")
)
_SHOP_DOMAIN = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
_SHOP_TOK    = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
_SHOP_VER    = lambda: os.getenv("SHOPIFY_API_VERSION", "2026-04")
_DS24_KEY    = lambda: (
    os.getenv("DIGISTORE24_API_KEY")
    or os.getenv("DS24_API_KEY", "")
)
_KLAVIYO_KEY  = lambda: os.getenv("KLAVIYO_API_KEY", "")
_KLAVIYO_LIST = lambda: os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")


# ── SQLite helper ──────────────────────────────────────────────────────────────

def _db_query(db_path: Path, query: str, params: tuple = ()) -> List[dict]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.debug("DB query failed (%s): %s", db_path.name, e)
        return []


def _db_count(db_path: Path, table: str, where: str = "", params: tuple = ()) -> int:
    if not db_path.exists():
        return 0
    sql = f"SELECT COUNT(*) as cnt FROM {table}"
    if where:
        sql += f" WHERE {where}"
    try:
        conn = sqlite3.connect(str(db_path))
        row  = conn.execute(sql, params).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


# ── Individual source collectors ───────────────────────────────────────────────

async def _collect_stripe() -> Dict:
    """Stripe: Revenue heute / 7 Tage / Monat + aktive Subscriptions."""
    key = _STRIPE_KEY()
    if not key:
        return {"configured": False, "today": 0.0, "week": 0.0, "month": 0.0, "subscriptions": 0}

    import urllib.request
    import urllib.parse
    import base64

    def _stripe_get(path: str, params: dict = None) -> dict:
        url = f"https://api.stripe.com/v1{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header(
            "Authorization",
            "Basic " + base64.b64encode(f"{key}:".encode()).decode(),
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            log.debug("Stripe GET %s failed: %s", path, e)
            return {}

    now    = datetime.now(timezone.utc)
    today  = int((now.replace(hour=0, minute=0, second=0)).timestamp())
    week   = int((now - timedelta(days=7)).timestamp())
    month  = int((now - timedelta(days=30)).timestamp())

    def _sum_charges(since_ts: int) -> float:
        data = _stripe_get("/charges", {
            "created[gte]": since_ts,
            "limit": 100,
        })
        charges = data.get("data", [])
        return round(
            sum(
                c.get("amount", 0) / 100
                for c in charges
                if c.get("paid") and not c.get("refunded")
                   and c.get("currency", "").lower() == "eur"
            ),
            2,
        )

    # Run in thread executor (urllib is blocking)
    loop = asyncio.get_event_loop()
    today_rev, week_rev, month_rev = await asyncio.gather(
        loop.run_in_executor(None, _sum_charges, today),
        loop.run_in_executor(None, _sum_charges, week),
        loop.run_in_executor(None, _sum_charges, month),
        return_exceptions=True,
    )

    # Active subscriptions
    sub_data = await loop.run_in_executor(
        None,
        lambda: _stripe_get("/subscriptions", {"status": "active", "limit": 100}),
    )
    sub_count = len(sub_data.get("data", [])) if isinstance(sub_data, dict) else 0

    return {
        "configured":    True,
        "today":         today_rev if isinstance(today_rev, float) else 0.0,
        "week":          week_rev  if isinstance(week_rev, float) else 0.0,
        "month":         month_rev if isinstance(month_rev, float) else 0.0,
        "subscriptions": sub_count if isinstance(sub_count, int) else 0,
    }


async def _collect_shopify() -> Dict:
    """Shopify: Bestellungen + Umsatz heute / 7 Tage / Monat + Produktanzahl."""
    domain = _SHOP_DOMAIN()
    tok    = _SHOP_TOK()
    ver    = _SHOP_VER()
    if not domain or not tok:
        return {
            "configured": False, "today": 0.0, "week": 0.0, "month": 0.0,
            "orders_today": 0, "products_active": 0,
        }

    base = f"https://{domain}/admin/api/{ver}"
    headers = {"X-Shopify-Access-Token": tok}

    now   = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    week  = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    month = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _orders_since(since: str) -> tuple:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{base}/orders.json",
                    headers=headers,
                    params={
                        "status": "any",
                        "financial_status": "paid",
                        "created_at_min": since,
                        "limit": 250,
                    },
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as r:
                    if r.status != 200:
                        return 0.0, 0
                    orders = (await r.json()).get("orders", [])
                    rev = round(sum(float(o.get("total_price", 0)) for o in orders), 2)
                    return rev, len(orders)
        except Exception as e:
            log.debug("Shopify orders failed: %s", e)
            return 0.0, 0

    async def _product_count() -> int:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{base}/products/count.json",
                    headers=headers,
                    params={"status": "active"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        return (await r.json()).get("count", 0)
        except Exception:
            pass
        return 0

    results = await asyncio.gather(
        _orders_since(today),
        _orders_since(week),
        _orders_since(month),
        _product_count(),
        return_exceptions=True,
    )

    today_rev,  today_cnt  = results[0] if isinstance(results[0], tuple) else (0.0, 0)
    week_rev,   _          = results[1] if isinstance(results[1], tuple) else (0.0, 0)
    month_rev,  _          = results[2] if isinstance(results[2], tuple) else (0.0, 0)
    products               = results[3] if isinstance(results[3], int) else 0

    return {
        "configured":     True,
        "today":          today_rev,
        "week":           week_rev,
        "month":          month_rev,
        "orders_today":   today_cnt,
        "products_active": products,
    }


async def _collect_ds24() -> Dict:
    """DS24: Transaktionen letzte 24h / 7 Tage / 30 Tage."""
    key = _DS24_KEY()
    if not key:
        return {"configured": False, "today": 0.0, "week": 0.0, "month": 0.0, "orders_count": 0}

    try:
        from modules.digistore24_automation import get_orders as ds24_orders
        orders = await ds24_orders(per_page=100)
    except Exception as e:
        log.warning("DS24 orders failed: %s", e)
        return {"configured": bool(key), "today": 0.0, "week": 0.0, "month": 0.0, "orders_count": 0}

    now     = datetime.now(timezone.utc)
    cutoffs = {
        "today": now - timedelta(hours=24),
        "week":  now - timedelta(days=7),
        "month": now - timedelta(days=30),
    }
    totals = {"today": 0.0, "week": 0.0, "month": 0.0}
    orders_count = 0

    for order in orders:
        try:
            date_str = order.get("date_created") or order.get("created_at") or ""
            if not date_str:
                continue
            od = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            amount = float(order.get("total", order.get("order_total", order.get("amount", 0))))
            for period, cutoff in cutoffs.items():
                if od >= cutoff:
                    totals[period] += amount
            orders_count += 1
        except Exception:
            pass

    return {
        "configured":   True,
        "today":        round(totals["today"], 2),
        "week":         round(totals["week"],  2),
        "month":        round(totals["month"], 2),
        "orders_count": orders_count,
    }


async def _collect_klaviyo() -> Dict:
    """Klaviyo: Subscriber-Anzahl + Liste-Stats."""
    key     = _KLAVIYO_KEY()
    list_id = _KLAVIYO_LIST()
    if not key or not list_id:
        return {"configured": False, "subscriber_count": 0, "list_id": list_id}

    try:
        async with aiohttp.ClientSession() as s:
            # Get list profile count
            async with s.get(
                f"https://a.klaviyo.com/api/lists/{list_id}/",
                headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-07-15"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    attrs = data.get("data", {}).get("attributes", {})
                    return {
                        "configured":       True,
                        "subscriber_count": attrs.get("profile_count", 0),
                        "list_name":        attrs.get("name", ""),
                        "list_id":          list_id,
                    }
    except Exception as e:
        log.debug("Klaviyo list fetch failed: %s", e)

    return {"configured": bool(key), "subscriber_count": 0, "list_id": list_id}


async def _collect_pipeline_stats() -> Dict:
    """Lokale SQLite DB Stats: Leads, Affiliates, Promo-Logs, Acquisition."""
    stats: Dict[str, Any] = {}

    # Revenue expansion DB
    exp_db = DATA_DIR / "revenue_expansion.db"
    if exp_db.exists():
        stats["promo_logs_today"] = _db_count(
            exp_db, "promo_log",
            "created_at >= date('now')"
        )
        stats["promo_logs_week"] = _db_count(
            exp_db, "promo_log",
            "created_at >= date('now', '-7 days')"
        )
        stats["outreach_today"] = _db_count(
            exp_db, "outreach_log",
            "created_at >= date('now')"
        )
        stats["outreach_week"] = _db_count(
            exp_db, "outreach_log",
            "created_at >= date('now', '-7 days')"
        )
        stats["emails_queued"] = _db_count(
            exp_db, "email_queue",
            "status = 'pending'"
        )

    # SaaS acquisition DB
    acq_db = DATA_DIR / "saas_acquisition.db"
    if acq_db.exists():
        stats["saas_prospects_total"]    = _db_count(acq_db, "prospects")
        stats["saas_prospects_this_week"] = _db_count(
            acq_db, "prospects",
            "contacted_at >= date('now', '-7 days')"
        )

    # Affiliates DB
    aff_db = DATA_DIR / "affiliates.db"
    if aff_db.exists():
        stats["affiliates_total"]  = _db_count(aff_db, "affiliates")
        stats["affiliates_active"] = _db_count(aff_db, "affiliates", "status = 'active'")
        conv_rows = _db_query(aff_db, "SELECT SUM(commission) as total FROM conversions WHERE status = 'paid'")
        stats["affiliate_commissions_paid"] = round(
            float(conv_rows[0].get("total") or 0) if conv_rows else 0.0, 2
        )

    # B2B leads DB
    industrie_db = DATA_DIR / "industrie_outreach.db"
    if industrie_db.exists():
        # Try common table names
        for table in ["leads", "companies", "outreach", "contacts"]:
            try:
                conn = sqlite3.connect(str(industrie_db))
                cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.close()
                stats["b2b_leads_total"] = cnt
                break
            except Exception:
                continue

    # Mass outreach DB
    mass_db = DATA_DIR / "mass_outreach.db"
    if mass_db.exists():
        stats["mass_outreach_total"] = _db_count(mass_db, "outreach")

    return stats


async def _collect_social_metrics() -> Dict:
    """Holt Social Media Stats aus State-Dateien (auto_poster, social_autoposter)."""
    metrics: Dict[str, Any] = {}

    state_files = {
        "social_autoposter":  DATA_DIR / "social_autoposter_state.json",
        "auto_poster":        DATA_DIR / "auto_poster" / "state.json",
    }

    for key, path in state_files.items():
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                metrics[key] = {
                    "posts_total": data.get("total_posts", data.get("count", 0)),
                    "last_post":   data.get("last_post", data.get("last_run", "")),
                }
            except Exception:
                pass

    return metrics


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN: get_all_revenue_stats
# ═══════════════════════════════════════════════════════════════════════════════

async def get_all_revenue_stats() -> Dict:
    """
    Gibt vollständige Revenue + Pipeline Stats für das MEGA-Dashboard zurück.
    Alle Quellen werden parallel abgefragt.
    Fehler in einzelnen Quellen blockieren nicht den Rest.
    """
    t0 = time.monotonic()

    # Parallel data collection
    results = await asyncio.gather(
        _collect_stripe(),
        _collect_shopify(),
        _collect_ds24(),
        _collect_klaviyo(),
        _collect_pipeline_stats(),
        _collect_social_metrics(),
        return_exceptions=True,
    )

    stripe_data  = results[0] if isinstance(results[0], dict) else {}
    shopify_data = results[1] if isinstance(results[1], dict) else {}
    ds24_data    = results[2] if isinstance(results[2], dict) else {}
    klaviyo_data = results[3] if isinstance(results[3], dict) else {}
    pipeline     = results[4] if isinstance(results[4], dict) else {}
    social       = results[5] if isinstance(results[5], dict) else {}

    # Aggregate totals
    today_total = round(
        float(stripe_data.get("today", 0))
        + float(shopify_data.get("today", 0))
        + float(ds24_data.get("today", 0)),
        2,
    )
    week_total = round(
        float(stripe_data.get("week", 0))
        + float(shopify_data.get("week", 0))
        + float(ds24_data.get("week", 0)),
        2,
    )
    month_total = round(
        float(stripe_data.get("month", 0))
        + float(shopify_data.get("month", 0))
        + float(ds24_data.get("month", 0)),
        2,
    )

    duration = round(time.monotonic() - t0, 2)

    return {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "duration_s":       duration,

        # Revenue aggregates
        "revenue": {
            "today":  today_total,
            "week":   week_total,
            "month":  month_total,
            "target": float(os.getenv("SCALING_TARGET_EUR", "1000")),
            "progress_pct": round(
                min(100.0, month_total / max(float(os.getenv("SCALING_TARGET_EUR", "1000")), 1) * 100), 1
            ),
        },

        # Per-source breakdown
        "stripe":  stripe_data,
        "shopify": shopify_data,
        "ds24":    ds24_data,

        # Marketing & leads
        "klaviyo":  klaviyo_data,
        "pipeline": pipeline,
        "social":   social,

        # Quick summary for dashboard cards
        "summary": {
            "total_revenue_today":   today_total,
            "total_revenue_week":    week_total,
            "total_revenue_month":   month_total,
            "active_subscriptions":  stripe_data.get("subscriptions", 0),
            "shopify_products":      shopify_data.get("products_active", 0),
            "email_subscribers":     klaviyo_data.get("subscriber_count", 0),
            "affiliates_active":     pipeline.get("affiliates_active", 0),
            "saas_prospects_week":   pipeline.get("saas_prospects_this_week", 0),
            "outreach_today":        pipeline.get("outreach_today", 0),
            "social_posts_today":    pipeline.get("promo_logs_today", 0),
        },
    }
