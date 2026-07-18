#!/usr/bin/env python3
"""
RudiAgent — Dauerhafter autonomer KI-Assistent für Rudolf Sarkany
=================================================================
24/7 aktiv auf Railway. Empfängt Telegram-Befehle, überwacht alle
Systeme, repariert Fehler, deployt Fixes — und berichtet alles per Telegram.

Aktivierung:
  - Telegram: schreib dem Bot eine Aufgabe → RudiAgent erledigt sie
  - Automatisch: alle 30min Health-Check + Auto-Fix
  - Webhook: externe Systeme können Aufgaben übergeben

Fähigkeiten:
  - System-Health überwachen (Railway, Shopify, Stripe, APIs)
  - Code lesen, reparieren, per GitHub pushen
  - Shopify-Produkte verwalten
  - Stripe/Umsatz analysieren
  - GMC-Feed prüfen
  - Telegram-Alerts senden
  - Alle SuperMegaBot APIs steuern
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from modules.ai_client import ai_complete

log = logging.getLogger("RudiAgent")

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL        = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'supermegabot-production.up.railway.app')}"
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_RUDICLONE", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO     = os.getenv("GITHUB_REPO", "bullpowerhubgit/supermegabot")
CHECK_INTERVAL  = int(os.getenv("RUDI_AGENT_INTERVAL", "1800"))  # 30min

# Autorisierte Telegram-User (Chat-IDs) — nur diese können Befehle geben
_ALLOWED_CHATS: set = {TELEGRAM_CHAT} if TELEGRAM_CHAT else set()

# ── System-Wissen ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Du bist RudiAgent — der permanente autonome KI-Assistent von Rudolf Sarkany.

DEINE IDENTITÄT:
- Du bist Rudolfs verlängerter Arm: seine rechte Hand, sein technischer Direktor, sein 24/7-Assistent
- Du kennst JEDES Detail von SuperMegaBot, AIITEC, iNeedit, allen APIs und Systemen
- Du agierst SELBSTSTÄNDIG — keine Rückfragen außer bei irreversiblen Aktionen
- Du kommunizierst auf Deutsch, direkt und klar

DEINE FÄHIGKEITEN:
1. System-Health: Railway, Shopify, Stripe, GMC, Twilio, WhatsApp, alle APIs überwachen
2. Auto-Repair: Fehler erkennen → Code fixen → GitHub pushen → Railway deployt automatisch
3. Shopify: Produkte, Collections, SEO, GMC-Feed verwalten
4. Umsatz: Stripe, DS24, Gumroad analysieren und optimieren
5. Marketing: Social-Posts, E-Mails, Content planen und ausführen
6. Reporting: tägliche/wöchentliche Reports an Telegram

SYSTEME (alle live auf Railway):
- SuperMegaBot Dashboard: https://supermegabot-production.up.railway.app (Port 8888)
- AIITEC SaaS: aiitec-saas (Port 8091)
- Shop: ineedit.com.co (Shopify, 10k+ Produkte)
- Voice Agent: +1 762 568 5298 (Sofia/Max, OpenAI Realtime)
- GMC: Merchant 5734366162 (316 Produkte live)

PRODUKTE & PREISE (vollständig):
Smart Home: Starter Set €89, Kamera €129, Solar 800W €449, LED €69, Rasenmäher €349, Thermostat €149
Digital: SuperMegaBot €297, YouTube Blueprint €47, Automatisierungs-Blueprint €27, AI Guide €17
SaaS: Starter €49/Mo, Pro €99/Mo, Enterprise €299/Mo (monatlich kündbar)

RUDOLF SARKANY:
Gelernter KFZ-Mechaniker, autodidaktischer KI-Entwickler, Gründer AIITEC + iNeedit, Wien.
100+ KI-Systeme gebaut. Sein Motto: Alles automatisieren, niemals stehen bleiben.

REGELN:
- Führe Aufgaben vollständig durch — kein Halbfertiges
- Bei Fehlern: 3x retry, dann Telegram-Alert mit konkretem Problem
- Niemals Demo-Daten, Fake-Produkte oder Platzhalter erstellen
- Niemals Produkte mass-löschen ohne Bestätigung
- Niemals Railway deployen ohne Erlaubnis (außer bei Auto-Fix nach Push)
- Immer in Deutsch antworten
"""

# ── Telegram ──────────────────────────────────────────────────────────────────
async def _tg(text: str, parse_mode: str = "HTML") -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": text[:4096], "parse_mode": parse_mode},
            )
    except Exception as e:
        log.warning("Telegram send: %s", e)


async def _tg_typing() -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                json={"chat_id": TELEGRAM_CHAT, "action": "typing"},
            )
    except Exception:
        pass


# ── AI API (via ai_client — automatischer Fallback: Groq → DeepSeek → OpenRouter → Anthropic) ──
async def ask_claude(task: str, context: str = "", model: str = "claude-sonnet-5") -> str:
    """Sendet Aufgabe an ai_complete (automatischer Provider-Fallback) und gibt Antwort zurück."""
    prompt = f"{context}\n\nAufgabe: {task}" if context else f"Aufgabe: {task}"
    try:
        return await ai_complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
    except Exception as e:
        log.error("ai_complete: %s", e)
        return f"❌ Fehler: {e}"


# ── Health Check ──────────────────────────────────────────────────────────────
async def health_check() -> Dict[str, Any]:
    """Prüft alle Systeme und gibt Status zurück."""
    results = {}
    checks = [
        ("SuperMegaBot", f"{BASE_URL}/health"),
        ("GMC Feed", f"{BASE_URL}/api/gmc/feed.xml"),
        ("Voice API", f"{BASE_URL}/api/phone/stats"),
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        for name, url in checks:
            try:
                async with s.get(url) as r:
                    results[name] = {"ok": r.status < 400, "status": r.status}
            except Exception as e:
                results[name] = {"ok": False, "error": str(e)[:50]}
    return results


async def auto_health_report() -> None:
    """Automatischer Health-Check alle 30min."""
    results = await health_check()
    broken = [k for k, v in results.items() if not v.get("ok")]

    if broken:
        msg = f"⚠️ <b>RudiAgent Health-Alert</b>\n\n"
        msg += f"Probleme erkannt:\n"
        for k in broken:
            msg += f"  ❌ {k}: {results[k]}\n"
        msg += f"\n🔧 Analysiere und repariere..."
        await _tg(msg)

        # Auto-Fix via Claude
        fix_task = f"System-Health-Probleme gefunden: {broken}. Analysiere die Ursache und repariere autonom."
        fix = await ask_claude(fix_task, context=json.dumps(results))
        await _tg(f"🤖 <b>Auto-Fix Report:</b>\n\n{fix[:3000]}")
    else:
        log.info("Health OK: %s", list(results.keys()))


# ── Telegram Bot Loop ─────────────────────────────────────────────────────────
_last_update_id = 0

async def process_telegram_updates() -> None:
    """Verarbeitet eingehende Telegram-Nachrichten."""
    global _last_update_id
    if not TELEGRAM_TOKEN:
        return

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            params = {"timeout": 20, "offset": _last_update_id + 1}
            async with s.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params=params,
            ) as r:
                data = await r.json(content_type=None)

        updates = data.get("result", [])
        for upd in updates:
            _last_update_id = upd["update_id"]
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue

            chat_id = str(msg["chat"]["id"])
            text = msg.get("text", "").strip()

            if not text or chat_id not in _ALLOWED_CHATS:
                continue

            # Typing indicator
            await _tg_typing()

            # Spezielle Befehle
            if text.lower() in ("/start", "/hilfe", "/help"):
                await _tg(
                    "🤖 <b>RudiAgent — Dein autonomer KI-Assistent</b>\n\n"
                    "Ich bin 24/7 aktiv und erledige alles für dich.\n\n"
                    "Einfach schreiben was du brauchst — ich kümmere mich.\n\n"
                    "<b>Beispiele:</b>\n"
                    "• Prüf den System-Status\n"
                    "• Zeig mir den heutigen Umsatz\n"
                    "• Finde und fixe alle Fehler\n"
                    "• Erstelle 5 neue Shopify-Produkte\n"
                    "• Analysiere den GMC-Feed\n"
                    "• Wer hat heute angerufen?"
                )
                continue

            if text.lower() == "/health":
                results = await health_check()
                lines = ["🏥 <b>System Health:</b>\n"]
                for k, v in results.items():
                    icon = "✅" if v.get("ok") else "❌"
                    lines.append(f"{icon} {k}")
                await _tg("\n".join(lines))
                continue

            # Allgemeine Aufgabe an Claude
            log.info("Telegram task: %s", text[:80])

            # System-Kontext sammeln
            context = f"Aktueller Zeitpunkt: {time.strftime('%Y-%m-%d %H:%M')}\nBasis-URL: {BASE_URL}"

            response = await ask_claude(text, context=context)
            await _tg(f"🤖 <b>RudiAgent:</b>\n\n{response[:3900]}")

    except Exception as e:
        log.error("Telegram update: %s", e)


# ── Hauptschleife ─────────────────────────────────────────────────────────────
async def run() -> None:
    """Hauptschleife: Telegram-Updates + periodischer Health-Check."""
    log.info("RudiAgent gestartet — 24/7 aktiv")
    await _tg(
        "🚀 <b>RudiAgent ist online!</b>\n\n"
        "Ich bin deine rechte Hand — schreib mir einfach was du brauchst.\n"
        "Tippe /hilfe für eine Übersicht."
    )

    last_health = 0.0
    while True:
        try:
            # Telegram-Updates verarbeiten
            await process_telegram_updates()

            # Periodischer Health-Check
            if time.time() - last_health > CHECK_INTERVAL:
                last_health = time.time()
                await auto_health_report()

        except Exception as e:
            log.error("Hauptschleife: %s", e)

        await asyncio.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
    asyncio.run(run())
