#!/usr/bin/env python3
"""
ShopText.ai — Autonomer Traffic-Autopilot
Postet alle 3h auf Telegram + Reddit mit rotierenden Nachrichten.
Kein Spam: jede Nachricht anders, Cooldown pro Kanal.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("shoptext_promo")

DB_PATH = Path(__file__).parent.parent / "data" / "shoptext_promo.db"

LIVE_URL = "https://supermegabot-production.up.railway.app/shoptext"

# ── Nachrichtenvorlagen (rotierend, klingen menschlich) ─────────────────────

TELEGRAM_TEMPLATES = [
    """🛒 Tipp für Shopify-Händler:

Ich hab jetzt alle meine Produkttexte mit KI schreiben lassen — spart mir jeden Monat 8+ Stunden.

Tool: {url}
→ Produktname eingeben, 15 Sek warten, fertige SEO-Beschreibung + Meta-Titel + Tags
→ 3 Texte kostenlos testen, keine Kreditkarte

Falls jemand auch kämpft mit Produktbeschreibungen 👇""",

    """💡 Kurze Frage an euch:

Wer schreibt noch manuell seine Shopify-Produkttexte?

Ich mach das seit 2 Wochen mit KI — dauert 15 Sek pro Produkt statt 30 Min.
SEO-optimiert, Meta-Description inkl., direkt kopieren und einfügen.

Test (kostenlos): {url}""",

    """📦 Für alle die gerade ihren Shop aufbauen:

Produkttexte sind der größte Zeitfresser beim Shopify-Setup.
Mit KI geht das jetzt in 15 Sekunden — auf Deutsch, SEO-fertig.

Hab das Tool selbst gebaut, nutze es täglich: {url}
3 Texte gratis ohne Anmeldung""",

    """Kleiner Hack wenn ihr viele Shopify-Produkte habt 👇

Statt 20 Min pro Produktbeschreibung zu tippen:
1. Produktname eingeben
2. Keywords angeben
3. KI schreibt fertige SEO-Beschreibung auf Deutsch

{url} — erste 3 kostenlos""",

    """🇩🇪 Für deutsche Shopify-Händler:

Die meisten AI-Tools schreiben Produkttexte nur auf Englisch.
Hab einen gebaut der auf Deutsch optimiert — inkl. Meta-Titel & Tags.

Gratis testen: {url}""",
]

REDDIT_POSTS = [
    {
        "title": "Produktbeschreibungen für Shopify mit KI — spart mir 8h/Monat",
        "text": """Hey r/shopify,

wollte kurz teilen was mir viel Zeit spart:

**Problem**: Ich hab 200+ Produkte im Shop und brauche für jedes eine deutsche SEO-Beschreibung, Meta-Title und Tags.

**Was ich jetzt mache**: KI-Tool eingeben → 15 Sekunden → fertige Beschreibung + Meta + Tags auf Deutsch, direkt kopierbar.

Hab das Tool selbst gebaut: {url}

3 Texte sind kostenlos zum Testen, keine Kreditkarte nötig.

Funktioniert für alle Nischen (hab's für Smart Home, Elektronik und Mode getestet).

Irgendwer hier auch so ein Workflow?""",
    },
    {
        "title": "Wie erstellt ihr eure Shopify Produkttexte? (DE-Markt)",
        "text": """Moin,

ich hab mich lange gefragt wie andere Shopify-Händler ihre deutschen Produktbeschreibungen erstellen.

Freelancer ist teuer (€30-80 pro Text), selbst schreiben dauert ewig.

Hab jetzt einen KI-Workflow: {url}
→ Produktname + Keywords eingeben
→ 15 Sek warten
→ SEO-Text auf Deutsch, Meta-Title, Tags — alles fertig

3 Texte gratis, dann €49/Mo für unlimited.

Würde mich interessieren wie ihr das macht!""",
    },
    {
        "title": "Gratis Tool: SEO-Produkttexte für Shopify auf Deutsch (KI)",
        "text": """Hi,

ich hab ein Tool gebaut das mir für meine Shopify-Produkte automatisch SEO-Texte auf Deutsch schreibt.

**Was es macht:**
- Produktbeschreibung (200+ Wörter, SEO-optimiert)
- Meta-Title + Meta-Description
- Tags für Shopify
- Bullet Points

**Kostenlos testen:** {url} (3 Texte ohne Anmeldung)

Powered by Claude AI. Feedback willkommen!""",
    },
]

# Subreddits die Shopify-relevanten Traffic bringen
SUBREDDITS = [
    "shopify",
    "ecommerce",
    "Unternehmertum",
    "Existenzgruendung",
    "onlinehandel",
]

# Telegram-Gruppen Chats (echte IDs aus bestehender Config)
TELEGRAM_CHATS_ENV = "SHOPTEXT_TG_CHATS"  # komma-getrennte Chat-IDs in .env


# ── DB ───────────────────────────────────────────────────────────────────────

def _init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            channel    TEXT,
            target     TEXT,
            template   INTEGER,
            posted_at  INTEGER,
            success    INTEGER DEFAULT 0,
            response   TEXT
        )
    """)
    conn.commit()
    conn.close()


def _last_post(channel: str, target: str) -> int:
    """Returns timestamp of last post to this target, or 0."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT posted_at FROM posts WHERE channel=? AND target=? AND success=1 ORDER BY posted_at DESC LIMIT 1",
        (channel, target)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def _used_templates(channel: str, target: str) -> set:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT template FROM posts WHERE channel=? AND target=? ORDER BY posted_at DESC LIMIT 10",
        (channel, target)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def _record(channel: str, target: str, tmpl_idx: int, success: bool, response: str = ""):
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO posts (channel, target, template, posted_at, success, response) VALUES (?,?,?,?,?,?)",
        (channel, target, tmpl_idx, int(time.time()), 1 if success else 0, response[:500])
    )
    conn.commit()
    conn.close()


def _pick_template(templates: list, channel: str, target: str) -> tuple[int, str]:
    """Pick a not-recently-used template."""
    used = _used_templates(channel, target)
    available = [i for i in range(len(templates)) if i not in used]
    if not available:
        available = list(range(len(templates)))
    idx = random.choice(available)
    return idx, templates[idx]


# ── Telegram ─────────────────────────────────────────────────────────────────

async def _post_telegram(chat_id: str, text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN nicht gesetzt")
        return False

    import aiohttp
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return data.get("ok", False)
    except Exception as e:
        log.warning("TG post error %s: %s", chat_id, e)
        return False


async def run_telegram_promo() -> dict:
    """Post ShopText.ai promo to configured Telegram chats."""
    # Primary: owner chat + configured group chats
    owner_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    extra_chats_raw = os.getenv(TELEGRAM_CHATS_ENV, "")
    extra_chats = [c.strip() for c in extra_chats_raw.split(",") if c.strip()]

    chats_to_post = []
    if owner_chat:
        chats_to_post.append(owner_chat)
    chats_to_post.extend(extra_chats)

    if not chats_to_post:
        return {"ok": False, "reason": "Keine Telegram Chats konfiguriert"}

    cooldown = 10800  # 3h zwischen Posts zum selben Chat
    posted = []
    skipped = []

    for chat_id in chats_to_post:
        last = _last_post("telegram", chat_id)
        if time.time() - last < cooldown:
            skipped.append(chat_id)
            continue

        idx, tmpl = _pick_template(TELEGRAM_TEMPLATES, "telegram", chat_id)
        text = tmpl.format(url=LIVE_URL)

        ok = await _post_telegram(chat_id, text)
        _record("telegram", chat_id, idx, ok)
        if ok:
            posted.append(chat_id)

    return {"ok": True, "posted": len(posted), "skipped": len(skipped), "chats": posted}


# ── Reddit ───────────────────────────────────────────────────────────────────

async def _reddit_post_via_cookie(subreddit: str, title: str, text: str) -> bool:
    """Try posting via the existing reddit_cookie_poster module."""
    try:
        from modules.reddit_cookie_poster import submit_post
        result = await submit_post(subreddit=subreddit, title=title, text=text)
        return bool(result and result.get("ok"))
    except Exception as e:
        log.warning("Reddit cookie post error: %s", e)
        return False


async def run_reddit_promo() -> dict:
    cooldown = 43200  # 12h pro Subreddit
    posted = []
    skipped = []

    random.shuffle(SUBREDDITS)
    # Post to max 2 subreddits per cycle to avoid spam
    targets = SUBREDDITS[:2]

    for sub in targets:
        last = _last_post("reddit", sub)
        if time.time() - last < cooldown:
            skipped.append(sub)
            continue

        idx = random.randrange(len(REDDIT_POSTS))
        post = REDDIT_POSTS[idx]
        title = post["title"]
        text = post["text"].format(url=LIVE_URL)

        ok = await _reddit_post_via_cookie(sub, title, text)
        _record("reddit", sub, idx, ok)
        if ok:
            posted.append(f"r/{sub}")

    return {"ok": True, "posted": len(posted), "skipped": len(skipped), "subs": posted}


# ── Status Report via Telegram ───────────────────────────────────────────────

async def _notify_owner(msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg},
                timeout=aiohttp.ClientTimeout(total=8)
            )
    except Exception:
        pass


# ── Haupt-Entry ──────────────────────────────────────────────────────────────

async def run_promo_cycle() -> dict:
    """Vollautonomer ShopText.ai Promo-Zyklus: TG + Reddit."""
    results: dict = {}

    # 1. Telegram
    try:
        tg = await run_telegram_promo()
        results["telegram"] = tg
    except Exception as e:
        results["telegram"] = {"ok": False, "error": str(e)}

    # 2. Reddit
    try:
        rd = await run_reddit_promo()
        results["reddit"] = rd
    except Exception as e:
        results["reddit"] = {"ok": False, "error": str(e)}

    # 3. ShopText stats abrufen
    try:
        from modules.shoptext_ai import get_stats
        stats = get_stats()
        results["shoptext_stats"] = stats
    except Exception:
        stats = {}
        results["shoptext_stats"] = {}

    # 4. Status-Report an Rudolf
    tg_r = results.get("telegram", {})
    rd_r = results.get("reddit", {})
    total_gen = stats.get("total_generations", 0)
    paid = stats.get("paid_users", 0)

    summary = (
        f"📊 ShopText.ai Promo-Report\n"
        f"TG: {tg_r.get('posted',0)} gepostet / {tg_r.get('skipped',0)} übersprungen\n"
        f"Reddit: {rd_r.get('posted',0)} gepostet → {', '.join(rd_r.get('subs',[]) or ['–'])}\n"
        f"Generierungen gesamt: {total_gen} | Paid: {paid}\n"
        f"URL: {LIVE_URL}"
    )
    await _notify_owner(summary)

    results["summary"] = summary
    return results
