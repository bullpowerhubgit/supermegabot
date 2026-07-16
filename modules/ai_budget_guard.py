#!/usr/bin/env python3
"""
AI Budget Guard — Anthropic Credits NUR für Umsatz
===================================================
$10 = knapp. Kein einziger Token für interne Agents, Monitoring oder SEO.

NUR diese Module dürfen Anthropic nutzen:
  - revenue_engine          (DS24 + Flash + AIITEC Promo)
  - service_delivery        (SYS-Produkte liefern nach Kauf)
  - sys18_newsletter_ki     (€149/Mo — Steuerberater Newsletter)
  - sys23_expose_ki         (€499 — Unternehmensverkauf Exposé)
  - sys37_mieterbrief_ki    (€249/Mo — Mieterbrief)
  - partner_channel         (Partner/Reseller CRM)
  - compliance_outreach_all (B2B Outreach → Leads)
  - smart_product_finder    (Shopify Produkte finden)
  - ds24_affiliate_blaster  (DS24 Affiliate Posts)
  - daily_system_check      (Täglicher Health-Check)

Alle anderen → BLOCKED, kein API Call.
Tageslimit: max $8 von $10 (Puffer für Notfälle).
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("AIBudgetGuard")

# ── Whitelist — NUR diese Module dürfen Anthropic nutzen ──────────────────────
REVENUE_MODULES = frozenset({
    "revenue_engine",
    "service_delivery",
    "sys18_newsletter_ki",
    "sys23_expose_ki",
    "sys37_mieterbrief_ki",
    "partner_channel",
    "compliance_outreach_all",
    "smart_product_finder",
    "ds24_affiliate_blaster",
    "daily_system_check",
    "megabot_umsatzmaschine",
    "ds24_funnel_automation",
    "klaviyo_automation",
    "email_outreach_bulk",
})

# ── Tagesbudget ────────────────────────────────────────────────────────────────
DAILY_USD_LIMIT  = float(os.getenv("ANTHROPIC_DAILY_USD_LIMIT", "8.0"))  # $8 von $10
COST_PER_1K_IN   = 0.00025   # Haiku input  $/1K tokens
COST_PER_1K_OUT  = 0.00125   # Haiku output $/1K tokens

_STATE_FILE = Path("data/ai_budget_state.json")


def _load() -> dict:
    try:
        if _STATE_FILE.exists():
            d = json.loads(_STATE_FILE.read_text())
            if d.get("date") == time.strftime("%Y-%m-%d"):
                return d
    except Exception:
        pass
    return {"date": time.strftime("%Y-%m-%d"), "usd_spent": 0.0, "calls": 0, "blocked": 0}


def _save(state: dict):
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def _caller_module() -> str:
    """Liest den Modul-Namen des Aufrufers aus dem Call-Stack."""
    frame = inspect.stack()
    for entry in frame[2:10]:
        filename = entry.filename or ""
        if "modules/" in filename:
            name = Path(filename).stem
            if name not in ("claude_automation", "ai_budget_guard", "anthropic_compat"):
                return name
    return "__unknown__"


def is_allowed(caller: str = "") -> tuple[bool, str]:
    """
    Prüft ob der Aufrufer Anthropic nutzen darf.
    Returns (allowed: bool, reason: str)
    """
    module = caller or _caller_module()

    # Whitelist-Check
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist — kein Anthropic-Aufruf"

    # Budget-Check
    state = _load()
    if state["usd_spent"] >= DAILY_USD_LIMIT:
        return False, f"Tageslimit ${DAILY_USD_LIMIT:.2f} erreicht (verbraucht: ${state['usd_spent']:.4f})"

    return True, module


def record_usage(input_tokens: int, output_tokens: int, caller: str = ""):
    """Bucht verbrauchte Tokens gegen das Tagesbudget."""
    cost = (input_tokens / 1000 * COST_PER_1K_IN) + (output_tokens / 1000 * COST_PER_1K_OUT)
    state = _load()
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _save(state)
    log.debug("AI Budget: +$%.5f (in=%d out=%d) caller=%s | Heute: $%.4f",
              cost, input_tokens, output_tokens, caller, state["usd_spent"])


def record_blocked():
    """Zählt blockierte Aufrufe."""
    state = _load()
    state["blocked"] = state.get("blocked", 0) + 1
    _save(state)


def get_status() -> dict:
    """Für Dashboard/Health-Check."""
    state = _load()
    remaining = max(0.0, DAILY_USD_LIMIT - state["usd_spent"])
    return {
        "date": state["date"],
        "usd_spent": state["usd_spent"],
        "usd_limit": DAILY_USD_LIMIT,
        "usd_remaining": round(remaining, 4),
        "calls_today": state.get("calls", 0),
        "calls_blocked": state.get("blocked", 0),
        "pct_used": round(state["usd_spent"] / DAILY_USD_LIMIT * 100, 1) if DAILY_USD_LIMIT else 0,
    }
