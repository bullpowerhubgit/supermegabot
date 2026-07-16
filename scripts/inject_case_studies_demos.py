#!/usr/bin/env python3
"""Injiziert Case Studies + interaktive Demo-Sektion in alle Landing Pages."""
import os, re

NETLIFY = "/Users/rudolfsarkany/supermegabot/netlify-deploy"

# Produkt-Konfiguration: case studies + demo per Verzeichnis
CONFIGS = {
    "bullpower-ai": {
        "product": "BullPower AI",
        "icon": "🤖",
        "demo_title": "Live KI-Demo",
        "demo_desc": "Gib eine Aufgabe ein — BullPower AI löst sie sofort:",
        "demo_suggestions": [
            "Schreibe 5 Shopify-Produktbeschreibungen für Smart-Home-Gadgets",
            "Analysiere meinen Shop und gib SEO-Empfehlungen",
            "Erstelle einen Klaviyo Email-Flow für Warenkorbabbrecher",
        ],
        "demo_outputs": [
            "✅ <strong>5 Produktbeschreibungen generiert</strong><br>»Smart LED Strip Pro — 16 Mio. Farben, Sprachsteuerung, 5m. Perfekt für Gaming-Räume und Wohnzimmer. App-gesteuert via Alexa & Google Home.«<br><span style='color:#94a3b8;font-size:0.85rem'>+ 4 weitere Beschreibungen erstellt in 3.2 Sek.</span>",
            "✅ <strong>SEO-Analyse abgeschlossen</strong><br>• 23 Produkte ohne Meta-Description → auto-generiert<br>• 47 Alt-Texte fehlen → hinzugefügt<br>• Top-Keyword-Gap: »smart home gadget kaufen« — fehlt auf 12 Seiten",
            "✅ <strong>Klaviyo-Flow erstellt</strong><br>Email 1 (1h): »Vergessen?« | Email 2 (24h): »10% Rabatt« | Email 3 (72h): »Letzte Chance«<br>Erwartete Recovery-Rate: 8-12% basierend auf Branchendurchschnitt",
        ],
        "cases": [
            {"name": "Klaus M.", "role": "Shopify Store-Inhaber, Wien", "avatar": "KM", "color": "#7c3aed",
             "result": "+€4.200/Monat Zusatzumsatz", "duration": "nach 6 Wochen",
             "text": "Ich hatte 340 Produkte ohne ordentliche Beschreibungen. BullPower AI hat alle in einer Nacht automatisch optimiert — meine organischen Klicks stiegen um 67% in 3 Wochen."},
            {"name": "Sarah L.", "role": "E-Commerce Managerin, München", "avatar": "SL", "color": "#2563eb",
             "result": "12h/Woche Zeitersparnis", "duration": "von Anfang an",
             "text": "Content-Erstellung war unser größter Flaschenhals. Jetzt generiert der Bot täglich 20+ Posts, Emails und Anzeigentexte — alles auf Marke, ohne dass ich eingreifen muss."},
            {"name": "Timo R.", "role": "Dropshipping Agency, Hamburg", "avatar": "TR", "color": "#059669",
             "result": "€12.400 MRR bei Kunden", "duration": "in 3 Monaten",
             "text": "Ich biete BullPower AI als White-Label an meine Kunden an. Der Preis rechtfertigt sich sofort — kein Kunde hat nach dem ersten Monat abgesagt."},
        ],
    },
    "shopify-brutal-tuning": {
        "product": "Shopify Brutal Tuning",
        "icon": "⚡",
        "demo_title": "Shop-Analyse Live",
        "demo_desc": "Deine Shop-URL eingeben — sofortige Optimierungsanalyse:",
        "demo_suggestions": [
            "Analysiere meinen Shop auf Conversion-Probleme",
            "Zeige mir die 10 langsamsten Seiten meines Shops",
            "Welche Produkte haben die höchste Abbruchrate?",
        ],
        "demo_outputs": [
            "✅ <strong>Conversion-Analyse abgeschlossen</strong><br>• Checkout-Abbruchrate: 71% → Haupt-Ursache: fehlendes Trust-Badge<br>• Mobile-Score: 58/100 → 3 kritische Bilder unoptimiert<br>• A/B-Test empfohlen: »Jetzt kaufen« vs »In den Warenkorb«",
            "✅ <strong>Performance-Report</strong><br>Langsamste Seiten: /collections/all (4.8s), /products/* (3.2s), /cart (2.1s)<br>Quick-Win: Bilder auf WebP → Ladezeit -62%, sofort umsetzbar",
            "✅ <strong>Abbruch-Analyse</strong><br>Höchste Abbruchrate: »Smart LED Streifen« (89%) — Hauptgrund: kein Video<br>Lösung: Demo-Video eingebettet → Conversion +34% (Branchen-Benchmark)",
        ],
        "cases": [
            {"name": "Markus T.", "role": "Shopify Plus Store, Frankfurt", "avatar": "MT", "color": "#f59e0b",
             "result": "Conversion von 1.1% → 3.4%", "duration": "in 4 Wochen",
             "text": "Das Tool hat in 2 Minuten gefunden, was wir monatelang gesucht haben: unser Checkout-Formular war auf Mobile kaputt. Fix deployed, Umsatz verdreifacht."},
            {"name": "Anna K.", "role": "Beauty E-Commerce, Berlin", "avatar": "AK", "color": "#ec4899",
             "result": "+€8.900/Monat", "duration": "nach erstem Monat",
             "text": "Page Speed von 42 auf 91 — das allein hat uns 23% mehr organischen Traffic gebracht. Brutal einfach zu bedienen, brutale Ergebnisse."},
            {"name": "Felix B.", "role": "Shopify Agency Owner, Zürich", "avatar": "FB", "color": "#8b5cf6",
             "result": "15 Kunden optimiert", "duration": "in 2 Monaten",
             "text": "Ich verwende Brutal Tuning für alle Onboarding-Audits. Jeder neue Kunde bekommt sofort einen 40-Punkte-Report — das rechtfertigt alleine meine Agency-Gebühren."},
        ],
    },
    "steuercockpit": {
        "product": "SteuercockPit Pro",
        "icon": "💰",
        "demo_title": "Steuer-Demo",
        "demo_desc": "Gib deine Situation ein — sofortige Steueroptimierungsanalyse:",
        "demo_suggestions": [
            "Ich bin Shopify-Händler mit €80k Jahresumsatz in Österreich",
            "Wie viel USt. muss ich auf meine EU-Verkäufe abführen?",
            "Welche Ausgaben kann ich als Online-Händler absetzen?",
        ],
        "demo_outputs": [
            "✅ <strong>Steueroptimierung für AT Online-Händler €80k</strong><br>• OSS-Pflicht: JA ab €10k EU-Umsatz → bereits registriert?<br>• Steuerersparnis durch Kleinunternehmerregelung: NICHT möglich (>€35k)<br>• Empfehlung: GmbH-Gründung ab €60k Gewinn → Steuerersparnis ~€8.400/Jahr",
            "✅ <strong>EU-OSS Berechnung</strong><br>DE: 19% auf €23.000 = €4.370 | FR: 20% auf €8.400 = €1.680 | IT: 22% auf €5.200 = €1.144<br>Gesamt fällig: €7.194 | Nächste Meldung: 31. Oktober 2026",
            "✅ <strong>Absetzbare Ausgaben für Online-Händler</strong><br>✓ Plattformgebühren (Shopify, Stripe, DS24)<br>✓ Werbung (Meta Ads, Google Ads, LinkedIn)<br>✓ Software & SaaS-Abos<br>✓ Homeoffice-Pauschale AT: €900/Jahr<br>✓ Fortbildung & Fachbücher",
        ],
        "cases": [
            {"name": "Robert H.", "role": "Shopify-Händler, Graz", "avatar": "RH", "color": "#10b981",
             "result": "€14.200 Steuerersparnis", "duration": "im ersten Jahr",
             "text": "Ich wusste nicht, dass ich OSS-pflichtig war. SteuercockPit hat das sofort erkannt, mich durch die Anmeldung geführt und gleichzeitig €14k Optimierungspotenzial aufgedeckt."},
            {"name": "Petra M.", "role": "Digistore24-Affiliaterin, Linz", "avatar": "PM", "color": "#f59e0b",
             "result": "4h/Monat statt 20h", "duration": "seit Tag 1",
             "text": "Früher saß ich stundenlang an meiner MWST-Abrechnung. Jetzt tippt SteuercockPit alles automatisch ein — ich prüfe nur noch und klicke auf Senden."},
            {"name": "David S.", "role": "E-Commerce GmbH, Salzburg", "avatar": "DS", "color": "#3b82f6",
             "result": "0 Nachzahlungen in 2 Jahren", "duration": "seit Nutzungsbeginn",
             "text": "Als GmbH mit 5-stelligen Monatseinnahmen ist Compliance kein Spaß. SteuercockPit alarmiert mich sofort bei Anomalien — noch nie eine Nachzahlung gehabt."},
        ],
    },
    "telegram-bot": {
        "product": "Telegram Agency Bot",
        "icon": "📱",
        "demo_title": "Bot-Demo",
        "demo_desc": "Simuliere deinen eigenen Subscription-Bot:",
        "demo_suggestions": [
            "/start — Bot begrüßt neuen User",
            "/premium — Zeige verfügbare Abo-Pläne",
            "/stats — Abonnenten-Statistiken anzeigen",
        ],
        "demo_outputs": [
            "🤖 <strong>Bot-Antwort:</strong><br>Willkommen bei <em>deinem Premium-Kanal</em>! 🚀<br>Du hast Zugang zu:<br>• 📊 Tägliche Marktanalysen<br>• 🎯 Exklusive Deals & Alerts<br>• 💬 Private Community<br><br>👉 /premium für Abo-Pläne",
            "💳 <strong>Verfügbare Pläne:</strong><br>Starter: €29/Monat — Basis-Zugang<br>Pro: €79/Monat — Alle Features + Alerts<br>Agency: €199/Monat — Unbegrenzte Nutzer<br><br>[Stripe-Zahlung wird direkt im Chat abgewickelt ✅]",
            "📊 <strong>Deine Bot-Statistiken:</strong><br>Gesamt-Abonnenten: 847<br>Aktive Abos: 312 (€17.680/Monat MRR)<br>Churn diese Woche: 3 (-0.96%)<br>Neue User heute: 14<br>Durchschnittl. Abo-Dauer: 4.2 Monate",
        ],
        "cases": [
            {"name": "Michael B.", "role": "Trading-Coach, Wien", "avatar": "MB", "color": "#7c3aed",
             "result": "€8.400 MRR in 60 Tagen", "duration": "ab Woche 1",
             "text": "Ich hatte bereits 2.000 Follower auf Telegram. Das Bot-System hat aus meiner kostenlosen Gruppe einen €29/mo Kanal gemacht — 290 zahlende Mitglieder in 2 Monaten."},
            {"name": "Lisa F.", "role": "KI-Kurse Anbieterin, München", "avatar": "LF", "color": "#ec4899",
             "result": "Zero-Support-Setup", "duration": "sofort nach Einrichtung",
             "text": "Keine Ahnung von Technik — in 2 Stunden war mein Bot live. Stripe-Zahlungen, Auto-Zugang, automatische Mahnung bei Failed Payment. Alles fertig."},
            {"name": "Jan K.", "role": "Affiliate Marketing, Hamburg", "avatar": "JK", "color": "#059669",
             "result": "3 Bots für 3 Nischen", "duration": "ein Setup, drei Kanäle",
             "text": "Smart Home Deals, Crypto Alerts und E-Commerce Tips — drei komplett separate Bots, alle aus einem Dashboard gesteuert. Skalieren war noch nie so einfach."},
        ],
    },
    "autoincome-ai": {
        "product": "AutoIncome AI",
        "icon": "💸",
        "demo_title": "Einkommens-Kalkulator",
        "demo_desc": "Wähle deine Ausgangssituation:",
        "demo_suggestions": [
            "Ich habe 500€ Budget und 5h/Woche Zeit",
            "Zeige mir die 3 profitabelsten passiven Einkommensquellen",
            "Erstelle meinen 90-Tage-Aktionsplan",
        ],
        "demo_outputs": [
            "✅ <strong>Analyse für 500€ Budget / 5h Woche</strong><br>Empfohlene Strategie: Affiliate + digitale Produkte<br>• Monat 1-2: Setup + Content (€0-200 Einnahmen)<br>• Monat 3-4: Wachstumsphase (€200-800/mo)<br>• Ab Monat 6: Skalierung möglich auf €2.000+/mo",
            "✅ <strong>Top 3 passive Einkommensquellen 2026</strong><br>1. Digistore24 Affiliate (50% Provision, sofort startbar)<br>2. Telegram Subscription Bot (€29-199/mo recurring)<br>3. Gumroad digitale Produkte (kein Lager, instant delivery)<br>Potenzial gesamt: €1.500-4.000/mo nach 6 Monaten",
            "✅ <strong>90-Tage Aktionsplan erstellt</strong><br>Woche 1-2: Nische + Plattform wählen<br>Woche 3-6: Ersten Content + Produkt live<br>Woche 7-10: Traffic aufbauen (SEO + Social)<br>Woche 11-13: Automatisierung + Skalierung<br>📅 Exportiert nach Google Calendar",
        ],
        "cases": [
            {"name": "Sandra W.", "role": "Lehrerin, Graz (Nebenberuf)", "avatar": "SW", "color": "#f59e0b",
             "result": "€1.800/Monat nebenbei", "duration": "nach 5 Monaten",
             "text": "Als Lehrerin dachte ich, passives Einkommen sei nur für Techniker. AutoIncome AI hat mir Schritt für Schritt gezeigt wie es geht — heute verdiene ich mehr nebenbei als mancher im Hauptberuf."},
            {"name": "Thomas E.", "role": "Angestellter, Frankfurt", "avatar": "TE", "color": "#3b82f6",
             "result": "€4.200 in 3 Monaten", "duration": "mit nur 4h/Woche",
             "text": "Das System hat mir genau gesagt welche Affiliate-Produkte ich bewerben soll, wie ich Content erstelle und wo ich Traffic herbekomme. 4 Stunden pro Woche, €4.200 Ergebnis."},
            {"name": "Nicole P.", "role": "Freelancerin, Zürich", "avatar": "NP", "color": "#8b5cf6",
             "result": "Freelance-Einnahmen verdoppelt", "duration": "durch Automatisierung",
             "text": "AutoIncome AI hat mir geholfen, mein bestehendes Wissen zu digitalen Produkten zu verpacken. Mein erster Gumroad-Kurs: €97, 43 Verkäufe im ersten Monat ohne Werbung."},
        ],
    },
    "creatorai-ultra": {
        "product": "CreatorAI Ultra",
        "icon": "🎨",
        "demo_title": "Content Demo",
        "demo_desc": "Lass KI sofort Content für dich erstellen:",
        "demo_suggestions": [
            "Erstelle 7 Instagram-Posts für mein Smart Home Business",
            "Schreibe einen YouTube-Script über E-Commerce Automatisierung",
            "Generiere 30 Tage Content-Kalender für LinkedIn",
        ],
        "demo_outputs": [
            "✅ <strong>7 Instagram Posts generiert</strong><br>Post 1: »Smart Home Gadgets die 2026 explodieren werden 🔥« + Hook + CTA<br>Post 2: »Mein Lieblings-Setup für unter €200 — Thread 🧵«<br>Post 3: »3 Fehler die 90% der Dropshipper machen [und wie du sie vermeidest]«<br><em>+ 4 weitere Posts inkl. Hashtag-Sets</em>",
            "✅ <strong>YouTube-Script: 12min Video</strong><br>Intro (Hook + Preview): 45 Sek.<br>Problem-Agitate: 2 Min.<br>Lösung (3 Wege): 6 Min.<br>CTA + Outro: 90 Sek.<br>SEO-Titel: »E-Commerce 2026: Diese KI-Tools machen ALLES allein (ich teste sie)«",
            "✅ <strong>30-Tage LinkedIn Kalender</strong><br>Woche 1: Thought Leadership (3 Posts)<br>Woche 2: Case Studies (3 Posts)<br>Woche 3: How-To Content (3 Posts)<br>Woche 4: Engagement + Polls (3 Posts)<br>📅 Exportiert + geplant für 08:00 Uhr täglich",
        ],
        "cases": [
            {"name": "Julia M.", "role": "Content Creator, München", "avatar": "JM", "color": "#ec4899",
             "result": "Von 800 → 12k Instagram", "duration": "in 4 Monaten",
             "text": "Ich hatte keine Zeit täglich Content zu erstellen. CreatorAI Ultra generiert jetzt täglich 3 Posts für mich — konsistent, markenkonform und mit echter Reichweite."},
            {"name": "Stefan R.", "role": "E-Commerce Coach, Düsseldorf", "avatar": "SR", "color": "#7c3aed",
             "result": "€6.800 Kursverkäufe", "duration": "im ersten Monat",
             "text": "Das Tool hat meinen Launch-Content komplett übernommen: Email-Sequenz, Social Posts, YouTube-Script, Sales-Page-Texte. Launch war mein bisher erfolgreichster."},
            {"name": "Mia H.", "role": "Social Media Managerin, Wien", "avatar": "MH", "color": "#06b6d4",
             "result": "8 Kunden statt 3", "duration": "bei gleichem Zeitaufwand",
             "text": "Ich manege jetzt 8 Kundenkonten statt 3 — ohne Mehrarbeit. CreatorAI Ultra generiert den Grundcontent, ich verfeinere nur noch. Mein Stundensatz ist um 40% gestiegen."},
        ],
    },
    "shopify-suite": {
        "product": "Shopify Suite Pro",
        "icon": "🛒",
        "demo_title": "Shop-Demo",
        "demo_desc": "Automatisiere deinen Shopify-Store:",
        "demo_suggestions": [
            "Synchronisiere 500 neue Produkte mit Beschreibungen",
            "Aktiviere automatische Preisanpassung gegen Konkurrenz",
            "Erstelle Smart Collections für alle Kategorien",
        ],
        "demo_outputs": [
            "✅ <strong>500 Produkte synchronisiert</strong><br>• Titel optimiert: 500/500 ✓<br>• Beschreibungen generiert: 500/500 ✓<br>• Bilder komprimiert: 1.247 Bilder (-62% Dateigröße)<br>• Tags hinzugefügt: durchschn. 8 Tags/Produkt<br>Dauer: 4 Minuten 12 Sekunden",
            "✅ <strong>Preisanpassung aktiv</strong><br>Überwachte Konkurrenten: 3 (Amazon.de, eBay, Idealo)<br>Regel: Immer 2-5% unter Bestpreis bleiben<br>Heute angepasst: 23 Produkte<br>Erwartete Conversion-Steigerung: +8-14%",
            "✅ <strong>12 Smart Collections erstellt</strong><br>Smart Home | Solar & Energie | Gadgets unter €50 | Top-Rated | Sale | Neuheiten | Bundle-Deals | ...<br>Alle Collections mit SEO-Beschreibungen befüllt<br>Google Shopping Feed aktualisiert ✓",
        ],
        "cases": [
            {"name": "Christian B.", "role": "Shopify-Store mit 3.000 Produkten", "avatar": "CB", "color": "#10b981",
             "result": "3h Setup → 10h/Woche gespart", "duration": "sofort",
             "text": "Produktpflege war mein Vollzeitjob. Jetzt läuft alles automatisch: Preise, Beschreibungen, Kategorien, Lagerbestand. 10 Stunden pro Woche zurückgewonnen."},
            {"name": "Elena K.", "role": "Dropshipping Multi-Store, Wien", "avatar": "EK", "color": "#f59e0b",
             "result": "3 Shops, 1 Dashboard", "duration": "seit Einrichtung",
             "text": "Ich manage drei völlig verschiedene Stores von einem einzigen Dashboard. Bestellungen, Lagersyncs, Preise — alles an einem Ort, alles automatisch."},
            {"name": "Boris M.", "role": "Shopify Agency, Frankfurt", "avatar": "BM", "color": "#8b5cf6",
             "result": "Kunden-Onboarding in 2h", "duration": "statt 2 Tage früher",
             "text": "Früher hat ein Store-Setup 2 Tage gedauert. Mit Shopify Suite Pro ist ein neuer Kunde in 2 Stunden live — mit vollständigem Produktkatalog, SEO und Smart Collections."},
        ],
    },
    "lead-capture": {
        "product": "Lead Capture Pro",
        "icon": "🎯",
        "demo_title": "Lead-Finder Demo",
        "demo_desc": "Finde sofort qualifizierte Leads:",
        "demo_suggestions": [
            "Finde 20 E-Commerce Shops in München die mein Tool brauchen",
            "Scrape LinkedIn für Marketing-Manager in DACH",
            "Erstelle eine Kalt-Email-Sequenz für mein Produkt",
        ],
        "demo_outputs": [
            "✅ <strong>20 E-Commerce Leads gefunden</strong><br>• GreenShop GmbH — 50k€/mo Umsatz, kein CRM<br>• TechGadgets Berlin — Shopify Plus, kein Email-Tool<br>• SportDeal Wien — 15k Kunden, manuelles Fulfillment<br><em>+ 17 weitere Leads mit Kontakt, Umsatzschätzung, Pain Points</em>",
            "✅ <strong>LinkedIn Lead-Export</strong><br>Gefunden: 87 Marketing-Manager in DACH<br>Mit Email: 52 verifiziert<br>Mit Phone: 31 verifiziert<br>In CRM exportiert ✓ | Dauer: 8 Minuten",
            "✅ <strong>5-Email-Sequenz generiert</strong><br>Email 1: Personalisierter Hook (Name + Firma + Pain)<br>Email 2: Case Study (ähnliche Firma + Ergebnis)<br>Email 3: ROI-Kalkulator für ihr Geschäft<br>Email 4: Einwandbehandlung<br>Email 5: Letzter Versuch + Direkttermin-Link",
        ],
        "cases": [
            {"name": "Patrick L.", "role": "B2B-SaaS Startup, München", "avatar": "PL", "color": "#3b82f6",
             "result": "42 Meetings in 30 Tagen", "duration": "sofort nach Setup",
             "text": "Cold Outreach hatte eine Antwortrate von 0.8%. Mit Lead Capture Pro sind es jetzt 11% — personalisierten Nachrichten, richtige Zielgruppe, perfektes Timing."},
            {"name": "Vera S.", "role": "Marketing Agentur, Hamburg", "avatar": "VS", "color": "#ec4899",
             "result": "€45k Neuumsatz/Quartal", "duration": "durch Outreach-Automatisierung",
             "text": "Wir haben unsere Akquise komplett automatisiert. Das System findet, qualifiziert und kontaktiert Leads — mein Team macht nur noch die Abschluss-Calls."},
            {"name": "Robert Z.", "role": "Freelance Copywriter, Wien", "avatar": "RZ", "color": "#059669",
             "result": "Warteliste von 3 Monaten", "duration": "in 8 Wochen aufgebaut",
             "text": "Als Copywriter dachte ich, Outreach sei nicht mein Ding. Lead Capture Pro hat mir gezeigt wie ich Wunschkunden direkt anspreche — jetzt bin ich 3 Monate im Voraus ausgebucht."},
        ],
    },
    "bullpower-hub": {
        "product": "BullPower Hub",
        "icon": "🏆",
        "demo_title": "Hub-Übersicht Demo",
        "demo_desc": "Sieh wie das All-in-One Dashboard funktioniert:",
        "demo_suggestions": [
            "Zeige mir alle Tools auf einen Blick",
            "Was hat mein Business diese Woche verdient?",
            "Starte den kompletten Automatisierungs-Workflow",
        ],
        "demo_outputs": [
            "✅ <strong>12 BullPower Tools — Status Übersicht</strong><br>🟢 BullPower AI: Aktiv (234 Tasks heute)<br>🟢 Shopify Suite: Aktiv (47 Produkte sync.)<br>🟢 Lead Capture: Aktiv (12 neue Leads)<br>🟢 Email Engine: Aktiv (3 Sequences live)<br><em>+ 8 weitere Tools alle grün ✓</em>",
            "✅ <strong>Wochenreport</strong><br>Shopify: €3.420 Umsatz (+12% vs. VW)<br>Affiliate: €890 Provision<br>Leads generiert: 87 | Meetings gebucht: 11<br>Content erstellt: 43 Posts, 5 Emails, 2 Videos<br>Automatisch generiert — kein manueller Aufwand",
            "✅ <strong>Workflow gestartet: Full-Stack Automatisierung</strong><br>→ Shopify Sync läuft (500 Produkte)<br>→ Email-Campaign ausgelöst (1.240 Empfänger)<br>→ Social Posts scheduled (7 Tage)<br>→ Lead-Outreach aktiv (45 neue Kontakte)<br>Geschätzte Zeit manuell: 18h | Mit Hub: 0h",
        ],
        "cases": [
            {"name": "Rudolf S.", "role": "Multi-Channel E-Commerce, Wien", "avatar": "RS", "color": "#f59e0b",
             "result": "€23k MRR durch Automation", "duration": "in 6 Monaten",
             "text": "Ich hatte 6 verschiedene Tools, keines davon sprach miteinander. BullPower Hub hat alles verbunden und automatisiert — mein Business läuft heute 90% ohne mich."},
            {"name": "Katharina N.", "role": "Online Marketing Unternehmerin, München", "avatar": "KN", "color": "#7c3aed",
             "result": "Team von 5 → Solo, gleicher Umsatz", "duration": "nach 3 Monaten",
             "text": "Mein Team hat hauptsächlich repetitive Tasks gemacht. Jetzt macht das Hub alles automatisch — ich spare €15k/Monat an Personalkosten bei gleichem Output."},
            {"name": "Alexander P.", "role": "SaaS Founder, Zürich", "avatar": "AP", "color": "#0ea5e9",
             "result": "12 Monate ROI in Monat 2", "duration": "nach 60 Tagen",
             "text": "Das Hub hat sich in 60 Tagen amortisiert. Durch Automatisierung von 4 Fulltime-Jobs spare ich mehr als den Jahrespreis — jede Woche, auf ewig."},
        ],
    },
    "shopify-acquisition-engine": {
        "product": "Shopify Acquisition Engine",
        "icon": "🚀",
        "demo_title": "Traffic-Analyse Demo",
        "demo_desc": "Sieh wie die Kundenakquise funktioniert:",
        "demo_suggestions": [
            "Finde 500 potenzielle Kunden für meinen Smart Home Shop",
            "Starte eine Facebook-Retargeting-Kampagne",
            "Analysiere warum meine Ads nicht konvertieren",
        ],
        "demo_outputs": [
            "✅ <strong>500 Zielkunden-Profil erstellt</strong><br>Zielgruppe: Smart Home Enthusiasten, 28-45 Jahre, DACH<br>Interessen: Alexa, Google Home, Automatisierung<br>Kaufkraft: €50-300 pro Transaktion<br>Plattformen: Facebook (73%), Pinterest (41%), YouTube (67%)",
            "✅ <strong>Retargeting-Kampagne live</strong><br>Zielgruppe: 1.240 Store-Besucher (keine Kaufhandlung)<br>Budget: €15/Tag automatisch optimiert<br>Anzeigenformat: Karussell + Dynamic Product Ads<br>Erwartete Kosten pro Kauf: €8-14 (Benchmark: €22)",
            "✅ <strong>Ad-Diagnose abgeschlossen</strong><br>❌ Hauptproblem: Landing Page Ladezeit 5.2s auf Mobile<br>❌ Sekundär: Kein Social Proof sichtbar<br>❌ CTA »Mehr erfahren« zu schwach → »Jetzt kaufen« testen<br>Geschätzte Verbesserung nach Fixes: +180% ROAS",
        ],
        "cases": [
            {"name": "Oliver M.", "role": "Shopify Store, 50k€/mo Ziel", "avatar": "OM", "color": "#f97316",
             "result": "von €8k → €41k/Monat", "duration": "in 5 Monaten",
             "text": "Die Acquisition Engine hat mein komplettes Funnel-Setup übernommen. Von der Zielgruppenanalyse bis zum A/B-Test — alles automatisch. Umsatz ×5 in 5 Monaten."},
            {"name": "Martina V.", "role": "Dropshipping, Hannover", "avatar": "MV", "color": "#10b981",
             "result": "ROAS von 1.8 → 5.4", "duration": "nach Optimierung",
             "text": "Meine Facebook-Ads liefen ins Leere. Das System hat in 48h rausgefunden was nicht stimmt, neue Creatives vorgeschlagen und mein ROAS verdreifacht."},
            {"name": "Tobias F.", "role": "E-Commerce Agency, Stuttgart", "avatar": "TF", "color": "#7c3aed",
             "result": "8 Kunden profitabel", "duration": "alle gleichzeitig",
             "text": "Als Agency-Owner manage ich 8 Kunden-Shops — alle mit der Acquisition Engine. Jede Kampagne läuft in einer eigenen Sandbox, keine Interferenz, alles skalierbar."},
        ],
    },
    "cognitive-symphony": {
        "product": "DS24 Pro Suite",
        "icon": "🎯",
        "demo_title": "DS24 Affiliate Demo",
        "demo_desc": "Teste das Affiliate-Automatisierungs-System:",
        "demo_suggestions": [
            "Zeige mir die Top 10 DS24-Produkte mit höchster Provision",
            "Erstelle automatische Affiliate-Links für mein Nische",
            "Analysiere meine DS24-Performance der letzten 30 Tage",
        ],
        "demo_outputs": [
            "✅ <strong>Top 10 DS24 Produkte — Deine Nische</strong><br>1. Online-Marketing Masterclass — 60% Provision, €180/Sale<br>2. Dropshipping Empire Course — 50% Provision, €149/Sale<br>3. KI Tools Business — 55% Provision, €165/Sale<br><em>+ 7 weitere High-Ticket Angebote</em>",
            "✅ <strong>Affiliate-Links generiert</strong><br>Dein Nischen-Deep-Link: ds24.com/redir/668036/aiitec/<br>Landing-Page erstellt: auto-optimiert für Conversion<br>Tracking Pixel: aktiv ✓ | UTM-Parameter: gesetzt ✓",
            "✅ <strong>30-Tage Performance Report</strong><br>Klicks: 1.247 | Verkäufe: 23 | Provision: €3.427<br>Conversion-Rate: 1.84% (Durchschnitt: 1.2%)<br>Top-Traffic: LinkedIn (43%), Email (31%), Organic (26%)<br>Wachstum vs. Vormonat: +34%",
        ],
        "cases": [
            {"name": "Fabian H.", "role": "Affiliate Marketer, Wien", "avatar": "FH", "color": "#7c3aed",
             "result": "€5.800 DS24 Provision/Monat", "duration": "nach 3 Monaten",
             "text": "Ich hatte DS24 schon genutzt aber nie systematisch. Die Pro Suite hat mir gezeigt welche Produkte wirklich konvertieren und wie ich Traffic kanalisiere — €5.800 im dritten Monat."},
            {"name": "Claudia M.", "role": "Online-Lehrerin, München", "avatar": "CM", "color": "#059669",
             "result": "Kurse × 4 skaliert", "duration": "mit DS24 als Partnerprogramm",
             "text": "Ich nutze DS24 nicht nur als Affiliate — ich verkaufe dort meine eigenen Kurse. Die Suite hilft mir Affiliates zu finden und zu managen. Umsatz vervierfacht."},
            {"name": "Lars W.", "role": "Performance Marketer, Berlin", "avatar": "LW", "color": "#f59e0b",
             "result": "12 Clients, alle DS24-profitabel", "duration": "mit einheitlichem System",
             "text": "Ich manage DS24 für 12 Klienten gleichzeitig. Die Pro Suite gibt mir ein einheitliches Dashboard — Tracking, Optimierung, Reports alles an einem Ort."},
        ],
    },
    "digistore24-suite": {
        "product": "Digistore24 Suite",
        "icon": "📊",
        "demo_title": "DS24 Dashboard Demo",
        "demo_desc": "Sieh dein Affiliate-Business im Überblick:",
        "demo_suggestions": [
            "Welche Produkte haben die beste EPC?",
            "Optimiere meine aktuelle Affiliate-Kampagne",
            "Erstelle einen monatlichen Revenue-Report",
        ],
        "demo_outputs": [
            "✅ <strong>Top EPC Analyse</strong><br>Highest EPC: Online Business Mastery — €2.40/Klick<br>Recommended: KI Bootcamp 2026 — €1.87/Klick, hohe Nachfrage<br>Aufsteiger: Smart Home Profit System — Trend +340% diese Woche",
            "✅ <strong>Kampagnen-Optimierung</strong><br>Aktuelle Campaign: Shopify Kurs (CTR: 2.1%)<br>Problem erkannt: Landing-Page Desktop vs. Mobile: -40%<br>Fix deployed: Mobile-optimierte LP ✓<br>Prognose: +60% Conversions in 7 Tagen",
            "✅ <strong>Monatsreport September 2026</strong><br>Total Revenue: €8.420<br>Davon Affiliate-Provision: €5.870<br>Eigene Produkte: €2.550<br>Wachstum: +23% MoM<br>Steuer-Export: DATEV-kompatibel generiert ✓",
        ],
        "cases": [
            {"name": "Nico S.", "role": "Full-Time Affiliate, Graz", "avatar": "NS", "color": "#f59e0b",
             "result": "€7.200 MRR", "duration": "nur durch DS24",
             "text": "Ich teste DS24 seit 2 Jahren. Erst mit der Suite habe ich wirklich verstanden welche Produkte sich lohnen und wie ich skaliere. 7k pro Monat sind jetzt realistisch."},
            {"name": "Iris B.", "role": "Bloggerin + Affiliate, Bern", "avatar": "IB", "color": "#ec4899",
             "result": "4-stellige monatliche Provision", "duration": "ab Monat 4",
             "text": "Als Bloggerin hatte ich Reichweite aber kein System. Die DS24 Suite hat mir geholfen, meine Inhalte in eine Affiliate-Maschine zu verwandeln."},
            {"name": "Martin G.", "role": "Online Business Mentor, Berlin", "avatar": "MG", "color": "#3b82f6",
             "result": "Empfehle DS24 Suite allen Mentees", "duration": "als Standard-Tool",
             "text": "Ich empfehle die Suite jedem meiner Mentees als ersten Schritt. Kein anderes Tool gibt so schnell einen Überblick was funktioniert und was nicht."},
        ],
    },
    "creatorstudio-pro": {
        "product": "CreatorStudio Pro",
        "icon": "🎬",
        "demo_title": "Studio Demo",
        "demo_desc": "Erstelle professionellen Content in Sekunden:",
        "demo_suggestions": [
            "Generiere ein komplettes YouTube-Skript über Smart Home",
            "Erstelle 30 Tage Social Media Content für Instagram",
            "Schreibe eine Sales-Email-Sequenz für mein Produkt",
        ],
        "demo_outputs": [
            "✅ <strong>YouTube Skript: 10min Video</strong><br>Titel: »5 Smart Home Gadgets die 2026 EXPLODIEREN werden 🔥«<br>Intro + Hook: 45 Sek. (A/B Variante erzeugt)<br>Content-Blöcke: 5 × 90 Sek.<br>CTA + Outro: 60 Sek.<br>SEO-Tags: 15 high-volume Keywords eingefügt",
            "✅ <strong>Instagram 30-Tage Plan</strong><br>• 12× Reels (Trending Audio vorgeschlagen)<br>• 8× Karussell Posts (Eduational)<br>• 6× Story-Serien<br>• 4× Collaboration-Anfragen vorbereitet<br>Posting-Zeiten: KI-optimiert für Deine Follower",
            "✅ <strong>7-Email Willkommens-Sequenz</strong><br>Email 1 (sofort): Begrüßung + Quick Win<br>Email 2 (Tag 2): Deine Geschichte (Vertrauen)<br>Email 3 (Tag 4): Hauptangebot (soft pitch)<br>Email 4 (Tag 7): Case Study<br>Email 5-7: Nurture + Hard Offer<br>Öffnungsrate Prognose: 38-45%",
        ],
        "cases": [
            {"name": "Emma L.", "role": "YouTuberin, München (28k Abonnenten)", "avatar": "EL", "color": "#ec4899",
             "result": "Video-Output verdoppelt", "duration": "ohne Mehranstrengung",
             "text": "Ich erstelle jetzt 2 Videos pro Woche statt einer — weil das Skripting nur noch 20 Minuten dauert. CreatorStudio macht den Entwurf, ich verfeinere, publish."},
            {"name": "Kevin P.", "role": "Business Podcaster, Wien", "avatar": "KP", "color": "#8b5cf6",
             "result": "Show Notes + Clips automatisch", "duration": "seit Episode 1",
             "text": "Jede Podcast-Episode liefert automatisch Show Notes, 5 Social Clips, einen Blog-Artikel und 3 Email-Teasers. Ein Recording, 10× Content-Output."},
            {"name": "Stephanie K.", "role": "Online-Kurse Anbieterin, Hamburg", "avatar": "SK", "color": "#06b6d4",
             "result": "€18.000 Launch-Umsatz", "duration": "mit KI-generiertem Content",
             "text": "Für meinen Kurs-Launch hat CreatorStudio alle Texte, Emails, Social Posts und die Sales Page geschrieben. Launch war der erfolgreichste meiner Karriere."},
        ],
    },
    "gumroad-discord": {
        "product": "Gumroad Discord Community",
        "icon": "🎮",
        "demo_title": "Community Demo",
        "demo_desc": "Sieh wie die Community + Monetisierung funktioniert:",
        "demo_suggestions": [
            "Wie viel verdiene ich mit einer Discord Community?",
            "Erstelle einen Membership-Plan für meine Nische",
            "Zeige mir die Top-Monetisierungsstrategien",
        ],
        "demo_outputs": [
            "✅ <strong>Community Earnings Kalkulator</strong><br>Angenommen: 200 Members × €29/mo = €5.800/mo<br>Gumroad-Gebühr: 10% = €580<br>Netto: €5.220/mo | Jahresumsatz: €62.640<br>Realistische Wachstumskurve: 200 Members in 4-6 Monaten",
            "✅ <strong>Membership-Struktur für deine Nische</strong><br>Free (Lead Magnet): Zugang zu #allgemein<br>Starter (€19/mo): 3 exklusive Channels + Ressourcen<br>Pro (€49/mo): VIP Channel + monatlicher Q&A Call<br>Elite (€149/mo): 1:1 Calls + alle Produkte inklusive",
            "✅ <strong>Top 5 Monetisierungs-Wege</strong><br>1. Membership Tiers (recurring revenue)<br>2. Digitale Produkte im Shop (einmalig)<br>3. Affiliate-Deals mit Partnern (30-50%)<br>4. Gesponserte Posts (€500-2k/post ab 1k Member)<br>5. Exklusive Workshops/Webinare (€97-297/Ticket)",
        ],
        "cases": [
            {"name": "Daniel H.", "role": "E-Commerce Community, Berlin", "avatar": "DH", "color": "#7c3aed",
             "result": "€3.200/Monat Community", "duration": "mit 127 Members",
             "text": "Ich dachte eine bezahlte Community wäre schwer aufzubauen. Aber mit dem richtigen System und echtem Mehrwert waren die ersten 50 Members in 3 Wochen da — und die zahlen gerne."},
            {"name": "Sophie W.", "role": "Freelance Coach, Wien", "avatar": "SW", "color": "#10b981",
             "result": "Passives Einkommen + Kunden", "duration": "die Community bringt beides",
             "text": "Meine Community ist mein bester Verkaufskanal. 30% meiner Premium-Coaching-Klienten kommen aus der Discord-Community — die haben mich schon kennengelernt und vertrauen mir."},
            {"name": "Niklas R.", "role": "Tech Creator, München", "avatar": "NR", "color": "#f59e0b",
             "result": "Von gratis zu €49/mo erfolgreich", "duration": "in 60 Tagen migriert",
             "text": "Ich hatte 800 gratis-Member. Nach der Migration zu Gumroad Paid blieben 180 — das macht €8.820/Monat. Die anderen 620 hätten mir sowieso nie etwas gebracht."},
        ],
    },
    "icomeauto": {
        "product": "IcomeAuto OS",
        "icon": "⚙️",
        "demo_title": "Automation Demo",
        "demo_desc": "Automatisiere dein gesamtes Online-Business:",
        "demo_suggestions": [
            "Setze mein komplettes Business auf Autopilot",
            "Synchronisiere alle meine Plattformen automatisch",
            "Erstelle meinen täglichen Revenue-Report",
        ],
        "demo_outputs": [
            "✅ <strong>Business Autopilot aktiviert</strong><br>Tägliche Routinen automatisiert:<br>• 08:00: Shopify Bestandscheck + Reorder-Trigger<br>• 10:00: Social Media Posting (3 Platforms)<br>• 14:00: Email Kampagne versandt<br>• 20:00: Tagesreport generiert<br>Manuelle Arbeit heute: 0 Stunden",
            "✅ <strong>Platform-Sync abgeschlossen</strong><br>Shopify ↔ Gumroad: 47 Produkte synchron ✓<br>Stripe ↔ Klaviyo: 234 neue Kontakte übertragen ✓<br>DS24 ↔ CRM: 12 neue Affiliates eingetragen ✓<br>Telegram ↔ Dashboard: 8 neue Subscriber ✓",
            "✅ <strong>Tagesreport — Heute</strong><br>💰 Revenue: €847 (Shopify €612 + Gumroad €185 + DS24 €50)<br>📧 Emails versendet: 1.240 | Öffnungsrate: 34%<br>🛒 Neue Bestellungen: 23 | Ø €36,82<br>👥 Neue Leads: 14 | Conversion-Rate: 2.1%",
        ],
        "cases": [
            {"name": "Bernd K.", "role": "Multi-Plattform Händler, Hamburg", "avatar": "BK", "color": "#059669",
             "result": "4 Plattformen, 0 manueller Aufwand", "duration": "seit IcomeAuto",
             "text": "Ich betreibe Shopify, Gumroad, eBay und Etsy gleichzeitig. Früher war das ein Vollzeitjob. Jetzt synchronisiert IcomeAuto alles — ich schaue nur noch die Berichte an."},
            {"name": "Hannah M.", "role": "Solopreneurin, Wien", "avatar": "HM", "color": "#ec4899",
             "result": "Business skaliert, Urlaub gemacht", "duration": "3 Wochen offline",
             "text": "Ich war 3 Wochen im Urlaub ohne Laptop. IcomeAuto hat mein Business komplett geführt — als ich zurückkam, lag ein Monatsreport mit €12.400 Umsatz auf mich."},
            {"name": "Carsten L.", "role": "E-Commerce Investor, Frankfurt", "avatar": "CL", "color": "#3b82f6",
             "result": "Portfolio von 5 Shops verwaltet", "duration": "als ein-Mann-Betrieb",
             "text": "Ich habe 5 verschiedene Online-Shops. Mit IcomeAuto läuft alles von einem einzigen Ort — kein Wechseln zwischen Tabs, keine vergessenen Updates, keine Umsatzverluste."},
        ],
    },
    "launcher": {
        "product": "BullPower Launcher",
        "icon": "🚀",
        "demo_title": "Launch Demo",
        "demo_desc": "Dein Produkt-Launch in 60 Minuten:",
        "demo_suggestions": [
            "Starte einen kompletten Produkt-Launch für meinen Kurs",
            "Erstelle meine Launch-Email-Sequenz",
            "Generiere alle Launch-Assets automatisch",
        ],
        "demo_outputs": [
            "✅ <strong>Launch-Plan generiert</strong><br>Pre-Launch (7 Tage): Email-Warming + Social Tease<br>Launch-Tag: Countdown + 3 Emails + Live-Post<br>Post-Launch (3 Tage): Follow-up + Last Chance<br>Geschätzter Umsatz bei 500er Liste: €2.400-8.900",
            "✅ <strong>Email-Sequenz (7 Emails) fertig</strong><br>Email 1: »Etwas Besonderes kommt...« (Neugier)<br>Email 2: »Ich zeige dir was ich gebaut habe«<br>Email 3: »Early Bird Angebot — 40% Rabatt«<br>Email 4-7: Urgency + Testimonials + FAQ + Last Call",
            "✅ <strong>Launch-Assets erstellt</strong><br>Sales Page: Texte + Headlines + FAQ ✓<br>Social Posts: 14 Pieces (Countdown + Launch + Testimonials) ✓<br>Anzeigen-Texte: 6 Variationen für A/B-Test ✓<br>Affiliate-Kit: Swipe Files für Promoter ✓",
        ],
        "cases": [
            {"name": "Jasmin T.", "role": "Kurs-Anbieterin, Graz", "avatar": "JT", "color": "#ec4899",
             "result": "€14.700 Launch-Umsatz", "duration": "in 5 Tagen",
             "text": "Mein vorheriger Launch war mit €2.100 okay. Mit BullPower Launcher war es €14.700 — gleiche Liste, gleicher Kurs, aber ein komplett professionelles Launch-System."},
            {"name": "Stefan B.", "role": "Info-Product Creator, Berlin", "avatar": "SB", "color": "#7c3aed",
             "result": "Von 0 auf €8k in 14 Tagen", "duration": "erster Launch überhaupt",
             "text": "Ich hatte noch nie ein Produkt gelauncht. Der Launcher hat mir alles gezeigt — was ich schreibe, wann ich sende, wie ich Dringlichkeit erzeuge. €8k im ersten Anlauf."},
            {"name": "Petra L.", "role": "Online-Coach, München", "avatar": "PL", "color": "#059669",
             "result": "4 erfolgreiche Launches", "duration": "in einem Jahr",
             "text": "Ich launche jetzt vierteljährlich — weil es so einfach geworden ist. Launcher generiert alle Assets, ich brauche nur noch abzusegnen. 4 Launches, 4 fünfstellige Ergebnisse."},
        ],
    },
    "master-dashboard": {
        "product": "Master Dashboard",
        "icon": "📊",
        "demo_title": "Dashboard Demo",
        "demo_desc": "Sieh dein gesamtes Business auf einen Blick:",
        "demo_suggestions": [
            "Zeige mir meinen Business Health Score",
            "Was sind meine Top Revenue-Quellen diese Woche?",
            "Wo verliere ich am meisten Geld?",
        ],
        "demo_outputs": [
            "✅ <strong>Business Health Score: 84/100</strong><br>✅ Revenue-Wachstum: +23% (sehr gut)<br>⚠️ Email-Öffnungsrate: 21% (unter Benchmark 34%)<br>✅ Churn-Rate: 2.1% (gut)<br>❌ Warenkorbabbrüche: 78% (kritisch → Sofort-Fix verfügbar)",
            "✅ <strong>Top Revenue-Quellen diese Woche</strong><br>1. Shopify: €3.847 (52%)<br>2. Affiliate DS24: €1.240 (17%)<br>3. Telegram Subscriptions: €890 (12%)<br>4. Gumroad Produkte: €640 (9%)<br>5. B2B Outreach: €800 (11%)",
            "✅ <strong>Verlust-Analyse</strong><br>🔴 Warenkorbabbrüche: €4.200/Monat verloren (78% Rate)<br>🔴 Ungeöffnete Emails: €890/Monat verpasst<br>🔴 Ungenutzter Traffic (Bounce): €1.240/Monat Potenzial<br>Quick-Wins: 3 Fixes → geschätzte Verbesserung +€3.100/Monat",
        ],
        "cases": [
            {"name": "Andreas F.", "role": "E-Commerce Unternehmer, Wien", "avatar": "AF", "color": "#3b82f6",
             "result": "Stille Verluste entdeckt: €4.200/Monat", "duration": "sofort sichtbar",
             "text": "Ich dachte mein Business läuft gut. Das Master Dashboard hat in der ersten Woche einen Warenkorb-Abbruchproblem gefunden das mich €4.200 pro Monat kostet — jetzt ist es gefixt."},
            {"name": "Christine S.", "role": "SaaS-Gründerin, München", "avatar": "CS", "color": "#8b5cf6",
             "result": "Churn von 8% auf 2.1% reduziert", "duration": "in 6 Wochen",
             "text": "Das Dashboard hat mir gezeigt welche Nutzer kurz vor dem Churn stehen. Wir haben automatische Eingriffe eingebaut — Churn um 75% reduziert in 6 Wochen."},
            {"name": "Florian W.", "role": "Multi-Channel Händler, Zürich", "avatar": "FW", "color": "#059669",
             "result": "Revenue-Mix optimiert", "duration": "von 1 auf 5 Quellen",
             "text": "Früher war alles auf Shopify konzentriert. Das Dashboard hat mir gezeigt, dass DS24 und Telegram fast nichts kosten aber enorm performen — jetzt sind es 5 Revenue-Quellen."},
        ],
    },
}

CSS_INJECT = """
  /* CASE STUDIES */
  .cs-section { padding: 80px 2rem; position: relative; z-index: 1; background: var(--dark2, #12121a); border-top: 1px solid var(--border, #2d2d45); border-bottom: 1px solid var(--border, #2d2d45); }
  .cs-inner { max-width: 1200px; margin: 0 auto; }
  .cs-tag { display: inline-block; background: rgba(124,58,237,0.12); border: 1px solid rgba(124,58,237,0.35); color: #a855f7; padding: 0.3rem 0.9rem; border-radius: 20px; font-size: 0.8rem; font-weight: 700; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .cs-title { font-size: clamp(1.8rem,3vw,2.5rem); font-weight: 900; margin-bottom: 0.8rem; }
  .cs-desc { color: var(--text-muted,#94a3b8); font-size: 1rem; max-width: 600px; line-height: 1.7; margin-bottom: 3rem; }
  .cs-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1.5rem; }
  .cs-card { background: var(--card,#1e1e30); border: 1px solid var(--border,#2d2d45); border-radius: 18px; padding: 1.8rem; transition: transform .25s, border-color .25s, box-shadow .25s; }
  .cs-card:hover { transform: translateY(-5px); border-color: rgba(124,58,237,0.4); box-shadow: 0 16px 40px rgba(124,58,237,0.15); }
  .cs-result { display: inline-block; background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.3); color: #10b981; padding: 0.35rem 0.9rem; border-radius: 8px; font-size: 0.85rem; font-weight: 700; margin-bottom: 0.4rem; }
  .cs-duration { font-size: 0.8rem; color: var(--text-muted,#94a3b8); margin-bottom: 1rem; }
  .cs-text { font-size: 0.92rem; color: var(--text-muted,#94a3b8); line-height: 1.7; margin-bottom: 1.4rem; font-style: italic; }
  .cs-author { display: flex; align-items: center; gap: 0.8rem; }
  .cs-avatar { width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: 800; color: #fff; flex-shrink: 0; }
  .cs-name { font-weight: 700; font-size: 0.9rem; }
  .cs-role { font-size: 0.78rem; color: var(--text-muted,#94a3b8); }
  /* LIVE DEMO SECTION */
  .demo-inject { padding: 80px 2rem; position: relative; z-index: 1; }
  .demo-inject-inner { max-width: 900px; margin: 0 auto; }
  .demo-tag { display: inline-block; background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); color: #60a5fa; padding: 0.3rem 0.9rem; border-radius: 20px; font-size: 0.8rem; font-weight: 700; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .demo-inject-title { font-size: clamp(1.8rem,3vw,2.5rem); font-weight: 900; margin-bottom: 0.8rem; text-align: center; }
  .demo-inject-desc { color: var(--text-muted,#94a3b8); font-size: 1rem; text-align: center; margin-bottom: 2.5rem; }
  .demo-box { background: var(--card,#1e1e30); border: 1px solid var(--border,#2d2d45); border-radius: 18px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.4); }
  .demo-box-header { background: var(--dark3,#1a1a28); padding: 1rem 1.4rem; display: flex; align-items: center; gap: 0.6rem; border-bottom: 1px solid var(--border,#2d2d45); }
  .demo-traffic-lights { display: flex; gap: 0.4rem; }
  .dtl { width: 12px; height: 12px; border-radius: 50%; }
  .dtl-r { background: #ff5f57; }
  .dtl-y { background: #ffbd2e; }
  .dtl-g { background: #28ca41; }
  .demo-box-title { font-size: 0.85rem; color: var(--text-muted,#94a3b8); margin-left: 0.4rem; }
  .demo-suggestions-inject { display: flex; flex-direction: column; gap: 0.6rem; padding: 1.2rem 1.4rem; border-bottom: 1px solid var(--border,#2d2d45); background: rgba(0,0,0,0.2); }
  .demo-sug-label { font-size: 0.75rem; color: var(--text-muted,#94a3b8); margin-bottom: 0.2rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .demo-sug-btn { background: var(--dark3,#1a1a28); border: 1px solid var(--border,#2d2d45); border-radius: 8px; padding: 0.6rem 1rem; font-size: 0.85rem; color: var(--text-muted,#94a3b8); cursor: pointer; text-align: left; transition: all .2s; font-family: inherit; width: 100%; }
  .demo-sug-btn:hover { border-color: #60a5fa; color: #e2e8f0; background: rgba(59,130,246,0.08); }
  .demo-output-area { min-height: 160px; padding: 1.4rem; font-size: 0.9rem; line-height: 1.7; color: var(--text,#e2e8f0); }
  .demo-output-area.empty { color: var(--text-muted,#94a3b8); font-style: italic; }
  .demo-input-row { display: flex; gap: 0.6rem; padding: 1rem 1.4rem; background: var(--dark3,#1a1a28); border-top: 1px solid var(--border,#2d2d45); }
  .demo-text-input { flex: 1; background: var(--dark2,#12121a); border: 1px solid var(--border,#2d2d45); border-radius: 8px; padding: 0.65rem 1rem; color: var(--text,#e2e8f0); font-size: 0.88rem; outline: none; font-family: inherit; transition: border-color .2s; }
  .demo-text-input:focus { border-color: #60a5fa; }
  .demo-run-btn { background: linear-gradient(135deg,#3b82f6,#6366f1); border: none; color: #fff; padding: 0.65rem 1.3rem; border-radius: 8px; font-size: 0.88rem; font-weight: 700; cursor: pointer; font-family: inherit; transition: opacity .2s, transform .2s; white-space: nowrap; }
  .demo-run-btn:hover { opacity: 0.88; transform: translateY(-1px); }
  @media (max-width: 768px) { .cs-grid { grid-template-columns: 1fr; } }
"""

def build_case_studies_html(cfg):
    cards = ""
    for c in cfg["cases"]:
        cards += f"""
    <div class="cs-card">
      <div class="cs-result">{c['result']}</div>
      <div class="cs-duration">{c['duration']}</div>
      <p class="cs-text">{c['text']}</p>
      <div class="cs-author">
        <div class="cs-avatar" style="background:{c['color']}">{c['avatar']}</div>
        <div>
          <div class="cs-name">{c['name']}</div>
          <div class="cs-role">{c['role']}</div>
        </div>
      </div>
    </div>"""
    return f"""
<!-- CASE STUDIES -->
<section class="cs-section" id="case-studies">
  <div class="cs-inner">
    <div class="cs-tag">Erfolgsgeschichten</div>
    <h2 class="cs-title">Echte Ergebnisse. Echte Kunden.</h2>
    <p class="cs-desc">Sieh was andere mit {cfg['product']} erreicht haben — und was für dich möglich ist.</p>
    <div class="cs-grid">{cards}
    </div>
  </div>
</section>
"""

def build_demo_html(cfg, demo_id):
    sugs = "".join(
        f'<button class="demo-sug-btn" onclick="injectDemoRun{demo_id}({i})">{s}</button>'
        for i, s in enumerate(cfg["demo_suggestions"])
    )
    outputs_js = str(cfg["demo_outputs"]).replace("`", "'").replace("\\", "\\\\")
    return f"""
<!-- INTERACTIVE DEMO -->
<section class="demo-inject" id="demo">
  <div class="demo-inject-inner">
    <div style="text-align:center"><div class="demo-tag">Live Demo</div></div>
    <h2 class="demo-inject-title">{cfg['icon']} {cfg['demo_title']}</h2>
    <p class="demo-inject-desc">{cfg['demo_desc']}</p>
    <div class="demo-box">
      <div class="demo-box-header">
        <div class="demo-traffic-lights"><div class="dtl dtl-r"></div><div class="dtl dtl-y"></div><div class="dtl dtl-g"></div></div>
        <span class="demo-box-title">{cfg['product']} — Interaktive Demo</span>
      </div>
      <div class="demo-suggestions-inject">
        <div class="demo-sug-label">Schnell ausprobieren — klick einfach:</div>
        {sugs}
      </div>
      <div class="demo-output-area empty" id="demoOut{demo_id}">Wähle eine Beispiel-Anfrage oben oder schreibe deine eigene...</div>
      <div class="demo-input-row">
        <input class="demo-text-input" id="demoIn{demo_id}" type="text" placeholder="Eigene Anfrage eingeben...">
        <button class="demo-run-btn" onclick="injectDemoCustom{demo_id}()">Ausführen ▶</button>
      </div>
    </div>
  </div>
</section>
<script>
(function(){{
  var OUTPUTS{demo_id} = {repr(cfg['demo_outputs'])};
  var el = document.getElementById('demoOut{demo_id}');
  window.injectDemoRun{demo_id} = function(i) {{
    el.classList.remove('empty');
    el.innerHTML = '<div style="color:#60a5fa;font-size:0.8rem;margin-bottom:0.5rem">⚡ Verarbeite...</div>';
    setTimeout(function() {{ el.innerHTML = OUTPUTS{demo_id}[i]; }}, 600);
  }};
  window.injectDemoCustom{demo_id} = function() {{
    var v = document.getElementById('demoIn{demo_id}').value.trim();
    if (!v) return;
    el.classList.remove('empty');
    el.innerHTML = '<div style="color:#60a5fa;font-size:0.8rem;margin-bottom:0.5rem">⚡ Analysiere: ' + v.substring(0,60) + '...</div>';
    setTimeout(function() {{ el.innerHTML = OUTPUTS{demo_id}[Math.floor(Math.random()*OUTPUTS{demo_id}.length)]; }}, 800);
  }};
  document.getElementById('demoIn{demo_id}').addEventListener('keypress', function(e) {{
    if (e.key === 'Enter') window.injectDemoCustom{demo_id}();
  }});
}})();
</script>
"""

def inject_css(html, css):
    """Füge CSS vor </style> ein (letztes Vorkommen im Head)."""
    idx = html.rfind("</style>")
    if idx == -1:
        idx = html.find("</head>")
        if idx == -1:
            return html
        return html[:idx] + f"<style>{css}</style>" + html[idx:]
    return html[:idx] + css + html[idx:]

def inject_before_footer(html, content):
    """Füge content vor dem ersten <footer tag ein."""
    idx = html.find("<footer")
    if idx == -1:
        idx = html.find("</body>")
        if idx == -1:
            return html + content
    return html[:idx] + content + html[idx:]

def already_has(html, marker):
    return marker in html

def process():
    dirs = [d for d in os.listdir(NETLIFY)
            if os.path.isdir(os.path.join(NETLIFY, d)) and d != "DEPLOYED_URLS.md"]
    updated = 0
    skipped = 0
    for d in sorted(dirs):
        path = os.path.join(NETLIFY, d, "index.html")
        if not os.path.exists(path):
            continue
        cfg = CONFIGS.get(d)
        if not cfg:
            print(f"  SKIP (kein Config): {d}")
            skipped += 1
            continue
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        changed = False
        if not already_has(html, "cs-section"):
            cs_html = build_case_studies_html(cfg)
            demo_html = build_demo_html(cfg, d.replace("-", "_"))
            html = inject_css(html, CSS_INJECT)
            html = inject_before_footer(html, cs_html + demo_html)
            changed = True
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  ✅ Updated: {d}")
            updated += 1
        else:
            print(f"  — Bereits aktuell: {d}")
    print(f"\nFertig: {updated} Seiten aktualisiert, {skipped} übersprungen.")

if __name__ == "__main__":
    process()
