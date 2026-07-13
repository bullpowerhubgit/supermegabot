#!/usr/bin/env python3
"""Alias: leitet weiter zu modules.zvg_radar; bietet generische Lead-Finder-API."""
import logging
from typing import List, Dict

_log = logging.getLogger(__name__)

try:
    from modules.zvg_radar import (
        run_cycle,
        run_zvg_cycle,
        scrape_zvg,
        init_db,
        enrich_with_ai,
    )
    _log.debug("lead_finder: zvg_radar geladen")
except ImportError as _e:
    _log.warning("lead_finder: zvg_radar nicht verfügbar (%s)", _e)
    async def run_cycle() -> Dict:
        return {"status": "nicht verfügbar"}
    async def run_zvg_cycle() -> Dict:
        return {}
    async def scrape_zvg(max_per_land: int = 15) -> List[Dict]:
        return []
    def init_db() -> None:
        pass
    async def enrich_with_ai(entry: Dict) -> str:
        return ""


# ── Generische Lead-Finder-API (stub) ────────────────────────────────────────

import json
import os
from pathlib import Path

_LEADS_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "lead_finder_leads.json"


def _load_leads() -> List[Dict]:
    """Lädt gespeicherte Leads aus JSON-Datei."""
    try:
        if _LEADS_FILE.exists():
            return json.loads(_LEADS_FILE.read_text())
    except Exception as exc:
        _log.warning("lead_finder: Leads konnten nicht geladen werden: %s", exc)
    return []


def _save_leads(leads: List[Dict]) -> None:
    """Speichert Lead-Liste in JSON-Datei."""
    try:
        _LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LEADS_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2))
    except Exception as exc:
        _log.warning("lead_finder: Leads konnten nicht gespeichert werden: %s", exc)


def get_lead_stats() -> Dict:
    """Gibt Statistiken der gespeicherten Lead-Pipeline zurück."""
    leads = _load_leads()
    scored = [l for l in leads if l.get("score", 0) > 0]
    pipeline_value = sum(l.get("estimated_value", 0) for l in leads)
    return {
        "total_leads": len(leads),
        "scored_leads": len(scored),
        "pipeline_value_eur": pipeline_value,
    }


async def get_leads() -> List[Dict]:
    """Gibt alle gespeicherten Leads zurück."""
    return _load_leads()


async def discover_shopify_stores(limit: int = 20) -> List[Dict]:
    """Stub: Rückgabe leerer Liste (kein Shopify-Discovery-Backend verfügbar)."""
    _log.warning("lead_finder.discover_shopify_stores: kein Backend verfügbar")
    return []


async def scan_and_score_leads(stores: List[Dict]) -> List[Dict]:
    """Stub: Rückgabe leerer Liste (kein Scan-Backend verfügbar)."""
    _log.warning("lead_finder.scan_and_score_leads: kein Backend verfügbar")
    return []


async def lead_scan_loop() -> None:
    """Stub: Kein Lead-Scan-Loop ohne Backend."""
    _log.warning("lead_finder.lead_scan_loop: kein Backend verfügbar")
