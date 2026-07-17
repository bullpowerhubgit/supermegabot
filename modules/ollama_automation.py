#!/usr/bin/env python3
"""
Ollama-Native Automation — Lokale KI für Routine-Tasks (kein API-Credit-Verbrauch)

Aufgaben die lokal via Ollama laufen:
  - Shopify Produktbeschreibungen (DE/EN)
  - Social-Media-Posts (Instagram, Facebook, LinkedIn)
  - Email-Betreffzeilen A/B-Tests
  - SEO-Meta-Descriptions
  - Telegram-Bot-Antworten
  - Trend-Analyse-Zusammenfassungen
  - Abandoned-Cart Email-Texte

Scheduler-Tasks (alle in automation_scheduler.py registriert):
  ollama_product_descriptions  — 6h: 5 Shopify-Produkttexte generieren
  ollama_social_posts          — 4h: 3 Social-Posts für IG/FB/LinkedIn
  ollama_email_subjects        — 8h: A/B-Betreffzeilen für Outreach
  ollama_seo_meta              — 12h: Meta-Descriptions für Top-Seiten
  ollama_daily_brief           — 24h: Tages-Briefing an Telegram

CLI:
  python3 -m modules.ollama_automation --task product
  python3 -m modules.ollama_automation --task social
  python3 -m modules.ollama_automation --task brief
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

log = logging.getLogger("OllamaAuto")

_BASE = Path(__file__).resolve().parents[1]
_DATA = _BASE / "data" / "ollama_automation"
_DATA.mkdir(parents=True, exist_ok=True)


def _tg_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

def _tg_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


# ── Ollama via open_claw (Cache + Pool) ──────────────────────────────────────

async def ollama_chat(prompt: str, system: str = "", max_tokens: int = 600) -> str:
    """OpenClaw-gestützter Call (Cache + Connection-Pool aus open_claw.py)."""
    try:
        from modules.open_claw import claw_complete
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await claw_complete(full_prompt, max_tokens=max_tokens)
    except Exception:
        # Direkt-Fallback
        import aiohttp as _aio
        url   = os.getenv("OLLAMA_BASE", "http://localhost:11434")
        model = os.getenv("OLLAMA_CLAW_MODEL", "llama3.2:latest")
        msgs  = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        async with _aio.ClientSession(timeout=_aio.ClientTimeout(total=120)) as s:
            async with s.post(f"{url}/api/chat", json={
                "model": model, "messages": msgs, "stream": False,
                "options": {"num_predict": max_tokens},
            }) as r:
                data = await r.json()
                return (data.get("message") or {}).get("content", "").strip()


async def ollama_available() -> bool:
    try:
        from modules.open_claw import is_online
        return await is_online()
    except Exception:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(f"{os.getenv('OLLAMA_BASE','http://localhost:11434')}/api/tags") as r:
                    return r.status == 200
        except Exception:
            return False


# ── Task 1: Shopify Produktbeschreibungen ────────────────────────────────────

async def task_ollama_product_descriptions() -> dict[str, Any]:
    """Generiert 5 SEO-optimierte Produktbeschreibungen für Shopify (DE)."""
    if not await ollama_available():
        return {"ok": False, "error": "Ollama nicht erreichbar"}

    system = (
        "Du bist ein E-Commerce-Texter für ineedit.com.co — ein Smart-Home & Technologie-Shop. "
        "Schreibe verkaufsstarke, SEO-optimierte Produktbeschreibungen auf Deutsch. "
        "Fokus: Smart-Home, Solar, Gadgets, Elektronik. Keine Fake-Produkte, kein Plastikschrott."
    )

    # Hole echte Shopify-Produkte die keine Beschreibung haben
    products_to_describe = await _get_products_needing_description()

    results = []
    for product in products_to_describe[:5]:
        prompt = (
            f"Schreibe eine Produktbeschreibung (150-250 Wörter) für:\n"
            f"Titel: {product.get('title', 'Smart Produkt')}\n"
            f"Produkttyp: {product.get('product_type', 'Smart Home')}\n"
            f"Tags: {', '.join(product.get('tags', [])[:5])}\n\n"
            f"Format: 2-3 Absätze, Bullet-Liste mit 3 Hauptvorteilen, CTA-Satz am Ende."
        )
        try:
            desc = await ollama_chat(prompt, system=system, max_tokens=400)
            results.append({
                "product_id": product.get("id"),
                "title": product.get("title"),
                "description": desc,
            })
            log.info("✅ Beschreibung generiert: %s", product.get("title", "?")[:50])
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("Fehler bei %s: %s", product.get("title"), e)

    # Speichern
    out = _DATA / f"product_descriptions_{int(time.time())}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # In Shopify schreiben wenn Modul verfügbar
    if results:
        await _push_descriptions_to_shopify(results)

    return {"ok": True, "count": len(results), "saved": str(out)}


async def _get_products_needing_description() -> list[dict]:
    """Holt Shopify-Produkte ohne Beschreibung."""
    try:
        from modules.shopify_client import ShopifyClient
        client = ShopifyClient()
        # Produkte ohne body_html holen
        products = await client.get_products(limit=20, fields="id,title,product_type,tags,body_html")
        return [p for p in products if not p.get("body_html") or len(p.get("body_html", "")) < 50]
    except Exception as e:
        log.warning("Shopify-Produkte nicht verfügbar: %s — nutze Dummy-Liste", e)
        return [
            {"id": None, "title": "Solar Panel 100W Faltbar", "product_type": "Solar", "tags": ["solar", "outdoor", "camping"]},
            {"id": None, "title": "Smart WLAN Steckdose EU", "product_type": "Smart Home", "tags": ["smart", "wlan", "alexa"]},
            {"id": None, "title": "Dashcam 4K GPS Wifi", "product_type": "Elektronik", "tags": ["dashcam", "auto", "gps"]},
            {"id": None, "title": "RGB LED Strip 5m", "product_type": "Beleuchtung", "tags": ["led", "rgb", "smart"]},
            {"id": None, "title": "Powerstation 500Wh LiFePO4", "product_type": "Solar", "tags": ["akku", "camping", "solar"]},
        ]


async def _push_descriptions_to_shopify(results: list[dict]) -> None:
    try:
        from modules.shopify_client import ShopifyClient
        client = ShopifyClient()
        for r in results:
            if r.get("product_id"):
                await client.update_product(r["product_id"], {"body_html": r["description"]})
                log.info("Shopify aktualisiert: %s", r["product_id"])
    except Exception as e:
        log.warning("Shopify-Update übersprungen: %s", e)


# ── Post-Bereinigung (Meta-Kommentare entfernen) ──────────────────────────────

_META_PREFIXES = [
    "hier ist ein möglicher", "hier ist ein", "natürlich! hier", "gerne! hier",
    "hier ist", "post:", "instagram-post:", "facebook-post:", "linkedin-post:",
    "hier mein vorschlag:", "vorschlag:", "beispiel:", "entwurf:",
]

def _clean_post(text: str) -> str:
    """Entfernt Ollama-Meta-Kommentare und Platzhalter aus generierten Posts."""
    lines = text.strip().splitlines()
    # Erste Zeile weg wenn sie Meta-Kommentar ist
    while lines and any(lines[0].lower().startswith(p) for p in _META_PREFIXES):
        lines = lines[1:]
    text = "\n".join(lines).strip()
    # Platzhalter-Links ersetzen (case-insensitive, ohne Text kleinzuschreiben)
    import re
    shop_url = os.getenv("PUBLIC_SHOP_URL", "https://ineedit.com.co")
    for placeholder in [r"\[link zur website\]", r"\[link\]", r"\[url\]", r"\[deine website\]",
                        r"\[shop url\]", r"\[website\]", r"\[hier klicken\]", r"\[link einfügen\]"]:
        text = re.sub(placeholder, shop_url, text, flags=re.IGNORECASE)
    # Anführungszeichen außen entfernen wenn ganzer Text in Anführungszeichen
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    return text


# ── Task 2: Social-Media-Posts ───────────────────────────────────────────────

async def task_ollama_social_posts() -> dict[str, Any]:
    """Generiert 3 Social-Media-Posts (IG/FB/LinkedIn) für ineedit.com.co."""
    if not await ollama_available():
        return {"ok": False, "error": "Ollama nicht erreichbar"}

    shop_url = os.getenv("PUBLIC_SHOP_URL", "https://ineedit.com.co")
    ig_handle = "@aaiitecc"

    system = (
        "Du bist Social-Media-Manager für ineedit.com.co — ein Smart-Home, Solar & Gadget-Shop.\n"
        "REGELN (PFLICHT):\n"
        "- Antworte NUR mit dem fertigen Post-Text. Kein 'Hier ist ein Post:', kein 'Natürlich:', kein Kommentar.\n"
        "- Verwende NIEMALS Platzhalter wie [Link], [URL], [Website]. Schreibe immer die echte URL: " + shop_url + "\n"
        "- Schreibe auf Deutsch. Nur echte deutsche Wörter.\n"
        "- Kein Spam. Echter Mehrwert, konkrete Produkte, konkrete Preise wenn möglich.\n"
        "- Instagram: immer den Handle " + ig_handle + " erwähnen.\n"
    )

    topics = [
        ("Instagram",
         f"Schreibe einen Instagram-Post für ein Smart-Home-Produkt aus unserem Shop {shop_url}.\n"
         f"Erwähne den Handle {ig_handle}. Füge 4-5 relevante Hashtags ein. "
         f"Emotional, kurz, klarer Kauf-Link am Ende. Max 200 Zeichen + Hashtags.\n"
         f"Antworte NUR mit dem fertigen Post. Kein Kommentar davor."),
        ("Facebook",
         f"Schreibe einen Facebook-Post über ein Solar- oder Smart-Home-Produkt von {shop_url}.\n"
         f"Nenne einen konkreten Vorteil (z.B. Stromersparnis, Komfort). "
         f"Ende mit: Jetzt entdecken: {shop_url}\n"
         f"3-4 Sätze. Antworte NUR mit dem fertigen Post. Kein Kommentar davor."),
        ("LinkedIn",
         f"Schreibe einen LinkedIn-Post über E-Commerce-Automatisierung für Shopify-Händler.\n"
         f"Erwähne eine konkrete Zahl (z.B. '30% mehr Umsatz' oder '5 Stunden/Woche sparen').\n"
         f"Ende mit einem Link zu {shop_url} oder einem Call-to-Action.\n"
         f"4-5 Sätze professionell. Antworte NUR mit dem fertigen Post. Kein Kommentar davor."),
    ]

    posts = []
    for platform, prompt in topics:
        try:
            raw  = await ollama_chat(prompt, system=system, max_tokens=350)
            text = _clean_post(raw)
            if len(text) < 30:
                log.warning("%s-Post zu kurz nach Bereinigung (%d Zeichen) — verworfen", platform, len(text))
                continue
            posts.append({"platform": platform, "text": text, "generated_at": _now()})
            log.info("✅ %s-Post generiert (%d Zeichen)", platform, len(text))
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Post-Fehler für %s: %s", platform, e)

    # Speichern
    out = _DATA / f"social_posts_{int(time.time())}.json"
    out.write_text(json.dumps(posts, ensure_ascii=False, indent=2))

    if posts:
        await _send_posts_to_telegram(posts)

    return {"ok": True, "count": len(posts), "saved": str(out)}


async def _send_posts_to_telegram(posts: list[dict]) -> None:
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    msg = "✅ <b>Social Posts fertig — bereit zum Posten</b>\n\n"
    for p in posts:
        msg += f"<b>📱 {p['platform']}:</b>\n{p['text'][:500]}\n\n"
    msg += "🤖 <i>Lokal via Ollama — 0 API-Kosten</i>"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
            )
    except Exception as e:
        log.warning("Telegram-Fehler: %s", e)


# ── Task 3: Email-Betreffzeilen A/B ─────────────────────────────────────────

async def task_ollama_email_subjects() -> dict[str, Any]:
    """Generiert A/B-Betreffzeilen für Outreach-Emails."""
    if not await ollama_available():
        return {"ok": False, "error": "Ollama nicht erreichbar"}

    system = (
        "Du bist Email-Marketing-Experte mit Fokus auf B2B-Outreach für E-Commerce-Automation. "
        "Betreffzeilen müssen neugierig machen, konkret sein und keine Spam-Wörter enthalten."
    )

    scenarios = [
        "Erstkontakt an Shopify-Betreiber (Cold Email)",
        "Follow-up nach 48h ohne Antwort",
        "Abandoned-Cart-Recovery für E-Commerce-Kunden",
        "Reaktivierung ruhender Kontakte (90 Tage inaktiv)",
        "Upsell-Email nach erstem Kauf",
    ]

    subjects = []
    for scenario in scenarios:
        prompt = (
            f"Generiere 3 verschiedene Email-Betreffzeilen für: {scenario}\n"
            f"Format: Eine Zeile pro Betreff, nummeriert 1. 2. 3.\n"
            f"Regeln: Max 60 Zeichen, kein Spam, auf Deutsch, konkrete Zahlen wenn möglich."
        )
        try:
            result = await ollama_chat(prompt, system=system, max_tokens=200)
            subjects.append({"scenario": scenario, "subjects": result})
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Subject-Fehler für %s: %s", scenario, e)

    out = _DATA / f"email_subjects_{int(time.time())}.json"
    out.write_text(json.dumps(subjects, ensure_ascii=False, indent=2))
    return {"ok": True, "count": len(subjects), "saved": str(out)}


# ── Task 4: SEO Meta-Descriptions ────────────────────────────────────────────

async def task_ollama_seo_meta() -> dict[str, Any]:
    """Generiert SEO Meta-Descriptions für ineedit.com.co Seiten."""
    if not await ollama_available():
        return {"ok": False, "error": "Ollama nicht erreichbar"}

    system = (
        "Du bist SEO-Experte für E-Commerce. "
        "Meta-Descriptions müssen das primäre Keyword enthalten, "
        "150-160 Zeichen lang sein und zum Klicken animieren."
    )

    pages = [
        {"url": "ineedit.com.co", "keyword": "Smart Home Shop", "page_type": "Startseite"},
        {"url": "ineedit.com.co/collections/solar", "keyword": "Solar Powerstation kaufen", "page_type": "Kategorie Solar"},
        {"url": "ineedit.com.co/collections/smart-home", "keyword": "Smart Home Geräte", "page_type": "Kategorie Smart Home"},
        {"url": "ineedit.com.co/collections/elektronik", "keyword": "Gadgets Elektronik", "page_type": "Kategorie Elektronik"},
    ]

    metas = []
    for page in pages:
        prompt = (
            f"Schreibe eine SEO Meta-Description für:\n"
            f"Seite: {page['page_type']} ({page['url']})\n"
            f"Hauptkeyword: {page['keyword']}\n"
            f"Max 160 Zeichen, enthält das Keyword, animiert zum Klicken.\n"
            f"Nur die Description — kein zusätzlicher Text."
        )
        try:
            meta = _clean_post(await ollama_chat(prompt, system=system, max_tokens=80))
            metas.append({"page": page["url"], "keyword": page["keyword"], "meta": meta[:160]})
            await asyncio.sleep(1)
        except Exception as e:
            log.error("Meta-Fehler für %s: %s", page["url"], e)

    out = _DATA / f"seo_meta_{int(time.time())}.json"
    out.write_text(json.dumps(metas, ensure_ascii=False, indent=2))
    return {"ok": True, "count": len(metas), "saved": str(out)}


# ── Task 5: Tages-Briefing ───────────────────────────────────────────────────

async def task_ollama_daily_brief() -> dict[str, Any]:
    """Generiert ein Tages-Briefing mit Empfehlungen an Rudolf via Telegram."""
    if not await ollama_available():
        return {"ok": False, "error": "Ollama nicht erreichbar"}

    # Kontext sammeln
    context_parts = []

    try:
        from modules.autonomous_loop import _read_latest_report
        report = _read_latest_report()
        if report:
            mrr = report.get("payments", {}).get("mrr", 0)
            context_parts.append(f"Aktueller MRR: €{mrr}")
    except Exception:
        pass

    context = "\n".join(context_parts) or "Kein Kontext verfügbar"

    prompt = (
        f"Du bist Rudolf Sarkanys Business-Assistent für AIITEC/ineedit.com.co.\n"
        f"Heutiges Datum: {datetime.now().strftime('%d.%m.%Y')}\n"
        f"Aktueller Status: {context}\n\n"
        f"Erstelle ein kurzes Tages-Briefing (5-8 Stichpunkte) mit:\n"
        f"1. Top-3 Prioritäten für heute (E-Commerce-Fokus)\n"
        f"2. Welche Automation-Aufgaben heute automatisch laufen\n"
        f"3. Einen konkreten Wachstums-Tipp für ineedit.com.co\n"
        f"Format: Stichpunkte mit Emoji, auf Deutsch, prägnant."
    )

    try:
        brief = await ollama_chat(prompt, max_tokens=500)
        token = _tg_token()
        chat  = _tg_chat()
        if token and chat:
            msg = f"🌅 <b>Tages-Briefing — {datetime.now().strftime('%d.%m.%Y')}</b>\n\n{brief}\n\n<i>🤖 Generiert via Ollama (lokal)</i>"
            async with aiohttp.ClientSession() as s:
                await s.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
                )
        out = _DATA / f"daily_brief_{int(time.time())}.txt"
        out.write_text(brief)
        return {"ok": True, "brief": brief[:500], "saved": str(out)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Hilfs-Funktion ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_latest_report():
    p = _BASE / "data" / "autonomous_loop" / "latest.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


# ── CLI ──────────────────────────────────────────────────────────────────────

async def run_all() -> dict[str, Any]:
    results = {}
    results["product_descriptions"] = await task_ollama_product_descriptions()
    results["social_posts"]         = await task_ollama_social_posts()
    results["email_subjects"]       = await task_ollama_email_subjects()
    results["seo_meta"]             = await task_ollama_seo_meta()
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [OLLAMA] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["product", "social", "email", "seo", "brief", "all"], default="all")
    args = parser.parse_args()

    task_map = {
        "product": task_ollama_product_descriptions,
        "social":  task_ollama_social_posts,
        "email":   task_ollama_email_subjects,
        "seo":     task_ollama_seo_meta,
        "brief":   task_ollama_daily_brief,
        "all":     run_all,
    }
    result = asyncio.run(task_map[args.task]())
    print(json.dumps(result, ensure_ascii=False, indent=2))
