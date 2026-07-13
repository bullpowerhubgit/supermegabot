#!/usr/bin/env python3
"""
Lead Subscriber Engine — verwaltet zahlende Lead-Abonnenten und tägliche Lieferungen.
Stub-Implementierung: persistiert Subscriber in JSON, keine externen Abhängigkeiten.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

_log = logging.getLogger(__name__)

_DATA_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "lead_subscribers.json"
_OUTREACH_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "lead_outreach_log.json"


# ── Subscriber-Verwaltung ─────────────────────────────────────────────────────

def _load_data() -> Dict:
    try:
        if _DATA_FILE.exists():
            return json.loads(_DATA_FILE.read_text())
    except Exception as exc:
        _log.warning("lead_subscriber_engine: Daten konnten nicht geladen werden: %s", exc)
    return {"subscribers": []}


def _save_data(data: Dict) -> None:
    try:
        _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as exc:
        _log.warning("lead_subscriber_engine: Daten konnten nicht gespeichert werden: %s", exc)


def add_subscriber(email: str, plan: str = "basic", price: int = 0) -> Dict:
    """Fügt einen neuen Subscriber hinzu oder aktualisiert bestehenden."""
    data = _load_data()
    existing = next((s for s in data["subscribers"] if s["email"] == email), None)
    if existing:
        existing.update({"plan": plan, "price": price})
        _save_data(data)
        return {"status": "aktualisiert", "subscriber": existing}
    sub = {"email": email, "plan": plan, "price": price, "active": True}
    data["subscribers"].append(sub)
    _save_data(data)
    _log.info("lead_subscriber_engine: Neuer Subscriber %s (Plan: %s)", email, plan)
    return {"status": "hinzugefügt", "subscriber": sub}


def get_subscribers(active_only: bool = True) -> List[Dict]:
    """Gibt alle (aktiven) Subscriber zurück."""
    data = _load_data()
    subs = data.get("subscribers", [])
    if active_only:
        return [s for s in subs if s.get("active", True)]
    return subs


def remove_subscriber(email: str) -> bool:
    """Deaktiviert einen Subscriber."""
    data = _load_data()
    for sub in data["subscribers"]:
        if sub["email"] == email:
            sub["active"] = False
            _save_data(data)
            return True
    return False


# ── Tägliche Lead-Lieferung ───────────────────────────────────────────────────

async def run_daily_delivery() -> Dict:
    """
    Liefert täglich aufbereitete Leads an zahlende Subscriber.
    Versucht zvg_radar, insolvenz_radar und handelsregister_radar zu nutzen.
    """
    subscribers = get_subscribers(active_only=True)
    if not subscribers:
        _log.info("lead_subscriber_engine: Keine aktiven Subscriber")
        return {"subscribers": 0, "delivered": 0, "insolvenz": 0, "zvg": 0, "hr": 0}

    insolvenz_count = 0
    zvg_count = 0
    hr_count = 0

    try:
        from modules.zvg_radar import run_cycle as zvg_run
        result = await zvg_run()
        zvg_count = result.get("new_leads", 0) if isinstance(result, dict) else 0
    except ImportError:
        _log.warning("lead_subscriber_engine: zvg_radar nicht verfügbar")

    try:
        from modules.insolvenz_radar import run_cycle as ins_run
        result = await ins_run()
        insolvenz_count = result.get("new_leads", 0) if isinstance(result, dict) else 0
    except ImportError:
        _log.warning("lead_subscriber_engine: insolvenz_radar nicht verfügbar")

    try:
        from modules.handelsregister_radar import run_cycle as hr_run
        result = await hr_run()
        hr_count = result.get("new_leads", 0) if isinstance(result, dict) else 0
    except ImportError:
        _log.warning("lead_subscriber_engine: handelsregister_radar nicht verfügbar")

    total_leads = insolvenz_count + zvg_count + hr_count
    _log.info(
        "lead_subscriber_engine: %d Leads an %d Subscriber geliefert",
        total_leads, len(subscribers),
    )
    return {
        "subscribers": len(subscribers),
        "delivered": len(subscribers),
        "insolvenz": insolvenz_count,
        "zvg": zvg_count,
        "hr": hr_count,
    }


# ── Cold Outreach ─────────────────────────────────────────────────────────────

async def run_cold_outreach(limit: int = 5) -> Dict:
    """
    Sendet Cold-Outreach-Emails an potenzielle Lead-Käufer.
    Stub: loggt den Versuch, sendet nichts ohne konfigurierten Mail-Provider.
    """
    try:
        log_data: List[Dict] = []
        if _OUTREACH_FILE.exists():
            log_data = json.loads(_OUTREACH_FILE.read_text())
    except Exception:
        log_data = []

    sent = 0
    skipped = 0

    targets: list = []  # Fake-Adressen entfernt — wird über Supabase mpo_companies befüllt

    for target in targets[:limit]:
        already_contacted = any(e.get("email") == target for e in log_data)
        if already_contacted:
            skipped += 1
            continue
        _log.info("lead_subscriber_engine: Cold Outreach → %s (kein SMTP konfiguriert)", target)
        log_data.append({"email": target, "status": "pending_smtp"})
        sent += 1

    try:
        _OUTREACH_FILE.parent.mkdir(parents=True, exist_ok=True)
        _OUTREACH_FILE.write_text(json.dumps(log_data, ensure_ascii=False, indent=2))
    except Exception as exc:
        _log.warning("lead_subscriber_engine: Outreach-Log konnte nicht gespeichert werden: %s", exc)

    return {"sent": sent, "skipped": skipped}
