#!/usr/bin/env python3
"""
Outreach Engine — Automatisierte B2B-Kalt-Akquise
===================================================
Kombiniert Insolvenz Radar Leads mit personalisierten Nachrichten.

Flow:
  1. Holt Top-Leads aus Insolvenz Radar (Score 60+)
  2. Findet Steuerberater/Factoring-Firmen in der gleichen Region
  3. Generiert 10 personalisierte Nachrichten via Claude Haiku
  4. Sendet automatisch via Gmail (SMTP)
  5. Generiert LinkedIn-Nachrichten zum 1-Klick-Kopieren
  6. Trackt alles in SQLite (kein Doppel-Versand)

Targets:
  - Steuerberater (öffentliche Kanzlei-Emails via Google)
  - Factoring-Firmen (DE-weit, feste Ziel-Liste)
  - M&A-Berater / Insolvenzverwalter

Channels:
  - Email via Gmail (aiitecbuuss@gmail.com) — automatisch
  - LinkedIn Message — vorgeneriert, 1-Klick-Copy im Dashboard
  - Twitter DM — vorgeneriert template
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

log = logging.getLogger("OutreachEngine")

_BASE    = Path(__file__).parent.parent
_DB_PATH = _BASE / "data" / "outreach_engine.db"

# ── Env helpers ───────────────────────────────────────────────────────────────
def _gmail_user()     -> str: return os.getenv("GMAIL_USER_AIITEC", "aiitecbuuss@gmail.com")
def _gmail_pass()     -> str: return os.getenv("GMAIL_APP_PASSWORD_AIITEC", "")
def _gmail_user2()    -> str: return os.getenv("GMAIL_USER_BULLPOWER", "bullpowersrtkennels@gmail.com")
def _gmail_pass2()    -> str: return os.getenv("GMAIL_APP_PASSWORD_BULLPOWER", "")
def _tg_token()       -> str: return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
def _tg_chat()        -> str: return os.getenv("TELEGRAM_CHAT_ID", "")
def _dashboard_url()  -> str: return os.getenv("DASHBOARD_URL", "https://supermegabot-production.up.railway.app")

# ── Feste Ziel-Liste: Factoring & Inkasso DE ──────────────────────────────────
FACTORING_TARGETS = [
    {"name": "BFS finance GmbH", "email": "info@bfs-finance.de", "type": "Factoring"},
    {"name": "Deutsche Factoring Bank", "email": "info@deutsche-factoring.de", "type": "Factoring"},
    {"name": "Bibby Financial Services", "email": "info@bibbyfinancialservices.de", "type": "Factoring"},
    {"name": "Grenke Factoring", "email": "factoring@grenke.de", "type": "Factoring"},
    {"name": "Arvato Financial Solutions", "email": "kontakt@arvato-financial.de", "type": "Inkasso"},
    {"name": "Creditreform", "email": "info@creditreform.de", "type": "Kredit-Auskunft"},
    {"name": "GFKL Financial Services", "email": "info@gfkl.com", "type": "Inkasso"},
    {"name": "EOS Gruppe", "email": "info@eos-solutions.de", "type": "Inkasso"},
    {"name": "Coface Deutschland", "email": "info@coface.de", "type": "Kreditversicherung"},
    {"name": "Atradius", "email": "info@atradius.de", "type": "Kreditversicherung"},
]

# Öffentliche Steuerberater-Verbände & Kammern
STEUERBERATER_VERBÄNDE = [
    {"name": "Steuerberaterkammer München", "email": "info@stbk-muenchen.de", "type": "Verband"},
    {"name": "Steuerberaterkammer Berlin", "email": "info@stbk-berlin.de", "type": "Verband"},
    {"name": "BStBK", "email": "info@bstbk.de", "type": "Bundesverband"},
]

# ── DB ────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS outreach_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            target_name     TEXT NOT NULL,
            target_email    TEXT,
            target_type     TEXT,
            lead_uid        TEXT,
            lead_name       TEXT,
            lead_score      INTEGER,
            lead_branche    TEXT,
            lead_bundesland TEXT,
            channel         TEXT DEFAULT 'email',
            subject         TEXT,
            body_email      TEXT,
            body_linkedin   TEXT,
            body_twitter    TEXT,
            status          TEXT DEFAULT 'pending',
            sent_at         INTEGER,
            opened          INTEGER DEFAULT 0,
            replied         INTEGER DEFAULT 0,
            created_at      INTEGER,
            UNIQUE(target_email, lead_uid)
        );

        CREATE TABLE IF NOT EXISTS outreach_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT,
            generated   INTEGER DEFAULT 0,
            sent_email  INTEGER DEFAULT 0,
            sent_li     INTEGER DEFAULT 0,
            opened      INTEGER DEFAULT 0,
            replied     INTEGER DEFAULT 0
        );
        """)


# ── AI Nachrichts-Generator ───────────────────────────────────────────────────

async def generate_messages(
    target: Dict,
    lead: Dict,
) -> Dict:
    """Generiert personalisierte Outreach-Nachricht für ein Target + Lead."""
    import json as _json
    types = _json.loads(lead.get("lead_types", "[]"))
    lead_type = types[0] if types else "Steuerberater"
    dashboard = _dashboard_url()

    # Heuristik-Fallback (kein AI nötig)
    def _fallback() -> Dict:
        subject = (
            f"Insolvenz-Alert: {lead['debtor_name']} ({lead.get('bundesland','DE')}) — "
            f"Score {lead.get('score', 70)}/100"
        )
        body_email = f"""Guten Tag,

mein System hat heute eine neue Insolvenzbekanntmachung identifiziert, die für Ihre Arbeit als {target['type']} relevant sein könnte:

Schuldner:    {lead['debtor_name']}
Bundesland:   {lead.get('bundesland', '?')}
Branche:      {lead.get('branche', '?')}
Score:        {lead.get('score', 70)}/100
Insolvenzart: {lead.get('insolvency_type', 'Insolvenzeröffnung')}

Mein Tool "Insolvenz Radar Pro" scannt täglich das offizielle Insolvenzregister und bewertet jeden Eintrag automatisch nach Relevanz für Steuerberater, Factoring-Firmen und M&A-Berater.

Hätten Sie Interesse an einem kostenlosen 7-Tage-Test?

👉 {dashboard}/insolvenz-radar

Mit freundlichen Grüßen
Rudolf Sarkany
AiiteC GmbH
"""
        body_linkedin = (
            f"Hallo {target['name'].split()[0] if target['name'] else 'zusammen'},\n\n"
            f"mein Tool hat heute eine neue Insolvenz identifiziert, die für {target['type']} "
            f"interessant sein könnte: {lead['debtor_name']} in {lead.get('bundesland','?')} "
            f"(Branche: {lead.get('branche','?')}, Score {lead.get('score',70)}/100).\n\n"
            f"Ich entwickle Insolvenz Radar Pro — täglich automatische B2B-Leads aus dem "
            f"deutschen Insolvenzregister, kuratiert für {target['type']}.\n\n"
            f"Wäre ein 7-Tage-Test interessant? Keine Kreditkarte nötig. "
            f"Mehr: {dashboard}/insolvenz-radar"
        )
        body_twitter = (
            f"Hey! Ich tracke täglich neue Insolvenzen in DE — heute: {lead['debtor_name']} "
            f"in {lead.get('bundesland','?')}. Für {target['type']} oft ein Neukunde. "
            f"7-Tage-Test gratis: {dashboard}/insolvenz-radar"
        )[:280]
        return {
            "subject":       subject,
            "body_email":    body_email,
            "body_linkedin": body_linkedin,
            "body_twitter":  body_twitter,
        }

    prompt = f"""Schreibe eine professionelle, kurze Kalt-Akquise-Nachricht auf Deutsch.

Empfänger: {target['name']} ({target['type']})
Lead aus dem Insolvenzregister:
  - Schuldner: {lead['debtor_name']}
  - Bundesland: {lead.get('bundesland','?')}
  - Branche: {lead.get('branche','?')}
  - Score: {lead.get('score',70)}/100
  - Art: {lead.get('insolvency_type','Insolvenzeröffnung')}
  - AI-Hinweis: {lead.get('ai_summary','')}

Produkt: "Insolvenz Radar Pro" — täglich neue B2B-Leads aus dem deutschen Insolvenzregister,
automatisch bewertet. €29-199/Monat. URL: {dashboard}/insolvenz-radar

Regeln:
- Email: max 120 Wörter, professionell, konkreter Lead als Hook, 1 klarer CTA (7-Tage-Test)
- LinkedIn: max 80 Wörter, persönlicher Ton, kein "sehr geehrte", direkt zum Punkt
- Twitter: max 240 Zeichen, kurz + neugierig machend

Antworte als JSON:
{{
  "subject": "Email-Betreff (max 80 Zeichen, mit Lead-Name)",
  "body_email": "Email-Text",
  "body_linkedin": "LinkedIn-Nachricht",
  "body_twitter": "Twitter-DM"
}}"""

    try:
        from modules.ai_client import ai_complete
        text = await ai_complete(prompt, system="", max_tokens=600)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        log.debug("AI generate: %s", e)

    return _fallback()


# ── Email-Versand ─────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str, sender_idx: int = 0) -> bool:
    """Sendet via gmail_accounts — sender_idx 0=aiitec(5), 1=bullpower(3)."""
    from modules.email_guard import require_valid_email, register_sent
    ok_g, errs = require_valid_email(subject, body, to_email)
    if not ok_g:
        log.warning("EmailGuard blockiert outreach_engine [%s]: %s", to_email, errs)
        return False
    from modules.gmail_accounts import send_email as ga_send
    idx = 5 if sender_idx == 0 else 3
    html_body = body.replace("\n", "<br>")
    html = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px">
<p>{html_body}</p>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0">
<p style="font-size:12px;color:#999">Abmeldung: Antworten Sie mit "Abmeldung"</p>
</body></html>"""
    ok, via = ga_send(to_email, subject, body, html=html, account_index=idx)
    if not ok:
        ok, via = ga_send(to_email, subject, body, html=html)
    if ok:
        register_sent(to_email, subject, body)
        log.info("Email gesendet: %s → %s via %s", subject[:40], to_email, via)
    return ok


# ── Hauptfunktion: Outreach-Batch generieren & senden ────────────────────────

async def _sb_insert_lead_event(data: dict) -> None:
    """Schreibt ein Lead-Event in Supabase lead_events (fire-and-forget)."""
    import aiohttp as _aio
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY", "")
    auth_key = key or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not auth_key:
        log.debug("Supabase credentials fehlen — lead_event nicht gespeichert")
        return
    try:
        async with _aio.ClientSession() as s:
            await s.post(
                f"{url}/rest/v1/lead_events",
                json=data,
                headers={
                    "apikey": auth_key,
                    "Authorization": f"Bearer {auth_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                timeout=_aio.ClientTimeout(total=8),
            )
        log.debug("Supabase lead_event gespeichert: %s", data.get("event_type"))
    except Exception as e:
        log.debug("Supabase lead_event Fehler: %s", e)


async def generate_outreach_batch(
    auto_send_email: bool = True,
    max_targets: int = 10,
    min_lead_score: int = 60
) -> Dict:
    """
    Generiert und sendet 10 personalisierte Outreach-Nachrichten.
    Kombiniert Factoring-Targets + Top-Leads aus Insolvenz Radar.
    """
    init_db()

    # Top-Leads holen
    try:
        from modules.insolvenz_radar import get_leads
        leads = get_leads(min_score=min_lead_score, limit=20)
    except Exception as e:
        log.error("Keine Insolvenz-Leads: %s — kein Fake-Fallback", e)
        log.error("Keine Leads verfügbar — Insolvenz Radar zuerst ausführen")
        return {"ok": False, "error": "Keine Leads — erst Scan starten"}

    if not leads:
        return {"ok": False, "error": "Keine Leads im Insolvenz Radar — erst Scan starten"}

    # Targets zusammenstellen
    targets = FACTORING_TARGETS + STEUERBERATER_VERBÄNDE
    targets = targets[:max_targets]

    generated = 0
    sent      = 0
    skipped   = 0
    queue     = []

    for i, target in enumerate(targets):
        lead = leads[i % len(leads)]  # rotiere durch leads

        # Bereits kontaktiert?
        with _db() as conn:
            exists = conn.execute(
                "SELECT id FROM outreach_queue WHERE target_email=? AND lead_uid=?",
                (target.get("email", ""), lead.get("uid", ""))
            ).fetchone()
            if exists:
                skipped += 1
                continue

        # Nachrichten generieren
        msgs = await generate_messages(target, lead)
        await asyncio.sleep(0.3)

        # In Queue speichern
        now = int(time.time())
        try:
            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO outreach_queue
                       (target_name, target_email, target_type, lead_uid, lead_name,
                        lead_score, lead_branche, lead_bundesland, channel,
                        subject, body_email, body_linkedin, body_twitter, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        target["name"], target.get("email", ""), target["type"],
                        lead.get("uid", ""), lead.get("debtor_name", ""),
                        lead.get("score", 0), lead.get("branche", ""),
                        lead.get("bundesland", ""), "email",
                        msgs["subject"], msgs["body_email"],
                        msgs["body_linkedin"], msgs["body_twitter"],
                        now
                    )
                )
            generated += 1
        except Exception as e:
            log.debug("Queue insert: %s", e)
            continue

        queue.append({
            "target":      target["name"],
            "email":       target.get("email", ""),
            "lead":        lead.get("debtor_name", ""),
            "score":       lead.get("score", 0),
            "subject":     msgs["subject"],
            "linkedin_msg": msgs["body_linkedin"],
        })

        # Email auto-senden
        if auto_send_email and target.get("email"):
            ok = send_email(target["email"], msgs["subject"], msgs["body_email"])
            if ok:
                sent += 1
                with _db() as conn:
                    conn.execute(
                        "UPDATE outreach_queue SET status='sent', sent_at=? WHERE target_email=? AND lead_uid=?",
                        (now, target["email"], lead.get("uid", ""))
                    )
                # Supabase CRM: Lead-Event eintragen
                asyncio.create_task(_sb_insert_lead_event({
                    "event_type": "outreach_email_sent",
                    "source":     "outreach_engine",
                    "email":      target.get("email", ""),
                    "company":    target.get("name", ""),
                    "product_id": lead.get("uid", ""),
                    "notes":      msgs.get("subject", "")[:255],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }))
                await asyncio.sleep(3)  # Anti-Spam: 3s zwischen Emails
            else:
                with _db() as conn:
                    conn.execute(
                        "UPDATE outreach_queue SET status='error' WHERE target_email=? AND lead_uid=?",
                        (target["email"], lead.get("uid", ""))
                    )

    # Telegram-Report
    await _tg_report(generated, sent, skipped, queue)

    return {
        "ok":        True,
        "generated": generated,
        "sent":      sent,
        "skipped":   skipped,
        "queue":     queue,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def _tg_report(generated: int, sent: int, skipped: int, queue: List[Dict]):
    token = _tg_token()
    chat  = _tg_chat()
    if not token or not chat:
        return
    lines = [
        f"📧 <b>Outreach Engine — Batch fertig</b>",
        f"✅ Generiert: {generated} | 📤 Gesendet: {sent} | ⏭ Übersprungen: {skipped}\n",
    ]
    for q in queue[:5]:
        lines.append(f"• <b>{q['target']}</b> → Lead: {q['lead']} (Score {q['score']})")
    if len(queue) > 5:
        lines.append(f"<i>... und {len(queue)-5} weitere</i>")
    lines.append(f"\n👉 Dashboard: /outreach")
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            timeout=aiohttp.ClientTimeout(total=10)
        ) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": "\n".join(lines),
                      "parse_mode": "HTML", "disable_web_page_preview": True}
            )
    except Exception as e:
        log.debug("TG report: %s", e)


# ── Status & Queue API ────────────────────────────────────────────────────────

def get_status() -> Dict:
    init_db()
    with _db() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM outreach_queue").fetchone()[0]
        sent    = conn.execute("SELECT COUNT(*) FROM outreach_queue WHERE status='sent'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM outreach_queue WHERE status='pending'").fetchone()[0]
        errors  = conn.execute("SELECT COUNT(*) FROM outreach_queue WHERE status='error'").fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM outreach_queue WHERE created_at > ?",
            (int(time.time()) - 86400,)
        ).fetchone()[0]
    return {
        "ok": True, "total": total, "sent": sent,
        "pending": pending, "errors": errors, "today": today,
    }


def get_queue(status: str = "", limit: int = 50) -> List[Dict]:
    init_db()
    where  = "WHERE status=?" if status else ""
    params = [status, limit] if status else [limit]
    with _db() as conn:
        rows = conn.execute(
            f"SELECT * FROM outreach_queue {where} ORDER BY lead_score DESC, created_at DESC LIMIT ?",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def mark_replied(outreach_id: int) -> Dict:
    init_db()
    with _db() as conn:
        conn.execute("UPDATE outreach_queue SET replied=1, status='replied' WHERE id=?", (outreach_id,))
    return {"ok": True}


init_db()
