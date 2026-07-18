# SuperMegaBot — Copilot Instructions

## Projekt-Übersicht
SuperMegaBot ist eine Production-SaaS-Plattform für E-Commerce-Automatisierung.
Owner: Rudolf Sarkany (bullpowersrtkennels@gmail.com)
Live: https://supermegabot-production.up.railway.app
Shop: https://ineedit.com.co (Shopify, Smart Home / Solar / Tech)

## Architektur
```
dashboard/server.py     → aiohttp Web-Server Port 8888 (Railway)
core/automation_scheduler.py → 400+ Tasks, SQLite State
core/mega_orchestrator.py    → 110 Bot-Commands
modules/                → 373+ Module (EINZIGE Quelle für alle Server)
modules/tg_gate.py      → Globaler Telegram-Spam-Gatekeeper (aiohttp Monkey-Patch)
```

## AI-Provider-Reihenfolge (ai_client.py)
Alle parallel versucht, erster Erfolg gewinnt:
1. OpenClaw (lokal / gratis)
2. Groq (gratis-Tier)
3. DeepSeek
4. **OpenRouter** (Haupt-Fallback wenn Anthropic-Credits leer)
5. Anthropic Claude

→ Bei Anthropic-Quota-Limit: OpenRouter übernimmt automatisch.
→ `OPENROUTER_API_KEY` ist in Railway gesetzt.

## Telegram-Spam-Schutz (TgGate)
`modules/tg_gate.py` patcht `aiohttp.ClientSession.post` + `urllib.urlopen` beim Start.
ALLE sendMessage-Calls laufen durch:
- Pattern-Filter (17 Spam-Patterns)
- Dedup (5 Minuten Fenster)
- Rate-Limit (50/Stunde, `TG_MAX_PER_HOUR` Railway Env)

## Deployment
- Railway auto-deploy auf Push zu `main`
- `railway up --detach` für sofortigen Deploy
- Health: `GET /health` → `{"status":"ok"}`

## Coding-Regeln
- Python 3.11+ async/await (aiohttp)
- Kein `print()` → `logging` Modul
- Kein `os.environ[]` → `os.getenv(KEY, "")` mit Default
- Keine Secrets hardcoden — immer aus `.env` / Railway Env
- Module NUR in `modules/` ablegen — kein separates Repo
- Port 587 + STARTTLS für Gmail (nie Port 465)
- `mass_creator` und `bulk_activate` DAUERHAFT deaktiviert

## Monetarisierung-Streams
1. Shopify ineedit.com.co — Smart Home / Solar (11.000+ Produkte)
2. Digistore24 DS24 — Key 1581233-... (aiitec-Konto, NIEMALS 1682000-...)
3. Stripe — NUR acct_1Tg1U0 bullpowersrtkennels@gmail.com
4. Gumroad — 9 digitale Produkte (tecbuuss.gumroad.com)
5. Klaviyo Email-Marketing
6. Meta Ads — Page 1016738738178786 / @aaiitecc

## Permanente Verbote
- NIEMALS `STRIPE_SECRET_KEY_AIITEC` verwenden (401 Fehler)
- NIEMALS DS24 Key 1682000-... (falsches Konto)
- NIEMALS Facebook Page IWIN (1135864516276500)
- NIEMALS Mailchimp (alle 3 Konten gesperrt seit 2026-07-12)
- NIEMALS Railway deployen ohne explizite Erlaubnis
- NIEMALS Massen-Löschen ohne Bestätigung
- NIEMALS Fake-Produkte generieren
- NIEMALS Demo-Daten / _demo_leads() aufrufen
- NIEMALS Cold-Outreach an fremde Firmen (DSGVO)

## Wichtige Env-Vars (Railway)
```
TELEGRAM_BOT_TOKEN      = 8600739487:... (Rudiclone, EINZIGER Bot)
TELEGRAM_CHAT_ID        = Rudolf's Chat-ID
ANTHROPIC_API_KEY       = sk-ant-...
OPENROUTER_API_KEY      = sk-or-v1-... (Fallback wenn Anthropic-Quota leer)
SHOPIFY_SHOP_DOMAIN     = ineedit.com.co
SHOPIFY_ADMIN_API_TOKEN = shpat_...
STRIPE_SECRET_KEY       = sk_live_... (bullpowersrtkennels ONLY)
SUPABASE_URL            = https://qyrjeckzacjaazkpvnjk.supabase.co
```

## Supabase
Projekt: `qyrjeckzacjaazkpvnjk`
Tabellen: scraped_products, import_results, clients, agent_memory, lead_events, ab_tests

## Aktuelle Prioritäten (Stand 2026-07-18)
1. Telegram-Spam-Gatekeeper (TgGate) — deployed
2. Cold-Email-Blocker — deployed
3. Anthropic-Credits aufladen → console.anthropic.com
4. Meta Ads Budget setzen (ROAS=0.00 wegen €0 Budget)
5. Gumroad: 9 Produkte Dateien hochladen
