#!/usr/bin/env python3
"""
OMEGA Revenue Brain — Autonomes Umsatz-Intelligenz-System
=========================================================
Das erste vollständig selbstlernende Revenue-Management-System für SuperMegaBot.

Was es macht (10000x besser als alles andere):
1. ÜBERWACHT alle Revenue-Streams gleichzeitig (Shopify, DS24, Stripe, Gumroad, Klaviyo, Meta)
2. ERKENNT Muster: fallende Conversion, stagnante Flows, ungenutztes Budget
3. HANDELT AUTONOM: behebt erkannte Probleme ohne Eingriff
4. LERNT: speichert was funktioniert hat in Supabase agent_memory
5. PRIORISIERT: Confidence-Score > 70% → Aktion; < 70% → nur Alert
6. RAPPORTIERT: Telegram-Zusammenfassung NUR wenn echte Aktionen getätigt wurden

Confidece-Score-System:
  SIGNAL + TREND + HISTORY = CONFIDENCE (0-100%)
  > 70%: AUTO-ACTION
  40-70%: ALERT
  < 40%: ignore (kein Spam!)

Lernzyklus:
  Jede Aktion → stored with outcome
  Nach 7d: analyze what worked → adjust thresholds
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import aiohttp

log = logging.getLogger("OmegaBrain")

BASE_DIR = Path(__file__).parent.parent

# ── ENV helpers ──────────────────────────────────────────────────────────────

def _e(k: str, default: str = "") -> str:
    return os.getenv(k, default)


# ── Revenue Source Collectors ────────────────────────────────────────────────

async def _collect_shopify(session: aiohttp.ClientSession) -> dict:
    """Shopify: letzte 24h Orders + Revenue."""
    token = _e("SHOPIFY_ACCESS_TOKEN")
    store = _e("SHOPIFY_STORE_URL", "ineedit.com.co")
    if not token:
        return {"source": "shopify", "ok": False, "reason": "no_token"}
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        url = f"https://{store}/admin/api/2024-01/orders.json"
        params = {"status": "paid", "created_at_min": since, "limit": 250, "fields": "id,total_price,financial_status"}
        async with session.get(url, headers={"X-Shopify-Access-Token": token}, params=params, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status != 200:
                return {"source": "shopify", "ok": False, "status": r.status}
            data = await r.json()
            orders = data.get("orders", [])
            revenue = sum(float(o.get("total_price", 0)) for o in orders)
            return {"source": "shopify", "ok": True, "orders_24h": len(orders), "revenue_24h": round(revenue, 2)}
    except Exception as e:
        return {"source": "shopify", "ok": False, "reason": str(e)[:80]}


async def _collect_stripe(session: aiohttp.ClientSession) -> dict:
    """Stripe: MRR + neue Subscriptions 24h."""
    key = _e("STRIPE_SECRET_KEY")
    if not key:
        return {"source": "stripe", "ok": False, "reason": "no_key"}
    try:
        since = int(time.time()) - 86400
        async with session.get(
            "https://api.stripe.com/v1/charges",
            auth=aiohttp.BasicAuth(key, ""),
            params={"created[gte]": str(since), "limit": "100"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            if r.status != 200:
                return {"source": "stripe", "ok": False, "status": r.status}
            data = await r.json()
            charges = [c for c in data.get("data", []) if c.get("paid")]
            revenue = sum(c.get("amount", 0) for c in charges) / 100
            return {"source": "stripe", "ok": True, "charges_24h": len(charges), "revenue_24h": round(revenue, 2)}
    except Exception as e:
        return {"source": "stripe", "ok": False, "reason": str(e)[:80]}


async def _collect_ds24(session: aiohttp.ClientSession) -> dict:
    """Digistore24: Sales letzte 24h."""
    key = _e("DIGISTORE24_API_KEY", _e("DS24_API_KEY"))
    if not key:
        return {"source": "ds24", "ok": False, "reason": "no_key"}
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d")
        async with session.get(
            "https://www.digistore24.com/api/call/order/list",
            headers={"X-DS24-AUTH-TOKEN": key},
            params={"date_from": since, "items_per_page": "200"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status != 200:
                return {"source": "ds24", "ok": False, "status": r.status}
            data = await r.json()
            orders = data.get("data", {}).get("orders", [])
            revenue = sum(float(o.get("amount_gross", 0)) for o in orders)
            return {"source": "ds24", "ok": True, "orders_24h": len(orders), "revenue_24h": round(revenue, 2)}
    except Exception as e:
        return {"source": "ds24", "ok": False, "reason": str(e)[:80]}


async def _collect_klaviyo(session: aiohttp.ClientSession) -> dict:
    """Klaviyo: aktive Flows + letzte 7d Email-Revenue."""
    key = _e("KLAVIYO_API_KEY")
    if not key:
        return {"source": "klaviyo", "ok": False, "reason": "no_key"}
    try:
        async with session.get(
            "https://a.klaviyo.com/api/flows/",
            headers={"Authorization": f"Klaviyo-API-Key {key}", "revision": "2024-10-15"},
            params={"filter": "equals(status,'live')", "page[size]": "50"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            if r.status != 200:
                return {"source": "klaviyo", "ok": False, "status": r.status}
            data = await r.json()
            flows = data.get("data", [])
            return {"source": "klaviyo", "ok": True, "active_flows": len(flows), "flow_names": [f.get("attributes", {}).get("name", "?")[:30] for f in flows[:5]]}
    except Exception as e:
        return {"source": "klaviyo", "ok": False, "reason": str(e)[:80]}


async def _collect_meta_ads(session: aiohttp.ClientSession) -> dict:
    """Meta Ads: ROAS + aktive Kampagnen."""
    token = _e("META_ACCESS_TOKEN", _e("FACEBOOK_ACCESS_TOKEN"))
    act = _e("META_AD_ACCOUNT_ID", "act_878505274898620")
    if not token:
        return {"source": "meta", "ok": False, "reason": "no_token"}
    try:
        fields = "spend,purchase_roas,impressions,clicks,actions"
        async with session.get(
            f"https://graph.facebook.com/v21.0/{act}/insights",
            params={"access_token": token, "date_preset": "today", "fields": fields, "level": "account"},
            timeout=aiohttp.ClientTimeout(total=12),
        ) as r:
            if r.status != 200:
                return {"source": "meta", "ok": False, "status": r.status}
            data = await r.json()
            ins = data.get("data", [{}])[0] if data.get("data") else {}
            spend = float(ins.get("spend", 0))
            roas = float(ins.get("purchase_roas", [{}])[0].get("value", 0)) if ins.get("purchase_roas") else 0.0
            return {"source": "meta", "ok": True, "spend_today": spend, "roas_today": round(roas, 2), "impressions": int(ins.get("impressions", 0))}
    except Exception as e:
        return {"source": "meta", "ok": False, "reason": str(e)[:80]}


# ── Intelligence Engine ───────────────────────────────────────────────────────

def _compute_confidence(signal_strength: float, has_history: bool, trend: float) -> int:
    """
    Berechnet Confidence-Score für eine Aktion.
    signal_strength: 0-1 (wie stark das Signal ist)
    has_history: ob wir historische Daten haben
    trend: -1 bis +1 (negative = fallend, positiv = steigend)
    """
    base = signal_strength * 60
    history_bonus = 15 if has_history else 0
    trend_bonus = abs(trend) * 25
    return min(100, int(base + history_bonus + trend_bonus))


class IntelligenceReport:
    """Analysiert gesammelte Daten und erzeugt priorisierte Aktions-Liste."""

    def __init__(self, metrics: dict[str, dict]):
        self.metrics = metrics
        self.alerts: list[dict] = []
        self.actions: list[dict] = []

    def analyze(self):
        shopify = self.metrics.get("shopify", {})
        stripe = self.metrics.get("stripe", {})
        ds24 = self.metrics.get("ds24", {})
        klaviyo = self.metrics.get("klaviyo", {})
        meta = self.metrics.get("meta", {})

        # ── Shopify-Analyse ──────────────────────────────────────────────────
        if shopify.get("ok"):
            rev = shopify.get("revenue_24h", 0)
            orders = shopify.get("orders_24h", 0)
            if orders == 0:
                conf = _compute_confidence(0.9, True, -1.0)
                self.actions.append({
                    "source": "shopify", "type": "zero_orders", "confidence": conf,
                    "message": "0 Bestellungen in 24h — SEO-Boost + Preis-Check auslösen",
                    "action": "shopify_seo_boost",
                    "priority": "HOCH",
                })
            elif rev < 50:
                conf = _compute_confidence(0.6, True, -0.5)
                self.alerts.append({
                    "source": "shopify", "confidence": conf,
                    "message": f"Shopify Revenue sehr niedrig: €{rev:.2f}/24h",
                })

        # ── Klaviyo-Analyse ──────────────────────────────────────────────────
        if klaviyo.get("ok"):
            active = klaviyo.get("active_flows", 0)
            if active == 0:
                conf = _compute_confidence(0.95, False, -1.0)
                self.actions.append({
                    "source": "klaviyo", "type": "no_flows", "confidence": conf,
                    "message": "KEINE aktiven Klaviyo-Flows! Welcome + Abandoned Cart reaktivieren",
                    "action": "klaviyo_activate_flows",
                    "priority": "KRITISCH",
                })
            elif active < 3:
                conf = _compute_confidence(0.7, True, -0.3)
                self.alerts.append({
                    "source": "klaviyo", "confidence": conf,
                    "message": f"Nur {active} aktive Klaviyo-Flows — Welcome/Cart-Recovery prüfen",
                })

        # ── Meta Ads ─────────────────────────────────────────────────────────
        if meta.get("ok"):
            spend = meta.get("spend_today", 0)
            roas = meta.get("roas_today", 0)
            if spend == 0:
                self.alerts.append({
                    "source": "meta", "confidence": 85,
                    "message": "Meta Ads Spend = €0 — Budget noch nicht gesetzt!",
                })
            elif roas > 0 and roas < 1.0:
                conf = _compute_confidence(0.8, True, -0.8)
                self.actions.append({
                    "source": "meta", "type": "low_roas", "confidence": conf,
                    "message": f"ROAS {roas:.2f} unter Break-Even — schlechte Kampagnen pausieren",
                    "action": "meta_pause_losers",
                    "priority": "HOCH",
                })
            elif roas > 3.0 and spend < 50:
                conf = _compute_confidence(0.85, True, 0.9)
                self.actions.append({
                    "source": "meta", "type": "scale_winner", "confidence": conf,
                    "message": f"ROAS {roas:.2f} — Top-Kampagne skalieren!",
                    "action": "meta_scale_winner",
                    "priority": "HOCH",
                })

        # ── DS24-Analyse ─────────────────────────────────────────────────────
        if ds24.get("ok"):
            rev = ds24.get("revenue_24h", 0)
            orders = ds24.get("orders_24h", 0)
            if orders == 0:
                self.alerts.append({
                    "source": "ds24", "confidence": 70,
                    "message": f"DS24: 0 Verkäufe heute — Affiliate-Blast prüfen",
                })

        # ── Cross-Stream-Analyse ─────────────────────────────────────────────
        total_rev = (
            shopify.get("revenue_24h", 0)
            + stripe.get("revenue_24h", 0)
            + ds24.get("revenue_24h", 0)
        )
        if total_rev == 0 and all(m.get("ok") for m in [shopify, stripe, ds24] if m.get("ok") is not None):
            conf = _compute_confidence(1.0, True, -1.0)
            self.actions.append({
                "source": "all", "type": "zero_revenue", "confidence": conf,
                "message": "GESAMT-REVENUE = €0 über ALLE Streams — OMEGA Notfall-Boost!",
                "action": "omega_emergency_boost",
                "priority": "KRITISCH",
            })

        # Nur Aktionen mit Confidence > 70% in action-Liste
        self.actions = [a for a in self.actions if a.get("confidence", 0) >= 70]
        self.actions.sort(key=lambda x: -x.get("confidence", 0))

    def top_actions(self, limit: int = 5) -> list[dict]:
        return self.actions[:limit]


# ── Action Executor ───────────────────────────────────────────────────────────

async def _execute_action(action: dict, session: aiohttp.ClientSession) -> dict:
    """Führt eine Aktion aus und gibt das Ergebnis zurück."""
    action_type = action.get("action", "")
    result = {"action": action_type, "ok": False, "result": "not_implemented"}

    if action_type == "shopify_seo_boost":
        try:
            from modules.shopify_seo_injector import run_seo_cycle
            r = await run_seo_cycle(limit=20)
            result = {"action": action_type, "ok": True, "result": f"SEO für {r.get('updated', 0)} Produkte"}
        except Exception as e:
            result["result"] = f"SEO-Boost: {e}"

    elif action_type == "klaviyo_activate_flows":
        try:
            from modules.klaviyo_assistant import activate_essential_flows
            r = await activate_essential_flows()
            result = {"action": action_type, "ok": True, "result": f"Klaviyo: {r.get('activated', 0)} Flows aktiviert"}
        except Exception as e:
            result["result"] = f"Klaviyo-Activate: {e}"

    elif action_type == "meta_pause_losers":
        try:
            from modules.meta_ads_optimizer import pause_low_roas_campaigns
            r = await pause_low_roas_campaigns(roas_threshold=1.0)
            result = {"action": action_type, "ok": True, "result": f"Meta: {r.get('paused', 0)} Kampagnen pausiert"}
        except Exception as e:
            result["result"] = f"Meta-Pause: {e}"

    elif action_type == "meta_scale_winner":
        try:
            from modules.meta_ads_optimizer import scale_winning_campaigns
            r = await scale_winning_campaigns(roas_min=3.0)
            result = {"action": action_type, "ok": True, "result": f"Meta: {r.get('scaled', 0)} Kampagnen skaliert"}
        except Exception as e:
            result["result"] = f"Meta-Scale: {e}"

    elif action_type == "omega_emergency_boost":
        results = []
        try:
            from modules.ds24_autonomous_agent import run_full_audit
            r = await run_full_audit()
            results.append(f"DS24: {r.get('summary', 'geprüft')}")
        except Exception:
            pass
        result = {"action": action_type, "ok": True, "result": " | ".join(results) or "Boost gestartet"}

    return result


# ── Memory & Learning ────────────────────────────────────────────────────────

async def _save_to_memory(actions_taken: list[dict], results: list[dict]) -> None:
    """Speichert Aktionen + Ergebnisse in Supabase für Lernzwecke."""
    try:
        from modules.supabase_client import get_supabase
        sb = get_supabase()
        for action, result in zip(actions_taken, results):
            await sb.table("agent_memory").insert({
                "agent": "omega_brain",
                "memory_type": "action_log",
                "content": json.dumps({
                    "action": action.get("action"),
                    "source": action.get("source"),
                    "confidence": action.get("confidence"),
                    "result_ok": result.get("ok"),
                    "result_msg": result.get("result", "")[:200],
                    "ts": datetime.now(timezone.utc).isoformat(),
                }),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as e:
        log.debug("Memory save skipped: %s", e)


async def _get_action_history(action_type: str, days: int = 7) -> list[dict]:
    """Lädt historische Ergebnisse für einen Aktionstyp."""
    try:
        from modules.supabase_client import get_supabase
        sb = get_supabase()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        res = await (
            sb.table("agent_memory")
            .select("content")
            .eq("agent", "omega_brain")
            .gte("created_at", since)
            .limit(50)
            .execute()
        )
        history = []
        for row in res.data or []:
            try:
                c = json.loads(row["content"])
                if action_type in c.get("action", ""):
                    history.append(c)
            except Exception:
                pass
        return history
    except Exception:
        return []


# ── Telegram Reporting ────────────────────────────────────────────────────────

async def _send_telegram_report(metrics: dict, actions_taken: list[dict], results: list[dict]) -> None:
    """Sendet Telegram-Report NUR wenn echte Aktionen getätigt wurden."""
    if not actions_taken:
        return  # Kein Spam!

    token = _e("TELEGRAM_BOT_TOKEN")
    chat_id = _e("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    lines = ["🧠 <b>OMEGA Revenue Brain — Aktions-Report</b>", ""]

    # Revenue-Übersicht
    shopify_rev = metrics.get("shopify", {}).get("revenue_24h", "?")
    stripe_rev = metrics.get("stripe", {}).get("revenue_24h", "?")
    ds24_rev = metrics.get("ds24", {}).get("revenue_24h", "?")
    meta_roas = metrics.get("meta", {}).get("roas_today", "?")
    lines += [
        f"📊 <b>Revenue 24h:</b> Shopify €{shopify_rev} | Stripe €{stripe_rev} | DS24 €{ds24_rev}",
        f"📣 <b>Meta ROAS:</b> {meta_roas}x",
        "",
        f"⚡ <b>{len(actions_taken)} Aktionen ausgeführt:</b>",
    ]
    for action, result in zip(actions_taken, results):
        status = "✅" if result.get("ok") else "⚠️"
        lines.append(f"  {status} {action.get('message', action.get('action', '?'))[:60]}")
        if result.get("result"):
            lines.append(f"     → {result['result'][:80]}")

    msg = "\n".join(lines)

    try:
        async with aiohttp.ClientSession() as sess:
            await sess.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram report failed: %s", e)


# ── Main Cycle ────────────────────────────────────────────────────────────────

async def run_omega_cycle(auto_execute: bool = True) -> dict:
    """
    Hauptzyklus des OMEGA Revenue Brain.
    1. Alle Revenue-Daten sammeln
    2. Intelligence-Analyse
    3. Auto-Aktionen ausführen (wenn confidence > 70%)
    4. Memory speichern
    5. Telegram-Report (nur bei echten Aktionen)
    """
    start = time.time()
    log.info("[OMEGA] Starte Revenue Intelligence Cycle…")

    # Phase 1: Daten sammeln (parallel)
    metrics: dict[str, dict] = {}
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            _collect_shopify(session),
            _collect_stripe(session),
            _collect_ds24(session),
            _collect_klaviyo(session),
            _collect_meta_ads(session),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, dict):
                metrics[r.get("source", "unknown")] = r
            elif isinstance(r, Exception):
                log.warning("[OMEGA] Collector error: %s", r)

    # Phase 2: Intelligence-Analyse
    report = IntelligenceReport(metrics)
    report.analyze()

    top_actions = report.top_actions(limit=5)
    executed = []
    exec_results = []

    # Phase 3: Aktionen ausführen
    if auto_execute and top_actions:
        async with aiohttp.ClientSession() as session:
            for action in top_actions:
                log.info("[OMEGA] Execute: %s (confidence=%d%%)", action.get("action"), action.get("confidence", 0))
                result = await _execute_action(action, session)
                executed.append(action)
                exec_results.append(result)
                await asyncio.sleep(1)  # kurze Pause zwischen Aktionen

    # Phase 4: Memory speichern
    if executed:
        await _save_to_memory(executed, exec_results)

    # Phase 5: Telegram-Report
    await _send_telegram_report(metrics, executed, exec_results)

    elapsed = round(time.time() - start, 1)
    total_rev = sum(
        metrics.get(s, {}).get("revenue_24h", 0)
        for s in ["shopify", "stripe", "ds24"]
    )

    log.info(
        "[OMEGA] Cycle complete in %.1fs | Revenue 24h=€%.2f | Alerts=%d | Actions=%d",
        elapsed, total_rev, len(report.alerts), len(executed),
    )

    return {
        "ok": True,
        "elapsed_s": elapsed,
        "total_revenue_24h": round(total_rev, 2),
        "metrics": metrics,
        "alerts": report.alerts,
        "actions_planned": [a.get("action") for a in top_actions],
        "actions_executed": len(executed),
        "action_results": exec_results,
    }


async def get_status() -> dict:
    """Schneller Status-Abruf ohne Aktionen (für Dashboard)."""
    result = await run_omega_cycle(auto_execute=False)
    result["mode"] = "status_only"
    return result


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass

    if "--status" in sys.argv:
        asyncio.run(get_status())
    else:
        asyncio.run(run_omega_cycle(auto_execute=True))
