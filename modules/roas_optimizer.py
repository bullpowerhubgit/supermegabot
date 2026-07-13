"""
ROAS Optimizer — automatischer Meta Ads & Google Ads Performance-Loop
Logik:
  ROAS < 1.2  → Ad Set pausieren + Telegram-Alert
  ROAS 1.2-2.5 → Status-quo, tägl. Monitoring
  ROAS > 3.0  → Budget +20% skalieren
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

META_BASE = "https://graph.facebook.com/v19.0"
STATE_FILE = Path(__file__).parent.parent / "data" / "roas_optimizer.json"

ROAS_PAUSE_THRESHOLD = 1.2
ROAS_SCALE_THRESHOLD = 3.0
BUDGET_SCALE_FACTOR = 1.20   # +20 %


# ---------------------------------------------------------------------------
# State-Verwaltung
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning("State-Datei konnte nicht geladen werden: %s", exc)
    return {
        "last_run": None,
        "ad_sets_checked": 0,
        "paused_today": 0,
        "scaled_today": 0,
        "history": [],
    }


def _save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("State konnte nicht gespeichert werden: %s", exc)


# ---------------------------------------------------------------------------
# Telegram-Alert
# ---------------------------------------------------------------------------

async def _send_telegram(session: aiohttp.ClientSession, message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram nicht konfiguriert — Alert übersprungen")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning("Telegram-Alert fehlgeschlagen (%d): %s", resp.status, body)
            else:
                logger.info("Telegram-Alert gesendet")
    except Exception as exc:
        logger.error("Telegram-Fehler: %s", exc)


# ---------------------------------------------------------------------------
# Shopify Revenue-Abfrage (letzte 24 h, UTM source=facebook)
# ---------------------------------------------------------------------------

async def _get_shopify_revenue_facebook(session: aiohttp.ClientSession) -> float:
    """Gibt den Umsatz (EUR/USD) der letzten 24 h aus Facebook-Traffic zurück."""
    shop = os.getenv("SHOPIFY_SHOP_DOMAIN")
    token = os.getenv("SHOPIFY_ADMIN_API_TOKEN")
    api_version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    if not shop or not token:
        logger.warning("Shopify nicht konfiguriert — Revenue auf 0 gesetzt")
        return 0.0

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"https://{shop}/admin/api/{api_version}/orders.json"
        f"?status=any&created_at_min={since}&limit=250"
        f"&fields=id,total_price,note_attributes,source_name,referring_site"
    )
    headers = {"X-Shopify-Access-Token": token}
    revenue = 0.0
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("Shopify-Orders-Abfrage fehlgeschlagen: %d", resp.status)
                return 0.0
            data = await resp.json()
            orders = data.get("orders", [])
            for order in orders:
                # UTM-Source via note_attributes oder referring_site prüfen
                source_match = False
                for attr in order.get("note_attributes", []):
                    if attr.get("name", "").lower() == "utm_source" and "facebook" in str(attr.get("value", "")).lower():
                        source_match = True
                        break
                if not source_match:
                    ref = (order.get("referring_site") or "").lower()
                    if "facebook" in ref or "fb.com" in ref or "instagram" in ref:
                        source_match = True
                if not source_match:
                    src = (order.get("source_name") or "").lower()
                    if "facebook" in src or "instagram" in src:
                        source_match = True
                if source_match:
                    try:
                        revenue += float(order.get("total_price", 0))
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        logger.error("Shopify Revenue-Abfrage Fehler: %s", exc)
    logger.info("Shopify Facebook-Revenue (24 h): %.2f", revenue)
    return revenue


# ---------------------------------------------------------------------------
# Meta Ads API
# ---------------------------------------------------------------------------

def _meta_token() -> Optional[str]:
    return os.getenv("META_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC")


async def _get_meta_ad_sets(session: aiohttp.ClientSession, ad_account_id: str, access_token: str) -> list[dict]:
    """Holt alle aktiven Ad Sets inkl. Spend-Insights der letzten 24 h."""
    date_preset = "last_1d"
    fields = "id,name,status,daily_budget,insights.date_preset(last_1d){spend,impressions,clicks}"
    url = (
        f"{META_BASE}/act_{ad_account_id}/adsets"
        f"?fields={fields}&status=['ACTIVE']&access_token={access_token}&limit=100"
    )
    ad_sets = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error("Meta Ad Sets Abfrage fehlgeschlagen (%d): %s", resp.status, body)
                return []
            data = await resp.json()
            ad_sets = data.get("data", [])
            logger.info("%d aktive Meta Ad Sets gefunden", len(ad_sets))
    except Exception as exc:
        logger.error("Meta Ad Sets Fehler: %s", exc)
    return ad_sets


async def _pause_meta_ad_set(session: aiohttp.ClientSession, ad_set_id: str, access_token: str) -> bool:
    url = f"{META_BASE}/{ad_set_id}"
    payload = {"status": "PAUSED", "access_token": access_token}
    try:
        async with session.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                logger.info("Ad Set %s pausiert", ad_set_id)
                return True
            body = await resp.text()
            logger.error("Ad Set %s pausieren fehlgeschlagen (%d): %s", ad_set_id, resp.status, body)
    except Exception as exc:
        logger.error("Pause-Fehler Ad Set %s: %s", ad_set_id, exc)
    return False


async def _scale_meta_ad_set_budget(
    session: aiohttp.ClientSession,
    ad_set_id: str,
    current_budget_cents: int,
    access_token: str,
) -> bool:
    """Erhöht das Tagesbudget um BUDGET_SCALE_FACTOR."""
    new_budget = int(current_budget_cents * BUDGET_SCALE_FACTOR)
    url = f"{META_BASE}/{ad_set_id}"
    payload = {"daily_budget": new_budget, "access_token": access_token}
    try:
        async with session.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                logger.info(
                    "Ad Set %s Budget skaliert: %d → %d (Cent)",
                    ad_set_id, current_budget_cents, new_budget,
                )
                return True
            body = await resp.text()
            logger.error("Budget-Skalierung fehlgeschlagen (%d): %s", resp.status, body)
    except Exception as exc:
        logger.error("Scale-Fehler Ad Set %s: %s", ad_set_id, exc)
    return False


def _extract_spend(ad_set: dict) -> float:
    """Extrahiert den Spend aus den Insights eines Ad Sets."""
    try:
        insights = ad_set.get("insights", {})
        if isinstance(insights, dict):
            data = insights.get("data", [])
            if data:
                return float(data[0].get("spend", 0))
    except (TypeError, ValueError, IndexError):
        pass
    return 0.0


async def _process_meta_ad_sets(
    session: aiohttp.ClientSession,
    ad_account_id: str,
    access_token: str,
    facebook_revenue: float,
    state: dict,
) -> list[dict]:
    """Verarbeitet alle Meta Ad Sets und wendet ROAS-Logik an."""
    ad_sets = await _get_meta_ad_sets(session, ad_account_id, access_token)
    if not ad_sets:
        return []

    results = []
    total_spend = sum(_extract_spend(ads) for ads in ad_sets)

    for ad_set in ad_sets:
        ad_set_id = ad_set.get("id", "unbekannt")
        ad_set_name = ad_set.get("name", "unbekannt")
        status = ad_set.get("status", "")
        daily_budget = int(ad_set.get("daily_budget") or 0)
        spend = _extract_spend(ad_set)

        # ROAS berechnen: anteiliger Revenue (proportional zum Spend)
        if total_spend > 0 and spend > 0:
            ad_set_revenue = facebook_revenue * (spend / total_spend)
        else:
            ad_set_revenue = 0.0

        roas = (ad_set_revenue / spend) if spend > 0 else 0.0

        logger.info(
            "Ad Set '%s' | Spend: %.2f | Revenue: %.2f | ROAS: %.2f",
            ad_set_name, spend, ad_set_revenue, roas,
        )

        action_taken = "monitoring"
        success = True

        if spend == 0:
            action_taken = "kein_spend"
        elif roas < ROAS_PAUSE_THRESHOLD:
            # ROAS zu niedrig → pausieren
            success = await _pause_meta_ad_set(session, ad_set_id, access_token)
            if success:
                action_taken = "pausiert"
                state["paused_today"] = state.get("paused_today", 0) + 1
                alert_msg = (
                    f"🛑 <b>ROAS-Optimizer: Ad Set pausiert</b>\n"
                    f"Ad Set: {ad_set_name}\n"
                    f"ROAS: {roas:.2f} (Schwelle: {ROAS_PAUSE_THRESHOLD})\n"
                    f"Spend (24h): {spend:.2f}\n"
                    f"Revenue: {ad_set_revenue:.2f}\n"
                    f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                )
                await _send_telegram(session, alert_msg)
            else:
                action_taken = "pause_fehlgeschlagen"

        elif roas > ROAS_SCALE_THRESHOLD:
            # ROAS sehr gut → Budget skalieren
            if daily_budget > 0:
                success = await _scale_meta_ad_set_budget(session, ad_set_id, daily_budget, access_token)
                if success:
                    action_taken = "budget_skaliert"
                    state["scaled_today"] = state.get("scaled_today", 0) + 1
                    scale_msg = (
                        f"📈 <b>ROAS-Optimizer: Budget skaliert</b>\n"
                        f"Ad Set: {ad_set_name}\n"
                        f"ROAS: {roas:.2f} (Schwelle: {ROAS_SCALE_THRESHOLD})\n"
                        f"Budget: {daily_budget/100:.2f} → {daily_budget*BUDGET_SCALE_FACTOR/100:.2f}\n"
                        f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                    await _send_telegram(session, scale_msg)
                else:
                    action_taken = "scale_fehlgeschlagen"
            else:
                action_taken = "kein_budget_gesetzt"

        results.append({
            "platform": "meta",
            "ad_set_id": ad_set_id,
            "ad_set_name": ad_set_name,
            "spend": spend,
            "revenue": ad_set_revenue,
            "roas": round(roas, 4),
            "action": action_taken,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return results


# ---------------------------------------------------------------------------
# Google Ads (optional, graceful fallback)
# ---------------------------------------------------------------------------

async def _process_google_ads(session: aiohttp.ClientSession) -> list[dict]:
    """Google Ads ROAS-Analyse — nur wenn Env-Vars gesetzt."""
    customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
    developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
    refresh_token = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")

    if not customer_id or not developer_token:
        logger.info("Google Ads nicht konfiguriert (GOOGLE_ADS_CUSTOMER_ID oder GOOGLE_ADS_DEVELOPER_TOKEN fehlt) — übersprungen")
        return []

    logger.info("Google Ads Analyse gestartet für Customer ID: %s", customer_id)
    results = []

    try:
        # Access Token via OAuth2 Refresh-Token holen
        access_token = None
        if refresh_token and client_id and client_secret:
            token_url = "https://oauth2.googleapis.com/token"
            token_payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
            async with session.post(token_url, data=token_payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    access_token = token_data.get("access_token")
                else:
                    body = await resp.text()
                    logger.warning("Google OAuth2 Token fehlgeschlagen (%d): %s", resp.status, body)

        if not access_token:
            logger.warning("Kein Google Ads Access Token — Google Ads übersprungen")
            return []

        # Google Ads Query Language (GAQL) — Campaign-Performance letzte 24h
        query = (
            "SELECT campaign.id, campaign.name, campaign.status, "
            "metrics.cost_micros, metrics.conversions_value, "
            "campaign_budget.amount_micros "
            "FROM campaign "
            "WHERE segments.date DURING YESTERDAY "
            "AND campaign.status = 'ENABLED'"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": developer_token,
            "Content-Type": "application/json",
        }
        clean_customer_id = customer_id.replace("-", "")
        url = f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/googleAds:search"
        payload = {"query": query}

        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning("Google Ads Query fehlgeschlagen (%d): %s", resp.status, body)
                return []
            data = await resp.json()

        for row in data.get("results", []):
            campaign = row.get("campaign", {})
            metrics = row.get("metrics", {})
            budget = row.get("campaignBudget", {})

            campaign_id = campaign.get("id", "unbekannt")
            campaign_name = campaign.get("name", "unbekannt")

            spend = float(metrics.get("costMicros", 0)) / 1_000_000
            revenue = float(metrics.get("conversionsValue", 0))
            roas = (revenue / spend) if spend > 0 else 0.0

            logger.info(
                "Google Ads Kampagne '%s' | Spend: %.2f | Revenue: %.2f | ROAS: %.2f",
                campaign_name, spend, revenue, roas,
            )

            action_taken = "monitoring"

            if spend > 0 and roas < ROAS_PAUSE_THRESHOLD:
                # Kampagne pausieren
                pause_url = (
                    f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/campaigns:mutate"
                )
                pause_payload = {
                    "operations": [{
                        "update": {
                            "resourceName": f"customers/{clean_customer_id}/campaigns/{campaign_id}",
                            "status": "PAUSED",
                        },
                        "updateMask": "status",
                    }]
                }
                async with session.post(
                    pause_url, headers=headers, json=pause_payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as presp:
                    if presp.status == 200:
                        action_taken = "pausiert"
                        alert_msg = (
                            f"🛑 <b>ROAS-Optimizer: Google Kampagne pausiert</b>\n"
                            f"Kampagne: {campaign_name}\n"
                            f"ROAS: {roas:.2f}\n"
                            f"Spend (24h): {spend:.2f}\n"
                            f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                        )
                        await _send_telegram(session, alert_msg)
                    else:
                        body = await presp.text()
                        logger.warning("Google Ads Pause fehlgeschlagen: %s", body)
                        action_taken = "pause_fehlgeschlagen"

            elif spend > 0 and roas > ROAS_SCALE_THRESHOLD:
                # Budget skalieren
                budget_micros = int(budget.get("amountMicros", 0))
                if budget_micros > 0:
                    new_budget_micros = int(budget_micros * BUDGET_SCALE_FACTOR)
                    budget_resource = budget.get("resourceName", "")
                    scale_url = (
                        f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/campaignBudgets:mutate"
                    )
                    scale_payload = {
                        "operations": [{
                            "update": {
                                "resourceName": budget_resource,
                                "amountMicros": new_budget_micros,
                            },
                            "updateMask": "amountMicros",
                        }]
                    }
                    async with session.post(
                        scale_url, headers=headers, json=scale_payload, timeout=aiohttp.ClientTimeout(total=10)
                    ) as sresp:
                        if sresp.status == 200:
                            action_taken = "budget_skaliert"
                            scale_msg = (
                                f"📈 <b>ROAS-Optimizer: Google Budget skaliert</b>\n"
                                f"Kampagne: {campaign_name}\n"
                                f"ROAS: {roas:.2f}\n"
                                f"Budget: {budget_micros/1e6:.2f} → {new_budget_micros/1e6:.2f}\n"
                                f"Zeit: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                            )
                            await _send_telegram(session, scale_msg)
                        else:
                            body = await sresp.text()
                            logger.warning("Google Ads Budget-Scale fehlgeschlagen: %s", body)
                            action_taken = "scale_fehlgeschlagen"

            results.append({
                "platform": "google",
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "spend": spend,
                "revenue": revenue,
                "roas": round(roas, 4),
                "action": action_taken,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    except Exception as exc:
        logger.error("Google Ads Analyse Fehler: %s", exc)

    return results


# ---------------------------------------------------------------------------
# Haupt-Exportfunktionen
# ---------------------------------------------------------------------------

async def run_roas_cycle() -> str:
    """
    Haupt-Loop: Meta + Google Ads ROAS-Check.
    Wird vom Scheduler aufgerufen.
    Returns: Zusammenfassungs-String
    """
    logger.info("ROAS-Optimizer Cycle gestartet")
    state = _load_state()

    # Tages-Zähler zurücksetzen wenn neuer Tag
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("last_run_date") != today:
        state["paused_today"] = 0
        state["scaled_today"] = 0
        state["last_run_date"] = today

    access_token = _meta_token()
    ad_account_id = os.getenv("META_AD_ACCOUNT_ID")

    if not access_token or not ad_account_id:
        msg = "Meta Ads nicht konfiguriert — ROAS-Check übersprungen"
        logger.warning(msg)
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        return msg

    all_results = []

    connector = aiohttp.TCPConnector(ssl=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Shopify Revenue für Facebook-Traffic holen
        facebook_revenue = await _get_shopify_revenue_facebook(session)

        # Meta Ad Sets verarbeiten
        meta_results = await _process_meta_ad_sets(
            session, ad_account_id, access_token, facebook_revenue, state
        )
        all_results.extend(meta_results)
        state["ad_sets_checked"] = state.get("ad_sets_checked", 0) + len(meta_results)

        # Google Ads verarbeiten (optional)
        google_results = await _process_google_ads(session)
        all_results.extend(google_results)

    # History-Eintrag hinzufügen
    history_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": "meta+google",
        "ad_sets_checked": len(all_results),
        "paused": sum(1 for r in all_results if r.get("action") == "pausiert"),
        "scaled": sum(1 for r in all_results if r.get("action") == "budget_skaliert"),
        "facebook_revenue_24h": facebook_revenue,
        "results": all_results,
    }
    history = state.get("history", [])
    history.append(history_entry)
    state["history"] = history[-50:]  # Letzte 50 Einträge behalten
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    paused = history_entry["paused"]
    scaled = history_entry["scaled"]
    checked = history_entry["ad_sets_checked"]

    summary = (
        f"ROAS-Cycle abgeschlossen: {checked} Ad Sets geprüft | "
        f"{paused} pausiert | {scaled} skaliert | "
        f"FB-Revenue (24h): {facebook_revenue:.2f}"
    )
    logger.info(summary)
    return summary


async def get_status() -> dict:
    """
    Gibt den aktuellen Status des ROAS-Optimizers zurück.
    """
    state = _load_state()
    history = state.get("history", [])
    last_entry = history[-1] if history else {}

    return {
        "module": "roas_optimizer",
        "last_run": state.get("last_run"),
        "ad_sets_checked_total": state.get("ad_sets_checked", 0),
        "paused_today": state.get("paused_today", 0),
        "scaled_today": state.get("scaled_today", 0),
        "meta_configured": bool(_meta_token() and os.getenv("META_AD_ACCOUNT_ID")),
        "google_configured": bool(
            os.getenv("GOOGLE_ADS_CUSTOMER_ID") and os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
        ),
        "thresholds": {
            "pause_below": ROAS_PAUSE_THRESHOLD,
            "scale_above": ROAS_SCALE_THRESHOLD,
            "scale_factor": BUDGET_SCALE_FACTOR,
        },
        "last_cycle": last_entry,
        "history_count": len(history),
    }


# ---------------------------------------------------------------------------
# Standalone-Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main():
        result = await run_roas_cycle()
        print(result)
        status = await get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

    asyncio.run(_main())
