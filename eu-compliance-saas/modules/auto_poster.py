"""Auto-Poster — Twitter/X + Telegram für EU Compliance SaaS
Postet täglich 3x auf Twitter, alle 6h auf Telegram.
Inhalte werden via Claude Haiku generiert.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("AutoPoster")

TWITTER_API_KEY      = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET   = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "") or os.getenv("TWITTER_ACCESS_SECRET", "")
TELEGRAM_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT        = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY        = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL             = os.getenv("RAILWAY_STATIC_URL", "https://eu-compliance-saas-production.up.railway.app")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
POSTED_FILE = DATA_DIR / "compliance_posted.json"

TWEET_TOPICS = [
    ("ai_act_urgency", "Die EU KI-Verordnung Art. 50 tritt am 2. August 2026 in Kraft. Shopify-Shops mit KI-Chat oder KI-Empfehlungen müssen JETZT eine Offenlegung einbauen — Bußgeld bis €15 Mio. Gibt es ein Tool dafür?"),
    ("customs_reform", "Seit 1. Juli 2026: Die EU hat die €150-Zollfreigrenze abgeschafft. Jedes Paket aus China/USA kostet jetzt €3+ Zoll pro HS-Code. Wer seine Produkte noch nicht klassifiziert hat, zahlt blind drauf."),
    ("vat_trap", "Nicht-EU-Shops (USA, China, UK) haben KEINEN Mindestbetrag für EU-Mehrwertsteuer. Ab dem ersten Verkauf an einen EU-Kunden: MwSt im Zielland fällig. Die meisten wissen das nicht — bis zum Betriebsprüfer."),
    ("zvg_nrw", "NRW macht ≈19% aller deutschen Zwangsversteigerungen aus. 8.500+ Fälle/Jahr. B2B-Leads für Insolvenzverwalter: €50–200 pro Kontakt. KI-nativer Radar bisher: keiner. Marktlücke."),
    ("deadline_count", "⏰ Noch {} Tage bis zur AI-Act-Pflicht (Art. 50 EU-KI-VO). Danach: Bußgeld bis €15.000.000 oder 3% Jahresumsatz. €49/Monat reichen zum Schutz."),
    ("fine_math", "Mach die Mathe: KI-Act-Bußgeld bis €15.000.000. Compliance-Tool: €49/Monat = €588/Jahr. ROI: 25.500x. Kein Vergleich."),
    ("hs_code_pain", "300 Produkte ohne HS-Code = €300 × €5 Zollaufwand pro Bestellung = teuer. Ein ML-Classifier löst das in Sekunden. EU-Pflicht ab 1. Juli 2026."),
]

TELEGRAM_POSTS = [
    "🚨 <b>EU KI-Act Countdown</b>\n⏰ Noch <b>{days} Tage</b> bis Artikel 50 in Kraft tritt.\nShops mit KI-Chat ohne Disclosure: Bußgeld bis <b>€15 Mio.</b>\n\n💡 <b>Fix in 10 Minuten:</b> {url}/api/scan → Banner-Code kopieren → einbauen.\n\nOder einfach Starter-Plan ab <b>€49/Monat</b>: {url}",
    "📦 <b>EU Zollreform: Jetzt aktiv</b>\n€150-Freigrenze ist Geschichte (seit 1. Juli 2026).\n\nJedes Paket aus China/USA/UK:\n• €3 Pauschalzoll pro HS-Code-Unterposition\n• + ~€2 Bearbeitungsgebühr\n• = <b>€5 pro Sendung</b> ohne Automatisierung\n\n🤖 HS-Code Batch-Classifier: {url}",
    "🇪🇺 <b>VAT-Falle für Nicht-EU-Shops</b>\nUS, UK, China: <b>KEIN Schwellenwert!</b>\nAb Verkauf Nr. 1 an EU-Kunden: Zielland-MwSt (17–27%) fällig.\nMost non-EU sellers ignore this until audit.\n\n📋 OSS-Registrierungsassistent + Quartals-Prefill: {url}",
    "🏠 <b>ZVG NRW: {count} neue Leads</b>\nNordrhein-Westfalen: ≈19% des deutschen Zwangsversteigerungs-Volumens.\nTop heute: {top_type} in {top_loc} — Schätzwert €{top_val:,.0f}\n\n💼 Für Insolvenzverwalter + Distress-Investoren: {url}/api/zvg/leads",
]


def _days_to_deadline() -> int:
    diff = datetime(2026, 8, 2, tzinfo=timezone.utc) - datetime.now(timezone.utc)
    return max(0, diff.days)


# ── Twitter OAuth 1.0a ────────────────────────────────────────────────────────
def _oauth_header(method: str, url: str) -> str:
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return ""
    params = {
        "oauth_consumer_key":     TWITTER_API_KEY,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            TWITTER_ACCESS_TOKEN,
        "oauth_version":          "1.0",
    }
    param_str = "&".join(
        f"{urllib.parse.quote(k,'=')}={urllib.parse.quote(str(v),'=')}"
        for k, v in sorted(params.items())
    )
    base_str = "&".join([method.upper(), urllib.parse.quote(url, safe=""), urllib.parse.quote(param_str, safe="")])
    signing_key = f"{urllib.parse.quote(TWITTER_API_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_SECRET, safe='')}"
    sig = base64.b64encode(hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{urllib.parse.quote(k,safe="")}="{urllib.parse.quote(str(v),safe="")}"' for k, v in sorted(params.items()))


async def _post_tweet(text: str) -> bool:
    if not TWITTER_API_KEY:
        log.info("[DRY-RUN] Tweet: %s", text[:80])
        return True
    url = "https://api.twitter.com/2/tweets"
    auth = _oauth_header("POST", url)
    if not auth:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"text": text[:280]},
                              headers={"Authorization": auth, "Content-Type": "application/json"},
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                ok = r.status in (200, 201)
                if not ok:
                    log.warning("Twitter %s: %s", r.status, await r.text())
                return ok
    except Exception as e:
        log.error("Twitter post error: %s", e)
        return False


async def _post_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        log.info("[DRY-RUN] Telegram: %s", text[:80])
        return True
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                return r.status == 200
    except Exception as e:
        log.error("Telegram post error: %s", e)
        return False


async def _generate_tweet_claude(topic_hint: str) -> str | None:
    """Generiert Tweet-Text via Claude Haiku."""
    if not ANTHROPIC_KEY:
        return None
    days = _days_to_deadline()
    prompt = (
        f"Schreibe einen kurzen, präzisen deutschen Tweet (max 270 Zeichen) über EU E-Commerce-Compliance für Shopify-Shop-Besitzer. "
        f"Thema: {topic_hint}. Heute sind es noch {days} Tage bis zur EU-KI-Act-Frist (2.8.2026). "
        f"Kein Hashtag-Spam, max 2 Hashtags. Kein Emoji-Spam, max 2 Emojis. Direkt und faktenbasiert. "
        f"Erwähne am Ende: {BASE_URL} — NUR den Text, keine Anführungszeichen."
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 120,
                      "messages": [{"role": "user", "content": prompt}]},
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["content"][0]["text"].strip().strip('"').strip("'")
    except Exception as e:
        log.warning("Claude tweet gen error: %s", e)
    return None


def _load_posted() -> set:
    try:
        return set(json.loads(POSTED_FILE.read_text()))
    except Exception:
        return set()


def _mark_posted(key: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    posted = _load_posted()
    posted.add(key)
    POSTED_FILE.write_text(json.dumps(sorted(posted)))


# ── Public loops ──────────────────────────────────────────────────────────────
async def twitter_posting_loop():
    """Postet 3x täglich auf Twitter/X."""
    posted = _load_posted()
    topic_idx = 0
    while True:
        try:
            days = _days_to_deadline()
            topic_key, topic_hint = TWEET_TOPICS[topic_idx % len(TWEET_TOPICS)]
            post_key = f"tw_{topic_key}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

            if post_key not in posted:
                text = await _generate_tweet_claude(topic_hint)
                if not text:
                    text = topic_hint.format(days) if "{}" in topic_hint else topic_hint
                    text = text[:270] + f" {BASE_URL}"
                ok = await _post_tweet(text)
                if ok:
                    _mark_posted(post_key)
                    posted.add(post_key)
                    log.info("Tweet posted: %s", post_key)

            topic_idx += 1
        except Exception as e:
            log.error("Twitter loop error: %s", e)

        await asyncio.sleep(8 * 3600)  # 3x täglich


async def telegram_marketing_loop(leads_cache_ref: list):
    """Postet alle 6h einen Compliance-Alert auf Telegram."""
    post_idx = 0
    while True:
        try:
            days = _days_to_deadline()
            template = TELEGRAM_POSTS[post_idx % len(TELEGRAM_POSTS)]

            if "{count}" in template and leads_cache_ref:
                top = leads_cache_ref[0] if leads_cache_ref else {}
                text = template.format(
                    count=len(leads_cache_ref),
                    top_type=top.get("property_type", "Objekt"),
                    top_loc=top.get("location", "NRW"),
                    top_val=top.get("estimated_value_eur", 250000),
                    url=BASE_URL,
                )
            else:
                text = template.format(days=days, url=BASE_URL) if "{days}" in template else template.format(url=BASE_URL)

            await _post_telegram(text)
            log.info("Telegram post %d sent", post_idx)
            post_idx += 1
        except Exception as e:
            log.error("Telegram marketing loop error: %s", e)
        await asyncio.sleep(6 * 3600)


async def post_new_subscriber_announcement(email: str, plan: str, price: int):
    """Wird nach jedem Stripe-Payment getriggert."""
    await _post_telegram(
        f"✅ <b>NEUER SUBSCRIBER!</b>\n"
        f"💌 {email[:3]}***@{email.split('@')[-1] if '@' in email else '?'}\n"
        f"📦 Plan: <b>{plan}</b> — €{price}/Monat\n"
        f"📈 MRR +€{price}"
    )
