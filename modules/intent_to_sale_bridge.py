#!/usr/bin/env python3
"""
Intent-to-Sale Bridge — Welteinzigartiger KI-Verkäufer der niemals schläft.

Scannt Telegram-Gruppen auf semantische Kaufabsicht (nicht nur Keywords),
matcht Produkte aus ineedit.com.co live, antwortet in 60s hilfreich und natürlich.

Anti-Spam: max 1 Antwort pro Gruppe alle 15 Minuten, nur bei Konfidenz > 0.75.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any

log = logging.getLogger("IntentBridge")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "intent_bridge.db"

SHOPIFY_DOMAIN  = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "autopilot-store-suite-fmbka.myshopify.com")
SHOPIFY_TOKEN   = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION = lambda: os.getenv("SHOPIFY_API_VERSION", "2024-01")
SHOPIFY_STORE   = lambda: os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")
TELEGRAM_TOKEN  = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")

COOLDOWN_SECS    = 900   # 15 min between responses per group
MIN_CONFIDENCE   = 0.75  # threshold for buying-intent detection
MAX_PRODUCTS     = 3     # products to suggest per response

# Category → Shopify search terms mapping (German e-commerce focus)
_CATEGORY_TERMS: dict[str, list[str]] = {
    "powerstation":    ["powerstation", "solar", "batterie speicher", "power station"],
    "smart_home":      ["smart home", "zigbee", "wlan steckdose", "alexa", "google home"],
    "gadgets":         ["gadget", "elektronik", "tech", "smart"],
    "audio":           ["kopfhörer", "lautsprecher", "bluetooth audio", "headphone"],
    "roboter":         ["saugroboter", "robot", "mähroboter"],
    "kamera":          ["kamera", "dashcam", "überwachung", "security cam"],
    "wearables":       ["smartwatch", "fitnesstracker", "wearable"],
    "outdoor":         ["camping", "outdoor", "solar panel", "powerbank"],
    "auto_tech":       ["auto gadget", "kfz", "dashcam", "autoladegerät"],
    "home_office":     ["monitor", "tastatur", "webcam", "schreibtisch"],
    "general":         ["smart", "tech", "elektronik"],
}


# ─────────────────────────────────────────────────────────────────────────────
# DB Setup
# ─────────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS ib_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER NOT NULL,
                chat_id     TEXT,
                user_id     TEXT,
                username    TEXT,
                message     TEXT,
                intent      TEXT,
                confidence  REAL,
                category    TEXT,
                product_url TEXT,
                responded   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ib_cooldowns (
                chat_id     TEXT PRIMARY KEY,
                last_reply  INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ib_clicks (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      INTEGER,
                ref     TEXT,
                chat_id TEXT
            );
            CREATE INDEX IF NOT EXISTS ib_events_ts ON ib_events(ts);
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────────────────────────────────────────

def can_respond(chat_id: str) -> bool:
    with _db() as con:
        row = con.execute(
            "SELECT last_reply FROM ib_cooldowns WHERE chat_id=?", (chat_id,)
        ).fetchone()
    if not row:
        return True
    return (time.time() - row["last_reply"]) > COOLDOWN_SECS


def mark_responded(chat_id: str) -> None:
    with _db() as con:
        con.execute(
            "INSERT OR REPLACE INTO ib_cooldowns(chat_id, last_reply) VALUES(?,?)",
            (chat_id, int(time.time())),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Intent classification via AI
# ─────────────────────────────────────────────────────────────────────────────

async def classify_intent(text: str) -> dict[str, Any]:
    """Returns {is_buying, confidence, category, keywords, language}."""
    try:
        from modules.ai_client import ai_complete
    except ImportError:
        return {"is_buying": False, "confidence": 0.0, "category": "general", "keywords": [], "language": "de"}

    prompt = f"""Analysiere diese Nachricht und erkenne Kaufabsicht.

Nachricht: "{text}"

Antworte NUR mit validem JSON (kein Markdown, keine Erklärung):
{{
  "is_buying": true/false,
  "confidence": 0.0-1.0,
  "category": "powerstation|smart_home|gadgets|audio|roboter|kamera|wearables|outdoor|auto_tech|home_office|general",
  "keywords": ["keyword1", "keyword2"],
  "language": "de|en|other"
}}

Kaufabsicht liegt vor wenn jemand:
- fragt wo man etwas kaufen kann
- nach Empfehlungen/Erfahrungen für ein Produkt fragt
- sagt dass er etwas sucht/braucht
- Preise vergleicht oder ein konkretes Produkt recherchiert
- NICHT: allgemeine Fragen, Probleme mit bestehendem Gerät, Tech-Diskussionen ohne Kaufinteresse"""

    system = "Du bist ein Intent-Classifier. Antworte ausschließlich mit JSON."
    raw = await ai_complete(prompt, system=system, model_hint="fast", max_tokens=200)

    try:
        # strip potential markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        result = json.loads(cleaned.strip())
        result.setdefault("is_buying", False)
        result.setdefault("confidence", 0.0)
        result.setdefault("category", "general")
        result.setdefault("keywords", [])
        result.setdefault("language", "de")
        return result
    except Exception:
        log.debug("Intent parse failed: %s", raw[:200])
        return {"is_buying": False, "confidence": 0.0, "category": "general", "keywords": [], "language": "de"}


# ─────────────────────────────────────────────────────────────────────────────
# Shopify product search
# ─────────────────────────────────────────────────────────────────────────────

async def search_products(category: str, keywords: list[str]) -> list[dict]:
    """Returns up to MAX_PRODUCTS products from ineedit.com.co."""
    import aiohttp

    domain  = SHOPIFY_DOMAIN()
    token   = SHOPIFY_TOKEN()
    version = SHOPIFY_VERSION()

    if not domain or not token:
        return []

    found: list[dict] = []
    search_terms = (keywords[:2] if keywords else []) + _CATEGORY_TERMS.get(category, ["smart"])

    seen_ids: set = set()
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as sess:
        for term in search_terms[:3]:
            if len(found) >= MAX_PRODUCTS:
                break
            q = urllib.parse.quote(term)
            url = f"https://{domain}/admin/api/{version}/products.json?title={q}&limit=5&status=active&fields=id,title,handle,variants,images,product_type"
            try:
                async with sess.get(url) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
                    for p in data.get("products", []):
                        pid = p.get("id")
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        price = ""
                        variants = p.get("variants", [])
                        if variants:
                            price = variants[0].get("price", "")
                        image = ""
                        images = p.get("images", [])
                        if images:
                            image = images[0].get("src", "")
                        handle = p.get("handle", "")
                        store_url = SHOPIFY_STORE().rstrip("/")
                        product_url = f"{store_url}/products/{handle}"
                        found.append({
                            "title": p.get("title", ""),
                            "url": product_url,
                            "price": price,
                            "image": image,
                            "category": p.get("product_type", ""),
                        })
                        if len(found) >= MAX_PRODUCTS:
                            break
            except Exception as e:
                log.debug("Shopify search error for '%s': %s", term, e)

    return found[:MAX_PRODUCTS]


# ─────────────────────────────────────────────────────────────────────────────
# Tracking URL
# ─────────────────────────────────────────────────────────────────────────────

def make_tracking_url(product_url: str, chat_id: str, source: str = "tg_group") -> str:
    sep = "&" if "?" in product_url else "?"
    ref = urllib.parse.quote(f"itb_{chat_id[:8]}")
    return f"{product_url}{sep}utm_source={source}&utm_medium=intent_bridge&utm_campaign=itb&ref={ref}"


# ─────────────────────────────────────────────────────────────────────────────
# Response generation
# ─────────────────────────────────────────────────────────────────────────────

async def generate_response(original_text: str, products: list[dict], language: str) -> str:
    """Generate a helpful, natural, non-spammy reply with product links."""
    try:
        from modules.ai_client import ai_complete
    except ImportError:
        return _fallback_response(products, language)

    products_str = "\n".join(
        f"- {p['title']} | {p['price']}€ | {p['url']}" for p in products
    )

    if language == "de":
        prompt = f"""Jemand hat in einer Telegram-Gruppe geschrieben:
"{original_text}"

Du bist ein freundlicher Nutzer (kein Bot) der hilfreiche Empfehlungen gibt.
Schreibe eine kurze, natürliche, hilfreiche Antwort (max 3 Sätze) die:
1. Kurz auf die Frage eingeht
2. Diese Produkte als Tipp erwähnt (keine Werbung, kein Spam-Ton):
{products_str}
3. Auf Deutsch ist
4. Nicht roboterhaft klingt
5. KEIN "Als KI" oder "Ich bin ein Bot" enthält

Antworte NUR mit dem Nachrichtentext, ohne Anführungszeichen."""
    else:
        prompt = f"""Someone wrote in a Telegram group:
"{original_text}"

You are a helpful community member (not a bot). Write a short, natural reply (max 3 sentences) that:
1. Briefly addresses the question
2. Mentions these products as a helpful tip (not spam):
{products_str}
3. Is in English
4. Doesn't sound robotic

Reply ONLY with the message text, no quotes."""

    system = "Du bist ein hilfsbereiter Community-Nutzer. Antworte kurz und natürlich."
    response = await ai_complete(prompt, system=system, model_hint="fast", max_tokens=300)
    return response.strip() if response.strip() else _fallback_response(products, language)


def _fallback_response(products: list[dict], language: str) -> str:
    if not products:
        return ""
    links = " | ".join(f"{p['title']} → {p['url']}" for p in products[:2])
    if language == "de":
        return f"Schau mal hier, könnte passen: {links}"
    return f"Check this out, might help: {links}"


# ─────────────────────────────────────────────────────────────────────────────
# Telegram send
# ─────────────────────────────────────────────────────────────────────────────

async def send_telegram_reply(chat_id: str, text: str, reply_to_message_id: int | None = None) -> bool:
    import aiohttp
    token = TELEGRAM_TOKEN()
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
        "parse_mode": "HTML",
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
            async with sess.post(url, json=payload) as r:
                ok = r.status == 200
                if not ok:
                    body = await r.text()
                    log.warning("Telegram send failed %s: %s", r.status, body[:200])
                return ok
    except Exception as e:
        log.warning("Telegram send error: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Event logging
# ─────────────────────────────────────────────────────────────────────────────

def log_event(chat_id: str, user_id: str, username: str, message: str,
              intent_result: dict, products: list[dict], responded: bool) -> None:
    product_url = products[0]["url"] if products else ""
    with _db() as con:
        con.execute("""
            INSERT INTO ib_events(ts, chat_id, user_id, username, message, intent,
                                  confidence, category, product_url, responded)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            int(time.time()), chat_id, user_id, username,
            message[:500],
            intent_result.get("is_buying", False),
            intent_result.get("confidence", 0.0),
            intent_result.get("category", ""),
            product_url,
            1 if responded else 0,
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def process_group_message(
    text: str,
    chat_id: str,
    user_id: str = "",
    username: str = "",
    message_id: int | None = None,
    chat_type: str = "group",
) -> bool:
    """
    Analyze a Telegram group message for buying intent and respond if warranted.
    Returns True if a response was sent.
    """
    if not text or len(text) < 10:
        return False

    # Skip own bot messages (bot commands / responses)
    if text.startswith("/"):
        return False

    # Rate limit
    if not can_respond(chat_id):
        return False

    # Classify intent
    intent = await classify_intent(text)

    if not intent.get("is_buying") or intent.get("confidence", 0) < MIN_CONFIDENCE:
        log.debug("[IntentBridge] No intent in chat=%s (conf=%.2f)", chat_id, intent.get("confidence", 0))
        return False

    log.info("[IntentBridge] INTENT DETECTED chat=%s conf=%.2f cat=%s",
             chat_id, intent["confidence"], intent.get("category"))

    # Find products
    products = await search_products(intent.get("category", "general"), intent.get("keywords", []))
    if not products:
        log.info("[IntentBridge] No products found for category=%s", intent.get("category"))
        return False

    # Add tracking URLs
    for p in products:
        p["url"] = make_tracking_url(p["url"], chat_id)

    # Generate response
    response_text = await generate_response(text, products, intent.get("language", "de"))
    if not response_text:
        return False

    # Send
    sent = await send_telegram_reply(chat_id, response_text, reply_to_message_id=message_id)

    if sent:
        mark_responded(chat_id)
        log.info("[IntentBridge] RESPONDED to chat=%s — %s", chat_id, products[0]["title"])

    # Log event always (even if send failed)
    log_event(chat_id, user_id, username, text, intent, products, responded=sent)

    return sent


# ─────────────────────────────────────────────────────────────────────────────
# Stats for dashboard
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    try:
        with _db() as con:
            total      = con.execute("SELECT COUNT(*) FROM ib_events").fetchone()[0]
            responded  = con.execute("SELECT COUNT(*) FROM ib_events WHERE responded=1").fetchone()[0]
            today_ts   = int(time.time()) - 86400
            today      = con.execute("SELECT COUNT(*) FROM ib_events WHERE ts>? AND responded=1", (today_ts,)).fetchone()[0]
            recent     = con.execute(
                "SELECT ts, chat_id, username, message, confidence, category, product_url, responded "
                "FROM ib_events ORDER BY ts DESC LIMIT 20"
            ).fetchall()
            return {
                "total_detected": total,
                "total_responded": responded,
                "responded_today": today,
                "response_rate": round(responded / total * 100, 1) if total else 0,
                "recent_events": [dict(r) for r in recent],
            }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled reporting task (called by automation_scheduler)
# ─────────────────────────────────────────────────────────────────────────────

async def scheduled_daily_report() -> str:
    """Send daily Intent Bridge stats to Telegram admin chat."""
    import aiohttp

    stats = get_stats()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return "No TELEGRAM_CHAT_ID"

    msg = (
        f"📊 <b>Intent Bridge Report</b>\n"
        f"Gesamt erkannt: {stats.get('total_detected', 0)}\n"
        f"Geantwortet: {stats.get('total_responded', 0)} ({stats.get('response_rate', 0)}%)\n"
        f"Heute: {stats.get('responded_today', 0)} Antworten\n"
        f"Status: ✅ Aktiv"
    )

    token = TELEGRAM_TOKEN()
    if token:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession() as sess:
            await sess.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})

    return f"Report sent: {stats.get('responded_today', 0)} responses today"


# Init DB on import
try:
    init_db()
except Exception as e:
    log.warning("IntentBridge DB init failed: %s", e)
