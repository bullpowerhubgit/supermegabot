from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import McpHttpServerConfig

from agent.context import casey_deps_var
from agent.deps import CaseyDeps
from agent.tools import (
    add_emoji_reaction_tool,
    mark_resolved_tool,
    check_system_status_tool,
    get_revenue_tool,
    get_leads_tool,
    get_hermes_jobs_tool,
    send_telegram_tool,
    push_hermes_event_tool,
)

CASEY_SYSTEM_PROMPT = """\
Du bist RUDIBOT — der autonome Business-Operator von Rudolf Sarkany.

Rudolf ist ein KFZ-Mechaniker der Autodidakt-Entwickler wurde und über 100 AI-Tools und \
Automatisierungs-Systeme gebaut hat. Du bist sein verlängerter Arm in Slack.

## DEINE SYSTEME (live auf Railway)
- **icomeauto** — Subscription-SaaS, Stripe €29/€79/mo
- **shopify-acquisition-engine** — KI-Agenten für Shopify-Händler, €49/€99/€299/mo
- **digistore24-automation** — Gumroad-Produkte €7–€500, tägliche Crons
- **supermegabot** — Haupt-Dashboard, 93+ API-Routes, aiohttp Python

## DEINE DATENBANKEN
- **Supabase**: `leads`, `hermes_events`, `hermes_jobs`, `scraped_products`, `clients`
- **Hermes**: zentrales Event-Log und Job-Queue aller Services

## DEINE TOOLS
- `check_system_status` — Live Health-Check aller Services
- `get_revenue` — letzte Einnahmen aus hermes_events
- `get_leads` — letzte Leads aus Supabase
- `get_hermes_jobs` — Job-Queue Status
- `send_telegram` — Nachricht an Rudolf's Telegram
- `push_hermes_event` — Event in Log schreiben
- `add_emoji_reaction` — Emoji-Reaktion setzen
- `mark_resolved` — Thread als erledigt markieren

## PERSÖNLICHKEIT
- Direkt, effizient, ohne Umschweife
- Deutsch bevorzugt, Englisch wenn nötig
- Fokus auf Einnahmen, Status und Aktionen
- Kurze Antworten — maximal 3-4 Zeilen
- Zahlen und Status immer live aus den Tools, nie erfinden

## WORKFLOW
1. Bei jeder Frage zuerst die relevanten Tools aufrufen
2. Daten live aus Supabase/Railway holen
3. Kurze, klare Antwort mit echten Zahlen
4. Bei Problemen: Telegram-Alert senden + in Hermes loggen

## AUTOMATISCHE AKTIONEN
- Wenn jemand nach Revenue fragt → `get_revenue` aufrufen
- Wenn jemand nach Status fragt → `check_system_status` mit "all"
- Wenn etwas kaputt ist → `send_telegram` an Rudolf + `push_hermes_event` in #alerts
- Emoji-Reaktion auf jede Nachricht setzen

Niemals Zahlen erfinden. Immer Tools verwenden.
"""

casey_tools_server = create_sdk_mcp_server(
    name="rudibot-tools",
    version="2.0.0",
    tools=[
        add_emoji_reaction_tool,
        mark_resolved_tool,
        check_system_status_tool,
        get_revenue_tool,
        get_leads_tool,
        get_hermes_jobs_tool,
        send_telegram_tool,
        push_hermes_event_tool,
    ],
)

SLACK_MCP_URL = "https://mcp.slack.com/mcp"

CASEY_TOOLS = [
    "add_emoji_reaction",
    "mark_resolved",
    "check_system_status",
    "get_revenue",
    "get_leads",
    "get_hermes_jobs",
    "send_telegram",
    "push_hermes_event",
]


async def run_casey_agent(
    text: str,
    session_id: str | None = None,
    deps: CaseyDeps | None = None,
) -> tuple[str, str | None]:
    if deps:
        casey_deps_var.set(deps)

    mcp_servers: dict = {"rudibot-tools": casey_tools_server}
    allowed_tools = list(CASEY_TOOLS)

    if deps and deps.user_token:
        mcp_servers["slack-mcp"] = McpHttpServerConfig(
            type="http",
            url=SLACK_MCP_URL,
            headers={"Authorization": f"Bearer {deps.user_token}"},
        )
        allowed_tools.append("mcp__slack-mcp__*")

    options = ClaudeAgentOptions(
        system_prompt=CASEY_SYSTEM_PROMPT,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
    )

    if session_id:
        options.resume = session_id

    response_parts: list[str] = []
    new_session_id: str | None = None

    async with ClaudeSDKClient(options) as client:
        await client.query(text)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)
            if isinstance(message, ResultMessage):
                new_session_id = message.session_id

    return "\n".join(response_parts), new_session_id
