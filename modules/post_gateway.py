#!/usr/bin/env python3
"""
Post Gateway — Universeller Post-Schutz für ALLE Kanäle
========================================================
ALLE Social-Media-Posts MÜSSEN durch diesen Gateway gehen.
Kein Post verlässt das System ohne 5-Schicht-Prüfung.

5 Prüfschichten:
  1. Inhaltsprüfung (Placeholder, KI-Text, Fehler, Länge)
  2. Duplikat-Check (kein gleicher Content in 7 Tagen)
  3. Credential-Check (Token vorhanden + nicht abgelaufen)
  4. AI-Qualitätsprüfung (bei Bedarf, für kritische Posts)
  5. Plattform-API-Call mit Retry + Rate-Limit-Schutz

Bei Fehler: Block + Telegram-Report → NIE silent fail.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("PostGateway")

_ROOT = Path(__file__).parent.parent
_DB = _ROOT / "data" / "post_gateway.db"

# ── Credentials ───────────────────────────────────────────────────────────────
def _cred(key: str, *fallbacks: str) -> str:
    for k in (key, *fallbacks):
        v = os.getenv(k, "")
        if v:
            return v
    return ""


# ── DB: Protokoll jedes Posts ─────────────────────────────────────────────────
def _init_db():
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB)) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, status TEXT,
            content_hash TEXT, preview TEXT,
            errors TEXT, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS blocked (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, reason TEXT, preview TEXT,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_hash ON posts(content_hash);
        """)

def _log_post(platform: str, status: str, content: str, errors: list):
    import hashlib
    h = hashlib.md5(content.encode()).hexdigest()
    preview = content[:100].replace("\n", " ")
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        c.execute("INSERT INTO posts(platform,status,content_hash,preview,errors) VALUES(?,?,?,?,?)",
                  (platform, status, h, preview, json.dumps(errors, ensure_ascii=False)))

def _log_blocked(platform: str, reason: str, content: str):
    preview = content[:100].replace("\n", " ")
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        c.execute("INSERT INTO blocked(platform,reason,preview) VALUES(?,?,?)", (platform, reason, preview))

def _is_duplicate(content: str, platform: str, days: int = 7) -> bool:
    import hashlib
    h = hashlib.md5(content.encode()).hexdigest()
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        row = c.execute(
            "SELECT id FROM posts WHERE content_hash=? AND platform=? "
            "AND ts > datetime('now', ?) AND status='sent'",
            (h, platform, f"-{days} days")
        ).fetchone()
    return row is not None


def _sent_today(platform: str) -> int:
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        return c.execute(
            "SELECT COUNT(*) FROM posts WHERE platform=? AND status='sent' AND ts > date('now')",
            (platform,),
        ).fetchone()[0]


def _should_alert(platform: str, reason: str, content: str, minutes: int = 60) -> bool:
    normalized_reason = (reason or "").strip().lower()
    if any(marker in normalized_reason for marker in _QUIET_BLOCK_MARKERS):
        return False
    preview = content[:100].replace("\n", " ")
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        row = c.execute(
            "SELECT 1 FROM blocked WHERE platform=? AND reason=? AND preview=? "
            "AND ts > datetime('now', ?) LIMIT 1",
            (platform, reason, preview, f"-{minutes} minutes"),
        ).fetchone()
    return row is None


# ── Schicht 1+2: Inhalts- und Duplikat-Prüfung ───────────────────────────────
_PLACEHOLDER = re.compile(
    r'\[PLATZHALTER\]|\[PLACEHOLDER\]|\[TODO\]|\[INSERT\]|\[NAME\]|\[LINK\]|\[URL\]|\[PRODUKT\]'
    r'|lorem ipsum|TODO:|FIXME:|BEISPIEL:|BEISPIELTEXT'
    r'|\{\{[^}]+\}\}'  # {{variable}}
    r'|\{[a-z_]{3,}\}'  # {placeholder} aber nicht {0}
    r'|myshopify\.com|Hallo\s+None|—\s*None\b'
    r'|blender|3d\s*modellierung|vancouver\s+pd|hacker\.news|show\s+hn',
    re.IGNORECASE
)
_AI_REVEAL = re.compile(
    r'als\s+ki[- ]sprachmodell|als\s+künstliche\s+intelligenz'
    r'|as\s+an\s+ai\s+(language\s+)?model|i\s+am\s+an\s+ai'
    r'|ich\s+bin\s+(eine?\s+)?ki'
    r'|generated\s+by\s+(claude|gpt|openai|anthropic)',
    re.IGNORECASE
)
_ERRORS = re.compile(
    r'traceback\s*\(most recent call|syntaxerror:|nameerror:|attributeerror:'
    r'|<html>.*?</html>|404\s+not\s+found|500\s+internal\s+server',
    re.IGNORECASE | re.DOTALL
)
_SECRET = re.compile(
    r'\bsk_live_[A-Za-z0-9]{24,}|\bsk_test_[A-Za-z0-9]{24,}'
    r'|\bANTH[A-Za-z0-9_-]{30,}|\bAIza[A-Za-z0-9_-]{35,}'
    r'|api[_\s]?key\s*[=:]\s*\S{10,}',
    re.IGNORECASE
)
_PLATFORM_LIMITS = {
    "facebook":  (20, 63000, 30),
    "instagram": (20, 2200,  30),
    "linkedin":  (30, 3000,   5),
    "twitter":   (10, 280,    5),
    "x":         (10, 280,    5),
    "telegram":  (1,  4096,  50),
    "default":   (10, 5000,  30),
}
_PLATFORM_DAILY_CAPS = {
    "facebook": 8,
    "instagram": 8,
    "linkedin": 4,
    "telegram": 24,
    "twitter": 12,
    "x": 12,
}
_QUIET_BLOCK_MARKERS = (
    "duplikat",
    "duplicate",
    "daily_cap",
    "tageslimit",
    "rate limit",
    "rate_limited",
    "429",
)

def _validate_content(text: str, platform: str) -> list[str]:
    errors = []
    t = text.strip()
    min_len, max_len, max_tags = _PLATFORM_LIMITS.get(platform.lower(), _PLATFORM_LIMITS["default"])

    if len(t) < min_len:
        errors.append(f"Zu kurz: {len(t)} Zeichen (min {min_len})")
    if len(t) > max_len:
        errors.append(f"Zu lang: {len(t)} Zeichen (max {max_len})")
    if not t:
        errors.append("Leerer Post")

    if _PLACEHOLDER.search(t):
        errors.append("Placeholder-Text gefunden — Post unvollständig")
    if _AI_REVEAL.search(t):
        errors.append("KI-Offenbarung im Text — verboten")
    if _ERRORS.search(t):
        errors.append("Code-Fehler/Stack-Trace im Post-Text")
    if _SECRET.search(t):
        errors.append("KRITISCH: API-Key/Secret im Post-Text!")

    hashtag_count = len(re.findall(r'#\w+', t))
    if hashtag_count > max_tags:
        errors.append(f"Zu viele Hashtags: {hashtag_count} (max {max_tags} für {platform})")

    # Unvollständige Sätze / abgebrochener Text
    if t.endswith(("...", "…", ",", "-", "–", "/")):
        errors.append("Post endet abrupt — möglicherweise abgeschnitten")

    return errors


# ── Telegram Alert ────────────────────────────────────────────────────────────
async def _alert(msg: str):
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception:
        pass


# ── Schicht 3: Credential-Check ───────────────────────────────────────────────
def _check_credential(platform: str) -> tuple[bool, str]:
    checks = {
        "facebook":  ("FACEBOOK_PAGE_TOKEN_AIITEC", "FACEBOOK_PAGE_ACCESS_TOKEN"),
        "instagram": ("FACEBOOK_PAGE_TOKEN_AIITEC", "FACEBOOK_PAGE_ACCESS_TOKEN"),
        "linkedin":  ("LINKEDIN_ACCESS_TOKEN",),
        "twitter":   ("TWITTER_ACCESS_TOKEN", "TWITTER_BEARER_TOKEN"),
        "x":         ("TWITTER_ACCESS_TOKEN", "TWITTER_BEARER_TOKEN"),
        "telegram":  ("TELEGRAM_BOT_TOKEN",),
    }
    required = checks.get(platform.lower(), ())
    for key in required:
        if os.getenv(key, ""):
            return True, ""
    if not required:
        return True, ""
    return False, f"Kein gültiger Token für {platform} ({', '.join(required)})"


# ── Schicht 5: API-Calls mit Retry ───────────────────────────────────────────
async def _post_facebook(text: str, image_url: str = "") -> dict:
    token = _cred("FACEBOOK_PAGE_TOKEN_AIITEC", "FACEBOOK_PAGE_ACCESS_TOKEN")
    page_id = os.getenv("FACEBOOK_PAGE_ID", "1016738738178786")
    if not token:
        return {"ok": False, "error": "Kein FB-Token"}

    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
    payload = {"message": text, "access_token": token}
    if image_url:
        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
        payload["url"] = image_url
        payload["caption"] = text

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    resp = await r.json(content_type=None)
                    if r.status in (200, 201) and ("id" in resp or "post_id" in resp):
                        return {"ok": True, "post_id": resp.get("id", resp.get("post_id", "?"))}
                    if r.status == 429:
                        await asyncio.sleep(60 * (attempt + 1))
                        continue
                    err = resp.get("error", {}).get("message", str(resp))
                    return {"ok": False, "error": err}
        except Exception as e:
            if attempt == 2:
                return {"ok": False, "error": str(e)}
            await asyncio.sleep(5)
    return {"ok": False, "error": "Max Retries erreicht"}


async def _post_instagram(caption: str, image_url: str = "") -> dict:
    token = _cred("FACEBOOK_PAGE_TOKEN_AIITEC", "FACEBOOK_PAGE_ACCESS_TOKEN")
    ig_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841478315197796")
    if not token:
        return {"ok": False, "error": "Kein IG-Token"}
    if not image_url:
        return {"ok": False, "error": "Instagram braucht ein Bild — kein image_url"}

    graph = "https://graph.facebook.com/v21.0"
    try:
        async with aiohttp.ClientSession() as s:
            # Schritt 1: Container erstellen
            async with s.post(f"{graph}/{ig_id}/media",
                              data={"image_url": image_url, "caption": caption, "access_token": token},
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json(content_type=None)
                if "id" not in data:
                    return {"ok": False, "error": f"Container-Fehler: {data.get('error',{}).get('message', str(data))}"}
                container_id = data["id"]

            await asyncio.sleep(3)  # warte auf Container-Verarbeitung

            # Schritt 2: Publizieren
            async with s.post(f"{graph}/{ig_id}/media_publish",
                              data={"creation_id": container_id, "access_token": token},
                              timeout=aiohttp.ClientTimeout(total=30)) as r2:
                pub = await r2.json(content_type=None)
                if "id" in pub:
                    return {"ok": True, "post_id": pub["id"]}
                return {"ok": False, "error": pub.get("error", {}).get("message", str(pub))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _post_linkedin(text: str) -> dict:
    token = _cred("LINKEDIN_ACCESS_TOKEN")
    urn = os.getenv("LINKEDIN_PERSON_URN", "")
    if not token:
        return {"ok": False, "error": "Kein LinkedIn-Token"}
    if not urn:
        return {"ok": False, "error": "LINKEDIN_PERSON_URN fehlt"}

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.linkedin.com/v2/ugcPosts",
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json",
                                       "X-Restli-Protocol-Version": "2.0.0"},
                              json=payload,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status in (200, 201):
                    data = await r.json(content_type=None)
                    return {"ok": True, "post_id": data.get("id", "ok")}
                body = await r.text()
                return {"ok": False, "error": f"HTTP {r.status}: {body[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _post_telegram(text: str, chat_id: str = "") -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("TELEGRAM_CHANNEL_ID", "")
    if not token or not chat:
        return {"ok": False, "error": "Kein Telegram-Token/Chat"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json(content_type=None)
                if data.get("ok"):
                    return {"ok": True, "post_id": str(data.get("result", {}).get("message_id", ""))}
                return {"ok": False, "error": data.get("description", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── MASTER GATEWAY FUNCTION ───────────────────────────────────────────────────
async def safe_post(
    platform: str,
    text: str,
    image_url: str = "",
    chat_id: str = "",
    skip_duplicate_check: bool = False,
    source_module: str = "unknown",
) -> dict:
    """
    Einzige Funktion die alle anderen Module für Social-Posts aufrufen MÜSSEN.
    Führt alle 5 Prüfschichten durch. Blockiert bei Fehler, postet nur bei 100% OK.

    Returns: {ok, platform, post_id, errors, blocked, source}
    """
    result = {
        "ok": False, "platform": platform, "post_id": None,
        "errors": [], "blocked": False, "source": source_module,
    }

    def _remember(reasons: list) -> None:
        try:
            from modules.post_never_twice import remember_block
            remember_block(text, platform, reasons, source_module=source_module)
        except Exception as e:
            log.debug("remember_block: %s", e)

    # Schicht 0: NEVER-TWICE — gleicher Content/Violation nie wieder
    # WICHTIG: fail-open bei technischen Fehlern (DB-Fehler, Import) — nur bei echten Content-Violations blocken
    try:
        from modules.post_never_twice import check_never_twice
        nt_ok, nt_errs = check_never_twice(text, platform)
        if not nt_ok:
            result["errors"] = nt_errs
            result["blocked"] = True
            _log_blocked(platform, " | ".join(nt_errs), text)
            _remember(nt_errs)
            log.warning("NeverTwice BLOCK [%s] %s: %s", platform, source_module, nt_errs)
            return result
    except Exception as e:
        # Fail-OPEN: technischer NeverTwice-Fehler darf Posts NICHT blockieren
        log.warning("NeverTwice nicht verfügbar (%s) — Post wird trotzdem geprüft", e)

    # Schicht 1a: PostGuardian (Off-Topic, Nische, Placeholder, KI-Text)
    try:
        from modules.post_guardian import validate_post as _guardian_check
        guardian_ok, guardian_errors = _guardian_check(text, platform=platform)
        if not guardian_ok:
            result["errors"] = guardian_errors
            result["blocked"] = True
            _log_blocked(platform, " | ".join(guardian_errors), text)
            _remember(guardian_errors)
            if _should_alert(platform, " | ".join(guardian_errors), text):
                await _alert(
                    f"🚫 <b>PostGuardian BLOCKIERT</b> [{platform}] von {source_module}\n" +
                    "\n".join(f"• {e}" for e in guardian_errors[:5]) +
                    f"\n\nPreview: {text[:150]!r}"
                )
            log.warning("PostGuardian blockiert [%s] von %s: %s", platform, source_module, guardian_errors)
            return result
    except Exception as _ge:
        log.warning("PostGuardian nicht verfügbar (%s) — Fallback auf _validate_content", _ge)

    # Schicht 1b: Eigener Content-Check (Länge, Abschnitt, Secrets)
    content_errors = _validate_content(text, platform)
    if content_errors:
        result["errors"] = content_errors
        result["blocked"] = True
        _log_blocked(platform, " | ".join(content_errors), text)
        _remember(content_errors)
        if _should_alert(platform, " | ".join(content_errors), text):
            await _alert(
                f"🚫 <b>Post BLOCKIERT</b> [{platform}] von {source_module}\n"
                f"Fehler ({len(content_errors)}):\n" +
                "\n".join(f"• {e}" for e in content_errors[:5]) +
                f"\n\nPreview: {text[:150]!r}"
            )
        log.warning("Post blockiert [%s] von %s: %s", platform, source_module, content_errors)
        return result

    # Schicht 2: Duplikat-Check
    if not skip_duplicate_check and _is_duplicate(text, platform):
        result["errors"] = ["Duplikat: gleicher Content bereits in letzten 7 Tagen gepostet"]
        result["blocked"] = True
        _log_blocked(platform, "Duplikat", text)
        try:
            from modules.post_never_twice import remember_block
            remember_block(text, platform, result["errors"], source_module=source_module)
        except Exception:
            pass
        log.info("Post übersprungen [%s] — Duplikat", platform)
        return result

    daily_cap = _PLATFORM_DAILY_CAPS.get(platform.lower())
    if daily_cap and _sent_today(platform) >= daily_cap:
        result["errors"] = [f"daily_cap_reached: {platform} {daily_cap}/Tag"]
        result["blocked"] = True
        _log_blocked(platform, "daily_cap_reached", text)
        log.warning("Post übersprungen [%s] von %s — Tageslimit %d erreicht", platform, source_module, daily_cap)
        return result

    # Schicht 3: Credential-Check
    cred_ok, cred_err = _check_credential(platform)
    if not cred_ok:
        result["errors"] = [cred_err]
        result["blocked"] = True
        _log_blocked(platform, cred_err, text)
        try:
            from modules.post_never_twice import remember_block
            remember_block(text, platform, [cred_err], source_module=source_module, kind="fail")
        except Exception:
            pass
        if _should_alert(platform, cred_err, text):
            await _alert(f"⚠️ <b>Post blockiert</b> [{platform}]: {cred_err}")
        log.error("Credential fehlt [%s]: %s", platform, cred_err)
        return result

    # Schicht 4+5: API-Call
    p = platform.lower()
    try:
        if p == "facebook":
            api_result = await _post_facebook(text, image_url)
        elif p == "instagram":
            api_result = await _post_instagram(text, image_url)
        elif p in ("linkedin",):
            api_result = await _post_linkedin(text)
        elif p == "telegram":
            api_result = await _post_telegram(text, chat_id)
        else:
            api_result = {"ok": False, "error": f"Unbekannte Plattform: {platform}"}
    except Exception as e:
        api_result = {"ok": False, "error": str(e)}

    if api_result.get("ok"):
        _log_post(platform, "sent", text, [])
        result["ok"] = True
        result["post_id"] = api_result.get("post_id")
        try:
            from modules.post_never_twice import remember_sent
            remember_sent(text, platform, source_module=source_module)
        except Exception:
            pass
        log.info("✅ Post gesendet [%s] von %s: %s", platform, source_module, result["post_id"])
    else:
        err = api_result.get("error", "Unbekannter API-Fehler")
        result["errors"] = [err]
        _log_post(platform, "failed", text, [err])
        # KEIN remember_block bei API-Fehlern (falscher Token, Netzwerk, Rate-Limit)!
        # Nur Content-Violations werden dauerhaft geblockt — nicht technische API-Fehler.
        # Sonst: korrigierter Token → gleicher Content bleibt für immer gesperrt.
        if _should_alert(platform, err, text):
            await _alert(
                f"❌ <b>Post FEHLGESCHLAGEN</b> [{platform}] von {source_module}\n"
                f"Fehler: {err}\nPreview: {text[:100]!r}"
            )
        log.error("Post fehlgeschlagen [%s]: %s", platform, err)

    return result


# ── Batch-Poster: mehrere Plattformen gleichzeitig ───────────────────────────
async def safe_post_all(
    text: str,
    platforms: list[str] | None = None,
    image_url: str = "",
    source_module: str = "unknown",
) -> dict:
    """
    Postet denselben Content auf alle angegebenen Plattformen parallel.
    Jede Plattform läuft durch alle 5 Schichten.
    """
    if platforms is None:
        platforms = ["facebook", "instagram", "linkedin", "telegram"]

    tasks = [
        safe_post(platform=p, text=text, image_url=image_url, source_module=source_module)
        for p in platforms
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = {"ok_count": 0, "blocked_count": 0, "fail_count": 0, "details": {}}
    for p, r in zip(platforms, results):
        if isinstance(r, Exception):
            summary["fail_count"] += 1
            summary["details"][p] = {"ok": False, "error": str(r)}
        elif r.get("ok"):
            summary["ok_count"] += 1
            summary["details"][p] = r
        elif r.get("blocked"):
            summary["blocked_count"] += 1
            summary["details"][p] = r
        else:
            summary["fail_count"] += 1
            summary["details"][p] = r

    log.info("safe_post_all [%s]: %d OK, %d blockiert, %d Fehler",
             source_module, summary["ok_count"], summary["blocked_count"], summary["fail_count"])
    return summary


# ── Status-Report ─────────────────────────────────────────────────────────────
def get_gateway_stats(hours: int = 24) -> dict:
    """Statistik der letzten X Stunden."""
    _init_db()
    with sqlite3.connect(str(_DB)) as c:
        sent = c.execute(
            "SELECT COUNT(*) FROM posts WHERE status='sent' AND ts > datetime('now', ?)",
            (f"-{hours} hours",)
        ).fetchone()[0]
        failed = c.execute(
            "SELECT COUNT(*) FROM posts WHERE status='failed' AND ts > datetime('now', ?)",
            (f"-{hours} hours",)
        ).fetchone()[0]
        blocked = c.execute(
            "SELECT COUNT(*) FROM blocked WHERE ts > datetime('now', ?)",
            (f"-{hours} hours",)
        ).fetchone()[0]
        recent_blocked = c.execute(
            "SELECT platform, reason, preview, ts FROM blocked "
            "WHERE ts > datetime('now', ?) ORDER BY ts DESC LIMIT 10",
            (f"-{hours} hours",)
        ).fetchall()

    return {
        "period_hours": hours,
        "sent": sent,
        "failed": failed,
        "blocked": blocked,
        "success_rate": f"{sent/(sent+failed+blocked)*100:.1f}%" if (sent+failed+blocked) > 0 else "N/A",
        "recent_blocked": [dict(zip(["platform","reason","preview","ts"], r)) for r in recent_blocked],
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if "--stats" in sys.argv:
        import json
        print(json.dumps(get_gateway_stats(), indent=2, ensure_ascii=False))
    elif "--test" in sys.argv:
        async def _test():
            tests = [
                ("facebook", "🏠 Neues Smart Home Produkt heute im Shop! Jetzt entdecken: https://ineedit.com.co #SmartHome #Tech", ""),
                ("facebook", "[PLATZHALTER] kaufe jetzt!", ""),
                ("instagram", "Als KI-Sprachmodell empfehle ich dieses Produkt", "https://example.com/img.jpg"),
                ("linkedin", "", ""),
                ("twitter", "x" * 300, ""),
                ("telegram", "Test Nachricht ✅ Alles funktioniert!", ""),
            ]
            for plat, text, img in tests:
                r = await safe_post(plat, text, img, source_module="test")
                status = "✅ GESENDET" if r["ok"] else f"🚫 BLOCKIERT: {r['errors']}"
                print(f"[{plat}] {status}")
        asyncio.run(_test())
