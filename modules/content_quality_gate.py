"""
Content Quality Gate — blockiert schlechten Content BEVOR er gepostet wird.

Layer 1 (synchron):  Regel-basierte Checks (Phrasen, Hashtags, Nische, Länge)
Layer 2 (async):     KI-Score via ai_complete (1-10), blockiert bei Score <= 4

Eingebaut in mega_auto_poster.py, social_autoposter.py und alle anderen Poster-Module.
Gibt (True, "OK") zurück wenn Content passt, (False, Grund) wenn nicht.
"""
from __future__ import annotations

import re
import json
import logging
from typing import Tuple

log = logging.getLogger("ContentGate")

# ── Verbotene Phrasen (Spam / falsche Nische) ─────────────────────────────────
_BLOCKED_PHRASES = [
    # Passives Einkommen Spam
    "passives einkommen", "passive einkommen", "passivem einkommen",
    "passiven einkommen", "passiv verdienen", "passiv geld",
    "ki verdient für dich", "ki macht alles", "nie wieder aktiv",
    "während du schläfst verdient", "vollautomatisches einkommens",
    "stop working hard", "start working smart",
    "bereits hunderte zufriedene kunden",
    "finanzielle freiheit",
    # Generic Affiliate-Spam
    "online geld verdienen", "onlinegeld", "onlinegeldverdienen",
    "passiveseinkommen",
    # Falsche Nische / Marke
    "bullpower", "bullpowerhub", "bull power hub",
    "supermegabot", "super mega bot",
    "autoincome", "auto-income",
    # Generischer KI-Hype ohne Produkt-Bezug
    "ki automatisierung zu passivem",
    "ki-gestütztes passives",
    "vollautomatisches business-system",
]

# ── Verbotene Hashtags ─────────────────────────────────────────────────────────
_BLOCKED_HASHTAGS = {
    "passiveseinkommen", "passiveincome", "onlinegeldverdienen",
    "passivgeld", "passiverdienen", "affiliatemarketing",
    "mlm", "dropshipping_hype", "geheimtipp", "schnellgeld",
    "reich_werden", "geldverdienen", "bullpower", "supermegabot",
}

# ── Pflicht-Keywords für Smart-Home-Shop (mindestens 1 davon) ─────────────────
_NICHE_KEYWORDS = [
    "smart", "home", "solar", "gadget", "tech", "elektronik",
    "wlan", "wifi", "bluetooth", "led", "sicherheit", "kamera",
    "thermostat", "rasenmäher", "roboter", "akku", "strom",
    "energie", "licht", "automatisch", "sensor", "display",
    "tablet", "drohne", "outdoor", "camping", "powerstation",
    "balkonkraftwerk", "ineedit", "aiitec",
    # E-Com / SaaS / B2B / LinkedIn Authority
    "shopify", "e-commerce", "ecommerce", "automation", "automatisierung",
    "saas", "ki", "ai", "software", "stripe", "digistore", "affiliate",
    "b2b", "compliance", "outreach", "lead", "chatbot", "marketing",
    # Preis-Angaben sind ok (zeigen Produkt-Kontext)
    "€", "eur", "preis",
]

# Mindest-Content-Länge
MIN_POST_LENGTH   = 30
MIN_EMAIL_LENGTH  = 80

# Maximale Wiederholung desselben Satzes
MAX_REPEAT_RATIO  = 0.6


def validate_post(
    text: str,
    product_name: str = "",
    platform: str = "social",  # "social" | "email" | "blog"
) -> Tuple[bool, str]:
    """
    Prüft ob ein Post-Text gepostet werden darf.
    Returns: (ok, reason)
    """
    if not text or not text.strip():
        return False, "Leerer Content"

    low = text.lower()

    # Länge prüfen
    min_len = MIN_EMAIL_LENGTH if platform == "email" else MIN_POST_LENGTH
    if len(text.strip()) < min_len:
        return False, f"Text zu kurz ({len(text)} Zeichen, min {min_len})"

    # Verbotene Phrasen
    for phrase in _BLOCKED_PHRASES:
        if phrase in low:
            return False, f"Spam-Phrase erkannt: '{phrase}'"

    # Nischen-Check (mindestens 1 Keyword für Smart-Home)
    if platform != "email":
        has_niche = any(kw in low for kw in _NICHE_KEYWORDS)
        if not has_niche and len(text) > 50:
            return False, "Kein Smart-Home/Tech-Bezug erkennbar"

    # Wiederholung prüfen (duplizierter Text)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 15]
    if len(sentences) > 3:
        unique_ratio = len(set(sentences)) / len(sentences)
        if unique_ratio < MAX_REPEAT_RATIO:
            return False, f"Zu viel wiederholter Text (nur {unique_ratio:.0%} unique)"

    return True, "OK"


def validate_hashtags(hashtags: list[str]) -> Tuple[list[str], list[str]]:
    """
    Filtert verbotene Hashtags raus.
    Returns: (approved, blocked)
    """
    approved = []
    blocked  = []
    for tag in hashtags:
        clean = tag.strip("#").lower().replace(" ", "")
        if clean in _BLOCKED_HASHTAGS:
            blocked.append(tag)
        else:
            approved.append(tag)
    return approved, blocked


def sanitize_content(content: dict, product_name: str = "") -> Tuple[dict, list[str]]:
    """
    Bereinigt Content-Dict: validiert body, filtert Hashtags.
    Returns: (bereinigter content, liste der Probleme)
    """
    problems = []

    # Body validieren
    body = content.get("body", "")
    ok, reason = validate_post(body, product_name, platform="social")
    if not ok:
        problems.append(f"body: {reason}")
        log.warning("ContentGate BLOCKIERT body: %s — %s", body[:60], reason)

    # Email-Body validieren
    email_body = content.get("email_body", "")
    if email_body:
        ok2, reason2 = validate_post(email_body, product_name, platform="email")
        if not ok2:
            problems.append(f"email_body: {reason2}")
            log.warning("ContentGate BLOCKIERT email_body: %s", reason2)

    # Hashtags filtern
    hashtags = content.get("hashtags", [])
    if hashtags:
        approved, blocked = validate_hashtags(hashtags)
        if blocked:
            problems.append(f"Hashtags entfernt: {blocked}")
            log.info("ContentGate: Hashtags entfernt: %s", blocked)
        content = {**content, "hashtags": approved}

    return content, problems


def is_content_valid(content: dict, product_name: str = "") -> bool:
    """
    Schnell-Check: Darf dieser Content gepostet werden?
    Gibt False zurück wenn kritische Probleme gefunden.
    """
    _, problems = sanitize_content(content, product_name)
    critical = [p for p in problems if p.startswith("body:")]
    return len(critical) == 0


# ── KI-Score Schwellwerte ─────────────────────────────────────────────────────
AI_SCORE_BLOCK  = 4   # <= 4 → automatisch blockieren
AI_SCORE_WARN   = 6   # 5-6 → Warnung im Log, trotzdem posten
AI_SCORE_GOOD   = 7   # >= 7 → grünes Licht

# KI-Prompt für Content-Qualitäts-Scoring
_AI_QUALITY_PROMPT = """\
Du bist ein strenger Content-Qualitäts-Filter für einen Smart-Home & Technik Online-Shop.

Bewerte den folgenden {platform}-Content auf einer Skala 1-10:

Kriterien:
- 9-10: Exzellent. Seriös, informativ, klar nischen-relevant (Smart Home / Technik), \
keine falschen Behauptungen, hoher Mehrwert.
- 7-8:  Gut. Passt zur Nische, klare Botschaft, kein Spam, keine Lücken.
- 5-6:  Grenzwertig. Zu generisch, leicht schwach, oder nur bedingt nischen-relevant.
- 3-4:  Schlecht. Fake-Claims, irreführend, nischen-fremd, oder Spam-artig.
- 1-2:  SOFORT BLOCKIEREN. MLM-Sprache, Fake-Einkommensversprechen, komplett falscher Kontext.

Produkt-Kontext: {product_name}

Text zu bewerten:
---
{text}
---

Antworte NUR mit JSON (kein Text davor/danach):
{{"score": <Zahl 1-10>, "reason": "<max 100 Zeichen auf Deutsch>"}}"""


async def ai_quality_score(
    text: str,
    platform: str = "social",
    product_name: str = "",
) -> Tuple[int, str]:
    """
    KI-basiertes Qualitäts-Scoring über ai_complete.

    Returns: (score 1-10, begründung)
    Fallback bei Fehler: (6, "KI-Check fehlgeschlagen")
    """
    from modules.ai_client import ai_complete

    if not text or len(text.strip()) < 10:
        return 3, "Text zu kurz für KI-Bewertung"

    prompt = _AI_QUALITY_PROMPT.format(
        platform=platform,
        product_name=product_name or "unbekannt",
        text=text[:1200],
    )
    try:
        raw = await ai_complete(prompt, system="", model_hint="fast", max_tokens=80)
        # JSON aus der Antwort extrahieren — auch wenn Modell Präfix schreibt
        raw = raw.strip()
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if match:
            raw = match.group(0)
        parsed = json.loads(raw)
        score  = int(parsed.get("score", 6))
        reason = str(parsed.get("reason", "KI-Bewertung"))
        score  = max(1, min(10, score))
        return score, reason
    except json.JSONDecodeError as e:
        log.debug("ai_quality_score JSON-Fehler: %s | raw=%s", e, raw[:120])
        return 6, "KI-Check fehlgeschlagen (JSON)"
    except Exception as e:
        log.debug("ai_quality_score Fehler: %s", e)
        return 6, "KI-Check fehlgeschlagen"


async def validate_post_ai(
    text: str,
    product_name: str = "",
    platform: str = "social",
) -> Tuple[bool, str]:
    """
    Vollständige Qualitätsprüfung: erst Regel-Check, dann KI-Score.

    Returns: (ok, reason)
    - ok=False wenn Regelverstoß oder KI-Score <= AI_SCORE_BLOCK
    - Warnung bei Score 5-6, aber ok=True
    """
    # Layer 1: Regel-Check (synchron, schnell)
    ok, reason = validate_post(text, product_name, platform)
    if not ok:
        return False, reason

    # Layer 2: KI-Score (async)
    score, ai_reason = await ai_quality_score(text, platform, product_name)

    if score <= AI_SCORE_BLOCK:
        log.warning(
            "ContentGate KI-BLOCK (Score %d/10): %s | %s",
            score, ai_reason, text[:80],
        )
        return False, f"KI-Score {score}/10: {ai_reason}"

    if score <= AI_SCORE_WARN:
        log.warning(
            "ContentGate KI-WARNUNG (Score %d/10): %s | %s",
            score, ai_reason, text[:80],
        )
    else:
        log.info("ContentGate KI-OK (Score %d/10): %s", score, text[:60])

    return True, "OK"


async def sanitize_content_ai(
    content: dict,
    product_name: str = "",
    platform: str = "social",
) -> Tuple[dict, list[str]]:
    """
    Async-Version von sanitize_content mit zusätzlichem KI-Score.

    Führt aus:
    1. Regel-basiertes sanitize_content (Phrasen, Hashtags)
    2. KI-Score auf dem body-Text

    Returns: (bereinigter content, liste der Probleme)
    """
    # Layer 1: Regel-Check + Hashtag-Bereinigung
    content, problems = sanitize_content(content, product_name)

    # Layer 2: KI-Score auf body, aber nur wenn Layer 1 body akzeptiert hat
    body = content.get("body", "")
    body_blocked = any(p.startswith("body:") for p in problems)

    if body and not body_blocked:
        score, ai_reason = await ai_quality_score(body, platform, product_name)

        if score <= AI_SCORE_BLOCK:
            problems.append(f"body (KI-Score {score}/10): {ai_reason}")
            log.warning(
                "ContentGate KI-BLOCK body (Score %d/10): %s | %s",
                score, ai_reason, body[:80],
            )
        elif score <= AI_SCORE_WARN:
            log.warning(
                "ContentGate KI-WARNUNG body (Score %d/10): %s",
                score, ai_reason,
            )

    return content, problems


async def is_content_valid_ai(content: dict, product_name: str = "") -> bool:
    """
    Async Schnell-Check mit KI-Score.
    Gibt False zurück wenn kritische Probleme gefunden (Regel oder KI-Score <= 4).
    """
    _, problems = await sanitize_content_ai(content, product_name)
    critical = [p for p in problems if p.startswith("body")]
    return len(critical) == 0
