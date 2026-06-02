# Windsurf Agent Rules for SuperMegaBot

## Architecture

- Core bot: `/Users/rudolfsarkany/supermegabot/`
- Dashboard: port `8888`
- Guardian API: port `3201`
- Telegram bot: `@DudiRudibot` (Token OK)
- Alt Telegram bot: `@RudiCludiBot` (Token OK)
- Army Commander: `rudibot-army/army_commander.py`
- Windsurf Telegram Bot: `/Users/rudolfsarkany/windsurf-telegram-bot/`
- MCP Servers: `mcp_server.py` + `mcp-server.js`

## API Status (Live)

| Service                | Status         | Check                           |
| ---------------------- | -------------- | ------------------------------- |
| Shopify                | ✅ OK          | Shop: "I Want That! I Need It!" |
| Stripe                 | ✅ OK          | LIVE mode                       |
| Telegram @DudiRudibot | ✅ OK          | Admin bot                       |
| Telegram @RudiCludiBot | ✅ OK          | Kunden bot                      |
| Supabase               | ⚠️ 401         | Key prüfen — `SUPABASE_ANON_KEY` |
| OpenAI                 | ✅ Key present | `OPENAI_API_KEY`                |
| Anthropic              | ✅ Key present | `ANTHROPIC_API_KEY`             |
| Guardian               | 🔴 OFFLINE     | Port 3201 unreachable           |
| Dashboard              | ✅ OK          | `http://localhost:8888`          |

## Branches

- `main` — stable production
- `ultimate/production-ready` — active development (current)
- `claude/blissful-noether-eoEVy` — Claude Desktop integration

## Security Rules (CRITICAL)

1. **NEVER hardcode credentials** — always use `os.getenv()`
2. **NEVER commit `.env`** — `.env.example` als Master-Template
3. **NEVER commit `windsurf-mcp-config.json`** — enthält API Keys
4. `.windsurf/` ist in `.gitignore` — lokale Configs bleiben lokal
5. Vor Push prüfen: `grep -r "sk_live\|shpat_\|ghp_" . --include="*.py" --include="*.json"`

## Claude Desktop Integration

- MCP Server: `mcp_server.py` — SuperMegaBot API + Guardian
- MCP Server: `windsurf-telegram-bot/mcp-server.js` — Telegram + Webhooks
- Config: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Zusätzlich: GitHub MCP + Ollama MCP

## Rules

1. All agents must report status via `rudibot-army/shared/bus.py`
2. Dashboard endpoints follow `/api/<resource>` convention
3. Python files: use type hints, handle exceptions explicitly
4. Run `test_live_connections.py` before committing to verify APIs
5. Use `.env.example` as master config — keep `.env` in sync
6. For Telegram: prefer `@DudiRudibot` token (primary)
7. Neue APIs: erst in `.env.example` dokumentieren, dann `.env` aktualisieren
8. Merge-Konflikte: `--theirs` für `.env.example`, lokale `.env` behalten

## Integration Points

- `army_commander.py`: register new agents here
- `core/mega_orchestrator.py`: main dispatch
- `dashboard/server.py`: add new API endpoints here
- `test_live_connections.py`: verify all APIs before deploy
- `mcp_server.py`: Claude Desktop MCP integration
