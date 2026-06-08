# RudiBot Security Suite v3.0

👑 **King of Tools** — Enterprise-grade Security & Billing for RudiBot

---

## Features

### 🔐 Authentication & Authorization
- **Supabase Auth Integration** — JWT-based authentication
- **Role-Based Access Control** — free, starter, pro, enterprise
- **API Key Support** — `x-api-key` header for system integrations
- **Middleware**: `requireAuth()`, `requireRole()`, `requireAuthOrApiKey()`

### 💰 Billing & Usage Tracking
- **Stripe Plan Enforcement** — Automatic plan checks
- **Daily Usage Tracking** — API calls, shop syncs, emails sent
- **Rate Limiting** — Per-plan API call limits
- **Feature Gating** — `requireFeature()` middleware
- **Middleware**: `checkPlanLimits()`, `requireFeature()`, `getBillingInfo()`

### 🔒 Webhook Security
- **HMAC Signature Verification** — Timing-safe comparison
- **Stripe Webhook Verification** — Built-in Stripe signature check
- **Shopify Webhook Verification** — HMAC-SHA256 validation
- **Replay Attack Protection** — 5-minute timestamp window
- **Middleware**: `verifyHmacWebhook()`, `verifyStripeWebhook()`, `verifyShopifyWebhook()`

### 🗄️ Database Schema
- **Supabase Integration** — PostgreSQL with Row Level Security
- **Tables**: `users`, `shops`, `products`, `usage_daily`, `webhooks`, `audit_log`
- **RLS Policies** — User data isolation
- **Audit Logging** — All actions tracked

### 🛡️ Secret Scanning
- **Pre-commit Hook** — Automatic secret detection
- **Pattern Matching** — API keys, tokens, secrets
- **Clean `.env.example`** — 50+ environment variables

### 🚀 Deployment
- **Railway Config** — `railway.toml` for easy deployment
- **Vercel Entry-Point** — Serverless-optimized
- **Health Checks** — `/health` endpoint

---

## Quick Start

### 1. Setup Environment

```bash
cd ~/windsurf
./setup-env.sh
```

### 2. Configure Supabase

1. Create a Supabase project at https://supabase.com
2. Run the schema:
   ```bash
   psql -h db.xxx.supabase.co -U postgres -d postgres < src/db/schema.sql
   ```
3. Copy environment variables to `.env`:
   ```bash
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SERVICE_KEY=your-service-role-key
   SUPABASE_ANON_KEY=your-anon-key
   ```

### 3. Configure Stripe

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_STARTER_PRICE_ID=price_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_ENTERPRISE_PRICE_ID=price_...
```

### 4. Run Development Server

```bash
npm run dev
```

---

## API Endpoints

### Public Endpoints
- `GET /` — API info
- `GET /health` — Health check
- `GET /api/orchestrator` — Service status
- `GET /api/orchestrator/health` — Full health check

### Protected Endpoints (Auth Required)
- `GET /api/billing/info` — User billing info
- `POST /api/chat` — AI chat (with usage tracking)
- `POST /api/browser/action` — Browser automation (feature-gated)

### Webhook Endpoints (Signature Verified)
- `POST /api/webhooks/stripe` — Stripe webhooks
- `POST /api/webhooks/shopify` — Shopify webhooks
- `POST /api/webhooks/generic` — Generic HMAC webhooks

---

## Middleware Usage

### Auth Middleware

```typescript
import { requireAuth, requireRole } from '../middleware/auth.js';

// Require authentication
app.get('/api/profile', requireAuth, (req, res) => {
  res.json({ user: req.user });
});

// Require specific role
app.get('/api/admin', requireAuth, requireRole(['admin', 'enterprise']), (req, res) => {
  res.json({ admin: true });
});
```

### Billing Middleware

```typescript
import { checkPlanLimits, requireFeature } from '../middleware/billing.js';

// Check plan limits
app.post('/api/chat', requireAuth, checkPlanLimits, (req, res) => {
  // Automatically tracks usage
  res.json({ response: '...' });
});

// Require specific feature
app.post('/api/browser', requireAuth, requireFeature('browser_automation'), (req, res) => {
  res.json({ result: '...' });
});
```

### Webhook Middleware

```typescript
import { verifyStripeWebhook, verifyShopifyWebhook } from '../middleware/webhook.js';

app.post('/api/webhooks/stripe', verifyStripeWebhook, (req, res) => {
  const event = req.stripeEvent;
  res.json({ received: true });
});
```

---

## Plan Limits

| Plan | Max Shops | Max Products | Daily API Calls | Features |
|------|-----------|--------------|----------------|----------|
| Free | 1 | 100 | 1,000 | basic_chat, health_check |
| Starter | 3 | 1,000 | 10,000 | + shopify_sync, email_automation |
| Pro | 10 | 10,000 | 100,000 | + ai_assistant, webhook_automation |
| Enterprise | ∞ | ∞ | ∞ | All features |

---

## Security Best Practices

1. **Never commit `.env`** — Use `.env.example` as template
2. **Use environment variables** — All secrets in env vars
3. **Enable RLS** — Row Level Security on all tables
4. **Verify webhooks** — Always use signature verification
5. **Rate limit** — Protect against abuse
6. **Audit logs** — Track all sensitive actions

---

## Files Added

```
src/
├── middleware/
│   ├── auth.ts          # Supabase Auth middleware
│   ├── billing.ts       # Stripe billing middleware
│   └── webhook.ts       # HMAC webhook verification
├── db/
│   └── schema.sql       # Supabase database schema
├── services/
│   └── index.ts         # Unified services export
└── opencode-sdk/
    └── openclaw-client.ts # OpenClaw WebSocket client

.github/hooks/
└── pre-commit           # Secret scanning hook

.env.example            # Clean environment template
railway.toml            # Railway deployment config
setup-env.sh            # Environment setup script
```

---

## Testing

```bash
# Run tests (requires Jest setup)
npm test

# Run TypeScript build
npm run build

# Run development server
npm run dev
```

---

## Deployment

### Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize
railway init

# Deploy
railway up
```

### Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel --prod
```

---

## Support

- **GitHub Issues**: https://github.com/bullpowerhubgit/supermegabot/issues
- **Documentation**: See inline code comments
- **PR**: https://github.com/bullpowerhubgit/supermegabot/pull/31

---

**Version**: 3.0  
**License**: MIT  
**Status**: Production Ready ✅
