"""
Ghost Vendor Network — unsichtbares Backend fuer fremde Shopify-Shops.

Bezieht Produkte aus dem eigenen ineedit-Shop, generiert SEO-Texte per KI,
optimiert Preise und laedt alles automatisch in Client-Shops hoch.

Pakete:
    basic  — 3 Produkte/Tag, EUR 299/mo
    pro    — 5 Produkte/Tag, EUR 499/mo
    elite  — 10 Produkte/Tag, EUR 699/mo

CLI:
    # Client hinzufuegen
    python3 modules/ghost_vendor_network.py \\
        --add myshop.myshopify.com shpat_xxx info@shop.de pro "Smart Home"

    # Alle Clients anzeigen (inkl. MRR)
    python3 modules/ghost_vendor_network.py --list

    # Sofort-Run (alle Clients)
    python3 modules/ghost_vendor_network.py --now

    # Daemon (06:00 UTC taeglich)
    python3 modules/ghost_vendor_network.py
"""

import argparse
import asyncio
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ghost_vendor_network")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ghost_vendor.db")

PACKAGES = {
    "basic": {"products_per_day": 3, "price_eur": 299},
    "pro": {"products_per_day": 5, "price_eur": 499},
    "elite": {"products_per_day": 10, "price_eur": 699},
}

# Marge nach Nische
MARGIN_MAP = {
    "smart home": 1.30,
    "solar": 1.30,
}
DEFAULT_MARGIN = 1.25

SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_domain TEXT NOT NULL UNIQUE,
            api_token TEXT NOT NULL,
            email TEXT,
            package TEXT DEFAULT 'basic',
            niche TEXT DEFAULT '',
            stripe_subscription_id TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS processed_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            source_title TEXT NOT NULL,
            client_product_id TEXT,
            processed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS monthly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            products_uploaded INTEGER DEFAULT 0,
            report_html TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Haupt-Klasse
# ---------------------------------------------------------------------------

class GhostVendorNetwork:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.db = _get_db()

        # Quell-Shop (ineedit)
        self.source_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        self.source_token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")

        # KI
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

        # Stripe
        self.stripe_key = os.getenv("STRIPE_SECRET_KEY", "")

        # Telegram
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    # ------------------------------------------------------------------
    # Produkte aus Quell-Shop holen + Nischen-Scoring
    # ------------------------------------------------------------------
    async def find_products_for_client(self, client_id: int, niche: str, limit: int = 250) -> list:
        if not self.source_domain or not self.source_token:
            log.warning("Quell-Shop-Credentials fehlen")
            return []

        url = (
            f"https://{self.source_domain}/admin/api/{SHOPIFY_API_VERSION}/products.json"
            f"?status=active&limit={limit}"
        )
        headers = {"X-Shopify-Access-Token": self.source_token}
        try:
            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                products = data.get("products", [])
        except Exception as exc:
            log.error("Quell-Shop-Abruf fehlgeschlagen: %s", exc)
            return []

        # Bereits verarbeitete Titel laden
        processed_rows = self.db.execute(
            "SELECT source_title FROM processed_products WHERE client_id=?", (client_id,)
        ).fetchall()
        processed_titles = {r["source_title"] for r in processed_rows}

        niche_keywords = niche.lower().split()
        scored = []
        for p in products:
            title = p.get("title", "")
            if title in processed_titles:
                continue
            title_lower = title.lower()
            score = sum(1 for kw in niche_keywords if kw in title_lower)
            if score > 0:
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    # ------------------------------------------------------------------
    # SEO-Text generieren (Claude Haiku -> GPT-4o-mini Fallback)
    # ------------------------------------------------------------------
    async def generate_seo_text(self, title: str, niche: str) -> str:
        prompt = (
            f"Schreibe einen kurzen, SEO-optimierten Produktbeschreibungstext (150-200 Woerter) "
            f"fuer das Produkt '{title}' in der Nische '{niche}'. "
            f"Auf Deutsch. Kein Markdown, nur reiner Text."
        )

        # Versuch 1: Anthropic Claude Haiku
        if self.anthropic_key:
            try:
                payload = {
                    "model": "claude-haiku-20240307",
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                }
                async with self.session.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers={
                        "x-api-key": self.anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("content", [{}])[0].get("text", "").strip()
                        if text:
                            return text
            except Exception as exc:
                log.warning("Claude Haiku fehlgeschlagen: %s", exc)

        # Versuch 2: OpenAI GPT-4o-mini
        if self.openai_key:
            try:
                payload = {
                    "model": "gpt-4o-mini",
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                }
                async with self.session.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        if text:
                            return text
            except Exception as exc:
                log.warning("GPT-4o-mini fehlgeschlagen: %s", exc)

        # Kein Fallback auf Demo-Text
        log.warning("SEO-Textgenerierung komplett fehlgeschlagen fuer '%s' — Original behalten", title)
        return ""

    # ------------------------------------------------------------------
    # Preis-Optimierung
    # ------------------------------------------------------------------
    def _optimize_price(self, source_price: float, niche: str) -> float:
        niche_lower = niche.lower()
        margin = MARGIN_MAP.get(niche_lower, DEFAULT_MARGIN)
        for key, val in MARGIN_MAP.items():
            if key in niche_lower:
                margin = val
                break
        return round(source_price * margin, 2)

    # ------------------------------------------------------------------
    # Produkt in Client-Shop hochladen
    # ------------------------------------------------------------------
    async def upload_to_client_shop(
        self,
        client_id: int,
        client_domain: str,
        client_token: str,
        niche: str,
        product: dict,
    ) -> bool:
        title = product.get("title", "").strip()
        if not title:
            log.warning("Leerer Titel — skip")
            return False

        seo_text = await self.generate_seo_text(title, niche)
        body_html = f"<p>{seo_text}</p>" if seo_text else product.get("body_html", "")

        # Preis aus erster Variante
        variants = product.get("variants", [])
        source_price = float(variants[0].get("price", "0")) if variants else 0.0
        optimized_price = self._optimize_price(source_price, niche) if source_price else source_price

        # Varianten mit neuem Preis
        new_variants = []
        for v in variants:
            new_v = {
                "option1": v.get("option1", "Default Title"),
                "price": str(optimized_price),
                "inventory_management": v.get("inventory_management"),
                "inventory_quantity": v.get("inventory_quantity", 10),
            }
            new_variants.append(new_v)

        images = [{"src": img["src"]} for img in product.get("images", []) if img.get("src")]

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": product.get("vendor", ""),
                "product_type": product.get("product_type", ""),
                "tags": product.get("tags", ""),
                "status": "active",
                "variants": new_variants or [{"price": str(optimized_price)}],
                "images": images,
            }
        }

        url = f"https://{client_domain}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        headers = {"X-Shopify-Access-Token": client_token, "Content-Type": "application/json"}
        try:
            async with self.session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status not in (200, 201):
                    log.warning("Upload zu %s HTTP %s", client_domain, resp.status)
                    return False
                data = await resp.json()
                client_product_id = str(data.get("product", {}).get("id", ""))
                self.db.execute(
                    "INSERT INTO processed_products (client_id, source_title, client_product_id) VALUES (?,?,?)",
                    (client_id, title, client_product_id),
                )
                self.db.commit()
                log.info("Produkt '%s' hochgeladen zu %s (ID %s)", title, client_domain, client_product_id)
                return True
        except Exception as exc:
            log.error("Upload-Fehler %s: %s", client_domain, exc)
            return False

    # ------------------------------------------------------------------
    # Monatsbericht generieren (Dark-Theme HTML)
    # ------------------------------------------------------------------
    def generate_monthly_report(self, client: sqlite3.Row, month: str, products_uploaded: int) -> str:
        package_price = PACKAGES.get(client["package"], {}).get("price_eur", 0)
        prognose = products_uploaded * 35  # grobe Umsatz-Prognose

        report_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Ghost Vendor Report {month}</title>
<style>
  body {{ background:#0d0d0d; color:#e0e0e0; font-family:sans-serif; padding:2rem; }}
  h1 {{ color:#f0a500; }} h2 {{ color:#ccc; }}
  table {{ border-collapse:collapse; width:100%; }}
  th,td {{ padding:.6rem 1rem; border:1px solid #333; text-align:left; }}
  th {{ background:#1a1a1a; color:#f0a500; }}
  .kpi {{ display:flex; gap:2rem; margin:1.5rem 0; }}
  .kpi-box {{ background:#1a1a1a; border-radius:8px; padding:1rem 1.5rem; min-width:140px; }}
  .kpi-box span {{ font-size:1.8rem; font-weight:bold; color:#f0a500; }}
</style>
</head>
<body>
<h1>Ghost Vendor Network — Monatsbericht {month}</h1>
<p>Shop: <strong>{client['shop_domain']}</strong> | Paket: <strong>{client['package'].upper()}</strong></p>
<div class="kpi">
  <div class="kpi-box"><small>Produkte hochgeladen</small><br><span>{products_uploaded}</span></div>
  <div class="kpi-box"><small>Monatsgebuehr</small><br><span>EUR {package_price}</span></div>
  <div class="kpi-box"><small>Umsatz-Prognose</small><br><span>EUR {prognose}</span></div>
</div>
<h2>Zusammenfassung</h2>
<table>
  <tr><th>Kennzahl</th><th>Wert</th></tr>
  <tr><td>Nische</td><td>{client['niche']}</td></tr>
  <tr><td>Produkte/Tag (Limit)</td><td>{PACKAGES.get(client['package'], {}).get('products_per_day', '-')}</td></tr>
  <tr><td>Hochgeladen im Monat</td><td>{products_uploaded}</td></tr>
  <tr><td>Prognose-Umsatz</td><td>EUR {prognose}</td></tr>
</table>
<p style="margin-top:2rem;color:#666;font-size:.8rem;">Generiert am {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — Ghost Vendor Network</p>
</body></html>"""
        self.db.execute(
            "INSERT OR REPLACE INTO monthly_reports (client_id, month, products_uploaded, report_html) VALUES (?,?,?,?)",
            (client["id"], month, products_uploaded, report_html),
        )
        self.db.commit()
        return report_html

    # ------------------------------------------------------------------
    # Stripe Billing pruefen
    # ------------------------------------------------------------------
    async def bill_clients(self) -> None:
        if not self.stripe_key:
            log.warning("Stripe-Key fehlen — Billing uebersprungen")
            return

        clients = self.db.execute(
            "SELECT * FROM clients WHERE active=1 AND stripe_subscription_id IS NOT NULL"
        ).fetchall()

        for client in clients:
            sub_id = client["stripe_subscription_id"]
            try:
                async with self.session.get(
                    f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                    headers={"Authorization": f"Bearer {self.stripe_key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    status = data.get("status", "")
                    if status in ("past_due", "incomplete"):
                        # Invoice erstellen
                        async with self.session.post(
                            "https://api.stripe.com/v1/invoices",
                            data={"customer": data.get("customer", ""), "auto_advance": "true"},
                            headers={"Authorization": f"Bearer {self.stripe_key}"},
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as inv_resp:
                            if inv_resp.status in (200, 201):
                                inv_data = await inv_resp.json()
                                log.info("Invoice erstellt fuer %s: %s", client["shop_domain"], inv_data.get("id"))
            except Exception as exc:
                log.warning("Stripe-Check fehlgeschlagen fuer %s: %s", client["shop_domain"], exc)

    # ------------------------------------------------------------------
    # Telegram-Report
    # ------------------------------------------------------------------
    async def telegram_report(self, summary: list) -> None:
        if not self.telegram_token or not self.telegram_chat_id:
            return
        lines = ["*Ghost Vendor Network — Taeglicherberichtt*\n"]
        total_uploads = 0
        for item in summary:
            lines.append(f"* {item['domain']} ({item['package']}): {item['uploaded']} Produkte hochgeladen")
            total_uploads += item["uploaded"]
        lines.append(f"\n*Gesamt heute:* {total_uploads} Produkte")
        text = "\n".join(lines)
        try:
            async with self.session.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning("Telegram-Report HTTP %s", resp.status)
        except Exception as exc:
            log.warning("Telegram-Report fehlgeschlagen: %s", exc)

    # ------------------------------------------------------------------
    # Taeglich alle aktiven Clients verarbeiten
    # ------------------------------------------------------------------
    async def daily_run(self) -> None:
        clients = self.db.execute("SELECT * FROM clients WHERE active=1").fetchall()
        log.info("Ghost Vendor Daily Run: %d aktive Clients", len(clients))

        today = datetime.now(timezone.utc)
        is_first_of_month = today.day == 1
        month_str = today.strftime("%Y-%m")

        summary = []
        for client in clients:
            pkg = PACKAGES.get(client["package"], PACKAGES["basic"])
            daily_limit = pkg["products_per_day"]
            niche = client["niche"] or ""

            products = await self.find_products_for_client(client["id"], niche, limit=250)
            candidates = products[:daily_limit]

            uploaded = 0
            for product in candidates:
                success = await self.upload_to_client_shop(
                    client["id"],
                    client["shop_domain"],
                    client["api_token"],
                    niche,
                    product,
                )
                if success:
                    uploaded += 1

            summary.append({
                "domain": client["shop_domain"],
                "package": client["package"],
                "uploaded": uploaded,
            })

            if is_first_of_month:
                # Uploads des letzten Monats zaehlen
                prev_month = (today.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%Y-%m")
                row = self.db.execute(
                    "SELECT COUNT(*) as cnt FROM processed_products WHERE client_id=? AND strftime('%Y-%m', processed_at)=?",
                    (client["id"], prev_month),
                ).fetchone()
                cnt = row["cnt"] if row else 0
                self.generate_monthly_report(client, prev_month, cnt)
                log.info("Monatsbericht generiert fuer %s (%s): %d Produkte", client["shop_domain"], prev_month, cnt)

        await self.bill_clients()
        await self.telegram_report(summary)
        log.info("Daily Run abgeschlossen.")

    # ------------------------------------------------------------------
    # CLI-Hilfsmethoden
    # ------------------------------------------------------------------
    def add_client(self, domain: str, token: str, email: str, package: str, niche: str) -> None:
        if package not in PACKAGES:
            raise ValueError(f"Unbekanntes Paket '{package}'. Erlaubt: {list(PACKAGES.keys())}")
        self.db.execute(
            "INSERT OR REPLACE INTO clients (shop_domain, api_token, email, package, niche) VALUES (?,?,?,?,?)",
            (domain, token, email, package, niche),
        )
        self.db.commit()
        log.info("Client hinzugefuegt: %s (%s, %s)", domain, package, niche)

    def list_clients(self) -> list:
        rows = self.db.execute("SELECT * FROM clients ORDER BY id").fetchall()
        result = []
        for r in rows:
            mrr = PACKAGES.get(r["package"], {}).get("price_eur", 0)
            result.append({
                "id": r["id"],
                "domain": r["shop_domain"],
                "email": r["email"],
                "package": r["package"],
                "niche": r["niche"],
                "active": bool(r["active"]),
                "mrr_eur": mrr,
            })
        return result


# ---------------------------------------------------------------------------
# Schedule-Daemon (06:00 UTC taeglich)
# ---------------------------------------------------------------------------

async def _wait_until_next_run() -> None:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now >= target:
        # Naechsten Tag
        target = target.replace(day=target.day + 1)
    wait_seconds = (target - now).total_seconds()
    log.info("Naechster Run um %s UTC (in %.0fs)", target.strftime("%Y-%m-%d %H:%M"), wait_seconds)
    await asyncio.sleep(wait_seconds)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Ghost Vendor Network")
    parser.add_argument("--add", nargs=5, metavar=("DOMAIN", "TOKEN", "EMAIL", "PACKAGE", "NICHE"),
                        help="Neuen Client hinzufuegen")
    parser.add_argument("--list", action="store_true", help="Alle Clients anzeigen")
    parser.add_argument("--now", action="store_true", help="Sofort alle Clients verarbeiten")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        gvn = GhostVendorNetwork(session)

        if args.add:
            domain, token, email, package, niche = args.add
            gvn.add_client(domain, token, email, package, niche)
            return

        if args.list:
            clients = gvn.list_clients()
            total_mrr = sum(c["mrr_eur"] for c in clients)
            print(f"\n{'ID':>3}  {'Domain':<35} {'Paket':<8} {'Nische':<20} {'MRR':>8}  Aktiv")
            print("-" * 85)
            for c in clients:
                status = "JA" if c["active"] else "nein"
                print(f"{c['id']:>3}  {c['domain']:<35} {c['package']:<8} {c['niche']:<20} {c['mrr_eur']:>6} EUR  {status}")
            print(f"\nGesamt MRR: EUR {total_mrr}\n")
            return

        if args.now:
            await gvn.daily_run()
            return

        # Daemon-Modus: jeden Tag um 06:00 UTC
        log.info("Ghost Vendor Network Daemon gestartet.")
        while True:
            await _wait_until_next_run()
            try:
                await gvn.daily_run()
            except Exception as exc:
                log.error("Daily-Run-Fehler (Auto-Restart): %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
