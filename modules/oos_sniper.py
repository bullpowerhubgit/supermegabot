#!/usr/bin/env python3
"""
OOS Sniper — Konkurrenz Out-of-Stock Überwachung
=================================================
Monitort Konkurrenz-Shopify-Stores. Sobald ein Produkt OOS geht:
  → Telegram-Alert mit Handlungsempfehlung
  → Optional: eigene Shopify-Preisanpassung (Preis hochsetzen solange OOS)
  → AI-generierter Google/Meta Ad-Vorschlag für den OOS-Moment

Konfiguration: SNIPER_TARGETS env var (kommaseparierte Domains) oder
               über POST /api/oos-sniper/targets
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("OOSSniper")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "oos_sniper.db"
_BASE / "data" / ""

TG_API = "https://api.telegram.org"

def _tg_token() -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()  -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _anthropic() -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _openai()    -> str: return os.getenv("OPENAI_API_KEY", "")

DEFAULT_TARGETS = [
    t.strip() for t in os.getenv("SNIPER_TARGETS", "").split(",") if t.strip()
]

CHECK_INTERVAL_H = 2  # Prüfe alle 2 Stunden


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sniper_targets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            domain     TEXT UNIQUE NOT NULL,
            label      TEXT,
            active     INTEGER DEFAULT 1,
            added_at   INTEGER
        );

        CREATE TABLE IF NOT EXISTS sniper_products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            domain      TEXT NOT NULL,
            product_id  TEXT NOT NULL,
            title       TEXT,
            url         TEXT,
            price       REAL,
            in_stock    INTEGER DEFAULT 1,
            last_check  INTEGER,
            oos_since   INTEGER,
            back_since  INTEGER,
            alerted     INTEGER DEFAULT 0,
            UNIQUE(domain, product_id)
        );

        CREATE TABLE IF NOT EXISTS sniper_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            domain     TEXT,
            product_id TEXT,
            title      TEXT,
            event_type TEXT,
            message    TEXT,
            created_at INTEGER
        );
        """)


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _session(timeout: int = 20) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers={"User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"},
        connector=aiohttp.TCPConnector(ssl=False)
    )


async def _tg(text: str, chat: str = "") -> bool:
    token = _tg_token()
    cid   = chat or _tg_chat()
    if not token or not cid:
        return False
    try:
        async with _session(8) as s:
            r = await s.post(
                f"{TG_API}/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True}
            )
            return r.status == 200
    except Exception as e:
        log.debug("TG error: %s", e)
        return False


# ── Shopify Store Scraper ─────────────────────────────────────────────────────

async def fetch_store_products(domain: str) -> List[Dict]:
    """Holt alle Produkte eines Shopify Stores via /products.json (public endpoint)."""
    domain = domain.strip().rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    url = f"{domain}/products.json?limit=250"
    products = []
    try:
        async with _session(25) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    log.debug("Store %s → HTTP %s", domain, r.status)
                    return []
                data = await r.json(content_type=None)
                for p in data.get("products", []):
                    pid   = str(p.get("id", ""))
                    title = p.get("title", "")
                    handle = p.get("handle", "")
                    variants = p.get("variants", [])
                    # Produkt gilt als OOS wenn ALLE Varianten leer sind
                    total_inventory = sum(
                        v.get("inventory_quantity", 1) for v in variants
                    )
                    in_stock = total_inventory > 0 or not any(
                        v.get("inventory_management") for v in variants
                    )
                    price = float(variants[0].get("price", 0)) if variants else 0.0
                    products.append({
                        "product_id": pid,
                        "title":      title,
                        "url":        f"{domain}/products/{handle}",
                        "price":      price,
                        "in_stock":   in_stock,
                    })
    except Exception as e:
        log.warning("fetch_store_products(%s): %s", domain, e)
    return products


# ── OOS Change Detection ──────────────────────────────────────────────────────

async def check_target(domain: str) -> List[Dict]:
    """Prüft einen Store und gibt OOS-Änderungen zurück."""
    products = await fetch_store_products(domain)
    if not products:
        return []

    now    = int(time.time())
    events = []

    with _db() as conn:
        for p in products:
            pid      = p["product_id"]
            in_stock = 1 if p["in_stock"] else 0

            existing = conn.execute(
                "SELECT in_stock, alerted FROM sniper_products WHERE domain=? AND product_id=?",
                (domain, pid)
            ).fetchone()

            if existing is None:
                # Neu — nur eintragen, kein Alert
                conn.execute(
                    """INSERT OR IGNORE INTO sniper_products
                       (domain, product_id, title, url, price, in_stock, last_check)
                       VALUES (?,?,?,?,?,?,?)""",
                    (domain, pid, p["title"], p["url"], p["price"], in_stock, now)
                )
            else:
                was_in_stock = existing["in_stock"]
                alerted      = existing["alerted"]

                if was_in_stock == 1 and in_stock == 0:
                    # WURDE OOS! 🎯
                    conn.execute(
                        "UPDATE sniper_products SET in_stock=0, oos_since=?, alerted=0, last_check=? WHERE domain=? AND product_id=?",
                        (now, now, domain, pid)
                    )
                    events.append({"type": "went_oos", **p, "domain": domain})

                elif was_in_stock == 0 and in_stock == 1:
                    # Wieder verfügbar
                    conn.execute(
                        "UPDATE sniper_products SET in_stock=1, back_since=?, last_check=? WHERE domain=? AND product_id=?",
                        (now, now, domain, pid)
                    )
                    events.append({"type": "back_in_stock", **p, "domain": domain})
                else:
                    conn.execute(
                        "UPDATE sniper_products SET last_check=? WHERE domain=? AND product_id=?",
                        (now, domain, pid)
                    )
    return events


# ── AI Ad-Empfehlung ──────────────────────────────────────────────────────────

async def generate_oos_opportunity(product_title: str, competitor_url: str) -> str:
    prompt = f"""Ein Konkurrent hat dieses Produkt auf LAGER VERGRIFFEN: "{product_title}"
URL: {competitor_url}

Schreibe in 3 Sätzen:
1. Den besten Google Ads Headline (max 30 Zeichen) um deren Traffic abzufangen
2. Die beste Facebook Ad Description (max 90 Zeichen) mit Urgency
3. Den wichtigsten SEO-Keyword für diesen Moment

Format: Headline: ... | FB: ... | SEO: ..."""

    if _anthropic():
        try:
            async with _session(20) as s:
                async with s.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200,
                          "messages": [{"role": "user", "content": prompt}]}
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d.get("content", [{}])[0].get("text", "")
        except Exception as e:
            log.debug("AI error: %s", e)
    return f'Headline: "Jetzt verfügbar!" | FB: "Alle anderen ausverkauft? Bei uns sofort lieferbar!" | SEO: {product_title.split()[0]} kaufen'


# ── Alert senden ──────────────────────────────────────────────────────────────

async def send_oos_alert(event: Dict):
    title   = event.get("title", "Unbekannt")
    domain  = event.get("domain", "")
    url     = event.get("url", "")
    price   = event.get("price", 0)
    ev_type = event.get("type", "")

    if ev_type == "went_oos":
        ad_tip = await generate_oos_opportunity(title, url)
        msg = f"""🎯 <b>OOS SNIPER — ANGRIFF JETZT!</b>

🔴 Konkurrent AUSVERKAUFT: <b>{title}</b>
🏪 Store: {domain}
💰 Ihr Preis war: €{price:.2f}
🔗 {url}

<b>📣 Deine Chance (KI-generiert):</b>
{ad_tip}

⚡ <i>Schalte jetzt Ads / erhöhe deinen Preis solange sie OOS sind!</i>"""

        await _tg(msg)
        with _db() as conn:
            conn.execute(
                "INSERT INTO sniper_events (domain, product_id, title, event_type, message, created_at) VALUES (?,?,?,?,?,?)",
                (domain, event.get("product_id",""), title, "went_oos", msg, int(time.time()))
            )
            conn.execute(
                "UPDATE sniper_products SET alerted=1 WHERE domain=? AND product_id=?",
                (domain, event.get("product_id",""))
            )

    elif ev_type == "back_in_stock":
        msg = f"""✅ <b>OOS Sniper:</b> Konkurrent wieder am Lager
📦 {title}
🏪 {domain}
<i>Ihr Traffic-Steal Fenster schließt sich!</i>"""
        await _tg(msg)


# ── Haupt-Scan ────────────────────────────────────────────────────────────────

async def run_scan(targets: List[str] = None) -> Dict:
    init_db()
    if targets is None:
        targets = _get_active_targets()
    if not targets:
        return {"ok": True, "message": "Keine Targets konfiguriert", "events": []}

    all_events = []
    for domain in targets:
        events = await check_target(domain)
        for ev in events:
            await send_oos_alert(ev)
        all_events.extend(events)
        await asyncio.sleep(0.5)

    oos_count = sum(1 for e in all_events if e["type"] == "went_oos")
    return {
        "ok":          True,
        "targets":     len(targets),
        "events":      len(all_events),
        "oos_events":  oos_count,
        "scanned_at":  datetime.now(timezone.utc).isoformat()
    }


def _get_active_targets() -> List[str]:
    init_db()
    with _db() as conn:
        rows = conn.execute("SELECT domain FROM sniper_targets WHERE active=1").fetchall()
    result = [r["domain"] for r in rows]
    if not result:
        result = DEFAULT_TARGETS
    return result


def add_target(domain: str, label: str = "") -> Dict:
    init_db()
    domain = domain.strip().lower().replace("https://","").replace("http://","").rstrip("/")
    try:
        with _db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sniper_targets (domain, label, active, added_at) VALUES (?,?,1,?)",
                (domain, label or domain, int(time.time()))
            )
        return {"ok": True, "domain": domain}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_status() -> Dict:
    init_db()
    with _db() as conn:
        targets   = conn.execute("SELECT COUNT(*) FROM sniper_targets WHERE active=1").fetchone()[0]
        tracked   = conn.execute("SELECT COUNT(*) FROM sniper_products").fetchone()[0]
        oos_now   = conn.execute("SELECT COUNT(*) FROM sniper_products WHERE in_stock=0").fetchone()[0]
        events_7d = conn.execute(
            "SELECT COUNT(*) FROM sniper_events WHERE created_at > ?",
            (int(time.time()) - 604800,)
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT domain, title, event_type, created_at FROM sniper_events ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
    return {
        "ok":         True,
        "targets":    targets,
        "tracked":    tracked,
        "oos_now":    oos_now,
        "events_7d":  events_7d,
        "recent":     [dict(r) for r in recent]
    }


init_db()
