import os
import aiohttp
from claude_agent_sdk import tool

SB_URL = os.getenv("SUPABASE_URL", "https://qyrjeckzacjaazkpvnjk.supabase.co")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Accept-Profile": "public",
}


@tool(
    name="get_revenue",
    description="Zeigt letzte Einnahmen-Events aus allen Services (Stripe Subscriptions, Gumroad, Digistore24).",
    input_schema={"limit": int},
)
async def get_revenue_tool(args):
    limit = min(args.get("limit", 10), 50)
    url = f"{SB_URL}/rest/v1/hermes_events?event_type=eq.new_subscription&order=created_at.desc&limit={limit}"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(url, headers=SB_HEADERS, timeout=aiohttp.ClientTimeout(total=8))
            events = await r.json()
        if not events or isinstance(events, dict):
            return {"content": [{"type": "text", "text": "Noch keine Einnahmen-Events. Sobald jemand kauft erscheinen sie hier."}]}
        lines = [f"💰 `{e['service']}` — {e['message']} — {e['created_at'][:16]}" for e in events]
        text = f"*Letzte {len(lines)} Einnahmen:*\n" + "\n".join(lines)
    except Exception as e:
        text = f"Fehler beim Laden: {e}"
    return {"content": [{"type": "text", "text": text}]}


@tool(
    name="get_leads",
    description="Zeigt letzte Leads aus der Supabase leads-Tabelle.",
    input_schema={"limit": int},
)
async def get_leads_tool(args):
    limit = min(args.get("limit", 10), 50)
    url = f"{SB_URL}/rest/v1/leads?order=created_at.desc&limit={limit}"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(url, headers=SB_HEADERS, timeout=aiohttp.ClientTimeout(total=8))
            leads = await r.json()
        if not leads or isinstance(leads, dict):
            return {"content": [{"type": "text", "text": "Noch keine Leads."}]}
        lines = [f"📧 `{l['email']}` | {l.get('source','?')} | {l['created_at'][:16]}" for l in leads]
        text = f"*Letzte {len(lines)} Leads:*\n" + "\n".join(lines)
    except Exception as e:
        text = f"Fehler: {e}"
    return {"content": [{"type": "text", "text": text}]}
