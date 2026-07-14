"""ROAS Optimizer — Live Meta Ads API Pull, Auto-Scale/Pause, Purchase Campaign Creation

Cycle (called every hour by scheduler):
  1. Pull live insights (last 7d) per ad set from all active campaigns
  2. Calculate ROAS = purchase_value / spend
  3. ROAS > SCALE_THRESHOLD → scale daily_budget +SCALE_PCT
  4. ROAS < PAUSE_THRESHOLD (after MIN_SPEND) → pause ad set
  5. No active PURCHASE campaign → create one for ineedit.com.co
  6. Telegram report

Main entry: run_roas_cycle() → dict
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

log = logging.getLogger(__name__)

# ── Credentials ───────────────────────────────────────────────────────────────
_TOKEN    = (os.getenv("META_ADS_TOKEN") or os.getenv("META_ACCESS_TOKEN") or "").strip()
_ACC      = (os.getenv("META_AD_ACCOUNT_ID") or "act_878505274898620").strip()
_ACC_INEEDIT = "act_2215713609248740"
_PIXEL    = "4215456142051261"
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
_API      = "https://graph.facebook.com/v25.0"

# ── Thresholds ────────────────────────────────────────────────────────────────
ROAS_SCALE   = float(os.getenv("ROAS_SCALE_THRESHOLD", "3.5"))   # scale if >
ROAS_PAUSE   = float(os.getenv("ROAS_PAUSE_THRESHOLD", "1.2"))   # pause if <
SCALE_PCT    = float(os.getenv("SCALE_BUDGET_PCT", "25.0"))      # % budget increase
MIN_SPEND    = float(os.getenv("ROAS_MIN_SPEND_EUR", "3.0"))     # min € before pause
MAX_DAILY    = int(os.getenv("ROAS_MAX_DAILY_CENTS", "5000"))    # max budget per adset (cents)


def _act(acct: str = "") -> str:
    a = (acct or _ACC).strip()
    return a if a.startswith("act_") else f"act_{a}"


async def _tg(msg: str) -> None:
    if not _TG_TOKEN or not _TG_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                json={"chat_id": _TG_CHAT, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        log.warning("_tg: %s", e)


async def _get(session: aiohttp.ClientSession, path: str, params: dict) -> dict:
    params["access_token"] = _TOKEN
    try:
        async with session.get(
            f"{_API}/{path}", params=params,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if "error" in data:
                log.warning("Meta API error [%s]: %s", path, data["error"].get("message"))
                return {}
            return data
    except Exception as e:
        log.warning("_get(%s): %s", path, e)
        return {}


async def _post(session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
    payload["access_token"] = _TOKEN
    try:
        async with session.post(
            f"{_API}/{path}", data=payload,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            data = await r.json()
            if "error" in data:
                log.warning("Meta POST error [%s]: %s", path, data["error"].get("message"))
            return data
    except Exception as e:
        log.warning("_post(%s): %s", path, e)
        return {}


# ── Live Insights Pull ────────────────────────────────────────────────────────

async def _fetch_campaigns(session: aiohttp.ClientSession, acct: str) -> list[dict]:
    data = await _get(session, f"{_act(acct)}/campaigns", {
        "fields": "id,name,status,objective,daily_budget",
        "limit": "50",
    })
    return [c for c in data.get("data", []) if c.get("status") == "ACTIVE"]


async def _fetch_adset_insights(session: aiohttp.ClientSession, acct: str) -> list[dict]:
    """Pull 7-day insights at ad-set level: spend, purchases, revenue."""
    data = await _get(session, f"{_act(acct)}/adsets", {
        "fields": "id,name,status,daily_budget,campaign_id",
        "limit": "200",
    })
    adsets = [a for a in data.get("data", []) if a.get("status") == "ACTIVE"]
    if not adsets:
        return []

    results = []
    for adset in adsets:
        ins = await _get(session, f"{adset['id']}/insights", {
            "fields": "spend,impressions,clicks,actions,action_values,cost_per_action_type",
            "date_preset": "last_7d",
        })
        row_data = ins.get("data", [{}])[0] if ins.get("data") else {}

        spend = float(row_data.get("spend", 0))
        purchases = next(
            (float(a["value"]) for a in row_data.get("actions", [])
             if a["action_type"] == "purchase"), 0.0
        )
        revenue = next(
            (float(a["value"]) for a in row_data.get("action_values", [])
             if a["action_type"] == "purchase"), 0.0
        )
        roas = round(revenue / spend, 2) if spend > 0 else 0.0

        results.append({
            "id": adset["id"],
            "name": adset["name"],
            "campaign_id": adset.get("campaign_id", ""),
            "daily_budget_cents": int(adset.get("daily_budget", 0)),
            "spend_7d": round(spend, 2),
            "purchases_7d": purchases,
            "revenue_7d": round(revenue, 2),
            "roas": roas,
            "impressions": int(row_data.get("impressions", 0)),
            "clicks": int(row_data.get("clicks", 0)),
        })

    return results


# ── Scale / Pause ─────────────────────────────────────────────────────────────

async def _scale_adset(session: aiohttp.ClientSession, adset: dict) -> bool:
    current = adset["daily_budget_cents"]
    if current <= 0:
        return False
    new_budget = min(int(current * (1 + SCALE_PCT / 100)), MAX_DAILY)
    if new_budget <= current:
        return False
    result = await _post(session, adset["id"], {"daily_budget": str(new_budget)})
    if result.get("success"):
        log.info("SCALED %s: %d→%d cents (ROAS=%.2fx)", adset["name"], current, new_budget, adset["roas"])
        return True
    return False


async def _pause_adset(session: aiohttp.ClientSession, adset: dict) -> bool:
    result = await _post(session, adset["id"], {"status": "PAUSED"})
    if result.get("success"):
        log.info("PAUSED %s (ROAS=%.2fx spend=€%.2f)", adset["name"], adset["roas"], adset["spend_7d"])
        return True
    return False


# ── Create Purchase Campaign ──────────────────────────────────────────────────

async def _has_purchase_campaign(session: aiohttp.ClientSession, acct: str) -> bool:
    data = await _get(session, f"{_act(acct)}/campaigns", {
        "fields": "id,objective,status",
        "limit": "50",
    })
    for c in data.get("data", []):
        if c.get("objective") == "OUTCOME_SALES" and c.get("status") == "ACTIVE":
            return True
    return False


async def _create_purchase_campaign(session: aiohttp.ClientSession) -> str | None:
    """Create OUTCOME_SALES campaign in primary account if not existing."""
    acct = _act(_ACC)

    # Campaign
    camp = await _post(session, f"{acct}/campaigns", {
        "name": "ineedit | Smart Home | Käufe | ROAS-Max",
        "objective": "OUTCOME_SALES",
        "status": "ACTIVE",
        "special_ad_categories": "[]",
        "smart_promotion_type": "GUIDED_CREATION",
    })
    cid = camp.get("id")
    if not cid:
        log.warning("Campaign creation failed: %s", camp)
        return None
    log.info("Created campaign: %s", cid)

    # Ad Set — DACH, Smart Home interests, Purchase optimization
    adset = await _post(session, f"{acct}/adsets", {
        "name": "ineedit | DACH | Lookalike 1% | Käufe",
        "campaign_id": cid,
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "promoted_object": f'{{"pixel_id":"{_PIXEL}","custom_event_type":"PURCHASE"}}',
        "daily_budget": "1000",  # €10/day in cents
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": """{
            "geo_locations": {"countries": ["DE","AT","CH"]},
            "age_min": 22,
            "age_max": 55,
            "interests": [
                {"id": "6003139266461", "name": "Smart home"},
                {"id": "6003397425735", "name": "Consumer electronics"},
                {"id": "6003105328161", "name": "Online shopping"},
                {"id": "6003348604963", "name": "Technology"}
            ],
            "publisher_platforms": ["facebook","instagram"],
            "facebook_positions": ["feed","right_hand_column"],
            "instagram_positions": ["stream","explore"]
        }""",
        "status": "ACTIVE",
        "pixel_id": _PIXEL,
    })
    asid = adset.get("id")
    if not asid:
        log.warning("Ad set creation failed: %s", adset)
        return cid

    log.info("Created ad set: %s", asid)
    return cid


# ── Main Cycle ────────────────────────────────────────────────────────────────

async def run_roas_cycle() -> dict:
    if not _TOKEN:
        log.warning("META_ADS_TOKEN not set — skipping ROAS cycle")
        return {"status": "no_token", "paused": [], "scaled": [], "revenue_7d": 0, "spend_7d": 0, "roas": 0}

    log.info("ROAS Optimizer — live cycle start")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    scaled: list[dict] = []
    paused: list[dict] = []
    kept: list[dict] = []
    errors: list[str] = []

    async with aiohttp.ClientSession() as session:
        # Pull insights from both ad accounts
        all_adsets: list[dict] = []
        for acct in [_ACC, _ACC_INEEDIT]:
            try:
                rows = await _fetch_adset_insights(session, acct)
                for r in rows:
                    r["account"] = acct
                all_adsets.extend(rows)
            except Exception as e:
                errors.append(f"{acct}: {e}")

        log.info("Fetched %d active ad sets", len(all_adsets))

        # Apply scale / pause logic
        for adset in all_adsets:
            try:
                if adset["spend_7d"] >= MIN_SPEND and adset["roas"] < ROAS_PAUSE:
                    ok = await _pause_adset(session, adset)
                    (paused if ok else kept).append(adset)
                elif adset["roas"] >= ROAS_SCALE:
                    ok = await _scale_adset(session, adset)
                    (scaled if ok else kept).append(adset)
                else:
                    kept.append(adset)
            except Exception as e:
                errors.append(f"adset {adset.get('id','?')}: {e}")

        # Create PURCHASE campaign in primary account if none active
        # (ineedit act_2215713609248740 is currently blocked by FB)
        campaign_created = None
        try:
            if not await _has_purchase_campaign(session, _ACC):
                log.info("No active PURCHASE campaign in primary — creating...")
                campaign_created = await _create_purchase_campaign(session)
                if campaign_created:
                    log.info("Created new purchase campaign: %s", campaign_created)
        except Exception as e:
            errors.append(f"campaign_create: {e}")

    # Aggregate stats
    total_spend   = round(sum(a["spend_7d"]   for a in all_adsets), 2)
    total_revenue = round(sum(a["revenue_7d"] for a in all_adsets), 2)
    overall_roas  = round(total_revenue / total_spend, 2) if total_spend > 0 else 0.0

    # Telegram report
    lines = [
        "📊 <b>ROAS Optimizer Report</b>",
        f"🕐 {now}",
        f"💰 Spend 7d: <b>€{total_spend:.2f}</b>  |  Revenue: <b>€{total_revenue:.2f}</b>  |  ROAS: <b>{overall_roas:.2f}x</b>",
        "",
    ]
    if scaled:
        lines.append(f"🚀 <b>SKALIERT (+{SCALE_PCT:.0f}%):</b>")
        for a in scaled:
            lines.append(f"  ✅ {a['name']} | ROAS={a['roas']:.2f}x | €{a['spend_7d']:.0f} Spend")
    if paused:
        lines.append(f"⛔ <b>PAUSIERT (ROAS &lt; {ROAS_PAUSE}x):</b>")
        for a in paused:
            lines.append(f"  🔴 {a['name']} | ROAS={a['roas']:.2f}x | €{a['spend_7d']:.0f} Spend")
    if campaign_created:
        lines.append(f"🆕 <b>Neue Purchase Kampagne erstellt:</b> {campaign_created}")
    if not scaled and not paused and not campaign_created:
        lines.append(f"✅ {len(kept)} Ad Sets im grünen Bereich — kein Eingriff nötig")
    if errors:
        lines.append(f"⚠️ Fehler: {'; '.join(errors[:3])}")

    await _tg("\n".join(lines))

    result = {
        "status": "ok",
        "paused": [a["name"] for a in paused],
        "scaled": [a["name"] for a in scaled],
        "kept":   [a["name"] for a in kept],
        "spend_7d": total_spend,
        "revenue_7d": total_revenue,
        "roas": overall_roas,
        "adsets_total": len(all_adsets),
        "campaign_created": campaign_created,
        "errors": errors,
    }
    log.info("ROAS cycle done — roas=%.2fx spend=€%.2f revenue=€%.2f paused=%d scaled=%d",
             overall_roas, total_spend, total_revenue, len(paused), len(scaled))
    return result


async def get_status() -> dict:
    return {
        "module": "roas_optimizer",
        "meta_configured": bool(_TOKEN),
        "account_primary": _ACC,
        "account_ineedit": _ACC_INEEDIT,
        "pixel": _PIXEL,
        "thresholds": {
            "pause_below": ROAS_PAUSE,
            "scale_above": ROAS_SCALE,
            "scale_pct": SCALE_PCT,
            "min_spend_eur": MIN_SPEND,
            "max_daily_cents": MAX_DAILY,
        },
    }


if __name__ == "__main__":
    import pprint
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = asyncio.run(run_roas_cycle())
    print(f"\n=== ROAS LIVE REPORT ===")
    print(f"Spend 7d:   €{report['spend_7d']:.2f}")
    print(f"Revenue 7d: €{report['revenue_7d']:.2f}")
    print(f"ROAS:       {report['roas']:.2f}x")
    print(f"Paused:     {report['paused']}")
    print(f"Scaled:     {report['scaled']}")
    pprint.pprint(report)
