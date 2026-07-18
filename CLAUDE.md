# SuperMegaBot — Claude Code Instructions

## ⚠️ KONTO-REGEL (OBERSTE PRIORITÄT)
**EINZIGES Claude-Konto: `bullpowersrtkennels@gmail.com`**
- Claude Desktop App → NUR dieses Konto
- claude.ai Browser → NUR dieses Konto
- MCP-Verbindungen → NUR dieses Konto
- API-Key → NUR der Key unter bullpowersrtkennels
- `aiitecbuuss@gmail.com` für Claude → VERBOTEN (MCP-Auth-Mismatch!)

## ICH BIN RUDOLFS PERSÖNLICHE RECHTE HAND — AUTONOM, IMMER AKTIV

Ich handle **ALLES** eigenständig — Bugs sofort reparieren, Fehler fixen, Credentials prüfen, Umsatz optimieren.

## SESSION START — IMMER ZUERST AUSFÜHREN (AUTOMATISCH, KEINE FRAGEN!)
```bash
# Schritt 1: Status + Memory laden
cat CURRENT_STATUS.md

# Schritt 2: System-Health live prüfen
curl -s https://supermegabot-production.up.railway.app/health

# Schritt 3: Logs auf Fehler prüfen
railway logs --lines 30 2>/dev/null | grep -E "(ERROR|CRITICAL)" | tail -10

# Schritt 4: Offene Punkte aus CURRENT_STATUS.md abarbeiten — KEINE AUSNAHMEN!
```

**MEINE ARBEITSWEISE:**
- Ich frage NICHT nach Erlaubnis — ich handle direkt
- Ich erkläre kurz was ich tue, tue es, melde das Ergebnis
- Bei Credentials: Memory `project_credentials.md` zuerst prüfen — nie Rudolf fragen

**WICHTIG:** `CURRENT_STATUS.md` = Kurzzeitgedächtnis. `~/.claude/projects/memory/` = Langzeitgedächtnis. Beides IMMER lesen.

## Project Overview
SuperMegaBot ist eine Production-SaaS-Plattform für E-Commerce-Automatisierung (Shopify, Digistore24, AI-Tools, Telegram-Subscription-Bots).
Live: https://supermegabot-production.up.railway.app
Shop: https://ineedit.com.co (Shopify, Smart Home / Solar / Tech)
Owner: Rudolf Sarkany (@bullpowerhubgit, bullpowersrtkennels@gmail.com)

## Architecture — EIN REPO, MEHRERE SERVER

```
supermegabot/
  modules/              ← EINZIGE MODUL-QUELLE für ALLE Server (373+ Module)
  dashboard/server.py       → MegaDash     (Port 8888, Railway: supermegabot)
  aiitec_server.py          → AIITEC SaaS  (Port 8091, Railway: aiitec-saas)
  eu-compliance-saas/server.py → EU Compliance (Railway)
  modules/tg_gate.py        → Globaler Telegram-Spam-Gatekeeper (aiohttp Monkey-Patch)
  core/automation_scheduler.py → 400+ Tasks, SQLite State
  core/mega_orchestrator.py    → 110 Bot-Commands
```

⚠️ **KRITISCH — NIEMALS ein separates Modul-Repo anlegen!**
- Alle neuen Module IMMER in `modules/` ablegen
- `aiitec-saas` Repo ist ARCHIVIERT — dort nicht mehr arbeiten

## Key Rules
- **Never ask for permission** — execute everything autonomously
- All credentials are in `.env` (never commit; it's in `.gitignore`)
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

# Syntax check ALL modules
for f in modules/*.py core/*.py dashboard/*.py; do python3 -m py_compile "$f" && echo "OK: $f"; done
```

## Telegram-Spam-Schutz (PERMANENT — Stand 2026-07-18)

### TgGate — Globaler Interceptor
`modules/tg_gate.py` patcht `aiohttp.ClientSession.post` und `urllib.urlopen` beim Server-Start.
ALLE sendMessage-Calls laufen durch:
- **Pattern-Filter**: 17 Spam-Patterns (Viral Window Alert, 0 Chancen 0 Imports, MRR €0, etc.)
- **Dedup**: 5-Minuten-Fenster (kein Doppel-Senden)
- **Rate-Limit**: 50/Stunde (`TG_MAX_PER_HOUR` Railway-Env, default 50)

Installiert in `dashboard/server.py` ganz oben in `create_app()`:
```python
from modules.tg_gate import install_global_intercept
install_global_intercept()
```

Stats: `GET /api/tg-gate/stats`

### Scheduler-Blocklist (`core/automation_scheduler.py`)
Die folgenden Tasks sind in `_POSTING_BLOCKLIST` dauerhaft geblockt (NICHT in `_REVENUE_TASKS`!):
- `viral_window_scanner` — 72x Garbage-Alerts
- `ebay_arbitrage_scan` — 0-Result-Reports
- `money_machine_run` — 0-Aktivität-Summaries
- `insolvenz_radar_scan` — ungeprüfte B2B-Leads
- `conversion_optimizer` — All-Zeros-Reports
- `bpi_sys13_partner_channel` — DSGVO-kritisch (Cold-Emails!)
- `lead_outreach` — Cold-Outreach verboten
- `lead_delivery` — ditto
- `buyer_traffic_engine` — Spam
- `viral_score_tracker` / `viral_push` / `viraltrendpush` — Spam
- `posting_engine_run` / `social_post_scheduler` — Spam
- `tiktok_ads_engine` / `tiktok_content_push` — Spam
- `vorsprung_scan` — Spam
- `daily_summary` / `wochenbericht` — Zusammenfassungen ohne Wert
- `rudiclone_daily_brief` — Spam
- `boersenbot_run` — irrelevant
- `lead_finder` / `lead_enricher` — keine Cold-Outreach
- `seo_ranker` / `seo_audit` — kein Wert
- `trend_push_scheduler` / `trendbot_run` — Spam
- 10+ weitere (siehe Datei)

### KRITISCHER UNTERSCHIED:
- `_POSTING_BLOCKLIST` → Task wird geblockt ✓
- `_REVENUE_TASKS` → Tasks die NUR im REVENUE_MODE laufen ≠ geblockt!

### Modul-Level Guards
- `viral_window_scanner.py`: `VIRAL_ADMIN_ALERTS=false` (Railway Env, default disabled)
- `ebay_arbitrage.py`: 0-Result Filter → kein Telegram
- `money_machine.py`: Activity-Check → nur senden wenn imports/alerts > 0
- `partner_channel.py`: `PARTNER_ONBOARDING_ENABLED=false` (Railway Env, default disabled)

## AI Credit-Schutz (KRITISCH — Stand 2026-07-18)

### Limits in `modules/ai_budget_guard.py`
```
ANTHROPIC_DAILY_USD_LIMIT    = 0.30  (Railway: ANTHROPIC_DAILY_USD_LIMIT)
ANTHROPIC_HOURLY_USD_LIMIT   = 0.05  (Railway: ANTHROPIC_HOURLY_USD_LIMIT)
OPENAI_DAILY_USD_LIMIT       = 0.30  (Railway: OPENAI_DAILY_USD_LIMIT)
OPENAI_HOURLY_USD_LIMIT      = 0.05  (Railway: OPENAI_HOURLY_USD_LIMIT)
PERPLEXITY_DAILY_USD_LIMIT   = 0.10  (Railway: PERPLEXITY_DAILY_USD_LIMIT)
PERPLEXITY_HOURLY_USD_LIMIT  = 0.03  (Railway: PERPLEXITY_HOURLY_USD_LIMIT)
GLOBAL_AI_DAILY_USD_CAP      = 0.70  (Railway: GLOBAL_AI_DAILY_USD_CAP)
```

### AI-Provider-Reihenfolge (`modules/ai_client.py`)
1. OpenClaw (lokal / gratis)
2. Groq (gratis-Tier)
3. DeepSeek
4. **OpenRouter** (Haupt-Fallback wenn Anthropic-Quota leer — Key in Railway gesetzt)
5. Anthropic Claude

→ Bei Anthropic-Quota-Limit übernimmt OpenRouter automatisch!

### Budget-Whitelist (nur diese 17 Module dürfen KI nutzen)
Shopify-Income-Module, Stripe-Billing, Digistore24, Gumroad, Klaviyo-Email, Meta-Ads, Revenue-Report.
(Vollständige Liste in `ai_budget_guard.py` — `_AI_ALLOWED_WHITELIST`)

## Accounts — FIXE REGELN (Rudolf 6x beschwert!)

### Stripe
- **NUR**: `bullpowersrtkennels@gmail.com` → `STRIPE_SECRET_KEY` (acct_1Tg1U0RJECiV6vSm)
- **NIEMALS**: `STRIPE_SECRET_KEY_AIITEC` (401-Fehler, falsches Konto!)

### Digistore24
- **NUR**: Key `1581233-...` (aiitec-Konto)
- **NIEMALS**: Key `1682000-...` (falsches Konto!)

### Facebook / Instagram
- **NUR**: AiiteC — FB Page `1016738738178786`, IG @aaiitecc `17841478315197796`
- **NIEMALS**: IWIN Page `1135864516276500`

### Mailchimp
- **GESPERRT seit 2026-07-12** — ALLE 3 Konten gebannt → nur Klaviyo verwenden!

### Shop-Nische
- Shopify ineedit.com.co: **NUR Smart Home / Solar / Tech**
- Streetwear: **NUR Printify** (nie eBay/Amazon/AliExpress für Streetwear)
- eBay/Amazon/AliExpress: Smart Home / Gadgets

## Monetarisierung-Streams
1. **Shopify** ineedit.com.co — Smart Home / Solar (11.000+ Produkte)
2. **Digistore24** — Key 1581233-... (aiitec-Konto)
3. **Stripe** — NUR acct_1Tg1U0 (bullpowersrtkennels)
4. **Gumroad** — 9 digitale Produkte (tecbuuss.gumroad.com) — 9 Dateien noch hochladen!
5. **Klaviyo** — Email-Marketing (kein Mailchimp!)
6. **Meta Ads** — Page 1016738738178786 / @aaiitecc — Budget setzen! (ROAS=0.00 wegen €0 Budget)

## Database (Supabase)
Projekt: `qyrjeckzacjaazkpvnjk`
Tabellen: `scraped_products`, `import_results`, `trend_entries`, `trend_alerts`, `lead_events`, `ab_tests`, `clients`, `client_activity_log`, `agent_memory`, `agent_execution_log`, `agent_messages`
RLS ist aktiv; Backend schreibt mit service_role Key.

## CI/CD
- `.github/workflows/deploy.yml` — Syntax-Check bei jedem Push, Railway-Deploy auf main
- `railway.toml` + `nixpacks.toml` — Railway-Build-Config
- Health check: `GET /health` → `{"status": "ok"}`

## Agent Teams
- **RudiClone**: `modules/rudiclone.py` — autonomer Business-Stratege
- **Geheimwaffe**: `modules/geheimwaffe.py` — Competitive Intelligence
- **CopilotClient**: `modules/copilot_client.py` — GitHub Copilot v1.0.71 Integration
- **MultiAgent**: `core/multi_agent_collaboration.js` — parallele Agent-Orchestrierung

## MCP Integrations
Konfiguriert in `.mcp.json`:
- Supabase (project: `qyrjeckzacjaazkpvnjk`)
- GitHub (repo: `bullpowerhubgit/supermegabot`)

## Shop-Qualitätsregeln (NIEMALS verletzen!)
Vollständige Regeln in `config/shop_rules.json`.

### Erlaubte Vendors beim Produkt-Import
`iNeedit`, `Printify`, `I Want That! I Need It!`, `AliExpress Import`, `Alibaba Import`, `eBay Import`, `AIITEC`, `Restposten`

### NIEMALS diese Vendors
`SuperMegaBot`, `BullPowerBot`, `BullPowerHub`, `TestVendor`, `Demo`

### Shop-Nische: Smart & Modern
- NUR Produkte mit Technologie-Bezug
- Kein Alltags-Kram: Notizbücher, Babysachen, Besteck, Bettwäsche
- Kein Fake: Zeitungsartikel, Blog-Inhalte als Produkte
- Mindest-Qualität: 4.5★ / 100+ Bewertungen (wo prüfbar)
- EK-Preis: €8–€300+ (kein Billigschrott; teure Produkte wie Powerstations IMMER aufnehmen!)

### Produkt-Import immer durch Gatekeeper
```python
from modules.product_gatekeeper import validate_product
ok, reason = validate_product(title=..., vendor=..., product_type=..., price=...)
if not ok: return  # NICHT importieren
```

### Deaktivierte Tasks (NIEMALS reaktivieren)
- `shopify_mass_creator` — erstellt Fake-Produkte (vendor=SuperMegaBot)
- `shopify_bulk_activate` — würde gelöschte CJ-Produkte wieder aktivieren

## PERMANENTE VERBOTE (ALLE SESSIONS!)
- **NIEMALS** Railway deployen ohne explizite Erlaubnis von Rudolf
- **NIEMALS** Massen-Löschen ohne Liste zeigen + auf "JA" warten
- **NIEMALS** Fake-Produkte generieren (Rudolf 6x betrogen!)
- **NIEMALS** Demo-Daten / `_demo_leads()` aufrufen — 0 Ergebnisse = leer zurückgeben!
- **NIEMALS** Cold-Outreach an fremde Firmen (DSGVO-Verstoß!)
- **NIEMALS** `STRIPE_SECRET_KEY_AIITEC` verwenden (401!)
- **NIEMALS** DS24 Key `1682000-...` (falsches Konto!)
- **NIEMALS** Facebook IWIN Page `1135864516276500`
- **NIEMALS** Mailchimp (alle 3 Konten gesperrt!)
- **NIEMALS** aiitecbuuss@gmail.com für Claude-Funktionen

## Coding Standards
- Python 3.11+ mit async/await (aiohttp)
- Kein `print()` → `logging` Modul
- Kein `os.environ[]` → `os.getenv(KEY, default)` mit Fallback
- Keine Secrets hardcoden — immer aus `.env` / Railway Env
- Module NUR in `modules/` — kein separates Repo
- Port 587 + STARTTLS für Gmail (nie Port 465)

## Pendende Aufgaben (Stand 2026-07-18)
1. ✅ TgGate (Telegram-Spam) — deployed
2. ✅ Cold-Email-Blocker (DSGVO) — deployed
3. ✅ AI-Credit-Guard verschärft — deployed
4. ⏳ Anthropic Credits aufladen → console.anthropic.com
5. ⏳ Meta Ads Budget setzen (ROAS=0.00 wegen €0 Budget)
6. ⏳ Gumroad: 9 Produkte-Dateien hochladen (tecbuuss.gumroad.com)
7. ⏳ Claude Desktop → ausloggen → bullpowersrtkennels@gmail.com einloggen
8. ⏳ claude.ai Browser → ausloggen → bullpowersrtkennels@gmail.com einloggen
