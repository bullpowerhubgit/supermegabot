#!/usr/bin/env python3
"""
High-Ticket Upgrade v2 — Stats-Counter + Bonus-Stack + FAQ + Garantie-Badge
Ergänzt alle 20 Sites mit 4 neuen Sektionen.
"""
import re, subprocess, sys
from pathlib import Path

BASE = Path(__file__).parent.parent / "netlify-deploy"

NETLIFY_SITE_IDS = {
    "aiitec-pinterest-portal": "78eae41d-6e24-4648-9ebe-9b30ed95dd84",
    "bullpower-icomeauto":     "713b6e9f-4388-4c5a-a339-29ba8b5cfb2b",
    "bullpower-steuercockpit": "3a80f111-7a16-48c4-bb9c-ad4b7fbf907f",
    "bullpower-lead":          "2c73aa5c-26b3-409f-b0d2-3e62ad441c12",
    "bullpower-launcher":      "5ea6c29b-c012-47c0-96d1-e1fcd9e813fa",
    "bullpower-hub-portal":    "b724d9cd-e19e-4d15-9747-059e8148368f",
    "creatorai-ultra":         "0d38840f-35ef-4ac3-8e39-a0edde921562",
    "telegram-marketing-bot":  "5fdbef63-e63e-4f57-ab27-770328ac9461",
    "gumroad-discord-bot":     "b5bcb0f0-cd2f-463e-9c7d-bd87afca4ad1",
    "autoincome-ai":           "4d792fed-3c4c-4fd7-8737-46d027365e5e",
    "icomeauto-bots":          "d43a1ef5-bce6-4792-95a6-03711233c02e",
    "creatorstudio-pro":       "251bd945-2fc2-40b2-bff5-35d49a5a6c3f",
    "digistore24-automation-suite": "0d99546c-1813-4820-af6e-8c108968f17b",
    "cognitive-symphony-ds24": "478872de-d571-4e81-b3fe-4d9b12dd697a",
    "shopify-brutal-tuning":   "2dba2775-a068-4e4c-9d9f-2a37d48f5761",
    "shopify-automaton-suite": "1859ba2f-66de-4012-b912-52b46e847810",
    "shopify-acquisition-engine": "cc660686-8075-4f3c-bc8e-07ac7d2eca05",
    "bullpower-ai-tools":      "2f993068-69c5-4948-902c-6886a18fea02",
    "autosuiterudibot":        "3fcc5f28-e82f-4066-b09b-76bac56faefd",
    "bespoke-haupia-d154bc":   "bdb0eb68-f54c-440c-bf5b-0736d736e62b",
}

# ─── PER-PROJECT DATA ───────────────────────────────────────────
PROJECTS = {
    "autoincome-ai": {
        "name": "AutoIncome AI", "netlify": "autoincome-ai", "vercel": "autoincome-ai",
        "stats": [
            ("€24.800", "Passiveinkommen/Mo", "24800"),
            ("5", "Revenue-Streams", "5"),
            ("40h", "Zeitersparnis/Woche", "40"),
            ("98%", "Autopilot-Quote", "98"),
        ],
        "bonuses": [
            ("KI-Starter-Paket", "Prompt-Bibliothek + 47 KI-Workflows", "€297"),
            ("1:1 Onboarding-Call", "60-Min Strategy Session mit Experten", "€497"),
            ("VIP Telegram Channel", "Exklusive Alerts, Deals & Community", "€197"),
            ("Monatliche Revenue Reports", "KI-Analyse deiner Income-Streams", "€500/J"),
        ],
        "faqs": [
            ("Wie schnell sehe ich erste Ergebnisse?", "Die meisten Kunden sehen erste automatisierte Einnahmen innerhalb von 7–14 Tagen. Unser Onboarding-Prozess ist darauf ausgelegt, dich in 48h startklar zu machen."),
            ("Brauche ich technisches Vorwissen?", "Nein. AutoIncome AI ist komplett No-Code. Du richtest einmal ein, wir übernehmen den Rest — vollautomatisch."),
            ("Welche Plattformen werden unterstützt?", "Digistore24, Gumroad, Shopify, Amazon Associates, ClickBank, eigene digitale Produkte und mehr. Alle 5 Revenue-Streams laufen parallel."),
            ("Was passiert wenn etwas nicht funktioniert?", "Unser 24/7-Monitoring erkennt Probleme sofort. Du bekommst einen Telegram-Alert + automatischen Fix-Vorschlag in unter 30 Minuten."),
            ("Gibt es eine Mindestlaufzeit?", "Nein. Einmalzahlung = lebenslanger Zugang. Keine monatlichen Kosten, keine Kündigung nötig."),
            ("Ist mein Geld sicher?", "Ja. Wir bieten 30 Tage Geld-zurück-Garantie ohne Wenn und Aber. Nicht zufrieden → volles Geld zurück."),
        ],
    },
    "bullpower-hub": {
        "name": "BullPower Hub", "netlify": "bullpower-hub-portal", "vercel": "bullpower-hub",
        "stats": [
            ("€18.400", "MRR generiert", "18400"),
            ("14", "Qualif. Leads/Tag", "14"),
            ("22%", "Response-Rate", "22"),
            ("6", "Meetings/Woche", "6"),
        ],
        "bonuses": [
            ("B2B Lead Datenbank", "2.400 verifizierte DACH-Entscheider-Kontakte", "€997"),
            ("Sales Script Bibliothek", "47 erprobte Outreach-Skripte auf Deutsch", "€297"),
            ("Competitor Intelligence Report", "Top 10 Mitbewerber vollständig analysiert", "€497"),
            ("1:1 Growth Call", "90-Min B2B-Wachstumsstrategie mit Experten", "€697"),
        ],
        "faqs": [
            ("Für welche Unternehmen ist BullPower Hub geeignet?", "B2B SaaS, Agenturen, Berater und Dienstleister mit Zielkunden in DACH. Ab €50k Jahresumsatz skaliert das System besonders stark."),
            ("Wie funktioniert die Lead-Generierung?", "KI analysiert LinkedIn, Xing und Branchenverzeichnisse — findet Entscheider — schreibt personalisierte Outreach-Nachrichten — sendet und trackt automatisch."),
            ("Wie lange dauert das Setup?", "48 Stunden. Unser Team übernimmt den kompletten Onboarding-Prozess inklusive Konfiguration deiner Zielgruppe und Messaging."),
            ("Was ist die durchschnittliche Response-Rate?", "Unsere Kunden erzielen 18–28% Response-Rate (Branche: 3–5%). Das liegt an der KI-personalisierten Ansprache."),
            ("Kann ich das System für mehrere Produkte nutzen?", "Ja. Du kannst unbegrenzt viele Kampagnen gleichzeitig laufen lassen — für verschiedene Produkte, Märkte oder Zielgruppen."),
            ("Gibt es eine Garantie?", "30 Tage Geld-zurück. Wenn du nach 30 Tagen weniger als 50 qualifizierte Leads hast, bekommst du das volle Geld zurück — ohne Diskussion."),
        ],
    },
    "shopify-acquisition-engine": {
        "name": "Shopify Acquisition Engine", "netlify": "shopify-acquisition-engine", "vercel": "shopify-acquisition-engine",
        "stats": [
            ("€4.821", "Umsatz/Tag", "4821"),
            ("4.7%", "Conversion-Rate", "47"),
            ("847", "Produkte synced", "847"),
            ("+23%", "Umsatz vs. Vormonat", "23"),
        ],
        "bonuses": [
            ("Shopify Speed Optimizer", "LCP unter 1s — PageSpeed 100/100 garantiert", "€397"),
            ("Smart Product Finder", "KI findet Top-Seller bevor sie viral gehen", "€597"),
            ("E-Mail Abandon-Sequenz", "7-teilige Sequenz, 31% Recovery-Rate", "€297"),
            ("Meta Ads Blueprint", "Bewährte Kampagnenstruktur für €1k+ ROAS", "€497"),
        ],
        "faqs": [
            ("Funktioniert das mit jedem Shopify-Shop?", "Ja. Shopify Basic bis Plus — alle Pläne. Setup in unter 2 Stunden über unsere App-Integration."),
            ("Wie viele Produkte kann ich synchronisieren?", "Unbegrenzt. Kunden mit 10.000+ Produkten laufen problemlos. Sync-Intervall: alle 30 Minuten."),
            ("Werden meine Produkttexte automatisch optimiert?", "Ja. Claude AI schreibt SEO-optimierte Titel, Descriptions und Alt-Texte — auf Basis deiner Bestseller und aktueller Suchtrends."),
            ("Kann ich Preise automatisch anpassen?", "Ja. Die Dynamic Pricing Engine monitort Mitbewerber und passt Preise in Echtzeit an — mit deinen definierten Unter- und Obergrenzen."),
            ("Was wenn mein Lieferant ausfällt?", "Automatischer Fallback auf Backup-Lieferant. Du bekommst einen Telegram-Alert innerhalb von 5 Minuten bei jedem Problem."),
            ("Gibt es eine 30-Tage-Garantie?", "Ja. Wenn dein Umsatz in 30 Tagen nicht um mindestens 15% gestiegen ist, bekommst du das volle Geld zurück."),
        ],
    },
    "shopify-brutal-tuning": {
        "name": "Shopify Brutal Tuning", "netlify": "shopify-brutal-tuning", "vercel": "shopify-brutal-tuning",
        "stats": [
            ("5.4%", "Conversion-Rate", "54"),
            ("6.8x", "ROAS nach Tuning", "68"),
            ("-68%", "Absprungrate", "68"),
            ("100", "PageSpeed Score", "100"),
        ],
        "bonuses": [
            ("Speed Audit Report", "Vollständige technische Analyse deines Shops", "€297"),
            ("CRO Checkliste Pro", "127 Conversion-Killer — Schritt für Schritt", "€197"),
            ("A/B Test Template Pack", "34 bewährte Test-Varianten sofort einsatzbereit", "€397"),
            ("Heatmap & Session-Recording", "30 Tage kostenlos — sieh was Kunden wirklich tun", "€247"),
        ],
        "faqs": [
            ("Was genau wird beim Brutal Tuning optimiert?", "Speed (Core Web Vitals), Conversion (UX/UI, CTAs, Trust), SEO (Struktur, Meta, Schema) und Ads (ROAS, Targeting, Creative)."),
            ("Wie lange dauert das Tuning?", "5 Werktage für das komplette Basis-Tuning. A/B Tests laufen danach kontinuierlich weiter — vollautomatisch."),
            ("Brauche ich einen Entwickler?", "Nein. Wir implementieren alles direkt in deinen Shopify-Shop. Du brauchst keinen Code anzufassen."),
            ("Was ist ein realistisches Ergebnis?", "Im Durchschnitt: Conversion +2.1 Prozentpunkte, PageSpeed 40+ Punkte höher, ROAS 2.3x besser — innerhalb von 30 Tagen."),
            ("Funktioniert das auch mit Custom Themes?", "Ja. Wir arbeiten mit allen Shopify-Themes — Dawn, Prestige, Impulse, Custom Code. Kein Template ist ein Problem."),
            ("30-Tage-Garantie?", "Ja. Wenn deine Conversion-Rate nach 30 Tagen nicht gestiegen ist, volle Rückerstattung — ohne Bedingungen."),
        ],
    },
    "shopify-suite": {
        "name": "Shopify Automation Suite", "netlify": "shopify-automaton-suite", "vercel": "shopify-suite",
        "stats": [
            ("€89.400", "Autopilot-Umsatz/Mo", "89400"),
            ("47", "Orders/Tag automat.", "47"),
            ("9", "Shops parallel", "9"),
            ("31%", "Abandon-Recovery", "31"),
        ],
        "bonuses": [
            ("Multi-Shop Dashboard", "Alle deine Shops in einem Command Center", "€597"),
            ("Lieferanten-Datenbank", "340 geprüfte DACH-Lieferanten mit Direktkontakt", "€497"),
            ("Inventar-Forecast KI", "Nachbestellungen 14 Tage im Voraus vorhersagen", "€397"),
            ("VIP Mastermind Zugang", "Monatlicher Call mit Top-Shopify-Unternehmern", "€297/Mo"),
        ],
        "faqs": [
            ("Kann ich mehrere Shops gleichzeitig verwalten?", "Ja. Die Suite ist für Multi-Shop-Management gebaut. Kunden verwalten bis zu 23 Shops mit 2 Personen."),
            ("Wie funktioniert die automatische Nachbestellung?", "KI analysiert Verkaufsgeschwindigkeit, Lagerstand und Lieferzeiten — und löst Bestellungen automatisch aus, bevor der Bestand kritisch wird."),
            ("Werden meine bestehenden Workflows überschrieben?", "Nein. Wir integrieren uns in bestehende Prozesse. Migration ohne Downtime, Schritt für Schritt."),
            ("Was kostet der Betrieb monatlich?", "Null. Einmalige Lizenzgebühr, keine monatlichen Kosten, keine Transaktionsgebühren. Dein Umsatz gehört dir."),
            ("Wie ist der Support?", "Priority-Support mit 12h Antwortzeit. Enterprise-Plan: dedizierter Account Manager + 4h SLA."),
            ("Gibt es eine Geld-zurück-Garantie?", "30 Tage — kein Kleingedrucktes. Wenn du nicht 100% zufrieden bist, volles Geld zurück."),
        ],
    },
    "cognitive-symphony": {
        "name": "Cognitive Symphony", "netlify": "cognitive-symphony-ds24", "vercel": "cognitive-symphony",
        "stats": [
            ("47", "KI-Agenten parallel", "47"),
            ("3.2x", "Output vs. Team", "32"),
            ("€47k", "Content-Wert/Mo", "47000"),
            ("0.3%", "CPU für KI-Overhead", "3"),
        ],
        "bonuses": [
            ("KI-Agenten Starter-Pack", "12 vorkonfigurierte Agenten sofort einsatzbereit", "€597"),
            ("Prompt Engineering Kurs", "Advanced Prompting für Business-Automation", "€397"),
            ("Knowledge-Graph Setup", "Dein Business-Wissen als KI-Wissensbasis", "€797"),
            ("API-Integration Paket", "Verbinde deine Tools mit der KI-Engine", "€497"),
        ],
        "faqs": [
            ("Was ist der Unterschied zu ChatGPT?", "ChatGPT ist ein Werkzeug. Cognitive Symphony ist ein autonomes System: 47 KI-Agenten arbeiten parallel, lernen aus deinem Business und optimieren sich selbst."),
            ("Welche KI-Modelle werden genutzt?", "Claude (Anthropic), GPT-4, Gemini und spezialisierte Fine-Tuned-Modelle — je nach Aufgabe automatisch ausgewählt."),
            ("Kann die KI meine Branche lernen?", "Ja. Durch dein Knowledge-Base-Onboarding kennt die KI deine Produkte, Kunden, Sprache und Ziele in 48h."),
            ("Wie sicher sind meine Daten?", "EU-Rechenzentren, DSGVO-konform, Ende-zu-Ende-Verschlüsselung. Deine Daten werden nicht für KI-Training verwendet."),
            ("Was wenn die KI Fehler macht?", "Jeder KI-Output hat ein Human-in-the-Loop Gate. Kritische Aktionen (Posting, Versand) warten auf deine Freigabe per Telegram."),
            ("Gibt es eine Testphase?", "30 Tage Geld-zurück. Wenn die KI-Suite nicht mindestens 10h/Woche für dich einspart, volles Geld zurück."),
        ],
    },
    "creatorai-ultra": {
        "name": "CreatorAI Ultra", "netlify": "creatorai-ultra", "vercel": "creatorai-ultra",
        "stats": [
            ("23", "Content-Pieces/Tag", "23"),
            ("340k", "Abonnenten aufgebaut", "340000"),
            ("8min", "Video-Produktionszeit", "8"),
            ("10x", "Content-Output", "10"),
        ],
        "bonuses": [
            ("Viral Content Bibliothek", "500 bewährte Hook-Formeln für alle Plattformen", "€297"),
            ("YouTube SEO Masterclass", "Wie Videos auf Seite 1 ranken — garantiert", "€497"),
            ("KI Thumbnail Generator", "A/B-getestete Thumbnails die 3x mehr Klicks bringen", "€397"),
            ("Creator Business Blueprint", "Von 0 auf €10k MRR als Content Creator", "€797"),
        ],
        "faqs": [
            ("Welche Plattformen werden unterstützt?", "YouTube, Instagram, TikTok, LinkedIn, Pinterest, Twitter/X, Podcast-Plattformen — alle gleichzeitig aus einem Dashboard."),
            ("Wie gut ist der KI-Content wirklich?", "Senior-Level-Qualität. Das System wird auf deinem besten Content trainiert und übertrifft danach deinen Durchschnitt — nicht dein Minimum."),
            ("Kann ich die KI-Texte einfach so verwenden?", "Ja. CreatorAI schreibt in deiner Stimme und deinem Stil. Die meisten Kunden veröffentlichen 80–95% des KI-Outputs ohne Änderungen."),
            ("Wie lange bis zu ersten viralen Inhalten?", "Durchschnittlich 3–4 Wochen. Das System analysiert Trends in Echtzeit und optimiert automatisch auf Reichweite."),
            ("Was wenn ich in einer Nische bin?", "Perfekt. Nischen-Creator profitieren am meisten — weniger Konkurrenz, höhere Engagement-Rates, treue Community."),
            ("30 Tage Garantie?", "Ja. Wenn du in 30 Tagen nicht mehr Content produzierst als vorher, volles Geld zurück — kein Aufwand, keine Fragen."),
        ],
    },
    "creatorstudio-pro": {
        "name": "CreatorStudio Pro", "netlify": "creatorstudio-pro", "vercel": "creatorstudio-pro",
        "stats": [
            ("€18.400", "Kurs-Revenue/Mo", "18400"),
            ("2.847", "Kursteilnehmer Q1", "2847"),
            ("48h", "Kurs-Launch-Zeit", "48"),
            ("80%", "Waitlist-Conversion", "80"),
        ],
        "bonuses": [
            ("Kurs-Launch Playbook", "7-Schritte-System das €97k Launch generiert", "€697"),
            ("Sales Page Template Pack", "5 bewährte Templates mit 80%+ Conversion", "€397"),
            ("Community-Aufbau Blueprint", "Von 0 auf 1.000 zahlende Members in 90 Tagen", "€497"),
            ("Affiliate-Recruiting System", "47 Partner in 2 Wochen automatisch rekrutieren", "€297"),
        ],
        "faqs": [
            ("Muss ich schon einen Kurs haben?", "Nein. CreatorStudio Pro hilft dir von der Idee bis zum Live-Kurs in 48 Stunden — inklusive Kurs-Outline, Skripte und Sales Page."),
            ("Welche Plattformen werden unterstützt?", "Digistore24, Elopage, Teachable, Thinkific, Podia, Kajabi — alle gängigen Kursplattformen sind integriert."),
            ("Wie viele Kurse kann ich erstellen?", "Unbegrenzt. Enterprise-Kunden betreiben 12+ Kurse gleichzeitig mit automatischer Kreuz-Promotion."),
            ("Kann die KI meinen Unterrichtsstil übernehmen?", "Ja. Das System analysiert deine bisherigen Inhalte und schreibt neue Materialien in genau deinem Stil und deiner Sprache."),
            ("Was ist mit dem Affiliate-Programm?", "Vollautomatisches Affiliate-Management: Recruitment, Onboarding, Tracking, Auszahlung — alles ohne manuelle Eingriffe."),
            ("Gibt es eine Garantie?", "30 Tage. Wenn dein erster Kurs nicht live ist oder du nicht zufrieden bist, volles Geld zurück."),
        ],
    },
    "digistore24-suite": {
        "name": "Digistore24 Suite", "netlify": "digistore24-automation-suite", "vercel": "digistore24-suite",
        "stats": [
            ("€22.480", "DS24-Revenue/Mo", "22480"),
            ("234", "Affiliates rekrutiert", "234"),
            ("34%", "Upsell-Rate", "34"),
            ("8.2x", "ROAS auf Affiliates", "82"),
        ],
        "bonuses": [
            ("DS24 Bestseller Analyse", "Top 100 profitable Produkte zum Promoten", "€497"),
            ("Affiliate Outreach System", "E-Mail + DM Sequenz die Partner überzeugt", "€397"),
            ("Upsell Funnel Bibliothek", "7 bewährte Upsell-Strukturen mit Conversion-Daten", "€597"),
            ("DS24 API Integration", "Vollautomatische Synchronisation all deiner Daten", "€297"),
        ],
        "faqs": [
            ("Funktioniert das für Vendor und Affiliate?", "Ja. Beide Seiten werden unterstützt. Als Vendor automatisierst du Affiliates und Funnels. Als Affiliate automatisierst du Promotion und Tracking."),
            ("Wie viele Produkte kann ich verwalten?", "Unbegrenzt. Kunden mit 47+ aktiven Produkten nutzen die Suite täglich."),
            ("Wird mein DS24-Account gesperrt?", "Nein. Alle Aktionen entsprechen den DS24-Richtlinien. Wir nutzen nur offizielle API-Verbindungen."),
            ("Wie läuft das Affiliate-Recruiting ab?", "KI findet passende Affiliates → personalisierte Outreach-E-Mail → automatisches Follow-up → Onboarding → Live. Vollautomatisch."),
            ("Was wenn ein Produkt schlecht läuft?", "Automatische Analyse identifiziert schwache Produkte. Handlungsempfehlung kommt per Telegram — du entscheidest, KI setzt um."),
            ("30-Tage-Garantie?", "Ja. Wenn dein DS24-Umsatz in 30 Tagen nicht gestiegen ist, volles Geld zurück."),
        ],
    },
    "gumroad-discord": {
        "name": "Gumroad Discord Bot", "netlify": "gumroad-discord-bot", "vercel": "gumroad-discord",
        "stats": [
            ("€14.100", "Community MRR", "14100"),
            ("2.847", "Aktive Members", "2847"),
            ("71%", "Free→Premium Conv.", "71"),
            ("0", "Manuelle Eingriffe", "0"),
        ],
        "bonuses": [
            ("Community Launch Kit", "Komplette Struktur für zahlende Discord-Community", "€497"),
            ("Content Calendar Template", "90-Tage Community-Content geplant + ready", "€197"),
            ("Churn-Prevention Playbook", "7 Strategien Mitglieder langfristig zu halten", "€297"),
            ("Gumroad Product Templates", "10 bewährte Produktbeschreibungen die konvertieren", "€197"),
        ],
        "faqs": [
            ("Muss ich Discord-Kenntnisse haben?", "Nein. Der Bot richtet sich selbst ein. Du sagst was du willst, wir konfigurieren alles in 48h."),
            ("Wie funktioniert das Premium-Gate?", "Kauf auf Gumroad → Bot verifiziert automatisch → Rolle vergeben → Zugang zu Premium-Channels in unter 30 Sekunden."),
            ("Kann ich verschiedene Mitglieder-Stufen haben?", "Ja. Bronze, Silber, Gold, VIP — unbegrenzte Stufen mit automatischer Rollen-Zuweisung und verschiedenen Preisen."),
            ("Was wenn jemand Zugang verliert (Chargeback)?", "Automatische Erkennung → Rollen-Entzug → freundliche Reaktivierungs-Sequenz. Kein manuelles Eingreifen."),
            ("Funktioniert das auch für Slack oder Telegram?", "Primär Discord und Telegram. Slack-Integration ist in Planung (Q3 2026)."),
            ("Gibt es eine Garantie?", "30 Tage. Nicht zufrieden → volles Geld zurück. Kein Risiko."),
        ],
    },
    "telegram-bot": {
        "name": "Telegram Marketing Bot", "netlify": "telegram-marketing-bot", "vercel": "telegram-bot",
        "stats": [
            ("47.392", "Abonnenten verwaltet", "47392"),
            ("34%", "Öffnungsrate", "34"),
            ("€25.410", "Telegram MRR", "25410"),
            ("847", "Bot-Befehle/Tag", "847"),
        ],
        "bonuses": [
            ("Telegram Wachstums-Blueprint", "Von 0 auf 10k Abonnenten in 90 Tagen", "€497"),
            ("Broadcast-Sequenz Bibliothek", "30 bewährte Nachrichten-Vorlagen die konvertieren", "€297"),
            ("Subscription Pricing Guide", "Wie du Premium-Stufen richtig bepreist", "€197"),
            ("Cross-Promotion System", "Automatisch andere Channels für Wachstum nutzen", "€397"),
        ],
        "faqs": [
            ("Wie unterscheidet sich Telegram von E-Mail?", "Telegram hat 34% Öffnungsrate vs. 8% bei E-Mail. Nachrichten kommen sofort an, kein Spam-Filter, direkte Interaktion."),
            ("Kann der Bot Bestellungen verarbeiten?", "Ja. Payment via Stripe oder PayPal direkt im Chat. Der Bot nimmt Bestellungen an, bestätigt und liefert digital."),
            ("Wie viele Channels kann ich verwalten?", "Unbegrenzt. Enterprise-Kunden verwalten 12+ Channels mit über 200k Abonnenten gesamt."),
            ("Was wenn Telegram mein Konto sperrt?", "Wir halten alle Telegram-Richtlinien ein. Kunden die die Anti-Spam-Regeln befolgen haben keine Probleme — seit 3 Jahren, tausende Kunden."),
            ("Kann ich bestehende Abonnenten importieren?", "Ja. Migration aus bestehenden Channels oder E-Mail-Listen — vollautomatisch mit Opt-in-Bestätigung."),
            ("30-Tage-Garantie?", "Ja. Nicht zufrieden — volles Geld zurück. So einfach ist das."),
        ],
    },
    "launcher": {
        "name": "BullPower Launcher", "netlify": "bullpower-launcher", "vercel": "launcher",
        "stats": [
            ("€97.400", "Rekord-Launch-Tag", "97400"),
            ("189", "Käufer Tag 1", "189"),
            ("67%", "Waitlist-Conversion", "67"),
            ("47", "Partner für Launch", "47"),
        ],
        "bonuses": [
            ("Launch Countdown System", "Psychologisch optimierter 14-Tage-Aufbau", "€497"),
            ("Affiliate Army Blueprint", "47 Partner in 14 Tagen rekrutieren und briefen", "€397"),
            ("Launch E-Mail Sequence", "7-Teil-Sequenz mit 67% Open Rate", "€297"),
            ("Launch Analytics Dashboard", "Echtzeit-Tracking aller KPIs während des Launches", "€497"),
        ],
        "faqs": [
            ("Was wenn mein Produkt noch nicht fertig ist?", "Perfekt. BullPower Launcher baut zuerst Waitlist auf — du lieferst dann wenn das Produkt bereit ist. Pre-Sales finanzieren oft die Entwicklung."),
            ("Wie viele Affiliates kann ich rekrutieren?", "So viele wie du willst. Das System skaliert von 5 auf 500 Partner — vollautomatisch mit individuellen Tracking-Links."),
            ("Was wenn der Launch floppt?", "Das passiert mit unserem System nicht. Wir haben einen Mindest-Revenue-Checkpoint: Wenn die Waitlist nicht ausreichend groß ist, empfehlen wir den Launch zu verschieben."),
            ("Kann ich mehrere Produkte gleichzeitig launchen?", "Nicht empfohlen. Fokus auf ein Produkt erzielt 3x bessere Ergebnisse. Danach kannst du das System für den nächsten Launch wiederholen."),
            ("Welche Zahlungsanbieter werden unterstützt?", "Stripe, PayPal, Digistore24, Elopage, Klarna und mehr. Multi-Currency global."),
            ("30-Tage-Garantie?", "Ja. Wenn du nach 30 Tagen weniger als 100 Waitlist-Anmeldungen hast, volles Geld zurück."),
        ],
    },
    "lead-capture": {
        "name": "Lead Capture Pro", "netlify": "bullpower-lead", "vercel": "lead-capture",
        "stats": [
            ("847", "Leads/Tag qualifiziert", "847"),
            ("8.4%", "Lead→Deal Conv.", "84"),
            ("€127k", "Pipeline aufgebaut/Mo", "127000"),
            ("7", "Deals/Tag abgeschlossen", "7"),
        ],
        "bonuses": [
            ("Lead Score Algorithmus", "Automatisch Hot-Leads von Cold-Leads trennen", "€597"),
            ("Nurturing Sequenz Pack", "12-Teil E-Mail + SMS + LinkedIn Sequenz", "€397"),
            ("CRM Integration Setup", "HubSpot, Pipedrive oder Salesforce vorkonfiguriert", "€497"),
            ("Discovery Call Script", "High-Ticket Abschluss-Framework mit 73% Close Rate", "€297"),
        ],
        "faqs": [
            ("Wie werden Leads qualifiziert?", "KI-Score basiert auf 23 Datenpunkten: Budget-Signale, Engagement, Firmengröße, Entscheidungs-Position. Nur Hot-Leads landen bei deinem Sales-Team."),
            ("Welche Lead-Quellen werden unterstützt?", "LinkedIn, Facebook, Google, Website-Formulare, Referrals, Kaltakquise-Listen — alle Quellen in einem System."),
            ("Wie lange bis zur ersten Lead-Pipeline?", "72 Stunden nach Setup. Erste qualifizierte Leads kommen automatisch in dein CRM."),
            ("Kann das System für B2C und B2B genutzt werden?", "Primär B2B optimiert. B2C mit hohem Ticket (€500+) funktioniert ebenfalls sehr gut."),
            ("Wie läuft das Lead-Nurturing ab?", "Vollautomatische Sequenz: E-Mail → LinkedIn → SMS → Telegram. Timing basiert auf Verhalten, nicht auf fixen Intervallen."),
            ("Gibt es eine Garantie?", "Ja. 30 Tage. Wenn du weniger als 50 qualifizierte Leads in Monat 1 bekommst, volles Geld zurück."),
        ],
    },
    "steuercockpit": {
        "name": "Steuer-Cockpit", "netlify": "bullpower-steuercockpit", "vercel": "steuercockpit",
        "stats": [
            ("€23.400", "Steuerersparnis/J", "23400"),
            ("0%", "Fehlerquote", "0"),
            ("90%", "Zeitersparnis", "90"),
            ("34", "Absetzungsmögl.", "34"),
        ],
        "bonuses": [
            ("Steueroptimierungs-Checkliste", "127 legale Wege Steuern zu sparen (DE/AT/CH)", "€397"),
            ("DATEV-Import Template", "Buchführung in 3 Klicks exportfertig", "€197"),
            ("GmbH-Gründungs-Leitfaden", "Wann und wie du eine GmbH gründen solltest", "€597"),
            ("Jahresabschluss KI-Assistent", "Kompletter Jahresabschluss in 2 Stunden", "€797"),
        ],
        "faqs": [
            ("Ersetzt das Steuer-Cockpit meinen Steuerberater?", "Es ergänzt ihn. Dein Steuerberater bekommt perfekt aufbereitete Unterlagen — spart ihm 80% Zeit → spart dir Honorar."),
            ("Welche Länder werden unterstützt?", "Deutschland, Österreich, Schweiz. DATEV-Export, Elster-kompatibel, MwSt.-Voranmeldung für alle drei Länder."),
            ("Wie werden meine Belege erfasst?", "Foto mit Handy → KI erkennt automatisch: Betrag, Kategorie, Datum, Lieferant. Fertig in 10 Sekunden pro Beleg."),
            ("Was wenn das Finanzamt prüft?", "Alle Buchungen sind revisionssicher gespeichert. GoBD-konform. Prüfungs-Export auf Knopfdruck."),
            ("Kann ich mehrere Unternehmen verwalten?", "Ja. Einzelunternehmen, GbR, GmbH — alle Rechtsformen, beliebig viele Mandanten in einem Login."),
            ("30-Tage-Garantie?", "Ja. Wenn das Cockpit nicht mindestens 5h/Woche spart, volles Geld zurück."),
        ],
    },
    "icomeauto": {
        "name": "IcomeAuto", "netlify": "icomeauto-bots", "vercel": "icomeauto",
        "stats": [
            ("€24.800", "Passiveinkommen/Mo", "24800"),
            ("5", "Streams aktiv", "5"),
            ("365", "Tage/J Autopilot", "365"),
            ("7.8x", "ROAS auto-reinvest.", "78"),
        ],
        "bonuses": [
            ("Income Stream Analyse", "Welche 5 Streams zu deinem Business passen", "€497"),
            ("Reinvestitions-Algorithmus", "Automatisch Gewinne in die besten Kanäle stecken", "€397"),
            ("Passive Income Tracking App", "Alle Einnahmen live in einem Dashboard", "€197"),
            ("Skalierungs-Blueprint", "Von €5k auf €25k/Mo passiv in 12 Monaten", "€797"),
        ],
        "faqs": [
            ("Wie viel Startkapital brauche ich?", "Ab €0. Einige Streams (Affiliate, digitale Produkte) laufen ohne Startkapital. Mit €500+ skaliert es schneller."),
            ("Wie passiv ist das wirklich?", "Nach Setup-Phase (2–4 Wochen): unter 4h/Woche Aufwand. Die meisten Kunden prüfen nur noch wöchentliche Reports."),
            ("Was sind die 5 Income-Streams?", "Digitale Produkte, Affiliate Marketing, KI-Content, Subscription Communities und Investments. Mix je nach Profil."),
            ("Was wenn ein Stream nicht mehr funktioniert?", "Automatische Umverteilung auf bessere Streams. Benachrichtigung per Telegram + Handlungsempfehlung."),
            ("Wie schnell kommt Geld rein?", "Erste Einnahmen typischerweise in Woche 2–3. Vollständiger Ramp-Up in 60–90 Tagen."),
            ("30-Tage-Garantie?", "Ja. Wenn du in 30 Tagen keine ersten automatisierten Einnahmen siehst, volles Geld zurück."),
        ],
    },
    "bullpower-ai": {
        "name": "BullPower AI Tools", "netlify": "bullpower-ai-tools", "vercel": "bullpower-ai",
        "stats": [
            ("23", "KI-Tools aktiv", "23"),
            ("847x", "ROI auf KI-Kosten", "847"),
            ("€2.847", "Content-Wert/Tag", "2847"),
            ("90%", "Zeitersparnis", "90"),
        ],
        "bonuses": [
            ("KI Tool Stack Guide", "Die 23 besten KI-Tools — was wofür und wie", "€297"),
            ("Prompt Engineering Bibel", "847 bewährte Prompts für Business-Automation", "€497"),
            ("KI-Workflow Templates", "12 komplette Workflows sofort einsatzbereit", "€397"),
            ("Monthly AI Updates", "Neue Tools und Strategien jeden Monat", "€197/Mo"),
        ],
        "faqs": [
            ("Muss ich jedes KI-Tool separat bezahlen?", "Nein. BullPower AI Tools kombiniert die besten Tools in einem System. Du zahlst einmal — alles integriert."),
            ("Welche KI-Modelle sind enthalten?", "Claude, GPT-4o, Gemini, Perplexity, Midjourney, ElevenLabs und 17 weitere — je nach Aufgabe automatisch ausgewählt."),
            ("Wie lerne ich die Tools zu nutzen?", "Du lernst nichts. Das System bedient sich selbst. Du sagst was du brauchst, KI erledigt es."),
            ("Was wenn neue bessere KI-Tools erscheinen?", "Automatisch integriert. Monatliche Updates ohne Mehrkosten. Du bist immer am Puls."),
            ("Kann ich die KI für mein Team nutzen?", "Ja. Enterprise-Plan: unbegrenzte User-Lizenzen für dein gesamtes Team."),
            ("30-Tage-Garantie?", "Ja. Wenn die KI-Suite nicht mindestens 10h/Woche spart, volles Geld zurück."),
        ],
    },
    "aiitec-all": {
        "name": "AIITEC All-in-One", "netlify": None, "vercel": "aiitec-all",
        "stats": [
            ("373+", "Module integriert", "373"),
            ("110", "Bot-Befehle", "110"),
            ("24/7", "Autonomer Betrieb", "247"),
            ("9", "Plattformen verb.", "9"),
        ],
        "bonuses": [
            ("AIITEC Setup-Service", "Komplettes 5-Tage-Onboarding durch unser Team", "€997"),
            ("Custom Bot Commands", "10 individuelle Befehle für dein Business", "€697"),
            ("Automation Blueprint", "Dein kompletter Automatisierungs-Fahrplan", "€497"),
            ("Priority Access", "Neue Features zuerst — 30 Tage Early Access", "€297"),
        ],
        "faqs": [
            ("Was ist AIITEC All-in-One?", "Das vollständige SuperMegaBot System — alle 373+ Module, 110 Bot-Befehle und 9 Plattform-Integrationen in einem einzigen Zugang."),
            ("Für wen ist das geeignet?", "Unternehmer die ALLES automatisieren wollen: Shop, Content, Leads, Revenue, Social Media — ohne 10 verschiedene Tools."),
            ("Wie lange dauert das Onboarding?", "5 Tage Done-For-You. Unser Team konfiguriert alles. Du startest Day 6 vollautomatisch."),
            ("Was wenn ich nur bestimmte Module brauche?", "Du kannst einzelne Module deaktivieren. Die meisten Kunden entdecken nach 2 Wochen, dass sie mehr Module nutzen als erwartet."),
            ("Ist das technisch komplex?", "Für dich nicht. Für uns schon — deshalb machen wir das Setup. Du bekommst ein fertiges System."),
            ("Gibt es eine Garantie?", "30 Tage. Nicht zufrieden → volles Geld zurück. Ohne Bedingungen."),
        ],
    },
    "aiitec-pinterest-portal": {
        "name": "AIITEC Pinterest Portal", "netlify": "aiitec-pinterest-portal", "vercel": "aiitec-pinterest-portal",
        "stats": [
            ("10M+", "Monthly Views", "10000000"),
            ("847", "Pins/Monat auto.", "847"),
            ("34%", "Traffic-Steigerung", "34"),
            ("0", "Manuelle Posts", "0"),
        ],
        "bonuses": [
            ("Pinterest SEO Masterclass", "Wie Pins auf Seite 1 ranken", "€397"),
            ("Pin Design Template Pack", "50 bewährte Designs die viral gehen", "€297"),
            ("Board-Strategie Blueprint", "Optimale Board-Struktur für maximale Reichweite", "€197"),
            ("Shopping-Tab Setup", "Pinterest Shopping vollständig einrichten", "€497"),
        ],
        "faqs": [
            ("Für welche Nischen funktioniert Pinterest am besten?", "Smart Home, Fashion, Beauty, Reisen, Food, DIY, Fitness. Wenn deine Produkte fotogen sind, funktioniert Pinterest hervorragend."),
            ("Wie viele Pins werden täglich erstellt?", "28–47 Pins täglich — vollautomatisch. KI erstellt, optimiert und plant auf Basis von Trending-Daten."),
            ("Wird mein Pinterest-Konto gesperrt?", "Nein. Wir halten alle Pinterest-Richtlinien ein. Rate-Limits werden automatisch respektiert."),
            ("Wie lange bis zu ersten Ergebnissen?", "Pinterest ist ein Slow-Burn-Kanal: erste Traffic-Steigerung in 4–6 Wochen, volle Wirkung in 3–4 Monaten."),
            ("Kann ich Shopping-Pins verknüpfen?", "Ja. Shopify, WooCommerce und jeder Shop mit Produktfeed werden automatisch mit Pinterest Shopping verbunden."),
            ("Gibt es eine Garantie?", "30 Tage. Wenn dein Pinterest-Traffic nicht gestiegen ist, volles Geld zurück."),
        ],
    },
}

# ─── HTML BUILDER ─────────────────────────────────────────────

def _counter_js(slug):
    return f"""
<script>
(function(){{
  if(window.cntDone_{slug}) return;
  window.cntDone_{slug}=true;
  var counters=document.querySelectorAll('[data-cnt-{slug}]');
  var started=false;
  function run(){{
    if(started) return; started=true;
    counters.forEach(function(el){{
      var target=parseFloat(el.getAttribute('data-cnt-{slug}'))||0;
      var suffix=el.getAttribute('data-sfx')||'';
      var prefix=el.getAttribute('data-pfx')||'';
      var dur=2000, steps=60, step=0;
      var iv=setInterval(function(){{
        step++;
        var val=Math.round(target*(step/steps));
        el.textContent=prefix+(target>1000?val.toLocaleString('de-DE'):val)+suffix;
        if(step>=steps){{ el.textContent=prefix+(target>1000?Math.round(target).toLocaleString('de-DE'):target)+suffix; clearInterval(iv); }}
      }},dur/steps);
    }});
  }}
  var obs=new IntersectionObserver(function(entries){{entries.forEach(function(e){{if(e.isIntersecting) run();}});}},{{threshold:.3}});
  var sec=document.getElementById('stats-{slug}');
  if(sec) obs.observe(sec); else run();
}})();
</script>"""

def build_v2_injection(proj):
    name = proj["name"]
    slug = name.replace(" ", "-").lower().replace("ö","oe").replace("ä","ae").replace("ü","ue")

    # ── STATS COUNTER ──────────────────────────────────────────
    stat_cards = ""
    for label, sub, raw in proj["stats"]:
        # parse numeric value for counting
        num_str = raw.replace(",","").replace(".","")
        try: num = float(num_str)
        except: num = 0
        # detect prefix/suffix
        prefix = "€" if label.startswith("€") else ""
        val_display = label.lstrip("€").rstrip("%").rstrip("x").rstrip("h").rstrip("+")
        sfx = ""
        if label.endswith("%"): sfx="%"
        elif label.endswith("x"): sfx="x"
        elif label.endswith("h"): sfx="h"
        elif label.endswith("+"): sfx="+"
        stat_cards += f"""
<div style="text-align:center;padding:1.5rem 1rem">
  <div style="font-size:clamp(2rem,5vw,3.2rem);font-weight:900;letter-spacing:-.04em;line-height:1;background:linear-gradient(135deg,#6c63ff,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text"
       data-cnt-{slug}="{num}" data-pfx="{prefix}" data-sfx="{sfx}">{label}</div>
  <div style="font-size:.78rem;color:#555577;text-transform:uppercase;letter-spacing:.08em;margin-top:.5rem;font-weight:600">{sub}</div>
</div>"""

    # ── BONUSES ────────────────────────────────────────────────
    bonus_cards = ""
    total_val = 0
    for i, (btitle, bdesc, bval) in enumerate(proj["bonuses"]):
        try:
            v = float(bval.replace("€","").replace(".","").replace(",",".").split("/")[0])
            total_val += v
        except: pass
        bonus_cards += f"""
<div style="display:flex;gap:1rem;align-items:flex-start;background:var(--surface2,#0c1220);border:1px solid rgba(108,99,255,.18);border-radius:14px;padding:1.25rem">
  <div style="min-width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#6c63ff,#00d4ff);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:.9rem;flex-shrink:0">#{i+1}</div>
  <div style="flex:1">
    <div style="font-weight:800;font-size:.95rem;margin-bottom:.2rem">{btitle}</div>
    <div style="font-size:.8rem;color:#94a3b8;line-height:1.5">{bdesc}</div>
  </div>
  <div style="text-align:right;flex-shrink:0">
    <div style="font-size:.68rem;color:#555577;text-decoration:line-through">{bval}</div>
    <div style="font-size:.78rem;font-weight:800;color:#00ff88">GRATIS</div>
  </div>
</div>"""

    total_str = f"€{int(total_val):,}".replace(",",".") if total_val else "€1.497"

    # ── FAQ ────────────────────────────────────────────────────
    faq_items = ""
    for i, (q, a) in enumerate(proj["faqs"]):
        faq_items += f"""
<div class="ht2-faq-item" onclick="htFaqToggle(this)" style="border:1px solid rgba(108,99,255,.18);border-radius:12px;overflow:hidden;cursor:pointer;margin-bottom:.75rem">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:1.1rem 1.25rem;background:var(--surface2,#0c1220)">
    <span style="font-weight:700;font-size:.9rem;line-height:1.4;padding-right:1rem">{q}</span>
    <span class="ht2-faq-icon" style="color:#6c63ff;font-size:1.3rem;font-weight:300;flex-shrink:0;transition:transform .25s">＋</span>
  </div>
  <div class="ht2-faq-body" style="max-height:0;overflow:hidden;transition:max-height .3s ease">
    <div style="padding:1rem 1.25rem 1.25rem;font-size:.85rem;color:#94a3b8;line-height:1.7;border-top:1px solid rgba(255,255,255,.05)">{a}</div>
  </div>
</div>"""

    return f"""
<!-- ── HT-V2 INJECTION START ── -->
<style>
.ht2-section{{padding:72px 5%;}}
.ht2-inner{{max-width:1100px;margin:0 auto;}}
.ht2-label{{font-size:.68rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#00d4ff;margin-bottom:.75rem;}}
.ht2-h2{{font-size:clamp(1.6rem,3.5vw,2.4rem);font-weight:900;letter-spacing:-.03em;line-height:1.15;margin-bottom:1.5rem;}}
.ht2-h2 em{{font-style:normal;background:linear-gradient(135deg,#6c63ff,#00d4ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}}
.ht2-faq-item.open .ht2-faq-icon{{transform:rotate(45deg);}}
.ht2-faq-item.open .ht2-faq-body{{max-height:400px;}}
@keyframes ht2pulse{{0%,100%{{box-shadow:0 0 0 0 rgba(108,99,255,.4)}}50%{{box-shadow:0 0 0 14px rgba(108,99,255,0)}}}}
</style>

<!-- STATS COUNTER -->
<section class="ht2-section" id="stats-{slug}" style="background:linear-gradient(135deg,rgba(108,99,255,.07),rgba(0,212,255,.05));border-top:1px solid var(--border,#1a1a2e);border-bottom:1px solid var(--border,#1a1a2e)">
  <div class="ht2-inner">
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;">
      {stat_cards}
    </div>
    <div style="text-align:center;margin-top:1.25rem;padding-top:1.25rem;border-top:1px solid rgba(255,255,255,.06)">
      <span style="font-size:.78rem;color:#555577;letter-spacing:.06em">Echte Zahlen unserer Kunden · Letzte Aktualisierung: Juli 2026</span>
    </div>
  </div>
</section>

<!-- BONUS STACK -->
<section class="ht2-section" style="background:var(--bg,#0a0a0f)">
  <div class="ht2-inner">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:3rem;align-items:start">
      <div>
        <div class="ht2-label">Exklusive Boni</div>
        <h2 class="ht2-h2">Alles was du brauchst<br><em>kostenlos dazu</em></h2>
        <p style="color:#94a3b8;font-size:.95rem;line-height:1.65;margin-bottom:1.5rem">Im Pro &amp; Enterprise Plan bekommst du diese Boni kostenlos dazu. Gesamtwert:</p>
        <div style="background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.2);border-radius:14px;padding:1.25rem;text-align:center;margin-bottom:1.5rem">
          <div style="font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.3rem">Bonus-Gesamtwert</div>
          <div style="font-size:2.6rem;font-weight:900;color:#ffd700;letter-spacing:-.04em">{total_str}</div>
          <div style="font-size:.78rem;color:#94a3b8;margin-top:.25rem">für dich kostenlos im Paket</div>
        </div>
        <a href="#preise" style="display:inline-block;padding:.85rem 2rem;background:linear-gradient(135deg,#6c63ff,#5a52e0);color:#fff;border-radius:10px;font-weight:800;font-size:.9rem;text-decoration:none;letter-spacing:.02em">Boni sichern →</a>
      </div>
      <div style="display:flex;flex-direction:column;gap:.75rem">
        {bonus_cards}
      </div>
    </div>
  </div>
</section>

<!-- GARANTIE BADGE -->
<section class="ht2-section" style="background:var(--surface,#0f0f1a);border-top:1px solid var(--border,#1a1a2e);border-bottom:1px solid var(--border,#1a1a2e)">
  <div class="ht2-inner" style="text-align:center">
    <div style="display:inline-flex;flex-direction:column;align-items:center;gap:1.5rem;max-width:640px">
      <div style="width:120px;height:120px;border-radius:50%;background:linear-gradient(135deg,rgba(0,255,136,.12),rgba(0,212,255,.08));border:2px solid rgba(0,255,136,.3);display:flex;align-items:center;justify-content:center;animation:ht2pulse 3s infinite">
        <svg width="52" height="52" viewBox="0 0 52 52" fill="none">
          <path d="M26 4L8 12v12c0 11.1 7.7 21.5 18 24 10.3-2.5 18-12.9 18-24V12L26 4z" fill="rgba(0,255,136,.15)" stroke="#00ff88" stroke-width="1.5"/>
          <path d="M18 26l5.5 5.5 10.5-10.5" stroke="#00ff88" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div>
        <div class="ht2-label" style="text-align:center;color:#00ff88">Risikofreie Investition</div>
        <h2 style="font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;letter-spacing:-.03em;line-height:1.15;margin-bottom:.75rem">30 Tage <em style="font-style:normal;color:#00ff88">Geld-zurück-Garantie</em></h2>
        <p style="color:#94a3b8;font-size:1rem;line-height:1.7;margin-bottom:1.5rem">Teste {name} 30 Tage lang ohne Risiko. Wenn du nicht 100% zufrieden bist — aus welchem Grund auch immer — bekommst du das volle Geld zurück. Kein Kleingedrucktes. Kein Aufwand. Kein Risiko.</p>
        <div style="display:flex;justify-content:center;gap:2rem;flex-wrap:wrap">
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:900;color:#00ff88">100%</div>
            <div style="font-size:.72rem;color:#555577;text-transform:uppercase;letter-spacing:.07em">Rückerstattung</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:900;color:#00d4ff">0</div>
            <div style="font-size:.72rem;color:#555577;text-transform:uppercase;letter-spacing:.07em">Fragen gestellt</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:900;color:#ffd700">30</div>
            <div style="font-size:.72rem;color:#555577;text-transform:uppercase;letter-spacing:.07em">Tage Testzeit</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- FAQ -->
<section class="ht2-section" style="background:var(--bg,#0a0a0f)">
  <div class="ht2-inner" style="max-width:780px">
    <div class="ht2-label">Häufige Fragen</div>
    <h2 class="ht2-h2">Noch offene <em>Fragen?</em></h2>
    {faq_items}
    <div style="text-align:center;margin-top:2rem;padding:1.5rem;background:rgba(108,99,255,.06);border:1px solid rgba(108,99,255,.15);border-radius:14px">
      <p style="color:#94a3b8;font-size:.9rem;margin-bottom:.75rem">Noch eine Frage? Wir antworten innerhalb von 2 Stunden.</p>
      <a href="https://t.me/bullpowerhub" target="_blank" style="display:inline-block;padding:.7rem 1.75rem;background:#6c63ff;color:#fff;border-radius:10px;font-weight:700;font-size:.85rem;text-decoration:none">Telegram Support →</a>
    </div>
  </div>
</section>

<script>
function htFaqToggle(el){{
  var isOpen=el.classList.contains('open');
  document.querySelectorAll('.ht2-faq-item.open').forEach(function(x){{x.classList.remove('open');}});
  if(!isOpen) el.classList.add('open');
}}
</script>
{_counter_js(slug)}
<!-- ── HT-V2 INJECTION END ── -->
"""


def process_file(dir_name, proj, base=BASE):
    html_path = base / dir_name / "index.html"
    if not html_path.exists():
        print(f"  ⚠️  kein index.html in {dir_name}")
        return False
    html = html_path.read_text(encoding="utf-8")

    # Alten v2-Block entfernen falls vorhanden
    html = re.sub(r'\n?<!-- ── HT-V2 INJECTION START ──.*?<!-- ── HT-V2 INJECTION END ── -->\n?', '', html, flags=re.DOTALL)

    injection = build_v2_injection(proj)

    # Einfügen: nach der v1-Testimonials-Sektion oder vor Pricing
    markers = [
        '<!-- ── HIGH-TICKET INJECTION END ── -->',
        '<section class="pricing-section"',
        '</main>',
        '<footer',
    ]
    inserted = False
    for m in markers:
        if m in html:
            html = html.replace(m, m + "\n" + injection, 1)
            inserted = True
            break
    if not inserted:
        html += "\n" + injection

    html_path.write_text(html, encoding="utf-8")
    return True


def deploy_netlify(site_name, dir_name):
    sid = NETLIFY_SITE_IDS.get(site_name)
    if not sid:
        return False
    d = BASE / dir_name
    if not d.exists():
        return False
    r = subprocess.run(["netlify","deploy","--prod",f"--dir={d}",f"--site={sid}"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def deploy_vercel(proj_name, dir_name):
    d = BASE / dir_name
    if not d.exists():
        return False
    r = subprocess.run(["vercel","--prod","--yes","--cwd",str(d)],
                       capture_output=True, text=True, timeout=180)
    return r.returncode == 0


def main():
    deploy = "--deploy" in sys.argv or "-d" in sys.argv

    # Dir-Mapping: proj_key → subdir
    DIR_MAP = {
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
        "aiitec-all":                 "aiitec-all",
        "aiitec-pinterest-portal":    "aiitec-pinterest-portal",
    }

    print(f"\n{'='*60}")
    print(f"HT UPGRADE v2 — {len(PROJECTS)} Sites")
    print(f"Mode: {'DEPLOY' if deploy else 'FILE-UPDATE ONLY'}")
    print(f"{'='*60}\n")

    ok_count = 0
    for key, proj in PROJECTS.items():
        dir_name = DIR_MAP.get(key, key)
        print(f"⚙️  {proj['name']}")
        ok = process_file(dir_name, proj)
        if not ok:
            print(f"  ❌ übersprungen")
            continue
        print(f"  ✅ HTML: Stats + Bonus + Garantie + FAQ injiziert")
        ok_count += 1

        if deploy:
            n_name = proj.get("netlify")
            if n_name:
                n_ok = deploy_netlify(n_name, dir_name)
                print(f"  {'✅' if n_ok else '❌'} Netlify → {n_name}.netlify.app")
            v_name = proj.get("vercel")
            if v_name:
                v_ok = deploy_vercel(v_name, dir_name)
                print(f"  {'✅' if v_ok else '❌'} Vercel → {v_name}.vercel.app")
        print()

    print(f"\n✅ {ok_count}/{len(PROJECTS)} Sites mit v2-Injection aktualisiert")


if __name__ == "__main__":
    main()
