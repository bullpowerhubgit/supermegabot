#!/usr/bin/env python3
"""
30 SMB-Outreach-Templates (Deutsch/English) für E-Commerce / Shopify-Betreiber.
Dienen als Basis für Email-Sequenzen und Telegram-DMs.
"""
from __future__ import annotations

TEMPLATES: dict[str | int, dict] = {

    # ── Erstkontakt ──────────────────────────────────────────────────────────
    1: {
        "name": "initial_shopify",
        "subject": "Shopify + Telegram Automation — kurze Frage",
        "body": """\
Hallo {name},

ich bin auf Ihren Shopify-Store aufmerksam geworden — sehr schöne Produktauswahl!

Ich arbeite mit E-Commerce-Betreibern zusammen, die ihre Shop-Automation komplett auf Autopilot stellen: Produktimport, Abandoned-Cart-Recovery, Kunden-Follow-ups — alles automatisch über Telegram gesteuert.

Hätten Sie 5 Minuten für ein kurzes Gespräch? Würde gern zeigen, was konkret für {company} möglich wäre.

Viele Grüße,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com
""",
    },

    2: {
        "name": "initial_general",
        "subject": "Automatisierung für {company} — passt das?",
        "body": """\
Hallo {name},

kurze Frage: Wie viel Zeit verbringen Sie täglich mit manuellen Shop-Aufgaben — Listings, Preisanpassungen, Kundenanfragen?

Wir automatisieren genau das. Komplett, ohne Programmierkenntnisse, direkt über Telegram.

Darf ich Ihnen in 3 Minuten zeigen wie? Einfach antworten.

Beste Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    3: {
        "name": "initial_revenue",
        "subject": "Mehr Umsatz ohne mehr Arbeit — {company}",
        "body": """\
Hallo {name},

unsere Kunden steigern ihren Shopify-Umsatz im Schnitt um 23 % — ohne mehr Personal.

Das Geheimnis: vollautomatische Abandoned-Cart-Sequenzen, KI-generierte Produktbeschreibungen und automatische Preisoptimierung.

Passt das für {company}? Ich sende Ihnen gern eine kurze Demo.

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    4: {
        "name": "initial_pain",
        "subject": "Shopify-Probleme die uns täglich begegnen",
        "body": """\
Hallo {name},

die 3 größten Zeitfresser bei Shopify-Betreibern die ich kenne:

1. Manuelle Produktpflege kostet 2–4h täglich
2. Abandoned Carts werden nicht oder zu spät recovert
3. Kein automatisches Upselling nach dem Kauf

Alle drei lassen sich vollautomatisch lösen. Interesse an einer kurzen Übersicht?

Grüße,
Rudolf | AIITEC
""",
    },

    5: {
        "name": "initial_competitor",
        "subject": "Ihre Mitbewerber automatisieren bereits",
        "body": """\
Hallo {name},

eine Beobachtung aus der Branche: Shops die Automation einsetzen, antworten 4x schneller auf Kundenanfragen und recovern 30–40 % ihrer abgebrochenen Warenkörbe.

Das sind Umsätze die ohne Automation einfach verloren gehen.

Darf ich Ihnen zeigen wie das konkret für {company} aussieht?

Beste Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    6: {
        "name": "abandoned_cart",
        "subject": "Abandoned Checkouts — automatisch zurückgewinnen",
        "body": """\
Hallo {name},

wussten Sie: 70 % aller Shopify-Warenkörbe werden abgebrochen. Ohne automatisches Follow-up ist dieses Geld weg.

Mit unserem System erhalten Kunden innerhalb von 30 Minuten eine personalisierte Erinnerung — vollautomatisch, ohne dass Sie etwas tun müssen.

Unsere Kunden recovern damit im Schnitt €800–€2.400 zusätzlich pro Monat.

Interesse an einer kurzen Demo für {company}?

Viele Grüße,
Rudolf | AIITEC
""",
    },

    7: {
        "name": "initial_telegram",
        "subject": "Shopify komplett per Telegram steuern",
        "body": """\
Hallo {name},

was wäre, wenn Sie Ihren gesamten Shopify-Store per Telegram-Nachricht steuern könnten?

• Neue Produkte importieren: /import [URL]
• Preise anpassen: /price [Produkt] [€]
• Umsatz checken: /revenue heute
• Kunden-Follow-up starten: /followup [Email]

Kein Browser, kein Dashboard — alles direkt aus Telegram.

Das bieten wir für {company}. Kurzes Gespräch möglich?

Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    8: {
        "name": "initial_digistore",
        "subject": "Digitale Produkte + Shopify — Synergie nutzen",
        "body": """\
Hallo {name},

kombinieren Sie schon physische Shopware mit digitalen Produkten? Das ist eine der profitabelsten Kombinationen im E-Commerce 2026.

Wir automatisieren beide Stränge: Shopify für physische Ware, Digistore24 für digitale — alles in einem Dashboard, alles per Telegram steuerbar.

Passt das für {company}?

Viele Grüße,
Rudolf | AIITEC
""",
    },

    9: {
        "name": "initial_ki",
        "subject": "KI-Produktbeschreibungen in 60 Sekunden",
        "body": """\
Hallo {name},

wie lange schreiben Sie aktuell eine Produktbeschreibung? 15 Minuten? 30?

Unsere KI erstellt SEO-optimierte, verkaufsstarke Beschreibungen in unter 60 Sekunden — in Deutsch, Englisch oder beiden gleichzeitig.

Für {company} könnten wir das als kostenlosen Test für 10 Produkte zeigen. Interesse?

Beste Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    10: {
        "name": "initial_b2b",
        "subject": "B2B-Automatisierung für {company}",
        "body": """\
Hallo {name},

für B2B-Shops gibt es besondere Anforderungen: Staffelpreise, individuelle Angebote, lange Entscheidungswege.

Unser System automatisiert genau das: automatische Angebotserstellung, Follow-up-Sequenzen, CRM-Integration — alles ohne manuellen Aufwand.

Darf ich Ihnen eine kurze Übersicht schicken?

Viele Grüße,
Rudolf | AIITEC
""",
    },

    # ── 24h Follow-Up ────────────────────────────────────────────────────────
    "24h": {
        "name": "followup_24h",
        "subject": "Kurze Nachfrage",
        "body": """\
Hallo {name},

ich wollte kurz nachfragen, ob meine Email vom gestrigen Tag ankam?

Falls Sie gerade keine Zeit haben — kein Problem. Ich habe auch eine kurze 3-Minuten-Demo vorbereitet, falls das einfacher ist als ein Gespräch.

Link auf Anfrage.

Viele Grüße,
Rudolf | AIITEC
""",
    },

    # ── Value-Email (Tag 3) ───────────────────────────────────────────────────
    "value": {
        "name": "value_content",
        "subject": "Für Shopify-Betreiber: 5 Automation-Tipps die sofort wirken",
        "body": """\
Hallo {name},

unabhängig davon ob wir zusammenarbeiten — hier sind 5 Dinge, die sofort Ihren Shopify-Umsatz steigern:

1. **Abandoned Cart < 30 min**: Je schneller die erste Erinnerung, desto höher die Conversion.
2. **Post-Purchase Upsell**: 35 % der Kunden kaufen ein zweites Mal wenn man es richtig anfragt.
3. **KI-Produkttitel mit Keywords**: 20–40 % mehr organischer Traffic möglich.
4. **Preisautomatisierung**: Dynamische Preise nach Wochentag/Uhrzeit steigern die Marge.
5. **WhatsApp/Telegram für Versand-Updates**: Öffnungsrate >90 % vs. 20 % Email.

Falls Sie wissen möchten wie wir das für {company} konkret umsetzen: einfach antworten.

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    # ── Closing (Tag 7) ──────────────────────────────────────────────────────
    "close": {
        "name": "trial_close",
        "subject": "7-Tage Trial — direkt starten",
        "body": """\
Hallo {name},

das ist meine letzte Email in dieser Serie — ich möchte Ihnen Zeit sparen.

Falls Sie Interesse haben: Wir bieten einen kostenlosen 7-Tage-Trial an. Keine Kreditkarte, keine Verpflichtung.

Sie sehen in einer Woche ob es für {company} passt — oder nicht. Fair?

Direktlink: {stripe_link}

Falls das nichts für Sie ist, kein Problem — ich wünsche Ihnen weiterhin viel Erfolg!

Herzliche Grüße,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com
""",
    },

    # ── Spezial-Templates ────────────────────────────────────────────────────
    11: {
        "name": "seasonal_sale",
        "subject": "Saisonale Kampagnen automatisch schalten",
        "body": """\
Hallo {name},

Black Friday, Weihnachten, Ostern — wie viel Zeit verbringen Sie mit der manuellen Vorbereitung?

Unser System plant und schaltet saisonale Kampagnen vollautomatisch: Rabattcodes, Email-Sequenzen, Social-Media-Posts — alles mit einem Klick vorgeplant.

Für {company} könnte das 10–15h Arbeit pro Saison sparen. Kurzes Gespräch?

Grüße,
Rudolf | AIITEC
""",
    },

    12: {
        "name": "review_automation",
        "subject": "Mehr Bewertungen = mehr Umsatz — automatisch",
        "body": """\
Hallo {name},

Shops mit 4,8★ oder mehr verkaufen 40 % mehr als Shops mit 4,2★.

Unser System sendet 3–5 Tage nach Lieferung automatisch eine freundliche Bewertungsanfrage — personalisiert, DSGVO-konform, per Email oder WhatsApp.

Unsere Kunden verdoppeln damit ihre Bewertungsrate in 30 Tagen.

Interesse für {company}?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    13: {
        "name": "inventory_automation",
        "subject": "Nie wieder ausverkauft oder überbevorratet",
        "body": """\
Hallo {name},

zu viel Lager kostet Geld, zu wenig Lager kostet Kunden.

Unser KI-System analysiert Ihre Verkaufsmuster und gibt automatisch Nachbestellungsempfehlungen — per Telegram, sobald der Schwellenwert unterschritten wird.

Für {company} konfigurierbar in 30 Minuten. Kurze Demo?

Grüße,
Rudolf | AIITEC
""",
    },

    14: {
        "name": "customer_retention",
        "subject": "Stammkunden sind 5x wertvoller als Neukunden",
        "body": """\
Hallo {name},

wann haben Sie zuletzt einen Kunden der seit 90 Tagen nicht gekauft hat automatisch reaktiviert?

Unser System identifiziert ruhende Kunden und sendet ihnen automatisch personalisierte Reaktivierungs-Emails mit individuellem Rabattcode.

Klingt interessant für {company}? 5 Minuten Demo?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    15: {
        "name": "social_automation",
        "subject": "Social Media für {company} auf Autopilot",
        "body": """\
Hallo {name},

Instagram, Facebook, LinkedIn — jeden Tag posten ist zeitintensiv.

Unser System erstellt und postet automatisch:
• Produktposts mit KI-Texten
• Angebote und Aktionen
• Kunden-Testimonials
• Saisonale Inhalte

Alles geplant, alles automatisch, alles mit echten Ergebnissen.

Interesse für {company}?

Grüße,
Rudolf | AIITEC
""",
    },

    16: {
        "name": "email_list_growth",
        "subject": "Email-Liste auf Autopilot wachsen lassen",
        "body": """\
Hallo {name},

wie groß ist Ihre Email-Liste aktuell? Und wächst sie jeden Monat automatisch?

Unser System integriert Exit-Intent-Popups, Post-Purchase-Opt-ins und Lead-Magneten — alles automatisch synchronisiert mit Klaviyo oder Ihrem bestehenden Email-Tool.

Für {company} lässt sich das in einem halben Tag einrichten. Kurzes Gespräch?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    17: {
        "name": "seo_automation",
        "subject": "SEO für {company} — KI optimiert täglich",
        "body": """\
Hallo {name},

Google ändert täglich seine Rankings. Manuell hinterher zu kommen ist unmöglich.

Unser KI-System analysiert täglich Ihre Rankings, optimiert Produkttitel und Meta-Descriptions, und erstellt SEO-Content automatisch.

Unsere Kunden sehen im Schnitt 30 % mehr organischen Traffic in 60 Tagen.

Demo für {company}?

Grüße,
Rudolf | AIITEC
""",
    },

    18: {
        "name": "ai_customer_service",
        "subject": "KI beantwortet Kundenanfragen für Sie",
        "body": """\
Hallo {name},

wie viele Stunden täglich bearbeiten Sie Kundenanfragen? Bestellstatus, Versandfragen, Rücksendungen?

Unser KI-Chatbot beantwortet 80 % aller Standardanfragen automatisch — 24/7, auf Deutsch und Englisch.

Für {company} lässt sich das in 2 Stunden integrieren. Interesse?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    19: {
        "name": "cross_sell",
        "subject": "Cross-Sell: +35 % Umsatz pro Bestellung",
        "body": """\
Hallo {name},

der beste Zeitpunkt für ein zweites Angebot ist direkt nach dem Kauf.

Unser System zeigt automatisch passende Ergänzungsprodukte — personalisiert basierend auf dem Warenkorb. Das steigert den durchschnittlichen Bestellwert unserer Kunden um 25–40 %.

Passt das für {company}?

Grüße,
Rudolf | AIITEC
""",
    },

    20: {
        "name": "multi_channel",
        "subject": "Shopify + Amazon + eBay — ein System",
        "body": """\
Hallo {name},

verkaufen Sie neben Shopify auch auf Amazon oder eBay? Dann wissen Sie: drei Plattformen, dreifacher Pflegeaufwand.

Unser System synchronisiert Lagerbestand, Preise und Bestellungen über alle Kanäle — in Echtzeit, vollautomatisch.

Für {company} lohnt sich das ab ca. 50 Produkten. Demo?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    21: {
        "name": "returns_automation",
        "subject": "Retouren automatisch abwickeln",
        "body": """\
Hallo {name},

Retouren kosten Zeit und nerven. Aber sie sind auch eine Chance für Kundenbindung.

Unser System automatisiert den kompletten Retourenprozess: automatische Bestätigung, Versandetiketten, Rückerstattung und optionaler Umtausch-Vorschlag.

Kunden die einfach retournieren können, kaufen 50 % häufiger wieder.

Für {company} interessant?

Grüße,
Rudolf | AIITEC
""",
    },

    22: {
        "name": "analytics_auto",
        "subject": "Ihren Shopify-Umsatz täglich per Telegram",
        "body": """\
Hallo {name},

stellen Sie sich vor, Sie erhalten jeden Morgen um 8:00 Uhr automatisch:

• Umsatz gestern
• Top-3-Produkte
• Conversion-Rate
• Offene Bestellungen
• Wichtige Alerts

Per Telegram, ohne Browser, ohne Login.

Das bieten wir für {company}. Kurze Demo?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    23: {
        "name": "affiliate_outreach",
        "subject": "Affiliate-Programm für {company} — vollautomatisch",
        "body": """\
Hallo {name},

haben Sie schon ein Affiliate-Programm? Es ist eine der günstigsten Wege um Umsatz zu skalieren — Partner verkaufen für Sie, Sie zahlen nur bei Erfolg.

Unser System erstellt und verwaltet Ihr Affiliate-Programm komplett automatisch: Tracking-Links, Provisionen, monatliche Abrechnungen.

Interesse für {company}?

Grüße,
Rudolf | AIITEC
""",
    },

    24: {
        "name": "whatsapp_outreach",
        "subject": "WhatsApp-Marketing für {company} — 90 % Öffnungsrate",
        "body": """\
Hallo {name},

Email-Öffnungsrate: 20 %. WhatsApp-Öffnungsrate: 90 %.

Unser System sendet Bestellbestätigungen, Versand-Updates und Angebote per WhatsApp — vollautomatisch, DSGVO-konform.

Für {company} lässt sich das in 24h aktivieren. Kurze Demo?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    25: {
        "name": "bundle_offer",
        "subject": "Bundles automatisch erstellen und bewerben",
        "body": """\
Hallo {name},

Produkt-Bundles verkaufen sich 2–3x besser als Einzelprodukte — aber manuell erstellen ist zeitaufwendig.

Unser KI-System analysiert Ihre meistgekauften Kombinationen und erstellt automatisch passende Bundles mit optimierten Preisen.

Für {company} interessant?

Grüße,
Rudolf | AIITEC
""",
    },

    26: {
        "name": "b2b_lead_gen",
        "subject": "B2B-Leads automatisch qualifizieren",
        "body": """\
Hallo {name},

B2B-Interessenten die auf Ihrer Website landen, verschwinden oft wortlos. Zu wenig Zeit für manuelle Follow-ups.

Unser System erkennt Unternehmens-Besucher, qualifiziert sie automatisch und startet eine personalisierte Email-Sequenz — ohne manuellen Aufwand.

Für {company} aufsetzbar in 48h. Demo?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    27: {
        "name": "price_monitor",
        "subject": "Mitbewerber-Preise automatisch beobachten",
        "body": """\
Hallo {name},

wissen Sie gerade was Ihre Mitbewerber für dieselben Produkte verlangen?

Unser System überwacht täglich die Preise Ihrer Hauptkonkurrenten und benachrichtigt Sie per Telegram wenn jemand unter Ihren Preis geht.

Für {company} einrichtbar in einer Stunde. Interesse?

Grüße,
Rudolf | AIITEC
""",
    },

    28: {
        "name": "flash_sale",
        "subject": "Flash-Sales automatisch schalten",
        "body": """\
Hallo {name},

Flash-Sales erzeugen Dringlichkeit — aber manuell zu koordinieren (Preise ändern, Email raus, Social posten, Timer einstellen) kostet 2–3 Stunden pro Aktion.

Unser System macht das in 2 Klicks: Produkt wählen, Rabatt eingeben, Dauer festlegen — der Rest läuft automatisch.

Demo für {company}?

Viele Grüße,
Rudolf Sarkany | AIITEC
""",
    },

    29: {
        "name": "loyalty_program",
        "subject": "Kundenbindung per Punkte-System — vollautomatisch",
        "body": """\
Hallo {name},

Stammkunden kaufen 5x wahrscheinlicher wieder. Aber ein Treueprogramm manuell zu betreiben ist komplex.

Unser System erstellt und verwaltet ein komplettes Punkteprogramm: Punkte vergeben, einlösen, Tier-Upgrades, automatische Reminder.

Für {company} aktivierbar in 24h. Kurze Demo?

Grüße,
Rudolf | AIITEC
""",
    },

    30: {
        "name": "full_autopilot",
        "subject": "{company} — kompletter E-Commerce-Autopilot",
        "body": """\
Hallo {name},

stellen Sie sich vor: Ihr Shop läuft komplett auf Autopilot.

Morgens erhalten Sie per Telegram einen Report. Tagsüber werden Bestellungen verarbeitet, Kunden betreut, Kampagnen geschaltet, Preise optimiert. Abends werden Abandoned Carts recovert.

Sie steuern alles per Telegram-Befehl wenn Sie wollen — oder lassen es einfach laufen.

Das ist keine Vision, das machen unsere Kunden bereits. Für {company} umsetzbar in einer Woche.

Kurzes Gespräch?

Herzliche Grüße,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com
""",
    },
}


def get_template(key: str | int, name: str = "", company: str = "", stripe_link: str = "") -> dict:
    """Gibt ein Template zurück, Platzhalter bereits ersetzt."""
    t = TEMPLATES.get(key)
    if not t:
        t = TEMPLATES[1]
    return {
        "subject": t["subject"].format(name=name, company=company, stripe_link=stripe_link),
        "body": t["body"].format(name=name, company=company, stripe_link=stripe_link),
        "name": t["name"],
    }
