# SuperMegaBot

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Railway](https://img.shields.io/badge/Deployed%20on-Railway-blueviolet?logo=railway)
![aiohttp](https://img.shields.io/badge/Framework-aiohttp-green)
![License](https://img.shields.io/badge/License-Private-red)

**One bot. All controls.** SuperMegaBot is a production SaaS platform for full-stack e-commerce automation — Shopify, Digistore24, Printify, TikTok Shop, Stripe, AI tools, and more — controlled entirely from Telegram or a web dashboard.

- 110+ Telegram bot commands
- 93+ REST API endpoints
- 40+ automated background tasks
- 50+ integration modules
- Local AI via Ollama (95% on-device, zero cloud cost)
- Auto-deployed on Railway via GitHub push

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID at minimum

# 3. Start the dashboard
python3 dashboard/server.py
# Dashboard: http://localhost:8888
# Health:    http://localhost:8888/health
```

**Optional: run Telegram bridge in a second terminal**

```bash
python3 modules/telegram_hub_bridge.py
# Every Telegram message now routes to /api/bot/execute → CommandRouter → response
```

**Optional: PM2 for production**

```bash
pm2 start ecosystem.config.js
pm2 save && pm2 logs
```

---

## Architecture

```
                     ┌──────────────────────────┐
                     │      Telegram User       │
                     └─────────────┬────────────┘
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │     modules/telegram_hub_bridge.py  │
                │  Long-poll → POST /api/bot/execute  │
                └─────────────────┬───────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │   SuperMegaBot Dashboard  (aiohttp, Port 8888)  │
        │   ┌──────────────────┐  ┌──────────────────┐    │
        │   │  HTML Frontend   │  │  /api/bot/execute│    │
        │   │  (buttons → API) │  │  → CommandRouter │    │
        │   └──────────────────┘  └────────┬─────────┘    │
        │                                  ▼              │
        │         ┌─────────────────────────────────────┐ │
        │         │  core/mega_orchestrator.py          │ │
        │         │  MegaOrchestrator + CommandRouter   │ │
        │         │  110 commands · MemorySystem (SQLite│ │
        │         │  OllamaClient · SelfHealingEngine   │ │
        │         └──────────────┬──────────────────────┘ │
        └─────────────────────── │ ────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     core/automation_       modules/ (50+)     Guardian Client
     scheduler.py           integrations       (rudibot-eternal)
     40+ background tasks
              │
    ┌─────────┼─────────────────────┐
    ▼         ▼         ▼           ▼
 Shopify  Stripe    Supabase     Digistore24
 Printify TikTok    Mailchimp    Klaviyo
 Google   YouTube   GitHub       Ollama LLM
```

### Repository Structure

```
supermegabot/
├── core/
│   ├── mega_orchestrator.py      # Main orchestrator, 110 commands
│   ├── automation_scheduler.py   # 40+ scheduled background tasks
│   ├── bot_clones.py             # 6 specialised bot clones
│   ├── self_healer.py            # Auto-repair engine
│   └── multi_agent_collaboration.js
├── modules/                      # 50+ async integration modules
├── dashboard/
│   ├── server.py                 # aiohttp server, 93+ API routes
│   └── index.html                # Dashboard frontend
├── data/                         # SQLite DBs + JSON cache files
├── logs/
├── .env                          # All secrets — never commit
├── ecosystem.config.js           # PM2 config
├── railway.toml                  # Railway build config
└── requirements.txt
```

---

## Features

### E-Commerce Automation
- **Shopify** — product sync, order alerts, SEO optimization, webhook handling, abandoned cart recovery
- **Printify** — auto-fulfillment, shop discovery, Shopify sync
- **Digistore24** — order sync, product tracking, Mailchimp integration
- **TikTok Shop** — product + order sync, promotions
- **Etsy / Gumroad** — connector + transaction sync
- **Dropshipping** — trending product scan, auto-listing, social promotion
- **Dynamic Pricing** — AI-driven price optimization (up to 20 products per cycle)

### Marketing & Growth
- **Email Sequences** — welcome, post-purchase, VIP, win-back via Mailchimp / Klaviyo
- **Content Calendar** — 7-day AI-generated content plan
- **SEO Autopilot** — Ollama-powered Shopify product SEO (up to 10 per cycle)
- **Referral Program** — link creation, stats, top-referrer tracking
- **B2B Pipeline** — prospect, outreach, lead management
- **WhatsApp** — daily revenue alerts, broadcast messaging
- **Review Automation** — post-purchase review emails (orders > 7 days old)
- **Flash Sales** — one-click bulk price reduction + restore

### Payments & Revenue
- **Stripe** — subscriptions, balance, charges, webhooks, customer portal
- **Revenue Aggregator** — unified report across all platforms
- **MRR Tracking** — `GET /api/mrr`
- **Crypto Trading** — arbitrage scanner, live price feed (6 pairs)

### AI & Agents
- **Ollama** — local LLM (llama3, gemma2, codellama, mistral), zero cost, no rate limits
- **RudiClone** — autonomous business strategy agent
- **Geheimwaffe** — competitive intelligence, winning-product finder
- **Autopilot Agents** — fully automated business workflow agents
- **RudiBot Army** — fleet of specialised micro-bots
- **Self-Learner** — runtime skill acquisition via Ollama
- **SelfHealingEngine** — automatic dependency repair (`pip/npm/brew install`)

### Infrastructure
- **Guardian / RudiBot Eternal** — external service watchdog, auto-heal, backup/restore
- **PM2 Watchdog** — process supervision, crash recovery
- **Google Drive Backup** — daily `data/` JSON backup
- **GitHub Backup** — daily `git add + commit + push`
- **Storage Monitor** — disk usage alerts, cache cleanup, large-file offload
- **Mac Controller** — macOS screenshots, app control, subscription manager
- **Deep Scan / Repair** — codebase health scan with `--fix` mode

---

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Admin bot token (@DudiRudibot) |
| `TELEGRAM_CHAT_ID` | Authorised chat ID — all others are ignored |
| `SHOPIFY_SHOP_DOMAIN` | `yourstore.myshopify.com` |
| `SHOPIFY_ACCESS_TOKEN` | Admin API token (`shpat_...`) |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service-role key (backend writes) |

### AI & Local Models

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_FAST_MODEL` | `llama3.2:latest` | Fast responses |
| `OLLAMA_SMART_MODEL` | `gemma2:latest` | Complex reasoning |
| `OLLAMA_CODE_MODEL` | `codellama:latest` | Code tasks |
| `OLLAMA_ANALYSIS_MODEL` | `mistral:latest` | Data analysis |
| `ANTHROPIC_API_KEY` | — | Claude API (optional) |
| `OPENAI_API_KEY` | — | OpenAI (optional) |

### Payments & E-Commerce

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe live/test key |
| `STRIPE_WEBHOOK_SECRET` | Stripe HMAC webhook secret |
| `DIGISTORE24_API_KEY` | Digistore24 API key |
| `PRINTIFY_API_KEY` | Printify API key |
| `DAILY_REVENUE_TARGET` | Daily revenue goal in EUR (default: `200`) |

### Marketing

| Variable | Description |
|---|---|
| `MAILCHIMP_API_KEY` | Mailchimp API key |
| `KLAVIYO_API_KEY` | Klaviyo API key |

### Google

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 secret |
| `GMC_MERCHANT_ID` | Google Merchant Center ID |
| `YOUTUBE_CHANNEL_ID` | YouTube channel ID |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key |

### Infrastructure

| Variable | Default | Description |
|---|---|---|
| `SUPABASE_ANON_KEY` | — | Supabase public/anon key |
| `GITHUB_TOKEN` | — | GitHub personal access token |
| `GITHUB_USER` | — | GitHub username |
| `TELEGRAM_BOT_TOKEN_2` | — | Customer bot (@RudiCludiBot) |
| `DASHBOARD_PORT` | `8888` | Web server port |
| `SHOPIFY_API_VERSION` | `2024-10` | Shopify API version |
| `SHOPIFY_WEBHOOK_SECRET` | — | Shopify HMAC verification |

---

## Telegram Bot Commands

Two bots are running in parallel:

| Bot | Token Variable | Audience |
|---|---|---|
| `@DudiRudibot` | `TELEGRAM_BOT_TOKEN` | Admin — all 110 commands |
| `@RudiCludiBot` | `TELEGRAM_BOT_TOKEN_2` | Customers — subscriptions, support |

### Command Reference (compact)

| Category | Commands |
|---|---|
| **System** | `status`, `prozesse`, `speicher`, `screenshot`, `/help`, `/start` |
| **Hub / PM2** | `/hub`, `/pm2`, `/pm2_restart <name>`, `/pm2_start`, `/pm2_stop`, `/pm2_logs`, `/pm2_save` |
| **Shopify / GMC** | `/gmc_status`, `/produkte`, `/ads`, `/shopify_analytics` |
| **Geheimwaffe** | `/waffe`, `/waffe_run <nische>`, `/waffe_produkte`, `/waffe_content <product>`, `/waffe_seo` |
| **API Builder** | `/api_liste`, `/api_test <name>`, `/api_test_alle`, `/api_neu`, `/api_hilfe` |
| **Autopilot** | `/autopilot`, `/autopilot_run`, `/autopilot_logs`, `/agenten` |
| **RudiBot Army** | `/army`, `/army_status`, `/army_start`, `/army_stop`, `/army_events` |
| **ImmortalBot** | `/immortal`, `/immortal_start`, `/immortal_stop`, `/immortal_brain` |
| **Self-Learner** | `/learner`, `/skills`, `/lerne <desc>`, `/lerne_api <desc>`, `/api_finde <task>`, `/skill_del` |
| **Micro Bots** | `/micro`, `/micro_status`, `/micro_ping` |
| **Trading** | `arbitrage`, `preise`, `finanzen` |
| **Guardian** | `/guardian`, `/guardian_health`, `/guardian_services`, `/guardian_heal [svc]`, `/guardian_backup`, `/guardian_restore` |
| **Monetisation** | `/plans`, `/subscribe`, `/mrr`, `/team_run` |
| **Password Sync** | `/pw`, `/pw_status`, `/pw_stats` |
| **Control Panel** | `/menu`, `/steuerung`, `/control` (inline keyboard) |
| **AI Chat** | Any unrecognised text → Ollama (gemma2, last 10 messages context) |

---

## Dashboard URLs

All endpoints are served on `http://localhost:8888` (or your Railway URL).

| URL | Description |
|---|---|
| `/` | Main dashboard (HTML) |
| `/health` | Health check — `{"status": "ok"}` |
| `/revenue` | Revenue Autopilot dashboard |
| `/autopilot` | Autopilot agent dashboard |
| `/storage` | Storage monitor widget |
| `/monitor` | System monitor dashboard |

### Key API Groups

| Group | Base Path |
|---|---|
| System & metrics | `/api/system`, `/api/processes`, `/api/logs`, `/api/keys` |
| Bot & AI | `/api/bot/execute`, `/api/bot/commands`, `/api/chat`, `/api/ollama/models` |
| Services | `/api/services`, `/api/services/status`, `/api/services/action` |
| Shopify | `/api/shopify/status` |
| Revenue & Stripe | `/api/revenue/*`, `/api/stripe/*`, `/api/mrr` |
| Automation | `/api/automation/status`, `/api/automation/run`, `/api/automation/tasks` |
| Agents | `/api/autopilot/*`, `/api/agents/*`, `/api/army/*`, `/api/bots/*` |
| Marketing | `/api/mailchimp/*`, `/api/klaviyo/*`, `/api/email/*`, `/api/seo/*` |
| E-Commerce | `/api/dropshipping/*`, `/api/printify/*`, `/api/tiktok/*`, `/api/pod/*` |
| Growth | `/api/growth/*`, `/api/pricing/*`, `/api/b2b/*` |
| Google / Drive | `/api/google/*`, `/api/drive/*`, `/api/gmc`, `/api/youtube/*` |
| Backup / GitHub | `/api/backup/*`, `/api/github/*` |
| Geheimwaffe | `/api/geheimwaffe/run`, `/api/geheimwaffe/content` |
| WhatsApp | `/api/whatsapp/*`, `/webhook/whatsapp` |
| Telegram | `/api/telegram/status`, `/api/telegram/send` |
| Trading | `/api/trading/prices`, `/api/trading/arbitrage` |

Full route reference: see `dashboard/server.py` or `SUPERMEGABOT_SYSTEM_DOCS.md`.

---

## Scheduled Tasks

`core/automation_scheduler.py` — 40+ tasks persisted in `data/scheduler.db`.

| Interval | Tasks |
|---|---|
| **Every 5 min** | System health (CPU/RAM/Disk alert >90%) |
| **Every 10 min** | Railway health check, new Shopify order alerts |
| **Every 15 min** | Digistore24 order sync → Supabase + Telegram |
| **Every 30 min** | Printify/PoD fulfillment, Etsy/Gumroad sync, Stripe monitor, TikTok order sync |
| **Every 1 h** | Shopify product sync, Mailchimp sync, social autoposter, abandoned cart emails, TikTok product sync |
| **Every 2 h** | SEO optimization (up to 10 products), dropshipping scan, dynamic pricing |
| **Every 6 h** | API key health check, trading report, Shopify webhook setup |
| **Daily** | Revenue report, content calendar, GitHub backup, Google Drive backup, log cleanup, daily summary, review emails, win-back campaign, VIP promotion, B2B prospecting, WhatsApp daily report |

---

## Deployment (Railway)

Auto-deploy is triggered on every push to `main`:

```bash
git add -A
git commit -m "feat: ..."
git push origin main
# Railway builds and deploys automatically
```

**Build config:** `railway.toml` + `nixpacks.toml`  
**Health check:** `GET /health` must return `{"status": "ok"}`  
**Port:** set automatically by Railway via `PORT` env var

### GitHub Actions (`.github/workflows/deploy.yml`)

1. Syntax check on every push:

```bash
for f in modules/*.py core/*.py dashboard/*.py; do
  python3 -m py_compile "$f" && echo "OK: $f"
done
```

2. Railway deploy on push to `main` (requires `RAILWAY_TOKEN` secret)

---

## Development Commands

```bash
# Start dashboard
python3 dashboard/server.py

# Health check
curl http://localhost:8888/health

# List all bot commands
curl http://localhost:8888/api/bot/commands

# Execute a bot command via API
curl -X POST http://localhost:8888/api/bot/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "status"}'

# Syntax check all Python modules
for f in modules/*.py core/*.py dashboard/*.py; do
  python3 -m py_compile "$f" && echo "OK: $f"
done

# Deep scan (read-only)
python3 deep_scan_repair.py

# Deep scan + auto-repair
python3 deep_scan_repair.py --fix

# End-to-end smoke test (starts server on port 8889, tests 23 endpoints)
python3 test_bot_hub.py

# View live logs
tail -f logs/megabot.log

# Manually trigger a scheduler task
python3 -c "
import asyncio
from core.automation_scheduler import get_scheduler
async def main():
    result = await get_scheduler().run_now('shopify_sync')
    print(result)
asyncio.run(main())
"

# View scheduler statistics
python3 -c "
from core.automation_scheduler import get_task_stats
import json; print(json.dumps(get_task_stats(), indent=2))
"
```

---

## Monetisation

| Tier | Price | Includes |
|---|---|---|
| **Starter** | €49 / month | Shopify sync, Telegram bot, AI chat |
| **Pro** | €99 / month | Starter + multi-store, SEO autopilot |
| **Enterprise** | €299 / month | Pro + agent teams, dedicated support |

Checkout: `{DASHBOARD_URL}/checkout?plan=starter|pro|enterprise`

Revenue streams: Shopify SaaS, Digistore24 digital products, AI API tiers, Telegram premium commands, TikTok Shop, Printify/PoD, B2B pipeline.

---

## Database

### SQLite (local)

| File | Tables |
|---|---|
| `data/memory.db` | `conversations`, `learned_facts`, `repair_history`, `task_history` |
| `data/scheduler.db` | `task_runs` (name, ran_at, success, result, duration_ms) |

### Supabase (PostgreSQL + RLS)

`scraped_products`, `import_results`, `trend_entries`, `trend_alerts`, `lead_events`, `ab_tests`, `clients`, `client_activity_log`, `agent_memory`, `agent_execution_log`, `agent_messages`

RLS is enabled on all tables. Backend writes use `SUPABASE_SERVICE_KEY`. Never expose the service key to the frontend.

---

## Security

- All secrets in `.env` — never committed (`.gitignore`)
- Telegram: only `TELEGRAM_CHAT_ID` can send commands; all other chat IDs are silently ignored
- Shopify webhooks: HMAC-SHA256 verification via `X-Shopify-Hmac-Sha256`, timing-safe comparison, returns HTTP 401 on failure
- SelfHealingEngine: only `pip/npm/brew install <pkg>` allowed, `shell=False`, package names regex-validated
- GuardianClient: lazy init — missing `GUARDIAN_API_SECRET` does not block dashboard startup
- No hardcoded domains, versions, or tokens anywhere in source code

---

## Troubleshooting

**Ollama offline**
```bash
ollama serve
ollama list
ollama pull llama3.2 && ollama pull gemma2
```

**Telegram 409 conflict** — another process is using the same token
```bash
ps aux | grep python          # find the duplicate process
kill <PID>
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```

**Railway deploy fails** — run the syntax check locally first:
```bash
for f in modules/*.py core/*.py dashboard/*.py; do
  python3 -m py_compile "$f" && echo "OK: $f"
done
railway logs
```

**Supabase `permission denied`** — ensure backend uses `SUPABASE_SERVICE_KEY`, not `SUPABASE_ANON_KEY`.

**Scheduler task failing** — check stats and re-run manually:
```bash
python3 -c "
from core.automation_scheduler import get_task_stats
import json
for name, s in get_task_stats().items():
    if s.get('ok', 0) < s.get('total', 0):
        print(f'FAILING: {name} — {s[\"ok\"]}/{s[\"total\"]} OK')
"
```

---

*SuperMegaBot v3.0 — Owner: Rudolf Sarkany (@bullpowerhubgit) — Deployed on Railway*
