# 🏗️ MASTER ARCHITEKTUR - RudiBot Ökosystem
## Ziel: Zentrale Integration aller Services

---

## 📐 Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │  Telegram   │  │   Web App   │  │  Dashboard  │  │  Mobile  │ │
│  │    Bot      │  │  (Next.js)  │  │  (Port 8888)│  │  (PWA)   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
└─────────┼────────────────┼────────────────┼──────────────┼────────┘
          │                │                │              │
          ▼                ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      WINDSURF API GATEWAY                           │
│                   (Zentraler Router - Port 8080)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │   Auth      │  │  Rate Limit │  │   Logging   │  │  Health  │ │
│  │  (JWT)      │  │  (Redis)    │  │  (Winston)  │  │  Check   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
└─────────┼────────────────┼────────────────┼──────────────┼────────┘
          │                │                │              │
          ▼                ▼                ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SERVICE LAYER (Microservices)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │ supermega│ │  shopify │ │ windsurf │ │  creator │ │  auto  │ │
│  │   bot    │ │   api    │ │ telegram │ │   ai     │ │ income │ │
│  │ (8888)   │ │ (3000)   │ │  (8003)  │ │ (3002)   │ │(3003)  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘ │
└───────┼────────────┼────────────┼────────────┼───────────┼────────┘
        │            │            │            │           │
        └────────────┴────────────┴────────────┴───────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │   Supabase      │  │    Redis        │  │    File System      │ │
│  │  (PostgreSQL)   │  │   (Cache)       │  │    (Logs/Backups)   │ │
│  │                 │  │                 │  │                     │ │
│  │ • Users         │  │ • Sessions      │  │ • Configs           │ │
│  │ • Products      │  │ • Rate Limits   │  │ • Analytics         │ │
│  │ • Orders        │  │ • Job Queues    │  │ • Backups           │ │
│  │ • Subscriptions │  │ • Webhooks      │  │ • Logs              │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔗 Service-Verbindungen

### supermegabot (Dashboard Hub)
- **Port**: 8888
- **Role**: Zentrales Dashboard & Bot-Steuerung
- **Verbindungen**:
  - ← Telegram Hub Bridge (Long-Polling)
  - ← Telegram Webhook (/webhook/telegram)
  - → Shopify API (Status/Produkte)
  - → Ollama (lokale LLM)
  - → Alle externen Services via CommandRouter

### windsurf-api-gateway
- **Port**: 8080
- **Role**: API Gateway & Router
- **Verbindungen**:
  - ← Alle Frontend-Clients
  - → supermegabot (/api/proxy)
  - → shopify-automation-api
  - → windsurf-telegram-bot
  - → Alle Microservices

### shopify-automation-api
- **Port**: 3000
- **Role**: Shopify Automation Backend
- **Verbindungen**:
  - ← windsurf-api-gateway
  - → Shopify Admin API (GraphQL + REST)
  - → Supabase (Produkte, Bestellungen)
  - → Stripe (Zahlungen)

### windsurf-telegram-bot
- **Port**: 8003
- **Role**: Telegram Bot API
- **Verbindungen**:
  - ← Telegram Webhooks
  - → supermegabot (Bot-Commands)
  - → AI-APIs (Claude, OpenAI)

---

## 🔐 Auth-System (Shared)

```javascript
// windsurf-api-gateway/src/middleware/auth.js
const jwt = require('jsonwebtoken');
const { createClient } = require('@supabase/supabase-js');

class AuthMiddleware {
  constructor() {
    this.supabase = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_SERVICE_KEY
    );
  }

  async verifyToken(req, res, next) {
    const token = req.headers.authorization?.replace('Bearer ', '');
    if (!token) return res.status(401).json({ error: 'No token' });
    
    try {
      const { data: { user }, error } = await this.supabase.auth.getUser(token);
      if (error) throw error;
      req.user = user;
      next();
    } catch (e) {
      res.status(401).json({ error: 'Invalid token' });
    }
  }

  requireRole(role) {
    return (req, res, next) => {
      if (req.user?.role !== role) {
        return res.status(403).json({ error: 'Forbidden' });
      }
      next();
    };
  }
}
```

---

## 📡 Webhook-Routing

| Quelle | Ziel | Endpunkt | Zweck |
|--------|------|----------|-------|
| Telegram | supermegabot | POST /webhook/telegram | Bot-Nachrichten |
| Shopify | shopify-automation-api | POST /webhooks/shopify | Bestellungen |
| Stripe | shopify-automation-api | POST /webhooks/stripe | Zahlungen |
| Digistore24 | digistore24-automation | POST /webhooks/digistore | Verkäufe |
| GitHub | windsurf-github-app | POST /webhooks/github | Push Events |

---

## 🚀 Deployment-Strategie

### Railway (Backend-Services)
- supermegabot (Python aiohttp)
- windsurf-api-gateway (Node.js)
- shopify-automation-api (Node.js + Prisma)

### Vercel (Frontend)
- app-frontend (Next.js)
- autoincome-ai-dashboard (Next.js)

### Cloudflare (CDN + DNS)
- Alle Domains
- SSL-Zertifikate
- DDoS-Schutz

---

## 📊 Monitoring & Alerts

### Health-Check Endpoints
```
GET /health → { status: "ok", service: "name", uptime: 123 }
```

### Services zu überwachen
| Service | Endpoint | Kritisch? |
|---------|----------|-----------|
| supermegabot | /health | ✅ Ja |
| api-gateway | /health | ✅ Ja |
| shopify-api | /api/health | ✅ Ja |
| telegram-bot | /health | ⚠️ Medium |
| supabase | Intern | ✅ Ja |

### Alert-Kanäle
- Telegram Bot (Admin)
- E-Mail (Kritisch)
- Dashboard (Visual)

---

## 💰 Monetarisierungs-Flow

### 1. Shopify Automation SaaS
```
Benutzer → Pricing Page → Stripe Checkout → 
Webhook → Supabase (Subscription aktiv) → 
Dashboard freigeschaltet
```

### 2. Digistore24 Digital Products
```
Verkauf → Digistore Webhook → 
Telegram Alert → Gumroad Discord Verify → 
Zugang freigeschaltet
```

### 3. Telegram Bot Subscription
```
Benutzer → /subscribe → TON Payment → 
Webhook → Supabase (Status: active) → 
Premium Features freigeschaltet
```

---

## 🔄 CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy All Services
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Test supermegabot
        run: cd supermegabot && python3 test_bot_hub.py
      - name: Test shopify-api
        run: cd shopify-automation-api && npm test
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Railway
        run: railway up
      - name: Deploy to Vercel
        run: vercel --prod
```

---

## 📋 Umsetzungs-Reihenfolge

### Phase 1: Foundation (Woche 1)
- [x] Security Audit & Fixes
- [x] Telegram Webhook Endpunkte
- [ ] windsurf-api-gateway als zentralen Hub konfigurieren
- [ ] Shared Auth-System implementieren
- [ ] Einheitliche .env Management

### Phase 2: Integration (Woche 2)
- [ ] Alle Services über API Gateway verbinden
- [ ] Webhook-System zentralisieren
- [ ] PM2 Ecosystem File
- [ ] Health-Checks für alle Services

### Phase 3: Monetarisierung (Woche 3-4)
- [ ] Stripe-Integration
- [ ] Pricing Tiers implementieren
- [ ] Trial-System
- [ ] Digistore24-Automatisierung

### Phase 4: Deployment (Woche 4)
- [ ] Railway Deployment
- [ ] Vercel Deployment
- [ ] Cloudflare DNS
- [ ] Monitoring einrichten

---

## 🛠️ Technologie-Stack

| Layer | Technologie |
|-------|-------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Node.js (Express/Fastify), Python (aiohttp) |
| Database | Supabase (PostgreSQL), Redis |
| AI | Anthropic Claude API, OpenAI, Ollama |
| Bots | Telegram Bot API, node-telegram-bot-api |
| E-Commerce | Shopify Admin API, Stripe, Digistore24 |
| Deployment | Railway, Vercel, Cloudflare |
| DevOps | Docker, PM2, GitHub Actions |
| Monitoring | Winston, Sentry, UptimeRobot |
