# SuperMegaBot — Claude Code Instructions

## Project Overview
SuperMegaBot is a production SaaS platform for e-commerce automation (Shopify, Digistore24, AI tools, Telegram subscription bots). Deployed on Railway. Owner: Rudolf Sarkany (@bullpowerhubgit).

## Architecture
- **Dashboard**: `dashboard/server.py` — aiohttp web server on port 8888, 93+ API routes
- **Core**: `core/mega_orchestrator.py` — MegaOrchestrator + CommandRouter, 110 bot commands
- **Modules**: `modules/` — Shopify, Stripe, Supabase, Telegram, AI, marketing integrations
- **Scheduler**: `core/automation_scheduler.py` — periodic task runner (SQLite state)
- **Bridge**: `modules/telegram_hub_bridge.py` → POST `/api/bot/execute` → MegaOrchestrator

## Key Rules
- **Never ask for permission** — execute everything autonomously
- All credentials are in `.env` (never commit it; it's in `.gitignore`)
- Development branch: `claude/blissful-noether-eoEVy`
- Always push and create draft PR after changes
- Railway auto-deploys on push to `main` via GitHub Actions (`RAILWAY_TOKEN` secret required)

## Development Commands
```bash
# Local dev
python3 dashboard/server.py

# Test health
curl http://localhost:8888/health

# Test bot commands
curl http://localhost:8888/api/bot/commands

# Run syntax check
for f in modules/*.py core/*.py dashboard/*.py; do python3 -m py_compile "$f" && echo "OK: $f"; done
```

## Environment Variables
All required vars are documented in `.env.example`. Key ones:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_API_TOKEN`, `SHOPIFY_API_VERSION`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `GITHUB_TOKEN`, `GITHUB_USER`

## Monetization Streams
1. **Shopify SaaS**: Subscription tiers (Starter €49/mo, Pro €99/mo, Enterprise €299/mo) via Stripe
2. **Digistore24**: Digital products + affiliate programs
3. **AI Tools**: API access tiers, Claude/GPT proxy with billing
4. **Telegram Subscription**: Premium bot commands gated behind payment

## Database (Supabase)
Tables: `scraped_products`, `import_results`, `trend_entries`, `trend_alerts`, `lead_events`, `ab_tests`, `clients`, `client_activity_log`, `agent_memory`, `agent_execution_log`, `agent_messages`
RLS is enabled on all tables with service_role bypass for backend writes.

## CI/CD
- `.github/workflows/deploy.yml` — syntax check on every push, Railway deploy on push to main
- `railway.toml` + `nixpacks.toml` — Railway build config
- Health check: `GET /health` must return `{"status": "ok"}`

## Scheduled Tasks (automation_scheduler.py)
- Every 30min: Shopify product sync
- Every 1h: Digistore24 revenue sync
- Every 2h: System health alerts (Telegram notification)
- Every 6h: AI trend analysis
- Daily: Full backup to GitHub

## Agent Teams
- **RudiClone**: `modules/rudiclone.py` — autonomous business strategist agent
- **Geheimwaffe**: `modules/geheimwaffe.py` — competitive intelligence
- **CopilotClient**: `modules/copilot_client.py` — GitHub Copilot integration
- **MultiAgent**: `core/multi_agent_collaboration.js` — parallel agent orchestration

## MCP Integrations
Configured in `.mcp.json`:
- Supabase (project: `qyrjeckzacjaazkpvnjk`)
- GitHub (repo: `bullpowerhubgit/supermegabot`)

## Coding Standards
- Python 3.11+
- async/await throughout (aiohttp)
- Environment variables via `os.getenv()` with sensible defaults
- No hardcoded secrets, domains, or API versions
- Log via `logging` module, not `print()`
