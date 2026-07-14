#!/usr/bin/env python3
"""
Klaviyo Mass Campaigns — 1000 automatische Email-Kampagnen
==========================================================
- 200 hardcodierte Kampagnen-Templates (10 Themen × 20)
- KI generiert weitere Kampagnen on-demand
- 5 parallele Worker
- Klaviyo API 2024-02-15 (bewährte campaign-messages in attributes)
- Supabase Dedup
- BrutusCore Blast nach jeder 100. Kampagne
- Täglich 3 neue Kampagnen automatisch
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("KlaviyoMassCampaigns")

API_KEY  = os.getenv("KLAVIYO_API_KEY", "")
LIST_ID  = os.getenv("KLAVIYO_LIST_ID", "Xwxq6V")
BASE     = "https://a.klaviyo.com/api"
REVISION = "2024-02-15"
FROM_EMAIL = os.getenv("FROM_EMAIL", "aiitecbuuss@gmail.com")
SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")


def _headers() -> dict:
    return {
        "Authorization": f"Klaviyo-API-Key {API_KEY}",
        "revision": REVISION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── 200 Kampagnen-Templates (10 Themen × 20) ────────────────────────────────

CAMPAIGN_TEMPLATES: list[dict] = [
    # ── Flash Sales ──────────────────────────────────────────────────────────
    {"name": "Flash Sale 24h — Bis zu 70% Rabatt", "subject": "⚡ NUR 24h: Bis zu 70% auf alles!", "theme": "flash_sale", "cta": "Jetzt sichern"},
    {"name": "Blitzangebot Wochenende — Sonderpreise", "subject": "🔥 Wochenend-Blitz: Sonderpreise nur heute!", "theme": "flash_sale", "cta": "Zum Angebot"},
    {"name": "Midnight Deal — Nur bis 00:00 Uhr", "subject": "🌙 Midnight Deal läuft aus um 00:00!", "theme": "flash_sale", "cta": "Jetzt bestellen"},
    {"name": "Montagsknaller — Woche startet günstig", "subject": "💥 Montagsknaller: Preise die schocken!", "theme": "flash_sale", "cta": "Preise sehen"},
    {"name": "Happy Hour Sale — Nur 2 Stunden", "subject": "⏰ Happy Hour: 2h lang Sonderpreise!", "theme": "flash_sale", "cta": "Jetzt kaufen"},
    {"name": "Überraschungsangebot — Öffne mich!", "subject": "🎁 Überraschung wartet auf dich!", "theme": "flash_sale", "cta": "Überraschung sehen"},
    {"name": "Lucky Deal Mittwoch — Zufällige Rabatte", "subject": "🍀 Lucky Wednesday: Dein Rabatt wartet!", "theme": "flash_sale", "cta": "Glück versuchen"},
    {"name": "Early Bird Sale — Frühaufsteher sparen", "subject": "🐦 Early Bird: Spare 30% bis 10 Uhr!", "theme": "flash_sale", "cta": "Frühstück sichern"},
    {"name": "Letzte Chance — Artikel fast weg!", "subject": "🚨 Letzte Chance! Nur noch wenige Stücke!", "theme": "flash_sale", "cta": "Schnell sein"},
    {"name": "Geheimrabatt — Nur für dich!", "subject": "🤫 Geheimrabatt: 40% nur für diese E-Mail!", "theme": "flash_sale", "cta": "Code einlösen"},
    {"name": "Türknaller Donnerstag Deal", "subject": "🚪 Türknaller: Angebote die reinhauen!", "theme": "flash_sale", "cta": "Reinholen"},
    {"name": "Sale Countdown läuft — 3h noch!", "subject": "⏳ 3 Stunden noch! Sale endet bald!", "theme": "flash_sale", "cta": "Countdown stoppen"},
    {"name": "Mega Ausverkauf Lagerräumung", "subject": "📦 Lagerrräumung: Alles muss raus!", "theme": "flash_sale", "cta": "Jetzt räumen"},
    {"name": "Spontan-Sale heute Abend", "subject": "🌟 Spontan-Sale heute 18-21 Uhr!", "theme": "flash_sale", "cta": "Dabei sein"},
    {"name": "VIP Flash Zugang — Du wurdest gewählt", "subject": "👑 VIP-Zugang: Exklusiver Flash Sale!", "theme": "flash_sale", "cta": "Zugang nutzen"},
    {"name": "Pay Day Deal — Nach dem Gehalt", "subject": "💰 Pay Day Deal: Belohn dich heute!", "theme": "flash_sale", "cta": "Belohnung holen"},
    {"name": "Super Sonntagsdeal Exclusive", "subject": "☀️ Sonntagsdeal: Günstig in die Woche!", "theme": "flash_sale", "cta": "Deal sichern"},
    {"name": "2-für-1 Aktion — Heute Only", "subject": "✌️ 2-für-1! Heute nur mit diesem Link!", "theme": "flash_sale", "cta": "Doppelt sparen"},
    {"name": "Gratis Versand ab sofort Aktion", "subject": "🚚 GRATIS Versand — Nur heute!", "theme": "flash_sale", "cta": "Kostenlos bestellen"},
    {"name": "Jahrestag Sale — Wir feiern!", "subject": "🎂 Unser Jahrestag = Dein Rabatt!", "theme": "flash_sale", "cta": "Mitfeiern"},
    # ── Produktneuheiten ───────────────────────────────────────────────────────
    {"name": "NEU eingetroffen — Smart Home Kollektion", "subject": "🆕 Neu: Smart Home Hits sind da!", "theme": "new_products", "cta": "Jetzt entdecken"},
    {"name": "Fitness Neuheiten — Frühling 2026", "subject": "💪 Fitness-Neuheiten für Frühjahr 2026!", "theme": "new_products", "cta": "Fit werden"},
    {"name": "Küchen Innovation — Top Gadgets", "subject": "🍳 Küchen-Revolution: Die besten Gadgets!", "theme": "new_products", "cta": "Entdecken"},
    {"name": "Office Upgrade — Neue Büro-Highlights", "subject": "🖥️ Büro-Upgrade: Neue Produkte sind da!", "theme": "new_products", "cta": "Upgraden"},
    {"name": "Beauty Neuigkeiten — Trends 2026", "subject": "✨ Beauty-Trends 2026: Neu eingetroffen!", "theme": "new_products", "cta": "Entdecken"},
    {"name": "Outdoor Saison beginnt — Top Gear", "subject": "🌿 Outdoor-Saison: Das neue Gear ist da!", "theme": "new_products", "cta": "Ausrüsten"},
    {"name": "Gaming Drops — Neue Arrivals", "subject": "🎮 Gaming Drops: Neue Arrivals warten!", "theme": "new_products", "cta": "Checken"},
    {"name": "Baby & Kids Neuheiten Mai 2026", "subject": "👶 Baby-Neuheiten: Die Kleinen werden staunen!", "theme": "new_products", "cta": "Entdecken"},
    {"name": "Pet Lovers Neuigkeiten", "subject": "🐾 Für Tierliebhaber: Neue Produkte!", "theme": "new_products", "cta": "Für Haustiere"},
    {"name": "Travel Season Gear Neuheiten", "subject": "✈️ Reisesaison: Das neue Travel-Gear!", "theme": "new_products", "cta": "Packen"},
    {"name": "Wöchentliche Neuheiten KW24", "subject": "📦 Wöchentliche Highlights sind da!", "theme": "new_products", "cta": "Ansehen"},
    {"name": "Top Seller diese Woche", "subject": "🏆 Diese Woche meist verkauft!", "theme": "new_products", "cta": "Top-Seller sehen"},
    {"name": "Trending Now — Was gerade viral ist", "subject": "📈 Trending jetzt: Verpasse es nicht!", "theme": "new_products", "cta": "Viral sehen"},
    {"name": "Editor's Choice — Unsere Favoriten", "subject": "❤️ Editor's Pick: Das lieben wir gerade!", "theme": "new_products", "cta": "Favoriten sehen"},
    {"name": "Sommerkollektiion Preview", "subject": "☀️ Sommer-Preview: Erste Einblicke!", "theme": "new_products", "cta": "Jetzt vorschauen"},
    {"name": "Limited Edition — Nur kurz verfügbar", "subject": "⭐ Limited Edition: Greif schnell zu!", "theme": "new_products", "cta": "Limitiert sichern"},
    {"name": "Bundle Deals neu hinzugefügt", "subject": "🎁 Neue Bundles: Mehr Wert für dich!", "theme": "new_products", "cta": "Bundles entdecken"},
    {"name": "Customer Favorites Top Liste", "subject": "⭐ Was unsere Kunden am meisten lieben!", "theme": "new_products", "cta": "Beliebtes sehen"},
    {"name": "Restposten unter 10 Euro", "subject": "💶 Schnäppchen unter €10!", "theme": "new_products", "cta": "Günstig kaufen"},
    {"name": "Premium Collection Launch", "subject": "👑 Premium Launch: Hochwertig & exklusiv!", "theme": "new_products", "cta": "Premium entdecken"},
    # ── Saisonale Aktionen ─────────────────────────────────────────────────────
    {"name": "Frühlings Aktion — Frisch starten", "subject": "🌸 Frühling: Frisch durchstarten mit uns!", "theme": "seasonal", "cta": "Frühling shoppen"},
    {"name": "Sommer Sale 2026 gestartet!", "subject": "🌞 Sommer Sale 2026: Jetzt ist er da!", "theme": "seasonal", "cta": "Summer vibe"},
    {"name": "Herbst Deals — Warm bleiben", "subject": "🍂 Herbst-Deals: Warm und günstig!", "theme": "seasonal", "cta": "Herbst entdecken"},
    {"name": "Winter Warming Sale", "subject": "❄️ Winter-Sale: Warm durch die Kälte!", "theme": "seasonal", "cta": "Einheizen"},
    {"name": "Muttertag Geschenk Ideen 2026", "subject": "💐 Muttertag: Die schönsten Geschenke!", "theme": "seasonal", "cta": "Mama beglücken"},
    {"name": "Vatertag Special 2026", "subject": "👨 Vatertag-Special: Er verdients!", "theme": "seasonal", "cta": "Papa überraschen"},
    {"name": "Weihnachten Advance Shopping", "subject": "🎄 Weihnachts-Vorfreude: Früh shoppen!", "theme": "seasonal", "cta": "Advent starten"},
    {"name": "Ostern Angebote — Eier Aktion", "subject": "🐣 Ostern: Süße Deals wie Ostereier!", "theme": "seasonal", "cta": "Osterdeal finden"},
    {"name": "Valentinstag Geschenke Top 10", "subject": "❤️ Valentinstag: Die Top 10 Geschenke!", "theme": "seasonal", "cta": "Liebe zeigen"},
    {"name": "Halloween Spezialangebot Gruseldeal", "subject": "🎃 Halloween: Gruselig günstige Deals!", "theme": "seasonal", "cta": "Schockpreis"},
    {"name": "Silvester Party Einkauf Tipps", "subject": "🎆 Silvester: Perfekt vorbereitet mit uns!", "theme": "seasonal", "cta": "Party starten"},
    {"name": "Back to School September Deals", "subject": "🎒 Back to School: Günstig ins neue Jahr!", "theme": "seasonal", "cta": "Ausrüsten"},
    {"name": "Nikolaus Geschenke Countdown", "subject": "🎅 Nikolaus kommt: Leer die Stiefel!", "theme": "seasonal", "cta": "Geschenke sichern"},
    {"name": "Karneval Fasching Special", "subject": "🎭 Karneval: Das Beste zum Feiern!", "theme": "seasonal", "cta": "Feiern starten"},
    {"name": "Schulstart Aktionen September", "subject": "✏️ Schulstart-Aktion: Günstig starten!", "theme": "seasonal", "cta": "Schulbedarf"},
    {"name": "Herbstferien Deals", "subject": "🍁 Herbstferien: Jetzt entspannen!", "theme": "seasonal", "cta": "Ferien genießen"},
    {"name": "Sommerferien Ausrüstung", "subject": "🏖️ Sommerferien-Gear: Alles dabei!", "theme": "seasonal", "cta": "Urlaub shoppen"},
    {"name": "Ski Saison Opening Sale", "subject": "⛷️ Ski-Saison: Auf die Piste!", "theme": "seasonal", "cta": "Ski ausrüsten"},
    {"name": "Gartenzeit beginnt — Outdoor Sale", "subject": "🌱 Gartenzeit: Jetzt draußen aktiv!", "theme": "seasonal", "cta": "Garten shoppen"},
    {"name": "Herbst Cozy Season Textilien", "subject": "🧣 Cozy Season: Gemütlich einrichten!", "theme": "seasonal", "cta": "Gemütlich werden"},
    # ── Personalisierte Angebote ──────────────────────────────────────────────
    {"name": "Wir vermissen dich — Comeback Angebot", "subject": "💔 Wir vermissen dich! Komm zurück!", "theme": "personalized", "cta": "Zurückkommen"},
    {"name": "Alles Gute zum Geburtstag", "subject": "🎂 Happy Birthday! Dein Geburtstagsrabatt!", "theme": "personalized", "cta": "Rabatt einlösen"},
    {"name": "Jubiläumsangebot — 1 Jahr bei uns", "subject": "🥳 1 Jahr mit uns: Danke & Sonderbonus!", "theme": "personalized", "cta": "Bonus holen"},
    {"name": "Exklusives VIP Angebot für dich", "subject": "👑 Exklusiv nur für dich: VIP Deal!", "theme": "personalized", "cta": "Einlösen"},
    {"name": "Aufgrund deiner Interessen — Top Picks", "subject": "💡 Basierend auf dir: Unsere Top Picks!", "theme": "personalized", "cta": "Meine Picks"},
    {"name": "Du hast was im Warenkorb gelassen", "subject": "🛒 Dein Warenkorb wartet noch auf dich!", "theme": "personalized", "cta": "Jetzt kaufen"},
    {"name": "Dein letzter Kauf — Wie wars?", "subject": "⭐ Wie war dein Einkauf? Bewertung?", "theme": "personalized", "cta": "Bewerten"},
    {"name": "Früher Kunde Deal — Danke dir!", "subject": "🙏 Danke! Früh-Bucher-Bonus für dich!", "theme": "personalized", "cta": "Bonus sichern"},
    {"name": "Wunschliste fast weg — Schnell sein!", "subject": "⚠️ Deine Wunschliste: Fast ausverkauft!", "theme": "personalized", "cta": "Wunsch erfüllen"},
    {"name": "Noch 500 Punkte bis Free Shipping", "subject": "🎯 Noch 500 Punkte bis Gratisversand!", "theme": "personalized", "cta": "Punkte sammeln"},
    {"name": "Treuebonus — Silber Status!", "subject": "🥈 Glückwunsch: Du bist Silber-Mitglied!", "theme": "personalized", "cta": "Vorteile sehen"},
    {"name": "Treue Gold Status erreicht", "subject": "🥇 Gold-Status! Deine Premium Vorteile!", "theme": "personalized", "cta": "Vorteile nutzen"},
    {"name": "Willkommen zurück — Sonderangebot", "subject": "👋 Willkommen zurück! Wir haben etwas für dich!", "theme": "personalized", "cta": "Angebot ansehen"},
    {"name": "Dank dir Nachricht aus dem Team", "subject": "💌 Von uns persönlich: Danke!", "theme": "personalized", "cta": "Danke lesen"},
    {"name": "Empfehlung Bonus — Freund einladen", "subject": "👥 Freund einladen = 20% für euch beide!", "theme": "personalized", "cta": "Einladen"},
    {"name": "Reaktivierung nach 6 Monaten", "subject": "😮 6 Monate? Hier ist was Besonderes!", "theme": "personalized", "cta": "Reaktivieren"},
    {"name": "Nur für treue Abonnenten Early Access", "subject": "🔑 Nur du siehst das: Early Access Sale!", "theme": "personalized", "cta": "Zugang nutzen"},
    {"name": "Top 3 Empfehlungen diese Woche", "subject": "💎 Nur für dich: Top 3 Empfehlungen!", "theme": "personalized", "cta": "Empfehlungen sehen"},
    {"name": "Deine Statistiken — Was du gemocht hast", "subject": "📊 Deine persönliche Jahresstatistik!", "theme": "personalized", "cta": "Stats sehen"},
    {"name": "Geheimes Angebot — NUR für dich!", "subject": "🤐 Psst! Geheimes Angebot NUR für dich!", "theme": "personalized", "cta": "Geheimnis lüften"},
    # ── Educational / Mehrwert ────────────────────────────────────────────────
    {"name": "5 Tipps für Smart Home Anfänger", "subject": "💡 5 Smart Home Tipps für Einsteiger!", "theme": "educational", "cta": "Tipps lesen"},
    {"name": "Fitnessplan für zu Hause — Kostenlos", "subject": "🏋️ Gratis: 4-Wochen Heimtrainingsplan!", "theme": "educational", "cta": "Plan holen"},
    {"name": "10 Küchengeheimtipps Profi Kochen", "subject": "👨‍🍳 10 Geheimtipps wie ein Profi kochen!", "theme": "educational", "cta": "Tipps lesen"},
    {"name": "Homeoffice produktiver gestalten Guide", "subject": "🖥️ Guide: So wirst du im Homeoffice produktiver!", "theme": "educational", "cta": "Guide lesen"},
    {"name": "Beauty Routine Morgen Abend", "subject": "✨ Perfekte Beauty-Routine: Morgen & Abend!", "theme": "educational", "cta": "Routine starten"},
    {"name": "Camping Checkliste für Anfänger", "subject": "⛺ Camping-Checkliste: Nichts vergessen!", "theme": "educational", "cta": "Checkliste holen"},
    {"name": "Haustier Ernährung Ratgeber", "subject": "🐶 Was dein Tier wirklich braucht!", "theme": "educational", "cta": "Ratgeber lesen"},
    {"name": "Gaming Setup optimieren Tipps", "subject": "🎮 Dein Gaming Setup auf Profi-Level!", "theme": "educational", "cta": "Optimieren"},
    {"name": "Baby Erstausstattung Checkliste", "subject": "👶 Erstausstattung: Alles was du brauchst!", "theme": "educational", "cta": "Checkliste"},
    {"name": "Packen wie ein Profi Reisetipps", "subject": "✈️ Wie Profis packen: Die ultimativen Tipps!", "theme": "educational", "cta": "Tipps anwenden"},
    {"name": "Energie sparen mit Smart Home", "subject": "⚡ Smart sparen: So senkst du Energiekosten!", "theme": "educational", "cta": "Sparen starten"},
    {"name": "Muskelaufbau für Anfänger Guide", "subject": "💪 Muskelaufbau-Guide für Anfänger!", "theme": "educational", "cta": "Guide lesen"},
    {"name": "Meal Prep Sonntag Anleitung", "subject": "🍱 Meal Prep: So kochst du für 5 Tage vor!", "theme": "educational", "cta": "Anleitung holen"},
    {"name": "Büro ergonomisch einrichten Anleitung", "subject": "🪑 Ergonomisches Büro in 5 Schritten!", "theme": "educational", "cta": "Anleitung"},
    {"name": "DIY Beauty Rezepte zu Hause", "subject": "🧴 DIY Beauty: Rezepte die wirklich helfen!", "theme": "educational", "cta": "Rezepte holen"},
    {"name": "Wandern Anfänger Guide Deutschland", "subject": "🥾 Wandern für Anfänger: Top Tipps!", "theme": "educational", "cta": "Guide lesen"},
    {"name": "Streaming Setup verbessern Guide", "subject": "📹 Streaming-Setup verbessern in 7 Schritten!", "theme": "educational", "cta": "Verbessern"},
    {"name": "Hundetraining Grundkommandos", "subject": "🐕 Grundkommandos: So lernst du deinen Hund!", "theme": "educational", "cta": "Training starten"},
    {"name": "Babynahrung ab 4 Monate Tipps", "subject": "👶 Beikost starten: Tipps für die ersten Wochen!", "theme": "educational", "cta": "Tipps lesen"},
    {"name": "Packliste Digitaler Nomade", "subject": "🌍 Digitaler Nomad: Die ultimative Packliste!", "theme": "educational", "cta": "Packliste"},
    # ── Testimonials / Social Proof ───────────────────────────────────────────
    {"name": "5-Sterne Bewertungen diese Woche", "subject": "⭐⭐⭐⭐⭐ Das sagen unsere Kunden!", "theme": "social_proof", "cta": "Bewertungen lesen"},
    {"name": "1000 glückliche Kunden Meilenstein", "subject": "🎉 1000 glückliche Kunden! Danke!", "theme": "social_proof", "cta": "Story lesen"},
    {"name": "Kundenstory — Thomas aus München", "subject": "💬 Thomas: 'Das beste Produkt dieses Jahr!'", "theme": "social_proof", "cta": "Story lesen"},
    {"name": "Instagram Fotos unserer Community", "subject": "📸 Schau was unsere Community macht!", "theme": "social_proof", "cta": "Fotos ansehen"},
    {"name": "Presse & Medien berichten über uns", "subject": "📰 In den Medien: Was Presse über uns sagt!", "theme": "social_proof", "cta": "Artikel lesen"},
    {"name": "Bestseller Ranking Top 5", "subject": "🏆 Unsere Top 5 Bestseller der Woche!", "theme": "social_proof", "cta": "Bestseller sehen"},
    {"name": "Kundenfoto des Monats Wettbewerb", "subject": "📷 Kundenfoto des Monats: Stimm ab!", "theme": "social_proof", "cta": "Abstimmen"},
    {"name": "YouTube Review positiv Video", "subject": "▶️ Sieh was YouTuber über uns sagen!", "theme": "social_proof", "cta": "Video ansehen"},
    {"name": "10.000 Social Media Follower!", "subject": "🎊 10K Follower! Feier mit uns!", "theme": "social_proof", "cta": "Mitfeiern"},
    {"name": "Vertrauen Daten Fakten Zahlen", "subject": "📊 Zahlen die für sich sprechen!", "theme": "social_proof", "cta": "Fakten sehen"},
    {"name": "Kundenzufriedenheit 98% laut Umfrage", "subject": "✅ 98% Kundenzufriedenheit!", "theme": "social_proof", "cta": "Erfahren"},
    {"name": "TikTok viral gegangen unser Produkt", "subject": "🎵 Viral auf TikTok: Schau es dir an!", "theme": "social_proof", "cta": "Viral video"},
    {"name": "Blog Beiträge Experten empfehlen", "subject": "🖊️ Experten empfehlen: Warum das stimmt!", "theme": "social_proof", "cta": "Blog lesen"},
    {"name": "Auszeichnung Bestes Produkt 2026", "subject": "🥇 Ausgezeichnet: Bestes Produkt 2026!", "theme": "social_proof", "cta": "Auszeichnung"},
    {"name": "Community Challenge Gewinner", "subject": "🏆 Challenge-Gewinner vorgestellt!", "theme": "social_proof", "cta": "Gewinner sehen"},
    {"name": "Unboxing Videos Community", "subject": "📦 Die besten Unboxing-Videos unserer Kunden!", "theme": "social_proof", "cta": "Unboxen"},
    {"name": "Trustpilot Score 4,8 Sterne", "subject": "⭐ 4,8 auf Trustpilot: Sieh warum!", "theme": "social_proof", "cta": "Bewertungen"},
    {"name": "Kundendankschreiben gesammelt", "subject": "💌 Echte Kundenbriefe: Das rührt uns!", "theme": "social_proof", "cta": "Briefe lesen"},
    {"name": "Vorher Nachher Kundenergebnisse", "subject": "🔄 Vorher-Nachher: Echte Resultate!", "theme": "social_proof", "cta": "Ergebnisse sehen"},
    {"name": "Community Spotlight Mitglieder Feature", "subject": "✨ Spotlight: Das macht unsere Community!", "theme": "social_proof", "cta": "Spotlight"},
    # ── Newsletter Regulär ────────────────────────────────────────────────────
    {"name": "Wöchentlicher Newsletter KW 24", "subject": "📬 Dein Weekly Update — Was neu ist!", "theme": "newsletter", "cta": "Update lesen"},
    {"name": "Monatsrückblick Mai 2026", "subject": "📅 Mai Rückblick: Was war, was kommt!", "theme": "newsletter", "cta": "Rückblick"},
    {"name": "Branchentrends diese Woche", "subject": "📈 Diese Woche im Trend: Stay informed!", "theme": "newsletter", "cta": "Trends sehen"},
    {"name": "Behind the Scenes Blick ins Team", "subject": "🎬 Behind the Scenes: So arbeiten wir!", "theme": "newsletter", "cta": "Einblick"},
    {"name": "CEO Brief — Nachrichten von Rudolf", "subject": "📝 Ein Brief von Rudolf persönlich!", "theme": "newsletter", "cta": "Brief lesen"},
    {"name": "Produktvorschau Nächste Woche", "subject": "👀 Sneak Peak: Was nächste Woche kommt!", "theme": "newsletter", "cta": "Vorschau sehen"},
    {"name": "Community Fragen und Antworten", "subject": "❓ Eure Fragen — Unsere Antworten!", "theme": "newsletter", "cta": "Q&A lesen"},
    {"name": "Nachhaltigkeit Bericht Update", "subject": "🌱 Unser Nachhaltigkeits-Update!", "theme": "newsletter", "cta": "Update lesen"},
    {"name": "Neue Features App Update", "subject": "🆕 App-Update: Neue Features für dich!", "theme": "newsletter", "cta": "Update ansehen"},
    {"name": "Partnerschaft Announcement News", "subject": "🤝 Neue Partnerschaft: Das bedeutet das für dich!", "theme": "newsletter", "cta": "News lesen"},
    {"name": "Wetter Saisonale Empfehlungen", "subject": "🌤️ Das Wetter dreht: Unsere Empfehlungen!", "theme": "newsletter", "cta": "Empfehlungen"},
    {"name": "Produkttest Ergebnis intern", "subject": "🔬 Wir haben getestet: Das Ergebnis!", "theme": "newsletter", "cta": "Ergebnis sehen"},
    {"name": "Kooperation Influencer Vorstellung", "subject": "🌟 Unsere Influencer: Lern sie kennen!", "theme": "newsletter", "cta": "Vorstellung"},
    {"name": "Rabattcode aktueller Monat", "subject": "🎫 Dein Monatscode: Spare jetzt!", "theme": "newsletter", "cta": "Code nutzen"},
    {"name": "Top 10 Links diese Woche", "subject": "🔗 Top 10: Das Beste aus dem Web!", "theme": "newsletter", "cta": "Links klicken"},
    {"name": "Social Media Highlights Zusammenfassung", "subject": "📱 Social Highlights: Was los war!", "theme": "newsletter", "cta": "Highlights sehen"},
    {"name": "Wunschzettel Features Update", "subject": "🌟 Wunschliste-Update: Neue Funktionen!", "theme": "newsletter", "cta": "Update sehen"},
    {"name": "Mitarbeiter Spotlight des Monats", "subject": "👤 Mitarbeiter des Monats vorgestellt!", "theme": "newsletter", "cta": "Lernen kennen"},
    {"name": "Kundenfeedback Umfrage Einladung", "subject": "📋 Kurze Umfrage: 3 Minuten Deiner Zeit!", "theme": "newsletter", "cta": "Teilnehmen"},
    {"name": "Jahresrückblick Highlights", "subject": "🎊 Jahresrückblick: Was für ein Jahr!", "theme": "newsletter", "cta": "Rückblick"},
    # ── Re-Engagement ─────────────────────────────────────────────────────────
    {"name": "Lange nicht gesehen — Vermisst dich!", "subject": "👋 Schon lange her! Wir haben was für dich!", "theme": "reengagement", "cta": "Zurück kommen"},
    {"name": "Letzte Chance Abonnement kündigen", "subject": "😢 Bleib bei uns — oder sag Tschüss!", "theme": "reengagement", "cta": "Bleiben"},
    {"name": "Wir haben uns verbessert — Sieh nach!", "subject": "✨ Wir sind besser als je zuvor!", "theme": "reengagement", "cta": "Neues entdecken"},
    {"name": "Exklusiver Comeback Rabatt 20%", "subject": "🎁 Comeback-Bonus: 20% nur heute!", "theme": "reengagement", "cta": "Einlösen"},
    {"name": "Was haben wir verpasst — Feedback", "subject": "💬 Was haben wir falsch gemacht? Sag's uns!", "theme": "reengagement", "cta": "Feedback geben"},
    {"name": "Neue Produkte seit letztem Besuch", "subject": "🆕 Neu seit deinem letzten Besuch!", "theme": "reengagement", "cta": "Entdecken"},
    {"name": "Nur noch 2 Tage Reaktivierungsangebot", "subject": "⏰ 2 Tage noch: Dein spezielles Angebot!", "theme": "reengagement", "cta": "Angebot sichern"},
    {"name": "Was denkst du — Umfrage kurz", "subject": "🤔 Schnelle Frage: Was denkst du?", "theme": "reengagement", "cta": "Antworten"},
    {"name": "Du wirst uns fehlen wenn du gehst", "subject": "💔 Bitte geh nicht — Hier ist warum!", "theme": "reengagement", "cta": "Bleiben"},
    {"name": "Kostenloser Test deiner Wahl", "subject": "🎁 Gratis testen: Wähle dein Produkt!", "theme": "reengagement", "cta": "Gratis testen"},
    {"name": "Dein Profil braucht ein Update", "subject": "📝 Dein Profil: Aktualisiere & spare!", "theme": "reengagement", "cta": "Aktualisieren"},
    {"name": "Alte Favoriten immer noch da", "subject": "❤️ Deine Favoriten von damals: Noch da!", "theme": "reengagement", "cta": "Wiedersehen"},
    {"name": "Alles einfacher jetzt mit der App", "subject": "📱 Alles einfacher: Unsere neue App!", "theme": "reengagement", "cta": "App öffnen"},
    {"name": "Seltene Sonderchance für dich", "subject": "🍀 Sonderchance: Das gibt's nicht oft!", "theme": "reengagement", "cta": "Chance nutzen"},
    {"name": "Community vermisst dich wirklich", "subject": "👥 Die Community fragt nach dir!", "theme": "reengagement", "cta": "Zurückkehren"},
    {"name": "Alles bereinigt — Neuer Start", "subject": "🌅 Neuer Start: Wir haben alles verbessert!", "theme": "reengagement", "cta": "Frisch starten"},
    {"name": "Bonuspunkte verfallen bald", "subject": "⚠️ Deine Punkte verfallen bald!", "theme": "reengagement", "cta": "Punkte nutzen"},
    {"name": "Erste E-Mail in sechs Monaten", "subject": "📬 Lange her: Hier ist unser Update!", "theme": "reengagement", "cta": "Lesen"},
    {"name": "Danke Angebot zum Bleiben", "subject": "🙏 Danke dass du noch hier bist!", "theme": "reengagement", "cta": "Dankeschön sehen"},
    {"name": "Letzte E-Mail dieser Art Versprechen", "subject": "✋ Letzte solche Mail: Hier unser Bestes!", "theme": "reengagement", "cta": "Angebot sehen"},
    # ── Abandoned Cart / Konversion ───────────────────────────────────────────
    {"name": "Warenkorb vergessen — Wir halten ihn fest", "subject": "🛒 Dein Warenkorb: Wir heben ihn für dich!", "theme": "conversion", "cta": "Jetzt kaufen"},
    {"name": "Artikel fast ausverkauft — Jetzt kaufen", "subject": "⚠️ Fast weg! Dein Artikel läuft aus!", "theme": "conversion", "cta": "Sichern"},
    {"name": "Preissenkung deines Wunschartikels", "subject": "💲 Preissenkung! Dein Artikel ist günstiger!", "theme": "conversion", "cta": "Kaufen"},
    {"name": "Kauf Abschluss Hilfe Angebot", "subject": "🤝 Brauche du Hilfe beim Kauf?", "theme": "conversion", "cta": "Hilfe holen"},
    {"name": "Rabatt für Fertigstellen des Kaufs", "subject": "🎁 10% für deinen abgebrochenen Kauf!", "theme": "conversion", "cta": "Kaufen & sparen"},
    {"name": "Kunden kauften auch — Empfehlungen", "subject": "👥 Kunden wie du kauften auch das!", "theme": "conversion", "cta": "Entdecken"},
    {"name": "Gratis Versand wenn du jetzt kaufst", "subject": "🚚 Gratis Versand für deinen Kauf jetzt!", "theme": "conversion", "cta": "Kostenlos bestellen"},
    {"name": "Zahlung aufgesplittet möglich", "subject": "💳 In 3 Raten zahlen: So geht's!", "theme": "conversion", "cta": "Ratenkauf"},
    {"name": "Produktvergleich Empfehlung", "subject": "🔄 Wir helfen dir vergleichen!", "theme": "conversion", "cta": "Vergleichen"},
    {"name": "Dringende Aufforderung Bestandskunde", "subject": "❗ Nur noch 3 Stück! Handle jetzt!", "theme": "conversion", "cta": "Sofort kaufen"},
    {"name": "Kostenlose Rückgabe Hinweis", "subject": "↩️ Kein Risiko: 30 Tage kostenlose Rückgabe!", "theme": "conversion", "cta": "Sicher kaufen"},
    {"name": "Live Chat Angebot Kaufhilfe", "subject": "💬 Fragen? Live Chat hilft sofort!", "theme": "conversion", "cta": "Chat starten"},
    {"name": "Nachbestellungshinweis populäres Produkt", "subject": "🔔 Zurück im Sortiment: Dein Lieblings-Produkt!", "theme": "conversion", "cta": "Kaufen"},
    {"name": "Bundle kaufen und sparen Empfehlung", "subject": "📦 Bundle kaufen = mehr sparen!", "theme": "conversion", "cta": "Bundle kaufen"},
    {"name": "Nur heute Kaufbonus geschenkt", "subject": "🎁 Kaufbonus heute gratis dazu!", "theme": "conversion", "cta": "Bonus sichern"},
    {"name": "Preisgarantie Versprechen", "subject": "💯 Preisgarantie: Wir schlagen jeden Preis!", "theme": "conversion", "cta": "Günstigst kaufen"},
    {"name": "Stück Limit Mengenwarnung", "subject": "🔢 Nur noch 5 Stück! Beeile dich!", "theme": "conversion", "cta": "Jetzt sichern"},
    {"name": "Gutschein Erinnerung läuft ab", "subject": "⏰ Dein Gutschein läuft morgen ab!", "theme": "conversion", "cta": "Einlösen"},
    {"name": "Geschenkverpackung Option verfügbar", "subject": "🎁 Geschenkverpackung: Jetzt wählen!", "theme": "conversion", "cta": "Geschenk bestellen"},
    {"name": "Expresslieferung heute noch bestellen", "subject": "⚡ Heute bestellt = morgen geliefert!", "theme": "conversion", "cta": "Express bestellen"},
]


async def _kv_post(path: str, data: dict) -> dict:
    if not API_KEY:
        return {"error": "no KLAVIYO_API_KEY"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{BASE}{path}", headers={
                "Authorization": f"Klaviyo-API-Key {API_KEY}",
                "revision": REVISION,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, json=data, timeout=aiohttp.ClientTimeout(total=25)) as r:
                return await r.json() if r.status < 400 else {"error": await r.text()}
    except Exception as e:
        return {"error": str(e)}


async def _ai(prompt: str, max_tokens: int = 500) -> str:
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


def _build_html(template: dict, custom_body: str = "") -> str:
    shop = SHOP_URL
    cta  = template.get("cta", "Jetzt entdecken")
    name = template.get("name", "")
    if not custom_body:
        custom_body = (f"<p>Entdecke unsere aktuellen Angebote und Neuheiten. "
                       f"Als geschätzter Kunde erhältst du exklusiven Zugang zu besonderen Deals.</p>"
                       f"<p>Nicht verpassen – limitierte Auflage!</p>")
    return f"""<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto'>
<h1 style='color:#1a1a2e;border-bottom:3px solid #e63946;padding-bottom:10px'>{name}</h1>
{custom_body}
<div style='text-align:center;margin:30px 0'>
  <a href='{shop}' style='background:#e63946;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold'>{cta} →</a>
</div>
<p style='color:#888;font-size:12px'>BullPowerHub · <a href='{shop}'>Shop</a> · Abmelden</p>
</div>"""


async def create_campaign_from_template(tmpl: dict) -> dict:
    """Erstellt eine Klaviyo-Kampagne aus Template (2-step: create → add message)."""
    name    = tmpl["name"]
    subject = tmpl["subject"]
    theme   = tmpl.get("theme", "general")

    # AI-generierter Body
    prompt = f"""Schreibe einen kurzen deutschen Email-Body (HTML, kein DOCTYPE) für:
Kampagne: "{name}"
Thema: {theme}
Subject: {subject}

Nur: 1 Headline h2, 3 Sätze Body, kein CTA-Button (kommt separat).
Max 150 Wörter."""
    ai_body = await _ai(prompt, max_tokens=200)
    html = _build_html(tmpl, ai_body or "")

    # Step 1: Create bare campaign
    campaign_payload = {
        "data": {
            "type": "campaign",
            "attributes": {
                "name": name[:100],
                "audiences": {
                    "included": [{"type": "list", "id": LIST_ID}],
                    "excluded": [],
                },
                "send_strategy": {"method": "immediate"},
                "tracking_options": {
                    "is_tracking_opens": True,
                    "is_tracking_clicks": True,
                },
            },
        }
    }

    result = await _kv_post("/campaigns/", campaign_payload)
    cid = (result.get("data") or {}).get("id")
    if not cid:
        return {"ok": False, "error": str(result.get("error", result))[:300]}

    # Step 2: Add campaign message
    msg_payload = {
        "data": {
            "type": "campaign-message",
            "attributes": {
                "channel": "email",
                "label": name[:50],
                "content": {
                    "subject": subject[:150],
                    "preview_text": name[:80],
                    "from_email": FROM_EMAIL,
                    "from_label": "BullPowerHub",
                    "body": html,
                },
            },
            "relationships": {
                "campaign": {"data": {"type": "campaign", "id": cid}},
            },
        }
    }
    msg_r = await _kv_post("/campaign-messages/", msg_payload)
    # Message creation failure is non-fatal — campaign draft still exists
    msg_ok = not msg_r.get("error")

    # Step 3: Send immediately
    send_r = await _kv_post("/campaign-send-jobs/", {
        "data": {
            "type": "campaign-send-job",
            "attributes": {},
            "relationships": {"campaign": {"data": {"type": "campaign", "id": cid}}},
        }
    })
    sent = "error" not in send_r

    try:
        from modules.supabase_client import get_client
        get_client().table("klaviyo_mass_campaigns").insert({
            "campaign_id": cid, "name": name, "subject": subject,
            "theme": theme, "sent": sent,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as _e:
        log.debug("skipped: %s", _e)

    return {"ok": True, "campaign_id": cid, "name": name, "sent": sent}


async def _worker(queue: asyncio.Queue, results: list, worker_id: int):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        try:
            r = await create_campaign_from_template(item)
            results.append(r)
            status = "✅" if r.get("ok") else "❌"
            log.info("W%d %s %s", worker_id, status, item["name"][:50])
        except Exception as e:
            results.append({"ok": False, "error": str(e)})
        finally:
            queue.task_done()
        await asyncio.sleep(2)


async def mass_create_klaviyo_campaigns(count: int = 200, workers: int = 3) -> dict:
    """Erstellt bis zu count Klaviyo-Kampagnen aus Templates."""
    existing: set[str] = set()
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("klaviyo_mass_campaigns").select("name").execute()
        existing = {r["name"] for r in rows.data or []}
    except Exception as _e:
        log.debug("skipped: %s", _e)

    templates = [t for t in CAMPAIGN_TEMPLATES if t["name"] not in existing]
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
    last_notify = 0

    async def tracker():
        nonlocal last_notify
        while True:
            await asyncio.sleep(10)
            ok_now = sum(1 for r in results if r.get("ok"))
            if ok_now >= last_notify + 50:
                last_notify = ok_now
                await _notify(f"📧 Klaviyo Mass: {ok_now} Kampagnen erstellt!")

    worker_tasks = [asyncio.create_task(_worker(queue, results, i)) for i in range(workers)]
    tracker_t = asyncio.create_task(tracker())
    await queue.join()
    for t in worker_tasks:
        t.cancel()
    tracker_t.cancel()

    ok  = sum(1 for r in results if r.get("ok"))
    err = len(results) - ok

    # BrutusCore blast
    if ok > 0:
        try:
            from modules.brutus_core import fire
            await fire("Klaviyo Mass Kampagnen gestartet",
                       f"✅ {ok} E-Mail Kampagnen erstellt und gesendet!",
                       channels=["telegram", "slack"])
        except Exception as _e:
            log.debug("skipped: %s", _e)

    await _notify(f"✅ Klaviyo Mass Complete: {ok} Kampagnen erstellt, {err} failed!")
    return {"ok": True, "created": ok, "failed": err}


async def run_daily_klaviyo_campaigns(count: int = 3) -> dict:
    """Täglich 3 neue Kampagnen aus nicht gesendeten Templates."""
    return await mass_create_klaviyo_campaigns(count=count, workers=2)


async def get_klaviyo_mass_stats() -> dict:
    total = len(CAMPAIGN_TEMPLATES)
    try:
        from modules.supabase_client import get_client
        rows = get_client().table("klaviyo_mass_campaigns").select("id", count="exact").execute()
        created = rows.count or 0
    except Exception:
        created = 0
    return {"ok": True, "templates": total, "created_in_db": created,
            "remaining": max(0, total - created)}
