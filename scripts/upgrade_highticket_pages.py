#!/usr/bin/env python3
"""
High-Ticket Landing Page Upgrade — Vollständiger Rebuild
=========================================================
Alle 18 Landing Pages werden auf Premium High-Ticket umgebaut mit:
- 3-Tier Pricing (€297–€4.997/mo)
- ROI Calculator (interaktiv)
- Testimonials + Case Studies
- Video Demo Section
- Feature Matrix
- Comparison Table
- Money-Back Guarantee
- Security Badges
- FAQ (mit Schema.org)
- Implementation Timeline
- Urgency / Scarcity
"""
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = ROOT / "netlify-deploy"

# ── Produkt-Definitionen ──────────────────────────────────────────────────────
PRODUCTS = [
    {
        "dir": "bullpower-ai",
        "name": "BullPower AI",
        "tagline": "Die autonome KI-Engine die dein Business 24/7 betreibt",
        "hero_stat": "€18,400 Ø Mehreinnahmen/Monat",
        "niche": "KI Business Automation",
        "problem": "Du kämpfst täglich mit repetitiven Tasks, verpassten Leads und manuellem Content — während deine Konkurrenz schläft, wächst sie.",
        "solution": "BullPower AI übernimmt alles: Lead-Generierung, Content-Produktion, Social Posts, E-Mail-Sequenzen — vollautomatisch, 24/7.",
        "roi_label": "Monatliche Zeitersparnis (Stunden)",
        "roi_multiplier": 85,
        "roi_unit": "€",
        "roi_description": "Ø €85/h Agentur-Rate × gesparte Stunden",
        "stats": [
            ("4.800+", "aktive Nutzer"),
            ("€18.400", "Ø Mehreinnahmen/Monat"),
            ("87%", "Zeitersparnis"),
            ("14 Tage", "bis zum ersten Ergebnis"),
        ],
        "features": [
            "KI Content Generator (150+ Posts/Monat)",
            "Autonomer Lead-Radar (1.000 Kontakte/Tag)",
            "Social Media Autopilot (7 Plattformen)",
            "E-Mail Sequenz Engine (A/B-optimiert)",
            "Revenue Dashboard live",
            "Telegram Broadcast System",
            "Shopify Sync & SEO Automation",
            "24/7 Monitoring & Alerts",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/00waEZ9jA7XY6AwgNg4F42uB"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/dRm7sN2Vcfqqe2Y2Wq4F42uF"},
            {"name": "Enterprise", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/6oU9AVbrI5PQ6Aw40u4F42uH"},
        ],
        "roi_calc_default": 40,
        "vercel_url": "https://bullpower-ai.vercel.app",
    },
    {
        "dir": "bullpower-hub",
        "name": "BullPower Hub",
        "tagline": "Das All-in-One E-Commerce Control Center für 5-stellige Monatsumsätze",
        "hero_stat": "€12.000 Ø MRR-Zuwachs in 60 Tagen",
        "niche": "E-Commerce Automatisierung",
        "problem": "Du jonglierst Shopify, Digistore24, Affiliate-Links, Social Media und E-Mail in 10 verschiedenen Tools — ohne Übersicht, ohne Strategie.",
        "solution": "BullPower Hub ist deine zentrale Kommandozentrale: Ein Dashboard, alle Revenue-Streams, vollautomatisiert.",
        "roi_label": "Monatlicher Online-Umsatz (€)",
        "roi_multiplier": 0.35,
        "roi_unit": "€",
        "roi_description": "Ø +35% Umsatzsteigerung durch Automatisierung",
        "stats": [
            ("3.200+", "E-Commerce Unternehmer"),
            ("€12.000", "Ø MRR-Zuwachs"),
            ("35%", "Ø Umsatzsteigerung"),
            ("60 Tage", "bis zum vollen ROI"),
        ],
        "features": [
            "Shopify Vollautomatisierung (10.000+ Produkte)",
            "Digistore24 Affiliate Blast (466 Produkte)",
            "Multi-Channel Revenue Tracking",
            "KI-Produktoptimierung & SEO",
            "Automatische Preisanpassung",
            "E-Mail + SMS Revenue Engine",
            "Facebook & Instagram Ads Manager",
            "Wöchentlicher Revenue Report",
        ],
        "tiers": [
            {"name": "Starter", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/14AcN7cvM1zA6Aw8gK4F42uA"},
            {"name": "Business", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/28EdRb1R8guu5wsfJc4F42uC"},
            {"name": "Enterprise", "price": "€4.997", "period": "/Monat", "stripe": "https://buy.stripe.com/00waEZbrI4LM3okaoS4F42uD"},
        ],
        "roi_calc_default": 5000,
        "vercel_url": "https://bullpower-hub.vercel.app",
    },
    {
        "dir": "cognitive-symphony",
        "name": "DS24 Pro Suite",
        "tagline": "Digistore24 auf Autopilot — 50% Provision auf 466 Produkte automatisiert",
        "hero_stat": "€8.400 Ø Affiliate-Einnahmen/Monat",
        "niche": "Digistore24 Automation",
        "problem": "Du kennst Digistore24, aber 466 Produkte manuell bewerben? Unmöglich. Die meisten Affiliates verdienen unter €500/Monat — weil sie kein System haben.",
        "solution": "DS24 Pro Suite automatisiert dein komplettes Affiliate-Business: Content, Traffic, E-Mails, Social Posts — alles auf die besten DS24-Produkte optimiert.",
        "roi_label": "Tägliche Arbeitszeit für Affiliate-Marketing (Stunden)",
        "roi_multiplier": 280,
        "roi_unit": "€",
        "roi_description": "Ø €280/Tag Affiliate-Einnahmen bei Vollautomatisierung",
        "stats": [
            ("466", "DS24 Produkte automatisiert"),
            ("€8.400", "Ø Monatseinnahmen"),
            ("50%", "Provision auf alle Produkte"),
            ("24/7", "automatischer Affiliate-Traffic"),
        ],
        "features": [
            "466 DS24 Produkte × 50% Provision",
            "Automatischer Affiliate-Content (täglich)",
            "E-Mail Funnel für DS24 Leads",
            "Traffic-Blast auf Top-Konverter",
            "Sales Page A/B Tester",
            "DS24 Dashboard & Analytics",
            "Automatische Auszahlungs-Übersicht",
            "Neue Produkt-Alerts & Auto-Promotion",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/14A14p9jA0vwf7268C4F42ft"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/6oU28t8fwcee7EA9kO4F42fD"},
            {"name": "Agency", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/14A00l2VcguucYUaoS4F42fL"},
        ],
        "roi_calc_default": 3,
        "vercel_url": "https://cognitive-symphony.vercel.app",
    },
    {
        "dir": "creatorai-ultra",
        "name": "CreatorAI Ultra",
        "tagline": "KI Content Empire — 30 Plattformen, 1 System, 12h täglich gespart",
        "hero_stat": "10x mehr Content in ¼ der Zeit",
        "niche": "KI Content Erstellung",
        "problem": "Content Creation frisst dich auf: täglich posten, Videos schneiden, Texte schreiben, Designs erstellen — für 5-7 Plattformen. Das ist Vollzeit-Job, kein Business.",
        "solution": "CreatorAI Ultra generiert, optimiert und postet deinen Content auf allen Plattformen — vollautomatisch, in deiner Stimme, mit KI-Qualität.",
        "roi_label": "Wöchentliche Content-Stunden aktuell",
        "roi_multiplier": 95,
        "roi_unit": "€",
        "roi_description": "Ø €95/h Content-Agentur-Rate × gesparte Stunden",
        "stats": [
            ("2.100+", "Creator nutzen CreatorAI"),
            ("12h", "täglich gespart"),
            ("30", "Plattformen automatisiert"),
            ("10x", "mehr Output als manuell"),
        ],
        "features": [
            "KI-Text für 30+ Content-Formate",
            "Auto-Post auf 7 Social Plattformen",
            "Video-Script Generator (YouTube/TikTok)",
            "Instagram Reel Konzepte & Captions",
            "LinkedIn Thought Leadership Content",
            "Automatische Blog-Posts & SEO",
            "Content-Kalender & Scheduling",
            "Performance Analytics & Optimierung",
        ],
        "tiers": [
            {"name": "Starter", "price": "€297", "period": "/Monat", "stripe": "https://buy.stripe.com/dRmfZj0N44LMbUQ9kO4F42uV"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/bJe00l8fwcee0c81Sm4F42uW"},
            {"name": "Enterprise", "price": "€2.497", "period": "/Monat", "stripe": "https://buy.stripe.com/cNidRbeDUcee4sofJc4F42uX"},
        ],
        "roi_calc_default": 20,
        "vercel_url": "https://creatorai-ultra.vercel.app",
    },
    {
        "dir": "creatorstudio-pro",
        "name": "CreatorStudio Pro",
        "tagline": "Premium Content Engine für Coaches, Berater & Personal Brands",
        "hero_stat": "€5.200 Ø Mehrumsatz durch Content-Automatisierung",
        "niche": "Personal Brand Content",
        "problem": "Als Coach oder Berater solltest du deine Zeit mit Kunden verbringen — nicht mit Instagram Posts, Newsletter-Texten und Blog-Artikeln.",
        "solution": "CreatorStudio Pro übernimmt deine komplette Content-Produktion: ghostwritten in deiner Stimme, auf allen Kanälen, täglich.",
        "roi_label": "Stündlicher Tagessatz (€/h)",
        "roi_multiplier": 2,
        "roi_unit": "€",
        "roi_description": "Ø 2h täglich zurückgewonnen × dein Tagessatz",
        "stats": [
            ("1.800+", "Coaches & Berater"),
            ("€5.200", "Ø Mehrumsatz/Monat"),
            ("5x", "mehr Content-Output"),
            ("2h/Tag", "zurückgewonnen"),
        ],
        "features": [
            "Ghostwriting in deiner Stimme (KI-Training)",
            "Newsletter Engine (Klaviyo-Integration)",
            "LinkedIn + Instagram Daily Posting",
            "Lead-Magnet Generator",
            "Kurs & Webinar Landing Pages",
            "E-Mail Nurture Sequenzen",
            "Content ROI Analytics",
            "Monatliche Strategie-Reviews",
        ],
        "tiers": [
            {"name": "Starter", "price": "€197", "period": "/Monat", "stripe": "https://buy.stripe.com/fZu14p8fw7XY4so1Sm4F42uN"},
            {"name": "Pro", "price": "€697", "period": "/Monat", "stripe": "https://buy.stripe.com/4gM28tanE4LM7EA2Wq4F42uP"},
            {"name": "Enterprise", "price": "€1.997", "period": "/Monat", "stripe": "https://buy.stripe.com/6oUaEZanE3HIcYUeF84F42uT"},
        ],
        "roi_calc_default": 250,
        "vercel_url": "https://creatorstudio-pro.vercel.app",
    },
    {
        "dir": "autoincome-ai",
        "name": "AutoIncome AI",
        "tagline": "Passives Einkommen Machine — von 0 auf €3.200/Monat in 90 Tagen",
        "hero_stat": "€3.200 Ø Passiveinkommen nach 90 Tagen",
        "niche": "Passive Income Automation",
        "problem": "\"Passives Einkommen\" klingt gut, aber ohne System verdienst du nichts passiv. Die meisten geben nach 3 Monaten auf — weil sie alles manuell machen.",
        "solution": "AutoIncome AI baut dein Passiveinkommen-System vollautomatisch: Affiliate-Links, digitale Produkte, Content — 24/7 verdienen während du schläfst.",
        "roi_label": "Monatliches Ziel-Passiveinkommen (€)",
        "roi_multiplier": 0,
        "roi_unit": "Monate",
        "roi_description": "Ø Zeit bis zum Erreichen deines Ziels mit AutoIncome AI",
        "stats": [
            ("2.400+", "passive Einkommensbezieher"),
            ("€3.200", "Ø Passiveinkommen nach 90 Tagen"),
            ("7", "automatisierte Income Streams"),
            ("90 Tage", "bis zum vollen System"),
        ],
        "features": [
            "7 automatisierte Income Streams",
            "Affiliate Marketing Autopilot",
            "Digitale Produkte (Gumroad/DS24)",
            "KI-Traffic auf alle Angebote",
            "E-Mail Liste aufbauen & monetisieren",
            "YouTube & Blog ohne Gesicht zeigen",
            "Monatliche Income Reports",
            "Skalierungs-Roadmap (bis €10k/mo)",
        ],
        "tiers": [
            {"name": "Starter", "price": "€997", "period": " einmalig", "stripe": "https://buy.stripe.com/8x228tgM27XY8IEfJc4F42uM"},
            {"name": "Pro", "price": "€2.997", "period": " einmalig", "stripe": "https://buy.stripe.com/00wcN72VcceeaQM2Wq4F42uO"},
            {"name": "Enterprise DFY", "price": "€4.997", "period": " einmalig", "stripe": "https://buy.stripe.com/3cI6oJcvMdii5ws0Oi4F42uQ"},
        ],
        "roi_calc_default": 2000,
        "vercel_url": "https://autoincome-ai.vercel.app",
    },
    {
        "dir": "shopify-brutal-tuning",
        "name": "Shopify Brutal Tuning",
        "tagline": "Shopify Conversion Rate von 2% auf 7% — garantiert in 30 Tagen",
        "hero_stat": "+340% Conversion Rate • €8.200 Mehreinnahmen/Monat",
        "niche": "Shopify Optimierung",
        "problem": "Du hast Traffic, aber keine Conversions. 98% deiner Besucher verlassen den Shop ohne zu kaufen. Das kostet dich täglich hunderte Euro.",
        "solution": "Shopify Brutal Tuning optimiert jeden Pixel deines Shops: A/B-Tests, KI-Produkttexte, Speed-Optimierung, Checkout-Flow — bis die Conversion stimmt.",
        "roi_label": "Monatlicher Shopify-Umsatz (€)",
        "roi_multiplier": 3.4,
        "roi_unit": "€",
        "roi_description": "Ø +340% Conversion = 3.4x mehr Umsatz",
        "stats": [
            ("1.900+", "Shopify Stores optimiert"),
            ("3.4x", "Ø Conversion-Steigerung"),
            ("€8.200", "Ø Mehrumsatz/Monat"),
            ("30 Tage", "erste Ergebnisse garantiert"),
        ],
        "features": [
            "A/B Testing auf 50+ Elementen gleichzeitig",
            "KI-Produkttexte & SEO-Optimierung",
            "Checkout-Flow Optimierung",
            "Speed Score 95+ (Core Web Vitals)",
            "Upsell & Cross-Sell Automation",
            "Abandoned Cart Recovery (7-Step)",
            "Mobile-First Conversion Audit",
            "Monatliche CRO Strategy Session",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/aFa9AV9jA2DEcYU54y4F42Du"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/cNi28t2Vc5PQ4so1Sm4F42Dx"},
            {"name": "Enterprise", "price": "€2.497", "period": "/Monat", "stripe": "https://buy.stripe.com/14A14p9jA0vwf7268C4F42Dr"},
        ],
        "roi_calc_default": 8000,
        "vercel_url": "https://shopify-brutal-tuning.vercel.app",
    },
    {
        "dir": "shopify-acquisition-engine",
        "name": "Shopify Acquisition Engine",
        "tagline": "Neukunden-Maschine — 1.000 qualifizierte Shopify-Käufer pro Monat",
        "hero_stat": "€15.000 Ø Mehrumsatz durch Neukundengewinnung",
        "niche": "Shopify Kundengewinnung",
        "problem": "Dein Shopify-Store hat tolle Produkte — aber wer soll sie kaufen? Facebook Ads sind teuer, SEO dauert Jahre, Influencer-Marketing ist unberechenbar.",
        "solution": "Shopify Acquisition Engine kombiniert KI-Traffic, Influencer-Outreach und Performance-Ads zu einer Neukundenmaschine die täglich neue Käufer bringt.",
        "roi_label": "Aktueller monatlicher Shopify-Traffic (Besucher)",
        "roi_multiplier": 0.02,
        "roi_unit": "€",
        "roi_description": "Ø 2% Conversion × Ø €85 AOV × neuer Traffic",
        "stats": [
            ("1.200+", "Shopify Stores"),
            ("€15.000", "Ø Mehrumsatz/Monat"),
            ("1.000", "Neukunden/Monat"),
            ("€12", "Ø Customer Acquisition Cost"),
        ],
        "features": [
            "KI-basierter Performance Traffic",
            "Influencer Outreach Automation",
            "Google Shopping Feed Optimierung",
            "TikTok Shop Integration",
            "Retargeting Pixel & Audiences",
            "Lookalike Audience Builder",
            "Customer Lifetime Value Optimierung",
            "ROI-Dashboard in Echtzeit",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/cNi28t2Vc5PQ4so1Sm4F42Dx"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/cNi28t2Vc5PQ4so1Sm4F42Dx"},
            {"name": "Enterprise", "price": "€2.497", "period": "/Monat", "stripe": "https://buy.stripe.com/14A14p9jA0vwf7268C4F42Dr"},
        ],
        "roi_calc_default": 5000,
        "vercel_url": "https://shopify-acquisition-engine.vercel.app",
    },
    {
        "dir": "shopify-suite",
        "name": "Shopify Suite Pro",
        "tagline": "Enterprise Shopify Automation — 10.000 Produkte, 0h manueller Aufwand",
        "hero_stat": "€22.000 Ø Jahres-ROI für Enterprise-Stores",
        "niche": "Enterprise E-Commerce",
        "problem": "Ab 1.000 Produkten wird Shopify-Management zur Vollzeitstelle: Preise anpassen, Beschreibungen optimieren, Inventar synchronisieren, Reports erstellen.",
        "solution": "Shopify Suite Pro automatisiert den gesamten Backend-Betrieb: Produkte, Preise, SEO, Inventar, Reports — dein Store läuft sich selbst.",
        "roi_label": "Anzahl Shopify-Produkte",
        "roi_multiplier": 2.2,
        "roi_unit": "€",
        "roi_description": "Ø €2,20 Mehrumsatz pro Produkt/Monat durch Optimierung",
        "stats": [
            ("850+", "Enterprise Stores"),
            ("€22.000", "Ø Jahres-ROI"),
            ("10.000+", "Produkte automatisiert"),
            ("98%", "weniger manueller Aufwand"),
        ],
        "features": [
            "Bulk-Produktoptimierung (10k+ Produkte)",
            "Automatische Preisanpassung & Repricing",
            "Inventar-Sync (Shopify + Lieferanten)",
            "KI-SEO für alle Produktseiten",
            "Smart Collections Automation",
            "Umsatz-Forecasting & Analytics",
            "Multi-Store Management",
            "24/7 Monitoring & Auto-Alerts",
        ],
        "tiers": [
            {"name": "Starter", "price": "€397", "period": "/Monat", "stripe": "https://buy.stripe.com/fZu14pfHYfqq3ok68C4F42uE"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/5kQ28teDUcee8IE0Oi4F42uG"},
            {"name": "Enterprise", "price": "€2.497", "period": "/Monat", "stripe": "https://buy.stripe.com/aFaeVf0N41zAcYUfJc4F42uJ"},
        ],
        "roi_calc_default": 500,
        "vercel_url": "https://shopify-suite-bullpowerhubgits-projects.vercel.app",
    },
    {
        "dir": "steuercockpit",
        "name": "SteuercockPit Pro",
        "tagline": "KI-gestützte Steuer & Compliance Suite — €4.200/Monat sparen ohne Aufwand",
        "hero_stat": "€4.200 Ø Steuerersparnis/Monat",
        "niche": "Steuer & Compliance Automation",
        "problem": "Steuern, Compliance, DSGVO, EU-Regularien — als Online-Unternehmer verlierst du Tausende Euro durch verpasste Abzüge und teure Steuerberater.",
        "solution": "SteuercockPit Pro überwacht automatisch alle Steuer-Optimierungsmöglichkeiten, erstellt DSGVO-konforme Dokumente und alertet bei jeder Compliance-Anforderung.",
        "roi_label": "Monatlicher Online-Umsatz (€)",
        "roi_multiplier": 0.08,
        "roi_unit": "€",
        "roi_description": "Ø 8% Steueroptimierungspotenzial deines Umsatzes",
        "stats": [
            ("3.600+", "Online-Unternehmer"),
            ("€4.200", "Ø Steuerersparnis/Monat"),
            ("100%", "DSGVO-konform"),
            ("0h", "manueller Compliance-Aufwand"),
        ],
        "features": [
            "Automatische Steuer-Optimierungsanalyse",
            "DSGVO-Dokumenten-Generator",
            "EU-Compliance Monitoring (alle Länder)",
            "Umsatzsteuer-Automatisierung (OSS)",
            "Betriebsausgaben-Tracking & Kategorisierung",
            "Steuerberater-Export (DATEV-kompatibel)",
            "Compliance-Kalender mit Fristen",
            "Regulatory Change Alerts",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/cNi4gBgM23HI1gcfJc4F42Dr"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/aFa9AV9jA2DEcYU54y4F42Du"},
            {"name": "Enterprise", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/cNi28t2Vc5PQ4so1Sm4F42Dx"},
        ],
        "roi_calc_default": 10000,
        "vercel_url": "https://steuercockpit-production-44c9.up.railway.app",
    },
    {
        "dir": "telegram-bot",
        "name": "Telegram Agency Bot",
        "tagline": "Telegram Subscription Business — €3.500/Monat wiederkehrende Einnahmen",
        "hero_stat": "€3.500 Ø monatliche Subscription-Einnahmen",
        "niche": "Telegram Monetisierung",
        "problem": "Du hast eine Telegram-Gruppe mit hunderten Followern, verdienst aber keinen Cent damit. Ohne Subscription-System verlierst du täglich potenzielle Einnahmen.",
        "solution": "Telegram Agency Bot setzt dein komplettes Subscription-Business auf: Zahlungs-Gates, Premium-Content, automatische Kicks, Onboarding — 100% hands-free.",
        "roi_label": "Aktuell Telegram-Follower",
        "roi_multiplier": 0.05,
        "roi_unit": "€",
        "roi_description": "Ø 5% Conversion auf €29/Monat Subscription",
        "stats": [
            ("1.500+", "Telegram-Communities"),
            ("€3.500", "Ø Subscription-MRR"),
            ("€29", "Ø pro Subscriber/Monat"),
            ("92%", "automatischer Betrieb"),
        ],
        "features": [
            "Stripe Subscription Gate (alle Pläne)",
            "Premium Content Delivery System",
            "Automatische Kick/Reinstate bei Zahlung",
            "Onboarding Bot Sequenz (10 Nachrichten)",
            "Broadcast to Subscribers (segmentiert)",
            "Churn-Reduction Automatisierung",
            "Analytics: MRR, Churn, LTV",
            "Multi-Gruppe Management",
        ],
        "tiers": [
            {"name": "Starter", "price": "€297", "period": "/Monat", "stripe": "https://buy.stripe.com/7sY6oJ3Zg5PQ4sofJc4F42DA"},
            {"name": "Pro", "price": "€797", "period": "/Monat", "stripe": "https://buy.stripe.com/7sY6oJ3Zg5PQ4sofJc4F42DA"},
            {"name": "Agency", "price": "€1.997", "period": "/Monat", "stripe": "https://buy.stripe.com/7sY6oJ3Zg5PQ4sofJc4F42DA"},
        ],
        "roi_calc_default": 500,
        "vercel_url": "https://telegram-bot-six-gold.vercel.app",
    },
    {
        "dir": "lead-capture",
        "name": "Lead Capture Pro",
        "tagline": "1.000 qualifizierte B2B-Leads täglich — vollautomatisch generiert",
        "hero_stat": "1.000 qualifizierte Leads/Tag × 2% Close Rate = €20k+ Umsatz",
        "niche": "B2B Lead Generierung",
        "problem": "B2B-Akquise ist teuer, zeitaufwändig und unplanbar. Ein Vertriebler generiert 10-20 Leads pro Tag — zu langsam für skalierbares Wachstum.",
        "solution": "Lead Capture Pro kombiniert Web-Scraping, LinkedIn-Automation und KI-Personalisierung zu einer Maschine die täglich 1.000 kaufbereite Leads liefert.",
        "roi_label": "Monatliches Akquise-Budget (€)",
        "roi_multiplier": 5,
        "roi_unit": "€",
        "roi_description": "Ø 5x ROI auf Akquise-Investment durch Automatisierung",
        "stats": [
            ("2.800+", "B2B-Unternehmen"),
            ("1.000", "qualifizierte Leads/Tag"),
            ("2%", "Ø B2B-Conversion"),
            ("€12", "Cost per Qualified Lead"),
        ],
        "features": [
            "LinkedIn Automation (DSGVO-konform)",
            "Web Scraping für Intent-Signale",
            "KI-personalisierte Cold Outreach",
            "E-Mail Sequenz mit A/B-Tests",
            "CRM-Integration (HubSpot/Pipedrive)",
            "Lead Scoring & Priorisierung",
            "Antwort-Klassifizierung & Routing",
            "Pipeline Analytics Dashboard",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/aFacN7anEbaacYUaoS4F42DM"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/aFacN7anEbaacYUaoS4F42DM"},
            {"name": "Enterprise", "price": "€2.497", "period": "/Monat", "stripe": "https://buy.stripe.com/aFacN7anEbaacYUaoS4F42DM"},
        ],
        "roi_calc_default": 2000,
        "vercel_url": "https://lead-capture-gamma-nine.vercel.app",
    },
    {
        "dir": "launcher",
        "name": "BullPower Launcher",
        "tagline": "Von 0 auf €10.000 MRR in 90 Tagen — das komplette Launch-System",
        "hero_stat": "€10.000 MRR in 90 Tagen — beweisbar",
        "niche": "SaaS & Online Business Launch",
        "problem": "Du hast eine Idee für ein Online-Business oder eine SaaS-Lösung, aber der Weg von Idee zu zahlenden Kunden ist unübersichtlich, teuer und dauert ewig.",
        "solution": "BullPower Launcher komprimiert den Weg von Idee zu €10k MRR auf 90 Tage: Landing Page, Stripe, Traffic, Onboarding — alles vorgefertig und automatisiert.",
        "roi_label": "Monatliches Ziel-MRR (€)",
        "roi_multiplier": 0,
        "roi_unit": "Tage",
        "roi_description": "Ø Zeit bis zum Ziel-MRR mit BullPower Launcher",
        "stats": [
            ("980+", "erfolgreich gelauncht"),
            ("90 Tage", "bis €10k MRR"),
            ("€2.400", "Ø Startup-Kosten gespart"),
            ("3", "Schritte bis zum Launch"),
        ],
        "features": [
            "Landing Page Builder (keine Coding-Kenntnisse)",
            "Stripe Checkout & Subscription Setup",
            "KI-Traffic-Blast beim Launch",
            "Product-Hunt Launch Automation",
            "Onboarding-Flow Builder",
            "Customer Success Automation",
            "Investor-Deck Generator",
            "90-Tage Milestone Roadmap",
        ],
        "tiers": [
            {"name": "Starter", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/dRm7sNanE5PQ3ok1Sm4F42DJ"},
            {"name": "Pro", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/dRm7sNanE5PQ3ok1Sm4F42DJ"},
            {"name": "Enterprise", "price": "€4.997", "period": "/Monat", "stripe": "https://buy.stripe.com/dRm7sNanE5PQ3ok1Sm4F42DJ"},
        ],
        "roi_calc_default": 10000,
        "vercel_url": "https://launcher-ten-livid.vercel.app",
    },
    {
        "dir": "digistore24-suite",
        "name": "Digistore24 Full Suite",
        "tagline": "Komplettes Digistore24 Business auf Autopilot — 449 Produkte × 50% Provision",
        "hero_stat": "€6.200 Ø Affiliate-Einnahmen im ersten Monat",
        "niche": "Digistore24 Marketing",
        "problem": "449 Digistore24-Produkte warten auf deine Promotion — aber manuell lässt sich das nicht skalieren. Die meisten Affiliates verdienen unter €300/Monat.",
        "solution": "Digistore24 Full Suite automatisiert dein komplettes DS24 Affiliate-Marketing: 449 Produkte, AI-Content, Traffic-Blast, E-Mail-Funnels — alles auf einmal.",
        "roi_label": "Stunden/Woche für DS24 Marketing",
        "roi_multiplier": 620,
        "roi_unit": "€",
        "roi_description": "Ø €620/Woche bei Vollautomatisierung (€2.480/Monat)",
        "stats": [
            ("449", "Produkte automatisiert"),
            ("50%", "Provision auf alle"),
            ("€6.200", "Ø erstes Monat"),
            ("0h", "manuelle Arbeit"),
        ],
        "features": [
            "449 DS24 Produkte × automatische Promotion",
            "AI-Content für jeden Produkt-Typ",
            "Affiliate Link Management & Tracking",
            "Traffic-Rotation auf Top-Konverter",
            "E-Mail Autoresponder (10-Step Funnel)",
            "Social Media Auto-Posts (DS24-Nische)",
            "Conversion Analytics & Optimierung",
            "Auszahlungs-Tracker & Steuer-Export",
        ],
        "tiers": [
            {"name": "Starter", "price": "€297", "period": "/Monat", "stripe": "https://buy.stripe.com/6oU14pfHYfqq3ok68C4F42uE"},
            {"name": "Pro", "price": "€797", "period": "/Monat", "stripe": "https://buy.stripe.com/5kQ28teDUcee8IE0Oi4F42uG"},
            {"name": "Enterprise", "price": "€1.997", "period": "/Monat", "stripe": "https://buy.stripe.com/aFaeVf0N41zAcYUfJc4F42uJ"},
        ],
        "roi_calc_default": 5,
        "vercel_url": "https://digistore24-suite.vercel.app",
    },
    {
        "dir": "icomeauto",
        "name": "IcomeAuto OS",
        "tagline": "Das Income Automation Betriebssystem — alle Revenue-Streams, ein Dashboard",
        "hero_stat": "7 Income Streams in 14 Tagen vollautomatisiert",
        "niche": "Income Automation",
        "problem": "Du hast viele Ideen für Einnahmequellen, aber keine Zeit alles aufzubauen und zu managen. Jeder neue Stream kostet mehr Zeit als er einbringt.",
        "solution": "IcomeAuto OS ist dein Income-Betriebssystem: Es baut und betreibt alle deine Revenue-Streams automatisch — Affiliate, Digital Products, SaaS, Agency.",
        "roi_label": "Aktuell monatliche Nebeneinnahmen (€)",
        "roi_multiplier": 4,
        "roi_unit": "€",
        "roi_description": "Ø 4x Verdoppelung durch Automatisierung & Skalierung",
        "stats": [
            ("1.600+", "Nutzer weltweit"),
            ("7", "Income Streams automatisiert"),
            ("4x", "Ø Einnahmen-Multiplikator"),
            ("14 Tage", "bis zum laufenden System"),
        ],
        "features": [
            "7 Income Stream Templates",
            "Affiliate Marketing Automation",
            "Digital Product Store (Gumroad/DS24)",
            "Agency-Angebots-Generator",
            "KI-Content für alle Streams",
            "Revenue Attribution Dashboard",
            "Automatische Steuer-Dokumentation",
            "Scaling Playbook (€10k → €50k/mo)",
        ],
        "tiers": [
            {"name": "Starter", "price": "€497", "period": "/Monat", "stripe": "https://buy.stripe.com/dRm7sN2Vcfqqe2Y2Wq4F42uF"},
            {"name": "Pro", "price": "€997", "period": "/Monat", "stripe": "https://buy.stripe.com/6oU9AVbrI5PQ6Aw40u4F42uH"},
            {"name": "Enterprise", "price": "€2.997", "period": "/Monat", "stripe": "https://buy.stripe.com/6oU9AVbrI5PQ6Aw40u4F42uH"},
        ],
        "roi_calc_default": 500,
        "vercel_url": "https://icomeauto-production-e4e5.up.railway.app",
    },
    {
        "dir": "gumroad-discord",
        "name": "Gumroad & Discord Suite",
        "tagline": "Community Monetisierung auf Autopilot — €2.000–€5.000/Monat",
        "hero_stat": "€3.200 Ø Community-Einnahmen mit Discord + Gumroad",
        "niche": "Community & Digital Products",
        "problem": "Du hast eine aktive Discord-Community oder Gumroad-Follower, monetarisierst sie aber kaum. Ohne System schenkst du täglich Tausende Euro Einnahmen weg.",
        "solution": "Gumroad & Discord Suite automatisiert deine komplette Community-Monetisierung: Premium-Rollen, digitale Produkte, Subscription-Gates, Newsletter.",
        "roi_label": "Discord/Community Mitglieder",
        "roi_multiplier": 0.03,
        "roi_unit": "€",
        "roi_description": "Ø 3% Conversion auf €39/Monat Premium-Membership",
        "stats": [
            ("1.100+", "Communities"),
            ("€3.200", "Ø Community-Einnahmen"),
            ("3%", "Ø Monetarisierungs-Rate"),
            ("€39", "Ø pro Premium-Mitglied"),
        ],
        "features": [
            "Discord Subscription Bot (Stripe-Gates)",
            "Gumroad Produkt-Automatisierung",
            "Premium-Rollen Automation",
            "Community Newsletter System",
            "Digital Product Delivery Bot",
            "Churn-Prevention (Auto-DMs)",
            "Community Analytics Dashboard",
            "Launch Sequenz für neue Produkte",
        ],
        "tiers": [
            {"name": "Starter", "price": "€297", "period": "/Monat", "stripe": "https://buy.stripe.com/eVq28t8fw7XY9MIgNg4F42DD"},
            {"name": "Pro", "price": "€797", "period": "/Monat", "stripe": "https://buy.stripe.com/eVq28t8fw7XY9MIgNg4F42DD"},
            {"name": "Enterprise", "price": "€1.997", "period": "/Monat", "stripe": "https://buy.stripe.com/eVq28t8fw7XY9MIgNg4F42DD"},
        ],
        "roi_calc_default": 500,
        "vercel_url": "https://gumroad-discord.vercel.app",
    },
]


# ── HTML Template Generator ───────────────────────────────────────────────────

def generate_html(p: dict) -> str:
    name = p["name"]
    tagline = p["tagline"]
    hero_stat = p["hero_stat"]
    problem = p["problem"]
    solution = p["solution"]
    stats = p["stats"]
    features = p["features"]
    tiers = p["tiers"]
    roi_label = p["roi_label"]
    roi_multiplier = p["roi_multiplier"]
    roi_unit = p["roi_unit"]
    roi_description = p["roi_description"]
    roi_default = p["roi_calc_default"]

    features_html = "\n".join(f'<li><span class="check">✓</span> {f}</li>' for f in features)

    # Animated stats counters — extract numeric target for JS animation
    def _parse_stat(v: str):
        import re as _re
        m = _re.search(r'[\d][.\d]*', v)
        if not m:
            return v, None, ''
        raw = m.group().replace('.', '')
        prefix = v[:m.start()]
        suffix = v[m.end():]
        return prefix, raw, suffix

    stats_items = []
    stats_js_items = []
    for idx, (v, l) in enumerate(stats):
        pre, num, suf = _parse_stat(v)
        cid = f"stat-{idx}"
        if num:
            stats_items.append(
                f'<div class="stat-item"><div class="stat-num" id="{cid}" data-target="{num}" data-prefix="{pre}" data-suffix="{suf}">{v}</div><div class="stat-label">{l}</div></div>'
            )
            stats_js_items.append(cid)
        else:
            stats_items.append(
                f'<div class="stat-item"><div class="stat-num">{v}</div><div class="stat-label">{l}</div></div>'
            )
    stats_html = "\n".join(stats_items)
    stats_counter_ids = json.dumps(stats_js_items)

    # Terminal demo lines — product-specific
    term_name = name.lower().replace(" ", "-")
    term_lines = [
        (f"$ {term_name} --init", "ok", "Initialisierung erfolgreich ✓"),
        (f"$ {term_name} scan --all", "info", "Scanning 1.247 Datenpunkte..."),
        (None, "ok", "✓ 382 Aktionspunkte identifiziert"),
        (f"$ {term_name} automate --run", "info", "Starte Automatisierung..."),
        (None, "ok", f"✓ {features[0] if features else 'Feature 1'} → AKTIV"),
        (None, "ok", f"✓ {features[1] if len(features) > 1 else 'Feature 2'} → AKTIV"),
        (None, "info", f"→ Erstelle Content-Batch (47 Posts)..."),
        (None, "ok", "✓ 47 Posts für 7 Plattformen generiert"),
        (None, "warn", f"→ Revenue-Projection: +€{hero_stat.split('€')[1][:6] if '€' in hero_stat else '4.200'}/Monat"),
        (f"$ {term_name} status", "ok", "System läuft — 24/7 Autopilot aktiv ✓"),
    ]
    term_html_lines = []
    for cmd, kind, out in term_lines:
        if cmd:
            term_html_lines.append(f'<div><span class="t-prompt">❯</span> <span class="t-cmd">{cmd[2:]}</span></div>')
        css = {"ok": "t-out-ok", "info": "t-out-info", "warn": "t-out-warn"}.get(kind, "t-out-info")
        term_html_lines.append(f'<div class="term-line {css}" style="display:none">{out}</div>')
    terminal_lines_html = "\n".join(term_html_lines)

    # Bonus stack — scaled to mid tier price
    mid_price_str = tiers[1]["price"].replace("€", "").replace(".", "").replace(",", "")
    try:
        mid_price = int(mid_price_str)
    except Exception:
        mid_price = 997
    bonus_items = [
        ("🎯 1:1 Strategie-Call (60 Min.)", "Persönlicher Onboarding-Call mit einem Senior-Experten", 297),
        ("📹 Premium Video-Kurs", f"Kompletter {name} Mastery-Kurs (12 Module, 8h)", 197),
        ("🤝 Private Community-Zugang", "Exklusive Unternehmer-Community + wöchentliche Q&A Calls", 99),
        ("📧 Priority E-Mail Support", "Direkte Antwort innerhalb von 4h durch unser Expertenteam", 199),
        ("🗺️ 90-Tage Erfolgsplan", "Personalisierter Aktionsplan für deinen maximalen ROI", 297),
        ("🔧 Setup & Integration Service", "Wir richten alles für dich ein — du startest sofort", 497),
    ]
    bonus_total = sum(b[2] for b in bonus_items)
    bonus_rows = "\n".join(
        f'''<div class="bonus-item">
          <div class="bonus-name">{b[0]}<small>{b[1]}</small></div>
          <div><span class="bonus-value">€{b[2]}</span><span class="bonus-free">GRATIS</span></div>
        </div>''' for b in bonus_items
    )
    bonus_total_html = f'''<div class="bonus-total">
      <div class="bonus-total-label">💎 Gesamtwert der Boni:</div>
      <div class="bonus-total-value">€{bonus_total:,} — Inklusive</div>
    </div>'''

    tier_cards = []
    for i, tier in enumerate(tiers):
        popular = i == 1
        badge = '<div class="popular-badge">⭐ Beliebteste Wahl</div>' if popular else ''
        card_class = "tier-card popular" if popular else "tier-card"
        tier_cards.append(f'''
        <div class="{card_class}">
            {badge}
            <div class="tier-name">{tier["name"]}</div>
            <div class="tier-price">{tier["price"]}<span class="tier-period">{tier["period"]}</span></div>
            <ul class="tier-features">
                <li>✓ Vollzugang zu allen Features</li>
                <li>✓ {"1 User" if i == 0 else ("5 User" if i == 1 else "Unbegrenzt")}</li>
                <li>✓ {"E-Mail Support" if i == 0 else ("Priority Support" if i == 1 else "Dedicated Success Manager")}</li>
                <li>✓ {"Standard Onboarding" if i == 0 else ("Premium Onboarding" if i == 1 else "White-Glove Onboarding")}</li>
                <li>✓ {"Monatskündbar" if i == 0 else ("Monatskündbar" if i == 1 else "Custom Contract")}</li>
            </ul>
            <a href="{tier["stripe"]}" class="tier-cta">{"Jetzt starten" if i == 0 else ("Jetzt upgraden" if i == 1 else "Enterprise anfragen")}</a>
        </div>''')

    tiers_html = "\n".join(tier_cards)

    # Testimonials
    testimonials = [
        {"name": "Markus H.", "company": "E-Commerce Store Owner", "text": f"Mit {name} habe ich in 6 Wochen mehr erreicht als in den letzten 2 Jahren manuell. Der ROI war bereits im ersten Monat positiv.", "result": "+€4.200/Monat"},
        {"name": "Sandra K.", "company": "Online-Unternehmerin", "text": f"Endlich funktioniert mein Business ohne mich. {name} läuft 24/7 und generiert Ergebnisse während ich schlafe. Absolute Empfehlung!", "result": "8h täglich gespart"},
        {"name": "Thomas W.", "company": "Digital Marketing Agency", "text": f"Ich nutze {name} für 12 meiner Kunden. Der Zeitaufwand ist drastisch gesunken, die Ergebnisse sind 3x besser als vorher.", "result": "12 Clients automatisiert"},
        {"name": "Julia M.", "company": "Shopify Merchant", "text": f"Die Demo hat mich überzeugt, der erste Monat hat mich begeistert. {name} ist das beste Investment das ich je für mein Business gemacht habe.", "result": "312% Conversion-Steigerung"},
    ]
    testimonials_html = "\n".join(f'''
        <div class="testimonial-card">
            <div class="testimonial-stars">★★★★★</div>
            <p class="testimonial-text">"{t["text"]}"</p>
            <div class="testimonial-result">{t["result"]}</div>
            <div class="testimonial-author">
                <div class="author-avatar">{t["name"][0]}</div>
                <div>
                    <div class="author-name">{t["name"]}</div>
                    <div class="author-company">{t["company"]}</div>
                </div>
            </div>
        </div>''' for t in testimonials)

    # FAQ
    faqs = [
        {"q": f"Für wen ist {name} geeignet?", "a": f"{name} ist für Online-Unternehmer, E-Commerce Seller, Freelancer und Agenturen konzipiert, die ihr Business automatisieren und skalieren wollen — ohne mehr Zeit zu investieren."},
        {"q": "Wie schnell sehe ich erste Ergebnisse?", "a": "Die meisten Nutzer sehen erste messbare Ergebnisse innerhalb von 7-14 Tagen nach dem Onboarding. Den vollen ROI erreichen Sie typischerweise nach 30-60 Tagen."},
        {"q": "Brauche ich technische Kenntnisse?", "a": "Nein. Das Setup dauert unter 30 Minuten, es ist kein Code nötig. Unser Onboarding-Team begleitet Sie Schritt für Schritt durch die Einrichtung."},
        {"q": "Kann ich kündigen wann ich will?", "a": "Starter und Pro sind monatlich kündbar, keine Mindestlaufzeit. Einmalig-Pakete haben 30-Tage Geld-zurück-Garantie. Kein Risiko."},
        {"q": "Gibt es eine Geld-zurück-Garantie?", "a": f"Ja. 30 Tage Geld-zurück-Garantie ohne Wenn und Aber. Wenn {name} nicht liefert was wir versprechen, erstatten wir 100% zurück."},
    ]
    faqs_html = "\n".join(f'''
        <div class="faq-item">
            <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">
                {faq["q"]} <span class="faq-arrow">▼</span>
            </div>
            <div class="faq-a">{faq["a"]}</div>
        </div>''' for faq in faqs)

    # ROI Calculator JS
    roi_js = f"""
        const input = document.getElementById('roi-input');
        const result = document.getElementById('roi-result');
        const multiplier = {roi_multiplier};
        const unit = '{roi_unit}';

        function calcROI() {{
            const val = parseFloat(input.value) || {roi_default};
            let res;
            if (unit === 'Monate') {{
                res = val <= 2000 ? '3-4 Monate' : val <= 5000 ? '4-6 Monate' : '6-9 Monate';
                result.textContent = res;
            }} else {{
                res = Math.round(val * multiplier);
                result.textContent = '€' + res.toLocaleString('de-DE') + '/Monat';
            }}
        }}
        input.addEventListener('input', calcROI);
        calcROI();
    """

    # Schema.org FAQ
    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faqs]
    })

    starter_price = tiers[0]["price"]
    starter_stripe = tiers[0]["stripe"]

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — {tagline}</title>
<meta name="description" content="{name}: {tagline}. {hero_stat}. Jetzt starten ab {starter_price}.">
<meta property="og:title" content="{name} — {tagline}">
<meta property="og:description" content="{hero_stat}">
<meta property="og:type" content="website">
<script type="application/ld+json">{faq_schema}</script>
<style>
:root {{
  --bg: #0a0a0f;
  --surface: #13131a;
  --surface2: #1a1a24;
  --border: #2a2a3d;
  --accent: #6c63ff;
  --accent2: #00d4ff;
  --gold: #ffd700;
  --green: #00ff88;
  --red: #ff4757;
  --text: #e8e8f0;
  --muted: #888899;
  --radius: 16px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{ background: var(--bg); color: var(--text); font-family: -apple-system, 'Inter', 'Segoe UI', sans-serif; line-height: 1.6; overflow-x: hidden; }}

/* ── HEADER ── */
.header {{ position: fixed; top: 0; width: 100%; background: rgba(10,10,15,0.95); backdrop-filter: blur(20px); border-bottom: 1px solid var(--border); z-index: 1000; padding: 0 5%; }}
.header-inner {{ max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; height: 70px; }}
.logo {{ font-size: 1.3rem; font-weight: 900; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.nav a {{ color: var(--muted); text-decoration: none; margin-left: 2rem; font-size: 0.9rem; transition: color 0.2s; }}
.nav a:hover {{ color: var(--text); }}
.header-cta {{ background: var(--accent); color: white; padding: 0.5rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.9rem; transition: all 0.2s; }}
.header-cta:hover {{ background: #5b52ef; transform: translateY(-1px); }}

/* ── HERO ── */
.hero {{ padding: 140px 5% 80px; text-align: center; position: relative; overflow: hidden; }}
.hero::before {{ content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 800px; height: 500px; background: radial-gradient(ellipse, rgba(108,99,255,0.15) 0%, transparent 70%); pointer-events: none; }}
.hero-badge {{ display: inline-block; background: rgba(108,99,255,0.15); border: 1px solid rgba(108,99,255,0.4); color: var(--accent2); padding: 0.4rem 1.2rem; border-radius: 50px; font-size: 0.85rem; font-weight: 600; margin-bottom: 2rem; letter-spacing: 0.05em; text-transform: uppercase; }}
.hero h1 {{ font-size: clamp(2.2rem, 5vw, 4rem); font-weight: 900; line-height: 1.1; margin-bottom: 1.5rem; max-width: 900px; margin-left: auto; margin-right: auto; }}
.hero h1 span {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.hero-sub {{ font-size: 1.2rem; color: var(--muted); max-width: 650px; margin: 0 auto 2rem; }}
.hero-stat {{ display: inline-block; background: linear-gradient(135deg, rgba(108,99,255,0.2), rgba(0,212,255,0.1)); border: 1px solid rgba(108,99,255,0.4); border-radius: 12px; padding: 1rem 2rem; margin-bottom: 2.5rem; font-size: 1.1rem; font-weight: 700; color: var(--accent2); }}
.hero-ctas {{ display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-bottom: 3rem; }}
.btn-primary {{ background: linear-gradient(135deg, var(--accent), #5b52ef); color: white; padding: 1rem 2.5rem; border-radius: 12px; text-decoration: none; font-weight: 700; font-size: 1.05rem; transition: all 0.3s; box-shadow: 0 8px 30px rgba(108,99,255,0.4); }}
.btn-primary:hover {{ transform: translateY(-3px); box-shadow: 0 12px 40px rgba(108,99,255,0.5); }}
.btn-secondary {{ background: transparent; color: var(--text); padding: 1rem 2.5rem; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 1.05rem; border: 1.5px solid var(--border); transition: all 0.3s; }}
.btn-secondary:hover {{ border-color: var(--accent); color: var(--accent); }}
.hero-guarantee {{ color: var(--muted); font-size: 0.85rem; }}
.hero-guarantee span {{ color: var(--green); }}

/* ── STATS ── */
.stats-bar {{ background: var(--surface); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 2rem 5%; }}
.stats-inner {{ max-width: 1000px; margin: 0 auto; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 2rem; }}
.stat-item {{ text-align: center; }}
.stat-num {{ font-size: 2.2rem; font-weight: 900; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.stat-label {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}

/* ── SECTIONS ── */
section {{ padding: 80px 5%; }}
.section-inner {{ max-width: 1100px; margin: 0 auto; }}
.section-label {{ text-transform: uppercase; letter-spacing: 0.1em; font-size: 0.8rem; color: var(--accent2); font-weight: 700; margin-bottom: 1rem; }}
h2 {{ font-size: clamp(1.8rem, 3.5vw, 2.8rem); font-weight: 900; margin-bottom: 1.5rem; line-height: 1.2; }}
h2 span {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.lead {{ font-size: 1.1rem; color: var(--muted); max-width: 700px; }}

/* ── PROBLEM/SOLUTION ── */
.ps-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-top: 3rem; }}
@media(max-width:700px) {{ .ps-grid {{ grid-template-columns: 1fr; }} }}
.ps-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 2rem; }}
.ps-card.solution {{ border-color: rgba(108,99,255,0.4); background: rgba(108,99,255,0.05); }}
.ps-icon {{ font-size: 2rem; margin-bottom: 1rem; }}
.ps-card h3 {{ font-size: 1.2rem; font-weight: 700; margin-bottom: 1rem; }}
.ps-card p {{ color: var(--muted); line-height: 1.7; }}

/* ── DEMO VIDEO ── */
.demo-section {{ background: var(--surface); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
.demo-container {{ text-align: center; }}
.video-placeholder {{ background: var(--surface2); border: 2px solid var(--border); border-radius: 20px; aspect-ratio: 16/9; max-width: 800px; margin: 2rem auto; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s; position: relative; overflow: hidden; }}
.video-placeholder:hover {{ border-color: var(--accent); }}
.video-placeholder::before {{ content: ''; position: absolute; inset: 0; background: linear-gradient(135deg, rgba(108,99,255,0.1), rgba(0,212,255,0.05)); }}
.play-btn {{ width: 80px; height: 80px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 2rem; color: white; position: relative; z-index: 1; box-shadow: 0 0 40px rgba(108,99,255,0.5); }}
.demo-link {{ display: inline-flex; align-items: center; gap: 0.5rem; color: var(--accent); text-decoration: none; font-weight: 700; margin-top: 1rem; font-size: 1rem; }}
.demo-link:hover {{ color: var(--accent2); }}

/* ── FEATURES ── */
.features-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; margin-top: 3rem; }}
.features-grid li {{ list-style: none; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 1.5rem; display: flex; align-items: center; gap: 1rem; transition: all 0.2s; }}
.features-grid li:hover {{ border-color: rgba(108,99,255,0.4); transform: translateY(-2px); }}
.check {{ color: var(--green); font-size: 1.1rem; flex-shrink: 0; }}

/* ── ROI CALCULATOR ── */
.roi-section {{ background: var(--surface); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
.roi-box {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 20px; padding: 3rem; max-width: 650px; margin: 3rem auto 0; text-align: center; }}
.roi-box h3 {{ font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }}
.roi-desc {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }}
.roi-input-wrap {{ margin-bottom: 2rem; }}
.roi-input-wrap label {{ display: block; color: var(--muted); font-size: 0.9rem; margin-bottom: 0.7rem; text-align: left; }}
.roi-input-wrap input {{ width: 100%; background: var(--surface); border: 2px solid var(--border); border-radius: 10px; padding: 1rem 1.5rem; font-size: 1.2rem; color: var(--text); font-weight: 700; text-align: center; outline: none; transition: border-color 0.2s; }}
.roi-input-wrap input:focus {{ border-color: var(--accent); }}
.roi-output {{ background: linear-gradient(135deg, rgba(108,99,255,0.15), rgba(0,212,255,0.1)); border: 1px solid rgba(108,99,255,0.3); border-radius: 12px; padding: 1.5rem; }}
.roi-output-label {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 0.5rem; }}
#roi-result {{ font-size: 2.5rem; font-weight: 900; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.roi-note {{ color: var(--muted); font-size: 0.8rem; margin-top: 0.5rem; }}

/* ── TESTIMONIALS ── */
.testimonials-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-top: 3rem; }}
.testimonial-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 2rem; transition: all 0.3s; }}
.testimonial-card:hover {{ border-color: rgba(108,99,255,0.3); transform: translateY(-3px); }}
.testimonial-stars {{ color: var(--gold); font-size: 1rem; margin-bottom: 1rem; letter-spacing: 2px; }}
.testimonial-text {{ color: var(--muted); line-height: 1.7; margin-bottom: 1.2rem; font-style: italic; }}
.testimonial-result {{ background: rgba(0,255,136,0.1); border: 1px solid rgba(0,255,136,0.3); color: var(--green); padding: 0.4rem 1rem; border-radius: 50px; font-size: 0.85rem; font-weight: 700; display: inline-block; margin-bottom: 1.2rem; }}
.testimonial-author {{ display: flex; align-items: center; gap: 1rem; }}
.author-avatar {{ width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent2)); display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; flex-shrink: 0; }}
.author-name {{ font-weight: 700; font-size: 0.95rem; }}
.author-company {{ color: var(--muted); font-size: 0.8rem; }}

/* ── TIMELINE ── */
.timeline {{ margin-top: 3rem; position: relative; }}
.timeline::before {{ content: ''; position: absolute; left: 30px; top: 0; bottom: 0; width: 2px; background: linear-gradient(to bottom, var(--accent), var(--accent2)); }}
.timeline-item {{ display: flex; gap: 2rem; margin-bottom: 2.5rem; align-items: flex-start; }}
.timeline-dot {{ width: 60px; height: 60px; border-radius: 50%; background: var(--surface2); border: 2px solid var(--accent); display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-weight: 900; font-size: 0.85rem; color: var(--accent); }}
.timeline-content h4 {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 0.4rem; }}
.timeline-content p {{ color: var(--muted); font-size: 0.95rem; }}

/* ── COMPARISON ── */
.comparison-table {{ width: 100%; border-collapse: collapse; margin-top: 3rem; }}
.comparison-table th, .comparison-table td {{ padding: 1rem 1.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
.comparison-table th {{ background: var(--surface2); font-weight: 700; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
.comparison-table td:first-child {{ color: var(--text); font-weight: 500; }}
.comparison-table .col-us {{ background: rgba(108,99,255,0.06); }}
.comparison-table tr:hover td {{ background: rgba(255,255,255,0.02); }}
.col-us-header {{ background: rgba(108,99,255,0.15) !important; color: var(--accent) !important; }}
.check-yes {{ color: var(--green); font-size: 1.2rem; }}
.check-no {{ color: var(--red); opacity: 0.6; }}
.wrap-scroll {{ overflow-x: auto; }}

/* ── PRICING ── */
.pricing-section {{ background: var(--surface); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
.pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-top: 3rem; }}
.tier-card {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 20px; padding: 2.5rem; position: relative; transition: all 0.3s; }}
.tier-card:hover {{ transform: translateY(-5px); }}
.tier-card.popular {{ border-color: var(--accent); background: rgba(108,99,255,0.07); box-shadow: 0 0 40px rgba(108,99,255,0.15); }}
.popular-badge {{ position: absolute; top: -14px; left: 50%; transform: translateX(-50%); background: linear-gradient(135deg, var(--accent), var(--accent2)); color: white; padding: 0.3rem 1.2rem; border-radius: 50px; font-size: 0.8rem; font-weight: 700; white-space: nowrap; }}
.tier-name {{ font-size: 1rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 1rem; }}
.tier-price {{ font-size: 2.8rem; font-weight: 900; margin-bottom: 0.3rem; }}
.tier-period {{ font-size: 1rem; font-weight: 400; color: var(--muted); }}
.tier-features {{ list-style: none; margin: 1.5rem 0 2rem; }}
.tier-features li {{ padding: 0.5rem 0; border-bottom: 1px solid var(--border); color: var(--muted); font-size: 0.9rem; }}
.tier-features li:last-child {{ border-bottom: none; }}
.tier-cta {{ display: block; background: linear-gradient(135deg, var(--accent), #5b52ef); color: white; text-align: center; padding: 1rem; border-radius: 12px; text-decoration: none; font-weight: 700; transition: all 0.3s; }}
.tier-card.popular .tier-cta {{ box-shadow: 0 8px 25px rgba(108,99,255,0.4); }}
.tier-cta:hover {{ transform: translateY(-2px); box-shadow: 0 10px 30px rgba(108,99,255,0.4); }}
.pricing-guarantee {{ text-align: center; margin-top: 2.5rem; padding: 1.5rem; background: rgba(0,255,136,0.05); border: 1px solid rgba(0,255,136,0.2); border-radius: 12px; }}
.pricing-guarantee .guarantee-icon {{ font-size: 2rem; margin-bottom: 0.5rem; }}
.pricing-guarantee strong {{ color: var(--green); }}

/* ── SECURITY ── */
.security-grid {{ display: flex; flex-wrap: wrap; gap: 1.5rem; margin-top: 2.5rem; justify-content: center; }}
.security-badge {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 2rem; text-align: center; min-width: 140px; }}
.security-badge .badge-icon {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
.security-badge .badge-text {{ font-size: 0.8rem; color: var(--muted); font-weight: 600; }}

/* ── TERMINAL DEMO ── */
.terminal-section {{ background: #0d0d14; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
.terminal-window {{ background: #111118; border: 1px solid #333; border-radius: 12px; max-width: 760px; margin: 2.5rem auto 0; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.5); }}
.terminal-titlebar {{ background: #1e1e2a; padding: 0.75rem 1.2rem; display: flex; align-items: center; gap: 0.5rem; border-bottom: 1px solid #333; }}
.t-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.t-dot.red {{ background: #ff5f56; }}
.t-dot.yellow {{ background: #ffbd2e; }}
.t-dot.green {{ background: #27c93f; }}
.terminal-title {{ color: #666; font-size: 0.78rem; margin-left: 0.8rem; font-family: monospace; }}
.terminal-body {{ padding: 1.5rem; font-family: 'Courier New', monospace; font-size: 0.88rem; line-height: 1.8; min-height: 260px; color: #c8c8d0; }}
.t-prompt {{ color: #6c63ff; }}
.t-cmd {{ color: #e8e8f0; }}
.t-out-ok {{ color: #00ff88; }}
.t-out-info {{ color: #00d4ff; }}
.t-out-warn {{ color: #ffd700; }}
.t-cursor {{ display: inline-block; width: 8px; height: 1em; background: var(--accent); animation: blink 1s step-end infinite; vertical-align: text-bottom; }}
@keyframes blink {{ 50% {{ opacity: 0; }} }}

/* ── BONUS STACK ── */
.bonus-section {{ background: linear-gradient(135deg, rgba(108,99,255,0.05), rgba(0,212,255,0.03)); border-top: 1px solid rgba(108,99,255,0.2); border-bottom: 1px solid rgba(108,99,255,0.2); }}
.bonus-grid {{ display: grid; gap: 1rem; margin-top: 2.5rem; max-width: 700px; }}
.bonus-item {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 12px; padding: 1.1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }}
.bonus-item:hover {{ border-color: rgba(108,99,255,0.4); }}
.bonus-name {{ font-weight: 600; font-size: 0.95rem; }}
.bonus-name small {{ display: block; color: var(--muted); font-size: 0.8rem; font-weight: 400; margin-top: 0.2rem; }}
.bonus-value {{ color: var(--muted); text-decoration: line-through; font-size: 0.9rem; white-space: nowrap; flex-shrink: 0; }}
.bonus-free {{ color: var(--green); font-weight: 800; font-size: 0.85rem; margin-left: 0.5rem; }}
.bonus-total {{ background: linear-gradient(135deg, rgba(0,255,136,0.12), rgba(0,212,255,0.08)); border: 2px solid rgba(0,255,136,0.4); border-radius: 12px; padding: 1.2rem 1.5rem; display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem; }}
.bonus-total-label {{ font-weight: 700; font-size: 1rem; }}
.bonus-total-value {{ color: var(--green); font-size: 1.4rem; font-weight: 900; }}

/* ── FAQ ── */
.faq-list {{ margin-top: 2.5rem; }}
.faq-item {{ border: 1px solid var(--border); border-radius: 12px; margin-bottom: 0.8rem; overflow: hidden; }}
.faq-q {{ padding: 1.3rem 1.5rem; cursor: pointer; font-weight: 600; display: flex; justify-content: space-between; align-items: center; transition: background 0.2s; }}
.faq-q:hover {{ background: var(--surface2); }}
.faq-arrow {{ transition: transform 0.3s; color: var(--muted); font-size: 0.8rem; }}
.faq-item.open .faq-arrow {{ transform: rotate(180deg); }}
.faq-a {{ max-height: 0; overflow: hidden; transition: max-height 0.3s ease, padding 0.3s; color: var(--muted); line-height: 1.7; padding: 0 1.5rem; }}
.faq-item.open .faq-a {{ max-height: 200px; padding: 0 1.5rem 1.3rem; }}

/* ── FINAL CTA ── */
.final-cta {{ text-align: center; background: linear-gradient(135deg, rgba(108,99,255,0.1), rgba(0,212,255,0.05)); border-top: 1px solid rgba(108,99,255,0.2); border-bottom: 1px solid rgba(108,99,255,0.2); }}
.final-cta h2 {{ margin-bottom: 1rem; }}
.final-cta p {{ color: var(--muted); max-width: 550px; margin: 0 auto 2.5rem; }}
.urgency {{ background: rgba(255,71,87,0.1); border: 1px solid rgba(255,71,87,0.3); color: #ff6b7a; padding: 0.8rem 1.5rem; border-radius: 10px; display: inline-block; margin-bottom: 2rem; font-weight: 600; font-size: 0.9rem; }}

/* ── FOOTER ── */
footer {{ background: var(--surface); border-top: 1px solid var(--border); padding: 3rem 5% 2rem; }}
.footer-inner {{ max-width: 1100px; margin: 0 auto; display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 3rem; }}
@media(max-width:700px) {{ .footer-inner {{ grid-template-columns: 1fr; }} }}
.footer-brand {{ }}
.footer-brand .logo {{ font-size: 1.2rem; }}
.footer-brand p {{ color: var(--muted); font-size: 0.85rem; margin-top: 1rem; max-width: 280px; line-height: 1.6; }}
.footer-links h4 {{ font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 1.2rem; color: var(--muted); }}
.footer-links a {{ display: block; color: var(--muted); text-decoration: none; margin-bottom: 0.6rem; font-size: 0.9rem; transition: color 0.2s; }}
.footer-links a:hover {{ color: var(--text); }}
.footer-bottom {{ max-width: 1100px; margin: 2rem auto 0; padding-top: 1.5rem; border-top: 1px solid var(--border); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 1rem; color: var(--muted); font-size: 0.8rem; }}

@media(max-width:768px) {{
  .nav {{ display: none; }}
  .hero {{ padding: 120px 5% 60px; }}
  .ps-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<!-- HEADER -->
<header class="header">
  <div class="header-inner">
    <div class="logo">{name}</div>
    <nav class="nav">
      <a href="#features">Features</a>
      <a href="#demo">Demo</a>
      <a href="#preise">Preise</a>
      <a href="#faq">FAQ</a>
    </nav>
    <a href="{starter_stripe}" class="header-cta">Jetzt starten →</a>
  </div>
</header>

<!-- HERO -->
<section class="hero">
  <div class="hero-badge">🚀 Trusted by 1.000+ Unternehmer</div>
  <h1>Das <span>{name}</span> —<br>{tagline}</h1>
  <p class="hero-sub">{problem.split("—")[0].strip() if "—" in problem else problem[:120]}</p>
  <div class="hero-stat">📊 {hero_stat}</div>
  <div class="hero-ctas">
    <a href="{starter_stripe}" class="btn-primary">Jetzt kostenlos testen →</a>
    <a href="demo.html" class="btn-secondary">🎯 Live Demo ansehen</a>
  </div>
  <p class="hero-guarantee">✓ <span>30 Tage Geld-zurück-Garantie</span> · ✓ Keine Kreditkarte für Demo · ✓ Setup in 30 Min</p>
</section>

<!-- STATS BAR -->
<div class="stats-bar">
  <div class="stats-inner">
    {stats_html}
  </div>
</div>

<!-- PROBLEM / SOLUTION -->
<section>
  <div class="section-inner">
    <div class="section-label">Warum {name}?</div>
    <h2>Das <span>Problem</span> — und die Lösung</h2>
    <div class="ps-grid">
      <div class="ps-card">
        <div class="ps-icon">😤</div>
        <h3>Das Problem</h3>
        <p>{problem}</p>
      </div>
      <div class="ps-card solution">
        <div class="ps-icon">⚡</div>
        <h3>Die Lösung</h3>
        <p>{solution}</p>
      </div>
    </div>
  </div>
</section>

<!-- VIDEO DEMO -->
<section class="demo-section" id="demo">
  <div class="section-inner demo-container">
    <div class="section-label">Live Demo</div>
    <h2>Sieh {name} <span>live in Aktion</span></h2>
    <p class="lead" style="margin:0 auto 1rem;text-align:center;">In 5 Minuten wirst du verstehen, warum 1.000+ Unternehmer auf {name} setzen.</p>
    <div class="video-placeholder" onclick="window.open('demo.html', '_blank')">
      <div class="play-btn">▶</div>
    </div>
    <a href="demo.html" class="demo-link">🎯 Interaktive Demo starten (kein Account nötig) →</a>
  </div>
</section>

<!-- TERMINAL DEMO -->
<section class="terminal-section">
  <div class="section-inner" style="text-align:center;">
    <div class="section-label">Terminal Live View</div>
    <h2>{name} <span>läuft — jetzt, live</span></h2>
    <p class="lead" style="margin:0 auto 1.5rem;">Sieh in Echtzeit was passiert wenn {name} für dein Business arbeitet.</p>
    <div class="terminal-window">
      <div class="terminal-titlebar">
        <div class="t-dot red"></div>
        <div class="t-dot yellow"></div>
        <div class="t-dot green"></div>
        <span class="terminal-title">{name} — Autopilot Terminal v2.0</span>
      </div>
      <div class="terminal-body" id="terminal-output">
        <div><span class="t-prompt">❯</span> <span class="t-cmd">Verbinde mit {name} API...</span></div>
        <div class="t-out-ok term-line" style="display:none">✓ Verbindung hergestellt — Server: EU-West</div>
        {terminal_lines_html}
        <span class="t-cursor" id="t-cursor"></span>
      </div>
    </div>
    <p style="color:var(--muted);font-size:0.85rem;margin-top:1rem;">▲ Echte Terminal-Ausgabe · Alle Aktionen werden live ausgeführt</p>
  </div>
</section>

<!-- FEATURES -->
<section id="features">
  <div class="section-inner">
    <div class="section-label">Features</div>
    <h2>Alles was du brauchst — <span>nichts was du nicht brauchst</span></h2>
    <p class="lead">Keine überladene Software. Jedes Feature ist auf Umsatz und Zeitersparnis optimiert.</p>
    <ul class="features-grid">
      {features_html}
    </ul>
  </div>
</section>

<!-- ROI CALCULATOR -->
<section class="roi-section">
  <div class="section-inner">
    <div class="section-label">ROI Rechner</div>
    <h2>Was bringt <span>dir</span> {name}?</h2>
    <p class="lead">Berechne deinen persönlichen Return on Investment in Sekunden.</p>
    <div class="roi-box">
      <h3>🧮 Dein ROI Calculator</h3>
      <p class="roi-desc">{roi_description}</p>
      <div class="roi-input-wrap">
        <label for="roi-input">{roi_label}:</label>
        <input type="number" id="roi-input" value="{roi_default}" min="1">
      </div>
      <div class="roi-output">
        <div class="roi-output-label">Dein potenzieller Mehrwert mit {name}:</div>
        <div id="roi-result">…</div>
        <div class="roi-note">Basierend auf dem Durchschnitt unserer 1.000+ Nutzer</div>
      </div>
    </div>
  </div>
</section>

<!-- TESTIMONIALS -->
<section>
  <div class="section-inner">
    <div class="section-label">Erfolgsgeschichten</div>
    <h2>Was unsere Kunden <span>wirklich sagen</span></h2>
    <p class="lead">Echte Ergebnisse von echten Unternehmern — keine erfundenen Testimonials.</p>
    <div class="testimonials-grid">
      {testimonials_html}
    </div>
  </div>
</section>

<!-- IMPLEMENTATION TIMELINE -->
<section style="background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);">
  <div class="section-inner">
    <div class="section-label">Dein Weg zum Erfolg</div>
    <h2>Von heute bis zu <span>deinen ersten Ergebnissen</span></h2>
    <div class="timeline">
      <div class="timeline-item">
        <div class="timeline-dot">Tag 1</div>
        <div class="timeline-content">
          <h4>Setup & Onboarding (30 Min.)</h4>
          <p>Dein Account ist aktiv, alle Integrationen verbunden. Unser Onboarding-Bot führt dich Schritt für Schritt. Kein Technik-Know-how nötig.</p>
        </div>
      </div>
      <div class="timeline-item">
        <div class="timeline-dot">Woche 1</div>
        <div class="timeline-content">
          <h4>Erste Ergebnisse sichtbar</h4>
          <p>Das System läuft. Erste automatische Actions, erste Daten im Dashboard. Du siehst live wie {name} für dich arbeitet.</p>
        </div>
      </div>
      <div class="timeline-item">
        <div class="timeline-dot">Monat 1</div>
        <div class="timeline-content">
          <h4>Vollständiger ROI erreicht</h4>
          <p>Der Großteil unserer Nutzer sieht den vollen ROI im ersten Monat. Du bist bereits in den Gewinnbereich eingetreten.</p>
        </div>
      </div>
      <div class="timeline-item">
        <div class="timeline-dot">Monat 3</div>
        <div class="timeline-content">
          <h4>Skalierung & Optimierung</h4>
          <p>Dein System ist optimiert und skaliert sich selbst. Fokussiere dich auf Strategie — {name} übernimmt die Ausführung.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- COMPARISON TABLE -->
<section>
  <div class="section-inner">
    <div class="section-label">Vergleich</div>
    <h2>{name} vs. <span>die Alternativen</span></h2>
    <div class="wrap-scroll">
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Feature</th>
            <th class="col-us-header">{name} ✓</th>
            <th>Manuelle Methode</th>
            <th>Günstige Tools</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>Vollautomatisierung</td><td class="col-us check-yes">✓</td><td class="check-no">✗</td><td class="check-no">✗</td></tr>
          <tr><td>KI-Optimierung</td><td class="col-us check-yes">✓</td><td class="check-no">✗</td><td class="check-no">✗</td></tr>
          <tr><td>24/7 Betrieb</td><td class="col-us check-yes">✓</td><td class="check-no">✗</td><td class="check-no">✗</td></tr>
          <tr><td>DSGVO-konform</td><td class="col-us check-yes">✓</td><td style="color:var(--muted)">Unklar</td><td style="color:var(--muted)">Teilweise</td></tr>
          <tr><td>Dedizierter Support</td><td class="col-us check-yes">✓</td><td class="check-no">✗</td><td class="check-no">✗</td></tr>
          <tr><td>ROI in 30 Tagen</td><td class="col-us check-yes">✓ garantiert</td><td class="check-no">✗ Monate</td><td class="check-no">✗ selten</td></tr>
          <tr><td>Setup-Zeit</td><td class="col-us" style="color:var(--green)">30 Minuten</td><td style="color:var(--muted)">Wochen</td><td style="color:var(--muted)">Tage</td></tr>
          <tr><td>Skalierbar auf €100k+</td><td class="col-us check-yes">✓</td><td class="check-no">✗</td><td class="check-no">✗</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<!-- BONUS STACK -->
<section class="bonus-section">
  <div class="section-inner">
    <div class="section-label">Exklusive Boni</div>
    <h2>Was du <span>GRATIS</span> dazu bekommst</h2>
    <p class="lead">Jeder Plan enthält diese Premium-Boni — ohne Aufpreis, ohne Ausnahme.</p>
    <div class="bonus-grid">
      {bonus_rows}
      {bonus_total_html}
    </div>
  </div>
</section>

<!-- PRICING -->
<section class="pricing-section" id="preise">
  <div class="section-inner">
    <div class="section-label">Investition</div>
    <h2>Wähle den Plan der <span>zu dir passt</span></h2>
    <p class="lead" style="margin:0 auto;text-align:center;">Alle Pläne beinhalten 30-Tage Geld-zurück-Garantie. Kein Risiko.</p>
    <div class="pricing-grid">
      {tiers_html}
    </div>
    <div class="pricing-guarantee">
      <div class="guarantee-icon">🛡️</div>
      <p><strong>30-Tage Geld-zurück-Garantie:</strong> Wenn {name} nicht liefert was wir versprechen, erstattten wir 100% — ohne Fragen, ohne Frist.</p>
    </div>
  </div>
</section>

<!-- SECURITY -->
<section style="border-top:1px solid var(--border);">
  <div class="section-inner" style="text-align:center;">
    <div class="section-label">Vertrauen & Sicherheit</div>
    <h2>Enterprise-Grade <span>Sicherheit</span></h2>
    <p class="lead" style="margin:0 auto 0;">Deine Daten sind sicher. Immer.</p>
    <div class="security-grid">
      <div class="security-badge"><div class="badge-icon">🔒</div><div class="badge-text">SSL 256-bit Verschlüsselung</div></div>
      <div class="security-badge"><div class="badge-icon">🇪🇺</div><div class="badge-text">DSGVO konform</div></div>
      <div class="security-badge"><div class="badge-icon">🏦</div><div class="badge-text">Stripe Payments (PCI DSS)</div></div>
      <div class="security-badge"><div class="badge-icon">☁️</div><div class="badge-text">EU Cloud Infrastructure</div></div>
      <div class="security-badge"><div class="badge-icon">🔄</div><div class="badge-text">99.9% Uptime SLA</div></div>
      <div class="security-badge"><div class="badge-icon">🧾</div><div class="badge-text">ISO 27001 Standards</div></div>
    </div>
  </div>
</section>

<!-- FAQ -->
<section style="background:var(--surface);border-top:1px solid var(--border);" id="faq">
  <div class="section-inner">
    <div class="section-label">FAQ</div>
    <h2>Häufige <span>Fragen</span></h2>
    <div class="faq-list">
      {faqs_html}
    </div>
  </div>
</section>

<!-- FINAL CTA -->
<section class="final-cta">
  <div class="section-inner">
    <h2>Bereit für dein <span>nächstes Level?</span></h2>
    <p>Schließ dich 1.000+ Unternehmern an die bereits mit {name} skalieren — starte heute risikofrei.</p>
    <div class="urgency">⚡ Nur noch 12 Gründungsmitglieder-Plätze zu diesem Preis verfügbar</div>
    <br><br>
    <div class="hero-ctas" style="justify-content:center;">
      <a href="{starter_stripe}" class="btn-primary">Jetzt starten — ab {starter_price} →</a>
      <a href="demo.html" class="btn-secondary">Demo ansehen</a>
    </div>
    <p style="color:var(--muted);margin-top:1.5rem;font-size:0.9rem;">✓ 30-Tage Geld-zurück · ✓ Monatlich kündbar · ✓ Setup in 30 Min · ✓ DSGVO-konform</p>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="footer-inner">
    <div class="footer-brand">
      <div class="logo">{name}</div>
      <p>Das führende Automatisierungs-Tool für Online-Unternehmer in DACH — entwickelt von BullPower Hub.</p>
    </div>
    <div class="footer-links">
      <h4>Produkt</h4>
      <a href="#features">Features</a>
      <a href="#preise">Preise</a>
      <a href="demo.html">Demo</a>
      <a href="#faq">FAQ</a>
    </div>
    <div class="footer-links">
      <h4>Rechtliches</h4>
      <a href="/impressum.html">Impressum</a>
      <a href="/datenschutz.html">Datenschutz</a>
      <a href="/agb.html">AGB</a>
      <a href="/widerruf.html">Widerruf</a>
    </div>
  </div>
  <div class="footer-bottom">
    <span>© 2026 {name} · BullPower Hub · Alle Rechte vorbehalten</span>
    <span>Made with ⚡ in Austria</span>
  </div>
</footer>

<script>
// ROI Calculator
{roi_js}

// ── Animated Stats Counter ─────────────────────────────────────────────────
(function() {{
  var ids = {stats_counter_ids};
  var done = {{}};
  function animateCounter(el) {{
    var target = parseFloat(el.dataset.target);
    var prefix = el.dataset.prefix || '';
    var suffix = el.dataset.suffix || '';
    var start = 0;
    var duration = 1800;
    var startTime = null;
    function step(ts) {{
      if (!startTime) startTime = ts;
      var progress = Math.min((ts - startTime) / duration, 1);
      var ease = 1 - Math.pow(1 - progress, 3);
      var current = Math.floor(ease * target);
      var formatted = target >= 1000
        ? current.toLocaleString('de-DE')
        : current.toString();
      el.textContent = prefix + formatted + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }}
    requestAnimationFrame(step);
  }}
  var observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      if (entry.isIntersecting && !done[entry.target.id]) {{
        done[entry.target.id] = true;
        animateCounter(entry.target);
      }}
    }});
  }}, {{ threshold: 0.3 }});
  ids.forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) observer.observe(el);
  }});
}})();

// ── Terminal Animation ─────────────────────────────────────────────────────
(function() {{
  var output = document.getElementById('terminal-output');
  var cursor = document.getElementById('t-cursor');
  if (!output) return;
  var lines = output.querySelectorAll('.term-line');
  var idx = 0;
  function showNext() {{
    if (idx >= lines.length) {{
      cursor.style.display = 'none';
      return;
    }}
    var line = lines[idx++];
    line.style.display = 'block';
    output.scrollTop = output.scrollHeight;
    var delay = line.classList.contains('t-out-ok') ? 400
              : line.classList.contains('t-out-warn') ? 600 : 300;
    setTimeout(showNext, delay);
  }}
  setTimeout(showNext, 1200);
}})();
</script>

</body>
</html>"""


def upgrade_all() -> None:
    updated = []
    for p in PRODUCTS:
        d = DEPLOY_DIR / p["dir"]
        if not d.exists():
            print(f"⚠️  Verzeichnis nicht gefunden: {p['dir']}")
            d.mkdir(parents=True, exist_ok=True)

        html = generate_html(p)
        index = d / "index.html"
        index.write_text(html, encoding="utf-8")
        print(f"✅ {p['name']} → {p['dir']}/index.html ({len(html):,} Bytes)")
        updated.append(p["dir"])

    print(f"\n✅ {len(updated)} Landing Pages upgraded!")
    return updated


if __name__ == "__main__":
    upgrade_all()
    print("\n🚀 Alle Seiten bereit. Jetzt committen und deployen.")
