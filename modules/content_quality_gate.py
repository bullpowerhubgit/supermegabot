"""
Content Quality Gate — blockiert schlechten Content BEVOR er gepostet wird.

Eingebaut in mega_auto_poster.py, social_autoposter.py und alle anderen Poster-Module.
Gibt (True, "OK") zurück wenn Content passt, (False, Grund) wenn nicht.
"""
from __future__ import annotations

import re
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
