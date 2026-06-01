# My-Shop Backend

SuperMegaBot Shop API - Verbindet Frontend mit bestehendem E-Commerce System.

## Schnellstart

```bash
cd my-shop/backend
npm install
npm run dev
```

## API Endpunkte

| Route | Beschreibung |
|-------|-------------|
| `GET /api/health` | System-Status |
| `GET /api/produkte` | Alle Produkte |
| `GET /api/bestellungen` | Alle Bestellungen |
| `GET /api/marketing` | Kampagnen |
| `GET /api/analytics/dashboard` | Dashboard-Daten |
| `GET /api/system/status` | System-Info |

## Integration

Das Backend verbindet sich mit:
- `ecommerce-master-orchestrator.js`
- Shopify API
- Supabase
- Telegram Bots
