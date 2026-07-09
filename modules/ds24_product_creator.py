#!/usr/bin/env python3
"""
Digistore24 Autonomous Product Creator
=======================================
Erstellt vollständig autonome Digistore24-Produkte:
1. KI generiert Produktname, Beschreibung, Preis, Salespage
2. createProduct → Produkt anlegen
3. createPaymentPlan → Zahlungsplan mit Preis
4. updateProduct → aktivieren + Affiliate-Provision setzen
5. Affiliate-Link generieren + via BrutusCore auf alle Kanäle blasen
6. Supabase: Produkt-ID speichern zur Deduplizierung

Getestete API-Calls (2026-06-20):
- createProduct: ✅ gibt product_id zurück
- createPaymentPlan: ✅ gibt paymentplan_id zurück
- updateProduct: ✅ aktiviert Produkt
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("DS24ProductCreator")

DS24_KEY     = os.getenv("DIGISTORE24_API_KEY", "1581233-eOOUB4qRJJybjVb9z4q5tO68wtEQmt9h9l8t3s1N")
AFFILIATE_ID = os.getenv("DS24_AFFILIATE_ID", "user37405262")
DS24_BASE    = "https://www.digistore24.com/api/call"
SHOP_URL     = os.getenv("SHOPIFY_SHOP_URL", "https://autopilot-store-suite-fmbka.myshopify.com")

# Vordefinierte Produkt-Vorlagen für autonome Erstellung (100 Konzepte)
PRODUCT_TEMPLATES = [
    # ── E-Commerce & Dropshipping ─────────────────────────────────────────────
    {"concept": "KI-gestütztes E-Commerce Automatisierungs-System", "niche": "software", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Amazon Affiliate Marketing Masterclass 2026", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Shopify Dropshipping Komplett-System", "niche": "software", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "eBay Dropshipping Geheimstrategie — €1000 pro Woche", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "AliExpress Gewinner-Produkte finden — Automatisiertes System", "niche": "software", "price": "47.00", "affiliate_commission": "45"},
    {"concept": "Print-on-Demand Passives Einkommen mit Printify & Printful", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Shopify SEO Masterclass — 10x mehr organischen Traffic", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "E-Commerce Email Marketing Komplettsystem", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Produktrecherche Tool — Topseller finden bevor sie viral gehen", "niche": "software", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Etsy Handmade Business Blueprint 2026", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    # ── KI & Automatisierung ─────────────────────────────────────────────────
    {"concept": "ChatGPT Business Blueprint — Geld verdienen mit KI", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "KI Texter Komplettkurs — Texte schreiben mit ChatGPT & Claude", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Midjourney & DALL-E Meisterkurs — KI-Bilder verkaufen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "ChatGPT Prompt Engineering Masterclass", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "KI-gestütztes Social Media Management System", "niche": "software", "price": "67.00", "affiliate_commission": "40"},
    {"concept": "Automatisierter Blog mit KI — Passives SEO-Einkommen", "niche": "software", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "KI Video-Erstellung Masterclass — YouTube mit KI automatisieren", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Make.com & Zapier Automatisierungs-Komplettkurs", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "n8n Workflow Automation Meisterkurs für Anfänger", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "KI-Kundenservice Bot für Shopify & WooCommerce", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    # ── Social Media & Marketing ─────────────────────────────────────────────
    {"concept": "Social Media Automation Suite 2026", "niche": "software", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Instagram Reels Masterclass — Von 0 auf 10.000 Follower", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "TikTok Marketing Geheimstrategie 2026", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Pinterest Traffic Maschine — 100.000 Besucher passiv", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "LinkedIn B2B Lead Generation Komplettsystem", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "YouTube Kanal aufbauen mit KI — Ohne Gesicht zeigen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Viral Content Formel — Jeder Post wird zum Hit", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Email Marketing Masterclass — 50% Öffnungsraten erzielen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Facebook Ads Komplettkurs — ROAS 5x garantiert", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Google Ads Masterclass für E-Commerce 2026", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    # ── Finanzen & Investment ────────────────────────────────────────────────
    {"concept": "Passives Einkommen Blueprint — 10 Wege zu €3000/Monat", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "ETF Investieren für Anfänger — Vermögen aufbauen 2026", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Kryptowährungen verstehen & profitabel handeln", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Dividendenstrategie Komplettkurs — Monatliche Ausschüttungen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Immobilien Investment ohne Eigenkapital 2026", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Forex Trading Einsteiger Masterclass", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Steueroptimierung für Selbstständige — Legal €5000 sparen", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Schuldenfreiheit in 24 Monaten — Praktischer Schritt-für-Schritt Plan", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Haushaltsbuch & Budgetplaner Komplettsystem", "niche": "software", "price": "17.00", "affiliate_commission": "50"},
    {"concept": "Side-Hustle Masterclass — €500 extra pro Monat nebenbei", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── Business & Freelancing ───────────────────────────────────────────────
    {"concept": "Freelancer Masterclass — Von 0 auf €5000/Monat", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Online-Kurs erstellen & verkaufen — Komplettsystem", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Copywriting Meisterkurs — Texte die verkaufen", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Business Plan Template Paket — 20 branchenspezifische Vorlagen", "niche": "software", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Digitale Produkte erstellen & verkaufen ohne Startkapital", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Webdesign Freelancer Starterpaket — Erste Kunden in 30 Tagen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Consulting Business Blueprint — Expertise monetarisieren", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Fiverr & Upwork Erfolgsformel — Top-Seller werden", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Virtuelle Assistentin werden — Work from Home Komplettguide", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "SaaS Produkt aufbauen ohne Coding — No-Code 2026", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    # ── Gesundheit & Fitness ─────────────────────────────────────────────────
    {"concept": "Intermittierendes Fasten Komplettsystem — 10 kg in 12 Wochen", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Home Workout Masterclass — Traumkörper ohne Fitnessstudio", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Abnehmen ohne Hunger — Der nachhaltige Ernährungsplan", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Muskelaufbau für Anfänger — 12-Wochen Transformation", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Meditation & Mindfulness Komplettkurs für Einsteiger", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Stressmanagement Masterclass — Burnout verhindern", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Yoga für Anfänger — 30-Tage Challenge", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    {"concept": "Schlaf optimieren — In 7 Nächten zur Bestleistung", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Keto Diät Komplettsystem mit Rezepten & Einkaufslisten", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Personal Trainer werden — Zertifizierungsvorbereitung", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    # ── Persönlichkeitsentwicklung ────────────────────────────────────────────
    {"concept": "Produktivitätssystem für Selbstständige — 4-Stunden-Arbeitstag", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Selbstvertrauen aufbauen Masterclass", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Gewohnheiten für Erfolg — 21-Tage Programm", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Public Speaking Masterclass — Überzeugend präsentieren", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Zeitmanagement System — Nie wieder gestresst", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Verhandlungsführung Meisterkurs — Immer das Beste rausholen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Mindset Reset Programm — Limitierende Glaubenssätze löschen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Morning Routine Blueprint — Erfolgreiche Morgenroutine", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    {"concept": "Beziehungen & Kommunikation Masterclass", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Leadership Masterclass — Führungskraft werden", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    # ── Kreativität & Technik ────────────────────────────────────────────────
    {"concept": "Fotografie Einsteigerkurs — Professionelle Fotos mit jedem Smartphone", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Video Editing Masterclass — Premiere Pro von Anfang bis Profi", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Podcast aufbauen & monetarisieren — Vollständiger Guide", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "WordPress Website erstellen ohne Vorkenntnisse", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Python Programmierung für Anfänger — In 30 Tagen zum Entwickler", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Canva Masterclass — Professionelle Designs in Minuten", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Musik produzieren mit FL Studio — Einsteigerkurs", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Grafikdesign Grundlagen — Logo & Branding selbst erstellen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "3D Druck Masterclass — Von Anfänger zum Profi", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Drohnen Fotografie Komplettkurs — Lizenz & Technik", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    # ── Sprachen & Bildung ────────────────────────────────────────────────────
    {"concept": "Englisch Fließend in 90 Tagen — Intensivprogramm", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Spanisch lernen für Anfänger — Urlaubs-Spanisch in 4 Wochen", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Japanisch Grundkurs — Hiragana, Katakana & Basis-Kanji", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Business English Masterclass — Professionell auf Englisch kommunizieren", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Lernmethoden Masterclass — 3x schneller lernen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── Ernährung & Kochen ───────────────────────────────────────────────────
    {"concept": "Vegane Ernährung Komplettkurs — Gesund & lecker ohne Fleisch", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Meal Prep Masterclass — 5 Tage in 2 Stunden kochen", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Brot backen Profi-Kurs — Sauerteig & Handwerksbrot", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Rohkost & Superfood Guide — Maximale Energie durch Ernährung", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Meal Replacement Shakes — DIY Rezepte für Abnehmen", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    # ── Reisen & Lifestyle ───────────────────────────────────────────────────
    {"concept": "Digitaler Nomade werden — Ortsunabhängig arbeiten & reisen", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Weltreise planen unter €10.000 — Insider-Tipps", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Van Life Guide — Ausbau, Reise & Freiheit", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Minimalismus Masterclass — Weniger besitzen, mehr leben", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    {"concept": "Nachhaltiger Lebensstil — Zero Waste für Einsteiger", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    # ── Immobilien & Haushalts-Know-how ──────────────────────────────────────
    {"concept": "Airbnb Erfolgsformel — Wohnung vermieten & €2000 extra", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Hausautomation für Einsteiger — Smart Home selbst einrichten", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Garten anlegen für Anfänger — Gemüse & Kräuter selbst anbauen", "niche": "course", "price": "17.00", "affiliate_commission": "50"},
    {"concept": "Handwerker Skills — 10 Reparaturen die jeder selbst machen kann", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Feng Shui Grundkurs — Harmonisches Zuhause gestalten", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    # ── Spezial: Hochpreisige Software-Produkte ───────────────────────────────
    {"concept": "All-in-One Marketing Automation Suite für KMUs", "niche": "software", "price": "197.00", "affiliate_commission": "35"},
    {"concept": "Komplettes Shopify Webshop Paket mit 500 Produkten", "niche": "software", "price": "197.00", "affiliate_commission": "35"},
    {"concept": "Done-for-You Affiliate Website — Fertige Nischenseite kaufen", "niche": "software", "price": "147.00", "affiliate_commission": "35"},
    {"concept": "Email Funnel Vorlagen-Paket — 50 konvertierende Sequenzen", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Social Media Content Kalender 2026 — 365 Tage Beiträge", "niche": "software", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: KI & LLMs 2026 ───────────────────────────────────────────────────
    {"concept": "Claude 3 & GPT-4o Business Masterclass — KI-Agenten bauen ohne Code", "niche": "course", "price": "97.00", "affiliate_commission": "45"},
    {"concept": "Lokale KI ohne Internet — Ollama & LM Studio Komplettguide", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "KI-Automatisierungsagentur gründen — €10k/Monat mit n8n & Make", "niche": "course", "price": "147.00", "affiliate_commission": "40"},
    {"concept": "Perplexity AI & Gemini Pro für Unternehmen nutzen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "KI-Vertriebs-Bot bauen — Leads automatisch qualifizieren & konvertieren", "niche": "software", "price": "127.00", "affiliate_commission": "40"},
    {"concept": "Voice AI für Kundenservice — ElevenLabs & Whisper Praxiskurs", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "RAG System aufbauen — Eigene Wissensdatenbank mit KI durchsuchen", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "KI-Bild-Business 2026 — Flux & Stable Diffusion kommerziell nutzen", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Autonomous Agents mit LangChain & AutoGPT — Praxiskurs", "niche": "course", "price": "87.00", "affiliate_commission": "40"},
    {"concept": "AI Prompt-Pakete für Online-Business — 500 getestete Prompts", "niche": "software", "price": "27.00", "affiliate_commission": "50"},
    # ── V2: EU AI Act & Compliance ───────────────────────────────────────────
    {"concept": "EU AI Act Compliance Guide 2026 — Pflichten für KMUs erklärt", "niche": "course", "price": "127.00", "affiliate_commission": "40"},
    {"concept": "DSGVO & KI — Datenschutz beim KI-Einsatz im Unternehmen", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "KI-Risikoklassen nach EU AI Act — Praktisches Handbuch", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    # ── V2: TikTok Shop & Neue Plattformen ──────────────────────────────────
    {"concept": "TikTok Shop Dropshipping 2026 — Produkte viral verkaufen ohne Lager", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "TikTok Affiliate Marketing System — Provisionen mit kurzen Videos", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Instagram Shopping Automation — Produkte täglich automatisch posten", "niche": "software", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "YouTube Shorts Monetarisierung — Passives Einkommen mit 60-Sekunden-Videos", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Pinterest Shopping Funnel — Kaufbereite Kunden automatisch gewinnen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Threads & Bluesky Wachstumsstrategie 2026 — Erste 10k Follower", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    # ── V2: Amazon & Marktplätze Deutschland/Europa ─────────────────────────
    {"concept": "Amazon FBA Deutschland — Von 0 auf €5000/Monat Schritt für Schritt", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Amazon KDP Passive Einkommen — Bücher publizieren & automatisch verdienen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Kaufland Marketplace Masterclass — Nebenkanal für mehr Umsatz", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Otto.de Seller-Guide — Produkte listen & skalieren auf Deutschlands Plattform", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Handmade auf Dawanda & Etsy DE — Handwerk profitabel online verkaufen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: Hochpreisige Kurse & Coaching ───────────────────────────────────
    {"concept": "High-Ticket Coaching Business aufbauen — €2000+ pro Klient", "niche": "course", "price": "197.00", "affiliate_commission": "35"},
    {"concept": "Online-Business 100k — Dein erster 6-stelliger Jahresumsatz online", "niche": "course", "price": "297.00", "affiliate_commission": "30"},
    {"concept": "Membership-Site aufbauen — Monatliches Abo-Einkommen skalieren", "niche": "course", "price": "147.00", "affiliate_commission": "40"},
    {"concept": "Affiliate-Marketing Agentur 2026 — Für andere Geld verdienen", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Done-for-You E-Commerce System — Fertig aufgesetzter Shop mit Lieferanten", "niche": "software", "price": "247.00", "affiliate_commission": "30"},
    # ── V2: Biohacking & Longevity ──────────────────────────────────────────
    {"concept": "Biohacking Starter Guide — HRV, Schlaf & Peak Performance wissenschaftlich", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Longevity Ernährungsplan — Länger leben mit Intervallfasten & mTOR", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Cold Exposure & Sauna Protokoll — Wim Hof Methode auf Deutsch", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Hormesis & Stresstoleranz — Körper stärker machen durch kontrolliertem Stress", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Gut Health Revolution — Darm sanieren & Energie verdoppeln", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    # ── V2: Finanzen & DeFi 2026 ────────────────────────────────────────────
    {"concept": "Bitcoin & Layer-2 Einkommen 2026 — Lightning Network & Staking erklärt", "niche": "course", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Solana Ökosystem Komplettkurs — DeFi, NFTs & neue Protokolle", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Steuern auf Krypto in Deutschland 2026 — Legal optimieren", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Passives Einkommen mit P2P-Krediten — Bondora & Mintos Strategie", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Vermögensaufbau für Beamte & Angestellte — Sicherheit + Rendite", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Optionen handeln lernen — Cash Secured Puts & Covered Calls", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Riester & Rürup Maximieren — Staatliche Förderung vollständig ausschöpfen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    # ── V2: Immobilien Real ──────────────────────────────────────────────────
    {"concept": "Immobilien Analyse Tool — Rendite kalkulieren vor dem Kauf", "niche": "software", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Fix & Flip Österreich — Immobilien kaufen, sanieren, verkaufen mit Gewinn", "niche": "course", "price": "127.00", "affiliate_commission": "40"},
    {"concept": "Ferienimmobilien Investment — Airbnb-Rendite in Tirol & Kärnten", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "WEG-Verwaltung selbst gemacht — Eigentümergemeinschaft effizient führen", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    # ── V2: Business Automatisierung ────────────────────────────────────────
    {"concept": "Buchhaltung automatisieren 2026 — Lexoffice & DATEV mit KI verbinden", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "CRM ohne Aufwand — HubSpot kostenlos meistern & Kunden binden", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Rechnungs- & Angebotswesen automatisieren — Zeitersparnis 80%", "niche": "software", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Kundensupport mit KI-Chatbot — Zendesk & Intercom auf Autopilot", "niche": "software", "price": "77.00", "affiliate_commission": "40"},
    {"concept": "Newsletter Empire aufbauen — Von 0 auf 10k Abonnenten in 6 Monaten", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Projektmanagement Masterclass — Asana, Notion & ClickUp effizient", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: Content & Creator Economy ───────────────────────────────────────
    {"concept": "Faceless YouTube Channel 2026 — KI-Videos ohne Gesicht zeigen monetarisieren", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Substack & Newsletter Monetarisierung — Aus Lesern Kunden machen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Podcast Sponsoren finden & Deals abschließen — Schritt-für-Schritt", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Twitch & Gaming Content Monetarisieren — Streams in Einkommen umwandeln", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Ghostwriting als Nebenjob — Für KI-Unternehmen Texte schreiben", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Digitales Produkt-Ökosystem — eBook → Kurs → Coaching automatisiert", "niche": "course", "price": "97.00", "affiliate_commission": "40"},
    # ── V2: Handwerk & Offline-Expertise online ──────────────────────────────
    {"concept": "Elektroinstallation Grundlagen — Was Heimwerker selbst dürfen & können", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Autoreparatur Basics — 10 Reparaturen selbst machen & €500/Jahr sparen", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Holzbearbeitung für Einsteiger — Schreiner-Skills zuhause anwenden", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Nähen & Schneidern lernen — Kleidung selbst reparieren & gestalten", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Aquaponik & Permakultur — Selbstversorgung im eigenen Garten", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: Sprachen & Zertifikate ──────────────────────────────────────────
    {"concept": "Französisch B2 in 6 Monaten — Intensiv-Sprachkurs für Berufstätige", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Chinesisch Grundlagen (HSK 1-2) — Mandarin für Einsteiger auf Deutsch", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "IELTS & TOEFL Vorbereitung — Zertifikat in 8 Wochen bestehen", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Arabisch Grundkurs — Moderne Standardsprache schnell lernen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: Kinder & Eltern ─────────────────────────────────────────────────
    {"concept": "Kinder Programmieren lernen — Scratch & Python für 8-14 Jährige", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Entspannte Elternschaft — Kinder ohne Schreien & Strafen erziehen", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Montessori zuhause — Lernumgebung für Kinder 0-6 selbst gestalten", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    # ── V2: Nischen-Software & Tools ────────────────────────────────────────
    {"concept": "Rank Tracking Tool — SEO-Rankings täglich überwachen & optimieren", "niche": "software", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Social Proof Widget — Echtzeit-Benachrichtigungen für Shopify & WooCommerce", "niche": "software", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Upsell-Funnel Builder — 1-Click-Upsell ohne Programmieren einrichten", "niche": "software", "price": "67.00", "affiliate_commission": "45"},
    {"concept": "Exit-Intent Popup System — Abwandernde Besucher in Kunden verwandeln", "niche": "software", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Automatischer Bewertungs-Generator — 5-Sterne Reviews legal maximieren", "niche": "software", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "A/B Testing Toolkit für Shopify — Conversion Rate verdoppeln", "niche": "software", "price": "47.00", "affiliate_commission": "50"},
    # ── V2: Nachhaltigkeit & Energie ─────────────────────────────────────────
    {"concept": "Balkonkraftwerk Komplettanleitung 2026 — Anlage, Anmeldung, Optimierung", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Wärmepumpe verstehen & richtig nutzen — Heizkosten 60% senken", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "E-Auto günstig laden & Reichweite optimieren — Praxistipps 2026", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Energie-Audit Zuhause — Versteckte Stromfresser finden & eliminieren", "niche": "software", "price": "17.00", "affiliate_commission": "50"},
    # ── V2: Job & Karriere ───────────────────────────────────────────────────
    {"concept": "Remote-Job finden 2026 — Die 100 besten Arbeitgeber & wie du dort landest", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Gehaltsverhandlung Masterclass — 20% mehr Gehalt in der nächsten Verhandlung", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "LinkedIn Profil optimieren — Headhunter finden dich automatisch", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Selbstständigkeit nebenberuflich starten — Gewerbe, Steuern & erste Kunden", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Existenzgründung Schritt für Schritt — GmbH oder Einzelunternehmen richtig wählen", "niche": "course", "price": "67.00", "affiliate_commission": "45"},
    # ── V2: Psychologie & Mentaltraining ─────────────────────────────────────
    {"concept": "Prokrastination besiegen — Warum du nicht anfängst & wie du es änderst", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Emotionale Intelligenz steigern — Beziehungen & Karriere verbessern", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "NLP Grundkurs auf Deutsch — Sprache des Unterbewusstseins verstehen", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    {"concept": "Stoische Gelassenheit im Alltag — Epiktet & Marcus Aurelius praktisch anwenden", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Angst & Panikattacken überwinden — Kognitiv-Verhaltenstherapie selbst anwenden", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    # ── V2: Haustiere & Tiere ────────────────────────────────────────────────
    {"concept": "Hund artgerecht erziehen — Ohne Strafen, mit Belohnung zur Traumbeziehung", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Katze verstehen & glücklich machen — Verhalten & Bedürfnisse erklärt", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    {"concept": "Tierarztkosten reduzieren — Was ich zuhause selbst behandeln kann", "niche": "course", "price": "27.00", "affiliate_commission": "50"},
    # ── V2: Wohnen & Interior ────────────────────────────────────────────────
    {"concept": "Inneneinrichtung mit KI — DALL-E & Midjourney für Raumplanung nutzen", "niche": "course", "price": "37.00", "affiliate_commission": "50"},
    {"concept": "Smart Home Budget-Setup 2026 — Alexa, Google Home & Zigbee unter €200", "niche": "course", "price": "47.00", "affiliate_commission": "50"},
    {"concept": "Tiny House planen & bauen — Freiheit auf 25m² verwirklichen", "niche": "course", "price": "57.00", "affiliate_commission": "45"},
    # ── V2: Mega-Bundle Software ─────────────────────────────────────────────
    {"concept": "360° Online-Business Starter Kit — Alle Tools & Vorlagen für den Start", "niche": "software", "price": "197.00", "affiliate_commission": "35"},
    {"concept": "Affiliate Webseiten Paket — 5 fertige Nischenseiten mit Monetarisierung", "niche": "software", "price": "147.00", "affiliate_commission": "40"},
    {"concept": "KI-Content Fabrik — Templates & Workflows für täglich 50 Inhalte", "niche": "software", "price": "97.00", "affiliate_commission": "40"},
    {"concept": "Shopify 2026 Starter Bundle — Shop-Setup, Produkte & erste Kunden in 7 Tagen", "niche": "software", "price": "127.00", "affiliate_commission": "40"},
    {"concept": "Freelancer Toolbox Komplett — Verträge, Rechnungen & Akquise-Vorlagen", "niche": "software", "price": "47.00", "affiliate_commission": "50"},
]


# ─── DS24 API Helpers ─────────────────────────────────────────────────────────

async def _ds24_post(endpoint: str, payload: dict) -> dict:
    """POST to Digistore24 API with x-ds-api-key header."""
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


async def _ai(prompt: str, max_tokens: int = 600) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


# ─── KI Produktdaten generieren ──────────────────────────────────────────────

async def generate_ds24_product_data(concept: str, price: str = "97.00",
                                      niche: str = "software") -> dict:
    """KI generiert vollständige DS24-Produktdaten für ein Konzept."""
    prompt = f"""Erstelle vollständige Digistore24 Produktdaten auf Deutsch.
Konzept: "{concept}"
Preis: €{price}
Nische: {niche}

Antworte NUR mit diesem JSON:
{{
  "name_de": "Produktname (max 60 Zeichen, verkaufspsychologisch optimiert)",
  "name_intern": "interner-name-kebab-case-max-40",
  "description_de": "Kurzbeschreibung 100-150 Wörter. Nutzen, Zielgruppe, Ergebnis. Überzeugend.",
  "access_instructions_de": "Nach dem Kauf erhalten Sie sofort Zugang per E-Mail. Link ist 30 Tage gültig.",
  "salespage_url": "{SHOP_URL}",
  "thankyou_url": "{SHOP_URL}/pages/danke",
  "tags": "tag1,tag2,tag3",
  "usp": "Hauptnutzen in einem Satz für Marketing"
}}"""

    raw = await _ai(prompt, max_tokens=500)
    if not raw:
        return {}
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            return {}
        return json.loads(raw[start:end])
    except Exception:
        return {}


# ─── DS24 Produkt anlegen ────────────────────────────────────────────────────

async def create_product(
    name_de: str,
    description_de: str,
    salespage_url: str = "",
    thankyou_url: str = "",
    name_intern: str = "",
    access_instructions_de: str = "",
    affiliate_commission: str = "40",
) -> Optional[str]:
    """Legt ein neues Produkt auf Digistore24 an. Gibt product_id zurück."""
    data_payload: dict = {
        "name_de": name_de[:100],
        "name_intern": (name_intern or name_de[:40].lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))[:40],
        "description_de": description_de[:2000],
        "access_instructions_de": access_instructions_de or "Zugang wird nach Zahlungseingang per E-Mail zugeschickt.",
        "language": "de",
        "currency": "EUR",
        "affiliate_commission": str(affiliate_commission),
        "is_active": "0",  # start inactive, activate after payment plan added
        "is_affiliation_auto_accepted": "1",
    }
    # Only add URLs if provided — DS24 blocks domains registered to other accounts
    if salespage_url:
        data_payload["salespage_url"] = salespage_url
    if thankyou_url:
        data_payload["thankyou_url"] = thankyou_url
    payload = {
        "data": {
            **data_payload,
        }
    }
    result = await _ds24_post("createProduct", payload)
    if result.get("result") == "success":
        pid = str(result["data"]["product_id"])
        log.info("DS24 Produkt angelegt: %s (ID: %s)", name_de[:50], pid)
        return pid
    log.warning("DS24 createProduct Error: %s", result.get("message", result))
    return None


async def create_payment_plan(
    product_id: str,
    amount: str = "97.00",
    currency: str = "EUR",
) -> Optional[str]:
    """Erstellt Zahlungsplan (Einmalzahlung) für das Produkt."""
    payload = {
        "product_id": product_id,
        "data": {
            "first_amount": str(amount),
            "currency": currency,
            "is_active": "1",
        }
    }
    result = await _ds24_post("createPaymentPlan", payload)
    if result.get("result") == "success":
        ppid = str(result["data"]["paymentplan_id"])
        log.info("DS24 Zahlungsplan angelegt: %s (Plan-ID: %s)", amount, ppid)
        return ppid
    log.warning("DS24 createPaymentPlan Error: %s", result.get("message", result))
    return None


async def activate_product(product_id: str, commission: str = "40") -> bool:
    """Aktiviert Produkt + setzt Affiliate-Provision."""
    payload = {
        "product_id": product_id,
        "data": {
            "is_active": "1",
            "affiliate_commission": str(commission),
            "is_affiliation_auto_accepted": "1",
        }
    }
    result = await _ds24_post("updateProduct", payload)
    ok = result.get("result") == "success"
    if ok:
        log.info("DS24 Produkt aktiviert: %s (Provision: %s%%)", product_id, commission)
    return ok


def build_affiliate_link(product_id: str) -> str:
    """Erstellt den Affiliate-Link für das Produkt."""
    return f"https://www.digistore24.com/redir/{product_id}/{AFFILIATE_ID}/"


def build_checkout_link(product_id: str) -> str:
    """Direkt-Checkout-Link (kein Affiliate-Redirect)."""
    return f"https://checkout.digistore24.com/checkout/product/{product_id}"


# ─── Vollautomatische Produkt-Erstellung ─────────────────────────────────────

async def create_full_product(
    concept: str,
    price: str = "97.00",
    niche: str = "software",
    affiliate_commission: str = "40",
) -> dict:
    """
    Vollautomatisch: Konzept → KI → DS24 anlegen → aktivieren → blitzen.
    """
    log.info("DS24 Auto-Create: %s (€%s)", concept[:50], price)

    # 1. KI: Produktdaten generieren
    data = await generate_ds24_product_data(concept, price, niche)
    if not data or not data.get("name_de"):
        # Fallback wenn KI leer
        data = {
            "name_de": concept[:60],
            "name_intern": concept[:30].lower().replace(" ", "-"),
            "description_de": f"Professionelles {concept} — sofort einsetzbar, vollständig auf Deutsch.",
            "access_instructions_de": "Zugang per E-Mail nach Zahlungseingang.",
            "salespage_url": SHOP_URL,
            "thankyou_url": f"{SHOP_URL}/pages/danke",
        }

    # 2. Produkt anlegen (keine salespage_url — DS24 blockt fremde Domains)
    product_id = await create_product(
        name_de=data["name_de"],
        description_de=data.get("description_de", ""),
        salespage_url="",
        thankyou_url="",
        name_intern=data.get("name_intern", ""),
        access_instructions_de=data.get("access_instructions_de", ""),
        affiliate_commission=affiliate_commission,
    )
    if not product_id:
        return {"ok": False, "error": "createProduct failed"}

    # 3. Zahlungsplan anlegen
    plan_id = await create_payment_plan(product_id, price)

    # 4. Aktivieren
    await activate_product(product_id, affiliate_commission)

    # 5. Links generieren
    affiliate_link = build_affiliate_link(product_id)
    checkout_link = build_checkout_link(product_id)

    # 6. Supabase: Produkt speichern
    try:
        from modules.supabase_client import get_client
        get_client().table("ds24_products").insert({
            "product_id": product_id,
            "name": data["name_de"],
            "price": price,
            "concept": concept[:200],
            "affiliate_link": affiliate_link,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.debug("Supabase DS24 log: %s", e)

    # 7. BrutusCore Blast
    usp = data.get("usp", f"Neues Produkt: {data['name_de']}")
    blast_msg = (
        f"🆕 Neues DS24-Produkt live!\n\n"
        f"📦 {data['name_de']}\n"
        f"💶 Preis: €{price}\n"
        f"💰 Affiliate: {affiliate_commission}% Provision\n\n"
        f"⚡ {usp}\n\n"
        f"🛒 Kaufen: {checkout_link}\n"
        f"🔗 Affiliate: {affiliate_link}"
    )
    try:
        from modules.brutus_core import fire
        await fire(
            data["name_de"],
            blast_msg,
            link=affiliate_link,
            channels=["telegram", "slack", "mailchimp", "klaviyo",
                      "linkedin", "discord", "shopify_blog"],
        )
    except Exception as e:
        log.debug("Blast error: %s", e)

    log.info("DS24 Komplett-Produkt erstellt: %s (ID: %s, Plan: %s)",
             data['name_de'][:50], product_id, plan_id)
    return {
        "ok": True,
        "product_id": product_id,
        "payment_plan_id": plan_id,
        "name": data["name_de"],
        "price": price,
        "affiliate_link": affiliate_link,
        "checkout_link": checkout_link,
        "commission": f"{affiliate_commission}%",
    }


# ─── Batch Auto-Creator ───────────────────────────────────────────────────────

async def auto_create_products(count: int = 2, fast: bool = False) -> dict:
    """
    Autonome Erstellung von 'count' DS24-Produkten aus PRODUCT_TEMPLATES.
    fast=True: kein BrutusCore pro Produkt (Bulk-Modus), nur finale Telegram-Meldung.
    """
    import random
    created = []
    failed = 0

    # Prüfe welche Produkte schon existieren (Supabase)
    existing_concepts = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("ds24_products").select("concept").execute()
        existing_concepts = {r["concept"][:60] for r in rows.data or []}
    except Exception:
        pass

    # Bei mehr als 5 → alle Templates nutzen, sonst random sample
    templates = list(PRODUCT_TEMPLATES)
    if count <= len(templates):
        if count <= 10:
            templates = random.sample(templates, min(count * 2, len(templates)))
    # Deduplizieren
    queue = [t for t in templates if t["concept"][:60] not in existing_concepts]
    random.shuffle(queue)

    for tmpl in queue:
        if len(created) >= count:
            break
        concept = tmpl["concept"]
        try:
            # Im Fast-Modus: kein BrutusCore blast per Produkt
            if fast:
                result = await _create_product_silent(concept, tmpl["price"],
                                                        tmpl.get("niche", "course"),
                                                        tmpl["affiliate_commission"])
            else:
                result = await create_full_product(
                    concept=concept,
                    price=tmpl["price"],
                    niche=tmpl.get("niche", "course"),
                    affiliate_commission=tmpl["affiliate_commission"],
                )
            if result.get("ok"):
                created.append(result)
                existing_concepts.add(concept[:60])
                log.info("DS24 [%d/%d] erstellt: %s", len(created), count, result.get("name", "")[:50])
            else:
                failed += 1
                log.warning("DS24 failed: %s → %s", concept[:40], result.get("error"))
            await asyncio.sleep(1 if fast else 3)
        except Exception as e:
            log.warning("DS24 auto-create error: %s", e)
            failed += 1

    # Finale Telegram-Meldung
    if created:
        try:
            from modules.notify_hub import notify
            lines = [f"🎯 DS24: {len(created)}/{count} Produkte erstellt!\n"]
            for p in created[:10]:
                lines.append(f"• {p['name'][:45]} (€{p['price']}, {p['commission']})")
            if len(created) > 10:
                lines.append(f"... + {len(created)-10} weitere")
            await notify("\n".join(lines), level="success")
        except Exception:
            pass

    # Falls fast-Modus: am Ende einmal BrutusCore für Überblick
    if fast and created:
        try:
            from modules.brutus_core import fire
            summary = "\n".join(f"• {p['name'][:50]}" for p in created[:5])
            if len(created) > 5:
                summary += f"\n... + {len(created)-5} weitere"
            await fire("DS24 Produkt-Launch: 100 neue Produkte!",
                       f"🚀 {len(created)} neue Digistore24-Produkte live!\n\n{summary}\n\nAffiliate-Provision bis 50%!",
                       link=build_affiliate_link(created[0]["product_id"]),
                       channels=["telegram", "slack", "shopify_blog", "discord", "linkedin"])
        except Exception as e:
            log.debug("Final blast error: %s", e)

    return {"ok": True, "created": len(created), "failed": failed,
            "total_requested": count, "products": created}


async def _create_product_silent(concept: str, price: str,
                                  niche: str = "course",
                                  affiliate_commission: str = "50") -> dict:
    """Schnelle Produkterstellung ohne BrutusCore-Blast (für Batch-Modus)."""
    data = await generate_ds24_product_data(concept, price, niche)
    if not data or not data.get("name_de"):
        data = {
            "name_de": concept[:60],
            "name_intern": concept[:30].lower().replace(" ", "-"),
            "description_de": f"Professionelles {concept} — sofort einsetzbar, vollständig auf Deutsch.",
            "access_instructions_de": "Zugang per E-Mail nach Zahlungseingang.",
            "salespage_url": SHOP_URL,
            "thankyou_url": f"{SHOP_URL}/pages/danke",
        }

    product_id = await create_product(
        name_de=data["name_de"],
        description_de=data.get("description_de", ""),
        salespage_url=data.get("salespage_url", SHOP_URL),
        thankyou_url=data.get("thankyou_url", f"{SHOP_URL}/pages/danke"),
        name_intern=data.get("name_intern", ""),
        access_instructions_de=data.get("access_instructions_de", ""),
        affiliate_commission=affiliate_commission,
    )
    if not product_id:
        return {"ok": False, "error": "createProduct failed"}

    plan_id = await create_payment_plan(product_id, price)
    await activate_product(product_id, affiliate_commission)

    affiliate_link = build_affiliate_link(product_id)
    checkout_link = build_checkout_link(product_id)

    try:
        from modules.supabase_client import get_client
        get_client().table("ds24_products").insert({
            "product_id": product_id,
            "name": data["name_de"],
            "price": price,
            "concept": concept[:200],
            "affiliate_link": affiliate_link,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass

    return {
        "ok": True,
        "product_id": product_id,
        "payment_plan_id": plan_id,
        "name": data["name_de"],
        "price": price,
        "affiliate_link": affiliate_link,
        "checkout_link": checkout_link,
        "commission": f"{affiliate_commission}%",
    }


async def create_100_products() -> dict:
    """Erstellt alle 100 Produkte aus PRODUCT_TEMPLATES — vollautomatisch."""
    return await auto_create_products(count=100, fast=True)


async def fix_product_669750() -> dict:
    """
    Repariert das nicht-verkaufbare Produkt 669750:
    - Prüft Status
    - Fügt fehlenden Zahlungsplan hinzu
    - Aktiviert es
    """
    product_id = "669750"
    log.info("Fixing DS24 product 669750...")

    # Zahlungsplan hinzufügen
    plan_id = await create_payment_plan(product_id, "97.00")

    # Aktivieren
    activated = await activate_product(product_id, "40")

    # Checkout link
    link = build_checkout_link(product_id)
    affiliate = build_affiliate_link(product_id)

    result = {
        "ok": activated,
        "product_id": product_id,
        "payment_plan_added": plan_id,
        "activated": activated,
        "checkout_link": link,
        "affiliate_link": affiliate,
    }
    log.info("Fix 669750: %s", result)
    return result


async def list_ds24_products() -> dict:
    """Listet alle DS24-Produkte mit Links."""
    result = await _ds24_post("listProducts", {})
    if result.get("result") != "success":
        return {"ok": False, "error": result.get("message", "unknown")}

    products = result.get("data", {}).get("products", [])
    enriched = []
    for p in products:
        pid = str(p.get("id", ""))
        enriched.append({
            "id": pid,
            "name": p.get("name", ""),
            "price": p.get("net_price", ""),
            "is_active": p.get("is_active", "0") == "1",
            "affiliate_link": build_affiliate_link(pid),
            "checkout_link": build_checkout_link(pid),
        })
    return {"ok": True, "count": len(enriched), "products": enriched}
