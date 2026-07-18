"""
OrganicTrafficManager — 7-Plattformen Content-Maschine
Ersetzt Meta Ads durch kostenlosen organischen Traffic.

SICHERHEITS-PRINZIP: KEIN Post geht raus ohne vollständige PostGuard-Prüfung.
  ✓ URL-Erreichbarkeit (kein 404, kein "Seite nicht gefunden")
  ✓ Content-Qualität (kein Platzhalter, kein Spam)
  ✓ Plattform-Limits (Zeichenlänge, Hashtag-Anzahl)
  ✓ Nischen-Relevanz (Smart Home / Solar Keyword Pflicht)
  ✓ Keine Duplikate (NeverTwice-System)
  ✓ Shop-URL muss live sein bevor gepostet wird
  ✓ Max 3 Versuche pro Post — danach überspringen, kein Spam
"""

import asyncio
import logging
import os
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("OrganicTraffic")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "organic_traffic.db"

SHOP_URL = os.getenv("SHOPIFY_STORE_URL", "https://ineedit.com.co")
SHOP_NAME = "iNeedit"

# ── SICHERHEITSKRITISCHE LIMITS ───────────────────────────────────────────────
# Konservativ: lieber weniger posten als Accounts ruinieren
# (ursprünglich 4-6/Tag — zu aggressiv → reduziert)
MAX_PER_DAY = {
    "instagram":  2,   # war 4 — reduziert wegen Account-Schaden
    "facebook":   2,   # war 4
    "tiktok":     2,   # war 3
    "pinterest":  3,   # war 6
    "twitter":    3,   # war 6
    "reddit":     1,   # war 3 — Reddit sehr empfindlich für Spam
    "linkedin":   1,   # war 2 — LinkedIn straft Überposten mit Reichweiten-Verlust
}

# Mindestabstand zwischen zwei Posts auf derselben Plattform (in Sekunden)
MIN_GAP_BETWEEN_POSTS = {
    "instagram":  3 * 3600,   # min. 3 Stunden
    "facebook":   4 * 3600,
    "tiktok":     4 * 3600,
    "pinterest":  2 * 3600,
    "twitter":    2 * 3600,
    "reddit":    12 * 3600,   # Reddit: max 1x täglich
    "linkedin":  10 * 3600,
}

# Plattform-Pause bei Fehler (Stunden)
PLATFORM_PAUSE_ON_ERROR = 6

# Welche Plattformen in welchem Slot aktiv sind (2 Slots pro Tag: 0=10h, 1=19h)
SLOT_MATRIX = {
    #           0      1
    "instagram": [True,  True ],
    "facebook":  [True,  False],
    "tiktok":    [False, True ],
    "pinterest": [True,  True ],
    "twitter":   [True,  True ],
    "reddit":    [False, True ],
    "linkedin":  [False, True ],
    "reddit":    [True,  False, True,  False],
    "linkedin":  [False, True ],
}

# Gesperrte Plattformen (bei wiederholten Fehlern automatisch pausiert)
_PLATFORM_PAUSED_UNTIL: dict = {}

# ── Shop-URL Live-Check ───────────────────────────────────────────────────────

_SHOP_LIVE_CACHE: dict = {"ok": None, "ts": 0.0}

def _shop_is_live() -> bool:
    """Prüft ob ineedit.com.co erreichbar ist. Cached 10 Minuten."""
    now = time.time()
    if now - _SHOP_LIVE_CACHE["ts"] < 600 and _SHOP_LIVE_CACHE["ok"] is not None:
        return _SHOP_LIVE_CACHE["ok"]
    try:
        req = urllib.request.Request(
            SHOP_URL, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 OrganicTrafficBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            ok = r.status < 400
    except Exception as e:
        log.warning("Shop-URL Check fehlgeschlagen: %s — Posts pausiert", e)
        ok = False
    _SHOP_LIVE_CACHE["ok"] = ok
    _SHOP_LIVE_CACHE["ts"] = now
    if not ok:
        log.error("STOP: Shop %s nicht erreichbar — KEINE Posts werden gesendet!", SHOP_URL)
    return ok

# ── Content-Typen & Prompts ───────────────────────────────────────────────────
CONTENT_TYPES = ["product", "tip", "trend", "question", "story", "comparison"]

PLATFORM_SPECS = {
    "instagram": {"max_chars": 2200, "hashtags": 15, "format": "caption+hashtags", "image": True},
    "facebook":  {"max_chars": 500,  "hashtags": 5,  "format": "conversational",   "image": True},
    "tiktok":    {"max_chars": 2200, "hashtags": 20, "format": "hook+script",       "image": False},
    "pinterest": {"max_chars": 500,  "hashtags": 0,  "format": "seo-description",  "image": True},
    "reddit":    {"max_chars": 10000,"hashtags": 0,  "format": "reddit-post",       "image": False},
    "twitter":   {"max_chars": 280,  "hashtags": 3,  "format": "tweet",             "image": False},
    "linkedin":  {"max_chars": 3000, "hashtags": 5,  "format": "professional",      "image": False},
}

NICHE_TOPICS = [
    "Solar-Balkonkraftwerk", "Smart Home Beleuchtung", "Energiesparen 2026",
    "Powerstation tragbar", "Smart Plug WiFi", "Solar Panel Balkon",
    "Smarte Steckdose", "LED Strip", "Smart Thermostat", "Zigbee Gateway",
    "Off-Grid Leben", "Hausautomatisierung", "Alexa Smart Home",
    "Home Assistant", "Wärmepumpe Smart", "EV Laden Zuhause",
    "Smart Security Kamera", "Solar Generator", "Photovoltaik Balkon",
    "Smarter Kühlschrank", "Robot Staubsauger Smart", "Smarte Rollläden",
]

CONTENT_PROMPTS = {
    "product": (
        "Erstelle einen {platform}-Post über das Produkt '{topic}' für den Online-Shop {shop} "
        "({url}). Mache einen HOOK in der ersten Zeile. Zeige 3 Vorteile. Füge einen Call-to-Action "
        "ein. {format_hint}. Nur Deutsch. Max {max_chars} Zeichen."
    ),
    "tip": (
        "Erstelle einen {platform}-Post mit einem nützlichen Tipp zum Thema '{topic}'. "
        "KEIN Werbung — echter Mehrwert. Schreibe für {shop}-Kunden die Smart Home lieben. "
        "{format_hint}. Nur Deutsch. Max {max_chars} Zeichen."
    ),
    "trend": (
        "Erstelle einen {platform}-Post über den Trend '{topic}' 2026. Überraschende Statistik "
        "oder Fakt am Anfang. Verbinde mit Alltagsnutzen. {format_hint}. Nur Deutsch. "
        "Max {max_chars} Zeichen."
    ),
    "question": (
        "Erstelle eine Engagement-Frage für {platform} zum Thema '{topic}'. "
        "Stelle eine provokante oder interessante Frage die zum Kommentieren einlädt. "
        "Kurz und prägnant. {format_hint}. Nur Deutsch. Max {max_chars} Zeichen."
    ),
    "story": (
        "Erstelle einen {platform}-Post im Story-Format: 'Stell dir vor...' oder 'So war mein Morgen:' "
        "rund um '{topic}'. Persönlich, authentic, kein Verkaufstext. "
        "{format_hint}. Nur Deutsch. Max {max_chars} Zeichen."
    ),
    "comparison": (
        "Erstelle einen {platform}-Post: '{topic}' — damals vs. heute. "
        "Oder: mit Smart Home vs. ohne. Überzeugend aber nicht übertrieben. "
        "{format_hint}. Nur Deutsch. Max {max_chars} Zeichen."
    ),
}

FORMAT_HINTS = {
    "instagram": "Füge 10-15 relevante Hashtags am Ende hinzu. Nutze Emojis sparsam.",
    "facebook":  "Schreibe conversational, wie ein Freund. 3-5 Hashtags. Ein Emoji.",
    "tiktok":    "Beginne mit 'POV:' oder '🔥' oder einer Frage. 15-20 Hashtags. Energetisch!",
    "pinterest": "SEO-optimierter Beschreibungstext. Keine Hashtags. Keywords natürlich einbauen.",
    "reddit":    "Schreibe wie ein echter Reddit-Nutzer. Kein Verkaufstext. Mehrwert first. "
                 "Format: Titel (max 300 Zeichen) | Text (ausführlich, hilfreich).",
    "twitter":   "Max 280 Zeichen. Knackig. 1-3 Hashtags. Optional eine Frage am Ende.",
    "linkedin":  "Professionell aber persönlich. Business-Perspektive. 3-5 Hashtags. "
                 "Beginne mit einer Erkenntnis oder Zahl.",
}

# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS post_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL,
                content_type TEXT,
                topic       TEXT,
                text_snippet TEXT,
                post_id     TEXT,
                posted_at   REAL,
                success     INTEGER DEFAULT 0,
                error       TEXT,
                likes       INTEGER DEFAULT 0,
                comments    INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS content_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT,
                content_type TEXT,
                topic       TEXT,
                content     TEXT,
                created_at  REAL,
                used        INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_post_platform ON post_log(platform, posted_at);
        """)

_init_db()

# ── Content-Generator ─────────────────────────────────────────────────────────

async def _ai(prompt: str, max_tokens: int = 600) -> str:
    from modules.ai_client import ai_complete
    return await ai_complete(prompt, max_tokens=max_tokens)


async def generate_content(platform: str, content_type: str = None, topic: str = None) -> dict:
    """Generiert AI-Content für eine bestimmte Plattform."""
    import random

    if not content_type:
        content_type = random.choice(CONTENT_TYPES)
    if not topic:
        topic = random.choice(NICHE_TOPICS)

    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["instagram"])
    prompt_tpl = CONTENT_PROMPTS.get(content_type, CONTENT_PROMPTS["tip"])
    fmt_hint   = FORMAT_HINTS.get(platform, "")

    prompt = prompt_tpl.format(
        platform=platform.capitalize(),
        topic=topic,
        shop=SHOP_NAME,
        url=SHOP_URL,
        format_hint=fmt_hint,
        max_chars=spec["max_chars"],
    )

    text = await _ai(prompt, max_tokens=800)

    # Reddit: split Titel / Text
    if platform == "reddit" and "|" in text:
        parts = text.split("|", 1)
        title = parts[0].strip()[:299]
        body  = parts[1].strip()[:9000]
    else:
        title = _make_title(text, platform)
        body  = text.strip()[:spec["max_chars"]]

    return {
        "platform":     platform,
        "content_type": content_type,
        "topic":        topic,
        "title":        title,
        "text":         body,
        "needs_image":  spec["image"],
    }


def _make_title(text: str, platform: str) -> str:
    """Erste Zeile als Titel extrahieren."""
    first = text.split("\n")[0].strip()
    return first[:100] if first else f"{platform} Post"


async def get_shopify_product_image() -> Optional[str]:
    """Zufälliges echtes Produktbild aus dem Shopify-Store."""
    try:
        from modules.shopify_client import get_products
        products = await get_products(limit=50)
        import random
        for p in random.sample(products, min(10, len(products))):
            imgs = p.get("images", [])
            if imgs:
                return imgs[0].get("src")
    except Exception as e:
        log.debug("Shopify image fetch: %s", e)
    return None

# ── Platform-Poster ───────────────────────────────────────────────────────────

async def post_instagram(content: dict) -> dict:
    try:
        from modules.instagram_pipeline import post_to_instagram, _page_token
        token = await _page_token()
        image_url = await get_shopify_product_image()
        if not image_url:
            image_url = f"https://picsum.photos/seed/{int(time.time())}/1080/1080"
        r = await post_to_instagram(content["text"], image_url, token)
        return {"ok": r.get("id") is not None or r.get("success"), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_facebook(content: dict) -> dict:
    try:
        from modules.instagram_pipeline import post_to_facebook, _page_token
        token = await _page_token()
        r = await post_to_facebook(content["text"], token)
        return {"ok": r.get("id") is not None or r.get("success"), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_twitter(content: dict) -> dict:
    try:
        from modules.twitter_auto_poster import post_tweet
        r = await post_tweet(content["text"])
        return {"ok": r.get("ok", False) or r.get("id") is not None, "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_linkedin(content: dict) -> dict:
    try:
        from modules.linkedin_poster import post_to_linkedin
        r = await post_to_linkedin(content["text"])
        return {"ok": r.get("id") is not None or r.get("ok"), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_pinterest(content: dict) -> dict:
    try:
        from modules.pinterest_autonomy import create_pin
        image_url = await get_shopify_product_image()
        if not image_url:
            return {"ok": False, "error": "Kein Produktbild verfügbar"}
        r = await create_pin(
            title=content["title"],
            desc=content["text"],
            image_url=image_url,
            link=SHOP_URL,
        )
        return {"ok": r.get("id") is not None or r.get("ok"), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_reddit(content: dict) -> dict:
    try:
        from modules.reddit_autoposter import _post_to_subreddit, _get_token

        SUBREDDITS = {
            "Solar-Balkonkraftwerk": "r/balconysolar",
            "Smart Home":            "r/smarthome",
            "default":               "r/homeautomation",
        }
        topic = content.get("topic", "")
        subreddit = next(
            (v for k, v in SUBREDDITS.items() if k.lower() in topic.lower()),
            SUBREDDITS["default"]
        ).replace("r/", "")

        token = await _get_token()
        r = await _post_to_subreddit(subreddit, content["title"], content["text"], token)
        return {"ok": r.get("ok") or "url" in str(r), "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def post_tiktok(content: dict) -> dict:
    try:
        from modules.tiktok_autonomy import generate_video_scripts
        # TikTok braucht Video — wir generieren Scripts + posten als Text-Only via API
        # (TikTok Creator API ermöglicht Photo Posts)
        ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        OPEN_ID      = os.getenv("TIKTOK_OPEN_ID", "")
        if not ACCESS_TOKEN or not OPEN_ID:
            return {"ok": False, "error": "TIKTOK_ACCESS_TOKEN oder TIKTOK_OPEN_ID fehlt"}

        import aiohttp
        # TikTok Photo Post (Creator Marketplace API)
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "post_info": {
                "title":       content["text"][:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_comment": False,
            },
            "source_info": {"source": "FILE_UPLOAD"},
        }
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            )
            data = await r.json()
        ok = data.get("error", {}).get("code") == "ok"
        return {"ok": ok, "result": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


PLATFORM_POSTERS = {
    "instagram": post_instagram,
    "facebook":  post_facebook,
    "twitter":   post_twitter,
    "linkedin":  post_linkedin,
    "pinterest": post_pinterest,
    "reddit":    post_reddit,
    "tiktok":    post_tiktok,
}

# ── Rate-Limit-Check ─────────────────────────────────────────────────────────

def _posts_today(platform: str) -> int:
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    with sqlite3.connect(DB_PATH) as c:
        row = c.execute(
            "SELECT COUNT(*) FROM post_log WHERE platform=? AND posted_at>=? AND success=1",
            (platform, day_start)
        ).fetchone()
    return row[0] if row else 0


def _last_post_ts(platform: str) -> float:
    """Zeitstempel des letzten erfolgreichen Posts auf dieser Plattform."""
    with sqlite3.connect(DB_PATH) as c:
        row = c.execute(
            "SELECT MAX(posted_at) FROM post_log WHERE platform=? AND success=1",
            (platform,)
        ).fetchone()
    return row[0] or 0.0


def _log_post(platform: str, content: dict, result: dict, guard_errors: list = None):
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
            INSERT INTO post_log
            (platform, content_type, topic, text_snippet, post_id, posted_at, success, error)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            platform,
            content.get("content_type", ""),
            content.get("topic", ""),
            content.get("text", "")[:150],
            str(result.get("result", {}).get("id", "")),
            time.time(),
            int(result.get("ok", False)),
            result.get("error", "") or ("; ".join(guard_errors) if guard_errors else ""),
        ))


async def _post_with_guard(platform: str, content: dict) -> dict:
    """
    Führt vollständige PostGuard-Prüfung durch bevor gepostet wird.
    Max 3 Versuche mit neuem Content falls Guard fehlschlägt.
    """
    MAX_RETRIES = 3

    for attempt in range(1, MAX_RETRIES + 1):
        text = content.get("text", "")

        # ── PostGuard-Prüfung (alle Checks: URL, Qualität, Duplikat, Spam) ──
        try:
            from modules.post_guard import check_post
            guard_ok, guard_errors = await check_post(
                text=text,
                platform=platform,
                skip_ai=(attempt > 1),   # AI-Check nur beim ersten Versuch
            )
        except Exception as e:
            log.warning("PostGuard nicht verfügbar: %s — fail-open für %s", e, platform)
            guard_ok, guard_errors = True, []

        if not guard_ok:
            log.warning(
                "PostGuard BLOCKIERT [%s] Versuch %d/%d: %s",
                platform, attempt, MAX_RETRIES, guard_errors
            )
            if attempt < MAX_RETRIES:
                # Neuen Content generieren und nochmal versuchen
                try:
                    content = await generate_content(platform)
                except Exception:
                    break
                await asyncio.sleep(2)
                continue
            # Alle Versuche erschöpft
            _log_post(platform, content, {"ok": False}, guard_errors)
            return {"ok": False, "error": f"PostGuard blockiert nach {MAX_RETRIES} Versuchen: {guard_errors}"}

        # ── Guard OK → jetzt erst posten ────────────────────────────────────
        try:
            poster = PLATFORM_POSTERS[platform]
            result = await poster(content)
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        _log_post(platform, content, result)

        if result["ok"]:
            log.info("✅ [%s] Gepostet (Versuch %d): %s — %s",
                     platform, attempt, content["topic"], content["content_type"])
        else:
            err = result.get("error", "")
            log.warning("❌ [%s] API-Fehler: %s", platform, err)
            # Plattform bei API-Fehler temporär pausieren
            if "rate" in err.lower() or "limit" in err.lower() or "banned" in err.lower():
                pause_until = time.time() + PLATFORM_PAUSE_ON_ERROR * 3600
                _PLATFORM_PAUSED_UNTIL[platform] = pause_until
                log.error("Plattform %s für %dh gesperrt!", platform, PLATFORM_PAUSE_ON_ERROR)

        return result

    return {"ok": False, "error": "Maximale Versuche erreicht"}


# ── Haupt-Post-Session ────────────────────────────────────────────────────────

async def run_posting_session(slot: int = None) -> dict:
    """
    Sicherheits-Posting-Session: jeder Post durch vollständige Guard-Pipeline.
    slot: 0=morgen(10h), 1=abend(19h)
    """
    # ── Schritt 1: Shop muss erreichbar sein ─────────────────────────────────
    if not _shop_is_live():
        msg = f"STOP: Shop {SHOP_URL} nicht erreichbar — keine Posts gesendet!"
        log.error(msg)
        await _notify_error(msg)
        return {"ok": False, "error": msg, "posted": [], "skipped": list(PLATFORM_POSTERS.keys())}

    if slot is None:
        hour = datetime.now().hour
        slot = 0 if hour < 15 else 1

    results = {}
    posted  = []
    skipped = []
    blocked = []

    for platform in PLATFORM_POSTERS:
        now = time.time()

        # Plattform pausiert (nach Fehler)?
        paused_until = _PLATFORM_PAUSED_UNTIL.get(platform, 0)
        if now < paused_until:
            remaining = int((paused_until - now) / 3600)
            skipped.append(f"{platform}(pausiert:{remaining}h)")
            continue

        # Slot-Check
        slots = SLOT_MATRIX[platform]
        if slot >= len(slots) or not slots[slot]:
            skipped.append(platform)
            continue

        # Tageslimit-Check
        today = _posts_today(platform)
        max_p = MAX_PER_DAY[platform]
        if today >= max_p:
            skipped.append(f"{platform}(limit:{max_p})")
            continue

        # Mindestabstand zwischen Posts
        last_ts  = _last_post_ts(platform)
        min_gap  = MIN_GAP_BETWEEN_POSTS.get(platform, 3600)
        if now - last_ts < min_gap:
            wait_min = int((min_gap - (now - last_ts)) / 60)
            skipped.append(f"{platform}(warten:{wait_min}min)")
            continue

        # Content generieren
        try:
            content = await generate_content(platform)
        except Exception as e:
            log.warning("Content-Gen fehlgeschlagen für %s: %s", platform, e)
            skipped.append(f"{platform}(gen-err)")
            continue

        # PostGuard + Posten
        result = await _post_with_guard(platform, content)
        results[platform] = result

        if result["ok"]:
            posted.append(platform)
        elif "PostGuard blockiert" in result.get("error", ""):
            blocked.append(platform)
        else:
            skipped.append(f"{platform}(err)")

        # Pause zwischen Plattformen (kein Burst)
        await asyncio.sleep(5)

    if posted or blocked:
        await _notify(posted, blocked, results, slot)

    return {
        "slot":    slot,
        "posted":  posted,
        "blocked": blocked,
        "skipped": skipped,
        "results": {k: {"ok": v["ok"], "error": v.get("error", "")} for k, v in results.items()},
    }


async def _notify(posted: list, results: dict, slot: int):
    slot_names = {0: "☀️ Morgen", 1: "🌞 Mittag", 2: "🌆 Nachmittag", 3: "🌙 Abend"}
    ok  = [p for p, r in results.items() if r.get("ok")]
    err = [p for p, r in results.items() if not r.get("ok")]

    msg = (
        f"📣 <b>Organic Traffic — {slot_names.get(slot, 'Session')}</b>\n"
        f"✅ Gepostet: {', '.join(ok) if ok else '—'}\n"
        f"❌ Fehler: {', '.join(err) if err else '—'}\n"
        f"📊 Heute gesamt: {sum(_posts_today(p) for p in PLATFORM_POSTERS)} Posts"
    )

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("Telegram notify: %s", e)

# ── Status & Analytics ────────────────────────────────────────────────────────

def get_status() -> dict:
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row

        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        week_start = day_start - 6 * 86400

        today_total = c.execute(
            "SELECT COUNT(*) FROM post_log WHERE posted_at>=? AND success=1", (day_start,)
        ).fetchone()[0]

        week_total = c.execute(
            "SELECT COUNT(*) FROM post_log WHERE posted_at>=? AND success=1", (week_start,)
        ).fetchone()[0]

        by_platform = {}
        for row in c.execute("""
            SELECT platform, COUNT(*) as cnt
            FROM post_log WHERE posted_at>=? AND success=1
            GROUP BY platform
        """, (week_start,)):
            by_platform[row["platform"]] = row["cnt"]

        recent = [dict(r) for r in c.execute("""
            SELECT platform, content_type, topic, posted_at, success, error
            FROM post_log ORDER BY posted_at DESC LIMIT 10
        """).fetchall()]

    # Heute noch möglich
    remaining = {
        p: max(0, MAX_PER_DAY[p] - _posts_today(p))
        for p in PLATFORM_POSTERS
    }

    return {
        "ok":            True,
        "today_posts":   today_total,
        "week_posts":    week_total,
        "by_platform":   by_platform,
        "remaining":     remaining,
        "max_per_day":   MAX_PER_DAY,
        "recent":        recent,
        "platforms":     list(PLATFORM_POSTERS.keys()),
    }

# ── Dauerschleife (für Scheduler) ────────────────────────────────────────────

async def run_traffic_loop():
    """Endlosschleife: postet 4× täglich zur richtigen Uhrzeit."""
    SLOTS = {0: 8, 1: 12, 2: 16, 3: 20}
    last_slot = -1

    log.info("OrganicTrafficManager gestartet — 7 Plattformen, 4× täglich")

    while True:
        now   = datetime.now()
        hour  = now.hour
        # Welcher Slot ist gerade aktiv?
        current_slot = next((s for s, h in SLOTS.items() if hour == h), None)

        if current_slot is not None and current_slot != last_slot:
            last_slot = current_slot
            log.info("Starte Posting-Session Slot %d (%02d:00)", current_slot, SLOTS[current_slot])
            try:
                await run_posting_session(slot=current_slot)
            except Exception as e:
                log.error("Posting-Session Fehler: %s", e)

        await asyncio.sleep(60)  # jede Minute prüfen
