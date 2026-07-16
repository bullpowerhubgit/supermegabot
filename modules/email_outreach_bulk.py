#!/usr/bin/env python3
"""
SYS-10: Bulk Email Outreach — 1000 Multiplier-Firmen
=====================================================
Ziel: Berater, Agenturen, Kanzleien, Verbände als RESELLER gewinnen.
Strategie: 1 Partner = 10-100 Endkunden — kein eigener Traffic-Aufbau.

Täglich 100 personalisierte Kalt-Emails an Multiplikatoren:
  - Marketing-/Web-/SEO-Agenturen
  - Unternehmensberater & IT-Beratungen
  - Steuerberater & Anwaltskanzleien
  - Handwerker-Verbände & Innungen
  - Immobilien-Netzwerke
  - E-Commerce-Dienstleister

Pitch: "Bieten Sie Ihren Kunden KI-Services an — 30% Provision, null Aufwand."

Starten:
  python3 modules/email_outreach_bulk.py

Hintergrund:
  nohup python3 modules/email_outreach_bulk.py > /tmp/bulk_outreach.log 2>&1 &
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BULK-OUTREACH] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("BulkOutreach")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "bulk_outreach.db"

# ── Env ───────────────────────────────────────────────────────────────────────

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

# 7 Gmail-Konten rotieren — mehr Volumen, bessere Zustellrate
_GMAIL_ACCOUNTS = [
    {"user": os.getenv("GMAIL_USER_5", "aiitecbuuss@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_5", "rqcd uzim npsl odgw"),
     "name": "Rudolf Sarkany | AIITEC"},
    {"user": os.getenv("GMAIL_USER_1", "dragonadnp@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_1", ""),
     "name": "AIITEC KI-Services"},
    {"user": os.getenv("GMAIL_USER_3", "bullpowersrtkennels@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_3", ""),
     "name": "AIITEC Partnerservice"},
    {"user": os.getenv("GMAIL_USER_7", "rudolf.sarkany.aiitec@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_7", ""),
     "name": "Rudolf Sarkany | AIITEC"},
]

def _anthropic_key() -> str: return os.getenv("ANTHROPIC_API_KEY", "")
def _tg_token()      -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "")
def _tg_chat()       -> str: return os.getenv("TELEGRAM_CHAT_ID", "")

# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def mark_bounced(email_addr: str) -> bool:
    """Markiert eine E-Mail-Adresse als gebounced — wird nie mehr kontaktiert."""
    import time
    try:
        with _db() as c:
            c.execute(
                "UPDATE bo_companies SET bounced=1, bounced_at=? WHERE email=?",
                (int(time.time()), email_addr.lower().strip()),
            )
            c.execute(
                "UPDATE bo_outreach SET status='bounced' WHERE email=?",
                (email_addr.lower().strip(),),
            )
        log.info("Bounce markiert: %s", email_addr)
        return True
    except Exception as e:
        log.warning("mark_bounced Fehler: %s", e)
        return False


def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS bo_companies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            domain      TEXT,
            segment     TEXT,
            service_fit TEXT,
            city        TEXT,
            source      TEXT DEFAULT 'seed',
            added_at    INTEGER,
            bounced     INTEGER DEFAULT 0,
            bounced_at  INTEGER
        );
        -- Migration: Spalte nachrüsten falls DB älter
        CREATE TABLE IF NOT EXISTS _migrations (key TEXT PRIMARY KEY);


        CREATE TABLE IF NOT EXISTS bo_outreach (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id   INTEGER REFERENCES bo_companies(id),
            email        TEXT NOT NULL,
            subject      TEXT,
            sender_acct  TEXT,
            status       TEXT DEFAULT 'pending',
            sent_at      INTEGER,
            opened_at    INTEGER,
            replied_at   INTEGER,
            error_msg    TEXT,
            follow_up_due INTEGER,
            UNIQUE(email, subject)
        );

        CREATE TABLE IF NOT EXISTS bo_partners (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id   INTEGER REFERENCES bo_companies(id),
            email        TEXT UNIQUE NOT NULL,
            status       TEXT DEFAULT 'interested',
            commission_pct REAL DEFAULT 30.0,
            onboarded_at INTEGER,
            total_referrals INTEGER DEFAULT 0,
            total_earned REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS bo_run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at      INTEGER,
            emails_sent INTEGER DEFAULT 0,
            errors      INTEGER DEFAULT 0,
            new_partners INTEGER DEFAULT 0,
            duration_s  REAL
        );
        """)

# ── 1000 Multiplier-Firmen (Seed-Datenbank) ────────────────────────────────

MULTIPLIER_SEED: List[Dict] = [
    # ── Marketing-Agenturen (resellen Product Texts + Social Media KI) ────────
    {"name": "Hutter Consult AG",               "email": "info@hutter-consult.ch",        "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender,shopify_texte"},
    {"name": "Elbdudler GmbH",                  "email": "hello@elbdudler.de",             "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender,shopify_texte"},
    {"name": "Zum goldenen Hirschen",            "email": "kontakt@zumgoldenenhirschen.de", "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Serviceplan Group",                "email": "info@serviceplan.com",           "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender,shopify_texte"},
    {"name": "Jung von Matt",                    "email": "info@jvm.com",                   "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Pilot Media",                      "email": "info@pilot.de",                  "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Wunderman Thompson DE",            "email": "info@wtgermany.com",             "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Crispy Content",                   "email": "hello@crispy-content.com",       "segment": "Marketing-Agentur",      "service_fit": "shopify_texte,social_media_kalender"},
    {"name": "Weischer Network",                 "email": "info@weischer.media",            "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Media Impact",                     "email": "info@media-impact.de",           "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    # ── SEO-/Web-Agenturen (resellen Product Texts + eBay/Amazon Listings) ───
    {"name": "Searchmetrics GmbH",              "email": "contact@searchmetrics.com",       "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Sistrix GmbH",                    "email": "info@sistrix.de",                 "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Coretelligence",                  "email": "info@coretelligence.de",          "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "eMinded GmbH",                    "email": "info@eminded.com",                "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Explido iProspect",               "email": "info@explido.de",                 "segment": "SEO-Agentur",            "service_fit": "shopify_texte"},
    {"name": "Smarketer GmbH",                  "email": "info@smarketer.de",               "segment": "SEO-Agentur",            "service_fit": "shopify_texte,social_media_kalender"},
    {"name": "Digital Media GmbH",              "email": "info@digital-media.de",           "segment": "SEO-Agentur",            "service_fit": "shopify_texte"},
    {"name": "Clicks Digital",                  "email": "info@clicks.de",                  "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Projecter GmbH",                  "email": "hallo@projecter.de",              "segment": "SEO-Agentur",            "service_fit": "shopify_texte,social_media_kalender"},
    {"name": "Suchhelden GmbH",                 "email": "info@suchhelden.de",              "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    # ── Unternehmensberater (resellen EU AI Act + Vertragscheck) ─────────────
    {"name": "Roland Berger GmbH",              "email": "info@rolandberger.com",           "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Staufen AG",                      "email": "info@staufen.ag",                 "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "zeb Beratung",                    "email": "info@zeb.de",                     "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Crisp Research AG",               "email": "info@crisp-research.com",         "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act"},
    {"name": "BearingPoint GmbH",               "email": "info@bearingpoint.com",           "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Kienbaum Consultants",            "email": "info@kienbaum.com",               "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Sopra Steria DE",                 "email": "info@soprasteria.de",             "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act"},
    {"name": "Detecon International",           "email": "info@detecon.com",                "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Capgemini Invent DE",             "email": "invent@capgemini.com",            "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act"},
    {"name": "MHP Management",                  "email": "info@mhp.com",                    "segment": "Unternehmensberatung",   "service_fit": "eu_ai_act,vertragscheck"},
    # ── IT-Beratungen (resellen EU AI Act Compliance) ─────────────────────────
    {"name": "iteratec GmbH",                   "email": "info@iteratec.de",                "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "msg systems ag",                  "email": "info@msg.group",                  "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Adesso SE",                       "email": "info@adesso.de",                  "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Materna SE",                      "email": "info@materna.de",                 "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Atos IT Solutions DE",            "email": "info@atos.net",                   "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "CGI Deutschland",                 "email": "info@cgi.com",                    "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Computacenter DE",                "email": "info@computacenter.com",          "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Nagarro SE",                      "email": "info@nagarro.com",                "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "PRODYNA SE",                      "email": "info@prodyna.com",                "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    {"name": "Accenture DE",                    "email": "info@accenture.de",               "segment": "IT-Beratung",            "service_fit": "eu_ai_act"},
    # ── Steuerberater-Ketten (resellen Rechtstexte + Vertragscheck) ───────────
    {"name": "ETL Unternehmensgruppe",          "email": "info@etl.de",                     "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "DHPG GmbH",                       "email": "info@dhpg.de",                    "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "Ebner Stolz GmbH",                "email": "info@ebnerstolz.de",              "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "Deloitte Tax DE",                 "email": "deloitte@deloitte.de",            "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "BDO AG",                          "email": "info@bdo.de",                     "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "Rödl & Partner",                  "email": "nuernberg@roedl.com",             "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "Warth & Klein Grant Thornton",    "email": "info@wkgt.com",                   "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "Taxgate GmbH",                    "email": "info@taxgate.de",                 "segment": "Steuerberatung",         "service_fit": "rechtstexte"},
    {"name": "Peters Schönberger & Partner",    "email": "info@psp.eu",                     "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    {"name": "TPA Steuerberatung GmbH",         "email": "info@tpa-group.de",               "segment": "Steuerberatung",         "service_fit": "rechtstexte,vertragscheck"},
    # ── Anwaltskanzleien (EU AI Act + Vertragscheck als Effizienz-Tool) ───────
    {"name": "Linklaters LLP Deutschland",      "email": "info.germany@linklaters.com",     "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Freshfields DE",                  "email": "info@freshfields.com",            "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Gleiss Lutz",                     "email": "info@gleisslutz.com",             "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Noerr LLP",                       "email": "info@noerr.com",                  "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "CMS Hasche Sigle",                "email": "info@cms-hs.com",                 "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Hengeler Mueller",                "email": "info@hengeler.com",               "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Bird & Bird DE",                  "email": "info@twobirds.com",               "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act"},
    {"name": "Fieldfisher Germany",             "email": "germany@fieldfisher.com",         "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act,vertragscheck"},
    {"name": "Taylor Wessing DE",               "email": "info@taylorwessing.com",          "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act"},
    {"name": "DLA Piper Germany",               "email": "info@dlapiper.com",               "segment": "Anwaltskanzlei",         "service_fit": "eu_ai_act"},
    # ── Handwerker-Verbände und Innungen (Angebots-KI für Mitglieder) ─────────
    {"name": "Zentralverband SHK",             "email": "info@zvshk.de",                   "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "ZVEH Elektro",                    "email": "info@zveh.de",                    "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "Zentralverband Dachdecker",       "email": "info@dachdecker.de",              "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "Bundesverband Farbe",             "email": "info@farbe.de",                   "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "ZDH Zentralverband Handwerk",     "email": "info@zdh.de",                     "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "HWK München-Oberbayern",          "email": "info@hwk-muenchen.de",            "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "HWK Düsseldorf",                  "email": "info@hwk-duesseldorf.de",         "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "HWK Köln",                        "email": "info@hwk-koeln.de",               "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "HWK Hamburg",                     "email": "info@hwk-hamburg.de",             "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    {"name": "HWK Berlin",                      "email": "info@hwk-berlin.de",              "segment": "Handwerk-Verband",       "service_fit": "angebots_ki"},
    # ── Immobilien-Netzwerke (Exposé-KI für Mitglieds-Makler) ────────────────
    {"name": "IVD Immobilienverband",           "email": "info@ivd.net",                    "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "RDM Ring Deutscher Makler",       "email": "info@rdm.de",                     "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "RE/MAX Deutschland",              "email": "info@remax.de",                   "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "Engel & Völkers AG",              "email": "presse@engelvoelkers.com",        "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "VON POLL IMMOBILIEN",             "email": "info@von-poll.com",               "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "DAHLER & COMPANY",                "email": "info@dahlercompany.com",          "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "Sparkassen-Immobilien",           "email": "info@sparkassen-immobilien.de",   "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "PlanetHome AG",                   "email": "info@planethome.com",             "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "BUWOG Group GmbH",                "email": "info@buwog.com",                  "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    {"name": "Immonet GmbH",                    "email": "info@immonet.de",                 "segment": "Immobilien-Netzwerk",    "service_fit": "expose_ki"},
    # ── E-Commerce-Dienstleister (Amazon/eBay Listings für Shop-Kunden) ───────
    {"name": "ChannelAdvisor DE",               "email": "info@channeladvisor.com",         "segment": "E-Commerce-Service",     "service_fit": "amazon_listings,shopify_texte"},
    {"name": "basecom GmbH",                    "email": "info@basecom.de",                 "segment": "E-Commerce-Service",     "service_fit": "amazon_listings,shopify_texte"},
    {"name": "diva-e Digital Value",            "email": "info@diva-e.com",                 "segment": "E-Commerce-Service",     "service_fit": "amazon_listings,shopify_texte"},
    {"name": "Webwirkung GmbH",                 "email": "info@webwirkung.de",              "segment": "E-Commerce-Service",     "service_fit": "shopify_texte,amazon_listings"},
    {"name": "NETFORMIC GmbH",                  "email": "info@netformic.de",               "segment": "E-Commerce-Service",     "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Blackbit digital Commerce",       "email": "info@blackbit.de",                "segment": "E-Commerce-Service",     "service_fit": "shopify_texte"},
    {"name": "Claranet DE",                     "email": "info@claranet.de",                "segment": "E-Commerce-Service",     "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Ueberall GmbH",                   "email": "info@uberall.com",                "segment": "E-Commerce-Service",     "service_fit": "amazon_listings,shopify_texte"},
    {"name": "Afterbuy GmbH",                   "email": "info@afterbuy.de",                "segment": "E-Commerce-Service",     "service_fit": "amazon_listings"},
    {"name": "JTL-Software GmbH",               "email": "info@jtl-software.de",            "segment": "E-Commerce-Service",     "service_fit": "amazon_listings,shopify_texte"},
    # ── Franchise-Systeme (Paket-Reseller für alle Franchisees) ─────────────
    {"name": "Deutsches Franchiseinstitut",     "email": "info@franchiseinstitut.de",       "segment": "Franchise-System",       "service_fit": "social_media_kalender,rechtstexte"},
    {"name": "Franchise Portal Germany",        "email": "info@franchiseportal.de",         "segment": "Franchise-System",       "service_fit": "social_media_kalender,rechtstexte"},
    {"name": "European Franchise Federation",   "email": "eff@eff-franchise.com",           "segment": "Franchise-System",       "service_fit": "social_media_kalender,rechtstexte"},
    {"name": "Deutsches Franchise-Institut",    "email": "info@dfi.de",                     "segment": "Franchise-System",       "service_fit": "social_media_kalender"},
    {"name": "McArthurGlen DE",                 "email": "info@mcarthurglen.com",           "segment": "Franchise-System",       "service_fit": "social_media_kalender"},
    # ── Unternehmensverbände / IHK-Netzwerke ─────────────────────────────────
    {"name": "BVMW Bundesverband KMU",         "email": "info@bvmw.de",                    "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte,angebots_ki"},
    {"name": "DIHK Berlin",                     "email": "info@dihk.de",                    "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte"},
    {"name": "IHK München",                     "email": "info@muenchen.ihk.de",            "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte"},
    {"name": "IHK Frankfurt",                   "email": "info@frankfurt-main.ihk.de",      "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte"},
    {"name": "IHK Hamburg",                     "email": "info@hamburg.ihk.de",             "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte"},
    {"name": "BDI Bundesverband Industrie",     "email": "info@bdi.eu",                     "segment": "Unternehmensverband",    "service_fit": "eu_ai_act"},
    {"name": "Startup Germany Foundation",      "email": "info@startupgermany.de",          "segment": "Unternehmensverband",    "service_fit": "eu_ai_act,rechtstexte"},
    {"name": "Digital Hub Initiative DE",       "email": "info@de-hub.de",                  "segment": "Unternehmensverband",    "service_fit": "eu_ai_act"},
    # ── Regionale Marketing-Netzwerke / Agenturen ─────────────────────────────
    {"name": "Löwenstark Digital Group",        "email": "info@loewenstark.com",            "segment": "Marketing-Agentur",      "service_fit": "shopify_texte,social_media_kalender"},
    {"name": "Claneo GmbH",                     "email": "info@claneo.com",                 "segment": "SEO-Agentur",            "service_fit": "shopify_texte,amazon_listings"},
    {"name": "Seokratie GmbH",                  "email": "info@seokratie.de",               "segment": "SEO-Agentur",            "service_fit": "shopify_texte"},
    {"name": "Online-Marketing.de GmbH",        "email": "info@online-marketing.de",        "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender,shopify_texte"},
    {"name": "Catbird Seat GmbH",               "email": "info@catbirdseat.de",             "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Kombo GmbH",                      "email": "hi@kombo.de",                     "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Torben, Lucie und die gelbe Gefahr", "email": "kontakt@tlgg.de",              "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Pulse Advertising",               "email": "info@pulseadvertising.com",       "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "The Social Chain DE",             "email": "hello@socialchain.com",           "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender"},
    {"name": "Faktor 3 AG",                     "email": "info@faktor3.de",                 "segment": "Marketing-Agentur",      "service_fit": "social_media_kalender,shopify_texte"},
]

# Weitere 900 Einträge werden durch den Web-Scraper ergänzt (bo_companies-Tabelle)
# Initiale Seed → Datenbank füllen

# ── Email-Templates (Multiplikatoren-Pitch) ───────────────────────────────────

SERVICE_PAGES = {
    "eu_ai_act":            "https://dist-pi-jet-78.vercel.app/#sys3",
    "vertragscheck":        "https://cognitive-symphony-bullpowerhubgits-projects.vercel.app",
    "rechtstexte":          "https://steuercockpit-bullpowerhubgits-projects.vercel.app",
    "angebots_ki":          "https://hospital-wage-calculator-kpeb-bullpowerhubgits-projects.vercel.app",
    "shopify_texte":        "https://monetization-hub-bullpowerhubgits-projects.vercel.app",
    "amazon_listings":      "https://etsy-gumroad-bullpowerhubgits-projects.vercel.app",
    "expose_ki":            "https://digifabrik-bullpowerhubgits-projects.vercel.app",
    "social_media_kalender": "https://desktop-tutorial-bullpowerhubgits-projects.vercel.app",
    "linkedin_optimierung": "https://gistore-bullpowerhubgits-projects.vercel.app",
}

SERVICE_LABELS = {
    "eu_ai_act":            "EU AI Act Risiko-Radar (ab €299/Report)",
    "vertragscheck":        "KI-Vertragscheck (ab €129/Vertrag)",
    "rechtstexte":          "Rechtstexte KI (€49 Impressum+AGB+Datenschutz)",
    "angebots_ki":          "Handwerker Angebots-KI (30 Angebote für €79)",
    "shopify_texte":        "Shopify KI-Produktbeschreibungen (50 Stück für €79)",
    "amazon_listings":      "eBay & Amazon Listing-KI (100 Listings für €99)",
    "expose_ki":            "Makler Exposé-KI (15 Exposés für €199)",
    "social_media_kalender": "Social Media KI-Kalender (30 Posts/Monat für €69)",
}

PARTNER_CTA = "https://dist-pi-jet-78.vercel.app"

TEMPLATES: Dict[str, Dict] = {
    "Marketing-Agentur": {
        "subject": "KI-Content für Ihre Kunden — 30% Provision, null Aufwand",
        "body": """\
Guten Tag,

ich schreibe Ihnen mit einem konkreten Angebot, das für Ihre Agentur-Kunden sofort Mehrwert schafft.

Wir haben KI-gestützte Content-Services entwickelt, die Ihre Kunden nachfragen werden:
{service_list}

Das Modell: Sie vermitteln uns Ihre Kunden — wir liefern, Sie erhalten 30% Provision auf jeden Auftrag. Keine Integration, kein eigenes Team, keine Technik von Ihrer Seite.

Gerade Ihre Kunden mit E-Commerce-Anteil und Social-Media-Bedarf profitieren sofort.

Haben Sie 15 Minuten für ein kurzes Gespräch diese Woche?

Mehr dazu: {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com

--
Abmeldung: Antworten Sie mit "Abmelden" — wir streichen Sie sofort aus unserem Verteiler.""",
    },
    "SEO-Agentur": {
        "subject": "Produkttexte & Amazon-Listings für Ihre Shop-Kunden — Reseller-Modell",
        "body": """\
Hallo,

als SEO-Agentur kennen Sie das Problem Ihrer Kunden: fehlende, schlechte oder nicht skalierbare Produkttexte.

Wir haben genau das gelöst — KI-Services die Sie Ihren Shop-Kunden anbieten können:
{service_list}

Das Reseller-Modell: Ihre Kunden buchen über Sie, wir liefern in 24-48h, Sie erhalten 30% Provision. Keine Nacharbeit für Sie.

Interesse? Oder Fragen zum Modell?

Details: {cta_url}

Beste Grüße,
Rudolf Sarkany | AIITEC

--
Keine weiteren Emails gewünscht? Antworten Sie mit "Stop".""",
    },
    "Unternehmensberatung": {
        "subject": "EU AI Act: Service für Ihre Beratungskunden — wir liefern, Sie empfehlen",
        "body": """\
Sehr geehrte Damen und Herren,

seit August 2026 gilt der EU AI Act vollständig. Viele Ihrer Mandanten sind betroffen — und suchen Unterstützung.

Wir bieten:
{service_list}

Ihr Vorteil als Beratungspartner: Sie empfehlen unseren Service an Klienten, wir übernehmen die Lieferung. Für Sie 30% auf jeden Umsatz — ohne eigene Kapazität.

Für IT- und Compliance-Beratungen ist das eine natürliche Ergänzung zum bestehenden Portfolio.

Gerne stellen wir das Modell in einem kurzen Call vor.

{cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Abmeldung jederzeit durch Antwort auf diese E-Mail.""",
    },
    "IT-Beratung": {
        "subject": "EU AI Act Compliance-Tool — für Ihre Kunden, 30% Provision",
        "body": """\
Guten Tag,

Ihre IT-Beratungskunden werden in den nächsten Monaten EU AI Act Compliance-Bedarf haben. Wir haben das Produkt dafür.

{service_list}

Als IT-Berater können Sie diesen Service nahtlos in Ihre Projektleistungen integrieren — wir liefern, Sie empfehlen und erhalten 30% Provision.

Details zum Partner-Programm: {cta_url}

Grüße,
Rudolf Sarkany | AIITEC

--
Nicht interessiert? Einfach antworten — wir kontaktieren Sie nicht wieder.""",
    },
    "Steuerberatung": {
        "subject": "Rechtstexte & Vertragscheck für Ihre Mandanten — Empfehlung lohnt sich",
        "body": """\
Sehr geehrte Damen und Herren,

viele Ihrer Mandanten benötigen Impressum, AGB und Datenschutzerklärung — und fragen Sie als Berater um Rat.

Wir haben einen schlanken Service dafür:
{service_list}

Modell: Sie empfehlen uns weiter — Ihre Mandanten bekommen professionelle Rechtstexte für €49, Sie erhalten 30% Provision (€14,70 je Empfehlung). Null Aufwand für Sie.

Mehr Info: {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Abmeldung: Antwort mit "Abmelden" genügt.""",
    },
    "Anwaltskanzlei": {
        "subject": "KI-Vertragsanalyse als Effizienz-Tool — Kooperation anfragen",
        "body": """\
Sehr geehrte Damen und Herren,

wir bieten einen KI-gestützten Vertragscheck-Service für KMU-Kunden, die eine schnelle erste Einschätzung benötigen:

{service_list}

Das ist kein Ersatz für Ihre Rechtsberatung — sondern eine Vorstufe. Kunden die unseren €129-Check nutzen, kommen oft mit konkreten Fragen zu Ihnen.

Kooperationsmodell: Wir verweisen unsere Kunden bei komplexen Fragen an Partner-Kanzleien. Gegenseitige Empfehlung.

Interesse? {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Keine weiteren Emails: Kurze Antwort genügt.""",
    },
    "Handwerk-Verband": {
        "subject": "Angebotserstellung für Ihre Mitglieder — KI-Service zum Weiterempfehlen",
        "body": """\
Guten Tag,

als Verband wissen Sie: Angebotserstellung kostet Ihre Mitglieder Stunden pro Woche — Zeit die auf der Baustelle fehlt.

Unser Service löst das:
{service_list}

Viele Verbände empfehlen uns ihren Mitgliedern — als kostenloser Mehrwert für die Mitgliedschaft. Und erhalten 30% Provision auf jede Bestellung.

Mehr dazu: {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Keine weiteren Kontaktaufnahmen gewünscht? Antwort genügt.""",
    },
    "Immobilien-Netzwerk": {
        "subject": "Professionelle Exposés für Ihre Makler-Netzwerk — KI, 48h, €199",
        "body": """\
Guten Tag,

Exposés sind das Aushängeschild jedes Maklers. Viele schreiben sie selbst — und verlieren dabei wertvolle Zeit.

Unser KI-Service erstellt 15 professionelle Exposés in 48h für €199:
{service_list}

Als Netzwerk können Sie diesen Service Ihren angeschlossenen Maklern empfehlen — und erhalten 30% Provision. Keine Technik, keine Integration.

Details: {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Abmeldung: Antwort auf diese E-Mail.""",
    },
    "E-Commerce-Service": {
        "subject": "Amazon & eBay Listings für Ihre Shop-Kunden — skalierbar per KI",
        "body": """\
Hallo,

wenn Sie E-Commerce-Kunden betreuen, kennen Sie das Listing-Problem: entweder zu wenig, zu generisch oder zu teuer.

Unsere KI liefert 100 individuelle Listings in 48h für €99:
{service_list}

Reseller-Modell: Sie vermitteln, wir liefern, Sie erhalten 30% Provision. White-Label auf Anfrage.

{cta_url}

Grüße,
Rudolf Sarkany | AIITEC

--
Keine weiteren E-Mails: kurz antworten.""",
    },
    "Unternehmensverband": {
        "subject": "KI-Services für Ihre Mitglieder — Empfehlung + 30% Provision",
        "body": """\
Sehr geehrte Damen und Herren,

als Verband haben Sie direkten Zugang zu Hunderten von Unternehmen, die KI-Services suchen aber nicht selbst entwickeln können.

Wir bieten ein Komplettpaket das Sie einfach weiterempfehlen:
{service_list}

Ihr Vorteil: 30% Provision auf jeden Auftrag — und ein konkreter Mehrwert für Ihre Mitglieder.

{cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Nicht interessiert? Kurze Rückmeldung — wir melden uns nicht wieder.""",
    },
    "Franchise-System": {
        "subject": "KI-Paketlösung für alle Ihre Franchisees — ein Vertrag, alle profitieren",
        "body": """\
Hallo,

als Franchise-System haben Sie eine einmalige Möglichkeit: einen KI-Service einmalig einzuführen und für alle Franchisees bereitzustellen.

{service_list}

Rahmenvertrag-Modell: Ein Vertrag mit uns, alle Franchisees profitieren zu Vorzugspreisen, Sie erhalten Provision auf alle Bestellungen.

Gespräch diese Woche? {cta_url}

Grüße,
Rudolf Sarkany | AIITEC

--
Abmeldung per Antwort-E-Mail.""",
    },
    "default": {
        "subject": "KI-Services als Zusatzeinnahme — 30% Provision, null Eigenaufwand",
        "body": """\
Guten Tag,

ich schreibe Ihnen wegen eines einfachen Reseller-Modells: Sie empfehlen unsere KI-Services an Ihre Kunden, wir liefern, Sie erhalten 30% Provision.

Unsere Services:
{service_list}

Kein eigener Technik-Aufwand, keine Entwicklung, keine Kundensupport-Last — das übernehmen wir.

Mehr: {cta_url}

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC

--
Abmeldung: Antwort mit "Stop" genügt.""",
    },
}

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _personalized_opener(company_name: str, segment: str) -> str:
    """Generiert eine KI-personalisierte Eröffnungszeile via ai_complete()."""
    try:
        from modules.ai_client import ai_complete
        prompt = (
            f"Schreibe EINE kurze (max. 20 Wörter) deutsche Begrüßungszeile für eine "
            f"B2B-Kalt-Email an '{company_name}' ({segment}). "
            f"Sehr spezifisch auf ihre Branche. Kein 'Ich schreibe Ihnen wegen', direkt starten. "
            f"Antworte NUR mit der Zeile, kein JSON, keine Anführungszeichen."
        )
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(ai_complete(prompt, max_tokens=60, model_hint="fast"))
            return result.strip().strip('"').strip("'")
        finally:
            loop.close()
    except Exception:
        return ""


def _build_email_body(company: dict) -> Tuple[str, str]:
    segment = company.get("segment", "default")
    template = TEMPLATES.get(segment, TEMPLATES["default"])

    service_fits = company.get("service_fit", "").split(",")
    service_lines = []
    for sf in service_fits:
        sf = sf.strip()
        if sf in SERVICE_LABELS:
            url = SERVICE_PAGES.get(sf, PARTNER_CTA)
            service_lines.append(f"  • {SERVICE_LABELS[sf]}\n    → {url}")

    if not service_lines:
        for k, v in list(SERVICE_LABELS.items())[:3]:
            service_lines.append(f"  • {v}")

    service_list = "\n".join(service_lines)

    subject = template["subject"]

    # KI-Opener für erste Zeile — macht Email persönlicher, erhöht Öffnungsrate
    opener = _personalized_opener(company.get("name", ""), segment)
    opener_line = f"{opener}\n\n" if opener else ""

    body = opener_line + template["body"].format(
        service_list=service_list,
        cta_url=PARTNER_CTA,
    )
    return subject, body


_OWN_EMAILS = {
    "aiitecbuuss@gmail.com", "bullpowersrtkennels@gmail.com",
    "dragonadnp@gmail.com", "rudolf.sarkany.aiitec@gmail.com",
    "rudolfsarkany1984@gmail.com", "nikolestimi@gmail.com", "looopwave@gmail.com",
}

_SKIP_PREFIXES = (
    "noreply@", "no-reply@", "no_reply@", "donotreply@", "do-not-reply@",
    "mailer-daemon@", "postmaster@", "bounce@", "bounces@", "notification@",
    "notifications@", "info-noreply@", "auto@", "automated@",
)

def _is_valid_recipient(addr: str) -> bool:
    a = addr.lower().strip()
    if not a or "@" not in a:
        return False
    local = a.split("@")[0]
    if any(a.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if local in ("noreply", "no-reply", "no_reply", "donotreply", "bounce",
                 "bounces", "postmaster", "mailer-daemon", "auto", "automated"):
        return False
    return True

def _send_email(sender_idx: int, to_email: str, subject: str, body: str) -> bool:
    if to_email.lower() in _OWN_EMAILS:
        log.warning(f"Eigene Adresse übersprungen: {to_email}")
        return False
    if not _is_valid_recipient(to_email):
        log.warning(f"Ungültige/Noreply-Adresse übersprungen: {to_email}")
        return False
    from modules.email_guard import require_valid_email, register_sent
    ok_g, errs = require_valid_email(subject, body, to_email)
    if not ok_g:
        log.warning("EmailGuard blockiert bulk [%s]: %s", to_email, errs)
        return False
    acct = _GMAIL_ACCOUNTS[sender_idx % len(_GMAIL_ACCOUNTS)]
    if not acct["pass"]:
        log.warning(f"Kein App-Passwort für {acct['user']} — überspringe")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{acct['name']} <{acct['user']}>"
        msg["To"]      = to_email
        msg["Reply-To"] = "aiitecbuuss@gmail.com"
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(acct["user"], acct["pass"])
            s.sendmail(acct["user"], to_email, msg.as_string())
        register_sent(to_email, subject, body)
        return True
    except Exception as e:
        log.error(f"SMTP Fehler an {to_email}: {e}")
        return False


async def _tg_notify(msg_text: str):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": chat, "text": msg_text, "parse_mode": "HTML"})
    except Exception as e:
        log.warning(f"Telegram Fehler: {e}")


def _seed_companies():
    now = int(time.time())
    inserted = 0
    with _db() as c:
        for co in MULTIPLIER_SEED:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO bo_companies
                        (name, email, domain, segment, service_fit, source, added_at)
                    VALUES (?, ?, ?, ?, ?, 'seed', ?)
                """, (
                    co["name"], co["email"],
                    co["email"].split("@")[-1] if "@" in co["email"] else "",
                    co.get("segment", ""),
                    co.get("service_fit", ""),
                    now,
                ))
                inserted += c.execute("SELECT changes()").fetchone()[0]
            except Exception as e:
                log.debug(f"Seed skip {co['email']}: {e}")
    log.info(f"Seed: {inserted} neue Firmen eingefügt")


async def scrape_more_companies(limit: int = 200):
    """Scrapt öffentliche Verzeichnisse für weitere Multiplikatoren."""
    search_terms = [
        ("Marketing Agentur Deutschland", "Marketing-Agentur", "social_media_kalender,shopify_texte"),
        ("SEO Agentur Deutschland", "SEO-Agentur", "shopify_texte,amazon_listings"),
        ("Unternehmensberatung Mittelstand", "Unternehmensberatung", "eu_ai_act,vertragscheck"),
        ("IT Beratung KMU Deutschland", "IT-Beratung", "eu_ai_act"),
        ("Steuerberatung Kanzlei", "Steuerberatung", "rechtstexte,vertragscheck"),
        ("Immobilienmakler Franchise", "Immobilien-Netzwerk", "expose_ki"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BulkOutreach/1.0)"}
    added = 0
    now = int(time.time())

    async with aiohttp.ClientSession(headers=headers) as session:
        for term, segment, service_fit in search_terms:
            if added >= limit:
                break
            try:
                url = f"https://www.wlw.de/de/suche?q={term.replace(' ', '+')}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        continue
                    html = await r.text()
                    emails = re.findall(r'[\w.\-]+@[\w.\-]+\.[a-z]{2,}', html)
                    domains = re.findall(r'href="https?://([\w.\-]+\.de)', html)
                    for domain in list(set(domains))[:20]:
                        email = f"info@{domain}"
                        if added >= limit:
                            break
                        try:
                            with _db() as c:
                                c.execute("""
                                    INSERT OR IGNORE INTO bo_companies
                                        (name, email, domain, segment, service_fit, source, added_at)
                                    VALUES (?, ?, ?, ?, ?, 'scraped', ?)
                                """, (domain, email, domain, segment, service_fit, now))
                                chg = c.execute("SELECT changes()").fetchone()[0]
                                if chg:
                                    added += 1
                        except Exception:
                            pass
                await asyncio.sleep(2)
            except Exception as e:
                log.warning(f"Scrape Fehler ({term}): {e}")

    log.info(f"Scraper: {added} neue Firmen ergänzt")
    return added


# ── Hauptlauf ─────────────────────────────────────────────────────────────────

async def run_outreach(daily_limit: int = 100) -> Dict:
    from modules.distributed_lock import acquire_lock
    async with acquire_lock("email_outreach_bulk", ttl=90 * 60) as locked:
        if not locked:
            log.info("Email Outreach läuft bereits in anderem Terminal — übersprungen")
            return {"sent": 0, "errors": 0, "skipped": True, "reason": "locked"}
        return await _run_outreach_inner(daily_limit)


async def _run_outreach_inner(daily_limit: int = 100) -> Dict:
    t0 = time.time()
    init_db()
    _seed_companies()

    now = int(time.time())
    sent = 0
    errors = 0
    sender_idx = 0

    # Migration: bounced-Spalte nachrüsten falls alte DB
    with _db() as c:
        try:
            c.execute("ALTER TABLE bo_companies ADD COLUMN bounced INTEGER DEFAULT 0")
            c.execute("ALTER TABLE bo_companies ADD COLUMN bounced_at INTEGER")
        except Exception:
            pass

    with _db() as c:
        companies = c.execute("""
            SELECT co.id, co.name, co.email, co.segment, co.service_fit
            FROM bo_companies co
            LEFT JOIN bo_outreach out ON out.email = co.email AND out.status IN ('sent','bounced')
            WHERE out.email IS NULL
              AND (co.bounced IS NULL OR co.bounced = 0)
            ORDER BY RANDOM()
            LIMIT ?
        """, (daily_limit,)).fetchall()

    log.info(f"{len(companies)} Firmen zur Kontaktaufnahme heute")

    for co in companies:
        if sent >= daily_limit:
            break

        subject, body = _build_email_body(dict(co))
        success = await asyncio.to_thread(_send_email, sender_idx, co["email"], subject, body)

        with _db() as c:
            c.execute("""
                INSERT OR IGNORE INTO bo_outreach
                    (company_id, email, subject, sender_acct, status, sent_at, follow_up_due)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                co["id"], co["email"], subject,
                _GMAIL_ACCOUNTS[sender_idx % len(_GMAIL_ACCOUNTS)]["user"],
                "sent" if success else "error",
                now if success else None,
                now + 7 * 86400 if success else None,
            ))

        if success:
            sent += 1
            log.info(f"✓ {co['name']} <{co['email']}> [{co['segment']}]")
        else:
            errors += 1
            log.warning(f"✗ {co['email']}")

        sender_idx += 1
        await asyncio.sleep(random.uniform(30, 90))  # Rate limiting

    duration = time.time() - t0
    with _db() as c:
        c.execute("INSERT INTO bo_run_log (ran_at, emails_sent, errors, duration_s) VALUES (?,?,?,?)",
                  (now, sent, errors, duration))

    report = (
        f"📧 <b>SYS-10 Bulk Outreach — Tagesbericht</b>\n"
        f"✅ Gesendet: {sent}\n"
        f"❌ Fehler: {errors}\n"
        f"⏱ Dauer: {duration:.0f}s\n"
        f"🎯 Ziel: Multiplikatoren → 30% Provision-Pitch\n"
        f"💡 Tipp: Antworten im Postfach aiitecbuuss@gmail.com prüfen!"
    )
    await _tg_notify(report)
    log.info(report.replace("<b>", "").replace("</b>", ""))
    return {"sent": sent, "errors": errors}


# ── Follow-Up (nach 7 Tagen ohne Antwort) ────────────────────────────────────

async def run_followup(daily_limit: int = 30) -> Dict:
    """
    Sendet AI-personalisierte Follow-Up Emails an Leads die nicht geantwortet haben.
    Nutzt email_followup_ai für KI-Content-Generierung und Reply-Detection.
    """
    from modules.ai_client import ai_complete
    from modules.email_followup_ai import generate_followup_email, unsubscribe_link

    now  = int(time.time())
    sent = 0

    with _db() as c:
        dues = c.execute("""
            SELECT out.id, out.email, co.name, co.segment, co.service_fit
            FROM bo_outreach out
            JOIN bo_companies co ON co.id = out.company_id
            WHERE out.status = 'sent'
            AND out.follow_up_due IS NOT NULL
            AND out.follow_up_due <= ?
            AND out.replied_at IS NULL
            LIMIT ?
        """, (now, daily_limit)).fetchall()

    for row in dues:
        email      = row["email"]
        company    = row["name"] or "Ihr Unternehmen"
        segment    = row["segment"] or "default"
        service_fit = row["service_fit"] or ""

        # KI-generierter Follow-Up (Step 1 = 7-Tage-Nachfasse)
        subject, body = await generate_followup_email(
            email=email,
            company=company,
            first_name="",          # kein Vorname in bulk_outreach
            segment=segment,
            service_fit=service_fit,
            step=1,
            tone="friendly",
            prior_sends=1,
        )

        success = await asyncio.to_thread(_send_email, sent % len(_GMAIL_ACCOUNTS), email, subject, body)
        if success:
            with _db() as c:
                c.execute("UPDATE bo_outreach SET status='followup_sent', follow_up_due=NULL WHERE id=?", (row["id"],))
            sent += 1
            log.info("Follow-Up (AI) gesendet → %s [%s]", email, segment)
        await asyncio.sleep(random.uniform(60, 120))

    log.info("Follow-Up: %d gesendet", sent)
    return {"followup_sent": sent}


# ── Standalone ────────────────────────────────────────────────────────────────

async def main():
    log.info("SYS-10: Bulk Outreach startet")
    init_db()
    _seed_companies()

    # Erst mehr Firmen scrapen
    log.info("Scrape öffentliche Verzeichnisse...")
    await scrape_more_companies(200)

    # Dann Outreach starten
    result = await run_outreach(daily_limit=100)
    log.info(f"Fertig: {result}")

    # Follow-Ups
    await run_followup(daily_limit=30)

    # Danach täglich um 09:00 Uhr wiederholen
    while True:
        now = datetime.now()
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run.replace(day=next_run.day + 1)
        wait_s = (next_run - now).total_seconds()
        log.info(f"Nächster Lauf in {wait_s/3600:.1f}h (09:00 Uhr)")
        await asyncio.sleep(wait_s)
        await run_outreach(daily_limit=100)
        await run_followup(daily_limit=30)


if __name__ == "__main__":
    asyncio.run(main())
