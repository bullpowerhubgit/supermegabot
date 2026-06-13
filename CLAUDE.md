# SuperMegaBot — Claude Code Instructions

## Project Overview
SuperMegaBot is a production SaaS platform for e-commerce automation (Shopify, Digistore24, AI tools, Telegram subscription bots). Deployed on Railway. Owner: Rudolf Sarkany (@bullpowerhubgit).

## Key Rules
- **Never ask for permission** — execute everything autonomously
- All credentials are in `.env` (never commit it; it's in `.gitignore`)
- Always push and create draft PR after changes
- Railway auto-deploys on push to `main` via GitHub Actions (`RAILWAY_TOKEN` secret required)
- Development branch: `claude/blissful-noether-eoEVy`

---

## Architecture

### Core Files
| File | Role |
|------|------|
| `dashboard/server.py` | aiohttp web server on port 8888, 165 API routes |
| `core/mega_orchestrator.py` | MegaOrchestrator + CommandRouter, 110+ bot commands |
| `core/automation_scheduler.py` | 44 periodic tasks, SQLite state in `data/scheduler.db` |
| `core/bot_orchestrator.js` | Node.js bot orchestration layer |
| `core/agenten_hub.js` | Multi-agent hub (JavaScript) |
| `core/multi_agent_collaboration.js` | Parallel agent orchestration |
| `core/self_healer.py` | Auto-healing service monitor |
| `core/bot_clones.py` | Bot clone management |
| `core/specialized_bots.py` | Specialized task bots |
| `core/mac_controller.py` | macOS system control |
| `core/unified_bot_orchestrator.js` | Unified Node.js bot orchestrator |
| `core/watchdog/` | Watchdog scripts for process monitoring |
| `telegram_hub_bridge.py` | Telegram → POST `/api/bot/execute` → MegaOrchestrator |
| `mcp_server.py` | Local MCP server for Claude integration |

### Dashboard HTML
| File | Description |
|------|-------------|
| `dashboard/index.html` | Main dashboard UI |
| `dashboard/autopilot.html` | Autopilot control panel |
| `dashboard/mega_monitor.html` | Real-time system monitor |
| `dashboard/mega_monitor.py` | Monitor backend (Plotly charts) |
| `dashboard/storage_widget.html` | Storage management widget |
| `dashboard/server_windsurf.js` | Windsurf JS server variant |

---

## Modules (`modules/`)

### AI & Automation
- `autopilot.py`, `autopilot_agents.py` — Autopilot workflow agents
- `ai_content_pipeline.py` — AI content calendar generation
- `campaign_manager.py` — Multi-channel campaign management
- `monitoring_agent.py` — System monitoring agent
- `real_data_guard.py` — Data integrity protection

### E-Commerce
- `shopify_client.py`, `shopify_revenue_engine.py`, `shopify_token.py` — Shopify API integration
- `digistore24_automation.py` — Digistore24 orders + affiliate sync
- `printify_automation.py` — Printify Print-on-Demand auto-fulfillment
- `dropshipping_automation.py` — Dropshipping + PoD workflows
- `dynamic_pricing.py` — AI-powered dynamic pricing
- `ecommerce_connectors.py` — Etsy, Gumroad connectors
- `ecommerce_automation_system.js` — JS e-commerce automation
- `ecommerce_orchestrator.js` — JS e-commerce orchestrator
- `tiktok_shop_sync.py` — TikTok Shop ↔ Shopify product/order sync

### Marketing & Growth
- `klaviyo_automation.py` — Klaviyo email marketing
- `mailchimp_automation.py` — Mailchimp list + campaign sync
- `email_sequence_engine.py` — Drip email sequences (welcome, post-purchase, VIP)
- `growth_engine.py` — Review automation, win-back campaigns, referral program
- `seo_automation.py` — Auto-optimize Shopify product SEO via Ollama
- `seo_engine.js` — JS SEO engine
- `marketing_engine.js` — JS marketing automation
- `b2b_pipeline.py` — B2B lead prospecting + outreach
- `social_connectors.py` — Facebook, Instagram, Pinterest, Reddit
- `youtube_analytics.py` — YouTube channel stats

### Revenue & Payments
- `stripe_automation.py`, `stripe_client.py` — Stripe payments + webhook monitor
- `monetization.py` — Subscription tier logic
- `revenue_aggregator.py` — Multi-platform daily revenue report

### Infrastructure
- `supabase_client.py` — Supabase database client
- `google_drive_automation.py` — Google Drive backup
- `google_oauth.py` — Google OAuth flow
- `gmc_monitor.py` — Google Merchant Center feed refresh
- `gcp_loader.py` — GCP service account loader
- `whatsapp_automation.py` — WhatsApp Business API
- `telegram_control.py` — Telegram bot control
- `webhook_handler.py`, `webhook_notifier.py` — Inbound + outbound webhooks
- `trading_bot.py` — Crypto arbitrage scanner
- `storage_monitor.py` — Disk + storage monitoring
- `tailscale.py` — Tailscale VPN control

### Agent Teams
- `rudiclone.py` — RudiClone: autonomous business strategist agent
- `geheimwaffe.py` — Competitive intelligence agent
- `copilot_client.py` — GitHub Copilot integration
- `agent_teams.py` — Multi-agent team coordination
- `mega_hub.py` — Central agent hub
- `rudibot_army.py` (in `rudibot-army/`) — Multi-bot army commander
- `api_builder.py` — Dynamic API endpoint builder
- `api_auto_tester.js` — Automated API testing

---

## Scheduled Tasks (`core/automation_scheduler.py`)

44 tasks total. State stored in SQLite (`data/scheduler.db`). Each task has overlap protection (asyncio.Lock), 5-minute hard timeout, and Telegram alert after 3 consecutive failures.

### Every 5 minutes
- `system_health` — CPU/RAM/Disk check; Telegram alert if >90%

### Every 10 minutes
- `railway_health` — Ping Railway Shopify AI Suite `/health`
- `shopify_orders_alert` — New Shopify orders → Telegram alert

### Every 15 minutes
- `digistore_sync` — Fetch Digistore24 orders → cache → Telegram alert

### Every 30 minutes
- `printify_autofulfill` — Auto-submit Printify orders for production
- `pod_autofulfill` — Print-on-Demand auto-fulfill
- `etsy_sync` — Etsy listings + new transactions
- `gumroad_sync` — Gumroad new sales alert
- `digistore_products_check` — Cache Digistore24 product stats
- `stripe_monitor` — Check Stripe for new payments
- `tiktok_order_sync` — TikTok orders → import to Shopify

### Every 1 hour
- `mailchimp_sync` — Sync Digistore24 buyers to Mailchimp
- `shopify_sync` — Cache Shopify product + order counts
- `social_status` — Ping all social media connectors
- `social_autoposter` — Auto-post trending Shopify products to social
- `env_auto_update` — Write auto-discovered values to data cache
- `printify_shopify_sync` — Sync Printify published products to Shopify
- `revenue_autopilot_carts` — Detect abandoned carts, send recovery emails
- `referral_stats` — Fetch + cache referral program stats
- `email_enroll_new` — Auto-enroll new customers (welcome + post-purchase)
- `tiktok_product_sync` — Sync Shopify products to TikTok Shop

### Every 2 hours
- `seo_optimizer` — Auto-optimize Shopify SEO via Ollama
- `dropshipping_scan` — Scan trending products, auto-list
- `dynamic_pricing` — AI dynamic pricing across 20 Shopify products

### Every 6 hours
- `api_keys_health` — Validate critical API keys, Telegram alert if missing
- `trading_report` — Crypto arbitrage scan, best opportunity → Telegram
- `printify_discover_shop` — Auto-discover + cache Printify shop ID
- `shopify_webhooks_setup` — Register Shopify order/fulfillment webhooks

### Daily
- `revenue_report` — Multi-platform revenue summary → Telegram
- `content_calendar` — AI-generate 7-day content calendar
- `github_backup` — git add + commit + push all changes
- `gmc_refresh` — Google Merchant Center feed status cache
- `youtube_stats` — Fetch YouTube channel stats (subscribers, views, videos)
- `log_cleanup` — Compress logs >10MB, delete .gz files older than 30 days
- `daily_summary` — Complete daily business summary → Telegram
- `drive_backup` — Backup `data/` JSON files to Google Drive
- `revenue_autopilot_daily` — Revenue report + zero-seller analysis → Telegram
- `review_automation` — Send review request emails (7+ days post-purchase)
- `winback_campaign` — Win-back emails + discount codes to inactive customers
- `email_sequences` — Process all due email sequence deliveries
- `vip_promotion` — Promote qualifying customers (3+ orders, €200+) to VIP
- `b2b_prospecting` — Daily B2B lead prospecting
- `whatsapp_daily_report` — WhatsApp daily revenue report to owner

---

## Dashboard API Groups (`dashboard/server.py` — 165 routes)

| Group | Prefix | Key Endpoints |
|-------|--------|---------------|
| Core | `/` `/health` `/monitor` `/autopilot` `/revenue` `/storage` | Dashboard UI, health check |
| Bot | `/api/bot/` | `execute`, `commands` |
| System | `/api/system` `/api/processes` `/api/logs` | Resources, processes, logs |
| Services | `/api/services/` `/api/service/` | `status`, `action`, `start`, `stop` |
| Automation | `/api/automation/` | `status`, `run`, `tasks` |
| Shopify | `/api/shopify/` | `status` |
| Digistore24 | `/api/digistore/` | `status`, `orders` |
| Mailchimp | `/api/mailchimp/` | `status`, `sync`, `campaign` |
| Klaviyo | `/api/klaviyo/` | `status`, `lists`, `sync`, `campaign` |
| Printify | `/api/printify/` | `status`, `autofulfill` |
| Revenue | `/api/revenue/` | `dashboard`, `summary`, `analytics`, `abandoned-carts`, `product-performance`, `products`, `ai-descriptions`, `low-inventory`, `publish-drafts`, `upsell-pairs` |
| Stripe | `/api/stripe/` | `status`, `balance`, `charges`, `customers`, `revenue`, `webhook`, `mrr`, `churn`, `setup-products`, `checkout`, `portal` |
| SEO | `/api/seo/` | `status`, `run` |
| Dropshipping | `/api/dropshipping/` | `status`, `run` |
| Social | `/api/social/` | `status` |
| Trading | `/api/trading/` | `prices`, `arbitrage` |
| Telegram | `/api/telegram/` `/webhook/telegram` | `status`, `send`, webhooks |
| Google | `/api/google/` | `auth`, `callback`, `status`, `refresh`, `revoke` |
| Drive | `/api/drive/` | `status`, `files`, `backup` |
| YouTube | `/api/youtube/` | `dashboard`, `stats`, `latest`, `top` |
| GMC | `/api/gmc` | Merchant Center status |
| Growth | `/api/growth/` | `dashboard`, referral CRUD, `reviews/run`, `winback/run` |
| Pricing | `/api/pricing/` | `dashboard`, `run`, `history`, `enable` |
| Email | `/api/email/` | `stats`, `enroll`, `process`, `enroll-new` |
| B2B | `/api/b2b/` | `stats`, `leads`, `lead` CRUD, `prospect`, `outreach` |
| TikTok | `/api/tiktok/` | `sync`, `orders`, `analytics`, `revenue`, `promotion` |
| WhatsApp | `/webhook/whatsapp` `/api/whatsapp/` | webhook verify+post, `send`, `broadcast`, `stats` |
| Agents | `/api/agents/` `/api/autopilot/` | hub, teams, run, logs |
| Bots | `/api/bots/` | `status`, `run` |
| Army | `/api/army/` | `status`, `start` |
| Backup | `/api/backup/` `/api/github/` | `status`, `run`, `push` |
| Storage | `/api/storage/` | `status`, `cleanup`, `offload`, `large-files`, `history` |
| Self-Learner | `/api/self-learner/` | `status`, `learn`, `skills`, `delete`, `find-api` |
| Watchdog | `/api/watchdog/` | `status` |
| Notes | `/api/notes` | `get`, `save` |
| Plans | `/api/plans` `/api/mrr` `/api/checkout` | SaaS subscription plans |
| Cloud | `/api/cloud/status` | Cloud provider status |
| Ollama | `/api/ollama/models` | Local LLM models |
| Chat | `/api/chat` | AI chat endpoint |
| Deep Scan | `/api/deepscan` | Full system deep scan |

---

## 15 Services (`SERVICES` in `dashboard/server.py`)

| ID | Name | Port | Description |
|----|------|------|-------------|
| `dashboard` | SuperMegaBot | 8888 | Main Python dashboard |
| `rudibot_army` | RudiBot Army | — | `rudibot-army/army_commander.py` |
| `mega_orchestrator` | Mega Orchestrator | — | `core/mega_orchestrator.py` |
| `telegram_bot` | Telegram Bot | 3200 | Node.js `telegram-automation-bot/server.js` |
| `cratorhub` | CreatorHub | 3000 | `digifabrik/server.ts` (npx tsx) |
| `ollama` | Ollama LLM | 11434 | Local LLM server |
| `openclaw` | OpenClaw Gateway | 18789 | `openclaw gateway run` |
| `windsurf_shopify_suite` | Shopify Webhook Suite | 3001 | `windsurf-shopify-suite/` (npm) |
| `windsurf_telegram_bot` | Windsurf Telegram Bot | 8000 | `windsurf-telegram-bot/index.js` |
| `shopify_ai_suite` | Shopify AI Suite (Railway) | — | `https://shopify-suite-v2-production.up.railway.app` |
| `windsurf_shopify` | Windsurf API Gateway | 8080 | `windsurf-api-gateway/src/index.js` |
| `windsurf_autoheal` | Windsurf Auto-Heal | 9000 | `windsurf-auto-heal/index.js` |
| `password_sync` | Password Sync | 3005 | `password-sync-suite/web-app/server.js` |
| `rudibot_eternal` | RudiBot Eternal | — | `rudibot-eternal/immortal_bot.py` |
| `kivo` | KIVO Voice | — | `kivo/kivo.py` |

---

## Monetization Streams
1. **Shopify SaaS**: Subscription tiers (Starter €49/mo, Pro €99/mo, Enterprise €299/mo) via Stripe
2. **Digistore24**: Digital products + affiliate programs
3. **AI Tools**: API access tiers, Claude/GPT proxy with billing
4. **Telegram Subscription**: Premium bot commands gated behind payment
5. **Print-on-Demand**: Printify + Shopify auto-fulfillment
6. **TikTok Shop**: Shopify ↔ TikTok Shop bi-directional sync
7. **B2B SaaS**: Outbound prospecting pipeline to Shopify store owners

---

## Database (Supabase — project: `qyrjeckzacjaazkpvnjk`)
Tables: `scraped_products`, `import_results`, `trend_entries`, `trend_alerts`, `lead_events`, `ab_tests`, `clients`, `client_activity_log`, `agent_memory`, `agent_execution_log`, `agent_messages`
RLS is enabled on all tables with service_role bypass for backend writes.

Local SQLite (in `data/`):
- `scheduler.db` — Automation scheduler task run log
- `memory.db` — MegaOrchestrator conversation memory + learned facts

---

## CI/CD
- `.github/workflows/deploy.yml` — Syntax check on every push, Railway deploy on push to main
- `railway.toml` + `nixpacks.toml` — Railway build config
- Health check: `GET /health` must return `{"status": "ok"}`

---

## MCP Integrations (`.mcp.json`)
- **Supabase**: `https://mcp.supabase.com/mcp?project_ref=qyrjeckzacjaazkpvnjk`
- **SuperMegaBot local MCP**: `mcp_server.py` (via Python3 subprocess)
- GitHub: `bullpowerhubgit/supermegabot`

---

## Development Commands
```bash
# Local dev
python3 dashboard/server.py

# Test health
curl http://localhost:8888/health

# Test bot commands
curl http://localhost:8888/api/bot/commands

# Syntax check all Python files
for f in modules/*.py core/*.py dashboard/*.py; do python3 -m py_compile "$f" && echo "OK: $f"; done

# Run scheduler standalone
python3 core/automation_scheduler.py

# Trigger a specific scheduler task manually
curl -X POST http://localhost:8888/api/automation/run -H "Content-Type: application/json" -d '{"task":"shopify_sync"}'
```

---

## Environment Variables

All required vars are documented in `.env.example`. Never commit `.env`.

### System / Server
- `PORT` / `DASHBOARD_PORT` — HTTP port (Railway sets `PORT` automatically)
- `DASHBOARD_URL` — Base URL of dashboard
- `SITE_URL`, `SUPERMEGABOT_URL` — Public-facing URLs
- `RAILWAY_PUBLIC_DOMAIN` / `RAILWAY_STATIC_URL` — Set by Railway automatically
- `DATA_DIR` — Data path (default: `<project_root>/data`)

### Telegram
- `TELEGRAM_BOT_TOKEN` — Main admin bot token (`@DudiRudibot`, all 110 commands)
- `TELEGRAM_BOT_TOKEN_1`, `TELEGRAM_BOT_TOKEN_2` — Additional bot tokens
- `TELEGRAM_CHAT_ID` — Admin chat/channel ID
- `AUTHORIZED_USER_ID` — Telegram User-ID of admin

### AI / LLM
- `ANTHROPIC_API_KEY` — Claude API key (`sk-ant-api03-...`)
- `OPENAI_API_KEY` — OpenAI API key (`sk-...`)
- `PERPLEXITY_API_KEY` — Perplexity AI key (`pplx-...`)
- `OLLAMA_HOST` — Ollama server URL (default: `http://localhost:11434`)
- `OLLAMA_MODEL` / `OLLAMA_DEFAULT_MODEL` — Standard model (e.g. `llama3.2`)
- `OLLAMA_FAST_MODEL`, `OLLAMA_SMART_MODEL` — Fast/smart model aliases
- `OLLAMA_ANALYSIS_MODEL`, `OLLAMA_CODE_MODEL` — Task-specific models

### Shopify
- `SHOPIFY_SHOP_DOMAIN` — Shop domain (without `https://`, e.g. `your-store.myshopify.com`)
- `SHOPIFY_ACCESS_TOKEN` / `SHOPIFY_ADMIN_API_TOKEN` — Admin API access token (`shpat_...`)
- `SHOPIFY_WEBHOOK_SECRET` — Webhook signature secret
- `SHOPIFY_API_VERSION` — API version (e.g. `2024-10`)
- `SHOPIFY_SUITE_URL` — Railway Shopify AI Suite URL
- `SHOPIFY_SUITE_ACCESS_TOKEN` — Suite access token
- `SHOPIFY_STORE2_DOMAIN`, `SHOPIFY_STORE2_TOKEN` — Second store (optional)
- `REVIEW_URL` — URL for review request emails
- `REVIEW_DELAY_DAYS` — Days after purchase before review email (default: 7)

### Stripe
- `STRIPE_SECRET_KEY` / `STRIPE_API_KEY` — Secret key (`sk_live_...` or `sk_test_...`)
- `STRIPE_WEBHOOK_SECRET` — Webhook signing secret (`whsec_...`)
- `STRIPE_PRICE_STARTER` / `STRIPE_PRICE_PRO` / `STRIPE_PRICE_ENTERPRISE` — Stripe Price IDs

### Supabase
- `SUPABASE_URL` — Project URL (`https://qyrjeckzacjaazkpvnjk.supabase.co`)
- `SUPABASE_ANON_KEY` — Anon/public key
- `SUPABASE_SERVICE_KEY` — Service role key (backend writes only, never expose)
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — For Next.js/Vercel

### GitHub
- `GITHUB_TOKEN` — Personal access token (`ghp_...`)
- `GITHUB_USER` — GitHub username
- `GITHUB_REPO` — Repository (`bullpowerhubgit/supermegabot`)
- `GITHUB_WEBHOOK_SECRET` — Webhook signing secret

### Google / GCP
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — OAuth credentials
- `GOOGLE_REDIRECT_URI` — OAuth callback URL
- `GOOGLE_REFRESH_TOKEN`, `GOOGLE_ACCESS_TOKEN` — OAuth tokens
- `GOOGLE_APPLICATION_CREDENTIALS` — Path to GCP service account JSON
- `GCP_PROJECT_ID`, `GCP_REGION` — GCP project config
- `GCP_SERVICE_ACCOUNT_JSON_B64` — Base64-encoded service account JSON
- `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID` — Google Ads
- `GMC_MERCHANT_ID` — Google Merchant Center ID
- `YOUTUBE_API_KEY`, `YOUTUBE_CHANNEL_ID` — YouTube Data API v3

### Marketing / Email
- `KLAVIYO_API_KEY` — Klaviyo private API key
- `MAILCHIMP_API_KEY`, `MAILCHIMP_SERVER_PREFIX`, `MAILCHIMP_LIST_ID` — Mailchimp
- `MANDRILL_API_KEY` — Mandrill transactional email
- `FROM_EMAIL`, `FROM_NAME` — Email sender identity

### Social Media
- `FACEBOOK_PAGE_ACCESS_TOKEN`, `INSTAGRAM_ACCESS_TOKEN` — Meta APIs
- `PINTEREST_ACCESS_TOKEN` — Pinterest API
- `REDDIT_DEFAULT_SUBREDDIT` — Default subreddit for posts
- `TIKTOK_APP_KEY`, `TIKTOK_APP_SECRET`, `TIKTOK_ACCESS_TOKEN`, `TIKTOK_SHOP_ID`, `TIKTOK_REFRESH_TOKEN` — TikTok Shop

### WhatsApp Business
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_OWNER_NUMBER` — WhatsApp Business API

### E-Commerce Marketplaces
- `DIGISTORE24_API_KEY` — Digistore24 API key
- `ETSY_API_KEY`, `ETSY_ACCESS_TOKEN`, `ETSY_SHOP_ID` — Etsy
- `PRINTIFY_API_KEY` / `PRINTIFY_API_TOKEN`, `PRINTIFY_SHOP_ID` — Printify
- `GUMROAD_ACCESS_TOKEN` — Gumroad

### Business Logic / Tuning
- `DAILY_REVENUE_TARGET` — Daily revenue goal in EUR (default: `1000`)
- `REFERRAL_COMMISSION_PCT` — Referral commission % (default: `20`)
- `WINBACK_DISCOUNT_PCT` — Win-back discount % (default: `15`)
- `CHURN_DAYS` — Days before customer is considered churned (default: `90`)
- `RAM_WARN_PCT`, `STORAGE_WARN_PCT`, `STORAGE_CRITICAL_PCT` — Alert thresholds
- `BACKUP_EXTRA_DIRS` — Additional backup directories (comma-separated)

### Infrastructure
- `TAILSCALE_API_KEY`, `TAILSCALE_TAILNET` — Tailscale VPN (optional)
- `SLACK_WEBHOOK_URL`, `DISCORD_WEBHOOK_URL` — Optional notification channels

---

## Python Dependencies (`requirements.txt`)
```
aiohttp>=3.9.0          # Async HTTP server + client
psutil>=5.9.0           # System metrics (CPU, RAM, disk)
python-dotenv>=1.2.1    # .env loading
anthropic>=0.25.0       # Claude API
openai>=1.14.0          # OpenAI API
stripe>=10.0.0          # Stripe payments
supabase>=2.3.0         # Supabase client
google-api-python-client>=2.100.0  # Google APIs (GMC, Drive, YouTube)
google-auth>=2.20.0     # Google OAuth
plotly>=5.18.0          # Charts in mega_monitor.py
```

---

## Coding Standards
- Python 3.11+
- `async`/`await` throughout (aiohttp)
- Environment variables via `os.getenv()` with sensible defaults — never hardcode secrets
- Log via `logging` module (`log = logging.getLogger("ModuleName")`), never `print()`
- All new scheduled tasks: add to `TASKS` list in `core/automation_scheduler.py`
- All new API routes: register in `create_app()` at bottom of `dashboard/server.py`
- Data caching: write JSON files to `data/` directory (`DATA_DIR`)
- Module guard: every scheduler task catches all exceptions and returns a string result
- No hardcoded domains, API versions, or price values
