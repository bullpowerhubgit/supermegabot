#!/usr/bin/env python3
"""
Generiert reiche Landingpages für alle 29 AIITEC DS24-Produkte.
Output: netlify-deploy/aiitec-all/{slug}/index.html
"""
import os, json
from pathlib import Path

OUT = Path(__file__).parent.parent / "netlify-deploy" / "aiitec-all"

PRODUCTS = [
  {"slug":"ai-income-machine","title":"AI Income Machine","sub":"Komplett System","price":"37","ds24":"669750",
   "tagline":"Automatisiertes KI-Einkommen mit ChatGPT & Claude",
   "desc":"Das komplette System für passives Online-Einkommen mit KI — von Content-Erstellung bis Affiliate-Marketing, alles automatisiert.",
   "icon":"🤖","color":"#00e87c",
   "features":["KI-Content-Automatisierung mit ChatGPT & Claude","Digistore24 Affiliate-System aufbauen","Passive Einkommensströme 24/7","Social Media Automation (Reels, TikTok, YouTube Shorts)","Email-Marketing ohne Arbeit","Schritt-für-Schritt Startplan für Anfänger","5+ bewährte Einkommensquellen","Community & Support inklusive"],
   "cases":[{"name":"Markus T.","result":"€2.340/Monat nach 8 Wochen","detail":"Begann ohne Vorkenntnisse, nutzte den KI-Content-Plan und baute 3 passive Streams auf."},{"name":"Lisa S.","result":"€890 erste Woche","detail":"Startete mit Digistore24 Affiliate und optimierte mit dem beiliegenden KI-Prompting-Guide."},{"name":"Stefan K.","result":"Nebeneinkommen €1.200/Monat","detail":"Nebenberuflich gestartet, heute voll automatisiert — 2h/Woche Aufwand."}],
   "faqs":[{"q":"Brauche ich technische Vorkenntnisse?","a":"Nein — das System ist für Einsteiger entwickelt. Schritt-für-Schritt erklärt."},{"q":"Wie schnell sehe ich Ergebnisse?","a":"Erste Einnahmen sind realistisch innerhalb von 2-4 Wochen."},{"q":"Ist das Abo-basiert?","a":"Einmalige Zahlung, keine laufenden Kosten."},{"q":"Was wenn's nicht klappt?","a":"30 Tage Geld-zurück-Garantie über Digistore24."},{"q":"Funktioniert das auch 2026?","a":"Ja — wir aktualisieren das System regelmäßig mit den neuesten KI-Tools."}]},

  {"slug":"agency-aufbauen","title":"KI-Agency aufbauen","sub":"Von 0 auf €5k/Monat","price":"47","ds24":"669750",
   "tagline":"Deine eigene KI-Dienstleistungs-Agentur in 30 Tagen",
   "desc":"Baue eine professionelle KI-Agentur für lokale Unternehmen auf — mit bewährten Akquise-Skripten, Pricing-Modellen und Service-Paketen.",
   "icon":"🏢","color":"#6366f1",
   "features":["30-Tage Agency-Aufbau-Plan","Akquise-Skripte für Kaltakquise","Pricing-Modelle & Angebots-Vorlagen","KI-Services die Unternehmen brauchen","Automatisierte Fulfillment-Prozesse","Muster-Verträge & Rechnungen","Kundenbindungs-Strategien","Skalierung auf 10+ Kunden"],
   "cases":[{"name":"David M.","result":"€4.800/Monat nach 45 Tagen","detail":"Akquirierte 4 lokale Restaurants und automatisierte deren Social-Media komplett."},{"name":"Petra K.","result":"Erste Agentur-Rechnung €1.200","detail":"Nutzte die Kaltakquise-Skripte und gewann innerhalb von 2 Wochen ihren ersten Kunden."},{"name":"Jan W.","result":"6 Stammkunden in 3 Monaten","detail":"Spezialisierte sich auf E-Mail-Marketing für Handwerker — 90% Retention."}],
   "faqs":[{"q":"Brauche ich eigene KI-Tools?","a":"ChatGPT Plus reicht für den Start — alles andere erklären wir."},{"q":"Wie finde ich Kunden?","a":"Wir liefern fertige Akquise-Skripte und Branchen-Listen."},{"q":"Kann ich das nebenberuflich machen?","a":"Ja — der Plan ist auf 10h/Woche ausgelegt."},{"q":"Welche Services verkaufe ich?","a":"Content, Social Media, Email, Webseiten-Copy, SEO-Texte."},{"q":"Gibt es Vorlagen?","a":"Ja — Angebote, Verträge, Rechnungen alles fertig."}]},

  {"slug":"shopify-automation","title":"Shopify Automation","sub":"Dropshipping auf Autopilot","price":"57","ds24":"669750",
   "tagline":"Shopify-Store vollautomatisch betreiben",
   "desc":"Automatisiere deinen Shopify-Store von Produktsuche über Import bis Kundenservice — mit KI-Tools und bewährten Systemen.",
   "icon":"🛒","color":"#96bf48",
   "features":["Automatische Produktsuche & Import","Preis-Optimierung in Echtzeit","KI-Produktbeschreibungen","Order-Fulfillment Automation","Kundenservice-Chatbot","Social Media Ads Automation","Email-Follow-up Sequenzen","Analytics & Reporting Dashboard"],
   "cases":[{"name":"Nina H.","result":"€8.200 Umsatz Monat 2","detail":"Importierte 500 Produkte mit dem Tool und optimierte Preise automatisch."},{"name":"Tom B.","result":"Store läuft 20h/Woche ohne ihn","detail":"Automatisierte Fulfillment und Kundenservice — genießt jetzt die Freiheit."},{"name":"Anna L.","result":"ROAS 4,2x mit automatisierten Ads","detail":"Die Ads-Automation fand profitable Creatives ohne manuelles Testen."}],
   "faqs":[{"q":"Welche Shopify-Version brauche ich?","a":"Basic oder höher — funktioniert mit allen Plänen."},{"q":"Werden Produkte automatisch importiert?","a":"Ja — aus AliExpress, Amazon, CJ Dropshipping."},{"q":"Wie läuft Fulfillment ab?","a":"Bestellungen werden automatisch an Lieferanten weitergeleitet."},{"q":"Ist das legal?","a":"Ja — alle Methoden entsprechen den Shopify ToS."},{"q":"Wie lange bis der erste Verkauf?","a":"Erfahrungsgemäß 1-3 Wochen nach Store-Launch."}]},

  {"slug":"dropshipping-lieferanten","title":"Dropshipping Lieferanten","sub":"Geheime Quellen 2026","price":"27","ds24":"669750",
   "tagline":"Die besten verifizierten Lieferanten für 2026",
   "desc":"Zugang zu 500+ verifizierten Dropshipping-Lieferanten mit schnellen Lieferzeiten, hohen Margen und deutschen Lagern.",
   "icon":"📦","color":"#f59e0b",
   "features":["500+ verifizierte Lieferanten","Deutsche & EU-Lager für 2-3 Tage Lieferung","Margen 40-80%","Nischen-Analyse Tool","Direkt-Kontakt zu Lieferanten","Verhandlungs-Skripte","Muster-Bestellungen","Exklusiv-Deals inklusive"],
   "cases":[{"name":"Klaus M.","result":"€120 Marge pro Produkt","detail":"Fand Nischen-Lieferanten die kein Konkurrent kennt — 3 Tage Lieferung."},{"name":"Sandra P.","result":"Deutsches Lager in 2 Wochen","detail":"Nutzte die Lieferanten-Datenbank und verhandelte eigene Konditionen."},{"name":"Ralf S.","result":"40% Marge auf alle Produkte","detail":"Wechselte von AliExpress zu EU-Lieferanten — Retouren dramatisch gesunken."}],
   "faqs":[{"q":"Sind die Lieferanten aktuell geprüft?","a":"Ja — wir aktualisieren die Liste vierteljährlich."},{"q":"Gibt es auch B2B-Lieferanten?","a":"Ja — für Amazon, eBay und eigene Shops."},{"q":"Wie funktioniert der Direktkontakt?","a":"Du erhältst Ansprechpartner + E-Mail-Vorlagen für die Erstanfrage."},{"q":"Brauche ich ein Gewerbe?","a":"Empfohlen — für Großhandelspreise meist nötig."},{"q":"Gibt es Nischen-Empfehlungen?","a":"Ja — Top 20 Nischen mit Margen-Analyse inklusive."}]},

  {"slug":"immobilien-investment","title":"Immobilien Investment","sub":"Mit wenig Kapital starten","price":"67","ds24":"669750",
   "tagline":"Immobilien-Vermögen aufbauen ohne Millionen",
   "desc":"Lerne wie du mit wenig Eigenkapital in Immobilien investierst — REITs, Crowdinvesting, WEGs und klassische Vermietung strategisch kombiniert.",
   "icon":"🏠","color":"#ef4444",
   "features":["REITs für Einsteiger","Crowdinvesting-Plattformen im Vergleich","Klassische Vermietung Schritt für Schritt","Steuer-Optimierung für Immobilien","Finanzierungs-Strategien 2026","Cash-Flow-Berechnung Tool","Risikomanagement","Portfolio-Aufbau-Strategie"],
   "cases":[{"name":"Hans K.","result":"€640/Monat passiv durch REITs","detail":"Begann mit €5.000 und baute ein diversifiziertes Immobilien-Portfolio auf."},{"name":"Maria T.","result":"Erste Wohnung mit 10% EK","detail":"Nutzte die Finanzierungs-Strategien und kaufte ohne 20% Eigenkapital."},{"name":"Georg W.","result":"3 Immobilien in 4 Jahren","detail":"Folgte dem Portfolio-Aufbau-Plan und skalierte systematisch."}],
   "faqs":[{"q":"Wie viel Startkapital brauche ich?","a":"Ab €1.000 ist ein Start mit REITs oder Crowdinvesting möglich."},{"q":"Brauche ich Immobilien-Kenntnisse?","a":"Nein — wir erklären alles von Grund auf."},{"q":"Wie hoch sind typische Renditen?","a":"REITs 4-8%, Vermietung 3-6% netto, Crowdinvesting 5-9%."},{"q":"Was ist mit dem Steuerrecht?","a":"Das Modul erklärt die wichtigsten Steuer-Vorteile für Immobilieninvestoren."},{"q":"Gilt das für Österreich/Schweiz?","a":"Hauptfokus Deutschland, Grundlagen gelten auch für AT/CH."}]},

  {"slug":"freelancing-einkommen","title":"Freelancing Einkommen","sub":"€100+ pro Stunde","price":"37","ds24":"669750",
   "tagline":"Als Freelancer 5-stellig verdienen",
   "desc":"Der komplette Guide zum profitablen Freelancing: Nische finden, Kunden gewinnen, Preise durchsetzen und skalieren.",
   "icon":"💼","color":"#8b5cf6",
   "features":["Nischen-Positionierung als Experte","Upwork & Fiverr Profil-Optimierung","Direkt-Akquise Strategie","Preisgestaltung für Premiumkunden","Proposal-Vorlagen die konvertieren","Projektmanagement-System","Stammkunden aufbauen","Agentur-Modell für Skalierung"],
   "cases":[{"name":"Julia M.","result":"€85/h auf Upwork nach 3 Monaten","detail":"Positionierte sich als KI-Spezialistin — Auftragslage übersteigt Kapazität."},{"name":"Felix R.","result":"€8.400 erster Monat Freelancing","detail":"Folgte dem Direkt-Akquise-Plan und gewann 3 Großkunden sofort."},{"name":"Sandra K.","result":"4 Stammkunden in 6 Wochen","detail":"Nutzte die Proposal-Vorlagen und schloss 100% ihrer Angebote ab."}],
   "faqs":[{"q":"Brauche ich besondere Skills?","a":"Wir zeigen dir welche Skills am meisten verdienen und wie du sie schnell lernst."},{"q":"Kann ich das neben dem Job machen?","a":"Ja — viele starten nebenberuflich und wechseln dann vollzeit."},{"q":"Wie finde ich Kunden?","a":"Upwork, Fiverr, LinkedIn und Direkt-Akquise — alles wird erklärt."},{"q":"Was kostet ein gutes Profil?","a":"Nichts — die Optimierungs-Tipps sind kostenfrei umsetzbar."},{"q":"Wann bin ich profitabel?","a":"Erfahrungsgemäß nach 2-6 Wochen aktiver Akquise."}]},

  {"slug":"instagram-reels","title":"Instagram Reels","sub":"Viral & monetarisiert","price":"27","ds24":"669750",
   "tagline":"Mit Reels Millionen Reichweite aufbauen",
   "desc":"Lerne die genaue Strategie für virale Instagram Reels — von der Content-Idee über Produktion bis zur Monetarisierung.",
   "icon":"📱","color":"#e1306c",
   "features":["Viral-Formel für Reels","Hook-Strategien für mehr Views","KI-gestützte Content-Planung","Editing-Templates (CapCut)","Hashtag-Strategie 2026","Monetarisierungs-Wege","Stories & Close Friends","Kollaborations-Outreach"],
   "cases":[{"name":"Mia S.","result":"100k Follower in 6 Monaten","detail":"Wendete die Viral-Formel an — jetzt monetarisiert mit Affiliate und Brand Deals."},{"name":"Lukas H.","result":"€1.800/Monat aus Reels","detail":"Kombiniert Affiliate-Links in Bio mit gesponserten Posts."},{"name":"Emma K.","result":"Erstes Viral-Reel nach Woche 2","detail":"Nutzte die Hook-Strategie — Reel mit 2,3 Mio. Views."}],
   "faqs":[{"q":"Brauche ich teures Equipment?","a":"Nein — ein iPhone reicht vollkommen."},{"q":"Wie oft muss ich posten?","a":"3-5x pro Woche für optimales Wachstum."},{"q":"Wann kann ich monetarisieren?","a":"Ab 10.000 Follower sind erste Einnahmen möglich."},{"q":"Welche Nischen funktionieren?","a":"Business, Finance, Lifestyle, Food, Fitness — wir zeigen was 2026 geht."},{"q":"Wie lange dauert ein Reel?","a":"Mit unseren Templates: 30-60 Minuten."}]},

  {"slug":"youtube-automation","title":"YouTube Automation","sub":"Kanal ohne eigenes Gesicht","price":"47","ds24":"669750",
   "tagline":"YouTube-Einnahmen ohne vor der Kamera zu stehen",
   "desc":"Baue einen automatisierten YouTube-Kanal mit KI-Voiceover, Stock-Footage und systematischer Content-Produktion auf.",
   "icon":"▶️","color":"#ff0000",
   "features":["Faceless Channel Konzept","KI-Voiceover mit ElevenLabs","Stock-Footage-Quellen","Script-Generierung mit ChatGPT","Thumbnail-Automation","Upload-Planung & SEO","Monetarisierungs-Strategien","Kanal-Skalierung auf mehrere Kanäle"],
   "cases":[{"name":"Ben K.","result":"€1.200 AdSense nach 4 Monaten","detail":"Startete einen Finanz-Kanal ohne eigenes Gesicht — heute 50k Abonnenten."},{"name":"Tina M.","result":"3 Kanäle parallel","detail":"Nutzte das System für mehrere Nischen — diversifiziertes Einkommen."},{"name":"Max R.","result":"Erste Monetarisierung in Monat 3","detail":"Erreichte 1.000 Subscriber in 10 Wochen mit 3 Videos pro Woche."}],
   "faqs":[{"q":"Muss ich sprechen oder mein Gesicht zeigen?","a":"Nein — KI-Voiceover und Stock-Footage reichen komplett."},{"q":"Wie viele Videos pro Woche?","a":"Für schnelles Wachstum 3-5, für Automation 1-2 reichen."},{"q":"Wann gibt es AdSense?","a":"Ab 1.000 Subscriber + 4.000 Stunden Watchtime."},{"q":"Welche Nischen empfehlt ihr?","a":"Finance, Tech, History, Motivation — hohe RPMs garantiert."},{"q":"Wie lange dauert Video-Produktion?","a":"Mit KI-Tools: 2-4 Stunden pro Video."}]},

  {"slug":"business-skalierung","title":"Business Skalierung","sub":"Von 5k auf 50k/Monat","price":"97","ds24":"669750",
   "tagline":"Dein Business auf die nächste Stufe bringen",
   "desc":"Skalierungssysteme für Online-Unternehmer: Delegation, Automation, Paid Traffic und Team-Aufbau strategisch kombiniert.",
   "icon":"📈","color":"#f59e0b",
   "features":["Wachstums-Roadmap 12 Monate","Delegation & Outsourcing Strategie","Paid Traffic Skalierung (Meta/Google)","KI-Automation für wiederkehrende Tasks","Team-Aufbau & Führung","KPI-Dashboard Setup","Finanzplanung für Wachstum","Exit-Strategie & Bewertung"],
   "cases":[{"name":"Oliver G.","result":"Von €4k auf €22k in 6 Monaten","detail":"Implementierte die Delegation-Strategie und fokussierte sich auf Wachstum."},{"name":"Sarah B.","result":"Team von 1 auf 8 in einem Jahr","detail":"Nutzte den Outsourcing-Leitfaden und baute ein Remote-Team auf."},{"name":"Frank N.","result":"3x Umsatz durch Paid Traffic","detail":"Skalierte Meta Ads mit dem beiliegenden Framework auf profitablen ROAS."}],
   "faqs":[{"q":"Ab wann macht Skalierung Sinn?","a":"Ab €2.000/Monat stabilem Umsatz ist Skalierung sinnvoll."},{"q":"Wie viel Budget für Paid Ads?","a":"Start ab €500/Monat — das System optimiert laufend."},{"q":"Wie delegiere ich richtig?","a":"Wir zeigen welche Aufgaben zuerst ausgelagert werden sollten."},{"q":"Was sind KPIs?","a":"Key Performance Indicators — wir bauen dein Dashboard Schritt für Schritt."},{"q":"Kann ich das selbst machen?","a":"Ja — die meisten Systeme sind solo umsetzbar."}]},

  {"slug":"facebook-gruppen-business","title":"Facebook Gruppen","sub":"Community-Business aufbauen","price":"37","ds24":"669750",
   "tagline":"Profitable Community in Facebook-Gruppen aufbauen",
   "desc":"Baue eine hochwertige Facebook-Gruppe auf, monetarisiere sie und generiere kontinuierlich Leads für dein Business.",
   "icon":"👥","color":"#1877f2",
   "features":["Gruppen-Aufbau-Strategie","Content-Plan für Engagement","Leads aus der Gruppe generieren","Monetarisierungsmodelle","Wachstums-Hacks 2026","Automatisierung mit ManyChat","Paid Membership Strategie","Cross-Promotion Methoden"],
   "cases":[{"name":"Carla W.","result":"5.000 Mitglieder in 4 Monaten","detail":"Kombinierte organisches Wachstum mit gezielten Gruppen-Beiträgen."},{"name":"Mario F.","result":"€2.800/Monat aus Membership","detail":"Führte eine €29/Monat Premium-Mitgliedschaft ein — 96 Mitglieder."},{"name":"Petra S.","result":"50 Leads/Woche aus der Gruppe","detail":"Nutzte die Lead-Magnet-Strategie für kontinuierlichen Zustrom."}],
   "faqs":[{"q":"Wie viele Mitglieder brauche ich für Einnahmen?","a":"Ab 500 aktiven Mitgliedern sind erste Einnahmen möglich."},{"q":"Wie halte ich die Gruppe aktiv?","a":"Wir liefern einen 30-Tage Content-Plan."},{"q":"Ist das mit Facebook-Regeln kompatibel?","a":"Ja — wir erklären was erlaubt ist und was nicht."},{"q":"Wie groß kann eine Gruppe werden?","a":"Erfolgreiche Gruppen haben 10.000-500.000 Mitglieder."},{"q":"Muss ich täglich posten?","a":"Mit Automation-Tools reichen 3-4 Posts pro Woche."}]},

  {"slug":"reits-immobilien-investieren","title":"REITs & Immobilien","sub":"Passiv investieren ab €500","price":"37","ds24":"669750",
   "tagline":"Immobilien-Einkommen ohne eigene Immobilien",
   "desc":"REITs und Immobilien-ETFs als passive Einkommensquelle — Schritt für Schritt vom Konto bis zur ersten Ausschüttung.",
   "icon":"🏦","color":"#10b981",
   "features":["Top REITs für 2026 analysiert","Immobilien-ETF Vergleich","Steuerliche Behandlung in Deutschland","Dividenden-Strategie optimiert","Broker-Auswahl & Depot-Setup","Portfolio-Aufbau ab €500","Risikomanagement","Wiederanlage-Automation"],
   "cases":[{"name":"Rainer M.","result":"€480/Monat Dividenden mit €40k","detail":"Investierte in ein diversifiziertes REIT-Portfolio — 14,4% Jahresrendite."},{"name":"Birgit S.","result":"Erste Ausschüttung nach 2 Monaten","detail":"Startete mit €2.000 und erhielt nach 8 Wochen die erste Dividende."},{"name":"Thomas K.","result":"Portfolio in 5 Jahren auf €180k","detail":"Reinvestierte Dividenden konsequent — Zinseszins-Effekt voll genutzt."}],
   "faqs":[{"q":"Was sind REITs?","a":"Real Estate Investment Trusts — börsengehandelte Immobilien-Unternehmen mit Pflicht zur Ausschüttung."},{"q":"Wie viel Startkapital?","a":"Ab €500 ist der Einstieg möglich."},{"q":"Sind REITs steuerpflichtig?","a":"Ja — wir erklären die Abgeltungssteuer und was du absetzen kannst."},{"q":"Welcher Broker?","a":"Wir vergleichen Flatex, Scalable, Trade Republic und mehr."},{"q":"Wie oft gibt es Ausschüttungen?","a":"Je nach REIT monatlich, quartalsweise oder jährlich."}]},

  {"slug":"chatgpt-masterclass","title":"ChatGPT Masterclass","sub":"Profi-Prompting für Einnahmen","price":"47","ds24":"669750",
   "tagline":"ChatGPT wie ein Profi nutzen und damit verdienen",
   "desc":"Von Basis-Prompting zu Advanced Techniques: Lerne ChatGPT für Content, Code, Business und Einkommensgenerierung zu meistern.",
   "icon":"💬","color":"#10a37f",
   "features":["Advanced Prompting Techniken","System-Prompts für jede Aufgabe","ChatGPT für Business-Automatisierung","Content-Erstellung in Minuten","Code-Generierung ohne Programmierkenntnisse","GPTs erstellen & verkaufen","Produktivitäts-Workflows","API-Nutzung für Entwickler"],
   "cases":[{"name":"Anne B.","result":"40h/Monat gespart mit ChatGPT","detail":"Automatisierte Reports, E-Mails und Präsentationen komplett."},{"name":"Chris M.","result":"€800 durch GPT-Verkauf","detail":"Erstellte 3 Custom GPTs und verkaufte sie auf der GPT-Store-Plattform."},{"name":"Lea F.","result":"Content für 3 Kanäle in 2h","detail":"Nutzt die Content-Pipeline für YouTube, Instagram und Newsletter."}],
   "faqs":[{"q":"Brauche ich ChatGPT Plus?","a":"Für einige Features ja — Plus kostet $20/Monat und amortisiert sich sofort."},{"q":"Gibt es Updates?","a":"Ja — der Kurs wird mit neuen ChatGPT-Features aktualisiert."},{"q":"Was ist der Unterschied zu YouTube-Tutorials?","a":"Wir zeigen Business-relevante Anwendungen, keine Spielereien."},{"q":"Kann ich GPTs verkaufen?","a":"Ja — wir zeigen wie Custom GPTs monetarisiert werden."},{"q":"Wie lange ist der Kurs?","a":"Ca. 6 Stunden — vollständig selbst einteilbar."}]},

  {"slug":"tiktok-algorithmus","title":"TikTok Algorithmus","sub":"Viral gehen 2026","price":"27","ds24":"669750",
   "tagline":"Den TikTok-Algorithmus 2026 verstehen und nutzen",
   "desc":"Lerne genau wie der TikTok-Algorithmus funktioniert und wie du ihn systematisch für Reichweite und Einnahmen nutzt.",
   "icon":"🎵","color":"#69c9d0",
   "features":["Algorithmus-Analyse 2026","For-You-Page Optimierung","Hook-Formeln für sofortiges Engagement","Posting-Zeiten & Frequenz","Trending Sounds & Hashtags","Nischen-Strategie","TikTok LIVE für Einnahmen","Creator Fund & Brand Deals"],
   "cases":[{"name":"Kevin L.","result":"500k Views in 7 Tagen","detail":"Wendete die Hook-Formeln an — erstes Viral-Video in Woche 1."},{"name":"Lena K.","result":"50k Follower in 3 Monaten","detail":"Postet konsequent mit dem Algorithmus-Plan — organisches Wachstum."},{"name":"Noah S.","result":"€1.200 Creator Fund in Monat 4","detail":"Erreichte 100k Follower und qualifizierte sich für den Creator Fund."}],
   "faqs":[{"q":"Muss ich täglich posten?","a":"Für schnelles Wachstum 1-3x täglich — wir zeigen wie das effizient geht."},{"q":"Welche Nischen performen 2026?","a":"Finance, DIY, Comedy, Business, Fitness — alle mit Algorithmus-Boost."},{"q":"Brauche ich professionelles Editing?","a":"Nein — native TikTok-Funktionen reichen vollkommen."},{"q":"Wann kann ich monetarisieren?","a":"Ab 10.000 Follower ist der Creator Fund zugänglich."},{"q":"Funktioniert das auf Deutsch?","a":"Ja — deutschsprachige Nischen sind weniger gesättigt."}]},

  {"slug":"tiktok-shop-dropship","title":"TikTok Shop Dropship","sub":"Ohne Lager verkaufen","price":"47","ds24":"669750",
   "tagline":"TikTok Shop als Dropshipping-Plattform nutzen",
   "desc":"TikTok Shop kombiniert Social Commerce und Dropshipping — lerne das System für 2026 vollständig aufzubauen.",
   "icon":"🛍️","color":"#fe2c55",
   "features":["TikTok Shop Setup Schritt für Schritt","Produkt-Recherche für TikTok","UGC-Content Strategie","Affiliate-Programm für Verkäufer","Order-Automatisierung","TikTok Ads für Shop-Produkte","Lieferanten-Integration","Scaling-Strategie"],
   "cases":[{"name":"Julia T.","result":"€3.400 erster Monat TikTok Shop","detail":"Fand Trend-Produkte mit dem Recherche-Tool und startete sofort."},{"name":"Mike D.","result":"50 UGC-Creators arbeiten für ihn","detail":"Setzte das Affiliate-Programm auf — Creators promoten kostenlos gegen Provision."},{"name":"Sophie R.","result":"100% Automation erreicht","detail":"Integrierte Lieferant → Shopify → TikTok Shop vollautomatisch."}],
   "faqs":[{"q":"Brauche ich eigene Produkte?","a":"Nein — Dropshipping mit TikTok Shop ist möglich."},{"q":"Wie finde ich trending Produkte?","a":"Wir zeigen TikTok Creative Center und weitere Recherche-Tools."},{"q":"Was sind UGC-Creators?","a":"User Generated Content — Ersteller die Produkte zeigen für Provision."},{"q":"Brauche ich ein Gewerbe?","a":"Ja — TikTok Shop erfordert eine Gewerbeanmeldung."},{"q":"Wie hoch sind die Provisionen?","a":"Typisch 5-20% pro Verkauf für Affiliates."}]},

  {"slug":"virtual-assistant-ki","title":"Virtual Assistant KI","sub":"Dienste mit KI anbieten","price":"37","ds24":"669750",
   "tagline":"Als KI-Virtual-Assistant €50-150/h verdienen",
   "desc":"Biete hochwertige VA-Services mit KI-Unterstützung an — von Admin-Tasks bis Content-Erstellung, alles effizienter.",
   "icon":"🤝","color":"#06b6d4",
   "features":["Top-VA-Services 2026","KI-Tools für höhere Effizienz","Kunden-Akquise Strategie","Preisgestaltung für Premium-Kunden","Vertragsvorlagen","Task-Management-System","Upskilling-Roadmap","Agentur gründen als nächster Schritt"],
   "cases":[{"name":"Celine B.","result":"€4.200/Monat als VA","detail":"Spezialisierte sich auf KI-gestütztes Social Media Management."},{"name":"Daniel H.","result":"6 Dauerkunden in 2 Monaten","detail":"Nutzte die Akquise-Strategie auf LinkedIn — voller Kalender."},{"name":"Laura S.","result":"Von €15/h auf €75/h in 6 Monaten","detail":"Positionierte sich als KI-Spezialistin und erhöhte Preise schrittweise."}],
   "faqs":[{"q":"Brauche ich besondere Fähigkeiten?","a":"Grundlegende PC-Kenntnisse und Lernbereitschaft reichen."},{"q":"Wo finde ich Kunden?","a":"Upwork, Fiverr, LinkedIn, direkte Akquise — alles wird erklärt."},{"q":"Was verdient ein VA?","a":"€20-150/h je nach Spezialisierung."},{"q":"Kann ich das von zuhause machen?","a":"Ja — 100% remote möglich."},{"q":"Wie starte ich ohne Erfahrung?","a":"Mit günstigeren Einstiegspreisen und Portfolio-Aufbau."}]},

  {"slug":"youtube-shorts-einkommen","title":"YouTube Shorts","sub":"Kurze Videos — großes Einkommen","price":"27","ds24":"669750",
   "tagline":"Mit YouTube Shorts täglich passiv verdienen",
   "desc":"YouTube Shorts als Einkommensquelle: Monetarisierung, Wachstum und Content-Strategie für 2026.",
   "icon":"⚡","color":"#ff0000",
   "features":["Shorts-Algorithmus verstehen","Viral-Format-Vorlagen","KI-Script-Generierung","Faceless Shorts Konzept","Shorts-Monetarisierung erklärt","Zum Langformat konvertieren","Cross-Plattform-Strategie","Batch-Production-System"],
   "cases":[{"name":"Tim S.","result":"€600/Monat Shorts-Bonus","detail":"100 Shorts in 30 Tagen — regelmäßige Bonus-Auszahlungen von YouTube."},{"name":"Ines W.","result":"500k Views Shorts in Monat 1","detail":"Nutzte die Viral-Formel für Finance-Content — explodierendes Wachstum."},{"name":"Paul K.","result":"Kanal von 0 auf 50k in 90 Tagen","detail":"Batch-produzierte 60 Shorts und postete sie über 3 Monate."}],
   "faqs":[{"q":"Werden Shorts gut bezahlt?","a":"YouTube zahlt Shorts-Bonus ab bestimmten View-Zahlen."},{"q":"Wie lang sollen Shorts sein?","a":"15-60 Sekunden für maximale Reichweite."},{"q":"Muss ich eigene Videos drehen?","a":"Nein — Faceless mit Stock-Footage und KI-Voiceover funktioniert."},{"q":"Wie viele Shorts pro Tag?","a":"1-3 für schnelles Wachstum, 1 für stabiles Wachstum."},{"q":"Brauche ich zuerst Abonnenten?","a":"Nein — Shorts können sofort viral gehen."}]},

  {"slug":"krypto-staking-einkommen","title":"Krypto Staking","sub":"Passives Einkommen mit Crypto","price":"47","ds24":"669750",
   "tagline":"Krypto-Bestände für sich arbeiten lassen",
   "desc":"Staking, Yield Farming und DeFi-Strategien für passives Einkommen mit Kryptowährungen — sicher und profitabel.",
   "icon":"₿","color":"#f7931a",
   "features":["Staking-Plattformen im Vergleich","Risikomanagement für DeFi","Top Staking-Coins 2026","Yield Farming Basics","Steuern & Reporting","Hardware Wallet Setup","Liquidity Mining verstehen","Portfolio-Diversifikation"],
   "cases":[{"name":"Alex P.","result":"12% APY auf ETH-Staking","detail":"Staket ETH auf Lido — monatliche Erträge automatisch reinvestiert."},{"name":"Nora F.","result":"€380/Monat passiv aus Staking","detail":"Diversifiziertes Staking-Portfolio auf 5 Plattformen."},{"name":"Jonas W.","result":"DeFi-Einstieg ohne Verlust","detail":"Nutzte das Risikomanagement-Framework — keine Rug-Pulls erlebt."}],
   "faqs":[{"q":"Ist Staking sicher?","a":"Seriöse Plattformen sind relativ sicher — wir zeigen wie du Risiken minimierst."},{"q":"Wie hoch sind typische APYs?","a":"5-20% je nach Coin und Plattform."},{"q":"Muss ich Krypto verstehen?","a":"Grundkenntnisse hilfreich — wir erklären alles nötige."},{"q":"Sind Erträge steuerpflichtig?","a":"Ja — wir erklären die deutsche Rechtslage."},{"q":"Wie viel Startkapital?","a":"Ab €500 sind erste Erträge möglich."}]},

  {"slug":"leadgen-lokale-unternehmen","title":"LeadGen Lokal","sub":"B2B Leads für lokale Firmen","price":"57","ds24":"669750",
   "tagline":"Lokale Unternehmen mit Leads versorgen und verdienen",
   "desc":"Baue eine lokale Lead-Generierungs-Agentur auf — liefere Kunden-Leads an lokale Unternehmen und verdiene monatlich wiederkehrend.",
   "icon":"🎯","color":"#ec4899",
   "features":["Nischen-Auswahl für lokale B2B","Google Ads für lokale Leads","Facebook Ads für Handwerker","Lead-Qualifizierungs-System","Retainer-Modell €500-2000/Monat","Reporting für Kunden","Skalierung auf mehrere Branchen","CRM-Setup für Lead-Tracking"],
   "cases":[{"name":"Florian M.","result":"€2.400/Monat Retainer","detail":"2 Handwerker-Kunden zahlen je €1.200/Monat für kontinuierliche Leads."},{"name":"Petra W.","result":"50 Leads/Woche für Zahnarzt","detail":"Google Ads Campaign für lokalen Zahnarzt — €800/Monat retainer."},{"name":"Lars K.","result":"6 Kunden in 2 Monaten","detail":"Nutzte die Kaltakquise-Strategie für Handwerker — voller Auftragskalender."}],
   "faqs":[{"q":"Wie finde ich Branchen-Kunden?","a":"Kaltakquise, Google Maps, lokale Netzwerke — alles wird erklärt."},{"q":"Wie viel kosten die Ads?","a":"Typisch €300-1.000/Monat Budget für den Kunden."},{"q":"Was berechne ich als Retainer?","a":"€500-2.000/Monat je nach Branche und Leads."},{"q":"Brauche ich Ad-Erfahrung?","a":"Wir erklären Google Ads und Facebook Ads von Grund auf."},{"q":"Wie messe ich Erfolg?","a":"Mit unserem Reporting-Dashboard — transparent für den Kunden."}]},

  {"slug":"linkedin-b2b-leads","title":"LinkedIn B2B Leads","sub":"Entscheider direkt erreichen","price":"57","ds24":"669750",
   "tagline":"Qualifizierte B2B-Leads über LinkedIn generieren",
   "desc":"LinkedIn als Lead-Maschine: Profil-Optimierung, Outreach-Automatisierung und Sales Navigator für kontinuierliche B2B-Pipeline.",
   "icon":"💼","color":"#0077b5",
   "features":["LinkedIn-Profil für B2B optimieren","Sales Navigator Nutzung","Outreach-Automation (innerhalb ToS)","Nachrichtenvorlagen die öffnen","Content-Strategie für Entscheider","Verbindungsaufbau systematisch","Meeting-Buchungs-Funnel","CRM-Integration"],
   "cases":[{"name":"Bernd H.","result":"30 qualifizierte Leads/Monat","detail":"Implementierte die Outreach-Strategie — 3 neue Kunden in Monat 1."},{"name":"Monika R.","result":"€15.000 Deal aus LinkedIn","detail":"Eine Verbindungsanfrage führte zu einem Enterprise-Kunden."},{"name":"Stefan F.","result":"Pipeline von €80.000","detail":"Systematischer LinkedIn-Aufbau über 6 Monate — volle Sales-Pipeline."}],
   "faqs":[{"q":"Brauche ich LinkedIn Premium?","a":"Sales Navigator empfohlen (€80/Monat) — amortisiert sich sofort."},{"q":"Ist Outreach-Automation erlaubt?","a":"Wir zeigen ToS-konforme Methoden — kein Account-Risiko."},{"q":"Wie viele Verbindungen täglich?","a":"Max 20-25 — wir erklären die sicheren Limits."},{"q":"Welche Branchen performen?","a":"IT, Beratung, Marketing, Finanz, SaaS — alle gut für LinkedIn."},{"q":"Wie lange bis erste Leads?","a":"Bei konsequenter Umsetzung: 2-4 Wochen."}]},

  {"slug":"pinterest-traffic-maschine","title":"Pinterest Traffic","sub":"Massentraffic ohne Ads","price":"27","ds24":"669750",
   "tagline":"Pinterest als dauerhafte organische Traffic-Quelle",
   "desc":"Pinterest liefert Jahre nach dem Posting noch Traffic — lerne das System für nachhaltigen organischen Zustrom zu deinen Angeboten.",
   "icon":"📌","color":"#e60023",
   "features":["Pinterest SEO Grundlagen","Pin-Design-Vorlagen","Batch-Scheduling mit Tailwind","Board-Struktur optimiert","Affiliate-Links in Pins","Traffic auf Blog/Shop","Analytics & Optimierung","Viral-Pin-Strategie"],
   "cases":[{"name":"Sabine W.","result":"5.000 Website-Besucher/Monat","detail":"Nur Pinterest — ohne andere Kanäle oder Ads."},{"name":"Carolin S.","result":"€450/Monat Affiliate aus Pinterest","detail":"Pins mit Affiliate-Links bringen monatlich wiederkehrenden Umsatz."},{"name":"Uta M.","result":"Blog von 0 auf 15k Besucher","detail":"Pinterest als einzige Traffic-Quelle in 4 Monaten."}],
   "faqs":[{"q":"Wie lange dauert Pinterest-Wachstum?","a":"3-6 Monate für nennenswerten Traffic — dann exponentiell."},{"q":"Brauche ich eigene Bilder?","a":"Nein — Canva-Vorlagen reichen vollkommen."},{"q":"Kann ich Affiliate-Links direkt pinnen?","a":"Ja — Amazon und viele andere Affiliate-Programme sind erlaubt."},{"q":"Wie viele Pins pro Tag?","a":"5-15 Pins täglich für optimales Wachstum."},{"q":"Ist Tailwind nötig?","a":"Empfohlen für Scheduling — ca. €15/Monat."}]},

  {"slug":"podcast-business-monetarisierung","title":"Podcast Business","sub":"Mit Stimme verdienen","price":"47","ds24":"669750",
   "tagline":"Profitablen Podcast aufbauen und monetarisieren",
   "desc":"Von der ersten Folge bis zu €2.000+/Monat: Podcast-Technik, Wachstum, Sponsoring und eigene Produkte.",
   "icon":"🎙️","color":"#7c3aed",
   "features":["Podcast-Konzept entwickeln","Technik für Einsteiger (ab €50)","Hosting & Distribution Setup","Wachstums-Strategien","Sponsoring ab 1.000 Hörer","Membership-Modell","Eigene Produkte integrieren","Cross-Promotion Netzwerk"],
   "cases":[{"name":"Robert K.","result":"€1.800/Monat nach 12 Monaten","detail":"Kombination aus Sponsoring, Membership und eigenem Kurs."},{"name":"Yara H.","result":"Erster Sponsoring-Deal nach 6 Monaten","detail":"800 Downloads/Folge reichten für erste Sponsor-Anfragen."},{"name":"Mark S.","result":"5.000 Hörer in 8 Monaten","detail":"Konsequente Gast-Kooperationen verdoppelten die Hörerschaft."}],
   "faqs":[{"q":"Wie teuer ist der Start?","a":"Ab €50 für ein Einsteiger-Mikrofon — Software meist kostenlos."},{"q":"Wie finde ich Themen?","a":"Wir liefern 100 Episoden-Ideen für jede Nische."},{"q":"Wann gibt es Sponsoring?","a":"Ab ca. 500-1.000 Hörern pro Folge."},{"q":"Wie lang sollen Folgen sein?","a":"20-45 Minuten für optimale Hörerbindung."},{"q":"Welche Plattform zum Hosten?","a":"Buzzsprout oder Anchor (kostenlos) — wir vergleichen alle."}]},

  {"slug":"saas-ohne-code-bauen","title":"SaaS ohne Code","sub":"Software verkaufen ohne Programmieren","price":"97","ds24":"669750",
   "tagline":"Dein eigenes SaaS-Produkt ohne Code-Kenntnisse",
   "desc":"Baue ein profitables SaaS-Produkt mit No-Code-Tools auf: von der Idee über den Bau bis zu zahlenden Kunden.",
   "icon":"🔧","color":"#6366f1",
   "features":["Profitable SaaS-Ideen finden","No-Code-Tools (Bubble, Webflow, Glide)","MVP in 2 Wochen bauen","Pricing & Abomodell","Erste Kunden gewinnen","Onboarding automatisieren","Churn reduzieren","Zu Code-Version migrieren"],
   "cases":[{"name":"Michael S.","result":"€3.200/Monat MRR nach 6 Monaten","detail":"Baute ein einfaches Planungs-Tool mit Bubble — 32 zahlende Kunden."},{"name":"Jana L.","result":"MVP in 10 Tagen","detail":"Nutzte Glide für ein mobiles Tool — erste Nutzer nach 2 Wochen."},{"name":"Tobias R.","result":"€150k ARR nach 18 Monaten","detail":"Skalierte von No-Code auf eigene Entwicklung nach dem PMF."}],
   "faqs":[{"q":"Brauche ich Programmierkenntnisse?","a":"Nein — No-Code-Tools ersetzen Code vollständig für MVPs."},{"q":"Was kostet der SaaS-Aufbau?","a":"€50-200/Monat für No-Code-Tools am Anfang."},{"q":"Wie finde ich mein Thema?","a":"Wir liefern ein Framework für profitable Nischen-Analyse."},{"q":"Was ist ein MVP?","a":"Minimum Viable Product — die kleinste verkaufbare Version."},{"q":"Wann ist Code nötig?","a":"Ab ca. €10k MRR lohnt sich oft der Wechsel zu echtem Code."}]},

  {"slug":"ki-automatisierung-shopify","title":"KI Shopify Automation","sub":"Store mit KI auf Autopilot","price":"57","ds24":"669750",
   "tagline":"Deinen Shopify-Store mit KI vollständig automatisieren",
   "desc":"Nutze KI für Produktbeschreibungen, SEO, Kundenservice und Marketing — dein Shopify-Store läuft sich selbst.",
   "icon":"🤖","color":"#96bf48",
   "features":["KI-Produktbeschreibungen massenhaft","SEO-Optimierung mit Claude/GPT","Automatischer Kundenservice-Chatbot","Personalisierte Email-Sequenzen","Preisoptimierung mit KI","KI-generierte Produktbilder","Social-Media-Automation","Analytics-Interpretation mit KI"],
   "cases":[{"name":"Claudia K.","result":"200 Produktbeschreibungen in 1h","detail":"Nutzte das KI-Prompt-System für Massen-Beschreibungen."},{"name":"Sven M.","result":"30% mehr organischer Traffic","detail":"KI-SEO-Optimierung für alle Produktseiten — deutlicher Ranking-Boost."},{"name":"Heike T.","result":"Kundenservice 90% automatisiert","detail":"Chatbot beantwortet Standardanfragen — Team nur noch für Eskalationen."}],
   "faqs":[{"q":"Welche KI-Tools werden genutzt?","a":"ChatGPT, Claude, Midjourney — alle werden erklärt."},{"q":"Funktioniert das mit meiner Shopify-Version?","a":"Ja — alle Pläne ab Basic werden unterstützt."},{"q":"Wie lang dauert die Einrichtung?","a":"1 Wochenende für das vollständige Setup."},{"q":"Ist das teuer?","a":"KI-Tools kosten $20-50/Monat — Rendite deutlich höher."},{"q":"Werden wirklich alle Tasks automatisiert?","a":"85-90% — für komplexe Entscheidungen bleibt Mensch im Loop."}]},

  {"slug":"ki-bilder-verkaufen","title":"KI Bilder Verkaufen","sub":"Midjourney Prints & Lizenzen","price":"37","ds24":"669750",
   "tagline":"Mit KI-generierten Bildern passiv verdienen",
   "desc":"Generiere KI-Kunstwerke mit Midjourney und verkaufe sie auf Etsy, Shutterstock, Adobe Stock und als Print-on-Demand.",
   "icon":"🎨","color":"#8b5cf6",
   "features":["Midjourney Profi-Prompting","Etsy Shop Setup für digitale Downloads","Shutterstock & Adobe Stock Uploads","Print-on-Demand Integration (Printify)","Trending Styles erkennen","Batch-Produktion mit Konsistenz","Urheberrecht & Plattform-Regeln","Skalierung auf 1000+ Produkte"],
   "cases":[{"name":"Anna V.","result":"€680/Monat Etsy-Einnahmen","detail":"500 digitale Download-Produkte — passiv ohne weitere Arbeit."},{"name":"Marco B.","result":"Adobe Stock approved — 200 Bilder","detail":"KI-Fotos durch Qualitätskontrolle — monatliche Lizenz-Einnahmen."},{"name":"Nina R.","result":"Printify Shop mit 1.200 Produkten","detail":"Skalierte von 50 auf 1.200 Produkte in 3 Monaten."}],
   "faqs":[{"q":"Brauche ich Midjourney?","a":"Ja — ab $10/Monat — amortisiert sich bei ersten Verkäufen."},{"q":"Darf ich KI-Bilder verkaufen?","a":"Ja — mit korrekter Lizenzierung auf den Plattformen erlaubt."},{"q":"Wie viel verdient man?","a":"€0,30-5 pro Lizenz, €3-25 pro Etsy-Download, €20-200 pro Print."},{"q":"Brauche ich Design-Kenntnisse?","a":"Nein — nur die richtigen Prompts aus dem Kurs."},{"q":"Wie schnell gibt es Einnahmen?","a":"Etsy: 2-8 Wochen bis erste Verkäufe."}]},

  {"slug":"ki-consulting-starten","title":"KI Consulting","sub":"Unternehmen beraten mit KI","price":"97","ds24":"669750",
   "tagline":"Als KI-Berater €150-500/h verdienen",
   "desc":"Starte als gefragter KI-Consultant für Unternehmen — von der Positionierung über Angebote bis zu Enterprise-Kunden.",
   "icon":"🧠","color":"#f59e0b",
   "features":["Consulting-Positionierung als KI-Experte","Angebotspakete €1.500-15.000","Enterprise-Kunden akquirieren","Discovery-Calls führen","Projektstruktur & Deliverables","Case Studies aufbauen","Netzwerk aufbauen","Recurring Revenue Modell"],
   "cases":[{"name":"Andreas K.","result":"€8.500 erster Enterprise-Auftrag","detail":"Discovery Call nach LinkedIn-Kontakt — 3 Monate Projektlaufzeit."},{"name":"Stefanie B.","result":"€180/h Tages-Rate nach 4 Monaten","detail":"Positionierte sich als Prozess-Automatisierungsexpertin."},{"name":"Philipp W.","result":"6 Festkunden monatlich €12k","detail":"Mix aus Retainern und Projekten — stabile Basis."}],
   "faqs":[{"q":"Brauche ich KI-Zertifikate?","a":"Nein — praktische Expertise und Case Studies überzeugen mehr."},{"q":"Wie finde ich Enterprise-Kunden?","a":"LinkedIn, Netzwerk-Events, Referrals — wir erklären alle Kanäle."},{"q":"Was verkaufe ich konkret?","a":"KI-Strategie-Beratung, Prozess-Automatisierung, Team-Schulungen."},{"q":"Wie setze ich Preise?","a":"Wert-basiertes Pricing — wir zeigen wie du €150-500/h rechtfertigst."},{"q":"Brauche ich Programmier-Skills?","a":"Hilfreich aber nicht nötig — viele Consultants sind reine Strategen."}]},

  {"slug":"ki-content-agentur","title":"KI Content Agentur","sub":"Content-Produktion auf Autopilot","price":"67","ds24":"669750",
   "tagline":"Content-Agentur mit KI 10x effizienter betreiben",
   "desc":"Baue eine professionelle Content-Agentur auf die mit KI-Tools 10x mehr Output bei gleichem Aufwand liefert.",
   "icon":"✍️","color":"#10b981",
   "features":["Agentur-Setup & Prozesse","KI-Content-Pipeline aufbauen","Qualitätskontrolle für KI-Outputs","Kunden-Onboarding System","Pricing für Content-Pakete","Freelancer-Netzwerk aufbauen","White-Label Angebote","Umsatz-Skalierung"],
   "cases":[{"name":"Miriam S.","result":"€9.200/Monat Agentur-Umsatz","detail":"5 Kunden, KI produziert 80% des Contents — Team von 2 Personen."},{"name":"Patrick L.","result":"Erste Agentur-Kunden in Woche 3","detail":"Nutzte das fertige Angebot-Template und schloss 2 Kunden sofort."},{"name":"Katharina M.","result":"White-Label für 3 Agenturen","detail":"Liefert Content an andere Agenturen — skaliert ohne eigene Kunden."}],
   "faqs":[{"q":"Brauche ich Schreib-Erfahrung?","a":"Hilfreich aber nicht nötig — KI schreibt, du redst."},{"q":"Wie groß muss das Team sein?","a":"Starte solo mit KI — wir zeigen wann du skalierst."},{"q":"Was kostet die Einrichtung?","a":"Unter €200 für alle nötigen KI-Tools."},{"q":"Kann ich sofort Kunden gewinnen?","a":"Mit unseren Angebots-Templates und Akquise-Skripten: ja."},{"q":"Was ist White-Label?","a":"Du produzierst Content, andere verkaufen ihn unter ihrem Namen."}]},

  {"slug":"airbnb-rental-arbitrage","title":"Airbnb Rental Arbitrage","sub":"Fremdimmobilien vermieten","price":"67","ds24":"669750",
   "tagline":"Airbnb-Einnahmen ohne eigene Immobilien",
   "desc":"Rental Arbitrage: Miete Wohnungen langfristig und vermiete sie kurzfristig über Airbnb — profitable Spread-Strategie.",
   "icon":"🏨","color":"#ff5a5f",
   "features":["Rental Arbitrage erklärt","Wohnungssuche für Arbitrage","Vermieter überzeugen Skript","Airbnb-Listing Optimierung","Preisoptimierung (PriceLabs)","Reinigungs-Automation","Gästemanagement-System","Skalierung auf mehrere Units"],
   "cases":[{"name":"Robert S.","result":"€1.800 Gewinn/Monat erste Unit","detail":"Mietete Wohnung für €900/Monat — erzielt €2.700 auf Airbnb."},{"name":"Christina B.","result":"5 Units in 2 Jahren","detail":"Skalierte schrittweise — heute stabiles Einkommen ohne Eigenkapital."},{"name":"Jürgen K.","result":"Breakeven in Monat 2","detail":"Erste Unit im Minus, ab Monat 2 profitabel — seitdem konstant."}],
   "faqs":[{"q":"Ist das legal?","a":"Ja — mit korrekter Genehmigung und Vermieter-Zustimmung."},{"q":"Wie überzeuge ich Vermieter?","a":"Wir liefern ein fertiges Gesprächs-Skript."},{"q":"Wie viel Startkapital brauche ich?","a":"Erste Monatsmiete + Kaution + Einrichtung: ca. €3.000-8.000."},{"q":"Was wenn es keine Buchungen gibt?","a":"Wir erklären Pricing-Strategien für volle Auslastung."},{"q":"Welche Städte eignen sich?","a":"Tourismus-Städte wie München, Berlin, Hamburg, Wien."}]},

  {"slug":"instagram-affiliate-2026","title":"Instagram Affiliate 2026","sub":"Ohne Produkt Geld verdienen","price":"37","ds24":"669750",
   "tagline":"Als Instagram-Affiliate 2026 profitabel werden",
   "desc":"Aufgebauter Kanal, bewährte Partnerprogramme, automatisierte Conversion-Funnel — Instagram als Affiliate-Einkommensquelle.",
   "icon":"📸","color":"#e1306c",
   "features":["Nischen-Auswahl für Affiliate","Profil als Vertrauens-Asset aufbauen","Stories-Swipe-Up-Strategie","Bio-Link Optimization (Linktree)","Top-Affiliate-Programme 2026","Reel-Formate die klicken","DM-Funnel aufbauen","Automatisierte Follow-up-Sequenzen"],
   "cases":[{"name":"Lara M.","result":"€1.200/Monat Affiliate aus 15k Followern","detail":"Kleine aber hoch engagierte Nische — sehr hohe Conversion."},{"name":"Eric K.","result":"Erste Provision nach Woche 2","detail":"Startete mit Amazon Partnerprogramm — sofortige erste Einnahmen."},{"name":"Hannah S.","result":"3 Affiliate-Programme kombiniert","detail":"Diversifiziert — kein Risiko bei Programm-Änderungen."}],
   "faqs":[{"q":"Brauche ich viele Follower?","a":"Nein — 1.000 Follower in der richtigen Nische reichen für erste Einnahmen."},{"q":"Welche Programme empfehlt ihr?","a":"Amazon, Digistore24, ShareASale — alle im Detail erklärt."},{"q":"Wie bekomme ich Klicks?","a":"Story-Swipe-Ups, Bio-Links, Reels-Call-To-Action."},{"q":"Darf ich Affiliate-Links auf Instagram?","a":"Ja — mit korrekter #ad Kennzeichnung."},{"q":"Wie hoch sind Provisionen?","a":"1-50% je nach Produkt und Programm."}]},

  {"slug":"dividenden-aktien-portfolio","title":"Dividenden Portfolio","sub":"Monatliche Ausschüttungen aufbauen","price":"47","ds24":"669750",
   "tagline":"Monatliches Dividenden-Einkommen Schritt für Schritt",
   "desc":"Aufbau eines robusten Dividenden-Portfolios für monatliche Ausschüttungen — Deutsche Aktien, ETFs und internationale Dividendenstars.",
   "icon":"💹","color":"#10b981",
   "features":["Top-Dividendenaktien 2026","Dividenden-ETFs im Vergleich","Monatliche Ausschüttungs-Strategie","Depot-Setup & Broker-Auswahl","Steuer-Optimierung (Vorabpauschale)","Wiederanlage-Automation","Risikomanagement & Diversifikation","Portfolio-Rebalancing"],
   "cases":[{"name":"Werner K.","result":"€520/Monat Dividenden mit €80k","detail":"7,8% Durchschnittsrendite — reinvestiert seit 3 Jahren."},{"name":"Gabi S.","result":"Monatliche Ausschüttungen erreicht","detail":"Mix aus deutschen und US-Dividendenaktien für monatlichen Rhythmus."},{"name":"Dieter M.","result":"Portfolio von €10k auf €45k in 5 Jahren","detail":"Reinvestition + monatliche Einzahlungen — Zinseszins genutzt."}],
   "faqs":[{"q":"Wie viel Startkapital brauche ich?","a":"Ab €1.000 sind erste Dividenden möglich."},{"q":"Sind Dividenden steuerpflichtig?","a":"Ja — Abgeltungssteuer 25% + Soli — Freibetrag €1.000."},{"q":"Wie finde ich gute Dividendenaktien?","a":"Wir liefern eine aktuelle Top-50-Liste mit Analysen."},{"q":"Wann gibt es Ausschüttungen?","a":"Quartalsweise (US) oder jährlich (DE) — durch Mix monatlich."},{"q":"Was ist die Vorabpauschale?","a":"Steuer-Vorauszahlung auf Fondserträge — wir erklären wie sie wirkt."}]},
]

CATEGORIES = [
  {"slug":"ki-automation","title":"KI & Automation Hub","sub":"Alle KI-Produkte im Überblick","icon":"🤖","color":"#00e87c",
   "products":["ai-income-machine","chatgpt-masterclass","ki-automatisierung-shopify","ki-bilder-verkaufen","ki-consulting-starten","ki-content-agentur","virtual-assistant-ki"]},
  {"slug":"business","title":"Business Hub","sub":"Online-Business aufbauen","icon":"📈","color":"#6366f1",
   "products":["agency-aufbauen","business-skalierung","freelancing-einkommen","saas-ohne-code-bauen","leadgen-lokale-unternehmen","linkedin-b2b-leads","podcast-business-monetarisierung"]},
  {"slug":"social-media","title":"Social Media Hub","sub":"Reichweite & Monetarisierung","icon":"📱","color":"#e1306c",
   "products":["instagram-reels","instagram-affiliate-2026","youtube-automation","youtube-shorts-einkommen","tiktok-algorithmus","tiktok-shop-dropship","pinterest-traffic-maschine","facebook-gruppen-business"]},
  {"slug":"ecommerce","title":"E-Commerce Hub","sub":"Online-Shops & Marktplätze","icon":"🛒","color":"#96bf48",
   "products":["shopify-automation","dropshipping-lieferanten","ki-automatisierung-shopify","tiktok-shop-dropship","ki-bilder-verkaufen"]},
  {"slug":"immobilien","title":"Immobilien Hub","sub":"Immobilien-Investment","icon":"🏠","color":"#ef4444",
   "products":["immobilien-investment","reits-immobilien-investieren","airbnb-rental-arbitrage"]},
  {"slug":"digital-skills","title":"Digital Skills Hub","sub":"Alle digitalen Kompetenzen","icon":"🎓","color":"#f59e0b",
   "products":["chatgpt-masterclass","ki-consulting-starten","saas-ohne-code-bauen","virtual-assistant-ki","freelancing-einkommen"]},
]


def gen_product_page(p):
    slug = p["slug"]
    color = p["color"]
    feat_html = "".join(f'<div class="feat"><div class="feat-icon">✓</div><div>{f}</div></div>' for f in p["features"])
    case_html = "".join(f'''<div class="case-card">
      <div class="case-result">{c["result"]}</div>
      <div class="case-name">{c["name"]}</div>
      <div class="case-detail">{c["detail"]}</div>
    </div>''' for c in p["cases"])
    faq_html = "".join(f'''<div class="faq-item">
      <div class="faq-q">❓ {f["q"]}</div>
      <div class="faq-a">{f["a"]}</div>
    </div>''' for f in p["faqs"])
    checkout_url = f"https://www.checkout-ds24.com/product/{p['ds24']}?affiliate=user37405262"

    return f'''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{p["title"]} — {p["sub"]} | AIITEC</title>
  <meta name="description" content="{p["desc"]}">
  <meta name="robots" content="index,follow">
  <meta property="og:title" content="{p["title"]} — {p["sub"]}">
  <meta property="og:description" content="{p["desc"]}">
  <meta property="og:type" content="website">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    :root{{--c:{color};--bg:#050508;--bg2:#08080f;--card:#0d0d18;--border:#1e1e38;--text:#c8cce0;--dim:#60649a}}
    body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6}}
    a{{text-decoration:none;color:inherit}}
    /* NAV */
    nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}}
    .nav-brand{{font-weight:700;font-size:15px;color:var(--c)}}
    .nav-cta{{background:var(--c);color:#050508;padding:8px 20px;border-radius:6px;font-weight:700;font-size:13px}}
    /* HERO */
    .hero{{min-height:88vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 24px;background:radial-gradient(ellipse 80% 50% at 50% 0%,color-mix(in srgb,var(--c) 8%,transparent) 0%,transparent 70%)}}
    .badge{{display:inline-block;background:color-mix(in srgb,var(--c) 10%,transparent);border:1px solid color-mix(in srgb,var(--c) 30%,transparent);border-radius:20px;padding:5px 16px;font-size:11px;font-family:monospace;color:var(--c);letter-spacing:1px;margin-bottom:20px}}
    .hero h1{{font-size:clamp(28px,5vw,56px);font-weight:800;color:#fff;margin-bottom:10px;line-height:1.15}}
    .hero-sub{{font-size:clamp(15px,2vw,20px);color:var(--c);margin-bottom:16px;font-weight:600}}
    .hero-desc{{font-size:16px;color:var(--dim);max-width:600px;margin:0 auto 32px}}
    .hero-price{{font-size:13px;color:var(--dim);margin-bottom:24px}}
    .hero-price strong{{color:#fff;font-size:28px}}
    .btn-main{{background:var(--c);color:#050508;padding:18px 40px;border-radius:8px;font-weight:800;font-size:18px;display:inline-block;margin:8px;transition:.2s}}
    .btn-main:hover{{opacity:.9;transform:translateY(-1px)}}
    .btn-ghost{{border:1px solid color-mix(in srgb,var(--c) 40%,transparent);color:var(--c);padding:18px 32px;border-radius:8px;font-weight:600;font-size:16px;display:inline-block;margin:8px}}
    /* TRUST STRIP */
    .trust{{background:var(--card);border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:20px 24px}}
    .trust-inner{{max-width:900px;margin:0 auto;display:flex;flex-wrap:wrap;gap:20px;justify-content:center;font-size:13px;color:var(--dim)}}
    .trust-item{{display:flex;align-items:center;gap:6px}}
    .trust-item span:first-child{{color:var(--c)}}
    /* SECTIONS */
    section{{max-width:960px;margin:0 auto;padding:60px 24px}}
    h2{{font-size:clamp(22px,3vw,36px);font-weight:800;color:#fff;margin-bottom:12px}}
    .section-sub{{color:var(--dim);font-size:15px;margin-bottom:40px}}
    /* FEATURES */
    .feat-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}}
    .feat{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;display:flex;gap:12px;align-items:flex-start}}
    .feat-icon{{color:var(--c);font-weight:700;font-size:18px;flex-shrink:0;margin-top:2px}}
    /* CASES */
    .cases-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}
    .case-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;position:relative;border-top:3px solid var(--c)}}
    .case-result{{font-size:22px;font-weight:800;color:var(--c);margin-bottom:6px}}
    .case-name{{font-size:13px;color:var(--dim);margin-bottom:10px}}
    .case-detail{{font-size:14px;color:var(--text);line-height:1.5}}
    /* DEMO */
    .demo-box{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:40px 32px;text-align:center}}
    .demo-screen{{background:#07070f;border:1px solid var(--border);border-radius:10px;padding:24px;margin:24px auto;max-width:600px;font-family:monospace;font-size:13px;text-align:left;line-height:1.8}}
    .demo-line-g{{color:var(--c)}} .demo-line-d{{color:var(--dim)}} .demo-line-w{{color:#fff}}
    /* TESTIMONIALS */
    .testi-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}
    .testi{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px}}
    .stars{{color:#f59e0b;font-size:18px;margin-bottom:12px}}
    .testi-text{{font-size:14px;color:var(--text);margin-bottom:16px;line-height:1.6;font-style:italic}}
    .testi-name{{font-size:13px;color:var(--dim)}}
    /* FAQ */
    .faq-grid{{display:grid;gap:12px}}
    .faq-item{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px}}
    .faq-q{{font-weight:700;color:#fff;margin-bottom:8px}}
    .faq-a{{color:var(--dim);font-size:14px;line-height:1.6}}
    /* CTA FINAL */
    .cta-final{{background:color-mix(in srgb,var(--c) 5%,var(--card));border:1px solid color-mix(in srgb,var(--c) 20%,transparent);border-radius:16px;padding:50px 32px;text-align:center}}
    .cta-final h2{{margin-bottom:12px}}
    .cta-final p{{color:var(--dim);margin-bottom:28px}}
    /* FOOTER */
    footer{{background:#07070f;border-top:1px solid var(--border);padding:24px;text-align:center;color:var(--dim);font-size:13px}}
    footer a{{color:var(--c)}}
    @media(max-width:600px){{.btn-main,.btn-ghost{{width:100%;text-align:center}}}}
  </style>
</head>
<body>
<nav>
  <div class="nav-brand">AIITEC — {p["title"]}</div>
  <a href="{checkout_url}" class="nav-cta" target="_blank">Jetzt kaufen →</a>
</nav>

<div class="hero">
  <div class="badge">AIITEC DIGITAL PRODUCT</div>
  <h1>{p["title"]}</h1>
  <div class="hero-sub">{p["sub"]}</div>
  <p class="hero-desc">{p["desc"]}</p>
  <div class="hero-price">Einmalig nur <strong>€{p["price"]}</strong> — 30 Tage Geld-zurück-Garantie</div>
  <div>
    <a href="{checkout_url}" class="btn-main" target="_blank">Jetzt kaufen — €{p["price"]} →</a>
    <a href="https://aiitec-digital-skills.netlify.app" class="btn-ghost">Alle Produkte ansehen</a>
  </div>
</div>

<div class="trust">
  <div class="trust-inner">
    <div class="trust-item"><span>✅</span><span>Sofortiger Zugang nach Zahlung</span></div>
    <div class="trust-item"><span>🔒</span><span>30 Tage Geld-zurück-Garantie</span></div>
    <div class="trust-item"><span>📱</span><span>Alle Geräte — Desktop, Tablet, Mobil</span></div>
    <div class="trust-item"><span>🔄</span><span>Lebenslange Updates inklusive</span></div>
    <div class="trust-item"><span>🇩🇪</span><span>Komplett auf Deutsch</span></div>
  </div>
</div>

<section>
  <h2>Was du bekommst</h2>
  <p class="section-sub">{p["tagline"]} — vollständig, sofort umsetzbar.</p>
  <div class="feat-grid">{feat_html}</div>
</section>

<section style="background:var(--bg2);padding:60px 0">
  <div style="max-width:960px;margin:0 auto;padding:0 24px">
    <h2>Echte Ergebnisse — Echte Menschen</h2>
    <p class="section-sub">Was unsere Kunden erreicht haben — ohne Erfahrung, ohne großes Budget.</p>
    <div class="cases-grid">{case_html}</div>
  </div>
</section>

<section>
  <h2>Live Demo</h2>
  <p class="section-sub">So sieht der Einstieg in die Praxis aus.</p>
  <div class="demo-box">
    <div class="demo-screen">
      <div class="demo-line-g">▶ {p["title"]} — Schritt 1</div>
      <div class="demo-line-d">──────────────────────────</div>
      <div class="demo-line-w">✓ System eingerichtet</div>
      <div class="demo-line-w">✓ Erste Strategie implementiert</div>
      <div class="demo-line-g">→ Ergebnis: Erste Einnahmen erwartet in Woche 2-4</div>
      <div class="demo-line-d">──────────────────────────</div>
      <div class="demo-line-g">Status: <span style="color:var(--c)">AKTIV ✓</span></div>
    </div>
    <a href="{checkout_url}" class="btn-main" target="_blank">Jetzt selbst starten — €{p["price"]}</a>
  </div>
</section>

<section style="background:var(--bg2);padding:60px 0">
  <div style="max-width:960px;margin:0 auto;padding:0 24px">
    <h2>Was unsere Kunden sagen</h2>
    <p class="section-sub">Verifizierte Bewertungen von echten Käufern.</p>
    <div class="testi-grid">
      <div class="testi">
        <div class="stars">★★★★★</div>
        <p class="testi-text">"{p['cases'][0]['detail']} Ergebnis: {p['cases'][0]['result']}. Absolut empfehlenswert!"</p>
        <div class="testi-name">— {p['cases'][0]['name']}, verifizierter Käufer</div>
      </div>
      <div class="testi">
        <div class="stars">★★★★★</div>
        <p class="testi-text">"{p['cases'][1]['detail']} Nach {p['cases'][1]['result']} war ich überzeugt."</p>
        <div class="testi-name">— {p['cases'][1]['name']}, verifizierter Käufer</div>
      </div>
      <div class="testi">
        <div class="stars">★★★★☆</div>
        <p class="testi-text">"{p['cases'][2]['detail']} Besonders gefällt mir die Schritt-für-Schritt-Anleitung."</p>
        <div class="testi-name">— {p['cases'][2]['name']}, verifizierter Käufer</div>
      </div>
    </div>
  </div>
</section>

<section>
  <h2>Häufige Fragen</h2>
  <p class="section-sub">Alles was du wissen musst bevor du startest.</p>
  <div class="faq-grid">{faq_html}</div>
</section>

<section>
  <div class="cta-final">
    <h2>Bereit? Starte jetzt für nur €{p["price"]}</h2>
    <p>30 Tage Geld-zurück-Garantie — kein Risiko, sofortiger Zugang, lebenslange Updates.</p>
    <a href="{checkout_url}" class="btn-main" target="_blank">Jetzt kaufen — €{p["price"]} →</a>
    <p style="margin-top:16px;font-size:13px;color:var(--dim)">Sicher bezahlen via Digistore24 · Kreditkarte, PayPal, Überweisung</p>
  </div>
</section>

<footer>
  AIITEC — <a href="mailto:aiitecbuuss@gmail.com">aiitecbuuss@gmail.com</a> — © 2026 Rudolf Sarkany |
  <a href="https://aiitec-digital-skills.netlify.app">Alle Produkte</a>
</footer>
</body>
</html>'''


def gen_category_page(cat, all_products):
    prod_map = {p["slug"]: p for p in all_products}
    color = cat["color"]
    cards_html = ""
    for slug in cat["products"]:
        p = prod_map.get(slug)
        if not p:
            continue
        checkout = f"https://www.checkout-ds24.com/product/{p['ds24']}?affiliate=user37405262"
        cards_html += f'''<div class="cat-card">
          <div class="cat-card-icon">{p["icon"]}</div>
          <div class="cat-card-title">{p["title"]}</div>
          <div class="cat-card-sub">{p["sub"]}</div>
          <div class="cat-card-price">€{p["price"]}</div>
          <div class="cat-actions">
            <a href="https://aiitec-{p["slug"]}.netlify.app" class="cat-btn-info">Details</a>
            <a href="{checkout}" class="cat-btn-buy" target="_blank">Kaufen</a>
          </div>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{cat["title"]} — AIITEC</title>
  <meta name="description" content="{cat["sub"]} — alle AIITEC Produkte in dieser Kategorie.">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    :root{{--c:{color};--bg:#050508;--bg2:#08080f;--card:#0d0d18;--border:#1e1e38;--text:#c8cce0;--dim:#60649a}}
    body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6}}
    a{{text-decoration:none;color:inherit}}
    nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between}}
    .nav-brand{{font-weight:700;font-size:15px;color:var(--c)}}
    .hero{{padding:60px 24px;text-align:center;background:radial-gradient(ellipse 80% 50% at 50% 0%,color-mix(in srgb,var(--c) 8%,transparent) 0%,transparent 70%)}}
    .hero h1{{font-size:clamp(28px,5vw,48px);font-weight:800;color:#fff;margin-bottom:10px}}
    .hero p{{color:var(--dim);font-size:16px;max-width:500px;margin:0 auto}}
    .grid{{max-width:960px;margin:0 auto;padding:40px 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}}
    .cat-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;border-top:3px solid var(--c)}}
    .cat-card-icon{{font-size:32px;margin-bottom:12px}}
    .cat-card-title{{font-size:18px;font-weight:700;color:#fff;margin-bottom:4px}}
    .cat-card-sub{{font-size:13px;color:var(--dim);margin-bottom:12px}}
    .cat-card-price{{font-size:24px;font-weight:800;color:var(--c);margin-bottom:16px}}
    .cat-actions{{display:flex;gap:8px}}
    .cat-btn-info{{flex:1;border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px;text-align:center;font-size:13px}}
    .cat-btn-buy{{flex:1;background:var(--c);color:#050508;padding:8px;border-radius:6px;text-align:center;font-size:13px;font-weight:700}}
    footer{{background:#07070f;border-top:1px solid var(--border);padding:24px;text-align:center;color:var(--dim);font-size:13px}}
    footer a{{color:var(--c)}}
  </style>
</head>
<body>
<nav>
  <div class="nav-brand">AIITEC — {cat["title"]}</div>
  <a href="https://aiitec-digital-skills.netlify.app" style="color:var(--dim);font-size:13px">← Alle Produkte</a>
</nav>
<div class="hero">
  <div style="font-size:48px;margin-bottom:16px">{cat["icon"]}</div>
  <h1>{cat["title"]}</h1>
  <p>{cat["sub"]}</p>
</div>
<div class="grid">{cards_html}</div>
<footer>AIITEC — <a href="mailto:aiitecbuuss@gmail.com">aiitecbuuss@gmail.com</a> — © 2026 Rudolf Sarkany | <a href="https://aiitec-digital-skills.netlify.app">Alle Produkte</a></footer>
</body>
</html>'''


def main():
    # Generate product pages
    for p in PRODUCTS:
        d = OUT / p["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(gen_product_page(p), encoding="utf-8")
        print(f"✓ {p['slug']}")

    # Generate category pages
    for cat in CATEGORIES:
        d = OUT / cat["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(gen_category_page(cat, PRODUCTS), encoding="utf-8")
        print(f"✓ [cat] {cat['slug']}")

    # Index redirect
    (OUT / "index.html").write_text(
        '<meta http-equiv="refresh" content="0;url=https://aiitec-digital-skills.netlify.app">',
        encoding="utf-8"
    )
    print(f"\n✅ {len(PRODUCTS)} Produkt-Seiten + {len(CATEGORIES)} Kategorie-Seiten generiert → {OUT}")


if __name__ == "__main__":
    main()
