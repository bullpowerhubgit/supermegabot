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
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("B2BPipeline")

LEAD_SOURCES = ["shopify_app_store_scrape", "instagram_search", "manual_import"]

PIPELINE_STAGES = [
    "new", "contacted", "interested", "demo_scheduled",
    "proposal_sent", "closed_won", "closed_lost"
]

# Subscription tier MRR values for pipeline value calculation
_TIER_MRR = {"starter": 49.0, "pro": 99.0, "enterprise": 299.0}

# E-mail validation regex (RFC-5321 compatible subset)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ── Input validators ─────────────────────────────────────────────────────────

def _validate_email(email: str) -> Tuple[bool, str]:
    """Returns (valid, normalised_email). Empty email is accepted (outreach via other channel)."""
    if not email:
        return True, ""
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        return False, email
    return True, email


def _validate_stage(stage: str) -> Tuple[bool, str]:
    """Returns (valid, stage). Logs and returns error string when invalid."""
    if stage not in PIPELINE_STAGES:
        return False, f"Invalid stage '{stage}'. Valid stages: {PIPELINE_STAGES}"
    return True, stage


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

async def _claude_complete(
    prompt: str,
    max_tokens: int = 1024,
    retries: int = 3,
) -> str:
    """Call Claude API with retry on 429/500/503."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not HAS_AIOHTTP:
        return ""
    backoff = 2.0
    for attempt in range(1, retries + 1):
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
                    if resp.status in (429, 500, 503):
                        log.warning(
                            "Claude API %s (attempt %s/%s), retrying in %.0fs",
                            resp.status, attempt, retries, backoff,
                        )
                        if attempt < retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        text = await resp.text()
                        log.warning("Claude API %s final: %s", resp.status, text[:200])
                        return ""
                    if resp.status != 200:
                        text = await resp.text()
                        log.warning("Claude API %s: %s", resp.status, text[:200])
                        return ""
                    data = await resp.json()
                    return data["content"][0]["text"]
        except aiohttp.ClientError as exc:
            log.warning("Claude API network error (attempt %s/%s): %s", attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
        except Exception as exc:
            log.error("Claude API unexpected error: %s", exc)
            return ""
    return ""


# ── JSON extraction helper ────────────────────────────────────────────────────

def _extract_json(raw: str) -> Any:
    """
    Robustly extract JSON from a string that may be wrapped in markdown fences.
    Raises json.JSONDecodeError on parse failure.
    """
    clean = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    if clean.startswith("```"):
        lines = clean.split("\n")
        # remove first line (```json or ```) and last ``` line
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        clean = "\n".join(inner).strip()
    # Fallback: find first [ or { and last ] or }
    if not clean or clean[0] not in ("{", "["):
        start_obj = clean.find("{")
        start_arr = clean.find("[")
        starts = [i for i in (start_obj, start_arr) if i >= 0]
        if starts:
            clean = clean[min(starts):]
    return json.loads(clean)


# ── Core functions ───────────────────────────────────────────────────────────

async def find_shopify_store_owners(
    niche: str = "dropshipping", limit: int = 20
) -> List[Dict]:
    """
    Nutzt Claude AI um potenzielle Shopify Store-Betreiber zu finden.
    Returns a list of dicts with store_name, website, niche, score.
    """
    if not niche or not niche.strip():
        log.warning("find_shopify_store_owners: empty niche, using 'dropshipping'")
        niche = "dropshipping"
    limit = max(1, min(limit, 50))

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
        log.warning("find_shopify_store_owners: empty Claude response for niche=%s", niche)
        return []
    try:
        leads = _extract_json(raw)
        if not isinstance(leads, list):
            log.warning("find_shopify_store_owners: expected list, got %s", type(leads).__name__)
            return []
        result = []
        for item in leads:
            if not isinstance(item, dict) or not item.get("store_name"):
                continue
            result.append({
                "store_name": str(item.get("store_name", "")),
                "website": str(item.get("website", "")),
                "niche": niche,
                "estimated_monthly_revenue": str(item.get("estimated_monthly_revenue", "")),
                "contact_hint": str(item.get("contact_hint", "")),
                "score": max(0, min(100, int(item.get("score", 50)))),
            })
        log.info("find_shopify_store_owners: found %s leads for niche=%s", len(result), niche)
        return result
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        log.warning("find_shopify_store_owners parse error: %s — raw[:200]: %s", exc, raw[:200])
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
    All dict key accesses are .get() guarded to handle missing keys safely.
    """
    if not isinstance(lead, dict):
        log.warning("score_lead: received non-dict input (%s)", type(lead).__name__)
        return 0

    score = 0
    website = str(lead.get("website") or "").lower()
    revenue = str(lead.get("estimated_monthly_revenue") or "").lower()
    notes   = str(lead.get("notes") or "").lower()
    source  = str(lead.get("source") or "").lower()

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
    product_count = lead.get("product_count")
    try:
        product_count = int(product_count or 0)
    except (TypeError, ValueError):
        product_count = 0
    if product_count > 5 or "multiple" in notes:
        score += 15

    # Competitor automation
    if any(x in notes for x in ["automation", "automated", "competitor"]):
        score += 10

    # Existing score from AI (carry over partially)
    try:
        ai_score = int(lead.get("score") or 0)
    except (TypeError, ValueError):
        ai_score = 0
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
    """Fügt Lead zur Pipeline in Supabase hinzu. Dedupliziert nach E-Mail."""
    # Validate email
    email_valid, email = _validate_email(email)
    if not email_valid:
        log.warning("add_lead: invalid email format '%s' — skipping", email)
        return {"error": f"Invalid email format: {email}"}

    # Validate required fields
    if not company and not website:
        log.warning("add_lead: both company and website are empty")
        return {"error": "company or website must be provided"}

    if source not in LEAD_SOURCES:
        source = "manual_import"

    # Clamp score
    score = max(0, min(100, int(score)))

    now = datetime.now(timezone.utc).isoformat()

    try:
        client = _supa()

        # Deduplication: check if email already exists (only when email provided)
        if email:
            existing = client.table("b2b_leads").select("id, stage").eq("email", email).execute()
            if existing.data:
                existing_lead = existing.data[0]
                log.info(
                    "add_lead: duplicate email %s (lead_id=%s, stage=%s) — skipping insert",
                    email, existing_lead.get("id"), existing_lead.get("stage"),
                )
                return {"skipped": True, "reason": "duplicate_email", **existing_lead}

        row = {
            "email": email or None,
            "name": name or None,
            "company": company or None,
            "website": website or None,
            "niche": niche or None,
            "source": source,
            "score": score,
            "stage": "new",
            "notes": notes or None,
            "monthly_revenue_est": monthly_revenue_est if monthly_revenue_est else None,
            "created_at": now,
            "updated_at": now,
        }
        result = client.table("b2b_leads").insert(row).execute()
        data = result.data
        if data:
            log.info("add_lead: inserted lead_id=%s company=%s", data[0].get("id"), company)
            return data[0]
        return row
    except Exception as exc:
        log.error("add_lead error: %s", exc)
        return {"error": str(exc)}


async def update_lead_stage(lead_id: int, stage: str, notes: str = "") -> Dict:
    """Bewegt Lead durch Pipeline-Stages. Validiert Stage-Name."""
    if not isinstance(lead_id, int) or lead_id <= 0:
        return {"error": f"Invalid lead_id: {lead_id}"}

    valid, err = _validate_stage(stage)
    if not valid:
        log.warning("update_lead_stage: %s", err)
        return {"error": err}

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
        if data:
            log.info("update_lead_stage: lead_id=%s -> stage=%s", lead_id, stage)
            return data[0]
        # Lead not found
        log.warning("update_lead_stage: lead_id=%s not found", lead_id)
        return {"error": f"Lead {lead_id} not found", "id": lead_id, "stage": stage}
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
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected dict, got {type(parsed).__name__}")
        # Ensure required keys exist
        return {
            "email_subject": str(parsed.get("email_subject", f"SuperMegaBot für {company}"))[:80],
            "email_body": str(parsed.get("email_body", raw[:800])),
            "telegram_msg": str(parsed.get("telegram_msg", raw[:100])),
        }
    except Exception as exc:
        log.warning("generate_outreach_message parse error: %s", exc)
        return {
            "email_subject": f"SuperMegaBot für {company}",
            "email_body": raw[:800],
            "telegram_msg": raw[:100],
        }


async def send_outreach_email(lead_id: int) -> bool:
    """Sendet Outreach-Email via Mailchimp Transactional (Mandrill), trackt in DB.
    Verhindert doppeltes Senden durch Prüfung von outreach_sent_at."""
    if not isinstance(lead_id, int) or lead_id <= 0:
        log.warning("send_outreach_email: invalid lead_id %s", lead_id)
        return False
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

        # Deduplication guard — never send twice
        if lead.get("outreach_sent_at"):
            log.info(
                "send_outreach_email: lead %s already contacted at %s — skipping",
                lead_id, lead["outreach_sent_at"],
            )
            return True  # Not an error, already done

        # Validate email format before sending
        email_valid, email = _validate_email(lead["email"])
        if not email_valid:
            log.warning("send_outreach_email: lead %s has invalid email '%s'", lead_id, lead["email"])
            return False

        msg = await generate_outreach_message(lead)

        mc_key = os.getenv("MAILCHIMP_API_KEY", "")
        email_sent = False
        if mc_key and HAS_AIOHTTP:
            # Use Mailchimp Transactional (Mandrill) if available
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                    async with s.post(
                        "https://mandrillapp.com/api/1.0/messages/send",
                        json={
                            "key": mc_key,
                            "message": {
                                "from_email": os.getenv("FROM_EMAIL", "hello@supermegabot.io"),
                                "from_name": "SuperMegaBot",
                                "to": [{"email": email, "name": lead.get("name", "")}],
                                "subject": msg["email_subject"],
                                "text": msg["email_body"],
                            },
                        },
                    ) as resp:
                        resp_data = await resp.json(content_type=None)
                        if resp.status in (200, 201):
                            email_sent = True
                            log.info(
                                "Mandrill: email sent to %s (lead %s)", email, lead_id
                            )
                        else:
                            log.warning("Mandrill API %s: %s", resp.status, resp_data)
            except aiohttp.ClientError as exc:
                log.warning("Mandrill network error: %s", exc)
            except Exception as exc:
                log.warning("Mandrill send error: %s", exc)
        else:
            log.info("Mailchimp not configured — skipping email for lead %s", lead_id)

        # Track outreach in DB regardless (idempotent timestamp write)
        now = datetime.now(timezone.utc).isoformat()
        client.table("b2b_leads").update({
            "outreach_sent_at": now,
            "stage": "contacted",
            "updated_at": now,
        }).eq("id", lead_id).execute()
        log.info("Outreach tracked for lead %s (%s), email_sent=%s", lead_id, email, email_sent)
        return True
    except Exception as exc:
        log.error("send_outreach_email error: %s", exc)
        return False


async def get_pipeline_stats() -> Dict:
    """
    Returns pipeline statistics including conversion rate and pipeline value.
    Robust against Supabase unavailability — returns error dict, never raises.
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

        log.info("Pipeline stats: %s total leads, %s closed_won, conversion=%.1f%%",
                 total, closed_won, conversion)
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


async def get_pipeline_leads(
    stage: Optional[str] = None, limit: int = 50
) -> List[Dict]:
    """Holt Leads aus Supabase, optional nach Stage gefiltert."""
    # Validate stage filter
    if stage is not None and stage not in PIPELINE_STAGES:
        log.warning("get_pipeline_leads: invalid stage filter '%s' — ignoring", stage)
        stage = None

    limit = max(1, min(limit, 200))
    try:
        client = _supa()
        query = client.table("b2b_leads").select("*").order("created_at", desc=True).limit(limit)
        if stage:
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
    3. Fügt Top-Leads (score >= 60) zur Pipeline hinzu — ohne Duplikate
    4. Telegram-Notification mit Summary

    Supabase-Fehler beim Hinzufügen einzelner Leads werden geloggt und gezählt,
    aber unterbrechen nicht die gesamte Schleife (kein Lead-Verlust durch Exception).
    """
    if niches is None:
        niches = ["dropshipping", "print-on-demand", "digital-products"]

    total_found = 0
    total_added = 0
    total_skipped = 0
    all_errors: List[str] = []

    for niche in niches:
        try:
            leads = await find_shopify_store_owners(niche=niche, limit=10)
            total_found += len(leads)
            for lead in leads:
                score = await score_lead(lead)
                if score >= 60:
                    add_result = await add_lead(
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
                    if add_result.get("error"):
                        err = f"{niche}/{lead.get('store_name','?')}: {add_result['error']}"
                        log.warning("run_daily_prospecting: add_lead failed — %s", err)
                        all_errors.append(err)
                    elif add_result.get("skipped"):
                        total_skipped += 1
                    else:
                        total_added += 1
            await asyncio.sleep(1)  # Rate limiting
        except Exception as exc:
            err = f"Nische {niche}: {exc}"
            log.error("run_daily_prospecting error — %s", err)
            all_errors.append(err)

    summary = (
        f"B2B Prospecting: {total_found} gefunden, {total_added} hinzugefügt, "
        f"{total_skipped} Duplikate übersprungen ({', '.join(niches)})"
    )
    if all_errors:
        summary += f" | Fehler: {'; '.join(all_errors[:2])}"

    await _tg(
        f"B2B Prospecting abgeschlossen\n"
        f"Gefunden: {total_found} | Hinzugefügt: {total_added} | Duplikate: {total_skipped}\n"
        f"Nischen: {', '.join(niches)}"
    )
    log.info(summary)
    return {
        "found": total_found,
        "added": total_added,
        "skipped_duplicates": total_skipped,
        "niches": niches,
        "errors": all_errors,
    }
