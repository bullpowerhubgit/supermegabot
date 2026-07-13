"""
Trend Velocity Pipeline — erkennt virale Keywords (Reddit + Google Trends),
bewertet sie per Viral-Score, sucht AliExpress-Lieferanten, erstellt
Shopify-Listings und Meta-Ads, und prueft nach 72h die Performance.

CLI:
    python3 modules/trend_velocity_pipeline.py --now    # Sofort-Scan
    python3 modules/trend_velocity_pipeline.py --check  # 72h-Auswertung
    python3 modules/trend_velocity_pipeline.py          # Schedule alle 2h
"""

import argparse
import asyncio
import logging
import os
import re
import sqlite3
import time
from collections import defaultdict

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("trend_velocity_pipeline")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trend_velocity.db")

VIRAL_THRESHOLD = 5.0
SCHEDULE_INTERVAL = 7200  # 2h in Sekunden


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            viral_score REAL,
            shopify_product_id TEXT,
            shopify_product_url TEXT,
            meta_ad_id TEXT,
            status TEXT DEFAULT 'draft',
            supplier_url TEXT,
            supplier_price_eur REAL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            source TEXT,
            mentions INTEGER DEFAULT 0,
            velocity REAL DEFAULT 0,
            upvotes INTEGER DEFAULT 0,
            subreddit TEXT,
            scanned_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Verlaufs-Puffer fuer Acceleration
# ---------------------------------------------------------------------------
_velocity_history: dict = defaultdict(list)


# ---------------------------------------------------------------------------
# Haupt-Klasse
# ---------------------------------------------------------------------------

class TrendVelocityPipeline:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
        self.shopify_token = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
        self.shopify_api_version = os.getenv("SHOPIFY_API_VERSION", "2026-04")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.meta_access_token = os.getenv("META_ACCESS_TOKEN", "")
        self.meta_ad_account_id = os.getenv("META_AD_ACCOUNT_ID", "")
        self.db = _get_db()

    # ------------------------------------------------------------------
    # Reddit-Trends via PullPush.io (kein Auth noetig)
    # ------------------------------------------------------------------
    async def scan_reddit_trends(self) -> list:
        results: list = []
        now = int(time.time())
        two_hours_ago = now - 7200
        url = (
            "https://api.pullpush.io/reddit/search/submission/"
            f"?after={two_hours_ago}&before={now}&size=100&sort=score"
        )
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    log.warning("PullPush HTTP %s", resp.status)
                    return results
                data = await resp.json()
                posts = data.get("data", [])
        except Exception as exc:
            log.warning("Reddit scan fehlgeschlagen: %s", exc)
            return results

        keyword_map: dict = {}
        for post in posts:
            title = post.get("title", "")
            words = re.findall(r"[A-Za-z]{4,}", title)
            for w in words:
                kw = w.lower()
                if kw not in keyword_map:
                    keyword_map[kw] = {
                        "keyword": kw,
                        "mentions": 0,
                        "upvotes": 0,
                        "subreddit": post.get("subreddit", ""),
                        "source": "reddit",
                    }
                keyword_map[kw]["mentions"] += 1
                keyword_map[kw]["upvotes"] += int(post.get("score", 0))

        for kw, entry in keyword_map.items():
            entry["velocity"] = entry["mentions"] / 2.0  # mentions per hour
            results.append(entry)
            self.db.execute(
                "INSERT INTO trend_scans (keyword, source, mentions, velocity, upvotes, subreddit) VALUES (?,?,?,?,?,?)",
                (kw, "reddit", entry["mentions"], entry["velocity"], entry["upvotes"], entry["subreddit"]),
            )
        self.db.commit()
        log.info("Reddit: %d Keywords gescannt", len(results))
        return results

    # ------------------------------------------------------------------
    # Google Trends via RSS (DE + US)
    # ------------------------------------------------------------------
    async def scan_google_trends(self) -> list:
        results: list = []
        feeds = [
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=DE",
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
        ]
        for feed_url in feeds:
            try:
                async with self.session.get(feed_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
            except Exception as exc:
                log.warning("Google Trends RSS fehlgeschlagen (%s): %s", feed_url, exc)
                continue

            titles = re.findall(r"<title><!\[CDATA\[(.+?)]]></title>", text)
            traffic_vals = re.findall(r"<ht:approx_traffic>([^<]+)</ht:approx_traffic>", text)
            for i, title in enumerate(titles[1:], 0):  # erstes <title> = Feed-Titel
                traffic_str = traffic_vals[i] if i < len(traffic_vals) else "0"
                traffic_clean = re.sub(r"[^\d]", "", traffic_str)
                traffic = int(traffic_clean) if traffic_clean else 0
                words = re.findall(r"[A-Za-z]{4,}", title)
                for w in words:
                    kw = w.lower()
                    results.append({
                        "keyword": kw,
                        "mentions": 1,
                        "velocity": traffic / 1000.0,
                        "upvotes": 0,
                        "subreddit": "",
                        "source": "google_trends",
                    })
                    self.db.execute(
                        "INSERT INTO trend_scans (keyword, source, mentions, velocity, upvotes) VALUES (?,?,?,?,?)",
                        (kw, "google_trends", 1, traffic / 1000.0, 0),
                    )
        self.db.commit()
        log.info("Google Trends: %d Eintraege", len(results))
        return results

    # ------------------------------------------------------------------
    # Viral-Score Berechnung
    # ------------------------------------------------------------------
    def calculate_viral_score(self, keyword: str, scan_data: list) -> float:
        velocity = sum(d["velocity"] for d in scan_data if d["keyword"] == keyword)
        upvotes = sum(d["upvotes"] for d in scan_data if d["keyword"] == keyword)

        history = _velocity_history[keyword]
        history.append(velocity)
        if len(history) > 10:
            history.pop(0)

        acceleration = 0.0
        if len(history) >= 2:
            acceleration = history[-1] - history[-2]

        score = (velocity * 10) + (upvotes / 100) + acceleration
        log.debug("Viral-Score '%s': %.2f (vel=%.2f, up=%d, acc=%.2f)", keyword, score, velocity, upvotes, acceleration)
        return round(score, 2)

    # ------------------------------------------------------------------
    # AliExpress-Lieferant suchen (HTML-Scraping)
    # ------------------------------------------------------------------
    async def find_aliexpress_supplier(self, keyword: str):
        search_url = f"https://www.aliexpress.com/wholesale?SearchText={keyword.replace(' ', '+')}&SortType=total_tranqua_desc"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        }
        try:
            async with self.session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    log.warning("AliExpress HTTP %s fuer '%s'", resp.status, keyword)
                    return None
                html = await resp.text()
        except Exception as exc:
            log.warning("AliExpress-Scraping fehlgeschlagen '%s': %s", keyword, exc)
            return None

        link_match = re.search(r'href="(https://www\.aliexpress\.com/item/[^"]+)"', html)
        if not link_match:
            return None
        product_link = link_match.group(1)

        title_match = re.search(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else keyword

        price_match = re.search(r'\$\s*([\d]+\.[\d]{2})', html)
        price_eur = round(float(price_match.group(1)) * 0.92, 2) if price_match else None

        img_match = re.search(r'"image"\s*:\s*"(https://ae01\.alicdn\.com[^"]+)"', html)
        image_url = img_match.group(1) if img_match else None

        return {
            "product_link": product_link,
            "title": title,
            "price_eur": price_eur,
            "image_url": image_url,
        }

    # ------------------------------------------------------------------
    # Shopify-Listing erstellen (Draft, 3x Markup)
    # ------------------------------------------------------------------
    async def create_shopify_listing(self, keyword: str, supplier: dict, viral_score: float):
        if not self.shopify_domain or not self.shopify_token:
            log.warning("Shopify-Credentials fehlen")
            return None

        title = supplier.get("title", "").strip()
        if not title:
            log.warning("Fake-Produkt-Schutz: leerer Titel fuer '%s' — skip", keyword)
            return None

        cost = supplier.get("price_eur") or 0.0
        price = round(cost * 3, 2) if cost else 29.99

        score_tag = f"viral-score-{int(viral_score)}"
        body_html = (
            f"<p><strong>{title}</strong></p>"
            f"<p>Trending keyword: <em>{keyword}</em> — Viral-Score: {viral_score}</p>"
        )

        images = []
        if supplier.get("image_url"):
            images.append({"src": supplier["image_url"]})

        payload = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": "TrendBot",
                "product_type": "Trending",
                "status": "draft",
                "tags": f"{keyword},{score_tag},trend-auto",
                "variants": [{"price": str(price), "inventory_management": "shopify", "inventory_quantity": 50}],
                "images": images,
            }
        }

        url = f"https://{self.shopify_domain}/admin/api/{self.shopify_api_version}/products.json"
        headers = {"X-Shopify-Access-Token": self.shopify_token, "Content-Type": "application/json"}
        try:
            async with self.session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()
                product = data.get("product", {})
                product_id = product.get("id")
                product_url = f"https://{self.shopify_domain}/products/{product.get('handle', '')}"
                self.db.execute(
                    "INSERT INTO trend_products (keyword, viral_score, shopify_product_id, shopify_product_url, supplier_url, supplier_price_eur, status) VALUES (?,?,?,?,?,?,'draft')",
                    (keyword, viral_score, str(product_id), product_url, supplier.get("product_link", ""), cost),
                )
                self.db.commit()
                log.info("Shopify Draft erstellt: %s (ID %s)", title, product_id)
                return {"product_id": product_id, "product_url": product_url}
        except Exception as exc:
            log.error("Shopify-Listing fehlgeschlagen '%s': %s", keyword, exc)
            return None

    # ------------------------------------------------------------------
    # Meta-Ad erstellen (Graph API v20.0)
    # ------------------------------------------------------------------
    async def create_meta_ad(self, keyword: str, product_url: str, product_id: str):
        if not self.meta_access_token or not self.meta_ad_account_id:
            log.warning("Meta-Credentials fehlen")
            return None

        variants = [
            f"Jetzt viral: {keyword.title()} — sichere dir deins!",
            f"Alle reden ueber {keyword.title()} — schau selbst!",
            f"{keyword.title()} im Trend — limitiert verfuegbar!",
        ]

        creatives_url = f"https://graph.facebook.com/v20.0/act_{self.meta_ad_account_id}/adcreatives"
        ad_ids = []
        for variant in variants:
            payload = {
                "name": f"TrendBot_{keyword}_{int(time.time())}",
                "object_story_spec": {
                    "link_data": {
                        "message": variant,
                        "link": product_url,
                        "call_to_action": {"type": "SHOP_NOW"},
                    }
                },
                "access_token": self.meta_access_token,
            }
            try:
                async with self.session.post(creatives_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    data = await resp.json()
                    if "id" in data:
                        ad_ids.append(data["id"])
            except Exception as exc:
                log.warning("Meta-Creative fehlgeschlagen: %s", exc)

        combined = ",".join(ad_ids)
        if combined:
            self.db.execute(
                "UPDATE trend_products SET meta_ad_id=?, updated_at=datetime('now') WHERE shopify_product_id=?",
                (combined, str(product_id)),
            )
            self.db.commit()
        return combined or None

    # ------------------------------------------------------------------
    # Telegram-Alert
    # ------------------------------------------------------------------
    async def telegram_alert(self, results: list) -> None:
        if not self.telegram_token or not self.telegram_chat_id:
            return
        lines = ["*TrendVelocity Pipeline — Neuer Zyklus abgeschlossen*\n"]
        total_prognose = 0.0
        for r in results:
            score = r.get("viral_score", 0)
            prognose = round(score * 12.50, 2)
            total_prognose += prognose
            lines.append(
                f"* {r.get('keyword', '?')} — Score: {score} — Prognose: EUR{prognose}/Tag\n"
                f"  Shop: {r.get('product_url', '-')}"
            )
        lines.append(f"\n*Gesamt-Prognose:* EUR{round(total_prognose, 2)}/Tag")
        text = "\n".join(lines)
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        try:
            async with self.session.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning("Telegram-Alert HTTP %s", resp.status)
        except Exception as exc:
            log.warning("Telegram-Alert fehlgeschlagen: %s", exc)

    # ------------------------------------------------------------------
    # 72h-Performance-Check
    # ------------------------------------------------------------------
    async def check_performance(self) -> None:
        if not self.shopify_domain or not self.shopify_token:
            log.warning("Shopify-Credentials fehlen fuer Performance-Check")
            return

        headers = {"X-Shopify-Access-Token": self.shopify_token}
        orders_url = (
            f"https://{self.shopify_domain}/admin/api/{self.shopify_api_version}/orders.json"
            "?status=any&limit=250&financial_status=paid"
        )
        try:
            async with self.session.get(orders_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()
                orders = data.get("orders", [])
        except Exception as exc:
            log.error("Shopify-Orders Abruf fehlgeschlagen: %s", exc)
            return

        sales_count: dict = defaultdict(int)
        for order in orders:
            for item in order.get("line_items", []):
                pid = str(item.get("product_id", ""))
                sales_count[pid] += item.get("quantity", 1)

        rows = self.db.execute(
            "SELECT shopify_product_id, keyword FROM trend_products WHERE status='draft'"
        ).fetchall()

        for row in rows:
            pid = row["shopify_product_id"]
            kw = row["keyword"]
            sales = sales_count.get(pid, 0)
            if sales >= 3:
                pub_url = (
                    f"https://{self.shopify_domain}/admin/api/{self.shopify_api_version}/products/{pid}.json"
                )
                try:
                    async with self.session.put(
                        pub_url,
                        json={"product": {"id": pid, "status": "active"}},
                        headers={**headers, "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status == 200:
                            self.db.execute(
                                "UPDATE trend_products SET status='active', updated_at=datetime('now') WHERE shopify_product_id=?",
                                (pid,),
                            )
                            log.info("Produkt publiziert (>= 3 Sales): %s (%s)", kw, pid)
                except Exception as exc:
                    log.warning("Produkt-Publish fehlgeschlagen %s: %s", pid, exc)
            else:
                self.db.execute(
                    "UPDATE trend_products SET status='loser', updated_at=datetime('now') WHERE shopify_product_id=?",
                    (pid,),
                )
                log.info("Produkt als Loser markiert (< 3 Sales): %s (%s) — %d Sales", kw, pid, sales)
        self.db.commit()

    # ------------------------------------------------------------------
    # Haupt-Zyklus
    # ------------------------------------------------------------------
    async def run_cycle(self) -> list:
        log.info("Starte Trend-Velocity-Zyklus ...")
        reddit_data, google_data = await asyncio.gather(
            self.scan_reddit_trends(),
            self.scan_google_trends(),
        )
        all_data = reddit_data + google_data

        all_keywords = {d["keyword"] for d in all_data}
        viral_keywords = []
        for kw in all_keywords:
            score = self.calculate_viral_score(kw, all_data)
            if score >= VIRAL_THRESHOLD:
                viral_keywords.append((kw, score))

        viral_keywords.sort(key=lambda x: x[1], reverse=True)
        log.info("Virale Keywords: %d (Threshold %.1f)", len(viral_keywords), VIRAL_THRESHOLD)

        processed = []
        for kw, score in viral_keywords[:20]:
            supplier = await self.find_aliexpress_supplier(kw)
            if not supplier:
                log.info("Kein Lieferant fuer '%s' — skip", kw)
                continue

            listing = await self.create_shopify_listing(kw, supplier, score)
            if not listing:
                continue

            ad_id = await self.create_meta_ad(kw, listing["product_url"], listing["product_id"])
            processed.append({
                "keyword": kw,
                "viral_score": score,
                "product_url": listing["product_url"],
                "product_id": listing["product_id"],
                "meta_ad_id": ad_id,
            })

        if processed:
            await self.telegram_alert(processed)

        log.info("Zyklus abgeschlossen: %d Produkte verarbeitet", len(processed))
        return processed


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Trend Velocity Pipeline")
    parser.add_argument("--now", action="store_true", help="Sofort einen Scan-Zyklus ausfuehren")
    parser.add_argument("--check", action="store_true", help="72h-Performance-Check ausfuehren")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        pipeline = TrendVelocityPipeline(session)

        if args.check:
            await pipeline.check_performance()
            return

        if args.now:
            await pipeline.run_cycle()
            return

        log.info("Starte Schedule-Modus (alle %ds)", SCHEDULE_INTERVAL)
        while True:
            try:
                await pipeline.run_cycle()
            except Exception as exc:
                log.error("Zyklus-Fehler (Auto-Restart): %s", exc)
            log.info("Naechster Zyklus in %ds ...", SCHEDULE_INTERVAL)
            await asyncio.sleep(SCHEDULE_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
