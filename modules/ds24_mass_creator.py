#!/usr/bin/env python3
"""
DS24 Mass Creator — 1000 Produkte vollautomatisch mit SEO
==========================================================
Erstellt bis zu 1000 Digistore24-Produkte mit:
- SEO-optimierten Texten (KI generiert name, description, tags, meta_keywords)
- 5 parallele Worker für maximale Geschwindigkeit
- Telegram Progress-Updates alle 100 Produkte
- Autonomer täglicher Refill auf Ziel-Anzahl
- Deduplizierung via Supabase ds24_products

Kategorien (30 pro Kategorie = 300 hardcodierte + 700 KI-generierte = 1000 total):
  E-Commerce, KI, Social Media, Finanzen, Business, Gesundheit,
  Persönlichkeit, Kreativität, Sprachen, Lifestyle
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("DS24MassCreator")

DS24_KEY     = os.getenv("DIGISTORE24_API_KEY", "1682000-T8KjTRJXCO1IgXOU5I7am6p6a0AZuqV2BGswDECY")
AFFILIATE_ID = os.getenv("DS24_AFFILIATE_ID", "user37405262")
DS24_BASE    = "https://www.digistore24.com/api/call"
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")

PRICE_DIST = ["17.00"] * 20 + ["27.00"] * 30 + ["37.00"] * 25 + ["47.00"] * 15 + ["67.00"] * 7 + ["97.00"] * 3


def _rand_price() -> str:
    return random.choice(PRICE_DIST)


def _rand_commission(price: str) -> str:
    p = float(price)
    if p <= 27:
        return "50"
    if p <= 47:
        return "45"
    return "40"


# ─── 300 Hardcodierte Templates (30 pro Kategorie) ───────────────────────────

MASS_TEMPLATES: list[dict] = [
    # ── E-Commerce & Dropshipping (30) ───────────────────────────────────────
    {"concept": "Shopify Dropshipping Starterpaket — Erste Bestellung in 7 Tagen", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["shopify", "dropshipping", "online shop"]},
    {"concept": "AliExpress Gewinner-Produkte System 2026", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["aliexpress", "produkte finden", "dropshipping"]},
    {"concept": "eBay Dropshipping Automatisierungs-Blueprint", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["ebay", "dropshipping", "automation"]},
    {"concept": "Amazon FBA Einsteiger Komplettkurs 2026", "niche": "ecommerce", "price": "67.00", "affiliate_commission": "40", "keywords": ["amazon fba", "fulfillment", "verkaufen"]},
    {"concept": "Print-on-Demand Empire aufbauen — Passives Einkommen", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["print on demand", "printify", "passiv"]},
    {"concept": "Shopify SEO Masterclass — Organischer Traffic kostenlos", "niche": "ecommerce", "price": "47.00", "affiliate_commission": "45", "keywords": ["shopify seo", "traffic", "google"]},
    {"concept": "E-Commerce Produktfotografie — Profi-Bilder mit Smartphone", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["produktfotografie", "shopify bilder", "smartphone"]},
    {"concept": "WooCommerce Shop von 0 auf €5000 — Schritt für Schritt", "niche": "ecommerce", "price": "47.00", "affiliate_commission": "45", "keywords": ["woocommerce", "wordpress shop", "online verkaufen"]},
    {"concept": "Etsy Handmade Business — €3000 pro Monat nebenberuflich", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["etsy", "handmade", "verkaufen"]},
    {"concept": "Winning Products Finder — KI analysiert Topseller", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["winning products", "produktforschung", "topseller"]},
    {"concept": "Shopify Email Marketing — Cart Abandonment Flows", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["email marketing", "cart abandonment", "klaviyo"]},
    {"concept": "Dropshipping Lieferanten finden — Direktkontakt ohne Mittelmann", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["lieferanten", "direktimport", "großhandel"]},
    {"concept": "Produktbeschreibungen die verkaufen — Copywriting für Shops", "niche": "ecommerce", "price": "17.00", "affiliate_commission": "50", "keywords": ["produktbeschreibung", "copywriting", "konversion"]},
    {"concept": "E-Commerce Kundensupport automatisieren — Chatbot System", "niche": "ecommerce", "price": "47.00", "affiliate_commission": "45", "keywords": ["kundensupport", "chatbot", "automation"]},
    {"concept": "Shopify Store Design — Conversion-Rate verdoppeln", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["shopify design", "conversion rate", "shop optimierung"]},
    {"concept": "Nischenmarkt finden — Unentdeckte Goldminen für E-Commerce", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["nische finden", "marktanalyse", "e-commerce"]},
    {"concept": "Amazon Affiliate Marketing Geheimstrategie 2026", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["amazon affiliate", "partnerprogramm", "provision"]},
    {"concept": "Fulfillment Optimierung — Versandkosten halbieren", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["fulfillment", "versand", "logistik"]},
    {"concept": "Social Commerce Masterclass — Verkaufen via TikTok Shop", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["tiktok shop", "social commerce", "verkaufen"]},
    {"concept": "Shopify Internationalisierung — Europa in 30 Tagen", "niche": "ecommerce", "price": "47.00", "affiliate_commission": "45", "keywords": ["international verkaufen", "mehrsprachig", "europa"]},
    {"concept": "E-Commerce Buchhaltung — Steuern einfach gemacht", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["buchhaltung", "steuern", "e-commerce"]},
    {"concept": "Retouren minimieren — Kundenzufriedenheit maximieren", "niche": "ecommerce", "price": "17.00", "affiliate_commission": "50", "keywords": ["retouren", "kundenzufriedenheit", "shop"]},
    {"concept": "Bundles & Upsells Strategie — Warenkorbwert verdreifachen", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["upsell", "bundle", "warenkorbwert"]},
    {"concept": "Influencer Marketing für Shopify — 10x Umsatz", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["influencer", "marketing", "shopify umsatz"]},
    {"concept": "Subscription Box Business aufbauen — Wiederkehrende Einnahmen", "niche": "ecommerce", "price": "47.00", "affiliate_commission": "45", "keywords": ["subscription box", "abo", "wiederkehrend"]},
    {"concept": "Produktvalidierung vor dem Launch — Kein Risiko mehr", "niche": "ecommerce", "price": "17.00", "affiliate_commission": "50", "keywords": ["produktvalidierung", "launch", "risiko"]},
    {"concept": "Cross-Selling Automation für Shopify", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["cross selling", "automation", "shopify"]},
    {"concept": "Shop Audit Blueprint — €10.000 Fehler vermeiden", "niche": "ecommerce", "price": "27.00", "affiliate_commission": "50", "keywords": ["shop audit", "fehler", "optimierung"]},
    {"concept": "Digistore24 Affiliate Masterclass — Provision ohne eigenes Produkt", "niche": "ecommerce", "price": "37.00", "affiliate_commission": "50", "keywords": ["digistore24", "affiliate", "provision"]},
    {"concept": "Gumroad Digital Products — Sofort starten, sofort verdienen", "niche": "ecommerce", "price": "17.00", "affiliate_commission": "50", "keywords": ["gumroad", "digitale produkte", "sofort starten"]},
    # ── KI & Automatisierung (30) ─────────────────────────────────────────────
    {"concept": "ChatGPT für Business — 50 profitable Anwendungen", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["chatgpt", "business", "ki anwendungen"]},
    {"concept": "Claude AI Prompt Engineering — Texte auf Expertenebene", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["claude ai", "prompt engineering", "ki texte"]},
    {"concept": "Midjourney Meisterkurs — KI-Bilder verkaufen für €5000/Monat", "niche": "ki", "price": "47.00", "affiliate_commission": "45", "keywords": ["midjourney", "ki bilder", "passives einkommen"]},
    {"concept": "Make.com Automatisierungen — 10h pro Woche sparen", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["make.com", "automatisierung", "workflow"]},
    {"concept": "n8n Self-Hosted Automation — Kosten auf €0 senken", "niche": "ki", "price": "47.00", "affiliate_commission": "45", "keywords": ["n8n", "automation", "self hosted"]},
    {"concept": "Zapier Profi-Kurs — Zapps verbinden ohne Code", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["zapier", "automation", "no code"]},
    {"concept": "KI SEO Content Factory — 30 Blogartikel pro Monat automatisch", "niche": "ki", "price": "47.00", "affiliate_commission": "45", "keywords": ["ki content", "seo blogartikel", "automation"]},
    {"concept": "Python Automatisierung für Nicht-Programmierer", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["python", "automation", "anfänger"]},
    {"concept": "ChatGPT API Integration — Eigenen KI-Service bauen", "niche": "ki", "price": "67.00", "affiliate_commission": "40", "keywords": ["chatgpt api", "ki service", "entwicklung"]},
    {"concept": "Stable Diffusion lokal — Unbegrenzte KI-Bilder gratis", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["stable diffusion", "lokal", "ki bilder"]},
    {"concept": "KI Kundenservice Bot — 24/7 Support ohne Mitarbeiter", "niche": "ki", "price": "67.00", "affiliate_commission": "40", "keywords": ["ki chatbot", "kundenservice", "automation"]},
    {"concept": "Automatisches Reporting System — Daten visualisieren mit KI", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["reporting", "daten", "ki automation"]},
    {"concept": "Voice AI Tools — Podcasts und Audios mit KI erstellen", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["voice ai", "podcast", "audio erstellen"]},
    {"concept": "KI Video Generator — YouTube Kanal ohne Gesicht zeigen", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["ki video", "youtube", "faceless"]},
    {"concept": "Google Sheets Automatisierung mit KI", "niche": "ki", "price": "17.00", "affiliate_commission": "50", "keywords": ["google sheets", "automation", "ki"]},
    {"concept": "WhatsApp Business Bot aufbauen — Leads automatisch qualifizieren", "niche": "ki", "price": "47.00", "affiliate_commission": "45", "keywords": ["whatsapp bot", "leads", "automation"]},
    {"concept": "Telegram Bot erstellen — Subscription Business aufbauen", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["telegram bot", "subscription", "automation"]},
    {"concept": "KI Übersetzer Business — 10 Sprachen, kein Aufwand", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["ki übersetzung", "mehrsprachig", "business"]},
    {"concept": "Airtable No-Code Datenbank — CRM selbst gebaut", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["airtable", "no code", "crm"]},
    {"concept": "Bubble.io App entwickeln ohne Code — SaaS in 30 Tagen", "niche": "ki", "price": "67.00", "affiliate_commission": "40", "keywords": ["bubble.io", "no code app", "saas"]},
    {"concept": "KI Marktforschung — Wettbewerber analysieren in Minuten", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["marktforschung", "wettbewerber", "ki analyse"]},
    {"concept": "Automatisierte Social Media Posts — 1 Stunde, 30 Tage Content", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["social media", "content automation", "ki posts"]},
    {"concept": "KI Buchhaltung — Belege scannen und kategorisieren", "niche": "ki", "price": "17.00", "affiliate_commission": "50", "keywords": ["ki buchhaltung", "belege", "automatisch"]},
    {"concept": "Perplexity AI für Businessrecherche nutzen", "niche": "ki", "price": "17.00", "affiliate_commission": "50", "keywords": ["perplexity ai", "recherche", "business"]},
    {"concept": "KI Landing Pages — Conversion-Rate mit ChatGPT optimieren", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["landing page", "ki optimierung", "conversion"]},
    {"concept": "Notion AI Produktivitätssystem — Komplette Unternehmensstruktur", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["notion ai", "produktivität", "system"]},
    {"concept": "Automatischer Preisfinder — Beste Preise mit KI verhandeln", "niche": "ki", "price": "17.00", "affiliate_commission": "50", "keywords": ["preisvergleich", "ki", "bester preis"]},
    {"concept": "GPT-4 Vision — Bilder analysieren für Business", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["gpt4 vision", "bildanalyse", "business ki"]},
    {"concept": "KI Podcast Editor — Schnitt automatisieren", "niche": "ki", "price": "27.00", "affiliate_commission": "50", "keywords": ["podcast", "ki editor", "audio automation"]},
    {"concept": "Lokale KI mit Ollama — Datenschutz + keine API-Kosten", "niche": "ki", "price": "37.00", "affiliate_commission": "50", "keywords": ["ollama", "lokale ki", "datenschutz"]},
    # ── Social Media Marketing (30) ──────────────────────────────────────────
    {"concept": "Instagram Reels Algorithmus Masterclass 2026", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["instagram reels", "algorithmus", "reichweite"]},
    {"concept": "TikTok Viral Content Formel — 1 Million Views in 90 Tagen", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["tiktok viral", "content", "views"]},
    {"concept": "Pinterest SEO Masterclass — Passiver Traffic für immer", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["pinterest seo", "traffic", "passiv"]},
    {"concept": "LinkedIn Thought Leadership — B2B Kunden gewinnen", "niche": "social", "price": "67.00", "affiliate_commission": "40", "keywords": ["linkedin", "thought leadership", "b2b kunden"]},
    {"concept": "YouTube Shorts Strategie — Kanal explodieren lassen", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["youtube shorts", "kanal wachsen", "strategie"]},
    {"concept": "Facebook Gruppen Business — Community monetarisieren", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["facebook gruppe", "community", "monetarisieren"]},
    {"concept": "Twitter/X Wachstum Blueprint — 10.000 Follower in 60 Tagen", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["twitter wachstum", "follower", "x social"]},
    {"concept": "Threads Marketing Guide — Neue Plattform, erste Mover", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["threads", "instagram", "neue plattform"]},
    {"concept": "Social Media Content Batching — 1 Tag filmen, 1 Monat Content", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["content batching", "social media", "effizienz"]},
    {"concept": "Hashtag Strategie 2026 — Maximale organische Reichweite", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["hashtags", "reichweite", "instagram tiktok"]},
    {"concept": "Influencer werden — Von 0 auf 50.000 Follower", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["influencer werden", "follower aufbauen", "social media"]},
    {"concept": "Brand Deals sichern — Kooperationen als Creator", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["brand deals", "kooperationen", "creator"]},
    {"concept": "Social Media Manager werden — Remote Job Komplettkurs", "niche": "social", "price": "47.00", "affiliate_commission": "45", "keywords": ["social media manager", "remote job", "freelancer"]},
    {"concept": "Storytelling für Business — Kunden durch Geschichten gewinnen", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["storytelling", "business", "kunden gewinnen"]},
    {"concept": "User Generated Content — Kunden als Markenbotschafter", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["ugc", "user generated content", "marketing"]},
    {"concept": "Social Proof System — Bewertungen automatisch sammeln", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["social proof", "bewertungen", "automation"]},
    {"concept": "Live Selling Masterclass — Produkte via Livestream verkaufen", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["live selling", "livestream", "verkaufen"]},
    {"concept": "Content Repurposing System — 1 Video, 20 Posts", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["content repurposing", "effizienz", "social media"]},
    {"concept": "Social Media Analytics meistern — Daten in Wachstum umwandeln", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["analytics", "social media daten", "wachstum"]},
    {"concept": "DM Marketing System — Direkte Nachrichten für Verkauf nutzen", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["dm marketing", "direkte nachrichten", "verkauf"]},
    {"concept": "Podcast mit Social Media verbinden — Maximale Reichweite", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["podcast", "social media", "reichweite"]},
    {"concept": "Reel Hooks — Die ersten 3 Sekunden entscheiden alles", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["reels hooks", "erste sekunden", "engagement"]},
    {"concept": "Social Media für B2B — LinkedIn + Instagram Kombistrategie", "niche": "social", "price": "47.00", "affiliate_commission": "45", "keywords": ["b2b social media", "linkedin instagram", "strategie"]},
    {"concept": "Creator Burnout vermeiden — Content ohne Erschöpfung", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["creator burnout", "nachhaltig", "content"]},
    {"concept": "Snapchat Marketing 2026 — Jüngere Zielgruppe erreichen", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["snapchat", "marketing", "junge zielgruppe"]},
    {"concept": "BeReal & neue Plattformen — First Mover Vorteil sichern", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["neue plattformen", "first mover", "social media"]},
    {"concept": "Social Commerce Funnel — Von Post zu Kauf in 3 Schritten", "niche": "social", "price": "37.00", "affiliate_commission": "50", "keywords": ["social commerce", "funnel", "conversion"]},
    {"concept": "Micro-Influencer Strategie — Klein, aber wirkungsvoll", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["micro influencer", "engagement", "strategie"]},
    {"concept": "Social Media Scheduling — Tools und Systeme für Effizienz", "niche": "social", "price": "17.00", "affiliate_commission": "50", "keywords": ["scheduling", "social media tools", "effizienz"]},
    {"concept": "Viral Hooks Formel — Jeder Post bekommt Aufmerksamkeit", "niche": "social", "price": "27.00", "affiliate_commission": "50", "keywords": ["viral hooks", "aufmerksamkeit", "reichweite"]},
    # ── Finanzen & Investment (30) ────────────────────────────────────────────
    {"concept": "ETF Portfolio aufbauen — €500/Monat anlegen und vergessen", "niche": "finanzen", "price": "27.00", "affiliate_commission": "50", "keywords": ["etf", "portfolio", "geldanlage"]},
    {"concept": "Krypto für Einsteiger — Bitcoin sicher kaufen 2026", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["krypto", "bitcoin", "sicher kaufen"]},
    {"concept": "DeFi Passives Einkommen — Krypto für sich arbeiten lassen", "niche": "finanzen", "price": "67.00", "affiliate_commission": "40", "keywords": ["defi", "passives einkommen", "krypto"]},
    {"concept": "Dividenden-Portfolio — €1000/Monat aus Aktien", "niche": "finanzen", "price": "47.00", "affiliate_commission": "45", "keywords": ["dividenden", "aktien", "passives einkommen"]},
    {"concept": "Immobilien Investment — Erste Wohnung kaufen ohne Eigenkapital", "niche": "finanzen", "price": "97.00", "affiliate_commission": "40", "keywords": ["immobilien", "wohnung kaufen", "investment"]},
    {"concept": "Trading Grundlagen — Technische Analyse für Anfänger", "niche": "finanzen", "price": "47.00", "affiliate_commission": "45", "keywords": ["trading", "technische analyse", "anfänger"]},
    {"concept": "Steueroptimierung 2026 — Legal €5000 mehr behalten", "niche": "finanzen", "price": "97.00", "affiliate_commission": "40", "keywords": ["steueroptimierung", "steuern sparen", "legal"]},
    {"concept": "Notgroschen aufbauen — Finanzielle Sicherheit in 12 Monaten", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["notgroschen", "finanzielle sicherheit", "sparen"]},
    {"concept": "Schulden schnell tilgen — Debt Snowball Methode", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["schulden tilgen", "debt snowball", "finanzen"]},
    {"concept": "Altersvorsorge optimieren — ETF statt Riester", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["altersvorsorge", "etf rente", "riester alternative"]},
    {"concept": "Aktien-Depot eröffnen — Brokerwahl und erste Käufe", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["depot", "broker", "aktien kaufen"]},
    {"concept": "Value Investing nach Warren Buffett — Unterbewertete Aktien finden", "niche": "finanzen", "price": "47.00", "affiliate_commission": "45", "keywords": ["value investing", "warren buffett", "aktien analyse"]},
    {"concept": "Forex Trading System — Währungen profitabel handeln", "niche": "finanzen", "price": "67.00", "affiliate_commission": "40", "keywords": ["forex", "währungen handeln", "trading system"]},
    {"concept": "Crowdfunding Investments — In Startups investieren ab €100", "niche": "finanzen", "price": "27.00", "affiliate_commission": "50", "keywords": ["crowdfunding", "startup investieren", "crowdinvesting"]},
    {"concept": "Girokonto optimieren — Null Gebühren und Cashback", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["girokonto", "gebühren sparen", "cashback"]},
    {"concept": "Budgetplan erstellen — Haushaltsbuch digital", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["budgetplan", "haushaltsbuch", "finanzen"]},
    {"concept": "Optionen Trading — Put und Call verständlich erklärt", "niche": "finanzen", "price": "67.00", "affiliate_commission": "40", "keywords": ["optionen", "put call", "trading"]},
    {"concept": "Wertpapiere vererben — Depot optimal übertragen", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["depot vererben", "erbschaft", "wertpapiere"]},
    {"concept": "Krypto Steuern — Richtig deklarieren und Strafen vermeiden", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["krypto steuern", "deklarieren", "bitcoin steuer"]},
    {"concept": "P2P Kredite — Zinsen bis 12% durch Direktvergabe", "niche": "finanzen", "price": "27.00", "affiliate_commission": "50", "keywords": ["p2p kredite", "zinsen", "investment"]},
    {"concept": "Gold und Silber kaufen — Krisen sicher überstehen", "niche": "finanzen", "price": "27.00", "affiliate_commission": "50", "keywords": ["gold kaufen", "silber", "krisensicherheit"]},
    {"concept": "REITs — In Immobilien investieren ohne Eigenheim", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["reits", "immobilien aktien", "dividenden"]},
    {"concept": "Finanzielle Freiheit in 10 Jahren — FIRE Methode", "niche": "finanzen", "price": "47.00", "affiliate_commission": "45", "keywords": ["fire movement", "finanzielle freiheit", "früh rente"]},
    {"concept": "Lebensversicherung kündigen — Besser anlegen", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["lebensversicherung", "kündigen", "alternativen"]},
    {"concept": "Indexfonds vs. aktive Fonds — Was wirklich besser ist", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["indexfonds", "aktive fonds", "vergleich"]},
    {"concept": "NFT investieren — Chancen und Risiken 2026", "niche": "finanzen", "price": "37.00", "affiliate_commission": "50", "keywords": ["nft", "investieren", "digital art"]},
    {"concept": "Renten-ETF Sparplan — Jeden Monat automatisch aufbauen", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["sparplan", "renten etf", "automatisch"]},
    {"concept": "Vermieter werden — Erste Immobilie kaufen und vermieten", "niche": "finanzen", "price": "67.00", "affiliate_commission": "40", "keywords": ["vermieter", "immobilie", "mieteinnahmen"]},
    {"concept": "Anleihen verstehen — Sicherer Baustein im Portfolio", "niche": "finanzen", "price": "17.00", "affiliate_commission": "50", "keywords": ["anleihen", "bonds", "portfolio"]},
    {"concept": "Behavioral Finance — Psychologische Fallen beim Investieren", "niche": "finanzen", "price": "27.00", "affiliate_commission": "50", "keywords": ["behavioral finance", "anlegerpsychologie", "fehler vermeiden"]},
    # ── Business & Freelancing (30) ──────────────────────────────────────────
    {"concept": "Freelance Business aufbauen — Erste Kunden in 30 Tagen", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["freelancer", "erste kunden", "selbstständig"]},
    {"concept": "Online Kurs erstellen — Von Idee zu €10.000", "niche": "business", "price": "67.00", "affiliate_commission": "40", "keywords": ["online kurs", "erstellen", "verkaufen"]},
    {"concept": "Copywriting Meisterkurs — Worte in Geld verwandeln", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["copywriting", "texten", "verkaufstexte"]},
    {"concept": "Personal Brand aufbauen — Experte werden in 90 Tagen", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["personal brand", "experte", "positionierung"]},
    {"concept": "SaaS ohne Code — Produkt in 60 Tagen launchen", "niche": "business", "price": "97.00", "affiliate_commission": "40", "keywords": ["saas", "no code", "produkt launch"]},
    {"concept": "Webdesign Freelancer — €3000 pro Projekt", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["webdesign", "freelancer", "projekte"]},
    {"concept": "Consulting starten — Expertise verkaufen ab €150/Stunde", "niche": "business", "price": "67.00", "affiliate_commission": "40", "keywords": ["consulting", "beratung", "stundensatz"]},
    {"concept": "Fiverr Top Seller werden — Gig Optimierung System", "niche": "business", "price": "27.00", "affiliate_commission": "50", "keywords": ["fiverr", "top seller", "gig"]},
    {"concept": "Upwork Profil optimieren — Ersten Job in 7 Tagen", "niche": "business", "price": "27.00", "affiliate_commission": "50", "keywords": ["upwork", "profil", "freelancer job"]},
    {"concept": "Agency aufbauen — Von Solo zu Team in 12 Monaten", "niche": "business", "price": "97.00", "affiliate_commission": "40", "keywords": ["agency", "aufbauen", "team wachstum"]},
    {"concept": "Preise erhöhen — Kunden zahlen mehr für gleiche Arbeit", "niche": "business", "price": "27.00", "affiliate_commission": "50", "keywords": ["preise erhöhen", "honorar", "freelancer"]},
    {"concept": "Kaltakquise eliminieren — Kunden kommen zu dir", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["kaltakquise", "inbound marketing", "kunden gewinnen"]},
    {"concept": "Digitale Produkte — Ebooks und Vorlagen verkaufen", "niche": "business", "price": "17.00", "affiliate_commission": "50", "keywords": ["ebooks", "vorlagen", "digitale produkte"]},
    {"concept": "Business auf Autopilot — Systeme die für dich arbeiten", "niche": "business", "price": "67.00", "affiliate_commission": "40", "keywords": ["autopilot business", "systeme", "delegation"]},
    {"concept": "Angebote schreiben die überzeugen — Conversion Masterclass", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["angebote schreiben", "conversion", "business"]},
    {"concept": "Remote Work Transition — Bürojob zum Remote Job", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["remote work", "homeoffice", "job wechsel"]},
    {"concept": "Newsletter Monetarisieren — Paid Subscriber gewinnen", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["newsletter", "monetarisierung", "subscriber"]},
    {"concept": "Coaching Business starten — Erste zahlende Klienten", "niche": "business", "price": "67.00", "affiliate_commission": "40", "keywords": ["coaching", "business", "klienten gewinnen"]},
    {"concept": "Membership Site aufbauen — Wiederkehrende Einnahmen", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["membership", "abo business", "community"]},
    {"concept": "Verhandlungsführung für Freelancer — Mehr Geld aushandeln", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["verhandlung", "freelancer", "honorar"]},
    {"concept": "Business Skalierung — Von €5000 auf €50.000 pro Monat", "niche": "business", "price": "97.00", "affiliate_commission": "40", "keywords": ["skalierung", "business wachstum", "umsatz steigern"]},
    {"concept": "Outsourcing Meisterkurs — Aufgaben delegieren", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["outsourcing", "delegieren", "virtual assistant"]},
    {"concept": "Buchveröffentlichung — Selfpublishing Komplettkurs", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["selfpublishing", "buch veröffentlichen", "amazon kdp"]},
    {"concept": "Kundenakquise mit LinkedIn — 10 Leads pro Woche", "niche": "business", "price": "37.00", "affiliate_commission": "50", "keywords": ["linkedin akquise", "leads", "b2b"]},
    {"concept": "Steuergestaltung Selbstständige — GmbH vs. Einzelunternehmen", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["gmbh", "einzelunternehmen", "steuern"]},
    {"concept": "Exit Strategie — Business verkaufen für das Maximum", "niche": "business", "price": "97.00", "affiliate_commission": "40", "keywords": ["exit strategie", "business verkaufen", "unternehmenswert"]},
    {"concept": "Produktivitätssystem — In 4h schaffen was andere in 8h brauchen", "niche": "business", "price": "27.00", "affiliate_commission": "50", "keywords": ["produktivität", "system", "effizienz"]},
    {"concept": "Networking meistern — Kontakte in Kunden verwandeln", "niche": "business", "price": "27.00", "affiliate_commission": "50", "keywords": ["networking", "kontakte", "kunden"]},
    {"concept": "Testimonials und Case Studies — Social Proof aufbauen", "niche": "business", "price": "17.00", "affiliate_commission": "50", "keywords": ["testimonials", "case studies", "social proof"]},
    {"concept": "Recurring Revenue Model — Jeder Monat sicheres Einkommen", "niche": "business", "price": "47.00", "affiliate_commission": "45", "keywords": ["recurring revenue", "abo", "sicheres einkommen"]},
    # ── Gesundheit & Fitness (30) ────────────────────────────────────────────
    {"concept": "Intermittent Fasting 16:8 — Einfach und effektiv abnehmen", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["fasten", "16:8", "abnehmen"]},
    {"concept": "Home Workout System — Traumkörper ohne Geräte", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["home workout", "körper", "training"]},
    {"concept": "Keto Diät Starter — Erste 4 Wochen Plan", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["keto", "diät", "ernährungsplan"]},
    {"concept": "Muskelaufbau Plan — 12 Wochen zur Traumfigur", "niche": "gesundheit", "price": "37.00", "affiliate_commission": "50", "keywords": ["muskelaufbau", "training", "ernährung"]},
    {"concept": "Rückenschmerzen loswerden — 10 Minuten täglich", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["rückenschmerzen", "übungen", "therapie"]},
    {"concept": "Vegan starten — 30-Tage Challenge mit Rezepten", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["vegan", "30 tage", "rezepte"]},
    {"concept": "Schlafqualität verbessern — In 7 Tagen besser schlafen", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["schlaf verbessern", "einschlafen", "energie"]},
    {"concept": "Stressabbau Programm — Burnout nie wieder", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["stress abbauen", "burnout", "entspannung"]},
    {"concept": "Meditation für Anfänger — 10 Minuten täglich verändern alles", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["meditation", "anfänger", "achtsamkeit"]},
    {"concept": "Yoga Intensivkurs — Flexibilität und Kraft in 8 Wochen", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["yoga", "flexibilität", "kraft"]},
    {"concept": "Marathon Vorbereitung — Von der Couch zum Ziel", "niche": "gesundheit", "price": "37.00", "affiliate_commission": "50", "keywords": ["marathon", "laufen", "vorbereitung"]},
    {"concept": "Gut Health Programm — Darm gesund = alles gesund", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["darmgesundheit", "gut health", "probiotika"]},
    {"concept": "Zuckerentzug Plan — 21 Tage ohne Zucker", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["zuckerentzug", "zucker frei", "gesünder leben"]},
    {"concept": "Meal Prep System — Gesund essen ohne Stress", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["meal prep", "kochen", "wochenplanung"]},
    {"concept": "Immunsystem stärken — Natürliche Methoden", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["immunsystem", "stärken", "natürlich"]},
    {"concept": "Hormonbalance für Frauen — Natürlich ins Gleichgewicht", "niche": "gesundheit", "price": "37.00", "affiliate_commission": "50", "keywords": ["hormone", "frauengesundheit", "balance"]},
    {"concept": "Testosteron optimieren — Natürlich und ohne Mittel", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["testosteron", "männergesundheit", "optimieren"]},
    {"concept": "Anti-Aging Protokoll — Jünger aussehen mit 50", "niche": "gesundheit", "price": "47.00", "affiliate_commission": "45", "keywords": ["anti aging", "jünger aussehen", "longevity"]},
    {"concept": "Atemübungen Masterclass — Wim Hof Methode und mehr", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["atemübungen", "wim hof", "stressabbau"]},
    {"concept": "Supplements Guide — Was wirklich wirkt (und was nicht)", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["supplements", "nahrungsergänzung", "guide"]},
    {"concept": "Ernährungsplan erstellen — Individuell und nachhaltig", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["ernährungsplan", "individuell", "gesund"]},
    {"concept": "CrossFit Einsteiger — Erste 8 Wochen sicher trainieren", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["crossfit", "einsteiger", "training"]},
    {"concept": "Stretching Routine — Täglich 15 Minuten für Beweglichkeit", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["stretching", "beweglichkeit", "routine"]},
    {"concept": "Kaltwasser Duschen — Energie und Immunsystem boosten", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["kaltwasser", "kalt duschen", "energie"]},
    {"concept": "Gesunde Snacks — 50 Rezepte für zwischendurch", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["gesunde snacks", "rezepte", "abnehmen"]},
    {"concept": "Personal Trainer Ausbildung Vorbereitung", "niche": "gesundheit", "price": "47.00", "affiliate_commission": "45", "keywords": ["personal trainer", "ausbildung", "fitness"]},
    {"concept": "Schwangerschaftsyoga — Sicher und sanft in der Schwangerschaft", "niche": "gesundheit", "price": "27.00", "affiliate_commission": "50", "keywords": ["schwangerschaftsyoga", "schwangerschaft", "yoga"]},
    {"concept": "Kinderernährung — Gesund und lecker für die ganze Familie", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["kinderernährung", "gesund", "familie"]},
    {"concept": "Biohacking Basics — Körper und Geist optimieren", "niche": "gesundheit", "price": "37.00", "affiliate_commission": "50", "keywords": ["biohacking", "optimieren", "performance"]},
    {"concept": "Sporternährung Guide — Vor und nach dem Training richtig essen", "niche": "gesundheit", "price": "17.00", "affiliate_commission": "50", "keywords": ["sporternährung", "training", "ernährung"]},
    # ── Persönlichkeitsentwicklung (30) ─────────────────────────────────────
    {"concept": "Selbstvertrauen aufbauen — 30-Tage Programm", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["selbstvertrauen", "persönlichkeit", "programm"]},
    {"concept": "Introvertiert erfolgreich — Stärken der Stille nutzen", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["introvertiert", "erfolg", "stärken"]},
    {"concept": "Gewohnheiten ändern — Das 2-Minuten-Gesetz", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["gewohnheiten", "veränderung", "routine"]},
    {"concept": "Prokrastination überwinden — Jetzt handeln statt warten", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["prokrastination", "motivation", "handeln"]},
    {"concept": "Emotionale Intelligenz — Gefühle verstehen und nutzen", "niche": "persoenlichkeit", "price": "37.00", "affiliate_commission": "50", "keywords": ["emotionale intelligenz", "eq", "gefühle"]},
    {"concept": "Angst überwinden — Komfortzone dauerhaft erweitern", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["angst überwinden", "komfortzone", "mut"]},
    {"concept": "Public Speaking — Reden halten ohne Lampenfieber", "niche": "persoenlichkeit", "price": "37.00", "affiliate_commission": "50", "keywords": ["public speaking", "reden", "lampenfieber"]},
    {"concept": "Nein sagen lernen — Grenzen setzen ohne Schuldgefühle", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["nein sagen", "grenzen", "selbstbehauptung"]},
    {"concept": "Morning Routine der Erfolgreichsten — 5-Uhr-Morgen", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["morning routine", "früh aufstehen", "erfolg"]},
    {"concept": "Ziele setzen und erreichen — OKR Methode", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["ziele setzen", "okr", "erreichen"]},
    {"concept": "Stressresistenz aufbauen — Resilienz Masterclass", "niche": "persoenlichkeit", "price": "37.00", "affiliate_commission": "50", "keywords": ["resilienz", "stress", "widerstandsfähigkeit"]},
    {"concept": "Dankbarkeit täglich üben — Positives Denken wirklich", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["dankbarkeit", "positiv denken", "glück"]},
    {"concept": "Journaling System — Klarheit durch Schreiben gewinnen", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["journaling", "tagebuch", "klarheit"]},
    {"concept": "NLP Grundlagen — Kommunikation und Überzeugung", "niche": "persoenlichkeit", "price": "47.00", "affiliate_commission": "45", "keywords": ["nlp", "kommunikation", "überzeugung"]},
    {"concept": "Minimalismus als Lebensstil — Weniger für mehr", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["minimalismus", "lebensstil", "simpel leben"]},
    {"concept": "Digital Detox — Smartphone Sucht überwinden", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["digital detox", "smartphone", "sucht"]},
    {"concept": "Konzentration stärken — Deep Work Methode", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["konzentration", "deep work", "fokus"]},
    {"concept": "Beziehungen verbessern — Kommunikation und Empathie", "niche": "persoenlichkeit", "price": "37.00", "affiliate_commission": "50", "keywords": ["beziehungen", "kommunikation", "empathie"]},
    {"concept": "Körpersprache meistern — Nonverbal überzeugen", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["körpersprache", "nonverbal", "überzeugung"]},
    {"concept": "Lesen Geschwindigkeit verdoppeln — Speed Reading", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["speed reading", "schnell lesen", "lernen"]},
    {"concept": "Gedächtnis stärken — Mnemonik Techniken", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["gedächtnis", "mnemonik", "merktechniken"]},
    {"concept": "Sozialer Erfolg — Netzwerk aufbauen ohne Networking-Events", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["sozial", "netzwerk", "beziehungen"]},
    {"concept": "Kreativität entfalten — Blockaden lösen", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["kreativität", "blockaden", "entfalten"]},
    {"concept": "Entscheidungen treffen — Systematisch und sicher", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["entscheidungen", "systematisch", "klarheit"]},
    {"concept": "Perfektionismus überwinden — Fertig ist besser als perfekt", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["perfektionismus", "überwinden", "fertigstellen"]},
    {"concept": "Selbstliebe entwickeln — Innere Stimme transformieren", "niche": "persoenlichkeit", "price": "27.00", "affiliate_commission": "50", "keywords": ["selbstliebe", "innere stimme", "selbstakzeptanz"]},
    {"concept": "Werte definieren — Authentisch leben nach inneren Prinzipien", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["werte", "authentisch", "prinzipien"]},
    {"concept": "Kritik annehmen — Konstruktiv wachsen", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["kritik", "feedback", "wachstum"]},
    {"concept": "Charisma entwickeln — Magnetische Ausstrahlung", "niche": "persoenlichkeit", "price": "37.00", "affiliate_commission": "50", "keywords": ["charisma", "ausstrahlung", "persönlichkeit"]},
    {"concept": "Ikigai finden — Sinn und Zweck im Leben", "niche": "persoenlichkeit", "price": "17.00", "affiliate_commission": "50", "keywords": ["ikigai", "sinn", "zweck leben"]},
    # ── Kreativität & Tech (30) ──────────────────────────────────────────────
    {"concept": "Canva Profi-Kurs — Designs die verkaufen", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["canva", "design", "grafik"]},
    {"concept": "Adobe Photoshop für Anfänger — In 10 Stunden zum Profi", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["photoshop", "bildbearbeitung", "anfänger"]},
    {"concept": "Final Cut Pro Meisterkurs — Professioneller Videoschnitt", "niche": "kreativ", "price": "47.00", "affiliate_commission": "45", "keywords": ["final cut", "video editing", "mac"]},
    {"concept": "Podcast starten — Technisches Setup unter €200", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["podcast starten", "setup", "mikrofon"]},
    {"concept": "Musik produzieren — Ableton für Anfänger", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["musik produzieren", "ableton", "beats"]},
    {"concept": "Fotografie Grundlagen — Kamera verstehen lernen", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["fotografie", "kamera", "grundlagen"]},
    {"concept": "Webdesign Grundlagen — HTML CSS in 20 Stunden", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["webdesign", "html css", "anfänger"]},
    {"concept": "WordPress Masterclass — Professionelle Website ohne Code", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["wordpress", "website", "no code"]},
    {"concept": "Logo Design Grundlagen — Marke visuell aufbauen", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["logo design", "marke", "branding"]},
    {"concept": "3D Modellierung Einsteiger — Blender von 0", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["blender", "3d modellierung", "animation"]},
    {"concept": "Lightroom Fotobearbeitung — Professionelle Presets", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["lightroom", "fotobearbeitung", "presets"]},
    {"concept": "Illustration mit iPad — Procreate Komplettkurs", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["procreate", "illustration", "ipad"]},
    {"concept": "Drohnen Fotografie — DJI Profi-Setup", "niche": "kreativ", "price": "47.00", "affiliate_commission": "45", "keywords": ["drohne", "luftfotografie", "dji"]},
    {"concept": "Figma UI Design — App Mockups für Anfänger", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["figma", "ui design", "mockup"]},
    {"concept": "Excel für Business — Daten meistern ohne Stress", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["excel", "business", "daten"]},
    {"concept": "Python in 30 Tagen — Programmieren für Anfänger", "niche": "kreativ", "price": "47.00", "affiliate_commission": "45", "keywords": ["python", "programmieren", "30 tage"]},
    {"concept": "JavaScript Grundlagen — Interaktive Webseiten", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["javascript", "web", "programmieren"]},
    {"concept": "Notion Mastery — Komplettes System aufbauen", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["notion", "system", "organisation"]},
    {"concept": "SEO Technisch — Core Web Vitals optimieren", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["technisches seo", "core web vitals", "google"]},
    {"concept": "Google Analytics 4 — Daten richtig interpretieren", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["google analytics", "daten", "auswertung"]},
    {"concept": "Typeface Design — Eigene Schriften erstellen", "niche": "kreativ", "price": "47.00", "affiliate_commission": "45", "keywords": ["schriftdesign", "typeface", "font"]},
    {"concept": "Motion Graphics — After Effects für Einsteiger", "niche": "kreativ", "price": "47.00", "affiliate_commission": "45", "keywords": ["motion graphics", "after effects", "animation"]},
    {"concept": "Webflow Masterclass — No-Code Webdesign Profi", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["webflow", "no code", "webdesign"]},
    {"concept": "Cybersecurity Grundlagen — Daten sicher schützen", "niche": "kreativ", "price": "37.00", "affiliate_commission": "50", "keywords": ["cybersecurity", "datenschutz", "sicherheit"]},
    {"concept": "Netzwerk Administration — Home Lab aufbauen", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["netzwerk", "administration", "home lab"]},
    {"concept": "Video Thumbnail Design — Click-Through-Rate maximieren", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["thumbnail", "youtube", "click rate"]},
    {"concept": "Infografiken erstellen — Komplexes einfach erklären", "niche": "kreativ", "price": "17.00", "affiliate_commission": "50", "keywords": ["infografik", "design", "visualisierung"]},
    {"concept": "Sound Design — Musikeffekte für Video und Podcasts", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["sound design", "musikeffekte", "audio"]},
    {"concept": "Twitch Streaming Aufbauen — Gaming Kanal monetarisieren", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["twitch", "streaming", "gaming"]},
    {"concept": "Comic Zeichnen — Von der Idee zur fertigen Seite", "niche": "kreativ", "price": "27.00", "affiliate_commission": "50", "keywords": ["comic", "zeichnen", "illustration"]},
    # ── Sprachen & Bildung (30) ──────────────────────────────────────────────
    {"concept": "Englisch B2 Niveau in 90 Tagen — Intensivprogramm", "niche": "sprachen", "price": "47.00", "affiliate_commission": "45", "keywords": ["englisch lernen", "b2", "intensiv"]},
    {"concept": "Business English — Professionell kommunizieren auf Englisch", "niche": "sprachen", "price": "37.00", "affiliate_commission": "50", "keywords": ["business english", "professionell", "kommunikation"]},
    {"concept": "Spanisch für Reisende — Überleben auf Spanisch", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["spanisch", "reisen", "überleben"]},
    {"concept": "Französisch Grundkurs — Bonjour bis Konversation", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["französisch", "grundkurs", "lernen"]},
    {"concept": "Japanisch lernen — Hiragana und Katakana in 2 Wochen", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["japanisch", "hiragana", "katakana"]},
    {"concept": "Mandarin Chinesisch — Erste 1000 Wörter und Sätze", "niche": "sprachen", "price": "37.00", "affiliate_commission": "50", "keywords": ["chinesisch", "mandarin", "lernen"]},
    {"concept": "Türkisch für Anfänger — Urlaub und mehr", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["türkisch", "anfänger", "urlaub"]},
    {"concept": "Arabisch Grundlagen — Alphabet und Basisvokabular", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["arabisch", "alphabet", "grundlagen"]},
    {"concept": "Portugiesisch — Brasilianisch vs. Europäisch verstehen", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["portugiesisch", "brasilianisch", "lernen"]},
    {"concept": "Russisch lesen lernen — Kyrillisch in 7 Tagen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["russisch", "kyrillisch", "lesen"]},
    {"concept": "Niederländisch für Deutschsprachige — Schnell und einfach", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["niederländisch", "deutsch", "lernen"]},
    {"concept": "Polnisch Grundkurs — Für Reise und Beruf", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["polnisch", "grundkurs", "beruf"]},
    {"concept": "Sprachlernen mit KI — Duolingo und mehr effizient nutzen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["sprachenlernen", "ki", "duolingo"]},
    {"concept": "Sprachreise vorbereiten — Maximaler Lernerfolg", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["sprachreise", "vorbereitung", "lernen"]},
    {"concept": "Akkzentrückgang — Hochdeutsch für Nicht-Muttersprachler", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["hochdeutsch", "akzent", "aussprache"]},
    {"concept": "Lernen lernen — Wissenschaftliche Methoden für alle", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["lernen", "methoden", "effizienz"]},
    {"concept": "Schneller lesen — 1 Buch pro Woche", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["schnell lesen", "buch", "lernen"]},
    {"concept": "Gedächtnistraining — Vokabeln nie wieder vergessen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["vokabeln", "gedächtnis", "lernen"]},
    {"concept": "IELTS Vorbereitung — 7.0 Band in 8 Wochen", "niche": "sprachen", "price": "47.00", "affiliate_commission": "45", "keywords": ["ielts", "vorbereitung", "prüfung"]},
    {"concept": "TOEFL Crash Course — Universität im Ausland", "niche": "sprachen", "price": "47.00", "affiliate_commission": "45", "keywords": ["toefl", "englisch", "universität"]},
    {"concept": "Italienisch lernen — La dolce vita verstehen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["italienisch", "lernen", "italien"]},
    {"concept": "Schwedisch Grundlagen — Skandinavien verstehen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["schwedisch", "skandinavien", "grundlagen"]},
    {"concept": "Lateinisch Einführung — Antike Texte lesen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["lateinisch", "antike", "texte"]},
    {"concept": "Gebärdensprache Basics — Inklusiv kommunizieren", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["gebärdensprache", "dgs", "inklusion"]},
    {"concept": "Sprachkurs strukturieren — Eigenen Kurs verkaufen", "niche": "sprachen", "price": "37.00", "affiliate_commission": "50", "keywords": ["sprachkurs", "erstellen", "verkaufen"]},
    {"concept": "Übersetzer werden — Beruflich übersetzen ohne Studium", "niche": "sprachen", "price": "37.00", "affiliate_commission": "50", "keywords": ["übersetzer", "beruf", "selbstständig"]},
    {"concept": "Koreanisch für K-Pop Fans — Hangul lernen", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["koreanisch", "hangul", "k-pop"]},
    {"concept": "Griechisch Reisekurs — Urlaub auf Griechisch", "niche": "sprachen", "price": "17.00", "affiliate_commission": "50", "keywords": ["griechisch", "urlaub", "reise"]},
    {"concept": "Zweisprachige Kinder fördern — Mehrsprachigkeit von klein auf", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["zweisprachig", "kinder", "mehrsprachigkeit"]},
    {"concept": "Aussprache perfektionieren — Muttersprachler klingen", "niche": "sprachen", "price": "27.00", "affiliate_commission": "50", "keywords": ["aussprache", "englisch", "muttersprachler"]},
    # ── Lifestyle & Reisen (30) ──────────────────────────────────────────────
    {"concept": "Digitaler Nomade werden — 6 Monate Vorbereitung", "niche": "lifestyle", "price": "47.00", "affiliate_commission": "45", "keywords": ["digitaler nomade", "remote arbeiten", "reisen"]},
    {"concept": "Weltreise günstig — Budget Reisen unter €30 pro Tag", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["weltreise", "budget", "günstig reisen"]},
    {"concept": "Auswandern nach Portugal — Alles was du wissen musst", "niche": "lifestyle", "price": "37.00", "affiliate_commission": "50", "keywords": ["auswandern", "portugal", "expat"]},
    {"concept": "Van Life starten — Umbau und erstes Jahr", "niche": "lifestyle", "price": "37.00", "affiliate_commission": "50", "keywords": ["van life", "umbau", "reisen"]},
    {"concept": "Slow Travel Masterclass — Tiefer reisen, nicht weiter", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["slow travel", "reisen", "tiefe"]},
    {"concept": "Backpacking Einsteiger — Rucksack, Route, Budget", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["backpacking", "einsteiger", "rucksack"]},
    {"concept": "Thailand Auswandern — Visum, Wohnen, Leben", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["thailand", "auswandern", "expat"]},
    {"concept": "Reisefotografie Masterclass — Unvergessliche Bilder", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["reisefotografie", "bilder", "kamera"]},
    {"concept": "Segeln lernen — Freie Meere, freies Leben", "niche": "lifestyle", "price": "47.00", "affiliate_commission": "45", "keywords": ["segeln", "lernen", "boot"]},
    {"concept": "Bergsteigen für Anfänger — Sicherheit und Ausrüstung", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["bergsteigen", "anfänger", "sicherheit"]},
    {"concept": "Camping System — Natur genießen ohne Stress", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["camping", "system", "natur"]},
    {"concept": "Pilates zu Hause — Kraft und Flexibilität im Wohnzimmer", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["pilates", "zuhause", "fitness"]},
    {"concept": "Zero Waste Leben — Plastikfrei in 30 Tagen", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["zero waste", "plastikfrei", "nachhaltig"]},
    {"concept": "Tiny House Leben — Weniger Platz, mehr Freiheit", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["tiny house", "minimalismus", "freiheit"]},
    {"concept": "Hunde Training — Gehorsam in 4 Wochen", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["hunde training", "gehorsam", "erziehung"]},
    {"concept": "Eigenheim renovieren — Küche und Bad DIY", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["renovieren", "diy", "zuhause"]},
    {"concept": "Kochen für Anfänger — 30 Grundrezepte beherrschen", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["kochen", "anfänger", "grundrezepte"]},
    {"concept": "Weinkenner werden — Wein verstehen und genießen", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["wein", "weinkenner", "genuss"]},
    {"concept": "Bier brauen Zuhause — Craft Beer Einsteiger", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["bier brauen", "craft beer", "zuhause"]},
    {"concept": "Gartengestaltung Einsteiger — Gemüse und Blumen", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["gartengestaltung", "gemüse", "garten"]},
    {"concept": "Nachhaltigkeit im Alltag — 100 einfache Gewohnheiten", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["nachhaltigkeit", "alltag", "umwelt"]},
    {"concept": "Airbnb Superhost werden — Rating 5 Sterne garantiert", "niche": "lifestyle", "price": "37.00", "affiliate_commission": "50", "keywords": ["airbnb", "superhost", "5 sterne"]},
    {"concept": "Housesitting — Kostenlos um die Welt reisen", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["housesitting", "kostenlos reisen", "welt"]},
    {"concept": "Reise Hacks — Upgrade und Meilen sammeln", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["reise hacks", "meilen", "upgrade"]},
    {"concept": "Workation Planen — Arbeiten von überall optimal", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["workation", "remote", "reisen"]},
    {"concept": "Auswandern nach Österreich — Für Deutsche Schritt für Schritt", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["auswandern österreich", "für deutsche", "umzug"]},
    {"concept": "Fernreise mit Baby — Sicher und entspannt", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["fernreise", "baby", "familie reisen"]},
    {"concept": "Motorrad Reisen Europa — Route, Ausrüstung, Kosten", "niche": "lifestyle", "price": "27.00", "affiliate_commission": "50", "keywords": ["motorrad reisen", "europa", "route"]},
    {"concept": "Pilgerweg Jakobsweg — Vorbereitung und Erlebnis", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["jakobsweg", "pilgern", "vorbereitung"]},
    {"concept": "Digitaler Minimalismus — Tech bewusst nutzen auf Reisen", "niche": "lifestyle", "price": "17.00", "affiliate_commission": "50", "keywords": ["digitaler minimalismus", "tech", "reisen"]},
]

CATEGORIES = [
    "ecommerce", "ki", "social", "finanzen", "business",
    "gesundheit", "persoenlichkeit", "kreativ", "sprachen", "lifestyle"
]


# ─── DS24 API ─────────────────────────────────────────────────────────────────

async def _ds24_post(endpoint: str, payload: dict) -> dict:
    if not DS24_KEY:
        return {"result": "error", "message": "no DIGISTORE24_API_KEY"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{DS24_BASE}/{endpoint}",
                headers={"x-ds-api-key": DS24_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return await r.json()
    except Exception as e:
        return {"result": "error", "message": str(e)}


async def _ai(prompt: str, max_tokens: int = 700) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _notify(msg: str):
    try:
        from modules.notify_hub import notify
        await notify(msg, level="info")
    except Exception:
        pass


def _build_affiliate_link(product_id: str) -> str:
    return f"https://www.digistore24.com/redir/{product_id}/{AFFILIATE_ID}/"


def _build_checkout_link(product_id: str) -> str:
    return f"https://checkout.digistore24.com/checkout/product/{product_id}"


# ─── KI-Konzept-Generator ────────────────────────────────────────────────────

async def generate_concept_batch(category: str, count: int = 10) -> list:
    """Generiert neue DS24 Produkt-Konzepte via KI für eine Kategorie."""
    price_hint = "20% €17, 30% €27, 25% €37, 15% €47, 7% €67, 3% €97"
    prompt = f"""Erstelle {count} neue Digistore24 Produkt-Konzepte für die Kategorie "{category}" auf Deutsch.
Preisverteilung: {price_hint}
Affiliate-Provision: 50% für €17-27, 45% für €37-47, 40% für €67-97.

Antworte NUR mit JSON-Array:
[
  {{
    "concept": "Produktkonzept auf Deutsch (max 80 Zeichen, verkaufspsychologisch optimiert)",
    "niche": "{category}",
    "price": "37.00",
    "affiliate_commission": "50",
    "keywords": ["keyword1", "keyword2", "keyword3"]
  }}
]
Nur das JSON, keine Erklärungen."""
    raw = await _ai(prompt, max_tokens=1200)
    if not raw:
        return []
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1:
            return []
        return json.loads(raw[start:end])
    except Exception:
        return []


# ─── SEO-Optimierung ─────────────────────────────────────────────────────────

async def generate_seo_product_data(concept: str, price: str, keywords: list) -> dict:
    """KI generiert SEO-optimierte DS24-Produktdaten."""
    kw_str = ", ".join(keywords[:5]) if keywords else concept[:30]
    prompt = f"""Erstelle SEO-optimierte Digistore24 Produktdaten auf Deutsch.
Konzept: "{concept}"
Preis: €{price}
Primäre Keywords: {kw_str}

Antworte NUR mit JSON:
{{
  "name_de": "Keyword-optimierter Produktname max 60 Zeichen mit klarem Nutzen",
  "name_intern": "interner-name-kebab-max-40",
  "description_de": "SEO-Text 150-200 Wörter: Primärkeyword im ersten Satz, 3 LSI-Keywords, Zielgruppe, konkretes Ergebnis, sozialer Beweis, starker CTA.",
  "access_instructions_de": "Nach Zahlungseingang erhalten Sie sofort Zugang per E-Mail. Der Download-Link ist 30 Tage gültig.",
  "tags": "tag1,tag2,tag3,tag4,tag5,tag6,tag7,tag8",
  "meta_keywords": "keyword1, keyword2, keyword3, keyword4, keyword5",
  "usp": "Ein Satz der das Hauptversprechen enthält — für Marketing-Texte"
}}"""
    raw = await _ai(prompt, max_tokens=600)
    if not raw:
        return {}
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {}
        return json.loads(raw[start:end])
    except Exception:
        return {}


# ─── Basis-Produkt-Erstellung (für Worker) ───────────────────────────────────

async def _create_one(tmpl: dict, results: list, counter: list):
    """Erstellt ein DS24-Produkt mit SEO. Thread-sicher via Liste."""
    concept = tmpl["concept"]
    price = tmpl.get("price", _rand_price())
    keywords = tmpl.get("keywords", [])
    commission = tmpl.get("affiliate_commission", _rand_commission(price))

    try:
        # SEO-Daten generieren
        seo = await generate_seo_product_data(concept, price, keywords)
        if not seo or not seo.get("name_de"):
            safe = concept[:30].lower().replace(" ", "-")
            seo = {
                "name_de": concept[:60],
                "name_intern": safe[:40],
                "description_de": f"{concept} — Professioneller Komplettkurs auf Deutsch. Sofort anwendbar.",
                "access_instructions_de": "Zugang per E-Mail nach Zahlungseingang.",
                "tags": ",".join(keywords[:5]),
                "meta_keywords": ", ".join(keywords),
                "usp": f"Das beste {concept[:40]} Programm auf Deutsch.",
            }

        # DS24: Produkt anlegen
        await asyncio.sleep(0.5)
        cp_result = await _ds24_post("createProduct", {"data": {
            "name_de": seo["name_de"][:100],
            "name_intern": seo.get("name_intern", "")[:40],
            "description_de": seo.get("description_de", "")[:2000],
            "salespage_url": SHOP_URL,
            "thankyou_url": f"{SHOP_URL}/pages/danke",
            "access_instructions_de": seo.get("access_instructions_de", "")[:500],
            "language": "de",
            "currency": "EUR",
            "affiliate_commission": str(commission),
            "is_active": "1",
            "is_affiliation_auto_accepted": "1",
        }})

        if cp_result.get("result") != "success":
            log.warning("createProduct failed: %s → %s", concept[:40], cp_result.get("message", "")[:100])
            return

        product_id = str(cp_result["data"]["product_id"])

        # DS24: Zahlungsplan
        await asyncio.sleep(0.5)
        await _ds24_post("createPaymentPlan", {"product_id": product_id, "data": {
            "first_amount": str(price),
            "currency": "EUR",
            "is_active": "1",
        }})

        # DS24: Aktivieren
        await asyncio.sleep(0.5)
        await _ds24_post("updateProduct", {"product_id": product_id, "data": {
            "is_active": "1",
            "affiliate_commission": str(commission),
            "is_affiliation_auto_accepted": "1",
        }})

        affiliate_link = _build_affiliate_link(product_id)
        checkout_link = _build_checkout_link(product_id)

        # Supabase speichern
        try:
            from modules.supabase_client import get_client
            get_client().table("ds24_products").upsert({
                "product_id": product_id,
                "name": seo["name_de"],
                "concept": concept[:200],
                "price": price,
                "affiliate_link": affiliate_link,
                "checkout_link": checkout_link,
                "keywords": keywords,
                "category": tmpl.get("niche", "allgemein"),
                "seo_score": 80 if seo.get("description_de") else 40,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="product_id").execute()
        except Exception as e:
            log.debug("Supabase upsert: %s", e)

        entry = {
            "ok": True,
            "product_id": product_id,
            "name": seo["name_de"],
            "price": price,
            "commission": f"{commission}%",
            "affiliate_link": affiliate_link,
            "checkout_link": checkout_link,
        }
        results.append(entry)
        counter[0] += 1
        log.info("[%d] DS24: %s (ID:%s €%s)", counter[0], seo["name_de"][:50], product_id, price)

    except Exception as e:
        log.warning("_create_one error for '%s': %s", concept[:40], e)


# ─── Worker-Pool ─────────────────────────────────────────────────────────────

async def _worker(queue: asyncio.Queue, results: list, counter: list,
                  worker_id: int, total: int, notify_every: int = 100):
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is None:
            break
        prev_count = counter[0]
        await _create_one(item, results, counter)
        # Progress-Update alle notify_every Produkte
        if counter[0] // notify_every > prev_count // notify_every:
            pct = int(counter[0] / total * 100)
            await _notify(f"✅ DS24 Massenanleger: {counter[0]}/{total} ({pct}%) erstellt...")
        queue.task_done()
        await asyncio.sleep(1.5)  # Rate-Limit-Puffer


async def mass_create_batch(templates: list, workers: int = 5,
                             notify_every: int = 100) -> dict:
    """Erstellt alle Templates via Worker-Pool parallel."""
    queue: asyncio.Queue = asyncio.Queue()
    for tmpl in templates:
        await queue.put(tmpl)

    results: list = []
    counter: list = [0]  # mutable int für Worker

    worker_tasks = [
        asyncio.create_task(_worker(queue, results, counter, i, len(templates), notify_every))
        for i in range(min(workers, len(templates)))
    ]
    await asyncio.gather(*worker_tasks, return_exceptions=True)

    return {"ok": True, "created": len(results), "total": len(templates), "products": results}


# ─── Haupt-Funktion: 1000 Produkte ───────────────────────────────────────────

async def create_1000_products() -> dict:
    """
    Vollautomatische Erstellung von 1000 DS24-Produkten.
    300 hardcodiert + 700 KI-generiert = 1000 total.
    5 Worker, Progress alle 100 Produkte via Telegram.
    """
    await _notify("🚀 DS24 Massenanleger gestartet! Ziel: 1000 Produkte mit SEO.\n⏱️ Geschätzte Zeit: ~60-90 Minuten.")

    # Bestehende Konzepte aus Supabase laden (Deduplizierung)
    existing_concepts: set = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("concept").execute()
        existing_concepts = {r["concept"][:60] for r in rows.data or []}
        log.info("DS24 Massenanleger: %d bestehende Konzepte übersprungen", len(existing_concepts))
    except Exception:
        pass

    # Queue aufbauen: hardcodierte Templates
    queue_items = []
    for tmpl in MASS_TEMPLATES:
        if tmpl["concept"][:60] not in existing_concepts:
            queue_items.append(tmpl)
            existing_concepts.add(tmpl["concept"][:60])

    # KI-generierte Konzepte für fehlende Menge (700 mehr)
    needed = 1000 - len(queue_items)
    if needed > 0:
        per_cat = max(1, needed // len(CATEGORIES))
        log.info("DS24: Generiere %d KI-Konzepte (%d pro Kategorie)", needed, per_cat)
        await _notify(f"🤖 Generiere {needed} KI-Konzepte ({per_cat} pro Kategorie)...")
        for cat in CATEGORIES:
            batch = await generate_concept_batch(cat, count=per_cat)
            for b in batch:
                if b.get("concept") and b["concept"][:60] not in existing_concepts:
                    queue_items.append(b)
                    existing_concepts.add(b["concept"][:60])
            await asyncio.sleep(1)

    # Auf max 1000 begrenzen
    random.shuffle(queue_items)
    queue_items = queue_items[:1000]

    log.info("DS24 Massenanleger: %d Produkte in Queue", len(queue_items))
    await _notify(f"📋 Queue bereit: {len(queue_items)} Produkte. Starte 5 Worker...")

    # Worker-Pool starten
    result = await mass_create_batch(queue_items, workers=5, notify_every=100)

    created = result.get("created", 0)
    total = result.get("total", len(queue_items))
    products = result.get("products", [])

    # Finale Benachrichtigung
    top5 = "\n".join(f"• {p['name'][:50]} (€{p['price']}, {p['commission']})" for p in products[:5])
    await _notify(
        f"🎯 DS24 MASSENANLEGER FERTIG!\n\n"
        f"✅ Erstellt: {created}/{total}\n"
        f"❌ Fehlgeschlagen: {total - created}\n\n"
        f"Top Produkte:\n{top5}\n\n"
        f"{'+ ' + str(created - 5) + ' weitere' if created > 5 else ''}"
    )

    # Brutus-Blast mit Zusammenfassung
    if products:
        try:
            from modules.brutus_core import fire
            await fire(
                f"🚀 {created} neue Digistore24-Produkte live!",
                f"Massiver Launch: {created} neue DS24 Produkte mit SEO-optimierten Texten!\n"
                f"Affiliate-Provision bis 50%! Sofort promotbar.\n\n"
                f"Top Produkte:\n{top5}",
                link=_build_affiliate_link(products[0]["product_id"]) if products else SHOP_URL,
                channels=["telegram", "slack", "shopify_blog", "discord", "linkedin", "mailchimp"],
            )
        except Exception as e:
            log.debug("Final blast error: %s", e)

    return {"ok": True, "created": created, "total": total,
            "success_rate": f"{created/total*100:.1f}%" if total else "0%",
            "products": products[:10]}


# ─── Autonomer Refill ─────────────────────────────────────────────────────────

async def autonomous_refill(target: int = 1000) -> dict:
    """
    Hält immer 'target' aktive Produkte auf DS24.
    Wird täglich vom Scheduler aufgerufen.
    """
    # Aktuelle Anzahl aus Supabase
    current_count = 0
    existing_concepts: set = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("concept,is_active").execute()
        all_rows = rows.data or []
        current_count = sum(1 for r in all_rows if r.get("is_active", True))
        existing_concepts = {r["concept"][:60] for r in all_rows}
    except Exception as e:
        log.warning("Supabase count error: %s", e)

    if current_count >= target:
        log.info("DS24 Refill: %d aktiv >= Ziel %d — kein Refill nötig", current_count, target)
        return {"ok": True, "created": 0, "total_active": current_count,
                "message": f"Ziel {target} bereits erreicht"}

    needed = target - current_count
    log.info("DS24 Refill: %d aktiv < Ziel %d — erstelle %d neue", current_count, target, needed)
    await _notify(f"🔄 DS24 Refill: {current_count}/{target} aktiv — erstelle {needed} neue Produkte...")

    # Templates die noch nicht existieren
    new_items = [t for t in MASS_TEMPLATES if t["concept"][:60] not in existing_concepts]

    # KI für fehlende
    if len(new_items) < needed:
        still_needed = needed - len(new_items)
        per_cat = max(1, still_needed // len(CATEGORIES))
        for cat in CATEGORIES:
            if len(new_items) >= needed:
                break
            batch = await generate_concept_batch(cat, count=per_cat)
            for b in batch:
                if b.get("concept") and b["concept"][:60] not in existing_concepts:
                    new_items.append(b)
                    existing_concepts.add(b["concept"][:60])
            await asyncio.sleep(1)

    new_items = new_items[:needed]
    result = await mass_create_batch(new_items, workers=3, notify_every=50)
    created = result.get("created", 0)

    return {
        "ok": True,
        "created": created,
        "total_active": current_count + created,
        "target": target,
        "gap_closed": created,
    }


# ─── Stats & Reporting ────────────────────────────────────────────────────────

async def get_ds24_stats() -> dict:
    """Statistiken über DS24-Produkte aus Supabase."""
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("*").execute()
        data = rows.data or []
        categories = {}
        prices = {}
        for r in data:
            cat = r.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            p = r.get("price", "?")
            prices[p] = prices.get(p, 0) + 1
        return {
            "ok": True,
            "total": len(data),
            "active": sum(1 for r in data if r.get("is_active", True)),
            "by_category": categories,
            "by_price": prices,
            "newest": [{"id": r["product_id"], "name": r.get("name", "")[:50]} for r in data[-5:]],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def blast_top_products(count: int = 10) -> dict:
    """Blast die neuesten 'count' DS24-Produkte auf allen Kanälen."""
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("*").order(
            "created_at", desc=True).limit(count).execute()
        products = rows.data or []
    except Exception:
        products = []

    if not products:
        return {"ok": False, "blasted": 0, "error": "no products in Supabase"}

    blasted = 0
    try:
        from modules.brutus_core import fire
        for p in products:
            name = p.get("name", "DS24 Produkt")[:60]
            price = p.get("price", "?")
            link = p.get("affiliate_link", SHOP_URL)
            await fire(
                f"🔥 {name}",
                f"Jetzt erhältlich: {name}\n💶 Nur €{price}\n💰 Bis 50% Affiliate-Provision\n\n🛒 {link}",
                link=link,
                channels=["telegram", "slack", "discord"],
            )
            blasted += 1
            await asyncio.sleep(2)
    except Exception as e:
        log.warning("blast_top_products error: %s", e)

    return {"ok": True, "blasted": blasted}
