"""
Meta Ads ROAS Maximizer — GaN Charger 240W | ineedit.com.co
============================================================
Erstellt CBO-Kampagne mit 3 Ad-Sets und 3 Creative-Varianten.
Zieht live ROAS aus Meta Insights API.
Auto-scale wenn ROAS > 3.5 | Auto-pause wenn ROAS < 1.8 (nach €10 Spend).
Entry-Points: run_roas_max() | get_roas_stats()
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

log = logging.getLogger("MetaROASMax")

_BASE   = Path(__file__).parent.parent
_DB     = _BASE / "data" / "meta_roas_max.db"
_GRAPH  = "https://graph.facebook.com/v20.0"

# ── Credentials ───────────────────────────────────────────────────────────────

def _creds() -> dict:
    token = (
        os.getenv("META_ADS_TOKEN")
        or os.getenv("FACEBOOK_PAGE_TOKEN_AIITEC")
        or os.getenv("FACEBOOK_PAGE_TOKEN")
        or ""
    )
    return {
        "token":      token,
        "account":    os.getenv("META_AD_ACCOUNT_ID", "act_878505274898620"),
        "pixel_id":   os.getenv("FACEBOOK_PIXEL_ID", "4215456142051261"),
        "page_id":    os.getenv("META_PAGE_ID", os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")),
        "shop_url":   f"https://{os.getenv('SHOPIFY_PUBLIC_DOMAIN', 'ineedit.com.co')}",
        "budget_eur": float(os.getenv("META_DAILY_BUDGET_EUR", "30")),
    }


# ── Database ──────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            status      TEXT,
            objective   TEXT,
            budget_eur  REAL,
            created_at  REAL
        );
        CREATE TABLE IF NOT EXISTS ad_sets (
            id          TEXT PRIMARY KEY,
            campaign_id TEXT,
            name        TEXT,
            status      TEXT,
            type        TEXT,
            created_at  REAL
        );
        CREATE TABLE IF NOT EXISTS ads (
            id          TEXT PRIMARY KEY,
            ad_set_id   TEXT,
            variant     INTEGER,
            status      TEXT,
            created_at  REAL
        );
        CREATE TABLE IF NOT EXISTS insights_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT,
            date_start  TEXT,
            date_stop   TEXT,
            spend       REAL,
            revenue     REAL,
            roas        REAL,
            impressions INTEGER,
            clicks      INTEGER,
            purchases   INTEGER,
            recorded_at REAL
        );
        CREATE TABLE IF NOT EXISTS optimization_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action      TEXT,
            campaign_id TEXT,
            reason      TEXT,
            old_budget  REAL,
            new_budget  REAL,
            recorded_at REAL
        );
    """)
    conn.commit()
    return conn


# ── Ad Copy Varianten (DE, proven hooks) ─────────────────────────────────────

PRODUCT_URL_HANDLE = "240w-gan-ladegerat-4-ports-fuer-macbook-iphone-ipad"

CREATIVES = [
    {
        "variant": 1,
        "hook":    "Problem/Solution",
        "title":   "Schluss mit Kabelchaos — 1 Stecker für alles",
        "body":    (
            "MacBook, iPhone, iPad, AirPods — gleichzeitig laden. "
            "240W GaN-Technologie. 4 Ports. Kein Überhitzen.\n"
            "Jetzt 31% günstiger: 103,99€ statt 149,99€ ✓ Kostenloser Versand ✓ 30 Tage Rückgabe"
        ),
        "cta": "SHOP_NOW",
    },
    {
        "variant": 2,
        "hook":    "Authority",
        "title":   "Das Ladegerät, das Tech-Profis empfehlen",
        "body":    (
            "240W GaN-Charger für Home-Office & Reise. "
            "4 Geräte gleichzeitig, kein Netzteiltausch mehr.\n"
            "✓ DE Lager ✓ 30T Rückgabe ✓ Heute -31%: 103,99€"
        ),
        "cta": "LEARN_MORE",
    },
    {
        "variant": 3,
        "hook":    "Urgency",
        "title":   "Nur noch heute: 240W GaN Charger −31%",
        "body":    (
            "⚡ Aktionspreis läuft heute Mitternacht ab.\n"
            "4 Ports · MacBook + iPhone + iPad · USB-C & USB-A\n"
            "103,99€ statt 149,99€ — Versand aus DE, 30 Tage Rückgabe."
        ),
        "cta": "GET_OFFER",
    },
]

# ── Targeting specs ───────────────────────────────────────────────────────────

def _targeting_broad() -> dict:
    """Advantage+ Audience — Meta KI übernimmt."""
    return {
        "geo_locations": {"countries": ["DE", "AT", "CH"]},
        "age_min": 22,
        "age_max": 65,
        "locales": [6],   # Deutsch
    }

def _targeting_interests() -> dict:
    """Interesse: Technik/Gadgets/Home-Office DE/AT/CH."""
    return {
        "geo_locations": {"countries": ["DE", "AT", "CH"]},
        "age_min": 25,
        "age_max": 60,
        "locales": [6],
        "flexible_spec": [{
            "interests": [
                {"id": "6003107902433", "name": "Technology"},
                {"id": "6003195167754", "name": "Consumer electronics"},
                {"id": "6004141684642", "name": "Home office"},
                {"id": "6003257161714", "name": "Gadget"},
            ]
        }],
        "publisher_platforms": ["facebook", "instagram"],
    }

def _targeting_retargeting(pixel_id: str) -> dict:
    """Pixel-Besucher letzter 30 Tage."""
    return {
        "geo_locations": {"countries": ["DE", "AT", "CH"]},
        "custom_audiences": [
            {"id": f"pixel_{pixel_id}_30d"}  # wird durch echte Custom Audience ID ersetzt
        ],
    }


# ── Meta API helper ───────────────────────────────────────────────────────────

async def _api(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    creds = _creds()
    token = creds["token"]
    if not token:
        return {"error": {"message": "META_ADS_TOKEN fehlt"}}

    url      = f"{_GRAPH}/{path}"
    p        = {"access_token": token}
    if params:
        p.update(params)

    try:
        to = aiohttp.ClientTimeout(total=timeout)
        if method == "GET":
            async with session.get(url, params=p, timeout=to) as r:
                result = await r.json()
        else:
            async with session.post(url, params=p, json=data or {}, timeout=to) as r:
                result = await r.json()

        if "error" in result:
            err = result["error"]
            log.warning("Meta API %s: %s", err.get("code"), err.get("message", "")[:120])
        return result
    except Exception as exc:
        log.error("Meta API %s %s: %s", method, path, exc)
        return {"error": {"message": str(exc)}}


# ── Campaign creation ─────────────────────────────────────────────────────────

async def _find_campaign(session: aiohttp.ClientSession, name: str) -> Optional[str]:
    creds = _creds()
    res = await _api(session, "GET", f"{creds['account']}/campaigns",
                     params={"fields": "id,name", "limit": "200"})
    for c in res.get("data", []):
        if c.get("name") == name:
            return c["id"]
    return None


async def _create_campaign(session: aiohttp.ClientSession) -> Optional[str]:
    creds  = _creds()
    budget = int(creds["budget_eur"] * 100)   # € → Cent
    name   = "GaN 240W | ROAS MAX | ineedit.com.co"

    existing = await _find_campaign(session, name)
    if existing:
        log.info("Kampagne bereits vorhanden: %s", existing)
        return existing

    payload = {
        "name":                    name,
        "objective":               "OUTCOME_SALES",
        "status":                  "PAUSED",
        "special_ad_categories":   [],
        "bid_strategy":            "LOWEST_COST_WITHOUT_CAP",
        "daily_budget":            budget,
    }
    res = await _api(session, "POST", f"{creds['account']}/campaigns", data=payload)
    cid = res.get("id")
    if cid:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO campaigns VALUES (?,?,?,?,?,?)",
                (cid, name, "PAUSED", "OUTCOME_SALES", creds["budget_eur"], time.time())
            )
        log.info("Kampagne erstellt: %s", cid)
    return cid


async def _create_adset(
    session: aiohttp.ClientSession,
    campaign_id: str,
    name: str,
    targeting: dict,
    set_type: str,
    budget_eur: Optional[float] = None,
    pixel_id: str = "",
) -> Optional[str]:
    creds = _creds()
    pid   = pixel_id or creds["pixel_id"]

    payload = {
        "name":              name,
        "campaign_id":       campaign_id,
        "status":            "PAUSED",
        "targeting":         json.dumps(targeting),
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "billing_event":     "IMPRESSIONS",
        "bid_strategy":      "LOWEST_COST_WITHOUT_CAP",
        "promoted_object": json.dumps({
            "pixel_id":          pid,
            "custom_event_type": "PURCHASE",
        }),
    }
    if budget_eur:
        payload["daily_budget"] = int(budget_eur * 100)

    res = await _api(session, "POST", f"{creds['account']}/adsets", data=payload)
    sid = res.get("id")
    if sid:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ad_sets VALUES (?,?,?,?,?,?)",
                (sid, campaign_id, name, "PAUSED", set_type, time.time())
            )
        log.info("Ad-Set erstellt [%s]: %s", set_type, sid)
    return sid


async def _upload_image(session: aiohttp.ClientSession, image_url: str) -> Optional[str]:
    """Bild von URL laden + zu Meta hochladen → Hash zurückgeben."""
    creds = _creds()
    try:
        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                return None
            data = await r.read()

        import base64
        b64 = base64.b64encode(data).decode()

        res = await _api(session, "POST", f"{creds['account']}/adimages",
                         data={"bytes": b64, "name": "gan_charger_240w.jpg"})
        images = res.get("images", {})
        for v in images.values():
            h = v.get("hash")
            if h:
                log.info("Bild hochgeladen, Hash: %s", h)
                return h
    except Exception as exc:
        log.warning("Image upload failed: %s", exc)
    return None


async def _get_product_image_url() -> Optional[str]:
    """Holt das erste Produktbild des GaN Chargers aus der Shopify API."""
    domain  = os.getenv("SHOPIFY_SHOP_DOMAIN", "ineedit.com.co")
    token   = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2024-01")
    if not token:
        return None
    url = f"https://{domain}/admin/api/{version}/products/16082238177667.json?fields=images"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers={"X-Shopify-Access-Token": token},
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    imgs = data.get("product", {}).get("images", [])
                    if imgs:
                        return imgs[0].get("src")
    except Exception as exc:
        log.warning("Shopify image fetch: %s", exc)
    return None


async def _create_ad_creative(
    session: aiohttp.ClientSession,
    page_id: str,
    variant: dict,
    product_url: str,
    image_hash: Optional[str] = None,
) -> Optional[str]:
    creds = _creds()

    link_data: dict = {
        "link":          product_url,
        "name":          variant["title"],
        "description":   variant["body"][:500],
        "call_to_action": {"type": variant["cta"], "value": {"link": product_url}},
        "message":       variant["body"],
    }
    if image_hash:
        link_data["image_hash"] = image_hash

    payload = {
        "name": f"GaN Creative V{variant['variant']} — {variant['hook']}",
        "object_story_spec": json.dumps({
            "page_id":   page_id,
            "link_data": link_data,
        }),
    }

    res = await _api(session, "POST", f"{creds['account']}/adcreatives", data=payload)
    crid = res.get("id")
    if crid:
        log.info("Creative erstellt V%s: %s", variant["variant"], crid)
    return crid


async def _create_ad(
    session: aiohttp.ClientSession,
    ad_set_id: str,
    creative_id: str,
    variant: dict,
) -> Optional[str]:
    creds = _creds()
    payload = {
        "name":        f"GaN Ad V{variant['variant']} — {variant['hook']}",
        "adset_id":    ad_set_id,
        "creative":    json.dumps({"creative_id": creative_id}),
        "status":      "PAUSED",
        "tracking_specs": json.dumps([{
            "action.type": ["offsite_conversion"],
            "fb_pixel":    [creds["pixel_id"]],
        }]),
    }
    res = await _api(session, "POST", f"{creds['account']}/ads", data=payload)
    aid = res.get("id")
    if aid:
        with _db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ads VALUES (?,?,?,?,?)",
                (aid, ad_set_id, variant["variant"], "PAUSED", time.time())
            )
        log.info("Ad erstellt V%s: %s", variant["variant"], aid)
    return aid


# ── Full campaign build ───────────────────────────────────────────────────────

async def create_gan_charger_campaign() -> dict:
    """
    Erstellt komplette GaN Charger ROAS-Kampagne:
    - 1 CBO-Kampagne
    - 3 Ad-Sets (Broad, Interest, Retargeting)
    - 3 Creative-Varianten pro Ad-Set
    Startet PAUSED — muss manuell im Meta Ads Manager aktiviert werden.
    """
    creds       = _creds()
    token       = creds["token"]
    if not token:
        return {"ok": False, "error": "META_ADS_TOKEN nicht gesetzt"}

    shop_domain = os.getenv("SHOPIFY_PUBLIC_DOMAIN", "ineedit.com.co")
    product_url = f"https://{shop_domain}/products/{PRODUCT_URL_HANDLE}"
    page_id     = creds["page_id"]

    result: dict = {"campaigns_created": [], "adsets_created": [], "ads_created": [], "errors": []}

    async with aiohttp.ClientSession() as session:
        # 1. Bild laden
        log.info("Lade Produktbild für Creative...")
        image_url   = await _get_product_image_url()
        image_hash  = None
        if image_url:
            image_hash = await _upload_image(session, image_url)

        # 2. Creatives (einmal erstellen, in allen Ad-Sets verwenden)
        creative_ids = []
        for v in CREATIVES:
            crid = await _create_ad_creative(session, page_id, v, product_url, image_hash)
            creative_ids.append(crid)
            if not crid:
                result["errors"].append(f"Creative V{v['variant']} fehlgeschlagen")

        # 3. Kampagne
        cid = await _create_campaign(session)
        if not cid:
            result["errors"].append("Kampagne konnte nicht erstellt werden")
            return {**result, "ok": False}
        result["campaigns_created"].append(cid)

        # 4. Ad-Sets + Ads
        sets = [
            ("GaN | Broad — Advantage+",     _targeting_broad(),     "broad",       creds["budget_eur"] * 0.4),
            ("GaN | Interests — DE/AT/CH",   _targeting_interests(), "interests",   creds["budget_eur"] * 0.4),
            ("GaN | Retargeting — 30d",      _targeting_broad(),     "retargeting", creds["budget_eur"] * 0.2),
        ]

        for set_name, targeting, set_type, budget in sets:
            sid = await _create_adset(
                session, cid, set_name, targeting, set_type, budget, creds["pixel_id"]
            )
            if not sid:
                result["errors"].append(f"Ad-Set '{set_name}' fehlgeschlagen")
                continue
            result["adsets_created"].append(sid)

            for i, v in enumerate(CREATIVES):
                crid = creative_ids[i]
                if not crid:
                    continue
                aid = await _create_ad(session, sid, crid, v)
                if aid:
                    result["ads_created"].append(aid)
                await asyncio.sleep(0.3)

            await asyncio.sleep(0.5)

    result["ok"] = len(result["campaigns_created"]) > 0
    result["message"] = (
        f"Kampagne erstellt (PAUSED) — {len(result['adsets_created'])} Ad-Sets, "
        f"{len(result['ads_created'])} Ads. Im Meta Ads Manager aktivieren!"
    )
    log.info(result["message"])
    await _telegram(
        f"✅ <b>Meta ROAS-Kampagne erstellt</b>\n"
        f"Produkt: GaN Charger 240W | ineedit.com.co\n"
        f"Ad-Sets: {len(result['adsets_created'])} | Ads: {len(result['ads_created'])}\n"
        f"Status: PAUSED — bitte im Meta Ads Manager aktivieren\n"
        f"Errors: {len(result['errors'])}"
    )
    return result


# ── Live ROAS von Meta Insights ───────────────────────────────────────────────

async def get_live_roas(days: int = 7) -> list[dict]:
    """Holt ROAS-Daten aus Meta Insights API für alle aktiven Kampagnen."""
    creds = _creds()
    token = creds["token"]
    if not token:
        return []

    async with aiohttp.ClientSession() as session:
        res = await _api(
            session, "GET", f"{creds['account']}/insights",
            params={
                "fields":       "campaign_id,campaign_name,spend,purchase_roas,actions,impressions,clicks,cpc",
                "date_preset":  f"last_{days}_days",
                "level":        "campaign",
                "limit":        "50",
            }
        )

    rows     = res.get("data", [])
    results  = []
    now      = time.time()

    for row in rows:
        spend = float(row.get("spend", 0))
        # purchase_roas kommt als [{"action_type":"omni_purchase","value":"3.52"}]
        roas_list = row.get("purchase_roas", [])
        roas = float(roas_list[0]["value"]) if roas_list else 0.0
        revenue = round(spend * roas, 2)

        purchases = 0
        for action in row.get("actions", []):
            if action.get("action_type") in ("purchase", "omni_purchase"):
                purchases += int(action.get("value", 0))

        entry = {
            "campaign_id":   row.get("campaign_id", ""),
            "campaign_name": row.get("campaign_name", ""),
            "spend":         round(spend, 2),
            "revenue":       revenue,
            "roas":          round(roas, 2),
            "impressions":   int(row.get("impressions", 0)),
            "clicks":        int(row.get("clicks", 0)),
            "cpc":           round(float(row.get("cpc", 0)), 2),
            "purchases":     purchases,
        }
        results.append(entry)

        # In DB loggen
        with _db() as conn:
            conn.execute(
                "INSERT INTO insights_log (campaign_id,date_start,date_stop,spend,revenue,roas,"
                "impressions,clicks,purchases,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry["campaign_id"], f"last_{days}d", "", spend, revenue, roas,
                 entry["impressions"], entry["clicks"], purchases, now)
            )

    log.info("Live ROAS: %d Kampagnen geladen", len(results))
    return results


# ── Auto-Optimierung ──────────────────────────────────────────────────────────

ROAS_SCALE = float(os.getenv("ROAS_SCALE_THRESHOLD", "3.5"))
ROAS_PAUSE = float(os.getenv("ROAS_PAUSE_THRESHOLD", "1.8"))
MIN_SPEND  = float(os.getenv("ROAS_MIN_SPEND_EUR",   "10.0"))
SCALE_PCT  = float(os.getenv("ROAS_SCALE_PCT",       "25.0"))


async def _get_adset_budgets(session: aiohttp.ClientSession, campaign_id: str) -> list[dict]:
    creds = _creds()
    res   = await _api(session, "GET", f"{campaign_id}/adsets",
                       params={"fields": "id,daily_budget,status"})
    return res.get("data", [])


async def _scale_campaign(session: aiohttp.ClientSession, campaign_id: str) -> float:
    """Budget um SCALE_PCT erhöhen. Gibt neues Budget zurück."""
    creds   = _creds()
    adsets  = await _get_adset_budgets(session, campaign_id)
    total   = 0.0
    for adset in adsets:
        if adset.get("status") != "ACTIVE":
            continue
        current = int(adset.get("daily_budget", 0))
        if current <= 0:
            continue
        new_b = int(current * (1 + SCALE_PCT / 100))
        await _api(session, "POST", adset["id"],
                   data={"daily_budget": str(new_b), "access_token": _creds()["token"]})
        total = new_b / 100
        log.info("Scale adset %s: %d→%d Cent", adset["id"], current, new_b)
    return total


async def _pause_campaign(session: aiohttp.ClientSession, campaign_id: str) -> bool:
    creds = _creds()
    res   = await _api(session, "POST", campaign_id, data={"status": "PAUSED"})
    ok    = bool(res.get("success"))
    if ok:
        log.info("Kampagne pausiert: %s", campaign_id)
    return ok


async def optimize_campaigns() -> dict:
    """Holt live ROAS und pausiert Verlierer / skaliert Gewinner."""
    rows    = await get_live_roas(days=7)
    paused  = []
    scaled  = []
    kept    = []

    if not rows:
        return {"ok": True, "paused": [], "scaled": [], "kept": [], "note": "Keine aktiven Kampagnen"}

    async with aiohttp.ClientSession() as session:
        for c in rows:
            cid   = c["campaign_id"]
            roas  = c["roas"]
            spend = c["spend"]

            if spend < MIN_SPEND:
                kept.append({"name": c["campaign_name"], "roas": roas, "reason": "zu wenig Spend"})
                continue

            if roas < ROAS_PAUSE:
                ok = await _pause_campaign(session, cid)
                if ok:
                    paused.append(c["campaign_name"])
                    with _db() as conn:
                        conn.execute(
                            "INSERT INTO optimization_log "
                            "(action,campaign_id,reason,old_budget,new_budget,recorded_at) "
                            "VALUES (?,?,?,?,?,?)",
                            ("PAUSE", cid, f"ROAS {roas} < {ROAS_PAUSE}", spend, 0, time.time())
                        )
            elif roas > ROAS_SCALE:
                new_b = await _scale_campaign(session, cid)
                scaled.append({"name": c["campaign_name"], "roas": roas, "new_budget_eur": new_b})
                with _db() as conn:
                    conn.execute(
                        "INSERT INTO optimization_log "
                        "(action,campaign_id,reason,old_budget,new_budget,recorded_at) "
                        "VALUES (?,?,?,?,?,?)",
                        ("SCALE", cid, f"ROAS {roas} > {ROAS_SCALE}", spend, new_b, time.time())
                    )
            else:
                kept.append({"name": c["campaign_name"], "roas": roas, "reason": "im Zielbereich"})

    msg = (
        f"📊 <b>ROAS-Optimierung</b>\n"
        f"Pausiert: {len(paused)} | Skaliert: {len(scaled)} | Behalten: {len(kept)}\n"
    )
    if scaled:
        for s in scaled:
            msg += f"⬆ {s['name']}: ROAS {s['roas']} → Budget +{SCALE_PCT}%\n"
    if paused:
        msg += f"⏸ Pausiert: {', '.join(paused)}\n"

    await _telegram(msg)
    return {"ok": True, "paused": paused, "scaled": scaled, "kept": kept}


# ── Stats für Dashboard ───────────────────────────────────────────────────────

def get_roas_stats() -> dict:
    with _db() as conn:
        last_insights = conn.execute(
            "SELECT * FROM insights_log ORDER BY recorded_at DESC LIMIT 10"
        ).fetchall()
        last_actions = conn.execute(
            "SELECT * FROM optimization_log ORDER BY recorded_at DESC LIMIT 10"
        ).fetchall()
        campaign_count = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
        adset_count    = conn.execute("SELECT COUNT(*) FROM ad_sets").fetchone()[0]
        ad_count       = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]

    def _row(r):
        return dict(r) if r else {}

    return {
        "campaigns":    campaign_count,
        "adsets":       adset_count,
        "ads":          ad_count,
        "last_insights": [_row(r) for r in last_insights],
        "last_actions":  [_row(r) for r in last_actions],
        "thresholds": {
            "scale_above_roas": ROAS_SCALE,
            "pause_below_roas": ROAS_PAUSE,
            "min_spend_eur":    MIN_SPEND,
            "scale_pct":        SCALE_PCT,
        }
    }


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def run_roas_max() -> str:
    """Scheduler-Entry: optimiert bestehende Kampagnen, erstellt wenn noch keine existiert."""
    creds = _creds()
    if not creds["token"]:
        return "META_ADS_TOKEN fehlt — übersprungen"

    # Prüfen ob Kampagne existiert
    async with aiohttp.ClientSession() as session:
        existing = await _find_campaign(session, "GaN 240W | ROAS MAX | ineedit.com.co")

    if not existing:
        log.info("Keine Kampagne gefunden — erstelle neue...")
        res = await create_gan_charger_campaign()
        return f"Kampagne erstellt: {res.get('message', 'ok')}"

    # Optimieren
    opt = await optimize_campaigns()
    return (
        f"ROAS-Optimierung: {len(opt.get('paused',[]))} pausiert, "
        f"{len(opt.get('scaled',[]))} skaliert, {len(opt.get('kept',[]))} im Zielbereich"
    )


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _telegram(msg: str) -> None:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    cid = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not cid:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as exc:
        log.warning("Telegram: %s", exc)
