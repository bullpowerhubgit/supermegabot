#!/usr/bin/env python3
"""MegaBot EU Compliance Engine — AI Act Art. 50, HS-Code, ZVG Leads."""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.megabot_umsatzmaschine import MegaBotUmsatzmaschine

log = logging.getLogger("EUCompliance")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
REPORTS_DIR = DATA_DIR / "reports"
_EU_SAAS_DIR = Path(__file__).parent.parent / "eu-compliance-saas" / "modules"


def _load_eu_saas_module(name: str):
    path = _EU_SAAS_DIR / f"{name}.py"
    if not path.exists():
        raise ImportError(f"eu-compliance-saas module missing: {name}")
    spec = importlib.util.spec_from_file_location(f"eu_saas_{name}", path)
    if not spec or not spec.loader:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _normalize_shop_url(shop_url: str) -> str:
    url = (shop_url or "").strip().lower()
    url = re.sub(r"^https?://", "", url)
    return url.rstrip("/")


class EUComplianceEngine:
    def __init__(self, main_bot: "MegaBotUmsatzmaschine"):
        self.bot = main_bot

    def scan_shop(self, shop_url: str) -> Dict[str, Any]:
        """AI-Act Art. 50 Scan für Shopify/E-Commerce-URL."""
        return asyncio.run(self._scan_shop_async(shop_url))

    async def _scan_shop_async(self, shop_url: str) -> Dict[str, Any]:
        host = _normalize_shop_url(shop_url)
        try:
            ai_mod = _load_eu_saas_module("ai_act_scanner")
            report = await ai_mod.generate_compliance_report(host)
            report["shop_url"] = host
            return report
        except Exception as e:
            log.warning("Shop scan fallback: %s", e)
            from modules.ai_act_scanner import analyze_ai_risk
            risk = await analyze_ai_risk(host, "E-Commerce", "Deutschland")
            level = risk.get("risiko_level", "MITTEL")
            return {
                "shop_url": host,
                "has_ai_widgets": level in ("HOCH", "MITTEL", "HIGH", "MEDIUM"),
                "has_disclosure": False,
                "compliant": False,
                "risk_level": level,
                "fine_risk_eur": 15_000_000 if level in ("HOCH", "HIGH") else 3_500_000,
                "violations": [risk.get("empfehlung", "EU AI Act Prüfung empfohlen")],
                "disclosure_banner_html": (
                    '<div id="ai-act-disclosure">🤖 KI-Hinweis: Dieser Shop nutzt KI-Funktionen (EU AI Act Art. 50)</div>'
                ),
                "ai_summary": risk.get("ai_summary", ""),
            }

    def hs_classify(self, product_title: str, description: str = "") -> Dict[str, Any]:
        """HS-Code Klassifizierung (EU Zoll VO 2026/382)."""
        return asyncio.run(self._hs_classify_async(product_title, description))

    async def _hs_classify_async(self, product_title: str, description: str = "") -> Dict[str, Any]:
        try:
            hs_mod = _load_eu_saas_module("hs_classifier")
            result = await hs_mod.classify_hs_code(
                product_title, description, os.getenv("ANTHROPIC_API_KEY", ""),
            )
            return {
                "hs_code": result.get("hs_code", "9999.99"),
                "confidence": result.get("confidence", 0.3),
                "customs_fee_eur": result.get("customs_fee_eur", 3.0),
                "total_eu_fee_eur": result.get("total_eu_fee_eur", 5.0),
                "method": result.get("method", "?"),
                "hs_description": result.get("hs_description", ""),
            }
        except Exception as e:
            log.warning("HS classify error: %s", e)
            return {"hs_code": "9999.99", "confidence": 0.3, "customs_fee_eur": 3.0, "error": str(e)[:80]}

    def generate_compliance_report(self, shop_url: str) -> str:
        """Vollständiger EU-Compliance-Report als PDF."""
        scan = self.scan_shop(shop_url)
        host = _normalize_shop_url(shop_url)
        safe = re.sub(r"[^a-z0-9_]", "_", host.replace(".", "_"))
        filename = REPORTS_DIR / f"compliance_{safe}_{datetime.now().strftime('%Y%m%d')}.pdf"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        doc = SimpleDocTemplate(str(filename), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("EU Compliance Report — MegaBot", styles["Title"]),
            Paragraph(f"Shop: {host}", styles["Normal"]),
            Paragraph(f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles["Normal"]),
            Spacer(1, 0.5 * cm),
            Paragraph("<b>EU AI Act Art. 50 — Scan</b>", styles["Heading2"]),
        ]

        rows = [
            ["Kennzahl", "Wert"],
            ["KI-Widgets erkannt", "Ja" if scan.get("has_ai_widgets") else "Nein"],
            ["Offenlegung vorhanden", "Ja" if scan.get("has_disclosure") else "Nein"],
            ["Compliant", "Ja" if scan.get("compliant") else "Nein"],
            ["Risiko-Level", str(scan.get("risk_level", "?"))],
            ["Bußgeld-Risiko", f"€{scan.get('fine_risk_eur', 0):,}"],
        ]
        t = Table(rows, colWidths=[8 * cm, 6 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5 * cm))

        for v in scan.get("violations", []):
            story.append(Paragraph(f"• {v}", styles["Normal"]))
        if scan.get("recommended_action"):
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(f"<b>Empfehlung:</b> {scan['recommended_action']}", styles["Normal"]))
        if scan.get("law_reference"):
            story.append(Paragraph(f"<i>{scan['law_reference']}</i>", styles["Normal"]))

        doc.build(story)
        log.info("Compliance PDF: %s", filename)
        return str(filename)

    def get_zvg_leads(self, min_score: int = 80) -> List[Dict[str, Any]]:
        """ZVG NRW Lead-Radar aus lokaler DB + Portal-Fallback."""
        leads: List[Dict[str, Any]] = []
        try:
            from modules.megabot_umsatzmaschine import get_zvg_signals
            for row in get_zvg_signals(50):
                score = int(row.get("score", 0))
                if score < min_score:
                    continue
                leads.append({
                    "location": row.get("objekt_adresse") or row.get("bundesland", "NRW"),
                    "lead_score": score,
                    "value_eur": row.get("verkehrswert", 0),
                    "court": row.get("gericht", ""),
                    "property_type": row.get("objekt_typ", ""),
                    "source": "zvg_radar.db",
                })
        except Exception as e:
            log.warning("ZVG DB: %s", e)

        if len(leads) < 3:
            try:
                zvg_mod = _load_eu_saas_module("zvg_radar")
                scraped = asyncio.run(zvg_mod.fetch_zvg_listings("NRW", limit=30))
                for row in scraped:
                    score = int(row.get("lead_score", 0))
                    if score < min_score:
                        continue
                    leads.append({
                        "location": row.get("location", "NRW"),
                        "lead_score": score,
                        "value_eur": row.get("estimated_value_eur", 0),
                        "court": row.get("court", ""),
                        "property_type": row.get("property_type", ""),
                        "source": "zvg-portal.de",
                    })
            except Exception as e:
                log.warning("ZVG portal: %s", e)

        leads.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
        return leads[:25]


def add_compliance_to_megabot(main_bot: "MegaBotUmsatzmaschine") -> EUComplianceEngine:
    engine = EUComplianceEngine(main_bot)
    main_bot.compliance = engine
    log.info("EU Compliance Engine in MegaBot integriert.")
    return engine


if __name__ == "__main__":
    import json
    import sys

    from modules.megabot_umsatzmaschine import MegaBotUmsatzmaschine

    bot = MegaBotUmsatzmaschine()
    add_compliance_to_megabot(bot)
    shop = sys.argv[1] if len(sys.argv) > 1 else "ineedit.com.co"
    eng = bot.compliance
    scan = eng.scan_shop(shop)
    print(json.dumps({"scan": scan, "hs": eng.hs_classify("Portable Power Station 500Wh")}, indent=2, ensure_ascii=False))
    print("PDF:", eng.generate_compliance_report(shop))
    print("ZVG:", eng.get_zvg_leads(80)[:3])