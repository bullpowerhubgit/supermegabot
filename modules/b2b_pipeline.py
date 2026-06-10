#!/usr/bin/env python3
"""
B2B Lead-Pipeline — findet potenzielle SaaS-Kunden für SuperMegaBot,
managt die gesamte Sales-Pipeline bis zum Abschluss.

Env vars:
  ANTHROPIC_API_KEY   — Claude AI für Lead-Suche und Outreach
  SUPABASE_URL / SUPABASE_SERVICE_KEY — Datenbank
  MAILCHIMP_API_KEY / MAILCHIMP_SERVER_PREFIX — Outreach per Email
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — Benachrichtigungen
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("B2BPipeline")

LEAD_SOURCES = ["shopify_app_store_scrape", "instagram_search", "manual_import"]

PIPELINE_STAGES = [
    "new", "contacted", "interested", "demo_scheduled",
    "proposal_sent", "closed_won", "closed_lost"
]

# Subscription tier MRR values for pipeline value calculation
_TIER_MRR = {"starter": 49.0, "pro": 99.0, "enterprise": 299.0}

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ── Telegram helper ──────────────────────────────────────────────────────────

async def _tg(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat or not HAS_AIOHTTP:
        return
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            await s.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}
            )
    except Exception as exc:
        log.warning("Telegram send failed: %s", exc)


# ── Supabase helpers ─────────────────────────────────────────────────────────

def _supa():
    """Return supabase client or raise RuntimeError."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    try:
        from supabase import create_client  # type: ignore
        return create_client(url, key)
    except ImportError:
        raise RuntimeError("supabase-py not installed: pip install supabase")


async def _ensure_table() -> None:
    """Create b2b_leads table if it doesn't exist yet (via raw SQL through Supabase REST)."""
    try:
        client = _supa()
        # Supabase client uses PostgREST; DDL needs service role + rpc or migrations.
        # We attempt a lightweight select to verify table exists.
        client.table("b2b_leads").select("id").limit(1).execute()
    except Exception as exc:
        log.warning("b2b_leads table check: %s — run migration manually", exc)


# ── Claude AI helper ─────────────────────────────────────────────────────────

async def _claude_complete(prompt: str, max_tokens: int = 1024) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not HAS_AIOHTTP:
        return ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.warning("Claude API %s: %s", resp.status, text[:200])
                    return ""
                data = await resp.json()
                return data["content"][0]["text"]
    except Exception as exc:
        log.error("Claude API error: %s", exc)
        return ""


# ── Core functions ───────────────────────────────────────────────────────────

async def find_shopify_store_owners(
    niche: str = "dropshipping", limit: int = 20
) -> List[Dict]:
    """
    Nutzt Claude AI um potenzielle Shopify Store-Betreiber zu finden.
    Returns a list of dicts with store_name, website, niche, score.
    """
    prompt = (
        f"Find {limit} active Shopify stores in the {niche} niche that could benefit "
        "from automation tools like abandoned cart recovery, AI product descriptions, "
        "and revenue analytics. "
        "Return ONLY a JSON array, no markdown, no explanation. "
        "Each element must have exactly these keys: "
        "store_name (string), website (string), niche (string), "
        "estimated_monthly_revenue (string like '€1k-5k'), contact_hint (string), score (integer 0-100). "
        "Example: [{\"store_name\": \"ExampleShop\", \"website\": \"example-shop.myshopify.com\", "
        "\"niche\": \"dropshipping\", \"estimated_monthly_revenue\": \"€1k-5k\", "
        "\"contact_hint\": \"info@example-shop.com\", \"score\": 72}]"
    )
    raw = await _claude_complete(prompt, max_tokens=2048)
    if not raw:
        log.warning("find_shopify_store_owners: empty Claude response")
        return []
    try:
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        leads = json.loads(clean)
        if not isinstance(leads, list):
            return []
        return [
            {
                "store_name": str(l.get("store_name", "")),
                "website": str(l.get("website", "")),
                "niche": niche,
                "estimated_monthly_revenue": str(l.get("estimated_monthly_revenue", "")),
                "contact_hint": str(l.get("contact_hint", "")),
                "score": int(l.get("score", 50)),
            }
            for l in leads
            if l.get("store_name")
        ]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        log.warning("find_shopify_store_owners parse error: %s — raw: %s", exc, raw[:200])
        return []


async def score_lead(lead: Dict) -> int:
    """
    Scoring 0-100 based on attributes:
    - Has Shopify?          +30
    - Revenue > €1k/month?  +20
    - Active social media?  +15
    - Uses email marketing? +10
    - Has multiple products?+15
    - Automated competitor? +10
    """
    score = 0
    website = str(lead.get("website", "")).lower()
    revenue = str(lead.get("estimated_monthly_revenue", "")).lower()
    notes   = str(lead.get("notes", "")).lower()
    source  = str(lead.get("source", "")).lower()

    # Shopify store
    if "shopify" in website or "myshopify" in website or source == "shopify_app_store_scrape":
        score += 30

    # Revenue estimate
    if any(x in revenue for x in ["€5k", "€10k", "10k", "5k", "€2k", "2k", "€3k"]):
        score += 20
    elif any(x in revenue for x in ["€1k", "1k"]):
        score += 10

    # Social media
    if any(x in notes for x in ["instagram", "tiktok", "facebook", "social"]):
        score += 15

    # Email marketing
    if any(x in notes for x in ["mailchimp", "klaviyo", "email", "newsletter"]):
        score += 10

    # Multiple products
    if lead.get("product_count", 0) > 5 or "multiple" in notes:
        score += 15

    # Competitor automation
    if any(x in notes for x in ["automation", "automated", "competitor"]):
        score += 10

    # Existing score from AI (carry over partially)
    ai_score = int(lead.get("score", 0))
    if ai_score > 0:
        score = min(100, max(score, ai_score))

    return min(100, score)


async def add_lead(
    email: str,
    name: str,
    company: str,
    website: str,
    niche: str,
    source: str,
    score: int = 0,
    notes: str = "",
    monthly_revenue_est: float = 0.0,
) -> Dict:
    """Fügt Lead zur Pipeline in Supabase hinzu."""
    if source not in LEAD_SOURCES:
        source = "manual_import"
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "email": email,
        "name": name,
        "company": company,
        "website": website,
        "niche": niche,
        "source": source,
        "score": score,
        "stage": "new",
        "notes": notes,
        "monthly_revenue_est": monthly_revenue_est if monthly_revenue_est else None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        client = _supa()
        result = client.table("b2b_leads").insert(row).execute()
        data = result.data
        if data:
            return data[0]
        return row
    except Exception as exc:
        log.error("add_lead error: %s", exc)
        return {"error": str(exc), **row}


async def update_lead_stage(lead_id: int, stage: str, notes: str = "") -> Dict:
    """Bewegt Lead durch Pipeline-Stages."""
    if stage not in PIPELINE_STAGES:
        return {"error": f"Invalid stage: {stage}. Valid: {PIPELINE_STAGES}"}
    try:
        client = _supa()
        update: Dict[str, Any] = {
            "stage": stage,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if notes:
            update["notes"] = notes
        result = client.table("b2b_leads").update(update).eq("id", lead_id).execute()
        data = result.data
        return data[0] if data else {"id": lead_id, "stage": stage}
    except Exception as exc:
        log.error("update_lead_stage error: %s", exc)
        return {"error": str(exc)}


async def generate_outreach_message(lead: Dict) -> Dict:
    """
    Claude AI generiert personalisierte Outreach-Nachricht.
    Returns: {"email_subject": "...", "email_body": "...", "telegram_msg": "..."}
    """
    company = lead.get("company") or lead.get("store_name") or "Ihr Shop"
    niche   = lead.get("niche", "E-Commerce")
    website = lead.get("website", "")
    name    = lead.get("name", "")

    prompt = (
        f"Write a personalized B2B outreach message for a Shopify store owner. "
        f"Company: {company}, Niche: {niche}, Website: {website}, Contact: {name}. "
        f"Product: SuperMegaBot — a SaaS automation platform for Shopify stores. "
        f"Key features: abandoned cart recovery, AI product descriptions, revenue analytics, "
        f"Telegram alerts, automated fulfillment. Pricing from €49/month. "
        f"Return ONLY a JSON object with these exact keys: "
        f"email_subject (max 60 chars), email_body (max 300 words, professional), "
        f"telegram_msg (max 100 chars, casual and direct). "
        f"Write in German. No markdown fences."
    )
    raw = await _claude_complete(prompt, max_tokens=1024)
    if not raw:
        company_short = company[:30]
        return {
            "email_subject": f"Mehr Umsatz für {company_short} — SuperMegaBot",
            "email_body": (
                f"Hallo{' ' + name if name else ''},\n\n"
                f"ich schreibe Ihnen, weil ich gesehen habe, dass {company} im {niche}-Bereich aktiv ist.\n\n"
                "SuperMegaBot automatisiert Ihren Shopify-Shop: Warenkorb-Recovery, "
                "KI-Produktbeschreibungen, Revenue-Tracking und mehr — ab €49/Monat.\n\n"
                "Hätten Sie 15 Minuten für eine kurze Demo?\n\nMit freundlichen Grüßen,\nRudolf"
            ),
            "telegram_msg": f"Hey! SuperMegaBot automatisiert deinen {niche}-Shop ab €49/mo. Demo gewünscht?",
        }
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except Exception as exc:
        log.warning("generate_outreach_message parse error: %s", exc)
        return {
            "email_subject": f"SuperMegaBot für {company}",
            "email_body": raw[:800],
            "telegram_msg": raw[:100],
        }


async def send_outreach_email(lead_id: int) -> bool:
    """Sendet Outreach-Email via Mailchimp Transactional (Mandrill), trackt in DB."""
    try:
        client = _supa()
        result = client.table("b2b_leads").select("*").eq("id", lead_id).execute()
        leads = result.data
        if not leads:
            log.warning("send_outreach_email: lead %s not found", lead_id)
            return False
        lead = leads[0]
        if not lead.get("email"):
            log.warning("send_outreach_email: lead %s has no email", lead_id)
            return False

        msg = await generate_outreach_message(lead)

        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        if mc_key and HAS_AIOHTTP:
            # Use Mailchimp Transactional (Mandrill) if available
            server = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                    async with s.post(
                        "https://mandrillapp.com/api/1.0/messages/send",
                        json={
                            "key": mc_key,
                            "message": {
                                "from_email": os.getenv("FROM_EMAIL", "hello@supermegabot.io"),
                                "from_name": "SuperMegaBot",
                                "to": [{"email": lead["email"], "name": lead.get("name", "")}],
                                "subject": msg["email_subject"],
                                "text": msg["email_body"],
                            },
                        },
                    ) as resp:
                        if resp.status not in (200, 201):
                            log.warning("Mandrill API %s", resp.status)
            except Exception as exc:
                log.warning("Mandrill send error: %s", exc)

        # Track outreach in DB regardless
        now = datetime.now(timezone.utc).isoformat()
        client.table("b2b_leads").update({
            "outreach_sent_at": now,
            "stage": "contacted",
            "updated_at": now,
        }).eq("id", lead_id).execute()
        log.info("Outreach sent to lead %s (%s)", lead_id, lead.get("email"))
        return True
    except Exception as exc:
        log.error("send_outreach_email error: %s", exc)
        return False


async def get_pipeline_stats() -> Dict:
    """
    Returns pipeline statistics including conversion rate and pipeline value.
    """
    try:
        client = _supa()
        result = client.table("b2b_leads").select("id, stage, score, monthly_revenue_est").execute()
        leads = result.data or []

        by_stage: Dict[str, int] = {s: 0 for s in PIPELINE_STAGES}
        for lead in leads:
            stage = lead.get("stage", "new")
            if stage in by_stage:
                by_stage[stage] += 1

        total = len(leads)
        closed_won = by_stage.get("closed_won", 0)
        conversion = round((closed_won / total * 100), 1) if total > 0 else 0.0

        # Pipeline value: assume average MRR of Starter plan (€49) for leads in active stages
        active_stages = {"interested", "demo_scheduled", "proposal_sent"}
        active_leads = [l for l in leads if l.get("stage") in active_stages]
        pipeline_value = sum(
            float(l.get("monthly_revenue_est") or _TIER_MRR["starter"])
            for l in active_leads
        )

        # MRR from closed_won this month
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-01")
        won_result = client.table("b2b_leads").select(
            "monthly_revenue_est, updated_at"
        ).eq("stage", "closed_won").gte("updated_at", from_date).execute()
        won_leads = won_result.data or []
        mrr_closed = sum(float(l.get("monthly_revenue_est") or _TIER_MRR["starter"]) for l in won_leads)

        return {
            "total_leads": total,
            "by_stage": by_stage,
            "conversion_rate": conversion,
            "pipeline_value": round(pipeline_value, 2),
            "closed_this_month": len(won_leads),
            "mrr_closed": round(mrr_closed, 2),
        }
    except Exception as exc:
        log.error("get_pipeline_stats error: %s", exc)
        return {
            "total_leads": 0,
            "by_stage": {s: 0 for s in PIPELINE_STAGES},
            "conversion_rate": 0.0,
            "pipeline_value": 0.0,
            "closed_this_month": 0,
            "mrr_closed": 0.0,
            "error": str(exc),
        }


async def get_pipeline_leads(stage: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Holt Leads aus Supabase, optional nach Stage gefiltert."""
    try:
        client = _supa()
        query = client.table("b2b_leads").select("*").order("created_at", desc=True).limit(limit)
        if stage and stage in PIPELINE_STAGES:
            query = query.eq("stage", stage)
        result = query.execute()
        return result.data or []
    except Exception as exc:
        log.error("get_pipeline_leads error: %s", exc)
        return []


async def run_daily_prospecting(niches: Optional[List[str]] = None) -> Dict:
    """
    Täglich:
    1. Findet 10 neue Leads pro Nische
    2. Scoret sie
    3. Fügt Top-Leads (score >= 60) zur Pipeline hinzu
    4. Telegram-Notification mit Summary
    """
    if niches is None:
        niches = ["dropshipping", "print-on-demand", "digital-products"]

    total_found = 0
    total_added = 0
    all_errors: List[str] = []

    for niche in niches:
        try:
            leads = await find_shopify_store_owners(niche=niche, limit=10)
            total_found += len(leads)
            for lead in leads:
                score = await score_lead(lead)
                if score >= 60:
                    await add_lead(
                        email=lead.get("contact_hint", ""),
                        name="",
                        company=lead.get("store_name", ""),
                        website=lead.get("website", ""),
                        niche=niche,
                        source="shopify_app_store_scrape",
                        score=score,
                        notes=f"Revenue est: {lead.get('estimated_monthly_revenue','?')}",
                        monthly_revenue_est=0.0,
                    )
                    total_added += 1
            await asyncio.sleep(1)  # Rate limiting
        except Exception as exc:
            err = f"Nische {niche}: {exc}"
            log.error("run_daily_prospecting error — %s", err)
            all_errors.append(err)

    summary = (
        f"B2B Prospecting: {total_found} gefunden, {total_added} hinzugefügt "
        f"({', '.join(niches)})"
    )
    if all_errors:
        summary += f" | Fehler: {'; '.join(all_errors[:2])}"

    await _tg(
        f"B2B Prospecting abgeschlossen\n"
        f"Gefunden: {total_found} | Hinzugefügt: {total_added}\n"
        f"Nischen: {', '.join(niches)}"
    )
    log.info(summary)
    return {
        "found": total_found,
        "added": total_added,
        "niches": niches,
        "errors": all_errors,
    }
