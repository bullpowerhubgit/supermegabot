"""
reply_monitor.py — Automatischer Reply-Monitor für alle Outreach-Agenten
Läuft alle 15 Min, prüft Gmail auf Antworten, klassifiziert per Claude Haiku,
sendet automatisch Stripe-Checkout-Link bei Interesse, Telegram-Alert sofort.
"""
import asyncio
import imaplib
import email
import email.header
import smtplib
import ssl
import sqlite3
import os
import sys
import logging
import json
import re
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REPLY-MON] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("reply_monitor")

# ── Config ──────────────────────────────────────────────────────────────────
GMAIL_USER = os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD_AIITEC", "xulp qyuz gxnb vfqw").replace(" ", "")
IMAP_HOST  = "imap.gmail.com"
IMAP_PORT  = 993
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 465

ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
STRIPE_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL = 15 * 60  # 15 Minuten
DB_PATH = Path("data/reply_monitor.db")

# ── Outreach-Schlüsselwörter (erkennen ob Reply auf unsere Emails) ──────────
OUTREACH_KEYWORDS = [
    "ai act", "compliance", "eu-ki-verordnung", "bußgeld", "risiko",
    "zwangsversteigerung", "zvg", "handelsregister", "gmbh", "gründung",
    "insolvenz", "factoring", "inkasso", "lead", "angebot",
    "steuerberater", "buchhaltung", "versicherung"
]

# ── Produkte → Stripe Payment Links (werden beim ersten Run erstellt) ─────────
PRODUCTS = {
    "AI_ACT_REPORT": {
        "name": "EU AI Act Compliance Report",
        "description": "Individueller Compliance-Bericht für Ihr Unternehmen — Risikoklasse, Handlungsempfehlungen, Fristen",
        "amount": 29900,  # €299 in Cent
        "currency": "eur",
        "recurring": None,
        "email_trigger": ["ai act", "compliance", "bericht", "risiko", "bußgeld"],
    },
    "AI_ACT_MONITORING": {
        "name": "EU AI Act Monitoring Abo",
        "description": "Monatliches Monitoring — Updates, neue Pflichten, Änderungen der EU KI-Verordnung",
        "amount": 9900,
        "currency": "eur",
        "recurring": "month",
        "email_trigger": ["monitoring", "abo", "monatlich", "überwachung"],
    },
    "ZVG_BASIC": {
        "name": "ZVG Lead-Feed Basic",
        "description": "Tägliche Zwangsversteigerungs-Leads: Objekt, Verkehrswert, Bundesland, Kontakt",
        "amount": 9900,
        "currency": "eur",
        "recurring": "month",
        "email_trigger": ["zvg", "zwangsversteigerung", "immobilien", "lead"],
    },
    "ZVG_PRO": {
        "name": "ZVG Lead-Feed Pro",
        "description": "Pro-Zugang: alle Leads, Frühzugang, KI-Scoring, unbegrenzte Downloads",
        "amount": 29900,
        "currency": "eur",
        "recurring": "month",
        "email_trigger": ["zvg pro", "premium", "alle leads"],
    },
    "HR_LEADS": {
        "name": "Handelsregister Lead-Feed",
        "description": "Tägliche neue GmbH-Gründungen: Firma, Branche, Bundesland, Geschäftsführer",
        "amount": 4900,
        "currency": "eur",
        "recurring": "month",
        "email_trigger": ["handelsregister", "gmbh", "gründung", "neugründung"],
    },
    "INSOLVENZ_DEAL": {
        "name": "Insolvenz-Lead Paket (Einmalig)",
        "description": "500 qualifizierte Insolvenz-Leads mit Scoring, Branche und Kontaktdaten",
        "amount": 49900,
        "currency": "eur",
        "recurring": None,
        "email_trigger": ["insolvenz", "factoring", "inkasso"],
    },
}

# ── DB ───────────────────────────────────────────────────────────────────────
def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY,
            sender TEXT,
            subject TEXT,
            classification TEXT,
            product_key TEXT,
            stripe_link TEXT,
            reply_sent INTEGER DEFAULT 0,
            telegram_sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stripe_links (
            product_key TEXT PRIMARY KEY,
            payment_link TEXT,
            price_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS blocklist (
            email TEXT PRIMARY KEY,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    con.commit()
    return con

# ── Stripe ────────────────────────────────────────────────────────────────────
def get_or_create_stripe_link(con: sqlite3.Connection, product_key: str) -> str:
    """Gibt gecachten Stripe Payment Link zurück oder erstellt neuen."""
    row = con.execute(
        "SELECT payment_link FROM stripe_links WHERE product_key=?", (product_key,)
    ).fetchone()
    if row:
        return row[0]

    if not STRIPE_KEY:
        log.warning("STRIPE_SECRET_KEY fehlt — kein echter Checkout-Link")
        return f"https://buy.stripe.com/PLACEHOLDER_{product_key}"

    import stripe
    stripe.api_key = STRIPE_KEY
    prod_def = PRODUCTS[product_key]

    try:
        product = stripe.Product.create(
            name=prod_def["name"],
            description=prod_def["description"],
        )
        price_params = {
            "product": product.id,
            "unit_amount": prod_def["amount"],
            "currency": prod_def["currency"],
        }
        if prod_def["recurring"]:
            price_params["recurring"] = {"interval": prod_def["recurring"]}

        price = stripe.Price.create(**price_params)

        link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            after_completion={
                "type": "redirect",
                "redirect": {"url": "https://supermegabot-production.up.railway.app/danke"},
            },
        )
        url = link.url
        con.execute(
            "INSERT OR REPLACE INTO stripe_links VALUES (?,?,?,datetime('now'))",
            (product_key, url, price.id)
        )
        con.commit()
        log.info(f"Stripe Payment Link erstellt: {product_key} → {url}")
        return url

    except Exception as e:
        log.error(f"Stripe Fehler: {e}")
        return "https://buy.stripe.com/ERROR"

# ── Gmail IMAP ────────────────────────────────────────────────────────────────
def fetch_unread_emails() -> list:
    """Holt ungelesene Emails aus Gmail INBOX."""
    results = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("INBOX")

        # Suche alle ungelesenen Emails
        _, data = mail.search(None, "UNSEEN")
        msg_ids = data[0].split() if data[0] else []
        log.info(f"IMAP: {len(msg_ids)} ungelesene Emails")

        for msg_id in msg_ids[-50:]:  # max 50 auf einmal
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_header_value(msg.get("Subject", ""))
            sender  = msg.get("From", "")
            msg_uid = msg.get("Message-ID", f"no-id-{msg_id.decode()}")
            in_reply = msg.get("In-Reply-To", "") or msg.get("References", "")
            body    = extract_body(msg)

            list_unsub = msg.get("List-Unsubscribe", "")
            results.append({
                "imap_id": msg_id,
                "message_id": msg_uid.strip(),
                "sender": sender,
                "subject": subject,
                "body": body[:2000],
                "in_reply_to": in_reply,
                "is_reply": bool(in_reply),
                "is_marketing": bool(list_unsub),
            })

        mail.logout()
    except Exception as e:
        log.error(f"IMAP Fehler: {e}")
    return results

def decode_header_value(val: str) -> str:
    parts = email.header.decode_header(val)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)

def extract_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            body = str(msg.get_payload())
    return body

# ── Claude Klassifikation ─────────────────────────────────────────────────────
async def classify_reply(sender: str, subject: str, body: str) -> dict:
    """Claude Haiku klassifiziert die Email-Antwort."""
    if not ANTHROPIC_KEY:
        return {"classification": "UNKNOWN", "product_key": "AI_ACT_REPORT", "reason": "kein API Key"}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Du bist ein Sales-Assistent. Klassifiziere diese Email-Antwort:

Von: {sender}
Betreff: {subject}
Text: {body[:800]}

Antworte NUR mit JSON (kein Markdown):
{{
  "classification": "INTERESTED" | "QUESTION" | "UNSUBSCRIBE" | "NOT_INTERESTED" | "OUT_OF_OFFICE",
  "product_key": "AI_ACT_REPORT" | "AI_ACT_MONITORING" | "ZVG_BASIC" | "ZVG_PRO" | "HR_LEADS" | "INSOLVENZ_DEAL",
  "confidence": 0-100,
  "key_phrase": "kurzes Zitat aus der Email das die Klassifikation begründet",
  "reason": "1 Satz Erklärung"
}}

Produktwahl nach Kontext:
- Erwähnt AI Act / Compliance / EU-KI → AI_ACT_REPORT oder AI_ACT_MONITORING
- Erwähnt ZVG / Zwangsversteigerung / Immobilien → ZVG_BASIC oder ZVG_PRO
- Erwähnt Handelsregister / GmbH / Gründung → HR_LEADS
- Erwähnt Insolvenz / Factoring / Inkasso → INSOLVENZ_DEAL

INTERESTED = DIREKTE persönliche Antwort mit klar positivem Kaufsignal ("ja", "schicken Sie mir", "Angebot annehmen", "wie kann ich kaufen", "Preis nennen"). NUR wenn es eine echte menschliche Antwort ist.
QUESTION = Direkte persönliche Nachfrage ohne klares Kaufsignal.
UNSUBSCRIBE = Abmeldewunsch, "kein Interesse", "bitte keine weiteren Emails".
NOT_INTERESTED = Ablehnung ODER automatische Email, Newsletter, Sequenz-Email, Marketing-Email.
OUT_OF_OFFICE = Abwesenheitsnotiz oder Bounce.

KRITISCH: Wenn die Email automatisch aussieht (Newsletter, Sequenz, kein direkter Bezug auf ein Angebot von uns), IMMER NOT_INTERESTED zurückgeben. Im Zweifel NOT_INTERESTED."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # JSON extrahieren
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        log.error(f"Claude Klassifikation Fehler: {e}")

    return {"classification": "UNKNOWN", "product_key": "AI_ACT_REPORT", "confidence": 0, "reason": str(e)}

# ── Auto-Reply Email ──────────────────────────────────────────────────────────
def send_auto_reply(to_email: str, original_subject: str, product_key: str, stripe_link: str) -> bool:
    """Sendet automatische Antwort mit Stripe Payment Link."""
    prod = PRODUCTS.get(product_key, PRODUCTS["AI_ACT_REPORT"])
    preis = f"€{prod['amount']//100}"
    if prod["recurring"]:
        preis += "/Monat"

    subject = f"Re: {original_subject}"
    body = f"""Vielen Dank für Ihr Interesse!

Ich freue mich, dass {prod['name']} für Sie relevant ist.

Hier ist Ihr direkter Zugang:
━━━━━━━━━━━━━━━━━━━━━━━━━━
{prod['name']}
Preis: {preis}
━━━━━━━━━━━━━━━━━━━━━━━━━━
➤ Jetzt kaufen: {stripe_link}
━━━━━━━━━━━━━━━━━━━━━━━━━━

{prod['description']}

Nach Ihrer Zahlung erhalten Sie sofort Zugang. Bei Fragen stehe ich gerne zur Verfügung.

Mit freundlichen Grüßen
Rudolf Sarkany
AiiteC GmbH
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"]   = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)

        log.info(f"Auto-Reply gesendet an {to_email} — {product_key} ({stripe_link})")
        return True
    except Exception as e:
        log.warning(f"Auto-Reply Fehler ({to_email}): {e}")
        return False

# ── Telegram ──────────────────────────────────────────────────────────────────
async def telegram_alert(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    import aiohttp
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        log.error(f"Telegram Fehler: {e}")

def extract_email_addr(raw: str) -> str:
    match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', raw)
    return match.group() if match else raw

def is_bounce(sender: str, subject: str) -> bool:
    s = (sender + subject).lower()
    return any(x in s for x in ["mailer-daemon", "postmaster", "delivery status", "mail delivery failed", "undeliverable"])

def extract_bounced_recipient(body: str) -> str:
    """Extrahiert die fehlgeschlagene Empfänger-Adresse aus einem Bounce."""
    for pattern in [
        r'(?:Final-Recipient|Original-Recipient):[^\n]*?<?([\w.+-]+@[\w.-]+\.\w+)>?',
        r'(?:failed|rejected|unknown user)[^\n]*?([\w.+-]+@[\w.-]+\.\w+)',
        r'The following addresses? (?:had|has) (?:permanent|temporary) (?:fatal )?errors?[^\n]*\n\s*([\w.+-]+@[\w.-]+\.\w+)',
    ]:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            return m.group(1)
    # Fallback: erste Email-Adresse im Body die nicht mailer-daemon ist
    for match in re.finditer(r'[\w.+-]+@[\w.-]+\.\w+', body):
        addr = match.group()
        if "mailer-daemon" not in addr and "google" not in addr:
            return addr
    return ""

def is_outreach_related(subject: str, body: str) -> bool:
    """Grobe Prüfung ob Reply zu unseren Outreach-Emails gehört."""
    text = (subject + " " + body).lower()
    return any(kw in text for kw in OUTREACH_KEYWORDS)

# ── Hauptzyklus ───────────────────────────────────────────────────────────────
async def run_cycle(con: sqlite3.Connection):
    log.info("═══ Reply Monitor — Zyklus startet ═══")
    emails = fetch_unread_emails()

    new_interested = 0
    new_questions  = 0

    for em in emails:
        msg_id = em["message_id"]

        # Bereits verarbeitet?
        if con.execute("SELECT 1 FROM processed_messages WHERE message_id=?", (msg_id,)).fetchone():
            continue

        sender  = em["sender"]
        subject = em["subject"]
        body    = em["body"]
        email_addr = extract_email_addr(sender)

        # Blocklist?
        if con.execute("SELECT 1 FROM blocklist WHERE email=?", (email_addr,)).fetchone():
            log.info(f"Blocklist: {email_addr} ignoriert")
            continue

        # Marketing-/Newsletter-Emails sofort überspringen
        if em.get("is_marketing"):
            con.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, sender, subject, classification) VALUES (?,?,?,?)",
                (msg_id, sender, subject, "MARKETING")
            )
            con.commit()
            continue

        # Bounces direkt behandeln — echten Empfänger in Blocklist
        if is_bounce(sender, subject):
            bounced = extract_bounced_recipient(body)
            if bounced and bounced != email_addr:
                con.execute(
                    "INSERT OR IGNORE INTO blocklist (email, reason) VALUES (?,?)",
                    (bounced, f"Hard Bounce via mailer-daemon: {subject[:50]}")
                )
                con.commit()
                log.info(f"Bounce-Blocklist: {bounced}")
            con.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, sender, subject, classification) VALUES (?,?,?,?)",
                (msg_id, sender, subject, "BOUNCE")
            )
            con.commit()
            continue

        # Nur relevante Emails verarbeiten (Antworten ODER Outreach-Schlüsselwörter)
        if not em["is_reply"] and not is_outreach_related(subject, body):
            log.info(f"Nicht relevant: {subject[:50]}")
            con.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, sender, subject, classification) VALUES (?,?,?,?)",
                (msg_id, sender, subject, "IGNORED")
            )
            con.commit()
            continue

        log.info(f"Klassifiziere: {subject[:60]} von {email_addr}")
        result = await classify_reply(sender, subject, body)
        classification = result.get("classification", "UNKNOWN")
        product_key    = result.get("product_key", "AI_ACT_REPORT")
        key_phrase     = result.get("key_phrase", "")
        reason         = result.get("reason", "")

        log.info(f"→ {classification} | {product_key} | {reason}")

        stripe_link = ""
        reply_sent  = 0
        tg_sent     = 0

        if classification == "INTERESTED":
            stripe_link = get_or_create_stripe_link(con, product_key)
            sent = send_auto_reply(email_addr, subject, product_key, stripe_link)
            reply_sent = 1 if sent else 0

            prod = PRODUCTS.get(product_key, {})
            preis = f"€{prod.get('amount', 0)//100}"
            if prod.get("recurring"):
                preis += "/mo"

            tg_msg = (
                f"🔥 <b>HOT LEAD — Kaufinteresse!</b>\n\n"
                f"Von: {email_addr}\n"
                f"Betreff: {subject[:80]}\n"
                f"Produkt: {prod.get('name','?')} ({preis})\n"
                f"Zitat: <i>\"{key_phrase[:100]}\"</i>\n\n"
                f"✅ Auto-Reply mit Stripe-Link gesendet:\n{stripe_link}"
            )
            await telegram_alert(tg_msg)
            tg_sent = 1
            new_interested += 1

        elif classification == "QUESTION":
            tg_msg = (
                f"❓ <b>Frage von Lead — manuelle Antwort nötig</b>\n\n"
                f"Von: {email_addr}\n"
                f"Betreff: {subject[:80]}\n"
                f"Frage: <i>{body[:200]}</i>\n\n"
                f"Produkt-Kontext: {product_key}\n"
                f"→ Bitte selbst antworten: {email_addr}"
            )
            await telegram_alert(tg_msg)
            tg_sent = 1
            new_questions += 1

        elif classification == "UNSUBSCRIBE":
            con.execute(
                "INSERT OR IGNORE INTO blocklist (email, reason) VALUES (?,?)",
                (email_addr, f"Unsubscribe via Email: {subject[:50]}")
            )
            con.commit()
            log.info(f"Blocklist hinzugefügt: {email_addr}")

        elif classification == "OUT_OF_OFFICE":
            log.info(f"Out-of-Office ignoriert: {email_addr}")

        con.execute("""
            INSERT OR REPLACE INTO processed_messages
            (message_id, sender, subject, classification, product_key, stripe_link, reply_sent, telegram_sent)
            VALUES (?,?,?,?,?,?,?,?)
        """, (msg_id, sender, subject, classification, product_key, stripe_link, reply_sent, tg_sent))
        con.commit()

        await asyncio.sleep(2)

    log.info(f"═══ Fertig: {new_interested} Interessenten, {new_questions} Fragen ═══")

    if new_interested > 0 or new_questions > 0:
        summary = (
            f"📊 <b>Reply Monitor — Zyklus {datetime.now().strftime('%H:%M')}</b>\n"
            f"🔥 Interessenten: {new_interested}\n"
            f"❓ Fragen: {new_questions}"
        )
        await telegram_alert(summary)

# ── Daemon / CLI ──────────────────────────────────────────────────────────────
async def scheduler_loop():
    con = init_db()
    log.info("Reply Monitor gestartet — alle 15 Min prüfen")
    await telegram_alert(
        "🚀 <b>Reply Monitor gestartet</b>\n"
        "Prüfe alle 15 Min auf Antworten → Auto-Stripe-Reply aktiv."
    )

    while True:
        try:
            await run_cycle(con)
        except Exception as e:
            log.error(f"Zyklus-Fehler: {e}")
            await telegram_alert(f"⚠️ Reply Monitor Fehler: {e}")

        next_check = datetime.now().strftime("%H:%M")
        log.info(f"Nächste Prüfung in 15 Min ({next_check})")
        await asyncio.sleep(CHECK_INTERVAL)

async def run_now():
    con = init_db()
    await run_cycle(con)

if __name__ == "__main__":
    if "--now" in sys.argv:
        asyncio.run(run_now())
    else:
        asyncio.run(scheduler_loop())
