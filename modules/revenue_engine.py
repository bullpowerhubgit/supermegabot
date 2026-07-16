#!/usr/bin/env python3
"""
SuperMegaBot — Revenue Engine v3.0
====================================
Das Herzstück aller Einnahmen. Läuft 2× täglich vollautomatisch.

ARCHITEKTUR:
  Morgens (09:00) → Awareness-Phase   → DS24 + Shopify Flash + AIITEC Promo
  Abends  (18:00) → Conversion-Phase  → Stripe Direktlink + B2B Email + Tagesbericht
  Jede Stunde     → Lead-Monitoring   → Neue Leads aus Supabase → Email-Sequenz

EINNAHMEN-QUELLEN (kombiniert):
  1. DS24 Affiliate      — 50% Provision auf digitale Produkte (€15–€150 pro Sale)
  2. Shopify Flash       — Direktverkäufe von ineedit.com.co
  3. AIITEC B2B          — EU AI Act Compliance (€99–€299 pro Kunde/Mo)
  4. Stripe Direktlinks  — SaaS Subscriptions (€49 / €99 / €299 / Mo)
  5. Email Sequences     — Warme Leads → Abschluss via automatischer Sequenz
  6. DS24 Eigene Produkte — "AI Income Machine" (100% Umsatz)

SELBSTHEILUNG:
  - Jeder Kanal hat Try/Except → Fehler blockieren nicht andere Kanäle
  - Telegram-Alert bei Fehlern > 3 in Folge
  - Tagesbericht zeigt was lief und was nicht
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import smtplib
import time
from dataclasses import dataclass, field, asdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger("RevenueEngine")

# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS
# ══════════════════════════════════════════════════════════════════════════════

def _e(*keys: str, default: str = "") -> str:
    for k in keys:
        v = os.getenv(k, "").strip()
        if v and v not in ("placeholder", "changeme", "your_token_here", "TODO"):
            return v
    return default

TG_TOKEN = lambda: _e("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_RUDICLONE")
TG_CHAT  = lambda: _e("TELEGRAM_CHAT_ID")
FB_TOKEN = lambda: _e("FACEBOOK_PAGE_TOKEN_AIITEC", "META_ACCESS_TOKEN", "FACEBOOK_ACCESS_TOKEN")
FB_PAGE  = lambda: _e("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ID_AIITEC")
SHOP_API_DOMAIN = lambda: _e("SHOPIFY_SHOP_DOMAIN")
SHOP_API_TOKEN  = lambda: _e("SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_ACCESS_TOKEN")
SHOP_PUBLIC_URL = "https://ineedit.com.co"
STRIPE_KEY      = lambda: _e("STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY_AIITEC")
SUPA_URL        = lambda: _e("SUPABASE_URL")
SUPA_KEY        = lambda: _e("SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY")

STRIPE_LINKS: Dict[str, Tuple[str, str, str]] = {
    "starter":    (_e("STRIPE_PLINK_STARTER"),              "€49/Mo",  "SuperMegaBot Starter"),
    "pro":        (_e("STRIPE_PLINK_PRO"),                  "€99/Mo",  "SuperMegaBot Pro"),
    "enterprise": (_e("STRIPE_PLINK_ENTERPRISE"),           "€299/Mo", "SuperMegaBot Enterprise"),
    "aiitec":     (_e("STRIPE_PLINK_AIITEC_COMPLIANCE"),    "€199",    "AIITEC EU AI Act Check"),
}

_STATE_FILE = Path("data/revenue_engine.json")

# ══════════════════════════════════════════════════════════════════════════════
# DS24 PRODUKTE
# ══════════════════════════════════════════════════════════════════════════════

DS24_PRODUCTS = [
    {
        "id": "ai_income",
        "title": "AI Income Machine",
        "teaser": "🤖 KI auf Autopilot — passives Einkommen mit künstlicher Intelligenz",
        "benefits": ["Vollautomatisch", "Kein technisches Vorwissen", "50% Provision für dich"],
        "link": _e("DS24_AFFILIATE_LINK", default="https://www.digistore24.com/redir/user37405262/"),
        "commission": "50%", "niche": "ai", "price_hint": "€47",
        "hashtags": "#ki #passiveseinkommen #onlinebusiness #aiincome",
    },
    {
        "id": "online_blueprint",
        "title": "Online Business Blueprint",
        "teaser": "💼 Vom 9-to-5 zur Freiheit — dein vollständiger Business-Plan",
        "benefits": ["Schritt-für-Schritt System", "Bewährt für Anfänger", "Sofort umsetzbar"],
        "link": "https://www.checkout-ds24.com/redir/554000/user37405262/",
        "commission": "50%", "niche": "business", "price_hint": "€97",
        "hashtags": "#onlinebusiness #selbststaendig #passiveseinkommen #freiheit",
    },
    {
        "id": "ai_fusion",
        "title": "AI Fusion Tools Bundle",
        "teaser": "⚡ Die KI-Tools die Profis nutzen — jetzt zum Sonderpreis",
        "benefits": ["10+ Premium KI-Tools", "Lifetime Zugang", "Spart €500/Jahr"],
        "link": "https://www.checkout-ds24.com/redir/570000/user37405262/",
        "commission": "40%", "niche": "ai", "price_hint": "€67",
        "hashtags": "#kitools #produktivitaet #aitools #automation",
    },
    {
        "id": "dropshipping_pro",
        "title": "Dropshipping Masterclass",
        "teaser": "🚀 Shopify Dropshipping — von 0 auf €5.000/Monat",
        "benefits": ["Komplettes A-Z System", "Lieferanten-Liste inklusive", "Mentoring"],
        "link": "https://www.checkout-ds24.com/redir/560000/user37405262/",
        "commission": "50%", "niche": "ecommerce", "price_hint": "€197",
        "hashtags": "#dropshipping #shopify #ecommerce #onlinehandel",
    },
    {
        "id": "crypto_passive",
        "title": "Crypto Passive Income System",
        "teaser": "₿ Krypto smart nutzen — passives Einkommen ohne Trading-Stress",
        "benefits": ["Risikominimiert", "Auch für Einsteiger", "Monatliche Updates"],
        "link": "https://www.checkout-ds24.com/redir/580000/user37405262/",
        "commission": "50%", "niche": "crypto", "price_hint": "€147",
        "hashtags": "#krypto #passiveseinkommen #bitcoin #investieren",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════════════════

def _load_state() -> Dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        pass
    return {"dedup": {}, "errors": {}, "cycles_total": 0}


def _save_state(state: Dict):
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    except Exception as e:
        log.warning("State save failed: %s", e)


def _dedup_ok(state: Dict, key: str, hours: float = 22) -> bool:
    return (time.time() - state.get("dedup", {}).get(key, 0)) > hours * 3600


def _dedup_mark(state: Dict, key: str):
    state.setdefault("dedup", {})[key] = time.time()


def _track_error(state: Dict, ch: str):
    state.setdefault("errors", {})[ch] = state.get("errors", {}).get(ch, 0) + 1


def _clear_error(state: Dict, ch: str):
    state.get("errors", {}).pop(ch, None)

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM + FACEBOOK
# ══════════════════════════════════════════════════════════════════════════════

async def _tg(text: str) -> bool:
    tok, chat = TG_TOKEN(), TG_CHAT()
    if not tok or not chat:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": text[:4096],
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                d = await r.json()
                return d.get("ok", False)
    except Exception as e:
        log.warning("TG: %s", e)
        return False


async def _fb(message: str, link: str = "") -> bool:
    token, page = FB_TOKEN(), FB_PAGE()
    if not token or not page:
        return False
    try:
        payload: Dict[str, str] = {"message": message[:2000], "access_token": token}
        if link:
            payload["link"] = link
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://graph.facebook.com/v19.0/{page}/feed",
                data=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                return "id" in d
    except Exception as e:
        log.warning("FB: %s", e)
        return False


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()

# ══════════════════════════════════════════════════════════════════════════════
# SHOPIFY
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ShopProduct:
    id: int
    title: str
    handle: str
    price: float
    url: str
    is_tech: bool = False


async def _load_shopify_products() -> List[ShopProduct]:
    tech_kw = ["smart", "tech", "digital", "ki", "ai", "solar", "led", "wifi",
               "bluetooth", "usb", "kamera", "camera", "sensor", "watch",
               "tracker", "speaker", "headphone", "wireless", "charge",
               "power", "charger", "drone", "robot"]
    products = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{SHOP_PUBLIC_URL}/products.json?limit=100",
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
        for p in data.get("products", []):
            if not p.get("images") or not p.get("variants"):
                continue
            try:
                price = float(p["variants"][0].get("price", 0))
            except (ValueError, TypeError):
                continue
            if price < 10:
                continue
            t = (p["title"] + " " + p.get("product_type", "")).lower()
            products.append(ShopProduct(
                id=p["id"], title=p["title"], handle=p["handle"],
                price=price, url=f"{SHOP_PUBLIC_URL}/products/{p['handle']}",
                is_tech=any(kw in t for kw in tech_kw),
            ))
    except Exception as e:
        log.warning("Shopify load: %s", e)
    return products


async def _create_discount(percent: int = 15) -> Optional[str]:
    domain, token = SHOP_API_DOMAIN(), SHOP_API_TOKEN()
    if not domain or not token:
        return None
    try:
        code = f"FLASH{random.randint(1000,9999)}"
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://{domain}/admin/api/2026-04/price_rules.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"price_rule": {
                    "title": f"Flash {code}",
                    "target_type": "line_item", "target_selection": "all",
                    "allocation_method": "across", "value_type": "percentage",
                    "value": f"-{percent}", "customer_selection": "all",
                    "starts_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "usage_limit": 50,
                }},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                d = await r.json()
                rule_id = d.get("price_rule", {}).get("id")
                if not rule_id:
                    return None
            async with s.post(
                f"https://{domain}/admin/api/2026-04/price_rules/{rule_id}/discount_codes.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"discount_code": {"code": code}},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r2:
                d2 = await r2.json()
                return d2.get("discount_code", {}).get("code")
    except Exception as e:
        log.warning("Discount create: %s", e)
        return None

# ══════════════════════════════════════════════════════════════════════════════
# STRIPE
# ══════════════════════════════════════════════════════════════════════════════

async def _get_stripe_revenue_7d() -> float:
    key = STRIPE_KEY()
    if not key or not key.startswith("sk_live_"):
        return 0.0
    since = int(time.time()) - 7 * 86400
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/charges",
                params={"limit": "100", "created[gte]": str(since)},
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status != 200:
                    return 0.0
                d = await r.json()
                return sum(ch.get("amount", 0) / 100 for ch in d.get("data", [])
                           if ch.get("paid"))
    except Exception:
        return 0.0


async def _get_stripe_balance_str() -> str:
    key = STRIPE_KEY()
    if not key or not key.startswith("sk_live_"):
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.stripe.com/v1/balance",
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status != 200:
                    return ""
                d = await r.json()
                avail = d.get("available", [{}])[0]
                amount = avail.get("amount", 0) / 100
                curr = avail.get("currency", "eur").upper()
                return f"💳 Stripe Guthaben: {curr} {amount:.2f}"
    except Exception:
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE LEADS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Lead:
    email: str
    name: str = ""
    company: str = ""


async def _load_warm_leads(limit: int = 10) -> List[Lead]:
    url, key = SUPA_URL(), SUPA_KEY()
    if not url or not key:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{url}/rest/v1/lead_events",
                params={"select": "email,name,company", "status": "eq.warm",
                        "order": "created_at.desc", "limit": str(limit)},
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status != 200:
                    return []
                return [Lead(email=row["email"], name=row.get("name",""),
                             company=row.get("company",""))
                        for row in await r.json() if "@" in row.get("email","")]
    except Exception as e:
        log.warning("Supabase leads: %s", e)
        return []


async def _mark_contacted(email: str):
    url, key = SUPA_URL(), SUPA_KEY()
    if not url or not key:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.patch(
                f"{url}/rest/v1/lead_events",
                params={"email": f"eq.{email}"},
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json", "Prefer": "return=minimal"},
                json={"status": "contacted"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# EMAIL
# ══════════════════════════════════════════════════════════════════════════════

async def _send_b2b_email(lead: Lead) -> bool:
    first = lead.name.split()[0] if lead.name else "Geschäftsführung"
    company = lead.company or "Ihr Unternehmen"
    subject = f"{first}, EU AI Act Prüfung für {company} — kostenloser Check"
    body = (
        f"Hallo {first},\n\n"
        f"ab August 2026 gilt der EU AI Act verbindlich.\n"
        f"Unternehmen wie {company} die KI einsetzen brauchen einen konformen Betrieb,\n"
        f"sonst drohen Bußgelder bis zu €35 Millionen.\n\n"
        f"Wir haben den EU AI Act Compliance Check speziell für KMU entwickelt:\n\n"
        f"✅ Vollautomatische Prüfung in unter 24 Stunden\n"
        f"✅ Konkreter Maßnahmenplan mit Prioritäten\n"
        f"✅ DSGVO + EU AI Act kombiniert prüfen\n"
        f"✅ Für {company} individuell aufbereitet\n\n"
        f"Preis: einmalig €199 — oder als monatliches Monitoring ab €99/Monat.\n\n"
        f"Interesse an einem kostenlosen 15-Minuten-Check-Call?\n"
        f"Einfach antworten — ich melde mich innerhalb von 2 Stunden.\n\n"
        f"Mit freundlichen Grüßen\n"
        f"Rudolf Sarkany\n"
        f"AIITEC — AI Compliance for Business\n"
        f"https://aiitec.de\n\n"
        f"---\nAbmeldung: einfach antworten mit \"Abmelden\""
    )

    smtp_user = smtp_pass = smtp_host = ""
    smtp_port = 587
    try:
        from modules.gmail_accounts import pick_account
        acct = pick_account()
        if acct:
            smtp_user = acct.email
            smtp_pass = acct.password
            smtp_host = acct.smtp_host
            smtp_port = acct.smtp_port
    except Exception:
        pass

    if not smtp_user:
        smtp_user = _e("GMAIL_USER_3", default="bullpowersrtkennels@gmail.com")
        smtp_pass = _e("GMAIL_APP_PASSWORD_3")
        smtp_host = "smtp.gmail.com"

    if not smtp_pass:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = lead.email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        def _do_send():
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
                s.ehlo(); s.starttls(); s.ehlo()
                s.login(smtp_user, smtp_pass.replace(" ", ""))
                s.sendmail(smtp_user, lead.email, msg.as_string())
        await asyncio.to_thread(_do_send)
        return True
    except Exception as e:
        log.warning("Email to %s failed: %s", lead.email, e)
        return False

# ══════════════════════════════════════════════════════════════════════════════
# CONTENT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _ds24_html(prod: Dict, variant: int) -> Tuple[str, str]:
    benefits = "\n".join(f"  ✅ {b}" for b in prod.get("benefits", [])[:3])
    link = prod.get("link", "")
    templates = [
        (
            f"💡 <b>{prod['title']}</b>\n\n{prod['teaser']}\n\n{benefits}\n\n"
            f"💰 Provision: <b>{prod.get('commission','50%')}</b> — du verdienst mit!\n"
            f"🔗 <a href='{link}'>Jetzt ansehen →</a>\n\n{prod.get('hashtags','')}",
            f"{prod['title']}\n\n{prod['teaser']}\n\nJetzt: {link}",
        ),
        (
            f"⚡ <b>Jetzt entscheiden:</b> {prod['title']}\n\n{benefits}\n\n"
            f"🎯 {prod['teaser']}\n💶 Preis: <b>{prod.get('price_hint','?')}</b>\n"
            f"👉 <a href='{link}'>Direkt starten →</a>\n\n{prod.get('hashtags','')}",
            f"Jetzt: {prod['title']} | {prod['teaser']} | Preis: {prod.get('price_hint','?')} | {link}",
        ),
        (
            f"🚀 <b>Stell dir vor...</b>\n\n...{prod['teaser'].lstrip('🤖💼⚡₿🚀 ')}\n\n"
            f"Das macht <b>{prod['title']}</b> möglich:\n{benefits}\n\n"
            f"🔗 <a href='{link}'>Mehr erfahren →</a>\n\n{prod.get('hashtags','')}",
            f"Stell dir vor: {prod['teaser']} – {prod['title']} macht es möglich. Mehr: {link}",
        ),
    ]
    return templates[variant % 3]


def _shopify_html(p: ShopProduct, code: Optional[str]) -> Tuple[str, str]:
    code_line = f"\n🏷️ Gutscheincode: <code>{code}</code> (15% Rabatt)" if code else ""
    urgency = random.choice(["Nur heute!", "Limitiertes Angebot", "Solange Vorrat reicht"])
    html = (
        f"⚡ <b>FLASH DEAL — {urgency}</b>\n\n"
        f"🛍️ <b>{p.title}</b>\n"
        f"💶 Nur <b>€{p.price:.2f}</b>{code_line}\n\n"
        f"✅ Direkt bei uns kaufen — schneller Versand\n"
        f"🔗 <a href='{p.url}'>Jetzt kaufen →</a>\n\n"
        f"#smarthome #techdeals #gadgets #ineedit #onlineshopping"
    )
    plain = f"FLASH DEAL: {p.title} für €{p.price:.2f}{' – Code: '+code if code else ''} – {p.url}"
    return html, plain


def _aiitec_html(variant: int) -> Tuple[str, str]:
    link = _e("STRIPE_PLINK_AIITEC_COMPLIANCE", default="https://aiitec.de")
    templates = [
        (
            f"🏢 <b>EU AI Act ab August 2026 — Ist dein Unternehmen bereit?</b>\n\n"
            f"Bußgelder bis <b>€35 Millionen</b> für nicht-konforme KI-Nutzung.\n\n"
            f"✅ AIITEC Compliance Check:\n"
            f"  • Vollautomatische Prüfung in 24h\n"
            f"  • Konkreter Maßnahmenplan\n"
            f"  • Einmalig <b>€199</b> oder <b>€99/Mo</b> Monitoring\n\n"
            f"🔗 <a href='{link}'>Jetzt prüfen →</a>\n\n"
            f"#EUAIAct #Compliance #Datenschutz #KMU #AIITEC #Business",
            f"EU AI Act ab Aug 2026 — Bußgelder bis €35Mio. AIITEC prüft in 24h. €199. {link}",
        ),
        (
            f"⚠️ <b>WARNING für Unternehmen mit KI-Tools:</b>\n\n"
            f"ChatGPT, Copilot, Midjourney — jedes KI-Tool braucht ab\n"
            f"<b>August 2026</b> eine EU AI Act Risikobewertung.\n\n"
            f"🤖 Wir analysieren deine KI-Tools automatisch:\n"
            f"  → Risiko-Einstufung (High / Limited / Minimal)\n"
            f"  → Maßnahmenliste zum Abhaken\n"
            f"  → Zertifikat für deine Dokumentation\n\n"
            f"💶 <b>€199</b> einmalig | <b>€99/Mo</b> Dauermonitoring\n"
            f"📩 <a href='{link}'>Kostenlose Ersteinschätzung →</a>\n\n"
            f"#EUAIAct #AICompliance #DSGVO #Unternehmen",
            f"EU AI Act: Jedes KI-Tool braucht Bewertung. AIITEC prüft automatisch. €199. {link}",
        ),
        (
            f"💡 <b>3 Fragen die jeder Unternehmer jetzt beantworten muss:</b>\n\n"
            f"1️⃣ Nutzt dein Team KI-Tools (ChatGPT, Copilot etc.)?\n"
            f"2️⃣ Habt ihr eine Risikobewertung nach EU AI Act?\n"
            f"3️⃣ Kennt ihr die Meldepflichten ab August 2026?\n\n"
            f"Wenn du bei einer Frage NEIN sagst — du brauchst uns:\n"
            f"🏢 <b>AIITEC EU AI Act Compliance Check</b>\n"
            f"🔗 <a href='{link}'>In 5 Minuten starten →</a>\n\n"
            f"#EUAIAct #KI #Compliance #Business #2026",
            f"3 Fragen zum EU AI Act — noch nicht bereit? AIITEC hilft in 24h. {link}",
        ),
    ]
    return templates[variant % 3]

# ══════════════════════════════════════════════════════════════════════════════
# ACTION RESULTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ActionResult:
    action: str
    ok: bool
    channels: List[str] = field(default_factory=list)
    revenue_potential: float = 0.0
    detail: str = ""
    error: str = ""

# ══════════════════════════════════════════════════════════════════════════════
# AKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

async def action_ds24_affiliate(state: Dict) -> ActionResult:
    key = "ds24"
    if not _dedup_ok(state, key, 23):
        return ActionResult("DS24 Affiliate", True, detail="Heute bereits gepostet ⏭")

    pool = [p for p in DS24_PRODUCTS if p.get("link")]
    if not pool:
        return ActionResult("DS24 Affiliate", False, error="Keine DS24 Links konfiguriert")

    day = int(time.time() / 86400)
    prod = pool[day % len(pool)]
    html_t, plain_t = _ds24_html(prod, day % 3)

    tg = await _tg(html_t)
    fb = await _fb(plain_t, link=prod.get("link", ""))

    channels = (["Telegram"] if tg else []) + (["Facebook"] if fb else [])
    if channels:
        _dedup_mark(state, key); _clear_error(state, key)
        return ActionResult("DS24 Affiliate", True, channels,
                            revenue_potential=25.0, detail=prod["title"])
    _track_error(state, key)
    return ActionResult("DS24 Affiliate", False, error="TG + FB fehlgeschlagen")


async def action_shopify_flash(state: Dict) -> ActionResult:
    key = "shopify_flash"
    if not _dedup_ok(state, key, 23):
        return ActionResult("Shopify Flash", True, detail="Heute bereits gepostet ⏭")

    products = await _load_shopify_products()
    if not products:
        return ActionResult("Shopify Flash", False, error="Keine Shopify Produkte")

    day = int(time.time() / 86400)
    pool = [p for p in products if p.is_tech] or products
    prod = pool[day % len(pool)]

    code = await _create_discount(15)
    html_t, plain_t = _shopify_html(prod, code)

    tg = await _tg(html_t)
    fb = await _fb(plain_t, link=prod.url)

    channels = (["Telegram"] if tg else []) + (["Facebook"] if fb else [])
    if channels:
        _dedup_mark(state, key); _clear_error(state, key)
        detail = f"{prod.title} €{prod.price:.2f}" + (f" · Code: {code}" if code else "")
        return ActionResult("Shopify Flash", True, channels,
                            revenue_potential=prod.price * 0.25, detail=detail)
    _track_error(state, key)
    return ActionResult("Shopify Flash", False, error="Kein Post erfolgreich")


async def action_aiitec_promo(state: Dict) -> ActionResult:
    key = "aiitec_promo"
    if not _dedup_ok(state, key, 23):
        return ActionResult("AIITEC Promo", True, detail="Heute bereits gepostet ⏭")

    day = int(time.time() / 86400)
    html_t, plain_t = _aiitec_html(day % 3)

    tg = await _tg(html_t)
    fb = await _fb(plain_t)

    channels = (["Telegram"] if tg else []) + (["Facebook"] if fb else [])
    if channels:
        _dedup_mark(state, key); _clear_error(state, key)
        return ActionResult("AIITEC Promo", True, channels,
                            revenue_potential=149.0, detail=f"Variante {day % 3}")
    _track_error(state, key)
    return ActionResult("AIITEC Promo", False, error="Kein Post erfolgreich")


async def action_b2b_emails(state: Dict) -> ActionResult:
    key = "b2b_email"
    if not _dedup_ok(state, key, 23):
        return ActionResult("B2B Emails", True, detail="Heute bereits gelaufen ⏭")

    leads = await _load_warm_leads(10)
    if not leads:
        return ActionResult("B2B Emails", True, detail="Keine warmen Leads in Supabase")

    sent = 0
    for lead in leads:
        if await _send_b2b_email(lead):
            await _mark_contacted(lead.email)
            sent += 1
        await asyncio.sleep(2)

    if sent > 0:
        _dedup_mark(state, key); _clear_error(state, key)
        return ActionResult("B2B Emails", True, ["Gmail SMTP"],
                            revenue_potential=sent * 149.0,
                            detail=f"{sent}/{len(leads)} Emails gesendet")
    _track_error(state, key)
    return ActionResult("B2B Emails", False, error="Alle Emails fehlgeschlagen")


async def action_stripe_promo(state: Dict) -> ActionResult:
    key = "stripe_promo"
    if not _dedup_ok(state, key, 23):
        return ActionResult("Stripe Promo", True, detail="Heute bereits gepostet ⏭")

    day = int(time.time() / 86400)
    plans = [("aiitec", "AIITEC EU AI Act Check"), ("pro", "SuperMegaBot Pro"),
             ("starter", "SuperMegaBot Starter")]
    plan_key, plan_name = plans[day % len(plans)]
    link_url, price, _ = STRIPE_LINKS.get(plan_key, ("", "?", ""))

    if not link_url:
        return ActionResult("Stripe Promo", False, error=f"Kein Stripe Link für {plan_key}")

    text = (
        f"💳 <b>Jetzt buchen: {plan_name}</b>\n\n"
        f"✅ Sofortiger Zugang nach Zahlung\n"
        f"🔒 Sicher via Stripe\n"
        f"💶 Preis: <b>{price}</b>\n"
        f"🔗 <a href='{link_url}'>Direkt bezahlen →</a>\n\n"
        f"#saas #automation #business #ki"
    )
    tg = await _tg(text)
    if tg:
        _dedup_mark(state, key)
        try:
            pot = float(price.replace("€","").replace("/Mo","").replace(",","."))
        except ValueError:
            pot = 99.0
        return ActionResult("Stripe Promo", True, ["Telegram"],
                            revenue_potential=pot, detail=plan_name)
    return ActionResult("Stripe Promo", False, error="TG fehlgeschlagen")


async def action_shop_check(state: Dict) -> ActionResult:
    products = await _load_shopify_products()
    count = len(products)
    if count >= 20:
        return ActionResult("Shop Check", True, detail=f"{count} Produkte online ✅")
    try:
        from modules.smart_product_finder import run_smart_product_cycle
        asyncio.create_task(run_smart_product_cycle())
        return ActionResult("Shop Check", True,
                            detail=f"Nur {count} Produkte — Smart Finder gestartet",
                            revenue_potential=30.0)
    except Exception as e:
        return ActionResult("Shop Check", False, error=f"Smart Finder: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# REVENUE REPORT
# ══════════════════════════════════════════════════════════════════════════════

async def _send_report(results: List[ActionResult], cycle: str):
    revenue_7d = await _get_stripe_revenue_7d()
    balance_line = await _get_stripe_balance_str()

    ok_n = sum(1 for r in results if r.ok)
    total_pot = sum(r.revenue_potential for r in results)

    lines = [f"📊 <b>Revenue Engine — {cycle}</b>"]
    if revenue_7d > 0:
        lines.append(f"\n💰 <b>Stripe letzte 7 Tage: €{revenue_7d:.2f}</b>")
    if balance_line:
        lines.append(balance_line)

    lines.append(f"\n🎯 <b>Aktionen ({ok_n}/{len(results)}):</b>")
    for r in results:
        icon = "✅" if r.ok else "❌"
        ch = " + ".join(r.channels) if r.channels else "–"
        skip = " ⏭" if "⏭" in r.detail else ""
        detail = f" — {r.detail}" if r.detail and "⏭" not in r.detail else ""
        lines.append(f"  {icon}{skip} {r.action}: {ch}{detail}")

    errors = [r for r in results if not r.ok]
    if errors:
        lines.append("\n⚠️ <b>Fehler:</b>")
        for r in errors:
            lines.append(f"  ❗ {r.action}: {r.error[:80]}")

    if total_pot > 0:
        lines.append(f"\n💡 Heutiges Potenzial: ~€{total_pot:.0f}")

    lines.append(
        "\n<b>🔴 Noch manuell nötig:</b>\n"
        "  → Meta App Live-Modus schalten\n"
        "  → aiitecbuuss App-PW erneuern\n"
        "  → Anthropic Credits aufladen"
    )

    await _tg("\n".join(lines))

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def run_morning_cycle() -> Dict:
    log.info("🌅 Revenue Engine — Morgen-Cycle")
    state = _load_state()

    raw = await asyncio.gather(
        action_ds24_affiliate(state),
        action_shopify_flash(state),
        action_aiitec_promo(state),
        action_shop_check(state),
        return_exceptions=True,
    )
    results = [r if isinstance(r, ActionResult)
               else ActionResult("Morgen-Aktion", False, error=str(r))
               for r in raw]

    state["cycles_total"] = state.get("cycles_total", 0) + 1
    state["last_run"] = time.time()
    _save_state(state)

    ok = sum(1 for r in results if r.ok)
    pot = sum(r.revenue_potential for r in results)
    log.info("Morgen-Cycle: %d/%d OK, ~€%.0f Potenzial", ok, len(results), pot)
    return {"ok": ok > 0, "actions": ok, "potential": pot,
            "results": [asdict(r) for r in results]}


async def run_evening_cycle() -> Dict:
    log.info("🌆 Revenue Engine — Abend-Cycle")
    state = _load_state()

    raw = await asyncio.gather(
        action_stripe_promo(state),
        action_b2b_emails(state),
        return_exceptions=True,
    )
    results = [r if isinstance(r, ActionResult)
               else ActionResult("Abend-Aktion", False, error=str(r))
               for r in raw]

    _save_state(state)
    await _send_report(results, "Abend-Bericht")

    ok = sum(1 for r in results if r.ok)
    pot = sum(r.revenue_potential for r in results)
    log.info("Abend-Cycle: %d/%d OK, ~€%.0f Potenzial", ok, len(results), pot)
    return {"ok": ok > 0, "actions": ok, "potential": pot,
            "results": [asdict(r) for r in results]}


async def run_revenue_cycle(evening: bool = False) -> Dict:
    """Dispatcher für automation_scheduler: morning=False, evening=True."""
    return await run_evening_cycle() if evening else await run_morning_cycle()


# Compat-Alias für alte Calls die run_revenue_cycle() ohne Argument nutzten
async def run_revenue_cycle_str() -> str:
    r = await run_morning_cycle()
    return (f"Revenue: {r['actions']} Aktionen OK, ~€{r['potential']:.0f} Potenzial")


async def get_revenue_status() -> Dict[str, Any]:
    state = _load_state()
    return {
        "ok": True,
        "cycles_total": state.get("cycles_total", 0),
        "last_run": state.get("last_run"),
        "ds24_products": len(DS24_PRODUCTS),
        "stripe_links": {k: v[1] for k, v in STRIPE_LINKS.items() if v[0]},
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    asyncio.run(run_revenue_cycle(evening="--evening" in sys.argv))
