"""
WhatsApp Business Cloud API — Outreach + Inbound Handler
85% Öffnungsrate · PHONE_ID: 1029511316922873
Nur für Leads mit Telefonnummer aus der DB
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger("WhatsAppOutreach")

WA_TOKEN    = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "1029511316922873")
WA_VERIFY   = os.getenv("WHATSAPP_VERIFY_TOKEN", "rudibot-verify-123")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL       = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")

DATA_DIR   = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
LEADS_FILE = DATA_DIR / "aiitec_leads.json"
WA_SENT    = DATA_DIR / "wa_sent.json"

WA_API = f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages"

# ── Nachrichtenvorlagen (müssen in Meta Business Suite genehmigt sein) ────────
# Bis Template genehmigt ist: direkte Text-Nachricht nach 24h-Fenster öffnen
COMPLIANCE_MSG = (
    "Hallo {name}! 👋\n\n"
    "Mein Name ist Rudolf Sarkany von AIITEC.\n\n"
    "Ich habe festgestellt, dass *{shop}* KI-gestützte Funktionen verwendet — "
    "und ab August 2026 greift *EU AI Act Artikel 50* mit Bußgeldern bis €15 Mio.\n\n"
    "Unser *Compliance Wächter* macht Sie in 24h vollständig konform:\n"
    "✅ Täglicher AI Act Scan\n"
    "✅ Automatisches Disclosure-Banner\n"
    "✅ Rechtssicherer Dokumentationsbericht\n\n"
    "*Preis: €1.500/Monat · Monatlich kündbar*\n\n"
    "Darf ich Ihnen kurz zeigen wie das aussieht?\n"
    "👉 {url}"
)

LEAD_AGENT_MSG = (
    "Hallo {name}! 👋\n\n"
    "Rudolf Sarkany hier, Gründer von AIITEC.\n\n"
    "Unser *Lead Agent* scannt täglich 50+ Firmen in Ihrer Zielgruppe "
    "und sendet Ihnen täglich *10 qualifizierte B2B-Kontakte* — vollautomatisch.\n\n"
    "Kein SDR. Kein Kaltanruf. Nur fertige Leads.\n\n"
    "*€500/Monat · Demo in 15 Minuten möglich*\n\n"
    "Interesse? 👉 {url}"
)


async def _send_wa(to: str, text: str) -> dict:
    """Sendet eine WhatsApp-Nachricht (Text)."""
    if not WA_TOKEN:
        log.warning("WHATSAPP_TOKEN fehlt")
        return {"error": "no_token"}

    # Nummer normalisieren: +4917... → 4917...
    to_clean = to.replace("+", "").replace(" ", "").replace("-", "")

    async with aiohttp.ClientSession() as s:
        async with s.post(
            WA_API,
            headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_clean,
                "type": "text",
                "text": {"preview_url": True, "body": text},
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            resp = await r.json()
            if resp.get("messages"):
                log.info("WA gesendet → %s", to_clean)
            else:
                log.warning("WA Fehler: %s", resp)
            return resp


async def send_outreach(phone: str, shop: str, name: str, product_fit: str) -> bool:
    """Sendet personalisierte WhatsApp-Outreach-Nachricht."""
    template = COMPLIANCE_MSG if product_fit == "compliance_waechter" else LEAD_AGENT_MSG
    text = template.format(name=name, shop=shop, url=BASE_URL)
    result = await _send_wa(phone, text)
    return bool(result.get("messages"))


async def run_wa_blast(max_sends: int = 20, dry_run: bool = False) -> dict:
    """Sendet WA-Nachrichten an Leads mit Telefonnummer."""
    leads = _load_leads()
    sent  = _load_sent()
    stats = {"total": len(leads), "sent": 0, "no_phone": 0, "already_sent": 0, "errors": 0}

    for lead in leads:
        if stats["sent"] >= max_sends:
            break

        phone = lead.get("phone", "").strip()
        if not phone:
            stats["no_phone"] += 1
            continue

        key = f"wa_{phone}"
        if key in sent:
            stats["already_sent"] += 1
            continue

        shop = lead.get("shop", lead.get("contact_email", "Ihr Shop"))
        name = lead.get("company", "Geschäftsführer")
        product_fit = lead.get("product_fit", "compliance_waechter")

        if dry_run:
            log.info("[DRY-RUN] WA → %s (%s): %s", phone, shop, product_fit)
            stats["sent"] += 1
            continue

        ok = await send_outreach(phone, shop, name, product_fit)
        if ok:
            sent.add(key)
            stats["sent"] += 1
            await asyncio.sleep(1)  # WhatsApp Rate-Limit
        else:
            stats["errors"] += 1

    if not dry_run:
        _save_sent(sent)

    await _notify_telegram(
        f"📱 <b>WhatsApp Blast fertig</b>\n"
        f"✅ Gesendet: {stats['sent']}\n"
        f"📵 Keine Nummer: {stats['no_phone']}\n"
        f"⏭️ Bereits gesendet: {stats['already_sent']}\n"
        f"❌ Fehler: {stats['errors']}"
    )
    return stats


# ── Inbound Handler (Webhook) ─────────────────────────────────────────────────
async def handle_wa_webhook_verify(request) -> "web.Response":
    """GET /webhook/whatsapp — Meta Verification."""
    from aiohttp import web
    mode      = request.rel_url.query.get("hub.mode", "")
    token     = request.rel_url.query.get("hub.verify_token", "")
    challenge = request.rel_url.query.get("hub.challenge", "")
    if mode == "subscribe" and token == WA_VERIFY:
        return web.Response(text=challenge)
    return web.Response(status=403)


async def handle_wa_webhook_event(request) -> "web.Response":
    """POST /webhook/whatsapp — eingehende Nachrichten."""
    from aiohttp import web
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=200)

    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        for msg in messages:
            sender = msg.get("from", "")
            text   = msg.get("text", {}).get("body", "")
            log.info("WA Eingang von %s: %s", sender, text[:80])

            reply = await _generate_wa_reply(text, sender)
            if reply:
                await _send_wa("+" + sender, reply)

            await _notify_telegram(
                f"📱 <b>WhatsApp Antwort!</b>\n"
                f"📞 Von: <code>+{sender}</code>\n"
                f"💬 Nachricht: {text[:200]}"
            )
    except Exception as e:
        log.error("WA Webhook Fehler: %s", e)

    return web.Response(text='{"status":"ok"}', content_type="application/json")


async def _generate_wa_reply(text: str, sender: str) -> str:
    """KI-Antwort: Claude → OpenAI → OpenRouter → Ollama."""
    from modules.ai_client import ai_chat

    result = await ai_chat(
        [{"role": "user", "content": f"Eingehende WhatsApp von +{sender}:\n{text}"}],
        system=(
            "Du bist Rudolf Sarkany von AIITEC. Antworte auf WhatsApp-Nachrichten "
            "auf Deutsch, professionell, freundlich. Max 150 Wörter. "
            "Ziel: Demo-Call buchen oder zur Website weiterleiten. "
            f"Website: {BASE_URL}"
        ),
        max_tokens=250,
    )
    return result or f"Danke für Ihre Nachricht! Weitere Infos: {BASE_URL}"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_leads() -> list:
    try:
        return json.loads(LEADS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _load_sent() -> set:
    try:
        return set(json.loads(WA_SENT.read_text(encoding="utf-8")))
    except Exception:
        return set()

def _save_sent(sent: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WA_SENT.write_text(json.dumps(list(sent), ensure_ascii=False), encoding="utf-8")

async def _notify_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass
