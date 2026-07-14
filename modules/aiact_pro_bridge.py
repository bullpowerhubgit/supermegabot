#!/usr/bin/env python3
"""
AIACT-Pro Bridge — verbindet SuperMegaBot mit dem lokalen AIACT-Pro Server
==========================================================================
AIACT-Pro läuft auf http://127.0.0.1:8770 (Edition PRO, dauerhaft aktiv).
Dieser Bridge-Layer macht alle AIACT-Pro Endpunkte für interne MegaBot-Nutzung
zugänglich und cached Ergebnisse 10 Minuten lang (SQLite).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

log = logging.getLogger(__name__)

AIACT_BASE  = os.getenv("AIACT_PRO_URL", "http://127.0.0.1:8770")
CACHE_TTL   = 600  # 10 Minuten Cache
_DB_PATH    = Path(__file__).parent.parent / "data" / "aiact_bridge_cache.db"


# ── Cache DB ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            ts      INTEGER NOT NULL
        )
    """)
    conn.commit()
    return conn


def _cache_get(key: str) -> Optional[dict]:
    try:
        conn = _db()
        row = conn.execute(
            "SELECT value, ts FROM cache WHERE key=?", (key,)
        ).fetchone()
        conn.close()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(key: str, value: dict):
    try:
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, ts) VALUES (?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── HTTP Helpers ──────────────────────────────────────────────────────────────

async def _get(path: str, params: dict | None = None) -> Dict[str, Any]:
    url = f"{AIACT_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except aiohttp.ClientConnectorError:
        log.warning("AIACT-Pro nicht erreichbar (%s) — bitte lokal starten", AIACT_BASE)
        return {"ok": False, "error": "AIACT-Pro offline", "offline": True}
    except Exception as e:
        log.error("AIACT-Pro GET %s: %s", path, e)
        return {"ok": False, "error": str(e)}


async def _post(path: str, payload: dict) -> Dict[str, Any]:
    url = f"{AIACT_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"}
            ) as r:
                return await r.json()
    except aiohttp.ClientConnectorError:
        log.warning("AIACT-Pro nicht erreichbar (%s) — bitte lokal starten", AIACT_BASE)
        return {"ok": False, "error": "AIACT-Pro offline", "offline": True}
    except Exception as e:
        log.error("AIACT-Pro POST %s: %s", path, e)
        return {"ok": False, "error": str(e)}


# ── Public API ────────────────────────────────────────────────────────────────

async def health() -> Dict[str, Any]:
    """Prüft ob AIACT-Pro lokal erreichbar ist."""
    return await _get("/health")


async def scan_ai_act(shop_url: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    AI-Act Art. 50 Compliance-Scan für einen Shop oder eine URL.
    Ergebnis: {risk_level, violations, recommendations, score}
    """
    cache_key = f"scan:{shop_url}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached:
            log.debug("AIACT cache hit: %s", shop_url)
            return cached
    result = await _post("/api/scan", {"url": shop_url, "shop_url": shop_url})
    if result.get("ok") is not False:
        _cache_set(cache_key, result)
    return result


async def classify_hs_code(product_title: str, description: str = "") -> Dict[str, Any]:
    """
    HS-Code Klassifizierung für Zollreform (EU €150 Freigrenze abgeschafft).
    Ergebnis: {hs_code, hs_description, duty_rate, vat_applicable}
    """
    cache_key = f"hs:{product_title[:80]}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    result = await _post("/api/hs-classify", {
        "title": product_title,
        "description": description,
    })
    if result.get("ok") is not False:
        _cache_set(cache_key, result)
    return result


async def vat_risk(country: str, revenue_eur: float) -> Dict[str, Any]:
    """
    EU VAT OSS Risiko-Assessment.
    Ergebnis: {oss_required, threshold_exceeded, registration_countries, risk_level}
    """
    cache_key = f"vat:{country}:{int(revenue_eur)}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    result = await _post("/api/vat/risk", {
        "country": country,
        "revenue_eur": revenue_eur,
    })
    if result.get("ok") is not False:
        _cache_set(cache_key, result)
    return result


async def zvg_leads(min_score: int = 80, limit: int = 20) -> Dict[str, Any]:
    """
    ZVG NRW Zwangsversteigerungen — qualifizierte Leads.
    Ergebnis: {leads: [{address, value, score, deadline}]}
    """
    cache_key = f"zvg:{min_score}:{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    result = await _get("/api/zvg/leads", {"min_score": min_score, "limit": limit})
    if result.get("ok") is not False:
        _cache_set(cache_key, result)
    return result


async def generate_compliance_report(
    shop_url: str,
    plan: str = "pro",
    recipient_email: str = "",
) -> Dict[str, Any]:
    """
    Vollständiger EU Compliance PDF-Report (AI-Act + Zoll + VAT).
    Ergebnis: {pdf_url, report_id, pages, summary}
    """
    return await _post("/api/compliance/report", {
        "shop_url": shop_url,
        "plan": plan,
        "email": recipient_email,
    })


async def batch_scan(urls: list[str], concurrency: int = 3) -> list[Dict[str, Any]]:
    """Scannt mehrere Shops parallel (max concurrency gleichzeitig)."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(url: str) -> Dict[str, Any]:
        async with sem:
            return await scan_ai_act(url)

    return await asyncio.gather(*[_one(u) for u in urls], return_exceptions=False)


# ── SuperMegaBot-System-Sync ──────────────────────────────────────────────────

SUPERMEGABOT_AI_SYSTEMS = [
    {"name": "Mass Outreach KI",    "purpose": "Automatisiertes B2B-Email-Marketing via KI", "data": "Firmenname, Email-Adressen, Branche", "context": "B2B-Vertrieb aiitec.de"},
    {"name": "Email-Brain KI",      "purpose": "KI-Klassifizierung eingehender Emails, Auto-Antwort via Groq", "data": "Email-Inhalte, Absender", "context": "Kundenkommunikation"},
    {"name": "RudiClone Agent-KI",  "purpose": "Autonomer Business-Strategie-Agent", "data": "Markt- und Revenue-Daten", "context": "Interne Business-Entscheidungen"},
    {"name": "Post Guardian KI",    "purpose": "KI-Inhaltsmoderation für Social-Media-Posts", "data": "Post-Texte, Metadaten", "context": "Social-Media-Marketing"},
    {"name": "Shopify Blog Auto-KI","purpose": "KI-generierte Blogartikel via Claude/Groq", "data": "Produkt-Daten, SEO-Keywords", "context": "Content-Marketing ineedit.com.co"},
    {"name": "AI Trend Analyse",    "purpose": "KI-Produkt-Trend-Erkennung, Marktrecherche", "data": "Öffentliche Produktdaten, Preise", "context": "E-Commerce-Automatisierung"},
    {"name": "Phone AI MAX",        "purpose": "KI-Telefon-Bot (OpenAI Realtime + Twilio)", "data": "Gesprächsinhalte, Telefonnummern", "context": "Automatisierter Vertrieb DACH"},
]


async def sync_systems() -> Dict[str, Any]:
    """Registriert alle SuperMegaBot-KI-Systeme in AIACT-Pro."""
    existing_data = await _get("/api/systems")
    if existing_data.get("offline") or not isinstance(existing_data.get("systems"), list):
        return {"ok": False, "error": "AIACT-Pro offline"}
    existing_names = {s.get("name", "") for s in existing_data.get("systems", [])}
    registered = 0
    skipped = 0
    for sys_def in SUPERMEGABOT_AI_SYSTEMS:
        if sys_def["name"] in existing_names:
            skipped += 1
            continue
        result = await _post("/api/systems", sys_def)
        if result and not result.get("error"):
            registered += 1
            log.info("AIACT-Pro: registriert '%s'", sys_def["name"])
    return {"ok": True, "registered": registered, "skipped": skipped, "total": len(SUPERMEGABOT_AI_SYSTEMS)}


async def get_compliance_status() -> Dict[str, Any]:
    """Holt Compliance-Status aller registrierten Systeme."""
    cached = _cache_get("compliance_status")
    if cached:
        return {**cached, "from_cache": True}
    data = await _get("/api/systems")
    if data.get("offline"):
        return {"ok": False, "error": "AIACT-Pro offline"}
    systems = data.get("systems", [])
    risk_summary: dict = {}
    high_risk: list = []
    for s in systems:
        c = s.get("classification", {})
        level = c.get("level", "minimal")
        risk_summary[level] = risk_summary.get(level, 0) + 1
        if level in ("high", "unacceptable"):
            high_risk.append({"name": s.get("name"), "level": level, "label": c.get("label", ""), "fine": c.get("fine", "")})
    result = {
        "ok": True,
        "total_systems": len(systems),
        "risk_summary": risk_summary,
        "high_risk_count": len(high_risk),
        "high_risk_systems": high_risk,
        "compliant": len(high_risk) == 0,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    _cache_set("compliance_status", result)
    return result


async def run_compliance_check() -> Dict[str, Any]:
    """Vollständiger Check: Sync → Status → Telegram-Alert."""
    sync_r = await sync_systems()
    status = await get_compliance_status()
    try:
        from modules.notify_hub import async_send_telegram
        high = status.get("high_risk_count", 0)
        total = status.get("total_systems", 0)
        if not status.get("ok"):
            msg = f"ℹ️ <b>AIACT-Pro</b> offline — Cache-Stand genutzt"
        elif high > 0:
            msg = (f"⚠️ <b>AIACT-Pro: {high} Hochrisiko-Systeme!</b>\n"
                   + "\n".join(f"⚠️ {s['name'][:40]}: {s['label']}" for s in status.get("high_risk_systems", [])[:3]))
        else:
            summary = " | ".join(f"{k}: {v}" for k, v in status.get("risk_summary", {}).items())
            msg = f"✅ <b>AIACT-Pro Compliance OK</b>\n{total} Systeme — kein Hochrisiko\n{summary}"
        await async_send_telegram(msg)
    except Exception:
        pass
    return {"ok": True, "sync": sync_r, "compliance": status}


# ── Standalone-Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _test():
        h = await health()
        log.info("Health: %s", h)
        if h.get("offline"):
            log.warning("AIACT-Pro nicht gestartet — starte mit: open ~/aiact-pro/AIACT-Pro-Start.command")
            return
        r = await scan_ai_act("https://ineedit.com.co")
        log.info("Scan: %s", json.dumps(r, indent=2, ensure_ascii=False))

    asyncio.run(_test())
