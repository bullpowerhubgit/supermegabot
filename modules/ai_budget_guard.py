#!/usr/bin/env python3
"""
AI Budget Guard — Anthropic + Perplexity NUR für Umsatz
=========================================================
Credits sind knapp. Kein einziger Token für interne Agents, Monitoring oder SEO.

NUR diese Module dürfen AI APIs nutzen:
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
  - perplexity_search       (Web-Research für Revenue)

Alle anderen → BLOCKED.
Tageslimit Anthropic: $8.00 | Perplexity: $5.00
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
DAILY_USD_LIMIT       = float(os.getenv("ANTHROPIC_DAILY_USD_LIMIT",   "8.0"))
DAILY_PPLX_USD_LIMIT  = float(os.getenv("PERPLEXITY_DAILY_USD_LIMIT",  "5.0"))
COST_PER_1K_IN        = 0.00025   # Haiku input  $/1K tokens
COST_PER_1K_OUT       = 0.00125   # Haiku output $/1K tokens
PPLX_COST_PER_REQ     = 0.005     # Sonar ~$0.005/Request (online search)

_STATE_FILE = Path("data/ai_budget_state.json")


_PPLX_STATE_FILE = Path("data/ai_budget_pplx_state.json")


def _load(file: Path = _STATE_FILE) -> dict:
    try:
        if file.exists():
            d = json.loads(file.read_text())
            if d.get("date") == time.strftime("%Y-%m-%d"):
                return d
    except Exception:
        pass
    return {"date": time.strftime("%Y-%m-%d"), "usd_spent": 0.0, "calls": 0, "blocked": 0}


def _save(state: dict, file: Path = _STATE_FILE):
    try:
        file.parent.mkdir(exist_ok=True)
        file.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def _caller_module() -> str:
    frame = inspect.stack()
    for entry in frame[2:10]:
        filename = entry.filename or ""
        if "modules/" in filename:
            name = Path(filename).stem
            if name not in ("claude_automation", "ai_budget_guard", "anthropic_compat",
                            "perplexity_client"):
                return name
    return "__unknown__"


def is_allowed(caller: str = "") -> tuple[bool, str]:
    """Prüft ob der Aufrufer Anthropic nutzen darf."""
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    state = _load()
    if state["usd_spent"] >= DAILY_USD_LIMIT:
        return False, f"Anthropic Tageslimit ${DAILY_USD_LIMIT:.2f} erreicht"
    return True, module


def is_allowed_pplx(caller: str = "") -> tuple[bool, str]:
    """Prüft ob der Aufrufer Perplexity nutzen darf."""
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    state = _load(_PPLX_STATE_FILE)
    if state["usd_spent"] >= DAILY_PPLX_USD_LIMIT:
        return False, f"Perplexity Tageslimit ${DAILY_PPLX_USD_LIMIT:.2f} erreicht"
    return True, module


def record_usage(input_tokens: int, output_tokens: int, caller: str = ""):
    """Bucht Anthropic Tokens gegen Tagesbudget."""
    cost = (input_tokens / 1000 * COST_PER_1K_IN) + (output_tokens / 1000 * COST_PER_1K_OUT)
    state = _load()
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _save(state)
    log.debug("Anthropic: +$%.5f caller=%s | Heute: $%.4f", cost, caller, state["usd_spent"])


def record_usage_pplx(caller: str = ""):
    """Bucht einen Perplexity Request gegen Tagesbudget."""
    state = _load(_PPLX_STATE_FILE)
    state["usd_spent"] = round(state["usd_spent"] + PPLX_COST_PER_REQ, 6)
    state["calls"] = state.get("calls", 0) + 1
    _save(state, _PPLX_STATE_FILE)
    log.debug("Perplexity: +$%.4f caller=%s | Heute: $%.4f",
              PPLX_COST_PER_REQ, caller, state["usd_spent"])


def record_blocked():
    state = _load()
    state["blocked"] = state.get("blocked", 0) + 1
    _save(state)


def get_status() -> dict:
    """Für Dashboard/Health-Check."""
    ant = _load()
    pplx = _load(_PPLX_STATE_FILE)
    return {
        "date": ant["date"],
        "anthropic": {
            "usd_spent": ant["usd_spent"],
            "usd_limit": DAILY_USD_LIMIT,
            "usd_remaining": round(max(0.0, DAILY_USD_LIMIT - ant["usd_spent"]), 4),
            "calls_today": ant.get("calls", 0),
            "calls_blocked": ant.get("blocked", 0),
            "pct_used": round(ant["usd_spent"] / DAILY_USD_LIMIT * 100, 1),
        },
        "perplexity": {
            "usd_spent": pplx["usd_spent"],
            "usd_limit": DAILY_PPLX_USD_LIMIT,
            "usd_remaining": round(max(0.0, DAILY_PPLX_USD_LIMIT - pplx["usd_spent"]), 4),
            "calls_today": pplx.get("calls", 0),
            "pct_used": round(pplx["usd_spent"] / DAILY_PPLX_USD_LIMIT * 100, 1),
        },
    }
