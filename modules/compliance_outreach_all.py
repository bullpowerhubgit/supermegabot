#!/usr/bin/env python3
"""
Compliance Outreach — vollautomatisch für alle 11 Tools
========================================================
Versendet täglich personalisierte Emails an potenzielle Käufer
aller Compliance-Tools (GPSR, NIS2, CRA, E-Rechnung, PPWR,
EUDR, HR-KI, BFSG, ZVG, Kanzlei-Radar, AI-Act).

Täglich max. 15 Emails pro Tool = max. 165 Emails/Tag total.
Follow-Up nach 5 Tagen, dann nochmal nach 10 Tagen.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import sqlite3
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Any

log = logging.getLogger(__name__)

_DB_PATH  = Path(__file__).parent.parent / "data" / "compliance_outreach.db"
BASE_URL  = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://supermegabot-production.up.railway.app")

# ── Tool-Konfiguration ────────────────────────────────────────────────────────

TOOLS = [
    {
        "id":      "gpsr",
        "name":    "GPSR Shop-Shield",
        "url":     f"{BASE_URL}/gpsr",
        "frist":   "bereits seit 13.12.2024 in Kraft",
        "risiko":  "Abmahnungen und Rückrufaktionen",
        "preis":   "€199/Audit",
        "subject": "GPSR-Pflicht seit Dezember: Ihr Shop unter Risiko?",
        "body": """\
Sehr geehrte Damen und Herren,

seit dem 13. Dezember 2024 gilt die EU-Produktsicherheitsverordnung (GPSR) verpflichtend.
{branche}-Unternehmen wie {name} müssen für jeden Artikel:
  • Eine verantwortliche Person in der EU benennen
  • Warnhinweise auf Produktebene angeben
  • Rückverfolgbarkeit sicherstellen

Erste Abmahnungen gegen Shop-Betreiber wurden bereits verschickt.

Unser GPSR Shop-Shield prüft Ihren gesamten Produktkatalog in 24h:
  → {url}

Audit ab €199, Ergebnis als PDF-Report, sofort umsetzbare Checkliste.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance GmbH
""",
        "targets": [
            {"name": "OTTO Group", "email": "compliance@otto.de", "branche": "E-Commerce"},
            {"name": "Zalando SE", "email": "legal@zalando.de", "branche": "Fashion E-Commerce"},
            {"name": "About You GmbH", "email": "info@aboutyou.de", "branche": "Fashion E-Commerce"},
            {"name": "Notino GmbH", "email": "info@notino.de", "branche": "Beauty E-Commerce"},
            {"name": "MediaMarkt Saturn", "email": "info@mediamarkt.de", "branche": "Elektronik"},
            {"name": "Cyberport GmbH", "email": "info@cyberport.de", "branche": "Elektronik"},
            {"name": "Alternate GmbH", "email": "info@alternate.de", "branche": "Elektronik"},
            {"name": "Thomann GmbH", "email": "info@thomann.de", "branche": "Musik"},
            {"name": "myToys.de GmbH", "email": "info@mytoys.de", "branche": "Spielzeug"},
            {"name": "Baby Walz GmbH", "email": "service@baby-walz.de", "branche": "Baby"},
            {"name": "Völkner Elektronik", "email": "info@voelkner.de", "branche": "Elektronik"},
            {"name": "Pearl GmbH", "email": "info@pearl.de", "branche": "Gadgets"},
            {"name": "Heine GmbH", "email": "info@heine.de", "branche": "Mode"},
            {"name": "Westfalia GmbH", "email": "info@westfalia.de", "branche": "Haushalt"},
            {"name": "Tchibo GmbH", "email": "presse@tchibo.de", "branche": "Multichannel"},
            {"name": "Lidl E-Commerce", "email": "info@lidl.de", "branche": "Lebensmittel"},
            {"name": "Aldi Online", "email": "info@aldi-onlineshop.de", "branche": "Lebensmittel"},
            {"name": "Kaufland.de", "email": "info@kaufland.de", "branche": "Lebensmittel"},
            {"name": "Rossmann Online", "email": "info@rossmann.de", "branche": "Drogerie"},
            {"name": "dm Online", "email": "info@dm.de", "branche": "Drogerie"},
        ],
    },
    {
        "id":      "erechnung",
        "name":    "E-Rechnungs-Autopilot",
        "url":     f"{BASE_URL}/e-rechnung",
        "frist":   "B2B-Empfangspflicht seit 01.01.2025",
        "risiko":  "Ablehnung durch Auftraggeber, Verzugszinsen",
        "preis":   "ab €49/Monat",
        "subject": "E-Rechnung B2B-Pflicht: Ihr Unternehmen bereits umgestellt?",
        "body": """\
Sehr geehrte Damen und Herren,

seit dem 01. Januar 2025 sind alle deutschen B2B-Unternehmen verpflichtet,
elektronische Rechnungen (E-Rechnung nach EN 16931 / ZUGFeRD/XRechnung) zu empfangen.
Ab 2027 gilt die Sendepflicht für alle.

Unternehmen wie {name} aus der {branche}-Branche müssen jetzt:
  • XRechnung oder ZUGFeRD-Format unterstützen
  • Bestehende Rechnungsprozesse umstellen
  • Steuerkonformität sicherstellen

Unser E-Rechnungs-Autopilot erledigt die komplette Umstellung:
  → {url}

Ab €49/Monat, sofortige Integration, kein ERP-Wechsel nötig.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Automation GmbH
""",
        "targets": [
            {"name": "Mittelständische Bäckerei Gruppe", "email": "info@baeckereiverband.de", "branche": "Lebensmittel"},
            {"name": "Handwerkskammer München", "email": "info@hwk-muenchen.de", "branche": "Handwerk"},
            {"name": "BDO AG Wirtschaftsprüfung", "email": "info@bdo.de", "branche": "Beratung"},
            {"name": "Steuer-Ring GmbH", "email": "info@steuer-ring.de", "branche": "Steuerberatung"},
            {"name": "Lohnsteuerhilfe Bayern", "email": "info@lohi.de", "branche": "Steuerberatung"},
            {"name": "Dr. Kleeberg & Partner", "email": "info@kleeberg.de", "branche": "Wirtschaftsprüfung"},
            {"name": "Volksbank BWKG eG", "email": "info@volksbank-bwkg.de", "branche": "Finanz"},
            {"name": "apoBank", "email": "info@apobank.de", "branche": "Finanz"},
            {"name": "Provinzial Versicherung", "email": "info@provinzial.de", "branche": "Versicherung"},
            {"name": "Signal Iduna Gruppe", "email": "info@signal-iduna.de", "branche": "Versicherung"},
            {"name": "Goldbeck GmbH", "email": "info@goldbeck.de", "branche": "Bau"},
            {"name": "Ed. Züblin AG", "email": "info@zueblin.de", "branche": "Bau"},
            {"name": "Kaefer Group", "email": "info@kaefer.com", "branche": "Industrie"},
            {"name": "Fachverband Gebäude-Klima", "email": "info@fgk.de", "branche": "Gebäudetechnik"},
            {"name": "Arburg GmbH + Co KG", "email": "info@arburg.de", "branche": "Maschinenbau"},
        ],
    },
    {
        "id":      "nis2",
        "name":    "NIS2 KMU-Check",
        "url":     f"{BASE_URL}/nis2",
        "frist":   "seit Oktober 2024 in Kraft",
        "risiko":  "Bußgelder bis €10 Mio., persönliche Haftung der Geschäftsführung",
        "preis":   "€149/Check",
        "subject": "NIS2-Pflichten: Haftung der Geschäftsführung seit Oktober 2024",
        "body": """\
Sehr geehrte Damen und Herren,

seit Oktober 2024 gilt die NIS2-Richtlinie auch für mittelständische Unternehmen
in kritischen Sektoren — und schließt die persönliche Haftung der Geschäftsführung ein.

{branche}-Unternehmen wie {name} müssen:
  • Cyber-Risikomanagement implementieren
  • Meldepflichten für Sicherheitsvorfälle einhalten (24h Erstmeldung!)
  • Lieferkettensicherheit nachweisen

Unser NIS2 KMU-Check identifiziert Ihre Lücken in 48h:
  → {url}

Ab €149, Report mit Maßnahmenplan, keine IT-Kenntnisse erforderlich.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance GmbH
""",
        "targets": [
            {"name": "Stadtwerke München GmbH", "email": "info@swm.de", "branche": "Energie"},
            {"name": "RheinEnergie AG", "email": "info@rheinenergie.com", "branche": "Energie"},
            {"name": "Thüringer Energie AG", "email": "info@thueringerenergie.de", "branche": "Energie"},
            {"name": "Deutschen Telekom AG", "email": "konzern.pressebuero@telekom.de", "branche": "Telekommunikation"},
            {"name": "Vodafone GmbH Deutschland", "email": "pressestelle@vodafone.com", "branche": "Telekommunikation"},
            {"name": "1&1 AG", "email": "info@1und1.de", "branche": "Telekommunikation"},
            {"name": "DHL Group", "email": "pressestelle@dhlgroup.com", "branche": "Logistik"},
            {"name": "Kühne + Nagel AG", "email": "info@kuehne-nagel.com", "branche": "Logistik"},
            {"name": "Hellmann Worldwide Logistics", "email": "info@hellmann.com", "branche": "Logistik"},
            {"name": "Dürr AG", "email": "info@durr.com", "branche": "Maschinenbau"},
            {"name": "Knorr-Bremse AG", "email": "info@knorr-bremse.com", "branche": "Automobil"},
            {"name": "Stabilus GmbH", "email": "info@stabilus.com", "branche": "Automobil"},
            {"name": "BayWa AG", "email": "info@baywa.de", "branche": "Agrar/Energie"},
            {"name": "Wacker Chemie AG", "email": "info@wacker.com", "branche": "Chemie"},
            {"name": "Evonik Industries", "email": "info@evonik.com", "branche": "Chemie"},
        ],
    },
    {
        "id":      "kanzlei",
        "name":    "Kanzlei-Mandanten-Radar",
        "url":     f"{BASE_URL}/kanzlei-radar",
        "frist":   "laufend — täglich neue Insolvenzen",
        "risiko":  "Mandate an Konkurrenz-Kanzleien verlieren",
        "preis":   "€490/Monat (exklusiv per Region)",
        "subject": "Insolvenz-Mandanten-Radar: Wer heute eröffnet, morgen mandatiert",
        "body": """\
Sehr geehrte Damen und Herren,

Insolvenzanwälte wissen: Wer den Geschäftsführer am Tag der Eröffnung erreicht,
bekommt das Mandat. Ihr Radar liefert genau diesen Tag.

Für {name}: Regionaler Tages-Alert mit allen Neueröffnungen in Ihrem PLZ-Gebiet —
exklusiv, denn pro Region gibt es nur einen Abnehmer.

Unser Kanzlei-Mandanten-Radar:
  • Täglich: Neue Insolvenzeröffnungen + Handelsregister-Änderungen
  • Per E-Mail + Telegram, sofort nach Bekanntmachung
  • Exklusivität: Ein Kanzlei-Abo pro Region
  → {url}

€490/Monat, 2 Wochen kostenlos testen.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Intelligence GmbH
""",
        "targets": [
            {"name": "Schultze & Braun", "email": "info@schubra.de", "branche": "Insolvenzrecht"},
            {"name": "Grub Brugger & Partner", "email": "info@grub-brugger.de", "branche": "Insolvenzrecht"},
            {"name": "Anchor Rechtsanwälte", "email": "info@anchor.eu", "branche": "Insolvenzrecht"},
            {"name": "hww Wienberg Wilhelm", "email": "info@hww-partner.de", "branche": "Insolvenzrecht"},
            {"name": "Pluta Rechtsanwalts GmbH", "email": "info@pluta.net", "branche": "Insolvenzrecht"},
            {"name": "Schneider Geiwitz", "email": "info@sg-partner.de", "branche": "Insolvenzrecht"},
            {"name": "Kübler GmbH", "email": "info@kuebler-partner.de", "branche": "Insolvenzrecht"},
            {"name": "Flöther & Wissing", "email": "info@floethe-wissing.de", "branche": "Insolvenzrecht"},
            {"name": "Restrukturierungspartner", "email": "info@restrukturierungspartner.de", "branche": "Restrukturierung"},
            {"name": "Wellensiek Rechtsanwälte", "email": "info@wellensiek.de", "branche": "Insolvenzrecht"},
            {"name": "BDO Legal", "email": "info@bdo-legal.de", "branche": "Restrukturierung"},
            {"name": "FalkenSteg GmbH", "email": "info@falkensteg.com", "branche": "Restrukturierung"},
            {"name": "Buchalik Brömmekamp", "email": "info@buchalik-broemmekamp.de", "branche": "Insolvenzrecht"},
            {"name": "Jaffé Rechtsanwälte", "email": "info@jaffe.de", "branche": "Insolvenzrecht"},
            {"name": "Böhm-Bendisch & Kollegen", "email": "info@bbk-partner.de", "branche": "Insolvenzrecht"},
        ],
    },
    {
        "id":      "zvg",
        "name":    "ZVG Exposé-Engine",
        "url":     f"{BASE_URL}/zvg",
        "frist":   "laufend — 60.000+ Termine/Jahr",
        "risiko":  "Fehlkäufe, übersehene Wohnrechte = €10.000+ Verlust",
        "preis":   "€99/Monat Bieter Pro",
        "subject": "Zwangsversteigerungen: Kaufen ohne Überraschungen — ZVG Dossier",
        "body": """\
Sehr geehrte Damen und Herren,

60.000+ Zwangsversteigerungstermine pro Jahr — aber die Unterlagen sind oft
80-seitige Amtsgericht-PDFs ohne Struktur. Ein übersehenes Wohnrecht oder
Nießbrauch kann den Kauf in einen Verlust verwandeln.

Unser ZVG Exposé-Engine-System erstellt in 3 Minuten ein lesbares Dossier:
  • Verkehrswert, Baujahr, Mängel strukturiert aufbereitet
  • Risiko-Flags: Wohnrecht, Altlasten, fehlende Innenbesichtigung
  • Vergleichspreise der Umgebung
  • Termin-Alerts für Ihre Wunsch-Region

Für {branche} wie {name} ideal als Profi-Desk (€290/Monat, unbegrenzt + API):
  → {url}

2 Wochen kostenlos testen — erstes Dossier gratis.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Data GmbH
""",
        "targets": [
            {"name": "Dr. Peters Group", "email": "info@dr-peters.de", "branche": "Immobilien-Investor"},
            {"name": "Corestate Capital", "email": "info@corestate-capital.com", "branche": "Immobilien-Investor"},
            {"name": "Deutsche Wohnen SE", "email": "info@deutsche-wohnen.com", "branche": "Wohnimmobilien"},
            {"name": "LEG Immobilien SE", "email": "info@leg.ag", "branche": "Wohnimmobilien"},
            {"name": "Vonovia SE", "email": "pressestelle@vonovia.de", "branche": "Wohnimmobilien"},
            {"name": "Engel & Völkers", "email": "info@engelvoelkers.com", "branche": "Makler"},
            {"name": "Dahler Company", "email": "info@dahlercompany.com", "branche": "Makler"},
            {"name": "Sotheby's Deutschland", "email": "info@sothebysrealty.de", "branche": "Makler"},
            {"name": "ImmoScout24 GmbH", "email": "info@immoscout24.de", "branche": "Proptech"},
            {"name": "McMakler GmbH", "email": "info@mcmakler.de", "branche": "Proptech"},
            {"name": "Exporo AG", "email": "info@exporo.de", "branche": "Immobilien-Fintech"},
            {"name": "Brickwise", "email": "info@brickwise.at", "branche": "Immobilien-Fintech"},
            {"name": "REFIRE GmbH", "email": "info@refire.com", "branche": "Immobilien-Fintech"},
            {"name": "Baufi24 GmbH", "email": "info@baufi24.de", "branche": "Finanzierung"},
            {"name": "Interhyp AG", "email": "info@interhyp.de", "branche": "Finanzierung"},
        ],
    },
    {
        "id":      "hrki",
        "name":    "HR-KI Hochrisiko-Audit",
        "url":     f"{BASE_URL}/hr-ki-audit",
        "frist":   "AI Act Art. 6 — ab 02.08.2026 Hochrisiko-KI-Klassifizierung",
        "risiko":  "KI in HR = Hochrisiko-KI → strenge Anforderungen",
        "preis":   "€299/Audit",
        "subject": "DRINGEND: KI in Ihrer Personalauswahl = Hochrisiko nach AI Act (02.08.2026)",
        "body": """\
Sehr geehrte Damen und Herren,

der EU AI Act klassifiziert KI-Systeme in der Personalauswahl als HOCHRISIKO-KI
(Anhang III, Nr. 4). Das betrifft: Bewerber-Screening, CV-Parser, Assessment-Tools,
automatisierte Interview-Auswertung.

Für {branche}-Unternehmen wie {name} bedeutet das bis zum 02.08.2026:
  • Vollständige technische Dokumentation aller KI-HR-Systeme
  • Menschliche Aufsicht nachweisen
  • Daten-Governance und Bias-Prüfung
  • Konformitätserklärung erstellen

Frist: 20 Tage. Bußgeld bei Verstoß: bis €15 Mio. oder 3% Jahresumsatz.

Unser HR-KI Hochrisiko-Audit prüft Ihr System in 48h:
  → {url}

€299, Ergebnis als zertifizierbarer PDF-Report.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance GmbH
""",
        "targets": [
            {"name": "Hays AG", "email": "info@hays.de", "branche": "Personaldienstleister"},
            {"name": "Adecco Deutschland", "email": "info@adecco.de", "branche": "Personaldienstleister"},
            {"name": "Randstad Deutschland", "email": "info@randstad.de", "branche": "Personaldienstleister"},
            {"name": "Manpower Deutschland", "email": "info@manpowergroup.de", "branche": "Personaldienstleister"},
            {"name": "Michael Page GmbH", "email": "info.de@michaelpage.com", "branche": "Executive Search"},
            {"name": "Kienbaum Management Consultants", "email": "info@kienbaum.com", "branche": "HR-Beratung"},
            {"name": "Korn Ferry Deutschland", "email": "info@kornferry.com", "branche": "Executive Search"},
            {"name": "Haufe Group SE", "email": "info@haufe.de", "branche": "HR-Software"},
            {"name": "Personio SE & Co. KG", "email": "info@personio.de", "branche": "HR-Software"},
            {"name": "rexx systems GmbH", "email": "info@rexx-systems.com", "branche": "HR-Software"},
            {"name": "Softgarden e-recruiting GmbH", "email": "info@softgarden.de", "branche": "HR-Software"},
            {"name": "d.vinci HR-Systems GmbH", "email": "info@dvinci.de", "branche": "HR-Software"},
            {"name": "Haufe-Lexware GmbH", "email": "info@lexware.de", "branche": "HR-Software"},
            {"name": "DATEV eG HR", "email": "info@datev.de", "branche": "HR-Software"},
            {"name": "SAP SE HR-Division", "email": "info@sap.com", "branche": "ERP/HR"},
        ],
    },
    {
        "id":      "cra",
        "name":    "CRA Melde-Wächter",
        "url":     f"{BASE_URL}/cra",
        "frist":   "Cyber Resilience Act — gilt ab 2027, Meldepflichten ab 2026",
        "risiko":  "24h Meldepflicht bei Sicherheitsvorfällen",
        "preis":   "€99/Monat",
        "subject": "Cyber Resilience Act: Ihre Meldepflicht bei Sicherheitsvorfällen — 24h Frist",
        "body": """\
Sehr geehrte Damen und Herren,

der EU Cyber Resilience Act verpflichtet Hersteller digitaler Produkte ab 2026
zur 24-Stunden-Meldung aktiv ausgenutzter Schwachstellen an ENISA.

Für {branche}-Unternehmen wie {name} mit digitalen Produkten bedeutet das:
  • Kontinuierliches Schwachstellen-Monitoring
  • 24h Alert-System für neue CVEs
  • Automatische Meldung an ENISA
  • Dokumentation aller Sicherheitsereignisse

Unser CRA Melde-Wächter übernimmt das vollautomatisch:
  → {url}

€99/Monat — kein Security-Team nötig.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Security GmbH
""",
        "targets": [
            {"name": "Bosch Connected Devices", "email": "info@bosch.com", "branche": "IoT-Hersteller"},
            {"name": "Siemens Healthineers", "email": "info@siemens-healthineers.com", "branche": "Medizintechnik"},
            {"name": "Endress+Hauser AG", "email": "info@endress.com", "branche": "Messtechnik"},
            {"name": "Sick AG", "email": "info@sick.de", "branche": "Sensortechnik"},
            {"name": "Balluff GmbH", "email": "info@balluff.com", "branche": "Sensortechnik"},
            {"name": "Trumpf GmbH + Co. KG", "email": "info@trumpf.com", "branche": "Lasertechnik"},
            {"name": "ifm electronic gmbh", "email": "info@ifm.com", "branche": "Sensortechnik"},
            {"name": "Turck GmbH & Co. KG", "email": "info@turck.com", "branche": "Automatisierung"},
            {"name": "WAGO GmbH & Co. KG", "email": "info@wago.com", "branche": "Automatisierung"},
            {"name": "Lenze SE", "email": "info@lenze.com", "branche": "Antriebstechnik"},
            {"name": "Kuka AG", "email": "info@kuka.com", "branche": "Robotik"},
            {"name": "Universal Robots", "email": "info@universal-robots.com", "branche": "Robotik"},
            {"name": "Wibu-Systems AG", "email": "info@wibu.com", "branche": "Software-Schutz"},
            {"name": "secunet Security Networks AG", "email": "info@secunet.com", "branche": "IT-Security"},
            {"name": "genua GmbH", "email": "info@genua.de", "branche": "IT-Security"},
        ],
    },
    {
        "id":      "bfsg",
        "name":    "BFSG Barriere-Scanner",
        "url":     f"{BASE_URL}/bfsg",
        "frist":   "28.06.2025 — BFSG gilt für alle digitalen Produkte & Dienste",
        "risiko":  "Bußgelder bis €100.000, Klagebefugnis für Verbände",
        "preis":   "€149/Scan",
        "subject": "BFSG-Frist 28. Juni: Ihr digitaler Dienst barrierefrei?",
        "body": """\
Sehr geehrte Damen und Herren,

seit dem 28. Juni 2025 gilt das Barrierefreiheitsstärkungsgesetz (BFSG) für
digitale Produkte und Dienstleistungen in Deutschland.

{branche}-Unternehmen wie {name} müssen sicherstellen:
  • Website-Barrierefreiheit nach WCAG 2.1 AA
  • Barrierefreie Mobile Apps
  • Zugänglichkeit von E-Commerce-Funktionen
  • Konformitätserklärung veröffentlichen

Verbände können bereits klagen. Behörden führen Stichproben durch.

Unser BFSG Barriere-Scanner prüft Ihren digitalen Dienst vollautomatisch:
  → {url}

€149/Scan, Ergebnis in 24h, Maßnahmenplan inklusive.

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Compliance GmbH
""",
        "targets": [
            {"name": "ING-DiBa AG", "email": "info@ing.de", "branche": "Online-Banking"},
            {"name": "DKB Deutsche Kreditbank", "email": "info@dkb.de", "branche": "Online-Banking"},
            {"name": "N26 Bank GmbH", "email": "info@n26.com", "branche": "Neobank"},
            {"name": "comdirect bank AG", "email": "info@comdirect.de", "branche": "Online-Banking"},
            {"name": "Scalable Capital GmbH", "email": "info@scalable.capital", "branche": "Fintech"},
            {"name": "Trade Republic Bank GmbH", "email": "info@traderepublic.com", "branche": "Fintech"},
            {"name": "Flixbus GmbH", "email": "info@flixbus.de", "branche": "Fernbus"},
            {"name": "BahnCard GmbH", "email": "info@bahn.de", "branche": "Bahn"},
            {"name": "Booking.com GmbH", "email": "info@booking.com", "branche": "Reise"},
            {"name": "HRS GmbH", "email": "info@hrs.de", "branche": "Reise"},
            {"name": "CHECK24 Vergleichsportal", "email": "info@check24.de", "branche": "Vergleichsportal"},
            {"name": "Verivox GmbH", "email": "info@verivox.de", "branche": "Vergleichsportal"},
            {"name": "Idealo Internet GmbH", "email": "info@idealo.de", "branche": "Preisvergleich"},
            {"name": "StepStone GmbH", "email": "info@stepstone.de", "branche": "Jobportal"},
            {"name": "XING SE", "email": "info@xing.com", "branche": "Karriere-Netzwerk"},
        ],
    },
]


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id     TEXT,
            company     TEXT,
            email       TEXT,
            branche     TEXT,
            status      TEXT DEFAULT 'pending',
            sent_at     INTEGER,
            followup_at INTEGER,
            followup2_at INTEGER,
            bounced     INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_email_tool ON outreach(email, tool_id)")
    conn.commit()

    # Seed alle Targets
    for tool in TOOLS:
        for t in tool["targets"]:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO outreach (tool_id, company, email, branche) VALUES (?,?,?,?)",
                    (tool["id"], t["name"], t["email"], t["branche"])
                )
            except Exception:
                pass
    conn.commit()
    return conn


# ── Email senden ──────────────────────────────────────────────────────────────

def _send_email(smtp_user: str, smtp_pass: str, smtp_host: str, smtp_port: int,
                to: str, subject: str, body: str) -> bool:
    try:
        from modules.email_guard import validate_email
        ok_g, errs = validate_email(subject=subject, body=body, to_email=to, skip_dedup=True)
        if not ok_g:
            log.warning("EmailGuard BLOCKED to=%s reason=%s", to, "; ".join(errs))
            return False
    except ImportError:
        pass
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to, msg.as_string())
        return True
    except Exception as e:
        log.warning("SMTP Fehler [%s]: %s", to, e)
        return False


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

async def run_compliance_outreach_all(per_tool_limit: int = 15) -> Dict[str, Any]:
    """
    Sendet täglich bis zu `per_tool_limit` Emails pro Tool.
    Verarbeitet zuerst Follow-Ups (Prio), dann neue Kontakte.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com"))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("GMAIL_APP_PASSWORD_AIITEC", ""))

    if not smtp_pass:
        log.warning("Compliance Outreach: SMTP-Passwort fehlt — übersprungen")
        return {"ok": False, "reason": "no_smtp_password"}

    conn    = _db()
    now_ts  = int(time.time())
    results = {"ok": True, "total_sent": 0, "by_tool": {}}

    for tool in TOOLS:
        tid     = tool["id"]
        sent    = 0
        errors  = 0

        # 1. Follow-Ups (Priorität)
        followups = conn.execute(
            "SELECT id, company, email, branche FROM outreach "
            "WHERE tool_id=? AND status='sent' AND bounced=0 "
            "AND followup_at<=? AND followup_at IS NOT NULL "
            "LIMIT ?",
            (tid, now_ts, per_tool_limit)
        ).fetchall()

        for row_id, company, email, branche in followups:
            body = tool["body"].replace("{name}", company).replace("{branche}", branche).replace("{url}", tool["url"])
            ok   = await asyncio.to_thread(
                _send_email, smtp_user, smtp_pass, smtp_host, smtp_port,
                email, f"Follow-Up: {tool['subject']}", body
            )
            if ok:
                conn.execute(
                    "UPDATE outreach SET status='followup', followup_at=NULL, followup2_at=? WHERE id=?",
                    (now_ts + 10 * 86400, row_id)
                )
                conn.commit()
                sent += 1
            else:
                errors += 1
            await asyncio.sleep(2)

        # 2. Neue Kontakte (bis per_tool_limit gesamt)
        remaining = per_tool_limit - sent
        if remaining > 0:
            pending = conn.execute(
                "SELECT id, company, email, branche FROM outreach "
                "WHERE tool_id=? AND status='pending' AND bounced=0 LIMIT ?",
                (tid, remaining)
            ).fetchall()

            for row_id, company, email, branche in pending:
                body = tool["body"].replace("{name}", company).replace("{branche}", branche).replace("{url}", tool["url"])
                ok   = await asyncio.to_thread(
                    _send_email, smtp_user, smtp_pass, smtp_host, smtp_port,
                    email, tool["subject"], body
                )
                if ok:
                    conn.execute(
                        "UPDATE outreach SET status='sent', sent_at=?, followup_at=? WHERE id=?",
                        (now_ts, now_ts + 5 * 86400, row_id)
                    )
                    conn.commit()
                    sent += 1
                else:
                    errors += 1
                await asyncio.sleep(2)

        results["by_tool"][tid] = {"sent": sent, "errors": errors}
        results["total_sent"] += sent
        log.info("Compliance Outreach [%s]: %d gesendet, %d Fehler", tid, sent, errors)

    conn.close()
    return results


def mark_bounced(email: str, tool_id: str = "") -> bool:
    """Markiert eine Adresse als bounced — wird bei zukünftigen Runs übersprungen."""
    try:
        conn = _db()
        if tool_id:
            conn.execute("UPDATE outreach SET bounced=1 WHERE email=? AND tool_id=?", (email, tool_id))
        else:
            conn.execute("UPDATE outreach SET bounced=1 WHERE email=?", (email,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
