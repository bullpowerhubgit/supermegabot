#!/usr/bin/env python3
"""Revenue Snapshot — Stripe MRR + heute Revenue + Digistore24 + Trial-Conversion Pipeline."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

STRIPE_API_BASE = "https://api.stripe.com/v1"
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY") or ""
DS24_KEY = os.getenv("DIGISTORE24_API_KEY", "")
DS24_BASE = "https://www.digistore24.com/api/call"

PLAN_PRICES = {
    os.getenv("STRIPE_PRICE_STARTER", ""): ("Starter", 49),
    os.getenv("STRIPE_PRICE_PRO", ""): ("Pro", 99),
    os.getenv("STRIPE_PRICE_ENTERPRISE", ""): ("Enterprise", 299),
}


# ── Stripe helpers ─────────────────────────────────────────────────────────

def _stripe(path: str, params: str = "") -> dict:
    if not STRIPE_KEY:
        return {"error": "STRIPE_SECRET_KEY not set", "data": []}
    url = f"{STRIPE_API_BASE}{path}"
    if params:
        url += ("&" if "?" in url else "?") + params
    token = base64.b64encode(f"{STRIPE_KEY}:".encode()).decode()
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Stripe-Version", "2024-12-18.acacia")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}", "data": []}


def get_active_subscriptions() -> list[dict]:
    result, subs = [], None
    params = "status=active&limit=100"
    while True:
        subs = _stripe("/subscriptions", params)
        result.extend(subs.get("data", []))
        if not subs.get("has_more"):
            break
        last_id = subs["data"][-1]["id"]
        params = f"status=active&limit=100&starting_after={last_id}"
    return result


def get_trialing_subscriptions() -> list[dict]:
    result = []
    params = "status=trialing&limit=100"
    while True:
        page = _stripe("/subscriptions", params)
        result.extend(page.get("data", []))
        if not page.get("has_more"):
            break
        last_id = page["data"][-1]["id"]
        params = f"status=trialing&limit=100&starting_after={last_id}"
    return result


def get_todays_charges() -> list[dict]:
    today_start = int(
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )
    result = []
    params = f"created[gte]={today_start}&limit=100"
    while True:
        page = _stripe("/charges", params)
        data = page.get("data", [])
        result.extend(data)
        if not page.get("has_more"):
            break
        params = f"created[gte]={today_start}&limit=100&starting_after={data[-1]['id']}"
    return result


# ── Digistore24 ────────────────────────────────────────────────────────────

def ds24_get(action: str) -> dict:
    if not DS24_KEY:
        return {"result": "error", "error": "DIGISTORE24_API_KEY not set"}
    url = f"{DS24_BASE}/{DS24_KEY}/{action}/json"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"result": "error", "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"result": "error", "error": str(e)}


def ds24_today_revenue() -> tuple[float, int]:
    data = ds24_get("listOrdersForVendor")
    if data.get("result") != "success":
        return 0.0, 0
    raw = data.get("data", {})
    orders = raw.get("order_list", raw.get("orders", []))
    today = datetime.now(timezone.utc).date()
    today_orders = []
    for o in orders:
        date_str = o.get("date_created") or o.get("created_at") or ""
        try:
            order_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        except Exception:
            continue
        if order_date == today and o.get("order_status") not in ("cancelled", "refunded", "chargeback"):
            today_orders.append(o)
    revenue = sum(float(o.get("total", o.get("price", 0))) for o in today_orders)
    return revenue, len(today_orders)


# ── Calculations ───────────────────────────────────────────────────────────

def calc_mrr(subs: list[dict]) -> tuple[float, dict]:
    total_cents = 0
    by_plan: dict[str, int] = {}
    for sub in subs:
        for item in sub.get("items", {}).get("data", []):
            price = item.get("price", {})
            amount = price.get("unit_amount", 0) or 0
            interval = price.get("recurring", {}).get("interval", "month")
            if interval == "year":
                amount = amount // 12
            total_cents += amount
            price_id = price.get("id", "")
            plan_name = PLAN_PRICES.get(price_id, ("Unknown", 0))[0]
            by_plan[plan_name] = by_plan.get(plan_name, 0) + 1
    return total_cents / 100.0, by_plan


def trials_expiring_soon(trials: list[dict], days: int = 3) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    expiring = []
    for sub in trials:
        trial_end = sub.get("trial_end")
        if trial_end:
            trial_dt = datetime.fromtimestamp(trial_end, tz=timezone.utc)
            if now <= trial_dt <= cutoff:
                email = (sub.get("customer_email") or
                         (sub.get("customer", {}) or {}).get("email") or "unknown")
                plan_name = "Unknown"
                for item in sub.get("items", {}).get("data", []):
                    pid = item.get("price", {}).get("id", "")
                    if pid in PLAN_PRICES:
                        plan_name = PLAN_PRICES[pid][0]
                expiring.append({
                    "id": sub["id"],
                    "email": email,
                    "plan": plan_name,
                    "trial_end": trial_dt.strftime("%Y-%m-%d %H:%M UTC"),
                    "hours_left": int((trial_dt - now).total_seconds() / 3600),
                })
    return sorted(expiring, key=lambda x: x["hours_left"])


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now(timezone.utc)
    print()
    print("=" * 60)
    print(f"  REVENUE SNAPSHOT — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # ── Stripe ─────────────────────────────────────────────────────────────
    if not STRIPE_KEY:
        print("\n  ⚠️  STRIPE_SECRET_KEY not found — skipping Stripe")
    else:
        print("\n  [STRIPE]")
        active_subs = get_active_subscriptions()
        mrr, by_plan = calc_mrr(active_subs)
        print(f"  Active subscriptions : {len(active_subs)}")
        for plan, count in sorted(by_plan.items()):
            print(f"    {plan:<12} : {count} subscriber(s)")
        print(f"  MRR                  : €{mrr:,.2f}")
        print(f"  ARR (projected)      : €{mrr * 12:,.2f}")

        trials = get_trialing_subscriptions()
        print(f"\n  Trialing             : {len(trials)}")
        expiring = trials_expiring_soon(trials, days=3)
        if expiring:
            print(f"  🔥 Expiring ≤3 days  : {len(expiring)} conversion opportunity!")
            for t in expiring[:5]:
                print(f"    [{t['hours_left']}h]  {t['email']:<30}  {t['plan']}")
        else:
            print("  No trials expiring in next 3 days")

        charges = get_todays_charges()
        successful = [c for c in charges if c.get("status") == "succeeded" and not c.get("refunded")]
        today_stripe = sum(c.get("amount", 0) for c in successful) / 100.0
        print(f"\n  Today Stripe Revenue : €{today_stripe:,.2f}  ({len(successful)} charges)")

    # ── Digistore24 ────────────────────────────────────────────────────────
    print("\n  [DIGISTORE24]")
    if not DS24_KEY:
        print("  ⚠️  DIGISTORE24_API_KEY not found — skipping")
        ds24_rev, ds24_count = 0.0, 0
    else:
        ds24_rev, ds24_count = ds24_today_revenue()
        print(f"  Today Revenue        : €{ds24_rev:,.2f}  ({ds24_count} orders)")

    # ── Total ──────────────────────────────────────────────────────────────
    stripe_today = today_stripe if STRIPE_KEY else 0.0
    total_today = stripe_today + ds24_rev
    print("\n" + "=" * 60)
    print(f"  TOTAL TODAY          : €{total_today:,.2f}")
    if STRIPE_KEY:
        print(f"  MRR                  : €{mrr:,.2f}")
        print(f"  Conversion pipeline  : {len(trials)} trials  ({len(expiring)} hot)")
    print("=" * 60)
    print()

    # ── Upgrade links for expiring trials ──────────────────────────────────
    if STRIPE_KEY and expiring:
        pro_price = os.getenv("STRIPE_PRICE_PRO", "")
        enterprise_price = os.getenv("STRIPE_PRICE_ENTERPRISE", "")
        print("  UPGRADE CHECKOUT LINKS (for hot trials):")
        for t in expiring[:3]:
            if pro_price:
                print(f"    {t['email']} → Pro:        "
                      f"https://buy.stripe.com/subscribe?price={pro_price}")
            if enterprise_price:
                print(f"    {t['email']} → Enterprise: "
                      f"https://buy.stripe.com/subscribe?price={enterprise_price}")
        print()


if __name__ == "__main__":
    main()
