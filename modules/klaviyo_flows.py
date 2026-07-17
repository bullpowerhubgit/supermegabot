#!/usr/bin/env python3
"""Klaviyo Flows — Welcome/Re-Engagement Email-Sequenzen."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

import aiohttp

log = logging.getLogger("KlaviyoFlows")

_ENROLLED_FILE = Path(__file__).resolve().parents[1] / "data" / "klaviyo_enrolled.json"
_SHOP_URL      = os.getenv("SHOPIFY_SHOP_URL", "https://ineedit.com.co")
_KV_KEY        = os.getenv("KLAVIYO_API_KEY", "")
_KV_BASE       = "https://a.klaviyo.com/api"
_KV_HEADERS    = {"Authorization": f"Klaviyo-API-Key {_KV_KEY}", "revision": "2024-10-15"}

_SEQUENCE_DAYS = [0, 3, 7]
_SUBJECTS = {
    0: "Willkommen bei ineedit Smart Home! 🏠",
    3: "Dein Smart-Home-Starter-Guide ist da 💡",
    7: "Exklusiv für dich: 10% auf deine nächste Bestellung 🎁",
}


# ── Lokale Enrollment-Datei ───────────────────────────────────────────────────

def _load_enrolled() -> Dict:
    try:
        if _ENROLLED_FILE.exists():
            return json.loads(_ENROLLED_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_enrolled(data: Dict) -> None:
    _ENROLLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ENROLLED_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ── Email-Templates ───────────────────────────────────────────────────────────

def _cta(text: str, url: str) -> str:
    return (f'<a href="{url}" style="display:inline-block;background:#ff6b35;color:#fff;'
            f'padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;'
            f'font-size:16px;margin:16px 0">{text}</a>')


def _wrap(content: str) -> str:
    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0d0d0d;color:#e0e0e0;padding:24px;border-radius:10px">
  {content}
  <hr style="border-color:#2a2a2a;margin:24px 0">
  <p style="font-size:11px;color:#555;text-align:center">
    <a href="{_SHOP_URL}" style="color:#555">ineedit.com.co</a> |
    <a href="{_SHOP_URL}/pages/unsubscribe" style="color:#555">Abmelden</a>
  </p>
</div>"""


def _build_step_email(step: int, name: str = "") -> tuple[str, str]:
    first = name.split()[0] if name else "du"
    if step == 0:
        html = _wrap(f"""
          <h2 style="color:#ff6b35">Willkommen, {first}! 🎉</h2>
          <p>Schön, dass du dabei bist. Entdecke unsere beliebtesten Smart-Home-Produkte:</p>
          <ul style="color:#ccc;padding-left:20px">
            <li>🔋 Solar Powerstations & Balkonkraftwerke</li>
            <li>🏠 Smart-Home Gadgets & AI-Geräte</li>
            <li>☀️ Off-Grid Energie-Sets</li>
          </ul>
          {_cta("Jetzt entdecken →", f"{_SHOP_URL}/collections/all")}
        """)
    elif step == 3:
        html = _wrap(f"""
          <h2 style="color:#ff6b35">Dein Smart-Home Guide 💡</h2>
          <p>Hey {first}, hier sind unsere Top-Tipps für dein smartes Zuhause:</p>
          <ol style="color:#ccc;padding-left:20px">
            <li><b>Smart-Thermostat</b> — spare bis zu 30% Heizkosten</li>
            <li><b>Solar-Powerstation</b> — Stromkosten senken + Blackout-Schutz</li>
            <li><b>Smart-Beleuchtung</b> — Atmosphäre + Energiesparen</li>
          </ol>
          {_cta("Alle Smart-Home Produkte →", f"{_SHOP_URL}/collections/smart-home")}
        """)
    else:
        html = _wrap(f"""
          <h2 style="color:#ff6b35">Exklusiv für dich: 10% Rabatt 🎁</h2>
          <p>Hey {first}, als Dankeschön für dein Interesse bekommst du 10% auf deine Bestellung:</p>
          <div style="background:#1a1a1a;padding:16px;border-radius:8px;margin:16px 0;text-align:center">
            <p style="font-size:24px;font-weight:bold;color:#ff6b35;margin:0">WELCOME10</p>
            <p style="color:#aaa;margin:8px 0 0 0">10% Rabatt auf alle Produkte</p>
          </div>
          {_cta("Code einlösen →", f"{_SHOP_URL}/discount/WELCOME10")}
        """)
    return _SUBJECTS[step], html


# ── Welcome Enroll ────────────────────────────────────────────────────────────

async def enroll_welcome_sequence(email: str, first_name: str = "") -> Dict:
    from modules.sendgrid_blast import send_single
    enrolled = _load_enrolled()
    if email in enrolled:
        return {"ok": True, "email": email, "status": "already_enrolled",
                "step": enrolled[email].get("step", 0)}

    subject, html = _build_step_email(0, first_name)
    result = await send_single(email, first_name, subject, html)

    enrolled[email] = {
        "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "sequence": "welcome",
        "step": 1,
        "name": first_name,
    }
    _save_enrolled(enrolled)
    return {"ok": result.get("ok", False), "email": email, "step": "welcome_sent"}


# ── Welcome Drip (täglich) ────────────────────────────────────────────────────

async def run_welcome_drip() -> Dict:
    from modules.sendgrid_blast import send_single
    enrolled = _load_enrolled()
    now = datetime.now(timezone.utc)
    sent = 0
    skipped = 0

    for email, data in list(enrolled.items()):
        if data.get("sequence") != "welcome":
            continue
        step = data.get("step", 1)
        if step >= len(_SEQUENCE_DAYS):
            skipped += 1
            continue

        enrolled_at = datetime.fromisoformat(data.get("enrolled_at", now.isoformat()))
        days_elapsed = (now - enrolled_at).days
        target_day   = _SEQUENCE_DAYS[step]

        if days_elapsed >= target_day:
            name = data.get("name", "")
            subject, html = _build_step_email(step, name)
            result = await send_single(email, name, subject, html)
            if result.get("ok"):
                enrolled[email]["step"] = step + 1
                sent += 1
                log.info("Drip step %d gesendet: %s", step, email[:20])
            await asyncio.sleep(0.1)
        else:
            skipped += 1

    _save_enrolled(enrolled)
    return {"ok": True, "sent": sent, "skipped": skipped, "total": len(enrolled)}


# ── Re-Engagement ─────────────────────────────────────────────────────────────

async def run_reengagement() -> Dict:
    if not _KV_KEY:
        return {"ok": False, "error": "no KLAVIYO_API_KEY"}

    from modules.sendgrid_blast import send_single
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    profiles = []

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(
                f"{_KV_BASE}/profiles/",
                headers={**_KV_HEADERS, "Content-Type": "application/json"},
                params={"fields[profile]": "email,first_name,updated", "page[size]": "50"},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    profiles = data.get("data", [])
    except Exception as e:
        log.warning("Klaviyo re-engagement list: %s", e)
        return {"ok": False, "error": str(e)[:100]}

    sent = 0
    for p in profiles[:20]:
        attrs = p.get("attributes", {})
        email = attrs.get("email", "").strip()
        name  = attrs.get("first_name", "")
        if not email:
            continue

        subject = "Hast du unsere neuen Smart-Home-Hits gesehen? 🔥"
        html = _wrap(f"""
          <h2 style="color:#ff6b35">Hey {name or 'du'}, wir vermissen dich! 👋</h2>
          <p>Es gibt Neues bei ineedit Smart Home — entdecke unsere aktuellen Highlights:</p>
          <ul style="color:#ccc;padding-left:20px">
            <li>⚡ Neue Solar Powerstations ab €199</li>
            <li>🤖 AI Smart-Home-Gadgets 2026</li>
            <li>🔋 Balkonkraftwerk-Komplettsets</li>
          </ul>
          {_cta("Jetzt neu entdecken →", f"{_SHOP_URL}/collections/all?sort_by=created-descending")}
        """)
        result = await send_single(email, name, subject, html)
        if result.get("ok"):
            sent += 1
        await asyncio.sleep(0.1)

    return {"ok": True, "sent": sent, "checked": len(profiles)}


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_flow_stats() -> Dict:
    enrolled = _load_enrolled()
    complete = sum(1 for d in enrolled.values() if d.get("step", 0) >= len(_SEQUENCE_DAYS))
    return {
        "ok": True,
        "enrolled": len(enrolled),
        "welcome_complete": complete,
        "in_progress": len(enrolled) - complete,
    }
