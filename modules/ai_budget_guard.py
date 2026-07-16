#!/usr/bin/env python3
"""
AI Budget Guard — Anthropic + OpenAI + Perplexity NUR für Umsatz
=================================================================
State wird in Supabase gespeichert — überlebt Railway-Neustarts!
Tageslimit: Anthropic $2 | OpenAI $2 | Perplexity $1
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("AIBudgetGuard")

# ── Whitelist — NUR diese Module dürfen Anthropic nutzen ──────────────────────
REVENUE_MODULES = frozenset({
    # Core Revenue
    "revenue_engine",
    "bullpower_revenue_engine",
    "megabot_umsatzmaschine",
    "ds24_funnel_automation",
    "ds24_affiliate_blaster",
    # Shop & Conversion
    "smart_product_finder",
    "shopify_ab_tester",
    "service_delivery",
    # Marketing & Email
    "klaviyo_automation",
    "email_outreach_bulk",
    "sys18_newsletter_ki",
    # Content & Outreach
    "sys23_expose_ki",
    "sys37_mieterbrief_ki",
    "partner_channel",
    "compliance_outreach_all",
    # B2B Lead Gen → Revenue (Intent Radar + Outreach)
    "b2b_intent_radar",
    "mass_outreach_1000",
    "rotating_buyer_prospector",
    "insolvenz_radar",
    "handelsregister_radar",
    # System (darf AI für Health/Strategy nutzen)
    "daily_system_check",
    "rudiclone",
    "geheimwaffe",
})

# ── Tagesbudget — KONSERVATIV nach Credit-Verlust ──────────────────────────────
DAILY_USD_LIMIT       = float(os.getenv("ANTHROPIC_DAILY_USD_LIMIT",   "2.0"))  # War $8 — zu hoch!
DAILY_OAI_USD_LIMIT   = float(os.getenv("OPENAI_DAILY_USD_LIMIT",      "2.0"))
DAILY_PPLX_USD_LIMIT  = float(os.getenv("PERPLEXITY_DAILY_USD_LIMIT",  "1.0"))
COST_PER_1K_IN        = 0.00080
COST_PER_1K_OUT       = 0.00400
OAI_COST_PER_1K_IN    = 0.00015
OAI_COST_PER_1K_OUT   = 0.00060
PPLX_COST_PER_REQ     = 0.005

# ── Supabase State (überlebt Neustarts) ───────────────────────────────────────
_SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
_TABLE         = "agent_memory"   # nutzt agent_role=key, content=value (JSON)
_PROVIDERS     = ("anthropic", "openai", "perplexity")

# Lokaler Cache — vermeidet DB-Hits bei jedem Token
_local_cache: dict[str, dict] = {}
_cache_ts: dict[str, float]   = {}
_CACHE_TTL = 30   # Sekunden


def _today() -> str:
    return time.strftime("%Y-%m-%d")


_FAILSAFE_FILE = Path("data/ai_budget_failsafe.json")
_supabase_reachable = True  # globaler Health-Status, initial optimistisch


def _local_fallback_get(provider: str) -> dict | None:
    """Liest lokale Backup-Datei (nur wenn Supabase nicht erreichbar)."""
    try:
        if _FAILSAFE_FILE.exists():
            data = json.loads(_FAILSAFE_FILE.read_text())
            return data.get(f"{provider}:{_today()}")
    except Exception:
        pass
    return None


def _local_fallback_save(provider: str, state: dict) -> None:
    """Schreibt in lokale Backup-Datei."""
    try:
        _FAILSAFE_FILE.parent.mkdir(exist_ok=True)
        existing = {}
        if _FAILSAFE_FILE.exists():
            try:
                existing = json.loads(_FAILSAFE_FILE.read_text())
            except Exception:
                pass
        existing[f"{provider}:{_today()}"] = state
        _FAILSAFE_FILE.write_text(json.dumps(existing))
    except Exception:
        pass


def _sb_get(provider: str) -> dict | None:
    """Liest aktuellen Tagesstand aus Supabase (mit lokalem Cache).
    Gibt None zurück wenn Supabase UND lokaler Fallback nicht verfügbar → BLOCK!
    """
    global _supabase_reachable
    now = time.time()
    cache_key = f"{provider}:{_today()}"
    if cache_key in _local_cache and now - _cache_ts.get(cache_key, 0) < _CACHE_TTL:
        return _local_cache[cache_key]

    if not _SUPABASE_URL or not _SUPABASE_KEY:
        # Kein Supabase konfiguriert — lokale Datei als Backup
        fallback = _local_fallback_get(provider)
        if fallback is None:
            fallback = {"date": _today(), "usd_spent": 0.0, "calls": 0, "blocked": 0}
        _local_cache[cache_key] = fallback
        _cache_ts[cache_key] = now
        return fallback

    try:
        key_id = f"ai_budget_{provider}_{_today()}"
        # agent_memory: agent_role=key, content=JSON-state, type='budget_state'
        url = (f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
               f"?select=content&agent_role=eq.{key_id}&type=eq.budget_state&limit=1")
        req = urllib.request.Request(url, headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
        })
        with urllib.request.urlopen(req, timeout=5) as r:
            rows = json.loads(r.read())
            _supabase_reachable = True
            if rows:
                state = json.loads(rows[0]["content"])
                _local_cache[cache_key] = state
                _cache_ts[cache_key] = now
                _local_fallback_save(provider, state)  # Backup aktualisieren
                return state
            # Kein Eintrag = neuer Tag → Default
            default = {"date": _today(), "usd_spent": 0.0, "calls": 0, "blocked": 0}
            _local_cache[cache_key] = default
            _cache_ts[cache_key] = now
            return default
    except Exception as e:
        log.warning("AIBudgetGuard: Supabase nicht erreichbar! %s → Fallback", e)
        _supabase_reachable = False
        # Fail-safe: lokale Datei verwenden
        fallback = _local_fallback_get(provider)
        if fallback is not None:
            _local_cache[cache_key] = fallback
            _cache_ts[cache_key] = now
            return fallback
        # Weder Supabase noch lokale Datei → None = BLOCK
        return None


def _sb_save(provider: str, state: dict) -> None:
    """Schreibt State in Supabase (upsert) + lokalen Cache."""
    cache_key = f"{provider}:{_today()}"
    _local_cache[cache_key] = state
    _cache_ts[cache_key] = time.time()

    if not _SUPABASE_URL or not _SUPABASE_KEY:
        # Fallback: lokale Datei
        try:
            fp = Path(f"data/ai_budget_{provider}_state.json")
            fp.parent.mkdir(exist_ok=True)
            fp.write_text(json.dumps(state))
        except Exception:
            pass
        return

    try:
        key_id = f"ai_budget_{provider}_{_today()}"
        content_json = json.dumps(state)

        # Erst prüfen ob Zeile existiert
        url_check = (f"{_SUPABASE_URL}/rest/v1/{_TABLE}"
                     f"?select=id&agent_role=eq.{key_id}&type=eq.budget_state&limit=1")
        req_check = urllib.request.Request(url_check, headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
        })
        with urllib.request.urlopen(req_check, timeout=5) as r:
            existing = json.loads(r.read())

        if existing:
            # PATCH (UPDATE)
            row_id = existing[0]["id"]
            body = json.dumps({"content": content_json}).encode()
            req = urllib.request.Request(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}?id=eq.{row_id}",
                data=body,
                headers={
                    "apikey": _SUPABASE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                    "Content-Type": "application/json",
                },
                method="PATCH",
            )
        else:
            # INSERT
            body = json.dumps({
                "agent_role": key_id,
                "type": "budget_state",
                "content": content_json,
            }).encode()
            req = urllib.request.Request(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                data=body,
                headers={
                    "apikey": _SUPABASE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="POST",
            )
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception as e:
        log.debug("AIBudgetGuard Supabase write error: %s", e)


def _caller_module() -> str:
    frame = inspect.stack()
    for entry in frame[2:12]:
        filename = entry.filename or ""
        if "modules/" in filename:
            name = Path(filename).stem
            if name not in ("claude_automation", "ai_budget_guard", "anthropic_compat",
                            "perplexity_client", "openai_client", "ai_client"):
                return name
    return "__unknown__"


def is_allowed(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        log.warning("AIBudgetGuard: '%s' BLOCKIERT (nicht in Whitelist)", module)
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    state = _sb_get("anthropic")
    if state is None:  # FAIL-CLOSED: Supabase + lokales Backup nicht verfügbar
        log.error("AIBudgetGuard: Kein State-Backend! Anthropic BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_USD_LIMIT:
        log.warning("AIBudgetGuard: Anthropic Tageslimit $%.2f erreicht!", DAILY_USD_LIMIT)
        return False, f"Anthropic Tageslimit ${DAILY_USD_LIMIT:.2f} erreicht"
    return True, module


def is_allowed_oai(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    state = _sb_get("openai")
    if state is None:
        log.error("AIBudgetGuard: Kein State-Backend! OpenAI BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_OAI_USD_LIMIT:
        return False, f"OpenAI Tageslimit ${DAILY_OAI_USD_LIMIT:.2f} erreicht"
    return True, module


def is_allowed_pplx(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    state = _sb_get("perplexity")
    if state is None:
        log.error("AIBudgetGuard: Kein State-Backend! Perplexity BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_PPLX_USD_LIMIT:
        return False, f"Perplexity Tageslimit ${DAILY_PPLX_USD_LIMIT:.2f} erreicht"
    return True, module


def record_usage(input_tokens: int, output_tokens: int, caller: str = "") -> None:
    cost = (input_tokens / 1000 * COST_PER_1K_IN) + (output_tokens / 1000 * COST_PER_1K_OUT)
    state = _sb_get("anthropic") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("anthropic", state)
    log.info("Anthropic: +$%.5f | Heute: $%.4f / $%.2f", cost, state["usd_spent"], DAILY_USD_LIMIT)


def record_usage_oai(input_tokens: int, output_tokens: int, caller: str = "") -> None:
    cost = (input_tokens / 1000 * OAI_COST_PER_1K_IN) + (output_tokens / 1000 * OAI_COST_PER_1K_OUT)
    state = _sb_get("openai") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("openai", state)


def record_usage_pplx(caller: str = "") -> None:
    state = _sb_get("perplexity") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + PPLX_COST_PER_REQ, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("perplexity", state)


def record_blocked() -> None:
    state = _sb_get("anthropic") or {"date": _today(), "usd_spent": 0.0, "blocked": 0}
    state["blocked"] = state.get("blocked", 0) + 1
    _sb_save("anthropic", state)


_UNAVAILABLE = {"usd_spent": 999.9, "calls": 0, "blocked": 0}  # Zeigt "Limit erreicht"


def get_status() -> dict:
    ant  = _sb_get("anthropic")  or _UNAVAILABLE
    oai  = _sb_get("openai")     or _UNAVAILABLE
    pplx = _sb_get("perplexity") or _UNAVAILABLE
    return {
        "date": _today(),
        "storage": "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local_file",
        "supabase_reachable": _supabase_reachable,
        "anthropic": {
            "usd_spent":    ant["usd_spent"],
            "usd_limit":    DAILY_USD_LIMIT,
            "usd_remaining": round(max(0.0, DAILY_USD_LIMIT - ant["usd_spent"]), 4),
            "calls_today":  ant.get("calls", 0),
            "calls_blocked": ant.get("blocked", 0),
            "pct_used":     round(ant["usd_spent"] / DAILY_USD_LIMIT * 100, 1) if DAILY_USD_LIMIT else 0,
        },
        "openai": {
            "usd_spent":    oai["usd_spent"],
            "usd_limit":    DAILY_OAI_USD_LIMIT,
            "usd_remaining": round(max(0.0, DAILY_OAI_USD_LIMIT - oai["usd_spent"]), 4),
            "calls_today":  oai.get("calls", 0),
            "pct_used":     round(oai["usd_spent"] / DAILY_OAI_USD_LIMIT * 100, 1) if DAILY_OAI_USD_LIMIT else 0,
        },
        "perplexity": {
            "usd_spent":    pplx["usd_spent"],
            "usd_limit":    DAILY_PPLX_USD_LIMIT,
            "usd_remaining": round(max(0.0, DAILY_PPLX_USD_LIMIT - pplx["usd_spent"]), 4),
            "calls_today":  pplx.get("calls", 0),
            "pct_used":     round(pplx["usd_spent"] / DAILY_PPLX_USD_LIMIT * 100, 1) if DAILY_PPLX_USD_LIMIT else 0,
        },
    }
