"""
Campaign Manager — Google Ads / Shopping campaign helpers.
Reads live data if Google Ads API credentials are present,
otherwise returns an empty list.
"""

import logging
import os
import time
from typing import Dict, Any, List

log = logging.getLogger("CampaignManager")

GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")


async def get_campaigns() -> List[Dict]:
    """Return campaign list — live if credentials available, empty otherwise."""
    if GOOGLE_ADS_CUSTOMER_ID and GOOGLE_ADS_DEVELOPER_TOKEN:
        try:
            return await _fetch_live_campaigns()
        except Exception as e:
            log.warning("Google Ads live fetch failed: %s", e)
    else:
        log.warning("Google Ads nicht konfiguriert — GOOGLE_ADS_CUSTOMER_ID/DEVELOPER_TOKEN fehlen")
    return []


async def _fetch_live_campaigns() -> List[Dict]:
    """Fetch via Google Ads REST API (requires OAuth2 access token + developer token)."""
    # Google Ads REST API needs a short-lived OAuth2 access token in addition to
    # the developer token. Without it we cannot authenticate, so we return empty.
    # To enable: set GOOGLE_ADS_ACCESS_TOKEN (refresh via google-auth or OAuth2 flow)
    # alongside GOOGLE_ADS_CUSTOMER_ID and GOOGLE_ADS_DEVELOPER_TOKEN.
    import aiohttp
    access_token = os.getenv("GOOGLE_ADS_ACCESS_TOKEN", "")
    if not access_token:
        log.warning("Google Ads: GOOGLE_ADS_ACCESS_TOKEN fehlt — kein Zugriff möglich")
        return []
    customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
    url = (
        f"https://googleads.googleapis.com/v16/customers/{customer_id}/googleAds:searchStream"
    )
    query = (
        "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
        "campaign_budget.amount_micros, metrics.impressions, metrics.clicks, "
        "metrics.cost_micros, metrics.conversions "
        "FROM campaign WHERE campaign.status != 'REMOVED' LIMIT 50"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": GOOGLE_ADS_DEVELOPER_TOKEN,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json={"query": query}, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    log.warning("Google Ads API %s: %s", resp.status, await resp.text())
                    return []
                rows = await resp.json()
    except Exception as e:
        log.warning("Google Ads REST fetch error: %s", e)
        return []
    campaigns: List[Dict] = []
    for batch in rows:
        for row in batch.get("results", []):
            c = row.get("campaign", {})
            bgt = row.get("campaignBudget", {})
            m = row.get("metrics", {})
            campaigns.append({
                "id": c.get("id"),
                "name": c.get("name", ""),
                "status": c.get("status", "UNKNOWN"),
                "type": c.get("advertisingChannelType", ""),
                "budget_eur": int(bgt.get("amountMicros", 0)) / 1_000_000,
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "cost_eur": int(m.get("costMicros", 0)) / 1_000_000,
                "conversions": float(m.get("conversions", 0)),
            })
    return campaigns


def format_telegram_ads(campaigns: List[Dict] = None) -> str:
    """Return Telegram HTML string with campaign overview."""
    if campaigns is None:
        campaigns = []

    lines = ["📣 <b>Google Ads — Kampagnen</b>", ""]

    if not campaigns:
        lines.append("Keine Kampagnen gefunden.")
        return "\n".join(lines)

    for c in campaigns:
        status_icon = "🟢" if c.get("status") == "ENABLED" else "⏸"
        lines += [
            f"{status_icon} <b>{c['name']}</b>",
            f"  Typ: {c.get('type', '?')} | Budget: €{c.get('budget_eur', 0):.2f}/Tag",
            f"  Impressionen: {c.get('impressions', 0):,} | Klicks: {c.get('clicks', 0):,}",
            f"  Kosten: €{c.get('cost_eur', 0):.2f} | Conversions: {c.get('conversions', 0)}",
            "",
        ]

    note = "⏳ <i>Google Ads OAuth ausstehend — zeige Konfigurationsdaten</i>" \
        if not GOOGLE_ADS_CUSTOMER_ID else \
        f"<i>Customer ID: {GOOGLE_ADS_CUSTOMER_ID}</i>"
    lines.append(note)
    return "\n".join(lines)
