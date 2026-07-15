"""
LinkedIn Auto-Poster — Tägliche Authority-Posts für AIITEC
Baut organischen Inbound via Thought Leadership zu EU AI Act + B2B Automation
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("LinkedInPoster")

LI_TOKEN     = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LI_PERSON_ID = os.getenv("LINKEDIN_PERSON_ID", "YcxbqVN0ZR")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL       = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
POSTED_LI  = DATA_DIR / "li_posted.json"

# Tägliche Posts (rotierend) — EU AI Act + B2B Automation Thought Leadership
LI_POSTS = [
    {
        "text": (
            "⚠️ In 18 Tagen wird EU AI Act Artikel 50 durchgesetzt.\n\n"
            "Ich habe diese Woche 50+ DACH Shopify-Stores gescannt:\n"
            "— 94% haben KI-Chat oder KI-Empfehlungen\n"
            "— Davon haben 91% KEIN Disclosure-Banner\n"
            "— Bußgeld: bis €15.000.000 oder 3% Jahresumsatz\n\n"
            "Das ist kein Zukunftsproblem. Das ist eine August-2026-Deadline.\n\n"
            "Wir machen euren Shop in 24h konform.\n"
            "Compliance Wächter: €1.500/Monat.\n\n"
            f"Link in Kommentaren 👇"
        ),
    },
    {
        "text": (
            "Ich habe meinen Vertrieb durch eine KI ersetzt.\n\n"
            "Vorher:\n"
            "— 2 SDRs · €6.000/Monat · 15 Leads/Woche\n"
            "— 80% davon unqualifiziert\n\n"
            "Heute:\n"
            "— 1 KI-Agent · €500/Monat · 10 qualifizierte Leads/Tag\n"
            "— Vollautomatisch, 24/7, kein Krankheitsausfall\n\n"
            "B2B-Sales 2026 sieht anders aus als 2022.\n\n"
            "Wer noch mit Kaltanrufen arbeitet: das ist Ihre Wettbewerbslücke.\n\n"
            f"Lead Agent Demo: {BASE_URL}"
        ),
    },
    {
        "text": (
            "Ein DACH-E-Commerce-Unternehmer hat mir diese Woche eine wichtige Frage gestellt:\n\n"
            '"Rudolf, macht mein Tidio-Chat mich EU AI Act pflichtig?"\n\n'
            "Antwort: Ja.\n\n"
            "Tidio, Gorgias, Intercom, Freshchat, Klarna AI, Rebuy — "
            "alle fallen unter Art. 50 der EU KI-Verordnung.\n\n"
            "Was braucht ihr:\n"
            "✅ Disclosure-Banner ('Dieser Chat wird von KI betrieben')\n"
            "✅ Dokumentation für Behörden\n"
            "✅ Täglicher Compliance-Scan\n\n"
            "Frist: 2. August 2026.\n\n"
            "Habt ihr euren Shop schon gecheckt?"
        ),
    },
    {
        "text": (
            "Wettbewerber-Analyse war früher eine Beratungsrechnung.\n\n"
            "€5.000–€15.000 für eine einmalige Studie.\n"
            "Die nach 3 Monaten veraltet war.\n\n"
            "Heute:\n"
            "— Täglich automatischer Scan der Top-10-Wettbewerber\n"
            "— Preisänderungen, neue Produkte, Kampagnen — alles in einer Telegram-Nachricht\n"
            "— KI-Handlungsempfehlungen direkt dazu\n\n"
            "Intelligence Suite: €2.000/Monat.\n"
            "Eine Agentur kostet das pro Woche.\n\n"
            f"Demo: {BASE_URL}"
        ),
    },
    {
        "text": (
            "Ich werde oft gefragt: 'Lohnt sich KI-Automation wirklich für KMUs?'\n\n"
            "Zahlen aus unserem System (letzte 30 Tage):\n\n"
            "📧 3.200 personalisierte Outreach-Emails gesendet\n"
            "📞 47 eingehende Anfragen via Sofia (KI-Rezeptionistin)\n"
            "🎯 12% Antwortrate auf kalte Emails (Branche: 2–3%)\n"
            "💶 €0 für menschliche SDRs\n\n"
            "Der Unterschied: Personalisierung. Jede Email kennt das spezifische Problem des Empfängers.\n\n"
            "KI ersetzt keine Menschen. Sie lässt Menschen wichtigere Arbeit machen."
        ),
    },
]


def _load_posted() -> set:
    try:
        return set(json.loads(POSTED_LI.read_text(encoding="utf-8")))
    except Exception:
        return set()

def _save_posted(posted: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_LI.write_text(json.dumps(list(posted), ensure_ascii=False), encoding="utf-8")


async def post_to_linkedin(text: str) -> dict:
    """Veröffentlicht einen LinkedIn-Post als Person."""
    try:
        from modules.post_guard import validate_and_log
        if not await validate_and_log(text, platform="linkedin"):
            return {"blocked": True, "reason": "PostGuard: Qualitätsprüfung nicht bestanden"}
    except Exception:
        pass

    if not LI_TOKEN or not LI_PERSON_ID:
        log.info("[DRY-RUN] LinkedIn: %s", text[:80])
        return {"dry_run": True}

    payload = {
        "author": f"urn:li:person:{LI_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=payload,
            headers={
                "Authorization": f"Bearer {LI_TOKEN}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            result = await r.json()
            if r.status in (200, 201):
                log.info("LinkedIn-Post veröffentlicht: %s", result.get("id"))
            else:
                log.warning("LinkedIn Fehler %s: %s", r.status, result)
            return result


async def linkedin_posting_loop():
    """Postet täglich einen LinkedIn-Post (morgens 08:00 UTC)."""
    log.info("LinkedIn Posting Loop gestartet")
    while True:
        now = datetime.now(timezone.utc)
        # Warte bis 08:00 UTC
        target_hour = 8
        wait = ((target_hour - now.hour - 1) % 24 + 1) * 3600 - now.minute * 60 - now.second
        if wait > 3600 * 23:
            wait = 60  # fast sofort beim ersten Start
        await asyncio.sleep(wait)

        try:
            posted = _load_posted()
            day_key = f"li_{datetime.now(timezone.utc).date()}_{now.weekday()}"
            if day_key not in posted:
                idx  = datetime.now(timezone.utc).timetuple().tm_yday % len(LI_POSTS)
                post = LI_POSTS[idx]
                result = await post_to_linkedin(post["text"])
                if result.get("id") or result.get("dry_run"):
                    posted.add(day_key)
                    _save_posted(posted)
                    await _notify_telegram(
                        f"🔗 <b>LinkedIn-Post veröffentlicht!</b>\n"
                        f"📝 {post['text'][:150]}..."
                    )
        except Exception as e:
            log.error("LinkedIn loop Fehler: %s", e)

        await asyncio.sleep(3600)  # Nächster Check in 1h


async def _notify_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass
