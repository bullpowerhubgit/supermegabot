#!/usr/bin/env python3
"""
Money Machine — Unified Orchestrator (5 Engines in 1)
======================================================
Kombiniert alle 5 Revenue-Engines:
  1. Viral Window Scanner  — Echtzeit-Trendprodukte
  2. OOS Sniper            — Konkurrenz Out-of-Stock abfangen
  3. Review Goldmine       — Amazon 1★ → fertige Werbung
  4. Cart Rescue           — Abandoned Checkout via Telegram/WhatsApp
  5. eBay Arbitrage        — AliExpress EK → eBay Marktpreis → Shopify

Stripe: LIVE Preise bereits vorhanden (Telegram-Tiers):
  €29/mo → price_1TjodoRJECiV6vSmL726jLd3
  €79/mo → price_1TjodoRJECiV6vSmcWkhHtWz
  €199/mo → price_1TjodpRJECiV6vSmFVtPj8yb
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import aiohttp

log = logging.getLogger("MoneyMachine")

_BASE = Path(__file__).parent.parent

# ── Stripe Live Price IDs (bereits angelegt!) ────────────────────────────────
def _price_alert()  -> str:
    return (os.getenv("VIRAL_PRICE_ALERT")
            or os.getenv("PRICE_TELEGRAM_STARTER", "price_1TjodoRJECiV6vSmL726jLd3"))

def _price_pro() -> str:
    return (os.getenv("VIRAL_PRICE_PRO")
            or os.getenv("PRICE_TELEGRAM_PRO", "price_1TjodoRJECiV6vSmcWkhHtWz"))

def _price_agency() -> str:
    return (os.getenv("VIRAL_PRICE_AGENCY")
            or os.getenv("PRICE_TELEGRAM_AGENCY", "price_1TjodpRJECiV6vSmFVtPj8yb"))

def _stripe_key()   -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _tg_token()     -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()      -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _dashboard_url()-> str: return os.getenv(
    "DASHBOARD_URL",
    "https://supermegabot-production.up.railway.app"
)


# ── Run All Engines ───────────────────────────────────────────────────────────

async def run_all_engines(engines: List[str] = None) -> Dict:
    """Startet alle 5 Engines parallel."""
    ALL = ["viral", "oos", "ebay"]
    selected = engines or ALL
    results = {}
    tasks   = []

    if "viral" in selected:
        tasks.append(("viral", _run_viral()))
    if "oos" in selected:
        tasks.append(("oos", _run_oos()))
    if "ebay" in selected:
        tasks.append(("ebay", _run_ebay()))

    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for i, (name, _) in enumerate(tasks):
        r = gathered[i]
        if isinstance(r, Exception):
            results[name] = {"ok": False, "error": str(r)}
        else:
            results[name] = r

    # Telegram-Summary
    await _send_summary(results)
    return results


async def _run_viral() -> Dict:
    try:
        from modules.viral_window_scanner import run_scan
        return await run_scan()
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "viral"}


async def _run_oos() -> Dict:
    try:
        from modules.oos_sniper import run_scan
        return await run_scan()
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "oos"}


async def _run_ebay() -> Dict:
    try:
        from modules.ebay_arbitrage import run_full_scan
        return await run_full_scan(max_imports=3)
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "ebay"}


async def _send_summary(results: Dict):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return

    lines = ["🤖 <b>Money Machine — Run Complete</b>\n"]
    icons = {"viral": "🔥", "oos": "🎯", "ebay": "📦"}
    for name, r in results.items():
        icon = icons.get(name, "•")
        if r.get("ok"):
            lines.append(f"{icon} <b>{name.upper()}</b>: ✅ {_summarize(name, r)}")
        else:
            lines.append(f"{icon} <b>{name.upper()}</b>: ❌ {r.get('error','?')[:60]}")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    msg = "\n".join(lines)

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}
            )
    except Exception as e:
        log.debug("TG summary error: %s", e)


def _summarize(name: str, r: Dict) -> str:
    if name == "viral":
        return f"{r.get('signals_total',0)} Signale, {r.get('alerts_sent',0)} Alerts, {r.get('shopify_imported',0)} Imports"
    if name == "oos":
        return f"{r.get('targets',0)} Targets, {r.get('oos_events',0)} OOS Events"
    if name == "ebay":
        return f"{r.get('scanned',0)} gescannt, {r.get('imported',0)} Imports"
    return str(r)[:80]


# ── Unified Status ────────────────────────────────────────────────────────────

async def get_combined_status() -> Dict:
    """Status aller 5 Engines in einem Call."""
    results = await asyncio.gather(
        _safe_status("viral"),
        _safe_status("oos"),
        _safe_status("review"),
        _safe_status("cart"),
        _safe_status("ebay"),
        return_exceptions=True
    )
    names = ["viral", "oos", "review", "cart", "ebay"]
    combined = {}
    for i, name in enumerate(names):
        r = results[i]
        combined[name] = r if isinstance(r, dict) else {"ok": False, "error": str(r)}

    # Revenue-Schätzung
    ebay_r  = combined.get("ebay", {})
    cart_r  = combined.get("cart", {})
    total_revenue = (
        float(ebay_r.get("total_profit", 0)) +
        float(cart_r.get("recovered_revenue", 0))
    )

    return {
        "ok":              True,
        "engines":         combined,
        "total_revenue":   round(total_revenue, 2),
        "stripe_prices": {
            "alert":  _price_alert(),
            "pro":    _price_pro(),
            "agency": _price_agency(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def _safe_status(name: str) -> Dict:
    try:
        if name == "viral":
            from modules.viral_window_scanner import get_status
            return await get_status()
        if name == "oos":
            from modules.oos_sniper import get_status
            return get_status()
        if name == "review":
            from modules.review_goldmine import get_status
            return get_status()
        if name == "cart":
            from modules.cart_rescue import get_status
            return get_status()
        if name == "ebay":
            from modules.ebay_arbitrage import get_stats
            return get_stats()
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}
    return {"ok": False, "error": "unknown engine"}


# ── Stripe Checkout (Money Machine All-in-One) ───────────────────────────────

async def create_mm_checkout(email: str, tier: str = "alert") -> Dict:
    price_map = {
        "alert":  _price_alert(),
        "pro":    _price_pro(),
        "agency": _price_agency()
    }
    price_id = price_map.get(tier, _price_alert())
    key      = _stripe_key()
    if not key:
        return {"error": "STRIPE_SECRET_KEY nicht gesetzt"}
    if not price_id:
        return {"error": f"Stripe Price für Tier '{tier}' nicht gefunden"}

    base = _dashboard_url()
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "payment_method_types[]": "card",
                    "mode":                   "subscription",
                    "line_items[0][price]":   price_id,
                    "line_items[0][quantity]":"1",
                    "customer_email":         email,
                    "success_url": f"{base}/money-machine/success?session={{CHECKOUT_SESSION_ID}}",
                    "cancel_url":  f"{base}/money-machine",
                    "metadata[tier]":    tier,
                    "metadata[service]": "money_machine"
                }
            ) as r:
                d = await r.json()
                return {
                    "ok":           "id" in d,
                    "checkout_url": d.get("url", ""),
                    "session_id":   d.get("id", ""),
                    "tier":         tier,
                    "price_id":     price_id,
                    "error":        d.get("error", {}).get("message", "") if "error" in d else ""
                }
    except Exception as e:
        return {"error": str(e)}
