# Windsurf Platform - Telegram Bot Integration

## Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Windsurf Platform                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                 │
│   │   Shopify   │     │   GitHub    │     │  Dashboard  │                 │
│   │  Service    │     │   Service   │     │   (UI)      │                 │
│   │  :3002      │     │   :3001     │     │   :8888     │                 │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                 │
│          │                   │                   │                          │
│          │    HTTP/Events    │    HTTP/Events    │                          │
│          └───────────────────┴───────────────────┘                          │
│                              │                                               │
│                   ┌──────────▼──────────┐                                   │
│                   │  Telegram Bot       │                                   │
│                   │  (Notification Hub) │                                   │
│                   │  :8000 / :8001      │                                   │
│                   └──────────┬──────────┘                                   │
│                              │                                               │
│                   ┌──────────▼──────────┐                                   │
│                   │   Telegram User     │                                   │
│                   │   (Mobile/Desktop)  │                                   │
│                   └─────────────────────┘                                   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Shared Services: MongoDB, Redis, Supabase (optional)               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Service-Map

| Service | Port | Beschreibung | Verbindung zum Bot |
|---------|------|--------------|-------------------|
| Telegram Bot | 8000/8001 | Notification Hub, Command Center | Zentral |
| Shopify Service | 3002 | E-Commerce Automation | Webhooks + API |
| GitHub Service | 3001 | Repo Management, CI/CD | Webhooks + API |
| Dashboard | 8888 | Web UI für Monitoring | API Calls |

## Kommunikationsfluss

### 1. Notification Pattern (Services -> Telegram)

Jeder Service kann über HTTP POST an den Bot Notifications senden:

```
POST http://telegram-bot:8000/api/send-notification
Content-Type: application/json

{
  "service": "shopify",
  "level": "info|warning|error|critical",
  "title": "Neue Bestellung #1234",
  "message": "Kunde Max Mustermann - €45,90",
  "metadata": {
    "order_id": 1234,
    "customer": "max@example.com"
  }
}
```

### 2. Command Pattern (Telegram -> Services)

Der Bot kann über interne APIs andere Services steuern:

```
# Bot empfängt: /shopify orders
# Bot ruft auf: GET http://shopify-service:3002/api/orders
# Bot antwortet in Telegram mit Ergebnis
```

### 3. Webhook Pattern (Extern -> Bot -> Services)

Externe Webhooks landen beim Bot und werden weitergeleitet:

```
GitHub Webhook -> POST /webhooks/github (Bot)
  -> Verifiziert Signature
  -> Sendet Notification an Telegram
  -> Leitet an GitHub Service weiter (optional)
```

## Umgebungsvariablen

Siehe `.env.platform` für die vollständige Konfiguration.

Wichtige Variablen für die Integration:

```bash
# Service Discovery (interne URLs)
TELEGRAM_BOT_URL=http://telegram-bot:8000
SHOPIFY_SERVICE_URL=http://shopify-service:3002
GITHUB_SERVICE_URL=http://github-service:3001
DASHBOARD_URL=http://dashboard:8888

# Telegram Bot Konfiguration
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Webhook Secrets (für alle Services)
SHOPIFY_WEBHOOK_SECRET=shared_secret
GITHUB_WEBHOOK_SECRET=shared_secret
```

## Integration-Module

### telegram-notification-client.js

Jeder Service importiert dieses Modul, um Notifications zu senden:

```javascript
import NotificationClient from './services/telegram-notification-client.js';

const notifier = new NotificationClient({
  botUrl: process.env.TELEGRAM_BOT_URL,
  serviceName: 'shopify'
});

// Sende Info-Notification
await notifier.info('Abandoned Cart erkannt', 'Kunde hat Warenkorb verlassen');

// Sende Error-Notification
await notifier.error('Shopify API Fehler', 'Rate limit überschritten');

// Sende Critical-Notification
await notifier.critical('System-Ausfall', 'Datenbank nicht erreichbar');
```

## Docker Compose

Alle Services starten mit einem Befehl:

```bash
docker-compose up -d
```

Siehe `docker-compose.yml` für die vollständige Konfiguration.

## Deployment-Optionen

### Option A: Lokale Entwicklung (Docker Compose)
- Alle Services laufen lokal
- Shared Network über Docker
- Ideal für Entwicklung und Testing

### Option B: Railway (Cloud)
- Jeder Service als separate Railway-App
- Interne Railway-URLs für Service-Discovery
- Siehe `deploy-railway.sh` im Bot-Projekt

### Option C: Hybrid (Local + Cloud)
- Core Services lokal (Bot, Dashboard)
- Externe APIs in Cloud (Shopify, GitHub sind sowieso extern)

## Security

1. **Webhook Secrets**: Alle Webhooks werden mit HMAC-SHA256 signatur-verifiziert
2. **Interne URLs**: Services kommunizieren nur über interne Docker-URLs
3. **API Keys**: Werden niemals im Code gespeichert, nur in `.env`
4. **Telegram Tokens**: Werden nicht in Git gepusht (`.gitignore`)

## Monitoring

Der Bot sendet automatisch Alerts für:
- Service-Ausfälle (Health-Check-Failures)
- API-Errors (Rate Limits, Timeouts)
- Business-Events (Neue Bestellungen, Deployments)
- System-Warnungen (Speicher, CPU)

## Nächste Schritte

1. [ ] `docker-compose.yml` anpassen (Pfade zu Services)
2. [ ] `.env.platform` mit echten API-Keys füllen
3. [ ] Telegram Bot als Service in Compose einbinden
4. [ ] Shopify/Webhook-Validatoren mit Notification-Client erweitern
5. [ ] Health-Checks zwischen Services einrichten
