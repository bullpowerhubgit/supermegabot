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
    # Social Media Posting — DARF AI für Content-Generierung nutzen
    "social_autoposter",
    "autonomous_social_proof",
    "post_content_generator",
    "rudibot_post_ai",
    "post_guard",              # Post-Quality-AI-Score
    # Traffic & SEO
    "brutus_traffic_engine",
    "brutus_core",
    "mega_seo_engine",
    "seo_content_engine",
    "full_seo_blast",
    # Shop & Produkt-Automatisierung
    "shopify_full_autonomy",
    "product_generator",
    "revenue_maximizer",
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
    # Email & Reply-Klassifikation → Revenue
    "reply_monitor",
    "agent_teams",
    "claude_agent",
    "claude_agent_collab",
    "autonomous_loop",
    "analytics_feedback",
    "telegram_dm_sheet",
    # Traffic & Conversion
    "traffic_maximizer",
    "full_revenue_expansion",
    "traffic_accelerator",
    "seo_mega_engine",
    # DS24 & Content Publishing
    "ds24_income_blaster",
    "github_blog_publisher",
    # Email Marketing
    "email_blast_engine",
    "klaviyo_blast",
    "newsletter_engine",
})

# ── Tagesbudget + Stundenlimit — DAUERHAFTER KERN-SCHUTZ 2026-07-18 ───────────
# NIEMALS diese Limits erhöhen ohne Rudolf zu fragen!
# Credits drainten in 30min (€10 in 30min) weil:
#  - content_factory_run machte 20+ parallele Claude-Calls
#  - seo_content_factory lief stündlich mit vielen Calls
#  - Jetzt: alle diese Tasks in POSTING_BLOCKLIST → laufen gar nicht mehr

# Tages-Limits (niedrig halten!)
DAILY_USD_LIMIT       = float(os.getenv("ANTHROPIC_DAILY_USD_LIMIT",   "1.00"))  # €0.92/Tag max
DAILY_OAI_USD_LIMIT   = float(os.getenv("OPENAI_DAILY_USD_LIMIT",      "1.00"))  # €0.92/Tag max
DAILY_PPLX_USD_LIMIT  = float(os.getenv("PERPLEXITY_DAILY_USD_LIMIT",  "0.50"))  # €0.46/Tag max

# Stunden-Limits (verhindert 30min-Drain!)
HOURLY_USD_LIMIT      = float(os.getenv("ANTHROPIC_HOURLY_USD_LIMIT",  "0.20"))  # max $0.20/h
HOURLY_OAI_USD_LIMIT  = float(os.getenv("OPENAI_HOURLY_USD_LIMIT",     "0.15"))  # max $0.15/h

# Gesamt-Cap über alle Provider (€ equivalent, ~$2.75 total = €2.53/Tag)
GLOBAL_DAILY_USD_CAP  = float(os.getenv("GLOBAL_AI_DAILY_USD_CAP",     "2.50"))

# Token-Kosten
COST_PER_1K_IN        = 0.00080
COST_PER_1K_OUT       = 0.00400
OAI_COST_PER_1K_IN    = 0.00015
OAI_COST_PER_1K_OUT   = 0.00060
PPLX_COST_PER_REQ     = 0.005

# ── In-Memory Echtzeit-Zähler (verhindert Race-Conditions) ────────────────────
# Diese Zähler laufen parallel zum Supabase-State und stoppen sofort
# wenn das Limit in der aktuellen Stunde erreicht wird, OHNE auf DB zu warten.
import threading as _threading
_mem_lock        = _threading.Lock()
_mem_hourly: dict[str, float]  = {}   # "provider:YYYY-MM-DD-HH" → USD spent
_mem_daily:  dict[str, float]  = {}   # "provider:YYYY-MM-DD"    → USD spent
_mem_global: dict[str, float]  = {}   # "global:YYYY-MM-DD"      → USD spent total
_alert_sent: dict[str, bool]   = {}   # "provider:50pct" → True wenn Alert gesendet


def _hour_key(provider: str) -> str:
    return f"{provider}:{time.strftime('%Y-%m-%d-%H')}"


def _add_mem_cost(provider: str, usd: float) -> None:
    """Addiert Kosten zum In-Memory Zähler (threadsafe)."""
    with _mem_lock:
        dk = f"{provider}:{_today()}"
        hk = _hour_key(provider)
        gk = f"global:{_today()}"
        _mem_hourly[hk]  = _mem_hourly.get(hk, 0.0)  + usd
        _mem_daily[dk]   = _mem_daily.get(dk, 0.0)   + usd
        _mem_global[gk]  = _mem_global.get(gk, 0.0)  + usd


def _mem_check(provider: str) -> tuple[bool, str]:
    """Prüft In-Memory Limits. Gibt (allowed, reason) zurück."""
    with _mem_lock:
        hk = _hour_key(provider)
        dk = f"{provider}:{_today()}"
        gk = f"global:{_today()}"
        spent_hourly = _mem_hourly.get(hk, 0.0)
        spent_daily  = _mem_daily.get(dk, 0.0)
        spent_global = _mem_global.get(gk, 0.0)

    # Stunden-Check (schnellster Schutz gegen 30min-Drain)
    if provider == "anthropic" and spent_hourly >= HOURLY_USD_LIMIT:
        return False, f"Anthropic Stundenlimit ${HOURLY_USD_LIMIT:.2f} erreicht (spent ${spent_hourly:.3f})"
    if provider == "openai" and spent_hourly >= HOURLY_OAI_USD_LIMIT:
        return False, f"OpenAI Stundenlimit ${HOURLY_OAI_USD_LIMIT:.2f} erreicht (spent ${spent_hourly:.3f})"

    # Tages-Check pro Provider
    daily_limit = {"anthropic": DAILY_USD_LIMIT, "openai": DAILY_OAI_USD_LIMIT, "perplexity": DAILY_PPLX_USD_LIMIT}.get(provider, 1.0)
    if spent_daily >= daily_limit:
        return False, f"{provider.capitalize()} Tageslimit ${daily_limit:.2f} erreicht (spent ${spent_daily:.3f})"

    # Globaler Cap
    if spent_global >= GLOBAL_DAILY_USD_CAP:
        return False, f"Globaler AI-Cap ${GLOBAL_DAILY_USD_CAP:.2f}/Tag erreicht (${spent_global:.3f} total)"

    return True, ""


def _maybe_send_budget_alert(provider: str, usd_spent: float, usd_limit: float) -> None:
    """Telegram-Alert wenn 50% oder 90% des Limits erreicht."""
    pct = (usd_spent / max(usd_limit, 0.001)) * 100
    for threshold in (50, 90):
        key = f"{provider}:{threshold}pct:{_today()}"
        if pct >= threshold and not _alert_sent.get(key):
            _alert_sent[key] = True
            try:
                tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
                chat = os.getenv("TELEGRAM_CHAT_ID", "")
                if not tok or not chat:
                    return
                emoji = "⚠️" if threshold == 50 else "🚨"
                msg  = (f"{emoji} <b>AI-Budget {threshold}% ausgeschöpft</b>\n"
                        f"Provider: {provider.upper()}\n"
                        f"Verbraucht: ${usd_spent:.3f} / ${usd_limit:.2f}\n"
                        f"Datum: {_today()}\n"
                        f"→ Kein weiterer {provider.upper()}-Einsatz bis Mitternacht wenn 100% erreicht!")
                import urllib.request as _ur, json as _json
                data = _json.dumps({"chat_id": chat, "text": msg, "parse_mode": "HTML"}).encode()
                req  = _ur.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                   data=data, headers={"Content-Type": "application/json"})
                with _ur.urlopen(req, timeout=5):
                    pass
            except Exception:
                pass

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
    for entry in frame[2:30]:  # Weiter suchen für async-Stacks
        filename = entry.filename or ""
        if "modules/" in filename:
            name = Path(filename).stem
            if name not in ("claude_automation", "ai_budget_guard", "anthropic_compat",
                            "perplexity_client", "openai_client", "ai_client",
                            "ai_gateway", "openrouter_client", "groq_client"):
                return name
    return "__unknown__"


def is_allowed(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        log.warning("AIBudgetGuard: '%s' BLOCKIERT (nicht in Whitelist)", module)
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    # ── In-Memory Check ZUERST (kein DB-Hit, kein Race-Condition) ──────────────
    ok, reason = _mem_check("anthropic")
    if not ok:
        log.warning("AIBudgetGuard: Anthropic MEM-LIMIT — %s", reason)
        return False, reason
    # ── Supabase State als zweite Prüfung ──────────────────────────────────────
    state = _sb_get("anthropic")
    if state is None:
        log.error("AIBudgetGuard: Kein State-Backend! Anthropic BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_USD_LIMIT:
        log.warning("AIBudgetGuard: Anthropic Tageslimit $%.2f erreicht!", DAILY_USD_LIMIT)
        _maybe_send_budget_alert("anthropic", state["usd_spent"], DAILY_USD_LIMIT)
        return False, f"Anthropic Tageslimit ${DAILY_USD_LIMIT:.2f} erreicht"
    _maybe_send_budget_alert("anthropic", state["usd_spent"], DAILY_USD_LIMIT)
    return True, module


def is_allowed_oai(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    ok, reason = _mem_check("openai")
    if not ok:
        log.warning("AIBudgetGuard: OpenAI MEM-LIMIT — %s", reason)
        return False, reason
    state = _sb_get("openai")
    if state is None:
        log.error("AIBudgetGuard: Kein State-Backend! OpenAI BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_OAI_USD_LIMIT:
        _maybe_send_budget_alert("openai", state["usd_spent"], DAILY_OAI_USD_LIMIT)
        return False, f"OpenAI Tageslimit ${DAILY_OAI_USD_LIMIT:.2f} erreicht"
    return True, module


def is_allowed_pplx(caller: str = "") -> tuple[bool, str]:
    module = caller or _caller_module()
    if module not in REVENUE_MODULES:
        return False, f"Modul '{module}' nicht in Revenue-Whitelist"
    ok, reason = _mem_check("perplexity")
    if not ok:
        log.warning("AIBudgetGuard: Perplexity MEM-LIMIT — %s", reason)
        return False, reason
    state = _sb_get("perplexity")
    if state is None:
        log.error("AIBudgetGuard: Kein State-Backend! Perplexity BLOCKIERT (fail-closed)")
        return False, "State-Backend nicht verfügbar — fail-closed"
    if state["usd_spent"] >= DAILY_PPLX_USD_LIMIT:
        return False, f"Perplexity Tageslimit ${DAILY_PPLX_USD_LIMIT:.2f} erreicht"
    return True, module


def record_usage(input_tokens: int, output_tokens: int, caller: str = "") -> None:
    cost = (input_tokens / 1000 * COST_PER_1K_IN) + (output_tokens / 1000 * COST_PER_1K_OUT)
    # In-Memory zuerst aktualisieren (sofort wirksam, kein DB-Lag)
    _add_mem_cost("anthropic", cost)
    state = _sb_get("anthropic") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("anthropic", state)
    log.info("Anthropic: +$%.5f | Heute: $%.4f / $%.2f", cost, state["usd_spent"], DAILY_USD_LIMIT)
    _maybe_send_budget_alert("anthropic", state["usd_spent"], DAILY_USD_LIMIT)


def record_usage_oai(input_tokens: int, output_tokens: int, caller: str = "") -> None:
    cost = (input_tokens / 1000 * OAI_COST_PER_1K_IN) + (output_tokens / 1000 * OAI_COST_PER_1K_OUT)
    _add_mem_cost("openai", cost)
    state = _sb_get("openai") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + cost, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("openai", state)
    _maybe_send_budget_alert("openai", state["usd_spent"], DAILY_OAI_USD_LIMIT)


def record_usage_pplx(caller: str = "") -> None:
    _add_mem_cost("perplexity", PPLX_COST_PER_REQ)
    state = _sb_get("perplexity") or {"date": _today(), "usd_spent": 0.0, "calls": 0}
    state["usd_spent"] = round(state["usd_spent"] + PPLX_COST_PER_REQ, 6)
    state["calls"] = state.get("calls", 0) + 1
    _sb_save("perplexity", state)
    _maybe_send_budget_alert("perplexity", state["usd_spent"], DAILY_PPLX_USD_LIMIT)


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
