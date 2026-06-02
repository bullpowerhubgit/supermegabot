# SuperMegaBot — Windsurf + Claude Sync Prompt

> Dieses Dokument ist die Single Source of Truth für Windsurf-Sessions.
> Lies es komplett bevor du Änderungen machst.

---

## Projekt-Identität

**Name:** SuperMegaBot  
**Zweck:** Produktives Multi-System AI Automation System mit 22 integrierten Services  
**Repo:** `bullpowerhubgit/supermegabot`  
**Haupt-Branch:** `main`  
**Dashboard:** `http://localhost:8888` (Python/aiohttp)

---

## Architektur — Zwei-Stack-System

### Stack 1: Python (PRODUKTIV — DAS ECHTE SYSTEM)
```
dashboard/server.py          ← Haupt-Server (aiohttp, Port 8888, ~90 Endpoints)
dashboard/index.html         ← Single-Page Dashboard
core/mega_orchestrator.py    ← Zentrales Gehirn (SQLite + Ollama + Self-Healing)
core/automation_scheduler.py ← Task-Scheduler
core/bot_clones.py           ← 6 Bot-Klone (Watch/Repair/Growth/Revenue/Guard/Deploy)
core/specialized_bots.py     ← 5 spezialisierte Bots
core/self_healer.py          ← Auto-Repair-System
core/watchdog/python_watchdog.py ← Produktions-Watchdog (Port 8888 Monitor)
rudibot-army/                ← Bot-Armee (army_commander.py + 7 Agents + 5 Micro-Bots)
```

### Stack 2: JS/Node (DEAKTIVIERT in PM2 — benötigt npm deps)
```
core/agenten_hub.js          ← Deaktiviert: benötigt Linux-Portabilität
core/watchdog/watchdog-v2.js ← Deaktiviert: benötigt SUPERMEGABOT_DIR ENV
modules/ecommerce_orchestrator.js ← Deaktiviert: benötigt axios
modules/marketing_engine.js  ← Deaktiviert: benötigt axios
modules/seo_engine.js        ← Deaktiviert: benötigt axios
dashboard/server_windsurf.js ← Deaktiviert: separater Port 9002
```
> Um JS-Stack zu aktivieren: `npm install axios ws node-cron` + ENV-Vars setzen

---

## Aktive Integrationen (Python-Stack)

| Service | Modul | ENV-Var | Status |
|---------|-------|---------|--------|
| Shopify | `modules/shopify_client.py` | `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_SHOP_DOMAIN` | ✅ |
| Stripe | `modules/stripe_automation.py` | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | ✅ |
| Telegram | `modules/telegram_control.py` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | ✅ |
| Google Drive | `modules/google_drive_automation.py` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | ✅ |
| Supabase | `modules/supabase_client.py` | `SUPABASE_URL`, `SUPABASE_ANON_KEY` | ✅ |
| Mailchimp | `modules/mailchimp_automation.py` | `MAILCHIMP_API_KEY`, `MAILCHIMP_SERVER_PREFIX` | ✅ |
| Klaviyo | `modules/klaviyo_automation.py` | `KLAVIYO_API_KEY` | ✅ |
| Printify | `modules/printify_automation.py` | `PRINTIFY_API_KEY` | ✅ |
| Digistore24 | `modules/digistore24_automation.py` | `DIGISTORE24_API_KEY` | ✅ |
| Perplexity | via aiohttp | `PERPLEXITY_API_KEY` | ✅ |
| Anthropic | `supermegabot_agent.py` | `ANTHROPIC_API_KEY` | ✅ |
| OpenAI | `modules/copilot_client.py` | `OPENAI_API_KEY` | ✅ |
| Guardian | `guardian_client.py` | `GUARDIAN_API_SECRET` | ✅ |
| Ollama | `core/mega_orchestrator.py` | `OLLAMA_HOST` | ✅ |
| SEO | `modules/seo_automation.py` | `SEMRUSH_API_KEY` | ⚠️ partial |
| Social | `modules/social_connectors.py` | `META_ACCESS_TOKEN` etc. | ⚠️ partial |
| Google Ads | `modules/campaign_manager.py` | — | ❌ NotImplementedError |
| GMC | `modules/gmc_monitor.py` | — | ❌ Placeholder |

---

## Produktionsregeln (PFLICHT)

1. **Keine Mock-Daten** — `digistore24_automation.py` und `social_connectors.py` geben bei fehlendem Key `{"available": false}` zurück, NICHT Fake-Daten
2. **Keine stillen Fehler** — `except: pass` wurde durch `log.exception()` ersetzt
3. **Keine hardcodierten Pfade** — immer `os.getenv()` oder `Path(__file__).resolve()`
4. **Keine toten Buttons** — UI-Elemente müssen echte Backend-Endpoints haben
5. **Stripe Webhooks** — Signatur-Verifikation via `verify_webhook_signature()` in `stripe_automation.py`

---

## Dashboard-Endpunkte (wichtigste)

```
GET  /api/status              ← System-Übersicht
GET  /api/shopify/status      ← Shopify-Verbindung
GET  /api/stripe/status       ← Stripe-Verbindung
POST /api/stripe/webhook      ← Stripe-Webhook (mit Signatur-Check)
GET  /api/google/auth         ← Google OAuth Start
GET  /api/google/callback     ← Google OAuth Callback
GET  /api/google/status       ← Google-Status
GET  /api/digistore/status    ← Digistore24
GET  /api/digistore/orders    ← Bestellungen
GET  /api/revenue/status      ← Gesamt-Revenue
GET  /api/watchdog/status     ← Watchdog (→ Port 9003)
GET  /api/agents/hub          ← Agenten-Hub (→ Port 9998)
```

---

## PM2 Services (aktiv)

```js
// ecosystem.config.js — aktive Services:
supermegabot-dashboard  → python3 dashboard/server.py   (Port 8888)
python-watchdog         → python3 core/watchdog/python_watchdog.py
rudibot-army            → python3 rudibot-army/army_commander.py

// DEAKTIVIERT (brauchen npm install axios ws):
// windsurf-watchdog, windsurf-watchdog-monitor, windsurf-dashboard
// windsurf-ecommerce, windsurf-marketing, windsurf-agenten-hub
```

---

## Starten

```bash
# Lokale Entwicklung
python3 dashboard/server.py

# Oder mit allen Services
pm2 start ecosystem.config.js

# Live-Verbindungstest
python3 test_live_connections.py
```

---

## Was noch fehlt (Backlog)

| Feature | Datei | Was gebraucht wird |
|---------|-------|--------------------|
| Google Ads OAuth | `modules/campaign_manager.py` | GCP OAuth Setup |
| GMC OAuth | `modules/gmc_monitor.py` | Google Merchant Center API |
| JS-Stack aktivieren | `ecosystem.config.js` | `npm install axios ws` |
| Etsy Integration | — | `ETSY_API_KEY`, `ETSY_SHARED_SECRET` |

---

## Windsurf-spezifische Anweisungen

- **Branch-Strategie:** Feature-Branches von `main`, PR erstellen, squash-merge
- **ENV-Vars:** Alle in `.env.example` dokumentiert — niemals in Code hardcoden
- **Tests:** `python3 test_live_connections.py` nach jeder größeren Änderung
- **Dashboard-Test:** `curl http://localhost:8888/api/status` muss `{"ok": true}` zurückgeben
- **Syntax-Check vor Commit:** `python3 -m py_compile <datei>` für Python, `node --check <datei>` für JS

---

*Zuletzt aktualisiert: 2026-06-02 | SuperMegaBot v2.0 Production*
