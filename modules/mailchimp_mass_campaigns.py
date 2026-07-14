#!/usr/bin/env python3
"""
Mailchimp Mass Campaigns — 1000 automatische Email-Kampagnen
============================================================
- 200 hardcodierte Templates (verschiedene Themen)
- Mailchimp Marketing API v3 (us7)
- 3 parallele Worker (Mailchimp Rate-Limit respektieren)
- Supabase Dedup
- BrutusCore Blast nach Erstellung
- Täglich 2 neue Kampagnen automatisch
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("MailchimpMassCampaigns")

API_KEY    = os.getenv("MAILCHIMP_API_KEY", "")
SERVER     = os.getenv("MAILCHIMP_SERVER", "us7")
LIST_ID    = os.getenv("MAILCHIMP_LIST_ID", "")
FROM_EMAIL = os.getenv("MAILCHIMP_FROM_EMAIL", os.getenv("FROM_EMAIL", "hello@ineedit.com.co"))
FROM_NAME  = os.getenv("MAILCHIMP_FROM_NAME", "BullPowerHub")
SHOP_URL   = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
BASE       = f"https://{SERVER}.api.mailchimp.com/3.0"


def _auth() -> dict:
    token = base64.b64encode(f"anystring:{API_KEY}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


# ─── 200 Kampagnen-Templates ──────────────────────────────────────────────────

MC_TEMPLATES: list[dict] = [
    # ── Willkommen & Onboarding (20) ─────────────────────────────────────────
    {"title": "Willkommen bei BullPowerHub!", "subject": "👋 Herzlich willkommen — Dein 10% Startercode!", "theme": "welcome", "cta": "Code einlösen"},
    {"title": "Erste Schritte — Dein Guide", "subject": "🚀 Los geht's: Dein Starter-Guide ist hier!", "theme": "welcome", "cta": "Guide starten"},
    {"title": "Was macht uns besonders", "subject": "💡 Warum über 10.000 Kunden uns vertrauen!", "theme": "welcome", "cta": "Mehr erfahren"},
    {"title": "Deine ersten 24h bei uns", "subject": "⭐ 24h mit uns: So machst du das Beste draus!", "theme": "welcome", "cta": "Tipps nutzen"},
    {"title": "Die besten Produkte für dich", "subject": "🎯 Für dich kuratiert: Unsere Top-Empfehlungen!", "theme": "welcome", "cta": "Entdecken"},
    {"title": "Community joinen — Discord & Social", "subject": "👥 Join unsere Community auf Discord!", "theme": "welcome", "cta": "Beitreten"},
    {"title": "Kostenlose Beratung buchen", "subject": "🤝 Kostenlose Beratung: Lass uns sprechen!", "theme": "welcome", "cta": "Beratung buchen"},
    {"title": "App herunterladen für mehr Vorteile", "subject": "📱 App-Download: Extra 5% für alle App-Käufe!", "theme": "welcome", "cta": "App laden"},
    {"title": "Wie alles funktioniert Übersicht", "subject": "🗺️ Wie alles funktioniert — Kurzer Überblick!", "theme": "welcome", "cta": "Übersicht ansehen"},
    {"title": "Dein Profil einrichten für Deals", "subject": "⚙️ Profil einrichten = persönliche Deals!", "theme": "welcome", "cta": "Profil einrichten"},
    {"title": "Zahlungsmethoden erklärt", "subject": "💳 Bezahle wie du willst — Alle Optionen!", "theme": "welcome", "cta": "Optionen sehen"},
    {"title": "Versandinfos und Lieferzeiten", "subject": "🚚 Versand: Schnell, günstig, zuverlässig!", "theme": "welcome", "cta": "Versandinfos"},
    {"title": "Rückgaberecht 30 Tage kostenlos", "subject": "↩️ 30 Tage Rückgabe: Kauf ohne Risiko!", "theme": "welcome", "cta": "Sicher kaufen"},
    {"title": "Garantie und Kundensupport Infos", "subject": "🛡️ Unser Versprechen: Garantie & Top-Support!", "theme": "welcome", "cta": "Support kontaktieren"},
    {"title": "Newsletter Vorteile erklärt", "subject": "📬 Newsletter-Vorteile: Das erwartet dich!", "theme": "welcome", "cta": "Vorteile sehen"},
    {"title": "Empfehle Freunde und verdiene", "subject": "🤑 Empfehle uns: 20€ für dich & deinen Freund!", "theme": "welcome", "cta": "Empfehlen"},
    {"title": "FAQ die wichtigsten Fragen", "subject": "❓ FAQ: Alle wichtigen Antworten für dich!", "theme": "welcome", "cta": "FAQ lesen"},
    {"title": "Bewertungen schreiben und gewinnen", "subject": "⭐ Bewerte & gewinne: Monatlicher Preis!", "theme": "welcome", "cta": "Bewertung schreiben"},
    {"title": "Wunschliste anlegen und teilen", "subject": "❤️ Wunschliste: Anlegen, teilen, erfüllen!", "theme": "welcome", "cta": "Wunschliste"},
    {"title": "Social Media folgen für Extras", "subject": "📱 Folge uns: Exclusive Deals im Feed!", "theme": "welcome", "cta": "Folgen"},
    # ── Sales & Promotions (30) ───────────────────────────────────────────────
    {"title": "Black Friday Vorbereitung Deals", "subject": "🖤 Black Friday: Sei vorbereitet!", "theme": "promotion", "cta": "Deal sichern"},
    {"title": "Cyber Monday Countdown Aktion", "subject": "💻 Cyber Monday: 24h voller Deals!", "theme": "promotion", "cta": "Countdown"},
    {"title": "Mega Sale 50% auf alles", "subject": "🔥 MEGA SALE: 50% auf alle Kategorien!", "theme": "promotion", "cta": "Shoppen"},
    {"title": "Summer Clearance ausverkauf", "subject": "☀️ Summer Clearance: Alles muss raus!", "theme": "promotion", "cta": "Ausverkauf"},
    {"title": "Mid Season Sale Zwischensaison", "subject": "🔄 Mid Season Sale gestartet!", "theme": "promotion", "cta": "Jetzt sparen"},
    {"title": "Private Sale Exklusiv Einladung", "subject": "🔒 Private Sale: Nur du hast Zugang!", "theme": "promotion", "cta": "Zugang nutzen"},
    {"title": "Staffelrabatt mehr kaufen mehr sparen", "subject": "📊 Mehr kaufen = mehr sparen: Staffel-Rabatt!", "theme": "promotion", "cta": "Jetzt staffeln"},
    {"title": "Gutscheincode SOMMER20 gültig", "subject": "🎫 Code SOMMER20: 20% heute einlösen!", "theme": "promotion", "cta": "Code nutzen"},
    {"title": "Preiskracher der Woche Highlight", "subject": "💥 Preiskracher der Woche ist da!", "theme": "promotion", "cta": "Preiskracher sehen"},
    {"title": "Sonderaktion für Stammkunden", "subject": "👑 Nur für Stammkunden: Exklusiver Deal!", "theme": "promotion", "cta": "Einlösen"},
    {"title": "Produktrückruf Rabatt Entschädigung", "subject": "🙏 Als Dankeschön: 15% Sonderrabatt!", "theme": "promotion", "cta": "Einlösen"},
    {"title": "Anniversary Sale Jahrestag", "subject": "🎂 Jahrestag Sale: Gemeinsam feiern!", "theme": "promotion", "cta": "Mitfeiern"},
    {"title": "Geburtstag Firma 5 Jahre", "subject": "🎉 5 Jahre BullPowerHub: Sonderpreise!", "theme": "promotion", "cta": "Feiern"},
    {"title": "Meilenstein 10.000 Bestellungen", "subject": "🏆 10.000 Bestellungen! Dein Geschenk!", "theme": "promotion", "cta": "Geschenk holen"},
    {"title": "Empfehlungsbonus eingelöst Bestätigung", "subject": "✅ Dein Empfehlungsbonus: Jetzt nutzen!", "theme": "promotion", "cta": "Bonus nutzen"},
    {"title": "Geheimverkauf entdeckt intern", "subject": "🤫 Geheimer Sale: Nur via E-Mail!", "theme": "promotion", "cta": "Geheimnis lüften"},
    {"title": "VIP Mitglieder Exclusive first look", "subject": "👀 VIP First Look: Bevor alle anderen!", "theme": "promotion", "cta": "First Look"},
    {"title": "Winterschluss Ausverkauf Final", "subject": "❄️ Winterschluss: Final Sale läuft!", "theme": "promotion", "cta": "Final Sale"},
    {"title": "Gratis Produkt beim Kauf dazu", "subject": "🎁 GRATIS Produkt bei Bestellungen über 50€!", "theme": "promotion", "cta": "Gratis sichern"},
    {"title": "Gewinnspiel Teilnahme Link", "subject": "🎰 Gewinnspiel: Mach mit und gewinne!", "theme": "promotion", "cta": "Mitmachen"},
    {"title": "2er Pack Sparsatz Empfehlung", "subject": "✌️ 2er Pack: 30% günstiger als Einzelkauf!", "theme": "promotion", "cta": "Pack kaufen"},
    {"title": "Kunden werben Kunden Programm", "subject": "👥 Werbe Freunde: 25€ für jeden!", "theme": "promotion", "cta": "Freunde werben"},
    {"title": "Schnäppchen Kalender täglich neu", "subject": "📅 Schnäppchen-Kalender: Täglich ein Deal!", "theme": "promotion", "cta": "Kalender öffnen"},
    {"title": "Letzte Restposten dieses Modells", "subject": "⚠️ Letzte Chance: Modell wird eingestellt!", "theme": "promotion", "cta": "Jetzt sichern"},
    {"title": "Treue Punkte verdoppeln Aktion", "subject": "⬆️ Doppelte Punkte diese Woche!", "theme": "promotion", "cta": "Punkte sammeln"},
    {"title": "Kombinationsangebot Set kaufen", "subject": "🎯 Set kaufen: 40% günstiger als einzeln!", "theme": "promotion", "cta": "Set kaufen"},
    {"title": "Cashback Angebot 5 Prozent zurück", "subject": "💰 5% Cashback: Geld zurück garantiert!", "theme": "promotion", "cta": "Cashback sichern"},
    {"title": "Deal des Monats Mai Highlight", "subject": "🌟 Deal des Monats: Unser Highlight!", "theme": "promotion", "cta": "Deal ansehen"},
    {"title": "Produktpaket Sparset komplett", "subject": "📦 Sparset: Alles was du brauchst!", "theme": "promotion", "cta": "Sparset kaufen"},
    {"title": "Sofortiger Rabatt nach Registrierung", "subject": "⚡ Sofort-Rabatt: Registriere dich jetzt!", "theme": "promotion", "cta": "Registrieren"},
    # ── Produktkategorien (30) ─────────────────────────────────────────────────
    {"title": "Smart Home Ratgeber Einstieg", "subject": "🏠 Smart Home 2026: So startest du!", "theme": "category", "cta": "Smart einrichten"},
    {"title": "Fitness Geräte für Home Gym", "subject": "💪 Home Gym: Die besten Geräte 2026!", "theme": "category", "cta": "Gym aufbauen"},
    {"title": "Küchengadgets Profi Kochen", "subject": "🍳 Profi-Küche: Top Gadgets!", "theme": "category", "cta": "Küche upgraden"},
    {"title": "Büro Ergonomie Ausstattung", "subject": "🖥️ Büro-Upgrade: Ergonomisch arbeiten!", "theme": "category", "cta": "Büro ausrüsten"},
    {"title": "Beauty Essentials Must-haves", "subject": "✨ Beauty Must-haves: Deine Essentials!", "theme": "category", "cta": "Beauty shoppen"},
    {"title": "Outdoor Gear Saison 2026", "subject": "🌿 Outdoor-Gear 2026: Das brauchst du!", "theme": "category", "cta": "Ausrüsten"},
    {"title": "Gaming Setup der Profis", "subject": "🎮 Gaming Setup der Profis enthüllt!", "theme": "category", "cta": "Setup bauen"},
    {"title": "Baby Erstausstattung komplett", "subject": "👶 Baby-Erstausstattung: Alles dabei!", "theme": "category", "cta": "Checkliste"},
    {"title": "Haustier Produkte Premium", "subject": "🐾 Premium für dein Haustier!", "theme": "category", "cta": "Für Tiere"},
    {"title": "Reise Gepäck und Accessoires", "subject": "✈️ Reise-Accessoires: Smart packen!", "theme": "category", "cta": "Reise shoppen"},
    {"title": "Elektronik Top Picks 2026", "subject": "📱 Elektronik Top Picks 2026!", "theme": "category", "cta": "Top Picks"},
    {"title": "Gartenprodukte Saison Start", "subject": "🌱 Gartensaison: Die besten Produkte!", "theme": "category", "cta": "Garten shoppen"},
    {"title": "Sportbekleidung neue Kollektion", "subject": "👟 Neue Sportkollektion ist da!", "theme": "category", "cta": "Kollektion sehen"},
    {"title": "Winterprodukte Kälteschutz", "subject": "❄️ Gegen die Kälte: Unsere Top-Produkte!", "theme": "category", "cta": "Winterprodukte"},
    {"title": "Küchenmesser Premium Set", "subject": "🔪 Premium-Messer: Scharf und langlebig!", "theme": "category", "cta": "Messer entdecken"},
    {"title": "Yoga Zubehör Komplett Set", "subject": "🧘 Yoga-Set: Alles für deine Praxis!", "theme": "category", "cta": "Yoga shoppen"},
    {"title": "Kaffee Espresso Maschinen Guide", "subject": "☕ Kaffeemaschinen: Welche ist die richtige?", "theme": "category", "cta": "Guide lesen"},
    {"title": "Handtaschen Rucksäcke Kollektion", "subject": "👜 Neue Taschen-Kollektion ist online!", "theme": "category", "cta": "Kollektion sehen"},
    {"title": "Uhren Smart Watches Übersicht", "subject": "⌚ Smartwatches 2026: Unsere Übersicht!", "theme": "category", "cta": "Übersicht"},
    {"title": "Kinder Spielzeug sicheres Holz", "subject": "🎠 Sicheres Kinderspielzeug: Holz & Natur!", "theme": "category", "cta": "Sicher spielen"},
    {"title": "Auto Zubehör nützliche Produkte", "subject": "🚗 Auto-Zubehör: Das musst du haben!", "theme": "category", "cta": "Auto upgraden"},
    {"title": "Bücher und E-Reader Empfehlungen", "subject": "📚 Bücher & E-Reader: Unsere Empfehlungen!", "theme": "category", "cta": "Lesen starten"},
    {"title": "Werkzeug Heimwerker Set", "subject": "🔧 Heimwerker-Set: Alles was du brauchst!", "theme": "category", "cta": "Werkzeug shoppen"},
    {"title": "Lebensmittel Superfoods Premium", "subject": "🥑 Superfoods: Premium-Qualität für dich!", "theme": "category", "cta": "Superfoods"},
    {"title": "Männer Pflege Kosmetik Set", "subject": "💈 Männer-Pflege: Das brauchst du wirklich!", "theme": "category", "cta": "Männerpflege"},
    {"title": "Schmuck Accessoires Sommer", "subject": "💍 Sommer-Schmuck: Trends 2026!", "theme": "category", "cta": "Schmuck sehen"},
    {"title": "Wohnzimmer Deko und Möbel", "subject": "🛋️ Wohnzimmer-Upgrade: Unsere Favoriten!", "theme": "category", "cta": "Wohnzimmer"},
    {"title": "Schlafzimmer Bettwäsche Premium", "subject": "😴 Premium-Bettwäsche: Besser schlafen!", "theme": "category", "cta": "Besser schlafen"},
    {"title": "Bad Accessoires Upgrade", "subject": "🚿 Bad-Upgrade: Luxus für jeden Tag!", "theme": "category", "cta": "Bad upgraden"},
    {"title": "Musikinstrumente Hobby Einstieg", "subject": "🎸 Musik als Hobby: Der perfekte Einstieg!", "theme": "category", "cta": "Musik starten"},
    # ── E-Commerce / Business Tips (20) ──────────────────────────────────────
    {"title": "Shopify Store Optimierung Tipps", "subject": "🛒 Shopify: 5 Tipps für mehr Umsatz!", "theme": "business", "cta": "Tipps lesen"},
    {"title": "Email Marketing ROI verbessern", "subject": "📧 Email-ROI: So verdoppelst du ihn!", "theme": "business", "cta": "ROI verbessern"},
    {"title": "Social Media für E-Commerce Guide", "subject": "📱 Social Media = mehr Umsatz: So geht's!", "theme": "business", "cta": "Guide lesen"},
    {"title": "SEO Grundlagen für Online Shop", "subject": "🔍 SEO: Grundlagen für deinen Shop!", "theme": "business", "cta": "SEO lernen"},
    {"title": "Produktfotos für mehr Conversion", "subject": "📸 Bessere Fotos = mehr Verkäufe!", "theme": "business", "cta": "Foto-Tipps"},
    {"title": "Kundenbewertungen generieren How-To", "subject": "⭐ Mehr Bewertungen: So geht's automatisch!", "theme": "business", "cta": "How-To lesen"},
    {"title": "Preisgestaltung Strategie E-Commerce", "subject": "💶 Preisgestaltung: So maximierst du Gewinn!", "theme": "business", "cta": "Strategie"},
    {"title": "Affiliate Marketing starten Guide", "subject": "🤝 Affiliate: Passives Einkommen starten!", "theme": "business", "cta": "Starten"},
    {"title": "Dropshipping Grundlagen 2026", "subject": "📦 Dropshipping 2026: Was du wissen musst!", "theme": "business", "cta": "Grundlagen"},
    {"title": "Amazon vs Shopify Vergleich", "subject": "🥊 Amazon vs Shopify: Was ist besser?", "theme": "business", "cta": "Vergleich lesen"},
    {"title": "KI Tools für Online Business", "subject": "🤖 KI-Tools 2026: Dein Business-Booster!", "theme": "business", "cta": "KI nutzen"},
    {"title": "Chatbot Integration Kundenservice", "subject": "💬 Chatbot = weniger Support-Aufwand!", "theme": "business", "cta": "Chatbot einbauen"},
    {"title": "Instagram Shopping einrichten", "subject": "📸 Instagram Shopping: Anleitung für dich!", "theme": "business", "cta": "Einrichten"},
    {"title": "TikTok Shop 2026 Anleitung", "subject": "🎵 TikTok Shop 2026: So startest du!", "theme": "business", "cta": "TikTok Shop"},
    {"title": "Pinterest Marketing E-Commerce", "subject": "📌 Pinterest: Mehr Traffic für deinen Shop!", "theme": "business", "cta": "Pinterest starten"},
    {"title": "Umsatzsteuer E-Commerce EU", "subject": "🇪🇺 EU-Umsatzsteuer: Was du wissen musst!", "theme": "business", "cta": "Info lesen"},
    {"title": "Retargeting Ads Facebook Google", "subject": "🎯 Retargeting: Kaufabbrecher zurückgewinnen!", "theme": "business", "cta": "Retargeting"},
    {"title": "Conversion Rate optimieren 10 Tipps", "subject": "📈 10 Tipps für bessere Conversion Rate!", "theme": "business", "cta": "Tipps umsetzen"},
    {"title": "Lagerbestand Management Tipps", "subject": "📊 Lager-Management: Nie wieder ausverkauft!", "theme": "business", "cta": "Tipps lesen"},
    {"title": "Kundendienst Automatisierung", "subject": "⚙️ Support automatisieren: Skaliere ohne Stress!", "theme": "business", "cta": "Automatisieren"},
    # ── Events & Webinare (20) ────────────────────────────────────────────────
    {"title": "Webinar Einladung E-Commerce Basics", "subject": "📹 Gratis Webinar: E-Commerce Basics!", "theme": "event", "cta": "Jetzt anmelden"},
    {"title": "Online Workshop Shopify Masterclass", "subject": "🎓 Shopify Masterclass: Jetzt anmelden!", "theme": "event", "cta": "Anmelden"},
    {"title": "Live Stream Produktvorstellung", "subject": "🔴 LIVE: Neue Produkte werden vorgestellt!", "theme": "event", "cta": "Live dabei sein"},
    {"title": "Q&A Session mit Rudolf", "subject": "🎤 Q&A mit Rudolf: Deine Fragen live!", "theme": "event", "cta": "Frage stellen"},
    {"title": "Workshop SEO für Anfänger", "subject": "🔍 SEO Workshop: Grundlagen in 60 Min!", "theme": "event", "cta": "Workshopplatz"},
    {"title": "Podcast Episode Folge 42 neu", "subject": "🎙️ Podcast Ep. 42: Das große E-Commerce!", "theme": "event", "cta": "Hören"},
    {"title": "Messe Stand Besuch Einladung", "subject": "🏛️ Wir sind auf der Messe: Besuche uns!", "theme": "event", "cta": "Treffen"},
    {"title": "Networking Event Online Abend", "subject": "🤝 Networking-Abend: Komm dazu!", "theme": "event", "cta": "Dabei sein"},
    {"title": "Online Kurs E-Commerce starten", "subject": "📚 Kurs: E-Commerce von Null auf Umsatz!", "theme": "event", "cta": "Kurs starten"},
    {"title": "Challenge 7 Tage mehr Umsatz", "subject": "⚡ 7-Tage-Challenge: Mehr Umsatz!", "theme": "event", "cta": "Challenge starten"},
    {"title": "Webinar Recap Zusammenfassung", "subject": "📋 Webinar Recap: Das Beste zusammengefasst!", "theme": "event", "cta": "Recap lesen"},
    {"title": "Live Product Demo neues Gerät", "subject": "🎬 Live Demo: Sieh es in Aktion!", "theme": "event", "cta": "Demo ansehen"},
    {"title": "Instagram Live Shopping Event", "subject": "📱 Instagram Live: Shop mit uns live!", "theme": "event", "cta": "Live shoppen"},
    {"title": "Masterclass Digital Marketing", "subject": "🎓 Masterclass Digital Marketing: Anmelden!", "theme": "event", "cta": "Masterclass"},
    {"title": "YouTube Serie neue Episode", "subject": "▶️ Neue YouTube-Episode ist online!", "theme": "event", "cta": "Jetzt ansehen"},
    {"title": "Community Call jeden Dienstag", "subject": "📞 Community Call: Jeden Dienstag 19 Uhr!", "theme": "event", "cta": "Einwählen"},
    {"title": "Exklusive Demo VIP Gruppe", "subject": "👑 VIP Demo: Nur du bekommst den Link!", "theme": "event", "cta": "VIP Demo"},
    {"title": "Beta Test neues Feature Einladung", "subject": "🧪 Beta-Test: Als Erster testen!", "theme": "event", "cta": "Beta testen"},
    {"title": "Giveaway Gewinnspiel Social", "subject": "🎁 Giveaway: Teile und gewinne mit!", "theme": "event", "cta": "Mitmachen"},
    {"title": "Launch Party neue Kollektion", "subject": "🎉 Launch Party: Neue Kollektion live!", "theme": "event", "cta": "Party beitreten"},
    # ── Automated Flows (20) ──────────────────────────────────────────────────
    {"title": "Bestellbestätigung mit Upsell", "subject": "✅ Bestellung bestätigt + Empfehlung für dich!", "theme": "automated", "cta": "Upsell ansehen"},
    {"title": "Versandbestätigung mit Tracking", "subject": "🚚 Paket unterwegs: Hier dein Tracking!", "theme": "automated", "cta": "Verfolgen"},
    {"title": "Lieferbestätigung Bewertung bitte", "subject": "📦 Paket angekommen? Wie war's?", "theme": "automated", "cta": "Bewerten"},
    {"title": "Abonnement läuft ab Erinnerung", "subject": "⏰ Dein Abonnement: Noch 7 Tage!", "theme": "automated", "cta": "Verlängern"},
    {"title": "Passwort Reset Bestätigung", "subject": "🔑 Passwort zurückgesetzt: Alles sicher!", "theme": "automated", "cta": "Einloggen"},
    {"title": "Rückgabe Status Update", "subject": "↩️ Rückgabe-Update: So steht's!", "theme": "automated", "cta": "Status prüfen"},
    {"title": "Warteliste Verfügbar Benachrichtigung", "subject": "🔔 Dein Produkt ist wieder verfügbar!", "theme": "automated", "cta": "Jetzt kaufen"},
    {"title": "Preissenkung Alert Wunschliste", "subject": "💲 Preissenkung: Dein Wunschprodukt!", "theme": "automated", "cta": "Kaufen"},
    {"title": "Geburtstag Email mit Rabatt", "subject": "🎂 Alles Gute! Dein Geburtstagsgeschenk!", "theme": "automated", "cta": "Geschenk holen"},
    {"title": "Jahrestag Email Danke", "subject": "🥳 1 Jahr bei uns: Danke für deine Treue!", "theme": "automated", "cta": "Bonus holen"},
    {"title": "Warenkorb Abandon 1h danach", "subject": "🛒 Vergessen? Dein Warenkorb wartet!", "theme": "automated", "cta": "Kaufen"},
    {"title": "Warenkorb Abandon 24h danach", "subject": "⏰ 24h vergangen: Produkt fast weg!", "theme": "automated", "cta": "Jetzt kaufen"},
    {"title": "Post Purchase Email Cross-Sell", "subject": "❤️ Perfekt dazu: Das empfehlen wir!", "theme": "automated", "cta": "Ergänzen"},
    {"title": "Repeat Purchase Trigger", "subject": "🔄 Zeit für Nachschub? Wir erinnern!", "theme": "automated", "cta": "Nachkaufen"},
    {"title": "Treuepunkte Zusammenfassung", "subject": "⭐ Deine Punkte: So viel hast du!", "theme": "automated", "cta": "Punkte einlösen"},
    {"title": "VIP Upgrade Notification", "subject": "👑 Du bist jetzt VIP-Mitglied!", "theme": "automated", "cta": "Vorteile sehen"},
    {"title": "Bestandswarnmeldung niedrig", "subject": "⚠️ Fast ausverkauft: Handle jetzt!", "theme": "automated", "cta": "Sofort kaufen"},
    {"title": "Survey nach 7 Tagen Kauf", "subject": "📋 7 Tage danach: Wie war dein Kauf?", "theme": "automated", "cta": "Bewerten"},
    {"title": "Reorder Reminder Verbrauchsgut", "subject": "⏰ Zeit für Nachbestellung: Noch Lager?", "theme": "automated", "cta": "Nachbestellen"},
    {"title": "Checkout Abbruch E-Mail", "subject": "🛑 Fast fertig! Beende deinen Kauf!", "theme": "automated", "cta": "Checkout fortsetzen"},
    # ── Content & Inspiration (20) ────────────────────────────────────────────
    {"title": "Wohninspo Sommer 2026 Ideen", "subject": "🏡 Wohninspo Sommer 2026: So geht's!", "theme": "content", "cta": "Inspiration"},
    {"title": "Rezept der Woche gesund kochen", "subject": "🥗 Rezept der Woche: Lecker & gesund!", "theme": "content", "cta": "Rezept sehen"},
    {"title": "Fitness Motivation Montag", "subject": "💪 Montags-Motivation: Starte die Woche!", "theme": "content", "cta": "Motiviert werden"},
    {"title": "Reise Destination Tipp Sommer", "subject": "✈️ Reisetipp: Das schönste Ziel 2026!", "theme": "content", "cta": "Destination entdecken"},
    {"title": "DIY Projekt Wochenende Idee", "subject": "🔨 Wochenend-DIY: Einfach und kreativ!", "theme": "content", "cta": "Projekt starten"},
    {"title": "Tech News August Zusammenfassung", "subject": "💻 Tech-News im Überblick!", "theme": "content", "cta": "Lesen"},
    {"title": "Lifestyle Blog Artikel neu", "subject": "📖 Neuer Blog: Das liest gerade alle!", "theme": "content", "cta": "Blog lesen"},
    {"title": "Fotos Upload Challenge Community", "subject": "📸 Challenge: Zeig uns dein Setup!", "theme": "content", "cta": "Mitmachen"},
    {"title": "Video Tutorial Produkt richtig nutzen", "subject": "▶️ Tutorial: So nutzt du es richtig!", "theme": "content", "cta": "Video sehen"},
    {"title": "Podcast Empfehlung diese Woche", "subject": "🎙️ Podcast der Woche: Hör rein!", "theme": "content", "cta": "Hören"},
    {"title": "Infografik Markttrends 2026", "subject": "📊 Infografik: E-Commerce Trends 2026!", "theme": "content", "cta": "Grafik ansehen"},
    {"title": "Buchempfehlung für Unternehmer", "subject": "📚 Buchempfehlung: Das musst du lesen!", "theme": "content", "cta": "Buch sehen"},
    {"title": "Playlist Musik für Produktivität", "subject": "🎵 Playlist: Musik die produktiv macht!", "theme": "content", "cta": "Hören"},
    {"title": "App Empfehlung diese Woche", "subject": "📱 App der Woche: Das nutzen Profis!", "theme": "content", "cta": "App testen"},
    {"title": "Instagram Reels Trend Mitmachen", "subject": "📱 Reels Trend: Mach mit und werde viral!", "theme": "content", "cta": "Mitmachen"},
    {"title": "Fitness Woche Plan kostenlos", "subject": "🏋️ Gratis Wochenplan: So trainierst du!", "theme": "content", "cta": "Plan holen"},
    {"title": "Meal Prep Tipps Woche Starten", "subject": "🍱 Meal Prep: Woche mit Köpfchen starten!", "theme": "content", "cta": "Tipps nutzen"},
    {"title": "Behind the Product Herstellung Video", "subject": "🏭 So wird's gemacht: Behind the Scenes!", "theme": "content", "cta": "Video ansehen"},
    {"title": "Kunden Story Erfahrungsbericht", "subject": "💬 Kundenstory: Das hat es verändert!", "theme": "content", "cta": "Story lesen"},
    {"title": "Tages Tipp kurz und knapp", "subject": "💡 Tipp des Tages: Schnell umsetzbar!", "theme": "content", "cta": "Tipp lesen"},
    # ── Produktneuheiten & Updates (20) ──────────────────────────────────────
    {"title": "Neue Farben beliebtestes Produkt", "subject": "🎨 Neue Farben für deinen Liebling!", "theme": "product_update", "cta": "Farben wählen"},
    {"title": "Version 2.0 Produkt Upgrade", "subject": "🆙 Version 2.0 ist da: Besser als je zuvor!", "theme": "product_update", "cta": "Upgrade sehen"},
    {"title": "Rezension Zusammenfassung Kunden", "subject": "⭐ Was Kunden zur neuen Version sagen!", "theme": "product_update", "cta": "Rezensionen"},
    {"title": "Größen Erweiterung Kollektion", "subject": "📏 Neue Größen: Jetzt für alle!", "theme": "product_update", "cta": "Größe wählen"},
    {"title": "Verbessertes Material gleicher Preis", "subject": "✨ Besser geworden: Gleiches Preis!", "theme": "product_update", "cta": "Verbesserung sehen"},
    {"title": "Nachhaltigkeit Update Bio Material", "subject": "🌱 Nachhaltiger: Jetzt aus Biomaterial!", "theme": "product_update", "cta": "Eco entdecken"},
    {"title": "Neue Zertifizierung erhalten", "subject": "🏅 Zertifiziert: Neue Qualitätssiegel!", "theme": "product_update", "cta": "Zertifikat sehen"},
    {"title": "Verpackung verbessert plastikfrei", "subject": "♻️ Neue Verpackung: 100% plastikfrei!", "theme": "product_update", "cta": "Mehr erfahren"},
    {"title": "Bundle neu zusammengestellt", "subject": "📦 Neues Bundle: Noch besser zusammengestellt!", "theme": "product_update", "cta": "Bundle sehen"},
    {"title": "Erweiterung Produktlinie neue Kategorie", "subject": "🆕 Neue Kategorie: Entdecke was neu ist!", "theme": "product_update", "cta": "Neue Kat."},
    {"title": "Preis reduziert dauerhaft", "subject": "💲 Dauerhafte Preissenkung: Jetzt noch günstiger!", "theme": "product_update", "cta": "Günstig kaufen"},
    {"title": "Qualitätskontrolle verbesserter Prozess", "subject": "✅ Bessere Qualität: So haben wir verbessert!", "theme": "product_update", "cta": "Qualität"},
    {"title": "Internationale Verfügbarkeit EU", "subject": "🇪🇺 Jetzt EU-weit: Wir liefern überall hin!", "theme": "product_update", "cta": "Liefergebiet"},
    {"title": "Express Variante neu verfügbar", "subject": "⚡ Express-Version: Schneller und besser!", "theme": "product_update", "cta": "Express wählen"},
    {"title": "Sonderanfertigung möglich Individuell", "subject": "✂️ Individualisierung: Jetzt möglich!", "theme": "product_update", "cta": "Individuell bestellen"},
    {"title": "Combo Deal erweitert Neues hinzu", "subject": "➕ Combo erweitert: Mehr für dein Geld!", "theme": "product_update", "cta": "Combo sehen"},
    {"title": "Produktbewertung 5 Sterne erreicht", "subject": "🌟 5-Sterne-Produkt: Kundenmeinung lesen!", "theme": "product_update", "cta": "Bewertungen"},
    {"title": "Saisonale Kollektion ausverkauft bald", "subject": "⚠️ Saisonale Kollektion: Fast weg!", "theme": "product_update", "cta": "Letzte Chance"},
    {"title": "DIY Kit Version jetzt erhältlich", "subject": "🔧 DIY-Kit: Selber bauen & sparen!", "theme": "product_update", "cta": "DIY Kit"},
    {"title": "PRO Version für Profis Launch", "subject": "💼 PRO-Version: Für die nächste Stufe!", "theme": "product_update", "cta": "PRO entdecken"},
    # ── Sonstiges (20) ────────────────────────────────────────────────────────
    {"title": "Feedback Umfrage 3 Minuten", "subject": "📋 3 Min Umfrage: Deine Meinung zählt!", "theme": "other", "cta": "Teilnehmen"},
    {"title": "Spende Charity Aktion Oktober", "subject": "❤️ Wir spenden: Jeder Kauf hilft!", "theme": "other", "cta": "Mitmachen"},
    {"title": "Unternehmensneuigkeiten Update", "subject": "📣 News vom Unternehmen: Das müsst ihr wissen!", "theme": "other", "cta": "Lesen"},
    {"title": "Presse Bericht Erwähnung Stolz", "subject": "📰 In der Presse: Wir wurden erwähnt!", "theme": "other", "cta": "Artikel lesen"},
    {"title": "Preisverleihung Gewinner 2026", "subject": "🏆 Wir haben gewonnen: Preis 2026!", "theme": "other", "cta": "Preisinfo"},
    {"title": "Neue Mitarbeiter Team vorstellung", "subject": "👥 Unser Team wächst: Neue Mitglieder!", "theme": "other", "cta": "Team kennenlernen"},
    {"title": "Datenschutz Update Information", "subject": "🔒 Datenschutz-Update: Was du wissen musst!", "theme": "other", "cta": "Lesen"},
    {"title": "AGB Änderung Information Kunden", "subject": "📜 AGB-Update: Kurz erklärt für dich!", "theme": "other", "cta": "Info lesen"},
    {"title": "Umzug Büro neue Adresse", "subject": "🏢 Wir ziehen um: Neue Adresse!", "theme": "other", "cta": "Neue Adresse"},
    {"title": "Betriebsurlaub Information Termine", "subject": "🏖️ Betriebsurlaub: Diese Tage geschlossen!", "theme": "other", "cta": "Termine sehen"},
    {"title": "Systemwartung Ankündigung Downtime", "subject": "⚙️ Wartung am Wochenende: Info!", "theme": "other", "cta": "Info lesen"},
    {"title": "Neue Zahlungsmethode PayPal Klarna", "subject": "💳 Neu: Jetzt mit Klarna zahlen!", "theme": "other", "cta": "Zahlen mit"},
    {"title": "CO2 Ausgleich Klimaneutral Update", "subject": "🌍 Klimaneutral: Unser CO2-Update!", "theme": "other", "cta": "Lesen"},
    {"title": "Partner Vorstellung Kooperation", "subject": "🤝 Unser neuer Partner: Spannend!", "theme": "other", "cta": "Partner kennen"},
    {"title": "Student Rabatt Einführung Edu", "subject": "🎓 Studentenrabatt: Jetzt beantragen!", "theme": "other", "cta": "Rabatt"},
    {"title": "NGO Rabatt Nonprofit Organisation", "subject": "❤️ NGO-Rabatt: Für gemeinnützige Zwecke!", "theme": "other", "cta": "Beantragen"},
    {"title": "Geschäftskunden B2B Angebot", "subject": "💼 B2B-Angebot: Für Unternehmen!", "theme": "other", "cta": "B2B anfragen"},
    {"title": "Affiliate Programm starten Info", "subject": "🔗 Affiliate-Programm: Verdiene mit uns!", "theme": "other", "cta": "Starten"},
    {"title": "Jahresabschluss Danke E-Mail", "subject": "🙏 Danke fürs Jahr: Unser Dank an dich!", "theme": "other", "cta": "Danke lesen"},
    {"title": "Neujahr Vorsatz Produktauswahl", "subject": "🎊 Neues Jahr = Neues Du: Unsere Picks!", "theme": "other", "cta": "Neustart"},
]


async def _mc_post(path: str, data: dict) -> dict:
    if not API_KEY:
        return {"error": "no MAILCHIMP_API_KEY"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{BASE}{path}", headers=_auth(), json=data,
                              timeout=aiohttp.ClientTimeout(total=25)) as r:
                return await r.json()
    except Exception as e:
        return {"error": str(e)}


async def _mc_get(path: str) -> dict:
    if not API_KEY:
        return {}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE}{path}", headers=_auth(),
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except Exception:
        return {}


async def _ai(prompt: str, max_tokens: int = 300) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=max_tokens)
    except Exception:
        return ""


async def _notify(msg: str):
    try:
        from modules.notify_hub import notify
        await notify(msg, level="info")
    except Exception as _e:
        log.debug("skipped: %s", _e)


async def _get_list_id() -> str:
    if LIST_ID:
        return LIST_ID
    r = await _mc_get("/lists?count=1")
    lists = r.get("lists", [])
    if lists:
        return lists[0]["id"]
    return ""


def _build_html(tmpl: dict, ai_body: str = "") -> str:
    name = tmpl.get("title", "")
    cta  = tmpl.get("cta", "Jetzt entdecken")
    if not ai_body:
        ai_body = f"<p>Entdecke unsere aktuellen Highlights und profitiere von exklusiven Angeboten.</p>"
    return f"""<!DOCTYPE html>
<html><body style='font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:0'>
<table width='100%' cellpadding='0' cellspacing='0'><tr><td align='center' style='padding:20px'>
<table width='600' cellpadding='0' cellspacing='0' style='background:#fff;border-radius:8px;overflow:hidden'>
<tr><td style='background:#1a1a2e;padding:20px;text-align:center'>
  <h1 style='color:#fff;margin:0;font-size:24px'>{name}</h1>
</td></tr>
<tr><td style='padding:30px'>
  {ai_body}
  <div style='text-align:center;margin:30px 0'>
    <a href='{SHOP_URL}' style='background:#e63946;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold'>{cta} →</a>
  </div>
</td></tr>
<tr><td style='background:#f5f5f5;padding:15px;text-align:center'>
  <p style='color:#888;font-size:12px;margin:0'>BullPowerHub · Abmelden: *|UNSUB|*</p>
</td></tr>
</table></td></tr></table>
</body></html>"""


async def create_mailchimp_campaign(tmpl: dict) -> dict:
    """Erstellt + sendet eine Mailchimp-Kampagne."""
    list_id = await _get_list_id()
    if not list_id:
        return {"ok": False, "error": "no Mailchimp list found"}

    title   = tmpl["title"]
    subject = tmpl["subject"]
    theme   = tmpl.get("theme", "general")

    prompt = f"""Schreibe einen kurzen deutschen E-Mail-Body (HTML) für:
Kampagne: "{title}"
Thema: {theme}
Nur: 1 Headline h2, 2-3 Sätze Fließtext, kein CTA. Max 100 Wörter."""
    ai_body = await _ai(prompt, max_tokens=150)
    html    = _build_html(tmpl, ai_body or "")

    # 1. Campaign erstellen
    camp_r = await _mc_post("/campaigns", {
        "type": "regular",
        "settings": {
            "subject_line": subject[:150],
            "title": title[:100],
            "from_name": FROM_NAME,
            "reply_to": FROM_EMAIL,
        },
        "recipients": {"list_id": list_id},
    })
    cid = camp_r.get("id")
    if not cid:
        return {"ok": False, "error": str(camp_r.get("detail", camp_r))[:300]}

    # 2. Content setzen
    await _mc_post(f"/campaigns/{cid}/content", {"html": html})

    # 3. Senden
    send_r = await _mc_post(f"/campaigns/{cid}/actions/send", {})
    sent   = send_r.get("status") != "error" if "status" in send_r else True

    try:
        from modules.supabase_client import get_client
        get_client().table("mailchimp_mass_campaigns").insert({
            "campaign_id": cid, "title": title, "subject": subject,
            "theme": theme, "sent": sent,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as _e:
        log.debug("skipped: %s", _e)

    return {"ok": True, "campaign_id": cid, "title": title, "sent": sent}


async def _worker(queue: asyncio.Queue, results: list, worker_id: int):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        try:
            r = await create_mailchimp_campaign(item)
            results.append(r)
            log.info("MC W%d %s %s", worker_id, "✅" if r.get("ok") else "❌", item["title"][:50])
        except Exception as e:
            results.append({"ok": False, "error": str(e)})
        finally:
            queue.task_done()
        await asyncio.sleep(3)


async def mass_create_mailchimp_campaigns(count: int = 200, workers: int = 3) -> dict:
    existing: set[str] = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("mailchimp_mass_campaigns").select("title").execute()
        existing = {r["title"] for r in rows.data or []}
    except Exception as _e:
        log.debug("skipped: %s", _e)

    templates = [t for t in MC_TEMPLATES if t["title"] not in existing]
    random.shuffle(templates)
    if len(templates) > count:
        templates = templates[:count]

    if not templates:
        return {"ok": True, "created": 0, "note": "all templates already created"}

    queue: asyncio.Queue = asyncio.Queue()
    for t in templates:
        await queue.put(t)
    for _ in range(workers):
        await queue.put(None)

    results: list = []

    async def tracker():
        last = 0
        while True:
            await asyncio.sleep(15)
            ok_now = sum(1 for r in results if r.get("ok"))
            if ok_now >= last + 25:
                last = ok_now
                await _notify(f"📧 Mailchimp Mass: {ok_now} Kampagnen erstellt!")

    worker_tasks = [asyncio.create_task(_worker(queue, results, i)) for i in range(workers)]
    t = asyncio.create_task(tracker())
    await queue.join()
    for wt in worker_tasks:
        wt.cancel()
    t.cancel()

    ok  = sum(1 for r in results if r.get("ok"))
    err = len(results) - ok

    if ok > 0:
        try:
            from modules.brutus_core import fire
            await fire("Mailchimp Mass Kampagnen gestartet",
                       f"✅ {ok} Mailchimp Kampagnen erstellt & gesendet!",
                       channels=["telegram", "slack"])
        except Exception as _e:
            log.debug("skipped: %s", _e)

    await _notify(f"✅ Mailchimp Mass Complete: {ok} Kampagnen, {err} failed!")
    return {"ok": True, "created": ok, "failed": err}


async def run_daily_mailchimp_campaigns(count: int = 2) -> dict:
    return await mass_create_mailchimp_campaigns(count=count, workers=2)


async def get_mailchimp_mass_stats() -> dict:
    total = len(MC_TEMPLATES)
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("mailchimp_mass_campaigns").select("id", count="exact").execute()
        created = rows.count or 0
    except Exception:
        created = 0
    return {"ok": True, "templates": total, "created_in_db": created,
            "remaining": max(0, total - created)}
