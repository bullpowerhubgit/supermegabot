"""Lead Finder — Autonomes Shopify-Store-Scanning für AI-Act-Verstöße
Findet Shops, scannt sie, baut E-Mail-Pipeline.
"""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from modules.ai_act_scanner import scan_shopify_store

log = logging.getLogger("LeadFinder")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
LEADS_FILE = DATA_DIR / "compliance_leads.json"
BASE_URL = os.getenv("RAILWAY_STATIC_URL", "https://eu-compliance-saas-production.up.railway.app")

# Shopify-Store-Quellen (öffentlich durchsuchbar)
SHOPIFY_DISCOVERY_SOURCES = [
    "https://www.shopify.com/examples",
    "https://myip.ms/browse/sites/1/own/Shopify_Inc/20522/",
]

# Shopify-Stores identifizieren via Myshopify-Subdomain-Pattern oder powered-by-shopify
SHOPIFY_PATTERNS = [
    r"([\w-]+\.myshopify\.com)",
    r"href=[\"'](https?://[\w-]+\.myshopify\.com)[\"']",
]

# Fallback-Liste bekannter öffentlicher Shopify-Stores (De-anonymisiert, öffentlich)
SEED_STORES = [
    # DACH / erreichbare Stores (keine toten example-shops)
    "allbirds.com", "gymshark.com", "bombas.com",
    "blendjet.com", "drmartens.com", "babbel.com",
    "aboutyou.de", "flaschenpost.de",
    "ineedit.com.co",
]


async def discover_shopify_stores(limit: int = 20) -> list:
    """Findet Shopify-Stores via Web-Discovery."""
    stores = set(SEED_STORES[:limit])
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for url in SHOPIFY_DISCOVERY_SOURCES[:2]:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10),
                                           headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            for pattern in SHOPIFY_PATTERNS:
                                found = re.findall(pattern, html)
                                stores.update(found[:10])
                except Exception:
                    pass
    except Exception as e:
        log.warning("Discovery error: %s", e)
    return list(stores)[:limit]


async def scan_and_score_leads(stores: list) -> list:
    """Scannt eine Store-Liste und filtert Violation-Leads heraus."""
    qualified = []
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [scan_shopify_store(store, session) for store in stores]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, dict) and r.get("violations"):
            r["contacted"] = False
            r["discovered_at"] = datetime.now(timezone.utc).isoformat()
            r["outreach_text"] = _build_outreach(r)
            qualified.append(r)

    return qualified


def _build_outreach(scan: dict) -> str:
    """Erstellt personalisierten Outreach-Text für den Shop-Betreiber."""
    shop = scan.get("shop", "Ihr Shop")
    widgets = ", ".join(scan.get("widgets_found", [])[:3])
    days = max(0, (datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)).days)
    return (
        f"Betreff: Dringend: EU KI-Act Compliance für {shop} — Frist {days} Tage\n\n"
        f"Hallo,\n\n"
        f"wir haben {shop} automatisch auf EU KI-Verordnung Artikel 50 geprüft und folgendes gefunden:\n"
        f"• KI-Tools erkannt: {widgets or 'Chat-Widget, KI-Empfehlungen'}\n"
        f"• Offenlegungspflicht: FEHLT\n"
        f"• Bußgeldrisiko: bis €15.000.000 oder 3% Jahresumsatz (Art. 99 Abs. 4 lit. g EU-KI-VO)\n"
        f"• Frist: 2. August 2026 ({days} Tage)\n\n"
        f"Wir haben einen automatischen Fix: Ein Compliance-Banner-Skript, das in 5 Minuten integriert ist.\n\n"
        f"Kostenloser Scan-Report: {BASE_URL}/api/scan\n"
        f"Starter-Plan (€49/Monat): {BASE_URL}/#plans\n\n"
        f"Viele Grüße,\nEU Compliance Revenue Engine"
    )


def _load_leads() -> list:
    try:
        return json.loads(LEADS_FILE.read_text())
    except Exception:
        return []


def _save_leads(leads: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEADS_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2))


async def lead_scan_loop():
    """Läuft alle 4h: neue Stores entdecken, scannen, Leads speichern."""
    while True:
        try:
            log.info("Lead scan: discovering stores...")
            stores = await discover_shopify_stores(limit=15)
            new_leads = await scan_and_score_leads(stores)

            existing = _load_leads()
            existing_shops = {l["shop"] for l in existing}
            fresh = [l for l in new_leads if l["shop"] not in existing_shops]

            if fresh:
                existing.extend(fresh)
                _save_leads(existing)
                log.info("Lead scan: %d new qualified leads", len(fresh))
                # Telegram-Benachrichtigung
                try:
                    import aiohttp as ah
                    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
                    TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
                    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
                        msg = (
                            f"🎯 <b>Neue Compliance-Leads!</b>\n"
                            f"📊 {len(fresh)} neue Shops mit AI-Act-Verstößen\n"
                            f"🏷 Gesamt-Pipeline: {len(existing)} Leads\n"
                            f"💰 Potenzial bei 5% Conversion: €{len(existing)*0.05*49:.0f}/mo"
                        )
                        async with ah.ClientSession() as s:
                            await s.post(
                                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                                timeout=ah.ClientTimeout(total=5),
                            )
                except Exception:
                    pass
        except Exception as e:
            log.error("Lead scan loop error: %s", e)

        await asyncio.sleep(4 * 3600)


def get_lead_stats() -> dict:
    leads = _load_leads()
    contacted = [l for l in leads if l.get("contacted")]
    return {
        "total_leads": len(leads),
        "contacted": len(contacted),
        "pending_outreach": len(leads) - len(contacted),
        "top_risk_shops": [l["shop"] for l in leads[:5]],
        "pipeline_value_eur": len(leads) * 49 * 0.05,
    }
