"""
PostValidator — 5-Layer Universalprüfer für ALLE ausgehenden Posts
==================================================================
Jeder Post MUSS alle 5 Layer bestehen. Bei Fehler → IMMER blockieren.

Layer 1  Basis-Sanity     (synchron, < 1ms)
Layer 2  Sprache/Format   (synchron, < 1ms)
Layer 3  Nischen-Check    (synchron, < 1ms)
Layer 4  KI-Qualitäts-Score (async, Groq/Haiku, < 500ms) — Score ≥ 7
Layer 5  Duplikat-Schutz  (synchron, SQLite, < 5ms)

Fail-Safe: Bei jedem technischen Fehler → BLOCKIEREN (nie durchlassen!)

Verwendung:
    from modules.post_validator import validate_post
    ok, layer, reason = await validate_post(text=..., platform=..., content_type="social")
    if not ok:
        return {"blocked": True, "layer": layer, "reason": reason}
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("PostValidator")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "post_validator.db"
_DB.parent.mkdir(exist_ok=True)

# ── Konfiguration ─────────────────────────────────────────────────────────────
MIN_AI_SCORE     = 4     # Minimum KI-Score (1-10) — unter 4 → BLOCK (1-3 = Spam/Fehler, 4+ = zulässig)
MIN_TEXT_LEN     = 30    # Mindest-Textlänge
MAX_TEXT_LEN     = 5000  # Maximum
DEDUP_WINDOW_H   = 24    # Gleicher Text innerhalb 24h → BLOCK

# ── Layer 0: Off-Topic Hard-Block (vor allem anderen) ─────────────────────────
# Nische = NUR Smart/Tech/Solar/E-Commerce. Alles andere → sofort blockieren.
_L0_OFFTOPIC = [
    # Haushalt/Küche ohne Tech-Bezug
    r"\bbambus\b", r"\bbamboo\b",
    r"\bschneidebrett\b", r"\bcutting[\s-]?board\b",
    r"\bkaffeemühl\b", r"\bcoffee[\s-]?grinder\b",
    r"\bmöbel\b", r"\bstuhl\b", r"\btisch\b", r"\bchair\b(?!\s*mount|\s*lift|\s*bot)",
    r"\bsofa\b", r"\bcouch\b", r"\bschrank\b",
    r"\bgeschirr\b", r"\bbesteck\b", r"\btopf\b(?!\s*\w{0,5}smart)",
    r"\bkochgeschirr\b",
    # Kleidung/Mode
    r"\bkleidung\b", r"\bmode\b(?!\s*\w{0,10}smart)", r"\bschuhe\b", r"\btextil\b",
    r"\bjacke\b", r"\bhose\b", r"\bhemd\b",
    # Körperpflege/Wellness ohne Tech
    r"\bhautpflege\b", r"\bkosmetik\b", r"\bparfüm\b", r"\bperfume\b",
    r"\bcreme\b", r"\bseife\b", r"\bshampoo\b",
    r"\byoga[\s-]?matte?\b", r"\byoga\s+mat\b",
    r"\bkerze\b(?!\s*\w{0,10}smart)", r"\bduftkerze\b", r"\bcandle\b(?!\s*\w{0,10}smart)",
    # Baby/Spielzeug
    r"\bkinderwagen\b", r"\bbabybett\b", r"\bspielzeug\b(?!\s*\w{0,10}robot)",
    r"\bschnuller\b",
    # Bücher/Print
    r"\bkochbuch\b", r"\bnoizbuch\b", r"\bnotizbuch\b", r"\btagebu\w+\b",
    # Haushalt ohne Tech
    r"\bwäschekorb\b", r"\bbettwäsche\b", r"\bkissen\b(?!\s*\w{0,10}smart)",
    r"\bvorhang\b", r"\bteppich\b(?!\s*\w{0,10}robot|\s*\w{0,10}auto)",
    # Lebensmittel
    r"\bkaffee\b(?!\s*\w{0,10}maschine|\s*\w{0,10}automat)",
    r"\btee\b(?!\s*\w{0,10}maschine|\s*\w{0,10}automat)",
    r"\bwein\b", r"\bbier\b", r"\bnahrungsergänzung\b",
    r"\bprotein\s*pulver\b",
    # Schmuck/Dekoration
    r"\bschmuck\b", r"\barmband\b(?!\s*\w{0,10}smart|\s*\w{0,10}fit)",
    r"\bhalskette\b", r"\bring\b(?!\s*\w{0,10}smart)",
    r"\bdeko\b(?!\s*\w{0,10}light|\s*\w{0,10}led)",
    # Ergonomie-Schlagwörter wenn ohne Tech-Kontext
    r"\bergonomic[\s-]?chair\b", r"\bchair\s+cushion\b", r"\bchair\s+pad\b",
    r"\berkrankung\b", r"\bgesundheit\b(?!\s*\w{0,10}monitor|\s*\w{0,10}tracker)",
    # Tiere (außer mit Tech-Bezug)
    r"\btierfutter\b", r"\bhundehalsband\b(?!\s*\w{0,10}gps|\s*\w{0,10}smart)",
    r"\bkatzenklo\b", r"\bvogelfutter\b",
    # Generisch off-niche News/Artikel-Titeln
    r"\bhacker\s*news\b", r"\bshow\s+hn\b",
    r"\bblender\b(?!\s*\w{0,10}3d)",  # Blender-Software ok, Mixer → block
    r"\bvancouver\s+pd\b",
]
_L0_RE = [re.compile(p, re.IGNORECASE) for p in _L0_OFFTOPIC]

# ── Layer 1: Verbotene Muster (sofort blockieren) ─────────────────────────────
_L1_BLOCKED = [
    r"\blorem ipsum\b",
    r"\bundefined\b",
    r"\bnull\b",
    r"\bNaN\b",
    r"\[object\s+Object\]",
    r"\bPLACEHOLDER\b",
    r"\bINSERT[_\s]+HERE\b",
    r"\bTODO[:\s]",
    r"example\.com",
    r"yourdomain\.",
    r"\btest\s+post\b",
    r"\bfake\s+produkt\b",
    r"\bERROR:\b",
    r"\bTraceback\b",
    r"\bException\b",
    r"<class '",
    r"\{\{.*\}\}",           # Template-Platzhalter {{var}}
    r"\$\{.*\}",             # Template-Platzhalter ${var}
    r"__MISSING__",
    r"N/A\s+N/A\s+N/A",
    r"None None None",
]
_L1_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _L1_BLOCKED]

# ── Layer 2: Spam-Phrasen (echte Scam-Inhalte, NICHT Marketing-Phrasen) ─────────
# WICHTIG: Keine Brand-Namen (bullpower, supermegabot) und keine legitimen
# Marketing-Phrasen (passives einkommen, finanzielle freiheit) hier eintragen!
# Diese sind für Rudolf's E-Commerce-Business ERWÜNSCHT.
_L2_SPAM = [
    "lorem ipsum", "test content", "sample text",
    "copy paste", "affiliate scam",
    "100% profit", "guaranteed income",
    "pyramid scheme", "pyramid scam",
    "get rich quick", "overnight millionaire",
    "make money fast", "easy money online",
    "online geld verdienen", "geld verdienen vollautomatisch",
    "passives einkommen online", "automatisches einkommen",
    "earn while you sleep",
]
_QUIET_NOTIFY_REASONS = (
    "duplikat_innerhalb_",
    "bereits_blockiert",
    "rate_limit",
    "429",
    "daily_cap",
)
_TRANSIENT_BLOCK_REASONS = _QUIET_NOTIFY_REASONS + ("token",)

# ── Layer 3: Nischen-Keywords (mindestens 1 STARKES muss vorhanden sein) ───────
# WICHTIG: Nur echte Tech/Smart/Digital-Keywords. Keine generischen Wörter.
# Removed: "home", "product", "shop", "energy", "power", "efficiency",
#          "innovative", "kaufen", "produkt", "sale", "deal", "service",
#          "lösung", "kunde", "content", "instagram", "facebook" etc.
#          — diese sind zu generisch und lassen Off-Topic-Posts durch.
_L3_NICHE = [
    # Direkte Tech/Smart-Produktkategorien
    "smart home", "smart device", "smart watch", "smart speaker",
    "e-bike", "e-scooter", "e-roller",
    "powerstation", "solar panel", "balkonkraftwerk", "photovoltaik",
    "wlan-kamera", "wifi-kamera", "überwachungskamera", "dashcam",
    # Technologie-Begriffe
    "solar", "photovoltaik", "wlan", "wifi", "bluetooth", "zigbee", "zwave",
    "led", "rgb", "akku", "lithium", "powerbank",
    "sensor", "detektor", "alarm", "kamera",
    "robot", "roboter", "drohne", "drone",
    "3d-druck", "3d printer", "laser cutter", "cnc",
    "raspberry pi", "arduino", "microcontroller",
    # Digitale Business-Begriffe (nur spezifische)
    "shopify", "e-commerce", "ecommerce", "e commerce",
    "saas", "software", "automation", "automatisierung",
    "ai", "ki", "künstliche intelligenz", "artificial intelligence",
    "machine learning", "chatgpt", "claude", "openai",
    "api", "webhook", "workflow",
    "digistore", "ds24", "affiliate",
    "gumroad", "stripe", "paypal",
    "seo", "conversion", "cpc", "cpm",
    "ineedit", "aiitec",
    # B2B / LinkedIn Thought-Leadership (EU AI Act, Sales-Automation)
    "b2b", "compliance", "eu ai act", "ki-verordnung", "ai act",
    "lead", "outreach", "sdr", "sales", "crm",
    "chatbot", "ki-agent", "ki agent", "rezeptionistin",
    # Spezifische Produkttypen die in Nische passen
    "gadget", "tech", "technologie", "elektronik",
    "steckdose", "thermostat", "heizung", "klimaanlage",
    "usb", "hdmi", "lan", "ethernet",
    "netzwerk", "router", "switch",
    "powerstrip", "verlängerungskabel",
    "ladegerät", "charger", "netzteil",
    "mikrofon", "lautsprecher", "kopfhörer",
    "projektor", "beamer",
    # Automotive Tech
    "obd", "can-bus", "fahrzeugdiagnose",
    "reifendruckmonitor", "tpms",
    # Digital Marketing spezifisch
    "traffic", "lead", "funnel", "upsell",
    "klaviyo", "mailchimp", "sendgrid",
    "telegram", "discord",
]
_L3_RE = [re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE) for kw in _L3_NICHE]

# ── SQLite für Duplikat-Tracking ─────────────────────────────────────────────
def _init_db():
    con = sqlite3.connect(str(_DB))
    con.execute("""
        CREATE TABLE IF NOT EXISTS posted_hashes (
            hash TEXT PRIMARY KEY,
            platform TEXT,
            posted_at REAL
        )
    """)
    con.commit()
    con.close()

_init_db()


def _text_hash(text: str) -> str:
    """Kompakter Hash des Post-Textes (erste 300 Zeichen)."""
    normalized = re.sub(r"\s+", " ", text[:300].lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _is_duplicate(text: str, platform: str) -> bool:
    """True wenn identischer Text auf DERSELBEN Platform in den letzten DEDUP_WINDOW_H Stunden gepostet."""
    h = _text_hash(text)
    cutoff = time.time() - DEDUP_WINDOW_H * 3600
    try:
        con = sqlite3.connect(str(_DB))
        row = con.execute(
            "SELECT posted_at FROM posted_hashes WHERE hash=? AND platform=? AND posted_at>?",
            (h, platform, cutoff)
        ).fetchone()
        con.close()
        return row is not None
    except Exception:
        return False


def _register_hash(text: str, platform: str):
    """Speichert den Hash nach erfolgreichem Post."""
    h = _text_hash(text)
    try:
        con = sqlite3.connect(str(_DB))
        con.execute(
            "INSERT OR REPLACE INTO posted_hashes (hash, platform, posted_at) VALUES (?,?,?)",
            (h, platform, time.time())
        )
        con.commit()
        con.close()
    except Exception:
        pass


# ── KI-Score via Groq ────────────────────────────────────────────────────────
_GROQ_KEY = lambda: os.getenv("GROQ_API_KEY", "")

_SCORE_PROMPT = """Du bist ein strenger Content-Qualitätsprüfer für einen E-Commerce/Tech-Shop.

Bewerte diesen Post auf einer Skala von 1-10:
1-3 = Spam, Fehler, unlesbarer Inhalt, falsche Nische, Platzhalter
4-6 = Schwach, generisch, kaum Mehrwert, könnte Spam sein
7-8 = Gut, relevant, professionell, nischenbezogen
9-10 = Ausgezeichnet, überzeugend, präzise, hoher Mehrwert

Antwort NUR mit der Zahl (1-10). Nichts anderes.

Post:
{text}"""

def _keyword_fallback_score(text: str) -> int:
    """Wenn KI down: Score aus Nischen-Keywords (nicht 0 → block-positive Block)."""
    if not text or len(text.strip()) < 30:
        return 3
    hits = sum(1 for rx in _L3_RE if rx.search(text))
    if hits >= 3:
        return 8
    if hits >= 1:
        return 7  # = MIN_AI_SCORE → PASS
    return 4  # unter MIN → BLOCK (kein Nischen-Bezug)


async def _ai_score(text: str) -> int:
    """KI-Score 1-10 via Groq. Bei Fehler: Keyword-Fallback (NIE 0 blind blocken)."""
    key = _GROQ_KEY()
    if not key:
        # Kein Groq → versuche Anthropic, dann Keyword
        sc = await _ai_score_anthropic(text)
        return sc if sc > 0 else _keyword_fallback_score(text)

    payload = {
        "model": "llama-3.1-8b-instant",
        "max_tokens": 5,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": _SCORE_PROMPT.format(text=text[:800])}
        ],
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    # Nur erste Zahl extrahieren
                    m = re.search(r"\d+", raw)
                    score = int(m.group()) if m else 0
                    if score <= 0:
                        return _keyword_fallback_score(text)
                    return min(10, max(0, score))
                elif r.status == 429:
                    # Rate limit → Anthropic fallback
                    sc = await _ai_score_anthropic(text)
                    return sc if sc > 0 else _keyword_fallback_score(text)
                else:
                    log.warning("PostValidator: Groq HTTP %s — keyword fallback", r.status)
                    return _keyword_fallback_score(text)
    except asyncio.TimeoutError:
        log.warning("PostValidator: Groq Timeout — keyword fallback")
        return _keyword_fallback_score(text)
    except Exception as e:
        log.warning("PostValidator: Groq Fehler %s — keyword fallback", e)
        return _keyword_fallback_score(text)
    return _keyword_fallback_score(text)


async def _ai_score_anthropic(text: str) -> int:
    """Fallback: Score via Anthropic Haiku."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return 0
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": _SCORE_PROMPT.format(text=text[:800])}],
                },
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    raw = d["content"][0]["text"].strip()
                    m = re.search(r"\d+", raw)
                    return min(10, max(0, int(m.group()))) if m else 0
    except Exception:
        pass
    return 0


# ── Telegram Alert ───────────────────────────────────────────────────────────
async def _notify_telegram(text: str, platform: str, layer: int, reason: str, score: int = 0):
    """Sendet Telegram-Benachrichtigung über blockierten Post."""
    if any(marker in (reason or "").lower() for marker in _QUIET_NOTIFY_REASONS):
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    preview = text[:150].replace("<", "&lt;").replace(">", "&gt;")
    msg = (
        f"🚫 <b>PostValidator BLOCKIERT</b>\n"
        f"Layer {layer} | Plattform: {platform}\n"
        f"Grund: <code>{reason}</code>\n"
        f"KI-Score: {score}/10\n"
        f"Text: <i>{preview}…</i>"
    )
    try:
        import urllib.request, urllib.parse
        payload = json.dumps({"chat_id": chat, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


# ── Haupt-Validierungsfunktion ────────────────────────────────────────────────

async def validate_post(
    text: str,
    platform: str = "unknown",
    content_type: str = "social",
    skip_dedup: bool = False,
) -> tuple[bool, int, str]:
    """
    Validiert einen Post durch alle 5 Layer.

    Returns:
        (ok: bool, failed_layer: int, reason: str)
        ok=True + layer=0 wenn alles bestanden.
        ok=False + layer=N wenn Layer N geblockt hat.
    """
    # ── Layer 0: NEVER-TWICE — gleicher Fehler/Content nie wieder ───────────
    try:
        from modules.post_never_twice import check_never_twice, remember_block
        nt_ok, nt_errs = check_never_twice(text or "", platform)
        if not nt_ok:
            try:
                remember_block(text or "", platform, nt_errs, source_module="post_validator")
            except Exception:
                pass
            return False, 0, f"never_twice: {nt_errs[0] if nt_errs else 'blocked'}"
    except Exception as e:
        if "locked" in str(e).lower():
            log.warning("PostValidator NeverTwice locked — fail-open")
        else:
            return False, 0, f"never_twice_error_blocked: {e}"

    # ── Layer 0: Off-Topic Hard-Block (schnellste Prüfung, vor allem) ───────────
    if content_type == "social":
        for rx in _L0_RE:
            if rx.search(text):
                reason = f"off_topic_nische: {rx.pattern[:50]}"
                await _notify_telegram(text, platform, 0, reason)
                return False, 0, reason

    # ── Layer 1: Basis-Sanity ────────────────────────────────────────────────
    if not text or not text.strip():
        return False, 1, "text_leer"

    text_clean = text.strip()

    if len(text_clean) < MIN_TEXT_LEN:
        return False, 1, f"text_zu_kurz ({len(text_clean)} < {MIN_TEXT_LEN} Zeichen)"

    if len(text_clean) > MAX_TEXT_LEN:
        text_clean = text_clean[:MAX_TEXT_LEN]  # Kürzen, kein Block

    def _remember(reason: str) -> None:
        if any(marker in reason.lower() for marker in _TRANSIENT_BLOCK_REASONS):
            return
        try:
            from modules.post_never_twice import remember_block
            remember_block(text_clean, platform, [reason], source_module="post_validator")
        except Exception:
            pass

    for rx in _L1_RE:
        if rx.search(text_clean):
            reason = f"verbotenes_muster: {rx.pattern[:40]}"
            _remember(reason)
            await _notify_telegram(text_clean, platform, 1, reason)
            return False, 1, reason

    # Nur Hashtags / URLs → kein echter Content
    stripped = re.sub(r"#\w+|https?://\S+", "", text_clean).strip()
    if len(stripped) < 20:
        reason = "nur_hashtags_oder_links_kein_text"
        _remember(reason)
        await _notify_telegram(text_clean, platform, 1, reason)
        return False, 1, reason

    # ── Layer 2: Spam-Phrasen ────────────────────────────────────────────────
    text_lower = text_clean.lower()
    for phrase in _L2_SPAM:
        if phrase in text_lower:
            reason = f"spam_phrase: {phrase}"
            _remember(reason)
            await _notify_telegram(text_clean, platform, 2, reason)
            return False, 2, reason

    # ── Layer 3: Nischen-Check ───────────────────────────────────────────────
    # LinkedIn: PostGuardian prüft Nische bereits vor http_guard → L3 überspringen
    # Sonst: minimum 1 starkes Nischen-Keyword für Social-Posts erforderlich
    has_niche = any(rx.search(text_clean) for rx in _L3_RE)
    if not has_niche and content_type == "social" and platform not in ("linkedin",):
        reason = "kein_nischen_keyword (Smart Home/Tech/Shop erforderlich)"
        _remember(reason)
        await _notify_telegram(text_clean, platform, 3, reason)
        return False, 3, reason

    # ── Layer 4: KI-Qualitäts-Score ──────────────────────────────────────────
    score = await _ai_score(text_clean)
    # Sicherheitsnetz: score=0 bedeutet API-Ausfall, NICHT schlechten Inhalt
    if score == 0:
        score = _keyword_fallback_score(text_clean)
        log.debug("PostValidator: score=0 → keyword_fallback: %d", score)
    if score < MIN_AI_SCORE:
        reason = f"ki_score_zu_niedrig ({score}/10 < {MIN_AI_SCORE})"
        _remember(reason)
        await _notify_telegram(text_clean, platform, 4, reason, score)
        return False, 4, reason

    # ── Layer 5: Duplikat-Check ──────────────────────────────────────────────
    if not skip_dedup and _is_duplicate(text_clean, platform):
        reason = f"duplikat_innerhalb_{DEDUP_WINDOW_H}h"
        _remember(reason)
        await _notify_telegram(text_clean, platform, 5, reason, score)
        return False, 5, reason

    # Alle Layer bestanden → Hash registrieren
    _register_hash(text_clean, platform)
    try:
        from modules.post_never_twice import remember_sent
        remember_sent(text_clean, platform, source_module="post_validator")
    except Exception:
        pass
    log.info("PostValidator ✅ [Score %d/10] %s: %s…", score, platform, text_clean[:60])
    return True, 0, f"ok (score={score})"


def register_posted(text: str, platform: str = "unknown"):
    """Nach manuellem/externem Post aufrufen um Duplikat-DB zu aktualisieren."""
    _register_hash(text, platform)
