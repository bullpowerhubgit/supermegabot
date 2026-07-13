#!/usr/bin/env python3
"""
SYS-08: Unternehmens-Intelligence Broker
=========================================
Handelsregister + Insolvenz + ZVG + AI Act Risiko = vollständiges Unternehmens-Profil.
Banken, Factoring-Firmen, Kreditversicherer zahlen €500–5.000 pro Report.

Tiers:
  Einzel-Report:    €499    — einmalig, Checkout → Webhook → Email-Delivery
  Marktwatch-Abo:  €1.999/mo — tägl. Alerts für 50 beobachtete Firmen
  Enterprise API:  €4.999/mo — vollständiger API-Zugang, White-Label

Starten:
  python3 intelligence_broker.py              # Daemon (tägl. 09:30 Watchlist-Check)
  python3 intelligence_broker.py --now        # Sofort: Watchlist + Outreach
  python3 intelligence_broker.py --report FIRMA   # Sofort-Report für Firma
  python3 intelligence_broker.py --watch FIRMA EMAIL  # Zur Watchlist hinzufügen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sqlite3
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [IB] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("IntelligenceBroker")

# ── Pfade ─────────────────────────────────────────────────────────────────────
_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "intelligence_broker.db"

# Quell-DBs der Radar-Module
_DB_INSOLVENZ       = _BASE / "data" / "insolvenz_radar.db"
_DB_HANDELSREGISTER = _BASE / "data" / "handelsregister_radar.db"
_DB_ZVG             = _BASE / "data" / "zvg_radar.db"
_DB_AI_ACT          = _BASE / "data" / "ai_act_scanner.db"


# ── .env Loader ───────────────────────────────────────────────────────────────
def _load_env() -> None:
    env_file = _BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()


# ── Credential-Helfer ─────────────────────────────────────────────────────────
def _stripe()        -> str: return os.getenv("STRIPE_SECRET_KEY", "")
def _stripe_wh()     -> str: return os.getenv("STRIPE_WEBHOOK_SECRET", "")
def _anthropic()     -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _tg_token()      -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()       -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _gmail_user()    -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass()    -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "")
def _dashboard_url() -> str: return os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

# Stripe Price IDs — eigene Env-Vars, Fallback auf bekannte IDs
def _price_single()  -> str: return os.getenv("IB_PRICE_SINGLE",      "price_1TjodoRJECiV6vSmL726jLd3")
def _price_watch()   -> str: return os.getenv("IB_PRICE_WATCH",       "price_1TjodoRJECiV6vSmcWkhHtWz")
def _price_enterprise() -> str: return os.getenv("IB_PRICE_ENTERPRISE", "price_1TjodpRJECiV6vSmFVtPj8yb")

# Outreach-Zielgruppen (B2B: Banken, Factoring, Kreditversicherer)
OUTREACH_TARGETS: list = []  # Echte Adressen über Dashboard /api/intelligence/outreach/add eintragen

RISIKO_SCHWELLE_ALERT = 20   # Punkte Anstieg → Watchlist-Alert


# ══════════════════════════════════════════════════════════════════════════════
# Datenklassen
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CompanyProfile:
    company_name: str
    handelsregister_data: Dict     = field(default_factory=dict)
    insolvenz_score: int           = 0
    zvg_score: int                 = 0
    ai_act_risk: str               = "Unbekannt"
    overall_risk_score: int        = 0
    recommendation: str            = "Keine Empfehlung"
    events: List[Dict]             = field(default_factory=list)
    report_html: str               = ""
    created_at: str                = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "CompanyProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ══════════════════════════════════════════════════════════════════════════════
# Datenbank-Initialisierung
# ══════════════════════════════════════════════════════════════════════════════

def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name     TEXT NOT NULL,
            profile_json     TEXT,
            report_html      TEXT,
            paid             INTEGER DEFAULT 0,
            client_email     TEXT,
            stripe_session_id TEXT,
            created_at       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            last_score   INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(company_name, client_email)
        );

        CREATE TABLE IF NOT EXISTS outreach (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            target_email TEXT NOT NULL,
            company_name TEXT NOT NULL,
            sent_at      TEXT DEFAULT (datetime('now')),
            UNIQUE(target_email, company_name)
        );
    """)
    con.commit()
    con.close()
    log.info("DB initialisiert: %s", _DB_PATH)


# ══════════════════════════════════════════════════════════════════════════════
# Hilfsfunktionen: Quell-DBs abfragen
# ══════════════════════════════════════════════════════════════════════════════

def _query_db(db_path: Path, sql: str, params: tuple = ()) -> List[Dict]:
    """Liest Daten aus einer Quell-DB. Gibt leere Liste zurück wenn DB fehlt."""
    if not db_path.exists():
        log.debug("Quell-DB nicht gefunden: %s", db_path)
        return []
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.warning("DB-Fehler (%s): %s", db_path.name, exc)
        return []


def _find_insolvenz_entries(company_name: str) -> List[Dict]:
    """Sucht Insolvenz-Einträge für eine Firma (fuzzy LIKE-Suche)."""
    # Mehrteilige Suche: erstes Wort + optional zweites Wort
    words   = company_name.split()
    pattern = f"%{words[0]}%"
    rows = _query_db(
        _DB_INSOLVENZ,
        "SELECT * FROM ir_leads WHERE debtor_name LIKE ? ORDER BY publication_date DESC LIMIT 10",
        (pattern,),
    )
    # Breiteren Match versuchen falls nichts gefunden
    if not rows and len(words) >= 2:
        pattern2 = f"%{words[1]}%"
        rows = _query_db(
            _DB_INSOLVENZ,
            "SELECT * FROM ir_leads WHERE debtor_name LIKE ? ORDER BY publication_date DESC LIMIT 10",
            (pattern2,),
        )
    return rows


def _find_handelsregister_entries(company_name: str) -> List[Dict]:
    words   = company_name.split()
    pattern = f"%{words[0]}%"
    rows = _query_db(
        _DB_HANDELSREGISTER,
        "SELECT * FROM hr_leads WHERE firma LIKE ? ORDER BY datum DESC LIMIT 5",
        (pattern,),
    )
    if not rows and len(words) >= 2:
        pattern2 = f"%{words[1]}%"
        rows = _query_db(
            _DB_HANDELSREGISTER,
            "SELECT * FROM hr_leads WHERE firma LIKE ? ORDER BY datum DESC LIMIT 5",
            (pattern2,),
        )
    return rows


def _find_zvg_entries(company_name: str) -> List[Dict]:
    """ZVG-Leads haben keine Firmennamen, aber Adressen."""
    words   = company_name.split()
    pattern = f"%{words[0]}%"
    rows = _query_db(
        _DB_ZVG,
        "SELECT * FROM zvg_leads WHERE objekt_adresse LIKE ? ORDER BY scraped_at DESC LIMIT 5",
        (pattern,),
    )
    return rows


def _find_ai_act_entries(company_name: str) -> List[Dict]:
    words   = company_name.split()
    pattern = f"%{words[0]}%"
    rows = _query_db(
        _DB_AI_ACT,
        "SELECT * FROM aia_scans WHERE firma LIKE ? ORDER BY scanned_at DESC LIMIT 5",
        (pattern,),
    )
    if not rows and len(words) >= 2:
        pattern2 = f"%{words[1]}%"
        rows = _query_db(
            _DB_AI_ACT,
            "SELECT * FROM aia_scans WHERE firma LIKE ? ORDER BY scanned_at DESC LIMIT 5",
            (pattern2,),
        )
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Scoring-Logik
# ══════════════════════════════════════════════════════════════════════════════

def _calc_insolvenz_score(entries: List[Dict]) -> int:
    """Score 0-100 basierend auf Anzahl + Art der Insolvenz-Einträge."""
    if not entries:
        return 0
    score = min(len(entries) * 30, 70)
    for e in entries:
        status = str(e.get("status", e.get("verfahren_status", ""))).lower()
        if "eroeffnet" in status or "eröffnet" in status or "opened" in status:
            score = min(score + 20, 100)
        if "abgewiesen" in status or "eingestellt" in status:
            score = max(score - 10, score)
    return min(score, 100)


def _calc_zvg_score(entries: List[Dict]) -> int:
    """Score 0-100 für ZVG-Risiko."""
    if not entries:
        return 0
    score = min(len(entries) * 25, 80)
    for e in entries:
        wert = e.get("verkehrswert", e.get("wert", 0)) or 0
        try:
            wert = float(str(wert).replace(".", "").replace(",", ".").replace("€", "").strip())
        except (ValueError, TypeError):
            wert = 0
        if wert > 500_000:
            score = min(score + 10, 100)
    return min(score, 100)


def _calc_ai_act_risk(entries: List[Dict], company_name: str) -> str:
    """Gibt 'Hoch', 'Mittel' oder 'Niedrig' zurück."""
    if not entries:
        # Heuristik nach Branche aus Firmenname
        name_lower = company_name.lower()
        if any(k in name_lower for k in ["ki ", "ai ", "tech", "software", "digital", "auto", "medizin", "pflege"]):
            return "Mittel"
        return "Niedrig"
    # Spalte in aia_scans: risiko_level (Werte: "hoch", "mittel", "niedrig")
    for e in entries:
        risk = str(e.get("risiko_level", e.get("risk_level", ""))).lower()
        if risk in ("hoch", "high", "critical"):
            return "Hoch"
        if risk in ("mittel", "medium", "moderate"):
            return "Mittel"
    return "Niedrig"


def _calc_overall_score(insolvenz: int, zvg: int, ai_act: str) -> int:
    """Gewichteter Gesamt-Score: Insolvenz 50%, ZVG 35%, AI-Act 15%."""
    ai_penalty = {"Hoch": 15, "Mittel": 8, "Niedrig": 0, "Unbekannt": 3}
    score = int(insolvenz * 0.50 + zvg * 0.35 + ai_penalty.get(ai_act, 3))
    return min(score, 100)


def _make_recommendation(overall: int) -> str:
    if overall >= 70:
        return "Ablehnen"
    if overall >= 40:
        return "Kreditlimit senken"
    return "Kreditlimit erhöhen"


def _extract_events(
    insolvenz_entries: List[Dict],
    zvg_entries: List[Dict],
    hr_entries: List[Dict],
) -> List[Dict]:
    """Vereinheitlichte Event-Timeline aus allen Quellen.
    Spalten:
      ir_leads:  debtor_name, court, insolvency_type, publication_date
      hr_leads:  firma, rechtsform, amtsgericht, datum
      zvg_leads: objekt_typ, objekt_adresse, verkehrswert, termin_datum, scraped_at
    """
    events: List[Dict] = []

    for e in hr_entries:
        events.append({
            "datum":        str(e.get("datum", ""))[:10],
            "typ":          "Handelsregister",
            "beschreibung": f"Neueintragung/Änderung — {e.get('rechtsform', '')}".strip(" —"),
            "quelle":       "handelsregister.de",
            "schwere":      "info",
        })

    for e in insolvenz_entries:
        events.append({
            "datum":        str(e.get("publication_date", ""))[:10],
            "typ":          "Insolvenz",
            "beschreibung": e.get("insolvency_type") or "Insolvenzverfahren",
            "quelle":       "insolvenzbekanntmachungen.de",
            "schwere":      "kritisch",
        })

    for e in zvg_entries:
        wert = e.get("verkehrswert", "")
        beschr = f"Zwangsversteigerung — {e.get('objekt_typ', 'Immobilie')}"
        if wert:
            beschr += f" (Verkehrswert: {wert})"
        events.append({
            "datum":        str(e.get("termin_datum") or e.get("scraped_at", ""))[:10],
            "typ":          "ZVG",
            "beschreibung": beschr,
            "quelle":       "zvg-portal.de",
            "schwere":      "warnung",
        })

    events.sort(key=lambda x: x.get("datum") or "", reverse=True)
    return events[:20]


# ══════════════════════════════════════════════════════════════════════════════
# HTML-Report-Generator (kein externes PDF-Lib!)
# ══════════════════════════════════════════════════════════════════════════════

def _gauge_svg(value: int, label: str, color: str) -> str:
    """Erzeugt einen SVG-Halbkreis-Gauge für Risiko-Scores."""
    pct   = min(max(value, 0), 100) / 100
    r     = 54
    circ  = 3.14159 * r
    dash  = pct * circ
    gap   = circ - dash
    rot   = -90
    return f"""
    <svg width="130" height="80" viewBox="0 0 130 80">
      <circle cx="65" cy="65" r="{r}" fill="none" stroke="#2a2a3e" stroke-width="14"
              stroke-dasharray="{circ:.1f} {circ:.1f}"
              stroke-dashoffset="{circ/2:.1f}"
              transform="rotate({rot} 65 65)"/>
      <circle cx="65" cy="65" r="{r}" fill="none" stroke="{color}" stroke-width="14"
              stroke-linecap="round"
              stroke-dasharray="{dash:.1f} {gap:.1f}"
              stroke-dashoffset="{circ/2:.1f}"
              transform="rotate({rot} 65 65)"/>
      <text x="65" y="63" text-anchor="middle" fill="#e8eaf6" font-size="20" font-weight="700">{value}</text>
      <text x="65" y="77" text-anchor="middle" fill="#9e9ec8" font-size="9">{label}</text>
    </svg>"""


def _risk_color(score: int) -> str:
    if score >= 70: return "#ef5350"
    if score >= 40: return "#ffa726"
    return "#66bb6a"


def _ai_badge_color(risk: str) -> str:
    return {"Hoch": "#ef5350", "Mittel": "#ffa726", "Niedrig": "#66bb6a"}.get(risk, "#78909c")


def _rec_color(rec: str) -> str:
    return {"Ablehnen": "#ef5350", "Kreditlimit senken": "#ffa726", "Kreditlimit erhöhen": "#66bb6a"}.get(rec, "#78909c")


def _events_html(events: List[Dict]) -> str:
    if not events:
        return '<p style="color:#9e9ec8;text-align:center;padding:1rem;">Keine historischen Ereignisse gefunden.</p>'
    rows = ""
    farbe_map = {"kritisch": "#ef5350", "warnung": "#ffa726", "info": "#66bb6a"}
    icon_map  = {"Insolvenz": "⚠️", "ZVG": "🏠", "Handelsregister": "📋"}
    for ev in events:
        farbe = farbe_map.get(ev.get("schwere", "info"), "#78909c")
        icon  = icon_map.get(ev.get("typ", ""), "•")
        datum = (ev.get("datum") or "Unbekannt")[:10]
        rows += f"""
        <tr>
          <td style="color:#9e9ec8;white-space:nowrap;padding:6px 10px;">{datum}</td>
          <td style="padding:6px 10px;">{icon} <span style="color:{farbe};font-weight:600;">{ev.get('typ','')}</span></td>
          <td style="padding:6px 10px;color:#e0e0f0;">{ev.get('beschreibung','')}</td>
          <td style="padding:6px 10px;color:#7986cb;font-size:0.85em;">{ev.get('quelle','')}</td>
        </tr>"""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
      <thead>
        <tr style="border-bottom:1px solid #2a2a4e;">
          <th style="text-align:left;color:#9e9ec8;padding:6px 10px;">Datum</th>
          <th style="text-align:left;color:#9e9ec8;padding:6px 10px;">Typ</th>
          <th style="text-align:left;color:#9e9ec8;padding:6px 10px;">Ereignis</th>
          <th style="text-align:left;color:#9e9ec8;padding:6px 10px;">Quelle</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _hr_table_html(data: Dict) -> str:
    if not data:
        return '<p style="color:#9e9ec8;">Keine Handelsregister-Daten verfügbar.</p>'
    rows = ""
    for k, v in data.items():
        if v:
            rows += f'<tr><td style="color:#9e9ec8;padding:4px 10px;width:35%;">{k}</td><td style="color:#e0e0f0;padding:4px 10px;">{v}</td></tr>'
    return f'<table style="width:100%;border-collapse:collapse;font-size:0.9rem;">{rows}</table>'


def generate_report_html(profile: CompanyProfile) -> str:
    """Vollständiger Dark-Theme HTML-Report ohne externe Bibliotheken."""
    now_str      = datetime.now().strftime("%d.%m.%Y %H:%M Uhr")
    gauge_insolv = _gauge_svg(profile.insolvenz_score, "Insolvenz", _risk_color(profile.insolvenz_score))
    gauge_zvg    = _gauge_svg(profile.zvg_score,       "ZVG",       _risk_color(profile.zvg_score))
    gauge_overall = _gauge_svg(profile.overall_risk_score, "Gesamt", _risk_color(profile.overall_risk_score))
    rec_color    = _rec_color(profile.recommendation)
    ai_color     = _ai_badge_color(profile.ai_act_risk)
    events_html  = _events_html(profile.events)
    hr_html      = _hr_table_html(profile.handelsregister_data)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Risikoprofil: {profile.company_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0d0d1a;
    color: #e0e0f0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.6;
  }}
  .page {{ max-width: 900px; margin: 0 auto; padding: 32px 24px; }}
  .header {{
    display: flex; justify-content: space-between; align-items: flex-start;
    padding-bottom: 24px; border-bottom: 2px solid #1a1a3e; margin-bottom: 28px;
  }}
  .logo-block h1 {{ font-size: 1.6rem; color: #7c83ff; letter-spacing: 0.5px; }}
  .logo-block p  {{ color: #9e9ec8; font-size: 0.85rem; margin-top: 4px; }}
  .report-meta   {{ text-align: right; color: #9e9ec8; font-size: 0.82rem; }}
  .company-banner {{
    background: linear-gradient(135deg, #12124a 0%, #1a1a3e 100%);
    border: 1px solid #2a2a5e; border-radius: 12px;
    padding: 24px 28px; margin-bottom: 24px;
  }}
  .company-banner h2 {{ font-size: 1.8rem; color: #e8eaf6; }}
  .company-banner .sub {{ color: #9e9ec8; margin-top: 6px; font-size: 0.9rem; }}
  .section {{
    background: #12122a; border: 1px solid #1e1e42;
    border-radius: 12px; padding: 22px 24px; margin-bottom: 20px;
  }}
  .section-title {{
    font-size: 0.78rem; font-weight: 700; letter-spacing: 1.5px;
    color: #7c83ff; text-transform: uppercase; margin-bottom: 16px;
  }}
  .gauges {{ display: flex; gap: 24px; justify-content: space-around; flex-wrap: wrap; }}
  .gauge-box {{ text-align: center; }}
  .rec-box {{
    background: {rec_color}18; border: 2px solid {rec_color};
    border-radius: 10px; padding: 18px 22px;
    display: flex; align-items: center; gap: 16px;
  }}
  .rec-icon  {{ font-size: 2rem; }}
  .rec-text  {{ }}
  .rec-label {{ font-size: 0.75rem; color: #9e9ec8; text-transform: uppercase; letter-spacing: 1px; }}
  .rec-value {{ font-size: 1.3rem; font-weight: 700; color: {rec_color}; margin-top: 2px; }}
  .ai-badge {{
    display: inline-block; padding: 6px 18px;
    background: {ai_color}22; border: 1px solid {ai_color};
    border-radius: 20px; color: {ai_color};
    font-weight: 700; font-size: 1rem; margin-left: 12px;
  }}
  .ai-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
  .ai-label {{ color: #9e9ec8; font-size: 0.9rem; }}
  .disclaimer {{
    background: #0f0f22; border: 1px solid #1a1a38;
    border-radius: 8px; padding: 16px 20px; margin-top: 28px;
    color: #6b6b9a; font-size: 0.78rem; line-height: 1.7;
  }}
  .footer {{ text-align: center; color: #3d3d60; font-size: 0.78rem; margin-top: 24px; padding-top: 16px; border-top: 1px solid #1a1a3e; }}
  @media print {{
    body {{ background: white; color: black; }}
    .section {{ border: 1px solid #ccc; background: #f9f9f9; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="logo-block">
      <h1>⚡ SuperMegaBot Intelligence</h1>
      <p>Unternehmens-Risikoprofil — Vertraulich</p>
    </div>
    <div class="report-meta">
      <div>Erstellt: {now_str}</div>
      <div style="margin-top:4px;">Report-ID: IB-{int(time.time())}</div>
      <div style="margin-top:4px;color:#3d3d60;">Datenquellen: 4 Radar-Module</div>
    </div>
  </div>

  <!-- Firmen-Banner -->
  <div class="company-banner">
    <h2>{profile.company_name}</h2>
    <div class="sub">
      Vollständiges Risikoprofil · Stand {now_str}
    </div>
  </div>

  <!-- Risiko-Gauges -->
  <div class="section">
    <div class="section-title">Risiko-Übersicht</div>
    <div class="gauges">
      <div class="gauge-box">{gauge_insolv}</div>
      <div class="gauge-box">{gauge_zvg}</div>
      <div class="gauge-box">{gauge_overall}</div>
    </div>
  </div>

  <!-- EU AI Act -->
  <div class="section">
    <div class="section-title">EU AI Act Compliance-Risiko</div>
    <div class="ai-row">
      <span class="ai-label">Einschätzung für <strong style="color:#e0e0f0;">{profile.company_name}</strong>:</span>
      <span class="ai-badge">{profile.ai_act_risk}</span>
    </div>
    <p style="color:#9e9ec8;margin-top:12px;font-size:0.88rem;">
      Bußgelder bis €35 Mio. oder 7 % Jahresumsatz ab 2. August 2026.
      {'Dringende Compliance-Prüfung empfohlen.' if profile.ai_act_risk == 'Hoch' else
       'Überprüfung der KI-Systeme empfohlen.' if profile.ai_act_risk == 'Mittel' else
       'Geringes Risiko — regelmäßige Überprüfung ausreichend.'}
    </p>
  </div>

  <!-- Empfehlung -->
  <div class="section">
    <div class="section-title">Kreditempfehlung</div>
    <div class="rec-box">
      <div class="rec-icon">{'🔴' if profile.recommendation == 'Ablehnen' else '🟡' if 'senken' in profile.recommendation else '🟢'}</div>
      <div class="rec-text">
        <div class="rec-label">Empfehlung</div>
        <div class="rec-value">{profile.recommendation}</div>
      </div>
    </div>
    <p style="color:#9e9ec8;margin-top:14px;font-size:0.88rem;">
      Basierend auf Gesamt-Score {profile.overall_risk_score}/100
      (Insolvenz: {profile.insolvenz_score} · ZVG: {profile.zvg_score} · AI Act: {profile.ai_act_risk})
    </p>
  </div>

  <!-- Handelsregister -->
  <div class="section">
    <div class="section-title">Handelsregister-Daten</div>
    {hr_html}
  </div>

  <!-- Event-Timeline -->
  <div class="section">
    <div class="section-title">Ereignis-Timeline</div>
    {events_html}
  </div>

  <!-- Haftungsausschluss -->
  <div class="disclaimer">
    <strong>Haftungsausschluss:</strong> Dieser Report wurde vollautomatisch auf Basis öffentlich
    zugänglicher Quellen (Handelsregister, Insolvenzbekanntmachungen, ZVG-Portal, EU-Regulierungsdatenbanken)
    erstellt. Die enthaltenen Informationen dienen ausschließlich als erste Orientierung und ersetzen
    keine rechtliche oder wirtschaftliche Beratung durch qualifizierte Fachleute. SuperMegaBot /
    AiiteC übernimmt keine Haftung für die Vollständigkeit, Aktualität oder Richtigkeit der Daten.
    Vertraulich — nur für den Empfänger bestimmt.
  </div>

  <div class="footer">
    SuperMegaBot Intelligence Broker · ineedit.com.co · AiiteC ·
    Report erstellt {now_str}
  </div>

</div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# Haupt-Klasse
# ══════════════════════════════════════════════════════════════════════════════

class IntelligenceBroker:
    """
    Aggregiert Daten aus allen 4 Radar-Modulen zu vollständigen Unternehmens-
    Risikoprofilen und monetarisiert diese über Stripe (€499–€4.999).
    """

    def __init__(self) -> None:
        _init_db()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "SuperMegaBot/2.0 IntelligenceBroker"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Daten-Aggregation ─────────────────────────────────────────────────────

    async def aggregate_company_data(self, company_name: str) -> CompanyProfile:
        """
        Liest alle verfügbaren Daten aus den 4 Quell-DBs und baut ein
        vollständiges CompanyProfile auf.
        """
        log.info("Aggregiere Daten für: %s", company_name)

        # Parallel aus allen Quell-DBs lesen (asyncio.to_thread weil SQLite synchron)
        insolvenz_entries, zvg_entries, hr_entries, ai_entries = await asyncio.gather(
            asyncio.to_thread(_find_insolvenz_entries, company_name),
            asyncio.to_thread(_find_zvg_entries, company_name),
            asyncio.to_thread(_find_handelsregister_entries, company_name),
            asyncio.to_thread(_find_ai_act_entries, company_name),
        )

        log.info(
            "Gefunden: %d Insolvenz, %d ZVG, %d HR, %d AI-Act Einträge",
            len(insolvenz_entries), len(zvg_entries), len(hr_entries), len(ai_entries),
        )

        # Handelsregister-Stammdaten (neuester Eintrag)
        # Echte Spalten: uid, firma, rechtsform, amtsgericht, registernr, bundesland, ort, datum, score
        hr_data: Dict = {}
        if hr_entries:
            e = hr_entries[0]
            hr_data = {
                "Firma":        e.get("firma", company_name),
                "Rechtsform":   e.get("rechtsform", "Unbekannt"),
                "Sitz":         e.get("ort", ""),
                "Amtsgericht":  e.get("amtsgericht", ""),
                "HRB-Nummer":   e.get("registernr", ""),
                "Bundesland":   e.get("bundesland", ""),
                "Eintragung":   str(e.get("datum", ""))[:10],
            }
            hr_data = {k: v for k, v in hr_data.items() if v}  # Leere Felder entfernen

        # Scores berechnen
        insolvenz_score = _calc_insolvenz_score(insolvenz_entries)
        zvg_score       = _calc_zvg_score(zvg_entries)
        ai_act_risk     = _calc_ai_act_risk(ai_entries, company_name)
        overall_score   = _calc_overall_score(insolvenz_score, zvg_score, ai_act_risk)
        recommendation  = _make_recommendation(overall_score)
        events          = _extract_events(insolvenz_entries, zvg_entries, hr_entries)

        profile = CompanyProfile(
            company_name          = company_name,
            handelsregister_data  = hr_data,
            insolvenz_score       = insolvenz_score,
            zvg_score             = zvg_score,
            ai_act_risk           = ai_act_risk,
            overall_risk_score    = overall_score,
            recommendation        = recommendation,
            events                = events,
        )
        profile.report_html = await self.generate_report_html(profile)

        # In DB speichern
        await asyncio.to_thread(self._save_report, profile)

        log.info(
            "Profil erstellt: %s — Score %d — Empfehlung: %s",
            company_name, overall_score, recommendation,
        )
        return profile

    def _save_report(self, profile: CompanyProfile, client_email: str = "",
                     stripe_session_id: str = "", paid: int = 0) -> int:
        con = sqlite3.connect(_DB_PATH)
        cur = con.execute(
            """INSERT INTO reports (company_name, profile_json, report_html, paid, client_email, stripe_session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                profile.company_name,
                json.dumps(profile.to_dict(), ensure_ascii=False),
                profile.report_html,
                paid,
                client_email,
                stripe_session_id,
            ),
        )
        report_id = cur.lastrowid
        con.commit()
        con.close()
        return report_id

    # ── HTML-Report ───────────────────────────────────────────────────────────

    async def generate_report_html(self, profile: CompanyProfile) -> str:
        return generate_report_html(profile)

    # ── Stripe Checkout ───────────────────────────────────────────────────────

    async def create_stripe_checkout(
        self,
        company_name: str,
        tier: str = "single",
        client_email: str = "",
    ) -> str:
        """
        Erstellt eine Stripe Checkout Session.
        tier: 'single' (€499) | 'watch' (€1.999/mo) | 'enterprise' (€4.999/mo)
        Gibt die checkout_url zurück.
        """
        key = _stripe()
        if not key:
            log.warning("STRIPE_SECRET_KEY fehlt — kein Checkout möglich")
            return ""

        price_map = {
            "single":     (_price_single(),     "payment"),
            "watch":      (_price_watch(),      "subscription"),
            "enterprise": (_price_enterprise(), "subscription"),
        }
        price_id, mode = price_map.get(tier, (_price_single(), "payment"))

        metadata = {
            "product":      "intelligence_broker",
            "company_name": company_name[:490],
            "tier":         tier,
        }

        payload: Dict = {
            "mode":                       mode,
            "success_url":                f"{_dashboard_url()}/intelligence/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url":                 f"{_dashboard_url()}/intelligence/cancel",
            "metadata[product]":          metadata["product"],
            "metadata[company_name]":     metadata["company_name"],
            "metadata[tier]":             metadata["tier"],
            "line_items[0][price]":       price_id,
            "line_items[0][quantity]":    "1",
        }
        if client_email:
            payload["customer_email"] = client_email

        try:
            session = await self._get_session()
            async with session.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=aiohttp.BasicAuth(key, ""),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error("Stripe Fehler %d: %s", resp.status, body[:300])
                    return ""
                data = await resp.json()
                url = data.get("url", "")
                log.info("Stripe Checkout erstellt: %s (tier=%s)", url[:60], tier)
                return url
        except Exception as exc:
            log.error("Stripe Exception: %s", exc)
            return ""

    # ── Email-Versand ─────────────────────────────────────────────────────────

    async def send_report_email(self, email: str, profile: CompanyProfile) -> bool:
        """Sendet den vollständigen HTML-Report per Email."""
        user = _gmail_user()
        pw   = _gmail_pass()
        if not user or not pw:
            log.warning("Gmail-Credentials fehlen — kein Email-Versand")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Ihr Risikoprofil: {profile.company_name} — Intelligence Report"
        msg["From"]    = f"SuperMegaBot Intelligence <{user}>"
        msg["To"]      = email

        text_body = (
            f"Sehr geehrte Damen und Herren,\n\n"
            f"anbei erhalten Sie das vollständige Risikoprofil für {profile.company_name}.\n\n"
            f"Gesamt-Risiko-Score: {profile.overall_risk_score}/100\n"
            f"Empfehlung: {profile.recommendation}\n\n"
            f"Bitte öffnen Sie die HTML-Ansicht für das vollständige Profil.\n\n"
            f"Mit freundlichen Grüßen,\nSuperMegaBot Intelligence"
        )
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(profile.report_html, "html", "utf-8"))

        try:
            await asyncio.to_thread(self._smtp_send, user, pw, email, msg)
            log.info("Report per Email gesendet an: %s", email)
            return True
        except Exception as exc:
            log.error("Email-Versand fehlgeschlagen: %s", exc)
            return False

    @staticmethod
    def _smtp_send(user: str, pw: str, to: str, msg: MIMEMultipart) -> None:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(user, pw)
            smtp.sendmail(user, to, msg.as_string())

    # ── Watchlist ─────────────────────────────────────────────────────────────

    async def add_to_watchlist(self, company_name: str, client_email: str) -> bool:
        """Fügt eine Firma zur Watchlist hinzu und erstellt sofort ein Baseline-Profil."""
        log.info("Watchlist: Füge hinzu — %s (%s)", company_name, client_email)
        try:
            profile = await self.aggregate_company_data(company_name)
            await asyncio.to_thread(
                self._upsert_watchlist, company_name, client_email, profile.overall_risk_score
            )
            return True
        except Exception as exc:
            log.error("Watchlist add Fehler: %s", exc)
            return False

    def _upsert_watchlist(self, company_name: str, client_email: str, score: int) -> None:
        con = sqlite3.connect(_DB_PATH)
        con.execute(
            """INSERT INTO watchlist (company_name, client_email, last_score)
               VALUES (?, ?, ?)
               ON CONFLICT(company_name, client_email) DO UPDATE SET last_score = excluded.last_score""",
            (company_name, client_email, score),
        )
        con.commit()
        con.close()

    async def check_watchlist(self) -> List[Dict]:
        """
        Prüft alle Watchlist-Firmen. Gibt Alert-Liste zurück wenn Score ≥ 20 Pkt gestiegen.
        Sendet Telegram-Alerts und Emails.
        """
        entries = await asyncio.to_thread(self._load_watchlist)
        if not entries:
            log.info("Watchlist ist leer.")
            return []

        alerts: List[Dict] = []
        for entry in entries:
            company   = entry["company_name"]
            email     = entry["client_email"]
            old_score = entry["last_score"]

            try:
                profile   = await self.aggregate_company_data(company)
                new_score = profile.overall_risk_score
                delta     = new_score - old_score

                if delta >= RISIKO_SCHWELLE_ALERT:
                    alert = {
                        "company_name": company,
                        "client_email": email,
                        "old_score":    old_score,
                        "new_score":    new_score,
                        "delta":        delta,
                        "recommendation": profile.recommendation,
                    }
                    alerts.append(alert)
                    log.warning("ALERT: %s — Score +%d (%d → %d)", company, delta, old_score, new_score)

                    # Watchlist-Score aktualisieren
                    await asyncio.to_thread(self._upsert_watchlist, company, email, new_score)

                    # Telegram-Alert
                    await self._send_telegram_alert(alert)

                    # Email-Alert an Kunde
                    if email:
                        await self._send_watchlist_email(email, alert, profile)
                else:
                    log.info("Watchlist OK: %s (Score %d, delta %+d)", company, new_score, delta)
            except Exception as exc:
                log.error("Watchlist-Check Fehler für %s: %s", company, exc)

        log.info("Watchlist-Check abgeschlossen: %d Alerts", len(alerts))
        return alerts

    def _load_watchlist(self) -> List[Dict]:
        con = sqlite3.connect(_DB_PATH)
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM watchlist ORDER BY created_at").fetchall()
        con.close()
        return [dict(r) for r in rows]

    async def _send_telegram_alert(self, alert: Dict) -> None:
        token = _tg_token()
        chat  = _tg_chat()
        if not token or not chat:
            return
        text = (
            f"🚨 *Intelligence Broker — WATCHLIST ALERT*\n\n"
            f"Firma: `{alert['company_name']}`\n"
            f"Risiko-Score: {alert['old_score']} → *{alert['new_score']}* (+{alert['delta']} Punkte)\n"
            f"Empfehlung: *{alert['recommendation']}*\n"
            f"Kunde: {alert['client_email']}"
        )
        try:
            session = await self._get_session()
            await session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as exc:
            log.warning("Telegram-Alert fehlgeschlagen: %s", exc)

    async def _send_watchlist_email(
        self, email: str, alert: Dict, profile: CompanyProfile
    ) -> None:
        user = _gmail_user()
        pw   = _gmail_pass()
        if not user or not pw:
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"⚠️ RISIKO-ALERT: {alert['company_name']} — Score +{alert['delta']} Punkte"
        )
        msg["From"] = f"SuperMegaBot Intelligence <{user}>"
        msg["To"]   = email

        text_body = (
            f"RISIKO-ALERT für {alert['company_name']}\n\n"
            f"Der Risiko-Score ist um {alert['delta']} Punkte gestiegen!\n"
            f"Alter Score: {alert['old_score']} | Neuer Score: {alert['new_score']}\n"
            f"Empfehlung: {alert['recommendation']}\n\n"
            f"Vollständiger Report im Anhang."
        )
        html_body = f"""
        <div style="background:#0d0d1a;color:#e0e0f0;padding:24px;font-family:sans-serif;">
          <h2 style="color:#ef5350;">⚠️ Risiko-Alert: {alert['company_name']}</h2>
          <p>Der Risiko-Score ist signifikant gestiegen:</p>
          <table style="margin:16px 0;border-collapse:collapse;">
            <tr><td style="color:#9e9ec8;padding:4px 12px;">Alter Score:</td>
                <td style="font-weight:700;">{alert['old_score']}</td></tr>
            <tr><td style="color:#9e9ec8;padding:4px 12px;">Neuer Score:</td>
                <td style="font-weight:700;color:#ef5350;">{alert['new_score']}</td></tr>
            <tr><td style="color:#9e9ec8;padding:4px 12px;">Veränderung:</td>
                <td style="font-weight:700;color:#ef5350;">+{alert['delta']} Punkte</td></tr>
            <tr><td style="color:#9e9ec8;padding:4px 12px;">Empfehlung:</td>
                <td style="font-weight:700;">{alert['recommendation']}</td></tr>
          </table>
          <p style="color:#9e9ec8;font-size:0.85rem;">SuperMegaBot Intelligence Broker</p>
        </div>
        {profile.report_html}
        """
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            await asyncio.to_thread(self._smtp_send, user, pw, email, msg)
        except Exception as exc:
            log.warning("Watchlist-Email fehlgeschlagen: %s", exc)

    # ── B2B Outreach ──────────────────────────────────────────────────────────

    async def daily_outreach(self) -> int:
        """
        Sendet täglich 5 personalisierte Outreach-Emails an potenzielle Kunden
        (Banken, Factoring-Firmen, Kreditversicherer).
        Vermeidet Duplikate via outreach-Tabelle.
        Gibt Anzahl gesendeter Emails zurück.
        """
        log.info("Starte tägliches B2B Outreach...")
        user = _gmail_user()
        pw   = _gmail_pass()
        if not user or not pw:
            log.warning("Gmail-Credentials fehlen — kein Outreach")
            return 0

        # Zufällige Probe aus den Radar-DBs für Beispiel-Firma
        sample_firma = await asyncio.to_thread(self._get_sample_company)

        sent = 0
        max_per_day = 5
        for target in OUTREACH_TARGETS:
            if sent >= max_per_day:
                break

            already_sent = await asyncio.to_thread(
                self._outreach_exists, target["email"], sample_firma
            )
            if already_sent:
                log.debug("Outreach bereits gesendet: %s → %s", sample_firma, target["email"])
                continue

            success = await self._send_outreach_email(target, sample_firma)
            if success:
                await asyncio.to_thread(
                    self._save_outreach, target["email"], sample_firma
                )
                sent += 1
                await asyncio.sleep(2)  # Anti-Spam-Pause

        log.info("Outreach abgeschlossen: %d Emails gesendet", sent)
        return sent

    def _get_sample_company(self) -> str:
        """Holt eine zufällige Firma aus den Radar-DBs als Outreach-Beispiel."""
        rows = _query_db(
            _DB_HANDELSREGISTER,
            "SELECT firma FROM hr_leads ORDER BY RANDOM() LIMIT 1",
        )
        if rows:
            return rows[0].get("firma", "")
        rows = _query_db(
            _DB_INSOLVENZ,
            "SELECT debtor_name FROM ir_leads ORDER BY RANDOM() LIMIT 1",
        )
        if rows:
            return rows[0].get("debtor_name", "")
        return "Mustermann GmbH"

    def _outreach_exists(self, email: str, company: str) -> bool:
        con = sqlite3.connect(_DB_PATH)
        row = con.execute(
            "SELECT 1 FROM outreach WHERE target_email=? AND company_name=?",
            (email, company),
        ).fetchone()
        con.close()
        return row is not None

    def _save_outreach(self, email: str, company: str) -> None:
        con = sqlite3.connect(_DB_PATH)
        try:
            con.execute(
                "INSERT OR IGNORE INTO outreach (target_email, company_name) VALUES (?, ?)",
                (email, company),
            )
            con.commit()
        finally:
            con.close()

    async def _send_outreach_email(self, target: Dict, firma: str) -> bool:
        user = _gmail_user()
        pw   = _gmail_pass()
        if not user or not pw:
            return False

        typ   = target.get("typ", "Finanzinstitut")
        tname = target.get("firma", "")

        intro_map = {
            "Bank":              "Als kreditgebendes Institut benötigen Sie präzise Risikodaten.",
            "Factoring":         "Als Factoring-Unternehmen ist die Bonität Ihrer Klienten entscheidend.",
            "Kreditversicherung": "Als Kreditversicherer schützt präzises Debtor-Scoring Ihr Portfolio.",
        }
        intro = intro_map.get(typ, "Als Finanzdienstleister sind präzise Risikodaten wertvoll.")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Wir haben ein vollständiges Risikoprofil für {firma} erstellt"
        msg["From"]    = f"SuperMegaBot Intelligence <{user}>"
        msg["To"]      = target["email"]

        text = (
            f"Sehr geehrte Damen und Herren,\n\n"
            f"{intro}\n\n"
            f"Wir haben soeben ein vollständiges Unternehmens-Risikoprofil für\n"
            f"  {firma}\n"
            f"erstellt — auf Basis von Handelsregister, Insolvenzbekanntmachungen,\n"
            f"ZVG-Portal und EU AI Act Compliance-Daten.\n\n"
            f"Was Sie erhalten:\n"
            f"• Insolvenz-Risiko-Score (0–100)\n"
            f"• ZVG / Zwangsversteigerungs-Risiko\n"
            f"• EU AI Act Compliance-Status\n"
            f"• Gewichteter Gesamt-Score + Kreditempfehlung\n"
            f"• Vollständige Event-Timeline\n\n"
            f"Einzel-Report:          €499\n"
            f"Marktwatch-Abo (50 Firmen tägl.): €1.999/Monat\n"
            f"Enterprise API:         €4.999/Monat\n\n"
            f"Interesse? Antworten Sie auf diese Email oder buchen Sie direkt:\n"
            f"{_dashboard_url()}/intelligence\n\n"
            f"Mit freundlichen Grüßen,\n"
            f"SuperMegaBot Intelligence Broker\n"
            f"AiiteC · ineedit.com.co"
        )

        html = f"""
        <div style="background:#0d0d1a;color:#e0e0f0;padding:28px;font-family:sans-serif;max-width:600px;">
          <h2 style="color:#7c83ff;margin-bottom:8px;">⚡ SuperMegaBot Intelligence Broker</h2>
          <hr style="border-color:#1e1e42;margin-bottom:20px;">
          <p style="color:#9e9ec8;">{intro}</p>
          <p style="margin-top:16px;">Wir haben soeben ein vollständiges Unternehmens-Risikoprofil für
            <strong style="color:#e8eaf6;">{firma}</strong> erstellt.</p>
          <div style="background:#12122a;border:1px solid #1e1e42;border-radius:10px;padding:18px;margin:20px 0;">
            <p style="color:#7c83ff;font-size:0.75rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Enthaltene Daten</p>
            <ul style="list-style:none;color:#e0e0f0;line-height:2;">
              <li>✅ Insolvenz-Risiko-Score (0–100)</li>
              <li>✅ ZVG / Zwangsversteigerungs-Risiko</li>
              <li>✅ EU AI Act Compliance-Status</li>
              <li>✅ Gewichteter Gesamt-Score + Kreditempfehlung</li>
              <li>✅ Vollständige Event-Timeline</li>
            </ul>
          </div>
          <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <tr style="background:#12122a;">
              <td style="padding:12px;color:#9e9ec8;">Einzel-Report</td>
              <td style="padding:12px;font-weight:700;color:#66bb6a;">€499</td>
            </tr>
            <tr>
              <td style="padding:12px;color:#9e9ec8;">Marktwatch-Abo (50 Firmen/tägl.)</td>
              <td style="padding:12px;font-weight:700;color:#ffa726;">€1.999 / Monat</td>
            </tr>
            <tr style="background:#12122a;">
              <td style="padding:12px;color:#9e9ec8;">Enterprise API</td>
              <td style="padding:12px;font-weight:700;color:#7c83ff;">€4.999 / Monat</td>
            </tr>
          </table>
          <a href="{_dashboard_url()}/intelligence"
             style="display:inline-block;background:#7c83ff;color:white;padding:12px 28px;
                    border-radius:8px;text-decoration:none;font-weight:700;margin-top:8px;">
            Jetzt Report anfragen
          </a>
          <p style="color:#3d3d60;font-size:0.78rem;margin-top:24px;">
            SuperMegaBot Intelligence Broker · AiiteC · ineedit.com.co<br>
            Abmelden: Antworten Sie mit "Abmelden"
          </p>
        </div>"""

        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            await asyncio.to_thread(self._smtp_send, user, pw, target["email"], msg)
            log.info("Outreach Email gesendet: %s → %s", firma, target["email"])
            return True
        except Exception as exc:
            log.error("Outreach-Email fehlgeschlagen (%s): %s", target["email"], exc)
            return False

    # ── Haupt-Run ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Daemon-Modus: Läuft täglich um 09:30 Uhr.
        - Watchlist-Check
        - B2B Outreach
        """
        log.info("Intelligence Broker Daemon gestartet.")
        while True:
            now = datetime.now()
            if now.hour == 9 and now.minute == 30:
                log.info("Täglicher Run: 09:30 Uhr")
                alerts = await self.check_watchlist()
                sent   = await self.daily_outreach()
                await self._send_telegram_summary(len(alerts), sent)
                await asyncio.sleep(61)   # verhindert Doppel-Run in derselben Minute
            else:
                # Nächsten Run berechnen und schlafen
                next_run = now.replace(hour=9, minute=30, second=0, microsecond=0)
                if now >= next_run:
                    from datetime import timedelta
                    next_run += timedelta(days=1)
                sleep_sec = (next_run - now).total_seconds()
                log.info("Nächster Run in %.0f Minuten (09:30 Uhr)", sleep_sec / 60)
                await asyncio.sleep(min(sleep_sec, 3600))

    async def _send_telegram_summary(self, alerts: int, outreach_sent: int) -> None:
        token = _tg_token()
        chat  = _tg_chat()
        if not token or not chat:
            return
        text = (
            f"📊 *Intelligence Broker — Tages-Report*\n\n"
            f"Watchlist-Alerts: *{alerts}*\n"
            f"Outreach-Emails:  *{outreach_sent}*\n\n"
            f"Dashboard: {_dashboard_url()}/intelligence"
        )
        try:
            session = await self._get_session()
            await session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as exc:
            log.warning("Telegram-Summary fehlgeschlagen: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

async def _cli() -> None:
    broker = IntelligenceBroker()
    try:
        args = sys.argv[1:]

        if not args:
            # Daemon-Modus
            await broker.run()

        elif args[0] == "--now":
            log.info("Sofort-Run gestartet...")
            alerts = await broker.check_watchlist()
            sent   = await broker.daily_outreach()
            print(f"\nWatchlist-Alerts: {len(alerts)}")
            print(f"Outreach-Emails gesendet: {sent}")

        elif args[0] == "--report" and len(args) >= 2:
            firma = " ".join(args[1:])
            log.info("Sofort-Report für: %s", firma)
            profile = await broker.aggregate_company_data(firma)
            out_path = _BASE / "data" / f"report_{firma.replace(' ', '_')[:50]}.html"
            out_path.write_text(profile.report_html, encoding="utf-8")
            print(f"\n--- Risikoprofil: {firma} ---")
            print(f"Insolvenz-Score:  {profile.insolvenz_score}")
            print(f"ZVG-Score:        {profile.zvg_score}")
            print(f"AI Act Risiko:    {profile.ai_act_risk}")
            print(f"Gesamt-Score:     {profile.overall_risk_score}")
            print(f"Empfehlung:       {profile.recommendation}")
            print(f"Events gefunden:  {len(profile.events)}")
            print(f"Report gespeichert: {out_path}")

        elif args[0] == "--watch" and len(args) >= 3:
            firma = args[1]
            email = args[2]
            ok = await broker.add_to_watchlist(firma, email)
            if ok:
                print(f"Watchlist: {firma} ({email}) hinzugefügt.")
            else:
                print("Fehler beim Hinzufügen zur Watchlist.")

        else:
            print("Verwendung:")
            print("  python3 intelligence_broker.py                        # Daemon")
            print("  python3 intelligence_broker.py --now                  # Sofort-Run")
            print("  python3 intelligence_broker.py --report FIRMA         # Sofort-Report")
            print("  python3 intelligence_broker.py --watch FIRMA EMAIL    # Watchlist")
    finally:
        await broker.close()


if __name__ == "__main__":
    asyncio.run(_cli())
