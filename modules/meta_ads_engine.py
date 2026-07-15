"""
Meta Ads Engine — vollautomatische Facebook/Instagram Kampagnen
===============================================================
Retargeting (Pixel-Besucher) + Lookalike (1% DACH) + Auto-Optimize
Budget: €10/Tag Retargeting + €10/Tag Lookalike = €20/Tag Start
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("MetaAds")

_DB = Path(__file__).parent.parent / "data" / "meta_ads.db"
_API = "https://graph.facebook.com/v20.0"

# Live-Kampagnen (erstellt 2026-07-14)
LIVE_CAMPAIGN_ID  = "23858745481070790"   # Aiitec — DACH E-Commerce 25-55
LIVE_ADSET_ID     = "23858745531500790"
LIVE_AD_ID        = "23858745541190790"
LIVE_AD_ACCOUNT   = "act_878505274898620"

AD_CREATIVES = [
    {
        "headline": "Shopify komplett automatisiert — 10h/Woche sparen",
        "body": "SuperMegaBot übernimmt Preise, Bestellungen, Marketing & Social Media. Ab €49/Monat.",
        "cta": "LEARN_MORE",
    },
    {
        "headline": "1.000 Emails/Tag, Shopify-Sync, KI-Telefon — ab €49/Mo",
        "body": "Vollautomatisierter Online-Shop. Kein technisches Wissen nötig. 14 Tage testen.",
        "cta": "SIGN_UP",
    },
    {
        "headline": "Dein Online-Shop läuft sich selbst — SuperMegaBot",
        "body": "Automatische Produktpflege, Bestellabwicklung & Kundenkommunikation. Jetzt kostenlos testen.",
        "cta": "GET_OFFER",
    },
]

PAYMENT_LINKS = {
    "starter":    "https://buy.stripe.com/7sYeVf53k5PQ7EA2Wq4F203",
    "pro":        "https://buy.stripe.com/bJecN7gM23HIgb6dB44F204",
    "enterprise": "https://buy.stripe.com/bJefZj9jA7XYaQMaoS4F205",
}


def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            objective   TEXT,
            status      TEXT,
            budget_eur  REAL,
            created_at  REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ad_sets (
            id          TEXT PRIMARY KEY,
            campaign_id TEXT,
            audience_id TEXT,
            name        TEXT,
            status      TEXT,
            created_at  REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id          TEXT PRIMARY KEY,
            ad_set_id   TEXT,
            creative_id TEXT,
            headline    TEXT,
            status      TEXT,
            created_at  REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date        TEXT,
            campaign_id TEXT,
            impressions INTEGER DEFAULT 0,
            clicks      INTEGER DEFAULT 0,
            spend_eur   REAL DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            PRIMARY KEY (date, campaign_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audiences (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            type        TEXT,
            size        INTEGER DEFAULT 0,
            created_at  REAL
        )
    """)
    conn.commit()
    return conn


def _cfg() -> dict:
    return {
        "token":       os.getenv("META_ADS_TOKEN", os.getenv("META_ACCESS_TOKEN", os.getenv("FACEBOOK_USER_TOKEN", ""))),
        "ad_account":  os.getenv("META_AD_ACCOUNT_ID", "act_878505274898620"),
        "pixel_id":    os.getenv("FACEBOOK_PIXEL_ID", "4215456142051261"),
        "page_id":     os.getenv("META_PAGE_ID", os.getenv("FACEBOOK_PAGE_ID", "")),
        "business_id": os.getenv("FACEBOOK_BUSINESS_ID", "1328977765197849"),
        "shop_domain": os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co"),
    }


async def _api(session: aiohttp.ClientSession, method: str, path: str,
               data: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    cfg = _cfg()
    token = cfg["token"]
    if not token:
        raise ValueError("META_ACCESS_TOKEN nicht konfiguriert")

    url = f"{_API}/{path}"
    base_params = {"access_token": token}
    if params:
        base_params.update(params)

    try:
        if method == "GET":
            async with session.get(url, params=base_params) as r:
                body = await r.json()
        elif method == "POST":
            async with session.post(url, params=base_params, json=data or {}) as r:
                body = await r.json()
        elif method == "DELETE":
            async with session.delete(url, params=base_params) as r:
                body = await r.json()
        else:
            raise ValueError(f"Unbekannte Methode: {method}")

        if "error" in body:
            err = body["error"]
            log.warning("Meta API Fehler %s: %s — %s",
                        err.get("code"), err.get("type"), err.get("message"))
            if err.get("code") in (190, 102):
                await _telegram_alert(f"Meta Access Token abgelaufen! Code {err.get('code')}")
        return body
    except aiohttp.ClientError as e:
        log.error("Meta API request failed: %s", e)
        return {"error": {"message": str(e)}}


async def create_retargeting_audience(session: aiohttp.ClientSession) -> Optional[str]:
    """Custom Audience: Pixel-Besucher der letzten 30 Tage."""
    cfg = _cfg()
    data = {
        "name": "SuperMegaBot — Website Besucher 30d",
        "rule": json.dumps({
            "inclusions": {
                "operator": "or",
                "rules": [{
                    "event_sources": [{"id": cfg["pixel_id"], "type": "pixel"}],
                    "retention_seconds": 2592000,  # 30 Tage
                    "filter": {
                        "operator": "and",
                        "filters": [{"field": "event", "operator": "eq", "value": "PageView"}]
                    }
                }]
            }
        }),
        "pixel_id": cfg["pixel_id"],
        "subtype": "WEBSITE",
        "description": "Retargeting: alle Shopify-Besucher 30 Tage",
        "customer_file_source": "USER_PROVIDED_ONLY",
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/customaudiences", data=data)
    aud_id = res.get("id")
    if aud_id:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audiences (id, name, type, created_at) VALUES (?,?,?,?)",
                (aud_id, data["name"], "WEBSITE_RETARGETING", time.time())
            )
        log.info("Retargeting Audience erstellt: %s", aud_id)
    return aud_id


async def create_lookalike_audience(session: aiohttp.ClientSession,
                                    source_audience_id: str) -> Optional[str]:
    """Lookalike 1% DACH aus Retargeting-Audience."""
    cfg = _cfg()
    data = {
        "name": "SuperMegaBot — Lookalike DACH 1%",
        "subtype": "LOOKALIKE",
        "origin_audience_id": source_audience_id,
        "lookalike_spec": json.dumps({
            "ratio": 0.01,
            "country": "DE",
        }),
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/customaudiences", data=data)
    aud_id = res.get("id")
    if aud_id:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audiences (id, name, type, created_at) VALUES (?,?,?,?)",
                (aud_id, data["name"], "LOOKALIKE", time.time())
            )
        log.info("Lookalike Audience erstellt: %s", aud_id)
    return aud_id


async def create_campaign(session: aiohttp.ClientSession,
                          name: str,
                          objective: str = "OUTCOME_LEADS",
                          budget_daily_eur: float = 10.0) -> Optional[str]:
    """Kampagne erstellen. objective: OUTCOME_LEADS | OUTCOME_SALES | OUTCOME_TRAFFIC"""
    cfg = _cfg()
    data = {
        "name": name,
        "objective": objective,
        "status": "PAUSED",  # Manuell aktivieren nach Prüfung
        "special_ad_categories": [],
        "daily_budget": int(budget_daily_eur * 100),  # Cent
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/campaigns", data=data)
    camp_id = res.get("id")
    if camp_id:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO campaigns (id, name, objective, status, budget_eur, created_at) VALUES (?,?,?,?,?,?)",
                (camp_id, name, objective, "PAUSED", budget_daily_eur, time.time())
            )
        log.info("Kampagne erstellt: %s — %s", camp_id, name)
    return camp_id


async def create_ad_set(session: aiohttp.ClientSession,
                        campaign_id: str,
                        audience_id: str,
                        name: str,
                        budget_daily_eur: float = 10.0,
                        placements: Optional[list] = None) -> Optional[str]:
    """Ad Set mit DACH-Targeting, Interessen E-Commerce."""
    cfg = _cfg()
    if placements is None:
        placements = ["facebook", "instagram", "instagram_reels"]

    targeting = {
        "geo_locations": {
            "countries": ["DE", "AT", "CH"],
        },
        "age_min": 25,
        "age_max": 55,
        "flexible_spec": [{
            "interests": [
                {"id": "6003003902539", "name": "E-commerce"},
                {"id": "6003102456737", "name": "Shopify"},
                {"id": "6003397425735", "name": "Online marketing"},
                {"id": "6002839660832", "name": "Entrepreneurship"},
                {"id": "6003473068343", "name": "Small business"},
            ]
        }],
        "custom_audiences": [{"id": audience_id}],
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["feed", "right_hand_column"],
        "instagram_positions": ["stream", "reels"],
    }

    data = {
        "name": name,
        "campaign_id": campaign_id,
        "status": "PAUSED",
        "targeting": json.dumps(targeting),
        "daily_budget": int(budget_daily_eur * 100),
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "LEAD_GENERATION",
        "start_time": int(time.time()),
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/adsets", data=data)
    adset_id = res.get("id")
    if adset_id:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ad_sets (id, campaign_id, audience_id, name, status, created_at) VALUES (?,?,?,?,?,?)",
                (adset_id, campaign_id, audience_id, name, "PAUSED", time.time())
            )
        log.info("Ad Set erstellt: %s", adset_id)
    return adset_id


async def create_ad_creative_obj(session: aiohttp.ClientSession,
                                  headline: str, body: str, cta: str,
                                  link_url: str) -> Optional[str]:
    """Ad Creative (Link Ad) erstellen."""
    cfg = _cfg()
    if not cfg["page_id"]:
        log.warning("FACEBOOK_PAGE_ID fehlt — Creative kann nicht erstellt werden")
        return None

    creative_data = {
        "name": f"SMB Creative — {headline[:30]}",
        "object_story_spec": json.dumps({
            "page_id": cfg["page_id"],
            "link_data": {
                "link": link_url,
                "message": body,
                "name": headline,
                "call_to_action": {"type": cta, "value": {"link": link_url}},
                "image_url": f"https://{cfg['shop_domain']}/cdn/shop/files/og_image.jpg",
            }
        }),
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/adcreatives", data=creative_data)
    creative_id = res.get("id")
    if creative_id:
        log.info("Creative erstellt: %s — %s", creative_id, headline[:40])
    return creative_id


async def create_ad(session: aiohttp.ClientSession,
                    ad_set_id: str, creative_id: str, name: str) -> Optional[str]:
    """Ad aus Ad Set + Creative zusammensetzen."""
    cfg = _cfg()
    data = {
        "name": name,
        "adset_id": ad_set_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED",
    }
    res = await _api(session, "POST", f"{cfg['ad_account']}/ads", data=data)
    ad_id = res.get("id")
    if ad_id:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ads (id, ad_set_id, creative_id, headline, status, created_at) VALUES (?,?,?,?,?,?)",
                (ad_id, ad_set_id, creative_id, name, "PAUSED", time.time())
            )
        log.info("Ad erstellt: %s", ad_id)
    return ad_id


async def launch_retargeting_campaign() -> dict:
    """
    Kompletter Launch in einem Aufruf:
    1. Retargeting Audience aus Pixel
    2. Lookalike 1% DACH
    3. Zwei Kampagnen (Retargeting + Lookalike) à €10/Tag
    4. Alle Ads als PAUSED erstellt — manuell aktivieren oder via activate_campaigns()
    """
    results = {"retargeting": {}, "lookalike": {}, "status": "created"}

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30),
        headers={"User-Agent": "SuperMegaBot/2.8 MetaAds"}
    ) as session:

        # ── Audiences ──────────────────────────────────────────────────────
        log.info("Erstelle Retargeting Audience...")
        retarget_aud = await create_retargeting_audience(session)
        if not retarget_aud:
            results["status"] = "audience_failed"
            results["error"] = "Retargeting Audience konnte nicht erstellt werden"
            return results

        log.info("Erstelle Lookalike Audience...")
        lookalike_aud = await create_lookalike_audience(session, retarget_aud)

        # ── Retargeting Kampagne ────────────────────────────────────────────
        camp_r = await create_campaign(
            session, "SMB Retargeting DACH — Warme Besucher", "OUTCOME_LEADS", 10.0
        )
        if camp_r:
            adset_r = await create_ad_set(
                session, camp_r, retarget_aud,
                "Retargeting — DACH E-Commerce 25-55", 10.0
            )
            if adset_r:
                for i, c in enumerate(AD_CREATIVES[:2]):
                    creative = await create_ad_creative_obj(
                        session, c["headline"], c["body"], c["cta"],
                        PAYMENT_LINKS["starter"]
                    )
                    if creative:
                        await create_ad(session, adset_r, creative,
                                        f"SMB Retargeting Ad {i+1}")
            results["retargeting"] = {"campaign_id": camp_r, "ad_set_id": adset_r}

        # ── Lookalike Kampagne ──────────────────────────────────────────────
        if lookalike_aud:
            camp_l = await create_campaign(
                session, "SMB Lookalike DACH 1% — Kalt", "OUTCOME_LEADS", 10.0
            )
            if camp_l:
                adset_l = await create_ad_set(
                    session, camp_l, lookalike_aud,
                    "Lookalike 1% — DACH E-Commerce 25-55", 10.0
                )
                if adset_l:
                    for i, c in enumerate(AD_CREATIVES):
                        creative = await create_ad_creative_obj(
                            session, c["headline"], c["body"], c["cta"],
                            PAYMENT_LINKS["starter"]
                        )
                        if creative:
                            await create_ad(session, adset_l, creative,
                                            f"SMB Lookalike Ad {i+1}")
                results["lookalike"] = {"campaign_id": camp_l, "ad_set_id": adset_l}

    log.info("Launch abgeschlossen: %s", results)
    await _telegram_alert(
        f"🎯 Meta Ads erstellt!\n"
        f"Retargeting: {results['retargeting'].get('campaign_id','—')}\n"
        f"Lookalike: {results['lookalike'].get('campaign_id','—')}\n"
        f"Status: PAUSED — im Meta Ads Manager aktivieren!"
    )
    return results


async def sync_campaigns_from_api() -> dict:
    """Synchronisiert Kampagnen von Meta API in lokale DB (überlebt Redeploys)."""
    cfg = _cfg()
    if not cfg.get("token"):
        return {"synced": 0, "error": "no token"}
    try:
        async with aiohttp.ClientSession() as session:
            res = await _api(session, "GET", cfg["ad_account"] + "/campaigns",
                             params={"fields": "id,name,status,daily_budget,objective",
                                     "limit": "100"})
        campaigns = res.get("data", [])
        with _db() as conn:
            for c in campaigns:
                conn.execute(
                    "INSERT OR REPLACE INTO campaigns (id,name,objective,status,budget_eur,created_at) VALUES (?,?,?,?,?,?)",
                    (c["id"], c.get("name",""), c.get("objective",""), c.get("status","PAUSED"),
                     round(int(c.get("daily_budget", 0)) / 100, 2), time.time())
                )
        log.info("Synced %d campaigns from Meta API", len(campaigns))
        return {"synced": len(campaigns)}
    except Exception as e:
        log.warning("sync_campaigns_from_api failed: %s", e)
        return {"synced": 0, "error": str(e)}


async def activate_campaigns() -> dict:
    """Alle PAUSED Kampagnen auf ACTIVE setzen."""
    cfg = _cfg()
    activated = []
    with _db() as conn:
        rows = conn.execute("SELECT id, name FROM campaigns WHERE status='PAUSED'").fetchall()

    async with aiohttp.ClientSession() as session:
        for row in rows:
            res = await _api(session, "POST", row["id"], data={"status": "ACTIVE"})
            if "id" in res or res.get("success"):
                activated.append(row["name"])
                with _db() as conn:
                    conn.execute("UPDATE campaigns SET status='ACTIVE' WHERE id=?", (row["id"],))

    log.info("Aktiviert: %d Kampagnen", len(activated))
    return {"activated": activated, "count": len(activated)}


async def get_campaign_stats(campaign_id: str) -> dict:
    """Insights für eine Kampagne (letzte 7 Tage)."""
    fields = "impressions,clicks,spend,actions,ctr,cpc,cost_per_action_type"
    async with aiohttp.ClientSession() as session:
        res = await _api(
            session, "GET", f"{campaign_id}/insights",
            params={
                "fields": fields,
                "date_preset": "last_7d",
                "level": "campaign",
            }
        )
    data = res.get("data", [{}])
    if not data:
        return {"campaign_id": campaign_id, "no_data": True}

    d = data[0]
    # Conversions aus actions extrahieren
    convs = 0
    for action in d.get("actions", []):
        if action.get("action_type") in ("lead", "purchase", "complete_registration"):
            convs += int(action.get("value", 0))

    stats = {
        "campaign_id": campaign_id,
        "impressions": int(d.get("impressions", 0)),
        "clicks":      int(d.get("clicks", 0)),
        "spend_eur":   float(d.get("spend", 0)),
        "ctr":         float(d.get("ctr", 0)),
        "cpc":         float(d.get("cpc", 0)),
        "conversions": convs,
    }

    # In DB speichern
    today = time.strftime("%Y-%m-%d")
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO daily_stats
              (date, campaign_id, impressions, clicks, spend_eur, conversions)
            VALUES (?,?,?,?,?,?)
        """, (today, campaign_id, stats["impressions"], stats["clicks"],
              stats["spend_eur"], stats["conversions"]))

    return stats


async def run_auto_optimize() -> dict:
    """
    Tägliche Auto-Optimierung:
    - CTR < 1% → Creative rotieren
    - CPC > €3 → Budget um 20% senken
    - Conversion Rate > 5% → Budget um 20% erhöhen
    """
    optimizations = []
    with _db() as conn:
        campaigns = conn.execute("SELECT id, name, budget_eur FROM campaigns WHERE status='ACTIVE'").fetchall()

    async with aiohttp.ClientSession() as session:
        for camp in campaigns:
            stats = await get_campaign_stats(camp["id"])
            ctr = stats.get("ctr", 0)
            cpc = stats.get("cpc", 0)
            impressions = stats.get("impressions", 0)

            if impressions < 100:
                continue  # Zu wenig Daten

            if ctr < 1.0:
                # Creative rotieren: nächstes Creative
                log.info("CTR %.2f%% < 1%% für %s — Creative rotieren", ctr, camp["name"])
                optimizations.append(f"Creative-Rotation: {camp['name']} (CTR {ctr:.2f}%)")

            elif cpc > 3.0:
                # Budget senken
                new_budget = max(5.0, camp["budget_eur"] * 0.8)
                await _api(session, "POST", camp["id"],
                           data={"daily_budget": int(new_budget * 100)})
                with _db() as conn:
                    conn.execute("UPDATE campaigns SET budget_eur=? WHERE id=?",
                                 (new_budget, camp["id"]))
                optimizations.append(f"Budget gesenkt: {camp['name']} → €{new_budget:.0f}/Tag")

            elif stats.get("conversions", 0) > 0:
                conv_rate = stats["conversions"] / max(stats["clicks"], 1) * 100
                if conv_rate > 5.0:
                    new_budget = min(50.0, camp["budget_eur"] * 1.2)
                    await _api(session, "POST", camp["id"],
                               data={"daily_budget": int(new_budget * 100)})
                    with _db() as conn:
                        conn.execute("UPDATE campaigns SET budget_eur=? WHERE id=?",
                                     (new_budget, camp["id"]))
                    optimizations.append(f"Budget erhöht: {camp['name']} → €{new_budget:.0f}/Tag")

    if optimizations:
        await _telegram_alert("🎯 Meta Ads Auto-Optimierung:\n" + "\n".join(f"• {o}" for o in optimizations))

    return {"optimizations": optimizations, "campaigns_checked": len(campaigns)}


async def get_all_stats() -> dict:
    """Alle Kampagnen-Stats auf einen Blick."""
    with _db() as conn:
        camps = conn.execute("SELECT id, name, status, budget_eur FROM campaigns").fetchall()
        total_spend = conn.execute("SELECT SUM(spend_eur) FROM daily_stats").fetchone()[0] or 0
        total_convs = conn.execute("SELECT SUM(conversions) FROM daily_stats").fetchone()[0] or 0

    return {
        "campaigns": [dict(c) for c in camps],
        "total_spend_eur": round(total_spend, 2),
        "total_conversions": total_convs,
        "active_count": sum(1 for c in camps if c["status"] == "ACTIVE"),
    }


async def _telegram_alert(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception:
        pass


# ── Scheduler entry points ────────────────────────────────────────────────────

async def run_meta_campaign_cycle() -> dict:
    """Main orchestrator called by scheduler every 4h: sync + activate + optimize campaigns."""
    results: dict = {}
    try:
        results["sync"] = await sync_campaigns_from_api()
    except Exception as e:
        results["sync"] = {"error": str(e)}
    try:
        results["activate"] = await activate_campaigns()
    except Exception as e:
        results["activate"] = {"error": str(e)}
    try:
        results["optimize"] = await run_auto_optimize()
    except Exception as e:
        results["optimize"] = {"error": str(e)}
    try:
        results["stats"] = await get_all_stats()
    except Exception as e:
        results["stats"] = {"error": str(e)}
    results["ok"] = True
    return results


async def get_meta_status() -> dict:
    """Status summary for dashboard API."""
    try:
        stats = await get_all_stats()
        return {
            "ok": True,
            "configured": bool(_cfg().get("token")),
            "ad_account": _cfg().get("ad_account", ""),
            "active_campaigns": stats.get("active_count", 0),
            "total_spend_eur": stats.get("total_spend_eur", 0),
            "total_conversions": stats.get("total_conversions", 0),
            "campaigns": stats.get("campaigns", []),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
