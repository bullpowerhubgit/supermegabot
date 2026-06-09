"""
Campaign Manager — Google Ads / Shopping campaign helpers.
Reads live data if Google Ads API credentials are present,
otherwise returns structured placeholder data.
"""

import logging
import os
import time
from typing import Dict, Any, List

log = logging.getLogger("CampaignManager")

GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")


# ---------------------------------------------------------------------------
# Mock / fallback campaign data
# ---------------------------------------------------------------------------

MOCK_CAMPAIGNS: List[Dict] = [
    {
        "id": "001",
        "name": "Shopping – Alle Produkte",
        "type": "Shopping",
        "status": "ENABLED",
        "budget_eur": 10.0,
        "impressions": 0,
        "clicks": 0,
        "conversions": 0,
        "cost_eur": 0.0,
    },
]


async def get_campaigns() -> List[Dict]:
    """Return campaign list — live if credentials available, mock otherwise."""
    if GOOGLE_ADS_CUSTOMER_ID and GOOGLE_ADS_DEVELOPER_TOKEN:
        try:
            return await _fetch_live_campaigns()
        except Exception as e:
            log.warning("Google Ads live fetch failed: %s — using mock data", e)
    return MOCK_CAMPAIGNS


async def _fetch_live_campaigns() -> List[Dict]:
    """Fetch via Google Ads REST API (requires OAuth2 access token)."""
    # Full implementation requires google-ads Python library or OAuth2 access token.
    # Placeholder — raises so callers fall back to mock data.
    raise NotImplementedError("Google Ads OAuth not configured yet")


def format_telegram_ads(campaigns: List[Dict] = None) -> str:
    """Return Telegram HTML string with campaign overview."""
    if campaigns is None:
        campaigns = MOCK_CAMPAIGNS

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
