#!/usr/bin/env python3
"""
SuperMegaBot — Rotating Buyer Prospector
=========================================
Jeder Lauf sucht Firmen aus einer ANDEREN Branche/Nische.
Niemals dieselbe Firma zweimal kontaktieren.
Vollautomatisch: Suche → Kontaktdaten → Email → Log.

Quellen (alle kostenlos, kein API-Key nötig):
  - DuckDuckGo Instant Answer / HTML-Suche
  - Google News RSS-Feeds
  - Bundesanzeiger RSS (neue Firmen-Registrierungen)
  - HackerNews "Ask HN: Who is hiring"
  - Reddit (r/shopify, r/ecommerce etc.)
  - GitHub Organizations
  - Hunter.io (25 free/Monat — wenn Key vorhanden)

Export: run_prospecting_cycle() → {found, emailed, niche, companies}
"""
from __future__ import annotations

import asyncio
import email.mime.multipart
import email.mime.text
import hashlib
import json
import logging
import os
import re
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("RotatingProspector")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "buyer_prospector.db"
_DATA = _BASE / "data"
_DATA.mkdir(exist_ok=True)

# ── 60 Branchen-Nischen — jeder Lauf eine andere ──────────────────────────────
NICHES: list[dict] = [
    # E-Commerce & Retail
    {"id": "shopify_stores",    "de": "Online-Shop Betreiber",        "search": "shopify shop Deutschland betreiber", "en": "shopify store owner"},
    {"id": "dropshipper",       "de": "Dropshipping Unternehmen",      "search": "dropshipping firma Deutschland gründer", "en": "dropshipping business"},
    {"id": "amazon_seller",     "de": "Amazon FBA Verkäufer",          "search": "amazon fba seller Deutschland", "en": "amazon fba seller germany"},
    {"id": "ebay_händler",      "de": "eBay Händler",                  "search": "ebay powerseller Deutschland gewerblich", "en": "ebay powerseller germany"},
    {"id": "etsy_shops",        "de": "Etsy Kreativ-Shops",            "search": "etsy shop Deutschland handgemacht verkäufer", "en": "etsy seller germany handmade"},
    {"id": "woocommerce",       "de": "WooCommerce Shops",             "search": "woocommerce online shop Deutschland", "en": "woocommerce store germany"},
    # Tech & SaaS
    {"id": "startup_tech",      "de": "Tech-Startups",                 "search": "tech startup Deutschland funding 2026", "en": "tech startup germany 2026"},
    {"id": "saas_gründer",      "de": "SaaS-Gründer",                  "search": "saas unternehmen deutschland gründer b2b", "en": "saas founder germany"},
    {"id": "app_developer",     "de": "App-Entwickler",                "search": "app entwickler agentur deutschland", "en": "app developer agency germany"},
    {"id": "web_agentur",       "de": "Web-Agenturen",                 "search": "webdesign agentur deutschland kunden shopify", "en": "web agency germany shopify"},
    {"id": "ki_unternehmen",    "de": "KI-Unternehmen",                "search": "ki künstliche intelligenz startup deutschland 2026", "en": "ai startup germany automation"},
    {"id": "freelancer_tech",   "de": "Tech-Freelancer",               "search": "freelancer shopify entwickler deutschland", "en": "freelance shopify developer germany"},
    # Marketing & Werbung
    {"id": "marketing_agentur", "de": "Marketing-Agenturen",           "search": "digital marketing agentur deutschland kunden", "en": "digital marketing agency germany clients"},
    {"id": "seo_agentur",       "de": "SEO-Agenturen",                 "search": "seo agentur deutschland e-commerce kunden", "en": "seo agency germany ecommerce"},
    {"id": "social_media_mgr",  "de": "Social Media Manager",          "search": "social media manager deutschland selbständig agentur", "en": "social media manager germany freelance"},
    {"id": "influencer_mgmt",   "de": "Influencer-Management",         "search": "influencer marketing agentur deutschland", "en": "influencer marketing agency germany"},
    {"id": "content_creator",   "de": "Content-Ersteller",             "search": "content creator deutschland youtube instagram business", "en": "content creator germany monetize"},
    {"id": "ads_agentur",       "de": "Werbeagenturen",                "search": "google ads facebook ads agentur deutschland", "en": "ppc agency germany google ads"},
    # Handel & Großhandel
    {"id": "großhandel",        "de": "Großhändler",                   "search": "großhändler deutschland b2b online verkauf", "en": "wholesaler germany b2b online"},
    {"id": "importeur",         "de": "Importeure",                    "search": "importeur deutschland china ware verkauf", "en": "importer germany china products"},
    {"id": "brand_owner",       "de": "Markeninhaber",                 "search": "eigenmarke deutschland onlineshop aufbau", "en": "private label brand germany shopify"},
    {"id": "handelsvertreter",  "de": "Handelsvertreter",              "search": "handelsvertreter deutschland onlinevertrieb", "en": "sales representative germany online"},
    # Smart Home & Elektronik
    {"id": "smart_home_handel", "de": "Smart Home Händler",            "search": "smart home produkte händler deutschland onlineshop", "en": "smart home retailer germany"},
    {"id": "elektronik_shop",   "de": "Elektronik-Shops",              "search": "elektronik shop deutschland gadgets online", "en": "electronics shop germany online"},
    {"id": "solar_energie",     "de": "Solar-Unternehmen",             "search": "solar energie unternehmen deutschland kleinunternehmen", "en": "solar energy company germany small"},
    {"id": "iot_startup",       "de": "IoT-Startups",                  "search": "iot internet of things startup deutschland", "en": "iot startup germany hardware"},
    # Dienstleistungen
    {"id": "coaching",          "de": "Business-Coach",                "search": "business coach deutschland online kurse verkauf", "en": "business coach germany online courses"},
    {"id": "unternehmensberater","de": "Unternehmensberater",          "search": "unternehmensberater deutschland digitalisierung", "en": "business consultant germany digitalization"},
    {"id": "steuerberater",     "de": "Steuerberater Digital",         "search": "steuerberater digitale buchhaltung deutschland", "en": "tax advisor germany digital"},
    {"id": "fitnessstudio",     "de": "Fitnessstudios",                "search": "fitnessstudio deutschland online verkauf merchandise", "en": "gym germany online shop"},
    {"id": "restaurant",        "de": "Restaurants & Gastronomie",     "search": "restaurant onlineshop catering deutschland bestellung", "en": "restaurant germany online ordering"},
    {"id": "handwerk",          "de": "Handwerk & Bau",                "search": "handwerker deutschland digitalisierung online", "en": "craftsman germany digital shop"},
    # Mode & Lifestyle
    {"id": "mode_label",        "de": "Mode-Labels",                   "search": "mode label deutschland eigene kollektion online", "en": "fashion label germany own collection"},
    {"id": "streetwear",        "de": "Streetwear-Brands",             "search": "streetwear marke deutschland print on demand", "en": "streetwear brand germany printify"},
    {"id": "schmuck",           "de": "Schmuck-Shops",                 "search": "schmuck shop deutschland handgemacht onlineverkauf", "en": "jewelry shop germany handmade"},
    {"id": "beauty_kosmetik",   "de": "Beauty & Kosmetik",             "search": "beauty kosmetik onlineshop deutschland eigenmarke", "en": "beauty brand germany online shop"},
    {"id": "sport_outdoor",     "de": "Sport & Outdoor",               "search": "sportartikel outdoor shop deutschland online", "en": "sports outdoor shop germany"},
    # B2B-Dienstleister
    {"id": "fulfillment",       "de": "Fulfillment-Dienste",           "search": "fulfillment dienstleister deutschland e-commerce", "en": "fulfillment service germany ecommerce"},
    {"id": "logistik",          "de": "Logistik-Startups",             "search": "logistik startup deutschland letzte meile", "en": "logistics startup germany last mile"},
    {"id": "fotografie",        "de": "Produktfotografen",             "search": "produktfotografie studio deutschland e-commerce", "en": "product photography germany ecommerce"},
    {"id": "erp_systeme",       "de": "ERP/Warenwirtschaft",           "search": "warenwirtschaft erp system deutschland shopify integration", "en": "erp software germany shopify integration"},
    # Österreich & Schweiz
    {"id": "oesterreich_shop",  "de": "Österreich Online-Shops",      "search": "online shop österreich shopify gründer", "en": "online shop austria shopify"},
    {"id": "schweiz_shop",      "de": "Schweiz Online-Shops",          "search": "online shop schweiz e-commerce gründer", "en": "ecommerce switzerland shopify"},
    # Spezial-Nischen
    {"id": "haustier",          "de": "Haustier-Shops",                "search": "haustier shop deutschland online zubehör", "en": "pet shop germany online accessories"},
    {"id": "baby_kinder",       "de": "Baby & Kinder",                 "search": "baby kinder shop deutschland online nachhaltig", "en": "baby kids shop germany sustainable"},
    {"id": "nachhaltigkeit",    "de": "Nachhaltige Unternehmen",       "search": "nachhaltiges unternehmen deutschland shop verkauf", "en": "sustainable business germany shop"},
    {"id": "gaming",            "de": "Gaming-Unternehmen",            "search": "gaming shop deutschland merchandise zubehör online", "en": "gaming shop germany merchandise"},
    {"id": "lebensmittel",      "de": "Food & Gourmet",                "search": "lebensmittel gourmet shop deutschland online lieferung", "en": "food gourmet shop germany online"},
    {"id": "handmade",          "de": "Handgemachtes",                 "search": "handmade produkte verkauf deutschland etsy shop", "en": "handmade products germany etsy shop"},
    {"id": "digitale_produkte", "de": "Digitale Produkte",             "search": "digitale produkte verkauf deutschland kurs ebook", "en": "digital products germany course ebook"},
    {"id": "abonnement",        "de": "Abo-Box Unternehmen",           "search": "abo box subscription box deutschland aufbau", "en": "subscription box germany startup"},
    {"id": "auto_zubehör",      "de": "Auto-Zubehör",                  "search": "auto zubehör tuning shop deutschland online", "en": "car accessories shop germany online"},
    {"id": "b2b_software",      "de": "B2B-Software-Anbieter",         "search": "b2b software deutschland anbieter automation", "en": "b2b software germany automation vendor"},
    {"id": "freelancer_design", "de": "Designer-Freelancer",           "search": "freelancer designer deutschland shopify branding", "en": "freelance designer germany shopify branding"},
    {"id": "podcast_creator",   "de": "Podcast-Ersteller",             "search": "podcast creator deutschland monetarisierung shop", "en": "podcast creator germany monetize shop"},
    {"id": "online_kurs",       "de": "Online-Kurs-Anbieter",          "search": "online kurs anbieter deutschland plattform verkauf", "en": "online course provider germany platform"},
    {"id": "print_on_demand",   "de": "Print-on-Demand",               "search": "print on demand shop deutschland anbieter", "en": "print on demand shop germany"},
    {"id": "digistore_vendor",  "de": "Digistore24-Vendoren",          "search": "digistore24 anbieter produkt digitales info", "en": "digistore24 vendor digital product"},
    {"id": "amazon_fba_coach",  "de": "Amazon-FBA-Coaches",            "search": "amazon fba coaching deutschland kurs online", "en": "amazon fba coach germany online course"},
    {"id": "neustart_gründer",  "de": "Neugründungen 2026",            "search": "unternehmen gründung 2026 deutschland online shop", "en": "new business 2026 germany online"},
]

EMAIL_TEMPLATES: dict[str, dict] = {
    "default": {
        "subject": "Automatisierung für {firma_name} — 10 Min. Demo?",
        "html": """
<p>Hallo {anrede},</p>

<p>ich bin auf <strong>{firma_name}</strong> aufmerksam geworden und sehe großes Potenzial für eine Zusammenarbeit.</p>

<p>Wir helfen {branche_de}-Unternehmen dabei, ihre <strong>Verkaufs- und Marketingprozesse vollautomatisch</strong> zu skalieren:</p>

<ul>
  <li>✅ <strong>Shopify-Automatisierung</strong> — Produkte, Preise, SEO automatisch optimieren</li>
  <li>✅ <strong>Email-Marketing</strong> — Klaviyo + Mailchimp vollautomatisch</li>
  <li>✅ <strong>KI-Inhalte</strong> — Produkttexte, Social Posts, SEO-Artikel täglich</li>
  <li>✅ <strong>Werbung optimieren</strong> — Google & Meta Ads automatisch skalieren/pausieren</li>
</ul>

<p>Resultate unserer Kunden: <strong>+40% Umsatz in 30 Tagen</strong>, ohne mehr Arbeitszeit.</p>

<p>Darf ich Ihnen in 10 Minuten zeigen, was konkret für {firma_name} möglich ist?</p>

<p>Einfach antworten oder hier buchen: <a href="https://ineedit.com.co">ineedit.com.co</a></p>

<p>Mit freundlichen Grüßen,<br>
<strong>Rudolf Sarkany</strong><br>
SuperMegaBot — KI-Automatisierung für E-Commerce<br>
📧 aiitecbuuss@gmail.com</p>
""",
    },
    "tech": {
        "subject": "KI-Automatisierung für {firma_name} — kostenlose Analyse",
        "html": """
<p>Hi {anrede},</p>

<p>ich schreibe Ihnen, weil <strong>{firma_name}</strong> genau der Typ Unternehmen ist, dem wir helfen können, 10x schneller zu wachsen.</p>

<p><strong>Was wir tun:</strong> KI-basierte Vollautomatisierung für {branche_de}-Unternehmen. Kein manuelles Posting mehr, keine manuellen Preisanpassungen — alles läuft autonom.</p>

<p><strong>In 48 Stunden eingerichtet:</strong></p>
<ul>
  <li>🤖 KI erstellt täglich frischen Content (SEO, Social, Emails)</li>
  <li>📊 ROAS-basierte Ad-Optimierung (schlechte Kampagnen auto-gestoppt)</li>
  <li>💰 Abandoned-Cart-Recovery automatisch</li>
  <li>🔄 Produkte, Preise, Beschreibungen täglich optimiert</li>
</ul>

<p>Kurzes 15-Min-Gespräch möglich diese Woche?</p>

<p>Beste Grüße,<br>Rudolf</p>
""",
    },
    "b2b": {
        "subject": "{firma_name} — Umsatz-Automatisierung für B2B-Anbieter",
        "html": """
<p>Sehr geehrte Damen und Herren,</p>

<p>ich bin <strong>Rudolf Sarkany</strong>, Gründer von SuperMegaBot — einer KI-Automatisierungsplattform speziell für <strong>{branche_de}</strong>.</p>

<p>Unser System hilft Unternehmen wie {firma_name}:</p>
<ul>
  <li>📧 <strong>1.200+ qualifizierte Leads/Tag</strong> automatisch identifizieren und ansprechen</li>
  <li>🏪 <strong>Online-Verkaufskanal aufbauen</strong> (Shopify, Digistore24, eigene Plattform)</li>
  <li>🤖 <strong>KI-gestützten Vertrieb</strong> — 24/7 ohne Mehraufwand</li>
</ul>

<p>Können wir kurz (15 Min.) darüber sprechen, was das konkret für {firma_name} bedeutet?</p>

<p>Mit freundlichen Grüßen,<br>
<strong>Rudolf Sarkany</strong> | SuperMegaBot<br>
🌐 ineedit.com.co</p>
""",
    },
}


# ── Database ──────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS niche_rotation (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            niche_id   TEXT NOT NULL,
            ran_at     REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS found_companies (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            domain     TEXT UNIQUE NOT NULL,
            name       TEXT,
            email      TEXT,
            niche_id   TEXT,
            source     TEXT,
            found_at   REAL NOT NULL,
            emailed    INTEGER DEFAULT 0,
            emailed_at REAL,
            smtp_user  TEXT,
            response   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_domain ON found_companies(domain);
        CREATE INDEX IF NOT EXISTS idx_emailed ON found_companies(emailed);
    """)
    con.commit()
    return con


def _next_niche() -> dict:
    """Wählt die Nische, die am längsten nicht verwendet wurde."""
    con = _db()
    try:
        rows = con.execute("SELECT niche_id, MAX(ran_at) as last FROM niche_rotation GROUP BY niche_id").fetchall()
        used = {r["niche_id"]: r["last"] for r in rows}
        # Alle Nischen die noch nie verwendet wurden → nehme erste davon
        never_used = [n for n in NICHES if n["id"] not in used]
        if never_used:
            return never_used[0]
        # Sonst: älteste zuerst
        return min(NICHES, key=lambda n: used.get(n["id"], 0))
    finally:
        con.close()


def _mark_niche_used(niche_id: str):
    con = _db()
    try:
        con.execute("INSERT INTO niche_rotation (niche_id, ran_at) VALUES (?,?)", (niche_id, time.time()))
        con.commit()
    finally:
        con.close()


def _is_known(domain: str) -> bool:
    con = _db()
    try:
        row = con.execute("SELECT id FROM found_companies WHERE domain=?", (domain,)).fetchone()
        return row is not None
    finally:
        con.close()


def _save_company(name: str, domain: str, email: str, niche_id: str, source: str):
    con = _db()
    try:
        con.execute("""
            INSERT OR IGNORE INTO found_companies (name, domain, email, niche_id, source, found_at)
            VALUES (?,?,?,?,?,?)
        """, (name, domain, email, niche_id, source, time.time()))
        con.commit()
    finally:
        con.close()


def _get_uncontacted(limit: int = 20) -> list[dict]:
    con = _db()
    try:
        rows = con.execute("""
            SELECT * FROM found_companies
            WHERE emailed=0 AND email != '' AND email IS NOT NULL
            ORDER BY found_at ASC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _mark_emailed(domain: str, smtp_user: str):
    con = _db()
    try:
        con.execute("UPDATE found_companies SET emailed=1, emailed_at=?, smtp_user=? WHERE domain=?",
                    (time.time(), smtp_user, domain))
        con.commit()
    finally:
        con.close()


# ── Suche ─────────────────────────────────────────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    """Extrahiert Email-Adressen aus beliebigem Text."""
    pattern = r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
    found = re.findall(pattern, text)
    # Filtere ungültige / Generic-Adressen
    blacklist = {"noreply", "no-reply", "info@example", "test@", "example.com",
                 "privacy@", "legal@", "press@", "support@shopify", "support@google"}
    return [e.lower() for e in found if not any(b in e.lower() for b in blacklist)]


def _extract_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
        domain = parsed.netloc.replace("www.", "").strip()
        return domain if "." in domain else ""
    except Exception:
        return ""


def _http_get(url: str, timeout: int = 10, user_agent: str = "Mozilla/5.0") -> str:
    """Simpler HTTP GET, gibt leeren String bei Fehler zurück."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(charset, errors="replace")
    except Exception as e:
        log.debug("HTTP error %s: %s", url[:60], e)
        return ""


async def search_duckduckgo(query: str, max_results: int = 15) -> list[dict]:
    """DuckDuckGo HTML-Suche — kein API-Key. Mehrere Parser-Varianten."""
    encoded = urllib.parse.quote(query)
    # Variante 1: HTML-Endpoint
    url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=de-de"
    html = _http_get(url, timeout=12, user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    results = []
    if html:
        # Alle URLs aus dem HTML extrahieren (breit)
        all_links = re.findall(r'href="(https?://(?!duckduckgo)[^"]{8,200})"', html)
        all_titles = re.findall(r'<a[^>]+class="[^"]*result[^"]*"[^>]*>(.*?)</a>', html, re.S)
        all_snips  = re.findall(r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</(?:span|div)>', html, re.S)
        seen_domains: set[str] = set()
        for i, link in enumerate(all_links):
            if len(results) >= max_results:
                break
            # Überspringe DDG-interne + Tracking-Links
            if any(x in link for x in ["duckduckgo", "bing.com/aclick", "ad.doubleclick"]):
                continue
            domain = _extract_domain(link)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            title = re.sub(r'<[^>]+>', '', all_titles[i] if i < len(all_titles) else "").strip()
            snip  = re.sub(r'<[^>]+>', '', all_snips[i]  if i < len(all_snips)  else "").strip()
            emails = _extract_emails(snip)
            results.append({"url": link, "domain": domain, "title": title, "snippet": snip, "emails": emails})

    # Variante 2: DDG Lite als Fallback
    if not results:
        url2 = f"https://lite.duckduckgo.com/lite/?q={encoded}"
        html2 = _http_get(url2, timeout=10, user_agent="Mozilla/5.0")
        if html2:
            links2  = re.findall(r'<a[^>]+href="(https?://(?!duckduckgo)[^"]{8,200})"', html2)
            for link in links2[:max_results]:
                domain = _extract_domain(link)
                if domain and domain not in {r["domain"] for r in results}:
                    results.append({"url": link, "domain": domain, "title": "", "snippet": "", "emails": []})

    await asyncio.sleep(0.5)
    return results[:max_results]


async def search_bing_rss(query: str, max_results: int = 10) -> list[dict]:
    """Bing News RSS — filtert auf echte Firmen-Domains (nicht news.bing.com)."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/news/search?q={encoded}&format=rss&mkt=de-DE"
    xml_text = _http_get(url, timeout=10)
    if not xml_text:
        return []
    results = []
    skip_domains = {"bing.com", "microsoft.com", "msn.com"}
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:max_results * 3]:
            link  = item.findtext("link", "") or ""
            title = item.findtext("title", "")
            desc  = item.findtext("description", "") or ""
            # Suche echte URLs im Description
            real_urls = re.findall(r'https?://(?!(?:bing|microsoft|msn)\.)[^\s"<>]{10,200}', desc)
            domain = _extract_domain(real_urls[0]) if real_urls else _extract_domain(link)
            if not domain or any(s in domain for s in skip_domains):
                continue
            emails = _extract_emails(desc)
            results.append({"url": real_urls[0] if real_urls else link, "domain": domain, "title": title, "snippet": desc[:200], "emails": emails})
            if len(results) >= max_results:
                break
    except ET.ParseError:
        pass
    return results


async def search_github_orgs(niche: dict, max_results: int = 10) -> list[dict]:
    """GitHub Organization Search — findet Tech-Firmen mit öffentlichen Repos."""
    token = os.getenv("GITHUB_TOKEN", "")
    keyword = niche["en"].split()[0]
    url = f"https://api.github.com/search/users?q={urllib.parse.quote(keyword)}+type:org+location:germany&per_page={max_results}"
    headers = f"Authorization: Bearer {token}\r\nUser-Agent: SuperMegaBot/1.0\r\n" if token else "User-Agent: SuperMegaBot/1.0\r\n"
    raw = _http_get(url, timeout=10)
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        for item in data.get("items", [])[:max_results]:
            login   = item.get("login", "")
            blog    = item.get("blog", "") or ""
            email   = item.get("email", "") or ""
            domain  = _extract_domain(blog) if blog else f"{login}.github.io"
            if domain:
                results.append({
                    "url": f"https://github.com/{login}",
                    "domain": domain,
                    "title": login,
                    "snippet": f"GitHub Org: {niche['de']}",
                    "emails": [email] if email and "@" in email else [],
                    "source": "github",
                })
    except (json.JSONDecodeError, KeyError):
        pass
    return results


async def search_producthunt_rss(niche: dict, max_results: int = 8) -> list[dict]:
    """Product Hunt RSS — neue Startups täglich, viele mit echten Websites."""
    url = "https://www.producthunt.com/feed"
    xml_text = _http_get(url, timeout=10)
    if not xml_text:
        return []
    results = []
    keyword = niche["en"].split()[0].lower()
    skip = {"producthunt.com", "twitter.com", "facebook.com", "instagram.com"}
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = item.findtext("title", "") or ""
            desc  = item.findtext("description", "") or ""
            link  = item.findtext("link", "") or ""
            # Nur relevante Posts
            combined = (title + " " + desc).lower()
            if not any(kw in combined for kw in [keyword, "shop", "ecommerce", "saas", "automation"]):
                continue
            # Extrahiere externe Links
            ext_urls = re.findall(r'href="(https?://(?!producthunt)[^"]{10,120})"', desc)
            for u in ext_urls[:2]:
                domain = _extract_domain(u)
                if domain and domain not in skip and "producthunt" not in domain:
                    emails = _extract_emails(desc)
                    results.append({"url": u, "domain": domain, "title": title[:60], "snippet": desc[:150], "emails": emails, "source": "producthunt"})
                    break
            if len(results) >= max_results:
                break
    except ET.ParseError:
        pass
    return results


async def search_existing_b2b_leads(niche: dict, max_results: int = 10) -> list[dict]:
    """Holt noch nicht kontaktierte Leads aus der B2B-Intent-Radar-DB."""
    try:
        b2b_db = Path(__file__).parent.parent / "data" / "b2b_intent_radar.db"
        if not b2b_db.exists():
            return []
        con = sqlite3.connect(str(b2b_db), timeout=5)
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT company_name, domain, email, summary
            FROM b2b_leads
            WHERE contacted = 0 AND email != '' AND email IS NOT NULL
            ORDER BY score DESC LIMIT ?
        """, (max_results,)).fetchall()
        con.close()
        return [{
            "url": f"https://{r['domain']}",
            "domain": r["domain"] or "",
            "title": r["company_name"] or r["domain"],
            "snippet": r["summary"] or "",
            "emails": [r["email"]] if r["email"] else [],
            "source": "b2b_radar",
        } for r in rows]
    except Exception as e:
        log.debug("b2b_leads fetch failed: %s", e)
        return []


async def search_google_news_rss(query: str, max_results: int = 10) -> list[dict]:
    """Google News RSS — extrahiert echte Artikel-Domains aus Redirect-URLs."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=de&gl=DE&ceid=DE:de"
    xml_text = _http_get(url, timeout=10)
    if not xml_text:
        return []
    results = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:max_results]:
            title   = item.findtext("title", "")
            link    = item.findtext("link", "") or ""
            desc    = item.findtext("description", "") or ""
            # Google News nutzt Redirect-URLs — echte Domain aus Titel extrahieren
            # Titel hat Format: "Artikel-Titel - Quelle"
            source_match = re.search(r' - ([^-]+)$', title)
            source_name = source_match.group(1).strip() if source_match else ""
            # URLs im Description suchen
            desc_urls = re.findall(r'https?://(?!news\.google\.com)[^\s"<>]{10,150}', desc)
            real_domain = _extract_domain(desc_urls[0]) if desc_urls else ""
            if not real_domain and source_name:
                # Grobe Domain-Annäherung aus Quelle (z.B. "Heise Online" → heise.de)
                clean = source_name.lower().replace(" ", "").replace("-", "")[:20]
                real_domain = clean + ".de" if len(clean) > 3 else ""
            emails = _extract_emails(desc)
            if real_domain or emails:
                results.append({"title": title, "url": link, "domain": real_domain, "snippet": desc[:200], "emails": emails})
    except ET.ParseError:
        pass
    return results


async def search_reddit_rss(niche: dict, max_results: int = 10) -> list[dict]:
    """Reddit RSS-Feed — findet Firmen/Projekte aus relevanten Subreddits."""
    subreddits = ["shopify", "ecommerce", "Entrepreneur", "smallbusiness", "startups"]
    results = []
    query_encoded = urllib.parse.quote(niche["en"].split()[0])
    for sub in subreddits[:2]:
        url = f"https://www.reddit.com/r/{sub}/search.rss?q={query_encoded}&sort=new&limit={max_results}"
        xml_text = _http_get(url, timeout=10, user_agent="Mozilla/5.0 SuperMegaBot/1.0")
        if not xml_text:
            continue
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:max_results]:
                title   = (entry.findtext("atom:title", "", ns) or "").strip()
                content = (entry.findtext("atom:content", "", ns) or "")
                link_el = entry.find("atom:link", ns)
                link    = link_el.get("href", "") if link_el is not None else ""
                # Extrahiere URLs aus dem Content
                urls    = re.findall(r'https?://(?!reddit\.com|redd\.it)[^\s"<>]{10,150}', content)
                emails  = _extract_emails(content)
                for u in urls[:2]:
                    domain = _extract_domain(u)
                    if domain:
                        results.append({"title": title, "url": u, "domain": domain, "snippet": content[:200], "emails": emails})
                        break
        except ET.ParseError:
            continue
    return results[:max_results]


async def search_hackers_news(niche: dict, max_results: int = 10) -> list[dict]:
    """HackerNews 'Who is Hiring' — Tech-Startups mit Budget."""
    url = "https://hn.algolia.com/api/v1/search?tags=ask_hn&query=who+is+hiring&hitsPerPage=5"
    raw = _http_get(url, timeout=8)
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        for hit in data.get("hits", [])[:3]:
            story_id = hit.get("objectID", "")
            if not story_id:
                continue
            comments_url = f"https://hn.algolia.com/api/v1/items/{story_id}"
            raw2 = _http_get(comments_url, timeout=10)
            if not raw2:
                continue
            data2 = json.loads(raw2)
            for child in (data2.get("children") or [])[:max_results]:
                text = child.get("text", "") or ""
                if not any(kw in text.lower() for kw in ["shopify", "ecommerce", "e-commerce", "shop", niche["en"].split()[0].lower()]):
                    continue
                emails = _extract_emails(text)
                urls_found = re.findall(r'href="(https?://[^"]+)"', text)
                domain = _extract_domain(urls_found[0]) if urls_found else ""
                if domain or emails:
                    company_match = re.search(r'<i>([^<]{3,60})</i>', text)
                    name = company_match.group(1) if company_match else domain
                    results.append({"title": name, "url": urls_found[0] if urls_found else "", "domain": domain, "snippet": text[:200], "emails": emails})
    except (json.JSONDecodeError, KeyError):
        pass
    return results


async def fetch_contact_page(domain: str) -> list[str]:
    """Versucht Email aus Kontakt/Impressum-Seite zu extrahieren."""
    if not domain:
        return []
    emails: list[str] = []
    for path in ["/contact", "/impressum", "/kontakt", "/about", "/über-uns", "/ueber-uns"]:
        url = f"https://{domain}{path}"
        html = _http_get(url, timeout=8)
        if html:
            found = _extract_emails(html)
            emails.extend(found)
        if emails:
            break
        await asyncio.sleep(0.2)
    return list(set(emails))[:3]


async def hunter_lookup(domain: str) -> list[str]:
    """Hunter.io email lookup — 25 free/Monat."""
    key = os.getenv("HUNTER_API_KEY", "")
    if not key or not domain:
        return []
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={key}&limit=3"
    raw = _http_get(url, timeout=8)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [e.get("value", "") for e in data.get("data", {}).get("emails", []) if e.get("value")]
    except json.JSONDecodeError:
        return []


# ── SMTP Pool (aus mass_outreach_1000.py übernommen) ──────────────────────────

def _smtp_pool() -> list[dict]:
    pairs = [
        ("GMAIL_USER_AIITEC",    "GMAIL_APP_PASSWORD_AIITEC"),
        ("GMAIL_USER_BULLPOWER", "GMAIL_APP_PASSWORD_BULLPOWER"),
        ("GMAIL_USER_1",         "GMAIL_APP_PASSWORD_1"),
        ("GMAIL_USER_2",         "GMAIL_APP_PASSWORD_2"),
        ("GMAIL_USER_3",         "GMAIL_APP_PASSWORD_3"),
        ("GMAIL_USER_4",         "GMAIL_APP_PASSWORD_4"),
        ("GMAIL_USER_5",         "GMAIL_APP_PASSWORD_5"),
        ("GMAIL_USER_6",         "GMAIL_APP_PASSWORD_6"),
        ("GMAIL_USER_7",         "GMAIL_APP_PASSWORD_7"),
        ("GMAIL_USER_8",         "GMAIL_APP_PASSWORD_8"),
    ]
    pool = []
    for user_key, pw_key in pairs:
        user = os.getenv(user_key, "")
        pw   = os.getenv(pw_key, "")
        if user and pw:
            pool.append({"user": user, "password": pw})
    return pool


def _send_email(smtp: dict, to_email: str, subject: str, html_body: str) -> bool:
    try:
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp["user"]
        msg["To"]      = to_email
        msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(smtp["user"], smtp["password"])
            s.sendmail(smtp["user"], [to_email], msg.as_string())
        return True
    except Exception as e:
        log.debug("SMTP send failed to %s: %s", to_email, e)
        return False


def _pick_template(niche: dict) -> dict:
    """Wählt passende Email-Vorlage basierend auf Nische."""
    if niche["id"] in {"startup_tech", "saas_gründer", "app_developer", "ki_unternehmen", "iot_startup"}:
        return EMAIL_TEMPLATES["tech"]
    if niche["id"] in {"großhandel", "importeur", "fulfillment", "logistik", "erp_systeme", "b2b_software"}:
        return EMAIL_TEMPLATES["b2b"]
    return EMAIL_TEMPLATES["default"]


def _build_email(template: dict, company: dict, niche: dict) -> tuple[str, str]:
    """Füllt Vorlage mit Firmen-Daten."""
    name  = company.get("name") or company.get("domain", "Ihr Unternehmen")
    # Kurze Firma ohne Domain-Suffix
    short = name.split(".")[0].replace("-", " ").title()
    subst = {
        "firma_name":  short,
        "anrede":      "Frau/Herr",
        "branche_de":  niche["de"],
    }
    subject  = template["subject"].format(**subst)
    html     = template["html"].format(**subst)
    return subject, html


# ── Haupt-Zyklus ──────────────────────────────────────────────────────────────

async def run_prospecting_cycle(
    emails_per_run: int = 15,
    search_results_per_source: int = 10,
) -> dict:
    """
    Hauptfunktion — jeder Aufruf:
    1. Wählt ANDERE Nische als letztes Mal
    2. Sucht Unternehmen (DDG + Google News + HN)
    3. Extrahiert Emails (Kontaktseite + Hunter.io)
    4. Sendet personalisierte Emails
    5. Loggt alles in SQLite
    """
    niche = _next_niche()
    log.info("🎯 Nische: %s (%s)", niche["de"], niche["id"])
    _mark_niche_used(niche["id"])

    stats = {
        "niche": niche["id"],
        "niche_de": niche["de"],
        "found": 0,
        "new_companies": 0,
        "with_email": 0,
        "emailed": 0,
        "failed": 0,
        "companies": [],
    }

    # ── Suche ────────────────────────────────────────────────────────────────
    all_results: list[dict] = []

    # Suche 1: DDG DE
    ddg_results = await search_duckduckgo(niche["search"], search_results_per_source)
    all_results.extend(ddg_results)
    log.info("  DDG DE: %d Ergebnisse", len(ddg_results))

    # Suche 2: DDG EN
    ddg_en = await search_duckduckgo(niche["en"] + " contact email website", search_results_per_source)
    all_results.extend(ddg_en)
    log.info("  DDG EN: %d Ergebnisse", len(ddg_en))

    # Suche 3: Google News RSS
    news_results = await search_google_news_rss(niche["search"], search_results_per_source)
    all_results.extend(news_results)
    log.info("  Google News: %d Ergebnisse", len(news_results))

    # Suche 4: Bing News RSS
    bing_results = await search_bing_rss(niche["search"], search_results_per_source)
    all_results.extend(bing_results)
    log.info("  Bing News: %d Ergebnisse", len(bing_results))

    # Suche 5: Reddit RSS
    reddit_results = await search_reddit_rss(niche, search_results_per_source)
    all_results.extend(reddit_results)
    log.info("  Reddit: %d Ergebnisse", len(reddit_results))

    # Suche 6: GitHub Organisationen (Tech-Firmen)
    gh_results = await search_github_orgs(niche, search_results_per_source)
    all_results.extend(gh_results)
    log.info("  GitHub Orgs: %d Ergebnisse", len(gh_results))

    # Suche 7: Product Hunt (neue Startups)
    ph_results = await search_producthunt_rss(niche, 8)
    all_results.extend(ph_results)
    log.info("  ProductHunt: %d Ergebnisse", len(ph_results))

    # Suche 8: Bestehende B2B-Radar-Leads (noch nicht kontaktiert)
    existing = await search_existing_b2b_leads(niche, search_results_per_source)
    all_results.extend(existing)
    log.info("  B2B-Radar Leads: %d vorhandene", len(existing))

    # Suche 7: HackerNews
    hn_results = await search_hackers_news(niche, 5)
    all_results.extend(hn_results)
    log.info("  HN: %d Ergebnisse", len(hn_results))

    stats["found"] = len(all_results)

    # ── Email-Extraktion + Deduplizierung ────────────────────────────────────
    smtp_pool = _smtp_pool()
    if not smtp_pool:
        log.warning("Kein SMTP Account konfiguriert — nur Suche ohne Versand")

    template = _pick_template(niche)
    smtp_idx = 0

    for result in all_results:
        domain = result.get("domain", "")
        if not domain or len(domain) < 4:
            continue
        if _is_known(domain):
            continue

        name   = result.get("title", domain)[:80]
        emails = result.get("emails", [])

        # Kontaktseite crawlen wenn keine Email in Snippet
        if not emails:
            emails = await fetch_contact_page(domain)

        # Hunter.io als Fallback
        if not emails:
            emails = await hunter_lookup(domain)

        # Firmen speichern (auch ohne Email — für spätere Recherche)
        primary_email = emails[0] if emails else ""
        _save_company(name, domain, primary_email, niche["id"], "prospector")
        stats["new_companies"] += 1

        if not emails:
            continue
        stats["with_email"] += 1

        # Email senden
        if not smtp_pool:
            continue
        if stats["emailed"] >= emails_per_run:
            continue

        subject, html_body = _build_email(template, {"name": name, "domain": domain}, niche)
        smtp = smtp_pool[smtp_idx % len(smtp_pool)]
        smtp_idx += 1

        success = _send_email(smtp, primary_email, subject, html_body)
        if success:
            _mark_emailed(domain, smtp["user"])
            stats["emailed"] += 1
            stats["companies"].append({"name": name, "email": primary_email, "domain": domain})
            log.info("  ✅ Gesendet → %s (%s)", primary_email, name[:40])
            await asyncio.sleep(2)  # Anti-Spam-Pause zwischen Emails
        else:
            stats["failed"] += 1

    log.info("📊 Ergebnis: %d gefunden, %d neu, %d mit Email, %d gesendet",
             stats["found"], stats["new_companies"], stats["with_email"], stats["emailed"])

    # ── Telegram-Bericht ─────────────────────────────────────────────────────
    await _notify_telegram(stats, niche)

    return stats


async def _notify_telegram(stats: dict, niche: dict):
    tok  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return
    lines = [
        f"🎯 <b>Buyer Prospector — {niche['de']}</b>",
        f"🔍 {stats['found']} Firmen gefunden | {stats['new_companies']} neu",
        f"📧 {stats['with_email']} mit Email | ✅ {stats['emailed']} gesendet",
    ]
    if stats["companies"]:
        lines.append("\n<b>Kontaktiert:</b>")
        for c in stats["companies"][:5]:
            lines.append(f"  • {c['name'][:30]} → {c['email']}")
    if stats["emailed"] == 0:
        lines.append("⚠️ 0 Emails gesendet — SMTP prüfen oder keine Emails gefunden")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("Telegram notify failed: %s", e)


async def get_stats() -> dict:
    """Gibt Gesamt-Statistik zurück."""
    con = _db()
    try:
        total   = con.execute("SELECT COUNT(*) FROM found_companies").fetchone()[0]
        emailed = con.execute("SELECT COUNT(*) FROM found_companies WHERE emailed=1").fetchone()[0]
        niches  = con.execute("SELECT COUNT(DISTINCT niche_id) FROM found_companies").fetchone()[0]
        last_run = con.execute("SELECT niche_id, ran_at FROM niche_rotation ORDER BY ran_at DESC LIMIT 1").fetchone()
        return {
            "total_companies": total,
            "emailed": emailed,
            "pending": total - emailed,
            "niches_covered": niches,
            "total_niches": len(NICHES),
            "last_niche": dict(last_run) if last_run else None,
        }
    finally:
        con.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def _main():
        print("🎯 Rotating Buyer Prospector — Test-Lauf")
        result = await run_prospecting_cycle(emails_per_run=5, search_results_per_source=8)
        print(f"\nNische: {result['niche_de']}")
        print(f"Gefunden: {result['found']} | Neu: {result['new_companies']} | Email: {result['with_email']} | Gesendet: {result['emailed']}")
        stats = await get_stats()
        print(f"\nGesamt-DB: {stats['total_companies']} Firmen | {stats['emailed']} kontaktiert")
        print(f"Nischen abgedeckt: {stats['niches_covered']}/{stats['total_niches']}")

    asyncio.run(_main())
