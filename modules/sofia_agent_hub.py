#!/usr/bin/env python3
"""
Sofia Agent Hub — Multi-Agenten-Koordination nach Telefonanrufen
================================================================
Nach jedem Sofia-Anruf wird automatisch das passende Agenten-Team ausgelöst:

  Kaufsignal 🔥  → Revenue Team + Growth Team (sofort, parallel)
  Anruf >30s     → Marketing Nurture Sequenz + Lead in Supabase
  Jeder Anruf    → Koordinator-Broadcast + Call in agent_messages

Einbindung in phone_ai_assistant.py:
    from modules.sofia_agent_hub import trigger_post_call_cascade
    asyncio.create_task(trigger_post_call_cascade(call_sid, duration, buying_signal, transcript))
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp

log = logging.getLogger("SofiaAgentHub")

_BASE = Path(__file__).parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(k: str, d: str = "") -> str:
    return os.getenv(k, d)


async def _tg(text: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    chat  = _env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text[:4096], "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=8),
            )
    except Exception as e:
        log.debug("TG-Fehler: %s", e)


def _coordinator_send(from_agent: str, payload: dict, to_agent: str = "all", msg_type: str = "info") -> None:
    try:
        from modules.agent_coordinator import send_message
        send_message(from_agent=from_agent, payload=payload, to_agent=to_agent, msg_type=msg_type)
    except Exception as e:
        log.debug("Coordinator unavailable: %s", e)


async def _supabase_upsert(table: str, data: dict) -> None:
    try:
        from modules.supabase_client import get_client
        get_client().table(table).upsert(data, on_conflict="id").execute()
    except Exception as e:
        log.debug("Supabase upsert Fehler: %s", e)


# ── Agent-Team Runner ─────────────────────────────────────────────────────────

async def _run_team(team: str, task: str) -> Optional[dict]:
    try:
        from modules.agent_teams import run_team
        return await asyncio.wait_for(run_team(team, task, notify=False), timeout=60)
    except asyncio.TimeoutError:
        log.warning("Team '%s' Timeout", team)
        return None
    except Exception as e:
        log.warning("Team '%s' Fehler: %s", team, e)
        return None


async def _email_drip_enroll(phone: str, product_id: str) -> None:
    """Trägt die Rufnummer (als Pseudo-Email) in die Drip-Sequenz ein."""
    try:
        from modules.email_drip_followup import enroll_lead
        pseudo_email = f"{phone.replace('+', '').replace(' ', '')}@phone.aiitec"
        await enroll_lead(email=pseudo_email, product_id=product_id, source="sofia_call")
    except AttributeError:
        pass
    except Exception as e:
        log.debug("Drip-Enroll Fehler: %s", e)


# ── Haupt-Cascade ─────────────────────────────────────────────────────────────

async def trigger_post_call_cascade(
    call_sid:      str,
    duration:      int,
    buying_signal: bool,
    transcript:    str,
    from_number:   str = "",
    product_id:    str = "general",
) -> None:
    """Startet die Multi-Agenten-Pipeline nach Abschluss eines Sofia-Anrufs."""

    now = datetime.now(timezone.utc).isoformat()

    # ── 1. Koordinator-Broadcast ──────────────────────────────────────────────
    _coordinator_send(
        from_agent="sofia",
        payload={
            "call_sid":      call_sid,
            "duration":      duration,
            "buying_signal": buying_signal,
            "from_number":   from_number,
            "product_id":    product_id,
            "timestamp":     now,
        },
        to_agent="all",
        msg_type="PHONE_CALL_COMPLETED",
    )
    log.info("[%s] Hub: Koordinator-Broadcast gesendet", call_sid)

    # ── 2. Lead in Supabase speichern (alle Anrufe) ───────────────────────────
    asyncio.create_task(_supabase_upsert("lead_events", {
        "event_type":    "sofia_call",
        "source":        "phone",
        "phone":         from_number,
        "product_id":    product_id,
        "call_sid":      call_sid,
        "duration_sec":  duration,
        "buying_signal": buying_signal,
        "notes":         transcript[:500] if transcript else "",
        "created_at":    now,
    }))

    # ── 3. Kurze Anrufe (<30s) — nur loggen ──────────────────────────────────
    if duration < 30:
        log.info("[%s] Hub: Anruf <30s — keine weiteren Aktionen", call_sid)
        return

    tasks = []

    # ── 4. Marketing Nurture (alle Anrufe >30s) ───────────────────────────────
    if from_number:
        tasks.append(_email_drip_enroll(from_number, product_id))

    # ── 5. Kaufsignal 🔥 → Revenue + Growth Team parallel ────────────────────
    if buying_signal:
        snippet = transcript[-600:] if transcript else "(kein Transkript)"

        tasks.append(_run_team(
            "revenue",
            f"Sofia-Anruf mit KAUFSIGNAL von {from_number}. "
            f"Produkt: {product_id}. Dauer: {duration}s.\n"
            f"Gesprächs-Snippet:\n{snippet}\n\n"
            f"Analysiere: Welches Upsell/Cross-Sell macht jetzt Sinn? "
            f"Soll sofort ein Rückruf-Task erstellt werden?"
        ))

        tasks.append(_run_team(
            "growth",
            f"Kaufsignal bei Sofia-Anruf: Produkt={product_id}, Nummer={from_number}.\n"
            f"Snippet: {snippet[:300]}\n"
            f"Was ist der optimale nächste Schritt um den Abschluss zu sichern? "
            f"Kurze Strategie in 3 Punkten."
        ))

        log.info("[%s] Hub: 🔥 Revenue + Growth Teams gestartet", call_sid)

    else:
        # ── 6. Kein Kaufsignal → Marketing-Team für Nachfass-Strategie ───────
        tasks.append(_run_team(
            "marketing",
            f"Sofia-Anruf ohne Kaufsignal: {from_number}, Produkt={product_id}, {duration}s.\n"
            f"Snippet: {transcript[-400:] if transcript else '—'}\n"
            f"Welche E-Mail-/SMS-Nachfass-Sequenz passt zu diesem Lead?"
        ))

    # Alle Tasks parallel ausführen
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ── 7. Zusammenfassung an Telegram ───────────────────────────────────────
    fire = "🔥 " if buying_signal else ""
    summaries = []
    for r in results:
        if isinstance(r, dict) and r.get("result"):
            summaries.append(str(r["result"])[:300])

    msg = (
        f"{fire}<b>Sofia Hub — Agenten-Cascade</b>\n"
        f"Anruf: {from_number} | {duration}s | {product_id}\n"
    )
    if buying_signal:
        msg += "🔥 <b>KAUFSIGNAL — Revenue + Growth Teams aktiviert</b>\n"
    else:
        msg += "📬 Marketing-Nurture gestartet\n"

    if summaries:
        msg += "\n<b>Agenten-Insights:</b>\n" + "\n---\n".join(summaries[:2])

    await _tg(msg)
    log.info("[%s] Hub: Cascade abgeschlossen (%d Tasks)", call_sid, len(results))
