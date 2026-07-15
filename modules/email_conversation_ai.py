#!/usr/bin/env python3
"""
EmailConversationAI — Vollautomatisches KI-E-Mail-Gesprächssystem.

Liest ungelesene Emails per IMAP, klassifiziert sie mit Claude,
generiert lebendige deutsche Antworten und sendet sie per SMTP.
Thread-Tracking läuft in SQLite (data/email_conversations.db).
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import json
import logging
import os
import re
import smtplib
import sqlite3
import ssl
from datetime import date, datetime, timezone
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.ai_client import ai_complete

log = logging.getLogger("EmailConversationAI")

# ── Pfade ────────────────────────────────────────────────────────────────────
_DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
_DB_PATH  = _DATA_DIR / "email_conversations.db"

# ── Umgebungsvariablen ───────────────────────────────────────────────────────
_RAILWAY_DOMAIN  = lambda: os.getenv("RAILWAY_PUBLIC_DOMAIN", "supermegabot-production.up.railway.app")
_IMAP_HOST       = "imap.gmail.com"
_IMAP_PORT       = 993
_SMTP_HOST       = "smtp.gmail.com"
_SMTP_PORT       = 587

# Produktlinks
_LINKS = {
    "shop":     "https://ineedit.com.co",
    "shopify":  "https://shopify-brutal-tuning.vercel.app",
    "ai_tools": "https://bullpower-hub.vercel.app",
    "telegram": "https://bullpower-steuercockpit.netlify.app",
    "calendly": "https://calendly.com/bullpower/demo",
}

# ── Kategorien ───────────────────────────────────────────────────────────────
EMAIL_CATEGORIES = [
    "new_lead",
    "product_inquiry",
    "support_request",
    "complaint",
    "partnership",
    "spam",
    "unsubscribe",
    "demo_request",
    "order_status",
]

# ── Systemanweisung für Claude ────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "Du bist Rudolf Sarkany, Gründer und Geschäftsführer von AiiteC — "
    "einem KI-Automatisierungs-Unternehmen. Schreibe eine natürliche, lebendige Email-Antwort "
    "auf Deutsch. Sei freundlich aber professionell. Zeige echtes Interesse am Anliegen des "
    "Kunden. Keine Standard-Floskeln, keine steifen Formulierungen. Maximum 200 Wörter."
)

# ── Kategorie-Prompts ─────────────────────────────────────────────────────────
_CATEGORY_PROMPTS: Dict[str, str] = {
    "new_lead": (
        "Schreibe eine herzliche Willkommens-Antwort für einen potenziellen Neukunden. "
        "Biete einen kostenlosen Demo-Call an und erkläre kurz was BullPower macht. "
        "Erwähne unsere KI-Automatisierungslösungen. Calendly-Link zum Buchen: {calendly}."
    ),
    "product_inquiry": (
        "Beantworte die Produktfrage detailliert und informativ. "
        "Nenne konkrete Vorteile unserer Lösungen. Erwähne relevante Links: "
        "Shop {shop}, AI Tools {ai_tools}, Shopify SaaS {shopify}. "
        "Lade zum Demo-Call ein: {calendly}."
    ),
    "support_request": (
        "Antworte empathisch und lösungsorientiert auf die Support-Anfrage. "
        "Zeige Verständnis für das Problem und biete konkrete Hilfe an. "
        "Falls nötig, eskaliere an unser Tech-Team. Sei beruhigend und kompetent."
    ),
    "complaint": (
        "Antworte aufrichtig entschuldigend auf die Beschwerde. "
        "Zeige echtes Verständnis und biete aktive Hilfe an. "
        "Als Entschädigung einen 10% Rabattcode: SORRY10. "
        "Erkläre wie wir das Problem schnell lösen werden."
    ),
    "partnership": (
        "Antworte professionell auf die B2B-Partnerschaftsanfrage. "
        "Zeige echtes Interesse und frage nach weiteren Details zum Unternehmen, "
        "den Zielen der Zusammenarbeit und dem gewünschten Zeitrahmen. "
        "Schlage ein erstes Kennenlern-Gespräch vor: {calendly}."
    ),
    "demo_request": (
        "Bestätige die Demo-Anfrage begeistert. "
        "Erkläre kurz was die Demo zeigt (echte KI-Automatisierung, Live-System). "
        "Sende den Calendly-Link zum direkten Buchen: {calendly}. "
        "Frage nach verfügbaren Zeiten falls Calendly nicht passt."
    ),
    "order_status": (
        "Antworte verständnisvoll auf die Bestellstatus-Anfrage. "
        "Erkläre dass wir die Bestellung prüfen und bitte um die Bestellnummer falls nicht angegeben. "
        "Verspreche schnellstmögliche Rückmeldung."
    ),
    "spam":        "ignore",
    "unsubscribe": "unsubscribe",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _decode_header_value(raw: Optional[str]) -> str:
    """Dekodiert MIME-encoded E-Mail-Header sicher."""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded).strip()


def _extract_body(msg: email.message.Message) -> str:
    """Extrahiert den reinen Text-Body aus einer E-Mail."""
    body_parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition") or "")
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_parts.append(part.get_payload(decode=True).decode(charset, errors="replace"))
                except Exception:
                    body_parts.append("")
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            body_parts.append(msg.get_payload(decode=True).decode(charset, errors="replace"))
        except Exception:
            body_parts.append("")
    text = "\n".join(body_parts).strip()
    # Kürzen auf 2000 Zeichen für Claude
    return text[:2000]


def _detect_language(text: str) -> str:
    """Grobe Spracherkennung Deutsch vs. Englisch."""
    german_words = {"ich", "du", "wir", "haben", "ist", "das", "der", "die", "und",
                    "ein", "eine", "nicht", "für", "mit", "auf", "bitte", "danke",
                    "können", "möchte", "würde", "sie", "ihr", "hallo", "guten"}
    words = set(re.findall(r"\b[a-zA-ZäöüÄÖÜß]{3,}\b", text.lower()))
    german_hits = len(words & german_words)
    return "de" if german_hits >= 2 else "en"


def _extract_name_from_email(from_str: str) -> str:
    """Extrahiert den Vornamen aus dem From-Header."""
    name, addr = parseaddr(from_str)
    name = name.strip()
    if name:
        return name.split()[0].capitalize()
    # Fallback: Erster Teil der E-Mail-Adresse
    local = addr.split("@")[0] if "@" in addr else addr
    return local.split(".")[0].capitalize()


def _init_db() -> None:
    """Erstellt SQLite-Tabellen falls nicht vorhanden."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_threads (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id    TEXT,
                thread_id     TEXT,
                sender_email  TEXT,
                sender_name   TEXT,
                subject       TEXT,
                category      TEXT,
                status        TEXT DEFAULT 'received',
                received_at   TEXT,
                replied_at    TEXT,
                account_used  TEXT
            );
            CREATE TABLE IF NOT EXISTS auto_replies (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id     TEXT,
                reply_subject TEXT,
                reply_body    TEXT,
                sent_at       TEXT,
                smtp_user     TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _db_insert_thread(
    message_id: str, thread_id: str, sender_email: str, sender_name: str,
    subject: str, category: str, account_used: str
) -> None:
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        # Nur einfügen wenn message_id noch nicht existiert
        existing = conn.execute(
            "SELECT id FROM email_threads WHERE message_id = ?", (message_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO email_threads
                   (message_id, thread_id, sender_email, sender_name, subject, category, status, received_at, account_used)
                   VALUES (?, ?, ?, ?, ?, ?, 'received', ?, ?)""",
                (message_id, thread_id, sender_email, sender_name, subject, category,
                 datetime.now(timezone.utc).isoformat(), account_used)
            )
            conn.commit()
    finally:
        conn.close()


def _db_mark_replied(message_id: str, thread_id: str, reply_subject: str,
                      reply_body: str, smtp_user: str) -> None:
    conn = sqlite3.connect(str(_DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "UPDATE email_threads SET status='replied', replied_at=? WHERE message_id=?",
            (now, message_id)
        )
        conn.execute(
            """INSERT INTO auto_replies (thread_id, reply_subject, reply_body, sent_at, smtp_user)
               VALUES (?, ?, ?, ?, ?)""",
            (thread_id, reply_subject, reply_body, now, smtp_user)
        )
        conn.commit()
    finally:
        conn.close()


def _already_replied(message_id: str) -> bool:
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        row = conn.execute(
            "SELECT status FROM email_threads WHERE message_id = ?", (message_id,)
        ).fetchone()
        return bool(row and row[0] == "replied")
    finally:
        conn.close()


# ── Kern-Klasse ───────────────────────────────────────────────────────────────

class EmailConversationAI:
    """Vollautomatisches KI-E-Mail-Gesprächssystem."""

    def __init__(self) -> None:
        _init_db()

    # ── IMAP-Hilfsmethode ─────────────────────────────────────────────────────

    def _imap_fetch(
        self, host: str, port: int, user: str, password: str, max_msgs: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Verbindet per IMAP4_SSL, liest ungelesene Nachrichten aus INBOX,
        parst Headers + Body, markiert als SEEN. Gibt Liste von Dicts zurück.
        """
        results: List[Dict[str, Any]] = []
        password = (password or "").replace(" ", "")
        if not password:
            log.warning("IMAP %s: kein Passwort konfiguriert", user)
            return results
        try:
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(user, password)
            mail.select("INBOX")
            _, search_data = mail.search(None, "UNSEEN")
            uid_list = search_data[0].split() if search_data[0] else []
            # Neueste zuerst, maximal max_msgs
            uid_list = uid_list[-max_msgs:]

            for uid in uid_list:
                try:
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw_bytes = msg_data[0][1]
                    msg = email.message_from_bytes(raw_bytes)

                    subject   = _decode_header_value(msg.get("Subject", ""))
                    from_raw  = _decode_header_value(msg.get("From", ""))
                    message_id = msg.get("Message-ID", f"uid-{uid.decode()}@imap").strip()
                    date_str  = msg.get("Date", "")
                    references = msg.get("References", "")
                    in_reply_to = msg.get("In-Reply-To", "")
                    thread_id = (references.split()[0] if references.split()
                                 else (in_reply_to or message_id))

                    _, addr = parseaddr(from_raw)
                    from_name = _extract_name_from_email(from_raw)
                    body_text = _extract_body(msg)

                    results.append({
                        "message_id":  message_id,
                        "thread_id":   thread_id.strip(),
                        "subject":     subject,
                        "from_raw":    from_raw,
                        "from_email":  addr.lower().strip(),
                        "from_name":   from_name,
                        "body_text":   body_text,
                        "date":        date_str,
                        "language":    _detect_language(body_text),
                    })
                    # Als gelesen markieren
                    mail.store(uid, "+FLAGS", "\\Seen")
                except Exception as e:
                    log.warning("IMAP fetch uid %s: %s", uid, e)

            try:
                mail.logout()
            except Exception:
                pass

        except imaplib.IMAP4.error as e:
            log.error("IMAP Login-Fehler %s: %s", user, e)
        except Exception as e:
            log.error("IMAP-Fehler %s: %s", user, e)

        return results

    # ── Öffentliche API ───────────────────────────────────────────────────────

    async def read_inbox(
        self, account_user: str, account_pass: str, max_messages: int = 50
    ) -> List[Dict[str, Any]]:
        """Liest IMAP-Posteingang asynchron (läuft in Thread-Pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._imap_fetch, _IMAP_HOST, _IMAP_PORT,
            account_user, account_pass, max_messages
        )

    async def classify_email(self, email_dict: Dict[str, Any]) -> str:
        """Klassifiziert eine E-Mail via KI. Gibt eine Kategorie zurück."""
        subject   = email_dict.get("subject", "")
        body      = email_dict.get("body_text", "")[:800]
        from_addr = email_dict.get("from_email", "")

        classify_prompt = (
            f"Klassifiziere diese eingehende E-Mail in GENAU EINE der folgenden Kategorien:\n"
            f"{', '.join(EMAIL_CATEGORIES)}\n\n"
            f"Betreff: {subject}\n"
            f"Von: {from_addr}\n"
            f"Inhalt: {body}\n\n"
            f"Antworte NUR mit dem Kategorie-Namen, ohne Erklärung."
        )

        try:
            raw = await ai_complete(
                classify_prompt,
                system="Du bist ein E-Mail-Klassifizierungs-Assistent. Antworte immer nur mit einem Wort.",
                max_tokens=20,
            )
            raw = raw.strip().lower()
            # Sicherheitscheck: muss eine valide Kategorie sein
            for cat in EMAIL_CATEGORIES:
                if cat in raw:
                    return cat
            log.warning("KI lieferte unbekannte Kategorie: %r — Fallback", raw)
        except Exception as e:
            log.error("classify error: %s", e)

        return self._fallback_classify(email_dict)

    def _fallback_classify(self, email_dict: Dict[str, Any]) -> str:
        """Regelbasierte Fallback-Klassifizierung ohne KI."""
        text = (email_dict.get("subject", "") + " " + email_dict.get("body_text", "")).lower()
        if any(w in text for w in ["unsubscribe", "abmelden", "austragen", "opt-out"]):
            return "unsubscribe"
        if any(w in text for w in ["demo", "vorführung", "kennenlernen"]):
            return "demo_request"
        if any(w in text for w in ["beschwerde", "complaint", "ärgerlich", "enttäuscht", "skandal"]):
            return "complaint"
        if any(w in text for w in ["partner", "kooperation", "zusammenarbeit", "b2b"]):
            return "partnership"
        if any(w in text for w in ["bestellung", "order", "tracking", "versand", "lieferung"]):
            return "order_status"
        if any(w in text for w in ["preis", "price", "kosten", "angebot", "pricing"]):
            return "product_inquiry"
        if any(w in text for w in ["hilfe", "support", "problem", "fehler", "funktioniert nicht"]):
            return "support_request"
        if any(w in text for w in ["viagra", "casino", "lottery", "winner", "claim"]):
            return "spam"
        return "new_lead"

    async def generate_reply(self, email_dict: Dict[str, Any], email_type: str) -> Optional[str]:
        """Generiert eine KI-Antwort basierend auf Kategorie. Gibt None zurück für spam/ignore."""
        if email_type == "spam":
            return None
        if email_type == "unsubscribe":
            return self._unsubscribe_response(email_dict)

        category_prompt_tpl = _CATEGORY_PROMPTS.get(email_type, _CATEGORY_PROMPTS["new_lead"])
        category_prompt = category_prompt_tpl.format(**_LINKS)

        sender_name  = email_dict.get("from_name", "")
        sender_email = email_dict.get("from_email", "")
        subject      = email_dict.get("subject", "")
        body         = email_dict.get("body_text", "")[:600]
        language     = email_dict.get("language", "de")
        railway_domain = _RAILWAY_DOMAIN()
        unsubscribe_url = f"https://{railway_domain}/api/unsubscribe?email={sender_email}"

        lang_hint = "" if language == "de" else "Schreibe auf Englisch, da der Sender auf Englisch geschrieben hat."

        user_prompt = (
            f"Sender: {sender_name} <{sender_email}>\n"
            f"Betreff: {subject}\n"
            f"Nachricht:\n{body}\n\n"
            f"Aufgabe: {category_prompt}\n"
            f"{lang_hint}\n\n"
            f"Unterschreibe mit: 'Liebe Grüße, Rudolf Sarkany | AiiteC'\n"
            f"Füge am Ende einen unauffälligen Abmeldelink ein: {unsubscribe_url}\n"
            f"Beginne mit persönlicher Anrede an {sender_name or 'den Sender'}."
        )

        try:
            text = await ai_complete(user_prompt, system=_SYSTEM_PROMPT, max_tokens=500)
            if text:
                return text.strip()
        except Exception as e:
            log.error("generate_reply error: %s", e)

        return None

    def _unsubscribe_response(self, email_dict: Dict[str, Any]) -> str:
        """Generiert eine DSGVO-konforme Abmelde-Bestätigung."""
        name = email_dict.get("from_name", "")
        greeting = f"Hallo {name}," if name else "Hallo,"
        return (
            f"{greeting}\n\n"
            "vielen Dank für deine Nachricht. Wir haben deine Abmeldeanfrage erhalten "
            "und werden deine E-Mail-Adresse innerhalb von 48 Stunden aus allen unseren "
            "Mailinglisten entfernen.\n\n"
            "Solltest du in Zukunft wieder von uns hören wollen, kannst du dich jederzeit "
            "neu anmelden.\n\n"
            "Alles Gute,\nRudolf Sarkany | AiiteC"
        )

    def _persist_unsubscribe(self, email_addr: str) -> None:
        """Schreibt Abmeldung in alle bekannten Opt-out-Listen (unified unsubscribe)."""
        email_addr = (email_addr or "").lower().strip()
        if not email_addr or "@" not in email_addr:
            return
        # 1. mass_outreach_1000 — primäres Opt-out-System
        try:
            from modules.mass_outreach_1000 import handle_unsubscribe as _mo_unsub
            _mo_unsub(email_addr)
        except Exception as exc:
            log.warning("mass_outreach_1000 unsubscribe error: %s", exc)
        # 2. Lokale email_conversations.db
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.execute(
                "UPDATE email_threads SET status='unsubscribed' WHERE sender_email=?",
                (email_addr,)
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            log.warning("email_conversations.db unsubscribe error: %s", exc)
        # 3. email_revenue.db — ere_sends Blacklist
        try:
            _rev_db = _DATA_DIR / "email_revenue.db"
            if _rev_db.exists():
                conn2 = sqlite3.connect(str(_rev_db))
                conn2.execute("""
                    CREATE TABLE IF NOT EXISTS ere_unsubscribes (
                        email TEXT PRIMARY KEY,
                        unsubscribed_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                conn2.execute(
                    "INSERT OR IGNORE INTO ere_unsubscribes (email) VALUES (?)", (email_addr,)
                )
                conn2.commit()
                conn2.close()
        except Exception as exc:
            log.warning("email_revenue.db unsubscribe error: %s", exc)
        log.info("Unsubscribe persistiert für: %s", email_addr)

    async def send_reply(
        self,
        original_email: Dict[str, Any],
        reply_text: str,
        smtp_user: str,
        smtp_pass: str,
    ) -> bool:
        """Sendet eine E-Mail-Antwort per SMTP/TLS. Gibt True bei Erfolg zurück."""
        smtp_pass = (smtp_pass or "").replace(" ", "")
        if not smtp_pass:
            log.error("SMTP %s: kein Passwort", smtp_user)
            return False

        to_addr  = original_email.get("from_email", "")
        subject  = original_email.get("subject", "")
        msg_id   = original_email.get("message_id", "")

        if not to_addr:
            log.error("send_reply: kein Empfänger")
            return False

        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = reply_subject
        msg["From"]    = smtp_user
        msg["To"]      = to_addr
        if msg_id:
            msg["In-Reply-To"] = msg_id
            msg["References"]  = msg_id
        msg["Date"] = email.utils.formatdate(localtime=True)

        msg.attach(MIMEText(reply_text, "plain", "utf-8"))

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, self._smtp_send, smtp_user, smtp_pass, to_addr, msg
            )
            log.info("Reply gesendet an %s via %s", to_addr, smtp_user)
            return True
        except Exception as e:
            log.error("SMTP-Fehler: %s", e)
            return False

    def _smtp_send(self, smtp_user: str, smtp_pass: str, to_addr: str, msg: MIMEMultipart) -> None:
        """Blockierender SMTP-Versand (läuft in Thread-Pool)."""
        context = ssl.create_default_context()
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_addr], msg.as_string())

    async def run_full_cycle(
        self, target_accounts: Optional[List[Tuple[str, str]]] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Vollständiger Zyklus: IMAP lesen → klassifizieren → Antwort generieren → senden.

        Args:
            target_accounts: Liste von (smtp_user, smtp_pass) Tupeln.
                             Wenn None, werden Standard-Konten aus .env geladen.
            dry_run: Wenn True, werden Antworten generiert aber NICHT gesendet.

        Returns:
            Dict mit Statistiken: emails_processed, replies_sent, categories, skipped
        """
        if target_accounts is None:
            target_accounts = self._load_default_accounts()

        stats: Dict[str, Any] = {
            "emails_processed": 0,
            "replies_sent": 0,
            "skipped": 0,
            "errors": 0,
            "categories": {},
            "dry_run": dry_run,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for smtp_user, smtp_pass in target_accounts:
            if not smtp_user or not smtp_pass:
                continue

            log.info("Verarbeite Konto: %s", smtp_user)
            emails = await self.read_inbox(smtp_user, smtp_pass, max_messages=30)
            log.info("  %d neue Emails gefunden", len(emails))

            for em in emails:
                msg_id = em.get("message_id", "")
                stats["emails_processed"] += 1

                # Schon beantwortet?
                if _already_replied(msg_id):
                    stats["skipped"] += 1
                    continue

                # Klassifizieren
                try:
                    category = await self.classify_email(em)
                except Exception as e:
                    log.error("Klassifizierung fehlgeschlagen: %s", e)
                    category = "new_lead"
                    stats["errors"] += 1

                stats["categories"][category] = stats["categories"].get(category, 0) + 1

                # Thread in DB speichern
                _db_insert_thread(
                    message_id=msg_id,
                    thread_id=em.get("thread_id", msg_id),
                    sender_email=em.get("from_email", ""),
                    sender_name=em.get("from_name", ""),
                    subject=em.get("subject", ""),
                    category=category,
                    account_used=smtp_user,
                )

                # Spam überspringen
                if category == "spam":
                    log.info("  [SPAM] ignoriert: %s", em.get("subject", "")[:50])
                    stats["skipped"] += 1
                    continue

                # Antwort generieren
                try:
                    reply_text = await self.generate_reply(em, category)
                except Exception as e:
                    log.error("Reply-Generierung fehlgeschlagen: %s", e)
                    reply_text = None
                    stats["errors"] += 1

                # Unsubscribe in DB persistieren (DSGVO) — auch wenn kein Reply gesendet wird
                if category == "unsubscribe":
                    self._persist_unsubscribe(em.get("from_email", ""))

                if not reply_text:
                    stats["skipped"] += 1
                    continue

                if dry_run:
                    log.info(
                        "  [DRY-RUN] Antwort für %s (%s):\n%s",
                        em.get("from_email"), category, reply_text[:200]
                    )
                    stats["replies_sent"] += 1
                    continue

                # Antwort senden
                sent = await self.send_reply(em, reply_text, smtp_user, smtp_pass)
                if sent:
                    stats["replies_sent"] += 1
                    reply_subject = em.get("subject", "")
                    if not reply_subject.lower().startswith("re:"):
                        reply_subject = f"Re: {reply_subject}"
                    _db_mark_replied(
                        message_id=msg_id,
                        thread_id=em.get("thread_id", msg_id),
                        reply_subject=reply_subject,
                        reply_body=reply_text,
                        smtp_user=smtp_user,
                    )
                else:
                    stats["errors"] += 1

                # Kurze Pause zwischen Emails um Rate-Limits zu vermeiden
                await asyncio.sleep(1.5)

        log.info("Zyklus abgeschlossen: %s", stats)
        return stats

    def _load_default_accounts(self) -> List[Tuple[str, str]]:
        """Lädt Standard-E-Mail-Konten aus Umgebungsvariablen."""
        accounts: List[Tuple[str, str]] = []

        # Primäre Aliase
        alias_map = [
            ("GMAIL_USER_AIITEC",     "GMAIL_APP_PASSWORD_AIITEC"),
            ("GMAIL_USER_BULLPOWER",  "GMAIL_APP_PASSWORD_BULLPOWER"),
            ("GMAIL_USER_1",          "GMAIL_APP_PASSWORD_1"),
            ("GMAIL_USER_2",          "GMAIL_APP_PASSWORD_2"),
            ("GMAIL_USER_3",          "GMAIL_APP_PASSWORD_3"),
            ("GMAIL_USER_5",          "GMAIL_APP_PASSWORD_5"),
            ("GMAIL_USER_6",          "GMAIL_APP_PASSWORD_6"),
            ("GMAIL_USER_7",          "GMAIL_APP_PASSWORD_7"),
            ("GMAIL_USER_8",          "GMAIL_APP_PASSWORD_8"),
            ("GMAIL_USER",            "GMAIL_APP_PASSWORD"),
        ]
        seen_users: set = set()
        for user_key, pass_key in alias_map:
            user = os.getenv(user_key, "")
            pw   = os.getenv(pass_key, "")
            if user and pw and user not in seen_users:
                accounts.append((user, pw))
                seen_users.add(user)

        if not accounts:
            log.warning("Keine Gmail-Konten in .env konfiguriert")
        return accounts

    def get_status(self) -> Dict[str, Any]:
        """Gibt Statistiken für heute zurück."""
        today = date.today().isoformat()
        conn = sqlite3.connect(str(_DB_PATH))
        try:
            emails_today = conn.execute(
                "SELECT COUNT(*) FROM email_threads WHERE received_at LIKE ?",
                (f"{today}%",)
            ).fetchone()[0]

            replied_today = conn.execute(
                "SELECT COUNT(*) FROM email_threads WHERE replied_at LIKE ?",
                (f"{today}%",)
            ).fetchone()[0]

            cat_rows = conn.execute(
                """SELECT category, COUNT(*) FROM email_threads
                   WHERE received_at LIKE ? GROUP BY category""",
                (f"{today}%",)
            ).fetchall()

            acc_rows = conn.execute(
                "SELECT DISTINCT account_used FROM email_threads WHERE received_at LIKE ?",
                (f"{today}%",)
            ).fetchall()

            return {
                "emails_today":   emails_today,
                "replied_today":  replied_today,
                "categories":     {row[0]: row[1] for row in cat_rows},
                "accounts_active": [row[0] for row in acc_rows],
                "db_path":         str(_DB_PATH),
                "date":            today,
            }
        finally:
            conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

async def _async_main(args: Any) -> None:
    ai = EmailConversationAI()

    if args.status:
        status = ai.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    if args.cycle or args.dry_run:
        target_accounts = None
        if args.account:
            parts = args.account.split(":")
            if len(parts) == 2:
                target_accounts = [(parts[0], parts[1])]
            else:
                print("Fehler: --account muss im Format user@gmail.com:PASSWORT sein")
                return

        result = await ai.run_full_cycle(
            target_accounts=target_accounts,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Standardfall: Status anzeigen
    status = ai.get_status()
    print("EmailConversationAI Status:")
    print(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="EmailConversationAI — Vollautomatisches KI-E-Mail-System"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Zeigt heutige Statistiken (Emails, Antworten, Kategorien)",
    )
    parser.add_argument(
        "--cycle",
        action="store_true",
        help="Führt einen vollständigen Lese-Klassifizier-Antwort-Zyklus durch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Generiert Antworten aber sendet sie NICHT (nur Ausgabe in Konsole)",
    )
    parser.add_argument(
        "--account",
        default=None,
        metavar="USER:PASS",
        help="Einzelnes Konto im Format user@gmail.com:app_passwort (überschreibt .env)",
    )

    cli_args = parser.parse_args()
    asyncio.run(_async_main(cli_args))
