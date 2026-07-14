#!/usr/bin/env python3
"""
SuperMegaBot — Revenue Trigger
================================
Startet sofort alle Revenue-generierenden Tasks.
Lässt sich lokal oder auf Railway per curl triggern.

Usage:
  python3 revenue_trigger.py              # alles starten
  python3 revenue_trigger.py --email      # nur Email Blast
  python3 revenue_trigger.py --cart       # nur Cart Recovery
  python3 revenue_trigger.py --klaviyo    # nur Klaviyo Kampagnen
  python3 revenue_trigger.py --ds24       # nur DS24 Sync
  python3 revenue_trigger.py --optimize   # Shopify + SEO optimieren
  python3 revenue_trigger.py --status     # Status anzeigen
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

try:
    import aiohttp
except ImportError:
    print("❌ aiohttp nicht installiert: pip install aiohttp")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
BASE = os.environ.get("SUPERMEGABOT_URL", "http://localhost:8888")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"

def ok(msg):   print(f"  {G}✅{X} {msg}")
def fail(msg): print(f"  {R}❌{X} {msg}")
def info(msg): print(f"  {B}→{X}  {msg}")

# ── Revenue Actions ────────────────────────────────────────────────────────────
ACTIONS = [
    ("Email Blast",        "POST", "/api/email/blast-now"),
    ("Cart Recovery",      "POST", "/api/shopify/cart-recovery"),
    ("Klaviyo Kampagne",   "POST", "/api/klaviyo/mass-campaign"),
    ("DS24 Sync",          "POST", "/api/digistore24/sync"),
    ("Shopify Optimize",   "POST", "/api/shopify/optimize-now"),
    ("SEO Mega Zyklus",    "POST", "/api/seo/mega-cycle"),
    ("Affiliate Blast",    "POST", "/api/affiliate/blast-all"),
    ("Trust Signals",      "POST", "/api/shopify/inject-trust"),
]

QUICK_ACTIONS = {
    "email":    [("Email Blast", "POST", "/api/email/blast-now"),
                 ("Email Daily Blast", "POST", "/api/email/daily-blast")],
    "cart":     [("Cart Recovery", "POST", "/api/shopify/cart-recovery")],
    "klaviyo":  [("Klaviyo Mass Campaign", "POST", "/api/klaviyo/mass-campaign")],
    "ds24":     [("DS24 Sync", "POST", "/api/digistore24/sync")],
    "optimize": [("Shopify Optimize", "POST", "/api/shopify/optimize-now"),
                 ("Trust Signals", "POST", "/api/shopify/inject-trust"),
                 ("SEO Mega Zyklus", "POST", "/api/seo/mega-cycle")],
    "status":   [],
}


async def call(session: aiohttp.ClientSession, name: str, method: str, path: str) -> dict:
    t0 = time.monotonic()
    try:
        async with session.request(
            method, f"{BASE}{path}",
            json={}, timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            ms = int((time.monotonic() - t0) * 1000)
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {}
            success = r.status < 400 and (data.get("ok") or data.get("success") or
                                           data.get("status") in ("ok", "started") or
                                           r.status == 200)
            if success:
                ok(f"{name} ({ms}ms)")
            else:
                fail(f"{name} — HTTP {r.status} — {data.get('error', '')}")
            return {"name": name, "ok": success, "status": r.status, "ms": ms}
    except Exception as e:
        fail(f"{name} — {e}")
        return {"name": name, "ok": False, "error": str(e)}


async def get_status(session: aiohttp.ClientSession):
    print(f"\n{B}{'─'*50}{X}")
    print(f"  Revenue Status")
    print(f"{'─'*50}")
    endpoints = [
        ("Health",          "/health"),
        ("Revenue Summary", "/api/revenue/summary"),
        ("Shopify Stats",   "/api/shopify/stats"),
        ("Email Stats",     "/api/email/stats"),
        ("Scheduler Stats", "/api/scheduler/stats"),
        ("Klaviyo Status",  "/api/klaviyo/status"),
    ]
    for name, path in endpoints:
        try:
            async with session.get(f"{BASE}{path}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    ok(f"{name:<20} {_summarize(data)}")
                else:
                    fail(f"{name:<20} HTTP {r.status}")
        except Exception as e:
            fail(f"{name:<20} {e}")


def _summarize(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    parts = []
    for key in ("revenue", "total", "orders", "products", "subscribers", "sent", "runs_today"):
        if key in data:
            parts.append(f"{key}={data[key]}")
    return " | ".join(parts[:4]) if parts else str(list(data.items())[:2])


async def notify_telegram(results: list[dict]):
    if not TG_TOKEN or not TG_CHAT:
        return
    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    failed_names = [r["name"] for r in results if not r.get("ok")]
    lines = [
        f"🚀 <b>Revenue Trigger gestartet</b>",
        f"✅ {ok_count} Tasks gestartet | ❌ {fail_count} Fehler",
        f"🕐 {datetime.now().strftime('%d.%m. %H:%M')}",
    ]
    if failed_names:
        lines.append(f"❌ Fehler: {', '.join(failed_names)}")
    msg = "\n".join(lines)
    body = json.dumps({"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"}).encode()
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data=body, headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            )
    except Exception:
        pass


async def run_direct_fallback():
    """Fallback: Wenn Dashboard nicht läuft, Module direkt importieren."""
    print(f"\n{Y}  Dashboard nicht erreichbar — versuche direkte Modul-Ausführung…{X}")
    results = []

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from modules.email_blast_engine import run_daily_blast
        info("Starte Email Blast…")
        r = await run_daily_blast()
        ok(f"Email Blast: {r}")
        results.append({"name": "Email Blast", "ok": True})
    except Exception as e:
        fail(f"Email Blast: {e}")
        results.append({"name": "Email Blast", "ok": False})

    try:
        from modules.klaviyo_mass_campaigns import run_daily_klaviyo_campaigns
        info("Starte Klaviyo Kampagnen…")
        r = await run_daily_klaviyo_campaigns()
        ok(f"Klaviyo: {r}")
        results.append({"name": "Klaviyo", "ok": True})
    except Exception as e:
        fail(f"Klaviyo: {e}")
        results.append({"name": "Klaviyo", "ok": False})

    try:
        from modules.shop_scaling_engine import run_abandoned_cart_recovery
        info("Starte Cart Recovery…")
        r = await run_abandoned_cart_recovery()
        ok(f"Cart Recovery: {r}")
        results.append({"name": "Cart Recovery", "ok": True})
    except Exception as e:
        fail(f"Cart Recovery: {e}")
        results.append({"name": "Cart Recovery", "ok": False})

    try:
        from modules.shop_scaling_engine import inject_trust_signals
        info("Starte Trust Signals…")
        r = await inject_trust_signals()
        ok(f"Trust Signals: {r}")
        results.append({"name": "Trust Signals", "ok": True})
    except Exception as e:
        fail(f"Trust Signals: {e}")
        results.append({"name": "Trust Signals", "ok": False})

    return results


async def main():
    args = set(sys.argv[1:])

    # Welche Actions?
    if not args or args == {"--full"}:
        actions = ACTIONS
    elif "--status" in args:
        actions = []
    else:
        actions = []
        for flag, flag_actions in QUICK_ACTIONS.items():
            if f"--{flag}" in args:
                actions.extend(flag_actions)
        if not actions and "--status" not in args:
            actions = ACTIONS

    print(f"\n{B}{'═'*50}{X}")
    print(f"{B}  💰 Revenue Trigger — SuperMegaBot{X}")
    print(f"{B}  {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}{X}")
    print(f"{B}  Base URL: {BASE}{X}")
    print(f"{B}{'═'*50}{X}")

    async with aiohttp.ClientSession() as session:
        # Health check
        try:
            async with session.get(f"{BASE}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                dashboard_ok = r.status == 200
        except Exception:
            dashboard_ok = False

        if "--status" in args:
            await get_status(session)
            return

        if not dashboard_ok:
            results = await run_direct_fallback()
        else:
            info(f"Dashboard erreichbar — {len(actions)} Actions starten…")
            tasks = [call(session, name, method, path) for name, method, path in actions]
            results = await asyncio.gather(*tasks)

    # Summary
    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    print(f"\n{B}{'═'*50}{X}")
    print(f"  {G}✅ {ok_count} gestartet{X}  |  {(R if fail_count else G)}❌ {fail_count} Fehler{X}")
    print(f"{B}{'═'*50}{X}\n")

    await notify_telegram(list(results))


if __name__ == "__main__":
    asyncio.run(main())
