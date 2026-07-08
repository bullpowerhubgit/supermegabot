#!/usr/bin/env python3
"""
Demand Oracle — Welteinzigartige Nachfrage-vor-Angebot Maschine.

Das E-Commerce-Modell der Welt ist falsch herum:
  Erst produzieren → dann hoffen → $1,77 Billion totes Inventar/Jahr

Demand Oracle dreht das um:
  Reddit/Amazon/Foren → latente Wünsche → KI clustert → Pre-Order live →
  erst kaufen wenn Minimum erreicht → Zero Lagerrisiko → 100% Sell-Through

Pinduoduo machte $2,7 Billionen GMV damit in China.
Für Alltagsprodukte unter €200 im Westen: noch nicht gebaut. Bis jetzt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("DemandOracle")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "demand_oracle.db"

# ── Credentials ───────────────────────────────────────────────────────────────
REDDIT_CLIENT_ID     = lambda: os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = lambda: os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = "DemandOracle/1.0 by SuperMegaBot"

SHOPIFY_DOMAIN  = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOPIFY_TOKEN   = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-01")
SHOPIFY_STORE   = lambda: os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")
TELEGRAM_TOKEN  = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = lambda: os.getenv("TELEGRAM_CHAT_ID", "")

# ── Scan targets ──────────────────────────────────────────────────────────────
# German & relevant English subreddits for latent product desire
SCAN_SUBREDDITS = [
    "de", "germany", "Kaufberatung", "smarthome", "homeautomation",
    "gadgets", "malelifestyle", "AskEurope", "solar", "camping",
    "electricvehicles", "frugal", "buyitforlife",
]

# Wish-language patterns (German + English)
WISH_PATTERNS = [
    r"ich w[üu]nsch",          # "ich wünschte", "ich wünsche mir"
    r"gibt es (nicht|kein)",   # "gibt es nicht"
    r"ich such[e ] ",          # "ich suche ein Produkt"
    r"w[äa]re cool wenn",      # "wäre cool wenn"
    r"jemand sollte",          # "jemand sollte das erfinden"
    r"warum gibt es kein",     # "warum gibt es kein X"
    r"i wish (there was|someone)",
    r"why (isn't there|doesn't exist)",
    r"someone should make",
    r"does anyone know where",
    r"looking for something that",
    r"can't find a product",
    r"need a .{5,40} (that|which|but)",
]

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_CLUSTER_SIZE    = 3     # minimum wishes to create a pre-order product
PRE_ORDER_MINIMUM   = 10   # minimum pre-orders before fulfillment triggered
MAX_PRODUCTS_PER_RUN = 3   # max new pre-order products per scan


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS do_wishes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER,
                source      TEXT,
                subreddit   TEXT,
                text        TEXT UNIQUE,
                url         TEXT,
                score       INTEGER DEFAULT 0,
                clustered   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS do_clusters (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              INTEGER,
                concept         TEXT,
                category        TEXT,
                wish_count      INTEGER,
                avg_price_max   REAL,
                keywords        TEXT,
                shopify_id      TEXT,
                shopify_handle  TEXT,
                preorder_count  INTEGER DEFAULT 0,
                fulfilled       INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS do_scans (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        INTEGER,
                wishes    INTEGER,
                clusters  INTEGER,
                products  INTEGER
            );
            CREATE INDEX IF NOT EXISTS do_wishes_ts ON do_wishes(ts);
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Mine latent demand from Reddit
# ─────────────────────────────────────────────────────────────────────────────

async def mine_reddit_wishes(limit_per_sub: int = 50) -> list[dict]:
    """Scan subreddits for latent product wish expressions."""
    cid    = REDDIT_CLIENT_ID()
    secret = REDDIT_CLIENT_SECRET()
    if not cid or not secret:
        log.warning("REDDIT_CLIENT_ID/SECRET not set — mining skipped")
        return []

    import aiohttp

    # Get Reddit OAuth token
    async with aiohttp.ClientSession() as sess:
        async with sess.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=aiohttp.BasicAuth(cid, secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            tok_data = await r.json(content_type=None)
    token = tok_data.get("access_token", "")
    if not token:
        log.warning("Reddit token failed: %s", tok_data)
        return []

    headers = {"Authorization": f"bearer {token}", "User-Agent": REDDIT_USER_AGENT}
    wishes: list[dict] = []
    compiled = [re.compile(p, re.IGNORECASE) for p in WISH_PATTERNS]

    async with aiohttp.ClientSession(headers=headers) as sess:
        for sub in SCAN_SUBREDDITS:
            try:
                async with sess.get(
                    f"https://oauth.reddit.com/r/{sub}/new.json",
                    params={"limit": limit_per_sub},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)

                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    p = post.get("data", {})
                    title   = p.get("title", "")
                    selftext = p.get("selftext", "")
                    full_text = f"{title} {selftext}"
                    score    = p.get("score", 0)
                    url      = f"https://reddit.com{p.get('permalink', '')}"

                    # Check for wish patterns
                    matched = any(pat.search(full_text) for pat in compiled)
                    if not matched:
                        continue

                    # Skip very short or very long texts
                    if len(full_text) < 20 or len(full_text) > 2000:
                        continue

                    # Extract the meaningful part (title usually most relevant)
                    wish_text = title if len(title) > 20 else full_text[:300]
                    wishes.append({
                        "source":    "reddit",
                        "subreddit": sub,
                        "text":      wish_text.strip(),
                        "url":       url,
                        "score":     score,
                    })

                await asyncio.sleep(1)  # Reddit rate limit: 60 req/min
            except Exception as e:
                log.debug("Reddit scan error r/%s: %s", sub, e)

    log.info("Mined %d wish expressions from Reddit", len(wishes))

    # Save to DB (ignore duplicates)
    now = int(time.time())
    with _db() as con:
        for w in wishes:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO do_wishes(ts,source,subreddit,text,url,score) VALUES(?,?,?,?,?,?)",
                    (now, w["source"], w["subreddit"], w["text"][:500], w["url"], w["score"]),
                )
            except Exception:
                pass

    return wishes


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Cluster desires into product concepts using Claude
# ─────────────────────────────────────────────────────────────────────────────

async def cluster_desires(wishes: list[dict]) -> list[dict]:
    """Use Claude to cluster raw wishes into actionable product concepts."""
    if not wishes:
        return []

    try:
        from modules.ai_client import ai_complete
    except ImportError:
        return []

    # Take up to 60 wishes for clustering (token budget)
    sample = sorted(wishes, key=lambda w: w.get("score", 0), reverse=True)[:60]
    wish_texts = "\n".join(f"- {w['text'][:200]}" for w in sample)

    prompt = f"""Analysiere diese Produkt-Wünsche aus Reddit und identifiziere konkrete Produkt-Konzepte.

Wünsche:
{wish_texts}

Erstelle eine JSON-Liste von Produkt-Konzepten die man WIRKLICH verkaufen kann. Nur konkrete physische Produkte.

Format (NUR gültiges JSON, kein Markdown):
[
  {{
    "concept": "Solar-Powerbank mit integrierter Taschenlampe unter 80€",
    "category": "Solar",
    "wish_count": 5,
    "max_price_eur": 80,
    "keywords": ["solar", "powerbank", "taschenlampe", "camping"],
    "demand_summary": "5 Nutzer suchen eine kompakte Solar-Powerbank die auch als Taschenlampe dient"
  }}
]

Regeln:
- Nur Produkte unter 200€
- Mindestens 2 ähnliche Wünsche für ein Konzept
- Smart Home, Elektronik, Outdoor, Solar, Gadgets bevorzugt
- Max 5 Konzepte zurückgeben
- Keine Dienstleistungen, nur physische Produkte"""

    raw = await ai_complete(prompt, model_hint="fast", max_tokens=800)

    try:
        # Clean JSON from possible markdown
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        clusters = json.loads(cleaned.strip())
        if not isinstance(clusters, list):
            return []
        log.info("Clustered %d product concepts from %d wishes", len(clusters), len(wishes))
        return clusters
    except Exception as e:
        log.warning("Cluster parse failed: %s | raw=%s", e, raw[:200])
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Create pre-order product on Shopify
# ─────────────────────────────────────────────────────────────────────────────

async def create_preorder_product(concept: dict) -> dict | None:
    """Create a Shopify pre-order product from a demand cluster concept."""
    import aiohttp
    from modules.ai_client import ai_complete

    domain  = SHOPIFY_DOMAIN()
    token   = SHOPIFY_TOKEN()
    version = SHOPIFY_VERSION()
    if not domain or not token:
        return None

    max_price  = float(concept.get("max_price_eur", 49))
    # Set price slightly below demand max (value perception)
    price      = round(max(9.99, max_price * 0.85), 2)
    wish_count = concept.get("wish_count", 0)
    category   = concept.get("category", "Gadgets")
    concept_title = concept.get("concept", "")
    summary    = concept.get("demand_summary", "")

    # Generate compelling pre-order description
    desc_prompt = f"""Schreibe eine überzeugende Pre-Order-Produktbeschreibung.

Produkt: {concept_title}
Nachfrage: {wish_count} Menschen haben genau dieses Produkt gesucht
Maximaler Preis laut Nachfrage: €{max_price:.0f}
Unser Pre-Order-Preis: €{price:.2f}

Die Beschreibung soll:
1. Erklären warum dieses Produkt bisher nicht existiert hat
2. Die Knappheit betonen: "Nur produziert wenn {PRE_ORDER_MINIMUM} Bestellungen erreicht"
3. Den Vorteil für Früh-Besteller hervorheben
4. Trust aufbauen: Geld-zurück-Garantie wenn nicht produziert
5. 3-4 konkrete Produktvorteile als HTML-Liste
6. Ca. 150 Wörter, Deutsch
7. HTML format mit <p> und <ul><li>

Nur HTML, keine Erklärungen."""

    description = await ai_complete(desc_prompt, model_hint="fast", max_tokens=400)
    if not description:
        description = (
            f"<p><strong>🔥 PRE-ORDER: {wish_count} Menschen haben genau dieses Produkt gesucht!</strong></p>"
            f"<p>{summary}</p>"
            f"<ul>"
            f"<li>✅ Wird produziert sobald {PRE_ORDER_MINIMUM} Bestellungen erreicht</li>"
            f"<li>✅ 100% Geld zurück wenn nicht produziert</li>"
            f"<li>✅ Preis basiert auf echter Nachfrage-Analyse</li>"
            f"<li>✅ Lieferung ca. 4-6 Wochen nach Produktion</li>"
            f"</ul>"
        )

    # Shopify product payload
    tags = ["preorder", "demand-oracle", category.lower()] + concept.get("keywords", [])[:3]
    payload = {
        "product": {
            "title":        concept_title,
            "body_html":    description,
            "product_type": category,
            "vendor":       "Demand Oracle | ineedit.com.co",
            "status":       "active",
            "tags":         tags,
            "variants": [{
                "price":                   f"{price:.2f}",
                "inventory_management":    "shopify",
                "inventory_quantity":      100,   # virtual stock for pre-orders
                "fulfillment_service":     "manual",
                "requires_shipping":       True,
            }],
            "metafields": [
                {
                    "namespace": "demand_oracle",
                    "key":       "pre_order_minimum",
                    "value":     str(PRE_ORDER_MINIMUM),
                    "type":      "single_line_text_field",
                },
                {
                    "namespace": "demand_oracle",
                    "key":       "wish_count",
                    "value":     str(wish_count),
                    "type":      "single_line_text_field",
                },
            ],
        }
    }

    url  = f"https://{domain}/admin/api/{version}/products.json"
    hdrs = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(headers=hdrs, timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, json=payload) as r:
                if r.status in (200, 201):
                    data   = await r.json(content_type=None)
                    prod   = data.get("product", {})
                    pid    = str(prod.get("id", ""))
                    handle = prod.get("handle", "")
                    store  = SHOPIFY_STORE().rstrip("/")
                    log.info("PRE-ORDER created: %s (€%.2f) — %s/products/%s",
                             concept_title[:50], price, store, handle)
                    return {
                        "shopify_id":     pid,
                        "shopify_handle": handle,
                        "price":          price,
                        "url":            f"{store}/products/{handle}",
                    }
                else:
                    body = await r.text()
                    log.warning("Shopify pre-order create failed %s: %s", r.status, body[:300])
                    return None
    except Exception as e:
        log.warning("Shopify create error: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Monitor pre-orders and trigger fulfillment
# ─────────────────────────────────────────────────────────────────────────────

async def check_preorder_thresholds() -> list[dict]:
    """Check all active pre-order products. Alert when minimum reached."""
    import aiohttp

    domain  = SHOPIFY_DOMAIN()
    token   = SHOPIFY_TOKEN()
    version = SHOPIFY_VERSION()
    if not domain or not token:
        return []

    with _db() as con:
        active = con.execute(
            "SELECT * FROM do_clusters WHERE shopify_id IS NOT NULL AND fulfilled=0"
        ).fetchall()

    triggered = []
    hdrs = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    for cluster in active:
        try:
            async with aiohttp.ClientSession(headers=hdrs, timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(
                    f"https://{domain}/admin/api/{version}/orders/count.json",
                    params={"status": "any", "product_id": cluster["shopify_id"]},
                ) as r:
                    data = await r.json(content_type=None)
            order_count = data.get("count", 0)

            # Update DB
            with _db() as con:
                con.execute("UPDATE do_clusters SET preorder_count=? WHERE id=?",
                            (order_count, cluster["id"]))

            if order_count >= PRE_ORDER_MINIMUM:
                triggered.append(dict(cluster) | {"order_count": order_count})
                await _send_fulfillment_alert(dict(cluster), order_count)

        except Exception as e:
            log.debug("Threshold check error for cluster %s: %s", cluster["id"], e)

    return triggered


async def _send_fulfillment_alert(cluster: dict, order_count: int) -> None:
    """Notify Rudolf via Telegram that a pre-order product hit its minimum."""
    import aiohttp

    token   = TELEGRAM_TOKEN()
    chat_id = TELEGRAM_CHAT()
    if not token or not chat_id:
        return

    store = SHOPIFY_STORE().rstrip("/")
    text = (
        f"🚀 <b>PRE-ORDER MINIMUM ERREICHT!</b>\n\n"
        f"Produkt: {cluster.get('concept', '')}\n"
        f"Bestellungen: <b>{order_count}/{PRE_ORDER_MINIMUM}</b> ✅\n"
        f"Shop: {store}/products/{cluster.get('shopify_handle', '')}\n\n"
        f"<b>JETZT BESTELLEN:</b> Lieferant für '{cluster.get('keywords', '')}' "
        f"auf AliExpress suchen und {order_count}x bestellen!\n"
        f"Kategorie: {cluster.get('category', '')}"
    )

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        await s.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )

    # Mark as fulfilled (manual action required)
    with _db() as con:
        con.execute("UPDATE do_clusters SET fulfilled=1 WHERE id=?", (cluster.get("id"),))


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_demand_scan() -> dict:
    """Full Demand Oracle pipeline: mine → cluster → create pre-orders → check thresholds."""
    log.info("[DemandOracle] Starting full scan")

    # 1. Mine wishes from Reddit
    wishes = await mine_reddit_wishes(limit_per_sub=50)

    # Also pull unclustered wishes from DB (accumulation from previous runs)
    with _db() as con:
        db_unclustered = con.execute(
            "SELECT text, score, subreddit FROM do_wishes WHERE clustered=0 ORDER BY score DESC LIMIT 100"
        ).fetchall()
    all_wishes = wishes + [dict(w) for w in db_unclustered]

    # 2. Cluster into product concepts
    clusters = await cluster_desires(all_wishes)

    # 3. Filter: only create products for clusters with enough demand
    viable = [c for c in clusters if c.get("wish_count", 0) >= MIN_CLUSTER_SIZE]
    log.info("[DemandOracle] %d viable clusters from %d wishes", len(viable), len(all_wishes))

    # 4. Create pre-order products (max N per run)
    created = []
    for concept in viable[:MAX_PRODUCTS_PER_RUN]:
        # Skip if we already have a product for this concept (basic dedup)
        with _db() as con:
            existing = con.execute(
                "SELECT id FROM do_clusters WHERE concept=?", (concept.get("concept", ""),)
            ).fetchone()
        if existing:
            continue

        product = await create_preorder_product(concept)
        if product:
            # Save cluster to DB
            with _db() as con:
                con.execute("""
                    INSERT INTO do_clusters(ts, concept, category, wish_count, avg_price_max,
                        keywords, shopify_id, shopify_handle)
                    VALUES(?,?,?,?,?,?,?,?)
                """, (
                    int(time.time()),
                    concept.get("concept", ""),
                    concept.get("category", ""),
                    concept.get("wish_count", 0),
                    concept.get("max_price_eur", 0),
                    json.dumps(concept.get("keywords", [])),
                    product["shopify_id"],
                    product["shopify_handle"],
                ))
            created.append({**concept, **product})
            await asyncio.sleep(3)

    # Mark wishes as clustered
    if all_wishes:
        with _db() as con:
            con.execute("UPDATE do_wishes SET clustered=1 WHERE clustered=0")

    # 5. Check thresholds for existing pre-orders
    triggered = await check_preorder_thresholds()

    # 6. Log scan
    with _db() as con:
        con.execute("INSERT INTO do_scans(ts, wishes, clusters, products) VALUES(?,?,?,?)",
                    (int(time.time()), len(all_wishes), len(viable), len(created)))

    summary = {
        "wishes_mined":       len(all_wishes),
        "clusters_found":     len(viable),
        "products_created":   len(created),
        "thresholds_hit":     len(triggered),
        "new_products":       [{"concept": c["concept"], "price": c["price"], "url": c["url"]} for c in created],
    }

    await _send_scan_report(summary)
    return summary


async def _send_scan_report(summary: dict) -> None:
    import aiohttp

    token   = TELEGRAM_TOKEN()
    chat_id = TELEGRAM_CHAT()
    if not token or not chat_id:
        return

    new = summary.get("new_products", [])
    lines = [
        f"🔮 <b>Demand Oracle Scan</b>",
        f"Wünsche gesammelt: {summary['wishes_mined']}",
        f"Produkt-Konzepte: {summary['clusters_found']}",
        f"Neue Pre-Orders: {summary['products_created']}",
        f"Schwellen erreicht: {summary['thresholds_hit']}",
    ]
    if new:
        lines.append("\n<b>Neue Pre-Order Produkte:</b>")
        for p in new[:3]:
            lines.append(f"• {p['concept'][:50]} — €{p['price']:.2f}\n  {p['url']}")

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
            total_wishes   = con.execute("SELECT COUNT(*) FROM do_wishes").fetchone()[0]
            total_clusters = con.execute("SELECT COUNT(*) FROM do_clusters").fetchone()[0]
            total_products = con.execute("SELECT COUNT(*) FROM do_clusters WHERE shopify_id IS NOT NULL").fetchone()[0]
            fulfilled      = con.execute("SELECT COUNT(*) FROM do_clusters WHERE fulfilled=1").fetchone()[0]
            total_orders   = con.execute("SELECT SUM(preorder_count) FROM do_clusters").fetchone()[0] or 0
            active_products = con.execute(
                "SELECT concept, category, wish_count, preorder_count, shopify_handle "
                "FROM do_clusters WHERE fulfilled=0 AND shopify_id IS NOT NULL "
                "ORDER BY preorder_count DESC LIMIT 10"
            ).fetchall()
        return {
            "total_wishes":    total_wishes,
            "total_clusters":  total_clusters,
            "products_live":   total_products,
            "fulfilled":       fulfilled,
            "total_preorders": int(total_orders),
            "active_products": [dict(r) for r in active_products],
            "pre_order_minimum": PRE_ORDER_MINIMUM,
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler entry point
# ─────────────────────────────────────────────────────────────────────────────

async def scheduled_demand_scan() -> str:
    try:
        result = await run_demand_scan()
        return (
            f"DemandOracle: {result['wishes_mined']} wünsche, "
            f"{result['clusters_found']} konzepte, "
            f"{result['products_created']} produkte erstellt, "
            f"{result['thresholds_hit']} schwellen erreicht"
        )
    except Exception as e:
        return f"DemandOracle Fehler: {e}"


# Init
try:
    init_db()
except Exception as e:
    log.warning("DemandOracle DB init failed: %s", e)
