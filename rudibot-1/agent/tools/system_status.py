import aiohttp
from claude_agent_sdk import tool

SERVICES = {
    "icomeauto":   "https://icomeauto-production.up.railway.app/health",
    "shopify":     "https://shopify-acquisition-engine-production.up.railway.app/health",
    "digistore":   "https://digistore24-automation-production.up.railway.app/api/health",
    "supermegabot":"https://supermegabot-production.up.railway.app/health",
}


@tool(
    name="check_system_status",
    description="Live Health-Check aller deployed Services (Railway). Zeigt Status, Uptime, Agents.",
    input_schema={"service": str},
)
async def check_system_status_tool(args):
    service = args.get("service", "all").lower()
    targets = {k: v for k, v in SERVICES.items() if service == "all" or service in k} or SERVICES

    lines = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
        for name, url in targets.items():
            try:
                r = await s.get(url)
                d = await r.json()
                st = d.get("status", "?")
                uptime = d.get("uptime_seconds") or d.get("uptime")
                extra = f" | uptime: {round(uptime)}s" if uptime else ""
                agents = f" | agents: {d.get('agents','')}" if d.get("agents") else ""
                icon = "✅" if st == "ok" else "❌"
                lines.append(f"{icon} *{name}*: {st}{uptime and extra}{agents}")
            except Exception as e:
                lines.append(f"❌ *{name}*: offline ({e})")

    text = "*Live Service Status:*\n" + "\n".join(lines)
    return {"content": [{"type": "text", "text": text}]}
