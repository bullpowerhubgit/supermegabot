import os
import aiohttp
from claude_agent_sdk import tool

SB_URL = os.getenv("SUPABASE_URL", "https://qyrjeckzacjaazkpvnjk.supabase.co")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Accept-Profile": "public",
    "Content-Profile": "public",
    "Content-Type": "application/json",
}


@tool(
    name="get_hermes_jobs",
    description="Zeigt den Status der Hermes Job-Queue aller Services.",
    input_schema={"status": str, "limit": int},
)
async def get_hermes_jobs_tool(args):
    status = args.get("status", "")
    limit = min(args.get("limit", 20), 100)
    qs = f"order=created_at.desc&limit={limit}"
    if status:
        qs += f"&status=eq.{status}"
    url = f"{SB_URL}/rest/v1/hermes_jobs?{qs}"
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(url, headers=SB_HEADERS, timeout=aiohttp.ClientTimeout(total=8))
            jobs = await r.json()
        if not jobs or isinstance(jobs, dict):
            return {"content": [{"type": "text", "text": "Keine Jobs in der Queue."}]}
        lines = [
            f"`{j['status']}` *{j['job_name']}* ({j['service']}) — {j['created_at'][:16]}"
            for j in jobs
        ]
        text = f"*Hermes Jobs ({len(lines)}):*\n" + "\n".join(lines)
    except Exception as e:
        text = f"Fehler: {e}"
    return {"content": [{"type": "text", "text": text}]}


@tool(
    name="send_telegram",
    description="Sendet eine Nachricht an Rudolf's Telegram-Chat.",
    input_schema={"message": str},
)
async def send_telegram_tool(args):
    message = args.get("message", "")
    if not TG_TOKEN or not TG_CHAT:
        return {"content": [{"type": "text", "text": "Telegram nicht konfiguriert."}]}
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": message, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=5)
            )
            d = await r.json()
        if d.get("ok"):
            return {"content": [{"type": "text", "text": f"✅ Telegram gesendet (message_id: {d['result']['message_id']})"}]}
        return {"content": [{"type": "text", "text": f"❌ Telegram Fehler: {d.get('description')}"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Fehler: {e}"}]}


@tool(
    name="push_hermes_event",
    description="Pusht ein Event in die Hermes-Event-Log (Supabase).",
    input_schema={"service": str, "event_type": str, "message": str, "channel": str},
)
async def push_hermes_event_tool(args):
    row = {
        "service": args.get("service", "rudibot"),
        "event_type": args.get("event_type", "info"),
        "channel": args.get("channel", "general"),
        "message": args.get("message", ""),
        "metadata": {},
    }
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(
                f"{SB_URL}/rest/v1/hermes_events",
                json=row, headers=SB_HEADERS,
                timeout=aiohttp.ClientTimeout(total=6)
            )
            d = await r.json()
        return {"content": [{"type": "text", "text": f"✅ Event geloggt: {row['event_type']} in #{row['channel']}"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Fehler: {e}"}]}
