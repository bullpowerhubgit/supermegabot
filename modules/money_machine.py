"""
Money Machine — Unified Orchestrator (5 Engines in 1) + Live Revenue Cycle
===========================================================================
Kombiniert alle 5 Revenue-Engines:
  1. Viral Window Scanner  — Echtzeit-Trendprodukte
  2. OOS Sniper            — Konkurrenz Out-of-Stock abfangen
  3. Review Goldmine       — Amazon 1★ → fertige Werbung
  4. Cart Rescue           — Abandoned Checkout via Telegram/WhatsApp
  5. eBay Arbitrage        — AliExpress EK → eBay Marktpreis → Shopify

Stripe: LIVE Preise bereits vorhanden (Telegram-Tiers):
  €29/mo → price_1TjodoRJECiV6vSmL726jLd3
  €79/mo → price_1TjodoRJECiV6vSmcWkhHtWz
  €199/mo → price_1TjodpRJECiV6vSmFVtPj8yb
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

log = logging.getLogger("MoneyMachine")

_BASE = Path(__file__).parent.parent

# ── Stripe Live Price IDs (bereits angelegt!) ────────────────────────────────
def _price_alert()  -> str:
    return (os.getenv("VIRAL_PRICE_ALERT")
            or os.getenv("PRICE_TELEGRAM_STARTER", "price_1TjodoRJECiV6vSmL726jLd3"))

def _price_pro() -> str:
    return (os.getenv("VIRAL_PRICE_PRO")
            or os.getenv("PRICE_TELEGRAM_PRO", "price_1TjodoRJECiV6vSmcWkhHtWz"))

def _price_agency() -> str:
    return (os.getenv("VIRAL_PRICE_AGENCY")
            or os.getenv("PRICE_TELEGRAM_AGENCY", "price_1TjodpRJECiV6vSmFVtPj8yb"))

def _stripe_key()   -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _tg_token()     -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()      -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _dashboard_url()-> str: return os.getenv(
    "DASHBOARD_URL",
    "https://supermegabot-production.up.railway.app"
)


# ── Run All Engines ───────────────────────────────────────────────────────────

async def run_all_engines(engines: List[str] = None) -> Dict:
    """Startet alle 5 Engines parallel."""
    ALL = ["viral", "oos", "ebay"]
    selected = engines or ALL
    results = {}
    tasks   = []

    if "viral" in selected:
        tasks.append(("viral", _run_viral()))
    if "oos" in selected:
        tasks.append(("oos", _run_oos()))
    if "ebay" in selected:
        tasks.append(("ebay", _run_ebay()))

    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for i, (name, _) in enumerate(tasks):
        r = gathered[i]
        if isinstance(r, Exception):
            results[name] = {"ok": False, "error": str(r)}
        else:
            results[name] = r

    # Telegram-Summary
    await _send_summary(results)
    return results


async def _run_viral() -> Dict:
    try:
        from modules.viral_window_scanner import run_scan
        return await run_scan()
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "viral"}


async def _run_oos() -> Dict:
    try:
        from modules.oos_sniper import run_scan
        return await run_scan()
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "oos"}


async def _run_ebay() -> Dict:
    try:
        from modules.ebay_arbitrage import run_full_scan
        return await run_full_scan(max_imports=3)
    except Exception as e:
        return {"ok": False, "error": str(e), "engine": "ebay"}


async def _send_summary(results: Dict):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return

    # Nur senden wenn echte Aktivität vorhanden
    has_results = any(
        r.get("ok") and (
            r.get("alerts_sent", 0) > 0 or
            r.get("shopify_imported", 0) > 0 or
            r.get("oos_events", 0) > 0 or
            r.get("imported", 0) > 0
        )
        for r in results.values()
    )
    if not has_results:
        log.debug("Money Machine: 0 Aktivität in allen Engines — kein Telegram")
        return

    lines = ["🤖 <b>Money Machine — Run Complete</b>\n"]
    icons = {"viral": "🔥", "oos": "🎯", "ebay": "📦"}
    for name, r in results.items():
        icon = icons.get(name, "•")
        if r.get("ok"):
            lines.append(f"{icon} <b>{name.upper()}</b>: ✅ {_summarize(name, r)}")
        else:
            lines.append(f"{icon} <b>{name.upper()}</b>: ❌ {r.get('error','?')[:60]}")

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    msg = "\n".join(lines)

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}
            )
    except Exception as e:
        log.debug("TG summary error: %s", e)


def _summarize(name: str, r: Dict) -> str:
    if name == "viral":
        return f"{r.get('signals_total',0)} Signale, {r.get('alerts_sent',0)} Alerts, {r.get('shopify_imported',0)} Imports"
    if name == "oos":
        return f"{r.get('targets',0)} Targets, {r.get('oos_events',0)} OOS Events"
    if name == "ebay":
        return f"{r.get('scanned',0)} gescannt, {r.get('imported',0)} Imports"
    return str(r)[:80]


# ── Unified Status ────────────────────────────────────────────────────────────

async def get_combined_status() -> Dict:
    """Status aller 5 Engines in einem Call."""
    results = await asyncio.gather(
        _safe_status("viral"),
        _safe_status("oos"),
        _safe_status("review"),
        _safe_status("cart"),
        _safe_status("ebay"),
        return_exceptions=True
    )
    names = ["viral", "oos", "review", "cart", "ebay"]
    combined = {}
    for i, name in enumerate(names):
        r = results[i]
        combined[name] = r if isinstance(r, dict) else {"ok": False, "error": str(r)}

    # Revenue-Schätzung
    ebay_r  = combined.get("ebay", {})
    cart_r  = combined.get("cart", {})
    total_revenue = (
        float(ebay_r.get("total_profit", 0)) +
        float(cart_r.get("recovered_revenue", 0))
    )

    return {
        "ok":              True,
        "engines":         combined,
        "total_revenue":   round(total_revenue, 2),
        "stripe_prices": {
            "alert":  _price_alert(),
            "pro":    _price_pro(),
            "agency": _price_agency(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def _safe_status(name: str) -> Dict:
    try:
        if name == "viral":
            from modules.viral_window_scanner import get_status
            return await get_status()
        if name == "oos":
            from modules.oos_sniper import get_status
            return get_status()
        if name == "review":
            from modules.review_goldmine import get_status
            return get_status()
        if name == "cart":
            from modules.cart_rescue import get_status
            return get_status()
        if name == "ebay":
            from modules.ebay_arbitrage import get_stats
            return get_stats()
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}
    return {"ok": False, "error": "unknown engine"}


# ── Stripe Checkout (Money Machine All-in-One) ───────────────────────────────

async def create_mm_checkout(email: str, tier: str = "alert") -> Dict:
    price_map = {
        "alert":  _price_alert(),
        "pro":    _price_pro(),
        "agency": _price_agency()
    }
    price_id = price_map.get(tier, _price_alert())
    key      = _stripe_key()
    if not key:
        return {"error": "STRIPE_SECRET_KEY nicht gesetzt"}
    if not price_id:
        return {"error": f"Stripe Price für Tier '{tier}' nicht gefunden"}

    base = _dashboard_url()
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            connector=aiohttp.TCPConnector(ssl=False)
        ) as s:
            async with s.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "payment_method_types[]": "card",
                    "mode":                   "subscription",
                    "line_items[0][price]":   price_id,
                    "line_items[0][quantity]":"1",
                    "customer_email":         email,
                    "success_url": f"{base}/money-machine/success?session={{CHECKOUT_SESSION_ID}}",
                    "cancel_url":  f"{base}/money-machine",
                    "metadata[tier]":    tier,
                    "metadata[service]": "money_machine"
                }
            ) as r:
                d = await r.json()
                return {
                    "ok":           "id" in d,
                    "checkout_url": d.get("url", ""),
                    "session_id":   d.get("id", ""),
                    "tier":         tier,
                    "price_id":     price_id,
                    "error":        d.get("error", {}).get("message", "") if "error" in d else ""
                }
    except Exception as e:
        return {"error": str(e)}


# ── Live Revenue Cycle (30-min autonomous orchestrator) ───────────────────────

_META_TOKEN  = lambda: (os.getenv("META_ADS_TOKEN") or os.getenv("META_ACCESS_TOKEN", "")).strip()
_PAGE_TOKEN  = lambda: (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or _META_TOKEN()).strip()
_AD_ACCOUNT  = lambda: os.getenv("META_AD_ACCOUNT_ID", "act_878505274898620").strip()
_IG_ACCT     = lambda: os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796").strip()
_SHOP_DOMAIN = lambda: os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co").strip()
_SHOP_TOKEN  = lambda: os.getenv("SHOPIFY_ADMIN_API_TOKEN", "").strip()
_GRAPH       = "https://graph.facebook.com/v25.0"
_SCALE_TO    = 2000   # cents — €20/day target


async def _g(s: aiohttp.ClientSession, path: str, p: dict) -> dict:
    p["access_token"] = _META_TOKEN()
    try:
        async with s.get(f"{_GRAPH}/{path}", params=p,
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await r.json()
            return d if "error" not in d else {}
    except Exception as e:
        log.warning("meta_get %s: %s", path, e)
        return {}


async def _p(s: aiohttp.ClientSession, path: str, data: dict) -> dict:
    data["access_token"] = _META_TOKEN()
    try:
        async with s.post(f"{_GRAPH}/{path}", data=data,
                          timeout=aiohttp.ClientTimeout(total=20)) as r:
            return await r.json()
    except Exception as e:
        log.warning("meta_post %s: %s", path, e)
        return {}


async def _live_ads(s: aiohttp.ClientSession) -> dict:
    act = _AD_ACCOUNT()
    if not act.startswith("act_"):
        act = f"act_{act}"
    ins = await _g(s, f"{act}/insights", {"fields": "spend,actions,action_values", "date_preset": "today"})
    row = (ins.get("data") or [{}])[0]
    spend   = float(row.get("spend", 0))
    revenue = next((float(a["value"]) for a in row.get("action_values", [])
                    if a["action_type"] == "purchase"), 0.0)
    roas    = round(revenue / spend, 2) if spend > 0 else 0.0
    scaled  = False
    if roas > 0:
        adsets = await _g(s, f"{act}/adsets", {"fields": "id,daily_budget,status", "limit": "50"})
        for a in adsets.get("data", []):
            if a.get("status") == "ACTIVE" and 0 < int(a.get("daily_budget", 0)) < _SCALE_TO:
                r = await _p(s, a["id"], {"daily_budget": str(_SCALE_TO)})
                if r.get("success"):
                    scaled = True
    return {"spend": spend, "revenue": revenue, "roas": roas, "scaled": scaled}


def _emails_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    base  = _BASE
    for db in ["bulk_outreach.db", "outreach_autonomous.db", "compliance_outreach.db"]:
        p = base / "data" / db
        if not p.exists():
            continue
        try:
            conn = sqlite3.connect(str(p))
            for col in ("sent_at", "created_at", "timestamp"):
                try:
                    n = conn.execute(
                        f"SELECT COUNT(*) FROM emails WHERE {col} LIKE ? AND status='sent'",
                        (f"{today}%",)).fetchone()[0]
                    conn.close()
                    return n
                except sqlite3.OperationalError:
                    continue
            conn.close()
        except Exception:
            continue
    return 0


async def _live_shopify(s: aiohttp.ClientSession) -> dict:
    token = _SHOP_TOKEN()
    if not token:
        return {"orders": -1, "triggered": False}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    try:
        async with s.get(
            f"https://{_SHOP_DOMAIN()}/admin/api/2026-04/orders.json",
            params={"created_at_min": today, "status": "any", "limit": "250", "fields": "id"},
            headers={"X-Shopify-Access-Token": token},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            orders = len((await r.json()).get("orders", []))
    except Exception as e:
        log.warning("shopify orders: %s", e)
        return {"orders": -1, "triggered": False}
    triggered = False
    if orders == 0 and datetime.now().hour >= 12:
        try:
            from modules.traffic_accelerator import run_traffic_cycle
            asyncio.create_task(run_traffic_cycle())
            triggered = True
        except Exception as e:
            log.warning("traffic trigger: %s", e)
    return {"orders": orders, "triggered": triggered}


async def _top_shopify_product(s: aiohttp.ClientSession) -> dict | None:
    token = _SHOP_TOKEN()
    if not token:
        return None
    try:
        async with s.get(
            f"https://{_SHOP_DOMAIN()}/admin/api/2026-04/products.json",
            params={"limit": "50", "status": "active", "fields": "id,title,variants,images"},
            headers={"X-Shopify-Access-Token": token},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            prods = [p for p in (await r.json()).get("products", []) if p.get("images")]
        if not prods:
            return None
        return max(prods, key=lambda p: float((p.get("variants") or [{}])[0].get("price", 0)))
    except Exception as e:
        log.warning("shopify products: %s", e)
        return None


async def _ig_post(s: aiohttp.ClientSession) -> dict:
    ig = _IG_ACCT()
    # check last post age
    media = await _g(s, f"{ig}/media", {"fields": "timestamp", "limit": "1", "access_token": _META_TOKEN()})
    age_h = 999.0
    if media.get("data"):
        try:
            ts = media["data"][0]["timestamp"]
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except Exception:
            pass
    if age_h < 24:
        return {"posted": False, "age_h": round(age_h, 1)}

    product = await _top_shopify_product(s)
    if not product or not product.get("images"):
        return {"posted": False, "reason": "no_product"}

    title     = product.get("title", "Top Produkt")
    price_str = ""
    try:
        price_str = f"€{float(product['variants'][0]['price']):.2f}"
    except Exception:
        pass
    img_url = product["images"][0].get("src", "")
    if not img_url:
        return {"posted": False, "reason": "no_image"}

    caption = (
        f"🔥 {title}\n"
        + (f"💶 {price_str}\n" if price_str else "")
        + "👉 jetzt shoppen: https://ineedit.com.co\n\n"
        "#SmartHome #Tech #OnlineShop #Gadgets #Deutschland #Österreich"
    )
    create = await _p(s, f"{ig}/media", {"image_url": img_url, "caption": caption})
    cid = create.get("id")
    if not cid:
        return {"posted": False, "reason": create.get("error", {}).get("message", "create_failed")}
    await asyncio.sleep(3)
    pub = await _p(s, f"{ig}/media_publish", {"creation_id": cid})
    if pub.get("id"):
        return {"posted": True, "media_id": pub["id"], "product": title}
    return {"posted": False, "reason": pub.get("error", {}).get("message", "publish_failed")}


async def run_money_cycle() -> dict:
    """30-min autonomous revenue cycle: Meta Ads + Email + Shopify + Instagram."""
    from modules.distributed_lock import acquire_lock, already_done, mark_done
    async with acquire_lock("money_cycle", ttl=25 * 60) as locked:
        if not locked:
            return {"skipped": True, "reason": "Läuft bereits in anderem Terminal/Agenten"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("MoneyMachine live cycle — %s", now)

    async with aiohttp.ClientSession() as s:
        ads, shopify, ig = await asyncio.gather(
            _live_ads(s), _live_shopify(s), _ig_post(s),
            return_exceptions=True,
        )

    def safe(r, d): return r if isinstance(r, dict) else d
    ads     = safe(ads,     {"spend": 0, "roas": 0, "scaled": False})
    shopify = safe(shopify, {"orders": -1, "triggered": False})
    ig      = safe(ig,      {"posted": False})

    emails  = _emails_today()
    email_triggered = False
    if emails < 100:
        try:
            from modules.aiitec_outreach_machine import run_outreach_cycle
            asyncio.ensure_future(run_outreach_cycle())
            email_triggered = True
        except Exception as e:
            log.warning("email trigger: %s", e)

    # Telegram report
    lines = [
        "🤖 <b>MoneyMachine</b>",
        f"🕐 {now}",
        f"📊 Ads: €{ads['spend']:.2f} spend | ROAS {ads['roas']:.2f}x" +
        (" 🚀 skaliert!" if ads.get("scaled") else ""),
        f"📧 Emails: {emails}/Tag" + (" ▶️ getriggert" if email_triggered else ""),
        f"🛒 Orders: {shopify['orders'] if shopify['orders'] >= 0 else 'n/a'}" +
        (" ▶️ Traffic" if shopify.get("triggered") else ""),
        "📸 IG: " + ("✅ gepostet" if ig.get("posted") else f"letzte {ig.get('age_h','?')}h")
    ]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{_tg_token()}/sendMessage",
                json={"chat_id": _tg_chat(), "text": "\n".join(lines), "parse_mode": "HTML"},
            )
    except Exception:
        pass

    return {
        "status": "ok", "timestamp": now,
        "roas": ads["roas"], "spend_today": ads["spend"],
        "revenue_today": ads.get("revenue", 0), "ads_scaled": ads.get("scaled"),
        "emails_today": emails, "email_triggered": email_triggered,
        "orders_today": shopify["orders"], "traffic_triggered": shopify.get("triggered"),
        "ig_posted": ig.get("posted"),
    }
