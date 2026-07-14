#!/usr/bin/env python3
"""
Shopify → Klaviyo/Mailchimp/DS24 customer exporter.
Exportiert alle Shopify-Käufer (bullpower-store) in das aiitec-Funnel-System.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

log = logging.getLogger("CustomerExporter")

# Shopify (bullpower store)
def _shop_domain() -> str:
    return os.getenv("SHOPIFY_SHOP_DOMAIN", "")

def _shop_token() -> str:
    return os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_API_TOKEN", "") or os.getenv("SHOPIFY_ACCESS_TOKEN", "")

def _shop_ver() -> str:
    return os.getenv("SHOPIFY_API_VERSION", "2026-04")

# Klaviyo aiitec — sanitize list ID (env may store as dict-string)
import re as _re_ce
_raw_kl_id = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
_m_kl = _re_ce.search(r"'id':\s*'([A-Za-z0-9]+)'", str(_raw_kl_id))
KLAVIYO_LIST_ID = _m_kl.group(1) if _m_kl else (str(_raw_kl_id).strip().strip("'\"") if len(str(_raw_kl_id)) < 20 else "Xwxq6V")
KLAVIYO_KEY     = os.getenv("KLAVIYO_API_KEY", "")

# Mailchimp Dragon/aiitec
MC_KEY_AIITEC   = os.getenv("MAILCHIMP_API_KEY", "")
MC_LIST_AIITEC  = os.getenv("MAILCHIMP_LIST_ID", "0e84a22a44")

# Telegram
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

_EXPORT_FILE = Path("/tmp/supermegabot/exported_customers.json")


async def _tg(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


async def fetch_shopify_customers(limit: int = 250) -> List[Dict]:
    """Pull all Shopify customers from the bullpower store."""
    domain = _shop_domain()
    token  = _shop_token()
    if not domain or not token:
        log.warning("Shopify credentials missing — SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_API_TOKEN not set")
        return []
    try:
        import aiohttp
        url = f"https://{domain}/admin/api/{_shop_ver()}/customers.json?limit={limit}&order=created_at+desc"
        headers = {"X-Shopify-Access-Token": token}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(url, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    customers = data.get("customers", [])
                    log.info("Shopify: %d Kunden geladen", len(customers))
                    return customers
                log.warning("Shopify customers status %s", r.status)
                return []
    except Exception as e:
        log.error("fetch_shopify_customers: %s", e)
        return []


async def export_to_klaviyo(customers: List[Dict]) -> Dict:
    """Upsert each customer into Klaviyo aiitec list."""
    if not KLAVIYO_KEY:
        return {"ok": False, "reason": "KLAVIYO_API_KEY nicht gesetzt"}
    try:
        from modules.klaviyo_automation import upsert_profile, add_profile_to_list
        synced, failed = 0, 0
        for c in customers:
            email = (c.get("email") or "").strip()
            if not email:
                continue
            try:
                pid = await upsert_profile(
                    email=email,
                    first_name=c.get("first_name", ""),
                    last_name=c.get("last_name", ""),
                    properties={
                        "source": "shopify_bullpower",
                        "orders_count": c.get("orders_count", 0),
                        "total_spent": c.get("total_spent", "0"),
                        "exported_at": datetime.now().isoformat(),
                    },
                )
                if pid:
                    await add_profile_to_list(KLAVIYO_LIST_ID, pid)
                    synced += 1
            except Exception as e:
                log.debug("Klaviyo upsert %s: %s", email, e)
                failed += 1
        return {"ok": True, "synced": synced, "failed": failed, "list": KLAVIYO_LIST_ID}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def export_to_mailchimp(customers: List[Dict]) -> Dict:
    """Add customers to Mailchimp AIITEC list."""
    key = MC_KEY_AIITEC
    if not key or key == "MISSING_PLEASE_ADD":
        return {"ok": False, "reason": "MAILCHIMP_API_KEY nicht gesetzt"}
    try:
        import aiohttp, hashlib
        server = key.split("-")[-1] if "-" in key else "us7"
        subscribed, skipped = 0, 0
        for c in customers:
            email = (c.get("email") or "").strip().lower()
            if not email:
                continue
            email_hash = hashlib.md5(email.encode()).hexdigest()
            url = f"https://{server}.api.mailchimp.com/3.0/lists/{MC_LIST_AIITEC}/members/{email_hash}"
            payload = {
                "email_address": email,
                "status_if_new": "subscribed",
                "merge_fields": {
                    "FNAME": c.get("first_name", ""),
                    "LNAME": c.get("last_name", ""),
                },
                "tags": ["shopify_buyer", "bullpower_export"],
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.put(
                    url, json=payload, auth=aiohttp.BasicAuth("anystring", key)
                ) as r:
                    if r.status in (200, 204):
                        subscribed += 1
                    else:
                        skipped += 1
        return {"ok": True, "subscribed": subscribed, "skipped": skipped}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def run_full_export() -> Dict:
    """Kompletter Shopify→Klaviyo+Mailchimp Export mit Telegram-Bericht."""
    _EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    log.info("Starte Customer Export: Shopify → aiitec Funnel")
    customers = await fetch_shopify_customers(limit=250)

    if not customers:
        msg = "⚠️ <b>Customer Export</b>\nKeine Shopify-Kunden gefunden — Store prüfen"
        await _tg(msg)
        return {"ok": False, "reason": "no_customers"}

    # Export to Klaviyo + Mailchimp in parallel
    klaviyo_result, mc_result = await asyncio.gather(
        export_to_klaviyo(customers),
        export_to_mailchimp(customers),
        return_exceptions=True,
    )
    if isinstance(klaviyo_result, Exception):
        klaviyo_result = {"ok": False, "error": str(klaviyo_result)}
    if isinstance(mc_result, Exception):
        mc_result = {"ok": False, "error": str(mc_result)}

    # Save snapshot
    snapshot = {
        "ts": datetime.now().isoformat(),
        "total_customers": len(customers),
        "emails": [c.get("email","") for c in customers if c.get("email")],
        "klaviyo": klaviyo_result,
        "mailchimp": mc_result,
    }
    _EXPORT_FILE.write_text(json.dumps(snapshot, indent=2))

    # Telegram report
    kl_ok = klaviyo_result.get("synced", 0) if klaviyo_result.get("ok") else 0
    mc_ok = mc_result.get("subscribed", 0) if mc_result.get("ok") else 0
    emails_total = len([c for c in customers if c.get("email")])
    buyers = [c for c in customers if c.get("orders_count", 0) > 0]

    msg = (
        f"🔄 <b>Customer Export Abgeschlossen!</b>\n\n"
        f"👥 Shopify Kunden: <b>{len(customers)}</b>\n"
        f"📧 Mit Email: <b>{emails_total}</b>\n"
        f"🛒 Käufer (orders > 0): <b>{len(buyers)}</b>\n\n"
        f"📊 <b>Klaviyo aiitec (Liste: {KLAVIYO_LIST_ID})</b>\n"
        f"   ✅ {kl_ok} importiert\n\n"
        f"📮 <b>Mailchimp aiitec</b>\n"
        f"   ✅ {mc_ok} abonniert\n\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await _tg(msg)
    log.info("Export fertig: %d Kunden → Klaviyo:%d, Mailchimp:%d", len(customers), kl_ok, mc_ok)

    return {
        "ok": True,
        "total_customers": len(customers),
        "emails_found": emails_total,
        "buyers": len(buyers),
        "klaviyo": klaviyo_result,
        "mailchimp": mc_result,
    }


async def get_export_stats() -> Dict:
    """Return last export stats from cache file."""
    if _EXPORT_FILE.exists():
        try:
            data = json.loads(_EXPORT_FILE.read_text())
            return {
                "last_export": data.get("ts", "?"),
                "total_customers": data.get("total_customers", 0),
                "emails": len(data.get("emails", [])),
                "klaviyo": data.get("klaviyo", {}),
                "mailchimp": data.get("mailchimp", {}),
            }
        except Exception:
            pass
    return {"last_export": "noch nie", "total_customers": 0}
