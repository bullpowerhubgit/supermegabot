#!/usr/bin/env python3
"""MegaBot Funding Intelligence — Förder-Scan + KfW-Antrag für Gründer."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("FundingIntelligence")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
SCAN_FILE = DATA_DIR / "funding_scan.json"
REPORTS_DIR = DATA_DIR / "reports"

DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "rudolf sarkany": {
        "antragsteller": "Rudolf Sarkany",
        "unternehmen": "SuperMegaBot / ShopText.ai",
        "rechtsform": "Einzelunternehmen",
        "gruendungsjahr": "2025",
        "branche": "SaaS, E-Commerce-KI-Automatisierung",
        "mitarbeiter": 1,
        "bundesland": "NRW",
        "webseiten": ["ineedit.com.co", "supermegabot-production.up.railway.app"],
    },
}

FUNDING_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "kfw-startgeld-067",
        "name": "KfW ERP-Gründerkredit StartGeld (067)",
        "provider": "KfW",
        "type": "kredit",
        "max_amount_eur": 125000,
        "url": "https://www.kfw.de/inlandsfoerderung/Produkte/ERP-Gr%C3%BCnderkredit-StartGeld/",
        "tags": ["gruendung", "betriebsmittel", "einzelunternehmen"],
        "criteria": {"max_age_years": 3, "min_score": 70},
    },
    {
        "id": "kfw-erp-gruendung",
        "name": "KfW ERP-Förderkredit Unternehmensgründung",
        "provider": "KfW",
        "type": "kredit",
        "max_amount_eur": 500000,
        "url": "https://www.kfw.de/inlandsfoerderung/Produkte/ERP-F%C3%B6rderkredit-Unternehmensgr%C3%BCndung/",
        "tags": ["gruendung", "investition"],
        "criteria": {"max_age_years": 3, "min_score": 65},
    },
    {
        "id": "bafa-unternehmensberatung",
        "name": "BAFA Unternehmensberatung für KMU",
        "provider": "BAFA",
        "type": "zuschuss",
        "max_amount_eur": 2800,
        "url": "https://www.bafa.de/DE/Wirtschaft/Beratung_Finanzierung/Unternehmensberatung/unternehmensberatung_node.html",
        "tags": ["beratung", "digitalisierung"],
        "criteria": {"max_age_years": 10, "min_score": 55},
    },
    {
        "id": "invest-zuschuss",
        "name": "INVEST — Zuschuss für Wagniskapital",
        "provider": "BMWK",
        "type": "zuschuss",
        "max_amount_eur": 250000,
        "url": "https://www.bmwi.de/Redaktion/DE/Artikel/Wirtschaft/invest-zuschuss-fuer-wagniskapital.html",
        "tags": ["investor", "startup", "innovation"],
        "criteria": {"max_age_years": 7, "min_score": 60},
    },
    {
        "id": "eic-accelerator",
        "name": "EU EIC Accelerator",
        "provider": "EU",
        "type": "grant",
        "max_amount_eur": 2500000,
        "url": "https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en",
        "tags": ["deep-tech", "innovation", "saas"],
        "criteria": {"max_age_years": 15, "min_score": 50},
    },
    {
        "id": "digitalbonus-nrw",
        "name": "Digitalbonus NRW",
        "provider": "NRW",
        "type": "zuschuss",
        "max_amount_eur": 50000,
        "url": "https://www.wirtschaft.nrw/digitalbonus",
        "tags": ["digitalisierung", "nrw"],
        "criteria": {"bundesland": "NRW", "max_age_years": 10, "min_score": 58},
    },
]


class FundingIntelligenceEngine:
    def __init__(self, profiles: Optional[Dict[str, Dict[str, Any]]] = None):
        self.profiles = profiles or DEFAULT_PROFILES
        self.last_scan: Dict[str, Any] = {}
        if SCAN_FILE.exists():
            try:
                self.last_scan = json.loads(SCAN_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.last_scan = {}

    def _profile_for(self, name: str) -> Dict[str, Any]:
        key = name.strip().lower()
        base = dict(self.profiles.get(key, DEFAULT_PROFILES["rudolf sarkany"]))
        base["antragsteller"] = name.strip()
        return base

    async def _live_metrics(self) -> Dict[str, Any]:
        from modules.megabot_kfw_generator import fetch_live_antrag_data
        return await fetch_live_antrag_data()

    def _company_age_years(self, gruendungsjahr: str) -> int:
        try:
            return max(0, datetime.now().year - int(gruendungsjahr))
        except Exception:
            return 0

    def _score_opportunity(
        self,
        opp: Dict[str, Any],
        profile: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        criteria = opp.get("criteria", {})
        score = 40
        reasons: List[str] = []

        age = self._company_age_years(profile.get("gruendungsjahr", "2025"))
        max_age = criteria.get("max_age_years", 99)
        if age <= max_age:
            score += 20
            reasons.append(f"Unternehmensalter {age}J ≤ {max_age}J")
        else:
            score -= 15
            reasons.append(f"Unternehmen zu alt ({age}J)")

        if criteria.get("bundesland") and profile.get("bundesland") == criteria["bundesland"]:
            score += 15
            reasons.append(f"Region {profile['bundesland']} passt")

        branche = (profile.get("branche") or "").lower()
        if any(t in branche for t in ("saas", "software", "ki", "e-commerce", "digital")):
            score += 10
            reasons.append("Tech/SaaS-Branche")

        zahlen = metrics.get("aktuelle_zahlen", {})
        if zahlen.get("shopify_produkte", 0) > 1000:
            score += 8
            reasons.append(f"{zahlen['shopify_produkte']:,} Shopify-Produkte live")
        if zahlen.get("ds24_umsatz", 0) > 0:
            score += 7
            reasons.append(f"DS24-Umsatz €{zahlen['ds24_umsatz']}")
        if zahlen.get("monat_umsatz", 0) > 0:
            score += 5
            reasons.append(f"Monatsumsatz €{zahlen['monat_umsatz']}")

        if profile.get("rechtsform", "").lower() in ("einzelunternehmen", "gmbh", "ug"):
            score += 5
            reasons.append(f"Rechtsform {profile['rechtsform']}")

        score = max(0, min(100, score))
        min_score = criteria.get("min_score", 50)
        eligible = score >= min_score

        return {
            **opp,
            "score": score,
            "eligible": eligible,
            "reasons": reasons,
            "recommended_amount_eur": min(
                opp.get("max_amount_eur", 50000),
                int(metrics.get("kredit_betrag", 50000)),
            ) if opp.get("type") == "kredit" else opp.get("max_amount_eur"),
        }

    def run_daily_funding_scan(self, user_name: str = "Rudolf Sarkany") -> Dict[str, Any]:
        """Sucht und bewertet Förder-Opportunities für den Nutzer."""
        profile = self._profile_for(user_name)
        metrics = asyncio.run(self._live_metrics())

        scored = [
            self._score_opportunity(opp, profile, metrics)
            for opp in FUNDING_CATALOG
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        eligible = [o for o in scored if o["eligible"]]

        result = {
            "ok": True,
            "timestamp": datetime.now().isoformat(),
            "user": profile["antragsteller"],
            "profile": profile,
            "live_metrics": metrics.get("aktuelle_zahlen", {}),
            "opportunities_total": len(scored),
            "opportunities_eligible": len(eligible),
            "top_match": eligible[0] if eligible else (scored[0] if scored else None),
            "opportunities": scored,
        }

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SCAN_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        self.last_scan = result
        log.info(
            "Funding scan: %d eligible / %d total für %s",
            len(eligible), len(scored), profile["antragsteller"],
        )
        return result

    def generate_kfw_antrag_for_user(
        self,
        user_name: str = "Rudolf Sarkany",
        *,
        kredit_betrag: Optional[int] = None,
    ) -> str:
        """Erzeugt KfW StartGeld Businessplan-PDF für den Nutzer."""
        profile = self._profile_for(user_name)
        scan = self.last_scan
        if not scan or scan.get("user", "").lower() != user_name.strip().lower():
            scan = self.run_daily_funding_scan(user_name)

        top = scan.get("top_match") or {}
        amount = kredit_betrag or top.get("recommended_amount_eur") or 50000

        antrag_data = {
            **profile,
            "kredit_betrag": int(amount),
            "verwendung": {
                "marketing": int(amount * 0.4),
                "infrastruktur": int(amount * 0.3),
                "betrieb": int(amount * 0.2),
                "reserve": int(amount * 0.1),
            },
        }

        from modules.megabot_umsatzmaschine import MegaBotUmsatzmaschine
        pdf_path = MegaBotUmsatzmaschine().generate_kfw_antrag(antrag_data, merge_live=True)
        log.info("KfW Antrag für %s: %s", user_name, pdf_path)
        return pdf_path

    def get_status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "scan_file": str(SCAN_FILE),
            "last_scan": self.last_scan.get("timestamp"),
            "eligible": self.last_scan.get("opportunities_eligible", 0),
            "profiles": list(self.profiles.keys()),
        }


async def run_daily_funding_scan_str(user_name: str = "Rudolf Sarkany") -> str:
    r = FundingIntelligenceEngine().run_daily_funding_scan(user_name)
    top = r.get("top_match") or {}
    return (
        f"Funding scan {r['user']}: {r['opportunities_eligible']}/{r['opportunities_total']} eligible | "
        f"Top: {top.get('name', '?')} ({top.get('score', 0)}%)"
    )


if __name__ == "__main__":
    import sys

    engine = FundingIntelligenceEngine()
    name = sys.argv[1] if len(sys.argv) > 1 else "Rudolf Sarkany"
    cmd = (sys.argv[2] if len(sys.argv) > 2 else "all").lower()

    if cmd in ("scan", "all"):
        scan = engine.run_daily_funding_scan(name)
        print(json.dumps({
            "eligible": scan["opportunities_eligible"],
            "top": scan.get("top_match", {}).get("name"),
            "score": scan.get("top_match", {}).get("score"),
        }, indent=2, ensure_ascii=False))

    if cmd in ("kfw", "antrag", "all"):
        pdf = engine.generate_kfw_antrag_for_user(name)
        print(f"PDF erstellt: {pdf}")