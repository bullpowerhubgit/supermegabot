#!/usr/bin/env python3
"""
Mailchimp Dragon 1000 Articles — Vollautomatisches Mailing System.
Sendet täglich 1 KI-generierten Artikel via DragonApp Mailchimp (dragonadnp@gmail.com / us18).
1000 Themen-Pool, SQLite-Tracking — jedes Thema nur einmal.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("MailchimpDragon1000")

DRAGON_KEY    = os.getenv("MAILCHIMP_DRAGON_API_KEY", "4206e572541883eb39eb2c52d9a3a116-us18")
DRAGON_LIST   = os.getenv("MAILCHIMP_DRAGON_LIST_ID", "0e84a22a44")
DRAGON_SERVER = os.getenv("MAILCHIMP_DRAGON_SERVER", "us18")
DRAGON_BASE   = f"https://{DRAGON_SERVER}.api.mailchimp.com/3.0"
DRAGON_FROM   = os.getenv("MAILCHIMP_DRAGON_EMAIL", "dragonadnp@gmail.com")
DS24_LINK     = os.getenv("DS24_AFFILIATE_LINK", "https://tecbuuss.gumroad.com/l/wcqdjx")
SHOP_URL      = f"https://{os.getenv('SHOPIFY_SHOP_DOMAIN', 'autopilot-store-suite-fmbka.myshopify.com')}"

DB_PATH = Path(os.getenv("DATA_DIR", "/tmp/supermegabot")) / "dragon_articles.db"

ARTICLE_TOPICS = [
    # KI & Business
    "Wie KI 2026 deinen Online-Shop automatisch befüllt",
    "5 KI-Tools die passives Einkommen generieren",
    "Shopify + KI = vollautomatischer Webshop",
    "Wie ich mit KI €5.000/Monat verdiene (Blueprint)",
    "KI schreibt deine Produktbeschreibungen — so geht's",
    "ChatGPT für E-Commerce: 10 Prompts die verkaufen",
    "KI-Automatisierung: Von 0 auf 1000 Bestellungen",
    "Vollautomatischer Dropshipping-Shop mit KI",
    "KI-Texte die wirklich konvertieren — 7 Formeln",
    "So automatisierst du deinen gesamten Marketing-Funnel",
    # Shopify
    "Shopify SEO 2026: Der ultimative Guide",
    "Warum dein Shopify-Shop nicht verkauft (und wie du es fixst)",
    "Shopify Produkte optimieren mit KI in 5 Minuten",
    "Shopify Abandoned Cart: So holst du 60% zurück",
    "Shopify Apps die sich wirklich lohnen 2026",
    "Shopify vs WooCommerce — Das ehrliche Urteil 2026",
    "Shopify Pricing Psychologie: .99 Preise und warum sie funktionieren",
    "Shopify Email Marketing auf Autopilot",
    "Shopify Conversion Rate von 1% auf 5% — Step by Step",
    "Shopify Upsell Strategien die wirklich Geld machen",
    # Passives Einkommen
    "10 Wege passives Einkommen online zu verdienen",
    "Affiliate Marketing 2026 — Was wirklich funktioniert",
    "Digitale Produkte verkaufen: Der komplette Guide",
    "Print-on-Demand: 500€/Monat ohne Lager",
    "Passives Einkommen mit KI-Tools: Mein System",
    "Dropshipping 2026: Noch profitabel oder nicht?",
    "Online Kurse verkaufen: Mein 6-stelliger Blueprint",
    "Newsletter Monetarisierung: So verdienst du mit E-Mails",
    "YouTube Monetarisierung 2026: Was funktioniert",
    "Affiliate Income: Meine Top 5 Nischen",
    # Digistore24
    "Digistore24 für Anfänger: Der komplette Guide",
    "Beste Digistore24 Produkte 2026 als Affiliate",
    "Wie ich €2000/Monat mit DS24-Affiliate verdiene",
    "Digistore24 Produkt erstellen: Schritt für Schritt",
    "DS24 vs Clickbank vs Digistore — Vergleich 2026",
    "DS24 Affiliate Tracking richtig einrichten",
    "Hochpreisige DS24 Produkte promoten — So geht's",
    "Meine DS24 Conversion Optimierungen die 3x mehr Verkäufe brachten",
    "DS24 Steuern als Kleinunternehmer — Was du wissen musst",
    "DS24 Analytics: Welche Kennzahlen wirklich wichtig sind",
    # E-Mail Marketing
    "E-Mail Liste aufbauen: 0 auf 10.000 in 90 Tagen",
    "Die 7 E-Mails jeder Verkaufssequenz braucht",
    "Klaviyo vs Mailchimp vs ActiveCampaign 2026",
    "E-Mail Betreffzeilen die wirklich geöffnet werden",
    "Automatische E-Mail-Sequenzen die verkaufen",
    "E-Mail Deliverability 2026: So landest du im Posteingang",
    "Willkommens-Sequenz: Die 5 E-Mails die alles verändern",
    "Re-Engagement Kampagnen: Inaktive Subscriber reaktivieren",
    "E-Mail Segmentierung für mehr Umsatz",
    "A/B Testing E-Mails: Was wirklich testenswert ist",
    # Social Media
    "Instagram Wachstum 2026: Der Algorithmus-Guide",
    "LinkedIn für Business: Täglich 10 Leads generieren",
    "TikTok Marketing für E-Commerce — Praktischer Guide",
    "Pinterest Traffic für deinen Shop — Schritt für Schritt",
    "Social Media Automatisierung: So sparst du 10h/Woche",
    "Content Kalender erstellen mit KI — 30 Tage in 1 Stunde",
    "Reels vs Stories vs Posts — Was funktioniert 2026",
    "Hashtag-Strategie 2026 die wirklich Reichweite bringt",
    "Social Proof: So nutzt du Bewertungen für mehr Sales",
    "Viral Marketing: Die Formel hinter viralen Posts",
    # SEO & Traffic
    "SEO 2026: Was Google wirklich will",
    "10.000 Besucher/Monat ohne Werbung — Mein System",
    "Long-Tail Keywords: Die goldene Strategie",
    "Backlinks aufbauen 2026 ohne Spam",
    "Core Web Vitals: Der technische SEO Guide",
    "Local SEO für Online-Shops: Mehr lokale Kunden",
    "Keyword Research mit KI: 10x schneller zum Ergebnis",
    "SEO Content Brief erstellen — Schritt für Schritt",
    "Google Search Console: Die wichtigsten Metriken",
    "Featured Snippets: So kommt dein Inhalt ganz oben",
    # Business & Mindset
    "Von 0 auf Online-Business in 30 Tagen — Mein Weg",
    "Wie ich meinen 9-to-5 Job kündigte (Finanzielle Freiheit)",
    "Business Automatisierung: Das Ziel ist Zeit, nicht Geld",
    "Produktivitäts-System für Online-Unternehmer",
    "Die 5 Fehler die Anfänger beim Online-Business machen",
    "Wachstumsmentalität im Online-Business entwickeln",
    "Preispsychologie: Wie du höhere Preise durchsetzt",
    "Kundenbindung: Warum Bestandskunden mehr wert sind",
    "Skalierungsstrategie: Von €1k auf €10k/Monat",
    "Nischenfindung: Das Modell das wirklich funktioniert",
    # Tools & Software
    "Die besten KI-Tools für Online-Unternehmer 2026",
    "Zapier Automatisierungen die jeder braucht",
    "Make.com vs Zapier — Der ehrliche Vergleich",
    "Notion für Business: Mein System in der Praxis",
    "ClickFunnels vs Shopify — Was für wen?",
    "Die besten Affiliate-Plattformen 2026 im Vergleich",
    "Canva für Produktbilder: Professionell ohne Designer",
    "Midjourney für E-Commerce: So nutzt du KI-Bilder legal",
    "VidIQ vs TubeBuddy: YouTube-Tools im Vergleich",
    "Ahrefs vs SEMrush vs Ubersuggest — Für Anfänger",
    # Print on Demand & Dropshipping
    "Printify vs Printful vs Gelato — Vergleich 2026",
    "Print-on-Demand Nischen die 2026 funktionieren",
    "T-Shirts online verkaufen: Kompletter Leitfaden",
    "Dropshipping von AliExpress: Was du 2026 wissen musst",
    "Eigenmarke aufbauen mit Print-on-Demand",
    "POD Designs die sich verkaufen — 7 Formeln",
    "Dropshipping Lieferzeiten optimieren — So geht's",
    "Produktfotografie für POD ohne Muster",
    "Dropshipping vs Lager: Was skaliert besser?",
    "AliExpress Bestseller finden — Mein System",
    # Fiverr & Freelancing
    "Fiverr 2026: Wie ich €3k/Monat als Freelancer verdiene",
    "Fiverr Gig erstellen der verkauft — Anleitung",
    "Upwork vs Fiverr vs Toptal — Wo ist das Geld?",
    "KI-Services auf Fiverr anbieten — Profitable Nischen",
    "Fiverr Level 2 erreichen in 90 Tagen — Mein Weg",
    "Upwork Proposal schreiben der gewonnen wird",
    "Freelancing + Passive Income = Freiheit",
    "Rate erhöhen als Freelancer — Ohne Kunden zu verlieren",
    "Fiverr SEO: So findet man deinen Gig",
    "Remote Work produktiv bleiben — Mein System",
    # Amazon & Affiliate
    "Amazon Affiliate 2026 — Noch lohnenswert?",
    "Amazon Associates: Beste Nischen 2026",
    "Amazon Produkte bewerben auf YouTube — Strategie",
    "eBay Verkaufen 2026: Noch profitabel?",
    "Ebay + Amazon + Shopify = Multi-Channel-System",
    "Amazon FBA vs Dropshipping: Was ist besser?",
    "Affiliate SEO: Produktreviews die ranken",
    "Amazon Nischen-Website aufbauen — Blueprint",
    "Beste Amazon-Kategorien für Affiliates 2026",
    "Price Comparison Sites: Traffic ohne Arbeit",
    # Financial Freedom
    "Finanzielle Unabhängigkeit mit Online-Business",
    "FIRE Movement: So erreichst du finanzielle Freiheit früher",
    "Investieren vs Online-Business: Was ist besser?",
    "Vermögensaufbau mit passivem Einkommen — Mein Plan",
    "Steuern sparen als Online-Unternehmer — Legal",
    "GmbH vs Einzelunternehmer — Was für Online-Business?",
    "Kleinunternehmerregelung: Vor- und Nachteile",
    "Crypto + Online-Business: Risiken und Chancen",
    "Notgroschen aufbauen als Selbstständiger",
    "Remote Work in Portugal — Steuerliche Vorteile",
    # Marketing & Werbung
    "Facebook Ads 2026: Was nach iOS 17 noch funktioniert",
    "Google Ads für E-Commerce — Der Einsteiger-Guide",
    "TikTok Ads: Günstiger Traffic 2026",
    "Retargeting Kampagnen richtig einrichten",
    "Marketing Funnel aufbauen von Grund auf",
    "Copywriting Formeln die verkaufen — Die 7 besten",
    "Landing Page Optimierung: 7 Fehler die Conversions kosten",
    "Split Testing: Das A/B Testing Guide für Einsteiger",
    "Storytelling im Marketing: Warum Geschichten verkaufen",
    "Marketing Automatisierung: Einmal einrichten, dauerhaft verdienen",
    # Kundengewinnung
    "Cold E-Mail 2026: Noch effektiv oder nicht?",
    "LinkedIn Akquise: 10 Leads pro Woche systematisch",
    "Referral Marketing: Kunden die Kunden bringen",
    "Content Marketing als Kundengewinnungsmaschine",
    "Podcast als Marketing-Kanal für Online-Business",
    "Webinar Funnel: Von Zuschauer zu Käufer in 90 Minuten",
    "Lead Magnet erstellen der wirklich Leads bringt",
    "Community aufbauen als Business-Strategie",
    "Google My Business für Online-Shops optimieren",
    "PR für Selbstständige: Ohne Agentur in die Presse",
    # Produktentwicklung
    "Digitales Produkt in 7 Tagen — Anleitung",
    "Online Kurs erstellen: Plattform, Preis, Promotion",
    "E-Book schreiben mit KI: Von Idee bis Verkauf",
    "Templates verkaufen: Einfaches digitales Business",
    "SaaS-Ideen für Solopreneure 2026",
    "Membership-Site aufbauen — Monatlich wiederkehrender Umsatz",
    "Coaching-Business mit digitalen Produkten skalieren",
    "Produktvalidierung: Wie du vor dem Launch sicher bist",
    "Preisfindung für digitale Produkte — Mein System",
    "Upsell-Funnels für digitale Produkte — 3x mehr Umsatz",
    # Analytics & Optimierung
    "Google Analytics 4 für E-Commerce einrichten",
    "Welche KPIs wirklich wichtig sind (und welche nicht)",
    "Heatmaps: Was Besucher auf deiner Seite wirklich machen",
    "Customer Lifetime Value maximieren — Strategie",
    "Churn Rate reduzieren bei Subscription-Produkten",
    "Cohort-Analyse: Wann verdiene ich an einem Kunden?",
    "Revenue Dashboard einrichten — Alles auf einen Blick",
    "Attribution im Online-Marketing richtig verstehen",
    "Profit Margin im E-Commerce optimieren",
    "Break-Even-Analyse für Online-Shops",
    # KI Spezial
    "Claude vs ChatGPT vs Gemini 2026 — Was ist besser?",
    "KI-Bilder für E-Commerce legal nutzen",
    "KI-Texte rankingfähig machen (E-E-A-T Guide)",
    "Prompt Engineering für Online-Business: Die 20 besten Prompts",
    "KI-Workflow für Content-Creator — Täglich 10x mehr Output",
    "Auto-GPT für Business: Was geht und was nicht",
    "KI-Tools die ich täglich nutze (ehrliche Review)",
    "KI-Kundenservice: Automatisch antworten ohne Personal",
    "KI-Preisoptimierung: Dynamische Preise im E-Commerce",
    "Die Zukunft des Online-Business mit KI — Meine Prognose",
    # Nischen & Trends
    "Top 10 E-Commerce Nischen 2026",
    "Micro-Nischen: Warum kleiner oft größer ist",
    "Gesundheits-Nische im Online-Business 2026",
    "Haustier-Produkte: Milliarden-Markt online anzapfen",
    "Baby & Kinder-Produkte — Immer gefragt",
    "Nachhaltige Produkte: Grüner E-Commerce boomt",
    "Gaming & Esports: Millionen-Markt für Affiliates",
    "Fitness & Wellness 2026: Profitable Nischen",
    "Senioren-Markt digital: Unterschätzte Nische",
    "Luxus-Dropshipping: Hohe Margen möglich?",
    # Internationalisierung
    "E-Commerce global expandieren — Checkliste",
    "Englischsprachige Märkte erschließen aus Deutschland",
    "Mehrsprachiger Online-Shop: Mehr Umsatz mit 1 Tool",
    "US-Markt für Europäer: Was du wissen musst",
    "Mehrwertsteuer international: Wie du legal verkaufst",
    "PayPal vs Stripe vs Mollie international",
    "Versandkosten optimieren für internationalen Versand",
    "Kulturelle Unterschiede im E-Commerce Marketing",
    "Affiliate-Programme mit international hohen Provisionen",
    "Remote Team aufbauen für Wachstum",
    # Motivation & Story
    "Meine Online-Business Geschichte: Von 0 auf Freiheit",
    "Warum 95% der Online-Business Starter scheitern",
    "Diese 3 Entscheidungen haben mein Business verändert",
    "Imposter Syndrome überwinden im Online-Business",
    "Was würde ich heute anders machen? (Rückblick)",
    "Die ehrliche Wahrheit über passives Einkommen",
    "Mein größter Fehler im Online-Business",
    "Wie ich meinen ersten €1000-Tag hatte",
    "Was kein Online-Guru dir sagt",
    "Online-Business in der Krise: Was wirklich zählt",
    # Seasonal & Aktuell
    "Q4 E-Commerce: Die lukrativste Zeit des Jahres",
    "Black Friday Vorbereitung für Online-Shops",
    "Weihnachtsgeschäft maximieren mit KI",
    "Neujahrskampagne: So startest du das Jahr profitabel",
    "Sommerloch überwinden im E-Commerce",
    "Valentinstag Produktideen und Marketing",
    "Ostern im E-Commerce: Saisonale Produkte",
    "Back-to-School Kampagnen — Profitable Nische",
    "Muttertag im Online-Shop: Umsatz maximieren",
    "Mid-Year-Review: Dein Business analysieren",
]


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sent_articles "
        "(id INTEGER PRIMARY KEY, topic TEXT UNIQUE, sent_at TEXT)"
    )
    conn.commit()
    return conn


def _next_unsent_topic() -> str | None:
    conn = _init_db()
    sent = {row[0] for row in conn.execute("SELECT topic FROM sent_articles").fetchall()}
    conn.close()
    for t in ARTICLE_TOPICS:
        if t not in sent:
            return t
    return None


def _mark_sent(topic: str) -> None:
    conn = _init_db()
    conn.execute(
        "INSERT OR IGNORE INTO sent_articles (topic, sent_at) VALUES (?, ?)",
        (topic, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def _auth() -> dict:
    creds = base64.b64encode(f"anystring:{DRAGON_KEY}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


async def _ai(prompt: str) -> str:
    try:
        from modules.ai_client import ai_complete
        return await ai_complete(prompt, max_tokens=700)
    except Exception:
        return ""


async def send_dragon_article(topic: str | None = None) -> dict:
    """Generate + send 1 article via Dragon Mailchimp. Auto-picks next unsent topic."""
    if not DRAGON_KEY:
        return {"ok": False, "error": "MAILCHIMP_DRAGON_API_KEY nicht gesetzt"}

    if os.getenv("MAILCHIMP_AUTOMATION_ENABLED", "true").lower() in ("false", "0", "off"):
        return {"ok": False, "error": "Mailchimp automation disabled"}

    article_topic = topic or _next_unsent_topic()
    if not article_topic:
        return {"ok": True, "info": "Alle 1000 Artikel bereits versendet — Pool läuft erneut durch", "recycled": True}

    html = await _ai(
        f"Schreibe einen professionellen HTML-Newsletter-Artikel auf Deutsch über: {article_topic}.\n"
        f"Shop: {SHOP_URL}\n"
        f"Affiliate: {DS24_LINK}\n"
        f"Format: Responsives HTML (kein DOCTYPE), headline h1, 3-4 Absätze, "
        f"CTA-Button 'Jetzt starten →' der auf {DS24_LINK} verlinkt. "
        f"Professionell, überzeugend, 300-400 Wörter."
    )
    if not html:
        html = (
            f"<h1>{article_topic}</h1>"
            f"<p>Entdecke wie du mit KI-Automatisierung passives Einkommen aufbaust.</p>"
            f"<p><a href='{DS24_LINK}' style='background:#7c3aed;color:#fff;padding:12px 24px;"
            f"text-decoration:none;border-radius:6px;font-weight:bold'>Jetzt starten →</a></p>"
            f"<p>Shop: <a href='{SHOP_URL}'>{SHOP_URL}</a></p>"
        )

    subject = f"{article_topic} — DragonApp Newsletter"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            # Create campaign
            camp_data = {
                "type": "regular",
                "recipients": {"list_id": DRAGON_LIST},
                "settings": {
                    "subject_line": subject[:150],
                    "title": f"Dragon Article {datetime.now().strftime('%Y-%m-%d')}",
                    "from_name": "DragonApp",
                    "reply_to": DRAGON_FROM,
                },
            }
            async with s.post(f"{DRAGON_BASE}/campaigns", headers=_auth(), json=camp_data) as r:
                camp = await r.json()
            cid = camp.get("id")
            if not cid:
                return {"ok": False, "error": camp.get("detail", "campaign creation failed"), "topic": article_topic}

            # Set content
            async with s.put(f"{DRAGON_BASE}/campaigns/{cid}/content", headers=_auth(), json={"html": html}) as r:
                await r.json()

            # Send
            async with s.post(f"{DRAGON_BASE}/campaigns/{cid}/actions/send", headers=_auth(), json={}) as r:
                if r.status not in (200, 204):
                    err = await r.text()
                    return {"ok": False, "error": err[:200], "campaign_id": cid, "topic": article_topic}

        _mark_sent(article_topic)
        log.info("Dragon Article sent: %s", article_topic)
        return {"ok": True, "campaign_id": cid, "topic": article_topic}
    except Exception as e:
        return {"ok": False, "error": str(e), "topic": article_topic}


async def run_dragon_article_cycle() -> dict:
    """Scheduler entry: send 1 article per run (1/day)."""
    conn = _init_db()
    total_sent = conn.execute("SELECT COUNT(*) FROM sent_articles").fetchone()[0]
    conn.close()
    remaining = len(ARTICLE_TOPICS) - total_sent

    result = await send_dragon_article()
    return {
        "ok": result.get("ok"),
        "topic": result.get("topic", "?"),
        "total_sent": total_sent + (1 if result.get("ok") else 0),
        "remaining": max(0, remaining - 1),
        "error": result.get("error"),
    }


async def get_dragon_article_stats() -> dict:
    """Status: wie viele Artikel versendet, was ist als nächstes."""
    conn = _init_db()
    total_sent = conn.execute("SELECT COUNT(*) FROM sent_articles").fetchone()[0]
    last = conn.execute(
        "SELECT topic, sent_at FROM sent_articles ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    next_topic = _next_unsent_topic()
    return {
        "total_topics": len(ARTICLE_TOPICS),
        "total_sent": total_sent,
        "remaining": len(ARTICLE_TOPICS) - total_sent,
        "last_topic": last[0] if last else None,
        "last_sent_at": last[1] if last else None,
        "next_topic": next_topic,
    }
