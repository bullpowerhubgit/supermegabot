"""
Post Auto-Repair Engine — Kein fehlerhafter Post darf je gesendet werden.

Wird von safe_post() VOR allen anderen Checks aufgerufen.
Repariert automatisch was reparierbar ist.
Liquidiert (None) was nicht reparierbar ist — Caller muss blocken.

Repariert:
  - Blacklisted DS24-Produkt-IDs → ersetzt mit gültigem Guardian-Link
  - Verbotene Einkommens-Phrasen → ersetzt mit genehmigter Formulierung
  - Ungefüllte {placeholder} / [PLACEHOLDER] → liquidiert
  - Python None im Text → liquidiert
  - Prompts-Leaks (Instruktionstext) → liquidiert
  - KI-Offenbarungs-Phrasen → liquidiert
  - Zu lang > 4096 → kürzt auf 4000 an Wortgrenze
  - Doppelte Sätze → dedupliziert
  - Localhost/Admin-Links → liquidiert
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("PostAutoRepair")

# ── DS24 Blacklist ────────────────────────────────────────────────────────────
_DS24_BLACKLISTED_IDS = {"704330", "668035", "669750", "704677"}

_DS24_PRODUCT_RE = re.compile(
    r'https?://[^\s]*checkout-ds24\.com/product/(\d+)[^\s]*',
    re.IGNORECASE,
)

# ── Verbotene Phrasen → Ersatz ────────────────────────────────────────────────
_PHRASE_REPAIRS = [
    # Passiv-Einkommen Varianten
    (re.compile(r'passives?\s+einkommen[^\n.!?]*', re.IGNORECASE),
     "automatisierte Business-Prozesse mit Shopify + DS24"),
    (re.compile(r'geld\s+verdienen\s+vollautomatisch[^\n.!?]*', re.IGNORECASE),
     "vollautomatischer E-Commerce mit KI-Unterstützung"),
    (re.compile(r'online\s+geld\s+verdienen[^\n.!?]*', re.IGNORECASE),
     "E-Commerce-Umsatz mit Shopify automatisieren"),
    (re.compile(r'earn\s+while\s+you\s+sleep[^\n.!?]*', re.IGNORECASE),
     "automatisierter Shopify-Shop rund um die Uhr aktiv"),
    # Tagesverdienst-Claims
    (re.compile(r'täglich\s+[€$]?\d+[€$]?[^\n.!?]*verdien[^\n.!?]*', re.IGNORECASE),
     "steigender Umsatz durch E-Commerce-Automatisierung"),
    (re.compile(r'\d+\s*[€$]\s*pro\s*tag[^\n.!?]*', re.IGNORECASE),
     "messbarer Umsatz mit automatisierten Workflows"),
    # Gratis-Spam
    (re.compile(r'heute\s+gratis[^\n.!?]*', re.IGNORECASE),
     "Jetzt starten"),
    (re.compile(r'gratis\s+heute[^\n.!?]*', re.IGNORECASE),
     "Jetzt entdecken"),
]

# ── Unfüllbare Platzhalter → Liquidation ─────────────────────────────────────
_PLACEHOLDER_RE = re.compile(
    r'\{[a-z_]{2,40}\}|'                          # {variable_name}
    r'\[PLACEHOLDER[^\]]*\]|'                      # [PLACEHOLDER]
    r'\[DEIN[^\]]{0,30}\]|'                        # [DEIN NAME]
    r'\[YOUR[^\]]{0,30}\]|'                        # [YOUR LINK]
    r'<LINK>|<URL>|<PRODUKT>|<PRODUCT>|'           # XML-Tags als Platzhalter
    r'INSERT_[A-Z_]+|YOUR_[A-Z_]+',                # Technik-Platzhalter
    re.IGNORECASE,
)

# ── Prompt-Leaks → Liquidation ────────────────────────────────────────────────
_PROMPT_LEAK_RE = re.compile(
    r'(\*\s*(topic|product|format|style|link|constraints?)\s*:)|'
    r'(translate only descriptive)|'
    r'(keep brand names)|'
    r'(tone:\s*modern)|'
    r'(max\.?\s*2\s*sentences)|'
    r'(system prompt|user prompt|assistant:)',
    re.IGNORECASE,
)

# ── KI-Offenbarungen → Liquidation ───────────────────────────────────────────
_AI_DISCLOSURE_RE = re.compile(
    r'als\s+ki[-\s]sprachmodell|'
    r'as\s+an\s+ai|'
    r'ich\s+bin\s+eine?\s+ki|'
    r'i\s+(cannot|can\'t)\s+(post|send|create)|'
    r'leider\s+kann\s+ich|'
    r'unfortunately\s+i|'
    r'entschuldigung,\s+ich\s+kann',
    re.IGNORECASE,
)

# ── Localhost / Admin Links → Liquidation ─────────────────────────────────────
_LOCALHOST_RE = re.compile(
    r'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?|'
    r'myshopify\.com/admin',
    re.IGNORECASE,
)

# ── Python None im Post ───────────────────────────────────────────────────────
_NONE_RE = re.compile(
    r'Hallo\s+None|—\s*None\b|für\s+None\b|NoneType|:\s*None\b',
)

# ── Doppelte Sätze ────────────────────────────────────────────────────────────
def _dedup_sentences(text: str) -> str:
    parts = re.split(r'(?<=[.!?\n])\s+', text)
    seen: set[str] = set()
    out = []
    for part in parts:
        key = part.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(part)
    return " ".join(out)


def _get_valid_ds24_link() -> str:
    try:
        from modules.ds24_link_guardian import get_ds24_link
        return get_ds24_link("repair")
    except Exception:
        return ""


def repair(text: str, platform: str = "telegram") -> Optional[str]:
    """
    Versucht den Post-Text zu reparieren.

    Returns:
        str  — reparierter Text (kann gleich wie Input sein wenn kein Fehler)
        None — nicht reparierbar → Post muss liquidiert/blockiert werden
    """
    if not text or not text.strip():
        return None

    original = text
    t = text

    # 1. Localhost/Admin-Links → sofort liquidieren (kein Ersatz möglich)
    if _LOCALHOST_RE.search(t):
        log.warning("[AutoRepair] LIQUIDIERT: Localhost/Admin-Link gefunden — '%s'", t[:80])
        return None

    # 2. Python None → liquidieren
    if _NONE_RE.search(t):
        log.warning("[AutoRepair] LIQUIDIERT: None-Placeholder im Text — '%s'", t[:80])
        return None

    # 3. KI-Offenbarungen → liquidieren
    if _AI_DISCLOSURE_RE.search(t):
        log.warning("[AutoRepair] LIQUIDIERT: KI-Offenbarung im Text — '%s'", t[:80])
        return None

    # 4. Prompt-Leaks → liquidieren
    if _PROMPT_LEAK_RE.search(t):
        log.warning("[AutoRepair] LIQUIDIERT: Prompt-Leak im Text — '%s'", t[:80])
        return None

    # 5. Ungefüllte Platzhalter → liquidieren
    m = _PLACEHOLDER_RE.search(t)
    if m:
        log.warning("[AutoRepair] LIQUIDIERT: Ungefüllter Platzhalter '%s' — '%s'", m.group(), t[:80])
        return None

    # 6. Blacklisted DS24-Produkt-IDs → reparieren mit gültigem Link
    def _fix_ds24_url(match: re.Match) -> str:
        product_id = match.group(1)
        if product_id in _DS24_BLACKLISTED_IDS:
            valid_link = _get_valid_ds24_link()
            if valid_link:
                log.warning("[AutoRepair] REPARIERT: DS24 %s → %s", product_id, valid_link)
                return valid_link
            else:
                log.error("[AutoRepair] LIQUIDIERT: DS24 %s blacklisted aber kein Ersatz-Link", product_id)
                return ""
        return match.group(0)

    t_new = _DS24_PRODUCT_RE.sub(_fix_ds24_url, t)
    if t_new != t:
        t = t_new
        if not t.strip():
            return None

    # 7. Verbotene Phrasen → genehmigte Formulierungen ersetzen
    for pattern, replacement in _PHRASE_REPAIRS:
        if pattern.search(t):
            t = pattern.sub(replacement, t)
            log.info("[AutoRepair] REPARIERT: Phrase ersetzt durch '%s'", replacement)

    # 8. Doppelte Sätze entfernen
    t_dedup = _dedup_sentences(t)
    if t_dedup != t:
        log.info("[AutoRepair] REPARIERT: Doppelte Sätze entfernt")
        t = t_dedup

    # 9. Zu lang → kürzen an Wortgrenze
    if len(t) > 4000:
        cutoff = t[:4000].rfind(" ")
        t = t[:cutoff if cutoff > 3800 else 4000] + "…"
        log.info("[AutoRepair] REPARIERT: Post auf 4000 Zeichen gekürzt")

    # 10. Ergebnis-Validierung: Mindestlänge
    if len(t.strip()) < 10:
        log.warning("[AutoRepair] LIQUIDIERT: Nach Reparatur zu kurz — '%s'", t[:40])
        return None

    if t != original:
        log.info("[AutoRepair] Post repariert (%d→%d Zeichen)", len(original), len(t))

    return t


def repair_or_block(text: str, platform: str = "telegram") -> tuple[Optional[str], list[str]]:
    """
    Repariert den Post oder gibt (None, [grund]) zurück.
    Direkt verwendbar in safe_post().
    """
    result = repair(text, platform)
    if result is None:
        return None, ["auto_repair_failed: Post liquidiert — nicht reparierbar"]
    return result, []
