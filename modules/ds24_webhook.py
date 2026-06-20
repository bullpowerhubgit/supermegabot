#!/usr/bin/env python3
"""
DS24 Dankeseite-Webhook — wird nach jedem Kauf von DS24 aufgerufen.
Schlüssel: O5jqklqAcxTvkKHp0rvn (in DS24 → Produkt → Dankeseite eintragen)

Dankeseite-URL: https://dudirudibot-mega-production.up.railway.app/api/ds24/dankeseite

DS24 übergibt folgende Parameter (GET oder POST):
  order_id, product_id, product_name, buyer_email, buyer_name,
  price, currency, affiliate_id, transaction_id
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("DS24Webhook")

DS24_DANKESEITE_KEY = os.getenv("DS24_DANKESEITE_KEY", "O5jqklqAcxTvkKHp0rvn")
DS24_KEY = os.getenv("DS24_API_KEY", "1682000-T8KjTRJXCO1IgXOU5I7am6p6a0AZuqV2BGswDECY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
RAILWAY_URL    = "https://dudirudibot-mega-production.up.railway.app"


async def _telegram(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


async def _log_to_supabase(data: dict) -> None:
    try:
        from modules.supabase_client import get_client
        get_client().table("ds24_purchases").insert({
            "order_id":       data.get("order_id", ""),
            "product_id":     data.get("product_id", ""),
            "product_name":   data.get("product_name", "")[:200],
            "buyer_email":    data.get("buyer_email", ""),
            "buyer_name":     data.get("buyer_name", ""),
            "price":          float(data.get("price", 0) or 0),
            "currency":       data.get("currency", "EUR"),
            "affiliate_id":   data.get("affiliate_id", ""),
            "transaction_id": data.get("transaction_id", ""),
            "created_at":     datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("Supabase log failed: %s", e)


async def _send_buyer_email(buyer_email: str, buyer_name: str,
                            product_name: str, order_id: str) -> None:
    if not buyer_email:
        return
    try:
        from modules.email_blast_engine import send_via_smtp
        name = buyer_name.split()[0] if buyer_name else "Kunde"
        html = (
            f"<h2>Danke für deinen Kauf, {name}! 🎉</h2>"
            f"<p>Deine Bestellung <strong>{product_name}</strong> (#{order_id}) ist eingegangen.</p>"
            f"<p>Du erhältst in Kürze Zugang per E-Mail von Digistore24.</p>"
            f"<p>Bei Fragen antworte einfach auf diese Mail.</p>"
            f"<p>Viele Grüße,<br><strong>BullPowerHub Team</strong></p>"
        )
        await send_via_smtp(
            subject=f"Danke für deinen Kauf: {product_name}",
            html=html,
            to_email=buyer_email,
        )
    except Exception as e:
        log.warning("Buyer email failed: %s", e)


async def _trigger_klaviyo_event(buyer_email: str, data: dict) -> None:
    if not buyer_email:
        return
    try:
        from modules.klaviyo_autonomy import track_event
        await track_event(
            email=buyer_email,
            event_name="DS24 Purchase",
            properties={
                "product_id":   data.get("product_id", ""),
                "product_name": data.get("product_name", ""),
                "order_id":     data.get("order_id", ""),
                "price":        float(data.get("price", 0) or 0),
                "currency":     data.get("currency", "EUR"),
            },
        )
    except Exception as e:
        log.warning("Klaviyo event failed: %s", e)


async def handle_ds24_purchase(data: dict) -> dict:
    """
    Wird aufgerufen wenn DS24 die Dankeseite-URL aufruft.
    data = Query-Parameter von DS24.
    """
    order_id     = data.get("order_id", data.get("bestellnummer", ""))
    product_id   = data.get("product_id", data.get("produkt_id", ""))
    product_name = data.get("product_name", data.get("produktname", f"Produkt #{product_id}"))
    buyer_email  = data.get("buyer_email", data.get("email", data.get("kaeufer_email", "")))
    buyer_name   = data.get("buyer_name",  data.get("name",  data.get("kaeufer_name",  "")))
    price        = data.get("price", data.get("preis", "0"))
    currency     = data.get("currency", data.get("waehrung", "EUR"))
    affiliate_id = data.get("affiliate_id", data.get("affiliate", ""))
    transaction_id = data.get("transaction_id", data.get("transaktions_id", order_id))

    log.info("DS24 Kauf: order=%s product=%s buyer=%s price=%s%s",
             order_id, product_id, buyer_email, price, currency)

    # Alles parallel ausführen
    await asyncio.gather(
        _telegram(
            f"💰 <b>NEUER KAUF!</b>\n"
            f"Produkt: {product_name}\n"
            f"Preis: {price} {currency}\n"
            f"Käufer: {buyer_name} ({buyer_email})\n"
            f"Order: #{order_id}\n"
            f"Affiliate: {affiliate_id or 'direkt'}"
        ),
        _log_to_supabase({
            "order_id": order_id, "product_id": product_id,
            "product_name": product_name, "buyer_email": buyer_email,
            "buyer_name": buyer_name, "price": price, "currency": currency,
            "affiliate_id": affiliate_id, "transaction_id": transaction_id,
        }),
        _send_buyer_email(buyer_email, buyer_name, product_name, order_id),
        _trigger_klaviyo_event(buyer_email, {
            "product_id": product_id, "product_name": product_name,
            "order_id": order_id, "price": price, "currency": currency,
        }),
        return_exceptions=True,
    )

    # BrutusCore Sale-Alert
    try:
        from modules.brutus_core import fire
        await fire(
            f"💰 DS24 VERKAUF: {product_name}",
            f"Preis: {price} {currency} | Order: #{order_id} | Affiliate: {affiliate_id or 'direkt'}",
            channels=["telegram", "slack"],
        )
    except Exception:
        pass

    return {
        "ok": True,
        "order_id": order_id,
        "product": product_name,
        "buyer": buyer_email,
        "price": price,
        "currency": currency,
    }


async def get_ds24_purchase_stats() -> dict:
    """Alle DS24-Käufe aus Supabase."""
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_purchases").select("*").order(
            "created_at", desc=True).limit(100).execute()
        data = rows.data or []
        total_revenue = sum(float(r.get("price", 0) or 0) for r in data)
        return {
            "ok": True,
            "total_purchases": len(data),
            "total_revenue_eur": round(total_revenue, 2),
            "recent": [
                {
                    "order_id": r.get("order_id"),
                    "product": r.get("product_name", "")[:50],
                    "price": r.get("price"),
                    "buyer": r.get("buyer_email", "")[:30],
                    "date": r.get("created_at", "")[:10],
                }
                for r in data[:10]
            ],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


DANKESEITE_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vielen Dank für deinen Kauf!</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #fff;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; }}
  .box {{ background: #111; border: 1px solid #222; border-radius: 16px;
          padding: 48px; max-width: 520px; text-align: center; }}
  h1 {{ color: #e63946; font-size: 2rem; margin: 0 0 16px; }}
  p  {{ color: #aaa; line-height: 1.6; }}
  .order {{ background: #1a1a1a; border-radius: 8px; padding: 16px;
            margin: 24px 0; font-size: 0.9rem; color: #888; }}
  .cta {{ display: inline-block; margin-top: 24px; padding: 14px 32px;
          background: #e63946; color: #fff; border-radius: 8px;
          text-decoration: none; font-weight: 600; }}
</style>
</head>
<body>
<div class="box">
  <h1>🎉 Vielen Dank!</h1>
  <p>Dein Kauf war erfolgreich. Du erhältst in Kürze eine E-Mail von Digistore24 mit deinem Zugang.</p>
  <div class="order">
    Bestellung: #{order_id}<br>
    Produkt: {product_name}
  </div>
  <p>Bei Fragen stehen wir dir jederzeit zur Verfügung.</p>
  <a href="https://bullpowerhub.com" class="cta">Zur Hauptseite →</a>
</div>
</body>
</html>"""
