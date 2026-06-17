#!/usr/bin/env python3
"""
Flash sale restore script.
Called by cron at 14:10 UTC 2026-06-18 to restore original prices.
Also sends Telegram confirmation.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from modules.shopify_revenue_engine import restore_flash_sale

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("FlashSaleRestore")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        log.warning("No Telegram credentials — skipping notification")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        if r.status_code == 200:
            log.info("Telegram notification sent")
        else:
            log.error(f"Telegram error {r.status_code}: {r.text[:100]}")


async def main() -> None:
    log.info("Starting flash sale restore...")
    result = await restore_flash_sale()
    log.info(f"Restore result: {result}")

    if result.get("ok"):
        n = result.get("variants_restored", 0)
        msg = (
            f"✅ <b>Flash Sale Restore Complete</b>\n"
            f"Restored {n} variants to original prices.\n"
            f"Flash sale ended. Normal pricing active."
        )
    else:
        err = result.get("error", "unknown error")
        msg = f"⚠️ <b>Flash Sale Restore</b>\n{err}"

    await send_telegram(msg)
    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
