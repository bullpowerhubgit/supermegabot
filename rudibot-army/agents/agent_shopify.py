#!/usr/bin/env python3
"""🛒 Shopify Agent — Beobachtet Orders, Inventory, meldet Neuigkeiten"""
import sys, os, time, json, urllib.request
sys.path.insert(0, os.path.expanduser("~/supermegabot/rudibot-army/shared"))
from bus import report, notify_telegram, get_env
from learner_mixin import AgentLearner

ID = "shopify"
API_VERSION = "2025-01"


def shopify_req(endpoint):
    token = get_env("SHOPIFY_ADMIN_TOKEN") or get_env("SHOPIFY_SUITE_ACCESS_TOKEN")
    domain = get_env("SHOPIFY_SHOP_DOMAIN") or f"{get_env('SHOPIFY_SHOP') or 'autopilot-store-suite-fmbka'}.myshopify.com"
    if not token:
        return None
    url = f"https://{domain}/admin/api/{API_VERSION}/{endpoint}"
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def run():
    print(f"[{ID}] 🛒 Shopify Agent gestartet")
    learner = AgentLearner(ID)
    last_order_count = None

    while True:
        try:
            shop = shopify_req("shop.json")
            orders = shopify_req("orders.json?status=any&limit=1")
            products = shopify_req("products.json?limit=1")

            if not shop:
                report(ID, "error", "Shopify API nicht erreichbar")
                time.sleep(300)
                continue

            shop_name = shop.get("shop", {}).get("name", "?")
            curr_orders = orders.get("orders", [])[0].get("id", "?") if orders and orders.get("orders") else None

            msg = f"Shop: {shop_name}"
            status = "ok"
            data = {"shop": shop_name}

            if curr_orders and last_order_count and curr_orders != last_order_count:
                notify_telegram(f"🛒 <b>Shopify:</b> Neue Order! Shop: {shop_name}")

            if curr_orders:
                last_order_count = curr_orders

            report(ID, status, msg, data)
            learner.log_cycle(status, msg, data)

        except Exception as e:
            report(ID, "error", str(e)[:80])

        time.sleep(300)


if __name__ == "__main__":
    run()
