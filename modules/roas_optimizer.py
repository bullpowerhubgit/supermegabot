"""ROAS Optimizer — reads ads_spend.csv + data/ads_spend.json, calculates ROAS
per campaign, pauses losers via Meta Ads API, scales winners, fires Telegram
alert, and returns a structured report dict.

Thresholds (configurable via env):
  ROAS > 4.0  → Scale budget +20%
  ROAS 2.0-4.0 → Keep / optimize
  ROAS < 2.0  → PAUSE immediately (Meta API call if credentials set)

Main entry point: run_roas_cycle() → dict
"""

import asyncio
import csv
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger(__name__)

# ── Credentials ───────────────────────────────────────────────────────────────
META_ADS_TOKEN     = os.getenv("META_ADS_TOKEN", "") or os.getenv("META_ACCESS_TOKEN", "") or os.getenv("FACEBOOK_PAGE_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Thresholds (env-overridable) ──────────────────────────────────────────────
ROAS_SCALE_THRESHOLD = float(os.getenv("ROAS_SCALE_THRESHOLD", "4.0"))   # scale if >
ROAS_PAUSE_THRESHOLD = float(os.getenv("ROAS_PAUSE_THRESHOLD", "2.0"))   # pause if <
SCALE_BUDGET_PCT     = float(os.getenv("SCALE_BUDGET_PCT", "20.0"))      # % increase

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH  = Path(os.getenv("ADS_SPEND_CSV", str(Path.home() / "ads_spend.csv")))
JSON_PATH = _BASE_DIR / "data" / "ads_spend.json"

META_GRAPH = "https://graph.facebook.com/v19.0"


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    """Send a Telegram message; silently skip when credentials are absent."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram credentials not set — skipping alert")
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as exc:
        log.warning("_tg: %s", exc)


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_csv() -> list[dict]:
    """Load rows from ads_spend.csv."""
    if not CSV_PATH.exists():
        log.warning("CSV not found: %s", CSV_PATH)
        return []
    rows: list[dict] = []
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                rows.append({
                    "date":        row["Date"].strip(),
                    "platform":    row["Platform"].strip(),
                    "campaign":    row["Campaign"].strip(),
                    "ad_set":      row["Ad_Set"].strip(),
                    "objective":   row["Objective"].strip(),
                    "spend_eur":   float(row["Spend_EUR"]),
                    "impressions": int(row["Impressions"]),
                    "clicks":      int(row["Clicks"]),
                    "ctr_pct":     float(row["CTR_%"]),
                    "cpc_eur":     float(row["CPC_EUR"]),
                    "conversions": int(row["Conversions"]),
                    "revenue_eur": float(row["Revenue_EUR"]),
                    "roas":        float(row["ROAS"]),
                })
            except (KeyError, ValueError) as exc:
                log.warning("Skipping malformed CSV row: %s — %s", row, exc)
    log.info("Loaded %d rows from CSV: %s", len(rows), CSV_PATH)
    return rows


def _load_json() -> list[dict]:
    """Load rows from data/ads_spend.json (supplement / override CSV)."""
    if not JSON_PATH.exists():
        return []
    try:
        with JSON_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "rows" in data:
            return data["rows"]
    except Exception as exc:
        log.warning("Could not parse %s: %s", JSON_PATH, exc)
    return []


def _merge_rows(csv_rows: list[dict], json_rows: list[dict]) -> list[dict]:
    """Merge CSV + JSON; deduplicate by (date, platform, campaign, ad_set)."""
    seen: set[tuple] = set()
    merged: list[dict] = []
    for row in csv_rows + json_rows:
        key = (row.get("date"), row.get("platform"), row.get("campaign"), row.get("ad_set"))
        if key not in seen:
            seen.add(key)
            merged.append(row)
    return merged


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate_by_campaign(rows: list[dict]) -> list[dict]:
    """Aggregate metrics by (campaign, platform) summing across all dates / ad_sets."""
    buckets: dict[tuple, dict[str, Any]] = defaultdict(lambda: {
        "spend_eur": 0.0, "revenue_eur": 0.0,
        "impressions": 0, "clicks": 0, "conversions": 0,
        "ad_sets": set(), "platform": "", "dates": [],
    })
    for row in rows:
        key = (row["campaign"], row["platform"])
        b = buckets[key]
        b["spend_eur"]   += row["spend_eur"]
        b["revenue_eur"] += row["revenue_eur"]
        b["impressions"] += row["impressions"]
        b["clicks"]      += row["clicks"]
        b["conversions"] += row["conversions"]
        b["ad_sets"].add(row["ad_set"])
        b["platform"]     = row["platform"]
        b["dates"].append(row["date"])

    results: list[dict] = []
    for (campaign, platform), b in buckets.items():
        spend   = b["spend_eur"]
        revenue = b["revenue_eur"]
        roas    = round(revenue / spend, 2) if spend > 0 else 0.0
        results.append({
            "campaign":    campaign,
            "platform":    platform,
            "ad_sets":     sorted(b["ad_sets"]),
            "spend_eur":   round(spend, 2),
            "revenue_eur": round(revenue, 2),
            "roas":        roas,
            "impressions": b["impressions"],
            "clicks":      b["clicks"],
            "conversions": b["conversions"],
            "date_first":  min(b["dates"]) if b["dates"] else "",
            "date_last":   max(b["dates"]) if b["dates"] else "",
        })
    return sorted(results, key=lambda x: x["roas"], reverse=True)


def _classify(campaigns: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split into (to_pause, to_scale, to_keep)."""
    to_pause, to_scale, to_keep = [], [], []
    for c in campaigns:
        if c["roas"] < ROAS_PAUSE_THRESHOLD:
            to_pause.append(c)
        elif c["roas"] > ROAS_SCALE_THRESHOLD:
            to_scale.append(c)
        else:
            to_keep.append(c)
    return to_pause, to_scale, to_keep


# ── Meta Ads API ──────────────────────────────────────────────────────────────

def _act_id() -> str:
    aid = (META_AD_ACCOUNT_ID or "").strip()
    return aid if aid.startswith("act_") else f"act_{aid}" if aid else ""


async def _meta_find_campaign_id(session: aiohttp.ClientSession, name: str) -> str | None:
    act = _act_id()
    if not act or not META_ADS_TOKEN:
        return None
    try:
        async with session.get(
            f"{META_GRAPH}/{act}/campaigns",
            params={"fields": "id,name,status", "limit": "500", "access_token": META_ADS_TOKEN},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            if r.status != 200:
                log.warning("Meta campaigns list HTTP %s", r.status)
                return None
            for camp in (await r.json()).get("data", []):
                if camp.get("name", "").strip().lower() == name.strip().lower():
                    return camp["id"]
    except Exception as exc:
        log.warning("_meta_find_campaign_id(%s): %s", name, exc)
    return None


async def _meta_pause_campaign(session: aiohttp.ClientSession, campaign_id: str) -> bool:
    if not META_ADS_TOKEN:
        return False
    try:
        async with session.post(
            f"{META_GRAPH}/{campaign_id}",
            data={"status": "PAUSED", "access_token": META_ADS_TOKEN},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                return bool((await r.json()).get("success"))
            log.warning("Meta pause HTTP %s for %s", r.status, campaign_id)
    except Exception as exc:
        log.warning("_meta_pause_campaign(%s): %s", campaign_id, exc)
    return False


async def _meta_scale_campaign(
    session: aiohttp.ClientSession, campaign_id: str, scale_pct: float
) -> bool:
    if not META_ADS_TOKEN:
        return False
    try:
        async with session.get(
            f"{META_GRAPH}/{campaign_id}/adsets",
            params={"fields": "id,daily_budget,status", "access_token": META_ADS_TOKEN},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status != 200:
                return False
            adsets = (await r.json()).get("data", [])

        scaled_any = False
        for adset in adsets:
            if adset.get("status") != "ACTIVE":
                continue
            current = int(adset.get("daily_budget", 0))
            if current <= 0:
                continue
            new_budget = int(current * (1 + scale_pct / 100))
            async with session.post(
                f"{META_GRAPH}/{adset['id']}",
                data={"daily_budget": str(new_budget), "access_token": META_ADS_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as rr:
                if rr.status == 200:
                    scaled_any = True
                    log.info("Scaled adset %s: %d → %d", adset["id"], current, new_budget)
        return scaled_any
    except Exception as exc:
        log.warning("_meta_scale_campaign(%s): %s", campaign_id, exc)
    return False


async def _apply_meta_actions(
    to_pause: list[dict], to_scale: list[dict]
) -> tuple[list[str], list[str]]:
    paused_ids: list[str] = []
    scaled_ids: list[str] = []

    if not META_ADS_TOKEN or not META_AD_ACCOUNT_ID:
        log.info("META_ADS_TOKEN / META_AD_ACCOUNT_ID not set — skipping live API calls")
        return paused_ids, scaled_ids

    async with aiohttp.ClientSession() as session:
        for c in to_pause:
            if c["platform"].lower() != "meta":
                continue
            cid = await _meta_find_campaign_id(session, c["campaign"])
            if cid and await _meta_pause_campaign(session, cid):
                paused_ids.append(c["campaign"])
                log.info("PAUSED Meta campaign: %s (ROAS %.2fx)", c["campaign"], c["roas"])
            else:
                log.warning("Could not pause Meta campaign: %s", c["campaign"])

        for c in to_scale:
            if c["platform"].lower() != "meta":
                continue
            cid = await _meta_find_campaign_id(session, c["campaign"])
            if cid and await _meta_scale_campaign(session, cid, SCALE_BUDGET_PCT):
                scaled_ids.append(c["campaign"])
                log.info("SCALED Meta campaign: %s (ROAS %.2fx +%.0f%%)",
                         c["campaign"], c["roas"], SCALE_BUDGET_PCT)

    return paused_ids, scaled_ids


# ── Telegram message ──────────────────────────────────────────────────────────

def _build_tg_message(
    to_pause: list[dict], to_scale: list[dict], to_keep: list[dict],
    paused_ids: list[str], scaled_ids: list[str],
    total_spend: float, total_revenue: float, overall_roas: float,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "<b>ROAS Optimizer Report</b>",
        f"Datum: {now}",
        f"Gesamtausgaben: <b>EUR {total_spend:,.2f}</b>  |  "
        f"Umsatz: <b>EUR {total_revenue:,.2f}</b>  |  "
        f"Overall ROAS: <b>{overall_roas:.2f}x</b>",
        "",
    ]
    if to_pause:
        lines.append(f"<b>PAUSE sofort (ROAS &lt; {ROAS_PAUSE_THRESHOLD}x)</b>")
        for c in to_pause:
            tag = " [API pausiert]" if c["campaign"] in paused_ids else " [manuell pausieren!]"
            lines.append(
                f"  - {c['campaign']} [{c['platform']}] "
                f"ROAS={c['roas']:.2f}x  Spend=EUR{c['spend_eur']:.0f}{tag}"
            )
    if to_scale:
        lines.append("")
        lines.append(f"<b>SKALIEREN +{SCALE_BUDGET_PCT:.0f}% (ROAS &gt; {ROAS_SCALE_THRESHOLD}x)</b>")
        for c in to_scale:
            tag = " [API skaliert]" if c["campaign"] in scaled_ids else ""
            lines.append(
                f"  - {c['campaign']} [{c['platform']}] "
                f"ROAS={c['roas']:.2f}x  Spend=EUR{c['spend_eur']:.0f}{tag}"
            )
    if to_keep:
        lines.append("")
        lines.append(f"<b>BEHALTEN / optimieren (ROAS {ROAS_PAUSE_THRESHOLD}-{ROAS_SCALE_THRESHOLD}x)</b>")
        for c in to_keep:
            lines.append(
                f"  - {c['campaign']} [{c['platform']}] "
                f"ROAS={c['roas']:.2f}x  Spend=EUR{c['spend_eur']:.0f}"
            )
    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_roas_cycle() -> dict:
    """
    Full ROAS optimization cycle.

    Returns
    -------
    dict:
        paused          list[str]  — campaign names paused via Meta API
        scaled          list[str]  — campaign names scaled via Meta API
        kept            list[str]  — campaign names in keep/optimize zone
        recommendations list[dict] — {campaign, platform, roas, action, reason, api_done}
        total_spend     float      — EUR
        total_revenue   float      — EUR
        overall_roas    float
        campaigns       list[dict] — full aggregated campaign metrics
    """
    log.info("ROAS Optimizer — starting cycle")

    csv_rows  = _load_csv()
    json_rows = _load_json()
    all_rows  = _merge_rows(csv_rows, json_rows)

    if not all_rows:
        log.warning("No ad spend data found — aborting")
        return {
            "paused": [], "scaled": [], "kept": [], "recommendations": [],
            "total_spend": 0.0, "total_revenue": 0.0, "overall_roas": 0.0,
            "campaigns": [],
        }

    campaigns              = _aggregate_by_campaign(all_rows)
    to_pause, to_scale, to_keep = _classify(campaigns)

    total_spend   = round(sum(c["spend_eur"]   for c in campaigns), 2)
    total_revenue = round(sum(c["revenue_eur"] for c in campaigns), 2)
    overall_roas  = round(total_revenue / total_spend, 2) if total_spend > 0 else 0.0

    log.info(
        "pause=%d scale=%d keep=%d  total_spend=EUR%.2f  overall_roas=%.2fx",
        len(to_pause), len(to_scale), len(to_keep), total_spend, overall_roas,
    )

    paused_ids, scaled_ids = await _apply_meta_actions(to_pause, to_scale)

    recommendations: list[dict] = []
    for c in to_pause:
        recommendations.append({
            "campaign": c["campaign"], "platform": c["platform"], "roas": c["roas"],
            "action": "PAUSE",
            "reason": f"ROAS {c['roas']:.2f}x < {ROAS_PAUSE_THRESHOLD}x — sofort pausieren",
            "api_done": c["campaign"] in paused_ids,
        })
    for c in to_scale:
        recommendations.append({
            "campaign": c["campaign"], "platform": c["platform"], "roas": c["roas"],
            "action": "SCALE",
            "reason": f"ROAS {c['roas']:.2f}x > {ROAS_SCALE_THRESHOLD}x — Budget +{SCALE_BUDGET_PCT:.0f}%",
            "api_done": c["campaign"] in scaled_ids,
        })
    for c in to_keep:
        recommendations.append({
            "campaign": c["campaign"], "platform": c["platform"], "roas": c["roas"],
            "action": "KEEP",
            "reason": f"ROAS {c['roas']:.2f}x — beobachten & optimieren",
            "api_done": False,
        })

    msg = _build_tg_message(
        to_pause, to_scale, to_keep, paused_ids, scaled_ids,
        total_spend, total_revenue, overall_roas,
    )
    await _tg(msg)
    log.info("Telegram alert sent")

    result = {
        "paused":          [c["campaign"] for c in to_pause],
        "scaled":          [c["campaign"] for c in to_scale],
        "kept":            [c["campaign"] for c in to_keep],
        "recommendations": recommendations,
        "total_spend":     total_spend,
        "total_revenue":   total_revenue,
        "overall_roas":    overall_roas,
        "campaigns":       campaigns,
    }
    log.info("ROAS Optimizer — done. paused=%s scaled=%s", result["paused"], result["scaled"])
    return result


async def get_status() -> dict:
    """Return current module config / thresholds (no API calls)."""
    return {
        "module": "roas_optimizer",
        "csv_path": str(CSV_PATH),
        "json_path": str(JSON_PATH),
        "csv_exists": CSV_PATH.exists(),
        "json_exists": JSON_PATH.exists(),
        "meta_configured": bool(META_ADS_TOKEN and META_AD_ACCOUNT_ID),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "thresholds": {
            "pause_below":  ROAS_PAUSE_THRESHOLD,
            "scale_above":  ROAS_SCALE_THRESHOLD,
            "scale_pct":    SCALE_BUDGET_PCT,
        },
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = asyncio.run(run_roas_cycle())
    print(f"\n=== ROAS OPTIMIZER REPORT ===")
    print(f"Total Spend:   EUR {report['total_spend']:,.2f}")
    print(f"Total Revenue: EUR {report['total_revenue']:,.2f}")
    print(f"Overall ROAS:  {report['overall_roas']:.2f}x")
    print(f"\nPAUSED ({len(report['paused'])}): {report['paused']}")
    print(f"SCALED ({len(report['scaled'])}): {report['scaled']}")
    print(f"KEPT   ({len(report['kept'])}): {report['kept']}")
    print("\nRecommendations:")
    pprint.pprint(report["recommendations"])
