"""AIITEC Reply Engine — Intelligente Email-Beantwortung

SICHERHEITSREGELN (NIEMALS brechen):
1. NUR antworten wenn Absender in unserer Leads-Datenbank ist
2. NUR antworten wenn kein System/Notification/Newsletter-Absender
3. NUR antworten wenn Email NICHT von einem unserer eigenen Accounts stammt
4. NUR 1 Antwort pro Email (duplicate prevention via message-id)
5. KI-Antwort muss auf das richtige Produkt eingehen
"""
import asyncio
import email as email_lib
import imaplib
import json
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp

log = logging.getLogger("ReplyEngine")

DATA_DIR      = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
REPLIED_FILE  = DATA_DIR / "replied_message_ids.json"
LEADS_FILE    = DATA_DIR / "aiitec_leads.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
BASE_URL       = os.getenv("RAILWAY_STATIC_URL", "https://aiitec-saas-production.up.railway.app")

# Brevo SMTP (primär — bessere Zustellbarkeit als Gmail)
BREVO_SMTP_HOST = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
BREVO_SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", "587"))
BREVO_SMTP_USER = os.getenv("BREVO_SMTP_USER", "")
BREVO_SMTP_PASS = os.getenv("BREVO_SMTP_PASS", "")
BREVO_FROM_EMAIL = os.getenv("BREVO_FROM_EMAIL", "aiitecbuuss@gmail.com")
BREVO_FROM_NAME  = os.getenv("BREVO_FROM_NAME", "Rudolf Sarkany | AIITEC")

# Stripe Payment Links — direkt in jede Reply eingebaut
STRIPE_LINK_STARTER    = os.getenv("STRIPE_LINK_STARTER",    "https://buy.stripe.com/plink_1Ti4nuRJECiV6vSmFVom8L5E")
STRIPE_LINK_PRO        = os.getenv("STRIPE_LINK_PRO",        "https://buy.stripe.com/plink_1Ti4nvRJECiV6vSmFHKXWjbz")
STRIPE_LINK_ENTERPRISE = os.getenv("STRIPE_LINK_ENTERPRISE", "https://buy.stripe.com/plink_1Ti4nwRJECiV6vSmgL2lZ7uk")

PAYMENT_LINKS = {
    "lead_agent":           ("Lead Agent €500/Mo",         STRIPE_LINK_STARTER),
    "compliance_waechter":  ("Compliance Wächter €1.500/Mo", STRIPE_LINK_PRO),
    "intelligence_suite":   ("Intelligence Suite €2.000/Mo", STRIPE_LINK_ENTERPRISE),
    "default":              ("Lead Agent €500/Mo",         STRIPE_LINK_STARTER),
}

# Hot-Lead Keywords — sofortiger Telegram-Alarm
_HOT_KEYWORDS = (
    "interessiert", "interesse", "demo", "termin", "angebot", "preis",
    "kosten", "kaufen", "buchen", "jetzt", "sofort", "wann", "wie viel",
    "anfragen", "kontakt", "call", "meeting", "gespräch", "yes", "ja",
    "proceed", "weiter", "machen wir", "nehmen wir", "klingt gut",
)

# ── Gmail-Konten (nur aktive) ─────────────────────────────────────────────────
GMAIL_ACCOUNTS = [
    {"user": os.getenv("GMAIL_USER_5",       "aiitecbuuss@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_5","").replace(" ",""),
     "name": "Rudolf Sarkany | AIITEC"},
    {"user": os.getenv("GMAIL_USER_3",       "bullpowersrtkennels@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_3","").replace(" ",""),
     "name": "Rudolf Sarkany | BullPower"},
    {"user": os.getenv("GMAIL_USER_1",       "dragonadnp@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_1","").replace(" ",""),
     "name": "Rudolf Sarkany"},
    {"user": os.getenv("GMAIL_USER_7",       "rudolf.sarkany.aiitec@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_7","").replace(" ",""),
     "name": "Rudolf Sarkany | AiiteC"},
    {"user": os.getenv("GMAIL_USER_8",       "rudolfsarkany1984@gmail.com"),
     "pass": os.getenv("GMAIL_APP_PASSWORD_8","").replace(" ",""),
     "name": "Rudolf Sarkany"},
]

# ── OWN EMAILS — niemals beantworten ────────────────────────────────────────
_OWN_EMAILS = {
    "aiitecbuuss@gmail.com", "bullpowersrtkennels@gmail.com",
    "dragonadnp@gmail.com", "rudolf.sarkany.aiitec@gmail.com",
    "rudolfsarkany1984@gmail.com",
}

# ── BLOCK-DOMAINS — niemals beantworten ─────────────────────────────────────
_BLOCK_DOMAINS = {
    "github.com", "github.io", "noreply.github.com",
    "facebookmail.com", "accounts.google.com", "google.com",
    "stripe.com", "shopify.com", "klaviyo.com", "sendgrid.net",
    "mailchimp.com", "beehiiv.com", "railway.app", "vercel.com",
    "joonix.net", "amazonses.com", "bounce.com",
    "mailer-daemon.googlemail.com", "postmaster.gmail.com",
    "digistore24.com", "paypal.com", "twilio.com",
    "microsoft.com", "linkedin.com", "xing.com",
    "slack.com", "notion.so", "atlassian.com",
    "sentry.io", "datadog.com", "newrelic.com",
}

# ── BLOCK-PREFIXES — niemals beantworten ────────────────────────────────────
_BLOCK_PREFIXES = (
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications", "notification", "alerts", "alert",
    "system", "daemon", "robot", "mailer-daemon",
    "newsletter", "marketing", "promo", "promotions",
    "updates", "info", "support", "help", "service",
    "billing", "invoice", "receipt", "order", "shipping",
    "bounce", "postmaster", "abuse", "unsubscribe",
    "auto", "automated", "autoresponder",
)

# ── KI-Antwort Prompts je Produkt ────────────────────────────────────────────
REPLY_PROMPTS = {
    "compliance_waechter": """Du bist Rudolf Sarkany von AIITEC. Ein potenzieller Kunde hat auf deine EU AI Act Compliance-Email geantwortet.
Schreibe eine professionelle, persönliche Email-Antwort auf Deutsch.
Ziel: Demo-Call buchen oder direkt zum Kauf führen.
Produkt: Compliance Wächter €1.500/mo — macht Shops in 24h EU AI Act konform.
Booking-Link: {url}/#compliance
Sei konkret, nicht generisch. Max 150 Wörter. Kein Spam-Verhalten.""",

    "lead_agent": """Du bist Rudolf Sarkany von AIITEC. Ein Interessent hat auf deine B2B Lead-Automation Email geantwortet.
Schreibe eine professionelle Antwort auf Deutsch.
Ziel: Demo-Call buchen oder direkt zum Kauf führen.
Produkt: Lead Agent €500/mo — KI findet täglich 10 qualifizierte B2B-Leads.
Buchung: {url}/#leads
Sei direkt, überzeugend, max 150 Wörter.""",

    "default": """Du bist Rudolf Sarkany von AIITEC. Jemand hat auf eine Email geantwortet.
Schreibe eine professionelle, kurze Antwort auf Deutsch.
Präsentiere kurz AIITEC's Angebote (Lead Agent €500/mo, Compliance Wächter €1.500/mo, Intelligence Suite €2.000/mo).
Website: {url}
Max 120 Wörter. Professionell und persönlich.""",
}


def _load_replied() -> set:
    try:
        return set(json.loads(REPLIED_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_replied(ids: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPLIED_FILE.write_text(json.dumps(list(ids), ensure_ascii=False), encoding="utf-8")


def _load_leads() -> dict:
    """Gibt leads als dict {email: lead_data} zurück."""
    try:
        leads = json.loads(LEADS_FILE.read_text(encoding="utf-8"))
        return {l.get("contact_email", l.get("shop", "")).lower(): l for l in leads if l.get("contact_email") or l.get("shop")}
    except Exception:
        return {}


def _is_safe_to_reply(from_email: str) -> tuple[bool, str]:
    """Gibt (safe, reason) zurück. Nur True wenn wirklich sicher."""
    addr = from_email.strip().lower()
    if not addr or "@" not in addr:
        return False, "kein gültiges Email-Format"
    local = addr.split("@")[0]
    domain = addr.split("@")[1]

    if addr in _OWN_EMAILS:
        return False, f"eigener Account ({addr})"
    if domain in _BLOCK_DOMAINS:
        return False, f"blockierte Domain ({domain})"
    if any(local.startswith(p) for p in _BLOCK_PREFIXES):
        return False, f"blockiertes Prefix ({local})"
    # Kein Reply auf Bounces
    if "bounce" in addr or "daemon" in addr or "mailer" in addr:
        return False, "Bounce/Daemon-Adresse"
    return True, "ok"


def _is_hot_lead(body: str) -> bool:
    """Erkennt Kaufsignale im Antwort-Text."""
    lower = body.lower()
    return any(kw in lower for kw in _HOT_KEYWORDS)


async def _hot_lead_alarm(from_email: str, subject: str, body: str, product_fit: str):
    """Sofort-Alarm an Telegram wenn Kaufsignale erkannt."""
    link_name, link_url = PAYMENT_LINKS.get(product_fit, PAYMENT_LINKS["default"])
    await _notify_telegram(
        f"🔥 <b>HOT LEAD!</b> Kaufsignal erkannt!\n\n"
        f"📧 Von: <code>{from_email}</code>\n"
        f"📦 Produkt: {product_fit}\n"
        f"💬 Betreff: {subject[:60]}\n"
        f"📝 Nachricht: {body[:200]}\n\n"
        f"💳 <b>Payment Link ({link_name}):</b>\n{link_url}\n\n"
        f"⚡ Ruf jetzt an oder schreib direkt zurück!"
    )


async def _generate_ai_reply(original_text: str, product_fit: str, sender_email: str) -> str:
    """Generiert KI-Antwort: Claude → OpenAI → OpenRouter → Ollama."""
    from modules.ai_client import ai_chat

    prompt_template = REPLY_PROMPTS.get(product_fit, REPLY_PROMPTS["default"])
    system_prompt = prompt_template.format(url=BASE_URL)
    user_msg = (
        f"Die ursprüngliche Email kam von: {sender_email}\n\n"
        f"Inhalt der Antwort des Interessenten:\n{original_text[:1000]}\n\n"
        f"Schreibe jetzt die Antwort-Email (nur den Text, kein Betreff):"
    )

    result = await ai_chat(
        [{"role": "user", "content": user_msg}],
        system=system_prompt,
        max_tokens=400,
    )

    return result or (
        f"Vielen Dank für Ihre Antwort!\n\n"
        f"Ich melde mich innerhalb von 24h persönlich bei Ihnen.\n\n"
        f"Für sofortige Infos: {BASE_URL}\n\n"
        f"Viele Grüße\nRudolf Sarkany | AIITEC"
    )


def _build_reply_msg(from_addr: str, from_name: str, to_email: str, subject: str, body: str, in_reply_to: str = "") -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"]    = f"{from_name} <{from_addr}>"
    msg["To"]      = to_email
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"]  = in_reply_to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def _send_reply(account: dict, to_email: str, subject: str, body: str, in_reply_to: str = "") -> bool:
    """Sendet Antwort: Brevo SMTP primär (bessere Zustellbarkeit), Gmail-SMTP als Fallback."""
    # Primär: Brevo SMTP (STARTTLS port 587)
    if BREVO_SMTP_USER and BREVO_SMTP_PASS:
        try:
            msg = _build_reply_msg(BREVO_FROM_EMAIL, BREVO_FROM_NAME, to_email, subject, body, in_reply_to)
            with smtplib.SMTP(BREVO_SMTP_HOST, BREVO_SMTP_PORT, timeout=20) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.login(BREVO_SMTP_USER, BREVO_SMTP_PASS)
                s.send_message(msg)
            log.info("Antwort via Brevo SMTP gesendet an %s", to_email)
            return True
        except Exception as e:
            log.warning("Brevo SMTP fehlgeschlagen: %s — Fallback zu Gmail", e)

    # Fallback: Gmail SMTP SSL
    if not account.get("pass"):
        return False
    try:
        msg = _build_reply_msg(account["user"], account["name"], to_email, subject, body, in_reply_to)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(account["user"], account["pass"])
            s.send_message(msg)
        log.info("Antwort via Gmail SMTP gesendet an %s", to_email)
        return True
    except Exception as e:
        log.warning("Gmail SMTP fehlgeschlagen (%s): %s", account["user"], e)
        return False


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


def _scan_inbox(account: dict, replied_ids: set) -> list:
    """Scannt ein Gmail-Konto auf ungelesene Replies. Gibt neue Messages zurück."""
    if not account.get("pass"):
        return []
    messages = []
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
        m.login(account["user"], account["pass"])
        m.select("INBOX")
        # Nur UNSEEN der letzten 24h
        _, data = m.search(None, "UNSEEN")
        uids = data[0].split() if data[0] else []
        # Max 20 pro Durchlauf
        for uid in uids[-20:]:
            _, msg_data = m.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)
            msg_id = msg.get("Message-ID", "").strip()
            if not msg_id or msg_id in replied_ids:
                continue
            from_raw = msg.get("From", "")
            from_email = email_lib.utils.parseaddr(from_raw)[1].lower().strip()
            subject   = msg.get("Subject", "")
            # Body extrahieren
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass

            messages.append({
                "uid": uid,
                "msg_id": msg_id,
                "from_email": from_email,
                "from_raw": from_raw,
                "subject": subject,
                "body": body[:2000],
                "account": account,
            })
        m.logout()
    except Exception as e:
        log.warning("IMAP %s: %s", account.get("user", "?"), e)
    return messages


async def process_replies_once() -> dict:
    """Ein Durchlauf: alle Postfächer scannen + sichere Antworten senden."""
    replied_ids = _load_replied()
    leads_db    = _load_leads()
    stats = {"scanned": 0, "replied": 0, "skipped": 0, "errors": 0}

    for account in GMAIL_ACCOUNTS:
        if not account.get("pass"):
            continue
        messages = _scan_inbox(account, replied_ids)
        stats["scanned"] += len(messages)

        for msg in messages:
            from_email = msg["from_email"]
            safe, reason = _is_safe_to_reply(from_email)

            if not safe:
                log.debug("[SKIP] %s — %s", from_email, reason)
                stats["skipped"] += 1
                replied_ids.add(msg["msg_id"])  # nicht nochmal prüfen
                continue

            # Produkt-Fit aus Leads-DB ermitteln
            lead_data   = leads_db.get(from_email, {})
            product_fit = lead_data.get("product_fit", "default")

            # Hot-Lead-Erkennung — sofortiger Alarm
            if _is_hot_lead(msg["body"]):
                await _hot_lead_alarm(from_email, msg["subject"], msg["body"], product_fit)

            # KI-Antwort generieren (mit Payment Link)
            try:
                ai_reply = await _generate_ai_reply(msg["body"], product_fit, from_email)
                # Payment Link ans Ende jeder Antwort
                link_name, link_url = PAYMENT_LINKS.get(product_fit, PAYMENT_LINKS["default"])
                ai_reply += (
                    f"\n\n---\n"
                    f"👉 Direkt starten: {link_url}\n"
                    f"({link_name} · monatlich kündbar)"
                )
            except Exception as e:
                log.error("KI-Fehler für %s: %s", from_email, e)
                stats["errors"] += 1
                continue

            # Antwort senden
            ok = _send_reply(
                account=msg["account"],
                to_email=from_email,
                subject=msg["subject"],
                body=ai_reply,
                in_reply_to=msg["msg_id"],
            )

            if ok:
                replied_ids.add(msg["msg_id"])
                stats["replied"] += 1
                log.info("[REPLY] ✅ %s → %s (Produkt: %s)", msg["account"]["user"], from_email, product_fit)
                await _notify_telegram(
                    f"📧 <b>Reply gesendet!</b>\n"
                    f"📨 An: <code>{from_email}</code>\n"
                    f"📦 Produkt: {product_fit}\n"
                    f"📬 Via: {msg['account']['user']}\n"
                    f"💬 Betreff: {msg['subject'][:60]}"
                )
            else:
                log.warning("[REPLY] ❌ SMTP fehlgeschlagen für %s", from_email)
                stats["errors"] += 1

    _save_replied(replied_ids)
    return stats


async def reply_watchdog_loop():
    """Läuft alle 10 Minuten. Prüft + korrigiert Email-Replies."""
    log.info("Reply Watchdog gestartet — Intervall: 10 Minuten")
    run_count = 0
    while True:
        await asyncio.sleep(10 * 60)  # 10 Minuten warten
        run_count += 1
        try:
            log.info("[Watchdog #%d] Starte Reply-Scan...", run_count)
            stats = await process_replies_once()
            log.info(
                "[Watchdog #%d] Ergebnis: %d gescannt | %d beantwortet | %d übersprungen | %d Fehler",
                run_count, stats["scanned"], stats["replied"], stats["skipped"], stats["errors"]
            )
            # Telegram-Alert nur wenn etwas passiert ist oder Fehler aufgetreten
            if stats["replied"] > 0 or stats["errors"] > 0:
                await _notify_telegram(
                    f"🔄 <b>Watchdog #{run_count}</b>\n"
                    f"📊 Gescannt: {stats['scanned']}\n"
                    f"✅ Beantwortet: {stats['replied']}\n"
                    f"⏭️ Übersprungen: {stats['skipped']}\n"
                    f"❌ Fehler: {stats['errors']}"
                )
        except Exception as e:
            log.error("[Watchdog #%d] Kritischer Fehler: %s", run_count, e)
            await _notify_telegram(
                f"🚨 <b>Watchdog Fehler!</b>\n"
                f"❌ {str(e)[:200]}\n"
                f"🔄 Nächster Versuch in 10 Min."
            )
