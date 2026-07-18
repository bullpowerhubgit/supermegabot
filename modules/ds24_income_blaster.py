"""
DS24 Income Blaster — kontrollierte DS24-Kommunikation auf freigegebenen Kanälen
====================================================================
Postet nur freigegebene, valide DS24-Angebote.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

log = logging.getLogger("DS24Blaster")

FB_PAGE_ID     = "1016738738178786"
_DB = Path(__file__).parent.parent / "data" / "ds24_blaster.db"

TEMPLATES = [
    "💡 KI-Workflows fuer digitale Angebote klar strukturieren.\n\n✅ Uebersichtliche Prozesse\n✅ Praxisnahe Automationen\n✅ Saubere Umsetzung statt leere Versprechen\n\nMehr erfahren: {LINK}\n\n#KI #Digistore24 #DigitalBusiness",
    "⚡ Digitale Produkt-Workflows besser aufsetzen.\n\n📦 Klarer Aufbau\n🛠️ Konkrete Umsetzungsschritte\n📈 Fokus auf Struktur und Nachvollziehbarkeit\n\nDetails: {LINK}\n\n#Automation #Digistore24 #Workflow",
    "🚀 E-Commerce- und Funnel-Ablaufe systematisch verbessern.\n\n✅ Schritt-fuer-Schritt\n✅ Weniger manueller Aufwand\n✅ Realistische Prozessoptimierung\n\nAnsehen: {LINK}\n\n#ECommerce #Automatisierung #DACH",
]


def _approved_link() -> str:
    try:
        from modules.ds24_link_guardian import get_ds24_link
        return get_ds24_link("social")
    except Exception:
        return os.getenv("DS24_AFFILIATE_LINK", "")


# ── DB ─────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blast_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            platform   TEXT NOT NULL,
            content    TEXT,
            posted_at  REAL NOT NULL,
            success    INTEGER DEFAULT 1,
            error      TEXT
        )
    """)
    conn.commit()
    return conn


def _log_post(platform: str, content: str, success: bool, error: str = "") -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO blast_log (platform, content, posted_at, success, error) VALUES (?,?,?,?,?)",
            (platform, content[:500], time.time(), int(success), error)
        )
        c.commit()


def _posts_today(platform: str) -> int:
    cutoff = time.time() - 86400
    with _db() as c:
        row = c.execute(
            "SELECT COUNT(*) FROM blast_log WHERE platform=? AND posted_at>? AND success=1",
            (platform, cutoff)
        ).fetchone()
        return row[0] if row else 0


# ── Content ────────────────────────────────────────────────────────────────────

async def generate_promo_content() -> str:
    """KI Content via ai_complete oder hardcoded Template."""
    link = _approved_link()
    if not link:
        log.warning("DS24 Blaster: kein freigegebener DS24-Link verfügbar")
        return ""
    from modules.ai_client import ai_complete
    prompt = (
        "Schreibe einen kurzen deutschen Social-Media-Post über KI-Automatisierung "
        "und digitale Produkt-Workflows. Max 180 Wörter. Nutze Emojis sparsam. Füge am Ende ein "
        f"Platzhalter {{LINK}} für den Affiliate-Link ein. Hashtags hinzufügen."
    )
    try:
        text = await ai_complete(prompt, max_tokens=200)
        if text:
            if "{LINK}" not in text:
                text += f"\n\n👉 {link}"
            else:
                text = text.replace("{LINK}", link)
            return text
    except Exception as e:
        log.warning("ai_complete Fehler: %s — nutze Template", e)

    tpl = random.choice(TEMPLATES)
    return tpl.replace("{LINK}", link)


# ── Plattformen ────────────────────────────────────────────────────────────────

async def post_to_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        log.warning("Telegram: keine Credentials")
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                res = await r.json()
                ok = res.get("ok", False)
                _log_post("telegram", text, ok, str(res.get("description", "")))
                if ok:
                    log.info("✅ Telegram Post OK")
                return ok
    except Exception as e:
        _log_post("telegram", text, False, str(e))
        log.error("Telegram Fehler: %s", e)
        return False


async def post_to_facebook(text: str) -> bool:
    token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
             or os.getenv("FACEBOOK_PAGE_TOKEN")
             or os.getenv("META_ADS_TOKEN", ""))
    if not token:
        log.warning("Facebook: kein Token")
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
                data={"message": text, "access_token": token},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                res = await r.json()
                ok = "id" in res
                _log_post("facebook", text, ok, str(res.get("error", {}).get("message", "")))
                if ok:
                    log.info("✅ Facebook Post OK: %s", res["id"])
                else:
                    log.warning("Facebook Fehler: %s", res.get("error", {}).get("message"))
                return ok
    except Exception as e:
        _log_post("facebook", text, False, str(e))
        log.error("Facebook Fehler: %s", e)
        return False


async def post_to_linkedin(text: str) -> bool:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    owner = os.getenv("LINKEDIN_PERSON_URN", "")
    if not token or not owner:
        log.warning("LinkedIn: kein Token/URN")
        return False
    try:
        if not owner.startswith("urn:li:"):
            owner = f"urn:li:person:{owner}"
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json={
                    "author": owner,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {"text": text[:3000]},
                            "shareMediaCategory": "NONE"
                        }
                    },
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                },
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                ok = r.status in (200, 201)
                body = await r.text()
                _log_post("linkedin", text, ok, "" if ok else body[:200])
                if ok:
                    log.info("✅ LinkedIn Post OK")
                return ok
    except Exception as e:
        _log_post("linkedin", text, False, str(e))
        log.error("LinkedIn Fehler: %s", e)
        return False


# ── DS24 Stats ─────────────────────────────────────────────────────────────────

async def get_ds24_stats() -> dict:
    api_key = os.getenv("DS24_API_KEY", "")
    if not api_key:
        return {"error": "DS24_API_KEY nicht gesetzt"}
    try:
        url = f"https://www.digistore24.com/api/v1/{api_key}/json/listSalesOfPeriod/today"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
                sales = data.get("data", {}).get("sales", [])
                total = sum(float(s_.get("amount", 0)) for s_ in sales)
                return {
                    "sales_today": len(sales),
                    "revenue_today_eur": round(total, 2),
                    "sales": sales[:5],
                }
    except Exception as e:
        return {"error": str(e)}


# ── Hauptfunktionen ────────────────────────────────────────────────────────────

async def run_ds24_blast() -> dict:
    """4× täglich: Content generieren und auf allen Kanälen posten."""
    from modules.agent_coordinator import run as coord_run
    async with coord_run("ds24_blast", "ds24_income_blaster", ttl=3600, reuse_result_age=3000) as ctx:
        if ctx.already_running:
            log.info("DS24 Blast zu frisch — übersprungen")
            return ctx.last_result.get("result", {"skipped": True}) if ctx.last_result else {"skipped": True}
        result = await _blast_inner()
        ctx.result = result
        return result


async def _blast_inner() -> dict:
    content = await generate_promo_content()
    if not content:
        return {"status": "skipped", "reason": "no_approved_link"}
    from modules.post_validator import validate_post
    ok, _layer, reason = await validate_post(content, platform="telegram", content_type="social")
    if not ok:
        log.warning("DS24 Blast blocked by validator: %s", reason)
        return {"status": "blocked", "reason": reason}
    results: dict[str, bool] = {}

    # Max 4 Posts/Tag pro Plattform
    tasks = []
    if _posts_today("telegram") < 4:
        tasks.append(("telegram", post_to_telegram(content)))
    if _posts_today("facebook") < 2:
        tasks.append(("facebook", post_to_facebook(content)))
    if _posts_today("linkedin") < 2:
        tasks.append(("linkedin", post_to_linkedin(content)))

    if not tasks:
        log.info("DS24 Blast: Tageslimit erreicht")
        return {"status": "limit_reached", "posts": {}}

    done = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)
    for (platform, _), res in zip(tasks, done):
        results[platform] = bool(res) if not isinstance(res, Exception) else False

    ok_count = sum(results.values())
    log.info("DS24 Blast: %d/%d Plattformen erfolgreich", ok_count, len(results))
    return {"status": "ok", "platforms": results, "content_snippet": content[:100]}


async def run_affiliate_blast_now() -> dict:
    """Sofort-Blast (ignoriert Coordinator-Cache)."""
    content = await generate_promo_content()
    if not content:
        return {"blocked": True, "reason": "no_approved_link"}
    from modules.post_validator import validate_post
    ok, _layer, reason = await validate_post(content, platform="telegram", content_type="social")
    if not ok:
        log.warning("DS24 immediate blast blocked by validator: %s", reason)
        return {"blocked": True, "reason": reason}
    tg = await post_to_telegram(content)
    fb = await post_to_facebook(content)
    li = await post_to_linkedin(content)
    return {"telegram": tg, "facebook": fb, "linkedin": li}


def get_stats() -> dict:
    with _db() as c:
        rows = c.execute(
            "SELECT platform, COUNT(*) as cnt, SUM(success) as ok "
            "FROM blast_log WHERE posted_at > ? GROUP BY platform",
            (time.time() - 86400,)
        ).fetchall()
    today = {r["platform"]: {"total": r["cnt"], "ok": r["ok"]} for r in rows}
    return {"posts_today": today, "affiliate_link": _approved_link()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run_ds24_blast())
    print(json.dumps(result, ensure_ascii=False, indent=2))
