"""
Supabase client — thin wrapper that reads credentials from environment.

Required env vars:
  SUPABASE_URL  — project URL (https://<ref>.supabase.co)
  SUPABASE_ANON_KEY — anon/publishable key (safe for server use with RLS)

Optional:
  NEXT_PUBLIC_SUPABASE_URL            — alias accepted too
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY — alias accepted too
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("supabase_client")

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    try:
        from supabase import create_client, Client  # type: ignore
    except ImportError:
        raise RuntimeError("supabase-py not installed: pip install supabase")

    url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    )
    key = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    )

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment"
        )

    _client = create_client(url, key)
    return _client


def is_configured() -> bool:
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    return bool(url and key)


# ── Analytics Extensions ──────────────────────────────────────────────────────

import asyncio as _asyncio
import logging as _logging
import os as _os
from datetime import datetime as _datetime, timedelta as _timedelta
from typing import Dict as _Dict, List as _List, Optional as _Optional

_alog = _logging.getLogger("supabase_analytics")


_service_client_instance = None


def _service_client():
    """Return a cached Supabase client using the service role key (bypasses RLS).

    The client is created once per process (module-level singleton) to avoid
    creating a new HTTP connection pool on every call.
    """
    global _service_client_instance
    if _service_client_instance is not None:
        return _service_client_instance

    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        raise RuntimeError("supabase-py not installed: pip install supabase")

    url = _os.getenv("SUPABASE_URL") or _os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = _os.getenv("SUPABASE_SERVICE_KEY") or _os.getenv("SUPABASE_ANON_KEY") or _os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    _service_client_instance = create_client(url, key)
    return _service_client_instance


async def get_revenue_cohorts(months_back: int = 6) -> _Dict:
    """Cohort analysis: which customers buy how often, grouped by first-purchase month.

    Uses the client_activity_log and clients tables.

    Returns:
        {"ok": True, "cohorts": [{"month": "2026-01", "new_customers": int, "repeat_customers": int, "avg_orders": float}]}
    """
    try:
        client = _service_client()
        since = (_datetime.now() - _timedelta(days=months_back * 31)).isoformat()

        # Fetch order events grouped by customer + month
        resp = (
            client.table("client_activity_log")
            .select("client_id, created_at, event_type")
            .gte("created_at", since)
            .eq("event_type", "order")
            .order("created_at")
            .limit(5000)
            .execute()
        )
        rows = resp.data or []

        # Guard: empty database → return gracefully instead of empty loop
        if not rows:
            _alog.info("get_revenue_cohorts: no order data in DB")
            return {"ok": True, "cohorts": [], "total_customers": 0, "note": "No order data found"}

        # Build cohort map: {YYYY-MM: {client_id: order_count}}
        cohort_map: _Dict[str, _Dict[str, int]] = {}
        first_purchase: _Dict[str, str] = {}  # client_id -> first month

        for row in rows:
            cid = str(row.get("client_id", ""))
            ts = str(row.get("created_at", ""))[:7]  # YYYY-MM
            if not cid or not ts:
                continue
            if cid not in first_purchase:
                first_purchase[cid] = ts
            cohort_month = first_purchase[cid]
            cohort_map.setdefault(cohort_month, {})
            cohort_map[cohort_month][cid] = cohort_map[cohort_month].get(cid, 0) + 1

        cohorts = []
        for month in sorted(cohort_map.keys()):
            order_counts = list(cohort_map[month].values())
            new_customers = len(order_counts)
            repeat_customers = sum(1 for c in order_counts if c > 1)
            avg_orders = round(sum(order_counts) / new_customers, 2) if new_customers else 0
            cohorts.append({
                "month":             month,
                "new_customers":     new_customers,
                "repeat_customers":  repeat_customers,
                "avg_orders":        avg_orders,
            })

        _alog.info("Revenue cohorts: %d months analysed", len(cohorts))
        return {"ok": True, "cohorts": cohorts, "total_customers": len(first_purchase)}
    except Exception as exc:
        _alog.error("get_revenue_cohorts: %s", exc)
        return {"ok": False, "error": str(exc), "cohorts": []}


async def get_ltv_by_segment(segment_field: str = "plan") -> _Dict:
    """Calculate Customer Lifetime Value grouped by a segment field.

    Segments are read from the clients table (column: plan, tier, or source).

    Returns:
        {"ok": True, "segments": [{"segment": str, "avg_ltv": float, "total_revenue": float, "count": int}]}
    """
    try:
        client = _service_client()

        # Fetch clients with their total spend from activity log
        clients_resp = (
            client.table("clients")
            .select(f"id, {segment_field}, total_revenue, created_at")
            .limit(2000)
            .execute()
        )
        clients_data = clients_resp.data or []

        if not clients_data:
            # Fallback: try without segment, use client_activity_log
            _alog.warning("No clients found; returning empty LTV")
            return {"ok": True, "segments": [], "note": "No client data found"}

        segment_map: _Dict[str, _Dict] = {}
        for c in clients_data:
            seg = str(c.get(segment_field) or "unknown")
            revenue = float(c.get("total_revenue") or 0)
            segment_map.setdefault(seg, {"total_revenue": 0.0, "count": 0})
            segment_map[seg]["total_revenue"] += revenue
            segment_map[seg]["count"] += 1

        segments = []
        for seg, data in sorted(segment_map.items(), key=lambda x: -x[1]["total_revenue"]):
            count = data["count"]
            total = data["total_revenue"]
            segments.append({
                "segment":       seg,
                "avg_ltv":       round(total / count, 2) if count else 0,
                "total_revenue": round(total, 2),
                "count":         count,
            })

        _alog.info("LTV by segment (%s): %d segments", segment_field, len(segments))
        return {"ok": True, "segments": segments, "segment_field": segment_field}
    except Exception as exc:
        _alog.error("get_ltv_by_segment: %s", exc)
        return {"ok": False, "error": str(exc), "segments": []}


async def create_analytics_views() -> _Dict:
    """Create SQL views in Supabase for fast dashboard queries.

    Views created:
      - v_daily_revenue    — revenue per day from client_activity_log
      - v_top_customers    — top 50 customers by total revenue
      - v_monthly_cohorts  — simplified cohort counts per month
      - v_active_plans     — subscriber counts per plan

    Returns:
        {"ok": True, "views_created": [...], "errors": [...]}
    """
    views = {
        "v_daily_revenue": """
            CREATE OR REPLACE VIEW v_daily_revenue AS
            SELECT
                date_trunc('day', created_at)::date AS day,
                COUNT(*)                            AS orders,
                COALESCE(SUM(amount), 0)            AS revenue
            FROM client_activity_log
            WHERE event_type = 'order'
            GROUP BY 1
            ORDER BY 1 DESC;
        """,
        "v_top_customers": """
            CREATE OR REPLACE VIEW v_top_customers AS
            SELECT
                c.id,
                c.email,
                c.plan,
                COALESCE(c.total_revenue, 0) AS total_revenue,
                c.created_at
            FROM clients c
            ORDER BY total_revenue DESC
            LIMIT 50;
        """,
        "v_monthly_cohorts": """
            CREATE OR REPLACE VIEW v_monthly_cohorts AS
            SELECT
                to_char(date_trunc('month', created_at), 'YYYY-MM') AS cohort_month,
                COUNT(DISTINCT client_id)                           AS new_customers
            FROM client_activity_log
            WHERE event_type = 'order'
            GROUP BY 1
            ORDER BY 1 DESC;
        """,
        "v_active_plans": """
            CREATE OR REPLACE VIEW v_active_plans AS
            SELECT
                COALESCE(plan, 'free') AS plan,
                COUNT(*)               AS subscriber_count,
                COALESCE(SUM(total_revenue), 0) AS total_revenue
            FROM clients
            GROUP BY 1
            ORDER BY subscriber_count DESC;
        """,
    }

    try:
        client = _service_client()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "views_created": [], "errors": [str(exc)]}

    created = []
    errors = []

    for view_name, sql in views.items():
        try:
            # Use rpc to execute raw SQL via Supabase
            client.postgrest.session.post(
                f"{client.supabase_url}/rest/v1/rpc/exec_sql",
                json={"query": sql},
                headers={"apikey": client.supabase_key, "Authorization": f"Bearer {client.supabase_key}"},
            )
            created.append(view_name)
            _alog.info("View created: %s", view_name)
        except Exception as exc:
            # Many Supabase setups don't expose exec_sql; fall back gracefully
            err_msg = f"{view_name}: {str(exc)[:120]}"
            errors.append(err_msg)
            _alog.warning("Could not create view %s: %s", view_name, exc)

    return {
        "ok":           len(created) > 0 or len(errors) == 0,
        "views_created": created,
        "errors":        errors,
        "note": "If exec_sql RPC is not available, run the SQL manually in Supabase SQL editor",
        "sql":  views,
    }


# ── Helper: upsert ────────────────────────────────────────────────────────────

async def upsert(table: str, data: _Dict, on_conflict: str = "id") -> _Dict:
    """Upsert a single row into *table* using the service-role client.

    Args:
        table:       Supabase table name
        data:        Row dict to upsert
        on_conflict: Comma-separated column(s) for conflict resolution (default "id")

    Returns:
        {"ok": True, "data": [...]} or {"ok": False, "error": str}
    """
    try:
        client = _service_client()
        resp = (
            client.table(table)
            .upsert(data, on_conflict=on_conflict)
            .execute()
        )
        _alog.debug("upsert(%s): %d rows", table, len(resp.data or []))
        return {"ok": True, "data": resp.data or []}
    except Exception as exc:
        _alog.error("upsert(%s): %s", table, exc)
        return {"ok": False, "error": str(exc)}


# ── Helper: bulk_insert ───────────────────────────────────────────────────────

async def bulk_insert(table: str, rows: _List[_Dict], chunk_size: int = 200) -> _Dict:
    """Insert a list of rows in batches to avoid request-size limits.

    Args:
        table:      Supabase table name
        rows:       List of row dicts to insert
        chunk_size: Number of rows per batch (default 200)

    Returns:
        {"ok": True, "inserted": int, "errors": List[str]}
    """
    if not rows:
        return {"ok": True, "inserted": 0, "errors": []}

    try:
        client = _service_client()
    except Exception as exc:
        return {"ok": False, "inserted": 0, "errors": [str(exc)]}

    inserted = 0
    errors: _List[str] = []

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        try:
            resp = client.table(table).insert(chunk).execute()
            inserted += len(resp.data or chunk)
            _alog.debug("bulk_insert(%s): chunk %d-%d OK", table, i, i + len(chunk))
        except Exception as exc:
            err_msg = f"chunk {i}-{i + len(chunk)}: {str(exc)[:200]}"
            errors.append(err_msg)
            _alog.error("bulk_insert(%s): %s", table, err_msg)

    return {
        "ok":       len(errors) == 0,
        "inserted": inserted,
        "errors":   errors,
    }
