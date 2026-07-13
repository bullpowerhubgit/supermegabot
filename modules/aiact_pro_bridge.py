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
