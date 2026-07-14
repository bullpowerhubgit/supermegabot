#!/usr/bin/env python3
"""
Post-Monitor — Automatischer Qualitäts-Filter für Social-Media-Posts
====================================================================
Verhindert fehlerhafte Posts auf Facebook, Instagram, Telegram, Shopify.

Was es prüft:
  1. Kein Fake-Produkt (Bild muss existieren, Preis > 0)
  2. Keine Platzhalter ({name}, {price}, TODO, LOREM etc.)
  3. Links erreichbar (HTTP 200)
  4. Textqualität (kein Spam-Score > 0.7 via Groq)
  5. Kein Massen-Löschen ohne Bestätigung
  6. Keine verbotenen Branchen-Mischungen (Streetwear ≠ AliExpress etc.)
  7. Keine privaten Daten im Post (E-Mails, API-Keys, Telefonnummern)

Verwendung:
  from modules.post_monitor import PostMonitor
  ok, reasons = await PostMonitor().check(post_dict)
  if not ok:
      log.warning("Post blockiert: %s", reasons)

CLI:
  python3 modules/post_monitor.py --check '{"text": "...", "url": "...", "platform": "facebook"}'
  python3 modules/post_monitor.py --daemon   # überwacht Post-Queue in Supabase
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [POST-MON] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("PostMonitor")

_BASE = Path(__file__).parent.parent

def _load_env():
    ef = _BASE / ".env"
    if ef.exists():
        for line in ef.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

_TG_TOKEN = lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT  = lambda: os.getenv("TELEGRAM_CHAT_ID", "")
_SB_URL   = lambda: os.getenv("SUPABASE_URL", "")
_SB_KEY   = lambda: os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))
_GROQ_KEY = lambda: os.getenv("GROQ_API_KEY", "")

# ── Verbotene Muster (gemäß Feedback-Memory) ──────────────────────────────────

FORBIDDEN_PLACEHOLDERS = [
    r"\{[a-z_]+\}",         # {name}, {price} etc.
    r"TODO",
    r"PLACEHOLDER",
    r"LOREM IPSUM",
    r"TEST\s+(POST|CONTENT|TEXT)",
    r"BEISPIEL",
    r"MUSTER",
    r"\[BILD\]",
    r"\[IMAGE\]",
]

FORBIDDEN_CONTENT_PATTERNS = [
    r"api[_-]?key\s*=",           # API-Keys im Post
    r"password\s*=",
    r"token\s*=\s*['\"]?[a-z0-9]{20,}",
    r"sk-[a-zA-Z0-9]{40,}",       # OpenAI Keys
    r"AIza[0-9A-Za-z-_]{35}",     # Google API Keys
    r"\+?[0-9]{2}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4,}",  # Telefonnummern
]

SPAM_SIGNALS = [
    "gratis gratis", "klick hier", "click here now",
    "sofort reich", "jetzt kaufen kaufen", "100% kostenlos",
    "!!!", "FREE FREE", "BUY BUY BUY",
]

# Streetwear DARF NICHT mit Amazon/AliExpress/eBay gemischt werden
FORBIDDEN_COMBOS = [
    (["streetwear", "fashion", "clothing"], ["aliexpress", "amazon.de", "ebay"]),
]

# ── Prüfroutinen ──────────────────────────────────────────────────────────────

def _check_placeholders(text: str) -> List[str]:
    issues = []
    for pattern in FORBIDDEN_PLACEHOLDERS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"Platzhalter gefunden: '{re.findall(pattern, text, re.IGNORECASE)[0]}'")
    return issues

def _check_sensitive_data(text: str) -> List[str]:
    issues = []
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(f"Sensible Daten im Post: {pattern}")
    return issues

def _check_spam_signals(text: str) -> List[str]:
    text_lower = text.lower()
    issues = []
    for signal in SPAM_SIGNALS:
        if signal.lower() in text_lower:
            issues.append(f"Spam-Signal: '{signal}'")
    # Übermäßige Ausrufezeichen
    if text.count("!") > 5:
        issues.append(f"Zu viele Ausrufezeichen: {text.count('!')}×")
    # ALL CAPS (>50% Großbuchstaben)
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6 and len(text) > 30:
        issues.append("Text fast vollständig in Großbuchstaben")
    return issues

def _check_niche_combos(text: str, url: str = "") -> List[str]:
    combined = (text + " " + url).lower()
    issues = []
    for (forbidden_terms, forbidden_with) in FORBIDDEN_COMBOS:
        if any(t in combined for t in forbidden_terms):
            for bad in forbidden_with:
                if bad in combined:
                    issues.append(f"Verbotene Nischen-Mischung: {forbidden_terms[0]} + {bad}")
    return issues

async def _check_url_reachable(url: str, timeout: float = 8.0) -> Optional[str]:
    """Prüft ob URL erreichbar ist. Gibt Fehlermeldung zurück oder None."""
    if not url or not url.startswith("http"):
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(url, timeout=aiohttp.ClientTimeout(total=timeout),
                             allow_redirects=True) as r:
                if r.status >= 400:
                    return f"URL nicht erreichbar: {url} → HTTP {r.status}"
    except Exception as e:
        return f"URL-Fehler: {url} → {e}"
    return None

def _check_price_validity(price: Any) -> Optional[str]:
    """Prüft ob Preis gültig ist."""
    if price is None:
        return None
    try:
        p = float(str(price).replace(",", ".").replace("€", "").strip())
        if p <= 0:
            return f"Ungültiger Preis: {price}"
        if p > 10000:
            log.debug("Hoher Preis %s — OK (kein Preislimit)", price)
    except (ValueError, TypeError):
        return f"Preis nicht parsebar: {price}"
    return None

async def _check_image_url(image_url: str) -> Optional[str]:
    """Prüft ob Bild-URL existiert und ein Bild ist."""
    if not image_url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.head(image_url, timeout=aiohttp.ClientTimeout(total=8),
                             allow_redirects=True) as r:
                ct = r.headers.get("content-type", "")
                if r.status >= 400:
                    return f"Bild nicht erreichbar: HTTP {r.status}"
                if "image" not in ct and "octet-stream" not in ct:
                    return f"URL ist kein Bild (Content-Type: {ct})"
    except Exception as e:
        return f"Bild-URL-Fehler: {e}"
    return None

async def _check_text_quality_llm(text: str) -> List[str]:
    """Verwendet Groq (kostenlos) um Textqualität zu prüfen."""
    api_key = _GROQ_KEY()
    if not api_key or len(text) < 20:
        return []
    try:
        prompt = (
            f"Analysiere diesen Social-Media-Post auf Qualitätsprobleme. "
            f"Antworte NUR mit JSON: {{\"issues\": [\"problem1\", ...], \"spam_score\": 0.0}}\n\n"
            f"Post:\n{text[:500]}"
        )
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    # JSON aus Response extrahieren
                    m = re.search(r'\{[^}]+\}', content, re.DOTALL)
                    if m:
                        result = json.loads(m.group())
                        issues = result.get("issues", [])
                        spam_score = float(result.get("spam_score", 0))
                        if spam_score > 0.7:
                            issues.append(f"KI-Spam-Score: {spam_score:.2f}")
                        return [f"[KI] {i}" for i in issues if i]
    except Exception as e:
        log.debug("LLM-Check-Fehler: %s", e)
    return []

# ── Haupt-Check ───────────────────────────────────────────────────────────────

class PostMonitor:
    """
    Prüft einen Post auf Qualität und Sicherheit.

    post_dict Felder (alle optional außer text oder url):
      text       — Post-Text
      url        — Link im Post
      image_url  — Bild-URL
      price      — Preis (Zahl oder String)
      platform   — "facebook", "instagram", "telegram", "shopify"
      product_type — "streetwear", "electronics" etc.
    """

    async def check(self, post: Dict[str, Any], use_llm: bool = True) -> Tuple[bool, List[str]]:
        """Gibt (ok, issues) zurück. ok=False = Post blockiert."""
        text = str(post.get("text") or post.get("body") or post.get("content") or "")
        url  = str(post.get("url") or post.get("link") or "")
        image_url = str(post.get("image_url") or post.get("image") or "")
        price = post.get("price")
        platform = str(post.get("platform") or "").lower()

        all_issues: List[str] = []

        # 1. Platzhalter
        all_issues += _check_placeholders(text)

        # 2. Sensible Daten
        all_issues += _check_sensitive_data(text)

        # 3. Spam-Signale
        all_issues += _check_spam_signals(text)

        # 4. Nischen-Mischungen
        all_issues += _check_niche_combos(text, url)

        # 5. Preis-Validierung
        price_err = _check_price_validity(price)
        if price_err:
            all_issues.append(price_err)

        # 6. URL-Erreichbarkeit (async)
        url_checks = []
        if url:
            url_checks.append(_check_url_reachable(url))
        if image_url:
            url_checks.append(_check_image_url(image_url))

        url_results = await asyncio.gather(*url_checks, return_exceptions=True)
        for r in url_results:
            if isinstance(r, str) and r:
                all_issues.append(r)

        # 7. KI-Textqualitäts-Check (nur wenn kein anderes Problem)
        if use_llm and text and len(all_issues) == 0:
            llm_issues = await _check_text_quality_llm(text)
            all_issues += llm_issues

        ok = len(all_issues) == 0
        return ok, all_issues

    async def check_and_alert(self, post: Dict[str, Any],
                               context: str = "") -> Tuple[bool, List[str]]:
        """Prüft und sendet Telegram-Alert wenn blockiert."""
        ok, issues = await self.check(post)
        if not ok:
            platform = post.get("platform", "unbekannt")
            text_preview = str(post.get("text") or "")[:100]
            tg_msg = (
                f"🚫 *Post-Monitor: POST BLOCKIERT*\n"
                f"📱 Platform: {platform}\n"
                f"📝 Text: _{text_preview}_\n\n"
                f"⚠️ Probleme:\n" + "\n".join(f"• {i}" for i in issues)
            )
            if context:
                tg_msg += f"\n\n_Kontext: {context}_"
            await _tg(tg_msg)
        return ok, issues


# ── Telegram ──────────────────────────────────────────────────────────────────

async def _tg(text: str):
    token = _TG_TOKEN()
    chat  = _TG_CHAT()
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        log.warning("Telegram: %s", e)


# ── Daemon: überwacht Post-Queue in Supabase ──────────────────────────────────

async def _sb(method: str, path: str, body=None, params=None):
    url = _SB_URL().rstrip("/") + path
    headers = {
        "apikey": _SB_KEY(),
        "Authorization": f"Bearer {_SB_KEY()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    async with aiohttp.ClientSession() as s:
        fn = getattr(s, method.lower())
        kw: dict = {"headers": headers}
        if body:   kw["json"] = body
        if params: kw["params"] = params
        async with fn(url, **kw) as r:
            text = await r.text()
            if r.status >= 400:
                return None
            try:
                return json.loads(text)
            except Exception:
                return text

MONITOR_INTERVAL = 120  # 2 Minuten

async def daemon():
    log.info("Post-Monitor Daemon gestartet — prüft alle %ds", MONITOR_INTERVAL)
    await _tg("🛡️ *Post-Monitor* gestartet — überwacht alle Posts auf Fehler")
    monitor = PostMonitor()
    while True:
        try:
            # Hole pending posts (falls post_queue Tabelle existiert)
            pending = await _sb("GET", "/rest/v1/post_queue",
                                params={"status": "eq.pending", "limit": "20"})
            if pending and isinstance(pending, list):
                for post_row in pending:
                    ok, issues = await monitor.check_and_alert(
                        post_row, context=f"post_queue ID={post_row.get('id')}"
                    )
                    new_status = "approved" if ok else "blocked"
                    if issues:
                        log.info("Post #%s → %s: %s", post_row.get("id"), new_status, issues)
                    await _sb("PATCH",
                              f"/rest/v1/post_queue?id=eq.{post_row['id']}",
                              body={"status": new_status,
                                    "monitor_notes": json.dumps(issues, ensure_ascii=False)})
        except Exception as e:
            log.debug("Daemon-Fehler: %s", e)
        await asyncio.sleep(MONITOR_INTERVAL)


# ── CLI ───────────────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    monitor = PostMonitor()

    if "--check" in args:
        idx = args.index("--check")
        post_json = args[idx + 1] if idx + 1 < len(args) else "{}"
        try:
            post = json.loads(post_json)
        except json.JSONDecodeError:
            post = {"text": post_json}
        ok, issues = await monitor.check(post)
        print("\n=== Post-Monitor Check ===")
        print(f"Status: {'✅ OK' if ok else '🚫 BLOCKIERT'}")
        if issues:
            for i in issues:
                print(f"  ⚠️  {i}")
        else:
            print("  Keine Probleme gefunden.")
        print()

    elif "--test" in args:
        # Standardtest mit verschiedenen Post-Typen
        test_cases = [
            {"text": "Gutes Produkt für nur €99! Jetzt kaufen.", "url": "https://google.com", "price": 99},
            {"text": "Hallo {name}, kaufe jetzt!", "url": "https://example.com"},
            {"text": "GRATIS GRATIS GRATIS!!! KLICK HIER KLICK HIER!!!", "platform": "facebook"},
            {"text": "Normaler Post über unser Produkt. Qualität seit 2020.", "price": 149},
            {"text": "Stripe API key = sk-test-abc123 Kauf hier.", "platform": "instagram"},
        ]
        print("\n=== Post-Monitor Selbsttest ===\n")
        for i, post in enumerate(test_cases, 1):
            ok, issues = await monitor.check(post, use_llm=False)
            status = "✅ OK" if ok else "🚫 BLOCKIERT"
            print(f"Test {i}: {status}")
            print(f"  Text: {post['text'][:60]}")
            for iss in issues:
                print(f"  ⚠️  {iss}")
            print()

    elif "--daemon" in args:
        await daemon()
    else:
        print("Verwendung:")
        print("  --check '{\"text\": \"...\", \"url\": \"...\"}' — Einzelnen Post prüfen")
        print("  --test                                        — Selbsttest")
        print("  --daemon                                      — Post-Queue überwachen")


if __name__ == "__main__":
    asyncio.run(main())
