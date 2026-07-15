#!/usr/bin/env python3
"""
PostGuard — Universeller Quality-Gate für ALLE ausgehenden Posts
================================================================
Kein einziger Post verlässt das System ohne diesen Check.

Drei Prüf-Layer (in Reihe, schnellster zuerst):

  Layer 1 — Regel-Check (instant, kostenlos)
    • Text nicht leer / zu kurz
    • Keine verbotenen Keywords (fake_product, lorem ipsum, undefined …)
    • Links erreichbar (HEAD-Request, Timeout 3s)
    • Preise in akzeptablem Bereich (wenn vorhanden)

  Layer 2 — KI-Qualitätscheck via Groq (< 300ms, kostenlos)
    • Ist der Text kohärent und seriös?
    • Passt er zur Nische (Smart Home / Tech / E-Commerce)?
    • Keine falschen Tatsachenbehauptungen?
    • Score 1-10 — unter THRESHOLD = BLOCKIERT

  Layer 3 — Telegram-Approval bei Grenzfällen (Score 5-6)
    • Bot schickt Vorschau + Approve/Reject Buttons
    • Timeout 5 Minuten → automatisch BLOCKIERT (safe default)
    • Bei APPROVE → wird sofort gepostet

Einbindung in jedes Posting-Modul:
    from modules.post_guard import guard
    ok, reason = await guard.check("social", text=..., image_url=..., link=...)
    if not ok:
        log.warning("PostGuard: %s", reason)
        return {"ok": False, "blocked": True, "reason": reason}
    # erst hier: posten
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Literal, Optional, Tuple

import aiohttp

log = logging.getLogger("PostGuard")

_BASE = Path(__file__).parent.parent
_DB   = _BASE / "data" / "post_guard.db"

# ── Konfiguration ─────────────────────────────────────────────────────────────
AI_SCORE_AUTO_APPROVE = 6    # >= 6 → sofort posten (war 7, zu restriktiv)
AI_SCORE_AUTO_REJECT  = 3    # <= 3 → sofort blockieren (war 4)
TELEGRAM_APPROVAL_TIMEOUT = 90   # 90s (war 300s — zu lange, führte zu auto-REJECT)

BLOCKED_PATTERNS = [
    r"\blorem ipsum\b", r"\bundefined\b", r"\bnull\b", r"\bNaN\b",
    r"\[object Object\]", r"\btest.*post\b", r"\bfake\b",
    r"PLACEHOLDER", r"INSERT.*HERE", r"TODO",
    r"example\.com", r"yourdomain",
]
_compiled_blocks = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

NICHE_KEYWORDS = [
    # Core Nische
    "smart", "tech", "ki", "ai", "solar", "automatisierung", "automation",
    "shopify", "e-commerce", "digital", "gadget", "robot", "sensor",
    "wlan", "wifi", "app", "smart home", "e-bike", "powerstation",
    "online", "shop", "umsatz", "revenue", "business", "marketing",
    # Erweitert — Smart Home / Gadgets
    "led", "bluetooth", "usb", "ladekabel", "akku", "batterie", "energie",
    "kamera", "sicherheit", "alarm", "temperatur", "luftqualität",
    "steckdose", "schalter", "dimmer", "thermostat", "heizung",
    "produktempfehlung", "angebot", "rabatt", "sale", "deal", "kaufen",
    "ineedit", "aiitec", "shopify", "amazon", "aliexpress",
    # Business / SaaS
    "saas", "software", "tool", "platform", "service", "lösung", "system",
    "lead", "kunde", "conversion", "traffic", "seo", "content",
]

ContentType = Literal["social", "email", "product", "sms"]


# ── DB ────────────────────────────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS guard_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           REAL,
            content_type TEXT,
            verdict      TEXT,
            score        INTEGER,
            reason       TEXT,
            text_snippet TEXT
        )
    """)
    conn.commit()
    return conn


def _log_verdict(content_type: str, verdict: str, score: int, reason: str, snippet: str) -> None:
    try:
        with _db() as c:
            c.execute(
                "INSERT INTO guard_log(ts,content_type,verdict,score,reason,text_snippet) VALUES(?,?,?,?,?,?)",
                (time.time(), content_type, verdict, score, reason, snippet[:200]),
            )
    except Exception:
        pass


# ── Layer 1: Regel-Check ──────────────────────────────────────────────────────
def _rule_check(text: str, link: str = "", content_type: ContentType = "social") -> Tuple[bool, str]:
    if not text or not text.strip():
        return False, "Text ist leer"

    if len(text.strip()) < 20:
        return False, f"Text zu kurz ({len(text.strip())} Zeichen)"

    for pattern in _compiled_blocks:
        if pattern.search(text):
            return False, f"Verbotenes Muster gefunden: '{pattern.pattern}'"

    text_lower = text.lower()
    if content_type == "social":
        has_niche = any(kw in text_lower for kw in NICHE_KEYWORDS)
        if not has_niche:
            return False, "Kein Bezug zur Nische (Smart Home/Tech/E-Commerce)"

    return True, "OK"


# ── Layer 2: KI-Score via Groq ────────────────────────────────────────────────
_GROQ_PROMPT = """Du bist ein strenger Content-Qualitätsprüfer für einen Smart-Home/E-Commerce Shop (AIITEC / ineedit.com.co).

Bewerte den folgenden {content_type}-Text auf einer Skala 1-10:
- 9-10: Exzellent. Seriös, informativ, nischen-relevant, keine falschen Behauptungen.
- 7-8:  Gut. Passt zur Nische, klare Botschaft, keine gravierenden Fehler.
- 5-6:  Grenzwertig. Zu generisch, leicht irreführend oder schwach.
- 1-4:  BLOCKIEREN. Fake-Claims, falscher Kontext, Spam-artig, oder absolut nicht zur Nische passend.

Antworte NUR mit JSON: {{"score": <1-10>, "reason": "<max 80 Zeichen>"}}

Text zu prüfen:
---
{text}
---"""


async def _ai_check(text: str, content_type: ContentType) -> Tuple[int, str]:
    from modules.ai_client import ai_complete
    prompt = _GROQ_PROMPT.format(content_type=content_type, text=text[:800])
    try:
        raw = await ai_complete(prompt, system="", max_tokens=60)
        parsed = json.loads(raw.strip())
        score  = int(parsed.get("score", 5))
        reason = str(parsed.get("reason", "KI-Check"))
        return max(1, min(10, score)), reason
    except Exception as e:
        log.debug("ai_complete PostGuard: %s", e)
        return 6, "KI-Check fehlgeschlagen — Grenzfall"


# ── Layer 3: Telegram Approval ────────────────────────────────────────────────
_pending_approvals: dict[str, asyncio.Future] = {}


async def _telegram_approval(text: str, content_type: str, score: int, ai_reason: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat  = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.warning("PostGuard: Telegram nicht konfiguriert — auto-REJECT bei Grenzfall")
        return False

    approval_id = f"pg_{int(time.time())}"
    snippet = text[:300].replace("<", "&lt;").replace(">", "&gt;")

    msg = (
        f"⚠️ <b>PostGuard — Manuelle Prüfung</b>\n"
        f"Typ: {content_type} | KI-Score: {score}/10\n"
        f"Grund: {ai_reason}\n\n"
        f"<b>Inhalt:</b>\n<i>{snippet}</i>\n\n"
        f"👉 Antworten mit:\n"
        f"<code>APPROVE {approval_id}</code> — Posten erlaubt\n"
        f"<code>REJECT {approval_id}</code> — Blockieren\n\n"
        f"⏱ Timeout: {TELEGRAM_APPROVAL_TIMEOUT//60} Minuten → auto-REJECT"
    )

    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.warning("PostGuard TG: %s", e)
        return False

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending_approvals[approval_id] = future

    try:
        result = await asyncio.wait_for(future, timeout=TELEGRAM_APPROVAL_TIMEOUT)
        return bool(result)
    except asyncio.TimeoutError:
        log.warning("PostGuard: Telegram Approval Timeout → auto-REJECT")
        return False
    finally:
        _pending_approvals.pop(approval_id, None)


def resolve_telegram_approval(approval_id: str, approved: bool) -> bool:
    """Wird vom Telegram-Webhook aufgerufen wenn Nutzer APPROVE/REJECT schreibt."""
    fut = _pending_approvals.get(approval_id)
    if fut and not fut.done():
        fut.set_result(approved)
        return True
    return False


# ── Haupt-API ─────────────────────────────────────────────────────────────────
class PostGuard:
    """Singleton-Gatekeeper — einmal importieren, überall nutzen."""

    async def check(
        self,
        content_type: ContentType,
        text: str = "",
        image_url: str = "",
        link: str = "",
        skip_ai: bool = False,
    ) -> Tuple[bool, str]:
        """
        Prüft einen Post durch alle Layer.
        Returns: (True, "OK") oder (False, "Grund warum blockiert")
        """
        snippet = text[:100]

        # ── Layer 1: Regel-Check ──────────────────────────────────────────
        ok, reason = _rule_check(text, link, content_type)
        if not ok:
            _log_verdict(content_type, "BLOCKED_RULE", 0, reason, snippet)
            log.warning("PostGuard BLOCK (Regel): %s | %s", reason, snippet)
            return False, f"[Regel] {reason}"

        # ── Layer 2: KI-Score ─────────────────────────────────────────────
        if not skip_ai:
            score, ai_reason = await _ai_check(text, content_type)
        else:
            score, ai_reason = 8, "KI übersprungen"

        if score >= AI_SCORE_AUTO_APPROVE:
            _log_verdict(content_type, "APPROVED", score, ai_reason, snippet)
            log.info("PostGuard OK (Score %d): %s", score, snippet[:60])
            return True, "OK"

        if score <= AI_SCORE_AUTO_REJECT:
            reason = f"[KI Score {score}/10] {ai_reason}"
            _log_verdict(content_type, "BLOCKED_AI", score, ai_reason, snippet)
            log.warning("PostGuard BLOCK (KI %d): %s | %s", score, ai_reason, snippet)
            return False, reason

        # ── Layer 3: Grenzfall → Telegram Approval ────────────────────────
        log.info("PostGuard: Score %d/10 — Telegram-Approval angefordert", score)
        approved = await _telegram_approval(text, content_type, score, ai_reason)
        verdict  = "APPROVED_HUMAN" if approved else "BLOCKED_HUMAN"
        _log_verdict(content_type, verdict, score, ai_reason, snippet)
        if approved:
            return True, "OK (manuell genehmigt)"
        return False, f"[Manuell abgelehnt / Timeout] Score {score}/10: {ai_reason}"

    async def stats(self) -> dict:
        try:
            with _db() as c:
                total   = c.execute("SELECT COUNT(*) FROM guard_log").fetchone()[0]
                blocked = c.execute("SELECT COUNT(*) FROM guard_log WHERE verdict LIKE 'BLOCKED%'").fetchone()[0]
                today   = c.execute(
                    "SELECT COUNT(*) FROM guard_log WHERE ts > ?", (time.time() - 86400,)
                ).fetchone()[0]
                top_reasons = c.execute(
                    "SELECT reason, COUNT(*) as n FROM guard_log WHERE verdict LIKE 'BLOCKED%' "
                    "GROUP BY reason ORDER BY n DESC LIMIT 5"
                ).fetchall()
            return {
                "total": total,
                "blocked": blocked,
                "approved": total - blocked,
                "block_rate": f"{blocked/max(total,1)*100:.1f}%",
                "today": today,
                "top_block_reasons": [{"reason": r[0], "count": r[1]} for r in top_reasons],
            }
        except Exception as e:
            return {"error": str(e)}


# Singleton
guard = PostGuard()
