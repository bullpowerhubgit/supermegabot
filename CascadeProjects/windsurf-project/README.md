# Windsurf Platform

Vollautomatische E-Commerce & Marketing-Plattform mit Telegram-Integration.

## Architektur

```
Telegram Bot (:8000)     ←→     Shopify Service (:3002)
      ↓                           GitHub Service (:3001)
 Dashboard (:8888)                MongoDB + Redis
```

**Der Telegram Bot ist das zentrale Command Center** – er empfängt Notifications von allen Services und erlaubt Steuerung über Telegram Commands.

## Quick Start (Standalone Telegram Bot)

### 1. Konfiguration

```bash
# .env erstellen (mit echten Keys vorausgefüllt)
cp .env.platform .env

# Optional: .env mit zusätzlichen Keys erweitern
nano .env
```

### 2. Telegram Bot starten

```bash
# Nur den Telegram Bot starten
docker-compose up -d telegram-bot

# Optional: Mit MongoDB für Persistence
docker-compose --profile with-db up -d

# Optional: Mit Redis für Caching
docker-compose --profile with-cache up -d
```

### 3. Status prüfen

```bash
# Telegram Bot Health Check
curl http://localhost:8000/health

# Bot API Test
curl http://localhost:8000/api/status
```

## Services (Standalone)

| Service | Port | Beschreibung |
|---------|------|--------------|
| Telegram Bot | 8000 | Notification Hub, Commands |
| MongoDB | 27017 | Optional: Bot Data Persistence |
| Redis | 6379 | Optional: Cache & Sessions |

**Externe Services** (laufen außerhalb Docker):
- Shopify Service: `http://localhost:3002` (dein eigener Service)
- GitHub Service: `http://localhost:3001` (dein eigener Service)  
- Dashboard: `http://localhost:8888` (dein eigener Service)

## Telegram Commands

- `/status` – Alle Services prüfen
- `/shopify orders` – Letzte Bestellungen
- `/github repos` – Repo-Liste
- `/automation` – Automation-Status

## Notification-Client verwenden

Jeder Service kann Notifications an Telegram senden:

```javascript
import NotificationClient from './services/telegram-notification-client.js';

const notifier = new NotificationClient({ serviceName: 'shopify' });
await notifier.info('Neue Bestellung', '€45,90');
await notifier.error('API Fehler', 'Rate limit überschritten');
await notifier.critical('System-Ausfall', 'DB nicht erreichbar');
```

## Logs

```bash
# Alle Services
docker-compose logs -f

# Einzelner Service
docker-compose logs -f telegram-bot
docker-compose logs -f shopify-service
```

## Weitere Dokumentation

- [Architektur-Details](platform-integration.md)
- [Shopify Automation](shopify-automation-solution.md)
- [Validierungs-Report](VALIDATION_REPORT.md)
