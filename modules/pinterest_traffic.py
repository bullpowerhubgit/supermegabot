#!/usr/bin/env python3
"""
Pinterest Traffic Engine — Autonomes Pinnen von ineedit.com.co Produkten.
Postet Produktbilder auf relevante Boards: Smart Home, Solar, E-Bike, Gadgets.
Pinterest API v5. Dedup via lokale JSON-Datei.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("PinterestTraffic")

PINTEREST_TOKEN      = os.getenv("PINTEREST_ACCESS_TOKEN", "")
PINTEREST_BASE       = "https://api.pinterest.com/v5"
SHOP_DOMAIN          = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN           = os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOP_VER             = os.getenv("SHOPIFY_API_VERSION", "2026-04")
SHOP_URL             = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")

DATA_DIR  = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DEDUP_FILE = DATA_DIR / "pinterest_posted.json"

BOARDS = [
    "Smart Home Gadgets",
    "Solar & Energie",
    "Smart Home Deutschland",
    "E-Bike & Elektromobilität",
    "Tech Gadgets 2026",
]

BOARD_KEYWORDS = {
    "Smart Home Gadgets":       ["smart", "home", "alexa", "google", "automation", "lamp", "bulb", "plug"],
    "Solar & Energie":          ["solar", "powerstation", "balkon", "power", "energy", "generator", "akku"],
    "Smart Home Deutschland":   ["smarthome", "germany", "deutsch", "haus", "zuhause"],
    "E-Bike & Elektromobilität": ["bike", "elektro", "e-bike", "scooter", "roller"],
    "Tech Gadgets 2026":        ["gadget", "tech", "device", "sensor", "camera", "rgb", "strip"],
}


def _pinterest_headers() -> Dict:
    return {
        "Authorization": f"Bearer {PINTEREST_TOKEN}",
        "Content-Type": "application/json",
    }


def _load_posted() -> set:
    try:
        return set(json.loads(DEDUP_FILE.read_text()))
    except Exception:
        return set()


def _save_posted(posted: set) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(sorted(posted)))


def _best_board_for_product(title: str, tags: List[str]) -> str:
    title_lower = (title + " " + " ".join(tags)).lower()
    for board, keywords in BOARD_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return board
    return "Smart Home Gadgets"


# ── Pinterest API calls ───────────────────────────────────────────────────────

async def get_or_create_board(board_name: str) -> Optional[str]:
    """Return board_id for board_name, creating it if it doesn't exist."""
    if not PINTEREST_TOKEN:
        return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            # List boards
            async with s.get(
                f"{PINTEREST_BASE}/boards",
                headers=_pinterest_headers(),
                params={"page_size": 100},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for board in data.get("items", []):
                        if board.get("name", "").lower() == board_name.lower():
                            return board["id"]

            # Create if not found
            async with s.post(
                f"{PINTEREST_BASE}/boards",
                headers=_pinterest_headers(),
                json={"name": board_name, "description": f"Smart Home & Technik — {board_name}", "privacy": "PUBLIC"},
            ) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    board_id = data.get("id")
                    log.info("Pinterest board created: %s → %s", board_name, board_id)
                    return board_id
                else:
                    body = await r.text()
                    log.warning("Board create %s: %s %s", board_name, r.status, body[:200])
    except Exception as e:
        log.warning("get_or_create_board %s: %s", board_name, e)
    return None


async def create_pin(board_id: str, title: str, description: str, image_url: str, link: str) -> Dict:
    """Create a Pinterest pin."""
    if not PINTEREST_TOKEN or not board_id:
        return {"ok": False, "error": "no token or board_id"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                f"{PINTEREST_BASE}/pins",
                headers=_pinterest_headers(),
                json={
                    "board_id": board_id,
                    "title": title[:100],
                    "description": description[:500],
                    "link": link,
                    "media_source": {
                        "source_type": "image_url",
                        "url": image_url,
                    },
                },
            ) as r:
                data = await r.json(content_type=None)
                ok = r.status in (200, 201)
                if ok:
                    log.info("Pin created: %s | board: %s", data.get("id"), board_id)
                else:
                    log.warning("Pin create error %s: %s", r.status, str(data)[:200])
                return {"ok": ok, "pin_id": data.get("id"), "status": r.status}
    except Exception as e:
        log.warning("create_pin: %s", e)
        return {"ok": False, "error": str(e)}


# ── Shopify product fetch ─────────────────────────────────────────────────────

async def get_shopify_products_with_images(limit: int = 50) -> List[Dict]:
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"https://{SHOP_DOMAIN}/admin/api/{SHOP_VER}/products.json",
                headers={"X-Shopify-Access-Token": SHOP_TOKEN},
                params={
                    "limit": limit,
                    "status": "active",
                    "fields": "id,title,handle,body_html,images,tags,variants,product_type",
                },
            ) as r:
                if r.status == 200:
                    products = (await r.json()).get("products", [])
                    return [p for p in products if p.get("images")]
    except Exception as e:
        log.warning("Shopify fetch: %s", e)
    return []


# ── Main posting cycle ────────────────────────────────────────────────────────

async def run_pinterest_posting_cycle(pins_per_run: int = 10) -> Dict:
    """
    Main cycle: get Shopify products → post to relevant Pinterest boards.
    Deduplicates by product ID so each product is pinned only once.
    """
    if not PINTEREST_TOKEN:
        return {"ok": False, "error": "no PINTEREST_ACCESS_TOKEN"}

    products = await get_shopify_products_with_images(limit=100)
    if not products:
        return {"ok": False, "error": "no Shopify products with images"}

    posted = _load_posted()

    # Pre-create all boards in parallel
    board_ids: Dict[str, str] = {}
    for board_name in BOARDS:
        bid = await get_or_create_board(board_name)
        if bid:
            board_ids[board_name] = bid
        await asyncio.sleep(0.3)

    if not board_ids:
        return {"ok": False, "error": "no Pinterest boards available"}

    pinned = 0
    errors = 0

    for product in products:
        if pinned >= pins_per_run:
            break

        pid = str(product.get("id", ""))
        if pid in posted:
            continue

        images = product.get("images", [])
        if not images:
            continue

        title = product.get("title", "")
        body_html = product.get("body_html", "") or ""
        description_text = re.sub("<[^>]+>", "", body_html)[:200]
        tags = [t.strip() for t in (product.get("tags", "") or "").split(",")]
        handle = product.get("handle", "")
        link = f"{SHOP_URL}/products/{handle}"
        image_url = images[0].get("src", "")

        board_name = _best_board_for_product(title, tags)
        board_id = board_ids.get(board_name, list(board_ids.values())[0])

        pin_title = f"{title} | ineedit.com.co"
        pin_description = f"{description_text}\n\n✅ Kostenloser Versand ab €50 | 30 Tage Rückgabe\n🛒 Jetzt kaufen: {link}"

        result = await create_pin(board_id, pin_title, pin_description, image_url, link)
        if result.get("ok"):
            pinned += 1
            posted.add(pid)
            log.info("Pinned: %s → %s", title[:40], board_name)
        else:
            errors += 1

        await asyncio.sleep(1.0)  # Pinterest rate limit

    _save_posted(posted)
    log.info("Pinterest cycle done: %d pinned, %d errors", pinned, errors)
    return {
        "ok": pinned > 0 or errors == 0,
        "pinned": pinned,
        "errors": errors,
        "boards_used": list(board_ids.keys()),
        "total_posted_ever": len(posted),
    }


async def get_pinterest_status() -> Dict:
    """Status for dashboard."""
    if not PINTEREST_TOKEN:
        return {"ok": False, "error": "no PINTEREST_ACCESS_TOKEN"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{PINTEREST_BASE}/boards", headers=_pinterest_headers(),
                             params={"page_size": 100}) as r:
                if r.status == 200:
                    data = await r.json()
                    boards = data.get("items", [])
                    posted = _load_posted()
                    return {
                        "ok": True,
                        "board_count": len(boards),
                        "boards": [b.get("name") for b in boards],
                        "total_pins_posted": len(posted),
                        "configured": True,
                    }
    except Exception as e:
        log.warning("Pinterest status: %s", e)
    return {"ok": False, "configured": bool(PINTEREST_TOKEN), "error": "API check failed"}
