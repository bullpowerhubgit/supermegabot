#!/usr/bin/env python3
"""
Industrie-Outreach — Große Fabriken & Industrieunternehmen automatisch anschreiben
==================================================================================
Ziele: Mittelständische und große Produktionsunternehmen (100–5000 MA)
Pitch: KI-Automatisierung für Produktion, Einkauf, HR, Dokumentation

Läuft täglich 09:00 via Scheduler — 50 Unternehmen/Tag.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp

log = logging.getLogger("IndustrieOutreach")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "industrie_outreach.db"


def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_GMAIL_USER = lambda: os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
_GMAIL_PASS = lambda: os.getenv("GMAIL_APP_PASSWORD_AIITEC", "rqcd uzim npsl odgw")
_TG_TOKEN   = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT    = lambda: os.getenv("TELEGRAM_CHAT_ID", "")


# ── Ziel-Unternehmen: Große Fabriken & Industrie ──────────────────────────────

INDUSTRIE_TARGETS = [
    # Maschinenbau & Automatisierung
    {"name": "Maschinenfabrik Reinhausen GmbH",   "email": "info@reinhausen.com",      "branche": "Maschinenbau"},
    {"name": "Festo AG & Co. KG",                 "email": "info@festo.com",           "branche": "Automatisierung"},
    {"name": "Trumpf GmbH + Co. KG",              "email": "kontakt@trumpf.com",       "branche": "Laser/Maschinenbau"},
    {"name": "Krones AG",                          "email": "info@krones.com",          "branche": "Verpackungsmaschinen"},
    {"name": "Wacker Neuson SE",                   "email": "info@wackerneuson.com",    "branche": "Baumaschinen"},
    {"name": "STILL GmbH",                         "email": "info@still.de",            "branche": "Gabelstapler/Intralogistik"},
    {"name": "Linde Material Handling",            "email": "info@linde-mh.de",         "branche": "Intralogistik"},
    # Automobil-Zulieferer
    {"name": "ZF Friedrichshafen AG",             "email": "info@zf.com",              "branche": "Automobil-Zulieferer"},
    {"name": "Continental AG",                     "email": "presse@conti.de",          "branche": "Automobil-Zulieferer"},
    {"name": "Mahle GmbH",                         "email": "info@mahle.com",           "branche": "Automobil-Zulieferer"},
    {"name": "Brose Fahrzeugteile SE",             "email": "info@brose.com",           "branche": "Automobil-Zulieferer"},
    {"name": "Webasto Group",                      "email": "info@webasto.com",         "branche": "Automobil-Zulieferer"},
    # Chemie & Kunststoff
    {"name": "Evonik Industries AG",               "email": "info@evonik.com",          "branche": "Chemie"},
    {"name": "Wacker Chemie AG",                   "email": "info@wacker.com",          "branche": "Chemie"},
    {"name": "Lanxess AG",                         "email": "info@lanxess.com",         "branche": "Chemie"},
    {"name": "Covestro AG",                        "email": "info@covestro.com",        "branche": "Kunststoffe"},
    {"name": "BASF Polyurethanes GmbH",            "email": "info@basf.com",            "branche": "Chemie"},
    # Elektronik & Elektrotechnik
    {"name": "Phoenix Contact GmbH",               "email": "info@phoenixcontact.com",  "branche": "Elektrotechnik"},
    {"name": "Weidmüller Interface GmbH",          "email": "info@weidmueller.com",     "branche": "Elektrotechnik"},
    {"name": "Beckhoff Automation GmbH",           "email": "info@beckhoff.de",         "branche": "Automation"},
    {"name": "Pilz GmbH & Co. KG",                "email": "info@pilz.de",             "branche": "Sicherheitstechnik"},
    {"name": "Murrelektronik GmbH",                "email": "info@murrelektronik.de",   "branche": "Elektrotechnik"},
    {"name": "Pepperl+Fuchs AG",                   "email": "info@pepperl-fuchs.com",   "branche": "Sensorik"},
    # Stahl & Metall
    {"name": "Salzgitter AG",                      "email": "info@salzgitter-ag.de",    "branche": "Stahl"},
    {"name": "Klöckner & Co SE",                   "email": "info@kloeckner.com",       "branche": "Stahlhandel"},
    {"name": "Schuler AG",                         "email": "info@schulergroup.com",    "branche": "Umformtechnik"},
    {"name": "Gebr. Heller Maschinenfabrik",       "email": "info@heller.biz",          "branche": "Zerspanungsmaschinen"},
    # Logistik & Warehousing
    {"name": "Jungheinrich AG",                    "email": "info@jungheinrich.de",     "branche": "Lagerlogistik"},
    {"name": "Swisslog Holding AG",                "email": "info@swisslog.com",        "branche": "Intralogistik"},
    {"name": "Kardex Remstar GmbH",                "email": "info@kardex.com",          "branche": "Lagertechnik"},
    # Medizintechnik
    {"name": "B. Braun Melsungen AG",              "email": "info@bbraun.com",          "branche": "Medizintechnik"},
    {"name": "Drägerwerk AG & Co. KGaA",           "email": "info@draeger.com",         "branche": "Medizin/Sicherheit"},
    {"name": "Qiagen NV",                          "email": "info@qiagen.com",          "branche": "Biotech"},
    # Nahrungsmittelmaschinen
    {"name": "GEA Group AG",                       "email": "media@gea.com",            "branche": "Lebensmitteltechnik"},
    {"name": "Multivac Sepp Haggenmüller",         "email": "info@multivac.com",        "branche": "Verpackung"},
    {"name": "Haver & Boecker OHG",                "email": "info@haverboecker.com",    "branche": "Schüttguttechnik"},
    # Handwerk & Fertigung (Verbände)
    {"name": "Zentralverband Elektrotechnik-DE",   "email": "info@zvei.org",            "branche": "Verband"},
    {"name": "VDMA Verband DE",                    "email": "info@vdma.org",            "branche": "Maschinenverband"},
    {"name": "Bitkom e.V.",                        "email": "info@bitkom.org",          "branche": "IT-Verband"},
    {"name": "BDI - Bundesverband Industrie",      "email": "info@bdi.eu",              "branche": "Industrie-Verband"},
    # Mittelstand / Regional
    {"name": "Haas Schleifmaschinen GmbH",        "email": "info@haas-schleifmaschinen.de", "branche": "Schleiftechnik"},
    {"name": "Grob-Werke GmbH & Co. KG",          "email": "info@grob.de",             "branche": "Bearbeitungszentren"},
    {"name": "Liebherr-International AG",          "email": "info@liebherr.com",        "branche": "Krane/Maschinen"},
    {"name": "Claas KGaA mbH",                    "email": "info@claas.com",           "branche": "Landmaschinen"},
    {"name": "Amazonen-Werke H. Dreyer",           "email": "info@amazone.de",          "branche": "Landmaschinen"},
    {"name": "Kässbohrer Geländefahrzeug AG",      "email": "info@kaessbohrer.com",     "branche": "Spezialfahrzeuge"},
    {"name": "Hans Turck GmbH & Co. KG",          "email": "info@turck.de",            "branche": "Automatisierung"},
    {"name": "Datalogic Germany GmbH",             "email": "info@datalogic.com",       "branche": "Scanner/Barcode"},
    {"name": "Sick AG",                            "email": "info@sick.de",             "branche": "Sensorik"},
    {"name": "IFM Electronic GmbH",               "email": "info@ifm.com",             "branche": "Sensorik/IoT"},
]


# ── Email-Vorlagen (personalisiert, branchenspezifisch) ───────────────────────

EMAIL_TEMPLATES = [
    {
        "subject": "KI-Automatisierung für {branche} — konkrete Zeitersparnis",
        "body": """Sehr geehrte Damen und Herren,

ich wende mich an Sie, weil Unternehmen in der {branche}-Branche zunehmend von KI-gestützten Prozessen profitieren.

Was wir konkret anbieten:
✅ Automatische Dokumentenerstellung (Angebote, Lieferscheine, Berichte) — 80% Zeitersparnis
✅ KI-gestützte Kundenkommunikation — 24/7 ohne Personalaufwand
✅ Intelligente Auftragsverwaltung und Lead-Qualifizierung

Viele unserer Kunden aus dem Maschinenbau und der Industrie sparen damit 15–20 Stunden/Woche ein.

Gerne zeige ich Ihnen in einem 20-minütigen Demo-Call, was konkret für {name} umsetzbar wäre.

Interesse? Einfach antworten — ich bin schnell erreichbar.

Mit freundlichen Grüßen
Rudolf Sarkany
AI Business Solutions | aiitec.de
""",
    },
    {
        "subject": "{name} — KI spart Ihrem Team 15h/Woche",
        "body": """Guten Tag,

kurze Frage: Wie viele Stunden verbringt Ihr Team mit repetitiven Aufgaben wie E-Mail-Beantwortung, Angebotserstellung oder Datenerfassung?

Bei unseren {branche}-Kunden sind es durchschnittlich 15–20 Stunden pro Woche — Zeit, die durch KI-Automatisierung frei wird.

Was wir bieten:
→ KI-Texte für Ihre Produkte und Prozesse (DE + EN)
→ Automatische Kundenkommunikation
→ Intelligente Lead-Qualifizierung
→ Einrichtung in 48 Stunden, kein IT-Aufwand

Testen kostenlos: Ich erstelle Ihnen ein konkretes Beispiel für {name} — kostenlos und unverbindlich.

Sollen wir das angehen?

Viele Grüße
Rudolf Sarkany
KI-Automatisierung für deutsche Industrie
""",
    },
    {
        "subject": "Frage an {name}: Nutzen Sie bereits KI-Tools?",
        "body": """Sehr geehrte Damen und Herren,

laut Bitkom nutzen erst 18% der deutschen Industrieunternehmen KI-Tools produktiv — obwohl die Technologie heute einfach und günstig verfügbar ist.

Ich helfe {branche}-Unternehmen dabei, konkrete Anwendungsfälle zu identifizieren und umzusetzen:

• Angebots- und Dokumentenerstellung mit KI → 70% schneller
• Automatische Kundenkommunikation auf Deutsch und Englisch
• KI-gestützte Fehleranalyse und Qualitätsprüfung

Das Besondere: Kein großes IT-Projekt, keine langen Einführungszeiten. Setup in 2 Tagen.

Für {name} sehe ich besonders viel Potenzial im Bereich Kommunikation und Dokumentation.

Hätten Sie 20 Minuten für eine kurze Demo?

Beste Grüße
Rudolf Sarkany
""",
    },
]


# ── DB ─────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS industrie_outreach (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            company    TEXT,
            email      TEXT,
            branche    TEXT,
            status     TEXT DEFAULT 'queued',
            sent_at    TEXT,
            followup_at TEXT,
            bounced    INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_io_email ON industrie_outreach(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_io_status ON industrie_outreach(status)")
    # Seed Targets
    for t in INDUSTRIE_TARGETS:
        conn.execute(
            "INSERT OR IGNORE INTO industrie_outreach (company,email,branche) VALUES (?,?,?)",
            (t["name"], t["email"], t["branche"]),
        )
    conn.commit()
    return conn


# ── Email senden ──────────────────────────────────────────────────────────────

_SMTP_POOL = [
    (lambda: os.getenv("GMAIL_USER_AIITEC","aiitecbuuss@gmail.com"),
     lambda: os.getenv("GMAIL_APP_PASSWORD_AIITEC","").replace(" ","")),
    (lambda: os.getenv("GMAIL_USER_BULLPOWER","rudolf.sarkany.aiitec@gmail.com"),
     lambda: os.getenv("GMAIL_APP_PASSWORD_7","").replace(" ","")),
    (lambda: os.getenv("GMAIL_USER_1","dragonadnp@gmail.com"),
     lambda: os.getenv("GMAIL_APP_PASSWORD_1","").replace(" ","")),
    (lambda: os.getenv("GMAIL_USER_5","aiitecbuuss@gmail.com"),
     lambda: os.getenv("GMAIL_APP_PASSWORD_5","").replace(" ","")),
]
_smtp_idx = 0

def _send_email(to_email: str, subject: str, body: str) -> bool:
    global _smtp_idx
    try:
        from modules.gmail_accounts import _is_valid_recipient
        if not _is_valid_recipient(to_email):
            log.warning("BLOCKED (noreply/dead): %s", to_email)
            return False
    except ImportError:
        pass
    # Try SendGrid first (best deliverability for B2B)
    sg_key = os.getenv("SENDGRID_API_KEY","")
    if sg_key:
        try:
            import json as _json
            import urllib.request as _ur, urllib.parse as _up
            payload = _json.dumps({
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": os.getenv("GMAIL_USER_AIITEC","aiitecbuuss@gmail.com"),
                         "name": "AiiteC Business"},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            }).encode()
            req = _ur.Request("https://api.sendgrid.com/v3/mail/send", data=payload,
                headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=15) as r:
                if r.status in (200, 202):
                    return True
        except Exception as sg_e:
            log.debug("SendGrid fallback to Gmail: %s", sg_e)
    # Rotate through Gmail pool
    for _ in range(len(_SMTP_POOL)):
        user_fn, pass_fn = _SMTP_POOL[_smtp_idx % len(_SMTP_POOL)]
        user, pw = user_fn(), pass_fn()
        _smtp_idx += 1
        if not user or not pw:
            continue
        try:
            msg = MIMEMultipart()
            msg["From"]    = user
            msg["To"]      = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as s:
                s.starttls()
                s.login(user, pw)
                s.send_message(msg)
            return True
        except smtplib.SMTPException as smtp_e:
            if "limit exceeded" in str(smtp_e).lower() or "550" in str(smtp_e):
                log.debug("Gmail limit %s, rotating pool", user)
                continue
            log.warning("Email Fehler → %s: %s", to_email, smtp_e)
            return False
        except Exception as e:
            log.warning("Email Fehler → %s: %s", to_email, e)
            return False
    log.error("Alle SMTP-Accounts limitiert für %s", to_email)
    return False


def mark_bounced(email: str) -> bool:
    conn = _db()
    conn.execute(
        "UPDATE industrie_outreach SET bounced=1, status='bounced' WHERE email=?", (email,)
    )
    conn.commit()
    conn.close()
    return True


# ── Outreach-Zyklus ───────────────────────────────────────────────────────────

async def run_industrie_outreach(daily_limit: int = 20) -> dict:
    """
    Täglich bis zu 20 Industrieunternehmen anschreiben.
    Folge-Mails nach 5 Tagen (wenn kein Bounce).
    """
    conn    = _db()
    sent    = 0
    followup = 0
    errors  = 0
    import random

    # Erst: Follow-Ups (5 Tage alte Erst-Mails)
    from datetime import timedelta
    five_days_ago = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
    ).isoformat()
    followups = conn.execute(
        """SELECT id, company, email, branche FROM industrie_outreach
           WHERE status='sent' AND sent_at < ? AND bounced=0 LIMIT ?""",
        (five_days_ago, daily_limit // 4),
    ).fetchall()

    for fid, company, email, branche in followups:
        if sent + followup >= daily_limit:
            break
        tmpl  = random.choice(EMAIL_TEMPLATES)
        subj  = tmpl["subject"].format(name=company, branche=branche)
        body  = tmpl["body"].format(name=company, branche=branche)
        subj  = "Follow-Up: " + subj
        ok    = _send_email(email, subj, body)
        if ok:
            conn.execute(
                "UPDATE industrie_outreach SET status='followup', followup_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), fid),
            )
            followup += 1
        else:
            errors += 1
        time.sleep(2)

    # Dann: Neue Erst-Mails
    queued = conn.execute(
        """SELECT id, company, email, branche FROM industrie_outreach
           WHERE status='queued' AND bounced=0 LIMIT ?""",
        (daily_limit - followup,),
    ).fetchall()

    tmpl_idx = 0
    for rid, company, email, branche in queued:
        if sent + followup >= daily_limit:
            break
        tmpl  = EMAIL_TEMPLATES[tmpl_idx % len(EMAIL_TEMPLATES)]
        subj  = tmpl["subject"].format(name=company, branche=branche)
        body  = tmpl["body"].format(name=company, branche=branche)
        ok    = _send_email(email, subj, body)
        if ok:
            conn.execute(
                "UPDATE industrie_outreach SET status='sent', sent_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), rid),
            )
            sent += 1
        else:
            errors += 1
        tmpl_idx += 1
        time.sleep(2)

    conn.commit()
    conn.close()

    log.info("Industrie-Outreach: %d neu, %d follow-ups, %d Fehler", sent, followup, errors)
    return {"sent": sent, "followup": followup, "errors": errors, "total": sent + followup}


async def get_stats() -> dict:
    conn = _db()
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM industrie_outreach GROUP BY status"
    ).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


# ── Scheduler-Einstiegspunkt ───────────────────────────────────────────────────

async def task_industrie_outreach() -> str:
    result = await run_industrie_outreach(daily_limit=20)
    return f"Industrie-Outreach: {result['sent']} neu + {result['followup']} Follow-ups"


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    result = asyncio.run(run_industrie_outreach(daily_limit=5))
    print(f"Ergebnis: {result}")
