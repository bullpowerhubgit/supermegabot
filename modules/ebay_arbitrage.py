#!/usr/bin/env python3
"""
eBay-Arbitrage-Autopilot — Welteinzigartiger geschlossener Margin-Loop.

Logik:
  AliExpress Einkaufspreis  → eBay Marktpreis-Scan  → Marge ≥ 35%?
  → Auto-Import Shopify     → Preis = eBay×0.75     → Telegram-Alert

Vorteil gegenüber eBay:
  Keine eBay-Gebühren (15%), volle Kundenkontrolle, "Billiger als eBay" als
  Conversion-Trigger auf ineedit.com.co.

Sofort-Geld: eBay-Marktpreise beweisen Nachfrage. Shopify-Listing live in Minuten.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("EbayArbitrage")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "ebay_arbitrage.db"

SHOPIFY_DOMAIN  = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
SHOPIFY_TOKEN   = lambda: os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = lambda: os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOPIFY_STORE   = lambda: os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")
TELEGRAM_TOKEN  = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = lambda: os.getenv("TELEGRAM_CHAT_ID", "")

# eBay Browse API credentials
EBAY_APP_ID   = lambda: os.getenv("EBAY_APP_ID", os.getenv("EBAY_CLIENT_ID", "IRV7wFsqtKC76676391G2237LhVpgNCRZ1"))
EBAY_CERT_ID  = lambda: os.getenv("EBAY_CERT_ID", os.getenv("EBAY_CLIENT_SECRET", ""))

# AliExpress Affiliate API
ALI_APP_KEY    = lambda: os.getenv("ALIEXPRESS_APP_KEY", os.getenv("ALI_APP_KEY", ""))
ALI_APP_SECRET = lambda: os.getenv("ALIEXPRESS_APP_SECRET", os.getenv("ALI_APP_SECRET", ""))
ALI_API_URL    = "https://api.taobao.com/router/rest"

# Arbitrage thresholds
MIN_MARGIN_PCT  = 35    # minimum net margin %
MIN_ABS_PROFIT  = 8.0   # minimum absolute profit in EUR
MAX_BUY_PRICE   = 120.0 # max AliExpress buy price (avoid high-risk items)
EBAY_FEE_PCT    = 0.13  # ~13% eBay total fees (selling + PayPal)
SHOPIFY_MARKUP  = 0.75  # set Shopify price at 75% of eBay price ("25% günstiger als eBay")

# Categories to scan: (display_name, [search_keywords])
SCAN_CATEGORIES: list[tuple[str, list[str]]] = [
    ("Smart Home",     ["smart steckdose wlan", "smart home hub", "zigbee gateway", "tuya smart"]),
    ("Powerstation",   ["tragbare powerstation 500w", "solar powerbank", "lifepo4 akku"]),
    ("Audio",          ["bluetooth lautsprecher outdoor", "tws kopfhörer aktiv", "mini soundbar"]),
    ("Gadgets",        ["led strip gaming", "handy gimbal stabilizer", "mini projektor"]),
    ("Saugroboter",    ["saugroboter wifi app", "wischroboter 2in1"]),
    ("Kamera",         ["dashcam 4k wifi", "überwachungskamera solar outdoor"]),
    ("Solar",          ["solar laderegler mppt", "faltbares solarpanel 100w"]),
    ("Wearables",      ["smartwatch blutdruck sport", "fitnesstracker mit gps"]),
    ("Auto",           ["kfz ladegerät schnellladung", "auto dash cam rückfahrkamera"]),
    ("HomeOffice",     ["ergonomischer bürostuhl netz", "dual monitor halterung"]),
]


# ─────────────────────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    Path(_DB).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS arb_opportunities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            INTEGER,
                category      TEXT,
                keyword       TEXT,
                title         TEXT,
                ali_price     REAL,
                ebay_price    REAL,
                margin_pct    REAL,
                abs_profit    REAL,
                shopify_price REAL,
                shopify_id    TEXT,
                imported      INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS arb_scans (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        INTEGER,
                found     INTEGER,
                imported  INTEGER,
                top_margin REAL
            );
            CREATE INDEX IF NOT EXISTS arb_ts ON arb_opportunities(ts);
        """)


# ─────────────────────────────────────────────────────────────────────────────
# eBay Browse API — get current market prices
# ─────────────────────────────────────────────────────────────────────────────

async def _ebay_token() -> str:
    import aiohttp, base64
    app_id = EBAY_APP_ID()
    cert   = EBAY_CERT_ID()
    if not app_id or not cert:
        return ""
    try:
        creds = base64.b64encode(f"{app_id}:{cert}".encode()).decode()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                "https://api.ebay.com/identity/v1/oauth2/token",
                headers={"Authorization": f"Basic {creds}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json(content_type=None)
        return d.get("access_token", "")
    except Exception as e:
        log.debug("eBay token error: %s", e)
        return ""


async def get_ebay_market_prices(keywords: str, limit: int = 10) -> list[float]:
    """Return list of active eBay DE listing prices for given keywords."""
    import aiohttp
    token = await _ebay_token()
    if not token:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE"},
                params={"q": keywords, "limit": min(limit, 50),
                        "filter": "buyingOptions:{FIXED_PRICE}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)
        prices = []
        for item in data.get("itemSummaries", []):
            p = item.get("price", {})
            try:
                prices.append(float(p.get("value", 0)))
            except Exception as e:
                log.warning("Ignored error: %s", e)
        return prices
    except Exception as e:
        log.debug("eBay search error for '%s': %s", keywords, e)
        return []


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ─────────────────────────────────────────────────────────────────────────────
# AliExpress Affiliate API — get buy prices
# ─────────────────────────────────────────────────────────────────────────────

def _ali_sign(params: dict, secret: str) -> str:
    import hashlib
    keys = sorted(params.keys())
    raw  = secret + "".join(f"{k}{params[k]}" for k in keys) + secret
    return hashlib.md5(raw.encode()).hexdigest().upper()


async def get_ali_products(keyword: str, count: int = 8) -> list[dict]:
    """Search AliExpress Affiliate API for products with prices."""
    import aiohttp

    app_key = ALI_APP_KEY()
    secret  = ALI_APP_SECRET()

    if not app_key or not secret:
        # No credentials — use fallback estimation
        return []

    params = {
        "method":        "aliexpress.affiliate.product.query",
        "app_key":       app_key,
        "timestamp":     str(int(time.time() * 1000)),
        "sign_method":   "md5",
        "format":        "json",
        "v":             "2.0",
        "keywords":      keyword,
        "page_size":     str(count),
        "page_no":       "1",
        "fields":        "product_id,product_title,sale_price,product_main_image_url,product_detail_url",
        "target_currency": "EUR",
        "target_language": "DE",
        "tracking_id":   "supermegabot",
    }
    params["sign"] = _ali_sign(params, secret)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(ALI_API_URL, data=params) as r:
                data = await r.json(content_type=None)
        resp = (data.get("aliexpress_affiliate_product_query_response", {})
                    .get("resp_result", {}))
        if resp.get("resp_code") != 200:
            return []
        items = resp.get("result", {}).get("products", {}).get("product", [])
        return [
            {
                "id":    str(p.get("product_id", "")),
                "title": p.get("product_title", "")[:120],
                "price": float(p.get("sale_price", 0)),
                "url":   p.get("product_detail_url", ""),
                "image": p.get("product_main_image_url", ""),
            }
            for p in items if float(p.get("sale_price", 0)) > 0
        ]
    except Exception as e:
        log.debug("AliExpress API error for '%s': %s", keyword, e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Margin calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_margin(ali_price: float, ebay_median_price: float) -> dict:
    """
    Returns margin analysis.
    Net profit = eBay_price × (1 - FEE) - ali_price
    Margin % = net_profit / ebay_price × 100
    """
    if ebay_median_price <= 0 or ali_price <= 0:
        return {"viable": False}

    net_revenue  = ebay_median_price * (1 - EBAY_FEE_PCT)
    abs_profit   = net_revenue - ali_price
    margin_pct   = (abs_profit / ebay_median_price) * 100
    shopify_price = round(ebay_median_price * SHOPIFY_MARKUP, 2)  # 25% below eBay
    shopify_profit = shopify_price - ali_price

    return {
        "viable":          margin_pct >= MIN_MARGIN_PCT and abs_profit >= MIN_ABS_PROFIT,
        "ali_price":       ali_price,
        "ebay_price":      ebay_median_price,
        "abs_profit_ebay": round(abs_profit, 2),
        "margin_pct":      round(margin_pct, 1),
        "shopify_price":   shopify_price,
        "shopify_profit":  round(shopify_profit, 2),
        "savings_vs_ebay": round((1 - SHOPIFY_MARKUP) * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Shopify import with eBay-beating price
# ─────────────────────────────────────────────────────────────────────────────

async def import_to_shopify(product: dict, margin: dict) -> str | None:
    """Create Shopify product priced below eBay, with 'günstiger als eBay' copy."""
    import aiohttp
    from modules.ai_client import ai_complete

    domain  = SHOPIFY_DOMAIN()
    token   = SHOPIFY_TOKEN()
    version = SHOPIFY_VERSION()
    if not domain or not token:
        return None

    savings = margin.get("savings_vs_ebay", 25)
    ali_p   = margin.get("ali_price", 0)
    ebay_p  = margin.get("ebay_price", 0)
    shop_p  = margin.get("shopify_price", 0)

    # AI-generated product description with eBay comparison angle
    desc_prompt = f"""Schreibe eine professionelle Produktbeschreibung für:
Produkt: {product['title']}
Preis: €{shop_p:.2f} (eBay-Marktpreis: €{ebay_p:.2f})

Die Beschreibung soll:
1. Attraktive Produktvorteile in 3-4 Stichpunkten nennen
2. Hervorheben: "{savings}% günstiger als eBay-Preis!"
3. Vertrauen aufbauen: schnelle Lieferung, 30 Tage Rückgabe
4. 150-200 Wörter, auf Deutsch
5. HTML-Format mit <ul><li> für die Stichpunkte

Nur den HTML-Text, keine weiteren Erklärungen."""

    description = await ai_complete(desc_prompt, model_hint="fast", max_tokens=400)
    if not description:
        description = (f"<p>{product['title']}</p>"
                      f"<ul><li>✅ {savings}% günstiger als eBay</li>"
                      f"<li>✅ Schnelle Lieferung 3-8 Werktage</li>"
                      f"<li>✅ 30 Tage Rückgabe</li></ul>")

    payload = {
        "product": {
            "title":        product["title"],
            "body_html":    description,
            "product_type": product.get("category", "Elektronik"),
            "vendor":       "I Want That! I Need It!",
            "status":       "active",
            "tags":         [
                "arbitrage", "ebay-preisvorteil",
                f"ebay-preis-{int(ebay_p)}eur",
                product.get("category", "gadget").lower().replace(" ", "-"),
            ],
            "variants": [{
                "price":            f"{shop_p:.2f}",
                "compare_at_price": f"{ebay_p:.2f}",
                "inventory_management": None,
                "requires_shipping": True,
            }],
            "images": [{"src": product["image"]}] if product.get("image") else [],
        }
    }

    url = f"https://{domain}/admin/api/{version}/products.json"
    hdrs = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(headers=hdrs, timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, json=payload) as r:
                if r.status in (200, 201):
                    data = await r.json(content_type=None)
                    pid = str(data.get("product", {}).get("id", ""))
                    log.info("Imported to Shopify: %s (€%.2f vs eBay €%.2f)", product["title"][:60], shop_p, ebay_p)
                    return pid
                else:
                    body = await r.text()
                    log.warning("Shopify import failed %s: %s", r.status, body[:200])
                    return None
    except Exception as e:
        log.warning("Shopify import error: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Core scan logic
# ─────────────────────────────────────────────────────────────────────────────

async def scan_category(category_name: str, keywords: list[str]) -> list[dict]:
    """Scan one category: find AliExpress products, check eBay market price, calculate margin."""
    opportunities = []

    for keyword in keywords[:2]:  # max 2 keywords per category to avoid rate limits
        ali_products = await get_ali_products(keyword, count=6)

        if not ali_products:
            log.debug("[Arb] No AliExpress results for '%s'", keyword)
            await asyncio.sleep(1)
            continue

        # Get eBay market price for this keyword (German market)
        ebay_prices = await get_ebay_market_prices(keyword, limit=15)
        ebay_median = _median(ebay_prices)

        if ebay_median < 5:
            log.debug("[Arb] eBay price too low for '%s': €%.2f", keyword, ebay_median)
            await asyncio.sleep(1)
            continue

        for product in ali_products:
            ali_price = product["price"]
            if ali_price <= 0 or ali_price > MAX_BUY_PRICE:
                continue

            margin = calculate_margin(ali_price, ebay_median)
            if not margin["viable"]:
                continue

            opp = {
                **product,
                "category": category_name,
                "keyword":  keyword,
                **margin,
            }
            opportunities.append(opp)
            log.info("[Arb] 💰 OPPORTUNITY: %s | ali=€%.2f ebay=€%.2f margin=%.0f%% shop=€%.2f",
                     product["title"][:50], ali_price, ebay_median,
                     margin["margin_pct"], margin["shopify_price"])

        await asyncio.sleep(2)  # rate limiting

    return opportunities


async def run_full_scan(max_imports: int = 5) -> dict:
    """
    Scan all categories for arbitrage opportunities, import top N to Shopify.
    Returns summary dict.
    """
    log.info("[Arb] Starting full arbitrage scan (%d categories)", len(SCAN_CATEGORIES))
    all_opportunities: list[dict] = []

    for cat_name, keywords in SCAN_CATEGORIES:
        try:
            opps = await scan_category(cat_name, keywords)
            all_opportunities.extend(opps)
            log.info("[Arb] Category '%s': %d opportunities", cat_name, len(opps))
        except Exception as e:
            log.warning("[Arb] Category scan error '%s': %s", cat_name, e)
        await asyncio.sleep(3)

    # Sort by margin %
    all_opportunities.sort(key=lambda o: o.get("margin_pct", 0), reverse=True)

    # Log to DB (before import)
    with _db() as con:
        for opp in all_opportunities:
            con.execute("""
                INSERT INTO arb_opportunities(ts, category, keyword, title, ali_price,
                    ebay_price, margin_pct, abs_profit, shopify_price)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (int(time.time()), opp["category"], opp["keyword"], opp["title"],
                  opp["ali_price"], opp["ebay_price"], opp["margin_pct"],
                  opp["abs_profit_ebay"], opp["shopify_price"]))

    # Import top N to Shopify
    imported = []
    seen_titles: set[str] = set()
    for opp in all_opportunities:
        if len(imported) >= max_imports:
            break
        title_key = opp["title"][:40].lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        shopify_id = await import_to_shopify(opp, opp)
        if shopify_id:
            imported.append({**opp, "shopify_id": shopify_id})
            with _db() as con:
                con.execute("UPDATE arb_opportunities SET imported=1, shopify_id=? WHERE title=? AND imported=0",
                            (shopify_id, opp["title"]))
        await asyncio.sleep(2)

    # Log scan summary
    top_margin = all_opportunities[0].get("margin_pct", 0) if all_opportunities else 0
    with _db() as con:
        con.execute("INSERT INTO arb_scans(ts, found, imported, top_margin) VALUES(?,?,?,?)",
                    (int(time.time()), len(all_opportunities), len(imported), top_margin))

    summary = {
        "total_found": len(all_opportunities),
        "imported": len(imported),
        "top_margin_pct": round(top_margin, 1),
        "top_opportunities": all_opportunities[:5],
        "imported_products": imported,
    }

    await _send_telegram_report(summary)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Telegram report
# ─────────────────────────────────────────────────────────────────────────────

async def _send_telegram_report(summary: dict) -> None:
    import aiohttp

    token   = TELEGRAM_TOKEN()
    chat_id = TELEGRAM_CHAT()
    if not token or not chat_id:
        return

    found    = summary["total_found"]
    imported = summary["imported"]
    top      = summary.get("top_opportunities", [])

    lines = [f"🎯 <b>eBay-Arbitrage-Scan</b>"]
    lines.append(f"Gefunden: {found} Chancen | Importiert: {imported} Produkte")

    if top:
        lines.append("\n<b>Top Chancen:</b>")
        for opp in top[:3]:
            lines.append(
                f"• {opp['title'][:45]}…\n"
                f"  Ali=€{opp['ali_price']:.2f} | eBay=€{opp['ebay_price']:.2f} | "
                f"Shop=€{opp['shopify_price']:.2f} | Marge={opp['margin_pct']:.0f}%"
            )

    if summary.get("imported_products"):
        store = SHOPIFY_STORE().rstrip("/")
        lines.append(f"\n✅ Live auf {store}")

    text = "\n".join(lines)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
            )
    except Exception as e:
        log.debug("Telegram report error: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    try:
        with _db() as con:
            total_opps  = con.execute("SELECT COUNT(*) FROM arb_opportunities").fetchone()[0]
            total_imp   = con.execute("SELECT COUNT(*) FROM arb_opportunities WHERE imported=1").fetchone()[0]
            total_scans = con.execute("SELECT COUNT(*) FROM arb_scans").fetchone()[0]
            best_margin = con.execute("SELECT MAX(margin_pct) FROM arb_opportunities").fetchone()[0] or 0
            avg_margin  = con.execute("SELECT AVG(margin_pct) FROM arb_opportunities WHERE imported=1").fetchone()[0] or 0
            recent_imp  = con.execute(
                "SELECT ts, title, ali_price, ebay_price, shopify_price, margin_pct, category "
                "FROM arb_opportunities WHERE imported=1 ORDER BY ts DESC LIMIT 10"
            ).fetchall()
        return {
            "total_opportunities": total_opps,
            "total_imported":      total_imp,
            "total_scans":         total_scans,
            "best_margin_pct":     round(best_margin, 1),
            "avg_imported_margin": round(avg_margin, 1),
            "recent_imports":      [dict(r) for r in recent_imp],
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Called from automation_scheduler
# ─────────────────────────────────────────────────────────────────────────────

async def scheduled_arbitrage_scan() -> str:
    try:
        result = await run_full_scan(max_imports=5)
        return (
            f"ArbitrageScan: {result['total_found']} chancen, "
            f"{result['imported']} importiert, "
            f"top-marge={result['top_margin_pct']}%"
        )
    except Exception as e:
        return f"ArbitrageScan Fehler: {e}"


# Init DB on import
try:
    init_db()
except Exception as e:
    log.warning("EbayArbitrage DB init failed: %s", e)
