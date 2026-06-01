# SuperMegaBot - Quickstart nach System-Audit

## Sofortmassnahmen (heute)

### 1. API-Keys sichern (KRITISCH)
```bash
# Pruefe, welche Keys in .env fehlen
cat .env | grep -E "^(ANTHROPIC|OPENAI|SHOPIFY|PERPLEXITY)_API_KEY"
```
- Keys aus `api-config.json` in `.env` uebertragen
- `api-config.json` sollte nie ins Git committet werden
- `bots/shared/secure-config.js` laedt jetzt automatisch aus `.env`

### 2. Neues Bot-System starten
```bash
# Alle 5 spezialisierten Bots starten
node bots/unified-orchestrator.js start-all

# Status anzeigen
node bots/unified-orchestrator.js status

# Einzelnen Bot starten
node bots/unified-orchestrator.js start-bot monitoring

# Alle stoppen
node bots/unified-orchestrator.js stop-all
```

### 3. Logs ueberwachen
```bash
# In einem neuen Terminal
tail -f logs/monitoring-bot.log
tail -f logs/error-detection-bot.log
```

## Prioritaet A - Sofort monetarisieren

### AutoShop Suite (24h bis Umsatz)
1. Etsy API Key in `.env` eintragen: `ETSY_API_KEY=...`
2. Printful API Key eintragen: `PRINTFUL_API_KEY=...`
3. Shopify Key pruefen (bereits in `api-config.json`)
4. `AutoShopSuite_fixed.tsx` deployen

### QuickCash System (24-48h)
1. `quickcash-backend.js` auf Vercel/Railway deployen
2. Stripe Keys in `.env`: `STRIPE_SECRET_KEY=...`
3. Frontend `QUICKCASH_FRONTEND.html` testen

### My-Shop (3-5 Tage)
1. `my-shop/frontend/` bauen: `cd my-shop/frontend && npm run build`
2. Stripe Checkout integrieren
3. Auf Vercel deployen

## Wichtige neue Dateien

| Datei | Zweck |
|-------|-------|
| `bots/specialized/monitoring-bot.js` | Systemueberwachung |
| `bots/specialized/error-detection-bot.js` | Log-Analyse & Exceptions |
| `bots/specialized/repair-bot.js` | Automatische Reparaturen |
| `bots/specialized/maintenance-bot.js` | Health-Checks & Backups |
| `bots/specialized/optimization-bot.js` | Performance & Conversion |
| `bots/unified-orchestrator.js` | Zentrale Steuerung aller Bots |
| `bots/shared/unified-logger.js` | Shared Logging |
| `bots/shared/event-bus.js` | Inter-Bot-Kommunikation |
| `bots/shared/secure-config.js` | Sichere Konfiguration |
| `api/api-client.js` | Robuster API Client mit Retry |
| `FINAL_SYSTEM_AUDIT_AND_PRIORITIZATION.md` | Vollstaendiger Audit-Report |

## Kritische Warnungen

1. **RAM bei 98.29%** - Sofort bereinigen oder Prozesse beenden
2. **API Keys in `api-config.json`** - Sicherheitsrisiko, umziehen in `.env`
3. **196x innerHTML in Dashboards** - XSS-Risiko, nach und nach durch textContent ersetzen

## Support

- Orchestrator Status: `node bots/unified-orchestrator.js status`
- Alle Logs: `ls -la logs/`
- Audit Report: `FINAL_SYSTEM_AUDIT_AND_PRIORITIZATION.md`
