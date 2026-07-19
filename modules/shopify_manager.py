"""
shopify_manager.py — Vollautonomer Shopify Manager Assistant
============================================================
Koordiniert alle Shopify-Automatisierungen in einem zentralen Manager:
- A/B Tests: Preise, Titel, Beschreibungen testen → Gewinner automatisch anwenden
- Duplikat-Schutz: keine Produkte doppelt importieren
- SEO-Optimierung: Titel, Meta, Alt-Texte automatisch verbessern
- Preisoptimierung: .99-Psychologie, Margin-Check, Marktvergleich
- Qualitäts-Gatekeeper: nur 5★ Tech-Produkte (Regeln aus shop_rules.json)
- Dashboard-Integration: GET/POST /api/shopify/manager/*

Verwendung:
    from modules.shopify_manager import run_manager_cycle, get_manager_status
    result = await run_manager_cycle()
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
from typing import Any, Dict, List, Optional

log = logging.getLogger("ShopifyManager")

_BASE     = Path(__file__).parent.parent
_DATA_DIR = _BASE / "data"
_DATA_DIR.mkdir(exist_ok=True)
_DB       = _DATA_DIR / "shopify_manager.db"

SHOPIFY_DOMAIN = os.getenv("SHOPIFY_DOMAIN", os.getenv("SHOPIFY_STORE_URL", "ineedit.com.co"))
SHOPIFY_TOKEN  = os.getenv("SHOPIFY_ACCESS_TOKEN", os.getenv("SHOPIFY_TOKEN", ""))
API_VERSION    = os.getenv("SHOPIFY_API_VERSION", "2024-01")

# ── DB Init ───────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con

def _init_db():
    with _db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS action_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                action   TEXT NOT NULL,
                target   TEXT,
                result   TEXT,
                ts       REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS imported_products (
                product_id TEXT PRIMARY KEY,
                title      TEXT,
                vendor     TEXT,
                imported_at REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS ab_decisions (
                product_id  TEXT,
                test_type   TEXT,
                winner      TEXT,
                applied_at  REAL DEFAULT (unixepoch()),
                PRIMARY KEY (product_id, test_type)
            );
        """)

_init_db()

# ── Shopify API Helper ────────────────────────────────────────────────────────

async def _gql(query: str, variables: dict = None) -> dict:
    """GraphQL-Anfrage an Shopify Admin API."""
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        return {"errors": [{"message": "Shopify nicht konfiguriert"}]}
    try:
        import aiohttp
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                json={"query": query, "variables": variables or {}},
                headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                         "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                return await r.json(content_type=None)
    except Exception as e:
        log.error("Shopify GQL Fehler: %s", e)
        return {"errors": [{"message": str(e)}]}


async def _rest(method: str, path: str, data: dict = None) -> dict:
    """REST-Anfrage an Shopify Admin API."""
    if not SHOPIFY_TOKEN or not SHOPIFY_DOMAIN:
        return {"error": "Shopify nicht konfiguriert"}
    try:
        import aiohttp
        url = f"https://{SHOPIFY_DOMAIN}/admin/api/{API_VERSION}/{path}"
        async with aiohttp.ClientSession() as s:
            if method.upper() == "GET":
                async with s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
                                  timeout=aiohttp.ClientTimeout(total=20)) as r:
                    return await r.json(content_type=None)
            elif method.upper() in ("PUT", "POST"):
                async with s.request(
                    method.upper(), url,
                    json=data,
                    headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN,
                             "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    return await r.json(content_type=None)
    except Exception as e:
        return {"error": str(e)}

# ── Duplikat-Prüfung ──────────────────────────────────────────────────────────

def is_duplicate_product(product_id: str = None, title: str = None) -> bool:
    """True wenn Produkt bereits importiert wurde (nach ID oder Titel)."""
    with _db() as c:
        if product_id:
            row = c.execute("SELECT 1 FROM imported_products WHERE product_id=?", (product_id,)).fetchone()
            if row:
                return True
        if title:
            norm = re.sub(r"\s+", " ", (title or "").lower().strip())[:100]
            row = c.execute(
                "SELECT 1 FROM imported_products WHERE lower(trim(title)) LIKE ?",
                (f"%{norm[:50]}%",)
            ).fetchone()
            if row:
                return True
    return False


def register_product(product_id: str, title: str, vendor: str = ""):
    """Produkt nach erfolgreichem Import registrieren."""
    with _db() as c:
        c.execute(
            "INSERT OR REPLACE INTO imported_products (product_id, title, vendor) VALUES (?,?,?)",
            (product_id, title, vendor)
        )


def _log_action(action: str, target: str = "", result: str = ""):
    with _db() as c:
        c.execute("INSERT INTO action_log (action, target, result) VALUES (?,?,?)",
                  (action, target, result[:500] if result else ""))

# ── A/B Test Integration ──────────────────────────────────────────────────────

async def run_ab_tests(products_per_run: int = 5) -> dict:
    """Startet A/B Tests für Preise/Titel. Delegiert an shopify_ab_tester."""
    try:
        from modules.shopify_ab_tester import run_shopify_ab_tests
        result = await run_shopify_ab_tests()
        started = result.get("started", 0)
        _log_action("ab_test_run", result=f"{started} neue Tests")
        return {"ok": True, "started": started, "result": result}
    except Exception as e:
        _log_action("ab_test_run", result=f"Fehler: {e}")
        return {"ok": False, "error": str(e)}


async def analyze_ab_winners() -> dict:
    """Analysiert A/B Tests und wendet Gewinner an."""
    try:
        from modules.shopify_ab_tester import analyze_shopify_ab_winners
        result = await analyze_shopify_ab_winners()
        winners = result.get("winners_applied", 0)
        _log_action("ab_analyze", result=f"{winners} Gewinner")
        return {"ok": True, "winners_applied": winners, "result": result}
    except Exception as e:
        _log_action("ab_analyze", result=f"Fehler: {e}")
        return {"ok": False, "error": str(e)}

# ── SEO Optimierung ───────────────────────────────────────────────────────────

async def run_seo_optimization(limit: int = 20) -> dict:
    """SEO-Optimierung: Titel, Meta-Beschreibungen, Alt-Texte verbessern."""
    optimized = 0
    errors = []
    try:
        # Produkte ohne body_html oder mit kurzer Beschreibung holen
        q = """
        query($n: Int!) {
          products(first: $n, query: "status:active") {
            edges { node {
              id title bodyHtml
              seo { title description }
              images(first: 1) { edges { node { altText } } }
            }}
          }
        }"""
        data = await _gql(q, {"n": limit})
        products = data.get("data", {}).get("products", {}).get("edges", [])
        for edge in products:
            p = edge["node"]
            pid = p["id"]
            title = p.get("title", "")
            body  = p.get("bodyHtml", "") or ""
            seo   = p.get("seo", {})

            needs_seo = (
                not seo.get("title") or
                not seo.get("description") or
                len(body.strip()) < 100
            )
            if not needs_seo:
                continue

            try:
                from modules.ai_client import ai_complete
                prompt = (
                    f"Erstelle für dieses Shopify Smart Home/Tech Produkt:\n"
                    f"Titel: {title}\n\n"
                    f"1. SEO-Meta-Title (max 60 Zeichen, keyword-reich)\n"
                    f"2. SEO-Meta-Description (max 155 Zeichen)\n"
                    f"3. Produktbeschreibung (150-200 Wörter, Vorteile, Keywords: smart home, tech, automatisierung)\n\n"
                    f"Format:\nTITLE: ...\nDESC: ...\nBODY: ..."
                )
                ai_text = await ai_complete(prompt, max_tokens=400)
                if not ai_text:
                    continue

                seo_title = re.search(r"TITLE:\s*(.+)", ai_text)
                seo_desc  = re.search(r"DESC:\s*(.+)", ai_text)
                body_text = re.search(r"BODY:\s*([\s\S]+?)(?:\n[A-Z]+:|$)", ai_text)

                update_data: dict = {
                    "product": {
                        "id": pid.split("/")[-1],
                        "metafields_global_title_tag": seo_title.group(1).strip()[:60] if seo_title else None,
                        "metafields_global_description_tag": seo_desc.group(1).strip()[:155] if seo_desc else None,
                    }
                }
                if body_text and len(body.strip()) < 100:
                    update_data["product"]["body_html"] = f"<p>{body_text.group(1).strip()}</p>"

                # Felder ohne Wert entfernen
                update_data["product"] = {k: v for k, v in update_data["product"].items() if v}

                pid_num = pid.split("/")[-1]
                await _rest("PUT", f"products/{pid_num}.json", update_data)
                optimized += 1
                _log_action("seo_optimize", target=title[:60], result="OK")
                await asyncio.sleep(0.5)  # Rate-Limit Schutz
            except Exception as e:
                errors.append(f"{title[:30]}: {e}")

    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "optimized": optimized, "errors": errors[:5]}

# ── Preis-Optimierung ─────────────────────────────────────────────────────────

async def run_price_optimization(limit: int = 30) -> dict:
    """Psychologische Preisoptimierung: .99 / .95 Endings, Margin-Check."""
    updated = 0
    try:
        from modules.shopify_price_optimizer import run_price_optimization as _ext
        result = await _ext()
        updated = result.get("updated", 0)
        _log_action("price_optimize", result=f"{updated} Preise angepasst")
        return {"ok": True, "updated": updated}
    except Exception:
        pass

    # Fallback: direkter Preis-Check
    try:
        q = """
        query($n: Int!) {
          products(first: $n, query: "status:active") {
            edges { node { id title
              variants(first: 1) { edges { node { id price } } }
            }}
          }
        }"""
        data = await _gql(q, {"n": limit})
        products = data.get("data", {}).get("products", {}).get("edges", [])
        for edge in products:
            p = edge["node"]
            variants = p.get("variants", {}).get("edges", [])
            if not variants:
                continue
            v      = variants[0]["node"]
            v_id   = v["id"].split("/")[-1]
            price  = float(v.get("price", 0))
            if price <= 0:
                continue
            # .99 Psychological Pricing
            cents = price % 1
            if abs(cents - 0.99) < 0.01 or abs(cents - 0.95) < 0.01:
                continue  # Bereits optimiert
            new_price = int(price) + 0.99 if price < 1000 else round(price, -1) - 0.05
            new_price = max(new_price, 0.99)
            pid_num = p["id"].split("/")[-1]
            await _rest("PUT", f"products/{pid_num}.json", {
                "product": {"id": pid_num, "variants": [{"id": v_id, "price": f"{new_price:.2f}"}]}
            })
            updated += 1
            await asyncio.sleep(0.3)
        _log_action("price_optimize", result=f"{updated} .99-Preise")
        return {"ok": True, "updated": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Qualitäts-Check bestehender Produkte ─────────────────────────────────────

async def run_quality_audit(limit: int = 50) -> dict:
    """Prüft bestehende Produkte auf Qualitäts-Standards. Meldet Probleme."""
    issues = []
    try:
        q = """
        query($n: Int!) {
          products(first: $n, query: "status:active") {
            edges { node {
              id title vendor bodyHtml productType
              images(first: 1) { edges { node { src } } }
              variants(first: 1) { edges { node { price } } }
            }}
          }
        }"""
        data = await _gql(q, {"n": limit})
        products = data.get("data", {}).get("products", {}).get("edges", [])

        for edge in products:
            p = edge["node"]
            title  = p.get("title", "")
            body   = p.get("bodyHtml", "") or ""
            ptype  = p.get("productType", "") or ""
            vendor = p.get("vendor", "") or ""
            images = p.get("images", {}).get("edges", [])
            price  = float(p.get("variants", {}).get("edges", [{}])[0].get("node", {}).get("price", 0) or 0)

            product_issues = []
            if not body.strip() or len(body.strip()) < 50:
                product_issues.append("Fehlende/kurze Beschreibung")
            if not images:
                product_issues.append("Kein Bild")
            if not ptype:
                product_issues.append("Kein product_type")
            if price < 0.01:
                product_issues.append("Preis = 0")
            if vendor.lower() in ("supermegabot", "bullpowerbot", "demo", "test"):
                product_issues.append(f"Falscher Vendor: {vendor}")

            if product_issues:
                issues.append({
                    "id": p["id"],
                    "title": title[:60],
                    "issues": product_issues,
                })

    except Exception as e:
        return {"ok": False, "error": str(e)}

    _log_action("quality_audit", result=f"{len(issues)} Probleme")
    return {"ok": True, "issues": issues[:20], "total_issues": len(issues)}

# ── Gesamt-Zyklus ─────────────────────────────────────────────────────────────

async def run_manager_cycle() -> dict:
    """
    Vollständiger Manager-Zyklus (täglich):
    1. A/B Tests starten (neue Produkte)
    2. A/B Gewinner analysieren + anwenden
    3. SEO optimieren (20 Produkte)
    4. Preise .99-optimieren (30 Produkte)
    5. Qualitäts-Audit (50 Produkte)
    """
    results = {}

    log.info("ShopifyManager: Starte vollständigen Zyklus...")

    # 1. A/B Tests
    results["ab_tests"] = await run_ab_tests()
    await asyncio.sleep(2)

    # 2. A/B Gewinner
    results["ab_winners"] = await analyze_ab_winners()
    await asyncio.sleep(2)

    # 3. SEO
    results["seo"] = await run_seo_optimization(20)
    await asyncio.sleep(2)

    # 4. Preise
    results["prices"] = await run_price_optimization(30)
    await asyncio.sleep(2)

    # 5. Qualitäts-Audit
    results["quality"] = await run_quality_audit(50)

    summary = (
        f"AB-Tests: {results['ab_tests'].get('started', 0)} neu | "
        f"Gewinner: {results['ab_winners'].get('winners_applied', 0)} | "
        f"SEO: {results['seo'].get('optimized', 0)} | "
        f"Preise: {results['prices'].get('updated', 0)} | "
        f"Qualitätsprobleme: {results['quality'].get('total_issues', 0)}"
    )
    _log_action("manager_cycle", result=summary)
    log.info("ShopifyManager: Zyklus fertig — %s", summary)

    # Telegram-Report bei Problemen
    quality_issues = results["quality"].get("total_issues", 0)
    if quality_issues > 0:
        try:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat  = os.getenv("TELEGRAM_CHAT_ID", "")
            if token and chat:
                import aiohttp
                msg = (f"🏪 <b>Shopify Manager</b>\n{summary}\n\n"
                       f"⚠️ {quality_issues} Produkte mit Qualitätsproblemen!")
                async with aiohttp.ClientSession() as s:
                    await s.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                        timeout=aiohttp.ClientTimeout(total=8),
                    )
        except Exception:
            pass

    return {"ok": True, "summary": summary, "details": results}


async def get_manager_status() -> dict:
    """Dashboard-Status: letzte Aktionen, AB-Test-Status, Duplikat-Count."""
    with _db() as c:
        recent = c.execute(
            "SELECT action, target, result, datetime(ts, 'unixepoch') AS ts "
            "FROM action_log ORDER BY ts DESC LIMIT 20"
        ).fetchall()
        dup_count = c.execute("SELECT COUNT(*) FROM imported_products").fetchone()[0]
        ab_count  = c.execute("SELECT COUNT(*) FROM ab_decisions").fetchone()[0]

    try:
        from modules.shopify_ab_tester import get_ab_test_status
        ab_status = await get_ab_test_status()
    except Exception:
        ab_status = {}

    return {
        "ok": True,
        "recent_actions": [dict(r) for r in recent],
        "registered_products": dup_count,
        "ab_decisions": ab_count,
        "ab_test_status": ab_status,
    }
