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
import time
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

    def generate_kfw_antrag(self, antrag_data: Dict[str, Any], *, merge_live: bool = True) -> str:
        """KfW ERP-Gründerkredit StartGeld — Businessplan-PDF aus Antragsdaten."""
        from modules.megabot_kfw_generator import KfWAntragGenerator, fetch_live_antrag_data

        data: Dict[str, Any] = {}
        if merge_live:
            data = asyncio.run(fetch_live_antrag_data())
        data.update(antrag_data or {})
        if not data.get("verwendung") and data.get("kredit_betrag"):
            total = int(data["kredit_betrag"])
            data["verwendung"] = {
                "marketing": int(total * 0.4),
                "infrastruktur": int(total * 0.3),
                "betrieb": int(total * 0.2),
                "reserve": int(total * 0.1),
            }
        path = KfWAntragGenerator().generate_kfw_startgeld_pdf(data)
        log.info("KfW Antrag PDF: %s", path)
        return path

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


# ── SYS-18: Kanzlei-Outreach → EU AI Act B2B Sales ──────────────────────────
# Zielgruppe: Anwaltskanzleien, Steuerberater, Compliance-Beratungen
# Paywall:    Stripe, €149/Einzel-Scan, €299/mo Abo
# Zustellung: E-Mail PDF-Report + Telegram
# Opens:      SYS-22 (Kanzlei-Mandats-Flatrate) sobald erster Käufer

_SYS18_DB = Path(__file__).parent.parent / "data" / "sys18_kanzlei.db"

_KANZLEI_TARGETS = [
    {"name": "Noerr LLP", "email": "info@noerr.com", "branche": "Kanzlei"},
    {"name": "CMS Hasche Sigle", "email": "info@cms-hs.com", "branche": "Kanzlei"},
    {"name": "Heuking Kühn Lüer Wojtek", "email": "info@heuking.de", "branche": "Kanzlei"},
    {"name": "Taylor Wessing", "email": "frankfurt@taylorwessing.com", "branche": "Kanzlei"},
    {"name": "DLA Piper Germany", "email": "frankfurt@dlapiper.com", "branche": "Kanzlei"},
    {"name": "Bird & Bird Germany", "email": "info@twobirds.com", "branche": "Kanzlei"},
    {"name": "Osborne Clarke", "email": "cologne@osborneclarke.com", "branche": "Kanzlei"},
    {"name": "Luther Rechtsanwaltsgesellschaft", "email": "info@luther-lawfirm.com", "branche": "Kanzlei"},
    {"name": "Fieldfisher Germany", "email": "info@fieldfisher.com", "branche": "Kanzlei"},
    {"name": "Rödl & Partner", "email": "nuernberg@roedl.de", "branche": "Steuerberater"},
    {"name": "KPMG Law", "email": "info@kpmg-law.de", "branche": "Steuerberater"},
    {"name": "EY Law", "email": "info@de.eylaw.com", "branche": "Steuerberater"},
    {"name": "Deloitte Legal", "email": "info@deloitte-legal.de", "branche": "Steuerberater"},
    {"name": "PwC Legal", "email": "de_law_klartext@de.pwc.com", "branche": "Steuerberater"},
    {"name": "BDO Legal", "email": "info@bdo.de", "branche": "Steuerberater"},
]

_SYS18_SUBJECT = "EU AI Act Art. 50 — Compliance-Lücken Ihrer Mandanten automatisch erkennen"
_SYS18_BODY    = """\
Sehr geehrte Damen und Herren,

der EU AI Act verpflichtet Unternehmen ab dem 02.08.2026 zu konkreten Transparenz- und
Dokumentationspflichten (Art. 50). Nicht-Erfüllung: bis zu €15 Mio. Bußgeld.

Unsere KI-gestützte Compliance-Prüfung analysiert in Echtzeit:
  • AI-Systeme und Chatbots (Transparenzpflicht Art. 50)
  • Hochrisiko-KI-Klassifizierung (Anhang III)
  • Dokumentationslücken (technische Dokumentation, Logs)
  • EU-Zollreform: HS-Code-Klassifizierung für E-Commerce-Mandanten (€150 Freigrenze abgeschafft)

Für {name}: Einzelscan €149 netto, Abo ab €299/Monat.
Scan-Ergebnis als PDF-Report, direkt an Ihren Mandanten sendbar.

Testlauf (kostenlos, 48h): https://supermegabot-production.up.railway.app/compliance

Mit freundlichen Grüßen
Rudolf Sarkany | AiiteC Automation GmbH
"""


def _sys18_db():
    _SYS18_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_SYS18_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT, email TEXT UNIQUE, branche TEXT,
            status TEXT DEFAULT 'pending',
            sent_at INTEGER, followup_at INTEGER, bounced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    # Seed targets
    for t in _KANZLEI_TARGETS:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO outreach (company, email, branche) VALUES (?,?,?)",
                (t["name"], t["email"], t["branche"])
            )
        except Exception:
            pass
    conn.commit()
    conn.close()


async def run_sys18_kanzlei_outreach(daily_limit: int = 10) -> Dict[str, Any]:
    """SYS-18: Kanzlei-Outreach — EU AI Act Compliance-Scanner als B2B-Produkt."""
    _sys18_db()
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", os.getenv("EMAIL_FROM", ""))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("EMAIL_PASSWORD", ""))

    now_ts = int(time.time())
    conn   = sqlite3.connect(_SYS18_DB)
    rows   = conn.execute(
        "SELECT id, company, email, branche FROM outreach "
        "WHERE status='pending' AND bounced=0 LIMIT ?",
        (daily_limit,)
    ).fetchall()

    sent = 0
    errors = 0
    for row_id, company, email, branche in rows:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = _SYS18_SUBJECT
            msg["From"]    = smtp_user
            msg["To"]      = email
            body = _SYS18_BODY.replace("{name}", company).replace("{branche}", branche)
            msg.attach(MIMEText(body, "plain", "utf-8"))

            if smtp_user and smtp_pass:
                with smtplib.SMTP(smtp_host, smtp_port) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_user, email, msg.as_string())

            conn.execute(
                "UPDATE outreach SET status='sent', sent_at=?, followup_at=? WHERE id=?",
                (now_ts, now_ts + 5 * 86400, row_id)
            )
            conn.commit()
            sent += 1
            log.info("SYS-18 sent: %s <%s>", company, email)
            await asyncio.sleep(2)
        except Exception as e:
            errors += 1
            log.warning("SYS-18 error %s: %s", email, e)

    conn.close()
    return {"ok": True, "system": "SYS-18", "sent": sent, "errors": errors}


# ── SYS-23: Shop-Customer Upsell Automation ──────────────────────────────────
# Zielgruppe: Bestehende Shopify-Kunden ohne aktives Abo
# Paywall:    Stripe-Subscription (Starter €49 → Pro €99 → Enterprise €299)
# Zustellung: Klaviyo E-Mail-Sequenz + Telegram Benachrichtigung
# Opens:      SYS-28 (Auto-Reorder) und SYS-29 (Loyalty-Cashback)

async def run_sys23_shop_upsell(limit: int = 50) -> Dict[str, Any]:
    """
    SYS-23: Shop-Customer Upsell — Kaufhistorie → Abo-Upgrade Angebot.
    Holt Shopify-Kunden mit >0 Bestellungen ohne laufendes Stripe-Abo.
    Sendet personalisierte Upgrade-Kampagne per Klaviyo/E-Mail.
    """
    results: Dict[str, Any] = {"ok": True, "system": "SYS-23", "targeted": 0, "campaigns": 0}

    try:
        from modules.shopify_client import get_customers
        customers = await asyncio.wait_for(
            asyncio.to_thread(get_customers, limit=limit),
            timeout=30
        )
        results["targeted"] = len(customers) if customers else 0
    except Exception as e:
        log.warning("SYS-23 Shopify-Kunden: %s", e)
        customers = []

    if not customers:
        results["note"] = "Keine Shopify-Kunden verfügbar"
        return results

    # Klaviyo-Kampagne für Shop-Kunden ohne Abo
    try:
        from modules.klaviyo_client import send_upsell_sequence
        campaign_count = 0
        for c in customers[:limit]:
            email = c.get("email", "") if isinstance(c, dict) else ""
            if not email:
                continue
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        send_upsell_sequence,
                        email=email,
                        first_name=c.get("first_name", ""),
                        sequence="shop_to_saas",
                        metadata={
                            "orders_count": c.get("orders_count", 0),
                            "total_spent":  c.get("total_spent", "0.00"),
                            "upsell_url":   "https://supermegabot-production.up.railway.app/pricing",
                        }
                    ),
                    timeout=10
                )
                campaign_count += 1
            except Exception:
                pass
        results["campaigns"] = campaign_count
    except ImportError:
        # Fallback: direkt per E-Mail
        results["note"] = "Klaviyo nicht verfügbar — E-Mail-Fallback"
        log.info("SYS-23: Klaviyo fehlt, Skip")

    log.info("SYS-23 abgeschlossen: %d Kampagnen", results.get("campaigns", 0))
    return results


# ── SYS-37: Template-Käufer → Mandat-Conversion ──────────────────────────────
# Zielgruppe: Käufer von Gumroad/Digistore24 Digital-Templates
# Paywall:    Monatliche Retainer (€299-€499/Monat Mandat)
# Zustellung: E-Mail-Sequenz (Tag 1, Tag 3, Tag 7, Tag 14)
# Opens:      SYS-39 (Ongoing Compliance) und SYS-40 (White-Label Resell)

_SYS37_FOLLOWUP_SEQUENCE = [
    {
        "day": 1,
        "subject": "Ihr Template funktioniert — der nächste Schritt kostet nichts",
        "body": (
            "Hallo {name},\n\n"
            "Sie haben das EU AI Act Template verwendet. Perfekt.\n\n"
            "Was Sie jetzt brauchen: automatische Überwachung — damit keine Änderung am "
            "AI Act oder der EU-Zollreform unbemerkt bleibt.\n\n"
            "Unser Mandat (€299/Monat) übernimmt:\n"
            "  • Monatliche Compliance-Checks per KI-Scanner\n"
            "  • Sofortmeldung bei Gesetzesänderungen\n"
            "  • Unbegrenzte Scans + PDF-Reports\n"
            "  • Prioritäts-Support\n\n"
            "14 Tage kostenlos testen: https://supermegabot-production.up.railway.app/mandate\n\n"
            "Beste Grüße\nRudolf Sarkany | AiiteC"
        ),
    },
    {
        "day": 3,
        "subject": "EU AI Act Frist läuft ab: 02.08.2026 — sind Sie vorbereitet?",
        "body": (
            "Hallo {name},\n\n"
            "Ab dem 02.08.2026 greifen die Bußgelder (bis €15 Mio. oder 3% Jahresumsatz).\n\n"
            "Ihr Template ist ein guter Start — aber kein Dauerschutz.\n"
            "Mit dem Mandat prüfen wir automatisch jeden Monat ob Sie noch compliant sind.\n\n"
            "Jetzt starten (30% Rabatt im Juli): https://supermegabot-production.up.railway.app/mandate?promo=JULY30\n\n"
            "Beste Grüße\nRudolf Sarkany | AiiteC"
        ),
    },
    {
        "day": 7,
        "subject": "Letzte Chance: Template-Käufer Sonderkonditionen",
        "body": (
            "Hallo {name},\n\n"
            "Als Template-Käufer erhalten Sie exklusiv:\n"
            "  • 2 Monate kostenlos bei jährlicher Zahlung\n"
            "  • Persönliches Onboarding-Call (30 Min.)\n"
            "  • Migration Ihrer bestehenden Dokumentation\n\n"
            "Angebot gilt bis Ende dieser Woche.\n"
            "Jetzt sichern: https://supermegabot-production.up.railway.app/mandate\n\n"
            "Beste Grüße\nRudolf Sarkany | AiiteC"
        ),
    },
]

_SYS37_DB = Path(__file__).parent.parent / "data" / "sys37_template_conv.db"


def _sys37_db():
    _SYS37_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_SYS37_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS buyers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE, name TEXT, source TEXT,
            product TEXT, bought_at INTEGER,
            followup_step INTEGER DEFAULT 0,
            next_followup INTEGER,
            converted INTEGER DEFAULT 0,
            bounced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


async def sync_sys37_template_buyers() -> int:
    """Holt neue Template-Käufer von Gumroad und Digistore24 → SYS-37 DB."""
    _sys37_db()
    added = 0
    now_ts = int(time.time())

    # Gumroad-Käufer
    try:
        from modules.gumroad_client import get_sales
        sales = await asyncio.wait_for(asyncio.to_thread(get_sales, limit=50), timeout=20)
        conn = sqlite3.connect(_SYS37_DB)
        for s in (sales or []):
            email = s.get("email", "") if isinstance(s, dict) else ""
            if not email:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO buyers (email, name, source, product, bought_at, next_followup) "
                    "VALUES (?,?,?,?,?,?)",
                    (email, s.get("full_name", ""), "gumroad",
                     s.get("product_name", ""), now_ts, now_ts + 86400)
                )
                added += conn.execute("SELECT changes()").fetchone()[0]
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("SYS-37 Gumroad-Sync: %s", e)

    # Digistore24-Käufer
    try:
        from modules.digistore_client import get_recent_orders
        orders = await asyncio.wait_for(asyncio.to_thread(get_recent_orders, limit=50), timeout=20)
        conn = sqlite3.connect(_SYS37_DB)
        for o in (orders or []):
            email = o.get("buyer_email", "") if isinstance(o, dict) else ""
            if not email:
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO buyers (email, name, source, product, bought_at, next_followup) "
                    "VALUES (?,?,?,?,?,?)",
                    (email, o.get("buyer_name", ""), "digistore24",
                     o.get("product_name", ""), now_ts, now_ts + 86400)
                )
                added += conn.execute("SELECT changes()").fetchone()[0]
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("SYS-37 DS24-Sync: %s", e)

    return added


async def run_sys37_template_conversion(limit: int = 30) -> Dict[str, Any]:
    """
    SYS-37: Template-Käufer → Mandat-Conversion.
    3-Schritt Follow-Up: Tag 1, Tag 3, Tag 7 mit eskalierendem Angebot.
    """
    await sync_sys37_template_buyers()

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", os.getenv("EMAIL_FROM", ""))
    smtp_pass = os.getenv("SMTP_PASS", os.getenv("EMAIL_PASSWORD", ""))

    now_ts = int(time.time())
    _sys37_db()
    conn = sqlite3.connect(_SYS37_DB)
    rows = conn.execute(
        "SELECT id, email, name, followup_step FROM buyers "
        "WHERE converted=0 AND bounced=0 AND next_followup<=? AND followup_step<? LIMIT ?",
        (now_ts, len(_SYS37_FOLLOWUP_SEQUENCE), limit)
    ).fetchall()

    sent = 0
    for row_id, email, name, step in rows:
        tpl = _SYS37_FOLLOWUP_SEQUENCE[step]
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = tpl["subject"]
            msg["From"]    = smtp_user
            msg["To"]      = email
            body = tpl["body"].replace("{name}", name or "")
            msg.attach(MIMEText(body, "plain", "utf-8"))

            if smtp_user and smtp_pass:
                with smtplib.SMTP(smtp_host, smtp_port) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_user, email, msg.as_string())

            next_step    = step + 1
            days_between = [1, 3, 7]
            next_ts      = now_ts + days_between[min(next_step, len(days_between) - 1)] * 86400
            conn.execute(
                "UPDATE buyers SET followup_step=?, next_followup=? WHERE id=?",
                (next_step, next_ts, row_id)
            )
            conn.commit()
            sent += 1
            log.info("SYS-37 step %d → %s", step, email)
            await asyncio.sleep(1.5)
        except Exception as e:
            log.warning("SYS-37 error %s: %s", email, e)

    conn.close()
    return {"ok": True, "system": "SYS-37", "sent": sent, "total_buyers": len(rows)}


async def run_priority_cluster(daily_limit: int = 20) -> Dict[str, Any]:
    """
    Startet SYS-18 → SYS-23 → SYS-37 sequenziell.
    Ein gewonnener Kunde senkt Akquisekosten aller Nachbarn auf nahe null.
    """
    results: Dict[str, Any] = {}
    for fn, key in [
        (run_sys18_kanzlei_outreach, "sys18"),
        (run_sys23_shop_upsell,      "sys23"),
        (run_sys37_template_conversion, "sys37"),
    ]:
        try:
            results[key] = await fn(daily_limit)
        except Exception as e:
            results[key] = {"ok": False, "error": str(e)}
    log.info("Priority Cluster SYS-18/23/37 fertig: %s", results)
    return {"ok": True, "priority_cluster": results}


# Singleton
_bot: Optional[MegaBotUmsatzmaschine] = None


def get_umsatzmaschine() -> MegaBotUmsatzmaschine:
    global _bot
    if _bot is None:
        _bot = MegaBotUmsatzmaschine()
        try:
            from modules.megabot_eu_compliance_engine import add_compliance_to_megabot
            add_compliance_to_megabot(_bot)
        except Exception as e:
            log.warning("EU Compliance Engine nicht geladen: %s", e)
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
        if cmd in ("kfw", "kfw-antrag"):
            overrides: Dict[str, Any] = {}
            if len(sys.argv) > 2 and Path(sys.argv[2]).exists():
                overrides = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            elif len(sys.argv) > 2:
                overrides["antragsteller"] = sys.argv[2]
            if len(sys.argv) > 3:
                overrides["unternehmen"] = sys.argv[3]
            if len(sys.argv) > 4:
                overrides["kredit_betrag"] = int(sys.argv[4])
            pdf = bot.generate_kfw_antrag(overrides)
            print(json.dumps({"ok": True, "pdf": pdf}, indent=2, ensure_ascii=False))
            return
        r = await run_autonomous_cycle()
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))

    print("MegaBot Umsatzmaschine — production module (8 Systeme + Stripe + PDF)")
    asyncio.run(_main())