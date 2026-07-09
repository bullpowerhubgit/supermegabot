#!/usr/bin/env python3
"""
Facebook Group Poster — Playwright Browser-Automation.

Kein OAuth2, kein App Review, kein API-Token nötig.
Postet direkt in Facebook-Gruppen via Browser-UI mit gespeicherten Chrome-Cookies.

Ablauf:
  1. Chrome-Cookies für .facebook.com extrahieren (AES-256)
  2. Playwright-Browser startet headless mit diesen Cookies
  3. Navigiert zur Gruppen-Seite
  4. Klickt Schreib-Feld → tippt Text → klickt Posten
  5. Cooldown (48h) verhindert Spam
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("fb_group_poster")
_BASE = Path(__file__).parent.parent
_COOKIES_FILE = _BASE / "data" / "fb_cookies.json"
_COOLDOWN_FILE = _BASE / "data" / "fb_group_cooldown.json"
_LOG_FILE = _BASE / "data" / "fb_group_posts.json"

# Alle Gruppen von Rudolf's Facebook-Account
# IDs aus der Gruppen-Seite automatisch erkannt
KNOWN_GROUPS: list[dict] = [
    {"id": "1630899237148823", "name": "Geld verdienen Quellen im Internet für ein Nebeneinkommen"},
    {"id": "factsknowledgehub", "name": "Facts and Knowledge"},
]

# Nische-relevante Gruppen — nur diese für Marketing-Posts verwenden
MARKETING_GROUPS: list[str] = ["1630899237148823"]  # "Geld verdienen"

GROUP_COOLDOWN_SEC = 48 * 3600  # 48h

_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


# ──────────────────────────────────────────────────────────────────────────────
# Chrome Cookie Extraktion
# ──────────────────────────────────────────────────────────────────────────────

def _chrome_aes_key() -> Optional[bytes]:
    try:
        from Crypto.Protocol.KDF import PBKDF2
        r = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
            capture_output=True, text=True, timeout=5,
        )
        raw = r.stdout.strip()
        if not raw:
            return None
        return PBKDF2(raw.encode(), b"saltysalt", 16, 1003)
    except Exception as e:
        log.warning("AES key error: %s", e)
        return None


def _decrypt(enc_bytes: bytes, aes_key: bytes) -> str:
    try:
        from Crypto.Cipher import AES
        enc = bytes(enc_bytes)
        if enc[:3] != b"v10":
            return enc.decode("utf-8", errors="ignore")
        iv = b" " * 16
        cipher = AES.new(aes_key, AES.MODE_CBC, IV=iv)
        dec = cipher.decrypt(enc[3:])
        pad = dec[-1]
        raw = dec[:-pad]
        if len(raw) > 32:
            raw = raw[32:]
        return raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def refresh_cookies() -> bool:
    """Extrahiert Facebook-Cookies aus Chrome → data/fb_cookies.json."""
    aes_key = _chrome_aes_key()
    if not aes_key:
        log.warning("Chrome AES key nicht verfügbar")
        return False

    chrome_path = os.path.expanduser(
        "~/Library/Application Support/Google/Chrome/Default/Cookies"
    )
    if not os.path.exists(chrome_path):
        log.warning("Chrome Cookies DB nicht gefunden")
        return False

    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(chrome_path, tmp)
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute("""
            SELECT name, value, encrypted_value, host_key
            FROM cookies
            WHERE host_key LIKE '%.facebook.com'
        """)
        rows = cur.fetchall()
        conn.close()
    finally:
        os.unlink(tmp)

    cookies: dict = {}
    for name, val, enc, host in rows:
        v = val if val else _decrypt(enc, aes_key)
        if v:
            cookies[name] = v

    if not {"xs", "c_user"}.issubset(cookies.keys()):
        log.warning("Facebook: kritische Cookies fehlen — in Chrome einloggen!")
        return False

    _COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    log.info("Facebook Cookies gespeichert: %s Einträge", len(cookies))
    return True


def _load_cookies() -> list[dict]:
    if not _COOKIES_FILE.exists():
        refresh_cookies()
    try:
        raw = json.loads(_COOKIES_FILE.read_text())
        return [{"name": k, "value": v, "domain": ".facebook.com", "path": "/"} for k, v in raw.items()]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Cooldown
# ──────────────────────────────────────────────────────────────────────────────

def _load_cooldown() -> dict:
    try:
        return json.loads(_COOLDOWN_FILE.read_text()) if _COOLDOWN_FILE.exists() else {}
    except Exception:
        return {}


def _cooldown_ok(group_id: str) -> bool:
    return (time.time() - _load_cooldown().get(group_id, 0)) >= GROUP_COOLDOWN_SEC


def _record_post(group_id: str, text: str, success: bool) -> None:
    cd = _load_cooldown()
    if success:
        cd[group_id] = time.time()
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COOLDOWN_FILE.write_text(json.dumps(cd, indent=2))

    log_data = []
    if _LOG_FILE.exists():
        try:
            log_data = json.loads(_LOG_FILE.read_text())
        except Exception:
            pass
    log_data.append({"group": group_id, "text": text[:100], "ok": success, "ts": int(time.time())})
    log_data = log_data[-200:]
    _LOG_FILE.write_text(json.dumps(log_data, indent=2))


# ──────────────────────────────────────────────────────────────────────────────
# Gruppen-Erkennung
# ──────────────────────────────────────────────────────────────────────────────

def discover_groups() -> list[dict]:
    """Findet alle Gruppen in denen Rudolf Mitglied ist via Playwright."""
    from playwright.sync_api import sync_playwright

    cookies = _load_cookies()
    if not cookies:
        log.warning("Keine Facebook-Cookies")
        return KNOWN_GROUPS

    groups = list(KNOWN_GROUPS)  # Starte mit bekannten Gruppen

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_DESKTOP_UA, viewport={"width": 1280, "height": 800})
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto("https://www.facebook.com/groups/?tab=joined", wait_until="load", timeout=25000)

            # Extrahiere Gruppen-Links
            import re
            links = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href*="/groups/"]'))
                    .map(a => ({href: a.href, text: a.innerText.trim()}))
                    .filter(x => x.href.match(/\\/groups\\/[0-9a-zA-Z_]+\\/?$/) && x.text.length > 3)
            """)

            seen_ids = {g["id"] for g in groups}
            for link in links:
                m = re.search(r"/groups/([0-9a-zA-Z_]+)/?$", link.get("href", ""))
                if m:
                    gid = m.group(1)
                    if gid not in seen_ids and gid not in ("discover", "feed", "joined"):
                        groups.append({"id": gid, "name": link.get("text", gid)[:60]})
                        seen_ids.add(gid)

            browser.close()
    except Exception as e:
        log.warning("Gruppen-Erkennung fehlgeschlagen: %s", e)

    # Speichere entdeckte Gruppen
    discovered_file = _BASE / "data" / "fb_groups_discovered.json"
    discovered_file.parent.mkdir(parents=True, exist_ok=True)
    discovered_file.write_text(json.dumps(groups, indent=2, ensure_ascii=False))
    log.info("Gruppen gefunden: %s", len(groups))
    return groups


# ──────────────────────────────────────────────────────────────────────────────
# Playwright Group Poster
# ──────────────────────────────────────────────────────────────────────────────

def _post_to_group_sync(group_id: str, text: str) -> dict:
    """Postet in eine Gruppe via Playwright (synchron, für Thread)."""
    from playwright.sync_api import sync_playwright

    cookies = _load_cookies()
    if not cookies:
        return {"ok": False, "error": "Keine Facebook-Cookies"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=_DESKTOP_UA, viewport={"width": 1280, "height": 900})
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        try:
            group_url = f"https://www.facebook.com/groups/{group_id}"
            page.goto(group_url, wait_until="load", timeout=30000)
            page.wait_for_timeout(3000)

            # Prüfe ob Login nötig
            if "login" in page.url.lower():
                return {"ok": False, "error": "Nicht eingeloggt — Cookies abgelaufen"}

            # Schritt 1: "Schreib etwas..." Button per JS klicken → öffnet Beitrag-Modal
            page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('[role="button"]'));
                    const btn = btns.find(b => (b.textContent || '').includes('Schreib etwas'));
                    if (btn) btn.click();
                }
            """)
            page.wait_for_timeout(4000)

            # Schritt 2: Warte bis Beitrag-Input erscheint (direkter Check statt Dialog-Check)
            text_sel = '[aria-placeholder="Erstelle einen öffentlichen Beitrag ..."]'
            try:
                page.wait_for_selector(text_sel, timeout=12000)
            except Exception:
                # Zweiter Versuch: Koordinaten-Klick
                page.mouse.click(400, 473)
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_selector(text_sel, timeout=8000)
                except Exception:
                    page.screenshot(path=f"/tmp/fb_group_{group_id}_no_input.png")
                    return {"ok": False, "group": group_id, "error": "Beitrag-Eingabefeld nicht gefunden"}

            # Schritt 3: Text-Input per JS fokussieren (umgeht Overlay-Check)
            page.evaluate("""
                () => {
                    const el = document.querySelector('[aria-placeholder="Erstelle einen öffentlichen Beitrag ..."]');
                    if (el) { el.focus(); el.click(); }
                }
            """)
            page.wait_for_timeout(800)
            page.keyboard.type(text, delay=25)
            page.wait_for_timeout(1500)

            # Schritt 4: Posten-Button per JS klicken (umgeht Overlay/Actionability-Check)
            posted = page.evaluate("""
                () => {
                    // Suche nach aria-label="Posten" / "Post"
                    let btn = document.querySelector('[aria-label="Posten"]') || document.querySelector('[aria-label="Post"]');
                    if (!btn) {
                        // Fallback: Text-Match
                        const btns = Array.from(document.querySelectorAll('[role="button"]'));
                        btn = btns.find(b => b.textContent.trim() === 'Posten' || b.textContent.trim() === 'Post');
                    }
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            if not posted:
                page.screenshot(path=f"/tmp/fb_group_{group_id}_no_btn.png")
                return {"ok": False, "group": group_id, "error": "Posten-Button nicht gefunden"}

            page.wait_for_timeout(5000)

            # Erfolg: Modal geschlossen = Post abgesendet
            dialog_still_open = page.query_selector('[aria-placeholder="Erstelle einen öffentlichen Beitrag ..."]')
            success = dialog_still_open is None and "login" not in page.url.lower()
            return {"ok": success, "group": group_id, "url": page.url[:80]}

        except Exception as e:
            try:
                page.screenshot(path=f"/tmp/fb_group_{group_id}_error.png")
            except Exception:
                pass
            return {"ok": False, "group": group_id, "error": str(e)[:200]}
        finally:
            browser.close()


async def post_to_group(group_id: str, text: str) -> dict:
    """Async Wrapper für Playwright (läuft in Thread-Pool)."""
    if not _cooldown_ok(group_id):
        return {"ok": False, "group": group_id, "error": f"Cooldown aktiv ({GROUP_COOLDOWN_SEC//3600}h)"}

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _post_to_group_sync, group_id, text)
    _record_post(group_id, text, result.get("ok", False))
    return result


async def post_to_marketing_groups(text: str) -> list[dict]:
    """Postet in alle Marketing-relevanten Gruppen."""
    eligible = [gid for gid in MARKETING_GROUPS if _cooldown_ok(gid)]
    if not eligible:
        return [{"ok": False, "error": "Alle Gruppen im Cooldown"}]

    results = []
    for group_id in eligible:
        result = await post_to_group(group_id, text)
        results.append(result)
        if result.get("ok"):
            await asyncio.sleep(20)  # Anti-Spam zwischen Posts

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Scheduler Tasks
# ──────────────────────────────────────────────────────────────────────────────

async def task_facebook_groups_post() -> str:
    """Scheduler: alle 6h in Facebook-Gruppen posten (Playwright, kein App Review)."""
    try:
        from modules.ai_content_generator import generate_post
        text = await generate_post("facebook_group", "KI-Automation passives Einkommen Dropshipping 2026")
    except Exception:
        text = (
            "💰 Mit KI + Smart Drops automatisch Geld verdienen — meine Erfahrung 2026\n\n"
            "Seit ich meinen Shop auf KI-Automation umgestellt habe:\n"
            "✅ Produktfindung läuft automatisch\n"
            "✅ Content erstellt sich selbst\n"
            "✅ Bestellungen ohne manuellen Aufwand\n\n"
            "Das System arbeitet 24/7 während ich schlafe.\n\n"
            "Hat jemand ähnliche Erfahrungen? Was nutzt ihr für euer Nebeneinkommen?\n\n"
            "#PassivesEinkommen #KI #Dropshipping #OnlineBusiness #Nebeneinkommen"
        )

    results = await post_to_marketing_groups(text)
    ok = sum(1 for r in results if r.get("ok"))
    groups_ok = [r.get("group", "") for r in results if r.get("ok")]
    errors = [f"{r.get('group','?')}: {r.get('error','?')}" for r in results if not r.get("ok")]

    if ok:
        return f"Facebook Groups: {ok}/{len(results)} Posts ✅ ({', '.join(groups_ok)})"
    return f"Facebook Groups: 0 Posts — {' | '.join(errors[:3])}"


async def task_facebook_cookies_refresh() -> str:
    """Scheduler: täglich Chrome-Cookies für Facebook extrahieren."""
    ok = refresh_cookies()
    if ok:
        raw = json.loads(_COOKIES_FILE.read_text())
        return f"Facebook Cookies ✅ — {len(raw)} Einträge, c_user={raw.get('c_user','?')}"
    return "Facebook Cookies ❌ — Chrome nicht verfügbar oder nicht bei Facebook eingeloggt"
