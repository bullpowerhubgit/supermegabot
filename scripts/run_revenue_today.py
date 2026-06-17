#!/usr/bin/env python3
"""
Revenue Today — Flash Sale + Cart Recovery + Performance Report
Runs standalone: python3 scripts/run_revenue_today.py
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Load .env from supermegabot root
_root = Path(__file__).parent.parent
_env_file = _root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Add supermegabot root to path so imports work
sys.path.insert(0, str(_root))


async def main():
    print(f"\n{'='*60}")
    print(f"  REVENUE TODAY — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    from modules.shopify_revenue_engine import (
        get_revenue_summary,
        get_product_performance,
        create_flash_sale,
        get_abandoned_carts,
        recover_all_carts,
        auto_publish_drafts,
    )

    # 1. Revenue Summary (baseline)
    print("📊 [1/5] Revenue Summary...")
    rev = await get_revenue_summary()
    if "error" in rev:
        print(f"   ⚠️  Warning: {rev['error']}")
    else:
        print(f"   Today:      {rev.get('currency','EUR')} {rev.get('today', 0)}")
        print(f"   Last 7d:    {rev.get('currency','EUR')} {rev.get('last_7_days', 0)}")
        print(f"   Last 30d:   {rev.get('currency','EUR')} {rev.get('last_30_days', 0)}")
        print(f"   Orders:     {rev.get('total_orders', 0)} total / {rev.get('open_orders', 0)} open")

    # 2. Product Performance — find slow movers for flash sale
    print("\n🔍 [2/5] Product Performance Analysis (last 30d)...")
    perf = await get_product_performance(30)
    total_products = perf.get("total_products", 0)
    slow_movers = perf.get("slow_movers", [])
    zero_sellers = perf.get("zero_sellers", [])
    top_sellers = perf.get("top_sellers", [])

    print(f"   Total products: {total_products}")
    print(f"   Top sellers:    {len(top_sellers)}")
    print(f"   Slow movers:    {len(slow_movers)}")
    print(f"   Zero sellers:   {len(zero_sellers)}")

    if top_sellers:
        print("   Top 3:")
        for p in top_sellers[:3]:
            print(f"     - {p['title'][:40]} ({p['units_sold']} units)")

    # 3. Auto-publish any draft products
    print("\n🚀 [3/5] Auto-publishing Draft Products...")
    pub = await auto_publish_drafts()
    print(f"   Drafts found: {pub.get('drafts_found', 0)} | Published: {pub.get('published', 0)}")

    # 4. Flash Sale on slow movers / zero sellers
    print("\n⚡ [4/5] Flash Sale -20% on Slow/Zero Movers...")
    # Target: zero sellers first (up to 5), then slow movers
    target_ids = [p["product_id"] for p in zero_sellers[:5]]
    if len(target_ids) < 5:
        target_ids += [p["product_id"] for p in slow_movers[:5 - len(target_ids)]]

    if target_ids:
        flash = await create_flash_sale(
            discount_pct=20,
            title="Flash Sale Today -20%",
            duration_hours=24,
            product_ids=target_ids,
        )
        print(f"   Flash Sale: {flash.get('title')}")
        print(f"   Variants updated: {flash.get('variants_updated', 0)}")
        print(f"   Duration: {flash.get('duration_hours')}h")
        print(f"   Restore via: {flash.get('restore_via')}")
    else:
        print("   ⚠️  No slow/zero-seller products found to target.")
        # Fall back: flash sale on all products
        flash = await create_flash_sale(discount_pct=20, title="Flash Sale Today -20%", duration_hours=24)
        print(f"   Fallback all-products flash: {flash.get('variants_updated', 0)} variants updated")

    # 5. Cart Recovery
    print("\n🛒 [5/5] Abandoned Cart Recovery...")
    carts = await get_abandoned_carts(24)
    print(f"   Abandoned carts (24h): {len(carts)}")
    if carts:
        for c in carts[:3]:
            print(f"     - {c.get('email','?')} | {c.get('currency','')} {c.get('total','?')} | {c.get('recovery_url','')[:60]}...")
        recovery = await recover_all_carts(24)
        print(f"   Klaviyo recovery events sent: {recovery.get('recovery_sent', 0)}/{recovery.get('carts_found', 0)}")
    else:
        print("   No abandoned carts in last 24h.")

    print(f"\n{'='*60}")
    print("  DONE — Revenue engine running for today.")
    print(f"  Flash sale active for 24h. Restore: POST /api/revenue/flash-sale/restore")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
