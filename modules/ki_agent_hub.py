"""
KI-Agent Hub — Autonome Geschäftsagenten
=========================================
SalesAgent    → Lead → Nurture → Close → Upsell (SMS/Voice/Email)
SupportAgent  → Kunden-Anfragen, Bestellstatus, Reklamationen
ResearchAgent → Wettbewerber-Monitoring, Trends, Produkt-Chancen
GrowthAgent   → Conversion-Optimierung, A/B-Tests, Preis-Analyse

Telegram-Befehle:
  /sales_agent   /support_agent  /research_agent  /growth_agent
  /ki_agents     /ki_agent_status

Scheduler-Tasks:
  task_ki_sales    (alle 30min)
  task_ki_support  (alle 15min)
  task_ki_research (alle 6h)
  task_ki_growth   (alle 2h)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("KIAgentHub")

# ─── Credentials ──────────────────────────────────────────────────────────────
TELEGRAM_BOT     = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN_1", "")
TELEGRAM_CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
SHOPIFY_DOMAIN   = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_TOKEN    = os.getenv("SHOPIFY_ADMIN_API_TOKEN", "")
SHOPIFY_VERSION  = os.getenv("SHOPIFY_API_VERSION", "2024-01")
STRIPE_KEY       = os.getenv("STRIPE_SECRET_KEY", "")       # IMMER bullpowersrtkennels
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
KLAVIYO_KEY      = os.getenv("KLAVIYO_API_KEY", "") or os.getenv("KLAVIYO_PRIVATE_KEY", "")

_DB_PATH = Path(__file__).parent.parent / "data" / "ki_agents.db"


# ─── DB ───────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent      TEXT NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL,
            result     TEXT,
            status     TEXT DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS sales_leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT,
            email       TEXT,
            name        TEXT,
            product     TEXT,
            stage       TEXT DEFAULT 'new',
            source      TEXT,
            last_contact REAL,
            notes       TEXT,
            created_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS support_tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel     TEXT,
            contact     TEXT,
            subject     TEXT,
            body        TEXT,
            status      TEXT DEFAULT 'open',
            resolved_at REAL,
            created_at  REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topic      TEXT,
            summary    TEXT,
            action     TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS growth_insights (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            area       TEXT,
            finding    TEXT,
            suggestion TEXT,
            priority   INTEGER DEFAULT 3,
            created_at REAL NOT NULL
        );
    """)
    conn.commit()
    return conn


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _telegram(text: str) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT, "text": text[:4096], "parse_mode": "HTML"})
    except Exception as e:
        log.warning("Telegram error: %s", e)


async def _ai(prompt: str, system: str = "", max_tokens: int = 512) -> str:
    """KI-Aufruf über ai_client mit automatischem Fallback (Groq → DeepSeek → OpenRouter → Anthropic)."""
    try:
        from modules.ai_client import ai_complete
        result = await ai_complete(
            prompt=prompt,
            system=system or "Du bist ein Geschäftsassistent.",
            max_tokens=max_tokens,
        )
        return result or ""
    except Exception as e:
        log.warning("ai_complete error: %s", e)
        return ""


async def _shopify_get(endpoint: str) -> Optional[Dict]:
    if not SHOPIFY_DOMAIN or not SHOPIFY_TOKEN:
        return None
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_VERSION}/{endpoint}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            resp = await s.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        log.warning("Shopify error: %s", e)
    return None


async def _supabase_query(table: str, params: str = "") -> Optional[List[Dict]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            resp = await s.get(
                url,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Accept": "application/json",
                },
            )
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        log.warning("Supabase error: %s", e)
    return None


def _log_run(agent: str) -> int:
    db = _db()
    cur = db.execute(
        "INSERT INTO agent_runs (agent, started_at) VALUES (?,?)",
        (agent, time.time()),
    )
    db.commit()
    return cur.lastrowid


def _finish_run(run_id: int, result: str, status: str = "ok") -> None:
    db = _db()
    db.execute(
        "UPDATE agent_runs SET finished_at=?, result=?, status=? WHERE id=?",
        (time.time(), result[:2000], status, run_id),
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# SALES AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class SalesAgent:
    """Lead → Nurture → Close → Upsell über alle Kanäle."""

    SYSTEM = (
        "Du bist Sofia, Rudolfs KI-Verkaufsassistentin für ineedit.com.co. "
        "Smart Home, Tech-Gadgets, Solar-Powerstations. Professionell, freundlich, direkt. "
        "Kurze Antworten (max 2 Sätze). Fokus: Kaufentscheidung beschleunigen."
    )

    async def run(self) -> Dict[str, Any]:
        run_id = _log_run("sales")
        result = {"leads_processed": 0, "actions_taken": [], "errors": []}
        try:
            leads = await self._fetch_new_leads()
            for lead in leads[:20]:
                action = await self._process_lead(lead)
                if action:
                    result["actions_taken"].append(action)
                    result["leads_processed"] += 1

            stage_moves = await self._nurture_pipeline()
            result["actions_taken"].extend(stage_moves)

            if result["leads_processed"] > 0 or stage_moves:
                summary = (
                    f"🤖 <b>Sales-Agent</b>\n"
                    f"Leads: {result['leads_processed']} verarbeitet\n"
                    f"Pipeline: {len(stage_moves)} Aktionen\n"
                    f"Zeit: {datetime.now(timezone.utc).strftime('%H:%M')}"
                )
                await _telegram(summary)

        except Exception as e:
            log.error("SalesAgent error: %s", e)
            result["errors"].append(str(e))
            _finish_run(run_id, json.dumps(result), "error")
            return result

        _finish_run(run_id, json.dumps(result))
        return result

    async def _fetch_new_leads(self) -> List[Dict]:
        leads: List[Dict] = []

        # Supabase lead_events
        events = await _supabase_query(
            "lead_events",
            "order=created_at.desc&limit=30&status=eq.new",
        )
        if events:
            for e in events:
                leads.append({
                    "source": "supabase",
                    "phone": e.get("phone"),
                    "email": e.get("email"),
                    "name": e.get("name", "Kunde"),
                    "product": e.get("product", "Smart Home"),
                    "id": e.get("id"),
                })

        # Sofia SMS Konversationen ohne Folgekontakt
        try:
            db = _db()
            sms_db_path = Path(__file__).parent.parent / "data" / "sofia_sms.db"
            if sms_db_path.exists():
                sms_conn = sqlite3.connect(str(sms_db_path), check_same_thread=False)
                sms_conn.row_factory = sqlite3.Row
                rows = sms_conn.execute(
                    """SELECT phone, last_message, last_at FROM sms_conversations
                       WHERE opted_out=0 AND buy_signal=0
                       AND last_at < ? ORDER BY last_at DESC LIMIT 10""",
                    (time.time() - 3600,),
                ).fetchall()
                for r in rows:
                    leads.append({
                        "source": "sms_conv",
                        "phone": r["phone"],
                        "product": "Smart Home",
                        "name": "Interessent",
                        "last_msg": r["last_message"],
                    })
                sms_conn.close()
        except Exception as e:
            log.warning("SMS lead fetch: %s", e)

        return leads

    async def _process_lead(self, lead: Dict) -> Optional[str]:
        name = lead.get("name", "Kunde")
        product = lead.get("product", "Smart Home Produkt")
        phone = lead.get("phone")
        source = lead.get("source", "?")

        # KI-Qualifizierung
        analysis = await _ai(
            f"Lead: Name={name}, Produkt-Interesse={product}, Quelle={source}.\n"
            "Welche Aktion soll ich jetzt ausführen? Antworte mit genau einem von:\n"
            "ANRUFEN / SMS_SENDEN / EMAIL / WARTEN / NURTURE",
            system=self.SYSTEM,
            max_tokens=30,
        )
        action_key = "WARTEN"
        for k in ["ANRUFEN", "SMS_SENDEN", "EMAIL", "NURTURE"]:
            if k in (analysis or "").upper():
                action_key = k
                break

        if action_key == "ANRUFEN" and phone:
            try:
                from modules.sofia_voice_agent import queue_sofia_call
                await queue_sofia_call(phone, product, name, f"Lead via {source}", source)
                return f"📞 Anruf für {name} ({phone}) eingeplant"
            except Exception as e:
                log.warning("queue_sofia_call: %s", e)

        elif action_key == "SMS_SENDEN" and phone:
            try:
                from modules.sofia_sms_agent import send_welcome_sms
                await send_welcome_sms(phone, name, product)
                return f"📱 Welcome-SMS an {name} gesendet"
            except Exception as e:
                log.warning("send_welcome_sms: %s", e)

        return None

    async def _nurture_pipeline(self) -> List[str]:
        actions = []
        try:
            db = _db()
            stale_leads = db.execute(
                """SELECT * FROM sales_leads
                   WHERE stage IN ('new','contacted')
                   AND (last_contact IS NULL OR last_contact < ?)
                   LIMIT 10""",
                (time.time() - 86400,),
            ).fetchall()

            for lead in stale_leads:
                phone = lead["phone"]
                name = lead["name"] or "Interessent"
                product = lead["product"] or "Smart Home"

                if phone:
                    try:
                        from modules.sofia_sms_agent import send_cart_recovery_sms
                        await send_cart_recovery_sms(phone, product, step=1)
                        db.execute(
                            "UPDATE sales_leads SET stage='nurturing', last_contact=? WHERE id=?",
                            (time.time(), lead["id"]),
                        )
                        db.commit()
                        actions.append(f"🔄 Nurture-SMS → {name}")
                    except Exception as e:
                        log.warning("nurture sms: %s", e)
        except Exception as e:
            log.warning("_nurture_pipeline: %s", e)
        return actions

    def add_lead(self, phone: str = "", email: str = "", name: str = "",
                 product: str = "", source: str = "") -> int:
        db = _db()
        cur = db.execute(
            "INSERT INTO sales_leads (phone,email,name,product,source,created_at) VALUES (?,?,?,?,?,?)",
            (phone, email, name, product, source, time.time()),
        )
        db.commit()
        return cur.lastrowid

    def get_stats(self) -> Dict:
        db = _db()
        stages = {}
        for row in db.execute("SELECT stage, COUNT(*) as n FROM sales_leads GROUP BY stage"):
            stages[row["stage"]] = row["n"]
        total_runs = db.execute("SELECT COUNT(*) FROM agent_runs WHERE agent='sales'").fetchone()[0]
        last_run = db.execute(
            "SELECT finished_at FROM agent_runs WHERE agent='sales' AND status='ok' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "pipeline_stages": stages,
            "total_leads": sum(stages.values()),
            "total_runs": total_runs,
            "last_run": datetime.fromtimestamp(last_run[0]).strftime("%H:%M %d.%m") if last_run and last_run[0] else "noch nie",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SUPPORT AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class SupportAgent:
    """Kunden-Support: Bestellstatus, Reklamationen, Rückfragen."""

    SYSTEM = (
        "Du bist der Kundendienst von ineedit.com.co. Smart Home & Tech-Produkte. "
        "Hilfreich, lösungsorientiert, professionell. Max 3 Sätze. "
        "Bei Problemen: sofort Lösung anbieten (Rücksendung, Ersatz, Gutschein)."
    )

    async def run(self) -> Dict[str, Any]:
        run_id = _log_run("support")
        result = {"tickets_checked": 0, "resolved": 0, "escalated": 0, "errors": []}
        try:
            # Shopify Orders auf Probleme prüfen
            orders_result = await self._check_recent_orders()
            result["tickets_checked"] += orders_result.get("checked", 0)
            result["escalated"] += orders_result.get("escalated", 0)

            # Offene Tickets bearbeiten
            resolved = await self._resolve_open_tickets()
            result["resolved"] += resolved

            if result["escalated"] > 0:
                await _telegram(
                    f"🎫 <b>Support-Agent</b>\n"
                    f"⚠️ {result['escalated']} Tickets eskaliert\n"
                    f"✅ {result['resolved']} gelöst"
                )

        except Exception as e:
            log.error("SupportAgent error: %s", e)
            result["errors"].append(str(e))
            _finish_run(run_id, json.dumps(result), "error")
            return result

        _finish_run(run_id, json.dumps(result))
        return result

    async def _check_recent_orders(self) -> Dict:
        result = {"checked": 0, "escalated": 0}
        data = await _shopify_get("orders.json?status=any&limit=50&created_at_min=" +
                                   datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z"))
        if not data:
            return result

        orders = data.get("orders", [])
        result["checked"] = len(orders)

        for order in orders:
            order_id = order.get("id")
            fulfillment_status = order.get("fulfillment_status")
            financial_status = order.get("financial_status")
            email = order.get("email", "")
            name = order.get("billing_address", {}).get("name", "Kunde") if order.get("billing_address") else "Kunde"

            # Unfulfilled + paid seit >24h → Eskalierung
            created_str = order.get("created_at", "")
            try:
                from datetime import datetime as dt
                created = dt.fromisoformat(created_str.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            except Exception:
                age_hours = 0

            if financial_status == "paid" and fulfillment_status is None and age_hours > 24:
                self._open_ticket(
                    channel="shopify",
                    contact=email or str(order_id),
                    subject=f"Bestellung #{order.get('order_number')} nicht versendet",
                    body=f"Bezahlt vor {age_hours:.0f}h, noch kein Versand. Order ID: {order_id}",
                )
                result["escalated"] += 1

                # Automatische Entschuldigungs-SMS wenn Telefon vorhanden
                phone = (order.get("billing_address") or {}).get("phone", "")
                if phone:
                    try:
                        from modules.sofia_sms_agent import send_sms
                        msg = (
                            f"Hallo {name}, deine Bestellung #{order.get('order_number')} wird bald versendet. "
                            "Entschuldigung für die Verzögerung! Bei Fragen antworte einfach. – ineedit"
                        )
                        await send_sms(phone, msg, campaign="support_delay")
                    except Exception as e:
                        log.warning("Support delay SMS: %s", e)

        return result

    async def _resolve_open_tickets(self) -> int:
        resolved = 0
        db = _db()
        tickets = db.execute(
            "SELECT * FROM support_tickets WHERE status='open' LIMIT 20"
        ).fetchall()

        for t in tickets:
            answer = await _ai(
                f"Kunden-Ticket:\nBetreff: {t['subject']}\nNachricht: {t['body']}\n\n"
                "Wie sollen wir antworten? Schreibe die SMS-Antwort (max 160 Zeichen).",
                system=self.SYSTEM,
                max_tokens=80,
            )
            if answer:
                contact = t["contact"]
                if contact and not "@" in contact:
                    try:
                        from modules.sofia_sms_agent import send_sms
                        await send_sms(contact, answer[:160], campaign="support_auto")
                        db.execute(
                            "UPDATE support_tickets SET status='resolved', resolved_at=? WHERE id=?",
                            (time.time(), t["id"]),
                        )
                        db.commit()
                        resolved += 1
                    except Exception as e:
                        log.warning("support resolve sms: %s", e)

        return resolved

    def _open_ticket(self, channel: str, contact: str, subject: str, body: str) -> int:
        db = _db()
        existing = db.execute(
            "SELECT id FROM support_tickets WHERE contact=? AND subject=? AND status='open'",
            (contact, subject),
        ).fetchone()
        if existing:
            return existing["id"]
        cur = db.execute(
            "INSERT INTO support_tickets (channel,contact,subject,body,created_at) VALUES (?,?,?,?,?)",
            (channel, contact, subject, body, time.time()),
        )
        db.commit()
        return cur.lastrowid

    def get_stats(self) -> Dict:
        db = _db()
        by_status = {}
        for row in db.execute("SELECT status, COUNT(*) as n FROM support_tickets GROUP BY status"):
            by_status[row["status"]] = row["n"]
        return {
            "tickets_by_status": by_status,
            "total_tickets": sum(by_status.values()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class ResearchAgent:
    """Wettbewerber-Monitoring, Trend-Analyse, Produkt-Chancen."""

    SYSTEM = (
        "Du bist ein E-Commerce-Marktanalyse-Experte. "
        "Fokus: Smart Home, Tech-Gadgets, Solar-Produkte für den deutschen Markt. "
        "Analysiere prägnant. Empfehle konkrete, umsetzbare Aktionen."
    )

    RESEARCH_TOPICS = [
        "Smart Home Trends Deutschland 2024 — welche Produkte steigen gerade?",
        "Solar Balkonkraftwerk Markt — neue Chancen und günstige Einkaufsquellen",
        "E-Commerce Wettbewerber Analyse — was machen Amazon.de und Otto besser?",
        "AI Gadgets & Tech-Produkte — welche neuen Produkte sollten wir aufnehmen?",
        "Kundenbewertungen Analyse — häufigste Beschwerden in unserem Sortiment",
    ]

    async def run(self) -> Dict[str, Any]:
        run_id = _log_run("research")
        result = {"reports": [], "actions": [], "errors": []}
        try:
            # Täglich ein rotierendes Thema analysieren
            topic_idx = int(time.time() / 86400) % len(self.RESEARCH_TOPICS)
            topic = self.RESEARCH_TOPICS[topic_idx]

            analysis = await _ai(
                f"Analysiere jetzt: {topic}\n\n"
                "Gib mir:\n"
                "1. Wichtigste Erkenntnis (1 Satz)\n"
                "2. Konkrete Handlungsempfehlung für ineedit.com.co (1-2 Sätze)\n"
                "3. Priorität: HOCH / MITTEL / NIEDRIG",
                system=self.SYSTEM,
                max_tokens=200,
            )

            if analysis:
                db = _db()
                db.execute(
                    "INSERT INTO research_reports (topic,summary,created_at) VALUES (?,?,?)",
                    (topic, analysis, time.time()),
                )
                db.commit()
                result["reports"].append({"topic": topic, "summary": analysis})

                await _telegram(
                    f"🔬 <b>Research-Agent</b>\n"
                    f"<b>Thema:</b> {topic[:80]}\n\n"
                    f"{analysis[:600]}"
                )

            # Shopify-Sortiment auf Lücken prüfen
            gap_action = await self._check_product_gaps()
            if gap_action:
                result["actions"].append(gap_action)

        except Exception as e:
            log.error("ResearchAgent error: %s", e)
            result["errors"].append(str(e))
            _finish_run(run_id, json.dumps(result), "error")
            return result

        _finish_run(run_id, json.dumps(result))
        return result

    async def _check_product_gaps(self) -> Optional[str]:
        data = await _shopify_get("products/count.json")
        if not data:
            return None

        count = data.get("count", 0)
        if count < 1000:
            gap_analysis = await _ai(
                f"Unser Shop hat nur {count} Produkte. Was sind die 3 wichtigsten "
                "Produkt-Kategorien, die wir sofort ergänzen sollten (Smart Home, Tech)?",
                system=self.SYSTEM,
                max_tokens=150,
            )
            if gap_analysis:
                db = _db()
                db.execute(
                    "INSERT INTO growth_insights (area,finding,suggestion,priority,created_at) VALUES (?,?,?,?,?)",
                    ("sortiment", f"Nur {count} Produkte", gap_analysis, 1, time.time()),
                )
                db.commit()
                return f"Sortiment-Lücke: {count} Produkte — {gap_analysis[:100]}"
        return None

    def get_stats(self) -> Dict:
        db = _db()
        total = db.execute("SELECT COUNT(*) FROM research_reports").fetchone()[0]
        last = db.execute(
            "SELECT topic, created_at FROM research_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "total_reports": total,
            "last_topic": last["topic"] if last else "—",
            "last_at": datetime.fromtimestamp(last["created_at"]).strftime("%d.%m %H:%M") if last else "—",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GROWTH AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class GrowthAgent:
    """Conversion-Optimierung, Preis-Analyse, Retention."""

    SYSTEM = (
        "Du bist ein Growth-Hacker für ineedit.com.co. "
        "Fokus: Umsatz steigern, Conversion erhöhen, Kunden binden. "
        "Datengetrieben, konkret, messbar. Empfehle 1 Aktion pro Analyse."
    )

    async def run(self) -> Dict[str, Any]:
        run_id = _log_run("growth")
        result = {"insights": [], "campaigns_triggered": 0, "errors": []}
        try:
            # Revenue-Analyse
            revenue_insight = await self._analyze_revenue()
            if revenue_insight:
                result["insights"].append(revenue_insight)

            # Preis-Optimierung
            price_insight = await self._analyze_pricing()
            if price_insight:
                result["insights"].append(price_insight)

            # Reaktivierungs-Kampagne für inaktive Kunden
            reactivated = await self._reactivation_campaign()
            result["campaigns_triggered"] += reactivated

            if result["insights"] or reactivated > 0:
                summary_text = "\n".join(f"• {i}" for i in result["insights"][:3])
                await _telegram(
                    f"📈 <b>Growth-Agent</b>\n"
                    f"{summary_text}\n"
                    f"Reaktiviert: {reactivated} Kunden"
                )

        except Exception as e:
            log.error("GrowthAgent error: %s", e)
            result["errors"].append(str(e))
            _finish_run(run_id, json.dumps(result), "error")
            return result

        _finish_run(run_id, json.dumps(result))
        return result

    async def _analyze_revenue(self) -> Optional[str]:
        data = await _shopify_get(
            "orders.json?status=closed&limit=250&financial_status=paid"
        )
        if not data:
            return None

        orders = data.get("orders", [])
        if not orders:
            return None

        total_revenue = sum(float(o.get("total_price", 0)) for o in orders)
        avg_order = total_revenue / len(orders) if orders else 0
        top_products: Dict[str, int] = {}
        for o in orders:
            for item in o.get("line_items", []):
                title = item.get("title", "?")
                top_products[title] = top_products.get(title, 0) + 1

        top_3 = sorted(top_products.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{t[0]} ({t[1]}x)" for t in top_3)

        insight = await _ai(
            f"Shop-Daten: {len(orders)} Bestellungen, Ø {avg_order:.2f}€, "
            f"Top-Produkte: {top_str}.\n"
            "Empfehle 1 konkrete Aktion zur Umsatzsteigerung.",
            system=self.SYSTEM,
            max_tokens=100,
        )

        if insight:
            db = _db()
            db.execute(
                "INSERT INTO growth_insights (area,finding,suggestion,priority,created_at) VALUES (?,?,?,?,?)",
                ("revenue", f"{len(orders)} Orders, Ø{avg_order:.0f}€", insight, 1, time.time()),
            )
            db.commit()
            return f"Revenue: {insight[:120]}"
        return None

    async def _analyze_pricing(self) -> Optional[str]:
        data = await _shopify_get("products.json?limit=50&status=active")
        if not data:
            return None

        products = data.get("products", [])
        if not products:
            return None

        prices = []
        for p in products:
            for v in p.get("variants", []):
                try:
                    prices.append(float(v.get("price", 0)))
                except Exception:
                    pass

        if not prices:
            return None

        avg_price = sum(prices) / len(prices)
        insight = await _ai(
            f"Shop-Sortiment: {len(products)} Produkte, Ø-Preis {avg_price:.2f}€, "
            f"Min {min(prices):.2f}€, Max {max(prices):.2f}€.\n"
            "Gibt es Optimierungspotenzial bei der Preisstrategie?",
            system=self.SYSTEM,
            max_tokens=80,
        )
        if insight:
            return f"Preise: {insight[:100]}"
        return None

    async def _reactivation_campaign(self) -> int:
        count = 0
        try:
            sms_db_path = Path(__file__).parent.parent / "data" / "sofia_sms.db"
            if not sms_db_path.exists():
                return 0

            sms_conn = sqlite3.connect(str(sms_db_path), check_same_thread=False)
            sms_conn.row_factory = sqlite3.Row
            # Kunden die vor 7-30 Tagen Kontakt hatten aber nicht gekauft haben
            cutoff_min = time.time() - 30 * 86400
            cutoff_max = time.time() - 7 * 86400
            stale = sms_conn.execute(
                """SELECT phone FROM sms_conversations
                   WHERE opted_out=0 AND buy_signal=0
                   AND last_at BETWEEN ? AND ?
                   LIMIT 20""",
                (cutoff_min, cutoff_max),
            ).fetchall()
            sms_conn.close()

            for row in stale:
                phone = row["phone"]
                try:
                    from modules.sofia_sms_agent import send_sms
                    await send_sms(
                        phone,
                        "Hallo! Wir haben neue Smart Home Highlights für dich. "
                        "10% Rabatt mit Code RUECKRUF10 → ineedit.com.co 🏠",
                        campaign="growth_reactivation",
                    )
                    count += 1
                    await asyncio.sleep(0.3)
                except Exception as e:
                    log.warning("reactivation sms: %s", e)
        except Exception as e:
            log.warning("_reactivation_campaign: %s", e)
        return count

    def get_stats(self) -> Dict:
        db = _db()
        insights = db.execute(
            "SELECT area, suggestion, created_at FROM growth_insights ORDER BY id DESC LIMIT 5"
        ).fetchall()
        return {
            "recent_insights": [
                {
                    "area": i["area"],
                    "suggestion": i["suggestion"][:100],
                    "date": datetime.fromtimestamp(i["created_at"]).strftime("%d.%m"),
                }
                for i in insights
            ]
        }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT ORCHESTRATOR — öffentliche API
# ═══════════════════════════════════════════════════════════════════════════════

_sales    = SalesAgent()
_support  = SupportAgent()
_research = ResearchAgent()
_growth   = GrowthAgent()


async def run_sales_agent() -> Dict:
    return await _sales.run()


async def run_support_agent() -> Dict:
    return await _support.run()


async def run_research_agent() -> Dict:
    return await _research.run()


async def run_growth_agent() -> Dict:
    return await _growth.run()


async def run_all_agents() -> Dict:
    results = await asyncio.gather(
        _sales.run(),
        _support.run(),
        _research.run(),
        _growth.run(),
        return_exceptions=True,
    )
    labels = ["sales", "support", "research", "growth"]
    return {labels[i]: (results[i] if not isinstance(results[i], Exception) else str(results[i]))
            for i in range(4)}


def get_all_stats() -> Dict:
    return {
        "sales":    _sales.get_stats(),
        "support":  _support.get_stats(),
        "research": _research.get_stats(),
        "growth":   _growth.get_stats(),
    }


def add_sales_lead(phone: str = "", email: str = "", name: str = "",
                   product: str = "", source: str = "") -> int:
    return _sales.add_lead(phone=phone, email=email, name=name, product=product, source=source)


def open_support_ticket(channel: str, contact: str, subject: str, body: str) -> int:
    return _support._open_ticket(channel, contact, subject, body)
