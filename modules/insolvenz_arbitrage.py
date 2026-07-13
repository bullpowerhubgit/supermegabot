"""
insolvenz_arbitrage.py — Insolvenz-Arbitrage-Modul fuer SuperMegaBot
Scannt insolvenz_radar.db fuer Score >= 90, berechnet Arbitrage-Parameter,
erstellt Shopify Draft-Listings und sendet Telegram-Alerts.

SICHERHEITSREGELN:
- NIEMALS automatisch Geld ausgeben
- Shopify-Produkte immer als Draft (status=draft)
- Capital-Limit-Check vor jedem Listing
- Kein Demo-Daten-Fallback
"""

import asyncio
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("insolvenz_arbitrage")

TECH_KEYWORDS = [
    "smart", "sensor", "zigbee", "matter", "solar", "wifi", "wi-fi",
    "bluetooth", "iot", "home automation", "smarthome", "alexa", "google home",
    "led", "rgb", "controller", "gateway", "hub", "mesh", "z-wave",
    "powerstation", "inverter",
]

ARBITRAGE_MAX_CAPITAL = float(os.getenv("ARBITRAGE_MAX_CAPITAL", "5000"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ADMIN_API_TOKEN = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
INSOLVENZ_DB = os.getenv("INSOLVENZ_DB", "data/insolvenz_radar.db")
ARBITRAGE_DB = os.getenv("ARBITRAGE_DB", "data/arbitrage_capital.db")


@dataclass
class ArbitrageOpportunity:
    lead_id: str
    company_name: str
    insolvenz_score: float
    estimated_inventory_value: float
    buy_price_target: float
    expected_sell_price: float
    expected_roi_percent: float
    product_categories: list
    contact_hint: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "new"
    shopify_product_id: Optional[str] = None
    rechtsform: str = ""
    gericht: str = ""
    aktenzeichen: str = ""
    branche: str = ""


class InsolvenzArbitrage:
    def __init__(self):
        self._ensure_capital_db()

    def _ensure_capital_db(self):
        os.makedirs("data", exist_ok=True)
        conn = sqlite3.connect(ARBITRAGE_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS arbitrage_capital (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS arbitrage_scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT DEFAULT (datetime('now')),
                opportunities_found INTEGER DEFAULT 0,
                details TEXT
            )
        """)
        conn.commit()
        conn.close()

    # -------------------------------------------------------------------------
    # 1. scan_opportunities
    # -------------------------------------------------------------------------
    async def scan_opportunities(self) -> list:
        if not os.path.exists(INSOLVENZ_DB):
            logger.warning("insolvenz_radar.db nicht gefunden: %s", INSOLVENZ_DB)
            return []

        conn = sqlite3.connect(INSOLVENZ_DB)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT * FROM leads
                WHERE score >= 90
                ORDER BY score DESC
            """).fetchall()
        except sqlite3.OperationalError as e:
            logger.error("DB-Fehler beim Lesen der Leads: %s", e)
            conn.close()
            return []
        conn.close()

        opportunities = []
        for row in rows:
            row_dict = dict(row)
            text_blob = " ".join([
                str(row_dict.get("company_name", "")),
                str(row_dict.get("branche", "")),
                str(row_dict.get("description", "")),
                str(row_dict.get("products", "")),
            ]).lower()

            matched_keywords = [kw for kw in TECH_KEYWORDS if kw in text_blob]
            if len(matched_keywords) == 0:
                continue

            score = float(row_dict.get("score", 0))
            inv_value = await self.estimate_inventory(row_dict)
            buy_target = round(inv_value * 0.10, 2)
            sell_price = round(inv_value * 0.35, 2)
            roi = round(((sell_price - buy_target) / buy_target) * 100, 1) if buy_target > 0 else 0

            opp = ArbitrageOpportunity(
                lead_id=str(row_dict.get("id", "")),
                company_name=row_dict.get("company_name", "Unbekannt"),
                insolvenz_score=score,
                estimated_inventory_value=inv_value,
                buy_price_target=buy_target,
                expected_sell_price=sell_price,
                expected_roi_percent=roi,
                product_categories=matched_keywords[:5],
                contact_hint=row_dict.get("contact_hint", row_dict.get("gericht", "")),
                rechtsform=row_dict.get("rechtsform", ""),
                gericht=row_dict.get("gericht", ""),
                aktenzeichen=row_dict.get("aktenzeichen", ""),
                branche=row_dict.get("branche", ""),
            )
            opportunities.append(opp)

        conn = sqlite3.connect(ARBITRAGE_DB)
        conn.execute(
            "INSERT INTO arbitrage_scan_log (opportunities_found, details) VALUES (?, ?)",
            (len(opportunities), f"Keywords: {TECH_KEYWORDS[:5]}")
        )
        conn.commit()
        conn.close()

        logger.info("Scan abgeschlossen: %d Opportunitaeten gefunden", len(opportunities))
        return opportunities

    # -------------------------------------------------------------------------
    # 2. estimate_inventory
    # -------------------------------------------------------------------------
    async def estimate_inventory(self, row: dict) -> float:
        rechtsform = str(row.get("rechtsform", "")).lower()
        branche = str(row.get("branche", "")).lower()
        score = float(row.get("score", 90))

        if "ag" in rechtsform or "se" in rechtsform:
            employees_est = 150
        elif "gmbh" in rechtsform:
            employees_est = 40
        elif "kg" in rechtsform or "ohg" in rechtsform:
            employees_est = 20
        else:
            employees_est = 10

        if any(b in branche for b in ["elektronik", "technologie", "it", "solar", "smart"]):
            multiplier = 8000
        elif any(b in branche for b in ["handel", "import", "export", "logistik"]):
            multiplier = 5000
        elif any(b in branche for b in ["produktion", "fertigung", "manufaktur"]):
            multiplier = 6000
        else:
            multiplier = 3000

        score_bonus = 1.0 + ((score - 90) / 100)
        heuristic_value = employees_est * multiplier * score_bonus

        if ANTHROPIC_API_KEY:
            try:
                claude_value = await self._claude_inventory_estimate(row, heuristic_value)
                final = round(heuristic_value * 0.6 + claude_value * 0.4, 2)
            except Exception as e:
                logger.warning("Claude-Schaetzung fehlgeschlagen: %s", e)
                final = round(heuristic_value, 2)
        else:
            final = round(heuristic_value, 2)

        final = max(5000.0, min(500000.0, final))
        return final

    async def _claude_inventory_estimate(self, row: dict, heuristic: float) -> float:
        prompt = (
            f"Du bist Insolvenz-Experte. Schaetze den Lagerwert (EUR) fuer:\n"
            f"Firma: {row.get('company_name', 'n/a')}\n"
            f"Rechtsform: {row.get('rechtsform', 'n/a')}\n"
            f"Branche: {row.get('branche', 'n/a')}\n"
            f"Insolvenz-Score: {row.get('score', 'n/a')}/100\n"
            f"Heuristik-Schaetzung: EUR {heuristic:.0f}\n\n"
            f"Antworte NUR mit einer Zahl (EUR-Betrag), z.B.: 45000"
        )
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-haiku-20240307",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                text = data["content"][0]["text"].strip().replace(",", "")
                digits = "".join(c for c in text if c.isdigit() or c == ".")
                return float(digits) if digits else heuristic

    # -------------------------------------------------------------------------
    # 3. create_restposten_listing
    # -------------------------------------------------------------------------
    async def create_restposten_listing(self, opp: ArbitrageOpportunity) -> Optional[str]:
        cap = await self.capital_status()
        if cap["available"] < opp.buy_price_target:
            logger.warning(
                "Kapital nicht ausreichend: verfuegbar=%.2f, benoetigt=%.2f",
                cap["available"], opp.buy_price_target,
            )
            return None

        title = f"Restposten: {opp.company_name} – Smart-Home Tech"
        body = (
            f"<p><strong>Insolvenz-Restposten aus zertifizierter Quelle.</strong></p>"
            f"<p>Kategorie: {', '.join(opp.product_categories)}</p>"
            f"<p>Geschaetzter Originalwert: EUR {opp.estimated_inventory_value:,.0f}</p>"
            f"<p>Aktenzeichen: {opp.aktenzeichen or 'auf Anfrage'}</p>"
            f"<p>Zustand: gelagert, ungenutzt oder leicht gebraucht – Besichtigung moeglich.</p>"
        )
        tags = "liquidation,auslaufmodell,restposten,smart-home," + ",".join(opp.product_categories[:3])

        payload = {
            "product": {
                "title": title,
                "body_html": body,
                "vendor": "Restposten",
                "product_type": "Liquidation",
                "status": "draft",
                "tags": tags,
                "variants": [
                    {
                        "price": str(opp.expected_sell_price),
                        "compare_at_price": str(round(opp.estimated_inventory_value * 0.5, 2)),
                        "requires_shipping": True,
                        "inventory_management": None,
                    }
                ],
            }
        }

        url = (
            f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/"
            f"{SHOPIFY_API_VERSION}/products.json"
        )
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_TOKEN,
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    pid = str(data["product"]["id"])
                    opp.shopify_product_id = pid
                    logger.info("Shopify Draft erstellt: %s (ID %s)", title, pid)
                    return pid
                else:
                    text = await resp.text()
                    logger.error("Shopify-Fehler %d: %s", resp.status, text[:300])
                    return None

    # -------------------------------------------------------------------------
    # 4. alert_opportunity
    # -------------------------------------------------------------------------
    async def alert_opportunity(self, opp: ArbitrageOpportunity) -> bool:
        urgency = opp.insolvenz_score >= 95
        flag = "DRINGEND – Score >= 95!" if urgency else "Neue Arbitrage-Opportunitaet"

        msg = (
            f"{flag}\n\n"
            f"Firma: {opp.company_name}\n"
            f"Insolvenz-Score: {opp.insolvenz_score}/100\n"
            f"Lager-Schaetzwert: EUR {opp.estimated_inventory_value:,.0f}\n"
            f"Kaufziel (10%): EUR {opp.buy_price_target:,.0f}\n"
            f"Erwarteter VK (35%): EUR {opp.expected_sell_price:,.0f}\n"
            f"Erwarteter ROI: {opp.expected_roi_percent}%\n"
            f"Kategorien: {', '.join(opp.product_categories)}\n"
            f"Gericht: {opp.gericht or 'n/a'}\n"
            f"AZ: {opp.aktenzeichen or 'n/a'}\n"
            f"Kontakt-Hinweis: {opp.contact_hint or 'Insolvenzverwalter kontaktieren'}\n"
        )
        if urgency:
            msg += (
                "\nSOFORT-HANDLUNGSBEDARF: Insolvenzverwalter kontaktieren!\n"
                "Dieses Objekt hat hoechste Prioritaet (Score >= 95)."
            )
        if opp.shopify_product_id:
            msg += f"\nShopify Draft-ID: {opp.shopify_product_id}"

        return await self._send_telegram(msg)

    # -------------------------------------------------------------------------
    # 5. capital_status
    # -------------------------------------------------------------------------
    async def capital_status(self) -> dict:
        conn = sqlite3.connect(ARBITRAGE_DB)
        rows = conn.execute(
            "SELECT event, SUM(amount) as total FROM arbitrage_capital GROUP BY event"
        ).fetchall()
        conn.close()

        invested = 0.0
        returned = 0.0
        for event, total in rows:
            if event == "invest":
                invested += total or 0
            elif event == "return":
                returned += total or 0

        available = ARBITRAGE_MAX_CAPITAL - invested + returned
        return {
            "max_capital": ARBITRAGE_MAX_CAPITAL,
            "invested": round(invested, 2),
            "returned": round(returned, 2),
            "available": round(available, 2),
        }

    # -------------------------------------------------------------------------
    # 6. daily_report
    # -------------------------------------------------------------------------
    async def daily_report(self) -> str:
        cap = await self.capital_status()
        opportunities = await self.scan_opportunities()

        conn = sqlite3.connect(ARBITRAGE_DB)
        logs = conn.execute(
            "SELECT scanned_at, opportunities_found FROM arbitrage_scan_log ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()

        log_lines = "\n".join(
            [f"  {ts}: {n} Opportunitaeten" for ts, n in logs]
        ) or "  (keine Logs)"

        top10 = sorted(opportunities, key=lambda o: o.insolvenz_score, reverse=True)[:10]
        top_lines = ""
        for i, o in enumerate(top10, 1):
            top_lines += (
                f"\n{i}. {o.company_name} — Score {o.insolvenz_score} "
                f"| ROI {o.expected_roi_percent}% | EUR {o.buy_price_target:,.0f} Kaufziel"
            )

        report = (
            f"INSOLVENZ-ARBITRAGE TAGES-REPORT — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Kapital-Status:\n"
            f"  Max:        EUR {cap['max_capital']:,.0f}\n"
            f"  Investiert: EUR {cap['invested']:,.0f}\n"
            f"  Rueckfluss: EUR {cap['returned']:,.0f}\n"
            f"  Verfuegbar: EUR {cap['available']:,.0f}\n\n"
            f"Top-10 Opportunitaeten:{top_lines or ' (keine)'}\n\n"
            f"Letzte Scans:\n{log_lines}"
        )

        await self._send_telegram(report)
        return report

    # -------------------------------------------------------------------------
    # Hilfsmethoden
    # -------------------------------------------------------------------------
    async def _send_telegram(self, text: str) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram nicht konfiguriert")
            return False
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
            "parse_mode": "HTML",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    ok = resp.status == 200
                    if not ok:
                        logger.error("Telegram-Fehler %d", resp.status)
                    return ok
        except Exception as e:
            logger.error("Telegram-Verbindungsfehler: %s", e)
            return False


# =============================================================================
# Main / CLI
# =============================================================================
async def _run_scan_and_alert(arb: InsolvenzArbitrage):
    opportunities = await arb.scan_opportunities()
    if not opportunities:
        logger.info("Keine Opportunitaeten gefunden.")
        return
    for opp in opportunities:
        await arb.alert_opportunity(opp)
        if opp.insolvenz_score >= 95:
            pid = await arb.create_restposten_listing(opp)
            if pid:
                logger.info("Draft-Listing erstellt: %s", pid)


async def _daemon(arb: InsolvenzArbitrage):
    import schedule
    import time

    schedule.every().day.at("08:30").do(lambda: asyncio.ensure_future(_run_scan_and_alert(arb)))
    logger.info("Daemon gestartet — naechster Run um 08:30 Uhr")
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)


async def main():
    arb = InsolvenzArbitrage()

    if "--now" in sys.argv:
        await _run_scan_and_alert(arb)
    elif "--status" in sys.argv:
        cap = await arb.capital_status()
        print(f"Kapital-Status: {cap}")
    elif "--report" in sys.argv:
        report = await arb.daily_report()
        print(report)
    else:
        try:
            import schedule  # noqa: F401
            await _daemon(arb)
        except ImportError:
            logger.warning("'schedule' nicht installiert — Einmal-Scan statt Daemon")
            await _run_scan_and_alert(arb)


if __name__ == "__main__":
    asyncio.run(main())
