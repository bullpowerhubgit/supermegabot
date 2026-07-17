#!/usr/bin/env python3
"""
Email Onboarding Autopilot — Resend + optional Loops.so sequences.

Sequences (days after signup):
  D0  Welcome + trial / payment link
  D1  Case study + Sales-Call CTA
  D3  Feature deep-dive + urgency
  D7  Soft close / upgrade

Env:
  RESEND_API_KEY
  RESEND_FROM_EMAIL / EMAIL_FROM / FROM_EMAIL
  LOOPS_API_KEY (optional)
  STRIPE_PAYMENT_LINK_STARTER or known buy.stripe.com fallback
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

log = logging.getLogger("EmailOnboardingAutopilot")

RESEND_API_KEY = os.getenv("RESEND_API_KEY") or os.getenv("RESEND_API_KEY_2") or ""
FROM_EMAIL = (
    os.getenv("RESEND_FROM_EMAIL")
    or os.getenv("EMAIL_FROM")
    or os.getenv("FROM_EMAIL")
    or "hello@ineedit.com.co"
)
LOOPS_API_KEY = os.getenv("LOOPS_API_KEY") or ""
STARTER_LINK = (
    os.getenv("STRIPE_PAYMENT_LINK_STARTER")
    or os.getenv("STRIPE_BUY_LINK_STARTER")
    or "https://buy.stripe.com/3cIfZjgM26TUgb60Oi4F434D"
)
CALL_CTA = os.getenv("SALES_CALL_URL") or "https://t.me/DudiRudibot"

SEQUENCE = [
    {
        "day": 0,
        "id": "welcome",
        "subject": "Willkommen bei SuperMegaBot — starte in 7 Minuten",
        "html": """
        <p>Hi{name},</p>
        <p>SuperMegaBot automatisiert Shopify, Traffic und Support — ohne dich als Flaschenhals.</p>
        <p><a href="{starter}">7 Tage starten (€49/mo Starter)</a></p>
        <p>Fragen? 15-Min Strategy Call: <a href="{call}">{call}</a></p>
        <p>— Rudolf / BullPower Hub</p>
        """,
    },
    {
        "day": 1,
        "id": "case_study",
        "subject": "Case Study: −40% Support-Tickets, mehr Recovery",
        "html": """
        <p>Hi{name},</p>
        <p>Ein Shopify-Shop senkte Support-Last um ~40% und steigerte Cart-Recovery mit dem gleichen Stack.</p>
        <p><a href="{starter}">Starter freischalten</a> · <a href="{call}">Sales-Call buchen</a></p>
        """,
    },
    {
        "day": 3,
        "id": "features",
        "subject": "Autopilot: Stripe · Agents · Deploy-Loop",
        "html": """
        <p>Hi{name},</p>
        <p>Unter der Haube: Stripe Abos, Claude-Agents, GitHub→Railway Deploy, Email-Sequenzen.</p>
        <p>Du zahlst nur, wenn du skalierst. <a href="{starter}">Jetzt Pro/Starter</a></p>
        """,
    },
    {
        "day": 7,
        "id": "close",
        "subject": "Letzte Erinnerung: Trial / Call diese Woche",
        "html": """
        <p>Hi{name},</p>
        <p>Wenn E-Commerce-Automation auf deiner Liste steht — diese Woche abschließen.</p>
        <p><a href="{starter}">Checkout</a> oder <a href="{call}">15-Min Call</a>.</p>
        """,
    },
]


def _render(html: str, email: str, name: str = "") -> str:
    nm = f" {name}" if name else ""
    return (
        html.replace("{name}", nm)
        .replace("{starter}", STARTER_LINK)
        .replace("{call}", CALL_CTA)
        .replace("{email}", email)
    )


async def send_resend(to: str, subject: str, html: str) -> dict[str, Any]:
    if not RESEND_API_KEY:
        return {"ok": False, "skipped": True, "reason": "RESEND_API_KEY missing"}
    payload = {
        "from": FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "SuperMegaBot-Onboarding/1.0",
                },
                json=payload,
            ) as r:
                data = await r.json(content_type=None)
                return {"ok": r.status < 300, "status": r.status, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def loops_upsert_contact(email: str, properties: dict | None = None) -> dict[str, Any]:
    if not LOOPS_API_KEY:
        return {"ok": False, "skipped": True, "reason": "LOOPS_API_KEY missing"}
    body = {"email": email, **(properties or {})}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(
                "https://app.loops.so/api/v1/contacts/update",
                headers={
                    "Authorization": f"Bearer {LOOPS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as r:
                data = await r.json(content_type=None)
                return {"ok": r.status < 300, "status": r.status, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def enroll_lead(email: str, name: str = "", day: int = 0) -> dict[str, Any]:
    """Send the sequence step for `day` and sync Loops contact."""
    step = next((s for s in SEQUENCE if s["day"] == day), SEQUENCE[0])
    html = _render(step["html"], email, name)
    resend = await send_resend(email, step["subject"], html)
    loops = await loops_upsert_contact(
        email,
        {
            "firstName": name or "",
            "source": "supermegabot_onboarding",
            "userGroup": f"day_{day}",
        },
    )
    return {
        "ok": bool(resend.get("ok") or resend.get("skipped")),
        "step": step["id"],
        "day": day,
        "resend": resend,
        "loops": loops,
        "at": datetime.now(timezone.utc).isoformat(),
    }


async def run_onboarding_health() -> dict[str, Any]:
    """Non-destructive health: keys present + sequence length."""
    return {
        "ok": True,
        "resend_configured": bool(RESEND_API_KEY),
        "loops_configured": bool(LOOPS_API_KEY),
        "from": FROM_EMAIL,
        "starter_link": STARTER_LINK,
        "steps": [{"day": s["day"], "id": s["id"]} for s in SEQUENCE],
        "at": datetime.now(timezone.utc).isoformat(),
    }
