#!/usr/bin/env python3
# DAUERHAFT DEAKTIVIERT 2026-07-16 — erzeugt Fake-Produkte (Reddit/HN-Posts als Shopify-Produkte).
# Scheduler-Task product_hub ebenfalls deaktiviert. Reaktivierung NUR nach OK von Rudolf.
"""
Product Intelligence Hub — Unified Orchestrator
================================================
Kombiniert viral_window_scanner + autonomous_product_pipeline zu EINEM Tool:

  [6 Signal-Quellen]
        ↓
  [AI-Score + Saturation + Margin]     ← viral_window_scanner
        ↓
  [Vollständige Listings generieren]   ← autonomous_product_pipeline
        ↓  Shopify  /  Gumroad  /  DS24
  [FB Ad Copy + Subscriber Alert]      ← viral_window_scanner (tier-basiert)

Kein Datenduplikat: beide Module teilen sich den keyword-basierten SQLite-State.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger("ProductIntelligenceHub")

# ── Tier-Konfiguration ────────────────────────────────────────────────────────
# Alert Only (€29): bekommt Alert + Score
# Pro       (€79): + Shopify-Link + FB Ad Copy
# Agency   (€199): + Gumroad + DS24 + alle Kanäle

MIN_SCORE_FULL_PIPELINE = 72   # Ab hier: komplette Multi-Platform Listing
MIN_SCORE_ALERT_ONLY    = 55   # Darunter: nur Alert an Pro/Agency

# ── Konvertierung: viral_item → pipeline_idea ─────────────────────────────────

def _item_to_idea(item: Dict) -> Dict:
    """
    Konvertiert ein viral_window_scanner Item in das Format von autonomous_product_pipeline.
    Kein Datenduplikat — die Felder werden nur temporär gemappt.
    """
    kw     = item["keyword"]
    score  = item["score"]
    margin = item.get("margin_data", {})
    reason = item.get("reason", "")
    supplier = item.get("supplier_hint", "AliExpress")

    # Preis aus Margin-Rechner oder Schätzung
    vk = margin.get("vk_eur", 0) if margin else 0
    if vk <= 0:
        vk = round(19.99 + (score / 100) * 40, 2)

    # Zielgruppe aus Keyword ableiten
    target = "Online-Händler und Dropshipper"
    if any(w in kw.lower() for w in ["smart", "solar", "e-bike", "powerstation"]):
        target = "Tech-affine Käufer und Heimwerker"
    elif any(w in kw.lower() for w in ["beauty", "hair", "skin", "nail"]):
        target = "Beauty-Enthusiasten und Selbstständige"
    elif any(w in kw.lower() for w in ["fitness", "sport", "gym"]):
        target = "Fitness-Fans und Sportler"

    return {
        "title":        kw,
        "tagline":      f"Trending 2026 — AI-Score {score}/100. {reason[:80]}",
        "price_eur":    vk,
        "type":         "physical",
        "target":       target,
        "keywords":     [kw.lower()] + ["trending", "dropshipping", "viral-2026",
                                         supplier.lower().split()[0]],
        "niche":        supplier,
        "seed_keywords": kw,
        # Extra-Felder für erweiterte Listings
        "score":        score,
        "margin_data":  margin,
        "saturation":   item.get("saturation", -1),
        "fb_ad":        item.get("fb_ad"),
        "supplier_hint": supplier,
        "window_h":     item.get("window_h", 48),
        "sources":      item.get("sources", "multi"),
    }


# ── Vollständiger Pipeline-Run pro Produkt ────────────────────────────────────

async def run_full_product_pipeline(item: Dict) -> Dict:
    """
    Für ein hochscorendes viral item:
    1. autonomous_product_pipeline → Shopify + Gumroad
    2. Subscriber-Alert mit allen Links
    Gibt ein result-dict zurück (URLs, Status).
    """
    idea    = _item_to_idea(item)
    kw      = idea["title"]
    results = {"keyword": kw, "score": idea["score"], "ok": False}

    # ── Step 1: Shopify-Listing (via autonomous_product_pipeline) ─────────────
    shopify_url = None
    try:
        from modules.autonomous_product_pipeline import _create_shopify_product
        shopify_url = await _create_shopify_product(idea)
        results["shopify_url"] = shopify_url
        log.info("Hub Shopify OK: %s → %s", kw, shopify_url)
    except Exception as e:
        log.warning("Hub Shopify error: %s", e)
        results["shopify_error"] = str(e)

    # ── Step 2: Gumroad-Listing (digitales Infoprodukt zum Thema) ────────────
    gumroad_url = None
    try:
        from modules.autonomous_product_pipeline import _create_gumroad_product
        # Für Gumroad: Produkttyp auf "digital" setzen (Sourcebook/Guide)
        digital_idea = {
            **idea,
            "type":    "digital",
            "title":   f"{kw} — Dropshipping Sourcebook",
            "tagline": f"Vollständiger Supplier-Guide für {kw} (AI-Score {idea['score']}/100)",
            "price_eur": round(idea["price_eur"] * 0.3, 2) or 9.99,
        }
        gumroad_url = await _create_gumroad_product(digital_idea)
        results["gumroad_url"] = gumroad_url
        log.info("Hub Gumroad OK: %s → %s", kw, gumroad_url)
    except Exception as e:
        log.debug("Hub Gumroad skip: %s", e)

    # ── Step 3: Multi-Channel Blast (alle 10 Kanäle) ─────────────────────────
    blast_result = {}
    if shopify_url:
        try:
            from modules.autonomous_product_pipeline import _blast_all_channels
            urls = {
                "shopify": shopify_url,
                "gumroad": gumroad_url or "",
            }
            blast_result = await _blast_all_channels(idea, urls)
            results["channels"] = blast_result
            log.info("Hub Blast OK: %s", kw)
        except Exception as e:
            log.debug("Hub Blast skip: %s", e)

    results["ok"] = bool(shopify_url)

    # ── Step 4: Subscriber Alert mit vollständigem Paket ─────────────────────
    await _send_hub_alert(idea, results)

    return results


async def _send_hub_alert(idea: Dict, results: Dict):
    """Sendet Tier-basierten Alert mit kompletter Listings-Übersicht."""
    try:
        from modules.viral_window_scanner import _tg_send, _notify_subscribers
    except ImportError:
        log.warning("viral_window_scanner nicht verfügbar für Alert")
        return

    kw      = idea["title"]
    score   = idea["score"]
    margin  = idea.get("margin_data", {})
    window  = idea.get("window_h", 48)
    sat     = idea.get("saturation", -1)
    sources = idea.get("sources", "multi")
    if isinstance(sources, list):
        sources = ", ".join(sources)

    emoji = "🔥🔥🔥" if score >= 85 else ("🔥🔥" if score >= 70 else "🔥")

    # Margin-Zeile
    margin_line = ""
    if margin and margin.get("ek_eur", 0) > 0:
        margin_line = (
            f"\n💵 EK ~€{margin['ek_eur']} → VK ~€{margin['vk_eur']}"
            f" → Gewinn ~€{margin['margin_eur']} ({margin['margin_pct']}%)"
        )

    # Sättigungszeile
    sat_line = ""
    if sat >= 0:
        lvl = "NIEDRIG 🟢" if sat < 50 else ("MITTEL 🟡" if sat < 500 else "HOCH 🔴")
        sat_line = f"\n🏪 Shopify-Sättigung: {lvl} (~{sat} Stores)"

    # Listing-Links
    link_lines = ""
    if results.get("shopify_url"):
        link_lines += f"\n🛍️ Shopify: {results['shopify_url']}"
    if results.get("gumroad_url"):
        link_lines += f"\n📦 Gumroad: {results['gumroad_url']}"

    # Channel-Zusammenfassung
    blast = results.get("channels", {})
    channels_done = [k for k, v in blast.items() if v and "error" not in str(v).lower()]
    channels_line = f"\n📡 Promoted auf: {', '.join(channels_done)}" if channels_done else ""

    # ── Alert Only Tier — kurze Version ──────────────────────────────────────
    alert_msg = f"""{emoji} <b>PRODUCT INTELLIGENCE HUB</b> {emoji}

🎯 <b>{kw}</b>
📊 Score: {score}/100 | ⏱ Fenster: ~{window}h{margin_line}{sat_line}
📡 Signale: {sources}
{link_lines}

🤖 Viral Window Scanner + Auto-Pipeline
💎 Pro-Tier für FB Ads + alle Kanäle: /subscribe"""

    # An Rudolf direkt
    await _tg_send(alert_msg)

    # ── Pro/Agency Tier — vollständiges Paket ────────────────────────────────
    fb_ad = idea.get("fb_ad", {})
    pro_extra = None
    if fb_ad and fb_ad.get("ad_a"):
        ad_a = fb_ad["ad_a"]
        ad_b = fb_ad.get("ad_b", {})
        pro_extra = (
            f"📢 <b>FB Ads für: {kw}</b>\n\n"
            f"<b>Ad A:</b> {ad_a.get('hook','')}\n{ad_a.get('body','')}\n"
            f"🔘 {ad_a.get('cta','Jetzt kaufen')}\n\n"
            f"<b>Ad B:</b> {ad_b.get('hook','')}\n{ad_b.get('body','')}\n"
            f"🔘 {ad_b.get('cta','Zum Shop')}\n\n"
            f"{fb_ad.get('hashtags','')}{channels_line}"
        )

    await _notify_subscribers(alert_msg, fb_msg=pro_extra, min_tier_score=score)


# ── Haupt-Orchestrator ────────────────────────────────────────────────────────

async def run_hub_cycle() -> Dict:
    # DAUERHAFT DEAKTIVIERT — erzeugt Fake-Produkte. Reaktivierung NUR nach OK von Rudolf.
    log.critical("run_hub_cycle DISABLED — Fake-Produkte verboten (Reddit/HN-Posts)")
    return {"ok": False, "error": "DISABLED — Fake-Produkte verboten", "created": 0}
    log.info("=== Product Intelligence Hub gestartet ===")
    start = time.time()

    # Phase 1: Viral Scanner
    try:
        from modules.viral_window_scanner import (
            aggregate_signals, score_with_ai, generate_fb_ad_copy,
            calculate_margin, init_db
        )
        import sqlite3
        from pathlib import Path
        init_db()
    except ImportError as e:
        return {"ok": False, "error": f"viral_window_scanner import: {e}"}

    signals = await aggregate_signals()
    if not signals:
        return {"ok": False, "error": "Keine Signale"}

    scored = await score_with_ai(signals)
    if not scored:
        return {"ok": False, "error": "Scoring fehlgeschlagen"}

    # Phase 2: FB Ads für Top-Items
    top_items = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
    for item in top_items:
        if not item.get("fb_ad"):
            item["fb_ad"] = await generate_fb_ad_copy(item)

        mg = item.get("margin_data")
        if not mg:
            ek = round(5 + (item["score"] / 100) * 35, 2)
            vk = round(ek * 2.5, 2)
            item["margin_data"] = calculate_margin(ek, vk)

    # Phase 3: Full Pipeline für Score >= 72
    pipeline_results = []
    for item in top_items:
        if item["score"] >= MIN_SCORE_FULL_PIPELINE:
            result = await run_full_product_pipeline(item)
            pipeline_results.append(result)
            await asyncio.sleep(2)  # Rate-Limit vermeiden

    elapsed = round(time.time() - start, 1)
    summary = {
        "ok":               True,
        "signals_total":    len(signals),
        "top_items":        len(top_items),
        "pipelines_run":    len(pipeline_results),
        "pipelines_ok":     sum(1 for r in pipeline_results if r.get("ok")),
        "elapsed_sec":      elapsed,
        "top_products":     [
            {"keyword": i["keyword"], "score": i["score"]}
            for i in top_items
        ],
        "ran_at": datetime.now(timezone.utc).isoformat()
    }
    log.info("Hub-Zyklus fertig in %ss: %s", elapsed, summary)
    return summary


# ── Intent Bridge Integration ─────────────────────────────────────────────────

async def _register_with_intent_bridge(results: Dict, idea: Dict):
    """
    Nach erfolgreichem Pipeline-Run: neue Shopify-Produkt-URL dem Intent Bridge
    bekannt machen, damit es bei Kaufabsichten in Telegram-Gruppen sofort antwortet.

    Die intent_to_sale_bridge sucht bereits live in Shopify — diese Funktion
    loggt den neuen Trigger in die Bridge-DB für Priority-Antworten.
    """
    shopify_url = results.get("shopify_url")
    if not shopify_url:
        return

    kw       = idea["title"]
    score    = idea["score"]
    category = _guess_category(kw)

    try:
        from modules.intent_to_sale_bridge import init_db as ib_init, _db as ib_db
        ib_init()
        with ib_db() as con:
            con.execute(
                """INSERT OR IGNORE INTO ib_events
                   (ts, chat_id, user_id, username, message, intent, confidence,
                    category, product_url, responded)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(time.time()), "hub_register", "system", "ProductHub",
                    f"Hub auto-registered: {kw}",
                    "purchase", min(score / 100, 0.99),
                    category, shopify_url, 0
                )
            )
        log.info("Intent Bridge: %s registriert in Kategorie '%s'", kw, category)
    except Exception as e:
        log.debug("Intent Bridge registration skip: %s", e)


def _guess_category(kw: str) -> str:
    """Leitet Kategorie aus Keyword ab (für intent_to_sale_bridge Routing)."""
    kw_l = kw.lower()
    if any(w in kw_l for w in ["solar", "powerstation", "akku", "batterie", "ladestation"]):
        return "powerstation"
    if any(w in kw_l for w in ["smart home", "steckdose", "schalter", "zigbee", "wlan"]):
        return "smart_home"
    if any(w in kw_l for w in ["kopfhörer", "lautsprecher", "bluetooth"]):
        return "audio"
    if any(w in kw_l for w in ["watch", "tracker", "wearable", "fitness"]):
        return "wearables"
    if any(w in kw_l for w in ["auto", "kfz", "dashcam", "fahrzeug"]):
        return "auto_tech"
    if any(w in kw_l for w in ["kamera", "cam", "überwachung"]):
        return "kamera"
    if any(w in kw_l for w in ["camping", "outdoor", "rucksack"]):
        return "outdoor"
    if any(w in kw_l for w in ["schreibtisch", "büro", "monitor", "webcam"]):
        return "home_office"
    return "gadgets"


# ── Hub-Zyklus Update mit Intent Bridge ──────────────────────────────────────

async def run_hub_cycle_v2() -> Dict:  # umbenannt — wird nicht mehr aufgerufen
    """
    Kompletter Hub-Zyklus:
    1. viral_window_scanner → Signale + Scoring + Saturation + FB Ads
    2. autonomous_product_pipeline → Multi-Platform Listing (Shopify/Gumroad/DS24)
    3. intent_to_sale_bridge → neue Produkte registrieren für 60s-Antworten in TG-Gruppen
    4. Subscriber-Alert mit vollständigem Paket
    """
    log.info("=== Product Intelligence Hub gestartet ===")
    start = time.time()

    # Phase 1: Viral Scanner
    try:
        from modules.viral_window_scanner import (
            aggregate_signals, score_with_ai, generate_fb_ad_copy,
            calculate_margin, init_db
        )
        init_db()
    except ImportError as e:
        return {"ok": False, "error": f"viral_window_scanner import: {e}"}

    signals = await aggregate_signals()
    if not signals:
        return {"ok": False, "error": "Keine Signale"}

    scored = await score_with_ai(signals)
    if not scored:
        return {"ok": False, "error": "Scoring fehlgeschlagen"}

    # Phase 2: FB Ads für Top-Items
    top_items = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
    for item in top_items:
        if not item.get("fb_ad"):
            item["fb_ad"] = await generate_fb_ad_copy(item)

        mg = item.get("margin_data")
        if not mg:
            ek = round(5 + (item["score"] / 100) * 35, 2)
            vk = round(ek * 2.5, 2)
            item["margin_data"] = calculate_margin(ek, vk)

    # Phase 3: Pipeline + Intent Bridge Registration
    pipeline_results = []
    for item in top_items:
        if item["score"] >= MIN_SCORE_FULL_PIPELINE:
            idea   = _item_to_idea(item)
            result = await run_full_product_pipeline(item)
            pipeline_results.append(result)

            # Intent Bridge: neues Produkt sofort registrieren
            await _register_with_intent_bridge(result, idea)
            await asyncio.sleep(2)

    elapsed = round(time.time() - start, 1)
    summary = {
        "ok":               True,
        "signals_total":    len(signals),
        "top_items":        len(top_items),
        "pipelines_run":    len(pipeline_results),
        "pipelines_ok":     sum(1 for r in pipeline_results if r.get("ok")),
        "intent_registered": sum(1 for r in pipeline_results if r.get("shopify_url")),
        "elapsed_sec":      elapsed,
        "top_products":     [
            {"keyword": i["keyword"], "score": i["score"]}
            for i in top_items
        ],
        "ran_at": datetime.now(timezone.utc).isoformat()
    }
    log.info("Hub-Zyklus fertig in %ss: %s", elapsed, summary)
    return summary


async def get_hub_status() -> Dict:
    """Status aller drei Module kombiniert in einer Übersicht."""
    try:
        from modules.viral_window_scanner import get_status as vs_status
        scanner = await vs_status()
    except Exception as e:
        scanner = {"error": str(e)}

    try:
        from modules.autonomous_product_pipeline import get_pipeline_history
        pipeline = await get_pipeline_history(limit=5)
    except Exception as e:
        pipeline = {"error": str(e)}

    try:
        from modules.intent_to_sale_bridge import get_stats as ib_stats
        intent = ib_stats()
    except Exception as e:
        intent = {"error": str(e)}

    return {
        "ok": True,
        "viral_scanner":   scanner,
        "pipeline_recent": pipeline,
        "intent_bridge":   intent,
        "architecture": {
            "layer_1": "viral_window_scanner — 6-Signal Trend-Erkennung + Subscriber-Alerts",
            "layer_2": "autonomous_product_pipeline — Content-Generierung + Shopify/Gumroad/DS24",
            "layer_3": "intent_to_sale_bridge — Telegram-Gruppen 60s-Antwort auf Kaufabsichten",
        }
    }
