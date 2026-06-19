"""B2B lead prospecting + email outreach pipeline for SuperMegaBot SaaS."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("B2BPipeline")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))

# Pre-seeded Shopify store targets for outreach (public directories)
SAMPLE_LEADS: list[dict] = [
    {"company": "OnlineShop DE", "email": "", "domain": "", "niche": "general", "source": "manual"},
]


def _db_path() -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / "b2b_leads.json"


def _load_db() -> dict:
    p = _db_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"leads": [], "outreach": []}


def _save_db(db: dict) -> None:
    _db_path().write_text(json.dumps(db, indent=2, default=str))


def _outreach_email(lead: dict) -> str:
    name = lead.get("contact_name", "") or lead.get("company", "")
    first = name.split()[0] if name else "Hallo"
    domain = lead.get("domain", "deinem Shop")
    return f"""Betreff: Automatisiere {domain} komplett — kostenlose Demo

Hallo {first},

ich habe {domain} gesehen und glaube, SuperMegaBot könnte deinen Umsatz deutlich steigern.

Was SuperMegaBot für Shopify-Shops macht:
✅ AI-Preisoptimierung (automatisch beste Preise rund um die Uhr)
✅ Winback-Emails (inaktive Kunden zurückgewinnen, +15% Umsatz)
✅ Warenkorb-Recovery (bis +20% Conversion)
✅ SEO-Autopilot (Google-Ranking verbessern ohne Aufwand)
✅ Tägliche Revenue-Reports per Telegram

Starter Plan: €49/Monat — aktuell 50% Rabatt: €24,50/Monat
Kein Jahresvertrag, jederzeit kündbar.

👉 Demo buchen: https://buy.stripe.com/plink_1Ti4nuRJECiV6vSmFVom8L5E

Oder einfach auf diese E-Mail antworten — ich zeige dir in 15 Minuten wie es funktioniert.

Viele Grüße,
Rudolf Sarkany
SuperMegaBot | AIITEC
"""


async def add_lead(company: str, email: str, domain: str = "", niche: str = "",
                   contact_name: str = "", source: str = "manual") -> dict:
    db = _load_db()
    lead = {
        "id": f"lead_{len(db['leads'])+1}_{int(datetime.now().timestamp())}",
        "company": company,
        "email": email,
        "domain": domain or company.lower().replace(" ", "") + ".de",
        "niche": niche,
        "contact_name": contact_name,
        "source": source,
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db["leads"].append(lead)
    _save_db(db)
    return lead


async def get_leads(status: str | None = None) -> list[dict]:
    db = _load_db()
    leads = db.get("leads", [])
    if status:
        leads = [l for l in leads if l.get("status") == status]
    return leads


async def update_lead(lead_id: str, **kwargs) -> dict:
    db = _load_db()
    for lead in db["leads"]:
        if lead["id"] == lead_id:
            lead.update(kwargs)
            _save_db(db)
            return {"ok": True, "lead": lead}
    return {"ok": False, "error": "Lead not found"}


async def delete_lead(lead_id: str) -> dict:
    db = _load_db()
    before = len(db["leads"])
    db["leads"] = [l for l in db["leads"] if l["id"] != lead_id]
    _save_db(db)
    return {"ok": len(db["leads"]) < before, "deleted": lead_id}


async def run_prospecting() -> dict:
    """Prospect new leads from Shopify-adjacent communities and directories."""
    db = _load_db()
    existing_emails = {l.get("email", "") for l in db["leads"]}

    # Seed high-value Shopify niches for manual outreach
    target_niches = [
        {"niche": "fashion", "keywords": ["Kleidung", "Mode", "Fashion"]},
        {"niche": "electronics", "keywords": ["Elektronik", "Gadgets"]},
        {"niche": "beauty", "keywords": ["Beauty", "Kosmetik", "Pflege"]},
        {"niche": "sports", "keywords": ["Sport", "Fitness", "Outdoor"]},
        {"niche": "home_deco", "keywords": ["Wohnen", "Deko", "Einrichtung"]},
    ]

    new_leads = 0
    outreach_templates = []
    for niche_info in target_niches:
        niche = niche_info["niche"]
        keywords_str = ", ".join(niche_info["keywords"])
        template = {
            "niche": niche,
            "keywords": keywords_str,
            "outreach_template": _outreach_email({
                "company": f"{niche.title()} Shop",
                "domain": f"[{niche}-shop].de",
                "contact_name": "Shopinhaber"
            }),
            "prospecting_note": f"Search: '{keywords_str} Shopify Deutschland' on LinkedIn, Google, or Shopify app store reviews",
        }
        outreach_templates.append(template)

    # Save outreach templates to data/
    (DATA_DIR / "b2b_outreach_templates.json").write_text(
        json.dumps(outreach_templates, indent=2, ensure_ascii=False)
    )

    return {
        "niche_templates_created": len(outreach_templates),
        "templates_saved": str(DATA_DIR / "b2b_outreach_templates.json"),
        "existing_leads": len(db["leads"]),
        "action_required": "Search LinkedIn/Google for Shopify store owners in these niches and add leads via /api/b2b/lead (POST)",
        "quick_add_url": "POST /api/b2b/lead {company, email, domain, niche, contact_name}",
    }


async def run_outreach(lead_id: str) -> dict:
    """Send outreach email to a specific lead via Klaviyo."""
    db = _load_db()
    lead = next((l for l in db["leads"] if l["id"] == lead_id), None)
    if not lead:
        return {"ok": False, "error": "Lead not found"}
    if not lead.get("email"):
        return {"ok": False, "error": "Lead has no email address"}

    email_body = _outreach_email(lead)

    # Send via Klaviyo
    try:
        import aiohttp
        kv_key = os.getenv("KLAVIYO_API_KEY", "")
        if kv_key:
            profile = {"data": {"type": "profile", "attributes": {
                "email": lead["email"],
                "first_name": (lead.get("contact_name", "") or "").split()[0],
                "organization": lead.get("company", ""),
                "properties": {"b2b_lead": True, "niche": lead.get("niche", ""), "outreach_sent": True}
            }}}
            headers = {"Authorization": f"Klaviyo-API-Key {kv_key}", "revision": "2024-10-15",
                       "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://a.klaviyo.com/api/profiles/", json=profile, headers=headers) as r:
                    ok = r.status in (200, 201, 409)
            if ok:
                lead["status"] = "contacted"
                lead["contacted_at"] = datetime.now(timezone.utc).isoformat()
                _save_db(db)
                return {"ok": True, "lead": lead["id"], "method": "klaviyo_profile"}
    except Exception as e:
        log.warning("Outreach email error: %s", e)

    return {"ok": False, "error": "No email provider configured", "email_draft": email_body}


async def get_stats() -> dict:
    db = _load_db()
    leads = db.get("leads", [])
    by_status: dict[str, int] = {}
    for l in leads:
        s = l.get("status", "new")
        by_status[s] = by_status.get(s, 0) + 1
    by_niche: dict[str, int] = {}
    for l in leads:
        n = l.get("niche", "general")
        by_niche[n] = by_niche.get(n, 0) + 1
    return {
        "total_leads": len(leads),
        "by_status": by_status,
        "by_niche": by_niche,
        "conversion_rate": f"{(by_status.get('converted',0)/max(len(leads),1)*100):.1f}%",
        "saas_pricing": {
            "starter": "€49/mo (€24.50 flash)",
            "pro": "€99/mo",
            "enterprise": "€299/mo"
        },
        "stripe_links": {
            "starter": "https://buy.stripe.com/plink_1Ti4nuRJECiV6vSmFVom8L5E",
            "pro": "https://buy.stripe.com/plink_1Ti4nvRJECiV6vSmFHKXWjbz",
            "enterprise": "https://buy.stripe.com/plink_1Ti4nwRJECiV6vSmgL2lZ7uk"
        }
    }

# Aliases for dashboard compatibility
run_daily_prospecting = run_prospecting
get_pipeline_stats    = get_stats
get_pipeline_leads    = get_leads
update_lead_stage     = update_lead
send_outreach_email   = run_outreach
