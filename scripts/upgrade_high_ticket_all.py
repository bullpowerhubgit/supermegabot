#!/usr/bin/env python3
"""High-Ticket Vollupgrade — alle Landing Pages auf Premium-Niveau bringen.

Fügt ein für alle Seiten:
- ROI-Kalkulator (interaktiv, JS)
- Live Interactive Demo (Mock-Dashboard mit Tabs)
- Vergleichstabelle (vs. DIY / Konkurrenz)
- Urgency Strip (Countdown + Plätze)
- Trust & Garantie-Sektion (30-Tage, Stripe, EU)
- Erweiterte FAQ (Einwände + Antworten)
"""
import os
import re
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).parent.parent
NETLIFY = BASE / "netlify-deploy"
MARKER = "<!-- HT-UPGRADE-V2:DONE -->"

# ── Produkt-Konfiguration ──────────────────────────────────────────────────────
PRODUCTS = {
    "bullpower-ai": {
        "name": "BullPower AI",
        "tagline": "KI-Business-Automatisierung",
        "emoji": "🤖",
        "roi_input_label": "Aktuelle Monatsumsatz (€)",
        "roi_input_default": "5000",
        "roi_multiplier": 2.8,
        "roi_metric": "Umsatzsteigerung",
        "roi_time": "12 Wochen",
        "hours_saved": "40 Stunden/Monat",
        "demo_tabs": ["Dashboard", "KI-Analyse", "Automation", "Reports"],
        "demo_stats": [("€12.400", "Monatsumsatz"), ("94%", "Automation"), ("+340%", "Effizienz"), ("24/7", "Aktiv")],
        "compare_features": ["KI-Automatisierung", "Shopify-Integration", "Telegram-Bots", "Revenue-Tracking", "Auto-Posting", "AI-Content"],
        "pain": "Stunden mit manuellen Tasks verschwenden",
        "gain": "Alles läuft automatisch — du kassierst",
        "price_anchor": "€9.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/dRm7sN2Vcfqqe2Y2Wq4F42uF",
        "guarantee_days": 30,
        "faq": [
            ("Wie schnell sehe ich Ergebnisse?", "Typisch: erste KI-Automatisierungen laufen binnen 24h. Messbare Umsatzsteigerung nach 2-4 Wochen."),
            ("Brauche ich technisches Know-how?", "Nein. Das System richtet sich selbst ein. Du gibst Ziele vor — die KI erledigt den Rest."),
            ("Was wenn es nicht funktioniert?", "30-Tage Fair-Use Garantie. Wenn du nicht zufrieden bist, erstattung ohne Fragen."),
            ("Ist es kompatibel mit meinem Shopify?", "Ja. Native API-Integration — verbindet sich in unter 5 Minuten mit deinem Store."),
        ],
    },
    "bullpower-hub": {
        "name": "BullPower Hub",
        "tagline": "Complete Revenue Stack",
        "emoji": "🏆",
        "roi_input_label": "Aktueller Monatsumsatz (€)",
        "roi_input_default": "10000",
        "roi_multiplier": 3.5,
        "roi_metric": "Umsatzmultiplikator",
        "roi_time": "16 Wochen",
        "hours_saved": "80 Stunden/Monat",
        "demo_tabs": ["Revenue Hub", "Multi-Channel", "Analytics", "Automation"],
        "demo_stats": [("€47.200", "Monatsumsatz"), ("12", "Kanäle aktiv"), ("+520%", "Wachstum"), ("99.9%", "Uptime")],
        "compare_features": ["Multi-Channel-Automation", "KI-Revenue-Optimierung", "White-Label-Option", "Dedicated Support", "Custom Integrations", "Agency-Tools"],
        "pain": "Umsatzpotenzial auf dem Tisch liegen lassen",
        "gain": "Vollautomatisches Revenue-System — skaliert ohne Aufwand",
        "price_anchor": "€19.997",
        "price_real": "€2.997/mo",
        "buy_link": "https://buy.stripe.com/28EdRb1R8guu5wsfJc4F42uC",
        "guarantee_days": 30,
        "faq": [
            ("Für wen ist BullPower Hub?", "Für ambitionierte E-Commerce-Unternehmer die €10k+/Mo machen und auf €50k+ skalieren wollen."),
            ("Was unterscheidet Hub von BullPower AI?", "Hub ist das komplette Paket: alle Tools, alle Integrationen, White-Label + dedizierter Account Manager."),
            ("Gibt es eine Setup-Gebühr?", "Nein. Monatliche Flat-Rate inkl. vollständigem Onboarding und Setup-Call."),
            ("Kann ich jederzeit kündigen?", "Ja. Monatlich kündbar, keine Mindestlaufzeit."),
        ],
    },
    "autoincome-ai": {
        "name": "AutoIncome AI",
        "tagline": "Passive Income Machine",
        "emoji": "💰",
        "roi_input_label": "Gewünschtes Monatseinkommen (€)",
        "roi_input_default": "3000",
        "roi_multiplier": 4.2,
        "roi_metric": "Passives Einkommen",
        "roi_time": "8 Wochen",
        "hours_saved": "50 Stunden/Monat",
        "demo_tabs": ["Income Streams", "DS24 Affiliate", "Automation", "Cashflow"],
        "demo_stats": [("€8.400", "Passiv/Monat"), ("14", "Income-Quellen"), ("50%", "Provision DS24"), ("0h", "Manueller Aufwand")],
        "compare_features": ["DS24-Affiliate-System", "Automatische Produkterstellung", "Multi-Channel-Traffic", "KI-Content-Produktion", "Einmal zahlen — immer verdienen", "Komplettes DFY-Setup"],
        "pain": "Aktiv Zeit gegen Geld tauschen",
        "gain": "Einmal einrichten — passiv verdienen während du schläfst",
        "price_anchor": "€14.997",
        "price_real": "€2.997 einmalig",
        "buy_link": "https://buy.stripe.com/00wcN72VcceeaQM2Wq4F42uO",
        "guarantee_days": 30,
        "faq": [
            ("Wie viel kann ich realistisch verdienen?", "Unsere Kunden erzielen im Schnitt €2.800-€8.400/Mo nach Vollbetrieb (8-12 Wochen). Ergebnisse variieren."),
            ("Muss ich vorher schon Follower haben?", "Nein. Das System baut Traffic-Quellen auf — du brauchst null Startkapital außer diesem Investment."),
            ("Was passiert nach dem Kauf?", "Sofortiger Zugang + 1:1 Onboarding-Call. DFY Setup in 72h abgeschlossen."),
            ("Ist das Dropshipping?", "Nein. Digitale Produkte + Affiliate — kein Lager, kein Versand, kein Kundensupport."),
        ],
    },
    "creatorai-ultra": {
        "name": "CreatorAI Ultra",
        "tagline": "KI Content Empire",
        "emoji": "✨",
        "roi_input_label": "Aktueller Content-Aufwand (h/Monat)",
        "roi_input_default": "80",
        "roi_multiplier": 10,
        "roi_metric": "Content-Output-Steigerung",
        "roi_time": "4 Wochen",
        "hours_saved": "70 Stunden/Monat",
        "demo_tabs": ["Content Hub", "KI-Produktion", "Multi-Platform", "Analytics"],
        "demo_stats": [("2.400", "Posts/Monat"), ("8", "Plattformen"), ("€0.08", "Pro Post"), ("100%", "KI-generiert")],
        "compare_features": ["KI-Textgenerierung", "Video-Skripte", "Social Media Automation", "SEO-Optimierung", "Brand Voice Training", "Massenproduktion"],
        "pain": "Stunden an Content-Erstellung verschwenden",
        "gain": "2.400 Posts/Monat auf Autopilot — ohne Schreiben",
        "price_anchor": "€7.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/bJe00l8fwcee0c81Sm4F42uW",
        "guarantee_days": 30,
        "faq": [
            ("Ist der Content wirklich gut?", "KI wird mit deiner Brand Voice trainiert — der Output klingt wie du, nur 100x schneller."),
            ("Welche Plattformen werden bedient?", "Instagram, TikTok, YouTube, LinkedIn, Facebook, Pinterest, Twitter/X, Telegram."),
            ("Wie lange bis erste Ergebnisse?", "Erste Posts live in 24h. Messbare Follower-Wachstum nach 2-3 Wochen."),
            ("Brauche ich eigene KI-API-Keys?", "Nein. Alles inklusive — KI-Kapazität + alle Tools in einem Paket."),
        ],
    },
    "creatorstudio-pro": {
        "name": "CreatorStudio Pro",
        "tagline": "Premium Content Engine",
        "emoji": "🎬",
        "roi_input_label": "Monatliche Content-Kosten (€)",
        "roi_input_default": "2000",
        "roi_multiplier": 5,
        "roi_metric": "Einsparung vs Agentur",
        "roi_time": "6 Wochen",
        "hours_saved": "45 Stunden/Monat",
        "demo_tabs": ["Studio", "Video-KI", "Brand Assets", "Publish"],
        "demo_stats": [("500+", "Assets/Monat"), ("€12", "Pro Video"), ("98%", "Brand Konsistenz"), ("∞", "Skalierung")],
        "compare_features": ["Video-Produktion KI", "Thumbnail-Generierung", "Brand Kit Builder", "Auto-Publish", "Caption-Generator", "Analytics Dashboard"],
        "pain": "€3.000-€10.000/Mo für Content-Agenturen zahlen",
        "gain": "Professioneller Studio-Output für €197/mo",
        "price_anchor": "€5.997",
        "price_real": "€697/mo",
        "buy_link": "https://buy.stripe.com/4gM28tanE4LM7EA2Wq4F42uP",
        "guarantee_days": 30,
        "faq": [
            ("Welche Formate werden generiert?", "Videos (Skript+Voiceover), Grafiken, Posts, Stories, Thumbnails, PDFs."),
            ("Muss ich selbst filmen?", "Nein. KI-Avatare und Slideshow-Videos verfügbar. Kein Studio nötig."),
            ("Wie ist die Content-Qualität?", "Vergleichbar mit professionellen Agenturen — trainiert auf High-Engagement-Content."),
            ("Gibt es ein Limit an Output?", "Nein. Unlimited Content im Plan inkludiert."),
        ],
    },
    "cognitive-symphony": {
        "name": "DS24 Pro Suite",
        "tagline": "Digistore24 Empire",
        "emoji": "💎",
        "roi_input_label": "Aktuell Affiliate-Einnahmen (€/Mo)",
        "roi_input_default": "0",
        "roi_multiplier": 8,
        "roi_metric": "Affiliate-Potenzial",
        "roi_time": "10 Wochen",
        "hours_saved": "60 Stunden/Monat",
        "demo_tabs": ["DS24 Hub", "Produkt-Finder", "Traffic", "Revenue"],
        "demo_stats": [("449", "DS24 Produkte"), ("50%", "Max. Provision"), ("€8.400", "Affiliat/Mo"), ("100%", "Automatisiert")],
        "compare_features": ["DS24 Account-Integration", "Auto-Affiliate-Kampagnen", "Produkt-Research-KI", "Traffic-Automation", "Email-Sequenzen", "Revenue-Tracking"],
        "pain": "Affiliate-Marketing manuell betreiben",
        "gain": "Vollautomatisches DS24 Empire — KI übernimmt alles",
        "price_anchor": "€8.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/6oU28t8fwcee7EA9kO4F42fD",
        "guarantee_days": 30,
        "faq": [
            ("Brauche ich eigene DS24-Produkte?", "Nein. Du startest als Affiliate — wir finden die besten Produkte mit 50% Provision für dich."),
            ("Wie viel kann ich realistisch verdienen?", "€2.000-€12.000/Mo ist realistisch nach 8-12 Wochen Vollbetrieb."),
            ("Ist DS24 legal in Deutschland?", "Ja. Digistore24 ist ein reguliertes Zahlungsunternehmen mit vollständigem EU-Compliance."),
            ("Wie oft wird das System geupdated?", "Wöchentliche Updates — neue Top-Produkte werden automatisch integriert."),
        ],
    },
    "shopify-suite": {
        "name": "Shopify Suite Pro",
        "tagline": "Enterprise E-Commerce Automation",
        "emoji": "🛒",
        "roi_input_label": "Aktueller Shopify-Umsatz (€/Mo)",
        "roi_input_default": "5000",
        "roi_multiplier": 3.2,
        "roi_metric": "Umsatz nach Optimierung",
        "roi_time": "8 Wochen",
        "hours_saved": "35 Stunden/Monat",
        "demo_tabs": ["Shop-Dashboard", "Produkt-KI", "Marketing", "Analytics"],
        "demo_stats": [("10.752", "Produkte live"), ("+340%", "Conversion"), ("€0.02", "Pro Produkt"), ("24/7", "Auto-Sync")],
        "compare_features": ["Automatischer Produkt-Import", "SEO-Optimierung KI", "Pricing-Automation", "Inventory-Sync", "Marketing-Automation", "Multi-Channel"],
        "pain": "Shopify manuell pflegen — tage-lange Arbeit",
        "gain": "10.000+ Produkte automatisch — du fokussierst auf Sales",
        "price_anchor": "€6.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/5kQ28teDUcee8IE0Oi4F42uG",
        "guarantee_days": 30,
        "faq": [
            ("Funktioniert das mit meinem bestehenden Shopify?", "Ja. Nahtlose Integration — keine Migration nötig."),
            ("Wie viele Produkte kann ich importieren?", "Unlimited. Unser System verwaltet Stores mit 10.000+ Produkten problemlos."),
            ("Überschreibt das meine bestehenden Produkte?", "Nein. Saubere Duplikat-Erkennung — bestehende Produkte bleiben unberührt."),
            ("Welche Produktquellen werden unterstützt?", "AliExpress, Amazon, eBay, eigene Lieferanten via CSV — alles automatisch."),
        ],
    },
    "shopify-brutal-tuning": {
        "name": "Shopify Brutal Tuning",
        "tagline": "Conversion Rate Maximizer",
        "emoji": "🚀",
        "roi_input_label": "Aktueller monatlicher Traffic (Besucher)",
        "roi_input_default": "5000",
        "roi_multiplier": 3.8,
        "roi_metric": "Conversions nach Tuning",
        "roi_time": "6 Wochen",
        "hours_saved": "30 Stunden/Monat",
        "demo_tabs": ["CRO-Dashboard", "A/B Testing", "Speed", "Revenue"],
        "demo_stats": [("4.8%", "Conversion Rate"), ("+340%", "Revenue"), ("0.8s", "Ladezeit"), ("€0", "Setup-Gebühr")],
        "compare_features": ["A/B Testing Automation", "Page Speed Optimizer", "Checkout Optimierung", "Heatmap Analytics", "Cart Recovery", "Trust Badges"],
        "pain": "95% der Besucher kaufen nicht",
        "gain": "4.8% Conversion Rate — 3x mehr Umsatz gleicher Traffic",
        "price_anchor": "€7.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/aFa9AV9jA2DEcYU54y4F42Du",
        "guarantee_days": 30,
        "faq": [
            ("Wie viel bringt 1% mehr Conversion?", "Bei €5.000 Monatsumsatz und 5.000 Besuchern = €1.000 mehr pro Monat. Messbar in Woche 2."),
            ("Muss ich den Theme-Code anfassen?", "Nein. Plugin-basiert — keine Programmierung erforderlich."),
            ("Ist das kompatibel mit Shopify 2.0?", "Ja. Vollständig optimiert für alle Shopify-Versionen inkl. OS 2.0."),
            ("Wie werden A/B Tests ausgewertet?", "Automatisch — KI ermittelt den Gewinner nach statistischer Signifikanz."),
        ],
    },
    "shopify-acquisition-engine": {
        "name": "Shopify Acquisition Engine",
        "tagline": "Automatische Kundengewinnung",
        "emoji": "🎯",
        "roi_input_label": "Aktueller Kunden-Akquisekosten (€/Kunde)",
        "roi_input_default": "45",
        "roi_multiplier": 0.3,
        "roi_metric": "Neue Akquisekosten",
        "roi_time": "8 Wochen",
        "hours_saved": "25 Stunden/Monat",
        "demo_tabs": ["Lead-Pipeline", "Traffic-Quellen", "Automation", "ROI"],
        "demo_stats": [("€12", "Akquise/Kunde"), ("450+", "Leads/Monat"), ("4.2x", "ROAS"), ("0h", "Manuelle Arbeit")],
        "compare_features": ["Multi-Channel Lead-Gen", "Retargeting-Automation", "Email-Sequenzen", "SMS-Followup", "Lookalike Audiences", "Attribution Tracking"],
        "pain": "€45+ pro Neukunde zahlen — teuer und unkontrolliert",
        "gain": "€12 pro Neukunde automatisch — skalierbar ohne Limit",
        "price_anchor": "€7.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/cNi28t2Vc5PQ4so1Sm4F42Dx",
        "guarantee_days": 30,
        "faq": [
            ("Welche Traffic-Kanäle werden genutzt?", "Meta Ads, Google Ads, SEO, Email, SMS, Organic Social — alles koordiniert."),
            ("Brauche ich ein Meta Ads Konto?", "Ja — aber wir helfen beim Setup und optimieren alles automatisch."),
            ("Wie schnell sehe ich Leads?", "Erste Leads in 48-72h nach Go-Live der Kampagnen."),
            ("Was ist der minimale Ad-Spend?", "Wir empfehlen €300-€500/Mo Ad-Budget für optimale Ergebnisse."),
        ],
    },
    "digistore24-suite": {
        "name": "Digistore24 Suite",
        "tagline": "Affiliate & Digital Products Empire",
        "emoji": "📦",
        "roi_input_label": "Ziel-Monatseinkommen DS24 (€)",
        "roi_input_default": "2000",
        "roi_multiplier": 4,
        "roi_metric": "Erreichbares DS24-Einkommen",
        "roi_time": "10 Wochen",
        "hours_saved": "55 Stunden/Monat",
        "demo_tabs": ["Produkt-Hub", "Affiliate-Links", "Traffic", "Auszahlungen"],
        "demo_stats": [("449", "Verfügbar"), ("50%", "Provision"), ("€6.200", "Best Month"), ("Täglich", "Auszahlung")],
        "compare_features": ["DS24 Auto-Integration", "Affiliate-Link-Generator", "Traffic-Automation", "Sales-Funnel-Builder", "Email-Marketing", "Conversion-Tracking"],
        "pain": "Stunden mit Produkt-Recherche und manuellen Kampagnen verbringen",
        "gain": "KI findet Top-Produkte + alle Kampagnen laufen automatisch",
        "price_anchor": "€5.997",
        "price_real": "€497/mo",
        "buy_link": "https://buy.stripe.com/cNi28tgM2dii9MIfJc4F42fD",
        "guarantee_days": 30,
        "faq": [
            ("Was ist Digistore24?", "Größte deutsche Plattform für digitale Produkte — Affiliate-System mit bis zu 75% Provision."),
            ("Brauche ich eigene Produkte?", "Nein. Starte als Affiliate — wir automatisieren alles für dich."),
            ("Ist das nachhaltig?", "Ja. Digitale Produkte — kein Lager, kein Versand. Margin bleibt konstant."),
            ("Wie oft gibt es Updates?", "Wöchentlich — neue Trendprodukte werden automatisch hinzugefügt."),
        ],
    },
    "steuercockpit": {
        "name": "SteuercockPit Pro",
        "tagline": "KI-Steuerautomation für E-Commerce",
        "emoji": "📊",
        "roi_input_label": "Aktueller Steuerberater-Kosten (€/Jahr)",
        "roi_input_default": "4800",
        "roi_multiplier": 0.25,
        "roi_metric": "Neue Steuerkosten/Jahr",
        "roi_time": "4 Wochen",
        "hours_saved": "20 Stunden/Monat",
        "demo_tabs": ["Steuer-Dashboard", "Belege", "Reports", "EU Compliance"],
        "demo_stats": [("€1.200", "vs €4.800 Steuerberater"), ("100%", "EU-Konform"), ("Echtzeit", "Buchhaltung"), ("0", "Fehler"), ],
        "compare_features": ["Automatische Belegerkennung", "E-Rechnung (ZUGFeRD)", "EU OSS-Konformität", "Shopify-Sync", "Steuer-Reports", "DATEV-Export"],
        "pain": "€4.800/Jahr Steuerberater + stundenlange Buchführung",
        "gain": "€1.200/Jahr — alles automatisch, 100% compliant",
        "price_anchor": "€3.997",
        "price_real": "€497/mo",
        "buy_link": "https://buy.stripe.com/cNi4gBgM23HI1gcfJc4F42Dr",
        "guarantee_days": 30,
        "faq": [
            ("Ersetzt das meinen Steuerberater komplett?", "Für E-Commerce-spezifische Aufgaben ja — komplexe Sonderfälle weiterhin mit Steuerberater abstimmen."),
            ("Ist der Export DATEV-kompatibel?", "Ja. Vollständiger DATEV-Export für deinen Steuerberater falls gewünscht."),
            ("Unterstützt das EU OSS?", "Ja. Vollständige OSS-Konformität für alle EU-Länder automatisch."),
            ("Wie lange dauert das Onboarding?", "Shopify-Verbindung in 5 Minuten. Erste Reports in 24h."),
        ],
    },
    "telegram-bot": {
        "name": "Telegram Agency Bot",
        "tagline": "Subscription-Empire auf Autopilot",
        "emoji": "📱",
        "roi_input_label": "Geplante Abo-Mitglieder",
        "roi_input_default": "200",
        "roi_multiplier": 29,
        "roi_metric": "MRR mit €29/Mitglied",
        "roi_time": "6 Wochen",
        "hours_saved": "30 Stunden/Monat",
        "demo_tabs": ["Bot-Studio", "Abonnenten", "Content", "Earnings"],
        "demo_stats": [("€5.800", "MRR bei 200 Mitgl."), ("24/7", "Bot aktiv"), ("0s", "Reaktionszeit"), ("∞", "Skalierbar")],
        "compare_features": ["Telegram Bot Builder", "Abo-Management", "Zahlungs-Integration", "Auto-Content", "Member-Gate", "Analytics"],
        "pain": "Manuell Abo-Mitglieder verwalten und Content posten",
        "gain": "Vollautomatisches Telegram-Abo — Bot macht alles",
        "price_anchor": "€4.997",
        "price_real": "€797/mo",
        "buy_link": "https://buy.stripe.com/7sY6oJ3Zg5PQ4sofJc4F42DA",
        "guarantee_days": 30,
        "faq": [
            ("Brauche ich Programmierkenntnisse?", "Null. Bot-Builder ohne Code — komplett No-Code Setup."),
            ("Welche Zahlungsmethoden werden unterstützt?", "Stripe, PayPal, Krypto — alles automatisch verarbeitet."),
            ("Kann ich mehrere Bots betreiben?", "Ja. Unlimited Bots im Agency-Plan."),
            ("Wie vermeide ich Telegram-Sperren?", "Unser System beachtet alle Telegram-Limits automatisch — keine manuellen Fehler."),
        ],
    },
    "icomeauto": {
        "name": "IcomeAuto OS",
        "tagline": "Vollautomatisches Income Operating System",
        "emoji": "⚙️",
        "roi_input_label": "Gewünschtes Ziel-Einkommen (€/Mo)",
        "roi_input_default": "5000",
        "roi_multiplier": 3.5,
        "roi_metric": "Erreichbares Einkommen",
        "roi_time": "12 Wochen",
        "hours_saved": "65 Stunden/Monat",
        "demo_tabs": ["Income OS", "Streams", "Automation", "Growth"],
        "demo_stats": [("7", "Income Streams"), ("€0", "Aktiver Aufwand"), ("+280%", "Wachstum"), ("24/7", "System läuft")],
        "compare_features": ["Multi-Stream-Automation", "KI-Revenue-Optimierung", "Passive Income Builder", "Cross-Channel-Sync", "Auto-Scale", "Dashboard"],
        "pain": "Jede Income-Quelle manuell managen",
        "gain": "Ein System — alle Einkommensquellen automatisch",
        "price_anchor": "€9.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/dRm7sNanE5PQ3ok1Sm4F42DG",
        "guarantee_days": 30,
        "faq": [
            ("Was sind Income Streams?", "Affiliate, Shopify, digitale Produkte, Services, Abo-Modelle — wir optimieren alle automatisch."),
            ("Kann ich mit einem Stream starten?", "Ja. IcomeAuto wächst mit dir — starte mit einem, skaliere auf 7+."),
            ("Wie lange bis das System profitabel ist?", "Typisch 8-12 Wochen bis Break-Even, danach exponentielles Wachstum."),
            ("Gibt es monatliche Zusatzkosten?", "Nein. Flat Monthly — alle Tools, API-Kapazität und Updates inklusive."),
        ],
    },
    "launcher": {
        "name": "BullPower Launcher",
        "tagline": "Agency-Suite für skalierbare Dienstleistung",
        "emoji": "🚀",
        "roi_input_label": "Geplante Agency-Kunden",
        "roi_input_default": "5",
        "roi_multiplier": 997,
        "roi_metric": "MRR bei €997/Kunde",
        "roi_time": "8 Wochen",
        "hours_saved": "100 Stunden/Monat",
        "demo_tabs": ["Agency Hub", "Kunden", "Deliverables", "Billing"],
        "demo_stats": [("€4.985", "MRR bei 5 Kunden"), ("White-Label", "Deine Brand"), ("∞", "Skalierbar"), ("0h", "Extraaufwand")],
        "compare_features": ["White-Label-Option", "Multi-Client-Dashboard", "Automatische Deliverables", "Reporting-Tools", "Billing-Automation", "Resell-Lizenz"],
        "pain": "Jede Agentur-Leistung manuell produzieren",
        "gain": "KI produziert alles — du lieferst, verkaufst, kassierst",
        "price_anchor": "€14.997",
        "price_real": "€2.997/mo",
        "buy_link": "https://buy.stripe.com/00wcN71R87XYcYU8gK4F42DJ",
        "guarantee_days": 30,
        "faq": [
            ("Kann ich das unter meiner Brand verkaufen?", "Ja. Vollständiges White-Label — du bist die Brand, Kunden sehen unsere Technik nicht."),
            ("Welche Dienstleistungen kann ich anbieten?", "KI-Marketing, E-Commerce-Automation, Content, Ads, SEO, Shopify-Management."),
            ("Brauche ich technisches Know-how?", "Nein. Wir trainieren dich in 2 Stunden — danach lieferst du Premium-Ergebnisse."),
            ("Wie viele Kunden kann ich betreuen?", "Unlimited. System skaliert automatisch mit deiner Kundenzahl."),
        ],
    },
    "lead-capture": {
        "name": "Lead Capture Pro",
        "tagline": "B2B Lead Generation auf Autopilot",
        "emoji": "🎯",
        "roi_input_label": "Aktueller Neukunden/Monat",
        "roi_input_default": "5",
        "roi_multiplier": 8,
        "roi_metric": "Qualifizierte Leads/Monat",
        "roi_time": "6 Wochen",
        "hours_saved": "40 Stunden/Monat",
        "demo_tabs": ["Lead-Hub", "Qualifizierung", "Outreach", "Pipeline"],
        "demo_stats": [("40+", "Leads/Monat"), ("85%", "Qualifizierungsrate"), ("€120", "Lead-Kosten"), ("KI", "Qualifizierung")],
        "compare_features": ["Automatische Lead-Recherche", "KI-Qualifizierung", "Multi-Channel-Outreach", "CRM-Integration", "Follow-Up-Automation", "Analytics"],
        "pain": "Stunden mit manueller Kaltakquise und Lead-Suche",
        "gain": "40+ qualifizierte Leads/Monat — automatisch geliefert",
        "price_anchor": "€4.997",
        "price_real": "€997/mo",
        "buy_link": "https://buy.stripe.com/aFacN7anEbaacYUaoS4F42DM",
        "guarantee_days": 30,
        "faq": [
            ("Welche Branchen werden unterstützt?", "E-Commerce, SaaS, Coaching, Agenturen, Berater — jede B2B-Nische funktioniert."),
            ("Wie werden Leads qualifiziert?", "KI prüft: Unternehmensgröße, Budget-Signale, Technologie-Stack, Kaufabsicht."),
            ("Verletzt das DSGVO?", "Nein. Alle Outreach-Methoden DSGVO-konform — kein Spam, nur relevante Ansprache."),
            ("Welche CRM-Systeme sind kompatibel?", "Pipedrive, HubSpot, Salesforce, Notion, Airtable — via API oder CSV-Export."),
        ],
    },
    "gumroad-discord": {
        "name": "Gumroad Discord Empire",
        "tagline": "Digitale Community monetarisieren",
        "emoji": "💫",
        "roi_input_label": "Community-Mitglieder (aktuell)",
        "roi_input_default": "500",
        "roi_multiplier": 15,
        "roi_metric": "MRR bei 3% Conversion",
        "roi_time": "8 Wochen",
        "hours_saved": "25 Stunden/Monat",
        "demo_tabs": ["Gumroad Shop", "Discord Gate", "Products", "Revenue"],
        "demo_stats": [("€15-€97", "Produktpreise"), ("3%", "Conv. Rate"), ("€2.250", "MRR 500 Mitgl."), ("Auto", "Delivery")],
        "compare_features": ["Gumroad-Automatisierung", "Discord-Gate-Integration", "Digitale Produkte", "Membership-System", "Auto-Delivery", "Analytics"],
        "pain": "Manuell Produkte erstellen und Community monetarisieren",
        "gain": "Automatische Gumroad-Produkte + Discord-Gate = passives Einkommen",
        "price_anchor": "€3.997",
        "price_real": "€297/mo",
        "buy_link": "https://buy.stripe.com/eVq28t8fw7XY9MIgNg4F42DD",
        "guarantee_days": 30,
        "faq": [
            ("Welche Produkte verkauft das System?", "PDFs, Templates, Kurse, Presets, Tools — alles automatisch generiert."),
            ("Brauche ich eine eigene Community?", "Nein. Das System hilft auch beim Aufbau von Discord/Telegram-Communities."),
            ("Wie läuft die Discord-Integration?", "Automatischer Role-Assign nach Kauf — Mitglieder erhalten sofort Zugang."),
            ("Wie viel kann ich mit 500 Followern verdienen?", "Bei 3% Conversion und €15/Produkt: €225/Mo passiv — skaliert mit Wachstum."),
        ],
    },
    "master-dashboard": {
        "name": "Master Revenue Dashboard",
        "tagline": "All-in-One Revenue Intelligence",
        "emoji": "📈",
        "roi_input_label": "Anzahl aktiver Revenue-Kanäle",
        "roi_input_default": "3",
        "roi_multiplier": 1800,
        "roi_metric": "Übersicht Revenue (€/Mo)",
        "roi_time": "Sofort",
        "hours_saved": "20 Stunden/Monat",
        "demo_tabs": ["Übersicht", "Kanalanalyse", "KI-Insights", "Forecasts"],
        "demo_stats": [("12", "Revenue-Kanäle"), ("Echtzeit", "Updates"), ("KI", "Prognosen"), ("+42%", "Optimierung")],
        "compare_features": ["Multi-Kanal-Dashboard", "KI-Prognosen", "Anomalie-Erkennung", "P&L Reporting", "Benchmark-Vergleich", "Custom Alerts"],
        "pain": "Umsatzdaten aus 10 Quellen manuell zusammenführen",
        "gain": "Alle Revenue-Daten in Echtzeit — KI zeigt wo Geld liegt",
        "price_anchor": "€3.997",
        "price_real": "€497/mo",
        "buy_link": "https://buy.stripe.com/8x2aEZ2Vc1zA1gceF84F42uR",
        "guarantee_days": 30,
        "faq": [
            ("Welche Plattformen werden verbunden?", "Shopify, Stripe, DS24, Gumroad, Amazon, eBay, PayPal — über 30 Integrationen."),
            ("Wie aktuell sind die Daten?", "Echtzeit für Stripe/Shopify, stündlich für andere Plattformen."),
            ("Kann ich eigene KPIs definieren?", "Ja. Custom Dashboard mit drag-and-drop Widgets."),
            ("Gibt es ein Alert-System?", "Ja. Telegram/Email-Alerts bei Umsatzeinbrüchen, Anomalien oder Zielerreichung."),
        ],
    },
}


def _generate_ht_sections(product_key: str) -> str:
    p = PRODUCTS.get(product_key)
    if not p:
        # Generic fallback
        p = {
            "name": product_key.replace("-", " ").title(),
            "tagline": "Premium Business Automation",
            "emoji": "⚡",
            "roi_input_label": "Aktueller Monatsumsatz (€)",
            "roi_input_default": "5000",
            "roi_multiplier": 3.0,
            "roi_metric": "Potenzial nach Optimierung",
            "roi_time": "8 Wochen",
            "hours_saved": "40 Stunden/Monat",
            "demo_tabs": ["Dashboard", "Analytics", "Automation", "Reports"],
            "demo_stats": [("3x", "Wachstum"), ("80%", "Automation"), ("+250%", "Effizienz"), ("24/7", "Aktiv")],
            "compare_features": ["KI-Automatisierung", "Analytics", "Integration", "Support", "Updates", "Training"],
            "pain": "Manuell alles selbst machen",
            "gain": "Vollautomatisch auf Autopilot",
            "price_anchor": "€9.997",
            "price_real": "€997/mo",
            "buy_link": "https://ineedit.com.co",
            "guarantee_days": 30,
            "faq": [
                ("Wie schnell sehe ich Ergebnisse?", "Erste Ergebnisse in 1-2 Wochen. Vollbetrieb nach 4-6 Wochen."),
                ("Gibt es technischen Support?", "Ja. Priority Email + Telegram Support inklusive."),
                ("Kann ich jederzeit kündigen?", "Ja. Monatlich kündbar, keine Mindestlaufzeit."),
                ("Ist das sicher?", "Ja. Alle Daten verschlüsselt, DSGVO-konform, Stripe-Zahlung."),
            ],
        }

    name = p["name"]
    emoji = p["emoji"]
    tabs_html = "".join(
        f'<button class="ht-tab {"ht-tab-active" if i == 0 else ""}" onclick="htTab(this,{i})">{t}</button>'
        for i, t in enumerate(p["demo_tabs"])
    )
    stats_html = "".join(
        f'<div class="ht-stat"><div class="ht-stat-num">{val}</div><div class="ht-stat-lbl">{lbl}</div></div>'
        for val, lbl in p["demo_stats"]
    )
    feature_rows = "".join(
        f"""<tr>
          <td style="padding:.6rem .8rem;border-bottom:1px solid rgba(255,255,255,.06)">{feat}</td>
          <td style="padding:.6rem;text-align:center;color:#ef4444;border-bottom:1px solid rgba(255,255,255,.06)">✗</td>
          <td style="padding:.6rem;text-align:center;color:#f59e0b;border-bottom:1px solid rgba(255,255,255,.06)">△</td>
          <td style="padding:.6rem;text-align:center;color:#10b981;border-bottom:1px solid rgba(255,255,255,.06)">✓</td>
        </tr>"""
        for feat in p["compare_features"]
    )
    faq_html = "".join(
        f"""<div class="ht-faq-item" onclick="this.classList.toggle('open')">
          <div class="ht-faq-q">{q} <span class="ht-faq-arrow">▾</span></div>
          <div class="ht-faq-a">{a}</div>
        </div>"""
        for q, a in p["faq"]
    )

    buy_link = p["buy_link"]
    price_anchor = p["price_anchor"]
    price_real = p["price_real"]
    pain = p["pain"]
    gain = p["gain"]
    roi_label = p["roi_input_label"]
    roi_default = p["roi_input_default"]
    roi_mult = p["roi_multiplier"]
    roi_metric = p["roi_metric"]
    roi_time = p["roi_time"]
    hours_saved = p["hours_saved"]
    tagline = p["tagline"]
    guarantee_days = p["guarantee_days"]

    return f"""
<!-- HT-UPGRADE-V2:DONE -->
<style>
/* ── High-Ticket Upgrade Styles ── */
.ht-section{{position:relative;z-index:2;padding:80px 1.5rem}}
.ht-inner{{max-width:1100px;margin:0 auto}}
.ht-badge{{display:inline-block;padding:.35rem 1rem;border-radius:999px;background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.4);color:#a78bfa;font-weight:700;font-size:.78rem;letter-spacing:.06em;margin-bottom:1.2rem}}
.ht-title{{font-size:clamp(1.9rem,3vw,2.7rem);font-weight:900;color:#fff;margin:0 0 .8rem;line-height:1.2}}
.ht-sub{{color:#a1a1aa;font-size:1.05rem;line-height:1.65;max-width:640px;margin:0 auto 2.5rem}}
/* Demo Tabs */
.ht-tabs{{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:center;margin-bottom:2rem}}
.ht-tab{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:#a1a1aa;padding:.55rem 1.2rem;border-radius:8px;cursor:pointer;font-size:.88rem;font-weight:600;transition:all .2s}}
.ht-tab-active,.ht-tab:hover{{background:rgba(124,58,237,.25);border-color:rgba(124,58,237,.6);color:#e9d5ff}}
.ht-demo-card{{background:#12121e;border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:2rem;margin-top:1rem;min-height:280px}}
.ht-stats-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1rem;margin-top:1.5rem}}
.ht-stat{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:1.2rem;text-align:center}}
.ht-stat-num{{font-size:1.8rem;font-weight:900;background:linear-gradient(135deg,#a78bfa,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.ht-stat-lbl{{font-size:.78rem;color:#71717a;margin-top:.3rem}}
/* ROI Calc */
.ht-roi-card{{background:linear-gradient(135deg,#1a1028,#0f1a2e);border:1px solid rgba(124,58,237,.3);border-radius:20px;padding:2.5rem;margin-top:2rem}}
.ht-roi-input{{width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);color:#fff;padding:.85rem 1.2rem;border-radius:10px;font-size:1.1rem;font-weight:600;outline:none;margin:.5rem 0 1.5rem}}
.ht-roi-result{{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.35);border-radius:12px;padding:1.5rem;text-align:center}}
.ht-roi-big{{font-size:2.8rem;font-weight:900;color:#34d399}}
.ht-roi-info{{color:#a1a1aa;font-size:.9rem;margin-top:.5rem}}
/* Comparison */
.ht-compare-table{{width:100%;border-collapse:collapse;font-size:.9rem;color:#d4d4d8}}
.ht-compare-table th{{padding:.8rem;font-weight:700;font-size:.8rem;letter-spacing:.05em;color:#a1a1aa;border-bottom:2px solid rgba(255,255,255,.1)}}
.ht-compare-table th:last-child{{color:#a78bfa}}
/* Urgency */
.ht-urgency{{background:linear-gradient(135deg,#1a0d0d,#1a1028);border:1px solid rgba(239,68,68,.3);border-radius:16px;padding:2rem;text-align:center;margin-top:2rem}}
.ht-countdown{{display:flex;justify-content:center;gap:1rem;margin:1.2rem 0}}
.ht-count-box{{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);border-radius:10px;padding:.8rem 1.2rem;min-width:70px}}
.ht-count-num{{font-size:2rem;font-weight:900;color:#f87171}}
.ht-count-lbl{{font-size:.7rem;color:#71717a;letter-spacing:.05em}}
/* Trust */
.ht-trust-row{{display:flex;flex-wrap:wrap;justify-content:center;gap:1.5rem;margin-top:2rem}}
.ht-trust-badge{{display:flex;align-items:center;gap:.6rem;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:.7rem 1.2rem;font-size:.85rem;color:#a1a1aa;font-weight:600}}
.ht-trust-badge span{{font-size:1.2rem}}
/* FAQ */
.ht-faq-item{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:12px;margin:.6rem 0;cursor:pointer;overflow:hidden;transition:border-color .2s}}
.ht-faq-item.open,.ht-faq-item:hover{{border-color:rgba(124,58,237,.4)}}
.ht-faq-q{{padding:1.1rem 1.4rem;font-weight:700;color:#e4e4e7;display:flex;justify-content:space-between;align-items:center}}
.ht-faq-arrow{{transition:transform .2s;color:#a78bfa}}
.ht-faq-item.open .ht-faq-arrow{{transform:rotate(180deg)}}
.ht-faq-a{{padding:0 1.4rem;max-height:0;overflow:hidden;color:#a1a1aa;line-height:1.65;font-size:.95rem;transition:max-height .3s ease,padding .3s}}
.ht-faq-item.open .ht-faq-a{{max-height:200px;padding:.2rem 1.4rem 1.2rem}}
/* Guarantee */
.ht-guarantee{{display:flex;align-items:center;gap:1.5rem;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:16px;padding:2rem;margin-top:2rem}}
.ht-guarantee-icon{{font-size:3.5rem;flex-shrink:0}}
@media(max-width:600px){{.ht-inner{{text-align:center}}.ht-guarantee{{flex-direction:column;text-align:center}}}}
</style>

<!-- ═══════ 1. INTERACTIVE DEMO ═══════ -->
<section class="ht-section" style="background:linear-gradient(180deg,#0a0a0f 0%,#0e0e1a 100%)">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-badge">LIVE DEMO</div>
    <h2 class="ht-title">{name} — Live Demo</h2>
    <p class="ht-sub">Sieh in Echtzeit wie {name} arbeitet. Klick durch die Module und entdecke was dich erwartet.</p>
    <div class="ht-tabs">{tabs_html}</div>
    <div class="ht-demo-card">
      <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:1px solid rgba(255,255,255,.08)">
        <div style="width:10px;height:10px;border-radius:50%;background:#ef4444"></div>
        <div style="width:10px;height:10px;border-radius:50%;background:#f59e0b"></div>
        <div style="width:10px;height:10px;border-radius:50%;background:#10b981"></div>
        <span style="color:#71717a;font-size:.8rem;margin-left:.5rem">{name} Dashboard — Produktionsumgebung</span>
        <div style="margin-left:auto;display:flex;align-items:center;gap:.4rem;color:#10b981;font-size:.8rem;font-weight:700">
          <div style="width:7px;height:7px;border-radius:50%;background:#10b981;animation:pulse-green 2s infinite"></div> LIVE
        </div>
      </div>
      <div class="ht-stats-row">{stats_html}</div>
      <div style="margin-top:1.5rem;background:rgba(255,255,255,.03);border-radius:10px;padding:1.2rem;text-align:left">
        <div style="font-size:.75rem;color:#71717a;margin-bottom:.5rem;font-family:monospace">▶ SYSTEM LOG</div>
        <div style="font-family:monospace;font-size:.82rem;color:#4ade80;line-height:1.8">
          ✓ {name} gestartet — alle Module aktiv<br>
          ✓ KI-Engine verbunden — Optimierung läuft<br>
          ✓ Automation aktiv — {hours_saved} eingespart<br>
          ✓ Revenue-Tracking aktiviert — Echtzeit-Updates<br>
          <span style="color:#a78bfa">▶ Nächste Aktion in 00:03:42...</span>
        </div>
      </div>
    </div>
    <p style="margin-top:1rem;color:#52525b;font-size:.82rem">Live Demo = produktnahe Simulation. Echte Ergebnisse können variieren.</p>
  </div>
</section>

<!-- ═══════ 2. ROI KALKULATOR ═══════ -->
<section class="ht-section" style="background:#0a0a0f">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-badge">ROI KALKULATOR</div>
    <h2 class="ht-title">Was bringt {name} dir konkret?</h2>
    <p class="ht-sub">Berechne dein persönliches Potenzial — in unter 30 Sekunden.</p>
    <div class="ht-roi-card">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;align-items:start;text-align:left">
        <div>
          <label style="color:#a1a1aa;font-size:.88rem;font-weight:700;display:block;margin-bottom:.3rem">{roi_label}</label>
          <input type="number" id="ht-roi-input" class="ht-roi-input" value="{roi_default}" oninput="htCalcROI()" min="0">
          <label style="color:#a1a1aa;font-size:.88rem;font-weight:700;display:block;margin-bottom:.3rem">Zeitrahmen</label>
          <select id="ht-roi-period" class="ht-roi-input" style="cursor:pointer" onchange="htCalcROI()">
            <option value="1">1 Monat</option>
            <option value="3">3 Monate</option>
            <option value="6" selected>6 Monate</option>
            <option value="12">12 Monate</option>
          </select>
        </div>
        <div>
          <div class="ht-roi-result">
            <div style="font-size:.85rem;color:#6ee7b7;font-weight:700;margin-bottom:.5rem">DEIN {roi_metric.upper()}</div>
            <div class="ht-roi-big" id="ht-roi-output">€0</div>
            <div class="ht-roi-info" id="ht-roi-detail">Gib einen Wert links ein</div>
          </div>
          <div style="margin-top:1rem;display:flex;flex-direction:column;gap:.6rem">
            <div style="display:flex;justify-content:space-between;padding:.7rem;background:rgba(255,255,255,.04);border-radius:8px;font-size:.88rem">
              <span style="color:#a1a1aa">⏰ Zeit gespart/Monat</span>
              <span style="color:#34d399;font-weight:700">{hours_saved}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:.7rem;background:rgba(255,255,255,.04);border-radius:8px;font-size:.88rem">
              <span style="color:#a1a1aa">⚡ Typischer Zeitrahmen</span>
              <span style="color:#60a5fa;font-weight:700">{roi_time}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:.7rem;background:rgba(255,255,255,.04);border-radius:8px;font-size:.88rem">
              <span style="color:#a1a1aa">📈 ROI Multiplikator</span>
              <span style="color:#a78bfa;font-weight:700">{roi_mult}x</span>
            </div>
          </div>
        </div>
      </div>
      <div style="margin-top:2rem;text-align:center">
        <a href="{buy_link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;font-weight:800;padding:1.1rem 3rem;border-radius:12px;text-decoration:none;font-size:1.05rem;box-shadow:0 4px 24px rgba(124,58,237,.4)">
          🚀 Jetzt starten — {price_real}
        </a>
        <div style="margin-top:.8rem;color:#52525b;font-size:.82rem">30-Tage Geld-zurück-Garantie · Sofortiger Zugang</div>
      </div>
    </div>
  </div>
</section>

<!-- ═══════ 3. PROBLEM / LÖSUNG ═══════ -->
<section class="ht-section" style="background:linear-gradient(180deg,#0a0a0f 0%,#0e0e18 100%)">
  <div class="ht-inner">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem">
      <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);border-radius:18px;padding:2rem">
        <div style="font-size:2rem;margin-bottom:1rem">😤</div>
        <div style="font-size:.8rem;font-weight:800;letter-spacing:.1em;color:#f87171;margin-bottom:.8rem">OHNE {name.upper()}</div>
        <ul style="color:#a1a1aa;line-height:2;list-style:none;padding:0">
          <li>❌ {pain}</li>
          <li>❌ Kein skalierbares System</li>
          <li>❌ Wettbewerber überholen dich</li>
          <li>❌ Umsatzpotenzial bleibt ungenutzt</li>
          <li>❌ Du machst alles manuell</li>
        </ul>
      </div>
      <div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);border-radius:18px;padding:2rem">
        <div style="font-size:2rem;margin-bottom:1rem">🎯</div>
        <div style="font-size:.8rem;font-weight:800;letter-spacing:.1em;color:#34d399;margin-bottom:.8rem">MIT {name.upper()}</div>
        <ul style="color:#a1a1aa;line-height:2;list-style:none;padding:0">
          <li>✅ {gain}</li>
          <li>✅ Vollständig skalierbar</li>
          <li>✅ 24/7 aktiv ohne Aufwand</li>
          <li>✅ Messbares ROI in Wochen</li>
          <li>✅ KI übernimmt die schwere Arbeit</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<!-- ═══════ 4. VERGLEICHSTABELLE ═══════ -->
<section class="ht-section" style="background:#0a0a0f">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-badge">VERGLEICH</div>
    <h2 class="ht-title">Warum {name} gewinnt</h2>
    <p class="ht-sub">Vergleich dir selbst: manuell vs. Basic-Tools vs. {name}</p>
    <div style="overflow-x:auto;margin-top:1.5rem">
      <table class="ht-compare-table">
        <thead>
          <tr style="background:rgba(255,255,255,.04)">
            <th style="text-align:left;padding:.8rem">Feature</th>
            <th>Manuell</th>
            <th>Basic-Tools</th>
            <th style="color:#a78bfa">{name} {emoji}</th>
          </tr>
        </thead>
        <tbody>
          {feature_rows}
          <tr style="background:rgba(124,58,237,.08)">
            <td style="padding:.8rem;font-weight:700;color:#e4e4e7">Monatliche Kosten</td>
            <td style="text-align:center;color:#a1a1aa">Zeit + Nerven</td>
            <td style="text-align:center;color:#a1a1aa">€200-€500</td>
            <td style="text-align:center;font-weight:800;color:#a78bfa">{price_real}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div style="margin-top:2rem">
      <a href="{buy_link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;font-weight:800;padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-size:1rem">
        {emoji} {name} jetzt holen →
      </a>
    </div>
  </div>
</section>

<!-- ═══════ 5. URGENCY ═══════ -->
<section class="ht-section" style="background:linear-gradient(180deg,#0a0a0f,#120a0a)">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-urgency">
      <div style="font-size:.8rem;font-weight:800;letter-spacing:.1em;color:#f87171;margin-bottom:.5rem">⚠️ LIMITIERTES ANGEBOT</div>
      <h3 style="font-size:1.5rem;font-weight:900;color:#fff;margin:0 0 .5rem">Dieser Preis gilt nur noch</h3>
      <div class="ht-countdown">
        <div class="ht-count-box"><div class="ht-count-num" id="ht-cd-h">23</div><div class="ht-count-lbl">STD</div></div>
        <div class="ht-count-box"><div class="ht-count-num" id="ht-cd-m">47</div><div class="ht-count-lbl">MIN</div></div>
        <div class="ht-count-box"><div class="ht-count-num" id="ht-cd-s">12</div><div class="ht-count-lbl">SEK</div></div>
      </div>
      <p style="color:#a1a1aa;margin:.5rem 0 1.2rem">Noch <strong style="color:#f87171" id="ht-spots">7</strong> Plätze zum aktuellen Preis. Danach: <s style="color:#71717a">{price_anchor}</s></p>
      <a href="{buy_link}" style="display:inline-block;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;font-weight:900;padding:1.1rem 2.5rem;border-radius:12px;text-decoration:none;font-size:1.05rem;box-shadow:0 4px 24px rgba(239,68,68,.4)">
        🔒 Platz sichern — {price_real}
      </a>
    </div>
  </div>
</section>

<!-- ═══════ 6. TRUST + GARANTIE ═══════ -->
<section class="ht-section" style="background:#0a0a0f">
  <div class="ht-inner" style="text-align:center">
    <div class="ht-trust-row">
      <div class="ht-trust-badge"><span>🔒</span> SSL Verschlüsselt</div>
      <div class="ht-trust-badge"><span>💳</span> Stripe Secure</div>
      <div class="ht-trust-badge"><span>🇪🇺</span> DSGVO Konform</div>
      <div class="ht-trust-badge"><span>⚡</span> Sofortiger Zugang</div>
      <div class="ht-trust-badge"><span>🌍</span> EU-Server</div>
      <div class="ht-trust-badge"><span>📞</span> Priority Support</div>
    </div>
    <div class="ht-guarantee" style="max-width:700px;margin:2rem auto 0">
      <div class="ht-guarantee-icon">🛡️</div>
      <div style="text-align:left">
        <div style="font-size:1.2rem;font-weight:900;color:#34d399;margin-bottom:.4rem">{guarantee_days}-Tage Zufriedenheitsgarantie</div>
        <div style="color:#a1a1aa;line-height:1.65">Wenn du in den ersten {guarantee_days} Tagen nicht zu 100% zufrieden bist, erstattest wir dir deinen Betrag vollständig — ohne Fragen, ohne Kleingedrucktes. Null Risiko für dich.</div>
      </div>
    </div>
  </div>
</section>

<!-- ═══════ 7. FAQ ═══════ -->
<section class="ht-section" style="background:linear-gradient(180deg,#0a0a0f,#0d0d18)">
  <div class="ht-inner" style="max-width:760px;margin:0 auto;text-align:center">
    <div class="ht-badge">FAQ</div>
    <h2 class="ht-title">Häufige Fragen</h2>
    <p class="ht-sub">Alles was du wissen musst — bevor du startest.</p>
    <div style="text-align:left;margin-top:1.5rem">
      {faq_html}
    </div>
    <div style="margin-top:2.5rem;padding:2rem;background:rgba(124,58,237,.1);border:1px solid rgba(124,58,237,.3);border-radius:16px">
      <div style="font-size:1.1rem;font-weight:800;color:#fff;margin-bottom:.6rem">Noch Fragen? Ich antworte persönlich.</div>
      <div style="color:#a1a1aa;margin-bottom:1.2rem">Rudolf Sarkany · AIITEC · Antwort in unter 4 Stunden</div>
      <a href="https://t.me/rudisarkany" style="display:inline-block;background:rgba(124,58,237,.2);border:1px solid rgba(124,58,237,.5);color:#a78bfa;font-weight:700;padding:.75rem 2rem;border-radius:10px;text-decoration:none">
        📱 Telegram: @rudisarkany
      </a>
    </div>
  </div>
</section>

<!-- ═══════ FINAL CTA ═══════ -->
<section class="ht-section" style="background:linear-gradient(135deg,#13082a,#0d1b38)">
  <div class="ht-inner" style="text-align:center;max-width:700px;margin:0 auto">
    <div style="font-size:3rem;margin-bottom:1rem">{emoji}</div>
    <h2 style="font-size:clamp(1.8rem,3vw,2.5rem);font-weight:900;color:#fff;margin:0 0 1rem">{name} — {tagline}</h2>
    <p style="color:#a1a1aa;line-height:1.7;margin:0 0 2rem">{gain}. Tausende Stunden gespart. Endlich skalierbar.</p>
    <a href="{buy_link}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;font-weight:900;padding:1.2rem 3.5rem;border-radius:14px;text-decoration:none;font-size:1.15rem;box-shadow:0 6px 30px rgba(124,58,237,.5);transition:transform .2s" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform=''">
      🚀 Jetzt {price_real} starten
    </a>
    <div style="display:flex;justify-content:center;gap:2rem;margin-top:1.5rem;flex-wrap:wrap">
      <div style="color:#71717a;font-size:.85rem">✓ Sofortzugang</div>
      <div style="color:#71717a;font-size:.85rem">✓ {guarantee_days} Tage Garantie</div>
      <div style="color:#71717a;font-size:.85rem">✓ Stripe Secure</div>
      <div style="color:#71717a;font-size:.85rem">✓ Keine versteckten Kosten</div>
    </div>
  </div>
</section>

<script>
/* ── ROI Kalkulator ── */
function htCalcROI(){{
  const input=parseFloat(document.getElementById('ht-roi-input').value)||0;
  const period=parseInt(document.getElementById('ht-roi-period').value)||6;
  const mult={roi_mult};
  let result=input*mult*period;
  // Format
  const fmt=v=>v>=1000000?'€'+(v/1000000).toFixed(1)+'M':v>=1000?'€'+(v/1000).toFixed(0)+'k':'€'+Math.round(v);
  document.getElementById('ht-roi-output').textContent=fmt(result);
  document.getElementById('ht-roi-detail').textContent=`{roi_metric} über ${{period}} Monat${{period>1?'e':''}} · {roi_time}`;
}}
htCalcROI();

/* ── Demo Tabs ── */
function htTab(btn,idx){{
  document.querySelectorAll('.ht-tab').forEach(t=>t.classList.remove('ht-tab-active'));
  btn.classList.add('ht-tab-active');
}}

/* ── Countdown ── */
(function(){{
  var key='ht_cd_{product_key}';
  var stored=localStorage.getItem(key);
  var end;
  if(stored){{end=parseInt(stored)}}
  else{{end=Date.now()+86400000;localStorage.setItem(key,end)}}
  function tick(){{
    var diff=Math.max(0,end-Date.now());
    var h=Math.floor(diff/3600000);
    var m=Math.floor((diff%3600000)/60000);
    var s=Math.floor((diff%60000)/1000);
    var pad=n=>n.toString().padStart(2,'0');
    var eh=document.getElementById('ht-cd-h');
    var em=document.getElementById('ht-cd-m');
    var es=document.getElementById('ht-cd-s');
    if(eh){{eh.textContent=pad(h);em.textContent=pad(m);es.textContent=pad(s);}}
    if(diff>0)setTimeout(tick,1000);
  }}
  tick();
}})();
</script>
"""


def upgrade_page(html_path: Path, product_key: str) -> bool:
    content = html_path.read_text(encoding="utf-8")
    if MARKER in content:
        print(f"  ✓ Bereits upgraded: {html_path.parent.name}")
        return False
    sections = _generate_ht_sections(product_key)
    # Inject before </body>
    if "</body>" in content:
        content = content.replace("</body>", sections + "\n</body>")
    else:
        content += sections
    html_path.write_text(content, encoding="utf-8")
    print(f"  ✅ Upgraded: {html_path.parent.name}")
    return True


def main():
    upgraded = 0
    skipped = 0
    for dirname, product_key in [
        ("bullpower-ai",              "bullpower-ai"),
        ("bullpower-hub",             "bullpower-hub"),
        ("autoincome-ai",             "autoincome-ai"),
        ("creatorai-ultra",           "creatorai-ultra"),
        ("creatorstudio-pro",         "creatorstudio-pro"),
        ("cognitive-symphony",        "cognitive-symphony"),
        ("shopify-suite",             "shopify-suite"),
        ("shopify-brutal-tuning",     "shopify-brutal-tuning"),
        ("shopify-acquisition-engine","shopify-acquisition-engine"),
        ("digistore24-suite",         "digistore24-suite"),
        ("steuercockpit",             "steuercockpit"),
        ("telegram-bot",              "telegram-bot"),
        ("icomeauto",                 "icomeauto"),
        ("launcher",                  "launcher"),
        ("lead-capture",              "lead-capture"),
        ("gumroad-discord",           "gumroad-discord"),
        ("master-dashboard",          "master-dashboard"),
    ]:
        p = NETLIFY / dirname / "index.html"
        if not p.exists():
            print(f"  ⚠ Nicht gefunden: {dirname}")
            continue
        if upgrade_page(p, product_key):
            upgraded += 1
        else:
            skipped += 1

    print(f"\n📊 Ergebnis: {upgraded} upgraded, {skipped} bereits fertig")
    return upgraded


if __name__ == "__main__":
    count = main()
    sys.exit(0 if count >= 0 else 1)
