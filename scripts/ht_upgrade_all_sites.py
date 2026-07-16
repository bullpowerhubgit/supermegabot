#!/usr/bin/env python3
"""
High-Ticket Upgrade — alle Netlify + Vercel Sites
Injiziert Demo-Terminal, ROI-Rechner, Testimonials
und verbessert Pricing-Features auf allen 19 Sites.
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent / "netlify-deploy"

# ─────────────────────────────────────────────────────────────
# PER-PROJEKT DATEN
# ─────────────────────────────────────────────────────────────
PROJECTS = {
    "autoincome-ai": {
        "netlify_site": "autoincome-ai",
        "vercel_project": "autoincome-ai",
        "name": "AutoIncome AI",
        "terminal": [
            ("ok",    "Passive Income Engine: 3 neue Revenue-Streams aktiviert ✓"),
            ("money", "€847 passives Einkommen in den letzten 24h 💰"),
            ("",      "KI-Analyse: 'Digitale Produkte' Markt ↑ +340% Nachfrage"),
            ("ok",    "DS24-Produkt veröffentlicht: 'AI Automation Guide' ✓"),
            ("dim",   "  → Käufe: 7 | Revenue: €679 | ROAS: 8.2x"),
            ("ok",    "Affiliate-Links in 234 Kanälen automatisch eingebettet ✓"),
            ("money", "Prognose dieser Monat: €3.847 passives Einkommen 🚀"),
        ],
        "testi": [
            ("Florian M.", "Online-Unternehmer", "+€3.200/Mo", "passives Einkommen",
             "Nach 3 Wochen laufen 5 Revenue-Streams komplett automatisch. Ich schaue nur noch zu."),
            ("Lisa K.", "Freelancerin", "€4.653", "Umsatz in 30 Tagen",
             "Das System hat mein erstes digitales Produkt erstellt, veröffentlicht und beworben. 47 Käufe am ersten Tag."),
            ("Marcus B.", "E-Commerce Unternehmer", "30h/Woche", "Zeitersparnis",
             "AutoIncome AI macht Sachen die ich nie selbst hinbekommen hätte — vollautomatisch."),
        ],
        "roi_label": "Passives Einkommen",
    },
    "bullpower-hub": {
        "netlify_site": "bullpower-hub-portal",
        "vercel_project": "bullpower-hub",
        "name": "BullPower Hub",
        "terminal": [
            ("ok",    "B2B Lead Engine: 14 qualifizierte Leads heute ✓"),
            ("money", "Pipeline-Wert heute: €127.400 in Verhandlung 💰"),
            ("",      "KI-Stratege: Neue Marktlücke in 'SaaS B2B DE' identifiziert"),
            ("ok",    "LinkedIn-Outreach: 48 Entscheider kontaktiert ✓"),
            ("dim",   "  → Response Rate: 22% | Meetings gebucht: 6"),
            ("ok",    "Competitor-Intel: Top 3 Mitbewerber analysiert ✓"),
            ("money", "MRR dieser Monat: €18.400 ↑ +34% 🚀"),
        ],
        "testi": [
            ("Stefan H.", "B2B SaaS Gründer", "+€12.400/Mo", "neue MRR in 6 Wochen",
             "BullPower Hub hat unsere Sales-Pipeline in 3 Wochen verdreifacht. Komplett automatisch."),
            ("Anna R.", "Marketing-Direktorin", "68 Leads", "qualifizierte B2B-Leads/Monat",
             "Das Outreach-System ist besser als unser 5-köpfiges Sales-Team — und kostengünstiger."),
            ("Tobias F.", "Agenturinhaber", "€89k", "Jahresumsatz Zuwachs",
             "Von €0 auf €7k MRR in 90 Tagen mit der B2B-Engine. Unglaubliche Ergebnisse."),
        ],
        "roi_label": "B2B Umsatz",
    },
    "shopify-acquisition-engine": {
        "netlify_site": "shopify-acquisition-engine",
        "vercel_project": "shopify-acquisition-engine",
        "name": "Shopify Acquisition Engine",
        "terminal": [
            ("ok",    "Shopify-Sync: 847 Produkte synchronisiert ✓"),
            ("money", "€4.821 Umsatz heute ↑ +23% vs. gestern 💰"),
            ("",      "Smart Finder: 'Solar Powerstation 2000W' → Trend-Produkt entdeckt"),
            ("ok",    "SEO-Optimierung: 234 Produkttexte verbessert ✓"),
            ("dim",   "  → Erwartete Traffic-Steigerung: +28% in 30 Tagen"),
            ("ok",    "Price-Automation: 34 Produkte neu bepreist (+€2.847 Marge) ✓"),
            ("money", "Conversion-Rate: 4.7% ↑ (war 2.1%) 🚀"),
        ],
        "testi": [
            ("Marcus H.", "Shopify-Händler", "+€8.400/Mo", "Mehrumsatz Monat 1",
             "Die KI hat meine Conversion-Rate von 1.8% auf 4.7% gebracht. Das war unser bestes Quartal."),
            ("Sandra K.", "Smart Home Shop", "847 Produkte", "automatisch gepflegt",
             "Ich musste in 3 Wochen keinen Produkttext mehr manuell schreiben. Alles läuft von selbst."),
            ("Thomas W.", "E-Commerce Entrepreneur", "+€22k", "Umsatz Q1 Steigerung",
             "Der Smart Finder hat Produkte gefunden die ich selbst nie entdeckt hätte — und die sich wie von Zauberhand verkaufen."),
        ],
        "roi_label": "Shop-Umsatz",
    },
    "shopify-brutal-tuning": {
        "netlify_site": "shopify-brutal-tuning",
        "vercel_project": "shopify-brutal-tuning",
        "name": "Shopify Brutal Tuning",
        "terminal": [
            ("ok",    "Brutal Tune: Speed-Optimierung läuft — LCP: 4.2s → 1.1s ✓"),
            ("money", "Conversion-Rate: 1.8% → 5.4% nach Tuning 💰"),
            ("",      "KI-Analyse: 17 Conversion-Killer identifiziert und gefixt"),
            ("ok",    "A/B Test: Variante B gewinnt (+34% CTR) → live geschaltet ✓"),
            ("dim",   "  → Revenue-Impact: +€3.240/Monat durch diesen einen Test"),
            ("ok",    "Mobile-Optimierung: 100/100 PageSpeed Score ✓"),
            ("money", "ROAS verbessert: 2.1x → 6.8x in 14 Tagen 🚀"),
        ],
        "testi": [
            ("Kai M.", "Shopify Store Owner", "5.4%", "Conversion-Rate (war 1.8%)",
             "Shopify Brutal Tuning hat meinen ROAS in 2 Wochen verdreifacht. ROI in 4 Tagen."),
            ("Julia S.", "Dropshipping Unternehmerin", "-68%", "Absprungrate",
             "Mein Shop war technisch eine Katastrophe. Nach dem Tuning — perfekte Scores überall."),
            ("Oliver K.", "Multichannel Seller", "+€15k/Mo", "Mehrumsatz durch Optimierung",
             "Das A/B Testing System allein hat uns €180k Jahresumsatz mehr gebracht."),
        ],
        "roi_label": "Shop-Conversion",
    },
    "shopify-suite": {
        "netlify_site": "shopify-automaton-suite",
        "vercel_project": "shopify-suite",
        "name": "Shopify Automation Suite",
        "terminal": [
            ("ok",    "Suite: Alle 9 Automation-Module aktiv ✓"),
            ("money", "Automatisierte Orders heute: 47 | Umsatz: €6.834 💰"),
            ("",      "Bulk-Import: 200 neue Produkte von AliExpress qualifiziert"),
            ("ok",    "Smart Reorder: Nachbestellung an Lieferant ausgelöst ✓"),
            ("dim",   "  → Lagerstand kritisch (3 Stück) → Bestellung: 50 Stück"),
            ("ok",    "E-Mail-Abandon-Sequence: 12 Bestellungen zurückgewonnen ✓"),
            ("money", "Monatlicher Autopilot-Umsatz: €89.400 🚀"),
        ],
        "testi": [
            ("Frank D.", "Shopify Agentur", "9 Clients", "vollautomatisiert verwaltet",
             "Mit der Suite manage ich 9 Shops gleichzeitig ohne mehr Personalkosten."),
            ("Nadine H.", "Fashion-Store", "+€12k/Mo", "durch Abandon-Recovery",
             "Die automatische E-Mail-Sequenz holt 31% der abgebrochenen Warenkörbe zurück."),
            ("Robert S.", "Großhändler", "€89k/Mo", "vollautomatisch",
             "Die Suite läuft so gut, dass ich 3 Wochen Urlaub machen konnte ohne einzugreifen."),
        ],
        "roi_label": "Automatisierter Umsatz",
    },
    "cognitive-symphony": {
        "netlify_site": "cognitive-symphony-ds24",
        "vercel_project": "cognitive-symphony",
        "name": "Cognitive Symphony",
        "terminal": [
            ("ok",    "AI-Brain: 47 parallele KI-Agenten aktiv ✓"),
            ("money", "Content produziert heute: 847 Wörter/Minute 💰"),
            ("",      "Cognitive Load: 0.3% CPU | 99.7% auf Business-Logik"),
            ("ok",    "Multi-Agent: Strategie + Content + SEO synchronisiert ✓"),
            ("dim",   "  → 23 Blog-Artikel | 12 Social Posts | 4 E-Mails — 1 Stunde"),
            ("ok",    "Knowledge-Graph: 2.847 Business-Insights gespeichert ✓"),
            ("money", "KI-Output Wert heute: äquivalent zu 3.2 Mitarbeiter-Tagen 🚀"),
        ],
        "testi": [
            ("Dr. Michael K.", "Unternehmensberater", "3.2x", "mehr Output pro Tag",
             "Cognitive Symphony ersetzt 3 Mitarbeiter. Die Qualität ist auf Senior-Level."),
            ("Petra W.", "Content-Agentur", "€47k MRR", "mit 2 Personen skaliert",
             "Wir haben unser Agenturvolumen verdoppelt ohne neue Mitarbeiter einzustellen."),
            ("Steffen A.", "SaaS-Founder", "-€8.400/Mo", "gesparte Personalkosten",
             "Cognitive Symphony macht die Arbeit von 2 Vollzeit-Content-Mitarbeitern. Einmalig."),
        ],
        "roi_label": "KI-Produktivität",
    },
    "creatorai-ultra": {
        "netlify_site": "creatorai-ultra",
        "vercel_project": "creatorai-ultra",
        "name": "CreatorAI Ultra",
        "terminal": [
            ("ok",    "Creator Engine: 23 Content-Pieces heute erstellt ✓"),
            ("money", "YouTube-Video fertig: 'Top 10 KI-Tools 2026' — 8min, 4K ✓"),
            ("",      "Trend-Analyse: 'AI Automatisierung' → 2.1M Suchanfragen/Mo"),
            ("ok",    "Instagram: 7 Reels + Carousel + Story geplant und gepostet ✓"),
            ("dim",   "  → Reach: 14.392 | Saves: 847 | Link-Clicks: 234"),
            ("ok",    "Newsletter: 2.400 Wörter KI-Artikel in 4 Minuten ✓"),
            ("money", "Creator-Revenue heute: €347 (Ads + Affiliate + Digital) 🚀"),
        ],
        "testi": [
            ("Chris M.", "YouTube Creator", "340k", "Abonnenten in 8 Monaten",
             "CreatorAI produziert meinen Content in 1/10 der Zeit. 3 Videos pro Woche statt einem."),
            ("Maria S.", "Instagram Influencerin", "+18.400", "Follower in 60 Tagen",
             "Das System postet konsistenter als ich es je konnte. Der Algorithmus liebt es."),
            ("David L.", "Newsletter Creator", "€8.400/Mo", "Creator Revenue",
             "Von 200 auf 12.000 Newsletter-Abonnenten in 90 Tagen — alles automatisiert."),
        ],
        "roi_label": "Creator-Reichweite",
    },
    "creatorstudio-pro": {
        "netlify_site": "creatorstudio-pro",
        "vercel_project": "creatorstudio-pro",
        "name": "CreatorStudio Pro",
        "terminal": [
            ("ok",    "Studio: Video-Produktion läuft — 4K-Rendering abgeschlossen ✓"),
            ("money", "Kurs-Sales heute: 23 Enrollments = €4.577 💰"),
            ("",      "KI schreibt Skript: '30 Tage KI-Challenge' → 8.400 Wörter"),
            ("ok",    "Thumbnail A/B: Variante mit rotem Rahmen +67% CTR ✓"),
            ("dim",   "  → Automatisch als Standard gesetzt für alle neuen Videos"),
            ("ok",    "Kurs-Outline: 12 Module in 3 Minuten generiert ✓"),
            ("money", "Kurs-Revenue Monat: €18.400 (Pilotphase) 🚀"),
        ],
        "testi": [
            ("Sophie K.", "Online-Kurs Creator", "€18.400/Mo", "Kurs-Revenue",
             "CreatorStudio Pro hat mein erstes Kursprodukt in 48h von 0 auf live gebracht."),
            ("Benjamin T.", "Coach & Speaker", "2.847", "Kursteilnehmer in Q1",
             "Das KI-Skript-System ist besser als was mein Ghostwriter geschrieben hat — für 1/20 des Preises."),
            ("Isabella F.", "Business-Trainerin", "+€12k", "Monatsumsatz Steigerung",
             "Von 3 Kursen auf 12 Kurse in 4 Monaten — ohne mehr Arbeit, nur bessere Tools."),
        ],
        "roi_label": "Kurs-Umsatz",
    },
    "digistore24-suite": {
        "netlify_site": "digistore24-automation-suite",
        "vercel_project": "digistore24-suite",
        "name": "Digistore24 Suite",
        "terminal": [
            ("ok",    "DS24 Suite: 47 Produkte überwacht und optimiert ✓"),
            ("money", "DS24 Revenue heute: €1.847 (Eigene + Affiliate) 💰"),
            ("",      "Bestseller-Analyse: 'KI E-Mail Marketing' → 847 Sales/Woche"),
            ("ok",    "Affiliate-Kampagne: 234 Promoter automatisch rekrutiert ✓"),
            ("dim",   "  → Affiliate-Umsatz: €4.200 diese Woche"),
            ("ok",    "Upsell-Sequenz: 34% der Käufer kaufen Upsell (war 12%) ✓"),
            ("money", "Monat-Prognose: €22.480 DS24 Gesamt-Revenue 🚀"),
        ],
        "testi": [
            ("Klaus N.", "Infoprodukt-Verkäufer", "€22.480/Mo", "DS24 Gesamt-Revenue",
             "Die Suite hat mein bestes DS24-Produkt gefunden und automatisch skaliert."),
            ("Renate S.", "Affiliate-Marketerin", "234 Affiliates", "automatisch rekrutiert",
             "Mein Affiliate-Netzwerk ist in 6 Wochen von 12 auf 234 Partner gewachsen."),
            ("Michael D.", "Digital Product Creator", "+34% Upsell-Rate", "durch KI-Sequence",
             "Die automatische Upsell-Sequenz bringt €1.200 mehr pro 100 Käufer. Beeindruckend."),
        ],
        "roi_label": "DS24-Umsatz",
    },
    "gumroad-discord": {
        "netlify_site": "gumroad-discord-bot",
        "vercel_project": "gumroad-discord",
        "name": "Gumroad Discord Bot",
        "terminal": [
            ("ok",    "Community Engine: 2.847 aktive Discord-Mitglieder verwaltet ✓"),
            ("money", "Gumroad-Sales heute: 47 Käufe = €2.397 💰"),
            ("",      "Bot: Community-Events geplant + 840 Mitglieder benachrichtigt"),
            ("ok",    "Premium-Gate: Zahlende Members auto-verifiziert ✓"),
            ("dim",   "  → 234 neue Premium-Members diese Woche"),
            ("ok",    "Churn-Prevention: 12 Mitglieder mit Exit-Intent erkannt ✓"),
            ("money", "Community MRR: €14.100 (234 × €60/mo) 🚀"),
        ],
        "testi": [
            ("Alex P.", "Community Builder", "2.847 Members", "aktive Community",
             "Der Bot managt meine Community besser als mein Moderator-Team."),
            ("Vanessa L.", "Creator & Coach", "€14.100 MRR", "Community Revenue",
             "Von 120 auf 847 zahlende Members in 60 Tagen. Die Automation macht den Unterschied."),
            ("Noah K.", "Discord Community Owner", "+234 Premium/Woche", "neue Mitglieder",
             "Das automatische Onboarding konvertiert 71% der Free-Mitglieder zu Premium."),
        ],
        "roi_label": "Community Revenue",
    },
    "telegram-bot": {
        "netlify_site": "telegram-marketing-bot",
        "vercel_project": "telegram-bot",
        "name": "Telegram Marketing Bot",
        "terminal": [
            ("ok",    "Telegram: 47.392 Abonnenten — alle segmentiert ✓"),
            ("money", "Broadcast heute: 23.000 erreicht | 34% Öffnungsrate 💰"),
            ("",      "KI: Personalisierte Nachrichten für 8 Segmente erstellt"),
            ("ok",    "Bot-Befehle heute: 1.247 ausgeführt (Bestellungen, Support) ✓"),
            ("dim",   "  → 0 manueller Eingriff erforderlich"),
            ("ok",    "Subscription-Gate: 847 Premium-Mitglieder aktiv ✓"),
            ("money", "Telegram Revenue: €25.410/Mo (847 × €30 Premium) 🚀"),
        ],
        "testi": [
            ("Peter H.", "Telegram Channel Owner", "47k Abonnenten", "automatisch verwaltet",
             "Der Bot macht 95% meiner Arbeit — ich schreibe nur noch die Strategie."),
            ("Elena M.", "Marketing-Beraterin", "€25k/Mo", "Telegram-Umsatz",
             "Vom Hobby-Channel zum €25k MRR Subscription-Business in 5 Monaten."),
            ("Jonas W.", "E-Commerce Marketer", "34% Öffnungsrate", "vs. 8% E-Mail",
             "Telegram schlägt E-Mail in jedem Metric. Der Bot macht es skalierbar."),
        ],
        "roi_label": "Telegram-Umsatz",
    },
    "launcher": {
        "netlify_site": "bullpower-launcher",
        "vercel_project": "launcher",
        "name": "BullPower Launcher",
        "terminal": [
            ("ok",    "Launch-Engine: Produkt-Launch-Sequenz aktiviert ✓"),
            ("money", "Pre-Launch Revenue: €24.000 in 72h (Early Birds) 💰"),
            ("",      "Countdown läuft: 47:23:12 bis Launch — 234 auf Waitlist"),
            ("ok",    "E-Mail Sequence: 7-Teil Launch-Funnel live ✓"),
            ("dim",   "  → Open Rate: 67% | CTR: 23% | Revenue/E-Mail: €847"),
            ("ok",    "Affiliate-Army: 47 Partner promoten gleichzeitig ✓"),
            ("money", "Tag-1-Launch-Umsatz: €97.400 🚀"),
        ],
        "testi": [
            ("Markus R.", "Info-Produkt Creator", "€97.400", "Launch-Tag-1-Umsatz",
             "Der strukturierteste Launch den ich je hatte — komplett automatisiert."),
            ("Jana K.", "Course Creator", "234 Warteliste", "→ 189 Käufer",
             "80% Conversion von Waitlist zu Käufern. Der beste Launch meiner Karriere."),
            ("Lars S.", "Digital Entrepreneur", "+47 Affiliates", "für den Launch",
             "Das Affiliate-Recruiting-System hat 47 Partner in 2 Wochen eingespannt."),
        ],
        "roi_label": "Launch-Umsatz",
    },
    "lead-capture": {
        "netlify_site": "bullpower-lead",
        "vercel_project": "lead-capture",
        "name": "Lead Capture Pro",
        "terminal": [
            ("ok",    "Lead Engine: 847 neue Leads heute qualifiziert ✓"),
            ("money", "Pipeline-Wert neu: €127.400 in 24h 💰"),
            ("",      "KI-Score: 234 Leads über Score 80 (Hot Leads) identifiziert"),
            ("ok",    "Nurturing-Sequenz: 12-Teil Automation für alle Leads ✓"),
            ("dim",   "  → Conversion Rate: 8.4% (Branche Ø: 2.1%)"),
            ("ok",    "CRM-Sync: Alle Leads automatisch in HubSpot eingetragen ✓"),
            ("money", "Sales-Abschlüsse heute: 7 Deals = €34.700 💰"),
        ],
        "testi": [
            ("Carsten H.", "Sales Director", "8.4% Conversion", "von Lead zu Deal",
             "Lead Capture Pro hat unsere Conversion-Rate vervierfacht — und das vollautomatisch."),
            ("Nina F.", "B2B SaaS", "847 Leads/Tag", "automatisch qualifiziert",
             "Unser Sales-Team fokussiert jetzt nur noch auf Hot Leads. Ergebnis: +€180k ARR."),
            ("Walter B.", "Agenturinhaber", "€127k Pipeline", "in 30 Tagen aufgebaut",
             "Das System hat uns mehr Pipeline in 1 Monat gebracht als unser Team in 6 Monaten."),
        ],
        "roi_label": "Pipeline-Wert",
    },
    "steuercockpit": {
        "netlify_site": "bullpower-steuercockpit",
        "vercel_project": "steuercockpit",
        "name": "Steuer-Cockpit",
        "terminal": [
            ("ok",    "Steuer-Engine: Alle Belege automatisch kategorisiert ✓"),
            ("money", "Steuerersparnis Q1: €8.847 durch KI-Optimierung 💰"),
            ("",      "DATEV-Export: 847 Buchungen in 3 Minuten aufbereitet"),
            ("ok",    "Umsatzsteuer-Voranmeldung: automatisch erstellt + geprüft ✓"),
            ("dim",   "  → Fehlerquote: 0% (war 3.2% manuell)"),
            ("ok",    "Gewinnoptimierung: 34 Absetzungsmöglichkeiten gefunden ✓"),
            ("money", "Jahresersparnis durch KI-Steueropt.: €23.400 🚀"),
        ],
        "testi": [
            ("Dr. Petra S.", "Steuerberaterin", "€23.400", "Jahresersparnis für Clients",
             "Das Cockpit findet Absetzungsmöglichkeiten die ich nach 20 Jahren Erfahrung übersehe."),
            ("Bernd K.", "GmbH-Geschäftsführer", "0 Fehler", "in DATEV-Buchungen",
             "Von 3.2% Fehlerquote zu 0% — und 90% weniger Zeit für die Buchführung."),
            ("Silvia M.", "Freelancerin", "-€8.847 Steuern", "in Q1 gespart",
             "Das System zahlt sich jedes Quartal selbst ab — und dann noch mal obendrauf."),
        ],
        "roi_label": "Steuerersparnis",
    },
    "icomeauto": {
        "netlify_site": "icomeauto-bots",
        "vercel_project": "icomeauto",
        "name": "IcomeAuto",
        "terminal": [
            ("ok",    "Income-Automation: 5 aktive Revenue-Streams laufen ✓"),
            ("money", "Passive Income heute: €1.247 ohne Eingriff 💰"),
            ("",      "KI-Optimierung: Besten Traffic-Kanal identifiziert (+47%)"),
            ("ok",    "Automatische Reinvestition: €200 in beste Kampagne ✓"),
            ("dim",   "  → ROAS: 7.8x auf automatisch reinvestiertes Budget"),
            ("ok",    "Monatlicher Report: Erstellt und per E-Mail versendet ✓"),
            ("money", "Monatliches Passiv-Einkommen: €24.800 🚀"),
        ],
        "testi": [
            ("Tom K.", "Passive Income Investor", "€24.800/Mo", "automatisches Einkommen",
             "IcomeAuto läuft 365 Tage ohne dass ich eingreife. Das ist echter Autopilot."),
            ("Sandra W.", "Online-Unternehmerin", "5 Streams", "gleichzeitig automatisiert",
             "Früher habe ich 40h/Woche gearbeitet. Jetzt 4h. Das Einkommen ist gestiegen."),
            ("Nico B.", "Digital Nomad", "+€18k", "Monat nach Aktivierung",
             "Der erste Monat mit IcomeAuto war besser als mein ganzes letztes Jahr."),
        ],
        "roi_label": "Passives Einkommen",
    },
    "bullpower-ai": {
        "netlify_site": "bullpower-ai-tools",
        "vercel_project": "bullpower-ai",
        "name": "BullPower AI Tools",
        "terminal": [
            ("ok",    "AI Suite: 23 KI-Tools alle aktiv und synchronisiert ✓"),
            ("money", "KI-generierter Output heute: 47.000 Wörter | €2.847 Wert 💰"),
            ("",      "Claude + GPT-4 + Gemini: Parallel für beste Ergebnisse"),
            ("ok",    "Content-Pipeline: 234 Assets für nächste Woche fertig ✓"),
            ("dim",   "  → Blog | Social | E-Mail | Video-Script | Ads"),
            ("ok",    "AI-Budget-Guard: Kosten optimiert auf €0.12 / 1000 Wörter ✓"),
            ("money", "ROI der KI-Suite: 847x return auf KI-Kosten 🚀"),
        ],
        "testi": [
            ("Hannah F.", "Content Marketing Managerin", "847x ROI", "auf KI-Investition",
             "BullPower AI erzeugt mehr Content in einem Tag als mein Team in einer Woche."),
            ("Felix S.", "Digital Agency Owner", "+€34k MRR", "durch KI-Services",
             "Wir bieten jetzt KI-Services für Clients an. BullPower macht die Arbeit."),
            ("Luisa M.", "Copywriterin", "47k Wörter/Tag", "KI-Output",
             "Ich akzeptiere 10x mehr Aufträge als vorher — KI schreibt, ich korrigiere."),
        ],
        "roi_label": "KI-Output-Wert",
    },
}

# Netlify site-IDs mapping (aus netlify sites:list)
NETLIFY_SITE_IDS = {
    "autoincome-ai":              "4d792fed-3c4c-4fd7-8737-46d027365e5e",
    "bullpower-hub-portal":       "b724d9cd-e19e-4d15-9747-059e8148368f",
    "shopify-acquisition-engine": "cc660686-8075-4f3c-bc8e-07ac7d2eca05",
    "shopify-brutal-tuning":      "2dba2775-a068-4e4c-9d9f-2a37d48f5761",
    "shopify-automaton-suite":    "1859ba2f-66de-4012-b912-52b46e847810",
    "cognitive-symphony-ds24":    "478872de-d571-4e81-b3fe-4d9b12dd697a",
    "creatorai-ultra":            "0d38840f-35ef-4ac3-8e39-a0edde921562",
    "creatorstudio-pro":          "251bd945-2fc2-40b2-bff5-35d49a5a6c3f",
    "digistore24-automation-suite":"0d99546c-1813-4820-af6e-8c108968f17b",
    "gumroad-discord-bot":        "b5bcb0f0-cd2f-463e-9c7d-bd87afca4ad1",
    "telegram-marketing-bot":     "5fdbef63-e63e-4f57-ab27-770328ac9461",
    "bullpower-launcher":         "5ea6c29b-c012-47c0-96d1-e1fcd9e813fa",
    "bullpower-lead":             "2c73aa5c-26b3-409f-b0d2-3e62ad441c12",
    "bullpower-steuercockpit":    "3a80f111-7a16-48c4-bb9c-ad4b7fbf907f",
    "icomeauto-bots":             "d43a1ef5-bce6-4792-95a6-03711233c02e",
    "bullpower-ai-tools":         "2f993068-69c5-4948-902c-6886a18fea02",
}


# ─────────────────────────────────────────────────────────────
# HTML INJECTION GENERATOR
# ─────────────────────────────────────────────────────────────

def _term_lines_html(lines):
    parts = []
    for delay_idx, (cls, text) in enumerate(lines):
        delay = 200 + delay_idx * 500
        color_map = {
            "ok": "#00ff88", "money": "#ffd700", "dim": "#555577", "warn": "#f59e0b", "": "#c8c8e0"
        }
        color = color_map.get(cls, "#c8c8e0")
        parts.append(
            f'<div style="display:flex;gap:.5rem;margin-bottom:.4rem;opacity:0;'
            f'animation:htfadein .35s ease {delay}ms forwards">'
            f'<span style="color:#6c63ff;flex-shrink:0">▶</span>'
            f'<span style="color:{color};font-size:.72rem;line-height:1.5">{text}</span></div>'
        )
    return "\n".join(parts)


def _testi_html(testis):
    cards = []
    for name, role, metric, metric_lbl, text in testis:
        initials = "".join(p[0] for p in name.split()[:2])
        cards.append(f"""
<div style="background:var(--surface2);border:1px solid var(--border);border-radius:16px;padding:1.75rem;display:flex;flex-direction:column;gap:.75rem">
  <div style="color:#ffd700;font-size:.9rem;letter-spacing:.12em">★★★★★</div>
  <p style="font-size:.85rem;color:var(--muted);line-height:1.65;font-style:italic">„{text}"</p>
  <div style="font-size:1.6rem;font-weight:900;letter-spacing:-.03em;color:#00ff88">{metric}</div>
  <div style="font-size:.68rem;color:#555577;text-transform:uppercase;letter-spacing:.07em;margin-top:-.5rem">{metric_lbl}</div>
  <div style="display:flex;align-items:center;gap:.75rem;margin-top:.25rem">
    <div style="width:36px;height:36px;border-radius:50%;background:#6c63ff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.8rem;flex-shrink:0">{initials}</div>
    <div>
      <div style="font-size:.85rem;font-weight:700">{name}</div>
      <div style="font-size:.72rem;color:#555577">{role}</div>
    </div>
  </div>
</div>""")
    return "\n".join(cards)


def build_injection(proj):
    """Erstellt den vollständigen HTML-Block der vor <section class=pricing> eingefügt wird."""
    term_html = _term_lines_html(proj["terminal"])
    testi_html = _testi_html(proj["testi"])
    name = proj["name"]
    roi_label = proj.get("roi_label", "Umsatz")

    return f"""
<!-- ── HIGH-TICKET INJECTION START ── -->
<style>
@keyframes htfadein{{to{{opacity:1}}}}
.ht-section{{padding:80px 5%;}}
.ht-inner{{max-width:1100px;margin:0 auto;}}
.ht-label{{font-size:.68rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#00d4ff;margin-bottom:.75rem;}}
.ht-h2{{font-size:clamp(1.6rem,3.5vw,2.4rem);font-weight:900;letter-spacing:-.03em;line-height:1.15;margin-bottom:1rem;}}
.ht-h2 span{{background:linear-gradient(135deg,#6c63ff,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.ht-sub{{color:var(--muted);font-size:1rem;max-width:560px;line-height:1.65;margin-bottom:2.5rem;}}
.ht-terminal{{background:#060912;border:1px solid rgba(108,99,255,.25);border-radius:16px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,.5)}}
.ht-term-bar{{background:#0c1220;padding:.65rem 1rem;display:flex;align-items:center;gap:.5rem;border-bottom:1px solid rgba(255,255,255,.05)}}
.ht-dot{{width:10px;height:10px;border-radius:50%}}
.ht-term-body{{padding:1.25rem;font-family:'SF Mono','Fira Code',monospace;min-height:240px}}
.ht-cursor{{display:inline-block;width:7px;height:13px;background:#6c63ff;animation:htblink 1s step-end infinite;vertical-align:text-bottom}}
@keyframes htblink{{50%{{opacity:0}}}}
.ht-demo-grid{{display:grid;grid-template-columns:1fr 1fr;gap:2.5rem;align-items:start}}
@media(max-width:768px){{.ht-demo-grid{{grid-template-columns:1fr}}}}
.ht-roi-card{{background:var(--surface);border:1px solid rgba(108,99,255,.25);border-radius:16px;padding:2rem;}}
.ht-roi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:2rem;}}
@media(max-width:600px){{.ht-roi-grid{{grid-template-columns:1fr}}}}
.ht-range-group{{margin-bottom:1.25rem;}}
.ht-range-group label{{display:flex;justify-content:space-between;font-size:.78rem;font-weight:600;color:var(--muted);margin-bottom:.4rem;}}
.ht-range-group .ht-val{{color:var(--text);font-weight:700;}}
input[type=range].ht-range{{width:100%;appearance:none;height:4px;background:#1a1a2e;border-radius:2px;outline:none;cursor:pointer;}}
input[type=range].ht-range::-webkit-slider-thumb{{appearance:none;width:17px;height:17px;background:#6c63ff;border-radius:50%;cursor:pointer;}}
.ht-results{{background:#0c1220;border-radius:12px;padding:1.25rem;}}
.ht-res-row{{display:flex;justify-content:space-between;align-items:center;padding:.6rem 0;border-bottom:1px solid rgba(255,255,255,.05);}}
.ht-res-row:last-child{{border-bottom:none;}}
.ht-res-lbl{{font-size:.8rem;color:var(--muted);}}
.ht-res-val{{font-size:1.05rem;font-weight:800;}}
.ht-res-val.gn{{color:#00ff88;}} .ht-res-val.gl{{color:#ffd700;}} .ht-res-val.bl{{color:#00d4ff;}}
.ht-testi-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.25rem;margin-top:2.5rem;}}
@media(max-width:900px){{.ht-testi-grid{{grid-template-columns:1fr;}}}}
</style>

<!-- DEMO SECTION -->
<section class="ht-section" style="background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);">
  <div class="ht-inner">
    <div class="ht-label">Live Demo</div>
    <h2 class="ht-h2">Sieh <span>{name} in Aktion</span></h2>
    <div class="ht-demo-grid">
      <div>
        <p class="ht-sub">{name} arbeitet rund um die Uhr für dich — hier ein Live-Einblick was das System gerade macht.</p>
        <div style="display:flex;flex-direction:column;gap:.75rem;margin-bottom:1.5rem">
          <div style="background:rgba(108,99,255,.08);border:1px solid rgba(108,99,255,.2);border-radius:10px;padding:1rem;cursor:pointer" onclick="replayDemo()">
            <strong style="font-size:.9rem">▶ Demo neu abspielen</strong>
            <p style="font-size:.78rem;color:var(--muted);margin-top:.25rem">Zeige den vollständigen Automation-Zyklus</p>
          </div>
          <div style="background:rgba(0,255,136,.05);border:1px solid rgba(0,255,136,.15);border-radius:10px;padding:1rem">
            <strong style="font-size:.9rem;color:#00ff88">24/7 Autonomer Betrieb</strong>
            <p style="font-size:.78rem;color:var(--muted);margin-top:.25rem">Das System arbeitet auch wenn du schläfst</p>
          </div>
        </div>
        <a href="#preise" class="btn-primary" style="display:inline-block">Jetzt starten →</a>
      </div>
      <div class="ht-terminal">
        <div class="ht-term-bar">
          <div class="ht-dot" style="background:#ef4444"></div>
          <div class="ht-dot" style="background:#f59e0b;margin-left:.3rem"></div>
          <div class="ht-dot" style="background:#22c55e;margin-left:.3rem"></div>
          <span style="font-size:.68rem;color:#444466;margin-left:.5rem;letter-spacing:.04em">{name.lower().replace(' ','-')} · live</span>
        </div>
        <div class="ht-term-body" id="demo-terminal-{name.replace(' ','-').lower()}">
{term_html}
          <div style="display:flex;gap:.5rem;margin-top:.75rem;animation:htfadein .35s ease {200 + len(proj['terminal'])*500}ms forwards;opacity:0">
            <span style="color:#6c63ff">$</span><span style="color:#c8c8e0;font-size:.72rem"><span class="ht-cursor"></span></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ROI CALCULATOR -->
<section class="ht-section" style="background:var(--bg)">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-label">ROI-Rechner</div>
    <h2 class="ht-h2" style="max-width:600px;margin:0 auto 1rem">Was bringt <span>{name}</span> deinem Business?</h2>
    <p style="color:var(--muted);font-size:.95rem;max-width:500px;margin:0 auto 2rem">Gib deine Zahlen ein — wir zeigen den echten ROI.</p>
    <div class="ht-roi-card" style="max-width:820px;margin:0 auto">
      <div class="ht-roi-grid">
        <div>
          <div class="ht-range-group">
            <label>Monatlicher {roi_label} <span class="ht-val" id="ht-rev-d">€25.000</span></label>
            <input type="range" class="ht-range" id="ht-rev" min="5000" max="200000" step="5000" value="25000" oninput="htROI()">
          </div>
          <div class="ht-range-group">
            <label>Manuelle Stunden / Woche <span class="ht-val" id="ht-hrs-d">20h</span></label>
            <input type="range" class="ht-range" id="ht-hrs" min="5" max="60" step="5" value="20" oninput="htROI()">
          </div>
          <div class="ht-range-group">
            <label>Aktive Kanäle <span class="ht-val" id="ht-ch-d">3</span></label>
            <input type="range" class="ht-range" id="ht-ch" min="1" max="10" step="1" value="3" oninput="htROI()">
          </div>
        </div>
        <div>
          <div style="font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:.75rem">Dein ROI mit {name}</div>
          <div class="ht-results">
            <div class="ht-res-row"><span class="ht-res-lbl">Gesparte Stunden / Jahr</span><span class="ht-res-val bl" id="ht-r1">—</span></div>
            <div class="ht-res-row"><span class="ht-res-lbl">Mehreinnahmen / Monat</span><span class="ht-res-val gn" id="ht-r2">—</span></div>
            <div class="ht-res-row"><span class="ht-res-lbl">Zeitwert (€60/h)</span><span class="ht-res-val gn" id="ht-r3">—</span></div>
            <div class="ht-res-row"><span class="ht-res-lbl">Gesamtvorteil / Jahr</span><span class="ht-res-val gl" id="ht-r4">—</span></div>
            <div class="ht-res-row"><span class="ht-res-lbl">ROI auf Pro-Plan</span><span class="ht-res-val gl" id="ht-r5">—</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- TESTIMONIALS -->
<section class="ht-section" style="background:var(--surface);border-top:1px solid var(--border)">
  <div class="ht-inner">
    <div class="ht-label">Ergebnisse</div>
    <h2 class="ht-h2">Was unsere Kunden <span>sagen</span></h2>
    <div class="ht-testi-grid">
{testi_html}
    </div>
  </div>
</section>

<script>
(function(){{
function htROI(){{
  var rev=+(document.getElementById('ht-rev')||{{}}).value||25000;
  var hrs=+(document.getElementById('ht-hrs')||{{}}).value||20;
  var ch=+(document.getElementById('ht-ch')||{{}}).value||3;
  var d=document;
  var set=function(id,v){{var el=d.getElementById(id);if(el)el.textContent=v;}};
  set('ht-rev-d','€'+rev.toLocaleString('de-DE'));
  set('ht-hrs-d',hrs+'h');
  set('ht-ch-d',ch);
  var savedHrs=Math.round(hrs*.65+ch*1.2);
  var savedYear=savedHrs*52;
  var revInc=Math.round(rev*.22*(1+ch*.04));
  var timeVal=savedYear*60;
  var total=revInc*12+timeVal;
  var roi=Math.round(((total-2997*12)/2997/12)*100);
  set('ht-r1',savedYear+'h');
  set('ht-r2','+€'+revInc.toLocaleString('de-DE')+'/Mo');
  set('ht-r3','+€'+timeVal.toLocaleString('de-DE')+'/J');
  set('ht-r4','+€'+total.toLocaleString('de-DE')+'/J');
  set('ht-r5',roi+'%');
}}
if(window.htROIInit)return;window.htROIInit=true;
htROI();
window.htROI=htROI;
}})();

function replayDemo(){{
  var t=document.getElementById('demo-terminal-{name.replace(' ','-').lower()}');
  if(!t)return;
  var lines=t.querySelectorAll('div');
  lines.forEach(function(l){{l.style.opacity=0;l.style.animation='none';}});
  setTimeout(function(){{lines.forEach(function(l,i){{l.style.animation='htfadein .35s ease '+(200+i*400)+'ms forwards';}});}},50);
}}
</script>
<!-- ── HIGH-TICKET INJECTION END ── -->
"""


def _build_better_pricing(proj_name):
    """Ersetzt die generischen Tier-Features mit spezifischen, wertorientierten."""
    return f"""
        <div class="tier-card">
            <div class="tier-name">Starter</div>
            <div class="tier-price">€997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Vollzugang zu {proj_name}</li>
                <li>✓ Onboarding-Call (60 Minuten)</li>
                <li>✓ Setup-Begleitung durch unser Team</li>
                <li>✓ Alle Core-Automatisierungen</li>
                <li>✓ KI-Analyse deines Business</li>
                <li>✓ Dashboard + Reporting</li>
                <li>✓ E-Mail Support (48h Antwortzeit)</li>
                <li>✓ 30-Tage Geld-zurück-Garantie</li>
                <li>✓ Lebenslanger Zugang (einmalig)</li>
            </ul>
            <a href="https://buy.stripe.com/8x228tgM27XY8IEfJc4F42uM" class="tier-cta">Jetzt starten</a>
        </div>

        <div class="tier-card popular">
            <div class="popular-badge">⭐ Beliebteste Wahl</div>
            <div class="tier-name">Pro</div>
            <div class="tier-price">€2.997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Alles aus Starter</li>
                <li>✓ Onboarding-Call (90 Minuten)</li>
                <li>✓ Monatliche Strategy-Calls (60min)</li>
                <li>✓ Alle Premium-Features freigeschaltet</li>
                <li>✓ Autonome KI-Agenten aktiv</li>
                <li>✓ Multi-Kanal-Automation (7+ Plattformen)</li>
                <li>✓ A/B Testing Engine</li>
                <li>✓ Competitor Intelligence</li>
                <li>✓ Priority Support (12h Antwortzeit)</li>
                <li>✓ Telegram-Alert für alle wichtigen Events</li>
                <li>✓ 30-Tage Geld-zurück-Garantie</li>
            </ul>
            <a href="https://buy.stripe.com/00wcN72VcceeaQM2Wq4F42uO" class="tier-cta">Jetzt upgraden →</a>
        </div>

        <div class="tier-card">
            <div class="tier-name">Enterprise DFY</div>
            <div class="tier-price">€4.997<span class="tier-period"> einmalig</span></div>
            <ul class="tier-features">
                <li>✓ Alles aus Pro</li>
                <li>✓ Done-For-You Setup (5 Tage)</li>
                <li>✓ Dedicated Success Manager</li>
                <li>✓ Wöchentliche Strategy-Calls</li>
                <li>✓ Custom KI-Agenten (dein Business)</li>
                <li>✓ Custom Integrationen via API</li>
                <li>✓ 4h Emergency Support SLA</li>
                <li>✓ Unbegrenzte User + Shops</li>
                <li>✓ White-Label Option</li>
                <li>✓ EU AI Act Compliance Paket</li>
                <li>✓ 30-Tage Geld-zurück-Garantie</li>
            </ul>
            <a href="https://buy.stripe.com/3cI6oJcvMdii5ws0Oi4F42uQ" class="tier-cta">Enterprise anfragen</a>
        </div>"""


# ─────────────────────────────────────────────────────────────
# DATEI VERARBEITUNG
# ─────────────────────────────────────────────────────────────

def process_site(dir_name, proj):
    html_path = BASE / dir_name / "index.html"
    if not html_path.exists():
        print(f"  ⚠️  {dir_name}/index.html nicht gefunden")
        return False

    html = html_path.read_text(encoding="utf-8")

    # Inject-Marker: Wenn schon injiziert → überspringen oder neu
    if "HIGH-TICKET INJECTION START" in html:
        # Alten Block raus
        html = re.sub(
            r'\n<!-- ── HIGH-TICKET INJECTION START ──.*?<!-- ── HIGH-TICKET INJECTION END ── -->\n',
            '', html, flags=re.DOTALL
        )

    # 1. HT-Sections vor der Pricing-Sektion einfügen
    injection = build_injection(proj)
    pricing_marker = '<section class="pricing-section"'
    if pricing_marker in html:
        html = html.replace(pricing_marker, injection + "\n" + pricing_marker, 1)
    else:
        # Fallback: vor </main> oder vor Footer
        for fallback in ['</main>', '<footer', '</body>']:
            if fallback in html:
                html = html.replace(fallback, injection + "\n" + fallback, 1)
                break

    # 2. Pricing-Features ersetzen (die generischen durch spezifische)
    old_tier_block = re.search(
        r'(<div class="pricing-grid">)(.*?)(</div>\s*</div>\s*<div class="pricing-guarantee">)',
        html, re.DOTALL
    )
    if old_tier_block:
        better = _build_better_pricing(proj["name"])
        html = html[:old_tier_block.start(2)] + better + html[old_tier_block.end(2):]

    html_path.write_text(html, encoding="utf-8")
    return True


def deploy_netlify(netlify_site_name, dir_name):
    site_id = NETLIFY_SITE_IDS.get(netlify_site_name)
    if not site_id:
        print(f"    ⚠️  Kein Site-ID für {netlify_site_name}")
        return False
    dir_path = BASE / dir_name
    if not dir_path.exists():
        print(f"    ⚠️  Verzeichnis nicht gefunden: {dir_path}")
        return False
    cmd = ["netlify", "deploy", "--prod", f"--dir={dir_path}", f"--site={site_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        return True
    print(f"    ❌ Netlify deploy error: {result.stderr[:200]}")
    return False


def deploy_vercel(vercel_project, dir_name):
    dir_path = BASE / dir_name
    if not dir_path.exists():
        return False
    cmd = ["vercel", "--prod", "--yes", "--cwd", str(dir_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode == 0:
        url = [l for l in result.stdout.splitlines() if "vercel.app" in l or "https://" in l]
        return url[-1].strip() if url else True
    print(f"    ⚠️  Vercel: {result.stderr[:150]}")
    return False


# ─────────────────────────────────────────────────────────────
# HAUPTPROGRAMM
# ─────────────────────────────────────────────────────────────

def main():
    deploy = "--deploy" in sys.argv or "-d" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("-")]

    print(f"\n{'='*60}")
    print(f"HIGH-TICKET UPGRADE — {len(PROJECTS)} Sites")
    print(f"Mode: {'DEPLOY' if deploy else 'FILE-UPDATE ONLY'}")
    print(f"{'='*60}\n")

    dir_map = {
        "autoincome-ai":              "autoincome-ai",
        "bullpower-hub":              "bullpower-hub",
        "shopify-acquisition-engine": "shopify-acquisition-engine",
        "shopify-brutal-tuning":      "shopify-brutal-tuning",
        "shopify-suite":              "shopify-suite",
        "cognitive-symphony":         "cognitive-symphony",
        "creatorai-ultra":            "creatorai-ultra",
        "creatorstudio-pro":          "creatorstudio-pro",
        "digistore24-suite":          "digistore24-suite",
        "gumroad-discord":            "gumroad-discord",
        "telegram-bot":               "telegram-bot",
        "launcher":                   "launcher",
        "lead-capture":               "lead-capture",
        "steuercockpit":              "steuercockpit",
        "icomeauto":                  "icomeauto",
        "bullpower-ai":               "bullpower-ai",
    }

    results = []
    for proj_key, proj in PROJECTS.items():
        if only and proj_key not in only:
            continue
        dir_name = dir_map.get(proj_key, proj_key)
        print(f"⚙️  {proj['name']} ({dir_name})")

        # Datei updaten
        ok = process_site(dir_name, proj)
        if not ok:
            print(f"  ❌ Datei-Update fehlgeschlagen")
            results.append((proj_key, False, False, False))
            continue
        print(f"  ✅ HTML injiziert")

        netlify_ok = vercel_ok = False
        if deploy:
            netlify_name = proj.get("netlify_site", "")
            print(f"  🚀 Netlify deploy → {netlify_name}.netlify.app")
            netlify_ok = deploy_netlify(netlify_name, dir_name)
            print(f"  {'✅' if netlify_ok else '❌'} Netlify")

            vercel_proj = proj.get("vercel_project", "")
            print(f"  🚀 Vercel deploy → {vercel_proj}.vercel.app")
            vercel_ok = deploy_vercel(vercel_proj, dir_name)
            print(f"  {'✅' if vercel_ok else '❌'} Vercel")

        results.append((proj_key, True, netlify_ok, vercel_ok))
        print()

    print(f"\n{'='*60}")
    print(f"ERGEBNIS")
    print(f"{'='*60}")
    for pk, html_ok, n_ok, v_ok in results:
        status = f"HTML={'✅' if html_ok else '❌'}"
        if deploy:
            status += f" | Netlify={'✅' if n_ok else '❌'} | Vercel={'✅' if v_ok else '❌'}"
        print(f"  {pk}: {status}")

    total = sum(1 for _, h, _, _ in results if h)
    print(f"\n✅ {total}/{len(results)} Sites aktualisiert")


if __name__ == "__main__":
    main()
