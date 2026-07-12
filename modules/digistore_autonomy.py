#!/usr/bin/env python3
"""
Digistore24 Autonomy — Products, transactions, affiliate blast, revenue report.
API: https://www.digistore24.com/api/call/{method}
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timedelta, timezone

import aiohttp

log = logging.getLogger("DigistoreAutonomy")

_DEFAULT_PRIMARY = "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N"


def _resolve_key(purpose: str = "default") -> str:
    chains = {
        "transactions": ("DIGISTORE24_API_KEY_FULL", "DIGISTORE24_API_KEY", "DIGISTORE24_API_KEY_READONLY"),
        "default": ("DIGISTORE24_API_KEY", "DIGISTORE24_API_KEY_READONLY"),
    }
    for k in chains.get(purpose, chains["default"]):
        v = os.getenv(k, "")
        if v and "-" in v:
            return v
    return os.getenv("DIGISTORE24_API_KEY", _DEFAULT_PRIMARY)


API_KEY = _resolve_key("default")
AFFILIATE_ID = os.getenv("DIGISTORE24_AFFILIATE_ID", os.getenv("DIGISTORE24_USER_ID", "user37405262"))
BASE = "https://www.digistore24.com/api/call"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


async def _ai(prompt: str, max_tokens: int = 400) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _ds24_get(method: str, extra_params: dict = None, purpose: str = "default") -> dict:
    """Call Digistore24 API with correct auth (X-DS-API-KEY header, /JSON/ suffix)."""
    url = f"{BASE}/{method}/JSON/"
    headers = {"X-DS-API-KEY": _resolve_key(purpose)}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=extra_params or {}, headers=headers,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                return await r.json(content_type=None)
    except Exception as e:
        log.warning("DS24 API %s error: %s", method, e)
        return {"result": "error", "message": str(e)}


async def get_products() -> list:
    """GET Digistore24 products list."""
    data = await _ds24_get("listProducts")
    if data.get("result") == "success":
        return data.get("data", {}).get("products", [])
    log.warning("DS24 listProducts: %s", data.get("message", ""))
    return []


async def get_recent_transactions(days: int = 7) -> list:
    """GET recent Digistore24 transactions."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    data = await _ds24_get("listTransactions", {"from": since}, purpose="transactions")
    if data.get("result") == "success":
        return data.get("data", {}).get("transactions", [])
    log.warning("DS24 listTransactions: %s", data.get("message", ""))
    return []


def create_affiliate_links(product_ids: list) -> list:
    """Create Digistore24 affiliate links."""
    links = []
    for pid in product_ids:
        links.append({
            "product_id": pid,
            "url": f"https://www.digistore24.com/redir/{pid}/{AFFILIATE_ID}",
        })
    return links


async def blast_best_products(count: int = 3) -> dict:
    """Get products → pick best → AI content → BrutusCore blast."""
    products = await get_products()
    if not products:
        # Use known product IDs as fallback
        products = [
            {"product_id": "668035", "name": "AI Income Machine – 90-Day Blueprint", "price": "37",
             "affiliate_link": os.getenv("DS24_AFFILIATE_LINK", "https://www.checkout-ds24.com/product/668035")},
            {"product_id": "704677", "name": "SuperMegaBot KI-Automation System", "price": "97",
             "affiliate_link": os.getenv("DS24_AFFILIATE_LINK_2", "https://www.checkout-ds24.com/product/704677")},
        ]

    # Sort by EPC if available, else random
    products_with_epc = [p for p in products if p.get("stats", {}).get("epc")]
    if products_with_epc:
        products_with_epc.sort(key=lambda x: float(x.get("stats", {}).get("epc", 0)), reverse=True)
        top = products_with_epc[:count]
    else:
        top = random.sample(products, min(count, len(products)))

    blasted = 0
    for p in top:
        try:
            pid = str(p.get("product_id") or p.get("id", ""))
            name = p.get("name") or p.get("title", "Digital Product")
            price = p.get("price") or p.get("amount", "")
            aff_link = f"https://www.digistore24.com/redir/{pid}/{AFFILIATE_ID}"

            prompt = f"""Überzeugender deutscher Affiliate-Text (3-4 Sätze) für Digistore24-Produkt:
Name: "{name}"
Preis: €{price}
Affiliate-Link: {aff_link}

Hebe Hauptvorteil hervor. Ende mit "Jetzt sichern ➜ {aff_link}"."""
            content = await _ai(prompt, max_tokens=200)
            if not content:
                content = f"{name} — Jetzt als digitales Produkt sichern!\n➜ {aff_link}"

            from modules.brutus_core import fire
            await fire(
                f"DS24: {name[:60]}",
                content,
                link=aff_link,
                channels=["telegram", "slack", "mailchimp", "klaviyo", "linkedin"],
            )
            blasted += 1
            log.info("DS24 blast: %s", name[:60])
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("DS24 blast error: %s", e)

    return {"ok": True, "blasted": blasted, "products_found": len(products)}


async def send_revenue_report() -> dict:
    """Calculate revenue from recent transactions → Telegram + Slack."""
    transactions = await get_recent_transactions(days=7)
    total = 0.0
    count = len(transactions)
    for t in transactions:
        try:
            total += float(t.get("amount") or t.get("total_amount") or 0)
        except (ValueError, TypeError):
            pass

    msg = (f"📊 Digistore24 — 7-Tage-Report\n\n"
           f"Transaktionen: {count}\n"
           f"Umsatz: €{total:.2f}\n"
           f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    # Telegram
    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT, "text": msg},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            log.warning("Telegram report error: %s", e)

    # Slack
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if slack_url:
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(slack_url, json={"text": msg},
                             timeout=aiohttp.ClientTimeout(total=10))
        except Exception as e:
            log.debug("Slack report: %s", e)

    log.info("DS24 revenue report sent: €%.2f from %d transactions", total, count)
    return {"ok": True, "total": total, "transactions": count}


async def run_digistore_cycle() -> dict:
    """Scheduler entry point."""
    blast = await blast_best_products(count=2)
    report = await send_revenue_report()
    return {"ok": True, "blast": blast, "report": report}
