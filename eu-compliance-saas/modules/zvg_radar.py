"""ZVG Radar NRW — Zwangsversteigerungs-Lead-Gen (≈19% des DE-Volumens in NRW)"""
import asyncio
import logging
import re
from datetime import datetime, timezone
import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("ZVGRadar")

ZVG_PORTAL_BASE = "https://www.zvg-portal.de"
NRW_COURTS = [
    "AG Aachen", "AG Bielefeld", "AG Bochum", "AG Bonn", "AG Dortmund",
    "AG Duisburg", "AG Düsseldorf", "AG Essen", "AG Gelsenkirchen",
    "AG Hagen", "AG Hamm", "AG Köln", "AG Krefeld", "AG Mönchengladbach",
    "AG Mülheim", "AG Münster", "AG Oberhausen", "AG Paderborn",
    "AG Siegen", "AG Solingen", "AG Wuppertal",
]

PROPERTY_TYPE_SCORES = {
    "einfamilienhaus": 95, "mehrfamilienhaus": 90, "eigentumswohnung": 85,
    "gewerbeobjekt": 80, "gewerbe": 80, "büro": 75, "laden": 70,
    "grundstück": 65, "garage": 40, "sonstige": 30,
}

LEAD_TEMPLATE = {
    "source": "zvg-portal.de",
    "region": "NRW",
    "lead_type": "Zwangsversteigerung",
    "cpl_range_eur": "50-200",
    "target_buyers": [
        "Insolvenzverwalter",
        "Distressed-Property-Investoren",
        "Restrukturierungsanwälte",
        "Immobilien-Asset-Manager",
    ],
}


async def fetch_zvg_listings(state: str = "NRW", limit: int = 50) -> list:
    """Scrapt aktuelle Zwangsversteigerungs-Listings vom ZVG-Portal."""
    leads = []
    try:
        # ZVG-Portal Suche nach Bundesland
        search_url = f"{ZVG_PORTAL_BASE}/versteigerung/list.do?action=getVersteigerung&land_abk=nw&gericht_id=0&verfahrensArt=Z&beginn_datum=&strasse=&plz=&ort=&objekt=&anzahl_treffer={limit}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; EUComplianceSaas/1.0)",
            "Accept": "text/html",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    log.warning("ZVG Portal returned status %s", resp.status)
                    return _generate_sample_leads(10)
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                rows = soup.find_all("tr", class_=re.compile(r"odd|even"))
                for row in rows[:limit]:
                    cells = row.find_all("td")
                    if len(cells) >= 5:
                        lead = {
                            **LEAD_TEMPLATE,
                            "court": cells[0].get_text(strip=True),
                            "case_number": cells[1].get_text(strip=True),
                            "auction_date": cells[2].get_text(strip=True),
                            "property_type": cells[3].get_text(strip=True),
                            "location": cells[4].get_text(strip=True),
                            "estimated_value_eur": _estimate_value(cells[3].get_text(strip=True)),
                            "lead_score": _score_lead(cells[3].get_text(strip=True)),
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }
                        leads.append(lead)
    except Exception as e:
        log.warning("ZVG scrape error: %s — using sample data", e)
        leads = _generate_sample_leads(10)

    if not leads:
        leads = _generate_sample_leads(10)

    leads.sort(key=lambda x: x.get("lead_score", 0), reverse=True)
    return leads


def _estimate_value(property_type: str) -> int:
    """Schätzt den Immobilienwert basierend auf Typ."""
    pt_lower = property_type.lower()
    if "mehrfamilienhaus" in pt_lower:
        return 450_000
    if "einfamilienhaus" in pt_lower or "haus" in pt_lower:
        return 280_000
    if "wohnung" in pt_lower:
        return 180_000
    if "gewerbe" in pt_lower or "büro" in pt_lower:
        return 320_000
    if "grundstück" in pt_lower:
        return 120_000
    return 150_000


def _score_lead(property_type: str) -> int:
    """Score 0-100 für Lead-Qualität."""
    pt_lower = property_type.lower()
    for key, score in PROPERTY_TYPE_SCORES.items():
        if key in pt_lower:
            return score
    return 50


def _generate_sample_leads(n: int) -> list:
    """Generiert Beispiel-Leads wenn Portal nicht erreichbar (Demo-Modus)."""
    sample_types = [
        ("Einfamilienhaus", "Dortmund", "AG Dortmund"),
        ("Eigentumswohnung", "Köln", "AG Köln"),
        ("Mehrfamilienhaus", "Düsseldorf", "AG Düsseldorf"),
        ("Gewerbeobjekt", "Essen", "AG Essen"),
        ("Eigentumswohnung", "Bochum", "AG Bochum"),
    ]
    leads = []
    for i in range(min(n, len(sample_types) * 2)):
        pt, loc, court = sample_types[i % len(sample_types)]
        leads.append({
            **LEAD_TEMPLATE,
            "court": court,
            "case_number": f"ZVG {100 + i}/26",
            "auction_date": "2026-09-15",
            "property_type": pt,
            "location": loc,
            "estimated_value_eur": _estimate_value(pt),
            "lead_score": _score_lead(pt),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "demo": True,
        })
    return leads


def get_nrw_market_stats() -> dict:
    """NRW-Marktstatistiken für Pitch/Dashboard."""
    return {
        "nrw_share_of_germany_pct": 19,
        "estimated_annual_auctions_nrw": 8500,
        "avg_property_value_eur": 220_000,
        "typical_cpl_eur_range": "50-200",
        "total_addressable_market_eur": 8500 * 100,
        "target_segments": NRW_COURTS,
        "data_source": "Argetra GmbH, Haufe, Deutsche Wirtschafts-Nachrichten",
        "last_verified": "2026-07-09",
    }
