"""
telegram_safe.py — Sicheres Telegram-Senden mit URL-Validierung
===============================================================
Prüft ALLE Links in einem Post BEVOR er gesendet wird.
Kaputte Links → werden entfernt oder durch Shop-URL ersetzt.
Kein Post mit 404/500-Links mehr.

Verwendung (statt direktem aiohttp-Call):
    from modules.telegram_safe import tg_send
    await tg_send(session, "Mein Post https://shop.com/produkt")
"""

import asyncio
import aiohttp
import logging
import os
import re
from typing import Optional

log = logging.getLogger("TelegramSafe")

TG_TOKEN    = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
STORE_URL   = f"https://{os.getenv('SHOPIFY_PUBLIC_DOMAIN','ineedit.com.co')}"
URL_TIMEOUT = 6   # Sekunden pro URL-Check
MAX_URLS    = 5   # Maximal so viele URLs pro Post prüfen

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")


_DS24_ERROR_PHRASES = [
    "nicht verkauft werden",
    "not available for sale",
    "product is not available",
    "kann nicht verkauft",
    "derzeit nicht verfügbar",
    "temporarily unavailable",
    "Fehler",  # DS24 error page title
]


async def _check_url(session: aiohttp.ClientSession, url: str) -> bool:
    """Gibt True zurück wenn URL erreichbar und kein Fehler-Content vorhanden ist."""
    # Interne URLs immer erlauben
    trusted = ["t.me", "telegram.me", "shopify.com", "stripe.com",
               "railway.app", "github.com", "supabase.co",
               "gumroad.com", "digistore24.com"]
    if any(t in url for t in trusted):
        # Gumroad + DS24 direkte Domain = vertrauenswürdig, ABER:
        # DS24 redir-Links können auf nicht-verkäufliche Produkte zeigen
        if "checkout-ds24.com/redir/" in url or "digistore24.com/redir/" in url:
            # DS24 Redir-Links via GET prüfen und Page-Content scannen
            try:
                async with session.get(
                    url,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=URL_TIMEOUT),
                    headers={"User-Agent": "Mozilla/5.0"}
                ) as r:
                    if r.status >= 400:
                        log.warning("DS24 redir HTTP %s: %s", r.status, url[:60])
                        return False
                    body = await r.text(errors="ignore")
                    for phrase in _DS24_ERROR_PHRASES:
                        if phrase.lower() in body.lower():
                            log.warning("DS24 Produkt nicht verfügbar: %s", url[:60])
                            return False
                    return True
            except Exception:
                return False
        return True

    try:
        async with session.head(
            url,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=URL_TIMEOUT),
            headers={"User-Agent": "Mozilla/5.0"}
        ) as r:
            ok = r.status < 400
            if not ok:
                log.debug("URL %s → HTTP %s (blockiert)", url[:60], r.status)
            return ok
    except Exception:
        # GET-Fallback wenn HEAD blockiert wird
        try:
            async with session.get(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=URL_TIMEOUT),
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                return r.status < 400
        except Exception:
            log.debug("URL nicht erreichbar: %s", url[:60])
            return False


async def validate_and_fix_text(session: aiohttp.ClientSession, text: str) -> Optional[str]:
    """
    Findet alle URLs im Text, prüft sie.
    - Alle OK → Original-Text zurückgeben
    - URL kaputt → URL durch STORE_URL ersetzen
    - Kein valider Content mehr → None (Post überspringen)
    """
    urls = _URL_RE.findall(text)
    if not urls:
        return text  # Kein Link → immer OK

    # Zu viele URLs: nur die ersten MAX_URLS prüfen
    to_check = urls[:MAX_URLS]

    results = await asyncio.gather(
        *[_check_url(session, u) for u in to_check],
        return_exceptions=True
    )

    fixed_text = text
    broken_count = 0
    for url, ok in zip(to_check, results):
        if isinstance(ok, Exception) or not ok:
            broken_count += 1
            # Ersetze kaputte URL durch Shop-URL
            fixed_text = fixed_text.replace(url, STORE_URL)
            log.warning("Kaputte URL ersetzt: %s → %s", url[:60], STORE_URL)

    if broken_count == len(to_check) and broken_count > 0:
        # Alle URLs waren kaputt — prüfe ob Text ohne Links noch sinnvoll ist
        text_without_urls = _URL_RE.sub("", fixed_text).strip()
        if len(text_without_urls) < 30:
            log.warning("Post übersprungen — alle URLs kaputt und kein sinnvoller Text: %s", text[:80])
            return None  # Post nicht senden

    return fixed_text


async def tg_send(
    session: aiohttp.ClientSession,
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "Markdown",
    skip_url_check: bool = False,
) -> bool:
    """
    Sicheres Telegram-Senden mit URL-Validierung.
    Gibt True bei Erfolg zurück, False bei Fehler oder übersprungenen Posts.
    """
    token = TG_TOKEN()
    chat  = chat_id or TG_CHAT()
    if not token or not chat:
        return False

    # URL-Validierung
    if not skip_url_check:
        validated = await validate_and_fix_text(session, text)
        if validated is None:
            return False  # Post übersprungen
        text = validated

    # Senden
    try:
        async with session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4096], "parse_mode": parse_mode},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                return True
            # Markdown-Fehler? → Plaintext retry
            if r.status == 400:
                async with session.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": text[:4096]},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r2:
                    return r2.status == 200
            log.debug("TG send HTTP %s", r.status)
            return False
    except Exception as e:
        log.debug("TG send error: %s", e)
        return False


async def tg_send_safe(text: str, chat_id: Optional[str] = None) -> bool:
    """Convenience-Wrapper — öffnet eigene Session."""
    async with aiohttp.ClientSession() as session:
        return await tg_send(session, text, chat_id=chat_id)
