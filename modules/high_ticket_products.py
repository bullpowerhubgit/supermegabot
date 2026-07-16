#!/usr/bin/env python3
"""
High-Ticket Produkt-Definitionen für SuperMegaBot / AIITEC / Telegram Premium.
Erstellt: 2026-07-16 — Wave 13 High-Ticket Umbau

Enthält:
- Vollständige Produkt-Definitionen (Name, Preis, Features, ROI, Use Cases)
- Stripe Price IDs (aus .env)
- Onboarding-Flow-Definition
- ROI-Kalkulatoren
- High-Ticket Standard-Features (auf ALLEN Produkten)
"""
from __future__ import annotations

import os
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# HIGH-TICKET STANDARD-FEATURES — gilt für ALLE Produkte
# ─────────────────────────────────────────────────────────────────────────────
HT_STANDARD_FEATURES: list[str] = [
    "14-Tage kostenlose Demo (kein Credit Card)",
    "Dedizierter Onboarding-Call (60 min, 1:1 mit Rudolf Sarkany)",
    "Persönlicher Customer Success Manager (CSM)",
    "ROI-Garantie: Geld zurück wenn kein ROI in 90 Tagen",
    "SLA 99.9% Uptime-Garantie",
    "Priority Support: Antwort <4h Business-Hours",
    "Quarterly Business Reviews (QBR)",
    "Custom Webhook & API Integration inklusive",
    "White-Label Option (Agency-Tier)",
    "DSGVO-konform — alle Daten auf EU-Servern",
    "Jährliche Zahlung: 2 Monate gratis (ca. 17% Rabatt)",
]


# ─────────────────────────────────────────────────────────────────────────────
# ROI-KALKULATOR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def roi_supermegabot(monatsumsatz_eur: float, produkte_anzahl: int) -> dict[str, Any]:
    """
    Berechnet ROI-Potenzial für SuperMegaBot.
    Konservative Annahmen:
      - 15% Umsatzsteigerung durch KI-Optimierung
      - 20h Zeitersparnis/Monat (80€/h Opportunitätskosten)
    """
    umsatz_uplift = monatsumsatz_eur * 0.15
    zeit_ersparnis = 20 * 80
    gesamt_roi_monat = umsatz_uplift + zeit_ersparnis
    return {
        "monatsumsatz_ist": monatsumsatz_eur,
        "umsatz_uplift_15pct": round(umsatz_uplift, 2),
        "zeitersparnis_wert": zeit_ersparnis,
        "gesamt_roi_pro_monat": round(gesamt_roi_monat, 2),
        "roi_pro_jahr": round(gesamt_roi_monat * 12, 2),
        "empfohlener_tier": _smb_tier_empfehlung(monatsumsatz_eur, produkte_anzahl),
        "amortisation_monate": round(497 / gesamt_roi_monat * 30, 1) if gesamt_roi_monat > 0 else None,
    }


def roi_aiitec_compliance(mitarbeiter: int, umsatz_mio: float) -> dict[str, Any]:
    """
    ROI für AIITEC AI-Compliance.
    EU AI Act: Strafrisiko bis €30 Mio oder 6% Jahresumsatz (höherer Betrag).
    Compliance-Kosten intern: ~200h/Jahr × 150€/h = €30.000/Jahr.
    """
    straf_risiko = min(30_000_000, umsatz_mio * 1_000_000 * 0.06)
    interne_compliance_kosten = mitarbeiter * 40 * 150  # 40h/MA/Jahr × €150
    gesamt_risiko_reduktion = straf_risiko * 0.80 + interne_compliance_kosten * 0.70
    return {
        "strafrisiko_max_eur": round(straf_risiko, 0),
        "interne_compliance_kosten_ist": round(interne_compliance_kosten, 0),
        "risikoreduktion_durch_aiitec": round(gesamt_risiko_reduktion, 0),
        "kosten_monitoring_pa": 797 * 12,
        "roi_ratio": round(gesamt_risiko_reduktion / (797 * 12), 1),
    }


def roi_telegram(abonnenten_ist: int, conversion_rate_pct: float = 5.0) -> dict[str, Any]:
    """ROI für Telegram Premium Subscription Bot."""
    neue_abonnenten_mo = abonnenten_ist * (conversion_rate_pct / 100)
    umsatz_pro_abo = 197  # Pro-Tier durchschnittlich
    potenzial_monat = neue_abonnenten_mo * umsatz_pro_abo
    return {
        "abonnenten_gesamt": abonnenten_ist,
        "conv_rate_pct": conversion_rate_pct,
        "neue_zahlende_pro_monat": round(neue_abonnenten_mo, 1),
        "umsatz_potenzial_monat": round(potenzial_monat, 2),
        "empfohlener_tier": "Pro" if abonnenten_ist < 500 else ("Agency" if abonnenten_ist < 2000 else "Enterprise"),
    }


def _smb_tier_empfehlung(umsatz: float, produkte: int) -> str:
    if umsatz >= 50_000 or produkte >= 10_000:
        return "Enterprise (€2.497/mo)"
    if umsatz >= 15_000 or produkte >= 3_000:
        return "Scale (€997/mo)"
    return "Growth (€497/mo)"


# ─────────────────────────────────────────────────────────────────────────────
# PRODUKT-DEFINITIONEN
# ─────────────────────────────────────────────────────────────────────────────

SUPERMEGABOT_PRODUCTS: dict[str, dict[str, Any]] = {
    "growth": {
        "id": "smb_growth",
        "name": "SuperMegaBot Growth",
        "tagline": "KI-Vollautomatisierung für wachsende E-Commerce Shops",
        "price_monthly": 497,
        "price_yearly": 497 * 10,  # 2 Monate gratis
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_SMB_GROWTH", "price_1Ttv8lRJECiV6vSmJcOQeeg6"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://supermegabot-production.up.railway.app/demo/growth",
        "features": [
            "Bis 5.000 Produkte vollautomatisch verwaltet",
            "KI-Kategorisierung & SEO-Optimierung",
            "Shopify Flow + Automatische Preisanpassung",
            "Täglich 3 neue qualifizierte Produkte (Smart Product Finder)",
            "Digistore24 & Affiliate Revenue Tracking",
            "Telegram-Bot: 50+ automatische Business-Commands",
            "AI Content-Pipeline: Produkttexte, Social Posts, E-Mails",
            "Analytics Dashboard (Echtzeit)",
            "E-Mail Marketing Automation (Klaviyo Integration)",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "Shopify-Händler mit €5.000–€30.000 Monatsumsatz",
            "Dropshipper die auf 1.000+ Produkte skalieren wollen",
            "Online-Händler die 20h+/Woche für manuelle Aufgaben verschwenden",
            "E-Commerce Einsteiger die sofort professionell starten wollen",
        ],
        "roi_statement": "Typischer ROI: €1.200–€2.800/Monat durch Umsatzsteigerung + Zeitersparnis. Amortisation in unter 30 Tagen.",
        "guarantee": "ROI-Garantie: Wenn du in 90 Tagen keinen messbaren ROI siehst, erstattest wir 100% des bezahlten Betrags.",
        "onboarding": {
            "step_1": "14-Tage Demo starten (kein CC) → sofort Zugang zu allen Features",
            "step_2": "60-min Onboarding-Call mit Rudolf Sarkany — Shopify verbinden, erste Produkte importieren",
            "step_3": "CSM begleitet erste 30 Tage — täglich check-in per Telegram",
            "step_4": "KPI-Review nach 30 Tagen — ROI-Nachweis oder Geld zurück",
        },
    },

    "scale": {
        "id": "smb_scale",
        "name": "SuperMegaBot Scale",
        "tagline": "Vollskalierung für ambitionierte E-Commerce Händler",
        "price_monthly": 997,
        "price_yearly": 997 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_SMB_SCALE", "price_1Ttv97RJECiV6vSmt6ESpEMa"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://supermegabot-production.up.railway.app/demo/scale",
        "features": [
            "Unlimitierte Produkte (kein Hard-Cap)",
            "Multi-Shop Management (bis 5 Shopify-Stores)",
            "White-Label Dashboard für Endkunden",
            "AI-gestützte Wettbewerberanalyse (Geheimwaffe Engine)",
            "Automatische Trend-Erkennung & Sofort-Import",
            "YouTube Autopilot (Video-Erstellung, SEO, Upload)",
            "Meta Ads Automation (Facebook + Instagram)",
            "Dediziertes Slack-Channel für schnelle Kommunikation",
            "Wöchentliche Strategie-Calls (30 min)",
            "Custom AI-Training auf deine Produkte",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "Shopify-Händler mit €30.000–€200.000 Monatsumsatz",
            "Agenturen die mehrere Kunden-Shops verwalten",
            "Händler die von Manual zu Vollautomatik wechseln",
            "B2B-Unternehmen die ihr E-Commerce skalieren",
        ],
        "roi_statement": "Typischer ROI: €5.000–€15.000/Monat. Multi-Shop-Skalierung mit 70% weniger Personalaufwand.",
        "guarantee": "ROI-Garantie: Wenn du in 90 Tagen keinen nachweisbaren ROI siehst, erstattest wir 100% + persönliches Strategie-Consulting (Wert €2.000).",
        "onboarding": {
            "step_1": "14-Tage Demo — alle Shops verbinden, White-Label Setup",
            "step_2": "90-min Deep-Dive mit Rudolf + Tech-Team — alle Integrationen konfigurieren",
            "step_3": "Dedizierter CSM + wöchentliche Calls in den ersten 60 Tagen",
            "step_4": "Quarterly Business Review (QBR) — KPI-Analyse, Strategie-Optimierung",
        },
    },

    "enterprise": {
        "id": "smb_enterprise",
        "name": "SuperMegaBot Enterprise HT",
        "tagline": "Enterprise KI-Vollautomatisierung mit dediziertem Entwickler-Team",
        "price_monthly": 2497,
        "price_yearly": 2497 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_SMB_ENTERPRISE", "price_1Ttv9ZRJECiV6vSmXKNNxyfg"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://supermegabot-production.up.railway.app/demo/enterprise",
        "features": [
            "Vollständig dediziertes Entwickler-Team (2 FTEs)",
            "Custom AI-Modell Training auf Unternehmens-Daten",
            "Multi-Market Expansion (DE/AT/CH/EU)",
            "ERP/PIM Integration (SAP, Shopware, etc.)",
            "Enterprise Compliance (EU AI Act, DSGVO-Audit)",
            "Eigene Railway-Instanz (kein Shared Hosting)",
            "24/7 On-Call Support (Reaktionszeit <1h)",
            "Monatliche On-Site/Video Executive Briefings",
            "Eigene Datenbank-Infrastruktur (keine Datenmischung)",
            "API-First: Alle Features via REST/GraphQL abrufbar",
            "IP-Übertragung: Code gehört dir nach 24 Monaten",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "Händler mit €500.000+ Monatsumsatz",
            "Enterprises die KI in ihr ERP integrieren wollen",
            "Konzerne die DSGVO + EU AI Act compliance brauchen",
            "Investoren die ein schlüsselfertiges E-Commerce-System kaufen",
        ],
        "roi_statement": "Typischer ROI: €30.000–€100.000/Monat durch End-to-End-Automatisierung. Break-Even typisch in <30 Tagen.",
        "guarantee": "ROI-Garantie + Executive SLA: Messbare ROI-Verbesserung in 90 Tagen — sonst volle Rückerstattung + 1 Monat kostenloser Service.",
        "onboarding": {
            "step_1": "Kick-off Workshop (halbtägig, remote oder vor Ort Wien)",
            "step_2": "Technisches Discovery: ERP, PIM, Logistics Mapping",
            "step_3": "Phased Rollout: Pilot → Scale → Full-Deploy (12 Wochen)",
            "step_4": "Go-Live + monatliche Executive Reviews",
        },
    },

    "one_time_build": {
        "id": "smb_onetime",
        "name": "SuperMegaBot One-Time Build",
        "tagline": "Einmaliger Custom-Build — komplett auf dein Business zugeschnitten",
        "price_monthly": None,
        "price_onetime": 4997,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_SMB_ONETIME", "price_1TtvAIRJECiV6vSmAv9HjFAT"),
        "currency": "EUR",
        "billing": "one_time",
        "trial_days": 0,
        "demo_url": "https://supermegabot-production.up.railway.app/demo/build",
        "features": [
            "Vollständiger Custom-Build nach deinen Anforderungen (max. 60h Entwicklung)",
            "Shopify + alle Integrationen fertig konfiguriert",
            "KI-Training auf deine Produkt-Kategorien",
            "Deployment auf deine eigene Infrastruktur",
            "30 Tage Post-Launch Support inklusive",
            "Video-Dokumentation + Betriebshandbuch",
            "Quellcode-Übergabe (vollständig, kommentiert)",
            "1 Revision-Runde ohne Extrakosten",
            *HT_STANDARD_FEATURES[:5],  # Subset
        ],
        "use_cases": [
            "Unternehmen die eine einmalige Investition bevorzugen",
            "Agenturen die das System für Kunden weiterverkaufen",
            "Händler mit spezifischen ERP-Anforderungen",
        ],
        "roi_statement": "Kein laufendes Abo — einmal zahlen, für immer nutzen. ROI ab Monat 2 typisch.",
        "guarantee": "Satisfaction-Garantie: Wenn das Ergebnis nicht deinen Anforderungen entspricht, überarbeiten wir gratis bis du zufrieden bist.",
        "onboarding": {
            "step_1": "Requirements-Call (90 min) — was genau soll gebaut werden?",
            "step_2": "Tech-Spec-Dokument (von uns erstellt) — du gibst Feedback",
            "step_3": "Build-Phase (4-6 Wochen) — wöchentliche Demos",
            "step_4": "Go-Live + 30 Tage Post-Launch Support",
        },
    },
}


AIITEC_B2B_PRODUCTS: dict[str, dict[str, Any]] = {
    "compliance_monitoring": {
        "id": "aiitec_monitoring",
        "name": "AIITEC AI-Compliance Monitoring",
        "tagline": "EU AI Act Compliance — kontinuierlich überwacht, automatisch gemeldet",
        "price_monthly": 797,
        "price_yearly": 797 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_AIITEC_MONITORING", "price_1TtvAiRJECiV6vSmXyL2lVMZ"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://aiitec-saas.up.railway.app/demo/compliance",
        "target_company_size": "50–500 Mitarbeiter",
        "features": [
            "Echtzeit-Monitoring aller KI-Systeme im Unternehmen",
            "Automatische EU AI Act Risikoklassifizierung (Art. 6, Annex III)",
            "Transparenz-Pflicht Watcher (Art. 50 DSGVO-konform)",
            "Monatlicher Compliance-Report für Geschäftsführung + Aufsicht",
            "Alert-System: sofortige Benachrichtigung bei Compliance-Verstoß",
            "DSGVO Art. 35 DSFA-Integration",
            "Audit-Trail: 3 Jahre revisionssicherer Log",
            "API zu bestehender GRC-Software (ServiceNow, Jira, etc.)",
            "Halbjährliches Compliance-Review mit AIITEC-Experten",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "KMUs die KI-Tools (ChatGPT, Copilot, etc.) im Unternehmen einsetzen",
            "Fintech/Legaltech die Hochrisiko-KI betreiben",
            "Konzerne mit Compliance-Abteilung die Automatisierung suchen",
            "Steuerberater/Rechtsanwälte mit KI-gestützten Mandanten-Tools",
        ],
        "roi_statement": "EU AI Act: Strafen bis €30 Mio. oder 6% Jahresumsatz. Unser Monitoring kostet €9.564/Jahr — eine Versicherung die sich auszahlt.",
        "risk_reduction": "Reduziert Compliance-Risiko um 85% (basierend auf Audit-Erfahrungen 2025/26)",
        "guarantee": "Compliance-Garantie: Bei einem Audit der durch unsere Kontrolllücke scheitert, übernehmen wir die direkten Folgekosten (bis €10.000).",
    },

    "enterprise_audit": {
        "id": "aiitec_audit",
        "name": "AIITEC Enterprise Audit",
        "tagline": "Vollständiger EU AI Act Compliance-Audit — einmalig, wasserdicht",
        "price_monthly": None,
        "price_onetime": 4997,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_AIITEC_AUDIT", "price_1TtvB3RJECiV6vSmf5DMInfT"),
        "currency": "EUR",
        "billing": "one_time",
        "trial_days": 0,
        "demo_url": "https://aiitec-saas.up.railway.app/demo/audit",
        "target_company_size": "50–5.000 Mitarbeiter",
        "features": [
            "Vollständige Bestandsaufnahme aller KI-Systeme im Unternehmen",
            "Risikoklassifizierung nach EU AI Act (Art. 6 + Annex III)",
            "Gap-Analyse: Wo bist du heute, wo musst du hin?",
            "Schriftliches Audit-Bericht (60–100 Seiten, juristisch verwertbar)",
            "Priorisierter Maßnahmenplan (Quick Wins → Must-Have → Nice-to-Have)",
            "Executive Presentation (für Vorstand/Geschäftsführung)",
            "Follow-Up Call (30 Tage nach Bericht): Umsetzungs-Check",
            "Zertifizierungs-Unterstützung (ISO 42001 Vorbereitung)",
        ],
        "use_cases": [
            "Konzerne die sich auf EU AI Act 2026 vorbereiten müssen",
            "Due-Diligence vor M&A: KI-Risiken des Akquisitionsobjekts",
            "Boards die ihren Pflichten nach Art. 10 EU AI Act nachkommen",
            "Unternehmen nach einem regulatorischen Hinweis/Beschwerde",
        ],
        "roi_statement": "Strafen-Prävention: Ein einziger Bußgeldbescheid kostet 10–100x mehr als dieser Audit.",
        "guarantee": "Qualitäts-Garantie: Wenn der Audit-Bericht nicht den Erwartungen entspricht, überarbeiten wir ihn kostenlos.",
    },

    "retainer": {
        "id": "aiitec_retainer",
        "name": "AIITEC Compliance Retainer",
        "tagline": "Dein KI-Compliance-Team auf Abruf — immer aktuell, immer bereit",
        "price_monthly": 1997,
        "price_yearly": 1997 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_AIITEC_RETAINER", "price_1TtvBcRJECiV6vSmd9ho0tbd"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://aiitec-saas.up.railway.app/demo/retainer",
        "target_company_size": "100–2.000 Mitarbeiter",
        "features": [
            "Alles aus Compliance Monitoring (€797/mo) inklusive",
            "Dedizierter Compliance-Experte (5h/Monat On-Demand Consulting)",
            "Gesetzgebungs-Alert: neue EU AI Act Anforderungen sofort gemeldet",
            "Interne KI-Policy-Erstellung + Aktualisierung",
            "Mitarbeiter-Awareness Training (1x/Quartal, max. 20 TN)",
            "Incident-Response: Bei Datenpanne/Compliance-Verstoß sofort reagieren",
            "Behörden-Korrespondenz-Support (BSI, BfDI, Datenschutzbehörde AT)",
            "Monatliches C-Level Briefing (30 min)",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "Unternehmen ohne eigene Compliance-Abteilung",
            "Finanz- und Versicherungsbranche mit strenger Aufsicht",
            "MedTech + HealthTech (Hochrisiko-KI nach Annex III)",
            "Öffentliche Institutionen (§ 38 DSG-Pflichten)",
        ],
        "roi_statement": "Ein interner Compliance-Manager kostet €80.000–€120.000/Jahr. Unser Retainer: €23.964/Jahr — volle Expertise, flexibel kündbar.",
        "guarantee": "Ergebnis-Garantie: Wenn du nach 6 Monaten keine signifikante Compliance-Verbesserung siehst, pausieren wir 2 Monate kostenlos.",
    },
}


TELEGRAM_PREMIUM_PRODUCTS: dict[str, dict[str, Any]] = {
    "pro": {
        "id": "tg_pro",
        "name": "Telegram Premium Pro",
        "tagline": "Professionelle KI-Bot-Suite für Einzel-Unternehmer und Freelancer",
        "price_monthly": 197,
        "price_yearly": 197 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_TG_PRO", "price_1TtvC1RJECiV6vSm1qXePyCC"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://t.me/DudiRudibot?start=demo_pro",
        "features": [
            "50 Premium Bot-Commands (Shopify, AI, Content, Analytics)",
            "Tägliche KI-Marktanalyse per Telegram",
            "Shopify Produkt-Import via Chat-Command",
            "AI-Content-Generator (Texte, Posts, E-Mails)",
            "Revenue Dashboard — täglicher Report im Chat",
            "Digistore24 + Stripe Umsatz-Tracking",
            "Smart Alerts: Preisänderungen, Out-of-Stock, Trending",
            "Persönlicher Onboarding-Call (30 min)",
            *HT_STANDARD_FEATURES[:8],
        ],
        "use_cases": [
            "Solopreneure mit Shopify-Store",
            "Freelancer die KI für ihre Kunden nutzen",
            "Online-Händler die unterwegs den Überblick behalten wollen",
        ],
        "roi_statement": "Spart 10h+/Woche durch Bot-Automatisierung. Bei €60/h Stundensatz = €2.400/Monat Zeitwert-Ersparnis.",
        "guarantee": "14-Tage Geld-zurück-Garantie ohne Fragen.",
    },

    "agency": {
        "id": "tg_agency",
        "name": "Telegram Premium Agency",
        "tagline": "KI-Bot-Suite für Agenturen — verwalte alle Kunden-Shops aus Telegram",
        "price_monthly": 497,
        "price_yearly": 497 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_TG_AGENCY", "price_1TtvCNRJECiV6vSm6YlDa5aw"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://t.me/DudiRudibot?start=demo_agency",
        "features": [
            "Alle Pro-Features (50 Commands) inklusive",
            "Multi-Client Dashboard — bis 10 Kunden-Accounts",
            "White-Label: eigener Bot-Name für Kunden",
            "Automatische Kunden-Reports (wöchentlich per Telegram/E-Mail)",
            "Team-Zugang: bis 3 Mitarbeiter",
            "Kampagnen-Management: geplante Posts über mehrere Kanäle",
            "Affiliate-Tracking: wer hat welchen Kunden gebracht?",
            "Monthly Agency-Strategy-Call (60 min)",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "E-Commerce-Agenturen mit 3–10 Kunden",
            "Social-Media-Manager die mehrere Shops betreuen",
            "VA-Teams die Kunden-Reporting automatisieren wollen",
        ],
        "roi_statement": "10 Kunden × €200 gesparte Stunden/Monat = €2.000 Zeitwert. Preis: €497/mo. ROI: 4:1.",
        "guarantee": "ROI-Garantie: Wenn du nach 90 Tagen keine nachweisbare Zeitersparnis hast, erstatten wir 100%.",
    },

    "enterprise": {
        "id": "tg_enterprise",
        "name": "Telegram Premium Enterprise",
        "tagline": "Enterprise Telegram-Automation — Custom Bots, Unlimited Scale",
        "price_monthly": 997,
        "price_yearly": 997 * 10,
        "stripe_price_id": os.getenv("STRIPE_PRICE_HT_TG_ENTERPRISE", "price_1TtvCzRJECiV6vSmASIX5zwg"),
        "currency": "EUR",
        "billing": "recurring_monthly",
        "trial_days": 14,
        "demo_url": "https://t.me/DudiRudibot?start=demo_enterprise",
        "features": [
            "Alle Agency-Features inklusive",
            "Unlimitierte Kunden-Accounts",
            "Custom Bot-Development (auf Wunsch neue Commands)",
            "Eigene Telegram-Mini-App für Endkunden",
            "Enterprise API: alle Bot-Funktionen als REST-Endpoints",
            "Dedicated Railway-Instanz (kein Shared)",
            "Audit-Log: alle Bot-Aktionen protokolliert",
            "Executive Telegram-Commands (Board-Dashboard)",
            "Schulungen für das gesamte Team (inkl. Video-Kurs)",
            *HT_STANDARD_FEATURES,
        ],
        "use_cases": [
            "Große Agenturen mit 10+ Kunden",
            "Enterprises die interne Prozesse via Telegram steuern",
            "Plattformen die Telegram als Kundenkommunikations-Kanal nutzen",
        ],
        "roi_statement": "Vollständige Telegram-Automatisierung: 50+ Stunden/Monat einsparen × durchschnittliche Teamgröße.",
        "guarantee": "Enterprise-SLA: 99.9% Uptime + <1h Reaktionszeit bei Incidents. Sonst Service-Gutschrift.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Alle Produkte als flache Liste
# ─────────────────────────────────────────────────────────────────────────────

ALL_HT_PRODUCTS: dict[str, dict[str, Any]] = {
    **{f"smb_{k}": v for k, v in SUPERMEGABOT_PRODUCTS.items()},
    **{f"aiitec_{k}": v for k, v in AIITEC_B2B_PRODUCTS.items()},
    **{f"tg_{k}": v for k, v in TELEGRAM_PREMIUM_PRODUCTS.items()},
}


def get_product(product_id: str) -> dict[str, Any] | None:
    """Gibt ein Produkt anhand seiner ID zurück."""
    return ALL_HT_PRODUCTS.get(product_id)


def get_stripe_price_id(product_id: str) -> str | None:
    """Gibt die Stripe Price ID eines Produkts zurück."""
    p = get_product(product_id)
    return p.get("stripe_price_id") if p else None


def list_products_summary() -> list[dict[str, str]]:
    """Kurze Übersicht aller High-Ticket Produkte für API-Responses."""
    result = []
    for pid, prod in ALL_HT_PRODUCTS.items():
        price_str = (
            f"€{prod['price_monthly']}/mo"
            if prod.get("price_monthly")
            else f"€{prod.get('price_onetime', '?')} einmalig"
        )
        result.append({
            "id": pid,
            "name": prod["name"],
            "price": price_str,
            "tagline": prod["tagline"],
            "stripe_price_id": prod.get("stripe_price_id", ""),
            "trial_days": str(prod.get("trial_days", 0)),
        })
    return result


if __name__ == "__main__":
    import json
    print("=== HIGH-TICKET PRODUKTE — ÜBERSICHT ===\n")
    for p in list_products_summary():
        print(f"  {p['name']:45s} {p['price']:20s} {p['stripe_price_id']}")
    print()
    print("=== ROI-BEISPIEL: SuperMegaBot Growth ===")
    roi = roi_supermegabot(monatsumsatz_eur=10_000, produkte_anzahl=500)
    print(json.dumps(roi, indent=2, ensure_ascii=False))
    print()
    print("=== ROI-BEISPIEL: AIITEC Compliance (50 MA, €5M Umsatz) ===")
    roi2 = roi_aiitec_compliance(mitarbeiter=50, umsatz_mio=5.0)
    print(json.dumps(roi2, indent=2, ensure_ascii=False))
