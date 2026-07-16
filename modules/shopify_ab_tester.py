"""
shopify_ab_tester.py — Autonomes Shopify A/B Testing
=====================================================
Testet automatisch Produkt-Titel, Preise und Beschreibungen in Shopify.
Speichert Zustand in SQLite, ermittelt Gewinner nach Bestellrate.

Test-Typen:
  price       — ±10%/±15% Preis-Variation
  title       — AI-generierter SEO-Alternativtitel (Claude Haiku)
  description — AI-optimierte Produktbeschreibung

Ablauf:
  run_shopify_ab_tests()     — jeden Tag: PRODUCTS_PER_RUN neue Tests starten
  analyze_shopify_ab_winners() — alle 48h: Gewinner auswählen / Verlierer zurücksetzen
  get_ab_test_status()       — Dashboard-Übersicht
"""
import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp

log = logging.getLogger("ShopifyABTest")

DB_PATH = Path(__file__).parent.parent / "data" / "shopify_ab_tests.db"
TEST_DURATION_DAYS = 5
MAX_ACTIVE_TESTS = 10
PRODUCTS_PER_RUN = 5


# ── Database ──────────────────────────────────────────────────────────────────

def _db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_init():
    with _db_connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shopify_ab_tests (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id       TEXT NOT NULL,
                product_gid      TEXT NOT NULL,
                variant_id       TEXT,
                test_type        TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'active',
                original_value   TEXT NOT NULL,
                variant_value    TEXT NOT NULL,
                orders_baseline  INTEGER DEFAULT 0,
                orders_during    INTEGER DEFAULT 0,
                started_at       TEXT NOT NULL,
                ends_at          TEXT NOT NULL,
                winner           TEXT,
                notes            TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_ab_active
                ON shopify_ab_tests(product_id, test_type)
                WHERE status = 'active';
        """)


# ── Shopify helpers ───────────────────────────────────────────────────────────

async def _shopify_auth() -> dict:
    token = (
        os.getenv("SHOPIFY_ADMIN_API_TOKEN")
        or os.getenv("SHOPIFY_SUITE_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
    if token and token != "NEUER_TOKEN_ERFORDERLICH":
        return {"X-Shopify-Access-Token": token}
    return {}


def _shop_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")


def _api_version() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2026-04")


async def _gql(query: str, variables: dict = None) -> dict:
    """Shopify Admin GraphQL with 429 retry."""
    auth = await _shopify_auth()
    url = f"https://{_shop_domain()}/admin/api/{_api_version()}/graphql.json"
    headers = {"Content-Type": "application/json", **auth}
    payload = {"query": query, "variables": variables or {}}
    backoff = [4, 8, 16]
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status == 429:
                        wait = int(r.headers.get("Retry-After", backoff[attempt]))
                        log.warning("Shopify rate-limited, warte %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    return await r.json()
        except Exception as exc:
            log.warning("Shopify GraphQL Fehler (Versuch %d): %s", attempt + 1, exc)
            if attempt == 2:
                return {"errors": str(exc)}
    return {"errors": "max retries exceeded"}


# ── AI content generation ─────────────────────────────────────────────────────

async def _ai_generate_title(original_title: str, product_type: str) -> str:
    """SEO-optimierten Alternativtitel via Claude Haiku generieren."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        if "smart" not in original_title.lower():
            return f"Smart {original_title}"
        return original_title + " – Premium"

    prompt = (
        f"Generate ONE alternative SEO-optimized German product title for this Shopify product.\n"
        f"Original: {original_title}\n"
        f"Product type: {product_type}\n"
        f"Rules: max 80 chars, include power keyword (Smart/Premium/Pro/Set/Kit), "
        f"different from original, no quotes.\n"
        f"Reply with ONLY the new title, nothing else."
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                body = await r.json()
                text = body.get("content", [{}])[0].get("text", "").strip().strip('"')
                return text[:80] if text else original_title
    except Exception as exc:
        log.warning("AI title generation failed: %s", exc)
        return original_title


async def _ai_generate_description(title: str, current_html: str, product_type: str) -> str:
    """Verbesserte Produktbeschreibung via Claude Haiku generieren."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return ""

    current_text = re.sub(r"<[^>]+>", "", current_html)[:500]
    prompt = (
        f"Write an improved German product description for this Shopify product.\n"
        f"Title: {title}\n"
        f"Type: {product_type}\n"
        f"Current description: {current_text}\n\n"
        f"Rules:\n"
        f"- 150-250 words in German\n"
        f"- Include 3-5 relevant keywords naturally\n"
        f"- Focus on benefits and smart/tech features\n"
        f"- Use simple HTML: <p> tags only, no complex formatting\n"
        f"- No fake reviews or unverifiable claims\n"
        f"Reply with ONLY the HTML description."
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                body = await r.json()
                text = body.get("content", [{}])[0].get("text", "").strip()
                return text if len(text) > 50 else ""
    except Exception as exc:
        log.warning("AI description generation failed: %s", exc)
        return ""


# ── Product fetching ──────────────────────────────────────────────────────────

async def _get_testable_products(count: int = 20) -> list:
    """Aktive Produkte holen, die nicht bereits in einem laufenden Test sind."""
    with _db_connect() as conn:
        active_ids = {
            r[0] for r in conn.execute(
                "SELECT product_id FROM shopify_ab_tests WHERE status='active'"
            )
        }

    q = """
    query($first: Int!) {
      products(first: $first, query: "status:active") {
        edges { node {
          id title bodyHtml productType vendor
          variants(first: 1) {
            edges { node { id price compareAtPrice } }
          }
        }}
      }
    }
    """
    r = await _gql(q, {"first": 50})
    products = []
    for e in r.get("data", {}).get("products", {}).get("edges", []):
        node = e["node"]
        numeric_id = node["id"].split("/")[-1]
        if numeric_id in active_ids:
            continue
        variants = node.get("variants", {}).get("edges", [])
        if not variants:
            continue
        v = variants[0]["node"]
        try:
            price = float(v.get("price", 0) or 0)
        except (ValueError, TypeError):
            continue
        if price < 5:
            continue
        products.append({
            "product_id":    numeric_id,
            "product_gid":   node["id"],
            "title":         node.get("title", ""),
            "body_html":     node.get("bodyHtml", ""),
            "product_type":  node.get("productType", ""),
            "variant_id":    v["id"],
            "price":         price,
            "compare_at_price": v.get("compareAtPrice"),
        })

    random.shuffle(products)
    return products[:count]


# ── Order counting ────────────────────────────────────────────────────────────

async def _count_product_orders(product_id: str, days_back: int, days_window: int = 5) -> int:
    """Bestellungen für ein Produkt in einem Zeitfenster zählen."""
    now = datetime.now(timezone.utc)
    end_dt = now - timedelta(days=days_back)
    start_dt = end_dt - timedelta(days=days_window)

    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    query_str = f"created_at:>{start_str} created_at:<{end_str}"

    q = """
    query($query: String!, $first: Int!) {
      orders(first: $first, query: $query) {
        edges { node {
          lineItems(first: 20) {
            edges { node { product { id } } }
          }
        }}
      }
    }
    """
    r = await _gql(q, {"query": query_str, "first": 250})
    count = 0
    target_gid = f"gid://shopify/Product/{product_id}"
    for order_edge in r.get("data", {}).get("orders", {}).get("edges", []):
        for item_edge in order_edge["node"]["lineItems"]["edges"]:
            if item_edge["node"].get("product", {}).get("id") == target_gid:
                count += 1
                break
    return count


# ── Shopify product mutations ─────────────────────────────────────────────────

async def _apply_variant(product_gid: str, variant_id: str, test_type: str, value: dict) -> bool:
    """Test-Variante auf Shopify-Produkt anwenden."""
    if test_type == "price":
        mutation = """
        mutation($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant { id price }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": variant_id, "price": str(value["price"])}})
        errors = r.get("data", {}).get("productVariantUpdate", {}).get("userErrors", [])

    elif test_type == "title":
        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id title }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": product_gid, "title": value["title"]}})
        errors = r.get("data", {}).get("productUpdate", {}).get("userErrors", [])

    elif test_type == "description":
        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id bodyHtml }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": product_gid, "bodyHtml": value["description"]}})
        errors = r.get("data", {}).get("productUpdate", {}).get("userErrors", [])

    else:
        return False

    if errors:
        log.warning("Shopify update errors für %s [%s]: %s", product_gid, test_type, errors)
        return False
    if "errors" in r:
        log.warning("Shopify GraphQL errors: %s", r["errors"])
        return False
    return True


async def _apply_original(product_gid: str, variant_id: str, test_type: str, original_val: dict) -> bool:
    """Produkt auf Originalwert zurücksetzen."""
    if test_type == "price":
        mutation = """
        mutation($input: ProductVariantInput!) {
          productVariantUpdate(input: $input) {
            productVariant { id price }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": variant_id, "price": str(original_val["price"])}})
        errors = r.get("data", {}).get("productVariantUpdate", {}).get("userErrors", [])

    elif test_type == "title":
        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id title }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": product_gid, "title": original_val["title"]}})
        errors = r.get("data", {}).get("productUpdate", {}).get("userErrors", [])

    elif test_type == "description":
        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id bodyHtml }
            userErrors { field message }
          }
        }
        """
        r = await _gql(mutation, {"input": {"id": product_gid, "bodyHtml": original_val["description"]}})
        errors = r.get("data", {}).get("productUpdate", {}).get("userErrors", [])

    else:
        return False

    if errors:
        log.warning("Shopify revert errors: %s", errors)
        return False
    return True


# ── Public API ────────────────────────────────────────────────────────────────

async def run_shopify_ab_tests() -> dict:
    """
    Neue Shopify A/B Tests starten (max PRODUCTS_PER_RUN pro Lauf).
    Täglich vom Scheduler aufgerufen.
    """
    _db_init()

    with _db_connect() as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM shopify_ab_tests WHERE status='active'"
        ).fetchone()[0]

    if active_count >= MAX_ACTIVE_TESTS:
        log.info("AB: %d aktive Tests — Maximum erreicht, keine neuen Tests", active_count)
        return {"started": 0, "active": active_count, "reason": "max_active_reached"}

    products = await _get_testable_products(count=20)
    if not products:
        log.info("AB: keine testbaren Produkte gefunden")
        return {"started": 0, "reason": "no_testable_products"}

    started = []
    errors = []
    to_start = min(PRODUCTS_PER_RUN, MAX_ACTIVE_TESTS - active_count)

    for product in products[:to_start * 2]:
        if len(started) >= to_start:
            break

        # Test-Typ deterministisch per Produkt-ID verteilen
        try:
            type_idx = int(product["product_id"]) % 3
        except (ValueError, TypeError):
            type_idx = 0
        test_type = ["price", "title", "description"][type_idx]

        try:
            baseline = await _count_product_orders(
                product["product_id"], days_back=5, days_window=5
            )

            original_val = {}
            variant_val = {}

            if test_type == "price":
                original_val = {"price": product["price"]}
                pct = random.choice([-0.10, -0.15, 0.10, 0.15])
                new_price = round(product["price"] * (1 + pct), 2)
                variant_val = {"price": new_price, "pct_change": pct}

            elif test_type == "title":
                original_val = {"title": product["title"]}
                new_title = await _ai_generate_title(
                    product["title"], product["product_type"]
                )
                if not new_title or new_title == product["title"]:
                    log.debug("AB: AI-Titel identisch für %s — übersprungen", product["product_id"])
                    continue
                variant_val = {"title": new_title}

            elif test_type == "description":
                original_val = {"description": product["body_html"][:2000]}
                new_desc = await _ai_generate_description(
                    product["title"], product["body_html"], product["product_type"]
                )
                if not new_desc:
                    log.debug("AB: AI-Beschreibung leer für %s — übersprungen", product["product_id"])
                    continue
                variant_val = {"description": new_desc}

            ok = await _apply_variant(
                product["product_gid"], product["variant_id"], test_type, variant_val
            )
            if not ok:
                errors.append(f"{product['product_id']}: apply failed [{test_type}]")
                continue

            now = datetime.now(timezone.utc)
            ends_at = now + timedelta(days=TEST_DURATION_DAYS)

            with _db_connect() as conn:
                conn.execute(
                    """
                    INSERT INTO shopify_ab_tests
                        (product_id, product_gid, variant_id, test_type, status,
                         original_value, variant_value, orders_baseline,
                         started_at, ends_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        product["product_id"], product["product_gid"],
                        product["variant_id"], test_type, "active",
                        json.dumps(original_val), json.dumps(variant_val),
                        baseline, now.isoformat(), ends_at.isoformat(),
                    ),
                )

            started.append({
                "product_id": product["product_id"],
                "title":      product["title"],
                "test_type":  test_type,
                "variant":    variant_val,
            })
            log.info(
                "AB Test gestartet: '%s' [%s] → %s",
                product["title"][:50], test_type,
                json.dumps(variant_val)[:80],
            )
            await asyncio.sleep(0.5)

        except Exception as exc:
            log.warning("AB Test Fehler für %s: %s", product["product_id"], exc)
            errors.append(f"{product['product_id']}: {exc}")

    return {"started": len(started), "tests": started, "errors": errors}


async def analyze_shopify_ab_winners() -> dict:
    """
    Abgelaufene Tests auswerten: Gewinner behalten, Verlierer zurücksetzen.
    Alle 48h vom Scheduler aufgerufen.
    """
    _db_init()
    now = datetime.now(timezone.utc)

    with _db_connect() as conn:
        expired = conn.execute(
            """
            SELECT id, product_id, product_gid, variant_id, test_type,
                   original_value, variant_value, orders_baseline
            FROM shopify_ab_tests
            WHERE status='active' AND ends_at <= ?
            """,
            (now.isoformat(),),
        ).fetchall()

    results = {"analyzed": 0, "winners": [], "reverted": []}

    for row in expired:
        (test_id, product_id, product_gid, variant_id, test_type,
         original_json, variant_json, baseline) = row

        try:
            original_val = json.loads(original_json)
            variant_val = json.loads(variant_json)

            orders_during = await _count_product_orders(
                product_id, days_back=0, days_window=TEST_DURATION_DAYS
            )

            baseline_rate = (baseline or 0) / TEST_DURATION_DAYS
            during_rate = orders_during / TEST_DURATION_DAYS
            variant_wins = during_rate >= baseline_rate

            winner = "variant" if variant_wins else "original"
            note = (
                f"baseline={baseline_rate:.2f}/day, "
                f"during={during_rate:.2f}/day — "
                f"{'kept variant' if variant_wins else 'reverted'}"
            )

            if not variant_wins:
                await _apply_original(product_gid, variant_id, test_type, original_val)
                results["reverted"].append({
                    "product_id":    product_id,
                    "test_type":     test_type,
                    "baseline_rate": round(baseline_rate, 2),
                    "during_rate":   round(during_rate, 2),
                })
                log.info(
                    "AB REVERTED %s [%s]: %.2f → %.2f orders/day",
                    product_id, test_type, baseline_rate, during_rate,
                )
            else:
                results["winners"].append({
                    "product_id":    product_id,
                    "test_type":     test_type,
                    "variant":       variant_val,
                    "baseline_rate": round(baseline_rate, 2),
                    "during_rate":   round(during_rate, 2),
                })
                log.info(
                    "AB WINNER %s [%s]: %.2f → %.2f orders/day — Variante behalten",
                    product_id, test_type, baseline_rate, during_rate,
                )

            with _db_connect() as conn:
                conn.execute(
                    """
                    UPDATE shopify_ab_tests
                    SET status=?, winner=?, orders_during=?, notes=?
                    WHERE id=?
                    """,
                    (
                        "winner_applied" if variant_wins else "reverted",
                        winner, orders_during, note, test_id,
                    ),
                )

            results["analyzed"] += 1
            await asyncio.sleep(0.5)

        except Exception as exc:
            log.warning("AB Analyse Fehler für Test %s: %s", test_id, exc)
            with _db_connect() as conn:
                conn.execute(
                    "UPDATE shopify_ab_tests SET status='error', notes=? WHERE id=?",
                    (str(exc)[:500], test_id),
                )

    return results


async def get_ab_test_status() -> dict:
    """Dashboard-Übersicht: aktive + abgeschlossene Tests."""
    _db_init()
    with _db_connect() as conn:
        cols = [d[0] for d in conn.execute(
            "PRAGMA table_info(shopify_ab_tests)"
        ).fetchall()]

        active = conn.execute(
            "SELECT * FROM shopify_ab_tests WHERE status='active' ORDER BY started_at DESC LIMIT 20"
        ).fetchall()

        completed = conn.execute(
            "SELECT * FROM shopify_ab_tests WHERE status != 'active' ORDER BY started_at DESC LIMIT 20"
        ).fetchall()

        stats = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='active'         THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN status='winner_applied' THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN status='reverted'       THEN 1 ELSE 0 END) as reverted,
                SUM(CASE WHEN status='error'          THEN 1 ELSE 0 END) as errors
            FROM shopify_ab_tests
            """
        ).fetchone()

    def row_to_dict(row):
        return dict(zip(cols, row))

    return {
        "stats": {
            "total":    stats[0] or 0,
            "active":   stats[1] or 0,
            "winners":  stats[2] or 0,
            "reverted": stats[3] or 0,
            "errors":   stats[4] or 0,
        },
        "active_tests":    [row_to_dict(r) for r in active],
        "completed_tests": [row_to_dict(r) for r in completed],
    }
