#!/usr/bin/env python3
"""
Monetization — Subscription tiers, Stripe Checkout, trial management.

Tiers:
  Starter   €49/mo  — Shopify sync, basic AI
  Pro       €99/mo  — All integrations, advanced AI
  Enterprise €299/mo — Unlimited, white-label, priority support

Env vars needed:
  STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
  SUPABASE_URL, SUPABASE_ANON_KEY (or SUPABASE_SERVICE_KEY)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("monetization")

STRIPE_API_BASE = "https://api.stripe.com/v1"

PLANS = {
    "starter": {
        "name": "Starter",
        "price_eur": 49,
        "stripe_price_id": os.getenv("STRIPE_PRICE_STARTER", ""),
        "features": ["shopify_sync", "basic_ai", "telegram_bot"],
        "ai_calls_per_day": 50,
        "shopify_products_limit": 500,
    },
    "pro": {
        "name": "Pro",
        "price_eur": 99,
        "stripe_price_id": os.getenv("STRIPE_PRICE_PRO", ""),
        "features": ["shopify_sync", "advanced_ai", "telegram_bot", "digistore24", "analytics", "seo"],
        "ai_calls_per_day": 500,
        "shopify_products_limit": 5000,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_eur": 299,
        "stripe_price_id": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
        "features": ["all", "white_label", "priority_support", "custom_agents"],
        "ai_calls_per_day": -1,
        "shopify_products_limit": -1,
    },
}

TRIAL_DAYS = 14


def _stripe_request(method: str, path: str, data: dict | None = None) -> dict:
    key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not set")

    url = f"{STRIPE_API_BASE}{path}"
    token = base64.b64encode(f"{key}:".encode()).decode()

    body = None
    if data:
        body = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in data.items()).encode()

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Stripe-Version", "2024-12-18.acacia")
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()[:500]
        raise RuntimeError(f"Stripe {e.code}: {body_text}") from e


def create_checkout_session(plan: str, customer_email: str, success_url: str, cancel_url: str) -> dict:
    """Create Stripe Checkout session for the given plan."""
    plan_info = PLANS.get(plan)
    if not plan_info:
        raise ValueError(f"Unknown plan: {plan}")

    price_id = plan_info["stripe_price_id"]
    if not price_id:
        raise RuntimeError(f"Stripe price ID not configured for plan '{plan}'. Set STRIPE_PRICE_{plan.upper()}")

    trial_end = int((datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)).timestamp())

    data = {
        "mode": "subscription",
        "customer_email": customer_email,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "subscription_data[trial_end]": str(trial_end),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "allow_promotion_codes": "true",
        "billing_address_collection": "auto",
    }

    return _stripe_request("POST", "/checkout/sessions", data)


def get_subscription(subscription_id: str) -> dict:
    return _stripe_request("GET", f"/subscriptions/{subscription_id}")


def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> dict:
    data = {"cancel_at_period_end": "true" if at_period_end else "false"}
    return _stripe_request("POST", f"/subscriptions/{subscription_id}", data)


def list_active_subscriptions(limit: int = 100) -> list[dict]:
    result = _stripe_request("GET", f"/subscriptions?status=active&limit={limit}")
    return result.get("data", [])


def get_mrr() -> float:
    """Calculate Monthly Recurring Revenue in EUR."""
    subs = list_active_subscriptions(limit=100)
    total_cents = 0
    for sub in subs:
        for item in sub.get("items", {}).get("data", []):
            price = item.get("price", {})
            amount = price.get("unit_amount", 0)
            interval = price.get("recurring", {}).get("interval", "month")
            if interval == "year":
                amount = amount // 12
            total_cents += amount
    return total_cents / 100.0


def get_plans_info() -> dict:
    """Return all plan info without sensitive stripe IDs."""
    result = {}
    for key, plan in PLANS.items():
        result[key] = {
            "name": plan["name"],
            "price_eur": plan["price_eur"],
            "features": plan["features"],
            "ai_calls_per_day": plan["ai_calls_per_day"],
            "shopify_products_limit": plan["shopify_products_limit"],
            "trial_days": TRIAL_DAYS,
            "configured": bool(plan["stripe_price_id"]),
        }
    return result


def check_feature_access(client_plan: str, feature: str) -> bool:
    """Check if a given plan has access to a feature."""
    plan_info = PLANS.get(client_plan, {})
    features = plan_info.get("features", [])
    return "all" in features or feature in features
