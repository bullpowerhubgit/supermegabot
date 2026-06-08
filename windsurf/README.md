# apitool - Universal KI-Assistent

Ein universeller KI-Assistent, der überall implementiert werden kann: Terminal, Browser, API, Library.

## Features

- **KI-Integration**: OpenAI (GPT-4o), Anthropic (Claude 3 Opus), Google Cloud Vertex AI (Gemini)
- **Browser-Steuerung**: Playwright-basierte Automatisierung (navigieren, klicken, tippen, Screenshots, Scrollen)
- **Mac-Systemsteuerung**: Maus, Tastatur, Tastenkombinationen, Apps öffnen, Clipboard
- **Google Cloud Services**: Translation, Vision, Speech/TTS, Storage, Firestore, Secret Manager, BigQuery, Logging
- **Shopify Integration**: Produkte, Bestellungen, Kunden, Inventory, Webhooks
- **Email Services**: SendGrid, Nodemailer (SMTP)
- **SMS Services**: Twilio
- **Payment Services**: Stripe (Payments, Subscriptions, Invoices)
- **Queue System**: Bull mit Redis (Job Queue)
- **Authentication**: JWT Tokens, Passport OAuth2
- **Data Import/Export**: CSV, Excel
- **CLI-Tool**: Interaktiver Chat im Terminal mit allen Services
- **Browser Extension**: Chrome/Firefox Extension für direkte Browser-Automatisierung
- **REST API**: Express-Server für Integration in andere Anwendungen

## Installation

```bash
npm install
```

## Build

```bash
npm run build
```

## Nutzung

### CLI (Terminal)

```bash
# Mit OpenAI
npm run cli -- chat --provider openai --key $OPENAI_API_KEY

# Mit Anthropic
npm run cli -- chat --provider anthropic --key $ANTHROPIC_API_KEY

# Mit Google Cloud Vertex AI (Gemini)
npm run cli -- chat --provider vertexai --key "$(cat gcp-config.json)" --project-id your-project-id

# Browser im sichtbaren Modus
npm run cli -- chat --provider openai --key $OPENAI_API_KEY --no-headless

# GCP Translation
npm run cli -- gcp:translate --project-id your-project-id --text "Hello World" --target de

# GCP Vision
npm run cli -- gcp:vision --project-id your-project-id --action detectLabels --image image.png

# GCP Speech
npm run cli -- gcp:speech --project-id your-project-id --action synthesize --text "Hallo" --language de-DE

# GCP Storage
npm run cli -- gcp:storage --project-id your-project-id --action list --bucket my-bucket

# GCP Firestore
npm run cli -- gcp:firestore --project-id your-project-id --action query --collection users

# GCP Secret Manager
npm run cli -- gcp:secret --project-id your-project-id --name my-secret

# GCP BigQuery
npm run cli -- gcp:bigquery --project-id your-project-id --query "SELECT * FROM dataset.table"

# Shopify Produkte
npm run cli -- shopify:products --shop-domain myshop.myshopify.com --access-token token

# Shopify Bestellungen
npm run cli -- shopify:orders --shop-domain myshop.myshopify.com --access-token token

# E-Mail senden
npm run cli -- email:send --provider sendgrid --to user@example.com --subject "Test" --text "Hello"

# SMS senden
npm run cli -- sms:send --to +1234567890 --body "Hello from apitool"

# Stripe Payment
npm run cli -- stripe:payment --amount 1000 --currency usd

# Queue Job hinzufügen
npm run cli -- queue:add --queue-name my-queue --job-name process-data --data '{"key":"value"}'

# JWT Token generieren
npm run cli -- auth:token --payload '{"user":"test"}'

# CSV Import
npm run cli -- data:import --file-path data.csv --format csv
```

### API Server

```bash
# Starten
npm run dev

# Oder nach Build
npm start
```

API Endpoints:

- `POST /api/chat` - Chat mit KI (mit Tool-Calling)
- `POST /api/browser` - Browser-Steuerung
- `POST /api/mac` - Mac-Steuerung
- `POST /api/gcp/translation` - Text übersetzen
- `POST /api/gcp/vision` - Bildanalyse
- `POST /api/gcp/speech` - Audio transkribieren/synthesieren
- `POST /api/gcp/storage` - Storage verwalten
- `POST /api/gcp/firestore` - Firestore verwalten
- `GET /api/gcp/secret/:secretName` - Secret abrufen
- `POST /api/gcp/bigquery` - SQL Query ausführen
- `POST /api/shopify` - Shopify API (Produkte, Bestellungen, Kunden, etc.)
- `POST /api/email` - E-Mail senden (SendGrid/Nodemailer)
- `POST /api/sms` - SMS senden (Twilio)
- `POST /api/stripe` - Stripe Payments (Payments, Subscriptions, Invoices)
- `POST /api/queue` - Queue Jobs verwalten (Bull/Redis)
- `POST /api/auth` - Authentication (JWT Tokens)
- `POST /api/data` - Data Import/Export (CSV/Excel)
- `DELETE /api/session/:sessionId` - Session schließen

Beispiel:

```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "test-session",
    "provider": "openai",
    "apiKey": "your-key",
    "messages": [{"role": "user", "content": "Öffne google.com"}]
  }'
```

### Browser Extension

1. Build: `npm run build`
2. Chrome: `chrome://extensions/` → Developer Mode → Load unpacked → `dist/extension`
3. Klicke auf das Extension-Icon im Browser

### Als Library

```typescript
import { AIClient, BrowserController, MacController } from 'apitool';

const ai = new AIClient({
  provider: 'openai',
  apiKey: 'your-key',
});

const browser = new BrowserController();
await browser.init(false); // sichtbar

const mac = new MacController();
await mac.execute({ action: 'type', text: 'Hello' });
```

## Umgebungsvariablen

- `OPENAI_API_KEY` - OpenAI API Key
- `ANTHROPIC_API_KEY` - Anthropic API Key
- `GCP_CONFIG` - GCP Service Account JSON (für Vertex AI)
- `GCP_PROJECT_ID` - GCP Project ID (für GCP Services)
- `SHOPIFY_SHOP_DOMAIN` - Shopify Shop Domain
- `SHOPIFY_ACCESS_TOKEN` - Shopify Access Token
- `SENDGRID_API_KEY` - SendGrid API Key
- `TWILIO_ACCOUNT_SID` - Twilio Account SID
- `TWILIO_AUTH_TOKEN` - Twilio Auth Token
- `TWILIO_FROM_NUMBER` - Twilio Absender-Nummer
- `STRIPE_API_KEY` - Stripe API Key
- `JWT_SECRET` - JWT Secret
- `PORT` - API Server Port (default: 3000)

## Projektstruktur

```
src/
├── core/           # Core Library (KI, Browser, Mac, GCP, Shopify, Email, SMS, Stripe, Queue, Auth, Data)
│   ├── ai.ts
│   ├── browser.ts
│   ├── mac.ts
│   ├── gcp.ts
│   ├── shopify.ts
│   ├── email.ts
│   ├── sms.ts
│   ├── stripe.ts
│   ├── queue.ts
│   ├── auth.ts
│   ├── data.ts
│   └── types.ts
├── cli/            # CLI-Tool
│   └── index.ts
├── api/            # REST API Server
│   └── server.ts
└── extension/      # Browser Extension
    ├── manifest.json
    ├── popup.html
    ├── popup.js
    ├── content.js
    └── background.js
```

## Lizenz

MIT
