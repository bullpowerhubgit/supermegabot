#!/usr/bin/env python3
"""DS24 Funnel Tracker — Trackt Klicks, Conversions, Affiliate-Verdienste."""
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger("DS24FunnelTracker")

DS24_BASE   = "https://www.digistore24.com/api/call"
DS24_FORMAT = "JSON"


_KEY_VARS = (
    "DIGISTORE24_API_KEY", "DS24_API_KEY",
    "DIGISTORE24_API_KEY_FULL", "DS24_API_KEY_FULL",
)


def _key_status() -> tuple[str, str]:
    """Gibt (key, status) zurück.

    status ist eines von: "ok", "no_api_key", "wrong_account"
    IMMER aiitec-Konto (1581233-...) — NIEMALS 1682000-... (falsches Konto).
    """
    # Erst explizit nach aiitec-Key suchen
    for k in _KEY_VARS:
        v = os.getenv(k, "")
        if v and v.startswith("1581233"):
            return v, "ok"

    # Prüfen ob falsches Konto (1682000-...) gesetzt ist
    for k in _KEY_VARS:
        v = os.getenv(k, "")
        if v and v.startswith("1682000"):
            log.error("DS24 FALSCHES KONTO: %s beginnt mit 1682000 — NUR 1581233-... (aiitec) erlaubt!", k)
            return "", "wrong_account"

    # Fallback: erster gesetzter Key (weder 1581233 noch 1682000)
    for k in _KEY_VARS:
        v = os.getenv(k, "")
        if v:
            return v, "ok"

    return "", "no_api_key"


def _key() -> str:
    """Gibt den DS24 API-Key zurück (leer wenn kein gültiger Key)."""
    key, _ = _key_status()
    return key


def _no_key_result(base: dict | None = None) -> dict:
    """Standardisierter Fehler-Return wenn kein Key vorhanden."""
    _, status = _key_status()
    result = {"ok": False, "reason": status, "revenue_eur": 0.0, "sales": 0}
    if base:
        result.update(base)
    return result


def _headers() -> dict:
    key = _key()
    if not key:
        return {}
    return {"X-DS-API-Key": key, "Content-Type": "application/json"}


def _url(action: str) -> str:
    return f"{DS24_BASE}/{action}/{DS24_FORMAT}/"


async def get_sales_today() -> dict:
    """DS24 API: Transaktionen von heute.

    Gibt {"sales": n, "revenue_eur": x} zurück.
    """
    key, status = _key_status()
    if not key:
        log.warning("DS24 get_sales_today: kein gültiger Key (%s) — 1581233-... (aiitec) erwartet", status)
        return _no_key_result()

    today = datetime.now().strftime("%Y-%m-%d")
    params = {
        "page_no":   1,
        "page_size": 100,
        "from":      today,
        "to":        today,
    }
    try:
        import aiohttp
        import json as _json
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(_url("listTransactions"), params=params, headers=_headers()) as r:
                body = await r.text()
                if r.status >= 400:
                    log.warning("DS24 listTransactions HTTP %s: %s", r.status, body[:200])
                    return {"sales": 0, "revenue_eur": 0.0, "error": f"http_{r.status}"}
                data = _json.loads(body)

        if data.get("result") != "success":
            log.warning("DS24 sales_today: result=%s msg=%s",
                        data.get("result"), data.get("message"))
            return {"sales": 0, "revenue_eur": 0.0,
                    "error": data.get("message", "unknown")}

        transactions = data.get("data", {}).get("transaction_list", [])
        revenue = 0.0
        for t in transactions:
            for field in ("earned_amount", "merchant_amount", "amount"):
                try:
                    v = float(t.get(field) or 0)
                    if v:
                        revenue += v
                        break
                except (ValueError, TypeError):
                    pass

        return {"sales": len(transactions), "revenue_eur": round(revenue, 2)}
    except Exception as exc:
        log.error("DS24 get_sales_today error: %s", exc)
        return {"sales": 0, "revenue_eur": 0.0, "error": str(exc)}


async def get_affiliate_earnings(days: int = 30) -> dict:
    """DS24 Affiliate-Report für die letzten `days` Tage."""
    key, status = _key_status()
    if not key:
        log.warning("DS24 get_affiliate_earnings: kein gültiger Key (%s) — 1581233-... (aiitec) erwartet", status)
        return _no_key_result({"period_days": days})

    now       = datetime.now()
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date   = now.strftime("%Y-%m-%d")
    params    = {
        "page_no":   1,
        "page_size": 200,
        "from":      from_date,
        "to":        to_date,
    }
    try:
        import aiohttp
        import json as _json
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(_url("listTransactions"), params=params, headers=_headers()) as r:
                body = await r.text()
                if r.status >= 400:
                    return {"period_days": days, "sales": 0, "revenue_eur": 0.0,
                            "error": f"http_{r.status}"}
                data = _json.loads(body)

        if data.get("result") != "success":
            return {"period_days": days, "sales": 0, "revenue_eur": 0.0,
                    "error": data.get("message", "unknown")}

        transactions = data.get("data", {}).get("transaction_list", [])
        revenue = 0.0
        for t in transactions:
            for field in ("earned_amount", "merchant_amount", "amount"):
                try:
                    v = float(t.get(field) or 0)
                    if v:
                        revenue += v
                        break
                except (ValueError, TypeError):
                    pass

        return {
            "period_days": days,
            "sales":       len(transactions),
            "revenue_eur": round(revenue, 2),
            "from":        from_date,
            "to":          to_date,
        }
    except Exception as exc:
        log.error("DS24 get_affiliate_earnings error: %s", exc)
        return {"period_days": days, "sales": 0, "revenue_eur": 0.0, "error": str(exc)}


async def run_ds24_daily_report() -> dict:
    """Kombinierter Daily-Report + Telegram-Nachricht wenn Revenue > 0."""
    today   = await get_sales_today()
    monthly = await get_affiliate_earnings(days=30)

    report = {
        "today":        today,
        "last_30_days": monthly,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }

    if today.get("revenue_eur", 0) > 0:
        try:
            import aiohttp
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chat  = os.getenv("TELEGRAM_CHAT_ID", "")
            if token and chat:
                msg = (
                    f"<b>DS24 Tages-Report</b>\n"
                    f"Heute: {today['sales']} Verkäufe | {today['revenue_eur']} EUR\n"
                    f"30 Tage: {monthly['sales']} Verkäufe | {monthly['revenue_eur']} EUR"
                )
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as s:
                    await s.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={
                            "chat_id": chat,
                            "text":    msg,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                        },
                    )
                report["telegram_sent"] = True
        except Exception as exc:
            log.warning("DS24 Telegram notify error: %s", exc)
            report["telegram_sent"] = False

    return report
