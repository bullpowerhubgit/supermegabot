# API Test Suite für SuperMegaBot

Diese Test-Suite validiert alle neuen API-Integrationen, die wir in den Bot einbauen wollen.

## 🚀 Setup

```bash
cd test-apis
npm install
cp ../.env.example .env
# .env mit echten API-Keys befüllen
```

## 🧪 Tests ausführen

### Einzelne APIs testen
```bash
npm run test:github      # GitHub API (Tokens, Repos, Issues)
npm run test:supabase    # Supabase (DB, CRUD, Real-time)
npm run test:stripe      # Stripe (Payments, Webhooks)
npm run test:shopify     # Shopify (Store, Products, Orders)
npm run test:klaviyo     # Klaviyo (Email Marketing, Campaigns)
npm run test:printify    # Printify (Print-on-Demand, Products)
```

### Alle Tests auf einmal
```bash
npm run test:all
```

## 📋 Was wird getestet

### GitHub API
- ✅ Token-Authentifizierung (Classic + Fine-Grained)
- ✅ Repository-Liste
- ✅ Issue-Erstellung und -Schließung
- ✅ Berechtigungsprüfung

### Supabase
- ✅ Datenbankverbindung (Anon + Service Keys)
- ✅ CRUD-Operationen (Create, Read, Update, Delete)
- ✅ Real-time Subscriptions
- ✅ Auth-System

### Stripe
- ✅ Account-Informationen
- ✅ Produkt- und Preis-Management
- ✅ Payment Links
- ✅ Webhook-Endpoints
- ✅ Transaktionshistorie

### Shopify
- ✅ Store-Informationen
- ✅ Produkt-Management
- ✅ Bestellhistorie
- ✅ Kunden-Daten
- ✅ Webhook-Setup

### Klaviyo
- ✅ Account-Verbindung
- ✅ Campaign-Management
- ✅ Listen-Management
- ✅ Profile-Operationen
- ✅ Metrics-Tracking

### Printify
- ✅ Shop-Verbindung
- ✅ Produkt-Katalog
- ✅ Bestell-Management
- ✅ Print-Provider
- ✅ Upload-Fähigkeit

## 🤝 Claude Desktop Integration

Diese Tests sind perfekt für die Zusammenarbeit mit Claude Desktop:

1. **Testergebnisse analysieren** - Claude hilft bei der Interpretation von API-Fehlern
2. **API-Optimierung** - Claude schlägt bessere Implementierungen vor
3. **Bot-Integration** - Claude hilft bei der Integration der APIs in den windsurf-telegram-bot
4. **Troubleshooting** - Claude hilft bei der Fehlersuche und Lösungsentwicklung

## 📊 Nächste Schritte

Nach erfolgreichen Tests:

1. ✅ API-Integration in windsurf-telegram-bot einbauen
2. ✅ Environment Variables für Railway/Vercel aktualisieren
3. ✅ Bot-Funktionen erweitern (GitHub-Automation, Shopify-Management, etc.)
4. ✅ Webhook-Handler implementieren

## 🔧 Fehlerbehebung

- **GitHub**: Token-Rechte prüfen (repo, issues:write)
- **Supabase**: RLS-Policies und Table-Berechtigungen
- **Stripe**: API-Key-Modus (live/test) und Webhook-Setup
- **Shopify**: Admin API Token und App-Berechtigungen
- **Klaviyo**: Private API Key und Scopes
- **Printify**: Shop-ID und Provider-Verfügbarkeit
