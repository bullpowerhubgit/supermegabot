"""
Shopify Bulk Activator
=======================
Aktiviert alle archivierten Produkte (status: archived → active).
Problem: 17.452 Produkte wurden beim Import nicht publiziert.

Strategie:
- Holt archived Produkte in 50er-Batches via REST API
- Aktiviert jedes mit status=active, published_at=now
- Rate-Limit: 0.6s Delay → ~1.6 req/s (unter 2 req/s Shopify-Limit)
- Speichert Fortschritt in State-File → restart-safe
- Sendet Telegram-Progress alle 500 aktivierten Produkte
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("ShopifyBulkActivator")

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOP_TOKEN  = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-10")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = DATA_DIR / "shopify_bulk_activator.json"

_DELAY     = 0.6   # 1.6 req/s
_BATCH     = 50    # Produkte pro Fetch
_TG_EVERY  = 500   # Telegram-Update alle N aktivierten Produkte


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"activated": 0, "last_id": 0, "done": False}


def _save_state(s: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, default=str))


def _base() -> str:
    return f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}"


def _hdrs() -> dict:
    return {"X-Shopify-Access-Token": SHOP_TOKEN, "Content-Type": "application/json"}


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def get_counts() -> dict:
    """Zählt Produkte nach Status."""
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {}
    result = {}
    async with aiohttp.ClientSession() as s:
        for status in ("active", "archived", "draft"):
            try:
                async with s.get(
                    f"{_base()}/products/count.json",
                    headers=_hdrs(),
                    params={"status": status},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        result[status] = (await r.json()).get("count", 0)
            except Exception:
                pass
    return result


async def run_activation_batch(max_per_run: int = 200) -> dict:
    """
    Aktiviert bis zu max_per_run archivierte Produkte.
    Kann mehrfach aufgerufen werden — setzt beim letzten seit_id fort.
    """
    if not SHOP_DOMAIN or not SHOP_TOKEN:
        return {"ok": False, "error": "Shopify credentials fehlen"}

    state = _load_state()
    if state.get("done"):
        counts = await get_counts()
        return {"ok": True, "status": "bereits_abgeschlossen", "counts": counts}

    last_id    = state.get("last_id", 0)
    total_done = state.get("activated", 0)
    activated  = 0
    errors     = 0
    now_iso    = datetime.now(timezone.utc).isoformat()

    log.info("Bulk Activator START: last_id=%s total_done=%s", last_id, total_done)

    async with aiohttp.ClientSession() as s:
        while activated < max_per_run:
            # Fetch batch of archived products
            try:
                async with s.get(
                    f"{_base()}/products.json",
                    headers=_hdrs(),
                    params={"status": "archived", "limit": _BATCH, "since_id": last_id,
                            "fields": "id,title,status"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 429:
                        log.warning("Rate limit 429 — sleep 10s")
                        await asyncio.sleep(10)
                        continue
                    if r.status != 200:
                        log.error("fetch archived: status=%s", r.status)
                        break
                    products = (await r.json()).get("products", [])
            except Exception as e:
                log.error("fetch archived exception: %s", e)
                break

            if not products:
                state["done"] = True
                log.info("Alle archivierten Produkte aktiviert!")
                await _tg(
                    f"✅ Shopify Bulk Activator FERTIG!\n"
                    f"Gesamt aktiviert: {total_done + activated}\n"
                    f"Alle Produkte sind jetzt sichtbar."
                )
                break

            for p in products:
                pid = p.get("id")
                if not pid:
                    continue
                last_id = pid

                # Produkt aktivieren
                try:
                    async with s.put(
                        f"{_base()}/products/{pid}.json",
                        headers=_hdrs(),
                        json={"product": {
                            "id": pid,
                            "status": "active",
                            "published_at": now_iso,
                        }},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r2:
                        if r2.status == 429:
                            await asyncio.sleep(10)
                            # Retry
                            async with s.put(
                                f"{_base()}/products/{pid}.json",
                                headers=_hdrs(),
                                json={"product": {"id": pid, "status": "active", "published_at": now_iso}},
                                timeout=aiohttp.ClientTimeout(total=10),
                            ) as r3:
                                if r3.status in (200, 201):
                                    activated += 1
                                else:
                                    errors += 1
                        elif r2.status in (200, 201):
                            activated += 1
                        else:
                            errors += 1
                except Exception as e:
                    log.warning("activate %s: %s", pid, e)
                    errors += 1

                await asyncio.sleep(_DELAY)

                # Telegram Progress Update
                if (total_done + activated) % _TG_EVERY == 0 and activated > 0:
                    await _tg(
                        f"🔄 Shopify Bulk Activator läuft...\n"
                        f"Aktiviert: {total_done + activated} Produkte\n"
                        f"Fehler: {errors}"
                    )

                if activated >= max_per_run:
                    break

    state["activated"] = total_done + activated
    state["last_id"]   = last_id
    _save_state(state)

    result = {
        "ok": True,
        "activated_this_run": activated,
        "total_activated": state["activated"],
        "errors": errors,
        "done": state.get("done", False),
        "last_id": last_id,
    }
    log.info("Bulk Activator DONE: %s", result)
    return result


async def get_status() -> dict:
    state = _load_state()
    counts = await get_counts()
    return {
        "ok": True,
        "module": "Shopify Bulk Activator",
        "state": state,
        "counts": counts,
    }
