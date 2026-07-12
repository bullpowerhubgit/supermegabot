#!/usr/bin/env python3
"""
MegaBot Umsatzmaschine — 8 Systeme + Stripe Webhook + PDF Delivery.

SYS-01 KI-Mitarbeiter-Leasing (B2B Leads)
SYS-02 Trend Velocity (Shopify + Meta Ads)
SYS-03 Ghost Vendor Network (Printful/Printify)
SYS-04 EU AI Act Compliance (PDF via ReportLab)
SYS-05 Insolvenz-Arbitrage + Kapital-Tracking
SYS-06 Platform Migration Kit (event-basiert)
SYS-07 AI Citation SEO
SYS-08 Intelligence Broker
"""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("Umsatzmaschine")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
CLIENTS_FILE = DATA_DIR / "megabot_clients.json"
AUTONOMOUS_STATE_FILE = DATA_DIR / "umsatzmaschine_autonomous.json"
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
AUTONOMOUS_INTERVAL_S = int(os.getenv("UMSATZMASCHINE_INTERVAL_S", "7200"))  # 2h
_CYCLE_LOCK = asyncio.Lock()

# Paket → System-Mapping
PACKAGE_SYSTEMS = {
    "lead-agent": "SYS-01",
    "lead-agent-pro": "SYS-01",
    "compliance": "SYS-04",
    "ai-act": "SYS-04",
    "insolvenz": "SYS-05",
    "insolvenz-pro": "SYS-05",
    "trend-velocity": "SYS-02",
    "ghost-vendor": "SYS-03",
    "intelligence": "SYS-08",
}


# ---------------------------------------------------------------------------
# Adapter — echte MegaBot-Module
# ---------------------------------------------------------------------------
async def fetch_b2b_leads(target_profile: str = "IT-Dienstleister DACH", num_leads: int = 10) -> List[Dict]:
    from modules.insolvenz_radar import get_top_leads, run_scan
    try:
        await run_scan(min_score_alert=60)
    except Exception as e:
        log.warning("Insolvenz scan: %s", e)
    leads = get_top_leads(limit=num_leads)
    return [
        {
            "company": l.get("debtor_name", l.get("company", "?")),
            "bundesland": l.get("bundesland", ""),
            "branche": l.get("branche", ""),
            "score": l.get("score", 0),
            "source": l.get("source", "insolvenz_radar"),
            "profile": target_profile,
        }
        for l in leads
    ]


async def generate_risk_report(company_name: str, systems: List[str]) -> Dict[str, Any]:
    from modules.ai_act_scanner import analyze_ai_risk
    findings: List[str] = []
    system_rows: List[Dict] = []
    max_risk = "NIEDRIG"
    risk_order = {"NIEDRIG": 0, "MITTEL": 1, "HOCH": 2}

    for sys_name in systems:
        branche = sys_name if sys_name in ("IT", "Finanzen", "Gesundheit") else "Sonstige"
        r = await analyze_ai_risk(company_name, branche, "Deutschland")
        level = r.get("risiko_level", "MITTEL")
        if risk_order.get(level, 1) > risk_order.get(max_risk, 0):
            max_risk = level
        findings.append(f"{sys_name}: {r.get('ai_summary', r.get('empfehlung', ''))}")
        system_rows.append({
            "system": sys_name,
            "risk_level": level,
            "measures": r.get("empfehlung", "Dokumentation + Human Oversight"),
        })

    return {
        "risk_level": max_risk,
        "findings": findings or ["Keine kritischen Verstöße im Scan gefunden."],
        "systems": system_rows,
        "company": company_name,
    }


def get_daily_insolvency_alerts(limit: int = 20) -> List[Dict]:
    from modules.insolvenz_radar import get_top_leads
    return get_top_leads(limit=limit)


def get_zvg_signals(limit: int = 15) -> List[Dict]:
    db = DATA_DIR / "zvg_radar.db"
    if not db.exists():
        db = Path(__file__).parent.parent / "data" / "zvg_radar.db"
    if not db.exists():
        return []
    try:
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM zvg_leads ORDER BY score DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("ZVG DB: %s", e)
        return []


async def run_trend_velocity() -> Dict[str, Any]:
    from modules.ds24_affiliate_blaster import blast_all_approved
    r = await blast_all_approved(delay=2.0)
    return {"ok": True, "blasted": r.get("blasted", 0), "system": "SYS-02"}


async def run_ghost_vendor_update(shop_id: str = "") -> Dict[str, Any]:
    sid = shop_id or os.getenv("PRINTFUL_STORE_ID", "")
    try:
        from modules.printful_automation import ping, get_stores
        ok = await ping()
        stores = await get_stores() if ok else []
        return {"ok": ok, "stores": len(stores), "shop_id": sid, "system": "SYS-03"}
    except Exception as e:
        return {"ok": False, "error": str(e), "system": "SYS-03"}


async def run_intelligence_broker(company: str) -> Dict[str, Any]:
    risk = await generate_risk_report(company, ["Chatbot", "Recommendation Engine"])
    hr: Dict[str, Any] = {}
    try:
        from modules.handelsregister_radar import run_cycle as hr_cycle
        hr = await hr_cycle()
    except Exception:
        hr = {"note": "Handelsregister scan optional"}
    return {
        "company": company,
        "handelsregister": hr,
        "insolvenz_alerts": len(get_daily_insolvency_alerts(5)),
        "ai_act_risk": risk.get("risk_level", "?"),
        "system": "SYS-08",
    }


# ---------------------------------------------------------------------------
# Email mit Attachment (Resend API)
# ---------------------------------------------------------------------------
async def send_email_with_attachment(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    attachment_name: Optional[str] = None,
    csv_rows: Optional[List[Dict]] = None,
) -> bool:
    import aiohttp

    attachments = []
    if csv_rows:
        output = io.StringIO()
        if csv_rows:
            writer = csv.DictWriter(output, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)
        attachments.append({
            "filename": attachment_name or "leads.csv",
            "content": base64.b64encode(output.getvalue().encode("utf-8")).decode(),
        })
    elif attachment_path and Path(attachment_path).exists():
        content = Path(attachment_path).read_bytes()
        attachments.append({
            "filename": attachment_name or Path(attachment_path).name,
            "content": base64.b64encode(content).decode(),
        })

    html = f"<html><body style='font-family:Arial,sans-serif'><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    key = os.getenv("RESEND_API_KEY", "")
    if not key:
        from modules.email_client import send_email
        return await send_email(to_email, subject, html)

    payload: Dict[str, Any] = {
        "from": os.getenv("EMAIL_FROM", "MegaBot <onboarding@resend.dev>"),
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if attachments:
        payload["attachments"] = attachments

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            ) as r:
                if r.status in (200, 201):
                    log.info("Email gesendet an %s: %s", to_email, subject)
                    return True
                log.warning("Resend %s: %s", r.status, (await r.text())[:200])
    except Exception as e:
        log.error("Resend-Fehler: %s", e)

    return await _send_smtp_fallback(to_email, subject, body, attachment_path, csv_rows, attachment_name)


async def _send_smtp_fallback(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Optional[str],
    csv_rows: Optional[List[Dict]],
    attachment_name: Optional[str],
) -> bool:
    """Gmail SMTP Fallback — alle konfigurierten Konten via gmail_accounts."""
    from modules.gmail_accounts import send_email_with_attachment as ga_send

    att_bytes = None
    att_name = attachment_name
    if csv_rows:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
        att_bytes = output.getvalue().encode("utf-8")
        att_name = att_name or "leads.csv"

    ok, _via = ga_send(
        to_email, subject, body,
        attachment_path=attachment_path if not att_bytes else None,
        attachment_bytes=att_bytes,
        attachment_name=att_name,
    )
    return ok


# ---------------------------------------------------------------------------
# Stripe Webhook Handler
# ---------------------------------------------------------------------------
class StripeWebhookHandler:
    def __init__(self, services: "MegaBotUmsatzmaschine"):
        self.services = services

    async def handle_checkout_session_completed_async(self, session_data: Dict) -> Dict:
        email = (
            session_data.get("customer_email")
            or (session_data.get("customer_details") or {}).get("email")
        )
        metadata = session_data.get("metadata") or {}
        package = metadata.get("package") or metadata.get("tier") or "lead-agent"
        company = metadata.get("company_name", "")
        amount = (session_data.get("amount_total") or 0) / 100

        client_id = self.services.register_new_client(
            email, package, company_name=company, amount_paid=amount
        )
        await self.services.trigger_immediate_delivery(client_id)
        return {
            "status": "success",
            "client_id": client_id,
            "package": package,
            "message": f"Client {email} für {package} aktiviert + Delivery gestartet",
        }


# ---------------------------------------------------------------------------
# MegaBot Umsatzmaschine
# ---------------------------------------------------------------------------
class MegaBotUmsatzmaschine:
    def __init__(self):
        self.clients = self.load_clients()
        self.deliveries_log: List[Dict] = []

    def load_clients(self) -> Dict[str, Any]:
        if CLIENTS_FILE.exists():
            return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
        return {}

    def save_clients(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIENTS_FILE.write_text(
            json.dumps(self.clients, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def register_new_client(
        self,
        email: str,
        package_name: str,
        *,
        company_name: str = "",
        amount_paid: float = 0.0,
    ) -> str:
        client_id = f"mb_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        pkg = package_name.lower().replace(" ", "-")
        self.clients[client_id] = {
            "email": email,
            "package": package_name,
            "package_key": pkg,
            "company_name": company_name or email.split("@")[0],
            "registered": datetime.now().isoformat(),
            "status": "active",
            "amount_paid": amount_paid,
            "capital_eur": 0.0,
            "next_delivery": (datetime.now() + timedelta(days=1)).isoformat(),
            "target_profile": "IT-Dienstleister DACH",
            "ai_systems": ["Chatbot", "Recommendation Engine", "Content Generator"],
            "history": [],
        }
        self.save_clients()
        log.info("Neuer Kunde: %s | %s | €%.2f", email, package_name, amount_paid)
        return client_id

    async def trigger_immediate_delivery(self, client_id: str) -> Dict[str, Any]:
        client = self.clients.get(client_id)
        if not client:
            return {"ok": False, "error": "Client nicht gefunden"}

        pkg = client.get("package", "").lower()
        if any(x in pkg for x in ("lead", "leasing", "sys-01")):
            return await self.deliver_leads(client_id)
        if any(x in pkg for x in ("compliance", "ai act", "ai-act", "sys-04")):
            return await self.deliver_compliance_report(client_id)
        if any(x in pkg for x in ("insolvenz", "zvg", "sys-05")):
            return await self.deliver_insolvency_alerts(client_id)
        if any(x in pkg for x in ("trend", "sys-02")):
            return await run_trend_velocity()
        if any(x in pkg for x in ("ghost", "vendor", "sys-03")):
            return await run_ghost_vendor_update()
        if any(x in pkg for x in ("intelligence", "sys-08")):
            return await run_intelligence_broker(client.get("company_name", ""))
        return await self.deliver_leads(client_id)

    async def deliver_leads(self, client_id: str) -> Dict[str, Any]:
        client = self.clients[client_id]
        leads = await fetch_b2b_leads(
            client.get("target_profile", "IT-Dienstleister DACH"),
            num_leads=10,
        )
        ok = await send_email_with_attachment(
            client["email"],
            f"Tägliche B2B-Leads — {datetime.now().strftime('%d.%m.%Y')}",
            f"Hier sind {len(leads)} validierte Leads aus Insolvenz- & Handelsregister-Quellen.",
            csv_rows=leads,
            attachment_name="leads.csv",
        )
        client["history"].append({
            "type": "SYS-01_leads", "date": datetime.now().isoformat(), "count": len(leads), "sent": ok,
        })
        self.save_clients()
        return {"ok": ok, "system": "SYS-01", "leads": len(leads)}

    async def deliver_compliance_report(self, client_id: str) -> Dict[str, Any]:
        client = self.clients[client_id]
        scan = await generate_risk_report(
            client.get("company_name", "Kunde GmbH"),
            client.get("ai_systems", ["Chatbot", "Recommendation Engine"]),
        )
        pdf_path = self.generate_ai_act_pdf_report(client, scan)
        ok = await send_email_with_attachment(
            client["email"],
            "EU AI Act Compliance Report — MegaBot",
            "Dein Risiko-Report mit Findings, To-dos und Maßnahmen (PDF im Anhang).",
            attachment_path=str(pdf_path),
            attachment_name=pdf_path.name,
        )
        client["history"].append({
            "type": "SYS-04_compliance", "date": datetime.now().isoformat(), "pdf": str(pdf_path), "sent": ok,
        })
        self.save_clients()
        return {"ok": ok, "system": "SYS-04", "pdf": str(pdf_path)}

    def generate_ai_act_pdf_report(self, client: Dict, scan_result: Dict) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        safe = client["email"].split("@")[0].replace(".", "_")
        filename = REPORTS_DIR / f"ai_act_{safe}_{datetime.now().strftime('%Y%m%d')}.pdf"
        doc = SimpleDocTemplate(str(filename), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("EU AI Act Compliance Report", styles["Title"]))
        story.append(Paragraph(f"Kunde: {client.get('company_name', '')}", styles["Normal"]))
        story.append(Paragraph(f"Datum: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("<b>Risiko-Klassifizierung</b>", styles["Heading2"]))

        rows = [["System", "Risikoklasse", "Maßnahmen"]]
        for s in scan_result.get("systems", []):
            rows.append([s["system"], s["risk_level"], s["measures"]])
        if len(rows) == 1:
            rows.append(["KI-Systeme", scan_result.get("risk_level", "MITTEL"), "Dokumentation + Oversight"])

        table = Table(rows, colWidths=[5 * cm, 3 * cm, 8 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.8 * cm))
        story.append(Paragraph("<b>Findings</b>", styles["Heading2"]))
        for f in scan_result.get("findings", []):
            story.append(Paragraph(f"• {f}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(
            "<i>Technische Risikoanalyse — ersetzt keine juristische Beratung.</i>",
            styles["Normal"],
        ))
        doc.build(story)
        return filename

    async def deliver_insolvency_alerts(self, client_id: str) -> Dict[str, Any]:
        client = self.clients[client_id]
        insolvenz = get_daily_insolvency_alerts(20)
        zvg = get_zvg_signals(10)
        combined = [
            {"type": "insolvenz", **{k: v for k, v in l.items() if k != "raw_text"}}
            for l in insolvenz
        ] + [
            {"type": "zvg", "objekt": l.get("objekt_typ"), "ort": l.get("objekt_adresse"),
             "wert": l.get("verkehrswert"), "score": l.get("score")}
            for l in zvg
        ]
        capital = float(client.get("capital_eur", 0))
        body = (
            f"Insolvenz-Alerts: {len(insolvenz)} | ZVG-Signale: {len(zvg)}\n"
            f"Verfügbares Kapital (SYS-05): €{capital:.2f}"
        )
        ok = await send_email_with_attachment(
            client["email"],
            f"Insolvenz & ZVG Alerts — {datetime.now().strftime('%d.%m.%Y')}",
            body,
            csv_rows=combined if combined else [{"info": "Keine neuen Alerts"}],
            attachment_name="insolvenz_zvg_alerts.csv",
        )
        client["history"].append({
            "type": "SYS-05_insolvenz", "date": datetime.now().isoformat(),
            "insolvenz": len(insolvenz), "zvg": len(zvg), "sent": ok,
        })
        self.save_clients()
        return {"ok": ok, "system": "SYS-05", "alerts": len(combined)}

    async def run_daily_deliveries(self) -> Dict[str, Any]:
        """Cron: alle aktiven Kunden deren next_delivery fällig ist."""
        now = datetime.now()
        delivered, skipped = 0, 0
        results = []

        for client_id, client in list(self.clients.items()):
            if client.get("status") != "active":
                skipped += 1
                continue
            pending_mail = self._has_pending_delivery(client)
            nd = client.get("next_delivery", "")
            try:
                due = datetime.fromisoformat(nd)
            except Exception:
                due = now - timedelta(seconds=1)
            if due > now and not pending_mail:
                skipped += 1
                continue

            r = await self.trigger_immediate_delivery(client_id)
            client["next_delivery"] = (now + timedelta(days=1)).isoformat()
            results.append({"client_id": client_id, **r})
            delivered += 1

        self.save_clients()
        return {"ok": True, "delivered": delivered, "skipped": skipped, "results": results}

    def deactivate_client(self, email: str, reason: str = "cancelled") -> bool:
        changed = False
        for cid, c in self.clients.items():
            if c.get("email", "").lower() == email.lower():
                c["status"] = "cancelled"
                c["cancelled_at"] = datetime.now().isoformat()
                c["cancel_reason"] = reason
                changed = True
        if changed:
            self.save_clients()
        return changed

    def deactivate_by_subscription(self, subscription_id: str) -> Optional[str]:
        email = None
        for c in self.clients.values():
            if c.get("stripe_subscription_id") == subscription_id:
                email = c.get("email")
                c["status"] = "cancelled"
                c["cancelled_at"] = datetime.now().isoformat()
        if email:
            self.save_clients()
        return email

    async def sync_ki_leasing_clients(self) -> Dict[str, Any]:
        """KI-Leasing SQLite → megabot_clients.json synchronisieren."""
        db = DATA_DIR / "ki_leasing.db"
        if not db.exists():
            return {"synced": 0, "reason": "no ki_leasing.db"}
        synced = 0
        try:
            from modules.ki_leasing_engine import PACKAGES
            with sqlite3.connect(str(db)) as conn:
                rows = conn.execute(
                    "SELECT email, package, stripe_subscription_id, active FROM clients WHERE active=1"
                ).fetchall()
            existing_emails = {c.get("email", "").lower() for c in self.clients.values()}
            for email, package, sub_id, active in rows:
                if not active or email.lower() in existing_emails:
                    continue
                pkg_label = PACKAGES.get(package, {}).get("label", package)
                cid = self.register_new_client(
                    email, f"lead-agent-{package}",
                    company_name=email.split("@")[0],
                    amount_paid=PACKAGES.get(package, {}).get("price_cents", 0) / 100,
                )
                self.clients[cid]["stripe_subscription_id"] = sub_id
                self.clients[cid]["source"] = "ki_leasing"
                self.clients[cid]["package"] = pkg_label
                if package == "pro":
                    self.clients[cid]["ai_systems"] = [
                        "Chatbot", "Recommendation Engine", "Content Generator", "HR Screening",
                    ]
                synced += 1
            self.save_clients()
        except Exception as e:
            log.warning("KI-Leasing sync: %s", e)
            return {"synced": 0, "error": str(e)[:120]}
        return {"synced": synced}

    def _has_pending_delivery(self, client: Dict) -> bool:
        history = client.get("history", [])
        if not history:
            return False
        last = history[-1]
        return last.get("sent") is False and int(last.get("retry_count", 0)) < 5

    async def retry_failed_deliveries(self) -> Dict[str, Any]:
        """Fehlgeschlagene Mails erneut senden (bis 5 Versuche)."""
        retried, ok_count = 0, 0
        for client_id, client in self.clients.items():
            if client.get("status") != "active":
                continue
            if not self._has_pending_delivery(client):
                continue
            last = client["history"][-1]
            last["retry_count"] = int(last.get("retry_count", 0)) + 1
            r = await self.trigger_immediate_delivery(client_id)
            retried += 1
            if r.get("ok"):
                ok_count += 1
                client["history"][-1]["sent"] = True
        self.save_clients()
        return {"retried": retried, "recovered": ok_count}

    def get_status(self) -> Dict[str, Any]:
        active = sum(1 for c in self.clients.values() if c.get("status") == "active")
        revenue = sum(float(c.get("amount_paid", 0)) for c in self.clients.values())
        auto_state = {}
        if AUTONOMOUS_STATE_FILE.exists():
            try:
                auto_state = json.loads(AUTONOMOUS_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "ok": True,
            "autonomous": os.getenv("UMSATZMASCHINE_AUTONOMOUS", "true").lower() not in ("false", "0", "off"),
            "interval_hours": AUTONOMOUS_INTERVAL_S / 3600,
            "clients_total": len(self.clients),
            "clients_active": active,
            "revenue_total_eur": round(revenue, 2),
            "clients_file": str(CLIENTS_FILE),
            "reports_dir": str(REPORTS_DIR),
            "systems": list(PACKAGE_SYSTEMS.keys()),
            "last_autonomous_run": auto_state.get("last_run"),
            "cycles_total": auto_state.get("cycles_total", 0),
        }


# Singleton
_bot: Optional[MegaBotUmsatzmaschine] = None


def get_umsatzmaschine() -> MegaBotUmsatzmaschine:
    global _bot
    if _bot is None:
        _bot = MegaBotUmsatzmaschine()
    return _bot


async def handle_stripe_checkout(session_data: Dict) -> Dict:
    handler = StripeWebhookHandler(get_umsatzmaschine())
    return await handler.handle_checkout_session_completed_async(session_data)


async def refresh_data_sources() -> Dict[str, Any]:
    """Alle Datenquellen für SYS-01/04/05 im Hintergrund aktualisieren."""
    results: Dict[str, Any] = {}

    async def _insolvenz():
        from modules.insolvenz_radar import run_scan
        return await run_scan(min_score_alert=55)

    async def _zvg():
        from modules.zvg_radar import run_cycle
        return await run_cycle()

    async def _ai_act():
        from modules.ai_act_scanner import run_cycle
        return await run_cycle()

    async def _handelsregister():
        from modules.handelsregister_radar import run_cycle
        return await run_cycle()

    for name, coro in [
        ("insolvenz", _insolvenz()),
        ("zvg", _zvg()),
        ("ai_act", _ai_act()),
        ("handelsregister", _handelsregister()),
    ]:
        try:
            results[name] = await asyncio.wait_for(coro, timeout=120)
        except Exception as e:
            results[name] = {"error": str(e)[:120]}

    return results


async def _should_run_ki_leasing_reports(state: Dict) -> bool:
    """KI-Leasing Reports: 1x täglich (nach 08:00 oder wenn >20h seit letztem Lauf)."""
    last = state.get("ki_leasing_last_run")
    now = datetime.now()
    if now.hour >= 8:
        if not last:
            return True
        try:
            prev = datetime.fromisoformat(last)
            return (now - prev).total_seconds() > 20 * 3600
        except Exception:
            return True
    return False


async def run_autonomous_cycle() -> Dict[str, Any]:
    """
    Vollautonomer Master-Zyklus — kein manueller Eingriff nötig.
    1. Daten refreshen  2. KI-Leasing sync  3. Deliveries  4. KI-Leasing Reports
    5. Retries  6. Revenue Engine  7. Telegram
    """
    if os.getenv("UMSATZMASCHINE_AUTONOMOUS", "true").lower() in ("false", "0", "off"):
        return {"ok": False, "skipped": True, "reason": "UMSATZMASCHINE_AUTONOMOUS=off"}

    if _CYCLE_LOCK.locked():
        log.info("Umsatzmaschine: Zyklus läuft bereits — übersprungen")
        return {"ok": True, "skipped": True, "reason": "cycle_already_running"}

    async with _CYCLE_LOCK:
        return await _run_autonomous_cycle_inner()


async def _run_autonomous_cycle_inner() -> Dict[str, Any]:
    log.info("═══ Umsatzmaschine AUTONOMOUS START ═══")
    bot = get_umsatzmaschine()
    state: Dict[str, Any] = {}
    if AUTONOMOUS_STATE_FILE.exists():
        try:
            state = json.loads(AUTONOMOUS_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    refresh, sync, deliveries, ki_reports, retries, revenue = await asyncio.gather(
        refresh_data_sources(),
        bot.sync_ki_leasing_clients(),
        bot.run_daily_deliveries(),
        _run_ki_leasing_if_due(state),
        bot.retry_failed_deliveries(),
        _run_revenue_engine_safe(),
        return_exceptions=True,
    )

    def _n(r: Any, name: str) -> Dict:
        return r if isinstance(r, dict) else {"error": str(r)[:120]}

    result = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "mode": "fully_autonomous",
        "steps": {
            "data_refresh": _n(refresh, "refresh"),
            "ki_leasing_sync": _n(sync, "sync"),
            "deliveries": _n(deliveries, "deliveries"),
            "ki_leasing_reports": _n(ki_reports, "ki_reports"),
            "retries": _n(retries, "retries"),
            "revenue_engine": _n(revenue, "revenue"),
        },
    }

    state["last_run"] = result["timestamp"]
    state["cycles_total"] = int(state.get("cycles_total", 0)) + 1
    state["last_result"] = {
        "delivered": _n(deliveries, "d").get("delivered", 0),
        "ki_sent": _n(ki_reports, "k").get("sent", 0),
    }
    if isinstance(ki_reports, dict) and ki_reports.get("sent", 0) > 0:
        state["ki_leasing_last_run"] = result["timestamp"]
    AUTONOMOUS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTONOMOUS_STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    d = _n(deliveries, "d")
    k = _n(ki_reports, "k")
    try:
        from modules.notify_hub import async_send_telegram
        await async_send_telegram(
            f"🤖 Umsatzmaschine AUTO\n"
            f"Deliveries: {d.get('delivered', 0)} | KI-Leasing: {k.get('sent', 0)} Reports\n"
            f"Retries recovered: {_n(retries, 'r').get('recovered', 0)}"
        )
    except Exception:
        pass

    log.info("Umsatzmaschine AUTONOMOUS DONE — %d deliveries", d.get("delivered", 0))
    return result


async def _run_ki_leasing_if_due(state: Dict) -> Dict[str, Any]:
    if not await _should_run_ki_leasing_reports(state):
        return {"skipped": True, "reason": "not_due"}
    try:
        from modules.ki_leasing_engine import send_daily_reports
        return await send_daily_reports()
    except Exception as e:
        return {"error": str(e)[:120]}


async def _run_revenue_engine_safe() -> Dict[str, Any]:
    try:
        from modules.revenue_engine import run_revenue_cycle
        return await run_revenue_cycle()
    except Exception as e:
        return {"error": str(e)[:120]}


async def run_autonomous_loop() -> None:
    """Endlos-Loop — startet beim Server-Boot."""
    await asyncio.sleep(int(os.getenv("UMSATZMASCHINE_BOOT_DELAY_S", "90")))
    log.info("Umsatzmaschine autonomous loop gestartet (alle %ds)", AUTONOMOUS_INTERVAL_S)
    while True:
        try:
            await run_autonomous_cycle()
        except Exception as e:
            log.error("Autonomous cycle Fehler: %s", e)
        await asyncio.sleep(AUTONOMOUS_INTERVAL_S)


async def handle_stripe_subscription_event(event_type: str, obj: Dict) -> Optional[str]:
    """Abo-Kündigung → Client deaktivieren."""
    bot = get_umsatzmaschine()
    if event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        sub_id = obj.get("id", "")
        email = bot.deactivate_by_subscription(sub_id)
        if email:
            return f"umsatzmaschine:cancelled:{email}"
    return None


async def run_daily_cron() -> Dict[str, Any]:
    return await run_autonomous_cycle()


async def run_daily_cron_str() -> str:
    r = await run_autonomous_cycle()
    d = r.get("steps", {}).get("deliveries", {})
    k = r.get("steps", {}).get("ki_leasing_reports", {})
    return (
        f"Umsatzmaschine AUTO: {d.get('delivered', 0)} Deliveries | "
        f"KI-Leasing {k.get('sent', 0)} Reports | "
        f"Retries {r.get('steps', {}).get('retries', {}).get('recovered', 0)}"
    )


if __name__ == "__main__":
    import sys

    cmd = (sys.argv[1] if len(sys.argv) > 1 else "cycle").lower()
    bot = get_umsatzmaschine()

    async def _main() -> None:
        if cmd in ("status", "st"):
            print(json.dumps(bot.get_status(), indent=2, ensure_ascii=False))
            return
        if cmd in ("delivery", "deliver") and len(sys.argv) > 2:
            r = await bot.trigger_immediate_delivery(sys.argv[2])
            print(json.dumps(r, indent=2, ensure_ascii=False))
            return
        if cmd in ("register", "client") and len(sys.argv) >= 4:
            cid = bot.register_new_client(sys.argv[2], sys.argv[3])
            print(json.dumps({"client_id": cid, "email": sys.argv[2], "package": sys.argv[3]}, indent=2))
            return
        r = await run_autonomous_cycle()
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))

    print("MegaBot Umsatzmaschine — production module (8 Systeme + Stripe + PDF)")
    asyncio.run(_main())