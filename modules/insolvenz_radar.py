#!/usr/bin/env python3
"""
Insolvenz Radar Pro — Deutsches Staatsregister als B2B-Leadmaschine
====================================================================
Quellen (alle 100% kostenlos & öffentlich):
  - insolvenzbekanntmachungen.de  — offiz. deutsches Insolvenzregister
  - handelsregister.de            — Unternehmensregister (neue Einträge)
  - bundesanzeiger.de             — Jahresabschlüsse, Gesellschafteränderg.

Flow:
  1. Täglich neue Insolvenzen scrapen
  2. AI-Scoring: Branche + Größe → Lead-Typ (Steuerberater, Factoring, M&A)
  3. Telegram-Alert mit vollständigem Lead-Profil
  4. Dashboard mit Karten-Ansicht, Filter nach Bundesland/Score/Branche
  5. Stripe-Abo für externe Nutzer (Steuerberater, Factoring-Firmen)

Stripe Tiers (benutzt bestehende Telegram-Preise):
  Starter  €29/mo → 50 Alerts/Tag, Email
  Pro      €79/mo → unlimitiert, CRM-Webhook, alle Bundesländer
  Agency  €199/mo → API-Zugang, White-Label, eigene Scoring-Regeln
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("InsolvenzRadar")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "insolvenz_radar.db"

# ── Env helpers ───────────────────────────────────────────────────────────────
def _tg_token()    -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()     -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _anthropic()   -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _openai()      -> str: return os.getenv("OPENAI_API_KEY", "")
def _stripe_key()  -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "https://dudirudibot-mega-production.up.railway.app")

def _price_starter() -> str:
    return os.getenv("INSOLVENZ_PRICE_STARTER") or os.getenv("PRICE_TELEGRAM_STARTER", "price_1TjodoRJECiV6vSmL726jLd3")
def _price_pro() -> str:
    return os.getenv("INSOLVENZ_PRICE_PRO") or os.getenv("PRICE_TELEGRAM_PRO", "price_1TjodoRJECiV6vSmcWkhHtWz")
def _price_agency() -> str:
    return os.getenv("INSOLVENZ_PRICE_AGENCY") or os.getenv("PRICE_TELEGRAM_AGENCY", "price_1TjodpRJECiV6vSmFVtPj8yb")

# Bundesländer-Kürzel → Name
BUNDESLAENDER = {
    "BB": "Brandenburg", "BE": "Berlin", "BW": "Baden-Württemberg",
    "BY": "Bayern", "HB": "Bremen", "HE": "Hessen",
    "HH": "Hamburg", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen", "RP": "Rheinland-Pfalz", "SH": "Schleswig-Holstein",
    "SL": "Saarland", "SN": "Sachsen", "ST": "Sachsen-Anhalt", "TH": "Thüringen"
}

# Branchen-Keywords → Kategorie
BRANCHEN_MAP = {
    "GmbH": "Kapitalgesellschaft", "AG": "Kapitalgesellschaft",
    "UG": "Kleinunternehmen", "OHG": "Personengesellschaft",
    "Bau": "Baugewerbe", "Dach": "Baugewerbe", "Sanitär": "Baugewerbe",
    "Elektro": "Elektrotechnik", "IT": "IT/Tech", "Software": "IT/Tech",
    "Handel": "Einzelhandel", "Markt": "Einzelhandel", "Shop": "Einzelhandel",
    "Transport": "Logistik", "Spedition": "Logistik", "Logistik": "Logistik",
    "Gastro": "Gastronomie", "Restaurant": "Gastronomie", "Hotel": "Gastronomie",
    "Pflege": "Gesundheit", "Arzt": "Gesundheit", "Med": "Gesundheit",
    "Immobilien": "Immobilien", "Makler": "Immobilien",
}

# Lead-Typ pro Score-Bereich
LEAD_TYPES = {
    (80, 100): ["M&A-Berater", "Insolvenzverwalter", "Factoring-Premium"],
    (60, 79):  ["Steuerberater", "Factoring", "Schnellkredit"],
    (40, 59):  ["Steuerberater", "Software-Anbieter", "Versicherung"],
    (0, 39):   ["Allgemein"],
}


# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS ir_leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uid             TEXT UNIQUE NOT NULL,
            debtor_name     TEXT NOT NULL,
            court           TEXT,
            case_number     TEXT,
            bundesland      TEXT,
            rechtsform      TEXT,
            branche         TEXT,
            score           INTEGER DEFAULT 0,
            lead_types      TEXT,
            publication_date TEXT,
            insolvency_type TEXT,
            raw_text        TEXT,
            ai_summary      TEXT,
            alerted         INTEGER DEFAULT 0,
            source          TEXT DEFAULT 'insolvenzbekanntmachungen',
            created_at      INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_ir_score ON ir_leads(score DESC);
        CREATE INDEX IF NOT EXISTS idx_ir_bl ON ir_leads(bundesland);
        CREATE INDEX IF NOT EXISTS idx_ir_date ON ir_leads(created_at DESC);

        CREATE TABLE IF NOT EXISTS ir_subscribers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            tier        TEXT DEFAULT 'starter',
            bundesland  TEXT DEFAULT 'ALL',
            min_score   INTEGER DEFAULT 60,
            webhook_url TEXT,
            stripe_sub  TEXT,
            active      INTEGER DEFAULT 1,
            created_at  INTEGER
        );

        CREATE TABLE IF NOT EXISTS ir_scan_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  INTEGER,
            finished_at INTEGER,
            new_leads   INTEGER DEFAULT 0,
            alerted     INTEGER DEFAULT 0,
            errors      TEXT
        );
        """)


# ── HTTP Helper ───────────────────────────────────────────────────────────────

def _session(timeout: int = 30) -> aiohttp.ClientSession:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout),
        headers=headers,
        connector=aiohttp.TCPConnector(ssl=False)
    )


async def _tg(text: str) -> bool:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return False
    try:
        async with _session(10) as s:
            r = await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True}
            )
            return r.status == 200
    except Exception as e:
        log.debug("TG error: %s", e)
        return False


# ── Scraper: insolvenzbekanntmachungen.de ────────────────────────────────────

async def scrape_insolvenzbekanntmachungen(bundesland: str = "", max_results: int = 50) -> List[Dict]:
    """Scrapt das offizielle deutsche Insolvenzregister."""
    results = []

    # Suche nach aktuellem Datum (letzte 2 Tage)
    from datetime import date, timedelta
    today = date.today()
    date_from = (today - timedelta(days=2)).strftime("%d.%m.%Y")
    date_to   = today.strftime("%d.%m.%Y")

    # Bundesland-Filter aufbauen
    bl_params = [("bundesland", bundesland)] if bundesland else [
        ("bundesland", bl) for bl in BUNDESLAENDER.keys()
    ]

    for bl_code, _ in bl_params[:3]:  # max 3 Bundesländer pro Call (Rate-Limit)
        try:
            # Offizielle Suche-URL (POST-basiert, wir simulieren GET mit Query-Params)
            url = "https://www.insolvenzbekanntmachungen.de/ap/suche.jsf"
            params = {
                "suchart": "norm",
                "bundesland": bl_code,
                "gericht": "",
                "datum_von": date_from,
                "datum_bis": date_to,
                "name": "",
                "seite": "1",
            }
            async with _session(25) as s:
                async with s.get(url, params=params) as r:
                    if r.status != 200:
                        log.debug("insolvenz.de %s → %s", bl_code, r.status)
                        continue
                    html = await r.text()

            # HTML parsen — Tabellen-Einträge extrahieren
            entries = _parse_insolvenz_html(html, bl_code)
            results.extend(entries)
            log.info("Insolvenz %s: %d Einträge", bl_code, len(entries))
            await asyncio.sleep(1.5)  # Rate-Limit respektieren

        except Exception as e:
            log.warning("scrape_insolvenz %s: %s", bl_code, e)

    return results[:max_results]


def _parse_insolvenz_html(html: str, bundesland: str) -> List[Dict]:
    """Parst die HTML-Tabelle von insolvenzbekanntmachungen.de."""
    entries = []

    # Tabellenzeilen finden
    rows = re.findall(
        r'<tr[^>]*class="[^"]*(?:odd|even)[^"]*"[^>]*>(.*?)</tr>',
        html, re.DOTALL | re.IGNORECASE
    )

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        cells = [re.sub(r'\s+', ' ', c) for c in cells]

        if len(cells) < 3:
            continue

        # Typische Spalten: Datum | Gericht | Schuldner | Aktenzeichen | Art
        pub_date    = cells[0] if len(cells) > 0 else ""
        court       = cells[1] if len(cells) > 1 else ""
        debtor_name = cells[2] if len(cells) > 2 else ""
        case_number = cells[3] if len(cells) > 3 else ""
        ins_type    = cells[4] if len(cells) > 4 else "Insolvenzeröffnung"

        if not debtor_name or len(debtor_name) < 3:
            continue

        uid = hashlib.md5(f"{debtor_name}{court}{case_number}".encode()).hexdigest()[:16]

        entries.append({
            "uid":             uid,
            "debtor_name":     debtor_name,
            "court":           court,
            "case_number":     case_number,
            "bundesland":      bundesland,
            "publication_date": pub_date,
            "insolvency_type": ins_type,
            "raw_text":        " | ".join(cells),
            "source":          "insolvenzbekanntmachungen"
        })

    return entries


# ── Scraper: Neugründungen via Bundesanzeiger ─────────────────────────────────

async def scrape_neugruendungen(max_results: int = 30) -> List[Dict]:
    """Scrapt neue Handelsregister-Einträge vom Bundesanzeiger."""
    results = []
    try:
        url = "https://www.bundesanzeiger.de/pub/de/suchergebnis"
        params = {
            "0-2.IFormSubmitListener-footer-footer_form-requester": "",
            "fulltext": "Neueintragung",
            "category_select": "HRB",
        }
        async with _session(20) as s:
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    html = await r.text()
                    results = _parse_bundesanzeiger_html(html)
    except Exception as e:
        log.debug("Bundesanzeiger scrape: %s", e)
    return results[:max_results]


def _parse_bundesanzeiger_html(html: str) -> List[Dict]:
    entries = []
    rows = re.findall(r'<div[^>]*class="[^"]*result_container[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    for row in rows[:20]:
        name_m = re.search(r'<span[^>]*class="[^"]*company[^"]*"[^>]*>(.*?)</span>', row, re.DOTALL)
        if not name_m:
            continue
        name = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()
        if not name:
            continue
        uid = hashlib.md5(f"bg_{name}".encode()).hexdigest()[:16]
        entries.append({
            "uid":             uid,
            "debtor_name":     name,
            "court":           "",
            "case_number":     "",
            "bundesland":      "",
            "publication_date": datetime.now().strftime("%d.%m.%Y"),
            "insolvency_type": "Neugründung",
            "raw_text":        name,
            "source":          "bundesanzeiger"
        })
    return entries


# ── AI Scoring & Lead-Profil ──────────────────────────────────────────────────

def _score_heuristic(entry: Dict) -> int:
    """Schnelles Heuristik-Scoring ohne AI."""
    score = 30  # Basis
    name = entry.get("debtor_name", "").lower()
    raw  = entry.get("raw_text", "").lower()
    ins_type = entry.get("insolvency_type", "").lower()

    # Rechtsform-Bonus
    if "gmbh" in name or " ag " in name:
        score += 20
    elif "ug" in name or "e.k." in name:
        score += 10

    # Insolenzart
    if "eröffnung" in ins_type or "eröffnet" in ins_type:
        score += 20
    elif "abweisung" in ins_type or "mangels" in ins_type:
        score -= 10  # Masselosigkeit = kein Geld da

    # Branche
    high_value_keywords = ["bau", "transport", "logistik", "handel", "immobilien", "pflege"]
    for kw in high_value_keywords:
        if kw in name or kw in raw:
            score += 15
            break

    # Größenindikator (Mitarbeiterzahl in Raw-Text)
    if any(x in raw for x in ["beschäftigte", "mitarbeiter", "arbeitnehmer"]):
        score += 10

    # Neugründung = andere Lead-Art (Dienstleister brauchen)
    if entry.get("source") == "bundesanzeiger":
        score = 55  # Fixwert: immer medium interest

    return min(max(score, 0), 100)


def _classify_branche(name: str, raw: str) -> str:
    combined = (name + " " + raw).lower()
    for keyword, branche in BRANCHEN_MAP.items():
        if keyword.lower() in combined:
            return branche
    return "Sonstige"


def _get_lead_types(score: int) -> List[str]:
    for (lo, hi), types in LEAD_TYPES.items():
        if lo <= score <= hi:
            return types
    return ["Allgemein"]


async def enrich_with_ai(entry: Dict) -> Dict:
    """Bereichert einen Lead mit AI-Analyse (optional, fällt auf Heuristik zurück)."""
    if not _anthropic():
        return entry

    prompt = f"""Analysiere diese deutsche Insolvenzbekanntmachung und erstelle ein B2B-Lead-Profil.

Schuldner: {entry['debtor_name']}
Gericht: {entry.get('court', '?')}
Bundesland: {entry.get('bundesland', '?')}
Insolvenzart: {entry.get('insolvency_type', '?')}
Datum: {entry.get('publication_date', '?')}

Antworte als JSON:
{{
  "score": <0-100, wie wertvoll ist dieser Lead für B2B-Dienstleister>,
  "branche": "<Branche des Unternehmens>",
  "unternehmensgroesse": "<micro/small/medium/large>",
  "lead_typen": ["<beste Zielgruppe 1>", "<beste Zielgruppe 2>"],
  "ai_summary": "<1 Satz: warum ist das ein interessanter Lead?>"
}}

Score-Logik: 80+ = sofort handeln (M&A/Factoring), 60-79 = hohe Priorität (Steuerberater), 40-59 = mittel, <40 = gering."""

    try:
        async with _session(20) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": _anthropic(), "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                      "messages": [{"role": "user", "content": prompt}]}
            ) as r:
                if r.status == 200:
                    d    = await r.json()
                    text = d.get("content", [{}])[0].get("text", "")
                    m    = re.search(r"\{.*\}", text, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group())
                        entry["score"]      = int(parsed.get("score", entry["score"]))
                        entry["branche"]    = parsed.get("branche", entry["branche"])
                        entry["lead_types"] = json.dumps(parsed.get("lead_typen", []), ensure_ascii=False)
                        entry["ai_summary"] = parsed.get("ai_summary", "")
    except Exception as e:
        log.debug("AI enrich: %s", e)
    return entry


# ── Hauptscan ────────────────────────────────────────────────────────────────

async def run_scan(bundesland: str = "", min_score_alert: int = 60) -> Dict:
    """Hauptfunktion: scrapt, bewertet, speichert, alertet."""
    init_db()
    started = int(time.time())
    log.info("InsolvenzRadar Scan gestartet (BL=%s)", bundesland or "ALL")

    # 1. Scrapen
    entries = await scrape_insolvenzbekanntmachungen(bundesland, max_results=50)
    log.info("Gescrapt: %d Insolvenz-Einträge", len(entries))

    new_count   = 0
    alert_count = 0

    for entry in entries:
        # Scoring
        entry["score"]      = _score_heuristic(entry)
        entry["branche"]    = _classify_branche(entry["debtor_name"], entry.get("raw_text", ""))
        entry["lead_types"] = json.dumps(_get_lead_types(entry["score"]), ensure_ascii=False)
        entry["rechtsform"] = _extract_rechtsform(entry["debtor_name"])

        # AI Enrichment nur für Score >= 50 (spart API-Kosten)
        if entry["score"] >= 50 and _anthropic():
            entry = await enrich_with_ai(entry)
            await asyncio.sleep(0.3)

        # In DB speichern (nur neue)
        try:
            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO ir_leads
                       (uid, debtor_name, court, case_number, bundesland, rechtsform,
                        branche, score, lead_types, publication_date, insolvency_type,
                        raw_text, ai_summary, source, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entry["uid"], entry["debtor_name"], entry.get("court", ""),
                        entry.get("case_number", ""), entry.get("bundesland", ""),
                        entry.get("rechtsform", ""), entry["branche"], entry["score"],
                        entry.get("lead_types", "[]"), entry.get("publication_date", ""),
                        entry.get("insolvency_type", ""), entry.get("raw_text", "")[:500],
                        entry.get("ai_summary", ""), entry["source"], int(time.time())
                    )
                )
                new_count += 1
        except Exception as e:
            if "UNIQUE" not in str(e):
                log.debug("DB insert: %s", e)
            continue

        # Telegram-Alert für hohe Scores
        if entry["score"] >= min_score_alert:
            await _send_lead_alert(entry)
            alert_count += 1
            await asyncio.sleep(0.5)

    # Scan-Log
    with _db() as conn:
        conn.execute(
            "INSERT INTO ir_scan_log (started_at, finished_at, new_leads, alerted) VALUES (?,?,?,?)",
            (started, int(time.time()), new_count, alert_count)
        )

    summary = f"InsolvenzRadar: {new_count} neue Leads, {alert_count} Alerts gesendet"
    log.info(summary)

    if new_count > 0:
        await _send_summary_tg(new_count, alert_count)

    return {
        "ok":           True,
        "new_leads":    new_count,
        "alerts_sent":  alert_count,
        "duration_s":   int(time.time()) - started,
        "scanned_at":   datetime.now(timezone.utc).isoformat()
    }


def _extract_rechtsform(name: str) -> str:
    for rf in ["GmbH & Co. KG", "GmbH", "AG", "UG", "OHG", "KG", "e.K.", "GbR", "e.V."]:
        if rf.lower() in name.lower():
            return rf
    return "Unbekannt"


async def _send_lead_alert(entry: Dict):
    score  = entry.get("score", 0)
    name   = entry.get("debtor_name", "?")
    court  = entry.get("court", "?")
    bl     = BUNDESLAENDER.get(entry.get("bundesland", ""), entry.get("bundesland", "?"))
    branche = entry.get("branche", "?")
    types  = json.loads(entry.get("lead_types", "[]"))
    summary = entry.get("ai_summary", "")
    ins_type = entry.get("insolvency_type", "Insolvenz")
    pub_date = entry.get("publication_date", "?")

    score_emoji = "🔴" if score >= 80 else "🟡" if score >= 60 else "🟢"

    msg = f"""{score_emoji} <b>InsolvenzRadar — Score {score}/100</b>

🏢 <b>{name}</b>
📍 {bl} | Gericht: {court}
📅 {pub_date} | {ins_type}
🏭 Branche: {branche}

🎯 <b>Ideal für:</b> {', '.join(types)}
{f'💡 {summary}' if summary else ''}

<i>Dashboard: /insolvenz-radar</i>"""

    await _tg(msg)
    with _db() as conn:
        conn.execute("UPDATE ir_leads SET alerted=1 WHERE uid=?", (entry["uid"],))


async def _send_summary_tg(new_count: int, alert_count: int):
    top_leads = get_top_leads(limit=3)
    lines = [f"📊 <b>InsolvenzRadar — Täglicher Report</b>",
             f"🆕 {new_count} neue Leads | 🔔 {alert_count} Alerts\n"]
    for lead in top_leads:
        lines.append(f"• <b>{lead['debtor_name']}</b> — Score {lead['score']} | {lead['branche']}")
    lines.append(f"\n🌐 Dashboard: /insolvenz-radar")
    await _tg("\n".join(lines))


# ── Status & Leads API ────────────────────────────────────────────────────────

def get_status() -> Dict:
    init_db()
    with _db() as conn:
        total       = conn.execute("SELECT COUNT(*) FROM ir_leads").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM ir_leads WHERE created_at > ?",
            (int(time.time()) - 86400,)
        ).fetchone()[0]
        high_score  = conn.execute(
            "SELECT COUNT(*) FROM ir_leads WHERE score >= 70"
        ).fetchone()[0]
        alerted     = conn.execute("SELECT COUNT(*) FROM ir_leads WHERE alerted=1").fetchone()[0]
        last_scan   = conn.execute(
            "SELECT finished_at, new_leads FROM ir_scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        top_bl      = conn.execute(
            "SELECT bundesland, COUNT(*) as cnt FROM ir_leads GROUP BY bundesland ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
    return {
        "ok":          True,
        "total_leads": total,
        "leads_today": today_count,
        "high_score":  high_score,
        "alerted":     alerted,
        "last_scan":   dict(last_scan) if last_scan else {},
        "top_bundeslaender": [dict(r) for r in top_bl],
        "stripe_prices": {
            "starter": _price_starter(),
            "pro":     _price_pro(),
            "agency":  _price_agency(),
        }
    }


def get_leads(
    bundesland: str = "",
    min_score: int = 0,
    branche: str = "",
    source: str = "",
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:
    init_db()
    where = ["1=1"]
    params = []
    if bundesland:
        where.append("bundesland=?")
        params.append(bundesland)
    if min_score:
        where.append("score >= ?")
        params.append(min_score)
    if branche:
        where.append("branche=?")
        params.append(branche)
    if source:
        where.append("source=?")
        params.append(source)

    params += [limit, offset]
    with _db() as conn:
        rows = conn.execute(
            f"""SELECT * FROM ir_leads WHERE {' AND '.join(where)}
                ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?""",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def get_top_leads(limit: int = 10) -> List[Dict]:
    return get_leads(min_score=60, limit=limit)


# ── Stripe Checkout ───────────────────────────────────────────────────────────

async def create_checkout(email: str, tier: str = "starter") -> Dict:
    price_map = {"starter": _price_starter(), "pro": _price_pro(), "agency": _price_agency()}
    price_id  = price_map.get(tier, _price_starter())
    key       = _stripe_key()
    if not key:
        return {"error": "STRIPE_SECRET_KEY nicht gesetzt"}

    base = _dashboard_url()
    try:
        async with _session(20) as s:
            async with s.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={"Authorization": f"Bearer {key}"},
                data={
                    "payment_method_types[]":  "card",
                    "mode":                    "subscription",
                    "line_items[0][price]":    price_id,
                    "line_items[0][quantity]": "1",
                    "customer_email":          email,
                    "success_url": f"{base}/insolvenz-radar/success?session={{CHECKOUT_SESSION_ID}}",
                    "cancel_url":  f"{base}/insolvenz-radar",
                    "metadata[tier]":    tier,
                    "metadata[service]": "insolvenz_radar"
                }
            ) as r:
                d = await r.json()
                return {
                    "ok":           "id" in d,
                    "checkout_url": d.get("url", ""),
                    "session_id":   d.get("id", ""),
                    "error":        d.get("error", {}).get("message", "") if "error" in d else ""
                }
    except Exception as e:
        return {"error": str(e)}


init_db()
