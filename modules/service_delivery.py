#!/usr/bin/env python3
"""
SYS-DELIVER: Automatische Service-Lieferung nach Bestellung
============================================================
Vollautonome Pipeline:
  Bestellung rein → KI generiert Inhalt → Email liefert in 48h

Produkte (product_key → Handler):
  shopify_texts       50 Shopify-Produktbeschreibungen
  ebay_listings       100 eBay/Amazon-Listings
  vertrag_check       Vertragsanalyse PDF
  makler_expose       15 Immobilien-Exposés
  rechtstexte         Impressum + AGB + Datenschutz
  social_kalender     30 Social-Posts + 2 Newsletter (Monat)
  handwerker_angebote 30 Handwerker-Angebotsschreiben
  gastro_texte        Website+Zimmer+Menü+Bewertungsantworten
  stellenanzeigen     10 Stellenanzeigen
  kfz_texte           50 Fahrzeugtexte
  fitness_content     30 Posts+Newsletter Fitness-Studio
  makler_briefe       20 Versicherungsmakler-Anschreiben

Nutzung:
  from modules.service_delivery import deliver_order
  result = await deliver_order("shopify_texts", customer_email, customer_data)
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import sqlite3
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DELIVERY] %(levelname)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ServiceDelivery")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "deliveries.db"

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

GMAIL_USER = os.getenv("GMAIL_USER_5", "aiitecbuuss@gmail.com")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD_5", "rqcd uzim npsl odgw")

# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS deliveries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key  TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                customer_data TEXT,
                status       TEXT DEFAULT 'pending',
                result_text  TEXT,
                created_at   INTEGER,
                delivered_at INTEGER,
                stripe_session TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_del_email ON deliveries(customer_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_del_status ON deliveries(status)")

def _log_order(product_key: str, email: str, data: dict, stripe_session: str = "") -> int:
    with sqlite3.connect(str(_DB_PATH)) as c:
        cur = c.execute(
            "INSERT INTO deliveries (product_key,customer_email,customer_data,created_at,stripe_session) VALUES (?,?,?,?,?)",
            (product_key, email, str(data), int(time.time()), stripe_session)
        )
        return cur.lastrowid

def _mark_delivered(order_id: int, result: str):
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute(
            "UPDATE deliveries SET status='delivered', result_text=?, delivered_at=? WHERE id=?",
            (result[:500], int(time.time()), order_id)
        )

def _mark_failed(order_id: int, error: str):
    with sqlite3.connect(str(_DB_PATH)) as c:
        c.execute(
            "UPDATE deliveries SET status='failed', result_text=? WHERE id=?",
            (error[:300], order_id)
        )

# ── KI-Generatoren pro Produkt ───────────────────────────────────────────────

async def _gen_shopify_texts(data: dict) -> str:
    from modules.claude_automation import ask
    products = data.get("products", "50 allgemeine Produkte aus Ihrem Shop")
    shop_name = data.get("shop_name", "Ihr Shopify-Shop")
    prompt = (
        f"Du bist ein E-Commerce-Texter. Erstelle 5 Beispiel-Produktbeschreibungen für '{shop_name}'. "
        f"Produkte: {products}. "
        "Jede Beschreibung: 150-200 Wörter, SEO-optimiert, emotional, mit Bullet-Points. "
        "Format: ### Produkt N: [Name]\n[Beschreibung]"
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_stellenanzeigen(data: dict) -> str:
    from modules.claude_automation import ask
    positionen = data.get("positionen", "allgemeine Positionen")
    firma = data.get("firma", "Ihr Unternehmen")
    prompt = (
        f"Erstelle 3 professionelle Stellenanzeigen für '{firma}'. "
        f"Positionen: {positionen}. "
        "Jede Anzeige: Titel, Hook-Opener, Unternehmensbeschreibung (5 Sätze), "
        "Aufgaben (5 Punkte), Profil (5 Punkte), Wir bieten (4 Punkte). "
        "Stil: modern, authentisch, employer-brand-konform."
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2500)

async def _gen_gastro_texte(data: dict) -> str:
    from modules.claude_automation import ask
    betrieb = data.get("betrieb", "Ihr Betrieb")
    typ = data.get("typ", "Hotel/Restaurant")
    ort = data.get("ort", "Deutschland")
    prompt = (
        f"Du bist Gastro-Texter. Erstelle Website-Texte für '{betrieb}' ({typ}, {ort}).\n"
        "Liefere:\n"
        "1. STARTSEITE: 3 Absätze (emotional, buchungsfördernd)\n"
        "2. ÜBER UNS: 2 Absätze (Geschichte, Werte)\n"
        "3. ZIMMER-BESCHREIBUNG Beispiel: 1 Zimmer, 150 Wörter\n"
        "4. MENÜ-TEXT: Küchen-Philosophie, 100 Wörter\n"
        "5. BEWERTUNGSANTWORT POSITIV: Vorlage\n"
        "6. BEWERTUNGSANTWORT NEGATIV: Vorlage\n"
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_kfz_texte(data: dict) -> str:
    from modules.claude_automation import ask
    haendler = data.get("haendler", "Ihr Autohaus")
    prompt = (
        f"Erstelle 5 Fahrzeugbeschreibungen für '{haendler}'. "
        "Fahrzeuge: BMW 3er (2022, 45k km), VW Passat (2020, 60k km), "
        "Mercedes A-Klasse (2023, 12k km), Audi A4 (2021, 55k km), Ford Focus (2019, 80k km). "
        "Pro Fahrzeug: emotionaler Opener (2 Sätze) + Ausstattungs-Highlights (5 Punkte) + "
        "Mobile.de-optimierter Abschluss (1 Satz). Direkt verkaufend, prägnant."
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_fitness_content(data: dict) -> str:
    from modules.claude_automation import ask
    studio = data.get("studio", "Ihr Fitness-Studio")
    typ = data.get("typ", "Fitnessstudio")
    prompt = (
        f"Erstelle Content-Kalender (1 Woche Vorschau) für '{studio}' ({typ}).\n"
        "Liefere:\n"
        "1. INSTAGRAM POST Mo (Motivation, mit Hashtags)\n"
        "2. INSTAGRAM POST Mi (Training-Tipp, mit Hashtags)\n"
        "3. FACEBOOK POST Fr (Community, mit Hashtags)\n"
        "4. NEWSLETTER (200 Wörter, Betreff + Body)\n"
        "5. ONBOARDING MAIL für neue Mitglieder (150 Wörter)\n"
        "6. REAKTIVIERUNGS-MAIL für inaktive Mitglieder (100 Wörter)\n"
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_makler_briefe(data: dict) -> str:
    from modules.claude_automation import ask
    makler = data.get("makler", "Ihr Maklerbüro")
    sparten = data.get("sparten", "KFZ, Hausrat, Leben")
    prompt = (
        f"Erstelle Angebots-Begleitschreiben für Versicherungsmakler '{makler}'. "
        f"Sparten: {sparten}.\n"
        "Liefere:\n"
        "1. ANGEBOTS-BRIEF KFZ (150 Wörter, Platzhalter: {{Kundenname}}, {{Fahrzeug}})\n"
        "2. ANGEBOTS-BRIEF HAUSRAT (150 Wörter, Platzhalter: {{Kundenname}}, {{Adresse}})\n"
        "3. NACHFASS-MAIL nach 3 Tagen (80 Wörter)\n"
        "4. NACHFASS-MAIL nach 7 Tagen mit Zusatznutzen (80 Wörter)\n"
        "Stil: seriös, vertrauensbildend, nicht aufdringlich."
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_handwerker_angebote(data: dict) -> str:
    from modules.claude_automation import ask
    firma = data.get("firma", "Ihr Handwerksbetrieb")
    gewerk = data.get("gewerk", "Allgemein")
    prompt = (
        f"Erstelle 5 professionelle Angebotsschreiben für Handwerksbetrieb '{firma}' ({gewerk}).\n"
        "Szenarien: Badezimmer-Renovierung, Elektro-Sanierung, Dacharbeiten, "
        "Küchen-Einbau, Außenanlage.\n"
        "Pro Angebot: Anrede → kurze Problembestätigung → Leistungsübersicht (4 Punkte) "
        "→ Preisrahmen-Formulierung → nächster Schritt. "
        "Seriös, handwerklich kompetent, klar."
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2000)

async def _gen_rechtstexte(data: dict) -> str:
    from modules.claude_automation import ask
    firma = data.get("firma", "Muster GmbH")
    url = data.get("url", "example.de")
    prompt = (
        f"Erstelle rechtliche Basistexte für Website '{url}' der Firma '{firma}'.\n"
        "Liefere:\n"
        "1. IMPRESSUM-VORLAGE (alle Pflichtfelder mit Platzhaltern)\n"
        "2. DATENSCHUTZERKLÄRUNG (DSGVO-konform, Standard-Website ohne Shop)\n"
        "3. AGB-VORLAGE für digitale Dienstleistungen\n"
        "Hinweis am Anfang: 'Vorlage zur rechtlichen Überprüfung durch Anwalt empfohlen.'"
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=3000)

async def _gen_social_kalender(data: dict) -> str:
    from modules.claude_automation import ask
    marke = data.get("marke", "Ihre Marke")
    branche = data.get("branche", "Allgemein")
    prompt = (
        f"Erstelle Social-Media-Kalender (2 Wochen) für '{marke}' ({branche}).\n"
        "Format pro Post: [Tag] [Kanal] [Text] [Hashtags]\n"
        "Mix: 40% Mehrwert-Tipps, 30% Produkt/Service, 20% Community, 10% Behind-Scenes.\n"
        "Dazu: 1 Newsletter-Entwurf (200 Wörter, Betreff + Body).\n"
        "Authentisch, plattformgerecht, sofort publishbar."
    )
    return await asyncio.to_thread(ask, prompt, max_tokens=2500)


async def _gen_sys18_newsletter(data: dict) -> str:
    from modules.sys18_newsletter_ki import generate_newsletter
    result = await generate_newsletter(
        kanzlei_name=data.get("kanzlei_name", "Ihre Kanzlei"),
        kanzlei_ort=data.get("ort", "Deutschland"),
        mandanten_typ=data.get("mandanten_typ", "gemischt"),
    )
    return f"BETREFF: {result['betreff']}\n\n{result['content']}"


async def _gen_sys23_expose(data: dict) -> str:
    from modules.sys23_expose_ki import generate_expose
    result = await generate_expose(data)
    return result["content"]


async def _gen_sys37_mieterbrief(data: dict) -> str:
    from modules.sys37_mieterbrief_ki import generate_brief_paket
    gesellschaft = data.get("gesellschaft", "Ihre Wohnungsgesellschaft")
    objekt = data.get("muster_objekt", "Musterstraße 1, 12345 Musterstadt")
    return await generate_brief_paket(gesellschaft, objekt)

# ── Generator-Mapping ─────────────────────────────────────────────────────────

GENERATORS = {
    "shopify_texts":       (_gen_shopify_texts,       "Shopify KI-Produktbeschreibungen"),
    "stellenanzeigen":     (_gen_stellenanzeigen,     "Stellenanzeigen KI"),
    "gastro_texte":        (_gen_gastro_texte,        "Hotel & Gastro Texte KI"),
    "kfz_texte":           (_gen_kfz_texte,           "Kfz-Händler Fahrzeugtexte KI"),
    "fitness_content":     (_gen_fitness_content,     "Fitness-Studio Content KI"),
    "makler_briefe":       (_gen_makler_briefe,       "Versicherungsmakler Angebots-KI"),
    "handwerker_angebote": (_gen_handwerker_angebote, "Handwerker Angebots-KI"),
    "rechtstexte":         (_gen_rechtstexte,         "Rechtstexte KI"),
    "social_kalender":     (_gen_social_kalender,     "Social Media KI-Kalender"),
    # SYS-18/23/37
    "sys18_newsletter":    (_gen_sys18_newsletter,    "Steuerberater Mandanten-Newsletter KI"),
    "sys23_expose":        (_gen_sys23_expose,        "Unternehmensverkauf-Exposé KI"),
    "sys37_mieterbrief":   (_gen_sys37_mieterbrief,   "Wohnungswirtschaft Mieterbrief KI"),
}

# ── Email-Versand ─────────────────────────────────────────────────────────────

def _send_delivery_email(to_email: str, product_name: str, content: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"✅ Ihre {product_name} sind fertig — AIITEC"
        msg["From"]    = f"Rudolf Sarkany | AIITEC <{GMAIL_USER}>"
        msg["To"]      = to_email

        body = f"""Sehr geehrte Damen und Herren,

Ihre {product_name} wurden erfolgreich erstellt und stehen bereit.

═══════════════════════════════════════════════════════════════
  IHRE LIEFERUNG
═══════════════════════════════════════════════════════════════

{content}

═══════════════════════════════════════════════════════════════

Diese Texte sind sofort einsatzbereit. Bitte prüfen Sie alle
Inhalte vor Veröffentlichung auf Ihre spezifischen Anforderungen.

Für Anpassungen oder Fragen: Einfach antworten!

Mit freundlichen Grüßen,
Rudolf Sarkany | AIITEC
aiitecbuuss@gmail.com

P.S.: Weitere Services mit 30% Partner-Provision:
https://dist-pi-jet-78.vercel.app
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        log.error(f"Delivery-Email Fehler an {to_email}: {e}")
        return False

# ── Haupt-Funktion ────────────────────────────────────────────────────────────

async def deliver_order(
    product_key: str,
    customer_email: str,
    customer_data: dict,
    stripe_session: str = "",
) -> dict:
    """
    Vollautomatische Bestellabwicklung:
      1. Bestellung in DB loggen
      2. KI-Inhalt generieren
      3. Delivery-Email senden
      4. Status aktualisieren
    """
    init_db()
    order_id = _log_order(product_key, customer_email, customer_data, stripe_session)
    log.info(f"Bestellung #{order_id}: {product_key} → {customer_email}")

    if product_key not in GENERATORS:
        _mark_failed(order_id, f"Unbekanntes Produkt: {product_key}")
        return {"ok": False, "error": f"Unbekanntes Produkt: {product_key}"}

    gen_fn, product_name = GENERATORS[product_key]

    try:
        content = await gen_fn(customer_data)
        ok = _send_delivery_email(customer_email, product_name, content)
        if ok:
            _mark_delivered(order_id, content)
            log.info(f"✅ Bestellung #{order_id} geliefert an {customer_email}")
            return {"ok": True, "order_id": order_id, "product": product_name}
        else:
            _mark_failed(order_id, "Email-Versand fehlgeschlagen")
            return {"ok": False, "error": "Email-Versand fehlgeschlagen"}
    except Exception as e:
        _mark_failed(order_id, str(e))
        log.error(f"Bestellung #{order_id} Fehler: {e}")
        return {"ok": False, "error": str(e)}


async def process_pending_orders():
    """Verarbeitet alle Bestellungen mit Status 'pending' aus der DB."""
    init_db()
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM deliveries WHERE status='pending' ORDER BY created_at ASC LIMIT 20"
        ).fetchall()

    results = {"processed": 0, "delivered": 0, "failed": 0}
    for row in rows:
        import json as _json
        try:
            data = _json.loads(row["customer_data"].replace("'", '"'))
        except Exception:
            data = {}
        r = await deliver_order(row["product_key"], row["customer_email"], data, row["stripe_session"] or "")
        results["processed"] += 1
        if r.get("ok"):
            results["delivered"] += 1
        else:
            results["failed"] += 1
        await asyncio.sleep(3)

    return results


if __name__ == "__main__":
    asyncio.run(process_pending_orders())
